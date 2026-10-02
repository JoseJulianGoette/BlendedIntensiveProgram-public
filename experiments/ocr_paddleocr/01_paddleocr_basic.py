"""Step 1: run PaddleOCR on one image and print the raw result.

Preparation from this directory:
    python -m pip install -r requirements.txt

The included ``example.png`` is loaded relative to this script, so the command
can be run from any working directory:
    python 01_paddleocr_basic.py

On the first run, PaddleOCR may download model files. No GPU configuration is
used by this example.
"""

from pathlib import Path

from paddleocr import PaddleOCR


SCRIPT_DIR = Path(__file__).resolve().parent
IMAGE_PATH = SCRIPT_DIR / "example.png"


def main() -> None:
    ocr = PaddleOCR(
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
    )
    results = ocr.predict(input=str(IMAGE_PATH))
    for result in results:
        result.print()


if __name__ == "__main__":
    main()
