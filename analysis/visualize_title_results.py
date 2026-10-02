from pathlib import Path

import pandas as pd
import matplotlib.pyplot as plt


# ============================================================
# PATHS
# ============================================================

# This script is located at:
# repo/analysis/visualize_title_results.py
ANALYSIS_DIR = Path(__file__).resolve().parent

# Repository root:
# repo/
REPO_ROOT = ANALYSIS_DIR.parent

# V4 detailed evaluation results:
# repo/testing/v4/evaluation_results_v4.csv
INPUT_FILE = (
    REPO_ROOT
    / "testing"
    / "v4"
    / "evaluation_results_v4.csv"
)

# All charts are stored centrally in:
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
# COLORS
# ============================================================

BVG_YELLOW = "#F7B500"
BVG_BLACK = "#111111"
BVG_GRAY = "#A7A7A7"


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def parse_bool(value):
    """
    Convert CSV True / False values into Python booleans.
    """

    if isinstance(value, bool):
        return value

    return (
        str(value)
        .strip()
        .lower()
        in {"true", "1", "yes"}
    )


def parse_number(series):
    """
    Convert values to numeric values.

    Also supports decimal commas:
    153,4 -> 153.4
    """

    return pd.to_numeric(
        series
        .astype(str)
        .str.replace(",", ".", regex=False),
        errors="coerce"
    )


def style_chart(ax):
    """
    Apply the same visual style to all charts.
    """

    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    ax.grid(
        axis="y",
        linestyle="--",
        alpha=0.20
    )

    ax.set_axisbelow(True)


def add_count_labels(ax, bars):
    """
    Add integer counts above vertical bars.
    """

    for bar in bars:

        value = bar.get_height()

        ax.text(
            bar.get_x() + bar.get_width() / 2,
            value + 0.3,
            f"{int(value)}",
            ha="center",
            va="bottom",
            fontsize=11,
            fontweight="bold"
        )


def add_accuracy_labels(ax, bars, counts):
    """
    Add accuracy percentage and sample size above each bar.
    """

    for bar, count in zip(
        bars,
        counts
    ):

        value = bar.get_height()

        ax.text(
            bar.get_x() + bar.get_width() / 2,
            value + 2,
            f"{value:.1f}%\n(n={count})",
            ha="center",
            va="bottom",
            fontsize=10,
            fontweight="bold"
        )


def accuracy_by_group(
    dataframe,
    group_column,
    order
):
    """
    Calculate strict title exact-match accuracy for each group.
    """

    rows = []

    for group in order:

        subset = dataframe[
            dataframe[group_column] == group
        ]

        if subset.empty:
            continue

        total = len(subset)

        correct = int(
            subset[
                "title_exact_match_bool"
            ].sum()
        )

        accuracy = (
            correct / total * 100
        )

        rows.append({
            "group": group,
            "total": total,
            "correct": correct,
            "accuracy": accuracy
        })

    return pd.DataFrame(rows)


# ============================================================
# CHECK INPUT
# ============================================================

print()
print("========================================")
print("TITLE RESULTS VISUALIZATION - V4")
print("========================================")

print()
print("Reading title evaluation results from:")
print(INPUT_FILE)

print()
print("Charts will be saved to:")
print(OUTPUT_DIR)


if not INPUT_FILE.exists():

    raise FileNotFoundError(
        "\nCould not find evaluation_results_v4.csv at:\n"
        f"{INPUT_FILE}"
    )


# ============================================================
# LOAD DATA
# ============================================================

df = pd.read_csv(
    INPUT_FILE,
    sep=";",
    encoding="utf-8-sig"
)

print()
print(f"Rows loaded: {len(df)}")


# ============================================================
# CHECK REQUIRED V4 COLUMNS
# ============================================================

required_columns = [
    "filename",
    "title_exact_match",
    "title_character_similarity",
    "title_word_similarity_f1",
    "title_suggested_error_category",
    "scale_percent",
    "actual_title_length",
    "prediction_original_size_mp"
]


missing_columns = [
    column
    for column in required_columns
    if column not in df.columns
]


if missing_columns:

    print()
    print("Columns found in the CSV:")

    for column in df.columns:
        print(f"  - {column}")

    raise ValueError(
        "\nThe V4 CSV is missing required columns:\n"
        + "\n".join(missing_columns)
    )


# ============================================================
# CLEAN VALUES
# ============================================================

df["title_exact_match_bool"] = (
    df[
        "title_exact_match"
    ]
    .apply(
        parse_bool
    )
)


df["character_similarity_numeric"] = (
    parse_number(
        df[
            "title_character_similarity"
        ]
    )
)


