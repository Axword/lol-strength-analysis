#!/usr/bin/env python3
"""
ROFL2 packet-layer taxonomy.

Requires container extract first (see scripts/rofl2_probe.py). Given a dump
dir with dict.bin + seg_*.bin + summary.json, this script:

  - reads plaintext f32 timestamps from chunk/keyframe bodies
  - builds a segment timeline (≈30s chunks, ≈60s keyframes)
  - writes taxonomy + timeline JSON for further decode work

Example:
  python3 scripts/rofl2_probe.py path/to/file.rofl --dump-dir /tmp/rofl2-out
  python3 scripts/rofl2_packet_taxonomy.py /tmp/rofl2-out
"""
from __future__ import annotations

import argparse
import json
import math
import struct
import sys
from collections import Counter
from pathlib import Path


def parse_body_time(data: bytes) -> dict:
    """Best-effort body header: marker u8 + f32 seconds at offset 1."""
    if len(data) < 5:
        return {"marker": None, "t": None, "ok": False}
    marker = data[0]
    t = struct.unpack_from("<f", data, 1)[0]
    ok = math.isfinite(t) and -0.5 <= t <= 10_000
    out = {"marker": marker, "t": float(t) if ok else None, "ok": ok, "head16": data[:16].hex()}
    # Keyframes (marker 1) also expose stable u32 fields at 5 and 9.
    if ok and len(data) >= 13 and marker == 1:
        a = struct.unpack_from("<I", data, 5)[0]
        b = struct.unpack_from("<I", data, 9)[0]
        out["kf_field_a"] = a
        out["kf_field_b"] = b
    return out


def entropy(data: bytes) -> float:
    if not data:
        return 0.0
    counts = Counter(data)
    n = len(data)
    return -sum((c / n) * math.log2(c / n) for c in counts.values())


def analyze_dump(dump_dir: Path) -> dict:
    summary_path = dump_dir / "summary.json"
    if not summary_path.exists():
        raise SystemExit(f"missing {summary_path} — run rofl2_probe.py --dump-dir first")
    summary = json.loads(summary_path.read_text())
    segs_meta = summary["segments"]

    timeline = []
    for i, meta in enumerate(segs_meta):
        matches = sorted(dump_dir.glob(f"seg_{i:03d}_*.bin"))
        if not matches:
            raise SystemExit(f"missing segment bin for index {i}")
        data = matches[0].read_bytes()
        hdr = parse_body_time(data)
        timeline.append(
            {
                "seg": i,
                "file": matches[0].name,
                "id_a": meta["id_a"],
                "id_b": meta["id_b"],
                "type": meta["type_name"],
                "size": len(data),
                "entropy": round(entropy(data), 4),
                **hdr,
            }
        )

    chunks = [x for x in timeline if x["type"] == "chunk" and x["t"] is not None]
    kfs = [x for x in timeline if x["type"] == "keyframe" and x["t"] is not None]
    cdiffs = [round(chunks[i + 1]["t"] - chunks[i]["t"], 3) for i in range(len(chunks) - 1)]
    kdiffs = [round(kfs[i + 1]["t"] - kfs[i]["t"], 3) for i in range(len(kfs) - 1)]

    # Early keyframe 0x29-run slots (structured, not ciphertext)
    kf_slots = []
    for x in kfs[:5]:
        data = (dump_dir / x["file"]).read_bytes()
        runs = []
        j = 0
        while j < min(len(data), 400) - 6:
            if data[j : j + 6] == b"\x29" * 6:
                runs.append({"off": j, "ctx": data[max(0, j - 8) : j + 16].hex()})
                j += 6
            else:
                j += 1
        kf_slots.append({"t": x["t"], "runs": runs})

    report = {
        "source_summary": {
            "file": summary.get("file"),
            "version": summary.get("version"),
            "meta": summary.get("meta"),
            "players": summary.get("players"),
        },
        "body_header": {
            "layout": "u8 marker | f32 time_seconds | (keyframes: u32=2, u32=0x50, …)",
            "keyframe_interval_s": "~60",
            "chunk_interval_s": "~30",
        },
        "counts": {
            "segments": len(timeline),
            "chunks_with_time": len(chunks),
            "keyframes_with_time": len(kfs),
            "chunk_markers": dict(Counter(c["marker"] for c in chunks)),
            "keyframe_markers": dict(Counter(k["marker"] for k in kfs)),
        },
        "cadence": {
            "chunk_dt_top": Counter(cdiffs).most_common(8),
            "keyframe_dt_top": Counter(kdiffs).most_common(8),
            "chunk_t_range": [chunks[0]["t"], chunks[-1]["t"]] if chunks else None,
            "keyframe_t_range": [kfs[0]["t"], kfs[-1]["t"]] if kfs else None,
        },
        "early_keyframe_0x29_slots": kf_slots,
        "blocked": [
            "Inner fields after the time header are still largely opaque (obfuscated / bit-packed).",
            "End-of-game box-score integers (gold, items) are not present as raw LE u32 in segment bodies.",
            "No reliable plaintext map-coordinate stream found yet — cannot emit stats_update.",
        ],
        "timeline": timeline,
    }
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("dump_dir", type=Path)
    ap.add_argument(
        "--json-out",
        type=Path,
        default=None,
        help="Write full taxonomy JSON (default: <dump_dir>/taxonomy.json)",
    )
    args = ap.parse_args()
    report = analyze_dump(args.dump_dir)
    out = args.json_out or (args.dump_dir / "taxonomy.json")
    out.write_text(json.dumps(report, indent=2))

    c = report["counts"]
    cad = report["cadence"]
    print(
        json.dumps(
            {
                "wrote": str(out),
                "segments": c["segments"],
                "chunks_with_time": c["chunks_with_time"],
                "keyframes_with_time": c["keyframes_with_time"],
                "chunk_dt_top": cad["chunk_dt_top"][:3],
                "keyframe_dt_top": cad["keyframe_dt_top"][:3],
                "chunk_t_range": cad["chunk_t_range"],
                "keyframe_t_range": cad["keyframe_t_range"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
