#!/usr/bin/env python3
"""
Build a small maknee-derived fixture + smoke-test the JSONL mapper.

Downloads one HF match (cached), keeps CreateHero + a capped subset of useful
packets, writes docs/rofl-research/fixtures/maknee_match_stub.json, converts to
JSONL, and asserts schema/position sanity.

Example:
  python3 scripts/rofl_maknee_fixture.py
  python3 scripts/rofl_maknee_fixture.py --skip-download  # reuse existing stub
"""
from __future__ import annotations

import argparse
import gzip
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "docs" / "rofl-research" / "fixtures"
STUB_PATH = FIXTURE_DIR / "maknee_match_stub.json"
OUT_JSONL = FIXTURE_DIR / "events_maknee_stub.jsonl"

KEEP_TYPES = {
    "CreateHero",
    "WaypointGroup",
    "WaypointGroupWithSpeed",
    "Replication",
    "BuyItem",
    "RemoveItem",
    "SwapItem",
    "CastSpellAns",
    "CreateTurret",
    "CreateNeutral",
    "NPCDieMapView",
    "NPCDieMapViewBroadcast",
    "HeroDie",
}

# Keep the committed stub small (<~500KB). Use --full for a denser local smoke.
CAPS_SMALL = {
    "CreateHero": 20,
    "WaypointGroup": 1200,
    "WaypointGroupWithSpeed": 120,
    "Replication": 2500,
    "CastSpellAns": 120,
    "BuyItem": 80,
    "RemoveItem": 40,
    "SwapItem": 20,
    "CreateTurret": 40,
    "CreateNeutral": 80,
    "NPCDieMapView": 120,
    "NPCDieMapViewBroadcast": 20,
    "HeroDie": 20,
}

CAPS_FULL = {
    "CreateHero": 30,
    "WaypointGroup": 4000,
    "WaypointGroupWithSpeed": 400,
    "Replication": 8000,
    "CastSpellAns": 400,
    "BuyItem": 200,
    "RemoveItem": 100,
    "SwapItem": 50,
    "CreateTurret": 50,
    "CreateNeutral": 200,
    "NPCDieMapView": 400,
    "NPCDieMapViewBroadcast": 50,
    "HeroDie": 50,
}


def build_stub_from_hf(*, full: bool = False) -> dict:
    from huggingface_hub import hf_hub_download

    caps = CAPS_FULL if full else CAPS_SMALL
    path = hf_hub_download(
        repo_id="maknee/league-of-legends-decoded-replay-packets",
        filename="12_22/batch_001.jsonl.gz",
        repo_type="dataset",
    )
    with gzip.open(path, "rt", encoding="utf-8") as f:
        match = json.loads(f.readline())
    counts: Counter = Counter()
    keep = []
    for e in match["events"]:
        key = next(iter(e))
        if key not in KEEP_TYPES:
            continue
        if counts[key] >= caps.get(key, 100):
            continue
        # Slim Replication: only hero-relevant named fields
        if key == "Replication":
            rep = e["Replication"]
            slim = {}
            for nid, data in (rep.get("net_id_to_replication_datas") or {}).items():
                name = data.get("name") or ""
                if name in ("mHP", "mMaxHP", "mLevelRef", "mGoldTotal"):
                    slim[nid] = data
            if not slim:
                continue
            e = {
                "Replication": {
                    "time": rep.get("time", 0),
                    "net_id_to_replication_datas": slim,
                }
            }
        keep.append(e)
        counts[key] += 1
    return {"events": keep, "fixture_counts": dict(counts)}