df["word_similarity_numeric"] = (
    parse_number(
        df[
            "title_word_similarity_f1"
        ]
    )
)


df["scale_percent_numeric"] = (
    parse_number(
        df[
            "scale_percent"
        ]
    )
)


df["title_length_numeric"] = (
    parse_number(
        df[
            "actual_title_length"
        ]
    )
)


# ============================================================
# PREPARE FILE EXTENSION
# ============================================================

if "file_extension" in df.columns:

    df["file_extension_clean"] = (
        df["file_extension"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.lower()
    )

else:

    df["file_extension_clean"] = ""


def get_extension(row):
    """
    Use V4 file_extension when available.
    Otherwise derive it from filename.
    """

    existing = row[
        "file_extension_clean"
    ]

    if existing:
        return existing

    return Path(
        str(
            row["filename"]
        )
    ).suffix.lower()


df["file_extension_clean"] = (
    df.apply(
        get_extension,
        axis=1
    )
)


# ============================================================
# PREPARE RESOLUTION
# ============================================================

# V4 can contain intrinsic megapixels if original files were
# supplied to the evaluator. Otherwise use the megapixel value
# recorded by the prediction pipeline.

if "image_megapixels" in df.columns:

    df["intrinsic_mp"] = (
        parse_number(
            df[
                "image_megapixels"
            ]
        )
    )

else:

    df["intrinsic_mp"] = float("nan")


df["prediction_mp"] = (
    parse_number(
        df[
            "prediction_original_size_mp"
        ]
    )
)


df["resolution_mp"] = (
    df["intrinsic_mp"]
    .fillna(
        df["prediction_mp"]
    )
)


# ============================================================
# OVERALL TITLE RESULTS
# ============================================================

total = len(df)


correct = int(
    df[
        "title_exact_match_bool"
    ].sum()
)


not_exact = (
    total
    - correct
)


strict_accuracy = (
    correct / total * 100
    if total
    else 0
)


average_character_similarity = (
    df[
        "character_similarity_numeric"
    ].mean()
    * 100
)


average_word_similarity = (
    df[
        "word_similarity_numeric"
    ].mean()
    * 100
)


print()
print("----------------------------------------")
print("OVERALL TITLE RESULTS - V4")
print("----------------------------------------")

print(f"Total plans:                   {total}")
print(f"Exact matches:                 {correct}")
print(f"Non-exact predictions:         {not_exact}")
print(f"Strict exact-match accuracy:   {strict_accuracy:.2f}%")

print()
print(
    "Average character similarity: "
    f"{average_character_similarity:.2f}%"
)

print(
    "Average word similarity:      "
    f"{average_word_similarity:.2f}%"
)


# ============================================================
# CHART 1
#
# STRICT TITLE RESULT
#
# Filename intentionally kept unchanged.
# ============================================================

fig, ax = plt.subplots(
    figsize=(8, 6)
)


labels = [
    "Exact match",
    "Not exact"
]


values = [
    correct,
    not_exact
]


bars = ax.bar(
    labels,
    values,
    color=[
        BVG_YELLOW,
        BVG_GRAY
    ],
    edgecolor=BVG_BLACK,
    linewidth=1.2,
    width=0.60
)


add_count_labels(
    ax,
    bars
)


ax.set_ylabel(
    "Number of plans"
)


fig.suptitle(
    "Strict Title Recognition Result",
    fontsize=15,
    fontweight="bold",
    y=0.97
)


fig.text(
    0.5,
    0.91,
    f"Exact-match accuracy: {strict_accuracy:.1f}%",
    ha="center",
    va="center",
    fontsize=11
)


style_chart(
    ax
)


plt.tight_layout(
    rect=[0, 0, 1, 0.86]
)


plt.savefig(
    OUTPUT_DIR
    / "strict_title_result.png",
    dpi=300,
    bbox_inches="tight"
)


plt.close()


# ============================================================
# CHART 2
#
# TITLE EVALUATION OUTCOMES
#
# Uses V4 title_suggested_error_category.
# Filename intentionally kept unchanged.
# ============================================================

difference_names = {

    "CORRECT":
        "Exact match",

    "MINOR_OCR_OR_FORMATTING_ERROR":
        "Minor text / formatting difference",

    "EXTRA_TEXT":
        "Extra text",

    "PARTIAL_TITLE":
        "Partial title",

    "MAJOR_RECOGNITION_ERROR":
        "Large text difference",

    "NO_TITLE_FOUND":
        "No title predicted",

    "POSSIBLE_WRONG_REGION_OR_SEVERE_ERROR":
        "Very low text similarity",

    "MISSING_PREDICTION":
        "Missing prediction"
}


def get_outcome_label(row):
    """
    Exact matches are shown as their own category.

    Non-exact predictions use the V4 title-error category.
    """

    if row[
        "title_exact_match_bool"
    ]:

        return "Exact match"


    internal_category = row[
        "title_suggested_error_category"
    ]


    return difference_names.get(
        internal_category,
        internal_category
    )


df[
    "outcome_label"
] = (
    df.apply(
        get_outcome_label,
        axis=1
    )
)


outcome_order = [
    "Exact match",
    "Minor text / formatting difference",
    "Extra text",
    "Partial title",
    "Large text difference",
    "Very low text similarity",
    "No title predicted",
    "Missing prediction"
]


outcome_counts = (
    df[
        "outcome_label"
    ]
    .value_counts()
    .reindex(
        outcome_order
    )
    .dropna()
)


outcome_counts = (
    outcome_counts[
        outcome_counts > 0
    ]
)


fig, ax = plt.subplots(
    figsize=(10, 7)
)


colors = [
    BVG_YELLOW
    if category == "Exact match"
    else BVG_GRAY

    for category in outcome_counts.index
]


bars = ax.barh(
    outcome_counts.index,
    outcome_counts.values,
    color=colors,
    edgecolor=BVG_BLACK
)


for bar in bars:

    value = bar.get_width()

    ax.text(
        value + 0.15,
        bar.get_y()
        + bar.get_height() / 2,
        str(
            int(value)
        ),
        va="center",
        fontsize=11,
        fontweight="bold"
    )


if len(
    outcome_counts
) > 0:

    ax.set_xlim(
        0,
        max(
            outcome_counts.values
        )
        * 1.18
    )


ax.set_xlabel(
    "Number of plans"
)


ax.set_title(
    "Title Evaluation Outcomes",
    fontsize=15,
    fontweight="bold",
    pad=22
)


ax.text(
    0.5,
    1.01,
    (
        f"All {total} evaluated titles: "
        f"{correct} exact matches and "
        f"{not_exact} non-exact predictions"
    ),
    transform=ax.transAxes,
    ha="center",
    va="bottom",
    fontsize=10
)


ax.spines[
    "top"
].set_visible(
    False
)

ax.spines[
    "right"
].set_visible(
    False
)


ax.grid(
    axis="x",
    linestyle="--",
    alpha=0.20
)


ax.set_axisbelow(
    True
)


ax.invert_yaxis()


plt.tight_layout()


plt.savefig(
    OUTPUT_DIR
    / "title_evaluation_outcomes.png",
    dpi=300,
    bbox_inches="tight"
)


plt.close()


print()
print("----------------------------------------")
print("TITLE EVALUATION OUTCOMES - V4")
print("----------------------------------------")


for category, count in outcome_counts.items():

    percentage = (
        count / total
        * 100
    )

    print(
        f"{category:<40} "
        f"{int(count):>2} "
        f"({percentage:5.1f}%)"
    )


# ============================================================
# CHART 3
#
# STRICT TITLE ACCURACY BY ORIGINAL RESOLUTION
#
# Filename intentionally kept unchanged.
# ============================================================

def resolution_group(row):

    extension = row[
        "file_extension_clean"
    ]

    mp = row[
        "resolution_mp"
    ]


    if extension == ".pdf":

        return "PDF"


    if pd.isna(
        mp
    ):

        return "Unknown"


    if mp >= 150:

        return (
            "Very high resolution\n"
            "(≥150 MP)"
        )


    return (
        "Normal resolution\n"
        "(<150 MP)"
    )


df[
    "resolution_group"
] = (
    df.apply(
        resolution_group,
        axis=1
    )
)


resolution_order = [
    "Normal resolution\n(<150 MP)",
    "Very high resolution\n(≥150 MP)",
    "PDF",
    "Unknown"
]


resolution_results = (
    accuracy_by_group(
        df,
        "resolution_group",
        resolution_order
    )
)


if not resolution_results.empty:

    fig, ax = plt.subplots(
        figsize=(9, 6)
    )


    colors = []


    for group in (
        resolution_results[
            "group"
        ]
    ):

        if "Normal resolution" in group:

            colors.append(
                BVG_YELLOW
            )

        elif "Very high" in group:

            colors.append(
                BVG_BLACK
            )

        else:

            colors.append(
                BVG_GRAY
            )


    bars = ax.bar(
        resolution_results[
            "group"
        ],
        resolution_results[
            "accuracy"
        ],
        color=colors,
        edgecolor=BVG_BLACK
    )


    add_accuracy_labels(
        ax,
        bars,
        resolution_results[
            "total"
        ]
    )


    ax.set_ylim(
        0,
        110
    )


    ax.set_ylabel(
        "Strict exact-match accuracy (%)"
    )


    ax.set_title(
        "Observed Strict Title Accuracy by Original Resolution",
        fontsize=15,
        fontweight="bold",
        pad=15
    )


    style_chart(
        ax
    )


    plt.tight_layout()


    plt.savefig(
        OUTPUT_DIR
        / "title_accuracy_by_resolution.png",
        dpi=300,
        bbox_inches="tight"
    )


    plt.close()


# ============================================================
# CHART 4
#
# STRICT TITLE ACCURACY BY IMAGE SCALING
#
# Filename intentionally kept unchanged.
# ============================================================

def scale_group(value):

    if pd.isna(
        value
    ):

        return "Unknown"


    if value < 25:

        return "<25%"


    if value < 40:

        return "25–40%"


    if value < 60:

        return "40–60%"


    return "≥60%"


df[
    "scale_group"
] = (
    df[
        "scale_percent_numeric"
    ]
    .apply(
        scale_group
    )
)


scale_order = [
    "<25%",
    "25–40%",
    "40–60%",
    "≥60%",
    "Unknown"
]


scale_results = (
    accuracy_by_group(
        df,
        "scale_group",
        scale_order
    )
)


if not scale_results.empty:

    fig, ax = plt.subplots(
        figsize=(9, 6)
    )


    bars = ax.bar(
        scale_results[
            "group"
        ],
        scale_results[
            "accuracy"
        ],
        color=BVG_YELLOW,
        edgecolor=BVG_BLACK
    )


    add_accuracy_labels(
        ax,
        bars,
        scale_results[
            "total"
        ]
    )


    ax.set_ylim(
        0,
        110
    )


    ax.set_xlabel(
        "Resize scale (%)"
    )


    ax.set_ylabel(
        "Strict exact-match accuracy (%)"
    )


    ax.set_title(
        "Observed Strict Title Accuracy by Image Scaling",
        fontsize=15,
        fontweight="bold",
        pad=15
    )


    style_chart(
        ax
    )


    plt.tight_layout()


    plt.savefig(
        OUTPUT_DIR
        / "title_accuracy_by_scaling.png",
        dpi=300,
        bbox_inches="tight"
    )


    plt.close()


# ============================================================
# CHART 5
#
# STRICT TITLE ACCURACY BY REFERENCE TITLE LENGTH
#
# Filename intentionally kept unchanged.
# ============================================================

def title_length_group(value):

    if pd.isna(
        value
    ):

        return "Unknown"


    if value <= 30:

        return "≤30"


    if value <= 50:

        return "31–50"


    if value <= 70:

        return "51–70"


    return ">70"


df[
    "title_length_group"
] = (
    df[
        "title_length_numeric"
    ]
    .apply(
        title_length_group
    )
)


title_length_order = [
    "≤30",
    "31–50",
    "51–70",
    ">70",
    "Unknown"
]


title_length_results = (
    accuracy_by_group(
        df,
        "title_length_group",
        title_length_order
    )
)


if not title_length_results.empty:

    fig, ax = plt.subplots(
        figsize=(9, 6)
    )


    bars = ax.bar(
        title_length_results[
            "group"
        ],
        title_length_results[
            "accuracy"
        ],
        color=BVG_YELLOW,
        edgecolor=BVG_BLACK
    )


    add_accuracy_labels(
        ax,
        bars,
        title_length_results[
            "total"
        ]
    )


    ax.set_ylim(
        0,
        110
    )


    ax.set_xlabel(
        "Reference title length (characters)"
    )


    ax.set_ylabel(
        "Strict exact-match accuracy (%)"
    )


    ax.set_title(
        "Observed Strict Title Accuracy by Title Length",
        fontsize=15,
        fontweight="bold",
        pad=15
    )


    style_chart(
        ax
    )


    plt.tight_layout()


    plt.savefig(
        OUTPUT_DIR
        / "title_accuracy_by_title_length.png",
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
print("Title charts created:")


created_charts = [
    OUTPUT_DIR
    / "strict_title_result.png",

    OUTPUT_DIR
    / "title_evaluation_outcomes.png",

    OUTPUT_DIR
    / "title_accuracy_by_resolution.png",

    OUTPUT_DIR
    / "title_accuracy_by_scaling.png",

    OUTPUT_DIR
    / "title_accuracy_by_title_length.png"
]


for path in created_charts:

    if path.exists():

        print(
            f"  - {path.name}"
        )


print()
print("Output directory:")
print(OUTPUT_DIR)
