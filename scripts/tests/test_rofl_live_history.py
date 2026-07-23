#!/usr/bin/env python3
"""Focused Phase 3 tests for honest Replay API liveclient history."""
from __future__ import annotations

import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import rfc461_emit  # noqa: E402
import rofl_ingest  # noqa: E402
import rofl_metadata  # noqa: E402
import rofl_replay_api_probe as probe  # noqa: E402
import rofl_replay_api_to_jsonl as capture  # noqa: E402


VERSION = "16.14.794.5912"
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


def live_players(*, score: int = 0) -> list[dict]:
    rows: list[dict] = []
    for index, champion in enumerate(CHAMPIONS):
        rows.append(
            {
                "puuid": f"puuid-{index}",
                "riotIdGameName": f"player {index}",
                "riotIdTagLine": f"T{index}",
                "summonerName": f"player {index}#T{index}",
                "championName": champion,
                "rawChampionName": "MonkeyKing" if champion == "Wukong" else champion,
                "team": "ORDER" if index < 5 else "CHAOS",
                "position": ("TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY")[
                    index % 5
                ],
                "level": index + 1,
                "items": [{"itemID": 1001 + index}],
                "isDead": False,
                "scores": {
                    "kills": score,
                    "deaths": score,
                    "assists": score,
                    "creepScore": score,
                    "wardScore": score,
                },
            }
        )
    return rows


class LiveclientTransport:
    def __init__(self, *, game_time: float, score: int = 0):
        self.all_players = live_players(score=score)
        self.playerlist = [dict(row) for row in reversed(self.all_players)]
        # Deliberately stale playerlist dynamics/scores. Accepted values must
        # come from the time-correlated allgamedata body.
        for row in self.playerlist:
            row["level"] = 99
            row["items"] = [{"itemID": 9999}]
            row["scores"] = {
                "kills": 999,
                "deaths": 999,
                "assists": 999,
                "creepScore": 999,
                "wardScore": 999,
            }
        self.allgamedata = {
            "gameData": {"gameTime": game_time},
            "allPlayers": self.all_players,
        }

    def __call__(
        self,
        method: str,
        url: str,
        *,
        body=None,
        timeout: float = 2.0,
    ) -> dict:
        del body, timeout
        if method == "GET" and url.endswith("/liveclientdata/allgamedata"):
            return {"ok": True, "body": self.allgamedata}
        if method == "GET" and url.endswith("/liveclientdata/playerlist"):
            return {"ok": True, "body": self.playerlist}
        return {"ok": False, "error": f"unexpected request: {method} {url}"}


def write_rofl(directory: Path) -> Path:
    players = []
    for index, champion in enumerate(CHAMPIONS):
        players.append(
            {
                "PUUID": f"puuid-{index}",
                "RIOT_ID_GAME_NAME": f"player {index}",
                "RIOT_ID_TAG_LINE": f"T{index}",
                "SKIN": "MonkeyKing" if champion == "Wukong" else champion,
                "TEAM": "100" if index < 5 else "200",
                "CHAMPIONS_KILLED": 9,
                "NUM_DEATHS": 8,
                "ASSISTS": 7,
                "MINIONS_KILLED": 123,
                "NEUTRAL_MINIONS_KILLED": 45,
                "VISION_SCORE": 33,
                "TOTAL_DAMAGE_DEALT_TO_CHAMPIONS": 45678,
            }
        )
    metadata = {
        "gameLength": 61_000,
        "statsJson": json.dumps(players),
    }
    version = VERSION.encode("ascii")
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
    path = directory / "BR1-3264361042.rofl"
    path.write_bytes(data)
    return path


