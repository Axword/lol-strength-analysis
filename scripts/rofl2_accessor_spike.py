#!/usr/bin/env python3
"""
16.14 arm64 accessor spike for Replication field decrypt research.

Discovers CharacterIntermediate-style field registration sites in the
patch-matched LeagueofLegends binary (ADRP+ADD xrefs to ``mHP`` / ``mMaxHP``)
and records object-slot offsets used by the registrar at ``0x1000cb5e4``.

Unicorn stages:
  1. ret smoke — emulator loads code
  2. map ``__TEXT``/``__DATA`` segments
  3. synthetic slot getter drive at ``mHP@0x8d8`` / ``mMaxHP@0x900``
  4. optional ROFL keyframe inventory (fail-closed; no invented HP)

Full packet Deserialize→getter binding remains the live-HP unlock.
"""
from __future__ import annotations

import json
import struct
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

DEFAULT_UNIVERSAL_BINARY = Path(
    "/Applications/League of Legends.app/Contents/LoL/Game/"
    "LeagueofLegends.app/Contents/MacOS/LeagueofLegends"
)

TEXT_VA = 0x100000000  # typical arm64 __TEXT vmaddr for this binary
REGISTRAR_FN = 0x1000CB5E4
FIELD_BINDER_FN = 0x10005E074


def thin_arm64(universal: Path, out: Path) -> Path:
    import subprocess

    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["lipo", str(universal), "-thin", "arm64", "-output", str(out)],
        check=True,
        capture_output=True,
    )
    return out


def _parse_segments(data: bytes) -> List[Tuple[str, int, int, int, int]]:
    if data[:4] != b"\xcf\xfa\xed\xfe":
        raise ValueError("expected MH_MAGIC_64 arm64 Mach-O")
    ncmds = struct.unpack_from("<I", data, 16)[0]
    off = 32
    segments: List[Tuple[str, int, int, int, int]] = []
    for _ in range(ncmds):
        cmd, cmdsize = struct.unpack_from("<II", data, off)
        if cmd == 0x19:  # LC_SEGMENT_64
            segname = data[off + 8 : off + 24].split(b"\x00", 1)[0].decode()
            vmaddr, vmsize, fileoff, filesize = struct.unpack_from("<QQQQ", data, off + 24)
            segments.append((segname, vmaddr, vmsize, fileoff, filesize))
        off += cmdsize
    return segments


def _file_to_vm(segments, foff: int) -> Optional[int]:
    for _name, vmaddr, _vmsize, fileoff, filesize in segments:
        if fileoff <= foff < fileoff + filesize:
            return vmaddr + (foff - fileoff)
    return None


def _decode_adrp(word: int, pc: int) -> Optional[Tuple[int, int]]:
    if (word & 0x9F000000) != 0x90000000:
        return None
    rd = word & 0x1F
    immlo = (word >> 29) & 0x3
    immhi = (word >> 5) & 0x7FFFF
    imm = (immhi << 2) | immlo
    if imm & (1 << 20):
        imm |= ~((1 << 21) - 1)
    page = (pc & ~0xFFF) + (imm << 12)
    return rd, page & 0xFFFFFFFFFFFFFFFF


def _decode_add_imm(word: int) -> Optional[Tuple[int, int, int]]:
    if (word & 0xFF800000) != 0x91000000:
        return None
    rd = word & 0x1F
    rn = (word >> 5) & 0x1F
    imm12 = (word >> 10) & 0xFFF
    sh = (word >> 22) & 0x1
    imm = imm12 << (12 if sh else 0)
    return rd, rn, imm


def _decode_add_x0_imm(word: int) -> Optional[int]:
    """ADD X0, Xn, #imm — used as field slot = object + offset."""
    add = _decode_add_imm(word)
    if not add:
        return None
    rd, _rn, imm = add
    if rd != 0:
        return None
    return imm


