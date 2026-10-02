from pathlib import Path
import csv
import matplotlib.pyplot as plt


# ============================================================
# PATHS
# ============================================================

# This script is located in:
# repo/analysis/plot_image_size_analysis.py
ANALYSIS_DIR = Path(__file__).resolve().parent

# Input:
# repo/analysis/results/image_sizes.csv
INPUT_FILE = (
    ANALYSIS_DIR
    / "results"
    / "image_sizes.csv"
)

# All project charts are stored here:
# repo/analysis/results/charts/
OUTPUT_DIR = (
    ANALYSIS_DIR
    / "results"
    / "charts"
)

OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True
)


# ============================================================
# OUTPUT FILES
# ============================================================

RESOLUTION_DISTRIBUTION_CHART = (
    OUTPUT_DIR
    / "resolution_distribution.png"
)

RESOLUTION_GROUP_CHART = (
    OUTPUT_DIR
    / "resolution_groups.png"
)


# ============================================================
# BVG-INSPIRED COLORS
# ============================================================

BVG_YELLOW = "#F7B500"
BVG_BLACK = "#111111"
BVG_GRAY = "#A7A7A7"


# ============================================================
# CHECK INPUT
# ============================================================

print()
print("========================================")
print("IMAGE RESOLUTION VISUALIZATION")
print("========================================")

print()
print("Reading resolution data from:")
print(INPUT_FILE)

print()
print("Charts will be saved to:")
print(OUTPUT_DIR)


if not INPUT_FILE.exists():
    raise FileNotFoundError(
        "\nCould not find image_sizes.csv at:\n"
        f"{INPUT_FILE}"
    )


# ============================================================
# READ RESOLUTION DATA
# ============================================================

resolution_values_mp = []

normal_resolution_count = 0
very_high_resolution_count = 0
pdf_count = 0


with INPUT_FILE.open(
    "r",
    encoding="utf-8-sig",
    newline=""
) as f:

    reader = csv.DictReader(
        f,
        delimiter=";"
    )

    for row in reader:

        # Existing CSV column:
        #
        # image_size_mp represents the total pixel count
        # expressed in megapixels.
        resolution_value = (
            row["image_size_mp"]
            .strip()
        )

        # Existing classification:
        #
        # yes            -> >=150 MP
        # no             -> <150 MP
        # not_applicable -> PDF
        resolution_group = (
            row["very_large_image"]
            .strip()
            .lower()
        )


        # ----------------------------------------------------
        # PDF
        # ----------------------------------------------------

        if resolution_group == "not_applicable":

            pdf_count += 1
            continue


        # ----------------------------------------------------
        # RESOLUTION IN MEGAPIXELS
        # ----------------------------------------------------

        if resolution_value:

            try:

                resolution_mp = float(
                    resolution_value.replace(",", ".")
                )

                resolution_values_mp.append(
                    resolution_mp
                )

            except ValueError:

                continue


        # ----------------------------------------------------
        # RESOLUTION CATEGORY
        # ----------------------------------------------------

        if resolution_group == "yes":

            very_high_resolution_count += 1

        elif resolution_group == "no":

            normal_resolution_count += 1


# ============================================================
# BASIC CHECK
# ============================================================

total_plans = (
    normal_resolution_count
    + very_high_resolution_count
    + pdf_count
)

print()
print("----------------------------------------")
print("DATASET RESOLUTION SUMMARY")
print("----------------------------------------")

print(f"Total plans:                    {total_plans}")
print(f"Raster images analysed:         {len(resolution_values_mp)}")
print(f"Normal resolution (<150 MP):    {normal_resolution_count}")
print(f"Very high resolution (>=150):   {very_high_resolution_count}")
print(f"PDF files:                      {pdf_count}")


# ============================================================
# CHART 1
#
# DISTRIBUTION OF ORIGINAL IMAGE RESOLUTIONS
#
# This chart includes raster images only.
# PDFs are excluded because they do not have one intrinsic
# raster pixel count in the same way as TIFF images.
# ============================================================

bins = [
    0,
    50,
    100,
    150,
    200,
    250,
    300,
    400
]


plt.figure(
    figsize=(10, 6)
)


