#!/usr/bin/env python3
"""
Train a YOLO detector on Touch / structure boxes.

Requires:
  pip install -r vision/requirements.txt
  labeled data split via vision/split_dataset.py

Usage:
  python vision/train_detector.py --model yolov8n.pt --epochs 80 --imgsz 1280
  python vision/train_detector.py --resume
"""
from __future__ import annotations

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_YAML = ROOT / "vision" / "dataset.yaml"
RUNS = ROOT / "vision" / "data" / "runs"
WEIGHTS = ROOT / "vision" / "weights"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", default="yolov8n.pt", help="Base checkpoint")
    ap.add_argument("--epochs", type=int, default=80)
    ap.add_argument("--imgsz", type=int, default=1280)
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--device", default="mps", help="mps | cpu | 0")
    ap.add_argument("--name", default="touch-od-v1")
    ap.add_argument("--resume", action="store_true")
    args = ap.parse_args()

    try:
        from ultralytics import YOLO
    except ImportError as e:
        raise SystemExit(
            "ultralytics not installed. Run:\n"
            "  python3 -m venv vision/.venv && "
            "source vision/.venv/bin/activate && "
            "pip install -r vision/requirements.txt"
        ) from e

    train_imgs = ROOT / "vision" / "data" / "images" / "train"
    if not train_imgs.exists() or not any(train_imgs.iterdir()):
        raise SystemExit(
            "No train images. Annotate labels, then:\n"
            "  python vision/split_dataset.py"
        )

    WEIGHTS.mkdir(parents=True, exist_ok=True)
    RUNS.mkdir(parents=True, exist_ok=True)

    model = YOLO(args.model)
    results = model.train(
        data=str(DATA_YAML),
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=args.device,
        project=str(RUNS),
        name=args.name,
        resume=args.resume,
        exist_ok=True,
    )

    best = RUNS / args.name / "weights" / "best.pt"
    if best.exists():
        dest = WEIGHTS / f"{args.name}-best.pt"
        dest.write_bytes(best.read_bytes())
        print(f"copied best weights → {dest}")
    print(results)


if __name__ == "__main__":
    main()
