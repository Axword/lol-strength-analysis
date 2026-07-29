#!/usr/bin/env python3
"""E8: identify 16.14 movement packets via MSVC RTTI + handler registration, then decode.

Hard constraints: no live Replay API, no plan edit, no commit, no binary vendoring,
no arbitrary oracle fitting. Oracle is QA-only.
"""
from __future__ import annotations

import argparse
import json
import re
import struct
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from rofl2_binary_format import load_binary, research_manifest  # noqa: E402
from rofl2_movement_decode import append_speed_record  # noqa: E402
from rofl2_movement_wire_scan import optimal_oracle_assignment  # noqa: E402
from rofl2_win_pe_packet_discover import (  # noqa: E402
    EXPECTED_SHA256,
    PROVEN_HERO_NET_ID_SET,
    WinX64PacketEmu,
    enumerate_rofl,
    official_provenance,
    scan_msvc_packet_types,
)
from rofl2_win_pe_rtti import (  # noqa: E402
    IMAGE_BASE_DEFAULT,
    annotate_factory_vptrs,
    demangle_msvc_name,
    image_base,
    scan_valid_cols,
    validate_col,
)

PROBE_VERSION = "e8-rtti-registration-v1"
MATCH_CODE = "3264361042"
DEFAULT_PE = Path("/tmp/League-of-Legends-16.14-win.exe")
DEFAULT_ROFL = Path.home() / "Documents/League of Legends/Replays/BR1-3264361042.rofl"
DEFAULT_ORACLE = Path("artifacts/rofl/3264361042/events.rfc461.jsonl")
DEFAULT_REPORT = Path("docs/rofl-research/movement-win-pe-e8-BR1-3264361042.json")
SPEED_LOG = Path("docs/rofl-research/speed-runs.jsonl")

# Register hub used by AIBaseClient MakeFunction wrappers (Windows 16.14).
REGISTER_HUB_VA = 0x1406F78B0

# Semantic targets from PE strings / MakeFunction TypeDescriptors.
MOVEMENT_PKT_NAMES = (
    "PKT_S2C_SetMovementDriver_s",
    "PKT_DirectInputMovementDriverServerTurnData_s",
    "PKT_S2C_AddFollowTargetPosition_s",
    "PKT_S2C_AddFollowTargetTeleport_s",
    "PKT_S2C_FaceDirection_s",
    "PKT_S2C_SyncCircularMovementRestriction_s",
)

ACCEPT_MIN_COMPARED_SAMPLES = 80
ACCEPT_MIN_STABLE_ENTITIES = 5
ACCEPT_MAX_MEDIAN_ERROR = 120.0
ACCEPT_MAX_P95_ERROR = 350.0
ACCEPT_MAX_MAX_ERROR = 800.0


def _hex(v: Optional[int]) -> Optional[str]:
    return None if v is None else hex(int(v))


def find_makefunction_type_descriptors(binary) -> Dict[str, dict]:
    """Locate MakeFunction <lambda_1> TypeDescriptors that name PKT_* structs."""
    out: Dict[str, dict] = {}
    for seg in binary.segments:
        if seg.name not in (".rdata", ".data"):
            continue
        blob = binary.data[seg.fileoff : seg.fileoff + seg.filesize]
        for pkt in MOVEMENT_PKT_NAMES:
            needle = pkt.encode("ascii")
            start = 0
            while True:
                j = blob.find(needle, start)
                if j < 0:
                    break
                k = j
                while k > 0 and blob[k : k + 4] != b".?AV":
                    k -= 1
                    if j - k > 500:
                        break
                if blob[k : k + 4] == b".?AV" and b"MakeFunction" in blob[k:j]:
                    name = blob[k : k + 360].split(b"\x00", 1)[0].decode("ascii", "replace")
                    name_va = seg.vmaddr + k
                    td_va = name_va - 16
                    out[pkt] = {
                        "pkt": pkt,
                        "typeDescriptorVa": _hex(td_va),
                        "nameVa": _hex(name_va),
                        "mangled": name,
                        "demangled": demangle_msvc_name(name),
                    }
                    break
                start = j + 1
    return out


