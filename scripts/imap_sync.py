# scripts/imap_sync.py
"""
IMAP email sync — associates recruitment emails with job applications.

Safety / privacy design:
  - Only imports emails that pass BOTH checks:
      1. Sender or subject contains the exact company name (or derived domain)
      2. Subject contains at least one recruitment keyword
  - Fuzzy / partial company name matches are rejected
  - Emails between known personal contacts are never imported
  - Only the INBOX and Sent folders are touched; no other folders
  - Credentials stored in config/email.yaml (gitignored)

Config: config/email.yaml  (see config/email.yaml.example)

Usage:
    conda run -n job-seeker python scripts/imap_sync.py
    conda run -n job-seeker python scripts/imap_sync.py --job-id 42
    conda run -n job-seeker python scripts/imap_sync.py --dry-run
"""
import email
import imaplib
import re
import sys
from datetime import datetime, timedelta
from email.header import decode_header as _raw_decode_header
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.db import DEFAULT_DB, init_db, get_interview_jobs, add_contact, get_contacts
from scripts.llm_router import LLMRouter

_CLASSIFIER_ROUTER = LLMRouter()

_CLASSIFY_SYSTEM = (
    "You are an email classifier. Classify the recruitment email into exactly ONE of these categories:\n"
    "  interview_scheduled, offer_received, rejected, positive_response, survey_received, neutral\n\n"
    "Rules:\n"
    "- interview_scheduled: recruiter wants to book a call/interview\n"
    "- offer_received: job offer is being extended\n"
    "- rejected: explicitly not moving forward\n"
    "- positive_response: interested/impressed but no interview booked yet\n"
    "- survey_received: link or request to complete a survey, assessment, or questionnaire\n"
    "- neutral: auto-confirmation, generic update, no clear signal\n\n"
    "Respond with ONLY the category name. No explanation."
)

_CLASSIFY_LABELS = [
    "interview_scheduled", "offer_received", "rejected",
    "positive_response", "survey_received", "neutral",
]

CONFIG_PATH = Path(__file__).parent.parent / "config" / "email.yaml"

# ── Recruitment keyword filter ────────────────────────────────────────────────
# An email must match at least one of these in its subject line to be imported.
RECRUITMENT_KEYWORDS = {
    # Application lifecycle
    "interview", "application", "applicant", "apply", "applied",
    "position", "opportunity", "role", "opening", "vacancy",
    "offer", "offer letter", "schedule", "scheduling",
    "screening", "screen", "phone screen", "video call",
    "assessment", "hiring", "hired", "recruiter", "recruitment",
    "talent", "candidate", "recruiting", "next steps", "follow up", "follow-up",
    "onboarding", "start date", "background check", "reference",
    "congratulations", "unfortunately", "decision", "update",
    # Job board / ATS notifications
    "viewed your profile", "interested in your background",
    "job alert", "new job", "job match", "job opportunity",
    "your application", "application received", "application status",
    "application update", "we received", "thank you for applying",
    "thanks for applying", "moved forward", "moving forward",
    "not moving forward", "decided to", "other candidates",
    "keep your resume", "keep you in mind",
    # Recruiter outreach
    "reaching out", "i came across", "your experience",
    "connect with you", "exciting opportunity", "great fit",
    "perfect fit", "right fit", "strong fit", "ideal candidate",
}

# ── Rejection / ATS-confirm phrase filter ─────────────────────────────────────
# Checked against subject + first 800 chars of body BEFORE calling any LLM.
# Covers the cases phi3:mini consistently mis-classifies as "neutral".
_REJECTION_PHRASES = [
    # Explicit rejection — safe to check subject + body
    "not moving forward", "decided not to move forward",
    "not selected", "not be moving forward", "will not be moving forward",
    "unfortunately", "regret to inform", "regret to let you know",
    "decided to go with other", "decided to pursue other",
    "other candidates", "other applicants", "position has been filled",
    "filled the position", "no longer moving forward",
    "we have decided", "we've decided", "after careful consideration",
    "at this time we", "at this point we",
    "we will not", "we won't be", "we are not able",
    "wish you the best", "best of luck in your",
    "keep your resume on file",
]

