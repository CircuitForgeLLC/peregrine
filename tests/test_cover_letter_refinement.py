# tests/test_cover_letter_refinement.py
"""
TDD tests for cover letter iterative refinement:
- generate() accepts previous_result + feedback params
- task_runner cover_letter handler passes params through
"""
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))


# ── generate() refinement params ──────────────────────────────────────────────

class TestGenerateRefinement:
    """generate() appends previous_result and feedback to the LLM prompt."""

    def _call_generate(self, previous_result="", feedback=""):
        """Call generate() with a mock router and return the captured prompt."""
        captured = {}
        mock_router = MagicMock()
        mock_router.complete.side_effect = lambda p, **kwargs: (captured.update({"prompt": p}), "result")[1]
        with patch("scripts.generate_cover_letter.load_corpus", return_value=[]), \
             patch("scripts.generate_cover_letter.find_similar_letters", return_value=[]):
            from scripts.generate_cover_letter import generate
            generate(
                "Software Engineer", "Acme",
                previous_result=previous_result,
                feedback=feedback,
                _router=mock_router,
            )
        return captured["prompt"]

    def test_no_refinement_prompt_unchanged(self):
        """When no previous_result or feedback, prompt has no refinement section."""
        prompt = self._call_generate()
        assert "Previous draft" not in prompt
        assert "User feedback" not in prompt

    def test_previous_result_appended(self):
        """previous_result is appended to the prompt."""
        prompt = self._call_generate(previous_result="Old letter text here.")
        assert "Previous draft" in prompt
        assert "Old letter text here." in prompt

    def test_feedback_appended(self):
        """feedback is appended with revision instruction."""
        prompt = self._call_generate(feedback="Make it shorter and punchier.")
        assert "User feedback" in prompt
        assert "Make it shorter and punchier." in prompt
        assert "revise" in prompt.lower()

    def test_both_fields_appended(self):
        """Both previous_result and feedback appear when both supplied."""
        prompt = self._call_generate(
            previous_result="Draft v1 text.",
            feedback="Add more about leadership.",
        )
        assert "Previous draft" in prompt
        assert "Draft v1 text." in prompt
        assert "User feedback" in prompt
        assert "Add more about leadership." in prompt

    def test_empty_strings_ignored(self):
        """Empty string values produce no refinement section."""
        prompt = self._call_generate(previous_result="", feedback="")
        assert "Previous draft" not in prompt
        assert "User feedback" not in prompt


# ── task_runner cover_letter params passthrough ───────────────────────────────

class TestTaskRunnerCoverLetterParams:
    """task_runner passes previous_result and feedback from params JSON to generate()."""

    def _run_cover_letter_task(self, params_json: str | None, job: dict):
        """Invoke _run_task for cover_letter and return captured generate() kwargs."""
        captured = {}

        def mock_generate(title, company, description="", previous_result="", feedback="",
                          is_jobgether=False, _router=None):
            captured.update({
                "title": title, "company": company,
                "previous_result": previous_result, "feedback": feedback,
                "is_jobgether": is_jobgether,
            })
            return "Generated letter"

        with patch("scripts.task_runner.insert_task", return_value=(1, True)), \
             patch("scripts.task_runner.update_task_status"), \
             patch("scripts.task_runner.update_cover_letter"), \
             patch("sqlite3.connect") as mock_conn, \
             patch("scripts.task_runner.generate_cover_letter_fn", mock_generate, create=True):

            import sqlite3
            mock_row = MagicMock()
            mock_row.__iter__ = lambda s: iter(job.items())
            mock_row.keys = lambda: job.keys()
            mock_conn.return_value.__enter__ = MagicMock(return_value=mock_conn.return_value)
            mock_conn.return_value.row_factory = None
            mock_row_factory_row = dict(job)

            conn_mock = MagicMock()
            conn_mock.row_factory = None
            conn_mock.execute.return_value.fetchone.return_value = job
            mock_conn.return_value = conn_mock

            from scripts.task_runner import _run_task
            with patch("scripts.generate_cover_letter.generate", mock_generate):
                _run_task(Path(":memory:"), 1, "cover_letter", job["id"], params_json)

        return captured

    def test_no_params_uses_empty_refinement(self):
        """When params is None, generate() receives empty previous_result and feedback."""
        job = {"id": 1, "title": "Dev", "company": "Corp", "description": "desc"}
        captured = self._run_cover_letter_task(None, job)
        assert captured.get("previous_result", "") == ""
        assert captured.get("feedback", "") == ""

    def test_params_with_feedback_passed_through(self):
        """previous_result and feedback from params JSON are passed to generate()."""
        job = {"id": 1, "title": "Dev", "company": "Corp", "description": "desc"}
        params = json.dumps({
            "previous_result": "Old draft text.",
            "feedback": "Make it more concise.",
        })
        captured = self._run_cover_letter_task(params, job)
        assert captured.get("previous_result") == "Old draft text."
        assert captured.get("feedback") == "Make it more concise."

    def test_empty_params_json_uses_empty_refinement(self):
        """Empty JSON object produces no refinement."""
        job = {"id": 1, "title": "Dev", "company": "Corp", "description": "desc"}
        captured = self._run_cover_letter_task("{}", job)
        assert captured.get("previous_result", "") == ""
        assert captured.get("feedback", "") == ""
