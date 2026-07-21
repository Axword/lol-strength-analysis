#!/usr/bin/env python3
"""
Touch VOD probe — cut siege windows from a match recording for AA/ability review.

Usage:

  python3 scripts/touch_vod_probe.py \\
    "G2 Esports vs FURIA ｜ League of Legends at EWC 26 - Group Stage - VOD [WWndc4XR3vs].webm" \\
    --timeline public/data/fur_vs_g2_timeline.json \\
    --out /tmp/touch-vod-clips \\
    --offset-sec 20

Offset: VOD clock − gameTime. If the recording starts at champ select, measure
how many seconds until 00:00 game clock and pass that as --offset-sec.

Requires: ffmpeg on PATH.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path


def cut_clip(vod: Path, start: float, dur: float, out_path: Path) -> bool:
    cmd = [
        "ffmpeg",
        "-y",
        "-ss",
        f"{start:.2f}",
        "-i",
        str(vod),
        "-t",
        f"{dur:.2f}",
        "-c:v",
        "libvpx-vp9",
        "-c:a",
        "libopus",
        "-deadline",
        "realtime",
        "-cpu-used",
        "8",
        str(out_path),
    ]
    # Prefer stream copy when container allows; fall back already set to reencode.
    copy_cmd = [
        "ffmpeg",
        "-y",
        "-ss",
        f"{start:.2f}",
        "-i",
        str(vod),
        "-t",
        f"{dur:.2f}",
        "-c",
        "copy",
        str(out_path),
    ]
    r = subprocess.run(copy_cmd, capture_output=True)
    if r.returncode == 0 and out_path.exists() and out_path.stat().st_size > 1000:
        return True
    r = subprocess.run(cmd, capture_output=True)
    return r.returncode == 0 and out_path.exists()


def grab_frame(vod: Path, t_sec: float, out_png: Path) -> bool:
    cmd = [
        "ffmpeg",
        "-y",
        "-ss",
        f"{t_sec:.2f}",
        "-i",
        str(vod),
        "-frames:v",
        "1",
        str(out_png),
    ]
    r = subprocess.run(cmd, capture_output=True)
    return r.returncode == 0 and out_png.exists()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("vod", type=Path, help="Match recording (mp4/mkv/webm)")
    ap.add_argument(
        "--timeline",
        type=Path,
        default=Path("public/data/fur_vs_g2_timeline.json"),
    )
    ap.add_argument("--out", type=Path, default=Path("/tmp/touch-vod-clips"))
    ap.add_argument("--pad-sec", type=float, default=3.5)
    ap.add_argument("--max-clips", type=int, default=36)
    ap.add_argument(
        "--offset-sec",
        type=float,
        default=0.0,
        help="VOD seconds at gameTime 0 (pregame length)",
    )
    ap.add_argument(
        "--frames",
        action="store_true",
        help="Also extract a still PNG at each clip midpoint",
    )
    args = ap.parse_args()

    if not shutil.which("ffmpeg"):
        raise SystemExit("ffmpeg not found on PATH")
    if not args.vod.exists():
        raise SystemExit(f"missing VOD: {args.vod}")
    if not args.timeline.exists():
        raise SystemExit(f"missing timeline: {args.timeline}")

    tl = json.loads(args.timeline.read_text())
    frames = tl.get("frames") or []
    candidates: list[dict] = []
    prev_touch: dict[int, float] = {}

    for fr in frames:
        t_ms = int(fr.get("t") or 0)
        for u in fr.get("units") or []:
            c = u.get("career") or {}
            stacks = int(c.get("touchStacks") or 0)
            if stacks <= 0:
                continue
            touch = float(c.get("touchDmg") or 0)
            pid = int(u.get("pid") or 0)
            prev = prev_touch.get(pid, touch)
            rising = touch > prev + 8
            prev_touch[pid] = touch
            if not rising:
                continue
            conf = c.get("touchConfidence") or "low"
            skill = int(c.get("touchRejectedSkill") or 0)
            far = int(c.get("touchRejectedFar") or 0)
            aa = int(c.get("touchRefreshAa") or 0)
            # Priority: non-high first, then skill-heavy highs (ability siegers),
            # then any strong Touch rise for validation.
            if conf != "high":
                pri = 0
            elif skill >= 3:
                pri = 1
            elif aa >= 5:
                pri = 2
            else:
                pri = 3
            candidates.append(
                {
                    "priority": pri,
                    "tMs": t_ms,
                    "tSec": t_ms / 1000.0,
                    "pid": pid,
                    "champ": u.get("champ") or u.get("name"),
                    "team": u.get("team"),
                    "confidence": conf,
                    "touchDmg": touch,
                    "deltaTouch": touch - prev,
                    "rejectedFar": far,
                    "rejectedSkill": skill,
                    "rejectedAbility": c.get("touchRejectedAbility"),
                    "refreshAa": aa,
                }
            )

    candidates.sort(key=lambda w: (w["priority"], -w["deltaTouch"], w["tSec"]))

    picked: list[dict] = []
    last_by_pid: dict[int, float] = {}
    for w in candidates:
        last = last_by_pid.get(w["pid"], -1e9)
        if w["tSec"] - last < 8.0:
            continue
        picked.append(w)
        last_by_pid[w["pid"]] = w["tSec"]
        if len(picked) >= args.max_clips:
            break

    # Prefer chronological for watching
    picked.sort(key=lambda w: w["tSec"])

    args.out.mkdir(parents=True, exist_ok=True)
    manifest = {
        "vod": str(args.vod.resolve()),
        "timeline": str(args.timeline),
        "offsetSec": args.offset_sec,
        "model": tl.get("touchModel"),
        "note": "vodTime = gameTimeSec + offsetSec",
        "clips": [],
    }

    for i, w in enumerate(picked):
        vod_mid = w["tSec"] + args.offset_sec
        start = max(0.0, vod_mid - args.pad_sec)
        dur = args.pad_sec * 2
        tag = w["confidence"]
        out_path = (
            args.out
            / f"siege_{i:03d}_t{int(w['tSec'])}s_pid{w['pid']}_{tag}.webm"
        )
        ok = cut_clip(args.vod, start, dur, out_path)
        frame_path = None
        if args.frames:
            frame_path = args.out / f"siege_{i:03d}_t{int(w['tSec'])}s_pid{w['pid']}.png"
            grab_frame(args.vod, vod_mid, frame_path)
        clip = {
            **w,
            "ok": ok,
            "file": str(out_path) if ok else None,
            "frame": str(frame_path) if frame_path and frame_path.exists() else None,
            "vodStartSec": start,
            "vodMidSec": vod_mid,
            "vodDurSec": dur,
        }
        manifest["clips"].append(clip)
        status = "ok" if ok else "FAIL"
        print(
            f"[{status}] {i:02d} game={w['tSec']:.0f}s vod={vod_mid:.0f}s "
            f"pid={w['pid']} conf={w['confidence']} Δtouch={w['deltaTouch']:.0f} "
            f"skill={w['rejectedSkill']} aa={w['refreshAa']}"
        )

    man_path = args.out / "manifest.json"
    man_path.write_text(json.dumps(manifest, indent=2))
    print(f"wrote {man_path} ({len(manifest['clips'])} clips)")


if __name__ == "__main__":
    main()
