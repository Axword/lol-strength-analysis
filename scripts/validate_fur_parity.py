#!/usr/bin/env python3
"""
Validate a canonical rfc461 JSONL against the FUR product-parity checklist.

Does not require a League process. Generic mode checks FUR field parity.
``--strict-product`` instead fail-closes on trusted timed identity-bound HP
provenance; parity/calculator completeness remain separately reported.

Example:
  python3 scripts/validate_fur_parity.py \\
    --jsonl docs/rofl-research/fixtures/events_fur_parity.jsonl

  python3 scripts/validate_fur_parity.py \\
    --jsonl artifacts/rofl/3264361042/events.hp-trusted.rfc461.jsonl \\
    --strict-product
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CHECKLIST = ROOT / "docs/rofl-research/fur-parity-checklist.json"
TRUSTED_HEALTH_SOURCE = "rofl2_replication_decrypt_timed_identity_bound"


def _strict_trusted_hp_gate(rows: List[dict]) -> Dict[str, Any]:
    coverage = next(
        (row for row in rows if row.get("rfc461Schema") == "rofl_coverage"),
        None,
    )
    info = next(
        (row for row in rows if row.get("rfc461Schema") == "game_info"),
        None,
    )
    stats = [row for row in rows if row.get("rfc461Schema") == "stats_update"]
    errors: List[str] = []
    if not coverage or not info or not stats:
        errors.append("requires rofl_coverage, game_info, and stats_update")
        return {"ok": False, "errors": errors, "trustedParticipantRows": 0}
    provenance = coverage.get("provenance") or {}
    info_identities = set()
    for participant in info.get("participants") or []:
        puuid = str(participant.get("puuid") or "").strip()
        full_riot_id = str(participant.get("summonerName") or "").strip()
        if puuid:
            info_identities.add(f"puuid:{puuid}")
        elif full_riot_id and "#" in full_riot_id:
            info_identities.add(f"riotid:{full_riot_id.casefold()}")
    if len(info_identities) != 10:
        errors.append("canonical roster lacks ten stable participant identities")
    source_text = " ".join(
        str(value or "").casefold()
        for value in (
            coverage.get("source"),
            provenance.get("source"),
            provenance.get("sourceKind"),
            provenance.get("notes"),
        )
    )
    if any(
        provenance.get(key) is True
        for key in ("publicationBlocked", "researchOnly", "schemaProof")
    ):
        errors.append("fixture/schema-proof/research provenance is not product")
    for marker in (
        "fixture",
        "schema_proof",
        "schema-proof",
        "static",
        "research",
        "createhero",
        "create_hero",
        "synthetic",
    ):
        if marker in source_text:
            errors.append(f"non-product provenance marker {marker!r}")
            break
    required_provenance = {
        "hpEvidenceMode": "timed_identity_bound",
        "hpEvidenceSchema": "rofl-trusted-hp-v1",
        "hpEvidenceSource": TRUSTED_HEALTH_SOURCE,
        "hpEvidenceTimed": True,
        "hpStaticSnapshot": False,
        "hpFixtureEvidence": False,
        "hpCreateHeroOrderFallback": False,
        "hpIdentityBinding": "stable_identity_to_net_id",
        "hpTimeUnit": "milliseconds",
        "hpTimeClock": "replay_game_time",
    }
    for key, expected in required_provenance.items():
        if provenance.get(key) != expected:
            errors.append(f"{key} missing or invalid")
    try:
        tolerance = int(provenance.get("hpTimeToleranceMs"))
    except (TypeError, ValueError):
        tolerance = -1
    if not 0 <= tolerance <= 500:
        errors.append("timing tolerance missing or indefensible")
    sample_coverage = provenance.get("hpSampleCoverage") or {}
    if int(sample_coverage.get("sampleCount") or 0) < 2:
        errors.append("timed evidence requires at least two samples")
    if not provenance.get("hpRosterHash"):
        errors.append("roster hash is absent")

    trusted_rows = 0
    trusted_frames = 0
    for row in stats:
        frame_participants = row.get("participants") or []
        frame_trusted = [
            participant
            for participant in frame_participants
            if participant.get("healthSource") == TRUSTED_HEALTH_SOURCE
        ]
        frame_evidence = row.get("hpEvidence") or {}
        frame_net_ids = [participant.get("healthNetId") for participant in frame_trusted]
        frame_identities = [
            participant.get("healthIdentityKey") for participant in frame_trusted
        ]
        if frame_trusted and (
            len(frame_trusted) != len(frame_participants)
            or frame_evidence.get("source") != TRUSTED_HEALTH_SOURCE
            or frame_evidence.get("coverage") != "known_at_sampled_frame"
            or len(set(frame_net_ids)) != len(frame_trusted)
            or set(frame_identities) != info_identities
        ):
            errors.append("trusted HP frame coverage/source annotation is invalid")
        if frame_trusted:
            trusted_frames += 1
        if not frame_trusted and (
            frame_evidence.get("source") != TRUSTED_HEALTH_SOURCE
            or frame_evidence.get("coverage") != "unknown_no_aligned_sample"
        ):
            errors.append("unmatched HP frame lacks honest unknown annotation")
        for participant in row.get("participants") or []:
            source = participant.get("healthSource")
            if source == TRUSTED_HEALTH_SOURCE:
                trusted_rows += 1
                try:
                    hp = float(participant.get("health"))
                    hp_max = float(participant.get("healthMax"))
                    delta = int(participant.get("healthSampleDeltaMs"))
                    sample_time = int(participant.get("healthSampleGameTimeMs"))
                    net_id = int(participant.get("healthNetId"))
                except (TypeError, ValueError):
                    errors.append("trusted HP row has invalid values/timing/binding")
                    continue
                if (
                    not math.isfinite(hp)
                    or not math.isfinite(hp_max)
                    or hp < 0
                    or hp_max <= 100
                    or hp > hp_max
                    or delta < 0
                    or delta > tolerance
                    or sample_time < 0
                    or net_id <= 0
                    or participant.get("mMaxHPExplicit") is not True
                    or participant.get("healthMaxEvidence") != "explicit_mMaxHP"
                    or participant.get("healthIdentityBinding")
                    != "stable_identity_to_net_id"
                    or participant.get("healthIdentityKey") not in info_identities
                ):
                    errors.append(
                        "trusted HP row lacks explicit mMaxHP, replay time, or net-id binding"
                    )
            elif source in ("unavailable_replay_api", "unavailable", "unknown"):
                if "health" in participant or "healthMax" in participant:
                    errors.append("unknown HP row materializes health")
            else:
                errors.append(
                    f"untrusted/static/CreateHero-order health source {source!r}"
                )
    if trusted_rows == 0:
        errors.append("no trusted timed HP participant rows")
    if (
        int(sample_coverage.get("fusedParticipantRows", -1)) != trusted_rows
        or int(sample_coverage.get("fusedFrames", -1)) != trusted_frames
        or int(sample_coverage.get("sampleTimesUsed", -1)) != trusted_frames
    ):
        errors.append("trusted HP sample/frame summary is inconsistent")
    return {
        "ok": not errors,
        "errors": list(dict.fromkeys(errors)),
        "trustedParticipantRows": trusted_rows,
        "hpCoverage": provenance.get("hpCoverage"),
        "calculatorReady": False,
    }


def load_checklist(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> List[dict]:
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def evaluate(
    rows: List[dict],
    checklist: dict,
    *,
    strict_product: bool = False,
    timeline: Optional[dict] = None,
) -> Dict[str, Any]:
    schemas = Counter(r.get("rfc461Schema") for r in rows)
    required = list(checklist.get("requiredSchemas") or [])
    optional = list(checklist.get("optionalSchemas") or [])
    present_required = [s for s in required if schemas.get(s, 0) > 0]
    missing_required = [s for s in required if schemas.get(s, 0) == 0]
    present_optional = [s for s in optional if schemas.get(s, 0) > 0]

    field_req = list(checklist.get("requiredStatsUpdateParticipantFields") or [])
    stats = [r for r in rows if r.get("rfc461Schema") == "stats_update"]
    # Product fields land after Replication/SkillLevelUp packets. Score ticks
    # that already carry decoded HP + combat so early placeholders do not fail.
    scored_stats = []
    for row in stats:
        parts = row.get("participants") or []
        if parts and all(
            p.get("healthSource") == "replication_decoded"
            and p.get("attackDamage") is not None
            and p.get("totalGold") is not None
            for p in parts
        ):
            scored_stats.append(row)
    if not scored_stats and stats:
        scored_stats = [stats[-1]]
    field_coverage: Dict[str, float] = {}
    sample_missing: Dict[str, List[str]] = {}
    if scored_stats and field_req:
        ok_counts = {f: 0 for f in field_req}
        checked = 0
        for row in scored_stats:
            for p in row.get("participants") or []:
                checked += 1
                miss = []
                for f in field_req:
                    if f == "position":
                        pos = p.get("position") or {}
                        if "x" in pos and "z" in pos:
                            ok_counts[f] += 1
                        else:
                            miss.append(f)
                    elif f in p and p.get(f) is not None:
                        ok_counts[f] += 1
                    else:
                        miss.append(f)
                if miss and len(sample_missing) < 3:
                    sample_missing[str(p.get("participantID"))] = miss
        for f in field_req:
            field_coverage[f] = (ok_counts[f] / checked) if checked else 0.0

    epic_types = Counter()
    for r in rows:
        if r.get("rfc461Schema") == "epic_monster_kill":
            epic_types[str(r.get("monsterType") or "")] += 1

    voidgrub_kills = epic_types.get("VoidGrub", 0)
    product = {
        "voidGrubKills": voidgrub_kills,
        "hasDragonKill": any(
            t.lower() == "dragon" or t.startswith("dragon") for t in epic_types
        ),
        "hasBaronKill": "baron" in epic_types,
    }

    timeline_gates = None
    if timeline is not None:
        frames = timeline.get("frames") or []
        # Prefer a post-objectives frame when available (void grubs ~5:00+).
        mid = frames[len(frames) // 2] if frames else {}
        late = frames[-1] if frames else {}
        pick = late if late else mid
        for cand in (late, mid, *reversed(frames[-50:] if frames else [])):
            sc = cand.get("score") or cand.get("scoreboard") or {}
            blue = sc.get("blue") or {}
            red = sc.get("red") or {}
            if (blue.get("voidGrubs") or 0) > 0 or (red.get("voidGrubs") or 0) > 0:
                pick = cand
                break
        units = pick.get("units") or []
        score = pick.get("score") or pick.get("scoreboard") or {}
        gates = checklist.get("calculatorGates") or {}
        timeline_gates = {
            "frameCount": len(frames),
            "hpKnown": all(u.get("hpKnown") is not False for u in units) and bool(units),
            "combatStatsKnown": all(
                u.get("combatStatsKnown") is not False for u in units
            )
            and bool(units),
            "abilityRanksKnown": all(
                u.get("abilityRanksKnown") is not False for u in units
            )
            and bool(units),
            "voidGrubsBlue": (score.get("blue") or {}).get("voidGrubs"),
            "voidGrubsRed": (score.get("red") or {}).get("voidGrubs"),
            "required": gates,
        }

    fields_ok = bool(field_coverage) and all(v >= 0.99 for v in field_coverage.values())
    schemas_ok = not missing_required
    parity_ok = schemas_ok and (fields_ok if stats else False)
    product_ok = True
    trusted_hp_gate = None
    if strict_product:
        trusted_hp_gate = _strict_trusted_hp_gate(rows)
        product_ok = bool(trusted_hp_gate["ok"])
        if timeline_gates is not None:
            trusted_hp_gate["calculatorReady"] = bool(
                product_ok
                and timeline_gates["hpKnown"]
                and timeline_gates["combatStatsKnown"]
                and timeline_gates["abilityRanksKnown"]
            )

    return {
        "ok": product_ok if strict_product else parity_ok,
        "schemasOk": schemas_ok,
        "fieldsOk": fields_ok,
        "parityOk": parity_ok,
        "productOk": product_ok,
        "schemaCounts": dict(schemas),
        "presentRequiredSchemas": present_required,
        "missingRequiredSchemas": missing_required,
        "presentOptionalSchemas": present_optional,
        "fieldCoverage": field_coverage,
        "sampleMissingFields": sample_missing,
        "epicMonsterTypes": dict(epic_types),
        "product": product,
        "trustedHpGate": trusted_hp_gate,
        "timelineGates": timeline_gates,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--jsonl", type=Path, required=True)
    ap.add_argument("--checklist", type=Path, default=DEFAULT_CHECKLIST)
    ap.add_argument("--timeline", type=Path, default=None)
    ap.add_argument(
        "--strict-product",
        action="store_true",
        help=(
            "Require timed same-match identity-bound HP and reject fixture/static/"
            "CreateHero-order evidence; calculator readiness remains separate"
        ),
    )
    ap.add_argument("--json-out", type=Path, default=None)
    args = ap.parse_args()

    checklist = load_checklist(args.checklist)
    rows = load_jsonl(args.jsonl)
    timeline = None
    if args.timeline is not None:
        timeline = json.loads(args.timeline.read_text(encoding="utf-8"))

    report = evaluate(
        rows,
        checklist,
        strict_product=args.strict_product,
        timeline=timeline,
    )
    text = json.dumps(report, indent=2)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(text + "\n", encoding="utf-8")
        print(f"wrote {args.json_out}")
    else:
        print(text)

    print(
        f"ok={report['ok']} schemasOk={report['schemasOk']} "
        f"fieldsOk={report['fieldsOk']} productOk={report['productOk']} "
        f"missing={report['missingRequiredSchemas']}"
    )
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
