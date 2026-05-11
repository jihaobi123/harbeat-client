import os

from sqlalchemy import create_engine, text

engine = create_engine(os.environ.get("DATABASE_URL", "sqlite:///./data/harbeat_dev.db"))
_dialect = engine.dialect.name
_beat_bump = (
    "GREATEST(COALESCE(beat_confidence, 0), 0.95)"
    if _dialect == "postgresql"
    else "MAX(COALESCE(beat_confidence, 0), 0.95)"
)
_ts_now = "NOW()" if _dialect == "postgresql" else "datetime('now')"

fixes = [
    # title_like, artist_like, bpm
    ("不怪她 (Blame)", "HARIKIRI", 80.0),
    ("One B-Boy", "Dj Pablo", 126.0),
    ("It's Been A Long Time", "Rakim", 89.0),
    ("So Many Ways", "Warren G", 95.0),
]

with engine.begin() as conn:
    print("BEFORE:")
    for t, a, _ in fixes:
        rows = conn.execute(
            text("""
            SELECT id, title, artist, bpm, beat_confidence, beat_engines_used
            FROM library_songs
            WHERE lower(title) LIKE :t AND lower(artist) LIKE :a
            ORDER BY id
            """),
            {"t": f"%{t.lower()}%", "a": f"%{a.lower()}%"},
        ).fetchall()
        for r in rows:
            print(f"  id={r.id} | {r.title} | {r.artist} | bpm={r.bpm} | conf={r.beat_confidence} | engines={r.beat_engines_used}")

    print("\nUPDATING...")
    total = 0
    for t, a, bpm in fixes:
        result = conn.execute(
            text(f"""
            UPDATE library_songs
            SET bpm = :bpm,
                beat_confidence = {_beat_bump},
                updated_at = {_ts_now}
            WHERE lower(title) LIKE :t AND lower(artist) LIKE :a
            """),
            {"bpm": bpm, "t": f"%{t.lower()}%", "a": f"%{a.lower()}%"},
        )
        total += result.rowcount or 0
        print(f"  {t} / {a} -> bpm={bpm} | affected={result.rowcount}")

    print(f"\nTotal updated rows: {total}")

    print("\nAFTER:")
    for t, a, _ in fixes:
        rows = conn.execute(
            text("""
            SELECT id, title, artist, bpm, beat_confidence
            FROM library_songs
            WHERE lower(title) LIKE :t AND lower(artist) LIKE :a
            ORDER BY id
            """),
            {"t": f"%{t.lower()}%", "a": f"%{a.lower()}%"},
        ).fetchall()
        for r in rows:
            print(f"  id={r.id} | {r.title} | {r.artist} | bpm={r.bpm} | conf={r.beat_confidence}")