# ATS-confirm phrases — checked against SUBJECT ONLY.
# Do NOT check these in the body: recruiters often quote ATS thread history,
# so "thank you for applying" can appear in a genuine follow-up body.
_ATS_CONFIRM_SUBJECTS = [
    "application received", "application confirmation",
    "thanks for applying", "thank you for applying",
    "thank you for your application",
    "we received your application",
    "application has been received",
    "has received your application",
    "successfully submitted",
    "your application for",
    "you applied to",
]

# Phrases that immediately identify a non-recruitment email (retail, spam, etc.)
_SPAM_PHRASES = [
    # Retail / commerce offers
    "special offer", "private offer", "exclusive offer", "limited time offer",
    "limited-time offer", "sent you a special offer", "sent you an offer",
    "holiday offer", "seasonal offer", "membership offer",
    "round trip from $", "bonus points",
    "% off", "% discount", "save up to", "free shipping",
    "unsubscribe", "view in browser", "view this email in",
    "update your preferences", "email preferences",
    # LinkedIn apply confirmations & digests (not new inbound leads)
    "your application was sent to",
    "your application was viewed by",
    "application updates this week",
    "don't forget to complete your application",
    "view your application updates",
    "you have new application updates",
    # Indeed apply confirmations
    "indeed application:",
    # DocuSign / e-signature
    "requests you to sign",
    "has sent you a reminder",
    "please sign",
    # Security / MFA codes
    "security code for your application",
    "verification code",
]

# Subject prefixes that identify non-job emails
_SPAM_SUBJECT_PREFIXES = [
    "@",                    # "@user sent you a special offer" — Depop / social commerce
    "re: fw:",              # forwarded chains unlikely to be first-contact recruitment
    "accepted:",            # Google Calendar accepted invite
    "notification:",        # Google Calendar notification
    "[meeting reminder]",   # Google Calendar meeting reminder
    "updated invitation:",  # Google Calendar update
    "[updated]",            # Google Calendar update
    "reminder:",            # Generic reminder (AAA digital interview reminders, etc.)
    "📄",                   # Newsletter/article emoji prefix
    "invitation from",      # Google Calendar invite forwarded by name
]

# Unicode-safe "don't forget" variants (Gmail renders typographic apostrophes)
_DONT_FORGET_VARIANTS = [
    "don't forget to complete your application",          # straight apostrophe
    "don\u2019t forget to complete your application",    # right single quotation mark '
    "don\u2018t forget to complete your application",    # left single quotation mark '
]


def _has_rejection_or_ats_signal(subject: str, body: str) -> bool:
    """Return True if the email is a rejection, ATS auto-confirmation, or non-recruitment spam."""
    subject_lower = subject.lower().strip()

    # Fast subject-prefix checks (Depop "@user", etc.)
    if any(subject_lower.startswith(p) for p in _SPAM_SUBJECT_PREFIXES):
        return True

    # Fast subject-only check for ATS confirmations
    if any(phrase in subject_lower for phrase in _ATS_CONFIRM_SUBJECTS):
        return True

    # Check subject + opening body for rejection and spam phrases
    haystack = subject_lower + " " + body[:1500].lower()
    if any(phrase in haystack for phrase in _REJECTION_PHRASES + _SPAM_PHRASES):
        return True
    # Unicode-safe "don't forget" check (handles straight, right, and left apostrophes)
    raw = (subject + " " + body[:1500]).lower()
    return any(phrase in raw for phrase in _DONT_FORGET_VARIANTS)


# Legal entity suffixes to strip when normalising company names
_LEGAL_SUFFIXES = re.compile(
    r",?\s*\b(Inc|LLC|Ltd|Limited|Corp|Corporation|Co|GmbH|AG|plc|PLC|SAS|SA|NV|BV|LP|LLP)\b\.?\s*$",
    re.IGNORECASE,
)

