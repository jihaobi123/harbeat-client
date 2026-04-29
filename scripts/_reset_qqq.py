"""Reset password for qqq and test login."""
import os, sys
sys.path.insert(0, "/app")
from sqlalchemy import create_engine, text
from app.shared.security import hash_password

db_url = os.environ.get("DATABASE_URL", "")
e = create_engine(db_url)
new_hash = hash_password("12345678")
with e.begin() as c:
    c.execute(text("UPDATE users SET password_hash = :h WHERE username = 'qqq'"), {"h": new_hash})
    print("Password reset for 'qqq' to '12345678'")
