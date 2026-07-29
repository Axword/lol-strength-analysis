#!/usr/bin/env python3
"""
Timed multi-sample type-107 Replication HP evidence toward rofl-trusted-hp-v1.

Walks ROFL2 chunk bodies, Deserializes type-107, applies post-Deserialize
vectors via ``rofl_replication_apply`` ((5,0)=mHP, (5,1)=mMaxHP explicit),
and emits ≥2 timed samples with 10 hero netIds when acceptance passes.

Identity: loads ROFL ``statsJson`` PUUID / full Riot ID. CreateHero packet
bind is attempted when events are supplied; otherwise binding stays
incomplete with ``createHeroOrderFallback`` research-only (never
``productEligible`` / ``identityBinding.complete``).

Combat primary-1 floats may be inventoried but are never trusted.

Example:
  npm run rofl:replication-timed-hp -- \\
    --rofl \"$HOME/Documents/League of Legends/Replays/BR1-3264361042.rofl\" \\
    --out docs/rofl-research/trusted-hp-candidate-BR1-3264361042.json \\
    --json-out docs/rofl-research/timed-hp-report-BR1-3264361042.json
"""
from __future__ import annotations

import argparse
import json
import struct
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fuse_replay_api_hp as fuse  # noqa: E402
import rofl2_accessor_spike as spike  # noqa: E402
import rofl_metadata  # noqa: E402
from rofl2_packet_decrypt_probe import DecryptError, heroes_from_events  # noqa: E402
from rofl2_probe import extract_segments, parse_rofl2  # noqa: E402
from rofl2_replication_decode import (  # noqa: E402
    DEFAULT_LEAGUE_BINARY,
    _drive_body_replication,
)
from rofl2_unicorn_packet_drive import (  # noqa: E402
    ARENA_BASE,
    BUF_BASE,
    BUF_SIZE,
    HEAP_BASE,
    HEAP_SIZE,
    REPLICATION_TYPE_CANDIDATE,
    SCRATCH,
    STACK_BASE,
    STACK_SIZE,
    TYPE_COUNT_GLOBAL,
    TYPE_COUNT_VALUE,
    BumpHeap,
    install_block_runtime_hooks,
    install_unmapped_stub,
    map_binary,
)
from rofl_replication_apply import (  # noqa: E402
    BANK0_UNKNOWN_A,
    BANK0_UNKNOWN_B,
    MHP_PRIMARY,
    MHP_SECONDARY,
    MMAXHP_PRIMARY,
    MMAXHP_SECONDARY,
    HeroReplicationState,
    acceptance_snapshot,
    install_use_map_stub,
    is_valid_use_replication_prologue,
)

DEFAULT_ROFL = (
    Path.home()
    / "Documents"
    / "League of Legends"
    / "Replays"
    / "BR1-3264361042.rofl"
)
PROVEN_HERO_NET_IDS: Tuple[int, ...] = tuple(range(0x400000AE, 0x400000B8))
DEFAULT_MAX_SAMPLES = 5
# CastSpellAns CreateHero-equivalent events — preferred Gate A bind source.
DEFAULT_CREATE_HERO_EVENTS = Path(
    "docs/rofl-research/create-hero-from-castspell-BR1-3264361042.json"
)
DEFAULT_TOLERANCE_MS = 100
MIN_SAMPLE_SPACING_MS = 30_000


def select_chunk_indices(n_chunks: int, max_samples: int) -> List[int]:
    """Spread sample targets across early / mid / late chunk indices."""
    if n_chunks <= 0 or max_samples <= 0:
        return []
    want = min(int(max_samples), int(n_chunks))
    if want == 1:
        return [0]
    return sorted(
        {
            int(round(i * (n_chunks - 1) / (want - 1)))
            for i in range(want)
        }
    )


def game_time_ms_from_seconds(time_s: float) -> int:
    return int(round(float(time_s) * 1000.0))


