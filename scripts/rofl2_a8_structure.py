#!/usr/bin/env python3
"""
Map the f1-wrapped a8 entity tables inside ROFL2 keyframes.

Verified layout (patch 16.14 keyframes, after the plaintext time header):
  10 player groups, each:
    ~2.0–2.4 KB opaque blob (candidate player state; fields still encrypted)
    a8 table runs sized [1, 117, 117, 64, 24, 6] = 329 rows
      each row = f1 00 | u16=8 | a8 XX .. .. .. .. .. ..  (12 bytes on wire)

No plaintext map floats / gold / HP found in blobs or a8 rows (static scan).
Full field values need client-side deobfuscation (see docs/rofl-format.md §5.3).

Example:
  python3 scripts/rofl2_a8_structure.py /tmp/rofl2-326 --json-out /tmp/a8-structure.json
"""
from __future__ import annotations

import argparse
import json
import struct
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Tuple


def f1_a8_rows(data: bytes) -> List[Tuple[int, bytes]]:
    rows: List[Tuple[int, bytes]] = []
    i = 0
    while i + 12 <= len(data):
        if data[i] == 0xF1 and data[i + 1] == 0x00 and struct.unpack_from("<H", data, i + 2)[0] == 8:
            pay = data[i + 4 : i + 12]
            if pay[0] == 0xA8:
                rows.append((i, pay))
                i += 12
                continue
        i += 1
    return rows


def contiguous_runs(rows: List[Tuple[int, bytes]]) -> List[List[Tuple[int, bytes]]]:
    if not rows:
        return []
    runs: List[List[Tuple[int, bytes]]] = []
    cur = [rows[0]]
    for r in rows[1:]:
        if r[0] == cur[-1][0] + 12:
            cur.append(r)
        else:
            runs.append(cur)
            cur = [r]
    runs.append(cur)
    return runs


def group_runs(runs: List[List[Tuple[int, bytes]]], gap_min: int = 1500):
    if not runs:
        return []
    groups = []
    g = [runs[0]]
    for i in range(1, len(runs)):
        gap = runs[i][0][0] - (runs[i - 1][-1][0] + 12)
        if gap >= gap_min:
            groups.append(g)
            g = [runs[i]]
        else:
            g.append(runs[i])
    groups.append(g)
    return groups


def analyze_keyframe(path: Path) -> Dict[str, Any]:
    data = path.read_bytes()
    t = struct.unpack_from("<f", data, 1)[0] if len(data) >= 5 else None
    rows = f1_a8_rows(data)
    runs = contiguous_runs(rows)
    groups = group_runs(runs)

    blobs = []
    for gi, g in enumerate(groups):
        first = g[0][0][0]
        if gi == 0:
            start = max(0, first - 2500)
            blob = data[start:first]
            if len(blob) > 2500:
                blob = blob[-2400:]
                start = first - len(blob)
        else:
            start = groups[gi - 1][-1][-1][0] + 12
            blob = data[start:first]
        blobs.append({"index": gi, "start": start, "end": first, "size": len(blob)})

    b1 = Counter(pay[1] for _, pay in rows)
    b2 = Counter(pay[2] for _, pay in rows)
    b7 = Counter(pay[7] for _, pay in rows)

    return {
        "file": path.name,
        "size": len(data),
        "time_s": t,
        "a8_row_count": len(rows),
        "run_count": len(runs),
        "run_sizes": [len(r) for r in runs],
        "group_count": len(groups),
        "group_run_sizes": [[len(r) for r in g] for g in groups],
        "group_row_totals": [sum(len(r) for r in g) for g in groups],
        "player_blobs": blobs,
        "byte1_top": b1.most_common(8),
        "byte2_top": b2.most_common(6),
        "byte7_top": b7.most_common(10),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("dump_dir", type=Path, help="Directory with seg_*_keyframe.bin")
    ap.add_argument("--json-out", type=Path, default=None)
    ap.add_argument("--limit", type=int, default=0, help="Max keyframes (0=all)")
    args = ap.parse_args()

    kfs = sorted(args.dump_dir.glob("seg_*_keyframe.bin"))
    if args.limit:
        kfs = kfs[: args.limit]
    if not kfs:
        print(f"no keyframes in {args.dump_dir}", file=sys.stderr)
        return 1

    reports = [analyze_keyframe(p) for p in kfs]
    # skip empty t=0 if present
    with_rows = [r for r in reports if r["a8_row_count"] > 0]
    sample = with_rows[0] if with_rows else reports[0]

    print(f"keyframes={len(reports)} with_a8={len(with_rows)}")
    print(
        f"sample {sample['file']} t={sample['time_s']:.1f}s "
        f"rows={sample['a8_row_count']} groups={sample['group_count']} "
        f"run_pattern={sample['group_run_sizes'][:1]}"
    )
    if sample["group_count"] == 10:
        print(f"  per-group rows={sample['group_row_totals']}")
        print(f"  blob sizes={[b['size'] for b in sample['player_blobs']]}")
    print(f"  byte1_top={sample['byte1_top']}")
    print(f"  byte2_top={sample['byte2_top']}")

    stable_groups = sum(1 for r in with_rows if r["group_count"] == 10)
    print(f"frames with exactly 10 groups: {stable_groups}/{len(with_rows)}")

    out = {
        "dump_dir": str(args.dump_dir),
        "keyframe_count": len(reports),
        "with_a8": len(with_rows),
        "frames_with_10_groups": stable_groups,
        "sample": sample,
        "all": reports,
    }
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(out, indent=2))
        print(f"wrote {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
