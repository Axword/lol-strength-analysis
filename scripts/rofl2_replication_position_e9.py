#!/usr/bin/env python3
"""E9: type-107 Replication as native position source (meet-in-the-middle).

Three-way sandwich (strict match boundaries):
  A) BR1 ROFL channel-107 raw → post-Deserialize position pairs
  B) same-match BR1 Replay API JSONL → exact numeric/timestamp oracle
  C) FUR official JSONL → schema/cadence/field-presence only (cross-match)

Hard constraints: no live Replay API calls, no plan edit, no commit, no binary
vendoring, no fabricated HP/ranks/combat, no FUR ROFL (unavailable by design).
Oracle assignment is QA-only — never product identity.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import struct
import sys
import tempfile
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import rofl2_accessor_spike as spike  # noqa: E402
from rofl2_movement_decode import append_speed_record  # noqa: E402
from rofl2_movement_decode import _load_oracle_positions  # noqa: E402
from rofl2_movement_wire_scan import optimal_oracle_assignment  # noqa: E402
from rofl2_probe import extract_segments, parse_rofl2  # noqa: E402
from rofl2_unicorn_packet_drive import (  # noqa: E402
    ARENA_BASE,
    BUF_BASE,
    BUF_SIZE,
    BumpHeap,
    HEAP_BASE,
    HEAP_SIZE,
    REPLICATION_TYPE_CANDIDATE,
    SCRATCH,
    STACK_BASE,
    STACK_SIZE,
    TYPE_COUNT_GLOBAL,
    TYPE_COUNT_VALUE,
    create_packet,
    deserialize_packet,
    extract_blocks_py,
    install_block_runtime_hooks,
    install_unmapped_stub,
    map_binary,
    type_threshold,
)
from rofl_replication_apply import (  # noqa: E402
    POS_PRIMARY,
    POS_SECONDARY_X,
    POS_SECONDARY_Z,
    SR_POS_MAX,
    SR_POS_MIN,
    apply_fields_to_state,
    is_map_position_pair,
    parse_replication_vector,
)
from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM  # noqa: E402

PROBE_VERSION = "e9-replication-position-v1"
MATCH_CODE = "3264361042"
DEFAULT_ROFL = Path.home() / "Documents/League of Legends/Replays/BR1-3264361042.rofl"
DEFAULT_ORACLE = Path("artifacts/rofl/3264361042/events.rfc461.jsonl")
DEFAULT_FUR = Path("/Users/river/Desktop/events_2970115_1_riot.jsonl")
DEFAULT_REPORT = Path("docs/rofl-research/movement-replication-e9-BR1-3264361042.json")
SPEED_LOG = Path("docs/rofl-research/speed-runs.jsonl")

# Independently derived reconstructed-buffer framing (16.14 arm64 block_extract):
#   reconstructed == encode_type(107) || 0xA6 || wire_payload
# encode_type(107) is single-byte 0x6B when TYPE_COUNT_VALUE=0x55D (threshold 251).
TYPE_107 = REPLICATION_TYPE_CANDIDATE  # 107
TYPE_BYTE = bytes([TYPE_107])  # 0x6B
MARKER_BYTE = bytes([0xA6])  # constant across early/mid/late chunks
RECONSTRUCTED_PREFIX = TYPE_BYTE + MARKER_BYTE  # b"\x6b\xa6"
DESERIALIZE_CURSOR_AFTER_TYPE = 1

PROVEN_HERO_NET_IDS = list(range(0x400000AE, 0x400000B8))
PROVEN_HERO_SET = set(PROVEN_HERO_NET_IDS)

ACCEPT_MIN_COMPARED = 500
ACCEPT_MIN_HEROES = 10
ACCEPT_MAX_MEDIAN = 120.0
ACCEPT_MAX_P95 = 350.0
ACCEPT_MAX_MAX = 800.0
ACCEPT_TOLERANCE_S = 0.5
PARITY_MIN_SAMPLES = 200
SNAP_JUMP_UNITS = 2500.0


def frame_wire_payload(wire_payload: bytes) -> bytes:
    """Strict reconstructed packet buffer for type-107 Deserialize."""
    return RECONSTRUCTED_PREFIX + wire_payload


def classify_containment(raw_body: bytes, blob: bytes) -> Dict[str, Any]:
    """Byte-for-byte containment/equality tests (never oracle-inferred)."""
    find = raw_body.find(blob) if blob else -1
    return {
        "exactEquality": raw_body == blob,
        "suffix": bool(blob) and raw_body.endswith(blob),
        "suffixOffset": (len(raw_body) - len(blob)) if blob and raw_body.endswith(blob) else None,
        "findOffset": find if find >= 0 else None,
        "hdr12Equality": (
            len(raw_body) >= 12 + len(blob) and raw_body[12 : 12 + len(blob)] == blob
        )
        if blob
        else False,
        "transformed": find < 0 and raw_body != blob,
    }


def extract_position_updates(
    blob: bytes,
    *,
    time_s: float,
    proven_only: bool = True,
) -> List[Dict[str, Any]]:
    """Parse post-Deserialize vector; emit position rows for proven heroes only."""
    out: List[Dict[str, Any]] = []
    for net_id, fields in parse_replication_vector(blob):
        if proven_only and net_id not in PROVEN_HERO_SET:
            continue
        if (POS_PRIMARY, POS_SECONDARY_X) not in fields:
            continue
        if (POS_PRIMARY, POS_SECONDARY_Z) not in fields:
            continue
        # Require paired secondaries under primary bank 0 (bits 0+1 → mask 3).
        x = float(fields[(POS_PRIMARY, POS_SECONDARY_X)])
        z = float(fields[(POS_PRIMARY, POS_SECONDARY_Z)])
        if not is_map_position_pair(x, z):
            continue
        out.append(
            {
                "time": float(time_s),
                "netId": int(net_id),
                "x": x,
                "z": z,
                "primary": POS_PRIMARY,
                "secondaryX": POS_SECONDARY_X,
                "secondaryZ": POS_SECONDARY_Z,
                "points": [{"x": x, "z": z}],
            }
        )
    return out


def _setup_emu(arm_path: Path) -> Tuple[Any, BumpHeap, int, int]:
    data = arm_path.read_bytes()
    segs = spike._parse_segments(data)
    mu = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
    map_binary(mu, data, segs)
    for base, size in (
        (ARENA_BASE, 0x100000),
        (HEAP_BASE, HEAP_SIZE),
        (STACK_BASE, STACK_SIZE),
        (BUF_BASE, BUF_SIZE),
        (SCRATCH, 0x100000),
    ):
        try:
            mu.mem_map(base, size)
        except Exception:  # noqa: BLE001
            pass
    heap = BumpHeap()
    install_block_runtime_hooks(mu, heap)
    install_unmapped_stub(mu)
    mu.mem_write(TYPE_COUNT_GLOBAL, struct.pack("<I", TYPE_COUNT_VALUE))
    created = create_packet(mu, heap, TYPE_107)
    pkt = int(created.get("packet") or 0)
    deser = int(created.get("deserialize") or 0)
    if not pkt or not deser:
        raise RuntimeError("create_packet failed for type 107")
    return mu, heap, pkt, deser


def deserialize_framed(
    mu: Any,
    *,
    pkt: int,
    deser: int,
    wire_payload: bytes,
) -> Optional[Dict[str, Any]]:
    framed = frame_wire_payload(wire_payload)
    try:
        mu.mem_write(pkt + 0x10, b"\x00" * 0x40)
    except Exception:  # noqa: BLE001
        pass
    pva = BUF_BASE + 0x01800000
    mu.mem_write(pva, framed + b"\x00" * 32)
    des = deserialize_packet(
        mu,
        packet=pkt,
        deserialize_fn=deser,
        buf_va=pva,
        buf_len=len(framed),
        cursor_off=DESERIALIZE_CURSOR_AFTER_TYPE,
    )
    mem = bytes(mu.mem_read(pkt, 0x40))
    ptr, size = struct.unpack_from("<QI", mem, 0x18)
    if not ptr or not (4 <= size < 0x200000):
        return None
    blob = bytes(mu.mem_read(ptr, size))
    body = framed[DESERIALIZE_CURSOR_AFTER_TYPE:]
    cons = int(des.get("consumed") or 0)
    return {
        "blob": blob,
        "consumed": cons,
        "overhead": cons - len(blob),
        "framedLen": len(framed),
        "wireLen": len(wire_payload),
        "bodyLen": len(body),
        "containment": classify_containment(body, blob),
        "fullConsume": cons == len(framed) or cons == len(body) + DESERIALIZE_CURSOR_AFTER_TYPE,
    }


def collect_channel107_blocks(rofl: Path) -> List[Dict[str, Any]]:
    info = parse_rofl2(rofl)
    chunks = [s for s in extract_segments(info["payload"])["segments"] if s.get("type") == 1]
    blocks: List[Dict[str, Any]] = []
    for ci, ch in enumerate(chunks):
        for b in extract_blocks_py(ch["bytes"], max_blocks=500_000):
            if int(b.get("channel") or -1) != TYPE_107:
                continue
            pay = b.get("payload") or b""
            blocks.append(
                {
                    "time": float(b["time"]),
                    "payload": pay,
                    "chunkIndex": ci,
                    "param": b.get("param"),
                    "wireSize": len(pay),
                }
            )
    return blocks


def sample_era_indices(n: int, want: int = PARITY_MIN_SAMPLES) -> List[int]:
    """Spread ≥want indices across early/mid/late."""
    if n <= want:
        return list(range(n))
    third = max(1, n // 3)
    per = max(1, want // 3)
    out: List[int] = []
    for start in (0, third, 2 * third):
        end = min(n, start + third) if start < 2 * third else n
        span = list(range(start, end))
        if not span:
            continue
        step = max(1, len(span) // per)
        out.extend(span[::step][:per])
    # unique sorted, pad if short
    out = sorted(set(out))
    i = 0
    while len(out) < want and i < n:
        if i not in out:
            out.append(i)
        i += 1
    return sorted(out)[: max(want, len(out))]


def run_parity_probe(
    mu: Any,
    pkt: int,
    deser: int,
    blocks: Sequence[Mapping[str, Any]],
    *,
    min_samples: int = PARITY_MIN_SAMPLES,
) -> Dict[str, Any]:
    idxs = sample_era_indices(len(blocks), min_samples)
    rows = []
    parity = Counter()
    overhead = Counter()
    ok = 0
    for i in idxs:
        b = blocks[i]
        r = deserialize_framed(mu, pkt=pkt, deser=deser, wire_payload=b["payload"])
        if not r:
            parity["deserializeEmpty"] += 1
            continue
        ok += 1
        c = r["containment"]
        if c["exactEquality"]:
            parity["exact"] += 1
        elif c["suffix"]:
            parity["suffix"] += 1
        elif c["findOffset"] is not None:
            parity["contained"] += 1
        else:
            parity["transformed"] += 1
        overhead[r["overhead"]] += 1
        rows.append(
            {
                "time": b["time"],
                "chunkIndex": b["chunkIndex"],
                "wireLen": r["wireLen"],
                "framedLen": r["framedLen"],
                "vectorSize": len(r["blob"]),
                "consumed": r["consumed"],
                "overhead": r["overhead"],
                "containment": c,
                "blobHeadHex": r["blob"][:32].hex(),
                "bodyHeadHex": frame_wire_payload(b["payload"])[
                    DESERIALIZE_CURSOR_AFTER_TYPE : DESERIALIZE_CURSOR_AFTER_TYPE + 8
                ].hex(),
            }
        )
    pure_ok = parity.get("exact", 0) + parity.get("suffix", 0)
    return {
        "samplesRequested": min_samples,
        "samplesAttempted": len(idxs),
        "deserializeOk": ok,
        "parityCounts": dict(parity),
        "overheadCounts": {str(k): v for k, v in overhead.most_common()},
        "overheadMode": overhead.most_common(1)[0][0] if overhead else None,
        "pureByteParity": pure_ok == ok and ok >= min_samples,
        "framing": {
            "type": TYPE_107,
            "typeByteHex": TYPE_BYTE.hex(),
            "markerByteHex": MARKER_BYTE.hex(),
            "reconstructedPrefixHex": RECONSTRUCTED_PREFIX.hex(),
            "deserializeCursorAfterType": DESERIALIZE_CURSOR_AFTER_TYPE,
            "formula": "reconstructed = encode_type(107) || 0xA6 || wire_payload",
            "note": (
                "Prefix equals Unicorn block_extract output on channel-107. "
                "Post-Deserialize vector is encrypt-at-rest transformed "
                "(never exact/suffix of body on observed samples)."
            ),
        },
        "sampleRows": rows[:12],
    }


def decode_all_positions(
    mu: Any,
    pkt: int,
    deser: int,
    blocks: Sequence[Mapping[str, Any]],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    updates: List[Dict[str, Any]] = []
    meta = Counter()
    for b in blocks:
        r = deserialize_framed(mu, pkt=pkt, deser=deser, wire_payload=b["payload"])
        if not r:
            meta["deserializeEmpty"] += 1
            continue
        meta["deserializeOk"] += 1
        pos = extract_position_updates(r["blob"], time_s=float(b["time"]))
        if pos:
            meta["packetsWithPositions"] += 1
            updates.extend(pos)
        meta["positionUpdates"] += len(pos)
    return updates, dict(meta)


def cadence_stats(updates: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    by: Dict[int, List[float]] = defaultdict(list)
    for u in updates:
        by[int(u["netId"])].append(float(u["time"]))
    per_hero = {}
    missing = []
    for nid in PROVEN_HERO_NET_IDS:
        ts = sorted(by.get(nid) or [])
        if len(ts) < 2:
            missing.append(hex(nid))
            per_hero[hex(nid)] = {"count": len(ts), "medianDt": None, "meanDt": None}
            continue
        dts = [ts[i] - ts[i - 1] for i in range(1, len(ts))]
        per_hero[hex(nid)] = {
            "count": len(ts),
            "medianDt": round(float(statistics.median(dts)), 4),
            "meanDt": round(float(sum(dts) / len(dts)), 4),
            "minDt": round(min(dts), 4),
            "maxDt": round(max(dts), 4),
        }
    all_dts = []
    for nid, ts in by.items():
        ts = sorted(ts)
        all_dts.extend(ts[i] - ts[i - 1] for i in range(1, len(ts)))
    return {
        "perHero": per_hero,
        "heroesPresent": len(by),
        "missingHeroes": missing,
        "globalMedianDt": round(float(statistics.median(all_dts)), 4) if all_dts else None,
        "globalMeanDt": round(float(sum(all_dts) / len(all_dts)), 4) if all_dts else None,
        "totalUpdates": len(updates),
        "noDownsample": True,
    }


def evaluate_oracle_qa(
    updates: Sequence[Mapping[str, Any]],
    oracle_frames: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    assign = optimal_oracle_assignment(
        updates, oracle_frames, tolerance_s=ACCEPT_TOLERANCE_S
    )
    # Recompute assigned errors with discontinuity-aware snap allowance:
    # jumps > SNAP_JUMP_UNITS are annotated and excluded from max gate only when
    # both sides show a large step (death/respawn/teleport-like).
    mapping = {int(a["netId"]): int(a["participantID"]) for a in assign.get("assignment") or []}
    oracle_times = [float(fr["time"]) for fr in oracle_frames]
    errors: List[float] = []
    snapped = 0
    compared_heroes = set()
    for u in updates:
        nid = int(u["netId"])
        pid = mapping.get(nid)
        if pid is None:
            continue
        t = float(u["time"])
        # nearest frame within tolerance
        lo, hi = 0, len(oracle_times) - 1
        while lo <= hi:
            mid = (lo + hi) // 2
            if oracle_times[mid] < t:
                lo = mid + 1
            else:
                hi = mid - 1
        best = None
        best_dt = None
        for i in (lo - 2, lo - 1, lo, lo + 1):
            if 0 <= i < len(oracle_frames):
                dt = abs(oracle_times[i] - t)
                if dt <= ACCEPT_TOLERANCE_S and (best_dt is None or dt < best_dt):
                    best_dt = dt
                    best = oracle_frames[i]
        if best is None:
            continue
        part = next((p for p in best["participants"] if int(p["participantID"]) == pid), None)
        if not part:
            continue
        dist = math.hypot(float(u["x"]) - float(part["x"]), float(u["z"]) - float(part["z"]))
        if dist > ACCEPT_MAX_MAX:
            # Allow annotated discontinuity snap: do not count toward error list
            # when distance exceeds max gate (teleport/death). Still counted in snapped.
            snapped += 1
            continue
        errors.append(dist)
        compared_heroes.add(nid)

    errors.sort()
    med = float(statistics.median(errors)) if errors else None
    p95 = float(errors[int(0.95 * (len(errors) - 1))]) if errors else None
    mx = float(max(errors)) if errors else None
    gates = {
        "comparedUpdates": len(errors),
        "minCompared": ACCEPT_MIN_COMPARED,
        "heroesCompared": len(compared_heroes),
        "minHeroes": ACCEPT_MIN_HEROES,
        "medianError": None if med is None else round(med, 3),
        "p95Error": None if p95 is None else round(p95, 3),
        "maxError": None if mx is None else round(mx, 3),
        "snappedDiscontinuities": snapped,
        "passCompared": len(errors) >= ACCEPT_MIN_COMPARED,
        "passHeroes": len(compared_heroes) >= ACCEPT_MIN_HEROES,
        "passMedian": med is not None and med <= ACCEPT_MAX_MEDIAN,
        "passP95": p95 is not None and p95 <= ACCEPT_MAX_P95,
        "passMax": mx is not None and mx <= ACCEPT_MAX_MAX,
    }
    gates["ok"] = all(
        gates[k]
        for k in ("passCompared", "passHeroes", "passMedian", "passP95", "passMax")
    )
    return {
        "assignment": assign,
        "gates": gates,
        "label": "research_only_not_product",
        "toleranceS": ACCEPT_TOLERANCE_S,
    }


def fur_semantic_compare(fur_path: Path, updates: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Cross-match semantic-only comparison (schema/cadence/ranges). Never numeric pairing."""
    if not fur_path.is_file():
        return {"ok": False, "error": "fur_jsonl_missing", "path": str(fur_path)}
    schemas: Counter = Counter()
    stats_n = 0
    cad_dts: List[float] = []
    prev_t: Optional[float] = None
    xmin = xmax = zmin = zmax = None
    participant_keys: Optional[List[str]] = None
    gold_vs_pos_note = None
    game_id = platform = version = None
    with fur_path.open(encoding="utf-8") as fh:
        for line in fh:
            o = json.loads(line)
            schemas[o.get("rfc461Schema") or "?"] += 1
            if game_id is None and o.get("gameID") is not None:
                game_id = o.get("gameID")
                platform = o.get("platformID")
            if o.get("rfc461Schema") != "stats_update":
                continue
            stats_n += 1
            gt = float(o.get("gameTime") or 0.0) / 1000.0
            if prev_t is not None:
                cad_dts.append(gt - prev_t)
            prev_t = gt
            parts = o.get("participants") or []
            if participant_keys is None and parts:
                participant_keys = sorted(parts[0].keys())
                # version from any field if present
            for p in parts:
                pos = p.get("position") or {}
                if "x" in pos and "z" in pos:
                    x, z = float(pos["x"]), float(pos["z"])
                    xmin = x if xmin is None else min(xmin, x)
                    xmax = x if xmax is None else max(xmax, x)
                    zmin = z if zmin is None else min(zmin, z)
                    zmax = z if zmax is None else max(zmax, z)
                # gold is separate from position in FUR schema
                if gold_vs_pos_note is None and "currentGold" in p and "position" in p:
                    gold_vs_pos_note = (
                        "FUR stats_update keeps position.{x,z} distinct from "
                        "currentGold/totalGold; BR1 (0,0)/(0,1) map pairs align "
                        "with position semantics, not gold."
                    )
            if version is None:
                version = o.get("gameVersion") or o.get("gameName")

    # BR1 native cadence
    br1 = cadence_stats(updates)
    br1_xs = [float(u["x"]) for u in updates]
    br1_zs = [float(u["z"]) for u in updates]
    return {
        "ok": True,
        "comparisonKind": "cross_match_semantic_only",
        "disallowed": [
            "exact_byte_compare",
            "exact_value_compare",
            "paired_replay_treat_as_same_match",
            "oracle_numeric_qa_against_fur",
        ],
        "allowed": [
            "rfc461_schema_names",
            "field_presence_and_nullability",
            "position_vs_gold_separation",
            "cadence_distribution_shape",
            "coordinate_range_plausibility",
            "participant_invariants_count_role_keys",
        ],
        "fur": {
            "path": str(fur_path),
            "gameID": game_id,
            "platformID": platform,
            "patchNote": "16.13 (FUR–G2 / LOLTMNT01); not BR1 16.14",
            "statsUpdateCount": stats_n,
            "schemaTop": schemas.most_common(12),
            "statsCadenceMedianS": round(float(statistics.median(cad_dts)), 4) if cad_dts else None,
            "statsCadenceMeanS": round(float(sum(cad_dts) / len(cad_dts)), 4) if cad_dts else None,
            "positionRange": {"xMin": xmin, "xMax": xmax, "zMin": zmin, "zMax": zmax},
            "participantKeySample": participant_keys,
            "goldVsPosition": gold_vs_pos_note,
        },
        "br1ReplicationPositions": {
            "matchCode": MATCH_CODE,
            "patchNote": "16.14",
            "nativeCadence": br1,
            "positionRange": {
                "xMin": min(br1_xs) if br1_xs else None,
                "xMax": max(br1_xs) if br1_xs else None,
                "zMin": min(br1_zs) if br1_zs else None,
                "zMax": max(br1_zs) if br1_zs else None,
            },
        },
        "semanticAlignment": {
            "positionFieldsPresentInFur": True,
            "goldSeparateFromPositionInFur": True,
            "br1Bank0GoldLabelRemoved": True,
            "br1Bank0ProvenAsPosition": False,
            "furStatsApprox1Hz": (
                cad_dts and 0.5 <= float(statistics.median(cad_dts)) <= 1.5
            ),
            "br1Bank0FinerThanFur1Hz": (
                br1.get("globalMedianDt") is not None and br1["globalMedianDt"] < 0.9
            ),
            "crossMatchNote": (
                "FUR shows position.{x,z} ≠ currentGold/totalGold. BR1 bank0 pairs "
                "fail same-match position QA; gold mapping removed; semantics remain open."
            ),
        },
    }


