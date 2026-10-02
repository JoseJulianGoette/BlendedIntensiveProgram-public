# Changelog

What was built, when, by whom and why - in the order it happened.
Newest first. Versions of the analysis pipeline are kept side by side
(`versions/`, current one in `src/`), so every step can be re-run.

| Person | Role |
|---|---|
| Jose (git: Josejuliangoette) | project lead, requirements, pipeline and app, testing on real plans |
| Eledina | translation of v5, ground truth, image size analysis and charts |
| Moritz S | documentation of the OCR approach |
| Daniel | testing: title evaluation against the ground truth |

---

## 2026-10-01 - Final presentation and documentation completed

*Who:* the whole team.
*Commits (documentation):* `0df08ce`, `40dafc9`, `c11e5e3`, `bd83986`, `08a17e6`, `7298926`, `d0ac487`.

- **Final presentation finalized:** the results of all group members were
  combined into the final presentation (team leads Asia and Adriana).
- **Documentation completed:** `DOCUMENTATION.md` brings
  together data, development and testing; README, testing documentation
  and evaluation charts were updated.

## 2026-10-01 - Title evaluation against the ground truth

*Who:* Daniel. *Commit:* `ec8e670`.
*Files:* `testing/`, `tests/` renamed to `unittests/`

- `evaluate_titles.py` (v1), `_v2.py`, `_v3.py` compare the titles read by the
  pipeline with the ground truth (42 plans): exact match, character and word
  similarity, suggested error categories, and (v3) accuracy per file type,
  title length, scale, DPI and megapixels.
- Result: 10 of 42 titles exactly right, 15 more near misses; very large
  scans (≥ 100 MP, shrunk below 25 %) were almost never exactly right.

## 2026-10-01 - OCR approach documented

*Who:* Moritz S. *Commit:* `ec65f61`.
*Files:* `docs/OCR_Attempt.md`

- Why classic OCR (PaddleOCR) was not pursued: printed headings are read,
  handwriting and drawing labels mostly not.

## 2026-09-30 - Charts: image sizes and ground truth

*Who:* Eledina. *Commits:* `b0cbdd4`, `d3985ab`.
*Files:* `analysis/plot_image_size_analysis.py`, `analysis/image_resolution_distribution.png`,
`analysis/image_resolution_groups.png`, `analysis/plot_ground_truth_location_status.py`,
`analysis/ground_truth_location_status.png`

- Distribution of plan resolutions and plans per resolution group (150 MP threshold, PDFs).
- Where the correct location in the ground truth comes from (identified manually,
  derived from the title, uncertain).

## 2026-09-30 - Repository restructure and documentation

*Who:* Jose. *Commits:* `5ccc9cc`, `dd51b7f`.

- New layout: `src/` (current app), `versions/` (v1-v9), `tests/`,
  `analysis/`, `experiments/`, `docs/`. Files were moved with `git mv`,
  so `git log --follow <file>` still shows the full history of each file.
- Documentation: `README.md`, this changelog, `docs/architecture.md`,
  `docs/decisions.md`, a README in every folder.
- New tests: `tests/test_models.py`, `tests/test_store.py`,
  `tests/test_image_prep.py` (62 tests in total, all synthetic data).
- Start commands changed: `python3 src/app.py` instead of `python3 app.py`.

## 2026-09-30 - v10: results stored in the project, only new plans analysed

*Who:* Jose. *Commit:* `ada209a`.
*Files:* `src/scan_plan_htw_api_v10.py`, `src/store.py`, `src/app.py`, `src/static/index.html`

- **Why:** every restart of the app analysed all plans again (3-4 min).
- Results, reviews, exports and the image cache are stored in the project
  under `data/<folder>-<hash>/` (git-ignored). The plan folder is only read.
- On start the app reopens the last folder and shows the saved results at
  once. Only new or changed plans are analysed (content hash, so copied
  folders are not re-analysed).
- "Re-analyse all plans" analyses everything again; model values are
  overwritten, human reviews are kept.
- Every analysis is appended to `analysis_log.jsonl`, so versions can still
  be compared after results were overwritten.
- v8/v9 results and reviews in the plan folder are imported once.

## 2026-09-30 - Image size analysis

*Who:* Eledina. *Commit:* `6c576fa`.
*Files:* `analysis/analyze_image_sizes.py`, `analysis/image_sizes.csv`

## 2026-09-30 - Ground truth for v9

*Who:* Eledina. *Commit:* `ceab8ae`.
*Files:* `analysis/results/title_location_groundtruth_vs_predictions_v9.xlsx`

## 2026-09-30 - Comparison of v6-v9 on the real plans