# Job-board SLDs that must never be used as company-match search terms.
# A LinkedIn job URL has domain "linkedin.com" → SLD "linkedin", which would
# incorrectly match every LinkedIn notification email against every LinkedIn job.
_JOB_BOARD_SLDS = {
    "linkedin", "indeed", "glassdoor", "ziprecruiter", "monster",
    "careerbuilder", "dice", "simplyhired", "wellfound", "angellist",
    "greenhouse", "lever", "workday", "taleo", "icims", "smartrecruiters",
    "bamboohr", "ashby", "rippling", "jobvite", "workable", "gusto",
    "paylocity", "paycom", "adp", "breezy", "recruitee", "jazz",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _decode_str(value: Optional[str]) -> str:
    """Decode an RFC2047-encoded header value to a plain Python string."""
    if not value:
        return ""
    parts = _raw_decode_header(value)
    result = []
    for part, encoding in parts:
        if isinstance(part, bytes):
            result.append(part.decode(encoding or "utf-8", errors="replace"))
        else:
            result.append(str(part))
    return " ".join(result).strip()


def _extract_domain(url_or_email: str) -> str:
    """
    Pull the bare domain from a URL (https://company.com/jobs/...) or
    an email address (recruiter@company.com).  Returns '' if none found.
    """
    url_or_email = url_or_email.strip()
    if "@" in url_or_email:
        return url_or_email.split("@")[-1].split(">")[0].strip().lower()
    try:
        parsed = urlparse(url_or_email)
        host = parsed.netloc or parsed.path
        # strip www.
        return re.sub(r"^www\.", "", host).lower()
    except Exception:
        return ""


def _normalise_company(company: str) -> str:
    """Strip legal suffixes and extra whitespace from a company name."""
    return _LEGAL_SUFFIXES.sub("", company).strip()


def _company_search_terms(company: str, job_url: str = "") -> list[str]:
    """
    Return a list of strings that must appear (case-insensitively) in the
    email's from-address or subject for it to be considered a match.

    We are deliberately conservative:
      - Use the full normalised company name (not just the first word)
      - Also include the company domain derived from the job URL, but ONLY
        when the domain belongs to the actual company (not a job board).
        LinkedIn jobs link to linkedin.com — if we used "linkedin" as a term
        we'd match every LinkedIn notification email against every LinkedIn job.
    """
    terms = []
    clean = _normalise_company(company)
    if len(clean) >= 3:
        terms.append(clean.lower())

    domain = _extract_domain(job_url)
    if domain and len(domain) > 4:
        sld = domain.split(".")[0]
        if len(sld) >= 3 and sld not in terms and sld not in _JOB_BOARD_SLDS:
            terms.append(sld)

    return terms


def _has_recruitment_keyword(subject: str) -> bool:
    """Return True if the subject contains at least one recruitment keyword."""
    subject_lower = subject.lower()
    return any(kw in subject_lower for kw in RECRUITMENT_KEYWORDS)


def _email_is_relevant(from_addr: str, subject: str, search_terms: list[str]) -> bool:
    """
    Two-gate filter:
      Gate 1 — from-address OR subject must contain an exact company term
      Gate 2 — subject must contain a recruitment keyword

    Both gates must pass.  This prevents importing unrelated emails that
    happen to mention a company name in passing.
    """
    combined = (from_addr + " " + subject).lower()

    gate1 = any(term in combined for term in search_terms)
    gate2 = _has_recruitment_keyword(subject)

    return gate1 and gate2


def _get_existing_message_ids(job_id: int, db_path: Path) -> set[str]:
    contacts = get_contacts(db_path, job_id=job_id)
    return {c.get("message_id", "") for c in contacts if c.get("message_id")}


def classify_stage_signal(subject: str, body: str) -> Optional[str]:
    """Classify an inbound email into a pipeline stage signal.

    Returns one of the 5 label strings, or None on failure.
    Uses phi3:mini via Ollama (benchmarked 100% on 12-case test set).
    """
    try:
        prompt = f"Subject: {subject}\n\nEmail: {body[:400]}"
        raw = _CLASSIFIER_ROUTER.complete(
            prompt,
            system=_CLASSIFY_SYSTEM,
            model_override="llama3.1:8b",
            fallback_order=["ollama_research"],
        )
        # Strip <think> blocks (in case a reasoning model slips through)
        text = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL)
        text = text.lower().strip()
        for label in _CLASSIFY_LABELS:
            if text.startswith(label) or label in text:
                return label
        return "neutral"
    except Exception:
        return None


