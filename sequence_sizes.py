#!/usr/bin/env python3
"""
sequence_sizes.py
==================
Re-sequences the SIZE VALUES of a Shopify-style product CSV WITHOUT moving,
reordering, or sorting any rows.

For each product, this script:
    1. Finds which option (Option1 / Option2 / Option3) is named "Size"
       (case-insensitive).
    2. Collects that product's current Size values, in the same order the
       rows already appear in the file.
    3. Works out the desired Size sequence - either a custom sequence you
       type in, or an automatically detected ascending order.
    4. Writes the resequenced Size values back into the SAME row positions.

Rows themselves are NEVER moved, reordered, deleted, or duplicated - only
the text inside the "Size" option's value cells changes. Every other
column (Product, Handle, SKU, Barcode, Price, Compare-at price, Inventory,
Color, Material, Style, Images, Description, any other option, etc.) is
left byte-for-byte untouched.

No `df.sort_values(...)` (or any other row-level sort/reorder) is used
anywhere in this script - only a column of values is recomputed and
assigned back with `df.loc[row, size_value_col] = new_value`.

Usage
-----
    python sequence_sizes.py

Two ways to choose Custom Mode vs. Automatic Mode:

1. Interactively - just run the script. It will ask:
       Do you want to use a custom size order? (Y/N):
   and, if yes:
       Enter custom size order separated by commas:
   (e.g. "XXL,XL,L,M,S,XS" or "36,34,32,30,28")

2. In code - set USE_CUSTOM_SIZE_ORDER / CUSTOM_SIZE_ORDER in the
   CONFIGURATION section below and set INTERACTIVE_PROMPT = False to skip
   the prompts entirely (handy for automated / non-interactive runs).
"""

import re
import pandas as pd
from collections import OrderedDict

# =============================================================================
# CONFIGURATION
# =============================================================================

# Path to the uploaded / source CSV file.
INPUT_FILE = "Estrella_ALL_Products_-_Estrella_ALL_Products.csv"

# Path for the new CSV that will be written (the original is never overwritten).
OUTPUT_FILE = "products_size_sequenced.csv"

# -----------------------------------------------------------------------------
# CUSTOM SIZE ORDER
# -----------------------------------------------------------------------------
# If INTERACTIVE_PROMPT is True (default), the script asks you at runtime
# whether to use a custom order and, if so, to type it in - the values
# below are only used as the DEFAULTS offered by / used instead of those
# prompts.
#
# If INTERACTIVE_PROMPT is False, the script uses these two variables
# directly with no prompts at all - set them here for scripted/automated
# runs.

# Set INTERACTIVE_PROMPT = False to skip the Y/N and comma-list prompts
# and use USE_CUSTOM_SIZE_ORDER / CUSTOM_SIZE_ORDER below as-is.
INTERACTIVE_PROMPT = True

# Master ON/OFF switch for custom ordering (only used when
# INTERACTIVE_PROMPT is False, or as the pre-fill/default when it's True).
USE_CUSTOM_SIZE_ORDER = False

# A plain comma-separated string, largest -> smallest, e.g.:
#   CUSTOM_SIZE_ORDER = "XXL,XL,L,M,S,XS"
#   CUSTOM_SIZE_ORDER = "36,34,32,30,28"
#   CUSTOM_SIZE_ORDER = "3XL,2XL,XL,L,M,S,XS"
# Leave as "" to have Automatic Mode compute the descending order itself.
CUSTOM_SIZE_ORDER = ""

# -----------------------------------------------------------------------------
# "Custom Size" option value
# -----------------------------------------------------------------------------
# Some catalogues include a made-to-order "Custom Size" value alongside the
# regular sizes (e.g. XXL, XL, L, M, S, XS, Custom Size). If a product's
# variants include this value, it should always land in the LAST position -
# after the smallest/last regular size - regardless of where it happens to
# sit in the file and regardless of Automatic vs. Custom Mode.
#
# This applies automatically; you don't need to type it into
# CUSTOM_SIZE_ORDER or the interactive prompt yourself.
ADD_CUSTOM_SIZE_LAST = True
CUSTOM_SIZE_LABEL = "Custom Size"

