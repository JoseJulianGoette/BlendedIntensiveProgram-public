#!/usr/bin/env python3
"""
Title-recognition evaluation pipeline v3

Inputs
------
1. Ground-truth CSV:
   filename;actual_title

2. Prediction CSV:
   Must contain at least:
   Filename;Title

   Optional prediction/process columns used when present:
   Title_confidence
   Title_probability
   Original_size_px
   Original_size_MP
   Crop_size_px
   Sent_size_px
   Scale_factor
   Scale_percent
   Sent_KB
   Preparation_time_s
   First_response_time_s
   Model_time_s
   Total_time_s

3. Optional directory containing the original .tif/.tiff/.pdf files

Outputs
-------
1. evaluation_results_v3.csv
   Per-file evaluation + process metadata + intrinsic file metadata.

2. evaluation_summary_v3.csv
   Overall statistics and grouped analysis.

Dependencies
------------
Standard library only for CSV/text analysis.

Optional metadata extraction:
    pip install pillow pymupdf

Pillow is used for TIFF metadata.
PyMuPDF (import name: fitz) is used for PDF metadata.

Notes
-----
- Exact-match comparison remains strict.
- Filenames are Unicode-normalized only for matching.
- Suggested error categories are heuristics, not proven causes.
- PDF "DPI" is often not a meaningful intrinsic property for vector PDFs.
  For PDFs, page size and embedded-image metadata are reported instead.
"""

import argparse
import csv
import re
import unicodedata
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path


def detect_delimiter(path):
    with open(path, "r", encoding="utf-8-sig", newline="") as file:
        sample = file.read(4096)
    try:
        return csv.Sniffer().sniff(sample, delimiters=";,\t").delimiter
    except csv.Error:
        return ";"


