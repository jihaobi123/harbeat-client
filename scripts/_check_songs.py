"""Check which users have library songs."""
import os
from sqlalchemy import create_engine, text

db_url = os.environ.get("DATABASE_URL", "")
e = create_engine(db_url)

with e.connect() as c:
    rows = c.execute(text(
        "SELECT user_id, count(*) as cnt FROM library_songs GROUP BY user_id ORDER BY cnt DESC"
    )).fetchall()
    print("Library songs per user:")
    for r in rows:
        user = c.execute(text("SELECT username FROM users WHERE id = :uid"), {"uid": r[0]}).fetchone()
        uname = user[0] if user else "unknown"
        print(f"  user_id={r[0]} ({uname}): {r[1]} songs")
    
    # Also check if there are any analyzed songs
    analyzed = c.execute(text(
        "SELECT user_id, count(*) as cnt FROM library_songs WHERE analysis_status != 'none' GROUP BY user_id"
    )).fetchall()
    print("\nAnalyzed songs per user:")
    for r in analyzed:
        user = c.execute(text("SELECT username FROM users WHERE id = :uid"), {"uid": r[0]}).fetchone()
        uname = user[0] if user else "unknown"
        print(f"  user_id={r[0]} ({uname}): {r[1]} analyzed")
