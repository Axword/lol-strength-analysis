#!/usr/bin/env python3
"""Shared ROFL2 metadata, match identity, and roster normalization helpers.

This module is stdlib-only and intentionally stops at the trailing metadata
layer. Packet extraction/decompression remains in ``rofl2_probe.py``.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import struct
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence


ROFL2_MAGIC = b"RIOT\x02\x00"
FILENAME_RE = re.compile(r"^(?P<platform>[A-Za-z0-9]+)-(?P<match>\d{7,})$")


class RoflMetadataError(ValueError):
    """ROFL metadata or identity is malformed/incomplete."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_filename_identity(path: Path, *, required: bool = True) -> dict[str, Any]:
    match = FILENAME_RE.fullmatch(path.stem)
    if match is None:
        if required:
            raise RoflMetadataError(
                "ROFL filename must be <platform>-<matchCode>.rofl "
                f"(got {path.name!r})"
            )
        return {"platformId": None, "matchCode": None, "gameId": None}
    match_code = match.group("match")
    return {
        "platformId": match.group("platform").upper(),
        "matchCode": match_code,
        "gameId": int(match_code),
    }


def parse_rofl2_metadata_bytes(data: bytes) -> dict[str, Any]:
    if len(data) < 32 or data[:6] != ROFL2_MAGIC:
        raise RoflMetadataError(f"not ROFL2 (magic={data[:6]!r})")
    version_len = data[14]
    version_start = 15
    version_end = version_start + version_len
    if version_end + 16 > len(data):
        raise RoflMetadataError("truncated ROFL2 version/header")
    version = data[version_start:version_end].decode("ascii", errors="strict")
    metadata_len = struct.unpack_from("<I", data, len(data) - 4)[0]
    metadata_start = len(data) - 4 - metadata_len
    if metadata_len <= 0 or metadata_start < version_end + 16:
        raise RoflMetadataError(
            f"invalid trailing metadata length {metadata_len}"
        )
    try:
        metadata = json.loads(data[metadata_start : len(data) - 4])
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RoflMetadataError(f"invalid trailing ROFL metadata JSON: {exc}") from exc
    if not isinstance(metadata, dict):
        raise RoflMetadataError("trailing ROFL metadata must be an object")
    return {
        "version": version,
        "versionLength": version_len,
        "headerOffset": version_end,
        "headerU32s": list(struct.unpack_from("<IIII", data, version_end)),
        "metadataStart": metadata_start,
        "metadataLength": metadata_len,
        "metadata": metadata,
    }


