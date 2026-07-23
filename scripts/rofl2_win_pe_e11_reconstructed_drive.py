#!/usr/bin/env python3
"""E11: Drive Windows Deserialize with reconstructed packet buffers (not raw wire).

Fixes the E10 methodological gap: Unicorn ``block_extract`` reconstructs
``encode_type(opcode) || marker || wire_payload``; raw ``extract_blocks_py``
payloads are not that input. E11 drives opcodes **58** (DirectInput) and
**1104** (SetMovementDriver) under reconstructed framing, hooks decrypt-helper
END_READ / buffer writers for plaintext f32 release, then QA against same-match
BR1 Replay API (search/QA only).

Hard constraints: no live API, no plan edit, no commit, no binary vendoring,
no learned affine. Axis-swap only; ``2*i16+SR_center`` only if insn stream
justifies (not used here — DirectInput path is 3×f32).
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

from unicorn import UC_HOOK_CODE  # noqa: E402
from unicorn.x86_const import UC_X86_REG_XMM0  # noqa: E402

from rofl2_binary_format import load_binary, research_manifest  # noqa: E402
from rofl2_movement_decode import (  # noqa: E402
    _load_oracle_positions,
    append_speed_record,
)
from rofl2_probe import extract_segments, parse_rofl2  # noqa: E402
from rofl2_unicorn_packet_drive import (  # noqa: E402
    TYPE_COUNT_VALUE,
    extract_blocks_py,
    type_threshold,
)
from rofl2_win_pe_packet_discover import (  # noqa: E402
    WinX64PacketEmu,
    enumerate_rofl,
    official_provenance,
    scan_msvc_packet_types,
)

PROBE_VERSION = "e11-win-pe-reconstructed-drive-v1"
MATCH_CODE = "3264361042"
DEFAULT_PE = Path("/tmp/League-of-Legends-16.14-win.exe")
DEFAULT_ROFL = Path.home() / "Documents/League of Legends/Replays/BR1-3264361042.rofl"
DEFAULT_ORACLE = Path("artifacts/rofl/3264361042/events.rfc461.jsonl")
DEFAULT_REPORT = Path("docs/rofl-research/movement-win-pe-e11-BR1-3264361042.json")
SPEED_LOG = Path("docs/rofl-research/speed-runs.jsonl")

# E8 semantic targets.
OPCODE_DIRECT_INPUT = 58
OPCODE_SET_MOVEMENT_DRIVER = 1104
OPCODE_FACE_DIRECTION = 420  # negative control (direction-only)

# E9-proven marker byte; generalized. DirectInput/FaceDirection deser consume a
# 1-byte bit header; SetMovementDriver consumes a 2-byte bit header.
MARKER_1 = bytes([0xA6])
MARKER_2 = bytes([0xC6, 0xFA])  # valid 2-byte bitfield for op 1104

# DirectInput decrypt END_READ (plaintext Vector3 window before re-encrypt).
DIRECT_INPUT_END_READ_VA = 0x140E66BAB
DIRECT_INPUT_VEC_OFF = 0x10

ACCEPT_MIN_SAMPLES = 80
ACCEPT_MIN_HEROES = 5
ACCEPT_MAX_MEDIAN = 120.0
ACCEPT_MAX_P95 = 350.0
ACCEPT_MAX_MAX = 800.0
ORACLE_TOL_S = 0.5
FRAMING_MIN_SAMPLES = 50
SR_MIN = -200.0
SR_MAX = 16000.0


def encode_type(typ: int, *, type_count: int = TYPE_COUNT_VALUE) -> bytes:
    """Inverse of ``read_packet_type`` / Unicorn block_extract type prefix."""
    thr = type_threshold(type_count)
    typ &= 0xFFFF
    if typ < thr:
        return bytes([typ])
    delta = typ - thr
    return bytes([(thr + ((delta >> 8) & 0xFF)) & 0xFF, delta & 0xFF])


def bit_header_for_opcode(opcode: int) -> bytes:
    """Bit-header length from Windows Deserialize (E8/E11 disasm)."""
    if int(opcode) == OPCODE_SET_MOVEMENT_DRIVER:
        return MARKER_2
    return MARKER_1


def reconstruct_buffer(opcode: int, wire_payload: bytes) -> bytes:
    """Full reconstructed packet buffer (type || marker || wire)."""
    return encode_type(opcode) + bit_header_for_opcode(opcode) + wire_payload


def deserialize_body(opcode: int, wire_payload: bytes) -> bytes:
    """Body presented to Deserialize (cursor after type; matches factory path)."""
    return bit_header_for_opcode(opcode) + wire_payload


def _hex(v: Optional[int]) -> Optional[str]:
    return None if v is None else hex(int(v))


def collect_blocks(
    rofl: Path, opcodes: Sequence[int]
) -> Dict[int, List[dict]]:
    want = {int(o) for o in opcodes}
    out: Dict[int, List[dict]] = defaultdict(list)
    info = parse_rofl2(rofl)
    for seg in extract_segments(info["payload"])["segments"]:
        if int(seg.get("type") or 0) != 1:
            continue
        for b in extract_blocks_py(seg["bytes"], max_blocks=500_000):
            op = int(b["channel"])
            if op not in want:
                continue
            pay = b.get("payload") or b""
            out[op].append(
                {
                    "time": float(b["time"]),
                    "param": int(b.get("param") or 0),
                    "payload": pay,
                    "wireSize": len(pay),
                }
            )
    for op in out:
        out[op].sort(key=lambda r: r["time"])
    return dict(out)


def era_sample_indices(n: int, k: int) -> List[int]:
    """≥k indices spanning early/mid/late."""
    if n <= 0:
        return []
    k = min(k, n)
    if k == 1:
        return [0]
    return sorted({int(round(i * (n - 1) / (k - 1))) for i in range(k)})


def validate_reconstruction(
    binary: Any,
    factory: Mapping[str, Any],
    blocks: Sequence[dict],
    *,
    min_samples: int = FRAMING_MIN_SAMPLES,
) -> dict:
    """Fail-closed: reconstructed body must beat raw wire on consume/retAl."""
    op = int(factory["opcode"])
    idxs = era_sample_indices(len(blocks), min_samples)
    raw_ok = 0
    recon_ok = 0
    raw_cons: List[int] = []
    recon_cons: List[int] = []
    for i in idxs:
        wire = blocks[i]["payload"]
        for label, body in (("raw", wire), ("recon", deserialize_body(op, wire))):
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
            cons = int(r.get("consumed") or 0)
            ok = bool(r.get("retAl")) and cons >= max(1, int(0.8 * len(body)))
            if label == "raw":
                raw_ok += int(ok)
                raw_cons.append(cons)
            else:
                recon_ok += int(ok)
                recon_cons.append(cons)
    n = len(idxs)
    avg_raw = (sum(raw_cons) / len(raw_cons)) if raw_cons else 0.0
    avg_recon = (sum(recon_cons) / len(recon_cons)) if recon_cons else 0.0
    validated = (
        n >= min(min_samples, max(1, len(blocks)))
        and recon_ok > raw_ok
        and (avg_recon > avg_raw + 0.5 or recon_ok >= max(1, int(0.8 * n)))
    )
    return {
        "opcode": op,
        "samples": n,
        "rawOk": raw_ok,
        "reconOk": recon_ok,
        "avgConsumedRaw": round(avg_raw, 3),
        "avgConsumedRecon": round(avg_recon, 3),
        "markerHex": bit_header_for_opcode(op).hex(),
        "encodeTypeHex": encode_type(op).hex(),
        "formula": (
            f"reconstructed = encode_type({op}) || "
            f"0x{bit_header_for_opcode(op).hex()} || wire_payload"
        ),
        "validated": validated,
    }


def _score_errs(errs: Sequence[float]) -> dict:
    if not errs:
        return {
            "n": 0,
            "median": None,
            "p95": None,
            "max": None,
            "ok": False,
        }
    s = sorted(float(e) for e in errs)
    def pct(p: float) -> float:
        i = min(len(s) - 1, int(round((p / 100.0) * (len(s) - 1))))
        return s[i]

    med = statistics.median(s)
    p95 = pct(95)
    mx = s[-1]
    heroes = 0  # filled by caller
    return {
        "n": len(s),
        "median": med,
        "p95": p95,
        "max": mx,
        "ok": (
            len(s) >= ACCEPT_MIN_SAMPLES
            and med <= ACCEPT_MAX_MEDIAN
            and p95 <= ACCEPT_MAX_P95
            and mx <= ACCEPT_MAX_MAX
        ),
    }


def nearest_oracle_frame(
    oracle: Sequence[dict], t: float, *, tol_s: float = ORACLE_TOL_S
) -> Optional[Tuple[float, Dict[int, Tuple[float, float]]]]:
    best = None
    best_dt = 1e9
    for row in oracle:
        dt = abs(float(row["time"]) - t)
        if dt < best_dt:
            best_dt = dt
            best = row
    if best is None or best_dt > tol_s:
        return None
    pos = {
        int(p["participantID"]): (float(p["x"]), float(p["z"]))
        for p in best["participants"]
    }
    return float(best["time"]), pos


def dist2(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def qa_samples(
    samples: Sequence[dict],
    oracle: Sequence[dict],
    *,
    swap: bool = False,
    forced_pid: Optional[int] = None,
) -> dict:
    errs: List[float] = []
    pid_counts: Counter = Counter()
    net_ids = set()
    for s in samples:
        fr = nearest_oracle_frame(oracle, float(s["t"]))
        if fr is None:
            continue
        _, pos = fr
        x, z = float(s["x"]), float(s["z"])
        if swap:
            x, z = z, x
        net_ids.add(int(s["param"]))
        if forced_pid is not None:
            if forced_pid not in pos:
                continue
            errs.append(dist2((x, z), pos[forced_pid]))
            pid_counts[forced_pid] += 1
            continue
        best_d = 1e18
        best_p = None
        for pid, pz in pos.items():
            d = dist2((x, z), pz)
            if d < best_d:
                best_d = d
                best_p = pid
        if best_p is not None:
            errs.append(best_d)
            pid_counts[best_p] += 1
    sc = _score_errs(errs)
    sc["heroes"] = len(net_ids)
    sc["heroGateOk"] = len(net_ids) >= ACCEPT_MIN_HEROES
    sc["ok"] = bool(sc["ok"] and sc["heroGateOk"])
    sc["nearestPidCounts"] = {str(k): int(v) for k, v in pid_counts.most_common()}
    return sc


def train_holdout_qa(samples: Sequence[dict], oracle: Sequence[dict]) -> dict:
    """Train picks best (pid, swap); holdout must also pass gates."""
    if len(samples) < 4:
        return {"winnerFound": False, "reason": "too_few_samples"}
    mid = len(samples) // 2
    train, hold = list(samples[:mid]), list(samples[mid:])
    best = None
    for swap in (False, True):
        # nearest-participant (research; single-entity stream)
        tr = qa_samples(train, oracle, swap=swap)
        if best is None or (tr.get("median") or 1e18) < (best["train"].get("median") or 1e18):
            best = {
                "mode": "nearest_participant",
                "swap": swap,
                "forcedPid": None,
                "train": tr,
                "holdout": qa_samples(hold, oracle, swap=swap),
            }
        for pid in range(1, 11):
            trp = qa_samples(train, oracle, swap=swap, forced_pid=pid)
            if trp["n"] < 10:
                continue
            if best is None or (trp.get("median") or 1e18) < (
                best["train"].get("median") or 1e18
            ):
                best = {
                    "mode": "forced_pid",
                    "swap": swap,
                    "forcedPid": pid,
                    "train": trp,
                    "holdout": qa_samples(hold, oracle, swap=swap, forced_pid=pid),
                }
    assert best is not None
    train_ok = bool(best["train"].get("ok"))
    hold_ok = bool(best["holdout"].get("ok"))
    # Allow axis-swap only when both improve vs direct nearest baseline.
    baseline = qa_samples(samples, oracle, swap=False)
    swap_all = qa_samples(samples, oracle, swap=True)
    axis_swap_accepted = bool(
        best["swap"]
        and (swap_all.get("median") or 1e18) < (baseline.get("median") or 1e18)
        and (best["holdout"].get("median") or 1e18)
        < (qa_samples(hold, oracle, swap=False).get("median") or 1e18)
    )
    if best["swap"] and not axis_swap_accepted:
        # Revert to direct
        best = {
            "mode": "nearest_participant",
            "swap": False,
            "forcedPid": None,
            "train": qa_samples(train, oracle, swap=False),
            "holdout": qa_samples(hold, oracle, swap=False),
        }
        train_ok = bool(best["train"].get("ok"))
        hold_ok = bool(best["holdout"].get("ok"))
    return {
        "winnerFound": train_ok and hold_ok,
        "axisSwapAccepted": bool(best["swap"]),
        "selection": best,
        "allSamplesDirect": baseline,
        "allSamplesSwap": swap_all,
        "gates": {
            "minSamples": ACCEPT_MIN_SAMPLES,
            "minHeroes": ACCEPT_MIN_HEROES,
            "maxMedian": ACCEPT_MAX_MEDIAN,
            "maxP95": ACCEPT_MAX_P95,
            "maxMax": ACCEPT_MAX_MAX,
            "oracleTolS": ORACLE_TOL_S,
        },
    }


def capture_direct_input(
    binary: Any, factory: Mapping[str, Any], blocks: Sequence[dict]
) -> dict:
    """Hook END_READ; read obj+0x10 as <fff> plaintext Vector3."""
    deser = int(factory["deserializeVa"])
    osz = int(factory["objectSize"])
    samples: List[dict] = []
    faults = 0
    for b in blocks:
        emu = WinX64PacketEmu(binary)
        fr = emu.construct(
            ctor_va=int(factory["ctorVa"]),
            object_size=osz,
            expected_opcode=OPCODE_DIRECT_INPUT,
            expected_vptr=int(factory["vptr"]),
        )
        if not fr.get("ok"):
            faults += 1
            continue
        obj = fr["obj"]
        hit: Dict[str, Any] = {}

        def on_end(uc: Any, address: int, size: int, user: Any) -> None:
            try:
                raw = bytes(uc.mem_read(obj + DIRECT_INPUT_VEC_OFF, 12))
                x, y, z = struct.unpack("<fff", raw)
                hit["xyz"] = (x, y, z)
                v = uc.reg_read(UC_X86_REG_XMM0)
                xb = v.to_bytes(16, "little") if isinstance(v, int) else bytes(v)[:16]
                hit["xmm0"] = struct.unpack_from("<fff", xb)
            except Exception as exc:  # noqa: BLE001
                hit["err"] = str(exc)

        h = emu.mu.hook_add(
            UC_HOOK_CODE, on_end, begin=DIRECT_INPUT_END_READ_VA, end=DIRECT_INPUT_END_READ_VA
        )
        body = deserialize_body(OPCODE_DIRECT_INPUT, b["payload"])
        r = emu.deserialize(
            obj=obj, deser_va=deser, payload=body, object_size=osz
        )
        try:
            emu.mu.hook_del(h)
        except Exception:  # noqa: BLE001
            pass
        if "xyz" not in hit:
            faults += 1
            continue
        x, y, z = hit["xyz"]
        samples.append(
            {
                "t": float(b["time"]),
                "param": int(b["param"]),
                "x": float(x),
                "y": float(y),
                "z": float(z),
                "retAl": int(r.get("retAl") or 0),
                "consumed": int(r.get("consumed") or 0),
                "mapRange": SR_MIN <= x <= SR_MAX and SR_MIN <= z <= SR_MAX,
            }
        )
    return {
        "opcode": OPCODE_DIRECT_INPUT,
        "name": "PKT_DirectInputMovementDriverServerTurnData_s",
        "endReadVa": _hex(DIRECT_INPUT_END_READ_VA),
        "layout": "obj+0x10 Vector3 <fff> (x,y,z); y typically height≈0",
        "register": "END_READ plaintext window (not sparse XMM sample)",
        "nBlocks": len(blocks),
        "nCaptured": len(samples),
        "nFaults": faults,
        "uniqueNetIds": sorted({s["param"] for s in samples}),
        "mapRangeCount": sum(1 for s in samples if s["mapRange"]),
        "samples": samples,
    }


def capture_set_movement_driver(
    binary: Any, factory: Mapping[str, Any], blocks: Sequence[dict]
) -> dict:
    """Reconstructed drive + post-deser buffer dump (waypoint writers)."""
    deser = int(factory["deserializeVa"])
    osz = int(factory["objectSize"])
    rows: List[dict] = []
    for b in blocks:
        emu = WinX64PacketEmu(binary)
        fr = emu.construct(
            ctor_va=int(factory["ctorVa"]),
            object_size=osz,
            expected_opcode=OPCODE_SET_MOVEMENT_DRIVER,
            expected_vptr=int(factory["vptr"]),
        )
        if not fr.get("ok"):
            continue
        body = deserialize_body(OPCODE_SET_MOVEMENT_DRIVER, b["payload"])
        r = emu.deserialize(
            obj=fr["obj"], deser_va=deser, payload=body, object_size=osz
        )
        after = bytes(emu.mu.mem_read(fr["obj"], max(osz, 64)))
        p10 = struct.unpack_from("<Q", after, 0x10)[0]
        n18 = struct.unpack_from("<I", after, 0x18)[0]
        p20 = struct.unpack_from("<Q", after, 0x20)[0]
        n28 = struct.unpack_from("<I", after, 0x28)[0]
        buf_floats: Dict[str, List[float]] = {}
        mapish = 0
        for name, ptr, n in (("buf+0x10", p10, n18), ("buf+0x20", p20, n28)):
            if not ptr or not n or n > 64:
                continue
            try:
                mem = bytes(emu.mu.mem_read(ptr, n * 4))
                floats = [struct.unpack_from("<f", mem, i)[0] for i in range(0, len(mem), 4)]
                buf_floats[name] = floats
                for f in floats:
                    if f == f and SR_MIN <= f <= SR_MAX and abs(f) > 50:
                        mapish += 1
            except Exception:  # noqa: BLE001
                pass
        rows.append(
            {
                "t": float(b["time"]),
                "param": int(b["param"]),
                "wireSize": int(b["wireSize"]),
                "retAl": int(r.get("retAl") or 0),
                "consumed": int(r.get("consumed") or 0),
                "bufFloats": buf_floats,
                "mapRangeFloatCount": mapish,
            }
        )
    return {
        "opcode": OPCODE_SET_MOVEMENT_DRIVER,
        "name": "PKT_S2C_SetMovementDriver_s",
        "nBlocks": len(blocks),
        "nRows": len(rows),
        "fullConsume": sum(
            1
            for row, b in zip(rows, blocks)
            if row["retAl"]
            and row["consumed"]
            >= len(deserialize_body(OPCODE_SET_MOVEMENT_DRIVER, b["payload"]))
        ),
        "mapRangeFloatTotal": sum(r["mapRangeFloatCount"] for r in rows),
        "note": (
            "Byte-decrypt writers fill small f32 (0/1/2/…); not map-range XZ. "
            "No END_READ Vector3 path analogous to DirectInput observed."
        ),
        "rows": rows,
    }


def capture_face_direction_control(
    binary: Any, factory: Mapping[str, Any], blocks: Sequence[dict], *, limit: int = 40
) -> dict:
    """Negative control: expect direction-ish scalars, not map XZ pairs."""
    deser = int(factory["deserializeVa"])
    osz = int(factory["objectSize"])
    map_pairs = 0
    directionish = 0
    for b in blocks[:limit]:
        emu = WinX64PacketEmu(binary)
        fr = emu.construct(
            ctor_va=int(factory["ctorVa"]),
            object_size=osz,
            expected_opcode=OPCODE_FACE_DIRECTION,
            expected_vptr=int(factory["vptr"]),
        )
        if not fr.get("ok"):
            continue
        body = deserialize_body(OPCODE_FACE_DIRECTION, b["payload"])
        r = emu.deserialize(
            obj=fr["obj"], deser_va=deser, payload=body, object_size=osz
        )
        if not r.get("retAl"):
            continue
        after = bytes(emu.mu.mem_read(fr["obj"], max(osz, 64)))
        floats = []
        for off in range(0x10, min(len(after) - 3, osz), 4):
            f = struct.unpack_from("<f", after, off)[0]
            if f == f and abs(f) > 1e-3:
                floats.append((off, f))
        xs = [f for _, f in floats if SR_MIN <= f <= SR_MAX and abs(f) > 50]
        if len(xs) >= 2:
            map_pairs += 1
        if any(abs(f) < 50 for _, f in floats):
            directionish += 1
    return {
        "opcode": OPCODE_FACE_DIRECTION,
        "name": "FaceDirection (negative control)",
        "sampled": min(limit, len(blocks)),
        "mapRangePairHits": map_pairs,
        "directionishHits": directionish,
        "expectPositionCarrier": False,
    }


def classify_blocker(
    *,
    framing: Mapping[int, dict],
    di: Mapping[str, Any],
    smd: Mapping[str, Any],
    qa: Mapping[str, Any],
) -> dict:
    recon_ok = all(framing[op]["validated"] for op in framing)
    helpers_58 = int(di.get("nCaptured") or 0) > 0 and int(di.get("mapRangeCount") or 0) > 0
    helpers_1104_map = int(smd.get("mapRangeFloatTotal") or 0) > 0
    qa_ok = bool(qa.get("winnerFound"))
    if not recon_ok:
        kind = "reconstruction_invalid"
        detail = "reconstructed prefix did not beat raw wire on consume/retAl"
    elif not helpers_58 and not helpers_1104_map:
        kind = "helpers_still_incomplete"
        detail = "no plaintext map-range f32 released from decrypt helpers"
    elif helpers_58 and not qa_ok:
        kind = "opcodes_not_position_carriers"
        detail = (
            "DirectInput END_READ releases map-range XZ, but train+holdout Replay API "
            "QA fails gates (not live positions within med≤120/p95≤350/max≤800; "
            f"uniqueNetIds={len(di.get('uniqueNetIds') or [])})"
        )
    else:
        kind = "unknown"
        detail = "unexpected state"
    return {
        "kind": kind,
        "detail": detail,
        "reconstructionValidated": recon_ok,
        "directInputPlaintextReleased": helpers_58,
        "setMovementDriverMapFloats": helpers_1104_map,
        "oracleQaPassed": qa_ok,
    }


def run_e11(
    *,
    pe_path: Path,
    rofl: Path,
    oracle_jsonl: Path,
    report_path: Path,
    dry_run: bool = False,
) -> dict:
    t0 = time.perf_counter()
    if not pe_path.is_file():
        raise FileNotFoundError(pe_path)
    binary = load_binary(pe_path)
    prov = official_provenance(size=pe_path.stat().st_size, sha256=binary.sha256)
    man = research_manifest(
        binary, patch="16.14", extra={"probeVersion": PROBE_VERSION, "official": prov}
    )
    counts, _ = enumerate_rofl(rofl)
    rows, coverage = scan_msvc_packet_types(binary, counts)
    factories = {int(r["opcode"]): r for r in rows}

    needed = [OPCODE_DIRECT_INPUT, OPCODE_SET_MOVEMENT_DRIVER, OPCODE_FACE_DIRECTION]
    for op in needed:
        if op not in factories:
            raise RuntimeError(f"missing factory for opcode {op}")

    blocks = collect_blocks(rofl, needed)
    framing: Dict[int, dict] = {}
    for op in (OPCODE_DIRECT_INPUT, OPCODE_SET_MOVEMENT_DRIVER):
        framing[op] = validate_reconstruction(
            binary, factories[op], blocks.get(op) or [], min_samples=FRAMING_MIN_SAMPLES
        )

    if not all(framing[op]["validated"] for op in framing):
        wall_ms = (time.perf_counter() - t0) * 1000.0
        blocker = classify_blocker(
            framing=framing,
            di={"nCaptured": 0, "mapRangeCount": 0, "uniqueNetIds": []},
            smd={"mapRangeFloatTotal": 0},
            qa={"winnerFound": False},
        )
        report = {
            "ok": False,
            "probeVersion": PROBE_VERSION,
            "hypothesis": "phase-b-e11-reconstructed-drive",
            "matchCode": MATCH_CODE,
            "wallMs": round(wall_ms, 3),
            "wallPass": wall_ms <= 60_000,
            "framingValidation": framing,
            "blocker": blocker,
            "pureDecoderDerived": False,
            "browserSafe": False,
            "productEligible": False,
        }
        if not dry_run:
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        return report

    di = capture_direct_input(
        binary, factories[OPCODE_DIRECT_INPUT], blocks.get(OPCODE_DIRECT_INPUT) or []
    )
    smd = capture_set_movement_driver(
        binary,
        factories[OPCODE_SET_MOVEMENT_DRIVER],
        blocks.get(OPCODE_SET_MOVEMENT_DRIVER) or [],
    )
    face = capture_face_direction_control(
        binary, factories[OPCODE_FACE_DIRECTION], blocks.get(OPCODE_FACE_DIRECTION) or []
    )

    oracle = _load_oracle_positions(oracle_jsonl)
    qa = train_holdout_qa(di.get("samples") or [], oracle)
    blocker = classify_blocker(framing=framing, di=di, smd=smd, qa=qa)

    winner = None
    if qa.get("winnerFound"):
        winner = {
            "opcode": OPCODE_DIRECT_INPUT,
            "pc": _hex(DIRECT_INPUT_END_READ_VA),
            "register": "obj+0x10 / END_READ plaintext Vector3",
            "layout": di["layout"],
            "selection": qa.get("selection"),
        }

    wall_ms = (time.perf_counter() - t0) * 1000.0
    pure = False
    browser_safe = False
    product_eligible = False

    # Strip bulky sample list from report; keep summary + first/last few.
    di_public = {
        k: v
        for k, v in di.items()
        if k != "samples"
    }
    di_public["sampleHead"] = (di.get("samples") or [])[:3]
    di_public["sampleTail"] = (di.get("samples") or [])[-3:]
    smd_public = {k: v for k, v in smd.items() if k != "rows"}
    smd_public["rowHead"] = (smd.get("rows") or [])[:3]

    report = {
        "ok": bool(winner),
        "probeVersion": PROBE_VERSION,
        "hypothesis": "phase-b-e11-reconstructed-drive",
        "matchCode": MATCH_CODE,
        "wallMs": round(wall_ms, 3),
        "wallTargetMs": 60_000,
        "wallPass": wall_ms <= 60_000,
        "official": prov,
        "binaryManifest": man,
        "constructorCoverage": coverage,
        "methodologicalGapFixed": {
            "e10Fed": "raw extract_blocks_py wire payloads",
            "e11Feeds": "reconstructed encode_type||marker||wire (Deserialize body=marker||wire)",
            "unicornParityNote": (
                "channelMatch already proven in unicorn-packet-drive-BR1-3264361042.json; "
                "marker/prefix validated here via ≥50-sample consume/retAl vs raw (fail-closed)"
            ),
        },
        "framingValidation": framing,
        "directInput": di_public,
        "setMovementDriver": smd_public,
        "faceDirectionControl": face,
        "evaluation": {
            "winnerFound": bool(winner),
            "winner": winner,
            "qa": qa,
        },
        "blocker": blocker,
        "pureDecoderDerived": pure,
        "browserSafe": browser_safe,
        "productEligible": product_eligible,
        "identity": {
            "stableNetIdKeys": True,
            "createHeroBindingDecoded": False,
            "productEligible": False,
            "note": "oracle assignment is QA/search only; productEligible needs CreateHero/PUUID",
        },
        "browserNotes": {
            "runtimeUnicornRequired": True,
            "browserSafeOnlyIfPureParser": True,
        },
    }

    keep = "keep" if winner else "discard"
    reason = (
        f"E11 winner opcode={winner['opcode']} pc={winner['pc']}"
        if winner
        else f"E11 blocker={blocker['kind']}: {blocker['detail'][:160]}"
    )
    if not dry_run:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        append_speed_record(
            log=SPEED_LOG,
            hypothesis="phase-b-e11-reconstructed-drive",
            diff_label="e11-reconstructed-drive-xz",
            keep=keep,
            reason=reason,
            wall_ms=wall_ms,
            match_code=MATCH_CODE,
            extra={
                "decoderVersion": PROBE_VERSION,
                "winnerFound": bool(winner),
                "winner": winner,
                "blocker": blocker,
                "browserSafe": browser_safe,
                "productEligible": product_eligible,
                "pureDecoderDerived": pure,
                "reconstructionValidated": blocker.get("reconstructionValidated"),
                "directInputCaptured": di_public.get("nCaptured"),
                "qaAllMedian": (qa.get("allSamplesDirect") or {}).get("median"),
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
    report = run_e11(
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
                "blocker": report.get("blocker"),
                "framingValidation": {
                    str(k): {
                        "validated": v.get("validated"),
                        "rawOk": v.get("rawOk"),
                        "reconOk": v.get("reconOk"),
                    }
                    for k, v in (report.get("framingValidation") or {}).items()
                },
                "directInputCaptured": (report.get("directInput") or {}).get("nCaptured"),
                "qaMedian": (
                    ((report.get("evaluation") or {}).get("qa") or {}).get(
                        "allSamplesDirect"
                    )
                    or {}
                ).get("median"),
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
