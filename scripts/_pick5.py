from sqlalchemy import create_engine, text
e = create_engine('postgresql+psycopg2://harbeat:Hb12345678@pgm-wz99am1godb1u59s3o.pg.rds.aliyuncs.com:5432/rhythm_prism')
with e.connect() as c:
    rows = c.execute(text("""
        SELECT id, title, artist, bpm, beat_confidence, beat_engines_used, beat_grid_interval,
               source_path, analysis_status, duration
        FROM library_songs
        WHERE source_path IS NOT NULL AND analysis_status = 'completed'
        ORDER BY RANDOM()
        LIMIT 5
    """)).fetchall()
    for r in rows:
        print(f"ID={r[0]}|TITLE={r[1]}|ARTIST={r[2]}|BPM={r[3]}|CONF={r[4]}|ENGINES={r[5]}|INTERVAL={r[6]}|PATH={r[7]}|DUR={r[9]}")
