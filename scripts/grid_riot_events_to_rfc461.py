#!/usr/bin/env python3
"""
Normalize GRID Riot live-stats JSONL (``events_*_*_riot.jsonl``) → research rfc461.

GRID File Download ``events-riot-game-N`` is already native rfc461 / FUR live-stats
shape (dense ~1 Hz ``stats_update``, kills, skills, wards, …) with real
``platformID`` + ``gameID``. This adapter:

- prepends honest ``rofl_coverage`` provenance (``sourceKind=grid_riot_livestats``)
- annotates participant rows with source markers when fields are present
- leaves HP / combat / ability ranks unknown when fields are missing or incomplete
- never sets ``productEligible`` / ``calculatorReady`` (research path only)
- extracts a rename hint: ``replay_riot_<seriesId>_N.rofl`` → ``<PLATFORM>-<gameID>.rofl``
  only when both platformID and gameID are present (never guessed)

Join roster on PUUID / full Riot ID — never participant order.

Usage:
  python3 scripts/grid_riot_events_to_rfc461.py \\
    --input artifacts/pro-grid/events_2970110_1_riot.jsonl \\
    --out artifacts/pro-grid/2970110/events.riot.rfc461.research.jsonl \\
    --summary artifacts/pro-grid/2970110/riot.summary.json \\
    --join-rofl artifacts/pro-grid/replay_riot_2970110_1.rofl

  # Slim working copy (preferred for local analysis; drops transport fluff):
  python3 scripts/grid_riot_events_to_rfc461.py \\
    --input artifacts/pro-grid/events_2970110_1_riot.jsonl \\
    --sqlite artifacts/pro-grid/2970110/timeline.slim.sqlite \\
    --series-id 2970110
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, Iterator, List, Mapping, Optional, Sequence, Tuple

import rfc461_emit

SQLITE_SCHEMA_VERSION = "pro-grid-riot-slim-v2"

# Discrete event types worth keeping in the slim DB (skip champ_select / ward spam / etc.).
SLIM_EVENT_SCHEMAS = frozenset(
    {
        "champion_kill",
        "champion_kill_special",
        "skill_level_up",
        "skill_used",
        "building_destroyed",
        "epic_monster_kill",
        "epic_monster_spawn",
        "game_end",
        "item_purchased",
        "item_sold",
        "item_destroyed",
        "summoner_spell_used",
        "turret_plate_destroyed",
    }
)

SOURCE = "grid_riot_livestats"
SOURCE_KIND = "grid_riot_livestats"
HEALTH_SOURCE = "grid_riot_livestats"
POSITION_SOURCE = "grid_riot_livestats"
COMBAT_STATS_SOURCE = "grid_riot_livestats"
ABILITY_RANKS_SOURCE = "grid_riot_livestats"
UNAVAILABLE = "unavailable"

COMBAT_FIELDS = (
    "attackDamage",
    "abilityPower",
    "armor",
    "magicResist",
    "attackSpeed",
)
ABILITY_LEVEL_FIELDS = (
    "ability1Level",
    "ability2Level",
    "ability3Level",
    "ability4Level",
)

# Transport / GRID envelope keys kept for research dumps but not required.
TRANSPORT_KEYS = frozenset(
    {
        "rfc001Scope",
        "rfc190Scope",
        "rfc460Hostname",
        "rfc460Timestamp",
        "repeater_timestamp",
        "sequenceIndex",
        "source_type",
        "generationID",
        "parentGameID",
        "rootGameID",
        "playbackID",
        "stageID",
        "path",
    }
)


def _iter_jsonl_rows(path: Path) -> Iterator[dict]:
    path = Path(path)
    with path.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            text = line.strip()
            if not text:
                continue
            try:
                row = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_no}: invalid JSON: {exc}") from exc
            if not isinstance(row, dict):
                raise ValueError(f"{path}:{line_no}: expected object, got {type(row)}")
            yield row


def full_riot_id(player: Mapping[str, Any]) -> str:
    """Build ``name#tag`` from riotId object or flat fields; empty if incomplete."""
    riot = player.get("riotId")
    if isinstance(riot, Mapping):
        name = str(riot.get("displayName") or riot.get("gameName") or "").strip()
        tag = str(riot.get("tagLine") or "").strip()
        if name and tag:
            return f"{name}#{tag}"
    name = str(
        player.get("riotIDGameName")
        or player.get("gameName")
        or player.get("summonerName")
        or player.get("playerName")
        or ""
    ).strip()
    tag = str(player.get("riotIDTagline") or player.get("tagLine") or "").strip()
    if name and tag:
        return f"{name}#{tag}"
    return ""


def _has_trustworthy_hp(part: Mapping[str, Any]) -> bool:
    if "health" not in part or "healthMax" not in part:
        return False
    try:
        health = float(part["health"])
        health_max = float(part["healthMax"])
    except (TypeError, ValueError):
        return False
    return health_max > 0 and health >= 0


