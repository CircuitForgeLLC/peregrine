"""
Resume match scoring.

Two modes:
  1. SQLite batch — score all unscored pending/approved jobs in staging.db
     Usage: python scripts/match.py

  2. Notion single — score one Notion page by URL/ID and write results back
     Usage: python scripts/match.py <notion-page-url-or-id>
"""
import re
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import requests
import yaml
from bs4 import BeautifulSoup
from notion_client import Client

CONFIG_DIR = Path(__file__).parent.parent / "config"
RESUME_PATH = Path("/Library/Documents/JobSearch/Meghan_McCann_Resume_02-19-2025.pdf")


def load_notion() -> tuple[Client, dict]:
    cfg = yaml.safe_load((CONFIG_DIR / "notion.yaml").read_text())
    return Client(auth=cfg["token"]), cfg["field_map"]


def extract_page_id(url_or_id: str) -> str:
    """Extract 32-char Notion page ID from a URL or return as-is."""
    clean = url_or_id.replace("-", "")
    match = re.search(r"[0-9a-f]{32}", clean)
    return match.group(0) if match else url_or_id.strip()


def get_job_url_from_notion(notion: Client, page_id: str, url_field: str) -> str:
    page = notion.pages.retrieve(page_id)
    return page["properties"][url_field]["url"] or ""


def extract_job_description(url: str) -> str:
    """Fetch a job listing URL and return its visible text."""
    resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer"]):
        tag.decompose()
    return " ".join(soup.get_text(separator=" ").split())


def read_resume_text() -> str:
    """Extract text from the ATS-clean PDF resume."""
    import pypdf
    reader = pypdf.PdfReader(str(RESUME_PATH))
    return " ".join(page.extract_text() or "" for page in reader.pages)


def match_score(resume_text: str, job_text: str) -> tuple[float, list[str]]:
    """
    Score resume against job description using TF-IDF cosine similarity.
    Returns (score 0–100, list of high-value job keywords missing from resume).
    """
    import numpy as np
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity

    vectorizer = TfidfVectorizer(stop_words="english", max_features=200)
    tfidf = vectorizer.fit_transform([resume_text, job_text])
    score = float(cosine_similarity(tfidf[0:1], tfidf[1:2])[0][0]) * 100

    resume_terms = set(resume_text.lower().split())
    feature_names = vectorizer.get_feature_names_out()
    job_tfidf = tfidf[1].toarray()[0]
    top_indices = np.argsort(job_tfidf)[::-1][:30]
    top_job_terms = [feature_names[i] for i in top_indices if job_tfidf[i] > 0]
    gaps = [t for t in top_job_terms if t not in resume_terms and t == t][:10]  # t==t drops NaN

    return round(score, 1), gaps


def write_match_to_notion(notion: Client, page_id: str, score: float, gaps: list[str], fm: dict) -> None:
    notion.pages.update(
        page_id=page_id,
        properties={
            fm["match_score"]:   {"number": score},
            fm["keyword_gaps"]:  {"rich_text": [{"text": {"content": ", ".join(gaps)}}]},
        },
    )


def run_match(page_url_or_id: str) -> None:
    notion, fm = load_notion()
    page_id = extract_page_id(page_url_or_id)

    print(f"[match] Page ID: {page_id}")
    job_url = get_job_url_from_notion(notion, page_id, fm["url"])
    print(f"[match] Fetching job description from: {job_url}")

    job_text = extract_job_description(job_url)
    resume_text = read_resume_text()

    score, gaps = match_score(resume_text, job_text)
    print(f"[match] Score: {score}/100")
    print(f"[match] Keyword gaps: {', '.join(gaps) or 'none'}")

    write_match_to_notion(notion, page_id, score, gaps, fm)
    print("[match] Written to Notion.")


def score_pending_jobs(db_path: Path = None) -> int:
    """
    Score all unscored jobs (any status) in SQLite using the description
    already scraped during discovery. Writes match_score + keyword_gaps back.
    Returns the number of jobs scored.
    """
    from scripts.db import DEFAULT_DB, write_match_scores

    if db_path is None:
        db_path = DEFAULT_DB

    import sqlite3
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, title, company, description FROM jobs "
        "WHERE match_score IS NULL "
        "AND description IS NOT NULL AND description != '' AND description != 'nan'"
    ).fetchall()
    conn.close()

    if not rows:
        print("[match] No unscored jobs with descriptions found.")
        return 0

    resume_text = read_resume_text()
    scored = 0
    for row in rows:
        job_id, title, company, description = row["id"], row["title"], row["company"], row["description"]
        try:
            score, gaps = match_score(resume_text, description)
            write_match_scores(db_path, job_id, score, ", ".join(gaps))
            print(f"[match] {title} @ {company}: {score}/100  gaps: {', '.join(gaps) or 'none'}")
            scored += 1
        except Exception as e:
            print(f"[match] Error scoring job {job_id}: {e}")

    print(f"[match] Done — {scored} jobs scored.")
    return scored


if __name__ == "__main__":
    if len(sys.argv) < 2:
        score_pending_jobs()
    else:
        run_match(sys.argv[1])
