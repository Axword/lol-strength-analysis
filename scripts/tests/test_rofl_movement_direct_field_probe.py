#!/usr/bin/env python3
"""Tests for Phase B E4 channel-351 direct-field probe."""
from __future__ import annotations

import struct
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import rofl2_movement_decode as mov  # noqa: E402
import rofl2_movement_direct_field_probe as e4  # noqa: E402


class FieldExtractionTests(unittest.TestCase):
    def test_extract_object_fields_layout(self):
        obj = bytearray(0x30)
        struct.pack_into("<I", obj, 0x8, 0x15F)
        struct.pack_into("<I", obj, 0xC, 0x4000006C)
        struct.pack_into("<I", obj, 0x10, 0x0C0C0C44)
        struct.pack_into("<I", obj, 0x14, 0x5555551E)
        obj[0x18] = 0x66
        fields = e4.extract_object_fields(bytes(obj))
        self.assertEqual(fields["storedType"], 0x15F)
        self.assertEqual(fields["innerEntityId"], 0x4000006C)
        self.assertEqual(fields["field10"], 0x0C0C0C44)
        self.assertEqual(fields["field14"], 0x5555551E)
        self.assertEqual(fields["byte18"], 0x66)

    def test_schema_from_payload_bits_3_5(self):
        # bits 3..5 = 5 → schema 5
        self.assertEqual(e4.schema_from_payload(bytes([(5 << 3) | 0x7])), 5)
        self.assertEqual(e4.schema_from_payload(b"\x00"), 0)

    def test_interpretations_are_structure_justified(self):
        inter = e4.field_interpretations(0x12345678, 0x0A0B0C0D)
        self.assertIn("f10_u16_pair", inter)
        self.assertIn("f10_i16_map", inter)
        self.assertIn("w15_packed14", inter)
        self.assertEqual(inter["f10_u16_pair"], (0x5678, 0x1234))


class FalseCorrelationTests(unittest.TestCase):
    def test_false_correlation_guard_fails_acceptance(self):
        oracle = [
            {
                "time": float(t),
                "participants": [
                    {"participantID": i + 1, "x": 1000.0 + i * 100, "z": 2000.0 + i * 100}
                    for i in range(10)
                ],
            }
            for t in range(60, 80)
        ]
        rows = e4.false_correlation_guard_samples()
        scored = e4.score_coord_hypothesis(rows, oracle, key="f10_i16_map")
        self.assertFalse(scored.get("accepted"))
        # Either insufficient assignment quality or high spatial error.
        qa = scored.get("oracleQa") or {}
        if qa.get("comparedSamples"):
            self.assertTrue(
                (qa.get("medianError") or 0) > e4.ACCEPT_MAX_MEDIAN_ERROR
                or not qa.get("methodPassed")
                or int(qa.get("assignmentCount") or 0) < e4.ACCEPT_MIN_STABLE_ENTITIES
            )


class LutManifestSeparationTests(unittest.TestCase):
    def test_no_hardcoded_fallback_lut_bytes_in_module(self):
        src = Path(mov.__file__).read_text(encoding="utf-8")
        self.assertNotIn("_FALLBACK_LUT", src)
        self.assertIn("GENERATED_LUT_BIN", src)
        lut, prov = mov.load_generated_lut_cache()
        self.assertEqual(len(lut), 256)
        self.assertIn("generated_cache", prov)

    def test_pure_decoder_stub_not_browser_safe_when_unproven(self):
        cfg = e4.pure_decoder_stub(movement_proven=False)
        self.assertFalse(cfg["browserSafe"])
        self.assertFalse(cfg["productEligible"])
        self.assertFalse(cfg["movementProven"])


if __name__ == "__main__":
    unittest.main()
