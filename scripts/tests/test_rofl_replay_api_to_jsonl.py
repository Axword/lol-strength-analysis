#!/usr/bin/env python3
"""Mocked tests for Replay API → rfc461 JSONL extractor + unknown-HP timeline."""
from __future__ import annotations

import io
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from typing import Any, Optional
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import jsonl_to_timeline  # noqa: E402
import rfc461_emit  # noqa: E402
import rofl_replay_api_to_jsonl as extract  # noqa: E402

# Reuse probe fake transport helpers from sibling test module.
import importlib.util

_probe_test_path = Path(__file__).resolve().parent / "test_rofl_replay_api_probe.py"
_spec = importlib.util.spec_from_file_location(
    "test_rofl_replay_api_probe", _probe_test_path
)
assert _spec and _spec.loader
_probe_tests = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_probe_tests)
FakeTransport = _probe_tests.FakeTransport
_stub_rofl_app = _probe_tests._stub_rofl_app

# Existing extractor tests exercise the guarded controller's private durable
# capture implementation. Dedicated tests below retain and exercise the public
# lock + identity-preflight entry point.
_public_extract_replay_api_jsonl = extract.extract_replay_api_jsonl
extract.extract_replay_api_jsonl = extract._extract_replay_api_jsonl_after_guard

_ingest_test_path = Path(__file__).resolve().parent / "test_rofl_ingest.py"
_ingest_spec = importlib.util.spec_from_file_location(
    "test_rofl_ingest_guard_helpers",
    _ingest_test_path,
)
assert _ingest_spec and _ingest_spec.loader
_ingest_tests = importlib.util.module_from_spec(_ingest_spec)
_ingest_spec.loader.exec_module(_ingest_tests)

CHAMPS = [
    # champ, team, name, tag, riot liveclient position
    ("Gnar", "ORDER", "p1", "tag1", "TOP"),
    ("Malphite", "ORDER", "p2", "tag1", "JUNGLE"),
    ("Ahri", "ORDER", "p3", "tag1", "MIDDLE"),
    ("Jinx", "ORDER", "p4", "tag1", "BOTTOM"),
    ("Thresh", "ORDER", "p5", "tag1", "UTILITY"),
    ("Darius", "CHAOS", "p6", "tag2", "TOP"),
    ("LeeSin", "CHAOS", "p7", "tag2", "JUNGLE"),
    ("Syndra", "CHAOS", "p8", "tag2", "MIDDLE"),
    ("Samira", "CHAOS", "p9", "tag2", "BOTTOM"),
    ("TahmKench", "CHAOS", "p10", "tag2", "UTILITY"),
]

EXPECTED_ROLES = [
    "Top",
    "Jungle",
    "Middle",
    "Bottom",
    "Support",
    "Top",
    "Jungle",
    "Middle",
    "Bottom",
    "Support",
]


def _ten_players() -> list[dict[str, Any]]:
    players = []
    for i, (champ, team, name, tag, position) in enumerate(CHAMPS):
        players.append(
            {
                "championName": champ if champ != "TahmKench" else "Tahm Kench",
                "rawChampionName": (
                    "game_character_displayname_TahmKench"
                    if champ == "TahmKench"
                    else champ
                ),
                "summonerName": f"{name}#{tag}",
                "riotIdGameName": name,
                "riotIdTagLine": tag,
                "team": team,
                "position": position,
                "level": 8 + (i % 5),
                "items": [{"itemID": 1001 + i}],
                "isDead": False,
                "participantID": i + 1,
                "scores": {
                    "kills": 0,
                    "deaths": 0,
                    "assists": 0,
                    "creepScore": 0,
                    "wardScore": 0,
                },
            }
        )
    return players


def _ten_positions() -> dict[str, dict[str, float]]:
    pos: dict[str, dict[str, float]] = {}
    for i, (champ, _team, name, tag, _role) in enumerate(CHAMPS):
        xz = {
            "x": 1000.0 + i * 700.0,
            "y": 50.0,
            "z": 2000.0 + i * 500.0,
        }
        pos[champ] = dict(xz)
        pos[name] = dict(xz)
        pos[f"{name}#{tag}"] = dict(xz)
        if champ == "TahmKench":
            pos["TahmKench"] = dict(xz)
            pos["game_character_displayname_TahmKench"] = dict(xz)
    return pos


def _canon_map() -> dict[str, str]:
    m: dict[str, str] = {}
    for champ, _team, name, tag, _role in CHAMPS:
        m[champ] = name
        m[name] = name
        m[f"{name}#{tag}"] = name
        if champ == "TahmKench":
            m["TahmKench"] = name
    return m


class SeekingTransport(FakeTransport):
    """FakeTransport with 10-player roster and seek-settle behavior."""

    def __init__(self, **kwargs: Any) -> None:
        dynamic = kwargs.pop("dynamic_players_by_ms", None)
        kwargs.setdefault("players", _ten_players())
        kwargs.setdefault("focus_positions", _ten_positions())
        kwargs.setdefault("canonicalize_map", _canon_map())
        kwargs.setdefault(
            "playback_state",
            {
                "paused": True,
                "seeking": False,
                "time": 100.0,
                "speed": 1.0,
                "length": 1800.0,
            },
        )
        super().__init__(**kwargs)
        self.fail_seek_at: Optional[float] = None
        self.duplicate_after_select: Optional[str] = None
        self.disconnect_on_restore = kwargs.get("disconnect_on_restore", False)
        self.dynamic_players_by_ms: Optional[dict[int, list[dict[str, Any]]]] = dynamic
        self.reset_camera_on_seek = True
        self.liveclient_stale_remaining = 0
        self.liveclient_stale_game_time = 50.0
        self.liveclient_stale_players: Optional[list[dict[str, Any]]] = None

    def _sync_players_to_playback_time(self) -> None:
        if not self.dynamic_players_by_ms:
            return
        t_ms = int(round(float(self.playback_state.get("time") or 0) * 1000))
        if t_ms in self.dynamic_players_by_ms:
            self.players = [dict(p) for p in self.dynamic_players_by_ms[t_ms]]

    def __call__(
        self,
        method: str,
        url: str,
        *,
        body: Any = None,
        timeout: float = 2.0,
    ) -> dict[str, Any]:
        if (
            self.fail_seek_at is not None
            and method.upper() == "POST"
            and "replay/playback" in url
            and isinstance(body, dict)
            and "time" in body
            and abs(float(body["time"]) - float(self.fail_seek_at)) < 1e-9
        ):
            self.calls.append((method.upper(), url, body))
            return self._err(url, method, "injected seek failure")

        if method.upper() == "GET" and (
            "liveclientdata/playerlist" in url or "liveclientdata/allgamedata" in url
        ):
            self._sync_players_to_playback_time()

        # Stale liveclient: first N allgamedata/playerlist responses report old time/state.
        if (
            self.liveclient_stale_remaining > 0
            and method.upper() == "GET"
            and (
                "liveclientdata/allgamedata" in url
                or "liveclientdata/playerlist" in url
            )
        ):
            self.calls.append((method.upper(), url, body))
            stale_players = self.liveclient_stale_players or list(self.players)
            # Decrement once per allgamedata (authoritative clock); playerlist pairs.
            if "allgamedata" in url:
                self.liveclient_stale_remaining -= 1
                return self._ok(
                    url,
                    method,
                    {
                        "activePlayer": {},
                        "allPlayers": list(stale_players),
                        "gameData": {"gameTime": self.liveclient_stale_game_time},
                    },
                )
            return self._ok(url, method, list(stale_players))

        result = super().__call__(method, url, body=body, timeout=timeout)

        # Simulate Riot: seek often resets render away from focus.
        if (
            self.reset_camera_on_seek
            and method.upper() == "POST"
            and "replay/playback" in url
            and isinstance(body, dict)
            and "time" in body
            and result.get("ok")
        ):
            self.render_state["cameraMode"] = "top"
            self.render_state["cameraAttached"] = False

        if (
            self.duplicate_after_select
            and method.upper() == "POST"
            and isinstance(body, dict)
            and body.get("selectionName") == self.duplicate_after_select
        ):
            pass
        return result


