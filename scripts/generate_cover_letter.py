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

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.user_profile import UserProfile
_USER_YAML = Path(__file__).parent.parent / "config" / "user.yaml"
_profile = UserProfile(_USER_YAML) if UserProfile.exists(_USER_YAML) else None

LETTERS_DIR = _profile.docs_dir if _profile else Path.home() / "Documents" / "JobSearch"
LETTER_GLOB = "*Cover Letter*.md"

# Background injected into every prompt so the model has the candidate's facts
def _build_system_context() -> str:
    if not _profile:
        return "You are a professional cover letter writer. Write in first person."
    parts = [f"You are writing cover letters for {_profile.name}. {_profile.career_summary}"]
    if _profile.candidate_voice:
        parts.append(
            f"Voice and personality: {_profile.candidate_voice} "
            "Write in a way that reflects these authentic traits — not as a checklist, "
            "but as a natural expression of who this person is."
        )
    return " ".join(parts)

SYSTEM_CONTEXT = _build_system_context()


# ── Mission-alignment detection ───────────────────────────────────────────────
# When a company/JD signals one of these preferred industries, the cover letter
# prompt injects a hint so Para 3 can reflect genuine personal connection.
# This does NOT disclose any personal disability or family information.

_MISSION_SIGNALS: dict[str, list[str]] = {
    "music": [
        "music", "spotify", "tidal", "soundcloud", "bandcamp", "apple music",
        "distrokid", "cd baby", "landr", "beatport", "reverb", "vinyl",
        "streaming", "artist", "label", "live nation", "ticketmaster", "aeg",
        "songkick", "concert", "venue", "festival", "audio", "podcast",
        "studio", "record", "musician", "playlist",
    ],
    "animal_welfare": [
        "animal", "shelter", "rescue", "humane society", "spca", "aspca",
        "veterinary", "vet ", "wildlife", "pet ", "adoption", "foster",
        "dog", "cat", "feline", "canine", "sanctuary", "zoo",
    ],
    "education": [
        "education", "school", "learning", "student", "edtech", "classroom",
        "curriculum", "tutoring", "academic", "university", "kids", "children",
        "youth", "literacy", "khan academy", "duolingo", "chegg", "coursera",
        "instructure", "canvas lms", "clever", "district", "teacher",
        "k-12", "k12", "grade", "pedagogy",
    ],
    "social_impact": [
        "nonprofit", "non-profit", "501(c)", "social impact", "mission-driven",
        "public benefit", "community", "underserved", "equity", "justice",
        "humanitarian", "advocacy", "charity", "foundation", "ngo",
        "social good", "civic", "public health", "mental health", "food security",
        "housing", "homelessness", "poverty", "workforce development",
    ],
    # Health is listed last — it's a genuine but lower-priority connection than
    # music/animals/education/social_impact. detect_mission_alignment returns on first
    # match, so dict order = preference order.
    "health": [
        "patient", "patients", "healthcare", "health tech", "healthtech",
        "pharma", "pharmaceutical", "clinical", "medical",
        "hospital", "clinic", "therapy", "therapist",
        "rare disease", "life sciences", "life science",
        "treatment", "prescription", "biotech", "biopharma", "medtech",
        "behavioral health", "population health",
        "care management", "care coordination", "oncology", "specialty pharmacy",
        "provider network", "payer", "health plan", "benefits administration",
        "ehr", "emr", "fhir", "hipaa",
    ],
}

_candidate = _profile.name if _profile else "the candidate"

