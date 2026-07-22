#!/usr/bin/env python3
"""
Convert maknee-style decoded replay packets → events_*_riot.jsonl (rfc461).

Downstream half of the ROFL hard path: once packets are decrypted into this
shape, the same mapper feeds rebuild/enrich. Accepts a match JSON with an
"events" list, or a HuggingFace .jsonl / .jsonl.gz batch via --line N.

Example:
  python3 scripts/maknee_packets_to_jsonl.py \\
    docs/rofl-research/fixtures/maknee_match_stub.json \\
    -o /tmp/events_maknee.jsonl --hz 1
"""
from __future__ import annotations

import argparse
import gzip
import json
import math
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Live-stats units/sec — ~base MS so sparse WaypointGroup destinations walk
# instead of teleporting between 1 Hz samples.
DEFAULT_MOVE_SPEED = 375.0
MAX_PATH_DRAIN_SECONDS = 180.0

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rfc461_emit import (  # noqa: E402
    barracks_minion_killed_line,
    barracks_minion_spawn_line,
    building_destroyed_line,
    champion_kill_line,
    coverage_line,
    epic_monster_kill_line,
    fountain_for_team,
    game_end_line,
    game_info_line,
    item_purchased_line,
    neutral_minion_spawn_line,
    participant_row,
    provenance_record,
    skill_level_up_line,
    skill_used_line,
    stats_update_line,
    to_live_stats_coords,
    ward_killed_line,
    ward_placed_line,
    write_jsonl,
)
from rofl_replication_fields import (  # noqa: E402
    apply_replication_value,
    resolve_combat_stats,
)

# CreateNeutral skin_name → (monsterType, dragonType|None)
EPIC_NEUTRALS = {
    "SRU_Dragon_Air": ("dragon", "air"),
    "SRU_Dragon_Fire": ("dragon", "fire"),
    "SRU_Dragon_Water": ("dragon", "water"),
    "SRU_Dragon_Earth": ("dragon", "earth"),
    "SRU_Dragon_Hextech": ("dragon", "hextech"),
    "SRU_Dragon_Chemtech": ("dragon", "chemtech"),
    "SRU_Dragon_Elder": ("dragon", "elder"),
    "SRU_Baron": ("baron", None),
    "SRU_RiftHerald": ("riftHerald", None),
    # Void grubs / voidmites — FUR live-stats uses monsterType "VoidGrub"
    "SRU_VoidGrub": ("VoidGrub", None),
    "SRU_Horde": ("VoidGrub", None),
}

# Synthetic 375 u/s path walking is fixture/research movement only.
POSITION_SYNTHESIS = "waypoint_path_walk_375_ups"
SYNTHETIC_SOURCE_KIND = "decoded_replay_packets_synthetic_path"


def _synthetic_path_provenance() -> Dict[str, Any]:
    """Provenance for WaypointGroup path-walked positions (not native product)."""
    prov = provenance_record(
        source="maknee_decoded_packets",
        source_kind=SYNTHETIC_SOURCE_KIND,
        position_coverage="partial",
        hp_coverage="partial",
        roster_mapping="CreateHero_order_1_to_10",
        artifact="maknee-shaped events[]",
        notes=(
            "Waypoint coordinates are centered and shifted by +7500 into "
            "live-stats space; multi-point / sparse destinations are walked "
            f"at ~{DEFAULT_MOVE_SPEED:g} u/s between stats_update samples "
            f"({POSITION_SYNTHESIS}). This is synthetic fixture movement, not "
            "native full_at_sampled_frames product evidence. "
            "Ability ranks from SkillLevelUp/CastSpellAns when present; "
            "VoidGrub via CreateNeutral naming."
        ),
    )
    prov["positionSynthesis"] = POSITION_SYNTHESIS
    prov["researchOnly"] = True
    prov["publicationBlocked"] = True
    return prov


def _packet_time(payload: dict) -> Optional[float]:
    t = payload.get("time")
    if t is None:
        return None
    try:
        return float(t)
    except (TypeError, ValueError):
        return None

