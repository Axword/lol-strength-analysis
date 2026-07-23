#!/usr/bin/env python3
"""E17: SetMovementDriver (1104) structural path + tick-integrate into PC+0xa0.

Pinned facts (reuse, do not re-debate):
  E11 reconstruct framing encode_type || marker || wire
  PathSetAbsolute @0x1403891a0 → PC+0xa0; abs getter 0x140305350
  UpdatePC / PATH_APPLY → PC+0x40 path vector
  Packet deser 58/420/908/1104 never reaches PathSetAbsolute (E16)

Single variable: structurally decoded 1104 path state + fixed-dt integration
into PathController+0xa0 vs Replay API oracle. Fail closed if waypoints /
driver state are not recovered.

Hard constraints: no live API, no plan edit, no commit, no binary vendoring,
no learned affine. Axis-swap only.
"""
from __future__ import annotations

import argparse
import json
import math
import struct
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from unicorn import UC_HOOK_MEM_WRITE  # noqa: E402

from rofl2_binary_format import load_binary, research_manifest  # noqa: E402
from rofl2_movement_decode import (  # noqa: E402
    _load_oracle_positions,
    append_speed_record,
)
from rofl2_movement_emulator_probe import (  # noqa: E402
    PathParseError,
    parse_compressed_path_packet,
)
from rofl2_movement_wire_scan import PROVEN_HERO_NET_ID_SET  # noqa: E402
from rofl2_win_pe_e11_reconstructed_drive import (  # noqa: E402
    OPCODE_FACE_DIRECTION,
    OPCODE_SET_MOVEMENT_DRIVER,
    capture_face_direction_control,
    deserialize_body,
    validate_reconstruction,
)
from rofl2_win_pe_e14_position_getters import (  # noqa: E402
    ACCEPT_MAX_MAX,
    ACCEPT_MAX_MEDIAN,
    ACCEPT_MAX_P95,
    ACCEPT_MIN_HEROES,
    ACCEPT_MIN_SAMPLES,
    MAX_SAMPLES_908,
    OPCODE_NEAR_MISS,
    ORACLE_TOL_S,
    SR_MAX,
    SR_MIN,
    capture_908_xyz,
    collect_blocks,
    diversify,
)
from rofl2_win_pe_e15_position_writers import (  # noqa: E402
    ABS_GETTER_VA,
    ABS_POSITION_IN_PC,
    PATH_SET_ABSOLUTE_VA,
)
from rofl2_win_pe_e16_pathsetabsolute_callers import (  # noqa: E402
    PATH_APPLY_VA,
    UPDATE_PC_VA,
    apply_path_set_absolute,
    qa_samples,
)
from rofl2_win_pe_packet_discover import (  # noqa: E402
    WinX64PacketEmu,
    enumerate_rofl,
    official_provenance,
    scan_msvc_packet_types,
)

PROBE_VERSION = "e17-win-pe-path-integrator-v1"
MATCH_CODE = "3264361042"
DEFAULT_PE = Path("/tmp/League-of-Legends-16.14-win.exe")
DEFAULT_ROFL = Path.home() / "Documents/League of Legends/Replays/BR1-3264361042.rofl"
DEFAULT_ORACLE = Path("artifacts/rofl/3264361042/events.rfc461.jsonl")
DEFAULT_REPORT = Path("docs/rofl-research/movement-win-pe-e17-BR1-3264361042.json")
SPEED_LOG = Path("docs/rofl-research/speed-runs.jsonl")

INTEGRATE_DT_S = 1.0 / 30.0  # fixed tick for path walk
SPEED_MIN = 50.0
SPEED_MAX = 2000.0
FRAMING_MIN_1104 = 1  # only 6 ROFL blocks exist; validate all available


def _f32_map(v: float) -> bool:
    return v == v and SR_MIN <= v <= SR_MAX and abs(v) > 50.0


def _f32_speed(v: float) -> bool:
    return v == v and SPEED_MIN <= v <= SPEED_MAX


