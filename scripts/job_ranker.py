"""Job ranking engine — two-stage discovery → review pipeline.

Stage 1 (discover.py) scrapes a wide corpus and stores everything as 'pending'.
Stage 2 (this module) scores the corpus; GET /api/jobs/stack returns top-N best
matches for the user's current review session.

All signal functions return a float in [0, 1]. The final stack_score is 0–100.

Usage:
    from scripts.job_ranker import rank_jobs
    ranked = rank_jobs(jobs, search_titles, salary_min, salary_max, user_level)
"""
from __future__ import annotations

import math
import re
from datetime import datetime, timezone


# ── TUNING ─────────────────────────────────────────────────────────────────────
# Adjust these constants to change how jobs are ranked.
# All individual signal scores are normalised to [0, 1] before weighting.
# Weights should sum to ≤ 1.0; the remainder is unallocated slack.

W_RESUME_MATCH  = 0.40   # TF-IDF cosine similarity stored as match_score (0–100 → 0–1)
W_TITLE_MATCH   = 0.30   # seniority-aware title + domain keyword overlap
W_RECENCY       = 0.15   # freshness — exponential decay from date_found
W_SALARY_FIT    = 0.10   # salary range overlap vs user target (neutral when unknown)
W_DESC_QUALITY  = 0.05   # posting completeness — penalises stub / ghost posts

# Keyword gap penalty: each missing keyword from the resume match costs points.
# Gaps are already partially captured by W_RESUME_MATCH (same TF-IDF source),
# so this is a soft nudge, not a hard filter.
GAP_PENALTY_PER_KEYWORD: float = 0.5   # points off per gap keyword (0–100 scale)
GAP_MAX_PENALTY:         float = 5.0   # hard cap so a gap-heavy job can still rank

# Recency half-life: score halves every N days past date_found
RECENCY_HALF_LIFE: int = 7  # days

# Description word-count thresholds
DESC_MIN_WORDS:    int = 50    # below this → scaled penalty
DESC_TARGET_WORDS: int = 200   # at or above → full quality score
# ── END TUNING ─────────────────────────────────────────────────────────────────


# ── Seniority level map ────────────────────────────────────────────────────────
# (level, [keyword substrings that identify that level])
# Matched on " <lower_title> " with a space-padded check to avoid false hits.
# Level 3 is the default (mid-level, no seniority modifier in title).
_SENIORITY_MAP: list[tuple[int, list[str]]] = [
    (1, ["intern", "internship", "trainee", "apprentice", "co-op", "coop"]),
    (2, ["entry level", "entry-level", "junior", "jr ", "jr.", "associate "]),
    (3, ["mid level", "mid-level", "intermediate"]),
    (4, ["senior ", "senior,", "sr ", "sr.", " lead ", "lead,", " ii ", " iii ",
          "specialist", "experienced"]),
    (5, ["staff ", "principal ", "architect ", "expert ", "distinguished"]),
    (6, ["director", "head of ", "manager ", "vice president", " vp "]),
    (7, ["chief", "cto", "cio", "cpo", "president", "founder"]),
]

# job_level − user_level → scoring multiplier
# Positive delta = job is more senior (stretch up = encouraged)
# Negative delta = job is below the user's level
_LEVEL_MULTIPLIER: dict[int, float] = {
    -4: 0.05, -3: 0.10, -2: 0.25, -1: 0.65,
     0: 1.00,
     1: 0.90,  2: 0.65,  3: 0.25,  4: 0.05,
}
_DEFAULT_LEVEL_MULTIPLIER = 0.05


# ── Seniority helpers ─────────────────────────────────────────────────────────

def infer_seniority(title: str) -> int:
    """Return seniority level 1–7 for a job or resume title. Defaults to 3."""
    padded = f" {title.lower()} "
    # Iterate highest → lowest so "Senior Lead" resolves to 4, not 6
    for level, keywords in reversed(_SENIORITY_MAP):
        for kw in keywords:
            if kw in padded:
                return level
    return 3


def seniority_from_experience(titles: list[str]) -> int:
    """Estimate user's current level from their most recent experience titles.

    Averages the levels of the top-3 most recent titles (first in the list).
    Falls back to 3 (mid-level) if no titles are provided.
    """
    if not titles:
        return 3
    sample = [t for t in titles if t.strip()][:3]
    if not sample:
        return 3
    levels = [infer_seniority(t) for t in sample]
    return round(sum(levels) / len(levels))


