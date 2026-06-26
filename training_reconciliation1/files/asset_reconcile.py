"""
asset_reconcile.py
-------------------
Training Asset Reconciliation Automation Script.

Reads assets_manifest.csv, cross-checks it against the actual files present
in the assets/ folder, validates every row, groups assets by day/type,
and produces:
    1. deployment_ready_manifest.csv  -> only valid + existing assets
    2. reconciliation_report.txt      -> duplicate/missing/orphan/warning/valid counts

Constraints honoured:
    - Standard library only (csv, re, os, sys, collections, functools)
    - Lambda used in sort/filter
    - Set operations used for filename comparison
    - Recursion used to flatten nested tag groups
    - Custom exceptions for invalid headers / invalid asset codes
"""

import csv
import os
import re
import sys
from collections import defaultdict

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #

MANIFEST_FILE = "assets_manifest.csv"
ASSETS_FOLDER = "assets"
REPORT_FILE = "reconciliation_report.txt"
DEPLOYMENT_FILE = "deployment_ready_manifest.csv"

REQUIRED_HEADERS = ["asset_code", "day_no", "asset_type", "filename", "owner_email", "tags"]
VALID_ASSET_TYPES = {"image", "video", "css", "js", "csv"}

ASSET_CODE_PATTERN = re.compile(r"^A-\d{3}$")
EMAIL_PATTERN = re.compile(r"^[\w.+-]+@[\w-]+\.[\w.-]+$")

MIN_DAY = 1
MAX_DAY = 40
WARNING_DAY_THRESHOLD = 30


# --------------------------------------------------------------------------- #
# Custom Exceptions
# --------------------------------------------------------------------------- #

class InvalidHeaderError(Exception):
    """Raised when the manifest CSV header row does not match the expected schema."""
    pass


class InvalidAssetCodeError(Exception):
    """Raised when a row's asset_code does not match the required 'A-###' pattern."""
    pass


# --------------------------------------------------------------------------- #
# Row record (kept as a simple dict-based structure, no ORM/DB used)
# --------------------------------------------------------------------------- #

def make_record(row, line_no):
    """Build a normalized record from a raw CSV row dict, tagging it with its
    source line number for reporting."""
    record = dict(row)
    record["_line_no"] = line_no
    record["_errors"] = []
    record["_warnings"] = []
    return record


# --------------------------------------------------------------------------- #
# Validation helpers
# --------------------------------------------------------------------------- #

def validate_headers(fieldnames):
    """Ensure the CSV has exactly the headers we expect (order-independent)."""
    if fieldnames is None or set(fieldnames) != set(REQUIRED_HEADERS):
        raise InvalidHeaderError(
            f"Expected headers {REQUIRED_HEADERS}, got {fieldnames}"
        )


def validate_asset_code(code):
    """asset_code must look like 'A-001'. Raises InvalidAssetCodeError otherwise."""
    if not code or not ASSET_CODE_PATTERN.match(code.strip()):
        raise InvalidAssetCodeError(f"Invalid asset_code: '{code}'")
    return code.strip()


def validate_email(email):
    return bool(EMAIL_PATTERN.match((email or "").strip()))


def validate_day_no(day_no_raw):
    """
    Returns (day_no_int, warning_flag).
    Raises ValueError if day_no is not a valid integer or is out of [1, 40].
    Adds a warning (not an error) if day_no > 30.
    """
    try:
        day_no = int(str(day_no_raw).strip())
    except (TypeError, ValueError):
        raise ValueError(f"day_no is not a valid integer: '{day_no_raw}'")

    if day_no < MIN_DAY or day_no > MAX_DAY:
        raise ValueError(f"day_no {day_no} out of allowed range [{MIN_DAY}-{MAX_DAY}]")

    warning = day_no > WARNING_DAY_THRESHOLD
    return day_no, warning


def validate_asset_type(asset_type):
    return (asset_type or "").strip().lower() in VALID_ASSET_TYPES


# --------------------------------------------------------------------------- #
# Recursion: flatten nested tag groups (tags separated by '|')
# --------------------------------------------------------------------------- #

def flatten_tags(tag_string):
    """
    Recursively splits a '|' separated tag string into a flat list of tags.
    e.g. "static|style|theme" -> ["static", "style", "theme"]

    Implemented recursively (rather than str.split) to satisfy the
    "use recursion to flatten nested tag groups" requirement.
    """
    if not tag_string:
        return []

    tag_string = tag_string.strip()
    if "|" not in tag_string:
        return [tag_string] if tag_string else []

    head, _, rest = tag_string.partition("|")
    head = head.strip()
    flattened_rest = flatten_tags(rest)  # recursive call on the remainder
    return ([head] if head else []) + flattened_rest


# --------------------------------------------------------------------------- #
# Step 1: Load + validate manifest
# --------------------------------------------------------------------------- #

