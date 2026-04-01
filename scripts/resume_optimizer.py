"""
ATS Resume Optimizer — rewrite a candidate's resume to maximize keyword match
for a specific job description without fabricating experience.

Tier behaviour:
  Free   → gap report only  (extract_jd_signals + prioritize_gaps, no LLM rewrite)
  Paid   → full LLM rewrite targeting the JD (rewrite_for_ats)
  Premium → same as paid for now; fine-tuned voice model is a future enhancement

Pipeline:
  job.description
      → extract_jd_signals()    # TF-IDF gaps + LLM-extracted ATS signals
      → prioritize_gaps()       # rank by impact, map to resume sections
      → rewrite_for_ats()       # per-section LLM rewrite (paid+)
      → hallucination_check()   # reject rewrites that invent new experience
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# ── Signal extraction ─────────────────────────────────────────────────────────

def extract_jd_signals(description: str, resume_text: str = "") -> list[str]:
    """Return ATS keyword signals from a job description.

    Combines two sources:
      1. TF-IDF keyword gaps from match.py (fast, deterministic, no LLM cost)
      2. LLM extraction for phrasing nuance TF-IDF misses (e.g. "cross-functional"
         vs "cross-team", "led" vs "managed")

    Falls back to TF-IDF-only if LLM is unavailable.

    Args:
        description: Raw job description text.
        resume_text: Candidate's resume text (used to compute gap vs. already present).

    Returns:
        Deduplicated list of ATS keyword signals, most impactful first.
    """
    # Phase 1: deterministic TF-IDF gaps (always available)
    tfidf_gaps: list[str] = []
    if resume_text:
        try:
            from scripts.match import match_score
            _, tfidf_gaps = match_score(resume_text, description)
        except Exception:
            log.warning("[resume_optimizer] TF-IDF gap extraction failed", exc_info=True)

    # Phase 2: LLM extraction for phrasing/qualifier nuance
    llm_signals: list[str] = []
    try:
        from scripts.llm_router import LLMRouter
        prompt = (
            "Extract the most important ATS (applicant tracking system) keywords and "
            "phrases from this job description. Focus on:\n"
            "- Required skills and technologies (exact phrasing matters)\n"
            "- Action verbs used to describe responsibilities\n"
            "- Qualification signals ('required', 'must have', 'preferred')\n"
            "- Industry-specific terminology\n\n"
            "Return a JSON array of strings only. No explanation.\n\n"
            f"Job description:\n{description[:3000]}"
        )
        raw = LLMRouter().complete(prompt)
        # Extract JSON array from response (LLM may wrap it in markdown)
        match = re.search(r"\[.*\]", raw, re.DOTALL)
        if match:
            llm_signals = json.loads(match.group(0))
            llm_signals = [s.strip() for s in llm_signals if isinstance(s, str) and s.strip()]
    except Exception:
        log.warning("[resume_optimizer] LLM signal extraction failed", exc_info=True)

    # Merge: LLM signals first (richer phrasing), TF-IDF fills gaps
    seen: set[str] = set()
    merged: list[str] = []
    for term in llm_signals + tfidf_gaps:
        key = term.lower()
        if key not in seen:
            seen.add(key)
            merged.append(term)

    return merged


# ── Gap prioritization ────────────────────────────────────────────────────────

# Map each gap term to the resume section where it would have the most ATS impact.
# ATS systems weight keywords higher in certain sections:
#   skills    — direct keyword match, highest density, indexed first
#   summary   — executive summary keywords often boost overall relevance score
#   experience — verbs + outcomes in bullet points; adds context weight
_SECTION_KEYWORDS: dict[str, list[str]] = {
    "skills": [
        "python", "sql", "java", "typescript", "react", "vue", "docker",
        "kubernetes", "aws", "gcp", "azure", "terraform", "ci/cd", "git",
        "postgresql", "redis", "kafka", "spark", "tableau", "salesforce",
        "jira", "figma", "excel", "powerpoint", "machine learning", "llm",
        "deep learning", "pytorch", "tensorflow", "scikit-learn",
    ],
    "summary": [
        "leadership", "strategy", "vision", "executive", "director", "vp",
        "growth", "transformation", "stakeholder", "cross-functional",
        "p&l", "revenue", "budget", "board", "c-suite",
    ],
}


def prioritize_gaps(gaps: list[str], resume_sections: dict[str, Any]) -> list[dict]:
    """Rank keyword gaps by ATS impact and map each to a target resume section.

    Args:
        gaps: List of missing keyword signals from extract_jd_signals().
        resume_sections: Structured resume dict from resume_parser.parse_resume().

    Returns:
        List of dicts, sorted by priority score descending:
            {
              "term": str,          # the keyword/phrase to inject
              "section": str,       # target resume section ("skills", "summary", "experience")
              "priority": int,      # 1=high, 2=medium, 3=low
              "rationale": str,     # why this section was chosen
            }

    TODO: implement the ranking logic below.
    The current stub assigns every gap to "experience" at medium priority.
    A good implementation should:
      - Score "skills" section terms highest (direct keyword density)
      - Score "summary" terms next (executive/leadership signals)
      - Route remaining gaps to "experience" bullets
      - Deprioritize terms already present in any section (case-insensitive)
      - Consider gap term length: multi-word phrases > single words (more specific = higher ATS weight)
    """
    existing_text = _flatten_resume_text(resume_sections).lower()

    prioritized: list[dict] = []
    for term in gaps:
        # Skip terms already present anywhere in the resume
        if term.lower() in existing_text:
            continue

        # REVIEW: _SECTION_KEYWORDS lists are tech-centric; domain-specific roles
        # (creative, healthcare, operations) may over-route to experience.
        # Consider expanding the lists or making them config-driven.
        term_lower = term.lower()

        # Partial-match: term contains a skills keyword (handles "PostgreSQL" vs "postgresql",
        # "AWS Lambda" vs "aws", etc.)
        skills_match = any(kw in term_lower or term_lower in kw
                           for kw in _SECTION_KEYWORDS["skills"])
        summary_match = any(kw in term_lower or term_lower in kw
                            for kw in _SECTION_KEYWORDS["summary"])

        if skills_match:
            section = "skills"
            priority = 1
            rationale = "matched technical skills list — highest ATS keyword density"
        elif summary_match:
            section = "summary"
            priority = 1
            rationale = "matched leadership/executive signals — boosts overall relevance score"
        elif len(term.split()) > 1:
            section = "experience"
            priority = 2
            rationale = "multi-word phrase — more specific than single keywords, context weight in bullets"
        else:
            section = "experience"
            priority = 3
            rationale = "single generic term — lowest ATS impact, added to experience for coverage"

        prioritized.append({
            "term":      term,
            "section":   section,
            "priority":  priority,
            "rationale": rationale,
        })

    prioritized.sort(key=lambda x: x["priority"])
    return prioritized


def _flatten_resume_text(resume: dict[str, Any]) -> str:
    """Concatenate all text from a structured resume dict into one searchable string."""
    parts: list[str] = []
    parts.append(resume.get("career_summary", "") or "")
    parts.extend(resume.get("skills", []))
    for exp in resume.get("experience", []):
        parts.append(exp.get("title", ""))
        parts.append(exp.get("company", ""))
        parts.extend(exp.get("bullets", []))
    for edu in resume.get("education", []):
        parts.append(edu.get("degree", ""))
        parts.append(edu.get("field", ""))
        parts.append(edu.get("institution", ""))
    parts.extend(resume.get("achievements", []))
    return " ".join(parts)


# ── LLM rewrite ───────────────────────────────────────────────────────────────

def rewrite_for_ats(
    resume: dict[str, Any],
    prioritized_gaps: list[dict],
    job: dict[str, Any],
    candidate_voice: str = "",
) -> dict[str, Any]:
    """Rewrite resume sections to naturally incorporate ATS keyword gaps.

    Operates section-by-section. For each target section in prioritized_gaps,
    builds a focused prompt that injects only the gaps destined for that section.
    The hallucination constraint is enforced in the prompt itself and verified
    post-hoc by hallucination_check().

    Args:
        resume: Structured resume dict (from resume_parser.parse_resume).
        prioritized_gaps: Output of prioritize_gaps().
        job: Job dict with at minimum {"title": str, "company": str, "description": str}.
        candidate_voice: Free-text personality/style note from user.yaml (may be empty).

    Returns:
        New resume dict (same structure as input) with rewritten sections.
        Sections with no relevant gaps are copied through unchanged.
    """
    from scripts.llm_router import LLMRouter
    router = LLMRouter()

    # Group gaps by target section
    by_section: dict[str, list[str]] = {}
    for gap in prioritized_gaps:
        by_section.setdefault(gap["section"], []).append(gap["term"])

    rewritten = dict(resume)  # shallow copy — sections replaced below

    for section, terms in by_section.items():
        terms_str = ", ".join(f'"{t}"' for t in terms)
        original_content = _section_text_for_prompt(resume, section)

        voice_note = (
            f'\n\nCandidate voice/style: "{candidate_voice}". '
            "Preserve this authentic tone — do not write generically."
        ) if candidate_voice else ""

        prompt = (
            f"You are rewriting the **{section}** section of a resume to help it pass "
            f"ATS (applicant tracking system) screening for this role:\n"
            f"  Job title: {job.get('title', 'Unknown')}\n"
            f"  Company: {job.get('company', 'Unknown')}\n\n"
            f"Inject these missing ATS keywords naturally into the section:\n"
            f"  {terms_str}\n\n"
            f"CRITICAL RULES — violating any of these invalidates the rewrite:\n"
            f"1. Do NOT invent new employers, job titles, dates, or education.\n"
            f"2. Do NOT add skills the candidate did not already demonstrate.\n"
            f"3. Only rephrase existing content — replace vague verbs/nouns with the "
            f"   ATS-preferred equivalents listed above.\n"
            f"4. Keep the same number of bullet points in experience entries.\n"
            f"5. Return ONLY the rewritten section content, no labels or explanation."
            f"{voice_note}\n\n"
            f"Original {section} section:\n{original_content}"
        )

        try:
            result = router.complete(prompt)
            rewritten = _apply_section_rewrite(rewritten, section, result.strip())
        except Exception:
            log.warning("[resume_optimizer] rewrite failed for section %r", section, exc_info=True)
            # Leave section unchanged on failure

    return rewritten


def _section_text_for_prompt(resume: dict[str, Any], section: str) -> str:
    """Render a resume section as plain text suitable for an LLM prompt."""
    if section == "summary":
        return resume.get("career_summary", "") or "(empty)"
    if section == "skills":
        skills = resume.get("skills", [])
        return ", ".join(skills) if skills else "(empty)"
    if section == "experience":
        lines: list[str] = []
        for exp in resume.get("experience", []):
            lines.append(f"{exp['title']} at {exp['company']} ({exp['start_date']}–{exp['end_date']})")
            for b in exp.get("bullets", []):
                lines.append(f"  • {b}")
        return "\n".join(lines) if lines else "(empty)"
    return "(unsupported section)"


def _apply_section_rewrite(resume: dict[str, Any], section: str, rewritten: str) -> dict[str, Any]:
    """Return a new resume dict with the given section replaced by rewritten text."""
    updated = dict(resume)
    if section == "summary":
        updated["career_summary"] = rewritten
    elif section == "skills":
        # LLM returns comma-separated or newline-separated skills
        skills = [s.strip() for s in re.split(r"[,\n•·]+", rewritten) if s.strip()]
        updated["skills"] = skills
    elif section == "experience":
        # For experience, we keep the structured entries but replace the bullets.
        # The LLM rewrites the whole section as plain text; we re-parse the bullets.
        updated["experience"] = _reparse_experience_bullets(resume["experience"], rewritten)
    return updated


def _reparse_experience_bullets(
    original_entries: list[dict],
    rewritten_text: str,
) -> list[dict]:
    """Re-associate rewritten bullet text with the original experience entries.

    The LLM rewrites the section as a block of text. We split on the original
    entry headers (title + company) to re-bind bullets to entries. Falls back
    to the original entries if splitting fails.
    """
    if not original_entries:
        return original_entries

    result: list[dict] = []
    remaining = rewritten_text

    for i, entry in enumerate(original_entries):
        # Find where the next entry starts so we can slice out this entry's bullets
        if i + 1 < len(original_entries):
            next_title = original_entries[i + 1]["title"]
            # Look for the next entry header in the remaining text
            split_pat = re.escape(next_title)
            m = re.search(split_pat, remaining, re.IGNORECASE)
            chunk = remaining[:m.start()] if m else remaining
            remaining = remaining[m.start():] if m else ""
        else:
            chunk = remaining

        bullets = [
            re.sub(r"^[•\-–—*◦▪▸►]\s*", "", line).strip()
            for line in chunk.splitlines()
            if re.match(r"^[•\-–—*◦▪▸►]\s*", line.strip())
        ]
        new_entry = dict(entry)
        new_entry["bullets"] = bullets if bullets else entry["bullets"]
        result.append(new_entry)

    return result


# ── Hallucination guard ───────────────────────────────────────────────────────

def hallucination_check(original: dict[str, Any], rewritten: dict[str, Any]) -> bool:
    """Return True if the rewrite is safe (no fabricated facts detected).

    Checks that the set of employers, job titles, and date ranges in the
    rewritten resume is a subset of those in the original. Any new entry
    signals hallucination.

    Args:
        original: Structured resume dict before rewrite.
        rewritten: Structured resume dict after rewrite.

    Returns:
        True  → rewrite is safe to use
        False → hallucination detected; caller should fall back to original
    """
    orig_anchors  = _extract_anchors(original)
    rewrite_anchors = _extract_anchors(rewritten)

    new_anchors = rewrite_anchors - orig_anchors
    if new_anchors:
        log.warning(
            "[resume_optimizer] hallucination_check FAILED — new anchors in rewrite: %s",
            new_anchors,
        )
        return False
    return True


def _extract_anchors(resume: dict[str, Any]) -> frozenset[str]:
    """Extract stable factual anchors (company, title, dates) from experience entries."""
    anchors: set[str] = set()
    for exp in resume.get("experience", []):
        for field in ("company", "title", "start_date", "end_date"):
            val = (exp.get(field) or "").strip().lower()
            if val:
                anchors.add(val)
    for edu in resume.get("education", []):
        val = (edu.get("institution") or "").strip().lower()
        if val:
            anchors.add(val)
    return frozenset(anchors)


# ── Resume → plain text renderer ─────────────────────────────────────────────

def render_resume_text(resume: dict[str, Any]) -> str:
    """Render a structured resume dict back to formatted plain text for PDF export."""
    lines: list[str] = []

    contact_parts = [resume.get("name", ""), resume.get("email", ""), resume.get("phone", "")]
    lines.append("  ".join(p for p in contact_parts if p))
    lines.append("")

    if resume.get("career_summary"):
        lines.append("SUMMARY")
        lines.append(resume["career_summary"])
        lines.append("")

    if resume.get("experience"):
        lines.append("EXPERIENCE")
        for exp in resume["experience"]:
            lines.append(
                f"{exp.get('title', '')}  |  {exp.get('company', '')}  "
                f"({exp.get('start_date', '')}–{exp.get('end_date', '')})"
            )
            for b in exp.get("bullets", []):
                lines.append(f"  • {b}")
        lines.append("")

    if resume.get("education"):
        lines.append("EDUCATION")
        for edu in resume["education"]:
            lines.append(
                f"{edu.get('degree', '')} {edu.get('field', '')}  |  "
                f"{edu.get('institution', '')}  {edu.get('graduation_year', '')}"
            )
        lines.append("")

    if resume.get("skills"):
        lines.append("SKILLS")
        lines.append(", ".join(resume["skills"]))
        lines.append("")

    if resume.get("achievements"):
        lines.append("ACHIEVEMENTS")
        for a in resume["achievements"]:
            lines.append(f"  • {a}")
        lines.append("")

    return "\n".join(lines)
