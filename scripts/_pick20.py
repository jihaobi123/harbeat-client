"""Pick 20 random songs from library_songs for BPM accuracy test."""
from sqlalchemy import create_engine, text
import json

DB = 'postgresql+psycopg2://harbeat:Hb12345678@pgm-wz99am1godb1u59s3o.pg.rds.aliyuncs.com:5432/rhythm_prism'
e = create_engine(DB)

with e.connect() as c:
    rows = c.execute(text("""
        SELECT title, artist, source_path, duration, bpm
        FROM library_songs
        WHERE source_path IS NOT NULL
          AND analysis_status = 'completed'
        ORDER BY random()
        LIMIT 20
    """)).fetchall()

    songs = []
    for r in rows:
        songs.append({
            "title": r.title,
            "artist": r.artist,
            "path": r.source_path,
            "duration": float(r.duration) if r.duration else 0,
            "db_bpm": float(r.bpm) if r.bpm else None,
        })
        print(f"{r.title} | {r.artist} | dur={r.duration:.1f}s | db_bpm={r.bpm}")

    # Write as JSON for the batch test script
    with open("/tmp/_songs20.json", "w") as f:
        json.dump(songs, f, ensure_ascii=False, indent=2)
    print(f"\nWrote {len(songs)} songs to /tmp/_songs20.json")
