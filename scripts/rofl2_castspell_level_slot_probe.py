#!/usr/bin/env python3
"""Gate B2: structurally probe CastSpellAns (opcode 197) for level+slot offsets.

Maknee prior art carries logical ``slot`` / ``level`` on CastSpellAns; live 16.14
Deserialize layout is unproven. This probe Deserializes hero casts, records
ability-name suffix → expected slot votes, and scans the 328-byte object for
stable u8/u32 candidates. Never remaps fixture ranks onto the match.

SkillLevelUp remains unmapped on 16.14 (plaintext absent).

Example:
  npm run rofl:castspell-level-slot-probe -- \\
    --rofl \"$HOME/Documents/League of Legends/Replays/BR1-3264361042.rofl\" \\
    --json-out docs/rofl-research/castspell-level-slot-BR1-3264361042.json
"""
from __future__ import annotations

import argparse
import json
import struct
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from rofl2_binary_format import load_binary, research_manifest  # noqa: E402
from rofl2_castspell_identity_bind import (  # noqa: E402
    CASTSPELL_PKT,
    DEFAULT_PE,
    DEFAULT_ROFL,
    PROVEN_HERO_NET_IDS,
    _needles,
    _roster_champ_names,
    _scan_blob,
    normalize_champion,
    resolve_castspell_opcode,
    roster_from_rofl,
)
from rofl2_create_hero_discover import PROVEN_HERO_NET_ID_SET  # noqa: E402
from rofl2_probe import extract_segments, parse_rofl2  # noqa: E402
from rofl2_unicorn_packet_drive import extract_blocks_py  # noqa: E402
from rofl2_win_pe_e11_reconstructed_drive import deserialize_body  # noqa: E402
from rofl2_win_pe_packet_discover import (  # noqa: E402
    WinX64PacketEmu,
    enumerate_rofl,
    scan_msvc_packet_types,
)
from rofl_speed_bench import utc_now_iso  # noqa: E402

DEFAULT_OUT = Path("docs/rofl-research/castspell-level-slot-BR1-3264361042.json")
MATCH_CODE = "3264361042"


