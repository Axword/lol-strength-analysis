#!/usr/bin/env python3
"""Build rofl-trusted-hp-v1 evidence from combat-wire densified timed HP samples.

Copies match/identity/timing from an existing trusted HP template and replaces
``samples`` with carry-forward densified all-10 explicit mMaxHP rows. Never
invents HP; never CreateHero-order binds.

Example:
  python3 scripts/rofl_build_dense_hp_evidence.py \\
    --template artifacts/rofl/3264361042/hp-evidence.json \\
    --combat-proof docs/rofl-research/combat-wire-proof-BR1-3264361042.json \\
    -o artifacts/rofl/3264361042/hp-evidence.dense.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from rofl2_packet_decrypt_probe import DecryptError  # noqa: E402


def build_dense_trusted_hp_evidence(
    *,
    template: Mapping[str, Any],
    combat_proof: Mapping[str, Any],
) -> Dict[str, Any]:
    if template.get("schema") != "rofl-trusted-hp-v1":
        raise DecryptError("template must be rofl-trusted-hp-v1")
    binding = template.get("identityBinding") or {}
    if binding.get("complete") is not True:
        raise DecryptError("template identityBinding.complete must be true")
    if binding.get("method") != "stable_identity_to_net_id":
        raise DecryptError("template must use stable_identity_to_net_id")
    timed = combat_proof.get("timedHpEvidence") or {}
    samples = list(timed.get("samples") or [])
    if len(samples) < 2:
        raise DecryptError("combat proof timedHpEvidence needs ≥2 densified samples")
    for index, sample in enumerate(samples):
        units = sample.get("units")
        if not isinstance(units, list) or len(units) != 10:
            raise DecryptError(f"dense sample[{index}] must contain 10 units")
        if not all(bool(u.get("mMaxHPExplicit")) for u in units):
            raise DecryptError(f"dense sample[{index}] lacks explicit mMaxHP")
        if "gameTimeMs" not in sample:
            raise DecryptError(f"dense sample[{index}] is untimed")

    out = json.loads(json.dumps(template))  # deep copy via JSON
    out["samples"] = samples
    prov = dict(out.get("provenance") or {})
    prov["hpDensified"] = True
    prov["hpDensifyMode"] = "carry_forward_explicit_mMaxHP_frame_grid"
    prov["firstAll10HpMs"] = timed.get("firstAll10HpMs")
    prov["monkeyKingFirstHpMs"] = timed.get("monkeyKingFirstHpMs")
    prov["otherHeroesFirstHpMs"] = timed.get("otherHeroesFirstHpMs")
    prov["denseSampleCount"] = len(samples)
    out["provenance"] = prov
    timing = dict(out.get("timing") or {})
    timing["alignmentNote"] = (
        "Carry-forward densify of explicit type-107 (5,0)/(5,1) onto Replay API "
        "1Hz frame times after first all-10 acceptance; ≤500ms product snap still "
        "applies at fuse."
    )
    out["timing"] = timing
    return out


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--template", type=Path, required=True)
    ap.add_argument("--combat-proof", type=Path, required=True)
    ap.add_argument("-o", "--out", type=Path, required=True)
    args = ap.parse_args(argv)
    template = json.loads(args.template.read_text(encoding="utf-8"))
    proof = json.loads(args.combat_proof.read_text(encoding="utf-8"))
    if proof.get("combatTrusted") is not True or proof.get("wireTableProven") is not True:
        print("combat proof is not wire-table trusted", file=sys.stderr)
        return 2
    evidence = build_dense_trusted_hp_evidence(template=template, combat_proof=proof)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print(
        f"wrote {args.out} samples={len(evidence['samples'])} "
        f"firstAll10={evidence['provenance'].get('firstAll10HpMs')}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
