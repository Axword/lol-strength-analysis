#!/usr/bin/env python3
"""Unit tests for scripts/rofl_replay_api_probe.py (mocked transport)."""
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

import rofl_replay_api_probe as probe  # noqa: E402

GNAR_POS = {"x": 1829.9483642578125, "y": 52.84000015258789, "z": 12021.4287109375}
SAMIRA_POS = {"x": 12473.32421875, "y": 51.57305145263672, "z": 2773.39306640625}


class FakeTransport:
    """Mock Replay API with focus-mode coordinate simulation."""

    def __init__(
        self,
        *,
        reachable: bool = True,
        openapi_props: Optional[dict[str, Any]] = None,
        render_state: Optional[dict[str, Any]] = None,
        playback_state: Optional[dict[str, Any]] = None,
        canonicalize_map: Optional[dict[str, str]] = None,
        focus_positions: Optional[dict[str, dict[str, float]]] = None,
        force_camera_mode: Optional[str] = None,
        disconnect_on_restore: bool = False,
        corrupt_restore_readback: bool = False,
        players: Optional[list[dict[str, Any]]] = None,
    ) -> None:
        self.reachable = reachable
        self.openapi_props = openapi_props or {
            "cameraAttached": {"type": "boolean"},
            "cameraMode": {"type": "string"},
            "selectionName": {"type": "string"},
            "selectionOffset": {"type": "object"},
            "cameraPosition": {"type": "object"},
        }
        self.render_state = dict(
            render_state
            or {
                "cameraAttached": False,
                "cameraMode": "top",
                "cameraPosition": {"x": 100.0, "y": 50.0, "z": 200.0},
                "fieldOfView": 40,
                "selectionName": "",
                "selectionOffset": {"x": 0.0, "y": 0.0, "z": 0.0},
            }
        )
        self.playback_state = dict(
            playback_state
            or {
                "paused": True,
                "seeking": False,
                "time": 121.83765411376953,
                "speed": 1.0,
                "length": 1800.0,
            }
        )
        # When unpaused, advance playback.time (and nudge attached camera) like Riot.
        self._playback_mono_anchor: Optional[float] = None
        self._playback_time_anchor: Optional[float] = None
        self.advance_camera_while_unpaused = True
        self.canonicalize_map = dict(
            canonicalize_map
            or {
                "Gnar": "ltetol",
                "Samira": "aizen cifer",
                "Malphite": "awakening",
                "ltetol#NA1": "ltetol",
                "ltetol": "ltetol",
                "aizen cifer#EUW": "aizen cifer",
                "aizen cifer": "aizen cifer",
                "TahmKench": "nhUwUmi",
                "nhUwUmi#glhf": "nhUwUmi",
                "nhUwUmi": "nhUwUmi",
            }
        )
        self.focus_positions = dict(
            focus_positions
            or {
                "Gnar": dict(GNAR_POS),
                "ltetol": dict(GNAR_POS),
                "ltetol#NA1": dict(GNAR_POS),
                "Samira": dict(SAMIRA_POS),
                "aizen cifer": dict(SAMIRA_POS),
                "aizen cifer#EUW": dict(SAMIRA_POS),
                "TahmKench": {
                    "x": 5500.0,
                    "y": 50.0,
                    "z": 5500.0,
                },
                "nhUwUmi": {"x": 5500.0, "y": 50.0, "z": 5500.0},
                "nhUwUmi#glhf": {"x": 5500.0, "y": 50.0, "z": 5500.0},
            }
        )
        self.force_camera_mode = force_camera_mode
        self.disconnect_on_restore = disconnect_on_restore
        self.corrupt_restore_readback = corrupt_restore_readback
        self._restore_get_corrupt_armed = False
        self._seek_pending = False
        self.players = players or [
            {
                "championName": "Gnar",
                "rawChampionName": "Gnar",
                "summonerName": "ltetol#NA1",
                "riotIdGameName": "ltetol",
                "riotIdTagLine": "NA1",
                "team": "ORDER",
                "level": 11,
                "items": [{"itemID": 3047}],
                "isDead": False,
            },
            {
                "championName": "Samira",
                "rawChampionName": "Samira",
                "summonerName": "aizen cifer#EUW",
                "riotIdGameName": "aizen cifer",
                "riotIdTagLine": "EUW",
                "team": "CHAOS",
                "level": 10,
                "items": [{"itemID": 6673}],
                "isDead": False,
            },
        ]
        self.calls: list[tuple[str, str, Any]] = []
        self._selected_champion: Optional[str] = None
        self._armed_restore_disconnect = False

    def __call__(
        self,
        method: str,
        url: str,
        *,
        body: Any = None,
        timeout: float = 2.0,
    ) -> dict[str, Any]:
        self.calls.append((method.upper(), url, body))
        if not self.reachable:
            return self._err(url, method, "URLError: Connection refused")

        path = url.split("2999", 1)[-1] if "2999" in url else url

        if path.endswith("/swagger/v3/openapi.json") and method.upper() == "GET":
            return self._ok(
                url,
                method,
                {
                    "openapi": "3.0.0",
                    "paths": {
                        "/replay/game": {},
                        "/replay/playback": {},
                        "/replay/render": {},
                        "/replay/sequence": {},
                        "/liveclientdata/allgamedata": {},
                        "/liveclientdata/playerlist": {},
                    },
                    "components": {
                        "schemas": {
                            "Render": {"properties": dict(self.openapi_props)},
                            "Sequence": {
                                "properties": {
                                    "selectionName": {"type": "array"},
                                    "selectionOffset": {"type": "array"},
                                }
                            },
                        }
                    },
                },
            )

        if path.endswith("/replay/game") and method.upper() == "GET":
            return self._ok(url, method, {"processID": 4242})

        if path.endswith("/replay/sequence") and method.upper() == "GET":
            return self._ok(url, method, {"selectionName": [], "selectionOffset": []})

        if path.endswith("/liveclientdata/playerlist") and method.upper() == "GET":
            return self._ok(url, method, list(self.players))

        if path.endswith("/liveclientdata/allgamedata") and method.upper() == "GET":
            return self._ok(
                url,
                method,
                {
                    "activePlayer": {},
                    "allPlayers": list(self.players),
                    "gameData": {"gameTime": self.playback_state.get("time", 0)},
                },
            )

        if path.endswith("/replay/playback"):
            if method.upper() == "GET":
                if self._seek_pending:
                    self.playback_state["seeking"] = False
                    self._seek_pending = False
                self._advance_playback_clock()
                body = dict(self.playback_state)
                if self._restore_get_corrupt_armed and self.corrupt_restore_readback:
                    body["seeking"] = True
                return self._ok(url, method, body)
            if method.upper() == "POST" and isinstance(body, dict):
                if self._armed_restore_disconnect and self.disconnect_on_restore:
                    self.reachable = False
                    return self._err(url, method, "URLError: Connection refused")
                # Freeze clock before applying pause/seek mutations.
                self._advance_playback_clock()
                # Simulate Riot: posting time triggers seeking=true until next GET settles.
                if "time" in body:
                    self.playback_state["seeking"] = True
                    self.playback_state["time"] = body["time"]
                    self._seek_pending = True
                    self._playback_time_anchor = float(body["time"])
                    if not self.playback_state.get("paused") and body.get("paused") is not True:
                        self._playback_mono_anchor = time.monotonic()
                for k, v in body.items():
                    if k == "time":
                        continue
                    self.playback_state[k] = v
                if "time" not in body:
                    self.playback_state["seeking"] = False
                    self._seek_pending = False
                if body.get("paused") is True:
                    self._playback_mono_anchor = None
                    self._playback_time_anchor = float(self.playback_state.get("time") or 0)
                elif body.get("paused") is False:
                    self._playback_mono_anchor = time.monotonic()
                    self._playback_time_anchor = float(self.playback_state.get("time") or 0)
                if self.corrupt_restore_readback and set(body.keys()) <= {
                    "paused",
                    "speed",
                }:
                    self._restore_get_corrupt_armed = True
                return self._ok(url, method, dict(self.playback_state))

        if path.endswith("/replay/render"):
            if method.upper() == "GET":
                self._advance_playback_clock()
                body = dict(self.render_state)
                if self._restore_get_corrupt_armed and self.corrupt_restore_readback:
                    body["cameraMode"] = "path"
                    body["cameraAttached"] = True
                # Arm disconnect after a successful focus readback.
                if (
                    self.render_state.get("cameraMode") == "focus"
                    and self.render_state.get("cameraAttached")
                    and self.render_state.get("selectionName")
                ):
                    self._armed_restore_disconnect = True
                return self._ok(url, method, body)
            if method.upper() == "POST" and isinstance(body, dict):
                if self._armed_restore_disconnect and self.disconnect_on_restore:
                    if "fieldOfView" in body or (
                        "cameraMode" in body and body.get("cameraMode") != "focus"
                    ):
                        self.reachable = False
                        return self._err(url, method, "URLError: Connection refused")
                    if (
                        "cameraPosition" in body
                        and "selectionName" not in body
                        and "cameraAttached" not in body
                    ):
                        self.reachable = False
                        return self._err(url, method, "URLError: Connection refused")
                    # Full snapshot restore often includes fieldOfView + cameraMode top.
                    if "fieldOfView" in body:
                        self.reachable = False
                        return self._err(url, method, "URLError: Connection refused")
                self._apply_render_post(body)
                if self.corrupt_restore_readback and "fieldOfView" in body:
                    self._restore_get_corrupt_armed = True
                return self._ok(url, method, dict(self.render_state))

        return self._err(url, method, "HTTP 404: Not Found", status=404)

    def _apply_render_post(self, body: dict[str, Any]) -> None:
        if self.force_camera_mode is not None and "cameraMode" in body:
            self.render_state["cameraMode"] = self.force_camera_mode
        elif "cameraMode" in body:
            self.render_state["cameraMode"] = body["cameraMode"]

        if "cameraAttached" in body:
            self.render_state["cameraAttached"] = body["cameraAttached"]
        if "selectionOffset" in body:
            self.render_state["selectionOffset"] = body["selectionOffset"]
        if "selectionName" in body:
            posted = body["selectionName"]
            # Spaced champion display names silently retain previous selection
            # (adversarial live finding: "Tahm Kench").
            if " " in str(posted) and posted not in self.canonicalize_map:
                pass
            else:
                self._selected_champion = posted if posted not in (None, "") else None
                if posted in (None, ""):
                    self.render_state["selectionName"] = ""
                else:
                    self.render_state["selectionName"] = self.canonicalize_map.get(
                        posted, posted
                    )

        mode = self.render_state.get("cameraMode")
        attached = bool(self.render_state.get("cameraAttached"))
        key = self._selected_champion
        canon = self.render_state.get("selectionName")
        if mode == "focus" and attached:
            for lookup in (key, canon):
                if lookup and lookup in self.focus_positions:
                    self.render_state["cameraPosition"] = dict(
                        self.focus_positions[lookup]
                    )
                    break

        for key2, value in body.items():
            if key2 in (
                "cameraMode",
                "cameraAttached",
                "selectionOffset",
                "selectionName",
            ):
                continue
            self.render_state[key2] = value

    def _advance_playback_clock(self) -> None:
        """Advance playback.time while unpaused; optionally nudge cameraPosition."""
        if self.playback_state.get("paused"):
            return
        if self._playback_mono_anchor is None or self._playback_time_anchor is None:
            # Start advancing from first observed unpaused GET/POST.
            self._playback_mono_anchor = time.monotonic()
            self._playback_time_anchor = float(self.playback_state.get("time") or 0)
            return
        elapsed = max(0.0, time.monotonic() - float(self._playback_mono_anchor))
        try:
            speed = max(0.0, float(self.playback_state.get("speed") or 1.0))
        except (TypeError, ValueError):
            speed = 1.0
        new_t = float(self._playback_time_anchor) + elapsed * speed
        self.playback_state["time"] = new_t
        if (
            self.advance_camera_while_unpaused
            and self.render_state.get("cameraAttached")
            and isinstance(self.render_state.get("cameraPosition"), dict)
        ):
            pos = dict(self.render_state["cameraPosition"])
            # Live focus camera tracks the moving champion after resume.
            pos["x"] = float(pos.get("x") or 0.0) + elapsed * 25.0
            pos["z"] = float(pos.get("z") or 0.0) + elapsed * 15.0
            self.render_state["cameraPosition"] = pos

    @staticmethod
    def _ok(url: str, method: str, body: Any) -> dict[str, Any]:
        return {
            "ok": True,
            "status": 200,
            "url": url,
            "method": method.upper(),
            "body": body,
            "rawText": None,
            "error": None,
        }

    @staticmethod
    def _err(
        url: str, method: str, error: str, status: Optional[int] = None
    ) -> dict[str, Any]:
        return {
            "ok": False,
            "status": status,
            "url": url,
            "method": method.upper(),
            "body": None,
            "rawText": None,
            "error": error,
        }


