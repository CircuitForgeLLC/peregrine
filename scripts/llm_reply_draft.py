# BSL 1.1 — see LICENSE-BSL
"""LLM-assisted reply draft generation for inbound job contacts (BSL 1.1)."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

_SYSTEM = (
    "You are drafting a professional email reply on behalf of a job seeker. "
    "Be concise and professional. Do not fabricate facts. If you are uncertain "
    "about a detail, leave a [TODO: fill in] placeholder. "
    "Output the reply body only — no subject line, no salutation preamble."
)


def _build_prompt(subject: str, from_addr: str, body: str, user_name: str, target_role: str) -> str:
    return (
        f"ORIGINAL EMAIL:\n"
        f"Subject: {subject}\n"
        f"From: {from_addr}\n"
        f"Body:\n{body}\n\n"
        f"USER PROFILE CONTEXT:\n"
        f"Name: {user_name}\n"
        f"Target role: {target_role}\n\n"
        "Write a concise, professional reply to this email."
    )


def generate_draft_reply(
    subject: str,
    from_addr: str,
    body: str,
    user_name: str,
    target_role: str,
    config_path: Optional[Path] = None,
) -> str:
    """Return a draft reply body string."""
    from scripts.llm_router import LLMRouter

    router = LLMRouter(config_path=config_path)
    prompt = _build_prompt(subject, from_addr, body, user_name, target_role)
    return router.complete(system=_SYSTEM, user=prompt).strip()
