"""Step 3: convert PaddleOCR output into a small evidence JSON file.

Each evidence item keeps the recognized text, confidence, and original polygon
coordinates. The original image and raw OCR output remain unchanged.
"""

import json
from pathlib import Path
from typing import Any

from paddleocr import PaddleOCR


SCRIPT_DIR = Path(__file__).resolve().parent
IMAGE_PATH = SCRIPT_DIR / "example.png"
OUTPUT_PATH = SCRIPT_DIR / "paddle_output/paddle_evidence.json"


def result_data(result: Any) -> dict[str, Any]:
    """Return the serializable result dictionary used by PaddleOCR 3.x."""
    data = result.json
    if isinstance(data, str):
        data = json.loads(data)
    return data.get("res", data)


def main() -> None:
    ocr = PaddleOCR(
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
    )
    results = ocr.predict(input=str(IMAGE_PATH))

    evidence = []
    for result in results:
        data = result_data(result)
        texts = data.get("rec_texts", [])
        scores = data.get("rec_scores", [])
        polygons = data.get("rec_polys", data.get("dt_polys", []))
        for text, score, polygon in zip(texts, scores, polygons):
            evidence.append(
                {
                    "text": str(text),
                    "polygon": polygon,
                    "confidence": float(score),
                    "source": IMAGE_PATH.name,
                    "engine": "paddleocr",
                }
            )

    OUTPUT_PATH.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(f"Wrote {len(evidence)} evidence items to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