def _has_trustworthy_combat(part: Mapping[str, Any]) -> bool:
    for key in COMBAT_FIELDS:
        if key not in part:
            return False
        try:
            float(part[key])
        except (TypeError, ValueError):
            return False
    return True


def _has_trustworthy_ability_ranks(part: Mapping[str, Any]) -> bool:
    """Ability levels are trustworthy when all four slots are present (0 is valid)."""
    for key in ABILITY_LEVEL_FIELDS:
        if key not in part:
            return False
        try:
            level = int(part[key])
        except (TypeError, ValueError):
            return False
        if level < 0 or level > 18:
            return False
    return True


def _has_trustworthy_position(part: Mapping[str, Any]) -> bool:
    pos = part.get("position")
    if not isinstance(pos, Mapping):
        return False
    try:
        float(pos.get("x"))
        float(pos.get("z") if "z" in pos else pos.get("y"))
    except (TypeError, ValueError):
        return False
    return True


def annotate_participant(part: Mapping[str, Any]) -> Dict[str, Any]:
    """Copy participant and attach honest source markers; strip unknown combat/HP keys."""
    out = dict(part)
    if _has_trustworthy_position(out):
        pos = out.get("position") or {}
        if isinstance(pos, Mapping) and "z" not in pos and "y" in pos:
            out["position"] = {"x": float(pos["x"]), "z": float(pos["y"])}
        out["positionSource"] = POSITION_SOURCE
    else:
        out.pop("position", None)
        out["positionSource"] = UNAVAILABLE

    if _has_trustworthy_hp(out):
        out["healthSource"] = HEALTH_SOURCE
    else:
        out.pop("health", None)
        out.pop("healthMax", None)
        out["healthSource"] = UNAVAILABLE

    if _has_trustworthy_combat(out):
        out["combatStatsSource"] = COMBAT_STATS_SOURCE
    else:
        for key in COMBAT_FIELDS:
            out.pop(key, None)
        out["combatStatsSource"] = UNAVAILABLE

    if _has_trustworthy_ability_ranks(out):
        out["abilityRanksSource"] = ABILITY_RANKS_SOURCE
    else:
        # Do not invent zeros — omit levels so consumers treat ranks as unknown.
        for key in ABILITY_LEVEL_FIELDS:
            out.pop(key, None)
        out["abilityRanksSource"] = UNAVAILABLE

    puuid = str(out.get("puuid") or "").strip()
    if puuid:
        out["puuid"] = puuid
    rid = full_riot_id(out)
    if rid:
        out["fullRiotId"] = rid
    return out


def annotate_event(row: Mapping[str, Any]) -> Dict[str, Any]:
    out = dict(row)
    schema = str(out.get("rfc461Schema") or "")
    if schema in {"game_info", "stats_update"}:
        parts = out.get("participants")
        if isinstance(parts, list):
            out["participants"] = [
                annotate_participant(p) if isinstance(p, Mapping) else p for p in parts
            ]
    return out


def coverage_for(
    *,
    game_id: int,
    platform_id: str,
    series_id: str,
    game_index: Optional[int],
    artifact: str,
    stats_updates: int,
    hp_known_frames: int,
    combat_known_frames: int,
    ranks_known_frames: int,
) -> Dict[str, Any]:
    decoded = [
        "game_info",
        "stats_update",
        "champion_kill",
        "skill_used",
        "skill_level_up",
        "building_destroyed",
        "epic_monster_kill",
        "item_purchased",
        "ward_placed",
    ]
    missing = [
        "calculatorReady",
        "product_publish",
        "rofl_decrypt_fuse",
    ]
    notes = (
        "GRID Riot live-stats research path. Dense ~1 Hz positions/HP/combat/ability "
        "levels when present on the wire. productEligible=false until "
        "validate-rofl-pipeline.py --product passes on a ROFL-fused product timeline. "
        "Never publish to public/data/matches/ from this adapter alone."
    )
    provenance = rfc461_emit.provenance_record(
        source=SOURCE,
        source_kind=SOURCE_KIND,
        position_coverage="dense_1hz_when_present",
        hp_coverage="dense_1hz_when_present",
        roster_mapping="puuid_or_full_riot_id",
        notes=notes,
        artifact=artifact,
    )
    extra: Dict[str, Any] = {
        "productEligible": False,
        "calculatorReady": False,
        "gridSeriesId": series_id or None,
        "gridGameIndex": game_index,
        "platformID": platform_id or None,
        "statsUpdateCount": stats_updates,
        "hpKnownFrameCount": hp_known_frames,
        "combatKnownFrameCount": combat_known_frames,
        "abilityRanksKnownFrameCount": ranks_known_frames,
    }
    return rfc461_emit.coverage_line(
        source=SOURCE,
        game_id=game_id,
        decoded=decoded,
        missing=missing,
        notes=notes,
        provenance=provenance,
        extra=extra,
    )


