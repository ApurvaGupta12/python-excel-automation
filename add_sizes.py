"""
add_sizes.py
------------
Automatically adds missing size variants (3XL, 4XL) to a Shopify linesheet
CSV, but only for products that:
  - have an option named "Size" (can be Option1, Option2, or Option3)
  - currently have sizes that form exactly "XS to XXL (2XL)" or
    "S to XXL (2XL)" (no gaps, no unrecognized sizes, and not already
    including 3XL/4XL)

Products that don't fit this pattern (Free Size, Length-only option,
already complete XS-4XL, custom/numeric sizes, gaps, etc.) are left
completely untouched.

Products with multiple variants / multiple options (e.g. Size + Product
Type, or Style + Size) are handled automatically - the new sizes are
duplicated for every existing "other option" combination (Product Type /
Style / etc.), and variant-level fields like price/grams/inventory/SKU
are copied from the matching existing row for that combination.

USAGE:
    python add_sizes.py input.csv output.csv

    (if you don't provide output.csv, it will save as input_with_sizes.csv)
"""

import csv
import sys
import os
from collections import OrderedDict

# ---------------------------------------------------------------------
# CONFIG: the size progression you want (smallest to largest)
# ---------------------------------------------------------------------
SIZE_ORDER = ["XS", "S", "M", "L", "XL", "XXL", "3XL", "4XL"]

# Alias map -> so that slightly different spellings in the sheet
# (2XL vs XXL, etc.) are still recognized correctly.
# Left side = what might appear in the sheet,
# Right side = its canonical name in SIZE_ORDER.
ALIASES = {
    "XS": "XS", "EXTRA SMALL": "XS",
    "S": "S", "SMALL": "S",
    "M": "M", "MEDIUM": "M",
    "L": "L", "LARGE": "L",
    "XL": "XL", "EXTRA LARGE": "XL",
    "XXL": "XXL", "2XL": "XXL", "DOUBLE XL": "XXL",
    "3XL": "3XL", "XXXL": "3XL",
    "4XL": "4XL", "XXXXL": "4XL",
}

# Target: we touch any product whose current sizes form a clean,
# contiguous run starting at XS or S (no gaps, no unrecognized sizes) -
# regardless of where that run currently ends (XXL, 3XL, doesn't matter).
# Whatever standard sizes are missing between there and 4XL get added.
VALID_STARTS = (0, 1)   # 0 = starts at XS, 1 = starts at S

# These fields will always be left BLANK on newly created rows
# (they are product-level / image-level fields, not per-variant)
FIELDS_TO_BLANK_ON_NEW_ROW = [
    "Title", "Body (HTML)", "Vendor", "Product Category", "Type", "Tags", "Published",
    "Option1 Name", "Option1 Linked To",
    "Option2 Name", "Option2 Linked To",
    "Option3 Name", "Option3 Linked To",
    "Image Src", "Image Position", "Image Alt Text", "Gift Card",
    "SEO Title", "SEO Description",
    "Google Shopping / Google Product Category", "Google Shopping / Gender",
    "Google Shopping / Age Group", "Google Shopping / MPN",
    "Google Shopping / Condition", "Google Shopping / Custom Product",
    "Google Shopping / Custom Label 0", "Google Shopping / Custom Label 1",
    "Google Shopping / Custom Label 2", "Google Shopping / Custom Label 3",
    "Google Shopping / Custom Label 4",
    "Collection (product.metafields.custom.collection)",
    "Product category (product.metafields.custom.product_category)",
    "Complementary products (product.metafields.shopify--discovery--product_recommendation.complementary_products)",
    "Related products (product.metafields.shopify--discovery--product_recommendation.related_products)",
    "Related products settings (product.metafields.shopify--discovery--product_recommendation.related_products_display)",
    "Search product boosts (product.metafields.shopify--discovery--product_search_boost.queries)",
    "Status",
    "Included / India",
    "Included / International",
]

