#!/usr/bin/env python3
"""E13: Live positions in type-2 keyframe segments?

Tests E12's next hypothesis: type-2 keyframes (not type-1 chunks) carry
multi-hero plaintext X/Z. Uses documented keyframe header + a8/player-blob
layout, optional filtered block Deserialize for channels that also exist in
chunks, and Replay API QA at keyframe times (±500 ms).

Hard constraints: no live API, no plan edit, no commit, no binary vendoring,
no learned affine. Axis-swap only.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import struct
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from unicorn import UC_HOOK_MEM_WRITE  # noqa: E402

from rofl2_a8_structure import contiguous_runs, f1_a8_rows, group_runs  # noqa: E402
from rofl2_binary_format import load_binary, research_manifest  # noqa: E402
from rofl2_movement_decode import (  # noqa: E402
    _load_oracle_positions,
    append_speed_record,
)
from rofl2_movement_wire_scan import (  # noqa: E402
    PROVEN_HERO_NET_ID_SET,
    PROVEN_HERO_NET_IDS,
)
from rofl2_probe import extract_segments, parse_rofl2  # noqa: E402
from rofl2_unicorn_packet_drive import extract_blocks_py  # noqa: E402
from rofl2_win_pe_e11_reconstructed_drive import MARKER_1, MARKER_2, encode_type  # noqa: E402
from rofl2_win_pe_packet_discover import (  # noqa: E402
    WinX64PacketEmu,
    enumerate_rofl,
    official_provenance,
    scan_msvc_packet_types,
)

PROBE_VERSION = "e13-win-pe-keyframe-positions-v1"
MATCH_CODE = "3264361042"
DEFAULT_PE = Path("/tmp/League-of-Legends-16.14-win.exe")
DEFAULT_ROFL = Path.home() / "Documents/League of Legends/Replays/BR1-3264361042.rofl"
DEFAULT_ORACLE = Path("artifacts/rofl/3264361042/events.rfc461.jsonl")
DEFAULT_REPORT = Path("docs/rofl-research/movement-win-pe-e13-BR1-3264361042.json")
SPEED_LOG = Path("docs/rofl-research/speed-runs.jsonl")

ACCEPT_MIN_SAMPLES = 80
ACCEPT_MIN_HEROES = 5
ACCEPT_MAX_MEDIAN = 120.0
ACCEPT_MAX_P95 = 350.0
ACCEPT_MAX_MAX = 800.0
ORACLE_TOL_S = 0.5
SR_MIN = -200.0
SR_MAX = 16000.0
SR_CENTER_X = 7358
SR_CENTER_Z = 7412

# Wall caps.
MAX_BLOCK_OPS = 8
MAX_BLOCK_SAMPLES = 50
FRAMING_SAMPLES = 8


def keyframe_time(body: bytes) -> Optional[float]:
    if len(body) < 5:
        return None
    return float(struct.unpack_from("<f", body, 1)[0])


def keyframe_header_u8(body: bytes) -> Optional[int]:
    return int(body[0]) if body else None


def inventory_keyframes(rofl: Path) -> dict:
    segs = extract_segments(parse_rofl2(rofl)["payload"])["segments"]
    chunks = [s for s in segs if int(s.get("type") or 0) == 1]
    kfs = [s for s in segs if int(s.get("type") or 0) == 2]
    times: List[float] = []
    sizes: List[int] = []
    headers: Counter = Counter()
    bodies: List[dict] = []
    for s in kfs:
        body = s["bytes"]
        t = keyframe_time(body)
        h = keyframe_header_u8(body)
        if t is None or h is None:
            continue
        times.append(t)
        sizes.append(len(body))
        headers[h] += 1
        bodies.append(
            {
                "id_a": int(s["id_a"]),
                "time": t,
                "size": len(body),
                "headerU8": h,
                "bytes": body,
            }
        )
    bodies.sort(key=lambda r: r["time"])
    dts = [times[i + 1] - times[i] for i in range(len(times) - 1)] if len(times) > 1 else []
    return {
        "chunkCount": len(chunks),
        "keyframeCount": len(bodies),
        "headerU8Counts": {str(k): int(v) for k, v in headers.items()},
        "headerLayout": "u8 | f32_le gameTime (offset 1); observed u8=1 on all keyframes",
        "timeFirst": times[0] if times else None,
        "timeLast": times[-1] if times else None,
        "cadence": {
            "dtMedian": statistics.median(dts) if dts else None,
            "dtMean": statistics.mean(dts) if dts else None,
            "dtMin": min(dts) if dts else None,
            "dtMax": max(dts) if dts else None,
            "note": "~60s keyframe anchors; not a 1Hz native stream",
        },
        "sizeMedian": statistics.median(sizes) if sizes else None,
        "sizeMin": min(sizes) if sizes else None,
        "sizeMax": max(sizes) if sizes else None,
        "bodies": bodies,
    }


def player_blobs(data: bytes) -> List[dict]:
    rows = f1_a8_rows(data)
    runs = contiguous_runs(rows)
    groups = group_runs(runs)
    blobs: List[dict] = []
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
        blobs.append({"index": gi, "start": start, "end": first, "bytes": blob})
    return blobs


def analyze_keyframe_structure(bodies: Sequence[dict]) -> dict:
    if not bodies:
        return {"ok": False, "error": "no keyframes"}
    mid = bodies[len(bodies) // 2]
    data = mid["bytes"]
    blobs = player_blobs(data)
    a8_rows = f1_a8_rows(data)
    net_in_blob = []
    order_ok = 0
    order_n = 0
    for body in bodies:
        bl = player_blobs(body["bytes"])
        if len(bl) != 10:
            continue
        nids = []
        for b in bl:
            found = None
            for nid in PROVEN_HERO_NET_IDS:
                if struct.pack("<I", nid) in b["bytes"]:
                    found = nid
                    break
            nids.append(found)
        if all(nids):
            order_n += 1
            if nids == list(PROVEN_HERO_NET_IDS):
                order_ok += 1
    for b in blobs:
        nids = [nid for nid in PROVEN_HERO_NET_IDS if struct.pack("<I", nid) in b["bytes"]]
        net_in_blob.append({"blobIndex": b["index"], "netIds": [hex(n) for n in nids]})
    return {
        "ok": True,
        "layoutEvidence": [
            "plaintext header u8|f32 time",
            "10 player groups: ~2.0–2.5KB opaque blob + a8 table runs (329 rows/group)",
            "each player blob contains exactly one proven hero netId AE..B7 in order",
        ],
        "midKeyframe": {
            "time": mid["time"],
            "size": mid["size"],
            "a8RowCount": len(a8_rows),
            "playerBlobCount": len(blobs),
            "playerBlobSizes": [len(b["bytes"]) for b in blobs],
            "netIdsPerBlob": net_in_blob,
        },
        "netIdOrderMatchesAE_to_B7": {"matches": order_ok, "keyed": order_n},
        "blockExtractNote": (
            "extract_blocks_py(full keyframe body) yields many ghost channels "
            "(e.g. 491) with no MSVC factory / zero type-1 presence — not native "
            "chunk framing. Native layout is a8/player-blob, not chunk block stream."
        ),
    }


def _f32_map(v: float) -> bool:
    return v == v and SR_MIN <= v <= SR_MAX and abs(v) > 50.0


def map_f32_pairs(data: bytes) -> List[Tuple[int, float, float]]:
    pairs = []
    for off in range(0, len(data) - 7, 4):
        x, z = struct.unpack_from("<ff", data, off)
        if _f32_map(x) and _f32_map(z):
            pairs.append((off, float(x), float(z)))
    return pairs


def nearest_oracle(
    oracle: Sequence[dict], t: float, *, tol_s: float = ORACLE_TOL_S
) -> Optional[Dict[int, Tuple[float, float]]]:
    best = None
    best_dt = 1e9
    for row in oracle:
        dt = abs(float(row["time"]) - t)
        if dt < best_dt:
            best_dt = dt
            best = row
    if best is None or best_dt > tol_s:
        return None
    return {
        int(p["participantID"]): (float(p["x"]), float(p["z"]))
        for p in best["participants"]
    }


def score_errs(errs: Sequence[float], heroes: int) -> dict:
    if not errs:
        return {"n": 0, "heroes": heroes, "ok": False}
    srt = sorted(float(e) for e in errs)
    med = statistics.median(srt)
    p95 = srt[min(len(srt) - 1, int(round(0.95 * (len(srt) - 1))))]
    mx = srt[-1]
    return {
        "n": len(srt),
        "heroes": heroes,
        "median": med,
        "p95": p95,
        "max": mx,
        "ok": (
            len(srt) >= ACCEPT_MIN_SAMPLES
            and heroes >= ACCEPT_MIN_HEROES
            and med <= ACCEPT_MAX_MEDIAN
            and p95 <= ACCEPT_MAX_P95
            and mx <= ACCEPT_MAX_MAX
        ),
    }


def qa_blob_static(bodies: Sequence[dict], oracle: Sequence[dict]) -> dict:
    """Static map-range f32 pairs inside player blobs vs oracle at KF time."""
    train_times = sorted({b["time"] for b in bodies})
    if not train_times:
        return {"ok": False}
    mid = train_times[len(train_times) // 2]

    def run(subset: Sequence[dict], mode: str, swap: bool = False) -> dict:
        errs: List[float] = []
        heroes = set()
        for body in subset:
            pos = nearest_oracle(oracle, float(body["time"]))
            if pos is None:
                continue
            blobs = player_blobs(body["bytes"])
            if len(blobs) != 10:
                continue
            for gi, blob in enumerate(blobs):
                pairs = map_f32_pairs(blob["bytes"])
                if not pairs:
                    continue
                heroes.add(gi + 1)
                if mode == "blob_index":
                    pid = gi + 1
                    if pid not in pos:
                        continue
                    ox, oz = pos[pid]
                    best = 1e18
                    for _, x, z in pairs:
                        xx, zz = (z, x) if swap else (x, z)
                        best = min(best, math.hypot(xx - ox, zz - oz))
                    errs.append(best)
                else:
                    best = 1e18
                    for _, x, z in pairs:
                        xx, zz = (z, x) if swap else (x, z)
                        for ox, oz in pos.values():
                            best = min(best, math.hypot(xx - ox, zz - oz))
                    errs.append(best)
        return score_errs(errs, len(heroes))

    train = [b for b in bodies if b["time"] <= mid]
    hold = [b for b in bodies if b["time"] > mid]
    modes = {}
    for mode in ("blob_index", "nearest"):
        tr = run(train, mode, False)
        ho = run(hold, mode, False)
        tr_s = run(train, mode, True)
        ho_s = run(hold, mode, True)
        use_swap = bool(
            tr_s.get("n", 0) >= 10
            and ho_s.get("n", 0) >= 10
            and (tr_s.get("median") or 1e18) < (tr.get("median") or 1e18)
            and (ho_s.get("median") or 1e18) < (ho.get("median") or 1e18)
        )
        modes[mode] = {
            "swap": use_swap,
            "train": tr_s if use_swap else tr,
            "holdout": ho_s if use_swap else ho,
            "winner": bool(
                (tr_s if use_swap else tr).get("ok")
                and (ho_s if use_swap else ho).get("ok")
            ),
        }
    # i16 near netId (only as structured scan near proven ids — public PathPacket form)
    i16_errs: List[float] = []
    for body in bodies:
        if body["time"] < 60:
            continue
        pos = nearest_oracle(oracle, float(body["time"]))
        if pos is None:
            continue
        data = body["bytes"]
        for nid in PROVEN_HERO_NET_IDS:
            raw = struct.pack("<I", nid)
            j = data.find(raw)
            if j < 0:
                continue
            lo, hi = max(0, j - 128), min(len(data) - 4, j + 128)
            best = 1e18
            for off in range(lo, hi, 2):
                ix, iz = struct.unpack_from("<hh", data, off)
                if abs(ix) < 8 and abs(iz) < 8:
                    continue
                x = float(2 * ix + SR_CENTER_X)
                z = float(2 * iz + SR_CENTER_Z)
                if not (_f32_map(x) and _f32_map(z)):
                    continue
                for ox, oz in pos.values():
                    best = min(best, math.hypot(x - ox, z - oz))
            if best < 1e18:
                i16_errs.append(best)
    return {
        "modes": modes,
        "i16NearNetId": score_errs(i16_errs, 10),
        "mapPairCountTotal": sum(
            len(map_f32_pairs(b["bytes"])) for body in bodies for b in player_blobs(body["bytes"])
        ),
    }


def chunk_modal_wire_sizes(rofl: Path) -> Dict[int, set]:
    out: Dict[int, Counter] = defaultdict(Counter)
    for seg in extract_segments(parse_rofl2(rofl)["payload"])["segments"]:
        if int(seg.get("type") or 0) != 1:
            continue
        for b in extract_blocks_py(seg["bytes"], max_blocks=500_000):
            p = int(b.get("param") or 0)
            if p not in PROVEN_HERO_NET_ID_SET:
                continue
            out[int(b["channel"])][len(b.get("payload") or b"")] += 1
    return {op: {sz for sz, _ in ctr.most_common(5)} for op, ctr in out.items()}


def ghost_channel_report(bodies: Sequence[dict], factories: Mapping[int, Any]) -> dict:
    """Document that naive extract_blocks_py on KF invents non-factory channels."""
    kf_ch: Counter = Counter()
    hero_ch: Counter = Counter()
    for body in bodies:
        for b in extract_blocks_py(body["bytes"], max_blocks=200_000):
            op = int(b["channel"])
            kf_ch[op] += 1
            if int(b.get("param") or 0) in PROVEN_HERO_NET_ID_SET:
                hero_ch[op] += 1
    ghosts = []
    for op, n in hero_ch.most_common(12):
        ghosts.append(
            {
                "opcode": op,
                "heroBlocks": int(n),
                "hasFactory": op in factories and bool(factories[op].get("deserializeVa")),
            }
        )
    return {
        "topHeroChannelsFromExtractBlocksPy": ghosts,
        "dominantGhost491": {
            "heroBlocks": int(hero_ch.get(491, 0)),
            "hasFactory": False,
            "interpretation": "false parse of a8/blob structure; not a real packet type",
        },
    }


def collect_filtered_kf_blocks(
    bodies: Sequence[dict],
    opcodes: Sequence[int],
    modal: Mapping[int, set],
) -> Dict[int, List[dict]]:
    want = set(int(o) for o in opcodes)
    out: Dict[int, List[dict]] = defaultdict(list)
    for body in bodies:
        t = float(body["time"])
        for b in extract_blocks_py(body["bytes"], max_blocks=200_000):
            op = int(b["channel"])
            if op not in want:
                continue
            p = int(b.get("param") or 0)
            if p not in PROVEN_HERO_NET_ID_SET:
                continue
            wsz = len(b.get("payload") or b"")
            allowed = modal.get(op) or set()
            if allowed and wsz not in allowed:
                continue
            out[op].append(
                {"t": t, "param": p, "payload": b.get("payload") or b"", "wireSize": wsz}
            )
    return dict(out)


def framing_check(
    binary: Any, factory: Mapping[str, Any], blocks: Sequence[dict]
) -> dict:
    op = int(factory["opcode"])
    samples = blocks[:FRAMING_SAMPLES]
    best = None
    for marker in (MARKER_1, MARKER_2):
        ok = 0
        raw_ok = 0
        for b in samples:
            for label, body in (("raw", b["payload"]), ("recon", marker + b["payload"])):
                emu = WinX64PacketEmu(binary)
                fr = emu.construct(
                    ctor_va=int(factory["ctorVa"]),
                    object_size=int(factory["objectSize"]),
                    expected_opcode=op,
                    expected_vptr=int(factory["vptr"]),
                )
                if not fr.get("ok"):
                    continue
                r = emu.deserialize(
                    obj=fr["obj"],
                    deser_va=int(factory["deserializeVa"]),
                    payload=body,
                    object_size=int(factory["objectSize"]),
                )
                good = bool(r.get("retAl")) and int(r.get("consumed") or 0) >= int(
                    0.75 * len(body)
                )
                if label == "raw":
                    raw_ok += int(good)
                else:
                    ok += int(good)
        row = {
            "markerHex": marker.hex(),
            "reconOk": ok,
            "rawOk": raw_ok,
            "n": len(samples),
            "validated": ok > raw_ok and ok >= max(1, len(samples) // 2),
            "marker": marker,
        }
        if best is None or row["reconOk"] > best["reconOk"]:
            best = row
    assert best is not None
    return best


def capture_writes(
    binary: Any, factory: Mapping[str, Any], blocks: Sequence[dict], marker: bytes
) -> List[dict]:
    op = int(factory["opcode"])
    osz = max(int(factory["objectSize"]), 64)
    out = []
    for b in blocks:
        emu = WinX64PacketEmu(binary)
        fr = emu.construct(
            ctor_va=int(factory["ctorVa"]),
            object_size=osz,
            expected_opcode=op,
            expected_vptr=int(factory["vptr"]),
        )
        if not fr.get("ok"):
            continue
        obj = int(fr["obj"])
        writes: List[dict] = []

        def on_write(uc: Any, access: int, address: int, size: int, value: int, user: Any) -> None:
            if size == 4:
                f32 = struct.unpack("<f", struct.pack("<I", value & 0xFFFFFFFF))[0]
                if _f32_map(f32):
                    writes.append({"off": int(address - obj), "f": float(f32)})
            elif size == 8:
                raw = struct.pack("<Q", value & 0xFFFFFFFFFFFFFFFF)
                for i, f32 in enumerate(struct.unpack("<ff", raw)):
                    if _f32_map(f32):
                        writes.append(
                            {"off": int(address + 4 * i - obj), "f": float(f32)}
                        )

        h = emu.mu.hook_add(UC_HOOK_MEM_WRITE, on_write)
        r = emu.deserialize(
            obj=obj,
            deser_va=int(factory["deserializeVa"]),
            payload=marker + b["payload"],
            object_size=osz,
        )
        try:
            emu.mu.hook_del(h)
        except Exception:  # noqa: BLE001
            pass
        out.append(
            {
                "t": float(b["t"]),
                "param": int(b["param"]),
                "retAl": int(r.get("retAl") or 0),
                "writes": writes,
            }
        )
    return out


def score_offset_pair(
    caps: Sequence[dict], oracle: Sequence[dict], ox: int, oz: int, *, swap: bool
) -> dict:
    errs = []
    heroes = set()
    for c in caps:
        pos = nearest_oracle(oracle, float(c["t"]))
        if pos is None:
            continue
        by = {int(w["off"]): float(w["f"]) for w in c["writes"]}
        if ox not in by or oz not in by:
            continue
        x, z = by[ox], by[oz]
        if swap:
            x, z = z, x
        heroes.add(int(c["param"]))
        errs.append(min(math.hypot(x - a, z - b) for a, b in pos.values()))
    return score_errs(errs, len(heroes))


def evaluate_block_ops(
    binary: Any,
    factories: Mapping[int, Any],
    blocks_by_op: Mapping[int, List[dict]],
    oracle: Sequence[dict],
) -> List[dict]:
    ranked_ops = sorted(
        blocks_by_op.keys(),
        key=lambda op: -len({r["param"] for r in blocks_by_op[op]}),
    )[:MAX_BLOCK_OPS]
    results = []
    for op in ranked_ops:
        fac = factories.get(op)
        if not fac or not fac.get("deserializeVa"):
            continue
        fac = {**fac, "opcode": op}
        rows = blocks_by_op[op]
        # diversify
        by = defaultdict(list)
        for r in rows:
            by[(round(r["t"], 2), r["param"])].append(r)
        uniq = [v[0] for v in by.values()]
        uniq.sort(key=lambda r: r["t"])
        if len(uniq) < 8:
            continue
        fr = framing_check(binary, fac, uniq)
        fr_pub = {k: v for k, v in fr.items() if k != "marker"}
        if not fr["validated"]:
            results.append(
                {
                    "opcode": op,
                    "samples": len(uniq),
                    "heroes": len({r["param"] for r in uniq}),
                    "framing": fr_pub,
                    "skipped": "framing_invalid",
                }
            )
            continue
        mid_t = sorted({r["t"] for r in uniq})[len({r["t"] for r in uniq}) // 2]
        train = [r for r in uniq if r["t"] <= mid_t][:MAX_BLOCK_SAMPLES]
        hold = [r for r in uniq if r["t"] > mid_t][:MAX_BLOCK_SAMPLES]
        caps_tr = capture_writes(binary, fac, train, fr["marker"])
        caps_ho = capture_writes(binary, fac, hold, fr["marker"])
        # rank pairs on train
        pair_errs: Dict[Tuple[int, int], List[float]] = defaultdict(list)
        for c in caps_tr:
            pos = nearest_oracle(oracle, float(c["t"]))
            if pos is None:
                continue
            by_off = {
                int(w["off"]): float(w["f"])
                for w in c["writes"]
                if 0 <= int(w["off"]) <= 128
            }
            offs = sorted(by_off)
            for i, a in enumerate(offs):
                for b in offs[i + 1 : i + 4]:
                    if b - a > 16:
                        break
                    d = min(
                        math.hypot(by_off[a] - ox, by_off[b] - oz)
                        for ox, oz in pos.values()
                    )
                    pair_errs[(a, b)].append(d)
        if not pair_errs:
            results.append(
                {
                    "opcode": op,
                    "samples": len(uniq),
                    "heroes": len({r["param"] for r in uniq}),
                    "framing": fr_pub,
                    "mapWrites": sum(len(c["writes"]) for c in caps_tr + caps_ho),
                    "skipped": "no_map_pairs",
                }
            )
            continue
        (ox, oz), _ = min(pair_errs.items(), key=lambda kv: statistics.median(kv[1]))
        tr = score_offset_pair(caps_tr, oracle, ox, oz, swap=False)
        ho = score_offset_pair(caps_ho, oracle, ox, oz, swap=False)
        tr_s = score_offset_pair(caps_tr, oracle, ox, oz, swap=True)
        ho_s = score_offset_pair(caps_ho, oracle, ox, oz, swap=True)
        use_swap = bool(
            tr_s.get("n", 0) >= 5
            and ho_s.get("n", 0) >= 5
            and (tr_s.get("median") or 1e18) < (tr.get("median") or 1e18)
            and (ho_s.get("median") or 1e18) < (ho.get("median") or 1e18)
        )
        train_sc = tr_s if use_swap else tr
        hold_sc = ho_s if use_swap else ho
        results.append(
            {
                "opcode": op,
                "samples": len(uniq),
                "heroes": len({r["param"] for r in uniq}),
                "framing": fr_pub,
                "offX": ox,
                "offZ": oz,
                "swap": use_swap,
                "train": train_sc,
                "holdout": hold_sc,
                "winner": bool(train_sc.get("ok") and hold_sc.get("ok")),
                "encodeTypeHex": encode_type(op).hex(),
            }
        )
    return results


def classify_blocker(
    *,
    structure: Mapping[str, Any],
    blob_qa: Mapping[str, Any],
    block_evals: Sequence[dict],
    ghost: Mapping[str, Any],
) -> dict:
    floats = int(blob_qa.get("mapPairCountTotal") or 0)
    blob_win = any(
        (m.get("winner") for m in (blob_qa.get("modes") or {}).values())
    )
    block_win = any(r.get("winner") for r in block_evals)
    if not structure.get("ok"):
        return {
            "kind": "keyframes_opaque",
            "detail": "could not establish keyframe layout evidence",
        }
    if floats == 0 and not any(
        int((r.get("train") or {}).get("n") or 0) > 0 for r in block_evals
    ):
        return {
            "kind": "keyframes_no_map_floats",
            "detail": "no map-range f32 pairs in player blobs or filtered block captures",
        }
    if not blob_win and not block_win:
        best = None
        for mode, row in (blob_qa.get("modes") or {}).items():
            ho = row.get("holdout") or {}
            if ho.get("median") is None:
                continue
            if best is None or ho["median"] < best["median"]:
                best = {"source": f"blob:{mode}", **ho}
        for r in block_evals:
            ho = r.get("holdout") or {}
            if ho.get("median") is None:
                continue
            if best is None or ho["median"] < best["median"]:
                best = {
                    "source": f"block:{r.get('opcode')}",
                    "offX": r.get("offX"),
                    "offZ": r.get("offZ"),
                    **ho,
                }
        return {
            "kind": "keyframes_floats_not_oracle_positions",
            "detail": (
                "keyframe layout is a8/player-blobs (~60s); map-range floats exist but "
                "fail Replay API gates; extract_blocks_py ghost channels "
                f"(e.g. 491 n={ghost.get('dominantGhost491', {}).get('heroBlocks')}) "
                "are not real factories — framing differs from type-1 chunks"
            ),
            "bestNearMiss": best,
            "framingDiffersFromChunks": True,
        }
    return {"kind": "none", "detail": "winner found"}


def run_e13(
    *,
    pe_path: Path,
    rofl: Path,
    oracle_jsonl: Path,
    report_path: Path,
    dry_run: bool = False,
) -> dict:
    t0 = time.perf_counter()
    inv = inventory_keyframes(rofl)
    bodies = inv.pop("bodies")
    structure = analyze_keyframe_structure(bodies)
    oracle = _load_oracle_positions(oracle_jsonl)
    blob_qa = qa_blob_static(bodies, oracle)

    binary = load_binary(pe_path)
    prov = official_provenance(size=pe_path.stat().st_size, sha256=binary.sha256)
    man = research_manifest(
        binary, patch="16.14", extra={"probeVersion": PROBE_VERSION, "official": prov}
    )
    counts, _ = enumerate_rofl(rofl)
    rows, coverage = scan_msvc_packet_types(binary, counts)
    factories = {int(r["opcode"]): r for r in rows}

    ghost = ghost_channel_report(bodies, factories)
    modal = chunk_modal_wire_sizes(rofl)
    # Prefer ops that appear in KF ghost hero list AND have factories + chunk modals.
    candidate_ops = []
    for row in ghost.get("topHeroChannelsFromExtractBlocksPy") or []:
        op = int(row["opcode"])
        if row.get("hasFactory") and op in modal:
            candidate_ops.append(op)
    for op in (908, 130, 197, 921, 774, 210, 636, 282):
        if op not in candidate_ops and op in factories and op in modal:
            candidate_ops.append(op)
    blocks_by_op = collect_filtered_kf_blocks(bodies, candidate_ops, modal)
    block_evals = evaluate_block_ops(binary, factories, blocks_by_op, oracle)

    winner = None
    for mode, row in (blob_qa.get("modes") or {}).items():
        if row.get("winner"):
            winner = {
                "source": f"player_blob_static:{mode}",
                "cadence": "~60s keyframe",
                "train": row.get("train"),
                "holdout": row.get("holdout"),
                "swap": row.get("swap"),
            }
            break
    if winner is None:
        for r in block_evals:
            if r.get("winner"):
                winner = {
                    "source": "filtered_keyframe_block_deserialize",
                    "opcode": r["opcode"],
                    "offX": r.get("offX"),
                    "offZ": r.get("offZ"),
                    "swap": r.get("swap"),
                    "cadence": "~60s keyframe",
                    "train": r.get("train"),
                    "holdout": r.get("holdout"),
                }
                break

    blocker = classify_blocker(
        structure=structure, blob_qa=blob_qa, block_evals=block_evals, ghost=ghost
    )
    wall_ms = (time.perf_counter() - t0) * 1000.0

    report = {
        "ok": bool(winner),
        "probeVersion": PROBE_VERSION,
        "hypothesis": "phase-b-e13-keyframe-positions",
        "matchCode": MATCH_CODE,
        "wallMs": round(wall_ms, 3),
        "wallTargetMs": 60_000,
        "wallPass": wall_ms <= 60_000,
        "official": prov,
        "binaryManifest": man,
        "constructorCoverage": coverage,
        "inventory": inv,
        "structure": structure,
        "ghostBlockExtract": ghost,
        "blobStaticQa": {
            "modes": blob_qa.get("modes"),
            "i16NearNetId": blob_qa.get("i16NearNetId"),
            "mapPairCountTotal": blob_qa.get("mapPairCountTotal"),
        },
        "filteredBlockEvals": block_evals,
        "evaluation": {
            "winnerFound": bool(winner),
            "winner": winner,
            "gates": {
                "minSamples": ACCEPT_MIN_SAMPLES,
                "minHeroes": ACCEPT_MIN_HEROES,
                "maxMedian": ACCEPT_MAX_MEDIAN,
                "maxP95": ACCEPT_MAX_P95,
                "maxMax": ACCEPT_MAX_MAX,
                "oracleTolS": ORACLE_TOL_S,
            },
            "cadenceHonesty": (
                "Positions — if present — would be ~60s keyframe anchors only; "
                "native continuous/1Hz stream remains open. Product would need "
                "keyframe anchors + movement deltas or Replay API backup."
            ),
        },
        "blocker": blocker,
        "pureDecoderDerived": False,
        "browserSafe": False,
        "productEligible": False,
        "identity": {
            "createHeroBindingDecoded": False,
            "productEligible": False,
            "note": "blob netId order AE..B7 is structural, not CreateHero/PUUID product bind",
        },
    }

    keep = "keep" if winner else "discard"
    reason = (
        f"E13 winner {winner['source']}"
        if winner
        else f"E13 blocker={blocker['kind']}: {str(blocker.get('detail') or '')[:180]}"
    )
    if not dry_run:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        append_speed_record(
            log=SPEED_LOG,
            hypothesis="phase-b-e13-keyframe-positions",
            diff_label="e13-keyframe-positions",
            keep=keep,
            reason=reason,
            wall_ms=wall_ms,
            match_code=MATCH_CODE,
            extra={
                "decoderVersion": PROBE_VERSION,
                "winnerFound": bool(winner),
                "winner": winner,
                "blocker": blocker,
                "browserSafe": False,
                "productEligible": False,
                "pureDecoderDerived": False,
                "keyframeCount": inv.get("keyframeCount"),
                "cadenceMedian": (inv.get("cadence") or {}).get("dtMedian"),
            },
        )
    return report


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pe", type=Path, default=DEFAULT_PE)
    ap.add_argument("--rofl", type=Path, default=DEFAULT_ROFL)
    ap.add_argument("--oracle", type=Path, default=DEFAULT_ORACLE)
    ap.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    report = run_e13(
        pe_path=args.pe,
        rofl=args.rofl,
        oracle_jsonl=args.oracle,
        report_path=args.report,
        dry_run=args.dry_run,
    )
    print(
        json.dumps(
            {
                "ok": report.get("ok"),
                "wallMs": report.get("wallMs"),
                "winnerFound": (report.get("evaluation") or {}).get("winnerFound"),
                "winner": (report.get("evaluation") or {}).get("winner"),
                "blocker": report.get("blocker"),
                "inventory": {
                    k: (report.get("inventory") or {}).get(k)
                    for k in (
                        "keyframeCount",
                        "chunkCount",
                        "headerLayout",
                        "cadence",
                        "sizeMedian",
                    )
                },
                "browserSafe": report.get("browserSafe"),
                "productEligible": report.get("productEligible"),
                "report": str(args.report),
            },
            indent=2,
        )
    )
    return 0 if report.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
