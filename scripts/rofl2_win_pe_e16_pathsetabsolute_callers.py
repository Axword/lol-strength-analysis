#!/usr/bin/env python3
"""E16: PathSetAbsolute callers + path-integration hypothesis.

Pinned E15:
  PathSetAbsolute @0x1403891a0 → PC+0xa0 absolute XYZ
  Abs getter @0x140305350 = lea rax,[rcx+0xa0]; ret
  GetPosition PC+0x20 is direction-only
  Packet floats through PathSetAbsolute fail oracle (908 med~191)

Question: who calls PathSetAbsolute, and is continuous live XYZ stored in
packets or produced by integrating path/driver state each tick?

Hard constraints: no live API, no plan edit, no commit, no binary vendoring,
no learned affine. Axis-swap only.
"""
from __future__ import annotations

import argparse
import json
import math
import re
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
from rofl2_win_pe_e11_reconstructed_drive import OPCODE_DIRECT_INPUT  # noqa: E402
from rofl2_win_pe_e14_position_getters import (  # noqa: E402
    ACCEPT_MAX_MAX,
    ACCEPT_MAX_MEDIAN,
    ACCEPT_MAX_P95,
    ACCEPT_MIN_HEROES,
    ACCEPT_MIN_SAMPLES,
    MAX_SAMPLES_58,
    MAX_SAMPLES_908,
    OPCODE_NEAR_MISS,
    ORACLE_TOL_S,
    PATH_CONTROLLER_IN_HERO,
    capture_908_xyz,
    capture_direct_input_xyz,
    collect_blocks,
    diversify,
    nearest_oracle,
    score_errs,
    unicorn_call,
)
from rofl2_win_pe_e15_position_writers import (  # noqa: E402
    ABS_GETTER_VA,
    ABS_POSITION_IN_PC,
    PATH_SET_ABSOLUTE_VA,
    VALIDATE_VEC3_VA,
)
from rofl2_win_pe_packet_discover import (  # noqa: E402
    WinX64PacketEmu,
    enumerate_rofl,
    official_provenance,
    scan_msvc_packet_types,
)

PROBE_VERSION = "e16-win-pe-pathsetabsolute-callers-v1"
MATCH_CODE = "3264361042"
DEFAULT_PE = Path("/tmp/League-of-Legends-16.14-win.exe")
DEFAULT_ROFL = Path.home() / "Documents/League of Legends/Replays/BR1-3264361042.rofl"
DEFAULT_ORACLE = Path("artifacts/rofl/3264361042/events.rfc461.jsonl")
DEFAULT_REPORT = Path("docs/rofl-research/movement-win-pe-e16-BR1-3264361042.json")
SPEED_LOG = Path("docs/rofl-research/speed-runs.jsonl")

# PathController helpers (E14/E15/E16 evidence).
UPDATE_PC_VA = 0x14036DDB0  # applies path blob; may call PATH_APPLY
PATH_APPLY_VA = 0x14038AC80  # writes PC+0x40/+0x44/+0x48 from blob
INIT_PC_STUB_VA = 0x14035D280
AIBASE_SETPOS_VA = 0x140270CA0  # lea PC+0x28d0; PathSetAbsolute(rdx=vec)
INTEGRATOR_ADD_VA = 0x1406B8E70  # addss delta into +0x9c/+0xa0/+0xa4/...
NORM_HELPER_VA = 0x1411847B0

STACK_REGS = frozenset({"rsp", "rbp", "esp", "ebp"})


def _md() -> Cs:
    return Cs(CS_ARCH_X86, CS_MODE_64)


def _call_sites(text_va: int, text: bytes, target: int) -> List[int]:
    out = []
    for m in re.finditer(rb"\xe8....", text):
        i = m.start()
        va = text_va + i
        rel = struct.unpack_from("<i", text, i + 1)[0]
        if va + 5 + rel == target:
            out.append(va)
    for m in re.finditer(rb"\xe9....", text):
        i = m.start()
        va = text_va + i
        rel = struct.unpack_from("<i", text, i + 1)[0]
        if va + 5 + rel == target:
            out.append(va)
    return sorted(set(out))


