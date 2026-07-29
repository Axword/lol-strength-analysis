#!/usr/bin/env python3
"""
Convert GRID series event JSONL (or .zip) → research rfc461 JSONL.

This is a research / side-channel path for pro-play fixtures (paired with
``replay_riot_<seriesId>_1.rofl``). It is NOT a product calculatorReady source:

- Player HP/position/combat appear only on sparse ``includesFullState`` snapshots
  (game clock / NPC respawn clock / series start-end), not 1 Hz.
- Ability objects expose ready flags, not ranks → ``abilityRanksSource=unavailable``.
- Combat is incomplete (often armor only) → ``combatStatsSource=unavailable``.

Canonical product path remains Replay API positions + ROFL decrypt fuse
(``rofl-trusted-hp-v1`` / combat wire / UpgradeSpellAns ranks).

Usage:
  python3 scripts/grid_events_to_rfc461.py \\
    --input artifacts/pro-grid/events_2970110_grid.jsonl.zip \\
    --out artifacts/pro-grid/2970110/events.rfc461.research.jsonl
"""
from __future__ import annotations

import argparse
import json
import re
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Mapping, Optional, Sequence, Tuple

import rfc461_emit

HEALTH_SOURCE = "grid_series_state"
POSITION_SOURCE = "grid_series_state"
COMBAT_STATS_SOURCE = "unavailable"
ABILITY_RANKS_SOURCE = "unavailable"

CHAMP_ID_FIX = {
    "chogath": "Chogath",
    "missfortune": "MissFortune",
    "monkeyking": "MonkeyKing",
    "wukong": "MonkeyKing",
    "jarvaniv": "JarvanIV",
    "leesin": "LeeSin",
    "masteryi": "MasterYi",
    "tahmkench": "TahmKench",
    "xinzhao": "XinZhao",
    "aurelionsol": "AurelionSol",
    "belveth": "Belveth",
    "renataglasc": "Renata",
    "renata": "Renata",
    "nunu": "Nunu",
    "nunuwillump": "Nunu",
    "kogmaw": "KogMaw",
    "reksai": "RekSai",
    "ksante": "KSante",
    "drmundo": "DrMundo",
    "twistedfate": "TwistedFate",
    "khazix": "Khazix",
    "velkoz": "Velkoz",
}


def champ_id(raw: Any) -> str:
    text = str(raw or "").strip()
    if not text:
        return "Unknown"
    key = re.sub(r"[^a-z0-9]", "", text.lower())
    if key in CHAMP_ID_FIX:
        return CHAMP_ID_FIX[key]
    if " " not in text and text[:1].isupper():
        return text
    # "Lee Sin" → LeeSin via fix table; otherwise strip non-alnum and title-case.
    compact = re.sub(r"[^A-Za-z0-9]", "", text)
    return compact[:1].upper() + compact[1:] if compact else "Unknown"


def _parse_iso_ms(value: Any) -> Optional[int]:
    if not isinstance(value, str) or not value:
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def _side_to_team_id(side: Any, team_index: int = 0) -> int:
    text = str(side or "").strip().lower()
    if text in {"blue", "order", "100"}:
        return 100
    if text in {"red", "chaos", "200"}:
        return 200
    return 100 if team_index == 0 else 200


def _puuid_from_player(player: Mapping[str, Any]) -> str:
    for link in player.get("externalLinks") or []:
        if not isinstance(link, Mapping):
            continue
        provider = link.get("dataProvider") or {}
        name = ""
        if isinstance(provider, Mapping):
            name = str(provider.get("name") or "")
        if name.upper() != "RIOT_PUUID":
            continue
        entity = link.get("externalEntity") or {}
        if isinstance(entity, Mapping):
            pid = str(entity.get("id") or "").strip()
            if pid:
                return pid
    return ""


def _iter_jsonl_rows(path: Path) -> Iterator[dict]:
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as zf:
            names = [n for n in zf.namelist() if n.endswith(".jsonl")]
            if not names:
                raise ValueError(f"no .jsonl inside zip: {path}")
            with zf.open(names[0]) as fh:
                for raw in fh:
                    line = raw.decode("utf-8").strip()
                    if not line:
                        continue
                    row = json.loads(line)
                    if isinstance(row, dict):
                        yield row
        return
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            text = line.strip()
            if not text:
                continue
            row = json.loads(text)
            if isinstance(row, dict):
                yield row