# Image-related fields are handled separately: they should always be blank
# on brand-new size rows (no image invented for them), but during the
# header swap (see below) they must NOT move - an image stays exactly on
# whichever row it was originally on.
IMAGE_FIELDS = ["Image Src", "Image Position", "Image Alt Text"]

# Fields that move from the old header row to the new first row when a
# smaller size is inserted ahead of it (everything except images)
HEADER_TRANSFER_FIELDS = [f for f in FIELDS_TO_BLANK_ON_NEW_ROW if f not in IMAGE_FIELDS]


def normalize_size(value):
    """Converts a size value from the sheet into its canonical SIZE_ORDER
    name. Returns None if it can't be recognized."""
    if value is None:
        return None
    v = value.strip().upper()
    if not v:
        return None
    return ALIASES.get(v)


def find_size_option_slot(header_row):
    """Checks the header row to find which option is 'Size':
    'Option1', 'Option2', or 'Option3' - or None if none of them is 'Size'."""
    for slot in ("Option1", "Option2", "Option3"):
        name = (header_row.get(f"{slot} Name") or "").strip().lower()
        if name == "size":
            return slot
    return None


def other_option_slots(size_slot, header_row):
    """Returns the slot names for any other options this product has
    besides Size (e.g. Product Type, Style), whose Name is filled in."""
    slots = []
    for slot in ("Option1", "Option2", "Option3"):
        if slot == size_slot:
            continue
        name = (header_row.get(f"{slot} Name") or "").strip()
        if name:
            slots.append(slot)
    return slots


