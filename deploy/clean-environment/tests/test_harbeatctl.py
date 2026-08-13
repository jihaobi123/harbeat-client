import json
import tempfile
import unittest
from pathlib import Path

from deploy.clean_environment.harbeatctl import main


class HarbeatCtlTests(unittest.TestCase):
    def test_validate_release_scaffold(self):
        self.assertEqual(main(["validate"]), 0)

    def test_clean_root_bootstrap_stage_activate_and_rollback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertEqual(main(["bootstrap", "--root", str(root)]), 0)
            self.assertEqual(main(["stage", "--root", str(root)]), 0)
            self.assertEqual(main(["verify", "--root", str(root)]), 0)
            self.assertEqual(main(["activate", "--root", str(root)]), 0)
            self.assertEqual(main(["stage", "--release", "0.3.1", "--root", str(root)]), 0)
            self.assertEqual(main(["verify", "--release", "0.3.1", "--root", str(root)]), 0)
            self.assertEqual(main(["activate", "--release", "0.3.1", "--root", str(root)]), 0)
            current = root / "opt" / "harbeat" / "current"
            self.assertTrue(current.exists())
            self.assertEqual(main(["rollback", "--root", str(root)]), 0)
            self.assertEqual(current.resolve().name, "0.3.0")
            self.assertEqual(main(["verify", "--release", "0.3.1", "--root", str(root)]), 0)

    def test_manifest_never_authorizes_cleanup(self):
        manifest = json.loads((Path(__file__).parents[3] / "deploy/clean-environment/release-manifest.json").read_text())
        self.assertFalse(manifest["production_ready"])
        self.assertFalse(manifest["cleanup_authorized"])


if __name__ == "__main__":
    unittest.main()