def integrate_path_at_time(
    waypoints: Sequence[Tuple[float, float]],
    speed: float,
    *,
    elapsed_s: float,
    dt: float = INTEGRATE_DT_S,
) -> Optional[Tuple[float, float]]:
    """Walk polyline at constant speed for elapsed_s; return (x, z) or None."""
    if len(waypoints) < 1 or speed <= 0 or elapsed_s < 0:
        return None
    if len(waypoints) == 1:
        return float(waypoints[0][0]), float(waypoints[0][1])
    x, z = float(waypoints[0][0]), float(waypoints[0][1])
    seg_i = 0
    remaining = float(elapsed_s)
    # Discrete ticks — fail closed on degenerate segments.
    steps = max(1, int(math.ceil(remaining / dt))) if remaining > 0 else 0
    for _ in range(steps + 1):
        if remaining <= 1e-9 or seg_i >= len(waypoints) - 1:
            break
        tx, tz = float(waypoints[seg_i + 1][0]), float(waypoints[seg_i + 1][1])
        dx, dz = tx - x, tz - z
        dist = math.hypot(dx, dz)
        if dist < 1e-6:
            seg_i += 1
            x, z = tx, tz
            continue
        step = min(dt, remaining)
        travel = speed * step
        if travel >= dist:
            remaining -= dist / speed
            x, z = tx, tz
            seg_i += 1
        else:
            f = travel / dist
            x += dx * f
            z += dz * f
            remaining -= step
    return x, z


def sample_integrated_timeline(
    *,
    t0: float,
    waypoints: Sequence[Tuple[float, float]],
    speed: float,
    param: int,
    horizon_s: float = 5.0,
    sample_hz: float = 1.0,
) -> List[dict]:
    """Emit 1Hz integrated positions for QA (not a full PathController sim)."""
    out: List[dict] = []
    n = max(1, int(horizon_s * sample_hz) + 1)
    for i in range(n):
        elapsed = i / sample_hz
        pos = integrate_path_at_time(waypoints, speed, elapsed_s=elapsed)
        if pos is None:
            continue
        out.append(
            {
                "t": t0 + elapsed,
                "param": int(param),
                "x": float(pos[0]),
                "y": 0.0,
                "z": float(pos[1]),
                "elapsedS": elapsed,
                "speed": float(speed),
                "waypointCount": len(waypoints),
                "source": "1104_path_integrator",
            }
        )
    return out


def _try_pathpacket(data: bytes) -> Optional[dict]:
    try:
        pp = parse_compressed_path_packet(data, require_full_consume=True)
    except (PathParseError, Exception):  # noqa: BLE001
        return None
    if not pp.full_consume or not pp.waypoints:
        return None
    if not _f32_speed(pp.speed):
        return None
    wps = [(float(x), float(z)) for x, z in pp.waypoints if _f32_map(x) and _f32_map(z)]
    if len(wps) < 1:
        return None
    return {
        "entityId": int(pp.entity_id),
        "speed": float(pp.speed),
        "waypoints": wps,
        "waypointCount": len(wps),
        "parsingType": int(pp.parsing_type),
        "fullConsume": True,
        "kind": "pathpacket",
    }


def _scan_map_pairs(floats: Sequence[float]) -> List[Tuple[float, float]]:
    pairs: List[Tuple[float, float]] = []
    for i in range(0, len(floats) - 1, 2):
        a, b = floats[i], floats[i + 1]
        if _f32_map(a) and _f32_map(b):
            pairs.append((float(a), float(b)))
    return pairs