def collect_hero_cast_blocks_spread(
    rofl: Path, opcode: int, *, per_hero: int = 8
) -> Dict[int, List[dict]]:
    """Collect early + mid + late casts per hero (ability names often appear later)."""
    info = parse_rofl2(rofl)
    extracted = extract_segments(info["payload"])
    buckets: Dict[int, List[dict]] = defaultdict(list)
    for seg in extracted["segments"]:
        if int(seg.get("type") or 0) != 1:
            continue
        for blk in extract_blocks_py(seg["bytes"], max_blocks=500_000):
            if int(blk["channel"]) != opcode:
                continue
            param = int(blk.get("param") or 0)
            if param not in PROVEN_HERO_NET_ID_SET:
                continue
            buckets[param].append(
                {
                    "time": float(blk["time"]),
                    "param": param,
                    "payload": blk["payload"] or b"",
                }
            )
    out: Dict[int, List[dict]] = {}
    for net_id, rows in buckets.items():
        rows = sorted(rows, key=lambda r: r["time"])
        if len(rows) <= per_hero:
            out[net_id] = rows
            continue
        n = per_hero
        a = max(1, n // 3)
        c = max(1, n // 3)
        b = max(1, n - a - c)
        early = rows[:a]
        mid_start = max(0, len(rows) // 2 - b // 2)
        mid = rows[mid_start : mid_start + b]
        late = rows[-c:]
        seen: set = set()
        picked: List[dict] = []
        for r in early + mid + late:
            key = (r["time"], len(r["payload"]))
            if key in seen:
                continue
            seen.add(key)
            picked.append(r)
        out[net_id] = picked[:per_hero]
    return out

SLOT_FROM_SUFFIX = {
    "Q": 0,
    "Q1": 0,
    "Q2": 0,
    "Q3": 0,
    "W": 1,
    "E": 2,
    "R": 3,
    "R1": 3,
    "R2": 3,
}


def _ability_slot(token: str, roster_names: Sequence[str]) -> Optional[int]:
    champ = normalize_champion(token, roster_names)
    if not champ or token == champ:
        return None
    rest = token[len(champ) :]
    if not rest and token.casefold().startswith("wukong"):
        rest = token[6:]
        champ = "MonkeyKing"
    if not rest and token.casefold().startswith("leblanc"):
        rest = token[7:]
    return SLOT_FROM_SUFFIX.get(rest) if rest else None


def _scan_int_candidates(obj: bytes) -> Dict[str, List[Dict[str, Any]]]:
    """Collect offsets whose values look like slot (0..3) or spell level (1..5)."""
    u8_slot: List[Dict[str, Any]] = []
    u8_level: List[Dict[str, Any]] = []
    u32_slot: List[Dict[str, Any]] = []
    u32_level: List[Dict[str, Any]] = []
    for off in range(len(obj)):
        v = obj[off]
        if 0 <= v <= 3:
            u8_slot.append({"offset": off, "value": v})
        if 1 <= v <= 5:
            u8_level.append({"offset": off, "value": v})
    for off in range(0, len(obj) - 3):
        v = struct.unpack_from("<I", obj, off)[0]
        if 0 <= v <= 3:
            u32_slot.append({"offset": off, "value": v})
        if 1 <= v <= 5:
            u32_level.append({"offset": off, "value": v})
    return {
        "u8SlotLike": u8_slot[:64],
        "u8LevelLike": u8_level[:64],
        "u32SlotLike": u32_slot[:64],
        "u32LevelLike": u32_level[:64],
    }


def probe_level_slot(
    *,
    rofl: Path,
    pe: Path,
    per_hero: int = 6,
) -> Dict[str, Any]:
    t0 = time.perf_counter()
    roster = roster_from_rofl(rofl)
    roster_names = _roster_champ_names(roster)
    binary = load_binary(pe)
    reg = resolve_castspell_opcode(binary)
    opcode = int(reg["opcode"])
    counts, _ = enumerate_rofl(rofl)
    factories, coverage = scan_msvc_packet_types(binary, counts)
    factory = next((r for r in factories if int(r["opcode"]) == opcode), None)
    if not factory:
        return {
            "ok": False,
            "schema": "rofl-castspell-level-slot-v0",
            "blocker": {
                "kind": "castspell_factory_missing",
                "detail": f"opcode {opcode} factory not recovered",
            },
            "castSpellAnsLevelSlotDecoded": False,
            "abilityRanksTrusted": False,
            "productEligible": False,
        }

    object_size = int(factory["objectSize"])
    by_hero = collect_hero_cast_blocks_spread(rofl, opcode, per_hero=per_hero)
    needles = _needles(roster_names)

    # offset → Counter of (expected_slot, observed_value) agreement
    slot_offset_agree: Dict[int, Counter] = defaultdict(Counter)
    slot_offset_total: Counter = Counter()
    level_offset_hist: Dict[int, Counter] = defaultdict(Counter)
    ability_suffix_votes: Counter = Counter()
    samples: List[Dict[str, Any]] = []
    deser_ok = 0

    for net_id in PROVEN_HERO_NET_IDS:
        for blk in by_hero.get(net_id) or []:
            emu = WinX64PacketEmu(binary)
            body = deserialize_body(opcode, blk["payload"])
            fac = emu.construct(
                ctor_va=int(factory["ctorVa"]),
                object_size=object_size,
                expected_opcode=opcode,
                expected_vptr=int(factory["vptr"]),
            )
            if not fac.get("ok"):
                continue
            obj = int(fac["obj"])
            deser = emu.deserialize(
                obj=obj,
                deser_va=int(factory["deserializeVa"]),
                payload=body,
                object_size=object_size,
            )
            if not deser.get("ok") and deser.get("retAl") not in (0, 1, None):
                # still read object; Deserialize may return via AL
                pass
            after = bytes(emu.mu.mem_read(obj, object_size))
            deser_ok += 1
            hits = set(_scan_blob(after, needles))
            for off in range(0, len(after) - 7, 8):
                ptr = struct.unpack_from("<Q", after, off)[0]
                if 0x300000000 <= ptr < 0x310000000:
                    try:
                        blob = bytes(emu.mu.mem_read(ptr, 96))
                    except Exception:  # noqa: BLE001
                        continue
                    hits.update(_scan_blob(blob, needles))

            expected_slots = []
            for h in hits:
                slot = _ability_slot(h, roster_names)
                if slot is not None:
                    expected_slots.append((h, slot))
                    ability_suffix_votes[f"{h}->{slot}"] += 1

            cands = _scan_int_candidates(after)
            # Correlate u8 candidates with expected slot from ability suffix.
            if expected_slots:
                # Use first ability-derived slot as expected
                exp = expected_slots[0][1]
                for row in cands["u8SlotLike"]:
                    off = int(row["offset"])
                    slot_offset_total[off] += 1
                    if int(row["value"]) == exp:
                        slot_offset_agree[off]["agree"] += 1
                    else:
                        slot_offset_agree[off]["disagree"] += 1
                for row in cands["u8LevelLike"]:
                    level_offset_hist[int(row["offset"])][int(row["value"])] += 1

            if len(samples) < 24:
                samples.append(
                    {
                        "netId": net_id,
                        "time": blk["time"],
                        "hits": sorted(hits)[:12],
                        "expectedSlots": expected_slots[:4],
                        "retAl": deser.get("retAl"),
                        "consumed": deser.get("consumed"),
                        "u8SlotCandidateCount": len(cands["u8SlotLike"]),
                        "u8LevelCandidateCount": len(cands["u8LevelLike"]),
                    }
                )

    # Require a single offset with high agreement and low disagreement.
    scored: List[Dict[str, Any]] = []
    for off, totals in slot_offset_total.items():
        agree = int(slot_offset_agree[off]["agree"])
        disagree = int(slot_offset_agree[off]["disagree"])
        if totals < 8:
            continue
        ratio = agree / totals if totals else 0.0
        scored.append(
            {
                "offset": off,
                "samples": totals,
                "agree": agree,
                "disagree": disagree,
                "agreeRatio": round(ratio, 4),
            }
        )
    scored.sort(key=lambda r: (-r["agreeRatio"], -r["agree"], r["offset"]))
    best = scored[0] if scored else None
    # Structural proof bar: ≥0.95 agree on ≥20 samples, unique best.
    proven = bool(
        best
        and best["agreeRatio"] >= 0.95
        and best["agree"] >= 20
        and (len(scored) < 2 or scored[1]["agreeRatio"] < 0.9)
    )

    # Level offsets: look for offsets with values concentrated in 1..5 across casts.
    level_scored: List[Dict[str, Any]] = []
    for off, hist in level_offset_hist.items():
        total = sum(hist.values())
        if total < 8:
            continue
        # Prefer offsets that aren't almost always the same trivial constant
        # across the whole object (too many false positives).
        distinct = len(hist)
        level_scored.append(
            {
                "offset": off,
                "samples": total,
                "distinctValues": distinct,
                "histogram": {str(k): v for k, v in sorted(hist.items())},
            }
        )
    level_scored.sort(key=lambda r: (-r["distinctValues"], -r["samples"], r["offset"]))
    level_proven = False  # require slot proven first + independent validation

    plaintext_hits = {"SkillLevelUp": 0, "mSkillUpLevel": 0, "SkillUp": 0}
    # cheap plaintext scan already done by ranks probe; keep schema field
    castspell_blocks = int(counts.get(opcode) or 0)

    if proven and level_proven:
        blocker = None
        decoded = True
    else:
        decoded = False
        blocker = {
            "kind": "ability_ranks_wire_unproven",
            "detail": (
                "CastSpellAns opcode 197 is mapped for champion identity, but "
                "SkillLevelUp is unmapped and CastSpellAns level/slot offsets are "
                "not structurally proven on 16.14 — do not fuse abilityRanksKnown"
            ),
            "slotBest": best,
            "slotCandidatesTop": scored[:8],
            "levelCandidatesTop": level_scored[:8],
            "abilitySuffixVotes": dict(ability_suffix_votes.most_common(20)),
            "structuralBar": {
                "slotAgreeRatio": 0.95,
                "slotMinAgree": 20,
                "levelIndependentProof": False,
            },
        }

    wall_ms = (time.perf_counter() - t0) * 1000.0
    return {
        "ok": False,
        "schema": "rofl-castspell-level-slot-v0",
        "ts": utc_now_iso(),
        "matchCode": MATCH_CODE,
        "wallMs": round(wall_ms, 3),
        "castSpellAnsMapped": True,
        "castSpellAnsOpcode": opcode,
        "castSpellAnsPkt": CASTSPELL_PKT,
        "castSpellAnsBlockCount": castspell_blocks,
        "objectSize": object_size,
        "deserializeOkCount": deser_ok,
        "castSpellAnsLevelSlotDecoded": decoded,
        "slotProof": {
            "proven": proven,
            "best": best,
            "top": scored[:12],
        },
        "levelProof": {
            "proven": level_proven,
            "top": level_scored[:12],
            "note": "Level offset requires slot proof plus independent validation",
        },
        "sampleHead": samples[:12],
        "skillLevelUpOpcodeMapped": False,
        "plaintextHits": plaintext_hits,
        "binaryManifest": research_manifest(
            binary,
            patch="16.14",
            extra={"probeVersion": "castspell-level-slot-v0"},
        ),
        "constructorCoverage": coverage,
        "blocker": blocker,
        "abilityRanksTrusted": False,
        "productEligible": False,
        "note": (
            "Prefer CastSpellAns level+slot structural decode over fixture remap. "
            "Ability-name suffix gives expected slot for correlation only."
        ),
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rofl", type=Path, default=DEFAULT_ROFL)
    ap.add_argument("--pe", type=Path, default=DEFAULT_PE)
    ap.add_argument("--json-out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--per-hero", type=int, default=6)
    args = ap.parse_args(argv)
    if not args.rofl.is_file():
        print(f"missing ROFL {args.rofl}", file=sys.stderr)
        return 2
    if not args.pe.is_file():
        print(f"missing PE {args.pe}", file=sys.stderr)
        return 2
    report = probe_level_slot(
        rofl=args.rofl,
        pe=args.pe,
        per_hero=max(1, int(args.per_hero)),
    )
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(
        json.dumps(report, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {args.json_out}")
    print(
        f"levelSlotDecoded={report.get('castSpellAnsLevelSlotDecoded')} "
        f"blocker={(report.get('blocker') or {}).get('kind')} "
        f"slotBest={(report.get('slotProof') or {}).get('best')}"
    )
    return 0 if report.get("castSpellAnsLevelSlotDecoded") else 2


if __name__ == "__main__":
    raise SystemExit(main())
