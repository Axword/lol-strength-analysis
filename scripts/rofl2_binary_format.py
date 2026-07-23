#!/usr/bin/env python3
"""OS-neutral binary format abstraction for League packet discovery.

Supports:
  - Mach-O 64 (thin x86_64 / arm64, or universal via lipo extract)
  - PE32+ x86-64 (section parse + same VA/file helpers)

Never vendors Riot binaries. Research manifests record platform/arch/SHA256.
"""
from __future__ import annotations

import hashlib
import struct
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

MH_MAGIC_64 = 0xFEEDFACF
MH_CIGAM_64 = 0xCFFAEDFE
FAT_MAGIC = 0xCAFEBABE
FAT_CIGAM = 0xBEBAFECA
LC_SEGMENT_64 = 0x19
CPU_TYPE_X86_64 = 0x01000007
CPU_TYPE_ARM64 = 0x0100000C

IMAGE_DOS_SIGNATURE = 0x5A4D
IMAGE_NT_SIGNATURE = 0x00004550
IMAGE_FILE_MACHINE_AMD64 = 0x8664


@dataclass
class Segment:
    name: str
    vmaddr: int
    vmsize: int
    fileoff: int
    filesize: int


@dataclass
class LoadedBinary:
    path: Path
    data: bytes
    format: str  # "macho64" | "pe64"
    arch: str  # "x86_64" | "arm64" | "unknown"
    platform: str  # "macos" | "windows" | "unknown"
    segments: List[Segment]
    sha256: str
    text_va: int
    text_size: int

    def va_to_file(self, va: int) -> Optional[int]:
        for seg in self.segments:
            if seg.vmaddr <= va < seg.vmaddr + seg.vmsize:
                rel = va - seg.vmaddr
                if rel < seg.filesize:
                    return seg.fileoff + rel
        return None

    def file_to_va(self, foff: int) -> Optional[int]:
        for seg in self.segments:
            if seg.fileoff <= foff < seg.fileoff + seg.filesize:
                return seg.vmaddr + (foff - seg.fileoff)
        return None

    def read_va(self, va: int, n: int) -> bytes:
        fo = self.va_to_file(va)
        if fo is None:
            raise ValueError(f"VA {hex(va)} not mapped")
        return self.data[fo : fo + n]

    def read_u64(self, va: int) -> int:
        return struct.unpack_from("<Q", self.read_va(va, 8), 0)[0]

    def read_u32(self, va: int) -> int:
        return struct.unpack_from("<I", self.read_va(va, 4), 0)[0]

    def text_bytes(self) -> Tuple[int, bytes]:
        for seg in self.segments:
            if seg.name in ("__TEXT", ".text"):
                return seg.vmaddr, self.data[seg.fileoff : seg.fileoff + seg.filesize]
        raise ValueError("no text segment")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def thin_macho_arch(universal: Path, arch: str, out: Path) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["lipo", str(universal), "-thin", arch, "-output", str(out)],
        check=True,
        capture_output=True,
    )
    return out


def detect_format(data: bytes) -> str:
    if len(data) < 4:
        return "unknown"
    mag = struct.unpack_from("<I", data, 0)[0]
    if mag in (MH_MAGIC_64, MH_CIGAM_64, FAT_MAGIC, FAT_CIGAM):
        return "macho"
    if struct.unpack_from("<H", data, 0)[0] == IMAGE_DOS_SIGNATURE:
        return "pe"
    return "unknown"


def parse_macho64_segments(data: bytes) -> Tuple[str, List[Segment]]:
    mag = struct.unpack_from("<I", data, 0)[0]
    if mag == FAT_MAGIC or mag == FAT_CIGAM:
        raise ValueError("fat Mach-O not thinned; call thin_macho_arch first")
    if mag != MH_MAGIC_64:
        raise ValueError(f"expected MH_MAGIC_64, got {hex(mag)}")
    cputype = struct.unpack_from("<I", data, 4)[0]
    if cputype == CPU_TYPE_X86_64:
        arch = "x86_64"
    elif cputype == CPU_TYPE_ARM64:
        arch = "arm64"
    else:
        arch = f"cpu_{hex(cputype)}"
    ncmds = struct.unpack_from("<I", data, 16)[0]
    off = 32
    segs: List[Segment] = []
    for _ in range(ncmds):
        cmd, cmdsize = struct.unpack_from("<II", data, off)
        if cmd == LC_SEGMENT_64:
            name = data[off + 8 : off + 24].split(b"\x00", 1)[0].decode("ascii", "replace")
            vmaddr, vmsize, fileoff, filesize = struct.unpack_from("<QQQQ", data, off + 24)
            segs.append(Segment(name, vmaddr, vmsize, fileoff, filesize))
        off += cmdsize
    return arch, segs


