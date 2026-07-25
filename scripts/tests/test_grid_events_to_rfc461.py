#!/usr/bin/env python3
"""Unit tests for Grid series events → research rfc461 adapter."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import grid_events_to_rfc461 as grid  # noqa: E402

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "grid_series_minimal.jsonl"


class TestChampId(unittest.TestCase):
    def test_spaced_and_special_names(self) -> None:
        self.assertEqual(grid.champ_id("Lee Sin"), "LeeSin")
        self.assertEqual(grid.champ_id("Miss Fortune"), "MissFortune")
        self.assertEqual(grid.champ_id("K'Sante"), "KSante")
        self.assertEqual(grid.champ_id("Renata Glasc"), "Renata")
        self.assertEqual(grid.champ_id("Wukong"), "MonkeyKing")


class TestConvertMinimalFixture(unittest.TestCase):
    def test_convert_emits_research_rfc461_not_product(self) -> None:
        rows = list(grid._iter_jsonl_rows(FIXTURE))
        out, summary = grid.convert_grid_events(rows)
        schemas = [r["rfc461Schema"] for r in out]
        self.assertIn("rofl_coverage", schemas)
        self.assertIn("game_info", schemas)
        self.assertIn("stats_update", schemas)
        self.assertIn("champion_kill", schemas)
        self.assertIn("skill_used", schemas)
        self.assertIn("epic_monster_kill", schemas)
        self.assertIn("game_end", schemas)

        coverage = next(r for r in out if r["rfc461Schema"] == "rofl_coverage")
        self.assertFalse(coverage["productEligible"])
        self.assertFalse(coverage["calculatorReady"])
        self.assertEqual(coverage["provenance"]["sourceKind"], "grid_series_events")
        self.assertIn("ability_ranks", coverage["missing"])
        self.assertIn("calculatorReady", coverage["missing"])

        game_info = next(r for r in out if r["rfc461Schema"] == "game_info")
        champs = {p["championName"] for p in game_info["participants"]}
        self.assertEqual(champs, {"LeeSin", "Ambessa", "MissFortune", "KSante"})
        puuids = {p.get("puuid") for p in game_info["participants"]}
        self.assertTrue(puuids >= {"puuid-alice", "puuid-bob", "puuid-carol", "puuid-dave"})

        stats = [r for r in out if r["rfc461Schema"] == "stats_update"]
        self.assertGreaterEqual(len(stats), 2)
        first = stats[0]["participants"][0]
        self.assertEqual(first["healthSource"], "grid_series_state")
        self.assertEqual(first["combatStatsSource"], "unavailable")
        self.assertEqual(first["abilityRanksSource"], "unavailable")
        self.assertIn("health", first)
        self.assertNotIn("armor", first)  # armor-only must not imply combat known
        self.assertEqual(first["positionSource"], "grid_series_state")

        kill = next(r for r in out if r["rfc461Schema"] == "champion_kill")
        self.assertEqual(kill["killerID"], 1)
        self.assertEqual(kill["victimID"], 3)

        skill = next(r for r in out if r["rfc461Schema"] == "skill_used")
        self.assertEqual(skill["skillSlot"], 1)
        self.assertEqual(skill["skillName"], "lee-sin-q")

        baron = next(r for r in out if r["rfc461Schema"] == "epic_monster_kill")
        self.assertEqual(baron["monsterType"], "baron")

        end = next(r for r in out if r["rfc461Schema"] == "game_end")
        self.assertEqual(end["winningTeam"], 100)

        self.assertFalse(summary["productEligible"])
        self.assertFalse(summary["calculatorReady"])
        self.assertEqual(summary["seriesId"], "2970110")

    def test_cli_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out.jsonl"
            code = grid.main(["--input", str(FIXTURE), "--out", str(out)])
            self.assertEqual(code, 0)
            lines = out.read_text(encoding="utf-8").strip().splitlines()
            self.assertGreaterEqual(len(lines), 5)
            self.assertEqual(json.loads(lines[0])["rfc461Schema"], "rofl_coverage")


class TestPairManifest(unittest.TestCase):
    def test_manifest_pairing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "replay_riot_1_1.rofl").write_bytes(b"rofl")
            (root / "events_1_grid.jsonl.zip").write_bytes(b"PK")
            (root / "replay_riot_2_1.rofl").write_bytes(b"rofl")
            (root / "events_3_grid.jsonl.zip").write_bytes(b"PK")
            manifest = grid.build_pair_manifest(root)
            self.assertEqual(manifest["pairedCount"], 1)
            by_id = {p["seriesId"]: p for p in manifest["pairs"]}
            self.assertTrue(by_id["1"]["paired"])
            self.assertFalse(by_id["2"]["paired"])
            self.assertFalse(by_id["3"]["paired"])
            # Invalid tiny "rofl" bytes should not crash manifest.
            self.assertIn("roflError", by_id["1"])


if __name__ == "__main__":
    unittest.main()
