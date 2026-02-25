#!/usr/bin/env python3
"""
Peregrine preflight check.

Scans for port conflicts, assesses system resources (RAM / CPU / GPU),
recommends a Docker Compose profile, and calculates optional vLLM KV-cache
CPU offload when VRAM is tight.  Writes resolved settings to .env so docker
compose picks them up automatically.

Usage:
    python scripts/preflight.py              # full report + write .env
    python scripts/preflight.py --check-only # report only, no .env write
    python scripts/preflight.py --service streamlit  # print resolved port, exit
    python scripts/preflight.py --quiet      # machine-readable, exit 0/1

Exit codes:
  0 — all checks passed (or issues auto-resolved)
  1 — manual action required (unresolvable port conflict on external service)
"""
import argparse
import platform
import socket
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).parent.parent
USER_YAML = ROOT / "config" / "user.yaml"
ENV_FILE = ROOT / ".env"

# ── Port table ────────────────────────────────────────────────────────────────
# (yaml_key, default, env_var, peregrine_owns_it)
_PORTS: dict[str, tuple[str, int, str, bool]] = {
    "streamlit": ("streamlit_port",   8501, "STREAMLIT_PORT", True),
    "searxng":   ("searxng_port",     8888, "SEARXNG_PORT",   True),
    "vllm":      ("vllm_port",        8000, "VLLM_PORT",      True),
    "vision":    ("vision_port",      8002, "VISION_PORT",    True),
    "ollama":    ("ollama_port",     11434, "OLLAMA_PORT",    False),
}


# ── System probes (stdlib only — no psutil) ───────────────────────────────────

def _sh(*cmd: str, timeout: int = 5) -> str:
    try:
        r = subprocess.run(list(cmd), capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip() if r.returncode == 0 else ""
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return ""


def get_ram_gb() -> tuple[float, float]:
    """Return (total_gb, available_gb).  Returns (0, 0) if undetectable."""
    os_name = platform.system()
    if os_name == "Linux":
        try:
            meminfo = Path("/proc/meminfo").read_text()
        except OSError:
            return 0.0, 0.0
        total = available = 0
        for line in meminfo.splitlines():
            if line.startswith("MemTotal:"):
                total = int(line.split()[1])
            elif line.startswith("MemAvailable:"):
                available = int(line.split()[1])
        return total / 1024 / 1024, available / 1024 / 1024
    elif os_name == "Darwin":
        total_bytes = _sh("sysctl", "-n", "hw.memsize")
        total = int(total_bytes) / 1024 ** 3 if total_bytes.isdigit() else 0.0
        vm = _sh("vm_stat")
        free_pages = 0
        for line in vm.splitlines():
            if "Pages free" in line or "Pages speculative" in line:
                try:
                    free_pages += int(line.split()[-1].rstrip("."))
                except ValueError:
                    pass
        available = free_pages * 4096 / 1024 ** 3
        return total, available
    return 0.0, 0.0


def get_cpu_cores() -> int:
    import os
    return os.cpu_count() or 1


def get_gpus() -> list[dict]:
    """Return list of {name, vram_total_gb, vram_free_gb} via nvidia-smi."""
    out = _sh(
        "nvidia-smi",
        "--query-gpu=name,memory.total,memory.free",
        "--format=csv,noheader,nounits",
    )
    if not out:
        return []
    gpus = []
    for line in out.splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) == 3:
            try:
                gpus.append({
                    "name": parts[0],
                    "vram_total_gb": round(int(parts[1]) / 1024, 1),
                    "vram_free_gb":  round(int(parts[2]) / 1024, 1),
                })
            except ValueError:
                pass
    return gpus


# ── Port probes ───────────────────────────────────────────────────────────────

def _load_svc() -> dict:
    if USER_YAML.exists():
        return (yaml.safe_load(USER_YAML.read_text()) or {}).get("services", {})
    return {}


def is_port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", port)) != 0


def find_free_port(start: int, limit: int = 30) -> int:
    for p in range(start, start + limit):
        if is_port_free(p):
            return p
    raise RuntimeError(f"No free port found in range {start}–{start + limit - 1}")


def check_ports(svc: dict) -> dict[str, dict]:
    results = {}
    for name, (yaml_key, default, env_var, owned) in _PORTS.items():
        configured = int(svc.get(yaml_key, default))
        free = is_port_free(configured)
        resolved = configured if (free or not owned) else find_free_port(configured + 1)
        results[name] = {
            "configured": configured,
            "resolved":   resolved,
            "changed":    resolved != configured,
            "owned":      owned,
            "free":       free,
            "env_var":    env_var,
        }
    return results


# ── Recommendations ───────────────────────────────────────────────────────────

def recommend_profile(gpus: list[dict], ram_total_gb: float) -> str:
    if len(gpus) >= 2:
        return "dual-gpu"
    if len(gpus) == 1:
        return "single-gpu"
    if ram_total_gb >= 8:
        return "cpu"
    return "remote"


