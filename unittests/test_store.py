"""
Project storage: saved results, change detection, import of v8/v9 data.

Uses a temporary data directory and invented files - the project's
data/ directory and real plans are never touched.
Run all tests:  python3 -m unittest discover -s tests -v
"""

# Repo layout: this file is in tests/, the shared modules are in src/
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / "src"))

import json
import os
import tempfile
import time
import unittest
from pathlib import Path

import store
from models import ImageData, Metadata, Review


class StoreTestCase(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)

        # redirect the project data directory
        self._old = (store.DATA_DIR, store.LAST_FOLDER_FILE)
        store.DATA_DIR = root / "data"
        store.LAST_FOLDER_FILE = store.DATA_DIR / "last_folder.txt"

        self.plans = root / "plans"
        self.plans.mkdir()
        self.plan = self.plans / "a.tif"
        self.plan.write_bytes(b"first version")

    def tearDown(self):
        store.DATA_DIR, store.LAST_FOLDER_FILE = self._old
        self.tmp.cleanup()

    def entry(self, name="a.tif", location="Kaiserdamm"):
        e = ImageData(filename=name, metadata=Metadata(location=location, title="Plan"))
        e.analysis = store.make_analysis(self.plans / name, "scan_plan_htw_api_v10.py")
        return e


class ChangeDetection(StoreTestCase):

    def test_unchanged_file_is_current(self):
        self.assertTrue(store.is_current(self.entry(), self.plan))

    def test_only_touched_file_is_still_current(self):
        e = self.entry()
        time.sleep(0.01)
        os.utime(self.plan)   # new modification time, same content
        self.assertTrue(store.is_current(e, self.plan))

    def test_changed_content_is_not_current(self):
        e = self.entry()
        self.plan.write_bytes(b"second version")
        self.assertFalse(store.is_current(e, self.plan))

    def test_entry_without_analysis_is_not_current(self):
        e = ImageData(filename="a.tif", metadata=Metadata(location=None, title=None))
        self.assertFalse(store.is_current(e, self.plan))


class Saving(StoreTestCase):

    def test_results_round_trip_without_reviews(self):
        e = self.entry()
        e.review = Review(location="Other")
        store.save_results(self.plans, {e.filename: e})

        loaded = store.load_results(self.plans)["a.tif"]
        self.assertEqual(loaded.metadata.location, "Kaiserdamm")
        self.assertIsNone(loaded.review)   # reviews live in reviews.json

    def test_log_keeps_every_analysis(self):
        store.append_log(self.plans, self.entry(location="A"))
        store.append_log(self.plans, self.entry(location="B"))
        self.assertEqual([e["metadata"]["location"] for e in store.read_log(self.plans)], ["A", "B"])

    def test_plan_folder_is_not_written(self):
        store.save_results(self.plans, {"a.tif": self.entry()})
        store.save_reviews(self.plans, {"a.tif": Review(location="X")})
        self.assertEqual(sorted(p.name for p in self.plans.iterdir()), ["a.tif"])

    def test_last_folder(self):
        self.assertIsNone(store.last_folder())
        store.remember_folder(self.plans)
        self.assertEqual(store.last_folder(), self.plans.resolve())


class ImportFromPlanFolder(StoreTestCase):

    def test_imports_v9_results_and_pins_v8_reviews(self):
        (self.plans / "plan_metadata_v9.json").write_text(json.dumps([
            {"filename": "a.tif", "metadata": {"location": "Kaiserdamm", "title": "Plan"}},
            {"filename": "gone.tif", "metadata": {"location": "X", "title": "Y"}},
        ]))
        (self.plans / "plan_metadata_v8.json").write_text(json.dumps([
            {"filename": "a.tif", "metadata": {"location": "Kaiserdam", "title": "Plan"}},
        ]))
        # v8 review: confirmed location stored as None
        (self.plans / "plan_reviews.json").write_text(json.dumps({"a.tif": {"location_level": "green"}}))

        notes = store.import_from_plan_folder(self.plans)

        results = store.load_results(self.plans)
        self.assertEqual(list(results), ["a.tif"])          # missing files are skipped
        self.assertEqual(results["a.tif"].analysis.script, "scan_plan_htw_api_v9.py")
        self.assertTrue(store.is_current(results["a.tif"], self.plan))

        # the v8 value the reviewer confirmed is pinned
        self.assertEqual(store.load_reviews(self.plans)["a.tif"].location, "Kaiserdam")
        self.assertEqual(len(notes), 2)

    def test_import_happens_only_once(self):
        (self.plans / "plan_metadata_v9.json").write_text(json.dumps([
            {"filename": "a.tif", "metadata": {"location": "A", "title": "T"}},
        ]))
        store.import_from_plan_folder(self.plans)
        self.assertEqual(store.import_from_plan_folder(self.plans), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
