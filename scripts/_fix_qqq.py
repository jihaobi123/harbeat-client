import sys, os
sys.path.insert(0, '/app')
from sqlalchemy import create_engine, text
from app.shared.security import verify_password, hash_password

e = create_engine(os.environ['DATABASE_URL'])
with e.connect() as c:
    row = c.execute(text("SELECT id, username, password_hash, status FROM users WHERE username='qqq'")).fetchone()
    print(f"id={row[0]}, username={row[1]}, status={row[3]}")
    print(f"verify '12345678': {verify_password('12345678', row[2])}")

# Re-fix password
with e.begin() as c:
    new_hash = hash_password("12345678")
    c.execute(text("UPDATE users SET password_hash = :h WHERE username = 'qqq'"), {"h": new_hash})
    print("Password re-reset to '12345678'")

# Verify again
with e.connect() as c:
    row = c.execute(text("SELECT password_hash FROM users WHERE username='qqq'")).fetchone()
    print(f"verify after reset: {verify_password('12345678', row[0])}")
