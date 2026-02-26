"""
Resume parser — extract text from PDF/DOCX and structure via section parsing.

Primary path: regex + section detection (no LLM, no token limits).
Optional enhancement: LLM-generated career_summary if a capable backend is configured.

Falls back to empty dict on unrecoverable errors — caller shows the form builder.
"""
from __future__ import annotations

import io
import json
import logging
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import pdfplumber
from docx import Document

log = logging.getLogger(__name__)

# ── Section header detection ──────────────────────────────────────────────────

_SECTION_NAMES = {
    "summary":    re.compile(r"^(summary|objective|profile|about me|professional summary|career summary|career objective|personal statement)\s*:?\s*$", re.I),
    "experience": re.compile(r"^(experience|work experience|employment|work history|professional experience|career history|relevant experience|professional history|employment history|positions? held)\s*:?\s*$", re.I),
    "education":  re.compile(r"^(education|academic|qualifications|degrees?|educational background|academic background)\s*:?\s*$", re.I),
    "skills":     re.compile(r"^(skills?|technical skills?|core competencies|competencies|expertise|areas? of expertise|key skills?|proficiencies|tools? & technologies)\s*:?\s*$", re.I),
    "achievements": re.compile(r"^(achievements?|accomplishments?|awards?|honors?|certifications?|publications?|volunteer)\s*:?\s*$", re.I),
}

# Degrees — used to detect education lines
_DEGREE_RE = re.compile(
    r"\b(b\.?s\.?|b\.?a\.?|m\.?s\.?|m\.?b\.?a\.?|ph\.?d\.?|bachelor|master|associate|doctorate|diploma)\b",
    re.I,
)

# Date patterns for experience entries: "Jan 2020", "2020", "01/2020", "2019 - 2022"
_DATE_RE = re.compile(
    r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|january|february|march|april|june|"
    r"july|august|september|october|november|december)?\s*\d{4}\b"
    r"|\b\d{1,2}/\d{4}\b",
    re.I,
)
_DATE_RANGE_RE = re.compile(
    r"("
    r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*\.?\s+\d{4}"
    r"|\d{1,2}/\d{4}"
    r"|\d{4}"
    r")"
    r"\s*[-–—to]+\s*"
    r"("
    r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*\.?\s+\d{4}"
    r"|\d{1,2}/\d{4}"
    r"|\d{4}"
    r"|present|current|now"
    r")",
    re.I,
)

# Contact info
_EMAIL_RE    = re.compile(r"[\w.+\-]+@[\w\-]+\.[\w.\-]+")
_PHONE_RE    = re.compile(r"(?:\+1[\s.\-]?)?\(?\d{3}\)?[\s.\-]?\d{3}[\s.\-]?\d{4}")
_LINKEDIN_RE = re.compile(r"linkedin\.com/in/[\w\-]+", re.I)


# ── Text extraction ───────────────────────────────────────────────────────────

def _find_column_split(page) -> float | None:
    """Return the x-coordinate of the gutter between two columns, or None if single-column.

    Finds the largest horizontal gap between word x0 positions in the middle 40%
    of the page width — that gap is the column gutter.
    """
    words = page.extract_words()
    if len(words) < 10:
        return None
    lo, hi = page.width * 0.25, page.width * 0.75
    # Collect unique left-edge positions of words that start in the middle band
    xs = sorted({int(w["x0"]) for w in words if lo <= w["x0"] <= hi})
    if len(xs) < 2:
        return None
    # Find the biggest consecutive gap
    best_gap, split_x = 0.0, None
    for i in range(len(xs) - 1):
        gap = xs[i + 1] - xs[i]
        if gap > best_gap:
            best_gap, split_x = gap, (xs[i] + xs[i + 1]) / 2
    # Only treat as two-column if the gap is substantial (> 3% of page width)
    return split_x if split_x and best_gap > page.width * 0.03 else None