def suggested_product_rofl_name(platform_id: str, game_id: Any) -> Optional[str]:
    platform = str(platform_id or "").strip()
    if not platform or platform.upper() in {"GRID", "UNKNOWN", "?"}:
        return None
    try:
        gid = int(game_id)
    except (TypeError, ValueError):
        return None
    if gid <= 0:
        return None
    # Do not invent region short-codes; use wire platformID as-is.
    return f"{platform}-{gid}.rofl"


def parse_grid_ids_from_path(path: Path) -> Tuple[str, Optional[int]]:
    """Parse ``events_<seriesId>_<gameIndex>_riot.jsonl`` → (seriesId, gameIndex)."""
    m = re.match(r"events_(\d+)_(\d+)_riot\.jsonl$", path.name)
    if m:
        return m.group(1), int(m.group(2))
    m = re.match(r"events_(\d+)_riot\.jsonl$", path.name)
    if m:
        return m.group(1), None
    return "", None


def convert_riot_livestats(
    rows: Iterator[Mapping[str, Any]],
    *,
    series_id_hint: str = "",
    game_index_hint: Optional[int] = None,
    artifact: str = "",
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Convert an in-memory / streamed row iterator into annotated research rfc461."""
    out_rows: List[Dict[str, Any]] = []
    schema_counts: Dict[str, int] = {}
    game_info: Optional[Dict[str, Any]] = None
    stats_updates = 0
    hp_known_frames = 0
    combat_known_frames = 0
    ranks_known_frames = 0
    puuids: List[str] = []
    full_riot_ids: List[str] = []

    for raw in rows:
        schema = str(raw.get("rfc461Schema") or "")
        schema_counts[schema] = schema_counts.get(schema, 0) + 1
        annotated = annotate_event(raw)
        if schema == "game_info" and game_info is None:
            game_info = annotated
            for p in annotated.get("participants") or []:
                if not isinstance(p, Mapping):
                    continue
                pid = str(p.get("puuid") or "").strip()
                if pid:
                    puuids.append(pid)
                rid = str(p.get("fullRiotId") or full_riot_id(p) or "").strip()
                if rid:
                    full_riot_ids.append(rid)
        if schema == "stats_update":
            stats_updates += 1
            parts = annotated.get("participants") or []
            if parts and all(
                isinstance(p, Mapping) and p.get("healthSource") == HEALTH_SOURCE
                for p in parts
            ):
                hp_known_frames += 1
            if parts and all(
                isinstance(p, Mapping)
                and p.get("combatStatsSource") == COMBAT_STATS_SOURCE
                for p in parts
            ):
                combat_known_frames += 1
            if parts and all(
                isinstance(p, Mapping)
                and p.get("abilityRanksSource") == ABILITY_RANKS_SOURCE
                for p in parts
            ):
                ranks_known_frames += 1
        out_rows.append(annotated)

    if game_info is None:
        raise ValueError("input has no game_info row")

    game_id = int(game_info.get("gameID") or 0)
    platform_id = str(game_info.get("platformID") or "").strip()
    series_id = str(series_id_hint or "").strip()
    game_index = game_index_hint
    rename = suggested_product_rofl_name(platform_id, game_id)

    coverage = coverage_for(
        game_id=game_id,
        platform_id=platform_id,
        series_id=series_id,
        game_index=game_index,
        artifact=artifact or SOURCE,
        stats_updates=stats_updates,
        hp_known_frames=hp_known_frames,
        combat_known_frames=combat_known_frames,
        ranks_known_frames=ranks_known_frames,
    )
    final_rows = [coverage] + out_rows

    summary: Dict[str, Any] = {
        "ok": True,
        "sourceKind": SOURCE_KIND,
        "seriesId": series_id or None,
        "gridGameIndex": game_index,
        "gameID": game_id,
        "platformID": platform_id or None,
        "suggestedProductRofl": rename,
        "productFilenameDerivable": bool(rename),
        "productEligible": False,
        "calculatorReady": False,
        "participants": len(game_info.get("participants") or []),
        "puuidCount": len(set(puuids)),
        "fullRiotIdCount": len(set(full_riot_ids)),
        "statsUpdates": stats_updates,
        "hpKnownFrameCount": hp_known_frames,
        "combatKnownFrameCount": combat_known_frames,
        "abilityRanksKnownFrameCount": ranks_known_frames,
        "schemaCounts": dict(sorted(schema_counts.items())),
        "trustGates": {
            "hpKnown": hp_known_frames > 0,
            "combatStatsKnown": combat_known_frames > 0,
            "abilityRanksKnown": ranks_known_frames > 0,
            "positionsDense": stats_updates > 0,
            "note": (
                "Live-stats frames can satisfy per-frame hp/combat/ranks markers when "
                "fields are on the wire, but match-level calculatorReady still requires "
                "ROFL identity fuse + validate-rofl-pipeline.py --product."
            ),
        },
        "renameBlocker": None
        if rename
        else (
            "platformID/gameID missing or invalid on game_info; "
            "do not invent PLATFORM-matchCode"
        ),
    }
    return final_rows, summary


def convert_riot_livestats_file(
    input_path: Path,
    out_path: Path,
    *,
    series_id_hint: str = "",
    game_index_hint: Optional[int] = None,
) -> Dict[str, Any]:
    """Stream-convert a riot JSONL file to annotated research rfc461 (memory-safe)."""
    input_path = Path(input_path)
    out_path = Path(out_path)
    parsed_series, parsed_game = parse_grid_ids_from_path(input_path)
    series_id = series_id_hint or parsed_series
    game_index = game_index_hint if game_index_hint is not None else parsed_game

    # First pass stats for coverage header — stream once into annotated output,
    # then rewrite coverage at the front via a temp buffer for small fixtures;
    # for large files write coverage placeholder then patch is expensive, so:
    # collect only until game_info + scan counts while writing body to a sibling temp.
    out_path.parent.mkdir(parents=True, exist_ok=True)
    body_path = out_path.with_suffix(out_path.suffix + ".body.tmp")

    schema_counts: Dict[str, int] = {}
    game_info: Optional[Dict[str, Any]] = None
    stats_updates = 0
    hp_known_frames = 0
    combat_known_frames = 0
    ranks_known_frames = 0
    puuids: List[str] = []
    full_riot_ids: List[str] = []
    event_count = 0

    with body_path.open("w", encoding="utf-8") as body_fh:
        for raw in _iter_jsonl_rows(input_path):
            schema = str(raw.get("rfc461Schema") or "")
            schema_counts[schema] = schema_counts.get(schema, 0) + 1
            annotated = annotate_event(raw)
            if schema == "game_info" and game_info is None:
                game_info = annotated
                for p in annotated.get("participants") or []:
                    if not isinstance(p, Mapping):
                        continue
                    pid = str(p.get("puuid") or "").strip()
                    if pid:
                        puuids.append(pid)
                    rid = str(p.get("fullRiotId") or full_riot_id(p) or "").strip()
                    if rid:
                        full_riot_ids.append(rid)
            if schema == "stats_update":
                stats_updates += 1
                parts = annotated.get("participants") or []
                if parts and all(
                    isinstance(p, Mapping) and p.get("healthSource") == HEALTH_SOURCE
                    for p in parts
                ):
                    hp_known_frames += 1
                if parts and all(
                    isinstance(p, Mapping)
                    and p.get("combatStatsSource") == COMBAT_STATS_SOURCE
                    for p in parts
                ):
                    combat_known_frames += 1
                if parts and all(
                    isinstance(p, Mapping)
                    and p.get("abilityRanksSource") == ABILITY_RANKS_SOURCE
                    for p in parts
                ):
                    ranks_known_frames += 1
            body_fh.write(json.dumps(annotated, ensure_ascii=False) + "\n")
            event_count += 1

    if game_info is None:
        body_path.unlink(missing_ok=True)
        raise ValueError(f"{input_path}: no game_info row")

    game_id = int(game_info.get("gameID") or 0)
    platform_id = str(game_info.get("platformID") or "").strip()
    rename = suggested_product_rofl_name(platform_id, game_id)
    coverage = coverage_for(
        game_id=game_id,
        platform_id=platform_id,
        series_id=series_id,
        game_index=game_index,
        artifact=str(input_path.name),
        stats_updates=stats_updates,
        hp_known_frames=hp_known_frames,
        combat_known_frames=combat_known_frames,
        ranks_known_frames=ranks_known_frames,
    )

    with out_path.open("w", encoding="utf-8") as out_fh:
        out_fh.write(json.dumps(coverage, ensure_ascii=False) + "\n")
        with body_path.open("r", encoding="utf-8") as body_fh:
            for line in body_fh:
                out_fh.write(line)
    body_path.unlink(missing_ok=True)

    summary: Dict[str, Any] = {
        "ok": True,
        "sourceKind": SOURCE_KIND,
        "input": str(input_path),
        "out": str(out_path),
        "seriesId": series_id or None,
        "gridGameIndex": game_index,
        "gameID": game_id,
        "platformID": platform_id or None,
        "suggestedProductRofl": rename,
        "productFilenameDerivable": bool(rename),
        "productEligible": False,
        "calculatorReady": False,
        "eventCount": event_count,
        "participants": len(game_info.get("participants") or []),
        "puuidCount": len(set(puuids)),
        "fullRiotIdCount": len(set(full_riot_ids)),
        "statsUpdates": stats_updates,
        "hpKnownFrameCount": hp_known_frames,
        "combatKnownFrameCount": combat_known_frames,
        "abilityRanksKnownFrameCount": ranks_known_frames,
        "schemaCounts": dict(sorted(schema_counts.items())),
        "trustGates": {
            "hpKnown": hp_known_frames > 0,
            "combatStatsKnown": combat_known_frames > 0,
            "abilityRanksKnown": ranks_known_frames > 0,
            "positionsDense": stats_updates > 0,
            "note": (
                "Live-stats frames can satisfy per-frame hp/combat/ranks markers when "
                "fields are on the wire, but match-level calculatorReady still requires "
                "ROFL identity fuse + validate-rofl-pipeline.py --product."
            ),
        },
        "renameBlocker": None
        if rename
        else (
            "platformID/gameID missing or invalid on game_info; "
            "do not invent PLATFORM-matchCode"
        ),
    }
    return summary


def _sqlite_num(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _sqlite_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _items_json_from_participant(part: Mapping[str, Any]) -> Optional[str]:
    """Serialize itemID list from live-stats ``items`` array; None if absent."""
    raw = part.get("items")
    if not isinstance(raw, list):
        return None
    ids: List[int] = []
    for entry in raw:
        if isinstance(entry, Mapping):
            item_id = _sqlite_int(entry.get("itemID") if "itemID" in entry else entry.get("itemId"))
        else:
            item_id = _sqlite_int(entry)
        if item_id is None or item_id <= 0:
            continue
        ids.append(item_id)
    return json.dumps(ids, separators=(",", ":"))


def _frame_row_from_participant(
    game_time_ms: int, part: Mapping[str, Any]
) -> Tuple[Any, ...]:
    """Build one frames tuple; unknown fields are NULL (never invent zeros)."""
    annotated = annotate_participant(part)
    pid = _sqlite_int(annotated.get("participantID")) or 0
    hp_known = annotated.get("healthSource") == HEALTH_SOURCE
    combat_known = annotated.get("combatStatsSource") == COMBAT_STATS_SOURCE
    ranks_known = annotated.get("abilityRanksSource") == ABILITY_RANKS_SOURCE
    pos_known = annotated.get("positionSource") == POSITION_SOURCE
    pos = annotated.get("position") if isinstance(annotated.get("position"), Mapping) else {}
    return (
        int(game_time_ms),
        pid,
        _sqlite_num(pos.get("x")) if pos_known else None,
        _sqlite_num(pos.get("z")) if pos_known else None,
        1 if annotated.get("alive") else 0 if "alive" in annotated else None,
        _sqlite_int(annotated.get("level")),
        _sqlite_num(annotated.get("health")) if hp_known else None,
        _sqlite_num(annotated.get("healthMax")) if hp_known else None,
        _sqlite_num(annotated.get("attackDamage")) if combat_known else None,
        _sqlite_num(annotated.get("abilityPower")) if combat_known else None,
        _sqlite_num(annotated.get("armor")) if combat_known else None,
        _sqlite_num(annotated.get("magicResist")) if combat_known else None,
        _sqlite_num(annotated.get("attackSpeed")) if combat_known else None,
        _sqlite_int(annotated.get("ability1Level")) if ranks_known else None,
        _sqlite_int(annotated.get("ability2Level")) if ranks_known else None,
        _sqlite_int(annotated.get("ability3Level")) if ranks_known else None,
        _sqlite_int(annotated.get("ability4Level")) if ranks_known else None,
        _sqlite_num(annotated.get("totalGold")),
        _sqlite_num(annotated.get("currentGold")),
        _sqlite_num(annotated.get("respawnTimer")),
        _items_json_from_participant(part),
        1 if hp_known else 0,
        1 if combat_known else 0,
        1 if ranks_known else 0,
        1 if pos_known else 0,
    )


def _slim_event_payload(row: Mapping[str, Any]) -> Dict[str, Any]:
    """Keep a few useful extras; drop transport / giant nested blobs."""
    keep_keys = (
        "skillName",
        "skillSlot",
        "monsterType",
        "buildingType",
        "laneType",
        "towerType",
        "itemID",
        "itemName",
        "killerTeamID",
        "assistingParticipantIDs",
        "position",
        "summonerSpellName",
    )
    out: Dict[str, Any] = {}
    for key in keep_keys:
        if key in row and row[key] is not None:
            out[key] = row[key]
    return out


def init_slim_sqlite(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        PRAGMA journal_mode = WAL;
        PRAGMA synchronous = NORMAL;

        CREATE TABLE IF NOT EXISTS meta (
          key TEXT PRIMARY KEY,
          value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS roster (
          participant_id INTEGER PRIMARY KEY,
          team_id INTEGER,
          champion_name TEXT,
          summoner_name TEXT,
          puuid TEXT,
          full_riot_id TEXT,
          role TEXT
        );

        CREATE TABLE IF NOT EXISTS frames (
          game_time_ms INTEGER NOT NULL,
          participant_id INTEGER NOT NULL,
          x REAL,
          z REAL,
          alive INTEGER,
          level INTEGER,
          health REAL,
          health_max REAL,
          attack_damage REAL,
          ability_power REAL,
          armor REAL,
          magic_resist REAL,
          attack_speed REAL,
          ability1_level INTEGER,
          ability2_level INTEGER,
          ability3_level INTEGER,
          ability4_level INTEGER,
          total_gold REAL,
          current_gold REAL,
          respawn_timer REAL,
          items_json TEXT,
          hp_known INTEGER NOT NULL,
          combat_known INTEGER NOT NULL,
          ranks_known INTEGER NOT NULL,
          position_known INTEGER NOT NULL,
          PRIMARY KEY (game_time_ms, participant_id)
        );

        CREATE TABLE IF NOT EXISTS events (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          game_time_ms INTEGER NOT NULL,
          schema TEXT NOT NULL,
          participant_id INTEGER,
          killer_id INTEGER,
          victim_id INTEGER,
          skill_slot INTEGER,
          monster_type TEXT,
          winning_team INTEGER,
          payload_json TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_frames_pid ON frames(participant_id);
        CREATE INDEX IF NOT EXISTS idx_events_t ON events(game_time_ms);
        CREATE INDEX IF NOT EXISTS idx_events_schema ON events(schema);
        """
    )