def _walk_games(obj: Any) -> Iterator[Mapping[str, Any]]:
    if isinstance(obj, Mapping):
        teams = obj.get("teams")
        players_ok = False
        if isinstance(teams, list) and teams:
            for team in teams:
                if isinstance(team, Mapping) and isinstance(team.get("players"), list):
                    players_ok = True
                    break
        if players_ok and ("structures" in obj or "clock" in obj or obj.get("type") == "game"):
            yield obj
        for value in obj.values():
            yield from _walk_games(value)
    elif isinstance(obj, list):
        for value in obj:
            yield from _walk_games(value)


def _clock_seconds(game: Mapping[str, Any]) -> Optional[float]:
    clock = game.get("clock")
    if isinstance(clock, Mapping) and "currentSeconds" in clock:
        try:
            return float(clock["currentSeconds"])
        except (TypeError, ValueError):
            return None
    return None


def _skill_slot(ability_name: str) -> int:
    text = str(ability_name or "").lower()
    if text.endswith("-q") or text.endswith("_q") or text.endswith(" q"):
        return 1
    if text.endswith("-w") or text.endswith("_w"):
        return 2
    if text.endswith("-e") or text.endswith("_e"):
        return 3
    if text.endswith("-r") or text.endswith("_r"):
        return 4
    return 0


def _monster_type_from_event(event_type: str) -> Tuple[str, Optional[str]]:
    t = event_type.lower()
    if "baron" in t:
        return "baron", None
    if "herald" in t:
        return "riftHerald", None
    if "voidgrub" in t:
        return "voidGrub", None
    if "elder" in t:
        return "dragon", "ELDER"
    for name in (
        "infernal",
        "cloud",
        "chemtech",
        "mountain",
        "ocean",
        "hextech",
    ):
        if name in t:
            return "dragon", name.upper()
    if "dragon" in t or "drake" in t:
        return "dragon", None
    if "scuttler" in t:
        return "riftScuttler", None
    if "atakhan" in t:
        return "atakhan", None
    return "unknown", None


@dataclass
class PlayerState:
    grid_id: str
    name: str
    team_id: int
    champion_name: str = "Unknown"
    puuid: str = ""
    participant_id: int = 0
    level: int = 1
    alive: bool = True
    health: Optional[float] = None
    health_max: Optional[float] = None
    position: Optional[Dict[str, float]] = None
    armor: Optional[float] = None
    kills: int = 0
    deaths: int = 0
    assists: int = 0
    total_gold: Optional[float] = None
    vision_score: Optional[float] = None