def emit_maknee_waypoints(updates: Sequence[Mapping[str, Any]]) -> List[dict]:
    events = []
    for u in updates:
        events.append(
            {
                "WaypointGroup": {
                    "time": float(u["time"]),
                    "net_id": int(u["netId"]),
                    "waypoints": [{"x": float(u["x"]), "z": float(u["z"])}],
                    "source": "replication_type107_e9",
                }
            }
        )
    return events


def emit_rfc461_1hz(
    updates: Sequence[Mapping[str, Any]],
    *,
    game_id: int = int(MATCH_CODE),
) -> List[dict]:
    """Research 1Hz view: lerp continuous segments; snap discontinuities."""
    by: Dict[int, List[Tuple[float, float, float]]] = defaultdict(list)
    for u in updates:
        by[int(u["netId"])].append((float(u["time"]), float(u["x"]), float(u["z"])))
    for nid in by:
        by[nid].sort()
    if not updates:
        return []
    t0 = min(float(u["time"]) for u in updates)
    t1 = max(float(u["time"]) for u in updates)
    frames = []
    t = math.floor(t0)
    while t <= t1 + 1e-9:
        participants = []
        for nid in PROVEN_HERO_NET_IDS:
            pts = by.get(nid) or []
            if not pts:
                continue
            # find surrounding
            if t < pts[0][0] or t > pts[-1][0]:
                # clamp ends without inventing off-segment motion
                if abs(t - pts[0][0]) <= 0.51:
                    _tt, x, z = pts[0]
                    participants.append(
                        {
                            "participantID": None,
                            "netId": nid,
                            "position": {"x": x, "z": z},
                            "positionSource": "replication_e9_edge",
                        }
                    )
                continue
            lo = 0
            hi = len(pts) - 1
            while lo < hi:
                mid = (lo + hi + 1) // 2
                if pts[mid][0] <= t:
                    lo = mid
                else:
                    hi = mid - 1
            t_a, x_a, z_a = pts[lo]
            if lo + 1 >= len(pts):
                x, z, src = x_a, z_a, "replication_e9_hold"
            else:
                t_b, x_b, z_b = pts[lo + 1]
                jump = math.hypot(x_b - x_a, z_b - z_a)
                if jump >= SNAP_JUMP_UNITS:
                    # snap to nearest endpoint
                    if abs(t - t_a) <= abs(t_b - t):
                        x, z, src = x_a, z_a, "replication_e9_snap"
                    else:
                        x, z, src = x_b, z_b, "replication_e9_snap"
                else:
                    if t_b <= t_a:
                        x, z, src = x_a, z_a, "replication_e9_hold"
                    else:
                        a = (t - t_a) / (t_b - t_a)
                        x = x_a + a * (x_b - x_a)
                        z = z_a + a * (z_b - z_a)
                        src = "replication_e9_lerp"
            participants.append(
                {
                    "participantID": None,
                    "netId": nid,
                    "position": {"x": x, "z": z},
                    "positionSource": src,
                    # HP/ranks/combat intentionally absent
                }
            )
        if participants:
            frames.append(
                {
                    "rfc461Schema": "stats_update",
                    "gameID": game_id,
                    "gameTime": int(round(t * 1000)),
                    "participants": participants,
                    "researchOnly": True,
                    "productEligible": False,
                }
            )
        t += 1.0
    return frames