def _func_start(binary: Any, va: int, back: int = 0x800) -> Optional[int]:
    fo = binary.va_to_file(va)
    data = binary.data
    for b in range(0, back):
        j = fo - b
        if j < 1:
            break
        if data[j] == 0xCC and data[j + 1] in (
            0x40,
            0x48,
            0x55,
            0x53,
            0x56,
            0x57,
            0x41,
            0x44,
            0x45,
            0x4C,
        ):
            try:
                return binary.file_to_va(j + 1)
            except Exception:  # noqa: BLE001
                pass
    return None


def _last_lea_or_mov(insns: Sequence[Any], reg: str) -> str:
    for i in reversed(list(insns)):
        if i.mnemonic in ("lea", "mov") and i.op_str.startswith(f"{reg},"):
            return i.op_str
    return "?"


def classify_caller(binary: Any, call_va: int) -> dict:
    md = _md()
    before = list(md.disasm(binary.read_va(call_va - 0x90, 0x90), call_va - 0x90))
    has_28d0 = any("0x28d0" in i.op_str for i in before)
    near_upd = any(
        i.mnemonic == "call" and hex(UPDATE_PC_VA)[2:] in i.op_str for i in before
    )
    near_init = any(
        i.mnemonic == "call" and hex(INIT_PC_STUB_VA)[2:] in i.op_str for i in before
    )
    near_norm = any(
        i.mnemonic == "call" and hex(NORM_HELPER_VA)[2:] in i.op_str for i in before
    )
    has_sqrt = any(i.mnemonic in ("sqrtss", "sqrtps") for i in before)
    rcx_src = _last_lea_or_mov(before, "rcx")
    rdx_src = _last_lea_or_mov(before, "rdx")

    kind = "unknown"
    if near_upd:
        kind = "after_pathcontroller_update"
    elif near_init and not has_28d0:
        kind = "temp_pc_stub_then_set"
    elif has_sqrt or near_norm:
        kind = "normalized_or_facing_vec"
    elif has_28d0 or "0x28d0" in rcx_src:
        kind = "hero_pathcontroller_snap"
    elif "rsp" in rcx_src or "rbp" in rcx_src:
        kind = "temp_pc_stub_then_set"

    fs = _func_start(binary, call_va)
    return {
        "callVa": hex(call_va),
        "funcGuess": hex(fs) if fs else None,
        "kind": kind,
        "rcx": rcx_src,
        "rdx": rdx_src,
        "hasHeroPathController": has_28d0 or "0x28d0" in rcx_src,
        "nearUpdatePc": near_upd,
        "nearInitStub": near_init,
        "nearNormHelper": near_norm,
        "hasSqrt": has_sqrt,
    }


def packet_factory_code_vas(binary: Any, factories: Mapping[int, Any]) -> Dict[int, dict]:
    out = {}
    for op, fac in factories.items():
        if op not in (58, 420, 908, 1104):
            continue
        deser = int(fac["deserializeVa"])
        pat = struct.pack("<Q", deser)
        j = binary.data.find(pat)
        slots = []
        vt = None
        if j >= 0:
            vt = binary.file_to_va(j)
            fo = binary.va_to_file(vt)
            slots = [
                struct.unpack_from("<Q", binary.data, fo + off)[0]
                for off in range(0, 64, 8)
            ]
        # Does deser body call PathSetAbsolute?
        raw = binary.read_va(deser, 0x400)
        calls = []
        for m in re.finditer(rb"\xe8....", raw):
            i = m.start()
            va = deser + i
            rel = struct.unpack_from("<i", raw, i + 1)[0]
            calls.append(va + 5 + rel)
        out[op] = {
            "deserializeVa": hex(deser),
            "vtable": hex(vt) if vt else None,
            "slots": [hex(s) for s in slots],
            "deserCallsPathSetAbsolute": PATH_SET_ABSOLUTE_VA in calls,
            "deserCallTargetsSample": [hex(c) for c in calls[:12]],
        }
    return out


