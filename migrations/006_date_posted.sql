-- 006_date_posted.sql
-- Add date_posted column for shadow listing detection (stale/shadow score feature).
-- New DBs already have this column from the CREATE TABLE statement in db.py;
-- this migration adds it to existing user DBs.

ALTER TABLE jobs ADD COLUMN date_posted TEXT;
