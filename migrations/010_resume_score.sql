-- 010_resume_score.sql
-- Holistic resume score (Forgejo #153): per-resume score + feedback, recomputed on demand.
ALTER TABLE resumes ADD COLUMN score INTEGER;
ALTER TABLE resumes ADD COLUMN ats_score INTEGER;
ALTER TABLE resumes ADD COLUMN feedback_json TEXT;
ALTER TABLE resumes ADD COLUMN scored_at TEXT;
