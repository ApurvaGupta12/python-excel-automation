"""
fill_down_product_values.py

Purpose
-------
For a product export CSV where each product occupies a block of rows
(one row per size: XS, S, M, L, XL, XXL, Custom, ...), this script copies
the value found in the FIRST row of each product block (the "XS" row) down
into every other row of that same block, for a configurable set of columns.

It does NOT touch any other data, does not reorder rows, and writes the
result to a brand-new file so your original CSV is never modified.

How product blocks are detected
--------------------------------
In this type of export, only the first row of each product contains the
product-level information (e.g. the "Handle" / product identifier in
column A); every following size row for that same product leaves that
column blank. This script uses that pattern to detect where one product
ends and the next one begins:

    - A row where BOUNDARY_COLUMN is non-empty  -> start of a NEW product
    - A row where BOUNDARY_COLUMN is empty       -> belongs to the
                                                     product started above

This detection is done from the ORIGINAL file contents before anything is
filled in, so it works correctly even if BOUNDARY_COLUMN is itself one of
the columns you want filled down (e.g. column A).

--------------------------------------------------------------------------
WHERE TO PUT YOUR FILE / HOW TO RUN
--------------------------------------------------------------------------
1. Place your CSV file in the SAME FOLDER as this script (or update the
   INPUT_FILE path below to point at it).
2. No extra packages are needed -- this script only uses Python's
   built-in "csv" module (plus openpyxl, just to convert column letters
   like "A" / "M" / "X" into positions -- it's already installed).
3. Run the script from a terminal:
       python fill_down_product_values.py
4. The result will be saved next to the input file as defined by
   OUTPUT_FILE below (by default: "<input name>_filled.csv"). Your
   original file is left completely untouched.
--------------------------------------------------------------------------
"""

import csv
import os
import sys
from openpyxl.utils import column_index_from_string

# ==========================================================================
# CONFIGURATION - edit the values in this section only
# ==========================================================================

# Path to the input CSV file you were given / that you uploaded.
INPUT_FILE = "Products.csv"

# Path where the new, filled-in copy will be saved.
# Leave as None to auto-generate "<INPUT_FILE>_filled.csv" next to the input.
OUTPUT_FILE = None

# Number of header row(s) at the top of the file to skip (not touched by
# the fill-down logic). Almost always 1.
HEADER_ROWS = 1

# ---- The columns you want filled down (edit this freely) ----------------
# Use plain Excel-style column letters (A, B, C, ... Z, AA, AB, ...) --
# same as you'd see if you opened this CSV in Excel. Add or remove as
# many as you like.
COLUMNS_TO_UPDATE = ["A", "M", "X"]
# ---------------------------------------------------------------------

# The column used to detect where one product ends and the next begins.
# A row is treated as the FIRST size row (e.g. "XS") of a new product
# whenever this column has a value in the ORIGINAL file; every following
# row that is blank in this column is treated as part of that same
# product's remaining size rows (S, M, L, XL, XXL, Custom, ...).
# This is checked BEFORE any filling happens, so it's safe even if this
# same column also appears in COLUMNS_TO_UPDATE.
BOUNDARY_COLUMN = "A"

# ==========================================================================
# MAIN LOGIC - no need to edit anything below this line
# ==========================================================================


def resolve_output_path(input_file, output_file):
    if output_file:
        return output_file
    base, ext = os.path.splitext(input_file)
    return f"{base}_filled{ext or '.csv'}"


def main():
    if not os.path.exists(INPUT_FILE):
        print(f"ERROR: Could not find input file '{INPUT_FILE}'.")
        print("Place your CSV file next to this script, or update the "
              "INPUT_FILE path at the top of the script.")
        sys.exit(1)

    output_path = resolve_output_path(INPUT_FILE, OUTPUT_FILE)

    # Read the whole CSV in as-is (every value stays a plain string, so
    # things like leading zeros in SKUs are never altered or reinterpreted).
    with open(INPUT_FILE, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        rows = list(reader)

    if len(rows) <= HEADER_ROWS:
        print("No data rows found below the header. Nothing to do.")
        with open(output_path, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerows(rows)
        print(f"Saved (unchanged) copy to: {output_path}")
        return

    boundary_idx0 = column_index_from_string(BOUNDARY_COLUMN) - 1  # 0-based
    update_idxs0 = {col: column_index_from_string(col) - 1 for col in COLUMNS_TO_UPDATE}

    first_data_row = HEADER_ROWS  # 0-based index into `rows`
    last_row = len(rows) - 1

    def get_cell(row_list, idx0):
        return row_list[idx0] if idx0 < len(row_list) else ""

    # ---- Step 1: detect product block boundaries from the ORIGINAL data ----
    block_starts = []
    for i in range(first_data_row, last_row + 1):
        cell_value = get_cell(rows[i], boundary_idx0)
        is_start_of_block = cell_value is not None and str(cell_value).strip() != ""
        if is_start_of_block or i == first_data_row:
            block_starts.append(i)

    if not block_starts or block_starts[0] != first_data_row:
        block_starts.insert(0, first_data_row)

    block_ranges = []
    for i, start in enumerate(block_starts):
        end = block_starts[i + 1] - 1 if i + 1 < len(block_starts) else last_row
        block_ranges.append((start, end))

    # ---- Step 2: fill each configured column down within each block ----
    filled_count = 0
    for start, end in block_ranges:
        for col_letter, idx0 in update_idxs0.items():
            source_value = get_cell(rows[start], idx0)
            for i in range(start, end + 1):
                row_list = rows[i]
                # Extend short rows if needed so the target column exists.
                while len(row_list) <= idx0:
                    row_list.append("")
                if row_list[idx0] != source_value:
                    row_list[idx0] = source_value
                    filled_count += 1

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerows(rows)

    print(f"Processed {len(block_ranges)} product block(s).")
    print(f"Updated {filled_count} cell(s) across columns: {', '.join(COLUMNS_TO_UPDATE)}.")
    print(f"Saved result to: {output_path}")
    print("Original file was not modified.")


if __name__ == "__main__":
    main()
