-- Migration 004: add resume_final_struct to jobs table
-- Stores the approved resume as a structured JSON dict alongside the plain text
-- (resume_optimized_text). Enables YAML export and future re-processing without
-- re-parsing the plain text.
ALTER TABLE jobs ADD COLUMN resume_final_struct TEXT;
