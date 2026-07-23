#!/usr/bin/env python3
"""E15 tests: writer classification helpers, gates, blocker kinds."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from rofl2_win_pe_e15_position_writers import (  # noqa: E402
    ABS_GETTER_VA,
    ABS_POSITION_IN_PC,
    GET_POSITION_VA,
    PATH_SET_ABSOLUTE_VA,
    PATH_SET_POSITION_CORE_VA,
    POSITION_IN_PATH_CONTROLLER,
    classify_blocker,
)
from rofl2_win_pe_e14_position_getters import (  # noqa: E402
    ACCEPT_MAX_MAX,
    ACCEPT_MAX_MEDIAN,
    ACCEPT_MAX_P95,
    ACCEPT_MIN_HEROES,
    ACCEPT_MIN_SAMPLES,
    score_errs,
)


class ConstantTests(unittest.TestCase):
    def test_pinned_offsets(self):
        self.assertEqual(GET_POSITION_VA, 0x1403030C0)
        self.assertEqual(POSITION_IN_PATH_CONTROLLER, 0x20)
        self.assertEqual(PATH_SET_POSITION_CORE_VA, 0x140389200)
        self.assertEqual(PATH_SET_ABSOLUTE_VA, 0x1403891A0)
        self.assertEqual(ABS_POSITION_IN_PC, 0xA0)
        self.assertEqual(ABS_GETTER_VA, 0x140305350)


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


class BlockerTests(unittest.TestCase):
    def test_no_absolute_pc20(self):
        b = classify_blocker(
            scan={
                "absoluteWritersToPc20Count": 0,
                "absoluteSlot": {"offsetInPathController": "0xa0"},
            },
            proof={"slot20HoldsDirection": True, "a0HoldsAbsolute": True},
            evaluations=[
                {
                    "opcode": 908,
                    "source": "test",
                    "qa": {
                        "winnerFound": False,
                        "holdout": {"median": 191.0, "n": 50, "ok": False},
                    },
                }
            ],
        )
        self.assertEqual(b["kind"], "no_absolute_pc20_writers")
        self.assertEqual(b.get("alias"), "position_slot_not_absolute_store")
        self.assertEqual(b.get("relatedBlockerIfAskingA0"), "writers_values_not_oracle")

    def test_winner_on_a0(self):
        b = classify_blocker(
            scan={"absoluteWritersToPc20Count": 0},
            proof={"slot20HoldsDirection": True, "a0HoldsAbsolute": True},
            evaluations=[
                {
                    "opcode": 908,
                    "qa": {"winnerFound": True, "holdout": {"ok": True, "median": 50}},
                }
            ],
        )
        self.assertEqual(b["kind"], "none")


if __name__ == "__main__":
    unittest.main()
