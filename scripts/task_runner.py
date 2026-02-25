# scripts/task_runner.py
"""
Background task runner for LLM generation tasks.

Submitting a task inserts a row in background_tasks and spawns a daemon thread.
The thread calls the appropriate generator, writes results to existing tables,
and marks the task completed or failed.

Deduplication: only one queued/running task per (task_type, job_id) is allowed.
Different task types for the same job run concurrently (e.g. cover letter + research).
"""
import sqlite3
import threading
from pathlib import Path

from scripts.db import (
    DEFAULT_DB,
    insert_task,
    update_task_status,
    update_task_stage,
    update_cover_letter,
    save_research,
)


def submit_task(db_path: Path = DEFAULT_DB, task_type: str = "",
                job_id: int = None,
                params: str | None = None) -> tuple[int, bool]:
    """Submit a background LLM task.

    Returns (task_id, True) if a new task was queued and a thread spawned.
    Returns (existing_id, False) if an identical task is already in-flight.
    """
    task_id, is_new = insert_task(db_path, task_type, job_id or 0, params=params)
    if is_new:
        t = threading.Thread(
            target=_run_task,
            args=(db_path, task_id, task_type, job_id or 0, params),
            daemon=True,
        )
        t.start()
    return task_id, is_new


_WIZARD_PROMPTS: dict[str, str] = {
    "career_summary": (
        "Based on the following resume text, write a concise 2-4 sentence professional "
        "career summary in first person. Focus on years of experience, key skills, and "
        "what makes this person distinctive. Return only the summary text, no labels.\n\n"
        "Resume:\n{resume_text}"
    ),
    "expand_bullets": (
        "Rewrite these rough responsibility notes as polished STAR-format bullet points "
        "(Situation/Task, Action, Result). Each bullet should start with a strong action verb. "
        "Return a JSON array of bullet strings only.\n\nNotes:\n{bullet_notes}"
    ),
    "suggest_skills": (
        "Based on these work experience descriptions, suggest additional skills to add to "
        "a resume. Return a JSON array of skill strings only — no explanations.\n\n"
        "Experience:\n{experience_text}"
    ),
    "voice_guidelines": (
        "Analyze the writing style and tone of this resume and cover letter corpus. "
        "Return 3-5 concise guidelines for maintaining this person's authentic voice in "
        "future cover letters (e.g. 'Uses direct, confident statements'). "
        "Return a JSON array of guideline strings.\n\nContent:\n{content}"
    ),
    "job_titles": (
        "Given these job titles and resume, suggest 5-8 additional job title variations "
        "this person should search for. Return a JSON array of title strings only.\n\n"
        "Current titles: {current_titles}\nResume summary: {resume_text}"
    ),
    "keywords": (
        "Based on this resume and target job titles, suggest important keywords and phrases "
        "to include in job applications. Return a JSON array of keyword strings.\n\n"
        "Titles: {titles}\nResume: {resume_text}"
    ),
    "blocklist": (
        "Based on this resume and job search context, suggest companies, industries, or "
        "keywords to blocklist (avoid in job search results). "
        "Return a JSON array of strings.\n\nContext: {resume_text}"
    ),
    "mission_notes": (
        "Based on this resume, write a short personal note (1-2 sentences) about why this "
        "person might genuinely care about each of these industries: music, animal_welfare, education. "
        "Return a JSON object with those three industry keys and note values. "
        "If the resume shows no clear connection to an industry, set its value to empty string.\n\n"
        "Resume: {resume_text}"
    ),
}


def _run_wizard_generate(section: str, input_data: dict) -> str:
    """Run LLM generation for a wizard section. Returns result string.

    Raises ValueError for unknown sections.
    Raises any LLM exception on failure.
    """
    template = _WIZARD_PROMPTS.get(section)
    if template is None:
        raise ValueError(f"Unknown wizard_generate section: {section!r}")
    # Format the prompt, substituting available keys; unknown placeholders become empty string
    import re as _re

    def _safe_format(tmpl: str, kwargs: dict) -> str:
        """Format template substituting available keys; leaves missing keys as empty string."""
        def replacer(m):
            key = m.group(1)
            return str(kwargs.get(key, ""))
        return _re.sub(r"\{(\w+)\}", replacer, tmpl)

    prompt = _safe_format(template, {k: str(v) for k, v in input_data.items()})
    # Append iterative refinement context if provided
    previous_result = input_data.get("previous_result", "")
    feedback = input_data.get("feedback", "")
    if previous_result:
        prompt += f"\n\n---\nPrevious output:\n{previous_result}"
    if feedback:
        prompt += f"\n\nUser feedback / requested changes:\n{feedback}\n\nPlease revise accordingly."
    from scripts.llm_router import LLMRouter
    return LLMRouter().complete(prompt)


