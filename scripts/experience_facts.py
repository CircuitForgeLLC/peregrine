"""
experience_facts.py — what the user tells us about each resume gap, kept as
reusable facts in their own database.

Rules this module enforces:
  * The user's wording is stored exactly as typed. Nothing here rewrites it.
  * Only active facts of kind "experience" or "adjacent" with visibility
    "document" are ever returned by usable_facts_for_prompt, so kind "none"
    and private rows can never reach a model prompt.
"""

import re
import sqlite3
from collections.abc import Sequence
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

KINDS = ("experience", "adjacent", "none")
VISIBILITIES = ("document", "private")
STATUSES = ("active", "retired")
SOURCES = ("card", "chat", "manual")

MAX_TEXT_LEN = 2000
MAX_TERM_LEN = 120
OVERLAP_THRESHOLD = 0.5

_USABLE_KINDS = ("experience", "adjacent")

_STOP_WORDS = frozenset({
    "a", "an", "and", "the", "of", "for", "to", "in", "on", "at", "with",
    "or", "by", "as", "is", "are", "be", "from", "into", "using", "use",
})
_TOKEN_RE = re.compile(r"(?<![a-z0-9])\.[a-z0-9]+[+#]*|[a-z0-9]+[+#]*")
_SUFFIXES = ("ing", "ed", "es", "s")


@dataclass(frozen=True)
class ExperienceFact:
    id: int
    kind: str
    requirement: str
    text: str
    visibility: str
    status: str
    source: str
    origin_job_id: int | None
    created_at: str
    updated_at: str


def normalize_term(term: str) -> str:
    """Lowercase, collapse whitespace, strip leading and trailing punctuation."""
    # A trailing "+" or "#" and a leading "." that is part of a name are kept,
    # so "c", "c++", "c#" and ".net" vs "net" stay distinct terms.
    result = " ".join(term.lower().split())
    result = re.sub(r"^(?:(?!\.\w)[^\w])+", "", result)
    # Trailing cleanup is a linear scan: drop punctuation, then keep a run of
    # "+" or "#" only when the character before it is a word character.
    while True:
        end = len(result)
        while end > 0 and not (result[end - 1].isalnum() or result[end - 1] in "_+#"):
            end -= 1
        trimmed = result[:end]
        core = trimmed.rstrip("+#")
        if core == trimmed or (core and (core[-1].isalnum() or core[-1] == "_")):
            return trimmed
        result = core


def _stem(token: str) -> str:
    if len(token) > 4:
        for suffix in _SUFFIXES:
            if token.endswith(suffix):
                token = token[: -len(suffix)]
                break
        token = token.removesuffix("e")
    return token


