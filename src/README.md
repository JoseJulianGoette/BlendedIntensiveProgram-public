# src - current application (v10)

| File | Purpose |
|---|---|
| `app.py` | local web app - start with `python3 src/app.py` |
| `static/index.html` | web page: list, search, plan popup, review form |
| `scan_plan_htw_api_v10.py` | analysis pipeline (also usable alone: `python3 src/scan_plan_htw_api_v10.py [--all]`) |
| `models.py` | data model: `ImageData`, `Metadata`, `Review`, `Analysis`, traffic lights |
| `store.py` | storage in `data/` (results, reviews, log, cache), change detection |
| `search.py` | fuzzy search over location and title |
| `export_xlsx.py` | formatted Excel export |

How the parts work together: [docs/architecture.md](../docs/architecture.md).