# Some products use a SHORTER or differently-worded version of the same
# "Custom Size" concept (e.g. just "custom" instead of "Custom Size").
# Any value that normalizes (uppercase + trimmed) to one of these is
# treated exactly like CUSTOM_SIZE_LABEL above - pulled out and placed
# LAST, and excluded from the ascending-order size detection so it can't
# break the detection for the product's other, real sizes. The original
# text in the CSV is still never rewritten - only its row position moves.
CUSTOM_SIZE_LABEL_ALIASES = ["Custom Size", "Custom"]

# -----------------------------------------------------------------------------
# Add a brand-new "Custom Size" VARIANT ROW per product
# -----------------------------------------------------------------------------
# This is different from ADD_CUSTOM_SIZE_LAST above (which only repositions
# a "Custom Size" value if one already exists in the data). This setting
# actually CREATES one new variant row for every product that has a Size
# option, so the row count of the output file will be larger than the input.
#
# The new row is inserted immediately after that product's existing rows
# (so products/variants for other products are never disturbed), and is
# built by copying the row that ends up holding the LARGEST size after
# resequencing - i.e. its Price, Inventory, SKU, Barcode, Images, and every
# other column are copied from that "largest size" row, and only the Size
# option's value is changed to CUSTOM_SIZE_ROW_LABEL.
ADD_NEW_CUSTOM_SIZE_ROW = False
CUSTOM_SIZE_ROW_LABEL = "Custom Size"

# The new row's SKU and Barcode are copied verbatim from the "largest size"
# row by default (so they will be duplicates of that row's SKU/Barcode -
# this mirrors exactly what was asked for, but duplicate SKUs/barcodes can
# cause problems on import for some platforms). Set this to a non-empty
# string (e.g. "-CUSTOM") to have it appended to the copied SKU/Barcode
# instead, to keep them unique.
CUSTOM_SIZE_SKU_SUFFIX = ""

# -----------------------------------------------------------------------------
# Known apparel-letter size scale, smallest -> largest.
# Used only for AUTOMATIC MODE (i.e. when no custom order is supplied).
# Extend this if your catalogue uses sizes beyond XXXL.
# -----------------------------------------------------------------------------
APPAREL_SCALE_ASCENDING = [
    "XXS", "XS", "S", "M", "L", "XL", "XXL", "XXXL", "4XL", "5XL", "6XL",
]

# Aliases so common alternate spellings map onto the scale above for the
# purpose of DETECTING order (the original text in the CSV is never
# rewritten to a different spelling - only reassigned to a different row).
APPAREL_ALIASES = {
    "2XL": "XXL",
    "3XL": "XXXL",
    "2X": "XXL",
    "3X": "XXXL",
    "X-SMALL": "XS",
    "SMALL": "S",
    "MEDIUM": "M",
    "LARGE": "L",
    "X-LARGE": "XL",
    "XX-LARGE": "XXL",
}


# =============================================================================
# INTERACTIVE INPUT
# =============================================================================

def get_custom_order_interactively(default_use_custom, default_order_string):
    """
    Ask the user (via input()) whether to use a custom size order and, if
    so, collect the comma-separated sequence. Returns (use_custom: bool,
    order_string: str). Falls back to the provided defaults if input isn't
    available (e.g. running in a non-interactive environment).
    """
    try:
        answer = input("Do you want to use a custom size order? (Y/N): ").strip().lower()
    except (EOFError, OSError):
        print("No interactive input available - using configured defaults.")
        return default_use_custom, default_order_string

    if answer.startswith("y"):
        order_string = input("Enter custom size order separated by commas: ").strip()
        return True, order_string

    return False, ""


def parse_custom_order_string(order_string):
    """Convert 'XXL,XL,L,M,S,XS' -> ['XXL','XL','L','M','S','XS']."""
    if not order_string:
        return []
    return [part.strip() for part in order_string.split(",") if part.strip()]


# =============================================================================
# HELPERS
# =============================================================================

def normalize(value):
    """Uppercase + strip a size value for comparison purposes only."""
    return str(value).strip().upper()


def apparel_rank(value):
    """Ascending rank of an apparel-letter size, or None if not recognized."""
    norm = normalize(value)
    norm = APPAREL_ALIASES.get(norm, norm)
    if norm in APPAREL_SCALE_ASCENDING:
        return APPAREL_SCALE_ASCENDING.index(norm)
    return None


