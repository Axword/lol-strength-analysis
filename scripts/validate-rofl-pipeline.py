#!/usr/bin/env python3
"""Validate a canonical rfc461 JSONL stream and its GameTimeline output.

The checks are intentionally provenance-aware: fountain coordinates are valid
only when explicitly marked as placeholders, and never count as live movement.
Use ``--require-live-positions`` for a calculator-safe import gate.
Use ``--product`` for real-match publication gates (rejects fixture/schema-proof
/synthetic/static-snapshot provenance and dishonest zero rows).
"""
from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Dict, Iterable, List, Optional, Set


def fail(message: str) -> None:
    raise SystemExit(f"FAIL: {message}")


# Provenance that may prove schemas in research/tests but must never publish.
NON_PRODUCT_SOURCE_KIND_MARKERS = (
    "deterministic_test",
    "schema_proof",
    "schema-proof",
    "fixture",
    "fur_parity",
    "research_static",
    "research_timed",
    "static_hp_snapshot",
    "static_snapshot",
    "synthetic",
    "decoded_replay_packets_synthetic",
)

NON_PRODUCT_SOURCE_MARKERS = (
    "schema_proof",
    "schema-proof",
    "fixture",
    "fur_parity",
    "short_ms_regression",
    "maknee_decoded_packets",
    "research_only",
    "live_fur_schema",
)

NON_PRODUCT_HP_COVERAGE = frozenset(
    {
        "snapshot_fused",
        "research_static",
        "research_timed_fused",
    }
)
TRUSTED_HEALTH_SOURCE = "rofl2_replication_decrypt_timed_identity_bound"
TRUSTED_HP_MODE = "timed_identity_bound"
TRUSTED_HP_BINDING = "stable_identity_to_net_id"
MAX_TRUSTED_HP_TOLERANCE_MS = 500

# FUR parity / schema-proof fixture roster (CreateHero champions).
FIXTURE_ROSTER_CHAMPIONS = frozenset(
    {
        "Gnar",
        "LeeSin",
        "Ahri",
        "Jinx",
        "Thresh",
        "Darius",
        "Vi",
        "Syndra",
        "Samira",
        "Nautilus",
    }
)

FIXTURE_PLAYER_NAME_MARKERS = frozenset(
    {f"blue{i}" for i in range(1, 6)} | {f"red{i}" for i in range(1, 6)}
)

# Minimal structural alias for career/combat dict checks.
JsonDict = Dict[str, Any]


UNAVAILABLE_EVIDENCE_MARKERS = (
    "unavailable",
    "unknown",
    "placeholder",
    "static_snapshot",
    "static snapshot",
    "fixture",
    "synthetic",
)

SCORE_ONLY_COVERAGE_MARKERS = (
    "liveclient_scores",
    "liveclient score",
    "scores_only",
    "scores only",
    "kda_cs_vision",
)

FULL_CAREER_COVERAGE_MARKERS = (
    "full",
    "riot_live_stats",
    "riot live stats",
    "authoritative_career",
)

SCORE_ONLY_CAREER_KEYS = frozenset(
    {
        "kills",
        "deaths",
        "assists",
        "cs",
        "visionScore",
        "careerSource",
        "careerCoverage",
        "scoreSource",
        "fieldSources",
        "unavailableFields",
    }
)

COMBAT_FIELDS = (
    "attackDamage",
    "abilityPower",
    "armor",
    "magicResist",
    "attackSpeed",
)