@dataclass
class Converter:
    series_id: str = ""
    game_id: int = 0
    game_start_ms: Optional[int] = None
    players_by_grid: Dict[str, PlayerState] = field(default_factory=dict)
    pick_order: List[str] = field(default_factory=list)
    stats_emitted_times: List[int] = field(default_factory=list)
    event_counts: Dict[str, int] = field(default_factory=dict)

    def ensure_player(
        self,
        grid_id: str,
        *,
        name: str = "",
        team_id: int = 100,
        champion_name: str = "",
        puuid: str = "",
    ) -> PlayerState:
        key = str(grid_id)
        player = self.players_by_grid.get(key)
        if player is None:
            player = PlayerState(
                grid_id=key,
                name=name or key,
                team_id=int(team_id),
                champion_name=champ_id(champion_name) if champion_name else "Unknown",
                puuid=puuid or "",
            )
            self.players_by_grid[key] = player
            if key not in self.pick_order:
                self.pick_order.append(key)
        else:
            if name:
                player.name = name
            if team_id:
                player.team_id = int(team_id)
            if champion_name:
                player.champion_name = champ_id(champion_name)
            if puuid:
                player.puuid = puuid
        return player

    def assign_participant_ids(self) -> None:
        blue = [gid for gid in self.pick_order if self.players_by_grid[gid].team_id == 100]
        red = [gid for gid in self.pick_order if self.players_by_grid[gid].team_id == 200]
        # Stable fallback: unknown sides after known blues then reds.
        rest = [
            gid
            for gid in self.pick_order
            if gid not in blue and gid not in red
        ]
        ordered = blue + red + rest
        for index, gid in enumerate(ordered, start=1):
            self.players_by_grid[gid].participant_id = index

    def game_time_ms(self, envelope: Mapping[str, Any], event: Mapping[str, Any]) -> int:
        for game in _walk_games(event):
            seconds = _clock_seconds(game)
            if seconds is not None and seconds >= 0:
                return int(round(seconds * 1000.0))
        occurred = _parse_iso_ms(envelope.get("occurredAt"))
        if occurred is not None and self.game_start_ms is not None:
            return max(0, occurred - self.game_start_ms)
        return 0

    def ingest_roster_from_game(self, game: Mapping[str, Any]) -> None:
        teams = game.get("teams") or []
        if not isinstance(teams, list):
            return
        for team_index, team in enumerate(teams):
            if not isinstance(team, Mapping):
                continue
            team_id = _side_to_team_id(team.get("side"), team_index)
            for player in team.get("players") or []:
                if not isinstance(player, Mapping):
                    continue
                gid = str(player.get("id") or "").strip()
                if not gid:
                    continue
                character = player.get("character") or {}
                champ = ""
                if isinstance(character, Mapping):
                    champ = str(character.get("name") or "")
                self.ensure_player(
                    gid,
                    name=str(player.get("name") or gid),
                    team_id=team_id,
                    champion_name=champ,
                    puuid=_puuid_from_player(player),
                )
                state = self.players_by_grid[gid]
                if "alive" in player:
                    state.alive = bool(player.get("alive"))
                if "currentHealth" in player and "maxHealth" in player:
                    try:
                        state.health = float(player["currentHealth"])
                        state.health_max = float(player["maxHealth"])
                    except (TypeError, ValueError):
                        pass
                pos = player.get("position")
                if isinstance(pos, Mapping) and "x" in pos and "y" in pos:
                    try:
                        # Grid uses {x,y}; rfc461 live-stats uses {x,z}.
                        state.position = {
                            "x": float(pos["x"]),
                            "z": float(pos["y"]),
                        }
                    except (TypeError, ValueError):
                        pass
                if "currentArmor" in player:
                    try:
                        state.armor = float(player["currentArmor"])
                    except (TypeError, ValueError):
                        pass
                for key_src, attr in (
                    ("kills", "kills"),
                    ("deaths", "deaths"),
                    ("killAssistsGiven", "assists"),
                ):
                    if key_src in player:
                        try:
                            setattr(state, attr, int(player[key_src]))
                        except (TypeError, ValueError):
                            pass
                if "netWorth" in player:
                    try:
                        state.total_gold = float(player["netWorth"])
                    except (TypeError, ValueError):
                        pass
                if "visionScore" in player:
                    try:
                        state.vision_score = float(player["visionScore"])
                    except (TypeError, ValueError):
                        pass
                # Level from increaseLevel completions when present on series/game nested blobs.
                series_blob = player.get("series")
                if isinstance(series_blob, Mapping):
                    # some feeds stash completionCount elsewhere; keep level bumps from events
                    pass

    def apply_level_up(self, grid_id: str) -> None:
        player = self.players_by_grid.get(str(grid_id))
        if player is None:
            player = self.ensure_player(str(grid_id))
        player.level = max(1, int(player.level) + 1)

    def participant_rows(self, *, include_sparse_combat_hint: bool = False) -> List[dict]:
        rows: List[dict] = []
        ordered = sorted(
            self.players_by_grid.values(),
            key=lambda p: (p.participant_id or 999, p.grid_id),
        )
        for player in ordered:
            if player.participant_id <= 0:
                continue
            health_known = player.health is not None and player.health_max is not None
            pos = player.position or rfc461_emit.fountain_for_team(player.team_id)
            career = None
            career_sources = None
            # Career only when we have an honest sample from Grid state.
            if player.kills or player.deaths or player.assists or player.vision_score is not None:
                career = {
                    "kills": player.kills,
                    "deaths": player.deaths,
                    "assists": player.assists,
                }
                if player.vision_score is not None:
                    career["visionScore"] = player.vision_score
                career_sources = {key: "grid_series_state" for key in career}
            row = rfc461_emit.participant_row(
                participant_id=player.participant_id,
                team_id=player.team_id,
                champion_name=player.champion_name,
                player_name=player.name,
                position=pos,
                position_source=POSITION_SOURCE if player.position else "grid_fountain_fallback",
                alive=player.alive,
                level=player.level,
                health=float(player.health or 0.0),
                health_max=float(player.health_max or 0.0),
                health_known=health_known,
                health_source=HEALTH_SOURCE if health_known else "unavailable",
                combat_stats_source=COMBAT_STATS_SOURCE,
                ability_ranks_source=ABILITY_RANKS_SOURCE,
                total_gold=player.total_gold,
                ability_levels=(0, 0, 0, 0),
                armor=player.armor if include_sparse_combat_hint else None,
                career=career,
                career_sources=career_sources,
                career_sample_game_time_ms=self.stats_emitted_times[-1]
                if career and self.stats_emitted_times
                else (0 if career else None),
                extra={
                    "gridPlayerId": player.grid_id,
                    "puuid": player.puuid or None,
                },
            )
            # Never claim combat known via armor-only: strip armor unless we keep
            # combat unavailable (consumer treats unavailable as unknown).
            if COMBAT_STATS_SOURCE == "unavailable":
                row.pop("armor", None)
            if not player.puuid:
                row.pop("puuid", None)
            rows.append(row)
        return rows


