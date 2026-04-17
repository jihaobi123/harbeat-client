import sys
sys.path.insert(0, "/home/mark/harbeat")
from sqlalchemy import create_engine, text
from app.shared.config import get_settings

s = get_settings()
e = create_engine(s.database_url)
with e.connect() as c:
    users = c.execute(text("SELECT id, username, email FROM users LIMIT 10")).fetchall()
    total_songs = c.execute(text("SELECT count(*) FROM songs")).scalar()
    analyzed = c.execute(text("SELECT count(*) FROM songs WHERE bpm IS NOT NULL")).scalar()
    with_stems = c.execute(text("SELECT count(*) FROM songs WHERE stems IS NOT NULL")).scalar()
    playlists = c.execute(text("SELECT count(*) FROM playlists")).scalar()
    print(f"=== Users ({len(users)}) ===")
    for u in users:
        print(f"  id={u[0]} user={u[1]} email={u[2]}")
    print(f"\n=== Songs ===")
    print(f"  Total: {total_songs}")
    print(f"  Analyzed (BPM): {analyzed}")
    print(f"  With stems: {with_stems}")
    print(f"\n=== Playlists: {playlists} ===")
