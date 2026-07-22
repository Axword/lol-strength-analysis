#!/usr/bin/env python3
"""
Rebuild FUR vs G2 timeline frames with competitive scoreboard + ward vision
+ mapObjects (structures / jungle camps by availability).

Derived from the Riot live-stats JSONL. Reuses existing unit frames.
"""
from __future__ import annotations

import json
import math
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JSONL = ROOT / "events_riot.jsonl"
TIMELINE = ROOT / "public/data/fur_vs_g2_timeline.json"
OUT = TIMELINE
MAP_SPAN = 14870.0

# SR camp clocks (ms) — patch 26.1+ (keep in sync with src/data/srLayout.ts)
FIRST_BUFF_WOLF_RAPTOR_MS = 55_000
FIRST_GROMP_KRUG_MS = 67_000
FIRST_SCUTTLE_MS = 175_000
FIRST_DRAGON_MS = 300_000
FIRST_GRUBS_MS = 300_000
HERALD_SPAWN_MS = 840_000  # 14:00
BARON_SPAWN_MS = 1_200_000  # 20:00
RESPAWN_SMALL_MS = 135_000
RESPAWN_BUFF_MS = 300_000
RESPAWN_SCUTTLE_MS = 150_000
RESPAWN_DRAGON_MS = 300_000
RESPAWN_BARON_MS = 360_000

BARON_DURATION_S = 180.0
ELDER_DURATION_S = 150.0
WARD_TTL = {
    "yellowTrinket": 110.0,
    "blueTrinket": 9999.0,
    "controlWard": 9999.0,
    "sightWard": 150.0,
    "visionWard": 9999.0,
}

# Keep in sync with src/data/srLayout.ts
STRUCTURES: list[dict] = []
CAMPS: list[dict] = []


def _seed_layout() -> None:
    global STRUCTURES, CAMPS
    blue_structs = [
        ("t_outer_top", "turret", "top", "outer", 981, 10441),
        ("t_outer_mid", "turret", "mid", "outer", 5846, 6396),
        ("t_outer_bot", "turret", "bot", "outer", 10504, 1029),
        ("t_inner_top", "turret", "top", "inner", 1512, 6699),
        ("t_inner_mid", "turret", "mid", "inner", 5048, 4812),
        ("t_inner_bot", "turret", "bot", "inner", 6919, 1483),
        ("t_base_top", "turret", "top", "base", 1169, 4287),
        ("t_base_mid", "turret", "mid", "base", 3651, 3696),
        ("t_base_bot", "turret", "bot", "base", 4281, 1253),
        ("t_nexus_a", "turret", "mid", "nexus", 1748, 2270),
        ("t_nexus_b", "turret", "mid", "nexus", 2177, 1807),
        ("i_top", "inhibitor", "top", None, 1170, 3570),
        ("i_mid", "inhibitor", "mid", None, 3210, 3217),
        ("i_bot", "inhibitor", "bot", None, 3468, 1230),
        ("nexus", "nexus", None, None, 1550, 1660),
    ]
    STRUCTURES = []
    for sid, kind, lane, tier, gx, gz in blue_structs:
        STRUCTURES.append(
            {
                "id": f"blue_{sid}",
                "kind": kind,
                "team": 100,
                "lane": lane,
                "tier": tier,
                "gx": gx,
                "gz": gz,
                **riot_to_norm(gx, gz),
            }
        )
        STRUCTURES.append(
            {
                "id": f"red_{sid}",
                "kind": kind,
                "team": 200,
                "lane": lane,
                "tier": tier,
                "gx": MAP_SPAN - gx,
                "gz": MAP_SPAN - gz,
                **riot_to_norm(MAP_SPAN - gx, MAP_SPAN - gz),
            }
        )

    # Spawn anchors + SR timers (first spawn + respawn). Patch 26.1+.
    CAMPS = []
    for sid, kind, team, label, gx, gz, respawn, first in (
        ("blue_blue_buff", "blue_buff", 100, "Blue buff", 3720, 7880, RESPAWN_BUFF_MS, FIRST_BUFF_WOLF_RAPTOR_MS),
        ("blue_gromp", "gromp", 100, "Gromp", 2300, 8380, RESPAWN_SMALL_MS, FIRST_GROMP_KRUG_MS),
        ("blue_wolves", "wolves", 100, "Wolves", 3780, 6500, RESPAWN_SMALL_MS, FIRST_BUFF_WOLF_RAPTOR_MS),
        ("blue_raptors", "raptors", 100, "Raptors", 7060, 5320, RESPAWN_SMALL_MS, FIRST_BUFF_WOLF_RAPTOR_MS),
        ("blue_red_buff", "red_buff", 100, "Red buff", 7730, 4050, RESPAWN_BUFF_MS, FIRST_BUFF_WOLF_RAPTOR_MS),
        ("blue_krugs", "krugs", 100, "Krugs", 8430, 2540, RESPAWN_SMALL_MS, FIRST_GROMP_KRUG_MS),
        ("red_blue_buff", "blue_buff", 200, "Blue buff", 11150, 6990, RESPAWN_BUFF_MS, FIRST_BUFF_WOLF_RAPTOR_MS),
        ("red_gromp", "gromp", 200, "Gromp", 12570, 6490, RESPAWN_SMALL_MS, FIRST_GROMP_KRUG_MS),
        ("red_wolves", "wolves", 200, "Wolves", 11090, 8370, RESPAWN_SMALL_MS, FIRST_BUFF_WOLF_RAPTOR_MS),
        ("red_raptors", "raptors", 200, "Raptors", 7810, 9550, RESPAWN_SMALL_MS, FIRST_BUFF_WOLF_RAPTOR_MS),
        ("red_red_buff", "red_buff", 200, "Red buff", 7140, 10820, RESPAWN_BUFF_MS, FIRST_BUFF_WOLF_RAPTOR_MS),
        ("red_krugs", "krugs", 200, "Krugs", 6440, 12330, RESPAWN_SMALL_MS, FIRST_GROMP_KRUG_MS),
        ("scuttle_top", "scuttle", None, "Scuttle (baron)", 5056, 8778, RESPAWN_SCUTTLE_MS, FIRST_SCUTTLE_MS),
        ("scuttle_bot", "scuttle", None, "Scuttle (dragon)", 9600, 5800, RESPAWN_SCUTTLE_MS, FIRST_SCUTTLE_MS),
        ("dragon_pit", "dragon_pit", None, "Dragon", 10021, 4529, RESPAWN_DRAGON_MS, FIRST_DRAGON_MS),
        ("baron_pit", "baron_pit", None, "Baron / Grubs / Herald", 4803, 10235, RESPAWN_BARON_MS, FIRST_GRUBS_MS),
    ):
        CAMPS.append(
            {
                "id": sid,
                "kind": kind,
                "team": team,
                "label": label,
                "gx": gx,
                "gz": gz,
                "respawnMs": respawn,
                "firstSpawnMs": first,
                **riot_to_norm(gx, gz),
            }
        )


