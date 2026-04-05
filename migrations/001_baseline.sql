-- Migration 001: Baseline schema
-- Captures the full schema as of v0.8.5 (all columns including those added via ALTER TABLE)

CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT,
    company TEXT,
    url TEXT UNIQUE,
    source TEXT,
    location TEXT,
    is_remote INTEGER DEFAULT 0,
    salary TEXT,
    description TEXT,
    match_score REAL,
    keyword_gaps TEXT,
    date_found TEXT,
    status TEXT DEFAULT 'pending',
    notion_page_id TEXT,
    cover_letter TEXT,
    applied_at TEXT,
    interview_date TEXT,
    rejection_stage TEXT,
    phone_screen_at TEXT,
    interviewing_at TEXT,
    offer_at TEXT,
    hired_at TEXT,
    survey_at TEXT,
    calendar_event_id TEXT,
    optimized_resume TEXT,
    ats_gap_report TEXT
);

CREATE TABLE IF NOT EXISTS job_contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER,
    direction TEXT,
    subject TEXT,
    from_addr TEXT,
    to_addr TEXT,
    body TEXT,
    received_at TEXT,
    is_response_needed INTEGER DEFAULT 0,
    responded_at TEXT,
    message_id TEXT,
    stage_signal TEXT,
    suggestion_dismissed INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS company_research (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER UNIQUE,
    generated_at TEXT,
    company_brief TEXT,
    ceo_brief TEXT,
    talking_points TEXT,
    raw_output TEXT,
    tech_brief TEXT,
    funding_brief TEXT,
    competitors_brief TEXT,
    red_flags TEXT,
    scrape_used INTEGER DEFAULT 0,
    accessibility_brief TEXT
);

CREATE TABLE IF NOT EXISTS background_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_type TEXT,
    job_id INTEGER,
    params TEXT,
    status TEXT DEFAULT 'pending',
    error TEXT,
    created_at TEXT,
    started_at TEXT,
    finished_at TEXT,
    stage TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS survey_responses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER,
    survey_name TEXT,
    received_at TEXT,
    source TEXT,
    raw_input TEXT,
    image_path TEXT,
    mode TEXT,
    llm_output TEXT,
    reported_score REAL,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS digest_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_contact_id INTEGER UNIQUE,
    created_at TEXT
);
