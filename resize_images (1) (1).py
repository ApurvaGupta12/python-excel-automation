#!/usr/bin/env python3
"""
resize_images.py

Resizes images to a fixed canvas of 800x1000 (WxH) WITHOUT stretching/distorting
the original image. The image is scaled proportionally to fit inside the
800x1000 box (contain-fit), then centered on a TRANSPARENT canvas. Any
existing background is NOT flattened -- transparency is preserved, and the
padding around the image is also transparent. Output is saved as PNG
(lossless) so image quality is not degraded.

Usage:
    python3 resize_images.py <input_path_or_folder> [output_folder]

Examples:
    # Single file -> outputs to ./resized/
    python3 resize_images.py product.webp

    # Whole folder -> outputs to ./resized/
    python3 resize_images.py ./raw_images

    # Custom output folder
    python3 resize_images.py ./raw_images ./final_images
"""

import sys
from pathlib import Path
from PIL import Image

# ---- Configuration -------------------------------------------------------
TARGET_WIDTH = 800
TARGET_HEIGHT = 1000
SUPPORTED_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".gif"}
OUTPUT_FORMAT = "PNG"    # PNG supports transparency and is lossless
OUTPUT_EXT = ".png"

# Padding: how much empty space to leave around the image on the canvas.
# Expressed as a fraction of canvas size PER SIDE (e.g. 0.08 = 8% of width
# on left+right combined is NOT how it works -- it's 8% margin on EACH side).
# So PADDING_RATIO = 0.08 means the image is fit within the inner
# (1 - 2*0.08) = 84% of the canvas, centered, leaving an 8% white border
# on all four sides.
PADDING_RATIO = 0.12
# ---------------------------------------------------------------------------


def to_rgba(img: Image.Image) -> Image.Image:
    """Convert the image to RGBA, preserving any existing transparency."""
    return img.convert("RGBA")


def resize_contain(img: Image.Image, target_w: int, target_h: int,
                    padding_ratio: float = PADDING_RATIO) -> Image.Image:
    """
    Resize the image to fit ENTIRELY within (target_w, target_h) while
    preserving its original aspect ratio (no stretching/distortion) and
    without any quality-degrading recompression, leaving a padding margin
    on all four sides, then center it on a target_w x target_h fully
    TRANSPARENT canvas.
    """
    src_w, src_h = img.size

    # Shrink the "available" box by the padding on each side.
    pad_x = target_w * padding_ratio
    pad_y = target_h * padding_ratio
    avail_w = target_w - 2 * pad_x
    avail_h = target_h - 2 * pad_y

    scale = min(avail_w / src_w, avail_h / src_h)
    new_w = max(1, round(src_w * scale))
    new_h = max(1, round(src_h * scale))

    resized = img.resize((new_w, new_h), Image.LANCZOS)

    # Fully transparent canvas (alpha = 0)
    canvas = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))
    offset_x = (target_w - new_w) // 2
    offset_y = (target_h - new_h) // 2
    canvas.paste(resized, (offset_x, offset_y), resized)  # use own alpha as mask
    return canvas


def process_image(src_path: Path, dst_path: Path):
    with Image.open(src_path) as img:
        img = to_rgba(img)
        img = resize_contain(img, TARGET_WIDTH, TARGET_HEIGHT)
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        # PNG is lossless -- no quality/compression settings needed to
        # preserve image quality. optimize=True just reduces file size
        # without touching pixel data.
        img.save(dst_path, OUTPUT_FORMAT, optimize=True)
    print(f"Saved: {dst_path}")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    input_path = Path(sys.argv[1])
    output_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("resized")

    if input_path.is_dir():
        files = sorted(p for p in input_path.iterdir() if p.suffix.lower() in SUPPORTED_EXTS)
        if not files:
            print(f"No supported images found in {input_path}")
            sys.exit(1)
        for f in files:
            out_file = output_dir / (f.stem + OUTPUT_EXT)
            process_image(f, out_file)
    elif input_path.is_file():
        out_file = output_dir / (input_path.stem + OUTPUT_EXT)
        process_image(input_path, out_file)
    else:
        print(f"Path not found: {input_path}")
        sys.exit(1)


if __name__ == "__main__":
    main()