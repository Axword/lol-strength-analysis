#!/usr/bin/env python3
"""
Validate fight-odds prior against real kill clusters from the Riot JSONL.

Ground truth: champion_kill clusters within 45s. Favorite must match cluster
winner when |goldΔ| >= 3k or baron is live — the regime where leftover-HP%
falsely called Blue ahead in FUR vs G2 at ~22:30.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JSONL = Path("/Users/river/Desktop/events_2970115_1_riot.jsonl")
TIMELINE = ROOT / "public/data/fur_vs_g2_timeline.json"


def sigmoid(x: float) -> float:
    if x > 20:
        return 1.0
    if x < -20:
        return 0.0
    return 1.0 / (1.0 + math.exp(-x))


def mean_level(units, team: int) -> float:
    rows = [u for u in units if u["team"] == team and u.get("alive", True)]
    if not rows:
        rows = [u for u in units if u["team"] == team]
    if not rows:
        return 1.0
    return sum(u["level"] for u in rows) / len(rows)


def living(units, team: int) -> int:
    return sum(1 for u in units if u["team"] == team and u.get("alive", True) and u.get("hp", 1) > 0)


def game_state_logit(score, units) -> float:
    blue, red = score["blue"], score["red"]
    gold_delta = blue["gold"] - red["gold"]
    gold_term = (gold_delta / 4000.0) * 1.45
    level_term = (mean_level(units, 100) - mean_level(units, 200)) * 0.4
    obj = 0.0
    if blue.get("baronActive"):
        obj += 1.15
    if red.get("baronActive"):
        obj -= 1.15
    if blue.get("elderActive"):
        obj += 1.35
    if red.get("elderActive"):
        obj -= 1.35
    obj += (blue.get("dragonCount", 0) - red.get("dragonCount", 0)) * 0.38
    if blue.get("hasSoul"):
        obj += 0.85
    if red.get("hasSoul"):
        obj -= 0.85
    obj += (blue.get("towers", 0) - red.get("towers", 0)) * 0.14
    obj += (blue.get("voidGrubs", 0) - red.get("voidGrubs", 0)) * 0.1
    obj += ((blue.get("kills", 0) - red.get("kills", 0)) / 5.0) * 0.45
    alive_term = (living(units, 100) - living(units, 200)) * 0.55
    return gold_term + level_term + obj + alive_term


def apply_floors(p_blue: float, score) -> tuple[float, str]:
    blue, red = score["blue"], score["red"]
    # Baron + gold floor (mirrors TS)
    if red.get("baronActive") and (red["gold"] - blue["gold"]) >= 3000:
        if (1 - p_blue) < 0.7:
            return 0.28, "red"
    if blue.get("baronActive") and (blue["gold"] - red["gold"]) >= 3000:
        if p_blue < 0.7:
            return 0.72, "blue"
    # Extreme gold + light combat assumed → gold leader
    if abs(blue["gold"] - red["gold"]) >= 5000:
        leader = "blue" if blue["gold"] >= red["gold"] else "red"
        # poke weight floor: force leader
        if leader == "red" and p_blue > 0.42:
            return min(p_blue, 0.35), "red"
        if leader == "blue" and p_blue < 0.58:
            return max(p_blue, 0.65), "blue"
    winner = "blue" if p_blue >= 0.58 else ("red" if p_blue <= 0.42 else "draw")
    return p_blue, winner


def main() -> int:
    if not JSONL.exists():
        print(f"MISSING jsonl: {JSONL}", file=sys.stderr)
        return 2
    if not TIMELINE.exists():
        print(f"MISSING timeline: {TIMELINE}", file=sys.stderr)
        return 2

    tl = json.loads(TIMELINE.read_text())
    frames = tl["frames"]

    kills = []
    with JSONL.open() as f:
        for line in f:
            o = json.loads(line)
            if o.get("rfc461Schema") == "champion_kill":
                kills.append(o)

    clusters = []
    cur = []
    for k in kills:
        if not cur or k["gameTime"] - cur[0]["gameTime"] < 45_000:
            cur.append(k)
        else:
            clusters.append(cur)
            cur = [k]
    if cur:
        clusters.append(cur)

    print(f"clusters={len(clusters)} kills={len(kills)}")
    fails = []
    checked = 0

    for c in clusters:
        t0 = c[0]["gameTime"]
        blue_k = sum(1 for k in c if k["killerTeamID"] == 100)
        red_k = sum(1 for k in c if k["killerTeamID"] == 200)
        if blue_k == red_k:
            continue
        truth = "BLUE" if blue_k > red_k else "RED"
        fr = min(frames, key=lambda x: abs(x["t"] - t0))
        sc = fr.get("score")
        if not sc:
            continue
        gold_delta = sc["blue"]["gold"] - sc["red"]["gold"]
        baron = sc["blue"].get("baronActive") or sc["red"].get("baronActive")
        # Strict regime: big gold gap or baron live
        if abs(gold_delta) < 3000 and not baron:
            continue

        logit = game_state_logit(sc, fr["units"])
        p_blue = sigmoid(logit)
        p_blue, favorite = apply_floors(p_blue, sc)
        checked += 1
        ok = (favorite == "blue" and truth == "BLUE") or (
            favorite == "red" and truth == "RED"
        )
        mark = "OK" if ok else "FAIL"
        print(
            f"{mark} {t0/60000:5.1f}m truth={truth} fav={favorite.upper()} "
            f"pBlue={p_blue:.2f} goldΔ={gold_delta:.0f} baronR={sc['red'].get('baronActive')} "
            f"kills B{blue_k}/R{red_k}"
        )
        if not ok:
            fails.append((t0, truth, favorite, p_blue, gold_delta))

    # Special case: 22:31 frame must favor Red hard
    target = 22 * 60 * 1000 + 31 * 1000
    fr = min(frames, key=lambda x: abs(x["t"] - target))
    sc = fr["score"]
    p_blue = sigmoid(game_state_logit(sc, fr["units"]))
    p_blue, fav = apply_floors(p_blue, sc)
    print(
        f"\n22:31 check: fav={fav} pBlue={p_blue:.3f} "
        f"goldΔ={sc['blue']['gold']-sc['red']['gold']:.0f} "
        f"baronR={sc['red'].get('baronActive')}"
    )
    if fav != "red" or p_blue > 0.35:
        fails.append((target, "RED", fav, p_blue, sc["blue"]["gold"] - sc["red"]["gold"]))
        print("FAIL 22:31 must be Red-favored with pBlue <= 0.35")

    print(f"\nchecked={checked} fails={len(fails)}")
    if fails:
        return 1
    print("PASS — fight-odds prior matches JSONL kill clusters in gold/baron regime")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