_NUMERIC_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*$")
_NUMERIC_SUFFIX_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*([A-Za-z]+)\s*$")


def numeric_rank(value):
    """Float rank for a plain numeric size ('28', '30.5'), or None."""
    m = _NUMERIC_RE.match(str(value))
    if m:
        return float(m.group(1))
    return None


def numeric_suffix_rank(value):
    """(number, suffix) rank for sizes like '28W', '32L', or None."""
    m = _NUMERIC_SUFFIX_RE.match(str(value))
    if m:
        return (float(m.group(1)), m.group(2).upper())
    return None


def detect_sort_key(unique_values):
    """
    Inspect a product's unique size values and decide how to rank them from
    smallest to largest. Returns (key_function, format_label).
    Falls back to alphabetical if nothing else matches.
    """
    if all(apparel_rank(v) is not None for v in unique_values):
        return (lambda v: apparel_rank(v), "apparel-letter scale")

    if all(numeric_rank(v) is not None for v in unique_values):
        return (lambda v: numeric_rank(v), "numeric")

    if all(numeric_suffix_rank(v) is not None for v in unique_values):
        return (lambda v: numeric_suffix_rank(v), "numeric-with-suffix")

    return (lambda v: normalize(v), "alphabetical (fallback)")


def build_rank_map(unique_values_in_appearance_order, use_custom_order, custom_order_list):
    """
    Given a product's unique size values (in first-appearance order), return
    a dict mapping each value -> its rank, where rank 0 = should end up
    FIRST (largest / top of the sequence), matching either the custom order
    (Custom Mode) or the auto-detected descending order (Automatic Mode).

    If ADD_CUSTOM_SIZE_LAST is enabled and this product has a "Custom Size"
    value, it's pulled out first and appended after everything else at the
    very end, then the remaining values are ranked normally.
    """
    custom_size_values = []
    working_values = unique_values_in_appearance_order
    if ADD_CUSTOM_SIZE_LAST:
        custom_size_norms = {normalize(alias) for alias in CUSTOM_SIZE_LABEL_ALIASES}
        custom_size_values = [v for v in unique_values_in_appearance_order
                               if normalize(v) in custom_size_norms]
        working_values = [v for v in unique_values_in_appearance_order
                           if normalize(v) not in custom_size_norms]

    if use_custom_order and custom_order_list:
        custom_norm_order = [normalize(v) for v in custom_order_list]
        in_custom = [v for v in working_values if normalize(v) in custom_norm_order]
        not_in_custom = [v for v in working_values if normalize(v) not in custom_norm_order]
        in_custom.sort(key=lambda v: custom_norm_order.index(normalize(v)))
        # Sizes not covered by the custom list are kept SAFE (never
        # deleted) - placed after every custom-listed size, in their
        # original relative order.
        ordered = in_custom + not_in_custom + custom_size_values
        label = "custom order" + (" + Custom Size last" if custom_size_values else "")
        return {v: i for i, v in enumerate(ordered)}, label

    key_func, fmt_label = detect_sort_key(working_values) if working_values else (None, "n/a")
    if working_values:
        ascending = sorted(working_values, key=key_func)
    else:
        ascending = []
    ordered = ascending + custom_size_values
    label = f"auto-detected ascending ({fmt_label})" + (" + Custom Size last" if custom_size_values else "")
    return {v: i for i, v in enumerate(ordered)}, label


# =============================================================================
# CORE PROCESSING
# =============================================================================

def find_size_option_slot(group_df):
    """
    For one product's rows, find which option slot (1, 2, or 3) is named
    "Size" (case-insensitive). Shopify CSVs typically only populate the
    "OptionN Name" cell on the product's first row, so every row in the
    group is scanned.

    Returns the integer N (1, 2, or 3), or None if there is no Size option.
    """
    for n in (1, 2, 3):
        name_col = f"Option{n} Name"
        if name_col not in group_df.columns:
            continue
        for val in group_df[name_col].astype(str):
            if val.strip().lower() == "size":
                return n
    return None


