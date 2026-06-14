"""Tests for AI interview wizard endpoints (POST /api/wizard/ai/*)."""
import json
import sys
import yaml
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

# ── Path bootstrap ────────────────────────────────────────────────────────────
_REPO = Path(__file__).parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))


@pytest.fixture(scope="module")
def client():
    from dev_api import app
    from fastapi.testclient import TestClient
    return TestClient(app)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _write_user_yaml(path: Path, data: dict | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = data if data is not None else {}
    path.write_text(yaml.dump(payload, allow_unicode=True, default_flow_style=False))


def _read_user_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text()) or {}


# ── GET /api/config/app — byokUnlocked field ──────────────────────────────────

class TestAppConfigByokField:
    def test_byok_unlocked_false_when_no_llm_configured(self, client, tmp_path):
        yaml_path = tmp_path / "config" / "user.yaml"
        _write_user_yaml(yaml_path, {"wizard_complete": True})
        with patch("dev_api._user_yaml_path", return_value=str(yaml_path)):
            with patch("app.wizard.tiers.has_configured_llm", return_value=False):
                r = client.get("/api/config/app")
        assert r.status_code == 200
        assert r.json()["byokUnlocked"] is False

    def test_byok_unlocked_true_when_llm_configured(self, client, tmp_path):
        yaml_path = tmp_path / "config" / "user.yaml"
        _write_user_yaml(yaml_path, {"wizard_complete": True})
        with patch("dev_api._user_yaml_path", return_value=str(yaml_path)):
            with patch("app.wizard.tiers.has_configured_llm", return_value=True):
                r = client.get("/api/config/app")
        assert r.status_code == 200
        assert r.json()["byokUnlocked"] is True


# ── POST /api/wizard/ai/interview — tier gate ─────────────────────────────────

class TestWizardAIInterviewTierGate:
    def test_returns_402_when_tier_blocked(self, client):
        """Free tier with no BYOK: expect 402."""
        with patch("dev_api._get_effective_tier", return_value="free"):
            with patch("app.wizard.tiers.has_configured_llm", return_value=False):
                r = client.post(
                    "/api/wizard/ai/interview",
                    json={"history": [{"role": "user", "content": "Hello"}]},
                )
        assert r.status_code == 402
        assert r.json()["detail"]["error"] == "tier_required"

    def test_returns_402_for_free_tier_without_byok(self, client):
        """Explicit check that free tier without LLM configured is gated."""
        with patch("dev_api._get_effective_tier", return_value="free"):
            with patch("app.wizard.tiers.has_configured_llm", return_value=False):
                r = client.post(
                    "/api/wizard/ai/interview",
                    json={"history": [], "profile_so_far": {}},
                )
        assert r.status_code == 402

    def test_free_tier_with_byok_is_allowed(self, client):
        """Free tier with BYOK configured: tier gate passes (mocked LLM response)."""
        llm_reply = json.dumps({
            "reply": "Hello! What's your name?",
            "extracted_fields": {},
            "complete": False,
        })
        with patch("dev_api._get_effective_tier", return_value="free"):
            with patch("app.wizard.tiers.has_configured_llm", return_value=True):
                with patch("scripts.llm_router.LLMRouter") as mock_cls:
                    mock_cls.return_value.complete.return_value = llm_reply
                    r = client.post(
                        "/api/wizard/ai/interview",
                        json={"history": [], "profile_so_far": {}},
                    )
        assert r.status_code == 200


# ── POST /api/wizard/ai/interview — LLM mocked responses ─────────────────────

