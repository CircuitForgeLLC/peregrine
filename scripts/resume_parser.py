"""
Resume parser — extract text from PDF/DOCX and structure via LLM.

Fast path: file bytes → raw text → LLM structures into resume dict.
Result dict keys mirror plain_text_resume.yaml sections.

Falls back to empty dict on any LLM/parsing error — caller should
then show the guided form builder.
"""
from __future__ import annotations
import io
import json
import logging
import re

import pdfplumber
from docx import Document

log = logging.getLogger(__name__)


def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Extract raw text from PDF bytes using pdfplumber.

    Returns empty string if extraction fails for any page.
    """
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        pages = [page.extract_text() or "" for page in pdf.pages]
    return "\n".join(pages)


def extract_text_from_docx(file_bytes: bytes) -> str:
    """Extract raw text from DOCX bytes using python-docx."""
    doc = Document(io.BytesIO(file_bytes))
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())


def _llm_structure(raw_text: str) -> str:
    """Call LLM to convert raw resume text to JSON. Returns raw LLM output string."""
    from scripts.llm_router import LLMRouter
    prompt = (
        "You are a resume parser. Convert the following resume text into a JSON object.\n\n"
        "Required JSON keys:\n"
        "- name (string)\n"
        "- email (string, may be empty)\n"
        "- phone (string, may be empty)\n"
        "- career_summary (string: 2-4 sentence professional summary)\n"
        "- experience (list of objects with: company, title, start_date, end_date, bullets list of strings)\n"
        "- education (list of objects with: institution, degree, field, graduation_year)\n"
        "- skills (list of strings)\n"
        "- achievements (list of strings, may be empty)\n\n"
        "Return ONLY valid JSON. No markdown, no explanation.\n\n"
        f"Resume text:\n{raw_text[:4000]}"
    )
    router = LLMRouter()
    return router.complete(prompt, max_tokens=2048)


def structure_resume(raw_text: str) -> tuple[dict, str]:
    """Convert raw resume text to a structured dict via LLM.

    Returns (result_dict, error_message). result_dict is empty on failure.
    """
    import traceback
    if not raw_text.strip():
        return {}, "Text extraction returned empty — the file may be image-based or unreadable."
    raw = ""
    try:
        raw = _llm_structure(raw_text)
        cleaned = re.sub(r"^```(?:json)?\s*", "", raw.strip())
        cleaned = re.sub(r"\s*```$", "", cleaned)
        try:
            return json.loads(cleaned), ""
        except json.JSONDecodeError:
            # Try json-repair before giving up — handles truncation and minor malformations
            from json_repair import repair_json
            repaired = repair_json(cleaned)
            result = json.loads(repaired)
            log.warning("[resume_parser] Used json-repair to recover malformed output")
            return result, ""
    except json.JSONDecodeError as e:
        log.error("[resume_parser] JSON parse error (even after repair): %s\nRaw output:\n%s", e, raw[:500])
        return {}, f"LLM returned invalid JSON: {e}"
    except Exception as e:
        log.error("[resume_parser] Error:\n%s", traceback.format_exc())
        return {}, str(e)
