from sqlalchemy import create_engine, text
e = create_engine('postgresql+psycopg2://harbeat:Hb12345678@pgm-wz99am1godb1u59s3o.pg.rds.aliyuncs.com:5432/rhythm_prism')
with e.connect() as c:
    rows = c.execute(text("""
        SELECT id, title, artist, source_path, duration
        FROM library_songs
        WHERE source_path IS NOT NULL AND analysis_status = 'completed'
        ORDER BY RANDOM()
        LIMIT 10
    """)).fetchall()
    for r in rows:
        print(f"{r[1]}|{r[2]}|{r[3]}|{r[4]}")
