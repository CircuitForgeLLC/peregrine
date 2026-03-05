"""
LLM-powered suggestion helpers for Settings UI.
Two functions, each makes one LLMRouter call:
  - suggest_search_terms: enhanced title + three-angle exclude suggestions
  - suggest_resume_keywords: skills/domains/keywords gap analysis
"""
import json
import re
from pathlib import Path
from typing import Any

from scripts.llm_router import LLMRouter


def _load_resume_context(resume_path: Path) -> str:
    """Extract 3 most recent positions from plain_text_resume.yaml as a short summary."""
    import yaml
    if not resume_path.exists():
        return ""
    resume = yaml.safe_load(resume_path.read_text()) or {}
    lines = []
    for exp in (resume.get("experience_details") or [])[:3]:
        pos = exp.get("position", "")
        co = exp.get("company", "")
        skills = ", ".join((exp.get("skills_acquired") or [])[:5])
        lines.append(f"- {pos} at {co}: {skills}")
    return "\n".join(lines)


def _parse_json(text: str) -> dict[str, Any]:
    """Extract the first JSON object from LLM output. Returns {} on failure."""
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
        except Exception:
            pass
    return {}


def suggest_search_terms(
    current_titles: list[str],
    resume_path: Path,
    blocklist: dict[str, Any],
    user_profile: dict[str, Any],
) -> dict:
    """
    Suggest additional job titles and exclude keywords.

    Three-angle exclude analysis:
      A: Blocklist alias expansion (blocked companies/industries → keyword variants)
      B: Values misalignment (mission preferences → industries/culture to avoid)
      C: Role-type filter (career summary → role types that don't fit)

    Returns: {"suggested_titles": [...], "suggested_excludes": [...]}
    """
    resume_context = _load_resume_context(resume_path)
    titles_str = "\n".join(f"- {t}" for t in current_titles) or "(none yet)"

    bl_companies = ", ".join(blocklist.get("companies", [])) or "none"
    bl_industries = ", ".join(blocklist.get("industries", [])) or "none"
    nda = ", ".join(user_profile.get("nda_companies", [])) or "none"
    career_summary = user_profile.get("career_summary", "") or "Not provided"
    mission_raw = user_profile.get("mission_preferences", {}) or {}
    # Three exclude angles are intentionally collapsed into one flat suggested_excludes list
    mission_str = "\n".join(
        f"  - {k}: {v}" for k, v in mission_raw.items() if v and isinstance(v, str) and v.strip()
    ) or "  (none specified)"

    prompt = f"""You are helping a job seeker optimise their search configuration.

--- RESUME BACKGROUND ---
{resume_context or "Not provided"}

--- CAREER SUMMARY ---
{career_summary}

--- CURRENT TITLES BEING SEARCHED ---
{titles_str}

--- BLOCKED ENTITIES ---
Companies blocked: {bl_companies}
Industries blocked: {bl_industries}
NDA / confidential employers: {nda}

--- MISSION & VALUES ---
{mission_str}

Provide all four of the following:

1. TITLE SUGGESTIONS
   5-8 additional job titles they may be missing: alternative names, adjacent roles, or senior variants of their current titles.

2. EXCLUDE KEYWORDS — BLOCKLIST ALIASES
   The user has blocked the companies/industries above. Suggest keyword variants that would also catch their aliases, subsidiaries, or related brands.
   Example: blocking "Meta" → also exclude "facebook", "instagram", "metaverse", "oculus".

3. EXCLUDE KEYWORDS — VALUES MISALIGNMENT
   Based on the user's mission and values above, suggest industry or culture keywords to exclude.
   Examples: "tobacco", "gambling", "fossil fuel", "defense contractor", "MLM", "commission-only", "pyramid".

4. EXCLUDE KEYWORDS — ROLE TYPE FILTER
   Based on the user's career background, suggest role-type terms that don't match their trajectory.
   Examples for a CS/TAM leader: "cold calling", "door to door", "quota-driven", "SDR", "sales development rep".

Return ONLY valid JSON in exactly this format (no extra text):
{{"suggested_titles": ["Title 1", "Title 2"],
  "suggested_excludes": ["keyword 1", "keyword 2", "keyword 3"]}}"""

    raw = LLMRouter().complete(prompt).strip()
    parsed = _parse_json(raw)
    return {
        "suggested_titles": parsed.get("suggested_titles", []),
        "suggested_excludes": parsed.get("suggested_excludes", []),
    }


def suggest_resume_keywords(
    resume_path: Path,
    current_kw: dict[str, list[str]],
) -> dict:
    """
    Suggest skills, domains, and keywords not already in the user's resume_keywords.yaml.

    Returns: {"skills": [...], "domains": [...], "keywords": [...]}
    """
    raise NotImplementedError
