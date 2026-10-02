"""
Fuzzy search over location and title of the analysed plans.

Query and data go through the SAME normalisation, so every spelling
variant meets in one form. Layers, strongest first:

    exact            same normalised word
    spelling variant same after normalisation, different raw spelling
                   (ß/ss/ſ, ä/ae/a, Thor/Tor, Str./Straße, upper/lower case,
                   hyphens and spaces in compound names)
    word start       "alex" -> "Alexanderplatz"
    part of word     "kanzler" -> "Reichskanzlerplatz"
    sounds alike     Kölner Phonetik: "Cottbuser" -> "Kottbusser"
    similar          typos / misread letters (Levenshtein based)
    renamed          renamed places: "Theodor-Heuss-Platz" -> "Reichskanzlerplatz"

Documented edge cases: see tests/test_search.py.
"""

import re
import unicodedata
from dataclasses import dataclass

from rapidfuzz import fuzz


# Minimum score for an entry to be shown (0-1)
MIN_SCORE = 0.78


# Renamed places. Each group = names of the same place over time.
# A query matching one name also finds the others.
# Extend this list when the review finds new cases.
ALIASES = [
    ["Theodor-Heuss-Platz", "Reichskanzlerplatz", "Adolf-Hitler-Platz"],
    ["Mohrenstraße", "Kaiserhof", "Thälmannplatz", "Otto-Grotewohl-Straße"],
    ["Gendarmenmarkt", "Gensdarmenmarkt"],
]


# Abbreviations as whole words (after normalisation, without dots)
ABBREVIATIONS = {
    "str": "strasse",
    "pl": "platz",
    "bhf": "bahnhof",
    "bf": "bahnhof",
    "ubhf": "ubahnhof",
    "haltest": "haltestelle",
}


# Words that do not help to find a plan. Ignored in the query
# unless the query consists only of them.
STOPWORDS = {
    "u", "s", "ubahn", "ubahnhof", "bahnhof", "haltestelle", "station",
    "der", "die", "das", "des", "dem", "den", "im", "in", "am", "an",
    "auf", "von", "vom", "zum", "zur", "und", "fur", "a", "d",
}


# ------------------------------------------------------------
# Normalisation
# ------------------------------------------------------------

def normalize_word(word: str) -> str:
    """Spelling-normalise one lower-case word (no spaces)."""

    # Umlauts and their old spellings meet in the base vowel:
    # "Schönhauser" / "Schoenhauser" / "Schonhauser" -> "schonhauser"
    word = word.replace("ä", "a").replace("ö", "o").replace("ü", "u")
    word = re.sub(r"(?<=[aou])e", "", word)

    # Historical spellings
    word = word.replace("th", "t")      # Thor -> Tor, Thiergarten
    word = word.replace("sz", "ss")     # Kurrent ſz for ß

    # "...str" at the end of a compound: "Bismarckstr." -> "bismarckstrasse"
    if word.endswith("str") and len(word) > 4:
        word += "asse"

    return ABBREVIATIONS.get(word, word)


def tokenize(text: str | None) -> list[str]:
    """Text -> list of normalised words."""

    if not text:
        return []

    text = unicodedata.normalize("NFKC", text)

    # Long s (Fraktur / Kurrent), casefold also turns ß into ss
    text = text.replace("ſ", "s").casefold()

    # Remove remaining accents (é -> e), keep base letters
    text = "".join(
        c for c in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(c) or c == "̈"
    )
    text = unicodedata.normalize("NFC", text)

    # "U-Bhf." / "U.-Bhf." -> "ubhf" ; other hyphens separate words
    text = re.sub(r"\b([us])\.?-", r"\1", text)

    words = re.split(r"[^0-9a-zäöü]+", text)

    return [normalize_word(w) for w in words if w]


def content_words(tokens: list[str]) -> list[str]:
    """Tokens without stopwords (all tokens if nothing would be left)."""

    kept = [t for t in tokens if t not in STOPWORDS]

    return kept or tokens


# ------------------------------------------------------------
# Kölner Phonetik (German sound code)
# ------------------------------------------------------------

def cologne_phonetic(word: str) -> str:
    """
    Kölner Phonetik of a normalised word, e.g.
    "kottbusser" and "cottbuser" -> "42187".
    """

    word = re.sub(r"[^a-z]", "", word)

    codes = []

    for i, c in enumerate(word):

        # "#" instead of "": ("" in "csz") would be True
        prev = word[i - 1] if i > 0 else "#"
        nxt = word[i + 1] if i + 1 < len(word) else "#"

        if c in "aeijouy":
            code = "0"
        elif c == "h":
            code = ""
        elif c == "b":
            code = "1"
        elif c == "p":
            code = "3" if nxt == "h" else "1"
        elif c in "dt":
            code = "8" if nxt in "csz" else "2"
        elif c in "fvw":
            code = "3"
        elif c in "gkq":
            code = "4"
        elif c == "c":
            if i == 0:
                code = "4" if nxt in "ahkloqrux" else "8"
            elif prev in "sz":
                code = "8"
            else:
                code = "4" if nxt in "ahkoqux" else "8"
        elif c == "x":
            code = "8" if prev in "ckq" else "48"
        elif c == "l":
            code = "5"
        elif c in "mn":
            code = "6"
        elif c == "r":
            code = "7"
        elif c in "sz":
            code = "8"
        else:
            code = ""

        codes.append(code)

    # Collapse repeated codes, then drop "0" except at the start
    result = ""

    for code in "".join(codes):
        if not result or result[-1] != code:
            result += code

    return result[:1] + result[1:].replace("0", "")