def read_csv(path):
    delimiter = detect_delimiter(path)
    with open(path, "r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file, delimiter=delimiter)
        if reader.fieldnames is None:
            raise ValueError(f"{path} has no header row.")
        return list(reader)


def require_columns(rows, required, file_label):
    if not rows:
        raise ValueError(f"{file_label} contains no data rows.")
    columns = set(rows[0].keys())
    missing = [col for col in required if col not in columns]
    if missing:
        raise ValueError(
            f"{file_label} is missing required column(s): {', '.join(missing)}"
        )


def normalize_filename(filename):
    if filename is None:
        return ""
    filename = unicodedata.normalize("NFC", filename)
    return filename.strip().casefold()


def parse_decimal(value):
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


def average(values):
    values = [v for v in values if v is not None]
    if not values:
        return None
    return sum(values) / len(values)


def format_number(value, digits=4):
    if value is None:
        return ""
    return f"{value:.{digits}f}"


def character_similarity(actual, predicted):
    return SequenceMatcher(None, actual, predicted).ratio()


def tokenize(text):
    if text is None:
        return []
    return re.findall(r"[0-9A-Za-zÄÖÜäöüß]+", text.casefold())


def word_metrics(actual, predicted):
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
        common += min(actual_counts[word], predicted_counts.get(word, 0))

    actual_total = len(actual_words)
    predicted_total = len(predicted_words)

    if actual_total == 0 and predicted_total == 0:
        precision = recall = f1 = 1.0
    elif actual_total == 0 or predicted_total == 0:
        precision = recall = f1 = 0.0
    else:
        precision = common / predicted_total
        recall = common / actual_total
        f1 = 0.0 if precision + recall == 0 else 2 * precision * recall / (precision + recall)

    missing_words = []
    for word, count in actual_counts.items():
        missing_count = count - predicted_counts.get(word, 0)
        missing_words.extend([word] * max(0, missing_count))

    extra_words = []
    for word, count in predicted_counts.items():
        extra_count = count - actual_counts.get(word, 0)
        extra_words.extend([word] * max(0, extra_count))

    return f1, missing_words, extra_words


def title_features(text):
    return {
        "title_characters": len(text),
        "title_words": len(tokenize(text)),
        "title_digits": sum(ch.isdigit() for ch in text),
        "title_punctuation": sum(
            1 for ch in text if not ch.isalnum() and not ch.isspace()
        ),
        "title_has_umlaut_or_sz": any(ch in "äöüÄÖÜß" for ch in text),
    }


def suggest_error_category(
    actual,
    predicted,
    exact_match,
    char_similarity,
    word_similarity,
    missing_words,
    extra_words,
):
    if exact_match:
        return "CORRECT"
    if predicted.strip() == "":
        return "NO_TITLE_FOUND"

    actual_words = tokenize(actual)
    predicted_words = tokenize(predicted)

    if char_similarity >= 0.92:
        return "MINOR_OCR_OR_FORMATTING_ERROR"

    if (
        word_similarity >= 0.65
        and len(predicted_words) < len(actual_words)
        and len(missing_words) > len(extra_words)
    ):
        return "PARTIAL_TITLE"

    if (
        word_similarity >= 0.65
        and len(predicted_words) > len(actual_words)
        and len(extra_words) > len(missing_words)
    ):
        return "EXTRA_TEXT"

    if char_similarity >= 0.55 or word_similarity >= 0.50:
        return "MAJOR_RECOGNITION_ERROR"

    return "POSSIBLE_WRONG_REGION_OR_SEVERE_ERROR"


def blank_file_metadata():
    return {
        "source_file_found": False,
        "file_extension": "",
        "file_size_mb": "",
        "image_width_px": "",
        "image_height_px": "",
        "image_megapixels": "",
        "aspect_ratio": "",
        "dpi_x": "",
        "dpi_y": "",
        "image_mode": "",
        "image_frames": "",
        "pdf_page_count": "",
        "pdf_page_width_pt": "",
        "pdf_page_height_pt": "",
        "pdf_page_width_mm": "",
        "pdf_page_height_mm": "",
        "pdf_embedded_image_count": "",
        "pdf_largest_image_width_px": "",
        "pdf_largest_image_height_px": "",
        "metadata_error": "",
    }


def extract_tiff_metadata(path):
    meta = blank_file_metadata()
    meta["source_file_found"] = True
    meta["file_extension"] = path.suffix.lower()
    meta["file_size_mb"] = round(path.stat().st_size / (1024 * 1024), 4)

    try:
        from PIL import Image
    except ImportError:
        meta["metadata_error"] = "Pillow not installed"
        return meta

    try:
        with Image.open(path) as img:
            width, height = img.size
            meta["image_width_px"] = width
            meta["image_height_px"] = height
            meta["image_megapixels"] = round((width * height) / 1_000_000, 4)
            if height:
                meta["aspect_ratio"] = round(width / height, 4)
            meta["image_mode"] = img.mode
            meta["image_frames"] = getattr(img, "n_frames", 1)

            dpi = img.info.get("dpi")
            if dpi and len(dpi) >= 2:
                meta["dpi_x"] = round(float(dpi[0]), 2)
                meta["dpi_y"] = round(float(dpi[1]), 2)
    except Exception as exc:
        meta["metadata_error"] = f"{type(exc).__name__}: {exc}"

    return meta


def extract_pdf_metadata(path):
    meta = blank_file_metadata()
    meta["source_file_found"] = True
    meta["file_extension"] = path.suffix.lower()
    meta["file_size_mb"] = round(path.stat().st_size / (1024 * 1024), 4)

    try:
        import fitz
    except ImportError:
        meta["metadata_error"] = "PyMuPDF not installed"
        return meta

    try:
        doc = fitz.open(path)
        meta["pdf_page_count"] = doc.page_count

        total_images = 0
        largest_area = 0
        largest_w = ""
        largest_h = ""

        if doc.page_count > 0:
            page = doc[0]
            rect = page.rect
            meta["pdf_page_width_pt"] = round(rect.width, 2)
            meta["pdf_page_height_pt"] = round(rect.height, 2)
            meta["pdf_page_width_mm"] = round(rect.width * 25.4 / 72, 2)
            meta["pdf_page_height_mm"] = round(rect.height * 25.4 / 72, 2)

        for page_index in range(doc.page_count):
            page = doc[page_index]
            images = page.get_images(full=True)
            total_images += len(images)

            for image in images:
                xref = image[0]
                try:
                    info = doc.extract_image(xref)
                    w = info.get("width")
                    h = info.get("height")
                    if w and h:
                        area = w * h
                        if area > largest_area:
                            largest_area = area
                            largest_w = w
                            largest_h = h
                except Exception:
                    pass

        meta["pdf_embedded_image_count"] = total_images
        meta["pdf_largest_image_width_px"] = largest_w
        meta["pdf_largest_image_height_px"] = largest_h
        doc.close()
    except Exception as exc:
        meta["metadata_error"] = f"{type(exc).__name__}: {exc}"

    return meta


def build_file_lookup(files_dir):
    lookup = {}
    if files_dir is None:
        return lookup

    files_dir = Path(files_dir)
    if not files_dir.exists():
        raise ValueError(f"Files directory does not exist: {files_dir}")

    for path in files_dir.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".tif", ".tiff", ".pdf"}:
            continue
        key = normalize_filename(path.name)
        if key not in lookup:
            lookup[key] = path

    return lookup


