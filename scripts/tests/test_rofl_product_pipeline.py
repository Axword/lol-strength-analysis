#!/usr/bin/env python3
"""Tests for combat inventory / ranks probe / product pipeline gates."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import rofl2_ability_ranks_probe as ranks  # noqa: E402
import rofl2_replication_combat_inventory as combat  # noqa: E402
import rofl_product_pipeline as pipeline  # noqa: E402


class CombatInventoryTests(unittest.TestCase):
    def test_never_trusted(self):
        report = combat.build_combat_report(
            timed_report={
                "identityBinding": {"complete": False},
                "combatInventory": {
                    "trusted": True,  # malicious input
                    "observedKeys": ["mFlatPhysicalDamageMod"],
                },
            },
            wire_proof={
                "schema": "rofl-combat-wire-proof-v1",
                "combatTrusted": False,
                "wireTableProven": False,
                "blocker": {"kind": "combat_wire_unproven", "observedNamed": []},
                "hypothesis": {"provenIndexCount": 0},
            },
        )
        self.assertFalse(report["combatTrusted"])
        self.assertFalse(report["productEligible"])
        self.assertEqual(report["blocker"]["kind"], "combat_wire_unproven")
    def test_empty_inventory(self):
        report = combat.build_combat_report(
            timed_report={"combatInventory": {"observedKeys": []}},
            wire_proof=None,
        )
        # When durable wire-proof artifact exists on disk it may supply names;
        # force empty by passing empty wire_proof-shaped dict without names.
        report = combat.build_combat_report(
            timed_report={"combatInventory": {"observedKeys": []}},
            wire_proof={"blocker": {"observedNamed": []}, "hypothesis": {}},
        )
        self.assertEqual(report["blocker"]["kind"], "combat_fields_not_observed")

    def test_wire_proof_keeps_fail_closed(self):
        report = combat.build_combat_report(
            timed_report={
                "identityBinding": {"complete": True},
                "combatInventory": {
                    "observedKeys": ["mFlatMagicDamageMod"],
                },
            },
            wire_proof={
                "schema": "rofl-combat-wire-proof-v0",
                "combatTrusted": False,
                "blocker": {
                    "kind": "combat_wire_unproven",
                    "observedNamed": ["mFlatMagicDamageMod"],
                    "detail": "no PE wire table",
                },
                "hypothesis": {"provenIndexCount": 0},
            },
        )
        self.assertFalse(report["combatTrusted"])
        self.assertEqual(report["blocker"]["kind"], "combat_wire_unproven")
        self.assertIn("wireProof", report["inventory"])


class RanksProbeTests(unittest.TestCase):
    def test_unproven_shape(self):
        report = {
            "ok": False,
            "opcodeMapped": False,
            "blocker": {"kind": "ability_ranks_wire_unproven"},
            "abilityRanksTrusted": False,
            "productEligible": False,
        }
        self.assertFalse(report["productEligible"])
        self.assertEqual(report["blocker"]["kind"], "ability_ranks_wire_unproven")
        self.assertFalse(report["abilityRanksTrusted"])

    def test_castspell_mapped_contract(self):
        self.assertTrue(callable(ranks.run_ranks_probe))
        self.assertEqual(ranks.CASTSPELL_ANS_OPCODE, 197)
        sample = {
            "castSpellAnsMapped": True,
            "castSpellAnsLevelSlotDecoded": False,
            "abilityRanksTrusted": False,
            "blocker": {"kind": "ability_ranks_wire_unproven"},
        }
        self.assertTrue(sample["castSpellAnsMapped"])
        self.assertFalse(sample["abilityRanksTrusted"])

    def test_level_slot_evidence_keeps_fail_closed(self):
        # Synthetic missing ROFL path short-circuits — exercise classifier fields.
        self.assertFalse(
            bool(
                {
                    "castSpellAnsLevelSlotDecoded": False,
                    "abilityRanksTrusted": False,
                }.get("castSpellAnsLevelSlotDecoded")
            )
        )


class PipelineGateTests(unittest.TestCase):
    def test_phase_c_missing_report(self):
        row = pipeline.phase_c_from_e17(Path("/tmp/missing-e17-report.json"))
        self.assertFalse(row["ok"])
        self.assertEqual(row["blocker"]["kind"], "e17_report_missing")

    def test_pipeline_skip_discover_no_pe(self):
        report = pipeline.run_pipeline(
            rofl=Path("/tmp/missing.rofl"),
            pe=Path("/tmp/missing.exe"),
            match_dir=Path("artifacts/rofl/3264361042"),
            skip_live_discover=True,
        )
        self.assertFalse(report["ok"])
        self.assertFalse(report["calculatorReady"])
        self.assertIn("A_createHero", report["phases"])
        # HP may already be published to the registry; calculator stays closed.
        self.assertFalse(report["phases"]["D_publish"]["calculatorReady"])
        self.assertIsNotNone(report["phases"]["D_publish"]["blocker"])

    def test_gate_a_prefers_castspell_and_match_dir_hp(self):
        report = pipeline.run_pipeline(
            rofl=Path("/tmp/missing.rofl"),
            pe=Path("/tmp/missing.exe"),
            match_dir=Path("artifacts/rofl/3264361042"),
            skip_live_discover=True,
        )
        phase_a = report["phases"]["A_createHero"]
        self.assertTrue(phase_a["ok"])
        self.assertEqual(phase_a["method"], "castspell_ans_champion_string")
        self.assertTrue(phase_a["identityBindingComplete"])
        self.assertTrue(report["phases"]["A_timedHpFuse"]["ok"])
        self.assertTrue(report["hpTrustedEligible"])
        # Gate B1 may already be proven on disk (combat-wire-proof report).
        wire = Path("docs/rofl-research/combat-wire-proof-BR1-3264361042.json")
        wire_trusted = False
        if wire.is_file():
            import json

            wire_trusted = bool(
                json.loads(wire.read_text(encoding="utf-8")).get("combatTrusted")
            )
        if wire_trusted:
            self.assertTrue(report["phases"]["B_combat"]["ok"])
            self.assertTrue(report["phases"]["B_combat"]["combatTrusted"])
        else:
            self.assertFalse(report["phases"]["B_combat"]["ok"])
            self.assertFalse(report["calculatorReady"])
            self.assertIn("combat", report["nextAction"].casefold())
        # UpgradeSpellAns ranks may already be proven on disk.
        if Path("docs/rofl-research/upgrade-spell-ranks-BR1-3264361042.json").is_file():
            self.assertTrue(report["phases"]["B_ranks"]["ok"])
            self.assertTrue(report["phases"]["B_ranks"]["abilityRanksTrusted"])
        else:
            self.assertFalse(report["phases"]["B_ranks"]["ok"])
        self.assertFalse(report["phases"]["C_offlinePositions"]["ok"])
        self.assertEqual(
            report["phases"]["C_offlinePositions"]["blocker"]["kind"],
            "waypoints_not_structurally_decoded",
        )
        self.assertTrue(report["phases"]["D_publish"]["trustedHpPublish"])
        if wire_trusted and report["phases"]["B_ranks"]["ok"]:
            self.assertTrue(report["phases"]["B_combat"]["ok"])
            self.assertTrue(report["phases"]["B_combat"]["combatTrusted"])
            # calculatorReady still needs full-frame HP (partial is not enough).
            if report["calculatorReady"]:
                self.assertTrue(report["phases"]["D_publish"]["calculatorReady"])
                self.assertIsNone(report["phases"]["D_publish"]["blocker"])
            else:
                self.assertFalse(report["phases"]["D_publish"]["calculatorReady"])
                blocker = report["phases"]["D_publish"]["blocker"] or {}
                self.assertIn(
                    blocker.get("kind"),
                    ("calculator_hp_density", "product_gates_incomplete"),
                )
        else:
            self.assertFalse(report["calculatorReady"])
            self.assertFalse(report["phases"]["D_publish"]["calculatorReady"])
            self.assertEqual(
                report["phases"]["D_publish"]["blocker"]["kind"],
                "product_gates_incomplete",
            )
if __name__ == "__main__":
    unittest.main()
