#!/usr/bin/env python3
"""
Replay API → canonical rfc461 JSONL (bounded seek + focus positions).

Seeks a paused replay across ``[--start-ms, --end-ms]`` at ``--step-ms``,
captures all 10 champion world positions via the proven focus / player-identity
primitive, and emits ONLY the existing rfc461 JSONL shape with honest unknown
HP / combat / ability semantics (fields omitted + source markers).

This path may seek. It does not decrypt ROFL payloads. Live League control is
only performed when the user explicitly runs this CLI against an open replay.

Examples:
  npm run rofl:replay-jsonl -- \\
    --rofl \"$HOME/Documents/League of Legends/Replays/BR1-3263797356.rofl\" \\
    --out /tmp/replay_api_121_124.jsonl \\
    --start-ms 121000 --end-ms 124000 --step-ms 1000 \\
    --checkpoint-out /tmp/replay_api_121_124.checkpoint.json

  # Crash-safe resume after interruption (strict coverage/roster/schedule check)
  npm run rofl:replay-jsonl -- \\
    --rofl \"$HOME/Documents/League of Legends/Replays/BR1-3263797356.rofl\" \\
    --out /tmp/replay_api_121_124.jsonl \\
    --start-ms 121000 --end-ms 124000 --step-ms 1000 \\
    --resume --checkpoint-out /tmp/replay_api_121_124.checkpoint.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence, TextIO

import rfc461_emit
import rofl_replay_api_probe as probe

DEFAULT_START_MS = 0
DEFAULT_END_MS = 0
DEFAULT_STEP_MS = 1000
DEFAULT_FINAL_SETTLE = 0.08
DEFAULT_IDENTITY_RETRIES = 1
DEFAULT_SEEK_TIMEOUT = 8.0
DEFAULT_SEEK_TIME_TOL = 1e-3
# Liveclient gameData.gameTime is seconds; require correlation to target sample.
DEFAULT_LIVECLIENT_TIME_TOL_SEC = 0.05
DEFAULT_LIVECLIENT_WAIT_TIMEOUT = 8.0
HEALTH_SOURCE = "unavailable_replay_api"
COMBAT_STATS_SOURCE = "unavailable_replay_api"
ABILITY_RANKS_SOURCE = "unavailable_replay_api"
POSITION_COVERAGE = "full_at_sampled_frames"
HP_COVERAGE = "none"
SOURCE = "replay_api_playback"


class ExtractError(RuntimeError):
    """Fatal extraction failure with optional checkpoint payload."""

    def __init__(self, message: str, *, checkpoint: Optional[dict[str, Any]] = None):
        super().__init__(message)
        self.checkpoint = checkpoint or {}


def _ms_to_sec(ms: int) -> float:
    return float(ms) / 1000.0


def _sample_times_ms(start_ms: int, end_ms: int, step_ms: int) -> list[int]:
    if step_ms <= 0:
        raise ExtractError("--step-ms must be > 0")
    if end_ms < start_ms:
        raise ExtractError("--end-ms must be >= --start-ms")
    out: list[int] = []
    t = start_ms
    while t <= end_ms:
        out.append(int(t))
        t += step_ms
    if not out:
        raise ExtractError("empty sample schedule")
    return out


def _items_as_rfc461(items: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not isinstance(items, list):
        return out
    for it in items:
        if isinstance(it, Mapping) and "itemID" in it:
            try:
                iid = int(it["itemID"])
            except (TypeError, ValueError):
                continue
            if iid:
                out.append({"itemID": iid})
        else:
            try:
                iid = int(it)
            except (TypeError, ValueError):
                continue
            if iid:
                out.append({"itemID": iid})
    return out


def _restore_render_bodies(
    original_render: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Full render snapshot + critical subset (selection/camera fields)."""
    critical = {
        k: original_render[k]
        for k in probe.RENDER_RESTORE_FIELDS
        if k in original_render
    }
    if "selectionName" in critical and critical["selectionName"] is None:
        critical["selectionName"] = ""
    return dict(original_render), critical


def _playback_sample(body: Any) -> Optional[dict[str, Any]]:
    if not isinstance(body, dict):
        return None
    return {
        k: body.get(k)
        for k in ("paused", "seeking", "time", "speed")
        if k in body
    }


def _render_sample(body: Any) -> Optional[dict[str, Any]]:
    if not isinstance(body, dict):
        return None
    return {
        k: body.get(k)
        for k in probe.RENDER_RESTORE_FIELDS
        if k in body
    }