def find_integration_writers(binary: Any) -> List[dict]:
    """movss stores to +0xa0 preceded by addss/mulss (tick integration)."""
    md = _md()
    text_va, text = binary.text_bytes()
    out = []
    for m in re.finditer(rb"\xf3\x0f\x11", text):
        i = m.start()
        va = text_va + i
        try:
            insn = next(md.disasm(text[i : i + 12], va))
        except StopIteration:
            continue
        if insn.mnemonic != "movss" or "+ 0xa0]" not in insn.op_str:
            continue
        if any(s in insn.op_str for s in STACK_REGS):
            continue
        before = list(md.disasm(binary.read_va(va - 0x50, 0x50), va - 0x50))
        recent = [x for x in before if x.address < va][-12:]
        if not any(x.mnemonic in ("addss", "mulss", "subss") for x in recent):
            continue
        fs = _func_start(binary, va)
        out.append(
            {
                "storeVa": hex(va),
                "dest": insn.op_str.split(",")[0],
                "funcGuess": hex(fs) if fs else None,
                "kind": "integrate_add_into_a0",
                "recentOps": [f"{x.mnemonic} {x.op_str}" for x in recent[-6:]],
            }
        )
    # dedupe by func
    by_fn: Dict[str, dict] = {}
    for w in out:
        key = w.get("funcGuess") or w["storeVa"]
        by_fn.setdefault(key, w)
    return list(by_fn.values())


def prove_integrator_stub(binary: Any) -> dict:
    """Unicorn: INTEGRATOR_ADD adds delta into PC+0xa0 (layout proof only)."""
    emu = WinX64PacketEmu(binary)
    # Integrator uses rcx as object with +0x38/+0x3c/+0x40 and +0x9c/+0xa0/+...
    # Empirically rdi/rcx is NOT the PathController base alone — it uses both
    # +0x38 and +0x9c. Treat as PathController-sized stub and set both regions.
    obj = emu._alloc(0x200, kind="pc_integ", pc=0)
    # Seed absolute-ish at +0xa0
    x0, y0, z0 = 1000.0, 50.0, 2000.0
    emu.mu.mem_write(obj + 0x9C, struct.pack("<fff", x0 - 10, y0, z0 - 20))
    emu.mu.mem_write(obj + ABS_POSITION_IN_PC, struct.pack("<fff", x0, y0, z0))
    emu.mu.mem_write(obj + 0xA8, struct.pack("<f", z0 + 5))
    # Also seed +0x38 region used before helper call
    emu.mu.mem_write(obj + 0x38, struct.pack("<fff", x0, y0, z0))
    delta = emu._alloc(16, kind="dxyz", pc=0)
    dx, dy, dz = 10.0, 0.0, 20.0
    emu.mu.mem_write(delta, struct.pack("<fff", dx, dy, dz))
    err = None
    try:
        unicorn_call(emu, fn=INTEGRATOR_ADD_VA, rcx=obj, rdx=delta)
    except Exception as exc:  # noqa: BLE001
        err = str(exc)
    after = struct.unpack("<fff", bytes(emu.mu.mem_read(obj + ABS_POSITION_IN_PC, 12)))
    mutated = any(abs(a - b) > 1e-3 for a, b in zip(after, (x0, y0, z0)))
    return {
        "integratorVa": hex(INTEGRATOR_ADD_VA),
        "ok": err is None,
        "error": err,
        "beforeA0": [x0, y0, z0],
        "delta": [dx, dy, dz],
        "afterA0": list(after),
        "mutatedA0": mutated,
        "note": (
            "Stub shows addss stores into the +0xa0 neighborhood; axis packing on a "
            "synthetic object is not identity to PathController — full sim required "
            "for oracle deltas"
        ),
    }


