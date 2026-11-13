"""The optimizer's approved resume had no name or contact info (peregrine#242): the LLM draft
carries only summary, experience, education, skills and achievements, while the PDF, text and
YAML exports read name/email/phone/linkedin from the same struct. These cover the pure helpers."""
import pytest

from scripts.resume_optimizer import (
    export_pdf,
    format_phone,
    render_resume_text,
    with_identity,
)

PROFILE = {"name": "Pat Example", "email": "pat@example.test", "phone": "5551234567", "linkedin": "https://linkedin.test/in/pat"}
DRAFT = {"career_summary": "Engineer.", "experience": [{"company": "Acme", "title": "Dev", "bullets": ["Built it."]}]}


@pytest.mark.parametrize("raw,expected", [
    ("5551234567", "(555) 123-4567"),
    ("555-123-4567", "(555) 123-4567"),
    ("(555) 123 4567", "(555) 123-4567"),
    ("+1 555 123 4567", "(555) 123-4567"),
    ("15551234567", "(555) 123-4567"),
    ("+44 20 7946 0958", "+44 20 7946 0958"),
    ("ext 12", "ext 12"),
    ("", ""),
    (None, ""),
])
def test_format_phone(raw, expected):
    assert format_phone(raw) == expected


def test_with_identity_adds_the_profile_fields_a_draft_lacks():
    merged = with_identity(DRAFT, PROFILE)

    assert merged["name"] == "Pat Example"
    assert merged["email"] == "pat@example.test"
    assert merged["phone"] == "(555) 123-4567"
    assert merged["linkedin"] == "https://linkedin.test/in/pat"
    assert merged["career_summary"] == "Engineer."


def test_with_identity_does_not_override_values_already_on_the_resume():
    merged = with_identity({**DRAFT, "name": "Patricia E.", "phone": ""}, PROFILE)

    assert merged["name"] == "Patricia E."
    assert merged["phone"] == "(555) 123-4567"


def test_with_identity_does_not_mutate_its_inputs_and_skips_empty_profile_values():
    draft = dict(DRAFT)
    merged = with_identity(draft, {"name": "Pat Example", "email": "", "phone": None, "linkedin": ""})

    assert draft == DRAFT
    assert merged["name"] == "Pat Example"
    assert "email" not in merged and "phone" not in merged and "linkedin" not in merged


def test_the_rendered_text_and_pdf_start_with_the_identity():
    merged = with_identity(DRAFT, PROFILE)

    assert render_resume_text(merged).splitlines()[0].startswith("Pat Example")
    assert "Pat Example" not in render_resume_text(DRAFT)


def test_the_pdf_header_is_drawn(tmp_path):
    import pdfplumber

    out = tmp_path / "r.pdf"
    export_pdf(with_identity(DRAFT, PROFILE), str(out))
    with pdfplumber.open(out) as pdf:
        text = pdf.pages[0].extract_text()

    assert text.splitlines()[0] == "Pat Example"
    assert "pat@example.test" in text.splitlines()[1]
    assert "(555) 123-4567" in text.splitlines()[1]
