#!/usr/bin/env python3
"""Shared global lock and GET-only identity preflight for Replay API capture."""
from __future__ import annotations

import fcntl
import json
import os
import socket
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional, Type

import rofl_metadata
import rofl_replay_api_probe as replay_probe

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_ROOT = ROOT / "artifacts/rofl"


class ReplayGuardError(RuntimeError):
    """Capture must stop before any output or Replay API mutation."""


def controller_lock_path(*, artifact_root: Path = ARTIFACT_ROOT) -> Path:
    return artifact_root / ".replay-api-controller.lock"


class ReplayControllerLock:
    """Kernel-backed exclusive lock held for preflight, capture, and restore."""

    def __init__(
        self,
        path: Path,
        *,
        error_type: Type[Exception] = ReplayGuardError,
    ) -> None:
        self.path = path
        self.error_type = error_type
        self._fh: Optional[Any] = None

    def acquire(self) -> "ReplayControllerLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fh = self.path.open("a+", encoding="utf-8")
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            fh.seek(0)
            owner = fh.read().strip() or "unknown owner"
            fh.close()
            raise self.error_type(
                f"Replay API controller already locked ({owner})"
            ) from exc
        owner = {
            "pid": os.getpid(),
            "host": socket.gethostname(),
            "acquiredAt": (
                datetime.now(timezone.utc)
                .isoformat()
                .replace("+00:00", "Z")
            ),
        }
        fh.seek(0)
        fh.truncate()
        fh.write(json.dumps(owner, separators=(",", ":")) + "\n")
        fh.flush()
        os.fsync(fh.fileno())
        self._fh = fh
        return self

    def release(self) -> None:
        if self._fh is None:
            return
        try:
            fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)
        finally:
            self._fh.close()
            self._fh = None

    def __enter__(self) -> "ReplayControllerLock":
        return self.acquire()

    def __exit__(self, _type: Any, _value: Any, _tb: Any) -> None:
        self.release()


def _active_build_candidates(game: Any, all_game_data: Any) -> list[str]:
    values: list[str] = []
    for body in (game, all_game_data):
        if not isinstance(body, Mapping):
            continue
        candidates = [body]
        if isinstance(body.get("gameData"), Mapping):
            candidates.append(body["gameData"])
        for candidate in candidates:
            for key in ("gameVersion", "buildVersion", "version"):
                value = str(candidate.get(key) or "").strip()
                if value:
                    values.append(value)
    return values


def _active_game_id(game: Any, all_game_data: Any) -> Optional[int]:
    for body in (game, all_game_data):
        if not isinstance(body, Mapping):
            continue
        candidates = [body]
        if isinstance(body.get("gameData"), Mapping):
            candidates.append(body["gameData"])
        for candidate in candidates:
            for key in ("gameID", "gameId", "matchId", "matchID"):
                try:
                    value = int(candidate.get(key))
                except (TypeError, ValueError):
                    continue
                if value > 0:
                    return value
    return None


def inspect_active_replay(
    transport: replay_probe.Transport,
    *,
    base_url: str,
    timeout: float,
) -> dict[str, Any]:
    if not replay_probe.is_loopback_url(base_url):
        raise ReplayGuardError(f"refusing non-loopback Replay API URL: {base_url}")
    base = base_url.rstrip("/")
    endpoints = {
        "game": transport("GET", f"{base}/replay/game", timeout=timeout),
        "playback": transport("GET", f"{base}/replay/playback", timeout=timeout),
        "playerlist": transport(
            "GET",
            f"{base}/liveclientdata/playerlist",
            timeout=timeout,
        ),
        "allgamedata": transport(
            "GET",
            f"{base}/liveclientdata/allgamedata",
            timeout=timeout,
        ),
    }
    required = ("playback", "playerlist", "allgamedata")
    failed = [name for name in required if not endpoints[name].get("ok")]
    if failed:
        raise ReplayGuardError(f"active replay preflight GET failed: {failed}")
    return {
        "game": (
            endpoints["game"].get("body")
            if endpoints["game"].get("ok")
            else {}
        ),
        "playback": endpoints["playback"].get("body") or {},
        "allgamedata": endpoints["allgamedata"].get("body") or {},
        "roster": replay_probe.build_roster_from_liveclient(
            endpoints["playerlist"].get("body"),
            endpoints["allgamedata"].get("body"),
        ),
    }


def _identity_aliases(participant: Mapping[str, Any]) -> set[str]:
    identity = rofl_metadata.stable_identity_from_row(participant)
    aliases: set[str] = set()
    if identity.get("puuid"):
        aliases.add(f"puuid:{identity['puuid']}")
    riot_id = identity.get("riotId") or {}
    if riot_id.get("normalized"):
        aliases.add(f"riotid:{riot_id['normalized']}")
    return aliases


