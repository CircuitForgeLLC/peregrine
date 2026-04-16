#!/usr/bin/env python3
"""
Generate demo/seed.sql — committed seed INSERT statements for the demo DB.

Run whenever seed data needs to change:
    conda run -n cf python scripts/generate_demo_seed.py

Outputs pure INSERT SQL (no DDL). Schema migrations are handled by db_migrate.py
at container startup. The seed SQL is loaded after migrations complete.
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

OUT_PATH = Path(__file__).parent.parent / "demo" / "seed.sql"

TODAY = date.today()


def _dago(n: int) -> str:
    return (TODAY - timedelta(days=n)).isoformat()


def _dfrom(n: int) -> str:
    return (TODAY + timedelta(days=n)).isoformat()


COVER_LETTER_SPOTIFY = """\
Dear Hiring Manager,

I'm excited to apply for the UX Designer role at Spotify. With five years of
experience designing for music discovery and cross-platform experiences, I've
consistently shipped features that make complex audio content feel effortless to
navigate. At my last role I led a redesign of the playlist creation flow that
reduced drop-off by 31%.

Spotify's commitment to artist and listener discovery — and its recent push into
audiobooks and podcast tooling — aligns directly with the kind of cross-format
design challenges I'm most energised by.

I'd love to bring that focus to your product design team.

