#!/usr/bin/env python3
"""
Peregrine preflight check.

Scans for port conflicts, assesses system resources (RAM / CPU / GPU),
recommends a Docker Compose profile, and calculates optional vLLM KV-cache
CPU offload when VRAM is tight.  Writes resolved settings to .env so docker
compose picks them up automatically.

When a managed service (ollama, vllm, vision, searxng) is already running
on its configured port, preflight *adopts* it: the app is configured to reach
it via host.docker.internal, and a compose.override.yml is generated to
prevent Docker from starting a conflicting container.

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
USER_YAML    = ROOT / "config" / "user.yaml"
LLM_YAML     = ROOT / "config" / "llm.yaml"
ENV_FILE     = ROOT / ".env"
OVERRIDE_YML = ROOT / "compose.override.yml"

# ── Service table ──────────────────────────────────────────────────────────────
# (yaml_key, default_port, env_var, docker_owned, adoptable)
#
# docker_owned  — True if Docker Compose normally starts this service
# adoptable     — True if an existing process on this port should be used instead
#                 of starting a Docker container (and the Docker service disabled)
_SERVICES: dict[str, tuple[str, int, str, bool, bool]] = {
    "streamlit": ("streamlit_port", 8501, "STREAMLIT_PORT", True,  False),
    "searxng":   ("searxng_port",   8888, "SEARXNG_PORT",   True,  True),
    "vllm":      ("vllm_port",      8000, "VLLM_PORT",      True,  True),
    "vision":    ("vision_port",    8002, "VISION_PORT",    True,  True),
    "ollama":    ("ollama_port",  11434,  "OLLAMA_PORT",    True,  True),
}

# LLM yaml backend keys → url suffix, keyed by service name
_LLM_BACKENDS: dict[str, list[tuple[str, str]]] = {
    "ollama": [("ollama", "/v1"), ("ollama_research", "/v1")],
    "vllm":   [("vllm", "/v1")],
    "vision": [("vision_service", "")],
}

# Docker-internal hostname:port for each service (when running in Docker)
_DOCKER_INTERNAL: dict[str, tuple[str, int]] = {
    "ollama":  ("ollama",  11434),
    "vllm":    ("vllm",    8000),
    "vision":  ("vision",  8002),
    "searxng": ("searxng", 8080),   # searxng internal port differs from host port
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
    for name, (yaml_key, default, env_var, docker_owned, adoptable) in _SERVICES.items():
        configured = int(svc.get(yaml_key, default))
        free = is_port_free(configured)

        if free:
            # Port is free — start Docker service as normal
            resolved = configured
            stub_port = configured
            external = False
        elif adoptable:
            # Port is in use by a compatible service — adopt it.
            # resolved = actual external port (used for host.docker.internal URL)
            # stub_port = free port for the no-op stub container (avoids binding conflict)
            resolved = configured
            stub_port = find_free_port(configured + 1)
            external = True
        else:
            # Port in use, not adoptable (e.g. streamlit) — reassign
            resolved = find_free_port(configured + 1)
            stub_port = resolved
            external = False

        results[name] = {
            "configured":   configured,
            "resolved":     resolved,
            "stub_port":    stub_port,
            "changed":      resolved != configured,
            "docker_owned": docker_owned,
            "adoptable":    adoptable,
            "free":         free,
            "external":     external,
            "env_var":      env_var,
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


# ── Config writers ─────────────────────────────────────────────────────────────

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


def update_llm_yaml(ports: dict[str, dict]) -> None:
    """Rewrite base_url entries in config/llm.yaml to match adopted/internal services."""
    if not LLM_YAML.exists():
        return
    cfg = yaml.safe_load(LLM_YAML.read_text()) or {}
    backends = cfg.get("backends", {})
    changed = False

    for svc_name, backend_list in _LLM_BACKENDS.items():
        if svc_name not in ports:
            continue
        info = ports[svc_name]
        port = info["resolved"]

        if info["external"]:
            # Reach the host service from inside the Docker container
            host = f"host.docker.internal:{port}"
        elif svc_name in _DOCKER_INTERNAL:
            # Use Docker service name + internal port
            docker_host, internal_port = _DOCKER_INTERNAL[svc_name]
            host = f"{docker_host}:{internal_port}"
        else:
            continue

        for backend_name, url_suffix in backend_list:
            if backend_name in backends:
                new_url = f"http://{host}{url_suffix}"
                if backends[backend_name].get("base_url") != new_url:
                    backends[backend_name]["base_url"] = new_url
                    changed = True

    if changed:
        cfg["backends"] = backends
        LLM_YAML.write_text(yaml.dump(cfg, default_flow_style=False, allow_unicode=True,
                                      sort_keys=False))


def write_compose_override(ports: dict[str, dict]) -> None:
    """
    Generate compose.override.yml to stub out Docker services that are being
    adopted from external processes.  Cleans up the file when nothing to disable.

    Stubbing strategy (not profiles): changing a service's profile to an unused
    value breaks depends_on references — Docker treats it as undefined.  Instead
    we replace the service with a no-op stub that:
      - Stays alive (sleep infinity) so depends_on: service_started is satisfied
      - Reports healthy immediately so depends_on: service_healthy is satisfied
      - Binds no ports (no conflict with the external service on the host)
    """
    to_disable = {
        name: info for name, info in ports.items()
        if info["external"] and info["docker_owned"]
    }

    if not to_disable:
        if OVERRIDE_YML.exists():
            OVERRIDE_YML.unlink()
        return

    lines = [
        "# compose.override.yml — AUTO-GENERATED by preflight.py, do not edit manually.",
        "# Stubs out Docker services whose ports are already in use by host services.",
        "# Re-run preflight (make preflight) to regenerate after stopping host services.",
        "services:",
    ]
    for name, info in to_disable.items():
        lines += [
            f"  {name}:  # adopted — host service on :{info['resolved']}",
            f"    entrypoint: [\"/bin/sh\", \"-c\", \"sleep infinity\"]",
            f"    ports: []",
            f"    healthcheck:",
            f"      test: [\"CMD\", \"true\"]",
            f"      interval: 1s",
            f"      timeout: 1s",
            f"      start_period: 0s",
            f"      retries: 1",
        ]

    OVERRIDE_YML.write_text("\n".join(lines) + "\n")


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

    # Single-service mode — used by manage.sh / manage-ui.sh
    if args.service:
        info = ports.get(args.service.lower())
        if info:
            print(info["resolved"])
        else:
            _, default, *_ = _SERVICES.get(args.service.lower(), (None, 8501, None, None, None))
            print(default)
        return

    ram_total, ram_avail = get_ram_gb()
    cpu_cores = get_cpu_cores()
    gpus = get_gpus()
    profile = recommend_profile(gpus, ram_total)
    offload_gb = calc_cpu_offload_gb(gpus, ram_avail)

    if not args.quiet:
        print("╔══ Peregrine Preflight ══════════════════════════════╗")
        print("║")
        print("║  Ports")
        for name, info in ports.items():
            if info["external"]:
                status = f"✓ adopted  (using host service on :{info['resolved']})"
                tag = "extern"
            elif not info["docker_owned"]:
                status = "⚠ not responding" if info["free"] else "✓ reachable"
                tag = "extern"
            elif info["free"]:
                status = "✓ free"
                tag = "owned "
            elif info["changed"]:
                status = f"→ reassigned to :{info['resolved']}"
                tag = "owned "
            else:
                status = "⚠ in use"
                tag = "owned "
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

        reassigned = [n for n, i in ports.items() if i["changed"]]
        adopted    = [n for n, i in ports.items() if i["external"]]

        if reassigned:
            print("║")
            print("║  Port reassignments written to .env:")
            for name in reassigned:
                info = ports[name]
                print(f"║    {info['env_var']}={info['resolved']}  (was :{info['configured']})")

        if adopted:
            print("║")
            print("║  Adopted external services (Docker containers disabled):")
            for name in adopted:
                info = ports[name]
                print(f"║    {name} :{info['resolved']}  → app will use host.docker.internal:{info['resolved']}")

        print("╚════════════════════════════════════════════════════╝")

    if not args.check_only:
        # For adopted services, write stub_port to .env so the no-op container
        # binds a harmless free port instead of conflicting with the external service.
        env_updates: dict[str, str] = {i["env_var"]: str(i["stub_port"]) for i in ports.values()}
        env_updates["RECOMMENDED_PROFILE"] = profile
        if offload_gb > 0:
            env_updates["CPU_OFFLOAD_GB"] = str(offload_gb)
        write_env(env_updates)
        update_llm_yaml(ports)
        write_compose_override(ports)
        if not args.quiet:
            artifacts = [str(ENV_FILE.relative_to(ROOT))]
            if OVERRIDE_YML.exists():
                artifacts.append(str(OVERRIDE_YML.relative_to(ROOT)))
            print(f"  wrote {', '.join(artifacts)}")

    # Fail only when a non-adoptable owned port couldn't be reassigned
    stuck = [n for n, i in ports.items()
             if not i["free"] and not i["external"] and not i["changed"]]
    sys.exit(1 if stuck else 0)


if __name__ == "__main__":
    main()
