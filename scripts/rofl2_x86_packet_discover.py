#!/usr/bin/env python3
"""Phase B E6: exact-patch x86-64 packet discovery (OS-neutral product target).

Why pivot: ROFL wire is platform-neutral, but vtables/layouts/allocators are
arch-specific. ROFL-X/MIT and Mowokuma prior art target Windows x86-64; Mac
ARM64 E5 correctly rejected a mismatched +0x18/+0x20 signature.

This tool:
  1. Loads Mac x86_64 slice (lipo) or PE32+ via ``rofl2_binary_format``
  2. Enumerates constructors by ``mov word [rax+8], imm16`` after ``operator new``
  3. Recovers Itanium vptr (lea rip; add 0x10) and Deserialize/Use slots
  4. Ranks MOVEMENT_PATH structurally (size~48, buffer-ish Deserialize, frequency)
  5. Optionally drives Unicorn x86-64 Deserialize on strong candidates

Factual technique (constructor id@+8 + RIP vtable) independently implemented;
do not copy third-party source. Product decoder must be pure wire/TS/WASM —
no League binary or Unicorn at end-user runtime (Windows or Mac).
"""
from __future__ import annotations

import argparse
import json
import re
import struct
import sys
import tempfile
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rofl2_binary_format import (  # noqa: E402
    LoadedBinary,
    load_binary,
    research_manifest,
)
from rofl2_probe import extract_segments, parse_rofl2  # noqa: E402
from rofl2_unicorn_packet_drive import extract_blocks_py  # noqa: E402
from rofl2_movement_decode import (  # noqa: E402
    DEFAULT_LOG,
    PROVENANCE,
    _load_oracle_positions,
    append_speed_record,
)
from rofl2_movement_emulator_probe import (  # noqa: E402
    PathParseError,
    parse_compressed_path_packet,
)
from rofl2_movement_wire_scan import (  # noqa: E402
    ACCEPT_MAX_MAX_ERROR,
    ACCEPT_MAX_MEDIAN_ERROR,
    ACCEPT_MAX_P95_ERROR,
    ACCEPT_MIN_COMPARED_SAMPLES,
    ACCEPT_MIN_STABLE_ENTITIES,
    PROVEN_HERO_NET_ID_SET,
    optimal_oracle_assignment,
)
from rofl_speed_bench import utc_now_iso  # noqa: E402

PROBE_VERSION = "e6-x86-discovery-v1"
DEFAULT_LEAGUE_BINARY = Path(
    "/Applications/League of Legends.app/Contents/LoL/Game/"
    "LeagueofLegends.app/Contents/MacOS/LeagueofLegends"
)
# Observed operator new in 16.14 Mac x86_64 factory stubs.
OPERATOR_NEW_VA_HINT = 0x10176F500


def enumerate_rofl_opcodes(rofl: Path) -> Tuple[Counter, Dict[int, List[dict]]]:
    info = parse_rofl2(rofl)
    extracted = extract_segments(info["payload"])
    counts: Counter = Counter()
    samples: Dict[int, List[dict]] = defaultdict(list)
    for seg in extracted["segments"]:
        if int(seg.get("type") or 0) != 1:
            continue
        for b in extract_blocks_py(seg["bytes"], max_blocks=500_000):
            op = int(b["channel"])
            counts[op] += 1
            pay = b["payload"] or b""
            if len(samples[op]) < 30 and 60.0 <= float(b["time"]) <= 1200.0:
                samples[op].append(
                    {"time": float(b["time"]), "param": int(b.get("param") or 0), "payload": pay}
                )
    return counts, samples


def scan_factory_stubs(binary: LoadedBinary) -> List[dict]:
    """Find ``mov edi, size; call; mov word [rax+8], opcode`` factory micro-stubs."""
    from rofl2_x86_unicorn_drive import recover_vptr_from_stub

    text_va, text_blob = binary.text_bytes()
    out: List[dict] = []
    i = 0
    while i < len(text_blob) - 16:
        if (
            text_blob[i] == 0xBF
            and text_blob[i + 5] == 0xE8
            and text_blob[i + 10 : i + 14] == b"\x66\xc7\x40\x08"
        ):
            size = struct.unpack_from("<I", text_blob, i + 1)[0]
            opcode = struct.unpack_from("<H", text_blob, i + 14)[0]
            stub_va = text_va + i
            call_rel = struct.unpack_from("<i", text_blob, i + 6)[0]
            new_va = stub_va + 5 + 5 + call_rel  # after BF.. and E8..
            vptr = recover_vptr_from_stub(binary, stub_va)
            virt: List[Optional[int]] = []
            if vptr:
                try:
                    virt = [binary.read_u64(vptr + k * 8) for k in range(6)]
                except Exception:  # noqa: BLE001
                    virt = []
            out.append(
                {
                    "opcode": opcode,
                    "objectSize": size,
                    "stubVa": stub_va,
                    "operatorNewVa": new_va,
                    "vtableLea": (vptr - 0x10) if vptr else None,
                    "vptr": vptr,
                    "virt": virt,
                    # Itanium: [0] often shared dtor-ish, [1] Deserialize, [2] Use-ish
                    "deserializeVa": virt[1] if len(virt) > 1 else None,
                    "useVa": virt[2] if len(virt) > 2 else None,
                }
            )
            i += 15
            continue
        i += 1
    return out