def calc_cpu_offload_gb(gpus: list[dict], ram_available_gb: float) -> int:
    """
    Suggest GBs of KV cache to offload from GPU VRAM → system RAM.

    Enabled when VRAM is tight (< 10 GB free on any GPU) and there is
    enough RAM headroom (> 4 GB available).  Uses at most 25% of the
    RAM headroom above 4 GB, capped at 8 GB.
    """
    if not gpus or ram_available_gb < 4:
        return 0
    min_vram_free = min(g["vram_free_gb"] for g in gpus)
    if min_vram_free >= 10:
        return 0
    headroom = ram_available_gb - 4.0  # reserve 4 GB for OS
    return min(int(headroom * 0.25), 8)


# ── .env writer ───────────────────────────────────────────────────────────────

def write_env(updates: dict[str, str]) -> None:
    existing: dict[str, str] = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                existing[k.strip()] = v.strip()
    existing.update(updates)
    ENV_FILE.write_text(
        "\n".join(f"{k}={v}" for k, v in sorted(existing.items())) + "\n"
    )


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Peregrine preflight check")
    parser.add_argument("--check-only", action="store_true",
                        help="Print report; don't write .env")
    parser.add_argument("--quiet", action="store_true",
                        help="Suppress output; rely on exit code")
    parser.add_argument("--service", metavar="NAME",
                        help="Print resolved port for one service and exit (e.g. streamlit)")
    args = parser.parse_args()

    svc = _load_svc()
    ports = check_ports(svc)

    # Single-service mode — used by manage-ui.sh
    if args.service:
        info = ports.get(args.service.lower())
        print(info["resolved"] if info else _PORTS[args.service.lower()][1])
        return

    ram_total, ram_avail = get_ram_gb()
    cpu_cores = get_cpu_cores()
    gpus = get_gpus()
    profile = recommend_profile(gpus, ram_total)
    offload_gb = calc_cpu_offload_gb(gpus, ram_avail)

    if not args.quiet:
        reassigned = [n for n, i in ports.items() if i["changed"]]
        unresolved  = [n for n, i in ports.items() if not i["free"] and not i["changed"]]

        print("╔══ Peregrine Preflight ══════════════════════════════╗")
        print("║")
        print("║  Ports")
        for name, info in ports.items():
            tag = "owned " if info["owned"] else "extern"
            if not info["owned"]:
                # external: in-use means the service is reachable
                status = "✓ reachable" if not info["free"] else "⚠ not responding"
            elif info["free"]:
                status = "✓ free"
            elif info["changed"]:
                status = f"→ reassigned to :{info['resolved']}"
            else:
                status = "⚠ in use"
            print(f"║    {name:<10} :{info['configured']}  [{tag}]  {status}")

        print("║")
        print("║  Resources")
        print(f"║    CPU      {cpu_cores} core{'s' if cpu_cores != 1 else ''}")
        if ram_total:
            print(f"║    RAM      {ram_total:.0f} GB total  /  {ram_avail:.1f} GB available")
        else:
            print("║    RAM      (undetectable)")
        if gpus:
            for i, g in enumerate(gpus):
                print(f"║    GPU {i}    {g['name']}  —  "
                      f"{g['vram_free_gb']:.1f} / {g['vram_total_gb']:.0f} GB VRAM free")
        else:
            print("║    GPU      none detected")

        print("║")
        print("║  Recommendations")
        print(f"║    Docker profile   {profile}")
        if offload_gb > 0:
            print(f"║    vLLM KV offload  {offload_gb} GB → RAM  (CPU_OFFLOAD_GB={offload_gb})")
        else:
            print("║    vLLM KV offload  not needed")

        if reassigned:
            print("║")
            print("║  Port reassignments written to .env:")
            for name in reassigned:
                info = ports[name]
                print(f"║    {info['env_var']}={info['resolved']}  (was :{info['configured']})")

        # External services: in-use = ✓ running; free = warn (may be down)
        ext_down = [n for n, i in ports.items() if not i["owned"] and i["free"]]
        if ext_down:
            print("║")
            print("║  ⚠  External services not detected on configured port:")
            for name in ext_down:
                info = ports[name]
                svc_key = _PORTS[name][0]
                print(f"║    {name} :{info['configured']} — nothing listening "
                      f"(start the service or update services.{svc_key} in user.yaml)")

        print("╚════════════════════════════════════════════════════╝")

    if not args.check_only:
        env_updates: dict[str, str] = {i["env_var"]: str(i["resolved"]) for i in ports.values()}
        env_updates["RECOMMENDED_PROFILE"] = profile
        if offload_gb > 0:
            env_updates["CPU_OFFLOAD_GB"] = str(offload_gb)
        write_env(env_updates)
        if not args.quiet:
            print(f"  wrote {ENV_FILE.relative_to(ROOT)}")

    # Fail only when an owned port can't be resolved (shouldn't happen in practice)
    owned_stuck = [n for n, i in ports.items() if i["owned"] and not i["free"] and not i["changed"]]
    sys.exit(1 if owned_stuck else 0)


if __name__ == "__main__":
    main()
