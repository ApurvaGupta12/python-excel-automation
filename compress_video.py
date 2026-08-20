#!/usr/bin/env python3
"""
compress_video.py (batch version)
------------------
Compresses one or more videos to a target file size (in MB), while
preserving quality and color as much as possible.

Requirements:
    - ffmpeg must be installed and available in your system PATH
      (Windows: download from https://ffmpeg.org/download.html and add it to PATH)
      (Mac: brew install ffmpeg)
      (Linux: sudo apt install ffmpeg)

Usage examples:

    1) Single video:
       python compress_video.py "REEL 9 V3.mp4" output.mp4 --size 15

    2) Multiple specific videos (saved into an output folder):
       python compress_video.py "video1.mp4" "video2.mp4" "video3.mp4" --outdir compressed --size 15

    3) Compress an entire folder of videos at once:
       python compress_video.py --folder "C:\\Users\\dell\\Videos\\Reels" --outdir compressed --size 15

Notes:
    - If you give only 1 input file and no --outdir, it works the old way:
      input output --size (same as the very first version of this script).
    - If you give 2+ inputs, or use --folder, then --outdir is required
      (compressed videos will be saved there, using the original filenames).
    - Videos are processed one at a time (sequentially), not in parallel,
      to avoid overloading your CPU/RAM — this keeps it safe and stable
      on modest hardware.
    - --preset controls the speed/quality trade-off. Options (fastest to
      slowest): ultrafast, superfast, veryfast, faster, fast, medium,
      slow, slower, veryslow. Default is "fast" — a good balance.
    - Supported video extensions (in --folder mode): .mp4 .mov .mkv .avi .webm

Safety notes:
    - This script only reads your input video(s) and writes new compressed
      output file(s). It does not modify, move, or delete your original
      videos, and it does not access the internet or send any data anywhere.
    - It runs locally on your machine using ffmpeg, a well-known open-source
      tool used worldwide for video processing.
    - Cross-platform: this script works on Windows, Mac, and Linux, as long
      as Python 3 and ffmpeg are installed on that system. No OS-specific
      code is used.
"""

import argparse
import subprocess
import json
import math
import os
import sys

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm"}


def get_video_duration(input_path: str) -> float:
    """Uses ffprobe to get the video's duration in seconds."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "json",
        input_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    data = json.loads(result.stdout)
    return float(data["format"]["duration"])


def compress_one(input_path: str, output_path: str, target_size_mb: float,
                  audio_bitrate_kbps: int, preset: str):
    if not os.path.isfile(input_path):
        print(f"⚠️  Skipping, file not found -> {input_path}")
        return False

    print(f"\n===============================")
    print(f"Processing: {input_path}")
    print(f"===============================")

    duration = get_video_duration(input_path)
    print(f"Video duration: {duration:.2f} sec")

    # Convert target size to bits, with a 5% safety margin so the final
    # file stays under the target instead of going over it.
    target_size_bits = target_size_mb * 8 * 1024 * 1024 * 0.95
    audio_bitrate_bps = audio_bitrate_kbps * 1000
    video_bitrate_bps = (target_size_bits / duration) - audio_bitrate_bps

    if video_bitrate_bps <= 0:
        print(f"⚠️  Skipping, target size ({target_size_mb}MB) is too small "
              f"for this video's duration ({duration:.1f}s).")
        return False

    video_bitrate_kbps = math.floor(video_bitrate_bps / 1000)
    print(f"Calculated video bitrate: {video_bitrate_kbps} kbps")
    print(f"Preset: {preset}")

    cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-c:v", "libx264",
        "-preset", preset,
        "-b:v", f"{video_bitrate_kbps}k",
        "-maxrate", f"{int(video_bitrate_kbps * 1.5)}k",
        "-bufsize", f"{video_bitrate_kbps * 2}k",
        "-pix_fmt", "yuv420p",   # preserve original color format
        "-c:a", "aac",
        "-b:a", f"{audio_bitrate_kbps}k",
        output_path,
    ]

    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError:
        print(f"❌ ffmpeg failed for this file: {input_path}")
        return False

    final_size_mb = os.path.getsize(output_path) / (1024 * 1024)
    print(f"✅ Done! Final size: {final_size_mb:.2f} MB -> {output_path}")
    return True


def collect_inputs_from_folder(folder_path: str):
    if not os.path.isdir(folder_path):
        print(f"Error: folder not found -> {folder_path}")
        sys.exit(1)

    files = []
    for name in sorted(os.listdir(folder_path)):
        ext = os.path.splitext(name)[1].lower()
        if ext in VIDEO_EXTENSIONS:
            files.append(os.path.join(folder_path, name))

    if not files:
        print(f"Error: no video files found in this folder -> {folder_path}")
        sys.exit(1)

    return files


def main():
    parser = argparse.ArgumentParser(
        description="Compress one or more videos to a target file size (MB)."
    )
    parser.add_argument("inputs", nargs="*", help="Input video file(s). Skip if using --folder.")
    parser.add_argument("output", nargs="?", help="Output file (only used in single-video mode)")
    parser.add_argument("--folder", type=str, default=None,
                         help="Path to a folder — every video inside it will be compressed.")
    parser.add_argument("--outdir", type=str, default=None,
                         help="Compressed videos will be saved here (required in multi-file or --folder mode).")
    parser.add_argument("--size", type=float, required=True, help="Target size in MB (e.g. 15)")
    parser.add_argument("--audio-bitrate", type=int, default=128, help="Audio bitrate in kbps (default: 128)")
    parser.add_argument("--preset", type=str, default="fast",
                         choices=["ultrafast", "superfast", "veryfast", "faster",
                                  "fast", "medium", "slow", "slower", "veryslow"],
                         help="ffmpeg encoding preset (default: fast).")
    args = parser.parse_args()

    # ---- Mode 1: --folder ----
    if args.folder:
        if not args.outdir:
            print("Error: --outdir is required when using --folder.")
            sys.exit(1)
        os.makedirs(args.outdir, exist_ok=True)
        input_files = collect_inputs_from_folder(args.folder)

    # ---- Mode 2: multiple specific files (2+) ----
    elif len(args.inputs) >= 2:
        if not args.outdir:
            print("Error: --outdir is required when passing multiple files.")
            sys.exit(1)
        os.makedirs(args.outdir, exist_ok=True)
        input_files = args.inputs

    # ---- Mode 3: single file, old style (input output --size) ----
    elif len(args.inputs) == 1 and args.output:
        ok = compress_one(args.inputs[0], args.output, args.size, args.audio_bitrate, args.preset)
        sys.exit(0 if ok else 1)

    else:
        print("Error: invalid arguments. Run with --help to see usage examples.")
        sys.exit(1)

    # ---- Batch processing (Mode 1 or 2) ----
    print(f"\nTotal {len(input_files)} video(s) to process, one at a time...\n")

    success_count = 0
    fail_count = 0

    for in_path in input_files:
        base_name = os.path.basename(in_path)
        name_no_ext = os.path.splitext(base_name)[0]
        out_path = os.path.join(args.outdir, f"{name_no_ext}_compressed.mp4")

        ok = compress_one(in_path, out_path, args.size, args.audio_bitrate, args.preset)
        if ok:
            success_count += 1
        else:
            fail_count += 1

    print(f"\n================================")
    print(f"Batch complete: {success_count} succeeded, {fail_count} failed/skipped.")
    print(f"Output folder: {os.path.abspath(args.outdir)}")
    print(f"================================")


if __name__ == "__main__":
    main()
