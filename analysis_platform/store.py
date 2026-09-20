"""Atomic local artifacts, separate from every existing HarBeat data store."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import tempfile
import fcntl
import errno
import logging
import threading
import time

from .report import canonical, validate_report


class Store:
    def __init__(self, root: Path):
        self.root = root.resolve()
        # SMB targets cannot always be replaced while an API reader holds them.
        self._locks_guard = threading.Lock()
        self._path_locks = {}
        self._job_summaries = {}
        for part in ['reports', 'jobs', 'audio', 'media']:
            (self.root / part).mkdir(parents=True, exist_ok=True)

    def path(self, group, identifier, suffix='.json'):
        if group not in ('reports', 'jobs', 'audio', 'media') or not re.fullmatch(r'[a-f0-9]{32,64}', identifier):
            raise ValueError('invalid artifact identifier')
        return self.root / group / (identifier + suffix)

    def _lock_for(self,path):
        key=os.path.abspath(path)
        with self._locks_guard:
            return self._path_locks.setdefault(key,threading.RLock())

    def write(self, path, value):
        with self._lock_for(path):
            self._job_summaries.pop(path,None)
            self._write(path,value)

    def _write(self,path,value):
        fd, temp = tempfile.mkstemp(dir=path.parent, prefix='.write-')
        staged=False
        try:
            with os.fdopen(fd, 'wb') as out:
                out.write(canonical(value))
                out.flush()
                os.fsync(out.fileno())
            staged=True
            for attempt in range(6):
                try:
                    os.replace(temp, path)
                    break
                except OSError as exc:
                    if exc.errno not in (errno.EACCES,errno.EBUSY,errno.EAGAIN) or attempt==5:
                        logging.getLogger(__name__).error('atomic publish failed; staged result retained at %s for target %s',temp,path)
                        raise
                    logging.getLogger(__name__).warning('atomic publish retry target=%s errno=%s attempt=%s',path.name,exc.errno,attempt+1)
                    time.sleep(.05*2**attempt)
        finally:
            # A completed rename consumes temp. On failure keep the fsynced payload
            # for recovery: an SMB replacement can leave its target delete-pending.
            if not staged and os.path.exists(temp):
                os.unlink(temp)

    def read(self,path):
        with self._lock_for(path):
            for attempt in range(6):
                try:
                    text=path.read_text()
                    break
                except OSError as exc:
                    if exc.errno not in (errno.ENOENT,errno.EACCES,errno.EBUSY) or attempt==5:raise
                    time.sleep(.05*2**attempt)
        return json.loads(text)

    def save_report(self, report):
        path = self.path('reports', report['id'])
        if not path.exists():
            self.write(path, report)
        with (self.root/'report-index.lock').open('a+') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            index_path=self.root/'report-index.json'
            index=self.read(index_path) if index_path.is_file() else self._scan_report_index()
            if report['id'] not in index or not index_path.is_file():
                index[report['id']]={k:report.get(k) for k in ['id','title','created_at','summary','audio']}
                self.write(index_path,index)

    def get_report(self, identifier):
        return validate_report(self.read(self.path('reports', identifier)))

    def save_job(self, job):
        self.write(self.path('jobs', job['id']), job)

    def get_job(self, identifier):
        return self.read(self.path('jobs', identifier))

    def reports(self):
        path=self.root/'report-index.json'
        if not path.is_file():self.rebuild_report_index()
        result=sorted(self.read(path).values(),key=lambda r:r.get('created_at') or '',reverse=True)
        # The picker only needs identity and summary; loading every media record
        # across the relay delays opening a single song by several seconds.
        return [{**r,'audio':{k:v for k,v in (r.get('audio') or {}).items() if k!='assets'}} for r in result]

    def rebuild_report_index(self):
        with (self.root/'report-index.lock').open('a+') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            self.write(self.root/'report-index.json',self._scan_report_index())

    def _scan_report_index(self):
        index={}
        for path in (self.root/'reports').glob('*.json'):
            r=self.read(path)
            index[r['id']]={k:r.get(k) for k in ['id','title','created_at','summary','audio']}
        return index

    def jobs(self):
        def modified(path):
            for attempt in range(6):
                try:return path.stat()
                except OSError as exc:
                    if exc.errno not in (errno.ENOENT,errno.EACCES,errno.EBUSY) or attempt==5:raise
                    time.sleep(.05*2**attempt)
        result = []
        for path in (self.root / 'jobs').glob('*.json'):
            with self._lock_for(path):
                stat=modified(path)
                stamp=(stat.st_mtime_ns,stat.st_size,stat.st_ino)
                cached=self._job_summaries.get(path)
                if cached is None or cached[0]!=stamp:
                    job=self.read(path)
                    summary={k:job.get(k) for k in ['id','status','module','reason','created_at','source_report_id','report_id']}
                    self._job_summaries[path]=(stamp,summary)
                else:summary=cached[1]
                result.append((stat.st_mtime_ns,dict(summary)))
        return [summary for _,summary in sorted(result,key=lambda row:row[0],reverse=True)]

    def recover(self):
        for path in (self.root / 'jobs').glob('*.json'):
            job = self.read(path)
            if job.get('status') in ('queued', 'running'):
                job.update(status='interrupted', reason='服务在任务完成前停止；原报告保持不变，可重新运行')
                self.save_job(job)