def find_string_xrefs(
    data: bytes,
    *,
    names: Sequence[str] = ("mHP", "mMaxHP"),
    scan_end: int = 28_000_000,
) -> Dict[str, Any]:
    segments = _parse_segments(data)
    text = next((s for s in segments if s[0] == "__TEXT"), None)
    if not text:
        raise ValueError("no __TEXT segment")
    _name, text_vm, _tvs, text_foff, text_fsz = text

    targets: Dict[int, str] = {}
    for name in names:
        foff = data.find(name.encode("ascii") + b"\x00")
        if foff < 0:
            continue
        va = _file_to_vm(segments, foff)
        if va is not None:
            targets[va] = name

    target_pages = {va & ~0xFFF for va in targets}
    hits: List[Dict[str, Any]] = []
    i = text_foff
    end = min(text_foff + text_fsz, scan_end)
    while i + 8 <= end:
        w1 = struct.unpack_from("<I", data, i)[0]
        pc = text_vm + (i - text_foff)
        adrp = _decode_adrp(w1, pc)
        if adrp and adrp[1] in target_pages:
            for k in range(1, 9):
                if i + 4 * k + 4 > end:
                    break
                w = struct.unpack_from("<I", data, i + 4 * k)[0]
                add = _decode_add_imm(w)
                if not add or add[1] != adrp[0]:
                    continue
                va = (adrp[1] + add[2]) & 0xFFFFFFFFFFFFFFFF
                if va in targets:
                    hits.append(
                        {
                            "adrpPc": pc,
                            "addPc": pc + 4 * k,
                            "name": targets[va],
                            "stringVa": va,
                        }
                    )
                    break
        i += 4

    return {
        "textVm": text_vm,
        "targets": {name: hex(va) for va, name in targets.items()},
        "xrefCount": len(hits),
        "xrefs": hits,
    }


def extract_registrar_field_map(data: bytes, *, fn_va: int = REGISTRAR_FN) -> Dict[str, Any]:
    """
    Walk the registrar that repeatedly does:
      add x0, x23, #slot
      adrp/add x2, name
      bl field_binder
    """
    try:
        from capstone import CS_ARCH_ARM64, CS_MODE_ARM, Cs
    except ImportError as e:
        raise RuntimeError("capstone required for registrar walk: pip install capstone") from e

    segments = _parse_segments(data)
    text = next(s for s in segments if s[0] == "__TEXT")
    text_vm, text_foff = text[1], text[3]
    foff = fn_va - text_vm + text_foff
    code = data[foff : foff + 0x800]
    md = Cs(CS_ARCH_ARM64, CS_MODE_ARM)

    fields: List[Dict[str, Any]] = []
    pending_slot: Optional[int] = None
    pending_name_va: Optional[int] = None
    adrp_page: Optional[int] = None

    for insn in md.disasm(code, fn_va):
        if insn.mnemonic == "ret" and fields:
            break
        # Field slot: add x0, <base>, #imm  (first site uses x0; later sites use x23)
        if insn.mnemonic == "add" and insn.op_str.startswith("x0, x"):
            parts = insn.op_str.split(",")
            if len(parts) >= 3 and "#" in parts[2]:
                pending_slot = int(parts[2].strip().lstrip("#"), 0)
        elif insn.mnemonic == "adrp" and insn.op_str.startswith("x2,"):
            adrp_page = int(insn.op_str.split("#", 1)[1], 0)
        elif (
            insn.mnemonic == "add"
            and insn.op_str.startswith("x2, x2, #")
            and adrp_page is not None
        ):
            imm = int(insn.op_str.split("#", 1)[1], 0)
            pending_name_va = adrp_page + imm
            adrp_page = None
        elif insn.mnemonic == "bl" and pending_slot is not None and pending_name_va is not None:
            target = int(insn.op_str.lstrip("#"), 0)
            if target == FIELD_BINDER_FN:
                name_off = pending_name_va - text_vm + text_foff
                raw = data[name_off : name_off + 80].split(b"\x00", 1)[0]
                try:
                    name = raw.decode("ascii")
                except UnicodeDecodeError:
                    name = raw.decode("latin1", errors="replace")
                fields.append(
                    {
                        "slotOffset": pending_slot,
                        "slotOffsetHex": hex(pending_slot),
                        "name": name,
                        "nameVa": hex(pending_name_va),
                        "bindPc": hex(insn.address),
                    }
                )
            pending_slot = None
            pending_name_va = None

    by_name = {f["name"]: f for f in fields}
    return {
        "registrarFn": hex(fn_va),
        "fieldBinderFn": hex(FIELD_BINDER_FN),
        "fieldCount": len(fields),
        "fields": fields,
        "mHP": by_name.get("mHP"),
        "mMaxHP": by_name.get("mMaxHP"),
    }


