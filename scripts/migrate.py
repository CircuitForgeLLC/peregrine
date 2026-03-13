#!/usr/bin/env python3
"""
Peregrine migration tool — import config and data from a legacy job-seeker repo.

Usage:
    python scripts/migrate.py                         # dry run (show what would change)
    python scripts/migrate.py --apply                 # write files
    python scripts/migrate.py --apply --copy-db       # also copy staging.db
    python scripts/migrate.py --source /path/to/repo  # non-default source

What it migrates:
  - config/user.yaml         (generated from source resume + scripts)
  - config/notion.yaml       (copied — contains live token)
  - config/email.yaml        (copied — contains IMAP credentials)
  - config/adzuna.yaml       (copied — API credentials)
  - config/craigslist.yaml   (copied — metro/location map)
  - config/search_profiles.yaml (copied — user's job search targets)
  - config/resume_keywords.yaml (copied)
  - config/blocklist.yaml    (copied)
  - config/llm.yaml          (merges fine-tuned model name from source)
  - aihawk/data_folder/plain_text_resume.yaml (copied if aihawk present)
  - staging.db               (optional — copies current DB state)
"""
import argparse
import shutil
import sys
from pathlib import Path
from textwrap import dedent

import yaml

ROOT = Path(__file__).parent.parent


def _load_yaml(path: Path) -> dict:
    if path.exists():
        return yaml.safe_load(path.read_text()) or {}
    return {}


def _write_yaml(path: Path, data: dict, apply: bool) -> None:
    text = yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False)
    if apply:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        print(f"  ✓ wrote {path.relative_to(ROOT)}")
    else:
        print(f"  (dry) would write {path.relative_to(ROOT)}")


def _copy_file(src: Path, dest: Path, apply: bool) -> bool:
    if not src.exists():
        print(f"  ✗ skip {dest.name} — not found at {src}")
        return False
    if apply:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        print(f"  ✓ copied {dest.relative_to(ROOT)}")
    else:
        print(f"  (dry) would copy {src} → {dest.relative_to(ROOT)}")
    return True


def _extract_career_summary(source: Path) -> str:
    """Pull career summary from source generate_cover_letter.py SYSTEM_CONTEXT."""
    gcl = source / "scripts" / "generate_cover_letter.py"
    if not gcl.exists():
        return ""
    text = gcl.read_text()
    start = text.find('SYSTEM_CONTEXT = """')
    if start == -1:
        start = text.find("SYSTEM_CONTEXT = '''")
    if start == -1:
        return ""
    start = text.find('"""', start) + 3
    end = text.find('"""', start)
    if end == -1:
        return ""
    block = text[start:end].strip()
    # Extract just the Background lines (skip the role description preamble)
    lines = [l.strip("- ").strip() for l in block.splitlines() if l.strip().startswith("-")]
    return " ".join(lines[:4]) if lines else block[:300]


def _extract_personal_info(source: Path) -> dict:
    """Extract personal info from resume yaml."""
    resume = source / "config" / "plain_text_resume.yaml"
    if not resume.exists():
        resume = source / "aihawk" / "data_folder" / "plain_text_resume.yaml"  # legacy path
    if not resume.exists():
        return {}
    data = _load_yaml(resume)
    info = data.get("personal_information", {})
    return {
        "name": f"{info.get('name', '')} {info.get('surname', '')}".strip(),
        "email": info.get("email", ""),
        "phone": str(info.get("phone", "")),
        "linkedin": info.get("linkedin", ""),
    }


def _extract_docs_dir(source: Path) -> str:
    """Try to find docs directory from source scripts."""
    gcl = source / "scripts" / "generate_cover_letter.py"
    if gcl.exists():
        for line in gcl.read_text().splitlines():
            if "LETTERS_DIR" in line and "Path(" in line:
                # e.g. LETTERS_DIR = Path("/Library/Documents/JobSearch")
                start = line.find('"')
                end = line.rfind('"')
                if start != end:
                    return line[start + 1:end]
    return "~/Documents/JobSearch"