class LiveclientHistoryTests(unittest.TestCase):
    def test_scores_are_time_correlated_and_emitted(self) -> None:
        transport = LiveclientTransport(game_time=61.0, score=4)
        sampled = capture.wait_liveclient_roster_at_time(
            transport,
            "https://127.0.0.1:2999",
            target_ms=61_000,
            timeout=0.1,
            poll_interval=0,
            wait_timeout=0.1,
        )
        self.assertTrue(sampled["ok"], sampled.get("error"))
        self.assertEqual(len(sampled["roster"]), 10)
        player = sampled["roster"][0]
        self.assertEqual(player["historySampleGameTimeMs"], 61_000)
        self.assertEqual(
            player["history"],
            {
                "kills": 4,
                "deaths": 4,
                "assists": 4,
                "totalCreepScore": 4,
                "visionScore": 4,
            },
        )
        self.assertNotEqual(player["level"], 99)
        self.assertNotEqual(player["items"], [{"itemID": 9999}])

        stable = capture.assign_stable_participant_ids(sampled["roster"])
        frame = capture.merge_dynamic_roster_state(stable, sampled["roster"])
        for index, row in enumerate(frame):
            row["position"] = {"x": float(index), "z": float(index + 1)}
        emitted = capture.participants_to_rfc461_rows(frame)
        self.assertEqual(len(emitted), 10)
        self.assertEqual(emitted[0]["careerSampleGameTimeMs"], 61_000)
        self.assertEqual(
            emitted[0]["careerSources"]["totalCreepScore"],
            "liveclient_allgamedata_scores",
        )

    def test_authoritative_early_zero_scores_are_preserved(self) -> None:
        transport = LiveclientTransport(game_time=0.0, score=0)
        sampled = capture.wait_liveclient_roster_at_time(
            transport,
            "https://127.0.0.1:2999",
            target_ms=0,
            timeout=0.1,
            poll_interval=0,
            wait_timeout=0.1,
        )
        self.assertTrue(sampled["ok"], sampled.get("error"))
        row = sampled["roster"][0]
        row["participantID"] = 1
        row["position"] = {"x": 1.0, "z": 2.0}
        emitted = capture.participants_to_rfc461_rows([row])[0]
        self.assertEqual(emitted["career"]["kills"], 0)
        self.assertEqual(emitted["career"]["totalCreepScore"], 0)
        self.assertEqual(emitted["career"]["visionScore"], 0)
        self.assertEqual(emitted["careerCoverage"]["kills"], "known")

    def test_unsupported_history_fields_stay_absent(self) -> None:
        row = rfc461_emit.participant_row(
            participant_id=1,
            team_id=100,
            champion_name="Zaahen",
            player_name="player",
            position={"x": 1.0, "z": 2.0},
            position_source="replay_api_focus_selection",
            career={"kills": 0, "visionScore": 0},
            career_sources={
                "kills": "liveclient_allgamedata_scores",
                "visionScore": "liveclient_allgamedata_scores",
            },
            career_sample_game_time_ms=0,
        )
        self.assertEqual(set(row["career"]), {"kills", "visionScore"})
        for unsupported in (
            "gold",
            "damage",
            "objectives",
            "jungleCreepScore",
            "laneCreepScore",
        ):
            self.assertNotIn(unsupported, row["career"])
        with self.assertRaisesRegex(ValueError, "unsupported"):
            rfc461_emit.participant_row(
                participant_id=1,
                team_id=100,
                champion_name="Zaahen",
                player_name="player",
                position={"x": 1.0, "z": 2.0},
                position_source="replay_api_focus_selection",
                career={"kills": 0, "dmgToChamps": 0},
                career_sources={
                    "kills": "liveclient_allgamedata_scores",
                    "dmgToChamps": "liveclient_allgamedata_scores",
                },
                career_sample_game_time_ms=0,
            )

    def test_stats_json_is_quarantined_to_static_manifest_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            metadata = rofl_metadata.inspect_rofl_metadata(write_rofl(Path(tmp)))
            config = rofl_ingest.capture_config(
                metadata,
                start_ms=60_000,
                end_ms=61_000,
                step_ms=1_000,
            )
            manifest = rofl_ingest.make_manifest(metadata, config)
        summary = manifest["postGameSummary"]
        self.assertEqual(summary["source"], "rofl_metadata_statsJson")
        self.assertEqual(summary["scope"], "end_game_static")
        self.assertFalse(summary["scrubbableFrameHistory"])
        self.assertEqual(summary["participants"][0]["finalStats"]["kills"], 9)
        self.assertNotIn("statsJson", manifest)
        self.assertNotIn("statsJson", manifest["rofl"])
        manifest_champions = {
            participant["champion"]["raw"]: participant["champion"]
            for participant in manifest["participants"]
        }
        self.assertIsNone(manifest_champions["Zaahen"]["model"])
        self.assertEqual(manifest_champions["Zaahen"]["asset"], "Zaahen")
        self.assertEqual(manifest_champions["MonkeyKing"]["display"], "Wukong")
        self.assertEqual(manifest_champions["MonkeyKing"]["asset"], "MonkeyKing")

        live_row = live_players(score=0)[0]
        live_row.update(
            {
                "participantID": 1,
                "teamID": 100,
                "history": probe.liveclient_history_from_player(live_row)["history"],
                "historySources": probe.liveclient_history_from_player(live_row)[
                    "historySources"
                ],
                "historySampleGameTimeMs": 0,
                "position": {"x": 1.0, "z": 2.0},
            }
        )
        emitted = capture.participants_to_rfc461_rows([live_row])[0]
        self.assertEqual(emitted["career"]["kills"], 0)
        self.assertNotIn("damageToChampions", emitted["career"])


