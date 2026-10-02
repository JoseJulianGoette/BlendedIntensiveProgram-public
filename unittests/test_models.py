"""
Data model: reviewed values, traffic lights, review status, filename notes.

Invented test data only. Run all tests:  python3 -m unittest discover -s tests -v
"""

# Repo layout: this file is in tests/, the shared modules are in src/
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / "src"))

import unicodedata
import unittest

from models import Confidence, ImageData, Metadata, Review, TrafficLight

G, Y, R = TrafficLight.GREEN, TrafficLight.YELLOW, TrafficLight.RED


def entry(location="Kaiserdamm", title="Bahnhofsplan", loc_level=G, title_level=Y, **kw):
    return ImageData(
        filename=kw.pop("filename", "plan.tif"),
        metadata=Metadata(location=location, title=title),
        location_confidence=Confidence(level=loc_level, probability=0.9) if loc_level else None,
        title_confidence=Confidence(level=title_level, probability=0.6) if title_level else None,
        **kw,
    )


class Values(unittest.TestCase):

    def test_model_value_without_review(self):
        self.assertEqual(entry().value("location"), "Kaiserdamm")

    def test_reviewed_value_wins(self):
        e = entry(review=Review(location="Kaiserdamm Süd"))
        self.assertEqual(e.value("location"), "Kaiserdamm Süd")

    def test_empty_review_means_not_on_plan(self):
        e = entry(review=Review(location=""))
        self.assertIsNone(e.value("location"))

    def test_v8_review_none_keeps_model_value(self):
        e = entry(review=Review(location_level=G))
        self.assertEqual(e.value("location"), "Kaiserdamm")


class TrafficLights(unittest.TestCase):

    def test_overall_is_worst_of_location_and_title(self):
        self.assertEqual(entry(loc_level=G, title_level=Y).overall_level, Y)
        self.assertEqual(entry(loc_level=R, title_level=G).overall_level, R)

    def test_reviewer_level_wins(self):
        e = entry(title_level=R, review=Review(title_level=G, location_level=G))
        self.assertEqual(e.level("title"), G)
        self.assertEqual(e.overall_level, G)

    def test_unreviewed_error_is_red(self):
        e = entry(location=None, title=None, loc_level=None, title_level=None, error="ERROR")
        self.assertEqual(e.overall_level, R)

    def test_no_logprobs_means_no_rating(self):
        self.assertIsNone(entry(loc_level=None).overall_level)


class ReviewStatus(unittest.TestCase):

    def test_open(self):
        self.assertEqual(entry().review_status, "open")

    def test_confirmed_when_same_as_model(self):
        # extra spaces do not count as a correction
        e = entry(review=Review(location=" Kaiserdamm ", title="Bahnhofsplan"))
        self.assertEqual(e.review_status, "confirmed")

    def test_corrected_when_different(self):
        e = entry(review=Review(location="Kaiserdamm", title="Grundriss"))
        self.assertEqual(e.review_status, "corrected")


class FilenameFlags(unittest.TestCase):

    def test_german_notes_become_english_labels(self):
        e = entry(filename="S_1 nie gebaut ungültig.tif")
        self.assertEqual(e.filename_flags, ["invalid", "never built"])

    def test_decomposed_umlaut_from_macos(self):
        e = entry(filename=unicodedata.normalize("NFD", "M1_überholt.tif"))
        self.assertEqual(e.filename_flags, ["superseded"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