def parse_pe64_sections(data: bytes) -> Tuple[str, List[Segment], int]:
    """Parse PE32+ sections. Returns (arch, segments, image_base)."""
    if struct.unpack_from("<H", data, 0)[0] != IMAGE_DOS_SIGNATURE:
        raise ValueError("not a DOS/PE image")
    e_lfanew = struct.unpack_from("<I", data, 0x3C)[0]
    if struct.unpack_from("<I", data, e_lfanew)[0] != IMAGE_NT_SIGNATURE:
        raise ValueError("missing PE signature")
    file_header = e_lfanew + 4
    machine = struct.unpack_from("<H", data, file_header)[0]
    if machine != IMAGE_FILE_MACHINE_AMD64:
        raise ValueError(f"unsupported PE machine {hex(machine)} (want amd64)")
    nsections = struct.unpack_from("<H", data, file_header + 2)[0]
    opt_size = struct.unpack_from("<H", data, file_header + 16)[0]
    opt = file_header + 20
    magic = struct.unpack_from("<H", data, opt)[0]
    if magic != 0x20B:
        raise ValueError(f"expected PE32+ optional header (0x20b), got {hex(magic)}")
    image_base = struct.unpack_from("<Q", data, opt + 24)[0]
    sec_off = opt + opt_size
    segs: List[Segment] = []
    for i in range(nsections):
        so = sec_off + i * 40
        name = data[so : so + 8].split(b"\x00", 1)[0].decode("ascii", "replace")
        vmsize = struct.unpack_from("<I", data, so + 8)[0]
        va = struct.unpack_from("<I", data, so + 12)[0]
        raw_size = struct.unpack_from("<I", data, so + 16)[0]
        raw_ptr = struct.unpack_from("<I", data, so + 20)[0]
        segs.append(
            Segment(
                name=name,
                vmaddr=image_base + va,
                vmsize=vmsize,
                fileoff=raw_ptr,
                filesize=raw_size,
            )
        )
    return "x86_64", segs, image_base


def load_binary(
    path: Path,
    *,
    prefer_arch: str = "x86_64",
    work_dir: Optional[Path] = None,
) -> LoadedBinary:
    """Load League binary; auto-detect Mach-O universal/thin vs PE."""
    path = Path(path)
    raw = path.read_bytes()
    kind = detect_format(raw)
    if kind == "macho":
        mag = struct.unpack_from("<I", raw, 0)[0]
        data = raw
        src_path = path
        if mag in (FAT_MAGIC, FAT_CIGAM):
            if work_dir is None:
                work_dir = Path(tempfile.mkdtemp(prefix="lol-bin-"))
            thin = work_dir / f"League.{prefer_arch}"
            thin_macho_arch(path, prefer_arch, thin)
            data = thin.read_bytes()
            src_path = thin
        arch, segs = parse_macho64_segments(data)
        text = next((s for s in segs if s.name == "__TEXT"), None)
        if text is None:
            raise ValueError("Mach-O missing __TEXT")
        return LoadedBinary(
            path=src_path,
            data=data,
            format="macho64",
            arch=arch,
            platform="macos",
            segments=segs,
            sha256=_sha256(data),
            text_va=text.vmaddr,
            text_size=text.filesize,
        )
    if kind == "pe":
        arch, segs, _base = parse_pe64_sections(raw)
        text = next((s for s in segs if s.name == ".text"), segs[0] if segs else None)
        if text is None:
            raise ValueError("PE missing sections")
        return LoadedBinary(
            path=path,
            data=raw,
            format="pe64",
            arch=arch,
            platform="windows",
            segments=segs,
            sha256=_sha256(raw),
            text_va=text.vmaddr,
            text_size=text.filesize,
        )
    raise ValueError(f"unsupported binary format for {path}")


def research_manifest(binary: LoadedBinary, *, patch: str, extra: Optional[Dict[str, Any]] = None) -> dict:
    man = {
        "kind": "league_packet_discovery_binary",
        "patch": patch,
        "platform": binary.platform,
        "arch": binary.arch,
        "format": binary.format,
        "sha256": binary.sha256,
        "pathNote": "local derivation only; never commit Riot binaries",
        "derivationStatus": "derived_offline",
        "textVa": hex(binary.text_va),
        "textSize": binary.text_size,
        "segmentCount": len(binary.segments),
    }
    if extra:
        man.update(extra)
    return man


def build_synthetic_pe64(
    *,
    image_base: int = 0x140000000,
    text: bytes = b"\x90" * 64,
    sections: Optional[Sequence[Tuple[str, bytes]]] = None,
) -> bytes:
    """Minimal PE32+ for unit tests (not a real League binary)."""
    secs = list(sections or [(".text", text)])
    dos = bytearray(128)
    struct.pack_into("<H", dos, 0, IMAGE_DOS_SIGNATURE)
    struct.pack_into("<I", dos, 0x3C, 128)
    # COFF + optional PE32+
    nsec = len(secs)
    opt = bytearray(240)  # PE32+ optional header size commonly 240
    struct.pack_into("<H", opt, 0, 0x20B)
    struct.pack_into("<Q", opt, 24, image_base)
    struct.pack_into("<I", opt, 16, 0x1000)  # section alignment
    struct.pack_into("<I", opt, 20, 0x200)  # file alignment
    file_header = struct.pack(
        "<HHIIIHH",
        IMAGE_FILE_MACHINE_AMD64,
        nsec,
        0,
        0,
        0,
        len(opt),
        0x22,  # executable + large address aware
    )
    # Place section raw data after headers
    sec_table = bytearray()
    raw_blobs = []
    raw_off = 0x400
    va = 0x1000
    for name, blob in secs:
        padded = blob + b"\x00" * ((0x200 - (len(blob) % 0x200)) % 0x200)
        nm = name.encode("ascii")[:8].ljust(8, b"\x00")
        sec_table += nm
        sec_table += struct.pack("<IIIIIIHHI", len(blob), va, len(padded), raw_off, 0, 0, 0, 0, 0x60000020)
        raw_blobs.append((raw_off, padded))
        raw_off += len(padded)
        va += 0x1000
    pe = bytes(dos) + struct.pack("<I", IMAGE_NT_SIGNATURE) + file_header + bytes(opt) + bytes(sec_table)
    pe = pe.ljust(0x400, b"\x00")
    buf = bytearray(pe)
    for off, blob in raw_blobs:
        if len(buf) < off + len(blob):
            buf.extend(b"\x00" * (off + len(blob) - len(buf)))
        buf[off : off + len(blob)] = blob
    return bytes(buf)