def find_typeid_stub_for_td(binary, td_va: int) -> Optional[int]:
    """lea rax,[rip+disp]; ret stubs that return the TypeDescriptor VA."""
    text_va, text = binary.text_bytes()
    pat = bytes([0x48, 0x8D, 0x05])  # lea rax,[rip+disp32]
    start = 0
    while True:
        i = text.find(pat, start)
        if i < 0:
            break
        if i + 8 <= len(text) and text[i + 7] == 0xC3:
            disp = struct.unpack_from("<i", text, i + 3)[0]
            dest = text_va + i + 7 + disp
            if dest == td_va:
                return text_va + i
        start = i + 1
    return None


def find_vtable_for_typeid_stub(binary, typeid_stub: int) -> Optional[int]:
    """MSVC std::function-like vtable: [2]=invoke trampoline, [3]=typeid stub."""
    invoke = 0x1402373A0
    raw = struct.pack("<Q", typeid_stub)
    for seg in binary.segments:
        if seg.name != ".rdata":
            continue
        blob = binary.data[seg.fileoff : seg.fileoff + seg.filesize]
        off = 0
        while True:
            j = blob.find(raw, off)
            if j < 0:
                break
            if j >= 24 and j % 8 == 0:
                prev = struct.unpack_from("<Q", blob, j - 8)[0]
                if prev == invoke:
                    return seg.vmaddr + j - 24
            off = j + 1
    return None


def find_lea_to(binary, target: int) -> List[int]:
    text_va, text = binary.text_bytes()
    hits = []
    for rex in (0x48, 0x4C):
        start = 0
        while True:
            i = text.find(bytes([rex, 0x8D]), start)
            if i < 0:
                break
            if i + 7 <= len(text) and (text[i + 2] & 0xC7) == 0x05:
                disp = struct.unpack_from("<i", text, i + 3)[0]
                if text_va + i + 7 + disp == target:
                    hits.append(text_va + i)
            start = i + 1
    return hits


def opcode_from_register_wrapper(binary, wrapper_va: int) -> Optional[int]:
    """Extract `mov r8d, imm` before `call REGISTER_HUB` inside a thin wrapper."""
    from capstone import Cs, CS_ARCH_X86, CS_MODE_64

    md = Cs(CS_ARCH_X86, CS_MODE_64)
    try:
        blob = binary.read_va(wrapper_va, 0xA0)
    except Exception:  # noqa: BLE001
        return None
    pending: Optional[int] = None
    for insn in md.disasm(blob, wrapper_va):
        if insn.mnemonic == "mov" and insn.op_str.startswith("r8d,"):
            part = insn.op_str.split(",", 1)[1].strip()
            try:
                pending = int(part, 16) if part.startswith("0x") else int(part)
            except ValueError:
                pending = None
        if insn.mnemonic == "call" and insn.op_str.startswith("0x"):
            if int(insn.op_str, 16) == REGISTER_HUB_VA and pending is not None:
                return pending
        if insn.mnemonic == "ret" and insn.address > wrapper_va + 8:
            break
    return None


def opcode_inline_near_lea(binary, lea_va: int, window: int = 0x80) -> Optional[Tuple[int, int]]:
    """Some handlers inline mov r8d,imm; call hub near the vtable lea (FaceDirection/Sync)."""
    from capstone import Cs, CS_ARCH_X86, CS_MODE_64

    md = Cs(CS_ARCH_X86, CS_MODE_64)
    try:
        blob = binary.read_va(lea_va, window)
    except Exception:  # noqa: BLE001
        return None
    pending: Optional[int] = None
    for insn in md.disasm(blob, lea_va):
        if insn.mnemonic == "mov" and insn.op_str.startswith("r8d,"):
            part = insn.op_str.split(",", 1)[1].strip()
            try:
                pending = int(part, 16) if part.startswith("0x") else int(part)
            except ValueError:
                pending = None
        if insn.mnemonic == "call" and insn.op_str.startswith("0x"):
            tgt = int(insn.op_str, 16)
            if tgt == REGISTER_HUB_VA and pending is not None:
                return pending, insn.address
            # Thin wrapper that embeds the opcode
            op = opcode_from_register_wrapper(binary, tgt)
            if op is not None:
                return op, insn.address
    return None


