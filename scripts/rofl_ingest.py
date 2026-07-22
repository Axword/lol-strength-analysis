#!/usr/bin/env python3
"""First-class resumable ROFL → canonical rfc461 → GameTimeline ingestion.

Default:
  python3 scripts/rofl_ingest.py BR1-3264361042.rofl [--publish]

Phase recovery:
  python3 scripts/rofl_ingest.py inspect BR1-3264361042.rofl
  python3 scripts/rofl_ingest.py capture BR1-3264361042.rofl
  python3 scripts/rofl_ingest.py build BR1-3264361042.rofl
  python3 scripts/rofl_ingest.py validate BR1-3264361042.rofl
  python3 scripts/rofl_ingest.py publish BR1-3264361042.rofl
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Sequence

import rofl_metadata
import rofl_replay_api_probe as replay_probe
import rofl_replay_api_to_jsonl as replay_capture
import rebuild_match_registry as match_registry
import fuse_replay_api_hp as hp_fusion
import replay_capture_guard


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
ARTIFACT_ROOT = ROOT / "artifacts/rofl"
PUBLISH_ROOT = ROOT / "public/data/matches"

MANIFEST_VERSION = 4
RFC461_FORMAT_VERSION = 2
TIMELINE_FORMAT_VERSION = 1
VALIDATION_FORMAT_VERSION = 1
DEFAULT_START_MS = 60_000
DEFAULT_STEP_MS = 1_000
PHASES = ("ingest", "inspect", "capture", "build", "validate", "publish")


class IngestError(RuntimeError):
    """Fail-closed ingest error."""


@dataclass(frozen=True)
class ArtifactPaths:
    match_dir: Path
    manifest: Path
    events: Path
    checkpoint: Path
    hp_evidence: Path
    hp_events: Path
    timeline: Path
    validation: Path

    @property
    def managed(self) -> tuple[Path, ...]:
        return (
            self.manifest,
            self.events,
            self.checkpoint,
            self.hp_evidence,
            self.hp_events,
            self.timeline,
            self.validation,
        )


def artifact_paths(
    match_code: str,
    *,
    artifact_root: Path = ARTIFACT_ROOT,
) -> ArtifactPaths:
    if not str(match_code).isdigit():
        raise IngestError(f"unsafe match code {match_code!r}")
    match_dir = artifact_root / str(match_code)
    return ArtifactPaths(
        match_dir=match_dir,
        manifest=match_dir / "manifest.json",
        events=match_dir / "events.rfc461.jsonl",
        checkpoint=match_dir / "capture.checkpoint.json",
        hp_evidence=match_dir / "hp-evidence.json",
        hp_events=match_dir / "events.hp-trusted.rfc461.jsonl",
        timeline=match_dir / "timeline.json",
        validation=match_dir / "validation.json",
    )


def controller_lock_path(*, artifact_root: Path = ARTIFACT_ROOT) -> Path:
    return replay_capture_guard.controller_lock_path(artifact_root=artifact_root)


class ReplayControllerLock(replay_capture_guard.ReplayControllerLock):
    """Ingest-facing shared controller lock with IngestError compatibility."""

    def __init__(self, path: Path) -> None:
        super().__init__(path, error_type=IngestError)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def atomic_write_json(path: Path, value: Any, *, compact: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    text = (
        json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        if compact
        else json.dumps(value, ensure_ascii=False, indent=2)
    )
    with tmp.open("w", encoding="utf-8") as fh:
        fh.write(text + "\n")
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def capture_config(
    metadata: Mapping[str, Any],
    *,
    start_ms: Optional[int],
    end_ms: Optional[int],
    step_ms: int,
) -> dict[str, Any]:
    duration = int(metadata["durationMs"])
    if step_ms <= 0:
        raise IngestError("--step-ms must be > 0")
    start = DEFAULT_START_MS if start_ms is None else int(start_ms)
    end = duration if end_ms is None else int(end_ms)
    start = max(0, min(start, duration))
    end = max(start, min(end, duration))
    samples = replay_capture._sample_times_ms(start, end, int(step_ms))  # noqa: SLF001
    return {
        "startMs": start,
        "endMs": end,
        "effectiveEndMs": samples[-1],
        "stepMs": int(step_ms),
        "cadenceMs": int(step_ms),
        "sampleCount": len(samples),
        "sampleTimesMs": samples,
    }


def _manifest_contract(manifest: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "manifestVersion": manifest.get("manifestVersion"),
        "matchCode": (manifest.get("match") or {}).get("matchCode"),
        "roflSha256": (manifest.get("rofl") or {}).get("sha256"),
        "rosterHash": manifest.get("rosterHash"),
        "capture": {
            key: (manifest.get("capture") or {}).get(key)
            for key in ("startMs", "endMs", "stepMs")
        },
    }


def make_manifest(
    metadata: Mapping[str, Any],
    config: Mapping[str, Any],
) -> dict[str, Any]:
    now = utc_now()
    return {
        "manifestVersion": MANIFEST_VERSION,
        "createdAt": now,
        "updatedAt": now,
        "match": {
            "platformId": metadata["platformId"],
            "matchCode": metadata["matchCode"],
            "gameId": metadata["gameId"],
            "gameName": metadata["matchCode"],
        },
        "rofl": {
            "basename": metadata["basename"],
            "sha256": metadata["sha256"],
            "sizeBytes": metadata["sizeBytes"],
            "format": metadata["format"],
            "formatVersion": metadata["formatVersion"],
            "patch": metadata["patch"],
            "build": metadata["build"],
            "durationMs": metadata["durationMs"],
        },
        "rosterHash": metadata["rosterHash"],
        "participants": copy.deepcopy(metadata["participants"]),
        "postGameSummary": copy.deepcopy(metadata.get("postGameSummary") or {}),
        "capture": {
            key: config[key]
            for key in (
                "startMs",
                "endMs",
                "effectiveEndMs",
                "stepMs",
                "cadenceMs",
                "sampleCount",
            )
        },
        "sourceCoverage": {
            "positions": "full_at_sampled_frames",
            "levelItemsAlive": "full_at_sampled_frames",
            "hp": "none",
            "combatStats": "none",
            "abilityRanks": "none",
            "careerHistory": "kda_total_cs_vision_at_sampled_frames",
            "careerHistoryFields": {
                field: {
                    "coverage": "full_at_sampled_frames",
                    "source": "liveclient_allgamedata_scores",
                }
                for field in replay_capture.LIVECLIENT_HISTORY_FIELDS
            },
            "careerHistoryUnsupported": [
                "damage",
                "gold",
                "objectives",
                "jungleCreepScore",
            ],
        },
        "artifacts": {
            "manifest": {
                "path": "manifest.json",
                "format": "rofl-ingest-manifest",
                "version": MANIFEST_VERSION,
            },
            "events": {
                "path": "events.rfc461.jsonl",
                "format": "rfc461-jsonl",
                "version": RFC461_FORMAT_VERSION,
            },
            "checkpoint": {
                "path": "capture.checkpoint.json",
                "format": "replay-api-capture-checkpoint",
                "version": 1,
            },
            "trustedHpEvidence": {
                "path": "hp-evidence.json",
                "format": hp_fusion.TRUSTED_EVIDENCE_SCHEMA,
                "version": 1,
                "optional": True,
            },
            "trustedHpEvents": {
                "path": "events.hp-trusted.rfc461.jsonl",
                "format": "rfc461-jsonl",
                "version": RFC461_FORMAT_VERSION,
                "optional": True,
            },
            "timeline": {
                "path": "timeline.json",
                "format": "GameTimeline",
                "version": TIMELINE_FORMAT_VERSION,
            },
            "validation": {
                "path": "validation.json",
                "format": "rofl-product-validation",
                "version": VALIDATION_FORMAT_VERSION,
            },
        },
        "phase": {
            "current": "inspect",
            "status": "ready",
            "completed": [],
        },
        "validation": None,
        "productGates": {
            "rosterCount": metadata["rosterCount"] == 10,
            "stableIdentityComplete": metadata["stableIdentityComplete"],
            "missingStableIdentityCount": metadata["missingStableIdentityCount"],
            "activeReplayIdentityVerified": False,
            "captureComplete": False,
            "productValidated": False,
            "hpTrusted": False,
            "calculatorReady": False,
        },
    }


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise IngestError(f"cannot read {path.name}: {exc}") from exc
    if not isinstance(value, dict):
        raise IngestError(f"{path.name} must contain a JSON object")
    return value


def _absolute_strings(value: Any, prefix: str = "$") -> list[str]:
    """Flag real local filesystem paths, not web-root URLs like ``/map/...``."""
    found: list[str] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            found.extend(_absolute_strings(child, f"{prefix}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(_absolute_strings(child, f"{prefix}[{index}]"))
    elif isinstance(value, str):
        text = value.strip()
        if (
            text.startswith(("file://", "/Users/", "/home/", "/tmp/", "/private/", "/var/"))
            or (len(text) >= 3 and text[1:3] in {":\\", ":/"})
        ):
            found.append(prefix)
    return found


def assert_sanitized(value: Any, *, label: str) -> None:
    absolute = _absolute_strings(value)
    if absolute:
        raise IngestError(
            f"{label} contains absolute local paths at {absolute[:5]}"
        )


def _expected_manifest(
    metadata: Mapping[str, Any],
    config: Mapping[str, Any],
) -> dict[str, Any]:
    manifest = make_manifest(metadata, config)
    assert_sanitized(manifest, label="manifest")
    return manifest


def _validate_partial_schedule(
    paths: ArtifactPaths,
    manifest: Mapping[str, Any],
    config: Mapping[str, Any],
) -> tuple[str, int]:
    if not paths.events.exists():
        return "empty", 0
    try:
        partial = replay_capture.read_partial_rfc461_jsonl(paths.events)
    except replay_capture.ExtractError as exc:
        raise IngestError(f"existing capture is invalid: {exc}") from exc
    times = list(partial.completed_times_ms)
    schedule = list(config["sampleTimesMs"])
    if times != schedule[: len(times)]:
        raise IngestError(
            "existing capture times are not the expected contiguous schedule prefix"
        )
    coverage = partial.coverage
    for key in ("startMs", "endMs", "stepMs"):
        if int(coverage.get(key, -1)) != int(config[key]):
            raise IngestError(
                f"existing capture {key} mismatch: {coverage.get(key)!r} != {config[key]}"
            )
    if int(partial.game_info.get("gameID") or 0) != int(
        (manifest.get("match") or {}).get("gameId") or 0
    ):
        raise IngestError("existing capture gameID mismatches manifest")
    if paths.checkpoint.exists():
        checkpoint = load_json(paths.checkpoint)
        completed = checkpoint.get("completedCount")
        if completed is not None and int(completed) != len(times):
            raise IngestError(
                "capture checkpoint completedCount mismatches durable JSONL"
            )
    return ("complete" if times == schedule else "partial"), len(times)


def assess_artifacts(
    paths: ArtifactPaths,
    desired: Mapping[str, Any],
    config: Mapping[str, Any],
) -> dict[str, Any]:
    if not paths.manifest.exists():
        unmanaged = [path.name for path in paths.managed[1:] if path.exists()]
        if unmanaged:
            return {
                "state": "mismatch",
                "reason": f"artifacts exist without manifest: {unmanaged}",
                "completed": 0,
            }
        return {"state": "new", "reason": None, "completed": 0}
    try:
        existing = load_json(paths.manifest)
    except IngestError as exc:
        return {"state": "mismatch", "reason": str(exc), "completed": 0}
    if _manifest_contract(existing) != _manifest_contract(desired):
        return {
            "state": "mismatch",
            "reason": "existing manifest identity/schedule contract differs",
            "completed": 0,
        }
    try:
        state, completed = _validate_partial_schedule(paths, existing, config)
    except IngestError as exc:
        return {"state": "mismatch", "reason": str(exc), "completed": 0}
    return {
        "state": state,
        "reason": None,
        "completed": completed,
        "manifest": existing,
    }


def clear_managed_artifacts(paths: ArtifactPaths) -> None:
    match_dir = paths.match_dir.resolve()
    for path in paths.managed:
        if path.parent.resolve() != match_dir:
            raise IngestError(f"refusing to clear path outside match dir: {path}")
        if path.exists():
            if not path.is_file():
                raise IngestError(f"refusing to remove non-file artifact: {path.name}")
            path.unlink()
    if paths.match_dir.exists():
        for tmp in paths.match_dir.glob(".*.tmp"):
            if tmp.is_file() and tmp.parent.resolve() == match_dir:
                tmp.unlink()


def prepare_artifacts(
    paths: ArtifactPaths,
    desired: dict[str, Any],
    config: Mapping[str, Any],
    *,
    force: bool,
) -> dict[str, Any]:
    assessment = assess_artifacts(paths, desired, config)
    if assessment["state"] == "mismatch" and not force:
        raise IngestError(
            f"{assessment['reason']}; pass --force for managed replacement"
        )
    if force:
        clear_managed_artifacts(paths)
        assessment = {"state": "new", "reason": None, "completed": 0}
    if assessment["state"] == "new":
        paths.match_dir.mkdir(parents=True, exist_ok=True)
        atomic_write_json(paths.manifest, desired)
        manifest = desired
    else:
        manifest = load_json(paths.manifest)
    return {"assessment": assessment, "manifest": manifest}


def update_manifest(
    paths: ArtifactPaths,
    *,
    phase: str,
    status: str,
    updates: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    manifest = load_json(paths.manifest)
    completed = list((manifest.get("phase") or {}).get("completed") or [])
    if status in {"complete", "skipped"} and phase not in completed:
        completed.append(phase)
    manifest["phase"] = {
        "current": phase,
        "status": status,
        "completed": completed,
    }
    manifest["updatedAt"] = utc_now()
    for key, value in (updates or {}).items():
        manifest[key] = value
    assert_sanitized(manifest, label="manifest")
    atomic_write_json(paths.manifest, manifest)
    return manifest


def inspect_active_replay(
    transport: replay_probe.Transport,
    *,
    base_url: str,
    timeout: float,
) -> dict[str, Any]:
    try:
        return replay_capture_guard.inspect_active_replay(
            transport,
            base_url=base_url,
            timeout=timeout,
        )
    except replay_capture_guard.ReplayGuardError as exc:
        raise IngestError(str(exc)) from exc


def verify_active_replay(
    metadata: Mapping[str, Any],
    active: Mapping[str, Any],
    *,
    app_path: Path,
) -> dict[str, Any]:
    try:
        return replay_capture_guard.verify_active_replay(
            metadata,
            active,
            app_path=app_path,
        )
    except replay_capture_guard.ReplayGuardError as exc:
        raise IngestError(str(exc)) from exc


def inspect_phase(
    metadata: Mapping[str, Any],
    config: Mapping[str, Any],
    paths: ArtifactPaths,
    *,
    force: bool,
) -> dict[str, Any]:
    desired = _expected_manifest(metadata, config)
    prepared = prepare_artifacts(paths, desired, config, force=force)
    manifest = update_manifest(
        paths,
        phase="inspect",
        status="complete",
    )
    return {
        "phase": "inspect",
        "state": prepared["assessment"]["state"],
        "manifest": manifest,
    }


def capture_phase(
    rofl_path: Path,
    metadata: Mapping[str, Any],
    config: Mapping[str, Any],
    paths: ArtifactPaths,
    *,
    force: bool,
    app_path: Path,
    base_url: str,
    timeout: float,
    transport: replay_probe.Transport = replay_probe.default_http_transport,
    capture_runner: Callable[..., dict[str, Any]] = (
        replay_capture._extract_replay_api_jsonl_after_guard
    ),
    lock_path: Optional[Path] = None,
) -> dict[str, Any]:
    desired = _expected_manifest(metadata, config)
    assessment = assess_artifacts(paths, desired, config)
    if assessment["state"] == "mismatch" and not force:
        raise IngestError(
            f"{assessment['reason']}; pass --force for managed replacement"
        )
    if assessment["state"] == "complete" and not force:
        manifest = load_json(paths.manifest)
        gates = dict(manifest.get("productGates") or {})
        gates["captureComplete"] = True
        gates["activeReplayIdentityVerified"] = bool(
            gates.get("activeReplayIdentityVerified")
        )
        update_manifest(
            paths,
            phase="capture",
            status="skipped",
            updates={"productGates": gates},
        )
        return {
            "phase": "capture",
            "ok": True,
            "noop": True,
            "completedCount": assessment["completed"],
        }

    lock = ReplayControllerLock(
        lock_path or controller_lock_path(artifact_root=paths.match_dir.parent)
    )
    with lock:
        # GET-only identity proof must complete before force cleanup, JSONL write,
        # pause, seek, or any other Replay API mutation.
        active = inspect_active_replay(
            transport,
            base_url=base_url,
            timeout=timeout,
        )
        preflight = verify_active_replay(metadata, active, app_path=app_path)
        prepared = prepare_artifacts(paths, desired, config, force=force)
        update_manifest(
            paths,
            phase="inspect",
            status="complete",
            updates={
                "productGates": {
                    **desired["productGates"],
                    "activeReplayIdentityVerified": True,
                },
                "activeReplayPreflight": preflight,
            },
        )
        resume = prepared["assessment"]["state"] == "partial" and paths.events.exists()
        try:
            status = capture_runner(
                transport,
                base_url=base_url,
                rofl_path=rofl_path,
                app_path=app_path,
                out_path=paths.events,
                start_ms=int(config["startMs"]),
                end_ms=int(config["endMs"]),
                step_ms=int(config["stepMs"]),
                allow_build_mismatch=False,
                timeout=timeout,
                game_id=int(metadata["gameId"]),
                resume=resume,
                checkpoint_out=paths.checkpoint,
            )
        except Exception:
            update_manifest(paths, phase="capture", status="failed")
            raise
        if not status.get("ok"):
            update_manifest(paths, phase="capture", status="failed")
            raise IngestError(f"capture failed: {status.get('error')}")
        completed = assess_artifacts(paths, desired, config)
        if completed["state"] != "complete":
            update_manifest(paths, phase="capture", status="failed")
            raise IngestError(
                "capture runner returned success without a complete durable schedule "
                f"(state={completed['state']})"
            )

    manifest = load_json(paths.manifest)
    gates = dict(manifest.get("productGates") or {})
    gates["activeReplayIdentityVerified"] = True
    gates["captureComplete"] = True
    update_manifest(
        paths,
        phase="capture",
        status="complete",
        updates={
            "captureResult": {
                "ok": True,
                "resumed": bool(status.get("resumed")),
                "noop": bool(status.get("noop")),
                "completedCount": status.get("completedCount"),
                "lastCompletedMs": status.get("lastCompletedMs"),
                "restoreSucceeded": status.get("restoreSucceeded"),
                "timing": copy.deepcopy(status.get("timing") or {}),
            },
            "productGates": gates,
        },
    )
    return {"phase": "capture", **status}


def _run_command(argv: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(argv),
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )


def _require_matching_manifest(
    metadata: Mapping[str, Any],
    config: Mapping[str, Any],
    paths: ArtifactPaths,
) -> dict[str, Any]:
    desired = _expected_manifest(metadata, config)
    assessment = assess_artifacts(paths, desired, config)
    if assessment["state"] == "new":
        raise IngestError("manifest missing; run inspect/capture first")
    if assessment["state"] == "mismatch":
        raise IngestError(str(assessment["reason"]))
    return assessment


def _sanitized_timeline(
    timeline: Mapping[str, Any],
    metadata: Mapping[str, Any],
    *,
    artifact: Optional[str] = None,
) -> dict[str, Any]:
    value = copy.deepcopy(dict(timeline))
    value["id"] = str(metadata["matchCode"])
    value["name"] = str(metadata["matchCode"])
    provenance = dict(value.get("provenance") or {})
    provenance["artifact"] = (
        artifact
        or str(provenance.get("artifact") or "")
        or "events.rfc461.jsonl"
    )
    provenance["matchCode"] = str(metadata["matchCode"])
    provenance["gameId"] = int(metadata["gameId"])
    value["provenance"] = provenance
    assert_sanitized(value, label="timeline")
    return value


def build_phase(
    metadata: Mapping[str, Any],
    config: Mapping[str, Any],
    paths: ArtifactPaths,
    *,
    hp_evidence: Optional[Path] = None,
    command_runner: Callable[[Sequence[str]], subprocess.CompletedProcess[str]] = _run_command,
) -> dict[str, Any]:
    assessment = _require_matching_manifest(metadata, config, paths)
    if assessment["state"] != "complete":
        raise IngestError(
            f"capture is {assessment['state']}; resume capture before build"
        )
    tmp = paths.match_dir / ".timeline.build.tmp.json"
    if tmp.exists():
        tmp.unlink()
    existing_manifest = load_json(paths.manifest)
    existing_trusted_hp = existing_manifest.get("trustedHp") or {}
    evidence_input = hp_evidence
    if evidence_input is None and paths.hp_evidence.is_file():
        evidence_input = paths.hp_evidence
    if (
        evidence_input is None
        and existing_trusted_hp.get("ok") is True
    ):
        raise IngestError(
            "manifest claims trusted HP but durable evidence is missing"
        )
    build_events = paths.events
    hp_summary: Optional[dict[str, Any]] = None
    if evidence_input is not None:
        if not evidence_input.is_file():
            raise IngestError(f"trusted HP evidence missing: {evidence_input}")
        evidence = load_json(evidence_input)
        assert_sanitized(evidence, label="trusted HP evidence")
        hp_events_tmp = paths.match_dir / ".events.hp-trusted.build.tmp.jsonl"
        if hp_events_tmp.exists():
            hp_events_tmp.unlink()
        fusion_command = [
            sys.executable,
            str(SCRIPTS / "fuse_replay_api_hp.py"),
            "--product",
            "--jsonl",
            str(paths.events),
            "--replay-manifest",
            str(paths.manifest),
            "--hp-evidence",
            str(evidence_input),
            "-o",
            str(hp_events_tmp),
        ]
        fusion_result = command_runner(fusion_command)
        if fusion_result.returncode != 0:
            if hp_events_tmp.exists():
                hp_events_tmp.unlink()
            raise IngestError(
                "trusted HP fusion failed: "
                + str(fusion_result.stderr or fusion_result.stdout)
            )
        if not hp_events_tmp.is_file():
            raise IngestError("trusted HP fusion did not write its canonical output")
        try:
            hp_summary = json.loads(fusion_result.stdout)
        except json.JSONDecodeError as exc:
            hp_events_tmp.unlink()
            raise IngestError(f"trusted HP fusion returned invalid summary: {exc}") from exc
        if hp_summary.get("ok") is not True:
            hp_events_tmp.unlink()
            raise IngestError("trusted HP fusion summary did not pass")
        os.replace(hp_events_tmp, paths.hp_events)
        atomic_write_json(paths.hp_evidence, evidence, compact=True)
        build_events = paths.hp_events
    commands = [
        [
            sys.executable,
            str(SCRIPTS / "jsonl_to_timeline.py"),
            str(build_events),
            "-o",
            str(tmp),
            "--id",
            str(metadata["matchCode"]),
            "--name",
            str(metadata["matchCode"]),
            "--patch",
            str(metadata.get("patch") or metadata.get("build") or ""),
        ],
        [
            sys.executable,
            str(SCRIPTS / "rebuild-timeline-scoreboard.py"),
            "--jsonl",
            str(build_events),
            "--timeline",
            str(tmp),
            "-o",
            str(tmp),
        ],
        [
            sys.executable,
            str(SCRIPTS / "enrich-timeline-career.py"),
            "--jsonl",
            str(build_events),
            "--timeline",
            str(tmp),
            "-o",
            str(tmp),
        ],
    ]
    try:
        for command in commands:
            result = command_runner(command)
            if result.returncode != 0:
                raise IngestError(
                    f"build command failed ({Path(command[1]).name}): "
                    f"{result.stderr or result.stdout}"
                )
        timeline = _sanitized_timeline(
            load_json(tmp),
            metadata,
            artifact=build_events.name,
        )
        atomic_write_json(paths.timeline, timeline, compact=True)
    finally:
        if tmp.exists():
            tmp.unlink()
    manifest = existing_manifest
    source_coverage = dict(manifest.get("sourceCoverage") or {})
    product_gates = dict(manifest.get("productGates") or {})
    trusted_hp: Optional[dict[str, Any]] = None
    if hp_summary is not None:
        source_coverage["hp"] = hp_summary["coverage"]
        trusted_hp = {
            "ok": True,
            "schema": hp_summary["schema"],
            "evidence": "hp-evidence.json",
            "events": "events.hp-trusted.rfc461.jsonl",
            "evidenceSha256": hp_summary["evidenceSha256"],
            "healthSource": hp_summary["healthSource"],
            "coverage": hp_summary["coverage"],
            "sampleCount": hp_summary["sampleCount"],
            "sampleTimesUsed": hp_summary["sampleTimesUsed"],
            "fusedFrames": hp_summary["fusedFrames"],
            "unmatchedFrames": hp_summary["unmatchedFrames"],
            "timeToleranceMs": hp_summary["timeToleranceMs"],
            "identityBinding": hp_summary["identityBinding"],
            "rosterHash": hp_summary["rosterHash"],
            "combatStatsKnown": False,
            "abilityRanksKnown": False,
        }
        product_gates["hpTrusted"] = True
    else:
        source_coverage["hp"] = "none"
        product_gates["hpTrusted"] = False
    update_manifest(
        paths,
        phase="build",
        status="complete",
        updates={
            "motionQA": copy.deepcopy(
                (timeline.get("provenance") or {}).get("motionAudit") or {}
            ),
            "sourceCoverage": source_coverage,
            "trustedHp": trusted_hp,
            "productGates": product_gates,
        },
    )
    return {"phase": "build", "ok": True, "timeline": paths.timeline.name}


def validate_phase(
    metadata: Mapping[str, Any],
    config: Mapping[str, Any],
    paths: ArtifactPaths,
    *,
    command_runner: Callable[[Sequence[str]], subprocess.CompletedProcess[str]] = _run_command,
) -> dict[str, Any]:
    _require_matching_manifest(metadata, config, paths)
    if not paths.timeline.is_file():
        raise IngestError("timeline missing; run build first")
    manifest = load_json(paths.manifest)
    trusted_hp = manifest.get("trustedHp") or {}
    validation_events = paths.events
    if trusted_hp.get("ok") is True:
        if not paths.hp_events.is_file() or not paths.hp_evidence.is_file():
            raise IngestError("trusted HP manifest claims missing durable artifacts")
        durable_evidence = load_json(paths.hp_evidence)
        durable_evidence_sha = hashlib.sha256(
            json.dumps(
                durable_evidence,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        if durable_evidence_sha != trusted_hp.get("evidenceSha256"):
            raise IngestError("trusted HP evidence hash changed after build")
        validation_events = paths.hp_events
    command = [
        sys.executable,
        str(SCRIPTS / "validate-rofl-pipeline.py"),
        "--jsonl",
        str(validation_events),
        "--timeline",
        str(paths.timeline),
        "--product",
    ]
    result = command_runner(command)
    report: dict[str, Any]
    if result.returncode == 0:
        try:
            report = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise IngestError(f"validator returned invalid JSON: {exc}") from exc
    else:
        report = {
            "ok": False,
            "productPublication": {"ok": False},
            "error": (result.stderr or result.stdout).strip(),
        }
    atomic_write_json(paths.validation, report)
    ok = bool(
        report.get("ok")
        and (report.get("productPublication") or {}).get("ok")
    )
    gates = dict(manifest.get("productGates") or {})
    gates["productValidated"] = ok
    gates["hpTrusted"] = bool(
        (report.get("productPublication") or {}).get("hpTrusted")
    )
    gates["calculatorReady"] = bool(
        (report.get("productPublication") or {}).get("calculatorReady")
    )
    update_manifest(
        paths,
        phase="validate",
        status="complete" if ok else "failed",
        updates={
            "validation": {
                "ok": ok,
                "path": "validation.json",
                "calculatorReady": gates["calculatorReady"],
                "hpTrusted": gates["hpTrusted"],
                "hpCoverage": (report.get("productPublication") or {}).get(
                    "hpCoverage"
                ),
                "motionAudit": copy.deepcopy(
                    report.get("motionAudit")
                    or (report.get("productPublication") or {}).get("motionAudit")
                    or {}
                ),
            },
            "productGates": gates,
        },
    )
    if not ok:
        raise IngestError("product validation failed; publication refused")
    return {"phase": "validate", "ok": True, "report": report}


def publish_phase(
    metadata: Mapping[str, Any],
    config: Mapping[str, Any],
    paths: ArtifactPaths,
    *,
    publish_root: Path = PUBLISH_ROOT,
    force: bool = False,
) -> dict[str, Any]:
    _require_matching_manifest(metadata, config, paths)
    if not paths.timeline.is_file() or not paths.validation.is_file():
        raise IngestError("timeline/validation missing; run build and validate first")
    validation = load_json(paths.validation)
    if not (
        validation.get("ok")
        and (validation.get("productPublication") or {}).get("ok")
    ):
        raise IngestError("publication refused: product validation did not pass")

    manifest = load_json(paths.manifest)
    gates = manifest.get("productGates") or {}
    if not gates.get("productValidated"):
        raise IngestError("publication refused: manifest product gate is not validated")
    manifest["publication"] = {
        "directory": f"public/data/matches/{metadata['matchCode']}",
        "timeline": "timeline.json",
        "manifest": "manifest.json",
    }
    manifest["phase"] = {
        "current": "publish",
        "status": "complete",
        "completed": list(
            dict.fromkeys(
                list((manifest.get("phase") or {}).get("completed") or [])
                + ["publish"]
            )
        ),
    }
    manifest["updatedAt"] = utc_now()
    timeline = _sanitized_timeline(load_json(paths.timeline), metadata)
    assert_sanitized(manifest, label="published manifest")
    assert_sanitized(timeline, label="published timeline")

    target = publish_root / str(metadata["matchCode"])
    target_manifest = target / "manifest.json"
    target_timeline = target / "timeline.json"
    if target_manifest.exists() and not force:
        existing = load_json(target_manifest)
        if (existing.get("rofl") or {}).get("sha256") != (
            manifest.get("rofl") or {}
        ).get("sha256"):
            raise IngestError(
                "published match differs; pass --force for atomic file replacement"
            )
    target.mkdir(parents=True, exist_ok=True)
    atomic_write_json(target_timeline, timeline, compact=True)
    atomic_write_json(target_manifest, manifest)
    atomic_write_json(paths.manifest, manifest)
    try:
        registry_result = match_registry.rebuild_registry(
            publish_root,
            strict=True,
        )
    except match_registry.RegistryError as exc:
        raise IngestError(f"published files written but registry rebuild failed: {exc}") from exc
    return {
        "phase": "publish",
        "ok": True,
        "directory": f"public/data/matches/{metadata['matchCode']}",
        "registry": {
            "matchCount": registry_result["matchCount"],
            "defaultMatchCode": registry_result["defaultMatchCode"],
        },
    }


def build_parser(phase: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__,
        usage=(
            "%(prog)s [inspect|capture|build|validate|publish] "
            "<BR1-….rofl> [options]"
        ),
    )
    parser.set_defaults(phase=phase)
    parser.add_argument("rofl", type=Path)
    parser.add_argument("--publish", action="store_true", help="Publish after default ingest")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--start-ms", type=int, default=None)
    parser.add_argument("--end-ms", type=int, default=None)
    parser.add_argument("--step-ms", type=int, default=DEFAULT_STEP_MS)
    parser.add_argument(
        "--hp-evidence",
        type=Path,
        default=None,
        help=(
            "Optional trusted timed same-match HP evidence for build/default ingest; "
            "stored durably for phase recovery"
        ),
    )
    parser.add_argument("--app", type=Path, default=replay_probe.DEFAULT_APP)
    parser.add_argument("--base-url", default=replay_probe.DEFAULT_BASE)
    parser.add_argument("--timeout", type=float, default=replay_probe.DEFAULT_TIMEOUT)
    return parser


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    args = list(sys.argv[1:] if argv is None else argv)
    phase = "ingest"
    if args and args[0] in PHASES:
        phase = args.pop(0)
    parsed = build_parser(phase).parse_args(args)
    if parsed.publish and phase != "ingest":
        raise IngestError("--publish is only valid with default ingest")
    if parsed.force and phase not in {"ingest", "inspect", "capture", "publish"}:
        raise IngestError(f"--force is not valid for {phase}")
    if parsed.hp_evidence is not None and phase not in {"ingest", "build"}:
        raise IngestError("--hp-evidence is only valid for build/default ingest")
    return parsed


def run(args: argparse.Namespace) -> dict[str, Any]:
    rofl_path = args.rofl.expanduser().resolve()
    metadata = rofl_metadata.inspect_rofl_metadata(rofl_path)
    config = capture_config(
        metadata,
        start_ms=args.start_ms,
        end_ms=args.end_ms,
        step_ms=args.step_ms,
    )
    paths = artifact_paths(str(metadata["matchCode"]))
    phase = args.phase
    results: list[dict[str, Any]] = []

    if phase == "inspect":
        results.append(
            inspect_phase(metadata, config, paths, force=bool(args.force))
        )
    elif phase == "capture":
        results.append(
            capture_phase(
                rofl_path,
                metadata,
                config,
                paths,
                force=bool(args.force),
                app_path=args.app,
                base_url=args.base_url,
                timeout=args.timeout,
            )
        )
    elif phase == "build":
        results.append(
            build_phase(
                metadata,
                config,
                paths,
                hp_evidence=args.hp_evidence,
            )
        )
    elif phase == "validate":
        results.append(validate_phase(metadata, config, paths))
    elif phase == "publish":
        results.append(
            publish_phase(
                metadata,
                config,
                paths,
                force=bool(args.force),
            )
        )
    else:
        capture_result = capture_phase(
            rofl_path,
            metadata,
            config,
            paths,
            force=bool(args.force),
            app_path=args.app,
            base_url=args.base_url,
            timeout=args.timeout,
        )
        results.append({"phase": "inspect", "ok": True})
        results.append(capture_result)
        results.append(
            build_phase(
                metadata,
                config,
                paths,
                hp_evidence=args.hp_evidence,
            )
        )
        results.append(validate_phase(metadata, config, paths))
        if args.publish:
            results.append(
                publish_phase(
                    metadata,
                    config,
                    paths,
                    force=bool(args.force),
                )
            )
    return {
        "ok": True,
        "matchCode": metadata["matchCode"],
        "artifactDirectory": f"artifacts/rofl/{metadata['matchCode']}",
        "phases": [result["phase"] for result in results],
        "results": results,
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    try:
        args = parse_args(argv)
        result = run(args)
    except (IngestError, rofl_metadata.RoflMetadataError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2), file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print(json.dumps({"ok": False, "error": "interrupted"}), file=sys.stderr)
        return 130
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
