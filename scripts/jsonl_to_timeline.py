#!/usr/bin/env python3
"""
Build a GameTimeline JSON from rfc461 events_* JSONL (maknee or live-stats).

Creates frames from stats_update rows so the map/review UI can load the file
without needing a pre-existing FUR/G2 skeleton.

Example:
  python3 scripts/jsonl_to_timeline.py \\
    docs/rofl-research/fixtures/events_maknee_stub.jsonl \\
    -o public/data/maknee_stub_timeline.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

MAP_SPAN = 14870.0

# Common DDragon id fixes for lowercase maknee champion strings
CHAMP_ID_FIX = {
    "chogath": "Chogath",
    "missfortune": "MissFortune",
    "monkeyking": "MonkeyKing",
    "jarvaniv": "JarvanIV",
    "leesin": "LeeSin",
    "masteryi": "MasterYi",
    "tahmkench": "TahmKench",
    "xinzhao": "XinZhao",
    "aurelionsol": "AurelionSol",
    "belveth": "Belveth",
    "renataglasc": "Renata",
    "nunu": "Nunu",
    "kogmaw": "KogMaw",
    "reksai": "RekSai",
    "ksante": "KSante",
    "drmundo": "DrMundo",
    "twistedfate": "TwistedFate",
}


def riot_to_norm(x: float, z: float) -> Tuple[float, float]:
    return (
        round(max(0.0, min(1.0, float(x) / MAP_SPAN)), 5),
        round(max(0.0, min(1.0, float(z) / MAP_SPAN)), 5),
    )


def champ_id(raw: str) -> str:
    if not raw:
        return "Unknown"
    key = re.sub(r"[^a-z0-9]", "", raw.lower())
    if key in CHAMP_ID_FIX:
        return CHAMP_ID_FIX[key]
    # PascalCase fallback: missfortune → Missfortune (ok for many); prefer known map
    if raw[0].isupper() and " " not in raw:
        return raw
    return raw[:1].upper() + raw[1:]


def canonical_game_time_ms(game_time: Any) -> int:
    """Return canonical rfc461 gameTime without changing its millisecond scale."""
    try:
        v = float(game_time)
    except (TypeError, ValueError):
        raise SystemExit(f"invalid canonical gameTime milliseconds: {game_time!r}")
    if v < 0 or abs(v - round(v)) > 1e-6:
        raise SystemExit(
            f"gameTime must be a non-negative integer millisecond value: {game_time!r}"
        )
    return int(round(v))


def item_ids(items: Any) -> List[int]:
    out: List[int] = []
    if not isinstance(items, list):
        return out
    for it in items:
        if isinstance(it, dict):
            iid = it.get("itemID") or it.get("itemId") or 0
        else:
            iid = it
        try:
            n = int(iid)
        except (TypeError, ValueError):
            continue
        if n:
            out.append(n)
    return out


def _health_known(participant: dict) -> bool:
    """True when rfc461 participant includes authoritative health values."""
    if participant.get("healthSource") in (
        "unavailable_replay_api",
        "unavailable",
        "unknown",
    ):
        return False
    if "health" not in participant and "healthMax" not in participant:
        return False
    return True


def _combat_stats_known(participant: dict) -> bool:
    src = participant.get("combatStatsSource")
    if src in ("unavailable_replay_api", "unavailable", "unknown"):
        return False
    # Prefer explicit combat fields when present.
    if any(
        k in participant
        for k in ("attackDamage", "abilityPower", "armor", "magicResist", "attackSpeed")
    ):
        return True
    # Explicit zero combat fields are not present on rfc461 rows today; treat
    # missing source as known for backward-compatible live-stats feeds.
    return src is None


def _ability_ranks_known(participant: dict) -> bool:
    src = participant.get("abilityRanksSource")
    if src in ("unavailable_replay_api", "unavailable", "unknown"):
        return False
    return True


def build_timeline(
    jsonl_path: Path,
    *,
    timeline_id: str,
    name: str,
    patch: str,
) -> dict:
    game_info = None
    coverage = None
    stats_rows: List[dict] = []
    game_end = None

    with jsonl_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            o = json.loads(line)
            schema = o.get("rfc461Schema")
            if schema == "rofl_coverage":
                coverage = o
            elif schema == "game_info":
                game_info = o
            elif schema == "stats_update":
                stats_rows.append(o)
            elif schema == "game_end":
                game_end = o

    if not game_info:
        raise SystemExit("JSONL missing game_info")
    if not stats_rows:
        raise SystemExit("JSONL missing stats_update rows")

    participants = []
    for p in game_info.get("participants") or []:
        participants.append(
            {
                "participantID": int(p["participantID"]),
                "summonerName": p.get("summonerName") or p.get("playerName") or "",
                "championName": champ_id(p.get("championName") or "Unknown"),
                "teamID": int(p.get("teamID") or 100),
                "role": p.get("role") or "NONE",
                "keystoneID": p.get("keystoneID"),
            }
        )

    source = "live_stats_jsonl"
    if coverage and coverage.get("source"):
        source = str(coverage["source"])

    frames = []
    for row in stats_rows:
        t = canonical_game_time_ms(row.get("gameTime") or 0)
        units = []
        for p in row.get("participants") or []:
            pos = p.get("position") or {}
            nx, ny = riot_to_norm(float(pos.get("x") or 0), float(pos.get("z") or 0))
            hp_known = _health_known(p)
            combat_known = _combat_stats_known(p)
            ranks_known = _ability_ranks_known(p)
            alive = bool(p.get("alive", True))
            if hp_known:
                hp = float(p.get("health") or 0)
                hp_max = float(p.get("healthMax") or hp or 1)
            else:
                # Neutral numeric storage only — hpKnown=false is authoritative.
                # Do not infer dead (0%) or full (100%) from missing health.
                hp = 0.0
                hp_max = 0.0
            unit: Dict[str, Any] = {
                "pid": int(p["participantID"]),
                "champ": champ_id(p.get("championName") or "Unknown"),
                "name": p.get("playerName") or p.get("summonerName") or "",
                "team": int(p.get("teamID") or 100),
                "role": p.get("role") or "NONE",
                "level": int(p.get("level") or 1),
                "hp": round(hp),
                "hpMax": round(hp_max),
                "alive": alive,
                "hpKnown": hp_known,
                "combatStatsKnown": combat_known,
                "abilityRanksKnown": ranks_known,
                # Neutral zeros when combatStatsKnown=false — flag is authoritative;
                # TypeScript must omit these as liveStats overrides.
                "ad": round(float(p.get("attackDamage") or 0)) if combat_known else 0,
                "ap": round(float(p.get("abilityPower") or 0)) if combat_known else 0,
                "armor": round(float(p.get("armor") or 0)) if combat_known else 0,
                "mr": round(float(p.get("magicResist") or 0)) if combat_known else 0,
                "as": (
                    round(float(p.get("attackSpeed") or 100)) if combat_known else 100
                ),
                "x": nx,
                "y": ny,
                "positionSource": p.get("positionSource") or (
                    "fountain_placeholder"
                    if source == "rofl2"
                    else "live_stats_position"
                ),
                "items": item_ids(p.get("items")),
                "q": int(p.get("ability1Level") or 0),
                "w": int(p.get("ability2Level") or 0),
                "e": int(p.get("ability3Level") or 0),
                "r": int(p.get("ability4Level") or 0),
            }
            units.append(unit)
        frames.append({"t": t, "units": units})

    duration_ms = frames[-1]["t"] if frames else 0
    if game_end and game_end.get("gameTime") is not None:
        duration_ms = max(duration_ms, canonical_game_time_ms(game_end["gameTime"]))

    cadence = 1000
    if len(frames) >= 2:
        cadence = max(1, frames[1]["t"] - frames[0]["t"])

    provenance = dict((coverage or {}).get("provenance") or {})
    if not provenance:
        provenance = {
            "source": source,
            "sourceKind": "rfc461_jsonl",
            "artifact": str(jsonl_path),
            "gameTimeUnit": "milliseconds",
            "coordinateSystem": "riot_live_stats_sr",
            "coordinateOffset": {"x": 7500.0, "z": 7500.0},
            "positionCoverage": "full",
            "hpCoverage": "unknown",
            "rosterMapping": "game_info_participantID",
            "placeholderPolicy": "explicit_positionSource_only",
            "notes": "No rofl_coverage row was present; treating this as a native live-stats JSONL feed.",
        }

    return {
        "id": timeline_id,
        "name": name,
        "patch": patch or (game_info.get("gameVersion") or "unknown"),
        "source": source,
        "provenance": provenance,
        "cadenceMs": cadence,
        "participants": participants,
        "frameCount": len(frames),
        "durationMs": duration_ms,
        "frames": frames,
        "hasScoreboard": False,
        "hasVision": False,
        "hasCareerStats": False,
        "hasMapObjects": False,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("-o", "--output", type=Path, required=True)
    ap.add_argument("--id", default="maknee_stub")
    ap.add_argument("--name", default="Maknee decoded-packets stub")
    ap.add_argument("--patch", default="")
    args = ap.parse_args()

    tl = build_timeline(args.jsonl, timeline_id=args.id, name=args.name, patch=args.patch)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(tl, separators=(",", ":")), encoding="utf-8")
    size_mb = args.output.stat().st_size / (1024 * 1024)

    # Position sanity: mid-game frame should not be all blue fountain
    mid = tl["frames"][len(tl["frames"]) // 2]
    xs = [u["x"] for u in mid["units"]]
    spread = max(xs) - min(xs) if xs else 0
    print(
        json.dumps(
            {
                "wrote": str(args.output),
                "mb": round(size_mb, 2),
                "frames": tl["frameCount"],
                "durationMs": tl["durationMs"],
                "mid_t": mid["t"],
                "mid_x_spread": round(spread, 4),
                "champs": [u["champ"] for u in mid["units"]],
            },
            indent=2,
        )
    )
    if spread < 0.05:
        print("WARN: mid-frame positions barely spread — check coord conversion", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
