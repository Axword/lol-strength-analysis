#!/usr/bin/env python3
"""Focused Phase 4 tests for partial history, scoreboard kills, and motion QA."""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1]


def load_script(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


career = load_script("phase4_career", "enrich-timeline-career.py")
scoreboard = load_script("phase4_scoreboard", "rebuild-timeline-scoreboard.py")


def score_participant(
    pid: int,
    *,
    kills: int,
    total_cs: int = 0,
    vision: int = 0,
) -> dict:
    return {
        "participantID": pid,
        "teamID": 100 if pid <= 5 else 200,
        "career": {
            "kills": kills,
            "deaths": 0,
            "assists": 0,
            "totalCreepScore": total_cs,
            "visionScore": vision,
        },
        "careerSource": "liveclient_allgamedata_scores",
        "careerSources": {
            field: "liveclient_allgamedata_scores"
            for field in (
                "kills",
                "deaths",
                "assists",
                "totalCreepScore",
                "visionScore",
            )
        },
    }


class PartialCareerTests(unittest.TestCase):
    def test_score_only_shape_preserves_zero_without_full_coverage(self) -> None:
        row = score_participant(1, kills=0, total_cs=0, vision=0)
        compact = career.compact_base(row)
        self.assertEqual(compact["careerCoverage"], "scores_only")
        self.assertEqual(compact["careerSource"], "liveclient_allgamedata_scores")
        self.assertEqual(compact["kills"], 0)
        self.assertEqual(compact["cs"], 0)
        self.assertEqual(compact["visionScore"], 0)
        for unsupported in (
            "jungleCs",
            "gold",
            "dmgTotal",
            "dmgToChamps",
            "dmgToObjectives",
        ):
            self.assertNotIn(unsupported, compact)

    def test_full_authoritative_rows_remain_full_and_zero_capable(self) -> None:
        row = {
            "participantID": 1,
            "stats": [
                {"name": key, "value": 0}
                for key in career.CAREER_KEYS
            ],
            "attackSpeed": 100,
            "cooldownReduction": 0,
            "lifeSteal": 0,
            "spellVamp": 0,
            "healthRegen": 0,
            "totalGold": 0,
            "currentGold": 0,
        }
        compact = career.compact_base(row)
        self.assertEqual(compact["careerCoverage"], "full")
        self.assertEqual(compact["dmgToChamps"], 0)
        self.assertEqual(compact["gold"], 0)
        self.assertEqual(compact["jungleCs"], 0)

    def test_known_cumulative_scores_must_be_monotonic(self) -> None:
        good = [
            (0, [score_participant(1, kills=0, total_cs=0)]),
            (1000, [score_participant(1, kills=1, total_cs=4)]),
        ]
        career.validate_monotonic_known_scores(good)
        bad = [
            (0, [score_participant(1, kills=1)]),
            (1000, [score_participant(1, kills=0)]),
        ]
        with self.assertRaisesRegex(ValueError, "non-monotonic known score"):
            career.validate_monotonic_known_scores(bad)

    def test_partial_enrichment_attaches_scores_without_unsupported_zeros(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            jsonl = root / "events.jsonl"
            timeline_path = root / "timeline.json"
            participants = [
                {
                    **score_participant(pid, kills=0, total_cs=pid, vision=0),
                    "position": {"x": 1000 + pid, "z": 2000 + pid},
                }
                for pid in range(1, 11)
            ]
            jsonl.write_text(
                "\n".join(
                    json.dumps(row)
                    for row in (
                        {
                            "rfc461Schema": "stats_update",
                            "gameTime": 0,
                            "participants": participants,
                        },
                        {
                            "rfc461Schema": "stats_update",
                            "gameTime": 1000,
                            "participants": participants,
                        },
                    )
                )
                + "\n",
                encoding="utf-8",
            )
            timeline_path.write_text(
                json.dumps(
                    {
                        "source": "replay_api_playback",
                        "provenance": {
                            "positionCoverage": "full_at_sampled_frames"
                        },
                        "frames": [
                            {
                                "t": t,
                                "units": [
                                    {
                                        "pid": pid,
                                        "x": 0.1 + pid * 0.001,
                                        "y": 0.2 + pid * 0.001,
                                        "alive": True,
                                    }
                                    for pid in range(1, 11)
                                ],
                            }
                            for t in (0, 1000)
                        ],
                    }
                ),
                encoding="utf-8",
            )
            argv = [
                "enrich-timeline-career.py",
                "--jsonl",
                str(jsonl),
                "--timeline",
                str(timeline_path),
                "-o",
                str(timeline_path),
            ]
            with mock.patch.object(sys, "argv", argv):
                career.main()
            enriched = json.loads(timeline_path.read_text(encoding="utf-8"))
        unit_career = enriched["frames"][1]["units"][0]["career"]
        self.assertEqual(unit_career["careerCoverage"], "scores_only")
        self.assertEqual(unit_career["cs"], 1)
        self.assertNotIn("gold", unit_career)
        self.assertNotIn("dmgToChamps", unit_career)
        self.assertTrue(enriched["hasCareerStats"])
        self.assertFalse(enriched["hasTouchDmg"])
        self.assertEqual(
            enriched["provenance"]["motionAudit"]["discontinuityCount"],
            0,
        )


class MotionAuditTests(unittest.TestCase):
    def test_continuous_and_discontinuous_segments_are_annotated_honestly(self) -> None:
        timeline = {
            "source": "replay_api_playback",
            "provenance": {"positionCoverage": "full_at_sampled_frames"},
            "frames": [
                {
                    "t": 0,
                    "units": [
                        {"pid": 1, "x": 0.1, "y": 0.1, "alive": True},
                        {"pid": 2, "x": 0.1, "y": 0.2, "alive": True},
                        {"pid": 3, "x": 0.2, "y": 0.2, "alive": True},
                    ],
                },
                {
                    "t": 1000,
                    "units": [
                        {"pid": 1, "x": 0.11, "y": 0.1, "alive": True},
                        {"pid": 2, "x": 0.9, "y": 0.9, "alive": False},
                        {"pid": 3, "x": 0.85, "y": 0.85, "alive": True},
                    ],
                },
                {
                    "t": 2000,
                    "units": [
                        {"pid": 1, "x": 0.9, "y": 0.9, "alive": True},
                        {"pid": 2, "x": 0.9, "y": 0.9, "alive": False},
                        {"pid": 3, "x": 0.86, "y": 0.85, "alive": True},
                    ],
                },
            ],
        }
        original = [
            (unit["pid"], unit["x"], unit["y"])
            for frame in timeline["frames"]
            for unit in frame["units"]
        ]
        summary = career.audit_motion_discontinuities(
            timeline,
            {3: [(1000, "teleport")]},
        )
        self.assertEqual(summary["discontinuityCount"], 3)
        self.assertEqual(summary["deathRespawnCount"], 1)
        self.assertEqual(summary["recallTeleportCount"], 1)
        self.assertEqual(summary["unexplainedCount"], 1)
        self.assertNotIn(
            "motionFromPrevious",
            timeline["frames"][1]["units"][0],
        )
        self.assertEqual(
            timeline["frames"][1]["units"][1]["motionFromPrevious"][
                "classification"
            ],
            "death_respawn",
        )
        self.assertEqual(
            timeline["frames"][1]["units"][2]["motionFromPrevious"][
                "classification"
            ],
            "recall_or_teleport",
        )
        self.assertEqual(
            timeline["frames"][2]["units"][0]["motionFromPrevious"][
                "classification"
            ],
            "unexplained",
        )
        self.assertEqual(
            original,
            [
                (unit["pid"], unit["x"], unit["y"])
                for frame in timeline["frames"]
                for unit in frame["units"]
            ],
        )

    def test_synthetic_path_never_claims_native_full_coverage(self) -> None:
        timeline = {
            "source": "synthetic_path_walk",
            "provenance": {"positionCoverage": "full_at_sampled_frames"},
            "frames": [],
        }
        career.audit_motion_discontinuities(timeline)
        provenance = timeline["provenance"]
        self.assertEqual(provenance["positionCoverage"], "synthetic_sampled_frames")
        self.assertEqual(provenance["nativePositionCoverage"], "none")


class ScoreboardKillsTests(unittest.TestCase):
    def test_team_kills_derive_from_participant_scores(self) -> None:
        participants = [
            score_participant(pid, kills=2 if pid == 1 else 1 if pid == 6 else 0)
            for pid in range(1, 11)
        ]
        snapshots = scoreboard.score_kill_snapshots([(60_000, participants)])
        self.assertEqual(snapshots, [(60_000, {100: 2, 200: 1})])

    def test_partial_scoreboard_keeps_gold_and_objectives_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            jsonl = root / "events.jsonl"
            timeline_path = root / "timeline.json"
            output = root / "out.json"
            participants = [
                score_participant(
                    pid,
                    kills=2 if pid == 1 else 1 if pid == 6 else 0,
                )
                for pid in range(1, 11)
            ]
            rows = [
                {
                    "rfc461Schema": "rofl_coverage",
                    "gameTime": 0,
                    "missing": ["goldHistory", "objectiveHistory"],
                },
                {
                    "rfc461Schema": "stats_update",
                    "gameTime": 60_000,
                    "participants": participants,
                },
                {
                    "rfc461Schema": "stats_update",
                    "gameTime": 61_000,
                    "participants": participants,
                },
            ]
            jsonl.write_text(
                "\n".join(json.dumps(row) for row in rows) + "\n",
                encoding="utf-8",
            )
            timeline_path.write_text(
                json.dumps(
                    {
                        "participants": [
                            {
                                "participantID": pid,
                                "teamID": 100 if pid <= 5 else 200,
                            }
                            for pid in range(1, 11)
                        ],
                        "frames": [
                            {"t": 60_000, "units": []},
                            {"t": 61_000, "units": []},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            argv = [
                "rebuild-timeline-scoreboard.py",
                "--jsonl",
                str(jsonl),
                "--timeline",
                str(timeline_path),
                "-o",
                str(output),
            ]
            with mock.patch.object(sys, "argv", argv):
                scoreboard.main()
            built = json.loads(output.read_text(encoding="utf-8"))
        score = built["frames"][0]["score"]
        self.assertEqual(score["blue"]["kills"], 2)
        self.assertEqual(score["red"]["kills"], 1)
        self.assertNotIn("gold", score["blue"])
        self.assertNotIn("towers", score["blue"])
        self.assertNotIn("dragons", score["blue"])
        self.assertNotIn("goldDelta", score)
        self.assertEqual(score["coverage"]["kills"]["source"], "liveclient_scores")
        self.assertEqual(score["coverage"]["gold"]["coverage"], "unavailable")
        self.assertEqual(
            score["coverage"]["objectives"]["coverage"],
            "unavailable",
        )


if __name__ == "__main__":
    unittest.main()
