#!/usr/bin/env python3
"""Finalize a calculator-ready replay with a same-match basic-attack timeline.

This is deliberately narrow. It does not discover opcodes, infer attacks from
HP deltas, assign participant IDs by packet order, or publish a match. It:

1. verifies the raw ROFL hash and ten-player roster against a replay manifest;
2. verifies a match-bound PUUID/full-Riot-ID/netId binding;
3. extracts only patch-registered basic-attack packets whose ``block.param`` is
   one of those ten bound hero netIds;
4. writes identity-bound rfc461 and GameTimeline rows; and
5. requires both the product calculator gate and the AA timeline gate.

Private replay and tournament data stay local. The output is suitable for
local product verification, not automatic publication.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from rofl2_probe import extract_segments_resilient, parse_rofl2  # noqa: E402
from rofl2_unicorn_packet_drive import extract_blocks_py  # noqa: E402

DEFAULT_OPCODE_REGISTRY = SCRIPTS / "data/lol_packet_opcodes.v1.json"
VALIDATOR = SCRIPTS / "validate-rofl-pipeline.py"
AA_SOURCE_KIND = "rofl_packet"
AA_FIELD_SOURCE = "pe_proven_opcode_registry_v1"
AA_COVERAGE = "identity_bound_replay_packets"


class FinalizeError(RuntimeError):
    """Raised when same-match provenance cannot be established."""


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FinalizeError(f"cannot read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise FinalizeError(f"expected JSON object in {path}")
    return value


def _required_text(value: Any, label: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise FinalizeError(f"missing {label}")
    return text


def _required_int(value: Any, label: str) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise FinalizeError(f"missing or invalid {label}: {value!r}") from exc
    if number <= 0:
        raise FinalizeError(f"missing or invalid {label}: {value!r}")
    return number


def _full_riot_id(row: Mapping[str, Any]) -> str:
    explicit = str(row.get("fullRiotId") or "").strip()
    if explicit:
        return explicit
    game_name = str(row.get("RIOT_ID_GAME_NAME") or "").strip()
    tag = str(row.get("RIOT_ID_TAG_LINE") or "").strip()
    return f"{game_name}#{tag}" if game_name and tag else ""


def _raw_roster(rofl_info: Mapping[str, Any]) -> list[dict[str, Any]]:
    meta = rofl_info.get("meta")
    if not isinstance(meta, Mapping):
        raise FinalizeError("ROFL metadata is missing")
    try:
        players = json.loads(str(meta.get("statsJson") or ""))
    except json.JSONDecodeError as exc:
        raise FinalizeError("ROFL statsJson is invalid") from exc
    if not isinstance(players, list) or len(players) != 10:
        raise FinalizeError(
            f"ROFL must contain exactly ten statsJson players, got {len(players) if isinstance(players, list) else 'invalid'}"
        )
    roster: list[dict[str, Any]] = []
    for participant_id, player in enumerate(players, start=1):
        if not isinstance(player, Mapping):
            raise FinalizeError(f"invalid ROFL player row {participant_id}")
        roster.append(
            {
                "participantID": participant_id,
                "puuid": _required_text(player.get("PUUID"), "ROFL PUUID"),
                "fullRiotId": _required_text(
                    _full_riot_id(player), "ROFL full Riot ID"
                ),
                "champion": _required_text(player.get("SKIN"), "ROFL champion"),
                "teamID": _required_int(player.get("TEAM"), "ROFL team ID"),
            }
        )
    if len({p["puuid"] for p in roster}) != 10:
        raise FinalizeError("ROFL PUUID roster is not unique")
    return roster


def _index_unique(
    rows: Iterable[Mapping[str, Any]], key: str, label: str
) -> dict[Any, Mapping[str, Any]]:
    indexed: dict[Any, Mapping[str, Any]] = {}
    for row in rows:
        value = row.get(key)
        if value in (None, ""):
            raise FinalizeError(f"{label} row missing {key}")
        if value in indexed:
            raise FinalizeError(f"{label} contains duplicate {key}={value!r}")
        indexed[value] = row
    return indexed


def verify_same_match_binding(
    *,
    rofl: Path,
    replay_manifest: Mapping[str, Any],
    identity_evidence: Mapping[str, Any],
    timeline: Mapping[str, Any],
) -> dict[str, Any]:
    """Return the verified match identity and netId map, or fail closed."""
    rofl_sha = sha256_file(rofl)
    manifest_match = replay_manifest.get("match")
    manifest_rofl = replay_manifest.get("rofl")
    if not isinstance(manifest_match, Mapping) or not isinstance(
        manifest_rofl, Mapping
    ):
        raise FinalizeError("replay manifest is missing match/rofl sections")
    if rofl_sha != _required_text(manifest_rofl.get("sha256"), "manifest ROFL hash"):
        raise FinalizeError("raw ROFL hash does not match replay manifest")

    evidence_match = identity_evidence.get("match")
    evidence_rofl = identity_evidence.get("rofl")
    binding = identity_evidence.get("identityBinding")
    if (
        not isinstance(evidence_match, Mapping)
        or not isinstance(evidence_rofl, Mapping)
        or not isinstance(binding, Mapping)
    ):
        raise FinalizeError("identity evidence is missing match/rofl/identityBinding")
    if evidence_rofl.get("sha256") != rofl_sha:
        raise FinalizeError("identity evidence is bound to a different ROFL hash")
    if binding.get("complete") is not True:
        raise FinalizeError("identity evidence binding is incomplete")
    if binding.get("createHeroOrderFallback") is not False:
        raise FinalizeError("identity evidence used CreateHero/order fallback")
    if binding.get("method") != "stable_identity_to_net_id":
        raise FinalizeError("identity evidence lacks stable_identity_to_net_id")
    if binding.get("pidStampMethod") not in (
        "slim_roster_puuid_join",
        "slim_roster_fullriotid_join",
    ):
        raise FinalizeError("identity evidence lacks a stable PUUID/full Riot ID pid stamp")
    if identity_evidence.get("identityOracleProven") is not True:
        raise FinalizeError("identity evidence oracle is not proven")
    manifest_roster_hash = _required_text(
        replay_manifest.get("rosterHash"), "manifest roster hash"
    )
    if identity_evidence.get("rosterHash") != manifest_roster_hash:
        raise FinalizeError("identity evidence roster hash does not match replay manifest")

    identity_fields = (
        ("gameId", "gameId"),
        ("matchCode", "matchCode"),
        ("gridSeriesId", "gridSeriesId"),
        ("gridGameIndex", "gridGameIndex"),
    )
    for manifest_key, evidence_key in identity_fields:
        if str(manifest_match.get(manifest_key)) != str(
            evidence_match.get(evidence_key)
        ):
            raise FinalizeError(
                f"identity evidence {evidence_key} does not match replay manifest"
            )

    rofl_info = parse_rofl2(rofl)
    raw_roster = _raw_roster(rofl_info)
    raw_by_puuid = _index_unique(raw_roster, "puuid", "ROFL roster")

    manifest_rows = replay_manifest.get("participants")
    bound_rows = binding.get("participants")
    timeline_rows = timeline.get("participants")
    if not all(
        isinstance(rows, list) and len(rows) == 10
        for rows in (manifest_rows, bound_rows, timeline_rows)
    ):
        raise FinalizeError("manifest, binding, and timeline must each have ten players")
    manifest_by_puuid = _index_unique(manifest_rows, "puuid", "replay manifest")
    bound_by_puuid = _index_unique(bound_rows, "puuid", "identity binding")
    timeline_by_pid = _index_unique(
        timeline_rows, "participantID", "timeline participants"
    )
    if set(raw_by_puuid) != set(manifest_by_puuid) or set(raw_by_puuid) != set(
        bound_by_puuid
    ):
        raise FinalizeError("same-match PUUID rosters differ")

    netid_to_pid: dict[int, int] = {}
    pid_to_netid: dict[int, int] = {}
    for puuid, raw in raw_by_puuid.items():
        manifest_row = manifest_by_puuid[puuid]
        bound = bound_by_puuid[puuid]
        raw_pid = _required_int(raw.get("participantID"), "ROFL participant ID")
        manifest_pid = _required_int(
            manifest_row.get("participantID"), "manifest participant ID"
        )
        bound_pid = _required_int(
            bound.get("participantID"), "bound participant ID"
        )
        if len({raw_pid, manifest_pid, bound_pid}) != 1:
            raise FinalizeError(f"participant ID mismatch for PUUID {puuid}")
        if _required_text(bound.get("fullRiotId"), "bound full Riot ID") != raw[
            "fullRiotId"
        ]:
            raise FinalizeError(f"full Riot ID mismatch for PUUID {puuid}")
        if _required_text(bound.get("champion"), "bound champion") != raw["champion"]:
            raise FinalizeError(f"champion mismatch for PUUID {puuid}")
        timeline_row = timeline_by_pid.get(raw_pid)
        if timeline_row is None:
            raise FinalizeError(f"timeline missing participant {raw_pid}")
        if timeline_row.get("championName") != raw["champion"]:
            raise FinalizeError(f"timeline champion mismatch for participant {raw_pid}")
        if timeline_row.get("summonerName") != raw["fullRiotId"]:
            raise FinalizeError(f"timeline Riot ID mismatch for participant {raw_pid}")
        net_id = _required_int(bound.get("netId"), "bound hero netId")
        if net_id in netid_to_pid or raw_pid in pid_to_netid:
            raise FinalizeError("identity binding netId/participant ID is not one-to-one")
        netid_to_pid[net_id] = raw_pid
        pid_to_netid[raw_pid] = net_id

    timeline_prov = timeline.get("provenance")
    if not isinstance(timeline_prov, Mapping):
        raise FinalizeError("timeline provenance is missing")
    game_id = _required_int(manifest_match.get("gameId"), "manifest game ID")
    if int(timeline_prov.get("gameId") or 0) != game_id:
        raise FinalizeError("timeline game ID does not match replay manifest")
    if str(timeline_prov.get("gridSeriesId")) != str(
        manifest_match.get("gridSeriesId")
    ):
        raise FinalizeError("timeline GRID series does not match replay manifest")
    if int(timeline_prov.get("gridGameIndex") or 0) != int(
        manifest_match.get("gridGameIndex") or 0
    ):
        raise FinalizeError("timeline GRID game index does not match replay manifest")

    return {
        "gameID": game_id,
        "matchCode": str(manifest_match.get("matchCode")),
        "gridSeriesId": str(manifest_match.get("gridSeriesId")),
        "gridGameIndex": int(manifest_match.get("gridGameIndex")),
        "platformID": str(manifest_match.get("platformId")),
        "patch": _required_text(manifest_rofl.get("patch"), "manifest patch"),
        "build": _required_text(manifest_rofl.get("build"), "manifest build"),
        "roflSha256": rofl_sha,
        "roflInfo": rofl_info,
        "netIdToParticipantId": netid_to_pid,
    }


def load_basic_attack_registry(
    registry_path: Path, patch: str, build: str
) -> dict[str, Any]:
    registry = _load_json(registry_path)
    if registry.get("schema") != "lol-packet-opcode-registry-v1":
        raise FinalizeError("unsupported packet opcode registry schema")
    patch_row = (registry.get("patches") or {}).get(patch)
    if not isinstance(patch_row, Mapping):
        raise FinalizeError(f"no basic-attack opcode proof for patch {patch}")
    if patch_row.get("clientBuild") != build:
        raise FinalizeError(
            f"opcode registry build {patch_row.get('clientBuild')!r} does not match {build!r}"
        )
    proof = patch_row.get("proof")
    attacks = patch_row.get("basicAttack")
    if not isinstance(proof, Mapping) or not isinstance(attacks, Mapping):
        raise FinalizeError("opcode registry patch row is incomplete")
    if len(attacks) != 4 or len(set(attacks.values())) != 4:
        raise FinalizeError("opcode registry must contain four unique AA packet opcodes")
    for key in ("sourceBinarySha256", "sourceEvidenceSha256"):
        value = str(proof.get(key) or "")
        if len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
            raise FinalizeError(f"opcode registry has invalid {key}")
    return {
        "registry": registry,
        "registrySha256": sha256_file(registry_path),
        "proof": dict(proof),
        "opcodes": {int(value): str(name) for name, value in attacks.items()},
    }


def extract_identity_bound_basic_attacks(
    *,
    rofl_info: Mapping[str, Any],
    netid_to_pid: Mapping[int, int],
    opcodes: Mapping[int, str],
    duration_ms: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    extracted = extract_segments_resilient(bytes(rofl_info["payload"]))
    events: list[dict[str, Any]] = []
    packet_counts: Counter[str] = Counter()
    participant_counts: Counter[int] = Counter()
    rejected_unbound = 0
    for segment in extracted["segments"]:
        if int(segment.get("type") or 0) != 1:
            continue
        for block in extract_blocks_py(segment["bytes"], max_blocks=500_000):
            opcode = int(block["channel"])
            if opcode not in opcodes:
                continue
            net_id = int(block.get("param") or 0)
            participant_id = netid_to_pid.get(net_id)
            if participant_id is None:
                rejected_unbound += 1
                continue
            t_ms = int(round(float(block["time"]) * 1000.0))
            if t_ms < 0 or t_ms > duration_ms:
                raise FinalizeError(
                    f"basic-attack packet time {t_ms} is outside timeline duration"
                )
            packet_name = opcodes[opcode]
            events.append(
                {
                    "tMs": t_ms,
                    "participantId": participant_id,
                    "netId": net_id,
                    "sourceKind": AA_SOURCE_KIND,
                    "fieldSource": AA_FIELD_SOURCE,
                }
            )
            packet_counts[packet_name] += 1
            participant_counts[participant_id] += 1
    events.sort(key=lambda row: (row["tMs"], row["participantId"], row["netId"]))
    if not events:
        raise FinalizeError("no identity-bound basic-attack packets were extracted")
    if set(participant_counts) != set(netid_to_pid.values()):
        missing = sorted(set(netid_to_pid.values()) - set(participant_counts))
        raise FinalizeError(f"AA timeline does not cover all ten heroes: missing {missing}")
    return events, {
        "segmentCount": len(extracted["segments"]),
        "segmentSkipCount": int(extracted.get("skip_count") or 0),
        "segmentLeftoverBytes": int(extracted.get("leftover") or 0),
        "rejectedUnboundAttackPackets": rejected_unbound,
        "packetCounts": dict(sorted(packet_counts.items())),
        "participantCounts": {
            str(pid): participant_counts[pid] for pid in sorted(participant_counts)
        },
    }


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise FinalizeError(f"invalid JSONL line {line_number}: {exc}") from exc
        if not isinstance(row, dict):
            raise FinalizeError(f"JSONL line {line_number} is not an object")
        rows.append(row)
    return rows


def build_final_documents(
    *,
    source_jsonl: Path,
    timeline: Mapping[str, Any],
    identity: Mapping[str, Any],
    attacks: Sequence[Mapping[str, Any]],
    replay_manifest_sha256: str,
    identity_evidence_sha256: str,
    opcode_registry_sha256: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Build normalized rfc461 and GameTimeline documents without mutating inputs."""
    rows = _read_jsonl(source_jsonl)
    coverage = next(
        (row for row in rows if row.get("rfc461Schema") == "rofl_coverage"), None
    )
    if coverage is None:
        raise FinalizeError("source JSONL lacks rofl_coverage")
    if int(coverage.get("gameID") or 0) != int(identity["gameID"]):
        raise FinalizeError("source JSONL game ID does not match replay manifest")

    prov_patch = {
        "calculatorReady": True,
        "calculatorReadyPolicy": "living_post_seed_v1",
        "combatStatsKnownWouldEmit": True,
        "aaCoverage": AA_COVERAGE,
        "damageCoverage": "none",
        "aaEventCount": len(attacks),
        "aaSourceRoflSha256": identity["roflSha256"],
        "aaReplayManifestSha256": replay_manifest_sha256,
        "aaIdentityEvidenceSha256": identity_evidence_sha256,
        "aaOpcodeRegistrySha256": opcode_registry_sha256,
        "aaIdentityBinding": "stable_puuid_full_riot_id_to_net_id",
        "aaCalculatorReadyImpact": "none",
    }
    coverage["provenance"] = {
        **dict(coverage.get("provenance") or {}),
        **prov_patch,
    }
    coverage["calculatorReady"] = True
    decoded = list(coverage.get("decoded") or [])
    if "basic_attack_identity_bound_replay_packets" not in decoded:
        decoded.append("basic_attack_identity_bound_replay_packets")
    coverage["decoded"] = decoded

    for attack in attacks:
        rows.append(
            {
                "rfc461Schema": "basic_attack",
                "gameID": identity["gameID"],
                "gameTime": int(attack["tMs"]),
                "participantID": int(attack["participantId"]),
                "netId": int(attack["netId"]),
                "sourceKind": AA_SOURCE_KIND,
                "fieldSource": AA_FIELD_SOURCE,
                "participantIdSource": "stable_identity_to_net_id",
            }
        )

    final_timeline = json.loads(json.dumps(timeline))
    final_timeline["provenance"] = {
        **dict(final_timeline.get("provenance") or {}),
        **prov_patch,
    }
    final_timeline["basicAttack"] = [dict(row) for row in attacks]
    final_timeline.pop("damageDealt", None)
    final_timeline.pop("actionEvents", None)
    return rows, final_timeline


