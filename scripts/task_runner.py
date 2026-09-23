# scripts/task_runner.py
"""
Background task runner for LLM generation tasks.

Submitting a task inserts a row in background_tasks and spawns a daemon thread.
The thread calls the appropriate generator, writes results to existing tables,
and marks the task completed or failed.

Deduplication: only one queued/running task per (task_type, job_id) is allowed.
Different task types for the same job run concurrently (e.g. cover letter + research).
"""
import logging
import re
import sqlite3
import threading
from pathlib import Path

log = logging.getLogger(__name__)

_VALID_USER_ID_RE = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.IGNORECASE)


def _resolve_cloud_user_id(db_path) -> str | None:
    """Extract the cloud tenant's user_id from a db_path shaped like
    <CLOUD_DATA_ROOT>/<user_id>/peregrine/staging.db. Returns None for a
    self-hosted db_path (no matching UUID segment) -- callers already treat
    a missing user_id as "use local routing", so this degrades safely.
    """
    try:
        candidate = Path(db_path).parts[-3]
    except IndexError:
        return None
    return candidate if _VALID_USER_ID_RE.match(candidate) else None


def _normalize_aihawk_resume(raw: dict) -> dict:
    """Convert a plain_text_resume.yaml (AIHawk format) into the optimizer struct.

    Handles two AIHawk variants:
    - Newer Peregrine wizard output: already uses bullets/start_date/end_date/career_summary
    - Older raw AIHawk format: uses responsibilities (str), period ("YYYY – Present")
    """
    import re as _re

    def _split_responsibilities(text: str) -> list[str]:
        lines = [ln.strip() for ln in text.strip().splitlines() if ln.strip()]
        return lines if lines else [text.strip()]

    def _parse_period(period: str) -> tuple[str, str]:
        parts = _re.split(r"\s*[–—-]\s*", period, maxsplit=1)
        start = parts[0].strip() if parts else ""
        end = parts[1].strip() if len(parts) > 1 else "Present"
        return start, end

    experience = []
    for entry in raw.get("experience", []):
        if "responsibilities" in entry:
            bullets = _split_responsibilities(entry["responsibilities"])
        else:
            bullets = entry.get("bullets", [])

        if "period" in entry:
            start_date, end_date = _parse_period(entry["period"])
        else:
            start_date = entry.get("start_date", "")
            end_date = entry.get("end_date", "Present")

        experience.append({
            "title": entry.get("title", ""),
            "company": entry.get("company", ""),
            "start_date": start_date,
            "end_date": end_date,
            "bullets": bullets,
        })

    # career_summary may be a string or absent; assessment field is a legacy bool in some profiles
    career_summary = raw.get("career_summary", "")
    if not isinstance(career_summary, str):
        career_summary = ""

    return {
        "career_summary": career_summary,
        "experience": experience,
        "education": raw.get("education", []),
        "skills": raw.get("skills", []),
        "achievements": raw.get("achievements", []),
    }


def _resume_struct_to_text(resume_struct: dict) -> str:
    """Flatten a normalized resume struct (career_summary/experience/education/
    skills/achievements) into plain text for TF-IDF gap matching.

    career_summary alone is frequently empty for AIHawk-format profiles, which
    have no such field -- this pulls in the actual content (experience bullets,
    skills) so gap analysis has something real to compare a job description
    against instead of silently running on an empty string.
    """
    lines: list[str] = []

    summary = resume_struct.get("career_summary", "")
    if isinstance(summary, str) and summary.strip():
        lines.append(summary.strip())

    for entry in resume_struct.get("experience", []) or []:
        if not isinstance(entry, dict):
            continue
        header = " — ".join(p for p in (entry.get("title", ""), entry.get("company", "")) if p)
        if header:
            lines.append(header)
        for bullet in entry.get("bullets", []) or []:
            if isinstance(bullet, str) and bullet.strip():
                lines.append(bullet.strip())

    skills = resume_struct.get("skills", []) or []
    skill_terms = [s if isinstance(s, str) else s.get("name", "") for s in skills]
    skill_terms = [s for s in skill_terms if s]
    if skill_terms:
        lines.append("Skills: " + ", ".join(skill_terms))

    for entry in resume_struct.get("education", []) or []:
        if isinstance(entry, str) and entry.strip():
            lines.append(entry.strip())
        elif isinstance(entry, dict):
            header = " — ".join(
                p for p in (entry.get("degree", ""), entry.get("school", "")) if p
            )
            if header:
                lines.append(header)

    for entry in resume_struct.get("achievements", []) or []:
        if isinstance(entry, str) and entry.strip():
            lines.append(entry.strip())

    return "\n".join(lines)