def load_manifest(path):
    """
    Reads the manifest CSV, validates headers, and validates each row.
    Returns a list of processed records (each annotated with errors/warnings).
    Malformed rows are NOT skipped silently - they are kept with their
    errors recorded, so the report can account for every input row.
    """
    if not os.path.isfile(path):
        print(f"FATAL: Manifest file not found: {path}")
        sys.exit(1)

    records = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        try:
            validate_headers(reader.fieldnames)
        except InvalidHeaderError as exc:
            print(f"FATAL: {exc}")
            sys.exit(1)

        for line_no, row in enumerate(reader, start=2):  # header is line 1
            record = make_record(row, line_no)

            # asset_code
            try:
                record["asset_code"] = validate_asset_code(row.get("asset_code"))
            except InvalidAssetCodeError as exc:
                record["_errors"].append(str(exc))

            # owner_email
            if not validate_email(row.get("owner_email")):
                record["_errors"].append(f"Invalid owner_email: '{row.get('owner_email')}'")

            # asset_type
            if not validate_asset_type(row.get("asset_type")):
                record["_errors"].append(f"Invalid asset_type: '{row.get('asset_type')}'")

            # day_no (+ beyond-Day-30 warning)
            try:
                day_no, beyond_day_30 = validate_day_no(row.get("day_no"))
                record["day_no"] = day_no
                if beyond_day_30:
                    record["_warnings"].append(
                        f"day_no {day_no} references a topic beyond Day 30"
                    )
            except ValueError as exc:
                record["_errors"].append(str(exc))

            # filename presence
            if not (row.get("filename") or "").strip():
                record["_errors"].append("filename is blank")

            # tags -> flattened via recursion
            record["tag_list"] = flatten_tags(row.get("tags", ""))

            records.append(record)

    return records


# --------------------------------------------------------------------------- #
# Step 2: Duplicate / conflicting filename detection
# --------------------------------------------------------------------------- #

def find_duplicates(records):
    """
    Detects:
      - duplicate asset_code: same asset_code appears in more than one row.
      - conflicting filenames: same asset_code mapped to DIFFERENT filenames.
    Returns (duplicate_codes_set, conflicting_codes_set).
    """
    code_to_filenames = defaultdict(set)
    code_to_count = defaultdict(int)

    for r in records:
        code = r.get("asset_code")
        if not code or r["_errors"]:
            # still count duplicates even for rows with other errors,
            # but skip rows where asset_code itself failed validation
            if code:
                code_to_count[code] += 1
                code_to_filenames[code].add((r.get("filename") or "").strip())
            continue
        code_to_count[code] += 1
        code_to_filenames[code].add((r.get("filename") or "").strip())

    duplicate_codes = {code for code, count in code_to_count.items() if count > 1}
    conflicting_codes = {
        code for code in duplicate_codes if len(code_to_filenames[code]) > 1
    }
    return duplicate_codes, conflicting_codes


# --------------------------------------------------------------------------- #
# Step 3: Compare manifest filenames vs actual folder filenames (SET OPS)
# --------------------------------------------------------------------------- #

def compare_with_folder(records, assets_folder):
    """
    Uses set operations to find:
      - missing_files: listed in manifest but absent from assets/ folder
      - orphan_files:  present in assets/ folder but not listed in manifest
    """
    if not os.path.isdir(assets_folder):
        print(f"FATAL: Assets folder not found: {assets_folder}")
        sys.exit(1)

    manifest_filenames = {
        (r.get("filename") or "").strip() for r in records if (r.get("filename") or "").strip()
    }
    actual_filenames = set(os.listdir(assets_folder))

    missing_files = manifest_filenames - actual_filenames   # set difference
    orphan_files = actual_filenames - manifest_filenames     # set difference
    present_files = manifest_filenames & actual_filenames    # set intersection

    return missing_files, orphan_files, present_files


# --------------------------------------------------------------------------- #
# Step 4: Group assets by day_no and asset_type (nested dict)
# --------------------------------------------------------------------------- #

def group_by_day_and_type(records):
    """
    Builds a nested dictionary: { day_no: { asset_type: [asset_code, ...] } }
    Only rows that have a usable day_no are included.
    """
    grouped = defaultdict(lambda: defaultdict(list))
    for r in records:
        day_no = r.get("day_no")
        asset_type = (r.get("asset_type") or "").strip().lower()
        if isinstance(day_no, int) and asset_type:
            grouped[day_no][asset_type].append(r.get("asset_code") or "<invalid>")

    # Sort using a lambda for deterministic, readable output
    sorted_days = sorted(grouped.keys(), key=lambda d: d)
    return grouped, sorted_days


# --------------------------------------------------------------------------- #
# Step 5: Decide final validity for deployment readiness
# --------------------------------------------------------------------------- #

def is_deployment_ready(record, duplicate_codes, conflicting_codes, missing_files):
    """A record is deployment-ready only if it has no errors, its asset_code
    is not a duplicate/conflicting code, and its file actually exists."""
    if record["_errors"]:
        return False
    if record.get("asset_code") in conflicting_codes:
        return False
    if record.get("asset_code") in duplicate_codes:
        return False
    filename = (record.get("filename") or "").strip()
    if filename in missing_files:
        return False
    return True


# --------------------------------------------------------------------------- #
# Step 6: Write deployment_ready_manifest.csv
# --------------------------------------------------------------------------- #