def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Extract text from PDF, handling two-column layouts via gutter detection.

    For two-column pages, the full-width header (name, contact) is extracted
    separately from the columnar body to avoid the centered header being clipped.
    """
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        pages: list[str] = []
        for page in pdf.pages:
            w, h = page.width, page.height
            split_x = _find_column_split(page)
            if split_x:
                # Find y-coordinate where right-column content starts.
                # Everything above that belongs to the full-width header.
                words = page.extract_words()
                right_words = [wd for wd in words if wd["x0"] >= split_x]
                col_start_y = min(wd["top"] for wd in right_words) if right_words else 0
                header_text = page.within_bbox((0,       0,       w,       col_start_y)).extract_text() or ""
                left_text   = page.within_bbox((0,       col_start_y, split_x, h)).extract_text() or ""
                right_text  = page.within_bbox((split_x, col_start_y, w,       h)).extract_text() or ""
                if len(left_text.strip()) > 60 and len(right_text.strip()) > 60:
                    pages.append("\n".join(filter(None, [header_text, left_text, right_text])))
                    continue
            pages.append(page.extract_text() or "")
    return "\n".join(pages)


def extract_text_from_docx(file_bytes: bytes) -> str:
    doc = Document(io.BytesIO(file_bytes))
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())


def extract_text_from_odt(file_bytes: bytes) -> str:
    """Extract plain text from an ODT file (ZIP + XML, no external deps required)."""
    # ODT is a ZIP archive; content.xml holds the document body
    _NS = "urn:oasis:names:tc:opendocument:xmlns:text:1.0"
    lines: list[str] = []
    with zipfile.ZipFile(io.BytesIO(file_bytes)) as zf:
        with zf.open("content.xml") as f:
            tree = ET.parse(f)
    # Walk all text:p and text:h elements in document order
    for elem in tree.iter():
        tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
        if tag in ("p", "h"):
            text = "".join(elem.itertext()).strip()
            if text:
                lines.append(text)
    return "\n".join(lines)


# ── Section splitter ──────────────────────────────────────────────────────────

def _split_sections(text: str) -> dict[str, list[str]]:
    """Split resume text into named sections. Lines that don't match a known
    section header go into 'header' (assumed to be contact/name block)."""
    sections: dict[str, list[str]] = {"header": []}
    current = "header"
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        matched = False
        for section, pattern in _SECTION_NAMES.items():
            # Match if the line IS a section header (short + matches pattern)
            if pattern.match(stripped) and len(stripped.split()) <= 5:
                current = section
                matched = True
                break
        if not matched:
            sections.setdefault(current, []).append(stripped)
    return sections


# ── Contact info ──────────────────────────────────────────────────────────────

def _parse_header(lines: list[str]) -> dict:
    """Extract name, email, phone from the top-of-resume block."""
    full_text = "\n".join(lines)
    email_m   = _EMAIL_RE.search(full_text)
    phone_m   = _PHONE_RE.search(full_text)

    # Name heuristic: first non-empty line that looks like a person's name.
    # Handle two common layouts:
    #   (A) Name on its own line
    #   (B) "email@example.com Firstname Lastname" on one line
    name = ""
    for line in lines[:8]:
        stripped = line.strip()
        if not stripped:
            continue
        # Layout B: line contains email — extract the part after the email as name
        if "@" in stripped:
            email_m = _EMAIL_RE.search(stripped)
            if email_m:
                after = stripped[email_m.end():].strip(" |•,")
                after_clean = re.sub(r"\s{2,}", " ", after)
                alpha_check = re.sub(r"[.\-'\u2019]", "", after_clean.replace(" ", ""))
                if 2 <= len(after_clean.split()) <= 5 and alpha_check.isalpha():
                    name = after_clean
                    break
            continue
        # Skip phone/URL/city lines
        if re.match(r"^\d", stripped):
            continue
        if re.search(r"\b[A-Z]{2}\b\s*\d{5}", stripped) or re.search(r"https?://|linkedin|github", stripped, re.I):
            continue
        # Layout A: plain name line
        candidate = re.sub(r"[|•·,]+", " ", stripped).strip()
        candidate = re.sub(r"\s{2,}", " ", candidate)
        alpha_check = re.sub(r"[.\-'\u2019]", "", candidate.replace(" ", ""))
        if 2 <= len(candidate.split()) <= 5 and alpha_check.isalpha():
            name = candidate
            break

    return {
        "name":  name,
        "email": email_m.group(0) if email_m else "",
        "phone": phone_m.group(0) if phone_m else "",
    }


# ── Experience ────────────────────────────────────────────────────────────────

def _parse_experience(lines: list[str]) -> list[dict]:
    """Parse work experience entries from section lines.

    Handles two common layouts:
      (A) Title | Company          (B) Title | Company | Dates
          Dates                        • bullet
          • bullet
    """
    entries: list[dict] = []
    current: dict | None = None
    prev_line = ""

    for line in lines:
        date_match = _DATE_RANGE_RE.search(line)
        if date_match:
            if current:
                entries.append(current)
            # Title/company extraction — three layouts:
            #  (A) Title on prev_line, "Company | Location | Dates" on date line
            #  (B) "Title | Company" on prev_line, dates on date line (same_line empty)
            #  (C) "Title | Company | Dates" all on one line
            same_line = _DATE_RANGE_RE.sub("", line)
            # Remove residual punctuation-only fragments like "()" left after date removal
            same_line = re.sub(r"[()[\]{}\s]+$", "", same_line).strip(" –—|-•")
            if prev_line and same_line.strip():
                # Layout A: title = prev_line, company = first segment of same_line
                title   = prev_line.strip()
                co_part = re.split(r"\s{2,}|[|,]\s*", same_line.strip(), maxsplit=1)[0]
                company = co_part.strip()
            else:
                # Layout B/C: title | company are together (prev_line or same_line)
                header = same_line if same_line.strip() else prev_line
                parts  = re.split(r"\s{2,}|[|•·,–—]\s*", header.strip(), maxsplit=1)
                title   = parts[0].strip() if parts else ""
                company = parts[1].strip() if len(parts) > 1 else ""
            current = {
                "title":      title,
                "company":    company,
                "start_date": date_match.group(1),
                "end_date":   date_match.group(2),
                "bullets":    [],
            }
            prev_line = ""
        elif current is not None:
            is_bullet = bool(re.match(r"^[•\-–—*◦▪▸►]\s*", line))
            looks_like_header = (
                not is_bullet
                and " | " in line
                and not _DATE_RE.search(line)
            )
            if looks_like_header:
                # Likely the title/company of the next entry — hold it as prev_line
                prev_line = line
            else:
                clean = re.sub(r"^[•\-–—*◦▪▸►]\s*", "", line).strip()
                if clean:
                    current["bullets"].append(clean)
                prev_line = line
        else:
            prev_line = line

    if current:
        entries.append(current)

    return entries


# ── Education ─────────────────────────────────────────────────────────────────

def _parse_education(lines: list[str]) -> list[dict]:
    entries: list[dict] = []
    current: dict | None = None
    prev_line = ""

    for line in lines:
        if _DEGREE_RE.search(line):
            if current:
                entries.append(current)
            current = {
                "institution":      "",
                "degree":           "",
                "field":            "",
                "graduation_year":  "",
            }
            year_m = re.search(r"\b(19|20)\d{2}\b", line)
            if year_m:
                current["graduation_year"] = year_m.group(0)
            degree_m = _DEGREE_RE.search(line)
            if degree_m:
                current["degree"] = degree_m.group(0).upper()
            remainder = _DEGREE_RE.sub("", _DATE_RE.sub("", line))
            remainder = re.sub(r"\b(19|20)\d{2}\b", "", remainder)
            current["field"] = remainder.strip(" ,–—|•.")
            # Layout A: institution was on the line before the degree line
            if prev_line and not _DEGREE_RE.search(prev_line):
                current["institution"] = prev_line.strip(" ,–—|•")
        elif current is not None and not current["institution"]:
            # Layout B: institution follows the degree line
            clean = line.strip(" ,–—|•")
            if clean:
                current["institution"] = clean
        prev_line = line.strip()

    if current:
        entries.append(current)

    return entries


# ── Skills ────────────────────────────────────────────────────────────────────

def _parse_skills(lines: list[str]) -> list[str]:
    skills: list[str] = []
    for line in lines:
        # Split on common delimiters
        for item in re.split(r"[,|•·/]+", line):
            clean = item.strip(" -–—*◦▪▸►()")
            if 1 < len(clean) <= 50:
                skills.append(clean)
    return skills


# ── Main parser ───────────────────────────────────────────────────────────────

def parse_resume(raw_text: str) -> tuple[dict, str]:
    """Parse resume text into a structured dict using section detection + regex.

    Returns (result_dict, error_message). result_dict is empty on failure.
    """
    if not raw_text.strip():
        return {}, "Text extraction returned empty — the file may be image-based or unreadable."

    try:
        sections = _split_sections(raw_text)
        contact  = _parse_header(sections.get("header", []))
        result = {
            **contact,
            "career_summary": " ".join(sections.get("summary", [])),
            "experience":     _parse_experience(sections.get("experience", [])),
            "education":      _parse_education(sections.get("education", [])),
            "skills":         _parse_skills(sections.get("skills", [])),
            "achievements":   sections.get("achievements", []),
        }
        return result, ""
    except Exception as e:
        import traceback
        log.error("[resume_parser] parse_resume error:\n%s", traceback.format_exc())
        return {}, str(e)


# ── LLM enhancement (career summary only, optional) ──────────────────────────

def _llm_career_summary(raw_text: str) -> str:
    """Use LLM to generate a career summary. Returns empty string on any failure."""
    try:
        from scripts.llm_router import LLMRouter
        prompt = (
            "Write a 2-3 sentence professional career summary for this candidate "
            "based on their resume. Return only the summary text, no labels.\n\n"
            f"Resume:\n{raw_text[:1500]}"
        )
        return LLMRouter().complete(prompt)
    except Exception:
        return ""


# ── Public entry point ────────────────────────────────────────────────────────

def structure_resume(raw_text: str) -> tuple[dict, str]:
    """Parse resume and optionally enhance career_summary via LLM.

    Returns (result_dict, error_message).
    """
    result, err = parse_resume(raw_text)
    if not result:
        return result, err

    # Enhance career summary via LLM if the section wasn't found in the document
    if not result.get("career_summary"):
        try:
            summary = _llm_career_summary(raw_text)
        except Exception:
            summary = ""
        if summary:
            result["career_summary"] = summary.strip()

    return result, ""