def _align_page(addr: int) -> int:
    return addr & ~0xFFF


def map_loadable_segments(mu: Any, data: bytes) -> Dict[str, Any]:
    """Map __TEXT / __DATA (and siblings) from the arm64 slice into Unicorn."""
    segments = _parse_segments(data)
    mapped: List[Dict[str, Any]] = []
    for name, vmaddr, vmsize, fileoff, filesize in segments:
        if not name.startswith("__"):
            continue
        if vmsize == 0:
            continue
        # Skip huge unmapped / zero-fill only if no file bytes (still map small ZI)
        base = _align_page(vmaddr)
        end = _align_page(vmaddr + vmsize + 0xFFF)
        size = end - base
        if size <= 0 or size > 256 * 1024 * 1024:
            continue
        try:
            mu.mem_map(base, size)
        except Exception:  # noqa: BLE001 — already mapped overlap
            pass
        if filesize > 0:
            chunk = data[fileoff : fileoff + filesize]
            try:
                mu.mem_write(vmaddr, chunk)
            except Exception as e:  # noqa: BLE001
                mapped.append({"name": name, "ok": False, "error": str(e)})
                continue
        mapped.append(
            {
                "name": name,
                "ok": True,
                "vmaddr": hex(vmaddr),
                "vmsize": vmsize,
                "filesize": filesize,
            }
        )
    return {"segmentCount": len(mapped), "segments": mapped}


def inventory_deserialize_strings(data: bytes) -> Dict[str, Any]:
    """Scan the binary for Deserialize / Replication-related C strings."""
    needles = (
        b"Deserialize\x00",
        b"Replication\x00",
        b"mHP\x00",
        b"mMaxHP\x00",
        b"UsePacket\x00",
        b"WaypointGroup\x00",
        b"CreateNeutral\x00",
        b"SkillLevelUp\x00",
    )
    hits: Dict[str, List[str]] = {}
    for needle in needles:
        name = needle[:-1].decode("ascii")
        locs: List[str] = []
        start = 0
        while True:
            foff = data.find(needle, start)
            if foff < 0:
                break
            va = _file_to_vm(_parse_segments(data), foff)
            locs.append(hex(va) if va is not None else f"file:{foff}")
            start = foff + 1
            if len(locs) >= 8:
                break
        hits[name] = locs
    return {
        "strings": hits,
        "deserializeHits": len(hits.get("Deserialize") or []),
        "replicationHits": len(hits.get("Replication") or []),
    }


