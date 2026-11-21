"""
gap_cards.py — question cards for resume gaps, and applying the user's answers.

A card shows one gap term, the job-description sentence that mentions it, and
any fact the user already saved for it. Answers are stored as the user typed
them, as facts in their own database. Nothing here calls a model.
"""

import re
from collections.abc import Sequence
from pathlib import Path

from scripts.experience_facts import (
    MAX_TERM_LEN,
    MAX_TEXT_LEN,
    add_fact,
    find_matching_fact,
    get_fact,
    is_usable_fact,
    list_facts,
    normalize_term,
    update_fact,
)

SNIPPET_MAX_LEN = 240
_CHOICES = ("yes", "similar", "no", "skip")
_KIND_FOR_CHOICE = {"yes": "experience", "similar": "adjacent", "no": "none"}
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")


def jd_snippet(description: str, term: str) -> str:
    """First sentence containing the term as a whole word, trimmed, or ''."""
    if not description or not term or not term.strip():
        return ""
    pattern = re.compile(rf"(?<!\w){re.escape(term.strip())}(?!\w)", re.IGNORECASE)
    for sentence in _SENTENCE_SPLIT.split(description):
        if pattern.search(sentence):
            return sentence.strip()[:SNIPPET_MAX_LEN]
    return ""


def build_cards(db_path: Path, description: str, terms: Sequence[str]) -> list[dict]:
    cards: list[dict] = []
    for term in terms:
        fact = find_matching_fact(db_path, term)
        suggestion = (
            {
                "id": fact.id,
                "kind": fact.kind,
                "text": fact.text,
                "visibility": fact.visibility,
            }
            if fact
            else None
        )
        cards.append(
            {"term": term, "snippet": jd_snippet(description, term), "suggestion": suggestion}
        )
    return cards


def _validate(db_path: Path, answer: dict) -> None:
    """Raise ValueError for any answer that must not be saved."""
    term = answer.get("term")
    if not isinstance(term, str) or not term.strip():
        raise ValueError("term must not be empty")
    if len(term) > MAX_TERM_LEN:
        raise ValueError(f"term must be at most {MAX_TERM_LEN} characters")
    choice = answer.get("choice")
    if choice not in _CHOICES:
        raise ValueError(f"choice must be one of {', '.join(_CHOICES)}")
    text = answer.get("text") or ""
    if len(text) > MAX_TEXT_LEN:
        raise ValueError(f"text must be at most {MAX_TEXT_LEN} characters")
    saved_id = answer.get("use_saved_fact_id")
    if saved_id is not None and choice in ("yes", "similar"):
        fact = get_fact(db_path, saved_id)
        if fact is None:
            raise ValueError(f"saved fact {saved_id} does not exist")
        if not is_usable_fact(fact):
            raise ValueError(f"saved fact {saved_id} can no longer be used")
        return
    if choice in ("yes", "similar") and not text.strip():
        raise ValueError(f"Please describe your experience with {term.strip()}")


def apply_answers(db_path: Path, job_id: int, answers: Sequence[dict]) -> dict:
    """Save the answers and return the terms the user approved for this job.

    Every answer is checked before anything is written, so a bad answer
    saves nothing from the batch.
    """
    for answer in answers:
        _validate(db_path, answer)

    approved: list[str] = []
    saved = 0
    for answer in answers:
        term = answer["term"]
        choice = answer["choice"]
        if choice == "skip":
            continue
        if answer.get("use_saved_fact_id") is not None and choice in ("yes", "similar"):
            approved.append(term)
            continue
        norm = normalize_term(term)
        for old in list_facts(db_path, status="active"):
            if normalize_term(old.requirement) == norm:
                update_fact(db_path, old.id, status="retired")
        private = bool(answer.get("private"))
        add_fact(
            db_path,
            kind=_KIND_FOR_CHOICE[choice],
            requirement=term.strip(),
            text="" if choice == "no" else answer.get("text") or "",
            visibility="private" if private else "document",
            source="card",
            origin_job_id=job_id,
        )
        saved += 1
        if choice in ("yes", "similar") and not private:
            approved.append(term)
    return {"approved_terms": approved, "saved": saved}
