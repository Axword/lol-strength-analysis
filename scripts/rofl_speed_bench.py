#!/usr/bin/env python3
"""Autoresearch-style fixed-budget ROFL → rfc461 JSONL speed harness.

Modes:
  --eval-jsonl PATH     Evaluate an existing rfc461 artifact (no mutation).
  --command CMD...      Wrap an arbitrary backend command under a wall budget.
  --replay-api          Bounded-window Replay API capture via the guarded path.
  --offline-command     Offline decode/emit hook for later packet experiments.

Every run appends one canonical JSON object to ``--log`` (default
``docs/rofl-research/speed-runs.jsonl``). Timing assertions never decide
correctness; quality gates do.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import shlex
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = Path(__file__).resolve().parent
DEFAULT_LOG = ROOT / "docs/rofl-research/speed-runs.jsonl"
DEFAULT_BUDGET_SECONDS = 60.0
DEFAULT_STEP_MS = 1000
DEFAULT_ORACLE_TOLERANCE = 50.0
UNAVAILABLE_SOURCES = frozenset(
    {
        "unavailable_replay_api",
        "unavailable",
        "unknown",
        "none",
    }
)
# Flat combat overrides written by rfc461_emit.participant_row.
COMBAT_OVERRIDE_FIELDS = (
    "attackDamage",
    "abilityPower",
    "armor",
    "magicResist",
    "attackSpeed",
)
ABILITY_LEVEL_FIELDS = (
    "ability1Level",
    "ability2Level",
    "ability3Level",
    "ability4Level",
)
# Non-flat rank aliases that must not appear under unavailable ranks.
ABILITY_RANK_ALIASES = (
    "abilityRanks",
    "abilityLevels",
    "abilityRank",
)


class SpeedBenchError(RuntimeError):
    """Harness failure (budget, gates, or malformed input)."""


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def new_run_id() -> str:
    return f"speed-{uuid.uuid4().hex[:12]}"


def compute_speed_metrics(
    *,
    wall_ms: float,
    stats_update_count: int,
    match_duration_ms: Optional[float] = None,
) -> dict[str, Any]:
    """Primary + secondary speed metrics. Fail closed on empty output."""
    if stats_update_count <= 0:
        raise SpeedBenchError("stats_update count must be > 0 for speed metrics")
    if wall_ms < 0:
        raise SpeedBenchError("wall_ms must be >= 0")
    ms_per_frame = float(wall_ms) / float(stats_update_count)
    wall_seconds_per_match_minute: Optional[float] = None
    if match_duration_ms is not None:
        if match_duration_ms <= 0:
            raise SpeedBenchError("match_duration_ms must be > 0 when supplied")
        match_minutes = float(match_duration_ms) / 60_000.0
        wall_seconds_per_match_minute = (float(wall_ms) / 1000.0) / match_minutes
    return {
        "wallMs": round(float(wall_ms), 3),
        "statsUpdateCount": int(stats_update_count),
        "msPerOutputFrame": round(ms_per_frame, 3),
        "wallSecondsPerMatchMinute": (
            round(wall_seconds_per_match_minute, 6)
            if wall_seconds_per_match_minute is not None
            else None
        ),
        "matchDurationMs": (
            int(match_duration_ms) if match_duration_ms is not None else None
        ),
    }


def _load_jsonl(
    path: Path,
    *,
    tolerate_truncated_tail: bool = False,
) -> list[dict[str, Any]]:
    """Load rfc461 JSONL rows.

    When ``tolerate_truncated_tail`` is true (timeout/partial diagnostics only),
    a malformed **final** non-empty line is skipped and durable prior rows are
    kept. Any earlier malformed line still fails closed.
    """
    if not path.is_file():
        raise SpeedBenchError(f"JSONL not found: {path}")
    raw_lines = path.read_text(encoding="utf-8").splitlines()
    # Identify last non-empty line index for truncated-tail tolerance.
    last_nonempty = -1
    for idx, line in enumerate(raw_lines):
        if line.strip():
            last_nonempty = idx

    rows: list[dict[str, Any]] = []
    for line_no, line in enumerate(raw_lines, start=1):
        text = line.strip()
        if not text:
            continue
        try:
            row = json.loads(text)
        except json.JSONDecodeError as exc:
            if tolerate_truncated_tail and (line_no - 1) == last_nonempty:
                # Concurrent writer / SIGTERM mid-line: keep durable prefix only.
                break
            raise SpeedBenchError(
                f"malformed JSONL at {path}:{line_no}: {exc}"
            ) from exc
        if not isinstance(row, dict):
            if tolerate_truncated_tail and (line_no - 1) == last_nonempty:
                break
            raise SpeedBenchError(
                f"malformed JSONL at {path}:{line_no}: expected object"
            )
        rows.append(row)
    if not rows:
        raise SpeedBenchError(f"empty JSONL artifact: {path}")
    return rows


def _participant_identity_key(row: Mapping[str, Any]) -> str:
    puuid = str(row.get("puuid") or "").strip()
    if puuid:
        return f"puuid:{puuid}"
    game = str(row.get("riotIdGameName") or "").strip()
    tag = str(row.get("riotIdTagLine") or "").strip()
    if game and tag:
        return f"riotid:{game.casefold()}#{tag.casefold()}"
    summoner = str(row.get("summonerName") or "").strip()
    if "#" in summoner:
        return f"riotid:{summoner.casefold()}"
    player = str(row.get("playerName") or "").strip()
    if player:
        return f"name:{player.casefold()}"
    return ""


def _is_unavailable_source(value: Any) -> bool:
    text = str(value or "").strip().casefold()
    return text in UNAVAILABLE_SOURCES or text.startswith("unavailable")


def _check_no_fabrication(participant: Mapping[str, Any], *, frame_ms: int) -> list[str]:
    """Reject fabricated HP/combat/ranks against the flat rfc461 participant shape.

    Neutral product storage is allowed:
    - omit ``health``/``healthMax`` with ``healthSource=unavailable_*``
    - omit flat combat overrides with ``combatStatsSource=unavailable_*``
    - keep ``ability1Level..ability4Level`` at 0 with ``abilityRanksSource=unavailable_*``
    - emit known ``health``/``healthMax`` when source is absent or honestly known
    """
    errors: list[str] = []
    pid = participant.get("participantID")

    health_source = participant.get("healthSource")
    has_health = "health" in participant or "healthMax" in participant
    if has_health and _is_unavailable_source(health_source):
        errors.append(
            f"t={frame_ms} pid={pid}: health/healthMax present under "
            f"unavailable healthSource={health_source!r}"
        )

    combat_source = participant.get("combatStatsSource")
    combat_unavailable = combat_source is None or _is_unavailable_source(combat_source)
    present_combat = [key for key in COMBAT_OVERRIDE_FIELDS if key in participant]
    if present_combat and combat_unavailable:
        errors.append(
            f"t={frame_ms} pid={pid}: combat fields {present_combat} present under "
            f"unavailable/unknown combatStatsSource={combat_source!r}"
        )
    if "combatStats" in participant and combat_unavailable:
        errors.append(
            f"t={frame_ms} pid={pid}: nested combatStats present under "
            f"unavailable/unknown combatStatsSource={combat_source!r}"
        )

    ranks_source = participant.get("abilityRanksSource")
    ranks_unavailable = ranks_source is None or _is_unavailable_source(ranks_source)
    if ranks_unavailable:
        nonzero_levels = []
        for key in ABILITY_LEVEL_FIELDS:
            try:
                level = int(participant.get(key) or 0)
            except (TypeError, ValueError):
                nonzero_levels.append(key)
                continue
            if level != 0:
                nonzero_levels.append(f"{key}={level}")
        if nonzero_levels:
            errors.append(
                f"t={frame_ms} pid={pid}: non-zero ability levels {nonzero_levels} "
                f"under unavailable/unknown abilityRanksSource={ranks_source!r}"
            )
        for alias in ABILITY_RANK_ALIASES:
            if alias in participant:
                errors.append(
                    f"t={frame_ms} pid={pid}: rank alias {alias!r} present under "
                    f"unavailable/unknown abilityRanksSource={ranks_source!r}"
                )
    return errors


def evaluate_quality_gates(
    rows: Sequence[Mapping[str, Any]],
    *,
    step_ms: int = DEFAULT_STEP_MS,
    expected_times_ms: Optional[Sequence[int]] = None,
    oracle_rows: Optional[Sequence[Mapping[str, Any]]] = None,
    oracle_tolerance: float = DEFAULT_ORACLE_TOLERANCE,
) -> dict[str, Any]:
    """Hard quality gates. Fail closed on malformed/incomplete artifacts."""
    failures: list[str] = []
    coverage = next((r for r in rows if r.get("rfc461Schema") == "rofl_coverage"), None)
    info = next((r for r in rows if r.get("rfc461Schema") == "game_info"), None)
    stats = [r for r in rows if r.get("rfc461Schema") == "stats_update"]

    if coverage is None:
        failures.append("missing rofl_coverage")
    if info is None:
        failures.append("missing game_info")
    if not stats:
        failures.append("missing stats_update rows")
    if failures:
        return {
            "ok": False,
            "failures": failures,
            "statsUpdateCount": len(stats),
            "fountainPlaceholders": 0,
            "identityStable": False,
            "cadenceOk": False,
            "noFabrication": False,
            "oracle": None,
        }

    roster = list(info.get("participants") or [])
    if len(roster) != 10:
        failures.append(f"game_info roster size {len(roster)} != 10")
    roster_ids = [int(p.get("participantID") or 0) for p in roster]
    if roster_ids != list(range(1, 11)):
        failures.append(f"game_info participantIDs not 1..10: {roster_ids}")

    identity_by_pid: dict[int, str] = {}
    for p in roster:
        pid = int(p.get("participantID") or 0)
        key = _participant_identity_key(p)
        if not key:
            failures.append(f"game_info pid={pid} lacks stable identity")
            continue
        identity_by_pid[pid] = key
    if len(set(identity_by_pid.values())) != len(identity_by_pid):
        failures.append("game_info identities are not unique")

    fountain = 0
    times: list[int] = []
    identity_stable = True
    no_fabrication = True

    for row in stats:
        try:
            t_ms = int(row.get("gameTime"))
        except (TypeError, ValueError):
            failures.append(f"stats_update missing/invalid gameTime: {row.get('gameTime')!r}")
            identity_stable = False
            continue
        times.append(t_ms)
        participants = list(row.get("participants") or [])
        if len(participants) != 10:
            failures.append(f"t={t_ms}: expected 10 participants, got {len(participants)}")
            identity_stable = False
            continue
        seen_pids: set[int] = set()
        for p in participants:
            try:
                pid = int(p.get("participantID"))
            except (TypeError, ValueError):
                failures.append(f"t={t_ms}: invalid participantID")
                identity_stable = False
                continue
            if pid in seen_pids:
                failures.append(f"t={t_ms}: duplicate participantID {pid}")
                identity_stable = False
            seen_pids.add(pid)
            if pid not in identity_by_pid:
                failures.append(f"t={t_ms}: participantID {pid} not in game_info roster")
                identity_stable = False
            if p.get("positionSource") == "fountain_placeholder":
                fountain += 1
            for err in _check_no_fabrication(p, frame_ms=t_ms):
                no_fabrication = False
                failures.append(err)
        if seen_pids != set(range(1, 11)):
            failures.append(f"t={t_ms}: participantID set {sorted(seen_pids)} != 1..10")
            identity_stable = False

    if fountain:
        failures.append(f"fountain_placeholder rows: {fountain}")

    cadence_ok = True
    if any(b < a for a, b in zip(times, times[1:])):
        cadence_ok = False
        failures.append("stats_update gameTime is not monotonic")

    expected = list(expected_times_ms) if expected_times_ms is not None else None
    if expected is None and times:
        if step_ms <= 0:
            failures.append("step_ms must be > 0")
            cadence_ok = False
        else:
            expected = list(range(times[0], times[0] + step_ms * len(times), step_ms))
    if expected is not None:
        if times != [int(x) for x in expected]:
            cadence_ok = False
            failures.append(
                "stats_update times are not on the requested cadence grid "
                f"(got {len(times)} frames, expected {len(expected)})"
            )

    oracle_report: Optional[dict[str, Any]] = None
    if oracle_rows is not None:
        oracle_report = compare_positions_to_oracle(
            stats,
            oracle_rows,
            tolerance=oracle_tolerance,
        )
        if not oracle_report.get("ok"):
            failures.extend(list(oracle_report.get("failures") or []))

    ok = (
        not failures
        and identity_stable
        and fountain == 0
        and cadence_ok
        and no_fabrication
        and (oracle_report is None or bool(oracle_report.get("ok")))
    )
    return {
        "ok": ok,
        "failures": failures,
        "statsUpdateCount": len(stats),
        "fountainPlaceholders": fountain,
        "identityStable": identity_stable and len(identity_by_pid) == 10,
        "cadenceOk": cadence_ok,
        "noFabrication": no_fabrication,
        "oracle": oracle_report,
        "firstMs": times[0] if times else None,
        "lastMs": times[-1] if times else None,
        "stepMs": step_ms,
    }


def compare_positions_to_oracle(
    candidate_stats: Sequence[Mapping[str, Any]],
    oracle_rows: Sequence[Mapping[str, Any]],
    *,
    tolerance: float = DEFAULT_ORACLE_TOLERANCE,
) -> dict[str, Any]:
    """Optional sparse position QA against an oracle rfc461 stream."""
    failures: list[str] = []
    oracle_stats = [r for r in oracle_rows if r.get("rfc461Schema") == "stats_update"]
    by_time: dict[int, Mapping[str, Any]] = {}
    for row in oracle_stats:
        try:
            by_time[int(row["gameTime"])] = row
        except (KeyError, TypeError, ValueError):
            failures.append("oracle stats_update missing gameTime")
    if not by_time:
        return {"ok": False, "failures": ["oracle has no stats_update rows"], "compared": 0}

    errors: list[float] = []
    compared = 0
    for row in candidate_stats:
        try:
            t_ms = int(row["gameTime"])
        except (KeyError, TypeError, ValueError):
            continue
        oracle = by_time.get(t_ms)
        if oracle is None:
            continue
        cand_by_pid = {
            int(p["participantID"]): p for p in (row.get("participants") or [])
        }
        for op in oracle.get("participants") or []:
            pid = int(op["participantID"])
            cp = cand_by_pid.get(pid)
            if cp is None:
                failures.append(f"oracle t={t_ms} pid={pid}: missing in candidate")
                continue
            opos = op.get("position") or {}
            cpos = cp.get("position") or {}
            try:
                dx = float(cpos["x"]) - float(opos["x"])
                dz = float(cpos["z"]) - float(opos["z"])
            except (KeyError, TypeError, ValueError):
                failures.append(f"oracle t={t_ms} pid={pid}: missing position")
                continue
            dist = math.hypot(dx, dz)
            errors.append(dist)
            compared += 1
            if dist > float(tolerance):
                failures.append(
                    f"oracle t={t_ms} pid={pid}: distance {dist:.1f} > tol {tolerance}"
                )

    if compared == 0:
        failures.append("no overlapping gameTime frames for oracle comparison")
    errors_sorted = sorted(errors)
    median = (
        errors_sorted[len(errors_sorted) // 2] if errors_sorted else None
    )
    return {
        "ok": not failures,
        "failures": failures,
        "compared": compared,
        "tolerance": float(tolerance),
        "medianError": round(median, 3) if median is not None else None,
        "maxError": round(max(errors), 3) if errors else None,
    }


def append_run_record(log_path: Path, record: Mapping[str, Any]) -> None:
    """Append one canonical JSON object; never rewrite prior runs."""
    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(dict(record), ensure_ascii=False, separators=(",", ":"))
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")
        fh.flush()
        try:
            os.fsync(fh.fileno())
        except OSError:
            pass


def decide_keep(
    *,
    gates_ok: bool,
    timed_out: bool,
    command_ok: bool,
    reason_parts: Sequence[str],
) -> tuple[str, str]:
    if timed_out:
        return "discard", "budget exceeded"
    if not command_ok:
        return "discard", "; ".join(reason_parts) or "command failed"
    if not gates_ok:
        return "discard", "; ".join(reason_parts) or "quality gates failed"
    return "keep", "; ".join(reason_parts) or "gates passed within budget"


def run_command_with_budget(
    command: Sequence[str],
    *,
    budget_seconds: float,
    cwd: Optional[Path] = None,
    env: Optional[Mapping[str, str]] = None,
) -> dict[str, Any]:
    """Run a command under a hard wall-clock budget (timeout → discard)."""
    if budget_seconds <= 0:
        raise SpeedBenchError("budget_seconds must be > 0")
    if not command:
        raise SpeedBenchError("command is empty")
    started = time.perf_counter()
    timed_out = False
    returncode: Optional[int] = None
    stdout = ""
    stderr = ""
    try:
        completed = subprocess.run(
            list(command),
            cwd=str(cwd) if cwd is not None else None,
            env=dict(env) if env is not None else None,
            capture_output=True,
            text=True,
            timeout=float(budget_seconds),
            check=False,
        )
        returncode = int(completed.returncode)
        stdout = completed.stdout or ""
        stderr = completed.stderr or ""
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        returncode = None
        stdout = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
        stderr = (exc.stderr or "") if isinstance(exc.stderr, str) else ""
        if not stderr:
            stderr = f"timed out after {budget_seconds}s"
    wall_ms = (time.perf_counter() - started) * 1000.0
    return {
        "ok": (not timed_out) and returncode == 0,
        "timedOut": timed_out,
        "returncode": returncode,
        "wallMs": round(wall_ms, 3),
        "stdout": stdout,
        "stderr": stderr,
        "command": list(command),
    }


def _infer_match_duration_ms(
    rows: Sequence[Mapping[str, Any]],
    *,
    match_duration_ms: Optional[int] = None,
) -> Optional[int]:
    if match_duration_ms is not None:
        return int(match_duration_ms)
    coverage = next((r for r in rows if r.get("rfc461Schema") == "rofl_coverage"), None)
    if not isinstance(coverage, Mapping):
        return None
    for key in ("roflGameLengthMs", "effectiveEndMs", "endMs"):
        extra = coverage.get(key)
        if extra is not None:
            try:
                return int(extra)
            except (TypeError, ValueError):
                pass
    prov = coverage.get("provenance") if isinstance(coverage.get("provenance"), Mapping) else {}
    for key in ("roflGameLengthMs", "durationMs", "gameLengthMs"):
        if prov.get(key) is not None:
            try:
                return int(prov[key])
            except (TypeError, ValueError):
                pass
    stats = [r for r in rows if r.get("rfc461Schema") == "stats_update"]
    if stats:
        try:
            return int(stats[-1]["gameTime"])
        except (KeyError, TypeError, ValueError):
            return None
    return None


def evaluate_existing_jsonl(
    jsonl_path: Path,
    *,
    wall_ms: Optional[float] = None,
    match_duration_ms: Optional[int] = None,
    step_ms: int = DEFAULT_STEP_MS,
    expected_times_ms: Optional[Sequence[int]] = None,
    oracle_path: Optional[Path] = None,
    oracle_tolerance: float = DEFAULT_ORACLE_TOLERANCE,
    tolerate_truncated_tail: bool = False,
    partial: bool = False,
) -> dict[str, Any]:
    """Evaluate an on-disk rfc461 artifact without mutation.

    ``partial=True`` scores durable rows after a budget timeout for diagnostics.
    Quality ``ok`` is forced false and ``completedExpectedSchedule`` is false;
    callers must still discard.
    """
    rows = _load_jsonl(
        jsonl_path,
        tolerate_truncated_tail=tolerate_truncated_tail,
    )
    oracle_rows = (
        _load_jsonl(oracle_path) if oracle_path is not None else None
    )
    gates = dict(
        evaluate_quality_gates(
            rows,
            step_ms=step_ms,
            expected_times_ms=expected_times_ms,
            oracle_rows=oracle_rows,
            oracle_tolerance=oracle_tolerance,
        )
    )
    stats_times = [
        int(r["gameTime"])
        for r in rows
        if r.get("rfc461Schema") == "stats_update" and r.get("gameTime") is not None
    ]
    expected_list = (
        [int(x) for x in expected_times_ms] if expected_times_ms is not None else None
    )
    completed_expected = bool(
        expected_list is not None and stats_times == expected_list
    )
    if expected_list is None and not partial:
        # Eval-only without an explicit schedule: treat observed grid as complete.
        completed_expected = bool(gates.get("cadenceOk"))

    gates["partial"] = bool(partial)
    gates["completedExpectedSchedule"] = bool(completed_expected) and not partial
    if partial:
        gates["ok"] = False
        failures = list(gates.get("failures") or [])
        if "incomplete capture window" not in failures:
            failures.append("incomplete capture window")
        gates["failures"] = failures

    duration = _infer_match_duration_ms(rows, match_duration_ms=match_duration_ms)
    metrics: Optional[dict[str, Any]] = None
    stats_count = int(gates.get("statsUpdateCount") or 0)
    if wall_ms is not None and stats_count > 0:
        metrics = compute_speed_metrics(
            wall_ms=float(wall_ms),
            stats_update_count=stats_count,
            match_duration_ms=duration,
        )
        if partial:
            metrics["partial"] = True
    elif wall_ms is not None and stats_count <= 0 and not partial:
        raise SpeedBenchError("cannot compute metrics: no stats_update rows")
    return {
        "jsonl": str(jsonl_path),
        "mutated": False,
        "qualityGates": gates,
        "metrics": metrics,
        "matchDurationMs": duration,
        "partial": bool(partial),
    }


def build_replay_api_command(
    *,
    rofl: Path,
    out: Path,
    start_ms: int,
    end_ms: int,
    step_ms: int,
    checkpoint_out: Optional[Path] = None,
    extra_args: Optional[Sequence[str]] = None,
) -> list[str]:
    """Build argv for the public guarded Replay API capture CLI."""
    cmd = [
        sys.executable,
        str(SCRIPTS / "rofl_replay_api_to_jsonl.py"),
        "--rofl",
        str(rofl),
        "--out",
        str(out),
        "--start-ms",
        str(int(start_ms)),
        "--end-ms",
        str(int(end_ms)),
        "--step-ms",
        str(int(step_ms)),
    ]
    if checkpoint_out is not None:
        cmd.extend(["--checkpoint-out", str(checkpoint_out)])
    if extra_args:
        cmd.extend(list(extra_args))
    return cmd


def expected_replay_api_sample_times_ms(
    *,
    rofl_path: Path,
    start_ms: int,
    end_ms: int,
    step_ms: int,
    rofl_game_length_ms: Optional[int] = None,
) -> list[int]:
    """Expected stats_update grid for a Replay API window (gameLength clamp).

    Prefers an explicit length; otherwise inspects ROFL metadata the same way
    capture does via ``read_rofl_build``.
    """
    # Local import keeps the harness importable without forcing probe side effects
    # at module load, while still sharing the exact capture schedule helper.
    import rofl_replay_api_probe as replay_probe
    import rofl_replay_api_to_jsonl as capture

    length = rofl_game_length_ms
    if length is None:
        try:
            meta = replay_probe.read_rofl_build(Path(rofl_path))
            raw = meta.get("gameLengthMs")
            length = int(raw) if raw is not None else None
        except (OSError, TypeError, ValueError, KeyError):
            length = None
    schedule = capture.resolve_sample_schedule_ms(
        int(start_ms),
        int(end_ms),
        int(step_ms),
        rofl_game_length_ms=length,
    )
    return list(schedule["sampleTimesMs"])


def build_run_record(
    *,
    run_id: str,
    match_code: str,
    backend: str,
    hypothesis: str,
    diff_label: str,
    budget_seconds: float,
    metrics: Optional[Mapping[str, Any]],
    quality_gates: Mapping[str, Any],
    keep: str,
    reason: str,
    command: Optional[Sequence[str]] = None,
    extra: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "runId": run_id,
        "timestamp": utc_now_iso(),
        "matchCode": str(match_code),
        "backend": backend,
        "hypothesis": hypothesis,
        "diffLabel": diff_label,
        "fixedBudgetSeconds": float(budget_seconds),
        "command": list(command) if command is not None else None,
        "metrics": dict(metrics) if metrics is not None else None,
        "qualityGates": dict(quality_gates),
        "keep": keep,
        "reason": reason,
    }
    if extra:
        record.update(dict(extra))
    return record


def _parse_command_arg(raw: Sequence[str]) -> list[str]:
    if len(raw) == 1 and (" " in raw[0] or "\t" in raw[0]):
        return shlex.split(raw[0])
    return list(raw)


def build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--eval-jsonl",
        type=Path,
        help="Evaluate an existing rfc461 JSONL without mutation",
    )
    mode.add_argument(
        "--command",
        nargs=argparse.REMAINDER,
        help="Arbitrary backend command (prefix with --)",
    )
    mode.add_argument(
        "--replay-api",
        action="store_true",
        help="Bounded-window Replay API capture via guarded CLI",
    )
    mode.add_argument(
        "--offline-command",
        nargs=argparse.REMAINDER,
        help="Offline packet/decode command hook (prefix with --)",
    )

    ap.add_argument("--match-code", default="")
    ap.add_argument("--backend", default="")
    ap.add_argument("--hypothesis", default="")
    ap.add_argument("--diff-label", default="")
    ap.add_argument(
        "--budget-seconds",
        type=float,
        default=DEFAULT_BUDGET_SECONDS,
        help="Fixed wall-clock experiment budget (default 60s)",
    )
    ap.add_argument("--log", type=Path, default=DEFAULT_LOG)
    ap.add_argument("--wall-ms", type=float, default=None)
    ap.add_argument("--match-duration-ms", type=int, default=None)
    ap.add_argument("--step-ms", type=int, default=DEFAULT_STEP_MS)
    ap.add_argument("--oracle-jsonl", type=Path, default=None)
    ap.add_argument(
        "--oracle-tolerance",
        type=float,
        default=DEFAULT_ORACLE_TOLERANCE,
    )
    ap.add_argument("--out-jsonl", type=Path, default=None)
    ap.add_argument("--rofl", type=Path, default=None)
    ap.add_argument("--start-ms", type=int, default=None)
    ap.add_argument("--end-ms", type=int, default=None)
    ap.add_argument("--checkpoint-out", type=Path, default=None)
    ap.add_argument(
        "--replay-extra",
        nargs=argparse.REMAINDER,
        default=None,
        help=(
            "Extra args forwarded to rofl_replay_api_to_jsonl "
            "(REMAINDER after --replay-extra, e.g. "
            "--replay-extra --cached-selection-strategy compact)"
        ),
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the run record without appending to the log",
    )
    return ap


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_arg_parser().parse_args(list(argv) if argv is not None else None)
    run_id = new_run_id()
    match_code = str(args.match_code or "")
    hypothesis = str(args.hypothesis or "")
    diff_label = str(args.diff_label or "")
    budget = float(args.budget_seconds)

    try:
        if args.eval_jsonl is not None:
            backend = args.backend or "eval-jsonl"
            result = evaluate_existing_jsonl(
                args.eval_jsonl,
                wall_ms=args.wall_ms,
                match_duration_ms=args.match_duration_ms,
                step_ms=args.step_ms,
                oracle_path=args.oracle_jsonl,
                oracle_tolerance=args.oracle_tolerance,
            )
            gates = result["qualityGates"]
            metrics = result["metrics"]
            keep, reason = decide_keep(
                gates_ok=bool(gates.get("ok")),
                timed_out=False,
                command_ok=True,
                reason_parts=(
                    []
                    if gates.get("ok")
                    else list(gates.get("failures") or ["quality gates failed"])
                ),
            )
            record = build_run_record(
                run_id=run_id,
                match_code=match_code or Path(args.eval_jsonl).parent.name,
                backend=backend,
                hypothesis=hypothesis or "evaluate existing rfc461 artifact",
                diff_label=diff_label or "eval-only",
                budget_seconds=budget,
                metrics=metrics,
                quality_gates=gates,
                keep=keep,
                reason=reason,
                command=None,
                extra={"source": "eval_jsonl", "jsonl": str(args.eval_jsonl)},
            )
        else:
            if args.replay_api:
                backend = args.backend or "replay-api-bounded"
                if args.rofl is None or args.out_jsonl is None:
                    raise SpeedBenchError("--replay-api requires --rofl and --out-jsonl")
                if args.start_ms is None or args.end_ms is None:
                    raise SpeedBenchError("--replay-api requires --start-ms and --end-ms")
                extra = list(args.replay_extra or [])
                if extra and extra[0] == "--":
                    extra = extra[1:]
                command = build_replay_api_command(
                    rofl=args.rofl,
                    out=args.out_jsonl,
                    start_ms=args.start_ms,
                    end_ms=args.end_ms,
                    step_ms=args.step_ms,
                    checkpoint_out=args.checkpoint_out,
                    extra_args=extra,
                )
                out_jsonl = Path(args.out_jsonl)
                expected = expected_replay_api_sample_times_ms(
                    rofl_path=args.rofl,
                    start_ms=int(args.start_ms),
                    end_ms=int(args.end_ms),
                    step_ms=int(args.step_ms),
                )
            elif args.command is not None:
                backend = args.backend or "command"
                raw = list(args.command)
                if raw and raw[0] == "--":
                    raw = raw[1:]
                command = _parse_command_arg(raw)
                out_jsonl = Path(args.out_jsonl) if args.out_jsonl else None
                expected = None
            elif args.offline_command is not None:
                backend = args.backend or "offline-command"
                raw = list(args.offline_command)
                if raw and raw[0] == "--":
                    raw = raw[1:]
                command = _parse_command_arg(raw)
                out_jsonl = Path(args.out_jsonl) if args.out_jsonl else None
                expected = None
            else:
                raise SpeedBenchError("no mode selected")

            cmd_result = run_command_with_budget(command, budget_seconds=budget, cwd=ROOT)
            gates: dict[str, Any]
            metrics: Optional[dict[str, Any]] = None
            if out_jsonl is not None and out_jsonl.is_file() and not cmd_result["timedOut"]:
                eval_result = evaluate_existing_jsonl(
                    out_jsonl,
                    wall_ms=float(cmd_result["wallMs"]),
                    match_duration_ms=args.match_duration_ms,
                    step_ms=args.step_ms,
                    expected_times_ms=expected,
                    oracle_path=args.oracle_jsonl,
                    oracle_tolerance=args.oracle_tolerance,
                )
                gates = eval_result["qualityGates"]
                metrics = eval_result["metrics"]
            elif (
                out_jsonl is not None
                and out_jsonl.is_file()
                and cmd_result["timedOut"]
            ):
                # Budget exceeded: still score durable partial rows for diagnostics.
                try:
                    eval_result = evaluate_existing_jsonl(
                        out_jsonl,
                        wall_ms=float(cmd_result["wallMs"]),
                        match_duration_ms=args.match_duration_ms,
                        step_ms=args.step_ms,
                        expected_times_ms=expected,
                        oracle_path=args.oracle_jsonl,
                        oracle_tolerance=args.oracle_tolerance,
                        tolerate_truncated_tail=True,
                        partial=True,
                    )
                    gates = dict(eval_result["qualityGates"])
                    metrics = eval_result["metrics"]
                except SpeedBenchError as exc:
                    gates = {
                        "ok": False,
                        "failures": ["budget exceeded", str(exc)],
                        "statsUpdateCount": 0,
                        "fountainPlaceholders": 0,
                        "identityStable": False,
                        "cadenceOk": False,
                        "noFabrication": False,
                        "oracle": None,
                        "partial": True,
                        "completedExpectedSchedule": False,
                    }
                    metrics = None
                failures = list(gates.get("failures") or [])
                if "budget exceeded" not in failures:
                    failures.insert(0, "budget exceeded")
                gates["failures"] = failures
                gates["ok"] = False
                gates["partial"] = True
                gates["completedExpectedSchedule"] = False
            else:
                if cmd_result["timedOut"]:
                    fail_reason = "budget exceeded"
                elif not cmd_result["ok"]:
                    fail_reason = "command failed"
                elif out_jsonl is None:
                    fail_reason = "output JSONL missing for quality gates"
                else:
                    fail_reason = f"output JSONL not found: {out_jsonl}"
                gates = {
                    "ok": False,
                    "failures": [fail_reason],
                    "statsUpdateCount": 0,
                    "fountainPlaceholders": 0,
                    "identityStable": False,
                    "cadenceOk": False,
                    "noFabrication": False,
                    "oracle": None,
                    "partial": bool(cmd_result["timedOut"]),
                    "completedExpectedSchedule": False,
                }

            reason_parts: list[str] = []
            if cmd_result["timedOut"]:
                reason_parts.append("budget exceeded")
            elif not cmd_result["ok"]:
                err = (cmd_result.get("stderr") or "").strip().splitlines()
                reason_parts.append(
                    err[-1] if err else f"command exit {cmd_result.get('returncode')}"
                )
            if not gates.get("ok") and gates.get("failures"):
                reason_parts.extend(str(x) for x in gates["failures"][:5])

            keep, reason = decide_keep(
                gates_ok=bool(gates.get("ok")),
                timed_out=bool(cmd_result["timedOut"]),
                command_ok=bool(cmd_result["ok"]),
                reason_parts=reason_parts,
            )
            if not match_code and args.rofl is not None:
                match_code = args.rofl.stem.split("-")[-1]
            record = build_run_record(
                run_id=run_id,
                match_code=match_code or "unknown",
                backend=backend,
                hypothesis=hypothesis or f"{backend} fixed-budget run",
                diff_label=diff_label or backend,
                budget_seconds=budget,
                metrics=metrics,
                quality_gates=gates,
                keep=keep,
                reason=reason,
                command=command,
                extra={
                    "timedOut": bool(cmd_result["timedOut"]),
                    "returncode": cmd_result.get("returncode"),
                    "commandWallMs": cmd_result.get("wallMs"),
                    "outJsonl": str(out_jsonl) if out_jsonl is not None else None,
                },
            )
    except SpeedBenchError as exc:
        record = build_run_record(
            run_id=run_id,
            match_code=match_code or "unknown",
            backend=args.backend or "error",
            hypothesis=hypothesis or "harness error",
            diff_label=diff_label or "error",
            budget_seconds=budget,
            metrics=None,
            quality_gates={
                "ok": False,
                "failures": [str(exc)],
                "statsUpdateCount": 0,
                "fountainPlaceholders": 0,
                "identityStable": False,
                "cadenceOk": False,
                "noFabrication": False,
                "oracle": None,
            },
            keep="discard",
            reason=str(exc),
            command=None,
        )
        print(json.dumps(record, indent=2, default=str))
        if not args.dry_run:
            append_run_record(args.log, record)
        return 2

    print(json.dumps(record, indent=2, default=str))
    if not args.dry_run:
        append_run_record(args.log, record)
    return 0 if record.get("keep") == "keep" else 1


if __name__ == "__main__":
    raise SystemExit(main())