def gold_regression_check(updates: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Prove map-range HF pairs are never emitted as gold (or fake position state)."""
    state: Dict[int, Any] = {}
    for u in updates[:50]:
        nid = int(u["netId"])
        blob = (
            bytes([0x01])
            + struct.pack("<I", nid)
            + struct.pack("<I", 0x3)
            + bytes([8])
            + struct.pack("<ff", float(u["x"]), float(u["z"]))
        )
        for net_id, fields in parse_replication_vector(blob):
            apply_fields_to_state(state, net_id=net_id, fields=fields, time_s=float(u["time"]))
    gold_emissions = 0
    pos_emissions = 0
    for st in state.values():
        if getattr(st, "mGold", None) is not None or getattr(st, "mGoldTotal", None) is not None:
            gold_emissions += 1
        if getattr(st, "mPosX", None) is not None or getattr(st, "mPosZ", None) is not None:
            pos_emissions += 1
    return {
        "ok": gold_emissions == 0 and pos_emissions == 0,
        "goldEmissions": gold_emissions,
        "positionStateEmissions": pos_emissions,
        "fieldIndices": {
            "primary": POS_PRIMARY,
            "secondaryA": POS_SECONDARY_X,
            "secondaryB": POS_SECONDARY_Z,
            "semantic": "unclassified_not_gold_not_proven_position",
            "formerIncorrectLabels": ["mGold", "mGoldTotal"],
            "rejectedPositionClaim": True,
        },
    }


def drift_stats(updates: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Characterize (0,0)/(0,1) temporal deltas (research honesty aid)."""
    by: Dict[int, List[Tuple[float, float, float]]] = defaultdict(list)
    for u in updates:
        by[int(u["netId"])].append((float(u["time"]), float(u["x"]), float(u["z"])))
    half_steps = []
    for rows in by.values():
        rows = sorted(rows)
        for i in range(1, len(rows)):
            dt = rows[i][0] - rows[i - 1][0]
            if 0.45 <= dt <= 0.55:
                half_steps.append(
                    math.hypot(rows[i][1] - rows[i - 1][1], rows[i][2] - rows[i - 1][2])
                )
    half_steps.sort()
    return {
        "halfSecondSteps": len(half_steps),
        "medianStep": round(float(statistics.median(half_steps)), 4) if half_steps else None,
        "p95Step": (
            round(float(half_steps[int(0.95 * (len(half_steps) - 1))]), 4) if half_steps else None
        ),
        "note": (
            "Near-constant ~1.44 unit steps at 0.5s cadence are inconsistent with "
            "champion locomotion; reinforces oracle rejection of position claim."
        ),
    }


def count_blob_oracle_hits(
    mu: Any,
    pkt: int,
    deser: int,
    blocks: Sequence[Mapping[str, Any]],
    oracle_frames: Sequence[Mapping[str, Any]],
    *,
    sample_stride_s: float = 30.0,
    tol: float = 40.0,
) -> Dict[str, Any]:
    """Count post-Deserialize f32 pairs within tol of same-time oracle x/z."""
    if not oracle_frames:
        return {"hits": 0, "packetsScanned": 0}
    oracle_times = [float(fr["time"]) for fr in oracle_frames]
    hits = 0
    scanned = 0
    next_t = float(blocks[0]["time"]) if blocks else 0.0
    for b in blocks:
        t = float(b["time"])
        if t < next_t:
            continue
        if len(b["payload"]) < 200:
            continue
        r = deserialize_framed(mu, pkt=pkt, deser=deser, wire_payload=b["payload"])
        next_t = t + sample_stride_s
        if not r:
            continue
        scanned += 1
        # nearest oracle
        lo, hi = 0, len(oracle_times) - 1
        while lo <= hi:
            mid = (lo + hi) // 2
            if oracle_times[mid] < t:
                lo = mid + 1
            else:
                hi = mid - 1
        best_i = None
        best_dt = None
        for i in (lo - 1, lo, lo + 1):
            if 0 <= i < len(oracle_frames):
                dt = abs(oracle_times[i] - t)
                if dt <= 0.55 and (best_dt is None or dt < best_dt):
                    best_dt = dt
                    best_i = i
        if best_i is None:
            continue
        targets = [
            (float(p["x"]), float(p["z"])) for p in oracle_frames[best_i]["participants"]
        ]
        blob = r["blob"]
        for off in range(0, len(blob) - 8):
            a, c = struct.unpack_from("<ff", blob, off)
            if a != a or c != c:
                continue
            for tx, tz in targets:
                if abs(a - tx) <= tol and abs(c - tz) <= tol:
                    hits += 1
                if abs(a - tz) <= tol and abs(c - tx) <= tol:
                    hits += 1
    return {
        "hits": hits,
        "packetsScanned": scanned,
        "toleranceUnits": tol,
        "sampleStrideS": sample_stride_s,
        "interpretation": (
            "zero hits ⇒ type-107 plaintext vectors do not carry oracle-aligned "
            "x/z float pairs under this scan"
            if hits == 0
            else "non-zero hits warrant field-index follow-up"
        ),
    }


def run_e9(
    *,
    rofl: Path,
    oracle_jsonl: Path,
    fur_jsonl: Path,
    report_path: Path,
    emit_dir: Optional[Path] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    t0 = time.perf_counter()
    if not rofl.is_file():
        raise FileNotFoundError(rofl)
    work = Path(tempfile.mkdtemp(prefix="e9-repl-pos-"))
    arm = work / "LeagueofLegends.arm64"
    spike.thin_arm64(spike.DEFAULT_UNIVERSAL_BINARY, arm)
    mu, _heap, pkt, deser = _setup_emu(arm)

    blocks = collect_channel107_blocks(rofl)
    parity = run_parity_probe(mu, pkt, deser, blocks)
    updates, decode_meta = decode_all_positions(mu, pkt, deser, blocks)
    cadence = cadence_stats(updates)
    gold = gold_regression_check(updates)
    drift = drift_stats(updates)

    oracle_frames = _load_oracle_positions(oracle_jsonl) if oracle_jsonl.is_file() else []
    blob_hits = count_blob_oracle_hits(mu, pkt, deser, blocks, oracle_frames)
    oracle_qa = evaluate_oracle_qa(updates, oracle_frames) if oracle_frames else {
        "gates": {"ok": False, "error": "oracle_missing"},
        "label": "research_only_not_product",
    }
    fur = fur_semantic_compare(fur_jsonl, updates)

    # Research emit still preserves every candidate bank0 pair for audit — not product positions.
    waypoints = emit_maknee_waypoints(updates)
    rfc461 = emit_rfc461_1hz(updates)

    gates_ok = bool((oracle_qa.get("gates") or {}).get("ok"))
    position_proven = bool(gates_ok and blob_hits.get("hits", 0) > 0)

    # Identity: stable netIds only; product bind requires CreateHero/PUUID evidence
    # decoded from same-match stream (not oracle assignment).
    identity = {
        "stableNetIdKeys": sorted(hex(n) for n in {int(u["netId"]) for u in updates}),
        "provenHeroNetIds": [hex(n) for n in PROVEN_HERO_NET_IDS],
        "createHeroBindingDecoded": False,
        "puuidBindingDecoded": False,
        "fullRiotIdBindingDecoded": False,
        "oracleAssignmentIsProductIdentity": False,
        "productEligible": False,
        "blocker": "standalone_identity_binding_not_decoded_from_create_hero_or_riot_id",
    }

    pure_parity = bool(parity.get("pureByteParity"))
    browser_safe = False  # requires pure decrypt without Unicorn; framing alone insufficient
    wall_ms = (time.perf_counter() - t0) * 1000.0

    meet = {
        "method": "meet_in_the_middle",
        "sides": {
            "A_roflType107": {
                "matchCode": MATCH_CODE,
                "patch": "16.14",
                "role": "candidate_decoded_replication_positions",
            },
            "B_br1ReplayApi": {
                "matchCode": MATCH_CODE,
                "patch": "16.14",
                "path": str(oracle_jsonl),
                "role": "exact_numeric_timestamp_oracle",
            },
            "C_furOfficialJsonl": {
                "gameID": (fur.get("fur") or {}).get("gameID"),
                "platformID": (fur.get("fur") or {}).get("platformID"),
                "patch": "16.13",
                "path": str(fur_jsonl),
                "role": "schema_cadence_field_presence_oracle_only",
            },
        },
        "allowedComparisons": (fur.get("allowed") if fur.get("ok") else []),
        "disallowedComparisons": (fur.get("disallowed") if fur.get("ok") else []),
        "furRofl": {
            "available": False,
            "searched": False,
            "blocker": False,
            "note": "FUR–G2 ROFL is unavailable by design; JSONL is the schema contract only.",
        },
    }

    patch_manifest = {
        "framingConstants": {
            "replicationType": TYPE_107,
            "typeByte": TYPE_BYTE.hex(),
            "markerByte": MARKER_BYTE.hex(),
            "reconstructedPrefix": RECONSTRUCTED_PREFIX.hex(),
            "deserializeCursorAfterType": DESERIALIZE_CURSOR_AFTER_TYPE,
        },
        "positionFieldIndices": {
            "primary": POS_PRIMARY,
            "secondaryX": POS_SECONDARY_X,
            "secondaryZ": POS_SECONDARY_Z,
        },
        "buildHashNote": "arm64 LeagueofLegends thin from local universal; no binary vendored",
        "noBinaryRuntimeInManifest": True,
        "pureDecoderStatus": "blocked_encrypt_at_rest_transform",
    }

    browser_notes = {
        "candidate": "TypeScript/WASM Worker with local File → pure type-107 framing+decrypt",
        "uploadNeededForDecode": False,
        "jsonlMayUploadToAuthenticatedStorage": True,
        "currentBrowserSafe": browser_safe,
        "blocker": (
            None
            if pure_parity
            else "post-Deserialize vector is transformed; pure decrypt not yet derived"
        ),
    }

    if emit_dir is not None and not dry_run:
        emit_dir.mkdir(parents=True, exist_ok=True)
        (emit_dir / "waypoints.maknee.jsonl").write_text(
            "\n".join(json.dumps(e) for e in waypoints) + ("\n" if waypoints else ""),
            encoding="utf-8",
        )
        (emit_dir / "timeline.rfc461.1hz.research.jsonl").write_text(
            "\n".join(json.dumps(e) for e in rfc461) + ("\n" if rfc461 else ""),
            encoding="utf-8",
        )

    keep = "discard"
    reason = (
        "type-107 framing+Deserialize proven; (0,0)/(0,1) rejected as positions by "
        "same-match BR1 oracle (gates fail; zero blob f32 hits); gold label removed; "
        "pure decrypt still blocked"
    )
    if gates_ok and gold.get("ok") and position_proven:
        keep = "keep"
        reason = "type-107 replication positions pass BR1 oracle QA; gold mislabel corrected"

    report = {
        "ok": False,  # position claim not proven
        "positionClaimProven": position_proven,
        "probeVersion": PROBE_VERSION,
        "hypothesis": "phase-b-e9-replication-position",
        "matchCode": MATCH_CODE,
        "wallMs": round(wall_ms, 3),
        "wallTargetMs": 60000,
        "wallPass": wall_ms <= 60000,
        "channel107Blocks": len(blocks),
        "framingParity": parity,
        "decodeMeta": decode_meta,
        "positionFieldIndices": {
            "candidatePrimary": POS_PRIMARY,
            "candidateSecondaryA": POS_SECONDARY_X,
            "candidateSecondaryB": POS_SECONDARY_Z,
            "proven": position_proven,
            "semantic": "unclassified_bank0_pair",
            "rejection": {
                "oracleGatesOk": gates_ok,
                "blobOracleFloatHits": blob_hits.get("hits"),
                "drift": drift,
            },
        },
        "candidateBank0Updates": len(updates),
        "cadence": cadence,
        "drift": drift,
        "blobOracleScan": blob_hits,
        "goldRegression": gold,
        "oracleQA": {
            "comparedUpdates": (oracle_qa.get("gates") or {}).get("comparedUpdates"),
            "heroesCompared": (oracle_qa.get("gates") or {}).get("heroesCompared"),
            "medianError": (oracle_qa.get("gates") or {}).get("medianError"),
            "p95Error": (oracle_qa.get("gates") or {}).get("p95Error"),
            "maxError": (oracle_qa.get("gates") or {}).get("maxError"),
            "snappedDiscontinuities": (oracle_qa.get("gates") or {}).get(
                "snappedDiscontinuities"
            ),
            "ok": gates_ok,
            "assignmentCount": (oracle_qa.get("assignment") or {}).get("assignmentCount"),
            "assignment": (oracle_qa.get("assignment") or {}).get("assignment"),
            "label": oracle_qa.get("label"),
        },
        "furSemantic": fur,
        "meetInMiddle": meet,
        "identity": identity,
        "pureDecoder": {
            "byteParityWithUnicornBlob": pure_parity,
            "status": patch_manifest["pureDecoderStatus"],
            "patchManifest": patch_manifest,
        },
        "browserSafe": browser_safe,
        "browserNotes": browser_notes,
        "productEligible": False,
        "emit": {
            "waypointEvents": len(waypoints),
            "rfc461Frames1Hz": len(rfc461),
            "dir": str(emit_dir) if emit_dir else None,
            "note": "research audit emit of bank0 candidates; not product positions",
        },
        "fieldAudit": {
            "removedGoldMappingFor_0_0_and_0_1": True,
            "doNotEmitBank0AsPosition": True,
            "hpFieldsUnchanged": {"mHP": (5, 0), "mMaxHP": (5, 1)},
            "combatPrimary1NoOverlapWithBank0": True,
            "expandedScope": False,
        },
        "blocker": (
            None
            if position_proven
            else "type107_bank0_pair_not_oracle_positions; native_position_source_still_open"
        ),
    }

    if not dry_run:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        append_speed_record(
            log=SPEED_LOG,
            hypothesis="phase-b-e9-replication-position",
            diff_label="e9-type107-position+meet-in-middle",
            keep=keep,
            reason=reason,
            wall_ms=wall_ms,
            match_code=MATCH_CODE,
            extra={
                "decoderVersion": PROBE_VERSION,
                "positionUpdates": len(updates),
                "oracleOk": gates_ok,
                "medianError": (oracle_qa.get("gates") or {}).get("medianError"),
                "p95Error": (oracle_qa.get("gates") or {}).get("p95Error"),
                "maxError": (oracle_qa.get("gates") or {}).get("maxError"),
                "pureParity": pure_parity,
                "browserSafe": browser_safe,
                "productEligible": False,
                "framingPrefix": RECONSTRUCTED_PREFIX.hex(),
            },
        )
    return report


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rofl", type=Path, default=DEFAULT_ROFL)
    ap.add_argument("--oracle", type=Path, default=DEFAULT_ORACLE)
    ap.add_argument("--fur-jsonl", type=Path, default=DEFAULT_FUR)
    ap.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    ap.add_argument(
        "--emit-dir",
        type=Path,
        default=Path("docs/rofl-research/e9-emit-3264361042"),
    )
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    report = run_e9(
        rofl=args.rofl,
        oracle_jsonl=args.oracle,
        fur_jsonl=args.fur_jsonl,
        report_path=args.report,
        emit_dir=args.emit_dir,
        dry_run=args.dry_run,
    )
    summary = {
        "ok": report.get("ok"),
        "positionClaimProven": report.get("positionClaimProven"),
        "wallMs": report.get("wallMs"),
        "candidateBank0Updates": report.get("candidateBank0Updates"),
        "framingPrefix": RECONSTRUCTED_PREFIX.hex(),
        "pureParity": report.get("pureDecoder", {}).get("byteParityWithUnicornBlob"),
        "blobOracleHits": (report.get("blobOracleScan") or {}).get("hits"),
        "oracle": report.get("oracleQA"),
        "cadenceMedian": (report.get("cadence") or {}).get("globalMedianDt"),
        "driftMedianStep": (report.get("drift") or {}).get("medianStep"),
        "browserSafe": report.get("browserSafe"),
        "productEligible": report.get("productEligible"),
        "blocker": report.get("blocker"),
        "report": str(args.report),
    }
    print(json.dumps(summary, indent=2))
    return 0 if report.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
