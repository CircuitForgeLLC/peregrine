# tests/test_mission_domains.py
"""Tests for YAML-driven mission domain configuration."""
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))


# ── load_mission_domains ──────────────────────────────────────────────────────

def test_load_mission_domains_returns_dict(tmp_path: Path) -> None:
    """load_mission_domains parses a valid YAML file into a dict."""
    cfg = tmp_path / "mission_domains.yaml"
    cfg.write_text(
        "domains:\n"
        "  music:\n"
        "    signals: [music, spotify]\n"
        "    default_note: A music note.\n"
    )
    from scripts.generate_cover_letter import load_mission_domains
    result = load_mission_domains(cfg)
    assert "music" in result
    assert result["music"]["signals"] == ["music", "spotify"]
    assert result["music"]["default_note"] == "A music note."


def test_load_mission_domains_missing_file_returns_empty(tmp_path: Path) -> None:
    """load_mission_domains returns {} when the file does not exist."""
    from scripts.generate_cover_letter import load_mission_domains
    result = load_mission_domains(tmp_path / "nonexistent.yaml")
    assert result == {}


def test_load_mission_domains_empty_file_returns_empty(tmp_path: Path) -> None:
    """load_mission_domains returns {} for a blank file."""
    cfg = tmp_path / "mission_domains.yaml"
    cfg.write_text("")
    from scripts.generate_cover_letter import load_mission_domains
    result = load_mission_domains(cfg)
    assert result == {}


# ── detect_mission_alignment ─────────────────────────────────────────────────

def _make_signals(domains: dict[str, dict]) -> dict[str, list[str]]:
    return {d: cfg.get("signals", []) for d, cfg in domains.items()}


def test_detect_returns_note_on_signal_match() -> None:
    """detect_mission_alignment returns the domain note when a signal is present."""
    from scripts.generate_cover_letter import detect_mission_alignment
    notes = {"music": "Music note here."}
    result = detect_mission_alignment("Spotify", "We stream music worldwide.", notes)
    assert result == "Music note here."


def test_detect_returns_none_on_no_match() -> None:
    """detect_mission_alignment returns None when no signal matches."""
    from scripts.generate_cover_letter import detect_mission_alignment
    notes = {"music": "Music note."}
    result = detect_mission_alignment("Acme Corp", "We sell widgets.", notes)
    assert result is None


def test_detect_is_case_insensitive() -> None:
    """Signal matching is case-insensitive (text is lowercased before scan)."""
    from scripts.generate_cover_letter import detect_mission_alignment
    notes = {"animal_welfare": "Animal note."}
    result = detect_mission_alignment("ASPCA", "We care for ANIMALS.", notes)
    assert result == "Animal note."


def test_detect_uses_default_mission_notes_when_none_passed() -> None:
    """detect_mission_alignment uses module-level _MISSION_NOTES when notes=None."""
    from scripts.generate_cover_letter import detect_mission_alignment, _MISSION_DOMAINS
    if "music" not in _MISSION_DOMAINS:
        pytest.skip("music domain not present in loaded config")
    result = detect_mission_alignment("Spotify", "We build music streaming products.")
    assert result is not None
    assert len(result) > 10  # some non-empty hint


# ── _build_mission_notes ─────────────────────────────────────────────────────

def test_build_mission_notes_uses_default_when_no_custom(tmp_path: Path) -> None:
    """_build_mission_notes uses YAML default_note when user has no custom note."""
    cfg = tmp_path / "mission_domains.yaml"
    cfg.write_text(
        "domains:\n"
        "  music:\n"
        "    signals: [music]\n"
        "    default_note: Generic music note.\n"
    )

    class EmptyProfile:
        name = "Test User"
        mission_preferences: dict = {}

    from scripts.generate_cover_letter import load_mission_domains, _build_mission_notes
    import scripts.generate_cover_letter as gcl
    domains_orig = gcl._MISSION_DOMAINS
    signals_orig = gcl._MISSION_SIGNALS
    try:
        gcl._MISSION_DOMAINS = load_mission_domains(cfg)
        gcl._MISSION_SIGNALS = _make_signals(gcl._MISSION_DOMAINS)
        notes = _build_mission_notes(profile=EmptyProfile())
        assert notes["music"] == "Generic music note."
    finally:
        gcl._MISSION_DOMAINS = domains_orig
        gcl._MISSION_SIGNALS = signals_orig


def test_build_mission_notes_uses_custom_note_when_provided(tmp_path: Path) -> None:
    """_build_mission_notes wraps user's custom note in a prompt hint."""
    cfg = tmp_path / "mission_domains.yaml"
    cfg.write_text(
        "domains:\n"
        "  music:\n"
        "    signals: [music]\n"
        "    default_note: Default.\n"
    )

    class FakeProfile:
        name = "Alex"
        mission_preferences = {"music": "I played guitar for 10 years."}

    from scripts.generate_cover_letter import load_mission_domains, _build_mission_notes
    import scripts.generate_cover_letter as gcl
    domains_orig = gcl._MISSION_DOMAINS
    signals_orig = gcl._MISSION_SIGNALS
    try:
        gcl._MISSION_DOMAINS = load_mission_domains(cfg)
        gcl._MISSION_SIGNALS = _make_signals(gcl._MISSION_DOMAINS)
        notes = _build_mission_notes(profile=FakeProfile())
        assert "I played guitar for 10 years." in notes["music"]
        assert "Alex" in notes["music"]
    finally:
        gcl._MISSION_DOMAINS = domains_orig
        gcl._MISSION_SIGNALS = signals_orig


# ── committed config sanity checks ───────────────────────────────────────────

def test_committed_config_has_required_domains() -> None:
    """The committed mission_domains.yaml contains the original 4 domains + 3 new ones."""
    from scripts.generate_cover_letter import _MISSION_DOMAINS
    required = {"music", "animal_welfare", "education", "social_impact", "health",
                "privacy", "accessibility", "open_source"}
    missing = required - set(_MISSION_DOMAINS.keys())
    assert not missing, f"Missing domains in committed config: {missing}"


def test_committed_config_each_domain_has_signals_and_note() -> None:
    """Every domain in the committed config has a non-empty signals list and default_note."""
    from scripts.generate_cover_letter import _MISSION_DOMAINS
    for domain, cfg in _MISSION_DOMAINS.items():
        assert cfg.get("signals"), f"Domain '{domain}' has no signals"
        assert cfg.get("default_note", "").strip(), f"Domain '{domain}' has no default_note"