def capture_1104_driver_state(
    binary: Any, factory: Mapping[str, Any], blocks: Sequence[dict]
) -> dict:
    """Reconstructed 1104 Deserialize + MEM_WRITE hooks for path/speed/count."""
    deser = int(factory["deserializeVa"])
    osz = max(int(factory["objectSize"]), 64)
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
            rows.append(
                {
                    "t": float(b["time"]),
                    "param": int(b["param"]),
                    "constructOk": False,
                    "structurallyDecoded": False,
                }
            )
            continue
        obj = int(fr["obj"])
        writes: List[dict] = []
        speed_cands: List[float] = []
        count_cands: List[int] = []
        map_writes: List[Tuple[float, float]] = []
        last_map: List[float] = []

        def on_write(
            uc: Any, access: int, address: int, size: int, value: int, user: Any
        ) -> None:
            if size != 4:
                return
            raw = value & 0xFFFFFFFF
            f32 = struct.unpack("<f", struct.pack("<I", raw))[0]
            off = int(address - obj)
            writes.append(
                {
                    "addr": hex(int(address)),
                    "objOff": off if 0 <= off < osz + 0x100 else None,
                    "u32": raw,
                    "f32": float(f32) if f32 == f32 else None,
                }
            )
            if _f32_speed(f32):
                speed_cands.append(float(f32))
            if 1 <= raw <= 32:
                count_cands.append(int(raw))
            if _f32_map(f32):
                last_map.append(float(f32))
                if len(last_map) >= 2:
                    map_writes.append((last_map[-2], last_map[-1]))

        h = emu.mu.hook_add(UC_HOOK_MEM_WRITE, on_write)
        body = deserialize_body(OPCODE_SET_MOVEMENT_DRIVER, b["payload"])
        r = emu.deserialize(obj=obj, deser_va=deser, payload=body, object_size=osz)
        try:
            emu.mu.hook_del(h)
        except Exception:  # noqa: BLE001
            pass

        after = bytes(emu.mu.mem_read(obj, max(osz, 64)))
        # E11 layout: ptr@+0x10 / count@+0x18, ptr@+0x20 / count@+0x28
        buf_meta: List[dict] = []
        path_hits: List[dict] = []
        for ptr_off, n_off, name in ((0x10, 0x18, "buf+0x10"), (0x20, 0x28, "buf+0x20")):
            if ptr_off + 8 > len(after) or n_off + 4 > len(after):
                continue
            ptr = struct.unpack_from("<Q", after, ptr_off)[0]
            n = struct.unpack_from("<I", after, n_off)[0]
            meta: Dict[str, Any] = {"name": name, "ptr": hex(ptr), "countOrBytes": n}
            if ptr and 1 <= n <= 256:
                try:
                    # Prefer byte length = n*4 (f32 vector) then raw n bytes.
                    for length in (n * 4, n):
                        if length < 4 or length > 0x4000:
                            continue
                        mem = bytes(emu.mu.mem_read(ptr, length))
                        floats = [
                            struct.unpack_from("<f", mem, i)[0]
                            for i in range(0, len(mem) - 3, 4)
                        ]
                        meta["floats"] = floats[:32]
                        meta["mapPairs"] = _scan_map_pairs(floats)
                        pp = _try_pathpacket(mem)
                        if pp:
                            path_hits.append({**pp, "source": name})
                        break
                except Exception:  # noqa: BLE001
                    meta["readError"] = True
            buf_meta.append(meta)

        # Also try PathPacket on any deser-reported buffers / allocs.
        for buf in r.get("buffers") or []:
            try:
                ptr = int(str(buf.get("ptr") or "0"), 16)
                length = int(buf.get("length") or 0)
                if ptr and 8 <= length <= 0x4000:
                    mem = bytes(emu.mu.mem_read(ptr, length))
                    pp = _try_pathpacket(mem)
                    if pp:
                        path_hits.append({**pp, "source": "deser_buffer"})
            except Exception:  # noqa: BLE001
                pass
        for hit in r.get("pathHits") or []:
            if hit.get("waypoints") and _f32_speed(float(hit.get("speed") or 0)):
                path_hits.append(
                    {
                        "entityId": int(hit.get("entityId") or 0),
                        "speed": float(hit["speed"]),
                        "waypoints": [(float(hit["x"]), float(hit["z"]))],
                        "waypointCount": int(hit.get("waypoints") or 1),
                        "kind": "deser_pathHits",
                        "fullConsume": True,
                        "source": "emu_pathHits",
                    }
                )

        # Structural decode decision for this block.
        best_path = path_hits[0] if path_hits else None
        map_from_writes = list(map_writes)
        speed = None
        waypoints: List[Tuple[float, float]] = []
        net_id = None
        decode_kind = None

        if best_path:
            waypoints = list(best_path["waypoints"])
            speed = float(best_path["speed"])
            net_id = int(best_path["entityId"])
            decode_kind = best_path.get("kind") or "pathpacket"
        elif map_from_writes and speed_cands:
            # Require both map pairs and a speed-range write — still not PathPacket.
            waypoints = map_from_writes[:16]
            speed = float(speed_cands[0])
            decode_kind = "memwrite_map_pairs"
            # netId: prefer proven blockParam only when path structurally present
            if int(b["param"]) in PROVEN_HERO_NET_ID_SET:
                net_id = int(b["param"])

        param = int(b["param"])
        has_path = len(waypoints) >= 1 and all(
            _f32_map(x) and _f32_map(z) for x, z in waypoints
        )
        has_speed = speed is not None and _f32_speed(float(speed))
        has_net = net_id is not None and (
            int(net_id) in PROVEN_HERO_NET_ID_SET or int(net_id) == param
        )
        structurally = bool(has_path and has_speed and has_net)

        rows.append(
            {
                "t": float(b["time"]),
                "param": param,
                "paramProvenHero": param in PROVEN_HERO_NET_ID_SET,
                "wireSize": int(b.get("wireSize") or len(b.get("payload") or b"")),
                "constructOk": True,
                "retAl": int(r.get("retAl") or 0),
                "consumed": int(r.get("consumed") or 0),
                "writeCount": len(writes),
                "speedCandidates": speed_cands[:8],
                "countCandidates": count_cands[:8],
                "mapWritePairs": [{"x": a, "z": b} for a, b in map_from_writes[:8]],
                "buffers": [
                    {k: v for k, v in m.items() if k != "floats"} for m in buf_meta
                ],
                "bufFloatHeads": {
                    m["name"]: (m.get("floats") or [])[:8] for m in buf_meta
                },
                "pathHits": [
                    {
                        "entityId": h.get("entityId"),
                        "speed": h.get("speed"),
                        "waypointCount": h.get("waypointCount"),
                        "source": h.get("source"),
                        "kind": h.get("kind"),
                    }
                    for h in path_hits
                ],
                "decoded": {
                    "waypoints": [{"x": x, "z": z} for x, z in waypoints],
                    "speed": speed,
                    "netId": net_id,
                    "kind": decode_kind,
                    "hasPath": has_path,
                    "hasSpeed": has_speed,
                    "hasNetId": has_net,
                },
                "structurallyDecoded": structurally,
            }
        )

    n_struct = sum(1 for r in rows if r.get("structurallyDecoded"))
    return {
        "opcode": OPCODE_SET_MOVEMENT_DRIVER,
        "name": "PKT_S2C_SetMovementDriver_s",
        "nBlocks": len(blocks),
        "nRows": len(rows),
        "structurallyDecodedCount": n_struct,
        "pathBlobRecovered": any(
            (r.get("decoded") or {}).get("hasPath") for r in rows
        ),
        "speedRecovered": any((r.get("decoded") or {}).get("hasSpeed") for r in rows),
        "netIdRecovered": any((r.get("decoded") or {}).get("hasNetId") for r in rows),
        "rows": rows,
    }


