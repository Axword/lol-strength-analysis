#!/usr/bin/env python3
"""
Shared rfc461 / live-stats JSONL emitters used by:
  - scripts/rofl2_to_jsonl.py (ROFL2 scaffold)
  - scripts/maknee_packets_to_jsonl.py (decoded packets)

Keep participant / stats_update shapes aligned so rebuild/enrich scripts
can consume either source.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

# Approximate SR fountain spawns (Riot map units).
FOUNTAIN = {
    100: {"x": 400.0, "z": 400.0},
    200: {"x": 14300.0, "z": 14400.0},
}

LIVE_COORDINATE_SYSTEM = "riot_live_stats_sr"
COORDINATE_OFFSET = {"x": 7500.0, "z": 7500.0}


def provenance_record(
    *,
    source: str,
    source_kind: str,
    position_coverage: str,
    hp_coverage: str,
    roster_mapping: str,
    notes: str = "",
    artifact: str = "",
) -> Dict[str, Any]:
    """Return the shared provenance contract carried by ``rofl_coverage``.

    This is metadata on the canonical rfc461 stream, not a second interchange
    format. Position source is also repeated on each participant row so a
    consumer can fail closed at a particular frame.
    """
    out: Dict[str, Any] = {
        "source": source,
        "sourceKind": source_kind,
        "artifact": artifact or source,
        "gameTimeUnit": "milliseconds",
        "coordinateSystem": LIVE_COORDINATE_SYSTEM,
        "coordinateOffset": dict(COORDINATE_OFFSET),
        "positionCoverage": position_coverage,
        "hpCoverage": hp_coverage,
        "rosterMapping": roster_mapping,
        "placeholderPolicy": "explicit_positionSource_only",
    }
    if notes:
        out["notes"] = notes
    return out


def to_live_stats_coords(x: float, z: float) -> Tuple[float, float]:
    """Centered SR coords (negative) → live-stats ~0..15000 space."""
    if x < 0 or z < 0:
        return (x + 7500.0, z + 7500.0)
    return (x, z)


def fountain_for_team(team_id: int) -> Dict[str, float]:
    return dict(FOUNTAIN.get(int(team_id), FOUNTAIN[100]))


def coverage_line(
    *,
    source: str,
    game_id: int = 0,
    decoded: Optional[Sequence[str]] = None,
    missing: Optional[Sequence[str]] = None,
    notes: str = "",
    extra: Optional[Dict[str, Any]] = None,
    provenance: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    row: Dict[str, Any] = {
        "rfc461Schema": "rofl_coverage",
        "gameID": game_id,
        "gameTime": 0,
        "source": source,
        "decoded": list(decoded or []),
        "missing": list(missing or []),
    }
    if provenance:
        row["provenance"] = dict(provenance)
    if notes:
        row["notes"] = notes
    if extra:
        row.update(extra)
    return row


def game_info_line(
    *,
    game_id: int,
    participants: List[Dict[str, Any]],
    game_name: str = "",
    game_version: str = "",
    platform_id: str = "",
    stats_update_interval_ms: int = 1000,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    row: Dict[str, Any] = {
        "rfc461Schema": "game_info",
        "gameID": game_id,
        "gameName": game_name,
        "gameVersion": game_version,
        "platformID": platform_id,
        "statsUpdateInterval": stats_update_interval_ms,
        "participants": participants,
    }
    if extra:
        row.update(extra)
    return row


def participant_row(
    *,
    participant_id: int,
    team_id: int,
    champion_name: str,
    player_name: str,
    position: Dict[str, float],
    position_source: str,
    alive: bool = True,
    level: int = 1,
    health: float = 1.0,
    health_max: float = 1.0,
    health_known: bool = True,
    health_source: Optional[str] = None,
    combat_stats_source: Optional[str] = None,
    ability_ranks_source: Optional[str] = None,
    items: Optional[List[Dict[str, Any]]] = None,
    total_gold: Optional[float] = None,
    current_gold: Optional[float] = None,
    respawn_timer: float = 0.0,
    ability_levels: Optional[Tuple[int, int, int, int]] = None,
    attack_damage: Optional[float] = None,
    ability_power: Optional[float] = None,
    armor: Optional[float] = None,
    magic_resist: Optional[float] = None,
    attack_speed: Optional[float] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build a participant object for ``stats_update``.

    Default ``health_known=True`` preserves the historical known-health shape
    (``health`` / ``healthMax`` always present). When ``health_known=False``,
    those keys are omitted and callers should set ``health_source`` (and usually
    combat/ability source markers) so consumers treat HP as unknown rather than
    dead/full/fake.

    Optional combat overrides (``attackDamage`` / ``abilityPower`` / ``armor`` /
    ``magicResist`` / ``attackSpeed``) are only written when provided. Callers
    that lack Replication combat fields should set ``combat_stats_source`` to an
    unavailable marker instead of inventing zeros.
    """
    a1, a2, a3, a4 = ability_levels or (0, 0, 0, 0)
    row: Dict[str, Any] = {
        "participantID": participant_id,
        "teamID": team_id,
        "championName": champion_name,
        "playerName": player_name,
        "alive": alive,
        "respawnTimer": respawn_timer,
        "level": level,
        "position": {"x": float(position["x"]), "z": float(position["z"])},
        "positionSource": position_source,
        "items": list(items or []),
        "ability1Level": a1,
        "ability2Level": a2,
        "ability3Level": a3,
        "ability4Level": a4,
    }
    if health_known:
        row["health"] = health
        row["healthMax"] = health_max
    if health_source is not None:
        row["healthSource"] = health_source
    if combat_stats_source is not None:
        row["combatStatsSource"] = combat_stats_source
    if ability_ranks_source is not None:
        row["abilityRanksSource"] = ability_ranks_source
    if total_gold is not None:
        row["totalGold"] = total_gold
    if current_gold is not None:
        row["currentGold"] = current_gold
    if attack_damage is not None:
        row["attackDamage"] = float(attack_damage)
    if ability_power is not None:
        row["abilityPower"] = float(ability_power)
    if armor is not None:
        row["armor"] = float(armor)
    if magic_resist is not None:
        row["magicResist"] = float(magic_resist)
    if attack_speed is not None:
        row["attackSpeed"] = float(attack_speed)
    if extra:
        row.update(extra)
    return row