def _rep_value(data: dict) -> Optional[float]:
    if not isinstance(data, dict):
        return None
    for k in ("Float", "Int", "Uint", "Bool"):
        if k in data:
            try:
                return float(data[k])
            except (TypeError, ValueError):
                return None
    return None


def _load_match(path: Path, line: int = 0) -> dict:
    name = path.name.lower()
    if name.endswith(".jsonl.gz") or name.endswith(".jsonl"):
        opener = gzip.open if name.endswith(".gz") else open
        with opener(path, "rt", encoding="utf-8") as f:
            for i, raw in enumerate(f):
                if i == line:
                    match = json.loads(raw)
                    break
            else:
                raise SystemExit(f"line {line} out of range in {path}")
    else:
        match = json.loads(path.read_text(encoding="utf-8"))

    if "events" in match:
        return match
    if "match" in match and isinstance(match["match"], dict) and "events" in match["match"]:
        return match["match"]
    raise SystemExit("expected JSON object with top-level 'events'")


def _heroes(events: List[dict]) -> List[dict]:
    out: List[dict] = []
    seen = set()
    for e in events:
        h = e.get("CreateHero")
        if not h:
            continue
        net_id = int(h["net_id"])
        if net_id in seen:
            continue
        seen.add(net_id)
        out.append(
            {
                "net_id": net_id,
                "waypoint_id": len(out) + 1,
                "name": h.get("name") or f"id{net_id}",
                "champion": h.get("champion") or "Unknown",
            }
        )
        if len(out) >= 10:
            break
    for i, h in enumerate(out):
        h["participantID"] = i + 1
        h["teamID"] = 100 if i < 5 else 200
    return out


def _parse_turret_meta(name: str) -> Tuple[int, Optional[str], Optional[str]]:
    """Return (owner_team_id, lane, tier) best-effort from CreateTurret name."""
    # Turret_T1_* = blue (100), Turret_T2_* = red (200)
    team = 100
    if "_T2_" in name or "Chaos" in name:
        team = 200
    elif "_T1_" in name or "Order" in name:
        team = 100
    lane = None
    if "_L_" in name:
        lane = "top"
    elif "_R_" in name:
        lane = "bottom"
    elif "_C_" in name:
        lane = "mid"
    tier = None
    m = re.search(r"_(\d{2})_A$", name)
    if m:
        tier = m.group(1)
    return team, lane, tier


def _event_time(ev: dict) -> float:
    if not ev:
        return 0.0
    payload = ev.get(next(iter(ev)))
    if not isinstance(payload, dict):
        return 0.0
    t = _packet_time(payload)
    return 0.0 if t is None else t


def _sort_events(events: List[dict]) -> List[dict]:
    """Stable time order — out-of-order packets otherwise skip early waypoints."""
    return sorted(events, key=_event_time)


def _as_live_point(pt: dict) -> Tuple[float, float]:
    return to_live_stats_coords(
        float(pt["x"]), float(pt.get("z", pt.get("y", 0)))
    )


