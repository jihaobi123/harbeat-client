from sqlalchemy import create_engine, text
e = create_engine('postgresql+psycopg2://harbeat:Hb12345678@pgm-wz99am1godb1u59s3o.pg.rds.aliyuncs.com:5432/rhythm_prism')
with e.connect() as c:
    for row in c.execute(text("SELECT title, artist, source_path FROM library_songs WHERE title LIKE '%怪她%' OR title LIKE '%B-Boy%' ORDER BY title")):
        print(f'{row[0]} | {row[1]} | {row[2]}')