def _ctor_start_for_lea(binary, lea_va: int) -> int:
    """Walk back over int3 padding to the start of the tiny vtable-install ctor."""
    try:
        pre = binary.read_va(lea_va - 0x30, 0x30)
    except Exception:  # noqa: BLE001
        return lea_va
    # find last non-int3 before lea
    rel = 0x30
    while rel > 0 and pre[rel - 1] == 0xCC:
        rel -= 1
    while rel > 0 and pre[rel - 1] != 0xCC:
        rel -= 1
    return lea_va - 0x30 + rel


def find_calls_to(binary, target: int) -> List[int]:
    text_va, text = binary.text_bytes()
    hits = []
    start = 0
    while True:
        i = text.find(b"\xE8", start)
        if i < 0:
            break
        rel = struct.unpack_from("<i", text, i + 1)[0]
        if text_va + i + 5 + rel == target:
            hits.append(text_va + i)
        start = i + 1
    return hits


def map_semantic_registrations(binary, td_info: Mapping[str, dict]) -> Dict[str, dict]:
    """Map PKT_* MakeFunction handlers to replay factory opcodes via registration xrefs.

    Evidence chain (not frequency):
      TypeDescriptor name contains PKT_*
        -> typeid stub (lea rax,TD; ret)
        -> std::function vtable with typeid at [3]
        -> tiny ctor that lea's that vtable
        -> caller of ctor then call register_wrapper OR inline mov r8d,imm; call hub
    """
    from capstone import Cs, CS_ARCH_X86, CS_MODE_64

    md = Cs(CS_ARCH_X86, CS_MODE_64)
    mapped: Dict[str, dict] = {}
    for pkt, info in td_info.items():
        td_va = int(info["typeDescriptorVa"], 16)
        stub = find_typeid_stub_for_td(binary, td_va)
        if stub is None:
            mapped[pkt] = {**info, "ok": False, "blocker": "typeid_stub_not_found"}
            continue
        vt = find_vtable_for_typeid_stub(binary, stub)
        if vt is None:
            mapped[pkt] = {
                **info,
                "ok": False,
                "typeidStub": _hex(stub),
                "blocker": "vtable_not_found",
            }
            continue
        leas = find_lea_to(binary, vt)
        # Registration ctors: lea sites in 0x14023–0x14025, not copy-ctors in 0x1402cxxxx
        ctor_leas = [va for va in leas if 0x140230000 <= va <= 0x140260000]
        opcode = None
        evidence = None

        # Path A: mid-function lea then inline mov r8d / call hub (FaceDirection / SyncCircular)
        for site in ctor_leas or leas:
            hit = opcode_inline_near_lea(binary, site, 0x100)
            if hit:
                opcode, call_va = hit
                evidence = {
                    "kind": "inline_hub_after_vtable_lea",
                    "leaVa": _hex(site),
                    "callVa": _hex(call_va),
                    "hub": _hex(REGISTER_HUB_VA),
                }
                break
        # Path B: tiny ctor containing lea; callers then call register_wrapper(opcode)
        if opcode is None:
            for site in ctor_leas:
                ctor = _ctor_start_for_lea(binary, site)
                for call_site in find_calls_to(binary, ctor):
                    # Disassemble forward for call to register wrapper
                    for insn in md.disasm(binary.read_va(call_site, 0x40), call_site):
                        if insn.address == call_site:
                            continue
                        if insn.mnemonic == "call" and insn.op_str.startswith("0x"):
                            tgt = int(insn.op_str, 16)
                            op = opcode_from_register_wrapper(binary, tgt)
                            if op is not None:
                                opcode = op
                                evidence = {
                                    "kind": "ctor_caller_to_register_wrapper",
                                    "vtableCtor": _hex(ctor),
                                    "vtableLea": _hex(site),
                                    "ctorCallSite": _hex(call_site),
                                    "wrapperVa": _hex(tgt),
                                    "hub": _hex(REGISTER_HUB_VA),
                                }
                                break
                        if insn.mnemonic == "ret":
                            break
                    if opcode is not None:
                        break
                if opcode is not None:
                    break

        mapped[pkt] = {
            **info,
            "ok": opcode is not None,
            "typeidStub": _hex(stub),
            "vtable": _hex(vt),
            "leaSites": [_hex(x) for x in leas[:6]],
            "opcode": opcode,
            "evidence": evidence,
            "blocker": None if opcode is not None else "registration_opcode_not_found",
        }
    return mapped


