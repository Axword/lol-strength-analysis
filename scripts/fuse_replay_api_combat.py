#!/usr/bin/env python3
"""Fuse PE-proven type-107 combat into rfc461 stats_update participants.

Requires Gate B1 ``rofl-combat-wire-proof-v1`` with ``combatTrusted=true`` plus
CastSpellAns identity winners. Does not invent combat floats; only emits
resolved AD/AP/armor/MR/AS when a timed sample has enough components.

Binds netIds by game_info identity (or healthNetId after HP fuse), never by
scrambled per-frame championName. Rewrites champion/player labels from the
CastSpell identity binding on every fused stats row.

Example:
  python3 scripts/fuse_replay_api_combat.py --product \\
    --jsonl artifacts/rofl/3264361042/events.ranks-trusted.rfc461.jsonl \\
    --combat-evidence docs/rofl-research/combat-wire-proof-BR1-3264361042.json \\
    --castspell-identity docs/rofl-research/castspell-identity-BR1-3264361042.json \\
    -o artifacts/rofl/3264361042/events.combat-trusted.rfc461.jsonl
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

from rofl2_packet_decrypt_probe import DecryptError  # noqa: E402
from rofl_combat_wire_table import COMBAT_STATS_SOURCE  # noqa: E402
from rofl_fuse_identity import (  # noqa: E402
    apply_roster_labels,
    pid_bindings_from_game_info,
    resolve_participant_net_id,
)
from rofl_replication_fields import resolve_combat_stats  # noqa: E402

FUR_KEYS = (
    "attackDamage",
    "abilityPower",
    "armor",
    "magicResist",
    "attackSpeed",
)


def _load_jsonl(path: Path) -> List[dict]:
    rows: List[dict] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def combat_at_time(
    samples: Sequence[Mapping[str, Any]],
    *,
    game_time_ms: int,
) -> Dict[int, Dict[str, float]]:
    """Latest resolved combat per netId at or before game_time_ms.

    Components merge across packets; once a hero has a full FUR set, that
    resolved row is carried forward until a newer complete sample arrives.
    """
    state: Dict[int, Dict[str, float]] = {}
    components: Dict[int, Dict[str, float]] = {}
    for sample in samples:
        t = int(sample.get("gameTimeMs") or 0)
        if t > game_time_ms:
            break
        nid = int(sample["netId"])
        comps = dict(sample.get("components") or {})
        if comps:
            merged = dict(components.get(nid) or {})
            merged.update(comps)
            components[nid] = merged
        resolved = sample.get("resolved")
        if not resolved:
            resolved = resolve_combat_stats(components.get(nid) or {})
        if not resolved:
            continue
        if not (
            float(resolved.get("attackDamage") or 0) > 0
            and float(resolved.get("armor") or 0) > 0
            and float(resolved.get("magicResist") or 0) > 0
            and float(resolved.get("attackSpeed") or 0) > 0
            and "abilityPower" in resolved
        ):
            continue
        state[nid] = {k: float(resolved[k]) for k in FUR_KEYS}
    return state


def fuse_combat_product(
    rows: Sequence[Mapping[str, Any]],
    *,
    combat_evidence: Mapping[str, Any],
    castspell_identity: Mapping[str, Any],
) -> Tuple[List[dict], Dict[str, Any]]:
    if combat_evidence.get("combatTrusted") is not True:
        raise DecryptError("combat evidence is not combatTrusted")
    if combat_evidence.get("ok") is not True:
        raise DecryptError("combat evidence ok!=true")
    if combat_evidence.get("wireTableProven") is not True:
        raise DecryptError("combat evidence wireTableProven!=true")
    timed = combat_evidence.get("timedCombatEvidence") or {}
    samples = list(timed.get("samples") or [])
    if len(samples) < 10:
        raise DecryptError(f"combat evidence has too few timed samples ({len(samples)})")

    pid_to_net, pid_to_labels, pid_to_identity = pid_bindings_from_game_info(
        rows, castspell_identity
    )
    samples_sorted = sorted(samples, key=lambda s: int(s.get("gameTimeMs") or 0))

    out: List[dict] = []
    fused_frames = 0
    fused_participants = 0
    frames_partial = 0
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
                marker = "combat_type107_pe_wire_table"
                if marker not in decoded:
                    decoded.append(marker)
                row["decoded"] = decoded
                missing = [
                    m
                    for m in (row.get("missing") or [])
                    if m != "combatStats"
                ]
                row["missing"] = missing
                prov = dict(row.get("provenance") or {})
                prov["combatStatsSource"] = COMBAT_STATS_SOURCE
                prov["combatTrusted"] = True
                notes = str(prov.get("notes") or "")
                note = (
                    "Combat from type-107 PE wire table "
                    "(w3→primary, shared-context secondary) with CastSpellAns identity."
                )
                if note not in notes:
                    prov["notes"] = (notes + " " if notes else "") + note
                row["provenance"] = prov
            out.append(row)
            continue

        frame_time = int(original.get("gameTime") or 0)
        state = combat_at_time(samples_sorted, game_time_ms=frame_time)
        participants: List[dict] = []
        frame_all = True
        for participant in original.get("participants") or []:
            pid = int(participant["participantID"])
            net_id = resolve_participant_net_id(
                participant, pid=pid, pid_to_net=pid_to_net
            )
            fused = apply_roster_labels(participant, pid_to_labels[pid])
            combat = state.get(net_id)
            if combat:
                for key in FUR_KEYS:
                    fused[key] = float(combat[key])
                fused["combatStatsSource"] = COMBAT_STATS_SOURCE
                fused["combatStatsNetId"] = net_id
                fused["combatStatsIdentityKey"] = pid_to_identity[pid]
                fused_participants += 1
            else:
                frame_all = False
                if fused.get("combatStatsSource") not in (
                    None,
                    "unavailable_replay_api",
                    "unavailable",
                    "unknown",
                ):
                    pass
                else:
                    fused["combatStatsSource"] = "unavailable_replay_api"
                    for key in FUR_KEYS:
                        fused.pop(key, None)
            participants.append(fused)
        frame = dict(original)
        frame["participants"] = participants
        out.append(frame)
        fused_frames += 1
        if not frame_all:
            frames_partial += 1

    summary = {
        "ok": True,
        "combatStatsSource": COMBAT_STATS_SOURCE,
        "combatStatsKnown": frames_partial == 0 and fused_participants > 0,
        "combatTrusted": True,
        "fusedFrames": fused_frames,
        "fusedParticipants": fused_participants,
        "framesPartialCombat": frames_partial,
        "sampleCount": len(samples_sorted),
        "schema": combat_evidence.get("schema"),
        "identityBinding": "stable_identity_to_net_id",
    }
    return out, summary


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--jsonl", type=Path, required=True)
    ap.add_argument("--combat-evidence", type=Path, required=True)
    ap.add_argument(
        "--castspell-identity",
        type=Path,
        default=Path("docs/rofl-research/castspell-identity-BR1-3264361042.json"),
    )
    ap.add_argument("-o", "--out", type=Path, required=True)
    ap.add_argument("--product", action="store_true")
    args = ap.parse_args(argv)
    if not args.product:
        print("refusing non-product fuse (pass --product)", file=sys.stderr)
        return 2
    evidence = json.loads(args.combat_evidence.read_text(encoding="utf-8"))
    identity = json.loads(args.castspell_identity.read_text(encoding="utf-8"))
    rows = _load_jsonl(args.jsonl)
    try:
        out, summary = fuse_combat_product(
            rows, combat_evidence=evidence, castspell_identity=identity
        )
    except DecryptError as exc:
        print(f"fuse failed: {exc}", file=sys.stderr)
        return 2
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as handle:
        for row in out:
            handle.write(json.dumps(row, separators=(",", ":")) + "\n")
    summary_path = args.out.with_name("combat-fuse-summary.json")
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {args.out}")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
