#!/usr/bin/env python3
"""
ROFL2 probe — metadata + zstd/dict segment extraction.

See docs/rofl-format.md for the full investigation write-up.
This script only handles the container/segment layer (not packet decode).

Example:
  python3 scripts/rofl2_probe.py \\
    "$HOME/Documents/League of Legends/Replays/BR1-3263797356.rofl" \\
    --dump-dir /tmp/rofl2-out
"""
from __future__ import annotations

import argparse
import json
import struct
import sys
from collections import Counter
from pathlib import Path

try:
    import zstandard as zstd
except ImportError:
    print("Install zstandard: pip install zstandard", file=sys.stderr)
    raise


def frame_compressed_size(buf: bytes, off: int) -> int:
    if buf[off : off + 4] != b"\x28\xb5\x2f\xfd":
        raise ValueError(f"no zstd magic at {off}")
    fhd = buf[off + 4]
    fcs_flag = (fhd >> 6) & 3
    single = (fhd >> 5) & 1
    has_checksum = (fhd >> 2) & 1
    dict_id_flag = fhd & 3
    pos = off + 5
    if not single:
        pos += 1
    pos += (0, 1, 2, 4)[dict_id_flag]
    pos += (1 if single else 0, 2, 4, 8)[fcs_flag]
    while True:
        bh = int.from_bytes(buf[pos : pos + 3], "little")
        pos += 3
        last = bh & 1
        btype = (bh >> 1) & 3
        bsize = bh >> 3
        if btype == 1:
            pos += 1
        elif btype in (0, 2):
            pos += bsize
        else:
            raise ValueError(f"reserved zstd block type {btype} at {pos}")
        if last:
            break
    if has_checksum:
        pos += 4
    return pos - off


def parse_rofl2(path: Path) -> dict:
    data = path.read_bytes()
    if data[:6] != b"RIOT\x02\x00":
        raise ValueError(f"not ROFL2 (magic={data[:6]!r})")
    unk8 = data[6:14]
    ver_len = data[14]
    version = data[15 : 15 + ver_len].decode("ascii")
    field_off = 15 + ver_len
    hdr = struct.unpack_from("<IIII", data, field_off)
    zstd_off = data.find(b"\x28\xb5\x2f\xfd", field_off + 16)
    if zstd_off < 0:
        raise ValueError("no zstd payload")
    pad = data[field_off + 16 : zstd_off]
    meta_len = struct.unpack_from("<I", data, len(data) - 4)[0]
    meta_start = len(data) - 4 - meta_len
    meta = json.loads(data[meta_start : len(data) - 4])
    return {
        "path": str(path),
        "size": len(data),
        "unk8": unk8.hex(),
        "version": version,
        "header_u32s": list(hdr),
        "pad": pad.hex(),
        "zstd_off": zstd_off,
        "payload": data[zstd_off:meta_start],
        "meta": meta,
    }


def extract_segments(payload: bytes) -> dict:
    dctx0 = zstd.ZstdDecompressor()
    flen0 = frame_compressed_size(payload, 0)
    dict_bytes = dctx0.decompress(payload[:flen0], max_output_size=50_000_000)
    dctx = zstd.ZstdDecompressor(dict_data=zstd.ZstdCompressionDict(dict_bytes))

    pos = flen0
    preamble = payload[pos : pos + 34]
    pos += 34

    segments = []
    while pos + 17 <= len(payload):
        rec = payload[pos : pos + 17]
        a, b = struct.unpack_from("<II", rec, 0)
        typ = rec[8]
        unc, comp = struct.unpack_from("<II", rec, 9)
        pos += 17
        if payload[pos : pos + 4] != b"\x28\xb5\x2f\xfd":
            break
        flen = frame_compressed_size(payload, pos)
        out = dctx.decompress(payload[pos : pos + flen], max_output_size=50_000_000)
        segments.append(
            {
                "id_a": a,
                "id_b": b,
                "type": typ,
                "type_name": {1: "chunk", 2: "keyframe"}.get(typ, f"unknown({typ})"),
                "unc": unc,
                "comp": comp,
                "flen": flen,
                "out_len": len(out),
                "match": unc == len(out) and comp == flen,
                "bytes": out,
            }
        )
        pos += flen

    return {
        "dict": dict_bytes,
        "preamble_hex": preamble.hex(),
        "segments": segments,
        "leftover": len(payload) - pos,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("rofl", type=Path)
    ap.add_argument("--dump-dir", type=Path, default=None, help="Write dict + segment bins")
    ap.add_argument("--json-out", type=Path, default=None, help="Write summary JSON (no raw bytes)")
    args = ap.parse_args()

    info = parse_rofl2(args.rofl)
    extracted = extract_segments(info["payload"])
    segs = extracted["segments"]
    types = Counter(s["type_name"] for s in segs)
    meta = {k: v for k, v in info["meta"].items() if k != "statsJson"}
    players = []
    for p in json.loads(info["meta"]["statsJson"]):
        players.append(
            {
                "name": f"{p.get('RIOT_ID_GAME_NAME')}#{p.get('RIOT_ID_TAG_LINE')}",
                "champ": p.get("SKIN"),
                "team": p.get("TEAM"),
                "kda": f"{p.get('CHAMPIONS_KILLED')}/{p.get('NUM_DEATHS')}/{p.get('ASSISTS')}",
                "win": p.get("WIN"),
            }
        )

    summary = {
        "file": args.rofl.name,
        "version": info["version"],
        "unk8": info["unk8"],
        "header_u32s": info["header_u32s"],
        "meta": meta,
        "dict_size": len(extracted["dict"]),
        "preamble_hex": extracted["preamble_hex"],
        "segment_count": len(segs),
        "types": dict(types),
        "all_size_match": all(s["match"] for s in segs),
        "leftover_bytes": extracted["leftover"],
        "players": players,
        "segments": [
            {k: v for k, v in s.items() if k != "bytes"} for s in segs
        ],
    }

    print(json.dumps({k: v for k, v in summary.items() if k != "segments"}, indent=2))
    print(f"segments: {len(segs)} types={dict(types)} size_match={summary['all_size_match']}")

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(summary, indent=2))
        print(f"wrote {args.json_out}")

    if args.dump_dir:
        args.dump_dir.mkdir(parents=True, exist_ok=True)
        (args.dump_dir / "dict.bin").write_bytes(extracted["dict"])
        for i, s in enumerate(segs):
            name = f"seg_{i:03d}_id{s['id_a']}_{s['type_name']}.bin"
            (args.dump_dir / name).write_bytes(s["bytes"])
        print(f"wrote {1 + len(segs)} bins to {args.dump_dir}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