def score_deserialize_bufferish(binary: LoadedBinary, deser_va: int) -> dict:
    """Heuristic score for variable-length buffer decode (ROFL-X-inspired)."""
    from capstone import Cs, CS_ARCH_X86, CS_MODE_64

    md = Cs(CS_ARCH_X86, CS_MODE_64)
    try:
        blob = binary.read_va(deser_va, 0x600)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc), "score": 0}
    hits = {
        "off10": 0,
        "off18": 0,
        "off20": 0,
        "off28": 0,
        "calls": 0,
        "callNew": 0,
        "ptrStoreAfterNew": 0,
    }
    new_sites = []
    for insn in md.disasm(blob, deser_va):
        o = insn.op_str.replace(" ", "")
        if "[" in o:
            if "+0x10]" in o:
                hits["off10"] += 1
            if "+0x18]" in o:
                hits["off18"] += 1
            if "+0x20]" in o:
                hits["off20"] += 1
            if "+0x28]" in o:
                hits["off28"] += 1
        if insn.mnemonic == "call" and insn.op_str.startswith("0x"):
            hits["calls"] += 1
            tgt = int(insn.op_str, 16)
            if tgt == OPERATOR_NEW_VA_HINT or abs(tgt - OPERATOR_NEW_VA_HINT) < 0x40:
                hits["callNew"] += 1
                new_sites.append(insn.address)
        if insn.mnemonic == "ret" and hits["calls"] > 0:
            break
        if insn.address > deser_va + 0x5E0:
            break
    # Look for mov [reg+disp], rax shortly after new
    for site in new_sites[:6]:
        rel = site - deser_va
        for insn in md.disasm(blob[rel + 5 : rel + 0x30], site + 5):
            if (
                insn.mnemonic == "mov"
                and insn.op_str.endswith(", rax")
                and "[" in insn.op_str
            ):
                hits["ptrStoreAfterNew"] += 1
                break
            if insn.mnemonic == "call":
                break
    score = 0
    if hits["off18"] and hits["off20"]:
        score += 4
    if hits["off10"] and hits["off18"]:
        score += 4
    if hits["callNew"]:
        score += 3
    if hits["ptrStoreAfterNew"]:
        score += 4
    if hits["calls"] >= 3:
        score += 1
    # Classic ROFL-X: size 48 + ptr/size pair — boost when both offs present + new
    movementish = bool(
        hits["callNew"]
        and hits["ptrStoreAfterNew"]
        and (hits["off18"] or hits["off10"])
        and (hits["off20"] or hits["off18"])
    )
    return {"ok": True, "score": score, "movementish": movementish, **hits}


def validate_ctor_coverage(
    factories: Sequence[Mapping[str, Any]],
    rofl_counts: Mapping[int, int],
) -> dict:
    by_op = {int(f["opcode"]): f for f in factories}
    ops = sorted(rofl_counts)
    covered = [op for op in ops if op in by_op]
    missing = [op for op in ops if op not in by_op]
    # Spot-check: constructor-stored id equals opcode key
    id_ok = sum(1 for op in covered if int(by_op[op]["opcode"]) == op)
    return {
        "roflOpcodes": len(ops),
        "factoryStubs": len(factories),
        "uniqueFactoryOpcodes": len(by_op),
        "coveredOpcodes": len(covered),
        "coverageRatio": round(len(covered) / max(1, len(ops)), 4),
        "missingOpcodesSample": missing[:20],
        "constructorIdMatchesKey": id_ok,
        "priorArt980": by_op.get(980),
        "priorArt982": by_op.get(982),
    }


def rank_movement_candidates(
    factories: Sequence[Mapping[str, Any]],
    binary: Optional[LoadedBinary],
    rofl_counts: Mapping[int, int],
    payload_sizes: Mapping[int, int],
) -> List[dict]:
    ranked = []
    for f in factories:
        op = int(f["opcode"])
        deser = f.get("deserializeVa")
        if not deser:
            continue
        if binary is None:
            sc = {"ok": False, "score": 0, "movementish": False}
        else:
            sc = score_deserialize_bufferish(binary, int(deser))
        blocks = int(rofl_counts.get(op, 0))
        nsz = int(payload_sizes.get(op, 0))
        size = int(f["objectSize"])
        # Structural prior: prefer ~48B, variable payloads, bufferish deser
        rank = float(sc.get("score") or 0)
        if size == 48:
            rank += 3
        elif size in (32, 40, 56, 64):
            rank += 1
        if blocks >= 500:
            rank += 2
        if nsz >= 10:
            rank += 2
        if sc.get("movementish"):
            rank += 5
        if op in (980, 982):
            rank += 1  # prior-art id bonus only, never sole acceptance
        ranked.append(
            {
                **{k: f[k] for k in ("opcode", "objectSize", "stubVa", "vptr", "deserializeVa", "useVa")},
                "blocks": blocks,
                "payloadSizeCardinality": nsz,
                "deserScore": sc,
                "rankScore": rank,
            }
        )
    ranked.sort(key=lambda r: (-r["rankScore"], -r["blocks"]))
    return ranked