def write_riot_slim_sqlite(
    input_path: Path,
    db_path: Path,
    *,
    series_id_hint: str = "",
    game_index_hint: Optional[int] = None,
) -> Dict[str, Any]:
    """Stream riot live-stats JSONL into a slim research SQLite DB.

    Drops transport fields and unused combat extras. Keeps ~1 Hz frame density.
    Never sets productEligible / calculatorReady.
    """
    input_path = Path(input_path)
    db_path = Path(db_path)
    parsed_series, parsed_game = parse_grid_ids_from_path(input_path)
    series_id = series_id_hint or parsed_series
    game_index = game_index_hint if game_index_hint is not None else parsed_game

    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    conn = sqlite3.connect(str(db_path))
    game_id = 0
    platform_id = ""
    rename: Optional[str] = None
    frame_rows = 0
    event_rows = 0
    stats_updates = 0
    schema_counts: Dict[str, int] = {}
    try:
        init_slim_sqlite(conn)
        game_info: Optional[Dict[str, Any]] = None

        frame_insert = """
            INSERT OR REPLACE INTO frames (
              game_time_ms, participant_id, x, z, alive, level,
              health, health_max, attack_damage, ability_power, armor, magic_resist,
              attack_speed, ability1_level, ability2_level, ability3_level, ability4_level,
              total_gold, current_gold, respawn_timer, items_json,
              hp_known, combat_known, ranks_known, position_known
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """
        event_insert = """
            INSERT INTO events (
              game_time_ms, schema, participant_id, killer_id, victim_id,
              skill_slot, monster_type, winning_team, payload_json
            ) VALUES (?,?,?,?,?,?,?,?,?)
        """

        batch_frames: List[Tuple[Any, ...]] = []
        batch_events: List[Tuple[Any, ...]] = []

        def flush() -> None:
            nonlocal batch_frames, batch_events
            if batch_frames:
                conn.executemany(frame_insert, batch_frames)
                batch_frames = []
            if batch_events:
                conn.executemany(event_insert, batch_events)
                batch_events = []

        for raw in _iter_jsonl_rows(input_path):
            schema = str(raw.get("rfc461Schema") or "")
            schema_counts[schema] = schema_counts.get(schema, 0) + 1

            if schema == "game_info" and game_info is None:
                game_info = dict(raw)
                roster_rows = []
                for p in raw.get("participants") or []:
                    if not isinstance(p, Mapping):
                        continue
                    annotated = annotate_participant(p)
                    roster_rows.append(
                        (
                            _sqlite_int(annotated.get("participantID")),
                            _sqlite_int(annotated.get("teamID")),
                            str(annotated.get("championName") or ""),
                            str(
                                annotated.get("summonerName")
                                or annotated.get("playerName")
                                or ""
                            ),
                            str(annotated.get("puuid") or ""),
                            str(annotated.get("fullRiotId") or full_riot_id(annotated) or ""),
                            str(annotated.get("role") or ""),
                        )
                    )
                conn.executemany(
                    """
                    INSERT OR REPLACE INTO roster (
                      participant_id, team_id, champion_name, summoner_name,
                      puuid, full_riot_id, role
                    ) VALUES (?,?,?,?,?,?,?)
                    """,
                    roster_rows,
                )

            elif schema == "stats_update":
                stats_updates += 1
                game_time = _sqlite_int(raw.get("gameTime")) or 0
                for p in raw.get("participants") or []:
                    if not isinstance(p, Mapping):
                        continue
                    batch_frames.append(_frame_row_from_participant(game_time, p))
                    frame_rows += 1
                if len(batch_frames) >= 2000:
                    flush()

            elif schema in SLIM_EVENT_SCHEMAS:
                payload = _slim_event_payload(raw)
                # GRID Riot live-stats uses killer/victim/participant (not *ID).
                participant_id = _sqlite_int(
                    raw.get("participantID")
                    if raw.get("participantID") is not None
                    else raw.get("participant")
                )
                killer_id = _sqlite_int(
                    raw.get("killerID")
                    if raw.get("killerID") is not None
                    else raw.get("killer")
                )
                victim_id = _sqlite_int(
                    raw.get("victimID")
                    if raw.get("victimID") is not None
                    else raw.get("victim")
                )
                # Keep ids in payload too for older DBs / consumers.
                if killer_id is not None:
                    payload.setdefault("killer", killer_id)
                if victim_id is not None:
                    payload.setdefault("victim", victim_id)
                if participant_id is not None:
                    payload.setdefault("participant", participant_id)
                batch_events.append(
                    (
                        _sqlite_int(raw.get("gameTime")) or 0,
                        schema,
                        participant_id,
                        killer_id,
                        victim_id,
                        _sqlite_int(raw.get("skillSlot") or payload.get("skillSlot")),
                        str(raw.get("monsterType") or payload.get("monsterType") or "")
                        or None,
                        _sqlite_int(raw.get("winningTeam")),
                        json.dumps(payload, ensure_ascii=False) if payload else None,
                    )
                )
                event_rows += 1
                if len(batch_events) >= 1000:
                    flush()

        flush()
        if game_info is None:
            raise ValueError(f"{input_path}: no game_info row")

        game_id = int(game_info.get("gameID") or 0)
        platform_id = str(game_info.get("platformID") or "").strip()
        rename = suggested_product_rofl_name(platform_id, game_id)
        meta = {
            "schema": SQLITE_SCHEMA_VERSION,
            "sourceKind": SOURCE_KIND,
            "productEligible": "false",
            "calculatorReady": "false",
            "input": str(input_path),
            "seriesId": series_id or "",
            "gridGameIndex": "" if game_index is None else str(game_index),
            "gameID": str(game_id),
            "platformID": platform_id,
            "gameName": str(game_info.get("gameName") or ""),
            "gameVersion": str(game_info.get("gameVersion") or ""),
            "suggestedProductRofl": rename or "",
            "statsUpdates": str(stats_updates),
            "frameRows": str(frame_rows),
            "eventRows": str(event_rows),
            "notes": (
                "Slim research extract from GRID Riot live-stats. "
                "Unknown HP/combat/ranks stored as NULL. Not product-publishable."
            ),
        }
        conn.executemany(
            "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
            list(meta.items()),
        )
        conn.commit()
    finally:
        conn.close()

    summary: Dict[str, Any] = {
        "ok": True,
        "schema": SQLITE_SCHEMA_VERSION,
        "sourceKind": SOURCE_KIND,
        "input": str(input_path),
        "sqlite": str(db_path),
        "sqliteBytes": db_path.stat().st_size if db_path.is_file() else 0,
        "inputBytes": input_path.stat().st_size if input_path.is_file() else 0,
        "seriesId": series_id or None,
        "gridGameIndex": game_index,
        "gameID": game_id,
        "platformID": platform_id or None,
        "suggestedProductRofl": rename,
        "productEligible": False,
        "calculatorReady": False,
        "statsUpdates": stats_updates,
        "frameRows": frame_rows,
        "eventRows": event_rows,
        "schemaCounts": dict(sorted(schema_counts.items())),
    }
    if summary["inputBytes"]:
        summary["compressionRatio"] = round(
            summary["sqliteBytes"] / summary["inputBytes"], 4
        )
    return summary


