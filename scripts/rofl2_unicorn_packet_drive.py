#!/usr/bin/env python3
"""
Unicorn packet drive for 16.14 arm64 LeagueofLegends.

Pipeline driven here:
  1. Chunk body → block framing (0x10076bc94) — flag/time/size/channel/param
  2. Reconstructed block buffer → read_packet_type + Packet::Packet + Deserialize
  3. (next) Replication field getters → maknee events[] → mapper

Fail-closed: never invents HP. Type 107 is the leading Replication candidate
(largest payloads; many HP-range floats after Deserialize) but mHP/mMaxHP
getters still require CharacterIntermediate binding.

Pinned 16.14 entrypoints (arm64 slice):
  Packet::Packet          0x101167a8c   (w0=type, x8=Packet**)
  read_packet_type        0x101775aec   (x0=&cursor, x1=end, x2=&u16)
  block_extract           0x10076bc94   (buf, &index, out, &chan, &param)
  type_count global       0x102422738   (set to 0x55d → threshold 251)
  allocator               0x10162ecc8 / 0x10162eb4c

Example:
  python3 scripts/rofl2_unicorn_packet_drive.py \\
    "$HOME/Documents/League of Legends/Replays/BR1-3264383283.rofl" \\
    --json-out docs/rofl-research/unicorn-packet-drive-BR1-3264383283.json
"""
from __future__ import annotations

import argparse
import json
import struct
import sys
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rofl2_accessor_spike as spike  # noqa: E402
from rofl2_probe import extract_segments, parse_rofl2  # noqa: E402

DEFAULT_LEAGUE_BINARY = spike.DEFAULT_UNIVERSAL_BINARY

PACKET_FACTORY = 0x101167A8C
READ_PACKET_TYPE = 0x101775AEC
BLOCK_EXTRACT = 0x10076BC94
TYPE_COUNT_GLOBAL = 0x102422738
ALLOCATOR = 0x10162ECC8
ALLOC_SIZE = 0x10162EB4C
FREE_FN = 0x10162EBAC
MEMSET_FN = 0x101F31594
MEMCPY_FN = 0x101F31B4C
# Runtime init uses max(patchExtra, 0x8f) + 0x4ce → 0x55d when patchExtra≤0x8f
TYPE_COUNT_VALUE = 0x55D
# Relative time scale used by block_extract (movk 0x3a83126f → ~0.001s)
BLOCK_TIME_SCALE = struct.unpack("<f", struct.pack("<I", 0x3A83126F))[0]
# Leading Replication candidate on 16.14 BR1 mid-chunk streams
REPLICATION_TYPE_CANDIDATE = 107

# Arena layout inside Unicorn (well above typical __TEXT/__DATA)
ARENA_BASE = 0x300000000
HEAP_BASE = ARENA_BASE + 0x01000000
HEAP_SIZE = 0x04000000
STACK_BASE = ARENA_BASE + 0x08000000
STACK_SIZE = 0x00100000
BUF_BASE = ARENA_BASE + 0x0A000000
BUF_SIZE = 0x02000000
SCRATCH = ARENA_BASE + 0x0C000000


class BumpHeap:
    def __init__(self, base: int = HEAP_BASE, size: int = HEAP_SIZE) -> None:
        self.base = base
        self.end = base + size
        self.ptr = base + 0x1000
        self.allocs: List[Tuple[int, int]] = []

    def alloc(self, n: int) -> int:
        n = int(n)
        if n < 0 or n > 0x1000000:
            raise MemoryError(f"unicorn heap alloc size unreasonable: {n}")
        n = max(n, 1)
        n = (n + 0xF) & ~0xF
        if self.ptr + n > self.end:
            raise MemoryError(f"unicorn heap exhausted need={n}")
        p = self.ptr
        self.ptr += n
        self.allocs.append((p, n))
        return p


def _va_to_off(segments, va: int) -> Optional[int]:
    for _name, vmaddr, vmsize, fileoff, filesize in segments:
        if vmaddr <= va < vmaddr + vmsize:
            rel = va - vmaddr
            if rel < filesize:
                return fileoff + rel
    return None


