# scripts/generate_cover_letter.py
"""
Generate a cover letter in Meghan's voice using few-shot examples from her corpus.

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

LETTERS_DIR = Path("/Library/Documents/JobSearch")
LETTER_GLOB = "*Cover Letter*.md"

# Background injected into every prompt so the model has Meghan's facts
SYSTEM_CONTEXT = """You are writing cover letters for Meghan McCann, a customer success leader.

Background:
- 6+ years in customer success, technical account management, and CS leadership
- Most recent role: led Americas Customer Success at UpGuard (cybersecurity SaaS), managing enterprise + Fortune 500 accounts, drove NPS consistently above 95
- Also founder of M3 Consulting, a CS advisory practice for SaaS startups
- Attended Texas State (2 yrs), CSU East Bay (1 yr); completed degree elsewhere
- Based in San Francisco Bay Area; open to remote/hybrid
- Pronouns: any

Voice guidelines:
- Warm, confident, and specific — never generic
- Opens with "I'm delighted/thrilled to apply for [role] at [company]."
- 3–4 focused paragraphs, ~250–350 words total
- Para 2: concrete experience (cite UpGuard and/or M3 Consulting with a specific metric)
- Para 3: genuine connection to THIS company's mission/product
- Closes with "Thank you for considering my application." + warm sign-off
- Never use: "I am writing to express my interest", "passionate about making a difference",
  "I look forward to hearing from you", or any hollow filler phrases
"""


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
}

_MISSION_NOTES: dict[str, str] = {
    "music": (
        "This company is in the music industry, which is one of Meghan's genuinely "
        "ideal work environments — she has a real personal passion for the music scene. "
        "Para 3 should warmly and specifically reflect this authentic alignment, not as "
        "a generic fan statement, but as an honest statement of where she'd love to apply "
        "her CS skills."
    ),
    "animal_welfare": (
        "This organization works in animal welfare/rescue — one of Meghan's dream-job "
        "domains and a genuine personal passion. Para 3 should reflect this authentic "
        "connection warmly and specifically, tying her CS skills to this mission."
    ),
    "education": (
        "This company works in children's education or EdTech — one of Meghan's ideal "
        "work domains, reflecting genuine personal values around learning and young people. "
        "Para 3 should reflect this authentic connection specifically and warmly."
    ),
}


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
) -> str:
    parts = [SYSTEM_CONTEXT.strip(), ""]
    if examples:
        parts.append("=== STYLE EXAMPLES (Meghan's past letters) ===\n")
        for i, ex in enumerate(examples, 1):
            parts.append(f"--- Example {i} ({ex['company']}) ---")
            parts.append(ex["text"])
            parts.append("")
        parts.append("=== END EXAMPLES ===\n")

    if mission_hint:
        parts.append(f"⭐ Mission alignment note (for Para 3): {mission_hint}\n")

    parts.append(f"Now write a new cover letter for:")
    parts.append(f"  Role: {title}")
    parts.append(f"  Company: {company}")
    if description:
        snippet = description[:1500].strip()
        parts.append(f"\nJob description excerpt:\n{snippet}")
    parts.append("\nWrite the full cover letter now:")
    return "\n".join(parts)


def generate(title: str, company: str, description: str = "", _router=None) -> str:
    """Generate a cover letter and return it as a string.

    _router is an optional pre-built LLMRouter (used in tests to avoid real LLM calls).
    """
    corpus = load_corpus()
    examples = find_similar_letters(description or f"{title} {company}", corpus)
    mission_hint = detect_mission_alignment(company, description)
    if mission_hint:
        print(f"[cover-letter] Mission alignment detected for {company}", file=sys.stderr)
    prompt = build_prompt(title, company, description, examples, mission_hint=mission_hint)

    if _router is None:
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from scripts.llm_router import LLMRouter
        _router = LLMRouter()

    print(f"[cover-letter] Generating for: {title} @ {company}", file=sys.stderr)
    print(f"[cover-letter] Style examples: {[e['company'] for e in examples]}", file=sys.stderr)

    result = _router.complete(prompt)
    return result.strip()


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a cover letter in Meghan's voice")
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
