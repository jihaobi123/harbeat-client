"""Server-written allowlist for existing NAS audio; clients never supply paths."""
import json
import hashlib
from pathlib import Path

from .report import digest


class MediaRegistry:
    def __init__(self, store, roots):
        self.store = store
        self.roots = [Path(p).resolve() for p in roots]

    def checked_path(self, path):
        path = Path(path).resolve(strict=True)
        if not any(path.is_relative_to(root) for root in self.roots):
            raise ValueError('audio path is outside configured media roots')
        if not path.is_file() or path.suffix.lower() not in {'.wav', '.flac', '.mp3', '.ogg', '.m4a', '.audio'}:
            raise ValueError('unsupported media file')
        return path

    def register(self, path, declared_sha256=None):
        import soundfile as sf
        path = self.checked_path(path)
        stat = path.stat()
        record = {'path': str(path), 'size': stat.st_size, 'mtime_ns': stat.st_mtime_ns}
        identifier = digest(record)
        cached = self.store.path('media', identifier)
        if cached.is_file():
            return json.loads(cached.read_text())['public']
        info = sf.info(path)
        public = {'id': identifier, 'duration': info.duration, 'sample_rate': info.samplerate,
                  'channels': info.channels, 'size_bytes': stat.st_size, 'filename': path.name,
                  'declared_sha256': declared_sha256, 'status': 'available'}
        self.store.write(cached, {**record, 'public': public})
        return public

    def resolve(self, identifier):
        record = json.loads(self.store.path('media', identifier).read_text())
        path = self.checked_path(record['path'])
        stat = path.stat()
        if stat.st_size != record['size'] or stat.st_mtime_ns != record['mtime_ns']:
            raise ValueError('registered audio changed; refresh source catalog')
        return path

    def verify(self, identifier):
        path=self.resolve(identifier)
        record_path=self.store.path('media',identifier)
        record=json.loads(record_path.read_text())
        if record.get('verified_sha256'):return record['verified_sha256']
        sha=hashlib.sha256()
        with path.open('rb') as source:
            for block in iter(lambda:source.read(1024*1024),b''):sha.update(block)
        self.resolve(identifier)
        value=sha.hexdigest()
        declared=record['public'].get('declared_sha256')
        if declared and value!=declared:raise ValueError('audio checksum differs from source manifest')
        record['verified_sha256']=value
        self.store.write(record_path,record)
        return value
