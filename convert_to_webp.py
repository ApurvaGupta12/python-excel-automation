#!/usr/bin/env python3
"""
convert_to_webp.py
-------------------
Batch-converts images (JPG, PNG, TIFF, BMP, GIF, etc.) to WebP format,
keeping quality as high as possible while making sure the final file
stays under Shopify's 20MB per-image limit.

HOW TO USE (SIMPLE):
    1. Put this script (convert_to_webp.py) inside the SAME folder that
       has your images / SKU sub-folders.
       Example:
           CRESCENT FINAL/
               convert_to_webp.py   <-- script goes here
               B-3014/
                   CBP Cocktail 2443.jpg
                   ...
               K-3038/
                   ...
    2. Just run it, no arguments needed:
           python convert_to_webp.py
    3. It will create a NEW folder called "output" right there, with the
       exact same sub-folder structure (B-3014, K-3038, etc.), containing
       the compressed .webp versions of every image. Your originals are
       never touched or moved.

           CRESCENT FINAL/
               convert_to_webp.py
               B-3014/                (originals, untouched)
               K-3038/                (originals, untouched)
               output/                <-- NEW, created automatically
                   B-3014/
                       CBP Cocktail 2443.webp
                       ...
                   K-3038/
                       ...

    Works whether your images are in a flat folder, or split across many
    SKU sub-folders (any depth) — the same folder structure is recreated
    inside "output".

    Optional: you can still point it at a different folder manually:
        python convert_to_webp.py /path/to/some/folder

HOW IT WORKS:
    1. Recursively scans the folder (and all sub-folders / SKU folders),
       skipping the "output" folder itself and the script file.
    2. Saves each image as WebP starting at quality=95 (near-lossless,
       no visible loss) using Pillow's "method=6" (best compression).
    3. If a file is still above 20MB (rare, only for very large/high-res
       images), it gradually reduces quality in small steps until it
       fits under the limit — quality is only sacrificed if absolutely
       necessary, never as a default.
    4. Preserves image mode (RGB/RGBA) so transparency is not lost.
    5. Reports any failures at the end.

Requires: Pillow  (pip install pillow --break-system-packages)
"""

import os
import sys
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
from PIL import Image, ImageFile

# Allow Pillow to load slightly truncated/large images without crashing
ImageFile.LOAD_TRUNCATED_IMAGES = True
Image.MAX_IMAGE_PIXELS = None  # disable decompression-bomb limit for large product photos

SHOPIFY_MAX_BYTES = 20 * 1024 * 1024  # 20 MB
SHOPIFY_MAX_MEGAPIXELS = 25_000_000     # Shopify also rejects images above 25MP (width x height)
TARGET_WIDTH = 2000                     # force width to 2000px, height auto-scales to keep aspect ratio
SUPPORTED_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".tif", ".tiff",
    ".bmp", ".gif", ".webp", ".heic", ".heif"
}

START_QUALITY = 95     # near-lossless starting point
MIN_QUALITY = 40        # don't go below this even if still too big
QUALITY_STEP = 5


def convert_image(input_path: Path, output_path: Path) -> tuple[bool, str]:
    """
    Convert a single image to WebP under the size limit.
    Returns (success, message).
    """
    try:
        with Image.open(input_path) as img:
            # Preserve transparency if present, otherwise convert to RGB
            if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
                img = img.convert("RGBA")
            else:
                img = img.convert("RGB")

            # Resize to a fixed width of 2000px, height auto-scaled to keep
            # the original aspect ratio. Only downscales (never enlarges a
            # smaller image, since upscaling would hurt quality). This also
            # keeps every image safely under Shopify's 25-megapixel limit.
            width, height = img.size
            resized = False
            if width > TARGET_WIDTH:
                new_width = TARGET_WIDTH
                new_height = max(1, round(height * (TARGET_WIDTH / width)))
                img = img.resize((new_width, new_height), Image.LANCZOS)
                resized = True

            quality = START_QUALITY
            while True:
                img.save(
                    output_path,
                    format="WEBP",
                    quality=quality,
                    method=4,       # good compression, much faster than method=6, quality unaffected
                    lossless=False
                )
                size = output_path.stat().st_size

                if size <= SHOPIFY_MAX_BYTES or quality <= MIN_QUALITY:
                    break

                quality -= QUALITY_STEP

            size_mb = size / (1024 * 1024)
            if size > SHOPIFY_MAX_BYTES:
                return False, f"Converted but still {size_mb:.1f}MB at min quality ({MIN_QUALITY}) - consider resizing dimensions"

            if resized:
                return True, f"OK ({size_mb:.1f}MB, quality={quality}, resized {width}x{height} -> {new_width}x{new_height})"
            return True, f"OK ({size_mb:.1f}MB, quality={quality}, kept original size {width}x{height})"

    except Exception as e:
        return False, f"Failed: {e}"


