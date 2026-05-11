import os

from sqlalchemy import create_engine, text

e = create_engine(os.environ.get("DATABASE_URL", "sqlite:///./data/harbeat_dev.db"))
with e.connect() as c:
    for row in c.execute(text("SELECT title, artist, source_path FROM library_songs WHERE title LIKE '%怪她%' OR title LIKE '%B-Boy%' ORDER BY title")):
        print(f'{row[0]} | {row[1]} | {row[2]}')