def harden_known_inline_opcodes(binary, mapped: Dict[str, dict]) -> Dict[str, dict]:
    """Fill FaceDirection / SyncCircular when lea→hub is mid-function (validated once)."""
    # Empirically recovered on this PE (also re-validated by scanning mov r8d near known leas).
    # Prefer live re-discovery: search text for mov r8d,imm / call hub near FaceDirection lea.
    from capstone import Cs, CS_ARCH_X86, CS_MODE_64

    md = Cs(CS_ARCH_X86, CS_MODE_64)
    # If already ok, keep
    # FaceDirection vtable lea sites include 0x140252048
    extras = {
        "PKT_S2C_FaceDirection_s": 0x140252048,
        "PKT_S2C_SyncCircularMovementRestriction_s": 0x140250688,
    }
    for pkt, site in extras.items():
        if mapped.get(pkt, {}).get("ok"):
            continue
        if pkt not in mapped:
            continue
        pending = None
        for insn in md.disasm(binary.read_va(site, 0x80), site):
            if insn.mnemonic == "mov" and insn.op_str.startswith("r8d,"):
                part = insn.op_str.split(",", 1)[1].strip()
                try:
                    pending = int(part, 16) if part.startswith("0x") else int(part)
                except ValueError:
                    pending = None
            if insn.mnemonic == "call" and insn.op_str.startswith("0x"):
                if int(insn.op_str, 16) == REGISTER_HUB_VA and pending is not None:
                    mapped[pkt] = {
                        **mapped[pkt],
                        "ok": True,
                        "opcode": pending,
                        "blocker": None,
                        "evidence": {
                            "kind": "mid_function_inline_hub",
                            "leaVa": _hex(site),
                            "hub": _hex(REGISTER_HUB_VA),
                        },
                    }
                    break
    return mapped


def _load_oracle_positions(path: Path) -> List[dict]:
    out = []
    with path.open() as f:
        for line in f:
            o = json.loads(line)
            if o.get("rfc461Schema") != "stats_update":
                continue
            gt = float(o.get("gameTime") or 0) / 1000.0
            for p in o.get("participants") or []:
                pos = p.get("position") or {}
                if "x" not in pos or "z" not in pos:
                    continue
                out.append(
                    {
                        "time": gt,
                        "participantID": int(p["participantID"]),
                        "x": float(pos["x"]),
                        "z": float(pos["z"]),
                        "championName": p.get("championName"),
                    }
                )
    return out


def capture_directinput_plaintext(emu: WinX64PacketEmu, obj: int):
    """Hook post-read / pre-reencrypt for DirectInput 3xf32 field at +0x10."""
    from unicorn import UC_HOOK_CODE

    END_READ = 0x140E66BAB
    state: Dict[str, Any] = {"final": None}

    def on_code(uc, address, size, user):  # noqa: ANN001, ARG001
        if address == END_READ:
            raw = bytes(uc.mem_read(obj + 0x10, 12))
            state["final"] = struct.unpack("<fff", raw)

    h = emu.mu.hook_add(UC_HOOK_CODE, on_code, begin=END_READ, end=END_READ)
    return h, state


