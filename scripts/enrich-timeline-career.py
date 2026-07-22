#!/usr/bin/env python3
"""
Attach compact career + live combat stats from Riot stats_update onto each
timeline unit frame, including monotonic wiki Touch-of-the-Void damage.

Touch model (touch-v4 / wiki V26.11):
- Camp = 3 Voidgrubs → max 3 stacks
- Ticks / 0.5s: melee 4/12/16, ranged 2/6/8
- Burn 4s, first tick +0.5s; refreshes on structure basic attacks
- Hunger @3: mite refreshes (live estimate; article O ceiling omits mites)
- Structure map seeded at t=0 (SR layout), refined by plate/destroy events
- Clean AA = near enemy structure + AD/AS-sized delta + no skill in window
"""
from __future__ import annotations

import json
import math
import argparse
from bisect import bisect_left
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JSONL = ROOT / "events_riot.jsonl"
TIMELINE = ROOT / "public/data/fur_vs_g2_timeline.json"
CHAMP_INDEX = ROOT / "public/data/lolwiki/champions-index.json"

TICK_MELEE = (0, 4, 12, 16)
TICK_RANGED = (0, 2, 6, 8)
TICK_INTERVAL = 0.5
BURN_DURATION = 4.0
FIRST_TICK_DELAY = 0.5
MAX_STACKS = 3
HUNGER_AT = 3
HUNGER_CD = 15.0

# Structure AA range (collision + typical champ ranges)
AA_RANGE_MELEE = 650.0
AA_RANGE_RANGED = 950.0
MAX_STRUCTURE_AA_DPS = 420.0
STRUCTURE_ARMOR_FOR_MAX_AA = 40.0
AA_SIZE_HEADROOM = 2.75
SKILL_VETO_SLACK_MS = 120
MODEL_VERSION = "touch-v5"
HIGH_CONF_MIN_AA = 3
HIGH_CONF_MAX_FAR_SHARE = 0.30
MAP_SIZE = 14870.0

# Blue (100) structures — this match + SR layout. Red = 180° rotate.
_BLUE_STRUCTURES: list[tuple[float, float]] = [
    (981.0, 10441.0),
    (5846.0, 6396.0),
    (10504.0, 1029.0),
    (1512.0, 6699.0),
    (5048.0, 4812.0),
    (6919.0, 1483.0),
    (1169.0, 4287.0),
    (3651.0, 3696.0),
    (4281.0, 1253.0),
    (1748.0, 2270.0),
    (2177.0, 1807.0),
    (1170.0, 3570.0),
    (3210.0, 3217.0),
    (3468.0, 1230.0),
]

CAREER_KEYS = [
    "MINIONS_KILLED",
    "NEUTRAL_MINIONS_KILLED",
    "CHAMPIONS_KILLED",
    "NUM_DEATHS",
    "ASSISTS",
    "VISION_SCORE",
    "TOTAL_DAMAGE_DEALT",
    "TOTAL_DAMAGE_DEALT_TO_CHAMPIONS",
    "PHYSICAL_DAMAGE_DEALT_TO_CHAMPIONS",
    "MAGIC_DAMAGE_DEALT_TO_CHAMPIONS",
    "TRUE_DAMAGE_DEALT_TO_CHAMPIONS",
    "TOTAL_DAMAGE_TAKEN",
    "TOTAL_DAMAGE_TAKEN_FROM_CHAMPIONS",
    "TOTAL_DAMAGE_SELF_MITIGATED",
    "TOTAL_DAMAGE_DEALT_TO_TURRETS",
    "TOTAL_DAMAGE_DEALT_TO_BUILDINGS",
    "TOTAL_DAMAGE_DEALT_TO_OBJECTIVES",
    "TOTAL_TIME_CROWD_CONTROL_DEALT_TO_CHAMPIONS",
    "TOTAL_HEAL_ON_TEAMMATES",
    "TOTAL_DAMAGE_SHIELDED_ON_TEAMMATES",
]


def dist(ax: float, az: float, bx: float, bz: float) -> float:
    return math.hypot(ax - bx, az - bz)


def seed_structures() -> list[tuple[float, float, int]]:
    out: list[tuple[float, float, int]] = []
    for x, z in _BLUE_STRUCTURES:
        out.append((x, z, 100))
        out.append((MAP_SIZE - x, MAP_SIZE - z, 200))
    return out


