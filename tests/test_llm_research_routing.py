"""dev_api's shared LLM helpers for suggestion/generation endpoints.

Regression coverage for: several "return a suggestion" endpoints
(suggest-tags, suggest-search, generate-summary/missions/voice) called
LLMRouter().complete(prompt) with no fallback_order override, so they used
the same chain as primary content generation (cover letters). On an install
where that chain's top ollama-backed entry is a fine-tune specialized for
cover-letter writing, it doesn't reliably follow a "return only JSON"
instruction and these silently returned nothing -- not a crash, just an
empty result with no visible cause. All of these now route through
research_fallback_order via _llm_research_complete(), matching the existing
convention in company_research.py and survey_assistant.py.
"""
from unittest.mock import MagicMock, patch


def test_llm_research_complete_passes_research_fallback_order():
    import dev_api

    fake_router = MagicMock()
    fake_router.config = {
        "fallback_order": ["ollama"],
        "research_fallback_order": ["ollama_research", "cf_text"],
    }
    fake_router.complete.return_value = "the result"

    with patch("scripts.llm_router.LLMRouter", return_value=fake_router):
        result = dev_api._llm_research_complete("suggest some skills")

    assert result == "the result"
    fake_router.complete.assert_called_once_with(
        "suggest some skills", system=None, fallback_order=["ollama_research", "cf_text"]
    )


def test_llm_research_complete_falls_back_to_default_chain_when_unset():
    import dev_api

    fake_router = MagicMock()
    fake_router.config = {"fallback_order": ["ollama"]}  # no research_fallback_order key
    fake_router.complete.return_value = "ok"

    with patch("scripts.llm_router.LLMRouter", return_value=fake_router):
        dev_api._llm_research_complete("prompt")

    fake_router.complete.assert_called_once_with("prompt", system=None, fallback_order=["ollama"])


def test_extract_json_array_parses_array_with_surrounding_prose():
    import dev_api

    raw = 'Sure, here you go:\n["Python", "Docker"]\nHope that helps!'
    assert dev_api._extract_json_array(raw) == ["Python", "Docker"]


def test_extract_json_array_returns_none_when_llm_ignored_the_format():
    import dev_api

    # This is the exact failure mode that made the Suggest button look
    # completely broken: a fine-tuned model returning empty/non-JSON prose
    # for a "return only a JSON array" instruction.
    assert dev_api._extract_json_array("") is None
    assert dev_api._extract_json_array("I don't have enough information to suggest anything.") is None


def test_extract_json_array_returns_none_on_malformed_json():
    import dev_api

    assert dev_api._extract_json_array("[not, valid, json") is None
