"""Tests for the feedback API backend."""
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path


# ── mask_pii ──────────────────────────────────────────────────────────────────

def test_mask_pii_email():
    from scripts.feedback_api import mask_pii
    assert mask_pii("contact foo@bar.com please") == "contact [email redacted] please"


def test_mask_pii_phone_dashes():
    from scripts.feedback_api import mask_pii
    assert mask_pii("call 555-123-4567 now") == "call [phone redacted] now"


def test_mask_pii_phone_parens():
    from scripts.feedback_api import mask_pii
    assert mask_pii("(555) 867-5309") == "[phone redacted]"


def test_mask_pii_clean_text():
    from scripts.feedback_api import mask_pii
    assert mask_pii("no sensitive data here") == "no sensitive data here"


def test_mask_pii_multiple_emails():
    from scripts.feedback_api import mask_pii
    result = mask_pii("a@b.com and c@d.com")
    assert result == "[email redacted] and [email redacted]"


# ── collect_context ───────────────────────────────────────────────────────────

def test_collect_context_required_keys():
    from scripts.feedback_api import collect_context
    ctx = collect_context("Home")
    for key in ("page", "version", "tier", "llm_backend", "os", "timestamp"):
        assert key in ctx, f"missing key: {key}"


def test_collect_context_page_value():
    from scripts.feedback_api import collect_context
    ctx = collect_context("MyPage")
    assert ctx["page"] == "MyPage"


def test_collect_context_timestamp_is_utc():
    from scripts.feedback_api import collect_context
    ctx = collect_context("X")
    assert ctx["timestamp"].endswith("Z")