def _build_user_yaml(source: Path, dest: Path, apply: bool) -> None:
    print("\n── Generating config/user.yaml")
    info = _extract_personal_info(source)
    career_summary = _extract_career_summary(source)
    docs_dir = _extract_docs_dir(source)

    # Mission preferences — extracted from source _MISSION_NOTES
    gcl_text = (source / "scripts" / "generate_cover_letter.py").read_text() \
        if (source / "scripts" / "generate_cover_letter.py").exists() else ""
    mission_prefs: dict = {}
    # The original _MISSION_NOTES encoded personal alignment notes inline;
    # we set sensible short personal notes for each industry.
    if "music" in gcl_text and "personal passion" in gcl_text:
        mission_prefs["music"] = (
            "I have a real personal passion for the music scene and would love "
            "to apply my CS skills in this space."
        )
    if "animal_welfare" in gcl_text or "animal" in gcl_text:
        mission_prefs["animal_welfare"] = (
            "Animal welfare is a dream domain for me — a genuine personal passion "
            "that deeply aligns with my values."
        )
    if "education" in gcl_text and "EdTech" in gcl_text:
        mission_prefs["education"] = (
            "Children's education and EdTech reflect genuine personal values around "
            "learning and young people that I'd love to connect to my CS work."
        )

    data = {
        "name": info.get("name", ""),
        "email": info.get("email", ""),
        "phone": info.get("phone", ""),
        "linkedin": info.get("linkedin", ""),
        "career_summary": career_summary,
        "nda_companies": [],
        "mission_preferences": mission_prefs,
        "candidate_accessibility_focus": False,
        "candidate_lgbtq_focus": False,
        "docs_dir": docs_dir,
        "ollama_models_dir": "~/models/ollama",
        "vllm_models_dir": "~/models/vllm",
        "inference_profile": "dual-gpu",
        "services": {
            "streamlit_port": 8501,
            "ollama_host": "localhost",
            "ollama_port": 11434,
            "ollama_ssl": False,
            "ollama_ssl_verify": True,
            "vllm_host": "localhost",
            "vllm_port": 8000,
            "vllm_ssl": False,
            "vllm_ssl_verify": True,
            "searxng_host": "localhost",
            "searxng_port": 8888,
            "searxng_ssl": False,
            "searxng_ssl_verify": True,
        },
    }
    _write_yaml(dest / "config" / "user.yaml", data, apply)

    if not apply:
        print(f"    name:    {data['name'] or '(not found)'}")
        print(f"    email:   {data['email'] or '(not found)'}")
        print(f"    docs:    {data['docs_dir']}")
        print(f"    profile: {data['inference_profile']}")


def _copy_configs(source: Path, dest: Path, apply: bool) -> None:
    print("\n── Copying config files")
    files = [
        "config/notion.yaml",
        "config/email.yaml",
        "config/adzuna.yaml",
        "config/craigslist.yaml",
        "config/search_profiles.yaml",
        "config/resume_keywords.yaml",
        "config/blocklist.yaml",
    ]
    for rel in files:
        _copy_file(source / rel, dest / rel, apply)


def _copy_aihawk_resume(source: Path, dest: Path, apply: bool) -> None:
    print("\n── Copying resume profile")
    src = source / "config" / "plain_text_resume.yaml"
    if not src.exists():
        src = source / "aihawk" / "data_folder" / "plain_text_resume.yaml"
    dst = dest / "config" / "plain_text_resume.yaml"
    _copy_file(src, dst, apply)


def _merge_llm_yaml(source: Path, dest: Path, apply: bool) -> None:
    """Copy the fine-tuned model name from source llm.yaml into dest llm.yaml."""
    print("\n── Merging llm.yaml (fine-tuned model name)")
    src_cfg = _load_yaml(source / "config" / "llm.yaml")
    dst_cfg = _load_yaml(dest / "config" / "llm.yaml")

    src_model = src_cfg.get("backends", {}).get("ollama", {}).get("model", "")
    if src_model and src_model != "llama3.2:3b":
        dst_cfg.setdefault("backends", {}).setdefault("ollama", {})["model"] = src_model
        print(f"  model: {src_model}")
        _write_yaml(dest / "config" / "llm.yaml", dst_cfg, apply)
    else:
        print(f"  no custom model in source — keeping {dst_cfg.get('backends', {}).get('ollama', {}).get('model', 'default')}")


def _copy_db(source: Path, dest: Path, apply: bool) -> None:
    print("\n── Copying staging database")
    _copy_file(source / "staging.db", dest / "staging.db", apply)


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate config from legacy job-seeker repo to Peregrine")
    parser.add_argument("--source", default="/devl/job-seeker",
                        help="Path to legacy job-seeker repo (default: /devl/job-seeker)")
    parser.add_argument("--dest", default=str(ROOT),
                        help="Path to Peregrine repo (default: this repo)")
    parser.add_argument("--apply", action="store_true",
                        help="Actually write files (default is dry run)")
    parser.add_argument("--copy-db", action="store_true",
                        help="Also copy staging.db")
    args = parser.parse_args()

    source = Path(args.source).expanduser().resolve()
    dest = Path(args.dest).expanduser().resolve()

    if not source.exists():
        print(f"Source repo not found: {source}", file=sys.stderr)
        sys.exit(1)

    mode = "APPLY" if args.apply else "DRY RUN"
    print(f"Peregrine migration [{mode}]")
    print(f"  source: {source}")
    print(f"  dest:   {dest}")

    _build_user_yaml(source, dest, args.apply)
    _copy_configs(source, dest, args.apply)
    _copy_aihawk_resume(source, dest, args.apply)
    _merge_llm_yaml(source, dest, args.apply)

    if args.copy_db:
        _copy_db(source, dest, args.apply)

    print()
    if args.apply:
        print("Migration complete.")
        print("Next: bash scripts/manage-ui.sh start")
    else:
        print("Dry run complete. Re-run with --apply to write files.")
        if args.copy_db or True:
            print("Add --copy-db to also migrate staging.db.")


if __name__ == "__main__":
    main()