class TestWizardAIInterviewLLM:
    def _paid_byok_patches(self):
        """Context managers for paid tier + BYOK."""
        return (
            patch("dev_api._get_effective_tier", return_value="paid"),
            patch("app.wizard.tiers.has_configured_llm", return_value=True),
        )

    def test_returns_valid_reply_structure(self, client):
        llm_reply = json.dumps({
            "reply": "Great to meet you! What's your preferred contact email?",
            "extracted_fields": {"name": "Alex Rivera"},
            "complete": False,
        })
        with patch("dev_api._get_effective_tier", return_value="paid"):
            with patch("app.wizard.tiers.has_configured_llm", return_value=True):
                with patch("scripts.llm_router.LLMRouter") as mock_cls:
                    mock_cls.return_value.complete.return_value = llm_reply
                    r = client.post(
                        "/api/wizard/ai/interview",
                        json={
                            "history": [
                                {"role": "user", "content": "My name is Alex Rivera"},
                            ],
                        },
                    )
        assert r.status_code == 200
        body = r.json()
        assert body["reply"] == "Great to meet you! What's your preferred contact email?"
        assert body["extracted_fields"] == {"name": "Alex Rivera"}
        assert body["complete"] is False

    def test_returns_complete_true_when_llm_signals_done(self, client):
        llm_reply = json.dumps({
            "reply": "You're all set! Your profile is complete.",
            "extracted_fields": {
                "name": "Alex",
                "email": "alex@example.com",
                "career_summary": "Backend engineer with 5 years experience.",
            },
            "complete": True,
        })
        with patch("dev_api._get_effective_tier", return_value="paid"):
            with patch("app.wizard.tiers.has_configured_llm", return_value=True):
                with patch("scripts.llm_router.LLMRouter") as mock_cls:
                    mock_cls.return_value.complete.return_value = llm_reply
                    r = client.post(
                        "/api/wizard/ai/interview",
                        json={
                            "history": [
                                {"role": "user", "content": "I'm done"},
                            ],
                        },
                    )
        assert r.status_code == 200
        body = r.json()
        assert body["complete"] is True
        assert "name" in body["extracted_fields"]

    def test_fallback_when_llm_returns_non_json(self, client):
        """If LLM returns non-JSON, the endpoint still returns 200 with raw reply."""
        with patch("dev_api._get_effective_tier", return_value="paid"):
            with patch("app.wizard.tiers.has_configured_llm", return_value=True):
                with patch("scripts.llm_router.LLMRouter") as mock_cls:
                    mock_cls.return_value.complete.return_value = "Hello, what is your name?"
                    r = client.post(
                        "/api/wizard/ai/interview",
                        json={"history": []},
                    )
        assert r.status_code == 200
        body = r.json()
        assert body["reply"] == "Hello, what is your name?"
        assert body["extracted_fields"] == {}
        assert body["complete"] is False

    def test_history_passed_to_llm(self, client):
        """Verify the history turns are included in the prompt sent to the LLM."""
        llm_reply = json.dumps({"reply": "OK", "extracted_fields": {}, "complete": False})
        captured_calls = []
        with patch("dev_api._get_effective_tier", return_value="paid"):
            with patch("app.wizard.tiers.has_configured_llm", return_value=True):
                with patch("scripts.llm_router.LLMRouter") as mock_cls:
                    mock_cls.return_value.complete.side_effect = (
                        lambda prompt, system=None: (captured_calls.append(prompt) or llm_reply)
                    )
                    client.post(
                        "/api/wizard/ai/interview",
                        json={
                            "history": [
                                {"role": "user", "content": "I am Alex"},
                                {"role": "assistant", "content": "Nice to meet you Alex!"},
                                {"role": "user", "content": "My email is alex@test.com"},
                            ],
                        },
                    )
        assert len(captured_calls) == 1
        prompt = captured_calls[0]
        assert "I am Alex" in prompt
        assert "alex@test.com" in prompt

    def test_profile_so_far_injected_into_prompt(self, client):
        """profile_so_far fields must appear in the prompt sent to the LLM."""
        llm_reply = json.dumps({"reply": "Got it!", "extracted_fields": {}, "complete": False})
        captured_calls = []
        with patch("dev_api._get_effective_tier", return_value="paid"):
            with patch("app.wizard.tiers.has_configured_llm", return_value=True):
                with patch("scripts.llm_router.LLMRouter") as mock_cls:
                    mock_cls.return_value.complete.side_effect = (
                        lambda prompt, system=None: (captured_calls.append(prompt) or llm_reply)
                    )
                    client.post(
                        "/api/wizard/ai/interview",
                        json={
                            "history": [
                                {"role": "user", "content": "I am Alex"},
                            ],
                            "profile_so_far": {
                                "name": "Alex Rivera",
                                "email": "alex@example.com",
                            },
                        },
                    )
        assert len(captured_calls) == 1
        prompt = captured_calls[0]
        assert "Alex Rivera" in prompt
        assert "alex@example.com" in prompt

    def test_llm_error_returns_500(self, client):
        """If LLM raises, the endpoint returns 500."""
        with patch("dev_api._get_effective_tier", return_value="paid"):
            with patch("app.wizard.tiers.has_configured_llm", return_value=True):
                with patch("scripts.llm_router.LLMRouter") as mock_cls:
                    mock_cls.return_value.complete.side_effect = RuntimeError("no backends")
                    r = client.post(
                        "/api/wizard/ai/interview",
                        json={"history": [{"role": "user", "content": "hi"}]},
                    )
        assert r.status_code == 500


# ── POST /api/wizard/ai/finalize ──────────────────────────────────────────────

