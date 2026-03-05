"""Tests for scripts/suggest_helpers.py."""
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

RESUME_PATH = Path(__file__).parent.parent / "config" / "plain_text_resume.yaml"


# ── _parse_json ───────────────────────────────────────────────────────────────

def test_parse_json_extracts_valid_object():
    from scripts.suggest_helpers import _parse_json
    raw = 'Here is the result: {"a": [1, 2], "b": "hello"} done.'
    assert _parse_json(raw) == {"a": [1, 2], "b": "hello"}


def test_parse_json_returns_empty_on_invalid():
    from scripts.suggest_helpers import _parse_json
    assert _parse_json("no json here") == {}
    assert _parse_json('{"broken": ') == {}


# ── suggest_search_terms ──────────────────────────────────────────────────────

BLOCKLIST = {
    "companies": ["Meta", "Amazon"],
    "industries": ["gambling"],
    "locations": [],
}
USER_PROFILE = {
    "career_summary": "Customer success leader with 10 years in B2B SaaS.",
    "mission_preferences": {
        "animal_welfare": "I volunteer at my local shelter.",
        "education": "",
    },
    "nda_companies": ["Acme Corp"],
}


def _mock_llm(response_dict: dict):
    """Return a patcher that makes LLMRouter().complete() return a JSON string."""
    mock_router = MagicMock()
    mock_router.complete.return_value = json.dumps(response_dict)
    return patch("scripts.suggest_helpers.LLMRouter", return_value=mock_router)


def test_suggest_search_terms_returns_titles_and_excludes():
    from scripts.suggest_helpers import suggest_search_terms
    payload = {"suggested_titles": ["VP Customer Success"], "suggested_excludes": ["cold calling"]}
    with _mock_llm(payload):
        result = suggest_search_terms(["Customer Success Manager"], RESUME_PATH, BLOCKLIST, USER_PROFILE)
    assert result["suggested_titles"] == ["VP Customer Success"]
    assert result["suggested_excludes"] == ["cold calling"]


def test_suggest_search_terms_prompt_contains_blocklist_companies():
    from scripts.suggest_helpers import suggest_search_terms
    with _mock_llm({"suggested_titles": [], "suggested_excludes": []}) as mock_cls:
        suggest_search_terms(["CSM"], RESUME_PATH, BLOCKLIST, USER_PROFILE)
    prompt_sent = mock_cls.return_value.complete.call_args[0][0]
    assert "Meta" in prompt_sent
    assert "Amazon" in prompt_sent


def test_suggest_search_terms_prompt_contains_mission():
    from scripts.suggest_helpers import suggest_search_terms
    with _mock_llm({"suggested_titles": [], "suggested_excludes": []}) as mock_cls:
        suggest_search_terms(["CSM"], RESUME_PATH, BLOCKLIST, USER_PROFILE)
    prompt_sent = mock_cls.return_value.complete.call_args[0][0]
    assert "animal_welfare" in prompt_sent or "animal welfare" in prompt_sent.lower()


def test_suggest_search_terms_prompt_contains_career_summary():
    from scripts.suggest_helpers import suggest_search_terms
    with _mock_llm({"suggested_titles": [], "suggested_excludes": []}) as mock_cls:
        suggest_search_terms(["CSM"], RESUME_PATH, BLOCKLIST, USER_PROFILE)
    prompt_sent = mock_cls.return_value.complete.call_args[0][0]
    assert "Customer success leader" in prompt_sent


def test_suggest_search_terms_returns_empty_on_bad_json():
    from scripts.suggest_helpers import suggest_search_terms
    mock_router = MagicMock()
    mock_router.complete.return_value = "sorry, I cannot help with that"
    with patch("scripts.suggest_helpers.LLMRouter", return_value=mock_router):
        result = suggest_search_terms(["CSM"], RESUME_PATH, BLOCKLIST, USER_PROFILE)
    assert result == {"suggested_titles": [], "suggested_excludes": []}


def test_suggest_search_terms_raises_on_llm_exhausted():
    from scripts.suggest_helpers import suggest_search_terms
    mock_router = MagicMock()
    mock_router.complete.side_effect = RuntimeError("All LLM backends exhausted")
    with patch("scripts.suggest_helpers.LLMRouter", return_value=mock_router):
        with pytest.raises(RuntimeError, match="All LLM backends exhausted"):
            suggest_search_terms(["CSM"], RESUME_PATH, BLOCKLIST, USER_PROFILE)