_EXTRACT_SYSTEM = (
    "Extract the hiring company name and job title from this recruitment email, "
    "but ONLY if it represents genuine new recruiter outreach — i.e. a recruiter "
    "contacting you about an open role for the first time.\n\n"
    "Return {\"company\": null, \"title\": null} if the email is any of:\n"
    "  - A rejection or 'not moving forward' notice\n"
    "  - An ATS auto-confirmation ('we received your application')\n"
    "  - A status update for an application already in progress\n"
    "  - A generic job-alert digest or newsletter\n"
    "  - A follow-up you sent, not a reply from a recruiter\n\n"
    "Otherwise respond with ONLY valid JSON: "
    '{"company": "Company Name", "title": "Job Title"}.'
)


def extract_lead_info(subject: str, body: str,
                      from_addr: str) -> tuple[Optional[str], Optional[str]]:
    """Use LLM to extract (company, title) from an unmatched recruitment email.

    Returns (company, title) or (None, None) on failure / low confidence.
    """
    import json as _json
    try:
        prompt = (
            f"From: {from_addr}\n"
            f"Subject: {subject}\n\n"
            f"Email excerpt:\n{body[:600]}"
        )
        raw = _CLASSIFIER_ROUTER.complete(
            prompt,
            system=_EXTRACT_SYSTEM,
            fallback_order=["ollama_research"],
        )
        text = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
        m = re.search(r'\{.*\}', text, re.DOTALL)
        if not m:
            return None, None
        data = _json.loads(m.group())
        company = data.get("company") or None
        title   = data.get("title") or None
        return company, title
    except Exception:
        return None, None


# Keywords that indicate an email in a curated label needs attention.
# Intentionally separate from RECRUITMENT_KEYWORDS — these are action-oriented.
_TODO_LABEL_KEYWORDS = {
    "action needed", "action required",
    "please complete", "please submit", "please respond", "please reply",
    "response needed", "response required",
    "next steps", "next step",
    "follow up", "follow-up",
    "deadline", "by end of",
    "your offer", "offer letter",
    "background check", "reference check",
    "onboarding", "start date",
    "congrats", "congratulations",
    "we'd like to", "we would like to",
    "interview", "schedule", "scheduling",
}


def _has_todo_keyword(subject: str) -> bool:
    """Return True if the subject contains a TODO-label action keyword."""
    subject_lower = subject.lower()
    return any(kw in subject_lower for kw in _TODO_LABEL_KEYWORDS)


_LINKEDIN_ALERT_SENDER = "jobalerts-noreply@linkedin.com"

# Social-proof / nav lines to skip when parsing alert blocks
_ALERT_SKIP_PHRASES = {
    "school alumni", "apply with", "actively hiring", "manage alerts",
    "view all jobs", "your job alert", "new jobs match",
    "unsubscribe", "linkedin corporation",
}


def parse_linkedin_alert(body: str) -> list[dict]:
    """
    Parse the plain-text body of a LinkedIn Job Alert digest email.

    Returns a list of dicts: {title, company, location, url}.
    URL is canonicalized to https://www.linkedin.com/jobs/view/<id>/
    (tracking parameters stripped).
    """
    jobs = []
    # Split on separator lines (10+ dashes)
    blocks = re.split(r"\n\s*-{10,}\s*\n", body)
    for block in blocks:
        lines = [ln.strip() for ln in block.strip().splitlines() if ln.strip()]

        # Find "View job:" URL
        url = None
        for line in lines:
            m = re.search(r"View job:\s*(https?://\S+)", line, re.IGNORECASE)
            if m:
                raw_url = m.group(1)
                job_id_m = re.search(r"/jobs/view/(\d+)", raw_url)
                if job_id_m:
                    url = f"https://www.linkedin.com/jobs/view/{job_id_m.group(1)}/"
                break
        if not url:
            continue

        # Filter noise lines
        content = [
            ln for ln in lines
            if not any(p in ln.lower() for p in _ALERT_SKIP_PHRASES)
            and not ln.lower().startswith("view job:")
            and not ln.startswith("http")
        ]
        if len(content) < 2:
            continue

        jobs.append({
            "title": content[0],
            "company": content[1],
            "location": content[2] if len(content) > 2 else "",
            "url": url,
        })
    return jobs