def type_threshold(type_count: int = TYPE_COUNT_VALUE) -> int:
    w9 = (type_count - 2) & 0xFFFFFFFF
    quot = (w9 * 0x80808081) >> 39
    return (256 - quot) & 0xFF


def read_packet_type_py(
    buf: bytes, i: int, end: int, *, threshold: int
) -> Tuple[Optional[int], int]:
    """Mirror of READ_PACKET_TYPE at 0x101775aec."""
    if i >= end:
        return None, i
    first = buf[i]
    i += 1
    if first < threshold:
        return int(first), i
    if i >= end:
        return None, i
    second = buf[i]
    i += 1
    typ = threshold + (((first - threshold) & 0xFF) << 8) + second
    return typ & 0xFFFF, i


def extract_blocks_py(
    stream: bytes,
    *,
    start: int = 0,
    max_blocks: int = 10_000,
) -> List[Dict[str, Any]]:
    """Pure-Python mirror of block_extract wire framing (0x10076bc94).

    Chunk bodies start at offset 0 with the first flag byte (the old "marker"
    byte). Each block is:
      flag:u8
      time: absolute f32 if flag>=0 else relative u8 * ~0.001s
      size: u8 if flag&0x10 else u32
      channel:u16 unless flag&0x40 (reuse prior)
      param: u32 absolute unless flag&0x20 (signed u8 delta)
      payload[size]
    Channel is the packet type once the client reconstructs the buffer.
    """
    i = start
    time_f = 0.0
    channel = 0
    param = 0
    blocks: List[Dict[str, Any]] = []
    while i < len(stream) and len(blocks) < max_blocks:
        flag_u = stream[i]
        flag = struct.unpack_from("<b", stream, i)[0]
        i += 1
        nibble = flag_u & 0x0F
        if flag < 0:
            if i >= len(stream):
                break
            time_f = time_f + stream[i] * BLOCK_TIME_SCALE
            i += 1
        else:
            if i + 4 > len(stream):
                break
            time_f = struct.unpack_from("<f", stream, i)[0]
            i += 4
        if flag_u & 0x10:
            if i >= len(stream):
                break
            size = stream[i]
            i += 1
        else:
            if i + 4 > len(stream):
                break
            size = struct.unpack_from("<I", stream, i)[0]
            i += 4
        if not (flag_u & 0x40):
            if i + 2 > len(stream):
                break
            channel = struct.unpack_from("<H", stream, i)[0]
            i += 2
        if flag_u & 0x20:
            if i >= len(stream):
                break
            param = (param + struct.unpack_from("<b", stream, i)[0]) & 0xFFFFFFFF
            i += 1
        else:
            if i + 4 > len(stream):
                break
            param = struct.unpack_from("<I", stream, i)[0]
            i += 4
        if size < 0 or i + size > len(stream):
            break
        payload = stream[i : i + size]
        i += size
        blocks.append(
            {
                "time": time_f,
                "nibble": nibble,
                "flag": flag_u,
                "channel": channel,
                "param": param,
                "wireSize": size,
                "payload": payload,
                "nextIndex": i,
            }
        )
    return blocks


def map_binary(mu: Any, data: bytes, segments) -> Dict[str, Any]:
    mapped = spike.map_loadable_segments(mu, data)
    # Ensure BSS-ish tails for __DATA beyond filesize are readable
    for name, vmaddr, vmsize, fileoff, filesize in segments:
        if not name.startswith("__DATA"):
            continue
        if vmsize <= filesize:
            continue
        base = spike._align_page(vmaddr + filesize)
        end = spike._align_page(vmaddr + vmsize + 0xFFF)
        size = end - base
        if size <= 0:
            continue
        try:
            mu.mem_map(base, size)
        except Exception:  # noqa: BLE001
            pass
    return mapped


