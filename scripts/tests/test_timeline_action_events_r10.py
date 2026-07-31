#!/usr/bin/env python3
"""Product AA timeline and same-match finalizer regression tests."""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1]
ROOT = SCRIPTS.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import finalize_calculator_ready_replay as finalizer  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "validate_rofl_pipeline_actions",
    SCRIPTS / "validate-rofl-pipeline.py",
)
assert _spec and _spec.loader
validator = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(validator)

HASHES = {
    "aaSourceRoflSha256": "a" * 64,
    "aaReplayManifestSha256": "b" * 64,
    "aaIdentityEvidenceSha256": "c" * 64,
    "aaOpcodeRegistrySha256": "d" * 64,
}


def _timeline_and_rows() -> tuple[dict, list[dict]]:
    attacks = [
        {
            "tMs": 100 + pid,
            "participantId": pid,
            "netId": 1000 + pid,
            "sourceKind": finalizer.AA_SOURCE_KIND,
            "fieldSource": finalizer.AA_FIELD_SOURCE,
        }
        for pid in range(1, 11)
    ]
    timeline = {
        "durationMs": 10_000,
        "participants": [
            {
                "participantID": pid,
                "championName": f"Champion{pid}",
                "summonerName": f"Player{pid}#TAG",
            }
            for pid in range(1, 11)
        ],
        "provenance": {
            "gameId": 428534,
            "aaCoverage": finalizer.AA_COVERAGE,
            "aaEventCount": len(attacks),
            "aaIdentityBinding": "stable_puuid_full_riot_id_to_net_id",
            "aaCalculatorReadyImpact": "none",
            **HASHES,
        },
        "basicAttack": attacks,
    }
    rows = [
        {
            "rfc461Schema": "basic_attack",
            "gameID": 428534,
            "gameTime": attack["tMs"],
            "participantID": attack["participantId"],
            "netId": attack["netId"],
            "sourceKind": finalizer.AA_SOURCE_KIND,
            "fieldSource": finalizer.AA_FIELD_SOURCE,
            "participantIdSource": "stable_identity_to_net_id",
        }
        for attack in attacks
    ]
    return timeline, rows


class ProductActionTimelineTests(unittest.TestCase):
    def test_identity_bound_ten_player_timeline_passes(self):
        timeline, rows = _timeline_and_rows()
        result = validator._validate_product_action_timeline(
            rows, timeline, require_aa_timeline=True
        )
        self.assertTrue(result["ready"])
        self.assertEqual(result["basicAttackCount"], 10)
        self.assertEqual(result["participantCount"], 10)

    def test_require_refuses_research_overlay(self):
        timeline, rows = _timeline_and_rows()
        timeline["provenance"]["aaCoverage"] = "research_overlay"
        with self.assertRaises(SystemExit) as ctx:
            validator._validate_product_action_timeline(
                rows, timeline, require_aa_timeline=True
            )
        self.assertIn("identity_bound_replay_packets", str(ctx.exception))

    def test_research_only_event_is_rejected(self):
        timeline, rows = _timeline_and_rows()
        timeline["basicAttack"][0]["researchOnly"] = True
        with self.assertRaises(SystemExit) as ctx:
            validator._validate_product_action_timeline(
                rows, timeline, require_aa_timeline=True
            )
        self.assertIn("researchOnly", str(ctx.exception))

    def test_participant_order_or_cross_mapping_is_rejected(self):
        timeline, rows = _timeline_and_rows()
        rows[0]["participantID"] = 2
        with self.assertRaises(SystemExit) as ctx:
            validator._validate_product_action_timeline(
                rows, timeline, require_aa_timeline=True
            )
        self.assertIn("rows differ", str(ctx.exception))

    def test_basic_attack_amount_is_rejected(self):
        timeline, rows = _timeline_and_rows()
        timeline["basicAttack"][0]["amount"] = 99
        with self.assertRaises(SystemExit) as ctx:
            validator._validate_product_action_timeline(
                rows, timeline, require_aa_timeline=True
            )
        self.assertIn("damage amount", str(ctx.exception))