def unicorn_x86_try_deserialize(
    binary: LoadedBinary,
    *,
    object_size: int,
    deser_va: int,
    payload: bytes,
    opcode: int,
    stub_va: Optional[int] = None,
    expected_vptr: Optional[int] = None,
    emu: Any = None,
) -> dict:
    """Drive factory-constructed object then Deserialize.

    Fabricated zero-objects are rejected. Pass stub_va + expected_vptr (E7a).
    """
    if stub_va is None or expected_vptr is None:
        return {
            "ok": False,
            "error": "fabricated_object_rejected: stub_va and expected_vptr required",
            "fabricatedRejected": True,
            "consumed": 0,
            "pathHits": [],
            "allocs": [],
        }
    from rofl2_x86_unicorn_drive import X86PacketEmu

    engine = emu if emu is not None else X86PacketEmu(binary)
    result = engine.drive_constructed(
        stub_va=int(stub_va),
        expected_opcode=int(opcode),
        expected_vptr=int(expected_vptr),
        object_size=int(object_size),
        deser_va=int(deser_va),
        payload=payload,
    )
    fac = result.factory
    return {
        "ok": result.ok,
        "fabricatedRejected": True,
        "factoryOk": bool(fac and fac.ok),
        "factory": (
            {
                "ok": fac.ok,
                "obj": hex(fac.obj),
                "vptr": hex(fac.vptr),
                "expectedVptr": hex(fac.expectedVptr),
                "opcode": fac.opcode,
                "expectedOpcode": fac.expectedOpcode,
                "error": fac.error,
                "objectPrefixHex": fac.objectPrefixHex,
            }
            if fac
            else None
        ),
        "error": result.error,
        "failurePc": result.failurePc,
        "consumed": result.consumed,
        "allocs": result.allocs,
        "calls": result.calls,
        "buffers": result.buffers,
        "objectPrefixHex": (fac.objectPrefixHex if fac else ""),
        "objectAfterHex": result.objectAfterHex,
        "pathHits": result.pathHits,
    }


def enumerate_opcode_blocks(rofl: Path, opcode: int) -> List[dict]:
    """All blocks for one opcode across the match (not just first 12)."""
    info = parse_rofl2(rofl)
    extracted = extract_segments(info["payload"])
    out: List[dict] = []
    for seg in extracted["segments"]:
        if int(seg.get("type") or 0) != 1:
            continue
        for b in extract_blocks_py(seg["bytes"], max_blocks=500_000):
            if int(b["channel"]) != int(opcode):
                continue
            out.append(
                {
                    "time": float(b["time"]),
                    "param": int(b.get("param") or 0),
                    "payload": b["payload"] or b"",
                }
            )
    return out


