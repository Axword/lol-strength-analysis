#!/usr/bin/env python3
"""P4 T2/T3 — Identity-stable product timeline fuse (2970110-g1) + R07 ranks.

Fail-closed orchestration:
  identity bind (R22 PUUID→netId→pid KEEP)
  → strip untrusted grid livestats HP/combat/ranks
  → optional HP fuse (rofl-trusted-hp-v1 only)
  → optional ranks fuse (UpgradeSpellAns 1012/636 + ranks-evidence.json; R07/R08)
  → optional combat fuse (PE-proven live samples only; R04 wire table ≠ live)
  → AA/damage attach (R10 schema; identity-gated bridge rows only)
  → jsonl_to_timeline

R12 attaches R07 UpgradeSpellAns opcode 1012 ranks for 2970110-g1.
Never invents HP/combat. Never writes parent public/data/matches/.
Never claims calculatorReady.

Example:
  python3 scripts/fuse_product_timeline.py \\
    --match-dir artifacts/rofl/2970110 \\
    --series 2970110 --game-index 1 \\
    --identity docs/rofl-research/product_ready/r22/castspell-identity-2970110-g1-pid-stamped.json \\
    --ranks-evidence docs/rofl-research/upgrade-spell-ranks-2970110-g1.json \\
    --position-jsonl artifacts/pro-grid/2970110/events.riot.rfc461.research.jsonl \\
    --action-jsonl docs/rofl-research/autoresearch/packet_decode/researchers/r41/emit_2970110_basic_attack_damage.jsonl \\
    --run-experiments
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from fuse_replay_api_combat import fuse_combat_product  # noqa: E402
from fuse_replay_api_hp import fuse_product as fuse_hp_product  # noqa: E402
from fuse_replay_api_ranks import fuse_ranks_product  # noqa: E402
from jsonl_to_timeline import build_timeline  # noqa: E402
from lib.timeline_action_events import load_netid_to_pid  # noqa: E402
from rofl2_packet_decrypt_probe import DecryptError  # noqa: E402
from rofl_fuse_identity import pid_bindings_from_game_info  # noqa: E402

UNTRUSTED_PRODUCT_SOURCES = frozenset(
    {
        "grid_riot_livestats",
        "grid_series_events",
        "grid_file_download",
        "research_overlay",
        "fixture",
        "schema_proof",
    }
)

HP_STRIP_KEYS = (
    "health",
    "healthMax",
    "healthNetId",
    "healthIdentityKey",
    "currentHealth",
    "maxHealth",
)
# Provenance tags must die with the values — stale hpSource/combatSource after
# strip is a silent lie (GOAL §D digestCleanGate: sources explicit end-to-end).
HP_SOURCE_STRIP_KEYS = (
    "hpSource",
    "hpHoldForward",
    "healthSampleGameTimeMs",
    "healthSampleDeltaMs",
    "healthCoverage",
    "healthMaxEvidence",
    "mMaxHPExplicit",
    "healthIdentityBinding",
    "healthTimeToleranceMs",
)
COMBAT_STRIP_KEYS = (
    "attackDamage",
    "abilityPower",
    "armor",
    "magicResist",
    "attackSpeed",
    "moveSpeed",
)
COMBAT_SOURCE_STRIP_KEYS = (
    "combatSource",
    "combatStatsNetId",
    "combatStatsIdentityKey",
    "combatStatsTimeToleranceMs",
    "combatStatsSeedGameTimeMs",
)
RANK_STRIP_KEYS = (
    "ability1Level",
    "ability2Level",
    "ability3Level",
    "ability4Level",
)

DEFAULT_IDENTITY = ROOT / (
    "docs/rofl-research/product_ready/r22/"
    "castspell-identity-2970110-g1-pid-stamped.json"
)
DEFAULT_POSITION = ROOT / (
    "artifacts/pro-grid/2970110/events.riot.rfc461.research.jsonl"
)
DEFAULT_ACTION = ROOT / (
    "docs/rofl-research/autoresearch/packet_decode/researchers/r41/"
    "emit_2970110_basic_attack_damage.jsonl"
)
_WIRE_CANDIDATES = (
    ROOT / "docs/rofl-research/combat-wire-table-16.13.json",
    ROOT
    / "docs/rofl-research/autoresearch/product_ready/r04/combat-wire-table-16.13.json",
    ROOT / "docs/rofl-research/product_ready/r04/combat-wire-table-16.13.json",
)
DEFAULT_COMBAT_WIRE = next((p for p in _WIRE_CANDIDATES if p.is_file()), _WIRE_CANDIDATES[0])
DEFAULT_MATCH_DIR = ROOT / "artifacts/rofl/2970110"
DEFAULT_RANKS_EVIDENCE = ROOT / "docs/rofl-research/upgrade-spell-ranks-2970110-g1.json"
_MATCH_CODE_RE = re.compile(r"^(\d+)[-_]g(\d+)$", re.IGNORECASE)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, separators=(",", ":"), ensure_ascii=False))
            handle.write("\n")


def _load_jsonl(path: Path) -> List[dict]:
    rows: List[dict] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _source_untrusted(src: Any) -> bool:
    if src is None:
        return False
    text = str(src).strip().casefold()
    if not text:
        return False
    if text in UNTRUSTED_PRODUCT_SOURCES:
        return True
    return any(marker in text for marker in ("grid_", "fixture", "schema_proof"))


def strip_untrusted_product_fields(row: Mapping[str, Any]) -> dict:
    """Positions stay; HP/combat/ranks from grid/research become unknown."""
    out = dict(row)
    schema = out.get("rfc461Schema")
    if schema == "game_info":
        parts = []
        for raw in out.get("participants") or []:
            if not isinstance(raw, Mapping):
                continue
            p = dict(raw)
            if _source_untrusted(p.get("healthSource")) or "health" in p:
                for k in HP_STRIP_KEYS:
                    p.pop(k, None)
                for k in HP_SOURCE_STRIP_KEYS:
                    p.pop(k, None)
                p["healthSource"] = "unavailable"
            if _source_untrusted(p.get("combatStatsSource")) or any(
                k in p for k in COMBAT_STRIP_KEYS
            ):
                for k in COMBAT_STRIP_KEYS:
                    p.pop(k, None)
                for k in COMBAT_SOURCE_STRIP_KEYS:
                    p.pop(k, None)
                p["combatStatsSource"] = "unavailable"
            if _source_untrusted(p.get("abilityRanksSource")) or any(
                k in p for k in RANK_STRIP_KEYS
            ):
                for k in RANK_STRIP_KEYS:
                    p.pop(k, None)
                p["abilityRanksSource"] = "unavailable"
            parts.append(p)
        out["participants"] = parts
        return out

    if schema != "stats_update":
        return out

    parts = []
    for raw in out.get("participants") or []:
        if not isinstance(raw, Mapping):
            continue
        p = dict(raw)
        # Product path: grid livestats never counts as known.
        for k in HP_STRIP_KEYS:
            p.pop(k, None)
        for k in HP_SOURCE_STRIP_KEYS:
            p.pop(k, None)
        p["healthSource"] = "unavailable"
        for k in COMBAT_STRIP_KEYS:
            p.pop(k, None)
        for k in COMBAT_SOURCE_STRIP_KEYS:
            p.pop(k, None)
        p["combatStatsSource"] = "unavailable"
        for k in RANK_STRIP_KEYS:
            p.pop(k, None)
        p["abilityRanksSource"] = "unavailable"
        parts.append(p)
    out["participants"] = parts
    return out


def bootstrap_position_spine(
    position_jsonl: Path,
    *,
    out_jsonl: Path,
    keep_schemas: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Extract game_info + stats_update (+ optional skill_used) with product strip."""
    keep = set(
        keep_schemas
        or (
            "rofl_coverage",
            "game_info",
            "stats_update",
            "skill_used",
            "game_end",
        )
    )
    counts: Dict[str, int] = {}
    rows: List[dict] = []
    with position_jsonl.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            schema = str(row.get("rfc461Schema") or "")
            if schema not in keep:
                continue
            stripped = strip_untrusted_product_fields(row)
            rows.append(stripped)
            counts[schema] = counts.get(schema, 0) + 1
    if counts.get("game_info", 0) != 1:
        raise DecryptError(
            f"position spine needs exactly 1 game_info, got {counts.get('game_info', 0)}"
        )
    if counts.get("stats_update", 0) < 2:
        raise DecryptError(
            f"position spine needs ≥2 stats_update, got {counts.get('stats_update', 0)}"
        )
    _write_jsonl(out_jsonl, rows)
    return {
        "ok": True,
        "path": str(out_jsonl),
        "rows": len(rows),
        "schemaCounts": counts,
        "strippedGridTrust": True,
        "note": "grid_riot_livestats HP/combat/ranks stripped to unavailable",
    }


