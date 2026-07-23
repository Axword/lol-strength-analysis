#!/usr/bin/env python3
"""Tests for Phase B E6 x86-64 packet discovery + binary format abstraction."""
from __future__ import annotations

import hashlib
import struct
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from rofl2_binary_format import (  # noqa: E402
    build_synthetic_pe64,
    detect_format,
    load_binary,
    parse_pe64_sections,
    research_manifest,
)
from rofl2_movement_emulator_probe import (  # noqa: E402
    PathParseError,
    parse_compressed_path_packet,
)
from rofl2_movement_wire_scan import (  # noqa: E402
    ACCEPT_MAX_MAX_ERROR,
    ACCEPT_MAX_MEDIAN_ERROR,
    ACCEPT_MAX_P95_ERROR,
    ACCEPT_MIN_COMPARED_SAMPLES,
    ACCEPT_MIN_STABLE_ENTITIES,
)
import rofl2_x86_packet_discover as e6  # noqa: E402


def _factory_stub(*, size: int, opcode: int, call_rel: int = 0) -> bytes:
    """Minimal x86-64 factory micro-stub matching the scanner pattern."""
    # BF size ; E8 rel32 ; 66 C7 40 08 imm16 ; ... padding
    return (
        b"\xbf"
        + struct.pack("<I", size)
        + b"\xe8"
        + struct.pack("<i", call_rel)
        + b"\x66\xc7\x40\x08"
        + struct.pack("<H", opcode)
        + b"\x90" * 8
    )


class SyntheticPeAbstractionTests(unittest.TestCase):
    def test_detect_and_parse_pe64(self):
        stub = _factory_stub(size=48, opcode=980)
        pe = build_synthetic_pe64(text=stub + b"\x90" * 128)
        self.assertEqual(detect_format(pe), "pe")
        arch, segs, base = parse_pe64_sections(pe)
        self.assertEqual(arch, "x86_64")
        self.assertEqual(base, 0x140000000)
        self.assertTrue(any(s.name == ".text" for s in segs))

    def test_load_binary_pe_and_manifest_separation(self):
        pe = build_synthetic_pe64(text=_factory_stub(size=48, opcode=556) + b"\xcc" * 64)
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "fake-league.exe"
            path.write_bytes(pe)
            binary = load_binary(path)
        self.assertEqual(binary.format, "pe64")
        self.assertEqual(binary.platform, "windows")
        self.assertEqual(binary.arch, "x86_64")
        man = research_manifest(binary, patch="16.14", extra={"windowsStatus": "synthetic"})
        self.assertEqual(man["platform"], "windows")
        self.assertEqual(man["arch"], "x86_64")
        self.assertEqual(man["sha256"], hashlib.sha256(pe).hexdigest())
        self.assertNotEqual(man["platform"], "macos")

    def test_pe_factory_scan_finds_stub(self):
        stub = _factory_stub(size=48, opcode=0x15F)
        pe = build_synthetic_pe64(text=b"\x90" * 32 + stub + b"\x90" * 64)
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "fake.exe"
            path.write_bytes(pe)
            binary = load_binary(path)
        hits = e6.scan_factory_stubs(binary)
        ops = {int(h["opcode"]) for h in hits}
        self.assertIn(0x15F, ops)
        hit = next(h for h in hits if int(h["opcode"]) == 0x15F)
        self.assertEqual(int(hit["objectSize"]), 48)