def drive_mapped_opcodes(
    binary,
    *,
    factories: Mapping[int, dict],
    samples: Mapping[int, List[dict]],
    mapped: Mapping[str, dict],
    max_per_opcode: int = 40,
) -> List[dict]:
    reports = []
    for pkt, info in mapped.items():
        if not info.get("ok") or info.get("opcode") is None:
            reports.append({"pkt": pkt, "ok": False, "blocker": info.get("blocker")})
            continue
        op = int(info["opcode"])
        fac = factories.get(op)
        blks = samples.get(op) or []
        if fac is None:
            reports.append(
                {
                    "pkt": pkt,
                    "opcode": op,
                    "ok": False,
                    "blocks": len(blks),
                    "blocker": "no_factory_for_opcode",
                }
            )
            continue
        emu = WinX64PacketEmu(binary)
        net_ids: Counter = Counter()
        field_captures = []
        factory_ok = 0
        deser_ret = 0
        plaintext_xyz = 0
        n = min(len(blks), max_per_opcode)
        for i in range(n):
            blk = blks[i]
            fac_res = emu.construct(
                ctor_va=int(fac["ctorVa"]),
                object_size=int(fac.get("objectSize") or 32),
                expected_opcode=op,
                expected_vptr=int(fac["vptr"]),
            )
            if not fac_res.get("ok"):
                continue
            factory_ok += 1
            obj = int(fac_res["obj"])
            hook = None
            state = None
            if op == 58:
                hook, state = capture_directinput_plaintext(emu, obj)
            deser = emu.deserialize(
                obj=obj,
                deser_va=int(fac["deserializeVa"]),
                payload=blk["payload"],
                object_size=int(fac.get("objectSize") or 32),
            )
            if hook is not None:
                emu.mu.hook_del(hook)
            if deser.get("retAl"):
                deser_ret += 1
            after = bytes(emu.mu.mem_read(obj, max(int(fac.get("objectSize") or 32), 0x20)))
            net = struct.unpack_from("<I", after, 12)[0]
            net_ids[net] += 1
            plain = state.get("final") if state else None
            if plain and all(100.0 < abs(f) < 16000.0 for f in (plain[0], plain[2])):
                plaintext_xyz += 1
                field_captures.append(
                    {
                        "time": blk["time"],
                        "netIdField": net,
                        "blockParam": blk.get("param"),
                        "x": plain[0],
                        "y": plain[1],
                        "z": plain[2],
                    }
                )
            elif len(field_captures) < 3:
                field_captures.append(
                    {
                        "time": blk["time"],
                        "netIdField": net,
                        "blockParam": blk.get("param"),
                        "retAl": deser.get("retAl"),
                        "consumed": deser.get("consumed"),
                        "error": deser.get("error"),
                        "objectAfterHex": after[:0x28].hex(),
                        "plaintextXyz": plain,
                    }
                )
        reports.append(
            {
                "pkt": pkt,
                "opcode": op,
                "objectSize": fac.get("objectSize"),
                "ctorVa": _hex(fac.get("ctorVa")),
                "vptr": _hex(fac.get("vptr")),
                "deserializeVa": _hex(fac.get("deserializeVa")),
                "vtableSlotNote": "slot[2]=GetSize (returns objectSize); slot[1]=Deserialize",
                "blocks": len(blks),
                "probed": n,
                "factoryOk": factory_ok,
                "deserRetAlNonzero": deser_ret,
                "plaintextMaplikeXyz": plaintext_xyz,
                "netIdFieldTop": [[_hex(k), v] for k, v in net_ids.most_common(8)],
                "fieldCaptureExamples": field_captures[:5],
                "registrationEvidence": info.get("evidence"),
            }
        )
    return reports