def restore_extractor_state(
    transport: probe.Transport,
    *,
    playback_url: str,
    render_url: str,
    original_playback: Mapping[str, Any],
    original_render: Mapping[str, Any],
    timeout: float,
    seek_timeout: float,
    time_tol: float,
    settle_delay: float,
) -> dict[str, Any]:
    """Two-phase restore: seek time while paused, prove, then resume.

    Phase 1 (paused/stable): POST render + ``time`` with ``paused=true``, wait
    until seeking=false at the exact restored time, then GET-prove exact time and
    stable critical render fields. ``cameraPosition`` remains strict when the
    replay started paused; Riot may ignore writes to a running top-mode camera,
    so it is best-effort for an originally running replay.

    Phase 2: restore original ``speed`` and original ``paused``. If the replay
    was originally paused, keep strict final time/render proof. If originally
    unpaused, require paused=false / speed / seeking=false and a monotonic time
    within an elapsed-time upper bound — never demand cameraPosition equality
    after resume (live camera may move).
    """
    originally_paused = bool(original_playback.get("paused", True))
    result: dict[str, Any] = {
        "restoreAttempted": True,
        "restoreSucceeded": False,
        "error": None,
        "originallyPaused": originally_paused,
        "snapshots": {
            "restorePlan": {
                "originallyPaused": originally_paused,
                "phases": [
                    "paused_seek_and_stable_proof",
                    "resume_speed_and_paused_state",
                ],
                "finalExactTime": originally_paused,
                "phase1RequireCameraPosition": originally_paused,
                "finalRequireCameraPosition": originally_paused,
            }
        },
    }
    errors: list[str] = []

    render_body, critical = _restore_render_bodies(original_render)
    render_post = transport("POST", render_url, body=render_body, timeout=timeout)
    critical_post = (
        transport("POST", render_url, body=critical, timeout=timeout) if critical else None
    )
    result["snapshots"]["restoreRender"] = {
        "ok": render_post.get("ok"),
        "status": render_post.get("status"),
        "error": render_post.get("error"),
    }
    if critical_post is not None:
        result["snapshots"]["restoreRenderCritical"] = {
            "ok": critical_post.get("ok"),
            "status": critical_post.get("status"),
            "error": critical_post.get("error"),
            "postedKeys": sorted(critical.keys()),
        }
    if not render_post.get("ok"):
        errors.append(render_post.get("error") or "render restore POST failed")
    if critical_post is not None and not critical_post.get("ok"):
        errors.append(critical_post.get("error") or "render critical restore POST failed")

    # --- Phase 1: restore time while paused (never resume in the same POST) ---
    phase1_body: dict[str, Any] = {"paused": True}
    target_t: Optional[float] = None
    if "time" in original_playback:
        try:
            target_t = float(original_playback["time"])
            phase1_body["time"] = target_t
        except (TypeError, ValueError):
            errors.append("original playback time not comparable for restore")
    phase1_post = transport("POST", playback_url, body=phase1_body, timeout=timeout)
    result["snapshots"]["restorePhase1PlaybackPost"] = {
        "ok": phase1_post.get("ok"),
        "status": phase1_post.get("status"),
        "error": phase1_post.get("error"),
        "postedKeys": sorted(phase1_body.keys()),
        "posted": dict(phase1_body),
    }
    if not phase1_post.get("ok"):
        errors.append(phase1_post.get("error") or "phase1 paused time restore POST failed")

    wait = probe.wait_playback_settled(
        transport,
        playback_url,
        target_time_sec=target_t,
        timeout=timeout,
        poll_interval=0.05,
        time_tol=time_tol,
        seek_timeout=seek_timeout,
    )
    result["snapshots"]["restorePhase1SeekWait"] = {
        "ok": wait.get("ok"),
        "settled": wait.get("settled"),
        "error": wait.get("error"),
        "sample": _playback_sample(wait.get("body")),
    }
    if not wait.get("ok"):
        errors.append(wait.get("error") or "phase1 restore seek wait failed")

    # Seek often resets camera mode/selection — re-apply critical render after settle.
    if critical:
        critical_reapply = transport(
            "POST", render_url, body=critical, timeout=timeout
        )
        result["snapshots"]["restorePhase1RenderReapply"] = {
            "ok": critical_reapply.get("ok"),
            "status": critical_reapply.get("status"),
            "error": critical_reapply.get("error"),
            "postedKeys": sorted(critical.keys()),
        }
        if not critical_reapply.get("ok"):
            errors.append(
                critical_reapply.get("error")
                or "phase1 render critical re-apply after seek failed"
            )
    # Riot can ignore cameraPosition when it is bundled with selection/camera
    # fields. Re-apply it alone after the seek and mode/selection restore.
    if "cameraPosition" in original_render:
        camera_position_post = transport(
            "POST",
            render_url,
            body={"cameraPosition": original_render["cameraPosition"]},
            timeout=timeout,
        )
        result["snapshots"]["restorePhase1CameraPositionReapply"] = {
            "ok": camera_position_post.get("ok"),
            "status": camera_position_post.get("status"),
            "error": camera_position_post.get("error"),
        }
        if not camera_position_post.get("ok"):
            errors.append(
                camera_position_post.get("error")
                or "phase1 cameraPosition re-apply after seek failed"
            )

    probe._settle(settle_delay)  # noqa: SLF001
    phase1_playback_get = transport("GET", playback_url, timeout=timeout)
    phase1_render_get = transport("GET", render_url, timeout=timeout)
    result["snapshots"]["restorePhase1PlaybackGet"] = {
        "ok": phase1_playback_get.get("ok"),
        "sample": _playback_sample(phase1_playback_get.get("body")),
    }
    result["snapshots"]["restorePhase1RenderGet"] = {
        "ok": phase1_render_get.get("ok"),
        "sample": _render_sample(phase1_render_get.get("body")),
    }
    if not phase1_playback_get.get("ok"):
        errors.append(
            phase1_playback_get.get("error") or "phase1 playback restore GET failed"
        )
    if not phase1_render_get.get("ok"):
        errors.append(phase1_render_get.get("error") or "phase1 render restore GET failed")
    if phase1_playback_get.get("ok") and phase1_render_get.get("ok"):
        phase1_errors = probe._verify_restore_readback(  # noqa: SLF001
            original_playback={
                **dict(original_playback),
                "paused": True,
            },
            original_render=original_render,
            playback_body=phase1_playback_get.get("body"),
            render_body=phase1_render_get.get("body"),
            time_tol=time_tol,
            require_exact_time=True,
            include_camera_position=originally_paused,
            restored_time_sec=target_t,
        )
        if phase1_errors:
            errors.extend(f"phase1: {e}" for e in phase1_errors)
        result["snapshots"]["restorePhase1Proof"] = {
            "ok": not phase1_errors,
            "errors": list(phase1_errors),
            "requireExactTime": True,
            "includeCameraPosition": originally_paused,
        }

    # --- Phase 2: restore speed + original paused state ---
    phase2_body: dict[str, Any] = {}
    if "paused" in original_playback:
        phase2_body["paused"] = original_playback["paused"]
    else:
        phase2_body["paused"] = originally_paused
    if "speed" in original_playback:
        phase2_body["speed"] = original_playback["speed"]
    # Never include time here — that would re-seek while possibly unpausing.
    assert "time" not in phase2_body
    # Arm before the POST: Riot may resume playback before the HTTP response
    # returns, so response latency is part of the legitimate clock advance.
    resume_mono: Optional[float] = (
        time.monotonic() if not originally_paused else None
    )
    phase2_post = transport(
        "POST", playback_url, body=phase2_body or {"paused": originally_paused}, timeout=timeout
    )
    result["snapshots"]["restorePhase2PlaybackPost"] = {
        "ok": phase2_post.get("ok"),
        "status": phase2_post.get("status"),
        "error": phase2_post.get("error"),
        "postedKeys": sorted(phase2_body.keys()),
        "posted": dict(phase2_body),
        "resumeMonoArmed": resume_mono is not None,
    }
    if not phase2_post.get("ok"):
        errors.append(phase2_post.get("error") or "phase2 resume restore POST failed")

    probe._settle(settle_delay)  # noqa: SLF001
    phase2_playback_get = transport("GET", playback_url, timeout=timeout)
    phase2_render_get = transport("GET", render_url, timeout=timeout)
    result["snapshots"]["restorePhase2PlaybackGet"] = {
        "ok": phase2_playback_get.get("ok"),
        "sample": _playback_sample(phase2_playback_get.get("body")),
    }
    result["snapshots"]["restorePhase2RenderGet"] = {
        "ok": phase2_render_get.get("ok"),
        "sample": _render_sample(phase2_render_get.get("body")),
    }
    # Keep legacy snapshot names pointing at the final proof for callers/checkpoints.
    result["snapshots"]["restorePlaybackGet"] = result["snapshots"]["restorePhase2PlaybackGet"]
    result["snapshots"]["restoreRenderGet"] = result["snapshots"]["restorePhase2RenderGet"]

    if not phase2_playback_get.get("ok"):
        errors.append(
            phase2_playback_get.get("error") or "phase2 playback restore GET failed"
        )
    if not phase2_render_get.get("ok"):
        errors.append(phase2_render_get.get("error") or "phase2 render restore GET failed")
    if phase2_playback_get.get("ok") and phase2_render_get.get("ok"):
        phase2_errors = probe._verify_restore_readback(  # noqa: SLF001
            original_playback=original_playback,
            original_render=original_render,
            playback_body=phase2_playback_get.get("body"),
            render_body=phase2_render_get.get("body"),
            time_tol=time_tol,
            require_exact_time=originally_paused,
            include_camera_position=originally_paused,
            resume_mono=resume_mono,
            restored_time_sec=target_t,
        )
        if phase2_errors:
            label = "phase2-paused" if originally_paused else "phase2-resumed"
            errors.extend(f"{label}: {e}" for e in phase2_errors)
        result["snapshots"]["restorePhase2Proof"] = {
            "ok": not phase2_errors,
            "errors": list(phase2_errors),
            "requireExactTime": originally_paused,
            "includeCameraPosition": originally_paused,
            "resumeMono": resume_mono,
        }

    result["restoreSucceeded"] = not errors
    if errors:
        result["error"] = "; ".join(errors)
    return result