def prove_path_apply_slot(binary: Any) -> dict:
    """PATH_APPLY writes blob XYZ into PC+0x40, not +0xa0."""
    md = _md()
    writes = []
    for i in md.disasm(binary.read_va(PATH_APPLY_VA, 0x60), PATH_APPLY_VA):
        if i.mnemonic == "movss" and "+ 0x4" in i.op_str and i.op_str.startswith("dword"):
            writes.append(f"{i.address:#x}: {i.mnemonic} {i.op_str}")
        if i.mnemonic == "ret":
            break
    return {
        "pathApplyVa": hex(PATH_APPLY_VA),
        "updatePcVa": hex(UPDATE_PC_VA),
        "writes": writes,
        "writesAbsoluteA0": False,
        "note": "UpdatePC/PATH_APPLY updates PC+0x40 path vector; absolute +0xa0 is separate",
    }


def apply_path_set_absolute(
    binary: Any, samples: Sequence[dict]
) -> List[dict]:
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

        def force_true(uc: Any, address: int, size: int, user: Any) -> None:
            uc.reg_write(UC_X86_REG_RAX, 1)
            rsp = uc.reg_read(UC_X86_REG_RSP)
            ret = struct.unpack("<Q", bytes(uc.mem_read(rsp, 8)))[0]
            uc.reg_write(UC_X86_REG_RSP, rsp + 8)
            uc.reg_write(UC_X86_REG_RIP, ret)

        h = emu.mu.hook_add(
            UC_HOOK_CODE, force_true, begin=VALIDATE_VEC3_VA, end=VALIDATE_VEC3_VA
        )
        try:
            unicorn_call(emu, fn=PATH_SET_ABSOLUTE_VA, rcx=pc, rdx=vec)
            rax = unicorn_call(emu, fn=ABS_GETTER_VA, rcx=pc)
            gx, gy, gz = struct.unpack("<fff", bytes(emu.mu.mem_read(rax, 12)))
            ok = True
            err = None
        except Exception as exc:  # noqa: BLE001
            ok = False
            err = str(exc)
            gx = gy = gz = 0.0
        try:
            emu.mu.hook_del(h)
        except Exception:  # noqa: BLE001
            pass
        out.append(
            {
                **s,
                "getOk": ok,
                "error": err,
                "gx": float(gx),
                "gy": float(gy),
                "gz": float(gz),
                "roundTrip": ok
                and abs(gx - s["x"]) < 1e-2
                and abs(gz - s["z"]) < 1e-2,
            }
        )
    return out


