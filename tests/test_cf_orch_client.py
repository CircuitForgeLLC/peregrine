"""scripts.cf_orch_client -- thin cf-orch task-allocation client.

Deliberately reimplements the two calls Peregrine needs (POST
/api/inference/task, DELETE the allocation) rather than depending on the
circuitforge-orch package, which bundles the full coordinator server
(fastapi, typer, mcp, psutil) -- far more than a single round trip needs.
See circuitforge-plans/peregrine/superpowers/plans/2026-09-18-cloud-custom-model-cforch-followup.md.
"""
from unittest.mock import MagicMock, patch

import httpx
import pytest

from scripts.cf_orch_client import CfOrchTaskError, complete_via_cf_orch


def _resp(status_code=200, json_data=None, text=""):
    r = MagicMock()
    r.status_code = status_code
    r.is_success = 200 <= status_code < 300
    r.text = text
    r.json.return_value = json_data or {}
    r.raise_for_status = MagicMock()
    if not r.is_success:
        def _raise():
            raise httpx.HTTPStatusError("error", request=MagicMock(), response=r)
        r.raise_for_status.side_effect = _raise
    return r


class TestCompleteViaCfOrch:
    @patch("scripts.cf_orch_client.httpx.delete")
    @patch("scripts.cf_orch_client.httpx.post")
    def test_success_returns_completion_text(self, mock_post, mock_delete):
        alloc = _resp(200, {"url": "http://node1:9000", "allocation_id": "a1", "service": "cf-text"})
        chat = _resp(200, {"choices": [{"message": {"content": "Dear hiring manager..."}}]})
        mock_post.side_effect = [alloc, chat]

        result = complete_via_cf_orch(
            "http://orch.internal", "peregrine", "primary", "write a cover letter",
        )

        assert result == "Dear hiring manager..."

    @patch("scripts.cf_orch_client.httpx.delete")
    @patch("scripts.cf_orch_client.httpx.post")
    def test_includes_user_id_and_model_override_when_set(self, mock_post, mock_delete):
        alloc = _resp(200, {"url": "http://node1:9000", "allocation_id": "a1", "service": "cf-text"})
        chat = _resp(200, {"choices": [{"message": {"content": "ok"}}]})
        mock_post.side_effect = [alloc, chat]

        complete_via_cf_orch(
            "http://orch.internal", "peregrine", "primary", "prompt",
            user_id="11111111-2222-3333-4444-555555555555",
            model_override="meghan-letter-writer-v2",
        )

        alloc_call_body = mock_post.call_args_list[0].kwargs["json"]
        assert alloc_call_body["user_id"] == "11111111-2222-3333-4444-555555555555"
        assert alloc_call_body["model_override"] == "meghan-letter-writer-v2"

    @patch("scripts.cf_orch_client.httpx.delete")
    @patch("scripts.cf_orch_client.httpx.post")
    def test_omits_user_id_and_model_override_when_not_set(self, mock_post, mock_delete):
        alloc = _resp(200, {"url": "http://node1:9000", "allocation_id": "a1", "service": "cf-text"})
        chat = _resp(200, {"choices": [{"message": {"content": "ok"}}]})
        mock_post.side_effect = [alloc, chat]

        complete_via_cf_orch("http://orch.internal", "peregrine", "primary", "prompt")

        alloc_call_body = mock_post.call_args_list[0].kwargs["json"]
        assert "user_id" not in alloc_call_body
        assert "model_override" not in alloc_call_body

    @patch("scripts.cf_orch_client.httpx.delete")
    @patch("scripts.cf_orch_client.httpx.post")
    def test_releases_allocation_after_success(self, mock_post, mock_delete):
        alloc = _resp(200, {"url": "http://node1:9000", "allocation_id": "a1", "service": "cf-text"})
        chat = _resp(200, {"choices": [{"message": {"content": "ok"}}]})
        mock_post.side_effect = [alloc, chat]

        complete_via_cf_orch("http://orch.internal", "peregrine", "primary", "prompt")

        mock_delete.assert_called_once()
        assert "cf-text/allocations/a1" in mock_delete.call_args.args[0]

    @patch("scripts.cf_orch_client.httpx.delete")
    @patch("scripts.cf_orch_client.httpx.post")
    def test_releases_allocation_even_when_inference_call_fails(self, mock_post, mock_delete):
        alloc = _resp(200, {"url": "http://node1:9000", "allocation_id": "a1", "service": "cf-text"})
        broken_chat = _resp(500, text="boom")
        mock_post.side_effect = [alloc, broken_chat]

        with pytest.raises(CfOrchTaskError):
            complete_via_cf_orch("http://orch.internal", "peregrine", "primary", "prompt")

        mock_delete.assert_called_once()

    @patch("scripts.cf_orch_client.httpx.post")
    def test_404_raises_no_assignment_error(self, mock_post):
        mock_post.return_value = _resp(404, text="not found")

        with pytest.raises(CfOrchTaskError, match="No cf-orch assignment"):
            complete_via_cf_orch("http://orch.internal", "peregrine", "primary", "prompt")

    @patch("scripts.cf_orch_client.httpx.post")
    def test_allocation_http_error_raises(self, mock_post):
        mock_post.return_value = _resp(503, text="no capacity")

        with pytest.raises(CfOrchTaskError, match="allocation failed"):
            complete_via_cf_orch("http://orch.internal", "peregrine", "primary", "prompt")

    @patch("scripts.cf_orch_client.httpx.post")
    def test_allocation_with_no_url_raises(self, mock_post):
        mock_post.return_value = _resp(200, {"allocation_id": "a1", "service": "cf-text"})

        with pytest.raises(CfOrchTaskError, match="no service URL"):
            complete_via_cf_orch("http://orch.internal", "peregrine", "primary", "prompt")

    @patch("scripts.cf_orch_client.httpx.post")
    def test_unreachable_orch_raises(self, mock_post):
        mock_post.side_effect = httpx.ConnectError("connection refused")

        with pytest.raises(CfOrchTaskError, match="unreachable"):
            complete_via_cf_orch("http://orch.internal", "peregrine", "primary", "prompt")