_MISSION_DEFAULTS: dict[str, str] = {
    "music": (
        f"This company is in the music industry — an industry {_candidate} finds genuinely "
        "compelling. Para 3 should warmly and specifically reflect this authentic alignment, "
        "not as a generic fan statement, but as an honest statement of where they'd love to "
        "apply their skills."
    ),
    "animal_welfare": (
        f"This organization works in animal welfare/rescue — a mission {_candidate} finds "
        "genuinely meaningful. Para 3 should reflect this authentic connection warmly and "
        "specifically, tying their skills to this mission."
    ),
    "education": (
        f"This company works in education or EdTech — a domain that resonates with "
        f"{_candidate}'s values. Para 3 should reflect this authentic connection specifically "
        "and warmly."
    ),
    "social_impact": (
        f"This organization is mission-driven / social impact focused — exactly the kind of "
        f"cause {_candidate} cares deeply about. Para 3 should warmly reflect their genuine "
        "desire to apply their skills to work that makes a real difference in people's lives."
    ),
    "health": (
        f"This company works in healthcare, life sciences, or patient care. "
        f"Do NOT write about {_candidate}'s passion for pharmaceuticals or healthcare as an "
        "industry. Instead, Para 3 should reflect genuine care for the PEOPLE these companies "
        "exist to serve — those navigating complex, often invisible, or unusual health journeys; "
        "patients facing rare or poorly understood conditions; individuals whose situations don't "
        "fit a clean category. The connection is to the humans behind the data, not the industry. "
        "If the user has provided a personal note, use that to anchor Para 3 specifically."
    ),
}


def _build_mission_notes() -> dict[str, str]:
    """Merge user's custom mission notes with generic defaults."""
    prefs = _profile.mission_preferences if _profile else {}
    notes = {}
    for industry, default_note in _MISSION_DEFAULTS.items():
        custom = (prefs.get(industry) or "").strip()
        if custom:
            notes[industry] = (
                f"Mission alignment — {_candidate} shared: \"{custom}\". "
                "Para 3 should warmly and specifically reflect this authentic connection."
            )
        else:
            notes[industry] = default_note
    return notes


_MISSION_NOTES = _build_mission_notes()


def detect_mission_alignment(company: str, description: str) -> str | None:
    """Return a mission hint string if company/JD matches a preferred industry, else None."""
    text = f"{company} {description}".lower()
    for industry, signals in _MISSION_SIGNALS.items():
        if any(sig in text for sig in signals):
            return _MISSION_NOTES[industry]
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
) -> str:
    parts = [SYSTEM_CONTEXT.strip(), ""]
    if examples:
        parts.append(f"=== STYLE EXAMPLES ({_candidate}'s past letters) ===\n")
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


def _trim_to_letter_end(text: str) -> str:
    """Remove repetitive hallucinated content after the first complete sign-off.

    Fine-tuned models sometimes loop after completing the letter. This cuts at
    the first closing + candidate name so only the intended letter is saved.
    """
    candidate_first = (_profile.name.split()[0] if _profile else "").strip()
    pattern = (
        r'(?:Warm regards|Sincerely|Best regards|Kind regards|Thank you)[,.]?\s*\n+\s*'
        + (re.escape(candidate_first) if candidate_first else r'\w+')
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
) -> str:
    """Generate a cover letter and return it as a string.

    Pass previous_result + feedback for iterative refinement — the prior draft
    and requested changes are appended to the prompt so the LLM revises rather
    than starting from scratch.

    _router is an optional pre-built LLMRouter (used in tests to avoid real LLM calls).
    """
    corpus = load_corpus()
    examples = find_similar_letters(description or f"{title} {company}", corpus)
    mission_hint = detect_mission_alignment(company, description)
    if mission_hint:
        print(f"[cover-letter] Mission alignment detected for {company}", file=sys.stderr)
    prompt = build_prompt(title, company, description, examples,
                          mission_hint=mission_hint, is_jobgether=is_jobgether)

    if previous_result:
        prompt += f"\n\n---\nPrevious draft:\n{previous_result}"
    if feedback:
        prompt += f"\n\nUser feedback / requested changes:\n{feedback}\n\nPlease revise accordingly."

    if _router is None:
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from scripts.llm_router import LLMRouter
        _router = LLMRouter()

    print(f"[cover-letter] Generating for: {title} @ {company}", file=sys.stderr)
    print(f"[cover-letter] Style examples: {[e['company'] for e in examples]}", file=sys.stderr)
    if feedback:
        print("[cover-letter] Refinement mode: feedback provided", file=sys.stderr)

    # max_tokens=1200 caps generation at ~900 words — enough for any cover letter
    # and prevents fine-tuned models from looping into repetitive garbage output.
    result = _router.complete(prompt, max_tokens=1200)
    return _trim_to_letter_end(result)


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
