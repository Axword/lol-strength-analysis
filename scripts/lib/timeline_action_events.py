#!/usr/bin/env python3
"""
P4 T1 — Product timeline AA/damage extract (identity-bound only).

Copies rfc461 `basic_attack` / `damage_dealt` rows into GameTimeline event
arrays. Never invents from HPΔ / skill_used echo. Never assigns participantId
from sorted-netId / CreateHero order.

Accept paths (any one):
1. Explicit netId → participantId map (PUUID / full Riot ID join artifact)
2. Row already carries netId + participantID with a proven participantIdSource

Reject:
- participantID without netId (order-only)
- netId with no identity resolution
- inventing amount from HP curves
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Tuple

PRODUCT_PID_SOURCES = frozenset(
    {
        "puuid_join",
        "full_riot_id_join",
        "identity_bind",
        "stable_identity",
        "stable_identity_to_net_id",
    }
)

ORDER_ONLY_PID_SOURCES = frozenset(
    {
        "create_hero_order",
        "createHeroOrder",
        "sorted_netid",
        "sorted_net_id",
        "participant_order",
        "ae_b7_order",
    }
)


def _finite_int(value: Any) -> Optional[int]:
    try:
        if value is None:
            return None
        n = int(value)
    except (TypeError, ValueError):
        return None
    return n


def _finite_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        f = float(value)
    except (TypeError, ValueError):
        return None
    if f != f:  # NaN
        return None
    return f


def event_time_ms(row: Mapping[str, Any]) -> Optional[int]:
    """Prefer explicit ms; accept integer-ms gameTime; reject bare seconds guess."""
    for key in ("gameTimeMs", "tMs", "timeMs"):
        if key in row and row[key] is not None:
            v = _finite_float(row[key])
            if v is None or v < 0:
                return None
            return int(round(v))
    gt = row.get("gameTime")
    v = _finite_float(gt)
    if v is None or v < 0:
        return None
    # Canonical product rfc461 uses integer milliseconds. Fractional / small
    # values are research decode seconds — convert only when clearly seconds.
    if abs(v - round(v)) < 1e-6 and v >= 1000:
        return int(round(v))
    if v < 1000:
        return int(round(v * 1000.0))
    return int(round(v * 1000.0)) if abs(v - round(v)) > 1e-6 else int(round(v))


def attacker_net_id(row: Mapping[str, Any]) -> Optional[int]:
    for key in ("attackerNetId", "sourceNetId", "netId"):
        n = _finite_int(row.get(key))
        if n is not None:
            return n
    return None


def target_net_id(row: Mapping[str, Any]) -> Optional[int]:
    return _finite_int(row.get("targetNetId"))


def load_netid_to_pid(identity: Mapping[str, Any]) -> Dict[int, int]:
    """
    Load netId→participantId from a product identity artifact.

    Accepts:
      - { "netIdToParticipantId": { "1073…": 1, ... } }
      - identityBinding.participants with explicit participantID
    Never invents from createHeroEvents order.
    """
    out: Dict[int, int] = {}
    direct = identity.get("netIdToParticipantId") or identity.get("net_id_to_participant_id")
    if isinstance(direct, Mapping):
        for k, v in direct.items():
            nid = _finite_int(k)
            pid = _finite_int(v)
            if nid is not None and pid is not None:
                out[nid] = pid
    bind = identity.get("identityBinding")
    if isinstance(bind, Mapping):
        for p in bind.get("participants") or []:
            if not isinstance(p, Mapping):
                continue
            nid = _finite_int(p.get("netId"))
            pid = _finite_int(p.get("participantID") or p.get("participantId"))
            if nid is not None and pid is not None:
                out[nid] = pid
    return out


def row_participant_id_source(row: Mapping[str, Any]) -> Optional[str]:
    src = row.get("participantIdSource") or row.get("participantIDSource")
    if isinstance(src, str) and src:
        return src
    # Some research emits put bind method under identityBind — only accept
    # when it is a proven product source enum, never createHero order labels.
    ib = row.get("identityBind")
    if isinstance(ib, str) and ib in PRODUCT_PID_SOURCES:
        return ib
    if row.get("identityResolved") is True:
        return "identity_bind"
    return None


def resolve_participant_id(
    row: Mapping[str, Any],
    *,
    net_id: int,
    netid_to_pid: Optional[Mapping[int, int]],
) -> Tuple[Optional[int], Optional[str]]:
    """Return (pid, reject_reason). reject_reason set ⇒ drop row."""
    if netid_to_pid and net_id in netid_to_pid:
        return int(netid_to_pid[net_id]), None

    raw_pid = _finite_int(row.get("participantID") or row.get("participantId"))
    if raw_pid is None:
        return None, "no_identity"

    src = row_participant_id_source(row)
    if src is None:
        return None, "unproven_pid"
    if src in ORDER_ONLY_PID_SOURCES:
        return None, "order_only_pid"
    if src not in PRODUCT_PID_SOURCES:
        return None, "unproven_pid"
    return raw_pid, None


def extract_action_events_from_rows(
    rows: Iterable[Mapping[str, Any]],
    *,
    netid_to_pid: Optional[Mapping[int, int]] = None,
) -> Dict[str, Any]:
    """
    Extract product timeline AA/damage arrays from rfc461-like rows.

    Never invents events from stats_update / HPΔ / skill_used.
    """
    basic_attack: List[Dict[str, Any]] = []
    damage_dealt: List[Dict[str, Any]] = []
    action_events: List[Dict[str, Any]] = []
    counters = {
        "seen_basic_attack": 0,
        "seen_damage_dealt": 0,
        "accepted_basic_attack": 0,
        "accepted_damage_dealt": 0,
        "rejected_no_net_id": 0,
        "rejected_no_identity": 0,
        "rejected_order_only_pid": 0,
        "rejected_unproven_pid": 0,
        "rejected_bad_time": 0,
        "skipped_other_schema": 0,
        "skipped_skill_used": 0,
        "skipped_stats_update": 0,
    }

    for row in rows:
        schema = str(row.get("rfc461Schema") or "")
        if schema == "skill_used":
            counters["skipped_skill_used"] += 1
            continue
        if schema == "stats_update":
            counters["skipped_stats_update"] += 1
            continue
        if schema not in ("basic_attack", "damage_dealt"):
            counters["skipped_other_schema"] += 1
            continue

        if schema == "basic_attack":
            counters["seen_basic_attack"] += 1
        else:
            counters["seen_damage_dealt"] += 1

        nid = attacker_net_id(row)
        raw_pid = _finite_int(row.get("participantID") or row.get("participantId"))
        if nid is None:
            counters["rejected_no_net_id"] += 1
            if raw_pid is not None:
                counters["rejected_order_only_pid"] += 1
            continue

        t_ms = event_time_ms(row)
        if t_ms is None:
            counters["rejected_bad_time"] += 1
            continue

        pid, reject = resolve_participant_id(
            row, net_id=nid, netid_to_pid=netid_to_pid
        )
        if reject == "order_only_pid":
            counters["rejected_order_only_pid"] += 1
            continue
        if reject == "unproven_pid":
            counters["rejected_unproven_pid"] += 1
            continue
        if reject or pid is None:
            counters["rejected_no_identity"] += 1
            continue

        source_kind = row.get("sourceKind")
        field_source = row.get("fieldSource")
        research_only = row.get("researchOnly")
        if research_only is None and row.get("calculatorReady") is False:
            research_only = True

        base: Dict[str, Any] = {
            "tMs": t_ms,
            "participantId": int(pid),
            "netId": int(nid),
        }
        tgt_nid = target_net_id(row)
        if tgt_nid is not None:
            base["targetNetId"] = tgt_nid
        tgt_pid = _finite_int(
            row.get("targetParticipantID") or row.get("targetParticipantId")
        )
        if tgt_pid is not None and tgt_nid is not None:
            # Only keep target pid when target netId is present (anti order-only).
            if netid_to_pid and tgt_nid in netid_to_pid:
                base["targetParticipantId"] = int(netid_to_pid[tgt_nid])
            elif row_participant_id_source(row) in PRODUCT_PID_SOURCES:
                base["targetParticipantId"] = tgt_pid
        if isinstance(source_kind, str) and source_kind:
            base["sourceKind"] = source_kind
        if isinstance(field_source, str) and field_source:
            base["fieldSource"] = field_source
        if isinstance(research_only, bool):
            base["researchOnly"] = research_only

        if schema == "basic_attack":
            basic_attack.append(dict(base))
            action_events.append({"kind": "basic_attack", **base})
            counters["accepted_basic_attack"] += 1
        else:
            amount = None
            for key in ("amount", "damageAmount", "damage"):
                amount = _finite_float(row.get(key))
                if amount is not None:
                    break
            # Never invent amount — omit when absent. HPΔ is not consulted.
            dmg = dict(base)
            if amount is not None:
                dmg["amount"] = amount
            damage_dealt.append(dmg)
            action_events.append({"kind": "damage_dealt", **dmg})
            counters["accepted_damage_dealt"] += 1

    aa_cov = "none"
    dmg_cov = "none"
    if counters["accepted_basic_attack"] > 0:
        aa_cov = (
            "partial"
            if counters["rejected_no_identity"]
            or counters["rejected_unproven_pid"]
            or counters["rejected_order_only_pid"]
            else "full"
        )
        if any(e.get("researchOnly") for e in basic_attack):
            aa_cov = "research_overlay"
    if counters["accepted_damage_dealt"] > 0:
        dmg_cov = (
            "partial"
            if counters["rejected_no_identity"]
            or counters["rejected_unproven_pid"]
            or counters["rejected_order_only_pid"]
            else "full"
        )
        if any(e.get("researchOnly") for e in damage_dealt):
            dmg_cov = "research_overlay"

    return {
        "basicAttack": basic_attack,
        "damageDealt": damage_dealt,
        "actionEvents": action_events,
        "counters": counters,
        "provenance": {
            "aaCoverage": aa_cov,
            "damageCoverage": dmg_cov,
        },
    }


def attach_action_events_to_timeline(
    timeline: MutableMapping[str, Any],
    extracted: Mapping[str, Any],
    *,
    omit_empty: bool = True,
) -> MutableMapping[str, Any]:
    """Mutate timeline with AA/damage arrays + provenance coverage keys."""
    prov = dict(timeline.get("provenance") or {})
    prov.update(extracted.get("provenance") or {})
    timeline["provenance"] = prov

    for key in ("basicAttack", "damageDealt", "actionEvents"):
        events = list(extracted.get(key) or [])
        if events or not omit_empty:
            timeline[key] = events
        elif key in timeline:
            # Keep absent (unknown) rather than empty invent signal when omit_empty.
            del timeline[key]
    return timeline