def upsert_structure(
    structures: list[tuple[float, float, int]],
    seen: set[tuple[int, int, int]],
    x: float,
    z: float,
    owner: int,
) -> None:
    key = (owner, int(round(x)), int(round(z)))
    if key in seen:
        return
    for i, (sx, sz, so) in enumerate(structures):
        if so == owner and dist(sx, sz, x, z) < 250:
            structures[i] = (x, z, owner)
            seen.discard((so, int(round(sx)), int(round(sz))))
            seen.add(key)
            return
    seen.add(key)
    structures.append((x, z, owner))


def remove_structure_near(
    structures: list[tuple[float, float, int]],
    seen: set[tuple[int, int, int]],
    x: float,
    z: float,
    owner: int,
) -> None:
    keep: list[tuple[float, float, int]] = []
    for sx, sz, so in structures:
        if so == owner and dist(sx, sz, x, z) < 350:
            seen.discard((so, int(round(sx)), int(round(sz))))
            continue
        keep.append((sx, sz, so))
    structures[:] = keep


def near_enemy_structure(
    pos: dict | None,
    team_id: int,
    structures: list[tuple[float, float, int]],
    ranged: bool,
) -> tuple[bool, float]:
    if not pos:
        return False, 1e9
    x, z = float(pos.get("x") or 0), float(pos.get("z") or 0)
    r = AA_RANGE_RANGED if ranged else AA_RANGE_MELEE
    best = 1e9
    for tx, tz, owner in structures:
        if owner == team_id:
            continue
        d = dist(x, z, tx, tz)
        if d < best:
            best = d
    return best <= r, best


def max_aa_delta(p: dict, dt_s: float) -> float:
    ad = float(p.get("attackDamage") or 0) or 100.0
    as_pct = float(p.get("attackSpeed") or 100.0) / 100.0
    phys = 100.0 / (100.0 + STRUCTURE_ARMOR_FOR_MAX_AA)
    per_hit = ad * phys
    attacks = max(1.0, as_pct * max(dt_s, 0.2) * 1.15 + 0.5)
    return max(
        80.0,
        per_hit * AA_SIZE_HEADROOM * attacks,
        MAX_STRUCTURE_AA_DPS * max(dt_s, 0.25),
    )


def skill_in_window(
    casts: list[int],
    t0: int,
    t1: int,
    slack_ms: int = SKILL_VETO_SLACK_MS,
) -> bool:
    if not casts:
        return False
    lo = t0 - slack_ms
    hi = t1 + slack_ms
    i = bisect_left(casts, lo)
    return i < len(casts) and casts[i] <= hi


def touch_confidence(*, have_structure_map: bool, aa_n: int, far_n: int) -> str:
    if aa_n <= 0:
        return "low"
    if not have_structure_map:
        return "medium"
    denom = aa_n + far_n
    far_share = far_n / denom if denom else 0.0
    if aa_n >= HIGH_CONF_MIN_AA and far_share <= HIGH_CONF_MAX_FAR_SHARE:
        return "high"
    return "medium"


def stats_map(p: dict) -> dict[str, float]:
    out = {k: 0.0 for k in CAREER_KEYS}
    for s in p.get("stats") or []:
        name = s.get("name")
        if name in out:
            out[name] = float(s.get("value") or 0)
    return out


def load_attack_types() -> dict[str, str]:
    if not CHAMP_INDEX.exists():
        return {}
    raw = json.loads(CHAMP_INDEX.read_text())
    return {
        k: (v.get("attackType") or "MELEE")
        for k, v in raw.items()
        if isinstance(v, dict)
    }