def capture_frame_positions(
    transport: probe.Transport,
    *,
    base_url: str,
    roster: Sequence[Mapping[str, Any]],
    timeout: float,
    settle_delay: float,
    final_settle: float,
    identity_retries: int,
    require_distinct: bool = True,
    previous_selection_name: Any = None,
) -> dict[str, Any]:
    """Capture one frame of focus positions for the given roster."""
    render_url = f"{base_url.rstrip('/')}/replay/render"
    participants: list[dict[str, Any]] = []
    positions: list[tuple[float, float]] = []
    prev = previous_selection_name

    for row in roster:
        if not row.get("selectionKeys"):
            return {
                "ok": False,
                "error": f"no valid selection keys for participant {row.get('participantID')}",
                "participants": participants,
                "previousSelectionName": prev,
            }
        steps, classification, used_key = probe.focus_select_roster_member(
            transport,
            render_url,
            row,
            timeout=timeout,
            settle_delay=settle_delay,
            previous_selection_name=prev,
            final_settle=final_settle,
            identity_retries=identity_retries,
        )
        read_body = (
            steps["readback"].get("body") if steps.get("readback", {}).get("ok") else {}
        )
        if not isinstance(read_body, dict):
            read_body = {}
        if not classification.get("coordinateProven"):
            return {
                "ok": False,
                "error": (
                    f"focus coordinate unsupported for "
                    f"{row.get('playerName') or row.get('championName')}: "
                    f"outcome={classification.get('outcome')} "
                    f"stale={classification.get('staleRetained')} "
                    f"key={used_key!r} "
                    f"canonical={read_body.get('selectionName')!r}"
                ),
                "participants": participants,
                "previousSelectionName": prev,
                "classification": classification,
            }
        pos = read_body["cameraPosition"]
        xz = probe._xz_position(pos)  # noqa: SLF001
        positions.append((xz["x"], xz["z"]))
        prev = read_body.get("selectionName")
        participants.append(
            {
                **dict(row),
                "selectionKeyUsed": used_key,
                "position": xz,
                "positionSource": probe.POSITION_SOURCE_FOCUS,
                "selectionNameCanonical": read_body.get("selectionName"),
            }
        )

    if require_distinct and len(positions) >= 2:
        unique = {(round(x, 3), round(z, 3)) for x, z in positions}
        # Multiple champions can legitimately overlap (including dead players
        # at a fountain). Only reject the unsupported/stale-render signature
        # where every independently identity-proven selection returns the same
        # camera coordinate.
        if len(unique) == 1:
            return {
                "ok": False,
                "error": (
                    f"all {len(positions)} identity-proven selections returned "
                    "one coordinate — likely stale render state"
                ),
                "participants": participants,
                "previousSelectionName": prev,
            }

    missing = [r for r in roster if int(r["participantID"]) not in {
        int(p["participantID"]) for p in participants
    }]
    if missing:
        return {
            "ok": False,
            "error": f"missing participants after capture: {[m.get('participantID') for m in missing]}",
            "participants": participants,
            "previousSelectionName": prev,
        }

    return {
        "ok": True,
        "error": None,
        "participants": participants,
        "previousSelectionName": prev,
    }


