import json
import sqlite3
import time
import uuid
from pathlib import Path

ACTIVE = ('queued', 'downloading', 'transferring', 'analyzing', 'publishing')


class Jobs:
    """One durable queue, one worker. Payloads and source paths never leave the API."""
    def __init__(self, root, limit=16):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / 'jobs.sqlite3'
        self.limit = limit
        with self.connect() as db:
            db.executescript('''
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY, dedup TEXT UNIQUE NOT NULL, status TEXT NOT NULL,
                    title TEXT NOT NULL, payload TEXT NOT NULL, message TEXT NOT NULL DEFAULT '',
                    track_id TEXT, created REAL NOT NULL, updated REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS candidates (
                    id TEXT PRIMARY KEY, payload TEXT NOT NULL, created REAL NOT NULL);
            ''')
        self.path.chmod(0o600)

    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        return db

    def submit_many(self, requests):
        result = []
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            active = db.execute("SELECT count(*) FROM jobs WHERE status IN ('queued','downloading','transferring','analyzing','publishing')").fetchone()[0]
            for key, payload in requests:
                row = db.execute('SELECT * FROM jobs WHERE dedup=?', (key,)).fetchone()
                if row is None:
                    if active >= self.limit:
                        raise ValueError('导入队列已满，请等当前任务完成后再添加。')
                    identifier, now = uuid.uuid4().hex, time.time()
                    db.execute('INSERT INTO jobs (id,dedup,status,title,payload,created,updated) VALUES (?,?,?,?,?,?,?)',
                               (identifier, key, 'queued', payload.get('title', '新音乐'), json.dumps(payload), now, now))
                    row = db.execute('SELECT * FROM jobs WHERE id=?', (identifier,)).fetchone()
                    active += 1
                result.append(dict(row))
        return result

    def submit(self, key, payload):
        return self.submit_many([(key, payload)])[0]

    def get(self, identifier):
        with self.connect() as db:
            row = db.execute('SELECT * FROM jobs WHERE id=?', (identifier,)).fetchone()
        if not row:
            raise ValueError('找不到这个导入任务。')
        return dict(row)

    def public(self, identifier):
        return {k: v for k, v in self.get(identifier).items() if k not in ('payload', 'dedup')}

    def list_public(self):
        with self.connect() as db:
            ids = [r[0] for r in db.execute('SELECT id FROM jobs ORDER BY created DESC LIMIT 100')]
        return [self.public(i) for i in ids]

    def update(self, identifier, **changes):
        if not changes.keys() <= {'status', 'message', 'track_id', 'payload'}:
            raise ValueError('invalid job update')
        if 'payload' in changes:
            changes['payload'] = json.dumps(changes['payload'])
        changes['updated'] = time.time()
        with self.connect() as db:
            db.execute('UPDATE jobs SET '+','.join(k+'=?' for k in changes)+' WHERE id=?', (*changes.values(), identifier))

    def recover(self):
        with self.connect() as db:
            db.execute("UPDATE jobs SET status='queued',message='服务恢复，等待继续处理' WHERE status IN ('downloading','transferring','analyzing','publishing')")

    def claim(self):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute("SELECT * FROM jobs WHERE status='queued' ORDER BY created LIMIT 1").fetchone()
            if row:
                db.execute("UPDATE jobs SET status='transferring',updated=? WHERE id=?", (time.time(), row['id']))
                return {**dict(row), 'payload': json.loads(row['payload'])}
        return None

    def retry(self, identifier):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT status FROM jobs WHERE id=?', (identifier,)).fetchone()
            if not row or row[0] != 'failed':
                raise ValueError('只有失败的任务可以重试。')
            count = db.execute("SELECT count(*) FROM jobs WHERE status IN ('queued','downloading','transferring','analyzing','publishing')").fetchone()[0]
            if count >= self.limit:
                raise ValueError('导入队列已满。')
            db.execute("UPDATE jobs SET status='queued',message='',updated=? WHERE id=?", (time.time(), identifier))
        return self.public(identifier)

    def candidate(self, value):
        identifier = uuid.uuid4().hex
        with self.connect() as db:
            db.execute('DELETE FROM candidates WHERE created < ?', (time.time()-86400,))
            db.execute('INSERT INTO candidates VALUES (?,?,?)', (identifier, json.dumps(value), time.time()))
        return {**value, 'candidate_id': identifier}

    def resolve_candidate(self, identifier):
        with self.connect() as db:
            row = db.execute('SELECT payload FROM candidates WHERE id=? AND created>?', (identifier, time.time()-86400)).fetchone()
        if not row:
            raise ValueError('音源匹配已过期，请重新搜索。')
        return json.loads(row[0])
