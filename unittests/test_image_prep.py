"""
Image preparation for the model (v9+): pixel budget, 1-bit scans, PDFs.

Generated test images only. Run all tests:  python3 -m unittest discover -s tests -v
"""

# Repo layout: this file is in tests/, the shared modules are in src/
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / "src"))

import io
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

import scan_plan_htw_api_v10 as scan


def visible_lines(img: Image.Image) -> int:
    """Number of separate dark vertical lines along the image."""
    g = img.convert("L")
    w, h = g.size
    dark = [any(g.getpixel((x, y)) < 200 for y in range(0, h, max(1, h // 40))) for x in range(w)]
    return sum(1 for x in range(1, w) if dark[x] and not dark[x - 1])


class ImagePrep(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dir = Path(cls.tmp.name)

        # 1-bit "scan", 24 MP, with 1 px and 3 px lines
        scan_img = Image.new("1", (6000, 4000), 1)
        d = ImageDraw.Draw(scan_img)
        cls.lines = 0
        for i, x in enumerate(range(100, 6000, 97)):
            d.line((x, 0, x, 3999), fill=0, width=1 if i % 2 else 3)
            cls.lines += 1
        cls.scan_path = cls.dir / "scan.tif"
        scan_img.save(cls.scan_path, compression="group4")

        # scanned PDF: one embedded image of 2000 x 1400 px
        cls.pdf_path = cls.dir / "scan.pdf"
        Image.new("L", (2000, 1400), 255).save(cls.pdf_path)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_budget_scale(self):
        self.assertAlmostEqual(scan.budget_scale(4000, 4000), 1.0)
        self.assertLess(scan.budget_scale(8000, 6000), 1.0)

    def test_large_scan_fits_pixel_budget(self):
        _, info = scan.prepare_image(self.scan_path)
        w, h = map(int, info["sent_size"].split("x"))
        self.assertLessEqual(w * h, scan.MAX_PIXELS)
        self.assertGreater(w * h, 0.95 * scan.MAX_PIXELS)   # uses the budget
        self.assertAlmostEqual(w / h, 1.5, places=2)        # keeps aspect ratio

    def test_thin_lines_of_1bit_scans_survive(self):
        data, _ = scan.prepare_image(self.scan_path)
        self.assertEqual(visible_lines(Image.open(io.BytesIO(data))), self.lines)

    def test_small_image_is_not_enlarged(self):
        small = self.dir / "small.png"
        Image.new("L", (1200, 800), 255).save(small)
        _, info = scan.prepare_image(small)
        self.assertEqual(info["sent_size"], "1200x800")

    def test_scanned_pdf_not_rendered_above_scan_resolution(self):
        _, info = scan.prepare_image(self.pdf_path)
        self.assertEqual(info["sent_size"], "2000x1400")


if __name__ == "__main__":
    unittest.main(verbosity=2)
