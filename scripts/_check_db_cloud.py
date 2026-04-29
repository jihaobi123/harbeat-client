from sqlalchemy import create_engine, text
DB_URL = 'postgresql://harbeat:Hb12345678@pgm-wz99am1godb1u59s3o.pg.rds.aliyuncs.com:5432/rhythm_prism'
e = create_engine(DB_URL)
with e.connect() as c:
    users = c.execute(text('SELECT id, username, email FROM users LIMIT 10')).fetchall()
    total_songs = c.execute(text('SELECT count(*) FROM songs')).scalar()
    with_tags = c.execute(text('SELECT count(*) FROM song_tags WHERE bpm IS NOT NULL')).scalar()
    with_audio = c.execute(text("SELECT count(*) FROM songs WHERE audio_url IS NOT NULL")).scalar()
    playlists = c.execute(text('SELECT count(*) FROM playlists')).scalar()
    playlist_songs = c.execute(text('SELECT count(*) FROM playlist_songs')).scalar()
    sample = c.execute(text('SELECT id, title, artist FROM songs LIMIT 5')).fetchall()
    print(f'=== Users ({len(users)}) ===')
    for u in users:
        print(f'  id={u[0]} user={u[1]} email={u[2]}')
    print(f'\n=== Songs ===')
    print(f'  Total: {total_songs}')
    print(f'  With audio_url: {with_audio}')
    print(f'  With BPM tags: {with_tags}')
    print(f'\n=== Sample songs ===')
    for s in sample:
        print(f'  id={s[0]} {s[1]} - {s[2]}')
    print(f'\n=== Playlists: {playlists} (songs: {playlist_songs}) ===')
