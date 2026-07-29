#!/usr/bin/env python3
"""E17 tests: path integrator helpers, gates, blocker taxonomy."""
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
    score_errs,
)
from rofl2_win_pe_e15_position_writers import (  # noqa: E402
    ABS_GETTER_VA,
    ABS_POSITION_IN_PC,
    PATH_SET_ABSOLUTE_VA,
)
from rofl2_win_pe_e16_pathsetabsolute_callers import (  # noqa: E402
    PATH_APPLY_VA,
    UPDATE_PC_VA,
)
from rofl2_win_pe_e17_path_integrator import (  # noqa: E402
    INTEGRATE_DT_S,
    OPCODE_SET_MOVEMENT_DRIVER,
    classify_blocker,
    integrate_path_at_time,
    sample_integrated_timeline,
)


class ConstantTests(unittest.TestCase):
    def test_pinned(self):
        self.assertEqual(PATH_SET_ABSOLUTE_VA, 0x1403891A0)
        self.assertEqual(ABS_GETTER_VA, 0x140305350)
        self.assertEqual(ABS_POSITION_IN_PC, 0xA0)
        self.assertEqual(UPDATE_PC_VA, 0x14036DDB0)
        self.assertEqual(PATH_APPLY_VA, 0x14038AC80)
        self.assertEqual(OPCODE_SET_MOVEMENT_DRIVER, 1104)
        self.assertAlmostEqual(INTEGRATE_DT_S, 1.0 / 30.0)


class GateTests(unittest.TestCase):
    def test_gates(self):
        self.assertEqual(ACCEPT_MIN_SAMPLES, 80)
        self.assertEqual(ACCEPT_MIN_HEROES, 5)
        self.assertEqual(ACCEPT_MAX_MEDIAN, 120.0)
        self.assertEqual(ACCEPT_MAX_P95, 350.0)
        self.assertEqual(ACCEPT_MAX_MAX, 800.0)
        self.assertFalse(score_errs([500.0] * 100, heroes=10)["ok"])


class IntegrateTests(unittest.TestCase):
    def test_walk_along_segment(self):
        wps = [(0.0, 0.0), (300.0, 0.0)]
        # 1s at 300 units/s → end of first segment
        pos = integrate_path_at_time(wps, 300.0, elapsed_s=1.0, dt=1.0 / 30.0)
        self.assertIsNotNone(pos)
        assert pos is not None
        self.assertAlmostEqual(pos[0], 300.0, delta=5.0)
        self.assertAlmostEqual(pos[1], 0.0, delta=1.0)

    def test_single_waypoint(self):
        pos = integrate_path_at_time([(1000.0, 2000.0)], 400.0, elapsed_s=2.0)
        self.assertEqual(pos, (1000.0, 2000.0))

    def test_timeline_samples(self):
        rows = sample_integrated_timeline(
            t0=10.0,
            waypoints=[(100.0, 100.0), (500.0, 100.0)],
            speed=200.0,
            param=1073741998,
            horizon_s=2.0,
            sample_hz=1.0,
        )
        self.assertEqual(len(rows), 3)  # t=10,11,12
        self.assertEqual(rows[0]["t"], 10.0)
        self.assertEqual(rows[0]["param"], 1073741998)


class BlockerTests(unittest.TestCase):
    def test_waypoints_not_decoded(self):
        b = classify_blocker(
            framing_ok=True,
            driver={
                "structurallyDecodedCount": 0,
                "pathBlobRecovered": False,
                "speedRecovered": False,
                "netIdRecovered": False,
            },
            integrated=[],
            qa={"winnerFound": False},
            neg_908={"qa": {"winnerFound": False}},
            face={"expectPositionCarrier": False},
        )
        self.assertEqual(b["kind"], "waypoints_not_structurally_decoded")

    def test_driver_incomplete(self):
        b = classify_blocker(
            framing_ok=True,
            driver={
                "structurallyDecodedCount": 0,
                "pathBlobRecovered": True,
                "speedRecovered": False,
                "netIdRecovered": True,
            },
            integrated=[],
            qa={"winnerFound": False},
            neg_908={"qa": {"winnerFound": False}},
            face={"expectPositionCarrier": False},
        )
        self.assertEqual(b["kind"], "driver_state_incomplete")

    def test_full_sim(self):
        b = classify_blocker(
            framing_ok=True,
            driver={
                "structurallyDecodedCount": 2,
                "pathBlobRecovered": True,
                "speedRecovered": True,
                "netIdRecovered": True,
            },
            integrated=[{"t": 1.0}] * 10,
            qa={"winnerFound": False, "holdout": {"median": 400.0, "ok": False}},
            neg_908={"qa": {"winnerFound": False}},
            face={"expectPositionCarrier": False},
        )
        self.assertEqual(b["kind"], "integration_requires_full_sim")

    def test_framing(self):
        b = classify_blocker(
            framing_ok=False,
            driver={},
            integrated=[],
            qa={},
            neg_908={},
            face={},
        )
        self.assertEqual(b["kind"], "reconstruction_invalid")


if __name__ == "__main__":
    unittest.main()
