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
            json_str = match.group(0)
            # LLMs occasionally emit invalid JSON escape sequences (e.g. \s, \d, \p)
            # that are valid regex but not valid JSON. Replace bare backslashes that
            # aren't followed by a recognised JSON escape character.
            json_str = re.sub(r'\\([^"\\/bfnrtu])', r'\1', json_str)
            llm_signals = json.loads(json_str)
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

    # Rerank gaps by JD relevance so the most impactful terms are injected first.
    # Falls back silently to the incoming priority ordering on any error.
    jd_text = job.get("description", "")
    if jd_text and prioritized_gaps:
        try:
            from circuitforge_core.reranker import rerank as _rerank
            terms = [g["term"] for g in prioritized_gaps]
            results = _rerank(jd_text, terms, top_n=len(terms))
            term_rank = {r.candidate: r.rank for r in results}
            prioritized_gaps = sorted(
                prioritized_gaps,
                key=lambda g: term_rank.get(g["term"], len(prioritized_gaps)),
            )
        except Exception:
            pass  # keep original priority ordering

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
        updated["experience"] = _reparse_experience_bullets(resume.get("experience", []), rewritten)
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


# ── Gap framing ───────────────────────────────────────────────────────────────

def frame_skill_gaps(
    struct: dict[str, Any],
    gap_framings: list[dict],
    job: dict[str, Any],
    candidate_voice: str = "",
) -> dict[str, Any]:
    """Inject honest framing language for skills the candidate doesn't have directly.

    For each gap framing decision the user provided:
      - mode "adjacent": user has related experience → injects one bridging sentence
        into the most relevant experience entry's bullets
      - mode "learning": actively developing the skill → prepends a structured
        "Developing: X (context)" note to the skills list
      - mode "skip": no connection at all → no change

    The user-supplied context text is the source of truth. The LLM's job is only
    to phrase it naturally in resume style — not to invent new claims.

    Args:
        struct: Resume dict (already processed by apply_review_decisions).
        gap_framings: List of dicts with keys:
            skill    — the ATS term the candidate lacks
            mode     — "adjacent" | "learning" | "skip"
            context  — candidate's own words describing their related background
        job: Job dict for role context in prompts.
        candidate_voice: Free-text style note from user.yaml.

    Returns:
        New resume dict with framing language injected.
    """
    from scripts.llm_router import LLMRouter
    router = LLMRouter()

    updated = dict(struct)
    updated["experience"] = [dict(e) for e in (struct.get("experience") or [])]

    adjacent_framings = [f for f in gap_framings if f.get("mode") == "adjacent" and f.get("context")]
    learning_framings = [f for f in gap_framings if f.get("mode") == "learning" and f.get("context")]

    # ── Adjacent experience: inject bridging sentence into most relevant entry ─
    for framing in adjacent_framings:
        skill = framing["skill"]
        context = framing["context"]

        # Find the experience entry most likely to be relevant (simple keyword match)
        best_entry_idx = _find_most_relevant_entry(updated["experience"], skill)
        if best_entry_idx is None:
            continue

        entry = updated["experience"][best_entry_idx]
        bullets = list(entry.get("bullets") or [])

        voice_note = (
            f'\n\nCandidate voice/style: "{candidate_voice}". Match this tone.'
        ) if candidate_voice else ""

        prompt = (
            f"You are adding one honest framing sentence to a resume bullet list.\n\n"
            f"The candidate does not have direct experience with '{skill}', "
            f"but they have relevant background they described as:\n"
            f'  "{context}"\n\n'
            f"Job context: {job.get('title', '')} at {job.get('company', '')}.\n\n"
            f"RULES:\n"
            f"1. Add exactly ONE new bullet point that bridges their background to '{skill}'.\n"
            f"2. Do NOT fabricate anything beyond what their context description says.\n"
            f"3. Use honest language: 'adjacent experience in', 'strong foundation applicable to', "
            f"   'directly transferable background in', etc.\n"
            f"4. Return ONLY the single new bullet text — no prefix, no explanation."
            f"{voice_note}\n\n"
            f"Existing bullets for context:\n"
            + "\n".join(f"  • {b}" for b in bullets[:3])
        )

        try:
            new_bullet = router.complete(prompt).strip()
            new_bullet = re.sub(r"^[•\-–—*◦▪▸►]\s*", "", new_bullet).strip()
            if new_bullet:
                bullets.append(new_bullet)
                new_entry = dict(entry)
                new_entry["bullets"] = bullets
                updated["experience"][best_entry_idx] = new_entry
        except Exception:
            log.warning(
                "[resume_optimizer] frame_skill_gaps adjacent failed for skill %r", skill,
                exc_info=True,
            )

    # ── Learning framing: add structured note to skills list ──────────────────
    if learning_framings:
        skills = list(updated.get("skills") or [])
        for framing in learning_framings:
            skill = framing["skill"]
            context = framing["context"].strip()
            # Format: "Developing: Kubernetes (strong Docker/container orchestration background)"
            note = f"Developing: {skill} ({context})" if context else f"Developing: {skill}"
            if note not in skills:
                skills.append(note)
        updated["skills"] = skills

    return updated


