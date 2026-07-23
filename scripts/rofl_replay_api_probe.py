#!/usr/bin/env python3
"""
Official Riot Replay API feasibility probe (stdlib-only, macOS-friendly).

Proves a supported *playback-access* path when the local Replay API is up —
not ROFL decryption. Focus-mode selection yields real per-champion world
coordinates at a paused timestamp; top mode does not. Capture JSON is
diagnostic proof data only (not ingestible timeline JSONL yet).

Examples:
  python3 scripts/rofl_replay_api_probe.py \\
    --rofl "$HOME/Documents/League of Legends/Replays/BR1-3263797356.rofl"

  npm run rofl:replay-api -- --rofl '.../BR1-3263797356.rofl' \\
    --probe-selection Gnar

  npm run rofl:replay-api -- --rofl '.../BR1-3263797356.rofl' \\
    --capture-current --capture-out /tmp/replay_focus_capture.json
"""
from __future__ import annotations

import argparse
import json
import math
import plistlib
import ssl
import struct
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Mapping, Optional
from urllib.parse import urlparse

import rofl_metadata

DEFAULT_ROFL = Path(
    "/Users/river/Documents/League of Legends/Replays/BR1-3263797356.rofl"
)
DEFAULT_APP = Path(
    "/Applications/League of Legends.app/Contents/LoL/Game/LeagueofLegends.app"
)
DEFAULT_BASE = "https://127.0.0.1:2999"
DEFAULT_TIMEOUT = 2.0
# Conservative settle between pause/select/read — avoid rapid seek/mode thrash on macOS.
DEFAULT_SETTLE_DELAY = 0.35
# Tight tolerance for proving playback time was not disturbed by restore.
PLAYBACK_TIME_TOL = 1e-4
# After resume, allow wall-clock * speed * slack drift past the restored time.
RESUME_TIME_SLACK = 1.25
RENDER_RESTORE_FIELDS = (
    "cameraMode",
    "cameraAttached",
    "selectionName",
    "selectionOffset",
    "cameraPosition",
)
# Fields that must remain stable even after an unpaused restore resumes.
RENDER_RESTORE_STABLE_FIELDS = (
    "cameraMode",
    "cameraAttached",
    "selectionName",
    "selectionOffset",
)

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1", "[::1]"})

ENDPOINTS = (
    ("openapi", "/swagger/v3/openapi.json"),
    ("game", "/replay/game"),
    ("playback", "/replay/playback"),
    ("render", "/replay/render"),
    ("sequence", "/replay/sequence"),
    ("liveclient_allgamedata", "/liveclientdata/allgamedata"),
    ("liveclient_playerlist", "/liveclientdata/playerlist"),
)

KNOWN_RENDER_SELECTION_FIELDS = (
    "selectionName",
    "selectionOffset",
    "cameraAttached",
    "cameraMode",
)
POSITION_SOURCE_FOCUS = "replay_api_focus_selection"
FOCUS_CAMERA_MODE = "focus"
ZERO_OFFSET = {"x": 0.0, "y": 0.0, "z": 0.0}
ENABLE_REPLAY_API_INSTRUCTIONS = {
    "section": "[General]",
    "setting": "EnableReplayApi=1",
    "note": (
        "Manually add EnableReplayApi=1 under [General] in the League "
        "game.cfg. This probe never edits game.cfg. Restart an active "
        "replay (or start a new replay session) after changing the setting."
    ),
    "examplePathMac": (
        "/Applications/League of Legends.app/Contents/LoL/Config/game.cfg"
    ),
    "restartRequired": True,
}


Transport = Callable[..., dict[str, Any]]


def normalize_build(version: str) -> str:
    """Collapse dotted/undotted Riot build strings to comparable digit runs."""
    return "".join(ch for ch in (version or "") if ch.isdigit())


def builds_match(a: str, b: str) -> bool:
    na, nb = normalize_build(a), normalize_build(b)
    return bool(na) and na == nb