def _validated_motion_audit(timeline: JsonDict) -> Optional[JsonDict]:
    summary = (timeline.get("provenance") or {}).get("motionAudit")
    if summary is None:
        return None
    if not isinstance(summary, dict):
        fail("motionAudit provenance must be an object")
    annotated = [
        unit.get("motionFromPrevious")
        for frame in timeline.get("frames") or []
        for unit in frame.get("units") or []
        if unit.get("motionFromPrevious") is not None
    ]
    classifications = Counter()
    for segment in annotated:
        if not isinstance(segment, dict) or segment.get("kind") != "discontinuity":
            fail("motionFromPrevious must be a discontinuity object")
        classification = segment.get("classification")
        if classification not in {
            "death_respawn",
            "recall_or_teleport",
            "unexplained",
        }:
            fail(f"invalid motion discontinuity classification: {classification!r}")
        classifications[classification] += 1
    expected = {
        "discontinuityCount": len(annotated),
        "deathRespawnCount": classifications["death_respawn"],
        "recallTeleportCount": classifications["recall_or_teleport"],
        "unexplainedCount": classifications["unexplained"],
    }
    for key, value in expected.items():
        if int(summary.get(key, -1)) != value:
            fail(
                f"motionAudit {key}={summary.get(key)!r} "
                f"does not match annotated segments={value}"
            )
    return dict(summary)


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
    if provenance.get("positionCoverage") in (
        "full",
        "partial",
        "full_at_sampled_frames",
        "synthetic_path_walk",
    ) and live_rows == 0:
        fail("coverage claims positions but no participant has a non-placeholder source")
    if provenance.get("positionCoverage") == "none" and live_rows:
        fail("coverage says no positions but participant rows claim live positions")

    timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
    if timeline.get("provenance", {}).get("positionCoverage") != provenance.get("positionCoverage"):
        fail("GameTimeline provenance does not match rfc461 coverage")
    if timeline.get("provenance", {}).get("hpCoverage") != provenance.get("hpCoverage"):
        fail("GameTimeline HP provenance does not match rfc461 coverage")
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
        "motionAudit": _validated_motion_audit(timeline),
    }


def _norm_text(value: Any) -> str:
    return str(value or "").strip().lower()


def _contains_any(haystack: str, needles: Iterable[str]) -> Optional[str]:
    for needle in needles:
        if needle in haystack:
            return needle
    return None


def _collect_identity(info: dict, coverage: dict, timeline: dict) -> Dict[str, Any]:
    provenance = dict(coverage.get("provenance") or {})
    tl_prov = dict(timeline.get("provenance") or {})
    game_id = info.get("gameID")
    if game_id is None:
        game_id = provenance.get("gameId") or provenance.get("matchCode")
    game_name = info.get("gameName")
    match_code = (
        provenance.get("matchCode")
        or tl_prov.get("matchCode")
        or timeline.get("name")
        or game_name
    )
    return {
        "gameID": game_id,
        "gameName": game_name,
        "matchCode": match_code,
        "provenance": provenance,
        "timelineProvenance": tl_prov,
    }


def _roster_champions(info: dict, timeline: dict) -> Set[str]:
    champs: Set[str] = set()
    for p in info.get("participants") or []:
        name = p.get("championName")
        if name:
            champs.add(str(name))
    for p in timeline.get("participants") or []:
        name = p.get("championName") or p.get("champ")
        if name:
            champs.add(str(name))
    return champs


def _roster_player_names(info: dict, timeline: dict) -> Set[str]:
    names: Set[str] = set()
    for p in info.get("participants") or []:
        for key in ("playerName", "summonerName"):
            raw = p.get(key)
            if raw:
                names.add(str(raw).split("#", 1)[0].strip().lower())
    for p in timeline.get("participants") or []:
        for key in ("summonerName", "name"):
            raw = p.get(key)
            if raw:
                names.add(str(raw).split("#", 1)[0].strip().lower())
    return names


def _career_has_fabrication_marker(career: JsonDict) -> bool:
    if not isinstance(career, dict) or not career:
        return False
    # End-box KDA pasted onto every frame is never scrubbable career history.
    touch = _norm_text(career.get("touchModel"))
    return "end_box" in touch or "kda_only" in touch


def _evidence_source(
    participant: JsonDict,
    provenance: JsonDict,
    participant_key: str,
    provenance_keys: Iterable[str],
) -> str:
    source = participant.get(participant_key)
    if source in (None, ""):
        for key in provenance_keys:
            source = provenance.get(key)
            if source not in (None, ""):
                break
    return _norm_text(source)


def _source_is_authoritative(source: str) -> bool:
    if not source:
        return False
    return _contains_any(source, UNAVAILABLE_EVIDENCE_MARKERS) is None


