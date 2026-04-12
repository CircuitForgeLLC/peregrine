# scripts/generate_cover_letter.py
"""
Generate a cover letter in the candidate's voice using few-shot examples from their corpus.

Usage:
    conda run -n job-seeker python scripts/generate_cover_letter.py \
        --title "Director of Customer Success" \
        --company "Acme Corp" \
        --description "We are looking for..."

    Or pass a staging DB job ID:
        conda run -n job-seeker python scripts/generate_cover_letter.py --job-id 42
"""
import argparse
import re
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.user_profile import UserProfile
_USER_YAML = Path(__file__).parent.parent / "config" / "user.yaml"
_profile = UserProfile(_USER_YAML) if UserProfile.exists(_USER_YAML) else None

LETTERS_DIR = _profile.docs_dir if _profile else Path.home() / "Documents" / "JobSearch"
LETTER_GLOB = "*Cover Letter*.md"

# Background injected into every prompt so the model has the candidate's facts
def _build_system_context(profile=None) -> str:
    p = profile or _profile
    if not p:
        return "You are a professional cover letter writer. Write in first person."
    parts = [f"You are writing cover letters for {p.name}. {p.career_summary}"]
    if p.candidate_voice:
        parts.append(
            f"Voice and personality: {p.candidate_voice} "
            "Write in a way that reflects these authentic traits — not as a checklist, "
            "but as a natural expression of who this person is."
        )
    return " ".join(parts)

SYSTEM_CONTEXT = _build_system_context()


# ── Mission-alignment detection ───────────────────────────────────────────────
# Domains and their keyword signals are loaded from config/mission_domains.yaml.
# This does NOT disclose any personal disability or family information.

_MISSION_DOMAINS_PATH = Path(__file__).parent.parent / "config" / "mission_domains.yaml"


def load_mission_domains(path: Path | None = None) -> dict[str, dict]:
    """Load mission domain config from YAML. Returns dict keyed by domain name."""
    p = path or _MISSION_DOMAINS_PATH
    if not p.exists():
        return {}
    with p.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return data.get("domains", {}) if data else {}


_MISSION_DOMAINS: dict[str, dict] = load_mission_domains()
_MISSION_SIGNALS: dict[str, list[str]] = {
    domain: cfg.get("signals", []) for domain, cfg in _MISSION_DOMAINS.items()
}


def _build_mission_notes(profile=None, candidate_name: str | None = None) -> dict[str, str]:
    """Merge user's custom mission notes with YAML defaults.

    For domains defined in mission_domains.yaml the default_note is used when
    the user has not provided a custom note in user.yaml mission_preferences.

    For user-defined domains (keys in mission_preferences that are NOT in the
    YAML config), the custom note is used as-is; no signal detection applies.
    """
    p = profile or _profile
    name = candidate_name or (p.name if p else "the candidate")
    prefs = p.mission_preferences if p else {}
    notes: dict[str, str] = {}

    for domain, cfg in _MISSION_DOMAINS.items():
        default_note = (cfg.get("default_note") or "").strip()
        custom = (prefs.get(domain) or "").strip()
        if custom:
            notes[domain] = (
                f"Mission alignment — {name} shared: \"{custom}\". "
                "Para 3 should warmly and specifically reflect this authentic connection."
            )
        else:
            notes[domain] = default_note

    return notes


_MISSION_NOTES = _build_mission_notes()


def detect_mission_alignment(
    company: str, description: str, mission_notes: dict | None = None
) -> str | None:
    """Return a mission hint string if company/JD matches a configured domain, else None.

    Checks domains in YAML file order (dict order = match priority).
    """
    notes = mission_notes if mission_notes is not None else _MISSION_NOTES
    text = f"{company} {description}".lower()
    for domain, signals in _MISSION_SIGNALS.items():
        if any(sig in text for sig in signals):
            return notes.get(domain)
    return None


