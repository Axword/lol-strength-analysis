#!/usr/bin/env python3
"""Combat/ranks fuse must bind by identity and rewrite scrambled capture labels."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import fuse_replay_api_combat as fuse_combat  # noqa: E402
import fuse_replay_api_ranks as fuse_ranks  # noqa: E402
import rfc461_emit  # noqa: E402

CASTSPELL = Path("docs/rofl-research/castspell-identity-BR1-3264361042.json")
RANKS = Path("docs/rofl-research/upgrade-spell-ranks-BR1-3264361042.json")
COMBAT = Path("docs/rofl-research/combat-wire-proof-BR1-3264361042.json")


def _binding_roster() -> list[dict[str, Any]]:
    identity = json.loads(CASTSPELL.read_text(encoding="utf-8"))
    rows = []
    for index, raw in enumerate(identity["identityBinding"]["participants"], start=1):
        full = raw["fullRiotId"]
        rows.append(
            {
                "participantID": index,
                "teamID": 100 if index <= 5 else 200,
                "championName": raw["champion"],
                "playerName": full.split("#", 1)[0],
                "summonerName": full,
                "puuid": raw["puuid"],
                "role": "NONE",
            }
        )
    return rows


def _scrambled_stats(base: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rotate blue labels: pid2 gets Sona name, pid5 gets MonkeyKing name.

    Identities (puuid) and participantIDs stay CreateHero-correct so HP netIds
    remain valid; only championName/playerName are lies.
    """
    out = [dict(p) for p in base]
    by_pid = {int(p["participantID"]): p for p in out}
    by_pid[2]["championName"] = "Sona"
    by_pid[2]["playerName"] = "nhUwUmi"
    by_pid[2]["summonerName"] = "nhUwUmi#glhf"
    by_pid[5]["championName"] = "MonkeyKing"
    by_pid[5]["playerName"] = "pixel"
    by_pid[5]["summonerName"] = "pixel#mari"
    # Pretend HP fuse already stamped correct netIds for CreateHero pids.
    identity = json.loads(CASTSPELL.read_text(encoding="utf-8"))
    net_by_puuid = {
        p["puuid"]: int(p["netId"]) for p in identity["identityBinding"]["participants"]
    }
    for p in out:
        p["healthNetId"] = net_by_puuid[p["puuid"]]
        p["healthIdentityKey"] = f"puuid:{p['puuid']}"
    return out


def _rows() -> list[dict]:
    roster = _binding_roster()
    scrambled = _scrambled_stats(roster)
    return [
        rfc461_emit.coverage_line(
            source="replay_api_playback",
            decoded=["positions_focus_selection"],
            missing=["combatStats", "abilityRanks"],
            provenance={
                "source": "replay_api_playback",
                "sourceKind": "replay_api_playback",
                "gameTimeUnit": "milliseconds",
                "positionCoverage": "full_at_sampled_frames",
                "hpCoverage": "partial",
                "rosterMapping": "stable_puuid_or_full_riot_id",
                "matchCode": "3264361042",
            },
        ),
        rfc461_emit.game_info_line(
            game_id=3264361042,
            participants=roster,
            game_name="3264361042",
            game_version="16.14.794.5912",
            platform_id="BR1",
            stats_update_interval_ms=1000,
        ),
        {
            "rfc461Schema": "stats_update",
            "gameTime": 100_000,
            "gameID": 3264361042,
            "participants": scrambled,
        },
    ]


@unittest.skipUnless(CASTSPELL.is_file() and RANKS.is_file(), "ranks fixtures missing")
class RanksFuseIdentityLabelTests(unittest.TestCase):
    def test_scrambled_labels_rewritten_and_net_follows_identity(self) -> None:
        evidence = json.loads(RANKS.read_text(encoding="utf-8"))
        castspell = json.loads(CASTSPELL.read_text(encoding="utf-8"))
        fused, summary = fuse_ranks.fuse_ranks_product(
            _rows(),
            ranks_evidence=evidence,
            castspell_identity=castspell,
        )
        self.assertTrue(summary["ok"])
        stats = next(r for r in fused if r.get("rfc461Schema") == "stats_update")
        by_pid = {int(p["participantID"]): p for p in stats["participants"]}
        self.assertEqual(by_pid[2]["championName"], "MonkeyKing")
        self.assertEqual(by_pid[2]["playerName"], "pixel")
        self.assertEqual(by_pid[2]["abilityRanksNetId"], 0x400000AF)
        self.assertEqual(by_pid[5]["championName"], "Sona")
        self.assertEqual(by_pid[5]["abilityRanksNetId"], 0x400000B2)
        # Must not attach MonkeyKing ranks to the Sona-named scrambled row.
        self.assertNotEqual(by_pid[5]["abilityRanksNetId"], 0x400000AF)


@unittest.skipUnless(CASTSPELL.is_file() and COMBAT.is_file(), "combat fixtures missing")
class CombatFuseIdentityLabelTests(unittest.TestCase):
    def test_scrambled_labels_rewritten_and_net_follows_identity(self) -> None:
        evidence = json.loads(COMBAT.read_text(encoding="utf-8"))
        castspell = json.loads(CASTSPELL.read_text(encoding="utf-8"))
        fused, summary = fuse_combat.fuse_combat_product(
            _rows(),
            combat_evidence=evidence,
            castspell_identity=castspell,
        )
        self.assertTrue(summary["ok"])
        stats = next(r for r in fused if r.get("rfc461Schema") == "stats_update")
        by_pid = {int(p["participantID"]): p for p in stats["participants"]}
        self.assertEqual(by_pid[2]["championName"], "MonkeyKing")
        self.assertEqual(by_pid[2]["playerName"], "pixel")
        if by_pid[2].get("combatStatsNetId") is not None:
            self.assertEqual(by_pid[2]["combatStatsNetId"], 0x400000AF)
        self.assertEqual(by_pid[5]["championName"], "Sona")
        if by_pid[5].get("combatStatsNetId") is not None:
            self.assertEqual(by_pid[5]["combatStatsNetId"], 0x400000B2)
            self.assertNotEqual(by_pid[5]["combatStatsNetId"], 0x400000AF)


if __name__ == "__main__":
    unittest.main()
