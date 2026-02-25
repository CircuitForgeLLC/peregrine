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
import re

import pdfplumber
from docx import Document


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
        f"Resume text:\n{raw_text[:6000]}"
    )
    router = LLMRouter()
    return router.complete(prompt)


def structure_resume(raw_text: str) -> dict:
    """Convert raw resume text to a structured dict via LLM.

    Returns an empty dict on any failure — caller should fall back to form builder.
    """
    try:
        raw = _llm_structure(raw_text)
        # Strip markdown code fences if present
        raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
        raw = re.sub(r"\s*```$", "", raw)
        return json.loads(raw)
    except Exception:
        return {}
