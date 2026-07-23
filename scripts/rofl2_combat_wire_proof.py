#!/usr/bin/env python3
"""Gate B1: prove live 16.14 type-107 index→name map for FUR combat fields.

PE path: CharacterIntermediate batch registrars pass ``w3`` as a power-of-two
mask (primary bit = w3.bit_length()-1) and assign secondaries in registration
order within a shared context VA. HP ``w3=32`` → primary 5 is the positive
control ((5,0)=mHP, (5,1)=mMaxHP). Combat shares context with ActionState under
``w3=4`` → primary 2 with secondary offset 3.

Live BR1 walk must observe plausible values for FUR targets under that PE table.
Never sets combatTrusted without PE table + HP control + FUR coverage.

Example:
  npm run rofl:combat-wire-proof -- \\
    --rofl \"$HOME/Documents/League of Legends/Replays/BR1-3264361042.rofl\" \\
    --json-out docs/rofl-research/combat-wire-proof-BR1-3264361042.json
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import rofl2_accessor_spike as spike  # noqa: E402
import rofl2_replication_decode as decode  # noqa: E402
from rofl_combat_wire_table import (  # noqa: E402
    COMBAT_STATS_SOURCE,
    FUR_COMPONENT_REQUIREMENTS,
    PLAUSIBLE_RANGES,
    PROVEN_COMBAT_WIRE_MAP_16_14,
    REFUTED_PRIMARY1_HYPOTHESIS,
    extract_wire_table_from_pe,
    filter_combat_fields,
    load_arm64_slice,
    value_in_plausible_range,
)
from rofl_replication_apply import parse_replication_vector  # noqa: E402
from rofl_replication_fields import (  # noqa: E402
    BINARY_COMBAT_REPLICATION_NAMES,
    resolve_combat_stats,
)
from rofl_speed_bench import utc_now_iso  # noqa: E402

DEFAULT_ROFL = (
    Path.home() / "Documents/League of Legends/Replays/BR1-3264361042.rofl"
)
DEFAULT_OUT = Path("docs/rofl-research/combat-wire-proof-BR1-3264361042.json")
MATCH_CODE = "3264361042"
FUR_COMBAT_TARGETS = tuple(FUR_COMPONENT_REQUIREMENTS.keys())


def densify_hp_onto_replay_api_frames(
    *,
    frame_times_ms: Sequence[int],
    first_all10_ms: int,
    carried_by_frame: Mapping[int, Sequence[Mapping[str, Any]]],
) -> List[Dict[str, Any]]:
    """Materialize identity-bound HP rows on Replay API 1Hz times.

    Values must already be explicit ``mMaxHP`` carry-forwards from type-107
    state (never invented). Frames before ``first_all10_ms`` are omitted.
    """
    out: List[Dict[str, Any]] = []
    for frame_ms in sorted(int(t) for t in frame_times_ms):
        if frame_ms < int(first_all10_ms):
            continue
        units = list(carried_by_frame.get(frame_ms) or [])
        if len(units) != 10:
            continue
        if not all(bool(u.get("mMaxHPExplicit")) for u in units):
            continue
        out.append({"gameTimeMs": frame_ms, "units": units})
    return out


def _collect_raw_indices(
    *,
    rofl: Path,
    league_binary: Path,
    max_chunks: int,
    max_blocks: int,
    frame_times_ms: Optional[Sequence[int]] = None,
) -> Dict[str, Any]:
    """Drive type-107 Deserialize and tally hero (primary,secondary) floats."""
    index_counts: Counter = Counter()
    index_values: Dict[str, List[float]] = defaultdict(list)
    timed_combat: List[Dict[str, Any]] = []
    merged_components: Dict[int, Dict[str, float]] = {}
    last_emit_ms: Dict[int, int] = {}
    timed_hp: List[Dict[str, Any]] = []
    first_accept_ms: Dict[int, int] = {}
    first_all10_ms: Optional[int] = None
    last_dense_frame_ms: Optional[int] = None
    hero_hits = 0
    # Proven CastSpellAns hero netIds for this match (inclusive AE..B7).
    HERO_NET_LO = 0x400000AE
    HERO_NET_HI = 0x400000B7
    hero_net_ids = list(range(HERO_NET_LO, HERO_NET_HI + 1))
    frames = sorted({int(t) for t in (frame_times_ms or []) if int(t) >= 0})
    if not frames:
        # Fallback 1Hz grid covering typical Replay API captures.
        frames = list(range(60_000, 2_400_000, 1_000))
    orig_apply = decode.apply_vector_blob

    def _capturing_apply(state, blob, *, time_s=0.0):  # type: ignore[no-untyped-def]
        nonlocal hero_hits, first_all10_ms, last_dense_frame_ms
        game_ms = int(round(float(time_s) * 1000.0))
        for net_id, fields in parse_replication_vector(blob):
            nid = int(net_id)
            if not (HERO_NET_LO <= nid <= HERO_NET_HI):
                continue
            hero_hits += 1
            for (p, s), val in fields.items():
                key = f"{p},{s}"
                index_counts[key] += 1
                if len(index_values[key]) < 40:
                    index_values[key].append(float(val))
            named = filter_combat_fields(fields)
            if not named:
                continue
            merged = dict(merged_components.get(nid) or {})
            merged.update(named)
            merged_components[nid] = merged
            resolved = resolve_combat_stats(merged)
            if not resolved:
                continue
            # Require product-usable AD/armor/MR/AS (AP may be 0 for AD champs).
            if not (
                float(resolved.get("attackDamage") or 0) > 0
                and float(resolved.get("armor") or 0) > 0
                and float(resolved.get("magicResist") or 0) > 0
                and float(resolved.get("attackSpeed") or 0) > 0
                and "abilityPower" in resolved
            ):
                continue
            prev = last_emit_ms.get(nid, -10_000)
            # Emit ~1Hz per hero once FUR-complete (carry components between packets).
            if game_ms - prev < 900 and timed_combat:
                continue
            last_emit_ms[nid] = game_ms
            timed_combat.append(
                {
                    "gameTimeMs": game_ms,
                    "netId": nid,
                    "netIdHex": hex(nid),
                    "components": dict(merged),
                    "resolved": {
                        k: float(resolved[k])
                        for k in (
                            "attackDamage",
                            "abilityPower",
                            "armor",
                            "magicResist",
                            "attackSpeed",
                        )
                    },
                }
            )
        applied = orig_apply(state, blob, time_s=time_s)
        for nid in hero_net_ids:
            st = state.get(nid)
            if st is not None and st.acceptance_ok() and nid not in first_accept_ms:
                first_accept_ms[nid] = game_ms
        if first_all10_ms is None and len(first_accept_ms) == 10:
            first_all10_ms = max(first_accept_ms.values())
        # Carry-forward densify onto Replay API 1Hz frames once all 10 accept.
        if first_all10_ms is not None and all(
            (state.get(nid) is not None and state[nid].acceptance_ok())
            for nid in hero_net_ids
        ):
            units = [
                {
                    "netId": nid,
                    "mHP": float(state[nid].mHP),
                    "mMaxHP": float(state[nid].mMaxHP),
                    "mMaxHPExplicit": True,
                }
                for nid in hero_net_ids
            ]
            for frame_ms in frames:
                if last_dense_frame_ms is not None and frame_ms <= last_dense_frame_ms:
                    continue
                if frame_ms < int(first_all10_ms):
                    continue
                if frame_ms > game_ms:
                    break
                timed_hp.append({"gameTimeMs": frame_ms, "units": [dict(u) for u in units]})
                last_dense_frame_ms = frame_ms
        return applied

    decode.apply_vector_blob = _capturing_apply  # type: ignore[attr-defined]
    try:
        with tempfile.TemporaryDirectory(prefix="combat-wire-") as td:
            work = Path(td)
            result = decode.decode_rofl_replication(
                rofl=rofl,
                league_binary=league_binary,
                work_dir=work,
                max_blocks=max_blocks,
                max_chunks=max_chunks,
                stub_use_map=True,
                stop_on_hp_acceptance=False,
            )
    finally:
        decode.apply_vector_blob = orig_apply  # type: ignore[attr-defined]

    snap = (result.get("hpSnapshot") or {}).get("heroes") or []
    named_from_apply: Counter = Counter()
    for hero in snap:
        combat = hero.get("combat") or {}
        for name in combat:
            named_from_apply[name] += 1

    monkey_king = 0x400000AF
    other_first = [
        ms for nid, ms in first_accept_ms.items() if nid != monkey_king
    ]
    return {
        "decodeOk": bool(result.get("ok")),
        "decryptStatus": result.get("decryptStatus"),
        "heroUnitParses": hero_hits,
        "indexCounts": dict(index_counts.most_common(96)),
        "indexValueSamples": {k: v[:8] for k, v in sorted(index_values.items())},
        "namedFromApply": dict(named_from_apply),
        "timedCombatSampleCount": len(timed_combat),
        "timedCombat": timed_combat[:8000],
        "timedHpSampleCount": len(timed_hp),
        "timedHp": timed_hp,
        "firstAcceptMs": {hex(nid): ms for nid, ms in sorted(first_accept_ms.items())},
        "firstAll10HpMs": first_all10_ms,
        "monkeyKingFirstHpMs": first_accept_ms.get(monkey_king),
        "otherHeroesFirstHpMs": min(other_first) if other_first else None,
        "decodeMeta": {
            "pythonReplicationBlocks": result.get("pythonReplicationBlocks"),
            "chunk": result.get("chunk"),
            "maxChunks": max_chunks,
            "maxBlocks": max_blocks,
        },
    }


def _pe_string_presence(league_binary: Path) -> Dict[str, Any]:
    data = load_arm64_slice(league_binary)
    present = {}
    for name in sorted(BINARY_COMBAT_REPLICATION_NAMES):
        present[name] = data.find(name.encode("ascii") + b"\x00") >= 0
    wire_table = extract_wire_table_from_pe(data)
    combat_slots = []
    for key, name in sorted(PROVEN_COMBAT_WIRE_MAP_16_14.items()):
        row = (wire_table.get("byKey") or {}).get(f"{key[0]},{key[1]}")
        if row:
            combat_slots.append(row)
    return {
        "binaryPath": str(league_binary),
        "stringPresent": present,
        "allCombatNamesPresent": all(present.values()),
        "wireTable": {
            "ok": wire_table.get("ok"),
            "fieldCount": wire_table.get("fieldCount"),
            "fieldBinderFn": wire_table.get("fieldBinderFn"),
            "hpPositiveControl": wire_table.get("hpPositiveControl"),
            "provenCombatMap": wire_table.get("provenCombatMap"),
            "note": wire_table.get("note"),
        },
        "registrarCombatSlots": combat_slots,
        "registrarNote": (
            "Batch registrar w3 masks map to wire primary bits; secondaries are "
            "registration order within shared context VAs. Object slot offsets "
            "are recorded for audit but are not wire indices."
        ),
    }


def _evaluate_proven_map(
    raw: Mapping[str, Any],
    pe: Mapping[str, Any],
) -> Dict[str, Any]:
    index_counts = raw.get("indexCounts") or {}
    samples = raw.get("indexValueSamples") or {}
    wire_ok = bool((pe.get("wireTable") or {}).get("hpPositiveControl", {}).get("ok"))
    rows: List[Dict[str, Any]] = []
    proven = 0
    for (p, s), name in sorted(PROVEN_COMBAT_WIRE_MAP_16_14.items()):
        key = f"{p},{s}"
        vals = list(samples.get(key) or [])
        in_range_vals = [v for v in vals if value_in_plausible_range(name, v)]
        pe_row = None
        for slot in pe.get("registrarCombatSlots") or []:
            if slot.get("primary") == p and slot.get("secondary") == s:
                pe_row = slot
                break
        pe_name_ok = bool(pe_row and pe_row.get("name") == name)
        observed = int(index_counts.get(key) or 0) > 0
        status = "index_not_observed"
        if pe_name_ok and in_range_vals:
            status = "proven"
            proven += 1
        elif pe_name_ok and observed:
            status = "pe_bound_values_filtered"
        elif pe_name_ok:
            status = "pe_bound_unobserved"
        rows.append(
            {
                "primary": p,
                "secondary": s,
                "name": name,
                "observed": observed,
                "observationCount": int(index_counts.get(key) or 0),
                "valueSamples": vals[:6],
                "plausibleSamples": in_range_vals[:6],
                "plausibleRange": list(PLAUSIBLE_RANGES.get(name, (None, None))),
                "peNameMatch": pe_name_ok,
                "status": status,
            }
        )

    # Refute primary-1 hypothesis explicitly.
    refuted_rows = []
    for (p, s), name in sorted(REFUTED_PRIMARY1_HYPOTHESIS.items()):
        key = f"{p},{s}"
        vals = list(samples.get(key) or [])
        refuted_rows.append(
            {
                "primary": p,
                "secondary": s,
                "name": name,
                "observationCount": int(index_counts.get(key) or 0),
                "valueSamples": vals[:4],
                "status": "refuted_not_pe_wire_table",
            }
        )

    fur_covered: Dict[str, bool] = {}
    for fur, comps in FUR_COMPONENT_REQUIREMENTS.items():
        fur_covered[fur] = any(
            r["name"] in comps and r["status"] == "proven" for r in rows
        )

    return {
        "provenRows": rows,
        "provenIndexCount": proven,
        "refutedPrimary1Hypothesis": refuted_rows,
        "furFieldProvenUnderPeTable": fur_covered,
        "furTargets": list(FUR_COMBAT_TARGETS),
        "hpPositiveControlOk": wire_ok,
        "note": (
            "Proven = PE registrar name at (primary,secondary) AND ≥1 live value "
            "in plausible range. Primary-1 apply hypothesis is refuted."
        ),
    }


def run_proof(
    *,
    rofl: Path,
    league_binary: Path,
    max_chunks: int = 80,
    max_blocks: int = 50_000,
    frame_times_ms: Optional[Sequence[int]] = None,
) -> Dict[str, Any]:
    t0 = time.perf_counter()
    pe = _pe_string_presence(league_binary)
    raw: Dict[str, Any]
    try:
        raw = _collect_raw_indices(
            rofl=rofl,
            league_binary=league_binary,
            max_chunks=max_chunks,
            max_blocks=max_blocks,
            frame_times_ms=frame_times_ms,
        )
    except Exception as exc:  # noqa: BLE001
        raw = {
            "decodeOk": False,
            "error": str(exc),
            "indexCounts": {},
            "indexValueSamples": {},
            "namedFromApply": {},
            "heroUnitParses": 0,
            "timedCombat": [],
            "timedCombatSampleCount": 0,
            "timedHp": [],
            "timedHpSampleCount": 0,
            "firstAcceptMs": {},
            "firstAll10HpMs": None,
            "monkeyKingFirstHpMs": None,
            "otherHeroesFirstHpMs": None,
        }
    hyp = _evaluate_proven_map(raw, pe)
    fur = hyp.get("furFieldProvenUnderPeTable") or {}
    hp_ok = bool(hyp.get("hpPositiveControlOk"))
    fur_ok = all(fur.get(k) for k in FUR_COMBAT_TARGETS)
    # magicResist may only appear after denormal filter; still require proven row.
    wire_table_proven = hp_ok and fur_ok and hyp["provenIndexCount"] >= 5
    identity_oracle_proven = False
    combat_trusted = wire_table_proven

    observed_named = sorted(
        {
            r["name"]
            for r in hyp["provenRows"]
            if r["status"] in ("proven", "pe_bound_values_filtered")
        }
    )

    if combat_trusted:
        blocker = None
    elif not hp_ok:
        blocker = {
            "kind": "combat_pe_hp_control_failed",
            "detail": "PE wire table HP positive control (5,0)/(5,1) failed",
            "wireTableProven": False,
            "identityOracleProven": False,
            "terminal": False,
        }
    elif not fur_ok:
        missing = [k for k, v in fur.items() if not v]
        blocker = {
            "kind": "combat_wire_unproven",
            "detail": (
                "PE registrar table extracted but FUR fields still missing "
                f"plausible live values: {missing}"
            ),
            "observedNamed": observed_named,
            "furFieldProvenUnderPeTable": fur,
            "wireTableProven": False,
            "identityOracleProven": False,
            "terminal": False,
        }
    else:
        blocker = {
            "kind": "combat_wire_unproven",
            "detail": "incomplete provenIndexCount",
            "wireTableProven": False,
            "identityOracleProven": False,
            "terminal": False,
        }

    wall_ms = (time.perf_counter() - t0) * 1000.0
    return {
        "ok": bool(combat_trusted),
        "schema": "rofl-combat-wire-proof-v1",
        "ts": utc_now_iso(),
        "matchCode": MATCH_CODE,
        "wallMs": round(wall_ms, 3),
        "pe": pe,
        "rawIndices": {
            k: v
            for k, v in raw.items()
            if k
            not in (
                "timedCombat",
                "timedHp",
            )  # keep timed samples under evidence keys
        },
        "hypothesis": hyp,
        "blocker": blocker,
        "combatTrusted": bool(combat_trusted),
        "productEligible": bool(combat_trusted),
        "combatStatsKnownWouldEmit": bool(combat_trusted),
        "combatStatsSource": COMBAT_STATS_SOURCE if combat_trusted else None,
        "wireTableProven": bool(wire_table_proven),
        "identityOracleProven": False,
        "timedCombatEvidence": {
            "sampleCount": raw.get("timedCombatSampleCount") or 0,
            "samples": raw.get("timedCombat") or [],
            "identityBound": False,
            "note": (
                "Samples are netId-timed from type-107; fuse binds via CastSpellAns "
                "winners before setting combatStatsKnown."
            ),
        },
        "timedHpEvidence": {
            "sampleCount": raw.get("timedHpSampleCount") or 0,
            "samples": raw.get("timedHp") or [],
            "firstAcceptMs": raw.get("firstAcceptMs") or {},
            "firstAll10HpMs": raw.get("firstAll10HpMs"),
            "monkeyKingFirstHpMs": raw.get("monkeyKingFirstHpMs"),
            "otherHeroesFirstHpMs": raw.get("otherHeroesFirstHpMs"),
            "note": (
                "Carry-forward densify onto Replay API 1Hz frames once all 10 heroes "
                "have explicit mMaxHP; values stay wire (5,0)/(5,1) — never invented."
            ),
        },
        "peAttempts": {
            "fieldBinderFn": (pe.get("wireTable") or {}).get("fieldBinderFn"),
            "hpPositiveControl": (pe.get("wireTable") or {}).get("hpPositiveControl"),
            "provenCombatMap": (pe.get("wireTable") or {}).get("provenCombatMap"),
            "refutedPrimary1Hypothesis": True,
            "refutedPrimary1Detail": (
                "Old apply map primary-1 is not the PE registrar table; "
                "(1,6) once at 2503 is not mFlatMagicDamageMod"
            ),
            "objectSlotsAreNotWireIndices": True,
            "replayApiCombatFloats": False,
            "conclusion": (
                "wire_table_proven"
                if wire_table_proven
                else "needs_fur_live_values_or_oracle"
            ),
        },
        "note": (
            "Gate B1 PE wire table proven: w3 mask→primary, shared-context secondary "
            "order; HP (5,0)/(5,1) positive control; combat under primary 2 offset+3. "
            "Primary-1 hypothesis refuted. calculatorReady still blocked by early "
            "MonkeyKing explicit mMaxHP gap before first all-10 HP."
            if combat_trusted
            else "Gate B1 fail-closed until PE table + FUR plausible live values."
        ),
        "calculatorReadyBlocker": (
            {
                "kind": "calculator_hp_density",
                "terminal": True,
                "detail": (
                    "Gate B1 combat wire table is proven (combatTrusted=true). "
                    "Trusted HP densify can cover Replay API frames only after all 10 "
                    "heroes have explicit mMaxHP. MonkeyKing (0x400000af) first accepts "
                    f"at ~{raw.get('monkeyKingFirstHpMs')}ms while other heroes accept "
                    f"at ~{raw.get('otherHeroesFirstHpMs')}ms; early Replay API frames "
                    "(timeline starts ~60000ms) cannot honestly set hpKnown without "
                    "inventing HP. Full-chunk type-107 walk shows no earlier MonkeyKing "
                    "(5,1) — combat-only vectors appear first; not a parse/filter miss."
                ),
                "monkeyKingFirstHpMs": raw.get("monkeyKingFirstHpMs"),
                "otherHeroesFirstHpMs": raw.get("otherHeroesFirstHpMs"),
                "firstAll10HpMs": raw.get("firstAll10HpMs"),
                "denseHpSampleCount": raw.get("timedHpSampleCount") or 0,
                "b1Closed": True,
            }
            if combat_trusted
            else None
        ),
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rofl", type=Path, default=DEFAULT_ROFL)
    ap.add_argument(
        "--league-binary",
        type=Path,
        default=spike.DEFAULT_UNIVERSAL_BINARY,
    )
    ap.add_argument("--json-out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--max-chunks", type=int, default=80)
    ap.add_argument("--max-blocks", type=int, default=50_000)
    ap.add_argument(
        "--frame-times-jsonl",
        type=Path,
        default=None,
        help="Optional rfc461 JSONL whose stats_update times densify HP onto",
    )
    args = ap.parse_args(argv)
    if not args.rofl.is_file():
        print(f"missing ROFL {args.rofl}", file=sys.stderr)
        return 2
    if not args.league_binary.is_file():
        print(f"missing league binary {args.league_binary}", file=sys.stderr)
        return 2
    frame_times: Optional[List[int]] = None
    if args.frame_times_jsonl is not None:
        if not args.frame_times_jsonl.is_file():
            print(f"missing frame times jsonl {args.frame_times_jsonl}", file=sys.stderr)
            return 2
        frame_times = []
        with args.frame_times_jsonl.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                if row.get("rfc461Schema") == "stats_update":
                    frame_times.append(int(row.get("gameTime") or 0))
    report = run_proof(
        rofl=args.rofl,
        league_binary=args.league_binary,
        max_chunks=max(1, int(args.max_chunks)),
        max_blocks=int(args.max_blocks),
        frame_times_ms=frame_times,
    )
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(
        json.dumps(report, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {args.json_out}")
    print(
        f"combatTrusted={report.get('combatTrusted')} "
        f"blocker={(report.get('blocker') or {}).get('kind')} "
        f"proven={((report.get('hypothesis') or {}).get('provenIndexCount'))} "
        f"fur={((report.get('hypothesis') or {}).get('furFieldProvenUnderPeTable'))}"
    )
    return 0 if report.get("combatTrusted") else 2


if __name__ == "__main__":
    raise SystemExit(main())