def resequence_product_sizes(df, group_index_labels, size_value_col,
                              use_custom_order, custom_order_list):
    """
    Recompute the Size VALUES for one product and write them back into the
    SAME row positions - the rows themselves are never touched or moved.

    Returns:
        rows_changed (int): number of Size cells whose text actually changed.
        order_label (str): which strategy was used for this product.
        had_values (bool): whether this product had any Size values at all.
        template_indices (list): ALL row labels that end up holding the
            LARGEST size after resequencing - e.g. if the top size has two
            rows (one per color), both are returned, so a "Custom Size"
            row can later be added for EACH of them, just like the other
            sizes have one row per color. Empty list if had_values is False.
        insert_after_idx: the row label of the LAST sized row for this
            product - new rows should be inserted right after this row
            (and before any trailing non-size rows, e.g. extra image-only
            rows), so no blank row ends up between the sizes and the new
            "Custom Size" row(s). None if had_values is False.
    """
    # Only rows that actually carry a size value participate; blank/extra
    # rows (e.g. image-only rows) are skipped entirely and left untouched.
    rows_with_size = [
        idx for idx in group_index_labels
        if str(df.at[idx, size_value_col]).strip() != ""
    ]
    if not rows_with_size:
        return 0, "no size values present", False, [], None

    original_size_values = [df.at[idx, size_value_col] for idx in rows_with_size]

    unique_in_order = list(OrderedDict.fromkeys(original_size_values))
    rank_map, order_label = build_rank_map(unique_in_order, use_custom_order, custom_order_list)

    # Sort ONLY the collected values (a plain Python list), not the rows.
    # `sorted` is stable, so equal-ranked duplicates (e.g. two "M" rows for
    # different colors) keep their original relative order among themselves.
    sequenced_size_values = sorted(original_size_values, key=lambda v: rank_map[v])

    # Assign the resequenced values back into the existing Size cells, in
    # the same row positions - this is the ONLY write this function does.
    rows_changed = 0
    for idx, new_val in zip(rows_with_size, sequenced_size_values):
        old_val = df.at[idx, size_value_col]
        if old_val != new_val:
            rows_changed += 1
        df.loc[idx, size_value_col] = new_val

    # After the loop above, sequenced_size_values[0] is the LARGEST size
    # (rank 0). Because `sorted` is stable, every row holding that same
    # top value sits contiguously at the START of rows_with_size - collect
    # all of them (covers multi-color/multi-option products).
    top_value = sequenced_size_values[0]
    top_count = sequenced_size_values.count(top_value)
    template_indices = rows_with_size[:top_count]

    insert_after_idx = rows_with_size[-1]

    return rows_changed, order_label, True, template_indices, insert_after_idx


# Columns that Shopify-style exports normally only fill on a product's
# FIRST row and leave blank on every other variant row (product-level
# fields, not per-variant fields). Used only as a FALLBACK when a product
# has just one existing row and there's no other row in that product to
# learn the blank pattern from directly.
PRODUCT_LEVEL_FALLBACK_COLUMNS = {
    "Title", "Body (HTML)", "Vendor", "Product Category", "Type", "Tags",
    "Published", "Gift Card", "SEO Title", "SEO Description", "Status",
}


def is_product_level_column(col):
    return (
        col in PRODUCT_LEVEL_FALLBACK_COLUMNS
        or col.startswith("Google Shopping")
        or "product.metafields" in col
    )


