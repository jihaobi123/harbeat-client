import os

from sqlalchemy import create_engine, text

e = create_engine(os.environ.get("DATABASE_URL", "sqlite:///./data/harbeat_dev.db"))
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
