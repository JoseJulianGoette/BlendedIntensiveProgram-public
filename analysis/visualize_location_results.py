from pathlib import Path

import pandas as pd
import matplotlib.pyplot as plt


# ============================================================
# PATHS
# ============================================================

# This script is located at:
# repo/analysis/visualize_location_results.py
ANALYSIS_DIR = Path(__file__).resolve().parent

# Repository root:
# repo/
REPO_ROOT = ANALYSIS_DIR.parent

# Input:
# repo/testing/v4/evaluation_results_v4.csv
INPUT_FILE = (
    REPO_ROOT
    / "testing"
    / "v4"
    / "evaluation_results_v4.csv"
)

# Output:
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
        in {
            "true",
            "1",
            "yes"
        }
    )


def parse_number(series):
    """
    Convert values to numbers.

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
            bar.get_x()
            + bar.get_width() / 2,
            value + 0.3,
            f"{int(value)}",
            ha="center",
            va="bottom",
            fontsize=11,
            fontweight="bold"
        )


def add_accuracy_labels(ax, bars, counts):
    """
    Add percentage and sample size above bars.
    """

    for bar, count in zip(
        bars,
        counts
    ):

        value = bar.get_height()

        ax.text(
            bar.get_x()
            + bar.get_width() / 2,
            value + 2,
            f"{value:.1f}%\n(n={count})",
            ha="center",
            va="bottom",
            fontsize=10,
            fontweight="bold"
        )


def grouped_accuracy(
    dataframe,
    group_column,
    order
):
    """
    Calculate strict location exact-match accuracy
    for each group.
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
                "location_exact_match_bool"
            ].sum()
        )

        accuracy = (
            correct / total * 100
        )

        rows.append({
            "group": group,
            "total": total,
            "accuracy": accuracy
        })

    return pd.DataFrame(rows)


# ============================================================
# CHECK INPUT
# ============================================================

print()
print("========================================")
print("LOCATION RESULTS VISUALIZATION")
print("========================================")

print()
print("Reading location evaluation results from:")
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
# CHECK REQUIRED COLUMNS
# ============================================================

required_columns = [
    "filename",
    "actual_location",
    "location_reference_reliable",
    "location_exact_match",
    "location_practical_match",
    "prediction_original_size_mp",
    "scale_percent"
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
        "\nThe CSV is missing required columns:\n"
        + "\n".join(missing_columns)
    )


# ============================================================
# CLEAN VALUES
# ============================================================

df["location_reference_reliable_bool"] = (
    df[
        "location_reference_reliable"
    ]
    .apply(
        parse_bool
    )
)


df["location_exact_match_bool"] = (
    df[
        "location_exact_match"
    ]
    .apply(
        parse_bool
    )
)


df["location_practical_match_bool"] = (
    df[
        "location_practical_match"
    ]
    .apply(
        parse_bool
    )
)


