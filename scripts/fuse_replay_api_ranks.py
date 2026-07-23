#!/usr/bin/env python3
"""Fuse UpgradeSpellAns ranks into rfc461 stats_update participants.

Requires Gate B2 evidence from ``rofl2_upgrade_spell_ranks`` plus the same
CastSpellAns identity binding used for trusted HP. Does not invent ranks;
cumulative state starts at [0,0,0,0] before the first upgrade.

Binds netIds by game_info identity (or healthNetId after HP fuse), never by
scrambled per-frame championName. Rewrites champion/player labels from the
CastSpell identity binding on every fused stats row.

Example:
  python3 scripts/fuse_replay_api_ranks.py --product \\
    --jsonl artifacts/rofl/3264361042/events.hp-trusted.rfc461.jsonl \\
    --ranks-evidence docs/rofl-research/upgrade-spell-ranks-BR1-3264361042.json \\
    --castspell-identity docs/rofl-research/castspell-identity-BR1-3264361042.json \\
    -o artifacts/rofl/3264361042/events.ranks-trusted.rfc461.jsonl
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from rofl2_create_hero_discover import PROVEN_HERO_NET_IDS  # noqa: E402
from rofl2_packet_decrypt_probe import DecryptError  # noqa: E402
from rofl2_upgrade_spell_ranks import ABILITY_RANKS_SOURCE  # noqa: E402
from rofl_fuse_identity import (  # noqa: E402
    apply_roster_labels,
    pid_bindings_from_game_info,
    resolve_participant_net_id,
)

RANK_KEYS = ("ability1Level", "ability2Level", "ability3Level", "ability4Level")


def _load_jsonl(path: Path) -> List[dict]:
    rows: List[dict] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def ranks_at_time(
    snapshots: Sequence[Mapping[str, Any]],
    *,
    game_time_ms: int,
) -> Dict[int, List[int]]:
    """Latest cumulative ranks per netId at or before game_time_ms."""
    state: Dict[int, List[int]] = {nid: [0, 0, 0, 0] for nid in PROVEN_HERO_NET_IDS}
    for snap in snapshots:
        t = int(snap.get("gameTimeMs") or 0)
        if t > game_time_ms:
            break
        nid = int(snap["netId"])
        ranks = list(snap.get("ranksAfter") or [])
        if len(ranks) == 4:
            state[nid] = [int(x) for x in ranks]
    return state


def fuse_ranks_product(
    rows: Sequence[Mapping[str, Any]],
    *,
    ranks_evidence: Mapping[str, Any],
    castspell_identity: Mapping[str, Any],
) -> Tuple[List[dict], Dict[str, Any]]:
    if ranks_evidence.get("abilityRanksTrusted") is not True:
        raise DecryptError("ranks evidence is not abilityRanksTrusted")
    if ranks_evidence.get("ok") is not True:
        raise DecryptError("ranks evidence ok!=true")
    snapshots = list(ranks_evidence.get("snapshots") or [])
    if len(snapshots) < 50:
        raise DecryptError("ranks evidence has too few snapshots")

    pid_to_net, pid_to_labels, pid_to_identity = pid_bindings_from_game_info(
        rows, castspell_identity
    )

    out: List[dict] = []
    fused_frames = 0
    fused_participants = 0
    for original in rows:
        schema = original.get("rfc461Schema")
        if schema == "game_info":
            gi = dict(original)
            gi["participants"] = [
                apply_roster_labels(
                    participant, pid_to_labels[int(participant["participantID"])]
                )
                for participant in original.get("participants") or []
            ]
            out.append(gi)
            continue
        if schema != "stats_update":
            row = dict(original)
            if schema == "rofl_coverage":
                decoded = list(row.get("decoded") or [])
                marker = "ability_ranks_upgrade_spell_ans_636"
                if marker not in decoded:
                    decoded.append(marker)
                row["decoded"] = decoded
                missing = [
                    m
                    for m in (row.get("missing") or [])
                    if m != "abilityRanks"
                ]
                row["missing"] = missing
                prov = dict(row.get("provenance") or {})
                prov["abilityRanksSource"] = ABILITY_RANKS_SOURCE
                prov["abilityRanksTrusted"] = True
                notes = str(prov.get("notes") or "")
                note = (
                    "Ability ranks from PKT_NPC_UpgradeSpellAns_s opcode 636 "
                    "first-write level@+0x10 / slot@+0x11 with CastSpellAns identity."
                )
                if note not in notes:
                    prov["notes"] = (notes + " " if notes else "") + note
                row["provenance"] = prov
            out.append(row)
            continue

        frame_time = int(original.get("gameTime") or 0)
        state = ranks_at_time(snapshots, game_time_ms=frame_time)
        participants: List[dict] = []
        for participant in original.get("participants") or []:
            pid = int(participant["participantID"])
            net_id = resolve_participant_net_id(
                participant, pid=pid, pid_to_net=pid_to_net
            )
            ranks = state.get(net_id) or [0, 0, 0, 0]
            fused = apply_roster_labels(participant, pid_to_labels[pid])
            for key, value in zip(RANK_KEYS, ranks):
                fused[key] = int(value)
            fused["abilityRanksSource"] = ABILITY_RANKS_SOURCE
            fused["abilityRanksNetId"] = net_id
            fused["abilityRanksIdentityKey"] = pid_to_identity[pid]
            fused["abilityRanksCoverage"] = "cumulative_upgrade_spell_ans"
            participants.append(fused)
            fused_participants += 1
        frame = dict(original)
        frame["participants"] = participants
        out.append(frame)
        fused_frames += 1

    summary = {
        "ok": True,
        "abilityRanksSource": ABILITY_RANKS_SOURCE,
        "abilityRanksKnown": True,
        "fusedFrames": fused_frames,
        "fusedParticipants": fused_participants,
        "eventCount": ranks_evidence.get("eventCount"),
        "schema": ranks_evidence.get("schema"),
        "identityBinding": "stable_identity_to_net_id",
    }
    return out, summary


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--jsonl", type=Path, required=True)
    ap.add_argument("--ranks-evidence", type=Path, required=True)
    ap.add_argument(
        "--castspell-identity",
        type=Path,
        default=Path("docs/rofl-research/castspell-identity-BR1-3264361042.json"),
    )
    ap.add_argument("-o", "--out", type=Path, required=True)
    ap.add_argument("--product", action="store_true")
    args = ap.parse_args(argv)
    if not args.product:
        print("refusing non-product ranks fuse", file=sys.stderr)
        return 2
    rows = _load_jsonl(args.jsonl)
    ranks_evidence = json.loads(args.ranks_evidence.read_text(encoding="utf-8"))
    castspell = json.loads(args.castspell_identity.read_text(encoding="utf-8"))
    try:
        fused, summary = fuse_ranks_product(
            rows,
            ranks_evidence=ranks_evidence,
            castspell_identity=castspell,
        )
    except DecryptError as exc:
        print(f"fuse failed: {exc}", file=sys.stderr)
        return 2
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as handle:
        for row in fused:
            handle.write(json.dumps(row, separators=(",", ":")) + "\n")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
