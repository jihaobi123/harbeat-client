import hashlib
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import install_data
import manage


class DeploymentSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def archive(self, entries):
        path = self.root / 'test.zip'
        with zipfile.ZipFile(path, 'w') as z:
            for key, value in entries.items():
                z.writestr(key, value)
        return path, install_data.sha(path)

    def test_unsafe_storage_keys_rejected(self):
        with patch.object(manage, 'ROOT', self.root):
            for key in ('', '/etc/passwd', '../outside', 'published/../../outside'):
                with self.subTest(key=key), self.assertRaises(ValueError):
                    manage.resolve(key)

    def test_symlink_escape_rejected(self):
        (self.root / 'outside').symlink_to('/tmp')
        with patch.object(manage, 'ROOT', self.root), self.assertRaises(ValueError):
            manage.resolve('outside/not-in-root')

    def test_valid_storage_key(self):
        with patch.object(manage, 'ROOT', self.root):
            # macOS /var is a symlink to /private/var; production resolves roots.
            self.assertEqual(manage.resolve('published/a.json'), (self.root / 'published/a.json').resolve())

    def test_archive_hash_checked_first(self):
        archive, checksum = self.archive({'published/a': 'hello'})
        with self.assertRaises(ValueError):
            install_data.extract(archive, self.root / 'out', '0' * 64)
        self.assertFalse((self.root / 'out').exists())

    def test_archive_traversal_rejected(self):
        archive, checksum = self.archive({'../escape': 'bad'})
        with self.assertRaises(ValueError):
            install_data.extract(archive, self.root / 'out', checksum)
        self.assertFalse((self.root / 'escape').exists())

    def test_idempotent_extract_preserves_identical_file(self):
        archive, checksum = self.archive({'published/a': 'hello'})
        target = self.root / 'out'
        install_data.extract(archive, target, checksum)
        stamp = (target / 'published/a').stat().st_mtime_ns
        install_data.extract(archive, target, checksum)
        self.assertEqual((target / 'published/a').stat().st_mtime_ns, stamp)

    def test_existing_different_file_never_overwritten(self):
        archive, checksum = self.archive({'a': 'new'})
        target = self.root / 'out'
        target.mkdir()
        (target / 'a').write_text('original')
        with self.assertRaises(ValueError):
            install_data.extract(archive, target, checksum)
        self.assertEqual((target / 'a').read_text(), 'original')


if __name__ == '__main__':
    unittest.main()
