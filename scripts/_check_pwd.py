"""Check password for user q."""
import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

db_url = os.environ.get("DATABASE_URL", "")
e = create_engine(db_url)

with e.connect() as c:
    row = c.execute(text("SELECT id, username, password_hash, status FROM users WHERE username='q'")).fetchone()
    if row:
        print(f"id={row[0]}, username={row[1]}, status={row[3]}")
        print(f"password_hash={row[2][:50]}...")
        
        # Try verify
        import sys
        sys.path.insert(0, "/app")
        from app.shared.security import verify_password
        result = verify_password("12345678", row[2])
        print(f"verify_password('12345678'): {result}")
    else:
        print("User 'q' not found!")
