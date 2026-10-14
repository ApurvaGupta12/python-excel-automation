#!/usr/bin/env python3
"""
resize_images.py

Resizes every image inside a folder and all of its subfolders to an
800x1000 canvas (WxH) without stretching or distorting the original image.
The resized image is saved in the same folder as the original, with
"_resized" added to the file name.

- If the image has a transparent background -> output is a PNG on a
  transparent canvas (transparency is preserved).
- If the image has no transparency -> output is a JPG on a white background.
- Original images are never modified or deleted.
- Files already ending in "_resized" are skipped, so re-running is safe.

Usage:
    python resize_images.py <folder>

Example:
    python resize_images.py "C:\\Users\\apurva\\Downloads\\products"
    python resize_images.py .
"""

import sys
from pathlib import Path
from PIL import Image

# ---- Configuration -------------------------------------------------------
TARGET_WIDTH = 800
TARGET_HEIGHT = 1000
BACKGROUND_COLOR = (255, 255, 255)  # white (only used for images without transparency)
SUPPORTED_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".gif"}
JPEG_QUALITY = 95
SUFFIX = "_resized"

# Empty space to leave around the image, as a fraction of the canvas size
# PER SIDE. For example, 0.12 means a 12% margin on each of the four sides.
PADDING_RATIO = 0.12
# ---------------------------------------------------------------------------


def has_transparency(img: Image.Image) -> bool:
    """Return True if the image contains real transparency."""
    if img.mode in ("RGBA", "LA"):
        alpha = img.getchannel("A")
        # If the minimum alpha value is below 255, at least one pixel is transparent
        return alpha.getextrema()[0] < 255
    if img.mode == "P" and "transparency" in img.info:
        return True
    return False


def resize_contain(img: Image.Image, target_w: int, target_h: int,
                   transparent: bool,
                   padding_ratio: float = PADDING_RATIO) -> Image.Image:
    """
    Fit the image inside the canvas while preserving its aspect ratio
    (no stretching), leaving padding on all sides, and center it.
    For transparent images the canvas is transparent too.
    """
    src_w, src_h = img.size

    pad_x = target_w * padding_ratio
    pad_y = target_h * padding_ratio
    avail_w = target_w - 2 * pad_x
    avail_h = target_h - 2 * pad_y

    scale = min(avail_w / src_w, avail_h / src_h)
    new_w = max(1, round(src_w * scale))
    new_h = max(1, round(src_h * scale))

    resized = img.resize((new_w, new_h), Image.LANCZOS)

    offset_x = (target_w - new_w) // 2
    offset_y = (target_h - new_h) // 2

    if transparent:
        canvas = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))
        # Passing the image as its own mask preserves the alpha channel correctly
        canvas.paste(resized, (offset_x, offset_y), resized)
    else:
        canvas = Image.new("RGB", (target_w, target_h), BACKGROUND_COLOR)
        canvas.paste(resized, (offset_x, offset_y))
    return canvas


def process_image(src_path: Path):
    with Image.open(src_path) as img:
        transparent = has_transparency(img)

        if transparent:
            img = img.convert("RGBA")
            out_ext = ".png"
        else:
            img = img.convert("RGB")
            out_ext = ".jpg"

        result = resize_contain(img, TARGET_WIDTH, TARGET_HEIGHT, transparent)

        dst_path = src_path.with_name(src_path.stem + SUFFIX + out_ext)

        if transparent:
            result.save(dst_path, "PNG", optimize=True)
        else:
            result.save(dst_path, "JPEG", quality=JPEG_QUALITY, optimize=True)

    kind = "transparent PNG" if transparent else "white JPG"
    print(f"Saved ({kind}): {dst_path}")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    input_path = Path(sys.argv[1])

    if not input_path.is_dir():
        print(f"Folder not found: {input_path}")
        sys.exit(1)

    # Search subfolders too (rglob) and skip files that were already resized
    files = sorted(
        p for p in input_path.rglob("*")
        if p.is_file()
        and p.suffix.lower() in SUPPORTED_EXTS
        and not p.stem.endswith(SUFFIX)
    )

    if not files:
        print(f"No supported images found in {input_path}")
        sys.exit(1)

    done = 0
    for f in files:
        try:
            process_image(f)
            done += 1
        except Exception as e:
            print(f"FAILED: {f} -> {e}")

    print(f"\nDone! {done}/{len(files)} images resized.")


if __name__ == "__main__":
    main()