class SelectionCacheTests(unittest.TestCase):
    def test_cached_key_fast_path_and_bounded_fallback(self) -> None:
        roster: list[dict] = []
        for index in range(10):
            roster.append(
                {
                    "participantID": index + 1,
                    "teamID": 100 if index < 5 else 200,
                    "puuid": f"puuid-{index}",
                    "championName": CHAMPIONS[index],
                    "championInternalName": (
                        "MonkeyKing" if CHAMPIONS[index] == "Wukong" else CHAMPIONS[index]
                    ),
                    "playerName": f"player{index}",
                    "summonerName": f"player{index}#T{index}",
                    "selectionKeys": [f"player{index}", CHAMPIONS[index]],
                    "level": 1,
                    "items": [],
                    "alive": True,
                }
            )

        calls: list[tuple[int, str | None]] = []
        fail_cached_once = {"pending": True}

        def select(_transport, _url, row, **kwargs):
            pid = int(row["participantID"])
            preferred = kwargs.get("preferred_key")
            calls.append((pid, preferred))
            if preferred and pid == 1 and fail_cached_once["pending"]:
                fail_cached_once["pending"] = False
                body = {
                    "selectionName": "stale",
                    "cameraPosition": {"x": 0.0, "y": 0.0, "z": 0.0},
                }
                return (
                    {"readback": {"ok": True, "body": body}},
                    {"coordinateProven": False, "outcome": "stale"},
                    preferred,
                )
            key = preferred or f"player{pid - 1}"
            body = {
                "selectionName": key,
                "cameraPosition": {
                    "x": float(pid * 10),
                    "y": 0.0,
                    "z": float(pid * 10 + 1),
                },
            }
            return (
                {"readback": {"ok": True, "body": body}},
                {"coordinateProven": True, "outcome": "accepted"},
                key,
            )

        cache: dict[str, str] = {}
        with mock.patch.object(capture.probe, "focus_select_roster_member", select):
            first = capture.capture_frame_positions(
                lambda *args, **kwargs: {"ok": True},
                base_url="https://127.0.0.1:2999",
                roster=roster,
                timeout=0.1,
                settle_delay=0,
                final_settle=0,
                identity_retries=1,
                selection_key_cache=cache,
            )
            self.assertTrue(first["ok"], first.get("error"))
            self.assertEqual(len(cache), 10)
            calls.clear()
            second = capture.capture_frame_positions(
                lambda *args, **kwargs: {"ok": True},
                base_url="https://127.0.0.1:2999",
                roster=roster,
                timeout=0.1,
                settle_delay=0,
                final_settle=0,
                identity_retries=1,
                selection_key_cache=cache,
            )
        self.assertTrue(second["ok"], second.get("error"))
        self.assertEqual(second["timing"]["fastPathAttempts"], 10)
        self.assertEqual(second["timing"]["fastPathHits"], 9)
        self.assertEqual(second["timing"]["fallbackReasserts"], 1)
        self.assertEqual(len(calls), 11)
        benchmark = capture.summarize_frame_timings([second["timing"]])
        self.assertTrue(benchmark["comparisonOnly"])
        self.assertFalse(benchmark["machineSpecificAssertion"])


