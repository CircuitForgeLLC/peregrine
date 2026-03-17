"""calendar_push.py — push interview events to connected calendar integrations.

Supports Apple Calendar (CalDAV) and Google Calendar. Idempotent: a second
push updates the existing event rather than creating a duplicate.
"""
from __future__ import annotations

import uuid
import yaml
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from scripts.db import get_job_by_id, get_research, set_calendar_event_id, DEFAULT_DB

_CALENDAR_INTEGRATIONS = ("apple_calendar", "google_calendar")

# Stage label map matches 5_Interviews.py
_STAGE_LABELS = {
    "phone_screen":  "Phone Screen",
    "interviewing":  "Interview",
    "offer":         "Offer Review",
}


def _load_integration(name: str, config_dir: Path):
    """Instantiate and connect an integration from its saved config file."""
    config_file = config_dir / "integrations" / f"{name}.yaml"
    if not config_file.exists():
        return None
    with open(config_file) as f:
        config = yaml.safe_load(f) or {}
    if name == "apple_calendar":
        from scripts.integrations.apple_calendar import AppleCalendarIntegration
        integration = AppleCalendarIntegration()
    elif name == "google_calendar":
        from scripts.integrations.google_calendar import GoogleCalendarIntegration
        integration = GoogleCalendarIntegration()
    else:
        return None
    integration.connect(config)
    return integration


def _build_event_details(job: dict, research: Optional[dict]) -> tuple[str, str]:
    """Return (title, description) for the calendar event."""
    stage_label = _STAGE_LABELS.get(job.get("status", ""), "Interview")
    title = f"{stage_label}: {job.get('title', 'Interview')} @ {job.get('company', '')}"

    lines = []
    if job.get("url"):
        lines.append(f"Job listing: {job['url']}")
    if research and research.get("company_brief"):
        brief = research["company_brief"].strip()
        # Trim to first 3 sentences so the event description stays readable
        sentences = brief.split(". ")
        lines.append("\n" + ". ".join(sentences[:3]) + ("." if len(sentences) > 1 else ""))
    lines.append("\n— Sent by Peregrine (CircuitForge)")

    return title, "\n".join(lines)


def push_interview_event(
    db_path: Path = DEFAULT_DB,
    job_id: int = None,
    config_dir: Path = None,
) -> dict:
    """Push (or update) an interview event on the first connected calendar integration.

    Returns:
        {"ok": True,  "provider": "apple_calendar", "event_id": "..."}
        {"ok": False, "error": "..."}
    """
    if config_dir is None:
        config_dir = Path(__file__).parent.parent / "config"

    job = get_job_by_id(db_path, job_id)
    if not job:
        return {"ok": False, "error": f"Job {job_id} not found"}

    interview_date = job.get("interview_date")
    if not interview_date:
        return {"ok": False, "error": "No interview date set — save a date first"}

    # Build datetimes: noon UTC, 1 hour duration
    try:
        base = datetime.fromisoformat(interview_date).replace(
            hour=12, minute=0, second=0, microsecond=0, tzinfo=timezone.utc
        )
    except ValueError:
        return {"ok": False, "error": f"Could not parse interview_date: {interview_date!r}"}
    start_dt = base
    end_dt = base + timedelta(hours=1)

    research = get_research(db_path, job_id)
    title, description = _build_event_details(job, research)

    existing_event_id = job.get("calendar_event_id")

    for name in _CALENDAR_INTEGRATIONS:
        integration = _load_integration(name, config_dir)
        if integration is None:
            continue

        try:
            # Use a stable UID derived from job_id for CalDAV; gcal uses the returned event id
            uid = existing_event_id or f"peregrine-job-{job_id}@circuitforge.tech"
            if existing_event_id:
                event_id = integration.update_event(uid, title, start_dt, end_dt, description)
            else:
                event_id = integration.create_event(uid, title, start_dt, end_dt, description)

            set_calendar_event_id(db_path, job_id, event_id)
            return {"ok": True, "provider": name, "event_id": event_id}

        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    return {"ok": False, "error": "No calendar integration configured — connect one in Settings → Integrations"}