def stats_update_line(
    *,
    game_id: int,
    game_time,  # canonical integer milliseconds
    participants: List[Dict[str, Any]],
    game_over: bool = False,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    row: Dict[str, Any] = {
        "rfc461Schema": "stats_update",
        "gameID": game_id,
        "gameTime": game_time,
        "gameOver": game_over,
        "participants": participants,
    }
    if extra:
        row.update(extra)
    return row


def game_end_line(
    *,
    game_id: int,
    game_time,
    winning_team: int = 0,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    row: Dict[str, Any] = {
        "rfc461Schema": "game_end",
        "gameID": game_id,
        "gameTime": game_time,
        "winningTeam": winning_team,
    }
    if extra:
        row.update(extra)
    return row


def champion_kill_line(
    *,
    game_id: int,
    game_time,
    killer_team_id: int,
    killer_id: Optional[int] = None,
    victim_id: Optional[int] = None,
    position: Optional[Dict[str, float]] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    row: Dict[str, Any] = {
        "rfc461Schema": "champion_kill",
        "gameID": game_id,
        "gameTime": game_time,
        "killerTeamID": killer_team_id,
    }
    if killer_id is not None:
        row["killerID"] = killer_id
    if victim_id is not None:
        row["victimID"] = victim_id
    if position:
        row["position"] = position
    if extra:
        row.update(extra)
    return row


def skill_used_line(
    *,
    game_id: int,
    game_time,
    participant_id: int,
    skill_slot: int,
    skill_name: str = "",
    position: Optional[Dict[str, float]] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    row: Dict[str, Any] = {
        "rfc461Schema": "skill_used",
        "gameID": game_id,
        "gameTime": game_time,
        "participantID": participant_id,
        "skillSlot": skill_slot,
        "skillName": skill_name,
    }
    if position:
        row["position"] = position
    if extra:
        row.update(extra)
    return row


def building_destroyed_line(
    *,
    game_id: int,
    game_time,
    team_id: int,
    building_type: str = "turret",
    lane: Optional[str] = None,
    turret_tier: Optional[str] = None,
    position: Optional[Dict[str, float]] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    row: Dict[str, Any] = {
        "rfc461Schema": "building_destroyed",
        "gameID": game_id,
        "gameTime": game_time,
        "teamID": team_id,
        "buildingType": building_type,
    }
    if lane is not None:
        row["lane"] = lane
    if turret_tier is not None:
        row["turretTier"] = turret_tier
    if position:
        row["position"] = position
    if extra:
        row.update(extra)
    return row


def epic_monster_kill_line(
    *,
    game_id: int,
    game_time,
    killer_team_id: int,
    monster_type: str,
    dragon_type: Optional[str] = None,
    position: Optional[Dict[str, float]] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    row: Dict[str, Any] = {
        "rfc461Schema": "epic_monster_kill",
        "gameID": game_id,
        "gameTime": game_time,
        "killerTeamID": killer_team_id,
        "monsterType": monster_type,
    }
    if dragon_type is not None:
        row["dragonType"] = dragon_type
    if position:
        row["position"] = position
    if extra:
        row.update(extra)
    return row


def write_jsonl(path, rows: Sequence[Dict[str, Any]]) -> None:
    import json
    from pathlib import Path

    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
