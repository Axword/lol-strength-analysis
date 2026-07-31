#!/usr/bin/env python3
"""Validate a canonical rfc461 JSONL stream and its GameTimeline output.

The checks are intentionally provenance-aware: fountain coordinates are valid
only when explicitly marked as placeholders, and never count as live movement.
Use ``--require-live-positions`` for a calculator-safe import gate.
Use ``--product`` for real-match publication gates (rejects fixture/schema-proof
/synthetic/static-snapshot provenance and dishonest zero rows).

Calculator readiness defaults to strict all-frame (hp+combat+ranks on every
unit). Path1 living-post-seed is opt-in via ``--calculator-ready-policy
living_post_seed_v1`` or provenance ``calculatorReadyPolicy`` (dead and
pre-seed may stay unknown; default is never silently weakened).
"""
from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple


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
    # GRID live-stats / series-events adapters are research density only.
    # A gameID rewrite must not slip them past --product (R19 H2/H4).
    "grid_riot_livestats",
    "grid_series_events",
    "grid_riot",
    "grid_series",
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
    "grid_riot_livestats",
    "grid_series_events",
    "grid_riot",
    "grid_series",
)

# Per-unit health/combat/ranks sources that must never satisfy product known-flags.
NON_PRODUCT_UNIT_SOURCE_MARKERS = (
    "grid_riot_livestats",
    "grid_series_events",
    "grid_riot",
    "grid_series",
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
TRUSTED_HP_MODE_PERHERO = "timed_identity_bound_per_hero"
TRUSTED_HP_SCHEMA = "rofl-trusted-hp-v1"
TRUSTED_HP_SCHEMA_PERHERO = "rofl-trusted-hp-v1-perhero"
TRUSTED_HP_SCHEMAS = frozenset({TRUSTED_HP_SCHEMA, TRUSTED_HP_SCHEMA_PERHERO})
TRUSTED_HP_BINDING = "stable_identity_to_net_id"
MAX_TRUSTED_HP_TOLERANCE_MS = 500
# calculatorReady policies (default stays strict all-frame; Path1 living is opt-in).
CALCULATOR_READY_POLICY_STRICT = "strict_all_frame_v1"
CALCULATOR_READY_POLICY_LIVING_POST_SEED = "living_post_seed_v1"
CALCULATOR_READY_POLICIES = frozenset(
    {
        CALCULATOR_READY_POLICY_STRICT,
        CALCULATOR_READY_POLICY_LIVING_POST_SEED,
    }
)
DEFAULT_CALCULATOR_READY_POLICY = CALCULATOR_READY_POLICY_STRICT
# Riot tournament platforms use short numeric gameIDs (often 5–6 digits). Product
# publish is allowed only with an explicit disclosure + matching suggested ROFL name.
# Never treat gridSeriesId as gameID. Never invent HP.
TOURNAMENT_PLATFORM_RE = re.compile(r"^LOLTMNT\d+$", re.IGNORECASE)
MIN_TOURNAMENT_GAME_ID = 10_000

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
                # R20: ability ranks are independent of HP densify — UpgradeSpellAns
                # (636/1012) may be fused while health remains unavailable. Do not
                # force abilityRanksSource=unavailable_replay_api under hpCoverage=none.
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
                # R20: abilityRanksKnown may be true from UpgradeSpellAns fuse without HP.
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
    platform_id = (
        info.get("platformID")
        or provenance.get("platformID")
        or provenance.get("platformId")
        or tl_prov.get("platformID")
        or tl_prov.get("platformId")
    )
    return {
        "gameID": game_id,
        "gameName": game_name,
        "matchCode": match_code,
        "platformID": platform_id,
        "provenance": provenance,
        "timelineProvenance": tl_prov,
    }


def _disclosed_tournament_identity(
    *,
    platform_id: Any,
    game_id_int: int,
    provenance: JsonDict,
    tl_prov: JsonDict,
) -> bool:
    """True when a short LOLTMNT gameID is an explicitly disclosed tournament identity.

    Research→product path for pro-grid dumps: livestats rename-report yields
    platformID+gameID (e.g. LOLTMNT01-426746). Grid series ids must not be used
    as gameID. Disclosure is fail-closed without the explicit marker.
    """
    platform = str(platform_id or "").strip().upper()
    if not TOURNAMENT_PLATFORM_RE.fullmatch(platform):
        return False
    if game_id_int < MIN_TOURNAMENT_GAME_ID:
        return False
    disclosed = (
        provenance.get("tournamentIdentityDisclosed") is True
        or tl_prov.get("tournamentIdentityDisclosed") is True
    )
    if not disclosed:
        return False
    suggested = str(
        provenance.get("suggestedProductRofl")
        or tl_prov.get("suggestedProductRofl")
        or ""
    ).strip()
    expected = f"{platform}-{game_id_int}.rofl"
    if suggested != expected:
        return False
    # Optional cross-check: gridSeriesId is a dump key, never the match code.
    series = provenance.get("gridSeriesId") or tl_prov.get("gridSeriesId")
    if series is not None and str(series).strip() == str(game_id_int):
        return False
    return True


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
    if _contains_any(source, UNAVAILABLE_EVIDENCE_MARKERS) is not None:
        return False
    if _contains_any(source, NON_PRODUCT_UNIT_SOURCE_MARKERS) is not None:
        return False
    return True


def _finite_number(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _is_pe_hp_seed(unit: JsonDict) -> bool:
    """PE-proven HP seed (not hold_forward)."""
    return unit.get("hpKnown") is True and _norm_text(unit.get("hpSource")) == "pe"


def _is_pe_combat_seed(unit: JsonDict) -> bool:
    """PE FUR combat seed (Path1 wire / non-hold authoritative source)."""
    if unit.get("combatStatsKnown") is not True:
        return False
    source = _norm_text(unit.get("combatStatsSource") or unit.get("combatSource"))
    if not source or source == "hold_forward":
        return False
    return _source_is_authoritative(source)


def _resolve_calculator_ready_policy(
    *,
    cli_policy: Optional[str],
    provenance: JsonDict,
    timeline_provenance: JsonDict,
) -> str:
    raw = cli_policy
    if raw in (None, ""):
        raw = provenance.get("calculatorReadyPolicy")
    if raw in (None, ""):
        raw = timeline_provenance.get("calculatorReadyPolicy")
    if raw in (None, ""):
        return DEFAULT_CALCULATOR_READY_POLICY
    policy = _norm_text(raw)
    if policy not in CALCULATOR_READY_POLICIES:
        fail(
            "product gate: unknown calculatorReadyPolicy "
            f"{raw!r}; allowed={sorted(CALCULATOR_READY_POLICIES)}"
        )
    return policy


def evaluate_calculator_ready_policies(
    frames: List[JsonDict],
    *,
    expected_units: int,
    hp_hold_across_respawn: bool = False,
) -> dict:
    """Evaluate strict all-frame and Path1 living-post-seed calculatorReady.

    living_post_seed_v1 (product-honest Path1):
      - all expected heroes have ≥1 PE HP seed and ≥1 PE FUR combat seed
      - abilityRanksKnown density is 1.0
      - for alive units past HP seed in the current continuous alive segment
        and past the unit's first PE combat seed: require hp+combat+ranks known
      - dead and pre-seed (including post-death before HP re-seed) may stay unknown

    Default: HP seed is segment-scoped because Path1 HP hold clears on death.
    When provenance ``hpHoldAcrossRespawn=true``, the HP seed survives death so
    post-respawn hold_forward counts without a mid-game PE re-seed (dead frames
    still stay unknown / not living-required).
    Combat seed is first PE in the match (combat may hold across respawn).
    """
    frame_shapes_complete = bool(frames) and all(
        len(frame.get("units") or []) == expected_units for frame in frames
    )
    total_slots = 0
    ranks_known_slots = 0
    strict_all_hp = frame_shapes_complete
    strict_all_combat = frame_shapes_complete
    strict_all_ranks = frame_shapes_complete

    first_pe_hp: Dict[int, int] = {}
    first_pe_combat: Dict[int, int] = {}
    segment_hp_seeded: Dict[int, bool] = {}

    living_required = 0
    living_ok = 0
    living_miss = 0
    pre_seed_slots = 0
    dead_slots = 0
    miss_examples: List[dict] = []

    for frame in frames:
        frame_t = int(frame.get("t") or 0)
        for unit in frame.get("units") or []:
            total_slots += 1
            pid = int(unit.get("pid"))
            hp_known = unit.get("hpKnown") is True
            combat_known = unit.get("combatStatsKnown") is True
            ranks_known = unit.get("abilityRanksKnown") is True
            if ranks_known:
                ranks_known_slots += 1
            strict_all_hp = strict_all_hp and hp_known
            strict_all_combat = strict_all_combat and combat_known
            strict_all_ranks = strict_all_ranks and ranks_known

            alive = unit.get("alive") is True
            if not alive:
                # Legacy clear-on-death: wipe segment seed. Hold-across-respawn
                # keeps the seed so post-respawn hold_forward is living-required.
                if not hp_hold_across_respawn:
                    segment_hp_seeded.pop(pid, None)
                dead_slots += 1
                continue

            if _is_pe_hp_seed(unit):
                first_pe_hp.setdefault(pid, frame_t)
                segment_hp_seeded[pid] = True
            elif hp_known and _norm_text(unit.get("hpSource")) == "hold_forward":
                # Hold implies a prior PE seed (segment or across-respawn).
                segment_hp_seeded.setdefault(pid, True)

            if _is_pe_combat_seed(unit):
                first_pe_combat.setdefault(pid, frame_t)

            past_hp_seed = segment_hp_seeded.get(pid) is True
            past_combat_seed = (
                pid in first_pe_combat and frame_t >= int(first_pe_combat[pid])
            )
            if not past_hp_seed or not past_combat_seed:
                pre_seed_slots += 1
                continue

            living_required += 1
            if hp_known and combat_known and ranks_known:
                living_ok += 1
            else:
                living_miss += 1
                if len(miss_examples) < 8:
                    miss_examples.append(
                        {
                            "t": frame_t,
                            "pid": pid,
                            "hpKnown": hp_known,
                            "combatStatsKnown": combat_known,
                            "abilityRanksKnown": ranks_known,
                            "hpSource": unit.get("hpSource"),
                            "combatStatsSource": unit.get("combatStatsSource"),
                        }
                    )

    ranks_density = (
        float(ranks_known_slots) / float(total_slots) if total_slots else 0.0
    )
    heroes_pe_hp = len(first_pe_hp)
    heroes_pe_combat = len(first_pe_combat)
    seed_coverage_ok = (
        expected_units > 0
        and heroes_pe_hp >= expected_units
        and heroes_pe_combat >= expected_units
    )
    ranks_ok = total_slots > 0 and ranks_known_slots == total_slots
    living_postseed_ready = bool(
        frame_shapes_complete
        and seed_coverage_ok
        and ranks_ok
        and living_miss == 0
        and living_required > 0
    )
    strict_all_frame_ready = bool(
        strict_all_hp and strict_all_combat and strict_all_ranks
    )
    return {
        "strictAllFrameCalculatorReady": strict_all_frame_ready,
        "livingPostSeedCalculatorReady": living_postseed_ready,
        "strictAllHp": strict_all_hp,
        "strictAllCombat": strict_all_combat,
        "strictAllRanks": strict_all_ranks,
        "expectedUnits": expected_units,
        "heroesWithPeHpSeed": heroes_pe_hp,
        "heroesWithPeCombatSeed": heroes_pe_combat,
        "firstPeHpMsByPid": {str(k): v for k, v in sorted(first_pe_hp.items())},
        "firstPeCombatMsByPid": {
            str(k): v for k, v in sorted(first_pe_combat.items())
        },
        "ranksKnownSlots": ranks_known_slots,
        "totalSlots": total_slots,
        "ranksDensity": ranks_density,
        "livingRequiredSlots": living_required,
        "livingOkSlots": living_ok,
        "livingMissSlots": living_miss,
        "preSeedSlots": pre_seed_slots,
        "deadSlots": dead_slots,
        "livingMissExamples": miss_examples,
        "seedCoverageOk": seed_coverage_ok,
        "ranksDensityOk": ranks_ok,
        "hpHoldAcrossRespawn": bool(hp_hold_across_respawn),
    }


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

    schema = provenance.get("hpEvidenceSchema")
    if schema not in TRUSTED_HP_SCHEMAS:
        fail(
            f"product gate: trusted HP provenance hpEvidenceSchema must be one of "
            f"{sorted(TRUSTED_HP_SCHEMAS)} (got {schema!r})"
        )
    perhero = schema == TRUSTED_HP_SCHEMA_PERHERO or (
        provenance.get("hpEvidenceMode") == TRUSTED_HP_MODE_PERHERO
    )
    expected_mode = TRUSTED_HP_MODE_PERHERO if perhero else TRUSTED_HP_MODE
    required_provenance = {
        "hpEvidenceMode": expected_mode,
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
    if perhero and sample_coverage.get("sampleModel") not in (None, "per_hero"):
        fail("product gate: per-hero trusted HP sampleModel must be per_hero")

    hold_forward_disclosed = (
        provenance.get("hpHoldForward") is True
        or provenance.get("hpHoldForwardUsed") is True
    )
    hold_forward_policy = _norm_text(
        provenance.get("hpHoldForwardPolicy")
        or "until_next_seed_or_end_of_continuous_alive_segment"
    )
    if hold_forward_disclosed and not hold_forward_policy:
        fail("product gate: hpHoldForward requires a disclosed hpHoldForwardPolicy")

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
            coverage_label = frame_evidence.get("coverage")
            if perhero:
                if frame_evidence.get("source") != TRUSTED_HEALTH_SOURCE:
                    fail("product gate: trusted HP frame has mismatched source")
                if coverage_label == "known_at_sampled_frame":
                    if len(frame_trusted) != len(participants) or set(
                        frame_identities
                    ) != info_identities:
                        fail(
                            "product gate: per-hero all-known frame has mismatched annotation"
                        )
                elif coverage_label == "partial_known_at_sampled_frame":
                    if not (
                        0 < len(frame_trusted) < len(participants)
                        and len(set(frame_net_ids)) == len(frame_trusted)
                        and len(set(frame_identities)) == len(frame_trusted)
                        and set(frame_identities).issubset(info_identities)
                    ):
                        fail(
                            "product gate: per-hero partial frame has mismatched annotation"
                        )
                elif hold_forward_disclosed and coverage_label in (
                    "known_with_hold_forward",
                    "partial_known_with_hold_forward",
                ):
                    if not (
                        0 < len(frame_trusted) <= len(participants)
                        and len(set(frame_net_ids)) == len(frame_trusted)
                        and len(set(frame_identities)) == len(frame_trusted)
                        and set(frame_identities).issubset(info_identities)
                    ):
                        fail(
                            "product gate: per-hero hold-forward frame has mismatched annotation"
                        )
                    if coverage_label == "known_with_hold_forward" and len(
                        frame_trusted
                    ) != len(participants):
                        fail(
                            "product gate: known_with_hold_forward must cover all participants"
                        )
                    if coverage_label == "partial_known_with_hold_forward" and len(
                        frame_trusted
                    ) >= len(participants):
                        fail(
                            "product gate: partial_known_with_hold_forward must leave "
                            "at least one unmatched participant"
                        )
                else:
                    fail(
                        "product gate: per-hero trusted frame coverage must be "
                        "known_at_sampled_frame or partial_known_at_sampled_frame"
                        + (
                            " (or disclosed *_with_hold_forward)"
                            if hold_forward_disclosed
                            else ""
                        )
                    )
            elif len(frame_trusted) != len(participants) or (
                frame_evidence.get("source") != TRUSTED_HEALTH_SOURCE
                or coverage_label != "known_at_sampled_frame"
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
            health_coverage = _norm_text(participant.get("healthCoverage"))
            is_hold_forward_row = (
                hold_forward_disclosed and health_coverage == "known_hold_forward"
            )
            is_pe_row = health_coverage == "known_at_sampled_frame"
            if not is_pe_row and not is_hold_forward_row:
                fail(
                    "product gate: trusted HP row healthCoverage must be "
                    "known_at_sampled_frame"
                    + (
                        " or known_hold_forward when hpHoldForward is disclosed"
                        if hold_forward_disclosed
                        else ""
                    )
                    + f" (got {participant.get('healthCoverage')!r})"
                )
            # PE seeds stay within align tolerance; hold_forward may exceed it by design.
            delta_ok = (
                delta_ms >= 0
                if is_hold_forward_row
                else (0 <= delta_ms <= tolerance_ms)
            )
            if (
                not math.isfinite(hp)
                or not math.isfinite(hp_max)
                or hp < 0
                or hp_max <= 100
                or hp > hp_max
                or sample_time < 0
                or not delta_ok
                or net_id <= 0
                or participant.get("mMaxHPExplicit") is not True
                or participant.get("healthMaxEvidence") != "explicit_mMaxHP"
                or participant.get("healthIdentityBinding") != TRUSTED_HP_BINDING
                or participant.get("healthIdentityKey") not in info_identities
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
    if (
        not perhero
        and hp_coverage == "partial"
        and len(trusted) >= len(all_participants)
    ):
        fail("product gate: hpCoverage=partial understates full trusted coverage")
    if perhero and hp_coverage == "partial" and len(trusted) == 0:
        fail("product gate: per-hero partial coverage has zero trusted rows")
    if int(sample_coverage.get("fusedParticipantRows", -1)) != len(trusted):
        fail("product gate: trusted HP participant-row summary is inconsistent")
    if (
        int(sample_coverage.get("statsFrames", -1)) != len(stats)
        or int(sample_coverage.get("fusedFrames", -1)) != trusted_frame_count
        or int(sample_coverage.get("unmatchedFrames", -1))
        != len(stats) - trusted_frame_count
    ):
        fail("product gate: trusted HP frame/time summary is inconsistent")
    if not perhero and int(sample_coverage.get("sampleTimesUsed", -1)) != trusted_frame_count:
        fail("product gate: trusted HP sampleTimesUsed summary is inconsistent")
    if perhero:
        sample_times_used = int(sample_coverage.get("sampleTimesUsed", -1))
        if hold_forward_disclosed:
            seed_rows = int(sample_coverage.get("seedParticipantRows", -1))
            hold_rows = int(sample_coverage.get("holdForwardParticipantRows", -1))
            if seed_rows < 1 or hold_rows < 0 or seed_rows + hold_rows != len(trusted):
                fail(
                    "product gate: hold-forward trusted HP seed/hold row summary "
                    "is inconsistent"
                )
            if sample_times_used not in (seed_rows, int(sample_coverage.get("sampleCount", -1))):
                fail(
                    "product gate: hold-forward sampleTimesUsed must equal PE seed rows"
                )
        elif sample_times_used != len(trusted):
            fail(
                "product gate: per-hero sampleTimesUsed must equal trusted participant rows"
            )
    return {
        "trusted": True,
        "knownParticipantRows": len(trusted),
        "totalParticipantRows": len(all_participants),
        "timeToleranceMs": tolerance_ms,
        "sampleCount": int(sample_coverage["sampleCount"]),
        "sampleModel": "per_hero" if perhero else "all10",
        "hpHoldForward": hold_forward_disclosed,
    }


PRODUCT_AA_COVERAGE = "identity_bound_replay_packets"
PRODUCT_AA_SOURCE_KIND = "rofl_packet"
PRODUCT_AA_FIELD_SOURCE = "pe_proven_opcode_registry_v1"


def _valid_sha256(value: Any) -> bool:
    return bool(re.fullmatch(r"[0-9a-f]{64}", str(value or "")))


def _validate_product_action_timeline(
    rows: List[dict],
    timeline: dict,
    *,
    require_aa_timeline: bool,
) -> dict:
    """Validate a same-match, identity-bound basic-attack product channel.

    AA is an independently audited replay channel. It never contributes to
    calculatorReady and it may not be synthesized from HP deltas, skill casts,
    participant order, or an external research overlay.
    """
    provenance = dict(timeline.get("provenance") or {})
    coverage = _norm_text(provenance.get("aaCoverage"))
    timeline_attacks = timeline.get("basicAttack")
    jsonl_attacks = [
        row for row in rows if row.get("rfc461Schema") == "basic_attack"
    ]
    claims_product_aa = coverage == PRODUCT_AA_COVERAGE

    if require_aa_timeline and not claims_product_aa:
        fail(
            "product gate: --require-aa-timeline requires "
            f"aaCoverage={PRODUCT_AA_COVERAGE!r}, got {coverage!r}"
        )
    if not claims_product_aa:
        return {
            "ready": False,
            "coverage": coverage or "none",
            "basicAttackCount": 0,
            "participantCount": 0,
        }

    if not isinstance(timeline_attacks, list) or not timeline_attacks:
        fail("product gate: identity-bound AA coverage requires timeline.basicAttack")
    if not jsonl_attacks:
        fail("product gate: identity-bound AA coverage requires rfc461 basic_attack rows")
    if provenance.get("aaCalculatorReadyImpact") != "none":
        fail("product gate: AA timeline must disclose aaCalculatorReadyImpact='none'")
    for key in (
        "aaSourceRoflSha256",
        "aaReplayManifestSha256",
        "aaIdentityEvidenceSha256",
        "aaOpcodeRegistrySha256",
    ):
        if not _valid_sha256(provenance.get(key)):
            fail(f"product gate: AA timeline has invalid or missing {key}")
    if provenance.get("aaIdentityBinding") != "stable_puuid_full_riot_id_to_net_id":
        fail("product gate: AA timeline lacks stable PUUID/full Riot ID identity binding")
    if int(provenance.get("aaEventCount") or -1) != len(timeline_attacks):
        fail("product gate: aaEventCount does not match timeline.basicAttack")
    if len(jsonl_attacks) != len(timeline_attacks):
        fail("product gate: rfc461 and timeline basic-attack counts differ")

    participants = timeline.get("participants") or []
    expected_game_id = int(provenance.get("gameId") or 0)
    if expected_game_id <= 0:
        fail("product gate: AA timeline requires provenance.gameId")
    roster_pids = {
        int(participant.get("participantID"))
        for participant in participants
        if participant.get("participantID") is not None
    }
    if len(roster_pids) != 10:
        fail("product gate: AA timeline requires the ten-player timeline roster")
    duration_ms = int(timeline.get("durationMs") or 0)
    if duration_ms <= 0:
        fail("product gate: AA timeline requires a positive durationMs")

    netid_to_pid: Dict[int, int] = {}
    pid_to_netid: Dict[int, int] = {}
    normalized_timeline: List[Tuple[int, int, int]] = []
    for index, event in enumerate(timeline_attacks):
        if not isinstance(event, dict):
            fail(f"product gate: basicAttack[{index}] is not an object")
        try:
            t_ms = int(event.get("tMs"))
            participant_id = int(event.get("participantId"))
            net_id = int(event.get("netId"))
        except (TypeError, ValueError):
            fail(f"product gate: basicAttack[{index}] has invalid time/identity")
        if t_ms < 0 or t_ms > duration_ms:
            fail(f"product gate: basicAttack[{index}] time is outside timeline duration")
        if participant_id not in roster_pids or net_id <= 0:
            fail(f"product gate: basicAttack[{index}] is not bound to the timeline roster")
        if event.get("sourceKind") != PRODUCT_AA_SOURCE_KIND:
            fail(f"product gate: basicAttack[{index}] has unsupported sourceKind")
        if event.get("fieldSource") != PRODUCT_AA_FIELD_SOURCE:
            fail(f"product gate: basicAttack[{index}] has unsupported fieldSource")
        if event.get("researchOnly") is True:
            fail(f"product gate: basicAttack[{index}] is researchOnly")
        if "amount" in event:
            fail(f"product gate: basicAttack[{index}] must not contain damage amount")
        prior_pid = netid_to_pid.setdefault(net_id, participant_id)
        prior_netid = pid_to_netid.setdefault(participant_id, net_id)
        if prior_pid != participant_id or prior_netid != net_id:
            fail("product gate: AA netId and participantId mapping is not one-to-one")
        normalized_timeline.append((t_ms, participant_id, net_id))

    normalized_jsonl: List[Tuple[int, int, int]] = []
    for index, event in enumerate(jsonl_attacks):
        try:
            t_ms = int(event.get("gameTime"))
            participant_id = int(event.get("participantID"))
            net_id = int(event.get("netId"))
        except (TypeError, ValueError):
            fail(f"product gate: rfc461 basic_attack row {index} has invalid identity")
        if event.get("sourceKind") != PRODUCT_AA_SOURCE_KIND:
            fail(f"product gate: rfc461 basic_attack row {index} has unsupported sourceKind")
        if event.get("fieldSource") != PRODUCT_AA_FIELD_SOURCE:
            fail(f"product gate: rfc461 basic_attack row {index} has unsupported fieldSource")
        if event.get("participantIdSource") != "stable_identity_to_net_id":
            fail(
                f"product gate: rfc461 basic_attack row {index} lacks stable identity source"
            )
        if int(event.get("gameID") or 0) != expected_game_id:
            fail(f"product gate: rfc461 basic_attack row {index} has wrong gameID")
        normalized_jsonl.append((t_ms, participant_id, net_id))

    if sorted(normalized_jsonl) != sorted(normalized_timeline):
        fail("product gate: rfc461 and timeline basic-attack rows differ")
    covered_pids = set(pid_to_netid)
    if covered_pids != roster_pids:
        fail(
            "product gate: AA timeline must contain decoded attacks for all ten heroes "
            f"(covered={len(covered_pids)}/10)"
        )
    return {
        "ready": True,
        "coverage": coverage,
        "basicAttackCount": len(timeline_attacks),
        "participantCount": len(covered_pids),
    }


def validate_product(
    jsonl: Path,
    timeline_path: Path,
    *,
    require_calculator_ready: bool = False,
    calculator_ready_policy: Optional[str] = None,
    require_aa_timeline: bool = False,
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
    policy = _resolve_calculator_ready_policy(
        cli_policy=calculator_ready_policy,
        provenance=provenance,
        timeline_provenance=tl_prov,
    )
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
    if (
        coverage.get("productEligible") is False
        or provenance.get("productEligible") is False
        or tl_prov.get("productEligible") is False
    ):
        fail("product gate: productEligible=false cannot publish")

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
    platform_id = identity.get("platformID")
    if game_id in (None, "", 0, "0"):
        fail("product gate: missing gameID/match identity for real-match publish")
    try:
        game_id_int = int(game_id)
    except (TypeError, ValueError):
        fail(f"product gate: gameID is not an integer match code ({game_id!r})")
    tournament_disclosed = _disclosed_tournament_identity(
        platform_id=platform_id,
        game_id_int=game_id_int,
        provenance=provenance,
        tl_prov=tl_prov,
    )
    if game_id_int < 1_000_000 and not tournament_disclosed:
        fail(
            f"product gate: gameID {game_id_int} does not look like a real match code "
            "(tournament LOLTMNT* identities require tournamentIdentityDisclosed=true "
            "and suggestedProductRofl=<PLATFORM>-<gameID>.rofl)"
        )

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
    for frame in frames:
        frame_t = int(frame.get("t") or 0)
        canonical_participants = canonical_by_time.get(frame_t, {})
        for unit in frame.get("units") or []:
            pid = int(unit.get("pid"))
            _validate_known_unit_evidence(
                frame_t=frame_t,
                unit=unit,
                participant=canonical_participants.get(pid),
                provenance=provenance,
            )

    hp_hold_across_respawn = (
        provenance.get("hpHoldAcrossRespawn") is True
        or tl_prov.get("hpHoldAcrossRespawn") is True
    )
    ready_metrics = evaluate_calculator_ready_policies(
        frames,
        expected_units=expected_units,
        hp_hold_across_respawn=hp_hold_across_respawn,
    )
    all_hp = bool(ready_metrics["strictAllHp"])
    all_combat = bool(ready_metrics["strictAllCombat"])
    all_ranks = bool(ready_metrics["strictAllRanks"])
    strict_all_frame_ready_flags = bool(ready_metrics["strictAllFrameCalculatorReady"])
    living_postseed_ready_flags = bool(ready_metrics["livingPostSeedCalculatorReady"])

    calculator_claim = any(
        token in notes
        for token in (
            "calculator-ready",
            "calculator ready",
            "calculator-capable",
            "calculator capable",
        )
    ) or provenance.get("calculatorReady") is True or tl_prov.get("calculatorReady") is True

    if calculator_claim and (
        provenance.get("combatStatsKnownWouldEmit") is False
        or tl_prov.get("combatStatsKnownWouldEmit") is False
    ):
        fail(
            "product gate: calculatorReady claim contradicts "
            "combatStatsKnownWouldEmit=false"
        )

    hp_source_ok = hp_cov in ("full", "partial") and "snapshot" not in hp_cov
    # Fountain placeholders / absent live coverage can never satisfy calculatorReady
    # even if ranks fuse or partial known-flags look dense (R21 H3).
    position_live_ok = bool(
        pos_cov
        and pos_cov
        not in (
            "",
            "none",
            "unknown",
            "fountain_placeholder_only",
            "fountain_placeholder",
        )
        and "fountain_placeholder" not in pos_cov
        and "placeholder_only" not in pos_cov
    )
    # Shared infrastructure: trusted HP + live positions + non-snapshot coverage.
    # livestats known-flags alone must never flip the claim (R19 E6b). Fountain red (R21).
    infra_ok = bool(hp_source_ok and trusted_hp["trusted"] and position_live_ok)
    strict_calculator_ready = bool(strict_all_frame_ready_flags and infra_ok)
    living_calculator_ready = bool(living_postseed_ready_flags and infra_ok)
    if policy == CALCULATOR_READY_POLICY_LIVING_POST_SEED:
        calculator_ready = living_calculator_ready
    else:
        calculator_ready = strict_calculator_ready

    if require_calculator_ready or calculator_claim:
        if not calculator_ready:
            if policy == CALCULATOR_READY_POLICY_LIVING_POST_SEED:
                fail(
                    "product gate: calculator-ready claim under living_post_seed_v1 requires "
                    "PE HP+combat seeds for all heroes, ranks density 1.0, and "
                    "hpKnown+combatStatsKnown+abilityRanksKnown on every living post-seed "
                    "frame/unit (dead/pre-seed may stay unknown), plus non-snapshot "
                    "hpCoverage, rofl-trusted-hp-v1, and non-fountain live positions "
                    f"(livingReady={living_postseed_ready_flags} "
                    f"livingMiss={ready_metrics['livingMissSlots']} "
                    f"peHpHeroes={ready_metrics['heroesWithPeHpSeed']}/"
                    f"{expected_units} peCombatHeroes="
                    f"{ready_metrics['heroesWithPeCombatSeed']}/{expected_units} "
                    f"ranksDensity={ready_metrics['ranksDensity']!r} "
                    f"hpCoverage={hp_cov!r} hpTrusted={trusted_hp['trusted']} "
                    f"positionCoverage={pos_cov!r} policy={policy!r})"
                )
            fail(
                "product gate: calculator-ready claim requires hpKnown + combatStatsKnown + "
                "abilityRanksKnown with authoritative canonical evidence on every frame/unit, "
                "non-snapshot hpCoverage, rofl-trusted-hp-v1, and non-fountain live positions "
                f"(hp={all_hp} combat={all_combat} ranks={all_ranks} hpCoverage={hp_cov!r} "
                f"hpTrusted={trusted_hp['trusted']} positionCoverage={pos_cov!r} "
                f"policy={policy!r})"
            )

    aa_timeline = _validate_product_action_timeline(
        rows,
        timeline,
        require_aa_timeline=require_aa_timeline,
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
        "calculatorReady": calculator_ready,
        "calculatorReadyPolicy": policy,
        "strictAllFrameCalculatorReady": strict_calculator_ready,
        "livingPostSeedCalculatorReady": living_calculator_ready,
        "calculatorReadyMetrics": ready_metrics,
        "calculatorFrameCount": len(frames),
        "aaTimelineReady": aa_timeline["ready"],
        "aaCoverage": aa_timeline["coverage"],
        "basicAttackCount": aa_timeline["basicAttackCount"],
        "aaParticipantCount": aa_timeline["participantCount"],
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
    ap.add_argument(
        "--calculator-ready-policy",
        choices=sorted(CALCULATOR_READY_POLICIES),
        default=None,
        help=(
            "Disclosed calculatorReady policy. Default is strict_all_frame_v1 "
            "(every frame/unit). Use living_post_seed_v1 for Path1 living-post-seed "
            "(dead/pre-seed may stay unknown). Also accepted via provenance "
            "calculatorReadyPolicy."
        ),
    )
    ap.add_argument(
        "--require-aa-timeline",
        action="store_true",
        help=(
            "With --product, require same-match identity-bound basic_attack rows "
            "in both rfc461 and GameTimeline. This does not affect calculatorReady."
        ),
    )
    args = ap.parse_args()
    if args.require_aa_timeline and not args.product:
        fail("--require-aa-timeline requires --product")
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
            calculator_ready_policy=args.calculator_ready_policy,
            require_aa_timeline=args.require_aa_timeline,
        )
        result["productPublication"] = product
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
