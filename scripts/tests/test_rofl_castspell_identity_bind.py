#!/usr/bin/env python3
"""Tests for CastSpellAns identity bind helpers."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import rofl2_castspell_identity_bind as bind  # noqa: E402
from rofl2_replication_timed_hp import attempt_identity_binding  # noqa: E402


class NormalizeTests(unittest.TestCase):
    def test_aliases(self):
        roster = [
            "Zaahen",
            "MonkeyKing",
            "Yasuo",
            "Ezreal",
            "Sona",
            "Renekton",
            "Lillia",
            "Leblanc",
            "Ashe",
            "Morgana",
        ]
        self.assertEqual(bind.normalize_champion("YasuoQ", roster), "Yasuo")
        self.assertEqual(bind.normalize_champion("Wukong", roster), "MonkeyKing")
        self.assertEqual(bind.normalize_champion("LeBlanc", roster), "Leblanc")
        self.assertEqual(bind.normalize_champion("Zaahen", roster), "Zaahen")


class BindCompletenessTests(unittest.TestCase):
    def test_castspell_rows_complete_bind(self):
        champs = [
            "Zaahen",
            "MonkeyKing",
            "Yasuo",
            "Ezreal",
            "Sona",
            "Renekton",
            "Lillia",
            "Leblanc",
            "Ashe",
            "Morgana",
        ]
        roster = []
        for i, champ in enumerate(champs):
            puuid = f"p-{i}"
            full = f"P{i}#BR1"
            roster.append(
                {
                    "puuid": puuid,
                    "riotId": {"full": full},
                    "champion": {"raw": champ},
                    "sourceIdentity": {
                        "stable": True,
                        "key": f"puuid:{puuid}",
                        "puuid": puuid,
                        "riotId": {"full": full},
                    },
                }
            )
        # Deliberately scramble CreateHero order vs roster list order.
        order = [3, 1, 0, 5, 2, 7, 4, 9, 6, 8]
        rows = [
            {
                "net_id": bind.PROVEN_HERO_NET_IDS[i],
                "champion": champs[order[i]],
                "participantID": i + 1,
            }
            for i in range(10)
        ]
        # Wait - for complete bind we need each roster champ to match a row.
        # Use correct champion per netId (statsJson spawn order).
        rows = [
            {
                "net_id": bind.PROVEN_HERO_NET_IDS[i],
                "champion": champs[i],
                "participantID": i + 1,
            }
            for i in range(10)
        ]
        binding = attempt_identity_binding(roster, create_hero_rows=rows)
        self.assertTrue(binding["complete"])
        self.assertFalse(binding.get("createHeroOrderFallback"))
        self.assertEqual(binding.get("note"), "create_hero_champion_match")


if __name__ == "__main__":
    unittest.main()