def units_from_heroes(heroes: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """Build trusted-hp unit rows; requires explicit mMaxHP on every hero."""
    units: List[Dict[str, Any]] = []
    for hero in heroes:
        net_id = int(hero["netId"])
        hp = float(hero["mHP"])
        mx = float(hero["mMaxHP"])
        explicit = bool(hero.get("explicitMax", hero.get("mMaxHPExplicit", True)))
        if not explicit:
            raise ValueError(f"hero netId={net_id} lacks explicit mMaxHP")
        if not (0 < hp <= mx and mx > 100):
            raise ValueError(f"invalid HP pair netId={net_id}: {hp}/{mx}")
        units.append(
            {
                "netId": net_id,
                "mHP": hp,
                "mMaxHP": mx,
                "mMaxHPExplicit": True,
            }
        )
    return units


def make_sample(
    *,
    game_time_ms: int,
    heroes: Sequence[Mapping[str, Any]],
    chunk_index: Optional[int] = None,
) -> Dict[str, Any]:
    if game_time_ms < 0:
        raise ValueError("gameTimeMs must be non-negative")
    units = units_from_heroes(heroes)
    if len(units) != 10:
        raise ValueError(f"sample requires exactly 10 units, got {len(units)}")
    sample: Dict[str, Any] = {
        "gameTimeMs": int(game_time_ms),
        "units": units,
    }
    if chunk_index is not None:
        sample["chunkIndex"] = int(chunk_index)
    return sample


def product_complete_blockers(evidence: Mapping[str, Any]) -> List[str]:
    """Honest gate list mirroring fuse_replay_api_hp TRUSTED_* product rules."""
    blockers: List[str] = []
    if evidence.get("schema") != fuse.TRUSTED_EVIDENCE_SCHEMA:
        blockers.append(f"schema!={fuse.TRUSTED_EVIDENCE_SCHEMA}")
    provenance = evidence.get("provenance")
    if not isinstance(provenance, Mapping):
        blockers.append("provenance_missing")
        return blockers
    if provenance.get("sourceKind") != fuse.TRUSTED_HEALTH_SOURCE:
        blockers.append("sourceKind_not_timed_identity_bound")
    if provenance.get("timed") is not True:
        blockers.append("not_timed")
    if provenance.get("staticSnapshot") is not False:
        blockers.append("static_snapshot")
    if provenance.get("fixture") is not False:
        blockers.append("fixture")
    if provenance.get("createHeroOrderFallback") is not False:
        blockers.append("createHeroOrderFallback")
    binding = evidence.get("identityBinding")
    if not isinstance(binding, Mapping):
        blockers.append("identityBinding_missing")
    else:
        if binding.get("method") != fuse.TRUSTED_BINDING_METHOD:
            blockers.append("identityBinding_method")
        if binding.get("complete") is not True:
            blockers.append("identityBinding_incomplete")
    samples = evidence.get("samples")
    if not isinstance(samples, list) or len(samples) < 2:
        blockers.append("need_at_least_two_timed_samples")
    else:
        for index, sample in enumerate(samples):
            if not isinstance(sample, Mapping):
                blockers.append(f"sample[{index}]_invalid")
                continue
            if "gameTimeMs" not in sample:
                blockers.append(f"sample[{index}]_untimed")
            units = sample.get("units")
            if not isinstance(units, list) or len(units) != 10:
                blockers.append(f"sample[{index}]_need_10_units")
                continue
            for unit in units:
                if not isinstance(unit, Mapping) or unit.get("mMaxHPExplicit") is not True:
                    blockers.append(f"sample[{index}]_mMaxHP_not_explicit")
                    break
    timing = evidence.get("timing")
    if not isinstance(timing, Mapping):
        blockers.append("timing_missing")
    else:
        if timing.get("unit") != "milliseconds" or timing.get("clock") != "replay_game_time":
            blockers.append("timing_clock")
        try:
            tol = int(timing.get("toleranceMs"))
        except (TypeError, ValueError):
            blockers.append("tolerance_invalid")
        else:
            if not 0 <= tol <= fuse.MAX_PRODUCT_TIME_TOLERANCE_MS:
                blockers.append("tolerance_out_of_range")
    return blockers


def is_product_complete(evidence: Mapping[str, Any]) -> bool:
    return not product_complete_blockers(evidence)


def attempt_identity_binding(
    roster: Sequence[Mapping[str, Any]],
    *,
    replication_net_ids: Optional[Sequence[int]] = None,
    create_hero_rows: Optional[Sequence[Mapping[str, Any]]] = None,
) -> Dict[str, Any]:
    """Map statsJson identities to netIds; complete only with CreateHero evidence.

    CreateHero-order / AE..B7 structural order alone is research-only
    (``createHeroOrderFallback=true``, ``complete=false``).

    CastSpellAns-derived create-hero-shaped rows (see
    ``rofl2_castspell_identity_bind``) are accepted as CreateHero-*equivalent*
    champion↔netId evidence when champion names match the roster.
    """
    if len(roster) != 10:
        return {
            "method": fuse.TRUSTED_BINDING_METHOD,
            "complete": False,
            "createHeroDecoded": False,
            "createHeroOrderFallback": False,
            "participants": [],
            "blocker": f"roster_need_10_got_{len(roster)}",
        }

    roster_rows: List[Dict[str, Any]] = []
    for row in roster:
        identity = row.get("sourceIdentity") if isinstance(row.get("sourceIdentity"), Mapping) else {}
        puuid = str(row.get("puuid") or identity.get("puuid") or "").strip() or None
        riot = row.get("riotId") if isinstance(row.get("riotId"), Mapping) else {}
        if not riot and isinstance(identity.get("riotId"), Mapping):
            riot = identity["riotId"]
        full = str(riot.get("full") or row.get("fullRiotId") or "").strip() or None
        champion = None
        champ_obj = row.get("champion")
        if isinstance(champ_obj, Mapping):
            champion = champ_obj.get("raw") or champ_obj.get("display") or champ_obj.get("asset")
        elif isinstance(champ_obj, str):
            champion = champ_obj
        roster_rows.append(
            {
                "puuid": puuid,
                "fullRiotId": full,
                "champion": champion,
                "stableKey": identity.get("key"),
            }
        )

    create_hero_decoded = False
    participants: List[Dict[str, Any]] = []
    complete = False
    order_fallback = False
    blocker: Optional[str] = None
    method_note = "awaiting_create_hero_netid_bind"

    if create_hero_rows:
        heroes = [
            h
            for h in create_hero_rows
            if isinstance(h, Mapping) and h.get("net_id") is not None
        ]
        if len(heroes) >= 10:
            create_hero_decoded = True
            # Prefer champion-name match over packet order.
            unused = list(heroes[:10])
            matched: List[Dict[str, Any]] = []
            for roster_row in roster_rows:
                champ = str(roster_row.get("champion") or "").casefold()
                hit_index = None
                for index, hero in enumerate(unused):
                    hero_champ = str(hero.get("champion") or "").casefold()
                    if champ and hero_champ and champ == hero_champ:
                        hit_index = index
                        break
                if hit_index is None:
                    matched = []
                    break
                hero = unused.pop(hit_index)
                matched.append(
                    {
                        "puuid": roster_row["puuid"],
                        "fullRiotId": roster_row["fullRiotId"],
                        "netId": int(hero["net_id"]),
                        "champion": roster_row["champion"],
                    }
                )
            if len(matched) == 10 and len({p["netId"] for p in matched}) == 10:
                participants = matched
                complete = True
                order_fallback = False
                method_note = "create_hero_champion_match"
            else:
                # Research-only CreateHero order join — never product-complete.
                order_fallback = True
                complete = False
                method_note = "create_hero_order_fallback_research_only"
                blocker = "create_hero_champion_match_incomplete"
                for index, roster_row in enumerate(roster_rows):
                    hero = heroes[index]
                    participants.append(
                        {
                            "puuid": roster_row["puuid"],
                            "fullRiotId": roster_row["fullRiotId"],
                            "netId": int(hero["net_id"]),
                            "champion": roster_row["champion"],
                            "researchOnlyOrderIndex": index,
                        }
                    )

    if not participants:
        net_ids = [
            int(n)
            for n in (replication_net_ids or PROVEN_HERO_NET_IDS)
            if 0x40000000 <= int(n) <= 0x400000FF
        ]
        # Prefer proven AE..B7 band when present.
        proven = [n for n in net_ids if n in PROVEN_HERO_NET_IDS]
        if len(proven) >= 10:
            net_ids = sorted(proven)[:10]
        else:
            net_ids = sorted(set(net_ids))[:10]
        if len(net_ids) == 10:
            order_fallback = True
            complete = False
            method_note = "replication_netid_order_fallback_research_only"
            blocker = "create_hero_bind_unavailable"
            for index, roster_row in enumerate(roster_rows):
                participants.append(
                    {
                        "puuid": roster_row["puuid"],
                        "fullRiotId": roster_row["fullRiotId"],
                        "netId": net_ids[index],
                        "champion": roster_row["champion"],
                        "researchOnlyOrderIndex": index,
                    }
                )
        else:
            blocker = "insufficient_replication_net_ids"
            for roster_row in roster_rows:
                participants.append(
                    {
                        "puuid": roster_row["puuid"],
                        "fullRiotId": roster_row["fullRiotId"],
                        "netId": None,
                        "champion": roster_row["champion"],
                    }
                )

    out: Dict[str, Any] = {
        "method": fuse.TRUSTED_BINDING_METHOD,
        "complete": complete,
        "createHeroDecoded": create_hero_decoded,
        "createHeroOrderFallback": order_fallback,
        "participants": participants,
        "note": method_note,
    }
    if blocker:
        out["blocker"] = blocker
    return out


def build_candidate_evidence(
    *,
    match: Mapping[str, Any],
    rofl_meta: Mapping[str, Any],
    roster_hash: str,
    samples: Sequence[Mapping[str, Any]],
    identity_binding: Mapping[str, Any],
    tolerance_ms: int = DEFAULT_TOLERANCE_MS,
    combat_inventory: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    order_fallback = bool(identity_binding.get("createHeroOrderFallback"))
    complete = identity_binding.get("complete") is True and not order_fallback
    # Product sourceKind only when bind is truly complete; otherwise research.
    if complete and len(samples) >= 2:
        source_kind = fuse.TRUSTED_HEALTH_SOURCE
        create_hero_flag = False
    else:
        source_kind = fuse.TIMED_RESEARCH_SOURCE_KIND
        create_hero_flag = True if order_fallback or not complete else False

    evidence: Dict[str, Any] = {
        "schema": fuse.TRUSTED_EVIDENCE_SCHEMA,
        "match": {
            "platformId": match.get("platformId"),
            "matchCode": str(match.get("matchCode")),
            "gameId": int(match.get("gameId") or match.get("matchCode") or 0),
            "gameName": str(match.get("gameName") or match.get("matchCode")),
        },
        "rofl": {
            "patch": rofl_meta.get("patch"),
            "build": rofl_meta.get("build"),
            "sha256": rofl_meta.get("sha256"),
            "basename": rofl_meta.get("basename"),
        },
        "rosterHash": roster_hash,
        "provenance": {
            "sourceKind": source_kind,
            "timed": True,
            "staticSnapshot": False,
            "fixture": False,
            "createHeroOrderFallback": create_hero_flag,
            "hpFieldIndices": {
                "mHP": [MHP_PRIMARY, MHP_SECONDARY],
                "mMaxHP": [MMAXHP_PRIMARY, MMAXHP_SECONDARY],
                "bank0": "unmapped",
                "bank0Pairs": [list(BANK0_UNKNOWN_A), list(BANK0_UNKNOWN_B)],
            },
            "combatTrusted": False,
            "abilityRanksTrusted": False,
        },
        "identityBinding": {
            "method": fuse.TRUSTED_BINDING_METHOD,
            "complete": bool(complete),
            "createHeroDecoded": bool(identity_binding.get("createHeroDecoded")),
            "createHeroOrderFallback": order_fallback,
            "participants": list(identity_binding.get("participants") or []),
            "note": identity_binding.get("note"),
        },
        "timing": {
            "unit": "milliseconds",
            "clock": "replay_game_time",
            "toleranceMs": int(tolerance_ms),
        },
        "samples": [dict(sample) for sample in samples],
        "fieldIndices": {
            "mHP": [MHP_PRIMARY, MHP_SECONDARY],
            "mMaxHP": [MMAXHP_PRIMARY, MMAXHP_SECONDARY],
            "bank0Unmapped": True,
        },
    }
    if identity_binding.get("blocker"):
        evidence["identityBinding"]["blocker"] = identity_binding["blocker"]
    if combat_inventory is not None:
        evidence["combatInventory"] = dict(combat_inventory)
        evidence["combatInventory"]["trusted"] = False
    return evidence


def fuse_dry_run(
    evidence: Mapping[str, Any],
    *,
    replay_manifest: Optional[Mapping[str, Any]] = None,
    replay_rows: Optional[Sequence[Mapping[str, Any]]] = None,
) -> Dict[str, Any]:
    """Validate evidence against product fuse gates; never writes fused JSONL."""
    blockers = product_complete_blockers(evidence)
    product_eligible = not blockers
    result: Dict[str, Any] = {
        "ok": False,
        "accepted": False,
        "productEligible": product_eligible,
        "blockers": blockers,
        "reason": None,
    }
    if blockers:
        result["reason"] = "reject:" + ",".join(blockers)
        return result
    if replay_manifest is None or replay_rows is None:
        result["ok"] = True
        result["accepted"] = False
        result["reason"] = (
            "evidence_shape_ok_but_fuse_skipped_missing_manifest_or_jsonl"
        )
        return result
    try:
        _fused, summary = fuse.fuse_product(
            list(replay_rows),
            replay_manifest=replay_manifest,
            hp_evidence=evidence,
        )
        result["ok"] = True
        result["accepted"] = True
        result["reason"] = "accept"
        result["summary"] = {
            "coverage": summary.get("coverage"),
            "fusedFrames": summary.get("fusedFrames"),
            "sampleCount": summary.get("sampleCount"),
            "combatStatsKnown": summary.get("combatStatsKnown"),
            "abilityRanksKnown": summary.get("abilityRanksKnown"),
        }
    except DecryptError as exc:
        result["reason"] = f"reject:{exc}"
        result["blockers"] = [str(exc)]
        result["productEligible"] = False
    return result


def _inventory_combat(state: Mapping[int, HeroReplicationState]) -> Dict[str, Any]:
    keys: Dict[str, int] = {}
    for st in state.values():
        for name in st.combat:
            keys[name] = keys.get(name, 0) + 1
    return {
        "trusted": False,
        "note": (
            "primary-1 combat-ish floats may appear on type-107 vectors; "
            "not product-trusted until a separate proof pass"
        ),
        "observedKeys": sorted(keys),
        "observationCounts": keys,
    }


def _load_create_hero_rows(path: Optional[Path]) -> Optional[List[Dict[str, Any]]]:
    if path is None or not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    events: Sequence[Mapping[str, Any]]
    if isinstance(payload, list):
        events = payload
    elif isinstance(payload, Mapping):
        raw = payload.get("events") or payload.get("CreateHero") or []
        if isinstance(raw, list):
            events = raw
        else:
            return None
    else:
        return None
    heroes = heroes_from_events(events)
    return heroes if heroes else None


def _chunk_sample_time_s(part: Mapping[str, Any], heroes: Sequence[Mapping[str, Any]]) -> float:
    """Prefer this chunk's replication packet times over cumulative hero state."""
    row_times = [
        float(row.get("time") or 0.0)
        for row in (part.get("rows") or [])
        if row.get("time") is not None
    ]
    if row_times:
        return max(row_times)
    if part.get("timeEnd") is not None:
        return float(part["timeEnd"])
    return max((float(h.get("time") or 0.0) for h in heroes), default=0.0)


def collect_timed_samples_from_state_walk(
    *,
    chunks: Sequence[Mapping[str, Any]],
    mu: Any,
    heap: BumpHeap,
    max_samples: int,
    max_blocks: int,
    min_spacing_ms: int = MIN_SAMPLE_SPACING_MS,
) -> Tuple[List[Dict[str, Any]], Dict[int, HeroReplicationState], Dict[str, Any]]:
    """Walk chunks once; snapshot HP at spaced times once acceptance passes."""
    pre_targets = set(select_chunk_indices(len(chunks), max_samples))
    state: Dict[int, HeroReplicationState] = {}
    ci_pool: Dict[int, int] = {}
    use_hits: List[int] = []
    samples: List[Dict[str, Any]] = []
    seen_times: set[int] = set()
    post_accept_targets: Optional[set[int]] = None
    decode_meta: Dict[str, Any] = {
        "chunksScanned": 0,
        "replicationPackets": 0,
        "targetChunkIndices": sorted(pre_targets),
        "acceptanceHits": 0,
        "firstAcceptanceChunk": None,
        "postAcceptTargets": None,
    }

    for chunk_index, chunk in enumerate(chunks):
        part = _drive_body_replication(
            mu=mu,
            heap=heap,
            body=chunk["bytes"],
            state=state,
            max_blocks=max_blocks,
            ci_pool=ci_pool,
            use_hits=use_hits,
        )
        decode_meta["chunksScanned"] = chunk_index + 1
        decode_meta["replicationPackets"] += int(part.get("replicationPackets") or 0)

        snap = acceptance_snapshot(state)
        if not snap["passed"]:
            continue
        decode_meta["acceptanceHits"] += 1
        if decode_meta["firstAcceptanceChunk"] is None:
            decode_meta["firstAcceptanceChunk"] = chunk_index
            span = list(range(chunk_index, len(chunks)))
            if len(span) <= max_samples:
                post_accept_targets = set(span)
            else:
                local = select_chunk_indices(len(span), max_samples)
                post_accept_targets = {span[i] for i in local}
            decode_meta["postAcceptTargets"] = sorted(post_accept_targets)

        heroes = snap["heroes"][:10]
        if len(heroes) < 10:
            continue
        game_time_ms = game_time_ms_from_seconds(_chunk_sample_time_s(part, heroes))
        if game_time_ms < 0 or game_time_ms in seen_times:
            continue

        last_ms = samples[-1]["gameTimeMs"] if samples else None
        spaced = last_ms is None or (game_time_ms - int(last_ms)) >= int(min_spacing_ms)
        active_targets = post_accept_targets if post_accept_targets is not None else pre_targets
        should_take = False
        if not samples:
            should_take = True
        elif chunk_index in active_targets and spaced:
            should_take = True
        elif spaced and len(samples) < max_samples and chunk_index == len(chunks) - 1:
            should_take = True
        elif len(samples) < 2 and chunk_index == len(chunks) - 1:
            should_take = True
        if not should_take:
            continue

        try:
            sample = make_sample(
                game_time_ms=game_time_ms,
                heroes=heroes,
                chunk_index=chunk_index,
            )
        except ValueError:
            continue
        samples.append(sample)
        seen_times.add(game_time_ms)
        if len(samples) >= max_samples and chunk_index >= max(active_targets or [chunk_index]):
            break

    return samples, state, decode_meta


def decode_timed_hp(
    *,
    rofl: Path,
    league_binary: Path = DEFAULT_LEAGUE_BINARY,
    work_dir: Optional[Path] = None,
    max_samples: int = DEFAULT_MAX_SAMPLES,
    max_blocks: int = 8000,
    max_chunks: Optional[int] = None,
    create_hero_events: Optional[Path] = None,
    replay_manifest: Optional[Mapping[str, Any]] = None,
    replay_rows: Optional[Sequence[Mapping[str, Any]]] = None,
    stub_use_map: bool = True,
) -> Dict[str, Any]:
    """Live Unicorn timed HP walk + identity bind + fuse dry-run honesty."""
    if not league_binary.is_file():
        return {
            "ok": False,
            "status": "blocked_need_league_binary",
            "error": f"missing {league_binary}",
            "productEligible": False,
            "samples": [],
        }
    if not rofl.is_file():
        return {
            "ok": False,
            "status": "blocked_need_rofl",
            "error": f"missing {rofl}",
            "productEligible": False,
            "samples": [],
        }
    try:
        from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM
    except ImportError as exc:
        return {
            "ok": False,
            "status": "blocked_unicorn_missing",
            "error": str(exc),
            "productEligible": False,
            "samples": [],
        }

    identity = rofl_metadata.inspect_rofl_metadata(rofl)
    create_hero_rows = _load_create_hero_rows(create_hero_events)

    if work_dir is None:
        work_dir = Path(tempfile.mkdtemp(prefix="lol-timed-hp-"))
    work_dir.mkdir(parents=True, exist_ok=True)
    arm64_path = work_dir / "LeagueofLegends.arm64"
    spike.thin_arm64(league_binary, arm64_path)
    data = arm64_path.read_bytes()
    segments = spike._parse_segments(data)
    text = next(s for s in segments if s[0] == "__TEXT")
    prologue_ok = is_valid_use_replication_prologue(
        data, text_vm=text[1], text_off=text[3]
    )

    info = parse_rofl2(rofl)
    chunks = [s for s in extract_segments(info["payload"])["segments"] if s.get("type") == 1]
    if max_chunks is not None:
        chunks = chunks[: max(0, int(max_chunks))]
    if not chunks:
        return {
            "ok": False,
            "status": "blocked_no_chunks",
            "productEligible": False,
            "samples": [],
            "match": {
                "platformId": identity["platformId"],
                "matchCode": identity["matchCode"],
            },
        }

    mu = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
    map_binary(mu, data, segments)
    for base, size in (
        (ARENA_BASE, 0x00100000),
        (HEAP_BASE, HEAP_SIZE),
        (STACK_BASE, STACK_SIZE),
        (BUF_BASE, BUF_SIZE),
        (SCRATCH, 0x00100000),
    ):
        try:
            mu.mem_map(base, size)
        except Exception:  # noqa: BLE001
            pass
    heap = BumpHeap()
    install_block_runtime_hooks(mu, heap)
    install_unmapped_stub(mu)
    mu.mem_write(TYPE_COUNT_GLOBAL, struct.pack("<I", TYPE_COUNT_VALUE))
    if stub_use_map:
        install_use_map_stub(mu, heap)

    samples, state, decode_meta = collect_timed_samples_from_state_walk(
        chunks=chunks,
        mu=mu,
        heap=heap,
        max_samples=max_samples,
        max_blocks=max_blocks,
    )
    combat_inventory = _inventory_combat(state)
    net_ids = sorted(state.keys())
    binding = attempt_identity_binding(
        identity["participants"],
        replication_net_ids=net_ids,
        create_hero_rows=create_hero_rows,
    )
    evidence = build_candidate_evidence(
        match={
            "platformId": identity["platformId"],
            "matchCode": identity["matchCode"],
            "gameId": identity["gameId"],
            "gameName": identity["matchCode"],
        },
        rofl_meta={
            "patch": identity["patch"],
            "build": identity["build"],
            "sha256": identity["sha256"],
            "basename": identity["basename"],
        },
        roster_hash=str(identity["rosterHash"]),
        samples=samples,
        identity_binding=binding,
        combat_inventory=combat_inventory,
    )
    dry = fuse_dry_run(
        evidence,
        replay_manifest=replay_manifest,
        replay_rows=replay_rows,
    )
    status = "timed_hp_samples_emitted" if len(samples) >= 2 else (
        "timed_hp_insufficient_samples" if samples else "replication_hp_not_accepted"
    )
    return {
        "ok": len(samples) >= 2,
        "status": status,
        "arch": "arm64",
        "rofl": str(rofl),
        "replicationType": REPLICATION_TYPE_CANDIDATE,
        "useReplicationPrologueOk": prologue_ok,
        "decode": decode_meta,
        "sampleCount": len(samples),
        "samples": samples,
        "identityBinding": binding,
        "evidence": evidence,
        "productEligible": bool(dry.get("productEligible")) and is_product_complete(evidence),
        "fuseDryRun": dry,
        "combatTrusted": False,
        "fieldIndices": evidence["fieldIndices"],
        "workDir": str(work_dir),
        "blocker": (
            None
            if dry.get("accepted")
            else (dry.get("reason") or binding.get("blocker") or status)
        ),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rofl", type=Path, default=DEFAULT_ROFL)
    ap.add_argument("--league-binary", type=Path, default=DEFAULT_LEAGUE_BINARY)
    ap.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Write rofl-trusted-hp-v1 candidate JSON",
    )
    ap.add_argument(
        "--json-out",
        type=Path,
        default=None,
        help="Write full timed-HP report JSON",
    )
    ap.add_argument("--max-samples", type=int, default=DEFAULT_MAX_SAMPLES)
    ap.add_argument("--max-blocks", type=int, default=8000)
    ap.add_argument("--max-chunks", type=int, default=None)
    ap.add_argument(
        "--create-hero-events",
        type=Path,
        default=DEFAULT_CREATE_HERO_EVENTS
        if DEFAULT_CREATE_HERO_EVENTS.is_file()
        else None,
        help=(
            "Maknee-shaped CreateHero events JSON (CastSpellAns bind). "
            f"Defaults to {DEFAULT_CREATE_HERO_EVENTS} when that file exists."
        ),
    )
    ap.add_argument("--replay-manifest", type=Path, default=None)
    ap.add_argument("--replay-jsonl", type=Path, default=None)
    ap.add_argument("--work-dir", type=Path, default=None)
    ap.add_argument("--no-use-stub", action="store_true")
    args = ap.parse_args()

    replay_manifest = None
    if args.replay_manifest and args.replay_manifest.is_file():
        replay_manifest = json.loads(args.replay_manifest.read_text(encoding="utf-8"))
    replay_rows = None
    if args.replay_jsonl and args.replay_jsonl.is_file():
        replay_rows = []
        with args.replay_jsonl.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    replay_rows.append(json.loads(line))

    report = decode_timed_hp(
        rofl=args.rofl,
        league_binary=args.league_binary,
        work_dir=args.work_dir,
        max_samples=max(1, int(args.max_samples)),
        max_blocks=int(args.max_blocks),
        max_chunks=args.max_chunks,
        create_hero_events=args.create_hero_events,
        replay_manifest=replay_manifest,
        replay_rows=replay_rows,
        stub_use_map=not args.no_use_stub,
    )
    evidence = report.get("evidence")
    if args.out and isinstance(evidence, Mapping):
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(evidence, indent=2, default=str) + "\n",
            encoding="utf-8",
        )
        print(f"wrote evidence {args.out}")
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(
            json.dumps(report, indent=2, default=str) + "\n",
            encoding="utf-8",
        )
        print(f"wrote report {args.json_out}")
    else:
        print(json.dumps(report, indent=2, default=str))

    dry = report.get("fuseDryRun") or {}
    print(
        f"status={report.get('status')} samples={report.get('sampleCount')} "
        f"productEligible={report.get('productEligible')} "
        f"fuse={dry.get('reason')} bindComplete="
        f"{(report.get('identityBinding') or {}).get('complete')}"
    )
    return 0 if report.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