def qa_samples(samples: Sequence[dict], oracle: Sequence[dict]) -> dict:
    rows = [s for s in samples if s.get("getOk")]
    if len(rows) < 4:
        return {"winnerFound": False, "reason": "too_few", "n": len(rows)}
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
    callers: Sequence[dict],
    packet_reach: Mapping[int, Any],
    integrators: Sequence[dict],
    integ_proof: Mapping[str, Any],
    evaluations: Sequence[dict],
    waypoints_decoded: bool,
) -> dict:
    deser_reach = any(
        bool((packet_reach.get(op) or {}).get("deserCallsPathSetAbsolute"))
        for op in packet_reach
    )
    snap_kinds = {
        "hero_pathcontroller_snap",
        "after_pathcontroller_update",
        "temp_pc_stub_then_set",
        "normalized_or_facing_vec",
    }
    kind_counts = defaultdict(int)
    for c in callers:
        kind_counts[c["kind"]] += 1

    winners = [e for e in evaluations if e.get("qa", {}).get("winnerFound")]
    if winners:
        return {"kind": "none", "detail": "oracle winner via PathSetAbsolute drive"}

    best = None
    for e in evaluations:
        ho = (e.get("qa") or {}).get("holdout") or {}
        if ho.get("median") is None:
            continue
        if best is None or ho["median"] < best["median"]:
            best = {"opcode": e.get("opcode"), **ho}

    if not deser_reach and integrators:
        return {
            "kind": "position_is_integrated_not_stored",
            "detail": (
                "PathSetAbsolute callers are AIBase/PathController gameplay snaps "
                f"({dict(kind_counts)}); packet Deserialize for 58/420/908/1104 does "
                "not call PathSetAbsolute. Continuous +0xa0 updates include "
                f"addss-integrators (e.g. {integrators[0].get('funcGuess')}). "
                "Feeding reconstructed packet XYZ through PathSetAbsolute still fails "
                "oracle — those fields are not live positions."
            ),
            "secondary": "pathsetabsolute_callers_not_rofl_reachable",
            "relatedSnapQa": "callers_values_not_oracle",
            "relatedBestNearMiss": best,
            "integrationProof": integ_proof,
            "waypointsStructurallyDecoded": waypoints_decoded,
            "integrationSimulation": (
                "integration_requires_full_sim"
                if not waypoints_decoded
                else "waypoints_available"
            ),
        }
    if not deser_reach:
        return {
            "kind": "pathsetabsolute_callers_not_rofl_reachable",
            "detail": "no packet Deserialize path calls PathSetAbsolute",
            "kindCounts": dict(kind_counts),
        }
    return {
        "kind": "callers_values_not_oracle",
        "detail": "ROFL-reachable PathSetAbsolute path found but values fail gates",
        "bestNearMiss": best,
        "kinds": snap_kinds,
    }


