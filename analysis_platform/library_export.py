"""Read-only snapshot of every persisted analysis column, not a reduced schema."""
from __future__ import annotations

from datetime import date, datetime

from .report import build_report


def song_report(song):
    # Storage locations and account ownership are not music measurements.
    omitted = {'source_path', 'user_id', 'platform_url'}
    values = {}
    for column in song.__table__.columns:
        if column.name in omitted:
            continue
        value = getattr(song, column.name)
        values[column.name] = value.isoformat() if isinstance(value, (datetime, date)) else value
    return build_report({'core': values})