def convert(match: dict, hz: float = 1.0, game_id: int = 0) -> List[dict]:
    events = _sort_events(list(match["events"]))
    heroes = _heroes(events)
    if not heroes:
        raise SystemExit("no CreateHero packets found")

    by_net = {h["net_id"]: h for h in heroes}
    by_wp = {h["waypoint_id"]: h for h in heroes}

    # Live state
    pos: Dict[int, Tuple[float, float]] = {}  # waypoint_id → xz
    # Remaining path destinations in live-stats space (walked at DEFAULT_MOVE_SPEED).
    paths: Dict[int, List[Tuple[float, float]]] = {}
    alive: Dict[int, bool] = {h["net_id"]: True for h in heroes}
    hp: Dict[int, float] = {}
    hp_max: Dict[int, float] = {}
    level: Dict[int, int] = {h["net_id"]: 1 for h in heroes}
    gold: Dict[int, float] = {}
    combat_components: Dict[int, Dict[str, float]] = {}
    # net_id → [Q,W,E,R] ranks (0-based slots 0..3)
    ability_ranks: Dict[int, List[int]] = {
        h["net_id"]: [0, 0, 0, 0] for h in heroes
    }
    items: Dict[int, Dict[int, int]] = {h["net_id"]: {} for h in heroes}  # slot → item_id

    turrets: Dict[int, dict] = {}  # net_id → meta
    neutrals: Dict[int, dict] = {}  # net_id → meta
    lane_minions: Dict[int, dict] = {}  # net_id → meta

    decoded = [
        "CreateHero",
        "WaypointGroup",
        "Replication.mHP",
        "Replication.combat_when_present",
        "BuyItem/RemoveItem/SwapItem",
        "CastSpellAns",
        "SkillLevelUp",
        "NPCDieMapView*",
        "CreateTurret",
        "CreateNeutral",
        "SpawnMinion/BarrackSpawnUnit",
        "WardPlace/WardKill",
    ]
    missing = [
        "wards_when_absent",
        "HeroDie_packet",
        "summoner_spell_used",
        "full_liveclient_cooldowns",
    ]

    lines: List[dict] = [
        coverage_line(
            source="maknee_decoded_packets",
            game_id=game_id,
            decoded=decoded,
            missing=missing,
            notes=(
                "Positions from WaypointGroup (synthetic path-walk between samples at "
                f"~{DEFAULT_MOVE_SPEED:g} u/s — not native full_at_sampled_frames); "
                "HP/gold/level from Replication. "
                "Combat overrides only when Replication emits combat field names. "
                "Ability ranks from SkillLevelUp / CastSpellAns levels when present. "
                "VoidGrub via CreateNeutral SRU_VoidGrub/SRU_Horde → epic_monster_kill. "
                "Plug-in point for ROFL decryptors that emit the same events[]."
            ),
            provenance=_synthetic_path_provenance(),
        ),
        game_info_line(
            game_id=game_id,
            game_name=str(game_id) if game_id else "maknee_match",
            platform_id="MAKNEE",
            stats_update_interval_ms=int(round(1000 / hz)) if hz > 0 else 1000,
            participants=[
                {
                    "participantID": h["participantID"],
                    "teamID": h["teamID"],
                    "championName": h["champion"],
                    "playerName": h["name"],
                    "summonerName": h["name"],
                }
                for h in heroes
            ],
        ),
    ]

    # Merge packet stream with sampled stats_update ticks in one pass
    step = 1.0 / hz if hz > 0 else 1.0
    next_sample = 0.0
    last_t = 0.0
    last_advance_t = 0.0
    emitted_samples = 0

    def advance_paths(dt: float) -> None:
        if dt <= 0:
            return
        for wid, queue in list(paths.items()):
            remaining = dt
            while remaining > 1e-9 and queue:
                cur = pos.get(wid)
                if cur is None:
                    pos[wid] = queue.pop(0)
                    continue
                tx, tz = queue[0]
                dx = tx - cur[0]
                dz = tz - cur[1]
                dist = math.hypot(dx, dz)
                if dist < 1e-3:
                    queue.pop(0)
                    pos[wid] = (tx, tz)
                    continue
                step_u = DEFAULT_MOVE_SPEED * remaining
                if step_u >= dist:
                    pos[wid] = (tx, tz)
                    queue.pop(0)
                    remaining -= dist / DEFAULT_MOVE_SPEED
                else:
                    pos[wid] = (cur[0] + dx / dist * step_u, cur[1] + dz / dist * step_u)
                    remaining = 0.0
            if not queue:
                paths.pop(wid, None)

    def set_path(wid: int, dests: List[Tuple[float, float]]) -> None:
        if not dests:
            return
        if wid not in pos:
            hero = by_wp.get(wid)
            if hero is not None:
                fountain = fountain_for_team(hero["teamID"])
                pos[wid] = (fountain["x"], fountain["z"])
            else:
                pos[wid] = dests[0]
                dests = dests[1:]
                if not dests:
                    return
        # Drop leading points we already occupy so we do not stutter in place.
        while dests:
            dx = dests[0][0] - pos[wid][0]
            dz = dests[0][1] - pos[wid][1]
            if math.hypot(dx, dz) < 25.0:
                pos[wid] = dests.pop(0)
            else:
                break
        if dests:
            paths[wid] = dests
        else:
            paths.pop(wid, None)

    def build_participants() -> List[dict]:
        parts = []
        for h in heroes:
            nid = h["net_id"]
            wid = h["waypoint_id"]
            default = fountain_for_team(h["teamID"])
            if wid in pos:
                x, z = pos[wid]
                src = "maknee_waypoint"
            else:
                x, z = default["x"], default["z"]
                src = "fountain_placeholder"
            slot_items = [
                {"itemID": iid, "itemCooldown": 0}
                for slot, iid in sorted(items.get(nid, {}).items())
                if iid
            ]
            h_cur = hp.get(nid)
            h_max = hp_max.get(nid)
            hp_decoded = h_cur is not None or h_max is not None
            if not hp_decoded:
                h_cur, h_max = 0.0, 0.0
            elif h_max is None:
                h_max = max(h_cur or 1.0, 1.0)
            elif h_cur is None:
                h_cur = h_max
            else:
                # Some sampled Replication packets carry mHP before the newer
                # mMaxHP value. Preserve the decoded HP and widen the envelope
                # instead of emitting an impossible health fraction.
                h_max = max(h_max, h_cur, 1.0)
            resolved = resolve_combat_stats(combat_components.get(nid) or {})
            combat_source = (
                "replication_decoded" if resolved is not None else "unavailable"
            )
            ranks = ability_ranks.get(nid) or [0, 0, 0, 0]
            ranks_known = any(r > 0 for r in ranks)
            ranks_source = "cast_or_level_up" if ranks_known else "unavailable"
            parts.append(
                participant_row(
                    participant_id=h["participantID"],
                    team_id=h["teamID"],
                    champion_name=h["champion"],
                    player_name=h["name"],
                    position={"x": x, "z": z},
                    position_source=src,
                    alive=alive.get(nid, True),
                    level=int(level.get(nid, 1)),
                    health=float(h_cur),
                    health_max=float(h_max),
                    health_known=hp_decoded,
                    health_source=(
                        "replication_decoded" if hp_decoded else "unavailable"
                    ),
                    combat_stats_source=combat_source,
                    ability_ranks_source=ranks_source,
                    ability_levels=(
                        int(ranks[0]),
                        int(ranks[1]),
                        int(ranks[2]),
                        int(ranks[3]),
                    ),
                    items=slot_items,
                    total_gold=gold.get(nid),
                    current_gold=gold.get(nid),
                    attack_damage=None if resolved is None else resolved["attackDamage"],
                    ability_power=None if resolved is None else resolved["abilityPower"],
                    armor=None if resolved is None else resolved["armor"],
                    magic_resist=None if resolved is None else resolved["magicResist"],
                    attack_speed=None if resolved is None else resolved["attackSpeed"],
                )
            )
        return parts

    def flush_stats(t: float, game_over: bool = False) -> None:
        nonlocal emitted_samples
        lines.append(
            stats_update_line(
                game_id=game_id,
                game_time=int(round(t * 1000)),
                participants=build_participants(),
                game_over=game_over,
            )
        )
        emitted_samples += 1

    def maybe_sample_up_to(t: float) -> None:
        nonlocal next_sample, last_advance_t
        while next_sample <= t + 1e-9:
            advance_paths(next_sample - last_advance_t)
            last_advance_t = next_sample
            flush_stats(next_sample)
            next_sample += step

    for e in events:
        if not e:
            continue
        key = next(iter(e))
        payload = e[key]
        if not isinstance(payload, dict):
            continue
        t = _packet_time(payload)
        if t is None:
            continue
        last_t = t
        maybe_sample_up_to(t)

        if key in ("WaypointGroup", "WaypointGroupWithSpeed"):
            for wid_s, pts in (payload.get("waypoints") or {}).items():
                if not pts:
                    continue
                dests = [_as_live_point(pt) for pt in pts]
                set_path(int(wid_s), dests)

        elif key == "Replication":
            for nid_s, rep in (payload.get("net_id_to_replication_datas") or {}).items():
                nid = int(nid_s)
                if nid not in by_net:
                    continue
                name = (rep.get("name") or "").strip()
                val = _rep_value(rep.get("data") or {})
                if val is None:
                    continue
                apply_replication_value(
                    name=name,
                    value=val,
                    hp=hp,
                    hp_max=hp_max,
                    level=level,
                    gold=gold,
                    combat=combat_components,
                    nid=nid,
                )

        elif key == "BuyItem":
            nid = int(payload["net_id"])
            item_id = int(payload.get("item_id") or 0)
            if nid in items:
                items[nid][int(payload.get("slot", 0))] = item_id
                if "entity_gold_after_change" in payload:
                    gold[nid] = float(payload["entity_gold_after_change"])
            hero = by_net.get(nid)
            if hero and item_id:
                lines.append(
                    item_purchased_line(
                        game_id=game_id,
                        game_time=int(round(t * 1000)),
                        participant_id=hero["participantID"],
                        item_id=item_id,
                    )
                )

        elif key == "RemoveItem":
            nid = int(payload["net_id"])
            if nid in items:
                items[nid].pop(int(payload.get("slot", 0)), None)
                if "entity_gold_after_change" in payload:
                    gold[nid] = float(payload["entity_gold_after_change"])

        elif key == "SwapItem":
            nid = int(payload["net_id"])
            if nid in items:
                a = int(payload.get("source_slot", 0))
                b = int(payload.get("target_slot", 0))
                ia = items[nid].get(a)
                ib = items[nid].get(b)
                if ib is None:
                    items[nid].pop(a, None)
                else:
                    items[nid][a] = ib
                if ia is None:
                    items[nid].pop(b, None)
                else:
                    items[nid][b] = ia

        elif key == "CastSpellAns":
            nid = int(payload.get("caster_net_id") or 0)
            hero = by_net.get(nid)
            if hero:
                slot = int(payload.get("slot") or 0)
                spell_level = int(payload.get("level") or 0)
                if 0 <= slot <= 3 and spell_level > 0 and nid in ability_ranks:
                    ability_ranks[nid][slot] = max(ability_ranks[nid][slot], spell_level)
                sp = payload.get("source_position") or {}
                sx, sz = to_live_stats_coords(
                    float(sp.get("x", 0)), float(sp.get("z", 0))
                )
                lines.append(
                    skill_used_line(
                        game_id=game_id,
                        game_time=int(round(t * 1000)),
                        participant_id=hero["participantID"],
                        skill_slot=slot,
                        skill_name=payload.get("spell_name") or "",
                        position={"x": sx, "z": sz},
                    )
                )

        elif key == "SkillLevelUp":
            nid = int(payload.get("net_id") or payload.get("participant_net_id") or 0)
            hero = by_net.get(nid)
            if hero:
                slot = int(payload.get("slot") or payload.get("skill_slot") or 0)
                # Live-stats skillSlot is often 1..4; normalize to 0..3
                if slot >= 1 and slot <= 4:
                    slot0 = slot - 1
                else:
                    slot0 = slot
                if 0 <= slot0 <= 3 and nid in ability_ranks:
                    ability_ranks[nid][slot0] = max(
                        ability_ranks[nid][slot0],
                        int(payload.get("level") or ability_ranks[nid][slot0] + 1),
                    )
                lines.append(
                    skill_level_up_line(
                        game_id=game_id,
                        game_time=int(round(t * 1000)),
                        participant_id=hero["participantID"],
                        skill_slot=slot if slot >= 1 else slot0 + 1,
                        evolved=bool(payload.get("evolved") or False),
                    )
                )

        elif key in ("WardPlace", "WardPlaced"):
            nid = int(payload.get("net_id") or payload.get("placer_net_id") or 0)
            hero = by_net.get(nid)
            if hero:
                wp = payload.get("position") or {}
                x, z = to_live_stats_coords(
                    float(wp.get("x", 0)), float(wp.get("z", wp.get("y", 0)))
                )
                lines.append(
                    ward_placed_line(
                        game_id=game_id,
                        game_time=int(round(t * 1000)),
                        placer_id=hero["participantID"],
                        ward_type=str(payload.get("ward_type") or "yellowTrinket"),
                        position={"x": x, "z": z},
                    )
                )

        elif key in ("WardKill", "WardKilled"):
            nid = int(payload.get("net_id") or payload.get("killer_net_id") or 0)
            hero = by_net.get(nid)
            if hero:
                wp = payload.get("position") or {}
                x, z = to_live_stats_coords(
                    float(wp.get("x", 0)), float(wp.get("z", wp.get("y", 0)))
                )
                lines.append(
                    ward_killed_line(
                        game_id=game_id,
                        game_time=int(round(t * 1000)),
                        killer_id=hero["participantID"],
                        ward_type=str(payload.get("ward_type") or "yellowTrinket"),
                        position={"x": x, "z": z},
                    )
                )

        elif key == "CreateTurret":
            nid = int(payload["net_id"])
            name = payload.get("name") or ""
            team, lane, tier = _parse_turret_meta(name)
            turrets[nid] = {"name": name, "teamID": team, "lane": lane, "tier": tier}

        elif key == "CreateNeutral":
            nid = int(payload["net_id"])
            skin = payload.get("skin_name") or payload.get("name") or ""
            p1 = payload.get("position1") or payload.get("position") or {}
            x, z = to_live_stats_coords(float(p1.get("x", 0)), float(p1.get("z", 0)))
            epic = EPIC_NEUTRALS.get(skin)
            if epic is None and "voidgrub" in skin.lower():
                epic = ("VoidGrub", None)
            if epic is None and "horde" in skin.lower():
                epic = ("VoidGrub", None)
            neutrals[nid] = {
                "skin": skin,
                "epic": epic,
                "position": {"x": x, "z": z},
            }
            if epic is None and skin:
                # Jungle camp (non-epic): surface spawn + location for map overlay.
                lines.append(
                    neutral_minion_spawn_line(
                        game_id=game_id,
                        game_time=int(round(t * 1000)),
                        monster_type=skin,
                        position={"x": x, "z": z},
                        net_id=nid,
                    )
                )

        elif key in ("SpawnMinion", "BarrackSpawnUnit"):
            nid = int(payload.get("net_id") or 0)
            team = int(payload.get("team_id") or payload.get("teamID") or 0)
            lane = payload.get("lane")
            mtype = str(
                payload.get("minion_type")
                or payload.get("minionType")
                or payload.get("skin_name")
                or "melee"
            )
            p1 = payload.get("position") or payload.get("position1") or {}
            x, z = to_live_stats_coords(float(p1.get("x", 0)), float(p1.get("z", 0)))
            if nid:
                lane_minions[nid] = {
                    "teamID": team,
                    "lane": lane,
                    "minionType": mtype,
                    "position": {"x": x, "z": z},
                }
            lines.append(
                barracks_minion_spawn_line(
                    game_id=game_id,
                    game_time=int(round(t * 1000)),
                    team_id=team,
                    lane=lane,
                    minion_type=mtype,
                    position={"x": x, "z": z},
                    net_id=nid or None,
                )
            )

        elif key in ("NPCDieMapView", "NPCDieMapViewBroadcast", "HeroDie"):
            killed = int(payload.get("killed_net_id") or payload.get("net_id") or 0)
            killer = int(payload.get("killer_net_id") or 0)

            if killed in by_net:
                alive[killed] = False
                victim = by_net[killed]
                killer_hero = by_net.get(killer)
                killer_team = (
                    killer_hero["teamID"]
                    if killer_hero
                    else (200 if victim["teamID"] == 100 else 100)
                )
                wid = victim["waypoint_id"]
                kill_pos = None
                if wid in pos:
                    kill_pos = {"x": pos[wid][0], "z": pos[wid][1]}
                lines.append(
                    champion_kill_line(
                        game_id=game_id,
                        game_time=int(round(t * 1000)),
                        killer_team_id=killer_team,
                        killer_id=killer_hero["participantID"] if killer_hero else None,
                        victim_id=victim["participantID"],
                        position=kill_pos,
                    )
                )

            elif killed in turrets:
                meta = turrets[killed]
                lines.append(
                    building_destroyed_line(
                        game_id=game_id,
                        game_time=int(round(t * 1000)),
                        team_id=meta["teamID"],
                        building_type="turret",
                        lane=meta.get("lane"),
                        turret_tier=meta.get("tier"),
                    )
                )
                turrets.pop(killed, None)

            elif killed in neutrals:
                meta = neutrals[killed]
                epic = meta.get("epic")
                if epic:
                    mtype, dtype = epic
                    killer_hero = by_net.get(killer)
                    killer_team = killer_hero["teamID"] if killer_hero else 0
                    lines.append(
                        epic_monster_kill_line(
                            game_id=game_id,
                            game_time=int(round(t * 1000)),
                            killer_team_id=killer_team,
                            monster_type=mtype,
                            dragon_type=dtype,
                            position=meta.get("position"),
                        )
                    )
                neutrals.pop(killed, None)

            elif killed in lane_minions:
                meta = lane_minions.pop(killed)
                lines.append(
                    barracks_minion_killed_line(
                        game_id=game_id,
                        game_time=int(round(t * 1000)),
                        team_id=int(meta.get("teamID") or 0),
                        position=meta.get("position"),
                        net_id=killed,
                    )
                )

        elif key == "LeaveFog":
            # Respawn signal heuristic: hero reappears → mark alive
            nid = int(payload.get("net_id") or 0)
            if nid in by_net and not alive.get(nid, True):
                alive[nid] = True

    # Final samples through last packet time. Packets that share the last
    # sample's timestamp are applied after that tick was emitted; refresh the
    # latest stats_update in place (keep its on-grid gameTime) so cadence stays
    # stable and terminal Replication/waypoints are included.
    maybe_sample_up_to(last_t)
    # Keep sampling while champions are still walking toward sparse destinations.
    drain_start = last_t
    drain_deadline = drain_start + MAX_PATH_DRAIN_SECONDS
    drain_t = drain_start
    while paths and drain_t < drain_deadline:
        drain_t = min(drain_t + step, drain_deadline)
        maybe_sample_up_to(drain_t)
    last_t = drain_t
    if emitted_samples == 0:
        flush_stats(last_t, game_over=True)
    else:
        for row in reversed(lines):
            if row.get("rfc461Schema") == "stats_update":
                row["participants"] = build_participants()
                row["gameOver"] = True
                break

    lines.append(
        game_end_line(
            game_id=game_id,
            game_time=int(round(last_t * 1000)),
            winning_team=0,
        )
    )
    return lines


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("packets_json", type=Path, help="Match JSON or HF .jsonl/.jsonl.gz")
    ap.add_argument("-o", "--output", type=Path, required=True)
    ap.add_argument("--hz", type=float, default=1.0)
    ap.add_argument("--game-id", type=int, default=0)
    ap.add_argument(
        "--line",
        type=int,
        default=0,
        help="When input is .jsonl/.jsonl.gz, which match line to convert",
    )
    args = ap.parse_args()

    match = _load_match(args.packets_json, line=args.line)
    rows = convert(match, hz=args.hz, game_id=args.game_id)
    write_jsonl(args.output, rows)

    schemas: Dict[str, int] = {}
    for row in rows:
        schemas[row["rfc461Schema"]] = schemas.get(row["rfc461Schema"], 0) + 1
    print(json.dumps({"wrote": str(args.output), "lines": len(rows), "schemas": schemas}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