def convert_grid_events(
    rows: Iterable[Mapping[str, Any]],
    *,
    series_id_hint: str = "",
) -> Tuple[List[dict], Dict[str, Any]]:
    conv = Converter(series_id=str(series_id_hint or ""))
    out: List[dict] = []
    pending_events: List[dict] = []

    for envelope in rows:
        if not conv.series_id:
            conv.series_id = str(envelope.get("seriesId") or series_id_hint or "")
        try:
            conv.game_id = int(conv.series_id) if str(conv.series_id).isdigit() else 0
        except ValueError:
            conv.game_id = 0

        for event in envelope.get("events") or []:
            if not isinstance(event, Mapping):
                continue
            event_type = str(event.get("type") or "")
            conv.event_counts[event_type] = conv.event_counts.get(event_type, 0) + 1

            if event_type == "team-picked-character":
                actor = event.get("actor") or {}
                target = event.get("target") or {}
                team = actor if actor.get("type") == "team" else {}
                character = target if target.get("type") == "character" else target
                # player id sometimes on target/state
                player_state = None
                for node in (target, actor, event.get("actor"), event.get("target")):
                    if isinstance(node, Mapping) and node.get("type") == "player":
                        player_state = node
                champ_name = ""
                if isinstance(character, Mapping):
                    st = character.get("state") or character.get("stateDelta") or character
                    if isinstance(st, Mapping):
                        champ_name = str(st.get("name") or character.get("name") or "")
                    else:
                        champ_name = str(character.get("name") or "")
                team_state = (team.get("state") or team.get("stateDelta") or team) if isinstance(team, Mapping) else {}
                side = team_state.get("side") if isinstance(team_state, Mapping) else None
                team_id = _side_to_team_id(side, 0)
                if player_state and isinstance(player_state, Mapping):
                    gid = str(player_state.get("id") or "")
                    pname = str((player_state.get("state") or {}).get("name") or player_state.get("name") or gid)
                    if gid:
                        conv.ensure_player(
                            gid,
                            name=pname,
                            team_id=team_id,
                            champion_name=champ_name,
                        )

            if event_type == "series-started-game":
                occurred = _parse_iso_ms(envelope.get("occurredAt"))
                if occurred is not None:
                    conv.game_start_ms = occurred

            for game in _walk_games(event):
                conv.ingest_roster_from_game(game)

            game_time = conv.game_time_ms(envelope, event)

            if event_type == "player-completed-increaseLevel":
                actor = event.get("actor") or {}
                if actor.get("type") == "player":
                    conv.apply_level_up(str(actor.get("id") or ""))

            # Discrete rfc461 events (identity resolved after roster assign).
            pending_events.append(
                {
                    "type": event_type,
                    "gameTime": game_time,
                    "event": event,
                    "envelope": envelope,
                }
            )

            # Sparse stats snapshots when full player HP state is present.
            if event.get("includesFullState"):
                games = list(_walk_games(event))
                if games and any(
                    isinstance(p, Mapping) and "currentHealth" in p
                    for g in games
                    for t in (g.get("teams") or [])
                    if isinstance(t, Mapping)
                    for p in (t.get("players") or [])
                ):
                    # Defer emit until participant ids assigned — store marker.
                    pending_events.append(
                        {
                            "type": "__stats_snapshot__",
                            "gameTime": game_time,
                            "event": event,
                            "envelope": envelope,
                        }
                    )

    if not conv.players_by_grid:
        raise ValueError("no players discovered in Grid feed")
    conv.assign_participant_ids()

    decoded = [
        "roster",
        "puuid",
        "sparse_positions",
        "sparse_hp",
        "kills",
        "abilities_used",
        "objectives",
        "structures",
        "items",
    ]
    missing = [
        "1hz_positions",
        "ability_ranks",
        "full_combat_stats",
        "calculatorReady",
    ]
    provenance = rfc461_emit.provenance_record(
        source=f"grid_series:{conv.series_id}",
        source_kind="grid_series_events",
        position_coverage="sparse_full_state_only",
        hp_coverage="sparse_full_state_only",
        roster_mapping="grid_player_id_puuid",
        notes=(
            "Research adapter only. Do not publish as product calculatorReady. "
            "Pair with replay_riot_<seriesId>_1.rofl for decrypt/Replay API work."
        ),
        artifact=f"events_{conv.series_id}_grid.jsonl",
    )
    out.append(
        rfc461_emit.coverage_line(
            source=f"grid_series:{conv.series_id}",
            game_id=conv.game_id,
            decoded=decoded,
            missing=missing,
            notes=provenance["notes"],
            provenance=provenance,
            extra={
                "productEligible": False,
                "calculatorReady": False,
                "gridSeriesId": conv.series_id,
            },
        )
    )

    game_participants = []
    for player in sorted(conv.players_by_grid.values(), key=lambda p: p.participant_id):
        if player.participant_id <= 0:
            continue
        game_participants.append(
            {
                "participantID": player.participant_id,
                "teamID": player.team_id,
                "championName": player.champion_name,
                "summonerName": player.name,
                "playerName": player.name,
                "puuid": player.puuid or None,
                "gridPlayerId": player.grid_id,
            }
        )
    out.append(
        rfc461_emit.game_info_line(
            game_id=conv.game_id,
            participants=game_participants,
            game_name=f"GRID series {conv.series_id}",
            platform_id="GRID",
            stats_update_interval_ms=0,
            extra={"gridSeriesId": conv.series_id, "productEligible": False},
        )
    )

    gid_to_participant = {
        p.grid_id: p.participant_id for p in conv.players_by_grid.values() if p.participant_id > 0
    }

    def _actor_participant(event: Mapping[str, Any]) -> Optional[int]:
        actor = event.get("actor") or {}
        if isinstance(actor, Mapping) and actor.get("type") == "player":
            return gid_to_participant.get(str(actor.get("id") or ""))
        return None

    def _target_participant(event: Mapping[str, Any]) -> Optional[int]:
        target = event.get("target") or {}
        if isinstance(target, Mapping) and target.get("type") == "player":
            return gid_to_participant.get(str(target.get("id") or ""))
        return None

    winning_team = 0
    end_time = 0
    last_stats_time = -1

    for item in pending_events:
        event_type = item["type"]
        game_time = int(item["gameTime"])
        event = item["event"]

        if event_type == "__stats_snapshot__":
            # Refresh roster/HP from this event before emit.
            for game in _walk_games(event):
                conv.ingest_roster_from_game(game)
            if game_time == last_stats_time:
                continue
            conv.stats_emitted_times.append(game_time)
            out.append(
                rfc461_emit.stats_update_line(
                    game_id=conv.game_id,
                    game_time=game_time,
                    participants=conv.participant_rows(),
                    extra={"gridSnapshot": True, "productEligible": False},
                )
            )
            last_stats_time = game_time
            continue

        if event_type == "player-killed-player":
            killer = _actor_participant(event)
            victim = _target_participant(event)
            killer_team = 0
            if killer:
                for p in conv.players_by_grid.values():
                    if p.participant_id == killer:
                        killer_team = p.team_id
                        p.kills += 1
                        break
            if victim:
                for p in conv.players_by_grid.values():
                    if p.participant_id == victim:
                        p.deaths += 1
                        p.alive = False
                        break
            out.append(
                rfc461_emit.champion_kill_line(
                    game_id=conv.game_id,
                    game_time=game_time,
                    killer_team_id=killer_team,
                    killer_id=killer,
                    victim_id=victim,
                )
            )
        elif event_type == "game-respawned-player":
            target = event.get("target") or event.get("actor") or {}
            if isinstance(target, Mapping) and target.get("type") == "player":
                pid = gid_to_participant.get(str(target.get("id") or ""))
                if pid:
                    for p in conv.players_by_grid.values():
                        if p.participant_id == pid:
                            p.alive = True
        elif event_type == "player-used-ability":
            pid = _actor_participant(event)
            target = event.get("target") or {}
            skill_name = ""
            if isinstance(target, Mapping):
                st = target.get("state") or target.get("stateDelta") or target
                if isinstance(st, Mapping):
                    skill_name = str(st.get("name") or st.get("id") or "")
            if pid:
                out.append(
                    rfc461_emit.skill_used_line(
                        game_id=conv.game_id,
                        game_time=game_time,
                        participant_id=pid,
                        skill_slot=_skill_slot(skill_name),
                        skill_name=skill_name,
                    )
                )
        elif "destroyTower" in event_type or event_type.endswith("destroyed-tower"):
            actor = event.get("actor") or {}
            team_id = 0
            if isinstance(actor, Mapping):
                if actor.get("type") == "team":
                    st = actor.get("state") or {}
                    team_id = _side_to_team_id(st.get("side") if isinstance(st, Mapping) else None)
                elif actor.get("type") == "player":
                    pid = gid_to_participant.get(str(actor.get("id") or ""))
                    for p in conv.players_by_grid.values():
                        if p.participant_id == pid:
                            team_id = p.team_id
                            break
            out.append(
                rfc461_emit.building_destroyed_line(
                    game_id=conv.game_id,
                    game_time=game_time,
                    team_id=team_id,
                    building_type="turret",
                )
            )
        elif "destroyNexus" in event_type or "destroyed-base" in event_type:
            actor = event.get("actor") or {}
            team_id = 0
            if isinstance(actor, Mapping) and actor.get("type") == "player":
                pid = gid_to_participant.get(str(actor.get("id") or ""))
                for p in conv.players_by_grid.values():
                    if p.participant_id == pid:
                        team_id = p.team_id
                        break
            out.append(
                rfc461_emit.building_destroyed_line(
                    game_id=conv.game_id,
                    game_time=game_time,
                    team_id=team_id,
                    building_type="nexus",
                )
            )
        elif "slay" in event_type and (
            "Dragon" in event_type
            or "Drake" in event_type
            or "Baron" in event_type
            or "Herald" in event_type
            or "VoidGrub" in event_type
            or "Atakhan" in event_type
            or "Scuttler" in event_type
        ):
            monster, dragon = _monster_type_from_event(event_type)
            pid = _actor_participant(event)
            team_id = 0
            if pid:
                for p in conv.players_by_grid.values():
                    if p.participant_id == pid:
                        team_id = p.team_id
                        break
            out.append(
                rfc461_emit.epic_monster_kill_line(
                    game_id=conv.game_id,
                    game_time=game_time,
                    killer_team_id=team_id,
                    monster_type=monster,
                    dragon_type=dragon,
                )
            )
        elif event_type == "player-purchased-item":
            pid = _actor_participant(event)
            target = event.get("target") or {}
            item_id = 0
            if isinstance(target, Mapping):
                st = target.get("state") or target.get("stateDelta") or {}
                if isinstance(st, Mapping):
                    # Grid item ids are UUIDs; keep 0 and name in extra.
                    raw_name = str(st.get("name") or st.get("id") or "")
                else:
                    raw_name = ""
            else:
                raw_name = ""
            if pid:
                out.append(
                    rfc461_emit.item_purchased_line(
                        game_id=conv.game_id,
                        game_time=game_time,
                        participant_id=pid,
                        item_id=item_id,
                        extra={"gridItem": raw_name} if raw_name else None,
                    )
                )
        elif event_type in {"team-won-game", "team-won-series"}:
            actor = event.get("actor") or {}
            if isinstance(actor, Mapping) and actor.get("type") == "team":
                st = actor.get("state") or {}
                winning_team = _side_to_team_id(
                    st.get("side") if isinstance(st, Mapping) else None
                )
            end_time = max(end_time, game_time)
        elif event_type == "series-ended-game":
            end_time = max(end_time, game_time)

    if last_stats_time < 0:
        # Guarantee at least one stats_update for timeline builders.
        conv.stats_emitted_times.append(0)
        out.append(
            rfc461_emit.stats_update_line(
                game_id=conv.game_id,
                game_time=0,
                participants=conv.participant_rows(),
                extra={"gridSnapshot": True, "productEligible": False},
            )
        )

    if end_time or winning_team:
        out.append(
            rfc461_emit.game_end_line(
                game_id=conv.game_id,
                game_time=end_time,
                winning_team=winning_team,
            )
        )

    summary = {
        "seriesId": conv.series_id,
        "gameId": conv.game_id,
        "participants": len(game_participants),
        "statsUpdates": sum(1 for r in out if r.get("rfc461Schema") == "stats_update"),
        "championKills": sum(1 for r in out if r.get("rfc461Schema") == "champion_kill"),
        "skillUsed": sum(1 for r in out if r.get("rfc461Schema") == "skill_used"),
        "productEligible": False,
        "calculatorReady": False,
        "eventCounts": dict(sorted(conv.event_counts.items(), key=lambda kv: (-kv[1], kv[0]))),
    }
    return out, summary


