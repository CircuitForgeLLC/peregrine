-- Resume review draft and version archive columns (migration 003)
ALTER TABLE jobs ADD COLUMN resume_draft_json TEXT;
ALTER TABLE jobs ADD COLUMN resume_archive_json TEXT;
