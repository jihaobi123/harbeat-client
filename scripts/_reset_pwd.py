"""Reset password for user q and test login."""
import os
import sys
sys.path.insert(0, "/app")

from sqlalchemy import create_engine, text
from app.shared.security import hash_password

db_url = os.environ.get("DATABASE_URL", "")
e = create_engine(db_url)

new_hash = hash_password("12345678")
print(f"New hash: {new_hash[:50]}...")

with e.begin() as c:
    c.execute(text("UPDATE users SET password_hash = :h WHERE username = 'q'"), {"h": new_hash})
    print("Password reset for user 'q' to '12345678'")

# Verify
from app.shared.security import verify_password
with e.connect() as c:
    row = c.execute(text("SELECT password_hash FROM users WHERE username='q'")).fetchone()
    print(f"Verify: {verify_password('12345678', row[0])}")
