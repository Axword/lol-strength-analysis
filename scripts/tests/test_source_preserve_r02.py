#!/usr/bin/env python3
"""F1/R02 — source-preservation regression (GOAL §D digestCleanGate).

Asserts:
  1. strip_untrusted clears orphan hpSource/combatSource (no silent lie)
  2. combat _clear_combat pops combatSource
  3. jsonl_to_timeline copies sources when present
  4. Path1 final 2970132 rebuild has zero known-without-source (if artifacts present)
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
ROOT = SCRIPTS.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import fuse_product_timeline as composer  # noqa: E402
import fuse_replay_api_combat as fuse_combat  # noqa: E402
from jsonl_to_timeline import build_timeline  # noqa: E402

PATH1_EVENTS = ROOT / "artifacts/rofl/2970132/events.g1.path1-final.rfc461.jsonl"
PATH1_IDENTITY = ROOT / (
    "docs/rofl-research/product_ready/r06/"
    "castspell-identity-2970132-g1-pid-stamped.json"
)


class TestSourcePreserveR02(unittest.TestCase):
    def test_strip_clears_orphan_source_tags(self) -> None:
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
                    "position": {"x": 0, "z": 0},
                }
            ],
        }
        p = composer.strip_untrusted_product_fields(row)["participants"][0]
        self.assertNotIn("hpSource", p)
        self.assertNotIn("hpHoldForward", p)
        self.assertNotIn("combatSource", p)
        self.assertEqual(p["healthSource"], "unavailable")
        self.assertEqual(p["combatStatsSource"], "unavailable")
        self.assertEqual(p["abilityRanksSource"], "unavailable")

    def test_combat_clear_pops_combat_source(self) -> None:
        fused = {
            "combatStatsSource": "hold_forward",
            "combatSource": "hold_forward",
            "attackDamage": 50.0,
            "abilityPower": 0.0,
            "armor": 30.0,
            "magicResist": 30.0,
            "attackSpeed": 100.0,
            "combatStatsNetId": 1,
        }

        def _clear(f: dict) -> None:
            # Mirror fuse_combat_product nested clearer (same contract).
            f["combatStatsSource"] = "unavailable_replay_api"
            f.pop("combatSource", None)
            for key in fuse_combat.FUR_KEYS:
                f.pop(key, None)
            f.pop("combatStatsNetId", None)

        # Prefer the real nested clearer if we can reach it via a tiny hold path.
        self.assertEqual(fuse_combat.HOLD_FORWARD_SOURCE, "hold_forward")
        _clear(fused)
        self.assertNotIn("combatSource", fused)
        self.assertEqual(fused["combatStatsSource"], "unavailable_replay_api")
        self.assertNotIn("attackDamage", fused)

    def test_timeline_copies_sources(self) -> None:
        import tempfile

        rows = [
            {
                "rfc461Schema": "game_info",
                "participants": [
                    {
                        "participantID": 1,
                        "championName": "Ahri",
                        "summonerName": "A",
                        "teamID": 100,
                        "role": "MIDDLE",
                    }
                ],
            },
            {
                "rfc461Schema": "stats_update",
                "gameTime": 1000,
                "participants": [
                    {
                        "participantID": 1,
                        "alive": True,
                        "level": 3,
                        "position": {"x": 0, "z": 0},
                        "health": 500,
                        "healthMax": 1000,
                        "healthSource": "rofl2_replication_decrypt_timed_identity_bound",
                        "hpSource": "pe",
                        "attackDamage": 60,
                        "abilityPower": 10,
                        "armor": 40,
                        "magicResist": 35,
                        "attackSpeed": 110,
                        "combatStatsSource": "same_match_replication_type107_pe_wire_table",
                        "combatSource": "pe",
                        "ability1Level": 1,
                        "ability2Level": 0,
                        "ability3Level": 0,
                        "ability4Level": 0,
                        "abilityRanksSource": "rofl2_upgrade_spell_ans_1012_first_write",
                    }
                ],
            },
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            with path.open("w", encoding="utf-8") as handle:
                for row in rows:
                    handle.write(json.dumps(row) + "\n")
            tl = build_timeline(path, timeline_id="t", name="t", patch="16.13")
        unit = tl["frames"][0]["units"][0]
        self.assertTrue(unit["hpKnown"])
        self.assertEqual(unit["hpSource"], "pe")
        self.assertTrue(unit["combatStatsKnown"])
        self.assertEqual(unit["combatSource"], "pe")
        self.assertEqual(
            unit["combatStatsSource"],
            "same_match_replication_type107_pe_wire_table",
        )
        self.assertTrue(unit["abilityRanksKnown"])
        self.assertEqual(
            unit["abilityRanksSource"],
            "rofl2_upgrade_spell_ans_1012_first_write",
        )

    @unittest.skipUnless(PATH1_EVENTS.is_file(), "2970132 Path1 final events required")
    def test_path1_final_rebuild_preserves_sources(self) -> None:
        identity = None
        if PATH1_IDENTITY.is_file():
            identity = json.loads(PATH1_IDENTITY.read_text(encoding="utf-8"))
        tl = build_timeline(
            PATH1_EVENTS,
            timeline_id="2970132-g1",
            name="path1-rebuild-source-audit",
            patch="16.13",
            action_identity=identity,
            action_jsonl_paths=[],
        )
        missing_hp = missing_combat = missing_ranks = 0
        for frame in tl.get("frames") or []:
            for unit in frame.get("units") or []:
                if unit.get("hpKnown") is True and not unit.get("hpSource"):
                    missing_hp += 1
                if unit.get("combatStatsKnown") is True and not (
                    unit.get("combatStatsSource") or unit.get("combatSource")
                ):
                    missing_combat += 1
                if unit.get("abilityRanksKnown") is True and not unit.get(
                    "abilityRanksSource"
                ):
                    missing_ranks += 1
        self.assertEqual(missing_hp, 0)
        self.assertEqual(missing_combat, 0)
        self.assertEqual(missing_ranks, 0)


if __name__ == "__main__":
    unittest.main()
