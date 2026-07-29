#!/usr/bin/env python3
"""Fuse PE-proven type-107 combat into rfc461 stats_update participants.

Requires Gate B1 ``rofl-combat-wire-proof-v1`` with ``combatTrusted=true`` plus
CastSpellAns identity winners. Does not invent combat floats; only emits
resolved AD/AP/armor/MR/AS when a timed sample has enough components.

Binds netIds by game_info identity (or healthNetId after HP fuse), never by
scrambled per-frame championName. Rewrites champion/player labels from the
CastSpell identity binding on every fused stats row.

Partial product emit (R05/R06 policy):
  * Per-unit combatStatsKnown may be true for FUR-complete heroes when a
    PE-proven sample aligns within ``align_ms`` (default product: ≤500ms).
  * Incomplete heroes stay unavailable / combatStatsKnown=false.
  * Match-level ``combatStatsKnownWouldEmit`` stays false until 10/10.
  * Never invent from livestats; never flip calculatorReady here.

Path 1 hold-forward (authorized):
  * Seed only from PE-proven FUR (AD+AP+armor+MR+AS) within ±align_ms.
  * Once a netId has ≥1 PE FUR seed, hold last floats + known through continuous
    alive until the next PE seed updates them. Death suppresses known on the
    dead frame but does **not** wipe seed history — respawn restores hold from
    the last PE FUR (combat floats do not reset on death; no invented first sample).
  * Disclose ``combatStatsSource=hold_forward`` (and ``combatSource``) on held rows.
  * Never invent before first PE seed; never invent for zero-seed netIds.
  * Path2 PE wirings still needed long-term for denser seeds / early gaps.

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
MAX_PRODUCT_TIME_TOLERANCE_MS = 500
HOLD_FORWARD_SOURCE = "hold_forward"


def _load_jsonl(path: Path) -> List[dict]:
    rows: List[dict] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _resolved_fur(sample: Mapping[str, Any]) -> Optional[Dict[str, float]]:
    resolved = sample.get("resolved")
    if not resolved:
        comps = dict(sample.get("components") or {})
        if comps:
            resolved = resolve_combat_stats(comps)
    if not resolved:
        return None
    if not (
        float(resolved.get("attackDamage") or 0) > 0
        and float(resolved.get("armor") or 0) > 0
        and float(resolved.get("magicResist") or 0) > 0
        and float(resolved.get("attackSpeed") or 0) > 0
        and "abilityPower" in resolved
    ):
        return None
    return {k: float(resolved[k]) for k in FUR_KEYS}


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
        fur = _resolved_fur({"resolved": resolved})
        if not fur:
            continue
        state[nid] = fur
    return state


def index_fur_samples(
    samples: Sequence[Mapping[str, Any]],
) -> Dict[int, List[Tuple[int, Dict[str, float]]]]:
    """netId → sorted (gameTimeMs, FUR floats) for FUR-complete PE samples only."""
    by_net: Dict[int, List[Tuple[int, Dict[str, float]]]] = {}
    for sample in samples:
        fur = _resolved_fur(sample)
        if not fur:
            continue
        nid = int(sample["netId"])
        t = int(sample.get("gameTimeMs") or 0)
        by_net.setdefault(nid, []).append((t, fur))
    for nid in by_net:
        by_net[nid].sort(key=lambda pair: pair[0])
    return by_net


def combat_nearest_within(
    samples_by_net: Mapping[int, Sequence[Tuple[int, Dict[str, float]]]],
    *,
    game_time_ms: int,
    tolerance_ms: int,
) -> Dict[int, Dict[str, float]]:
    """Nearest FUR-complete sample per netId within ±tolerance_ms (no invent)."""
    if tolerance_ms < 0 or tolerance_ms > MAX_PRODUCT_TIME_TOLERANCE_MS:
        raise DecryptError(
            f"combat align tolerance must be 0..{MAX_PRODUCT_TIME_TOLERANCE_MS}ms"
        )
    out: Dict[int, Dict[str, float]] = {}
    for nid, series in samples_by_net.items():
        best: Optional[Tuple[int, Dict[str, float]]] = None
        best_dt: Optional[int] = None
        for t, fur in series:
            dt = abs(int(t) - int(game_time_ms))
            if dt > tolerance_ms:
                # series is sorted; once past window on the right, stop.
                if int(t) > int(game_time_ms) + tolerance_ms:
                    break
                continue
            if best_dt is None or dt < best_dt:
                best_dt = dt
                best = (t, fur)
        if best is not None:
            out[int(nid)] = dict(best[1])
    return out


def fuse_combat_product(
    rows: Sequence[Mapping[str, Any]],
    *,
    combat_evidence: Mapping[str, Any],
    castspell_identity: Mapping[str, Any],
    align_ms: Optional[int] = None,
    allow_partial: bool = False,
    hold_forward: bool = False,
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

    # Product partial / hold-forward require explicit ≤500ms seed alignment.
    if (allow_partial or hold_forward) and align_ms is None:
        align_ms = int(timed.get("timeToleranceMs") or MAX_PRODUCT_TIME_TOLERANCE_MS)
    if hold_forward and align_ms is None:
        raise DecryptError("hold_forward requires align_ms for PE seed windows")
    if align_ms is not None:
        if int(align_ms) < 0 or int(align_ms) > MAX_PRODUCT_TIME_TOLERANCE_MS:
            raise DecryptError(
                f"align_ms must be 0..{MAX_PRODUCT_TIME_TOLERANCE_MS}"
            )

    pid_to_net, pid_to_labels, pid_to_identity = pid_bindings_from_game_info(
        rows, castspell_identity
    )
    samples_sorted = sorted(samples, key=lambda s: int(s.get("gameTimeMs") or 0))
    samples_by_net = index_fur_samples(samples_sorted) if align_ms is not None else {}

    fur_net_ids = sorted(samples_by_net.keys()) if samples_by_net else sorted(
        {
            int(s["netId"])
            for s in samples_sorted
            if _resolved_fur(s) is not None
        }
    )
    heroes_known_count = len(fur_net_ids)
    # Optional allow-list from evidence (R05 policy) — never invent missing.
    allow_net_ids = timed.get("furCompleteNetIds") or combat_evidence.get(
        "heroesWithFurCompleteNetIds"
    )
    allow_set = {int(n) for n in allow_net_ids} if allow_net_ids else None
    if allow_set is not None:
        fur_net_ids = [n for n in fur_net_ids if n in allow_set]
        heroes_known_count = len(fur_net_ids)
        if align_ms is not None:
            samples_by_net = {
                n: series for n, series in samples_by_net.items() if n in allow_set
            }

    out: List[dict] = []
    fused_frames = 0
    fused_participants = 0
    seed_participants = 0
    hold_participants = 0
    frames_partial = 0
    known_by_net: Dict[int, int] = {n: 0 for n in fur_net_ids}
    unknown_forced = 0
    # netId → last PE-proven FUR floats. Kept across death so respawn can
    # restore hold; dead frames still emit unavailable (no invent on corpses).
    held_state: Dict[int, Dict[str, float]] = {}

    def _clear_combat(fused: dict) -> None:
        fused["combatStatsSource"] = "unavailable_replay_api"
        fused.pop("combatSource", None)
        for key in FUR_KEYS:
            fused.pop(key, None)
        fused.pop("combatStatsNetId", None)
        fused.pop("combatStatsIdentityKey", None)
        fused.pop("combatStatsTimeToleranceMs", None)
        fused.pop("combatStatsSeedGameTimeMs", None)

    def _apply_combat(
        fused: dict,
        *,
        net_id: int,
        pid: int,
        combat: Mapping[str, float],
        source: str,
        seed_time_ms: Optional[int] = None,
    ) -> None:
        for key in FUR_KEYS:
            fused[key] = float(combat[key])
        fused["combatStatsSource"] = source
        if source == HOLD_FORWARD_SOURCE:
            fused["combatSource"] = HOLD_FORWARD_SOURCE
        else:
            fused.pop("combatSource", None)
        fused["combatStatsNetId"] = net_id
        fused["combatStatsIdentityKey"] = pid_to_identity[pid]
        if align_ms is not None:
            fused["combatStatsTimeToleranceMs"] = int(align_ms)
        if seed_time_ms is not None:
            fused["combatStatsSeedGameTimeMs"] = int(seed_time_ms)

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
                if allow_partial and marker + "_partial" not in decoded:
                    decoded.append(marker + "_partial")
                if hold_forward and marker + "_hold_forward" not in decoded:
                    decoded.append(marker + "_hold_forward")
                row["decoded"] = decoded
                missing = [
                    m
                    for m in (row.get("missing") or [])
                    if m != "combatStats"
                ]
                # Honest: match-level combatStats still missing while <10/10.
                if (allow_partial or hold_forward) and heroes_known_count < 10:
                    if "combatStats" not in missing:
                        missing.append("combatStats")
                row["missing"] = missing
                prov = dict(row.get("provenance") or {})
                prov["combatStatsSource"] = COMBAT_STATS_SOURCE
                prov["combatTrusted"] = True
                prov["combatStatsKnownWouldEmit"] = False
                if allow_partial:
                    prov["combatPartialEmit"] = True
                    prov["combatAlignMs"] = int(align_ms or 0)
                    prov["combatHeroesFurComplete"] = heroes_known_count
                if hold_forward:
                    prov["combatHoldForward"] = True
                    prov["combatSource"] = HOLD_FORWARD_SOURCE
                    prov["combatAlignMs"] = int(align_ms or 0)
                    prov["combatHeroesFurComplete"] = heroes_known_count
                notes = str(prov.get("notes") or "")
                note = (
                    "Combat from type-107 PE wire table "
                    "(w3→primary, shared-context secondary) with CastSpellAns identity."
                )
                if allow_partial:
                    note += (
                        f" Partial per-hero emit (≤{int(align_ms or 0)}ms); "
                        "match-level combatStatsKnownWouldEmit=false."
                    )
                if hold_forward:
                    note += (
                        f" Path1 hold-forward after PE FUR seed (≤{int(align_ms or 0)}ms); "
                        f"combatSource={HOLD_FORWARD_SOURCE}; "
                        "hold across continuous alive + post-respawn from last PE FUR; "
                        "dead frames unavailable; no invented first sample. "
                        "Path2 new PE wirings still needed long-term."
                    )
                if note not in notes:
                    prov["notes"] = (notes + " " if notes else "") + note
                row["provenance"] = prov
            out.append(row)
            continue

        frame_time = int(original.get("gameTime") or 0)
        if align_ms is not None:
            state = combat_nearest_within(
                samples_by_net,
                game_time_ms=frame_time,
                tolerance_ms=int(align_ms),
            )
        else:
            state = combat_at_time(samples_sorted, game_time_ms=frame_time)
        participants: List[dict] = []
        frame_all = True
        for participant in original.get("participants") or []:
            pid = int(participant["participantID"])
            net_id = resolve_participant_net_id(
                participant, pid=pid, pid_to_net=pid_to_net
            )
            fused = apply_roster_labels(participant, pid_to_labels[pid])
            alive = participant.get("alive", True) is not False
            allowed = allow_set is None or net_id in allow_set
            combat = state.get(net_id) if allowed else None

            if hold_forward and not alive:
                # Dead frame: suppress combat known, but keep last PE FUR so a
                # later alive frame can honestly hold_forward without a new seed.
                frame_all = False
                unknown_forced += 1
                _clear_combat(fused)
                participants.append(fused)
                continue

            if combat is not None:
                held_state[net_id] = dict(combat)
                _apply_combat(
                    fused,
                    net_id=net_id,
                    pid=pid,
                    combat=combat,
                    source=COMBAT_STATS_SOURCE,
                    seed_time_ms=frame_time,
                )
                fused_participants += 1
                seed_participants += 1
                if net_id in known_by_net:
                    known_by_net[net_id] += 1
            elif hold_forward and allowed and net_id in held_state:
                _apply_combat(
                    fused,
                    net_id=net_id,
                    pid=pid,
                    combat=held_state[net_id],
                    source=HOLD_FORWARD_SOURCE,
                    seed_time_ms=None,
                )
                fused_participants += 1
                hold_participants += 1
                if net_id in known_by_net:
                    known_by_net[net_id] += 1
            else:
                frame_all = False
                unknown_forced += 1
                _clear_combat(fused)
            participants.append(fused)
        frame = dict(original)
        frame["participants"] = participants
        out.append(frame)
        fused_frames += 1
        if not frame_all:
            frames_partial += 1

    match_level_known = frames_partial == 0 and fused_participants > 0
    # Partial / hold policy: never emit match-level known while <10 FUR heroes.
    if (allow_partial or hold_forward) and heroes_known_count < 10:
        match_level_known = False
    combat_stats_known_would_emit = bool(
        heroes_known_count >= 10 and match_level_known
    )

    summary = {
        "ok": True,
        "combatStatsSource": COMBAT_STATS_SOURCE,
        "combatStatsKnown": match_level_known,
        "combatStatsKnownWouldEmit": combat_stats_known_would_emit,
        "combatTrusted": True,
        "partialEmit": bool(allow_partial),
        "holdForward": bool(hold_forward),
        "combatSource": HOLD_FORWARD_SOURCE if hold_forward else None,
        "alignMs": align_ms,
        "heroesKnownCount": heroes_known_count,
        "furCompleteNetIds": fur_net_ids,
        "knownParticipantHitsByNetId": {
            str(k): int(v) for k, v in sorted(known_by_net.items())
        },
        "fusedFrames": fused_frames,
        "fusedParticipants": fused_participants,
        "seedParticipants": seed_participants,
        "holdParticipants": hold_participants,
        "framesPartialCombat": frames_partial,
        "unavailableParticipantSlots": unknown_forced,
        "sampleCount": len(samples_sorted),
        "schema": combat_evidence.get("schema"),
        "identityBinding": "stable_identity_to_net_id",
        "calculatorReady": False,
        "path2WiringsStillNeeded": True,
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
    ap.add_argument(
        "--partial",
        action="store_true",
        help="Honest per-hero partial emit; match-level WouldEmit stays false <10/10",
    )
    ap.add_argument(
        "--hold-forward",
        action="store_true",
        help=(
            "Path1: after ≥1 PE FUR seed (±align-ms), hold floats/known per netId "
            "through continuous alive and post-respawn until next PE seed; "
            "dead frames stay unavailable; disclose combatSource=hold_forward"
        ),
    )
    ap.add_argument(
        "--align-ms",
        type=int,
        default=None,
        help=f"Nearest-sample alignment 0..{MAX_PRODUCT_TIME_TOLERANCE_MS} (product partial)",
    )
    args = ap.parse_args(argv)
    if not args.product:
        print("refusing non-product fuse (pass --product)", file=sys.stderr)
        return 2
    evidence = json.loads(args.combat_evidence.read_text(encoding="utf-8"))
    identity = json.loads(args.castspell_identity.read_text(encoding="utf-8"))
    rows = _load_jsonl(args.jsonl)
    try:
        out, summary = fuse_combat_product(
            rows,
            combat_evidence=evidence,
            castspell_identity=identity,
            align_ms=args.align_ms,
            allow_partial=bool(args.partial),
            hold_forward=bool(args.hold_forward),
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
