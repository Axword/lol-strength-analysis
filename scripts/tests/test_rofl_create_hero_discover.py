#!/usr/bin/env python3
"""Tests for CreateHero discover / identity-bind fail-closed gates."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import rofl2_create_hero_discover as discover  # noqa: E402
from rofl2_replication_timed_hp import attempt_identity_binding  # noqa: E402


def _roster() -> list[dict]:
    champs = [
        "Zaahen",
        "Yasuo",
        "Sona",
        "MonkeyKing",
        "Ezreal",
        "Renekton",
        "Lillia",
        "Leblanc",
        "Ashe",
        "Morgana",
    ]
    rows = []
    for i, champ in enumerate(champs):
        puuid = f"puuid-{i+1}"
        full = f"Player{i+1}#BR1"
        rows.append(
            {
                "puuid": puuid,
                "riotId": {"full": full},
                "champion": {"raw": champ, "display": champ},
                "sourceIdentity": {
                    "stable": True,
                    "key": f"puuid:{puuid}",
                    "puuid": puuid,
                    "riotId": {"full": full},
                },
            }
        )
    return rows


class BlockerTaxonomyTests(unittest.TestCase):
    def test_no_shaped(self):
        b = discover.classify_blocker(
            shaped_count=0, candidate_rows=[], plaintext_in_rofl=False
        )
        self.assertEqual(b["kind"], "create_hero_opcode_not_found")

    def test_framed_without_champions(self):
        b = discover.classify_blocker(
            shaped_count=2,
            candidate_rows=[
                {
                    "framingValidated": True,
                    "championsRecovered": 0,
                    "createHeroCandidate": False,
                }
            ],
            plaintext_in_rofl=False,
        )
        self.assertEqual(b["kind"], "champion_not_structurally_decoded")

    def test_winner(self):
        b = discover.classify_blocker(
            shaped_count=1,
            candidate_rows=[
                {"opcode": 999, "createHeroCandidate": True, "championsRecovered": 10}
            ],
            plaintext_in_rofl=False,
        )
        self.assertIsNone(b["kind"])
        self.assertEqual(b["winnerOpcode"], 999)


class BindHonestyTests(unittest.TestCase):
    def test_order_fallback_not_product(self):
        binding = attempt_identity_binding(
            _roster(),
            replication_net_ids=list(discover.PROVEN_HERO_NET_IDS),
            create_hero_rows=None,
        )
        self.assertFalse(binding["complete"])
        self.assertTrue(binding.get("createHeroOrderFallback"))

    def test_champion_match_completes(self):
        rows = [
            {
                "net_id": discover.PROVEN_HERO_NET_IDS[i],
                "champion": _roster()[i]["champion"]["raw"],
                "participantID": i + 1,
            }
            for i in range(10)
        ]
        binding = attempt_identity_binding(_roster(), create_hero_rows=rows)
        self.assertTrue(binding["complete"])
        self.assertFalse(binding.get("createHeroOrderFallback"))

    def test_emit_events_shape(self):
        champ_by_net = {
            discover.PROVEN_HERO_NET_IDS[i]: _roster()[i]["champion"]["raw"]
            for i in range(10)
        }
        events = discover.emit_create_hero_events(champ_by_net)
        self.assertEqual(len(events), 10)
        self.assertIn("CreateHero", events[0])
        self.assertEqual(events[0]["CreateHero"]["net_id"], discover.PROVEN_HERO_NET_IDS[0])


if __name__ == "__main__":
    unittest.main()