def _scan_todo_label(conn: imaplib.IMAP4, cfg: dict, db_path: Path,
                     active_jobs: list[dict],
                     known_message_ids: set) -> int:
    """Scan the configured Gmail label for action emails, matching them to pipeline jobs.

    Two gates per email:
      1. Company name appears in from-address or subject (same as sync_job_emails)
      2. Subject contains a TODO-label action keyword

    Returns count of new contacts attached.
    """
    label = cfg.get("todo_label", "").strip()
    if not label:
        return 0

    lookback = int(cfg.get("lookback_days", 90))
    since = (datetime.now() - timedelta(days=lookback)).strftime("%d-%b-%Y")

    # Search the label folder for any emails (no keyword pre-filter — it's curated)
    uids = _search_folder(conn, label, "ALL", since)
    if not uids:
        return 0

    # Build a lookup: search_term → [job, ...] for all active jobs
    term_to_jobs: dict[str, list[dict]] = {}
    for job in active_jobs:
        for term in _company_search_terms(job.get("company", ""), job.get("url", "")):
            term_to_jobs.setdefault(term, []).append(job)

    added = 0
    for uid in uids:
        parsed = _parse_message(conn, uid)
        if not parsed:
            continue
        mid = parsed["message_id"]
        if mid in known_message_ids:
            continue

        # Gate 1: company name match — from_addr + subject + first 300 chars of body
        # Body fallback catches ATS emails (e.g. noreply@greenhouse.io) where the
        # company name only appears in the email body, not the sender or subject.
        combined = (
            parsed["from_addr"] + " " +
            parsed["subject"] + " " +
            parsed["body"][:300]
        ).lower()
        matched_jobs = []
        for term, jobs in term_to_jobs.items():
            if term in combined:
                matched_jobs.extend(jobs)
        # Deduplicate by job id
        seen_ids: set[int] = set()
        matched_jobs = [j for j in matched_jobs if not (j["id"] in seen_ids or seen_ids.add(j["id"]))]  # type: ignore[func-returns-value]
        if not matched_jobs:
            continue

        # Gate 2: action keyword in subject
        if not _has_todo_keyword(parsed["subject"]):
            continue

        for job in matched_jobs:
            contact_id = add_contact(
                db_path, job_id=job["id"], direction="inbound",
                subject=parsed["subject"],
                from_addr=parsed["from_addr"],
                to_addr=parsed["to_addr"],
                body=parsed["body"],
                received_at=parsed["date"][:16] if parsed["date"] else since,
                message_id=mid,
            )
            signal = classify_stage_signal(parsed["subject"], parsed["body"])
            if signal and signal != "neutral":
                _update_contact_signal(db_path, contact_id, signal)

        known_message_ids.add(mid)
        added += 1
        print(f"[imap] TODO label → {matched_jobs[0].get('company')} — {parsed['subject'][:60]}")

    return added