def rofl_stats_identities(rofl_path: Path) -> Dict[str, Any]:
    """Read trailing ROFL2 statsJson identities without requiring product filenames.

    Axword dump names are ``replay_riot_<gridSeriesId>_1.rofl`` — not
    ``<PLATFORM>-<matchCode>.rofl`` — so ``inspect_rofl_metadata`` cannot be used
    until files are renamed/mapped to Riot match codes.
    """
    from rofl_metadata import parse_rofl2_metadata_bytes, participant_from_stats

    data = rofl_path.read_bytes()
    parsed = parse_rofl2_metadata_bytes(data)
    metadata = parsed["metadata"]
    raw = metadata.get("statsJson")
    if isinstance(raw, str):
        raw = json.loads(raw)
    players = [dict(row) for row in (raw or []) if isinstance(row, Mapping)]
    participants = [
        participant_from_stats(player, index) for index, player in enumerate(players)
    ]
    puuids: List[str] = []
    riot_ids: List[str] = []
    for participant in participants:
        identity = participant.get("sourceIdentity") or {}
        puuid = str(
            identity.get("puuid") or participant.get("puuid") or ""
        ).strip()
        if puuid:
            puuids.append(puuid)
        riot = identity.get("riotId") or participant.get("riotId") or {}
        if isinstance(riot, Mapping):
            full = str(riot.get("full") or "").strip()
        else:
            full = str(riot or "").strip()
        if full:
            riot_ids.append(full)
    puuids = sorted(set(puuids))
    riot_ids = sorted(set(riot_ids))
    try:
        duration_ms = int(metadata.get("gameLength") or 0)
    except (TypeError, ValueError):
        duration_ms = 0
    return {
        "path": str(rofl_path),
        "playerCount": len(participants),
        "puuids": puuids,
        "riotIds": riot_ids,
        "durationMs": duration_ms,
        "productFilenameOk": bool(
            re.fullmatch(r"[A-Za-z0-9]+-\d{7,}\.rofl", rofl_path.name)
        ),
    }


