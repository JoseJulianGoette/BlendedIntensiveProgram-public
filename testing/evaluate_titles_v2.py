#!/usr/bin/env python3
"""
Title-recognition evaluation pipeline v2

Inputs
------
1. Ground-truth CSV:
   filename;actual_title

2. Prediction CSV:
   Must contain at least:
   Filename;Title

   If available, these columns are also used:
   Title_confidence
   Title_probability
   Scale_percent

Outputs
-------
1. evaluation_results_v2.csv
   Per-file evaluation data.

2. evaluation_summary_v2.csv
   Aggregate statistics.

Current analysis
----------------
- Strict exact match
- Character similarity
- Word similarity
- Title length
- Word counts
- Missing / extra words
- Prediction confidence/probability
- Scale percentage
- Suggested error category
- Aggregate comparison of correct vs incorrect cases

No title normalization is used for the strict exact-match metric.
"""

import argparse
import csv
import re
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path


def detect_delimiter(path):
    """Detect ; , or tab delimiter. Defaults to semicolon."""
    with open(path, "r", encoding="utf-8-sig", newline="") as file:
        sample = file.read(4096)

    try:
        return csv.Sniffer().sniff(sample, delimiters=";,\t").delimiter
    except csv.Error:
        return ";"


def read_csv(path):
    """Read CSV file and return rows as dictionaries."""
    delimiter = detect_delimiter(path)

    with open(path, "r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file, delimiter=delimiter)

        if reader.fieldnames is None:
            raise ValueError(f"{path} has no header row.")

        return list(reader)


def normalize_filename(filename):
    """
    Normalize filenames only for matching files across CSVs.
    Titles themselves are NOT normalized for exact-match evaluation.
    """
    if filename is None:
        return ""

    filename = unicodedata.normalize("NFC", filename)
    return filename.strip().casefold()


def parse_decimal(value):
    """
    Convert decimal strings such as '0,5301' or '44,6' to float.
    Returns None for missing or invalid values.
    """
    if value is None:
        return None

    value = str(value).strip()

    if value == "":
        return None

    value = value.replace("%", "").replace(",", ".")

    try:
        return float(value)
    except ValueError:
        return None


def require_columns(rows, required, file_label):
    """Verify required columns exist."""
    if not rows:
        raise ValueError(f"{file_label} contains no data rows.")

    columns = set(rows[0].keys())
    missing = [col for col in required if col not in columns]

    if missing:
        raise ValueError(
            f"{file_label} is missing required column(s): {', '.join(missing)}"
        )


def character_similarity(actual, predicted):
    """
    Similarity from 0.0 to 1.0 using Python's SequenceMatcher.
    1.0 means identical.
    """
    return SequenceMatcher(None, actual, predicted).ratio()


def tokenize(text):
    """
    Lowercase word extraction for word-level comparison.
    Keeps letters, digits and German umlauts/ß.
    """
    if text is None:
        return []

    return re.findall(r"[0-9A-Za-zÄÖÜäöüß]+", text.casefold())


def word_metrics(actual, predicted):
    """
    Compute word-level precision, recall and F1 using word counts.

    Returns:
        word_similarity_f1
        missing_words
        extra_words
    """
    actual_words = tokenize(actual)
    predicted_words = tokenize(predicted)

    actual_counts = {}
    predicted_counts = {}

    for word in actual_words:
        actual_counts[word] = actual_counts.get(word, 0) + 1

    for word in predicted_words:
        predicted_counts[word] = predicted_counts.get(word, 0) + 1

    common = 0

    for word in actual_counts:
        common += min(
            actual_counts[word],
            predicted_counts.get(word, 0)
        )

    actual_total = len(actual_words)
    predicted_total = len(predicted_words)

    if actual_total == 0 and predicted_total == 0:
        precision = recall = f1 = 1.0
    elif actual_total == 0 or predicted_total == 0:
        precision = recall = f1 = 0.0
    else:
        precision = common / predicted_total
        recall = common / actual_total

        if precision + recall == 0:
            f1 = 0.0
        else:
            f1 = 2 * precision * recall / (precision + recall)

    missing_words = []
    for word, count in actual_counts.items():
        missing_count = count - predicted_counts.get(word, 0)
        missing_words.extend([word] * max(0, missing_count))

    extra_words = []
    for word, count in predicted_counts.items():
        extra_count = count - actual_counts.get(word, 0)
        extra_words.extend([word] * max(0, extra_count))

    return f1, missing_words, extra_words


def suggest_error_category(
    actual,
    predicted,
    exact_match,
    char_similarity,
    word_similarity,
    missing_words,
    extra_words,
):
    """
    Heuristic only. This is a suggested category for manual review.

    It does NOT prove the technical cause of the error.
    """
    if exact_match:
        return "CORRECT"

    if predicted.strip() == "":
        return "NO_TITLE_FOUND"

    actual_words = tokenize(actual)
    predicted_words = tokenize(predicted)

    # Very high character similarity usually means small OCR/transcription changes.
    if char_similarity >= 0.92:
        return "MINOR_OCR_OR_FORMATTING_ERROR"

    # Prediction contains most ground-truth words but appears truncated.
    if (
        word_similarity >= 0.65
        and len(predicted_words) < len(actual_words)
        and len(missing_words) > len(extra_words)
    ):
        return "PARTIAL_TITLE"

    # Prediction has significant extra text.
    if (
        word_similarity >= 0.65
        and len(predicted_words) > len(actual_words)
        and len(extra_words) > len(missing_words)
    ):
        return "EXTRA_TEXT"

    # Some substantial overlap remains, but recognition is noticeably wrong.
    if char_similarity >= 0.55 or word_similarity >= 0.50:
        return "MAJOR_RECOGNITION_ERROR"

    # Very little overlap: could be wrong region OR severe recognition failure.
    # Image/crop inspection is needed to distinguish those.
    return "POSSIBLE_WRONG_REGION_OR_SEVERE_ERROR"


def average(values):
    values = [v for v in values if v is not None]

    if not values:
        return None

    return sum(values) / len(values)


def format_number(value, digits=4):
    if value is None:
        return ""
    return f"{value:.{digits}f}"


def evaluate(groundtruth_path, predictions_path, output_path, summary_path):
    groundtruth_rows = read_csv(groundtruth_path)
    prediction_rows = read_csv(predictions_path)

    require_columns(
        groundtruth_rows,
        ["filename", "actual_title"],
        "Ground-truth CSV",
    )

    require_columns(
        prediction_rows,
        ["Filename", "Title"],
        "Prediction CSV",
    )

    prediction_lookup = {}

    for row in prediction_rows:
        key = normalize_filename(row.get("Filename"))

        if not key:
            continue

        if key in prediction_lookup:
            raise ValueError(
                f"Duplicate filename in prediction CSV: {row.get('Filename')}"
            )

        prediction_lookup[key] = row

    results = []
    matched_prediction_keys = set()

    for gt_row in groundtruth_rows:
        filename = gt_row.get("filename", "")
        actual_title = gt_row.get("actual_title", "") or ""
        key = normalize_filename(filename)

        pred_row = prediction_lookup.get(key)

        if pred_row is None:
            predicted_title = ""
            title_confidence = ""
            title_probability = None
            scale_percent = None
            status = "MISSING_PREDICTION"
        else:
            matched_prediction_keys.add(key)

            predicted_title = pred_row.get("Title", "") or ""
            title_confidence = pred_row.get("Title_confidence", "") or ""
            title_probability = parse_decimal(
                pred_row.get("Title_probability")
            )
            scale_percent = parse_decimal(
                pred_row.get("Scale_percent")
            )
            status = ""

        exact_match = (
            pred_row is not None
            and predicted_title == actual_title
        )

        char_sim = character_similarity(
            actual_title,
            predicted_title
        )

        word_sim, missing_words, extra_words = word_metrics(
            actual_title,
            predicted_title
        )

        if pred_row is None:
            error_category = "MISSING_PREDICTION"
        else:
            error_category = suggest_error_category(
                actual_title,
                predicted_title,
                exact_match,
                char_sim,
                word_sim,
                missing_words,
                extra_words,
            )

            status = "CORRECT" if exact_match else "INCORRECT"

        result = {
            "filename": filename,
            "actual_title": actual_title,
            "predicted_title": predicted_title,
            "exact_match": exact_match,
            "status": status,
            "character_similarity": round(char_sim, 4),
            "word_similarity_f1": round(word_sim, 4),
            "actual_title_length": len(actual_title),
            "predicted_title_length": len(predicted_title),
            "actual_word_count": len(tokenize(actual_title)),
            "predicted_word_count": len(tokenize(predicted_title)),
            "missing_words": " | ".join(missing_words),
            "extra_words": " | ".join(extra_words),
            "title_confidence": title_confidence,
            "title_probability": (
                round(title_probability, 4)
                if title_probability is not None
                else ""
            ),
            "scale_percent": (
                round(scale_percent, 2)
                if scale_percent is not None
                else ""
            ),
            "suggested_error_category": error_category,
        }

        results.append(result)

    extra_prediction_keys = (
        set(prediction_lookup) - matched_prediction_keys
    )

    fieldnames = [
        "filename",
        "actual_title",
        "predicted_title",
        "exact_match",
        "status",
        "character_similarity",
        "word_similarity_f1",
        "actual_title_length",
        "predicted_title_length",
        "actual_word_count",
        "predicted_word_count",
        "missing_words",
        "extra_words",
        "title_confidence",
        "title_probability",
        "scale_percent",
        "suggested_error_category",
    ]

    with open(
        output_path,
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames,
            delimiter=";",
        )
        writer.writeheader()
        writer.writerows(results)

    # -------------------------
    # Aggregate statistics
    # -------------------------
    matched_results = [
        row for row in results
        if row["status"] != "MISSING_PREDICTION"
    ]

    correct_rows = [
        row for row in matched_results
        if row["exact_match"] is True
    ]

    incorrect_rows = [
        row for row in matched_results
        if row["exact_match"] is False
    ]

    total = len(results)
    correct = len(correct_rows)
    incorrect = total - correct
    missing_predictions = sum(
        1 for row in results
        if row["status"] == "MISSING_PREDICTION"
    )

    accuracy = (correct / total * 100) if total else 0.0

    avg_char_similarity = average(
        [float(r["character_similarity"]) for r in matched_results]
    )

    avg_word_similarity = average(
        [float(r["word_similarity_f1"]) for r in matched_results]
    )

    avg_probability_correct = average([
        parse_decimal(r["title_probability"])
        for r in correct_rows
    ])

    avg_probability_incorrect = average([
        parse_decimal(r["title_probability"])
        for r in incorrect_rows
    ])

    avg_scale_correct = average([
        parse_decimal(r["scale_percent"])
        for r in correct_rows
    ])

    avg_scale_incorrect = average([
        parse_decimal(r["scale_percent"])
        for r in incorrect_rows
    ])

    avg_title_length_correct = average([
        r["actual_title_length"]
        for r in correct_rows
    ])

    avg_title_length_incorrect = average([
        r["actual_title_length"]
        for r in incorrect_rows
    ])

    error_counts = {}

    for row in results:
        category = row["suggested_error_category"]
        error_counts[category] = error_counts.get(category, 0) + 1

    summary_rows = [
        ["metric", "value"],
        ["ground_truth_files", total],
        ["prediction_rows", len(prediction_rows)],
        ["correct_predictions", correct],
        ["incorrect_predictions", incorrect],
        ["missing_predictions", missing_predictions],
        ["extra_predictions", len(extra_prediction_keys)],
        ["exact_match_accuracy_percent", round(accuracy, 2)],
        ["average_character_similarity", format_number(avg_char_similarity)],
        ["average_word_similarity_f1", format_number(avg_word_similarity)],
        [
            "average_title_probability_correct",
            format_number(avg_probability_correct),
        ],
        [
            "average_title_probability_incorrect",
            format_number(avg_probability_incorrect),
        ],
        [
            "average_scale_percent_correct",
            format_number(avg_scale_correct, 2),
        ],
        [
            "average_scale_percent_incorrect",
            format_number(avg_scale_incorrect, 2),
        ],
        [
            "average_actual_title_length_correct",
            format_number(avg_title_length_correct, 2),
        ],
        [
            "average_actual_title_length_incorrect",
            format_number(avg_title_length_incorrect, 2),
        ],
    ]

    for category in sorted(error_counts):
        summary_rows.append(
            [f"error_category_{category}", error_counts[category]]
        )

    with open(
        summary_path,
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        writer = csv.writer(file, delimiter=";")
        writer.writerows(summary_rows)

    # -------------------------
    # Console output
    # -------------------------
    print()
    print("======================================")
    print("TITLE RECOGNITION EVALUATION - V2")
    print("======================================")
    print(f"Ground-truth files:          {total}")
    print(f"Prediction rows:             {len(prediction_rows)}")
    print(f"Correct predictions:         {correct}")
    print(f"Incorrect predictions:       {incorrect}")
    print(f"Missing predictions:         {missing_predictions}")
    print(f"Extra predictions:           {len(extra_prediction_keys)}")
    print(f"Exact-match accuracy:        {accuracy:.2f}%")
    print(
        "Average char similarity:    "
        f"{format_number(avg_char_similarity)}"
    )
    print(
        "Average word similarity:    "
        f"{format_number(avg_word_similarity)}"
    )

    print()
    print("CORRECT VS INCORRECT")
    print("--------------------------------------")
    print(
        "Avg title probability correct:   "
        f"{format_number(avg_probability_correct)}"
    )
    print(
        "Avg title probability incorrect: "
        f"{format_number(avg_probability_incorrect)}"
    )
    print(
        "Avg scale % correct:              "
        f"{format_number(avg_scale_correct, 2)}"
    )
    print(
        "Avg scale % incorrect:            "
        f"{format_number(avg_scale_incorrect, 2)}"
    )
    print(
        "Avg title length correct:         "
        f"{format_number(avg_title_length_correct, 2)}"
    )
    print(
        "Avg title length incorrect:       "
        f"{format_number(avg_title_length_incorrect, 2)}"
    )

    print()
    print("SUGGESTED ERROR CATEGORIES")
    print("--------------------------------------")
    for category, count in sorted(
        error_counts.items(),
        key=lambda item: (-item[1], item[0]),
    ):
        print(f"{category:38} {count}")

    print()
    print(f"Detailed results: {output_path}")
    print(f"Summary:          {summary_path}")

    if extra_prediction_keys:
        print()
        print("Prediction filenames without ground truth:")
        for key in sorted(extra_prediction_keys):
            print(f"  - {prediction_lookup[key]['Filename']}")


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate predicted technical-drawing titles "
            "against verified ground truth."
        )
    )

    parser.add_argument(
        "groundtruth",
        help="Path to ground-truth CSV",
    )

    parser.add_argument(
        "predictions",
        help="Path to prediction CSV",
    )

    parser.add_argument(
        "-o",
        "--output",
        default="evaluation_results_v2.csv",
        help=(
            "Detailed output CSV "
            "(default: evaluation_results_v2.csv)"
        ),
    )

    parser.add_argument(
        "-s",
        "--summary",
        default="evaluation_summary_v2.csv",
        help=(
            "Summary output CSV "
            "(default: evaluation_summary_v2.csv)"
        ),
    )

    args = parser.parse_args()

    evaluate(
        Path(args.groundtruth),
        Path(args.predictions),
        Path(args.output),
        Path(args.summary),
    )


if __name__ == "__main__":
    main()