def _scan_unmatched_leads(conn: imaplib.IMAP4, cfg: dict,
                          db_path: Path,
                          known_message_ids: set) -> int:
    """Scan INBOX for recruitment emails not matched to any pipeline job.

    Calls LLM to extract company/title; inserts qualifying emails as pending jobs.
    Returns the count of new leads inserted.
    """
    from scripts.db import get_existing_urls, insert_job, add_contact as _add_contact

    lookback = int(cfg.get("lookback_days", 90))
    since = (datetime.now() - timedelta(days=lookback)).strftime("%d-%b-%Y")

    broad_terms = ["interview", "opportunity", "offer letter", "job offer", "application", "recruiting"]
    all_uids: set = set()
    for term in broad_terms:
        uids = _search_folder(conn, "INBOX", f'(SUBJECT "{term}")', since)
        all_uids.update(uids)

    existing_urls = get_existing_urls(db_path)
    new_leads = 0

    for uid in all_uids:
        parsed = _parse_message(conn, uid)
        if not parsed:
            continue
        mid = parsed["message_id"]
        if mid in known_message_ids:
            continue

        # ── LinkedIn Job Alert digest — parse each card individually ──────
        if _LINKEDIN_ALERT_SENDER in parsed["from_addr"].lower():
            cards = parse_linkedin_alert(parsed["body"])
            for card in cards:
                if card["url"] in existing_urls:
                    continue
                job_id = insert_job(db_path, {
                    "title": card["title"],
                    "company": card["company"],
                    "url": card["url"],
                    "source": "linkedin",
                    "location": card["location"],
                    "is_remote": 0,
                    "salary": "",
                    "description": "",
                    "date_found": datetime.now().isoformat()[:10],
                })
                if job_id:
                    from scripts.task_runner import submit_task
                    submit_task(db_path, "scrape_url", job_id)
                    existing_urls.add(card["url"])
                    new_leads += 1
                    print(f"[imap] LinkedIn alert → {card['company']} — {card['title']}")
            known_message_ids.add(mid)
            continue  # skip normal LLM extraction path

        if not _has_recruitment_keyword(parsed["subject"]):
            continue

        # Fast phrase-based rejection / ATS-confirm filter (catches what phi3 misses)
        if _has_rejection_or_ats_signal(parsed["subject"], parsed["body"]):
            continue

        # LLM classification as secondary gate — skip on rejection or classifier failure
        signal = classify_stage_signal(parsed["subject"], parsed["body"])
        if signal is None or signal == "rejected":
            continue

        company, title = extract_lead_info(
            parsed["subject"], parsed["body"], parsed["from_addr"]
        )
        if not company:
            continue

        from_domain = _extract_domain(parsed["from_addr"]) or "unknown"
        mid_hash = str(abs(hash(mid)))[:10]
        synthetic_url = f"email://{from_domain}/{mid_hash}"

        if synthetic_url in existing_urls:
            continue

        job_id = insert_job(db_path, {
            "title": title or "(untitled)",
            "company": company,
            "url": synthetic_url,
            "source": "email",
            "location": "",
            "is_remote": 0,
            "salary": "",
            "description": parsed["body"][:2000],
            "date_found": datetime.now().isoformat()[:10],
        })
        if job_id:
            _add_contact(db_path, job_id=job_id, direction="inbound",
                         subject=parsed["subject"],
                         from_addr=parsed["from_addr"],
                         body=parsed["body"],
                         received_at=parsed["date"][:16] if parsed["date"] else "",
                         message_id=mid)
            known_message_ids.add(mid)
            existing_urls.add(synthetic_url)
            new_leads += 1

    return new_leads


# ── IMAP connection ───────────────────────────────────────────────────────────

def load_config() -> dict:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(
            f"Email config not found: {CONFIG_PATH}\n"
            f"Copy config/email.yaml.example → config/email.yaml and fill it in."
        )
    return yaml.safe_load(CONFIG_PATH.read_text()) or {}


def connect(cfg: dict) -> imaplib.IMAP4:
    host = cfg.get("host", "imap.gmail.com")
    port = int(cfg.get("port", 993))
    use_ssl = cfg.get("use_ssl", True)
    conn = (imaplib.IMAP4_SSL if use_ssl else imaplib.IMAP4)(host, port)
    conn.login(cfg["username"], cfg["password"])
    return conn


def _detect_sent_folder(conn: imaplib.IMAP4) -> str:
    """Try to auto-detect the Sent folder name."""
    candidates = ["[Gmail]/Sent Mail", "Sent", "Sent Items", "Sent Messages", "INBOX.Sent"]
    try:
        _, folder_list = conn.list()
        flat = " ".join(f.decode() for f in (folder_list or []))
        for candidate in candidates:
            if candidate.lower() in flat.lower():
                return candidate
    except Exception:
        pass
    return "Sent"


