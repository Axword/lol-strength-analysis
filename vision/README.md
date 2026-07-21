# Touch / structure object detection (broadcast VOD)

## Pipeline

1. **Extract frames @ 0.5s**
   ```bash
   python3 -m venv vision/.venv && source vision/.venv/bin/activate
   pip install -r vision/requirements.txt
   python vision/extract_frames.py --interval 0.5 --width 1280
   ```

2. **Prepare Label Studio tasks**
   ```bash
   python vision/prepare_annotation.py
   ```

3. **Annotate bounding boxes** (priority first — 546 siege/grub frames)
   - See `vision/data/exports/ANNOTATE.md`
   - Optional UI: `pip install -r vision/requirements-annotate.txt` then Label Studio
   - Or any YOLO-format tool; drop `*.txt` into `vision/data/labels/raw/`
   - Classes: voidmite, turret, inhibitor, nexus, champion, replay_bumper, touch_burn_fx, grub_buff_icon, baron_buff_icon

4. **Split + train**
   ```bash
   python vision/split_dataset.py
   python vision/train_detector.py --model yolov8n.pt --epochs 80 --imgsz 1280 --device mps
   ```

5. **Infer over all frames**
   ```bash
   python vision/infer_touch_od.py --weights vision/weights/touch-od-v1-best.pt
   ```

Detections JSONL feeds Touch confidence (voidmite / siege / replay skip) in a later enrich pass.
