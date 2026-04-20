# MIT License — see LICENSE
"""Survey assistant: prompt builders and LLM inference for culture-fit survey analysis.

Extracted from dev-api.py so task_runner can import this without importing the
FastAPI application. Callable directly or via the survey_analyze background task.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

SURVEY_SYSTEM = (
    "You are a job application advisor helping a candidate answer a culture-fit survey. "
    "The candidate values collaborative teamwork, clear communication, growth, and impact. "
    "Choose answers that present them in the best professional light."
)


def build_text_prompt(text: str, mode: str) -> str:
    if mode == "quick":
        return (
            "Answer each survey question below. For each, give ONLY the letter of the best "
            "option and a single-sentence reason. Format exactly as:\n"
            "1. B — reason here\n2. A — reason here\n\n"
            f"Survey:\n{text}"
        )
    return (
        "Analyze each survey question below. For each question:\n"
        "- Briefly evaluate each option (1 sentence each)\n"
        "- State your recommendation with reasoning\n\n"
        f"Survey:\n{text}"
    )


def build_image_prompt(mode: str) -> str:
    if mode == "quick":
        return (
            "This is a screenshot of a culture-fit survey. Read all questions and answer each "
            "with the letter of the best option for a collaborative, growth-oriented candidate. "
            "Format: '1. B — brief reason' on separate lines."
        )
    return (
        "This is a screenshot of a culture-fit survey. For each question, evaluate each option "
        "and recommend the best choice for a collaborative, growth-oriented candidate. "
        "Include a brief breakdown per option and a clear recommendation."
    )


def run_survey_analyze(
    text: Optional[str],
    image_b64: Optional[str],
    mode: str,
    config_path: Optional[Path] = None,
) -> dict:
    """Run LLM inference for survey analysis.

    Returns {"output": str, "source": "text_paste" | "screenshot"}.
    Raises on LLM failure — caller is responsible for error handling.
    """
    from scripts.llm_router import LLMRouter

    router = LLMRouter(config_path=config_path) if config_path else LLMRouter()

    if image_b64:
        prompt = build_image_prompt(mode)
        output = router.complete(
            prompt,
            images=[image_b64],
            fallback_order=router.config.get("vision_fallback_order"),
        )
        source = "screenshot"
    else:
        prompt = build_text_prompt(text or "", mode)
        output = router.complete(
            prompt,
            system=SURVEY_SYSTEM,
            fallback_order=router.config.get("research_fallback_order"),
        )
        source = "text_paste"

    return {"output": output, "source": source}