Warm regards,
[Your name]
"""

SQL_PARTS: list[str] = []

# ── Jobs ──────────────────────────────────────────────────────────────────────

# Columns: title, company, url, source, location, is_remote, salary,
#          match_score, status, date_found, date_posted, cover_letter,
#          applied_at, phone_screen_at, interviewing_at, offer_at, hired_at,
#          interview_date, rejection_stage, hired_feedback
JOBS: list[tuple] = [
    # ---- Review queue (12 jobs — mix of pending + approved) ------------------
    ("UX Designer",
     "Spotify", "https://www.linkedin.com/jobs/view/1000001",
     "linkedin", "Remote", 1, "$110k–$140k",
     94.0, "approved", _dago(1), _dago(3), COVER_LETTER_SPOTIFY,
     None, None, None, None, None, None, None, None),

    ("Product Designer",
     "Duolingo", "https://www.linkedin.com/jobs/view/1000002",
     "linkedin", "Pittsburgh, PA", 0, "$95k–$120k",
     87.0, "approved", _dago(2), _dago(5), "Draft in progress — cover letter generating…",
     None, None, None, None, None, None, None, None),

    ("UX Lead",
     "NPR", "https://www.indeed.com/viewjob?jk=1000003",
     "indeed", "Washington, DC", 1, "$120k–$150k",
     81.0, "approved", _dago(3), _dago(7), None,
     None, None, None, None, None, None, None, None),

    # Ghost post — date_posted 34 days ago → shadow indicator
    ("Senior UX Designer",
     "Mozilla", "https://www.linkedin.com/jobs/view/1000004",
     "linkedin", "Remote", 1, "$105k–$130k",
     81.0, "pending", _dago(2), _dago(34), None,
     None, None, None, None, None, None, None, None),

    ("Interaction Designer",
     "Figma", "https://www.indeed.com/viewjob?jk=1000005",
     "indeed", "San Francisco, CA", 1, "$115k–$145k",
     78.0, "pending", _dago(4), _dago(6), None,
     None, None, None, None, None, None, None, None),

    ("Product Designer II",
     "Notion", "https://www.linkedin.com/jobs/view/1000006",
     "linkedin", "Remote", 1, "$100k–$130k",
     76.0, "pending", _dago(5), _dago(8), None,
     None, None, None, None, None, None, None, None),

    ("UX Designer",
     "Stripe", "https://www.linkedin.com/jobs/view/1000007",
     "linkedin", "Remote", 1, "$120k–$150k",
     74.0, "pending", _dago(6), _dago(9), None,
     None, None, None, None, None, None, None, None),

    ("UI/UX Designer",
     "Canva", "https://www.indeed.com/viewjob?jk=1000008",
     "indeed", "Remote", 1, "$90k–$115k",
     72.0, "pending", _dago(7), _dago(10), None,
     None, None, None, None, None, None, None, None),

    ("Senior Product Designer",
     "Asana", "https://www.linkedin.com/jobs/view/1000009",
     "linkedin", "San Francisco, CA", 1, "$125k–$155k",
     69.0, "pending", _dago(8), _dago(11), None,
     None, None, None, None, None, None, None, None),

    ("UX Researcher",
     "Intercom", "https://www.indeed.com/viewjob?jk=1000010",
     "indeed", "Remote", 1, "$95k–$120k",
     67.0, "pending", _dago(9), _dago(12), None,
     None, None, None, None, None, None, None, None),

    ("Product Designer",
     "Linear", "https://www.linkedin.com/jobs/view/1000011",
     "linkedin", "Remote", 1, "$110k–$135k",
     65.0, "pending", _dago(10), _dago(13), None,
     None, None, None, None, None, None, None, None),

    ("UX Designer",
     "Loom", "https://www.indeed.com/viewjob?jk=1000012",
     "indeed", "Remote", 1, "$90k–$110k",
     62.0, "pending", _dago(11), _dago(14), None,
     None, None, None, None, None, None, None, None),

    # ---- Pipeline jobs (applied → hired) ------------------------------------
    ("Senior Product Designer",
     "Asana", "https://www.asana.com/jobs/1000013",
     "linkedin", "San Francisco, CA", 1, "$125k–$155k",
     91.0, "phone_screen", _dago(14), _dago(16), None,
     _dago(7), _dfrom(0), None, None, None,
     f"{_dfrom(0)}T14:00:00", None, None),

    ("Product Designer",
     "Notion", "https://www.notion.so/jobs/1000014",
     "indeed", "Remote", 1, "$100k–$130k",
     88.0, "interviewing", _dago(21), _dago(23), None,
     _dago(14), _dago(10), _dago(3), None, None,
     f"{_dfrom(7)}T10:00:00", None, None),

    ("Design Systems Designer",
     "Figma", "https://www.figma.com/jobs/1000015",
     "linkedin", "San Francisco, CA", 1, "$130k–$160k",
     96.0, "hired", _dago(45), _dago(47), None,
     _dago(38), _dago(32), _dago(25), _dago(14), _dago(7),
     None, None,
     '{"factors":["clear_scope","great_manager","mission_aligned"],"notes":"Excited about design systems work. Salary met expectations."}'),

    ("UX Designer",
     "Slack", "https://slack.com/jobs/1000016",
     "indeed", "Remote", 1, "$115k–$140k",
     79.0, "applied", _dago(28), _dago(30), None,
     _dago(18), None, None, None, None, None, None, None),
]


def _q(v: object) -> str:
    """SQL-quote a Python value."""
    if v is None:
        return "NULL"
    return "'" + str(v).replace("'", "''") + "'"


_JOB_COLS = (
    "title, company, url, source, location, is_remote, salary, "
    "match_score, status, date_found, date_posted, cover_letter, "
    "applied_at, phone_screen_at, interviewing_at, offer_at, hired_at, "
    "interview_date, rejection_stage, hired_feedback"
)

SQL_PARTS.append("-- jobs")
for job in JOBS:
    vals = ", ".join(_q(v) for v in job)
    SQL_PARTS.append(f"INSERT INTO jobs ({_JOB_COLS}) VALUES ({vals});")

# ── Contacts ──────────────────────────────────────────────────────────────────

# (job_id, direction, subject, from_addr, to_addr, received_at, stage_signal)
CONTACTS: list[tuple] = [
    (1, "inbound",  "Excited to connect — UX Designer role at Spotify",
     "jamie.chen@spotify.com", "you@example.com", _dago(3), "positive_response"),
    (1, "outbound", "Re: Excited to connect — UX Designer role at Spotify",
     "you@example.com", "jamie.chen@spotify.com", _dago(2), None),
    (13, "inbound", "Interview Confirmation — Senior Product Designer",
     "recruiting@asana.com", "you@example.com", _dago(2), "interview_scheduled"),
    (14, "inbound", "Your panel interview is confirmed for Apr 22",
     "recruiting@notion.so", "you@example.com", _dago(3), "interview_scheduled"),
    (14, "inbound", "Pre-interview prep resources",
     "marcus.webb@notion.so", "you@example.com", _dago(2), "positive_response"),
    (15, "inbound", "Figma Design Systems — Offer Letter",
     "offers@figma.com", "you@example.com", _dago(14), "offer_received"),
    (15, "outbound", "Re: Figma Design Systems — Offer Letter (acceptance)",
     "you@example.com", "offers@figma.com", _dago(10), None),
    (15, "inbound", "Welcome to Figma! Onboarding next steps",
     "onboarding@figma.com", "you@example.com", _dago(7), None),
    (16, "inbound", "Thanks for applying to Slack",
     "noreply@slack.com", "you@example.com", _dago(18), None),
]

SQL_PARTS.append("\n-- job_contacts")
for c in CONTACTS:
    job_id, direction, subject, from_addr, to_addr, received_at, stage_signal = c
    SQL_PARTS.append(
        f"INSERT INTO job_contacts "
        f"(job_id, direction, subject, from_addr, to_addr, received_at, stage_signal) "
        f"VALUES ({job_id}, {_q(direction)}, {_q(subject)}, {_q(from_addr)}, "
        f"{_q(to_addr)}, {_q(received_at)}, {_q(stage_signal)});"
    )

# ── References ────────────────────────────────────────────────────────────────

# (name, email, role, company, relationship, notes, tags, prep_email)
REFERENCES: list[tuple] = [
    ("Dr. Priya Nair", "priya.nair@example.com", "Director of Design", "Acme Corp",
     "former_manager",
     "Managed me for 3 years on the consumer app redesign. Enthusiastic reference.",
     '["manager","design"]',
     "Hi Priya,\n\nI hope you're doing well! I'm currently interviewing for a few senior UX roles "
     "and would be so grateful if you'd be willing to serve as a reference.\n\nThank you!\n[Your name]"),

    ("Sam Torres", "sam.torres@example.com", "Senior Product Designer", "Acme Corp",
     "former_colleague",
     "Worked together on design systems. Great at speaking to collaborative process.",
     '["colleague","design_systems"]', None),

    ("Jordan Kim", "jordan.kim@example.com", "VP of Product", "Streamline Inc",
     "former_manager",
     "Led the product team I was embedded in. Can speak to business impact of design work.",
     '["manager","product"]', None),
]

SQL_PARTS.append("\n-- references_")
for ref in REFERENCES:
    name, email, role, company, relationship, notes, tags, prep_email = ref
    SQL_PARTS.append(
        f"INSERT INTO references_ "
        f"(name, email, role, company, relationship, notes, tags, prep_email) "
        f"VALUES ({_q(name)}, {_q(email)}, {_q(role)}, {_q(company)}, "
        f"{_q(relationship)}, {_q(notes)}, {_q(tags)}, {_q(prep_email)});"
    )

# ── Write output ──────────────────────────────────────────────────────────────

output = "\n".join(SQL_PARTS) + "\n"
OUT_PATH.write_text(output, encoding="utf-8")
print(
    f"Wrote {OUT_PATH} "
    f"({len(JOBS)} jobs, {len(CONTACTS)} contacts, {len(REFERENCES)} references)"
)