def install_allocator_hook(mu: Any, heap: BumpHeap) -> None:
    from unicorn import UC_HOOK_CODE
    from unicorn.arm64_const import UC_ARM64_REG_LR, UC_ARM64_REG_PC, UC_ARM64_REG_X0

    def _on_alloc(uc, address, size, user_data):  # noqa: ANN001
        n = uc.reg_read(UC_ARM64_REG_X0)
        ptr = heap.alloc(n)
        # Zero the block
        uc.mem_write(ptr, b"\x00" * ((n + 0xF) & ~0xF))
        uc.reg_write(UC_ARM64_REG_X0, ptr)
        # Skip the hooked insn and return to LR
        lr = uc.reg_read(UC_ARM64_REG_LR)
        uc.reg_write(UC_ARM64_REG_PC, lr)

    mu.hook_add(UC_HOOK_CODE, _on_alloc, begin=ALLOCATOR, end=ALLOCATOR + 4)


def install_unmapped_stub(mu: Any) -> List[str]:
    """Map sparse pages on demand for data/code fetches outside the slice."""
    from unicorn import UC_HOOK_MEM_UNMAPPED, UC_MEM_FETCH_UNMAPPED, UC_MEM_READ_UNMAPPED, UC_MEM_WRITE_UNMAPPED

    faults: List[str] = []

    def _on_unmapped(uc, access, address, size, value, user_data):  # noqa: ANN001
        if address < 0x10000:
            faults.append(f"null-ish fault addr={hex(address)} access={access}")
            return False
        page = address & ~0xFFF
        try:
            uc.mem_map(page, 0x1000)
            uc.mem_write(page, b"\x00" * 0x1000)
            faults.append(f"auto-map {hex(page)} access={access}")
            return True
        except Exception as e:  # noqa: BLE001
            faults.append(f"fail-map {hex(page)}: {e}")
            return False

    mu.hook_add(UC_HOOK_MEM_UNMAPPED, _on_unmapped)
    return faults


def unicorn_call(
    mu: Any,
    *,
    fn: int,
    x0: int = 0,
    x1: int = 0,
    x2: int = 0,
    x3: int = 0,
    x4: int = 0,
    x8: int = 0,
    timeout_us: int = 2_000_000,
    max_insns: int = 5_000_000,
) -> Dict[str, Any]:
    from unicorn import UcError
    from unicorn.arm64_const import (
        UC_ARM64_REG_LR,
        UC_ARM64_REG_PC,
        UC_ARM64_REG_SP,
        UC_ARM64_REG_X0,
        UC_ARM64_REG_X1,
        UC_ARM64_REG_X2,
        UC_ARM64_REG_X3,
        UC_ARM64_REG_X4,
        UC_ARM64_REG_X8,
    )

    # Return sink: emu_start stops when PC hits STOP (instruction not executed).
    stop = SCRATCH + 0x100
    mu.mem_write(stop, struct.pack("<I", 0xD503201F))  # nop
    sp = STACK_BASE + STACK_SIZE - 0x1000
    mu.reg_write(UC_ARM64_REG_SP, sp)
    mu.reg_write(UC_ARM64_REG_LR, stop)
    mu.reg_write(UC_ARM64_REG_X0, x0)
    mu.reg_write(UC_ARM64_REG_X1, x1)
    mu.reg_write(UC_ARM64_REG_X2, x2)
    mu.reg_write(UC_ARM64_REG_X3, x3)
    mu.reg_write(UC_ARM64_REG_X4, x4)
    mu.reg_write(UC_ARM64_REG_X8, x8)
    mu.reg_write(UC_ARM64_REG_PC, fn)
    err = None
    try:
        mu.emu_start(fn, stop, timeout=timeout_us, count=max_insns)
    except UcError as e:
        err = str(e)
    pc = mu.reg_read(UC_ARM64_REG_PC)
    return {
        "x0": mu.reg_read(UC_ARM64_REG_X0),
        "pc": pc,
        "error": err,
        "returned": pc == stop and err is None,
    }


