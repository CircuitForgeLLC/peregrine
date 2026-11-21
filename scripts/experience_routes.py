"""
experience_routes.py — HTTP routes for experience facts and resume gap cards.

The router takes a callable that resolves the requesting user's database, so
hosted tenants are never routed to the shared staging database.
"""

import sqlite3
from collections.abc import Callable
from contextlib import closing
from dataclasses import asdict
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from scripts.experience_facts import (
    MAX_TERM_LEN,
    MAX_TEXT_LEN,
    ExperienceFact,
    add_fact,
    delete_fact,
    get_fact,
    list_facts,
    update_fact,
)
from scripts.gap_cards import apply_answers, build_cards


class FactCreate(BaseModel):
    kind: str
    requirement: str = Field(min_length=1, max_length=MAX_TERM_LEN)
    text: str = Field(default="", max_length=MAX_TEXT_LEN)
    visibility: str = "document"
    source: str = "manual"
    origin_job_id: int | None = None


class FactPatch(BaseModel):
    text: str | None = Field(default=None, max_length=MAX_TEXT_LEN)
    visibility: str | None = None
    status: str | None = None


class CardsRequest(BaseModel):
    terms: list[str] = Field(max_length=100)


class AnswerItem(BaseModel):
    term: str = Field(min_length=1, max_length=MAX_TERM_LEN)
    choice: Literal["yes", "similar", "no", "skip"]
    text: str = Field(default="", max_length=MAX_TEXT_LEN)
    private: bool = False
    use_saved_fact_id: int | None = None


class AnswersRequest(BaseModel):
    answers: list[AnswerItem] = Field(max_length=100)


def _fact_json(fact: ExperienceFact) -> dict:
    return asdict(fact)


def build_router(get_db_path: Callable[[], Path]) -> APIRouter:
    router = APIRouter()

    @router.get("/api/experience-facts")
    def list_experience_facts(status: str | None = "active", kind: str | None = None):
        if status == "all":
            status = None
        return [_fact_json(f) for f in list_facts(get_db_path(), status=status, kind=kind)]

    @router.post("/api/experience-facts")
    def create_experience_fact(body: FactCreate):
        db = get_db_path()
        try:
            fact_id = add_fact(db, **body.model_dump())
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return _fact_json(get_fact(db, fact_id))

    @router.patch("/api/experience-facts/{fact_id}")
    def patch_experience_fact(fact_id: int, body: FactPatch):
        db = get_db_path()
        try:
            found = update_fact(db, fact_id, **body.model_dump())
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if not found:
            raise HTTPException(status_code=404, detail="Fact not found")
        return _fact_json(get_fact(db, fact_id))

    @router.delete("/api/experience-facts/{fact_id}")
    def remove_experience_fact(fact_id: int):
        if not delete_fact(get_db_path(), fact_id):
            raise HTTPException(status_code=404, detail="Fact not found")
        return {"ok": True}

    @router.post("/api/jobs/{job_id}/gap_cards")
    def gap_cards(job_id: int, body: CardsRequest):
        db = get_db_path()
        with closing(sqlite3.connect(db)) as conn:
            row = conn.execute(
                "SELECT description FROM jobs WHERE id = ?", (job_id,)
            ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Job not found")
        return {"cards": build_cards(db, row[0] or "", body.terms)}

    @router.post("/api/jobs/{job_id}/gap_cards/answers")
    def gap_card_answers(job_id: int, body: AnswersRequest):
        try:
            return apply_answers(
                get_db_path(), job_id, [a.model_dump() for a in body.answers]
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    return router
