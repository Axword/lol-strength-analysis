#!/usr/bin/env python3
"""E14 tests: GetPosition slot constants, gates, blocker classification."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from rofl2_win_pe_e14_position_getters import (  # noqa: E402
    ACCEPT_MAX_MAX,
    ACCEPT_MAX_MEDIAN,
    ACCEPT_MAX_P95,
    ACCEPT_MIN_HEROES,
    ACCEPT_MIN_SAMPLES,
    GET_POSITION_VA,
    HERO_POSITION_ABS,
    PATH_CONTROLLER_IN_HERO,
    POSITION_IN_PATH_CONTROLLER,
    classify_blocker,
    score_errs,
)


class SlotConstantTests(unittest.TestCase):
    def test_hero_absolute_matches_pc_plus_slot(self):
        self.assertEqual(PATH_CONTROLLER_IN_HERO, 0x28D0)
        self.assertEqual(POSITION_IN_PATH_CONTROLLER, 0x20)
        self.assertEqual(HERO_POSITION_ABS, PATH_CONTROLLER_IN_HERO + POSITION_IN_PATH_CONTROLLER)
        self.assertEqual(GET_POSITION_VA, 0x1403030C0)


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
    def test_no_getter_slots(self):
        b = classify_blocker(
            discovery={"getPositionVa": None, "leaRaxRcx20RetCount": 0},
            geometry={},
            use_vt={},
            evaluations=[],
        )
        self.assertEqual(b["kind"], "no_position_getter_slots")

    def test_heap_not_emulatable_geometry(self):
        b = classify_blocker(
            discovery={"getPositionVa": hex(GET_POSITION_VA), "leaRaxRcx20RetCount": 1},
            geometry={"ok": False},
            use_vt={},
            evaluations=[],
        )
        self.assertEqual(b["kind"], "pathcontroller_heap_not_emulatable")

    def test_heap_not_emulatable_no_samples(self):
        b = classify_blocker(
            discovery={"getPositionVa": hex(GET_POSITION_VA), "leaRaxRcx20RetCount": 1},
            geometry={"ok": True},
            use_vt={"58": {}},
            evaluations=[{"getterSamples": 0, "qa": {}}],
        )
        self.assertEqual(b["kind"], "pathcontroller_heap_not_emulatable")

    def test_values_not_oracle(self):
        b = classify_blocker(
            discovery={"getPositionVa": hex(GET_POSITION_VA), "leaRaxRcx20RetCount": 1},
            geometry={"ok": True},
            use_vt={"58": {}},
            evaluations=[
                {
                    "opcode": 908,
                    "source": "test",
                    "getterSamples": 40,
                    "qa": {
                        "winnerFound": False,
                        "holdout": {"median": 191.0, "n": 40, "ok": False},
                    },
                }
            ],
        )
        self.assertEqual(b["kind"], "getters_found_but_values_not_oracle")
        self.assertEqual(b["bestNearMiss"]["opcode"], 908)


if __name__ == "__main__":
    unittest.main()