def write_deployment_manifest(records, duplicate_codes, conflicting_codes, missing_files, path):
    ready_records = [
        r for r in records
        if is_deployment_ready(r, duplicate_codes, conflicting_codes, missing_files)
    ]
    # Filter+sort demonstrated with a lambda, ordered by day_no then asset_code
    ready_records = sorted(ready_records, key=lambda r: (r["day_no"], r["asset_code"]))

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(REQUIRED_HEADERS)
        for r in ready_records:
            writer.writerow([
                r["asset_code"], r["day_no"], r["asset_type"],
                r["filename"], r["owner_email"], r.get("tags", "")
            ])
    return ready_records


# --------------------------------------------------------------------------- #
# Step 7: Write reconciliation_report.txt
# --------------------------------------------------------------------------- #

def write_report(records, duplicate_codes, conflicting_codes, missing_files,
                  orphan_files, grouped, sorted_days, ready_records, path):

    invalid_records = [r for r in records if r["_errors"]]
    warning_records = [r for r in records if r["_warnings"] and not r["_errors"]]
    valid_count = len(ready_records)

    lines = []
    lines.append("=" * 60)
    lines.append("ASSET RECONCILIATION REPORT")
    lines.append("=" * 60)
    lines.append("")

    lines.append("SUMMARY COUNTS")
    lines.append("-" * 60)
    lines.append(f"Total rows processed     : {len(records)}")
    lines.append(f"Valid (deployment-ready) : {valid_count}")
    lines.append(f"Invalid rows             : {len(invalid_records)}")
    lines.append(f"Duplicate asset_codes    : {len(duplicate_codes)}")
    lines.append(f"Conflicting asset_codes  : {len(conflicting_codes)}")
    lines.append(f"Missing files            : {len(missing_files)}")
    lines.append(f"Orphan files             : {len(orphan_files)}")
    lines.append(f"Rows with warnings only  : {len(warning_records)}")
    lines.append("")

    lines.append("DUPLICATE / CONFLICTING ASSET CODES")
    lines.append("-" * 60)
    if duplicate_codes:
        for code in sorted(duplicate_codes):
            tag = "CONFLICTING FILENAMES" if code in conflicting_codes else "duplicate code"
            lines.append(f"  - {code} ({tag})")
    else:
        lines.append("  None found.")
    lines.append("")

    lines.append("MISSING FILES (in manifest, not found in assets/)")
    lines.append("-" * 60)
    if missing_files:
        for fname in sorted(missing_files):
            lines.append(f"  - {fname}")
    else:
        lines.append("  None found.")
    lines.append("")

    lines.append("ORPHAN FILES (in assets/, not referenced in manifest)")
    lines.append("-" * 60)
    if orphan_files:
        for fname in sorted(orphan_files):
            lines.append(f"  - {fname}")
    else:
        lines.append("  None found.")
    lines.append("")

    lines.append("ROW-LEVEL ERRORS")
    lines.append("-" * 60)
    if invalid_records:
        for r in invalid_records:
            lines.append(f"  Line {r['_line_no']} (asset_code='{r.get('asset_code')}'):")
            for err in r["_errors"]:
                lines.append(f"      ERROR: {err}")
    else:
        lines.append("  None found.")
    lines.append("")

    lines.append("ROW-LEVEL WARNINGS (Day > 30)")
    lines.append("-" * 60)
    if warning_records:
        for r in warning_records:
            for w in r["_warnings"]:
                lines.append(f"  Line {r['_line_no']} (asset_code='{r.get('asset_code')}'): {w}")
    else:
        lines.append("  None found.")
    lines.append("")

    lines.append("ASSETS GROUPED BY DAY -> TYPE")
    lines.append("-" * 60)
    for day in sorted_days:
        lines.append(f"  Day {day}:")
        for asset_type in sorted(grouped[day].keys()):
            codes = ", ".join(grouped[day][asset_type])
            lines.append(f"      {asset_type:6s}: {codes}")
    lines.append("")
    lines.append("=" * 60)
    lines.append("END OF REPORT")
    lines.append("=" * 60)

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def main():
    records = load_manifest(MANIFEST_FILE)
    duplicate_codes, conflicting_codes = find_duplicates(records)
    missing_files, orphan_files, present_files = compare_with_folder(records, ASSETS_FOLDER)
    grouped, sorted_days = group_by_day_and_type(records)

    ready_records = write_deployment_manifest(
        records, duplicate_codes, conflicting_codes, missing_files, DEPLOYMENT_FILE
    )
    write_report(
        records, duplicate_codes, conflicting_codes, missing_files,
        orphan_files, grouped, sorted_days, ready_records, REPORT_FILE
    )

    print(f"Processed {len(records)} rows.")
    print(f"Deployment-ready assets : {len(ready_records)}")
    print(f"Duplicates              : {len(duplicate_codes)}")
    print(f"Missing files           : {len(missing_files)}")
    print(f"Orphan files            : {len(orphan_files)}")
    print(f"Reports written: {DEPLOYMENT_FILE}, {REPORT_FILE}")


if __name__ == "__main__":
    main()
