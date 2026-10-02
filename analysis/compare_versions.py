"""
Compare how well the analysis versions read location and title,
using the human reviews (plan_reviews.json) as the correct values.

    python3 analysis/compare_versions.py /path/to/plans
    python3 analysis/compare_versions.py /path/to/plans --details

Compares every version found in the project data of the folder
(data/.../analysis_log.jsonl, v10+) and in plan_metadata_v*.json files
in the plan folder (v5 ... v9). Prints only counts and percentages -
no plan content.
--details additionally lists every wrong value (for your own checking).

Only reviewed plans count. Note: the reviews were made while looking at
one version's values (so far v8), which can favour that version slightly.
"""

# Repo layout: this file is in analysis/, the shared modules are in src/
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / "src"))

import json
import re
import sys
from pathlib import Path

from rapidfuzz import fuzz

import store
from models import FIELDS, Review
from search import tokenize


LEVEL_NAMES = {"green": "confident", "yellow": "check", "red": "uncertain"}


def clean(text) -> str:
    return " ".join((text or "").split())


def normalized(text) -> str:
    """Same normalisation as the search: ß/ss, umlauts, case, punctuation."""
    return "".join(tokenize(text))


def load_truth(folder: Path) -> dict[str, dict[str, str]]:
    """
    Reviewed values by filename: from the project data (v10+),
    otherwise from plan_reviews.json in the plan folder. Nothing is changed.
    """

    reviews = store.load_reviews(folder)

    if not reviews:

        path = folder / "plan_reviews.json"

        if not path.exists():
            sys.exit(f"No reviews for {folder} - review some plans in the app first.")

        reviews = {
            name: Review.model_validate(r)
            for name, r in json.loads(path.read_text(encoding="utf-8")).items()
        }

        # v8 reviews: fill in the confirmed v8 value (in memory only)
        store.pin_v8_reviews(folder, reviews)

    return {
        name: {f: getattr(r, f) for f in FIELDS if getattr(r, f) is not None}
        for name, r in reviews.items()
    }


def load_versions(folder: Path) -> dict[str, dict[str, dict]]:
    """
    {"v10": {filename: entry}, ...}: latest analysis per version and plan
    from the project's analysis log, plus plan_metadata_v*.json files
    in the plan folder for versions that are not in the log.
    """

    versions = {}

    for entry in store.read_log(folder):
        match = re.search(r"_(v\d+)\.py", (entry.get("analysis") or {}).get("script", ""))
        if match:
            # log is in time order: later entries overwrite earlier ones
            versions.setdefault(match.group(1), {})[entry["filename"]] = entry

    for path in folder.glob("plan_metadata_v*.json"):

        match = re.fullmatch(r"plan_metadata_(v\d+)\.json", path.name)

        if match and match.group(1) not in versions:
            entries = json.loads(path.read_text(encoding="utf-8"))
            versions[match.group(1)] = {e["filename"]: e for e in entries}

    return dict(sorted(versions.items(), key=lambda kv: int(kv[0][1:])))


def evaluate(truth, entries, field):
    """Counts for one version and one field."""

    result = {"n": 0, "exact": 0, "normalized": 0, "similarity": 0.0, "levels": {}, "wrong": []}

    for name, fields in truth.items():

        if field not in fields:
            continue

        expected = fields[field]
        entry = entries.get(name) or {}
        got = (entry.get("metadata") or {}).get(field)

        result["n"] += 1

        is_exact = clean(got) == clean(expected)
        is_normalized = normalized(got) == normalized(expected)

        result["exact"] += is_exact
        result["normalized"] += is_normalized

        if normalized(got) or normalized(expected):
            result["similarity"] += fuzz.ratio(normalized(got), normalized(expected))
        else:
            result["similarity"] += 100   # both empty = correct

        confidence = entry.get(f"{field}_confidence")

        if confidence:
            counts = result["levels"].setdefault(confidence["level"], [0, 0])
            counts[0] += is_normalized
            counts[1] += 1

        if not is_normalized:
            result["wrong"].append((name, expected, got))

    return result


def pct(part, whole) -> str:
    return f"{part}/{whole} ({part / whole:.0%})" if whole else "–"


def main():

    args = [a for a in sys.argv[1:] if not a.startswith("--")]

    if not args:
        sys.exit(__doc__)

    folder = Path(args[0]).expanduser()
    details = "--details" in sys.argv

    truth = load_truth(folder)
    versions = load_versions(folder)

    if not versions:
        sys.exit(f"No analysis results for {folder} - run an analysis first.")

    print(f"\nReviewed plans: {len(truth)}")
    print("exact = same text (only spaces ignored)")
    print("normalized = same after ß/ss, umlauts, case and punctuation are ignored")
    print("similarity = average text similarity 0-100 (normalized)\n")

    for field in FIELDS:

        print(f"{field.upper():<10} {'exact':<16} {'normalized':<16} similarity")

        for version, entries in versions.items():
            r = evaluate(truth, entries, field)
            similarity = r["similarity"] / r["n"] if r["n"] else 0
            print(f"{version:<10} {pct(r['exact'], r['n']):<16} {pct(r['normalized'], r['n']):<16} {similarity:5.1f}")

        print()

    print("Does the traffic light fit? (normalized correct per rating)")

    for field in FIELDS:
        for version, entries in versions.items():
            levels = evaluate(truth, entries, field)["levels"]
            if levels:
                parts = [
                    f"{LEVEL_NAMES[level]} {pct(*levels[level])}"
                    for level in ("green", "yellow", "red")
                    if level in levels
                ]
                print(f"  {field:<9} {version}:  " + ",  ".join(parts))

    if details:
        print("\nWrong values (contains plan content):")
        for field in FIELDS:
            for version, entries in versions.items():
                for name, expected, got in evaluate(truth, entries, field)["wrong"]:
                    print(f"  {version} {field:<8} {name}\n      expected: {expected!r}\n      got:      {got!r}")

    print()


if __name__ == "__main__":
    main()
