-- Migration: Add multi-engine beat analysis columns to library_songs
-- Run against the PostgreSQL RDS database

ALTER TABLE library_songs
    ADD COLUMN IF NOT EXISTS beat_confidence FLOAT,
    ADD COLUMN IF NOT EXISTS beat_grid_offset FLOAT,
    ADD COLUMN IF NOT EXISTS beat_grid_interval FLOAT,
    ADD COLUMN IF NOT EXISTS beat_engines_used JSON NOT NULL DEFAULT '[]',
    ADD COLUMN IF NOT EXISTS beat_needs_review INTEGER NOT NULL DEFAULT 0;