def is_loopback_url(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host in {"127.0.0.1", "localhost", "::1"}


def ssl_context_for_url(url: str) -> ssl.SSLContext:
    """Accept self-signed TLS only for loopback Replay API hosts."""
    if not is_loopback_url(url):
        return ssl.create_default_context()
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def read_rofl_build(path: Path) -> dict[str, Any]:
    """Read ROFL2 head version without requiring zstd segment inflate."""
    data = path.read_bytes()
    magic = data[:6]
    out: dict[str, Any] = {
        "path": str(path),
        "size": len(data),
        "magic": magic.hex(),
        "format": None,
        "version": None,
        "gameLengthMs": None,
        "error": None,
    }
    if magic == b"RIOT\x02\x00":
        out["format"] = "ROFL2"
        ver_len = data[14]
        version = data[15 : 15 + ver_len].decode("ascii", errors="replace")
        out["version"] = version
        try:
            # Prefer existing parser when available (metadata cross-check).
            scripts_dir = str(Path(__file__).resolve().parent)
            if scripts_dir not in sys.path:
                sys.path.insert(0, scripts_dir)
            from rofl2_probe import parse_rofl2  # type: ignore

            parsed = parse_rofl2(path)
            out["version"] = parsed.get("version") or version
            meta = parsed.get("meta")
            if isinstance(meta, Mapping):
                try:
                    out["gameLengthMs"] = int(meta.get("gameLength"))
                except (TypeError, ValueError):
                    out["gameLengthMs"] = None
            out["parser"] = "rofl2_probe.parse_rofl2"
        except Exception:
            field_off = 15 + ver_len
            if field_off + 16 <= len(data):
                out["header_u32s"] = list(struct.unpack_from("<IIII", data, field_off))
            out["parser"] = "lightweight_rofl2_head"
    elif magic == b"RIOT\x00\x00":
        out["format"] = "ROFL1"
        out["error"] = "ROFL1 version lives in mid-file metadata; not probed here"
    else:
        out["error"] = f"unrecognized magic {magic!r}"
    return out


def read_app_build(app_path: Path) -> dict[str, Any]:
    plist_path = app_path / "Contents" / "Info.plist"
    out: dict[str, Any] = {
        "path": str(app_path),
        "plistPath": str(plist_path),
        "CFBundleVersion": None,
        "CFBundleShortVersionString": None,
        "FileVersion": None,
        "version": None,
        "error": None,
    }
    if not plist_path.is_file():
        out["error"] = f"Info.plist not found: {plist_path}"
        return out
    try:
        with plist_path.open("rb") as fh:
            info = plistlib.load(fh)
    except Exception as exc:  # noqa: BLE001 — surface as status evidence
        out["error"] = f"plist read failed: {exc}"
        return out
    out["CFBundleVersion"] = info.get("CFBundleVersion")
    out["CFBundleShortVersionString"] = info.get("CFBundleShortVersionString")
    out["FileVersion"] = info.get("FileVersion")
    # Prefer FileVersion (dotted, matches ROFL) then CFBundleVersion.
    out["version"] = (
        info.get("FileVersion")
        or info.get("CFBundleVersion")
        or info.get("CFBundleShortVersionString")
    )
    return out


def default_http_transport(
    method: str,
    url: str,
    *,
    body: Optional[Mapping[str, Any]] = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """Single-shot HTTP request; no retries (bounded timeout only)."""
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method.upper())
    try:
        with urllib.request.urlopen(
            req, timeout=timeout, context=ssl_context_for_url(url)
        ) as resp:
            raw = resp.read()
            text = raw.decode("utf-8", errors="replace")
            try:
                parsed = json.loads(text) if text else None
            except json.JSONDecodeError:
                parsed = None
            return {
                "ok": True,
                "status": getattr(resp, "status", 200),
                "url": url,
                "method": method.upper(),
                "body": parsed,
                "rawText": text if parsed is None else None,
                "error": None,
            }
    except urllib.error.HTTPError as exc:
        raw = exc.read() if hasattr(exc, "read") else b""
        text = raw.decode("utf-8", errors="replace") if raw else ""
        try:
            parsed = json.loads(text) if text else None
        except json.JSONDecodeError:
            parsed = None
        return {
            "ok": False,
            "status": exc.code,
            "url": url,
            "method": method.upper(),
            "body": parsed,
            "rawText": text if parsed is None else None,
            "error": f"HTTP {exc.code}: {exc.reason}",
        }
    except Exception as exc:  # noqa: BLE001 — connection refused is expected
        return {
            "ok": False,
            "status": None,
            "url": url,
            "method": method.upper(),
            "body": None,
            "rawText": None,
            "error": f"{type(exc).__name__}: {exc}",
        }


def schema_property_names(openapi: Any) -> set[str]:
    """Collect property names from an OpenAPI document (best-effort)."""
    names: set[str] = set()

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            props = node.get("properties")
            if isinstance(props, dict):
                names.update(str(k) for k in props.keys())
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(openapi)
    return names



def classify_selection_fields(
    schema_names: set[str],
    *,
    allow_experimental: bool = True,
) -> dict[str, str]:
    """Map selection-related fields to schema-supported vs experimental."""
    out: dict[str, str] = {}
    for name in KNOWN_RENDER_SELECTION_FIELDS:
        if name in schema_names:
            out[name] = "schema-supported"
        elif name == "cameraMode":
            out[name] = "schema-supported"
        elif allow_experimental and name in ("selectionName", "selectionOffset"):
            out[name] = "experimental"
        elif name == "cameraAttached":
            out[name] = "schema-supported" if name in schema_names else "experimental"
        else:
            out[name] = "absent"
    return out


def _settle(delay: float) -> None:
    if delay and delay > 0:
        time.sleep(delay)


def _is_finite_vec3(pos: Any) -> bool:
    if not isinstance(pos, Mapping):
        return False
    try:
        vals = [float(pos[k]) for k in ("x", "y", "z")]
    except (KeyError, TypeError, ValueError):
        return False
    return all(math.isfinite(v) for v in vals)


def _xz_position(pos: Mapping[str, Any]) -> dict[str, float]:
    return {"x": float(pos["x"]), "z": float(pos["z"])}


def _vec_approx_equal(a: Any, b: Any, *, tol: float = 1e-3) -> bool:
    if not isinstance(a, Mapping) or not isinstance(b, Mapping):
        return a == b
    for axis in ("x", "y", "z"):
        try:
            if abs(float(a.get(axis, 0)) - float(b.get(axis, 0))) > tol:
                return False
        except (TypeError, ValueError):
            return False
    return True


def _player_identity_key(value: Any) -> str:
    """Normalize Riot player identity for comparison (strip #tag, casefold)."""
    text = str(value or "").strip()
    if "#" in text:
        text = text.split("#", 1)[0].strip()
    return text.casefold()


def identities_match(a: Any, b: Any) -> bool:
    ka, kb = _player_identity_key(a), _player_identity_key(b)
    return bool(ka) and ka == kb


def champion_internal_name(display_name: str, raw: Optional[Mapping[str, Any]] = None) -> str:
    """Internal champion id (e.g. TahmKench). Never use spaced display names for selection.

    Strips Riot localization prefixes such as ``game_character_displayname_``.
    """
    candidates: list[str] = []
    if raw:
        for key in ("rawChampionName", "championId", "rawChampionNameKey"):
            val = raw.get(key)
            if isinstance(val, str) and val.strip():
                candidates.append(val.strip())
    if display_name:
        candidates.append(str(display_name).strip())

    for cand in candidates:
        cleaned = _strip_riot_champion_prefix(cand)
        if cleaned and " " not in cleaned:
            return cleaned
    # Last resort: strip spaces from display name.
    return "".join(ch for ch in str(display_name or "") if not ch.isspace())


def _strip_riot_champion_prefix(name: str) -> str:
    """Turn game_character_displayname_TahmKench into TahmKench."""
    text = str(name or "").strip()
    if not text:
        return ""
    lower = text.casefold()
    prefixes = (
        "game_character_displayname_",
        "game_character_display_name_",
        "game_character_name_",
        "character_displayname_",
        "character_display_name_",
    )
    for prefix in prefixes:
        if lower.startswith(prefix):
            return text[len(prefix) :]
    for marker in ("_displayname_", "_display_name_"):
        idx = lower.rfind(marker)
        if idx >= 0:
            return text[idx + len(marker) :]
    return text


def _selection_name_accepted(
    posted_name: Any,
    read_name: Any,
    *,
    expected_player_identity: Optional[str] = None,
    previous_selection_name: Optional[Any] = None,
) -> dict[str, Any]:
    """Validate selection against expected player identity (not mere nonempty canonicalize).

    Adversarial finding: posting spaced display name \"Tahm Kench\" can silently retain
    the previous champion's selectionName/cameraPosition. Finite coordinates alone are
    insufficient — canonical selectionName must match the expected player identity.
    """
    canonical_nonempty = bool(read_name not in (None, "") and str(read_name).strip())
    name_echoed = bool(canonical_nonempty and read_name == posted_name)
    name_canonicalized = bool(
        canonical_nonempty
        and str(read_name).strip()
        and str(read_name) != str(posted_name)
    )

    identity_matched = False
    stale_retained = False
    if expected_player_identity:
        identity_matched = identities_match(read_name, expected_player_identity)
        if (
            previous_selection_name not in (None, "")
            and not identities_match(previous_selection_name, expected_player_identity)
            and identities_match(read_name, previous_selection_name)
        ):
            stale_retained = True
            identity_matched = False
    else:
        # Probe without roster expected-id: require nonempty + echo/tag-strip match,
        # or a real change away from the previous selection.
        posted_id = _player_identity_key(posted_name)
        read_id = _player_identity_key(read_name)
        tag_strip_match = bool(posted_id and read_id and posted_id == read_id)
        changed_from_previous = (
            previous_selection_name in (None, "")
            or not identities_match(read_name, previous_selection_name)
        )
        identity_matched = canonical_nonempty and (
            name_echoed or tag_strip_match or (name_canonicalized and changed_from_previous)
        )
        if (
            previous_selection_name not in (None, "")
            and identities_match(read_name, previous_selection_name)
            and not tag_strip_match
            and not name_echoed
        ):
            stale_retained = True
            identity_matched = False

    selection_accepted = bool(canonical_nonempty and identity_matched and not stale_retained)
    return {
        "nameEchoed": name_echoed,
        "nameCanonicalized": name_canonicalized,
        "canonicalNonempty": canonical_nonempty,
        "identityMatched": identity_matched,
        "staleRetained": stale_retained,
        "selectionAccepted": selection_accepted,
        "expectedPlayerIdentity": expected_player_identity,
        "previousSelectionName": previous_selection_name,
    }


def classify_focus_readback(
    posted_key: str,
    readback: Mapping[str, Any],
    *,
    baseline_camera: Any = None,
    expected_player_identity: Optional[str] = None,
    previous_selection_name: Optional[Any] = None,
) -> dict[str, Any]:
    """Classify focus-mode selection + coordinate support.

    Proven path: cameraMode=focus, select by player identity (summonerName),
    cameraAttached=true, selectionOffset zero → finite cameraPosition.
    Top mode is NOT proof. Stale/spaced champion display names are NOT proof.
    """
    mode = readback.get("cameraMode")
    pos = readback.get("cameraPosition")
    name_info = _selection_name_accepted(
        posted_key,
        readback.get("selectionName"),
        expected_player_identity=expected_player_identity,
        previous_selection_name=previous_selection_name,
    )
    finite = _is_finite_vec3(pos)
    focus_mode = mode == FOCUS_CAMERA_MODE
    attached = bool(readback.get("cameraAttached")) is True

    camera_changed = False
    if baseline_camera is not None and pos is not None:
        camera_changed = not _vec_approx_equal(baseline_camera, pos)

    selection_accepted = name_info["selectionAccepted"]
    # Coordinates require identity-valid selection + focus + finite pos.
    # Finite pos with stale selectionName is explicitly invalid.
    coordinate_proven = bool(selection_accepted and focus_mode and finite)
    position_claim_allowed = coordinate_proven

    if coordinate_proven:
        outcome = "supported"
        position_coverage = POSITION_SOURCE_FOCUS
    elif name_info["staleRetained"]:
        outcome = "unsupported"
        position_coverage = "none"
    elif selection_accepted:
        outcome = "supported-but-coordinate-candidate"
        position_coverage = "none"
    elif attached or finite:
        outcome = "candidate"
        position_coverage = "none"
    else:
        outcome = "unsupported"
        position_coverage = "none"

    return {
        "outcome": outcome,
        "accepted": selection_accepted,
        "selectionAccepted": selection_accepted,
        "coordinateProven": coordinate_proven,
        "positionClaimAllowed": position_claim_allowed,
        "positionCoverage": position_coverage,
        "nameEchoed": name_info["nameEchoed"],
        "nameCanonicalized": name_info["nameCanonicalized"],
        "canonicalNonempty": name_info["canonicalNonempty"],
        "identityMatched": name_info["identityMatched"],
        "staleRetained": name_info["staleRetained"],
        "focusMode": focus_mode,
        "cameraMode": mode,
        "attachmentTrue": attached,
        "finitePosition": finite,
        "cameraPositionChanged": camera_changed,
        "evidence": {
            "postedKey": posted_key,
            "expectedPlayerIdentity": expected_player_identity,
            "previousSelectionName": previous_selection_name,
            "selectionName": readback.get("selectionName"),
            "cameraMode": mode,
            "cameraAttached": readback.get("cameraAttached"),
            "selectionOffset": readback.get("selectionOffset"),
            "cameraPosition": pos,
            "baselineCameraPosition": baseline_camera,
            "positionXZ": _xz_position(pos) if finite else None,
        },
    }


def _restore_bodies(
    original_playback: Mapping[str, Any], original_render: Mapping[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build restore POST bodies. Never include playback time (would seek)."""
    restore_playback: dict[str, Any] = {
        k: original_playback[k]
        for k in ("paused", "speed")
        if k in original_playback
    }
    # Explicitly never restore time — this primitive does not change playback time.
    assert "time" not in restore_playback
    return restore_playback, dict(original_render)


def _playback_ready_for_capture(playback: Mapping[str, Any]) -> tuple[bool, str]:
    """--capture-current requires an already-paused, non-seeking replay."""
    if not playback.get("paused"):
        return (
            False,
            "replay must already be paused for --capture-current "
            "(refusing to change playback)",
        )
    if playback.get("seeking") is True:
        return (
            False,
            "replay seeking=true; wait until seeking=false before --capture-current "
            "(refusing to change playback)",
        )
    return True, ""


def _verify_render_restore_fields(
    original_render: Mapping[str, Any],
    render_body: Mapping[str, Any],
    *,
    include_camera_position: bool,
) -> list[str]:
    """Compare restored render fields; optionally skip live cameraPosition."""
    errors: list[str] = []
    fields = (
        RENDER_RESTORE_FIELDS
        if include_camera_position
        else RENDER_RESTORE_STABLE_FIELDS
    )
    for field in fields:
        if field not in original_render:
            continue
        want = original_render.get(field)
        got = render_body.get(field)
        if field == "selectionName":
            want_s = "" if want in (None, "") else str(want)
            got_s = "" if got in (None, "") else str(got)
            if want_s != got_s:
                errors.append(
                    f"render.selectionName mismatch after restore: {got_s!r} vs {want_s!r}"
                )
            continue
        if field in ("cameraPosition", "selectionOffset"):
            if want is None and got in (None, {}):
                continue
            if not _vec_approx_equal(want, got, tol=1e-3):
                errors.append(f"render.{field} mismatch after restore")
        elif got != want:
            errors.append(f"render.{field} mismatch after restore")
    return errors


def _resume_time_errors(
    *,
    restored_time_sec: float,
    observed_time_sec: float,
    resume_mono: float,
    speed: float,
    time_tol: float,
    now_mono: Optional[float] = None,
) -> list[str]:
    """After unpause, time may advance; require monotonic within elapsed slack."""
    errors: list[str] = []
    now = float(time.monotonic() if now_mono is None else now_mono)
    elapsed = max(0.0, now - float(resume_mono))
    try:
        spd = max(0.0, float(speed))
    except (TypeError, ValueError):
        spd = 1.0
    upper = (
        float(restored_time_sec)
        + elapsed * spd * float(RESUME_TIME_SLACK)
        + float(time_tol)
    )
    lower = float(restored_time_sec) - float(time_tol)
    got = float(observed_time_sec)
    if got < lower:
        errors.append(
            f"playback time regressed after resume: {got} vs restored {restored_time_sec}"
        )
    elif got > upper:
        errors.append(
            f"playback time advanced beyond resume tolerance: {got} vs "
            f"restored {restored_time_sec} (elapsed={elapsed:.3f}s speed={spd})"
        )
    return errors


def _verify_restore_readback(
    *,
    original_playback: Mapping[str, Any],
    original_render: Mapping[str, Any],
    playback_body: Any,
    render_body: Any,
    time_tol: float = PLAYBACK_TIME_TOL,
    require_exact_time: bool = True,
    include_camera_position: bool = True,
    resume_mono: Optional[float] = None,
    restored_time_sec: Optional[float] = None,
) -> list[str]:
    """Prove restore via GET readback — HTTP 200 alone is insufficient.

    When ``require_exact_time`` is false (post-resume of an originally unpaused
    replay), accept monotonically advanced time within elapsed-time slack and do
    not require ``cameraPosition`` equality.
    """
    errors: list[str] = []
    if not isinstance(playback_body, Mapping):
        return ["playback restore readback missing/invalid"]
    if not isinstance(render_body, Mapping):
        return ["render restore readback missing/invalid"]

    if playback_body.get("seeking") is True:
        errors.append("seeking=true after restore")

    if "time" in original_playback or restored_time_sec is not None:
        try:
            want_t = float(
                original_playback["time"]
                if restored_time_sec is None
                else restored_time_sec
            )
            now_t = float(playback_body.get("time"))
            if require_exact_time:
                if abs(now_t - want_t) > float(time_tol):
                    errors.append(
                        f"playback time changed after restore: {now_t} vs {want_t}"
                    )
            else:
                if resume_mono is None:
                    errors.append("resume timing missing for unpaused restore proof")
                else:
                    speed = original_playback.get("speed", 1.0)
                    try:
                        speed_f = float(playback_body.get("speed", speed))
                    except (TypeError, ValueError):
                        speed_f = float(speed) if speed is not None else 1.0
                    errors.extend(
                        _resume_time_errors(
                            restored_time_sec=want_t,
                            observed_time_sec=now_t,
                            resume_mono=float(resume_mono),
                            speed=speed_f,
                            time_tol=float(time_tol),
                        )
                    )
        except (TypeError, ValueError):
            errors.append("playback time not comparable after restore")

    if "paused" in original_playback and playback_body.get("paused") != original_playback.get(
        "paused"
    ):
        errors.append(
            f"paused mismatch after restore: {playback_body.get('paused')!r} "
            f"vs {original_playback.get('paused')!r}"
        )
    if "speed" in original_playback:
        try:
            if abs(float(playback_body.get("speed")) - float(original_playback["speed"])) > 1e-6:
                errors.append("speed mismatch after restore")
        except (TypeError, ValueError):
            errors.append("speed not comparable after restore")

    errors.extend(
        _verify_render_restore_fields(
            original_render,
            render_body,
            include_camera_position=include_camera_position,
        )
    )
    return errors


def focus_select_target(
    transport: Transport,
    render_url: str,
    selection_key: str,
    *,
    timeout: float,
    settle_delay: float,
    final_settle: Optional[float] = None,
) -> dict[str, Any]:
    """Safe focus select by selection key: detach → name → attach+offset → GET.

    When ``final_settle`` is set, POSTs run without inter-POST sleeps and only the
    final settle applies before GET (scales better for multi-frame extraction).
    When unset, legacy behavior settles after every POST using ``settle_delay``.
    """
    steps: dict[str, Any] = {"selectionKey": selection_key}
    inter = 0.0 if final_settle is not None else settle_delay
    end = settle_delay if final_settle is None else max(0.0, float(final_settle))
    steps["detach"] = transport(
        "POST", render_url, body={"cameraAttached": False}, timeout=timeout
    )
    _settle(inter)
    steps["select"] = transport(
        "POST",
        render_url,
        body={"selectionName": selection_key},
        timeout=timeout,
    )
    _settle(inter)
    steps["attach"] = transport(
        "POST",
        render_url,
        body={"cameraAttached": True, "selectionOffset": dict(ZERO_OFFSET)},
        timeout=timeout,
    )
    _settle(end)
    steps["readback"] = transport("GET", render_url, timeout=timeout)
    return steps


def focus_select_compact(
    transport: Transport,
    render_url: str,
    selection_key: str,
    *,
    timeout: float,
    settle_delay: float,
    expected_player_identity: Optional[str] = None,
    previous_selection_name: Optional[Any] = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Experimental single-POST cached select: composite render + settle + GET.

    Posts ``selectionName`` + ``cameraAttached=true`` + zero ``selectionOffset``
    (and ``cameraMode=focus``) in one body, then runs the same
    ``classify_focus_readback`` proof as the full path. Callers must fall back to
    ``focus_select_target`` / ``focus_select_roster_member`` on any unproven
    readback. Not a product default.
    """
    key = str(selection_key or "").strip()
    steps: dict[str, Any] = {
        "selectionKey": key,
        "strategy": "compact",
    }
    body = {
        "selectionName": key,
        "cameraAttached": True,
        "selectionOffset": dict(ZERO_OFFSET),
        "cameraMode": FOCUS_CAMERA_MODE,
    }
    steps["compact"] = transport("POST", render_url, body=body, timeout=timeout)
    _settle(max(0.0, float(settle_delay)))
    steps["readback"] = transport("GET", render_url, timeout=timeout)
    read_body = (
        steps["readback"].get("body") if steps["readback"].get("ok") else {}
    )
    if not isinstance(read_body, dict):
        read_body = {}
    classification = classify_focus_readback(
        key,
        read_body,
        expected_player_identity=expected_player_identity,
        previous_selection_name=previous_selection_name,
    )
    steps["classification"] = {
        k: classification[k]
        for k in (
            "outcome",
            "selectionAccepted",
            "coordinateProven",
            "identityMatched",
            "staleRetained",
        )
    }
    return steps, classification


# Back-compat alias used by older call sites / docs.
focus_select_champion = focus_select_target


def selection_keys_for_roster_row(row: Mapping[str, Any]) -> list[str]:
    """Ordered selection keys: plain player identity first, then safe fallbacks.

    Never prefer spaced champion display names (\"Tahm Kench\") — they can silently
    retain the previous selection. Patch 16.14 live evidence also shows that the
    tagged Riot ID can be rejected while ``riotIdGameName`` succeeds, so avoid
    wasting an identity retry on the tagged form before the proven plain name.
    """
    keys: list[str] = []
    for candidate in (
        row.get("playerName"),
        row.get("summonerName"),
        row.get("championInternalName"),
    ):
        text = str(candidate or "").strip()
        if not text:
            continue
        if " " in text and text == str(row.get("championName") or "").strip():
            # Spaced display champion name is not a valid primary/fallback key.
            continue
        if text not in keys:
            keys.append(text)
    return keys


def focus_select_roster_member(
    transport: Transport,
    render_url: str,
    row: Mapping[str, Any],
    *,
    timeout: float,
    settle_delay: float,
    previous_selection_name: Optional[Any] = None,
    final_settle: Optional[float] = None,
    identity_retries: int = 0,
    preferred_key: Optional[str] = None,
) -> tuple[dict[str, Any], dict[str, Any], str]:
    """Try player-identity keys then champion internal name; validate identity match.

    ``final_settle`` / ``identity_retries`` support efficient multi-frame capture:
    short final settle + re-verify rather than sleeping after every POST.
    """
    keys = selection_keys_for_roster_row(row)
    if preferred_key is not None:
        preferred = str(preferred_key).strip()
        # A cached key is only a fast path when it is still valid for this
        # identity. The caller performs the bounded full-key reassertion.
        keys = [preferred] if preferred and preferred in keys else []
    expected = str(
        row.get("expectedSelectionIdentity")
        or row.get("playerName")
        or row.get("summonerName")
        or ""
    ).strip()
    if "#" in expected:
        expected = expected.split("#", 1)[0].strip()

    last_steps: dict[str, Any] = {"selectionKey": None, "attempts": []}
    last_classification: dict[str, Any] = {
        "outcome": "unsupported",
        "coordinateProven": False,
        "selectionAccepted": False,
        "staleRetained": False,
        "positionCoverage": "none",
    }
    last_key = ""
    for key in keys:
        attempts = 1 + max(0, int(identity_retries))
        for attempt_i in range(attempts):
            # First attempt uses efficient final_settle; retries bump settle.
            settle_for_attempt = (
                settle_delay
                if attempt_i > 0 or final_settle is None
                else None
            )
            final_for_attempt = (
                None if settle_for_attempt is not None else final_settle
            )
            steps = focus_select_target(
                transport,
                render_url,
                key,
                timeout=timeout,
                settle_delay=settle_delay if settle_for_attempt is None else settle_for_attempt,
                final_settle=final_for_attempt,
            )
            read_body = steps["readback"].get("body") if steps["readback"].get("ok") else {}
            if not isinstance(read_body, dict):
                read_body = {}
            classification = classify_focus_readback(
                key,
                read_body,
                expected_player_identity=expected or None,
                previous_selection_name=previous_selection_name,
            )
            steps["classification"] = {
                k: classification[k]
                for k in (
                    "outcome",
                    "selectionAccepted",
                    "coordinateProven",
                    "identityMatched",
                    "staleRetained",
                )
            }
            last_steps = steps
            last_steps["attempts"] = list(last_steps.get("attempts") or []) + [
                {
                    "key": key,
                    "outcome": classification["outcome"],
                    "attempt": attempt_i,
                }
            ]
            last_classification = classification
            last_key = key
            if classification["coordinateProven"]:
                return steps, classification, key
            previous_selection_name = read_body.get(
                "selectionName", previous_selection_name
            )
    return last_steps, last_classification, last_key


def ensure_paused_no_seek(
    transport: Transport,
    playback_url: str,
    *,
    timeout: float,
    settle_delay: float,
) -> dict[str, Any]:
    resp = transport("POST", playback_url, body={"paused": True}, timeout=timeout)
    _settle(settle_delay)
    return resp


def wait_playback_settled(
    transport: Transport,
    playback_url: str,
    *,
    target_time_sec: Optional[float] = None,
    timeout: float,
    poll_interval: float = 0.05,
    time_tol: float = PLAYBACK_TIME_TOL,
    seek_timeout: float = 8.0,
) -> dict[str, Any]:
    """Poll GET /replay/playback until seeking=false (and optional exact time)."""
    deadline = time.monotonic() + max(0.05, float(seek_timeout))
    last: dict[str, Any] = {"ok": False, "error": "seek wait not started"}
    while time.monotonic() < deadline:
        last = transport("GET", playback_url, timeout=timeout)
        if not last.get("ok"):
            return {
                "ok": False,
                "settled": False,
                "error": last.get("error") or "playback GET failed during seek wait",
                "body": last.get("body"),
                "status": last.get("status"),
            }
        body = last.get("body") if isinstance(last.get("body"), dict) else {}
        seeking = body.get("seeking") is True
        time_ok = True
        if target_time_sec is not None:
            try:
                now_t = float(body.get("time"))
                time_ok = abs(now_t - float(target_time_sec)) <= float(time_tol)
            except (TypeError, ValueError):
                time_ok = False
        if (not seeking) and time_ok:
            return {
                "ok": True,
                "settled": True,
                "body": body,
                "status": last.get("status"),
                "error": None,
            }
        _settle(poll_interval)
    body = last.get("body") if isinstance(last.get("body"), dict) else {}
    return {
        "ok": False,
        "settled": False,
        "error": (
            f"seek did not settle within {seek_timeout}s "
            f"(seeking={body.get('seeking')!r}, time={body.get('time')!r}, "
            f"target={target_time_sec!r})"
        ),
        "body": body,
        "status": last.get("status"),
    }


def seek_to_time(
    transport: Transport,
    playback_url: str,
    target_time_sec: float,
    *,
    timeout: float,
    poll_interval: float = 0.05,
    time_tol: float = 1e-3,
    seek_timeout: float = 8.0,
    pause_first: bool = True,
) -> dict[str, Any]:
    """Pause (optional), POST target playback time, poll until settled at target."""
    steps: dict[str, Any] = {"targetTimeSec": float(target_time_sec)}
    if pause_first:
        steps["pause"] = transport(
            "POST", playback_url, body={"paused": True}, timeout=timeout
        )
        if not steps["pause"].get("ok"):
            return {
                "ok": False,
                "settled": False,
                "error": steps["pause"].get("error") or "pause before seek failed",
                "steps": steps,
            }
    steps["seekPost"] = transport(
        "POST",
        playback_url,
        body={"time": float(target_time_sec)},
        timeout=timeout,
    )
    if not steps["seekPost"].get("ok"):
        return {
            "ok": False,
            "settled": False,
            "error": steps["seekPost"].get("error") or "seek POST failed",
            "steps": steps,
        }
    wait = wait_playback_settled(
        transport,
        playback_url,
        target_time_sec=float(target_time_sec),
        timeout=timeout,
        poll_interval=poll_interval,
        time_tol=time_tol,
        seek_timeout=seek_timeout,
    )
    steps["wait"] = {
        "ok": wait.get("ok"),
        "settled": wait.get("settled"),
        "error": wait.get("error"),
        "time": (wait.get("body") or {}).get("time") if isinstance(wait.get("body"), dict) else None,
        "seeking": (
            (wait.get("body") or {}).get("seeking")
            if isinstance(wait.get("body"), dict)
            else None
        ),
    }
    return {
        "ok": bool(wait.get("ok") and wait.get("settled")),
        "settled": bool(wait.get("settled")),
        "error": wait.get("error"),
        "body": wait.get("body"),
        "steps": steps,
    }


def set_camera_mode_focus(
    transport: Transport,
    render_url: str,
    *,
    timeout: float,
    settle_delay: float,
) -> dict[str, Any]:
    resp = transport(
        "POST", render_url, body={"cameraMode": FOCUS_CAMERA_MODE}, timeout=timeout
    )
    _settle(settle_delay)
    return resp


def _apply_restore(
    result: dict[str, Any],
    transport: Transport,
    *,
    playback_url: str,
    render_url: str,
    restore_playback_body: dict[str, Any],
    restore_render_body: dict[str, Any],
    original_playback: Mapping[str, Any],
    original_render: Mapping[str, Any],
    timeout: float,
    settle_delay: float = 0.0,
) -> None:
    """POST restore (never time): paused proof, then resume with soft final proof.

    This primitive never seeks. Phase 1 keeps/forces paused and proves exact time +
    critical render fields. Phase 2 restores speed + original paused; if originally
    unpaused, final proof allows monotonic time drift and skips cameraPosition.
    """
    result["restoreAttempted"] = True
    restore_errors: list[str] = []
    originally_paused = bool(original_playback.get("paused", True))
    result["originallyPaused"] = originally_paused
    result["snapshots"]["restorePlan"] = {
        "originallyPaused": originally_paused,
        "finalExactTime": originally_paused,
        "finalRequireCameraPosition": originally_paused,
        "seeksTime": False,
    }

    if "time" in restore_playback_body:
        restore_errors.append("internal error: restore playback body must not include time")
        result["restoreSucceeded"] = False
        result["restored"] = False
        result["error"] = "; ".join(restore_errors)
        return

    render_restore = transport(
        "POST", render_url, body=restore_render_body, timeout=timeout
    )
    # Riot often ignores selectionName/cameraAttached in a bulk render POST — re-apply
    # the critical fields explicitly (still no playback seek).
    critical = {
        k: original_render[k] for k in RENDER_RESTORE_FIELDS if k in original_render
    }
    # Normalize empty selection for clear comparison.
    if "selectionName" in critical and critical["selectionName"] is None:
        critical["selectionName"] = ""
    critical_restore = None
    if critical:
        critical_restore = transport(
            "POST", render_url, body=critical, timeout=timeout
        )
    result["snapshots"]["restoreRender"] = {
        "ok": render_restore.get("ok"),
        "status": render_restore.get("status"),
        "error": render_restore.get("error"),
    }
    if critical_restore is not None:
        result["snapshots"]["restoreRenderCritical"] = {
            "ok": critical_restore.get("ok"),
            "status": critical_restore.get("status"),
            "error": critical_restore.get("error"),
            "postedKeys": sorted(critical.keys()),
        }
    if not render_restore.get("ok"):
        restore_errors.append(render_restore.get("error") or "render restore POST failed")
    if critical_restore is not None and not critical_restore.get("ok"):
        restore_errors.append(
            critical_restore.get("error") or "render critical restore POST failed"
        )

    # Phase 1: hold paused for stable proof (never resume yet).
    phase1_body = {"paused": True}
    if "speed" in original_playback:
        # Keep speed unchanged during stable proof; resume posts the original speed.
        pass
    phase1_post = transport("POST", playback_url, body=phase1_body, timeout=timeout)
    result["snapshots"]["restorePhase1PlaybackPost"] = {
        "ok": phase1_post.get("ok"),
        "status": phase1_post.get("status"),
        "error": phase1_post.get("error"),
        "postedKeys": sorted(phase1_body.keys()),
    }
    if not phase1_post.get("ok"):
        restore_errors.append(
            phase1_post.get("error") or "phase1 paused restore POST failed"
        )

    _settle(settle_delay)
    phase1_playback_get = transport("GET", playback_url, timeout=timeout)
    phase1_render_get = transport("GET", render_url, timeout=timeout)
    result["snapshots"]["restorePhase1PlaybackGet"] = {
        "ok": phase1_playback_get.get("ok"),
        "status": phase1_playback_get.get("status"),
        "error": phase1_playback_get.get("error"),
        "sample": (
            {
                k: phase1_playback_get["body"].get(k)
                for k in ("paused", "seeking", "time", "speed")
                if isinstance(phase1_playback_get.get("body"), dict)
                and k in phase1_playback_get["body"]
            }
            if phase1_playback_get.get("ok")
            else None
        ),
    }
    result["snapshots"]["restorePhase1RenderGet"] = {
        "ok": phase1_render_get.get("ok"),
        "status": phase1_render_get.get("status"),
        "error": phase1_render_get.get("error"),
        "sample": (
            {
                k: phase1_render_get["body"].get(k)
                for k in RENDER_RESTORE_FIELDS
                if isinstance(phase1_render_get.get("body"), dict)
                and k in phase1_render_get["body"]
            }
            if phase1_render_get.get("ok")
            else None
        ),
    }
    if not phase1_playback_get.get("ok"):
        restore_errors.append(
            phase1_playback_get.get("error") or "phase1 playback restore GET failed"
        )
    if not phase1_render_get.get("ok"):
        restore_errors.append(
            phase1_render_get.get("error") or "phase1 render restore GET failed"
        )
    if phase1_playback_get.get("ok") and phase1_render_get.get("ok"):
        phase1_errors = _verify_restore_readback(
            original_playback={**dict(original_playback), "paused": True},
            original_render=original_render,
            playback_body=phase1_playback_get.get("body"),
            render_body=phase1_render_get.get("body"),
            require_exact_time=True,
            include_camera_position=originally_paused,
        )
        if phase1_errors:
            restore_errors.extend(f"phase1: {e}" for e in phase1_errors)
        result["snapshots"]["restorePhase1Proof"] = {
            "ok": not phase1_errors,
            "errors": list(phase1_errors),
            "requireExactTime": True,
            "includeCameraPosition": originally_paused,
        }

    # Phase 2: restore original paused/speed (still never time).
    playback_body = dict(restore_playback_body) if restore_playback_body else {}
    if not playback_body and "paused" in original_playback:
        playback_body = {"paused": original_playback.get("paused", True)}
        if "speed" in original_playback:
            playback_body["speed"] = original_playback["speed"]
    if "time" in playback_body:
        restore_errors.append("internal error: phase2 restore must not include time")
        playback_body = {k: v for k, v in playback_body.items() if k != "time"}
    # Arm before the POST: playback can resume while the request is in flight,
    # and that response latency must count toward the allowed clock advance.
    resume_mono: Optional[float] = (
        time.monotonic() if not originally_paused else None
    )
    playback_restore = transport(
        "POST",
        playback_url,
        body=playback_body or {"paused": True},
        timeout=timeout,
    )
    result["snapshots"]["restorePlayback"] = {
        "ok": playback_restore.get("ok"),
        "status": playback_restore.get("status"),
        "error": playback_restore.get("error"),
        "postedKeys": sorted(playback_body.keys()),
        "resumeMonoArmed": resume_mono is not None,
    }
    result["snapshots"]["restorePhase2PlaybackPost"] = result["snapshots"]["restorePlayback"]
    if not playback_restore.get("ok"):
        restore_errors.append(
            playback_restore.get("error") or "playback restore POST failed"
        )

    _settle(settle_delay)
    playback_get = transport("GET", playback_url, timeout=timeout)
    render_get = transport("GET", render_url, timeout=timeout)
    result["snapshots"]["restorePlaybackGet"] = {
        "ok": playback_get.get("ok"),
        "status": playback_get.get("status"),
        "error": playback_get.get("error"),
        "sample": (
            {
                k: playback_get["body"].get(k)
                for k in ("paused", "seeking", "time", "speed")
                if isinstance(playback_get.get("body"), dict) and k in playback_get["body"]
            }
            if playback_get.get("ok")
            else None
        ),
    }
    result["snapshots"]["restoreRenderGet"] = {
        "ok": render_get.get("ok"),
        "status": render_get.get("status"),
        "error": render_get.get("error"),
        "sample": (
            {
                k: render_get["body"].get(k)
                for k in RENDER_RESTORE_FIELDS
                if isinstance(render_get.get("body"), dict) and k in render_get["body"]
            }
            if render_get.get("ok")
            else None
        ),
    }
    if not playback_get.get("ok"):
        restore_errors.append(playback_get.get("error") or "playback restore GET failed")
    if not render_get.get("ok"):
        restore_errors.append(render_get.get("error") or "render restore GET failed")

    if playback_get.get("ok") and render_get.get("ok"):
        phase2_errors = _verify_restore_readback(
            original_playback=original_playback,
            original_render=original_render,
            playback_body=playback_get.get("body"),
            render_body=render_get.get("body"),
            require_exact_time=originally_paused,
            include_camera_position=originally_paused,
            resume_mono=resume_mono,
        )
        if phase2_errors:
            label = "phase2-paused" if originally_paused else "phase2-resumed"
            restore_errors.extend(f"{label}: {e}" for e in phase2_errors)
        result["snapshots"]["restorePhase2Proof"] = {
            "ok": not phase2_errors,
            "errors": list(phase2_errors),
            "requireExactTime": originally_paused,
            "includeCameraPosition": originally_paused,
            "resumeMono": resume_mono,
        }

    result["restoreSucceeded"] = not restore_errors
    result["restored"] = result["restoreSucceeded"]
    if restore_errors:
        prev = result.get("error")
        joined = "; ".join(restore_errors)
        result["error"] = f"{prev}; restore: {joined}" if prev else f"restore: {joined}"


def probe_selection(
    transport: Transport,
    base_url: str,
    selection_name: str,
    *,
    schema_names: set[str],
    timeout: float = DEFAULT_TIMEOUT,
    settle_delay: float = DEFAULT_SETTLE_DELAY,
    inject_failure_after_post: bool = False,
) -> dict[str, Any]:
    """Focus-mode select probe: snapshot → pause → focus → select → read → restore."""
    base = base_url.rstrip("/")
    result: dict[str, Any] = {
        "selectionNameRequested": selection_name,
        "fieldClassification": classify_selection_fields(schema_names),
        "fieldsTested": {
            "cameraMode": FOCUS_CAMERA_MODE,
            "selectionName": selection_name,
            "cameraAttached": True,
            "selectionOffset": dict(ZERO_OFFSET),
        },
        "outcome": "unsupported",
        "positionClaimAllowed": False,
        "positionCoverage": "none",
        "restored": False,
        "restoreAttempted": False,
        "restoreSucceeded": False,
        "error": None,
        "snapshots": {},
        "classification": None,
        "method": "focus_selection",
        "hardened": {
            "seek": False,
            "unpause": False,
            "cameraMode": FOCUS_CAMERA_MODE,
            "settleDelaySec": settle_delay,
        },
    }

    playback_url = f"{base}/replay/playback"
    render_url = f"{base}/replay/render"

    snap_playback = transport("GET", playback_url, timeout=timeout)
    snap_render = transport("GET", render_url, timeout=timeout)
    result["snapshots"]["playback"] = snap_playback
    result["snapshots"]["render"] = snap_render
    if not snap_playback.get("ok") or not snap_render.get("ok"):
        result["error"] = "failed to snapshot playback/render before selection probe"
        return result

    original_playback = dict(snap_playback.get("body") or {})
    original_render = dict(snap_render.get("body") or {})
    baseline_camera = original_render.get("cameraPosition")
    previous_selection = original_render.get("selectionName")
    restore_playback_body, restore_render_body = _restore_bodies(
        original_playback, original_render
    )

    try:
        result["snapshots"]["pause"] = ensure_paused_no_seek(
            transport, playback_url, timeout=timeout, settle_delay=settle_delay
        )
        result["snapshots"]["setFocus"] = set_camera_mode_focus(
            transport, render_url, timeout=timeout, settle_delay=settle_delay
        )
        steps = focus_select_target(
            transport,
            render_url,
            selection_name,
            timeout=timeout,
            settle_delay=settle_delay,
        )
        result["snapshots"]["focusSelect"] = steps
        if inject_failure_after_post:
            raise RuntimeError("injected failure after selection POST")

        read_body = steps["readback"].get("body") if steps["readback"].get("ok") else {}
        if not isinstance(read_body, dict):
            read_body = {}
        # Prefer treating #tag summoner posts as expected player identity.
        expected_id = None
        if "#" in selection_name or _player_identity_key(selection_name):
            # If the probe arg looks like a player id (has # or no spaces), expect it.
            if "#" in selection_name or " " not in selection_name:
                expected_id = selection_name.split("#", 1)[0].strip()
                # Champion internal names are also spaceless — only set expected when
                # arg contains # (definite summoner) or looks like riot id (has no
                # internal-champ heuristic). For champion args like Gnar, leave
                # expected_id None and rely on change-from-previous + canonicalize.
                if "#" not in selection_name and selection_name[:1].isupper():
                    # Likely champion / internal name probe — don't force identity.
                    expected_id = None
        classification = classify_focus_readback(
            selection_name,
            read_body,
            baseline_camera=baseline_camera,
            expected_player_identity=expected_id,
            previous_selection_name=previous_selection,
        )
        result["classification"] = classification
        result["outcome"] = classification["outcome"]
        result["positionClaimAllowed"] = classification["positionClaimAllowed"]
        result["positionCoverage"] = classification["positionCoverage"]
        result["note"] = (
            "Focus-mode selection with canonical nonempty selectionName and finite "
            "cameraPosition yields champion world coordinates. Top camera mode is "
            "not proof. Capture JSON is diagnostic only — not ingestible timeline "
            "JSONL (Replay API lacks participant HP / unknown-HP semantics)."
        )
    except Exception as exc:  # noqa: BLE001
        result["error"] = f"{type(exc).__name__}: {exc}"
        if result["outcome"] not in (
            "supported",
            "supported-but-coordinate-candidate",
            "candidate",
        ):
            result["outcome"] = "unsupported"
        result["positionCoverage"] = "none"
        result["positionClaimAllowed"] = False
    finally:
        _apply_restore(
            result,
            transport,
            playback_url=playback_url,
            render_url=render_url,
            restore_playback_body=restore_playback_body,
            restore_render_body=restore_render_body,
            original_playback=original_playback,
            original_render=original_render,
            timeout=timeout,
            settle_delay=settle_delay,
        )
    return result


def _team_id(raw: Any) -> int:
    if raw in (100, 200):
        return int(raw)
    if isinstance(raw, str):
        up = raw.upper()
        if up in ("ORDER", "BLUE", "TEAM1", "100"):
            return 100
        if up in ("CHAOS", "RED", "TEAM2", "200"):
            return 200
    return 100


# Riot liveclient `position` → Timeline role labels used by GameReview/unitToLoadout.
LIVECLIENT_POSITION_TO_ROLE = {
    "TOP": "Top",
    "JUNGLE": "Jungle",
    "MIDDLE": "Middle",
    "MID": "Middle",
    "BOTTOM": "Bottom",
    "BOT": "Bottom",
    "UTILITY": "Support",
    "SUPPORT": "Support",
}


def normalize_liveclient_role(raw: Any) -> str:
    """Map Riot liveclient position (TOP/JUNGLE/MIDDLE/BOTTOM/UTILITY) → Timeline roles."""
    if raw is None:
        return "NONE"
    text = str(raw).strip()
    if not text:
        return "NONE"
    mapped = LIVECLIENT_POSITION_TO_ROLE.get(text.upper())
    if mapped:
        return mapped
    # Already-normalized Timeline labels
    titled = {"Top", "Jungle", "Middle", "Bottom", "Support"}
    if text in titled:
        return text
    return "NONE"


def _items_from_player(player: Mapping[str, Any]) -> list[Any]:
    items = player.get("items")
    if isinstance(items, list):
        out = []
        for it in items:
            if isinstance(it, Mapping) and "itemID" in it:
                out.append(it.get("itemID"))
            else:
                out.append(it)
        return out
    out = []
    for i in range(7):
        key = f"item{i}"
        if key in player:
            out.append(player[key])
    return out


def _liveclient_identity_aliases(row: Mapping[str, Any]) -> set[str]:
    identity = rofl_metadata.stable_identity_from_row(row)
    aliases: set[str] = set()
    if identity.get("puuid"):
        aliases.add(f"puuid:{identity['puuid']}")
    riot_id = identity.get("riotId") or {}
    if riot_id.get("normalized"):
        aliases.add(f"riotid:{riot_id['normalized']}")
    return aliases


def _score_number(scores: Mapping[str, Any], keys: tuple[str, ...]) -> Optional[Any]:
    for key in keys:
        if key not in scores or scores.get(key) is None:
            continue
        value = scores.get(key)
        if isinstance(value, bool):
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(number) or number < 0:
            continue
        return int(number) if number.is_integer() else number
    return None


def liveclient_history_from_player(player: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize only score fields actually present in allgamedata."""
    scores = player.get("scores")
    if not isinstance(scores, Mapping):
        return {}
    source_keys: tuple[tuple[str, tuple[str, ...]], ...] = (
        ("kills", ("kills",)),
        ("deaths", ("deaths",)),
        ("assists", ("assists",)),
        # Live Client Data calls this creepScore. It is total CS, not lane CS.
        ("totalCreepScore", ("creepScore", "totalCreepScore")),
        ("visionScore", ("wardScore", "visionScore")),
    )
    history: dict[str, Any] = {}
    for output_key, candidates in source_keys:
        value = _score_number(scores, candidates)
        if value is not None:
            history[output_key] = value
    if not history:
        return {}
    source = "liveclient_allgamedata_scores"
    return {
        "history": history,
        "historyCoverage": {key: "known" for key in history},
        "historySources": {key: source for key in history},
        "historySource": source,
    }


def build_roster_from_liveclient(
    playerlist_body: Any, allgamedata_body: Any
) -> list[dict[str, Any]]:
    all_players: list[dict[str, Any]] = []
    all_by_alias: dict[str, list[int]] = {}
    by_champ: dict[str, list[int]] = {}
    if isinstance(allgamedata_body, Mapping):
        for p in allgamedata_body.get("allPlayers") or []:
            if not isinstance(p, Mapping):
                continue
            index = len(all_players)
            all_players.append(dict(p))
            for alias in _liveclient_identity_aliases(p):
                all_by_alias.setdefault(alias, []).append(index)
            champ = str(p.get("championName") or p.get("champion") or "")
            if champ:
                by_champ.setdefault(champ.casefold(), []).append(index)

    if isinstance(playerlist_body, list):
        players = playerlist_body
    elif isinstance(allgamedata_body, Mapping):
        players = all_players
    else:
        players = []

    rows: list[dict[str, Any]] = []
    for idx, raw in enumerate(players):
        if not isinstance(raw, Mapping):
            continue
        champ = str(raw.get("championName") or raw.get("champion") or "")
        matched_indexes = {
            candidate
            for alias in _liveclient_identity_aliases(raw)
            for candidate in all_by_alias.get(alias, [])
        }
        matched_index: Optional[int] = None
        if len(matched_indexes) == 1:
            matched_index = next(iter(matched_indexes))
        elif not matched_indexes:
            champion_matches = by_champ.get(champ.casefold()) or []
            if len(champion_matches) == 1:
                matched_index = champion_matches[0]
        merged = {k: v for k, v in raw.items() if v is not None}
        if matched_index is not None:
            # Dynamic values and scores must come from the same allgamedata
            # body whose gameData.gameTime was accepted by the caller.
            merged.update(
                {
                    k: v
                    for k, v in all_players[matched_index].items()
                    if v is not None
                }
            )
        team_raw = merged.get("team") or merged.get("teamID") or merged.get("teamId")
        summoner_name = str(
            merged.get("summonerName")
            or (
                f"{merged.get('riotIdGameName')}#{merged.get('riotIdTagLine')}"
                if merged.get("riotIdGameName") and merged.get("riotIdTagLine")
                else merged.get("riotIdGameName")
            )
            or merged.get("playerName")
            or ""
        ).strip()
        player_name = str(
            merged.get("riotIdGameName")
            or (
                summoner_name.split("#", 1)[0].strip()
                if summoner_name
                else ""
            )
            or merged.get("playerName")
            or ""
        ).strip()
        alive = True
        if "isDead" in merged:
            alive = not bool(merged.get("isDead"))
        elif merged.get("respawnTimer"):
            try:
                alive = float(merged.get("respawnTimer") or 0) <= 0
            except (TypeError, ValueError):
                alive = True
        level = merged.get("level")
        if level is None and isinstance(merged.get("championStats"), Mapping):
            level = merged["championStats"].get("level")
        internal = champion_internal_name(champ, merged)
        champion_identity = rofl_metadata.champion_identities(
            internal or champ,
            display_name=champ,
        )
        live_position = merged.get("position") or merged.get("role")
        riot_id_game_name = str(merged.get("riotIdGameName") or "").strip()
        riot_id_tag_line = str(merged.get("riotIdTagLine") or "").strip()
        row = {
            "participantID": int(merged.get("participantID") or idx + 1),
            "teamID": _team_id(team_raw),
            "championName": champion_identity.get("display") or champ,
            "championInternalName": champion_identity.get("asset") or internal,
            "championIdentity": champion_identity,
            "summonerName": summoner_name,
            "playerName": player_name,
            "riotIdGameName": riot_id_game_name or None,
            "riotIdTagLine": riot_id_tag_line or None,
            "puuid": merged.get("puuid") or merged.get("PUUID"),
            "expectedSelectionIdentity": player_name or summoner_name.split("#", 1)[0],
            "level": level,
            "items": _items_from_player(merged),
            "alive": alive,
            "liveclientPosition": live_position,
            "role": normalize_liveclient_role(live_position),
        }
        row.update(liveclient_history_from_player(merged))
        row["selectionKeys"] = selection_keys_for_roster_row(row)
        rows.append(row)
    return rows


def capture_current_positions(
    transport: Transport,
    base_url: str,
    *,
    timeout: float = DEFAULT_TIMEOUT,
    settle_delay: float = DEFAULT_SETTLE_DELAY,
    inject_failure_mid_capture: bool = False,
) -> dict[str, Any]:
    """Capture champion xz positions at one paused timestamp via focus selection.

    Selects each roster member by summonerName/player identity first (not spaced
    champion display names). Single diagnostic JSON — NOT JSONL / not ingest.
    hpCoverage is always none (Replay API lacks participant HP).
    """
    base = base_url.rstrip("/")
    playback_url = f"{base}/replay/playback"
    render_url = f"{base}/replay/render"
    result: dict[str, Any] = {
        "kind": "replay_api_focus_capture",
        "ok": False,
        "gameTimeMs": None,
        "playbackTimeSec": None,
        "roster": [],
        "participants": [],
        "repeatEvidence": None,
        "positionCoverage": "none",
        "hpCoverage": "none",
        "restoreAttempted": False,
        "restoreSucceeded": False,
        "restored": False,
        "error": None,
        "snapshots": {},
        "provenance": {
            "kind": "replay_api_focus_capture",
            "ingestible": False,
            "note": (
                "Proof/capture diagnostic data only — NOT ingestible timeline JSONL. "
                "Replay API lacks participant HP and canonical unknown-HP semantics "
                "are not yet implemented. Next bounded task: rfc461 unknown-HP + "
                "timeline capture. Downstream remains maknee-shaped events[]."
            ),
            "positionCoverage": "none",
            "hpCoverage": "none",
            "positionSource": POSITION_SOURCE_FOCUS,
            "selectionKeyPolicy": (
                "Primary: summonerName/player identity from liveclient playerlist. "
                "Fallback: champion internal name (TahmKench). Never rely on spaced "
                "display names (Tahm Kench) — they can silently retain the previous "
                "selection with a duplicate finite cameraPosition."
            ),
            "method": (
                "require already paused+seeking=false (no playback mutation) → "
                "cameraMode=focus → per player detach/select(identity)/attach/"
                "offset0 → GET render; require identity match + distinct + repeat; "
                "restore paused/speed only (never time) with GET verification"
            ),
        },
    }

    snap_playback = transport("GET", playback_url, timeout=timeout)
    snap_render = transport("GET", render_url, timeout=timeout)
    result["snapshots"]["playback"] = snap_playback
    result["snapshots"]["render"] = snap_render
    if not snap_playback.get("ok") or not snap_render.get("ok"):
        result["error"] = "failed to snapshot playback/render before capture"
        return result

    original_playback = dict(snap_playback.get("body") or {})
    original_render = dict(snap_render.get("body") or {})
    ready, ready_err = _playback_ready_for_capture(original_playback)
    if not ready:
        result["error"] = ready_err
        return result

    restore_playback_body, restore_render_body = _restore_bodies(
        original_playback, original_render
    )
    previous_selection = original_render.get("selectionName")
    playback_time = float(original_playback.get("time") or 0.0)
    result["playbackTimeSec"] = playback_time
    result["gameTimeMs"] = int(round(playback_time * 1000))

    try:
        # Do not POST pause/seek — capture requires already-paused state above.
        pl = transport("GET", f"{base}/liveclientdata/playerlist", timeout=timeout)
        ag = transport("GET", f"{base}/liveclientdata/allgamedata", timeout=timeout)
        result["snapshots"]["playerlist"] = {
            "ok": pl.get("ok"),
            "status": pl.get("status"),
            "error": pl.get("error"),
            "count": len(pl["body"]) if isinstance(pl.get("body"), list) else None,
        }
        result["snapshots"]["allgamedata"] = {
            "ok": ag.get("ok"),
            "status": ag.get("status"),
            "error": ag.get("error"),
            "bodyKeys": (
                sorted(ag["body"].keys())
                if isinstance(ag.get("body"), dict)
                else None
            ),
        }
        roster = build_roster_from_liveclient(pl.get("body"), ag.get("body"))
        result["roster"] = roster
        if not roster:
            result["error"] = "empty roster from liveclientdata"
            return result

        result["snapshots"]["setFocus"] = set_camera_mode_focus(
            transport, render_url, timeout=timeout, settle_delay=settle_delay
        )

        participants: list[dict[str, Any]] = []
        positions: list[tuple[float, float]] = []
        first_row: Optional[dict[str, Any]] = None
        first_pos = None
        first_key = None

        for row in roster:
            if not row.get("selectionKeys"):
                result["error"] = (
                    f"no valid selection keys for participant {row.get('participantID')}"
                )
                result["participants"] = participants
                return result
            if first_row is None:
                first_row = dict(row)

            steps, classification, used_key = focus_select_roster_member(
                transport,
                render_url,
                row,
                timeout=timeout,
                settle_delay=settle_delay,
                previous_selection_name=previous_selection,
            )
            if inject_failure_mid_capture and first_row is not None and row.get(
                "participantID"
            ) == first_row.get("participantID"):
                raise RuntimeError("injected failure mid capture")

            read_body = (
                steps["readback"].get("body") if steps.get("readback", {}).get("ok") else {}
            )
            if not isinstance(read_body, dict):
                read_body = {}

            if not classification["coordinateProven"]:
                result["error"] = (
                    f"focus coordinate unsupported for {row.get('playerName') or row.get('championName')}: "
                    f"outcome={classification['outcome']} "
                    f"stale={classification.get('staleRetained')} "
                    f"key={used_key!r} "
                    f"canonical={read_body.get('selectionName')!r}"
                )
                result["participants"] = participants
                return result

            pos = read_body["cameraPosition"]
            xz = _xz_position(pos)
            positions.append((xz["x"], xz["z"]))
            if first_pos is None:
                first_pos = dict(pos)
                first_key = used_key
            previous_selection = read_body.get("selectionName")
            participants.append(
                {
                    **row,
                    "selectionKeyUsed": used_key,
                    "position": xz,
                    "positionSource": POSITION_SOURCE_FOCUS,
                    "selectionNameCanonical": read_body.get("selectionName"),
                    "cameraPosition": {
                        "x": float(pos["x"]),
                        "y": float(pos["y"]),
                        "z": float(pos["z"]),
                    },
                }
            )

        unique = {(round(x, 3), round(z, 3)) for x, z in positions}
        if len(unique) < 2 and len(positions) >= 2:
            result["error"] = (
                "positions not distinct across players — refusing coordinate claim"
            )
            result["participants"] = participants
            return result
        if len(positions) >= 2 and len(unique) < len(positions):
            result["error"] = (
                f"duplicate coordinates among {len(positions)} players "
                f"({len(unique)} distinct) — likely stale selection"
            )
            result["participants"] = participants
            return result

        repeat_evidence = None
        if first_row and first_pos is not None and first_key:
            steps, rep_class, rep_key = focus_select_roster_member(
                transport,
                render_url,
                first_row,
                timeout=timeout,
                settle_delay=settle_delay,
                previous_selection_name=previous_selection,
            )
            rb = steps["readback"].get("body") if steps.get("readback", {}).get("ok") else {}
            if not isinstance(rb, dict):
                rb = {}
            rep_pos = rb.get("cameraPosition")
            match = bool(
                rep_class["coordinateProven"]
                and _vec_approx_equal(first_pos, rep_pos, tol=1e-2)
            )
            repeat_evidence = {
                "championName": first_row.get("championName"),
                "playerName": first_row.get("playerName"),
                "selectionKeyUsed": rep_key,
                "matched": match,
                "firstCameraPosition": first_pos,
                "repeatCameraPosition": rep_pos,
                "classification": {
                    k: rep_class[k]
                    for k in (
                        "outcome",
                        "selectionAccepted",
                        "coordinateProven",
                        "identityMatched",
                        "focusMode",
                    )
                    if k in rep_class
                },
            }
            if not match:
                result["error"] = "repeat selection did not return the same coordinate"
                result["participants"] = participants
                result["repeatEvidence"] = repeat_evidence
                return result

        result["participants"] = participants
        result["repeatEvidence"] = repeat_evidence
        result["ok"] = True
        result["positionCoverage"] = POSITION_SOURCE_FOCUS
        result["provenance"]["positionCoverage"] = POSITION_SOURCE_FOCUS
        result["provenance"]["hpCoverage"] = "none"
    except Exception as exc:  # noqa: BLE001
        result["error"] = f"{type(exc).__name__}: {exc}"
        result["ok"] = False
        result["positionCoverage"] = "none"
        result["provenance"]["positionCoverage"] = "none"
    finally:
        if "original_playback" in locals() and result.get("restoreAttempted") is False:
            # Only restore if we may have mutated render (passed readiness gate).
            if ready:
                _apply_restore(
                    result,
                    transport,
                    playback_url=playback_url,
                    render_url=render_url,
                    restore_playback_body=restore_playback_body,
                    restore_render_body=restore_render_body,
                    original_playback=original_playback,
                    original_render=original_render,
                    timeout=timeout,
                    settle_delay=settle_delay,
                )
    return result


def probe_endpoints(
    transport: Transport,
    base_url: str,
    *,
    timeout: float = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    base = base_url.rstrip("/")
    endpoints: dict[str, Any] = {}
    any_ok = False
    openapi_body = None
    for key, path in ENDPOINTS:
        url = f"{base}{path}"
        resp = transport("GET", url, timeout=timeout)
        entry: dict[str, Any] = {
            "path": path,
            "ok": bool(resp.get("ok")),
            "status": resp.get("status"),
            "error": resp.get("error"),
        }
        body = resp.get("body")
        if resp.get("ok"):
            any_ok = True
            if key == "openapi":
                openapi_body = body
                entry["schemaPropertyCount"] = len(schema_property_names(openapi_body))
            elif key == "liveclient_playerlist":
                entry["count"] = len(body) if isinstance(body, list) else None
            elif key == "liveclient_allgamedata" and isinstance(body, Mapping):
                game_data = body.get("gameData") if isinstance(body.get("gameData"), Mapping) else {}
                entry["summary"] = {
                    "bodyKeys": sorted(body.keys()),
                    "allPlayersCount": len(body.get("allPlayers") or []),
                    "gameData": {
                        k: game_data.get(k)
                        for k in ("gameTime", "gameMode", "mapName", "mapNumber")
                        if k in game_data
                    },
                }
            elif key in ("playback", "render", "game", "sequence") and isinstance(
                body, Mapping
            ):
                entry["bodyKeys"] = sorted(body.keys())
                # Compact field samples only — never dump liveclient roster payloads.
                if key == "playback":
                    entry["sample"] = {
                        k: body.get(k)
                        for k in ("paused", "seeking", "time", "speed", "length")
                        if k in body
                    }
                elif key == "game":
                    entry["sample"] = {
                        k: body.get(k) for k in ("processID",) if k in body
                    }
                elif key == "render":
                    entry["sample"] = {
                        k: body.get(k)
                        for k in ("cameraMode", "cameraAttached", "selectionName")
                        if k in body
                    }
        endpoints[key] = entry
    return {
        "apiReachable": any_ok,
        "endpoints": endpoints,
        "openapi": openapi_body,
    }


def infer_hp_coverage(endpoints: Mapping[str, Any]) -> str:
    # Capture/proof path always reports hpCoverage none at capture top-level;
    # status may note liveclient availability separately.
    lcd = endpoints.get("liveclient_allgamedata") or {}
    if lcd.get("ok"):
        return "liveclientdata_possible"
    if (endpoints.get("game") or {}).get("ok") or (
        endpoints.get("playback") or {}
    ).get("ok"):
        return "unknown_replay_session"
    return "none"


def build_status_report(
    *,
    rofl_path: Path,
    app_path: Path,
    base_url: str,
    transport: Transport,
    timeout: float = DEFAULT_TIMEOUT,
    settle_delay: float = DEFAULT_SETTLE_DELAY,
    probe_selection_name: Optional[str] = None,
    capture_current: bool = False,
    capture_out: Optional[Path] = None,
    schema_out: Optional[Path] = None,
) -> dict[str, Any]:
    rofl = read_rofl_build(rofl_path)
    client = read_app_build(app_path)
    rofl_ver = rofl.get("version") or ""
    client_ver = client.get("version") or ""
    match = (
        builds_match(str(rofl_ver), str(client_ver))
        if rofl_ver and client_ver
        else False
    )

    ep = probe_endpoints(transport, base_url, timeout=timeout)
    schema_names = (
        schema_property_names(ep.get("openapi")) if ep.get("openapi") else set()
    )

    if schema_out is not None:
        if ep.get("openapi") is not None:
            schema_out.parent.mkdir(parents=True, exist_ok=True)
            schema_out.write_text(
                json.dumps(ep["openapi"], indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            schema_saved = str(schema_out)
            schema_error = None
        else:
            schema_saved = None
            schema_error = "OpenAPI unreachable; schema not written"
    else:
        schema_saved = None
        schema_error = None

    selection = None
    if probe_selection_name:
        if not ep["apiReachable"]:
            selection = {
                "error": "API unreachable; --probe-selection skipped",
                "outcome": "unsupported",
                "positionCoverage": "none",
                "restored": False,
                "restoreAttempted": False,
                "restoreSucceeded": False,
            }
        else:
            selection = probe_selection(
                transport,
                base_url,
                probe_selection_name,
                schema_names=schema_names,
                timeout=timeout,
                settle_delay=settle_delay,
            )

    capture = None
    if capture_current:
        if not ep["apiReachable"]:
            capture = {
                "kind": "replay_api_focus_capture",
                "ok": False,
                "error": "API unreachable; --capture-current skipped",
                "positionCoverage": "none",
                "hpCoverage": "none",
                "restoreAttempted": False,
                "restoreSucceeded": False,
                "provenance": {
                    "ingestible": False,
                    "hpCoverage": "none",
                    "positionCoverage": "none",
                },
            }
        else:
            capture = capture_current_positions(
                transport,
                base_url,
                timeout=timeout,
                settle_delay=settle_delay,
            )
            if capture_out is not None:
                capture_out.parent.mkdir(parents=True, exist_ok=True)
                capture_out.write_text(
                    json.dumps(capture, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
                capture["captureOut"] = str(capture_out)

    position_coverage = "none"
    if capture and capture.get("ok"):
        position_coverage = capture.get("positionCoverage") or POSITION_SOURCE_FOCUS
    elif selection and selection.get("positionCoverage") == POSITION_SOURCE_FOCUS:
        position_coverage = POSITION_SOURCE_FOCUS

    # Status hpCoverage: capture proof always documents none for HP; status may
    # still note liveclient availability for separate debugging.
    hp_coverage = "none" if capture else infer_hp_coverage(ep["endpoints"])

    report: dict[str, Any] = {
        "apiReachable": ep["apiReachable"],
        "baseUrl": base_url,
        "rofl": {
            "path": rofl.get("path"),
            "format": rofl.get("format"),
            "version": rofl.get("version"),
            "normalizedBuild": normalize_build(str(rofl_ver)),
            "size": rofl.get("size"),
            "parser": rofl.get("parser"),
            "error": rofl.get("error"),
        },
        "client": {
            "path": client.get("path"),
            "version": client.get("version"),
            "normalizedBuild": normalize_build(str(client_ver)),
            "CFBundleVersion": client.get("CFBundleVersion"),
            "FileVersion": client.get("FileVersion"),
            "error": client.get("error"),
        },
        "buildMatch": match,
        "buildMatchDetail": "exact" if match else "mismatch_or_incomplete",
        "endpoints": ep["endpoints"],
        "positionCoverage": position_coverage,
        "hpCoverage": hp_coverage,
        "enableReplayApi": ENABLE_REPLAY_API_INSTRUCTIONS,
        "schemaOut": schema_saved,
        "schemaOutError": schema_error,
        "selectionProbe": selection,
        "capture": capture,
        "provenance": {
            "kind": "official_replay_api_probe",
            "claim": (
                "playback_access + focus-mode coordinate primitive — not ROFL "
                "decryption; capture is not ingestible timeline JSONL yet"
            ),
            "downstream": (
                "future maknee-shaped events[] → maknee_packets_to_jsonl.py "
                "→ jsonl_to_timeline.py"
            ),
            "selectionStatus": (
                "PROVEN: select by summonerName/player identity (e.g. "
                "nhUwUmi#glhf → nhUwUmi). Spaced champion display names "
                "(Tahm Kench) can silently retain the previous selection — "
                "invalid even if cameraPosition is finite. Champion internal "
                "name (TahmKench) is fallback only."
            ),
            "coordinateStatus": (
                "PROVEN in cameraMode=focus with identity-valid selection + "
                "cameraAttached + zero selectionOffset at a paused timestamp: "
                "distinct finite cameraPosition per player; reselect repeats. "
                "Top camera mode is NOT proof. Stale/spaced display-name "
                "selection is NOT proof."
            ),
            "positionCoveragePolicy": (
                f"'{POSITION_SOURCE_FOCUS}' only after focus-mode canonical "
                "selection + finite position; otherwise 'none'"
            ),
            "capturePolicy": (
                "--capture-current emits one diagnostic JSON object with "
                "hpCoverage always 'none' (no participant HP on Replay API). "
                "Not an ingest contract until unknown-HP rfc461 semantics exist."
            ),
            "macOSStability": (
                "No seek, no unpause for capture (must already be paused + "
                "seeking=false). Restore posts paused/speed only — never time — "
                "and GET-verifies seeking/time/render fields. Avoid rapid "
                "seek/mode thrash."
            ),
        },
    }
    return report


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description=(
            "Probe local Riot Replay API feasibility vs a ROFL build "
            "(playback access + focus-mode coordinates, not decryption)."
        )
    )
    ap.add_argument("--rofl", type=Path, default=DEFAULT_ROFL)
    ap.add_argument("--app", type=Path, default=DEFAULT_APP)
    ap.add_argument("--base-url", default=DEFAULT_BASE)
    ap.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    ap.add_argument(
        "--settle-delay",
        type=float,
        default=DEFAULT_SETTLE_DELAY,
        help=f"Settle delay seconds (default {DEFAULT_SETTLE_DELAY}; 0 in tests)",
    )
    ap.add_argument(
        "--require-api",
        action="store_true",
        help="Exit nonzero when apiReachable is false",
    )
    ap.add_argument(
        "--probe-selection",
        metavar="NAME",
        default=None,
        help=(
            "Focus-mode selection probe for one champion: pause (no seek), "
            "cameraMode=focus, select/attach/offset0, classify coords, restore"
        ),
    )
    ap.add_argument(
        "--capture-current",
        action="store_true",
        help=(
            "Capture all champion xz positions at the current paused timestamp "
            "(diagnostic JSON only; not timeline JSONL)"
        ),
    )
    ap.add_argument(
        "--capture-out",
        type=Path,
        default=None,
        help="Optional path for --capture-current diagnostic JSON",
    )
    ap.add_argument("--schema-out", type=Path, default=None)
    ap.add_argument("--json-out", type=Path, default=None)
    return ap.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    if not is_loopback_url(args.base_url):
        print(
            json.dumps(
                {
                    "error": (
                        f"refusing non-loopback base URL {args.base_url!r}; "
                        "self-signed TLS bypass is loopback-only"
                    ),
                    "apiReachable": False,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 2

    if not args.rofl.is_file():
        print(
            json.dumps(
                {"error": f"ROFL not found: {args.rofl}", "apiReachable": False},
                indent=2,
                sort_keys=True,
            )
        )
        return 2

    report = build_status_report(
        rofl_path=args.rofl,
        app_path=args.app,
        base_url=args.base_url,
        transport=default_http_transport,
        timeout=args.timeout,
        settle_delay=args.settle_delay,
        probe_selection_name=args.probe_selection,
        capture_current=args.capture_current,
        capture_out=args.capture_out,
        schema_out=args.schema_out,
    )

    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    sys.stdout.write(text)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(text, encoding="utf-8")

    if args.require_api and not report["apiReachable"]:
        return 1

    selection = report.get("selectionProbe") or {}
    if args.probe_selection and selection.get("restoreAttempted") and not selection.get(
        "restoreSucceeded"
    ):
        return 3

    capture = report.get("capture") or {}
    if args.capture_current:
        if capture.get("restoreAttempted") and not capture.get("restoreSucceeded"):
            return 3
        if not capture.get("ok"):
            return 4

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
