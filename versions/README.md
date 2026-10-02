# Pipeline versions v1 - v9

Earlier versions of the analysis pipeline. Each change got a new file
instead of editing the old one, so results of different versions can be
compared. The current version (v10) is `src/scan_plan_htw_api_v10.py`.
Details, authors and dates: [CHANGELOG.md](../CHANGELOG.md).

| Version | Main change | Reads |
|---|---|---|
| v1 | title of each plan via the HTW vision model | title |
| v2 | shrink to 3000 px, optional crop | title |
| v3 | parallel requests, image cache, timing statistics | title |
| v4 | thinking on, timeouts, retries | title |
| v5 | streaming, connection test; later: fixed data model (JSON schema), repeatable settings, PDFs, traffic light for the title | location, title, date |
| v6 | traffic light for every field, clearer location rule | location, title, date |
| v7 | used by the first web app; entries with errors are kept | location, title, date |
| v8 | human review, date removed, original resolution | location, title |
| v9 | 16 MP pixel budget (server limit), 1-bit scans to grayscale | location, title |
| v10 | results stored in the project, only new plans analysed -> `src/` | location, title |

## Running an old version

```bash
python3 versions/scan_plan_htw_api_v9.py
```

Each version asks for the plan folder and writes its results **into that
folder** (`plan_metadata_vN.csv/.json/.xlsx`) - unlike v10, which stores
everything in the project.

## Shared modules

- v5 - v7 use the frozen data model with a date field:
  `models_v7.py`, `export_xlsx_v7.py` (in this folder).
- v8 - v9 use the current modules in `src/` (a path line at the top of
  each file makes that work from this folder).
