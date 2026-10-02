"""
Storage of analysis results inside the project (v10+).

The plan folder is only read, never written: it may be a read-only
archive or network drive. Everything the app produces lives here:

    data/                                  project root, git-ignored: contains plan content!
    ├── last_folder.txt                    reopened automatically on start
    └── <folder name>-<hash of path>/      one directory per plan folder
        ├── folder.txt                     full path of the plan folder
        ├── results.json                   current model result per plan
        ├── reviews.json                   human reviews
        ├── analysis_log.jsonl             every analysis ever made (one per line),
        │                                  used to compare versions
        ├── plans.xlsx / last_run.csv      exports
        └── cache/                         resized images + originals for the viewer

A plan counts as analysed if results.json has an entry for its filename
and the file has not changed since (see is_current).
"""

import hashlib
import json
import os
import re
from datetime import datetime
from pathlib import Path

from models import FIELDS, Analysis, ImageData, Review


# PLANARCHIV_DATA_DIR: other location, e.g. for tests or a shared drive
DATA_DIR = Path(os.environ.get("PLANARCHIV_DATA_DIR") or Path(__file__).resolve().parents[1] / "data")

LAST_FOLDER_FILE = DATA_DIR / "last_folder.txt"

RESULTS_FILE = "results.json"
REVIEWS_FILE = "reviews.json"
LOG_FILE = "analysis_log.jsonl"


# ------------------------------------------------------------
# Paths
# ------------------------------------------------------------

def folder_dir(folder: Path) -> Path:
    """Project directory for one plan folder (created if missing)."""

    folder = Path(folder).expanduser().resolve()

    slug = re.sub(r"[^A-Za-z0-9_-]+", "_", folder.name)[:40] or "folder"
    key = hashlib.sha1(str(folder).encode()).hexdigest()[:8]

    path = DATA_DIR / f"{slug}-{key}"
    path.mkdir(parents=True, exist_ok=True)

    info = path / "folder.txt"
    if not info.exists():
        info.write_text(str(folder), encoding="utf-8")

    return path


def remember_folder(folder: Path):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    LAST_FOLDER_FILE.write_text(str(Path(folder).expanduser().resolve()), encoding="utf-8")


def last_folder() -> Path | None:
    """Folder used last time, if it still exists."""

    if not LAST_FOLDER_FILE.exists():
        return None

    folder = Path(LAST_FOLDER_FILE.read_text(encoding="utf-8").strip())

    return folder if folder.is_dir() else None


# ------------------------------------------------------------
# File versions
# ------------------------------------------------------------

def file_stat(path: Path) -> str:
    stat = path.stat()
    return f"{stat.st_size}-{stat.st_mtime_ns}"


def file_sha1(path: Path) -> str:
    digest = hashlib.sha1()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def make_analysis(path: Path, script: str) -> Analysis:
    return Analysis(
        script=script,
        at=datetime.now().isoformat(timespec="seconds"),
        file_sha1=file_sha1(path),
        file_stat=file_stat(path),
    )


def is_current(entry: ImageData, path: Path) -> bool:
    """
    Was this entry made from the file as it is now?
    Size + modification time unchanged -> yes (fast).
    Otherwise compare the content hash: a copied folder has new
    modification times but the same content -> still current.
    """

    analysis = entry.analysis

    if analysis is None:
        return False

    if analysis.file_stat == file_stat(path):
        return True

    if analysis.file_sha1 == file_sha1(path):
        analysis.file_stat = file_stat(path)   # remember the new time
        return True

    return False


# ------------------------------------------------------------
# Reading / writing
# ------------------------------------------------------------

def write_json(path: Path, data):
    """Atomic write: never leaves a half-written file behind."""

    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def load_results(folder: Path) -> dict[str, ImageData]:

    path = folder_dir(folder) / RESULTS_FILE

    if not path.exists():
        return {}

    return {
        e["filename"]: ImageData.model_validate(e)
        for e in json.loads(path.read_text(encoding="utf-8"))
    }


