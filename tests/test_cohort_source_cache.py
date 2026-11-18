import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from analysis_platform.cohort_source_cache import cache_run
from metric_mix.prepare import sha


class ApprovedSourceCacheTest(unittest.TestCase):
    def test_only_copies_the_approved_run_and_reuses_it(self):
        with TemporaryDirectory() as directory:
            base = Path(directory)
            nas, cache = base / 'nas', base / 'cache'
            tid, run = 'track-' + 'a' * 20, 'run-1'
            relative = Path('published/tracks') / tid / 'runs' / run
            source = nas / relative
            source.mkdir(parents=True)
            names = ('master', 'bass', 'drums', 'vocals', 'other')
            assets = {}
            for name in names:
                file = source / (name + '.wav')
                file.write_text(name)
                assets[name] = {'storage_key': str(relative / file.name)}
            manifest = source / 'manifest.json'
            manifest.write_text(json.dumps({'assets': {
                'master': assets['master'],
                'stems': {name: assets[name] for name in names[1:]},
            }}))
            checksum = sha(manifest)
            (source / '_SUCCESS.json').write_text(json.dumps({'manifest_sha256': checksum}))
            track = {'id': tid, 'provenance': {'runId': run}}
            with self.assertRaises(ValueError):
                cache_run(track, {'manifestSha256': '0' * 64}, nas, cache)
            self.assertFalse((cache / relative).exists())
            with patch('analysis_platform.cohort_source_cache.MIN_FREE_BYTES', 0):
                self.assertEqual(cache_run(track, {'manifestSha256': checksum}, nas, cache), cache)
            self.assertEqual((cache / relative / 'vocals.wav').read_text(), 'vocals')
            with patch('analysis_platform.cohort_source_cache.shutil.copyfile', side_effect=AssertionError):
                self.assertEqual(cache_run(track, {'manifestSha256': checksum}, nas, cache), cache)