def join_grid_rofl(
    *,
    grid_rows: Sequence[Mapping[str, Any]],
    rofl_path: Path,
    series_id_hint: str = "",
) -> Dict[str, Any]:
    """Compare Grid roster PUUIDs to ROFL statsJson PUUIDs (same-match check)."""
    rfc_rows, summary = convert_grid_events(grid_rows, series_id_hint=series_id_hint)
    game_info = next(r for r in rfc_rows if r.get("rfc461Schema") == "game_info")
    grid_puuids = sorted(
        {
            str(p.get("puuid") or "").strip()
            for p in game_info.get("participants") or []
            if str(p.get("puuid") or "").strip()
        }
    )
    rofl = rofl_stats_identities(rofl_path)
    rofl_puuids = set(rofl["puuids"])
    grid_set = set(grid_puuids)
    overlap = sorted(grid_set & rofl_puuids)
    only_grid = sorted(grid_set - rofl_puuids)
    only_rofl = sorted(rofl_puuids - grid_set)
    return {
        "seriesId": summary["seriesId"],
        "sameMatchLikely": len(overlap) >= 8 and not only_grid and len(only_rofl) <= 2,
        "overlapCount": len(overlap),
        "gridPuuidCount": len(grid_puuids),
        "roflPuuidCount": len(rofl_puuids),
        "overlapPuids": overlap,
        "onlyGrid": only_grid,
        "onlyRofl": only_rofl,
        "rofl": {
            "path": rofl["path"],
            "durationMs": rofl["durationMs"],
            "productFilenameOk": rofl["productFilenameOk"],
            "playerCount": rofl["playerCount"],
        },
        "note": (
            "Rename/map replay_riot_<seriesId>_1.rofl → <PLATFORM>-<riotMatchCode>.rofl "
            "before npm run rofl:ingest; Grid seriesId is not the Riot match code."
        ),
    }