def join_riot_rofl(
    *,
    riot_summary: Mapping[str, Any],
    riot_puuids: Sequence[str],
    rofl_path: Path,
) -> Dict[str, Any]:
    scripts_dir = Path(__file__).resolve().parent
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    import grid_events_to_rfc461 as grid

    rofl = grid.rofl_stats_identities(Path(rofl_path))
    riot_set = {p for p in riot_puuids if p}
    rofl_set = set(rofl["puuids"])
    overlap = sorted(riot_set & rofl_set)
    only_riot = sorted(riot_set - rofl_set)
    only_rofl = sorted(rofl_set - riot_set)
    return {
        "sameMatchLikely": len(overlap) >= 8 and not only_riot and len(only_rofl) <= 2,
        "overlapCount": len(overlap),
        "riotPuuidCount": len(riot_set),
        "roflPuuidCount": len(rofl_set),
        "overlapPuids": overlap,
        "onlyRiot": only_riot,
        "onlyRofl": only_rofl,
        "rofl": {
            "path": rofl["path"],
            "durationMs": rofl["durationMs"],
            "productFilenameOk": rofl["productFilenameOk"],
            "playerCount": rofl["playerCount"],
        },
        "suggestedProductRofl": riot_summary.get("suggestedProductRofl"),
        "note": (
            "Copy/rename ROFL to suggestedProductRofl before npm run rofl:ingest; "
            "Grid seriesId filenames are not Riot match codes."
        ),
    }


