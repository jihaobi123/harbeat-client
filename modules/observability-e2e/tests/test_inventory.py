from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from harbeat_observability.inventory import build_inventory


class InventoryTests(unittest.TestCase):
    def test_excludes_private_and_runtime_data(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "runtime"
            (root / "src").mkdir(parents=True)
            (root / "cache").mkdir()
            (root / "src" / "module.py").write_text("VALUE = 1\n", encoding="utf-8")
            (root / "src" / ".env").write_text("PASSWORD=nope\n", encoding="utf-8")
            (root / "cache" / "render.wav").write_bytes(b"audio")
            (root / "user.db").write_bytes(b"private")

            inventory = build_inventory(root)

        paths = [entry["path"] for entry in inventory["files"]]
        self.assertEqual(paths, ["src/module.py"])
        self.assertEqual(len(inventory["files"][0]["sha256"]), 64)
        self.assertNotIn(str(root), str(inventory))


if __name__ == "__main__":
    unittest.main()