def install_block_runtime_hooks(mu: Any, heap: BumpHeap) -> None:
    """Hook alloc/free/memcpy/memset used by block_extract reconstruction."""
    from unicorn import UC_HOOK_CODE
    from unicorn.arm64_const import (
        UC_ARM64_REG_LR,
        UC_ARM64_REG_PC,
        UC_ARM64_REG_X0,
        UC_ARM64_REG_X1,
        UC_ARM64_REG_X2,
    )

    def on_alloc(uc: Any, address: int, size: int, user: Any) -> None:
        req = uc.reg_read(UC_ARM64_REG_X0)
        if req <= 0 or req > 0x1000000:
            uc.reg_write(UC_ARM64_REG_X0, 0)
        else:
            p = heap.alloc(int(req))
            uc.mem_write(p, b"\x00" * int(req))
            uc.reg_write(UC_ARM64_REG_X0, p)
        uc.reg_write(UC_ARM64_REG_PC, uc.reg_read(UC_ARM64_REG_LR))

    def on_free(uc: Any, address: int, size: int, user: Any) -> None:
        uc.reg_write(UC_ARM64_REG_PC, uc.reg_read(UC_ARM64_REG_LR))

    def on_memset(uc: Any, address: int, size: int, user: Any) -> None:
        # Call sites used as bzero(dst, len): x0=dst, x1=len
        dst = uc.reg_read(UC_ARM64_REG_X0)
        ln = uc.reg_read(UC_ARM64_REG_X1)
        if 0 < ln < 0x1000000:
            try:
                uc.mem_write(dst, b"\x00" * int(ln))
            except Exception:  # noqa: BLE001
                pass
        uc.reg_write(UC_ARM64_REG_PC, uc.reg_read(UC_ARM64_REG_LR))

    def on_memcpy(uc: Any, address: int, size: int, user: Any) -> None:
        dst = uc.reg_read(UC_ARM64_REG_X0)
        src = uc.reg_read(UC_ARM64_REG_X1)
        n = uc.reg_read(UC_ARM64_REG_X2)
        if 0 < n < 0x1000000:
            try:
                uc.mem_write(dst, bytes(uc.mem_read(src, n)))
            except Exception:  # noqa: BLE001
                pass
        uc.reg_write(UC_ARM64_REG_X0, dst)
        uc.reg_write(UC_ARM64_REG_PC, uc.reg_read(UC_ARM64_REG_LR))

    for addr, cb in (
        (ALLOCATOR, on_alloc),
        (ALLOC_SIZE, on_alloc),
        (FREE_FN, on_free),
        (MEMSET_FN, on_memset),
        (MEMCPY_FN, on_memcpy),
    ):
        mu.hook_add(UC_HOOK_CODE, cb, begin=addr, end=addr)


