"""Step 2: export PaddleOCR's raw JSON result and visualization.

Run after activating the PaddleOCR environment:
    python 02_paddleocr_export.py

The script reads the included synthetic ``example.png`` and writes files to
``paddle_output`` next to this script. The original image remains unchanged.
"""

from pathlib import Path

from paddleocr import PaddleOCR


SCRIPT_DIR = Path(__file__).resolve().parent
IMAGE_PATH = SCRIPT_DIR / "example.png"
OUTPUT_DIR = SCRIPT_DIR / "paddle_output"


def main() -> None:
    ocr = PaddleOCR(
        use_doc_orientation_classify=True,
        use_doc_unwarping=False,
        use_textline_orientation=False,
    )
    results = ocr.predict(input=str(IMAGE_PATH))
    OUTPUT_DIR.mkdir(exist_ok=True)
    for result in results:
        result.save_to_json(str(OUTPUT_DIR))
        result.save_to_img(str(OUTPUT_DIR))
    print(f"Saved raw results to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
