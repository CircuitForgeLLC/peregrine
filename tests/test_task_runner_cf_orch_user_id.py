"""task_runner._run_task's cover_letter branch -- derives the cloud tenant's
user_id from the db_path shape (<CLOUD_DATA_ROOT>/<user_id>/peregrine/staging.db)
and passes it through to generate_cover_letter.generate() so cf-orch routing
(custom_model_alias) can identify the caller. Self-hosted db paths don't match
that shape, so user_id comes through as None -- generate() already falls back
to the local router whenever user_id is missing.
"""
from unittest.mock import patch


def _make_db(tmp_path, nested=False):
    from scripts.db import init_db, insert_job
    if nested:
        db_dir = tmp_path / "11111111-2222-3333-4444-555555555555" / "peregrine"
        db_dir.mkdir(parents=True)
        db = db_dir / "staging.db"
    else:
        db = tmp_path / "test.db"
    init_db(db)
    job_id = insert_job(db, {
        "title": "CSM", "company": "Acme", "url": "https://ex.com/1",
        "source": "linkedin", "location": "Remote", "is_remote": True,
        "salary": "", "description": "Great role.", "date_found": "2026-02-20",
    })
    return db, job_id


class TestCoverLetterUserIdDerivation:
    def test_passes_user_id_for_cloud_shaped_db_path(self, tmp_path):
        from scripts.db import insert_task
        from scripts.task_runner import _run_task

        db, job_id = _make_db(tmp_path, nested=True)
        task_id, _ = insert_task(db, "cover_letter", job_id)

        with patch("scripts.generate_cover_letter.generate", return_value="Dear Hiring Manager,") as mock_gen:
            _run_task(db, task_id, "cover_letter", job_id)

        assert mock_gen.call_args.kwargs["user_id"] == "11111111-2222-3333-4444-555555555555"

    def test_passes_none_user_id_for_self_hosted_db_path(self, tmp_path):
        from scripts.db import insert_task
        from scripts.task_runner import _run_task

        db, job_id = _make_db(tmp_path, nested=False)
        task_id, _ = insert_task(db, "cover_letter", job_id)

        with patch("scripts.generate_cover_letter.generate", return_value="Dear Hiring Manager,") as mock_gen:
            _run_task(db, task_id, "cover_letter", job_id)

        assert mock_gen.call_args.kwargs["user_id"] is None
