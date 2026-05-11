import os

from sqlalchemy import create_engine, text

e = create_engine(os.environ.get("DATABASE_URL", "sqlite:///./data/harbeat_dev.db"))
with e.connect() as c:
    # Find users with playlists
    rows = c.execute(text("""
        SELECT u.id, u.username, count(p.id) as playlist_count
        FROM users u
        JOIN playlists p ON p.user_id = u.id
        GROUP BY u.id, u.username
        ORDER BY playlist_count DESC LIMIT 5
    """)).fetchall()
    print("=== Users with playlists ===")
    for r in rows:
        print(f"  user={r[1]} (id={r[0]}) playlists={r[2]}")
        # Show playlist details
        pls = c.execute(text(f"SELECT id, name, (SELECT count(*) FROM playlist_songs WHERE playlist_id=p.id) FROM playlists p WHERE user_id={r[0]}")).fetchall()
        for p in pls:
            print(f"    playlist_id={p[0]} name={p[1]} songs={p[2]}")