def _find_most_relevant_entry(
    experience: list[dict],
    skill: str,
) -> int | None:
    """Return the index of the experience entry most relevant to a skill term.

    Uses simple keyword overlap between the skill and entry title/bullets.
    Falls back to the most recent (first) entry if no match found.
    """
    if not experience:
        return None

    skill_words = set(skill.lower().split())
    best_idx = 0
    best_score = -1

    for i, entry in enumerate(experience):
        entry_text = (
            (entry.get("title") or "") + " " +
            " ".join(entry.get("bullets") or [])
        ).lower()
        entry_words = set(entry_text.split())
        score = len(skill_words & entry_words)
        if score > best_score:
            best_score = score
            best_idx = i

    return best_idx


def apply_review_decisions(
    draft: dict[str, Any],
    decisions: dict[str, Any],
) -> dict[str, Any]:
    """Apply user section-level review decisions to the rewritten struct.

    Handles approved skills, summary accept/reject, and per-entry experience
    accept/reject. Returns the updated struct; does not call the LLM.

    Args:
        draft: The review draft dict from build_review_diff (contains
               "sections" and "rewritten_struct").
        decisions: Dict of per-section decisions from the review UI:
            skills:     {"approved_additions": [...]}
            summary:    {"accepted": bool}
            experience: {"accepted_entries": [{"title", "company", "accepted"}]}

    Returns:
        Updated resume struct ready for gap framing and final render.
    """
    struct = dict(draft.get("rewritten_struct") or {})
    sections = draft.get("sections") or []

    # ── Skills: keep original + only approved additions ────────────────────
    skills_decision = decisions.get("skills", {})
    approved_additions = set(skills_decision.get("approved_additions") or [])
    for sec in sections:
        if sec["section"] == "skills":
            original_kept = set(sec.get("kept") or [])
            struct["skills"] = sorted(original_kept | approved_additions)
            break

    # ── Summary: accept proposed or revert to original ──────────────────────
    if not decisions.get("summary", {}).get("accepted", True):
        for sec in sections:
            if sec["section"] == "summary":
                struct["career_summary"] = sec.get("original", struct.get("career_summary", ""))
                break

    # ── Experience: per-entry accept/reject ─────────────────────────────────
    exp_decisions: dict[str, bool] = {
        f"{ed.get('title', '')}|{ed.get('company', '')}": ed.get("accepted", True)
        for ed in (decisions.get("experience", {}).get("accepted_entries") or [])
    }
    for sec in sections:
        if sec["section"] == "experience":
            for entry_diff in (sec.get("entries") or []):
                key = f"{entry_diff['title']}|{entry_diff['company']}"
                if not exp_decisions.get(key, True):
                    for exp_entry in (struct.get("experience") or []):
                        if (exp_entry.get("title") == entry_diff["title"] and
                                exp_entry.get("company") == entry_diff["company"]):
                            exp_entry["bullets"] = entry_diff["original_bullets"]
            break

    return struct


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


# ── Review diff builder ────────────────────────────────────────────────────────

def build_review_diff(
    original: dict[str, Any],
    rewritten: dict[str, Any],
) -> dict[str, Any]:
    """Build a structured diff between original and rewritten resume for the review UI.

    Returns a dict with:
      sections: list of per-section diffs
      rewritten_struct: the full rewritten resume dict (used by finalize endpoint)

    Each section diff has:
      section: "skills" | "summary" | "experience"
      type: "skills_diff" | "text_diff" | "bullets_diff"
      For skills_diff:
        added: list of new skill strings (each requires user approval)
        removed: list of removed skill strings
        kept: list of unchanged skills
      For text_diff (summary):
        original: str
        proposed: str
      For bullets_diff (experience):
        entries: list of {title, company, original_bullets, proposed_bullets}
    """
    sections = []

    # ── Skills diff ────────────────────────────────────────────────────────
    orig_skills = set(s.strip() for s in (original.get("skills") or []))
    new_skills  = set(s.strip() for s in (rewritten.get("skills") or []))

    added   = sorted(new_skills - orig_skills)
    removed = sorted(orig_skills - new_skills)
    kept    = sorted(orig_skills & new_skills)

    if added or removed:
        sections.append({
            "section": "skills",
            "type":    "skills_diff",
            "added":   added,
            "removed": removed,
            "kept":    kept,
        })

    # ── Summary diff ───────────────────────────────────────────────────────
    orig_summary = (original.get("career_summary") or "").strip()
    new_summary  = (rewritten.get("career_summary") or "").strip()

    if orig_summary != new_summary and new_summary:
        sections.append({
            "section":  "summary",
            "type":     "text_diff",
            "original": orig_summary,
            "proposed": new_summary,
        })

    # ── Experience diff ────────────────────────────────────────────────────
    orig_exp = original.get("experience") or []
    new_exp  = rewritten.get("experience") or []

    entry_diffs = []
    for orig_entry, new_entry in zip(orig_exp, new_exp):
        orig_bullets = orig_entry.get("bullets") or []
        new_bullets  = new_entry.get("bullets") or []
        if orig_bullets != new_bullets:
            entry_diffs.append({
                "title":            orig_entry.get("title", ""),
                "company":          orig_entry.get("company", ""),
                "original_bullets": orig_bullets,
                "proposed_bullets": new_bullets,
            })

    if entry_diffs:
        sections.append({
            "section": "experience",
            "type":    "bullets_diff",
            "entries": entry_diffs,
        })

    return {
        "sections":         sections,
        "rewritten_struct": rewritten,
    }


