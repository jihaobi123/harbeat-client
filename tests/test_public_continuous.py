"""Cloud delivery must be complete, source bound, and independent of the NAS URLs."""
import copy
import hashlib
import importlib
import json
from pathlib import Path
import tempfile
import unittest


class PublicContinuousTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.corpus = self.root / 'corpus'
        self.store = self.root / 'store'
        self.out = self.root / 'public'
        for directory in [self.corpus / 'details', self.store / 'media']:
            directory.mkdir(parents=True)
        self.audio = self.root / 'native.flac'
        self.audio.write_bytes(b'unchanged source audio')
        self.sha = hashlib.sha256(self.audio.read_bytes()).hexdigest()
        self.identifier = 'a' * 64
        self.asset = dict(url='/api/analysis-lab/media/' + self.identifier,
                          sha256=self.sha, bytes=self.audio.stat().st_size, duration=10)
        (self.store / 'media' / (self.identifier + '.json')).write_text(json.dumps({
            'path': str(self.audio), 'size': self.audio.stat().st_size,
            'mtime_ns': self.audio.stat().st_mtime_ns,
            'public': {'declared_sha256': self.sha}}))
        self.track = dict(id='one', native=copy.deepcopy(self.asset),
                          audioSegments=[{'start': 0, 'end': 10, 'asset': copy.deepcopy(self.asset)}],
                          windows=[{'variants': {'two': copy.deepcopy(self.asset)}}],
                          provenance={'masterSha256': 'original'},
                          preprocessing={'vocalActivity': {'intervals': []},
                                         'reportSnapshotUrl': '/old/evidence/x.json'})
        (self.corpus / 'details' / 'one.json').write_text(json.dumps({'track': self.track}))
        self.index = dict(schema='harbeat.continuous-library.v1', tracks=[{
            'id': 'one', 'playStatus': 'ready', 'mixStatus': 'ready',
            'detailUrl': '/listen/details/one.json'}],
            coverage={'indexed': 1, 'playable': 1, 'mixReady': 1})
        self.save_index()

    def save_index(self):
        (self.corpus / 'library-index.json').write_text(json.dumps(self.index))

    def build(self):
        try:
            module = importlib.import_module('scripts.package_continuous_site')
        except ModuleNotFoundError:
            self.fail('Cloud bundle exporter has not been implemented')
        return module.build_bundle(self.corpus, self.store, self.out, self.root, expected=1)

    def test_rewrites_all_audio_and_deduplicates_without_modifying_analysis(self):
        manifest = self.build()
        self.assertEqual(len(manifest['assets']), 1)
        public = json.loads((self.out / 'details' / 'one.json').read_text())['track']
        expected = '/listen/media/' + self.sha + '.flac'
        self.assertEqual(public['native']['url'], expected)
        self.assertEqual(public['audioSegments'][0]['asset']['url'], expected)
        self.assertEqual(public['windows'][0]['variants']['two']['url'], expected)
        self.assertEqual(public['provenance'], self.track['provenance'])
        self.assertEqual(public['preprocessing']['vocalActivity'], self.track['preprocessing']['vocalActivity'])
        self.assertEqual(json.loads((self.corpus / 'details' / 'one.json').read_text())['track'], self.track)
        self.assertEqual(manifest['assets'][0]['source'], str(self.audio.resolve()))
        self.assertNotIn(str(self.root), (self.out / 'details' / 'one.json').read_text())
        self.assertTrue((self.out / 'library.json.gz').is_file())

    def test_incomplete_library_is_not_published(self):
        self.index['tracks'][0]['mixStatus'] = 'unavailable'
        self.save_index()
        with self.assertRaisesRegex(ValueError, 'complete'):
            self.build()
        self.assertFalse((self.out / 'library.json').exists())

    def test_known_analysis_limit_keeps_song_playable_and_does_not_inflate_mix_count(self):
        self.index['tracks'][0]['mixStatus']='unavailable'
        self.save_index()
        (self.corpus/'corpus-audit.json').write_text(json.dumps({'sourceMixReady':0,'failures':{}}))
        self.build()
        public=json.loads((self.out/'library.json').read_text())
        self.assertEqual(public['coverage']['playable'],1)
        self.assertEqual(public['coverage']['mixReady'],0)
        self.assertEqual(public['tracks'][0]['mixStatus'],'unavailable')

    def test_changed_source_is_rejected(self):
        self.audio.write_bytes(b'changed source')
        with self.assertRaisesRegex(ValueError, 'changed'):
            self.build()

    def test_source_outside_allowlisted_root_is_rejected(self):
        record = self.store / 'media' / (self.identifier + '.json')
        value = json.loads(record.read_text())
        value['path'] = '/etc/hosts'
        record.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, 'root'):
            self.build()

    def test_asset_checksum_conflicting_with_registry_is_rejected(self):
        self.track['native']['sha256'] = 'b' * 64
        (self.corpus / 'details' / 'one.json').write_text(json.dumps({'track': self.track}))
        with self.assertRaisesRegex(ValueError, 'checksum'):
            self.build()

    def test_cloud_verifier_rejects_same_size_corruption(self):
        manifest = self.build()
        module = importlib.import_module('scripts.package_continuous_site')
        downloaded = self.root / 'downloaded'
        target = downloaded / manifest['assets'][0]['source'].lstrip('/')
        target.parent.mkdir(parents=True)
        target.write_bytes(b'x' * self.audio.stat().st_size)
        with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
            module.verify_cloud(manifest, downloaded, self.root / 'media')
        self.assertFalse((self.root / 'media' / (self.sha + '.flac')).exists())

    def test_cloud_verified_audio_is_hardlinked_without_extra_storage(self):
        manifest = self.build()
        module = importlib.import_module('scripts.package_continuous_site')
        downloaded = self.root / 'downloaded'
        target = downloaded / manifest['assets'][0]['source'].lstrip('/')
        target.parent.mkdir(parents=True)
        target.write_bytes(self.audio.read_bytes())
        result = module.verify_cloud(manifest, downloaded, self.root / 'media')
        self.assertEqual(result['verifiedAssets'], 1)
        self.assertEqual(target.stat().st_ino, (self.root / 'media' / (self.sha + '.flac')).stat().st_ino)

    def test_redeployment_reuses_identical_content_from_a_different_release_inode(self):
        manifest=self.build()
        module=importlib.import_module('scripts.package_continuous_site')
        downloaded=self.root/'downloaded'
        source=downloaded/manifest['assets'][0]['source'].lstrip('/')
        source.parent.mkdir(parents=True);source.write_bytes(self.audio.read_bytes())
        media=self.root/'media';media.mkdir()
        existing=media/(self.sha+'.flac');existing.write_bytes(self.audio.read_bytes())
        inode=existing.stat().st_ino
        self.assertEqual(module.verify_cloud(manifest,downloaded,media)['verifiedAssets'],1)
        self.assertEqual(existing.stat().st_ino,inode)


if __name__ == '__main__':
    unittest.main()
