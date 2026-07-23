#!/usr/bin/env python3
"""Focused tests for the phased resumable ROFL ingest controller."""
from __future__ import annotations

import json
import plistlib
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1]
ROOT = SCRIPTS.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import rofl_ingest as ingest  # noqa: E402
import rofl_metadata  # noqa: E402


VERSION = "16.14.794.5912"
MATCH_CODE = "3264361042"


def metadata_players() -> list[dict]:
    champions = [
        "Zaahen",
        "Lillia",
        "Yasuo",
        "Ezreal",
        "Sona",
        "Renekton",
        "MonkeyKing",
        "Leblanc",
        "Ashe",
        "Morgana",
    ]
    rows = []
    for index, champion in enumerate(champions):
        rows.append(
            {
                "PUUID": f"puuid-{index + 1}",
                "RIOT_ID_GAME_NAME": f"player {index + 1}",
                "RIOT_ID_TAG_LINE": f"T{index + 1}",
                "SKIN": champion,
                "TEAM": "100" if index < 5 else "200",
                "TEAM_POSITION": (
                    "TOP",
                    "JUNGLE",
                    "MIDDLE",
                    "BOTTOM",
                    "UTILITY",
                )[index % 5],
            }
        )
    return rows


def write_rofl(
    directory: Path,
    *,
    basename: str = f"BR1-{MATCH_CODE}.rofl",
    duration_ms: int = 62_000,
) -> Path:
    path = directory / basename
    version = VERSION.encode("ascii")
    metadata = {
        "gameLength": duration_ms,
        "lastGameChunkId": 3,
        "lastKeyFrameId": 2,
        "statsJson": json.dumps(metadata_players()),
    }
    metadata_bytes = json.dumps(metadata, separators=(",", ":")).encode("utf-8")
    data = (
        b"RIOT\x02\x00"
        + b"\x00" * 8
        + bytes([len(version)])
        + version
        + struct.pack("<IIII", 1, 2, 3, 4)
        + b"payload"
        + metadata_bytes
        + struct.pack("<I", len(metadata_bytes))
    )
    path.write_bytes(data)
    return path


def write_app(directory: Path) -> Path:
    app = directory / "LeagueofLegends.app"
    plist = app / "Contents/Info.plist"
    plist.parent.mkdir(parents=True)
    plist.write_bytes(
        plistlib.dumps(
            {
                "CFBundleVersion": "16.14.7945912",
                "FileVersion": VERSION,
            }
        )
    )
    return app


def live_players(*, wrong_first_champion: bool = False) -> list[dict]:
    rows = []
    for index, source in enumerate(metadata_players()):
        champion = source["SKIN"]
        raw_champion = source["SKIN"]
        if champion == "MonkeyKing":
            champion = "Wukong"
        if wrong_first_champion and index == 0:
            champion = "Garen"
            raw_champion = "Garen"
        rows.append(
            {
                "puuid": source["PUUID"],
                "championName": champion,
                "rawChampionName": raw_champion,
                "summonerName": (
                    f"{source['RIOT_ID_GAME_NAME']}#{source['RIOT_ID_TAG_LINE']}"
                ),
                "riotIdGameName": source["RIOT_ID_GAME_NAME"],
                "riotIdTagLine": source["RIOT_ID_TAG_LINE"],
                "team": "ORDER" if index < 5 else "CHAOS",
                "position": source["TEAM_POSITION"],
                "level": 10,
                "items": [{"itemID": 1001}],
                "isDead": False,
            }
        )
    return rows


class PreflightTransport:
    def __init__(self, *, duration_ms: int, wrong_first_champion: bool = False):
        self.duration_ms = duration_ms
        self.players = live_players(wrong_first_champion=wrong_first_champion)
        self.calls: list[tuple[str, str, object]] = []

    def __call__(
        self,
        method: str,
        url: str,
        *,
        body: object = None,
        timeout: float = 2.0,
    ) -> dict:
        del timeout
        self.calls.append((method, url, body))
        if method != "GET":
            return {"ok": False, "error": "mutation forbidden in preflight"}
        if url.endswith("/replay/game"):
            payload = {"gameID": int(MATCH_CODE), "gameVersion": VERSION}
        elif url.endswith("/replay/playback"):
            payload = {
                "paused": True,
                "seeking": False,
                "time": 60.0,
                "length": self.duration_ms / 1000,
            }
        elif url.endswith("/liveclientdata/playerlist"):
            payload = self.players
        elif url.endswith("/liveclientdata/allgamedata"):
            payload = {
                "allPlayers": self.players,
                "gameData": {
                    "gameTime": 60.0,
                    "gameID": int(MATCH_CODE),
                    "gameVersion": VERSION,
                },
            }
        else:
            return {"ok": False, "error": f"unexpected URL {url}"}
        return {"ok": True, "body": payload}


