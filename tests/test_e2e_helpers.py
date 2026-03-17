"""Unit tests for E2E harness models and helper utilities."""
import fnmatch
import pytest
from unittest.mock import patch, MagicMock
import time
from tests.e2e.models import ErrorRecord, ModeConfig, diff_errors


def test_error_record_equality():
    a = ErrorRecord(type="exception", message="boom", element_html="<div>boom</div>")
    b = ErrorRecord(type="exception", message="boom", element_html="<div>boom</div>")
    assert a == b


def test_error_record_inequality():
    a = ErrorRecord(type="exception", message="boom", element_html="")
    b = ErrorRecord(type="alert", message="boom", element_html="")
    assert a != b


def test_diff_errors_returns_new_only():
    before = [ErrorRecord("exception", "old error", "")]
    after = [
        ErrorRecord("exception", "old error", ""),
        ErrorRecord("alert", "new error", ""),
    ]
    result = diff_errors(before, after)
    assert result == [ErrorRecord("alert", "new error", "")]


def test_diff_errors_empty_when_no_change():
    errors = [ErrorRecord("exception", "x", "")]
    assert diff_errors(errors, errors) == []


def test_diff_errors_empty_before():
    after = [ErrorRecord("alert", "boom", "")]
    assert diff_errors([], after) == after


def test_mode_config_expected_failure_match():
    config = ModeConfig(
        name="demo",
        base_url="http://localhost:8504",
        auth_setup=lambda ctx: None,
        expected_failures=["Fetch*", "Generate Cover Letter"],
        results_dir=None,
        settings_tabs=["👤 My Profile"],
    )
    assert config.matches_expected_failure("Fetch New Jobs")
    assert config.matches_expected_failure("Generate Cover Letter")
    assert not config.matches_expected_failure("View Jobs")


def test_mode_config_no_expected_failures():
    config = ModeConfig(
        name="local",
        base_url="http://localhost:8502",
        auth_setup=lambda ctx: None,
        expected_failures=[],
        results_dir=None,
        settings_tabs=[],
    )
    assert not config.matches_expected_failure("Fetch New Jobs")
