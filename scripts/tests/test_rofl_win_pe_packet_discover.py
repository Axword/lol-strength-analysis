#!/usr/bin/env python3
"""Tests for E7b Windows PE MSVC packet discovery (no real PE fixture)."""
from __future__ import annotations

import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from rofl2_binary_format import build_synthetic_pe64, load_binary  # noqa: E402
import rofl2_win_pe_packet_discover as e7b  # noqa: E402

REAL_PE = Path("/tmp/League-of-Legends-16.14-win.exe")


def _msvc_ctor_stub(*, opcode: int) -> bytes:
    """Minimal MSVC-like ctor: lea rax,[rip+X]; mov word [rcx+8],op; mov [rcx],rax; ret."""
    # lea rax, [rip+0] ; we'll pad so target is after stub
    body = bytearray()
    body += b"\x48\x8d\x05\x10\x00\x00\x00"  # lea rax,[rip+0x10]
    body += b"\x66\xc7\x41\x08" + struct.pack("<H", opcode)
    body += b"\x48\x89\x01"  # mov [rcx], rax
    body += b"\x48\x89\xc8"  # mov rax, rcx
    body += b"\xc3"
    # pad to lea target + fake vtable slots
    while len(body) < 0x17:
        body += b"\x90"
    # at lea target (rip after lea = start+7, +0x10 = start+0x17)
    body += struct.pack("<QQQQ", 0x1000, 0x2000, 0x3000, 0)  # dtor, deser, use
    return bytes(body)


class MsvcCtorVtableScannerTests(unittest.TestCase):
    def test_opcode_store_and_final_vptr_no_itanium_plus10(self):
        stub = _msvc_ctor_stub(opcode=980)
        pe = build_synthetic_pe64(text=b"\xcc" + stub + b"\x90" * 64)
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "fake.exe"
            path.write_bytes(pe)
            binary = load_binary(path)
        text_va, text = binary.text_bytes()
        # find store
        i = text.find(b"\x66\xc7\x41\x08")
        self.assertGreaterEqual(i, 0)
        store_va = text_va + i
        rec = e7b.recover_msvc_ctor(binary, store_va)
        self.assertEqual(rec["opcode"], 980)
        self.assertIsNotNone(rec["vptr"])
        # MSVC: vptr == lea target (NOT lea+0x10)
        lea_end = text_va + text.find(b"\x48\x8d\x05") + 7
        expected_vptr = lea_end + 0x10
        self.assertEqual(rec["vptr"], expected_vptr)
        self.assertEqual(rec["deserializeVa"], 0x2000)
        self.assertEqual(rec["useVa"], 0x3000)
        self.assertEqual(rec["dtorVa"], 0x1000)

    def test_false_positive_mov_word_without_vptr_store(self):
        bait = b"\x90" * 16 + b"\x66\xc7\x41\x08" + struct.pack("<H", 556) + b"\xc3"
        pe = build_synthetic_pe64(text=bait)
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "fp.exe"
            path.write_bytes(pe)
            binary = load_binary(path)
        text_va, text = binary.text_bytes()
        store_va = text_va + text.find(b"\x66\xc7\x41\x08")
        rec = e7b.recover_msvc_ctor(binary, store_va)
        self.assertIsNone(rec["vptr"])
        self.assertIsNone(rec["deserializeVa"])


class WindowsAbiRegisterTests(unittest.TestCase):
    def test_win_abi_uses_rcx_rdx_r8_not_sysv(self):
        # Documented in driver; construct/deserialize set rcx/rdx/r8.
        src = Path(SCRIPTS / "rofl2_win_pe_packet_discover.py").read_text(encoding="utf-8")
        self.assertIn('self._set("rcx", obj)', src)
        self.assertIn('self._set("rdx", cursor_slot)', src)
        self.assertIn('self._set("r8", end)', src)
        # Must not use SysV rdi/rsi for Windows Deserialize entry
        self.assertNotIn('self._set("rdi", obj)', src)


class ConstructedObjectGateTests(unittest.TestCase):
    def test_drive_requires_factory_ok_before_path_accept(self):
        # Unit: fabricated path is rejected by construct validation contract
        pe = build_synthetic_pe64(text=_msvc_ctor_stub(opcode=980) + b"\x90" * 32)
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "x.exe"
            path.write_bytes(pe)
            binary = load_binary(path)
        emu = e7b.WinX64PacketEmu(binary)
        # Wrong expected vptr => construct fails; no fabricated accept
        text_va, _ = binary.text_bytes()
        ctor = text_va + 1  # after 0xcc in some builds; for synthetic, stub at text start
        # locate ctor start (lea)
        _, text = binary.text_bytes()
        ctor = text_va + text.find(b"\x48\x8d\x05")
        bad = emu.construct(
            ctor_va=ctor,
            object_size=32,
            expected_opcode=980,
            expected_vptr=0xDEADBEEF,
        )
        self.assertFalse(bad["ok"])
        self.assertTrue(bad.get("fabricatedRejected"))


class OfficialPeValidationTests(unittest.TestCase):
    @unittest.skipUnless(REAL_PE.is_file(), "Windows PE not present at /tmp")
    def test_real_pe_hash_and_coverage(self):
        binary = load_binary(REAL_PE)
        self.assertEqual(binary.platform, "windows")
        self.assertEqual(binary.arch, "x86_64")
        self.assertEqual(binary.sha256, e7b.EXPECTED_SHA256)
        stores = e7b.find_opcode_stores(binary)
        self.assertIn(980, stores)
        # Coverage vs a tiny synthetic opcode set
        rows, cov = e7b.scan_msvc_packet_types(binary, {980: 0, 556: 1, 107: 1})
        self.assertGreaterEqual(cov["coveredOpcodes"], 2)
        p980 = next(r for r in rows if int(r["opcode"]) == 980)
        self.assertEqual(p980.get("objectSize"), 32)


class ProvenanceTests(unittest.TestCase):
    def test_official_manifest_recorded_not_binary(self):
        p = e7b.official_provenance(size=1, sha256=e7b.EXPECTED_SHA256)
        self.assertEqual(p["manifestUrl"], e7b.OFFICIAL_MANIFEST_URL)
        self.assertIn("never commit", p["pathNote"])
        self.assertEqual(p["normalizedRoflBuild"], e7b.NORMALIZED_ROFL_BUILD)


if __name__ == "__main__":
    unittest.main()
