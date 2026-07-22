#!/usr/bin/env python3
"""
Emit maknee-shaped {"events":[...]} from a decrypt probe report + roster source.

Plug-in point for ROFL2 field decrypt: once ``rofl2_packet_decrypt_probe`` or
``rofl2_replication_decode`` can supply Replication HP (and optional waypoints),
this writer produces the same events[] shape consumed by
``maknee_packets_to_jsonl.py``.

Example:
  python3 scripts/rofl2_packet_decrypt_probe.py \\
    --backend fixture \\
    --fixture-events docs/rofl-research/fixtures/maknee_match_stub.json \\
    --json-out /tmp/probe.json --require-acceptance

  python3 scripts/rofl2_to_maknee_events.py \\
    --probe /tmp/probe.json \\
    --fixture-events docs/rofl-research/fixtures/maknee_match_stub.json \\
    -o /tmp/rofl_decrypt_events.json

  # Live decode report (events only when acceptance already passed):
  python3 scripts/rofl2_to_maknee_events.py \\
    --probe /tmp/repl_decode.json \\
    -o /tmp/rofl_decrypt_events.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rofl2_packet_decrypt_probe import (  # noqa: E402
    DecryptError,
    heroes_from_events,
    heroes_from_rofl_stats,
)
from rofl2_replication_decode import (  # noqa: E402
    acceptance_heroes,
    maknee_replication_events,
)


def _load_events(path: Path) -> List[dict]:
    match = json.loads(path.read_text(encoding="utf-8"))
    if "events" in match:
        return list(match["events"])
    if isinstance(match.get("match"), dict) and "events" in match["match"]:
        return list(match["match"]["events"])
    raise SystemExit(f"no events[] in {path}")


def _create_hero_events(heroes: Sequence[Mapping[str, Any]], *, time_s: float = 0.0) -> List[dict]:
    out = []
    for h in heroes:
        out.append(
            {
                "CreateHero": {
                    "time": float(time_s),
                    "net_id": int(h["net_id"]),
                    "name": h.get("name") or f"id{h['net_id']}",
                    "champion": h.get("champion") or "Unknown",
                }
            }
        )
    return out


def build_events(
    *,
    probe: Mapping[str, Any],
    fixture_events: Optional[Path] = None,
    rofl: Optional[Path] = None,
    include_waypoints_from_fixture: bool = True,
) -> Dict[str, Any]:
    if not probe.get("ok"):
        raise DecryptError(
            f"probe not ok (status={probe.get('decryptStatus')}: "
            f"{probe.get('error') or 'acceptance failed'})"
        )

    # Prefer pre-built maknee events from replication decode / probe.
    replication = list(probe.get("replication") or probe.get("events") or [])
    if not replication:
        # Build from accepted hpSnapshot.heroes when present.
        snap = probe.get("hpSnapshot") or {}
        heroes_snap = list(snap.get("heroes") or [])
        acc = acceptance_heroes(heroes_snap)
        if acc["passed"]:
            t0 = float(heroes_snap[0].get("time") or snap.get("time_s") or 0.0)
            replication = maknee_replication_events(time_s=t0, heroes=acc["heroes"])
    if not replication:
        raise DecryptError("probe missing replication events")

    heroes = list(probe.get("heroes") or [])
    waypoint_events: List[dict] = []
    extra_events: List[dict] = []

    if fixture_events is not None:
        src_events = _load_events(fixture_events)
        if not heroes:
            heroes = heroes_from_events(src_events)
        for e in src_events:
            if not isinstance(e, dict):
                continue
            if "Replication" in e:
                # Keep fixture Replication (combat / denser HP) alongside probe snapshot.
                extra_events.append(e)
            elif include_waypoints_from_fixture and (
                "WaypointGroup" in e or "WaypointGroupWithSpeed" in e
            ):
                waypoint_events.append(e)
            else:
                key = next(iter(e), None)
                if key in (
                    "BuyItem",
                    "RemoveItem",
                    "SwapItem",
                    "CastSpellAns",
                    "NPCDieMapView",
                    "NPCDieMapViewBroadcast",
                    "CreateTurret",
                    "CreateNeutral",
                ):
                    extra_events.append(e)
    elif rofl is not None and not heroes:
        heroes = heroes_from_rofl_stats(rofl)

    # If still no CreateHero roster, synthesize from replication net_ids.
    if len(heroes) < 10:
        net_ids = []
        for e in replication:
            if not isinstance(e, dict) or "Replication" not in e:
                continue
            datas = (e["Replication"] or {}).get("net_id_to_replication_datas") or {}
            for nid in datas:
                try:
                    net_ids.append(int(nid))
                except (TypeError, ValueError):
                    continue
        uniq = sorted(set(net_ids))
        if len(uniq) >= 10 and not heroes:
            heroes = [
                {"net_id": nid, "name": f"id{nid}", "champion": "Unknown"}
                for nid in uniq[:10]
            ]

    if len(heroes) < 10:
        raise DecryptError(f"need 10 heroes, got {len(heroes)}")

    t0 = float((probe.get("hpSnapshot") or {}).get("time_s") or 0.0)
    events: List[dict] = []
    events.extend(_create_hero_events(heroes, time_s=0.0))
    events.extend(waypoint_events)
    events.extend(replication)
    events.extend(extra_events)

    # Sort by packet time when present so the mapper samples cleanly.
    def _t(e: dict) -> float:
        if not e:
            return 0.0
        payload = e.get(next(iter(e)))
        if isinstance(payload, dict) and payload.get("time") is not None:
            try:
                return float(payload["time"])
            except (TypeError, ValueError):
                return 0.0
        return 0.0

    events.sort(key=_t)

    build = probe.get("build") or {}
    return {
        "events": events,
        "provenance": {
            "sourceKind": "rofl2_emulator_decrypt",
            "decryptStatus": probe.get("decryptStatus"),
            "backend": probe.get("backend"),
            "roflVersion": build.get("roflVersion"),
            "appVersion": build.get("appVersion"),
            "hpSnapshotTime_s": t0,
            "notes": (
                "Replication HP from decrypt probe; positions from WaypointGroup "
                "when fixture/decoded waypoints are supplied. Ability ranks absent."
            ),
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--probe", type=Path, required=True, help="decrypt probe JSON report")
    ap.add_argument(
        "--fixture-events",
        type=Path,
        default=None,
        help="Optional maknee events for CreateHero/waypoints (fixture path)",
    )
    ap.add_argument(
        "--rofl",
        type=Path,
        default=None,
        help="Optional .rofl for statsJson roster when probe lacks heroes",
    )
    ap.add_argument(
        "--no-fixture-waypoints",
        action="store_true",
        help="Do not copy WaypointGroup packets from --fixture-events",
    )
    ap.add_argument("-o", "--output", type=Path, required=True)
    args = ap.parse_args()

    probe = json.loads(args.probe.read_text(encoding="utf-8"))
    try:
        out = build_events(
            probe=probe,
            fixture_events=args.fixture_events,
            rofl=args.rofl,
            include_waypoints_from_fixture=not args.no_fixture_waypoints,
        )
    except DecryptError as e:
        print(f"emit error: {e}", file=sys.stderr)
        return 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(out) + "\n", encoding="utf-8")
    print(
        f"wrote {args.output} events={len(out['events'])} "
        f"status={out['provenance'].get('decryptStatus')}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
