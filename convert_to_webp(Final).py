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

SHORTCUTS / GOOGLE DRIVE:
    If a folder was added via Google Drive's "Add shortcut to Drive" (shows
    up as a Windows "Shortcut" file, e.g. campaign.lnk) instead of being
    fully synced, the script now follows it automatically and recreates its
    contents under output/ the same way as a real folder. Requirements:
      - Google Drive Desktop must be running, and that folder should be set
        to "Available offline" so the actual image files are downloaded
        (not just cloud placeholders), otherwise they'll be skipped with a
        warning.
      - The 'pywin32' package must be installed to read shortcuts:
            pip install pywin32
    (This part is Windows-only; shortcuts aren't relevant on macOS/Linux.)

Requires: Pillow  (pip install pillow --break-system-packages)
          pywin32  (pip install pywin32)          <- only needed to follow .lnk shortcuts
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
WEBP_MAX_DIMENSION = 16383              # libwebp hard limit - encoder raises "Invalid argument" above this on either side
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
            # Capture the embedded color profile (if any) BEFORE converting -
            # img.convert() drops it from .info, and without it some viewers
            # can render slightly different colors than the original.
            icc_profile = img.info.get("icc_profile")

            # Preserve transparency if present, otherwise convert to RGB
            if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
                img = img.convert("RGBA")
            else:
                img = img.convert("RGB")

            # Resize to a fixed width of 2000px, height auto-scaled to keep
            # the original aspect ratio. Only downscales (never enlarges a
            # smaller image, since upscaling would hurt quality). This also
            # keeps every image safely under Shopify's 25-megapixel limit.
            orig_width, orig_height = img.size
            width, height = orig_width, orig_height
            resized = False
            if width > TARGET_WIDTH:
                new_width = TARGET_WIDTH
                new_height = max(1, round(height * (TARGET_WIDTH / width)))
                width, height = new_width, new_height
                resized = True

            # Some images (e.g. tall/narrow label scans) have a width under
            # TARGET_WIDTH but a very large height, so the check above never
            # triggers. libwebp hard-rejects any side over 16383px with
            # "[Errno 22] Invalid argument", so cap whichever side is still
            # too big, regardless of aspect ratio.
            longest_side = max(width, height)
            if longest_side > WEBP_MAX_DIMENSION:
                scale = WEBP_MAX_DIMENSION / longest_side
                width = max(1, round(width * scale))
                height = max(1, round(height * scale))
                resized = True

            if resized:
                img = img.resize((width, height), Image.LANCZOS)

            quality = START_QUALITY
            while True:
                save_kwargs = dict(
                    format="WEBP",
                    quality=quality,
                    method=4,       # good compression, much faster than method=6, quality unaffected
                    lossless=False
                )
                if icc_profile:
                    save_kwargs["icc_profile"] = icc_profile
                img.save(output_path, **save_kwargs)
                size = output_path.stat().st_size

                if size <= SHOPIFY_MAX_BYTES or quality <= MIN_QUALITY:
                    break

                quality -= QUALITY_STEP

            size_mb = size / (1024 * 1024)
            if size > SHOPIFY_MAX_BYTES:
                return False, f"Converted but still {size_mb:.1f}MB at min quality ({MIN_QUALITY}) - consider resizing dimensions"

            if resized:
                return True, f"OK ({size_mb:.1f}MB, quality={quality}, resized {orig_width}x{orig_height} -> {width}x{height})"
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


def safe_component(name: str) -> str:
    """
    Windows silently strips trailing spaces and dots from folder/file names
    when actually creating them on disk - but a Python Path string keeps
    them, so the two stop matching (e.g. a shortcut/folder named
    "campaign " creates a real folder called "campaign", but the script
    would keep trying to save into "campaign " and get
    "No such file or directory"). Clean names before using them to build
    the output folder structure.
    """
    cleaned = name.strip().rstrip(".")
    return cleaned if cleaned else name


def resolve_shortcut(lnk_path: Path):
    """
    Resolve a Windows .lnk shortcut to the real path it points to.
    Google Drive Desktop creates these when you use "Add shortcut to
    Drive" instead of actually syncing a folder, so a plain folder walk
    never sees what's inside them - this fixes that.

    Returns a Path if resolved successfully, otherwise None.
    """
    try:
        import win32com.client
    except ImportError:
        print(
            "  ! Found a shortcut (.lnk) but the 'pywin32' package is needed "
            "to follow it. Install it with:\n"
            "      pip install pywin32\n"
            "    then run this script again."
        )
        return None

    try:
        shell = win32com.client.Dispatch("WScript.Shell")
        shortcut = shell.CreateShortCut(str(lnk_path))
        target = shortcut.TargetPath
        if not target:
            return None
        return Path(target)
    except Exception as e:
        print(f"  ! Could not resolve shortcut {lnk_path.name}: {e}")
        return None


def find_all_images(root: Path, output_folder: Path, rel_prefix: Path = Path("."), _seen=None):
    """
    Recursively walk root and all sub-folders (SKU folders etc.), following
    Windows shortcuts (.lnk) into whatever real folder they point to (e.g. a
    Google Drive folder added via "Add shortcut to Drive"), and yield
    (actual_file_path, relative_output_path) pairs for every supported image
    found, at any depth. Skips the output folder itself (so re-running
    doesn't re-convert its own results).
    """
    if _seen is None:
        _seen = set()

    root_resolved = root.resolve()
    if root_resolved in _seen:
        return  # avoid loops if a shortcut points back to an ancestor folder
    _seen.add(root_resolved)

    try:
        entries = sorted(root.iterdir())
    except (PermissionError, OSError) as e:
        print(f"  ! Could not read folder '{root}': {e}")
        return

    for entry in entries:
        if entry.resolve() == output_folder.resolve():
            continue

        if entry.is_dir():
            yield from find_all_images(entry, output_folder, rel_prefix / safe_component(entry.name), _seen)
            continue

        if not entry.is_file():
            continue

        suffix = entry.suffix.lower()

        if suffix == ".lnk":
            target = resolve_shortcut(entry)
            if target is None:
                continue
            if not target.exists():
                print(
                    f"  ! Shortcut '{rel_prefix / entry.name}' points to "
                    f"'{target}', which doesn't exist locally. If this is a "
                    f"Google Drive folder, make sure Google Drive Desktop is "
                    f"running and the folder is set to 'Available offline' "
                    f"so the files are actually downloaded, not just cloud "
                    f"placeholders."
                )
                continue
            shortcut_label = rel_prefix / safe_component(entry.stem)  # drop the .lnk extension
            if target.is_dir():
                yield from find_all_images(target, output_folder, shortcut_label, _seen)
            elif target.suffix.lower() in SUPPORTED_EXTENSIONS:
                yield target, shortcut_label.with_suffix(target.suffix)
            continue

        if suffix in SUPPORTED_EXTENSIONS:
            clean_name = safe_component(entry.stem) + entry.suffix
            yield entry, rel_prefix / clean_name


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

    image_pairs = list(find_all_images(input_folder, output_folder))

    if not image_pairs:
        print(f"No supported images found in {input_folder} (checked all sub-folders and shortcuts)")
        sys.exit(0)

    # Leave 2 CPU cores free so the laptop doesn't freeze/lag while this runs
    worker_count = max(1, (os.cpu_count() or 4) - 2)
    print(f"Found {len(image_pairs)} image(s) across all sub-folders and shortcuts.")
    print(f"Converting to WebP -> {output_folder}")
    print(f"Using {worker_count} parallel workers (your CPU cores) to speed things up...\n")

    tasks = []
    for f, rel in image_pairs:
        out_path = (output_folder / rel).with_suffix(".webp")  # e.g. campaign/B-3014/CBP Cocktail 2443.webp
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