def load_corpus() -> list[dict]:
    """Load all .md cover letters from LETTERS_DIR. Returns list of {path, company, text}."""
    corpus = []
    for path in sorted(LETTERS_DIR.glob(LETTER_GLOB)):
        text = path.read_text(encoding="utf-8", errors="ignore").strip()
        if not text:
            continue
        # Extract company from filename: "Tailscale Cover Letter.md" → "Tailscale"
        company = re.sub(r"\s*Cover Letter.*", "", path.stem, flags=re.IGNORECASE).strip()
        corpus.append({"path": path, "company": company, "text": text})
    return corpus


def find_similar_letters(job_description: str, corpus: list[dict], top_k: int = 3) -> list[dict]:
    """Return the top_k letters most similar to the job description by TF-IDF cosine sim."""
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity

    if not corpus:
        return []

    docs = [job_description] + [c["text"] for c in corpus]
    vectorizer = TfidfVectorizer(stop_words="english", max_features=500)
    tfidf = vectorizer.fit_transform(docs)
    sims = cosine_similarity(tfidf[0:1], tfidf[1:])[0]

    ranked = sorted(zip(sims, corpus), key=lambda x: x[0], reverse=True)
    return [entry for _, entry in ranked[:top_k]]


def build_prompt(
    title: str,
    company: str,
    description: str,
    examples: list[dict],
    mission_hint: str | None = None,
    is_jobgether: bool = False,
    system_context: str | None = None,
    candidate_name: str | None = None,
) -> str:
    ctx = system_context if system_context is not None else SYSTEM_CONTEXT
    name = candidate_name or _candidate
    parts = [ctx.strip(), ""]
    if examples:
        parts.append(f"=== STYLE EXAMPLES ({name}'s past letters) ===\n")
        for i, ex in enumerate(examples, 1):
            parts.append(f"--- Example {i} ({ex['company']}) ---")
            parts.append(ex["text"])
            parts.append("")
        parts.append("=== END EXAMPLES ===\n")

    if mission_hint:
        parts.append(f"⭐ Mission alignment note (for Para 3): {mission_hint}\n")

    if is_jobgether:
        if company and company.lower() != "jobgether":
            recruiter_note = (
                f"🤝 Recruiter context: This listing is posted by Jobgether on behalf of "
                f"{company}. Address the cover letter to the Jobgether recruiter, not directly "
                f"to the hiring company. Use framing like 'Your client at {company} will "
                f"appreciate...' rather than addressing {company} directly. The role "
                f"requirements are those of the actual employer."
            )
        else:
            recruiter_note = (
                "🤝 Recruiter context: This listing is posted by Jobgether on behalf of an "
                "undisclosed employer. Address the cover letter to the Jobgether recruiter. "
                "Use framing like 'Your client will appreciate...' rather than addressing "
                "the company directly."
            )
        parts.append(f"{recruiter_note}\n")

    parts.append(f"Now write a new cover letter for:")
    parts.append(f"  Role: {title}")
    parts.append(f"  Company: {company}")
    if description:
        snippet = description[:1500].strip()
        parts.append(f"\nJob description excerpt:\n{snippet}")
    parts.append("\nWrite the full cover letter now:")
    return "\n".join(parts)


def _trim_to_letter_end(text: str, profile=None) -> str:
    """Remove repetitive hallucinated content after the first complete sign-off.

    Fine-tuned models sometimes loop after completing the letter. This cuts at
    the first closing + candidate name so only the intended letter is saved.
    """
    p = profile or _profile
    candidate_first = (p.name.split()[0] if p else "").strip()
    pattern = (
        r'(?:Warm regards|Sincerely|Best regards|Kind regards|Thank you)[,.]?\s*\n+\s*'
        + (re.escape(candidate_first) if candidate_first else r'\w+(?:\s+\w+)?')
        + r'\b'
    )
    m = re.search(pattern, text, re.IGNORECASE)
    if m:
        return text[:m.end()].strip()
    return text.strip()