def _quote_folder(name: str) -> str:
    """Quote an IMAP folder name if it contains spaces.
    Escapes internal backslashes and double-quotes per RFC 3501.
    e.g. 'TO DO JOBS' → '"TO DO JOBS"', 'My "Jobs"' → '"My \\"Jobs\\""'
    """
    if " " in name:
        escaped = name.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return name


def _search_folder(conn: imaplib.IMAP4, folder: str, criteria: str,
                   since: str) -> list[bytes]:
    """SELECT a folder and return matching UID list (empty on any error)."""
    try:
        conn.select(_quote_folder(folder), readonly=True)
        _, data = conn.search(None, f'(SINCE "{since}" {criteria})')
        return data[0].split() if data and data[0] else []
    except Exception:
        return []


def _parse_message(conn: imaplib.IMAP4, uid: bytes) -> Optional[dict]:
    """Fetch and parse one message.  Returns None on failure."""
    try:
        _, data = conn.fetch(uid, "(RFC822)")
        if not data or not data[0]:
            return None
        msg = email.message_from_bytes(data[0][1])

        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    try:
                        body = part.get_payload(decode=True).decode("utf-8", errors="replace")
                    except Exception:
                        pass
                    break
        else:
            try:
                body = msg.get_payload(decode=True).decode("utf-8", errors="replace")
            except Exception:
                pass

        mid = msg.get("Message-ID", "").strip()
        if not mid:
            return None  # No Message-ID → can't dedup; skip to avoid repeat inserts

        return {
            "message_id": mid,
            "subject":    _decode_str(msg.get("Subject")),
            "from_addr":  _decode_str(msg.get("From")),
            "to_addr":    _decode_str(msg.get("To")),
            "date":       _decode_str(msg.get("Date")),
            "body":       body[:4000],
        }
    except Exception:
        return None


# ── Per-job sync ──────────────────────────────────────────────────────────────

def _update_contact_signal(db_path: Path, contact_id: int, signal: str) -> None:
    """Write a stage signal onto an existing contact row."""
    import sqlite3 as _sqlite3
    conn = _sqlite3.connect(db_path)
    conn.execute(
        "UPDATE job_contacts SET stage_signal = ? WHERE id = ?",
        (signal, contact_id),
    )
    conn.commit()
    conn.close()


def sync_job_emails(job: dict, conn: imaplib.IMAP4, cfg: dict,
                    db_path: Path, dry_run: bool = False) -> tuple[int, int]:
    """
    Sync recruitment emails for one job.
    Returns (inbound_added, outbound_added).
    """
    company = (job.get("company") or "").strip()
    if not company:
        return 0, 0

    search_terms = _company_search_terms(company, job.get("url", ""))
    if not search_terms:
        return 0, 0

    lookback = int(cfg.get("lookback_days", 90))
    since = (datetime.now() - timedelta(days=lookback)).strftime("%d-%b-%Y")
    existing_ids = _get_existing_message_ids(job["id"], db_path)

    inbound = outbound = 0

    for term in search_terms:
        # ── INBOX — inbound ───────────────────────────────────────────────
        uids = _search_folder(
            conn, "INBOX",
            f'(OR FROM "{term}" SUBJECT "{term}")',
            since,
        )
        for uid in uids:
            parsed = _parse_message(conn, uid)
            if not parsed:
                continue
            if parsed["message_id"] in existing_ids:
                continue
            if not _email_is_relevant(parsed["from_addr"], parsed["subject"], search_terms):
                continue

            if not dry_run:
                contact_id = add_contact(
                    db_path, job_id=job["id"], direction="inbound",
                    subject=parsed["subject"], from_addr=parsed["from_addr"],
                    to_addr=parsed["to_addr"], body=parsed["body"],
                    received_at=parsed["date"][:16] if parsed["date"] else since,
                    message_id=parsed["message_id"],
                )
                signal = classify_stage_signal(parsed["subject"], parsed["body"])
                if signal and signal != "neutral":
                    _update_contact_signal(db_path, contact_id, signal)
            existing_ids.add(parsed["message_id"])
            inbound += 1

        # ── Sent — outbound ───────────────────────────────────────────────
        sent_folder = cfg.get("sent_folder") or _detect_sent_folder(conn)
        uids = _search_folder(
            conn, sent_folder,
            f'(OR TO "{term}" SUBJECT "{term}")',
            since,
        )
        for uid in uids:
            parsed = _parse_message(conn, uid)
            if not parsed:
                continue
            if parsed["message_id"] in existing_ids:
                continue
            if not _email_is_relevant(parsed["to_addr"], parsed["subject"], search_terms):
                continue

            if not dry_run:
                add_contact(
                    db_path, job_id=job["id"], direction="outbound",
                    subject=parsed["subject"], from_addr=parsed["from_addr"],
                    to_addr=parsed["to_addr"], body=parsed["body"],
                    received_at=parsed["date"][:16] if parsed["date"] else since,
                    message_id=parsed["message_id"],
                )
            existing_ids.add(parsed["message_id"])
            outbound += 1

    return inbound, outbound