counts, bin_edges, patches = plt.hist(
    resolution_values_mp,
    bins=bins,
    color=BVG_YELLOW,
    edgecolor=BVG_BLACK,
    linewidth=1.2
)


# ------------------------------------------------------------
# SHOW 150 MP PROJECT THRESHOLD
# ------------------------------------------------------------

plt.axvline(
    x=150,
    color=BVG_BLACK,
    linestyle="--",
    linewidth=2,
    label="Very-high-resolution threshold (150 MP)"
)


# ------------------------------------------------------------
# SHOW COUNT ABOVE EACH BAR
# ------------------------------------------------------------

for count, patch in zip(
    counts,
    patches
):

    if count > 0:

        x = (
            patch.get_x()
            + patch.get_width() / 2
        )

        y = patch.get_height()

        plt.text(
            x,
            y + 0.2,
            str(int(count)),
            ha="center",
            va="bottom",
            fontweight="bold",
            color=BVG_BLACK
        )


# ------------------------------------------------------------
# LABELS
# ------------------------------------------------------------

plt.xlabel(
    "Total image resolution (megapixels)",
    fontsize=11
)

plt.ylabel(
    "Number of raster plans",
    fontsize=11
)

plt.title(
    "Distribution of Original BVG Plan Resolutions",
    fontsize=15,
    fontweight="bold",
    pad=15
)


# ------------------------------------------------------------
# STYLE
# ------------------------------------------------------------

plt.grid(
    axis="y",
    linestyle="--",
    alpha=0.30
)

plt.gca().spines["top"].set_visible(False)
plt.gca().spines["right"].set_visible(False)

plt.legend(
    frameon=False
)

plt.tight_layout()


# ------------------------------------------------------------
# SAVE CHART
# ------------------------------------------------------------

plt.savefig(
    RESOLUTION_DISTRIBUTION_CHART,
    dpi=300,
    bbox_inches="tight"
)

plt.close()


# ============================================================
# CHART 2
#
# DATASET BY RESOLUTION CATEGORY
#
# All 42 plans are represented:
#
# - raster <150 MP
# - raster >=150 MP
# - PDF
# ============================================================

groups = [
    "Normal resolution\n(<150 MP)",
    "Very high resolution\n(≥150 MP)",
    "PDF"
]

group_counts = [
    normal_resolution_count,
    very_high_resolution_count,
    pdf_count
]

colors = [
    BVG_YELLOW,
    BVG_BLACK,
    BVG_GRAY
]


plt.figure(
    figsize=(9, 6)
)


bars = plt.bar(
    groups,
    group_counts,
    color=colors,
    edgecolor=BVG_BLACK,
    linewidth=1.2,
    width=0.6
)


# ------------------------------------------------------------
# SHOW COUNT ABOVE EACH BAR
# ------------------------------------------------------------

for bar in bars:

    height = bar.get_height()

    plt.text(
        bar.get_x()
        + bar.get_width() / 2,
        height + 0.3,
        str(int(height)),
        ha="center",
        va="bottom",
        fontsize=12,
        fontweight="bold",
        color=BVG_BLACK
    )


# ------------------------------------------------------------
# LABELS
# ------------------------------------------------------------

plt.ylabel(
    "Number of plans",
    fontsize=11
)

plt.title(
    "BVG Plans by Original Resolution Category",
    fontsize=15,
    fontweight="bold",
    pad=15
)


# ------------------------------------------------------------
# STYLE
# ------------------------------------------------------------

plt.grid(
    axis="y",
    linestyle="--",
    alpha=0.25
)

plt.gca().spines["top"].set_visible(False)
plt.gca().spines["right"].set_visible(False)

plt.tight_layout()


# ------------------------------------------------------------
# SAVE CHART
# ------------------------------------------------------------

plt.savefig(
    RESOLUTION_GROUP_CHART,
    dpi=300,
    bbox_inches="tight"
)

plt.close()


# ============================================================
# FINISHED
# ============================================================

print()
print("========================================")
print("FINISHED")
print("========================================")

print()
print("Charts created:")

print(
    f"  - {RESOLUTION_DISTRIBUTION_CHART.name}"
)

print(
    f"  - {RESOLUTION_GROUP_CHART.name}"
)

print()
print("Output directory:")
print(OUTPUT_DIR)