class FinalizerBindingTests(unittest.TestCase):
    def _binding_documents(self) -> tuple[dict, dict, dict, list[dict]]:
        raw_players = []
        manifest_players = []
        bound_players = []
        timeline_players = []
        for pid in range(1, 11):
            puuid = f"puuid-{pid}"
            champion = f"Champion{pid}"
            full_riot_id = f"Player{pid}#TAG"
            raw_players.append(
                {
                    "PUUID": puuid,
                    "RIOT_ID_GAME_NAME": f"Player{pid}",
                    "RIOT_ID_TAG_LINE": "TAG",
                    "SKIN": champion,
                    "TEAM": "100" if pid <= 5 else "200",
                }
            )
            manifest_players.append({"participantID": pid, "puuid": puuid})
            bound_players.append(
                {
                    "participantID": pid,
                    "puuid": puuid,
                    "fullRiotId": full_riot_id,
                    "champion": champion,
                    "netId": 1000 + pid,
                }
            )
            timeline_players.append(
                {
                    "participantID": pid,
                    "summonerName": full_riot_id,
                    "championName": champion,
                }
            )
        match = {
            "platformId": "LOLTMNT01",
            "matchCode": "428534",
            "gameId": 428534,
            "gridSeriesId": "2970132",
            "gridGameIndex": 1,
        }
        replay_manifest = {
            "match": match,
            "rofl": {
                "patch": "16.13",
                "build": "16.13.790.6961",
                "sha256": "a" * 64,
            },
            "rosterHash": "roster-hash",
            "participants": manifest_players,
        }
        evidence = {
            "match": dict(match),
            "rofl": {"sha256": "a" * 64},
            "rosterHash": "roster-hash",
            "identityOracleProven": True,
            "identityBinding": {
                "method": "stable_identity_to_net_id",
                "complete": True,
                "createHeroOrderFallback": False,
                "pidStampMethod": "slim_roster_puuid_join",
                "participants": bound_players,
            },
        }
        timeline = {
            "participants": timeline_players,
            "provenance": {
                "gameId": 428534,
                "gridSeriesId": "2970132",
                "gridGameIndex": 1,
            },
        }
        return replay_manifest, evidence, timeline, raw_players

    def test_verifies_puuid_full_id_champion_pid_and_netid(self):
        manifest, evidence, timeline, raw_players = self._binding_documents()
        with tempfile.TemporaryDirectory() as tmp:
            rofl = Path(tmp) / "same-match.rofl"
            rofl.write_bytes(b"test")
            with (
                mock.patch.object(finalizer, "sha256_file", return_value="a" * 64),
                mock.patch.object(
                    finalizer,
                    "parse_rofl2",
                    return_value={
                        "meta": {"statsJson": json.dumps(raw_players)},
                        "payload": b"",
                    },
                ),
            ):
                result = finalizer.verify_same_match_binding(
                    rofl=rofl,
                    replay_manifest=manifest,
                    identity_evidence=evidence,
                    timeline=timeline,
                )
        self.assertEqual(result["gameID"], 428534)
        self.assertEqual(len(result["netIdToParticipantId"]), 10)
        self.assertEqual(result["netIdToParticipantId"][1001], 1)

    def test_wrong_series_fails_closed(self):
        manifest, evidence, timeline, raw_players = self._binding_documents()
        evidence["match"]["gridSeriesId"] = "2970110"
        with tempfile.TemporaryDirectory() as tmp:
            rofl = Path(tmp) / "wrong-series.rofl"
            rofl.write_bytes(b"test")
            with (
                mock.patch.object(finalizer, "sha256_file", return_value="a" * 64),
                mock.patch.object(
                    finalizer,
                    "parse_rofl2",
                    return_value={
                        "meta": {"statsJson": json.dumps(raw_players)},
                        "payload": b"",
                    },
                ),
            ):
                with self.assertRaises(finalizer.FinalizeError) as ctx:
                    finalizer.verify_same_match_binding(
                        rofl=rofl,
                        replay_manifest=manifest,
                        identity_evidence=evidence,
                        timeline=timeline,
                    )
        self.assertIn("gridSeriesId", str(ctx.exception))

    def test_wrong_roster_hash_fails_closed(self):
        manifest, evidence, timeline, _raw_players = self._binding_documents()
        evidence["rosterHash"] = "another-roster"
        with tempfile.TemporaryDirectory() as tmp:
            rofl = Path(tmp) / "wrong-roster.rofl"
            rofl.write_bytes(b"test")
            with mock.patch.object(
                finalizer, "sha256_file", return_value="a" * 64
            ):
                with self.assertRaises(finalizer.FinalizeError) as ctx:
                    finalizer.verify_same_match_binding(
                        rofl=rofl,
                        replay_manifest=manifest,
                        identity_evidence=evidence,
                        timeline=timeline,
                    )
        self.assertIn("roster hash", str(ctx.exception))

    def test_registry_is_patch_and_build_pinned(self):
        registry = finalizer.load_basic_attack_registry(
            ROOT / "scripts/data/lol_packet_opcodes.v1.json",
            "16.13",
            "16.13.790.6961",
        )
        self.assertEqual(set(registry["opcodes"]), {128, 634, 782, 957})
        with self.assertRaises(finalizer.FinalizeError):
            finalizer.load_basic_attack_registry(
                ROOT / "scripts/data/lol_packet_opcodes.v1.json",
                "16.13",
                "16.13.wrong",
            )


if __name__ == "__main__":
    unittest.main()
