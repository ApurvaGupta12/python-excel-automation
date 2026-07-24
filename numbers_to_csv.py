#!/usr/bin/env python3
"""
numbers_to_csv.py

Converts all Apple Numbers (.numbers) files in a folder to .csv files.

Setup (one time):
    pip install numbers-parser

Usage:
    python numbers_to_csv.py                  # convert all .numbers in current folder
    python numbers_to_csv.py /path/to/folder  # convert all .numbers in given folder
    python numbers_to_csv.py -o out_folder     # write CSVs to a specific output folder

Notes:
    - A .numbers file can contain multiple sheets, and each sheet can contain
      multiple tables. This script exports every table it finds.
    - If a file has only one sheet with one table, the output is:
          filename.csv
    - If a file has multiple sheets/tables, the output is:
          filename__SheetName__TableName.csv
"""

import argparse
import csv
import sys
from pathlib import Path

try:
    from numbers_parser import Document
except ImportError:
    sys.exit(
        "Missing dependency 'numbers-parser'.\n"
        "Install it with:\n\n    pip install numbers-parser\n"
    )


def sanitize(name: str) -> str:
    """Make a string safe to use in a filename."""
    keep = "-_.() "
    return "".join(c if c.isalnum() or c in keep else "_" for c in name).strip()


def convert_file(numbers_path: Path, out_dir: Path) -> list[Path]:
    """Convert a single .numbers file to one or more .csv files. Returns list of written paths."""
    doc = Document(str(numbers_path))
    written = []

    # Collect (sheet_name, table) pairs across the whole document
    all_tables = []
    for sheet in doc.sheets:
        for table in sheet.tables:
            all_tables.append((sheet.name, table))

    multiple = len(all_tables) > 1

    for sheet_name, table in all_tables:
        rows = table.rows(values_only=True)

        if multiple:
            out_name = f"{numbers_path.stem}__{sanitize(sheet_name)}__{sanitize(table.name)}.csv"
        else:
            out_name = f"{numbers_path.stem}.csv"

        out_path = out_dir / out_name
        with open(out_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            for row in rows:
                writer.writerow(["" if v is None else v for v in row])

        written.append(out_path)

    return written


def main():
    parser = argparse.ArgumentParser(description="Convert .numbers files in a folder to .csv")
    parser.add_argument(
        "folder", nargs="?", default=".", help="Folder to scan for .numbers files (default: current folder)"
    )
    parser.add_argument(
        "-o", "--output", default=None, help="Output folder for CSVs (default: same as input folder)"
    )
    args = parser.parse_args()

    in_dir = Path(args.folder).expanduser().resolve()
    out_dir = Path(args.output).expanduser().resolve() if args.output else in_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    if not in_dir.is_dir():
        sys.exit(f"Error: '{in_dir}' is not a folder.")

    numbers_files = sorted(in_dir.glob("*.numbers"))

    if not numbers_files:
        print(f"No .numbers files found in {in_dir}")
        return

    print(f"Found {len(numbers_files)} .numbers file(s) in {in_dir}\n")

    total_written = 0
    for nf in numbers_files:
        try:
            written = convert_file(nf, out_dir)
            for w in written:
                print(f"  {nf.name}  ->  {w.name}")
            total_written += len(written)
        except Exception as e:
            print(f"  ERROR converting {nf.name}: {e}")

    print(f"\nDone. Wrote {total_written} CSV file(s) to {out_dir}")


if __name__ == "__main__":
    main()
