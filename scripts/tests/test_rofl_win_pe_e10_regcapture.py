#!/usr/bin/env python3
"""E10 tests: register capture helpers, train/holdout anti-overfit, axis swap, bounds."""
from __future__ import annotations

import json
import struct
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from rofl2_win_pe_e10_regcapture import (  # noqa: E402
    ACCEPT_MAX_MAX,
    ACCEPT_MAX_MEDIAN,
    ACCEPT_MAX_P95,
    ACCEPT_MIN_HEROES,
    ACCEPT_MIN_SAMPLES,
    SR_CENTER_X,
    SR_CENTER_Z,
    build_pair_candidates,
    evaluate_candidates,
    interpret_i16_pair,
    score_pair_list,
)


class BoundsTests(unittest.TestCase):
    def test_gate_constants(self):
        self.assertEqual(ACCEPT_MIN_SAMPLES, 80)
        self.assertEqual(ACCEPT_MIN_HEROES, 5)
        self.assertEqual(ACCEPT_MAX_MEDIAN, 120.0)
        self.assertEqual(ACCEPT_MAX_P95, 350.0)
        self.assertEqual(ACCEPT_MAX_MAX, 800.0)


class I16TransformTests(unittest.TestCase):
    def test_rejects_zero_center_only(self):
        raw = struct.pack("<hh", 0, 0)
        self.assertIsNone(interpret_i16_pair(raw))

    def test_accepts_nontrivial(self):
        raw = struct.pack("<hh", 100, -50)
        pair = interpret_i16_pair(raw)
        self.assertIsNotNone(pair)
        self.assertAlmostEqual(pair[0], 2 * 100 + SR_CENTER_X)
        self.assertAlmostEqual(pair[1], 2 * (-50) + SR_CENTER_Z)


class AntiOverfitTests(unittest.TestCase):
    def test_score_pair_requires_volume(self):
        rows = [
            {"netId": 0x400000AE + (i % 3), "time": float(i), "err": 50.0, "x": 1.0, "z": 2.0}
            for i in range(20)
        ]
        sc = score_pair_list(rows)
        self.assertEqual(sc["n"], 20)
        self.assertFalse(sc["ok"])  # <80 samples

    def test_false_match_high_error_fails(self):
        rows = [
            {
                "netId": 0x400000AE + (i % 6),
                "time": float(i),
                "err": 2000.0,
                "x": 1.0,
                "z": 2.0,
            }
            for i in range(100)
        ]
        sc = score_pair_list(rows)
        self.assertTrue(sc["n"] >= 80)
        self.assertFalse(sc["ok"])
        self.assertGreater(sc["median"], ACCEPT_MAX_MEDIAN)


class AxisSwapTests(unittest.TestCase):
    def test_build_pair_candidates_emits_swap_key(self):
        # One sample with x-hit and z-hit
        matches = [
            {
                "sampleKey": (351, 0, 100.0, 0x400000AE),
                "opcode": 351,
                "pc": 0x140001000,
                "site": "xmm0[0]",
                "value": 1000.0,
                "kind": "xmm",
                "axis": "x",
                "participantID": 1,
                "err": 10.0,
                "oracleX": 1000.0,
                "oracleZ": 2000.0,
                "time": 100.0,
                "netId": 0x400000AE,
            },
            {
                "sampleKey": (351, 0, 100.0, 0x400000AE),
                "opcode": 351,
                "pc": 0x140001008,
                "site": "xmm1[0]",
                "value": 2000.0,
                "kind": "xmm",
                "axis": "z",
                "participantID": 1,
                "err": 10.0,
                "oracleX": 1000.0,
                "oracleZ": 2000.0,
                "time": 100.0,
                "netId": 0x400000AE,
            },
        ]
        pairs = build_pair_candidates(matches)
        swaps = [k for k in pairs if k[5] is True]
        directs = [k for k in pairs if k[5] is False and k[6] == "direct"]
        self.assertTrue(directs)
        self.assertTrue(swaps)

    def test_evaluate_requires_holdout(self):
        # Train-only good pair must not win without holdout
        train = []
        for i in range(90):
            nid = 0x400000AE + (i % 6)
            train.append(
                {
                    "sampleKey": (420, i, float(100 + i), nid),
                    "opcode": 420,
                    "pc": 0x140010000,
                    "site": "xmm0[0]",
                    "value": 1000.0 + i,
                    "kind": "xmm",
                    "axis": "x",
                    "participantID": 1 + (i % 6),
                    "err": 20.0,
                    "oracleX": 1000.0 + i,
                    "oracleZ": 2000.0 + i,
                    "time": float(100 + i),
                    "netId": nid,
                }
            )
            train.append(
                {
                    "sampleKey": (420, i, float(100 + i), nid),
                    "opcode": 420,
                    "pc": 0x140010008,
                    "site": "xmm1[0]",
                    "value": 2000.0 + i,
                    "kind": "xmm",
                    "axis": "z",
                    "participantID": 1 + (i % 6),
                    "err": 20.0,
                    "oracleX": 1000.0 + i,
                    "oracleZ": 2000.0 + i,
                    "time": float(100 + i),
                    "netId": nid,
                }
            )
        res = evaluate_candidates(train, [])
        self.assertFalse(res["winnerFound"])


class ReportContractTests(unittest.TestCase):
    def test_report_if_present(self):
        path = Path("docs/rofl-research/movement-win-pe-e10-BR1-3264361042.json")
        if not path.is_file():
            self.skipTest("E10 report not generated")
        rep = json.loads(path.read_text())
        for k in (
            "evaluation",
            "trainCapture",
            "holdoutCapture",
            "browserSafe",
            "productEligible",
            "method",
            "blocker",
        ):
            self.assertIn(k, rep)
        self.assertFalse(rep["productEligible"])
        self.assertTrue(rep["method"]["noLearnedAffine"])
        self.assertFalse(rep["evaluation"]["winnerFound"] and rep.get("ok") is False)


if __name__ == "__main__":
    unittest.main()