df["resolution_mp"] = (
    parse_number(
        df[
            "prediction_original_size_mp"
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


df["file_extension_clean"] = (
    df["filename"]
    .astype(str)
    .apply(
        lambda value:
        Path(value).suffix.lower()
    )
)


df["actual_location_length"] = (
    df[
        "actual_location"
    ]
    .fillna("")
    .astype(str)
    .str.len()
)


# ============================================================
# RELIABLE LOCATION REFERENCES ONLY
# ============================================================

reliable = df[
    df[
        "location_reference_reliable_bool"
    ]
].copy()


# ============================================================
# OVERALL LOCATION RESULTS
# ============================================================

total_all = len(df)

total_reliable = len(
    reliable
)

uncertain_count = (
    total_all
    - total_reliable
)


exact = int(
    reliable[
        "location_exact_match_bool"
    ].sum()
)


not_exact = (
    total_reliable
    - exact
)


strict_accuracy = (
    exact / total_reliable * 100
    if total_reliable
    else 0
)


practical = int(
    reliable[
        "location_practical_match_bool"
    ].sum()
)


practical_accuracy = (
    practical / total_reliable * 100
    if total_reliable
    else 0
)


print()
print("----------------------------------------")
print("OVERALL LOCATION RESULTS")
print("----------------------------------------")

print(f"Total plans:                    {total_all}")
print(f"Reliable location references:   {total_reliable}")
print(f"Human-uncertain references:     {uncertain_count}")

print()
print(f"Exact matches:                  {exact}")
print(f"Not exact:                      {not_exact}")
print(f"Strict exact-match accuracy:    {strict_accuracy:.2f}%")

print()
print(f"Practical matches:              {practical}")
print(f"Practical accuracy:             {practical_accuracy:.2f}%")


# ============================================================
# CHART 1
#
# STRICT LOCATION RESULT
# ============================================================

fig, ax = plt.subplots(
    figsize=(8, 6)
)


bars = ax.bar(
    [
        "Exact match",
        "Not exact"
    ],
    [
        exact,
        not_exact
    ],
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
    "Strict Location Recognition Result",
    fontsize=15,
    fontweight="bold",
    y=0.97
)


fig.text(
    0.5,
    0.91,
    (
        f"Reliable human references only "
        f"(n={total_reliable}); "
        f"exact-match accuracy: "
        f"{strict_accuracy:.1f}%"
    ),
    ha="center",
    va="center",
    fontsize=10
)


style_chart(
    ax
)


plt.tight_layout(
    rect=[
        0,
        0,
        1,
        0.86
    ]
)


plt.savefig(
    OUTPUT_DIR
    / "strict_location_result.png",
    dpi=300,
    bbox_inches="tight"
)


plt.close()


# ============================================================
# CHART 2
#
# LOCATION EVALUATION OUTCOMES
#
# Shows:
# - exact
# - practically usable but non-exact
# - not practically usable
# - human reference uncertain
# ============================================================

practical_nonexact = int(
    (
        ~reliable[
            "location_exact_match_bool"
        ]
        &
        reliable[
            "location_practical_match_bool"
        ]
    ).sum()
)


not_practical = int(
    (
        ~reliable[
            "location_practical_match_bool"
        ]
    ).sum()
)


labels = [
    "Exact match",
    "Practically usable\nbut not exact",
    "Not practically usable",
    "Human reference uncertain"
]


counts = [
    exact,
    practical_nonexact,
    not_practical,
    uncertain_count
]


colors = [
    BVG_YELLOW,
    BVG_GRAY,
    BVG_GRAY,
    BVG_GRAY
]


fig, ax = plt.subplots(
    figsize=(10, 7)
)


bars = ax.barh(
    labels,
    counts,
    color=colors,
    edgecolor=BVG_BLACK
)


for bar in bars:

    value = bar.get_width()

    ax.text(
        value + 0.15,
        bar.get_y()
        + bar.get_height() / 2,
        str(int(value)),
        va="center",
        fontsize=11,
        fontweight="bold"
    )


if counts:

    ax.set_xlim(
        0,
        max(counts) * 1.20
    )


ax.set_xlabel(
    "Number of plans"
)


ax.set_title(
    "Location Evaluation Outcomes",
    fontsize=15,
    fontweight="bold",
    pad=22
)


ax.text(
    0.5,
    1.01,
    (
        f"All {total_all} plans: "
        f"{total_reliable} reliable location references "
        f"and {uncertain_count} human-uncertain references"
    ),
    transform=ax.transAxes,
    ha="center",
    va="bottom",
    fontsize=10
)


ax.spines["top"].set_visible(
    False
)

ax.spines["right"].set_visible(
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
    / "location_evaluation_outcomes.png",
    dpi=300,
    bbox_inches="tight"
)


plt.close()


# ============================================================
# CHART 3
#
# LOCATION ACCURACY BY ORIGINAL RESOLUTION
# ============================================================

def resolution_group(row):

    if (
        row[
            "file_extension_clean"
        ]
        == ".pdf"
    ):

        return "PDF"


    value = row[
        "resolution_mp"
    ]


    if pd.isna(
        value
    ):

        return "Unknown"


    if value >= 150:

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
] = df.apply(
    resolution_group,
    axis=1
)


reliable = df[
    df[
        "location_reference_reliable_bool"
    ]
].copy()


resolution_order = [
    "Normal resolution\n(<150 MP)",
    "Very high resolution\n(≥150 MP)",
    "PDF",
    "Unknown"
]


resolution_results = (
    grouped_accuracy(
        reliable,
        "resolution_group",
        resolution_order
    )
)


if not resolution_results.empty:

    fig, ax = plt.subplots(
        figsize=(9, 6)
    )


    colors = [
        BVG_YELLOW
        if "Normal" in group

        else BVG_BLACK
        if "Very high" in group

        else BVG_GRAY

        for group in (
            resolution_results[
                "group"
            ]
        )
    ]


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
        "Observed Strict Location Accuracy by Original Resolution",
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
        / "location_accuracy_by_resolution.png",
        dpi=300,
        bbox_inches="tight"
    )


    plt.close()


# ============================================================
# CHART 4
#
# LOCATION ACCURACY BY IMAGE SCALING
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


reliable = df[
    df[
        "location_reference_reliable_bool"
    ]
].copy()


scale_order = [
    "<25%",
    "25–40%",
    "40–60%",
    "≥60%",
    "Unknown"
]


scale_results = (
    grouped_accuracy(
        reliable,
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
        "Observed Strict Location Accuracy by Image Scaling",
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
        / "location_accuracy_by_scaling.png",
        dpi=300,
        bbox_inches="tight"
    )


    plt.close()


# ============================================================
# CHART 5
#
# LOCATION ACCURACY BY LOCATION LENGTH
# ============================================================

def location_length_group(value):

    if value <= 15:

        return "≤15"


    if value <= 30:

        return "16–30"


    if value <= 45:

        return "31–45"


    return ">45"


df[
    "location_length_group"
] = (
    df[
        "actual_location_length"
    ]
    .apply(
        location_length_group
    )
)


reliable = df[
    df[
        "location_reference_reliable_bool"
    ]
].copy()


length_order = [
    "≤15",
    "16–30",
    "31–45",
    ">45"
]


length_results = (
    grouped_accuracy(
        reliable,
        "location_length_group",
        length_order
    )
)


if not length_results.empty:

    fig, ax = plt.subplots(
        figsize=(9, 6)
    )


    bars = ax.bar(
        length_results[
            "group"
        ],
        length_results[
            "accuracy"
        ],
        color=BVG_YELLOW,
        edgecolor=BVG_BLACK
    )


    add_accuracy_labels(
        ax,
        bars,
        length_results[
            "total"
        ]
    )


    ax.set_ylim(
        0,
        110
    )


    ax.set_xlabel(
        "Reference location length (characters)"
    )


    ax.set_ylabel(
        "Strict exact-match accuracy (%)"
    )


    ax.set_title(
        "Observed Strict Location Accuracy by Location Length",
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
        / "location_accuracy_by_location_length.png",
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
print("Location charts created:")


created_charts = [
    OUTPUT_DIR
    / "strict_location_result.png",

    OUTPUT_DIR
    / "location_evaluation_outcomes.png",

    OUTPUT_DIR
    / "location_accuracy_by_resolution.png",

    OUTPUT_DIR
    / "location_accuracy_by_scaling.png",

    OUTPUT_DIR
    / "location_accuracy_by_location_length.png"
]


for path in created_charts:

    if path.exists():

        print(
            f"  - {path.name}"
        )


print()
print("Output directory:")
print(OUTPUT_DIR)