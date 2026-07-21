#!/usr/bin/env python3
"""
Run the trained detector over 0.5s frames (or a VOD) and emit detections JSONL.

Usage:
  python vision/infer_touch_od.py --weights vision/weights/touch-od-v1-best.pt
  python vision/infer_touch_od.py --weights ... --vod path.webm --interval 0.5
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRAMES = ROOT / "vision" / "data" / "frames" / "raw"
INDEX = ROOT / "vision" / "data" / "frames" / "index.jsonl"
OUT = ROOT / "vision" / "data" / "exports" / "detections.jsonl"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--weights", type=Path, required=True)
    ap.add_argument("--source", type=Path, default=FRAMES, help="Frame dir or VOD")
    ap.add_argument("--index", type=Path, default=INDEX)
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--imgsz", type=int, default=1280)
    ap.add_argument("--conf", type=float, default=0.25)
    ap.add_argument("--device", default="mps")
    args = ap.parse_args()

    from ultralytics import YOLO

    from classes import ID_TO_CLASS

    model = YOLO(str(args.weights))
    args.out.parent.mkdir(parents=True, exist_ok=True)

    t_by_frame: dict[str, float] = {}
    if args.index.exists():
        for line in args.index.read_text().splitlines():
            row = json.loads(line)
            t_by_frame[row["frame"]] = row["tSec"]

    results = model.predict(
        source=str(args.source),
        imgsz=args.imgsz,
        conf=args.conf,
        device=args.device,
        stream=True,
        verbose=False,
    )

    n = 0
    with args.out.open("w") as f:
        for r in results:
            path = Path(r.path)
            t_sec = t_by_frame.get(path.name)
            boxes = []
            if r.boxes is not None:
                for b in r.boxes:
                    cls_id = int(b.cls.item())
                    boxes.append(
                        {
                            "cls": ID_TO_CLASS.get(cls_id, str(cls_id)),
                            "clsId": cls_id,
                            "conf": float(b.conf.item()),
                            "xyxy": [float(x) for x in b.xyxy[0].tolist()],
                        }
                    )
            row = {
                "frame": path.name,
                "path": str(path),
                "tSec": t_sec,
                "boxes": boxes,
            }
            f.write(json.dumps(row) + "\n")
            n += 1
            if n % 200 == 0:
                print(f"... {n} frames")

    print(f"wrote {n} rows → {args.out}")


if __name__ == "__main__":
    main()