def smoke(jsonl_path: Path, expected_cadence_ms: int = 1000) -> None:
    from rfc461_emit import fountain_for_team

    schemas: Counter = Counter()
    stats = []
    coverage = None
    game_info = None
    for line in jsonl_path.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        schemas[row["rfc461Schema"]] += 1
        if row["rfc461Schema"] == "rofl_coverage":
            coverage = row
        if row["rfc461Schema"] == "game_info":
            game_info = row
        if row["rfc461Schema"] == "stats_update":
            stats.append(row)

    assert coverage is not None, "missing rofl_coverage"
    assert game_info is not None and schemas.get("game_info", 0) >= 1, "missing game_info"
    assert len(stats) >= 10, f"expected many stats_update, got {len(stats)}"
    assert schemas.get("game_end", 0) >= 1, "missing game_end"
    provenance = coverage.get("provenance") or {}
    assert provenance.get("gameTimeUnit") == "milliseconds"
    assert provenance.get("coordinateOffset") == {"x": 7500.0, "z": 7500.0}
    assert provenance.get("positionCoverage") == "partial"
    roster = game_info.get("participants") or []
    assert [p.get("participantID") for p in roster] == list(range(1, 11))
    assert [p.get("teamID") for p in roster] == [100] * 5 + [200] * 5
    times = [int(s["gameTime"]) for s in stats]
    assert times == sorted(times), "stats_update times are not monotonic milliseconds"
    assert all(
        (b - a) == expected_cadence_ms for a, b in zip(times, times[1:])
    ), "fixture cadence drifted from requested hz"

    # After 30s, champs should have real waypoints
    late = [s for s in stats if float(s["gameTime"]) >= 30_000]
    if not late:
        late = [s for s in stats if float(s["gameTime"]) >= 30]
    if not late:
        late = stats[len(stats) // 2 :]
    assert late, "no stats_update samples"
    sample = late[min(5, len(late) - 1)]
    non_fountain = sum(
        1 for p in sample["participants"] if p.get("positionSource") == "maknee_waypoint"
    )
    for p in sample["participants"]:
        pos = p.get("position") or {}
        assert 0 <= float(pos.get("x", -1)) <= 16000
        assert 0 <= float(pos.get("z", -1)) <= 16000
        assert p.get("positionSource") in {"maknee_waypoint", "fountain_placeholder"}
        if p.get("positionSource") == "fountain_placeholder":
            expected = fountain_for_team(int(p["teamID"]))
            assert abs(float(pos["x"]) - expected["x"]) < 1e-6
            assert abs(float(pos["z"]) - expected["z"]) < 1e-6
        hp, hp_max = float(p.get("health") or 0), float(p.get("healthMax") or 0)
        assert 0 <= hp <= hp_max, f"invalid decoded HP {hp}/{hp_max}"
    assert non_fountain >= 3, f"expected moving champs, got {non_fountain} waypoints"

    # HP should be real for at least some participants at some point
    hp_ok = False
    for s in late:
        for p in s["participants"]:
            if float(p.get("healthMax") or 0) > 100:
                hp_ok = True
                break
        if hp_ok:
            break
    assert hp_ok, "expected Replication mMaxHP > 100 on some late frame"

    print(
        json.dumps(
            {
                "ok": True,
                "schemas": dict(schemas),
                "stats_updates": len(stats),
                "late_sample_waypoints": non_fountain,
                "late_sample_t": sample["gameTime"],
                "position_sources": sorted(
                    {p.get("positionSource") for p in sample["participants"]}
                ),
            },
            indent=2,
        )
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--skip-download", action="store_true")
    ap.add_argument(
        "--full",
        action="store_true",
        help="Larger local stub (not for commit); denser smoke coverage",
    )
    ap.add_argument("--hz", type=float, default=1.0)
    ap.add_argument("--stub", type=Path, default=STUB_PATH)
    ap.add_argument("--jsonl-output", type=Path, default=OUT_JSONL)
    ap.add_argument(
        "--timeline-output",
        type=Path,
        default=ROOT / "public" / "data" / "maknee_stub_timeline.json",
    )
    args = ap.parse_args()

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from maknee_packets_to_jsonl import convert

    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)

    if args.skip_download and args.stub.exists():
        stub = json.loads(args.stub.read_text(encoding="utf-8"))
    else:
        stub = build_stub_from_hf(full=args.full)
        counts = stub.pop("fixture_counts", {})
        args.stub.parent.mkdir(parents=True, exist_ok=True)
        args.stub.write_text(json.dumps(stub, separators=(",", ":")), encoding="utf-8")
        meta = args.stub.with_suffix(".meta.json")
        meta.write_text(
            json.dumps(
                {"counts": counts, "events": len(stub["events"]), "full": args.full},
                indent=2,
            )
        )
        print(f"wrote stub {args.stub} events={len(stub['events'])} counts={counts}")

    rows = convert(stub, hz=args.hz, game_id=12022001)
    args.jsonl_output.parent.mkdir(parents=True, exist_ok=True)
    args.jsonl_output.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {args.jsonl_output} lines={len(rows)}")
    smoke(args.jsonl_output, expected_cadence_ms=round(1000 / args.hz) if args.hz > 0 else 1000)

    # Also rebuild the public timeline the Game Review UI can load
    from jsonl_to_timeline import build_timeline

    public_tl = args.timeline_output
    tl = build_timeline(
        args.jsonl_output,
        timeline_id="maknee_stub",
        name="Maknee decoded-packets stub",
        patch="12.22",
    )
    public_tl.parent.mkdir(parents=True, exist_ok=True)
    public_tl.write_text(json.dumps(tl, separators=(",", ":")), encoding="utf-8")
    mid = tl["frames"][len(tl["frames"]) // 2]
    xs = [u["x"] for u in mid["units"]]
    print(
        json.dumps(
            {
                "timeline": str(public_tl),
                "frames": tl["frameCount"],
                "durationMs": tl["durationMs"],
                "mid_x_spread": round(max(xs) - min(xs), 4) if xs else 0,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
