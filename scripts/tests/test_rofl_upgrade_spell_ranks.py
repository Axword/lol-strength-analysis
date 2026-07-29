#!/usr/bin/env python3
"""Tests for UpgradeSpellAns ranks decode + fuse helpers."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import fuse_replay_api_ranks as fuse_ranks  # noqa: E402
import rofl2_ability_ranks_probe as ranks  # noqa: E402
import rofl2_upgrade_spell_ranks as upgrade  # noqa: E402


class UpgradeSpellRanksUnitTests(unittest.TestCase):
    def test_cumulative_ranks_monotonic(self):
        events = [
            {"netId": 0x400000AE, "slot": 0, "level": 1, "gameTimeMs": 1000},
            {"netId": 0x400000AE, "slot": 0, "level": 2, "gameTimeMs": 2000},
            {"netId": 0x400000AE, "slot": 3, "level": 1, "gameTimeMs": 3000},
        ]
        final, snaps = upgrade.build_cumulative_ranks(events)
        self.assertEqual(final[0x400000AE], [2, 0, 0, 1])
        self.assertEqual(snaps[-1]["ranksAfter"], [2, 0, 0, 1])

    def test_ranks_at_time(self):
        snaps = [
            {
                "netId": 0x400000AE,
                "gameTimeMs": 1000,
                "ranksAfter": [1, 0, 0, 0],
            },
            {
                "netId": 0x400000AE,
                "gameTimeMs": 5000,
                "ranksAfter": [2, 1, 0, 0],
            },
        ]
        early = fuse_ranks.ranks_at_time(snaps, game_time_ms=2000)
        late = fuse_ranks.ranks_at_time(snaps, game_time_ms=6000)
        self.assertEqual(early[0x400000AE], [1, 0, 0, 0])
        self.assertEqual(late[0x400000AE], [2, 1, 0, 0])

    def test_probe_reads_upgrade_report_when_present(self):
        report_path = Path("docs/rofl-research/upgrade-spell-ranks-BR1-3264361042.json")
        if not report_path.is_file():
            self.skipTest("upgrade ranks report missing")
        rofl = ranks.DEFAULT_ROFL
        if not rofl.is_file():
            # CI without ROFL: still assert durable report shape
            evidence = __import__("json").loads(report_path.read_text(encoding="utf-8"))
            self.assertTrue(evidence.get("abilityRanksTrusted"))
            self.assertEqual(evidence.get("opcode"), 636)
            return
        probe = ranks.run_ranks_probe(rofl, upgrade_report=report_path)
        self.assertTrue(probe["ok"])
        self.assertTrue(probe["abilityRanksTrusted"])
        self.assertEqual(probe["mappedOpcode"], 636)
        self.assertIsNone(probe.get("blocker"))


if __name__ == "__main__":
    unittest.main()
