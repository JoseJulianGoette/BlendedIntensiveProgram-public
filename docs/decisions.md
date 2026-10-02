# Key decisions

Why the pipeline and app are built the way they are. Measurements were made
with generated test images unless stated otherwise. Dates: see [CHANGELOG.md](../CHANGELOG.md).

## 1. Fixed data model instead of free text (v5)

- **Decision:** the model must answer with JSON that matches `Metadata`,
  enforced by the server (JSON schema, `response_format`).
- **Why:** free text needed guessing to parse, and results must be stored,
  searched and compared per field.

## 2. Repeatable settings (v5)

- **Decision:** temperature 0, fixed seed, no thinking.
- **Why:** the same plan should give the same answer. Thinking needs a
  temperature above 0 and was slower.
- **Limit:** on the server identical requests still differ now and then.
  v6 and v7 had identical input and about one value in six differed. Compare
  versions on reviewed plans, not on single runs.

## 3. Traffic light from token probabilities, not from the model's own opinion (v5/v6)

- **Decision:** the probability of the least certain token of a value
  decides: confident ≥ 90 %, check ≥ 50 %, below that uncertain.
- **Why:** self-assessment of language models is poorly calibrated. The
  token probabilities showed invented values clearly: a made-up date had
  45 %, the correct title above 96 %.
- **Detail:** alternatives that are only a different split of the same
  text (" Ab"+"ort" vs " Abort") count as agreeing, otherwise correct
  words looked uncertain.
- **Open:** the thresholds 90 / 50 are starting values; calibrate them with
  `analysis/compare_versions.py` once enough plans are reviewed.

## 4. Whole plan instead of tiles (v7)

- **Decision:** send the whole plan, not overlapping tiles.
- **Test:** tiles (3×3) lost the context - title in one tile, station name
  in another - and the model invented values per tile (a wrong city, a
  wrong year). The whole plan gave the right location and title.
  9 times the requests as well.
- **Possible later:** whole plan plus a high-resolution crop of the title
  block in one request.

## 5. 16 MP pixel budget and 1-bit fix (v9)

- **Measurement on the HTW server:** 1 image token per 32×32 px, at most
  16,240 tokens per image (~16.6 MP). Larger images are shrunk by the
  server itself, in a way we cannot control.
- **Decision:** shrink to 16 MP ourselves (v8: fixed 3000 px ≈ 6 MP, a
  third of the budget).
- **1-bit scans:** Pillow ignores the good resampling filter for 1-bit
  images and drops pixels. Test: 61 of 92 thin lines were left, 92 of 92
  after converting to grayscale first.
- **Cost:** about 7-16 s per plan instead of 1-4 s.
- **Observed on the real plans:** station names read better, more
  single-letter mistakes in long titles (mostly flagged). One idea to test:
  more contrast after shrinking.

## 6. Date removed (v8)

- **Decision:** team decision.
- **Why:** dates were often missing, handwritten or invented and got low
  traffic lights; location and title are what makes plans findable.

## 7. Human in the loop with separate reviews (v8, v9)

- **Decision:** reviews are stored next to the model's values, never
  instead of them.
- **Why:** keeps the reviewed value traceable, and reviews are the ground
  truth for comparing versions.
- **v9:** a review stores the confirmed value itself. Before that, "confirmed"
  meant "same as the model", and a new model version would have changed a
  value a human had checked.

## 8. Everything stored in the project, plan folder read-only (v10)

- **Decision:** results, reviews, exports and cache are stored in `data/`
  in the project; only new or changed plans are analysed.
- **Why:**
  - restarting the app should not mean re-analysing 42 plans;
  - the plan archive may be read-only or a network drive.
- **`data/` is git-ignored** because it contains BVG plan content.
- **Later:** for several people reviewing at the same time, a database
  (e.g. SQLite) instead of JSON files.

## 9. A new file per pipeline version

- **Decision:** every change of the pipeline gets a new file (`versions/`),
  older ones stay runnable.
- **Why:** results of versions can be compared side by side, and it stays
  clear which result came from which code.
