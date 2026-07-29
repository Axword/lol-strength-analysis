#!/usr/bin/env python3
"""Focused tests for ROFL→JSONL speed harness + frame timing aggregation."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Optional

SCRIPTS = Path(__file__).resolve().parents[1]
ROOT = SCRIPTS.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import rfc461_emit  # noqa: E402
import rofl_replay_api_to_jsonl as capture  # noqa: E402
import rofl_speed_bench as bench  # noqa: E402


def _roster(n: int = 10) -> list[dict[str, Any]]:
    rows = []
    for i in range(1, n + 1):
        rows.append(
            {
                "participantID": i,
                "teamID": 100 if i <= 5 else 200,
                "championName": f"Champ{i}",
                "playerName": f"player{i}",
                "summonerName": f"player{i}#tag",
                "riotIdGameName": f"player{i}",
                "riotIdTagLine": "tag",
                "puuid": f"puuid-{i:02d}",
                "role": "NONE",
            }
        )
    return rows


def _participant(
    pid: int,
    *,
    x: float = 1000.0,
    z: float = 2000.0,
    position_source: str = "replay_api_focus_selection",
    health_known: bool = False,
    fabricate_health: bool = False,
    fabricate_combat: bool = False,
    fabricate_ranks: bool = False,
    known_health: bool = False,
    known_combat: bool = False,
    known_ranks: bool = False,
) -> dict[str, Any]:
    """Build a participant via rfc461_emit (actual flat schema)."""
    kwargs: dict[str, Any] = {
        "participant_id": pid,
        "team_id": 100 if pid <= 5 else 200,
        "champion_name": f"Champ{pid}",
        "player_name": f"player{pid}",
        "position": {"x": x + pid, "z": z + pid},
        "position_source": position_source,
        "health_known": False,
        "health_source": "unavailable_replay_api",
        "combat_stats_source": "unavailable_replay_api",
        "ability_ranks_source": "unavailable_replay_api",
        "ability_levels": (0, 0, 0, 0),
    }
    if known_health or fabricate_health:
        # Known-health product shape: health/healthMax present.
        kwargs["health_known"] = True
        kwargs["health"] = 500.0
        kwargs["health_max"] = 1000.0
        if fabricate_health:
            kwargs["health_source"] = "unavailable_replay_api"
        else:
            kwargs["health_source"] = None
    if known_combat:
        kwargs["combat_stats_source"] = "replication_decode"
        kwargs["attack_damage"] = 100.0
        kwargs["ability_power"] = 20.0
        kwargs["armor"] = 40.0
        kwargs["magic_resist"] = 30.0
        kwargs["attack_speed"] = 1.1
    if fabricate_combat:
        kwargs["combat_stats_source"] = "unavailable_replay_api"
        kwargs["attack_damage"] = 100.0
        kwargs["ability_power"] = 0.0
        kwargs["armor"] = 40.0
        kwargs["magic_resist"] = 30.0
        kwargs["attack_speed"] = 0.7
    if known_ranks:
        kwargs["ability_ranks_source"] = "skill_level_up"
        kwargs["ability_levels"] = (5, 3, 1, 2)
    if fabricate_ranks:
        kwargs["ability_ranks_source"] = "unavailable_replay_api"
        kwargs["ability_levels"] = (5, 0, 0, 1)
    return rfc461_emit.participant_row(**kwargs)


def _stream(
    *,
    times: Optional[list[int]] = None,
    fountain: bool = False,
    fabricate_health: bool = False,
    fabricate_combat: bool = False,
    fabricate_ranks: bool = False,
    known_health: bool = False,
    known_combat: bool = False,
    known_ranks: bool = False,
    drop_coverage: bool = False,
    roster_n: int = 10,
) -> list[dict[str, Any]]:
    times = times or [60_000, 61_000, 62_000]
    roster = _roster(roster_n)
    rows: list[dict[str, Any]] = []
    if not drop_coverage:
        rows.append(
            rfc461_emit.coverage_line(
                source="test",
                game_id=3264361042,
                decoded=["positions"],
                missing=["health"],
                provenance=rfc461_emit.provenance_record(
                    source="test",
                    source_kind="test",
                    position_coverage="full_at_sampled_frames",
                    hp_coverage="none",
                    roster_mapping="stable_puuid_or_full_riot_id",
                    artifact="test",
                ),
                extra={"roflGameLengthMs": 1_625_998},
            )
        )
    rows.append(
        rfc461_emit.game_info_line(
            game_id=3264361042,
            participants=[
                {
                    "participantID": p["participantID"],
                    "teamID": p["teamID"],
                    "championName": p["championName"],
                    "playerName": p["playerName"],
                    "summonerName": p["summonerName"],
                    "riotIdGameName": p["riotIdGameName"],
                    "riotIdTagLine": p["riotIdTagLine"],
                    "puuid": p["puuid"],
                    "role": p["role"],
                }
                for p in roster
            ],
            game_name="3264361042",
            game_version="16.14",
            platform_id="BR1",
            stats_update_interval_ms=1000,
        )
    )
    for t in times:
        rows.append(
            rfc461_emit.stats_update_line(
                game_id=3264361042,
                game_time=t,
                participants=[
                    _participant(
                        p["participantID"],
                        position_source=(
                            "fountain_placeholder"
                            if fountain
                            else "replay_api_focus_selection"
                        ),
                        fabricate_health=fabricate_health,
                        fabricate_combat=fabricate_combat,
                        fabricate_ranks=fabricate_ranks,
                        known_health=known_health,
                        known_combat=known_combat,
                        known_ranks=known_ranks,
                    )
                    for p in roster
                ],
            )
        )
    return rows


class MetricMathTests(unittest.TestCase):
    def test_baseline_ms_per_frame_and_wall_per_match_minute(self) -> None:
        metrics = bench.compute_speed_metrics(
            wall_ms=1566 * 1686.766,
            stats_update_count=1566,
            match_duration_ms=1_625_998,
        )
        self.assertEqual(metrics["statsUpdateCount"], 1566)
        self.assertAlmostEqual(metrics["msPerOutputFrame"], 1686.766, places=3)
        self.assertAlmostEqual(metrics["wallMs"], 2_641_475.556, places=3)
        self.assertAlmostEqual(
            metrics["wallSecondsPerMatchMinute"], 97.471543, places=5
        )

    def test_target_math_60s_and_100x(self) -> None:
        n = 1566
        self.assertAlmostEqual(60_000 / n, 38.314176, places=5)
        self.assertAlmostEqual(26_400 / n, 16.858238, places=5)

    def test_metrics_fail_closed_on_empty_output(self) -> None:
        with self.assertRaises(bench.SpeedBenchError):
            bench.compute_speed_metrics(wall_ms=1000, stats_update_count=0)


class QualityGateTests(unittest.TestCase):
    def test_passing_stream(self) -> None:
        gates = bench.evaluate_quality_gates(_stream(), step_ms=1000)
        self.assertTrue(gates["ok"], gates["failures"])
        self.assertEqual(gates["statsUpdateCount"], 3)
        self.assertEqual(gates["fountainPlaceholders"], 0)
        self.assertTrue(gates["identityStable"])
        self.assertTrue(gates["cadenceOk"])
        self.assertTrue(gates["noFabrication"])
        # Neutral Replay API storage: no health/combat overrides, zero ranks.
        sample = next(
            p
            for row in _stream()
            if row.get("rfc461Schema") == "stats_update"
            for p in row["participants"]
        )
        self.assertNotIn("health", sample)
        self.assertNotIn("healthMax", sample)
        self.assertNotIn("attackDamage", sample)
        self.assertEqual(sample["ability1Level"], 0)
        self.assertEqual(sample["abilityRanksSource"], "unavailable_replay_api")

    def test_fountain_placeholder_fails(self) -> None:
        gates = bench.evaluate_quality_gates(_stream(fountain=True))
        self.assertFalse(gates["ok"])
        self.assertGreater(gates["fountainPlaceholders"], 0)

    def test_off_grid_cadence_fails(self) -> None:
        gates = bench.evaluate_quality_gates(
            _stream(times=[60_000, 61_500, 63_000]),
            step_ms=1000,
        )
        self.assertFalse(gates["ok"])
        self.assertFalse(gates["cadenceOk"])

    def test_health_fabrication_fails(self) -> None:
        gates = bench.evaluate_quality_gates(_stream(fabricate_health=True))
        self.assertFalse(gates["ok"])
        self.assertFalse(gates["noFabrication"])
        self.assertTrue(
            any("health/healthMax" in f for f in gates["failures"]),
            gates["failures"],
        )

    def test_combat_fabrication_flat_fields_fails(self) -> None:
        gates = bench.evaluate_quality_gates(_stream(fabricate_combat=True))
        self.assertFalse(gates["ok"])
        self.assertFalse(gates["noFabrication"])
        self.assertTrue(
            any("combat fields" in f for f in gates["failures"]),
            gates["failures"],
        )

    def test_ability_rank_fabrication_fails(self) -> None:
        gates = bench.evaluate_quality_gates(_stream(fabricate_ranks=True))
        self.assertFalse(gates["ok"])
        self.assertFalse(gates["noFabrication"])
        self.assertTrue(
            any("non-zero ability levels" in f for f in gates["failures"]),
            gates["failures"],
        )

    def test_ability_rank_alias_under_unavailable_fails(self) -> None:
        rows = _stream()
        for row in rows:
            if row.get("rfc461Schema") != "stats_update":
                continue
            row["participants"][0]["abilityRanks"] = {"q": 5, "w": 0, "e": 0, "r": 1}
        gates = bench.evaluate_quality_gates(rows)
        self.assertFalse(gates["ok"])
        self.assertTrue(any("rank alias" in f for f in gates["failures"]))

    def test_known_health_combat_ranks_allowed(self) -> None:
        gates = bench.evaluate_quality_gates(
            _stream(known_health=True, known_combat=True, known_ranks=True)
        )
        self.assertTrue(gates["ok"], gates["failures"])
        self.assertTrue(gates["noFabrication"])

    def test_malformed_missing_coverage_fails_closed(self) -> None:
        gates = bench.evaluate_quality_gates(_stream(drop_coverage=True))
        self.assertFalse(gates["ok"])
        self.assertIn("missing rofl_coverage", gates["failures"])

    def test_wrong_roster_size_fails(self) -> None:
        gates = bench.evaluate_quality_gates(_stream(roster_n=9))
        self.assertFalse(gates["ok"])
        self.assertFalse(gates["identityStable"])


class OracleComparisonTests(unittest.TestCase):
    def test_oracle_within_tolerance_passes(self) -> None:
        candidate = _stream()
        oracle = _stream()
        gates = bench.evaluate_quality_gates(
            candidate,
            oracle_rows=oracle,
            oracle_tolerance=1.0,
        )
        self.assertTrue(gates["ok"], gates["failures"])
        self.assertEqual(gates["oracle"]["compared"], 30)

    def test_oracle_position_drift_fails(self) -> None:
        candidate = _stream()
        oracle = _stream()
        # Nudge one candidate coordinate far away.
        for row in candidate:
            if row.get("rfc461Schema") != "stats_update":
                continue
            row["participants"][0]["position"]["x"] += 500.0
            break
        gates = bench.evaluate_quality_gates(
            candidate,
            oracle_rows=oracle,
            oracle_tolerance=50.0,
        )
        self.assertFalse(gates["ok"])
        self.assertFalse(gates["oracle"]["ok"])


class RunLogTests(unittest.TestCase):
    def test_append_only_jsonl_log(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            log = Path(td) / "speed-runs.jsonl"
            first = bench.build_run_record(
                run_id="r1",
                match_code="3264361042",
                backend="eval-jsonl",
                hypothesis="a",
                diff_label="d1",
                budget_seconds=60,
                metrics={"wallMs": 1.0, "statsUpdateCount": 1, "msPerOutputFrame": 1.0},
                quality_gates={"ok": True},
                keep="keep",
                reason="ok",
            )
            second = bench.build_run_record(
                run_id="r2",
                match_code="3264361042",
                backend="command",
                hypothesis="b",
                diff_label="d2",
                budget_seconds=60,
                metrics=None,
                quality_gates={"ok": False, "failures": ["x"]},
                keep="discard",
                reason="x",
            )
            bench.append_run_record(log, first)
            bench.append_run_record(log, second)
            lines = log.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 2)
            self.assertEqual(json.loads(lines[0])["runId"], "r1")
            self.assertEqual(json.loads(lines[1])["keep"], "discard")


class TimeoutDiscardTests(unittest.TestCase):
    def test_budget_timeout_discards(self) -> None:
        result = bench.run_command_with_budget(
            [sys.executable, "-c", "import time; time.sleep(2)"],
            budget_seconds=0.2,
        )
        self.assertTrue(result["timedOut"])
        self.assertFalse(result["ok"])
        keep, reason = bench.decide_keep(
            gates_ok=True,
            timed_out=True,
            command_ok=False,
            reason_parts=["budget exceeded"],
        )
        self.assertEqual(keep, "discard")
        self.assertEqual(reason, "budget exceeded")

    def test_fast_command_ok(self) -> None:
        result = bench.run_command_with_budget(
            [sys.executable, "-c", "print('ok')"],
            budget_seconds=5.0,
        )
        self.assertFalse(result["timedOut"])
        self.assertTrue(result["ok"])

    def test_eval_jsonl_does_not_mutate(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "events.jsonl"
            rows = _stream()
            original = "\n".join(json.dumps(r) for r in rows) + "\n"
            path.write_text(original, encoding="utf-8")
            before = path.read_bytes()
            result = bench.evaluate_existing_jsonl(
                path,
                wall_ms=3000.0,
                match_duration_ms=1_625_998,
            )
            after = path.read_bytes()
            self.assertEqual(before, after)
            self.assertFalse(result["mutated"])
            self.assertTrue(result["qualityGates"]["ok"])
            self.assertAlmostEqual(result["metrics"]["msPerOutputFrame"], 1000.0)

    def test_timeout_partial_jsonl_scores_durable_rows_but_discards(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "partial.jsonl"
            expected = [60_000, 61_000, 62_000]
            # Only first two frames completed before "timeout".
            rows = _stream(times=expected[:2])
            out.write_text(
                "\n".join(json.dumps(r) for r in rows) + "\n",
                encoding="utf-8",
            )
            # Simulate a slow command that will be killed after partial output exists.
            cmd = [
                sys.executable,
                "-c",
                (
                    "import time; time.sleep(2)"
                ),
            ]
            # Pre-write output, then timeout the noop sleeper.
            result = bench.run_command_with_budget(cmd, budget_seconds=0.2)
            self.assertTrue(result["timedOut"])
            eval_result = bench.evaluate_existing_jsonl(
                out,
                wall_ms=float(result["wallMs"]),
                step_ms=1000,
                expected_times_ms=expected,
                tolerate_truncated_tail=True,
                partial=True,
            )
            gates = eval_result["qualityGates"]
            self.assertFalse(gates["ok"])
            self.assertTrue(gates["partial"])
            self.assertFalse(gates["completedExpectedSchedule"])
            self.assertEqual(gates["statsUpdateCount"], 2)
            self.assertIsNotNone(eval_result["metrics"])
            self.assertTrue(eval_result["metrics"]["partial"])
            keep, reason = bench.decide_keep(
                gates_ok=bool(gates.get("ok")),
                timed_out=True,
                command_ok=False,
                reason_parts=["budget exceeded"],
            )
            self.assertEqual(keep, "discard")
            self.assertEqual(reason, "budget exceeded")

    def test_truncated_tail_tolerated_midfile_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "events.jsonl"
            rows = _stream(times=[60_000, 61_000])
            good = "\n".join(json.dumps(r) for r in rows) + "\n"
            path.write_text(good + '{"rfc461Schema":"stats_update","gameTime":', encoding="utf-8")
            loaded = bench._load_jsonl(path, tolerate_truncated_tail=True)
            self.assertEqual(
                len([r for r in loaded if r.get("rfc461Schema") == "stats_update"]),
                2,
            )
            # Mid-file corruption must still fail closed.
            broken = (
                json.dumps(rows[0])
                + "\n"
                + "{not-json\n"
                + json.dumps(rows[1])
                + "\n"
            )
            path.write_text(broken, encoding="utf-8")
            with self.assertRaises(bench.SpeedBenchError):
                bench._load_jsonl(path, tolerate_truncated_tail=True)


class TimingAggregationTests(unittest.TestCase):
    def test_percentile_and_stage_summary(self) -> None:
        values = [10.0, 20.0, 30.0, 40.0, 100.0]
        self.assertEqual(capture._percentile(values, 50), 30.0)
        self.assertEqual(capture._percentile(values, 95), 88.0)
        summary = capture._stage_timing_summary(values)
        self.assertEqual(summary["count"], 5)
        self.assertEqual(summary["totalMs"], 200.0)
        self.assertEqual(summary["meanMs"], 40.0)
        self.assertEqual(summary["maxMs"], 100.0)

    def test_summarize_frame_timings_includes_stages_and_http(self) -> None:
        frames = [
            {
                "frameMs": 100.0,
                "seekMs": 10.0,
                "focusAssertMs": 5.0,
                "liveclientWaitMs": 20.0,
                "selectMs": 60.0,
                "emitMs": 5.0,
                "totalFrameMs": 100.0,
                "httpCounts": {"GET /replay/playback": 2, "POST /replay/render": 1},
            },
            {
                "frameMs": 200.0,
                "seekMs": 30.0,
                "focusAssertMs": 5.0,
                "liveclientWaitMs": 40.0,
                "selectMs": 120.0,
                "emitMs": 5.0,
                "totalFrameMs": 200.0,
                "httpCounts": {"GET /replay/playback": 1, "GET /liveclientdata/playerlist": 2},
            },
        ]
        summary = capture.summarize_frame_timings(frames)
        self.assertEqual(summary["frameCount"], 2)
        self.assertEqual(summary["averageFrameMs"], 150.0)
        self.assertEqual(summary["p50FrameMs"], 150.0)
        self.assertEqual(summary["maxFrameMs"], 200.0)
        self.assertTrue(summary["comparisonOnly"])
        self.assertFalse(summary["machineSpecificAssertion"])
        self.assertEqual(summary["stages"]["seekMs"]["totalMs"], 40.0)
        self.assertEqual(summary["stages"]["selectMs"]["meanMs"], 90.0)
        self.assertEqual(summary["httpCounts"]["GET /replay/playback"], 3)
        self.assertEqual(summary["httpCounts"]["POST /replay/render"], 1)

    def test_counting_transport_tallies_endpoints(self) -> None:
        calls: list[tuple[str, str]] = []

        def fake(method: str, url: str, *, body=None, timeout: float):
            calls.append((method, url))
            return {"ok": True, "body": {}}

        counter = capture.CountingTransport(fake)
        counter("GET", "https://127.0.0.1:2999/replay/playback", timeout=0.1)
        counter("POST", "https://127.0.0.1:2999/replay/render", body={}, timeout=0.1)
        counter("GET", "https://127.0.0.1:2999/liveclientdata/playerlist", timeout=0.1)
        snap = counter.snapshot()
        self.assertEqual(snap["GET /replay/playback"], 1)
        self.assertEqual(snap["POST /replay/render"], 1)
        self.assertEqual(snap["GET /liveclientdata/playerlist"], 1)
        self.assertEqual(len(calls), 3)

    def test_replay_api_command_uses_guarded_cli(self) -> None:
        cmd = bench.build_replay_api_command(
            rofl=Path("/tmp/BR1-3264361042.rofl"),
            out=Path("/tmp/out.jsonl"),
            start_ms=60_000,
            end_ms=119_000,
            step_ms=1000,
        )
        self.assertIn("rofl_replay_api_to_jsonl.py", cmd[1])
        self.assertIn("--start-ms", cmd)
        self.assertIn("60000", cmd)


class SampleScheduleClampTests(unittest.TestCase):
    def test_resolve_sample_schedule_clamps_to_game_length(self) -> None:
        schedule = capture.resolve_sample_schedule_ms(
            121_000,
            124_000,
            1000,
            rofl_game_length_ms=122_500,
        )
        self.assertEqual(schedule["sampleTimesMs"], [121_000, 122_000])
        self.assertEqual(schedule["requestedEndMs"], 124_000)
        self.assertEqual(schedule["scheduleEndMs"], 122_500)
        self.assertEqual(schedule["effectiveEndMs"], 122_000)
        self.assertEqual(schedule["roflGameLengthMs"], 122_500)

    def test_expected_replay_api_times_use_shared_clamp(self) -> None:
        times = bench.expected_replay_api_sample_times_ms(
            rofl_path=Path("/tmp/unused.rofl"),
            start_ms=121_000,
            end_ms=124_000,
            step_ms=1000,
            rofl_game_length_ms=122_500,
        )
        self.assertEqual(times, [121_000, 122_000])
        # Exact clamped schedule must pass cadence gates.
        gates = bench.evaluate_quality_gates(
            _stream(times=times),
            step_ms=1000,
            expected_times_ms=times,
        )
        self.assertTrue(gates["ok"], gates["failures"])

    def test_unclamped_requested_end_would_fail_against_clamped_output(self) -> None:
        clamped = [121_000, 122_000]
        naive = list(range(121_000, 124_000 + 1, 1000))
        gates = bench.evaluate_quality_gates(
            _stream(times=clamped),
            step_ms=1000,
            expected_times_ms=naive,
        )
        self.assertFalse(gates["ok"])
        self.assertFalse(gates["cadenceOk"])


class HistoricalBaselineRecordTests(unittest.TestCase):
    def test_speed_runs_baseline_row(self) -> None:
        path = ROOT / "docs/rofl-research/speed-runs.jsonl"
        self.assertTrue(path.is_file())
        row = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(row["source"], "historical_checkpoint")
        self.assertEqual(row["matchCode"], "3264361042")
        self.assertEqual(row["metrics"]["statsUpdateCount"], 1566)
        self.assertAlmostEqual(row["metrics"]["msPerOutputFrame"], 1686.766)
        self.assertTrue(row["qualityGates"]["ok"])
        self.assertEqual(row["qualityGates"]["fountainPlaceholders"], 0)
        self.assertEqual(row["keep"], "keep")


if __name__ == "__main__":
    unittest.main()