def get_file_metadata(filename, file_lookup):
    if not file_lookup:
        return blank_file_metadata()

    path = file_lookup.get(normalize_filename(filename))
    if path is None:
        return blank_file_metadata()

    ext = path.suffix.lower()
    if ext in {".tif", ".tiff"}:
        return extract_tiff_metadata(path)
    if ext == ".pdf":
        return extract_pdf_metadata(path)
    return blank_file_metadata()


def title_length_band(length):
    if length <= 30:
        return "<=30"
    if length <= 50:
        return "31-50"
    if length <= 70:
        return "51-70"
    return ">70"


def scale_band(value):
    if value is None:
        return "unknown"
    if value < 25:
        return "<25%"
    if value < 40:
        return "25-40%"
    if value < 60:
        return "40-60%"
    return ">=60%"


def dpi_band(value):
    if value is None:
        return "unknown"
    if value < 150:
        return "<150"
    if value < 300:
        return "150-299"
    if value < 600:
        return "300-599"
    return ">=600"


def megapixel_band(value):
    if value is None:
        return "unknown"
    if value < 10:
        return "<10MP"
    if value < 30:
        return "10-30MP"
    if value < 100:
        return "30-100MP"
    return ">=100MP"


def summarize_groups(results, field_name):
    groups = defaultdict(list)
    for row in results:
        groups[row[field_name]].append(row)

    summary = []
    for group_name, rows in sorted(groups.items(), key=lambda x: str(x[0])):
        count = len(rows)
        exact_count = sum(1 for r in rows if r["exact_match"] is True)
        char_avg = average([
            parse_decimal(r["character_similarity"]) for r in rows
        ])
        word_avg = average([
            parse_decimal(r["word_similarity_f1"]) for r in rows
        ])
        exact_rate = (exact_count / count * 100) if count else 0.0

        summary.append({
            "group": group_name,
            "count": count,
            "exact_rate_percent": round(exact_rate, 2),
            "avg_character_similarity": round(char_avg, 4) if char_avg is not None else "",
            "avg_word_similarity": round(word_avg, 4) if word_avg is not None else "",
        })
    return summary