def participants_to_rfc461_rows(
    captured: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for p in captured:
        role = str(p.get("role") or "NONE")
        rows.append(
            rfc461_emit.participant_row(
                participant_id=int(p["participantID"]),
                team_id=int(p["teamID"]),
                champion_name=str(p.get("championName") or "Unknown"),
                player_name=str(p.get("playerName") or p.get("summonerName") or ""),
                position=dict(p["position"]),
                position_source=probe.POSITION_SOURCE_FOCUS,
                alive=bool(p.get("alive", True)),
                level=int(p.get("level") or 1),
                health_known=False,
                health_source=HEALTH_SOURCE,
                combat_stats_source=COMBAT_STATS_SOURCE,
                ability_ranks_source=ABILITY_RANKS_SOURCE,
                items=_items_as_rfc461(p.get("items")),
                ability_levels=(0, 0, 0, 0),
                extra={"role": role},
            )
        )
    return rows


def game_info_participants(roster: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for p in roster:
        out.append(
            {
                "participantID": int(p["participantID"]),
                "teamID": int(p["teamID"]),
                "championName": p.get("championName") or "Unknown",
                "playerName": p.get("playerName") or p.get("summonerName") or "",
                "summonerName": p.get("summonerName") or p.get("playerName") or "",
                "role": p.get("role") or "NONE",
            }
        )
    return out


def roster_identity_key(row: Mapping[str, Any]) -> str:
    """Stable summoner identity key (casefold, #tag stripped)."""
    for cand in (
        row.get("expectedSelectionIdentity"),
        row.get("playerName"),
        row.get("summonerName"),
    ):
        key = probe._player_identity_key(cand)  # noqa: SLF001
        if key:
            return key
    return ""


def assign_stable_participant_ids(
    live_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """One-time identity→participantID roster (static champs/teams/names only)."""
    rows = [dict(r) for r in live_rows]
    if len(rows) != 10:
        raise ExtractError(f"expected 10 liveclient participants, got {len(rows)}")
    seen: dict[str, int] = {}
    for row in rows:
        key = roster_identity_key(row)
        if not key:
            raise ExtractError(
                f"roster row missing summoner identity: {row.get('championName')!r}"
            )
        if key in seen:
            raise ExtractError(f"duplicate summoner identity in initial roster: {key!r}")
        seen[key] = 1
        if int(row.get("participantID") or 0) <= 0:
            row["participantID"] = 0
    rows.sort(key=lambda r: (int(r["teamID"]), int(r.get("participantID") or 0), roster_identity_key(r)))
    for i, row in enumerate(rows):
        row["participantID"] = i + 1
        # Snapshot identity fields used for stable mapping; dynamics refreshed per frame.
        row["_identityKey"] = roster_identity_key(row)
    return rows


def merge_dynamic_roster_state(
    stable_roster: Sequence[Mapping[str, Any]],
    live_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Merge per-frame level/items/alive onto the stable identity→pid roster.

    Fails if any stable identity is missing or duplicated in the live snapshot.
    Does not infer dynamics from the initial roster.
    """
    by_identity: dict[str, list[Mapping[str, Any]]] = {}
    for live in live_rows:
        key = roster_identity_key(live)
        if not key:
            raise ExtractError(
                f"liveclient row missing summoner identity at frame: "
                f"{live.get('championName')!r}"
            )
        by_identity.setdefault(key, []).append(live)

    merged: list[dict[str, Any]] = []
    for base in stable_roster:
        key = str(base.get("_identityKey") or roster_identity_key(base))
        matches = by_identity.get(key) or []
        if not matches:
            raise ExtractError(
                f"summoner identity missing after seek: {key!r} "
                f"(participantID={base.get('participantID')})"
            )
        if len(matches) > 1:
            raise ExtractError(
                f"duplicate summoner identity after seek: {key!r} "
                f"({len(matches)} rows)"
            )
        live = matches[0]
        row = dict(base)
        # Dynamic fields only from the post-seek liveclient snapshot.
        if "level" in live and live.get("level") is not None:
            row["level"] = live.get("level")
        else:
            raise ExtractError(f"level missing for identity {key!r} after seek")
        row["items"] = list(live.get("items") or [])
        if "alive" not in live:
            raise ExtractError(f"alive missing for identity {key!r} after seek")
        row["alive"] = bool(live.get("alive"))
        # Keep selection keys current (summoner may still be primary).
        row["selectionKeys"] = probe.selection_keys_for_roster_row(row)
        row["summonerName"] = live.get("summonerName") or row.get("summonerName")
        row["playerName"] = live.get("playerName") or row.get("playerName")
        if live.get("role"):
            row["role"] = live.get("role")
        if "liveclientPosition" in live:
            row["liveclientPosition"] = live.get("liveclientPosition")
        merged.append(row)

    if len(merged) != 10:
        raise ExtractError(f"merged roster size {len(merged)} != 10")
    return merged


def fetch_liveclient_roster(
    transport: probe.Transport,
    base_url: str,
    *,
    timeout: float,
) -> list[dict[str, Any]]:
    """One-shot liveclient roster (no time correlation). Prefer wait_* for samples."""
    base = base_url.rstrip("/")
    pl = transport("GET", f"{base}/liveclientdata/playerlist", timeout=timeout)
    ag = transport("GET", f"{base}/liveclientdata/allgamedata", timeout=timeout)
    if not pl.get("ok"):
        raise ExtractError(pl.get("error") or "playerlist GET failed")
    return probe.build_roster_from_liveclient(pl.get("body"), ag.get("body"))


def _allgamedata_game_time_sec(allgamedata_body: Any) -> Optional[float]:
    if not isinstance(allgamedata_body, Mapping):
        return None
    game_data = allgamedata_body.get("gameData")
    if not isinstance(game_data, Mapping):
        return None
    try:
        return float(game_data.get("gameTime"))
    except (TypeError, ValueError):
        return None


def _roster_identities_complete(
    rows: Sequence[Mapping[str, Any]], *, expect_n: int = 10
) -> tuple[bool, str]:
    if len(rows) != expect_n:
        return False, f"expected {expect_n} players, got {len(rows)}"
    seen: set[str] = set()
    for row in rows:
        key = roster_identity_key(row)
        if not key:
            return False, f"incomplete identity for {row.get('championName')!r}"
        if key in seen:
            return False, f"duplicate identity {key!r}"
        seen.add(key)
        if row.get("level") is None:
            return False, f"level missing for {key!r}"
        if "alive" not in row:
            return False, f"alive missing for {key!r}"
    return True, ""


def wait_liveclient_roster_at_time(
    transport: probe.Transport,
    base_url: str,
    *,
    target_ms: int,
    timeout: float,
    poll_interval: float = 0.05,
    time_tol_sec: float = DEFAULT_LIVECLIENT_TIME_TOL_SEC,
    wait_timeout: float = DEFAULT_LIVECLIENT_WAIT_TIMEOUT,
    expect_n: int = 10,
) -> dict[str, Any]:
    """Poll allgamedata/playerlist until gameTime matches target and roster is complete.

    Riot liveclient ``gameData.gameTime`` is seconds. Refuses to merge until the
    snapshot is correlated to ``target_ms`` within ``time_tol_sec``.
    """
    base = base_url.rstrip("/")
    target_sec = _ms_to_sec(target_ms)
    deadline = time.monotonic() + max(0.05, float(wait_timeout))
    attempts: list[dict[str, Any]] = []
    last_observed: Optional[float] = None

    while time.monotonic() < deadline:
        ag = transport("GET", f"{base}/liveclientdata/allgamedata", timeout=timeout)
        pl = transport("GET", f"{base}/liveclientdata/playerlist", timeout=timeout)
        observed = _allgamedata_game_time_sec(ag.get("body") if ag.get("ok") else None)
        last_observed = observed
        attempt: dict[str, Any] = {
            "observedGameTimeSec": observed,
            "targetMs": target_ms,
            "targetSec": target_sec,
            "allgamedataOk": bool(ag.get("ok")),
            "playerlistOk": bool(pl.get("ok")),
        }
        if not ag.get("ok"):
            attempt["error"] = ag.get("error") or "allgamedata GET failed"
            attempts.append(attempt)
            probe._settle(poll_interval)  # noqa: SLF001
            continue
        if not pl.get("ok"):
            attempt["error"] = pl.get("error") or "playerlist GET failed"
            attempts.append(attempt)
            probe._settle(poll_interval)  # noqa: SLF001
            continue
        if observed is None:
            attempt["error"] = "gameData.gameTime missing"
            attempts.append(attempt)
            probe._settle(poll_interval)  # noqa: SLF001
            continue

        time_matched = abs(float(observed) - float(target_sec)) <= float(time_tol_sec)
        attempt["timeMatched"] = time_matched
        attempt["deltaSec"] = abs(float(observed) - float(target_sec))
        if not time_matched:
            attempt["error"] = (
                f"liveclient gameTime {observed}s != target {target_sec}s "
                f"(tol={time_tol_sec}s)"
            )
            attempts.append(attempt)
            probe._settle(poll_interval)  # noqa: SLF001
            continue

        roster = probe.build_roster_from_liveclient(pl.get("body"), ag.get("body"))
        complete, complete_err = _roster_identities_complete(roster, expect_n=expect_n)
        attempt["rosterCount"] = len(roster)
        attempt["identitiesComplete"] = complete
        if not complete:
            attempt["error"] = complete_err
            attempts.append(attempt)
            probe._settle(poll_interval)  # noqa: SLF001
            continue

        attempts.append(attempt)
        return {
            "ok": True,
            "roster": roster,
            "observedGameTimeSec": observed,
            "matchedGameTimeSec": observed,
            "targetMs": target_ms,
            "targetSec": target_sec,
            "timeTolSec": time_tol_sec,
            "attempts": len(attempts),
            "evidence": {
                "observedGameTimeSec": observed,
                "matchedGameTimeSec": observed,
                "targetMs": target_ms,
                "deltaSec": attempt["deltaSec"],
                "pollAttempts": len(attempts),
            },
            "error": None,
        }

    return {
        "ok": False,
        "roster": [],
        "observedGameTimeSec": last_observed,
        "matchedGameTimeSec": None,
        "targetMs": target_ms,
        "targetSec": target_sec,
        "timeTolSec": time_tol_sec,
        "attempts": len(attempts),
        "evidence": {
            "observedGameTimeSec": last_observed,
            "matchedGameTimeSec": None,
            "targetMs": target_ms,
            "pollAttempts": len(attempts),
            "lastAttempts": attempts[-3:],
        },
        "error": (
            f"liveclient did not reach gameTime≈{target_sec}s "
            f"(last observed={last_observed!r}) within {wait_timeout}s"
        ),
    }


def ensure_camera_mode_focus(
    transport: probe.Transport,
    render_url: str,
    *,
    timeout: float,
    settle_delay: float,
) -> dict[str, Any]:
    """POST cameraMode=focus and GET-prove it (seek may reset render state)."""
    post = probe.set_camera_mode_focus(
        transport, render_url, timeout=timeout, settle_delay=settle_delay
    )
    if not post.get("ok"):
        return {
            "ok": False,
            "error": post.get("error") or "cameraMode=focus POST failed",
            "post": post,
        }
    got = transport("GET", render_url, timeout=timeout)
    body = got.get("body") if got.get("ok") and isinstance(got.get("body"), dict) else {}
    mode = body.get("cameraMode")
    if mode != probe.FOCUS_CAMERA_MODE:
        return {
            "ok": False,
            "error": (
                f"cameraMode not focus after re-assert (got {mode!r}); "
                "seek may have reset render state"
            ),
            "post": post,
            "get": got,
        }
    return {"ok": True, "error": None, "post": post, "get": got}


@dataclass
class PartialRfc461Output:
    """Validated partial/complete replay-api rfc461 JSONL on disk."""

    coverage: dict[str, Any]
    game_info: dict[str, Any]
    completed_times_ms: list[int] = field(default_factory=list)
    stats_rows: list[dict[str, Any]] = field(default_factory=list)


def durable_append_jsonl_row(fh: TextIO, row: Mapping[str, Any]) -> None:
    """Write one JSONL row and fsync so SIGINT keeps completed lines parseable."""
    fh.write(json.dumps(dict(row), ensure_ascii=False) + "\n")
    fh.flush()
    try:
        os.fsync(fh.fileno())
    except OSError:
        # Some test/memory filesystems may not support fsync; flush still landed.
        pass


def write_checkpoint_file(path: Optional[Path], payload: Mapping[str, Any]) -> None:
    if path is None:
        return
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(dict(payload), indent=2, default=str)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        fh.write(text)
        fh.flush()
        try:
            os.fsync(fh.fileno())
        except OSError:
            pass
    tmp.replace(path)


def _artifact_paths_equal(a: Any, b: Any) -> bool:
    sa = str(a or "")
    sb = str(b or "")
    if sa == sb:
        return True
    try:
        return Path(sa).expanduser().resolve() == Path(sb).expanduser().resolve()
    except OSError:
        return False


def _roster_identity_contract(row: Mapping[str, Any]) -> tuple[str, int, str]:
    return (
        roster_identity_key(row),
        int(row.get("teamID") or 0),
        str(row.get("championName") or ""),
    )


def read_partial_rfc461_jsonl(path: Path) -> PartialRfc461Output:
    """Parse existing output strictly; reject truncated/malformed/mixed schema."""
    if not path.is_file():
        raise ExtractError(f"--resume requires existing output: {path}")
    raw = path.read_bytes()
    if not raw:
        raise ExtractError(f"partial output is empty: {path}")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ExtractError(f"partial output is not valid UTF-8: {exc}") from exc
    if not text.endswith("\n"):
        raise ExtractError(
            "truncated final line in partial output (missing trailing newline)"
        )

    coverage: Optional[dict[str, Any]] = None
    game_info: Optional[dict[str, Any]] = None
    stats_rows: list[dict[str, Any]] = []
    completed: list[int] = []
    line_no = 0
    for line in text.splitlines():
        line_no += 1
        if not line.strip():
            raise ExtractError(f"blank line at {path}:{line_no}")
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ExtractError(
                f"malformed JSON at {path}:{line_no}: {exc}"
            ) from exc
        if not isinstance(row, dict):
            raise ExtractError(f"non-object JSONL row at {path}:{line_no}")
        schema = row.get("rfc461Schema")
        if line_no == 1:
            if schema != "rofl_coverage":
                raise ExtractError(
                    f"expected first row rfc461Schema=rofl_coverage, got {schema!r}"
                )
            coverage = row
            continue
        if line_no == 2:
            if schema != "game_info":
                raise ExtractError(
                    f"expected second row rfc461Schema=game_info, got {schema!r}"
                )
            game_info = row
            continue
        if schema == "rofl_coverage" or schema == "game_info":
            raise ExtractError(
                f"duplicate header schema {schema!r} at {path}:{line_no}"
            )
        if schema != "stats_update":
            raise ExtractError(
                f"mixed/unsupported schema {schema!r} at {path}:{line_no} "
                "(resume accepts only rofl_coverage, game_info, stats_update)"
            )
        try:
            t_ms = int(row["gameTime"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ExtractError(
                f"stats_update missing integer gameTime at {path}:{line_no}"
            ) from exc
        stats_rows.append(row)
        completed.append(t_ms)

    if coverage is None or game_info is None:
        raise ExtractError(
            "partial output missing required rofl_coverage and game_info headers"
        )
    return PartialRfc461Output(
        coverage=coverage,
        game_info=game_info,
        completed_times_ms=completed,
        stats_rows=stats_rows,
    )


def validate_resume_contract(
    partial: PartialRfc461Output,
    *,
    sample_ms: Sequence[int],
    rofl_path: Path,
    rofl_version: Any,
    app_version: Any,
    start_ms: int,
    end_ms: int,
    step_ms: int,
    game_id: int,
) -> list[int]:
    """Strict coverage/roster/schedule checks; return remaining sample times."""
    cov = partial.coverage
    if cov.get("source") != SOURCE:
        raise ExtractError(
            f"coverage source mismatch: {cov.get('source')!r} != {SOURCE!r}"
        )
    prov = cov.get("provenance")
    if not isinstance(prov, Mapping):
        raise ExtractError("coverage missing provenance object")
    if prov.get("source") != SOURCE:
        raise ExtractError(
            f"provenance.source mismatch: {prov.get('source')!r} != {SOURCE!r}"
        )
    if prov.get("positionCoverage") != POSITION_COVERAGE:
        raise ExtractError(
            "provenance.positionCoverage mismatch: "
            f"{prov.get('positionCoverage')!r} != {POSITION_COVERAGE!r}"
        )
    if prov.get("hpCoverage") != HP_COVERAGE:
        raise ExtractError(
            f"provenance.hpCoverage mismatch: {prov.get('hpCoverage')!r} != {HP_COVERAGE!r}"
        )
    if not _artifact_paths_equal(prov.get("artifact"), rofl_path):
        raise ExtractError(
            "provenance.artifact mismatch: "
            f"{prov.get('artifact')!r} != {str(rofl_path)!r}"
        )
    if cov.get("roflGameVersion") != rofl_version:
        raise ExtractError(
            "coverage roflGameVersion mismatch: "
            f"{cov.get('roflGameVersion')!r} != {rofl_version!r}"
        )
    if cov.get("appBuildVersion") != app_version:
        raise ExtractError(
            "coverage appBuildVersion mismatch: "
            f"{cov.get('appBuildVersion')!r} != {app_version!r}"
        )
    for key, want in (("startMs", start_ms), ("endMs", end_ms), ("stepMs", step_ms)):
        got = cov.get(key)
        try:
            got_i = int(got)
        except (TypeError, ValueError):
            raise ExtractError(f"coverage {key} missing/invalid: {got!r}") from None
        if got_i != int(want):
            raise ExtractError(f"coverage {key} mismatch: {got_i} != {want}")

    info = partial.game_info
    try:
        info_gid = int(info.get("gameID"))
    except (TypeError, ValueError):
        raise ExtractError("game_info.gameID missing/invalid") from None
    if info_gid != int(game_id or 0):
        raise ExtractError(
            f"game_info.gameID mismatch: {info_gid} != {int(game_id or 0)}"
        )
    try:
        interval = int(info.get("statsUpdateInterval"))
    except (TypeError, ValueError):
        raise ExtractError("game_info.statsUpdateInterval missing/invalid") from None
    if interval != int(step_ms):
        raise ExtractError(
            f"game_info.statsUpdateInterval mismatch: {interval} != {step_ms}"
        )
    parts = info.get("participants")
    if not isinstance(parts, list) or len(parts) != 10:
        raise ExtractError("game_info must list exactly 10 participants")
    seen_ids: set[int] = set()
    for p in parts:
        if not isinstance(p, Mapping):
            raise ExtractError("game_info participant is not an object")
        ident, team, champ = _roster_identity_contract(p)
        if not ident:
            raise ExtractError("game_info participant missing summoner identity")
        if team not in (100, 200):
            raise ExtractError(f"game_info participant teamID invalid: {team}")
        if not champ:
            raise ExtractError("game_info participant missing championName")
        try:
            pid = int(p.get("participantID"))
        except (TypeError, ValueError):
            raise ExtractError("game_info participantID missing/invalid") from None
        if pid in seen_ids:
            raise ExtractError(f"duplicate participantID in game_info: {pid}")
        seen_ids.add(pid)

    schedule = [int(t) for t in sample_ms]
    completed = list(partial.completed_times_ms)
    if len(completed) > len(schedule):
        raise ExtractError(
            f"more completed stats rows ({len(completed)}) than schedule ({len(schedule)})"
        )
    seen_times: set[int] = set()
    for i, t_ms in enumerate(completed):
        if t_ms in seen_times:
            raise ExtractError(f"duplicate stats_update gameTime: {t_ms}")
        seen_times.add(t_ms)
        if t_ms not in schedule:
            raise ExtractError(f"out-of-schedule stats_update gameTime: {t_ms}")
        if t_ms != schedule[i]:
            # Contiguous completed prefix only — holes / reordered times rejected.
            raise ExtractError(
                "completed stats times are not a contiguous schedule prefix: "
                f"index {i} has {t_ms}, expected {schedule[i]} "
                f"(completed={completed!r})"
            )
    return schedule[len(completed) :]


def stable_roster_from_game_info(
    game_info_participants: Sequence[Mapping[str, Any]],
    live_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Rebuild stable roster from game_info pids; verify live identity/team/champ."""
    by_identity: dict[str, Mapping[str, Any]] = {}
    for live in live_rows:
        key = roster_identity_key(live)
        if not key:
            raise ExtractError(
                f"liveclient row missing summoner identity: {live.get('championName')!r}"
            )
        if key in by_identity:
            raise ExtractError(f"duplicate liveclient identity: {key!r}")
        by_identity[key] = live

    stable: list[dict[str, Any]] = []
    for gi in game_info_participants:
        key, team, champ = _roster_identity_contract(gi)
        live = by_identity.get(key)
        if live is None:
            raise ExtractError(
                f"resume roster identity missing in liveclient: {key!r}"
            )
        live_team = int(live.get("teamID") or 0)
        live_champ = str(live.get("championName") or "")
        if live_team != team:
            raise ExtractError(
                f"resume roster team mismatch for {key!r}: live={live_team} file={team}"
            )
        if live_champ != champ:
            raise ExtractError(
                f"resume roster champion mismatch for {key!r}: "
                f"live={live_champ!r} file={champ!r}"
            )
        row = dict(live)
        row["participantID"] = int(gi["participantID"])
        row["teamID"] = team
        row["championName"] = champ
        row["playerName"] = gi.get("playerName") or row.get("playerName")
        row["summonerName"] = gi.get("summonerName") or row.get("summonerName")
        row["role"] = gi.get("role") or row.get("role") or "NONE"
        row["_identityKey"] = key
        row["selectionKeys"] = probe.selection_keys_for_roster_row(row)
        stable.append(row)
    if len(stable) != 10:
        raise ExtractError(f"resume stable roster size {len(stable)} != 10")
    return stable


def _progress_fields(
    *,
    sample_ms: Sequence[int],
    completed_times_ms: Sequence[int],
    out_path: Path,
) -> dict[str, Any]:
    completed = list(completed_times_ms)
    remaining = [t for t in sample_ms if t not in set(completed)]
    # Prefer schedule-prefix remaining when contiguous.
    if completed and list(sample_ms[: len(completed)]) == list(completed):
        remaining = list(sample_ms[len(completed) :])
    return {
        "completedCount": len(completed),
        "lastCompletedMs": completed[-1] if completed else None,
        "nextSampleMs": remaining[0] if remaining else None,
        "remainingSampleTimesMs": remaining,
        "out": str(out_path),
    }


def extract_replay_api_jsonl(
    transport: probe.Transport,
    *,
    base_url: str,
    rofl_path: Path,
    app_path: Path,
    out_path: Path,
    start_ms: int,
    end_ms: int,
    step_ms: int,
    allow_build_mismatch: bool = False,
    timeout: float = probe.DEFAULT_TIMEOUT,
    settle_delay: float = probe.DEFAULT_SETTLE_DELAY,
    final_settle: float = DEFAULT_FINAL_SETTLE,
    identity_retries: int = DEFAULT_IDENTITY_RETRIES,
    seek_timeout: float = DEFAULT_SEEK_TIMEOUT,
    seek_time_tol: float = DEFAULT_SEEK_TIME_TOL,
    liveclient_time_tol_sec: float = DEFAULT_LIVECLIENT_TIME_TOL_SEC,
    liveclient_wait_timeout: float = DEFAULT_LIVECLIENT_WAIT_TIMEOUT,
    game_id: int = 0,
    resume: bool = False,
    checkpoint_out: Optional[Path] = None,
) -> dict[str, Any]:
    """Seek+capture bounded range → durable rfc461 JSONL. Always attempts restore."""
    status: dict[str, Any] = {
        "ok": False,
        "out": str(out_path),
        "framesCaptured": 0,
        "sampleTimesMs": [],
        "restoreAttempted": False,
        "restoreSucceeded": False,
        "error": None,
        "checkpoint": None,
        "buildMatch": None,
        "resumed": bool(resume),
        "completedCount": 0,
        "lastCompletedMs": None,
        "nextSampleMs": None,
    }
    if not probe.is_loopback_url(base_url):
        raise ExtractError(f"refusing non-loopback Replay API URL: {base_url}")

    rofl = probe.read_rofl_build(rofl_path)
    app = probe.read_app_build(app_path)
    match = probe.builds_match(str(rofl.get("version") or ""), str(app.get("version") or ""))
    status["buildMatch"] = {
        "rofl": rofl.get("version"),
        "app": app.get("version"),
        "exact": match,
    }
    if not match and not allow_build_mismatch:
        raise ExtractError(
            "client/replay build mismatch "
            f"(rofl={rofl.get('version')!r}, app={app.get('version')!r}); "
            "pass --allow-build-mismatch to override",
            checkpoint=status,
        )

    requested_end_ms = int(end_ms)
    rofl_game_length_ms: Optional[int] = None
    try:
        parsed_length = int(rofl.get("gameLengthMs"))
        if parsed_length > 0:
            rofl_game_length_ms = parsed_length
    except (TypeError, ValueError):
        rofl_game_length_ms = None
    schedule_end_ms = (
        min(requested_end_ms, rofl_game_length_ms)
        if rofl_game_length_ms is not None
        else requested_end_ms
    )
    sample_ms = _sample_times_ms(start_ms, schedule_end_ms, step_ms)
    status["sampleTimesMs"] = sample_ms
    status["requestedEndMs"] = requested_end_ms
    status["effectiveEndMs"] = sample_ms[-1]
    status["roflGameLengthMs"] = rofl_game_length_ms
    gid = int(game_id or 0)

    completed_times: list[int] = []
    remaining_ms: list[int] = list(sample_ms)
    partial: Optional[PartialRfc461Output] = None

    if resume:
        partial = read_partial_rfc461_jsonl(out_path)
        remaining_ms = validate_resume_contract(
            partial,
            sample_ms=sample_ms,
            rofl_path=rofl_path,
            rofl_version=rofl.get("version"),
            app_version=app.get("version"),
            start_ms=start_ms,
            end_ms=end_ms,
            step_ms=step_ms,
            game_id=gid,
        )
        completed_times = list(partial.completed_times_ms)
        status["framesCaptured"] = len(completed_times)
        status.update(_progress_fields(
            sample_ms=sample_ms,
            completed_times_ms=completed_times,
            out_path=out_path,
        ))
        write_checkpoint_file(checkpoint_out, {"ok": False, **status})
        if not remaining_ms:
            status["ok"] = True
            status["noop"] = True
            status["restoreAttempted"] = False
            status["restoreSucceeded"] = True
            write_checkpoint_file(checkpoint_out, {"ok": True, **status})
            return status
    else:
        status.update(_progress_fields(
            sample_ms=sample_ms,
            completed_times_ms=completed_times,
            out_path=out_path,
        ))

    base = base_url.rstrip("/")
    playback_url = f"{base}/replay/playback"
    render_url = f"{base}/replay/render"

    snap_playback = transport("GET", playback_url, timeout=timeout)
    snap_render = transport("GET", render_url, timeout=timeout)
    if not snap_playback.get("ok") or not snap_render.get("ok"):
        raise ExtractError(
            "failed to snapshot playback/render before extraction",
            checkpoint=status,
        )
    original_playback = dict(snap_playback.get("body") or {})
    original_render = dict(snap_render.get("body") or {})

    pending_error: Optional[BaseException] = None
    out_fh: Optional[TextIO] = None

    def _sync_progress() -> None:
        status["framesCaptured"] = len(completed_times)
        status.update(
            _progress_fields(
                sample_ms=sample_ms,
                completed_times_ms=completed_times,
                out_path=out_path,
            )
        )
        # Expose restore fields when known so mid-run checkpoints stay honest.
        write_checkpoint_file(
            checkpoint_out,
            {
                "ok": False,
                **status,
            },
        )

    try:
        # Pause once up front; seeks keep paused.
        pause = transport("POST", playback_url, body={"paused": True}, timeout=timeout)
        if not pause.get("ok"):
            raise ExtractError(pause.get("error") or "initial pause failed", checkpoint=status)

        pl = transport("GET", f"{base}/liveclientdata/playerlist", timeout=timeout)
        ag = transport("GET", f"{base}/liveclientdata/allgamedata", timeout=timeout)
        if not pl.get("ok"):
            raise ExtractError(pl.get("error") or "playerlist GET failed", checkpoint=status)
        initial_live = probe.build_roster_from_liveclient(pl.get("body"), ag.get("body"))

        if resume:
            assert partial is not None
            stable_roster = stable_roster_from_game_info(
                partial.game_info["participants"], initial_live
            )
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_fh = out_path.open("a", encoding="utf-8")
        else:
            stable_roster = assign_stable_participant_ids(initial_live)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_fh = out_path.open("w", encoding="utf-8")
            provenance = rfc461_emit.provenance_record(
                source=SOURCE,
                source_kind="replay_api_playback",
                position_coverage=POSITION_COVERAGE,
                hp_coverage=HP_COVERAGE,
                roster_mapping="liveclient_playerlist_participantID",
                notes=(
                    "Positions from Replay API focus selection at sampled frames. "
                    "Level/items/alive refreshed from liveclient after each seek. "
                    "HP/combat/ability ranks unavailable from Replay API — omitted "
                    "with unavailable_replay_api sources (not dead/full/fake)."
                ),
                artifact=str(rofl_path),
            )
            durable_append_jsonl_row(
                out_fh,
                rfc461_emit.coverage_line(
                    source=SOURCE,
                    game_id=gid,
                    decoded=[
                        "positions_focus_selection",
                        "alive_level_items_liveclient_per_frame",
                    ],
                    missing=["health", "healthMax", "combatStats", "abilityRanks"],
                    provenance=provenance,
                    extra={
                        "roflGameVersion": rofl.get("version"),
                        "appBuildVersion": app.get("version"),
                        "startMs": start_ms,
                        "endMs": end_ms,
                        "effectiveEndMs": sample_ms[-1],
                        "roflGameLengthMs": rofl_game_length_ms,
                        "stepMs": step_ms,
                    },
                ),
            )
            durable_append_jsonl_row(
                out_fh,
                rfc461_emit.game_info_line(
                    game_id=gid,
                    participants=game_info_participants(stable_roster),
                    game_version=str(rofl.get("version") or ""),
                    stats_update_interval_ms=step_ms,
                ),
            )
            _sync_progress()

        prev_sel = original_render.get("selectionName")
        for t_ms in remaining_ms:
            target_sec = _ms_to_sec(t_ms)
            seek = probe.seek_to_time(
                transport,
                playback_url,
                target_sec,
                timeout=timeout,
                poll_interval=0.05,
                time_tol=seek_time_tol,
                seek_timeout=seek_timeout,
                pause_first=False,
            )
            if not seek.get("ok"):
                raise ExtractError(
                    f"seek to {t_ms}ms failed: {seek.get('error')}",
                    checkpoint={
                        **status,
                        "failedAtMs": t_ms,
                        "framesCaptured": status["framesCaptured"],
                        "seek": seek.get("steps"),
                    },
                )

            # Seek may reset render — re-assert and GET-verify focus before select.
            focus = ensure_camera_mode_focus(
                transport,
                render_url,
                timeout=timeout,
                settle_delay=final_settle,
            )
            if not focus.get("ok"):
                raise ExtractError(
                    f"focus re-assert at {t_ms}ms failed: {focus.get('error')}",
                    checkpoint={
                        **status,
                        "failedAtMs": t_ms,
                        "framesCaptured": status["framesCaptured"],
                    },
                )

            # Dynamic state AFTER settle — correlated to target t_ms, never stale.
            live_wait = wait_liveclient_roster_at_time(
                transport,
                base,
                target_ms=int(t_ms),
                timeout=timeout,
                poll_interval=0.05,
                time_tol_sec=liveclient_time_tol_sec,
                wait_timeout=liveclient_wait_timeout,
            )
            if not live_wait.get("ok"):
                raise ExtractError(
                    f"liveclient time correlation at {t_ms}ms failed: {live_wait.get('error')}",
                    checkpoint={
                        **status,
                        "failedAtMs": t_ms,
                        "framesCaptured": status["framesCaptured"],
                        "liveclient": live_wait.get("evidence"),
                    },
                )
            frame_roster = merge_dynamic_roster_state(
                stable_roster, live_wait["roster"]
            )

            frame = capture_frame_positions(
                transport,
                base_url=base,
                roster=frame_roster,
                timeout=timeout,
                settle_delay=settle_delay,
                final_settle=final_settle,
                identity_retries=identity_retries,
                previous_selection_name=prev_sel,
            )
            if not frame.get("ok"):
                raise ExtractError(
                    f"capture at {t_ms}ms failed: {frame.get('error')}",
                    checkpoint={
                        **status,
                        "failedAtMs": t_ms,
                        "framesCaptured": status["framesCaptured"],
                        "partialParticipants": len(frame.get("participants") or []),
                    },
                )
            prev_sel = frame.get("previousSelectionName", prev_sel)
            assert out_fh is not None
            durable_append_jsonl_row(
                out_fh,
                rfc461_emit.stats_update_line(
                    game_id=gid,
                    game_time=int(t_ms),
                    participants=participants_to_rfc461_rows(frame["participants"]),
                ),
            )
            completed_times.append(int(t_ms))
            _sync_progress()

        status["ok"] = True
    except ExtractError as exc:
        pending_error = exc
    except Exception as exc:  # noqa: BLE001
        pending_error = ExtractError(
            f"{type(exc).__name__}: {exc}",
            checkpoint={**status, "traceback": traceback.format_exc()},
        )
    finally:
        if out_fh is not None:
            try:
                out_fh.flush()
                try:
                    os.fsync(out_fh.fileno())
                except OSError:
                    pass
            finally:
                out_fh.close()
        restore_info = restore_extractor_state(
            transport,
            playback_url=playback_url,
            render_url=render_url,
            original_playback=original_playback,
            original_render=original_render,
            timeout=timeout,
            seek_timeout=seek_timeout,
            time_tol=seek_time_tol,
            settle_delay=final_settle,
        )
        status["restoreAttempted"] = restore_info.get("restoreAttempted")
        status["restoreSucceeded"] = restore_info.get("restoreSucceeded")
        status["restore"] = {
            k: restore_info.get(k)
            for k in ("error", "snapshots", "restoreSucceeded")
        }
        status.update(
            _progress_fields(
                sample_ms=sample_ms,
                completed_times_ms=completed_times,
                out_path=out_path,
            )
        )
        status["framesCaptured"] = len(completed_times)
        if not restore_info.get("restoreSucceeded"):
            prev = status.get("error")
            rerr = restore_info.get("error") or "restore GET proof failed"
            status["error"] = f"{prev}; restore: {rerr}" if prev else f"restore: {rerr}"
        write_checkpoint_file(
            checkpoint_out,
            {
                "ok": bool(status.get("ok") and status.get("restoreSucceeded")),
                "error": status.get("error"),
                **status,
            },
        )

    if pending_error is not None:
        if isinstance(pending_error, ExtractError):
            pending_error.checkpoint = {
                **dict(pending_error.checkpoint or {}),
                **status,
            }
            write_checkpoint_file(
                checkpoint_out,
                {
                    "ok": False,
                    "error": str(pending_error),
                    **status,
                    "checkpoint": pending_error.checkpoint,
                },
            )
        raise pending_error

    if status.get("ok") and not status.get("restoreSucceeded"):
        status["ok"] = False
        raise ExtractError(
            status.get("error") or "restore failed after successful capture",
            checkpoint=status,
        )
    write_checkpoint_file(checkpoint_out, {"ok": True, **status})
    return status


def build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rofl", type=Path, required=True, help="Path to .rofl (build check)")
    ap.add_argument("--out", type=Path, required=True, help="Output rfc461 JSONL path")
    ap.add_argument("--start-ms", type=int, required=True)
    ap.add_argument("--end-ms", type=int, required=True)
    ap.add_argument("--step-ms", type=int, default=DEFAULT_STEP_MS)
    ap.add_argument("--app", type=Path, default=probe.DEFAULT_APP)
    ap.add_argument("--base-url", default=probe.DEFAULT_BASE)
    ap.add_argument("--timeout", type=float, default=probe.DEFAULT_TIMEOUT)
    ap.add_argument("--settle-delay", type=float, default=probe.DEFAULT_SETTLE_DELAY)
    ap.add_argument(
        "--final-settle",
        type=float,
        default=DEFAULT_FINAL_SETTLE,
        help="Short settle before selection GET (default efficient path)",
    )
    ap.add_argument("--identity-retries", type=int, default=DEFAULT_IDENTITY_RETRIES)
    ap.add_argument("--seek-timeout", type=float, default=DEFAULT_SEEK_TIMEOUT)
    ap.add_argument("--seek-time-tol", type=float, default=DEFAULT_SEEK_TIME_TOL)
    ap.add_argument(
        "--liveclient-time-tol-sec",
        type=float,
        default=DEFAULT_LIVECLIENT_TIME_TOL_SEC,
        help="Max |gameData.gameTime - target_sec| for liveclient correlation",
    )
    ap.add_argument(
        "--liveclient-wait-timeout",
        type=float,
        default=DEFAULT_LIVECLIENT_WAIT_TIMEOUT,
        help="Bounded poll timeout waiting for liveclient gameTime match",
    )
    ap.add_argument("--allow-build-mismatch", action="store_true")
    ap.add_argument("--game-id", type=int, default=0)
    ap.add_argument(
        "--resume",
        action="store_true",
        help=(
            "Append missing frames to an existing partial rfc461 JSONL after "
            "strict coverage/roster/schedule validation"
        ),
    )
    ap.add_argument(
        "--checkpoint-out",
        type=Path,
        default=None,
        help="Optional path for progress/failure checkpoint JSON (updated per frame)",
    )
    return ap


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    if not probe.is_loopback_url(args.base_url):
        print(
            json.dumps({"ok": False, "error": f"non-loopback URL refused: {args.base_url}"}),
            file=sys.stderr,
        )
        return 2

    transport = probe.default_http_transport
    try:
        status = extract_replay_api_jsonl(
            transport,
            base_url=args.base_url,
            rofl_path=args.rofl,
            app_path=args.app,
            out_path=args.out,
            start_ms=args.start_ms,
            end_ms=args.end_ms,
            step_ms=args.step_ms,
            allow_build_mismatch=args.allow_build_mismatch,
            timeout=args.timeout,
            settle_delay=args.settle_delay,
            final_settle=args.final_settle,
            identity_retries=args.identity_retries,
            seek_timeout=args.seek_timeout,
            seek_time_tol=args.seek_time_tol,
            liveclient_time_tol_sec=args.liveclient_time_tol_sec,
            liveclient_wait_timeout=args.liveclient_wait_timeout,
            game_id=args.game_id,
            resume=bool(args.resume),
            checkpoint_out=args.checkpoint_out,
        )
        print(json.dumps(status, indent=2, default=str))
        return 0 if status.get("ok") else 4
    except ExtractError as exc:
        payload = {
            "ok": False,
            "error": str(exc),
            "checkpoint": exc.checkpoint,
        }
        print(json.dumps(payload, indent=2, default=str))
        if args.checkpoint_out:
            write_checkpoint_file(args.checkpoint_out, payload)
        # Restore failures after write → exit 3; other extract failures → 4
        err = str(exc).lower()
        if "restore" in err:
            return 3
        return 4
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
