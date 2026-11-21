-- 011_experience_facts.sql
-- What the user tells us about each resume gap, stored as reusable facts.
-- Additive only: no existing table is touched.
CREATE TABLE IF NOT EXISTS experience_facts (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    kind          TEXT NOT NULL CHECK (kind IN ('experience','adjacent','none')),
    requirement   TEXT NOT NULL,
    text          TEXT NOT NULL DEFAULT '',
    visibility    TEXT NOT NULL DEFAULT 'document' CHECK (visibility IN ('document','private')),
    status        TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','retired')),
    source        TEXT NOT NULL DEFAULT 'card' CHECK (source IN ('card','chat','manual')),
    origin_job_id INTEGER,
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_experience_facts_status_requirement
    ON experience_facts (status, requirement);