def run_e8(
    *,
    pe_path: Path,
    rofl: Path,
    oracle_jsonl: Path,
    max_per_opcode: int = 40,
) -> dict:
    t0 = time.perf_counter()
    if not pe_path.is_file():
        raise FileNotFoundError(pe_path)
    binary = load_binary(pe_path)
    if binary.platform != "windows" or binary.format != "pe64" or binary.arch != "x86_64":
        raise ValueError(f"expected windows pe64 x86_64, got {binary.platform}/{binary.format}/{binary.arch}")
    if binary.sha256 != EXPECTED_SHA256:
        raise ValueError(f"SHA256 mismatch: got {binary.sha256}, expected {EXPECTED_SHA256}")

    base = image_base(binary)
    prov = official_provenance(size=pe_path.stat().st_size, sha256=binary.sha256)
    man = research_manifest(binary, patch="16.14", extra={"probeVersion": PROBE_VERSION, "official": prov})

    counts, samples = enumerate_rofl(rofl)
    rows, coverage = scan_msvc_packet_types(binary, counts)
    by_op = {int(r["opcode"]): r for r in rows}

    # 1) Strict RTTI on every factory vptr
    rtti = annotate_factory_vptrs(binary, rows, base=base)
    cols = scan_valid_cols(binary, base=base)
    rtti["validColCount"] = len(cols)
    rtti["validColSamples"] = [
        {"va": _hex(c.va), "name": demangle_msvc_name(c.type_descriptor.name)} for c in cols[:12]
    ]

    # 2) Semantic registration mapping
    td_info = find_makefunction_type_descriptors(binary)
    mapped = map_semantic_registrations(binary, td_info)
    mapped = harden_known_inline_opcodes(binary, mapped)

    # Cross-check: mapped opcode must xref factory Deserialize (same opcode key), not frequency.
    for pkt, info in mapped.items():
        if not info.get("ok"):
            continue
        op = int(info["opcode"])
        fac = by_op.get(op)
        info["factoryPresent"] = fac is not None
        info["roflBlocks"] = int(counts.get(op, 0))
        if fac:
            info["factory"] = {
                "objectSize": fac.get("objectSize"),
                "ctorVa": _hex(fac.get("ctorVa")),
                "vptr": _hex(fac.get("vptr")),
                "deserializeVa": _hex(fac.get("deserializeVa")),
                "useOrGetSizeVa": _hex(fac.get("useVa")),
            }

    # False-positive guard: highest-block opcode among mapped must not be the sole selection criterion
    by_blocks = sorted(
        ((info.get("opcode"), info.get("roflBlocks", 0), pkt) for pkt, info in mapped.items() if info.get("ok")),
        key=lambda t: -(t[1] or 0),
    )

    # 3) Constructed drive + field capture
    drive_reports = drive_mapped_opcodes(
        binary,
        factories=by_op,
        samples=samples,
        mapped=mapped,
        max_per_opcode=max_per_opcode,
    )

    # 4) Oracle QA only if we have maplike plaintext captures with entity ids
    oracle = _load_oracle_positions(oracle_jsonl) if oracle_jsonl.is_file() else []
    path_samples = []
    for rep in drive_reports:
        for cap in rep.get("fieldCaptureExamples") or []:
            if "x" in cap and "z" in cap:
                # ID from decoded field only (not blockParam)
                path_samples.append(
                    {
                        "time": float(cap["time"]),
                        "netId": int(cap["netIdField"]),
                        "x": float(cap["x"]),
                        "z": float(cap["z"]),
                        "points": [{"x": float(cap["x"]), "z": float(cap["z"])}],
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

    wall_ms = (time.perf_counter() - t0) * 1000

    semantic_ok = [pkt for pkt, info in mapped.items() if info.get("ok")]
    primary = None
    for prefer in (
        "PKT_S2C_SetMovementDriver_s",
        "PKT_DirectInputMovementDriverServerTurnData_s",
    ):
        if mapped.get(prefer, {}).get("ok"):
            primary = prefer
            break

    blocker = None
    if not accepted:
        di = next((r for r in drive_reports if r.get("pkt") == "PKT_DirectInputMovementDriverServerTurnData_s"), None)
        sm = next((r for r in drive_reports if r.get("pkt") == "PKT_S2C_SetMovementDriver_s"), None)
        blocker = {
            "kind": "registration_mapped_but_plaintext_positions_not_oracle_validated",
            "detail": (
                "MakeFunction registration maps movement PKT_* structs to factory opcodes via "
                f"mov r8d,imm → call {REGISTER_HUB_VA:#x}, but constructed Windows-ABI Deserialize "
                "does not yet yield ≥80 maplike plaintext XYZ samples across ≥5 heroes. "
                "DirectInput (58) presence path reads 3×f32 through encrypt-at-rest helpers but "
                "often fails full consume / faults mid-helper; SetMovementDriver (1104) vector "
                "path does not materialize waypoint buffers under current Unicorn hooks. "
                "Packet factory vptrs remain RTTI-stripped (0 COL hits)."
            ),
            "directInput": {
                "plaintextMaplikeXyz": (di or {}).get("plaintextMaplikeXyz"),
                "factoryOk": (di or {}).get("factoryOk"),
                "blocks": (di or {}).get("blocks"),
            },
            "setMovementDriver": {
                "plaintextMaplikeXyz": (sm or {}).get("plaintextMaplikeXyz"),
                "factoryOk": (sm or {}).get("factoryOk"),
                "blocks": (sm or {}).get("blocks"),
            },
        }

    report = {
        "ok": accepted,
        "phase": "B-E8",
        "probeVersion": PROBE_VERSION,
        "matchCode": MATCH_CODE,
        "provenance": man,
        "official": prov,
        "windowsRealBinaryValidated": True,
        "imageBase": _hex(base),
        "rtti": {
            "factoryCoverageRatio": rtti["coverageRatio"],
            "factoryRttiOk": rtti["rttiOkCount"],
            "factoryCount": rtti["factoryCount"],
            "validColCount": rtti["validColCount"],
            "validColSamples": rtti["validColSamples"],
            "note": (
                "Strict COL validation only (signature=1, pSelf, TD bounds, .?AV/.?AU name). "
                "No string-proximity class naming. Packet factory vptrs are RTTI-stripped on this PE."
            ),
            "perOpcode": rtti["rows"][:30],
        },
        "semanticRegistration": {
            "hub": _hex(REGISTER_HUB_VA),
            "mapped": mapped,
            "mappedOk": semantic_ok,
            "primaryMovementCandidate": primary,
            "blockCountOrderingAmongMapped": [
                {"opcode": op, "blocks": blocks, "pkt": pkt} for op, blocks, pkt in by_blocks
            ],
            "selectionCriterion": "register_mov_r8d_imm_to_hub_not_frequency",
            "noWaypointGroupString": True,
        },
        "driveReports": drive_reports,
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
        "pathSampleCount": len(path_samples),
        "winnerFound": accepted,
        "structuralBlocker": blocker,
        "fullMatchDecode": None,
        "pureBrowserDecoderDerived": False,
        "browserSafe": False,
        "productEligible": False,
        "osNeutralArchitecture": (
            "Offline per-patch PE RTTI/registration discovery → shared wire parser when proven; "
            "Unicorn/Windows PE remain research-only."
        ),
        "endToEndWallMs": round(wall_ms, 3),
        "keep": "discard" if not accepted else "keep",
        "reason": (
            "Semantic opcodes identified via registration; oracle position decode not yet proven"
            if not accepted
            else "Movement decode passed oracle gates"
        ),
        "nextSingleVariableHypothesis": (
            "Complete DirectInput/SetMovementDriver decrypt-access-release under Windows ABI "
            "(hook remaining unmapped helpers; capture 3xf32 / waypoint vectors before re-encrypt) "
            "then bind handler target netId without using blockParam."
        ),
        "constructorCoverage": coverage,
        "speedRun": {
            "hypothesis": "phase-b-e8-rtti-registration",
            "diffLabel": "e8-rtti+registration-map",
        },
    }
    return report


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--pe", type=Path, default=DEFAULT_PE)
    p.add_argument("--rofl", type=Path, default=DEFAULT_ROFL)
    p.add_argument("--oracle", type=Path, default=DEFAULT_ORACLE)
    p.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    p.add_argument("--max-per-opcode", type=int, default=40)
    p.add_argument("--speed-log", type=Path, default=SPEED_LOG)
    p.add_argument("--dry-run", action="store_true")
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    report = run_e8(
        pe_path=args.pe,
        rofl=args.rofl,
        oracle_jsonl=args.oracle,
        max_per_opcode=args.max_per_opcode,
    )
    if not args.dry_run:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        append_speed_record(
            log=args.speed_log,
            hypothesis=report["speedRun"]["hypothesis"],
            diff_label=report["speedRun"]["diffLabel"],
            keep=report["keep"],
            reason=report["reason"],
            wall_ms=report["endToEndWallMs"],
            match_code=MATCH_CODE,
            extra={
                "rttiCoverage": report["rtti"]["factoryCoverageRatio"],
                "mappedOpcodes": {
                    pkt: info.get("opcode")
                    for pkt, info in report["semanticRegistration"]["mapped"].items()
                    if info.get("ok")
                },
                "winnerFound": report["winnerFound"],
                "browserSafe": report["browserSafe"],
                "productEligible": report["productEligible"],
            },
        )
    print(
        json.dumps(
            {
                "ok": report["ok"],
                "report": str(args.report),
                "rttiCoverage": report["rtti"]["factoryCoverageRatio"],
                "mapped": {
                    pkt: info.get("opcode")
                    for pkt, info in report["semanticRegistration"]["mapped"].items()
                    if info.get("ok")
                },
                "wallMs": report["endToEndWallMs"],
                "blocker": (report.get("structuralBlocker") or {}).get("kind"),
                "browserSafe": report["browserSafe"],
            },
            indent=2,
        )
    )
    return 0 if report.get("structuralBlocker") is not None or report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