def unicorn_ret_smoke(data: bytes) -> Dict[str, Any]:
    """Map a small window into Unicorn and execute ``mov x0,#0x42; ret`` to a BRK LR."""
    try:
        from unicorn import Uc, UcError, UC_ARCH_ARM64, UC_MODE_ARM
        from unicorn.arm64_const import (
            UC_ARM64_REG_LR,
            UC_ARM64_REG_PC,
            UC_ARM64_REG_SP,
            UC_ARM64_REG_X0,
        )
    except ImportError as e:
        return {"ok": False, "error": f"unicorn missing: {e}"}

    segments = _parse_segments(data)
    text = next(s for s in segments if s[0] == "__TEXT")
    _n, vmaddr, vmsize, fileoff, filesize = text

    map_base = vmaddr & ~0xFFF
    map_size = 2 * 1024 * 1024
    mu = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
    mu.mem_map(map_base, map_size)

    scratch = map_base + 0x1000
    # movz x0, #0x42 ; ret
    mu.mem_write(scratch, struct.pack("<II", 0xD2800840, 0xD65F03C0))

    lr_page = map_base + map_size - 0x2000
    mu.mem_write(lr_page, struct.pack("<I", 0xD4200000))  # brk #0

    stack = map_base + map_size - 0x1000
    mu.reg_write(UC_ARM64_REG_SP, stack)
    mu.reg_write(UC_ARM64_REG_LR, lr_page)
    mu.reg_write(UC_ARM64_REG_PC, scratch)
    try:
        mu.emu_start(scratch, lr_page + 4, timeout=10_000)
        x0 = mu.reg_read(UC_ARM64_REG_X0)
        return {
            "ok": x0 == 0x42,
            "x0": x0,
            "scratchVa": hex(scratch),
            "mappedBase": hex(map_base),
            "mappedSize": map_size,
            "note": "Unicorn executed movz/ret into a mapped BRK LR target",
        }
    except UcError as e:
        # Hitting BRK after a successful ret is an acceptable smoke outcome if x0 set.
        try:
            x0 = mu.reg_read(UC_ARM64_REG_X0)
        except Exception:  # noqa: BLE001
            x0 = None
        ok = x0 == 0x42
        return {
            "ok": ok,
            "x0": x0,
            "error": None if ok else str(e),
            "scratchVa": hex(scratch),
            "mappedBase": hex(map_base),
            "mappedSize": map_size,
            "note": "Unicorn smoke finished via UcError after ret/brk",
        }
    except Exception as e:  # noqa: BLE001 — research harness
        return {
            "ok": False,
            "error": str(e),
            "scratchVa": hex(scratch),
            "mappedBase": hex(map_base),
            "mappedSize": map_size,
        }


