#!/usr/bin/env python3
"""Stamp Path1 living_post_seed provenance onto a rebuilt timeline (digest path).

Why: `jsonl_to_timeline.py` copies `rofl_coverage.provenance` as-is. Path1 rematch
stamps `hpHoldAcrossRespawn` / `calculatorReadyPolicy` onto the *timeline* after
build, but does not rewrite the rfc461 coverage row. A bare rebuild therefore
drops those stamps even though per-unit `hpSource`/`combatStatsSource`/
`abilityRanksSource` are preserved.

This helper re-applies the disclosed Path1 stamps so validate --product reports
`hpHoldAcrossRespawn: true` honestly. It never invents HP/combat/ranks pins.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict

PATH1_STAMPS: Dict[str, Any] = {
    "sourceKind": "product_fuse_composer_r15_path1_rematch_final",
    "fuseComposer": "rofl2_r15_path1_rematch_final.py",
    "calculatorReadyPolicy": "living_post_seed_v1",
    "hpHoldForward": True,
    "hpHoldForwardUsed": True,
    "hpHoldAcrossRespawn": True,
    "hpHoldForwardPolicy": "until_next_seed_keep_across_death_respawn_restores",
    "combatHoldForward": True,
    "combatHoldAcrossRespawn": True,
    "holdForwardUsed": True,
    "gridSeriesId": "2970132",
    "gridGameIndex": 1,
    "notes": (
        "R01 digest stamp: re-apply Path1 hold-across / living_post_seed_v1 "
        "provenance after jsonl_to_timeline rebuild. Per-unit sources already "
        "copied from rfc461; this does not invent HP/combat/ranks."
    ),
}


def stamp(timeline: Dict[str, Any], *, calculator_ready: bool | None = None) -> Dict[str, Any]:
    prov = dict(timeline.get("provenance") or {})
    prov.update(PATH1_STAMPS)
    if calculator_ready is not None:
        prov["calculatorReady"] = bool(calculator_ready)
    timeline["provenance"] = prov
    return timeline


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--timeline", type=Path, required=True)
    ap.add_argument("-o", "--output", type=Path, required=True)
    ap.add_argument(
        "--set-calculator-ready",
        choices=("true", "false", "leave"),
        default="leave",
        help="Optionally set provenance.calculatorReady; default leave unchanged.",
    )
    args = ap.parse_args(argv)

    timeline = json.loads(args.timeline.read_text(encoding="utf-8"))
    ready = None
    if args.set_calculator_ready == "true":
        ready = True
    elif args.set_calculator_ready == "false":
        ready = False
    stamp(timeline, calculator_ready=ready)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(timeline, separators=(",", ":"), ensure_ascii=False),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "wrote": str(args.output),
                "hpHoldAcrossRespawn": timeline["provenance"].get("hpHoldAcrossRespawn"),
                "calculatorReadyPolicy": timeline["provenance"].get(
                    "calculatorReadyPolicy"
                ),
                "calculatorReady": timeline["provenance"].get("calculatorReady"),
            }
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