def generate(
    title: str,
    company: str,
    description: str = "",
    previous_result: str = "",
    feedback: str = "",
    is_jobgether: bool = False,
    _router=None,
    config_path: "Path | None" = None,
    user_yaml_path: "Path | None" = None,
) -> str:
    """Generate a cover letter and return it as a string.

    Pass previous_result + feedback for iterative refinement — the prior draft
    and requested changes are appended to the prompt so the LLM revises rather
    than starting from scratch.

    user_yaml_path overrides the module-level profile — required in cloud mode
    so each user's name/voice/mission prefs are used instead of the global default.

    _router is an optional pre-built LLMRouter (used in tests to avoid real LLM calls).
    """
    # Per-call profile override (cloud mode: each user has their own user.yaml)
    if user_yaml_path and Path(user_yaml_path).exists():
        _prof = UserProfile(Path(user_yaml_path))
    else:
        _prof = _profile

    sys_ctx = _build_system_context(_prof)
    mission_notes = _build_mission_notes(_prof, candidate_name=(_prof.name if _prof else None))
    candidate_name = _prof.name if _prof else _candidate

    corpus = load_corpus()
    examples = find_similar_letters(description or f"{title} {company}", corpus)
    mission_hint = detect_mission_alignment(company, description, mission_notes=mission_notes)
    if mission_hint:
        print(f"[cover-letter] Mission alignment detected for {company}", file=sys.stderr)
    prompt = build_prompt(title, company, description, examples,
                          mission_hint=mission_hint, is_jobgether=is_jobgether,
                          system_context=sys_ctx, candidate_name=candidate_name)

    if previous_result:
        prompt += f"\n\n---\nPrevious draft:\n{previous_result}"
    if feedback:
        prompt += f"\n\nUser feedback / requested changes:\n{feedback}\n\nPlease revise accordingly."

    if _router is None:
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from scripts.llm_router import LLMRouter, CONFIG_PATH
        resolved = config_path if (config_path and Path(config_path).exists()) else CONFIG_PATH
        _router = LLMRouter(resolved)

    print(f"[cover-letter] Generating for: {title} @ {company}", file=sys.stderr)
    print(f"[cover-letter] Style examples: {[e['company'] for e in examples]}", file=sys.stderr)
    if feedback:
        print("[cover-letter] Refinement mode: feedback provided", file=sys.stderr)

    # max_tokens=1200 caps generation at ~900 words — enough for any cover letter
    # and prevents fine-tuned models from looping into repetitive garbage output.
    result = _router.complete(prompt, max_tokens=1200)
    return _trim_to_letter_end(result, _prof)


def main() -> None:
    parser = argparse.ArgumentParser(description=f"Generate a cover letter in {_candidate}'s voice")
    parser.add_argument("--title", help="Job title")
    parser.add_argument("--company", help="Company name")
    parser.add_argument("--description", default="", help="Job description text")
    parser.add_argument("--job-id", type=int, help="Load job from staging.db by ID")
    parser.add_argument("--output", help="Write output to this file path")
    args = parser.parse_args()

    title, company, description = args.title, args.company, args.description

    if args.job_id is not None:
        from scripts.db import DEFAULT_DB
        import sqlite3
        conn = sqlite3.connect(DEFAULT_DB)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (args.job_id,)).fetchone()
        conn.close()
        if not row:
            print(f"No job with id={args.job_id} in staging.db", file=sys.stderr)
            sys.exit(1)
        job = dict(row)
        title = title or job.get("title", "")
        company = company or job.get("company", "")
        description = description or job.get("description", "")

    if not title or not company:
        parser.error("--title and --company are required (or use --job-id)")

    letter = generate(title, company, description)

    if args.output:
        Path(args.output).write_text(letter)
        print(f"Saved to {args.output}", file=sys.stderr)
    else:
        print(letter)


if __name__ == "__main__":
    main()
