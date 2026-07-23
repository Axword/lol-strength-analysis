#!/usr/bin/env python3
"""Focused tests for the validated published-match registry."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import rebuild_match_registry as registry  # noqa: E402


CHAMPIONS = (
    "Zaahen",
    "Lillia",
    "Yasuo",
    "Ezreal",
    "Sona",
    "Renekton",
    "Wukong",
    "Leblanc",
    "Ashe",
    "Morgana",
)


def write_product_match(
    root: Path,
    match_code: str,
    *,
    source_kind: str = "replay_api_playback",
    calculator_ready: bool = False,
    mismatch_roster: bool = False,
    absolute_path: bool = False,
) -> None:
    match_dir = root / match_code
    match_dir.mkdir(parents=True)
    manifest_participants = []
    timeline_participants = []
    for index, champion in enumerate(CHAMPIONS):
        team = 100 if index < 5 else 200
        display = champion
        asset = "MonkeyKing" if champion == "Wukong" else champion
        manifest_participants.append(
            {
                "teamId": team,
                "sourceIdentity": {
                    "key": f"puuid:puuid-{index}",
                    "puuid": f"puuid-{index}",
                    "stable": True,
                },
                "champion": {
                    "raw": asset,
                    "display": display,
                    "asset": asset,
                    "model": None if champion == "Zaahen" else asset,
                },
            }
        )
        timeline_participants.append(
            {
                "participantID": index + 1,
                "summonerName": f"player {index}#T{index}",
                "championName": (
                    "Garen" if mismatch_roster and index == 0 else display
                ),
                "teamID": team,
                "role": "Top",
            }
        )
    manifest = {
        "manifestVersion": 3,
        "match": {
            "platformId": "BR1",
            "matchCode": match_code,
            "gameId": int(match_code),
            "gameName": match_code,
        },
        "rofl": {
            "basename": f"BR1-{match_code}.rofl",
            "sha256": "a" * 64,
            "patch": "16.14",
            "durationMs": 61_000,
        },
        "participants": manifest_participants,
        "sourceCoverage": {
            "positions": "full_at_sampled_frames",
            "careerHistory": "kda_total_cs_vision_at_sampled_frames",
            "hp": "none",
            "combatStats": "none",
            "abilityRanks": "none",
        },
        "validation": {
            "ok": True,
            "calculatorReady": calculator_ready,
        },
        "productGates": {
            "productValidated": True,
            "stableIdentityComplete": True,
            "calculatorReady": calculator_ready,
        },
        "phase": {
            "current": "publish",
            "status": "complete",
            "completed": ["inspect", "capture", "build", "validate", "publish"],
        },
        "publication": {
            "directory": f"public/data/matches/{match_code}",
            "timeline": "timeline.json",
            "manifest": "manifest.json",
        },
    }
    timeline = {
        "id": match_code,
        "name": match_code,
        "patch": "16.14",
        "source": source_kind,
        "provenance": {
            "source": source_kind,
            "sourceKind": source_kind,
            "artifact": (
                "/Users/example/private/events.jsonl"
                if absolute_path
                else "events.rfc461.jsonl"
            ),
            "matchCode": match_code,
            "gameId": int(match_code),
            "positionCoverage": "full_at_sampled_frames",
        },
        "durationMs": 61_000,
        "participants": timeline_participants,
        "frameCount": 2,
        "frames": [{"t": 60_000, "units": []}, {"t": 61_000, "units": []}],
    }
    (match_dir / "manifest.json").write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )
    (match_dir / "timeline.json").write_text(
        json.dumps(timeline),
        encoding="utf-8",
    )


class MatchRegistryTests(unittest.TestCase):
    def test_empty_registry_is_honest_and_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "matches"
            first = registry.rebuild_registry(root)
            first_bytes = (root / "index.json").read_bytes()
            second = registry.rebuild_registry(root)
            second_bytes = (root / "index.json").read_bytes()
        self.assertEqual(first["matchCount"], 0)
        self.assertIsNone(first["defaultMatchCode"])
        self.assertEqual(first_bytes, second_bytes)
        self.assertEqual(second["registry"]["matches"], [])

    def test_preferred_default_and_compact_product_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "matches"
            write_product_match(root, "3264383283")
            write_product_match(root, "3264361042", calculator_ready=True)
            result = registry.rebuild_registry(root)
            index = json.loads((root / "index.json").read_text(encoding="utf-8"))
        self.assertEqual(result["matchCount"], 2)
        self.assertEqual(index["version"], 1)
        self.assertEqual(index["defaultMatchCode"], "3264361042")
        self.assertEqual(
            [row["matchCode"] for row in index["matches"]],
            ["3264361042", "3264383283"],
        )
        first = index["matches"][0]
        self.assertEqual(first["timelineUrl"], "3264361042/timeline.json")
        self.assertEqual(first["manifestUrl"], "3264361042/manifest.json")
        self.assertEqual(first["roster"]["participantCount"], 10)
        self.assertEqual(first["coverage"]["history"], "kda_total_cs_vision_at_sampled_frames")
        self.assertFalse(first["productGates"]["hpTrusted"])
        self.assertTrue(first["productGates"]["calculatorReady"])
        self.assertNotIn("/Users/", json.dumps(index))

    def test_invalid_candidate_refuses_atomic_registry_replacement(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "matches"
            write_product_match(root, "3264361042")
            registry.rebuild_registry(root)
            prior = (root / "index.json").read_bytes()
            write_product_match(root, "3264383283", source_kind="schema_proof_fixture")
            with self.assertRaisesRegex(registry.RegistryError, "schema_proof"):
                registry.rebuild_registry(root)
            self.assertEqual((root / "index.json").read_bytes(), prior)

    def test_missing_identity_inconsistent_and_unsanitized_entries_fail(self) -> None:
        scenarios = (
            ("missing", {}),
            ("roster", {"mismatch_roster": True}),
            ("absolute", {"absolute_path": True}),
        )
        for label, kwargs in scenarios:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp) / "matches"
                if label == "missing":
                    (root / "3264361042").mkdir(parents=True)
                    (root / "3264361042" / "manifest.json").write_text(
                        "{}",
                        encoding="utf-8",
                    )
                else:
                    write_product_match(root, "3264361042", **kwargs)
                with self.assertRaises(registry.RegistryError):
                    registry.rebuild_registry(root)
                self.assertFalse((root / "index.json").exists())

    def test_non_strict_helper_excludes_and_reports_invalid_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "matches"
            write_product_match(root, "3264361042")
            write_product_match(root, "3264383283", source_kind="fur_parity_fixture")
            built, errors = registry.build_registry(root, strict=False)
        self.assertEqual([row["matchCode"] for row in built["matches"]], ["3264361042"])
        self.assertEqual(len(errors), 1)
        self.assertIn("fur_parity", errors[0])


if __name__ == "__main__":
    unittest.main()