def extract_blocks_unicorn(
    mu: Any,
    *,
    stream: bytes,
    buf_va: int = BUF_BASE,
    max_blocks: int = 512,
) -> Dict[str, Any]:
    """Drive 0x10076bc94 repeatedly; return reconstructed packet buffers."""
    mu.mem_write(buf_va, stream)
    # Keep scratch layout clear of create_packet (SCRATCH+0x200) / deserialize (SCRATCH+0x300).
    in_obj = SCRATCH + 0x800
    index_va = SCRATCH + 0x840
    out_va = SCRATCH + 0x880
    chan_va = SCRATCH + 0x8C0
    param_va = SCRATCH + 0x8D0
    mu.mem_write(in_obj, struct.pack("<QI", buf_va, len(stream)) + b"\x00" * 4)
    mu.mem_write(index_va, struct.pack("<I", 0))
    mu.mem_write(chan_va, struct.pack("<H", 0))
    mu.mem_write(param_va, struct.pack("<I", 0))
    saved_time = b"\x00" * 4
    blocks: List[Dict[str, Any]] = []
    stop_reason = None
    for _ in range(max_blocks):
        # Preserve prior time float; zero the rest of OUT (fresh dynbuf each packet).
        mu.mem_write(out_va, saved_time + b"\x00" * 0x1C)
        call = unicorn_call(
            mu,
            fn=BLOCK_EXTRACT,
            x0=in_obj,
            x1=index_va,
            x2=out_va,
            x3=chan_va,
            x4=param_va,
            timeout_us=5_000_000,
            max_insns=8_000_000,
        )
        out = bytes(mu.mem_read(out_va, 0x20))
        saved_time = out[:4]
        success = out[0x18]
        idx = struct.unpack("<I", bytes(mu.mem_read(index_va, 4)))[0]
        if not success:
            stop_reason = {
                "index": idx,
                "callError": call.get("error"),
                "returned": call.get("returned"),
            }
            break
        ptr, size, _cap = struct.unpack_from("<QII", out, 8)
        payload = b""
        if ptr and 0 < size < 0x100000:
            try:
                payload = bytes(mu.mem_read(ptr, size))
            except Exception as e:  # noqa: BLE001
                stop_reason = {"index": idx, "payloadError": str(e)}
                break
        blocks.append(
            {
                "time": struct.unpack_from("<f", out, 0)[0],
                "channel": struct.unpack("<H", bytes(mu.mem_read(chan_va, 2)))[0],
                "param": struct.unpack("<I", bytes(mu.mem_read(param_va, 4)))[0],
                "size": size,
                "payload": payload,
                "indexAfter": idx,
            }
        )
        if idx >= len(stream):
            stop_reason = {"index": idx, "eof": True}
            break
    return {
        "blocks": blocks,
        "count": len(blocks),
        "stop": stop_reason,
        "timeStart": blocks[0]["time"] if blocks else None,
        "timeEnd": blocks[-1]["time"] if blocks else None,
    }


def create_packet(mu: Any, heap: BumpHeap, packet_type: int) -> Dict[str, Any]:
    out_slot = SCRATCH + 0x200
    mu.mem_write(out_slot, struct.pack("<Q", 0))
    before = heap.ptr
    result = unicorn_call(mu, fn=PACKET_FACTORY, x0=packet_type & 0xFFFF, x8=out_slot)
    raw = mu.mem_read(out_slot, 8)
    pkt = struct.unpack("<Q", bytes(raw))[0]
    info: Dict[str, Any] = {
        "type": packet_type,
        "packet": pkt,
        "call": result,
        "heapDelta": heap.ptr - before,
    }
    if pkt:
        try:
            stored = struct.unpack("<H", bytes(mu.mem_read(pkt + 8, 2)))[0]
            vtable = struct.unpack("<Q", bytes(mu.mem_read(pkt, 8)))[0]
            info["storedType"] = stored
            info["vtable"] = vtable
            if vtable:
                deser = struct.unpack("<Q", bytes(mu.mem_read(vtable + 8, 8)))[0]
                info["deserialize"] = deser
        except Exception as e:  # noqa: BLE001
            info["readError"] = str(e)
    return info


def deserialize_packet(
    mu: Any,
    *,
    packet: int,
    deserialize_fn: int,
    buf_va: int,
    buf_len: int,
    cursor_off: int = 0,
) -> Dict[str, Any]:
    cursor_slot = SCRATCH + 0x300
    start = buf_va + cursor_off
    end = buf_va + buf_len
    mu.mem_write(cursor_slot, struct.pack("<Q", start))
    result = unicorn_call(
        mu,
        fn=deserialize_fn,
        x0=packet,
        x1=cursor_slot,
        x2=end,
        timeout_us=5_000_000,
    )
    new_cursor = struct.unpack("<Q", bytes(mu.mem_read(cursor_slot, 8)))[0]
    consumed = max(0, int(new_cursor) - int(start))
    returned = bool((result or {}).get("returned"))
    ok = returned and bool(result.get("x0")) and consumed > 0
    return {
        "ok": ok,
        "x0": result.get("x0"),
        "cursorBefore": start,
        "cursorAfter": new_cursor,
        "consumed": consumed,
        "call": result,
    }


