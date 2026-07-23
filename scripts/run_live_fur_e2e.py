#!/usr/bin/env python3
"""
SCHEMA PROOF ONLY — not a real-match publication path.

Live BR1 decrypt HP → merge FUR fixture roster/combat/ranks → jsonl →
timeline → validate_fur. Proves schema plumbing (hpKnown/combat/ranks gates
light up after remap). It deliberately remaps live Replication HP onto the
FUR fixture CreateHero net_ids and keeps fixture combat/ranks.

This must never masquerade as the authoritative timeline for the ROFL match
code, and must never pass ``validate-rofl-pipeline.py --product``.

Real match map review uses Replay API jsonl → timeline under the true match
code. Real calculator readiness requires same-match identity-bound positions
+ HP + combat + ranks (not this fixture merge).

Fail-closed: exits non-zero if replication HP acceptance fails (no invented HP).

Example:
  python3 scripts/run_live_fur_e2e.py \\
    "$HOME/Documents/League of Legends/Replays/BR1-3264383283.rofl" \\
    --out-dir /tmp/live_fur_schema_proof
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
PUBLIC_DATA = (ROOT / "public/data").resolve()

SCHEMA_PROOF_SOURCE = "schema_proof_fixture_hp_merge"
SCHEMA_PROOF_SOURCE_KIND = "schema_proof_fixture_hp_merge"
SCHEMA_PROOF_ID = "live_fur_schema_proof"


def game_id_from_rofl(path: Path) -> Optional[int]:
    """BR1-3264383283.rofl → 3264383283 (digits only; not a publish identity)."""
    m = re.search(r"(\d{7,})", path.stem)
    return int(m.group(1)) if m else None


def resolve_safe_output_dir(path: Path) -> Path:
    """Reject schema-proof writes anywhere under the public product data tree."""
    resolved = path.expanduser().resolve()
    if resolved == PUBLIC_DATA or PUBLIC_DATA in resolved.parents:
        raise ValueError(
            "refusing schema-proof output inside public/data; choose a research "
            f"directory outside {PUBLIC_DATA}"
        )
    return resolved


def _stamp_schema_proof_jsonl(jsonl: Path, *, rofl_stem: str) -> None:
    """Mark JSONL so product publication gates reject it unmistakably."""
    rows = []
    for line in jsonl.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rows.append(json.loads(line))
    for row in rows:
        if row.get("rfc461Schema") != "rofl_coverage":
            continue
        prov = dict(row.get("provenance") or {})
        prov["source"] = SCHEMA_PROOF_SOURCE
        prov["sourceKind"] = SCHEMA_PROOF_SOURCE_KIND
        prov["schemaProof"] = True
        prov["researchOnly"] = True
        prov["publicationBlocked"] = True
        prov["calculatorReady"] = False
        notes = prov.get("notes") or ""
        prov["notes"] = (
            (notes + " " if notes else "")
            + "SCHEMA PROOF ONLY: live Replication HP remapped onto FUR fixture "
            "roster/combat/ranks. Not a real match; publicationBlocked. "
            f"ROFL stem={rofl_stem}."
        ).strip()
        row["provenance"] = prov
        row["source"] = SCHEMA_PROOF_SOURCE
        row["notes"] = prov["notes"]
        break
    jsonl.write_text(
        "\n".join(json.dumps(r, separators=(",", ":")) for r in rows) + "\n",
        encoding="utf-8",
    )


def _stamp_schema_proof_timeline(timeline: Path, *, rofl_stem: str) -> None:
    """Mark GameTimeline so product publication gates reject it."""
    tl = json.loads(timeline.read_text(encoding="utf-8"))
    tl["id"] = SCHEMA_PROOF_ID
    tl["source"] = SCHEMA_PROOF_SOURCE
    prov = dict(tl.get("provenance") or {})
    prov["source"] = SCHEMA_PROOF_SOURCE
    prov["sourceKind"] = SCHEMA_PROOF_SOURCE_KIND
    prov["schemaProof"] = True
    prov["researchOnly"] = True
    prov["publicationBlocked"] = True
    prov["calculatorReady"] = False
    notes = prov.get("notes") or ""
    prov["notes"] = (
        (notes + " " if notes else "")
        + "SCHEMA PROOF ONLY — fixture roster/combat with live HP remap. "
        "Not product-publishable."
    ).strip()
    tl["provenance"] = prov
    if "FUR schema proof" not in str(tl.get("name") or ""):
        tl["name"] = f"FUR schema proof ({rofl_stem})"
    timeline.write_text(json.dumps(tl) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("rofl", type=Path)
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--max-chunks", type=int, default=50)
    ap.add_argument("--max-blocks", type=int, default=1200)
    ap.add_argument(
        "--game-id",
        type=int,
        default=None,
        help="Internal rfc461 gameID only; outputs stay schema-proof / publicationBlocked",
    )
    ap.add_argument("--hz", type=float, default=1.0)
    ap.add_argument(
        "--fixture-events",
        type=Path,
        default=ROOT / "docs/rofl-research/fixtures/fur_parity_maknee_events.json",
        help="Merged with live Replication HP events for full schema coverage",
    )
    args = ap.parse_args()
    try:
        out = resolve_safe_output_dir(args.out_dir)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    game_id = args.game_id if args.game_id is not None else game_id_from_rofl(args.rofl)
    if game_id is None:
        print("could not parse match code from ROFL name; pass --game-id", file=sys.stderr)
        return 2
    rofl_stem = args.rofl.stem

    out.mkdir(parents=True, exist_ok=True)
    decode_json = out / "replication_decode.json"
    events_json = out / "maknee_events.json"
    jsonl = out / "events_live_fur_schema_proof.jsonl"
    timeline = out / "live_fur_schema_proof_timeline.json"
    report_path = out / "live_fur_schema_proof_report.json"

    # 1) Live decrypt / apply
    r = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS / "rofl2_replication_decode.py"),
            str(args.rofl),
            "--max-chunks",
            str(args.max_chunks),
            "--max-blocks",
            str(args.max_blocks),
            "--json-out",
            str(decode_json),
            "--work-dir",
            str(out / "unicorn"),
        ],
        cwd=str(ROOT),
    )
    if r.returncode != 0:
        print("replication decode failed (fail-closed)", file=sys.stderr)
        return r.returncode

    decode = json.loads(decode_json.read_text(encoding="utf-8"))
    if not decode.get("ok") or decode.get("decryptStatus") != "replication_hp_accepted":
        print(
            f"HP not accepted: {decode.get('decryptStatus')}",
            file=sys.stderr,
        )
        return 1

    live_events = list(decode.get("events") or [])
    live_heroes = list((decode.get("hpSnapshot") or {}).get("heroes") or [])
    fixture = json.loads(args.fixture_events.read_text(encoding="utf-8"))
    fixture_heroes = [
        e["CreateHero"] for e in fixture.get("events") or [] if "CreateHero" in e
    ]
    # Bind live HP onto fixture roster order (CreateHero net_ids) so mapper gates light up.
    live_sorted = sorted(live_heroes, key=lambda h: int(h["netId"]))
    net_remap = {}
    if len(live_sorted) >= 10 and len(fixture_heroes) >= 10:
        for i in range(10):
            net_remap[int(live_sorted[i]["netId"])] = int(fixture_heroes[i]["net_id"])

    def remap_event(ev: dict) -> dict:
        if "Replication" not in ev:
            return ev
        rep = ev["Replication"]
        datas = rep.get("net_id_to_replication_datas") or {}
        new_datas = {}
        for nid, payload in datas.items():
            dst = net_remap.get(int(nid))
            if dst is None:
                continue
            new_datas[str(dst)] = payload
        if not new_datas:
            return ev
        return {"Replication": {**rep, "net_id_to_replication_datas": new_datas}}

    merged = []
    for ev in fixture.get("events") or []:
        if "Replication" in ev:
            name = None
            datas = (ev["Replication"].get("net_id_to_replication_datas") or {})
            for payload in datas.values():
                name = payload.get("name")
                break
            # Drop fixture HP; keep combat / level so schema combat gate stays green.
            if name in ("mHP", "mMaxHP"):
                continue
        merged.append(ev)
    for ev in live_events:
        merged.append(remap_event(ev))

    events_json.write_text(json.dumps({"events": merged}, indent=2) + "\n", encoding="utf-8")

    maknee_cmd = [
        sys.executable,
        str(SCRIPTS / "maknee_packets_to_jsonl.py"),
        str(events_json),
        "-o",
        str(jsonl),
        "--hz",
        str(args.hz),
        "--game-id",
        str(game_id),
    ]
    print("+", " ".join(maknee_cmd))
    rr = subprocess.run(maknee_cmd, cwd=str(ROOT))
    if rr.returncode != 0:
        return rr.returncode

    # Stamp before timeline build so provenance is inherited.
    _stamp_schema_proof_jsonl(jsonl, rofl_stem=rofl_stem)

    steps = [
        [
            sys.executable,
            str(SCRIPTS / "jsonl_to_timeline.py"),
            str(jsonl),
            "-o",
            str(timeline),
            "--id",
            SCHEMA_PROOF_ID,
            "--name",
            f"FUR schema proof ({rofl_stem})",
            "--patch",
            str(decode.get("gameVersion") or "live"),
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
        rr = subprocess.run(cmd, cwd=str(ROOT))
        if rr.returncode != 0:
            return rr.returncode

    _stamp_schema_proof_timeline(timeline, rofl_stem=rofl_stem)

    # Camp / minion assertions
    tl = json.loads(timeline.read_text(encoding="utf-8"))
    mid = tl["frames"][len(tl["frames"]) // 2]
    camps = (mid.get("mapObjects") or {}).get("camps") or []
    minions = (mid.get("mapObjects") or {}).get("minions") or []
    assert camps, "expected mapObjects.camps"
    marker = out / "SCHEMA_PROOF_ONLY"
    marker.write_text(
        "This directory is a FUR schema-proof artifact.\n"
        "Do not publish under a real match code or product registry.\n"
        "Use validate-rofl-pipeline.py --product to confirm rejection.\n",
        encoding="utf-8",
    )
    report = {
        "ok": True,
        "schemaProof": True,
        "researchOnly": True,
        "publicationBlocked": True,
        "calculatorReady": False,
        "productPublishable": False,
        "decryptStatus": decode.get("decryptStatus"),
        "hpHeroes": (decode.get("hpSnapshot") or {}).get("heroCount"),
        "useReplication": decode.get("useReplication"),
        "camps": len(camps),
        "minionsAtMid": len(minions),
        "validateReport": str(report_path),
        "timeline": str(timeline),
        "jsonl": str(jsonl),
        "note": (
            "Schema plumbing proof only. Real-match calculator readiness requires "
            "same-match identity-bound positions + HP + combat + ranks."
        ),
    }
    summary = out / "live_fur_schema_proof_summary.json"
    summary.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