def integrate_decoded_rows(driver: Mapping[str, Any]) -> List[dict]:
    """If structural path+speed+netId recovered, emit integrated samples."""
    samples: List[dict] = []
    for r in driver.get("rows") or []:
        if not r.get("structurallyDecoded"):
            continue
        dec = r.get("decoded") or {}
        wps = [(float(p["x"]), float(p["z"])) for p in (dec.get("waypoints") or [])]
        speed = float(dec["speed"])
        samples.extend(
            sample_integrated_timeline(
                t0=float(r["t"]),
                waypoints=wps,
                speed=speed,
                param=int(dec.get("netId") or r["param"]),
            )
        )
    return samples


def apply_integrated_to_a0(binary: Any, samples: Sequence[dict]) -> List[dict]:
    """PathSetAbsolute → abs getter (+0xa0) for integrated positions."""
    return apply_path_set_absolute(binary, samples)


def classify_blocker(
    *,
    framing_ok: bool,
    driver: Mapping[str, Any],
    integrated: Sequence[dict],
    qa: Mapping[str, Any],
    neg_908: Mapping[str, Any],
    face: Mapping[str, Any],
) -> dict:
    if not framing_ok:
        return {
            "kind": "reconstruction_invalid",
            "detail": "1104 reconstructed framing failed consume/retAl vs raw",
        }
    n_struct = int(driver.get("structurallyDecodedCount") or 0)
    has_path = bool(driver.get("pathBlobRecovered"))
    has_speed = bool(driver.get("speedRecovered"))
    has_net = bool(driver.get("netIdRecovered"))

    if qa.get("winnerFound"):
        return {"kind": "none", "detail": "integrated 1104 path passed oracle gates"}

    if not has_path:
        return {
            "kind": "waypoints_not_structurally_decoded",
            "detail": (
                "SetMovementDriver (1104) reconstructed Deserialize does not release "
                "map-range waypoint path blobs (E11 small scalars 0/1/2… persist; "
                "PathPacket full-consume=0). Cannot tick-integrate into PC+0xa0."
            ),
            "pathBlobRecovered": False,
            "speedRecovered": has_speed,
            "netIdRecovered": has_net,
            "negativeControls": {
                "opcode908": (neg_908.get("qa") or {}).get("winnerFound"),
                "faceDirectionExpectPosition": face.get("expectPositionCarrier"),
            },
        }

    if not (has_speed and has_net) or n_struct == 0:
        return {
            "kind": "driver_state_incomplete",
            "detail": (
                f"Partial 1104 state only (path={has_path}, speed={has_speed}, "
                f"netId={has_net}, structurallyDecoded={n_struct}); refuse integration"
            ),
            "pathBlobRecovered": has_path,
            "speedRecovered": has_speed,
            "netIdRecovered": has_net,
        }

    # Structural state present but QA failed / samples insufficient → full sim needed.
    return {
        "kind": "integration_requires_full_sim",
        "detail": (
            "1104 path+speed+netId recovered structurally, but fixed-dt polyline walk "
            "into PC+0xa0 does not pass Replay API gates (or needs AIBase/PathController "
            "heap UpdatePC each tick). Fail closed — no naive walk claim."
        ),
        "integratedSamples": len(integrated),
        "qa": {
            "winnerFound": qa.get("winnerFound"),
            "holdout": qa.get("holdout"),
            "train": qa.get("train"),
        },
        "secondary": "waypoints_available_but_oracle_fail",
    }