def _run_task(db_path: Path, task_id: int, task_type: str, job_id: int,
              params: str | None = None) -> None:
    """Thread body: run the generator and persist the result."""
    # job_id == 0 means a global task (e.g. discovery) with no associated job row.
    job: dict = {}
    if job_id:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        conn.close()
        if row is None:
            update_task_status(db_path, task_id, "failed", error=f"Job {job_id} not found")
            return
        job = dict(row)

    update_task_status(db_path, task_id, "running")

    try:
        if task_type == "discovery":
            from scripts.discover import run_discovery
            new_count = run_discovery(db_path)
            n = new_count or 0
            update_task_status(
                db_path, task_id, "completed",
                error=f"{n} new listing{'s' if n != 1 else ''} added",
            )
            return

        elif task_type == "cover_letter":
            import json as _json
            p = _json.loads(params or "{}")
            from scripts.generate_cover_letter import generate
            result = generate(
                job.get("title", ""),
                job.get("company", ""),
                job.get("description", ""),
                previous_result=p.get("previous_result", ""),
                feedback=p.get("feedback", ""),
            )
            update_cover_letter(db_path, job_id, result)

        elif task_type == "company_research":
            from scripts.company_research import research_company
            result = research_company(
                job,
                on_stage=lambda s: update_task_stage(db_path, task_id, s),
            )
            save_research(db_path, job_id=job_id, **result)

        elif task_type == "enrich_descriptions":
            from scripts.enrich_descriptions import enrich_all_descriptions
            r = enrich_all_descriptions(db_path)
            errs = len(r.get("errors", []))
            msg = (
                f"{r['succeeded']} description(s) fetched, {r['failed']} failed"
                + (f", {errs} error(s)" if errs else "")
            )
            update_task_status(db_path, task_id, "completed", error=msg)
            return

        elif task_type == "scrape_url":
            from scripts.scrape_url import scrape_job_url
            fields = scrape_job_url(db_path, job_id)
            title = fields.get("title") or job.get("url", "?")
            company = fields.get("company", "")
            msg = f"{title}" + (f" @ {company}" if company else "")
            update_task_status(db_path, task_id, "completed", error=msg)
            # Auto-enrich company/salary for Craigslist jobs
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            job_row = conn.execute(
                "SELECT source, company FROM jobs WHERE id=?", (job_id,)
            ).fetchone()
            conn.close()
            if job_row and job_row["source"] == "craigslist" and not job_row["company"]:
                submit_task(db_path, "enrich_craigslist", job_id)
            return

        elif task_type == "enrich_craigslist":
            from scripts.enrich_descriptions import enrich_craigslist_fields
            extracted = enrich_craigslist_fields(db_path, job_id)
            company = extracted.get("company", "")
            msg = f"company={company}" if company else "no company found"
            update_task_status(db_path, task_id, "completed", error=msg)
            return

        elif task_type == "email_sync":
            try:
                from scripts.imap_sync import sync_all
                result = sync_all(db_path,
                                  on_stage=lambda s: update_task_stage(db_path, task_id, s))
                leads = result.get("new_leads", 0)
                todo  = result.get("todo_attached", 0)
                errs  = len(result.get("errors", []))
                msg = (
                    f"{result['synced']} jobs updated, "
                    f"+{result['inbound']} in, +{result['outbound']} out"
                    + (f", {leads} new lead(s)" if leads else "")
                    + (f", {todo} todo attached" if todo else "")
                    + (f", {errs} error(s)" if errs else "")
                )
                update_task_status(db_path, task_id, "completed", error=msg)
                return
            except FileNotFoundError:
                update_task_status(db_path, task_id, "failed",
                                   error="Email not configured — go to Settings → Email")
                return

        elif task_type == "wizard_generate":
            import json as _json
            p = _json.loads(params or "{}")
            section = p.get("section", "")
            input_data = p.get("input", {})
            if not section:
                raise ValueError("wizard_generate: 'section' key is required in params")
            result = _run_wizard_generate(section, input_data)
            update_task_status(
                db_path, task_id, "completed",
                error=_json.dumps({"section": section, "result": result}),
            )
            return

        else:
            raise ValueError(f"Unknown task_type: {task_type!r}")

        update_task_status(db_path, task_id, "completed")

    except BaseException as exc:
        # BaseException catches SystemExit (from companyScraper sys.exit calls)
        # in addition to regular exceptions.
        update_task_status(db_path, task_id, "failed", error=str(exc))