*Who:* Jose.

- v9 reads station names clearly better (e.g. "Osloer Straße" instead of
  "Oslaer Straße"), but makes more single-letter mistakes in long titles;
  most of them are flagged yellow/red by the traffic light.
- Even with identical input (v6 vs v7) about one value in six differed:
  the model is not fully deterministic on the server. Single runs prove little.

## 2026-09-30 - v9: bigger images for the model, 1-bit fix, version comparison

*Who:* Jose. *Commits:* `7e9ae82`, `6fad9a1`.
*Files:* `versions/scan_plan_htw_api_v9.py`, `analysis/compare_versions.py`

- **Measured** on the HTW server with a synthetic image: 1 token per
  32x32 px, at most 16,240 tokens (~16.6 MP) per image; larger images are
  shrunk by the server itself. v8 sent 3000 px (~6 MP).
- Pixel budget of 16 MP instead of a fixed 3000 px side.
- 1-bit scans are converted to grayscale before shrinking: Pillow drops
  thin lines of 1-bit images otherwise (test: 61 of 92 lines left, 92/92 with the fix).
- Reviews now store the confirmed value itself (v8 stored "no change",
  which a new model version could silently change).
- `compare_versions.py` scores every version against the human reviews.

## 2026-09-29 - v8: human in the loop, date removed, original resolution

*Who:* Jose. *Commit:* `7e9ae82`.
*Files:* `versions/scan_plan_htw_api_v8.py`, `src/models.py`, `src/app.py`, `src/static/index.html`

- Location, title and traffic light can be edited in the app; reviews are
  stored separately from the model's values.
- Date removed completely (unreliable; team decision).
- Plans are shown in original resolution (1-bit scans as lossless PNG).
- v5-v7 were frozen on `versions/models_v7.py` / `export_xlsx_v7.py`.

## 2026-09-29 - v7: local app, fuzzy search, Excel, BVG design

*Who:* Jose. *Commit:* `7e9ae82`.
*Files:* `versions/scan_plan_htw_api_v7.py`, `src/app.py`, `src/search.py`,
`src/export_xlsx.py`, `src/static/index.html`, `tests/test_search.py`

- Local web app: choose a folder, analysis in the background, list,
  search, popup with the plan. English UI in the style of bvg.de.
- Fuzzy search on location and title: ß/ss, umlauts, old spellings
  (Thor/Tor), abbreviations, sound-alike (Kölner Phonetik), typos,
  renamed stations. Edge cases written down as 34 tests.
- All plans are kept, errors and filename notes ("ungültig", ...) are flagged.
- Formatted Excel export.
- Tiling the plans was tested and rejected (worse than the whole image).

## 2026-09-29 - v6: traffic light for location and date

*Who:* Jose. *Commit:* `7e9ae82`.
*Files:* `versions/scan_plan_htw_api_v6.py`

- Traffic light for every field. Prompt: location without words like
  "Haltestelle" (they made the location ambiguous).

## 2026-09-29 - v5 extended: fixed data model, repeatable results, PDFs, traffic light

*Who:* Jose. *Commit:* `7e9ae82`.
*Files:* `versions/scan_plan_htw_api_v5.py`, `src/models.py`

- The model answers in a fixed structure (`Metadata`: location, title,
  date) enforced by a JSON schema; results as `ImageData`.
- Repeatable settings: no thinking, temperature 0, fixed seed.
- PDFs are rendered and analysed like images.
- Traffic light for the title from the model's token probabilities.

## 2026-09-28 - v5 translated, first results

*Who:* Eledina. *Commit:* `e2fd36d`.
*Files:* `versions/scan_plan_htw_api_v5.py`, `analysis/results/results_v5.csv`

## 2026-09-28 - v1-v5 and OCR experiments

*Who:* Jose. *Commit:* `fb374d6`.
*Files:* `versions/scan_plan_htw_api_v1.py` ... `v5.py`, `experiments/ocr_paddleocr/`

- v1: send each plan image to the vision model, ask for the title, write a CSV.
- v2: shrink to 3000 px / optional crop before sending; prompt mentions metro stations.
- v3: 4 parallel requests, thinking switched off, image cache, timing columns in the CSV.
- v4: thinking switched on again, 2 parallel requests, timeouts and retries.
- v5: streaming with live progress, connection test before the run
  (translated to English later by Eledina).
- PaddleOCR experiments (basic OCR, export, evidence, tiling).

## 2026-09-28 - HTW API connection tests

*Who:* Jose. *Commits:* `2e7d089`, `771aa00`.
*Files:* `experiments/htw_connection/`
