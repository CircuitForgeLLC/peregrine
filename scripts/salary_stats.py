"""Salary/market snapshot computed from the user's own scraped job listings.

Honesty constraint (see plan doc): Peregrine is self-hosted, single-tenant.
This module only ever describes the salary spread within a user's own
`jobs` table results — never a broader labor-market percentile claim. Do
not add confidence scores, peer-percentile framing, or experience-level
segmentation here.
"""
from __future__ import annotations

import sqlite3
import statistics

from scripts.job_ranker import _parse_salary_range


def get_salary_stats(
    db: sqlite3.Connection,
    titles: list[str],
    location: str | None = None,
) -> dict:
    """Compute salary range stats from jobs matching title/location filters.

    `titles` is a list of case-insensitive substrings matched against
    `jobs.title` (OR'd together); an empty list matches all jobs. When
    `location` is a non-empty string, results are additionally filtered by
    a case-insensitive substring match against `jobs.location`.

    Returns a dict:
        {
            "count": int,              # total jobs matched, salary or not
            "count_with_salary": int,  # subset with a parseable salary
            "median": int | None,
            "p25": int | None,
            "p75": int | None,
        }
    `median`/`p25`/`p75` are `None` when `count_with_salary == 0`.
    """
    # Base filter clauses (title/location only) — used for `count`, which
    # includes jobs regardless of whether they have a parseable salary.
    base_clauses: list[str] = []
    params: list[str] = []

    title_clauses = [t for t in titles if t]
    if title_clauses:
        title_sql = " OR ".join(["LOWER(title) LIKE '%' || LOWER(?) || '%'"] * len(title_clauses))
        base_clauses.append(f"({title_sql})")
        params.extend(title_clauses)

    if location:
        base_clauses.append("LOWER(location) LIKE '%' || LOWER(?) || '%'")
        params.append(location)

    base_where = f" WHERE {' AND '.join(base_clauses)}" if base_clauses else ""
    count = db.execute(f"SELECT COUNT(*) FROM jobs{base_where}", params).fetchone()[0]

    # Salary-present filter clauses — used for count_with_salary/percentiles.
    salary_clauses = ["salary IS NOT NULL", "salary != ''"] + base_clauses
    query = f"SELECT salary FROM jobs WHERE {' AND '.join(salary_clauses)}"
    rows = db.execute(query, params).fetchall()

    midpoints: list[int] = []
    for row in rows:
        salary_text = row["salary"] if isinstance(row, sqlite3.Row) else row[0]
        low, high = _parse_salary_range(salary_text)
        if low is None or high is None:
            continue
        midpoints.append(round((low + high) / 2))

    count_with_salary = len(midpoints)

    if count_with_salary == 0:
        return {
            "count": count,
            "count_with_salary": 0,
            "median": None,
            "p25": None,
            "p75": None,
        }

    sorted_mids = sorted(midpoints)
    median = round(statistics.median(sorted_mids))
    p25 = round(_percentile(sorted_mids, 25))
    p75 = round(_percentile(sorted_mids, 75))

    return {
        "count": count,
        "count_with_salary": count_with_salary,
        "median": median,
        "p25": p25,
        "p75": p75,
    }


def _percentile(sorted_values: list[int], pct: float) -> float:
    """Linear-interpolation percentile over an already-sorted list.

    Standard "nearest-rank via interpolation" method (same approach as
    numpy's default 'linear' interpolation), reimplemented here in plain
    Python per this module's no-numpy/pandas constraint.
    """
    n = len(sorted_values)
    if n == 1:
        return float(sorted_values[0])
    rank = (pct / 100) * (n - 1)
    lower_idx = int(rank)
    upper_idx = min(lower_idx + 1, n - 1)
    frac = rank - lower_idx
    return sorted_values[lower_idx] + frac * (sorted_values[upper_idx] - sorted_values[lower_idx])