# ── Main entry ────────────────────────────────────────────────────────────────

def sync_all(db_path: Path = DEFAULT_DB,
             dry_run: bool = False,
             job_ids: Optional[list[int]] = None,
             on_stage=None) -> dict:
    """
    Sync emails for all active pipeline jobs (or a specific subset).

    Returns a summary dict:
        {"synced": N, "inbound": N, "outbound": N, "errors": [...]}
    """
    def _stage(msg: str) -> None:
        if on_stage:
            on_stage(msg)

    cfg = load_config()
    init_db(db_path)

    jobs_by_stage = get_interview_jobs(db_path)
    active_stages = ["applied", "phone_screen", "interviewing", "offer", "hired"]
    all_active = [j for stage in active_stages for j in jobs_by_stage.get(stage, [])]

    if job_ids:
        all_active = [j for j in all_active if j["id"] in job_ids]

    if not all_active:
        return {"synced": 0, "inbound": 0, "outbound": 0, "new_leads": 0, "todo_attached": 0, "errors": []}

    _stage("connecting")
    print(f"[imap] Connecting to {cfg.get('host', 'imap.gmail.com')} …")
    conn = connect(cfg)
    summary = {"synced": 0, "inbound": 0, "outbound": 0, "new_leads": 0, "errors": []}

    try:
        for i, job in enumerate(all_active, 1):
            _stage(f"job {i}/{len(all_active)}")
            try:
                inb, out = sync_job_emails(job, conn, cfg, db_path, dry_run=dry_run)
                label = "DRY-RUN " if dry_run else ""
                print(f"[imap] {label}{job.get('company'):30s}  +{inb} in  +{out} out")
                if inb + out > 0:
                    summary["synced"] += 1
                summary["inbound"]  += inb
                summary["outbound"] += out
            except Exception as e:
                msg = f"{job.get('company')}: {e}"
                summary["errors"].append(msg)
                print(f"[imap] ERROR — {msg}")

        _stage("scanning todo label")
        from scripts.db import get_all_message_ids
        known_mids = get_all_message_ids(db_path)
        summary["todo_attached"] = _scan_todo_label(conn, cfg, db_path, all_active, known_mids)

        _stage("scanning leads")
        summary["new_leads"] = _scan_unmatched_leads(conn, cfg, db_path, known_mids)
    finally:
        try:
            conn.logout()
        except Exception:
            pass

    return summary


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Sync IMAP emails to job contacts")
    parser.add_argument("--job-id", type=int, nargs="+", help="Sync only these job IDs")
    parser.add_argument("--dry-run", action="store_true", help="Show matches without saving")
    args = parser.parse_args()

    result = sync_all(
        dry_run=args.dry_run,
        job_ids=args.job_id,
    )
    print(f"\n[imap] Done — {result['synced']} jobs updated, "
          f"{result['inbound']} inbound, {result['outbound']} outbound"
          + (f", {len(result['errors'])} errors" if result["errors"] else ""))
