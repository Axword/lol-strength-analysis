#!/usr/bin/env python3
"""Unicorn x86-64 packet drive with real factory construction (E7a).

E6 invalidity: Deserialize was run on a fabricated zero object (opcode@+8 only).
Obfuscated field init lives in the factory stub / shared ctor tail; skipping it
invalidates PathPacket scans.

This module:
  - Maps Mach-O/PE segments once
  - Calls discovered factory stubs under Mac SysV (rbx = result slot)
  - Hooks evidenced allocators (operator new / resize new)
  - Validates vptr + opcode@+8 before Deserialize
  - Scans ptr+size and begin/end/cap buffer representations
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from rofl2_binary_format import LoadedBinary
from rofl2_movement_emulator_probe import parse_compressed_path_packet

# 16.14 Mac x86_64 allocator entrypoints observed from factory + buffer resize.
OPERATOR_NEW_VAS = (0x10176F500, 0x10176F560)
# Buffer resize used by nested {ptr,size,cap} decode helpers.
BUFFER_RESIZE_VA = 0x101788440

HEAP_BASE = 0x300000000
STACK_BASE = 0x200000000
BUF_BASE = 0x400000000
SCRATCH_BASE = 0x500000000


@dataclass
class AllocRecord:
    ptr: int
    size: int
    kind: str
    pc: int


@dataclass
class CallRecord:
    pc: int
    target: int
    kind: str
    rdi: int
    rsi: int
    rdx: int
    rax_out: Optional[int] = None


@dataclass
class FactoryValidation:
    ok: bool
    obj: int = 0
    objectSize: int = 0
    vptr: int = 0
    expectedVptr: int = 0
    opcode: int = 0
    expectedOpcode: int = 0
    error: Optional[str] = None
    objectPrefixHex: str = ""


@dataclass
class DriveResult:
    ok: bool
    fabricatedRejected: bool = True
    factory: Optional[FactoryValidation] = None
    consumed: int = 0
    pathHits: List[dict] = field(default_factory=list)
    allocs: List[dict] = field(default_factory=list)
    calls: List[dict] = field(default_factory=list)
    failurePc: Optional[str] = None
    error: Optional[str] = None
    objectAfterHex: str = ""
    buffers: List[dict] = field(default_factory=list)


class X86PacketEmu:
    """One emulator instance reused across constructor → Deserialize for a sample."""

    def __init__(self, binary: LoadedBinary):
        from unicorn import Uc, UC_ARCH_X86, UC_MODE_64
        from unicorn import UC_HOOK_CODE
        from unicorn.x86_const import (
            UC_X86_REG_RAX,
            UC_X86_REG_RBP,
            UC_X86_REG_RBX,
            UC_X86_REG_RCX,
            UC_X86_REG_RDI,
            UC_X86_REG_RDX,
            UC_X86_REG_RIP,
            UC_X86_REG_RSI,
            UC_X86_REG_RSP,
            UC_X86_REG_R14,
            UC_X86_REG_R15,
        )

        self._UC_HOOK_CODE = UC_HOOK_CODE
        self._regs = {
            "rax": UC_X86_REG_RAX,
            "rbp": UC_X86_REG_RBP,
            "rbx": UC_X86_REG_RBX,
            "rcx": UC_X86_REG_RCX,
            "rdi": UC_X86_REG_RDI,
            "rdx": UC_X86_REG_RDX,
            "rip": UC_X86_REG_RIP,
            "rsi": UC_X86_REG_RSI,
            "rsp": UC_X86_REG_RSP,
            "r14": UC_X86_REG_R14,
            "r15": UC_X86_REG_R15,
        }
        self.binary = binary
        self.mu = Uc(UC_ARCH_X86, UC_MODE_64)
        self.heap_ptr = HEAP_BASE + 0x10000
        self.allocs: List[AllocRecord] = []
        self.calls: List[CallRecord] = []
        self.hooked_targets: Set[int] = set()
        self._mapped: Set[Tuple[int, int]] = set()
        self._map_segments()
        self._map_rw(HEAP_BASE, 0x800000)
        self._map_rw(STACK_BASE, 0x200000)
        self._map_rw(BUF_BASE, 0x200000)
        self._map_rw(SCRATCH_BASE, 0x100000)
        for va in OPERATOR_NEW_VAS:
            self._hook_allocator(va, kind="operator_new")
        # Discover additional direct calls later via observe_and_hook_calls.

    def _map_rw(self, base: int, size: int) -> None:
        page = base & ~0xFFF
        end = (base + size + 0xFFF) & ~0xFFF
        sz = end - page
        key = (page, sz)
        if key in self._mapped:
            return
        try:
            self.mu.mem_map(page, sz)
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
            if size <= 0 or size > 0x20000000:
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

    def _set_reg(self, name: str, val: int) -> None:
        self.mu.reg_write(self._regs[name], int(val) & 0xFFFFFFFFFFFFFFFF)

    def _read_u64(self, va: int) -> int:
        return struct.unpack("<Q", bytes(self.mu.mem_read(va, 8)))[0]

    def _write_u64(self, va: int, val: int) -> None:
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
        self.allocs.append(AllocRecord(ptr=ptr, size=n, kind=kind, pc=pc))
        return ptr

    def _return_from_call(self, rax: int) -> None:
        rsp = self._reg("rsp")
        ret = self._read_u64(rsp)
        self._set_reg("rsp", rsp + 8)
        self._set_reg("rax", rax)
        self._set_reg("rip", ret)

    def _hook_allocator(self, va: int, *, kind: str) -> None:
        if va in self.hooked_targets:
            return
        self.hooked_targets.add(va)

        def on_enter(uc, address, size, user):  # noqa: ANN001, ARG001
            rdi = self._reg("rdi")
            rsi = self._reg("rsi")
            rdx = self._reg("rdx")
            pc = int(address)
            # calloc(nmemb, size) heuristic
            if kind == "calloc" or (kind == "operator_new" and 1 <= rsi <= 0x10000 and rdi <= 0x10000 and rsi * rdi <= 0x400000 and rdi > 1):
                # Prefer rdi-as-size for operator new; only treat as calloc when explicitly classified.
                pass
            if kind in ("operator_new", "malloc", "realloc_as_new"):
                req = rdi
                if kind == "realloc_as_new":
                    # realloc(ptr, size): rsi is size
                    req = rsi if rsi else rdi
                ptr = self._alloc(req, kind=kind, pc=pc)
                self.calls.append(
                    CallRecord(pc=pc, target=va, kind=kind, rdi=rdi, rsi=rsi, rdx=rdx, rax_out=ptr)
                )
                self._return_from_call(ptr)
                return
            if kind == "calloc":
                req = max(1, rdi) * max(1, rsi)
                ptr = self._alloc(req, kind=kind, pc=pc)
                self.calls.append(
                    CallRecord(pc=pc, target=va, kind=kind, rdi=rdi, rsi=rsi, rdx=rdx, rax_out=ptr)
                )
                self._return_from_call(ptr)
                return
            if kind == "free":
                self.calls.append(
                    CallRecord(pc=pc, target=va, kind=kind, rdi=rdi, rsi=rsi, rdx=rdx, rax_out=0)
                )
                self._return_from_call(0)
                return
            if kind == "memcpy":
                # memcpy(dst, src, n) — SysV: rdi, rsi, rdx
                n = int(rdx)
                if 0 < n <= 0x100000:
                    try:
                        data = bytes(self.mu.mem_read(rsi, n))
                        self.mu.mem_write(rdi, data)
                    except Exception:  # noqa: BLE001
                        pass
                self.calls.append(
                    CallRecord(pc=pc, target=va, kind=kind, rdi=rdi, rsi=rsi, rdx=rdx, rax_out=rdi)
                )
                self._return_from_call(rdi)
                return
            # Unknown: do not stub without evidence.
            self.calls.append(
                CallRecord(pc=pc, target=va, kind="unhandled", rdi=rdi, rsi=rsi, rdx=rdx)
            )

        self.mu.hook_add(self._UC_HOOK_CODE, on_enter, begin=va, end=va)

    def observe_and_hook_calls(self, entry: int, max_bytes: int = 0x800) -> List[int]:
        """Static direct-call scan from entry; hook new-like targets by address proximity."""
        from capstone import Cs, CS_ARCH_X86, CS_MODE_64

        md = Cs(CS_ARCH_X86, CS_MODE_64)
        try:
            blob = self.binary.read_va(entry, max_bytes)
        except Exception:  # noqa: BLE001
            return []
        targets: List[int] = []
        for insn in md.disasm(blob, entry):
            if insn.mnemonic == "call" and insn.op_str.startswith("0x"):
                tgt = int(insn.op_str, 16)
                targets.append(tgt)
                if tgt in OPERATOR_NEW_VAS or abs(tgt - OPERATOR_NEW_VAS[0]) < 0x100:
                    self._hook_allocator(tgt, kind="operator_new")
                elif tgt == BUFFER_RESIZE_VA:
                    # resize calls operator new internally; ensure those are hooked
                    for va in OPERATOR_NEW_VAS:
                        self._hook_allocator(va, kind="operator_new")
            if insn.address > entry + max_bytes - 0x10:
                break
        return targets

    def reset_trace(self) -> None:
        self.allocs.clear()
        self.calls.clear()

    def call_factory(
        self,
        *,
        stub_va: int,
        expected_opcode: int,
        expected_vptr: int,
        object_size: int,
    ) -> FactoryValidation:
        """Enter factory micro-stub with SysV frame matching shared epilogue."""
        self.reset_trace()
        self.observe_and_hook_calls(stub_va, 0x40)
        # Follow one jmp to shared ctor tail for additional calls
        from capstone import Cs, CS_ARCH_X86, CS_MODE_64

        md = Cs(CS_ARCH_X86, CS_MODE_64)
        try:
            for insn in md.disasm(self.binary.read_va(stub_va, 0x40), stub_va):
                if insn.mnemonic == "jmp" and insn.op_str.startswith("0x"):
                    self.observe_and_hook_calls(int(insn.op_str, 16), 0x80)
                    break
                if insn.mnemonic == "ret":
                    break
        except Exception:  # noqa: BLE001
            pass

        stop = STACK_BASE + 0x800
        self.mu.mem_write(stop, b"\xc3")
        result_slot = SCRATCH_BASE + 0x1000
        self._write_u64(result_slot, 0)

        # Epilogue: pop rbx; pop r14; pop rbp; ret
        rsp = STACK_BASE + 0x100000 - 0x40
        self._write_u64(rsp + 0, 0)  # saved rbx
        self._write_u64(rsp + 8, 0)  # saved r14
        self._write_u64(rsp + 16, 0)  # saved rbp
        self._write_u64(rsp + 24, stop)  # return
        self._set_reg("rsp", rsp)
        self._set_reg("rbp", rsp + 32)
        self._set_reg("rbx", result_slot)
        self._set_reg("r14", 0)
        self._set_reg("rax", 0)
        self._set_reg("rdi", 0)
        self._set_reg("rsi", 0)
        self._set_reg("rdx", 0)

        err = None
        fail_pc = None
        try:
            from unicorn import UcError

            self.mu.emu_start(stub_va, stop, timeout=2_000_000, count=500_000)
        except Exception as exc:  # noqa: BLE001
            err = str(exc)
            try:
                fail_pc = hex(self._reg("rip"))
            except Exception:  # noqa: BLE001
                fail_pc = None

        obj = self._read_u64(result_slot)
        if not obj:
            # Some stubs set rax=object before epilogue stores via rbx; try rax
            try:
                rax = self._reg("rax")
                if HEAP_BASE <= rax < self.heap_ptr:
                    obj = rax
                    self._write_u64(result_slot, obj)
            except Exception:  # noqa: BLE001
                pass

        if not obj:
            return FactoryValidation(
                ok=False,
                expectedVptr=expected_vptr,
                expectedOpcode=expected_opcode,
                objectSize=object_size,
                error=err or "factory returned null object",
                objectPrefixHex="",
            )

        try:
            prefix = bytes(self.mu.mem_read(obj, max(object_size, 32)))
        except Exception as exc:  # noqa: BLE001
            return FactoryValidation(
                ok=False,
                obj=obj,
                expectedVptr=expected_vptr,
                expectedOpcode=expected_opcode,
                objectSize=object_size,
                error=f"cannot read object: {exc}",
            )

        vptr = struct.unpack_from("<Q", prefix, 0)[0]
        opcode = struct.unpack_from("<H", prefix, 8)[0]
        ok = (
            err is None
            and vptr == expected_vptr
            and opcode == (expected_opcode & 0xFFFF)
        )
        return FactoryValidation(
            ok=ok,
            obj=obj,
            objectSize=object_size,
            vptr=vptr,
            expectedVptr=expected_vptr,
            opcode=opcode,
            expectedOpcode=expected_opcode & 0xFFFF,
            error=None
            if ok
            else (
                err
                or f"vptr/opcode mismatch got vptr={hex(vptr)} op={opcode} "
                f"want vptr={hex(expected_vptr)} op={expected_opcode}"
                + (f" failPc={fail_pc}" if fail_pc else "")
            ),
            objectPrefixHex=prefix[:0x28].hex(),
        )

    def call_deserialize(
        self,
        *,
        obj: int,
        deser_va: int,
        payload: bytes,
        object_size: int,
    ) -> Tuple[int, Optional[str], Optional[str], int]:
        self.observe_and_hook_calls(deser_va, 0x400)
        # Also scan nested helpers commonly used by 660-style decoders
        for helper in (0x10152B9B0, 0x10152B8A0, 0x10152B780, 0x1018D3150, BUFFER_RESIZE_VA):
            self.observe_and_hook_calls(helper, 0x200)

        stop = STACK_BASE + 0x880
        self.mu.mem_write(stop, b"\xc3")
        buf = BUF_BASE + 0x10000
        self.mu.mem_write(buf, payload + b"\x00" * 16)
        cursor_slot = SCRATCH_BASE + 0x2000
        self._write_u64(cursor_slot, buf)
        end = buf + len(payload)

        rsp = STACK_BASE + 0x100000 - 0x80
        self._write_u64(rsp, stop)
        self._set_reg("rsp", rsp)
        self._set_reg("rbp", rsp)
        self._set_reg("rdi", obj)
        self._set_reg("rsi", cursor_slot)
        self._set_reg("rdx", end)
        self._set_reg("rax", 0)

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

        new_cursor = self._read_u64(cursor_slot)
        consumed = max(0, int(new_cursor) - buf)
        ret_al = self._reg("rax") & 0xFF
        return consumed, err, fail_pc, ret_al

    def scan_buffers(self, obj: int, object_size: int) -> Tuple[List[dict], List[dict]]:
        """Scan object for ptr+size and begin/end/cap; PathPacket-parse allocated ranges."""
        try:
            blob = bytes(self.mu.mem_read(obj, max(object_size, 0x40)))
        except Exception:  # noqa: BLE001
            return [], []

        alloc_map = [(a.ptr, a.size) for a in self.allocs]
        buffers: List[dict] = []
        path_hits: List[dict] = []

        def try_buf(ptr: int, length: int, meta: dict) -> None:
            if length < 8 or length > 0x8000:
                return
            in_alloc = any(base <= ptr < base + n for base, n in alloc_map)
            # Only accept heap-backed buffers from this drive (reject vptr/code false positives).
            if not in_alloc:
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

        # ptr + u32/u64 size
        for off in range(0, min(len(blob) - 8, 0x38), 8):
            ptr = struct.unpack_from("<Q", blob, off)[0]
            if off + 16 <= len(blob):
                sz64 = struct.unpack_from("<Q", blob, off + 8)[0]
                sz32 = struct.unpack_from("<I", blob, off + 8)[0]
                for sz, tag in ((sz32, "ptr_u32"), (sz64 & 0xFFFFFFFF, "ptr_u64low")):
                    if 8 <= sz <= 0x4000:
                        try_buf(ptr, int(sz), {"repr": tag, "objOff": off})

        # begin/end/cap
        for off in range(0, min(len(blob) - 24, 0x30), 8):
            begin = struct.unpack_from("<Q", blob, off)[0]
            end = struct.unpack_from("<Q", blob, off + 8)[0]
            cap = struct.unpack_from("<Q", blob, off + 16)[0]
            if end >= begin and 8 <= (end - begin) <= 0x4000:
                if cap >= end or cap == 0:
                    try_buf(
                        begin,
                        int(end - begin),
                        {"repr": "begin_end_cap", "objOff": off, "cap": hex(cap)},
                    )

        return buffers, path_hits

    def drive_constructed(
        self,
        *,
        stub_va: int,
        expected_opcode: int,
        expected_vptr: int,
        object_size: int,
        deser_va: int,
        payload: bytes,
    ) -> DriveResult:
        """Factory construct then Deserialize. Never accepts fabricated objects."""
        fac = self.call_factory(
            stub_va=stub_va,
            expected_opcode=expected_opcode,
            expected_vptr=expected_vptr,
            object_size=object_size,
        )
        if not fac.ok:
            return DriveResult(
                ok=False,
                fabricatedRejected=True,
                factory=fac,
                error=fac.error,
                allocs=[{"ptr": hex(a.ptr), "size": a.size, "kind": a.kind} for a in self.allocs[:12]],
                calls=[
                    {
                        "pc": hex(c.pc),
                        "target": hex(c.target),
                        "kind": c.kind,
                        "rdi": c.rdi,
                        "rax": c.rax_out,
                    }
                    for c in self.calls[:20]
                ],
            )

        consumed, err, fail_pc, ret_al = self.call_deserialize(
            obj=fac.obj,
            deser_va=deser_va,
            payload=payload,
            object_size=object_size,
        )
        buffers, path_hits = self.scan_buffers(fac.obj, object_size)
        try:
            after = bytes(self.mu.mem_read(fac.obj, max(object_size, 0x28))).hex()
        except Exception:  # noqa: BLE001
            after = ""

        deser_ok = err is None and ret_al != 0
        return DriveResult(
            ok=deser_ok and (consumed > 0 or bool(path_hits)),
            fabricatedRejected=True,
            factory=fac,
            consumed=consumed,
            pathHits=path_hits,
            buffers=buffers,
            allocs=[{"ptr": hex(a.ptr), "size": a.size, "kind": a.kind} for a in self.allocs[:12]],
            calls=[
                {
                    "pc": hex(c.pc),
                    "target": hex(c.target),
                    "kind": c.kind,
                    "rdi": c.rdi,
                    "rax": c.rax_out,
                }
                for c in self.calls[:24]
            ],
            failurePc=fail_pc,
            error=err if err else (None if deser_ok else f"deserialize returned al=0 consumed={consumed}"),
            objectAfterHex=after,
        )


def recover_vptr_from_stub(binary: LoadedBinary, stub_va: int) -> Optional[int]:
    """Recover Itanium vptr from factory stub without scanning into the next stub."""
    from capstone import Cs, CS_ARCH_X86, CS_MODE_64
    import re

    md = Cs(CS_ARCH_X86, CS_MODE_64)
    try:
        blob = binary.read_va(stub_va, 0x60)
    except Exception:  # noqa: BLE001
        return None

    lea_target = None
    saw_add10 = False
    pending_jmp = None

    def consider(insn_blob: bytes, base: int, depth: int = 0) -> Optional[int]:
        nonlocal lea_target, saw_add10
        for insn in md.disasm(insn_blob, base):
            if insn.mnemonic == "lea" and "rip" in insn.op_str and "rcx" in insn.op_str:
                m = re.search(r"\[rip\s*([+-]\s*0x[0-9a-f]+)\]", insn.op_str)
                if m:
                    disp = int(m.group(1).replace(" ", ""), 16)
                    lea_target = insn.address + insn.size + disp
            if insn.mnemonic == "add" and insn.op_str.replace(" ", "") in (
                "rcx,0x10",
                "rcx,10h",
            ):
                saw_add10 = True
            if (
                insn.mnemonic == "mov"
                and "qword ptr [rax]" in insn.op_str
                and insn.op_str.endswith(", rcx")
                and lea_target is not None
            ):
                # Itanium: lea targets typeinfo; stored vptr is lea+0x10 after add rcx,0x10.
                return lea_target + 0x10
            if insn.mnemonic == "jmp" and insn.op_str.startswith("0x") and depth == 0:
                tgt = int(insn.op_str, 16)
                try:
                    return consider(binary.read_va(tgt, 0x40), tgt, depth=1)
                except Exception:  # noqa: BLE001
                    break
            if insn.mnemonic == "ret":
                break
            # Stop before next factory micro-stub
            if (
                depth == 0
                and insn.address > stub_va
                and insn.mnemonic == "mov"
                and insn.op_str.startswith("edi,")
            ):
                break
        if lea_target is not None:
            return lea_target + 0x10
        return None

    return consider(blob, stub_va, 0)
