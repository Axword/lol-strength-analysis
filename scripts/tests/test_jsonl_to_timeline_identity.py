from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.jsonl_to_timeline import build_timeline


class JsonlTimelineIdentityTests(unittest.TestCase):
    def test_carries_feed_identity_into_timeline_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "events.rfc461.jsonl"
            participants = [
                {
                    "participantID": index,
                    "puuid": f"player-{index}",
                    "championName": f"Champion{index}",
                    "teamID": 100 if index <= 5 else 200,
                }
                for index in range(1, 11)
            ]
            stats_participants = [
                {
                    "participantID": index,
                    "position": {"x": 1000 + index * 100, "z": 2000 + index * 100},
                    "health": 500,
                    "healthMax": 600,
                    "level": 1,
                }
                for index in range(1, 11)
            ]
            rows = [
                {
                    "rfc461Schema": "rofl_coverage",
                    "gameID": 0,
                    "platformID": "LOLTMNT02",
                    "source": "grid_riot_livestats",
                    "provenance": {
                        "sourceKind": "grid_riot_livestats",
                        "artifact": "events.jsonl",
                    },
                },
                {
                    "rfc461Schema": "game_info",
                    "gameID": 441536,
                    "platformID": "LOLTMNT02",
                    "gameVersion": "16.14.794.9266",
                    "participants": participants,
                },
                {
                    "rfc461Schema": "stats_update",
                    "gameTime": 1000,
                    "participants": stats_participants,
                },
            ]
            source.write_text(
                "".join(json.dumps(row) + "\n" for row in rows),
                encoding="utf-8",
            )

            timeline = build_timeline(
                source,
                timeline_id="LOLTMNT02-441536",
                name="Identity regression",
                patch="",
            )

            self.assertEqual(timeline["provenance"]["gameId"], 441536)
            self.assertEqual(timeline["provenance"]["matchCode"], "441536")
            self.assertEqual(timeline["provenance"]["platformId"], "LOLTMNT02")

    def test_rejects_conflicting_feed_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "events.rfc461.jsonl"
            rows = [
                {
                    "rfc461Schema": "rofl_coverage",
                    "gameID": 441536,
                    "platformID": "LOLTMNT02",
                },
                {
                    "rfc461Schema": "game_info",
                    "gameID": 999999,
                    "platformID": "LOLTMNT02",
                    "participants": [],
                },
                {
                    "rfc461Schema": "stats_update",
                    "gameTime": 1000,
                    "participants": [],
                },
            ]
            source.write_text(
                "".join(json.dumps(row) + "\n" for row in rows),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(SystemExit, "conflicting game identity"):
                build_timeline(
                    source,
                    timeline_id="conflict",
                    name="Conflict regression",
                    patch="",
                )


if __name__ == "__main__":
    unittest.main()
