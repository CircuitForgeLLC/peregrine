# scripts/prepare_training_data.py
"""
Extract training pairs from the candidate's cover letter corpus for LoRA fine-tuning.

Outputs a JSONL file where each line is:
  {"instruction": "Write a cover letter for the [role] position at [company].",
   "output": "<full letter text>"}

Usage:
    conda run -n job-seeker python scripts/prepare_training_data.py
    conda run -n job-seeker python scripts/prepare_training_data.py --output /path/to/out.jsonl
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.user_profile import UserProfile
_USER_YAML = Path(__file__).parent.parent / "config" / "user.yaml"
_profile = UserProfile(_USER_YAML) if UserProfile.exists(_USER_YAML) else None

_docs_env = os.environ.get("DOCS_DIR", "")
_docs = Path(_docs_env) if _docs_env else (
    _profile.docs_dir if _profile else Path.home() / "Documents" / "JobSearch"
)
LETTERS_DIR = _docs
# Use two globs to handle mixed capitalisation ("Cover Letter" vs "cover letter")
LETTER_GLOBS = ["*Cover Letter*.md", "*cover letter*.md"]
DEFAULT_OUTPUT = _docs / "training_data" / "cover_letters.jsonl"

# Patterns that appear in opening sentences to extract role
ROLE_PATTERNS = [
    r"apply for (?:the )?(.+?) (?:position|role|opportunity) at",
    r"apply for (?:the )?(.+?) (?:at|with)\b",
]


def extract_role_from_text(text: str) -> str:
    """Try to extract the role title from the first ~500 chars of a cover letter."""
    # Search the opening of the letter, skipping past any greeting line
    search_text = text[:600]
    for pattern in ROLE_PATTERNS:
        m = re.search(pattern, search_text, re.IGNORECASE)
        if m:
            role = m.group(1).strip().rstrip(".")
            # Filter out noise — role should be ≤6 words
            if 1 <= len(role.split()) <= 6:
                return role
    return ""


def extract_company_from_filename(stem: str) -> str:
    """Extract company name from cover letter filename stem."""
    return re.sub(r"\s*Cover Letter.*", "", stem, flags=re.IGNORECASE).strip()


def strip_greeting(text: str) -> str:
    """Remove the 'Dear X,' line so the output is just the letter body + sign-off."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.strip().lower().startswith("dear "):
            # Skip the greeting line and any following blank lines
            rest = lines[i + 1:]
            while rest and not rest[0].strip():
                rest = rest[1:]
            return "\n".join(rest).strip()
    return text.strip()


def build_records(letters_dir: Path = LETTERS_DIR) -> list[dict]:
    """Parse all cover letters and return list of training records."""
    records = []
    seen: set[Path] = set()
    all_paths = []
    for glob in LETTER_GLOBS:
        for p in letters_dir.glob(glob):
            if p not in seen:
                seen.add(p)
                all_paths.append(p)
    for path in sorted(all_paths):
        text = path.read_text(encoding="utf-8", errors="ignore").strip()
        if not text or len(text) < 100:
            continue

        company = extract_company_from_filename(path.stem)
        role = extract_role_from_text(text)
        body = strip_greeting(text)

        if not role:
            # Use a generic instruction when role extraction fails
            instruction = f"Write a cover letter for a position at {company}."
        else:
            instruction = f"Write a cover letter for the {role} position at {company}."

        records.append({
            "instruction": instruction,
            "output": body,
            "source_file": path.name,
        })

    return records


def write_jsonl(records: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare LoRA training data from cover letter corpus")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output JSONL path")
    parser.add_argument("--letters-dir", default=str(LETTERS_DIR), help="Directory of cover letters")
    parser.add_argument("--stats", action="store_true", help="Print statistics and exit")
    args = parser.parse_args()

    records = build_records(Path(args.letters_dir))

    if args.stats:
        print(f"Total letters: {len(records)}")
        with_role = sum(1 for r in records if not r["instruction"].startswith("Write a cover letter for a position"))
        print(f"Role extracted: {with_role}/{len(records)}")
        avg_len = sum(len(r["output"]) for r in records) / max(len(records), 1)
        print(f"Avg letter length: {avg_len:.0f} chars")
        for r in records:
            print(f"  {r['source_file']!r:55s} → {r['instruction'][:70]}")
        return

    output_path = Path(args.output)
    write_jsonl(records, output_path)
    print(f"Wrote {len(records)} training records to {output_path}")
    print()
    print("Next step for LoRA fine-tuning:")
    print("  1. Download base model: huggingface-cli download meta-llama/Meta-Llama-3.1-8B-Instruct")
    print("  2. Fine-tune with TRL: see docs/plans/lora-finetune.md (to be created)")
    print("  3. Or use HuggingFace Jobs: bash scripts/manage-ui.sh — hugging-face-model-trainer skill")


if __name__ == "__main__":
    main()