def verify_active_replay(
    metadata: Mapping[str, Any],
    active: Mapping[str, Any],
    *,
    app_path: Path,
) -> dict[str, Any]:
    app = replay_probe.read_app_build(app_path)
    if not replay_probe.builds_match(
        str(metadata.get("build") or ""),
        str(app.get("version") or ""),
    ):
        raise ReplayGuardError(
            "client/replay build mismatch before capture "
            f"(rofl={metadata.get('build')!r}, app={app.get('version')!r})"
        )
    active_builds = _active_build_candidates(
        active.get("game"),
        active.get("allgamedata"),
    )
    for active_build in active_builds:
        if not replay_probe.builds_match(
            str(metadata.get("build") or ""),
            active_build,
        ):
            raise ReplayGuardError(
                "wrong active replay build "
                f"(expected={metadata.get('build')!r}, active={active_build!r})"
            )

    active_game_id = _active_game_id(
        active.get("game"),
        active.get("allgamedata"),
    )
    if active_game_id is not None and active_game_id != int(metadata["gameId"]):
        raise ReplayGuardError(
            f"wrong active replay gameID {active_game_id} != {metadata['gameId']}"
        )

    try:
        active_duration_ms = int(
            round(float((active.get("playback") or {}).get("length")) * 1000)
        )
    except (TypeError, ValueError):
        raise ReplayGuardError("active replay playback length missing") from None
    expected_duration_ms = int(metadata["durationMs"])
    tolerance_ms = max(
        5_000,
        min(15_000, int(expected_duration_ms * 0.01)),
    )
    if abs(active_duration_ms - expected_duration_ms) > tolerance_ms:
        raise ReplayGuardError(
            "wrong active replay duration "
            f"({active_duration_ms}ms vs {expected_duration_ms}ms, "
            f"tolerance={tolerance_ms}ms)"
        )

    expected = list(metadata.get("participants") or [])
    live = list(active.get("roster") or [])
    if len(expected) != 10 or len(live) != 10:
        raise ReplayGuardError(
            "active replay roster size mismatch "
            f"(metadata={len(expected)}, live={len(live)})"
        )
    live_aliases: dict[str, list[int]] = {}
    for index, participant in enumerate(live):
        aliases = _identity_aliases(participant)
        if not aliases:
            raise ReplayGuardError(
                f"active participant lacks PUUID/full Riot ID: index={index}"
            )
        for alias in aliases:
            live_aliases.setdefault(alias, []).append(index)

    used: set[int] = set()
    for participant in expected:
        source_identity = participant.get("sourceIdentity") or {}
        aliases = set()
        if source_identity.get("puuid"):
            aliases.add(f"puuid:{source_identity['puuid']}")
        riot_id = source_identity.get("riotId") or {}
        if riot_id.get("normalized"):
            aliases.add(f"riotid:{riot_id['normalized']}")
        if not aliases:
            raise ReplayGuardError("ROFL participant lacks PUUID/full Riot ID")
        matches = {
            index
            for alias in aliases
            for index in live_aliases.get(alias, [])
        }
        if len(matches) != 1:
            raise ReplayGuardError(
                "wrong active replay player identity "
                f"({source_identity.get('value')!r}, matches={len(matches)})"
            )
        index = next(iter(matches))
        if index in used:
            raise ReplayGuardError("active replay identity matched more than once")
        used.add(index)
        live_participant = live[index]
        if int(live_participant.get("teamID") or 0) != int(
            participant.get("teamId") or 0
        ):
            raise ReplayGuardError(
                f"wrong active replay team for {source_identity.get('value')!r}"
            )
        expected_champion = (participant.get("champion") or {}).get("asset")
        live_champion = rofl_metadata.champion_identities(
            live_participant.get("championInternalName")
            or live_participant.get("championName")
        ).get("asset")
        if str(expected_champion or "").casefold() != str(
            live_champion or ""
        ).casefold():
            raise ReplayGuardError(
                "wrong active replay champion for "
                f"{source_identity.get('value')!r}: "
                f"{live_champion!r} != {expected_champion!r}"
            )
    return {
        "ok": True,
        "activeGameId": active_game_id,
        "activeBuild": active_builds[0] if active_builds else None,
        "appBuild": app.get("version"),
        "durationMs": active_duration_ms,
        "durationToleranceMs": tolerance_ms,
        "rosterCount": len(used),
        "rosterHash": metadata["rosterHash"],
    }