def _stub_rofl_app(tmp: str) -> tuple[Path, Path]:
    rofl = Path(tmp) / "stub.rofl"
    version = b"16.14.794.5912"
    rofl.write_bytes(
        b"RIOT\x02\x00" + b"\x00" * 8 + bytes([len(version)]) + version + b"\x00" * 32
    )
    app = Path(tmp) / "LeagueofLegends.app"
    plist = app / "Contents" / "Info.plist"
    plist.parent.mkdir(parents=True)
    plist.write_bytes(
        b"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleVersion</key><string>16.14.7945912</string>
<key>FileVersion</key><string>16.14.794.5912</string>
</dict></plist>
"""
    )
    return rofl, app


class NormalizeBuildTests(unittest.TestCase):
    def test_dotted_and_compact_match(self) -> None:
        self.assertEqual(probe.normalize_build("16.14.794.5912"), "16147945912")
        self.assertEqual(probe.normalize_build("16.14.7945912"), "16147945912")
        self.assertTrue(probe.builds_match("16.14.794.5912", "16.14.7945912"))
        self.assertFalse(probe.builds_match("16.14.794.5912", "16.13.791.5903"))


class LoopbackTlsTests(unittest.TestCase):
    def test_loopback_only(self) -> None:
        self.assertTrue(probe.is_loopback_url("https://127.0.0.1:2999/replay/game"))
        self.assertTrue(probe.is_loopback_url("https://localhost:2999/x"))
        self.assertFalse(probe.is_loopback_url("https://example.com:2999/x"))

    def test_ssl_context_verify_mode(self) -> None:
        loop = probe.ssl_context_for_url("https://127.0.0.1:2999/replay/game")
        self.assertEqual(loop.verify_mode, probe.ssl.CERT_NONE)
        remote = probe.ssl_context_for_url("https://example.com/replay/game")
        self.assertNotEqual(remote.verify_mode, probe.ssl.CERT_NONE)


class UnreachableStatusTests(unittest.TestCase):
    def test_unreachable_exit_zero_by_default(self) -> None:
        transport = FakeTransport(reachable=False)
        with tempfile.TemporaryDirectory() as tmp:
            rofl, app = _stub_rofl_app(tmp)
            report = probe.build_status_report(
                rofl_path=rofl,
                app_path=app,
                base_url="https://127.0.0.1:2999",
                transport=transport,
            )
            self.assertFalse(report["apiReachable"])
            self.assertEqual(report["positionCoverage"], "none")
            self.assertTrue(report["buildMatch"])

            with mock.patch(
                "rofl_replay_api_probe.default_http_transport", transport
            ), mock.patch("sys.stdout", new=io.StringIO()):
                code = probe.main(
                    ["--rofl", str(rofl), "--app", str(app), "--timeout", "0.1"]
                )
            self.assertEqual(code, 0)

            with mock.patch(
                "rofl_replay_api_probe.default_http_transport", transport
            ), mock.patch("sys.stdout", new=io.StringIO()):
                code_req = probe.main(
                    [
                        "--rofl",
                        str(rofl),
                        "--app",
                        str(app),
                        "--timeout",
                        "0.1",
                        "--require-api",
                    ]
                )
            self.assertEqual(code_req, 1)


class EndpointEvidenceTests(unittest.TestCase):
    def test_successful_endpoint_evidence(self) -> None:
        transport = FakeTransport(reachable=True)
        with tempfile.TemporaryDirectory() as tmp:
            rofl, app = _stub_rofl_app(tmp)
            schema_out = Path(tmp) / "openapi.json"
            report = probe.build_status_report(
                rofl_path=rofl,
                app_path=app,
                base_url="https://127.0.0.1:2999",
                transport=transport,
                schema_out=schema_out,
            )
            self.assertTrue(report["apiReachable"])
            self.assertTrue(report["endpoints"]["playback"]["ok"])
            self.assertTrue(report["endpoints"]["render"]["ok"])
            self.assertTrue(report["endpoints"]["sequence"]["ok"])
            self.assertTrue(report["endpoints"]["liveclient_playerlist"]["ok"])
            self.assertTrue(schema_out.is_file())


class FocusSelectionTests(unittest.TestCase):
    def test_focus_distinct_positions_supported(self) -> None:
        transport = FakeTransport(reachable=True)
        result = probe.probe_selection(
            transport,
            "https://127.0.0.1:2999",
            "Gnar",
            schema_names=set(transport.openapi_props),
            settle_delay=0,
        )
        self.assertEqual(result["outcome"], "supported")
        self.assertEqual(result["positionCoverage"], probe.POSITION_SOURCE_FOCUS)
        self.assertTrue(result["positionClaimAllowed"])
        self.assertTrue(result["classification"]["nameCanonicalized"])
        self.assertTrue(result["classification"]["focusMode"])
        self.assertTrue(result["restoreSucceeded"])
        pause = [
            c
            for c in transport.calls
            if c[0] == "POST" and c[1].endswith("/replay/playback")
        ][0]
        self.assertEqual(pause[2], {"paused": True})
        self.assertNotIn("time", pause[2])

    def test_top_mode_unchanged_camera_not_supported(self) -> None:
        transport = FakeTransport(reachable=True, force_camera_mode="top")
        baseline = dict(transport.render_state["cameraPosition"])
        result = probe.probe_selection(
            transport,
            "https://127.0.0.1:2999",
            "Gnar",
            schema_names=set(transport.openapi_props),
            settle_delay=0,
        )
        self.assertNotEqual(result["outcome"], "supported")
        self.assertEqual(result["positionCoverage"], "none")
        self.assertFalse(result["positionClaimAllowed"])
        self.assertEqual(
            result["classification"]["evidence"]["cameraPosition"], baseline
        )

    def test_restore_on_success_and_failure(self) -> None:
        transport = FakeTransport(reachable=True)
        original = dict(transport.render_state)
        result = probe.probe_selection(
            transport,
            "https://127.0.0.1:2999",
            "Samira",
            schema_names=set(transport.openapi_props),
            settle_delay=0,
        )
        self.assertTrue(result["restoreAttempted"])
        self.assertTrue(result["restoreSucceeded"])
        bulk_restore = [
            c
            for c in transport.calls
            if c[0] == "POST"
            and c[1].endswith("/replay/render")
            and isinstance(c[2], dict)
            and "fieldOfView" in c[2]
        ]
        self.assertTrue(bulk_restore)
        self.assertEqual(bulk_restore[-1][2].get("fieldOfView"), original["fieldOfView"])
        playback_posts = [
            c
            for c in transport.calls
            if c[0] == "POST" and c[1].endswith("/replay/playback")
        ]
        for _, _, body in playback_posts:
            self.assertNotIn("time", body or {})

        transport2 = FakeTransport(reachable=True)
        result2 = probe.probe_selection(
            transport2,
            "https://127.0.0.1:2999",
            "Gnar",
            schema_names=set(transport2.openapi_props),
            settle_delay=0,
            inject_failure_after_post=True,
        )
        self.assertTrue(result2["restoreAttempted"])
        self.assertTrue(result2["restoreSucceeded"])
        self.assertIn("injected failure", result2["error"] or "")

    def test_disconnect_during_restore_nonzero(self) -> None:
        transport = FakeTransport(reachable=True, disconnect_on_restore=True)
        result = probe.probe_selection(
            transport,
            "https://127.0.0.1:2999",
            "Gnar",
            schema_names=set(transport.openapi_props),
            settle_delay=0,
        )
        self.assertTrue(result["restoreAttempted"])
        self.assertFalse(result["restoreSucceeded"])

        with tempfile.TemporaryDirectory() as tmp:
            rofl, app = _stub_rofl_app(tmp)
            transport2 = FakeTransport(reachable=True, disconnect_on_restore=True)
            with mock.patch(
                "rofl_replay_api_probe.default_http_transport", transport2
            ), mock.patch("sys.stdout", new=io.StringIO()):
                code = probe.main(
                    [
                        "--rofl",
                        str(rofl),
                        "--app",
                        str(app),
                        "--probe-selection",
                        "Gnar",
                        "--settle-delay",
                        "0",
                        "--timeout",
                        "0.1",
                    ]
                )
            self.assertEqual(code, 3)


class CaptureCurrentTests(unittest.TestCase):
    def test_capture_distinct_focus_positions_and_repeat(self) -> None:
        transport = FakeTransport(reachable=True)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "capture.json"
            capture = probe.capture_current_positions(
                transport,
                "https://127.0.0.1:2999",
                settle_delay=0,
            )
            self.assertTrue(capture["ok"])
            self.assertEqual(capture["hpCoverage"], "none")
            self.assertEqual(capture["positionCoverage"], probe.POSITION_SOURCE_FOCUS)
            self.assertFalse(capture["provenance"]["ingestible"])
            self.assertEqual(capture["gameTimeMs"], 121838)
            self.assertEqual(len(capture["participants"]), 2)
            by_champ = {p["championName"]: p for p in capture["participants"]}
            self.assertEqual(by_champ["Gnar"]["position"]["x"], GNAR_POS["x"])
            self.assertEqual(by_champ["Samira"]["position"]["z"], SAMIRA_POS["z"])
            self.assertEqual(
                by_champ["Gnar"]["positionSource"], probe.POSITION_SOURCE_FOCUS
            )
            # Live patch 16.14 accepts the plain Riot game name before the
            # tagged identity; champion display name remains only a fallback.
            self.assertEqual(by_champ["Gnar"]["selectionKeyUsed"], "ltetol")
            self.assertTrue(capture["repeatEvidence"]["matched"])
            self.assertTrue(capture["restoreSucceeded"])

            rofl, app = _stub_rofl_app(tmp)
            transport2 = FakeTransport(reachable=True)
            report = probe.build_status_report(
                rofl_path=rofl,
                app_path=app,
                base_url="https://127.0.0.1:2999",
                transport=transport2,
                settle_delay=0,
                capture_current=True,
                capture_out=out,
            )
            self.assertTrue(report["capture"]["ok"])
            self.assertEqual(report["positionCoverage"], probe.POSITION_SOURCE_FOCUS)
            self.assertEqual(report["hpCoverage"], "none")
            saved = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(saved["kind"], "replay_api_focus_capture")

    def test_spaced_champion_display_name_stale_selection_rejected(self) -> None:
        """\"Tahm Kench\" retains previous selection; player identity / TahmKench works."""
        tahm_pos = {"x": 5500.0, "y": 50.0, "z": 5500.0}
        transport = FakeTransport(
            reachable=True,
            players=[
                {
                    "championName": "Gnar",
                    "rawChampionName": "Gnar",
                    "summonerName": "ltetol#NA1",
                    "riotIdGameName": "ltetol",
                    "riotIdTagLine": "NA1",
                    "team": "ORDER",
                    "level": 11,
                    "items": [],
                    "isDead": False,
                },
                {
                    "championName": "Tahm Kench",
                    "rawChampionName": "TahmKench",
                    "summonerName": "nhUwUmi#glhf",
                    "riotIdGameName": "nhUwUmi",
                    "riotIdTagLine": "glhf",
                    "team": "CHAOS",
                    "level": 9,
                    "items": [],
                    "isDead": False,
                },
            ],
            focus_positions={
                "ltetol#NA1": dict(GNAR_POS),
                "ltetol": dict(GNAR_POS),
                "Gnar": dict(GNAR_POS),
                "nhUwUmi#glhf": dict(tahm_pos),
                "nhUwUmi": dict(tahm_pos),
                "TahmKench": dict(tahm_pos),
            },
        )

        # Display name alone: stale retain → invalid even with finite previous camera.
        transport.render_state["selectionName"] = "ltetol"
        transport.render_state["cameraPosition"] = dict(GNAR_POS)
        transport.render_state["cameraMode"] = "focus"
        transport.render_state["cameraAttached"] = True
        transport._selected_champion = "ltetol"
        steps = probe.focus_select_target(
            transport,
            "https://127.0.0.1:2999/replay/render",
            "Tahm Kench",
            timeout=1.0,
            settle_delay=0,
        )
        body = steps["readback"]["body"]
        bad = probe.classify_focus_readback(
            "Tahm Kench",
            body,
            expected_player_identity="nhUwUmi",
            previous_selection_name="ltetol",
        )
        self.assertTrue(bad["staleRetained"] or not bad["identityMatched"])
        self.assertFalse(bad["coordinateProven"])
        self.assertEqual(body.get("selectionName"), "ltetol")

        # Player identity resolves canonically with distinct coords.
        capture = probe.capture_current_positions(
            transport,
            "https://127.0.0.1:2999",
            settle_delay=0,
        )
        self.assertTrue(capture["ok"], capture.get("error"))
        self.assertEqual(len(capture["participants"]), 2)
        xs = {(p["position"]["x"], p["position"]["z"]) for p in capture["participants"]}
        self.assertEqual(len(xs), 2)
        tahm = next(p for p in capture["participants"] if p["championName"] == "Tahm Kench")
        self.assertEqual(tahm["selectionNameCanonical"], "nhUwUmi")
        self.assertIn(tahm["selectionKeyUsed"], ("nhUwUmi#glhf", "nhUwUmi", "TahmKench"))
        self.assertNotEqual(tahm["selectionKeyUsed"], "Tahm Kench")

    def test_capture_restore_on_failure(self) -> None:
        transport = FakeTransport(reachable=True)
        capture = probe.capture_current_positions(
            transport,
            "https://127.0.0.1:2999",
            settle_delay=0,
            inject_failure_mid_capture=True,
        )
        self.assertFalse(capture["ok"])
        self.assertTrue(capture["restoreAttempted"])
        self.assertTrue(capture["restoreSucceeded"])
        self.assertEqual(capture["positionCoverage"], "none")
        self.assertEqual(capture["hpCoverage"], "none")

    def test_capture_top_mode_fails_coordinate_gate(self) -> None:
        transport = FakeTransport(reachable=True, force_camera_mode="top")
        capture = probe.capture_current_positions(
            transport,
            "https://127.0.0.1:2999",
            settle_delay=0,
        )
        self.assertFalse(capture["ok"])
        self.assertEqual(capture["positionCoverage"], "none")
        self.assertTrue(capture["restoreSucceeded"])


class RestoreAndFallbackTests(unittest.TestCase):
    def test_restore_bodies_never_include_time(self) -> None:
        pb = {"paused": True, "seeking": False, "time": 12.5, "speed": 1.0}
        rb = {"cameraMode": "top", "cameraAttached": False}
        restore_pb, _ = probe._restore_bodies(pb, rb)
        self.assertNotIn("time", restore_pb)
        self.assertEqual(set(restore_pb.keys()), {"paused", "speed"})

    def test_no_playback_post_contains_time(self) -> None:
        transport = FakeTransport(reachable=True)
        result = probe.probe_selection(
            transport,
            "https://127.0.0.1:2999",
            "Gnar",
            schema_names=set(transport.openapi_props),
            settle_delay=0,
        )
        self.assertTrue(result["restoreSucceeded"])
        for method, url, body in transport.calls:
            if method == "POST" and url.endswith("/replay/playback"):
                self.assertIsInstance(body, dict)
                self.assertNotIn("time", body)

        transport2 = FakeTransport(reachable=True)
        capture = probe.capture_current_positions(
            transport2, "https://127.0.0.1:2999", settle_delay=0
        )
        self.assertTrue(capture["ok"], capture.get("error"))
        for method, url, body in transport2.calls:
            if method == "POST" and url.endswith("/replay/playback"):
                self.assertNotIn("time", body or {})

    def test_restore_failed_when_readback_mismatches(self) -> None:
        transport = FakeTransport(reachable=True, corrupt_restore_readback=True)
        result = probe.probe_selection(
            transport,
            "https://127.0.0.1:2999",
            "Gnar",
            schema_names=set(transport.openapi_props),
            settle_delay=0,
        )
        self.assertTrue(result["restoreAttempted"])
        self.assertFalse(result["restoreSucceeded"])
        err = (result.get("error") or "").lower()
        self.assertTrue("mismatch" in err or "seeking" in err, err)

    def test_capture_requires_already_paused(self) -> None:
        transport = FakeTransport(
            reachable=True,
            playback_state={
                "paused": False,
                "seeking": False,
                "time": 10.0,
                "speed": 1.0,
                "length": 100.0,
            },
        )
        capture = probe.capture_current_positions(
            transport, "https://127.0.0.1:2999", settle_delay=0
        )
        self.assertFalse(capture["ok"])
        self.assertIn("paused", (capture.get("error") or "").lower())
        self.assertFalse(capture["restoreAttempted"])
        # Must not have mutated playback.
        playback_posts = [
            c
            for c in transport.calls
            if c[0] == "POST" and c[1].endswith("/replay/playback")
        ]
        self.assertEqual(playback_posts, [])

    def test_champion_internal_name_strips_localization_prefix(self) -> None:
        name = probe.champion_internal_name(
            "Tahm Kench",
            {"rawChampionName": "game_character_displayname_TahmKench"},
        )
        self.assertEqual(name, "TahmKench")
        row = probe.build_roster_from_liveclient(
            [
                {
                    "championName": "Tahm Kench",
                    "rawChampionName": "game_character_displayname_TahmKench",
                    "summonerName": "nhUwUmi#glhf",
                    "riotIdGameName": "nhUwUmi",
                    "riotIdTagLine": "glhf",
                    "team": "ORDER",
                }
            ],
            None,
        )[0]
        self.assertEqual(row["championInternalName"], "TahmKench")
        self.assertIn("TahmKench", row["selectionKeys"])
        self.assertNotIn("Tahm Kench", row["selectionKeys"])
        self.assertNotIn("game_character_displayname_TahmKench", row["selectionKeys"])

    def test_endpoint_evidence_is_compact(self) -> None:
        transport = FakeTransport(reachable=True)
        ep = probe.probe_endpoints(transport, "https://127.0.0.1:2999")
        lcd = ep["endpoints"]["liveclient_allgamedata"]
        self.assertNotIn("sample", lcd)
        self.assertIn("summary", lcd)
        self.assertIn("allPlayersCount", lcd["summary"])
        self.assertNotIn("allPlayers", lcd["summary"])
        self.assertEqual(ep["endpoints"]["liveclient_playerlist"].get("count"), 2)


class MainGuardTests(unittest.TestCase):
    def test_refuse_non_loopback(self) -> None:
        with mock.patch("sys.stdout", new=io.StringIO()):
            code = probe.main(
                ["--base-url", "https://example.com:2999", "--rofl", "/dev/null"]
            )
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