def write_capture(
    paths: ingest.ArtifactPaths,
    metadata: dict,
    config: dict,
    *,
    completed: int,
) -> None:
    roster = [
        {
            "participantID": index + 1,
            "teamID": participant["teamId"],
            "championName": participant["champion"]["asset"],
            "playerName": participant["riotId"]["gameName"],
            "summonerName": participant["riotId"]["full"],
            "puuid": participant["puuid"],
        }
        for index, participant in enumerate(metadata["participants"])
    ]
    rows = [
        {
            "rfc461Schema": "rofl_coverage",
            "gameID": metadata["gameId"],
            "gameTime": 0,
            "source": "replay_api_playback",
            "startMs": config["startMs"],
            "endMs": config["endMs"],
            "stepMs": config["stepMs"],
            "provenance": {
                "source": "replay_api_playback",
                "sourceKind": "replay_api_playback",
                "artifact": metadata["basename"],
                "gameTimeUnit": "milliseconds",
                "positionCoverage": "full_at_sampled_frames",
                "hpCoverage": "none",
                "placeholderPolicy": "explicit_positionSource_only",
            },
        },
        {
            "rfc461Schema": "game_info",
            "gameID": metadata["gameId"],
            "gameName": metadata["matchCode"],
            "platformID": metadata["platformId"],
            "statsUpdateInterval": config["stepMs"],
            "participants": roster,
        },
    ]
    for game_time in config["sampleTimesMs"][:completed]:
        rows.append(
            {
                "rfc461Schema": "stats_update",
                "gameID": metadata["gameId"],
                "gameTime": game_time,
                "participants": [
                    {
                        **participant,
                        "position": {"x": 1000 + index, "z": 2000 + index},
                        "positionSource": "replay_api_focus_selection",
                    }
                    for index, participant in enumerate(roster)
                ],
            }
        )
    paths.match_dir.mkdir(parents=True, exist_ok=True)
    paths.events.write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n",
        encoding="utf-8",
    )
    ingest.atomic_write_json(
        paths.checkpoint,
        {
            "ok": completed == len(config["sampleTimesMs"]),
            "completedCount": completed,
            "sampleTimesMs": config["sampleTimesMs"],
        },
    )


class MetadataAndPathTests(unittest.TestCase):
    def test_metadata_identity_roster_and_champion_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            rofl = write_rofl(Path(tmp))
            metadata = rofl_metadata.inspect_rofl_metadata(rofl)
        self.assertEqual(metadata["platformId"], "BR1")
        self.assertEqual(metadata["matchCode"], MATCH_CODE)
        self.assertEqual(metadata["build"], VERSION)
        self.assertEqual(metadata["durationMs"], 62_000)
        self.assertEqual(metadata["rosterCount"], 10)
        self.assertTrue(metadata["stableIdentityComplete"])
        champions = {row["champion"]["raw"]: row["champion"] for row in metadata["participants"]}
        self.assertEqual(champions["MonkeyKing"]["display"], "Wukong")
        self.assertEqual(champions["MonkeyKing"]["asset"], "MonkeyKing")
        self.assertEqual(champions["Zaahen"]["display"], "Zaahen")

    def test_deterministic_paths_and_clamped_native_defaults(self):
        paths = ingest.artifact_paths(MATCH_CODE, artifact_root=Path("/tmp/artifacts/rofl"))
        self.assertEqual(
            paths.events,
            Path(f"/tmp/artifacts/rofl/{MATCH_CODE}/events.rfc461.jsonl"),
        )
        config = ingest.capture_config(
            {"durationMs": 62_345},
            start_ms=None,
            end_ms=None,
            step_ms=1_000,
        )
        self.assertEqual(config["startMs"], 60_000)
        self.assertEqual(config["endMs"], 62_345)
        self.assertEqual(config["effectiveEndMs"], 62_000)
        self.assertEqual(config["sampleTimesMs"], [60_000, 61_000, 62_000])

    def test_cli_default_and_recovery_phase_are_unambiguous(self):
        default = ingest.parse_args([f"BR1-{MATCH_CODE}.rofl"])
        recovery = ingest.parse_args(["build", f"BR1-{MATCH_CODE}.rofl"])
        hp_build = ingest.parse_args(
            [
                "build",
                f"BR1-{MATCH_CODE}.rofl",
                "--hp-evidence",
                "trusted-hp.json",
            ]
        )
        self.assertEqual(default.phase, "ingest")
        self.assertEqual(recovery.phase, "build")
        self.assertEqual(hp_build.hp_evidence.name, "trusted-hp.json")
        self.assertEqual(recovery.rofl.name, f"BR1-{MATCH_CODE}.rofl")
        with self.assertRaisesRegex(ingest.IngestError, "only valid"):
            ingest.parse_args(
                [
                    "validate",
                    f"BR1-{MATCH_CODE}.rofl",
                    "--hp-evidence",
                    "trusted-hp.json",
                ]
            )
        package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
        self.assertEqual(
            package["scripts"]["rofl:ingest"],
            "python3 scripts/rofl_ingest.py",
        )