def evaluate(groundtruth_path, predictions_path, output_path, summary_path, files_dir=None):
    groundtruth_rows = read_csv(groundtruth_path)
    prediction_rows = read_csv(predictions_path)

    require_columns(groundtruth_rows, ["filename", "actual_title"], "Ground-truth CSV")
    require_columns(prediction_rows, ["Filename", "Title"], "Prediction CSV")

    prediction_lookup = {}
    for row in prediction_rows:
        key = normalize_filename(row.get("Filename"))
        if not key:
            continue
        if key in prediction_lookup:
            raise ValueError(f"Duplicate filename in prediction CSV: {row.get('Filename')}")
        prediction_lookup[key] = row

    file_lookup = build_file_lookup(files_dir)
    results = []
    matched_prediction_keys = set()

    for gt_row in groundtruth_rows:
        filename = gt_row.get("filename", "")
        actual_title = gt_row.get("actual_title", "") or ""
        key = normalize_filename(filename)
        pred_row = prediction_lookup.get(key)

        if pred_row is None:
            predicted_title = ""
            status = "MISSING_PREDICTION"
            pred_row = {}
        else:
            matched_prediction_keys.add(key)
            predicted_title = pred_row.get("Title", "") or ""
            status = ""

        exact_match = bool(pred_row) and predicted_title == actual_title
        char_sim = character_similarity(actual_title, predicted_title)
        word_sim, missing_words, extra_words = word_metrics(actual_title, predicted_title)

        if not pred_row:
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

        features = title_features(actual_title)
        file_meta = get_file_metadata(filename, file_lookup)

        title_probability = parse_decimal(pred_row.get("Title_probability"))
        scale_percent = parse_decimal(pred_row.get("Scale_percent"))
        original_mp = parse_decimal(pred_row.get("Original_size_MP"))
        intrinsic_mp = parse_decimal(file_meta.get("image_megapixels"))
        mp_for_band = intrinsic_mp if intrinsic_mp is not None else original_mp
        dpi_x = parse_decimal(file_meta.get("dpi_x"))

        result = {
            "filename": filename,
            "actual_title": actual_title,
            "predicted_title": predicted_title,
            "exact_match": exact_match,
            "status": status,
            "character_similarity": round(char_sim, 4),
            "word_similarity_f1": round(word_sim, 4),
            "actual_title_length": features["title_characters"],
            "predicted_title_length": len(predicted_title),
            "actual_word_count": features["title_words"],
            "predicted_word_count": len(tokenize(predicted_title)),
            "title_digit_count": features["title_digits"],
            "title_punctuation_count": features["title_punctuation"],
            "title_has_umlaut_or_sz": features["title_has_umlaut_or_sz"],
            "missing_words": " | ".join(missing_words),
            "extra_words": " | ".join(extra_words),
            "title_confidence": pred_row.get("Title_confidence", "") or "",
            "title_probability": round(title_probability, 4) if title_probability is not None else "",
            "prediction_original_size_px": pred_row.get("Original_size_px", "") or "",
            "prediction_original_size_mp": pred_row.get("Original_size_MP", "") or "",
            "prediction_crop_size_px": pred_row.get("Crop_size_px", "") or "",
            "prediction_sent_size_px": pred_row.get("Sent_size_px", "") or "",
            "prediction_scale_factor": pred_row.get("Scale_factor", "") or "",
            "scale_percent": round(scale_percent, 2) if scale_percent is not None else "",
            "prediction_sent_kb": pred_row.get("Sent_KB", "") or "",
            "preparation_time_s": pred_row.get("Preparation_time_s", "") or "",
            "first_response_time_s": pred_row.get("First_response_time_s", "") or "",
            "model_time_s": pred_row.get("Model_time_s", "") or "",
            "total_time_s": pred_row.get("Total_time_s", "") or "",
            "suggested_error_category": error_category,
        }
        result.update(file_meta)
        result["title_length_band"] = title_length_band(features["title_characters"])
        result["scale_band"] = scale_band(scale_percent)
        result["dpi_band"] = dpi_band(dpi_x)
        result["megapixel_band"] = megapixel_band(mp_for_band)
        results.append(result)

    extra_prediction_keys = set(prediction_lookup) - matched_prediction_keys

    fieldnames = list(results[0].keys()) if results else []
    with open(output_path, "w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, delimiter=";")
        writer.writeheader()
        writer.writerows(results)

    correct_rows = [r for r in results if r["exact_match"] is True]
    incorrect_rows = [r for r in results if r["status"] == "INCORRECT"]

    total = len(results)
    correct = len(correct_rows)
    incorrect = total - correct
    accuracy = (correct / total * 100) if total else 0.0

    avg_char = average([parse_decimal(r["character_similarity"]) for r in results])
    avg_word = average([parse_decimal(r["word_similarity_f1"]) for r in results])
    avg_prob_correct = average([parse_decimal(r["title_probability"]) for r in correct_rows])
    avg_prob_incorrect = average([parse_decimal(r["title_probability"]) for r in incorrect_rows])
    avg_scale_correct = average([parse_decimal(r["scale_percent"]) for r in correct_rows])
    avg_scale_incorrect = average([parse_decimal(r["scale_percent"]) for r in incorrect_rows])

    error_counts = defaultdict(int)
    for row in results:
        error_counts[row["suggested_error_category"]] += 1

    summary_rows = [
        ["section", "metric", "value", "count", "exact_rate_percent", "avg_character_similarity", "avg_word_similarity"],
        ["overall", "ground_truth_files", total, "", "", "", ""],
        ["overall", "prediction_rows", len(prediction_rows), "", "", "", ""],
        ["overall", "correct_predictions", correct, "", "", "", ""],
        ["overall", "incorrect_predictions", incorrect, "", "", "", ""],
        ["overall", "exact_match_accuracy_percent", round(accuracy, 2), "", "", "", ""],
        ["overall", "average_character_similarity", format_number(avg_char), "", "", "", ""],
        ["overall", "average_word_similarity_f1", format_number(avg_word), "", "", "", ""],
        ["overall", "average_title_probability_correct", format_number(avg_prob_correct), "", "", "", ""],
        ["overall", "average_title_probability_incorrect", format_number(avg_prob_incorrect), "", "", "", ""],
        ["overall", "average_scale_percent_correct", format_number(avg_scale_correct, 2), "", "", "", ""],
        ["overall", "average_scale_percent_incorrect", format_number(avg_scale_incorrect, 2), "", "", "", ""],
    ]

    for category, count in sorted(error_counts.items()):
        summary_rows.append(["error_category", category, count, "", "", "", ""])

    group_fields = [
        ("file_type", "file_extension"),
        ("title_length_band", "title_length_band"),
        ("scale_band", "scale_band"),
        ("dpi_band", "dpi_band"),
        ("megapixel_band", "megapixel_band"),
    ]

    for section_name, field_name in group_fields:
        for row in summarize_groups(results, field_name):
            summary_rows.append([
                section_name,
                row["group"],
                "",
                row["count"],
                row["exact_rate_percent"],
                row["avg_character_similarity"],
                row["avg_word_similarity"],
            ])

    with open(summary_path, "w", encoding="utf-8-sig", newline="") as file:
        writer = csv.writer(file, delimiter=";")
        writer.writerows(summary_rows)

    print()
    print("======================================")
    print("TITLE RECOGNITION EVALUATION - V3")
    print("======================================")
    print(f"Ground-truth files:          {total}")
    print(f"Prediction rows:             {len(prediction_rows)}")
    print(f"Correct predictions:         {correct}")
    print(f"Incorrect predictions:       {incorrect}")
    print(f"Exact-match accuracy:        {accuracy:.2f}%")
    print(f"Average char similarity:     {format_number(avg_char)}")
    print(f"Average word similarity:     {format_number(avg_word)}")

    if files_dir:
        found = sum(1 for r in results if r["source_file_found"] is True)
        print(f"Original files found:        {found}/{total}")
    else:
        print("Original file metadata:      not requested")

    print()
    print("CORRECT VS INCORRECT")
    print("--------------------------------------")
    print("Avg title probability correct:   " + format_number(avg_prob_correct))
    print("Avg title probability incorrect: " + format_number(avg_prob_incorrect))
    print("Avg scale % correct:              " + format_number(avg_scale_correct, 2))
    print("Avg scale % incorrect:            " + format_number(avg_scale_incorrect, 2))

    print()
    print("SUGGESTED ERROR CATEGORIES")
    print("--------------------------------------")
    for category, count in sorted(error_counts.items(), key=lambda item: (-item[1], item[0])):
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
            "Evaluate predicted technical-drawing titles against verified ground truth, "
            "optionally with original-file metadata."
        )
    )
    parser.add_argument("groundtruth", help="Path to ground-truth CSV")
    parser.add_argument("predictions", help="Path to prediction CSV")
    parser.add_argument(
        "files_dir",
        nargs="?",
        default=None,
        help="Optional directory containing original TIF/TIFF/PDF files",
    )
    parser.add_argument("-o", "--output", default="evaluation_results_v3.csv", help="Detailed output CSV")
    parser.add_argument("-s", "--summary", default="evaluation_summary_v3.csv", help="Summary output CSV")

    args = parser.parse_args()
    evaluate(
        Path(args.groundtruth),
        Path(args.predictions),
        Path(args.output),
        Path(args.summary),
        args.files_dir,
    )


if __name__ == "__main__":
    main()