def _strip_level_words(text: str) -> str:
    """Remove seniority/modifier words so domain keywords stand out."""
    strip = {
        "senior", "sr", "junior", "jr", "lead", "staff", "principal",
        "associate", "entry", "mid", "intermediate", "experienced",
        "director", "head", "manager", "architect", "chief", "intern",
        "ii", "iii", "iv", "i",
    }
    return " ".join(w for w in text.lower().split() if w not in strip)


# ── Signal functions ──────────────────────────────────────────────────────────

def title_match_score(job_title: str, search_titles: list[str], user_level: int) -> float:
    """Seniority-aware title similarity in [0, 1].

    Combines:
    - Domain overlap: keyword intersection between job title and search titles
      after stripping level modifiers (so "Senior Software Engineer" vs
      "Software Engineer" compares only on "software engineer").
    - Seniority multiplier: rewards same-level and +1 stretch; penalises
      large downgrade or unreachable stretch.
    """
    if not search_titles:
        return 0.5  # neutral — user hasn't set title prefs yet

    job_level = infer_seniority(job_title)
    level_delta = job_level - user_level
    seniority_factor = _LEVEL_MULTIPLIER.get(level_delta, _DEFAULT_LEVEL_MULTIPLIER)

    job_core_words = {w for w in _strip_level_words(job_title).split() if len(w) > 2}

    best_domain = 0.0
    for st in search_titles:
        st_core_words = {w for w in _strip_level_words(st).split() if len(w) > 2}
        if not st_core_words:
            continue
        # Recall-biased overlap: what fraction of the search title keywords
        # appear in the job title? (A job posting may use synonyms but we
        # at least want the core nouns to match.)
        overlap = len(st_core_words & job_core_words) / len(st_core_words)
        best_domain = max(best_domain, overlap)

    # Base score from domain match scaled by seniority appropriateness.
    # A small seniority_factor bonus (×0.2) ensures that even a near-miss
    # domain match still benefits from seniority alignment.
    return min(1.0, best_domain * seniority_factor + seniority_factor * 0.15)


def recency_decay(date_found: str) -> float:
    """Exponential decay starting from date_found.

    Returns 1.0 for today, 0.5 after RECENCY_HALF_LIFE days, ~0.0 after ~4×.
    Returns 0.5 (neutral) if the date is unparseable.
    """
    try:
        # Support both "YYYY-MM-DD" and "YYYY-MM-DD HH:MM:SS"
        found = datetime.fromisoformat(date_found.split("T")[0].split(" ")[0])
        found = found.replace(tzinfo=timezone.utc)
        now = datetime.now(tz=timezone.utc)
        days_old = max(0.0, (now - found).total_seconds() / 86400)
        return math.exp(-math.log(2) * days_old / RECENCY_HALF_LIFE)
    except Exception:
        return 0.5


def _parse_salary_range(text: str | None) -> tuple[int | None, int | None]:
    """Extract (low, high) salary integers from free-text. Returns (None, None) on failure.

    Handles: "$80k - $120k", "USD 80,000 - 120,000 per year", "£45,000",
             "80000", "80K/yr", "80-120k", etc.
    """
    if not text:
        return None, None
    normalized = re.sub(r"[$,£€₹¥\s]", "", text.lower())
    # Match numbers optionally followed by 'k'
    raw_nums = re.findall(r"(\d+(?:\.\d+)?)k?", normalized)
    values = []
    for n, full in zip(raw_nums, re.finditer(r"(\d+(?:\.\d+)?)(k?)", normalized)):
        val = float(full.group(1))
        if full.group(2):   # ends with 'k'
            val *= 1000
        elif val < 1000:    # bare numbers < 1000 are likely thousands (e.g., "80" in "80-120k")
            val *= 1000
        if val >= 10_000:   # sanity: ignore clearly wrong values
            values.append(int(val))
    values = sorted(set(values))
    if not values:
        return None, None
    return values[0], values[-1]


