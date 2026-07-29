#!/usr/bin/env python3
"""Strict MSVC x64 RTTI CompleteObjectLocator / TypeDescriptor decoding.

Valid COL (x64):
  +0  signature == 1
  +4  offset
  +8  cdOffset
  +12 pTypeDescriptor  (image-relative RVA)
  +16 pClassDescriptor (image-relative RVA)
  +20 pSelf            (image-relative RVA of this COL)

TypeDescriptor:
  +0  pVFTable
  +8  spare
  +16 name  (ASCII, typically .?AV...@@)

vptr[-1] on x64 is a pointer to COL (absolute VA), not an RVA.
"""
from __future__ import annotations

import re
import struct
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from rofl2_binary_format import LoadedBinary

IMAGE_BASE_DEFAULT = 0x140000000
COL_SIGNATURE_X64 = 1
NAME_RE = re.compile(r"^\.\?A[UV].+")


@dataclass(frozen=True)
class TypeDescriptor:
    va: int
    name: str
    name_va: int


@dataclass(frozen=True)
class CompleteObjectLocator:
    va: int
    signature: int
    offset: int
    cd_offset: int
    type_descriptor: TypeDescriptor
    p_self_rva: int


@dataclass(frozen=True)
class RttiLookup:
    col: Optional[CompleteObjectLocator]
    ok: bool
    reason: str
    demangled: Optional[str] = None


def image_base(binary: LoadedBinary) -> int:
    # PE preferred image base from optional header if present; else default.
    data = binary.data
    if len(data) < 0x40 or struct.unpack_from("<H", data, 0)[0] != 0x5A4D:
        return IMAGE_BASE_DEFAULT
    e_lfanew = struct.unpack_from("<I", data, 0x3C)[0]
    if e_lfanew + 0x30 + 8 > len(data):
        return IMAGE_BASE_DEFAULT
    # PE32+ optional header: ImageBase at +24 from optional header start
    # optional header starts at e_lfanew+24
    opt = e_lfanew + 24
    magic = struct.unpack_from("<H", data, opt)[0]
    if magic != 0x20B:  # PE32+
        return IMAGE_BASE_DEFAULT
    return int(struct.unpack_from("<Q", data, opt + 24)[0])


def _in_image(binary: LoadedBinary, va: int, nbytes: int = 1) -> bool:
    try:
        binary.read_va(va, nbytes)
        return True
    except Exception:  # noqa: BLE001
        return False


def read_type_descriptor(binary: LoadedBinary, td_va: int) -> Optional[TypeDescriptor]:
    if not _in_image(binary, td_va, 24):
        return None
    raw = binary.read_va(td_va + 16, 256)
    if not raw or raw[0:1] != b".":
        return None
    name = raw.split(b"\x00", 1)[0].decode("ascii", "replace")
    if not NAME_RE.match(name):
        return None
    return TypeDescriptor(va=td_va, name=name, name_va=td_va + 16)


def demangle_msvc_name(name: str) -> str:
    """Best-effort demangle for reports (not a full undname)."""
    if name.startswith(".?AV") and name.endswith("@@"):
        inner = name[4:-2]
        # Nested namespaces use @ separators in reverse
        parts = [p for p in inner.split("@") if p]
        parts.reverse()
        return "::".join(parts) if parts else name
    if name.startswith(".?AU") and name.endswith("@@"):
        inner = name[4:-2]
        parts = [p for p in inner.split("@") if p]
        parts.reverse()
        return "::".join(parts) if parts else name
    # Keep MakeFunction lambda names readable by extracting PKT_* token
    m = re.search(r"(PKT_[A-Za-z0-9_]+)", name)
    if m:
        return f"MakeFunction<...{m.group(1)}...>"
    return name


