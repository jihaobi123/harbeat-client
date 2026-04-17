from sqlalchemy import create_engine, text

DB = 'postgresql+psycopg2://harbeat:Hb12345678@pgm-wz99am1godb1u59s3o.pg.rds.aliyuncs.com:5432/rhythm_prism'
engine = create_engine(DB)

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
            WHERE title ILIKE :t AND artist ILIKE :a
            ORDER BY id
            """),
            {"t": f"%{t}%", "a": f"%{a}%"},
        ).fetchall()
        for r in rows:
            print(f"  id={r.id} | {r.title} | {r.artist} | bpm={r.bpm} | conf={r.beat_confidence} | engines={r.beat_engines_used}")

    print("\nUPDATING...")
    total = 0
    for t, a, bpm in fixes:
        result = conn.execute(
            text("""
            UPDATE library_songs
            SET bpm = :bpm,
                beat_confidence = GREATEST(COALESCE(beat_confidence, 0), 0.95),
                updated_at = NOW()
            WHERE title ILIKE :t AND artist ILIKE :a
            """),
            {"bpm": bpm, "t": f"%{t}%", "a": f"%{a}%"},
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
            WHERE title ILIKE :t AND artist ILIKE :a
            ORDER BY id
            """),
            {"t": f"%{t}%", "a": f"%{a}%"},
        ).fetchall()
        for r in rows:
            print(f"  id={r.id} | {r.title} | {r.artist} | bpm={r.bpm} | conf={r.beat_confidence}")
