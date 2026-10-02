"""
Edge cases of the plan search, written as tests.

The entries below are INVENTED test data (public station names,
made-up titles) - not taken from the BVG plans.

Run all tests:  python3 -m unittest discover -s tests -v
"""

# Repo layout: this file is in tests/, the shared modules are in src/
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / "src"))

import unicodedata
import unittest

from search import cologne_phonetic, search, tokenize


def entry(filename, location, title, error=None):
    return {
        "filename": filename,
        "metadata": {"location": location, "title": title},
        "error": error,
    }


ENTRIES = [
    entry("p01.tif", "Friedrichstrasse", "Grundriss Bahnsteig Friedrichstrasse"),
    entry("p02.tif", "Neue Friedrich-Straße", "Querschnitt Tunnel"),
    entry("p03.tif", "Kottbusser Tor", "Fahrtreppe am Kottbusser Tor"),
    entry("p04.tif", "Cottbuser Platz", "Ausgang Nord"),
    entry("p05.tif", "Krumme Lanke", "Kehrgleis Krumme Lanke"),
    entry("p06.tif", "BISMARCKSTR.", "U-BHF. BISMARCKSTR. BELEUCHTUNG"),
    entry("p07.tif", "Hallesches Thor", "Uebersicht und Grundriß"),
    entry("p08.tif", "Schönhauser Allee", "Treppenanlage"),
    entry("p09.tif", "Reichskanzlerplatz", "Kabelplan Bahnsteig"),
    entry("p10.tif", "Alexanderplatz", "Bahnsteighalle Alexanderplatz"),
    entry("p11.tif", "Kaiserdamm", "Bahnhofsplan"),
    entry("p12.tif", "Mohrenstraße", "Wandverkleidung"),
    entry("p13.tif", None, None, error="ERROR (Timeout)"),
    entry("p14.tif", "Wittenbergplatz", "Nebenräume im Zwickel"),
    entry("p15.tif", "Französische Straße", "Ausgang Linie 6"),
    entry("p16.tif", "Rathaus Schöneberg", "Wandfliesen"),
    entry("p17.tif", None, "Normalquerschnitt zweigleisiger Tunnel"),
]


def found(query):
    return {h.filename: h for h in search(ENTRIES, query)}


class SpellingVariants(unittest.TestCase):
    """A. Same word, different spelling -> must always be found."""

    def test_sharp_s_and_ss(self):
        # ß in the query, ss on the plan
        hits = found("Friedrichstraße")
        self.assertIn("p01.tif", hits)
        self.assertEqual(hits["p01.tif"].reason, "spelling variant")

    def test_ss_query_finds_sharp_s(self):
        self.assertIn("p12.tif", found("Mohrenstrasse"))

    def test_long_s(self):
        # Fraktur / Kurrent long s
        self.assertIn("p01.tif", found("Friedrichſtraße"))

    def test_hyphenated_compound(self):
        # "Friedrich-Straße" on the plan, one word in the query
        self.assertIn("p02.tif", found("Friedrichstraße"))

    def test_umlaut_written_as_ae_oe_ue(self):
        self.assertIn("p08.tif", found("Schoenhauser Allee"))

    def test_umlaut_dots_lost(self):
        # model / OCR dropped the dots
        self.assertIn("p08.tif", found("Schonhauser"))

    def test_ue_on_plan_umlaut_in_query(self):
        self.assertIn("p07.tif", found("Übersicht"))

    def test_old_th(self):
        self.assertIn("p07.tif", found("Hallesches Tor"))

    def test_eszett_in_old_title(self):
        hits = found("Grundriss")
        self.assertIn("p07.tif", hits)   # "Grundriß"
        self.assertIn("p01.tif", hits)   # "Grundriss"

    def test_abbreviation_str(self):
        self.assertIn("p06.tif", found("Bismarckstraße"))

    def test_abbreviation_in_query(self):
        self.assertIn("p15.tif", found("französische str."))

    def test_upper_case_on_plan(self):
        self.assertIn("p06.tif", found("bismarckstrasse"))

    def test_decomposed_unicode_query(self):
        # macOS may deliver "ö" as "o" + combining diaeresis
        self.assertIn("p15.tif", found(unicodedata.normalize("NFD", "Französische Straße")))

    def test_multi_word_glued(self):
        self.assertIn("p05.tif", found("krummelanke"))
        self.assertIn("p05.tif", found("Krumme-Lanke"))


