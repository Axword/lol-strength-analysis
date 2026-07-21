#!/usr/bin/env python3
"""
Bootstrap a Label Studio project config + import task list from extracted frames.

Also writes a starter batch of high-value frames (siege / grub windows) for
priority annotation.

Usage:
  python vision/prepare_annotation.py
  # then: label-studio start  (or Docker)
  # import vision/data/exports/labelstudio_tasks.json
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRAMES = ROOT / "vision" / "data" / "frames" / "raw"
INDEX = ROOT / "vision" / "data" / "frames" / "index.jsonl"
EXPORT = ROOT / "vision" / "data" / "exports"
TIMELINE = ROOT / "public" / "data" / "fur_vs_g2_timeline.json"
VOD_META = ROOT / "public" / "data" / "fur_vs_g2_vod.json"

# Priority game-time windows (sec) — grubs + late sieges from this match
PRIORITY_WINDOWS = [
    (520, 560),  # grub take
    (720, 760),  # early Touch rises
    (1040, 1080),
    (1150, 1200),
    (1310, 1330),
    (1390, 1470),  # base siege / mites visible
]


def in_priority(t: float) -> bool:
    return any(a <= t <= b for a, b in PRIORITY_WINDOWS)


def main() -> None:
    from classes import LABEL_STUDIO_XML

    EXPORT.mkdir(parents=True, exist_ok=True)
    (EXPORT / "labelstudio_config.xml").write_text(LABEL_STUDIO_XML.strip() + "\n")

    if not INDEX.exists():
        raise SystemExit(
            f"missing {INDEX} — run: python vision/extract_frames.py --interval 0.5"
        )

    tasks_all = []
    tasks_priority = []
    for line in INDEX.read_text().splitlines():
        row = json.loads(line)
        # Label Studio local files: absolute path or served URL
        abs_path = ROOT / row["path"]
        task = {
            "data": {
                "image": f"local-files://{abs_path}",
                "tSec": row["tSec"],
                "frame": row["frame"],
            },
            "meta": {"tSec": row["tSec"], "priority": in_priority(row["tSec"])},
        }
        tasks_all.append(task)
        if in_priority(row["tSec"]):
            tasks_priority.append(task)

    (EXPORT / "labelstudio_tasks.json").write_text(json.dumps(tasks_all, indent=2))
    (EXPORT / "labelstudio_tasks_priority.json").write_text(
        json.dumps(tasks_priority, indent=2)
    )

    # YOLO empty label stubs for priority frames (so annotators know targets)
    raw_labels = ROOT / "vision" / "data" / "labels" / "raw"
    raw_labels.mkdir(parents=True, exist_ok=True)
    stubbed = 0
    for task in tasks_priority:
        stem = Path(task["data"]["frame"]).stem
        lab = raw_labels / f"{stem}.txt"
        if not lab.exists():
            lab.write_text("")  # empty = image in queue, no boxes yet
            stubbed += 1

    readme = EXPORT / "ANNOTATE.md"
    readme.write_text(
        f"""# Annotate Touch OD boxes

## Classes
See `vision/classes.py` / `vision/dataset.yaml`.

Priority labels for Touch audit:
- **voidmite** — purple mites on structures (Hunger)
- **turret / inhibitor / nexus** — structures being sieged
- **champion** — champs near structures
- **replay_bumper** — full-screen REPLAY cards (negative / skip)
- **touch_burn_fx** — purple burn VFX if clearly visible
- **grub_buff_icon** — Touch buff icon over champ / HUD

## Label Studio (recommended)

```bash
# once
pip install label-studio
export LABEL_STUDIO_LOCAL_FILES_SERVING_ENABLED=true
export LABEL_STUDIO_LOCAL_FILES_DOCUMENT_ROOT={ROOT}
label-studio start
```

1. Create project → paste XML from `labelstudio_config.xml`
2. Import `labelstudio_tasks_priority.json` first (~priority siege/grub windows)
3. Draw boxes → Export YOLO → drop txt files into `vision/data/labels/raw/`
4. `python vision/split_dataset.py && python vision/train_detector.py`

## Counts
- all frames: {len(tasks_all)}
- priority frames: {len(tasks_priority)}
- empty label stubs created: {stubbed}
"""
    )
    print(f"tasks all={len(tasks_all)} priority={len(tasks_priority)}")
    print(f"config → {EXPORT / 'labelstudio_config.xml'}")
    print(f"guide → {readme}")


if __name__ == "__main__":
    main()
