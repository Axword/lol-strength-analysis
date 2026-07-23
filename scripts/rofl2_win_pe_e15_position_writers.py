#!/usr/bin/env python3
"""E15: Who writes absolute map XYZ into the E14 GetPosition slot (PC+0x20)?

Pinned E14 geometry (not re-discovered):
  GetPosition @0x1403030c0 = lea rax,[rcx+0x20]; ret
  PathController at hero+0x28d0; GetPosition Vector3 at PC+0x20 (= hero+0x28f0)
  PathSetPositionCore @0x140389200 writes *normalized direction* into +0x20

Hard constraints: no live API, no plan edit, no commit, no binary vendoring,
no learned affine. Axis-swap only.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import statistics
import struct
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from capstone import CS_ARCH_X86, CS_MODE_64, Cs  # noqa: E402
from unicorn import UC_HOOK_CODE  # noqa: E402
from unicorn.x86_const import (  # noqa: E402
    UC_X86_REG_RAX,
    UC_X86_REG_RIP,
    UC_X86_REG_RSP,
)

from rofl2_binary_format import load_binary, research_manifest  # noqa: E402
from rofl2_movement_decode import (  # noqa: E402
    _load_oracle_positions,
    append_speed_record,
)
from rofl2_win_pe_e11_reconstructed_drive import (  # noqa: E402
    OPCODE_DIRECT_INPUT,
)
from rofl2_win_pe_e14_position_getters import (  # noqa: E402
    ACCEPT_MAX_MAX,
    ACCEPT_MAX_MEDIAN,
    ACCEPT_MAX_P95,
    ACCEPT_MIN_HEROES,
    ACCEPT_MIN_SAMPLES,
    GET_POSITION_VA,
    HERO_POSITION_ABS,
    MAX_SAMPLES_58,
    MAX_SAMPLES_908,
    OPCODE_NEAR_MISS,
    ORACLE_TOL_S,
    PATH_CONTROLLER_IN_HERO,
    PATH_SET_POSITION_CORE_VA,
    POSITION_IN_PATH_CONTROLLER,
    capture_908_xyz,
    capture_direct_input_xyz,
    collect_blocks,
    diversify,
    nearest_oracle,
    score_errs,
    unicorn_call,
)
from rofl2_win_pe_packet_discover import (  # noqa: E402
    WinX64PacketEmu,
    enumerate_rofl,
    official_provenance,
    scan_msvc_packet_types,
)

PROBE_VERSION = "e15-win-pe-position-writers-v1"
MATCH_CODE = "3264361042"
DEFAULT_PE = Path("/tmp/League-of-Legends-16.14-win.exe")
DEFAULT_ROFL = Path.home() / "Documents/League of Legends/Replays/BR1-3264361042.rofl"
DEFAULT_ORACLE = Path("artifacts/rofl/3264361042/events.rfc461.jsonl")
DEFAULT_REPORT = Path("docs/rofl-research/movement-win-pe-e15-BR1-3264361042.json")
SPEED_LOG = Path("docs/rofl-research/speed-runs.jsonl")

# Absolute world XYZ (E15 discovery): PathController+0xa0, not GetPosition+0x20.
PATH_SET_ABSOLUTE_VA = 0x1403891A0  # copies rdx Vector3 → PC+0xa0; may call core
ABS_POSITION_IN_PC = 0xA0
ABS_GETTER_VA = 0x140305350  # lea rax,[rcx+0xa0]; ret
VALIDATE_VEC3_VA = 0x141181330  # finite check used by PathSetAbsolute
PC_REGION = (0x140380000, 0x1403A0000)

STACK_REGS = frozenset({"rsp", "rbp", "esp", "ebp"})


def _md() -> Cs:
    return Cs(CS_ARCH_X86, CS_MODE_64)


def _f32_map(v: float) -> bool:
    return v == v and -200.0 <= v <= 16000.0 and abs(v) > 50.0


def _callers_of(text_va: int, text: bytes, target: int) -> List[int]:
    out = []
    for m in re.finditer(rb"\xe8....", text):
        i = m.start()
        va = text_va + i
        rel = struct.unpack_from("<i", text, i + 1)[0]
        if va + 5 + rel == target:
            out.append(va)
    return out


def scan_pc20_writers(binary: Any) -> dict:
    """Static scan: movss stores to non-stack [reg+0x20] with nearby +0x28."""
    md = _md()
    text_va, text = binary.text_bytes()
    stores_20: List[Tuple[int, str, str]] = []
    for m in re.finditer(rb"\xf3\x0f\x11", text):
        i = m.start()
        va = text_va + i
        try:
            insn = next(md.disasm(text[i : i + 14], va))
        except StopIteration:
            continue
        if insn.mnemonic != "movss" or not insn.op_str.startswith("dword ptr ["):
            continue
        left, _, _src = insn.op_str.partition(", ")
        if "+ 0x20]" not in left:
            continue
        if any(s in left for s in STACK_REGS):
            continue
        stores_20.append((va, left, _src))

    writers: List[dict] = []
    for va, left, src in stores_20:
        win = list(md.disasm(binary.read_va(va - 0x80, 0x100), va - 0x80))
        has_z = any(
            i.address > va
            and i.address <= va + 0x40
            and i.mnemonic == "movss"
            and "+ 0x28]" in i.op_str
            for i in win
        )
        if not has_z:
            continue
        before = [i for i in win if i.address < va]
        has_sqrt = any(
            i.mnemonic in ("sqrtss", "rsqrtss", "divss", "mulss")
            and ("sqrt" in i.mnemonic or i.mnemonic == "divss")
            for i in before
        )
        # PathSetCore uses helper call 0x1411847b0 instead of inline sqrtss
        calls_norm_helper = any(
            i.mnemonic == "call" and "0x1411847b0" in i.op_str for i in before
        )
        loads_from_rdx = any(
            i.mnemonic == "movss"
            and i.op_str.startswith("xmm")
            and "[rdx" in i.op_str
            for i in before
        )
        is_known_core = PATH_SET_POSITION_CORE_VA <= va < PATH_SET_POSITION_CORE_VA + 0x180
        in_pc_region = PC_REGION[0] <= va < PC_REGION[1]
        # Scale-in-place (mulss then store same slot) ≠ absolute map write
        scale_inplace = any(
            i.mnemonic == "mulss" and "+ 0x20]" in i.op_str for i in before[-8:]
        )
        kind = "unknown"
        if is_known_core or calls_norm_helper:
            kind = "direction_normalize"
        elif has_sqrt:
            kind = "direction_normalize_likely"
        elif scale_inplace:
            kind = "scale_inplace"
        elif loads_from_rdx and not has_sqrt:
            # Still not proof of map XYZ — often matrix/struct field copies
            kind = "struct_field_copy"
        else:
            kind = "other_vector3_store"

        writers.append(
            {
                "storeVa": hex(va),
                "dest": left,
                "src": src,
                "kind": kind,
                "inPathControllerRegion": in_pc_region,
                "isPathSetPositionCore": is_known_core,
                "hasSqrtOrNormHelper": bool(has_sqrt or calls_norm_helper),
                "loadsFromRdx": loads_from_rdx,
            }
        )

    # Dedupe by storeVa
    by_va = {w["storeVa"]: w for w in writers}
    writers = list(by_va.values())
    kinds: Dict[str, int] = defaultdict(int)
    for w in writers:
        kinds[w["kind"]] += 1

    pc_region = [w for w in writers if w["inPathControllerRegion"]]
    absolute_to_pc20 = [
        w
        for w in writers
        if w["kind"] not in (
            "direction_normalize",
            "direction_normalize_likely",
            "scale_inplace",
        )
        and w["inPathControllerRegion"]
    ]

    core_callers = _callers_of(text_va, text, PATH_SET_POSITION_CORE_VA)
    parent_callers = _callers_of(text_va, text, PATH_SET_ABSOLUTE_VA)

    # Absolute slot +0xa0 inventory (related, not GetPosition)
    abs_a0_sites = []
    for m in re.finditer(rb"\x89[\x80-\x8f]\xa0\x00\x00\x00", text):
        va = text_va + m.start()
        try:
            insn = next(md.disasm(text[m.start() : m.start() + 8], va))
        except StopIteration:
            continue
        if "+ 0xa0]" not in insn.op_str:
            continue
        window = binary.read_va(va, 0x30)
        if b"\xa4\x00\x00\x00" in window and b"\xa8\x00\x00\x00" in window:
            abs_a0_sites.append({"storeVa": hex(va), "op": insn.op_str})

    abs_getter_bytes = binary.read_va(ABS_GETTER_VA, 8).hex()
    abs_getter_ok = abs_getter_bytes.startswith("488d81a0000000")  # lea rax,[rcx+0xa0]

    return {
        "e14Pinned": {
            "getPositionVa": hex(GET_POSITION_VA),
            "pathControllerInHero": hex(PATH_CONTROLLER_IN_HERO),
            "positionInPathController": hex(POSITION_IN_PATH_CONTROLLER),
            "heroGetPositionSlot": hex(HERO_POSITION_ABS),
            "pathSetPositionCoreVa": hex(PATH_SET_POSITION_CORE_VA),
        },
        "nonStackMovssPlus20": len(stores_20),
        "vector3ClustersPlus20Plus28": len(writers),
        "kindCounts": dict(kinds),
        "pathControllerRegionWriters": pc_region,
        "absoluteWritersToPc20": absolute_to_pc20,
        "absoluteWritersToPc20Count": len(absolute_to_pc20),
        "pathSetCoreCallers": [hex(c) for c in core_callers],
        "pathSetAbsoluteVa": hex(PATH_SET_ABSOLUTE_VA),
        "pathSetAbsoluteCallersCount": len(parent_callers),
        "pathSetAbsoluteCallersSample": [hex(c) for c in parent_callers[:20]],
        "absoluteSlot": {
            "offsetInPathController": hex(ABS_POSITION_IN_PC),
            "heroAbsolute": hex(PATH_CONTROLLER_IN_HERO + ABS_POSITION_IN_PC),
            "writerPrimary": hex(PATH_SET_ABSOLUTE_VA),
            "writerBehavior": (
                "copy rdx Vector3 → PC+0xa0/+0xa4/+0xa8; if flags clear, call "
                "PathSetPositionCore which writes *direction* into PC+0x20"
            ),
            "getterVa": hex(ABS_GETTER_VA),
            "getterDisasm": "lea rax, [rcx + 0xa0] ; ret",
            "getterBytesHex": abs_getter_bytes,
            "getterPatternOk": abs_getter_ok,
            "directE8CallersOfAbsGetter": len(_callers_of(text_va, text, ABS_GETTER_VA)),
            "dwordCopySitesA0A4A8": len(abs_a0_sites),
            "dwordCopySitesSample": abs_a0_sites[:12],
        },
        "conclusionPc20": (
            "GetPosition slot PC+0x20 has no absolute map-XYZ writers in the "
            "PathController region; only PathSetPositionCore direction normalize "
            "writes the Vector3 there. Absolute map XYZ is stored at PC+0xa0."
        ),
    }


def prove_absolute_vs_direction(binary: Any) -> dict:
    """Unicorn: PathSetAbsolute writes map XYZ to +0xa0; +0x20 becomes direction."""
    emu = WinX64PacketEmu(binary)
    hero = emu._alloc(0x4000, kind="hero", pc=0)
    pc = hero + PATH_CONTROLLER_IN_HERO
    emu.mu.mem_write(pc + 0x50, bytes([0]))
    emu.mu.mem_write(pc + 0xB9, bytes([0]))
    vec = emu._alloc(16, kind="vec", pc=0)
    x, y, z = 3500.0, 100.0, 7200.0
    emu.mu.mem_write(vec, struct.pack("<fff", x, y, z))

    def force_validate_true(uc: Any, address: int, size: int, user: Any) -> None:
        uc.reg_write(UC_X86_REG_RAX, 1)
        rsp = uc.reg_read(UC_X86_REG_RSP)
        ret = struct.unpack("<Q", bytes(uc.mem_read(rsp, 8)))[0]
        uc.reg_write(UC_X86_REG_RSP, rsp + 8)
        uc.reg_write(UC_X86_REG_RIP, ret)

    h = emu.mu.hook_add(
        UC_HOOK_CODE, force_validate_true, begin=VALIDATE_VEC3_VA, end=VALIDATE_VEC3_VA
    )
    err = None
    try:
        unicorn_call(emu, fn=PATH_SET_ABSOLUTE_VA, rcx=pc, rdx=vec)
    except Exception as exc:  # noqa: BLE001
        err = str(exc)
    try:
        emu.mu.hook_del(h)
    except Exception:  # noqa: BLE001
        pass

    a0 = struct.unpack("<fff", bytes(emu.mu.mem_read(pc + ABS_POSITION_IN_PC, 12)))
    p20 = struct.unpack("<fff", bytes(emu.mu.mem_read(pc + POSITION_IN_PATH_CONTROLLER, 12)))
    n = math.sqrt(x * x + z * z) or 1.0
    abs_rax = unicorn_call(emu, fn=ABS_GETTER_VA, rcx=pc)
    abs_got = struct.unpack("<fff", bytes(emu.mu.mem_read(abs_rax, 12)))
    gp_rax = unicorn_call(emu, fn=GET_POSITION_VA, rcx=pc)
    gp_got = struct.unpack("<fff", bytes(emu.mu.mem_read(gp_rax, 12)))
    return {
        "ok": err is None,
        "error": err,
        "input": [x, y, z],
        "slotA0": list(a0),
        "slot20": list(p20),
        "absGetter": list(abs_got),
        "getPosition": list(gp_got),
        "a0HoldsAbsolute": abs(a0[0] - x) < 1e-2 and abs(a0[2] - z) < 1e-2,
        "slot20HoldsDirection": abs(p20[0] - x / n) < 1e-2 and abs(p20[2] - z / n) < 1e-2,
        "absGetterMatchesA0": abs(abs_got[0] - a0[0]) < 1e-3,
        "getPositionMatches20": abs(gp_got[0] - p20[0]) < 1e-3,
    }


def apply_path_set_absolute(
    binary: Any, samples: Sequence[dict]
) -> List[dict]:
    """Drive PathSetAbsolute with packet XYZ; capture +0xa0 via abs getter."""
    out = []
    for s in samples:
        emu = WinX64PacketEmu(binary)
        hero = emu._alloc(0x4000, kind="hero", pc=0)
        pc = hero + PATH_CONTROLLER_IN_HERO
        emu.mu.mem_write(pc + 0x50, bytes([0]))
        emu.mu.mem_write(pc + 0xB9, bytes([0]))
        vec = emu._alloc(16, kind="vec", pc=0)
        emu.mu.mem_write(
            vec, struct.pack("<fff", float(s["x"]), float(s["y"]), float(s["z"]))
        )

        def force_validate_true(uc: Any, address: int, size: int, user: Any) -> None:
            uc.reg_write(UC_X86_REG_RAX, 1)
            rsp = uc.reg_read(UC_X86_REG_RSP)
            ret = struct.unpack("<Q", bytes(uc.mem_read(rsp, 8)))[0]
            uc.reg_write(UC_X86_REG_RSP, rsp + 8)
            uc.reg_write(UC_X86_REG_RIP, ret)

        h = emu.mu.hook_add(
            UC_HOOK_CODE,
            force_validate_true,
            begin=VALIDATE_VEC3_VA,
            end=VALIDATE_VEC3_VA,
        )
        try:
            unicorn_call(emu, fn=PATH_SET_ABSOLUTE_VA, rcx=pc, rdx=vec)
            rax = unicorn_call(emu, fn=ABS_GETTER_VA, rcx=pc)
            gx, gy, gz = struct.unpack("<fff", bytes(emu.mu.mem_read(rax, 12)))
            p20 = struct.unpack(
                "<fff", bytes(emu.mu.mem_read(pc + POSITION_IN_PATH_CONTROLLER, 12))
            )
        except Exception as exc:  # noqa: BLE001
            out.append({**s, "getOk": False, "error": str(exc)})
            try:
                emu.mu.hook_del(h)
            except Exception:  # noqa: BLE001
                pass
            continue
        try:
            emu.mu.hook_del(h)
        except Exception:  # noqa: BLE001
            pass
        out.append(
            {
                **s,
                "getOk": True,
                "gx": float(gx),
                "gy": float(gy),
                "gz": float(gz),
                "slot20": list(p20),
                "roundTrip": abs(gx - s["x"]) < 1e-2 and abs(gz - s["z"]) < 1e-2,
                "applyMode": "path_set_absolute_to_a0",
            }
        )
    return out


def qa_samples(samples: Sequence[dict], oracle: Sequence[dict]) -> dict:
    rows = [s for s in samples if s.get("getOk")]
    if len(rows) < 4:
        return {"winnerFound": False, "reason": "too_few_samples", "n": len(rows)}
    mid = len(rows) // 2
    train, hold = rows[:mid], rows[mid:]

    def run(subset: Sequence[dict], swap: bool) -> dict:
        errs = []
        heroes = set()
        for s in subset:
            pos = nearest_oracle(oracle, float(s["t"]))
            if pos is None:
                continue
            x = float(s.get("gx", s["x"]))
            z = float(s.get("gz", s["z"]))
            if swap:
                x, z = z, x
            heroes.add(int(s["param"]))
            errs.append(min(math.hypot(x - ox, z - oz) for ox, oz in pos.values()))
        return score_errs(errs, len(heroes))

    tr, ho = run(train, False), run(hold, False)
    tr_s, ho_s = run(train, True), run(hold, True)
    use_swap = bool(
        tr_s.get("n", 0) >= 10
        and ho_s.get("n", 0) >= 10
        and (tr_s.get("median") or 1e18) < (tr.get("median") or 1e18)
        and (ho_s.get("median") or 1e18) < (ho.get("median") or 1e18)
    )
    train_sc = tr_s if use_swap else tr
    hold_sc = ho_s if use_swap else ho
    return {
        "winnerFound": bool(train_sc.get("ok") and hold_sc.get("ok")),
        "swap": use_swap,
        "train": train_sc,
        "holdout": hold_sc,
        "roundTripOk": sum(1 for s in rows if s.get("roundTrip")),
        "roundTripN": len(rows),
    }


def classify_blocker(
    *,
    scan: Mapping[str, Any],
    proof: Mapping[str, Any],
    evaluations: Sequence[dict],
) -> dict:
    abs20 = int(scan.get("absoluteWritersToPc20Count") or 0)
    if abs20 == 0 and proof.get("slot20HoldsDirection") and proof.get("a0HoldsAbsolute"):
        # Related absolute path QA
        winners = [e for e in evaluations if e.get("qa", {}).get("winnerFound")]
        best = None
        for e in evaluations:
            ho = (e.get("qa") or {}).get("holdout") or {}
            if ho.get("median") is None:
                continue
            if best is None or ho["median"] < best["median"]:
                best = {"opcode": e.get("opcode"), "source": e.get("source"), **ho}
        if winners:
            return {
                "kind": "none",
                "detail": "absolute PC+0xa0 path passed oracle (GetPosition+0x20 still direction)",
                "relatedWinner": winners[0],
            }
        return {
            "kind": "no_absolute_pc20_writers",
            "alias": "position_slot_not_absolute_store",
            "detail": (
                "GetPosition slot PC+0x20 is direction/facing (PathSetPositionCore); "
                "no absolute map-XYZ stores into that slot. Absolute world XYZ is "
                "written to PC+0xa0 by PathSetAbsolute@0x1403891a0 (getter "
                "lea rax,[rcx+0xa0] @0x140305350). Driving PathSetAbsolute with "
                "reconstructed packet XYZ round-trips +0xa0 but fails Replay API "
                "gates — same packet floats as E14, not live positions."
            ),
            "relatedAbsoluteSlot": scan.get("absoluteSlot"),
            "relatedQaBestNearMiss": best,
            "relatedBlockerIfAskingA0": "writers_values_not_oracle",
            "nextHint": (
                "Path integration / nav waypoint state may produce live positions; "
                "packet XYZ through PathSetAbsolute is not oracle-live"
            ),
        }
    if abs20 == 0:
        return {
            "kind": "no_absolute_pc20_writers",
            "alias": "position_slot_not_absolute_store",
            "detail": "no absolute map writers to PC+0x20 found",
        }
    return {
        "kind": "writers_need_full_heap",
        "detail": "candidate absolute PC+0x20 writers exist but were not emulatable",
        "candidates": scan.get("absoluteWritersToPc20"),
    }


def run_e15(
    *,
    pe_path: Path,
    rofl: Path,
    oracle_jsonl: Path,
    report_path: Path,
    dry_run: bool = False,
) -> dict:
    t0 = time.perf_counter()
    binary = load_binary(pe_path)
    prov = official_provenance(size=pe_path.stat().st_size, sha256=binary.sha256)
    man = research_manifest(
        binary, patch="16.14", extra={"probeVersion": PROBE_VERSION, "official": prov}
    )
    counts, _ = enumerate_rofl(rofl)
    rows, coverage = scan_msvc_packet_types(binary, counts)
    factories = {int(r["opcode"]): r for r in rows}

    scan = scan_pc20_writers(binary)
    proof = prove_absolute_vs_direction(binary)

    oracle = _load_oracle_positions(oracle_jsonl)
    blocks = collect_blocks(rofl, [OPCODE_DIRECT_INPUT, OPCODE_NEAR_MISS])

    evaluations = []
    # Related absolute path: packet → PathSetAbsolute → +0xa0 getter
    if OPCODE_DIRECT_INPUT in factories and blocks.get(OPCODE_DIRECT_INPUT):
        samp = diversify(blocks[OPCODE_DIRECT_INPUT], MAX_SAMPLES_58)
        di = capture_direct_input_xyz(binary, factories[OPCODE_DIRECT_INPUT], samp)
        got = apply_path_set_absolute(binary, di)
        evaluations.append(
            {
                "opcode": OPCODE_DIRECT_INPUT,
                "slot": "PC+0xa0 (absolute, not GetPosition)",
                "source": "Deserialize+END_READ → PathSetAbsolute → abs getter +0xa0",
                "captured": len(di),
                "applied": sum(1 for s in got if s.get("getOk")),
                "qa": qa_samples(got, oracle),
            }
        )
    if OPCODE_NEAR_MISS in factories and blocks.get(OPCODE_NEAR_MISS):
        samp = diversify(blocks[OPCODE_NEAR_MISS], MAX_SAMPLES_908)
        rows908 = capture_908_xyz(binary, factories[OPCODE_NEAR_MISS], samp)
        got = apply_path_set_absolute(binary, rows908)
        evaluations.append(
            {
                "opcode": OPCODE_NEAR_MISS,
                "slot": "PC+0xa0 (absolute, not GetPosition)",
                "source": "Deserialize +16/+20 → PathSetAbsolute → abs getter +0xa0",
                "captured": len(rows908),
                "applied": sum(1 for s in got if s.get("getOk")),
                "qa": qa_samples(got, oracle),
            }
        )

    winner = None
    for e in evaluations:
        if e.get("qa", {}).get("winnerFound"):
            winner = {
                "note": "winner is on absolute PC+0xa0 path, not GetPosition+0x20",
                "opcode": e["opcode"],
                "slot": e["slot"],
                "writerVa": hex(PATH_SET_ABSOLUTE_VA),
                "getterVa": hex(ABS_GETTER_VA),
                "qa": e["qa"],
            }
            break

    blocker = classify_blocker(scan=scan, proof=proof, evaluations=evaluations)
    wall_ms = (time.perf_counter() - t0) * 1000.0

    # Primary E15 question is PC+0x20 absolute writers — winner on +0xa0 does not
    # satisfy GetPosition-slot hypothesis, but is reported.
    ok_pc20 = False
    report = {
        "ok": ok_pc20,
        "probeVersion": PROBE_VERSION,
        "hypothesis": "phase-b-e15-position-writers",
        "matchCode": MATCH_CODE,
        "wallMs": round(wall_ms, 3),
        "wallTargetMs": 60_000,
        "wallPass": wall_ms <= 60_000,
        "official": prov,
        "binaryManifest": man,
        "constructorCoverage": coverage,
        "scan": scan,
        "absoluteVsDirectionProof": proof,
        "evaluations": evaluations,
        "evaluation": {
            "winnerFound": bool(winner),
            "winner": winner,
            "winnerSlotNote": (
                "Any winner here is PC+0xa0 absolute path; GetPosition+0x20 remains "
                "direction-only with no absolute writers"
            ),
            "gates": {
                "minSamples": ACCEPT_MIN_SAMPLES,
                "minHeroes": ACCEPT_MIN_HEROES,
                "maxMedian": ACCEPT_MAX_MEDIAN,
                "maxP95": ACCEPT_MAX_P95,
                "maxMax": ACCEPT_MAX_MAX,
                "oracleTolS": ORACLE_TOL_S,
            },
            "cadenceHonesty": (
                "No 1Hz claim. Absolute PathSetAbsolute is whatever cadence packet "
                "sources provide (DI sparse; 908 higher)."
            ),
        },
        "blocker": blocker,
        "minimalStubIfContinuingA0": {
            "pathController": "alloc ≥0xc0; clear +0x50/+0xb9 flags",
            "writer": hex(PATH_SET_ABSOLUTE_VA),
            "validateHook": hex(VALIDATE_VEC3_VA) + " → return true",
            "absGetter": hex(ABS_GETTER_VA),
            "note": "still needs oracle-true XYZ source; packet fields fail gates",
        },
        "pureDecoderDerived": False,
        "browserSafe": False,
        "productEligible": False,
        "identity": {
            "createHeroBindingDecoded": False,
            "productEligible": False,
        },
    }

    keep = "discard"
    reason = (
        f"E15 blocker={blocker['kind']}: {str(blocker.get('detail') or '')[:200]}"
    )
    if not dry_run:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        append_speed_record(
            log=SPEED_LOG,
            hypothesis="phase-b-e15-position-writers",
            diff_label="e15-pc20-absolute-writers",
            keep=keep,
            reason=reason,
            wall_ms=wall_ms,
            match_code=MATCH_CODE,
            extra={
                "decoderVersion": PROBE_VERSION,
                "winnerFound": bool(winner),
                "blocker": blocker,
                "absoluteWritersToPc20": scan.get("absoluteWritersToPc20Count"),
                "browserSafe": False,
                "productEligible": False,
                "pureDecoderDerived": False,
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
    report = run_e15(
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
                "blocker": report.get("blocker"),
                "absoluteWritersToPc20": (report.get("scan") or {}).get(
                    "absoluteWritersToPc20Count"
                ),
                "pathControllerRegionWriters": (report.get("scan") or {}).get(
                    "pathControllerRegionWriters"
                ),
                "absoluteSlot": (report.get("scan") or {}).get("absoluteSlot"),
                "proof": {
                    k: (report.get("absoluteVsDirectionProof") or {}).get(k)
                    for k in (
                        "a0HoldsAbsolute",
                        "slot20HoldsDirection",
                        "slotA0",
                        "slot20",
                    )
                },
                "relatedWinner": (report.get("evaluation") or {}).get("winner"),
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