def _stats_players(metadata: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw = metadata.get("statsJson")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RoflMetadataError(f"invalid statsJson: {exc}") from exc
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise RoflMetadataError("statsJson must be a JSON array")
    return [dict(row) for row in raw if isinstance(row, Mapping)]


def _text(value: Any) -> str:
    return str(value or "").strip()


def _first_text(row: Mapping[str, Any], keys: Sequence[str]) -> str:
    for key in keys:
        value = _text(row.get(key))
        if value:
            return value
    return ""


def normalize_team_id(value: Any) -> int:
    text = _text(value).upper()
    if text in {"100", "ORDER", "BLUE"}:
        return 100
    if text in {"200", "CHAOS", "RED"}:
        return 200
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def normalize_riot_id(game_name: Any, tag_line: Any) -> dict[str, Optional[str]]:
    game = _text(game_name)
    tag = _text(tag_line)
    full = f"{game}#{tag}" if game and tag else None
    return {
        "gameName": game or None,
        "tagLine": tag or None,
        "full": full,
        "normalized": full.casefold() if full else None,
    }


def riot_id_from_row(row: Mapping[str, Any]) -> dict[str, Optional[str]]:
    game = _first_text(
        row,
        (
            "RIOT_ID_GAME_NAME",
            "riotIdGameName",
            "gameName",
            "playerName",
        ),
    )
    tag = _first_text(
        row,
        (
            "RIOT_ID_TAG_LINE",
            "riotIdTagLine",
            "tagLine",
        ),
    )
    if (not game or not tag) and "#" in _text(row.get("summonerName")):
        summoner_game, summoner_tag = _text(row.get("summonerName")).split("#", 1)
        game = game or summoner_game.strip()
        tag = tag or summoner_tag.strip()
    return normalize_riot_id(game, tag)


def champion_identities(
    raw_name: Any,
    *,
    display_name: Any = None,
    available_assets: Optional[Sequence[str]] = None,
) -> dict[str, Any]:
    """Separate source, display, asset, and combat-model champion identities.

    ``available_assets`` may be a patch-matched Data Dragon/asset key catalog.
    When supplied, its canonical spelling wins and ``assetResolved`` reflects
    whether the replay identity is present. Without a catalog the normalized
    asset key is retained but availability is explicitly unverified.
    """
    raw = _text(raw_name)
    source_display = _text(display_name)
    compact = raw.replace(" ", "")
    lower = compact.casefold()
    if lower in {"wukong", "monkeyking"}:
        display = "Wukong"
        asset_candidate = "MonkeyKing"
        model = "MonkeyKing"
        model_resolved = True
    elif lower == "zaahen":
        display = "Zaahen"
        asset_candidate = "Zaahen"
        # Zaahen is a real champion. A missing combat implementation must stay
        # unresolved, never alias to Wukong or a zero-damage generated model.
        model = None
        model_resolved = False
    else:
        display = source_display or raw or None
        asset_candidate = compact or None
        model = compact or None
        model_resolved = bool(model)

    asset = asset_candidate
    asset_resolved: Optional[bool] = None
    if available_assets is not None and asset_candidate:
        by_key = {
            str(candidate).replace(" ", "").casefold(): str(candidate)
            for candidate in available_assets
            if str(candidate).strip()
        }
        matched = by_key.get(asset_candidate.casefold())
        asset_resolved = matched is not None
        if matched is not None:
            asset = matched
    return {
        "raw": raw or None,
        "display": display,
        "asset": asset,
        "model": model,
        "rawResolved": bool(raw),
        "displayResolved": bool(display),
        "assetResolved": asset_resolved,
        "assetResolution": (
            "patch_catalog_match"
            if asset_resolved is True
            else "patch_catalog_missing"
            if asset_resolved is False
            else "normalized_unverified"
        ),
        "modelResolved": model_resolved,
        "modelResolution": (
            "normalized_identity"
            if model_resolved
            else "unresolved_no_zero_damage_fallback"
        ),
        # Backwards-compatible summary bit means the source identity was
        # normalized, not that a combat model exists.
        "resolved": bool(raw and display and asset),
    }


def stable_identity_from_row(row: Mapping[str, Any]) -> dict[str, Any]:
    puuid = _first_text(row, ("PUUID", "puuid"))
    riot_id = riot_id_from_row(row)
    if puuid:
        kind = "puuid"
        value = puuid
        key = f"puuid:{puuid}"
    elif riot_id["full"]:
        kind = "riotId"
        value = riot_id["full"]
        key = f"riotid:{riot_id['normalized']}"
    else:
        kind = "missing"
        value = None
        key = None
    return {
        "kind": kind,
        "value": value,
        "key": key,
        "puuid": puuid or None,
        "riotId": riot_id,
        "stable": key is not None,
    }


def participant_from_stats(row: Mapping[str, Any], source_index: int) -> dict[str, Any]:
    identity = stable_identity_from_row(row)
    champion = champion_identities(
        _first_text(row, ("SKIN", "championName", "champion"))
    )
    team_id = normalize_team_id(row.get("TEAM") or row.get("teamID") or row.get("team"))
    return {
        "sourceRecordIndex": source_index,
        "teamId": team_id,
        "sourceIdentity": identity,
        "puuid": identity["puuid"],
        "riotId": identity["riotId"],
        "champion": champion,
        "role": _first_text(
            row,
            ("TEAM_POSITION", "INDIVIDUAL_POSITION", "position", "role"),
        )
        or None,
    }


def _optional_number(
    row: Mapping[str, Any],
    keys: Sequence[str],
) -> Optional[Any]:
    for key in keys:
        if key not in row or row.get(key) is None:
            continue
        value = row.get(key)
        if isinstance(value, bool):
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(number):
            continue
        return int(number) if number.is_integer() else number
    return None


def post_game_summary(players: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Sanitized, explicitly static subset of trailing ``statsJson``."""
    stat_fields: tuple[tuple[str, tuple[str, ...]], ...] = (
        ("kills", ("CHAMPIONS_KILLED", "kills")),
        ("deaths", ("NUM_DEATHS", "deaths")),
        ("assists", ("ASSISTS", "assists")),
        ("minionsKilled", ("MINIONS_KILLED", "minionsKilled")),
        (
            "neutralMinionsKilled",
            ("NEUTRAL_MINIONS_KILLED", "neutralMinionsKilled"),
        ),
        ("visionScore", ("VISION_SCORE", "visionScore")),
        ("goldEarned", ("GOLD_EARNED", "goldEarned")),
        (
            "damageToChampions",
            ("TOTAL_DAMAGE_DEALT_TO_CHAMPIONS", "damageToChampions"),
        ),
        (
            "damageTaken",
            ("TOTAL_DAMAGE_TAKEN", "damageTaken"),
        ),
    )
    participants: list[dict[str, Any]] = []
    for index, player in enumerate(players):
        identity = stable_identity_from_row(player)
        final_stats: dict[str, Any] = {}
        for output_key, source_keys in stat_fields:
            value = _optional_number(player, source_keys)
            if value is not None:
                final_stats[output_key] = value
        participants.append(
            {
                "sourceRecordIndex": index,
                "sourceIdentity": identity,
                "champion": champion_identities(
                    _first_text(player, ("SKIN", "championName", "champion"))
                ),
                "finalStats": final_stats,
            }
        )
    participants.sort(
        key=lambda participant: (
            str((participant.get("sourceIdentity") or {}).get("key") or ""),
            int(participant.get("sourceRecordIndex") or 0),
        )
    )
    return {
        "source": "rofl_metadata_statsJson",
        "scope": "end_game_static",
        "scrubbableFrameHistory": False,
        "notes": (
            "Trailing ROFL statsJson is an end-game summary only and is never "
            "copied into sampled rfc461 frame history."
        ),
        "participants": participants,
    }


def _roster_hash(participants: Sequence[Mapping[str, Any]]) -> str:
    contract = [
        {
            "identity": (p.get("sourceIdentity") or {}).get("key"),
            "teamId": p.get("teamId"),
            "championAsset": (p.get("champion") or {}).get("asset"),
        }
        for p in participants
    ]
    encoded = json.dumps(
        contract,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def patch_from_build(version: str) -> Optional[str]:
    parts = [part for part in str(version or "").split(".") if part]
    return ".".join(parts[:2]) if len(parts) >= 2 else None


def inspect_rofl_metadata(path: Path) -> dict[str, Any]:
    path = path.expanduser().resolve()
    if not path.is_file():
        raise RoflMetadataError(f"ROFL file not found: {path}")
    if path.suffix.casefold() != ".rofl":
        raise RoflMetadataError(f"expected .rofl file, got {path.name!r}")
    filename_identity = parse_filename_identity(path)
    data = path.read_bytes()
    parsed = parse_rofl2_metadata_bytes(data)
    metadata = parsed["metadata"]
    metadata_platform = _first_text(
        metadata,
        ("platformId", "platformID", "platform"),
    ).upper()
    if (
        metadata_platform
        and metadata_platform != filename_identity["platformId"]
    ):
        raise RoflMetadataError(
            "ROFL filename/metadata platform mismatch "
            f"({filename_identity['platformId']} != {metadata_platform})"
        )
    metadata_game_id = _first_text(
        metadata,
        ("gameId", "gameID", "matchId", "matchID"),
    )
    if metadata_game_id and metadata_game_id != filename_identity["matchCode"]:
        raise RoflMetadataError(
            "ROFL filename/metadata match code mismatch "
            f"({filename_identity['matchCode']} != {metadata_game_id})"
        )
    players = _stats_players(metadata)
    participants = [
        participant_from_stats(player, index)
        for index, player in enumerate(players)
    ]
    participants.sort(
        key=lambda participant: (
            int(participant.get("teamId") or 0),
            str((participant.get("sourceIdentity") or {}).get("key") or ""),
            str((participant.get("champion") or {}).get("asset") or ""),
            int(participant.get("sourceRecordIndex") or 0),
        )
    )
    stable_keys = [
        (participant.get("sourceIdentity") or {}).get("key")
        for participant in participants
    ]
    stable_complete = (
        len(participants) == 10
        and all(stable_keys)
        and len(set(stable_keys)) == len(stable_keys)
    )
    try:
        duration_ms = int(metadata.get("gameLength"))
    except (TypeError, ValueError):
        duration_ms = 0
    if duration_ms <= 0:
        raise RoflMetadataError(
            f"ROFL metadata gameLength missing/invalid: {metadata.get('gameLength')!r}"
        )

    return {
        "format": "ROFL2",
        "formatVersion": 2,
        "platformId": filename_identity["platformId"],
        "matchCode": filename_identity["matchCode"],
        "gameId": filename_identity["gameId"],
        "basename": path.name,
        "sizeBytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "build": parsed["version"],
        "patch": patch_from_build(parsed["version"]),
        "durationMs": duration_ms,
        "lastGameChunkId": metadata.get("lastGameChunkId"),
        "lastKeyFrameId": metadata.get("lastKeyFrameId"),
        "participants": participants,
        "postGameSummary": post_game_summary(players),
        "rosterHash": _roster_hash(participants),
        "rosterCount": len(participants),
        "stableIdentityComplete": stable_complete,
        "missingStableIdentityCount": sum(1 for key in stable_keys if not key),
    }
