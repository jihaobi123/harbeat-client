#!/usr/bin/env python3
"""Add DJ analysis columns to an existing library_songs table.

SQLAlchemy create_all() creates fresh tables but does not alter existing ones.
Run this once before deploying the enhanced analyzer.
"""
from __future__ import annotations

import os
import sys

from sqlalchemy import inspect, text

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.shared.database import engine


JSON_COLUMNS = {
    "bpm_curve": "[]",
    "energy_curve": "[]",
    "loudness_profile": "{}",
    "transition_windows": "[]",
    "stem_activity": "{}",
    "stem_activity_windows": "[]",
    "music_features": "{}",
    "dance_styles": "[]",
    "dance_style_scores": "{}",
}


def migrate() -> None:
    inspector = inspect(engine)
    if "library_songs" not in inspector.get_table_names():
        print("library_songs does not exist; create_all() will create the new columns")
        return

    existing = {column["name"] for column in inspector.get_columns("library_songs")}
    statements = []
    for column, default in JSON_COLUMNS.items():
        if column not in existing:
            statements.append(
                f"ALTER TABLE library_songs ADD COLUMN {column} JSON DEFAULT '{default}'"
            )
    if "tempo_stability" not in existing:
        statements.append(
            "ALTER TABLE library_songs ADD COLUMN tempo_stability FLOAT"
        )
    if "stem_quality_score" not in existing:
        statements.append(
            "ALTER TABLE library_songs ADD COLUMN stem_quality_score FLOAT"
        )
    for column in ("intro_is_clean", "outro_is_clean", "has_drum_loop"):
        if column not in existing:
            statements.append(
                f"ALTER TABLE library_songs ADD COLUMN {column} INTEGER DEFAULT 0"
            )
    if "dance_style_status" not in existing:
        statements.append(
            "ALTER TABLE library_songs ADD COLUMN dance_style_status VARCHAR(50) DEFAULT 'none'"
        )

    if not statements:
        print("library_songs DJ analysis columns already exist")
        return

    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))
            print(statement)

    print(f"added {len(statements)} DJ analysis column(s)")


if __name__ == "__main__":
    migrate()
