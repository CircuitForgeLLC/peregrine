-- 007_resume_sync.sql
-- Add synced_at to resumes: ISO datetime of last library↔profile sync, null = never synced.
ALTER TABLE resumes ADD COLUMN synced_at TEXT;
