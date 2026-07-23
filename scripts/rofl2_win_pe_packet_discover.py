#!/usr/bin/env python3
"""Phase B E7b: Windows x64 PE MSVC packet discovery + constructed drive.

Prior art (Toastaspiring/ROFL-X MIT; Mowokuma/ROFL facts only — no source copy) targets
Windows x86-64. Mac Itanium vtable (+0x10 adjust) must NOT be reused.

MSVC facts used independently:
  - Packet id stored at object+8 (``mov word [rcx+8], imm16``)
  - Final RIP-relative ``lea`` + ``mov [rcx], rax`` is the vptr (no +0x10)
  - Vtable: +0 dtor, +8 Deserialize, +16 Use
  - Factory: ``mov ecx, size; call operator_new; mov rcx, rax; call ctor``

Windows Unicorn ABI: RCX, RDX, R8, R9.
Never vendors/copies the Riot PE; records official manifest URL + SHA256 only.
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

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rofl2_binary_format import LoadedBinary, load_binary, research_manifest  # noqa: E402
from rofl2_probe import extract_segments, parse_rofl2  # noqa: E402
from rofl2_unicorn_packet_drive import extract_blocks_py  # noqa: E402
from rofl2_movement_decode import (  # noqa: E402
    DEFAULT_LOG,
    PROVENANCE,
    _load_oracle_positions,
    append_speed_record,
)
from rofl2_movement_emulator_probe import parse_compressed_path_packet  # noqa: E402
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

PROBE_VERSION = "e7b-win-pe-msvc-v1"
DEFAULT_PE = Path("/tmp/League-of-Legends-16.14-win.exe")
EXPECTED_SHA256 = "34de26710352fcf4360b27691cecf77843a0ea338cd455be4fabb63fb467984f"
OFFICIAL_MANIFEST_URL = (
    "https://lol.secure.dyn.riotcdn.net/channels/public/releases/952B478DFC66B0AB.manifest"
)
OFFICIAL_VERSION = (
    "16.14.7945912+branch.releases-16-14.code.public.content.release."
    "cpuarch.x86.platform.windows"
)
NORMALIZED_ROFL_BUILD = "16.14.794.5912"
# Observed operator new in this PE (factory sites).
OPERATOR_NEW_VA = 0x141196540

HEAP_BASE = 0x300000000
STACK_BASE = 0x200000000
BUF_BASE = 0x400000000
SCRATCH_BASE = 0x500000000


def official_provenance(*, size: int, sha256: str) -> dict:
    return {
        "source": "Riot PatchSieve BR1 official release",
        "version": OFFICIAL_VERSION,
        "normalizedRoflBuild": NORMALIZED_ROFL_BUILD,
        "manifestUrl": OFFICIAL_MANIFEST_URL,
        "sha256": sha256,
        "sizeBytes": size,
        "pathNote": "local /tmp only; never commit Riot binary or CDN chunks",
        "derivationStatus": "official_pe_validated",
    }


def enumerate_rofl(rofl: Path) -> Tuple[Counter, Dict[int, List[dict]]]:
    info = parse_rofl2(rofl)
    extracted = extract_segments(info["payload"])
    counts: Counter = Counter()
    samples: Dict[int, List[dict]] = defaultdict(list)
    for seg in extracted["segments"]:
        if int(seg.get("type") or 0) != 1:
            continue
        for blk in extract_blocks_py(seg["bytes"], max_blocks=500_000):
            op = int(blk["channel"])
            counts[op] += 1
            pay = blk["payload"] or b""
            if len(samples[op]) < 24:
                samples[op].append(
                    {"time": float(blk["time"]), "param": int(blk.get("param") or 0), "payload": pay}
                )
    return counts, samples


def find_opcode_stores(binary: LoadedBinary) -> Dict[int, int]:
    """Map opcode -> VA of ``mov word [rcx/rax+8], imm16``."""
    text_va, text = binary.text_bytes()
    out: Dict[int, int] = {}
    for pat in (b"\x66\xc7\x41\x08", b"\x66\xc7\x40\x08"):
        start = 0
        while True:
            i = text.find(pat, start)
            if i < 0:
                break
            op = struct.unpack_from("<H", text, i + 4)[0]
            out.setdefault(op, text_va + i)
            start = i + 1
    return out


def _ctor_start(binary: LoadedBinary, store_va: int) -> int:
    text_va, text = binary.text_bytes()
    off = store_va - text_va
    for back in range(1, 0x60):
        p = off - back
        if p >= 0 and text[p] == 0xCC:
            return text_va + p + 1
    return max(text_va, store_va - 0x20)


def recover_msvc_ctor(binary: LoadedBinary, store_va: int) -> dict:
    """Recover final MSVC vptr (last lea→mov [rcx],reg) and virt slots."""
    from capstone import Cs, CS_ARCH_X86, CS_MODE_64

    md = Cs(CS_ARCH_X86, CS_MODE_64)
    ctor = _ctor_start(binary, store_va)
    blob = binary.read_va(ctor, 0x120)
    lea_target = None
    final_vptr = None
    opcode = None
    max_off = 8
    for insn in md.disasm(blob, ctor):
        if insn.mnemonic == "lea" and "rip" in insn.op_str:
            m = re.search(r"\[rip\s*([+-]\s*0x[0-9a-f]+)\]", insn.op_str)
            if m:
                disp = int(m.group(1).replace(" ", ""), 16)
                lea_target = insn.address + insn.size + disp
        if insn.mnemonic == "mov" and "word ptr [rcx + 8]" in insn.op_str:
            imm = insn.op_str.split(",")[-1].strip()
            try:
                opcode = int(imm, 16) if imm.startswith("0x") else int(imm)
            except ValueError:
                pass
        if (
            insn.mnemonic == "mov"
            and insn.op_str.startswith("qword ptr [rcx]")
            and lea_target is not None
        ):
            final_vptr = lea_target  # MSVC: no Itanium +0x10
        m2 = re.search(r"\[rcx\s*\+\s*(0x[0-9a-f]+)\]", insn.op_str)
        if m2 and insn.mnemonic.startswith("mov"):
            max_off = max(max_off, int(m2.group(1), 16) + 8)
        if insn.mnemonic == "ret":
            break
        if insn.address > ctor + 0x100:
            break
    virt: List[Optional[int]] = []
    if final_vptr:
        try:
            virt = [binary.read_u64(final_vptr + k * 8) for k in range(4)]
        except Exception:  # noqa: BLE001
            virt = []
    return {
        "ctorVa": ctor,
        "opcodeStoreVa": store_va,
        "opcode": opcode,
        "vptr": final_vptr,
        "fieldExtent": max_off,
        "dtorVa": virt[0] if len(virt) > 0 else None,
        "deserializeVa": virt[1] if len(virt) > 1 else None,
        "useVa": virt[2] if len(virt) > 2 else None,
        "virt": virt,
    }


def discover_object_sizes(
    binary: LoadedBinary, ctor_by_op: Mapping[int, int]
) -> Dict[int, int]:
    """From factory sites: mov ecx, size; call operator_new; ... call ctor."""
    text_va, text = binary.text_bytes()
    ctor_set = {int(v): int(k) for k, v in ctor_by_op.items()}
    sizes: Dict[int, int] = {}
    for i in range(len(text) - 5):
        if text[i] != 0xE8:
            continue
        rel = struct.unpack_from("<i", text, i + 1)[0]
        tgt = text_va + i + 5 + rel
        if tgt not in ctor_set:
            continue
        back = max(0, i - 0x40)
        window = text[back:i]
        j = 0
        while j < len(window) - 10:
            if window[j] == 0xB9 and window[j + 5] == 0xE8:
                size = struct.unpack_from("<I", window, j + 1)[0]
                call_rel = struct.unpack_from("<i", window, j + 6)[0]
                new_va = text_va + back + j + 10 + call_rel
                if new_va == OPERATOR_NEW_VA and 0x10 <= size <= 0x400:
                    sizes[ctor_set[tgt]] = size
                    break
            j += 1
    return sizes


def score_deserialize(binary: LoadedBinary, deser_va: int) -> dict:
    from capstone import Cs, CS_ARCH_X86, CS_MODE_64

    md = Cs(CS_ARCH_X86, CS_MODE_64)
    try:
        blob = binary.read_va(deser_va, 0xC00)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc), "score": 0}
    hits = {
        "off10": 0,
        "off18": 0,
        "off20": 0,
        "calls": 0,
        "callNew": 0,
        "approxBytes": 0,
        "ptrStore18": 0,
        "ptrStore20": 0,
    }
    for insn in md.disasm(blob, deser_va):
        hits["approxBytes"] += insn.size
        o = insn.op_str.replace(" ", "")
        if "+0x10]" in o:
            hits["off10"] += 1
        if "+0x18]" in o:
            hits["off18"] += 1
        if "+0x20]" in o:
            hits["off20"] += 1
        if insn.mnemonic == "mov" and "qwordptr[rbx+0x18]" in o and ",rax" in o:
            hits["ptrStore18"] += 1
        if insn.mnemonic == "mov" and "qwordptr[rbx+0x20]" in o:
            hits["ptrStore20"] += 1
        if insn.mnemonic == "call":
            hits["calls"] += 1
            if insn.op_str.startswith("0x"):
                tgt = int(insn.op_str, 16)
                if tgt == OPERATOR_NEW_VA or abs(tgt - OPERATOR_NEW_VA) < 0x100:
                    hits["callNew"] += 1
        if insn.mnemonic == "ret" and hits["calls"] > 0 and hits["approxBytes"] > 0x40:
            break
        if hits["approxBytes"] > 0xB00:
            break
    score = 0
    if hits["off18"] and hits["off20"]:
        score += 5
    if hits["ptrStore18"] or hits["ptrStore20"]:
        score += 4
    if hits["callNew"]:
        score += 4
    if hits["calls"] >= 5:
        score += 2
    if hits["approxBytes"] >= 0x200:
        score += 2
    if hits["approxBytes"] >= 0x400:
        score += 2
    movementish = bool(
        (hits["callNew"] or hits["ptrStore18"])
        and hits["off18"]
        and hits["off20"]
        and hits["approxBytes"] >= 0x200
    )
    return {"ok": True, "score": score, "movementish": movementish, **hits}


def scan_msvc_packet_types(
    binary: LoadedBinary, rofl_counts: Mapping[int, int]
) -> Tuple[List[dict], dict]:
    stores = find_opcode_stores(binary)
    interest = set(rofl_counts) | {980, 982}
    rows = []
    ctor_by_op: Dict[int, int] = {}
    for op in sorted(interest):
        if op not in stores:
            continue
        rec = recover_msvc_ctor(binary, stores[op])
        if rec.get("opcode") is None:
            rec["opcode"] = op
        ctor_by_op[op] = int(rec["ctorVa"])
        rows.append(rec)
    sizes = discover_object_sizes(binary, ctor_by_op)
    for rec in rows:
        op = int(rec["opcode"])
        rec["objectSize"] = sizes.get(op) or rec.get("fieldExtent")
        if rec.get("deserializeVa"):
            rec["deserScore"] = score_deserialize(binary, int(rec["deserializeVa"]))
        else:
            rec["deserScore"] = {"score": 0}
        rec["blocks"] = int(rofl_counts.get(op, 0))

    covered = [op for op in rofl_counts if op in ctor_by_op]
    coverage = {
        "roflOpcodes": len(rofl_counts),
        "opcodeStores": len(stores),
        "recoveredCtors": len(rows),
        "coveredOpcodes": len(covered),
        "coverageRatio": round(len(covered) / max(1, len(rofl_counts)), 4),
        "sizedFactories": len(sizes),
        "priorArt980": next((r for r in rows if int(r["opcode"]) == 980), None),
        "priorArt982": next((r for r in rows if int(r["opcode"]) == 982), None),
        "constructorIdMatchesKey": sum(
            1 for r in rows if int(r.get("opcode") or -1) in rofl_counts
        ),
    }
    return rows, coverage


def rank_movement(rows: Sequence[Mapping[str, Any]], payload_card: Mapping[int, int]) -> List[dict]:
    ranked = []
    for r in rows:
        op = int(r["opcode"])
        sc = r.get("deserScore") or {}
        sz = r.get("objectSize")
        blocks = int(r.get("blocks") or 0)
        rank = float(sc.get("score") or 0)
        if sz == 48:
            rank += 5
        elif sz in (32, 40, 56, 64):
            rank += 1
        if blocks >= 500:
            rank += 2
        if int(payload_card.get(op, 0)) >= 8:
            rank += 2
        if sc.get("movementish"):
            rank += 5
        if op in (980, 982):
            rank += 1
        ranked.append(
            {
                "opcode": op,
                "objectSize": sz,
                "blocks": blocks,
                "ctorVa": r.get("ctorVa"),
                "vptr": r.get("vptr"),
                "deserializeVa": r.get("deserializeVa"),
                "useVa": r.get("useVa"),
                "deserScore": sc,
                "rankScore": rank,
                "payloadCardinality": int(payload_card.get(op, 0)),
            }
        )
    ranked.sort(key=lambda x: (-x["rankScore"], -x["blocks"]))
    return ranked


class WinX64PacketEmu:
    """Unicorn x86-64 with Windows x64 ABI (RCX, RDX, R8, R9)."""

    def __init__(self, binary: LoadedBinary):
        from unicorn import Uc, UC_ARCH_X86, UC_MODE_64, UC_HOOK_CODE
        from unicorn.x86_const import (
            UC_X86_REG_RAX,
            UC_X86_REG_RBP,
            UC_X86_REG_RBX,
            UC_X86_REG_RCX,
            UC_X86_REG_RDX,
            UC_X86_REG_R8,
            UC_X86_REG_R9,
            UC_X86_REG_RIP,
            UC_X86_REG_RSP,
            UC_X86_REG_R10,
            UC_X86_REG_R11,
        )

        self._UC_HOOK_CODE = UC_HOOK_CODE
        self._regs = {
            "rax": UC_X86_REG_RAX,
            "rbp": UC_X86_REG_RBP,
            "rbx": UC_X86_REG_RBX,
            "rcx": UC_X86_REG_RCX,
            "rdx": UC_X86_REG_RDX,
            "r8": UC_X86_REG_R8,
            "r9": UC_X86_REG_R9,
            "r10": UC_X86_REG_R10,
            "r11": UC_X86_REG_R11,
            "rip": UC_X86_REG_RIP,
            "rsp": UC_X86_REG_RSP,
        }
        self.binary = binary
        self.mu = Uc(UC_ARCH_X86, UC_MODE_64)
        self.heap_ptr = HEAP_BASE + 0x10000
        self.allocs: List[Tuple[int, int]] = []
        self.calls: List[dict] = []
        self.hooked: set = set()
        self._mapped: set = set()
        self._map_segments()
        for base, size in (
            (HEAP_BASE, 0x800000),
            (STACK_BASE, 0x200000),
            (BUF_BASE, 0x200000),
            (SCRATCH_BASE, 0x100000),
        ):
            self._map_rw(base, size)
        self._hook_allocator(OPERATOR_NEW_VA, "operator_new")

    def _map_rw(self, base: int, size: int) -> None:
        page = base & ~0xFFF
        end = (base + size + 0xFFF) & ~0xFFF
        key = (page, end - page)
        if key in self._mapped:
            return
        try:
            self.mu.mem_map(page, end - page)
            self._mapped.add(key)
        except Exception:  # noqa: BLE001
            pass

    def _map_segments(self) -> None:
        for seg in self.binary.segments:
            if seg.filesize <= 0 and seg.vmsize <= 0:
                continue
            page = seg.vmaddr & ~0xFFF
            end = (seg.vmaddr + max(seg.vmsize, seg.filesize) + 0xFFF) & ~0xFFF
            size = end - page
            if size <= 0 or size > 0x40000000:
                continue
            key = (page, size)
            if key not in self._mapped:
                try:
                    self.mu.mem_map(page, size)
                    self._mapped.add(key)
                except Exception:  # noqa: BLE001
                    continue
            try:
                raw = self.binary.data[seg.fileoff : seg.fileoff + seg.filesize]
                if raw:
                    self.mu.mem_write(seg.vmaddr, raw)
            except Exception:  # noqa: BLE001
                pass

    def _reg(self, name: str) -> int:
        return int(self.mu.reg_read(self._regs[name]))

    def _set(self, name: str, val: int) -> None:
        self.mu.reg_write(self._regs[name], int(val) & 0xFFFFFFFFFFFFFFFF)

    def _u64(self, va: int) -> int:
        return struct.unpack("<Q", bytes(self.mu.mem_read(va, 8)))[0]

    def _wu64(self, va: int, val: int) -> None:
        self.mu.mem_write(va, struct.pack("<Q", int(val) & 0xFFFFFFFFFFFFFFFF))

    def _alloc(self, req: int, *, kind: str, pc: int) -> int:
        n = int(req)
        if not (1 <= n <= 0x400000):
            n = 0x40
        n = (n + 0x3F) & ~0x3F
        ptr = self.heap_ptr
        self.heap_ptr += n + 0x40
        try:
            self.mu.mem_write(ptr, b"\x00" * n)
        except Exception:  # noqa: BLE001
            self._map_rw(ptr, n + 0x1000)
            self.mu.mem_write(ptr, b"\x00" * n)
        self.allocs.append((ptr, n))
        return ptr

    def _ret(self, rax: int) -> None:
        rsp = self._reg("rsp")
        ret = self._u64(rsp)
        self._set("rsp", rsp + 8)
        self._set("rax", rax)
        self._set("rip", ret)

    def _hook_allocator(self, va: int, kind: str) -> None:
        if va in self.hooked:
            return
        self.hooked.add(va)

        def on_enter(uc, address, size, user):  # noqa: ANN001, ARG001
            # Windows: RCX = size for operator new
            rcx = self._reg("rcx")
            rdx = self._reg("rdx")
            r8 = self._reg("r8")
            pc = int(address)
            if kind in ("operator_new", "malloc"):
                ptr = self._alloc(rcx, kind=kind, pc=pc)
                self.calls.append(
                    {"pc": hex(pc), "target": hex(va), "kind": kind, "rcx": rcx, "rax": ptr}
                )
                self._ret(ptr)
                return
            if kind == "free":
                self.calls.append(
                    {"pc": hex(pc), "target": hex(va), "kind": kind, "rcx": rcx, "rax": 0}
                )
                self._ret(0)
                return
            if kind == "memcpy":
                n = int(r8)
                if 0 < n <= 0x100000:
                    try:
                        data = bytes(self.mu.mem_read(rdx, n))
                        self.mu.mem_write(rcx, data)
                    except Exception:  # noqa: BLE001
                        pass
                self.calls.append(
                    {
                        "pc": hex(pc),
                        "target": hex(va),
                        "kind": kind,
                        "rcx": rcx,
                        "rdx": rdx,
                        "r8": r8,
                        "rax": rcx,
                    }
                )
                self._ret(rcx)

        self.mu.hook_add(self._UC_HOOK_CODE, on_enter, begin=va, end=va)

    def observe_calls(self, entry: int, max_bytes: int = 0x800) -> None:
        from capstone import Cs, CS_ARCH_X86, CS_MODE_64

        md = Cs(CS_ARCH_X86, CS_MODE_64)
        try:
            blob = self.binary.read_va(entry, max_bytes)
        except Exception:  # noqa: BLE001
            return
        for insn in md.disasm(blob, entry):
            if insn.mnemonic == "call" and insn.op_str.startswith("0x"):
                tgt = int(insn.op_str, 16)
                if tgt == OPERATOR_NEW_VA or abs(tgt - OPERATOR_NEW_VA) < 0x100:
                    self._hook_allocator(tgt, "operator_new")
            if insn.address > entry + max_bytes - 0x10:
                break

    def construct(
        self,
        *,
        ctor_va: int,
        object_size: int,
        expected_opcode: int,
        expected_vptr: int,
    ) -> dict:
        """Allocate via hooked new semantics, call MSVC ctor(this=RCX)."""
        self.allocs.clear()
        self.calls.clear()
        self.observe_calls(ctor_va, 0x80)
        obj = self._alloc(max(object_size, 64), kind="operator_new", pc=0)
        stop = STACK_BASE + 0x800
        self.mu.mem_write(stop, b"\xc3")
        rsp = STACK_BASE + 0x100000 - 0x40
        # Windows home space: shadow space 0x20 below return
        self._wu64(rsp, stop)
        self._set("rsp", rsp - 0x20)
        self._set("rbp", rsp)
        self._set("rcx", obj)  # this
        self._set("rdx", 0)
        self._set("r8", 0)
        self._set("r9", 0)
        self._set("rax", 0)
        err = None
        fail_pc = None
        try:
            self.mu.emu_start(ctor_va, stop, timeout=2_000_000, count=500_000)
        except Exception as exc:  # noqa: BLE001
            err = str(exc)
            try:
                fail_pc = hex(self._reg("rip"))
            except Exception:  # noqa: BLE001
                fail_pc = None
        try:
            prefix = bytes(self.mu.mem_read(obj, max(object_size, 32)))
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"read obj: {exc}", "obj": obj}
        vptr = struct.unpack_from("<Q", prefix, 0)[0]
        opcode = struct.unpack_from("<H", prefix, 8)[0]
        # GS/cookie or epilogue may fault after fields are written; accept when
        # vptr + opcode@+8 already match the MSVC ctor contract.
        fields_ok = vptr == expected_vptr and opcode == (expected_opcode & 0xFFFF)
        ok = fields_ok
        return {
            "ok": ok,
            "obj": obj,
            "vptr": vptr,
            "expectedVptr": expected_vptr,
            "opcode": opcode,
            "expectedOpcode": expected_opcode & 0xFFFF,
            "error": None
            if ok
            else (
                err
                or f"vptr/opcode mismatch got {hex(vptr)}/{opcode} "
                f"want {hex(expected_vptr)}/{expected_opcode}"
                + (f" failPc={fail_pc}" if fail_pc else "")
            ),
            "emuError": err,
            "failurePc": fail_pc,
            "objectPrefixHex": prefix[:0x30].hex(),
            "fabricatedRejected": True,
        }

    def deserialize(self, *, obj: int, deser_va: int, payload: bytes, object_size: int) -> dict:
        self.observe_calls(deser_va, 0x600)
        stop = STACK_BASE + 0x880
        self.mu.mem_write(stop, b"\xc3")
        buf = BUF_BASE + 0x10000
        self.mu.mem_write(buf, payload + b"\x00" * 16)
        cursor_slot = SCRATCH_BASE + 0x2000
        self._wu64(cursor_slot, buf)
        end = buf + len(payload)
        rsp = STACK_BASE + 0x100000 - 0x80
        self._wu64(rsp, stop)
        self._set("rsp", rsp - 0x20)  # shadow space
        self._set("rbp", rsp)
        self._set("rcx", obj)  # this
        self._set("rdx", cursor_slot)  # cursor*
        self._set("r8", end)  # end
        self._set("r9", 0)
        self._set("rax", 0)
        err = None
        fail_pc = None
        try:
            self.mu.emu_start(deser_va, stop, timeout=5_000_000, count=2_000_000)
        except Exception as exc:  # noqa: BLE001
            err = str(exc)
            try:
                fail_pc = hex(self._reg("rip"))
            except Exception:  # noqa: BLE001
                fail_pc = None
        consumed = max(0, self._u64(cursor_slot) - buf)
        ret_al = self._reg("rax") & 0xFF
        after = bytes(self.mu.mem_read(obj, max(object_size, 0x40)))
        buffers, path_hits = self._scan_buffers(after, object_size)
        return {
            "ok": err is None and ret_al != 0,
            "consumed": consumed,
            "retAl": ret_al,
            "error": err,
            "failurePc": fail_pc,
            "objectAfterHex": after[:0x30].hex(),
            "buffers": buffers,
            "pathHits": path_hits,
            "allocs": [{"ptr": hex(p), "size": n} for p, n in self.allocs[:12]],
            "calls": self.calls[:20],
        }

    def _scan_buffers(self, blob: bytes, object_size: int) -> Tuple[List[dict], List[dict]]:
        buffers: List[dict] = []
        path_hits: List[dict] = []
        alloc_map = list(self.allocs)

        def try_buf(ptr: int, length: int, meta: dict) -> None:
            if length < 8 or length > 0x8000:
                return
            if not any(base <= ptr < base + n for base, n in alloc_map):
                return
            try:
                data = bytes(self.mu.mem_read(ptr, length))
            except Exception:  # noqa: BLE001
                return
            buffers.append({**meta, "ptr": hex(ptr), "length": length, "headHex": data[:24].hex()})
            try:
                pp = parse_compressed_path_packet(data)
            except Exception:  # noqa: BLE001
                return
            if pp.full_consume and 50 <= pp.speed <= 2000 and pp.waypoints:
                path_hits.append(
                    {
                        **meta,
                        "entityId": pp.entity_id,
                        "speed": pp.speed,
                        "waypoints": len(pp.waypoints),
                        "x": pp.waypoints[0][0],
                        "z": pp.waypoints[0][1],
                        "length": length,
                    }
                )

        for off in range(0, min(len(blob) - 8, 0x38), 8):
            ptr = struct.unpack_from("<Q", blob, off)[0]
            if off + 16 <= len(blob):
                sz32 = struct.unpack_from("<I", blob, off + 8)[0]
                if 8 <= sz32 <= 0x4000:
                    try_buf(ptr, int(sz32), {"repr": "ptr_u32", "objOff": off})
        for off in range(0, min(len(blob) - 24, 0x30), 8):
            begin = struct.unpack_from("<Q", blob, off)[0]
            end = struct.unpack_from("<Q", blob, off + 8)[0]
            cap = struct.unpack_from("<Q", blob, off + 16)[0]
            if end >= begin and 8 <= (end - begin) <= 0x4000 and (cap >= end or cap == 0):
                try_buf(begin, int(end - begin), {"repr": "begin_end_cap", "objOff": off})
        return buffers, path_hits

    def drive(
        self,
        *,
        ctor_va: int,
        deser_va: int,
        object_size: int,
        expected_opcode: int,
        expected_vptr: int,
        payload: bytes,
    ) -> dict:
        fac = self.construct(
            ctor_va=ctor_va,
            object_size=object_size,
            expected_opcode=expected_opcode,
            expected_vptr=expected_vptr,
        )
        if not fac["ok"]:
            return {"ok": False, "fabricatedRejected": True, "factory": fac, "pathHits": []}
        deser = self.deserialize(
            obj=int(fac["obj"]),
            deser_va=deser_va,
            payload=payload,
            object_size=object_size,
        )
        return {
            "ok": bool(deser.get("ok")),
            "fabricatedRejected": True,
            "factory": fac,
            **deser,
        }


def run_e7b(
    *,
    pe_path: Path,
    rofl: Path,
    oracle_jsonl: Path,
    max_probe_samples: int = 40,
    max_candidates: int = 8,
) -> dict:
    t0 = time.perf_counter()
    if not pe_path.is_file():
        raise FileNotFoundError(pe_path)
    raw_size = pe_path.stat().st_size
    binary = load_binary(pe_path)
    if binary.platform != "windows" or binary.format != "pe64" or binary.arch != "x86_64":
        raise ValueError(f"expected windows pe64 x86_64, got {binary.platform}/{binary.format}/{binary.arch}")
    if binary.sha256 != EXPECTED_SHA256:
        raise ValueError(
            f"SHA256 mismatch: got {binary.sha256}, expected {EXPECTED_SHA256}"
        )
    prov = official_provenance(size=raw_size, sha256=binary.sha256)
    man = research_manifest(
        binary,
        patch="16.14",
        extra={
            "probeVersion": PROBE_VERSION,
            "windowsStatus": "real_pe_validated",
            "official": prov,
            "imageBase": hex(binary.segments[0].vmaddr & ~0xFFFFF),
            "textVa": hex(binary.text_va),
            "textSize": binary.text_size,
            "sectionCount": len(binary.segments),
        },
    )

    counts, samples = enumerate_rofl(rofl)
    payload_card = {op: len({len(s["payload"]) for s in samples.get(op, [])}) for op in counts}
    rows, coverage = scan_msvc_packet_types(binary, counts)
    ranked = rank_movement(rows, payload_card)
    by_op = {int(r["opcode"]): r for r in rows}

    # Candidates: top ranked with blocks, plus prior-art 980
    targets: List[dict] = []
    for r in ranked:
        if r["blocks"] > 0 and r.get("deserializeVa") and r.get("ctorVa") and r.get("vptr"):
            targets.append(r)
        if len(targets) >= max_candidates:
            break
    if 980 in by_op and all(int(t["opcode"]) != 980 for t in targets):
        r980 = next(x for x in ranked if int(x["opcode"]) == 980)
        targets.append({**r980, "note": "prior-art opcode 980"})

    oracle = _load_oracle_positions(oracle_jsonl) if oracle_jsonl.is_file() else []
    emulate_reports = []
    winner = None

    for t in targets:
        op = int(t["opcode"])
        fac_row = by_op[op]
        deser_va = int(fac_row["deserializeVa"])
        ctor_va = int(fac_row["ctorVa"])
        vptr = int(fac_row["vptr"])
        obj_size = int(fac_row.get("objectSize") or 48)
        samp = samples.get(op) or []
        if not samp:
            emulate_reports.append(
                {
                    "opcode": op,
                    "objectSize": obj_size,
                    "skipped": "no_rofl_payloads",
                    "ctorVa": hex(ctor_va),
                    "deserializeVa": hex(deser_va),
                    "deserScore": t.get("deserScore"),
                }
            )
            continue

        n = len(samp)
        idxs = list(range(n)) if n <= max_probe_samples else list(range(0, n, max(1, n // max_probe_samples)))[:max_probe_samples]
        emu = WinX64PacketEmu(binary)
        path_samples = []
        examples = []
        factory_ok = 0
        deser_ok = 0
        first_factory = None
        for idx in idxs:
            s = samp[idx]
            rt = emu.drive(
                ctor_va=ctor_va,
                deser_va=deser_va,
                object_size=obj_size,
                expected_opcode=op,
                expected_vptr=vptr,
                payload=s["payload"],
            )
            if (rt.get("factory") or {}).get("ok"):
                factory_ok += 1
            if first_factory is None:
                first_factory = rt.get("factory")
            if rt.get("ok"):
                deser_ok += 1
            if len(examples) < 3:
                examples.append(
                    {
                        "time": round(float(s["time"]), 3),
                        "payloadLen": len(s["payload"]),
                        "factoryOk": (rt.get("factory") or {}).get("ok"),
                        "ok": rt.get("ok"),
                        "consumed": rt.get("consumed"),
                        "error": rt.get("error") or (rt.get("factory") or {}).get("error"),
                        "pathHits": rt.get("pathHits"),
                        "buffers": (rt.get("buffers") or [])[:3],
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
            "objectSize": obj_size,
            "ctorVa": hex(ctor_va),
            "vptr": hex(vptr),
            "deserializeVa": hex(deser_va),
            "rankScore": t.get("rankScore"),
            "deserScore": t.get("deserScore"),
            "probeSampleCount": len(idxs),
            "factoryOkCount": factory_ok,
            "deserOkCount": deser_ok,
            "factoryValidation": first_factory,
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
            "examples": examples,
        }
        emulate_reports.append(rec)
        if accepted and winner is None:
            winner = rec

    wall_ms = (time.perf_counter() - t0) * 1000
    p980 = coverage.get("priorArt980") or {}
    blocker = None
    if winner is None:
        blocker = {
            "kind": "win_pe_movement_path_not_proven",
            "detail": (
                "MSVC ctor/vtable map on official Windows 16.14 PE covers observed ROFL "
                "opcodes, but constructed Deserialize drives produced no PathPacket buffers "
                "passing oracle gates. Prior-art opcode 980 exists with objectSize="
                f"{p980.get('objectSize')} (not classic 48) and blocks={counts.get(980, 0)}."
            ),
            "topRanked": [
                {
                    "opcode": r["opcode"],
                    "objectSize": r["objectSize"],
                    "blocks": r["blocks"],
                    "rankScore": r["rankScore"],
                    "movementish": (r.get("deserScore") or {}).get("movementish"),
                    "approxBytes": (r.get("deserScore") or {}).get("approxBytes"),
                }
                for r in ranked[:10]
            ],
        }

    return {
        "ok": True,
        "phase": "B-E7b",
        "probeVersion": PROBE_VERSION,
        "provenance": PROVENANCE,
        "official": prov,
        "binaryManifest": man,
        "windowsRealBinaryValidated": True,
        "windowsFormatSupport": "real_pe_validated",
        "constructorCoverage": {
            k: (
                {
                    kk: (hex(vv) if isinstance(vv, int) and vv > 0x10000 else vv)
                    for kk, vv in (coverage[k] or {}).items()
                    if kk != "virt"
                }
                if k.startswith("priorArt") and isinstance(coverage.get(k), dict)
                else coverage.get(k)
            )
            for k in (
                "roflOpcodes",
                "opcodeStores",
                "recoveredCtors",
                "coveredOpcodes",
                "coverageRatio",
                "sizedFactories",
                "constructorIdMatchesKey",
                "priorArt980",
                "priorArt982",
            )
        },
        "movementRanked": [
            {
                **{
                    k: (hex(v) if isinstance(v, int) and k.endswith("Va") or k == "vptr" else v)
                    for k, v in r.items()
                    if k != "deserScore"
                },
                "deserScore": r.get("deserScore"),
            }
            for r in ranked[:25]
        ],
        "emulateReports": emulate_reports,
        "winner": winner,
        "winnerFound": winner is not None,
        "structuralBlocker": blocker,
        "pureBrowserDecoderDerived": False,
        "browserSafe": False,
        "productEligible": False,
        "osNeutralArchitecture": (
            "Offline per-patch manifests from PE (Windows) or Mach-O; one shared "
            "TS/WASM Worker decoder for Windows+Mac; Blob+Worker fallback for unknown "
            "patches. Never ship Riot binary or Unicorn to end users."
        ),
        "endToEndWallMs": round(wall_ms, 3),
        "keep": "keep-research" if winner is not None else "discard",
        "reason": (
            f"E7b movement opcode={winner['opcode']} PathPacket+oracle passed on Windows PE"
            if winner
            else "E7b discard: Windows MSVC ctor map ok, MOVEMENT_PATH PathPacket not proven"
        ),
        "nextSingleVariableHypothesis": (
            "E8: derive pure wire parser/manifest from proven Windows decode"
            if winner
            else "E8: UsePacket/world bind or live-stats field pairing — 980 is size-32 "
            "on 16.14 Windows (not ROFL-X 48); top size-48 types lack byte-buffer alloc"
        ),
    }


def build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--league-binary", type=Path, default=DEFAULT_PE)
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
    ap.add_argument("--max-probe-samples", type=int, default=40)
    ap.add_argument("--max-candidates", type=int, default=8)
    ap.add_argument("--json-out", type=Path, default=None)
    ap.add_argument("--append-speed-run", action="store_true")
    ap.add_argument("--log", type=Path, default=DEFAULT_LOG)
    ap.add_argument("--diff-label", default="phase-b-e7b-win-pe")
    ap.add_argument("--match-code", default="3264361042")
    ap.add_argument("--dry-run", action="store_true")
    return ap


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    report = run_e7b(
        pe_path=args.league_binary,
        rofl=args.rofl,
        oracle_jsonl=args.oracle_jsonl,
        max_probe_samples=int(args.max_probe_samples),
        max_candidates=int(args.max_candidates),
    )
    if args.append_speed_run:
        rec = append_speed_record(
            log=args.log,
            hypothesis="E7b: official Windows 16.14 PE MSVC ctor/Deserialize drive",
            diff_label=args.diff_label,
            keep="discard" if not report.get("winnerFound") else report["keep"],
            reason=report["reason"],
            wall_ms=float(report["endToEndWallMs"]),
            match_code=args.match_code,
            dry_run=args.dry_run,
            extra={
                "phase": "B-E7b",
                "winnerFound": report["winnerFound"],
                "winner": report.get("winner"),
                "constructorCoverage": report.get("constructorCoverage"),
                "structuralBlocker": report.get("structuralBlocker"),
                "official": report.get("official"),
                "windowsRealBinaryValidated": True,
                "pureBrowserDecoderDerived": False,
                "browserSafe": False,
                "endToEndWallMs": report.get("endToEndWallMs"),
                "nextSingleVariableHypothesis": report.get("nextSingleVariableHypothesis"),
                "statsUpdateCount": 0,
                "source": "offline_e7b_win_pe",
                "researchKeep": report.get("keep"),
                "ts": utc_now_iso(),
            },
        )
        report["speedRun"] = rec

    if args.json_out is not None:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        # compact priorArt virt
        disk = dict(report)
        args.json_out.write_text(
            json.dumps(disk, ensure_ascii=False, indent=2, default=str) + "\n",
            encoding="utf-8",
        )
        report["jsonOut"] = str(args.json_out)

    summary = {
        "phase": report["phase"],
        "winnerFound": report["winnerFound"],
        "winner": report.get("winner"),
        "constructorCoverage": report.get("constructorCoverage"),
        "structuralBlocker": report.get("structuralBlocker"),
        "official": report.get("official"),
        "windowsRealBinaryValidated": report.get("windowsRealBinaryValidated"),
        "endToEndWallMs": report["endToEndWallMs"],
        "keep": report["keep"],
        "reason": report["reason"],
        "browserSafe": report["browserSafe"],
        "pureBrowserDecoderDerived": report["pureBrowserDecoderDerived"],
        "productEligible": report["productEligible"],
        "topMovementRanked": (report.get("movementRanked") or [])[:8],
        "nextSingleVariableHypothesis": report.get("nextSingleVariableHypothesis"),
        "jsonOut": report.get("jsonOut"),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
