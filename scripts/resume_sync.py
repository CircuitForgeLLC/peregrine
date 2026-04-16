"""
Resume format transform — library ↔ profile.

Converts between:
  - Library format: struct_json produced by resume_parser.parse_resume()
      {name, email, phone, career_summary, experience[{title,company,start_date,end_date,location,bullets[]}],
       education[{institution,degree,field,start_date,end_date}], skills[], achievements[]}
  - Profile content format: ResumePayload content fields (plain_text_resume.yaml)
      {name, surname, email, phone, career_summary,
       experience[{title,company,period,location,industry,responsibilities,skills[]}],
       education[{institution,degree,field,start_date,end_date}],
       skills[], achievements[]}

Profile metadata fields (salary, work prefs, self-ID, PII) are never touched here.

License: MIT
"""
from __future__ import annotations

from datetime import date
from typing import Any


_CONTENT_FIELDS = frozenset({
    "name", "surname", "email", "phone", "career_summary",
    "experience", "skills", "education", "achievements",
})


def library_to_profile_content(struct_json: dict[str, Any]) -> dict[str, Any]:
    """Transform a library struct_json to ResumePayload content fields.

    Returns only content fields. Caller is responsible for merging with existing
    metadata fields (salary, preferences, self-ID) so they are not overwritten.

    Lossy for experience[].industry (always blank — parser does not capture it).
    name is split on first space into name/surname.
    """
    full_name: str = struct_json.get("name") or ""
    parts = full_name.split(" ", 1)
    name = parts[0]
    surname = parts[1] if len(parts) > 1 else ""

    experience = []
    for exp in struct_json.get("experience") or []:
        start = (exp.get("start_date") or "").strip()
        end = (exp.get("end_date") or "").strip()
        if start and end:
            period = f"{start} \u2013 {end}"
        elif start:
            period = start
        elif end:
            period = end
        else:
            period = ""

        bullets: list[str] = exp.get("bullets") or []
        responsibilities = "\n".join(b for b in bullets if b)

        experience.append({
            "title":            exp.get("title") or "",
            "company":          exp.get("company") or "",
            "period":           period,
            "location":         exp.get("location") or "",
            "industry":         "",  # not captured by parser
            "responsibilities": responsibilities,
            "skills":           [],
        })

    education = []
    for edu in struct_json.get("education") or []:
        education.append({
            "institution": edu.get("institution") or "",
            "degree":      edu.get("degree") or "",
            "field":       edu.get("field") or "",
            "start_date":  edu.get("start_date") or "",
            "end_date":    edu.get("end_date") or "",
        })

    return {
        "name":           name,
        "surname":        surname,
        "email":          struct_json.get("email") or "",
        "phone":          struct_json.get("phone") or "",
        "career_summary": struct_json.get("career_summary") or "",
        "experience":     experience,
        "skills":         list(struct_json.get("skills") or []),
        "education":      education,
        "achievements":   list(struct_json.get("achievements") or []),
    }


def profile_to_library(payload: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Transform ResumePayload content fields to (plain_text, struct_json).

    Inverse of library_to_profile_content. The plain_text is a best-effort
    reconstruction for display and re-parsing. struct_json is the canonical
    structured representation stored in the resumes table.
    """
    name_parts = [payload.get("name") or "", payload.get("surname") or ""]
    full_name = " ".join(p for p in name_parts if p).strip()

    career_summary = (payload.get("career_summary") or "").strip()

    lines: list[str] = []
    if full_name:
        lines.append(full_name)
    email = payload.get("email") or ""
    phone = payload.get("phone") or ""
    if email:
        lines.append(email)
    if phone:
        lines.append(phone)

    if career_summary:
        lines += ["", "SUMMARY", career_summary]

    experience_structs = []
    for exp in payload.get("experience") or []:
        title   = (exp.get("title") or "").strip()
        company = (exp.get("company") or "").strip()
        period  = (exp.get("period") or "").strip()
        location = (exp.get("location") or "").strip()

        # Split period back to start_date / end_date.
        # Split on the dash/dash separator BEFORE normalising to plain hyphens
        # so that ISO dates like "2023-01 – 2025-03" round-trip correctly.
        if "\u2013" in period:          # en-dash
            date_parts = [p.strip() for p in period.split("\u2013", 1)]
        elif "\u2014" in period:        # em-dash
            date_parts = [p.strip() for p in period.split("\u2014", 1)]
        else:
            date_parts = [period.strip()] if period.strip() else []
        start_date = date_parts[0] if date_parts else ""
        end_date   = date_parts[1] if len(date_parts) > 1 else ""

        resp = (exp.get("responsibilities") or "").strip()
        bullets = [b.strip() for b in resp.split("\n") if b.strip()]

        if title or company:
            header = " | ".join(p for p in [title, company, period] if p)
            lines += ["", header]
            if location:
                lines.append(location)
            for b in bullets:
                lines.append(f"\u2022 {b}")

        experience_structs.append({
            "title":      title,
            "company":    company,
            "start_date": start_date,
            "end_date":   end_date,
            "location":   location,
            "bullets":    bullets,
        })

    skills: list[str] = list(payload.get("skills") or [])
    if skills:
        lines += ["", "SKILLS", ", ".join(skills)]

    education_structs = []
    for edu in payload.get("education") or []:
        institution = (edu.get("institution") or "").strip()
        degree      = (edu.get("degree") or "").strip()
        field       = (edu.get("field") or "").strip()
        start_date  = (edu.get("start_date") or "").strip()
        end_date    = (edu.get("end_date") or "").strip()
        if institution or degree:
            label = " ".join(p for p in [degree, field] if p)
            lines.append(f"{label} \u2014 {institution}" if institution else label)
        education_structs.append({
            "institution": institution,
            "degree":      degree,
            "field":       field,
            "start_date":  start_date,
            "end_date":    end_date,
        })

    achievements: list[str] = list(payload.get("achievements") or [])

    struct_json: dict[str, Any] = {
        "name":           full_name,
        "email":          email,
        "phone":          phone,
        "career_summary": career_summary,
        "experience":     experience_structs,
        "skills":         skills,
        "education":      education_structs,
        "achievements":   achievements,
    }

    plain_text = "\n".join(lines).strip()
    return plain_text, struct_json


def make_auto_backup_name(source_name: str) -> str:
    """Generate a timestamped auto-backup name.

    Example: "Auto-backup before Senior Engineer Resume — 2026-04-16"
    """
    today = date.today().isoformat()
    return f"Auto-backup before {source_name} \u2014 {today}"


def blank_fields_on_import(struct_json: dict[str, Any]) -> list[str]:
    """Return content field names that will be blank after a library→profile import.

    Used to warn the user in the confirmation modal so they know what to fill in.
    """
    blank: list[str] = []
    if struct_json.get("experience"):
        # industry is always blank — parser never captures it
        blank.append("experience[].industry")
        # location may be blank for some entries
        if any(not (e.get("location") or "").strip() for e in struct_json["experience"]):
            blank.append("experience[].location")
    return blank