def walk_chunk_packets(
    mu: Any,
    heap: BumpHeap,
    body: bytes,
    *,
    buf_va: int,
    start_off: int,
    threshold: int,
    max_packets: int = 64,
) -> Dict[str, Any]:
    mu.mem_write(buf_va, body)
    end = len(body)
    i = start_off
    rows: List[Dict[str, Any]] = []
    types = Counter()
    while i < end and len(rows) < max_packets:
        typ, ni = read_packet_type_py(body, i, end, threshold=threshold)
        if typ is None:
            break
        if typ > 0x4CD:
            rows.append(
                {
                    "offset": i,
                    "type": typ,
                    "status": "type_out_of_range",
                }
            )
            break
        types[typ] += 1
        created = create_packet(mu, heap, typ)
        pkt = created.get("packet") or 0
        deser = created.get("deserialize") or 0
        row: Dict[str, Any] = {
            "offset": i,
            "type": typ,
            "typeBytes": ni - i,
            "create": {
                "packet": pkt,
                "storedType": created.get("storedType"),
                "vtable": created.get("vtable"),
                "deserialize": deser,
                "callError": (created.get("call") or {}).get("error"),
            },
        }
        if not pkt or not deser:
            row["status"] = "create_failed"
            rows.append(row)
            break
        # Cursor starts AFTER the type bytes (factory path reads type separately)
        des = deserialize_packet(
            mu,
            packet=pkt,
            deserialize_fn=deser,
            buf_va=buf_va,
            buf_len=end,
            cursor_off=ni,
        )
        row["deserialize"] = {
            "ok": des["ok"],
            "consumed": des["consumed"],
            "cursorAfter": des["cursorAfter"],
            "x0": des["x0"],
            "error": (des.get("call") or {}).get("error"),
        }
        if not des["ok"] or des["consumed"] <= 0:
            row["status"] = "deserialize_failed"
            rows.append(row)
            break
        row["status"] = "ok"
        rows.append(row)
        # Advance past type + payload
        i = ni + int(des["consumed"])
    return {
        "startOff": start_off,
        "packets": rows,
        "okCount": sum(1 for r in rows if r.get("status") == "ok"),
        "typeHistogram": dict(types.most_common(20)),
        "stoppedAt": i,
        "remaining": max(0, end - i),
    }