class ConstructorFalsePositiveTests(unittest.TestCase):
    def test_isolated_mov_word_at_plus8_is_not_factory(self):
        # False positive bait: mov word [rax+8], imm without preceding new stub.
        bait = b"\x90" * 40 + b"\x66\xc7\x40\x08" + struct.pack("<H", 980) + b"\x90" * 40
        pe = build_synthetic_pe64(text=bait)
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "fp.exe"
            path.write_bytes(pe)
            binary = load_binary(path)
        hits = e6.scan_factory_stubs(binary)
        self.assertEqual(hits, [])

    def test_validate_ctor_coverage_id_matches_key(self):
        factories = [
            {"opcode": 10, "objectSize": 48, "stubVa": 1, "operatorNewVa": 2},
            {"opcode": 20, "objectSize": 32, "stubVa": 3, "operatorNewVa": 4},
        ]
        cov = e6.validate_ctor_coverage(factories, {10: 5, 20: 1, 99: 3})
        self.assertEqual(cov["roflOpcodes"], 3)
        self.assertEqual(cov["coveredOpcodes"], 2)
        self.assertEqual(cov["constructorIdMatchesKey"], 2)
        self.assertIn(99, cov["missingOpcodesSample"])


class ManifestPlatformHashTests(unittest.TestCase):
    def test_distinct_binaries_get_distinct_hashes(self):
        a = build_synthetic_pe64(text=_factory_stub(size=48, opcode=1))
        b = build_synthetic_pe64(text=_factory_stub(size=48, opcode=2))
        with tempfile.TemporaryDirectory() as td:
            pa = Path(td) / "a.exe"
            pb = Path(td) / "b.exe"
            pa.write_bytes(a)
            pb.write_bytes(b)
            ba = load_binary(pa)
            bb = load_binary(pb)
        self.assertNotEqual(ba.sha256, bb.sha256)
        ma = research_manifest(ba, patch="16.14")
        mb = research_manifest(bb, patch="16.14")
        self.assertEqual(ma["platform"], mb["platform"])
        self.assertNotEqual(ma["sha256"], mb["sha256"])


class StrictPathPacketAndQaGateTests(unittest.TestCase):
    def test_pathpacket_full_consume_gate(self):
        parsing_type = 1 << 1
        payload = struct.pack("<HIf", parsing_type, 0x400000AE, 325.0)
        payload += struct.pack("<HH", 0, 0)
        pp = parse_compressed_path_packet(payload)
        self.assertTrue(pp.full_consume)
        with self.assertRaises(PathParseError):
            parse_compressed_path_packet(payload + b"\x00")

    def test_acceptance_thresholds_documented(self):
        self.assertEqual(ACCEPT_MIN_STABLE_ENTITIES, 5)
        self.assertEqual(ACCEPT_MIN_COMPARED_SAMPLES, 80)
        self.assertEqual(ACCEPT_MAX_MEDIAN_ERROR, 120.0)
        self.assertEqual(ACCEPT_MAX_P95_ERROR, 350.0)
        self.assertEqual(ACCEPT_MAX_MAX_ERROR, 800.0)


class MachOx86ScanSmokeTests(unittest.TestCase):
    """Optional: live League binary present → thin + factory scan smoke."""

    LEAGUE = Path(
        "/Applications/League of Legends.app/Contents/LoL/Game/"
        "LeagueofLegends.app/Contents/MacOS/LeagueofLegends"
    )

    @unittest.skipUnless(LEAGUE.is_file(), "League binary not installed")
    def test_thin_x86_factory_scan_covers_many_opcodes(self):
        with tempfile.TemporaryDirectory() as td:
            binary = load_binary(self.LEAGUE, prefer_arch="x86_64", work_dir=Path(td))
        self.assertEqual(binary.format, "macho64")
        self.assertEqual(binary.arch, "x86_64")
        self.assertEqual(binary.platform, "macos")
        hits = e6.scan_factory_stubs(binary)
        self.assertGreaterEqual(len(hits), 100)
        ops = {int(h["opcode"]) for h in hits}
        # Prior-art id exists on 16.14 x86 even if ROFL has 0 blocks
        self.assertIn(980, ops)
        man = research_manifest(binary, patch="16.14")
        self.assertEqual(man["platform"], "macos")
        self.assertEqual(len(man["sha256"]), 64)


if __name__ == "__main__":
    unittest.main()