def _finite_number(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _career_coverage_mode(
    career: JsonDict,
    provenance: JsonDict,
    timeline_provenance: JsonDict,
) -> Optional[str]:
    values = [
        career.get("careerSource"),
        career.get("careerCoverage"),
        career.get("scoreSource"),
        provenance.get("careerCoverage"),
        provenance.get("scoreCoverage"),
        provenance.get("careerSource"),
        provenance.get("scoreSource"),
        timeline_provenance.get("careerCoverage"),
        timeline_provenance.get("scoreCoverage"),
        timeline_provenance.get("careerSource"),
        timeline_provenance.get("scoreSource"),
    ]
    declaration = " ".join(_norm_text(value) for value in values if value not in (None, ""))
    if not declaration:
        return None
    if _contains_any(declaration, UNAVAILABLE_EVIDENCE_MARKERS):
        return "none"
    if _contains_any(declaration, SCORE_ONLY_COVERAGE_MARKERS):
        return "scores_only"
    if _contains_any(declaration, FULL_CAREER_COVERAGE_MARKERS):
        return "full"
    return None


def _validate_career_frames(
    frames: List[dict],
    *,
    has_career_stats: bool,
    provenance: JsonDict,
    timeline_provenance: JsonDict,
) -> None:
    for frame in frames:
        frame_t = frame.get("t")
        for unit in frame.get("units") or []:
            career = unit.get("career")
            if career is None:
                if has_career_stats:
                    fail(
                        "product gate: hasCareerStats=true but unit missing career "
                        f"(t={frame_t} pid={unit.get('pid')})"
                    )
                continue
            if not has_career_stats:
                fail(
                    "product gate: unit carries career while hasCareerStats=false "
                    f"(t={frame_t} pid={unit.get('pid')})"
                )
            if not isinstance(career, dict) or not career:
                fail(
                    "product gate: career must be a non-empty object "
                    f"(t={frame_t} pid={unit.get('pid')})"
                )
            if _career_has_fabrication_marker(career):
                fail(
                    "product gate: career uses non-scrubbable end-box/KDA-only data "
                    f"(t={frame_t} pid={unit.get('pid')} "
                    f"touchModel={career.get('touchModel')!r})"
                )
            mode = _career_coverage_mode(career, provenance, timeline_provenance)
            if mode in (None, "none"):
                fail(
                    "product gate: career row lacks authoritative career/score coverage "
                    f"(t={frame_t} pid={unit.get('pid')})"
                )
            if mode == "scores_only":
                unsupported = sorted(set(career) - SCORE_ONLY_CAREER_KEYS)
                if unsupported:
                    fail(
                        "product gate: score-only career materializes unsupported fields "
                        f"(t={frame_t} pid={unit.get('pid')} fields={unsupported})"
                    )


def _canonical_rows_by_time(rows: List[dict]) -> Dict[int, Dict[int, dict]]:
    by_time: Dict[int, Dict[int, dict]] = {}
    for row in rows:
        if row.get("rfc461Schema") != "stats_update":
            continue
        game_time = int(row.get("gameTime") or 0)
        by_time[game_time] = {
            int(participant.get("participantID")): participant
            for participant in row.get("participants") or []
        }
    return by_time


def _validate_known_unit_evidence(
    *,
    frame_t: int,
    unit: JsonDict,
    participant: Optional[JsonDict],
    provenance: JsonDict,
) -> tuple[bool, bool, bool]:
    pid = unit.get("pid")
    hp_known = unit.get("hpKnown") is True
    combat_known = unit.get("combatStatsKnown") is True
    ranks_known = unit.get("abilityRanksKnown") is True

    if (hp_known or combat_known or ranks_known) and participant is None:
        fail(
            "product gate: known timeline evidence has no matching canonical participant "
            f"(t={frame_t} pid={pid})"
        )
    participant = participant or {}

    if hp_known:
        hp = _finite_number(unit.get("hp"))
        hp_max = _finite_number(unit.get("hpMax"))
        canonical_hp = _finite_number(participant.get("health"))
        canonical_hp_max = _finite_number(participant.get("healthMax"))
        source = _evidence_source(
            participant,
            provenance,
            "healthSource",
            ("hpSource", "healthSource"),
        )
        if (
            hp is None
            or hp_max is None
            or hp < 0
            or hp_max <= 0
            or hp > hp_max
            or canonical_hp is None
            or canonical_hp_max is None
            or canonical_hp < 0
            or canonical_hp_max <= 0
            or canonical_hp > canonical_hp_max
            or not _source_is_authoritative(source)
        ):
            fail(
                "product gate: hpKnown=true without valid authoritative HP evidence "
                f"(t={frame_t} pid={pid} source={source!r})"
            )

    if combat_known:
        timeline_values = {key: _finite_number(unit.get(key)) for key in ("ad", "ap", "armor", "mr", "as")}
        canonical_values = {
            key: _finite_number(participant.get(key))
            for key in COMBAT_FIELDS
        }
        source = _evidence_source(
            participant,
            provenance,
            "combatStatsSource",
            ("combatStatsSource",),
        )
        if (
            any(value is None for value in timeline_values.values())
            or (timeline_values["ad"] or 0) <= 0
            or (timeline_values["as"] or 0) <= 0
            or any(value is None for value in canonical_values.values())
            or (canonical_values["attackDamage"] or 0) <= 0
            or (canonical_values["attackSpeed"] or 0) <= 0
            or not _source_is_authoritative(source)
        ):
            fail(
                "product gate: combatStatsKnown=true without valid non-placeholder "
                f"combat evidence (t={frame_t} pid={pid} source={source!r})"
            )

    if ranks_known:
        rank_keys = ("ability1Level", "ability2Level", "ability3Level", "ability4Level")
        canonical_ranks = [_finite_number(participant.get(key)) for key in rank_keys]
        timeline_ranks = [_finite_number(unit.get(key)) for key in ("q", "w", "e", "r")]
        source = _evidence_source(
            participant,
            provenance,
            "abilityRanksSource",
            ("abilityRanksSource",),
        )
        if (
            any(value is None or value < 0 for value in canonical_ranks)
            or any(value is None or value < 0 for value in timeline_ranks)
            or not _source_is_authoritative(source)
        ):
            fail(
                "product gate: abilityRanksKnown=true without authoritative rank evidence "
                f"(t={frame_t} pid={pid} source={source!r})"
            )

    return hp_known, combat_known, ranks_known


def _validate_trusted_hp_evidence(
    rows: List[dict],
    provenance: JsonDict,
    hp_coverage: str,
) -> dict:
    stats = [row for row in rows if row.get("rfc461Schema") == "stats_update"]
    info = next(
        (row for row in rows if row.get("rfc461Schema") == "game_info"),
        {},
    )
    info_identities: set[str] = set()
    for participant in info.get("participants") or []:
        puuid = str(participant.get("puuid") or "").strip()
        full_riot_id = str(participant.get("summonerName") or "").strip()
        if puuid:
            info_identities.add(f"puuid:{puuid}")
        elif full_riot_id and "#" in full_riot_id:
            info_identities.add(f"riotid:{full_riot_id.casefold()}")
    all_participants = [
        participant
        for row in stats
        for participant in row.get("participants") or []
    ]
    trusted = [
        participant
        for participant in all_participants
        if participant.get("healthSource") == TRUSTED_HEALTH_SOURCE
    ]
    legacy_decrypt = [
        participant
        for participant in all_participants
        if _norm_text(participant.get("healthSource"))
        in ("rofl2_replication_decrypt", "replication_decoded")
    ]
    claims_trusted = provenance.get("hpEvidenceMode") is not None
    if legacy_decrypt:
        fail(
            "product gate: decrypted HP lacks timed stable-identity evidence "
            "(legacy/CreateHero-order source)"
        )
    if not trusted:
        if claims_trusted:
            fail("product gate: trusted HP provenance has no trusted participant rows")
        return {
            "trusted": False,
            "knownParticipantRows": 0,
            "totalParticipantRows": len(all_participants),
        }

    required_provenance = {
        "hpEvidenceMode": TRUSTED_HP_MODE,
        "hpEvidenceSchema": "rofl-trusted-hp-v1",
        "hpEvidenceSource": TRUSTED_HEALTH_SOURCE,
        "hpEvidenceTimed": True,
        "hpStaticSnapshot": False,
        "hpFixtureEvidence": False,
        "hpCreateHeroOrderFallback": False,
        "hpIdentityBinding": TRUSTED_HP_BINDING,
        "hpTimeUnit": "milliseconds",
        "hpTimeClock": "replay_game_time",
    }
    for key, expected in required_provenance.items():
        if provenance.get(key) != expected:
            fail(
                f"product gate: trusted HP provenance {key} must be {expected!r} "
                f"(got {provenance.get(key)!r})"
            )
    if hp_coverage not in ("full", "partial"):
        fail(f"product gate: trusted HP has invalid coverage {hp_coverage!r}")
    try:
        tolerance_ms = int(provenance.get("hpTimeToleranceMs"))
    except (TypeError, ValueError):
        fail("product gate: trusted HP tolerance is absent/invalid")
    if not 0 <= tolerance_ms <= MAX_TRUSTED_HP_TOLERANCE_MS:
        fail("product gate: trusted HP time tolerance is not defensible")
    sample_coverage = provenance.get("hpSampleCoverage")
    if not isinstance(sample_coverage, dict):
        fail("product gate: trusted HP sample coverage summary is absent")
    if int(sample_coverage.get("sampleCount") or 0) < 2:
        fail("product gate: trusted HP requires at least two timed samples")

    trusted_frame_count = 0
    for row in stats:
        participants = row.get("participants") or []
        frame_trusted = [
            participant
            for participant in participants
            if participant.get("healthSource") == TRUSTED_HEALTH_SOURCE
        ]
        frame_evidence = row.get("hpEvidence")
        if not isinstance(frame_evidence, dict):
            fail("product gate: trusted HP frame lacks explicit evidence coverage")
        if frame_trusted:
            trusted_frame_count += 1
            frame_net_ids = [participant.get("healthNetId") for participant in frame_trusted]
            frame_identities = [
                participant.get("healthIdentityKey") for participant in frame_trusted
            ]
            if len(frame_trusted) != len(participants) or (
                frame_evidence.get("source") != TRUSTED_HEALTH_SOURCE
                or frame_evidence.get("coverage") != "known_at_sampled_frame"
                or len(set(frame_net_ids)) != len(frame_trusted)
                or len(set(frame_identities)) != len(frame_trusted)
                or set(frame_identities) != info_identities
            ):
                fail("product gate: trusted HP frame has partial/mismatched annotation")
        elif (
            frame_evidence.get("source") != TRUSTED_HEALTH_SOURCE
            or frame_evidence.get("coverage") != "unknown_no_aligned_sample"
        ):
            fail("product gate: unmatched HP frame lacks honest unknown annotation")

    for participant in all_participants:
        source = participant.get("healthSource")
        if source == TRUSTED_HEALTH_SOURCE:
            try:
                hp = float(participant.get("health"))
                hp_max = float(participant.get("healthMax"))
                sample_time = int(participant.get("healthSampleGameTimeMs"))
                delta_ms = int(participant.get("healthSampleDeltaMs"))
                net_id = int(participant.get("healthNetId"))
            except (TypeError, ValueError):
                fail("product gate: trusted HP row has invalid values/timing/netId")
            if (
                not math.isfinite(hp)
                or not math.isfinite(hp_max)
                or hp < 0
                or hp_max <= 100
                or hp > hp_max
                or sample_time < 0
                or delta_ms < 0
                or delta_ms > tolerance_ms
                or net_id <= 0
                or participant.get("mMaxHPExplicit") is not True
                or participant.get("healthMaxEvidence") != "explicit_mMaxHP"
                or participant.get("healthIdentityBinding") != TRUSTED_HP_BINDING
                or participant.get("healthIdentityKey") not in info_identities
                or participant.get("healthCoverage") != "known_at_sampled_frame"
            ):
                fail(
                    "product gate: trusted HP row lacks timed binding or explicit mMaxHP"
                )
        elif source in ("unavailable_replay_api", "unavailable", "unknown"):
            if "health" in participant or "healthMax" in participant:
                fail("product gate: unmatched trusted-HP row materializes unknown health")
        else:
            fail(
                "product gate: trusted HP stream mixes an unvalidated health source "
                f"{source!r}"
            )

    if hp_coverage == "full" and len(trusted) != len(all_participants):
        fail("product gate: hpCoverage=full has unmatched participant rows")
    if hp_coverage == "partial" and len(trusted) >= len(all_participants):
        fail("product gate: hpCoverage=partial understates full trusted coverage")
    if int(sample_coverage.get("fusedParticipantRows", -1)) != len(trusted):
        fail("product gate: trusted HP participant-row summary is inconsistent")
    if (
        int(sample_coverage.get("statsFrames", -1)) != len(stats)
        or int(sample_coverage.get("fusedFrames", -1)) != trusted_frame_count
        or int(sample_coverage.get("unmatchedFrames", -1))
        != len(stats) - trusted_frame_count
        or int(sample_coverage.get("sampleTimesUsed", -1))
        != trusted_frame_count
    ):
        fail("product gate: trusted HP frame/time summary is inconsistent")
    return {
        "trusted": True,
        "knownParticipantRows": len(trusted),
        "totalParticipantRows": len(all_participants),
        "timeToleranceMs": tolerance_ms,
        "sampleCount": int(sample_coverage["sampleCount"]),
    }


def validate_product(
    jsonl: Path,
    timeline_path: Path,
    *,
    require_calculator_ready: bool = False,
) -> dict:
    """Real-match publication gates. Fail closed on fixture/schema-proof paths."""
    rows = [json.loads(line) for line in jsonl.read_text(encoding="utf-8").splitlines() if line.strip()]
    coverage = next((row for row in rows if row.get("rfc461Schema") == "rofl_coverage"), None)
    info = next((row for row in rows if row.get("rfc461Schema") == "game_info"), None)
    if not coverage or not info:
        fail("product gate requires rofl_coverage and game_info")
    timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
    provenance = dict(coverage.get("provenance") or {})
    tl_prov = dict(timeline.get("provenance") or {})
    source = _norm_text(coverage.get("source") or provenance.get("source") or timeline.get("source"))
    source_kind = _norm_text(provenance.get("sourceKind") or tl_prov.get("sourceKind"))
    notes = " ".join(
        [
            _norm_text(provenance.get("notes")),
            _norm_text(tl_prov.get("notes")),
            _norm_text(coverage.get("notes")),
            _norm_text(timeline.get("name")),
            _norm_text(timeline.get("id")),
        ]
    )

    if provenance.get("publicationBlocked") is True or tl_prov.get("publicationBlocked") is True:
        fail("product gate: publicationBlocked provenance cannot publish")
    if provenance.get("researchOnly") is True or tl_prov.get("researchOnly") is True:
        fail("product gate: researchOnly provenance cannot publish")
    if provenance.get("schemaProof") is True or tl_prov.get("schemaProof") is True:
        fail("product gate: schemaProof provenance cannot publish as a real match")

    hit = _contains_any(source_kind, NON_PRODUCT_SOURCE_KIND_MARKERS)
    if hit:
        fail(f"product gate: non-product sourceKind marker {hit!r} ({source_kind!r})")
    hit = _contains_any(source, NON_PRODUCT_SOURCE_MARKERS)
    if hit:
        fail(f"product gate: non-product source marker {hit!r} ({source!r})")
    hit = _contains_any(notes, ("schema proof", "schema_proof", "fixture roster", "research only", "static snapshot"))
    if hit:
        fail(f"product gate: notes/id claim non-product path ({hit!r})")

    hp_cov = _norm_text(provenance.get("hpCoverage") or tl_prov.get("hpCoverage"))
    if hp_cov in NON_PRODUCT_HP_COVERAGE or "snapshot" in hp_cov:
        fail(f"product gate: hpCoverage {hp_cov!r} is research/static-only")
    trusted_hp = _validate_trusted_hp_evidence(rows, provenance, hp_cov)

    pos_cov = _norm_text(provenance.get("positionCoverage") or tl_prov.get("positionCoverage"))
    if pos_cov in ("synthetic_path_walk", "synthetic"):
        fail(f"product gate: positionCoverage {pos_cov!r} is synthetic, not native")
    if provenance.get("positionSynthesis") or tl_prov.get("positionSynthesis"):
        fail("product gate: positionSynthesis marker is fixture/synthetic movement")
    if pos_cov == "full_at_sampled_frames" and (
        "synthetic" in source_kind or provenance.get("positionSynthesis")
    ):
        fail("product gate: synthetic path walking cannot claim full_at_sampled_frames")

    identity = _collect_identity(info, coverage, timeline)
    game_id = identity["gameID"]
    game_name = identity["gameName"]
    match_code = identity["matchCode"]
    if game_id in (None, "", 0, "0"):
        fail("product gate: missing gameID/match identity for real-match publish")
    try:
        game_id_int = int(game_id)
    except (TypeError, ValueError):
        fail(f"product gate: gameID is not an integer match code ({game_id!r})")
    if game_id_int < 1_000_000:
        fail(f"product gate: gameID {game_id_int} does not look like a real match code")

    digits = re.sub(r"\D", "", str(match_code or ""))
    if digits and digits != str(game_id_int):
        fail(
            f"product gate: matchCode/name {match_code!r} inconsistent with gameID {game_id_int}"
        )
    if game_name not in (None, ""):
        name_digits = re.sub(r"\D", "", str(game_name))
        if name_digits and name_digits != str(game_id_int):
            fail(
                f"product gate: gameName {game_name!r} inconsistent with gameID {game_id_int}"
            )

    champs = _roster_champions(info, timeline)
    fixture_hits = sorted(champs & FIXTURE_ROSTER_CHAMPIONS)
    # Full FUR fixture set (or near-full) under a real match code is quarantine.
    if len(fixture_hits) >= 8:
        fail(
            "product gate: fixture roster champions under real match identity: "
            + ", ".join(fixture_hits)
        )
    players = _roster_player_names(info, timeline)
    if players & FIXTURE_PLAYER_NAME_MARKERS:
        fail(
            "product gate: fixture player-name markers under real match identity: "
            + ", ".join(sorted(players & FIXTURE_PLAYER_NAME_MARKERS))
        )

    frames = timeline.get("frames") or []
    _validate_career_frames(
        frames,
        has_career_stats=timeline.get("hasCareerStats") is True,
        provenance=provenance,
        timeline_provenance=tl_prov,
    )

    canonical_by_time = _canonical_rows_by_time(rows)
    expected_units = len(info.get("participants") or [])
    frame_shapes_complete = bool(frames) and all(
        len(frame.get("units") or []) == expected_units for frame in frames
    )
    all_hp = frame_shapes_complete
    all_combat = frame_shapes_complete
    all_ranks = frame_shapes_complete
    for frame in frames:
        frame_t = int(frame.get("t") or 0)
        canonical_participants = canonical_by_time.get(frame_t, {})
        for unit in frame.get("units") or []:
            pid = int(unit.get("pid"))
            hp_known, combat_known, ranks_known = _validate_known_unit_evidence(
                frame_t=frame_t,
                unit=unit,
                participant=canonical_participants.get(pid),
                provenance=provenance,
            )
            all_hp = all_hp and hp_known
            all_combat = all_combat and combat_known
            all_ranks = all_ranks and ranks_known

    calculator_claim = any(
        token in notes
        for token in (
            "calculator-ready",
            "calculator ready",
            "calculator-capable",
            "calculator capable",
        )
    ) or provenance.get("calculatorReady") is True or tl_prov.get("calculatorReady") is True

    hp_source_ok = hp_cov in ("full", "partial") and "snapshot" not in hp_cov
    if require_calculator_ready or calculator_claim:
        if not (all_hp and all_combat and all_ranks and hp_source_ok):
            fail(
                "product gate: calculator-ready claim requires hpKnown + combatStatsKnown + "
                "abilityRanksKnown with authoritative canonical evidence on every frame/unit "
                "and non-snapshot hpCoverage "
                f"(hp={all_hp} combat={all_combat} ranks={all_ranks} hpCoverage={hp_cov!r})"
            )

    return {
        "ok": True,
        "product": True,
        "gameID": game_id_int,
        "matchCode": str(match_code or game_id_int),
        "sourceKind": provenance.get("sourceKind"),
        "positionCoverage": provenance.get("positionCoverage"),
        "hpCoverage": provenance.get("hpCoverage"),
        "hpTrusted": trusted_hp["trusted"],
        "hpTrustedParticipantRows": trusted_hp["knownParticipantRows"],
        "positionOnly": hp_cov in ("", "none", "unknown"),
        "calculatorReady": bool(all_hp and all_combat and all_ranks and hp_source_ok),
        "calculatorFrameCount": len(frames),
        "rosterChampions": sorted(champs),
        "motionAudit": _validated_motion_audit(timeline),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--jsonl", type=Path, required=True)
    ap.add_argument("--timeline", type=Path, required=True)
    ap.add_argument("--require-live-positions", action="store_true")
    ap.add_argument(
        "--product",
        action="store_true",
        help=(
            "Real-match publication gates: reject fixture/schema-proof/synthetic/"
            "static-snapshot provenance, identity mismatches, and unknown-as-zero rows"
        ),
    )
    ap.add_argument(
        "--require-calculator-ready",
        action="store_true",
        help="With --product, also require HP+combat+ranks known under honest provenance",
    )
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
    if args.product:
        product = validate_product(
            args.jsonl,
            args.timeline,
            require_calculator_ready=args.require_calculator_ready,
        )
        result["productPublication"] = product
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