class SoundAlike(unittest.TestCase):
    """B. Historical c/k and double consonants -> Kölner Phonetik."""

    def test_c_and_k(self):
        hits = found("Cottbusser")
        self.assertIn("p03.tif", hits)   # Kottbusser Tor
        self.assertIn("p04.tif", hits)   # Cottbuser Platz

    def test_phonetic_code(self):
        # reference example of the Kölner Phonetik
        self.assertEqual(cologne_phonetic("mullerludenscheidt"), "65752682")
        self.assertEqual(cologne_phonetic("kottbusser"), cologne_phonetic("cottbuser"))


class ReadingAndTypingErrors(unittest.TestCase):
    """C. Misread letters on the plan / typos in the query."""

    def test_typo_missing_letter(self):
        self.assertIn("p11.tif", found("Kaiserdam"))

    def test_typo_extra_letter(self):
        self.assertIn("p09.tif", found("Reichskantzlerplatz"))

    def test_misread_letter(self):
        self.assertIn("p14.tif", found("Zwiekel"))


class PartialQueries(unittest.TestCase):
    """D. Incomplete queries."""

    def test_word_start(self):
        hits = found("alex")
        self.assertIn("p10.tif", hits)
        self.assertEqual(hits["p10.tif"].reason, "word start")

    def test_part_of_compound(self):
        self.assertIn("p09.tif", found("kanzler"))

    def test_generic_words_are_ignored(self):
        # "U-Bhf." adds nothing, the place decides
        hits = found("U-Bhf. Alexanderplatz")
        self.assertEqual(list(hits), ["p10.tif"])

    def test_found_via_title_only(self):
        # no location on the plan -> still findable by title
        self.assertIn("p17.tif", found("Normalquerschnitt"))


class RenamedPlaces(unittest.TestCase):
    """E. Different names over time -> alias list."""

    def test_modern_name_finds_historic_plan(self):
        hits = found("Theodor-Heuss-Platz")
        self.assertIn("p09.tif", hits)
        self.assertIn("Reichskanzlerplatz", hits["p09.tif"].reason)

    def test_historic_name_finds_renamed_place(self):
        self.assertIn("p12.tif", found("Kaiserhof"))

    def test_single_word_does_not_trigger_alias(self):
        # "platz" must not pull in every renamed "...platz"
        for hit in search(ENTRIES, "platz"):
            self.assertNotIn("renamed", hit.reason)


class NoFalseHits(unittest.TestCase):
    """F. Things that must NOT be found."""

    def test_unrelated_station(self):
        self.assertEqual(found("Lichtenberg"), {})

    def test_other_station_not_mixed_up(self):
        self.assertEqual(list(found("Alexanderplatz")), ["p10.tif"])

    def test_similar_but_different_station(self):
        self.assertNotIn("p16.tif", found("Rathaus Spandau"))

    def test_single_letter(self):
        self.assertEqual(found("a"), {})

    def test_empty_and_whitespace(self):
        self.assertEqual(found(""), {})
        self.assertEqual(found("   "), {})
        self.assertEqual(found("--."), {})


class Robustness(unittest.TestCase):
    """G. Entries with errors or missing fields never break the search."""

    def test_error_entry_is_skipped_quietly(self):
        self.assertNotIn("p13.tif", found("Tunnel"))

    def test_tokenize_none(self):
        self.assertEqual(tokenize(None), [])

    def test_best_hit_first(self):
        hits = search(ENTRIES, "Friedrichstrasse")
        self.assertEqual(hits[0].filename, "p01.tif")
        self.assertEqual(hits[0].reason, "exact")


if __name__ == "__main__":
    unittest.main(verbosity=2)
