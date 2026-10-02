# OCR Approach — Evaluation

As a first attempt at extracting text from scanned historical building plans, we tried
classic OCR using [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR).

## What we did

- Ran PaddleOCR on a scanned technical drawing (`00000018.TIF`, ~9500×6800 px) from the
  document set.
- Since the scan is much larger than a typical OCR input, the image was split into
  overlapping tiles, each tile run through OCR separately, and the resulting text boxes
  merged back together (de-duplicated by position and text) into one result for the full
  page.
- Added automatic document-orientation detection, since scans are not always upright.
  This first produced a bug: the orientation model reports how far the page is currently
  rotated, not the angle to rotate it by, so the first version rotated the image in the
  wrong direction and left it upside down. Once the rotation direction was corrected, the
  page was oriented correctly and recognition improved noticeably.

## Result

The screenshot below shows an excerpt of the plan (a door detail, left) next to the raw
text PaddleOCR recognized for the full page (right):

![OCR example: plan excerpt and recognized text](ocr_example.png)

## Conclusion

OCR technically works end-to-end (orientation correction, tiling, recognition, merging),
and parts of the printed title block and headings come through readable (e.g.
"Revisionszeichnung", "Ansicht A.", "Ansicht B."). However, the overall quality is not
good enough to be useful: handwritten and hatched/technical-drawing text is frequently
garbled, duplicated, or misrecognized (including unrelated characters such as "中"), and
dimension labels and annotations are mostly unreadable.

Because of this, we decided not to pursue the classic OCR pipeline further and to focus
on an LLM-based approach for text extraction instead.