def _tokens(term: str) -> frozenset[str]:
    raw = [
        "dot" + t[1:] if t.startswith(".") else t
        for t in _TOKEN_RE.findall(term.lower())
    ]
    return frozenset(_stem(t) for t in raw if t not in _STOP_WORDS)


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _to_fact(row: sqlite3.Row) -> ExperienceFact:
    return ExperienceFact(
        id=row["id"],
        kind=row["kind"],
        requirement=row["requirement"],
        text=row["text"],
        visibility=row["visibility"],
        status=row["status"],
        source=row["source"],
        origin_job_id=row["origin_job_id"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _check_choice(name: str, value: str, allowed: Sequence[str]) -> None:
    if value not in allowed:
        raise ValueError(f"{name} must be one of {', '.join(allowed)}")


def _check_text(text: str) -> None:
    if len(text) > MAX_TEXT_LEN:
        raise ValueError(f"text must be at most {MAX_TEXT_LEN} characters")


def _validate_new_fact(
    kind: str, requirement: str, text: str, visibility: str, source: str
) -> None:
    _check_choice("kind", kind, KINDS)
    _check_choice("visibility", visibility, VISIBILITIES)
    _check_choice("source", source, SOURCES)
    if not requirement or not requirement.strip():
        raise ValueError("requirement must not be empty")
    if len(requirement) > MAX_TERM_LEN:
        raise ValueError(f"requirement must be at most {MAX_TERM_LEN} characters")
    if not normalize_term(requirement):
        raise ValueError("requirement must contain letters or numbers")
    _check_text(text)
    if kind != "none" and not text.strip():
        raise ValueError("text must not be empty")


_INSERT_SQL = (
    "INSERT INTO experience_facts "
    "(kind, requirement, text, visibility, source, origin_job_id) "
    "VALUES (?, ?, ?, ?, ?, ?)"
)


def add_fact(
    db_path: Path,
    *,
    kind: str,
    requirement: str,
    text: str = "",
    visibility: str = "document",
    source: str = "card",
    origin_job_id: int | None = None,
) -> int:
    _validate_new_fact(kind, requirement, text, visibility, source)
    with closing(_connect(db_path)) as conn:
        cur = conn.execute(
            _INSERT_SQL,
            (kind, requirement, text, visibility, source, origin_job_id),
        )
        conn.commit()
        return int(cur.lastrowid)


def replace_fact(
    db_path: Path,
    *,
    kind: str,
    requirement: str,
    text: str = "",
    visibility: str = "document",
    source: str = "card",
    origin_job_id: int | None = None,
) -> int:
    """Insert a fact and retire every other active fact with the same
    normalised requirement, in one transaction. Returns the new id."""
    _validate_new_fact(kind, requirement, text, visibility, source)
    norm = normalize_term(requirement)
    with closing(_connect(db_path)) as conn:
        try:
            cur = conn.execute(
                _INSERT_SQL,
                (kind, requirement, text, visibility, source, origin_job_id),
            )
            new_id = int(cur.lastrowid)
            rows = conn.execute(
                "SELECT id, requirement FROM experience_facts "
                "WHERE status = 'active' AND id != ?",
                (new_id,),
            ).fetchall()
            old_ids = [r["id"] for r in rows if normalize_term(r["requirement"]) == norm]
            for old_id in old_ids:
                conn.execute(
                    "UPDATE experience_facts SET status = 'retired', "
                    "updated_at = datetime('now') WHERE id = ?",
                    (old_id,),
                )
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        return new_id


def get_fact(db_path: Path, fact_id: int) -> ExperienceFact | None:
    with closing(_connect(db_path)) as conn:
        row = conn.execute(
            "SELECT * FROM experience_facts WHERE id = ?", (fact_id,)
        ).fetchone()
    return _to_fact(row) if row else None


def list_facts(
    db_path: Path,
    *,
    status: str | None = "active",
    kind: str | None = None,
) -> list[ExperienceFact]:
    clauses: list[str] = []
    params: list[str] = []
    if status is not None:
        clauses.append("status = ?")
        params.append(status)
    if kind is not None:
        clauses.append("kind = ?")
        params.append(kind)
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    with closing(_connect(db_path)) as conn:
        rows = conn.execute(
            f"SELECT * FROM experience_facts{where} ORDER BY id DESC", params
        ).fetchall()
    return [_to_fact(r) for r in rows]


def update_fact(
    db_path: Path,
    fact_id: int,
    *,
    text: str | None = None,
    visibility: str | None = None,
    status: str | None = None,
) -> bool:
    sets: list[str] = []
    params: list[str | int] = []
    existing = get_fact(db_path, fact_id)
    if existing is None:
        return False
    if text is not None:
        _check_text(text)
        if existing.kind != "none" and not text.strip():
            raise ValueError("text must not be empty")
        sets.append("text = ?")
        params.append(text)
    if visibility is not None:
        _check_choice("visibility", visibility, VISIBILITIES)
        sets.append("visibility = ?")
        params.append(visibility)
    if status is not None:
        _check_choice("status", status, STATUSES)
        sets.append("status = ?")
        params.append(status)
    sets.append("updated_at = datetime('now')")
    params.append(fact_id)
    with closing(_connect(db_path)) as conn:
        cur = conn.execute(
            f"UPDATE experience_facts SET {', '.join(sets)} WHERE id = ?", params
        )
        conn.commit()
        return cur.rowcount > 0


def delete_fact(db_path: Path, fact_id: int) -> bool:
    with closing(_connect(db_path)) as conn:
        cur = conn.execute("DELETE FROM experience_facts WHERE id = ?", (fact_id,))
        conn.commit()
        return cur.rowcount > 0


def _best_match(term: str, facts: Sequence[ExperienceFact]) -> ExperienceFact | None:
    """Exact normalized requirement first, else best token overlap (newest wins ties)."""
    norm = normalize_term(term)
    if not norm:
        return None
    ordered = sorted(facts, key=lambda f: f.id, reverse=True)
    for fact in ordered:
        if normalize_term(fact.requirement) == norm:
            return fact
    term_tokens = _tokens(term)
    best: ExperienceFact | None = None
    best_score = 0.0
    for fact in ordered:
        score = _jaccard(term_tokens, _tokens(fact.requirement))
        if score >= OVERLAP_THRESHOLD and score > best_score:
            best, best_score = fact, score
    return best


def find_matching_fact(db_path: Path, term: str) -> ExperienceFact | None:
    """Active fact of any kind that best matches the term, or None."""
    return _best_match(term, list_facts(db_path, status="active"))


def is_usable_fact(fact: ExperienceFact) -> bool:
    """True only for an active, document-visible experience or adjacent fact with text."""
    return (
        fact.status == "active"
        and fact.kind in _USABLE_KINDS
        and fact.visibility == "document"
        and bool(fact.text.strip())
    )


def usable_facts_for_prompt(
    db_path: Path, terms: Sequence[str]
) -> dict[str, ExperienceFact]:
    """Facts safe to put in a prompt, keyed by the term as passed in.

    Only active experience or adjacent facts with document visibility are
    considered, resolved with the same matching as find_matching_fact.
    """
    usable = [f for f in list_facts(db_path, status="active") if is_usable_fact(f)]
    result: dict[str, ExperienceFact] = {}
    for term in terms:
        match = _best_match(term, usable)
        if match is not None:
            result[term] = match
    return result
