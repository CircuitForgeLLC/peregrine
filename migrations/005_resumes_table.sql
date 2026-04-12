-- 005_resumes_table.sql
-- Resume library: named saved resumes per user (optimizer output, imports, manual)

CREATE TABLE IF NOT EXISTS resumes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    source      TEXT NOT NULL DEFAULT 'manual',
    job_id      INTEGER REFERENCES jobs(id),
    text        TEXT NOT NULL,
    struct_json TEXT,
    word_count  INTEGER,
    is_default  INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

ALTER TABLE jobs ADD COLUMN resume_id INTEGER REFERENCES resumes(id);