def compact_base(p: dict) -> dict:
    sm = stats_map(p)
    return {
        "kills": int(sm["CHAMPIONS_KILLED"]),
        "deaths": int(sm["NUM_DEATHS"]),
        "assists": int(sm["ASSISTS"]),
        "cs": int(sm["MINIONS_KILLED"] + sm["NEUTRAL_MINIONS_KILLED"]),
        "jungleCs": int(sm["NEUTRAL_MINIONS_KILLED"]),
        "visionScore": round(sm["VISION_SCORE"], 1),
        "dmgTotal": round(sm["TOTAL_DAMAGE_DEALT"]),
        "dmgToChamps": round(sm["TOTAL_DAMAGE_DEALT_TO_CHAMPIONS"]),
        "physToChamps": round(sm["PHYSICAL_DAMAGE_DEALT_TO_CHAMPIONS"]),
        "magicToChamps": round(sm["MAGIC_DAMAGE_DEALT_TO_CHAMPIONS"]),
        "trueToChamps": round(sm["TRUE_DAMAGE_DEALT_TO_CHAMPIONS"]),
        "dmgTaken": round(sm["TOTAL_DAMAGE_TAKEN"]),
        "dmgTakenFromChamps": round(sm["TOTAL_DAMAGE_TAKEN_FROM_CHAMPIONS"]),
        "selfMitigated": round(sm["TOTAL_DAMAGE_SELF_MITIGATED"]),
        "dmgToTurrets": round(sm["TOTAL_DAMAGE_DEALT_TO_TURRETS"]),
        "dmgToBuildings": round(sm["TOTAL_DAMAGE_DEALT_TO_BUILDINGS"]),
        "dmgToObjectives": round(sm["TOTAL_DAMAGE_DEALT_TO_OBJECTIVES"]),
        "ccToChamps": round(sm["TOTAL_TIME_CROWD_CONTROL_DEALT_TO_CHAMPIONS"], 1),
        "healOnTeammates": round(sm["TOTAL_HEAL_ON_TEAMMATES"]),
        "shieldOnTeammates": round(sm["TOTAL_DAMAGE_SHIELDED_ON_TEAMMATES"]),
        "asPct": round(float(p.get("attackSpeed") or 100), 1),
        "cdr": round(float(p.get("cooldownReduction") or 0), 1),
        "lifeSteal": round(float(p.get("lifeSteal") or 0), 1),
        "spellVamp": round(float(p.get("spellVamp") or 0), 1),
        "hpRegen": round(float(p.get("healthRegen") or 0), 1),
        "gold": int(p.get("totalGold") or 0),
        "goldBag": int(p.get("currentGold") or 0),
    }