from scripts.db import (
    DEFAULT_DB,
    insert_task,
    save_optimized_resume,
    save_research,
    update_cover_letter,
    update_task_stage,
    update_task_status,
)


def submit_task(db_path: Path = DEFAULT_DB, task_type: str = "",
                job_id: int | None = None,
                params: str | None = None) -> tuple[int, bool]:
    """Submit a background task.

    LLM task types (cover_letter, company_research, wizard_generate) are routed
    through the TaskScheduler for VRAM-aware batch scheduling.
    All other types spawn a free daemon thread as before.

    Returns (task_id, True) if a new task was queued.
    Returns (existing_id, False) if an identical task is already in-flight.
    """
    task_id, is_new = insert_task(db_path, task_type, job_id or 0, params=params)
    if is_new:
        from scripts.task_scheduler import LLM_TASK_TYPES, get_scheduler
        if task_type in LLM_TASK_TYPES:
            import os as _os
            _cloud_mode = _os.environ.get("CLOUD_MODE", "").lower() in ("1", "true")
            scheduler_db_path = None if _cloud_mode else db_path
            enqueued = get_scheduler(scheduler_db_path, run_task_fn=_run_task).enqueue(
                task_id, task_type, job_id or 0, params, db_path
            )
            if not enqueued:
                update_task_status(
                    db_path, task_id, "failed", error="Queue depth limit reached"
                )
        else:
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
            import os as _os
            if _os.environ.get("DEMO_MODE", "").lower() in ("1", "true", "yes"):
                update_task_status(
                    db_path, task_id, "failed",
                    error="Discovery is disabled in the public demo. Run your own instance to use this feature.",
                )
                return
            from pathlib import Path as _Path

            from scripts.discover import run_discovery
            new_count = run_discovery(db_path, config_dir=_Path(db_path).parent / "config")
            n = new_count or 0
            update_task_status(
                db_path, task_id, "completed",
                error=f"{n} new listing{'s' if n != 1 else ''} added",
            )
            return

        elif task_type == "cover_letter":
            import json as _json
            import os as _os
            p = _json.loads(params or "{}")
            from scripts.generate_cover_letter import generate
            from scripts.llm_router import CONFIG_PATH as LLM_ROUTER_CONFIG_PATH
            from scripts.llm_router import _merged_cloud_llm_config
            _cfg_dir = Path(db_path).parent / "config"
            _user_yaml = _cfg_dir / "user.yaml"
            _cloud_mode = _os.environ.get("CLOUD_MODE", "").lower() in ("1", "true")
            _llm_config_path = _merged_cloud_llm_config(db_path) if _cloud_mode else LLM_ROUTER_CONFIG_PATH
            result = generate(
                job.get("title", ""),
                job.get("company", ""),
                job.get("description", ""),
                previous_result=p.get("previous_result", ""),
                feedback=p.get("feedback", ""),
                is_jobgether=job.get("source") == "jobgether",
                config_path=_llm_config_path,
                user_yaml_path=_user_yaml,
                user_id=_resolve_cloud_user_id(db_path),
            )
            update_cover_letter(db_path, job_id, result)

        elif task_type == "company_research":
            from scripts.company_research import research_company
            from scripts.llm_router import CONFIG_PATH as LLM_ROUTER_CONFIG_PATH
            result = research_company(
                job,
                on_stage=lambda s: update_task_stage(db_path, task_id, s),
                config_path=LLM_ROUTER_CONFIG_PATH,
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

        elif task_type == "resume_optimize":
            import json as _json

            from scripts.resume_optimizer import (
                extract_jd_signals,
                hallucination_check,
                prioritize_gaps,
                rewrite_for_ats,
            )
            from scripts.resume_parser import structure_resume
            from scripts.user_profile import load_user_profile

            _user_yaml = Path(db_path).parent / "config" / "user.yaml"
            description = job.get("description", "")
            resume_path = load_user_profile(str(_user_yaml)).get("resume_path", "")

            # Parse the candidate's resume
            update_task_stage(db_path, task_id, "parsing resume")
            _plain_yaml = Path(db_path).parent / "config" / "plain_text_resume.yaml"
            if resume_path and Path(resume_path).exists():
                resume_text = Path(resume_path).read_text(errors="replace")
                resume_struct, parse_err = structure_resume(resume_text)
                if parse_err:
                    log.warning("[task_runner] resume parse error for task_id=%s: %s", task_id, parse_err)
            elif _plain_yaml.exists():
                import yaml as _yaml
                _raw = _yaml.safe_load(_plain_yaml.read_text(encoding="utf-8")) or {}
                resume_struct = _normalize_aihawk_resume(_raw)
                # career_summary alone is frequently empty for AIHawk-format
                # profiles (no such field in the raw YAML) -- that silently
                # starved extract_jd_signals()'s TF-IDF phase, which requires
                # a non-empty resume_text to run at all. Flatten the full
                # structured resume (summary + experience bullets + skills)
                # into plain text instead, so TF-IDF has real content to
                # compare against regardless of which fields the profile has.
                resume_text = _resume_struct_to_text(resume_struct)
            else:
                resume_text = ""
                resume_struct, _parse_err = structure_resume("")

            # Extract keyword gaps and build gap report (free tier)
            update_task_stage(db_path, task_id, "extracting keyword gaps")
            gaps = extract_jd_signals(description, resume_text, company_name=job.get("company", ""))
            prioritized = prioritize_gaps(gaps, resume_struct)
            gap_report = _json.dumps(prioritized, indent=2)

            # Full rewrite (paid tier only) → enters awaiting_review, not completed
            p = _json.loads(params or "{}")
            selected_gaps = p.get("selected_gaps", None)
            if selected_gaps is not None:
                selected_set = set(selected_gaps)
                prioritized = [g for g in prioritized if g.get("term") in selected_set]
            if p.get("full_rewrite", False):
                update_task_stage(db_path, task_id, "rewriting resume sections")
                candidate_voice = load_user_profile(str(_user_yaml)).get("candidate_voice", "")
                rewritten = rewrite_for_ats(resume_struct, prioritized, job, candidate_voice)
                if hallucination_check(resume_struct, rewritten):
                    from scripts.db import save_resume_draft
                    from scripts.resume_optimizer import build_review_diff
                    draft = build_review_diff(resume_struct, rewritten)
                    # Attach gap report to draft for reference in the review UI
                    draft["gap_report"] = prioritized
                    save_resume_draft(db_path, job_id=job_id,
                                      draft_json=_json.dumps(draft))
                    # Save gap report now; final text written after user review
                    save_optimized_resume(db_path, job_id=job_id,
                                          text="", gap_report=gap_report)
                    # Park task in awaiting_review — finalize endpoint resolves it
                    update_task_status(db_path, task_id, "awaiting_review")
                    return
                else:
                    log.warning("[task_runner] resume_optimize hallucination check failed for job %d", job_id)
                    save_optimized_resume(db_path, job_id=job_id,
                                          text="", gap_report=gap_report)
            else:
                # Gap-only run (free tier): save report, no draft
                save_optimized_resume(db_path, job_id=job_id,
                                      text="", gap_report=gap_report)

        elif task_type == "resume_score":
            import json as _json

            from scripts.db import get_resume as _get_resume
            from scripts.resume_scorer import score_ats_hygiene, score_resume

            p = _json.loads(params or "{}")
            resume_id = p.get("resume_id")
            resume_row = _get_resume(db_path, resume_id)
            if not resume_row:
                update_task_status(db_path, task_id, "failed", error=f"Resume {resume_id} not found")
                return

            struct = _json.loads(resume_row["struct_json"]) if resume_row.get("struct_json") else {}
            needs_struct_persist = False
            if not struct:
                from scripts.resume_parser import parse_resume
                struct, _err = parse_resume(resume_row.get("text", ""))
                needs_struct_persist = True

            update_task_stage(db_path, task_id, "scoring resume")
            holistic = score_resume(struct)

            update_task_stage(db_path, task_id, "checking ATS hygiene")
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            recent_rows = conn.execute(
                "SELECT description FROM jobs WHERE description IS NOT NULL AND description != '' "
                "ORDER BY date_found DESC LIMIT 10"
            ).fetchall()
            conn.close()
            recent_descriptions = [r["description"] for r in recent_rows]
            ats = score_ats_hygiene(struct, recent_descriptions)

            feedback = dict(holistic)
            feedback.update(ats)
            conn = sqlite3.connect(db_path)
            if needs_struct_persist:
                # struct_json was empty on this row (e.g. non-YAML imports never
                # populate it) — we had to fall back to parse_resume() above to
                # score it at all. Persist that parsed struct now so downstream
                # apply-suggestion calls have structured data to edit instead of
                # permanently 409ing on a resume that was just scored fine.
                conn.execute(
                    "UPDATE resumes SET score=?, ats_score=?, feedback_json=?, "
                    "struct_json=?, scored_at=datetime('now') WHERE id=?",
                    (holistic.get("overall_score"), ats.get("ats_score"),
                     _json.dumps(feedback), _json.dumps(struct), resume_id),
                )
            else:
                conn.execute(
                    "UPDATE resumes SET score=?, ats_score=?, feedback_json=?, "
                    "scored_at=datetime('now') WHERE id=?",
                    (holistic.get("overall_score"), ats.get("ats_score"),
                     _json.dumps(feedback), resume_id),
                )
            conn.commit()
            conn.close()

        elif task_type == "survey_analyze":
            import json as _json

            from scripts.llm_router import CONFIG_PATH as LLM_ROUTER_CONFIG_PATH
            from scripts.survey_assistant import run_survey_analyze
            p = _json.loads(params or "{}")
            update_task_stage(db_path, task_id, "analyzing survey")
            result = run_survey_analyze(
                text=p.get("text"),
                image_b64=p.get("image_b64"),
                mode=p.get("mode", "quick"),
                config_path=LLM_ROUTER_CONFIG_PATH,
            )
            update_task_status(
                db_path, task_id, "completed",
                error=_json.dumps(result),
            )
            return

        elif task_type == "prepare_training":
            from scripts.prepare_training_data import (
                DEFAULT_OUTPUT,
                build_records,
                write_jsonl,
            )
            records = build_records()
            write_jsonl(records, DEFAULT_OUTPUT)
            n = len(records)
            update_task_status(
                db_path, task_id, "completed",
                error=f"{n} training pair{'s' if n != 1 else ''} extracted",
            )
            return

        else:
            raise ValueError(f"Unknown task_type: {task_type!r}")

        update_task_status(db_path, task_id, "completed")

    except BaseException as exc:  # noqa: BLE001 -- deliberately broader than
        # Exception: this wraps the entire dispatch of task_type handlers,
        # several of which shell out to third-party/legacy scraper modules
        # (e.g. companyScraper) that call sys.exit() on failure, raising
        # SystemExit -- a BaseException subclass that a plain `except
        # Exception` would let propagate and crash the task runner. This
        # runs inside a background task worker (not the main thread), so
        # catching KeyboardInterrupt here as a side effect does not block
        # process-level interrupt handling. Not silent -- the task is marked
        # "failed" with the error recorded via update_task_status().
        update_task_status(db_path, task_id, "failed", error=str(exc))