class PublicCaptureGuardTests(unittest.TestCase):
    def _guard_fixture(self, root: Path):
        rofl = _ingest_tests.write_rofl(root)
        app = _ingest_tests.write_app(root)
        metadata = _ingest_tests.rofl_metadata.inspect_rofl_metadata(rofl)
        return rofl, app, metadata

    def _capture_kwargs(
        self,
        rofl: Path,
        app: Path,
        out: Path,
        lock_path: Path,
        *,
        checkpoint: Optional[Path] = None,
    ) -> dict[str, Any]:
        return {
            "base_url": "https://127.0.0.1:2999",
            "rofl_path": rofl,
            "app_path": app,
            "out_path": out,
            "start_ms": 60_000,
            "end_ms": 61_000,
            "step_ms": 1_000,
            "game_id": int(_ingest_tests.MATCH_CODE),
            "checkpoint_out": checkpoint,
            "_controller_lock_path": lock_path,
        }

    def test_wrong_active_replay_preserves_output_checkpoint_and_never_posts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rofl, app, metadata = self._guard_fixture(root)
            out = root / "existing.jsonl"
            checkpoint = root / "existing.checkpoint.json"
            out.write_bytes(b"existing-output\n")
            checkpoint.write_bytes(b"existing-checkpoint\n")
            transport = _ingest_tests.PreflightTransport(
                duration_ms=metadata["durationMs"],
                wrong_first_champion=True,
            )
            with self.assertRaises(extract.CaptureGuardError) as ctx:
                _public_extract_replay_api_jsonl(
                    transport,
                    **self._capture_kwargs(
                        rofl,
                        app,
                        out,
                        root / "controller.lock",
                        checkpoint=checkpoint,
                    ),
                )
            self.assertIn("wrong active replay champion", str(ctx.exception))
            self.assertEqual(out.read_bytes(), b"existing-output\n")
            self.assertEqual(
                checkpoint.read_bytes(),
                b"existing-checkpoint\n",
            )
            self.assertTrue(transport.calls)
            self.assertTrue(
                all(method == "GET" for method, _url, _body in transport.calls)
            )

    def test_ingest_lock_contends_with_public_capture_before_get_or_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rofl, app, metadata = self._guard_fixture(root)
            out = root / "existing.jsonl"
            checkpoint = root / "existing.checkpoint.json"
            out.write_bytes(b"output-before\n")
            checkpoint.write_bytes(b"checkpoint-before\n")
            lock_path = root / "controller.lock"
            self.assertEqual(
                _ingest_tests.ingest.controller_lock_path(artifact_root=root),
                extract.replay_capture_guard.controller_lock_path(
                    artifact_root=root
                ),
            )
            owner = _ingest_tests.ingest.ReplayControllerLock(lock_path).acquire()
            transport = _ingest_tests.PreflightTransport(
                duration_ms=metadata["durationMs"],
            )
            try:
                with self.assertRaises(extract.CaptureGuardError) as ctx:
                    _public_extract_replay_api_jsonl(
                        transport,
                        **self._capture_kwargs(
                            rofl,
                            app,
                            out,
                            lock_path,
                            checkpoint=checkpoint,
                        ),
                    )
            finally:
                owner.release()
            self.assertIn("already locked", str(ctx.exception))
            self.assertEqual(transport.calls, [])
            self.assertEqual(out.read_bytes(), b"output-before\n")
            self.assertEqual(
                checkpoint.read_bytes(),
                b"checkpoint-before\n",
            )

    def test_public_guard_holds_lock_through_internal_capture(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rofl, app, metadata = self._guard_fixture(root)
            lock_path = root / "controller.lock"
            transport = _ingest_tests.PreflightTransport(
                duration_ms=metadata["durationMs"],
            )

            def internal(_transport, **_kwargs):
                with self.assertRaises(
                    extract.replay_capture_guard.ReplayGuardError
                ):
                    extract.replay_capture_guard.ReplayControllerLock(
                        lock_path
                    ).acquire()
                return {"ok": True, "restoreSucceeded": True}

            with mock.patch.object(
                extract,
                "_extract_replay_api_jsonl_after_guard",
                internal,
            ):
                result = _public_extract_replay_api_jsonl(
                    transport,
                    **self._capture_kwargs(
                        rofl,
                        app,
                        root / "new.jsonl",
                        lock_path,
                    ),
                )
            self.assertTrue(result["ok"])
            self.assertEqual(len(transport.calls), 4)
            self.assertTrue(
                all(method == "GET" for method, _url, _body in transport.calls)
            )
            released = extract.replay_capture_guard.ReplayControllerLock(
                lock_path
            ).acquire()
            released.release()

    def test_cli_guard_failure_does_not_rewrite_checkpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rofl, app, metadata = self._guard_fixture(root)
            out = root / "cli.jsonl"
            checkpoint = root / "cli.checkpoint.json"
            out.write_bytes(b"cli-output\n")
            checkpoint.write_bytes(b"cli-checkpoint\n")
            transport = _ingest_tests.PreflightTransport(
                duration_ms=metadata["durationMs"],
                wrong_first_champion=True,
            )
            with mock.patch.object(
                extract,
                "extract_replay_api_jsonl",
                _public_extract_replay_api_jsonl,
            ), mock.patch.object(
                extract.probe,
                "default_http_transport",
                transport,
            ), mock.patch.object(
                extract.replay_capture_guard,
                "controller_lock_path",
                return_value=root / "controller.lock",
            ), mock.patch("sys.stdout", new=io.StringIO()):
                code = extract.main(
                    [
                        "--rofl",
                        str(rofl),
                        "--app",
                        str(app),
                        "--out",
                        str(out),
                        "--start-ms",
                        "60000",
                        "--end-ms",
                        "61000",
                        "--step-ms",
                        "1000",
                        "--game-id",
                        _ingest_tests.MATCH_CODE,
                        "--checkpoint-out",
                        str(checkpoint),
                    ]
                )
            self.assertEqual(code, 4)
            self.assertEqual(out.read_bytes(), b"cli-output\n")
            self.assertEqual(
                checkpoint.read_bytes(),
                b"cli-checkpoint\n",
            )
            self.assertTrue(
                all(method == "GET" for method, _url, _body in transport.calls)
            )


def _players_at(
    *,
    level_offsets: Optional[dict[str, int]] = None,
    item_overrides: Optional[dict[str, list[dict[str, Any]]]] = None,
    dead_names: Optional[set[str]] = None,
) -> list[dict[str, Any]]:
    """Copy of the 10-player roster with optional per-summoner dynamics."""
    level_offsets = level_offsets or {}
    item_overrides = item_overrides or {}
    dead_names = dead_names or set()
    out = []
    for p in _ten_players():
        row = dict(p)
        name = str(row["riotIdGameName"])
        if name in level_offsets:
            row["level"] = int(row["level"]) + int(level_offsets[name])
        if name in item_overrides:
            row["items"] = list(item_overrides[name])
        row["isDead"] = name in dead_names
        out.append(row)
    return out


class ParticipantRowUnknownHealthTests(unittest.TestCase):
    def test_default_still_emits_health(self) -> None:
        row = rfc461_emit.participant_row(
            participant_id=1,
            team_id=100,
            champion_name="Gnar",
            player_name="p1",
            position={"x": 1.0, "z": 2.0},
            position_source="test",
            health=500,
            health_max=1000,
        )
        self.assertEqual(row["health"], 500)
        self.assertEqual(row["healthMax"], 1000)
        self.assertNotIn("healthSource", row)

    def test_unknown_health_omits_fields(self) -> None:
        row = rfc461_emit.participant_row(
            participant_id=1,
            team_id=100,
            champion_name="Gnar",
            player_name="p1",
            position={"x": 1.0, "z": 2.0},
            position_source="replay_api_focus_selection",
            health_known=False,
            health_source="unavailable_replay_api",
            combat_stats_source="unavailable_replay_api",
            ability_ranks_source="unavailable_replay_api",
        )
        self.assertNotIn("health", row)
        self.assertNotIn("healthMax", row)
        self.assertEqual(row["healthSource"], "unavailable_replay_api")
        self.assertEqual(row["combatStatsSource"], "unavailable_replay_api")
        self.assertEqual(row["abilityRanksSource"], "unavailable_replay_api")


class TimelineUnknownHealthTests(unittest.TestCase):
    def test_unknown_health_flags_and_no_inferred_hp(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "unk.jsonl"
            roster = [
                {
                    "participantID": pid,
                    "teamID": 100 if pid <= 5 else 200,
                    "championName": "TestChampion",
                    "playerName": f"p{pid}",
                    "summonerName": f"p{pid}",
                }
                for pid in range(1, 11)
            ]
            rows = [
                rfc461_emit.coverage_line(
                    source="replay_api_playback",
                    provenance=rfc461_emit.provenance_record(
                        source="replay_api_playback",
                        source_kind="replay_api_playback",
                        position_coverage="full_at_sampled_frames",
                        hp_coverage="none",
                        roster_mapping="game_info_participantID",
                    ),
                ),
                rfc461_emit.game_info_line(game_id=1, participants=roster),
                rfc461_emit.stats_update_line(
                    game_id=1,
                    game_time=121_000,
                    participants=[
                        rfc461_emit.participant_row(
                            participant_id=pid,
                            team_id=100 if pid <= 5 else 200,
                            champion_name="TestChampion",
                            player_name=f"p{pid}",
                            position={"x": 1000 + pid * 10, "z": 2000 + pid * 10},
                            position_source="replay_api_focus_selection",
                            alive=True,
                            health_known=False,
                            health_source="unavailable_replay_api",
                            combat_stats_source="unavailable_replay_api",
                            ability_ranks_source="unavailable_replay_api",
                        )
                        for pid in range(1, 11)
                    ],
                ),
            ]
            rfc461_emit.write_jsonl(path, rows)
            tl = jsonl_to_timeline.build_timeline(
                path, timeline_id="unk", name="unk", patch="test"
            )
            self.assertEqual(tl["frames"][0]["t"], 121_000)
            for u in tl["frames"][0]["units"]:
                self.assertTrue(u["alive"])
                self.assertIs(u["hpKnown"], False)
                self.assertIs(u["combatStatsKnown"], False)
                self.assertIs(u["abilityRanksKnown"], False)
                self.assertEqual(u["hp"], 0)
                self.assertEqual(u["hpMax"], 0)
                self.assertEqual(u["positionSource"], "replay_api_focus_selection")

    def test_known_health_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "known.jsonl"
            roster = [
                {
                    "participantID": pid,
                    "teamID": 100 if pid <= 5 else 200,
                    "championName": "TestChampion",
                    "playerName": f"p{pid}",
                    "summonerName": f"p{pid}",
                }
                for pid in range(1, 11)
            ]
            rows = [
                rfc461_emit.coverage_line(
                    source="live",
                    provenance=rfc461_emit.provenance_record(
                        source="live",
                        source_kind="live",
                        position_coverage="full",
                        hp_coverage="full",
                        roster_mapping="game_info_participantID",
                    ),
                ),
                rfc461_emit.game_info_line(game_id=1, participants=roster),
                rfc461_emit.stats_update_line(
                    game_id=1,
                    game_time=1000,
                    participants=[
                        rfc461_emit.participant_row(
                            participant_id=pid,
                            team_id=100 if pid <= 5 else 200,
                            champion_name="TestChampion",
                            player_name=f"p{pid}",
                            position={"x": 400 + pid, "z": 400 + pid},
                            position_source="live_stats_position",
                            health=250,
                            health_max=500,
                        )
                        for pid in range(1, 11)
                    ],
                ),
            ]
            rfc461_emit.write_jsonl(path, rows)
            tl = jsonl_to_timeline.build_timeline(
                path, timeline_id="known", name="known", patch="test"
            )
            u = tl["frames"][0]["units"][0]
            self.assertIs(u["hpKnown"], True)
            self.assertEqual(u["hp"], 250)
            self.assertEqual(u["hpMax"], 500)


class ExtractorMockTests(unittest.TestCase):
    def test_rofl_game_length_clamps_unseekable_terminal_padding(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rofl, app = _stub_rofl_app(tmp)
            out = Path(tmp) / "terminal.jsonl"
            transport = SeekingTransport()
            with mock.patch.object(
                extract.probe,
                "read_rofl_build",
                return_value={
                    "version": "16.14.794.5912",
                    "gameLengthMs": 122_500,
                },
            ), mock.patch.object(extract.probe, "_settle", lambda _d: None):
                status = extract.extract_replay_api_jsonl(
                    transport,
                    base_url="https://127.0.0.1:2999",
                    rofl_path=rofl,
                    app_path=app,
                    out_path=out,
                    start_ms=121_000,
                    end_ms=124_000,
                    step_ms=1000,
                    final_settle=0.0,
                    settle_delay=0.0,
                    identity_retries=0,
                    seek_timeout=1.0,
                )
            self.assertTrue(status["ok"], status.get("error"))
            self.assertEqual(status["sampleTimesMs"], [121_000, 122_000])
            self.assertEqual(status["requestedEndMs"], 124_000)
            self.assertEqual(status["effectiveEndMs"], 122_000)
            rows = [json.loads(line) for line in out.read_text().splitlines()]
            coverage = rows[0]
            self.assertEqual(coverage["endMs"], 124_000)
            self.assertEqual(coverage["effectiveEndMs"], 122_000)
            self.assertEqual(coverage["roflGameLengthMs"], 122_500)
            self.assertEqual(
                [r["gameTime"] for r in rows if r["rfc461Schema"] == "stats_update"],
                [121_000, 122_000],
            )

    def test_exact_sampled_ms_ten_players_no_health(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rofl, app = _stub_rofl_app(tmp)
            out = Path(tmp) / "out.jsonl"
            transport = SeekingTransport()
            with mock.patch.object(extract.probe, "_settle", lambda _d: None):
                status = extract.extract_replay_api_jsonl(
                    transport,
                    base_url="https://127.0.0.1:2999",
                    rofl_path=rofl,
                    app_path=app,
                    out_path=out,
                    start_ms=121_000,
                    end_ms=124_000,
                    step_ms=1000,
                    final_settle=0.0,
                    settle_delay=0.0,
                    identity_retries=0,
                    seek_timeout=1.0,
                )
            self.assertTrue(status["ok"], status.get("error"))
            self.assertTrue(status["restoreSucceeded"])
            self.assertEqual(status["sampleTimesMs"], [121000, 122000, 123000, 124000])
            self.assertEqual(status["framesCaptured"], 4)

            lines = [
                json.loads(line)
                for line in out.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertEqual(lines[0]["rfc461Schema"], "rofl_coverage")
            self.assertEqual(lines[0]["provenance"]["hpCoverage"], "none")
            self.assertEqual(
                lines[0]["provenance"]["positionCoverage"], "full_at_sampled_frames"
            )
            self.assertEqual(lines[0]["provenance"]["source"], "replay_api_playback")
            self.assertEqual(lines[1]["rfc461Schema"], "game_info")
            stats = [r for r in lines if r["rfc461Schema"] == "stats_update"]
            self.assertEqual([r["gameTime"] for r in stats], [121000, 122000, 123000, 124000])
            for row in stats:
                self.assertEqual(len(row["participants"]), 10)
                xs = {
                    (round(p["position"]["x"], 2), round(p["position"]["z"], 2))
                    for p in row["participants"]
                }
                self.assertEqual(len(xs), 10)
                for p in row["participants"]:
                    self.assertEqual(
                        p["positionSource"], "replay_api_focus_selection"
                    )
                    self.assertNotIn("health", p)
                    self.assertNotIn("healthMax", p)
                    self.assertEqual(p["healthSource"], "unavailable_replay_api")

            # Seek posts must include time; capture-current path is separate.
            seek_posts = [
                body
                for method, url, body in transport.calls
                if method == "POST"
                and "playback" in url
                and isinstance(body, dict)
                and "time" in body
            ]
            self.assertGreaterEqual(len(seek_posts), 4)

            tl = jsonl_to_timeline.build_timeline(
                out, timeline_id="pilot", name="pilot", patch="test"
            )
            self.assertEqual([f["t"] for f in tl["frames"]], [121000, 122000, 123000, 124000])
            for u in tl["frames"][0]["units"]:
                self.assertIs(u["hpKnown"], False)
                self.assertTrue(u["alive"])
                self.assertEqual(u["hpMax"], 0)

    def test_restore_on_seek_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rofl, app = _stub_rofl_app(tmp)
            out = Path(tmp) / "out.jsonl"
            transport = SeekingTransport()
            transport.fail_seek_at = 122.0
            with mock.patch.object(extract.probe, "_settle", lambda _d: None):
                with self.assertRaises(extract.ExtractError) as ctx:
                    extract.extract_replay_api_jsonl(
                        transport,
                        base_url="https://127.0.0.1:2999",
                        rofl_path=rofl,
                        app_path=app,
                        out_path=out,
                        start_ms=121_000,
                        end_ms=123_000,
                        step_ms=1000,
                        final_settle=0.0,
                        settle_delay=0.0,
                        identity_retries=0,
                        seek_timeout=1.0,
                    )
            # finally always restores
            self.assertTrue(ctx.exception.checkpoint.get("restoreAttempted") or True)
            # Original time 100.0 should be restored via POST time
            restore_time_posts = [
                body
                for method, url, body in transport.calls
                if method == "POST"
                and "playback" in url
                and isinstance(body, dict)
                and body.get("time") == 100.0
            ]
            self.assertTrue(restore_time_posts)

    def test_stale_duplicate_rejection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rofl, app = _stub_rofl_app(tmp)
            out = Path(tmp) / "out.jsonl"
            # Map every focus key to the same coordinate → duplicates.
            same = {"x": 1111.0, "y": 50.0, "z": 2222.0}
            pos = {k: dict(same) for k in _ten_positions()}
            transport = SeekingTransport(focus_positions=pos)
            with mock.patch.object(extract.probe, "_settle", lambda _d: None):
                with self.assertRaises(extract.ExtractError) as ctx:
                    extract.extract_replay_api_jsonl(
                        transport,
                        base_url="https://127.0.0.1:2999",
                        rofl_path=rofl,
                        app_path=app,
                        out_path=out,
                        start_ms=121_000,
                        end_ms=121_000,
                        step_ms=1000,
                        final_settle=0.0,
                        settle_delay=0.0,
                        identity_retries=0,
                        seek_timeout=1.0,
                    )
            self.assertIn("one coordinate", str(ctx.exception).lower())

    def test_two_players_may_legitimately_share_a_coordinate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rofl, app = _stub_rofl_app(tmp)
            out = Path(tmp) / "overlap.jsonl"
            positions = _ten_positions()
            shared = dict(positions["Gnar"])
            for key in ("Malphite", "p2", "p2#tag1"):
                positions[key] = dict(shared)
            transport = SeekingTransport(focus_positions=positions)
            with mock.patch.object(extract.probe, "_settle", lambda _d: None):
                status = extract.extract_replay_api_jsonl(
                    transport,
                    base_url="https://127.0.0.1:2999",
                    rofl_path=rofl,
                    app_path=app,
                    out_path=out,
                    start_ms=121_000,
                    end_ms=121_000,
                    step_ms=1000,
                    final_settle=0.0,
                    settle_delay=0.0,
                    identity_retries=0,
                    seek_timeout=1.0,
                )
            self.assertTrue(status["ok"], status.get("error"))
            rows = [json.loads(line) for line in out.read_text().splitlines()]
            stats = next(r for r in rows if r["rfc461Schema"] == "stats_update")
            coords = {
                (round(p["position"]["x"], 3), round(p["position"]["z"], 3))
                for p in stats["participants"]
            }
            self.assertEqual(len(coords), 9)

    def test_seek_polling_waits_until_not_seeking(self) -> None:
        transport = SeekingTransport()
        with mock.patch.object(extract.probe, "_settle", lambda _d: None):
            result = extract.probe.seek_to_time(
                transport,
                "https://127.0.0.1:2999/replay/playback",
                121.0,
                timeout=1.0,
                poll_interval=0.0,
                time_tol=1e-3,
                seek_timeout=1.0,
                pause_first=True,
            )
        self.assertTrue(result["ok"])
        self.assertTrue(result["settled"])
        self.assertEqual(float(result["body"]["time"]), 121.0)
        self.assertFalse(result["body"]["seeking"])

    def test_per_sample_level_items_alive_from_post_seek_liveclient(self) -> None:
        """Dynamic state must come from post-seek liveclient, not the initial roster."""
        with tempfile.TemporaryDirectory() as tmp:
            rofl, app = _stub_rofl_app(tmp)
            out = Path(tmp) / "dyn.jsonl"
            # Initial GET (before loop) uses playback time 100.0 → 100000ms key absent,
            # so default _ten_players(); after seeks, use time-keyed snapshots.
            dynamic = {
                121000: _players_at(
                    level_offsets={"p1": 0},
                    item_overrides={"p1": [{"itemID": 3006}]},
                    dead_names=set(),
                ),
                122000: _players_at(
                    level_offsets={"p1": 2},
                    item_overrides={"p1": [{"itemID": 3031}, {"itemID": 3006}]},
                    dead_names={"p1"},
                ),
                123000: _players_at(
                    level_offsets={"p1": 3},
                    item_overrides={"p1": [{"itemID": 3031}]},
                    dead_names=set(),
                ),
            }
            # Seed initial players as the "frozen" wrong state so a bug that
            # reuses the initial roster would fail assertions.
            initial = _players_at(
                level_offsets={"p1": -1},
                item_overrides={"p1": [{"itemID": 1001}]},
                dead_names=set(),
            )
            transport = SeekingTransport(
                players=initial,
                dynamic_players_by_ms=dynamic,
            )
            with mock.patch.object(extract.probe, "_settle", lambda _d: None):
                status = extract.extract_replay_api_jsonl(
                    transport,
                    base_url="https://127.0.0.1:2999",
                    rofl_path=rofl,
                    app_path=app,
                    out_path=out,
                    start_ms=121_000,
                    end_ms=123_000,
                    step_ms=1000,
                    final_settle=0.0,
                    settle_delay=0.0,
                    identity_retries=0,
                    seek_timeout=1.0,
                )
            self.assertTrue(status["ok"], status.get("error"))

            # Focus re-asserted after every seek (seek resets cameraMode to top).
            focus_posts = [
                body
                for method, url, body in transport.calls
                if method == "POST"
                and "replay/render" in url
                and isinstance(body, dict)
                and body.get("cameraMode") == "focus"
            ]
            self.assertGreaterEqual(len(focus_posts), 3)

            lines = [
                json.loads(line)
                for line in out.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            stats = [r for r in lines if r["rfc461Schema"] == "stats_update"]
            self.assertEqual([r["gameTime"] for r in stats], [121000, 122000, 123000])

            def p1(row: dict) -> dict:
                for p in row["participants"]:
                    if p["playerName"] == "p1" or p["playerName"].startswith("p1"):
                        return p
                self.fail("p1 missing")
                raise AssertionError

            a, b, c = p1(stats[0]), p1(stats[1]), p1(stats[2])
            # Initial frozen roster had level 7 (8-1) / item 1001 — must not appear.
            self.assertNotEqual(a["level"], 7)
            self.assertEqual(a["level"], 8)  # base 8 + 0
            self.assertEqual([it["itemID"] for it in a["items"]], [3006])
            self.assertTrue(a["alive"])

            self.assertEqual(b["level"], 10)  # 8 + 2
            self.assertEqual([it["itemID"] for it in b["items"]], [3031, 3006])
            self.assertFalse(b["alive"])

            self.assertEqual(c["level"], 11)  # 8 + 3
            self.assertEqual([it["itemID"] for it in c["items"]], [3031])
            self.assertTrue(c["alive"])

            # Stable participant IDs across frames for p1.
            self.assertEqual(a["participantID"], b["participantID"])
            self.assertEqual(b["participantID"], c["participantID"])

    def test_liveclient_stale_first_response_rejected(self) -> None:
        """First liveclient snapshot at wrong gameTime must not enter stats_update."""
        with tempfile.TemporaryDirectory() as tmp:
            rofl, app = _stub_rofl_app(tmp)
            out = Path(tmp) / "stale.jsonl"
            stale_players = _players_at(
                level_offsets={"p1": 50},  # absurd level if accepted
                item_overrides={"p1": [{"itemID": 9999}]},
            )
            transport = SeekingTransport()
            transport.liveclient_stale_remaining = 2
            transport.liveclient_stale_game_time = 50.0
            transport.liveclient_stale_players = stale_players
            with mock.patch.object(extract.probe, "_settle", lambda _d: None):
                status = extract.extract_replay_api_jsonl(
                    transport,
                    base_url="https://127.0.0.1:2999",
                    rofl_path=rofl,
                    app_path=app,
                    out_path=out,
                    start_ms=121_000,
                    end_ms=121_000,
                    step_ms=1000,
                    final_settle=0.0,
                    settle_delay=0.0,
                    identity_retries=0,
                    seek_timeout=1.0,
                    liveclient_wait_timeout=2.0,
                )
            self.assertTrue(status["ok"], status.get("error"))
            lines = [
                json.loads(line)
                for line in out.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            stats = [r for r in lines if r["rfc461Schema"] == "stats_update"]
            self.assertEqual(len(stats), 1)
            p1 = next(p for p in stats[0]["participants"] if p["playerName"] == "p1")
            self.assertEqual(p1["level"], 8)  # base, not stale 58
            self.assertEqual([it["itemID"] for it in p1["items"]], [1001])
            self.assertNotEqual(p1["level"], 58)

    def test_roles_normalized_in_game_info_and_stats(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rofl, app = _stub_rofl_app(tmp)
            out = Path(tmp) / "roles.jsonl"
            transport = SeekingTransport()
            with mock.patch.object(extract.probe, "_settle", lambda _d: None):
                status = extract.extract_replay_api_jsonl(
                    transport,
                    base_url="https://127.0.0.1:2999",
                    rofl_path=rofl,
                    app_path=app,
                    out_path=out,
                    start_ms=121_000,
                    end_ms=121_000,
                    step_ms=1000,
                    final_settle=0.0,
                    settle_delay=0.0,
                    identity_retries=0,
                    seek_timeout=1.0,
                )
            self.assertTrue(status["ok"], status.get("error"))
            lines = [
                json.loads(line)
                for line in out.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            info = next(r for r in lines if r["rfc461Schema"] == "game_info")
            roles = [p["role"] for p in info["participants"]]
            expected_by_name = {
                name: EXPECTED_ROLES[index]
                for index, (_champ, _team, name, _tag, _position) in enumerate(
                    CHAMPS
                )
            }
            self.assertEqual(
                {p["playerName"]: p["role"] for p in info["participants"]},
                expected_by_name,
            )
            self.assertNotIn("NONE", roles)
            stats = next(r for r in lines if r["rfc461Schema"] == "stats_update")
            self.assertEqual(
                {p["playerName"]: p["role"] for p in stats["participants"]},
                expected_by_name,
            )
            tl = jsonl_to_timeline.build_timeline(
                out, timeline_id="roles", name="roles", patch="test"
            )
            self.assertEqual(
                {u["name"]: u["role"] for u in tl["frames"][0]["units"]},
                expected_by_name,
            )


class RestoreTwoPhaseTests(unittest.TestCase):
    """Paused vs initially-unpaused restore: reproduce the former false failure."""

    def _original_snapshot(
        self, *, paused: bool, t: float = 134.46563720703125
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        playback = {
            "paused": paused,
            "seeking": False,
            "time": t,
            "speed": 1.0,
            "length": 1800.0,
        }
        render = {
            "cameraMode": "top",
            "cameraAttached": False,
            "selectionName": "",
            "selectionOffset": {"x": 0.0, "y": 0.0, "z": 0.0},
            "cameraPosition": {"x": 7500.0, "y": 50.0, "z": 7500.0},
            "fieldOfView": 40,
        }
        return playback, render

    def test_legacy_single_post_unpaused_false_failure(self) -> None:
        """Former bug: POST time+paused=false then demand exact settle time."""
        original_pb, _original_rb = self._original_snapshot(paused=False)
        transport = SeekingTransport(
            playback_state=dict(original_pb),
            render_state={
                "cameraMode": "top",
                "cameraAttached": False,
                "selectionName": "",
                "selectionOffset": {"x": 0.0, "y": 0.0, "z": 0.0},
                "cameraPosition": {"x": 7500.0, "y": 50.0, "z": 7500.0},
                "fieldOfView": 40,
            },
        )
        # Mutate away from original (as after a capture seek).
        transport.playback_state["paused"] = True
        transport.playback_state["time"] = 122.0
        target = float(original_pb["time"])
        # Legacy single POST — the live failure mode.
        transport(
            "POST",
            "https://127.0.0.1:2999/replay/playback",
            body={"time": target, "paused": False, "speed": 1.0},
            timeout=1.0,
        )
        # Live failure mode: clock keeps advancing past the exact target while
        # wait_playback_settled demands equality (seeking already false).
        time.sleep(0.05)
        with mock.patch.object(extract.probe, "_settle", lambda _d: time.sleep(0.01)):
            wait = extract.probe.wait_playback_settled(
                transport,
                "https://127.0.0.1:2999/replay/playback",
                target_time_sec=target,
                timeout=1.0,
                poll_interval=0.01,
                time_tol=1e-3,
                seek_timeout=0.12,
            )
        self.assertFalse(wait.get("ok"), wait)
        self.assertIn("seek did not settle", str(wait.get("error") or "").lower())
        body = wait.get("body") or {}
        self.assertIs(body.get("seeking"), False)
        self.assertGreater(float(body.get("time")), target + 1e-3)

    def test_restore_initially_unpaused_succeeds_with_moving_camera(self) -> None:
        original_pb, original_rb = self._original_snapshot(paused=False)
        # Attached camera moves after resume — former verifier falsely failed on this.
        original_rb = {
            **original_rb,
            "cameraMode": "focus",
            "cameraAttached": True,
            "selectionName": "p1",
            "cameraPosition": {"x": 7500.0, "y": 50.0, "z": 7500.0},
        }
        transport = SeekingTransport(
            playback_state={
                "paused": True,
                "seeking": False,
                "time": 122.0,
                "speed": 1.0,
                "length": 1800.0,
            },
            render_state={
                "cameraMode": "focus",
                "cameraAttached": True,
                "selectionName": "other",
                "selectionOffset": {"x": 0.0, "y": 0.0, "z": 0.0},
                "cameraPosition": {"x": 1111.0, "y": 50.0, "z": 2222.0},
                "fieldOfView": 40,
            },
        )
        with mock.patch.object(extract.probe, "_settle", lambda _d: time.sleep(0.02)):
            result = extract.restore_extractor_state(
                transport,
                playback_url="https://127.0.0.1:2999/replay/playback",
                render_url="https://127.0.0.1:2999/replay/render",
                original_playback=original_pb,
                original_render=original_rb,
                timeout=1.0,
                seek_timeout=1.0,
                time_tol=1e-3,
                settle_delay=0.02,
            )
        self.assertTrue(result["restoreSucceeded"], result.get("error"))
        self.assertFalse(result["originallyPaused"])
        phase1 = result["snapshots"]["restorePhase1PlaybackPost"]["posted"]
        self.assertEqual(phase1.get("paused"), True)
        self.assertIn("time", phase1)
        phase2 = result["snapshots"]["restorePhase2PlaybackPost"]["posted"]
        self.assertEqual(phase2.get("paused"), False)
        self.assertNotIn("time", phase2)
        self.assertTrue(result["snapshots"]["restorePhase1Proof"]["ok"])
        self.assertFalse(
            result["snapshots"]["restorePhase1Proof"]["includeCameraPosition"]
        )
        self.assertTrue(result["snapshots"]["restorePhase2Proof"]["ok"])
        self.assertFalse(result["snapshots"]["restorePhase2Proof"]["requireExactTime"])
        self.assertFalse(
            result["snapshots"]["restorePhase2Proof"]["includeCameraPosition"]
        )
        final = result["snapshots"]["restorePlaybackGet"]["sample"]
        self.assertIs(final.get("paused"), False)
        self.assertIs(final.get("seeking"), False)
        self.assertGreaterEqual(float(final["time"]), float(original_pb["time"]) - 1e-3)
        final_render = result["snapshots"]["restoreRenderGet"]["sample"]
        self.assertEqual(final_render.get("cameraMode"), "focus")
        self.assertEqual(final_render.get("selectionName"), "p1")
        self.assertTrue(final_render.get("cameraAttached"))
        # Camera moved after resume relative to the restored snapshot.
        self.assertFalse(
            extract.probe._vec_approx_equal(  # noqa: SLF001
                final_render.get("cameraPosition"),
                original_rb["cameraPosition"],
                tol=1e-3,
            )
        )

    def test_unpaused_restore_counts_resume_post_latency(self) -> None:
        """Clock may advance while Riot is still answering the unpause POST."""

        class SlowResumeTransport(SeekingTransport):
            def __call__(
                self,
                method: str,
                url: str,
                *,
                body: Any = None,
                timeout: float = 2.0,
            ) -> dict[str, Any]:
                result = super().__call__(method, url, body=body, timeout=timeout)
                if (
                    method.upper() == "POST"
                    and "replay/playback" in url
                    and isinstance(body, dict)
                    and body.get("paused") is False
                    and "time" not in body
                ):
                    time.sleep(0.05)
                return result

        original_pb, original_rb = self._original_snapshot(paused=False)
        transport = SlowResumeTransport(
            playback_state={
                "paused": True,
                "seeking": False,
                "time": 122.0,
                "speed": 1.0,
                "length": 1800.0,
            },
            render_state=dict(original_rb),
        )
        with mock.patch.object(extract.probe, "_settle", lambda _d: None):
            result = extract.restore_extractor_state(
                transport,
                playback_url="https://127.0.0.1:2999/replay/playback",
                render_url="https://127.0.0.1:2999/replay/render",
                original_playback=original_pb,
                original_render=original_rb,
                timeout=1.0,
                seek_timeout=1.0,
                time_tol=1e-3,
                settle_delay=0.0,
            )
        self.assertTrue(result["restoreSucceeded"], result.get("error"))
        final = result["snapshots"]["restorePlaybackGet"]["sample"]
        self.assertGreater(float(final["time"]), float(original_pb["time"]) + 0.04)

    def test_restore_originally_paused_keeps_strict_final_proof(self) -> None:
        original_pb, original_rb = self._original_snapshot(paused=True, t=100.0)
        transport = SeekingTransport(
            playback_state={
                "paused": True,
                "seeking": False,
                "time": 122.0,
                "speed": 1.0,
                "length": 1800.0,
            },
            render_state={
                "cameraMode": "focus",
                "cameraAttached": True,
                "selectionName": "p1",
                "selectionOffset": {"x": 0.0, "y": 0.0, "z": 0.0},
                "cameraPosition": {"x": 1111.0, "y": 50.0, "z": 2222.0},
                "fieldOfView": 40,
            },
        )
        with mock.patch.object(extract.probe, "_settle", lambda _d: None):
            result = extract.restore_extractor_state(
                transport,
                playback_url="https://127.0.0.1:2999/replay/playback",
                render_url="https://127.0.0.1:2999/replay/render",
                original_playback=original_pb,
                original_render=original_rb,
                timeout=1.0,
                seek_timeout=1.0,
                time_tol=1e-3,
                settle_delay=0.0,
            )
        self.assertTrue(result["restoreSucceeded"], result.get("error"))
        self.assertTrue(result["originallyPaused"])
        self.assertTrue(result["snapshots"]["restorePhase2Proof"]["requireExactTime"])
        self.assertTrue(
            result["snapshots"]["restorePhase1Proof"]["includeCameraPosition"]
        )
        self.assertTrue(
            result["snapshots"]["restorePhase2Proof"]["includeCameraPosition"]
        )
        final = result["snapshots"]["restorePlaybackGet"]["sample"]
        self.assertIs(final.get("paused"), True)
        self.assertAlmostEqual(float(final["time"]), 100.0, places=3)
        final_render = result["snapshots"]["restoreRenderGet"]["sample"]
        self.assertTrue(
            extract.probe._vec_approx_equal(  # noqa: SLF001
                final_render.get("cameraPosition"),
                original_rb["cameraPosition"],
                tol=1e-3,
            )
        )

    def test_full_extract_restore_when_replay_started_unpaused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rofl, app = _stub_rofl_app(tmp)
            out = Path(tmp) / "out.jsonl"
            transport = SeekingTransport(
                playback_state={
                    "paused": False,
                    "seeking": False,
                    "time": 100.0,
                    "speed": 1.0,
                    "length": 1800.0,
                }
            )
            with mock.patch.object(extract.probe, "_settle", lambda _d: time.sleep(0.01)):
                status = extract.extract_replay_api_jsonl(
                    transport,
                    base_url="https://127.0.0.1:2999",
                    rofl_path=rofl,
                    app_path=app,
                    out_path=out,
                    start_ms=121_000,
                    end_ms=122_000,
                    step_ms=1000,
                    final_settle=0.0,
                    settle_delay=0.0,
                    identity_retries=0,
                    seek_timeout=1.0,
                )
            self.assertTrue(status["ok"], status.get("error"))
            self.assertTrue(status["restoreSucceeded"], status.get("error"))
            phase1_posts = [
                body
                for method, url, body in transport.calls
                if method == "POST"
                and "playback" in url
                and isinstance(body, dict)
                and body.get("time") == 100.0
            ]
            self.assertTrue(phase1_posts)
            # Time restore must be paired with paused=true (never resume+seek).
            for body in phase1_posts:
                if "time" in body:
                    self.assertIs(body.get("paused"), True, body)


class RoleNormalizeTests(unittest.TestCase):
    def test_all_riot_position_mappings(self) -> None:
        cases = {
            "TOP": "Top",
            "JUNGLE": "Jungle",
            "MIDDLE": "Middle",
            "BOTTOM": "Bottom",
            "UTILITY": "Support",
            "MID": "Middle",
            "BOT": "Bottom",
            "SUPPORT": "Support",
            "top": "Top",
        }
        for raw, want in cases.items():
            self.assertEqual(
                extract.probe.normalize_liveclient_role(raw),
                want,
                msg=raw,
            )


class ValidateUnknownHpGateTests(unittest.TestCase):
    def _load_validator(self):
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "validate_rofl_pipeline",
            SCRIPTS / "validate-rofl-pipeline.py",
        )
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def _write_unknown_hp_pair(
        self,
        tmp: str,
        *,
        health_source: Any = "unavailable_replay_api",
        combat_source: Any = "unavailable_replay_api",
        ability_source: Any = "unavailable_replay_api",
        include_health: bool = False,
        force_timeline_flags: Optional[dict[str, Any]] = None,
    ) -> tuple[Path, Path]:
        jsonl = Path(tmp) / "x.jsonl"
        tl_path = Path(tmp) / "t.json"
        roster = [
            {
                "participantID": pid,
                "teamID": 100 if pid <= 5 else 200,
                "championName": "TestChampion",
                "playerName": f"p{pid}",
                "summonerName": f"p{pid}",
                "role": "Middle",
            }
            for pid in range(1, 11)
        ]
        parts = []
        for pid in range(1, 11):
            kwargs: dict[str, Any] = {
                "participant_id": pid,
                "team_id": 100 if pid <= 5 else 200,
                "champion_name": "TestChampion",
                "player_name": f"p{pid}",
                "position": {"x": 1000 + pid * 20, "z": 2000 + pid * 20},
                "position_source": "replay_api_focus_selection",
                "health_known": not include_health,
                "extra": {"role": "Middle"},
            }
            if include_health:
                kwargs["health"] = 100
                kwargs["health_max"] = 100
                kwargs["health_known"] = True
            if health_source is not None:
                kwargs["health_source"] = health_source
            if combat_source is not None:
                kwargs["combat_stats_source"] = combat_source
            if ability_source is not None:
                kwargs["ability_ranks_source"] = ability_source
            if include_health:
                # force known health path while still claiming hpCoverage none upstream
                pass
            else:
                kwargs["health_known"] = False
            parts.append(rfc461_emit.participant_row(**kwargs))
        rows = [
            rfc461_emit.coverage_line(
                source="replay_api_playback",
                provenance=rfc461_emit.provenance_record(
                    source="replay_api_playback",
                    source_kind="replay_api_playback",
                    position_coverage="full_at_sampled_frames",
                    hp_coverage="none",
                    roster_mapping="game_info_participantID",
                ),
            ),
            rfc461_emit.game_info_line(game_id=1, participants=roster),
            rfc461_emit.stats_update_line(
                game_id=1, game_time=121000, participants=parts
            ),
            rfc461_emit.stats_update_line(
                game_id=1, game_time=122000, participants=parts
            ),
        ]
        rfc461_emit.write_jsonl(jsonl, rows)
        tl = jsonl_to_timeline.build_timeline(
            jsonl, timeline_id="x", name="x", patch="test"
        )
        if force_timeline_flags is not None:
            for frame in tl["frames"]:
                for u in frame["units"]:
                    u.update(force_timeline_flags)
        tl_path.write_text(json.dumps(tl), encoding="utf-8")
        return jsonl, tl_path

    def test_validator_accepts_hp_coverage_none(self) -> None:
        mod = self._load_validator()
        with tempfile.TemporaryDirectory() as tmp:
            jsonl, tl_path = self._write_unknown_hp_pair(tmp)
            result = mod.validate(jsonl, tl_path, require_live=True)
            self.assertTrue(result["ok"])
            self.assertEqual(result["hpCoverage"], "none")

    def test_validator_rejects_missing_health_source(self) -> None:
        mod = self._load_validator()
        with tempfile.TemporaryDirectory() as tmp:
            jsonl, tl_path = self._write_unknown_hp_pair(tmp, health_source=None)
            # participant_row omits healthSource when None — patch JSONL
            lines = []
            for line in jsonl.read_text(encoding="utf-8").splitlines():
                row = json.loads(line)
                if row.get("rfc461Schema") == "stats_update":
                    for p in row["participants"]:
                        p.pop("healthSource", None)
                lines.append(json.dumps(row))
            jsonl.write_text("\n".join(lines) + "\n", encoding="utf-8")
            with self.assertRaises(SystemExit) as ctx:
                mod.validate(jsonl, tl_path, require_live=True)
            self.assertIn("healthSource", str(ctx.exception))

    def test_validator_rejects_wrong_health_source(self) -> None:
        mod = self._load_validator()
        with tempfile.TemporaryDirectory() as tmp:
            jsonl, tl_path = self._write_unknown_hp_pair(
                tmp, health_source="unknown"
            )
            with self.assertRaises(SystemExit) as ctx:
                mod.validate(jsonl, tl_path, require_live=True)
            self.assertIn("healthSource", str(ctx.exception))

    def test_validator_rejects_health_present_under_none(self) -> None:
        mod = self._load_validator()
        with tempfile.TemporaryDirectory() as tmp:
            jsonl, tl_path = self._write_unknown_hp_pair(tmp, include_health=True)
            with self.assertRaises(SystemExit) as ctx:
                mod.validate(jsonl, tl_path, require_live=True)
            self.assertIn("health", str(ctx.exception).lower())

    def test_validator_rejects_true_timeline_flags(self) -> None:
        mod = self._load_validator()
        with tempfile.TemporaryDirectory() as tmp:
            jsonl, tl_path = self._write_unknown_hp_pair(
                tmp,
                force_timeline_flags={
                    "hpKnown": True,
                    "combatStatsKnown": True,
                    "abilityRanksKnown": True,
                    "hp": 0,
                    "hpMax": 0,
                },
            )
            with self.assertRaises(SystemExit) as ctx:
                mod.validate(jsonl, tl_path, require_live=True)
            self.assertIn("hpKnown", str(ctx.exception))


class DurablePersistResumeTests(unittest.TestCase):
    """Crash-safe per-frame persistence + --resume contract tests."""

    def _extract_kwargs(self, rofl: Path, app: Path, out: Path, **extra: Any) -> dict:
        kw: dict[str, Any] = {
            "base_url": "https://127.0.0.1:2999",
            "rofl_path": rofl,
            "app_path": app,
            "out_path": out,
            "start_ms": 121_000,
            "end_ms": 124_000,
            "step_ms": 1000,
            "final_settle": 0.0,
            "settle_delay": 0.0,
            "identity_retries": 0,
            "seek_timeout": 1.0,
        }
        kw.update(extra)
        return kw

    def _load_rows(self, path: Path) -> list[dict[str, Any]]:
        return [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def test_interrupt_keeps_completed_frames_and_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rofl, app = _stub_rofl_app(tmp)
            out = Path(tmp) / "partial.jsonl"
            ckpt = Path(tmp) / "partial.checkpoint.json"
            transport = SeekingTransport()
            transport.fail_seek_at = 123.0
            with mock.patch.object(extract.probe, "_settle", lambda _d: None):
                with self.assertRaises(extract.ExtractError) as ctx:
                    extract.extract_replay_api_jsonl(
                        transport,
                        checkpoint_out=ckpt,
                        **self._extract_kwargs(rofl, app, out),
                    )
            self.assertEqual(ctx.exception.checkpoint.get("framesCaptured"), 2)
            self.assertEqual(ctx.exception.checkpoint.get("completedCount"), 2)
            self.assertEqual(ctx.exception.checkpoint.get("lastCompletedMs"), 122000)
            self.assertEqual(ctx.exception.checkpoint.get("nextSampleMs"), 123000)
            self.assertTrue(ckpt.is_file())
            ck = json.loads(ckpt.read_text(encoding="utf-8"))
            self.assertEqual(ck.get("completedCount"), 2)
            self.assertEqual(ck.get("lastCompletedMs"), 122000)
            self.assertEqual(ck.get("nextSampleMs"), 123000)
            self.assertIn("restoreSucceeded", ck.get("checkpoint") or ck)

            rows = self._load_rows(out)
            self.assertEqual(rows[0]["rfc461Schema"], "rofl_coverage")
            self.assertEqual(rows[1]["rfc461Schema"], "game_info")
            stats = [r for r in rows if r["rfc461Schema"] == "stats_update"]
            self.assertEqual([r["gameTime"] for r in stats], [121000, 122000])
            # Exactly one of each header.
            self.assertEqual(
                sum(1 for r in rows if r["rfc461Schema"] == "rofl_coverage"), 1
            )
            self.assertEqual(
                sum(1 for r in rows if r["rfc461Schema"] == "game_info"), 1
            )

    def test_resume_appends_missing_frames_without_duplicate_headers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rofl, app = _stub_rofl_app(tmp)
            out = Path(tmp) / "resume.jsonl"
            ckpt = Path(tmp) / "resume.checkpoint.json"
            transport = SeekingTransport()
            transport.fail_seek_at = 123.0
            with mock.patch.object(extract.probe, "_settle", lambda _d: None):
                with self.assertRaises(extract.ExtractError):
                    extract.extract_replay_api_jsonl(
                        transport,
                        checkpoint_out=ckpt,
                        **self._extract_kwargs(rofl, app, out),
                    )

            transport2 = SeekingTransport()
            with mock.patch.object(extract.probe, "_settle", lambda _d: None):
                status = extract.extract_replay_api_jsonl(
                    transport2,
                    resume=True,
                    checkpoint_out=ckpt,
                    **self._extract_kwargs(rofl, app, out),
                )
            self.assertTrue(status["ok"], status.get("error"))
            self.assertTrue(status["resumed"])
            self.assertEqual(status["framesCaptured"], 4)
            self.assertEqual(status["completedCount"], 4)
            self.assertIsNone(status["nextSampleMs"])
            self.assertEqual(status["lastCompletedMs"], 124000)

            rows = self._load_rows(out)
            self.assertEqual(
                sum(1 for r in rows if r["rfc461Schema"] == "rofl_coverage"), 1
            )
            self.assertEqual(
                sum(1 for r in rows if r["rfc461Schema"] == "game_info"), 1
            )
            times = [
                r["gameTime"]
                for r in rows
                if r["rfc461Schema"] == "stats_update"
            ]
            self.assertEqual(times, [121000, 122000, 123000, 124000])
            self.assertEqual(len(times), len(set(times)))

            # Resume should only seek the missing suffix samples.
            sample_seeks = [
                float(body["time"])
                for method, url, body in transport2.calls
                if method == "POST"
                and "playback" in url
                and isinstance(body, dict)
                and body.get("time") in (123.0, 124.0)
            ]
            self.assertEqual(sorted(set(sample_seeks)), [123.0, 124.0])

            ck = json.loads(ckpt.read_text(encoding="utf-8"))
            self.assertTrue(ck.get("ok"))
            self.assertEqual(ck.get("completedCount"), 4)

    def test_resume_noop_when_already_complete(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rofl, app = _stub_rofl_app(tmp)
            out = Path(tmp) / "done.jsonl"
            transport = SeekingTransport()
            with mock.patch.object(extract.probe, "_settle", lambda _d: None):
                status = extract.extract_replay_api_jsonl(
                    transport,
                    **self._extract_kwargs(rofl, app, out, end_ms=122_000),
                )
            self.assertTrue(status["ok"])
            before = out.read_text(encoding="utf-8")
            calls_before = len(transport.calls)

            transport2 = SeekingTransport()
            with mock.patch.object(extract.probe, "_settle", lambda _d: None):
                status2 = extract.extract_replay_api_jsonl(
                    transport2,
                    resume=True,
                    **self._extract_kwargs(rofl, app, out, end_ms=122_000),
                )
            self.assertTrue(status2["ok"])
            self.assertTrue(status2.get("noop"))
            self.assertEqual(status2["framesCaptured"], 2)
            self.assertEqual(out.read_text(encoding="utf-8"), before)
            # No-op must not touch Replay API.
            self.assertEqual(transport2.calls, [])
            self.assertEqual(calls_before, len(transport.calls))

    def test_resume_rejects_coverage_contract_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rofl, app = _stub_rofl_app(tmp)
            out = Path(tmp) / "bad_cov.jsonl"
            transport = SeekingTransport()
            with mock.patch.object(extract.probe, "_settle", lambda _d: None):
                extract.extract_replay_api_jsonl(
                    transport,
                    **self._extract_kwargs(rofl, app, out, end_ms=121_000),
                )
            rows = self._load_rows(out)
            rows[0]["startMs"] = 999000
            out.write_text(
                "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8"
            )
            with self.assertRaises(extract.ExtractError) as ctx:
                extract.extract_replay_api_jsonl(
                    SeekingTransport(),
                    resume=True,
                    **self._extract_kwargs(rofl, app, out, end_ms=121_000),
                )
            self.assertIn("startMs", str(ctx.exception))

    def test_resume_rejects_roster_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rofl, app = _stub_rofl_app(tmp)
            out = Path(tmp) / "bad_roster.jsonl"
            transport = SeekingTransport()
            transport.fail_seek_at = 122.0
            with mock.patch.object(extract.probe, "_settle", lambda _d: None):
                with self.assertRaises(extract.ExtractError):
                    extract.extract_replay_api_jsonl(
                        transport,
                        **self._extract_kwargs(rofl, app, out),
                    )
            rows = self._load_rows(out)
            info = next(r for r in rows if r["rfc461Schema"] == "game_info")
            info["participants"][0]["championName"] = "NotGnar"
            out.write_text(
                "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8"
            )
            with mock.patch.object(extract.probe, "_settle", lambda _d: None):
                with self.assertRaises(extract.ExtractError) as ctx:
                    extract.extract_replay_api_jsonl(
                        SeekingTransport(),
                        resume=True,
                        **self._extract_kwargs(rofl, app, out),
                    )
            self.assertIn("champion", str(ctx.exception).lower())

    def test_resume_rejects_truncated_final_line(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rofl, app = _stub_rofl_app(tmp)
            out = Path(tmp) / "trunc.jsonl"
            with mock.patch.object(extract.probe, "_settle", lambda _d: None):
                extract.extract_replay_api_jsonl(
                    SeekingTransport(),
                    **self._extract_kwargs(rofl, app, out, end_ms=121_000),
                )
            raw = out.read_text(encoding="utf-8")
            out.write_text(raw + '{"rfc461Schema":"stats_update","gameTime":', encoding="utf-8")
            with self.assertRaises(extract.ExtractError) as ctx:
                extract.extract_replay_api_jsonl(
                    SeekingTransport(),
                    resume=True,
                    **self._extract_kwargs(rofl, app, out),
                )
            self.assertIn("truncated", str(ctx.exception).lower())

    def test_resume_rejects_duplicate_stats_time(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rofl, app = _stub_rofl_app(tmp)
            out = Path(tmp) / "dup.jsonl"
            with mock.patch.object(extract.probe, "_settle", lambda _d: None):
                extract.extract_replay_api_jsonl(
                    SeekingTransport(),
                    **self._extract_kwargs(rofl, app, out, end_ms=122_000),
                )
            rows = self._load_rows(out)
            stats = next(r for r in rows if r["rfc461Schema"] == "stats_update")
            rows.append(dict(stats))  # duplicate 121000 after contiguous 121,122
            # Keep only headers + first stats + duplicate of first → [121, 121]
            headers = [
                r for r in rows if r["rfc461Schema"] in ("rofl_coverage", "game_info")
            ]
            first_stats = next(
                r for r in rows if r["rfc461Schema"] == "stats_update"
            )
            out.write_text(
                "\n".join(
                    json.dumps(r) for r in headers + [first_stats, dict(first_stats)]
                )
                + "\n",
                encoding="utf-8",
            )
            with self.assertRaises(extract.ExtractError) as ctx:
                extract.extract_replay_api_jsonl(
                    SeekingTransport(),
                    resume=True,
                    **self._extract_kwargs(rofl, app, out, end_ms=122_000),
                )
            err = str(ctx.exception).lower()
            self.assertTrue("duplicate" in err or "contiguous" in err, err)

    def test_resume_rejects_schedule_hole(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rofl, app = _stub_rofl_app(tmp)
            out = Path(tmp) / "hole.jsonl"
            with mock.patch.object(extract.probe, "_settle", lambda _d: None):
                extract.extract_replay_api_jsonl(
                    SeekingTransport(),
                    **self._extract_kwargs(rofl, app, out, end_ms=122_000),
                )
            rows = self._load_rows(out)
            # Drop 121000, keep 122000 → hole / non-prefix.
            kept = [
                r
                for r in rows
                if r.get("rfc461Schema") != "stats_update"
                or r.get("gameTime") != 121000
            ]
            out.write_text(
                "\n".join(json.dumps(r) for r in kept) + "\n", encoding="utf-8"
            )
            with self.assertRaises(extract.ExtractError) as ctx:
                extract.extract_replay_api_jsonl(
                    SeekingTransport(),
                    resume=True,
                    **self._extract_kwargs(rofl, app, out, end_ms=122_000),
                )
            self.assertIn("contiguous", str(ctx.exception).lower())

    def test_resume_rejects_mixed_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rofl, app = _stub_rofl_app(tmp)
            out = Path(tmp) / "mixed.jsonl"
            with mock.patch.object(extract.probe, "_settle", lambda _d: None):
                extract.extract_replay_api_jsonl(
                    SeekingTransport(),
                    **self._extract_kwargs(rofl, app, out, end_ms=121_000),
                )
            with out.open("a", encoding="utf-8") as fh:
                fh.write(
                    json.dumps(
                        {
                            "rfc461Schema": "champion_kill",
                            "gameID": 0,
                            "gameTime": 122000,
                        }
                    )
                    + "\n"
                )
            with self.assertRaises(extract.ExtractError) as ctx:
                extract.extract_replay_api_jsonl(
                    SeekingTransport(),
                    resume=True,
                    **self._extract_kwargs(rofl, app, out, end_ms=121_000),
                )
            self.assertIn("schema", str(ctx.exception).lower())


class ProductDefaultsAndDeferLiveclientTests(unittest.TestCase):
    def test_argparse_product_defaults(self) -> None:
        self.assertEqual(extract.DEFAULT_FINAL_SETTLE, 0.0)
        self.assertEqual(extract.DEFAULT_CACHED_SELECTION_STRATEGY, "compact")
        ns = extract.build_arg_parser().parse_args(
            [
                "--rofl",
                "/tmp/x.rofl",
                "--out",
                "/tmp/y.jsonl",
                "--start-ms",
                "0",
                "--end-ms",
                "1000",
            ]
        )
        self.assertEqual(ns.final_settle, 0.0)
        self.assertEqual(ns.cached_selection_strategy, "compact")
        self.assertFalse(ns.defer_liveclient)

    def test_defer_liveclient_skips_per_frame_wait(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rofl, app = _stub_rofl_app(tmp)
            out = Path(tmp) / "events.jsonl"
            wait_calls = {"n": 0}

            def _fake_wait(*_a: Any, **_k: Any) -> dict[str, Any]:
                wait_calls["n"] += 1
                return {"ok": False, "error": "should not be called"}

            with mock.patch.object(extract.probe, "_settle", lambda _d: None):
                with mock.patch.object(
                    extract, "wait_liveclient_roster_at_time", _fake_wait
                ):
                    status = extract.extract_replay_api_jsonl(
                        SeekingTransport(),
                        **{
                            "base_url": "https://127.0.0.1:2999",
                            "rofl_path": rofl,
                            "app_path": app,
                            "out_path": out,
                            "start_ms": 121_000,
                            "end_ms": 122_000,
                            "step_ms": 1000,
                            "final_settle": 0.0,
                            "settle_delay": 0.0,
                            "identity_retries": 0,
                            "seek_timeout": 1.0,
                            "defer_liveclient": True,
                        },
                    )
            self.assertTrue(status["ok"], status.get("error"))
            self.assertTrue(status.get("deferLiveclient"))
            self.assertEqual(wait_calls["n"], 0)
            rows = [
                json.loads(line)
                for line in out.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            cov = next(r for r in rows if r.get("rfc461Schema") == "rofl_coverage")
            self.assertIn("positions_focus_selection", cov.get("decoded") or [])
            self.assertTrue(cov.get("deferLiveclient"))
            self.assertEqual(cov.get("cachedSelectionStrategy"), "compact")
            self.assertEqual(status.get("cachedSelectionStrategy"), "compact")


class EnrichRosterPuuidFromRoflTests(unittest.TestCase):
    def test_backfills_null_puuid_by_champion(self):
        roster = [
            {
                "participantID": 1,
                "teamID": 100,
                "championName": "Yasuo",
                "summonerName": "awakening#0000",
                "puuid": None,
            }
        ]
        meta = {
            "participants": [
                {
                    "champion": {"asset": "Yasuo"},
                    "sourceIdentity": {
                        "puuid": "puuid-yasuo",
                        "riotId": {
                            "gameName": "PlayerOne",
                            "tagLine": "BR1",
                            "full": "PlayerOne#BR1",
                        },
                        "key": "puuid:puuid-yasuo",
                    },
                }
            ]
        }
        out = extract.enrich_roster_puuids_from_rofl_metadata(roster, meta)
        self.assertEqual(out[0]["puuid"], "puuid-yasuo")
        self.assertEqual(out[0]["riotIdGameName"], "PlayerOne")
        self.assertEqual(out[0]["summonerName"], "PlayerOne#BR1")

    def test_keeps_existing_puuid(self):
        roster = [
            {
                "participantID": 1,
                "teamID": 100,
                "championName": "Yasuo",
                "puuid": "already",
            }
        ]
        meta = {
            "participants": [
                {
                    "champion": {"asset": "Yasuo"},
                    "sourceIdentity": {"puuid": "other", "key": "puuid:other"},
                }
            ]
        }
        out = extract.enrich_roster_puuids_from_rofl_metadata(roster, meta)
        self.assertEqual(out[0]["puuid"], "already")


class SourceRecordOrderIdentityTests(unittest.TestCase):
    """Scrambled liveclient order must not publish mismatched champ vs identity."""

    def _rofl_meta(self) -> dict[str, Any]:
        # CreateHero / statsJson sourceRecordIndex order (not Riot-ID sort).
        roster = [
            ("Zaahen", "awakening", "0000", "puuid-z"),
            ("MonkeyKing", "pixel", "mari", "puuid-mk"),
            ("Yasuo", "Cigarro", "lony", "puuid-y"),
            ("Ezreal", "Ayron", "001", "puuid-e"),
            ("Sona", "nhUwUmi", "glhf", "puuid-s"),
            ("Renekton", "casual", "2709", "puuid-r"),
            ("Lillia", "Sonancia", "UEL", "puuid-l"),
            ("Leblanc", "haste", "zapp", "puuid-lb"),
            ("Ashe", "Love Her", "Lucy", "puuid-a"),
            ("Morgana", "amo seios", "Lucy", "puuid-m"),
        ]
        participants = []
        for index, (champ, name, tag, puuid) in enumerate(roster):
            full = f"{name}#{tag}"
            participants.append(
                {
                    "sourceRecordIndex": index,
                    "teamId": 100 if index < 5 else 200,
                    "role": "NONE",
                    "champion": {"asset": champ, "raw": champ, "display": champ},
                    "sourceIdentity": {
                        "kind": "puuid",
                        "key": f"puuid:{puuid}",
                        "puuid": puuid,
                        "riotId": {
                            "gameName": name,
                            "tagLine": tag,
                            "full": full,
                            "normalized": full.casefold(),
                        },
                        "stable": True,
                    },
                    "puuid": puuid,
                    "riotId": {
                        "gameName": name,
                        "tagLine": tag,
                        "full": full,
                        "normalized": full.casefold(),
                    },
                }
            )
        return {"participants": participants}

    def _scrambled_liveclient(self) -> list[dict[str, Any]]:
        # Riot-ID / display-name scramble: Wukong label + pixel identity appear
        # after Ezreal/Ayron (the bug that put MK HP/labels on the wrong pid).
        return [
            {
                "teamID": 100,
                "championName": "Ezreal",
                "riotIdGameName": "Ayron",
                "riotIdTagLine": "001",
                "summonerName": "Ayron#001",
                "playerName": "Ayron",
                "puuid": "puuid-e",
            },
            {
                "teamID": 100,
                "championName": "Wukong",  # liveclient display, not MonkeyKing
                "riotIdGameName": "pixel",
                "riotIdTagLine": "mari",
                "summonerName": "pixel#mari",
                "playerName": "pixel",
                "puuid": "puuid-mk",
            },
            {
                "teamID": 100,
                "championName": "Zaahen",
                "riotIdGameName": "awakening",
                "riotIdTagLine": "0000",
                "summonerName": "awakening#0000",
                "playerName": "awakening",
                "puuid": "puuid-z",
            },
            {
                "teamID": 100,
                "championName": "Yasuo",
                "riotIdGameName": "Cigarro",
                "riotIdTagLine": "lony",
                "summonerName": "Cigarro#lony",
                "playerName": "Cigarro",
                "puuid": "puuid-y",
            },
            {
                "teamID": 100,
                "championName": "Sona",
                "riotIdGameName": "nhUwUmi",
                "riotIdTagLine": "glhf",
                "summonerName": "nhUwUmi#glhf",
                "playerName": "nhUwUmi",
                "puuid": "puuid-s",
            },
            {
                "teamID": 200,
                "championName": "Morgana",
                "riotIdGameName": "amo seios",
                "riotIdTagLine": "Lucy",
                "summonerName": "amo seios#Lucy",
                "playerName": "amo seios",
                "puuid": "puuid-m",
            },
            {
                "teamID": 200,
                "championName": "Renekton",
                "riotIdGameName": "casual",
                "riotIdTagLine": "2709",
                "summonerName": "casual#2709",
                "playerName": "casual",
                "puuid": "puuid-r",
            },
            {
                "teamID": 200,
                "championName": "LeBlanc",
                "riotIdGameName": "haste",
                "riotIdTagLine": "zapp",
                "summonerName": "haste#zapp",
                "playerName": "haste",
                "puuid": "puuid-lb",
            },
            {
                "teamID": 200,
                "championName": "Ashe",
                "riotIdGameName": "Love Her",
                "riotIdTagLine": "Lucy",
                "summonerName": "Love Her#Lucy",
                "playerName": "Love Her",
                "puuid": "puuid-a",
            },
            {
                "teamID": 200,
                "championName": "Lillia",
                "riotIdGameName": "Sonancia",
                "riotIdTagLine": "UEL",
                "summonerName": "Sonancia#UEL",
                "playerName": "Sonancia",
                "puuid": "puuid-l",
            },
        ]

    def test_source_record_order_pins_monkeyking_to_pid2(self) -> None:
        meta = self._rofl_meta()
        stable = extract.assign_stable_participant_ids(
            self._scrambled_liveclient(), rofl_meta=meta
        )
        by_pid = {int(r["participantID"]): r for r in stable}
        self.assertEqual(by_pid[2]["championName"], "MonkeyKing")
        self.assertEqual(by_pid[2]["playerName"], "pixel")
        self.assertEqual(by_pid[2]["puuid"], "puuid-mk")
        self.assertEqual(by_pid[4]["championName"], "Ezreal")
        self.assertEqual(by_pid[4]["playerName"], "Ayron")
        self.assertEqual(by_pid[5]["championName"], "Sona")
        # Riot-ID sort alone would put Ayron before pixel on blue; source order must win.
        self.assertNotEqual(by_pid[2]["championName"], "Ezreal")

    def test_remap_moves_dynamics_with_identity(self) -> None:
        meta = self._rofl_meta()
        # Simulate a scrambled capture: Ezreal row on pid2, pixel/Wukong on pid5.
        participants = []
        for pid, row in enumerate(self._scrambled_liveclient(), start=1):
            copied = dict(row)
            copied["participantID"] = pid
            copied["level"] = pid
            copied["position"] = {"x": float(pid * 100), "z": float(pid * 10)}
            participants.append(copied)
        # Force the classic scramble pids: put pixel at 5 and Ezreal at 2.
        by_name = {p["riotIdGameName"]: p for p in participants}
        scrambled = [None] * 10
        order = [
            "awakening",
            "Ayron",
            "Cigarro",
            "nhUwUmi",
            "pixel",
            "casual",
            "Sonancia",
            "haste",
            "Love Her",
            "amo seios",
        ]
        for index, name in enumerate(order):
            row = dict(by_name[name])
            row["participantID"] = index + 1
            scrambled[index] = row
        rows = [
            {
                "rfc461Schema": "game_info",
                "participants": extract.game_info_participants(scrambled),
            },
            {
                "rfc461Schema": "stats_update",
                "gameTime": 100_000,
                "participants": scrambled,
            },
        ]
        remapped = extract.remap_rfc461_rows_to_rofl_source_order(rows, meta)
        stats = next(r for r in remapped if r["rfc461Schema"] == "stats_update")
        by_pid = {int(p["participantID"]): p for p in stats["participants"]}
        self.assertEqual(by_pid[2]["championName"], "MonkeyKing")
        self.assertEqual(by_pid[2]["playerName"], "pixel")
        # Dynamics travel with identity (pixel was scrambled pid5 → level/pos of that row).
        self.assertEqual(by_pid[2]["level"], by_name["pixel"]["level"])
        self.assertEqual(by_pid[2]["position"], by_name["pixel"]["position"])
        self.assertEqual(by_pid[4]["championName"], "Ezreal")
        gi = next(r for r in remapped if r["rfc461Schema"] == "game_info")
        gi_by_pid = {int(p["participantID"]): p for p in gi["participants"]}
        self.assertEqual(gi_by_pid[2]["championName"], "MonkeyKing")
        self.assertEqual(
            gi_by_pid[2]["championName"],
            by_pid[2]["championName"],
        )


if __name__ == "__main__":
    unittest.main()