def main() -> None:
    global JSONL, TIMELINE
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--jsonl", type=Path, required=True, help="Input canonical rfc461 JSONL")
    ap.add_argument("--timeline", type=Path, required=True, help="Timeline JSON to enrich")
    ap.add_argument("-o", "--output", type=Path, help="Output timeline JSON (defaults to --timeline)")
    args = ap.parse_args()
    JSONL = args.jsonl
    TIMELINE = args.output or args.timeline
    if not JSONL.exists():
        raise SystemExit(f"missing {JSONL}")
    if not args.timeline.exists():
        raise SystemExit(f"missing {args.timeline}")
    attack_types = load_attack_types()
    timeline = json.loads(args.timeline.read_text())
    frames = timeline["frames"]

    grub_kills: list[tuple[int, int]] = []
    structures = seed_structures()
    seen: set[tuple[int, int, int]] = {
        (o, int(round(x)), int(round(z))) for x, z, o in structures
    }
    skill_casts: dict[int, list[int]] = {}
    # Timed structure mutations applied during the stats loop
    structure_events: list[tuple[int, str, float, float, int]] = []

    updates_raw: list[tuple[int, list[dict]]] = []

    with JSONL.open() as f:
        for line in f:
            o = json.loads(line)
            schema = o.get("rfc461Schema")
            t = int(o.get("gameTime") or 0)

            if schema == "epic_monster_kill" and o.get("monsterType") == "VoidGrub":
                grub_kills.append((t, int(o.get("killerTeamID") or 0)))

            elif schema in (
                "turret_plate_destroyed",
                "building_gold_grant",
            ):
                pos = o.get("position") or {}
                x, z = float(pos.get("x") or 0), float(pos.get("z") or 0)
                owner = int(o.get("teamID") or 0)
                if x or z:
                    structure_events.append((t, "upsert", x, z, owner))

            elif schema == "building_destroyed":
                pos = o.get("position") or {}
                x, z = float(pos.get("x") or 0), float(pos.get("z") or 0)
                owner = int(o.get("teamID") or 0)
                if x or z:
                    structure_events.append((t, "upsert", x, z, owner))
                    structure_events.append((t, "remove", x, z, owner))

            elif schema in (
                "skill_used",
                "item_active_ability_used",
                "summoner_spell_used",
            ):
                pid = o.get("participantID")
                if pid is None:
                    pid = o.get("participant")
                if pid is not None:
                    skill_casts.setdefault(int(pid), []).append(t)

            elif schema == "stats_update":
                updates_raw.append((t, list(o.get("participants") or [])))

    for times in skill_casts.values():
        times.sort()
    structure_events.sort(key=lambda e: e[0])
    grub_kills.sort()
    updates_raw.sort(key=lambda x: x[0])

    # Apply all upserts from the match onto the seed (refine coords) before sim,
    # then re-seed live state and apply removes in time order during the loop.
    for _t, kind, x, z, owner in structure_events:
        if kind == "upsert":
            upsert_structure(structures, seen, x, z, owner)

    # Live map starts from refined seed; destroys applied in-time.
    live = list(structures)
    live_seen = set(seen)
    print(
        f"stats_updates={len(updates_raw)} frames={len(frames)} "
        f"grub_kills={len(grub_kills)} structures_seeded={len(live)} "
        f"skill_casters={len(skill_casts)}"
    )

    touch_cum: dict[int, float] = {}
    burn_sec: dict[int, float] = {}
    burn_start_ms: dict[int, float] = {}
    burn_end_ms: dict[int, float] = {}
    last_turret_dmg: dict[int, float] = {}
    last_t_ms: dict[int, float] = {}
    last_hunger_proc_ms: dict[int, float] = {}
    hunger_procs: dict[int, int] = {}
    siege_streak: dict[int, bool] = {}
    refresh_aa: dict[int, int] = {}
    refresh_rejected_far: dict[int, int] = {}
    refresh_rejected_ability: dict[int, int] = {}
    refresh_rejected_skill: dict[int, int] = {}
    refresh_mite: dict[int, int] = {}

    stacks_100 = 0
    stacks_200 = 0
    gi = 0
    si = 0
    have_map = len(live) > 0

    updates: list[tuple[int, dict[int, dict]]] = []

    for t, participants in updates_raw:
        while gi < len(grub_kills) and grub_kills[gi][0] <= t:
            _, team = grub_kills[gi]
            if team == 100:
                stacks_100 = min(MAX_STACKS, stacks_100 + 1)
            elif team == 200:
                stacks_200 = min(MAX_STACKS, stacks_200 + 1)
            gi += 1

        while si < len(structure_events) and structure_events[si][0] <= t:
            _et, kind, x, z, owner = structure_events[si]
            if kind == "upsert":
                upsert_structure(live, live_seen, x, z, owner)
            else:
                remove_structure_near(live, live_seen, x, z, owner)
            si += 1

        by_pid: dict[int, dict] = {}
        for p in participants:
            pid = int(p["participantID"])
            team = int(p.get("teamID") or 0)
            stacks = stacks_100 if team == 100 else stacks_200 if team == 200 else 0
            champ = p.get("championName") or ""
            ranged = (attack_types.get(champ) or "MELEE").upper() == "RANGED"
            tick_table = TICK_RANGED if ranged else TICK_MELEE
            tick = tick_table[min(MAX_STACKS, stacks)]

            career = compact_base(p)
            turret_dmg = float(
                next(
                    (
                        s.get("value") or 0
                        for s in (p.get("stats") or [])
                        if s.get("name") == "TOTAL_DAMAGE_DEALT_TO_TURRETS"
                    ),
                    0,
                )
            )

            prev_t = last_t_ms.get(pid, t)
            dt_s = max(0.0, (t - prev_t) / 1000.0)
            cum = touch_cum.get(pid, 0.0)
            active_burn = burn_sec.get(pid, 0.0)
            bstart = burn_start_ms.get(pid, 0.0)
            bend = burn_end_ms.get(pid, 0.0)

            if tick > 0 and bend > prev_t and dt_s > 0:
                win_lo = max(float(prev_t), bstart)
                win_hi = min(float(t), bend)
                active_s = max(0.0, (win_hi - win_lo) / 1000.0)
                cum += (tick / TICK_INTERVAL) * active_s
                active_burn += active_s

            prev_dmg = last_turret_dmg.get(pid, turret_dmg)
            delta = turret_dmg - prev_dmg
            dmg_up = delta > 0.5
            near, _nd = near_enemy_structure(p.get("position"), team, live, ranged)
            max_aa = max_aa_delta(p, dt_s)
            size_ok = dmg_up and delta <= max_aa
            skill_hit = skill_in_window(skill_casts.get(pid, []), int(prev_t), int(t))

            # Touch true often lands in TOTAL_DAMAGE_DEALT_TO_TURRETS while the
            # burn is already running — even after the champ walks away. Hunger
            # mites can also keep applying Touch while the summoner is far.
            # Those ticks are not failed AA refreshes.
            burn_was_active = bend > prev_t and tick > 0
            expected_touch = (tick / TICK_INTERVAL) * dt_s if tick > 0 else 0.0
            tick_shaped = dmg_up and delta <= expected_touch * 1.4 + 8.0
            burn_ticks_only = tick > 0 and tick_shaped and (
                burn_was_active or (stacks >= HUNGER_AT and not near)
            )

            if not burn_ticks_only:
                if stacks > 0 and dmg_up and not size_ok:
                    refresh_rejected_ability[pid] = (
                        refresh_rejected_ability.get(pid, 0) + 1
                    )
                if stacks > 0 and dmg_up and size_ok and skill_hit:
                    refresh_rejected_skill[pid] = (
                        refresh_rejected_skill.get(pid, 0) + 1
                    )
                if (
                    stacks > 0
                    and dmg_up
                    and size_ok
                    and not skill_hit
                    and have_map
                    and not near
                ):
                    refresh_rejected_far[pid] = refresh_rejected_far.get(pid, 0) + 1

            # Clean AA refresh (not burn-tick noise)
            aa_like = (not burn_ticks_only) and size_ok and not skill_hit
            sieging = stacks > 0 and aa_like and (near if have_map else True)

            if sieging and tick > 0:
                bstart = float(t) + FIRST_TICK_DELAY * 1000.0
                bend = float(t) + BURN_DURATION * 1000.0
                refresh_aa[pid] = refresh_aa.get(pid, 0) + 1
                if stacks >= HUNGER_AT:
                    last_proc = last_hunger_proc_ms.get(pid, -1e18)
                    if t - last_proc >= HUNGER_CD * 1000.0:
                        last_hunger_proc_ms[pid] = float(t)
                        hunger_procs[pid] = hunger_procs.get(pid, 0) + 1
                        refresh_mite[pid] = refresh_mite.get(pid, 0) + 1
                        bend = max(bend, float(t) + BURN_DURATION * 1000.0)
                siege_streak[pid] = True
            elif siege_streak.get(pid) and stacks >= HUNGER_AT and tick > 0:
                bend = max(bend, float(t) + BURN_DURATION * 1000.0)
                refresh_mite[pid] = refresh_mite.get(pid, 0) + 1
                siege_streak[pid] = False
            else:
                siege_streak[pid] = False

            touch_cum[pid] = cum
            burn_sec[pid] = active_burn
            burn_start_ms[pid] = bstart
            burn_end_ms[pid] = bend
            last_turret_dmg[pid] = turret_dmg
            last_t_ms[pid] = float(t)

            aa_n = refresh_aa.get(pid, 0)
            far_n = refresh_rejected_far.get(pid, 0)
            abil_n = refresh_rejected_ability.get(pid, 0)
            skill_n = refresh_rejected_skill.get(pid, 0)
            mite_n = refresh_mite.get(pid, 0)
            conf = touch_confidence(
                have_structure_map=have_map, aa_n=aa_n, far_n=far_n
            )

            career["touchDmg"] = round(cum)
            career["touchTick"] = tick
            career["touchStacks"] = stacks
            career["hungerActive"] = stacks >= HUNGER_AT
            career["touchRanged"] = ranged
            career["touchBurnSec"] = round(active_burn, 2)
            career["touchHungerProcs"] = hunger_procs.get(pid, 0)
            career["touchRefreshAa"] = aa_n
            career["touchRejectedFar"] = far_n
            career["touchRejectedAbility"] = abil_n
            career["touchRejectedSkill"] = skill_n
            career["touchRefreshMite"] = mite_n
            career["touchConfidence"] = conf
            career["touchModel"] = MODEL_VERSION
            by_pid[pid] = career

        updates.append((t, by_pid))

    ui = 0
    attached = 0
    for fr in frames:
        t = fr["t"]
        while ui + 1 < len(updates) and updates[ui + 1][0] <= t:
            ui += 1
        by_pid = updates[ui][1] if updates else {}
        for u in fr["units"]:
            career = by_pid.get(u["pid"])
            if career:
                u["career"] = career
                attached += 1

    timeline["hasCareerStats"] = True
    timeline["hasTouchDmg"] = True
    timeline["touchModel"] = MODEL_VERSION
    timeline["touchPatch"] = "26.11"
    TIMELINE.parent.mkdir(parents=True, exist_ok=True)
    TIMELINE.write_text(json.dumps(timeline, separators=(",", ":")))
    size_mb = TIMELINE.stat().st_size / (1024 * 1024)

    max_touch = 0
    highs = 0
    for _t, bp in updates:
        for c in bp.values():
            max_touch = max(max_touch, int(c.get("touchDmg") or 0))
    if updates:
        for c in updates[-1][1].values():
            if c.get("touchConfidence") == "high":
                highs += 1

    print(
        f"wrote {TIMELINE} ({size_mb:.2f} MB), career cells={attached}, "
        f"max touchDmg={max_touch}, endframe high_conf={highs}"
    )


if __name__ == "__main__":
    main()
