-- Add ATS resume optimizer columns introduced in v0.8.x.
-- Existing DBs that were created before the baseline included these columns
-- need this migration to add them. Safe to run on new DBs: IF NOT EXISTS guards
-- are not available for ADD COLUMN in SQLite, so we use a try/ignore pattern
-- at the application level (db_migrate.py wraps each migration in a transaction).
ALTER TABLE jobs ADD COLUMN optimized_resume TEXT;
ALTER TABLE jobs ADD COLUMN ats_gap_report TEXT;
