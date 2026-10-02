# Planarchiv - making BVG U-Bahn plans searchable

Blended Intensive Programme project with the BVG (Berliner Verkehrsbetriebe).

The BVG archive holds scanned construction plans of the Berlin U-Bahn - many
of them decades old, with handwritten or Kurrent lettering and old
spellings. This project reads every plan with a vision language model, pulls
out **where** the plan is about (location) and **what** it shows (title),
says how sure it is, and makes the plans searchable - also when the search
uses today's spelling and the plan an old one. A person checks and corrects
the results in a local web app.

**Status (2026-09-30):** working prototype, pipeline version **v10**,
tested by the team on 42 real plans.

---

## Contents

1. [What it does](#what-it-does)
2. [How it works](#how-it-works)
3. [Getting started](#getting-started)
4. [Using the app](#using-the-app)
5. [Results and findings](#results-and-findings)
6. [Project history](#project-history)
7. [Repository structure](#repository-structure)
8. [Data handling](#data-handling)
9. [Known issues and next steps](#known-issues-and-next-steps)
10. [Team](#team)

---

## What it does

- **Reads plans** (TIFF, PNG, JPEG, PDF, ...) with the Qwen vision model on
  the HTW Berlin server and extracts **location** and **title**.
- **Traffic light per field:** 🟢 *confident* / 🟡 *check* / 🔴 *uncertain*,
  computed from the model's own token probabilities - not from asking the
  model how sure it is.
- **Fuzzy search:**
  - ß/ss, umlauts (ö/oe/o), old spellings (Thor → Tor, Cottbuser → Kottbusser);
  - abbreviations (Str., U-Bhf.), typos and misread letters;
  - renamed stations (Theodor-Heuss-Platz ↔ Reichskanzlerplatz).
- **Human in the loop:** location, title and traffic light can be
  corrected in the app. Corrections are stored separately and are never
  overwritten by the model.
- **Original resolution viewer:** click into a plan to see every pixel of
  the scan.
- **Remembers everything:**
  - results are saved in the project;
  - on the next start the app shows them at once and only analyses new
    or changed plans;
  - "Re-analyse all plans" runs the model again on everything.
- **Excel export** with traffic-light colours, review status and what the
  model originally read.
- **Keeps every plan:** unreadable files and notes in file names
  ("ungültig", "nie gebaut", ...) are flagged, not dropped.

## How it works

```
plan folder (read only)
      │
      ▼
1  prepare image     first page · 1-bit scans to grayscale · shrink to ≤ 16 MP · cache
2  ask the model     HTW server (Qwen VL) · JSON schema {location, title} · temperature 0
3  check the answer  parse JSON · validate against the data model
4  traffic light     least certain token of each value: ≥ 90 % 🟢 · ≥ 50 % 🟡 · else 🔴
5  store             data/<folder>/results.json + analysis log
      │
      ▼
web app  ── list · search · plan viewer · review form ──►  reviews.json · Excel
```

- **16 MP:** the HTW server accepts at most about 16.6 megapixels per image
  (measured). Anything bigger it shrinks itself, so we shrink to just
  below that ourselves.
- **Two plans at a time:** each takes about 7-16 seconds, so 42 plans take
  about 3-4 minutes.
- **Details:** [docs/architecture.md](docs/architecture.md).

## Getting started

**Requirements**
- Python 3.10 or newer (tested with 3.13).
- Access to the HTW API server (HTW network / VPN) and an HTW API key.

```bash
pip install -r requirements.txt
```

Put the API key and the server address into a file `.env` in the
project folder (git-ignored, never commit it):

```bash
cp .env.example .env
```

Then enter the key (`HTW_API_KEY`) and the HTW server address
(`HTW_BASE_URL`, ask the team) in `.env`.

```bash
python3 src/app.py
```

The app opens at http://127.0.0.1:8765. It is only reachable from your own
computer.

| Task | Command |
|---|---|
| Start the app | `python3 src/app.py` |
| … on another port / without opening the browser | `python3 src/app.py --port 8766 --no-browser` |
| Analyse without the app | `python3 src/scan_plan_htw_api_v10.py` (`--all` = analyse everything again) |
| Run the tests | `python3 -m unittest discover -s unittests -v` |
| Compare versions against the reviews | `python3 analysis/compare_versions.py /path/to/plans` |

If the start fails with "Port 8765 is already in use", the app is still
running somewhere: stop it with Ctrl+C there, or use `--port 8766`.

## Using the app

1. **Open the folder** with the plans ("Choose folder" or paste the path,
   then "Open folder").
   - The first time, all plans are analysed and the list fills up while
     it runs.
   - After that the app opens the last folder by itself and only analyses
     plans that are new or changed.
2. **Find plans:**
   - Type part of a location or title, e.g. "alex", "Kottbusser Tor",
     "Grundriss".
   - Every hit says why it matched (*spelling variant*, *sounds alike*,
     *renamed*, ...).
3. **Review:**
   - Set **Show: Not reviewed** and **Sort by: Traffic light, uncertain first**.
   - Open a plan, compare location and title with the scan, correct them,
     set the traffic light.
   - Use **Save and next** to go through the list.
   - Under each field the app shows what the model read.
4. **Export:** "Download Excel". The file is also kept up to date in the
   project data folder.
5. **Re-analyse all plans** only after the pipeline or its settings changed.
   It overwrites the model's values; reviews stay.

## Results and findings

Measured with generated test images unless stated otherwise. Reasons and
numbers in detail: [docs/decisions.md](docs/decisions.md).

| Finding | Consequence |
|---|---|
| The HTW server counts 1 token per 32×32 px and accepts at most ~16.6 MP per image | shrink to 16 MP ourselves (v9) instead of 3000 px ≈ 6 MP |
| Pillow drops thin lines when shrinking 1-bit scans (61 of 92 lines left) | convert to grayscale first (92 of 92) |
| Tiling a plan lost context and made the model invent values | send the whole plan |
| Token probabilities expose invented values (a made-up date: 45 %, correct title: > 96 %) | traffic light from probabilities |
| Identical input gave different values in about 1 of 6 cases (v6 vs. v7, real plans) | compare versions on reviewed plans, not single runs |
| v9 read station names better than v8 on the real plans (e.g. Osloer Straße, Wilmersdorf, Gesundbrunnen), but made more single-letter mistakes in long titles - mostly flagged 🟡/🔴 | keep v9 image preparation; test more contrast next |
| Dates were often missing, handwritten or invented | date removed (team decision, v8) |

For a reliable score, review plans in the app and run
`analysis/compare_versions.py`. Eledina's ground truth for v9 is in
`analysis/results/`.

## Project history

Full detail with commits: [CHANGELOG.md](CHANGELOG.md).
Pipeline versions: [versions/README.md](versions/README.md).

| Date | Step | Who |
|---|---|---|
| 2026-09-28 | HTW API connection tests | Jose |
| 2026-09-28 | v1-v5: title per plan, shrinking, parallel requests, cache, streaming; PaddleOCR experiments | Jose |
| 2026-09-28 | v5 translated to English, first results | Eledina |
| 2026-09-29 | v5 extended: fixed data model, repeatable settings, PDFs, traffic light | Jose |
| 2026-09-29 | v6: traffic light for every field | Jose |
| 2026-09-29 | v7: web app, fuzzy search, Excel, BVG design, English UI | Jose |
| 2026-09-29 | v8: review in the app, date removed, original resolution | Jose |
| 2026-09-30 | v9: 16 MP budget, 1-bit fix, version comparison | Jose |
| 2026-09-30 | v6-v9 run and compared on the real plans | Jose |
| 2026-09-30 | ground truth for v9, image size analysis | Eledina |
| 2026-09-30 | v10: results stored in the project, only new plans analysed | Jose |
| 2026-09-30 | repository restructure, documentation, tests | Jose |

## Repository structure

```
src/                         current application (v10)
├── app.py                   local web app (server, API)
├── static/index.html        web page: list, search, viewer, review form
├── scan_plan_htw_api_v10.py analysis pipeline
├── models.py                data model (ImageData, Metadata, Review, Analysis)
├── store.py                 storage in data/, change detection
├── search.py                fuzzy search
└── export_xlsx.py           Excel export
unittests/                   62 unit tests - generated data only
testing/                     title evaluation against the ground truth (Daniel)
analysis/                    version comparison, image sizes, result files (results/)
versions/                    pipeline v1-v9 (history, still runnable)
experiments/                 HTW connection tests, PaddleOCR
docs/                        architecture.md, decisions.md
data/                        created by the app - git-ignored
CHANGELOG.md                 who did what, when and why
```

Every folder has a README with its contents.

**Where the app keeps its data** (per plan folder, never inside the plan folder):

```
data/<folder name>-<hash>/
├── results.json         current result per plan
├── reviews.json         human reviews  ← manual work, back it up
├── analysis_log.jsonl   every analysis ever made (for comparing versions)
├── plans.xlsx           Excel export
├── last_run.csv         timings of the last run
└── cache/               resized images and originals for the viewer
```

## Data handling

- **BVG plans are not in the repository.** The plans belong to the BVG.
  Plan images (`*.tif`, `*.tiff`) and `data/` are git-ignored, so plans
  do not end up in the repository by accident.
- **In the repository on purpose:** the results read from the plans and
  the ground truth (`analysis/results/`, `testing/`) - no plan images.
- **The API key and the server address are not in the repository.**
  They are read from `.env`
  (git-ignored), see *Getting started*.
- **The plan folder is only read.** The app never writes into it, so it can
  be a read-only archive or network drive.

## Known issues and next steps

**Known issues**
- The model is not fully deterministic on the server (see findings).
- The list of renamed stations in `src/search.py` has only a few entries.

**Next steps (ideas, not built yet)**
- Calibrate the traffic-light thresholds (90 / 50 %) with the reviewed plans.
- Fewer letter mistakes:
  - more contrast after shrinking;
  - or read each plan 2-3 times and take the majority.
- Whole plan plus a high-resolution crop of the title block in one request,
  for small print.
- "Re-analyse only outdated plans" button, to resume an interrupted re-analysis.
- Flag plans where versions disagree - a strong hint that a human should look.
- Clean up and present the extracted fields (e.g. link to a station
  list, map, timeline).
- Several people reviewing at once: database (SQLite) instead of JSON files.

## Team

- **Jose** (Josejuliangoette): project lead, requirements, testing on the real plans.
- **Eledina:** translation, ground truth, image size analysis.

Further reading:
- [DOCUMENTATION.md](DOCUMENTATION.md): the whole project in one document (data, development, testing).
- [CHANGELOG.md](CHANGELOG.md): who did what, when, why.
- [docs/architecture.md](docs/architecture.md): how it works.
- [docs/decisions.md](docs/decisions.md): why it is built this way.
