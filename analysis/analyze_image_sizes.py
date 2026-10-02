from pathlib import Path
from PIL import Image
import csv


# ============================================================
# PATHS
# ============================================================

# This script is located at:
# repo/analysis/analyze_image_sizes.py
ANALYSIS_DIR = Path(__file__).resolve().parent

# Results folder:
# repo/analysis/results/
RESULTS_DIR = (
    ANALYSIS_DIR
    / "results"
)

RESULTS_DIR.mkdir(
    parents=True,
    exist_ok=True
)

# Output:
# repo/analysis/results/image_sizes.csv
OUTPUT_CSV = (
    RESULTS_DIR
    / "image_sizes.csv"
)


# ============================================================
# SETTINGS
# ============================================================

SUPPORTED_IMAGES = {
    ".jpg",
    ".jpeg",
    ".png",
    ".bmp",
    ".webp",
    ".gif",
    ".tif",
    ".tiff",
}

# Project-defined threshold for identifying
# very-high-resolution raster scans.
VERY_HIGH_RESOLUTION_MP = 150


# The BVG scans are trusted local files.
# Pillow normally protects against extremely large images.
# We disable that limit here because these are known local scans.
Image.MAX_IMAGE_PIXELS = None


# ============================================================
# ASK USER FOR IMAGE FOLDER
# ============================================================

folder_input = input(
    "Enter the path to the folder containing the plan images:\n> "
).strip()


# Remove quotation marks if a Windows path was pasted
# with surrounding quotes.
folder_input = folder_input.strip('"')


IMAGE_FOLDER = Path(
    folder_input
)


# ============================================================
# CHECK IMAGE FOLDER
# ============================================================

if not IMAGE_FOLDER.exists():

    print()
    print("ERROR: Folder does not exist:")
    print(IMAGE_FOLDER)

    raise SystemExit


if not IMAGE_FOLDER.is_dir():

    print()
    print("ERROR: This is not a folder:")
    print(IMAGE_FOLDER)

    raise SystemExit


# ============================================================
# ANALYZE FILES
# ============================================================

results = []

files = sorted(
    IMAGE_FOLDER.iterdir()
)


for file_path in files:

    if not file_path.is_file():
        continue


    extension = (
        file_path.suffix.lower()
    )


    # --------------------------------------------------------
    # PDF
    #
    # PDFs are recorded separately because a PDF page does
    # not necessarily have one intrinsic raster pixel count
    # like a TIFF/JPEG image.
    # --------------------------------------------------------

    if extension == ".pdf":

        results.append({
            "filename": file_path.name,
            "image_size_mp": "",
            "very_large_image": "not_applicable"
        })

        continue


    # --------------------------------------------------------
    # IGNORE UNSUPPORTED FILE TYPES
    # --------------------------------------------------------

    if extension not in SUPPORTED_IMAGES:
        continue


    # --------------------------------------------------------
    # READ IMAGE RESOLUTION
    # --------------------------------------------------------

    try:

        with Image.open(file_path) as img:

            width, height = img.size


            # Total number of pixels expressed
            # in megapixels.
            megapixels = (
                width * height
            ) / 1_000_000


            # Keep the existing CSV field name
            # "very_large_image" for compatibility
            # with the visualization script.
            #
            # Conceptually this means:
            #
            # yes -> very-high-resolution scan (>=150 MP)
            # no  -> normal-resolution scan (<150 MP)
            very_high_resolution = (
                "yes"
                if megapixels >= VERY_HIGH_RESOLUTION_MP
                else "no"
            )


            results.append({
                "filename": file_path.name,
                "image_size_mp": round(
                    megapixels,
                    2
                ),
                "very_large_image": (
                    very_high_resolution
                )
            })


    except Exception as e:

        results.append({
            "filename": file_path.name,
            "image_size_mp": "",
            "very_large_image": (
                f"error: {e}"
            )
        })


# ============================================================
# SAVE RESULTS
# ============================================================

with OUTPUT_CSV.open(
    "w",
    encoding="utf-8-sig",
    newline=""
) as f:

    writer = csv.DictWriter(
        f,
        fieldnames=[
            "filename",
            "image_size_mp",
            "very_large_image"
        ],
        delimiter=";"
    )

    writer.writeheader()
    writer.writerows(
        results
    )


# ============================================================
# SUMMARY
# ============================================================

normal_count = sum(
    1
    for row in results
    if row["very_large_image"] == "no"
)

very_high_count = sum(
    1
    for row in results
    if row["very_large_image"] == "yes"
)

pdf_count = sum(
    1
    for row in results
    if row["very_large_image"] == "not_applicable"
)

error_count = sum(
    1
    for row in results
    if str(
        row["very_large_image"]
    ).startswith("error:")
)


print()
print("========================================")
print("IMAGE RESOLUTION ANALYSIS FINISHED")
print("========================================")

print()
print(f"Files analyzed:                 {len(results)}")
print(f"Normal resolution (<150 MP):    {normal_count}")
print(f"Very high resolution (>=150):   {very_high_count}")
print(f"PDF files:                      {pdf_count}")
print(f"Files with errors:              {error_count}")

print()
print("Results saved to:")
print(OUTPUT_CSV)