class CompactCachedSelectionTests(unittest.TestCase):
    def _roster(self) -> list[dict]:
        roster: list[dict] = []
        for index in range(10):
            roster.append(
                {
                    "participantID": index + 1,
                    "teamID": 100 if index < 5 else 200,
                    "puuid": f"puuid-{index}",
                    "championName": CHAMPIONS[index],
                    "championInternalName": (
                        "MonkeyKing" if CHAMPIONS[index] == "Wukong" else CHAMPIONS[index]
                    ),
                    "playerName": f"player{index}",
                    "summonerName": f"player{index}#T{index}",
                    "selectionKeys": [f"player{index}", CHAMPIONS[index]],
                    "level": 1,
                    "items": [],
                    "alive": True,
                }
            )
        return roster

    def _render_transport(self, *, stale_compact_pids: set[int] | None = None):
        stale_compact_pids = set(stale_compact_pids or set())
        state = {
            "cameraMode": "focus",
            "cameraAttached": False,
            "selectionName": "",
            "selectionOffset": {"x": 0.0, "y": 0.0, "z": 0.0},
            "cameraPosition": {"x": 0.0, "y": 0.0, "z": 0.0},
        }
        calls: list[tuple[str, dict | None]] = []

        def transport(method: str, url: str, *, body=None, timeout: float = 0.1):
            method_u = method.upper()
            payload = dict(body) if isinstance(body, dict) else None
            calls.append((method_u, payload))
            if method_u == "POST" and payload is not None:
                # Compact composite: selectionName + attach + offset together.
                if (
                    "selectionName" in payload
                    and payload.get("cameraAttached") is True
                    and "selectionOffset" in payload
                ):
                    name = str(payload.get("selectionName") or "")
                    pid = None
                    if name.startswith("player"):
                        try:
                            pid = int(name.replace("player", "")) + 1
                        except ValueError:
                            pid = None
                    if pid in stale_compact_pids:
                        # Stale retain: keep previous name/coords.
                        state["cameraAttached"] = True
                        state["selectionOffset"] = dict(payload["selectionOffset"])
                        if payload.get("cameraMode"):
                            state["cameraMode"] = payload["cameraMode"]
                    else:
                        state["selectionName"] = name
                        state["cameraAttached"] = True
                        state["selectionOffset"] = dict(payload["selectionOffset"])
                        if payload.get("cameraMode"):
                            state["cameraMode"] = payload["cameraMode"]
                        if pid is not None:
                            state["cameraPosition"] = {
                                "x": float(pid * 10),
                                "y": 0.0,
                                "z": float(pid * 10 + 1),
                            }
                    return {"ok": True, "body": dict(state)}
                if payload == {"cameraAttached": False}:
                    state["cameraAttached"] = False
                    return {"ok": True, "body": dict(state)}
                if set(payload.keys()) == {"selectionName"}:
                    name = str(payload.get("selectionName") or "")
                    state["selectionName"] = name
                    if name.startswith("player"):
                        pid = int(name.replace("player", "")) + 1
                        state["cameraPosition"] = {
                            "x": float(pid * 10),
                            "y": 0.0,
                            "z": float(pid * 10 + 1),
                        }
                    return {"ok": True, "body": dict(state)}
                if payload.get("cameraAttached") is True and "selectionOffset" in payload:
                    state["cameraAttached"] = True
                    state["selectionOffset"] = dict(payload["selectionOffset"])
                    return {"ok": True, "body": dict(state)}
                state.update(payload)
                return {"ok": True, "body": dict(state)}
            if method_u == "GET":
                return {"ok": True, "body": dict(state)}
            return {"ok": False, "error": f"unexpected {method_u}"}

        return transport, calls

    def test_compact_hit_uses_one_post_and_get_and_proves_identity(self) -> None:
        roster = self._roster()
        transport, calls = self._render_transport()
        cache: dict[str, str] = {}
        with mock.patch.object(capture.probe, "_settle", lambda _d: None):
            first = capture.capture_frame_positions(
                transport,
                base_url="https://127.0.0.1:2999",
                roster=roster,
                timeout=0.1,
                settle_delay=0,
                final_settle=0,
                identity_retries=0,
                selection_key_cache=cache,
                cached_selection_strategy="compact",
            )
        self.assertTrue(first["ok"], first.get("error"))
        self.assertEqual(len(cache), 10)
        self.assertEqual(first["timing"]["compactAttempts"], 0)
        self.assertEqual(first["timing"]["selectionRenderPosts"], 30)
        self.assertTrue(first["timing"]["cacheCommitted"])

        calls.clear()
        with mock.patch.object(capture.probe, "_settle", lambda _d: None):
            second = capture.capture_frame_positions(
                transport,
                base_url="https://127.0.0.1:2999",
                roster=roster,
                timeout=0.1,
                settle_delay=0,
                final_settle=0,
                identity_retries=0,
                selection_key_cache=cache,
                cached_selection_strategy="compact",
            )
        self.assertTrue(second["ok"], second.get("error"))
        self.assertEqual(second["timing"]["compactAttempts"], 10)
        self.assertEqual(second["timing"]["compactHits"], 10)
        self.assertEqual(second["timing"]["compactFallbacks"], 0)
        self.assertEqual(second["timing"]["selectionRenderPosts"], 10)
        self.assertEqual(second["timing"]["selectionRenderPostSavings"], 20)
        posts = [c for c in calls if c[0] == "POST"]
        gets = [c for c in calls if c[0] == "GET"]
        self.assertEqual(len(posts), 10)
        self.assertEqual(len(gets), 10)
        for _method, body in posts:
            assert body is not None
            self.assertIn("selectionName", body)
            self.assertTrue(body.get("cameraAttached"))
            self.assertEqual(body.get("cameraMode"), "focus")
        for participant in second["participants"]:
            self.assertEqual(
                participant["selectionNameCanonical"],
                participant["selectionKeyUsed"],
            )
            self.assertEqual(
                participant["position"]["x"],
                float(participant["participantID"] * 10),
            )

    def test_stale_compact_falls_back_to_full(self) -> None:
        roster = self._roster()
        transport, calls = self._render_transport(stale_compact_pids={1})
        cache: dict[str, str] = {}
        with mock.patch.object(capture.probe, "_settle", lambda _d: None):
            first = capture.capture_frame_positions(
                transport,
                base_url="https://127.0.0.1:2999",
                roster=roster,
                timeout=0.1,
                settle_delay=0,
                final_settle=0,
                identity_retries=0,
                selection_key_cache=cache,
                cached_selection_strategy="compact",
            )
            self.assertTrue(first["ok"], first.get("error"))
            calls.clear()
            second = capture.capture_frame_positions(
                transport,
                base_url="https://127.0.0.1:2999",
                roster=roster,
                timeout=0.1,
                settle_delay=0,
                final_settle=0,
                identity_retries=0,
                selection_key_cache=cache,
                cached_selection_strategy="compact",
            )
        self.assertTrue(second["ok"], second.get("error"))
        self.assertEqual(second["timing"]["compactAttempts"], 10)
        self.assertEqual(second["timing"]["compactHits"], 9)
        self.assertEqual(second["timing"]["compactFallbacks"], 1)
        # 9 compact POSTs + (1 compact miss + 3 full) = 9 + 4 = 13
        self.assertEqual(second["timing"]["selectionRenderPosts"], 13)
        self.assertEqual(second["timing"]["selectionRenderPostSavings"], 18)
        posts = [c for c in calls if c[0] == "POST"]
        self.assertEqual(len(posts), 13)

    def test_default_strategy_is_compact_with_full_opt_in(self) -> None:
        roster = self._roster()
        transport, calls = self._render_transport()
        cache: dict[str, str] = {}
        with mock.patch.object(capture.probe, "_settle", lambda _d: None):
            first = capture.capture_frame_positions(
                transport,
                base_url="https://127.0.0.1:2999",
                roster=roster,
                timeout=0.1,
                settle_delay=0,
                final_settle=0,
                identity_retries=0,
                selection_key_cache=cache,
            )
            self.assertTrue(first["ok"], first.get("error"))
            self.assertEqual(first["timing"]["cachedSelectionStrategy"], "compact")
            calls.clear()
            second = capture.capture_frame_positions(
                transport,
                base_url="https://127.0.0.1:2999",
                roster=roster,
                timeout=0.1,
                settle_delay=0,
                final_settle=0,
                identity_retries=0,
                selection_key_cache=cache,
            )
        self.assertTrue(second["ok"], second.get("error"))
        self.assertEqual(second["timing"]["cachedSelectionStrategy"], "compact")
        self.assertEqual(second["timing"]["compactAttempts"], 10)
        self.assertEqual(second["timing"]["compactHits"], 10)
        self.assertEqual(second["timing"]["selectionRenderPosts"], 10)
        posts = [c for c in calls if c[0] == "POST"]
        self.assertEqual(len(posts), 10)

        # Explicit full strategy still pays 3 POSTs per participant.
        transport_full, calls_full = self._render_transport()
        cache_full: dict[str, str] = {}
        with mock.patch.object(capture.probe, "_settle", lambda _d: None):
            warm = capture.capture_frame_positions(
                transport_full,
                base_url="https://127.0.0.1:2999",
                roster=roster,
                timeout=0.1,
                settle_delay=0,
                final_settle=0,
                identity_retries=0,
                selection_key_cache=cache_full,
                cached_selection_strategy="full",
            )
            self.assertTrue(warm["ok"], warm.get("error"))
            calls_full.clear()
            full = capture.capture_frame_positions(
                transport_full,
                base_url="https://127.0.0.1:2999",
                roster=roster,
                timeout=0.1,
                settle_delay=0,
                final_settle=0,
                identity_retries=0,
                selection_key_cache=cache_full,
                cached_selection_strategy="full",
            )
        self.assertTrue(full["ok"], full.get("error"))
        self.assertEqual(full["timing"]["cachedSelectionStrategy"], "full")
        self.assertEqual(full["timing"]["compactAttempts"], 0)
        self.assertEqual(full["timing"]["selectionRenderPosts"], 30)
        self.assertEqual(len([c for c in calls_full if c[0] == "POST"]), 30)

    def test_product_defaults_are_compact_and_zero_settle(self) -> None:
        self.assertEqual(capture.DEFAULT_FINAL_SETTLE, 0.0)
        self.assertEqual(
            capture.DEFAULT_CACHED_SELECTION_STRATEGY,
            capture.CACHED_SELECTION_STRATEGY_COMPACT,
        )
        self.assertEqual(capture.normalize_cached_selection_strategy(None), "compact")
        self.assertEqual(capture.normalize_cached_selection_strategy("default"), "compact")
        self.assertEqual(capture.normalize_cached_selection_strategy("full"), "full")
        parser = capture.build_arg_parser()
        # Minimal required args; defaults must be product keep values.
        ns = parser.parse_args(
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

    def test_cache_commits_only_after_whole_frame_succeeds(self) -> None:
        roster = self._roster()
        transport, _calls = self._render_transport()
        cache: dict[str, str] = {}
        with mock.patch.object(capture.probe, "_settle", lambda _d: None):
            first = capture.capture_frame_positions(
                transport,
                base_url="https://127.0.0.1:2999",
                roster=roster,
                timeout=0.1,
                settle_delay=0,
                final_settle=0,
                identity_retries=0,
                selection_key_cache=cache,
                cached_selection_strategy="compact",
            )
        self.assertTrue(first["ok"], first.get("error"))
        self.assertEqual(len(cache), 10)

        # Mid-frame failure must not commit new pending keys; existing cache stays.
        broken = list(roster)
        broken[5] = dict(broken[5])
        broken[5]["selectionKeys"] = []
        before = dict(cache)
        with mock.patch.object(capture.probe, "_settle", lambda _d: None):
            failed = capture.capture_frame_positions(
                transport,
                base_url="https://127.0.0.1:2999",
                roster=broken,
                timeout=0.1,
                settle_delay=0,
                final_settle=0,
                identity_retries=0,
                selection_key_cache=cache,
                cached_selection_strategy="compact",
            )
        self.assertFalse(failed["ok"])
        self.assertEqual(cache, before)
        self.assertNotIn("cacheCommitted", failed["timing"])


class ChampionIdentityTests(unittest.TestCase):
    def test_zaahen_and_wukong_identity_separation(self) -> None:
        zaahen = rofl_metadata.champion_identities(
            "Zaahen",
            available_assets=["Zaahen", "MonkeyKing"],
        )
        self.assertEqual(zaahen["display"], "Zaahen")
        self.assertEqual(zaahen["asset"], "Zaahen")
        self.assertTrue(zaahen["assetResolved"])
        self.assertIsNone(zaahen["model"])
        self.assertFalse(zaahen["modelResolved"])
        self.assertIn("no_zero_damage", zaahen["modelResolution"])

        wukong = rofl_metadata.champion_identities(
            "MonkeyKing",
            available_assets=["Zaahen", "MonkeyKing"],
        )
        self.assertEqual(wukong["raw"], "MonkeyKing")
        self.assertEqual(wukong["display"], "Wukong")
        self.assertEqual(wukong["asset"], "MonkeyKing")
        self.assertEqual(wukong["model"], "MonkeyKing")

    def test_stable_participant_ids_do_not_depend_on_input_order(self) -> None:
        rows = probe.build_roster_from_liveclient(
            live_players(score=0),
            {"allPlayers": live_players(score=0)},
        )
        forward = capture.assign_stable_participant_ids(rows)
        reverse = capture.assign_stable_participant_ids(list(reversed(rows)))
        forward_ids = {
            capture.roster_identity_key(row): row["participantID"] for row in forward
        }
        reverse_ids = {
            capture.roster_identity_key(row): row["participantID"] for row in reverse
        }
        self.assertEqual(forward_ids, reverse_ids)


if __name__ == "__main__":
    unittest.main()
