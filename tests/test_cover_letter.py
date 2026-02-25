# tests/test_cover_letter.py
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


# ── prepare_training_data tests ──────────────────────────────────────────────

def test_extract_role_from_text():
    """extract_role_from_text pulls the role title from the opening sentence."""
    from scripts.prepare_training_data import extract_role_from_text

    text = "Dear Tailscale Hiring Team,\n\nI'm delighted to apply for the Customer Support Manager position at Tailscale."
    assert extract_role_from_text(text) == "Customer Support Manager"


def test_extract_role_handles_missing():
    """extract_role_from_text returns empty string if no role found."""
    from scripts.prepare_training_data import extract_role_from_text

    assert extract_role_from_text("Dear Team,\n\nHello there.") == ""


def test_extract_company_from_filename():
    """extract_company_from_filename strips 'Cover Letter' suffix."""
    from scripts.prepare_training_data import extract_company_from_filename

    assert extract_company_from_filename("Tailscale Cover Letter") == "Tailscale"
    assert extract_company_from_filename("Dagster Labs Cover Letter.md") == "Dagster Labs"


def test_strip_greeting():
    """strip_greeting removes the 'Dear X,' line and returns the body."""
    from scripts.prepare_training_data import strip_greeting

    text = "Dear Hiring Team,\n\nI'm delighted to apply for the CSM role.\n\nBest regards,\nMeghan"
    result = strip_greeting(text)
    assert result.startswith("I'm delighted")
    assert "Dear" not in result


def test_build_records_from_tmp_corpus(tmp_path):
    """build_records parses a small corpus directory into training records."""
    from scripts.prepare_training_data import build_records

    letter = tmp_path / "Acme Corp Cover Letter.md"
    letter.write_text(
        "Dear Acme Hiring Team,\n\n"
        "I'm delighted to apply for the Director of Customer Success position at Acme Corp. "
        "With six years of experience, I bring strong skills.\n\n"
        "Best regards,\nMeghan McCann"
    )

    records = build_records(tmp_path)
    assert len(records) == 1
    assert "Acme Corp" in records[0]["instruction"]
    assert "Director of Customer Success" in records[0]["instruction"]
    assert records[0]["output"].startswith("I'm delighted")


def test_build_records_skips_empty_files(tmp_path):
    """build_records ignores empty or very short files."""
    from scripts.prepare_training_data import build_records

    (tmp_path / "Empty Cover Letter.md").write_text("")
    (tmp_path / "Tiny Cover Letter.md").write_text("Hi")

    records = build_records(tmp_path)
    assert len(records) == 0


# ── generate_cover_letter tests ───────────────────────────────────────────────

def test_find_similar_letters_returns_top_k():
    """find_similar_letters returns at most top_k entries."""
    from scripts.generate_cover_letter import find_similar_letters

    corpus = [
        {"company": "Acme", "text": "customer success technical account management SaaS"},
        {"company": "Beta", "text": "software engineering backend python"},
        {"company": "Gamma", "text": "customer onboarding enterprise NPS"},
        {"company": "Delta", "text": "customer success manager renewal QBR"},
    ]
    results = find_similar_letters("customer success manager enterprise SaaS", corpus, top_k=2)
    assert len(results) == 2
    # Should prefer customer success companies over software engineering
    companies = [r["company"] for r in results]
    assert "Beta" not in companies


def test_load_corpus_returns_list():
    """load_corpus returns a list (empty if LETTERS_DIR absent) without crashing."""
    from scripts.generate_cover_letter import load_corpus, LETTERS_DIR

    corpus = load_corpus()
    assert isinstance(corpus, list)
    if corpus:
        assert "company" in corpus[0]
        assert "text" in corpus[0]


def test_generate_calls_llm_router():
    """generate() calls the router's complete() and returns its output."""
    from scripts.generate_cover_letter import generate

    fake_corpus = [
        {"company": "Acme", "text": "I'm delighted to apply for the CSM role at Acme."},
    ]
    mock_router = MagicMock()
    mock_router.complete.return_value = "Dear Hiring Team,\n\nI'm delighted to apply.\n\nWarm regards,\nMeghan McCann"

    with patch("scripts.generate_cover_letter.load_corpus", return_value=fake_corpus):
        result = generate("Customer Success Manager", "TestCo", "Looking for a CSM",
                          _router=mock_router)

    mock_router.complete.assert_called_once()
    assert "Meghan McCann" in result
