"""Read an approved, additive device-execution cohort."""
import json
from pathlib import Path
import re

TRACK = re.compile(r'track-[a-f0-9]{20}')


def execution_index(root):
    path = root / 'index.json'
    if path.stat().st_size > 8 * 1024**2:
        raise ValueError('execution index too large')
    value = json.loads(path.read_bytes())
    rows = value['tracks']
    if (value['schema'] != 'harbeat.execution-library.v1'
            or not isinstance(rows, list) or len(rows) > 5000
            or any(not isinstance(row, dict) for row in rows)):
        raise ValueError('execution index invalid')
    return value


class ExecutionCohort:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.execution = self.root / 'execution'
        self.tracks = {}
        index = self.root / 'catalog' / 'library.json'
        if not index.is_file():
            return
        if index.stat().st_size > 1024**2:
            raise ValueError('cohort library too large')
        library = json.loads(index.read_bytes())
        rows = library['tracks']
        if (library['schema'] != 'harbeat.continuous-library.v1'
                or library.get('executionPolicy') != 'device-native-windows-v1'
                or not isinstance(rows, list) or len(rows) > 256):
            raise ValueError('cohort library invalid')
        for row in rows:
            tid = row['id']
            if not TRACK.fullmatch(tid) or tid in self.tracks or (
                row['playStatus'] != 'ready' or row['mixStatus'] != 'ready'
            ):
                raise ValueError('cohort source invalid')
            self.tracks[tid] = row

    def detail(self, tid):
        row = self.tracks[tid]
        path = self.root / 'catalog' / 'details' / (tid + '.json')
        if path.stat().st_size > 8 * 1024**2:
            raise ValueError('cohort detail too large')
        track = json.loads(path.read_bytes())['track']
        if (track['id'] != tid or track['bpm'] != row['bpm']
                or abs(track['duration'] - row['duration']) > 1 / 44100):
            raise ValueError('cohort detail identity mismatch')
        return track

    def merged_index(self, base):
        index = execution_index(base)
        if not self.tracks:
            return index
        supplemental = execution_index(self.execution)
        rows = {row['trackId']: row for row in index['tracks']}
        admitted = set()
        for row in supplemental['tracks']:
            tid = row['trackId']
            if tid not in self.tracks or tid in admitted or row.get('assetsReady') is not True:
                raise ValueError('cohort execution source invalid')
            admitted.add(tid)
            if tid not in rows or not rows[tid].get('assetsReady'):
                rows[tid] = row
        if admitted != self.tracks.keys():
            raise ValueError('cohort execution is incomplete')
        return {**index, 'tracks': list(rows.values())}
