#!/usr/bin/env python3
"""E13 tests: keyframe header/cadence helpers, gates, blocker kinds, netId packing."""
from __future__ import annotations

import struct
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from rofl2_win_pe_e13_keyframe_positions import (  # noqa: E402
    ACCEPT_MAX_MAX,
    ACCEPT_MAX_MEDIAN,
    ACCEPT_MAX_P95,
    ACCEPT_MIN_HEROES,
    ACCEPT_MIN_SAMPLES,
    classify_blocker,
    keyframe_header_u8,
    keyframe_time,
    map_f32_pairs,
    score_errs,
)


class HeaderTests(unittest.TestCase):
    def test_keyframe_time_and_header(self):
        body = bytes([1]) + struct.pack("<f", 840.5) + b"\x00" * 16
        self.assertEqual(keyframe_header_u8(body), 1)
        self.assertAlmostEqual(keyframe_time(body) or 0.0, 840.5, places=3)

    def test_map_f32_pairs_finds_adjacent(self):
        raw = struct.pack("<ff", 1000.0, 2000.0) + b"\x00" * 8
        pairs = map_f32_pairs(raw)
        self.assertTrue(any(abs(x - 1000) < 1e-3 and abs(z - 2000) < 1e-3 for _, x, z in pairs))


class GateTests(unittest.TestCase):
    def test_constants(self):
        self.assertEqual(ACCEPT_MIN_SAMPLES, 80)
        self.assertEqual(ACCEPT_MIN_HEROES, 5)
        self.assertEqual(ACCEPT_MAX_MEDIAN, 120.0)
        self.assertEqual(ACCEPT_MAX_P95, 350.0)
        self.assertEqual(ACCEPT_MAX_MAX, 800.0)

    def test_false_match(self):
        sc = score_errs([2000.0] * 100, heroes=10)
        self.assertFalse(sc["ok"])
        self.assertGreater(sc["median"], ACCEPT_MAX_MEDIAN)


class BlockerTests(unittest.TestCase):
    def test_opaque(self):
        b = classify_blocker(
            structure={"ok": False},
            blob_qa={},
            block_evals=[],
            ghost={},
        )
        self.assertEqual(b["kind"], "keyframes_opaque")

    def test_no_floats(self):
        b = classify_blocker(
            structure={"ok": True},
            blob_qa={"mapPairCountTotal": 0, "modes": {}},
            block_evals=[],
            ghost={},
        )
        self.assertEqual(b["kind"], "keyframes_no_map_floats")

    def test_floats_not_oracle(self):
        b = classify_blocker(
            structure={"ok": True},
            blob_qa={
                "mapPairCountTotal": 100,
                "modes": {
                    "nearest": {
                        "winner": False,
                        "holdout": {"median": 500.0, "n": 20, "ok": False},
                    }
                },
            },
            block_evals=[],
            ghost={"dominantGhost491": {"heroBlocks": 102480}},
        )
        self.assertEqual(b["kind"], "keyframes_floats_not_oracle_positions")
        self.assertTrue(b.get("framingDiffersFromChunks"))


if __name__ == "__main__":
    unittest.main()
