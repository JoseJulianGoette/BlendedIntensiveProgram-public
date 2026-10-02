# Experiments

Early experiments. Not used by the app, kept for reference.

| Folder | What | Who / when |
|---|---|---|
| `htw_connection/` | first connection tests to the HTW API (text and vision request with a test photo) | Jose, 2026-09-28 |
| `ocr_paddleocr/` | OCR with PaddleOCR: basic run, export, evidence with coordinates, tiling a large plan. See its `README.txt` | Jose, 2026-09-28 |

`ocr_paddleocr/04_paddleocr_tile.py` expects a plan as `ocr_paddleocr/00000018.TIF`.
The plan is BVG data and not in the repository - put your own copy there.
`htw_connection/test_htw_vision.py` asks for the path of the image to send.
`ocr_paddleocr/paddle_output/` is generated and git-ignored.

Findings that shaped the pipeline (details in [docs/decisions.md](../docs/decisions.md)):
sending tiles of a plan to the vision model was worse than sending the
whole plan; OCR could still help for small print in a later version.