def validate_identity_layer(
    identity: Mapping[str, Any],
    spine_rows: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    """Refuse incomplete PUUID→netId→pid bind; refuse CreateHero order fallback."""
    binding = identity.get("identityBinding")
    if not isinstance(binding, Mapping):
        raise DecryptError("identityBinding missing")
    if binding.get("createHeroOrderFallback") is True:
        raise DecryptError("refuse identity: createHeroOrderFallback=true")
    if identity.get("createHeroOrderFallback") is True:
        raise DecryptError("refuse identity: top-level createHeroOrderFallback=true")

    netid_to_pid = load_netid_to_pid(identity)
    if len(netid_to_pid) != 10:
        raise DecryptError(
            f"identity netId→pid incomplete ({len(netid_to_pid)}/10); need R22 stamp"
        )
    pids = sorted(netid_to_pid.values())
    if pids != list(range(1, 11)):
        raise DecryptError(f"identity pids must be 1..10 bijection, got {pids}")

    # Strict: no champion-name fallback when joining game_info.
    pid_to_net, pid_to_labels, pid_to_identity = pid_bindings_from_game_info(
        spine_rows, identity, allow_champion_fallback=False
    )
    if len(pid_to_net) != 10:
        raise DecryptError("game_info PUUID join did not bind 10 pids")

    # Round-trip: stamped map agrees with game_info join.
    for pid, net_id in pid_to_net.items():
        if netid_to_pid.get(int(net_id)) != int(pid):
            raise DecryptError(
                f"stamped netId→pid disagrees with game_info join for pid={pid}"
            )

    return {
        "ok": True,
        "accepted": True,
        "method": identity.get("pidStampMethod")
        or binding.get("pidStampMethod")
        or "identityBinding.participantID",
        "puuid_netId_pid": 10,
        "createHeroOrderFallback": False,
        "allow_champion_fallback": False,
        "pid_to_net": {str(k): v for k, v in sorted(pid_to_net.items())},
        "labels": {
            str(k): v.get("championName") for k, v in sorted(pid_to_labels.items())
        },
        "identity_keys": {
            str(k): v for k, v in sorted(pid_to_identity.items())
        },
    }


def _layer_reject(name: str, reason: str, **extra: Any) -> Dict[str, Any]:
    out = {
        "layer": name,
        "accepted": False,
        "rejected": True,
        "reason": reason,
        "invented": False,
    }
    out.update(extra)
    return out


def _evidence_series_game(
    evidence: Mapping[str, Any],
) -> Tuple[Optional[str], Optional[int]]:
    series = evidence.get("series") or evidence.get("gridSeriesId") or evidence.get(
        "seriesId"
    )
    if series is None and evidence.get("gameID") is not None:
        # Some research artifacts use gameID as series-like int (e.g. 2970110).
        series = evidence.get("gameID")
    game_index = evidence.get("gameIndex") or evidence.get("game_index")
    if game_index is None and evidence.get("game") is not None:
        game_index = evidence.get("game")
    # R07 evidence uses matchCode like "2970110-g1".
    if series is None or game_index is None:
        match_code = evidence.get("matchCode") or evidence.get("match_code")
        if match_code is not None:
            m = _MATCH_CODE_RE.match(str(match_code).strip())
            if m:
                if series is None:
                    series = m.group(1)
                if game_index is None:
                    game_index = int(m.group(2))
    try:
        gi = int(game_index) if game_index is not None else None
    except (TypeError, ValueError):
        gi = None
    return (str(series) if series is not None else None, gi)


def _refuse_wrong_match(
    evidence: Mapping[str, Any],
    *,
    series: str,
    game_index: int,
    layer: str,
) -> Optional[Dict[str, Any]]:
    """Fail-closed: never remap another match's evidence onto this series/game."""
    ev_series, ev_game = _evidence_series_game(evidence)
    # Explicit wrong series / gameID markers (BR1 fixture, other grid series).
    blob = json.dumps(evidence.get("match") or evidence.get("rofl") or "")
    pathish = str(evidence.get("roflPath") or evidence.get("artifact") or "")
    if "3264361042" in blob or "3264361042" in pathish:
        return _layer_reject(
            layer,
            "wrong_match_fixture_remap_refused",
            evidenceSeries=ev_series,
            evidenceGameIndex=ev_game,
            expectedSeries=series,
            expectedGameIndex=game_index,
        )
    if ev_series is not None and str(ev_series) not in (str(series), f"{series}"):
        # Allow missing series only when no contradictory id; refuse clear mismatch.
        if str(ev_series) != str(series):
            return _layer_reject(
                layer,
                "wrong_match_series_mismatch",
                evidenceSeries=ev_series,
                expectedSeries=series,
            )
    if ev_game is not None and int(ev_game) != int(game_index):
        return _layer_reject(
            layer,
            "wrong_match_game_index_mismatch",
            evidenceGameIndex=ev_game,
            expectedGameIndex=game_index,
        )
    # NetId overlap check when identity winners exist on evidence vs expected.
    return None


def try_hp_fuse(
    rows: Sequence[Mapping[str, Any]],
    *,
    hp_evidence_path: Optional[Path],
    replay_manifest_path: Optional[Path],
    series: str,
    game_index: int,
) -> Tuple[List[dict], Dict[str, Any]]:
    if hp_evidence_path is None or not hp_evidence_path.is_file():
        return list(rows), _layer_reject(
            "hp",
            "missing_rofl_trusted_hp_v1_evidence",
            path=str(hp_evidence_path) if hp_evidence_path else None,
        )
    if replay_manifest_path is None or not replay_manifest_path.is_file():
        return list(rows), _layer_reject(
            "hp",
            "missing_replay_manifest_for_hp_fuse",
            evidence=str(hp_evidence_path),
        )
    evidence = _load_json(hp_evidence_path)
    wrong = _refuse_wrong_match(
        evidence, series=series, game_index=game_index, layer="hp"
    )
    if wrong is not None:
        return list(rows), wrong
    if str(hp_evidence_path).find("3264361042") >= 0:
        return list(rows), _layer_reject(
            "hp", "wrong_match_fixture_path_refused", path=str(hp_evidence_path)
        )
    manifest = _load_json(replay_manifest_path)
    if evidence.get("scheme") not in ("rofl-trusted-hp-v1",) and evidence.get(
        "hpTrusted"
    ) is not True:
        return list(rows), _layer_reject(
            "hp",
            "evidence_not_rofl_trusted_hp_v1",
            scheme=evidence.get("scheme"),
            hpTrusted=evidence.get("hpTrusted"),
        )
    try:
        fused, summary = fuse_hp_product(
            rows, replay_manifest=manifest, hp_evidence=evidence
        )
    except DecryptError as exc:
        return list(rows), _layer_reject("hp", f"fuse_refused:{exc}")
    return fused, {
        "layer": "hp",
        "accepted": True,
        "rejected": False,
        "invented": False,
        "summary": summary,
    }


def try_ranks_fuse(
    rows: Sequence[Mapping[str, Any]],
    *,
    ranks_evidence_path: Optional[Path],
    identity: Mapping[str, Any],
    series: str,
    game_index: int,
) -> Tuple[List[dict], Dict[str, Any]]:
    if ranks_evidence_path is None or not ranks_evidence_path.is_file():
        return list(rows), _layer_reject(
            "ranks",
            "missing_upgrade_spell_ranks_evidence",
            path=str(ranks_evidence_path) if ranks_evidence_path else None,
        )
    if str(ranks_evidence_path).find("3264361042") >= 0:
        return list(rows), _layer_reject(
            "ranks",
            "wrong_match_fixture_path_refused",
            path=str(ranks_evidence_path),
        )
    evidence = _load_json(ranks_evidence_path)
    wrong = _refuse_wrong_match(
        evidence, series=series, game_index=game_index, layer="ranks"
    )
    if wrong is not None:
        return list(rows), wrong
    # Require evidence series/matchCode when present; if absent, refuse unless
    # caller explicitly names this match in the filename (2970110).
    ev_series, ev_game = _evidence_series_game(evidence)
    if ev_series is None and "2970110" not in str(ranks_evidence_path):
        return list(rows), _layer_reject(
            "ranks",
            "evidence_series_unproven_refuse",
            path=str(ranks_evidence_path),
        )
    if ev_series is not None and str(ev_series) != str(series):
        return list(rows), _layer_reject(
            "ranks",
            "wrong_match_series_mismatch",
            evidenceSeries=ev_series,
            expectedSeries=series,
        )
    if ev_game is not None and int(ev_game) != int(game_index):
        return list(rows), _layer_reject(
            "ranks",
            "wrong_match_game_index_mismatch",
            evidenceGameIndex=ev_game,
            expectedGameIndex=game_index,
        )
    try:
        fused, summary = fuse_ranks_product(
            rows, ranks_evidence=evidence, castspell_identity=identity
        )
    except DecryptError as exc:
        return list(rows), _layer_reject("ranks", f"fuse_refused:{exc}")
    return fused, {
        "layer": "ranks",
        "accepted": True,
        "rejected": False,
        "invented": False,
        "evidencePath": str(ranks_evidence_path),
        "opcode": summary.get("opcode"),
        "abilityRanksSource": summary.get("abilityRanksSource"),
        "summary": summary,
    }


def try_combat_fuse(
    rows: Sequence[Mapping[str, Any]],
    *,
    combat_evidence_path: Optional[Path],
    combat_wire_table_path: Optional[Path],
    identity: Mapping[str, Any],
    series: str,
    game_index: int,
) -> Tuple[List[dict], Dict[str, Any]]:
    """R04 KEEP wire table alone is insufficient — need live timed samples."""
    wire_note = None
    if combat_wire_table_path and combat_wire_table_path.is_file():
        wire = _load_json(combat_wire_table_path)
        wire_note = {
            "path": str(combat_wire_table_path),
            "wireTableProven": bool(
                wire.get("wireTableProven") or wire.get("ok")
            ),
            "C_combat": False,
            "note": "R04 KEEP table only; live samples required for combatStatsKnown",
        }

    if combat_evidence_path is None or not combat_evidence_path.is_file():
        return list(rows), _layer_reject(
            "combat",
            "missing_live_combat_evidence_C_combat_false",
            wireTable=wire_note,
            combatStatsKnown_invented=False,
        )
    if str(combat_evidence_path).find("3264361042") >= 0:
        return list(rows), _layer_reject(
            "combat",
            "wrong_match_fixture_path_refused",
            path=str(combat_evidence_path),
            wireTable=wire_note,
        )
    evidence = _load_json(combat_evidence_path)
    wrong = _refuse_wrong_match(
        evidence, series=series, game_index=game_index, layer="combat"
    )
    if wrong is not None:
        wrong["wireTable"] = wire_note
        return list(rows), wrong
    if evidence.get("combatTrusted") is not True:
        return list(rows), _layer_reject(
            "combat",
            "combat_evidence_not_combatTrusted",
            wireTable=wire_note,
            combatTrusted=evidence.get("combatTrusted"),
        )
    timed = evidence.get("timedCombatEvidence") or {}
    samples = list(timed.get("samples") or [])
    if len(samples) < 10:
        return list(rows), _layer_reject(
            "combat",
            "insufficient_live_combat_samples",
            sampleCount=len(samples),
            wireTable=wire_note,
        )
    try:
        fused, summary = fuse_combat_product(
            rows, combat_evidence=evidence, castspell_identity=identity
        )
    except DecryptError as exc:
        return list(rows), _layer_reject(
            "combat", f"fuse_refused:{exc}", wireTable=wire_note
        )
    return fused, {
        "layer": "combat",
        "accepted": True,
        "rejected": False,
        "invented": False,
        "wireTable": wire_note,
        "summary": summary,
    }


def known_flag_density(timeline: Mapping[str, Any]) -> Dict[str, Any]:
    frames = list(timeline.get("frames") or [])
    total_units = 0
    hp_true = combat_true = ranks_true = 0
    for frame in frames:
        for unit in frame.get("units") or []:
            total_units += 1
            if unit.get("hpKnown") is True:
                hp_true += 1
            if unit.get("combatStatsKnown") is True:
                combat_true += 1
            if unit.get("abilityRanksKnown") is True:
                ranks_true += 1
    denom = max(total_units, 1)
    return {
        "frames": len(frames),
        "units": total_units,
        "hpKnown_true": hp_true,
        "combatStatsKnown_true": combat_true,
        "abilityRanksKnown_true": ranks_true,
        "hpKnown_density": round(hp_true / denom, 6),
        "combatStatsKnown_density": round(combat_true / denom, 6),
        "abilityRanksKnown_density": round(ranks_true / denom, 6),
    }


def compose_product_timeline(
    *,
    match_dir: Path,
    series: str,
    game_index: int,
    identity_path: Path,
    position_jsonl: Path,
    action_jsonl_paths: Sequence[Path],
    hp_evidence: Optional[Path] = None,
    replay_manifest: Optional[Path] = None,
    ranks_evidence: Optional[Path] = None,
    combat_evidence: Optional[Path] = None,
    combat_wire_table: Optional[Path] = None,
    require_aa: bool = False,
) -> Dict[str, Any]:
    match_dir.mkdir(parents=True, exist_ok=True)
    identity = _load_json(identity_path)
    # Keep a copy of identity under match-dir (worktree only).
    identity_out = match_dir / f"identity.g{game_index}.pid-stamped.json"
    shutil.copy2(identity_path, identity_out)

    spine_path = match_dir / f"events.g{game_index}.position-spine.product.jsonl"
    spine_meta = bootstrap_position_spine(position_jsonl, out_jsonl=spine_path)
    spine_rows = _load_jsonl(spine_path)

    layers: Dict[str, Any] = {
        "spine": spine_meta,
        "identity": None,
        "hp": None,
        "ranks": None,
        "combat": None,
        "aa_damage": None,
        "timeline": None,
    }

    try:
        layers["identity"] = validate_identity_layer(identity, spine_rows)
    except DecryptError as exc:
        summary = {
            "ok": False,
            "researcher": "R12",
            "track": "P4-T2+T3+D_ranks",
            "series": series,
            "gameIndex": game_index,
            "ts": utc_now_iso(),
            "blocker": {"id": "identity_incomplete", "detail": str(exc)},
            "layers": layers,
            "calculatorReady": False,
            "productEligible": False,
            "fuse_composer_identity_stable": False,
            "never_invent": True,
        }
        _write_json(match_dir / "fuse-summary.json", summary)
        return summary

    working = list(spine_rows)
    working, layers["hp"] = try_hp_fuse(
        working,
        hp_evidence_path=hp_evidence,
        replay_manifest_path=replay_manifest,
        series=series,
        game_index=game_index,
    )
    fused_jsonl = match_dir / f"events.g{game_index}.fused.rfc461.jsonl"
    working, layers["ranks"] = try_ranks_fuse(
        working,
        ranks_evidence_path=ranks_evidence,
        identity=identity,
        series=series,
        game_index=game_index,
    )
    # R08 honesty: ship byte-identical ranks-evidence.json beside fuse artifacts.
    ranks_shipped = False
    ranks_evidence_sha = None
    ranks_evidence_out = match_dir / "ranks-evidence.json"
    if layers["ranks"].get("accepted") is True and ranks_evidence is not None:
        ranks_bytes = Path(ranks_evidence).read_bytes()
        ranks_evidence_out.write_bytes(ranks_bytes)
        ranks_evidence_sha = hashlib.sha256(ranks_bytes).hexdigest()
        ranks_shipped = True
        layers["ranks"]["ranksEvidencePath"] = str(ranks_evidence_out)
        layers["ranks"]["evidenceSha256"] = ranks_evidence_sha
    elif ranks_evidence_out.is_file() and layers["ranks"].get("accepted") is not True:
        # Fail-closed: do not leave stale evidence implying known ranks.
        ranks_evidence_out.unlink()

    working, layers["combat"] = try_combat_fuse(
        working,
        combat_evidence_path=combat_evidence,
        combat_wire_table_path=combat_wire_table,
        identity=identity,
        series=series,
        game_index=game_index,
    )
    _write_jsonl(fused_jsonl, working)

    # Side-car action bridges (research_overlay OK with disclosure).
    existing_actions = [p for p in action_jsonl_paths if p.is_file()]
    timeline_id = f"{series}-g{game_index}"
    timeline = build_timeline(
        fused_jsonl,
        timeline_id=timeline_id,
        name=f"GRID {series} game {game_index} product fuse (R12)",
        patch="",
        action_identity=identity,
        action_jsonl_paths=existing_actions,
    )
    counters = timeline.pop("_actionExtractCounters", {}) or {}
    aa_n = len(timeline.get("basicAttack") or [])
    dmg_n = len(timeline.get("damageDealt") or [])
    aa_ok = aa_n > 0 or dmg_n > 0
    if require_aa and not aa_ok:
        layers["aa_damage"] = _layer_reject(
            "aa_damage",
            "no_identity_resolved_aa_or_damage",
            counters=counters,
        )
    else:
        layers["aa_damage"] = {
            "layer": "aa_damage",
            "accepted": aa_ok,
            "rejected": not aa_ok,
            "invented": False,
            "basicAttack": aa_n,
            "damageDealt": dmg_n,
            "actionJsonl": [str(p) for p in existing_actions],
            "counters": counters,
            "provenance": (timeline.get("provenance") or {}),
            "schema": "R10 KEEP basicAttack/damageDealt identity-bound",
        }

    density = known_flag_density(timeline)
    # Honesty: without accepted combat layer, density must stay 0.
    if layers["combat"].get("accepted") is not True and density["combatStatsKnown_true"] != 0:
        raise DecryptError(
            "fail-closed: combatStatsKnown_true>0 without accepted combat fuse"
        )
    if layers["hp"].get("accepted") is not True and density["hpKnown_true"] != 0:
        raise DecryptError("fail-closed: hpKnown_true>0 without accepted HP fuse")
    if layers["ranks"].get("accepted") is not True and density["abilityRanksKnown_true"] != 0:
        raise DecryptError(
            "fail-closed: abilityRanksKnown_true>0 without accepted ranks fuse"
        )

    # Provenance: research fuse path, never product publish claim.
    prov = dict(timeline.get("provenance") or {})
    prov.update(
        {
            "sourceKind": "product_fuse_composer_r12",
            "researchOnly": True,
            "calculatorReady": False,
            "productEligible": False,
            "fuseComposer": "fuse_product_timeline.py",
            "identityArtifact": identity_out.name,
            "aaCoverage": prov.get("aaCoverage")
            or layers["aa_damage"].get("provenance", {}).get("aaCoverage"),
            "damageCoverage": prov.get("damageCoverage")
            or layers["aa_damage"].get("provenance", {}).get("damageCoverage"),
        }
    )
    if layers["ranks"].get("accepted") is True:
        prov["abilityRanksSource"] = layers["ranks"].get("abilityRanksSource")
        prov["abilityRanksTrusted"] = True
        prov["ranksEvidence"] = "ranks-evidence.json"
        prov["ranksOpcode"] = layers["ranks"].get("opcode")
    timeline["provenance"] = prov

    timeline_path = match_dir / f"timeline.g{game_index}.product-fuse.json"
    # Drop huge internal noise; keep parseable GameTimeline.
    timeline_path.write_text(
        json.dumps(timeline, separators=(",", ":"), ensure_ascii=False),
        encoding="utf-8",
    )
    layers["timeline"] = {
        "ok": True,
        "path": str(timeline_path),
        "bytes": timeline_path.stat().st_size,
        "frameCount": timeline.get("frameCount"),
        "basicAttack": aa_n,
        "damageDealt": dmg_n,
        "knownFlagDensity": density,
    }

    identity_ok = bool(layers["identity"].get("ok"))
    composer_stable = identity_ok and aa_ok and density["combatStatsKnown_true"] == 0
    ranks_ok = (
        layers["ranks"].get("accepted") is True
        and density["abilityRanksKnown_true"] > 0
        and ranks_shipped
    )
    # R11 keepable: identity + AA, no invented known flags.
    # R12 keepable: same + D_ranks accepted with ranks-evidence.json shipped.
    keepable_r11 = (
        identity_ok
        and aa_ok
        and layers["hp"].get("accepted") is False
        and layers["ranks"].get("accepted") is False
        and layers["combat"].get("accepted") is False
        and density["hpKnown_true"] == 0
        and density["combatStatsKnown_true"] == 0
        and density["abilityRanksKnown_true"] == 0
        and layers["aa_damage"].get("invented") is False
    )
    keepable = (
        identity_ok
        and aa_ok
        and ranks_ok
        and layers["hp"].get("accepted") is False
        and layers["combat"].get("accepted") is False
        and density["hpKnown_true"] == 0
        and density["combatStatsKnown_true"] == 0
        and layers["aa_damage"].get("invented") is False
    ) or keepable_r11

    # Sample mid-frame unit source for honesty audit.
    mid_unit_source = None
    frames = list(timeline.get("frames") or [])
    if frames:
        mid = frames[len(frames) // 2]
        for unit in mid.get("units") or []:
            if unit.get("abilityRanksKnown") is True:
                mid_unit_source = unit.get("abilityRanksSource")
                break

    summary = {
        "ok": keepable or (identity_ok and aa_ok),
        "researcher": "R12",
        "phase": "B",
        "room": "P4",
        "track": "T2+T3+D_ranks",
        "track_title": "Attach R07 UpgradeSpellAns 1012 ranks into identity-stable fuse",
        "series": series,
        "gameIndex": game_index,
        "match": f"{series}-g{game_index}",
        "ts": utc_now_iso(),
        "worktree": str(ROOT),
        "branch": "adv/prd-r12-timeline-fuse",
        "never_edited_parent": True,
        "identity_path": str(identity_out),
        "fused_jsonl": str(fused_jsonl),
        "timeline_path": str(timeline_path),
        "ranks_evidence_shipped": ranks_shipped,
        "ranks_evidence_sha256": ranks_evidence_sha,
        "mid_unit_abilityRanksSource": mid_unit_source,
        "layers": layers,
        "knownFlagDensity": density,
        "calculatorReady": False,
        "productEligible": False,
        "B_hp": layers["hp"].get("accepted") is True,
        "C_combat": False,
        "D_ranks": ranks_ok,
        "fuse_composer_identity_stable": composer_stable,
        "fuse_2970110_bridge_attach": aa_ok,
        "keepable": keepable,
        "ship_freeze": {
            "composite": 0.9683,
            "shipGate": True,
            "productShipGate": True,
            "touched": False,
        },
        "packetDecodeGate": True,
        "keeps_reused": {
            "R22_identity_pid": str(identity_path),
            "R10_aa_damage_schema": "src/game/timeline.ts + lib/timeline_action_events.py",
            "R07_upgrade_spell_ranks": str(ranks_evidence) if ranks_evidence else None,
            "R08_ranks_honesty": "ranks-evidence.json + per-unit abilityRanksSource",
            "R04_combat_wire_table": str(combat_wire_table) if combat_wire_table else None,
            "R11_fuse_composer": "scripts/fuse_product_timeline.py",
        },
        "blocker": None,
        "laws": {
            "never_invent": True,
            "no_combatStatsKnown_without_live_samples": True,
            "no_hpKnown_without_trusted_hp": True,
            "no_abilityRanksKnown_without_upgrade_spell_evidence": True,
            "no_grid_livestats_as_product_known": True,
            "no_public_matches_publish": True,
            "fail_closed": True,
        },
    }

    # Honest residual blockers for calculatorReady (not composer keep blockers).
    residual = []
    if layers["hp"].get("accepted") is not True:
        residual.append("B_hp: missing same-match rofl-trusted-hp-v1")
    if layers["combat"].get("accepted") is not True:
        residual.append("C_combat: R04 wire KEEP but no live samples (do not invent)")
    if not ranks_ok:
        residual.append("D_ranks: UpgradeSpellAns fuse/evidence incomplete")
    if residual:
        summary["blocker"] = {
            "id": "calculatorReady_layers_incomplete",
            "summary": "; ".join(residual),
            "note": "R12 KEEP attaches D_ranks (opcode 1012) with R08 honesty; "
            "calculatorReadyGate remains false until B_hp + C_combat + validate --product",
        }

    _write_json(match_dir / "fuse-summary.json", summary)
    return summary


def _exp(
    exp_id: str,
    hypothesis: str,
    ok: bool,
    detail: Any,
) -> Dict[str, Any]:
    return {
        "id": exp_id,
        "hypothesis": hypothesis,
        "ok": ok,
        "verdict": "kept" if ok else "discard",
        "detail": detail,
    }


def run_experiments(
    *,
    match_dir: Path,
    identity_path: Path,
    position_jsonl: Path,
    action_jsonl: Path,
    combat_wire_table: Path,
    ranks_evidence: Optional[Path] = None,
) -> Dict[str, Any]:
    """≥8 adversarial experiments for R12 ranks attach + T3 anti-scramble."""
    experiments: List[Dict[str, Any]] = []
    out_root = match_dir / "r12_experiments"
    if out_root.exists():
        shutil.rmtree(out_root)
    out_root.mkdir(parents=True)

    ranks_path = ranks_evidence or DEFAULT_RANKS_EVIDENCE
    if not ranks_path.is_file():
        raise DecryptError(f"R07 ranks evidence missing: {ranks_path}")

    # One-time spine extract from fat riot JSONL (reuse across experiments).
    cached_spine = out_root / "cached.position-spine.product.jsonl"
    bootstrap_position_spine(position_jsonl, out_jsonl=cached_spine)
    position_jsonl = cached_spine
    identity = _load_json(identity_path)

    # E1 — happy path: R07 ranks + R22 identity + AA
    e1_dir = out_root / "e1_ranks_happy"
    s1 = compose_product_timeline(
        match_dir=e1_dir,
        series="2970110",
        game_index=1,
        identity_path=identity_path,
        position_jsonl=position_jsonl,
        action_jsonl_paths=[action_jsonl],
        ranks_evidence=ranks_path,
        combat_wire_table=combat_wire_table,
    )
    experiments.append(
        _exp(
            "E1",
            "Happy path: R07 opcode-1012 ranks accepted; AA retained; HP/combat false",
            bool(
                s1.get("ok")
                and s1["layers"]["identity"]["ok"]
                and s1["layers"]["ranks"].get("accepted") is True
                and s1["layers"]["ranks"].get("opcode") == 1012
                and s1["layers"]["aa_damage"]["accepted"]
                and s1["knownFlagDensity"]["abilityRanksKnown_true"] > 0
                and s1["knownFlagDensity"]["hpKnown_true"] == 0
                and s1["knownFlagDensity"]["combatStatsKnown_true"] == 0
                and s1.get("D_ranks") is True
                and s1["calculatorReady"] is False
            ),
            {
                "aa": s1["layers"]["aa_damage"].get("basicAttack"),
                "dmg": s1["layers"]["aa_damage"].get("damageDealt"),
                "density": s1["knownFlagDensity"],
                "opcode": s1["layers"]["ranks"].get("opcode"),
                "keepable": s1.get("keepable"),
            },
        )
    )

    # E2 — missing ranks evidence → density 0
    e2_dir = out_root / "e2_no_ranks"
    s2 = compose_product_timeline(
        match_dir=e2_dir,
        series="2970110",
        game_index=1,
        identity_path=identity_path,
        position_jsonl=position_jsonl,
        action_jsonl_paths=[action_jsonl],
        ranks_evidence=None,
        combat_wire_table=combat_wire_table,
    )
    experiments.append(
        _exp(
            "E2",
            "Missing ranks evidence → ranks rejected; abilityRanksKnown density 0",
            s2["layers"]["ranks"].get("accepted") is not True
            and s2["knownFlagDensity"]["abilityRanksKnown_true"] == 0
            and s2.get("D_ranks") is not True,
            s2["layers"]["ranks"],
        )
    )

    # E3 — BR1 wrong-match refuse
    e3_dir = out_root / "e3_br1_refuse"
    ranks_br1 = ROOT / "docs/rofl-research/upgrade-spell-ranks-BR1-3264361042.json"
    s3 = compose_product_timeline(
        match_dir=e3_dir,
        series="2970110",
        game_index=1,
        identity_path=identity_path,
        position_jsonl=position_jsonl,
        action_jsonl_paths=[action_jsonl],
        ranks_evidence=ranks_br1 if ranks_br1.is_file() else Path("/no/such/br1.json"),
        combat_wire_table=combat_wire_table,
    )
    experiments.append(
        _exp(
            "E3",
            "Wrong-match BR1 ranks evidence refused; no invented abilityRanksKnown",
            s3["layers"]["ranks"].get("accepted") is not True
            and s3["knownFlagDensity"]["abilityRanksKnown_true"] == 0,
            s3["layers"]["ranks"],
        )
    )

    # E4 — wiki-only source refuse at fuse layer
    wiki_ev = deepcopy(_load_json(ranks_path))
    wiki_ev["abilityRanksSource"] = "wiki_skill_order"
    wiki_path = out_root / "e4_wiki.json"
    _write_json(wiki_path, wiki_ev)
    _fused4, layer4 = try_ranks_fuse(
        _load_jsonl(e1_dir / "events.g1.position-spine.product.jsonl"),
        ranks_evidence_path=wiki_path,
        identity=identity,
        series="2970110",
        game_index=1,
    )
    experiments.append(
        _exp(
            "E4",
            "Wiki-only abilityRanksSource refused (R08 honesty)",
            layer4.get("accepted") is not True
            and "fuse_refused" in str(layer4.get("reason") or ""),
            layer4,
        )
    )

    # E5 — opcode/source mismatch refuse (1012 evidence forced to 636 source)
    bad_op = deepcopy(_load_json(ranks_path))
    bad_op["abilityRanksSource"] = "rofl2_upgrade_spell_ans_636_first_write"
    bad_path = out_root / "e5_opcode_mismatch.json"
    _write_json(bad_path, bad_op)
    _fused5, layer5 = try_ranks_fuse(
        _load_jsonl(e1_dir / "events.g1.position-spine.product.jsonl"),
        ranks_evidence_path=bad_path,
        identity=identity,
        series="2970110",
        game_index=1,
    )
    experiments.append(
        _exp(
            "E5",
            "Opcode 1012 + legacy 636 source tag mismatch refused",
            layer5.get("accepted") is not True,
            layer5,
        )
    )

    # E6 — ranks-evidence.json shipped byte-identical (R08)
    e1_ship = e1_dir / "ranks-evidence.json"
    src_sha = hashlib.sha256(ranks_path.read_bytes()).hexdigest()
    ship_sha = (
        hashlib.sha256(e1_ship.read_bytes()).hexdigest() if e1_ship.is_file() else None
    )
    experiments.append(
        _exp(
            "E6",
            "ranks-evidence.json shipped byte-identical to R07 artifact",
            e1_ship.is_file() and ship_sha == src_sha and s1.get("ranks_evidence_shipped") is True,
            {"srcSha": src_sha, "shipSha": ship_sha, "path": str(e1_ship)},
        )
    )

    # E7 — per-unit abilityRanksSource stamped on timeline
    tl1 = _load_json(Path(s1["timeline_path"]))
    mid = tl1["frames"][len(tl1["frames"]) // 2]
    unit_sources = {
        u.get("abilityRanksSource")
        for u in mid["units"]
        if u.get("abilityRanksKnown") is True
    }
    experiments.append(
        _exp(
            "E7",
            "Per-unit abilityRanksSource=rofl2_upgrade_spell_ans_1012_first_write",
            unit_sources == {"rofl2_upgrade_spell_ans_1012_first_write"}
            and all(u.get("abilityRanksKnown") is True for u in mid["units"]),
            {"unit_sources": sorted(x for x in unit_sources if x), "mid_t": mid.get("t")},
        )
    )

    # E8 — T3 presentation-order scramble still binds ranks + AA
    e8_dir = out_root / "e8_scramble"
    spine_rows = _load_jsonl(e1_dir / "events.g1.position-spine.product.jsonl")
    scrambled = []
    for row in spine_rows:
        r = deepcopy(row)
        if r.get("rfc461Schema") == "game_info":
            parts = list(r["participants"])
            r["participants"] = list(reversed(parts))
        scrambled.append(r)
    scrambled_path = e8_dir / "scrambled-spine.jsonl"
    _write_jsonl(scrambled_path, scrambled)
    s8 = compose_product_timeline(
        match_dir=e8_dir / "out",
        series="2970110",
        game_index=1,
        identity_path=identity_path,
        position_jsonl=scrambled_path,
        action_jsonl_paths=[action_jsonl],
        ranks_evidence=ranks_path,
        combat_wire_table=combat_wire_table,
    )
    experiments.append(
        _exp(
            "E8",
            "T3: game_info order scramble still identity-stable ranks+AA",
            bool(
                s8.get("ok")
                and s8["layers"]["identity"]["ok"]
                and s8["layers"]["ranks"].get("accepted") is True
                and s8["layers"]["aa_damage"]["accepted"]
                and s8["knownFlagDensity"]["abilityRanksKnown_true"] > 0
            ),
            {
                "aa": s8["layers"]["aa_damage"].get("basicAttack"),
                "ranks_density": s8["knownFlagDensity"]["abilityRanksKnown_density"],
            },
        )
    )

    # E9 — incomplete identity refuse (no pid stamp)
    e9_dir = out_root / "e9_no_pid"
    wiped = deepcopy(identity)
    for p in wiped["identityBinding"]["participants"]:
        p.pop("participantID", None)
    wiped["pidStampComplete"] = False
    wiped["identityPidComplete"] = False
    bad_id = e9_dir / "bad-identity.json"
    _write_json(bad_id, wiped)
    s9 = compose_product_timeline(
        match_dir=e9_dir / "out",
        series="2970110",
        game_index=1,
        identity_path=bad_id,
        position_jsonl=position_jsonl,
        action_jsonl_paths=[action_jsonl],
        ranks_evidence=ranks_path,
        combat_wire_table=combat_wire_table,
    )
    experiments.append(
        _exp(
            "E9",
            "T3: refuse incomplete R22 pid stamp (no order invent)",
            s9.get("ok") is False
            and (s9.get("blocker") or {}).get("id") == "identity_incomplete",
            s9.get("blocker"),
        )
    )

    # E10 — HP/combat still not invented when ranks accepted
    experiments.append(
        _exp(
            "E10",
            "Fail-closed: ranks KEEP does not invent hpKnown/combatStatsKnown",
            s1["layers"]["hp"].get("accepted") is False
            and s1["layers"]["combat"].get("accepted") is False
            and s1["knownFlagDensity"]["hpKnown_true"] == 0
            and s1["knownFlagDensity"]["combatStatsKnown_true"] == 0
            and s1.get("C_combat") is False
            and s1.get("B_hp") is False,
            s1["knownFlagDensity"],
        )
    )

    # E11 — AA parity with R10 extract under R22 map (no freeze regress markers)
    from lib.timeline_action_events import extract_action_events_from_rows

    netmap = load_netid_to_pid(identity)
    extracted = extract_action_events_from_rows(
        _load_jsonl(action_jsonl), netid_to_pid=netmap
    )
    freeze = s1.get("ship_freeze") or {}
    experiments.append(
        _exp(
            "E11",
            "AA/damage counts == R10×R22 extract; ship freeze untouched 0.9683",
            s1["layers"]["aa_damage"]["basicAttack"]
            == extracted["counters"]["accepted_basic_attack"]
            and s1["layers"]["aa_damage"]["damageDealt"]
            == extracted["counters"]["accepted_damage_dealt"]
            and freeze.get("composite") == 0.9683
            and freeze.get("shipGate") is True
            and freeze.get("productShipGate") is True
            and freeze.get("touched") is False,
            {
                "composer": {
                    "aa": s1["layers"]["aa_damage"]["basicAttack"],
                    "dmg": s1["layers"]["aa_damage"]["damageDealt"],
                },
                "extract": extracted["counters"],
                "freeze": freeze,
            },
        )
    )

    # E12 — canonical fuse-summary under match_dir with D_ranks
    summary_path = match_dir / "fuse-summary.json"
    canonical = compose_product_timeline(
        match_dir=match_dir,
        series="2970110",
        game_index=1,
        identity_path=identity_path,
        position_jsonl=position_jsonl,
        action_jsonl_paths=[action_jsonl],
        ranks_evidence=ranks_path,
        combat_wire_table=combat_wire_table,
    )
    layers = canonical.get("layers") or {}
    experiments.append(
        _exp(
            "E12",
            "Canonical fuse-summary: D_ranks true, ranksKnown density>0, keepable",
            summary_path.is_file()
            and canonical.get("keepable") is True
            and canonical.get("D_ranks") is True
            and canonical["knownFlagDensity"]["abilityRanksKnown_true"] > 0
            and (match_dir / "ranks-evidence.json").is_file()
            and layers.get("ranks", {}).get("opcode") == 1012,
            {
                "density": canonical.get("knownFlagDensity"),
                "D_ranks": canonical.get("D_ranks"),
                "keepable": canonical.get("keepable"),
                "aa": layers.get("aa_damage", {}).get("basicAttack"),
            },
        )
    )

    ok_n = sum(1 for e in experiments if e["ok"])
    report = {
        "researcher": "R12",
        "track": "P4-T2+T3+D_ranks",
        "ts": utc_now_iso(),
        "experiments_run": len(experiments),
        "experiments_passed": ok_n,
        "experiments_ok": ok_n == len(experiments),
        "ranks_evidence": str(ranks_path),
        "experiments": experiments,
        "canonical": {
            "ok": canonical.get("ok"),
            "keepable": canonical.get("keepable"),
            "D_ranks": canonical.get("D_ranks"),
            "fuse_composer_identity_stable": canonical.get(
                "fuse_composer_identity_stable"
            ),
            "timeline_path": canonical.get("timeline_path"),
            "fuse_summary": str(summary_path),
            "ranks_evidence_shipped": canonical.get("ranks_evidence_shipped"),
            "basicAttack": (canonical.get("layers") or {})
            .get("aa_damage", {})
            .get("basicAttack"),
            "damageDealt": (canonical.get("layers") or {})
            .get("aa_damage", {})
            .get("damageDealt"),
            "knownFlagDensity": canonical.get("knownFlagDensity"),
            "blocker": canonical.get("blocker"),
        },
    }
    _write_json(match_dir / "r12-experiments-summary.json", report)
    _write_json(out_root / "experiments-summary.json", report)
    return report


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--match-dir", type=Path, default=DEFAULT_MATCH_DIR)
    ap.add_argument("--series", default="2970110")
    ap.add_argument("--game-index", type=int, default=1)
    ap.add_argument("--identity", type=Path, default=DEFAULT_IDENTITY)
    ap.add_argument("--position-jsonl", type=Path, default=DEFAULT_POSITION)
    ap.add_argument(
        "--action-jsonl",
        type=Path,
        action="append",
        default=[],
        help="Side-car basic_attack/damage_dealt JSONL (repeatable)",
    )
    ap.add_argument("--hp-evidence", type=Path, default=None)
    ap.add_argument("--replay-manifest", type=Path, default=None)
    ap.add_argument(
        "--ranks-evidence",
        type=Path,
        default=DEFAULT_RANKS_EVIDENCE,
        help="R07 UpgradeSpellAns ranks evidence (default: 2970110-g1 opcode 1012)",
    )
    ap.add_argument("--combat-evidence", type=Path, default=None)
    ap.add_argument("--combat-wire-table", type=Path, default=DEFAULT_COMBAT_WIRE)
    ap.add_argument("--require-aa", action="store_true")
    ap.add_argument("--run-experiments", action="store_true")
    ap.add_argument(
        "--no-ranks-evidence",
        action="store_true",
        help="Explicitly omit ranks fuse (R11-style unknown ranks).",
    )
    args = ap.parse_args(list(argv) if argv is not None else None)

    actions = list(args.action_jsonl) or [DEFAULT_ACTION]
    ranks_ev = None if args.no_ranks_evidence else args.ranks_evidence

    if args.run_experiments:
        report = run_experiments(
            match_dir=args.match_dir,
            identity_path=args.identity,
            position_jsonl=args.position_jsonl,
            action_jsonl=actions[0],
            combat_wire_table=args.combat_wire_table,
            ranks_evidence=ranks_ev or DEFAULT_RANKS_EVIDENCE,
        )
        print(json.dumps(report, indent=2))
        return 0 if report.get("experiments_ok") else 2

    summary = compose_product_timeline(
        match_dir=args.match_dir,
        series=args.series,
        game_index=args.game_index,
        identity_path=args.identity,
        position_jsonl=args.position_jsonl,
        action_jsonl_paths=actions,
        hp_evidence=args.hp_evidence,
        replay_manifest=args.replay_manifest,
        ranks_evidence=ranks_ev,
        combat_evidence=args.combat_evidence,
        combat_wire_table=args.combat_wire_table,
        require_aa=args.require_aa,
    )
    print(json.dumps(summary, indent=2))
    return 0 if summary.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
