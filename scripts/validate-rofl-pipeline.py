#!/usr/bin/env python3
"""Validate a canonical rfc461 JSONL stream and its GameTimeline output.

The checks are intentionally provenance-aware: fountain coordinates are valid
only when explicitly marked as placeholders, and never count as live movement.
Use ``--require-live-positions`` for a calculator-safe import gate.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory


def fail(message: str) -> None:
    raise SystemExit(f"FAIL: {message}")


def short_canonical_ms_regression() -> list[int]:
    """Prove short canonical streams are not mistaken for seconds."""
    from jsonl_to_timeline import build_timeline
    from rfc461_emit import (
        coverage_line,
        game_end_line,
        game_info_line,
        participant_row,
        provenance_record,
        stats_update_line,
    )

    expected = list(range(0, 40_001, 1_000))
    roster = [
        {
            "participantID": pid,
            "teamID": 100 if pid <= 5 else 200,
            "championName": "TestChampion",
            "playerName": f"p{pid}",
            "summonerName": f"p{pid}",
        }
        for pid in range(1, 11)
    ]
    with TemporaryDirectory(prefix="rofl-ms-regression-") as tmp:
        path = Path(tmp) / "short.jsonl"
        rows = [
            coverage_line(
                source="short_ms_regression",
                provenance=provenance_record(
                    source="short_ms_regression",
                    source_kind="deterministic_test",
                    position_coverage="full",
                    hp_coverage="full",
                    roster_mapping="game_info_participantID",
                ),
            ),
            game_info_line(game_id=1, participants=roster),
        ]
        for t in expected:
            rows.append(
                stats_update_line(
                    game_id=1,
                    game_time=t,
                    participants=[
                        participant_row(
                            participant_id=pid,
                            team_id=100 if pid <= 5 else 200,
                            champion_name="TestChampion",
                            player_name=f"p{pid}",
                            position={"x": 400 + pid, "z": 400 + pid},
                            position_source="short_ms_regression",
                            health=100,
                            health_max=100,
                        )
                        for pid in range(1, 11)
                    ],
                )
            )
        rows.append(game_end_line(game_id=1, game_time=40_000))
        path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
        timeline = build_timeline(
            path,
            timeline_id="short_ms_regression",
            name="Short millisecond regression",
            patch="test",
        )
    actual = [frame["t"] for frame in timeline["frames"]]
    if actual != expected:
        fail(f"short canonical millisecond regression changed timestamps: {actual}")
    return expected


def validate(jsonl: Path, timeline_path: Path, require_live: bool) -> dict:
    rows = [json.loads(line) for line in jsonl.read_text(encoding="utf-8").splitlines() if line.strip()]
    counts = Counter(row.get("rfc461Schema") for row in rows)
    coverage = next((row for row in rows if row.get("rfc461Schema") == "rofl_coverage"), None)
    info = next((row for row in rows if row.get("rfc461Schema") == "game_info"), None)
    stats = [row for row in rows if row.get("rfc461Schema") == "stats_update"]
    if not info or not stats:
        fail("canonical stream needs game_info and stats_update")
    if not coverage:
        fail("canonical stream is missing rofl_coverage provenance")

    provenance = coverage.get("provenance") or {}
    if provenance.get("gameTimeUnit") != "milliseconds":
        fail("rofl_coverage.provenance.gameTimeUnit must be milliseconds")
    if provenance.get("placeholderPolicy") != "explicit_positionSource_only":
        fail("placeholder policy is missing or unsafe")

    ids = [int(p.get("participantID")) for p in info.get("participants") or []]
    if ids != list(range(1, len(ids) + 1)) or len(ids) != 10:
        fail(f"expected CreateHero/game_info roster IDs 1..10, got {ids}")
    teams = [int(p.get("teamID") or 0) for p in info["participants"]]
    if teams[:5] != [100] * 5 or teams[5:] != [200] * 5:
        fail(f"expected CreateHero order mapped to 5v5 teams, got {teams}")

    times = [int(row.get("gameTime") or 0) for row in stats]
    if any(t2 < t1 for t1, t2 in zip(times, times[1:])):
        fail("stats_update gameTime is not monotonic")
    cadence = [b - a for a, b in zip(times, times[1:]) if b > a]
    if not cadence or max(cadence) > 120_000:
        fail(f"stats_update cadence is not plausible: {cadence[:5]}")

    placeholder_rows = 0
    live_rows = 0
    moving: set[int] = set()
    previous: dict[int, tuple[float, float]] = {}
    hp_samples = 0
    for row in stats:
        participants = row.get("participants") or []
        if len(participants) != 10:
            fail(f"stats_update at {row.get('gameTime')} has {len(participants)} participants")
        for p in participants:
            pid = int(p["participantID"])
            pos = p.get("position") or {}
            x, z = float(pos.get("x", -1)), float(pos.get("z", -1))
            if not (0 <= x <= 15000 and 0 <= z <= 15000):
                fail(f"participant {pid} has out-of-bounds position {(x, z)}")
            source = p.get("positionSource")
            if not source:
                fail(f"participant {pid} is missing explicit positionSource")
            if source == "fountain_placeholder":
                placeholder_rows += 1
            else:
                live_rows += 1
                old = previous.get(pid)
                if old and abs(x - old[0]) + abs(z - old[1]) > 1:
                    moving.add(pid)
            previous[pid] = (x, z)
            has_health = "health" in p or "healthMax" in p
            hp_cov = provenance.get("hpCoverage")
            if hp_cov == "none":
                if has_health:
                    fail(
                        f"participant {pid} includes health under hpCoverage=none "
                        f"(must omit health/healthMax)"
                    )
                if p.get("healthSource") != "unavailable_replay_api":
                    fail(
                        f"participant {pid} healthSource must be "
                        f"'unavailable_replay_api' under hpCoverage=none "
                        f"(got {p.get('healthSource')!r})"
                    )
                if p.get("combatStatsSource") != "unavailable_replay_api":
                    fail(
                        f"participant {pid} combatStatsSource must be "
                        f"'unavailable_replay_api' under hpCoverage=none "
                        f"(got {p.get('combatStatsSource')!r})"
                    )
                if p.get("abilityRanksSource") != "unavailable_replay_api":
                    fail(
                        f"participant {pid} abilityRanksSource must be "
                        f"'unavailable_replay_api' under hpCoverage=none "
                        f"(got {p.get('abilityRanksSource')!r})"
                    )
            else:
                hp, hp_max = float(p.get("health") or 0), float(p.get("healthMax") or 0)
                if hp_max > 1:
                    hp_samples += 1
                if hp < 0 or hp_max < 0 or hp > hp_max + 1e-6:
                    fail(f"participant {pid} has invalid HP {hp}/{hp_max}")

    if require_live and placeholder_rows:
        fail(f"live-position gate found {placeholder_rows} fountain participant rows")
    if provenance.get("positionCoverage") in ("full", "partial", "full_at_sampled_frames") and live_rows == 0:
        fail("coverage claims positions but no participant has a non-placeholder source")
    if provenance.get("positionCoverage") == "none" and live_rows:
        fail("coverage says no positions but participant rows claim live positions")

    timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
    if timeline.get("provenance", {}).get("positionCoverage") != provenance.get("positionCoverage"):
        fail("GameTimeline provenance does not match rfc461 coverage")
    frames = timeline.get("frames") or []
    if len(frames) != counts.get("stats_update", 0):
        fail("GameTimeline frame count does not match stats_update count")
    frame_times = [int(frame.get("t") or 0) for frame in frames]
    if any(b < a for a, b in zip(frame_times, frame_times[1:])):
        fail("GameTimeline frame times are not monotonic milliseconds")
    if frame_times != times:
        fail("GameTimeline frame timestamps do not exactly equal stats_update gameTime values")
    timeline_sources = {u.get("positionSource") for frame in frames for u in frame.get("units") or []}
    if "fountain_placeholder" in timeline_sources and require_live:
        fail("GameTimeline contains fountain placeholders under live-position gate")

    if provenance.get("hpCoverage") == "none":
        for frame in frames:
            for u in frame.get("units") or []:
                if u.get("hpKnown") is not False:
                    fail("hpCoverage=none requires TimelineUnitFrame.hpKnown=false")
                if u.get("combatStatsKnown") is not False:
                    fail("hpCoverage=none requires TimelineUnitFrame.combatStatsKnown=false")
                if u.get("abilityRanksKnown") is not False:
                    fail("hpCoverage=none requires TimelineUnitFrame.abilityRanksKnown=false")
                # Must not look like inferred full HP
                if u.get("hpMax", 0) > 0 and u.get("hp") == u.get("hpMax"):
                    fail("unknown-HP frame must not store full HP as authoritative value")

    return {
        "ok": True,
        "schemas": dict(counts),
        "statsUpdates": len(stats),
        "cadenceMs": sorted(set(cadence))[:8],
        "positionCoverage": provenance.get("positionCoverage"),
        "hpCoverage": provenance.get("hpCoverage"),
        "liveParticipantRows": live_rows,
        "placeholderParticipantRows": placeholder_rows,
        "movingParticipants": sorted(moving),
        "hpSamplesOverOne": hp_samples,
        "timelineFrames": len(frames),
        "timelineDurationMs": timeline.get("durationMs"),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--jsonl", type=Path, required=True)
    ap.add_argument("--timeline", type=Path, required=True)
    ap.add_argument("--require-live-positions", action="store_true")
    args = ap.parse_args()
    for path in (args.jsonl, args.timeline):
        if not path.exists():
            fail(f"missing {path}")
    short_regression = short_canonical_ms_regression()
    result = validate(args.jsonl, args.timeline, args.require_live_positions)
    result["shortMillisecondRegression"] = {
        "ok": True,
        "firstMs": short_regression[1],
        "lastMs": short_regression[-1],
        "frameCount": len(short_regression),
    }
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
