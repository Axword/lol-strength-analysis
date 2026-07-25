#!/usr/bin/env python3
"""Unit tests for GRID Riot live-stats → research rfc461 adapter."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import grid_riot_events_to_rfc461 as riot  # noqa: E402

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "grid_riot_livestats_minimal.jsonl"


class TestSuggestedRename(unittest.TestCase):
    def test_derives_platform_game_id(self) -> None:
        self.assertEqual(
            riot.suggested_product_rofl_name("LOLTMNT01", 426746),
            "LOLTMNT01-426746.rofl",
        )

    def test_refuses_missing_or_grid_platform(self) -> None:
        self.assertIsNone(riot.suggested_product_rofl_name("", 426746))
        self.assertIsNone(riot.suggested_product_rofl_name("GRID", 426746))
        self.assertIsNone(riot.suggested_product_rofl_name("LOLTMNT01", None))
        self.assertIsNone(riot.suggested_product_rofl_name("LOLTMNT01", 0))


class TestAnnotateHonesty(unittest.TestCase):
    def test_strips_incomplete_hp_and_combat(self) -> None:
        incomplete = {
            "participantID": 1,
            "teamID": 100,
            "championName": "Ambessa",
            "playerName": "P1",
            "puuid": "puuid-1",
            "position": {"x": 1, "z": 2},
            "health": 100,  # missing healthMax
            "attackDamage": 60,  # incomplete combat set
            "ability1Level": 1,
            "ability2Level": 0,
            "ability3Level": 0,
            "ability4Level": 0,
        }
        out = riot.annotate_participant(incomplete)
        self.assertEqual(out["healthSource"], "unavailable")
        self.assertNotIn("health", out)
        self.assertEqual(out["combatStatsSource"], "unavailable")
        self.assertNotIn("attackDamage", out)
        self.assertEqual(out["abilityRanksSource"], "grid_riot_livestats")
        self.assertEqual(out["positionSource"], "grid_riot_livestats")


class TestConvertFixture(unittest.TestCase):
    def test_convert_emits_research_not_product(self) -> None:
        rows = list(riot._iter_jsonl_rows(FIXTURE))
        out, summary = riot.convert_riot_livestats(
            iter(rows),
            series_id_hint="2970110",
            game_index_hint=1,
            artifact="fixture",
        )
        schemas = [r["rfc461Schema"] for r in out]
        self.assertEqual(schemas[0], "rofl_coverage")
        self.assertIn("game_info", schemas)
        self.assertIn("stats_update", schemas)
        self.assertIn("champion_kill", schemas)
        self.assertIn("skill_level_up", schemas)
        self.assertIn("game_end", schemas)

        coverage = out[0]
        self.assertFalse(coverage["productEligible"])
        self.assertFalse(coverage["calculatorReady"])
        self.assertEqual(coverage["provenance"]["sourceKind"], "grid_riot_livestats")
        self.assertIn("calculatorReady", coverage["missing"])

        game_info = next(r for r in out if r["rfc461Schema"] == "game_info")
        self.assertEqual(game_info["platformID"], "LOLTMNT01")
        self.assertEqual(game_info["gameID"], 426746)
        puuids = {p.get("puuid") for p in game_info["participants"]}
        self.assertIn("puuid-riot-1", puuids)
        self.assertEqual(game_info["participants"][0].get("fullRiotId"), "Player1#TEST")

        good_stats = next(
            r for r in out if r["rfc461Schema"] == "stats_update" and r["gameTime"] == 1000
        )
        p0 = good_stats["participants"][0]
        self.assertEqual(p0["healthSource"], "grid_riot_livestats")
        self.assertEqual(p0["combatStatsSource"], "grid_riot_livestats")
        self.assertEqual(p0["abilityRanksSource"], "grid_riot_livestats")
        self.assertIn("health", p0)
        self.assertIn("armor", p0)

        bad_stats = next(
            r for r in out if r["rfc461Schema"] == "stats_update" and r["gameTime"] == 601000
        )
        bad0 = bad_stats["participants"][0]
        self.assertEqual(bad0["healthSource"], "unavailable")
        self.assertNotIn("health", bad0)
        bad1 = bad_stats["participants"][1]
        self.assertEqual(bad1["combatStatsSource"], "unavailable")
        self.assertNotIn("attackDamage", bad1)

        self.assertFalse(summary["productEligible"])
        self.assertFalse(summary["calculatorReady"])
        self.assertEqual(summary["suggestedProductRofl"], "LOLTMNT01-426746.rofl")
        self.assertTrue(summary["productFilenameDerivable"])
        self.assertTrue(summary["trustGates"]["hpKnown"])
        self.assertTrue(summary["trustGates"]["abilityRanksKnown"])

    def test_cli_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out.jsonl"
            summary = Path(tmp) / "summary.json"
            code = riot.main(
                [
                    "--input",
                    str(FIXTURE),
                    "--out",
                    str(out),
                    "--summary",
                    str(summary),
                    "--series-id",
                    "2970110",
                    "--game-index",
                    "1",
                ]
            )
            self.assertEqual(code, 0)
            lines = out.read_text(encoding="utf-8").strip().splitlines()
            self.assertGreaterEqual(len(lines), 5)
            self.assertEqual(json.loads(lines[0])["rfc461Schema"], "rofl_coverage")
            payload = json.loads(summary.read_text(encoding="utf-8"))
            self.assertEqual(payload["suggestedProductRofl"], "LOLTMNT01-426746.rofl")

    def test_rename_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            # Minimal game_info-only riot file
            riot_path = root / "events_2970110_1_riot.jsonl"
            riot_path.write_text(
                json.dumps(
                    {
                        "rfc461Schema": "game_info",
                        "gameID": 426746,
                        "platformID": "LOLTMNT01",
                        "participants": [],
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (root / "replay_riot_2970110_1.rofl").write_bytes(b"rofl")
            report = riot.build_rename_report(root)
            self.assertEqual(report["derivableCount"], 1)
            entry = report["entries"][0]
            self.assertEqual(entry["suggestedProductRofl"], "LOLTMNT01-426746.rofl")
            self.assertTrue(entry["dumpRoflPresent"])


class TestSlimSqlite(unittest.TestCase):
    def test_sqlite_strips_unknown_and_keeps_dense_frames(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "timeline.slim.sqlite"
            summary = riot.write_riot_slim_sqlite(
                FIXTURE,
                db,
                series_id_hint="2970110",
                game_index_hint=1,
            )
            self.assertTrue(db.is_file())
            self.assertFalse(summary["productEligible"])
            self.assertFalse(summary["calculatorReady"])
            self.assertEqual(summary["suggestedProductRofl"], "LOLTMNT01-426746.rofl")
            self.assertEqual(summary["statsUpdates"], 3)
            self.assertEqual(summary["frameRows"], 30)  # 3 updates × 10 players

            conn = __import__("sqlite3").connect(str(db))
            try:
                meta = dict(conn.execute("SELECT key, value FROM meta"))
                self.assertEqual(meta["schema"], riot.SQLITE_SCHEMA_VERSION)
                self.assertEqual(meta["calculatorReady"], "false")
                self.assertEqual(meta["suggestedProductRofl"], "LOLTMNT01-426746.rofl")

                roster_n = conn.execute("SELECT COUNT(*) FROM roster").fetchone()[0]
                self.assertEqual(roster_n, 10)
                puuid = conn.execute(
                    "SELECT puuid FROM roster WHERE participant_id = 1"
                ).fetchone()[0]
                self.assertEqual(puuid, "puuid-riot-1")

                # Good frame keeps HP/combat
                good = conn.execute(
                    "SELECT health, health_max, attack_damage, hp_known, combat_known, items_json "
                    "FROM frames WHERE game_time_ms = 1000 AND participant_id = 1"
                ).fetchone()
                self.assertEqual(good[3], 1)
                self.assertEqual(good[4], 1)
                self.assertIsNotNone(good[0])
                self.assertIsNotNone(good[2])
                self.assertEqual(json.loads(good[5]), [1055, 2003])

                # Incomplete HP → NULL + hp_known=0
                bad_hp = conn.execute(
                    "SELECT health, hp_known FROM frames "
                    "WHERE game_time_ms = 601000 AND participant_id = 1"
                ).fetchone()
                self.assertIsNone(bad_hp[0])
                self.assertEqual(bad_hp[1], 0)

                # Incomplete combat → NULL + combat_known=0
                bad_combat = conn.execute(
                    "SELECT attack_damage, combat_known FROM frames "
                    "WHERE game_time_ms = 601000 AND participant_id = 2"
                ).fetchone()
                self.assertIsNone(bad_combat[0])
                self.assertEqual(bad_combat[1], 0)

                kill_n = conn.execute(
                    "SELECT COUNT(*) FROM events WHERE schema = 'champion_kill'"
                ).fetchone()[0]
                self.assertEqual(kill_n, 1)
            finally:
                conn.close()

    def test_cli_sqlite_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "out.sqlite"
            code = riot.main(
                [
                    "--input",
                    str(FIXTURE),
                    "--sqlite",
                    str(db),
                    "--series-id",
                    "2970110",
                ]
            )
            self.assertEqual(code, 0)
            self.assertTrue(db.is_file())


if __name__ == "__main__":
    unittest.main()