def process_group(rows, fieldnames, log):
    """Processes all rows for one product (same Handle).
    Returns: the new row list (existing rows, plus any new size rows added)."""
    handle = rows[0].get("Handle", "")
    header_row = rows[0]

    size_slot = find_size_option_slot(header_row)
    if size_slot is None:
        log.append(f"SKIP  [{handle}] - no option named 'Size' was found")
        return rows

    size_value_col = f"{size_slot} Value"
    other_slots = other_option_slots(size_slot, header_row)
    other_value_cols = [f"{s} Value" for s in other_slots]

    # Variant rows = rows that have a value in the size column
    variant_rows = [r for r in rows if (r.get(size_value_col) or "").strip()]
    extra_rows = [r for r in rows if not (r.get(size_value_col) or "").strip()]

    if not variant_rows:
        log.append(f"SKIP  [{handle}] - no value found in the size column")
        return rows

    # Normalize existing sizes
    normalized_existing = set()
    unknown_found = False
    for r in variant_rows:
        norm = normalize_size(r.get(size_value_col))
        if norm is None:
            unknown_found = True
        else:
            normalized_existing.add(norm)

    if unknown_found:
        log.append(f"SKIP  [{handle}] - some size values could not be recognized (e.g. 'Free Size' / custom)")
        return rows

    indices = sorted(SIZE_ORDER.index(s) for s in normalized_existing)

    # Pattern check: contiguous range (no gaps), starting at XS or S.
    # We no longer require the range to end exactly at XXL - a product
    # that already runs S..3XL (missing only 4XL) is still a valid target.
    is_contiguous = indices == list(range(indices[0], indices[-1] + 1))
    starts_ok = indices[0] in VALID_STARTS

    if not (is_contiguous and starts_ok):
        log.append(
            f"SKIP  [{handle}] - current sizes ({', '.join(SIZE_ORDER[i] for i in indices)}) "
            f"don't form a clean XS/S-starting contiguous range"
        )
        return rows

    # ---- Pattern matched -> fill in whichever sizes are missing so the
    # product covers the full XS-to-4XL range (this may include XS itself,
    # not just 3XL/4XL, if the product currently starts at S) ----
    missing_sizes = [s for s in SIZE_ORDER if s not in normalized_existing]

    if not missing_sizes:
        log.append(f"SKIP  [{handle}] - already has the full XS-4XL range")
        return rows

    # Capture the existing images in their original order (before any
    # reordering), so we can re-attach them starting from the top of the
    # product again afterwards
    images_in_order = []
    for r in variant_rows:
        if (r.get("Image Src") or "").strip():
            images_in_order.append({
                "Image Src": r.get("Image Src", ""),
                "Image Position": r.get("Image Position", ""),
                "Image Alt Text": r.get("Image Alt Text", ""),
            })

    # One template row for each unique "other option" combo, and a lookup
    # of which (combo, size) pairs already exist so we know where each
    # existing row belongs in the final, size-ordered output
    combo_template = OrderedDict()   # combo tuple -> template row (dict)
    combo_order = []                 # to preserve insertion order
    variant_lookup = {}              # (combo, size_norm) -> existing row
    for r in variant_rows:
        combo = tuple((r.get(col) or "").strip() for col in other_value_cols)
        if combo not in combo_template:
            combo_template[combo] = r
            combo_order.append(combo)
        size_norm = normalize_size(r.get(size_value_col))
        variant_lookup[(combo, size_norm)] = r

    new_rows = []
    ordered_rows = []
    for size_name in SIZE_ORDER:
        if size_name not in normalized_existing and size_name not in missing_sizes:
            continue
        for combo in combo_order:
            existing_row = variant_lookup.get((combo, size_name))
            if existing_row is not None:
                ordered_rows.append(existing_row)
                continue

            template = combo_template[combo]
            new_row = dict(template)  # variant-level fields (price, grams,
                                       # inventory, SKU, barcode, etc.) get copied

            # Blank out product-level / image-level fields
            for col in FIELDS_TO_BLANK_ON_NEW_ROW:
                if col in new_row:
                    new_row[col] = ""

            new_row["Handle"] = handle
            new_row[size_value_col] = size_name
            for col, val in zip(other_value_cols, combo):
                new_row[col] = val

            new_rows.append(new_row)
            ordered_rows.append(new_row)

    # Shopify only reads product-level info (Title, Vendor, Body, Images,
    # SEO, Status, etc.) from the very FIRST row of each Handle. If a new,
    # smaller size (e.g. XS) got placed ahead of the original header row
    # (e.g. S), that new row is now first - so we move the product-level
    # info onto it, and turn the old header row into a normal blank
    # continuation row (just like the other size rows).
    if ordered_rows and ordered_rows[0] is not header_row:
        new_header = ordered_rows[0]
        for col in HEADER_TRANSFER_FIELDS:
            if col in header_row:
                new_header[col] = header_row[col]
                header_row[col] = ""

    # Re-attach the images starting from the top row of the product again,
    # in their original order - this keeps images starting right from row 1
    # of the product block, regardless of which size now sits there
    for r in ordered_rows:
        for col in IMAGE_FIELDS:
            if col in r:
                r[col] = ""
    for i, img in enumerate(images_in_order):
        if i < len(ordered_rows):
            for col in IMAGE_FIELDS:
                ordered_rows[i][col] = img[col]

    log.append(
        f"ADD   [{handle}] - sizes added: {', '.join(missing_sizes)} "
        f"x {len(combo_order)} combo(s) = {len(new_rows)} new row(s)"
    )

    # Existing variant rows + newly created ones, in proper size order,
    # followed by any trailing image-only rows
    return ordered_rows + extra_rows


def process_csv(input_path, output_path):
    with open(input_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    # Group by Handle, preserving order
    groups = OrderedDict()
    for r in rows:
        groups.setdefault(r.get("Handle", ""), []).append(r)

    log = []
    output_rows = []
    for handle, group_rows in groups.items():
        output_rows.extend(process_group(group_rows, fieldnames, log))

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(output_rows)

    print("\n".join(log))
    print(f"\nDone. {len(rows)} rows -> {len(output_rows)} rows. Saved to: {output_path}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python add_sizes.py input.csv [output.csv]")
        sys.exit(1)

    in_path = sys.argv[1]
    out_path = sys.argv[2] if len(sys.argv) > 2 else (
        os.path.splitext(in_path)[0] + "_with_sizes.csv"
    )
    process_csv(in_path, out_path)
