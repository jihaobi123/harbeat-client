from sqlalchemy import create_engine, text
DB_URL = 'postgresql://harbeat:Hb12345678@pgm-wz99am1godb1u59s3o.pg.rds.aliyuncs.com:5432/rhythm_prism'
e = create_engine(DB_URL)
with e.connect() as c:
    users = c.execute(text("SELECT id, username, password_hash, status FROM users LIMIT 10")).fetchall()
    print("=== Users ===")
    for u in users:
        has_pw = "YES" if u[2] else "NO"
        pw_prefix = u[2][:30] if u[2] else "NULL"
        print(f"  id={u[0]} user={u[1]} status={u[3]} has_pw={has_pw} hash_prefix={pw_prefix}")
