#!/usr/bin/env python3
"""
Split labeled frames into train/val YOLO layout.

Expects YOLO labels next to or mirrored under:
  vision/data/labels/raw/<frame_stem>.txt

Copies images + labels into:
  vision/data/images/{train,val}
  vision/data/labels/{train,val}

Usage:
  python vision/split_dataset.py --val-ratio 0.2
"""
from __future__ import annotations

import argparse
import random
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRAMES = ROOT / "vision" / "data" / "frames" / "raw"
LABELS = ROOT / "vision" / "data" / "labels" / "raw"
DATA = ROOT / "vision" / "data"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--val-ratio", type=float, default=0.2)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    if not LABELS.exists():
        raise SystemExit(f"no labels yet: {LABELS} — annotate first")

    pairs: list[tuple[Path, Path]] = []
    for lab in sorted(LABELS.glob("*.txt")):
        img = FRAMES / f"{lab.stem}.jpg"
        if not img.exists():
            img = FRAMES / f"{lab.stem}.png"
        if img.exists():
            pairs.append((img, lab))

    if not pairs:
        raise SystemExit("no image/label pairs found")

    rng = random.Random(args.seed)
    rng.shuffle(pairs)
    n_val = max(1, int(len(pairs) * args.val_ratio)) if len(pairs) >= 5 else max(
        1, len(pairs) // 5 or 1
    )
    n_val = min(n_val, len(pairs) - 1) if len(pairs) > 1 else 0
    val = pairs[:n_val]
    train = pairs[n_val:] or pairs

    for split, items in (("train", train), ("val", val)):
        idir = DATA / "images" / split
        ldir = DATA / "labels" / split
        if idir.exists():
            shutil.rmtree(idir)
        if ldir.exists():
            shutil.rmtree(ldir)
        idir.mkdir(parents=True)
        ldir.mkdir(parents=True)
        for img, lab in items:
            shutil.copy2(img, idir / img.name)
            shutil.copy2(lab, ldir / lab.name)
        print(f"{split}: {len(items)} pairs → {idir}")

    print("done. Train with: python vision/train_detector.py")


if __name__ == "__main__":
    main()