def build_custom_size_row(df, template_idx, size_value_col, group_index_labels):
    """
    Build a new variant row for CUSTOM_SIZE_ROW_LABEL.

    Instead of blindly copying every column from `template_idx` (the row
    holding the product's largest size), this makes the new row's columns
    behave exactly like this product's OTHER size rows behave: whichever
    columns are blank on this product's other (non-first) variant rows -
    Title, Body (HTML), Vendor, Tags, SEO fields, Google Shopping fields,
    product-level metafields, etc. - are left blank here too. Per-variant
    columns (Option values, SKU, Price, Inventory, Barcode, Image, variant
    metafields, etc.) are copied from the template row, same as before.
    """
    new_row = df.loc[template_idx].copy()
    new_row[size_value_col] = CUSTOM_SIZE_ROW_LABEL

    # Learn the blank/filled pattern from an actual continuation row of
    # this SAME product when one exists (most accurate - adapts to
    # whatever this store's CSV structure actually looks like).
    other_rows = [idx for idx in group_index_labels if idx != group_index_labels[0]]
    if other_rows:
        reference_row = df.loc[other_rows[0]]
        for col in df.columns:
            if col == size_value_col:
                continue
            if str(reference_row[col]).strip() == "" and str(new_row[col]).strip() != "":
                new_row[col] = ""
    else:
        # Only one existing row for this product (so it's necessarily the
        # first/only row) - fall back to the known product-level columns.
        for col in df.columns:
            if col == size_value_col:
                continue
            if is_product_level_column(col):
                new_row[col] = ""

    if CUSTOM_SIZE_SKU_SUFFIX:
        for col in ("Variant SKU", "Variant Barcode"):
            if col in new_row.index and str(new_row[col]).strip():
                new_row[col] = str(new_row[col]).strip() + CUSTOM_SIZE_SKU_SUFFIX

    return new_row