class TestWizardAIFinalize:
    def test_merges_allowed_fields_into_user_yaml(self, client, tmp_path):
        yaml_path = tmp_path / "config" / "user.yaml"
        _write_user_yaml(yaml_path, {"tier": "paid", "wizard_complete": True})
        with patch("dev_api._user_yaml_path", return_value=str(yaml_path)):
            r = client.post(
                "/api/wizard/ai/finalize",
                json={
                    "profile": {
                        "name": "Jordan Lee",
                        "email": "jordan@example.com",
                        "career_summary": "Full-stack developer with 8 years experience.",
                        "candidate_voice": "warm and conversational",
                    }
                },
            )
        assert r.status_code == 200
        body = r.json()
        assert body["saved"] is True
        assert set(body["fields"]) == {"name", "email", "career_summary", "candidate_voice"}

        saved = _read_user_yaml(yaml_path)
        assert saved["name"] == "Jordan Lee"
        assert saved["email"] == "jordan@example.com"
        assert saved["career_summary"] == "Full-stack developer with 8 years experience."
        assert saved["candidate_voice"] == "warm and conversational"

    def test_does_not_clobber_existing_non_wizard_keys(self, client, tmp_path):
        """Keys like tier, wizard_complete must not be overwritten by finalize."""
        yaml_path = tmp_path / "config" / "user.yaml"
        _write_user_yaml(yaml_path, {
            "tier": "premium",
            "wizard_complete": True,
            "inference_profile": "single-gpu",
        })
        with patch("dev_api._user_yaml_path", return_value=str(yaml_path)):
            r = client.post(
                "/api/wizard/ai/finalize",
                json={
                    "profile": {
                        "name": "Sam Park",
                        "tier": "free",          # attempt to downgrade — must be blocked
                        "wizard_complete": False,  # attempt to reset — must be blocked
                    }
                },
            )
        assert r.status_code == 200
        saved = _read_user_yaml(yaml_path)
        # Non-wizard keys are preserved
        assert saved["tier"] == "premium"
        assert saved["wizard_complete"] is True
        assert saved["inference_profile"] == "single-gpu"
        # Allowed wizard key is written
        assert saved["name"] == "Sam Park"

    def test_unknown_keys_are_silently_ignored(self, client, tmp_path):
        yaml_path = tmp_path / "config" / "user.yaml"
        _write_user_yaml(yaml_path, {})
        with patch("dev_api._user_yaml_path", return_value=str(yaml_path)):
            r = client.post(
                "/api/wizard/ai/finalize",
                json={
                    "profile": {
                        "email": "test@example.com",
                        "injected_field": "should be ignored",
                        "admin": True,
                    }
                },
            )
        assert r.status_code == 200
        saved = _read_user_yaml(yaml_path)
        assert saved["email"] == "test@example.com"
        assert "injected_field" not in saved
        assert "admin" not in saved

    def test_all_allowed_fields_are_written(self, client, tmp_path):
        """All allowed wizard fields are accepted when provided."""
        yaml_path = tmp_path / "config" / "user.yaml"
        _write_user_yaml(yaml_path, {})
        full_profile = {
            "name": "Casey Morgan",
            "email": "casey@example.com",
            "career_summary": "Designer turned product manager.",
            "candidate_voice": "professional and direct",
            "mission_preferences": ["education", "social_impact"],
            "candidate_accessibility_focus": True,
            "candidate_lgbtq_focus": True,
            "linkedin": "https://linkedin.com/in/casey",
        }
        with patch("dev_api._user_yaml_path", return_value=str(yaml_path)):
            r = client.post("/api/wizard/ai/finalize", json={"profile": full_profile})
        assert r.status_code == 200
        saved = _read_user_yaml(yaml_path)
        for key, value in full_profile.items():
            assert saved[key] == value, f"Expected {key}={value!r}, got {saved.get(key)!r}"

    def test_empty_profile_returns_saved_true(self, client, tmp_path):
        yaml_path = tmp_path / "config" / "user.yaml"
        _write_user_yaml(yaml_path, {"name": "Existing"})
        with patch("dev_api._user_yaml_path", return_value=str(yaml_path)):
            r = client.post("/api/wizard/ai/finalize", json={"profile": {}})
        assert r.status_code == 200
        assert r.json()["saved"] is True
        assert r.json()["fields"] == []
        # Existing data is preserved
        assert _read_user_yaml(yaml_path)["name"] == "Existing"

    def test_mission_preferences_list_written_correctly(self, client, tmp_path):
        yaml_path = tmp_path / "config" / "user.yaml"
        _write_user_yaml(yaml_path, {})
        with patch("dev_api._user_yaml_path", return_value=str(yaml_path)):
            r = client.post(
                "/api/wizard/ai/finalize",
                json={"profile": {"mission_preferences": ["music", "animal_welfare"]}},
            )
        assert r.status_code == 200
        saved = _read_user_yaml(yaml_path)
        assert saved["mission_preferences"] == ["music", "animal_welfare"]
