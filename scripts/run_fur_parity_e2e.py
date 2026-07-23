#!/usr/bin/env python3
"""
FUR live-stats parity e2e: maknee events → JSONL → timeline → scoreboard → enrich.

Fixture-driven until live ROFL Decrypt emits the same events[]. Fail-closed on
invented HP (mapper only marks health when Replication decoded it).

Example:
  python3 scripts/run_fur_parity_e2e.py \\
    --fixture docs/rofl-research/fixtures/fur_parity_maknee_events.json \\
    --out-dir /tmp/fur_parity_e2e
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
DEFAULT_FIXTURE = ROOT / "docs/rofl-research/fixtures/fur_parity_maknee_events.json"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--game-id", type=int, default=2970115)
    ap.add_argument("--hz", type=float, default=1.0)
    args = ap.parse_args()

    out = args.out_dir
    out.mkdir(parents=True, exist_ok=True)
    jsonl = out / "events_fur_parity.jsonl"
    timeline = out / "fur_parity_timeline.json"
    report_path = out / "fur_parity_report.json"

    steps = [
        [
            sys.executable,
            str(SCRIPTS / "maknee_packets_to_jsonl.py"),
            str(args.fixture),
            "-o",
            str(jsonl),
            "--hz",
            str(args.hz),
            "--game-id",
            str(args.game_id),
        ],
        [
            sys.executable,
            str(SCRIPTS / "jsonl_to_timeline.py"),
            str(jsonl),
            "-o",
            str(timeline),
            "--id",
            "fur_parity",
            "--name",
            "FUR live-stats parity fixture",
            "--patch",
            "fixture",
        ],
        [
            sys.executable,
            str(SCRIPTS / "rebuild-timeline-scoreboard.py"),
            "--jsonl",
            str(jsonl),
            "--timeline",
            str(timeline),
            "-o",
            str(timeline),
        ],
        [
            sys.executable,
            str(SCRIPTS / "enrich-timeline-career.py"),
            "--jsonl",
            str(jsonl),
            "--timeline",
            str(timeline),
            "-o",
            str(timeline),
        ],
        [
            sys.executable,
            str(SCRIPTS / "validate_fur_parity.py"),
            "--jsonl",
            str(jsonl),
            "--timeline",
            str(timeline),
            "--json-out",
            str(report_path),
        ],
    ]

    for cmd in steps:
        print("+", " ".join(cmd))
        subprocess.check_call(cmd, cwd=str(ROOT))

    report = json.loads(report_path.read_text(encoding="utf-8"))
    print(
        json.dumps(
            {
                "ok": report.get("ok"),
                "jsonl": str(jsonl),
                "timeline": str(timeline),
                "report": str(report_path),
                "voidGrubsBlue": (report.get("timelineGates") or {}).get("voidGrubsBlue"),
                "calculator": {
                    k: (report.get("timelineGates") or {}).get(k)
                    for k in ("hpKnown", "combatStatsKnown", "abilityRanksKnown")
                },
            },
            indent=2,
        )
    )
    return 0 if report.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