# ── PDF export ─────────────────────────────────────────────────────────────────

def export_pdf(resume: dict[str, Any], output_path: str) -> None:
    """Render a structured resume dict to a clean PDF using reportlab.

    Uses a single-column layout with section headers, consistent spacing,
    and a readable sans-serif body font suitable for ATS submission.

    Args:
        resume: Structured resume dict (same format as resume_parser output).
        output_path: Absolute path for the output .pdf file.
    """
    from reportlab.lib.pagesizes import LETTER
    from reportlab.lib.units import inch
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
    from reportlab.lib import colors

    MARGIN = 0.75 * inch

    name_style = ParagraphStyle(
        "name", fontName="Helvetica-Bold", fontSize=16, leading=20,
        alignment=TA_CENTER, spaceAfter=2,
    )
    contact_style = ParagraphStyle(
        "contact", fontName="Helvetica", fontSize=9, leading=12,
        alignment=TA_CENTER, spaceAfter=6,
        textColor=colors.HexColor("#555555"),
    )
    section_style = ParagraphStyle(
        "section", fontName="Helvetica-Bold", fontSize=10, leading=14,
        spaceBefore=10, spaceAfter=2,
        textColor=colors.HexColor("#1a1a2e"),
    )
    body_style = ParagraphStyle(
        "body", fontName="Helvetica", fontSize=9, leading=13, alignment=TA_LEFT,
    )
    role_style = ParagraphStyle(
        "role", fontName="Helvetica-Bold", fontSize=9, leading=13,
    )
    meta_style = ParagraphStyle(
        "meta", fontName="Helvetica-Oblique", fontSize=8, leading=12,
        textColor=colors.HexColor("#555555"), spaceAfter=2,
    )
    bullet_style = ParagraphStyle(
        "bullet", fontName="Helvetica", fontSize=9, leading=13, leftIndent=12,
    )

    def hr():
        return HRFlowable(width="100%", thickness=0.5,
                          color=colors.HexColor("#cccccc"),
                          spaceAfter=4, spaceBefore=2)

    story = []

    if resume.get("name"):
        story.append(Paragraph(resume["name"], name_style))

    contact_parts = [p for p in (
        resume.get("email", ""), resume.get("phone", ""),
        resume.get("location", ""), resume.get("linkedin", ""),
    ) if p]
    if contact_parts:
        story.append(Paragraph("  |  ".join(contact_parts), contact_style))

    story.append(hr())

    summary = (resume.get("career_summary") or "").strip()
    if summary:
        story.append(Paragraph("SUMMARY", section_style))
        story.append(hr())
        story.append(Paragraph(summary, body_style))
        story.append(Spacer(1, 4))

    if resume.get("experience"):
        story.append(Paragraph("EXPERIENCE", section_style))
        story.append(hr())
        for exp in resume["experience"]:
            dates = f"{exp.get('start_date', '')}–{exp.get('end_date', '')}"
            story.append(Paragraph(
                f"{exp.get('title', '')}  |  {exp.get('company', '')}", role_style
            ))
            story.append(Paragraph(dates, meta_style))
            for bullet in (exp.get("bullets") or []):
                story.append(Paragraph(f"• {bullet}", bullet_style))
            story.append(Spacer(1, 4))

    if resume.get("education"):
        story.append(Paragraph("EDUCATION", section_style))
        story.append(hr())
        for edu in resume["education"]:
            degree = f"{edu.get('degree', '')} {edu.get('field', '')}".strip()
            story.append(Paragraph(
                f"{degree}  |  {edu.get('institution', '')}  {edu.get('graduation_year', '')}".strip(),
                body_style,
            ))
        story.append(Spacer(1, 4))

    if resume.get("skills"):
        story.append(Paragraph("SKILLS", section_style))
        story.append(hr())
        story.append(Paragraph(", ".join(resume["skills"]), body_style))
        story.append(Spacer(1, 4))

    if resume.get("achievements"):
        story.append(Paragraph("ACHIEVEMENTS", section_style))
        story.append(hr())
        for a in resume["achievements"]:
            story.append(Paragraph(f"• {a}", bullet_style))

    doc = SimpleDocTemplate(
        output_path, pagesize=LETTER,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=MARGIN, bottomMargin=MARGIN,
    )
    doc.build(story)
