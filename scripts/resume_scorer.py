"""
Holistic Resume Scorer - job-agnostic resume quality + ATS hygiene scoring.

Unlike scripts/resume_optimizer.py (which rewrites a resume against ONE job
description), this module scores a resume standing alone: overall quality,
narrative feedback, and per-bullet wording suggestions with no job in the loop.

Every suggestion is checked with the existing hallucination_check() before being
marked appliable - reusing the same safety gate as the job-specific rewrite flow.

The ATS sub-score has no job description to diff against (this is explicitly
job-agnostic), so it is computed against the user's own recent saved job
history when available, and ALWAYS carries an explicit ats_basis string naming
its source - never a bare score implying a broader market benchmark.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from scripts.llm_router import LLMRouter
from scripts.resume_optimizer import hallucination_check, render_resume_text

log = logging.getLogger(__name__)


def score_resume(struct: dict[str, Any]) -> dict[str, Any]:
    """Run one LLM pass producing a holistic score, narrative feedback, and
    per-bullet wording suggestions for a resume, with no job in the loop.

    Args:
        struct: Structured resume dict (from resume_parser.parse_resume shape).

    Returns:
        {
          "overall_score": int (1-10),
          "summary": str,
          "strengths": list[str],
          "improvements": list[str],
          "suggestions": list[dict with id/section/target/before/after/
              rationale/appliable keys],
        }
        On any LLM or parse failure, returns a safe empty-ish shape with
        overall_score=None so the caller/UI can show a clear failure state
        rather than a fabricated score.
    """
    router = LLMRouter()

    resume_text = render_resume_text(struct)
    prompt = (
        "You are reviewing a resume holistically - not for any specific job, but "
        "for overall quality: clarity, impact, quantification, and professional "
        "presentation.\n\n"
        "Return ONLY valid JSON matching exactly this shape, no markdown fences, "
        "no explanation outside the JSON:\n"
        '{\n'
        '  "overall_score": <integer 1-10>,\n'
        '  "summary": "<one paragraph narrative assessment>",\n'
        '  "strengths": ["<short strength>", ...],\n'
        '  "improvements": ["<short area for improvement>", ...],\n'
        '  "suggestions": [\n'
        '    {"id": "sugg-1", "section": "summary|experience|skills", '
        '"target": "<section name, or Company|Title for an experience entry>", '
        '"before": "<exact original text>", "after": "<improved rewording>", '
        '"rationale": "<one sentence why>"}\n'
        '  ]\n'
        '}\n\n'
        "CRITICAL RULES for every suggestion's \"after\" text - violating these "
        "invalidates the suggestion:\n"
        "1. Do NOT invent new employers, job titles, dates, or education.\n"
        "2. Do NOT add skills or achievements not already present in \"before\".\n"
        "3. Only rephrase existing content - do not fabricate new facts.\n"
        "4. \"before\" must be an exact substring of the original resume text below.\n\n"
        f"Resume:\n{resume_text}"
    )

    try:
        raw = router.complete(prompt)
        parsed = _parse_llm_json(raw)
    except Exception:
        log.warning("[resume_scorer] score_resume LLM call failed", exc_info=True)
        return {
            "overall_score": None, "summary": "", "strengths": [], "improvements": [],
            "suggestions": [],
        }

    suggestions = []
    for i, sugg in enumerate(parsed.get("suggestions") or []):
        rewritten = _apply_to_copy(struct, sugg)
        # hallucination_check() only verifies company/title/dates/institution
        # anchors, not bullet-text content -- see issue #160 for the known gap.
        # This is the gate that decides whether the Apply button even appears
        # in the UI, so a false "appliable: true" here is what a user actually
        # sees and acts on.
        appliable = hallucination_check(struct, rewritten)
        suggestions.append({
            "id": sugg.get("id") or f"sugg-{i+1}",
            "section": sugg.get("section", ""),
            "target": sugg.get("target", ""),
            "before": sugg.get("before", ""),
            "after": sugg.get("after", ""),
            "rationale": sugg.get("rationale", ""),
            "appliable": appliable,
        })

    return {
        "overall_score": parsed.get("overall_score"),
        "summary": parsed.get("summary", ""),
        "strengths": parsed.get("strengths") or [],
        "improvements": parsed.get("improvements") or [],
        "suggestions": suggestions,
    }


def score_ats_hygiene(struct: dict[str, Any], recent_job_descriptions: list[str]) -> dict[str, Any]:
    """Score ATS parseability/hygiene, honestly framed by its actual data source.

    Args:
        struct: Structured resume dict.
        recent_job_descriptions: Plain-text descriptions of the user's own most
            recently saved jobs (may be empty).

    Returns:
        {"ats_score": int (1-10), "ats_basis": str, "ats_issues": list[str]}
        ats_basis is ALWAYS present and ALWAYS names its actual source -
        never a bare score implying a broader labor-market benchmark.
    """
    issues: list[str] = []
    score = 10

    # Deterministic hygiene checks (JD-independent).
    if not struct.get("email") and not struct.get("phone"):
        issues.append("No contact email or phone found - may be missing or unparseable.")
        score -= 2
    for exp in struct.get("experience", []):
        bullets = exp.get("bullets") or []
        unquantified = [b for b in bullets if not re.search(r"\d", b)]
        if bullets and len(unquantified) == len(bullets):
            issues.append(
                f"{exp.get('title', 'A role')} at {exp.get('company', 'a company')} "
                "has no quantified bullets (numbers, %, $, team size)."
            )
            score -= 1

    n = len(recent_job_descriptions)
    if n:
        ats_basis = f"based on your {n} most recently saved job{'s' if n != 1 else ''}"
        # Lightweight relevance signal: fraction of the user's own skills that
        # appear anywhere in their own recent job descriptions.
        skills = [s.lower() for s in (struct.get("skills") or [])]
        combined = " ".join(recent_job_descriptions).lower()
        if skills:
            hits = sum(1 for s in skills if s in combined)
            coverage = hits / len(skills)
            if coverage < 0.3:
                issues.append(
                    "Few of your listed skills appear in your recently saved jobs - "
                    "consider whether your skills list matches what you're applying to."
                )
                score -= 1
    else:
        ats_basis = "general ATS best practices — save some jobs to sharpen this"

    return {
        "ats_score": max(1, min(10, score)),
        "ats_basis": ats_basis,
        "ats_issues": issues,
    }


def apply_suggestion(struct: dict[str, Any], suggestion: dict[str, Any]) -> dict[str, Any]:
    """Apply one suggestion's "after" text into a copy of the resume struct.

    Args:
        struct: The resume's current structured dict.
        suggestion: One entry from score_resume()'s "suggestions" list - must
            have "section", "target", "before", "after".

    Returns:
        A new struct dict with the suggestion applied. Does NOT check
        hallucination_check() - callers must do that before persisting, using
        the pre-existing struct as `original` and this return value as
        `rewritten`.
    """
    return _apply_to_copy(struct, suggestion)


def _apply_to_copy(struct: dict[str, Any], suggestion: dict[str, Any]) -> dict[str, Any]:
    """Return a deep-enough copy of struct with suggestion["after"] substituted
    for suggestion["before"] in the target section/entry.
    """
    import copy
    rewritten = copy.deepcopy(struct)
    section = suggestion.get("section", "")
    before = suggestion.get("before", "")
    after = suggestion.get("after", "")

    if section == "summary":
        if rewritten.get("career_summary", "") == before:
            rewritten["career_summary"] = after
    elif section == "experience":
        # target format is "Company|Title" (see score_resume's prompt spec).
        target = suggestion.get("target", "")
        company, _, title = target.partition("|")
        matched = False
        for exp in rewritten.get("experience", []):
            if exp.get("title") == title and exp.get("company") == company:
                matched = True
                bullets = exp.get("bullets") or []
                exp["bullets"] = [after if b == before else b for b in bullets]
        if not matched and (company or title):
            # The suggestion targets an experience entry that does not exist in
            # the original resume. Rather than silently dropping it, record it
            # as a new entry so hallucination_check() sees the fabricated
            # company/title as a new anchor and rejects it, instead of letting
            # an unmatched target through as a no-op that looks "safe".
            new_entry = {"company": company, "title": title, "start_date": "",
                              "end_date": "", "bullets": [after]}
            rewritten.setdefault("experience", []).append(new_entry)
    elif section == "skills":
        skills = rewritten.get("skills") or []
        rewritten["skills"] = [after if s == before else s for s in skills]

    return rewritten


def _parse_llm_json(raw: str) -> dict[str, Any]:
    """Parse an LLM's JSON response, stripping markdown code fences if present."""
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    return json.loads(text)
