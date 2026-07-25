#!/usr/bin/env python3
"""R11 P4 T2 — unit tests for identity-stable product fuse composer."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
ROOT = SCRIPTS.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import fuse_product_timeline as composer  # noqa: E402


IDENTITY = ROOT / (
    "docs/rofl-research/product_ready/r22/"
    "castspell-identity-2970110-g1-pid-stamped.json"
)
POSITION = ROOT / "artifacts/pro-grid/2970110/events.riot.rfc461.research.jsonl"
ACTION = ROOT / (
    "docs/rofl-research/autoresearch/packet_decode/researchers/r41/"
    "emit_2970110_basic_attack_damage.jsonl"
)
WIRE = ROOT / "docs/rofl-research/product_ready/r04/combat-wire-table-16.13.json"
if not WIRE.is_file():
    WIRE = ROOT / "docs/rofl-research/combat-wire-table-16.13.json"
if not WIRE.is_file():
    WIRE = (
        ROOT
        / "docs/rofl-research/autoresearch/product_ready/r04/combat-wire-table-16.13.json"
    )


@unittest.skipUnless(
    IDENTITY.is_file() and POSITION.is_file() and ACTION.is_file(),
    "2970110 KEEP artifacts / pro-grid riot JSONL required",
)
class TestFuseProductTimelineR11(unittest.TestCase):
    def test_strip_removes_grid_trust(self) -> None:
        row = {
            "rfc461Schema": "stats_update",
            "participants": [
                {
                    "participantID": 1,
                    "health": 100,
                    "healthMax": 100,
                    "healthSource": "grid_riot_livestats",
                    "attackDamage": 50,
                    "combatStatsSource": "grid_riot_livestats",
                    "ability1Level": 1,
                    "abilityRanksSource": "grid_riot_livestats",
                    "position": {"x": 1, "z": 2},
                }
            ],
        }
        out = composer.strip_untrusted_product_fields(row)
        p = out["participants"][0]
        self.assertNotIn("health", p)
        self.assertNotIn("attackDamage", p)
        self.assertEqual(p["healthSource"], "unavailable")
        self.assertEqual(p["combatStatsSource"], "unavailable")
        self.assertEqual(p["abilityRanksSource"], "unavailable")
        self.assertEqual(p["position"]["x"], 1)

    def test_strip_clears_stale_source_tags(self) -> None:
        """GOAL §D: strip must not leave orphan hpSource/combatSource."""
        row = {
            "rfc461Schema": "stats_update",
            "participants": [
                {
                    "participantID": 1,
                    "health": 100,
                    "healthMax": 200,
                    "healthSource": "rofl2_replication_decrypt_timed_identity_bound",
                    "hpSource": "pe",
                    "hpHoldForward": True,
                    "attackDamage": 50,
                    "abilityPower": 0,
                    "armor": 30,
                    "magicResist": 30,
                    "attackSpeed": 100,
                    "combatStatsSource": "same_match_replication_type107_pe_wire_table",
                    "combatSource": "hold_forward",
                    "ability1Level": 1,
                    "abilityRanksSource": "rofl2_upgrade_spell_ans_1012_first_write",
                    "position": {"x": 1, "z": 2},
                }
            ],
        }
        out = composer.strip_untrusted_product_fields(row)
        p = out["participants"][0]
        self.assertNotIn("health", p)
        self.assertNotIn("hpSource", p)
        self.assertNotIn("hpHoldForward", p)
        self.assertNotIn("attackDamage", p)
        self.assertNotIn("combatSource", p)
        self.assertEqual(p["healthSource"], "unavailable")
        self.assertEqual(p["combatStatsSource"], "unavailable")
        self.assertEqual(p["abilityRanksSource"], "unavailable")
        self.assertEqual(p["position"]["x"], 1)

    def test_wrong_match_path_refused(self) -> None:
        rows: list = []
        _fused, layer = composer.try_ranks_fuse(
            rows,
            ranks_evidence_path=ROOT
            / "docs/rofl-research/upgrade-spell-ranks-BR1-3264361042.json",
            identity=json.loads(IDENTITY.read_text(encoding="utf-8")),
            series="2970110",
            game_index=1,
        )
        self.assertFalse(layer["accepted"])
        self.assertIn("wrong_match", layer["reason"])

    def test_compose_keepable_happy_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            match_dir = Path(tmp) / "2970110"
            summary = composer.compose_product_timeline(
                match_dir=match_dir,
                series="2970110",
                game_index=1,
                identity_path=IDENTITY,
                position_jsonl=POSITION,
                action_jsonl_paths=[ACTION],
                combat_wire_table=WIRE if WIRE.is_file() else None,
            )
            self.assertTrue(summary.get("ok"))
            self.assertTrue(summary.get("keepable"))
            self.assertTrue((match_dir / "fuse-summary.json").is_file())
            self.assertGreater(summary["layers"]["aa_damage"]["basicAttack"], 0)
            self.assertEqual(summary["knownFlagDensity"]["combatStatsKnown_true"], 0)
            self.assertFalse(summary["calculatorReady"])
            self.assertFalse(summary["C_combat"])


if __name__ == "__main__":
    unittest.main()
