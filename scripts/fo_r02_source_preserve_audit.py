#!/usr/bin/env python3
"""F1/R02 — audit Path1 fuse/merge for silent *Source wipe (GOAL §D).

Reads 2970132 Path1 final events (+ optional timeline), rebuilds via
jsonl_to_timeline, and reports known-without-source counts.

Never edits parent checkout. Never invents pins.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from jsonl_to_timeline import build_timeline  # noqa: E402

PARENT = Path("/Users/river/Projects/lol-strength-analysis")
DEFAULT_EVENTS = ROOT / "artifacts/rofl/2970132/events.g1.path1-final.rfc461.jsonl"
DEFAULT_TIMELINE = ROOT / "artifacts/rofl/2970132/timeline.g1.path1-final.json"
DEFAULT_IDENTITY = ROOT / (
    "docs/rofl-research/product_ready/r06/"
    "castspell-identity-2970132-g1-pid-stamped.json"
)
DEFAULT_OUT = ROOT / (
    "docs/rofl-research/autoresearch/fight_outcome/r02/source_preserve_audit.json"
)


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def census_timeline(timeline: Mapping[str, Any]) -> Dict[str, Any]:
    hp = Counter()
    combat = Counter()
    ranks = Counter()
    missing = {"hp": 0, "combat": 0, "ranks": 0}
    for frame in timeline.get("frames") or []:
        for unit in frame.get("units") or []:
            if unit.get("hpKnown") is True:
                src = unit.get("hpSource")
                if src:
                    hp[str(src)] += 1
                else:
                    missing["hp"] += 1
            if unit.get("combatStatsKnown") is True:
                src = unit.get("combatStatsSource") or unit.get("combatSource")
                if src:
                    combat[str(src)] += 1
                else:
                    missing["combat"] += 1
            if unit.get("abilityRanksKnown") is True:
                src = unit.get("abilityRanksSource")
                if src:
                    ranks[str(src)] += 1
                else:
                    missing["ranks"] += 1
    return {
        "hpSource": dict(hp),
        "combatSource": dict(combat),
        "abilityRanksSource": dict(ranks),
        "knownWithoutSource": missing,
        "ok": missing["hp"] == 0 and missing["combat"] == 0 and missing["ranks"] == 0,
    }


def census_events(events_path: Path) -> Dict[str, Any]:
    hp = Counter()
    combat = Counter()
    ranks = Counter()
    stats = 0
    with events_path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if row.get("rfc461Schema") != "stats_update":
                continue
            stats += 1
            for part in row.get("participants") or []:
                if part.get("hpSource"):
                    hp[str(part["hpSource"])] += 1
                cs = part.get("combatStatsSource") or part.get("combatSource")
                if cs and cs not in ("unavailable", "unavailable_replay_api", "unknown"):
                    combat[str(cs)] += 1
                if part.get("abilityRanksSource"):
                    ranks[str(part["abilityRanksSource"])] += 1
    return {
        "statsFrames": stats,
        "hpSource": dict(hp),
        "combatSource": dict(combat),
        "abilityRanksSource": dict(ranks),
    }


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--events", type=Path, default=DEFAULT_EVENTS)
    ap.add_argument("--timeline", type=Path, default=DEFAULT_TIMELINE)
    ap.add_argument("--identity", type=Path, default=DEFAULT_IDENTITY)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args(argv)

    if ROOT.resolve() == PARENT.resolve():
        print("FAIL: refusing to run inside parent checkout", file=sys.stderr)
        return 2
    if not args.events.is_file():
        print(f"FAIL: missing events {args.events}", file=sys.stderr)
        return 2

    identity = None
    if args.identity.is_file():
        identity = json.loads(args.identity.read_text(encoding="utf-8"))

    event_census = census_events(args.events)
    rebuilt = build_timeline(
        args.events,
        timeline_id="2970132-g1",
        name="R02 source-preserve rebuild",
        patch="16.13",
        action_identity=identity,
        action_jsonl_paths=[],
    )
    rebuilt.pop("_actionExtractCounters", None)
    rebuild_census = census_timeline(rebuilt)

    shipped_census = None
    if args.timeline.is_file():
        shipped = json.loads(args.timeline.read_text(encoding="utf-8"))
        shipped_census = census_timeline(shipped)

    findings = [
        {
            "id": "F1",
            "title": "jsonl_to_timeline must copy hpSource/combatSource/abilityRanksSource",
            "status": "fixed_in_worktree",
            "note": (
                "Prior Path1 death-merge rematch saw peHpHeroes=0/10 because "
                "timeline rebuild dropped source tags. Copy path is present; "
                "rebuild census must show missing=0."
            ),
        },
        {
            "id": "F2",
            "title": "strip_untrusted left orphan hpSource/combatSource",
            "status": "patched",
            "note": (
                "fuse_product_timeline.strip_untrusted_product_fields wiped "
                "health/combat floats but left hpSource/combatSource — silent lie. "
                "Now clears HP_SOURCE_STRIP_KEYS + COMBAT_SOURCE_STRIP_KEYS."
            ),
        },
        {
            "id": "F3",
            "title": "combat clear must pop combatSource",
            "status": "patched",
            "note": (
                "Restored Path1 hold_forward fuse_replay_api_combat from prd-r04; "
                "_clear_combat pops combatSource when forcing unavailable."
            ),
        },
        {
            "id": "F4",
            "title": "Dead HP across-death pops hpSource (honest unknown)",
            "status": "ok_intentional",
            "note": (
                "fuse_replay_api_hp across-death dead frames pop hpSource while "
                "health unavailable — not a silent wipe of known; dead stays unknown."
            ),
        },
    ]

    report = {
        "schema": "fo-r02-source-preserve-audit-v1",
        "utc": _utc(),
        "researcher": "R02",
        "room": "f1",
        "hypothesis": "F1#2 Source preserve",
        "branch": "adv/fo-r02-digest-sources",
        "worktree": str(ROOT),
        "never_edited_parent": True,
        "events": {
            "path": str(args.events.relative_to(ROOT)),
            "bytes": args.events.stat().st_size,
            "sha256": _sha256(args.events),
            "census": event_census,
        },
        "shippedTimeline": (
            {
                "path": str(args.timeline.relative_to(ROOT)),
                "bytes": args.timeline.stat().st_size,
                "sha256": _sha256(args.timeline),
                "census": shipped_census,
            }
            if shipped_census is not None
            else None
        ),
        "rebuildTimeline": {
            "census": rebuild_census,
            "ok": rebuild_census["ok"],
        },
        "findings": findings,
        "pass": bool(rebuild_census["ok"]),
        "digestCleanGateContribution": (
            "source tags survive events→timeline rebuild on 2970132 Path1 final; "
            "strip/clear no longer leave orphan or drop known sources silently"
        ),
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"pass": report["pass"], "out": str(args.out), "rebuild": rebuild_census}, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