def riot_to_norm(x: float, z: float) -> dict:
    return {
        "x": round(max(0.0, min(1.0, x / MAP_SPAN)), 5),
        "y": round(max(0.0, min(1.0, z / MAP_SPAN)), 5),
    }


def empty_team_obj():
    return {
        "towers": 0,
        "inhibs": 0,
        "kills": 0,
        "gold": 0,
        "roleQuests": 0,
        "voidGrubs": 0,
        "dragons": [],
        "dragonCount": 0,
        "hasSoul": False,
        "soulType": None,
        "barons": 0,
        "baronActive": False,
        "baronEndsAtMs": None,
        "elders": 0,
        "elderActive": False,
        "elderEndsAtMs": None,
        "heralds": 0,
    }


MONSTER_TO_CAMP = {
    "raptor": "raptors",
    "wolf": "wolves",
    "gromp": "gromp",
    "krug": "krugs",
    "redCamp": "red_buff",
    "blueCamp": "blue_buff",
    "scuttleCrab": "scuttle",
    "dragon": "dragon_pit",
    "baron": "baron_pit",
    "VoidGrub": "baron_pit",
    "riftHerald": "baron_pit",
}


def nearest_structure(team: int, gx: float, gz: float, kind: str | None, max_d=450.0):
    best = None
    best_d = max_d
    for s in STRUCTURES:
        if s["team"] != team:
            continue
        if kind and s["kind"] != kind:
            continue
        d = math.hypot(s["gx"] - gx, s["gz"] - gz)
        if d < best_d:
            best_d = d
            best = s
    return best


def nearest_camp(gx: float, gz: float, kind: str | None, max_d=1400.0):
    best = None
    best_d = max_d
    for c in CAMPS:
        if kind and c["kind"] != kind:
            continue
        d = math.hypot(c["gx"] - gx, c["gz"] - gz)
        if d < best_d:
            best_d = d
            best = c
    return best


