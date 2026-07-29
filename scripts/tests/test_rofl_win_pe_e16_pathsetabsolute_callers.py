#!/usr/bin/env python3
"""E16 tests: PathSetAbsolute constants, blocker taxonomy, gates."""
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
    PATH_SET_ABSOLUTE_VA,
)
from rofl2_win_pe_e16_pathsetabsolute_callers import (  # noqa: E402
    INTEGRATOR_ADD_VA,
    PATH_APPLY_VA,
    UPDATE_PC_VA,
    classify_blocker,
)
from rofl2_win_pe_e14_position_getters import (  # noqa: E402
    ACCEPT_MAX_MEDIAN,
    ACCEPT_MIN_HEROES,
    ACCEPT_MIN_SAMPLES,
    score_errs,
)


class ConstantTests(unittest.TestCase):
    def test_pinned(self):
        self.assertEqual(PATH_SET_ABSOLUTE_VA, 0x1403891A0)
        self.assertEqual(ABS_GETTER_VA, 0x140305350)
        self.assertEqual(ABS_POSITION_IN_PC, 0xA0)
        self.assertEqual(UPDATE_PC_VA, 0x14036DDB0)
        self.assertEqual(PATH_APPLY_VA, 0x14038AC80)
        self.assertEqual(INTEGRATOR_ADD_VA, 0x1406B8E70)


class GateTests(unittest.TestCase):
    def test_gates(self):
        self.assertEqual(ACCEPT_MIN_SAMPLES, 80)
        self.assertEqual(ACCEPT_MIN_HEROES, 5)
        self.assertEqual(ACCEPT_MAX_MEDIAN, 120.0)
        self.assertFalse(score_errs([500.0] * 100, heroes=10)["ok"])


class BlockerTests(unittest.TestCase):
    def test_integrated_not_stored(self):
        b = classify_blocker(
            callers=[{"kind": "hero_pathcontroller_snap"}],
            packet_reach={
                58: {"deserCallsPathSetAbsolute": False},
                908: {"deserCallsPathSetAbsolute": False},
            },
            integrators=[{"funcGuess": "0x1406b8e70"}],
            integ_proof={"addedDelta": True},
            evaluations=[
                {
                    "opcode": 908,
                    "qa": {
                        "winnerFound": False,
                        "holdout": {"median": 191.0, "n": 50, "ok": False},
                    },
                }
            ],
            waypoints_decoded=False,
        )
        self.assertEqual(b["kind"], "position_is_integrated_not_stored")
        self.assertEqual(b["integrationSimulation"], "integration_requires_full_sim")
        self.assertEqual(b["secondary"], "pathsetabsolute_callers_not_rofl_reachable")

    def test_not_reachable(self):
        b = classify_blocker(
            callers=[{"kind": "unknown"}],
            packet_reach={58: {"deserCallsPathSetAbsolute": False}},
            integrators=[],
            integ_proof={},
            evaluations=[],
            waypoints_decoded=False,
        )
        self.assertEqual(b["kind"], "pathsetabsolute_callers_not_rofl_reachable")


if __name__ == "__main__":
    unittest.main()
