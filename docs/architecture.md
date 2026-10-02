# Architecture (v10)

## Overview

```
 plan folder (read only)          src/                                   data/<folder>-<hash>/
 ┌──────────────────┐   ┌──────────────────────────────────────┐   ┌─────────────────────┐
 │ *.tif *.pdf ...  │──>│ scan_plan_htw_api_v10.py             │──>│ results.json        │
 └──────────────────┘   │  1 prepare image (≤16 MP, cache)     │   │ analysis_log.jsonl  │
                        │  2 ask model (HTW server, Qwen VL)   │   │ cache/              │
                        │  3 parse JSON -> Metadata            │   │ plans.xlsx          │
                        │  4 traffic light from logprobs       │   └─────────┬───────────┘
                        └──────────────────────────────────────┘             │
                        ┌──────────────────────────────────────┐             │
 browser  <────────────>│ app.py  (local server, 127.0.0.1)    │<────────────┘
 static/index.html      │  list, search.py, popup, reviews ────┼──> reviews.json
                        └──────────────────────────────────────┘
```

## Analysis pipeline (`scan_plan_htw_api_v10.py`)

For every plan that is new or changed (see *Storage*), two at a time:

1. **Prepare the image** (`prepare_image`)
   - First page only: multi-page TIFF → page 1; a PDF is rendered, at most
     at the resolution of the embedded scan.
   - 1-bit scans → grayscale (keeps thin lines).
   - Shrink to at most `MAX_PIXELS` = 16 MP, just below the server limit.
   - Save as JPEG and cache it.
2. **Ask the model:** prompt plus image to the HTW server. Settings:
   - `temperature 0`, fixed seed, no thinking;
   - JSON schema of `Metadata` (location, title) as the required answer format;
   - token probabilities (logprobs) requested.
3. **Parse** the JSON answer and validate it against `Metadata`.
4. **Traffic light** per field (`rate_field`):
   - The probability of the least certain token of the value counts.
   - Alternative tokens that spell the same text are added up
     (" Ab"+"ort" = " Abort").
   - confident ≥ 90 %, check ≥ 50 %, uncertain below or not found.
5. **Store:**
   - The result goes to `results.json`, replacing the old one.
   - It is also appended to `analysis_log.jsonl`.
   - It is stamped with the script, the time and the file version
     (`Analysis`).

Errors (unreadable file, timeout) do not stop the run: the plan is kept
as a red entry with the error message.

## Data model (`models.py`)

```
ImageData
├── filename
├── metadata              what the model read: location, title
├── location_confidence   traffic light + probability of the model
├── title_confidence
├── error                 if the analysis failed
├── analysis              script, time, file hash + size/mtime
└── review                human review: confirmed/corrected values and traffic lights
```

- `value(field)` / `level(field)` return the reviewed value / traffic light
  if there is one, otherwise the model's.
- The model's values are never overwritten by a review.

## Storage (`store.py`)

- **One directory per plan folder:** `data/<folder name>-<hash of the path>/`.
- **Plan folder is never written:** it may be read-only.
- **Tests / shared drive:** the environment variable `PLANARCHIV_DATA_DIR`
  moves `data/` elsewhere.
- **"Analysed" means:** `results.json` has an entry for the file name and
  the file is unchanged. The quick check is size + modification time; if
  those changed, the content hash (SHA-1) is compared, so a copied folder
  is not analysed again.
- **Import:** results and reviews that v8 / v9 wrote into the plan folder
  are imported once.

## App (`app.py`, `static/index.html`)

Local HTTP server on 127.0.0.1 (standard library only). The page polls the
state every second while an analysis runs.

| Endpoint | Purpose |
|---|---|
| `GET /api/state` | folder, progress, all entries (with reviewed values) |
| `POST /api/analyze` | open a folder: `mode: "new"` (new/changed plans) or `"all"` (re-analyse everything) |
| `GET /api/search?q=` | fuzzy search over reviewed location and title |
| `GET /api/image?file=&full=1` | plan preview / original resolution |
| `POST /api/review`, `/api/review/reset` | save / undo a human review |
| `GET /api/export.xlsx` | Excel export |
| `POST /api/pick-folder` | native folder dialog |

`API_VERSION` in `app.py` and `index.html` must match; otherwise the page
asks to restart the server (a server started with older code cannot serve
the page correctly).

## Search (`search.py`)

- **Same normalisation for query and data:** casefold (ß → ss), long s,
  umlauts, Thor → Tor, abbreviations (Str. → strasse), without filler words.
- **Matching:** exact, then word start, part of a word, sound-alike
  (Kölner Phonetik), then similar (Levenshtein).
- **Renamed stations:** an alias list (e.g. Reichskanzlerplatz ↔ Theodor-Heuss-Platz).
- **Edge cases** are written down as tests in `tests/test_search.py`.