def run_e17(
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

    needed = [
        OPCODE_SET_MOVEMENT_DRIVER,
        OPCODE_NEAR_MISS,
        OPCODE_FACE_DIRECTION,
    ]
    for op in needed:
        if op not in factories:
            raise RuntimeError(f"missing factory for opcode {op}")

    blocks = collect_blocks(rofl, needed)
    framing = validate_reconstruction(
        binary,
        factories[OPCODE_SET_MOVEMENT_DRIVER],
        blocks.get(OPCODE_SET_MOVEMENT_DRIVER) or [],
        min_samples=min(
            FRAMING_MIN_1104, max(1, len(blocks.get(OPCODE_SET_MOVEMENT_DRIVER) or []))
        ),
    )

    driver = capture_1104_driver_state(
        binary,
        factories[OPCODE_SET_MOVEMENT_DRIVER],
        blocks.get(OPCODE_SET_MOVEMENT_DRIVER) or [],
    )

    integrated = integrate_decoded_rows(driver)
    applied: List[dict] = []
    qa: dict = {"winnerFound": False, "reason": "no_structural_path"}
    if integrated:
        applied = apply_integrated_to_a0(binary, integrated)
        oracle = _load_oracle_positions(oracle_jsonl)
        qa = qa_samples(applied, oracle)

    # Negative controls: 908 poke (known near-miss) + FaceDirection.
    neg_908: dict = {"opcode": OPCODE_NEAR_MISS, "skipped": True}
    if blocks.get(OPCODE_NEAR_MISS):
        samp = diversify(blocks[OPCODE_NEAR_MISS], min(40, MAX_SAMPLES_908))
        rows908 = capture_908_xyz(binary, factories[OPCODE_NEAR_MISS], samp)
        got908 = apply_path_set_absolute(binary, rows908)
        oracle = _load_oracle_positions(oracle_jsonl)
        neg_908 = {
            "opcode": OPCODE_NEAR_MISS,
            "source": "908 +16/+20 → PathSetAbsolute → abs getter (negative control)",
            "captured": len(rows908),
            "applied": sum(1 for s in got908 if s.get("getOk")),
            "qa": qa_samples(got908, oracle),
            "expectWinner": False,
        }

    face_blocks = (blocks.get(OPCODE_FACE_DIRECTION) or [])[:40]
    face = capture_face_direction_control(
        binary, factories[OPCODE_FACE_DIRECTION], face_blocks, limit=40
    )

    framing_ok = bool(framing.get("validated"))
    blocker = classify_blocker(
        framing_ok=framing_ok,
        driver=driver,
        integrated=integrated,
        qa=qa,
        neg_908=neg_908,
        face=face,
    )
    winner = blocker.get("kind") == "none" and bool(qa.get("winnerFound"))
    # Pure decoder only if structural path recovered AND oracle gates pass
    # without requiring Unicorn at product runtime — not met here unless winner
    # and decode_kind is a pure wire parse (pathpacket from bytes alone).
    pure = False
    if winner:
        kinds = {
            (r.get("decoded") or {}).get("kind")
            for r in (driver.get("rows") or [])
            if r.get("structurallyDecoded")
        }
        pure = kinds == {"pathpacket"}

    wall_ms = (time.perf_counter() - t0) * 1000.0
    driver_public = {k: v for k, v in driver.items() if k != "rows"}
    driver_public["rowHead"] = (driver.get("rows") or [])[:4]
    driver_public["rowSummary"] = [
        {
            "t": r.get("t"),
            "param": r.get("param"),
            "wireSize": r.get("wireSize"),
            "structurallyDecoded": r.get("structurallyDecoded"),
            "hasPath": (r.get("decoded") or {}).get("hasPath"),
            "hasSpeed": (r.get("decoded") or {}).get("hasSpeed"),
            "hasNetId": (r.get("decoded") or {}).get("hasNetId"),
            "bufFloatHeads": r.get("bufFloatHeads"),
            "pathHitCount": len(r.get("pathHits") or []),
        }
        for r in (driver.get("rows") or [])
    ]

    report = {
        "ok": bool(winner),
        "probeVersion": PROBE_VERSION,
        "hypothesis": "phase-b-e17-path-integrator",
        "matchCode": MATCH_CODE,
        "wallMs": round(wall_ms, 3),
        "wallTargetMs": 60_000,
        "wallPass": wall_ms <= 60_000,
        "official": prov,
        "binaryManifest": man,
        "constructorCoverage": coverage,
        "pinned": {
            "reconstruct": "encode_type || marker || wire (E11)",
            "pathSetAbsolute": hex(PATH_SET_ABSOLUTE_VA),
            "absGetter": hex(ABS_GETTER_VA),
            "absOffset": hex(ABS_POSITION_IN_PC),
            "updatePc": hex(UPDATE_PC_VA),
            "pathApply": hex(PATH_APPLY_VA),
            "pathApplySlot": "PC+0x40 (not +0xa0)",
            "packetDeserCallsPathSetAbsolute": {
                "58": False,
                "420": False,
                "908": False,
                "1104": False,
            },
            "integrateDtS": INTEGRATE_DT_S,
        },
        "framing1104": framing,
        "setMovementDriver": driver_public,
        "integration": {
            "attempted": bool(integrated),
            "sampleCount": len(integrated),
            "appliedOk": sum(1 for s in applied if s.get("getOk")),
            "dtS": INTEGRATE_DT_S,
            "note": (
                "Fixed-dt polyline walk only when structural path+speed+netId recovered; "
                "never invent waypoints"
            ),
        },
        "negativeControls": {
            "opcode908Poke": neg_908,
            "faceDirection": face,
        },
        "evaluation": {
            "winnerFound": bool(winner),
            "winner": (
                {
                    "opcode": OPCODE_SET_MOVEMENT_DRIVER,
                    "slot": "PC+0xa0",
                    "method": "1104_structural_path_tick_integrate",
                }
                if winner
                else None
            ),
            "qa": qa,
            "gates": {
                "minSamples": ACCEPT_MIN_SAMPLES,
                "minHeroes": ACCEPT_MIN_HEROES,
                "maxMedian": ACCEPT_MAX_MEDIAN,
                "maxP95": ACCEPT_MAX_P95,
                "maxMax": ACCEPT_MAX_MAX,
                "oracleTolS": ORACLE_TOL_S,
            },
            "cadenceHonesty": (
                "Integration samples are synthetic 1Hz along decoded paths only when "
                "structurally proven; 1104 itself is sparse (6 blocks on this match)"
            ),
        },
        "blocker": blocker,
        "pureDecoderDerived": bool(pure),
        "browserSafe": bool(pure),
        "productEligible": False,  # never without CreateHero/PUUID identity binding
        "identity": {"createHeroBindingDecoded": False, "productEligible": False},
    }

    if not dry_run:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        append_speed_record(
            log=SPEED_LOG,
            hypothesis="phase-b-e17-path-integrator",
            diff_label="e17-1104-path-integrate-a0",
            keep="keep" if winner else "discard",
            reason=(
                f"E17 blocker={blocker['kind']}: "
                f"{str(blocker.get('detail') or '')[:220]}"
            ),
            wall_ms=wall_ms,
            match_code=MATCH_CODE,
            extra={
                "decoderVersion": PROBE_VERSION,
                "winnerFound": bool(winner),
                "winner": report["evaluation"]["winner"],
                "blocker": blocker,
                "structurallyDecodedCount": driver.get("structurallyDecodedCount"),
                "integratedSamples": len(integrated),
                "browserSafe": bool(pure),
                "productEligible": False,
                "pureDecoderDerived": bool(pure),
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
    report = run_e17(
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
                "wallPass": report.get("wallPass"),
                "blocker": report.get("blocker"),
                "structurallyDecodedCount": (
                    report.get("setMovementDriver") or {}
                ).get("structurallyDecodedCount"),
                "pathBlobRecovered": (report.get("setMovementDriver") or {}).get(
                    "pathBlobRecovered"
                ),
                "integratedSamples": (report.get("integration") or {}).get(
                    "sampleCount"
                ),
                "winnerFound": (report.get("evaluation") or {}).get("winnerFound"),
                "qa": (report.get("evaluation") or {}).get("qa"),
                "browserSafe": report.get("browserSafe"),
                "productEligible": report.get("productEligible"),
                "pureDecoderDerived": report.get("pureDecoderDerived"),
                "report": str(args.report),
            },
            indent=2,
        )
    )
    return 0 if report.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