def salary_fit(
    salary_text: str | None,
    target_min: int | None,
    target_max: int | None,
) -> float:
    """Salary range overlap score in [0, 1].

    Returns 0.5 (neutral) when either range is unknown — a missing salary
    line is not inherently negative.
    """
    if not salary_text or (target_min is None and target_max is None):
        return 0.5

    job_low, job_high = _parse_salary_range(salary_text)
    if job_low is None:
        return 0.5

    t_min = target_min or 0
    t_max = target_max or (int(target_min * 1.5) if target_min else job_high or job_low)
    job_high = job_high or job_low

    overlap_low  = max(job_low, t_min)
    overlap_high = min(job_high, t_max)
    overlap = max(0, overlap_high - overlap_low)
    target_span = max(1, t_max - t_min)
    return min(1.0, overlap / target_span)


def description_quality(description: str | None) -> float:
    """Posting completeness score in [0, 1].

    Stubs and ghost posts score near 0; well-written descriptions score 1.0.
    """
    if not description:
        return 0.0
    words = len(description.split())
    if words < DESC_MIN_WORDS:
        return (words / DESC_MIN_WORDS) * 0.4  # steep penalty for stubs
    if words >= DESC_TARGET_WORDS:
        return 1.0
    return 0.4 + 0.6 * (words - DESC_MIN_WORDS) / (DESC_TARGET_WORDS - DESC_MIN_WORDS)


# ── Composite scorer ──────────────────────────────────────────────────────────

def score_job(
    job: dict,
    search_titles: list[str],
    target_salary_min: int | None,
    target_salary_max: int | None,
    user_level: int,
) -> float:
    """Compute composite stack_score (0–100) for a single job dict.

    Args:
        job:              Row dict from the jobs table (must have title, match_score,
                          date_found, salary, description, keyword_gaps).
        search_titles:    User's desired job titles (from search prefs).
        target_salary_*:  User's salary target from resume profile (or None).
        user_level:       Inferred seniority level 1–7.

    Returns:
        A float 0–100. Higher = better match for this user's session.
    """
    # ── Individual signals (all 0–1) ──────────────────────────────────────────
    match_raw = job.get("match_score")
    s_resume  = (match_raw / 100.0) if match_raw is not None else 0.5

    s_title   = title_match_score(job.get("title", ""), search_titles, user_level)
    s_recency = recency_decay(job.get("date_found", ""))
    s_salary  = salary_fit(job.get("salary"), target_salary_min, target_salary_max)
    s_desc    = description_quality(job.get("description"))

    # ── Weighted sum ──────────────────────────────────────────────────────────
    base = (
        W_RESUME_MATCH   * s_resume
        + W_TITLE_MATCH  * s_title
        + W_RECENCY      * s_recency
        + W_SALARY_FIT   * s_salary
        + W_DESC_QUALITY * s_desc
    )

    # ── Keyword gap penalty (applied on the 0–100 scale) ─────────────────────
    gaps_raw  = job.get("keyword_gaps") or ""
    gap_count = len([g for g in gaps_raw.split(",") if g.strip()]) if gaps_raw else 0
    gap_penalty = min(GAP_MAX_PENALTY, gap_count * GAP_PENALTY_PER_KEYWORD) / 100.0

    return round(max(0.0, base - gap_penalty) * 100, 1)


# ── Public API ────────────────────────────────────────────────────────────────

def rank_jobs(
    jobs: list[dict],
    search_titles: list[str],
    target_salary_min: int | None = None,
    target_salary_max: int | None = None,
    user_level: int = 3,
    limit: int = 10,
    min_score: float = 20.0,
) -> list[dict]:
    """Score and rank pending jobs; return top-N above min_score.

    Args:
        jobs:             List of job dicts (from DB or any source).
        search_titles:    User's desired job titles from search prefs.
        target_salary_*:  User's salary target (from resume profile).
        user_level:       Seniority level 1–7 (use seniority_from_experience()).
        limit:            Stack size; pass 0 to return all qualifying jobs.
        min_score:        Minimum stack_score to include (0–100).

    Returns:
        Sorted list (best first) with 'stack_score' key added to each dict.
    """
    scored = []
    for job in jobs:
        s = score_job(job, search_titles, target_salary_min, target_salary_max, user_level)
        if s >= min_score:
            scored.append({**job, "stack_score": s})

    scored.sort(key=lambda j: j["stack_score"], reverse=True)
    return scored[:limit] if limit > 0 else scored