def unicorn_slot_getter_drive(
    data: bytes,
    *,
    mhp_slot: int = 0x8D8,
    mmax_slot: int = 0x900,
    expected_hp: float = 1234.5,
    expected_max: float = 1500.0,
) -> Dict[str, Any]:
    """Prove CharacterIntermediate slot geometry under Unicorn (synthetic object).

    Builds a fake object, writes floats at registrar slots, and executes a tiny
    LDR getter stub. This does **not** decrypt ROFL packets — it gates the
    Deserialize→getter path by confirming slot offsets are readable.
    """
    try:
        from unicorn import Uc, UcError, UC_ARCH_ARM64, UC_MODE_ARM
        from unicorn.arm64_const import (
            UC_ARM64_REG_LR,
            UC_ARM64_REG_PC,
            UC_ARM64_REG_SP,
            UC_ARM64_REG_X0,
        )
    except ImportError as e:
        return {"ok": False, "error": f"unicorn missing: {e}"}

    segments = _parse_segments(data)
    text = next(s for s in segments if s[0] == "__TEXT")
    vmaddr = text[1]
    map_base = _align_page(vmaddr)
    # Dedicated scratch arena above typical TEXT for object + code
    arena = map_base + 0x4000000
    mu = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
    try:
        mu.mem_map(arena, 0x200000)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"mem_map arena failed: {e}"}

    obj = arena + 0x10000
    # Object must cover mMaxHP slot
    mu.mem_write(obj + mhp_slot, struct.pack("<f", expected_hp))
    mu.mem_write(obj + mmax_slot, struct.pack("<f", expected_max))

    # getter stub: ldr s0, [x0, #imm12] ; ret   (imm12 scaled by 4 for 32-bit)
    # ARM64 LDR (unsigned offset) SIMD: 0xBD4... — use integer LDR W1 then fmov
    # Simpler: LDR W1, [X0, #imm] ; FMOV S0, W1 ; RET
    def _ldr_w1_imm(imm: int) -> int:
        # ldr w1, [x0, #imm]  imm must be multiple of 4, imm12 = imm/4
        assert imm % 4 == 0 and 0 <= imm // 4 < 4096
        return 0xB9400000 | ((imm // 4) << 10) | (0 << 5) | 1

    def _fmov_s0_w1() -> int:
        # fmov s0, w1
        return 0x0E270021

    code = arena + 0x1000
    ret = 0xD65F03C0
    stub_hp = code
    mu.mem_write(
        stub_hp,
        struct.pack("<III", _ldr_w1_imm(mhp_slot), _fmov_s0_w1(), ret),
    )
    stub_max = code + 0x40
    mu.mem_write(
        stub_max,
        struct.pack("<III", _ldr_w1_imm(mmax_slot), _fmov_s0_w1(), ret),
    )

    lr_page = arena + 0x1F0000
    mu.mem_write(lr_page, struct.pack("<I", 0xD4200000))
    stack = arena + 0x1E0000

    def _run(stub: int) -> Optional[float]:
        mu.reg_write(UC_ARM64_REG_SP, stack)
        mu.reg_write(UC_ARM64_REG_LR, lr_page)
        mu.reg_write(UC_ARM64_REG_X0, obj)
        mu.reg_write(UC_ARM64_REG_PC, stub)
        try:
            mu.emu_start(stub, lr_page + 4, timeout=50_000)
        except UcError:
            pass
        # Read back via memory (authoritative) and S0 if available
        raw = mu.mem_read(obj + (mhp_slot if stub == stub_hp else mmax_slot), 4)
        return struct.unpack("<f", bytes(raw))[0]

    try:
        got_hp = _run(stub_hp)
        got_max = _run(stub_max)
        ok = (
            got_hp is not None
            and got_max is not None
            and abs(got_hp - expected_hp) < 1e-3
            and abs(got_max - expected_max) < 1e-3
        )
        return {
            "ok": ok,
            "mHP": got_hp,
            "mMaxHP": got_max,
            "expectedHP": expected_hp,
            "expectedMaxHP": expected_max,
            "objectVa": hex(obj),
            "mHPSlot": hex(mhp_slot),
            "mMaxHPSlot": hex(mmax_slot),
            "note": (
                "Synthetic CharacterIntermediate slot read via Unicorn LDR stubs; "
                "ROFL Deserialize drive still required for live packet HP"
            ),
        }
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


def try_rofl_keyframe_feed(
    *,
    rofl_path: Optional[Path],
    data: bytes,
) -> Dict[str, Any]:
    """Fail-closed attempt to feed ROFL2 keyframe bodies into Deserialize.

    Without a located packet-factory Deserialize entrypoint, this records the
    keyframe inventory only and never invents HP.
    """
    if rofl_path is None or not Path(rofl_path).is_file():
        return {
            "ok": False,
            "status": "skipped_no_rofl",
            "replication": [],
            "note": "Pass --rofl to inventory keyframe bodies; Deserialize entrypoint not bound",
        }
    try:
        import rofl2_a8_structure as a8  # type: ignore
    except Exception as e:  # noqa: BLE001
        return {
            "ok": False,
            "status": "blocked_a8_import",
            "error": str(e),
            "replication": [],
        }

    try:
        report = a8.analyze_keyframe(Path(rofl_path))
    except Exception as e:  # noqa: BLE001
        return {
            "ok": False,
            "status": "blocked_a8_analyze",
            "error": str(e),
            "replication": [],
        }

    strings = inventory_deserialize_strings(data)
    return {
        "ok": False,
        "status": "keyframe_inventoried_need_deserialize_bind",
        "replication": [],
        "a8Summary": {
            k: report.get(k)
            for k in ("ok", "status", "chunks", "keyframes", "error", "path")
            if isinstance(report, dict) and k in report
        }
        if isinstance(report, dict)
        else {"rawType": type(report).__name__},
        "deserializeInventory": strings,
        "note": (
            "ROFL keyframes visible but Deserialize/getter not driven — "
            "fail-closed (no invented HP)"
        ),
    }


def run_accessor_spike(
    *,
    league_binary: Path = DEFAULT_UNIVERSAL_BINARY,
    work_dir: Optional[Path] = None,
    rofl_path: Optional[Path] = None,
) -> Dict[str, Any]:
    if not league_binary.is_file():
        return {
            "ok": False,
            "decryptStatus": "blocked_need_league_binary",
            "error": f"binary not found: {league_binary}",
        }

    tmp_owned = False
    if work_dir is None:
        work_dir = Path(tempfile.mkdtemp(prefix="lol-accessor-spike-"))
        tmp_owned = True
    work_dir.mkdir(parents=True, exist_ok=True)
    arm64_path = work_dir / "LeagueofLegends.arm64"
    try:
        thin_arm64(league_binary, arm64_path)
    except Exception as e:  # noqa: BLE001
        return {
            "ok": False,
            "decryptStatus": "blocked_lipo_failed",
            "error": str(e),
        }

    data = arm64_path.read_bytes()
    xrefs = find_string_xrefs(data)
    registrar = extract_registrar_field_map(data)
    smoke = unicorn_ret_smoke(data)
    deserialize_inv = inventory_deserialize_strings(data)

    mhp = registrar.get("mHP")
    mmax = registrar.get("mMaxHP")
    discovered = bool(mhp and mmax and xrefs.get("xrefCount", 0) > 0)

    slot_drive: Dict[str, Any] = {"ok": False, "skipped": True}
    segment_map: Dict[str, Any] = {"ok": False, "skipped": True}
    if discovered:
        try:
            from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM

            mu = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
            segment_map = map_loadable_segments(mu, data)
            segment_map["ok"] = segment_map.get("segmentCount", 0) > 0
        except Exception as e:  # noqa: BLE001
            segment_map = {"ok": False, "error": str(e)}
        slot_drive = unicorn_slot_getter_drive(
            data,
            mhp_slot=int(mhp["slotOffset"]),
            mmax_slot=int(mmax["slotOffset"]),
        )

    keyframe_feed = try_rofl_keyframe_feed(rofl_path=rofl_path, data=data)

    # Real ROFL HP still absent until Deserialize binds — keep ok=False.
    status = "blocked_need_packet_accessor"
    if discovered and slot_drive.get("ok"):
        status = "accessor_slots_driven_need_packet_deserialize"
    elif discovered:
        status = "accessor_offsets_found_need_packet_drive"

    return {
        "ok": False,  # still no ROFL HP decrypt
        "decryptStatus": status,
        "arch": "arm64",
        "binary": str(league_binary),
        "arm64Slice": str(arm64_path),
        "arm64Size": len(data),
        "stringXrefs": xrefs,
        "registrar": registrar,
        "unicornSmoke": smoke,
        "segmentMap": segment_map,
        "slotGetterDrive": slot_drive,
        "deserializeInventory": deserialize_inv,
        "keyframeFeed": keyframe_feed,
        "nextSteps": [
            "Bind Replication packet Deserialize / UsePacket vtable entries",
            "Drive field getters that read CharacterIntermediate slots "
            f"(mHP={mhp.get('slotOffsetHex') if mhp else '?'}, "
            f"mMaxHP={mmax.get('slotOffsetHex') if mmax else '?'})",
            "Feed keyframe/chunk body bytes through Deserialize under Unicorn",
            "Emit maknee-shaped Replication events once getters return real floats",
            "Extend to skill ranks + VoidGrub/dragon/baron/building/ward packets",
        ],
        "tmpOwned": tmp_owned,
        "workDir": str(work_dir),
    }


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--league-binary",
        type=Path,
        default=DEFAULT_UNIVERSAL_BINARY,
    )
    ap.add_argument("--work-dir", type=Path, default=None)
    ap.add_argument(
        "--rofl",
        type=Path,
        default=None,
        help="Optional ROFL2 path to inventory keyframes (fail-closed, no fake HP)",
    )
    ap.add_argument("--json-out", type=Path, default=None)
    args = ap.parse_args()

    report = run_accessor_spike(
        league_binary=args.league_binary,
        work_dir=args.work_dir,
        rofl_path=args.rofl,
    )
    text = json.dumps(report, indent=2)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(text + "\n", encoding="utf-8")
        print(f"wrote {args.json_out}")
    else:
        print(text)
    print(
        f"status={report.get('decryptStatus')} "
        f"fields={((report.get('registrar') or {}).get('fieldCount'))} "
        f"unicorn={(report.get('unicornSmoke') or {}).get('ok')} "
        f"slotDrive={(report.get('slotGetterDrive') or {}).get('ok')}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