def process_csv(input_path=INPUT_FILE, output_path=OUTPUT_FILE,
                 use_custom_order=USE_CUSTOM_SIZE_ORDER,
                 custom_order_list=None):
    if custom_order_list is None:
        custom_order_list = parse_custom_order_string(CUSTOM_SIZE_ORDER)

    # Read everything as plain strings and keep blanks as empty strings
    # (rather than NaN) so every other column round-trips byte-for-byte.
    df = pd.read_csv(input_path, dtype=str, keep_default_na=False)

    if "Handle" not in df.columns:
        raise ValueError("Expected a 'Handle' column identifying each product; not found.")

    # Keep a copy of the original for the post-run validation checks below.
    df_original = df.copy()
    original_row_count = len(df)
    original_col_count = len(df.columns)

    products_processed = 0
    products_with_size = 0
    products_without_size = 0
    total_values_changed = 0
    custom_size_rows_added = 0
    order_strategy_counts = {}

    # Walk through products in the order their rows already appear. We
    # never sort/reorder the file - this loop only groups row LABELS by
    # Handle so we know which rows belong to which product.
    handle_to_rows = OrderedDict()
    for idx, handle in df["Handle"].items():
        handle_to_rows.setdefault(handle, []).append(idx)

    # Per-product bookkeeping needed to (a) validate afterwards and
    # (b) insert the new Custom Size row(s) in the right spot.
    size_value_col_by_handle = {}
    new_rows_by_handle = {}          # handle -> list of new rows to add
    insert_after_idx_by_handle = {}  # handle -> row label to insert new rows after

    for handle, index_labels in handle_to_rows.items():
        products_processed += 1
        group_df = df.loc[index_labels]

        size_slot = find_size_option_slot(group_df)
        if size_slot is None:
            products_without_size += 1
            continue

        value_col = f"Option{size_slot} Value"
        if value_col not in df.columns:
            products_without_size += 1
            continue

        rows_changed, order_label, had_values, template_indices, insert_after_idx = \
            resequence_product_sizes(df, index_labels, value_col, use_custom_order, custom_order_list)
        if not had_values:
            products_without_size += 1
            continue

        products_with_size += 1
        total_values_changed += rows_changed
        order_strategy_counts[order_label] = order_strategy_counts.get(order_label, 0) + 1
        size_value_col_by_handle[handle] = value_col

        if ADD_NEW_CUSTOM_SIZE_ROW:
            # One new row per template - e.g. if the top size has a "blue"
            # row and a "pink" row, Custom Size gets a "blue" row and a
            # "pink" row too, same as every other size does.
            new_rows_by_handle[handle] = [
                build_custom_size_row(df, template_idx, value_col, index_labels)
                for template_idx in template_indices
            ]
            insert_after_idx_by_handle[handle] = insert_after_idx
            custom_size_rows_added += len(template_indices)

    # -----------------------------------------------------------------
    # Rebuild the output row-by-row in original order, inserting each
    # product's new Custom Size row(s) immediately after the LAST SIZED
    # row (not necessarily the last row overall - trailing non-size rows,
    # like extra product-image rows, are left after the new rows so no
    # blank row ever sits between the sizes and the new Custom Size
    # row(s)). Original rows are never reordered relative to each other.
    # -----------------------------------------------------------------
    output_rows = []
    for handle, index_labels in handle_to_rows.items():
        insert_after_idx = insert_after_idx_by_handle.get(handle)
        for idx in index_labels:
            output_rows.append(df.loc[idx])
            if idx == insert_after_idx:
                output_rows.extend(new_rows_by_handle[handle])

    final_df = pd.DataFrame(output_rows, columns=df.columns).reset_index(drop=True)

    # -----------------------------------------------------------------
    # Validation
    # -----------------------------------------------------------------
    expected_row_count = original_row_count + custom_size_rows_added
    assert len(final_df) == expected_row_count, "Unexpected row count - aborting."
    assert len(final_df.columns) == original_col_count, "Column count changed - aborting."

    # Walk both frames in lockstep, skipping the newly-inserted rows, and
    # diff everything except each product's Size Value column.
    orig_pointer = 0
    for handle, index_labels in handle_to_rows.items():
        value_col = size_value_col_by_handle.get(handle)
        insert_after_idx = insert_after_idx_by_handle.get(handle)
        for idx in index_labels:
            orig_row = df_original.loc[idx]
            out_row = final_df.iloc[orig_pointer]
            for col in df.columns:
                if col == value_col:
                    continue
                assert orig_row[col] == out_row[col], (
                    f"Non-Size column '{col}' changed for an original row - aborting."
                )
            orig_pointer += 1
            if idx == insert_after_idx:
                orig_pointer += len(new_rows_by_handle[handle])  # skip inserted rows

    final_df.to_csv(output_path, index=False)

    # ---------------------------------------------------------------
    # Summary
    # ---------------------------------------------------------------
    print()
    print(f"Total rows in input: {original_row_count}")
    print(f"Total rows in output: {len(final_df)}")
    print(f"Products processed: {products_processed}")
    print(f"Products with Size option: {products_with_size}")
    print(f"Products without Size option: {products_without_size}")
    print(f"Size values changed (existing rows): {total_values_changed}")
    print(f"Custom size order: {'Enabled' if use_custom_order and custom_order_list else 'Disabled'}")
    if use_custom_order and custom_order_list:
        print(f"Custom size sequence used: {custom_order_list}")
    if order_strategy_counts:
        print("Breakdown by strategy used:")
        for label, count in sorted(order_strategy_counts.items(), key=lambda kv: -kv[1]):
            print(f"  - {label}: {count} product(s)")
    print(f"New '{CUSTOM_SIZE_ROW_LABEL}' rows added: {custom_size_rows_added}")
    if custom_size_rows_added and not CUSTOM_SIZE_SKU_SUFFIX:
        print("  NOTE: new rows copy SKU/Barcode verbatim from the largest-size row,")
        print("        so those fields will be duplicated. Set CUSTOM_SIZE_SKU_SUFFIX")
        print("        (e.g. '-CUSTOM') if you need them to be unique.")
    print(f"Original row order preserved: True")
    print(f"Only Size Value column(s) modified on existing rows: True")
    print(f"Output: {output_path}")


if __name__ == "__main__":
    import sys

    # Optional command-line usage:
    #     python sequence_sizes.py input.csv [output.csv]
    # If given, these override the INPUT_FILE / OUTPUT_FILE variables in
    # the CONFIGURATION section above. If not given, those variables are
    # used as-is (unchanged behaviour).
    cli_input = sys.argv[1] if len(sys.argv) > 1 else INPUT_FILE
    cli_output = sys.argv[2] if len(sys.argv) > 2 else OUTPUT_FILE

    use_custom = USE_CUSTOM_SIZE_ORDER
    custom_list = parse_custom_order_string(CUSTOM_SIZE_ORDER)

    if INTERACTIVE_PROMPT:
        use_custom, order_string = get_custom_order_interactively(
            USE_CUSTOM_SIZE_ORDER, CUSTOM_SIZE_ORDER
        )
        custom_list = parse_custom_order_string(order_string)

    process_csv(input_path=cli_input, output_path=cli_output,
                use_custom_order=use_custom, custom_order_list=custom_list)
