"""Unit tests for scripts.resume_sync — format transform between library and profile."""
import json
import pytest
from scripts.resume_sync import (
    library_to_profile_content,
    profile_to_library,
    make_auto_backup_name,
    blank_fields_on_import,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────

STRUCT_JSON = {
    "name": "Alex Rivera",
    "email": "alex@example.com",
    "phone": "555-0100",
    "career_summary": "Senior UX Designer with 6 years experience.",
    "experience": [
        {
            "title": "Senior UX Designer",
            "company": "StreamNote",
            "start_date": "2023",
            "end_date": "present",
            "location": "Remote",
            "bullets": ["Led queue redesign", "Built component library"],
        }
    ],
    "education": [
        {
            "institution": "State University",
            "degree": "B.F.A.",
            "field": "Graphic Design",
            "start_date": "2015",
            "end_date": "2019",
        }
    ],
    "skills": ["Figma", "User Research"],
    "achievements": ["Design award 2024"],
}

PROFILE_PAYLOAD = {
    "name": "Alex",
    "surname": "Rivera",
    "email": "alex@example.com",
    "phone": "555-0100",
    "career_summary": "Senior UX Designer with 6 years experience.",
    "experience": [
        {
            "title": "Senior UX Designer",
            "company": "StreamNote",
            "period": "2023 – present",
            "location": "Remote",
            "industry": "",
            "responsibilities": "Led queue redesign\nBuilt component library",
            "skills": [],
        }
    ],
    "education": [
        {
            "institution": "State University",
            "degree": "B.F.A.",
            "field": "Graphic Design",
            "start_date": "2015",
            "end_date": "2019",
        }
    ],
    "skills": ["Figma", "User Research"],
    "achievements": ["Design award 2024"],
}


# ── library_to_profile_content ────────────────────────────────────────────────

def test_library_to_profile_splits_name():
    result = library_to_profile_content(STRUCT_JSON)
    assert result["name"] == "Alex"
    assert result["surname"] == "Rivera"

def test_library_to_profile_single_word_name():
    result = library_to_profile_content({**STRUCT_JSON, "name": "Cher"})
    assert result["name"] == "Cher"
    assert result["surname"] == ""

def test_library_to_profile_email_phone():
    result = library_to_profile_content(STRUCT_JSON)
    assert result["email"] == "alex@example.com"
    assert result["phone"] == "555-0100"

def test_library_to_profile_career_summary():
    result = library_to_profile_content(STRUCT_JSON)
    assert result["career_summary"] == "Senior UX Designer with 6 years experience."

def test_library_to_profile_experience_period():
    result = library_to_profile_content(STRUCT_JSON)
    assert result["experience"][0]["period"] == "2023 – present"

def test_library_to_profile_experience_bullets_joined():
    result = library_to_profile_content(STRUCT_JSON)
    assert result["experience"][0]["responsibilities"] == "Led queue redesign\nBuilt component library"

def test_library_to_profile_experience_industry_blank():
    result = library_to_profile_content(STRUCT_JSON)
    assert result["experience"][0]["industry"] == ""

def test_library_to_profile_education():
    result = library_to_profile_content(STRUCT_JSON)
    assert result["education"][0]["institution"] == "State University"
    assert result["education"][0]["degree"] == "B.F.A."

def test_library_to_profile_skills():
    result = library_to_profile_content(STRUCT_JSON)
    assert result["skills"] == ["Figma", "User Research"]

def test_library_to_profile_achievements():
    result = library_to_profile_content(STRUCT_JSON)
    assert result["achievements"] == ["Design award 2024"]

def test_library_to_profile_missing_fields_no_keyerror():
    result = library_to_profile_content({})
    assert result["name"] == ""
    assert result["experience"] == []
    assert result["education"] == []
    assert result["skills"] == []
    assert result["achievements"] == []


# ── profile_to_library ────────────────────────────────────────────────────────

def test_profile_to_library_full_name():
    text, struct = profile_to_library(PROFILE_PAYLOAD)
    assert struct["name"] == "Alex Rivera"

def test_profile_to_library_experience_bullets_reconstructed():
    _, struct = profile_to_library(PROFILE_PAYLOAD)
    assert struct["experience"][0]["bullets"] == ["Led queue redesign", "Built component library"]

def test_profile_to_library_period_split():
    _, struct = profile_to_library(PROFILE_PAYLOAD)
    assert struct["experience"][0]["start_date"] == "2023"
    assert struct["experience"][0]["end_date"] == "present"

def test_profile_to_library_period_split_iso_dates():
    """ISO dates (with hyphens) must round-trip through the period field correctly."""
    payload = {
        **PROFILE_PAYLOAD,
        "experience": [{
            **PROFILE_PAYLOAD["experience"][0],
            "period": "2023-01 \u2013 2025-03",
        }],
    }
    _, struct = profile_to_library(payload)
    assert struct["experience"][0]["start_date"] == "2023-01"
    assert struct["experience"][0]["end_date"] == "2025-03"

def test_profile_to_library_period_split_em_dash():
    """Em-dash separator is also handled."""
    payload = {
        **PROFILE_PAYLOAD,
        "experience": [{
            **PROFILE_PAYLOAD["experience"][0],
            "period": "2022-06 \u2014 2023-12",
        }],
    }
    _, struct = profile_to_library(payload)
    assert struct["experience"][0]["start_date"] == "2022-06"
    assert struct["experience"][0]["end_date"] == "2023-12"

def test_profile_to_library_education_round_trip():
    _, struct = profile_to_library(PROFILE_PAYLOAD)
    assert struct["education"][0]["institution"] == "State University"

def test_profile_to_library_plain_text_contains_name():
    text, _ = profile_to_library(PROFILE_PAYLOAD)
    assert "Alex Rivera" in text

def test_profile_to_library_plain_text_contains_summary():
    text, _ = profile_to_library(PROFILE_PAYLOAD)
    assert "Senior UX Designer" in text

def test_profile_to_library_empty_payload_no_crash():
    text, struct = profile_to_library({})
    assert isinstance(text, str)
    assert isinstance(struct, dict)


# ── make_auto_backup_name ─────────────────────────────────────────────────────

def test_backup_name_format():
    name = make_auto_backup_name("Senior Engineer Resume")
    import re
    assert re.match(r"Auto-backup before Senior Engineer Resume — \d{4}-\d{2}-\d{2}", name)


# ── blank_fields_on_import ────────────────────────────────────────────────────

def test_blank_fields_industry_always_listed():
    result = blank_fields_on_import(STRUCT_JSON)
    assert "experience[].industry" in result

def test_blank_fields_location_listed_when_missing():
    no_loc = {**STRUCT_JSON, "experience": [{**STRUCT_JSON["experience"][0], "location": ""}]}
    result = blank_fields_on_import(no_loc)
    assert "experience[].location" in result

def test_blank_fields_location_not_listed_when_present():
    result = blank_fields_on_import(STRUCT_JSON)
    assert "experience[].location" not in result
