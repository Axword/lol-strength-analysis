#!/usr/bin/env python3
"""E9 tests: framing parity helpers, position classification, gold regression, gates."""
from __future__ import annotations

import json
import struct
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from rofl_replication_apply import (  # noqa: E402
    POS_PRIMARY,
    POS_SECONDARY_X,
    POS_SECONDARY_Z,
    apply_fields_to_state,
    is_map_position_pair,
    parse_replication_vector,
)
from rofl2_replication_position_e9 import (  # noqa: E402
    ACCEPT_MAX_MAX,
    ACCEPT_MAX_MEDIAN,
    ACCEPT_MAX_P95,
    ACCEPT_MIN_COMPARED,
    DESERIALIZE_CURSOR_AFTER_TYPE,
    MARKER_BYTE,
    RECONSTRUCTED_PREFIX,
    TYPE_BYTE,
    TYPE_107,
    classify_containment,
    extract_position_updates,
    frame_wire_payload,
    gold_regression_check,
)


class FramingTests(unittest.TestCase):
    def test_reconstructed_prefix_constants(self):
        self.assertEqual(TYPE_107, 107)
        self.assertEqual(TYPE_BYTE, b"\x6b")
        self.assertEqual(MARKER_BYTE, b"\xa6")
        self.assertEqual(RECONSTRUCTED_PREFIX, b"\x6b\xa6")
        self.assertEqual(DESERIALIZE_CURSOR_AFTER_TYPE, 1)

    def test_frame_wire_payload(self):
        wire = b"\x01\x02\x03"
        self.assertEqual(frame_wire_payload(wire), b"\x6b\xa6\x01\x02\x03")

    def test_containment_transformed_fail_closed(self):
        body = b"\xa6" + b"\x00" * 20
        blob = b"\x01\xae\x00\x00\x40" + b"\x00" * 8
        c = classify_containment(body, blob)
        self.assertTrue(c["transformed"])
        self.assertFalse(c["exactEquality"])
        self.assertFalse(c["suffix"])

    def test_malformed_empty_blob(self):
        c = classify_containment(b"abc", b"")
        self.assertFalse(c["exactEquality"])
        self.assertTrue(c["transformed"] or c["findOffset"] is None)


class PositionClassificationTests(unittest.TestCase):
    def test_indices_are_primary0_secondary01(self):
        self.assertEqual(POS_PRIMARY, 0)
        self.assertEqual(POS_SECONDARY_X, 0)
        self.assertEqual(POS_SECONDARY_Z, 1)

    def test_map_pair_bounds(self):
        self.assertTrue(is_map_position_pair(44.0, 14346.0))
        self.assertFalse(is_map_position_pair(float("nan"), 100.0))
        self.assertFalse(is_map_position_pair(50000.0, 100.0))

    def test_extract_requires_proven_hero_and_pair(self):
        # AE hero with (0,0)/(0,1) map coords
        x, z = 1200.5, 3400.25
        blob = (
            bytes([0x01])
            + struct.pack("<I", 0x400000AE)
            + struct.pack("<I", 0x3)
            + bytes([8])
            + struct.pack("<ff", x, z)
        )
        rows = extract_position_updates(blob, time_s=10.5)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["netId"], 0x400000AE)
        self.assertAlmostEqual(rows[0]["x"], x)
        self.assertAlmostEqual(rows[0]["z"], z)

    def test_non_hero_netid_ignored(self):
        blob = (
            bytes([0x01])
            + struct.pack("<I", 0x40000100)
            + struct.pack("<I", 0x3)
            + bytes([8])
            + struct.pack("<ff", 100.0, 200.0)
        )
        self.assertEqual(extract_position_updates(blob, time_s=1.0), [])


class GoldRegressionTests(unittest.TestCase):
    def test_map_range_pair_never_becomes_gold(self):
        state = {}
        x, z = 44.0, 14346.0
        blob = (
            bytes([0x01])
            + struct.pack("<I", 0x400000AF)
            + struct.pack("<I", 0x3)
            + bytes([8])
            + struct.pack("<ff", x, z)
        )
        for net_id, fields in parse_replication_vector(blob):
            apply_fields_to_state(state, net_id=net_id, fields=fields, time_s=1.0)
        st = state[0x400000AF]
        self.assertIsNone(getattr(st, "mGold", None))
        self.assertIsNone(getattr(st, "mGoldTotal", None))
        self.assertFalse(hasattr(st, "mPosX") and getattr(st, "mPosX") is not None)

    def test_gold_regression_helper(self):
        updates = [
            {"time": 1.0, "netId": 0x400000AE, "x": 500.0, "z": 600.0},
            {"time": 1.5, "netId": 0x400000AF, "x": 700.0, "z": 800.0},
        ]
        r = gold_regression_check(updates)
        self.assertTrue(r["ok"])
        self.assertEqual(r["goldEmissions"], 0)
        self.assertEqual(r["positionStateEmissions"], 0)
        self.assertTrue(r["fieldIndices"]["rejectedPositionClaim"])


class GateConstantTests(unittest.TestCase):
    def test_qa_thresholds(self):
        self.assertEqual(ACCEPT_MIN_COMPARED, 500)
        self.assertEqual(ACCEPT_MAX_MEDIAN, 120.0)
        self.assertEqual(ACCEPT_MAX_P95, 350.0)
        self.assertEqual(ACCEPT_MAX_MAX, 800.0)


class ReportContractTests(unittest.TestCase):
    def test_report_schema_keys_if_present(self):
        path = Path("docs/rofl-research/movement-replication-e9-BR1-3264361042.json")
        if not path.is_file():
            self.skipTest("E9 report not generated yet")
        rep = json.loads(path.read_text())
        for k in (
            "framingParity",
            "positionFieldIndices",
            "oracleQA",
            "furSemantic",
            "meetInMiddle",
            "identity",
            "browserSafe",
            "productEligible",
            "cadence",
            "blobOracleScan",
            "drift",
        ):
            self.assertIn(k, rep)
        self.assertFalse(rep["productEligible"])
        self.assertFalse(rep.get("positionClaimProven"))
        self.assertFalse(rep["positionFieldIndices"]["proven"])
        self.assertIn("disallowedComparisons", rep["meetInMiddle"])
        self.assertFalse(rep["meetInMiddle"]["furRofl"]["searched"])
        self.assertEqual(rep["framingParity"]["framing"]["reconstructedPrefixHex"], "6ba6")
        self.assertFalse(rep["pureDecoder"]["byteParityWithUnicornBlob"])
        self.assertEqual(rep["blobOracleScan"]["hits"], 0)


if __name__ == "__main__":
    unittest.main()
