#!/usr/bin/env python3
"""Tests for Phase B E5 ROFL-X structural movement scan."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import rofl2_movement_structural_scan as e5  # noqa: E402
from rofl2_movement_emulator_probe import (  # noqa: E402
    PathParseError,
    parse_compressed_path_packet,
)
import struct


class FactoryScanHelpersTests(unittest.TestCase):
    def test_group_by_deserialize_collapses_duplicates(self):
        rows = [
            {"opcode": 1, "deserialize": "0xabc"},
            {"opcode": 2, "deserialize": "0xabc"},
            {"opcode": 3, "deserialize": "0xdef"},
        ]
        g = e5.group_by_deserialize(rows)
        self.assertEqual(len(g["0xabc"]), 2)
        self.assertEqual(len(g["0xdef"]), 1)

    def test_score_requires_alloc_then_ptr_for_byte_buffer(self):
        strong = e5.score_from_features(
            {"str_x_18": 1, "str_w_20": 1, "stride18": 0, "alloc_then_str_x18": 1}
        )
        self.assertTrue(strong["byteBufferCandidate"])
        self.assertGreaterEqual(strong["score"], 10)

        weak = e5.score_from_features(
            {"str_x_18": 1, "str_w_20": 1, "stride18": 0, "alloc_then_str_x18": 0}
        )
        self.assertFalse(weak["byteBufferCandidate"])
        self.assertTrue(weak["weakByteBufferShape"])


class SignatureFalsePositiveTests(unittest.TestCase):
    def test_scalar_or_float_at_0x18_is_not_movement(self):
        fp = e5.score_from_features(e5.false_positive_signature_fixture())
        self.assertFalse(fp["byteBufferCandidate"])
        self.assertFalse(fp.get("alloc_then_str_x18"))

    def test_vector_stride_rejected(self):
        # Matches opcode-855 shape: alloc→+0x18 but element stride 0x18.
        vec = e5.score_from_features(
            {"str_x_18": 1, "str_w_20": 1, "stride18": 2, "alloc_then_str_x18": 1}
        )
        self.assertTrue(vec["vectorStrideRejected"])
        self.assertFalse(vec["byteBufferCandidate"])
        self.assertLess(vec["score"], 10)


class AllocatorHookManifestTests(unittest.TestCase):
    def test_vector_alloc_vas_are_explicit(self):
        self.assertEqual(e5.VECTOR_ALLOC_VA, 0x10162EB4C)
        self.assertEqual(e5.VECTOR_FREE_VA, 0x10162EBAC)
        self.assertEqual(e5.PTR_OFF, 0x18)
        self.assertEqual(e5.SIZE_OFF, 0x20)
        self.assertEqual(e5.ROFLX_OBJECT_SIZE, 48)


class StrictPathPacketTests(unittest.TestCase):
    def test_pathpacket_full_consume_gate(self):
        # Minimal 1-waypoint absolute path
        parsing_type = 1 << 1  # count=1
        payload = struct.pack("<HIf", parsing_type, 0x400000AE, 325.0)
        payload += struct.pack("<HH", 0, 0)  # encoded coords
        pp = parse_compressed_path_packet(payload)
        self.assertTrue(pp.full_consume)
        with self.assertRaises(PathParseError):
            parse_compressed_path_packet(payload + b"\x00")


if __name__ == "__main__":
    unittest.main()
