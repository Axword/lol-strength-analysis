#!/usr/bin/env python3
"""
Convert a ROFL2 replay into a best-effort events_*_riot.jsonl.

What is real today
  - game_info roster from trailing statsJson
  - gameTime on every keyframe (~60s) from plaintext segment headers
  - final-frame combat totals / items / KDA from statsJson
  - game_end from metadata

What is still placeholder / missing
  - per-second positions, live HP, wards, kills, skill casts
  - intermediate stats_update rows use team fountain coordinates as
    position placeholders (marked in rofl_coverage) until packet fields decode

When a future decryptor emits maknee-shaped events[], use
scripts/maknee_packets_to_jsonl.py instead — same rfc461 helpers.

Example:
  python3 scripts/rofl2_to_jsonl.py \\
    "$HOME/Documents/League of Legends/Replays/BR1-3263797356.rofl" \\
    -o "$HOME/Desktop/events_BR1-3263797356_rofl.jsonl"
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rfc461_emit import (  # noqa: E402
    coverage_line,
    fountain_for_team,
    game_end_line,
    game_info_line,
    participant_row,
    provenance_record,
    stats_update_line,
    write_jsonl,
)
from rofl2_probe import extract_segments, parse_rofl2  # noqa: E402
from rofl_metadata import parse_filename_identity  # noqa: E402

ROLE_MAP = {
    "TOP": "TOP",
    "JUNGLE": "JUNGLE",
    "MIDDLE": "MID",
    "MID": "MID",
    "BOTTOM": "BOTTOM",
    "BOT": "BOTTOM",
    "UTILITY": "SUPPORT",
    "SUPPORT": "SUPPORT",
}


def _i(v, default=0):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _game_id_from_path(path: Path, meta_players: list) -> int:
    identity = parse_filename_identity(path, required=False)
    if identity["gameId"] is not None:
        return int(identity["gameId"])
    # Research-only fallback for non-standard fixture filenames. Product ingest
    # requires the true <platform>-<matchCode>.rofl filename contract.
    seed = str(meta_players[0].get("PUUID") or path.stem) if meta_players else path.stem
    return int(hashlib.sha256(seed.encode("utf-8")).hexdigest()[:8], 16) % 2_000_000_000


def _role(p: dict) -> str:
    raw = (p.get("TEAM_POSITION") or p.get("INDIVIDUAL_POSITION") or "").upper()
    return ROLE_MAP.get(raw, raw or "NONE")


def _items(p: dict) -> List[dict]:
    out: List[dict] = []
    for k in ("ITEM0", "ITEM1", "ITEM2", "ITEM3", "ITEM4", "ITEM5", "ITEM6"):
        iid = _i(p.get(k))
        if iid:
            out.append({"itemID": iid, "itemCooldown": 0})
    return out


def _parse_body_time(data: bytes) -> Optional[float]:
    if len(data) < 5:
        return None
    t = struct.unpack_from("<f", data, 1)[0]
    if math.isfinite(t) and -0.5 <= t <= 20_000:
        return float(t)
    return None


def build_participants_base(players: List[dict]) -> List[dict]:
    base: List[dict] = []
    ordered = sorted(
        enumerate(players),
        key=lambda ip: (_i(ip[1].get("TEAM"), 999), ip[0]),
    )
    for new_pid, (_, p) in enumerate(ordered, start=1):
        team = _i(p.get("TEAM"), 100)
        name = p.get("RIOT_ID_GAME_NAME") or p.get("NAME") or f"player{new_pid}"
        tag = p.get("RIOT_ID_TAG_LINE") or ""
        base.append(
            {
                "participantID": new_pid,
                "teamID": team,
                "championName": p.get("SKIN") or "Unknown",
                "playerName": name,
                "summonerName": name,
                "riotIdGameName": name,
                "riotIdTagLine": tag,
                "puuid": p.get("PUUID") or "",
                "role": _role(p),
                "keystoneID": _i(p.get("KEYSTONE_ID")),
                "summonerSpells": {
                    "summonerSpellOne": {"key": _i(p.get("SUMMONER_SPELL_1"))},
                    "summonerSpellTwo": {"key": _i(p.get("SUMMONER_SPELL_2"))},
                },
                "_final": p,
            }
        )
    return base


def stats_participant(base: dict, *, game_time_ms: int, final: bool) -> Dict[str, Any]:
    p = base["_final"]
    team = base["teamID"]
    fountain = fountain_for_team(team)
    gold = _i(p.get("GOLD_EARNED"), 500) if final else 500
    extra = None
    if final:
        extra = {
            "stats": [
                {"name": "CHAMPIONS_KILLED", "value": _i(p.get("CHAMPIONS_KILLED"))},
                {"name": "NUM_DEATHS", "value": _i(p.get("NUM_DEATHS"))},
                {"name": "ASSISTS", "value": _i(p.get("ASSISTS"))},
                {"name": "MINIONS_KILLED", "value": _i(p.get("MINIONS_KILLED"))},
                {
                    "name": "NEUTRAL_MINIONS_KILLED",
                    "value": _i(p.get("NEUTRAL_MINIONS_KILLED")),
                },
                {
                    "name": "TOTAL_DAMAGE_DEALT_TO_CHAMPIONS",
                    "value": _i(p.get("TOTAL_DAMAGE_DEALT_TO_CHAMPIONS")),
                },
                {
                    "name": "TOTAL_DAMAGE_TAKEN",
                    "value": _i(p.get("TOTAL_DAMAGE_TAKEN")),
                },
                {
                    "name": "TOTAL_DAMAGE_DEALT_TO_TURRETS",
                    "value": _i(p.get("TOTAL_DAMAGE_DEALT_TO_TURRETS")),
                },
            ]
        }
    return participant_row(
        participant_id=base["participantID"],
        team_id=team,
        champion_name=base["championName"],
        player_name=base["playerName"],
        position=fountain,
        position_source="fountain_placeholder",
        alive=True,
        level=_i(p.get("LEVEL"), 1) if final else 1,
        health=1.0,
        health_max=1.0,
        items=_items(p) if final else [],
        total_gold=gold,
        current_gold=gold,
        extra=extra,
    )


def convert(rofl_path: Path) -> List[dict]:
    info = parse_rofl2(rofl_path)
    extracted = extract_segments(info["payload"])
    players = json.loads(info["meta"]["statsJson"])
    bases = build_participants_base(players)
    game_id = _game_id_from_path(rofl_path, players)
    game_len_ms = _i(info["meta"].get("gameLength"))
    version = info["version"]

    keyframes = []
    for seg in extracted["segments"]:
        if seg["type"] != 2:
            continue
        t = _parse_body_time(seg["bytes"])
        if t is None:
            continue
        keyframes.append({"t": t, "id": seg["id_a"], "size": seg["out_len"]})
    keyframes.sort(key=lambda x: x["t"])

    events: List[dict] = [
        coverage_line(
            source="rofl2",
            game_id=game_id,
            decoded=[
                "game_info.roster",
                "keyframe.gameTime",
                "final.box_score",
            ],
            missing=[
                "live.positions",
                "live.hp",
                "wards",
                "champion_kill",
                "skill_used",
                "1Hz_stats_update",
            ],
            notes=(
                "Generated from ROFL2 container only. Positions are team-fountain "
                "placeholders until packet decrypt. When decrypt emits maknee-shaped "
                "events[], run scripts/maknee_packets_to_jsonl.py for live positions."
            ),
            extra={
                "roflPath": str(rofl_path),
                "gameVersion": version,
                "keyframeCount": len(keyframes),
                "chunkCount": sum(1 for s in extracted["segments"] if s["type"] == 1),
                "positionPolicy": "fountain_placeholder_until_packet_decode",
            },
            provenance=provenance_record(
                source="rofl2",
                source_kind="rofl2_container",
                position_coverage="none",
                hp_coverage="none",
                roster_mapping="statsJson_team_then_source_order",
                artifact=str(rofl_path),
                notes="ROFL2 container parsing does not decrypt live packet fields; fountain positions are not live state.",
            ),
        ),
        game_info_line(
            game_id=game_id,
            game_name=rofl_path.stem,
            game_version=version,
            platform_id="ROFL",
            stats_update_interval_ms=60000,
            participants=[
                {
                    "participantID": b["participantID"],
                    "teamID": b["teamID"],
                    "championName": b["championName"],
                    "summonerName": b["summonerName"],
                    "puuid": b["puuid"],
                    "role": b["role"],
                    "keystoneID": b["keystoneID"],
                    "riotId": {
                        "displayName": b["riotIdGameName"],
                        "tagLine": b["riotIdTagLine"],
                    },
                }
                for b in bases
            ],
        ),
    ]

    for i, kf in enumerate(keyframes):
        final = i == len(keyframes) - 1
        game_time_ms = int(round(kf["t"] * 1000))
        events.append(
            stats_update_line(
                game_id=game_id,
                game_time=game_time_ms,
                game_over=final,
                participants=[
                    stats_participant(b, game_time_ms=game_time_ms, final=final)
                    for b in bases
                ],
                extra={"roflKeyframeId": kf["id"]},
            )
        )

    winners = [
        b
        for b in bases
        if str(b["_final"].get("WIN", "")).lower() in ("win", "1", "true")
    ]
    win_team = winners[0]["teamID"] if winners else 0
    events.append(
        game_end_line(
            game_id=game_id,
            game_time=game_len_ms
            or (int(keyframes[-1]["t"] * 1000) if keyframes else 0),
            winning_team=win_team,
        )
    )
    return events


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("rofl", type=Path)
    ap.add_argument("-o", "--output", type=Path, required=True)
    args = ap.parse_args()

    events = convert(args.rofl)
    write_jsonl(args.output, events)

    schemas: Dict[str, int] = {}
    for ev in events:
        schemas[ev["rfc461Schema"]] = schemas.get(ev["rfc461Schema"], 0) + 1
    print(
        json.dumps(
            {"wrote": str(args.output), "lines": len(events), "schemas": schemas},
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
