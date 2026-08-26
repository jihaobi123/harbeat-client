import re
import subprocess
import tempfile
import unittest
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[2]
CONVERTER = PROJECT / "tools" / "convert_dancer_art.py"
SOURCE = PROJECT / "assets" / "source"
NAMES = ("hiphop", "breaking", "funk", "locking")


class DancerAssetConversionTest(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.output = Path(self.tempdir.name)
        subprocess.run(
            ["python3", str(CONVERTER), "--source", str(SOURCE), "--output", str(self.output)],
            check=True,
        )
        self.c_text = (self.output / "flow_dancer_assets.c").read_text()
        self.h_text = (self.output / "flow_dancer_assets.h").read_text()

    def tearDown(self):
        self.tempdir.cleanup()

    def test_exports_all_four_descriptors(self):
        for name in NAMES:
            symbol = f"flow_dancer_{name}"
            self.assertIn(f"extern const lv_image_dsc_t {symbol};", self.h_text)
            self.assertIn(f"const lv_image_dsc_t {symbol} =", self.c_text)

    def test_every_asset_is_112_square_rgb565a8(self):
        self.assertEqual(4, self.c_text.count(".cf = LV_COLOR_FORMAT_RGB565A8"))
        self.assertEqual(4, self.c_text.count(".w = 112"))
        self.assertEqual(4, self.c_text.count(".h = 112"))
        self.assertEqual(4, self.c_text.count(".stride = 224"))

    def test_asset_budget_is_bounded(self):
        sizes = [int(value) for value in re.findall(r"data_size = (\d+)", self.c_text)]
        self.assertEqual([37632] * 4, sizes)
        self.assertLessEqual(sum(sizes), 250 * 1024)

    def test_conversion_is_deterministic(self):
        subprocess.run(
            ["python3", str(CONVERTER), "--source", str(SOURCE), "--output", str(self.output)],
            check=True,
        )
        self.assertEqual(self.c_text, (self.output / "flow_dancer_assets.c").read_text())


if __name__ == "__main__":
    unittest.main()
