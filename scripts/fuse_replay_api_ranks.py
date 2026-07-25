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
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from rofl2_create_hero_discover import PROVEN_HERO_NET_IDS  # noqa: E402
from rofl2_packet_decrypt_probe import DecryptError  # noqa: E402
from rofl2_upgrade_spell_ranks import (  # noqa: E402
    ABILITY_RANKS_SOURCE,
    UPGRADE_SPELL_OPCODE_16_13,
    UPGRADE_SPELL_OPCODE_FALLBACK_16_14,
)
from rofl_fuse_identity import (  # noqa: E402
    apply_roster_labels,
    pid_bindings_from_game_info,
    resolve_participant_net_id,
)

RANK_KEYS = ("ability1Level", "ability2Level", "ability3Level", "ability4Level")
# 16.14 BR1 uses opcode 636; 16.13 pro (2970110) uses PE-proven 1012 (R07).
ABILITY_RANKS_SOURCES_BY_OPCODE = {
    UPGRADE_SPELL_OPCODE_FALLBACK_16_14: ABILITY_RANKS_SOURCE,
    UPGRADE_SPELL_OPCODE_16_13: "rofl2_upgrade_spell_ans_1012_first_write",
}


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
    if ranks_evidence.get("productEligible") is not True:
        raise DecryptError("ranks evidence is not productEligible")
    opcode = int(ranks_evidence.get("opcode") or 0)
    expected_source = ABILITY_RANKS_SOURCES_BY_OPCODE.get(opcode)
    if expected_source is None:
        raise DecryptError(
            "ranks evidence opcode must be UpgradeSpellAns "
            f"{UPGRADE_SPELL_OPCODE_FALLBACK_16_14} (16.14) or "
            f"{UPGRADE_SPELL_OPCODE_16_13} (16.13); got {opcode}"
        )
    ev_source = ranks_evidence.get("abilityRanksSource")
    if ev_source not in (None, "", expected_source):
        raise DecryptError(
            f"ranks evidence abilityRanksSource must be {expected_source!r} "
            f"(got {ev_source!r})"
        )
    snapshots = list(ranks_evidence.get("snapshots") or [])
    if len(snapshots) < 50:
        raise DecryptError("ranks evidence has too few snapshots")
    if int(ranks_evidence.get("heroesHit") or 0) < 10:
        raise DecryptError("ranks evidence heroesHit < 10")

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
                marker = f"ability_ranks_upgrade_spell_ans_{opcode}"
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
                prov["abilityRanksSource"] = expected_source
                prov["abilityRanksTrusted"] = True
                notes = str(prov.get("notes") or "")
                if opcode == UPGRADE_SPELL_OPCODE_16_13:
                    note = (
                        "Ability ranks from PKT_NPC_UpgradeSpellAns_s opcode 1012 "
                        "first-write (16.13 slot@+0x12 / level@+0x13) with CastSpellAns identity."
                    )
                else:
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
            fused["abilityRanksSource"] = expected_source
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
        "abilityRanksSource": expected_source,
        "abilityRanksKnown": True,
        "fusedFrames": fused_frames,
        "fusedParticipants": fused_participants,
        "eventCount": ranks_evidence.get("eventCount"),
        "schema": ranks_evidence.get("schema"),
        "identityBinding": "stable_identity_to_net_id",
        "opcode": opcode,
        "pkt": "PKT_NPC_UpgradeSpellAns_s",
        "heroesHit": ranks_evidence.get("heroesHit"),
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
    ap.add_argument(
        "--ship-evidence",
        type=Path,
        default=None,
        help="Copy ranks-evidence.json beside the fused artifact (product honesty).",
    )
    ap.add_argument("--product", action="store_true")
    args = ap.parse_args(argv)
    if not args.product:
        print("refusing non-product ranks fuse", file=sys.stderr)
        return 2
    rows = _load_jsonl(args.jsonl)
    ranks_bytes = args.ranks_evidence.read_bytes()
    ranks_evidence = json.loads(ranks_bytes.decode("utf-8"))
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
    ship_path = args.ship_evidence
    if ship_path is None:
        ship_path = args.out.parent / "ranks-evidence.json"
    ship_path.parent.mkdir(parents=True, exist_ok=True)
    # Byte-identical ship so evidenceSha256 matches the UpgradeSpellAns artifact.
    ship_path.write_bytes(ranks_bytes)
    summary["evidenceSha256"] = hashlib.sha256(ranks_bytes).hexdigest()
    summary["ranksEvidencePath"] = str(ship_path)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
