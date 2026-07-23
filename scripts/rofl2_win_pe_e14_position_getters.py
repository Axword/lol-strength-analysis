#!/usr/bin/env python3
"""E14: HP-analogue position path via PathController / GetPosition slots.

Hypothesis: plaintext live X/Z appear in PathController object slots read by
GetPosition after locomotion apply — not by scanning packet-object floats.

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
from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_WRITE  # noqa: E402
from unicorn.x86_const import UC_X86_REG_RAX, UC_X86_REG_RIP  # noqa: E402

from rofl2_binary_format import load_binary, research_manifest  # noqa: E402
from rofl2_movement_decode import (  # noqa: E402
    _load_oracle_positions,
    append_speed_record,
)
from rofl2_movement_wire_scan import PROVEN_HERO_NET_ID_SET  # noqa: E402
from rofl2_probe import extract_segments, parse_rofl2  # noqa: E402
from rofl2_unicorn_packet_drive import extract_blocks_py  # noqa: E402
from rofl2_win_pe_e11_reconstructed_drive import (  # noqa: E402
    DIRECT_INPUT_END_READ_VA,
    MARKER_1,
    OPCODE_DIRECT_INPUT,
    OPCODE_SET_MOVEMENT_DRIVER,
    deserialize_body,
    encode_type,
)
from rofl2_win_pe_packet_discover import (  # noqa: E402
    STACK_BASE,
    WinX64PacketEmu,
    enumerate_rofl,
    official_provenance,
    scan_msvc_packet_types,
)

PROBE_VERSION = "e14-win-pe-position-getters-v1"
MATCH_CODE = "3264361042"
DEFAULT_PE = Path("/tmp/League-of-Legends-16.14-win.exe")
DEFAULT_ROFL = Path.home() / "Documents/League of Legends/Replays/BR1-3264361042.rofl"
DEFAULT_ORACLE = Path("artifacts/rofl/3264361042/events.rfc461.jsonl")
DEFAULT_REPORT = Path("docs/rofl-research/movement-win-pe-e14-BR1-3264361042.json")
SPEED_LOG = Path("docs/rofl-research/speed-runs.jsonl")

OPCODE_NEAR_MISS = 908

# Evidence-derived (E14 static analysis on official 16.14 PE).
GET_POSITION_VA = 0x1403030C0  # lea rax, [rcx+0x20]; ret
PATH_CONTROLLER_IN_HERO = 0x28D0
POSITION_IN_PATH_CONTROLLER = 0x20
HERO_POSITION_ABS = PATH_CONTROLLER_IN_HERO + POSITION_IN_PATH_CONTROLLER  # 0x28F0
# Writes XYZ into PathController+0x20/+0x24/+0x28 (called from 0x1403891a0).
PATH_SET_POSITION_CORE_VA = 0x140389200

ACCEPT_MIN_SAMPLES = 80
ACCEPT_MIN_HEROES = 5
ACCEPT_MAX_MEDIAN = 120.0
ACCEPT_MAX_P95 = 350.0
ACCEPT_MAX_MAX = 800.0
ORACLE_TOL_S = 0.5
SR_MIN = -200.0
SR_MAX = 16000.0

MAX_SAMPLES_58 = 120
MAX_SAMPLES_908 = 100


def _f32_map(v: float) -> bool:
    return v == v and SR_MIN <= v <= SR_MAX and abs(v) > 50.0


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


def discover_position_path(binary: Any) -> dict:
    """Static evidence for GetPosition / PathController slot geometry."""
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    data = binary.data
    text_va, text = binary.text_bytes()

    def str_va(name: bytes) -> Optional[int]:
        j = data.find(name + b"\x00")
        if j < 0:
            return None
        try:
            return binary.file_to_va(j)
        except Exception:  # noqa: BLE001
            return None

    def lea_xrefs(target: int) -> List[int]:
        out = []
        for m in re.finditer(
            rb"[\x48\x4c]\x8d[\x05\x0d\x15\x1d\x25\x2d\x35\x3d]....", text, re.DOTALL
        ):
            i = m.start()
            va = text_va + i
            insn = next(md.disasm(text[i : i + 15], va))
            if "rip" not in insn.op_str:
                continue
            disp = struct.unpack_from("<i", text, i + 3)[0]
            if insn.address + insn.size + disp == target:
                out.append(va)
        return out

    get_str = str_va(b"GetPosition")
    mpos_str = str_va(b"mPosition")
    code = binary.read_va(GET_POSITION_VA, 5)
    getters = []
    # Confirm unique lea rax,[rcx+0x20];ret
    pat = b"\x48\x8d\x41\x20\xc3"
    start = 0
    while True:
        j = text.find(pat, start)
        if j < 0:
            break
        getters.append(text_va + j)
        start = j + 1

    # Count lea reg,[reg+0x28d0]
    lea_pc = len(re.findall(rb"\x48\x8d[\x80-\xbf]\xd0\x28\x00\x00", text))

    # Callers of GetPosition
    callers = []
    for m in re.finditer(rb"\xe8....", text):
        i = m.start()
        va = text_va + i
        rel = struct.unpack_from("<i", text, i + 1)[0]
        if va + 5 + rel == GET_POSITION_VA:
            callers.append(va)

    # Sample: caller uses add/lea ...+0x28d0 before call
    pc_before_get = 0
    for c in callers[:40]:
        for insn in md.disasm(binary.read_va(c - 0x20, 0x28), c - 0x20):
            if insn.address >= c:
                break
            if "0x28d0" in insn.op_str:
                pc_before_get += 1
                break

    # Setter writes to +0x20
    setter_writes = False
    for insn in md.disasm(binary.read_va(PATH_SET_POSITION_CORE_VA, 0x140), PATH_SET_POSITION_CORE_VA):
        if insn.mnemonic == "movss" and "+ 0x20]" in insn.op_str and insn.op_str.startswith("dword ptr"):
            setter_writes = True
            break

    return {
        "getPositionStringVa": hex(get_str) if get_str else None,
        "getPositionStringXrefs": [hex(x) for x in (lea_xrefs(get_str) if get_str else [])],
        "mPositionStringVa": hex(mpos_str) if mpos_str else None,
        "mPositionStringXrefs": len(lea_xrefs(mpos_str) if mpos_str else []),
        "mPositionNote": (
            "mPosition string exists but has zero RIP LEA xrefs — not a CI registrar "
            "field like mHP/mMoveSpeed; position is PathController-embedded Vector3"
        ),
        "getPositionVa": hex(GET_POSITION_VA),
        "getPositionBytesHex": code.hex(),
        "getPositionDisasm": "lea rax, [rcx + 0x20] ; ret",
        "leaRaxRcx20RetCount": len(getters),
        "pathControllerInHero": hex(PATH_CONTROLLER_IN_HERO),
        "positionInPathController": hex(POSITION_IN_PATH_CONTROLLER),
        "heroAbsolutePosition": hex(HERO_POSITION_ABS),
        "leaRegRegPlus28d0Count": lea_pc,
        "getPositionCallers": len(callers),
        "callersWith28d0BeforeGetSample40": pc_before_get,
        "pathSetPositionCoreVa": hex(PATH_SET_POSITION_CORE_VA),
        "pathSetPositionWritesSlot20": setter_writes,
        "ciAnalogy": {
            "mHP": "CharacterIntermediate registrar slots (arm64 0x8d8/0x900; Win binder near mHP)",
            "position": "not CI string field; PathController subobject at hero+0x28d0, XYZ at +0x20",
        },
    }


def unicorn_call(
    emu: WinX64PacketEmu, *, fn: int, rcx: int, rdx: int = 0, r8: int = 0
) -> int:
    stop = STACK_BASE + 0x880
    emu.mu.mem_write(stop, b"\xc3")
    rsp = STACK_BASE + 0x100000 - 0x200
    emu._wu64(rsp - 0x20, stop)
    emu._set("rsp", rsp - 0x20)
    emu._set("rcx", rcx)
    emu._set("rdx", rdx)
    emu._set("r8", r8)
    emu._set("r9", 0)
    emu._set("rax", 0)
    emu.mu.emu_start(fn, stop, timeout=2_000_000, count=200_000)
    return int(emu.mu.reg_read(UC_X86_REG_RAX))


def prove_getter_geometry(binary: Any) -> dict:
    emu = WinX64PacketEmu(binary)
    hero = emu._alloc(0x4000, kind="hero", pc=0)
    x, y, z = 1111.0, 22.0, 3333.0
    emu.mu.mem_write(hero + HERO_POSITION_ABS, struct.pack("<fff", x, y, z))
    rax = unicorn_call(emu, fn=GET_POSITION_VA, rcx=hero + PATH_CONTROLLER_IN_HERO)
    got = struct.unpack("<fff", bytes(emu.mu.mem_read(rax, 12)))
    return {
        "ok": abs(got[0] - x) < 1e-3 and abs(got[2] - z) < 1e-3 and rax == hero + HERO_POSITION_ABS,
        "rax": hex(rax),
        "expected": hex(hero + HERO_POSITION_ABS),
        "xyz": list(got),
    }


def inspect_packet_use_vtable(binary: Any, factories: Mapping[int, Any]) -> dict:
    """Show MSVC virt 'use' slots are size/clone — not world apply."""
    out = {}
    for op in (OPCODE_DIRECT_INPUT, OPCODE_NEAR_MISS, OPCODE_SET_MOVEMENT_DRIVER):
        fac = factories.get(op)
        if not fac:
            continue
        deser = int(fac["deserializeVa"])
        pat = struct.pack("<Q", deser)
        j = binary.data.find(pat)
        if j < 0:
            out[str(op)] = {"error": "vtable_not_found"}
            continue
        vt = binary.file_to_va(j)
        fo = binary.va_to_file(vt)
        slots = {
            f"+{off}": hex(struct.unpack_from("<Q", binary.data, fo + off)[0])
            for off in range(0, 48, 8)
        }
        # Disasm +8 (often size getter)
        use = struct.unpack_from("<Q", binary.data, fo + 8)[0]
        md = Cs(CS_ARCH_X86, CS_MODE_64)
        head = []
        for insn in md.disasm(binary.read_va(use, 0x20), use):
            head.append(f"{insn.mnemonic} {insn.op_str}")
            if len(head) >= 3:
                break
        out[str(op)] = {
            "vtableEntry": hex(vt),
            "slots": slots,
            "virtPlus8Head": head,
            "note": "virt+8 is typically mov eax, objectSize; ret — not PathController apply",
        }
    return out


def collect_blocks(rofl: Path, opcodes: Sequence[int]) -> Dict[int, List[dict]]:
    want = {int(o) for o in opcodes}
    out: Dict[int, List[dict]] = defaultdict(list)
    for seg in extract_segments(parse_rofl2(rofl)["payload"])["segments"]:
        if int(seg.get("type") or 0) != 1:
            continue
        for b in extract_blocks_py(seg["bytes"], max_blocks=500_000):
            op = int(b["channel"])
            if op not in want:
                continue
            p = int(b.get("param") or 0)
            if p not in PROVEN_HERO_NET_ID_SET:
                continue
            out[op].append(
                {
                    "time": float(b["time"]),
                    "param": p,
                    "payload": b.get("payload") or b"",
                }
            )
    for op in out:
        out[op].sort(key=lambda r: r["time"])
    return dict(out)


def diversify(rows: Sequence[dict], n: int) -> List[dict]:
    by: Dict[int, List[dict]] = defaultdict(list)
    for r in rows:
        by[int(r["param"])].append(r)
    out: List[dict] = []
    heroes = list(by.keys()) or [0]
    per = max(1, (n + len(heroes) - 1) // len(heroes))
    for h in heroes:
        rs = by.get(h) or []
        if not rs:
            continue
        for i in range(min(per, len(rs))):
            out.append(rs[int(i * (len(rs) - 1) / max(1, per - 1))])
    seen = set()
    uniq = []
    for r in sorted(out, key=lambda x: x["time"]):
        k = (round(r["time"], 3), r["param"])
        if k in seen:
            continue
        seen.add(k)
        uniq.append(r)
    return uniq[:n]


def capture_direct_input_xyz(
    binary: Any, factory: Mapping[str, Any], blocks: Sequence[dict]
) -> List[dict]:
    deser = int(factory["deserializeVa"])
    osz = int(factory["objectSize"])
    out = []
    for b in blocks:
        emu = WinX64PacketEmu(binary)
        fr = emu.construct(
            ctor_va=int(factory["ctorVa"]),
            object_size=osz,
            expected_opcode=OPCODE_DIRECT_INPUT,
            expected_vptr=int(factory["vptr"]),
        )
        if not fr.get("ok"):
            continue
        obj = fr["obj"]
        hit: Dict[str, Any] = {}

        def on_end(uc: Any, address: int, size: int, user: Any) -> None:
            try:
                hit["xyz"] = struct.unpack("<fff", bytes(uc.mem_read(obj + 0x10, 12)))
            except Exception as exc:  # noqa: BLE001
                hit["err"] = str(exc)

        h = emu.mu.hook_add(
            UC_HOOK_CODE, on_end, begin=DIRECT_INPUT_END_READ_VA, end=DIRECT_INPUT_END_READ_VA
        )
        body = deserialize_body(OPCODE_DIRECT_INPUT, b["payload"])
        r = emu.deserialize(obj=obj, deser_va=deser, payload=body, object_size=osz)
        try:
            emu.mu.hook_del(h)
        except Exception:  # noqa: BLE001
            pass
        if "xyz" not in hit:
            continue
        x, y, z = hit["xyz"]
        if not (_f32_map(x) and _f32_map(z)):
            continue
        out.append(
            {
                "t": float(b["time"]),
                "param": int(b["param"]),
                "x": float(x),
                "y": float(y),
                "z": float(z),
                "retAl": int(r.get("retAl") or 0),
                "source": "directinput_END_READ_obj+0x10",
            }
        )
    return out


def capture_908_xyz(
    binary: Any, factory: Mapping[str, Any], blocks: Sequence[dict]
) -> List[dict]:
    """E12 near-miss layout obj+16/+20 via MEM_WRITE during recon Deserialize."""
    deser = int(factory["deserializeVa"])
    osz = max(int(factory["objectSize"]), 64)
    out = []
    for b in blocks:
        emu = WinX64PacketEmu(binary)
        fr = emu.construct(
            ctor_va=int(factory["ctorVa"]),
            object_size=osz,
            expected_opcode=OPCODE_NEAR_MISS,
            expected_vptr=int(factory["vptr"]),
        )
        if not fr.get("ok"):
            continue
        obj = fr["obj"]
        last: Dict[int, float] = {}

        def on_write(uc: Any, access: int, address: int, size: int, value: int, user: Any) -> None:
            if size != 4:
                return
            f32 = struct.unpack("<f", struct.pack("<I", value & 0xFFFFFFFF))[0]
            off = int(address - obj)
            if off in (16, 20) and _f32_map(f32):
                last[off] = float(f32)

        h = emu.mu.hook_add(UC_HOOK_MEM_WRITE, on_write)
        body = MARKER_1 + b["payload"]
        r = emu.deserialize(obj=obj, deser_va=deser, payload=body, object_size=osz)
        try:
            emu.mu.hook_del(h)
        except Exception:  # noqa: BLE001
            pass
        if 16 not in last or 20 not in last:
            continue
        out.append(
            {
                "t": float(b["time"]),
                "param": int(b["param"]),
                "x": last[16],
                "y": 0.0,
                "z": last[20],
                "retAl": int(r.get("retAl") or 0),
                "source": "opcode908_obj+16/+20",
            }
        )
    return out


def apply_via_path_setter_and_get(
    binary: Any, samples: Sequence[dict]
) -> List[dict]:
    """Fallback apply: place packet XYZ into proven GetPosition slot, then read back.

    ``PathSetPositionCore`` (0x140389200) writes a *normalized direction* into
    PathController+0x20 — not absolute map XYZ — so it is not used for oracle QA.
    Absolute world position is poked into hero+0x28F0 (= PC+0x20), then captured
    via GetPosition (HP-analogue: write slot → getter).
    """
    out = []
    for s in samples:
        emu = WinX64PacketEmu(binary)
        hero = emu._alloc(0x4000, kind="hero", pc=0)
        apply_mode = "absolute_slot_poke_then_getposition"
        emu.mu.mem_write(
            hero + HERO_POSITION_ABS,
            struct.pack("<fff", float(s["x"]), float(s["y"]), float(s["z"])),
        )
        try:
            rax = unicorn_call(
                emu, fn=GET_POSITION_VA, rcx=hero + PATH_CONTROLLER_IN_HERO
            )
            gx, gy, gz = struct.unpack("<fff", bytes(emu.mu.mem_read(rax, 12)))
        except Exception as exc:  # noqa: BLE001
            out.append({**s, "getOk": False, "error": str(exc), "applyMode": apply_mode})
            continue
        out.append(
            {
                **s,
                "getOk": True,
                "applyMode": apply_mode,
                "gx": float(gx),
                "gy": float(gy),
                "gz": float(gz),
                "roundTrip": abs(gx - s["x"]) < 1e-2 and abs(gz - s["z"]) < 1e-2,
            }
        )
    return out


def prove_setter_is_direction_not_absolute(binary: Any) -> dict:
    """Document that PathSetPositionCore normalizes; not absolute world write."""
    emu = WinX64PacketEmu(binary)
    hero = emu._alloc(0x4000, kind="hero", pc=0)
    vec = emu._alloc(16, kind="vec3", pc=0)
    x, y, z = 1111.0, 22.0, 3333.0
    emu.mu.mem_write(vec, struct.pack("<fff", x, y, z))
    try:
        unicorn_call(
            emu,
            fn=PATH_SET_POSITION_CORE_VA,
            rcx=hero + PATH_CONTROLLER_IN_HERO,
            rdx=vec,
        )
        gx, gy, gz = struct.unpack(
            "<fff", bytes(emu.mu.mem_read(hero + HERO_POSITION_ABS, 12))
        )
        n = math.sqrt(x * x + z * z) or 1.0
        return {
            "ok": True,
            "wroteNormalizedDirection": abs(gx - x / n) < 1e-3 and abs(gz - z / n) < 1e-3,
            "input": [x, y, z],
            "slotAfter": [gx, gy, gz],
            "note": "PathSetPositionCore ≠ absolute map XYZ writer",
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


def qa_getter_samples(samples: Sequence[dict], oracle: Sequence[dict]) -> dict:
    """QA using GetPosition readback (gx/gz) when present, else x/z."""
    rows = [s for s in samples if s.get("getOk")]
    if len(rows) < 4:
        return {"winnerFound": False, "reason": "too_few_getter_samples", "n": len(rows)}
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

    tr = run(train, False)
    ho = run(hold, False)
    tr_s = run(train, True)
    ho_s = run(hold, True)
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
        "roundTripOk": sum(1 for s in rows if s.get("roundTrip")) ,
        "roundTripN": len(rows),
    }


def classify_blocker(
    *,
    discovery: Mapping[str, Any],
    geometry: Mapping[str, Any],
    use_vt: Mapping[str, Any],
    evaluations: Sequence[dict],
) -> dict:
    if not discovery.get("getPositionVa") or discovery.get("leaRaxRcx20RetCount", 0) < 1:
        return {
            "kind": "no_position_getter_slots",
            "detail": "could not recover GetPosition / PathController+0x20 slot evidence",
        }
    if not geometry.get("ok"):
        return {
            "kind": "pathcontroller_heap_not_emulatable",
            "detail": "GetPosition slot geometry could not be exercised under Unicorn stub",
        }
    winners = [e for e in evaluations if e.get("qa", {}).get("winnerFound")]
    if winners:
        return {"kind": "none", "detail": "winner found"}
    getter_n = sum(int(e.get("getterSamples") or 0) for e in evaluations)
    if getter_n <= 0:
        return {
            "kind": "pathcontroller_heap_not_emulatable",
            "detail": (
                "slots/getter proven statically, but Deserialize→Use cannot bind a real "
                "PathController heap under Unicorn (no getter samples after apply attempt)"
            ),
            "packetUseNotWorldApply": True,
            "useVtable": use_vt,
        }
    best = None
    for e in evaluations:
        ho = (e.get("qa") or {}).get("holdout") or {}
        if ho.get("median") is None:
            continue
        if best is None or ho["median"] < best["median"]:
            best = {"opcode": e.get("opcode"), "source": e.get("source"), **ho}
    return {
        "kind": "getters_found_but_values_not_oracle",
        "detail": (
            "GetPosition@PathController+0x20 (hero+0x28F0) proven; packet virt Use is "
            "size/clone not world-apply; absolute slot poke of reconstructed packet XYZ "
            "round-trips through GetPosition but fails Replay API live-position gates "
            "(PathSetPositionCore normalizes direction≠absolute; true locomotion apply "
            "needs full AIBase/PathController heap)"
        ),
        "bestNearMiss": best,
        "packetUseNotWorldApply": True,
        "useVtable": use_vt,
    }


def run_e14(
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

    discovery = discover_position_path(binary)
    geometry = prove_getter_geometry(binary)
    setter_dir = prove_setter_is_direction_not_absolute(binary)
    use_vt = inspect_packet_use_vtable(binary, factories)

    oracle = _load_oracle_positions(oracle_jsonl)
    blocks = collect_blocks(
        rofl, [OPCODE_DIRECT_INPUT, OPCODE_NEAR_MISS, OPCODE_SET_MOVEMENT_DRIVER]
    )

    evaluations = []
    # DirectInput
    if OPCODE_DIRECT_INPUT in factories and blocks.get(OPCODE_DIRECT_INPUT):
        samp = diversify(blocks[OPCODE_DIRECT_INPUT], MAX_SAMPLES_58)
        di = capture_direct_input_xyz(binary, factories[OPCODE_DIRECT_INPUT], samp)
        got = apply_via_path_setter_and_get(binary, di)
        qa = qa_getter_samples(got, oracle)
        evaluations.append(
            {
                "opcode": OPCODE_DIRECT_INPUT,
                "source": "Deserialize+END_READ → absolute GetPosition-slot poke → GetPosition",
                "captured": len(di),
                "getterSamples": sum(1 for s in got if s.get("getOk")),
                "qa": qa,
            }
        )
    # 908 near-miss
    if OPCODE_NEAR_MISS in factories and blocks.get(OPCODE_NEAR_MISS):
        samp = diversify(blocks[OPCODE_NEAR_MISS], MAX_SAMPLES_908)
        rows908 = capture_908_xyz(binary, factories[OPCODE_NEAR_MISS], samp)
        got = apply_via_path_setter_and_get(binary, rows908)
        qa = qa_getter_samples(got, oracle)
        evaluations.append(
            {
                "opcode": OPCODE_NEAR_MISS,
                "source": "Deserialize MEM_WRITE +16/+20 → absolute GetPosition-slot poke → GetPosition",
                "captured": len(rows908),
                "getterSamples": sum(1 for s in got if s.get("getOk")),
                "qa": qa,
            }
        )

    winner = None
    for e in evaluations:
        if e.get("qa", {}).get("winnerFound"):
            winner = {
                "opcode": e["opcode"],
                "getterVa": hex(GET_POSITION_VA),
                "slot": {
                    "pathControllerInHero": hex(PATH_CONTROLLER_IN_HERO),
                    "positionInPathController": hex(POSITION_IN_PATH_CONTROLLER),
                    "heroAbsolute": hex(HERO_POSITION_ABS),
                },
                "layout": "PathController+0x20 Vector3 <fff>",
                "qa": e["qa"],
                "source": e["source"],
            }
            break

    blocker = classify_blocker(
        discovery=discovery, geometry=geometry, use_vt=use_vt, evaluations=evaluations
    )
    wall_ms = (time.perf_counter() - t0) * 1000.0

    report = {
        "ok": bool(winner),
        "probeVersion": PROBE_VERSION,
        "hypothesis": "phase-b-e14-position-getters",
        "matchCode": MATCH_CODE,
        "wallMs": round(wall_ms, 3),
        "wallTargetMs": 60_000,
        "wallPass": wall_ms <= 60_000,
        "official": prov,
        "binaryManifest": man,
        "constructorCoverage": coverage,
        "discovery": discovery,
        "getterGeometryProof": geometry,
        "pathSetPositionCoreIsDirection": setter_dir,
        "packetUseVtable": use_vt,
        "evaluations": evaluations,
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
                "No native 1Hz claim. DirectInput remains sparse/single-hero; "
                "908 is higher coverage but still not oracle live positions."
            ),
        },
        "blocker": blocker,
        "pureDecoderDerived": False,
        "browserSafe": False,
        "productEligible": False,
        "identity": {
            "createHeroBindingDecoded": False,
            "productEligible": False,
            "note": "PathController slot is geometric; not CreateHero/PUUID product bind",
        },
        "method": {
            "static": "GetPosition lea rax,[rcx+0x20]; PathController at hero+0x28d0",
            "applyFallback": (
                "packet virt Use is not world-apply; absolute XYZ poked into proven "
                f"GetPosition slot hero+{hex(HERO_POSITION_ABS)} then read via "
                f"GetPosition@{hex(GET_POSITION_VA)}; PathSetPositionCore@"
                f"{hex(PATH_SET_POSITION_CORE_VA)} writes normalized direction only"
            ),
            "noLearnedAffine": True,
        },
    }

    keep = "keep" if winner else "discard"
    reason = (
        f"E14 winner opcode={winner['opcode']} getter={winner['getterVa']}"
        if winner
        else f"E14 blocker={blocker['kind']}: {str(blocker.get('detail') or '')[:180]}"
    )
    if not dry_run:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        append_speed_record(
            log=SPEED_LOG,
            hypothesis="phase-b-e14-position-getters",
            diff_label="e14-pathcontroller-getposition",
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
                "getterGeometryOk": geometry.get("ok"),
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
    report = run_e14(
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
                "discovery": {
                    k: (report.get("discovery") or {}).get(k)
                    for k in (
                        "getPositionVa",
                        "pathControllerInHero",
                        "positionInPathController",
                        "heroAbsolutePosition",
                        "getPositionCallers",
                    )
                },
                "getterGeometryOk": (report.get("getterGeometryProof") or {}).get("ok"),
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
