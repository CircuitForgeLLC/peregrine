"""generate_cover_letter.generate() -- cloud custom-model-alias routing.

When a cloud managed user has set a custom_model_alias (Settings > System >
Custom Model) and CF_ORCH_URL is configured, the Primary-task completion
should go through cf-orch's task-allocation API with that alias as a
model_override, instead of the local LLMRouter chain. Falls back to the
local router whenever any piece of that (alias, orch URL, or user_id) is
missing -- self-hosted installs never set custom_model_alias, so they are
unaffected by default.
"""
import os
from unittest.mock import MagicMock, patch

import yaml


def _write_user_yaml(path, custom_model_alias=None):
    data = {"name": "Alex Rivera"}
    if custom_model_alias is not None:
        data["custom_model_alias"] = custom_model_alias
    path.write_text(yaml.safe_dump(data))


class TestCoverLetterCfOrchRouting:
    def test_uses_cf_orch_when_alias_url_and_user_id_all_set(self, tmp_path):
        from scripts.generate_cover_letter import generate

        user_yaml = tmp_path / "user.yaml"
        _write_user_yaml(user_yaml, custom_model_alias="meghan-letter-writer-v2")

        with patch("scripts.generate_cover_letter.load_corpus", return_value=[]), \
             patch.dict(os.environ, {"CF_ORCH_URL": "http://orch.internal"}), \
             patch("scripts.generate_cover_letter.complete_via_cf_orch") as mock_cf_orch:
            mock_cf_orch.return_value = "Dear Hiring Team,\n\nCustom model output.\n\nBest,\nAlex"
            result = generate(
                "Customer Success Manager", "TestCo", "Looking for a CSM",
                user_yaml_path=user_yaml, user_id="11111111-2222-3333-4444-555555555555",
            )

        mock_cf_orch.assert_called_once()
        _, kwargs = mock_cf_orch.call_args
        assert mock_cf_orch.call_args.args[1] == "peregrine"
        assert mock_cf_orch.call_args.args[2] == "primary"
        assert kwargs["user_id"] == "11111111-2222-3333-4444-555555555555"
        assert kwargs["model_override"] == "meghan-letter-writer-v2"
        assert "Custom model output" in result

    def test_falls_back_to_local_router_when_no_alias_set(self, tmp_path):
        from scripts.generate_cover_letter import generate

        user_yaml = tmp_path / "user.yaml"
        _write_user_yaml(user_yaml, custom_model_alias="")

        mock_router = MagicMock()
        mock_router.complete_task.return_value = "Dear Hiring Team,\n\nDefault model output.\n\nBest,\nAlex"

        with patch("scripts.generate_cover_letter.load_corpus", return_value=[]), \
             patch.dict(os.environ, {"CF_ORCH_URL": "http://orch.internal"}), \
             patch("scripts.generate_cover_letter.complete_via_cf_orch") as mock_cf_orch:
            result = generate(
                "Customer Success Manager", "TestCo", "Looking for a CSM",
                user_yaml_path=user_yaml, user_id="11111111-2222-3333-4444-555555555555",
                _router=mock_router,
            )

        mock_cf_orch.assert_not_called()
        mock_router.complete_task.assert_called_once()
        assert "Default model output" in result

    def test_falls_back_to_local_router_when_orch_url_not_configured(self, tmp_path):
        from scripts.generate_cover_letter import generate

        user_yaml = tmp_path / "user.yaml"
        _write_user_yaml(user_yaml, custom_model_alias="meghan-letter-writer-v2")

        mock_router = MagicMock()
        mock_router.complete_task.return_value = "Dear Hiring Team,\n\nDefault model output.\n\nBest,\nAlex"

        with patch("scripts.generate_cover_letter.load_corpus", return_value=[]), \
             patch.dict(os.environ, {"CF_ORCH_URL": ""}), \
             patch("scripts.generate_cover_letter.complete_via_cf_orch") as mock_cf_orch:
            result = generate(
                "Customer Success Manager", "TestCo", "Looking for a CSM",
                user_yaml_path=user_yaml, user_id="11111111-2222-3333-4444-555555555555",
                _router=mock_router,
            )

        mock_cf_orch.assert_not_called()
        mock_router.complete_task.assert_called_once()
        assert "Default model output" in result

    def test_falls_back_to_local_router_when_no_user_id(self, tmp_path):
        from scripts.generate_cover_letter import generate

        user_yaml = tmp_path / "user.yaml"
        _write_user_yaml(user_yaml, custom_model_alias="meghan-letter-writer-v2")

        mock_router = MagicMock()
        mock_router.complete_task.return_value = "Dear Hiring Team,\n\nDefault model output.\n\nBest,\nAlex"

        with patch("scripts.generate_cover_letter.load_corpus", return_value=[]), \
             patch.dict(os.environ, {"CF_ORCH_URL": "http://orch.internal"}), \
             patch("scripts.generate_cover_letter.complete_via_cf_orch") as mock_cf_orch:
            result = generate(
                "Customer Success Manager", "TestCo", "Looking for a CSM",
                user_yaml_path=user_yaml, _router=mock_router,
            )

        mock_cf_orch.assert_not_called()
        mock_router.complete_task.assert_called_once()
        assert "Default model output" in result

    def test_cf_orch_failure_raises_friendly_runtime_error(self, tmp_path):
        from scripts.cf_orch_client import CfOrchTaskError
        from scripts.generate_cover_letter import generate

        user_yaml = tmp_path / "user.yaml"
        _write_user_yaml(user_yaml, custom_model_alias="meghan-letter-writer-v2")

        with patch("scripts.generate_cover_letter.load_corpus", return_value=[]), \
             patch.dict(os.environ, {"CF_ORCH_URL": "http://orch.internal"}), \
             patch("scripts.generate_cover_letter.complete_via_cf_orch") as mock_cf_orch:
            mock_cf_orch.side_effect = CfOrchTaskError("no capacity")
            try:
                generate(
                    "Customer Success Manager", "TestCo", "Looking for a CSM",
                    user_yaml_path=user_yaml, user_id="11111111-2222-3333-4444-555555555555",
                )
                assert False, "expected RuntimeError"
            except RuntimeError as e:
                assert "custom model" in str(e).lower()