# ------------------------------------------------------------
# Matching
# ------------------------------------------------------------

@dataclass
class Match:
    score: float     # 0-1
    reason: str      # exact / spelling variant / word start / ...


def match_word(query: str, raw_query: str, words: list[str], raw_text: str) -> Match:
    """Best match of one normalised query word against the words of a field."""

    best = Match(0.0, "")

    # Compound words may be split differently:
    # "Friedrichstraße" vs "Friedrich-Straße" -> also compare the joined field
    candidates = words + ["".join(words)]

    for word in candidates:

        if word == query:
            # Raw spelling identical? Otherwise it was a spelling variant.
            # lower(), not casefold(): casefold would make ß == ss.
            if raw_query.lower() in raw_text.lower():
                m = Match(1.0, "exact")
            else:
                m = Match(0.97, "spelling variant")

        elif len(query) >= 2 and word.startswith(query):
            m = Match(0.95, "word start")

        elif len(query) >= 4 and query in word:
            m = Match(0.90, "part of word")

        elif (
            len(query) >= 4
            and len(word) >= 4
            and cologne_phonetic(query) == cologne_phonetic(word)
        ):
            m = Match(0.88, "sounds alike")

        elif len(query) >= 4:
            # Typos / misread letters. partial_ratio handles
            # "reichskantzler" vs "reichskanzlerplatz".
            similarity = fuzz.ratio(query, word) / 100

            if len(query) >= 5 and len(word) > len(query):
                similarity = max(
                    similarity,
                    fuzz.partial_ratio(query, word) / 100 * 0.95
                )

            m = Match(similarity * 0.9, "similar")

        else:
            continue

        if m.score > best.score:
            best = m

    return best


def match_field(query_text: str, field_text: str | None) -> Match:
    """
    How well the query matches one field (average over query words;
    every query word has to be found somewhere in the field).
    """

    field_words = tokenize(field_text)

    if not field_words:
        return Match(0.0, "")

    raw_words = re.split(r"[\s\-]+", query_text.strip())
    query_words = content_words(tokenize(query_text))

    if not query_words:
        return Match(0.0, "")

    # Several query words glued together: "krumme lanke" vs "Krummelanke"
    joined_query = "".join(query_words)
    joined_field = "".join(field_words)

    if len(query_words) > 1 and joined_query in joined_field:
        exact = query_text.strip().lower() in field_text.lower()
        return Match(1.0 if exact else 0.97, "exact" if exact else "spelling variant")

    matches = [
        match_word(
            q,
            raw_words[i] if len(raw_words) == len(query_words) else query_text,
            field_words,
            field_text
        )
        for i, q in enumerate(query_words)
    ]

    score = sum(m.score for m in matches) / len(matches)

    # Name of the weakest match = what made this a fuzzy hit
    reason = min(matches, key=lambda m: m.score).reason

    return Match(score, reason)


def alias_queries(query: str) -> list[tuple[str, str]]:
    """
    Other names of the place the query refers to.
    Returns [(alias, name the query matched), ...].
    """

    joined_query = "".join(content_words(tokenize(query)))

    result = []

    for group in ALIASES:

        for name in group:

            joined_name = "".join(content_words(tokenize(name)))

            # The whole name has to match (typos allowed), not just
            # one word - otherwise "platz" would trigger every alias.
            if (
                fuzz.ratio(joined_query, joined_name) >= 90
                or (len(joined_query) >= 6 and joined_name.startswith(joined_query))
            ):

                result.extend(
                    (other, name)
                    for other in group
                    if other != name
                )

                break

    return result


@dataclass
class SearchHit:
    filename: str
    score: float
    field: str       # "location" or "title"
    reason: str


def search(entries: list[dict], query: str, min_score: float = MIN_SCORE) -> list[SearchHit]:
    """
    Search entries (ImageData dicts) by location and title.
    Sorted by score, best first. Empty query -> no hits.
    """

    if not tokenize(query):
        return []

    variants = [(query, None)] + alias_queries(query)

    hits = []

    for entry in entries:

        metadata = entry.get("metadata") or {}

        best = None

        for text, alias_of in variants:

            for field, weight in (("location", 1.0), ("title", 0.98)):

                m = match_field(text, metadata.get(field))

                score = m.score * weight
                reason = m.reason

                if alias_of is not None:
                    score *= 0.95
                    reason = f"renamed: {alias_of} ↔ {text}"

                if best is None or score > best.score:
                    best = SearchHit(entry["filename"], score, field, reason)

        if best is not None and best.score >= min_score:
            hits.append(best)

    hits.sort(key=lambda h: (-h.score, h.filename))

    return hits
