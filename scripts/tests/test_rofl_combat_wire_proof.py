#!/usr/bin/env python3
"""Unit tests for Gate B1 combat wire proof + PE table helpers."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import rofl2_combat_wire_proof as proof  # noqa: E402
from rofl_combat_wire_table import (  # noqa: E402
    PROVEN_COMBAT_WIRE_MAP_16_14,
    REFUTED_PRIMARY1_HYPOTHESIS,
    filter_combat_fields,
    primary_from_w3_mask,
    value_in_plausible_range,
)


class CombatWireTableUnitTests(unittest.TestCase):
    def test_w3_mask_to_primary(self):
        self.assertEqual(primary_from_w3_mask(4), 2)
        self.assertEqual(primary_from_w3_mask(8), 3)
        self.assertEqual(primary_from_w3_mask(32), 5)

    def test_refutes_primary1_hypothesis(self):
        self.assertNotEqual(
            set(PROVEN_COMBAT_WIRE_MAP_16_14.keys()),
            set(REFUTED_PRIMARY1_HYPOTHESIS.keys()),
        )
        self.assertEqual(PROVEN_COMBAT_WIRE_MAP_16_14[(2, 3)], "mBaseAttackDamage")
        self.assertEqual(PROVEN_COMBAT_WIRE_MAP_16_14[(2, 7)], "mArmor")

    def test_filter_drops_denormal_mr(self):
        named = filter_combat_fields(
            {
                (2, 3): 65.0,
                (2, 7): 40.0,
                (2, 8): 9.1e-44,  # denormal — reject
                (2, 18): 1.1,
            }
        )
        self.assertIn("mBaseAttackDamage", named)
        self.assertNotIn("mSpellBlock", named)
        named2 = filter_combat_fields({(2, 8): 32.0})
        self.assertEqual(named2["mSpellBlock"], 32.0)


class CombatWireProofTests(unittest.TestCase):
    def test_evaluate_marks_proven_with_pe_and_plausible(self):
        raw = {
            "indexCounts": {
                "2,3": 5,
                "2,7": 5,
                "2,8": 5,
                "2,12": 5,
                "2,14": 5,
                "2,18": 5,
                "3,17": 5,
                "3,21": 5,
            },
            "indexValueSamples": {
                "2,3": [65.0],
                "2,7": [40.0],
                "2,8": [30.0],
                "2,12": [20.0],
                "2,14": [50.0],
                "2,18": [1.1],
                "3,17": [10.0],
                "3,21": [0.2],
            },
        }
        pe = {
            "wireTable": {"hpPositiveControl": {"ok": True}},
            "registrarCombatSlots": [
                {"primary": p, "secondary": s, "name": name}
                for (p, s), name in PROVEN_COMBAT_WIRE_MAP_16_14.items()
            ],
        }
        hyp = proof._evaluate_proven_map(raw, pe)
        self.assertGreaterEqual(hyp["provenIndexCount"], 5)
        self.assertTrue(all(hyp["furFieldProvenUnderPeTable"].values()))
        self.assertTrue(hyp["hpPositiveControlOk"])

    def test_durable_report_shape_when_present(self):
        report_path = Path("docs/rofl-research/combat-wire-proof-BR1-3264361042.json")
        if not report_path.is_file():
            self.skipTest("combat wire proof report missing")
        import json

        report = json.loads(report_path.read_text(encoding="utf-8"))
        if report.get("combatTrusted") is True:
            self.assertTrue(report.get("wireTableProven"))
            self.assertTrue(report.get("ok"))
            self.assertIsNone(report.get("blocker"))
            fur = (report.get("hypothesis") or {}).get("furFieldProvenUnderPeTable") or {}
            self.assertTrue(all(fur.get(k) for k in proof.FUR_COMBAT_TARGETS))
        else:
            self.assertFalse(report.get("combatStatsKnownWouldEmit"))
            self.assertIsNotNone(report.get("blocker"))


class DensifyHpFrameGridTests(unittest.TestCase):
    def test_omits_frames_before_first_all10(self):
        units = [
            {"netId": 0x400000AE + i, "mHP": 500.0, "mMaxHP": 600.0, "mMaxHPExplicit": True}
            for i in range(10)
        ]
        carried = {80_000: units, 81_000: units}
        samples = proof.densify_hp_onto_replay_api_frames(
            frame_times_ms=[60_000, 77_000, 80_000, 81_000],
            first_all10_ms=77_278,
            carried_by_frame=carried,
        )
        self.assertEqual([s["gameTimeMs"] for s in samples], [80_000, 81_000])
        self.assertEqual(len(samples[0]["units"]), 10)


if __name__ == "__main__":
    unittest.main()