def save_results(folder: Path, entries: dict[str, ImageData]):
    """Model results only - reviews are kept in reviews.json."""

    write_json(
        folder_dir(folder) / RESULTS_FILE,
        [
            e.model_dump(mode="json", exclude={"review"})
            for e in sorted(entries.values(), key=lambda e: e.filename.casefold())
        ],
    )


def append_log(folder: Path, entry: ImageData):
    """Keep every analysis, also overwritten ones (for version comparison)."""

    line = json.dumps(entry.model_dump(mode="json", exclude={"review"}), ensure_ascii=False)

    with open(folder_dir(folder) / LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def read_log(folder: Path) -> list[dict]:

    path = folder_dir(folder) / LOG_FILE

    if not path.exists():
        return []

    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def load_reviews(folder: Path) -> dict[str, Review]:

    path = folder_dir(folder) / REVIEWS_FILE

    if not path.exists():
        return {}

    return {
        name: Review.model_validate(r)
        for name, r in json.loads(path.read_text(encoding="utf-8")).items()
    }


def save_reviews(folder: Path, reviews: dict[str, Review]):
    write_json(
        folder_dir(folder) / REVIEWS_FILE,
        {name: r.model_dump(mode="json", exclude_none=True) for name, r in sorted(reviews.items())},
    )


# ------------------------------------------------------------
# One-time import of results that v8 / v9 wrote into the plan folder
# ------------------------------------------------------------

def pin_v8_reviews(plan_folder: Path, reviews: dict[str, Review]) -> bool:
    """
    v8 stored a confirmed value as None ("same as the model"). Fill in the
    v8 value the reviewer actually saw ("" = the model found nothing).
    Returns True if something was filled in.
    """

    open_fields = [
        (name, f) for name, r in reviews.items() for f in FIELDS if getattr(r, f) is None
    ]

    v8_path = Path(plan_folder) / "plan_metadata_v8.json"

    if not open_fields or not v8_path.exists():
        return False

    v8 = {
        e["filename"]: e.get("metadata") or {}
        for e in json.loads(v8_path.read_text(encoding="utf-8"))
    }

    changed = False

    for name, f in open_fields:
        if name in v8:
            setattr(reviews[name], f, v8[name].get(f) or "")
            changed = True

    return changed


def import_from_plan_folder(plan_folder: Path) -> list[str]:
    """
    If this plan folder has no project data yet, take over what earlier
    versions stored in the plan folder itself - so nothing has to be
    analysed or reviewed again. The plan folder is not changed.
    Returns short notes about what was imported.
    """

    plan_folder = Path(plan_folder)
    notes = []

    # results: newest of v9 / v8 (same data model as v10)
    if not (folder_dir(plan_folder) / RESULTS_FILE).exists():

        for version in ("v9", "v8"):

            source = plan_folder / f"plan_metadata_{version}.json"

            if not source.exists():
                continue

            at = datetime.fromtimestamp(source.stat().st_mtime).isoformat(timespec="seconds")
            entries = {}

            for raw in json.loads(source.read_text(encoding="utf-8")):

                raw.pop("review", None)
                entry = ImageData.model_validate(raw)
                path = plan_folder / entry.filename

                if not path.exists():
                    continue

                # assumes the file has not changed since that run
                entry.analysis = Analysis(
                    script=f"scan_plan_htw_api_{version}.py",
                    at=at,
                    file_sha1=file_sha1(path),
                    file_stat=file_stat(path),
                )
                entries[entry.filename] = entry
                append_log(plan_folder, entry)

            save_results(plan_folder, entries)
            notes.append(f"{len(entries)} results imported from {source.name}")
            break

    # reviews
    if not (folder_dir(plan_folder) / REVIEWS_FILE).exists():

        source = plan_folder / "plan_reviews.json"

        if source.exists():
            reviews = {
                name: Review.model_validate(r)
                for name, r in json.loads(source.read_text(encoding="utf-8")).items()
            }
            pin_v8_reviews(plan_folder, reviews)
            save_reviews(plan_folder, reviews)
            notes.append(f"{len(reviews)} reviews imported from {source.name}")

    return notes