def _jsonl_text(rows: Sequence[Mapping[str, Any]]) -> str:
    return "".join(
        json.dumps(row, separators=(",", ":"), ensure_ascii=False) + "\n"
        for row in rows
    )


def _run_validator(jsonl: Path, timeline: Path) -> dict[str, Any]:
    command = [
        sys.executable,
        str(VALIDATOR),
        "--product",
        "--require-calculator-ready",
        "--calculator-ready-policy",
        "living_post_seed_v1",
        "--require-aa-timeline",
        "--jsonl",
        str(jsonl),
        "--timeline",
        str(timeline),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise FinalizeError(
            "final product validation failed: "
            + (result.stderr.strip() or result.stdout.strip())
        )
    try:
        report = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise FinalizeError("validator did not return JSON") from exc
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rofl", type=Path, required=True)
    parser.add_argument("--source-jsonl", type=Path, required=True)
    parser.add_argument("--source-timeline", type=Path, required=True)
    parser.add_argument("--replay-manifest", type=Path, required=True)
    parser.add_argument("--identity-evidence", type=Path, required=True)
    parser.add_argument(
        "--opcode-registry", type=Path, default=DEFAULT_OPCODE_REGISTRY
    )
    parser.add_argument("--output-jsonl", type=Path, required=True)
    parser.add_argument("--output-timeline", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    args = parser.parse_args()

    input_paths = (
        args.rofl,
        args.source_jsonl,
        args.source_timeline,
        args.replay_manifest,
        args.identity_evidence,
        args.opcode_registry,
    )
    missing = [str(path) for path in input_paths if not path.is_file()]
    if missing:
        raise SystemExit("missing input files: " + ", ".join(missing))
    if args.output_jsonl.resolve() == args.source_jsonl.resolve():
        raise SystemExit("output JSONL must differ from source JSONL")
    if args.output_timeline.resolve() == args.source_timeline.resolve():
        raise SystemExit("output timeline must differ from source timeline")

    try:
        timeline = _load_json(args.source_timeline)
        replay_manifest = _load_json(args.replay_manifest)
        identity_evidence = _load_json(args.identity_evidence)
        identity = verify_same_match_binding(
            rofl=args.rofl,
            replay_manifest=replay_manifest,
            identity_evidence=identity_evidence,
            timeline=timeline,
        )
        registry = load_basic_attack_registry(
            args.opcode_registry, identity["patch"], identity["build"]
        )
        duration_ms = _required_int(timeline.get("durationMs"), "timeline duration")
        attacks, extraction = extract_identity_bound_basic_attacks(
            rofl_info=identity["roflInfo"],
            netid_to_pid=identity["netIdToParticipantId"],
            opcodes=registry["opcodes"],
            duration_ms=duration_ms,
        )
        replay_manifest_sha = sha256_file(args.replay_manifest)
        identity_evidence_sha = sha256_file(args.identity_evidence)
        rows, final_timeline = build_final_documents(
            source_jsonl=args.source_jsonl,
            timeline=timeline,
            identity=identity,
            attacks=attacks,
            replay_manifest_sha256=replay_manifest_sha,
            identity_evidence_sha256=identity_evidence_sha,
            opcode_registry_sha256=registry["registrySha256"],
        )

        with tempfile.TemporaryDirectory(prefix="calculator-ready-finalize-") as tmp:
            temp_dir = Path(tmp)
            temp_jsonl = temp_dir / "events.rfc461.jsonl"
            temp_timeline = temp_dir / "timeline.json"
            temp_jsonl.write_text(_jsonl_text(rows), encoding="utf-8")
            temp_timeline.write_text(
                json.dumps(final_timeline, separators=(",", ":"), ensure_ascii=False)
                + "\n",
                encoding="utf-8",
            )
            validation = _run_validator(temp_jsonl, temp_timeline)
            summary = {
                "schema": "calculator-ready-replay-finalization-v1",
                "ok": True,
                "publicationPerformed": False,
                "match": {
                    key: identity[key]
                    for key in (
                        "gameID",
                        "matchCode",
                        "gridSeriesId",
                        "gridGameIndex",
                        "platformID",
                        "patch",
                        "build",
                    )
                },
                "roflSha256": identity["roflSha256"],
                "replayManifestSha256": replay_manifest_sha,
                "identityEvidenceSha256": identity_evidence_sha,
                "opcodeRegistrySha256": registry["registrySha256"],
                "opcodeProof": registry["proof"],
                "basicAttackCount": len(attacks),
                "extraction": extraction,
                "validator": validation,
                "notes": [
                    "AA packets do not contribute to calculatorReady.",
                    "No damage amounts were decoded or inferred.",
                    "No fixture, participant-order, or cross-match identity fallback was used.",
                    "No public match registry entry was created.",
                ],
            }
            temp_summary = temp_dir / "summary.json"
            temp_summary.write_text(
                json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )

            for output in (args.output_jsonl, args.output_timeline, args.summary):
                output.parent.mkdir(parents=True, exist_ok=True)
            os.replace(temp_jsonl, args.output_jsonl)
            os.replace(temp_timeline, args.output_timeline)
            os.replace(temp_summary, args.summary)
    except (FinalizeError, OSError, ValueError) as exc:
        print(f"FAIL {exc}", file=sys.stderr)
        return 2

    print(
        json.dumps(
            {
                "ok": True,
                "gameID": identity["gameID"],
                "calculatorReady": True,
                "aaTimelineReady": True,
                "basicAttackCount": len(attacks),
                "outputTimeline": str(args.output_timeline),
                "outputJsonl": str(args.output_jsonl),
                "summary": str(args.summary),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