def main() -> None:
    global JSONL, TIMELINE, OUT
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--jsonl", type=Path, required=True, help="Input canonical rfc461 JSONL")
    ap.add_argument("--timeline", type=Path, required=True, help="Timeline JSON to enrich")
    ap.add_argument("-o", "--output", type=Path, help="Output timeline JSON (defaults to --timeline)")
    args = ap.parse_args()
    JSONL = args.jsonl
    TIMELINE = args.timeline
    OUT = args.output or args.timeline
    _seed_layout()
    if not JSONL.exists():
        raise SystemExit(f"missing {JSONL}")
    if not TIMELINE.exists():
        raise SystemExit(f"missing {TIMELINE}")

    timeline = json.loads(TIMELINE.read_text())
    frames = timeline["frames"]
    print(f"loaded {len(frames)} frames structures={len(STRUCTURES)} camps={len(CAMPS)}")

    pid_team = {p["participantID"]: p["teamID"] for p in timeline["participants"]}

    building_events = []  # (t, owner, kind, lane, tier, gx, gz)
    kill_events = []
    monster_events = []  # (t, killer_team, monsterType, dragonType, gx, gz)
    quest_events = []
    ward_events = []
    gold_by_time = []

    with JSONL.open() as f:
        for line in f:
            o = json.loads(line)
            schema = o.get("rfc461Schema")
            t = int(o.get("gameTime") or 0)

            if schema == "stats_update":
                g100 = g200 = 0
                for p in o.get("participants") or []:
                    tg = int(p.get("totalGold") or 0)
                    if p.get("teamID") == 100:
                        g100 += tg
                    else:
                        g200 += tg
                gold_by_time.append((t, {100: g100, 200: g200}))

            elif schema == "building_destroyed":
                pos = o.get("position") or {}
                building_events.append(
                    (
                        t,
                        int(o.get("teamID") or 0),
                        o.get("buildingType") or "turret",
                        o.get("lane"),
                        o.get("turretTier"),
                        float(pos.get("x") or 0),
                        float(pos.get("z") or 0),
                    )
                )

            elif schema == "champion_kill":
                kill_events.append((t, o.get("killerTeamID")))

            elif schema == "epic_monster_kill":
                pos = o.get("position") or {}
                monster_events.append(
                    (
                        t,
                        o.get("killerTeamID"),
                        o.get("monsterType") or "",
                        o.get("dragonType"),
                        float(pos.get("x") or 0),
                        float(pos.get("z") or 0),
                    )
                )

            elif schema == "role_bound_quest_completed":
                quest_events.append((t, o.get("participantID")))

            elif schema == "ward_placed":
                ward_events.append(
                    {
                        "op": "place",
                        "t": t,
                        "placer": o.get("placer"),
                        "pos": riot_to_norm(
                            o.get("position", {}).get("x", 0),
                            o.get("position", {}).get("z", 0),
                        ),
                        "wardType": o.get("wardType") or "yellowTrinket",
                    }
                )
            elif schema == "ward_killed":
                ward_events.append(
                    {
                        "op": "kill",
                        "t": t,
                        "pos": riot_to_norm(
                            o.get("position", {}).get("x", 0),
                            o.get("position", {}).get("z", 0),
                        )
                        if o.get("position")
                        else None,
                        "killer": o.get("killer"),
                    }
                )

    gold_by_time.sort()
    building_events.sort()
    kill_events.sort()
    monster_events.sort()
    quest_events.sort()
    ward_events.sort(key=lambda w: w["t"])

    print(
        "events",
        len(building_events),
        "buildings",
        len(kill_events),
        "kills",
        len(monster_events),
        "monsters",
        len(quest_events),
        "quests",
        len(ward_events),
        "ward ops",
        len(gold_by_time),
        "gold snaps",
    )

    def gold_at(ms: int) -> dict:
        lo, hi = 0, len(gold_by_time) - 1
        best = {100: 2500, 200: 2500}
        while lo <= hi:
            mid = (lo + hi) // 2
            if gold_by_time[mid][0] <= ms:
                best = gold_by_time[mid][1]
                lo = mid + 1
            else:
                hi = mid - 1
        return best

    def dragon_label(monster_type: str, dragon_type) -> str | None:
        mt = (monster_type or "").lower()
        if "elder" in mt:
            return "elder"
        if mt != "dragon" and "dragon" not in mt:
            return None
        dt = (dragon_type or "").lower()
        mapping = {
            "air": "cloud",
            "cloud": "cloud",
            "fire": "infernal",
            "infernal": "infernal",
            "earth": "mountain",
            "mountain": "mountain",
            "water": "ocean",
            "ocean": "ocean",
            "hextech": "hextech",
            "chemtech": "chemtech",
        }
        return mapping.get(dt, dt or "elemental")

    # Structure / camp live state
    destroyed_at: dict[str, int] = {}  # structure id → ms
    # Seed: every camp is down until its first spawn clock
    camp_down_until: dict[str, int] = {
        c["id"]: int(c["firstSpawnMs"]) for c in CAMPS
    }
    camp_last_clear: dict[str, int] = {}
    grub_kills_in_pit = 0

    bi = ki = mi = qi = 0
    blue = empty_team_obj()
    red = empty_team_obj()
    wards: list[dict] = []
    wi = 0
    ward_seq = 0

    matched_buildings = 0
    matched_camps = 0

    for fr in frames:
        t = int(fr["t"])

        while bi < len(building_events) and building_events[bi][0] <= t:
            bt, owner, kind, _lane, _tier, gx, gz = building_events[bi]
            taker = red if owner == 100 else blue
            if kind == "turret":
                taker["towers"] += 1
            elif kind == "inhibitor":
                taker["inhibs"] += 1
            hit = nearest_structure(owner, gx, gz, kind if kind in ("turret", "inhibitor", "nexus") else None)
            if hit:
                destroyed_at[hit["id"]] = bt
                matched_buildings += 1
            bi += 1

        while ki < len(kill_events) and kill_events[ki][0] <= t:
            _, team = kill_events[ki]
            if team == 100:
                blue["kills"] += 1
            elif team == 200:
                red["kills"] += 1
            ki += 1

        while mi < len(monster_events) and monster_events[mi][0] <= t:
            mt_t, team, mtype, dtype, gx, gz = monster_events[mi]
            side = blue if team == 100 else red if team == 200 else None
            if side is not None:
                ml = mtype.lower()
                if "voidgrub" in ml or mtype == "VoidGrub":
                    side["voidGrubs"] = min(3, side["voidGrubs"] + 1)
                elif "baron" in ml:
                    side["barons"] += 1
                    side["baronActive"] = True
                    side["baronEndsAtMs"] = mt_t + int(BARON_DURATION_S * 1000)
                elif "elder" in ml:
                    side["elders"] += 1
                    side["elderActive"] = True
                    side["elderEndsAtMs"] = mt_t + int(ELDER_DURATION_S * 1000)
                elif "herald" in ml or mtype == "riftHerald":
                    side["heralds"] += 1
                else:
                    label = dragon_label(mtype, dtype)
                    if label and label != "elder":
                        side["dragons"].append(label)
                        side["dragonCount"] = len(side["dragons"])
                        if side["dragonCount"] >= 4 and not side["hasSoul"]:
                            side["hasSoul"] = True
                            side["soulType"] = label
                    elif label == "elder":
                        side["elders"] += 1
                        side["elderActive"] = True
                        side["elderEndsAtMs"] = mt_t + int(ELDER_DURATION_S * 1000)

            camp_kind = MONSTER_TO_CAMP.get(mtype)
            if camp_kind:
                hit = nearest_camp(gx, gz, camp_kind)
                if hit:
                    camp_last_clear[hit["id"]] = mt_t
                    matched_camps += 1
                    cid = hit["id"]
                    if hit["kind"] == "dragon_pit":
                        camp_down_until[cid] = mt_t + int(hit["respawnMs"] or 300_000)
                    elif hit["kind"] == "baron_pit":
                        if mtype == "VoidGrub":
                            grub_kills_in_pit += 1
                            # Pack stays up until the third grub dies, then wait for Herald/Baron clock
                            if grub_kills_in_pit >= 3:
                                next_obj = (
                                    HERALD_SPAWN_MS
                                    if mt_t < HERALD_SPAWN_MS
                                    else BARON_SPAWN_MS
                                    if mt_t < BARON_SPAWN_MS
                                    else mt_t + int(hit["respawnMs"] or 360_000)
                                )
                                camp_down_until[cid] = next_obj
                            else:
                                # Still grubs up — ensure alive
                                camp_down_until[cid] = mt_t
                        elif mtype == "riftHerald":
                            camp_down_until[cid] = (
                                BARON_SPAWN_MS
                                if mt_t < BARON_SPAWN_MS
                                else mt_t + int(hit["respawnMs"] or 360_000)
                            )
                        else:
                            # Baron
                            camp_down_until[cid] = mt_t + int(hit["respawnMs"] or 360_000)
                    elif hit.get("respawnMs"):
                        camp_down_until[cid] = mt_t + int(hit["respawnMs"])
            mi += 1

        while qi < len(quest_events) and quest_events[qi][0] <= t:
            _, pid = quest_events[qi]
            team = pid_team.get(pid)
            if team == 100:
                blue["roleQuests"] += 1
            elif team == 200:
                red["roleQuests"] += 1
            qi += 1

        for side in (blue, red):
            if side["baronActive"] and side["baronEndsAtMs"] is not None and t >= side["baronEndsAtMs"]:
                side["baronActive"] = False
            if side["elderActive"] and side["elderEndsAtMs"] is not None and t >= side["elderEndsAtMs"]:
                side["elderActive"] = False

        while wi < len(ward_events) and ward_events[wi]["t"] <= t:
            ev = ward_events[wi]
            if ev["op"] == "place":
                pid = ev["placer"]
                team = pid_team.get(pid, 0)
                ttl = WARD_TTL.get(ev["wardType"], 120.0)
                ward_seq += 1
                wards.append(
                    {
                        "id": f"w{ward_seq}",
                        "team": 100 if team == 100 else 200,
                        "type": ev["wardType"],
                        "x": ev["pos"]["x"],
                        "y": ev["pos"]["y"],
                        "expiresAtMs": ev["t"] + int(ttl * 1000),
                        "visionRadius": 0.06 if "blue" in (ev["wardType"] or "") else 0.055,
                    }
                )
            elif ev["op"] == "kill" and ev.get("pos"):
                px, py = ev["pos"]["x"], ev["pos"]["y"]
                best_i, best_d = None, 1e9
                for i, w in enumerate(wards):
                    d = (w["x"] - px) ** 2 + (w["y"] - py) ** 2
                    if d < best_d:
                        best_d, best_i = d, i
                if best_i is not None and best_d < 0.0025:
                    wards.pop(best_i)
            wi += 1

        wards = [w for w in wards if w["expiresAtMs"] > t]

        g = gold_at(t)
        blue["gold"] = g.get(100, 0)
        red["gold"] = g.get(200, 0)
        gold_delta = blue["gold"] - red["gold"]

        fr["score"] = {
            "t": t,
            "blue": {k: (list(v) if k == "dragons" else v) for k, v in blue.items()},
            "red": {k: (list(v) if k == "dragons" else v) for k, v in red.items()},
            "goldDelta": gold_delta,
            "goldLeader": "blue" if gold_delta > 0 else "red" if gold_delta < 0 else "even",
        }
        fr["wards"] = [
            {
                "id": w["id"],
                "team": "blue" if w["team"] == 100 else "red",
                "type": w["type"],
                "x": w["x"],
                "y": w["y"],
                "visionRadius": w["visionRadius"],
            }
            for w in wards
        ]

        structures_state = []
        for s in STRUCTURES:
            alive = s["id"] not in destroyed_at
            structures_state.append(
                {
                    "id": s["id"],
                    "kind": s["kind"],
                    "team": "blue" if s["team"] == 100 else "red",
                    "lane": s["lane"],
                    "tier": s["tier"],
                    "x": s["x"],
                    "y": s["y"],
                    "alive": alive,
                }
            )

        camps_state = []
        for c in CAMPS:
            down_until = camp_down_until.get(c["id"])
            alive = down_until is None or t >= down_until
            row = {
                "id": c["id"],
                "kind": c["kind"],
                "team": (
                    "blue" if c["team"] == 100 else "red" if c["team"] == 200 else None
                ),
                "label": c["label"],
                "x": c["x"],
                "y": c["y"],
                "alive": alive,
            }
            cleared = camp_last_clear.get(c["id"])
            if cleared is not None:
                row["clearedAtMs"] = cleared
            if not alive and down_until is not None:
                row["respawnsAtMs"] = int(down_until)
            camps_state.append(row)

        fr["mapObjects"] = {"structures": structures_state, "camps": camps_state}

    timeline["hasScoreboard"] = True
    timeline["hasVision"] = True
    timeline["hasMapObjects"] = True
    timeline["mapImage"] = "/map/summoners_rift.png"
    timeline["mapTerrain"] = "/map/terrain.json"

    print("writing", OUT)
    OUT.write_text(json.dumps(timeline, separators=(",", ":")))
    print("done bytes", OUT.stat().st_size)
    print(f"matched building destroys={matched_buildings} camp clears={matched_camps}")
    mid = frames[len(frames) // 2]
    alive_s = sum(1 for s in mid["mapObjects"]["structures"] if s["alive"])
    alive_c = sum(1 for c in mid["mapObjects"]["camps"] if c["alive"])
    print(f"mid mapObjects structures alive={alive_s}/{len(STRUCTURES)} camps alive={alive_c}/{len(CAMPS)}")


if __name__ == "__main__":
    main()
