#!/usr/bin/env python3
"""Focused product tests for timed same-match identity-bound HP fusion."""
from __future__ import annotations

import copy
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import fuse_replay_api_hp as fuse  # noqa: E402
import jsonl_to_timeline  # noqa: E402
import rfc461_emit  # noqa: E402
import validate_fur_parity  # noqa: E402

MATCH_CODE = "3264361042"
ROSTER_HASH = "b" * 64
ROFL_HASH = "a" * 64
PATCH = "16.14"
BUILD = "16.14.672.1234"
TIMES = (60_000, 61_000)


def load_product_validator():
    path = SCRIPTS / "validate-rofl-pipeline.py"
    spec = importlib.util.spec_from_file_location("validate_rofl_phase6", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def replay_manifest() -> dict:
    return {
        "manifestVersion": 4,
        "match": {
            "platformId": "BR1",
            "matchCode": MATCH_CODE,
            "gameId": int(MATCH_CODE),
            "gameName": MATCH_CODE,
        },
        "rofl": {
            "patch": PATCH,
            "build": BUILD,
            "sha256": ROFL_HASH,
        },
        "rosterHash": ROSTER_HASH,
        "participants": [
            {
                "participantID": index,
                "puuid": f"puuid-{index}",
                "sourceIdentity": {
                    "stable": True,
                    "key": f"puuid:puuid-{index}",
                },
            }
            for index in range(1, 11)
        ],
        "productGates": {
            "stableIdentityComplete": True,
            "activeReplayIdentityVerified": True,
            "captureComplete": True,
        },
    }


def replay_rows(times: tuple[int, ...] = TIMES) -> list[dict]:
    participants = [
        {
            "participantID": index,
            "teamID": 100 if index <= 5 else 200,
            "championName": f"Champion{index}",
            "playerName": f"Player {index}",
            "summonerName": f"Player {index}#BR1",
            "puuid": f"puuid-{index}",
            "role": "Top",
        }
        for index in range(1, 11)
    ]
    rows = [
        rfc461_emit.coverage_line(
            source="replay_api_playback",
            decoded=["positions_focus_selection"],
            missing=["health", "healthMax", "combatStats", "abilityRanks"],
            provenance={
                "source": "replay_api_playback",
                "sourceKind": "replay_api_playback",
                "gameTimeUnit": "milliseconds",
                "positionCoverage": "full_at_sampled_frames",
                "nativePositionCoverage": "full_at_sampled_frames",
                "hpCoverage": "none",
                "rosterMapping": "stable_liveclient_identity",
                "placeholderPolicy": "explicit_positionSource_only",
                "matchCode": MATCH_CODE,
                "gameId": int(MATCH_CODE),
            },
            extra={"gameID": int(MATCH_CODE)},
        ),
        rfc461_emit.game_info_line(
            game_id=int(MATCH_CODE),
            game_name=MATCH_CODE,
            game_version=BUILD,
            platform_id="BR1",
            participants=participants,
        ),
    ]
    for frame_index, game_time in enumerate(times):
        frame = []
        for index in range(1, 11):
            frame.append(
                rfc461_emit.participant_row(
                    participant_id=index,
                    team_id=100 if index <= 5 else 200,
                    champion_name=f"Champion{index}",
                    player_name=f"Player {index}",
                    position={"x": 1000.0 + index + frame_index, "z": 2000.0 + index},
                    position_source="replay_api_focus_selection",
                    level=10,
                    health_known=False,
                    health_source="unavailable_replay_api",
                    combat_stats_source="unavailable_replay_api",
                    ability_ranks_source="unavailable_replay_api",
                    extra={
                        "summonerName": f"Player {index}#BR1",
                        "puuid": f"puuid-{index}",
                        "role": "Top",
                    },
                )
            )
        rows.append(
            rfc461_emit.stats_update_line(
                game_id=int(MATCH_CODE),
                game_time=game_time,
                participants=frame,
            )
        )
    return rows


def hp_evidence(times: tuple[int, ...] = TIMES) -> dict:
    return {
        "schema": fuse.TRUSTED_EVIDENCE_SCHEMA,
        "match": {
            "platformId": "BR1",
            "matchCode": MATCH_CODE,
            "gameId": int(MATCH_CODE),
            "gameName": MATCH_CODE,
        },
        "rofl": {
            "patch": PATCH,
            "build": BUILD,
            "sha256": ROFL_HASH,
        },
        "rosterHash": ROSTER_HASH,
        "provenance": {
            "sourceKind": fuse.TRUSTED_HEALTH_SOURCE,
            "timed": True,
            "staticSnapshot": False,
            "fixture": False,
            "createHeroOrderFallback": False,
        },
        "identityBinding": {
            "method": fuse.TRUSTED_BINDING_METHOD,
            "complete": True,
            "participants": [
                {
                    "puuid": f"puuid-{index}",
                    "fullRiotId": f"Player {index}#BR1",
                    "champion": f"Champion{index}",
                    "netId": 1000 + index,
                }
                for index in range(1, 11)
            ],
        },
        "timing": {
            "unit": "milliseconds",
            "clock": "replay_game_time",
            "toleranceMs": 100,
        },
        "samples": [
            {
                "gameTimeMs": game_time,
                "units": [
                    {
                        "netId": 1000 + index,
                        "mHP": 500 + index - sample_index * 25,
                        "mMaxHP": 1000 + index,
                        "mMaxHPExplicit": True,
                    }
                    for index in range(1, 11)
                ],
            }
            for sample_index, game_time in enumerate(times)
        ],
    }


class TrustedHpFusionTests(unittest.TestCase):
    def test_minimal_valid_timed_fusion_and_product_validation(self) -> None:
        fused, summary = fuse.fuse_product(
            replay_rows(),
            replay_manifest=replay_manifest(),
            hp_evidence=hp_evidence(),
        )
        self.assertEqual(summary["coverage"], "full")
        self.assertEqual(summary["fusedFrames"], 2)
        stats = [row for row in fused if row.get("rfc461Schema") == "stats_update"]
        first = stats[0]["participants"][0]
        second = stats[1]["participants"][0]
        self.assertEqual(first["health"], 501)
        self.assertEqual(second["health"], 476)
        self.assertEqual(first["healthSource"], fuse.TRUSTED_HEALTH_SOURCE)
        self.assertTrue(first["mMaxHPExplicit"])
        self.assertEqual(first["healthSampleGameTimeMs"], TIMES[0])
        self.assertEqual(first["healthIdentityKey"], "puuid:puuid-1")
        for participant in stats[0]["participants"]:
            self.assertNotIn("attackDamage", participant)
            self.assertEqual(
                participant["combatStatsSource"],
                "unavailable_replay_api",
            )
            self.assertEqual(
                participant["abilityRanksSource"],
                "unavailable_replay_api",
            )
            pid = int(participant["participantID"])
            self.assertEqual(participant["championName"], f"Champion{pid}")
            self.assertEqual(participant["playerName"], f"Player {pid}")
            self.assertEqual(participant["summonerName"], f"Player {pid}#BR1")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            jsonl = root / "events.jsonl"
            timeline_path = root / "timeline.json"
            rfc461_emit.write_jsonl(jsonl, fused)
            timeline = jsonl_to_timeline.build_timeline(
                jsonl,
                timeline_id=MATCH_CODE,
                name=MATCH_CODE,
                patch=PATCH,
            )
            timeline_path.write_text(json.dumps(timeline), encoding="utf-8")
            validator = load_product_validator()
            generic = validator.validate(jsonl, timeline_path, require_live=False)
            product = validator.validate_product(jsonl, timeline_path)
        self.assertTrue(generic["ok"])
        self.assertTrue(product["ok"])
        self.assertTrue(product["hpTrusted"])
        self.assertFalse(product["positionOnly"])
        self.assertFalse(product["calculatorReady"])

        strict = validate_fur_parity.evaluate(
            fused,
            {"requiredSchemas": [], "requiredStatsUpdateParticipantFields": []},
            strict_product=True,
            timeline=timeline,
        )
        self.assertTrue(strict["ok"], strict)
        self.assertTrue(strict["trustedHpGate"]["ok"])
        self.assertFalse(strict["trustedHpGate"]["calculatorReady"])

    def test_scrambled_capture_labels_rewritten_from_binding(self) -> None:
        """Replay capture can put Wukong's name on Sona's pid; HP still binds by identity.

        Product fuse must rewrite champion/player labels from the validated binding
        so timeline units never show MonkeyKing wearing another champ's HP.
        """
        rows = replay_rows()
        for row in rows:
            if row.get("rfc461Schema") != "stats_update":
                continue
            # Rotate blue labels: pid2 gets pid5's name, pid5 gets pid2's name.
            by_pid = {int(p["participantID"]): p for p in row["participants"]}
            by_pid[2]["championName"] = "Sona"
            by_pid[2]["playerName"] = "Player 5"
            by_pid[2]["summonerName"] = "Player 5#BR1"
            by_pid[5]["championName"] = "MonkeyKing"
            by_pid[5]["playerName"] = "Player 2"
            by_pid[5]["summonerName"] = "Player 2#BR1"
        evidence = hp_evidence()
        evidence["identityBinding"]["participants"][1]["champion"] = "MonkeyKing"
        evidence["identityBinding"]["participants"][4]["champion"] = "Sona"
        fused, _summary = fuse.fuse_product(
            rows,
            replay_manifest=replay_manifest(),
            hp_evidence=evidence,
        )
        stats = next(row for row in fused if row.get("rfc461Schema") == "stats_update")
        by_pid = {int(p["participantID"]): p for p in stats["participants"]}
        self.assertEqual(by_pid[2]["championName"], "MonkeyKing")
        self.assertEqual(by_pid[2]["playerName"], "Player 2")
        self.assertEqual(by_pid[5]["championName"], "Sona")
        self.assertEqual(by_pid[5]["playerName"], "Player 5")

        # Timeline must also prefer game_info over scrambled stats labels.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            jsonl = root / "events.jsonl"
            # Pretend game_info is correct while stats stay scrambled (pre-fuse path).
            scrambled = copy.deepcopy(rows)
            rfc461_emit.write_jsonl(jsonl, scrambled)
            timeline = jsonl_to_timeline.build_timeline(
                jsonl,
                timeline_id=MATCH_CODE,
                name=MATCH_CODE,
                patch=PATCH,
            )
        unit_by_pid = {u["pid"]: u for u in timeline["frames"][0]["units"]}
        self.assertEqual(unit_by_pid[2]["champ"], "Champion2")
        self.assertEqual(unit_by_pid[5]["champ"], "Champion5")

    def test_unmatched_frame_remains_unknown_and_coverage_is_partial(self) -> None:
        fused, summary = fuse.fuse_product(
            replay_rows((60_000, 61_000, 62_000)),
            replay_manifest=replay_manifest(),
            hp_evidence=hp_evidence(),
            time_tolerance_ms=0,
        )
        self.assertEqual(summary["coverage"], "partial")
        last = [
            row for row in fused if row.get("rfc461Schema") == "stats_update"
        ][-1]
        self.assertEqual(
            last["hpEvidence"]["coverage"],
            "unknown_no_aligned_sample",
        )
        for participant in last["participants"]:
            self.assertNotIn("health", participant)
            self.assertEqual(
                participant["healthSource"],
                "unavailable_replay_api",
            )

    def test_one_nearby_sample_is_never_reused_across_frames(self) -> None:
        evidence = hp_evidence((60_500, 999_000))
        evidence["timing"]["toleranceMs"] = 500
        fused, summary = fuse.fuse_product(
            replay_rows((60_000, 61_000, 999_000)),
            replay_manifest=replay_manifest(),
            hp_evidence=evidence,
        )
        self.assertEqual(summary["fusedFrames"], 2)
        self.assertEqual(summary["sampleTimesUsed"], 2)
        self.assertEqual(summary["coverage"], "partial")
        stats = [row for row in fused if row.get("rfc461Schema") == "stats_update"]
        self.assertEqual(
            [row["hpEvidence"]["coverage"] for row in stats],
            [
                "known_at_sampled_frame",
                "unknown_no_aligned_sample",
                "known_at_sampled_frame",
            ],
        )

    def test_backfill_null_puuid_from_manifest_riot_id(self) -> None:
        rows = replay_rows()
        for participant in rows[1]["participants"]:
            participant.pop("puuid")
        manifest = replay_manifest()
        for index, participant in enumerate(manifest["participants"], start=1):
            participant["riotId"] = {"full": f"Player {index}#BR1"}
        fused, summary = fuse.fuse_product(
            rows,
            replay_manifest=manifest,
            hp_evidence=hp_evidence(),
        )
        self.assertTrue(summary["ok"])
        game_info = next(row for row in fused if row.get("rfc461Schema") == "game_info")
        self.assertEqual(game_info["participants"][0]["puuid"], "puuid-1")
        self.assertEqual(
            fused[2]["participants"][0]["healthIdentityKey"],
            "puuid:puuid-1",
        )

    def test_decrypt_times_snap_onto_replay_api_frame_grid(self) -> None:
        evidence = hp_evidence((60_325, 61_206))
        evidence["timing"]["toleranceMs"] = 100
        fused, summary = fuse.fuse_product(
            replay_rows(),
            replay_manifest=replay_manifest(),
            hp_evidence=evidence,
        )
        self.assertEqual(summary["fusedFrames"], 2)
        self.assertEqual(
            [s["gameTimeMs"] for s in summary["alignedEvidence"]["samples"]],
            [60_000, 61_000],
        )
        stats = [row for row in fused if row.get("rfc461Schema") == "stats_update"]
        self.assertEqual(stats[0]["participants"][0]["healthSampleGameTimeMs"], 60_000)
        self.assertEqual(stats[0]["participants"][0]["healthSampleDeltaMs"], 0)

    def test_match_patch_hash_and_roster_mismatches_fail(self) -> None:
        scenarios = (
            ("matchCode", ("match", "matchCode"), "3264383283"),
            ("gameID", ("match", "gameId"), 3264383283),
            ("gameName", ("match", "gameName"), "3264383283"),
            ("platform", ("match", "platformId"), "NA1"),
            ("patch", ("rofl", "patch"), "16.13"),
            ("build", ("rofl", "build"), "16.14.other"),
            ("ROFL SHA", ("rofl", "sha256"), "c" * 64),
            ("roster hash", ("rosterHash",), "d" * 64),
        )
        for label, path, value in scenarios:
            with self.subTest(label=label):
                evidence = hp_evidence()
                target = evidence
                for key in path[:-1]:
                    target = target[key]
                target[path[-1]] = value
                with self.assertRaises(fuse.DecryptError):
                    fuse.fuse_product(
                        replay_rows(),
                        replay_manifest=replay_manifest(),
                        hp_evidence=evidence,
                    )

    def test_identity_and_net_id_binding_fail_closed(self) -> None:
        mutations = []
        missing = hp_evidence()
        missing["identityBinding"]["participants"][0].pop("puuid")
        missing["identityBinding"]["participants"][0].pop("fullRiotId")
        mutations.append(missing)
        wrong_identity = hp_evidence()
        wrong_identity["identityBinding"]["participants"][0]["puuid"] = "wrong"
        mutations.append(wrong_identity)
        duplicate_net = hp_evidence()
        duplicate_net["identityBinding"]["participants"][1]["netId"] = 1001
        mutations.append(duplicate_net)
        absent_binding = hp_evidence()
        absent_binding.pop("identityBinding")
        mutations.append(absent_binding)
        for evidence in mutations:
            with self.subTest(mutation=len(mutations)):
                with self.assertRaises(fuse.DecryptError):
                    fuse.fuse_product(
                        replay_rows(),
                        replay_manifest=replay_manifest(),
                        hp_evidence=evidence,
                    )

    def test_full_riot_id_is_valid_stable_fallback_without_order_join(self) -> None:
        manifest = replay_manifest()
        rows = replay_rows()
        evidence = hp_evidence()
        for index, participant in enumerate(manifest["participants"], start=1):
            participant.pop("puuid")
            full = f"Player {index}#BR1"
            participant["riotId"] = {"full": full}
            participant["sourceIdentity"]["key"] = f"riotid:{full.casefold()}"
        game_info = next(
            row for row in rows if row.get("rfc461Schema") == "game_info"
        )
        for participant in game_info["participants"]:
            participant.pop("puuid")
        for participant in evidence["identityBinding"]["participants"]:
            participant.pop("puuid")
        fused, summary = fuse.fuse_product(
            rows,
            replay_manifest=manifest,
            hp_evidence=evidence,
        )
        self.assertTrue(summary["ok"])
        first = next(
            row for row in fused if row.get("rfc461Schema") == "stats_update"
        )["participants"][0]
        self.assertEqual(first["healthIdentityKey"], "riotid:player 1#br1")

    def test_untimed_static_order_and_missing_max_evidence_fail(self) -> None:
        mutations = []
        one_sample = hp_evidence()
        one_sample["samples"] = one_sample["samples"][:1]
        mutations.append(one_sample)
        untimed = hp_evidence()
        untimed["samples"][0].pop("gameTimeMs")
        mutations.append(untimed)
        no_max = hp_evidence()
        no_max["samples"][0]["units"][0]["mMaxHPExplicit"] = False
        mutations.append(no_max)
        wide_tolerance = hp_evidence()
        wide_tolerance["timing"]["toleranceMs"] = 501
        mutations.append(wide_tolerance)
        static = hp_evidence()
        static["provenance"]["staticSnapshot"] = True
        mutations.append(static)
        fixture = hp_evidence()
        fixture["provenance"]["fixture"] = True
        mutations.append(fixture)
        order = hp_evidence()
        order["provenance"]["createHeroOrderFallback"] = True
        mutations.append(order)
        for evidence in mutations:
            with self.assertRaises(fuse.DecryptError):
                fuse.fuse_product(
                    replay_rows(),
                    replay_manifest=replay_manifest(),
                    hp_evidence=evidence,
                )

    def test_legacy_timed_fusion_remains_research_only(self) -> None:
        rows = replay_rows()
        samples = [
            (
                60.0,
                {index: (500.0, 1000.0) for index in range(1, 11)},
            )
        ]
        fused = fuse.fuse(rows, hp_samples=samples, static_snapshot=False)
        provenance = fused[0]["provenance"]
        self.assertTrue(provenance["publicationBlocked"])
        self.assertTrue(provenance["researchOnly"])
        self.assertEqual(
            provenance["sourceKind"],
            fuse.TIMED_RESEARCH_SOURCE_KIND,
        )

    def test_strict_fur_gate_rejects_static_order_binding_max_and_time_gaps(self) -> None:
        fused, _summary = fuse.fuse_product(
            replay_rows(),
            replay_manifest=replay_manifest(),
            hp_evidence=hp_evidence(),
        )

        def provenance(rows: list[dict]) -> dict:
            return next(
                row for row in rows if row.get("rfc461Schema") == "rofl_coverage"
            )["provenance"]

        def first_participant(rows: list[dict]) -> dict:
            return next(
                row for row in rows if row.get("rfc461Schema") == "stats_update"
            )["participants"][0]

        cases = []
        static = copy.deepcopy(fused)
        provenance(static)["sourceKind"] = "research_static_hp_snapshot"
        cases.append(static)
        order = copy.deepcopy(fused)
        provenance(order)["hpIdentityBinding"] = "CreateHero_order"
        cases.append(order)
        absent_binding = copy.deepcopy(fused)
        first_participant(absent_binding).pop("healthNetId")
        cases.append(absent_binding)
        absent_max = copy.deepcopy(fused)
        first_participant(absent_max)["mMaxHPExplicit"] = False
        cases.append(absent_max)
        untimed = copy.deepcopy(fused)
        first_participant(untimed).pop("healthSampleGameTimeMs")
        cases.append(untimed)
        fixture = copy.deepcopy(fused)
        provenance(fixture)["schemaProof"] = True
        cases.append(fixture)

        for rows in cases:
            report = validate_fur_parity.evaluate(
                rows,
                {
                    "requiredSchemas": [],
                    "requiredStatsUpdateParticipantFields": [],
                },
                strict_product=True,
            )
            self.assertFalse(report["ok"], report)
            self.assertFalse(report["trustedHpGate"]["ok"], report)


if __name__ == "__main__":
    unittest.main()