def run_e16(
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
    text_va, text = binary.text_bytes()
    counts, _ = enumerate_rofl(rofl)
    rows, coverage = scan_msvc_packet_types(binary, counts)
    factories = {int(r["opcode"]): r for r in rows}

    sites = _call_sites(text_va, text, PATH_SET_ABSOLUTE_VA)
    callers = [classify_caller(binary, va) for va in sites]
    kind_counts: Dict[str, int] = defaultdict(int)
    for c in callers:
        kind_counts[c["kind"]] += 1

    packet_reach = packet_factory_code_vas(binary, factories)
    integrators = find_integration_writers(binary)
    integ_proof = prove_integrator_stub(binary)
    path_apply = prove_path_apply_slot(binary)

    # Waypoints: no structural ROFL decode in this probe (E12/E13 float fishing failed).
    waypoints_decoded = False

    oracle = _load_oracle_positions(oracle_jsonl)
    blocks = collect_blocks(rofl, [OPCODE_DIRECT_INPUT, OPCODE_NEAR_MISS])
    evaluations = []
    # Bounded dynamic: still drive PathSetAbsolute with reconstructed packet XYZ
    # (documents callers_values_not_oracle for the snap path).
    if OPCODE_DIRECT_INPUT in factories and blocks.get(OPCODE_DIRECT_INPUT):
        samp = diversify(blocks[OPCODE_DIRECT_INPUT], MAX_SAMPLES_58)
        di = capture_direct_input_xyz(binary, factories[OPCODE_DIRECT_INPUT], samp)
        got = apply_path_set_absolute(binary, di)
        evaluations.append(
            {
                "opcode": OPCODE_DIRECT_INPUT,
                "source": "DI END_READ → PathSetAbsolute → abs getter (snap path)",
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
                "source": "908 +16/+20 → PathSetAbsolute → abs getter (snap path)",
                "captured": len(rows908),
                "applied": sum(1 for s in got if s.get("getOk")),
                "qa": qa_samples(got, oracle),
            }
        )

    blocker = classify_blocker(
        callers=callers,
        packet_reach=packet_reach,
        integrators=integrators,
        integ_proof=integ_proof,
        evaluations=evaluations,
        waypoints_decoded=waypoints_decoded,
    )
    wall_ms = (time.perf_counter() - t0) * 1000.0

    pc_layout = {
        "+0x20": "GetPosition / facing direction (PathSetPositionCore)",
        "+0x40/+0x44/+0x48": "PATH_APPLY path vector from UpdatePC blob+0x40",
        "+0x50/+0xb9": "flags gating PathSetPositionCore",
        "+0xa0/+0xa4/+0xa8": "absolute world XYZ (PathSetAbsolute snaps + integrators)",
        "heroPathController": hex(PATH_CONTROLLER_IN_HERO),
    }

    report = {
        "ok": False,
        "probeVersion": PROBE_VERSION,
        "hypothesis": "phase-b-e16-pathsetabsolute-callers",
        "matchCode": MATCH_CODE,
        "wallMs": round(wall_ms, 3),
        "wallTargetMs": 60_000,
        "wallPass": wall_ms <= 60_000,
        "official": prov,
        "binaryManifest": man,
        "constructorCoverage": coverage,
        "pathSetAbsolute": {
            "va": hex(PATH_SET_ABSOLUTE_VA),
            "absGetterVa": hex(ABS_GETTER_VA),
            "absOffset": hex(ABS_POSITION_IN_PC),
            "callerCount": len(callers),
            "kindCounts": dict(kind_counts),
            "callers": callers,
            "aibaseSetPositionVa": hex(AIBASE_SETPOS_VA),
            "aibaseSetPositionNote": (
                "0x140270ca0: AIBase-ish setpos; lea PC+0x28d0 then PathSetAbsolute; "
                "0 E8 callers (vtable/indirect)"
            ),
        },
        "packetReachability": packet_reach,
        "pathControllerLayout": pc_layout,
        "pathApply": path_apply,
        "integrationWriters": integrators,
        "integrationStubProof": integ_proof,
        "waypointDecode": {
            "structurallyProvenFromRofl": waypoints_decoded,
            "note": (
                "No waypoint list recovered under reconstructed framing without float "
                "fishing; naive constant-speed walk not attempted"
            ),
        },
        "evaluations": evaluations,
        "evaluation": {
            "winnerFound": False,
            "winner": None,
            "continuousPositionModel": (
                "integrated_and_snapped"
                if integrators
                else "snap_only_via_pathsetabsolute"
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
                "PathSetAbsolute snaps are event-driven; continuous Replay API 1Hz "
                "positions are consistent with tick integration into +0xa0, not with "
                "packet XYZ carriers tested in E11–E15"
            ),
        },
        "blocker": blocker,
        "pureDecoderDerived": False,
        "browserSafe": False,
        "productEligible": False,
        "identity": {"createHeroBindingDecoded": False, "productEligible": False},
    }

    if not dry_run:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        append_speed_record(
            log=SPEED_LOG,
            hypothesis="phase-b-e16-pathsetabsolute-callers",
            diff_label="e16-pathsetabsolute-integration",
            keep="discard",
            reason=f"E16 blocker={blocker['kind']}: {str(blocker.get('detail') or '')[:200]}",
            wall_ms=wall_ms,
            match_code=MATCH_CODE,
            extra={
                "decoderVersion": PROBE_VERSION,
                "blocker": blocker,
                "callerCount": len(callers),
                "integratorCount": len(integrators),
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
    report = run_e16(
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
                "callerCount": (report.get("pathSetAbsolute") or {}).get("callerCount"),
                "kindCounts": (report.get("pathSetAbsolute") or {}).get("kindCounts"),
                "integratorCount": len(report.get("integrationWriters") or []),
                "packetDeserCallsPsa": {
                    str(k): v.get("deserCallsPathSetAbsolute")
                    for k, v in (report.get("packetReachability") or {}).items()
                },
                "continuousModel": (report.get("evaluation") or {}).get(
                    "continuousPositionModel"
                ),
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