def _convert_worker(args):
    """
    Wrapper so each (input_path, output_path, rel) tuple can be sent to a
    separate process by ProcessPoolExecutor.
    """
    input_path, output_path, rel = args
    output_path.parent.mkdir(parents=True, exist_ok=True)
    success, message = convert_image(input_path, output_path)
    return str(rel), success, message


OUTPUT_FOLDER_NAME = "output"


def find_all_images(root: Path, output_folder: Path):
    """
    Recursively walk root and all sub-folders (SKU folders etc.)
    and yield every supported image file found, at any depth.
    Skips the output folder itself (so re-running doesn't re-convert
    its own results).
    """
    for dirpath, dirnames, filenames in os.walk(root):
        current = Path(dirpath)
        # Don't descend into the output folder
        dirnames[:] = [d for d in dirnames if (current / d).resolve() != output_folder.resolve()]
        if current.resolve() == output_folder.resolve():
            continue
        for name in sorted(filenames):
            f = current / name
            if f.suffix.lower() in SUPPORTED_EXTENSIONS:
                yield f


def main():
    # Default: use the folder this script lives in, so you can just drop
    # the script next to your images/SKU folders and run it directly.
    if len(sys.argv) > 1:
        input_folder = Path(sys.argv[1]).resolve()
    else:
        input_folder = Path(__file__).resolve().parent

    if not input_folder.is_dir():
        print(f"Error: '{input_folder}' is not a valid folder")
        sys.exit(1)

    output_folder = input_folder / OUTPUT_FOLDER_NAME
    output_folder.mkdir(parents=True, exist_ok=True)

    image_files = list(find_all_images(input_folder, output_folder))

    if not image_files:
        print(f"No supported images found in {input_folder} (checked all sub-folders)")
        sys.exit(0)

    worker_count = os.cpu_count() or 4
    print(f"Found {len(image_files)} image(s) across all sub-folders.")
    print(f"Converting to WebP -> {output_folder}")
    print(f"Using {worker_count} parallel workers (your CPU cores) to speed things up...\n")

    tasks = []
    for f in image_files:
        rel = f.relative_to(input_folder)                    # e.g. B-3014/CBP Cocktail 2443.jpg
        out_path = (output_folder / rel).with_suffix(".webp")
        tasks.append((f, out_path, rel))

    results = []
    done_count = 0
    with ProcessPoolExecutor(max_workers=worker_count) as executor:
        futures = {executor.submit(_convert_worker, t): t for t in tasks}
        for future in as_completed(futures):
            rel, success, message = future.result()
            done_count += 1
            status = "✔" if success else "✘"
            print(f"  [{done_count}/{len(tasks)}] {status} {rel}  [{message}]")
            results.append((rel, success, message))

    ok_count = sum(1 for _, s, _ in results if s)
    print(f"\nDone: {ok_count}/{len(results)} converted successfully.")
    print(f"All compressed images are inside: {output_folder}")
    print("(same sub-folder / SKU structure as your originals, originals untouched)")

    failed = [r for r in results if not r[1]]
    if failed:
        print("\nFiles needing attention:")
        for name, _, message in failed:
            print(f"  - {name}: {message}")


if __name__ == "__main__":
    main()
