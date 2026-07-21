#!/usr/bin/env python3
"""
Extract VOD frames at a fixed interval (default 0.5s → 2 fps) for OD training.

Writes:
  vision/data/frames/raw/frame_XXXXXX.jpg
  vision/data/frames/index.jsonl   # one row per frame: idx, tSec, path

Usage:
  python vision/extract_frames.py \\
    --vod "G2 Esports vs FURIA ｜ League of Legends at EWC 26 - Group Stage - VOD [WWndc4XR3vs].webm" \\
    --interval 0.5 \\
    --width 1280
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_VOD = ROOT / (
    "G2 Esports vs FURIA ｜ League of Legends at EWC 26 - Group Stage - VOD [WWndc4XR3vs].webm"
)
OUT_DIR = ROOT / "vision" / "data" / "frames" / "raw"
INDEX = ROOT / "vision" / "data" / "frames" / "index.jsonl"


def ffprobe_duration(vod: Path) -> float:
    r = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(vod),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(r.stdout.strip())


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--vod", type=Path, default=DEFAULT_VOD)
    ap.add_argument("--interval", type=float, default=0.5, help="Seconds between frames")
    ap.add_argument("--width", type=int, default=1280, help="Output width (keeps aspect)")
    ap.add_argument("--out", type=Path, default=OUT_DIR)
    ap.add_argument("--index", type=Path, default=INDEX)
    ap.add_argument(
        "--resume",
        action="store_true",
        help="Skip ffmpeg if frames already exist; rebuild index only",
    )
    args = ap.parse_args()

    if not args.vod.exists():
        raise SystemExit(f"missing VOD: {args.vod}")

    args.out.mkdir(parents=True, exist_ok=True)
    args.index.parent.mkdir(parents=True, exist_ok=True)

    duration = ffprobe_duration(args.vod)
    fps = 1.0 / args.interval
    expected = int(duration * fps) + 1
    pattern = str(args.out / "frame_%06d.jpg")

    existing = sorted(args.out.glob("frame_*.jpg"))
    if args.resume and len(existing) >= expected * 0.95:
        print(f"resume: found {len(existing)} frames (expected ~{expected})")
    else:
        # fps filter + scale. -q:v 3 ≈ high-quality JPEG.
        vf = f"fps={fps},scale={args.width}:-1"
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(args.vod),
            "-vf",
            vf,
            "-q:v",
            "3",
            pattern,
        ]
        print("running:", " ".join(cmd))
        print(f"duration={duration:.1f}s interval={args.interval}s → ~{expected} frames")
        subprocess.run(cmd, check=True)
        existing = sorted(args.out.glob("frame_*.jpg"))

    # Rebuild index: frame_000001 = t=0 for ffmpeg fps filter (first frame at 0)
    rows = []
    with args.index.open("w") as f:
        for i, path in enumerate(existing):
            t_sec = i * args.interval
            row = {
                "idx": i,
                "frame": path.name,
                "path": str(path.relative_to(ROOT)),
                "tSec": round(t_sec, 3),
                "interval": args.interval,
            }
            f.write(json.dumps(row) + "\n")
            rows.append(row)

    meta = {
        "vod": str(args.vod),
        "durationSec": duration,
        "intervalSec": args.interval,
        "width": args.width,
        "frameCount": len(rows),
        "index": str(args.index.relative_to(ROOT)),
    }
    meta_path = args.out.parent / "meta.json"
    meta_path.write_text(json.dumps(meta, indent=2))
    print(f"wrote {len(rows)} frames → {args.out}")
    print(f"index → {args.index}")
    print(f"meta → {meta_path}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