def run_e7a(
    *,
    league_binary: Path,
    rofl: Path,
    oracle_jsonl: Path,
    prefer_arch: str = "x86_64",
    work_dir: Optional[Path] = None,
    primary_opcode: int = 660,
    fallback_opcode: int = 556,
    max_probe_samples: int = 80,
) -> dict:
    """E7a: properly constructed x86 packet objects (invalidate E6 fabricated negatives)."""
    from rofl2_x86_unicorn_drive import X86PacketEmu

    t0 = time.perf_counter()
    if work_dir is None:
        work_dir = Path(tempfile.mkdtemp(prefix="lol-e7a-"))
    binary = load_binary(league_binary, prefer_arch=prefer_arch, work_dir=work_dir)
    man = research_manifest(
        binary,
        patch="16.14",
        extra={
            "probeVersion": "e7a-constructed-x86-v1",
            "e6FabricatedObjectNegatives": "invalid",
            "windowsStatus": (
                "format_support_tested_synthetic_pe"
                if binary.platform != "windows"
                else "real_pe_loaded"
            ),
        },
    )
    factories = scan_factory_stubs(binary)
    by_op = {int(f["opcode"]): f for f in factories}
    oracle = _load_oracle_positions(oracle_jsonl) if oracle_jsonl.is_file() else []

    def probe_opcode(op: int) -> dict:
        fac = by_op.get(int(op))
        if not fac or not fac.get("stubVa") or not fac.get("vptr") or not fac.get("deserializeVa"):
            return {
                "opcode": op,
                "skipped": "missing_factory",
                "factoryValidation": None,
                "accepted": False,
            }
        blocks = enumerate_opcode_blocks(rofl, op)
        if not blocks:
            return {
                "opcode": op,
                "skipped": "no_rofl_payloads",
                "factory": {
                    "stubVa": hex(int(fac["stubVa"])),
                    "vptr": hex(int(fac["vptr"])),
                    "deserializeVa": hex(int(fac["deserializeVa"])),
                    "objectSize": fac["objectSize"],
                },
                "accepted": False,
            }

        # Spread samples across match (660 begins ~144s)
        n = len(blocks)
        if n <= max_probe_samples:
            sample_idxs = list(range(n))
        else:
            step = max(1, n // max_probe_samples)
            sample_idxs = list(range(0, n, step))[:max_probe_samples]

        emu = X86PacketEmu(binary)
        path_samples: List[dict] = []
        examples: List[dict] = []
        factory_ok_count = 0
        deser_ok_count = 0
        first_factory = None
        net_ids_at_c: Counter = Counter()

        for idx in sample_idxs:
            s = blocks[idx]
            # One emulator instance: constructor then Deserialize per sample (reuse maps).
            rt = unicorn_x86_try_deserialize(
                binary,
                object_size=int(fac["objectSize"]),
                deser_va=int(fac["deserializeVa"]),
                payload=s["payload"],
                opcode=op,
                stub_va=int(fac["stubVa"]),
                expected_vptr=int(fac["vptr"]),
                emu=emu,
            )
            if rt.get("factoryOk"):
                factory_ok_count += 1
            if first_factory is None:
                first_factory = rt.get("factory")
            if rt.get("ok"):
                deser_ok_count += 1
            # 660 writes encrypted netId at +0xc after constructed Deserialize
            after = rt.get("objectAfterHex") or ""
            if len(after) >= 24:
                try:
                    net_ids_at_c[struct.unpack_from("<I", bytes.fromhex(after), 0x0C)[0]] += 1
                except Exception:  # noqa: BLE001
                    pass
            if len(examples) < 4:
                examples.append(
                    {
                        "time": round(float(s["time"]), 3),
                        "payloadLen": len(s["payload"]),
                        "factoryOk": rt.get("factoryOk"),
                        "ok": rt.get("ok"),
                        "consumed": rt.get("consumed"),
                        "error": rt.get("error"),
                        "failurePc": rt.get("failurePc"),
                        "pathHits": rt.get("pathHits"),
                        "buffers": (rt.get("buffers") or [])[:4],
                        "objectAfterHex": rt.get("objectAfterHex"),
                        "allocs": rt.get("allocs"),
                    }
                )
            for hit in rt.get("pathHits") or []:
                path_samples.append(
                    {
                        "time": float(s["time"]),
                        "netId": int(hit["entityId"]),
                        "x": float(hit["x"]),
                        "z": float(hit["z"]),
                        "speed": float(hit["speed"]),
                        "points": [{"x": hit["x"], "z": hit["z"]}],
                    }
                )

        # If any PathPacket hit on probe, decode ALL blocks
        full_path_samples = path_samples
        decoded_all = False
        if path_samples:
            decoded_all = True
            full_path_samples = []
            for s in blocks:
                rt = unicorn_x86_try_deserialize(
                    binary,
                    object_size=int(fac["objectSize"]),
                    deser_va=int(fac["deserializeVa"]),
                    payload=s["payload"],
                    opcode=op,
                    stub_va=int(fac["stubVa"]),
                    expected_vptr=int(fac["vptr"]),
                    emu=emu,
                )
                for hit in rt.get("pathHits") or []:
                    full_path_samples.append(
                        {
                            "time": float(s["time"]),
                            "netId": int(hit["entityId"]),
                            "x": float(hit["x"]),
                            "z": float(hit["z"]),
                            "speed": float(hit["speed"]),
                            "points": [{"x": hit["x"], "z": hit["z"]}],
                        }
                    )

        qa = None
        accepted = False
        if full_path_samples and oracle:
            qa = optimal_oracle_assignment(full_path_samples, oracle, tolerance_s=0.5)
            accepted = bool(
                qa.get("methodPassed")
                and int(qa.get("assignmentCount") or 0) >= ACCEPT_MIN_STABLE_ENTITIES
                and int(qa.get("comparedSamples") or 0) >= ACCEPT_MIN_COMPARED_SAMPLES
                and float(qa.get("medianError") or 1e9) <= ACCEPT_MAX_MEDIAN_ERROR
                and float(qa.get("p95Error") or 1e9) <= ACCEPT_MAX_P95_ERROR
                and float(qa.get("maxError") or 1e9) <= ACCEPT_MAX_MAX_ERROR
            )

        return {
            "opcode": op,
            "objectSize": fac["objectSize"],
            "stubVa": hex(int(fac["stubVa"])),
            "vptr": hex(int(fac["vptr"])),
            "deserializeVa": hex(int(fac["deserializeVa"])),
            "blockCount": len(blocks),
            "timeRange": (
                [round(blocks[0]["time"], 3), round(blocks[-1]["time"], 3)]
                if blocks
                else None
            ),
            "probeSampleCount": len(sample_idxs),
            "factoryOkCount": factory_ok_count,
            "deserOkCount": deser_ok_count,
            "factoryValidation": first_factory,
            "netIdAtPlus0cTop": [
                {"netId": hex(k), "count": v} for k, v in net_ids_at_c.most_common(8)
            ],
            "pathSampleCount": len(full_path_samples),
            "heroPathCount": sum(
                1 for p in full_path_samples if int(p["netId"]) in PROVEN_HERO_NET_ID_SET
            ),
            "decodedAllBlocks": decoded_all,
            "oracleQa": (
                {
                    k: (qa or {}).get(k)
                    for k in (
                        "assignmentCount",
                        "comparedSamples",
                        "medianError",
                        "p95Error",
                        "maxError",
                        "methodPassed",
                    )
                }
                if qa
                else None
            ),
            "accepted": accepted,
            "examples": examples,
            "semantic": (
                "pathpacket_oracle_pass"
                if accepted
                else (
                    "pathpacket_hits_oracle_fail"
                    if full_path_samples
                    else (
                        "netid_field_packet_not_pathpacket"
                        if net_ids_at_c and op == 660
                        else "no_pathpacket_after_constructed_deserialize"
                    )
                )
            ),
        }

    primary = probe_opcode(primary_opcode)
    fallback = None
    winner = primary if primary.get("accepted") else None
    if not primary.get("accepted"):
        # Only run 556 if 660 fails semantically (no PathPacket or QA fail)
        fallback = probe_opcode(fallback_opcode)
        if fallback.get("accepted"):
            winner = fallback

    wall_ms = (time.perf_counter() - t0) * 1000
    pure_derived = False
    browser_safe = False
    product_eligible = False
    # Product path only if pure wire derived without Unicorn at runtime — not yet.
    if winner and winner.get("accepted"):
        pure_derived = False
        browser_safe = False
        product_eligible = False

    e6_invalid = {
        "status": "invalid",
        "reason": (
            "E6 unicorn_x86_try_deserialize fabricated a zero object with only "
            "opcode@+8 and never called stubVa; also vtable recovery could bleed "
            "into the next factory stub (wrong Deserialize for opcode 660)."
        ),
        "replacement": "E7a constructed factory→Deserialize drive",
    }

    return {
        "ok": True,
        "phase": "B-E7a",
        "probeVersion": "e7a-constructed-x86-v1",
        "provenance": PROVENANCE,
        "e6FabricatedObjectNegatives": e6_invalid,
        "binaryManifest": man,
        "primaryOpcode": primary_opcode,
        "primary": primary,
        "fallbackOpcode": fallback_opcode,
        "fallback": fallback,
        "winner": winner,
        "winnerFound": winner is not None,
        "pureBrowserDecoderDerived": pure_derived,
        "browserSafe": browser_safe,
        "productEligible": product_eligible,
        "windowsFormatSupport": "tested_via_synthetic_pe_fixtures",
        "windowsRealBinaryValidated": False,
        "endToEndWallMs": round(wall_ms, 3),
        "keep": "keep-research" if winner is not None else "discard",
        "reason": (
            f"E7a opcode={winner['opcode']} constructed PathPacket+oracle passed"
            if winner
            else (
                f"E7a: constructed drive on {primary_opcode} "
                f"semantic={primary.get('semantic')}; "
                + (
                    f"fallback {fallback_opcode} semantic={fallback.get('semantic')}"
                    if fallback
                    else "no fallback"
                )
            )
        ),
        "nextSingleVariableHypothesis": (
            "E7b: derive pure wire parser/manifest from proven constructed decode"
            if winner
            else "E7b: deepen alloc/copy hooks on constructed 660/556 or Windows PE"
        ),
    }


def run_e6(
    *,
    league_binary: Path,
    rofl: Path,
    oracle_jsonl: Path,
    prefer_arch: str = "x86_64",
    max_emulate: int = 5,
    work_dir: Optional[Path] = None,
) -> dict:
    t0 = time.perf_counter()
    if work_dir is None:
        work_dir = Path(tempfile.mkdtemp(prefix="lol-e6-"))
    binary = load_binary(league_binary, prefer_arch=prefer_arch, work_dir=work_dir)
    man = research_manifest(
        binary,
        patch="16.14",
        extra={
            "probeVersion": PROBE_VERSION,
            "windowsStatus": (
                "format_support_tested_synthetic_pe"
                if binary.platform != "windows"
                else "real_pe_loaded"
            ),
        },
    )
    factories = scan_factory_stubs(binary)
    counts, samples = enumerate_rofl_opcodes(rofl)
    payload_card = {
        op: len({len(s["payload"]) for s in samples.get(op, [])}) for op in counts
    }
    # Also compute cardinality from a fuller pass already in samples; improve with counts-only sizes from inventory if needed
    coverage = validate_ctor_coverage(factories, counts)
    ranked = rank_movement_candidates(factories, binary, counts, payload_card)

    oracle = _load_oracle_positions(oracle_jsonl) if oracle_jsonl.is_file() else []
    emulate_reports = []
    winner = None
    # Emulate top structural candidates that have ROFL blocks, plus prior-art 980 if present
    targets = []
    for r in ranked:
        if r["blocks"] > 0 and r["rankScore"] >= 8:
            targets.append(r)
        if len(targets) >= max_emulate:
            break
    f980 = next((f for f in factories if int(f["opcode"]) == 980), None)
    if f980 and all(int(t["opcode"]) != 980 for t in targets):
        targets.append(
            {
                **{k: f980[k] for k in ("opcode", "objectSize", "stubVa", "vptr", "deserializeVa", "useVa")},
                "blocks": 0,
                "payloadSizeCardinality": 0,
                "deserScore": score_deserialize_bufferish(binary, int(f980["deserializeVa"] or 0))
                if f980.get("deserializeVa")
                else {},
                "rankScore": -1,
                "note": "prior-art opcode 980 (may have 0 ROFL blocks)",
            }
        )

    for t in targets:
        op = int(t["opcode"])
        deser = t.get("deserializeVa")
        if not deser:
            continue
        path_samples = []
        runtime_examples = []
        samp = samples.get(op) or []
        if not samp and op == 980:
            # No wire samples — record static-only
            emulate_reports.append(
                {
                    "opcode": op,
                    "objectSize": t["objectSize"],
                    "deserializeVa": hex(int(deser)),
                    "skipped": "no_rofl_payloads",
                    "deserScore": t.get("deserScore"),
                }
            )
            continue
        for s in samp[:12]:
            rt = unicorn_x86_try_deserialize(
                binary,
                object_size=int(t["objectSize"]),
                deser_va=int(deser),
                payload=s["payload"],
                opcode=op,
                stub_va=int(t["stubVa"]) if t.get("stubVa") else None,
                expected_vptr=int(t["vptr"]) if t.get("vptr") else None,
            )
            if len(runtime_examples) < 3:
                runtime_examples.append(
                    {
                        "time": round(float(s["time"]), 3),
                        "payloadLen": len(s["payload"]),
                        "ok": rt.get("ok"),
                        "consumed": rt.get("consumed"),
                        "error": rt.get("error"),
                        "pathHits": rt.get("pathHits"),
                        "allocs": rt.get("allocs"),
                    }
                )
            for hit in rt.get("pathHits") or []:
                path_samples.append(
                    {
                        "time": float(s["time"]),
                        "netId": int(hit["entityId"]),
                        "x": float(hit["x"]),
                        "z": float(hit["z"]),
                        "speed": float(hit["speed"]),
                        "points": [{"x": hit["x"], "z": hit["z"]}],
                    }
                )
        qa = None
        accepted = False
        if path_samples and oracle:
            qa = optimal_oracle_assignment(path_samples, oracle, tolerance_s=0.5)
            accepted = bool(
                qa.get("methodPassed")
                and int(qa.get("assignmentCount") or 0) >= ACCEPT_MIN_STABLE_ENTITIES
                and int(qa.get("comparedSamples") or 0) >= ACCEPT_MIN_COMPARED_SAMPLES
                and float(qa.get("medianError") or 1e9) <= ACCEPT_MAX_MEDIAN_ERROR
                and float(qa.get("p95Error") or 1e9) <= ACCEPT_MAX_P95_ERROR
                and float(qa.get("maxError") or 1e9) <= ACCEPT_MAX_MAX_ERROR
            )
        rec = {
            "opcode": op,
            "objectSize": t["objectSize"],
            "deserializeVa": hex(int(deser)),
            "rankScore": t.get("rankScore"),
            "deserScore": t.get("deserScore"),
            "pathSampleCount": len(path_samples),
            "heroPathCount": sum(
                1 for p in path_samples if int(p["netId"]) in PROVEN_HERO_NET_ID_SET
            ),
            "oracleQa": (
                {
                    k: (qa or {}).get(k)
                    for k in (
                        "assignmentCount",
                        "comparedSamples",
                        "medianError",
                        "p95Error",
                        "maxError",
                        "methodPassed",
                    )
                }
                if qa
                else None
            ),
            "accepted": accepted,
            "examples": runtime_examples,
        }
        emulate_reports.append(rec)
        if accepted and winner is None:
            winner = rec

    wall_ms = (time.perf_counter() - t0) * 1000
    pure = {
        "decoderVersion": "e6-pending-wire-v0",
        "productEligible": False,
        "browserSafe": False,
        "requiresLeagueBinary": True,
        "requiresUnicorn": True,
        "osNeutralWireGoal": True,
        "platforms": ["windows", "macos"],
        "architecture": (
            "Offline per-patch manifests derived on PE (Windows) or Mach-O x86_64 "
            "(Mac universal thin). One shared TS/WASM PathPacket/wire decoder in "
            "browser Worker; optional Blob+background worker for unknown patches. "
            "Never ship League binary or Unicorn to Vercel/browser."
        ),
        "windowsStatus": man.get("windowsStatus"),
    }
    blocker = None
    if winner is None:
        p980 = coverage.get("priorArt980")
        blocker = {
            "kind": "x86_movement_path_not_proven",
            "detail": (
                "Constructor/vtable discovery on exact-patch x86_64 succeeded with "
                "high ROFL opcode coverage, but no candidate produced PathPacket "
                "buffers that pass oracle gates under Unicorn x86 Deserialize. "
                "Prior-art opcode 980 exists as a factory type but objectSize="
                f"{(p980 or {}).get('objectSize')} (not classic 48) and "
                f"blocks={(counts.get(980, 0))} on this ROFL."
            ),
            "topRanked": [
                {
                    "opcode": r["opcode"],
                    "objectSize": r["objectSize"],
                    "blocks": r["blocks"],
                    "rankScore": r["rankScore"],
                    "movementish": (r.get("deserScore") or {}).get("movementish"),
                }
                for r in ranked[:8]
            ],
        }

    return {
        "ok": True,
        "phase": "B-E6",
        "probeVersion": PROBE_VERSION,
        "provenance": PROVENANCE,
        "attribution": {
            "roflX": "Toastaspiring/ROFL-X (MIT) — layout/prior opcode facts only",
            "ctorTechnique": (
                "Independent implementation of public constructor id@object+8 + "
                "RIP-relative vtable recovery (quomark-style facts; no source copied; "
                "upstream license not established)"
            ),
        },
        "binaryManifest": man,
        "constructorCoverage": coverage,
        "movementRanked": ranked[:25],
        "emulateReports": emulate_reports,
        "winner": winner,
        "winnerFound": winner is not None,
        "structuralBlocker": blocker,
        "pureDecoderConfig": pure,
        "productEligible": False,
        "browserSafe": False,
        "pureBrowserDecoderDerived": False,
        "osNeutralArchitectureDocumented": True,
        "windowsFormatSupport": "tested_via_synthetic_pe_fixtures",
        "windowsRealBinaryValidated": False,
        "endToEndWallMs": round(wall_ms, 3),
        "keep": "keep-research" if winner is not None else "discard",
        "reason": (
            f"E6 movement opcode={winner['opcode']} PathPacket+oracle passed on x86"
            if winner
            else "E6 discard: x86 constructor map ok, but MOVEMENT_PATH PathPacket "
            "not proven under Unicorn for observed opcodes"
        ),
        "nextSingleVariableHypothesis": (
            "E7: productize pure wire decoder from proven x86-derived manifest"
            if winner
            else "E7: run same scanner against a real Windows 16.14 PE (format already "
            "supported) or deepen x86 Deserialize alloc hooks / UsePacket bind for "
            "top-ranked size-48 types (556/107) without assuming ARM64 offsets"
        ),
    }


def build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--league-binary",
        type=Path,
        default=DEFAULT_LEAGUE_BINARY,
        help="Mach-O universal/thin or PE32+ path (auto-detected)",
    )
    ap.add_argument(
        "--rofl",
        type=Path,
        default=Path.home()
        / "Documents/League of Legends/Replays/BR1-3264361042.rofl",
    )
    ap.add_argument(
        "--oracle-jsonl",
        type=Path,
        default=Path("artifacts/rofl/3264361042/events.rfc461.jsonl"),
    )
    ap.add_argument("--prefer-arch", default="x86_64")
    ap.add_argument("--max-emulate", type=int, default=5)
    ap.add_argument(
        "--e7a",
        action="store_true",
        help="Run E7a constructed-object drive (opcode 660 then 556)",
    )
    ap.add_argument("--max-probe-samples", type=int, default=80)
    ap.add_argument("--json-out", type=Path, default=None)
    ap.add_argument("--append-speed-run", action="store_true")
    ap.add_argument("--log", type=Path, default=DEFAULT_LOG)
    ap.add_argument("--hypothesis", default="")
    ap.add_argument("--diff-label", default="")
    ap.add_argument("--match-code", default="3264361042")
    ap.add_argument("--dry-run", action="store_true")
    return ap


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    if not args.league_binary.is_file():
        print(f"missing binary: {args.league_binary}", file=sys.stderr)
        return 2
    if not args.rofl.is_file():
        print(f"missing rofl: {args.rofl}", file=sys.stderr)
        return 2

    if args.e7a:
        report = run_e7a(
            league_binary=args.league_binary,
            rofl=args.rofl,
            oracle_jsonl=args.oracle_jsonl,
            prefer_arch=args.prefer_arch,
            max_probe_samples=int(args.max_probe_samples),
        )
        diff_label = args.diff_label or "phase-b-e7a-constructed"
        hypothesis = (
            args.hypothesis
            or "E7a: properly constructed x86 factory object then Deserialize"
        )
        phase = "B-E7a"
        source = "offline_e7a_constructed_x86"
    else:
        report = run_e6(
            league_binary=args.league_binary,
            rofl=args.rofl,
            oracle_jsonl=args.oracle_jsonl,
            prefer_arch=args.prefer_arch,
            max_emulate=int(args.max_emulate),
        )
        diff_label = args.diff_label or "phase-b-e6-x86"
        hypothesis = (
            args.hypothesis
            or "E6: exact-patch x86_64 constructor/vtable MOVEMENT_PATH discovery"
        )
        phase = "B-E6"
        source = "offline_e6_x86_discovery"

    if args.append_speed_run:
        rec = append_speed_record(
            log=args.log,
            hypothesis=hypothesis,
            diff_label=diff_label,
            keep="discard" if not report.get("winnerFound") else report["keep"],
            reason=report["reason"],
            wall_ms=float(report["endToEndWallMs"]),
            match_code=args.match_code,
            dry_run=args.dry_run,
            extra={
                "phase": phase,
                "winnerFound": report["winnerFound"],
                "winner": report.get("winner"),
                "primary": report.get("primary"),
                "fallback": report.get("fallback"),
                "e6FabricatedObjectNegatives": report.get("e6FabricatedObjectNegatives"),
                "constructorCoverage": report.get("constructorCoverage"),
                "structuralBlocker": report.get("structuralBlocker"),
                "binaryManifest": report.get("binaryManifest"),
                "pureBrowserDecoderDerived": report.get("pureBrowserDecoderDerived"),
                "browserSafe": report.get("browserSafe"),
                "windowsFormatSupport": report.get("windowsFormatSupport"),
                "windowsRealBinaryValidated": report.get("windowsRealBinaryValidated"),
                "endToEndWallMs": report.get("endToEndWallMs"),
                "nextSingleVariableHypothesis": report.get(
                    "nextSingleVariableHypothesis"
                ),
                "statsUpdateCount": 0,
                "source": source,
                "researchKeep": report.get("keep"),
                "ts": utc_now_iso(),
            },
        )
        report["speedRun"] = rec

    disk = dict(report)
    if args.json_out is not None:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        cov = dict(disk.get("constructorCoverage") or {})
        for key in ("priorArt980", "priorArt982"):
            ent = cov.get(key)
            if isinstance(ent, dict):
                cov[key] = {
                    k: (hex(v) if isinstance(v, int) and v > 0x10000 else v)
                    for k, v in ent.items()
                    if k != "virt"
                } | {"virt": [hex(x) if x else None for x in (ent.get("virt") or [])]}
        if cov:
            disk["constructorCoverage"] = cov
        ranked = []
        for r in disk.get("movementRanked") or []:
            rr = dict(r)
            for k in ("stubVa", "vptr", "deserializeVa", "useVa"):
                if isinstance(rr.get(k), int):
                    rr[k] = hex(rr[k])
            ranked.append(rr)
        if ranked:
            disk["movementRanked"] = ranked
        args.json_out.write_text(
            json.dumps(disk, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        report["jsonOut"] = str(args.json_out)

    if args.e7a:
        summary = {
            "phase": report["phase"],
            "winnerFound": report["winnerFound"],
            "factoryValidation": (report.get("primary") or {}).get("factoryValidation"),
            "primary": {
                k: (report.get("primary") or {}).get(k)
                for k in (
                    "opcode",
                    "objectSize",
                    "stubVa",
                    "vptr",
                    "deserializeVa",
                    "blockCount",
                    "factoryOkCount",
                    "deserOkCount",
                    "pathSampleCount",
                    "heroPathCount",
                    "oracleQa",
                    "accepted",
                    "semantic",
                )
            },
            "fallback": (
                {
                    k: (report.get("fallback") or {}).get(k)
                    for k in (
                        "opcode",
                        "semantic",
                        "pathSampleCount",
                        "oracleQa",
                        "accepted",
                        "factoryOkCount",
                    )
                }
                if report.get("fallback")
                else None
            ),
            "e6FabricatedObjectNegatives": report.get("e6FabricatedObjectNegatives"),
            "endToEndWallMs": report["endToEndWallMs"],
            "keep": report["keep"],
            "reason": report["reason"],
            "browserSafe": report["browserSafe"],
            "pureBrowserDecoderDerived": report["pureBrowserDecoderDerived"],
            "productEligible": report.get("productEligible"),
            "windowsFormatSupport": report["windowsFormatSupport"],
            "windowsRealBinaryValidated": report["windowsRealBinaryValidated"],
            "nextSingleVariableHypothesis": report.get("nextSingleVariableHypothesis"),
            "jsonOut": report.get("jsonOut"),
        }
    else:
        summary = {
            "phase": report["phase"],
            "winnerFound": report["winnerFound"],
            "winner": report.get("winner"),
            "structuralBlocker": report.get("structuralBlocker"),
            "constructorCoverage": {
                k: (report.get("constructorCoverage") or {}).get(k)
                for k in (
                    "roflOpcodes",
                    "factoryStubs",
                    "coveredOpcodes",
                    "coverageRatio",
                    "constructorIdMatchesKey",
                )
            },
            "endToEndWallMs": report["endToEndWallMs"],
            "keep": report["keep"],
            "reason": report["reason"],
            "browserSafe": report["browserSafe"],
            "pureBrowserDecoderDerived": report["pureBrowserDecoderDerived"],
            "jsonOut": report.get("jsonOut"),
        }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