def build_pair_manifest(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    pairs: List[dict] = []
    rofl_ids = set()
    grid_ids = set()
    riot_by_series: Dict[str, List[str]] = {}
    for path in sorted(root.glob("replay_riot_*_1.rofl")):
        m = re.match(r"replay_riot_(\d+)_1\.rofl$", path.name)
        if m:
            rofl_ids.add(m.group(1))
    for path in sorted(root.glob("events_*_grid.jsonl.zip")):
        m = re.match(r"events_(\d+)_grid\.jsonl\.zip$", path.name)
        if m:
            grid_ids.add(m.group(1))
    for path in sorted(root.glob("events_*_grid.jsonl")):
        m = re.match(r"events_(\d+)_grid\.jsonl$", path.name)
        if m:
            grid_ids.add(m.group(1))
    for path in sorted(root.glob("events_*_*_riot.jsonl")):
        m = re.match(r"events_(\d+)_(\d+)_riot\.jsonl$", path.name)
        if m:
            riot_by_series.setdefault(m.group(1), []).append(path.name)
    all_ids = sorted(
        rofl_ids | grid_ids | set(riot_by_series),
        key=lambda x: int(x) if x.isdigit() else x,
    )
    for series_id in all_ids:
        pair: Dict[str, Any] = {
            "seriesId": series_id,
            "rofl": f"replay_riot_{series_id}_1.rofl" if series_id in rofl_ids else None,
            "gridZip": f"events_{series_id}_grid.jsonl.zip"
            if series_id in grid_ids
            else None,
            "riotJsonl": riot_by_series.get(series_id) or [],
            "paired": series_id in rofl_ids and series_id in grid_ids,
            "productFilenameOk": False,
            "puuidJoin": None,
        }
        if pair["rofl"]:
            rofl_path = root / pair["rofl"]
            try:
                identities = rofl_stats_identities(rofl_path)
                pair["productFilenameOk"] = identities["productFilenameOk"]
                pair["roflDurationMs"] = identities["durationMs"]
                pair["roflPuuidCount"] = len(identities["puuids"])
            except Exception as exc:  # noqa: BLE001 - manifest must stay resilient
                pair["roflError"] = f"{type(exc).__name__}: {exc}"
        if pair["paired"] and pair["rofl"] and pair["gridZip"]:
            try:
                grid_path = root / pair["gridZip"]
                join = join_grid_rofl(
                    grid_rows=list(_iter_jsonl_rows(grid_path)),
                    rofl_path=root / pair["rofl"],
                    series_id_hint=series_id,
                )
                pair["puuidJoin"] = {
                    "sameMatchLikely": join["sameMatchLikely"],
                    "overlapCount": join["overlapCount"],
                    "gridPuuidCount": join["gridPuuidCount"],
                    "roflPuuidCount": join["roflPuuidCount"],
                }
            except Exception as exc:  # noqa: BLE001
                pair["puuidJoinError"] = f"{type(exc).__name__}: {exc}"
        pairs.append(pair)
    return {
        "schema": "pro-grid-pair-manifest-v1",
        "root": str(root),
        "pairedCount": sum(1 for p in pairs if p["paired"]),
        "sameMatchLikelyCount": sum(
            1
            for p in pairs
            if (p.get("puuidJoin") or {}).get("sameMatchLikely")
        ),
        "riotLiveStatsSeriesCount": sum(1 for p in pairs if p.get("riotJsonl")),
        "pairs": pairs,
        "notes": (
            "Local Axword/MEGA pro-play dump. Gitignored. "
            "Prefer dense events_*_*_riot.jsonl (grid_riot_events_to_rfc461) for timelines; "
            "Grid zip remains a sparse side channel (grid_events_to_rfc461). "
            "ROFL filenames are Grid series ids, not Riot PLATFORM-matchCode — "
            "derive rename from riot live-stats game_info (npm run grid:rename-report)."
        ),
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, help="Grid events .jsonl or .jsonl.zip")
    parser.add_argument("--out", type=Path, help="Output rfc461 research JSONL path")
    parser.add_argument(
        "--series-id",
        default="",
        help="Optional series id hint when missing from envelopes",
    )
    parser.add_argument(
        "--write-manifest",
        type=Path,
        help="Write pair manifest for a pro-grid directory (no convert)",
    )
    parser.add_argument(
        "--summary",
        type=Path,
        help="Optional JSON summary path",
    )
    parser.add_argument(
        "--join-rofl",
        type=Path,
        help="Optional ROFL path; emit PUUID join report (same-match check)",
    )
    args = parser.parse_args(argv)

    if args.write_manifest:
        manifest = build_pair_manifest(args.write_manifest)
        out_path = args.write_manifest / "MANIFEST.json"
        out_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        print(
            json.dumps(
                {
                    "ok": True,
                    "manifest": str(out_path),
                    "pairedCount": manifest["pairedCount"],
                    "sameMatchLikelyCount": manifest["sameMatchLikelyCount"],
                },
                indent=2,
            )
        )
        return 0

    if not args.input or not args.out:
        parser.error("--input and --out are required unless --write-manifest is set")

    rows = list(_iter_jsonl_rows(args.input))
    rfc_rows, summary = convert_grid_events(rows, series_id_hint=args.series_id)
    rfc461_emit.write_jsonl(args.out, rfc_rows)
    summary["out"] = str(args.out)
    summary["input"] = str(args.input)
    if args.join_rofl:
        summary["puuidJoin"] = join_grid_rofl(
            grid_rows=rows,
            rofl_path=args.join_rofl,
            series_id_hint=args.series_id or summary.get("seriesId") or "",
        )
    if args.summary:
        args.summary.parent.mkdir(parents=True, exist_ok=True)
        args.summary.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, **summary}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
