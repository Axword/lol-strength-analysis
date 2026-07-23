#!/usr/bin/env python3
"""E12 tests: marker selection, pair scoring, gates, false match, blocker kinds."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from rofl2_win_pe_e11_reconstructed_drive import (  # noqa: E402
    MARKER_1,
    MARKER_2,
    encode_type,
)
from rofl2_win_pe_e12_recon_opcode_scan import (  # noqa: E402
    ACCEPT_MAX_MAX,
    ACCEPT_MAX_MEDIAN,
    ACCEPT_MAX_P95,
    ACCEPT_MIN_HEROES,
    ACCEPT_MIN_SAMPLES,
    classify_blocker,
    extract_offset_pairs,
    score_pair_key,
)


class FramingHelperTests(unittest.TestCase):
    def test_encode_type_58_single_byte(self):
        self.assertEqual(encode_type(58), bytes([58]))

    def test_markers(self):
        self.assertEqual(MARKER_1, b"\xa6")
        self.assertEqual(MARKER_2, b"\xc6\xfa")


class PairExtractTests(unittest.TestCase):
    def test_adjacent_offsets(self):
        writes = [
            {"off": 16, "f": 1000.0},
            {"off": 20, "f": 2000.0},
            {"off": 24, "f": 3000.0},
        ]
        pairs = extract_offset_pairs(writes)
        keys = {(a, b) for a, b, _, _ in pairs}
        self.assertIn((16, 20), keys)
        self.assertIn((16, 24), keys)
        self.assertIn((20, 24), keys)


class GateTests(unittest.TestCase):
    def test_constants(self):
        self.assertEqual(ACCEPT_MIN_SAMPLES, 80)
        self.assertEqual(ACCEPT_MIN_HEROES, 5)
        self.assertEqual(ACCEPT_MAX_MEDIAN, 120.0)
        self.assertEqual(ACCEPT_MAX_P95, 350.0)
        self.assertEqual(ACCEPT_MAX_MAX, 800.0)

    def test_false_match_high_error(self):
        oracle = [
            {
                "time": float(t),
                "participants": [
                    {"participantID": 1, "x": 1000.0, "z": 2000.0},
                    {"participantID": 2, "x": 3000.0, "z": 4000.0},
                ],
            }
            for t in range(100, 200)
        ]
        caps = []
        for i, t in enumerate(range(100, 200)):
            caps.append(
                {
                    "t": float(t),
                    "param": 0x400000AE + (i % 6),
                    "writes": [
                        {"off": 16, "f": 9000.0},
                        {"off": 20, "f": 9000.0},
                    ],
                }
            )
        sc = score_pair_key(caps, oracle, 16, 20, swap=False)
        self.assertGreaterEqual(sc["n"], 80)
        self.assertFalse(sc["ok"])
        self.assertGreater(sc["median"], ACCEPT_MAX_MEDIAN)

    def test_axis_swap_changes_error(self):
        oracle = [
            {
                "time": 100.0,
                "participants": [{"participantID": 1, "x": 1000.0, "z": 2000.0}],
            }
        ]
        caps = [
            {
                "t": 100.0,
                "param": 0x400000AE,
                "writes": [{"off": 16, "f": 1000.0}, {"off": 20, "f": 2000.0}],
            }
        ]
        direct = score_pair_key(caps, oracle, 16, 20, swap=False)
        swapped = score_pair_key(caps, oracle, 16, 20, swap=True)
        self.assertLess(direct["median"], swapped["median"])


class BlockerTests(unittest.TestCase):
    def test_no_framing(self):
        b = classify_blocker(
            framing_ok=0,
            framing_fail=5,
            with_writes=0,
            evaluated=[],
            seg_types={1: 55},
        )
        self.assertEqual(b["kind"], "no_multi_hero_framing")

    def test_helpers_incomplete(self):
        b = classify_blocker(
            framing_ok=10,
            framing_fail=0,
            with_writes=0,
            evaluated=[],
            seg_types={1: 55, 2: 28},
        )
        self.assertEqual(b["kind"], "helpers_incomplete_beyond_58")

    def test_position_not_in_chunks(self):
        b = classify_blocker(
            framing_ok=10,
            framing_fail=0,
            with_writes=3,
            evaluated=[
                {
                    "opcode": 908,
                    "offX": 16,
                    "offZ": 20,
                    "swap": False,
                    "train": {"median": 140.0, "ok": False},
                    "holdout": {"median": 191.0, "ok": False},
                }
            ],
            seg_types={1: 55, 2: 28},
        )
        self.assertEqual(b["kind"], "position_not_in_chunk_packets")


if __name__ == "__main__":
    unittest.main()