def drive_rofl(
    *,
    rofl: Path,
    league_binary: Path = DEFAULT_LEAGUE_BINARY,
    work_dir: Optional[Path] = None,
    max_packets: int = 48,
    max_blocks: int = 512,
    chunk_index: Optional[int] = None,
) -> Dict[str, Any]:
    if not league_binary.is_file():
        return {
            "ok": False,
            "decryptStatus": "blocked_need_league_binary",
            "error": f"missing {league_binary}",
            "replication": [],
        }
    if not rofl.is_file():
        return {
            "ok": False,
            "decryptStatus": "blocked_need_rofl",
            "error": f"missing {rofl}",
            "replication": [],
        }

    try:
        from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM
    except ImportError as e:
        return {
            "ok": False,
            "decryptStatus": "blocked_unicorn_missing",
            "error": str(e),
            "replication": [],
        }

    if work_dir is None:
        work_dir = Path(tempfile.mkdtemp(prefix="lol-unicorn-pkt-"))
    work_dir.mkdir(parents=True, exist_ok=True)
    arm64_path = work_dir / "LeagueofLegends.arm64"
    spike.thin_arm64(league_binary, arm64_path)
    data = arm64_path.read_bytes()
    segments = spike._parse_segments(data)

    info = parse_rofl2(rofl)
    extracted = extract_segments(info["payload"])
    chunks = [s for s in extracted["segments"] if s.get("type") == 1]
    if not chunks:
        return {
            "ok": False,
            "decryptStatus": "blocked_no_chunks",
            "replication": [],
        }

    # Prefer a mid-game chunk unless specified
    if chunk_index is None:
        chunk_index = min(len(chunks) - 1, max(0, len(chunks) // 2))
    chunk = chunks[chunk_index]
    body: bytes = chunk["bytes"]
    time_s = struct.unpack_from("<f", body, 1)[0] if len(body) >= 5 else None

    # Pure-Python framing sanity (no Unicorn) — chunk starts at offset 0.
    py_blocks = extract_blocks_py(body, max_blocks=min(max_blocks, 2000))
    py_channels = Counter(b["channel"] for b in py_blocks)

    mu = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
    mapped = map_binary(mu, data, segments)
    for base, size in (
        (ARENA_BASE, 0x00100000),
        (HEAP_BASE, HEAP_SIZE),
        (STACK_BASE, STACK_SIZE),
        (BUF_BASE, BUF_SIZE),
        (SCRATCH, 0x00100000),
    ):
        try:
            mu.mem_map(base, size)
        except Exception:  # noqa: BLE001
            pass

    heap = BumpHeap()
    # Covers Packet::Packet malloc + block_extract realloc/memcpy/memset.
    install_block_runtime_hooks(mu, heap)
    unmapped_faults = install_unmapped_stub(mu)

    try:
        mu.mem_write(TYPE_COUNT_GLOBAL, struct.pack("<I", TYPE_COUNT_VALUE))
    except Exception as e:  # noqa: BLE001
        return {
            "ok": False,
            "decryptStatus": "blocked_type_global_unmap",
            "error": str(e),
            "replication": [],
        }

    thr = type_threshold(TYPE_COUNT_VALUE)

    create_smoke = []
    for t in (2, 3, 11, 196, REPLICATION_TYPE_CANDIDATE):
        create_smoke.append(create_packet(mu, heap, t))
    creates_ok = sum(1 for c in create_smoke if c.get("packet") and c.get("deserialize"))

    extracted_u = extract_blocks_unicorn(mu, stream=body, max_blocks=max_blocks)
    blocks = extracted_u["blocks"]

    # Deserialize reconstructed payloads (extract-all first, then create/deser).
    deser_rows: List[Dict[str, Any]] = []
    type_hist = Counter()
    deser_ok = 0
    repl_candidates = 0
    for b in blocks[:max_packets]:
        pay = b.get("payload") or b""
        if not pay:
            continue
        typ, ni = read_packet_type_py(pay, 0, len(pay), threshold=thr)
        row: Dict[str, Any] = {
            "time": b.get("time"),
            "channel": b.get("channel"),
            "param": b.get("param"),
            "size": b.get("size"),
            "type": typ,
        }
        if typ is None or typ > 0x4CD:
            row["status"] = "type_bad"
            deser_rows.append(row)
            continue
        created = create_packet(mu, heap, typ)
        deser = created.get("deserialize") or 0
        pkt = created.get("packet") or 0
        if not pkt or not deser:
            row["status"] = "create_failed"
            deser_rows.append(row)
            continue
        pva = BUF_BASE + 0x01800000
        mu.mem_write(pva, pay)
        des = deserialize_packet(
            mu,
            packet=pkt,
            deserialize_fn=deser,
            buf_va=pva,
            buf_len=len(pay),
            cursor_off=ni,
        )
        row["deserialize"] = {
            "ok": des["ok"],
            "consumed": des["consumed"],
            "x0": des["x0"],
            "error": (des.get("call") or {}).get("error"),
        }
        if des["ok"]:
            row["status"] = "ok"
            deser_ok += 1
            type_hist[typ] += 1
            if typ == REPLICATION_TYPE_CANDIDATE:
                repl_candidates += 1
        else:
            row["status"] = "deserialize_failed"
        deser_rows.append(row)

    # Channel match between Python wire walker and Unicorn channel field
    n_match = min(32, len(py_blocks), len(blocks))
    channel_match = n_match > 0 and all(
        py_blocks[i]["channel"] == blocks[i]["channel"] for i in range(n_match)
    )

    status = "packet_factory_driven_need_stream_sync"
    if creates_ok >= 3 and extracted_u["count"] == 0:
        status = "packet_factory_driven_need_stream_sync"
    if extracted_u["count"] > 0:
        status = "block_framing_synced_need_replication_fields"
    if deser_ok > 0:
        status = "block_framing_synced_packets_deserialized"
    if deser_ok >= 8 and repl_candidates > 0:
        status = "replication_candidate_deserialized_need_field_getters"

    return {
        "ok": False,  # no Replication HP yet — fail-closed for product HP
        "decryptStatus": status,
        "arch": "arm64",
        "rofl": str(rofl),
        "gameVersion": (info.get("meta") or {}).get("gameVersion")
        or info.get("version"),
        "chunk": {
            "index": chunk_index,
            "id_a": chunk.get("id_a"),
            "time_s": time_s,
            "size": len(body),
        },
        "typeCountGlobal": TYPE_COUNT_VALUE,
        "typeThreshold": thr,
        "segmentMap": {"segmentCount": mapped.get("segmentCount")},
        "createSmoke": create_smoke,
        "createsOk": creates_ok,
        "blockFraming": {
            "entry": hex(BLOCK_EXTRACT),
            "pythonBlocks": len(py_blocks),
            "unicornBlocks": extracted_u["count"],
            "timeStart": extracted_u.get("timeStart"),
            "timeEnd": extracted_u.get("timeEnd"),
            "channelMatch": channel_match,
            "pythonChannelHist": dict(py_channels.most_common(15)),
            "stop": extracted_u.get("stop"),
            "replicationTypeCandidate": REPLICATION_TYPE_CANDIDATE,
        },
        "deserialize": {
            "okCount": deser_ok,
            "attempted": len(deser_rows),
            "typeHistogram": dict(type_hist.most_common(20)),
            "replicationCandidates": repl_candidates,
            "rows": deser_rows[:40],
        },
        # Keep legacy key for older tests/probe wiring
        "bestWalk": {
            "startOff": 0,
            "okCount": deser_ok,
            "typeHistogram": dict(type_hist.most_common(20)),
            "packets": deser_rows[:40],
        },
        "unmappedFaults": unmapped_faults[:40],
        "replication": [],
        "hpSnapshot": {
            "ok": False,
            "heroCount": 0,
            "heroes": [],
            "acceptance": {"passed": False, "needHeroes": 10},
        },
        "nextSteps": [
            "Confirm type 107 == Replication via UsePacket / field-name tables",
            "Bind CharacterIntermediate and call mHP/mMaxHP getters (slots 0x8d8/0x900)",
            "Emit maknee Replication events into rofl2_to_maknee_events",
            "Map SpawnMinion / BarrackSpawnUnit type ids if minion tracking is needed",
        ],
        "workDir": str(work_dir),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("rofl", type=Path)
    ap.add_argument("--league-binary", type=Path, default=DEFAULT_LEAGUE_BINARY)
    ap.add_argument("--work-dir", type=Path, default=None)
    ap.add_argument("--chunk-index", type=int, default=None)
    ap.add_argument("--max-packets", type=int, default=48)
    ap.add_argument("--max-blocks", type=int, default=512)
    ap.add_argument("--json-out", type=Path, default=None)
    args = ap.parse_args()

    report = drive_rofl(
        rofl=args.rofl,
        league_binary=args.league_binary,
        work_dir=args.work_dir,
        max_packets=args.max_packets,
        max_blocks=args.max_blocks,
        chunk_index=args.chunk_index,
    )
    text = json.dumps(report, indent=2, default=str)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(text + "\n", encoding="utf-8")
        print(f"wrote {args.json_out}")
    else:
        print(text)
    bf = report.get("blockFraming") or {}
    des = report.get("deserialize") or {}
    print(
        f"status={report.get('decryptStatus')} "
        f"blocks={bf.get('unicornBlocks')} "
        f"deserOk={des.get('okCount')} "
        f"replCand={des.get('replicationCandidates')} "
        f"types={des.get('typeHistogram')}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