def validate_col(
    binary: LoadedBinary,
    col_va: int,
    *,
    base: Optional[int] = None,
) -> Tuple[Optional[CompleteObjectLocator], str]:
    """Strict COL validation. Returns (col, reason)."""
    base = IMAGE_BASE_DEFAULT if base is None else int(base)
    if not _in_image(binary, col_va, 24):
        return None, "col_unmapped"
    sig, offset, cd_off, p_td, p_chd, p_self = struct.unpack(
        "<IIIIII", binary.read_va(col_va, 24)
    )
    if sig != COL_SIGNATURE_X64:
        return None, f"bad_signature:{sig}"
    expect_self = (col_va - base) & 0xFFFFFFFF
    if p_self != expect_self:
        return None, f"pSelf_mismatch:got={p_self:#x} want={expect_self:#x}"
    td_va = base + (p_td & 0xFFFFFFFF)
    if not _in_image(binary, td_va, 24):
        return None, "type_descriptor_unmapped"
    # Class hierarchy descriptor must also land in image (bounds check only)
    chd_va = base + (p_chd & 0xFFFFFFFF)
    if not _in_image(binary, chd_va, 4):
        return None, "class_descriptor_unmapped"
    td = read_type_descriptor(binary, td_va)
    if td is None:
        return None, "type_name_grammar_reject"
    return (
        CompleteObjectLocator(
            va=col_va,
            signature=sig,
            offset=offset,
            cd_offset=cd_off,
            type_descriptor=td,
            p_self_rva=p_self,
        ),
        "ok",
    )


def rtti_from_vptr(
    binary: LoadedBinary,
    vptr: int,
    *,
    base: Optional[int] = None,
) -> RttiLookup:
    """Resolve class name via vptr[-1] -> COL. No string proximity fallbacks."""
    base = IMAGE_BASE_DEFAULT if base is None else int(base)
    if not _in_image(binary, vptr - 8, 8):
        return RttiLookup(None, False, "vptr_minus1_unmapped")
    col_va = struct.unpack("<Q", binary.read_va(vptr - 8, 8))[0]
    if col_va == 0 or not _in_image(binary, col_va, 24):
        return RttiLookup(None, False, "col_ptr_invalid")
    # Reject if "COL" lands in executable .text (common false positive)
    try:
        text_va, text = binary.text_bytes()
        if text_va <= col_va < text_va + len(text):
            return RttiLookup(None, False, "col_in_text")
    except Exception:  # noqa: BLE001
        pass
    col, reason = validate_col(binary, col_va, base=base)
    if col is None:
        return RttiLookup(None, False, reason)
    return RttiLookup(col, True, "ok", demangle_msvc_name(col.type_descriptor.name))


def scan_valid_cols(binary: LoadedBinary, *, base: Optional[int] = None) -> List[CompleteObjectLocator]:
    """Scan .rdata/.data for COLs that pass strict validation."""
    base = IMAGE_BASE_DEFAULT if base is None else int(base)
    out: List[CompleteObjectLocator] = []
    for seg in binary.segments:
        if seg.name not in (".rdata", ".data", "_RDATA"):
            continue
        blob = binary.data[seg.fileoff : seg.fileoff + seg.filesize]
        for i in range(0, max(0, len(blob) - 24), 4):
            if struct.unpack_from("<I", blob, i)[0] != COL_SIGNATURE_X64:
                continue
            col_va = seg.vmaddr + i
            col, reason = validate_col(binary, col_va, base=base)
            if col is not None:
                out.append(col)
    return out


def annotate_factory_vptrs(
    binary: LoadedBinary,
    factories: Sequence[Mapping[str, Any]],
    *,
    base: Optional[int] = None,
) -> dict:
    """RTTI annotate every factory vptr. Reports coverage; no proximity guessing."""
    base = IMAGE_BASE_DEFAULT if base is None else int(base)
    rows = []
    ok = 0
    for fac in factories:
        vptr = fac.get("vptr")
        if isinstance(vptr, str):
            vptr = int(vptr, 16) if vptr.startswith("0x") else int(vptr)
        if not vptr:
            rows.append(
                {
                    "opcode": fac.get("opcode"),
                    "vptr": None,
                    "rttiOk": False,
                    "reason": "missing_vptr",
                }
            )
            continue
        look = rtti_from_vptr(binary, int(vptr), base=base)
        if look.ok:
            ok += 1
        rows.append(
            {
                "opcode": fac.get("opcode"),
                "vptr": hex(int(vptr)),
                "rttiOk": look.ok,
                "reason": look.reason,
                "className": look.demangled,
                "mangled": look.col.type_descriptor.name if look.col else None,
                "colVa": hex(look.col.va) if look.col else None,
            }
        )
    n = len(rows)
    return {
        "factoryCount": n,
        "rttiOkCount": ok,
        "coverageRatio": round(ok / max(1, n), 4),
        "rows": rows,
    }