def _puuids_from_out(out_path: Path) -> List[str]:
    with out_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            row = json.loads(line)
            if row.get("rfc461Schema") != "game_info":
                continue
            return [
                str(p.get("puuid") or "").strip()
                for p in (row.get("participants") or [])
                if str(p.get("puuid") or "").strip()
            ]
    return []


def build_rename_report(root: Path) -> Dict[str, Any]:
    """Scan pro-grid for events_*_*_riot.jsonl and map to suggested ROFL names."""
    root = Path(root).resolve()
    entries: List[Dict[str, Any]] = []
    for path in sorted(root.glob("events_*_*_riot.jsonl")):
        series_id, game_index = parse_grid_ids_from_path(path)
        platform_id = ""
        game_id: Any = None
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                row = json.loads(line)
                if row.get("rfc461Schema") == "game_info":
                    platform_id = str(row.get("platformID") or "").strip()
                    game_id = row.get("gameID")
                    break
        suggested = suggested_product_rofl_name(platform_id, game_id)
        dump_rofl = f"replay_riot_{series_id}_{game_index}.rofl" if game_index else None
        dump_exists = bool(dump_rofl and (root / dump_rofl).is_file())
        entries.append(
            {
                "seriesId": series_id,
                "gridGameIndex": game_index,
                "riotJsonl": path.name,
                "dumpRofl": dump_rofl,
                "dumpRoflPresent": dump_exists,
                "platformID": platform_id or None,
                "gameID": game_id,
                "suggestedProductRofl": suggested,
                "productFilenameDerivable": bool(suggested),
                "blocker": None
                if suggested
                else "missing platformID/gameID on game_info — do not invent",
            }
        )
    return {
        "schema": "pro-grid-rofl-rename-report-v1",
        "root": str(root),
        "count": len(entries),
        "derivableCount": sum(1 for e in entries if e["productFilenameDerivable"]),
        "entries": entries,
        "notes": (
            "Suggested names come only from Riot live-stats game_info.platformID + "
            "gameID. Trailing ROFL metadata on Grid dumps often lacks these fields. "
            "Do not guess platform. Rename (copy) before npm run rofl:ingest."
        ),
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, help="GRID events_*_*_riot.jsonl")
    parser.add_argument("--out", type=Path, help="Output research rfc461 JSONL")
    parser.add_argument(
        "--sqlite",
        type=Path,
        help="Slim research SQLite path (frames/events/roster; preferred working copy)",
    )
    parser.add_argument("--series-id", default="", help="Grid series id hint")
    parser.add_argument("--game-index", type=int, default=None, help="Game index hint")
    parser.add_argument("--summary", type=Path, help="Optional JSON summary path")
    parser.add_argument(
        "--join-rofl",
        type=Path,
        help="Optional ROFL path for PUUID same-match join",
    )
    parser.add_argument(
        "--write-rename-report",
        type=Path,
        help="Scan a pro-grid dir and write rofl-rename-report.json",
    )
    args = parser.parse_args(argv)

    if args.write_rename_report:
        report = build_rename_report(args.write_rename_report)
        out_path = args.write_rename_report / "rofl-rename-report.json"
        out_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(
            json.dumps(
                {
                    "ok": True,
                    "report": str(out_path),
                    "count": report["count"],
                    "derivableCount": report["derivableCount"],
                },
                indent=2,
            )
        )
        return 0

    if not args.input or (not args.out and not args.sqlite):
        parser.error(
            "--input and at least one of --out / --sqlite are required "
            "unless --write-rename-report"
        )

    summary: Dict[str, Any] = {
        "ok": True,
        "productEligible": False,
        "calculatorReady": False,
    }
    if args.out:
        summary.update(
            convert_riot_livestats_file(
                args.input,
                args.out,
                series_id_hint=args.series_id,
                game_index_hint=args.game_index,
            )
        )
    if args.sqlite:
        sqlite_summary = write_riot_slim_sqlite(
            args.input,
            args.sqlite,
            series_id_hint=args.series_id,
            game_index_hint=args.game_index,
        )
        if not args.out:
            summary.update(sqlite_summary)
        else:
            summary["sqlite"] = sqlite_summary
    if args.join_rofl:
        if args.out:
            puuids = _puuids_from_out(args.out)
        else:
            # Pull PUUIDs from sqlite roster when only --sqlite was requested.
            conn = sqlite3.connect(str(args.sqlite))
            try:
                puuids = [
                    row[0]
                    for row in conn.execute(
                        "SELECT puuid FROM roster WHERE puuid IS NOT NULL AND puuid != ''"
                    )
                ]
            finally:
                conn.close()
        summary["puuidJoin"] = join_riot_rofl(
            riot_summary=summary if not isinstance(summary.get("sqlite"), dict) else {
                **summary,
                **(summary.get("sqlite") or {}),
            },
            riot_puuids=puuids,
            rofl_path=args.join_rofl,
        )
    if args.summary:
        args.summary.parent.mkdir(parents=True, exist_ok=True)
        args.summary.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
