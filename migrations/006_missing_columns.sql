-- Migration 006: Add columns and tables present in the live DB but missing from migrations
-- These were added via direct ALTER TABLE after the v0.8.5 baseline was written.

-- date_posted: used for ghost-post shadow-score detection
ALTER TABLE jobs ADD COLUMN date_posted TEXT;

-- hired_feedback: JSON blob saved when a job reaches the 'hired' outcome
ALTER TABLE jobs ADD COLUMN hired_feedback TEXT;

-- references_ table: contacts who can provide references for applications
CREATE TABLE IF NOT EXISTS references_ (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT NOT NULL,
    relationship TEXT,
    company      TEXT,
    email        TEXT,
    phone        TEXT,
    notes        TEXT,
    tags         TEXT,
    prep_email   TEXT,
    role         TEXT
);
