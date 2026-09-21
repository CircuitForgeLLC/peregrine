"""dev_api's shared LLM helpers for suggestion/generation endpoints.

Regression coverage for: several "return a suggestion" endpoints
(suggest-tags, suggest-search, generate-summary/missions/voice) called
LLMRouter().complete(prompt) with no fallback_order override, so they used
the same chain as primary content generation (cover letters). On an install
where that chain's top ollama-backed entry is a fine-tune specialized for
cover-letter writing, it doesn't reliably follow a "return only JSON"
instruction and these silently returned nothing -- not a crash, just an
empty result with no visible cause.

These endpoints now route through LLMRouter().complete_task("research", ...)
(see tests/test_task_complete_call_sites.py for the per-endpoint error-path
coverage) -- the former _llm_research_complete()/research_fallback_order
helper this file used to test was removed once its last caller was migrated.
The _extract_json_array() parsing helper below is unaffected and still used
by every one of those endpoints.
"""
from unittest.mock import MagicMock, patch


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
