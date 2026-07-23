#!/usr/bin/env python3
"""Phase B: inventory type-107 combat floats; never mark trusted without proof.

Walks the same Replication path as timed HP, inventories primary-1 combat-ish
keys named in ``BINARY_COMBAT_REPLICATION_NAMES``, and fail-closes product
combat emission until a separate index→FUR-field proof pass exists.

Example:
  npm run rofl:replication-combat-inventory -- \\
    --rofl \"$HOME/Documents/League of Legends/Replays/BR1-3264361042.rofl\" \\
    --json-out docs/rofl-research/combat-inventory-BR1-3264361042.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import rofl2_replication_timed_hp as timed  # noqa: E402
from rofl_replication_fields import BINARY_COMBAT_REPLICATION_NAMES  # noqa: E402

DEFAULT_ROFL = timed.DEFAULT_ROFL
DEFAULT_OUT = Path("docs/rofl-research/combat-inventory-BR1-3264361042.json")
WIRE_PROOF_REPORT = Path("docs/rofl-research/combat-wire-proof-BR1-3264361042.json")


def classify_combat_blocker(inventory: Mapping[str, Any]) -> Dict[str, str]:
    observed = list(inventory.get("observedKeys") or [])
    named = sorted(set(observed) & set(BINARY_COMBAT_REPLICATION_NAMES))
    if not observed:
        return {
            "kind": "combat_fields_not_observed",
            "detail": "type-107 walk produced no combat-ish primary-1 keys",
        }
    if not named:
        return {
            "kind": "combat_fields_unmapped",
            "detail": (
                "combat-ish floats observed but none match BINARY_COMBAT_REPLICATION_NAMES"
            ),
        }
    wire = inventory.get("wireProof") or {}
    hyp_observed = []
    if isinstance(wire, Mapping):
        hyp_observed = list(
            ((wire.get("blocker") or {}).get("observedNamed"))
            or wire.get("observedNamed")
            or []
        )
        detail_extra = (wire.get("blocker") or {}).get("detail")
    else:
        detail_extra = None
    return {
        "kind": "combat_wire_unproven",
        "detail": detail_extra
        or (
            "named combat fields appear in inventory only; no product index→FUR "
            "proof pass yet — combatTrusted stays false. Live BR1 type-107 walk "
            f"observes hypothesis names {named or hyp_observed}; PE has combat "
            "strings but no proven (primary,secondary)→name table or identity-bound "
            "FUR oracle (Replay API has no combat floats)."
        ),
    }


def build_combat_report(
    *,
    timed_report: Mapping[str, Any],
    wire_proof: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    inventory = dict(timed_report.get("combatInventory") or {})
    evidence = timed_report.get("evidence")
    if not inventory and isinstance(evidence, Mapping):
        inventory = dict(evidence.get("combatInventory") or {})
    if not inventory:
        inventory = {
            "trusted": False,
            "observedKeys": [],
            "note": "no combat inventory on timed report",
        }
    inventory["trusted"] = False
    inventory["binaryCombatNames"] = sorted(BINARY_COMBAT_REPLICATION_NAMES)
    named = sorted(
        set(inventory.get("observedKeys") or []) & set(BINARY_COMBAT_REPLICATION_NAMES)
    )
    inventory["namedHits"] = named
    bind = timed_report.get("identityBinding") or {}
    if not bind and isinstance(evidence, Mapping):
        bind = evidence.get("identityBinding") or {}
    evidence_match = None
    if isinstance(evidence, Mapping):
        evidence_match = evidence.get("match")
    if wire_proof is None and WIRE_PROOF_REPORT.is_file():
        try:
            loaded = json.loads(WIRE_PROOF_REPORT.read_text(encoding="utf-8"))
            wire_proof = loaded if isinstance(loaded, dict) else None
        except (OSError, json.JSONDecodeError):
            wire_proof = None
    if isinstance(wire_proof, Mapping):
        inventory["wireProof"] = {
            "schema": wire_proof.get("schema"),
            "combatTrusted": bool(wire_proof.get("combatTrusted")),
            "wireTableProven": bool(wire_proof.get("wireTableProven")),
            "observedNamed": (wire_proof.get("blocker") or {}).get("observedNamed")
            or list(
                (
                    (wire_proof.get("hypothesis") or {}).get("furFieldProvenUnderPeTable")
                    or {}
                ).keys()
            ),
            "hypothesisProvenIndexCount": (
                (wire_proof.get("hypothesis") or {}).get("provenIndexCount")
            ),
            "furFieldProvenUnderPeTable": (
                (wire_proof.get("hypothesis") or {}).get("furFieldProvenUnderPeTable")
            ),
            "evidence": str(WIRE_PROOF_REPORT),
        }
        # Prefer wire-proof named observations when inventory is sparse.
        wp_named = (wire_proof.get("blocker") or {}).get("observedNamed") or []
        if wp_named and not named:
            inventory["namedHits"] = list(wp_named)
            inventory["observedKeys"] = sorted(
                set(inventory.get("observedKeys") or []) | set(wp_named)
            )
            named = list(inventory["namedHits"])
        if wire_proof.get("combatTrusted") is True and wire_proof.get("wireTableProven"):
            inventory["trusted"] = True
            return {
                "ok": True,
                "schema": "rofl-combat-inventory-v0",
                "match": evidence_match or timed_report.get("rofl"),
                "identityBindingComplete": bool(bind.get("complete")),
                "inventory": inventory,
                "blocker": None,
                "combatTrusted": True,
                "productEligible": True,
                "note": (
                    "Gate B1 PE wire table proven; combatTrusted=true for product fuse."
                ),
                "dependsOnGateA": not bool(bind.get("complete")),
            }
    blocker = classify_combat_blocker(inventory)
    return {
        "ok": False,
        "schema": "rofl-combat-inventory-v0",
        "match": evidence_match or timed_report.get("rofl"),
        "identityBindingComplete": bool(bind.get("complete")),
        "inventory": inventory,
        "blocker": blocker,
        "combatTrusted": False,
        "productEligible": False,
        "note": (
            "Phase B requires Gate A identity bind plus a proven combat wire map. "
            "This script inventories only; see combat-wire-proof report for PE/index "
            "evidence."
        ),
        "dependsOnGateA": not bool(bind.get("complete")),
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rofl", type=Path, default=DEFAULT_ROFL)
    ap.add_argument("--timed-report", type=Path, default=None)
    ap.add_argument("--json-out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--max-samples", type=int, default=2)
    args = ap.parse_args(argv)

    if args.timed_report and args.timed_report.is_file():
        timed_report = json.loads(args.timed_report.read_text(encoding="utf-8"))
    else:
        # Lightweight: reuse existing candidate report when present.
        fallback = Path("docs/rofl-research/timed-hp-report-BR1-3264361042.json")
        if fallback.is_file():
            timed_report = json.loads(fallback.read_text(encoding="utf-8"))
        else:
            timed_report = timed.decode_timed_hp(
                rofl=args.rofl,
                max_samples=max(1, int(args.max_samples)),
            )

    # Attach combat inventory from evidence when the emitter stored it.
    evidence = timed_report.get("evidence") or {}
    if "combatInventory" not in timed_report and isinstance(evidence, Mapping):
        # Rebuild a minimal inventory note from fieldIndices honesty.
        timed_report = dict(timed_report)
        timed_report["combatInventory"] = {
            "trusted": False,
            "observedKeys": list(
                ((evidence.get("combatInventory") or {}).get("observedKeys")) or []
            ),
            "note": "from timed HP evidence; not product-trusted",
        }

    report = build_combat_report(timed_report=timed_report)
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(
        json.dumps(report, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {args.json_out}")
    print(
        f"combatTrusted={report.get('combatTrusted')} "
        f"blocker={(report.get('blocker') or {}).get('kind')} "
        f"gateA={not report.get('dependsOnGateA')}"
    )
    return 0 if report.get("combatTrusted") else 2

if __name__ == "__main__":
    raise SystemExit(main())
