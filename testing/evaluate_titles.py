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

