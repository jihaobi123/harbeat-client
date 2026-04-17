"""Check users in DB."""
import os
from sqlalchemy import create_engine, text

db_url = os.environ.get("DATABASE_URL", "")
e = create_engine(db_url)

with e.connect() as c:
    users = c.execute(text("SELECT id, username, email FROM users ORDER BY id")).fetchall()
    print(f"Users ({len(users)}):")
    for u in users:
        print(f"  id={u[0]}, username={u[1]}, email={u[2]}")