class LockAndPreflightTests(unittest.TestCase):
    def test_lock_contention_and_release(self):
        self.assertIs(
            ingest.capture_phase.__kwdefaults__["capture_runner"],
            ingest.replay_capture._extract_replay_api_jsonl_after_guard,
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "controller.lock"
            first = ingest.ReplayControllerLock(path).acquire()
            with self.assertRaises(ingest.IngestError):
                ingest.ReplayControllerLock(path).acquire()
            first.release()
            second = ingest.ReplayControllerLock(path).acquire()
            second.release()

    def test_wrong_active_replay_fails_before_capture_or_artifact_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rofl = write_rofl(root)
            app = write_app(root)
            metadata = rofl_metadata.inspect_rofl_metadata(rofl)
            config = ingest.capture_config(
                metadata, start_ms=None, end_ms=None, step_ms=1_000
            )
            paths = ingest.artifact_paths(
                MATCH_CODE, artifact_root=root / "artifacts/rofl"
            )
            transport = PreflightTransport(
                duration_ms=metadata["durationMs"],
                wrong_first_champion=True,
            )
            runner = mock.Mock()
            with self.assertRaises(ingest.IngestError) as ctx:
                ingest.capture_phase(
                    rofl,
                    metadata,
                    config,
                    paths,
                    force=False,
                    app_path=app,
                    base_url="https://127.0.0.1:2999",
                    timeout=0.1,
                    transport=transport,
                    capture_runner=runner,
                )
            self.assertIn("wrong active replay champion", str(ctx.exception))
            runner.assert_not_called()
            self.assertFalse(paths.manifest.exists())
            self.assertFalse(paths.events.exists())
            self.assertTrue(all(method == "GET" for method, _url, _body in transport.calls))


class ResumeForceAndManifestTests(unittest.TestCase):
    def test_matching_partial_resumes_and_mismatch_needs_force(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rofl = write_rofl(root)
            app = write_app(root)
            metadata = rofl_metadata.inspect_rofl_metadata(rofl)
            config = ingest.capture_config(
                metadata, start_ms=None, end_ms=None, step_ms=1_000
            )
            paths = ingest.artifact_paths(
                MATCH_CODE, artifact_root=root / "artifacts/rofl"
            )
            manifest = ingest.make_manifest(metadata, config)
            ingest.atomic_write_json(paths.manifest, manifest)
            write_capture(paths, metadata, config, completed=2)
            transport = PreflightTransport(duration_ms=metadata["durationMs"])

            def resume_runner(_transport, **kwargs):
                self.assertTrue(kwargs["resume"])
                write_capture(
                    paths,
                    metadata,
                    config,
                    completed=len(config["sampleTimesMs"]),
                )
                return {
                    "ok": True,
                    "resumed": True,
                    "completedCount": len(config["sampleTimesMs"]),
                    "lastCompletedMs": config["effectiveEndMs"],
                    "restoreSucceeded": True,
                }

            result = ingest.capture_phase(
                rofl,
                metadata,
                config,
                paths,
                force=False,
                app_path=app,
                base_url="https://127.0.0.1:2999",
                timeout=0.1,
                transport=transport,
                capture_runner=resume_runner,
            )
            self.assertTrue(result["resumed"])
            self.assertEqual(
                ingest.assess_artifacts(paths, manifest, config)["state"],
                "complete",
            )
            before = paths.events.read_bytes()
            should_not_run = mock.Mock()
            noop = ingest.capture_phase(
                rofl,
                metadata,
                config,
                paths,
                force=False,
                app_path=app,
                base_url="https://127.0.0.1:2999",
                timeout=0.1,
                transport=transport,
                capture_runner=should_not_run,
            )
            self.assertTrue(noop["noop"])
            should_not_run.assert_not_called()
            self.assertEqual(paths.events.read_bytes(), before)

            changed = dict(config)
            changed["stepMs"] = 2_000
            changed["cadenceMs"] = 2_000
            changed["sampleTimesMs"] = [60_000, 62_000]
            changed["sampleCount"] = 2
            desired = ingest.make_manifest(metadata, changed)
            with self.assertRaises(ingest.IngestError):
                ingest.prepare_artifacts(paths, desired, changed, force=False)
            ingest.prepare_artifacts(paths, desired, changed, force=True)
            self.assertFalse(paths.events.exists())
            self.assertFalse(paths.checkpoint.exists())
            self.assertEqual(
                (ingest.load_json(paths.manifest)["capture"])["stepMs"],
                2_000,
            )

    def test_manifest_has_only_sanitized_relative_artifact_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            metadata = rofl_metadata.inspect_rofl_metadata(write_rofl(Path(tmp)))
        config = ingest.capture_config(
            metadata, start_ms=None, end_ms=None, step_ms=1_000
        )
        manifest = ingest.make_manifest(metadata, config)
        ingest.assert_sanitized(manifest, label="test manifest")
        text = json.dumps(manifest)
        self.assertNotIn(str(Path(tmp).resolve()), text)
        self.assertEqual(manifest["rofl"]["basename"], f"BR1-{MATCH_CODE}.rofl")
        self.assertEqual(
            manifest["artifacts"]["events"]["path"],
            "events.rfc461.jsonl",
        )


class PhaseRecoveryAndPublishTests(unittest.TestCase):
    def _ready_capture(self, root: Path):
        rofl = write_rofl(root)
        metadata = rofl_metadata.inspect_rofl_metadata(rofl)
        config = ingest.capture_config(
            metadata, start_ms=None, end_ms=None, step_ms=1_000
        )
        paths = ingest.artifact_paths(
            MATCH_CODE, artifact_root=root / "artifacts/rofl"
        )
        ingest.atomic_write_json(paths.manifest, ingest.make_manifest(metadata, config))
        write_capture(
            paths,
            metadata,
            config,
            completed=len(config["sampleTimesMs"]),
        )
        return metadata, config, paths

    def test_build_validate_publish_recovery_and_sanitization(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            metadata, config, paths = self._ready_capture(root)

            def build_runner(command):
                if Path(command[1]).name == "jsonl_to_timeline.py":
                    output = Path(command[command.index("-o") + 1])
                    ingest.atomic_write_json(
                        output,
                        {
                            "id": "wrong",
                            "name": "wrong",
                            "source": "replay_api_playback",
                            "provenance": {
                                "source": "replay_api_playback",
                                "sourceKind": "replay_api_playback",
                                "artifact": str(paths.events.resolve()),
                                "positionCoverage": "full_at_sampled_frames",
                                "hpCoverage": "none",
                                "motionAudit": {
                                    "version": "motion-audit-v1",
                                    "segmentCount": 0,
                                    "discontinuityCount": 0,
                                    "deathRespawnCount": 0,
                                    "recallTeleportCount": 0,
                                    "unexplainedCount": 0,
                                    "maxDisplacementMapUnits": 0,
                                },
                            },
                            "durationMs": config["endMs"],
                            "participants": [
                                {
                                    "participantID": index + 1,
                                    "summonerName": participant["riotId"]["full"],
                                    "championName": participant["champion"]["display"],
                                    "teamID": participant["teamId"],
                                    "role": participant["role"],
                                }
                                for index, participant in enumerate(
                                    metadata["participants"]
                                )
                            ],
                            "frameCount": 1,
                            "frames": [{"t": config["endMs"], "units": []}],
                            "hasCareerStats": False,
                        },
                    )
                return subprocess.CompletedProcess(command, 0, "", "")

            ingest.build_phase(
                metadata,
                config,
                paths,
                command_runner=build_runner,
            )
            timeline = ingest.load_json(paths.timeline)
            self.assertEqual(timeline["id"], MATCH_CODE)
            self.assertEqual(
                timeline["provenance"]["artifact"],
                "events.rfc461.jsonl",
            )
            manifest_after_build = ingest.load_json(paths.manifest)
            self.assertEqual(
                manifest_after_build["motionQA"]["version"],
                "motion-audit-v1",
            )

            validation_report = {
                "ok": True,
                "motionAudit": timeline["provenance"]["motionAudit"],
                "productPublication": {
                    "ok": True,
                    "calculatorReady": False,
                },
            }

            def validator(command):
                return subprocess.CompletedProcess(
                    command,
                    0,
                    json.dumps(validation_report),
                    "",
                )

            ingest.validate_phase(
                metadata,
                config,
                paths,
                command_runner=validator,
            )
            manifest_after_validation = ingest.load_json(paths.manifest)
            self.assertEqual(
                manifest_after_validation["validation"]["motionAudit"][
                    "discontinuityCount"
                ],
                0,
            )
            published = ingest.publish_phase(
                metadata,
                config,
                paths,
                publish_root=root / "public/data/matches",
            )
            self.assertTrue(published["ok"])
            target = root / f"public/data/matches/{MATCH_CODE}"
            public_manifest = ingest.load_json(target / "manifest.json")
            public_timeline = ingest.load_json(target / "timeline.json")
            ingest.assert_sanitized(public_manifest, label="public manifest")
            ingest.assert_sanitized(public_timeline, label="public timeline")
            index = ingest.load_json(root / "public/data/matches/index.json")
            self.assertEqual(index["defaultMatchCode"], MATCH_CODE)
            self.assertEqual(
                [entry["matchCode"] for entry in index["matches"]],
                [MATCH_CODE],
            )
            self.assertEqual(published["registry"]["matchCount"], 1)

    def test_optional_trusted_hp_build_is_durable_and_not_calculator_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            metadata, config, paths = self._ready_capture(root)
            rows = [
                json.loads(line)
                for line in paths.events.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            for row in rows:
                if row.get("rfc461Schema") != "stats_update":
                    continue
                for participant in row["participants"]:
                    participant["healthSource"] = "unavailable_replay_api"
                    participant["combatStatsSource"] = "unavailable_replay_api"
                    participant["abilityRanksSource"] = "unavailable_replay_api"
            paths.events.write_text(
                "\n".join(json.dumps(row) for row in rows) + "\n",
                encoding="utf-8",
            )
            capture_manifest = ingest.load_json(paths.manifest)
            capture_manifest["productGates"]["activeReplayIdentityVerified"] = True
            capture_manifest["productGates"]["captureComplete"] = True
            ingest.atomic_write_json(paths.manifest, capture_manifest)
            bindings = [
                {
                    "puuid": participant["puuid"],
                    "fullRiotId": participant["riotId"]["full"],
                    "champion": (
                        (participant.get("champion") or {}).get("asset")
                        or (participant.get("champion") or {}).get("raw")
                        or f"Champion{index}"
                    ),
                    "netId": 1000 + index,
                }
                for index, participant in enumerate(
                    metadata["participants"],
                    start=1,
                )
            ]
            evidence = {
                "schema": "rofl-trusted-hp-v1",
                "match": {
                    "platformId": metadata["platformId"],
                    "matchCode": metadata["matchCode"],
                    "gameId": metadata["gameId"],
                    "gameName": metadata["matchCode"],
                },
                "rofl": {
                    "patch": metadata["patch"],
                    "build": metadata["build"],
                    "sha256": metadata["sha256"],
                },
                "rosterHash": metadata["rosterHash"],
                "provenance": {
                    "sourceKind": "rofl2_replication_decrypt_timed_identity_bound",
                    "timed": True,
                    "staticSnapshot": False,
                    "fixture": False,
                    "createHeroOrderFallback": False,
                },
                "identityBinding": {
                    "method": "stable_identity_to_net_id",
                    "complete": True,
                    "participants": bindings,
                },
                "timing": {
                    "unit": "milliseconds",
                    "clock": "replay_game_time",
                    "toleranceMs": 0,
                },
                "samples": [
                    {
                        "gameTimeMs": game_time,
                        "units": [
                            {
                                "netId": binding["netId"],
                                "mHP": 500 + index,
                                "mMaxHP": 1000 + index,
                                "mMaxHPExplicit": True,
                            }
                            for index, binding in enumerate(bindings, start=1)
                        ],
                    }
                    for game_time in config["sampleTimesMs"]
                ],
            }
            evidence_path = root / "trusted-hp.json"
            evidence_path.write_text(json.dumps(evidence), encoding="utf-8")

            def build_runner(command):
                script_name = Path(command[1]).name
                if script_name == "fuse_replay_api_hp.py":
                    return subprocess.run(
                        command,
                        cwd=str(ROOT),
                        capture_output=True,
                        text=True,
                    )
                if script_name == "jsonl_to_timeline.py":
                    import jsonl_to_timeline

                    output = Path(command[command.index("-o") + 1])
                    timeline = jsonl_to_timeline.build_timeline(
                        Path(command[2]),
                        timeline_id=MATCH_CODE,
                        name=MATCH_CODE,
                        patch=metadata["patch"],
                    )
                    ingest.atomic_write_json(output, timeline)
                return subprocess.CompletedProcess(command, 0, "", "")

            ingest.build_phase(
                metadata,
                config,
                paths,
                hp_evidence=evidence_path,
                command_runner=build_runner,
            )
            manifest = ingest.load_json(paths.manifest)
            self.assertTrue(paths.hp_evidence.is_file())
            self.assertTrue(paths.hp_events.is_file())
            self.assertEqual(manifest["sourceCoverage"]["hp"], "full")
            self.assertEqual(manifest["sourceCoverage"]["combatStats"], "none")
            self.assertEqual(manifest["sourceCoverage"]["abilityRanks"], "none")
            self.assertTrue(manifest["productGates"]["hpTrusted"])
            self.assertFalse(manifest["trustedHp"]["combatStatsKnown"])
            self.assertFalse(manifest["trustedHp"]["abilityRanksKnown"])
            self.assertEqual(
                ingest.load_json(paths.timeline)["provenance"]["artifact"],
                "events.hp-trusted.rfc461.jsonl",
            )

            validated = ingest.validate_phase(metadata, config, paths)
            self.assertTrue(validated["ok"])
            product = validated["report"]["productPublication"]
            self.assertTrue(product["hpTrusted"])
            self.assertFalse(product["calculatorReady"])
            after = ingest.load_json(paths.manifest)
            self.assertTrue(after["validation"]["hpTrusted"])
            self.assertFalse(after["productGates"]["calculatorReady"])
            tampered = ingest.load_json(paths.hp_evidence)
            tampered["samples"][0]["units"][0]["mHP"] += 1
            ingest.atomic_write_json(paths.hp_evidence, tampered, compact=True)
            with self.assertRaisesRegex(ingest.IngestError, "hash changed"):
                ingest.validate_phase(metadata, config, paths)
            paths.hp_evidence.unlink()
            with self.assertRaisesRegex(ingest.IngestError, "evidence is missing"):
                ingest.build_phase(metadata, config, paths)

    def test_publication_refused_after_fixture_validation_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            metadata, config, paths = self._ready_capture(root)
            ingest.atomic_write_json(
                paths.timeline,
                {
                    "id": MATCH_CODE,
                    "name": MATCH_CODE,
                    "provenance": {
                        "sourceKind": "schema_proof_fixture_hp_merge",
                        "artifact": "events.rfc461.jsonl",
                    },
                    "frames": [],
                },
            )

            def rejected(command):
                return subprocess.CompletedProcess(
                    command,
                    2,
                    "",
                    "FAIL: fixture provenance cannot publish",
                )

            with self.assertRaises(ingest.IngestError):
                ingest.validate_phase(
                    metadata,
                    config,
                    paths,
                    command_runner=rejected,
                )
            with self.assertRaises(ingest.IngestError):
                ingest.publish_phase(
                    metadata,
                    config,
                    paths,
                    publish_root=root / "public/data/matches",
                )
            self.assertFalse((root / f"public/data/matches/{MATCH_CODE}").exists())


if __name__ == "__main__":
    unittest.main()
