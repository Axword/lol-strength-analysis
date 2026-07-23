#!/usr/bin/env python3
"""
Fuse decrypted Replication HP onto a Replay API rfc461 JSONL stream.

Positions / level / items / alive stay from the Replay API capture. HP and
healthMax are injected from a decrypt probe HP snapshot (or maknee-shaped
Replication events) at matching gameTime with honest source markers.

Ability ranks and missing combat stats stay unavailable — calculator Send
remains blocked.

Static snapshot mode (``--static-snapshot`` / probe-only) is research/demo
only: provenance is marked ``researchOnly`` + ``publicationBlocked`` and must
never pass a product publication gate.

Product example:
  python3 scripts/fuse_replay_api_hp.py --product \\
    --jsonl artifacts/rofl/3264361042/events.rfc461.jsonl \\
    --replay-manifest artifacts/rofl/3264361042/manifest.json \\
    --hp-evidence /tmp/3264361042.trusted-hp.json \\
    -o artifacts/rofl/3264361042/events.hp-trusted.rfc461.jsonl

Research example:
  python3 scripts/fuse_replay_api_hp.py \\
    --jsonl ~/Desktop/events_BR1-3264383283_replay_api_1hz.jsonl \\
    --probe /tmp/decrypt_probe_fixture.json \\
    -o /tmp/events_fused_hp.jsonl
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rofl2_packet_decrypt_probe import DecryptError, extract_hp_snapshot_from_events  # noqa: E402

HEALTH_SOURCE = "rofl2_replication_decrypt"
TRUSTED_HEALTH_SOURCE = "rofl2_replication_decrypt_timed_identity_bound"
TRUSTED_EVIDENCE_SCHEMA = "rofl-trusted-hp-v1"
TRUSTED_EVIDENCE_MODE = "timed_identity_bound"
TRUSTED_BINDING_METHOD = "stable_identity_to_net_id"
MAX_PRODUCT_TIME_TOLERANCE_MS = 500
ABILITY_RANKS_SOURCE = "unavailable"
DEFAULT_COMBAT_STATS_SOURCE = "unavailable"
STATIC_SNAPSHOT_SOURCE_KIND = "research_static_hp_snapshot"
TIMED_RESEARCH_SOURCE_KIND = "research_timed_hp_createhero_order"
COMBAT_FIELDS = (
    "attackDamage",
    "abilityPower",
    "armor",
    "magicResist",
    "attackSpeed",
)
def _load_jsonl(path: Path) -> List[dict]:
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, separators=(",", ":")) + "\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def _object(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise DecryptError(f"{label} must be an object")
    return value


def _stable_identity(row: Mapping[str, Any], *, label: str) -> str:
    puuid = str(row.get("puuid") or row.get("PUUID") or "").strip()
    if puuid:
        return f"puuid:{puuid}"
    riot = row.get("riotId")
    full = ""
    if isinstance(riot, Mapping):
        full = str(riot.get("full") or "").strip()
    full = str(
        full
        or row.get("fullRiotId")
        or row.get("summonerName")
        or (
            f"{row.get('riotIdGameName')}#{row.get('riotIdTagLine')}"
            if row.get("riotIdGameName") and row.get("riotIdTagLine")
            else ""
        )
    ).strip()
    if full and "#" in full:
        return f"riotid:{full.casefold()}"
    raise DecryptError(f"{label} lacks stable PUUID/full Riot ID")


def _riot_id_full(row: Mapping[str, Any]) -> str:
    riot = row.get("riotId")
    if isinstance(riot, Mapping):
        full = str(riot.get("full") or "").strip()
        if full and "#" in full:
            return full
    game_name = str(row.get("riotIdGameName") or "").strip()
    tag = str(row.get("riotIdTagLine") or "").strip()
    if game_name and tag:
        return f"{game_name}#{tag}"
    for key in ("fullRiotId", "summonerName", "playerName"):
        value = str(row.get(key) or "").strip()
        if value and "#" in value:
            return value
    return ""


def _champion_name(row: Mapping[str, Any]) -> str:
    champ = row.get("champion")
    if isinstance(champ, Mapping):
        return str(
            champ.get("raw") or champ.get("display") or champ.get("asset") or ""
        ).strip()
    return str(row.get("championName") or champ or "").strip()


def backfill_game_info_identities_from_manifest(
    rows: Sequence[Mapping[str, Any]],
    replay_manifest: Mapping[str, Any],
) -> List[dict]:
    """Fill missing game_info PUUID/Riot ID fields from the same-match manifest.

    Replay API / liveclient captures often carry ``awakening#0000`` in
    summonerName while leaving ``puuid`` null. Product fuse keys roster by
    PUUID from ROFL ``statsJson`` in the manifest — backfill closes that gap
    without inventing identities.
    """
    manifest_rows = replay_manifest.get("participants")
    if not isinstance(manifest_rows, list) or len(manifest_rows) != 10:
        raise DecryptError("replay manifest participants must contain exactly 10 rows")

    by_riot: Dict[str, Mapping[str, Any]] = {}
    by_champ: Dict[str, Mapping[str, Any]] = {}
    for index, raw in enumerate(manifest_rows):
        row = _object(raw, f"replay manifest participants[{index}]")
        riot_full = _riot_id_full(row)
        if riot_full:
            key = riot_full.casefold()
            if key in by_riot:
                raise DecryptError(f"duplicate manifest Riot ID {riot_full!r}")
            by_riot[key] = row
        champ = _champion_name(row)
        if champ:
            ckey = champ.casefold()
            if ckey in by_champ:
                # Ambiguous champion duplicate — Riot ID match only.
                by_champ.pop(ckey, None)
            else:
                by_champ[ckey] = row

    out: List[dict] = []
    for row in rows:
        copied = dict(row)
        if copied.get("rfc461Schema") != "game_info":
            out.append(copied)
            continue
        participants = copied.get("participants")
        if not isinstance(participants, list) or len(participants) != 10:
            raise DecryptError("canonical game_info must list exactly 10 participants")
        patched: List[dict] = []
        used_keys: set[str] = set()
        for index, raw_participant in enumerate(participants):
            participant = dict(_object(raw_participant, f"game_info participants[{index}]"))
            try:
                existing = _stable_identity(
                    participant, label=f"game_info participants[{index}]"
                )
            except DecryptError:
                existing = ""
            if existing.startswith("puuid:"):
                patched.append(participant)
                used_keys.add(existing)
                continue
            riot_full = _riot_id_full(participant)
            match = by_riot.get(riot_full.casefold()) if riot_full else None
            if match is None:
                champ = _champion_name(participant)
                match = by_champ.get(champ.casefold()) if champ else None
            if match is None:
                raise DecryptError(
                    f"game_info participants[{index}] has no ROFL/manifest identity match"
                )
            puuid = str(match.get("puuid") or "").strip()
            riot = match.get("riotId") if isinstance(match.get("riotId"), Mapping) else {}
            game_name = str(riot.get("gameName") or "").strip()
            tag = str(riot.get("tagLine") or "").strip()
            full = str(riot.get("full") or "").strip()
            if not puuid and not (full and "#" in full):
                raise DecryptError(
                    f"manifest identity for game_info participants[{index}] is incomplete"
                )
            if puuid:
                participant["puuid"] = puuid
            if game_name:
                participant["riotIdGameName"] = game_name
            if tag:
                participant["riotIdTagLine"] = tag
            if full and "#" in full:
                participant["riotId"] = {
                    "gameName": game_name or full.split("#", 1)[0],
                    "tagLine": tag or full.split("#", 1)[1],
                    "full": full,
                    "normalized": full.casefold(),
                }
                if not participant.get("summonerName"):
                    participant["summonerName"] = full
                if not participant.get("playerName"):
                    participant["playerName"] = full
            key = _stable_identity(
                participant, label=f"game_info participants[{index}]"
            )
            if key in used_keys:
                raise DecryptError(f"duplicate backfilled identity {key!r}")
            used_keys.add(key)
            patched.append(participant)
        copied["participants"] = patched
        out.append(copied)
    return out


def align_hp_samples_to_stats_frames(
    samples: Sequence[Mapping[str, Any]],
    frame_times_ms: Sequence[int],
    *,
    max_delta_ms: int = MAX_PRODUCT_TIME_TOLERANCE_MS,
) -> List[dict]:
    """Snap decrypt sample times onto Replay API 1Hz frame times within tolerance."""
    if not frame_times_ms:
        raise DecryptError("cannot align HP samples without stats_update frame times")
    frames = sorted({int(t) for t in frame_times_ms})
    aligned: List[dict] = []
    used: set[int] = set()
    for index, raw in enumerate(samples):
        sample = dict(_object(raw, f"HP sample[{index}]"))
        try:
            source_t = int(sample.get("gameTimeMs"))
        except (TypeError, ValueError):
            raise DecryptError(f"HP sample[{index}] is untimed") from None
        nearest = min(frames, key=lambda frame: abs(frame - source_t))
        delta = abs(nearest - source_t)
        if delta > int(max_delta_ms):
            continue
        if nearest in used:
            continue
        used.add(nearest)
        sample["gameTimeMs"] = nearest
        sample["alignment"] = {
            "sourceGameTimeMs": source_t,
            "snappedToFrameMs": nearest,
            "deltaMs": delta,
        }
        aligned.append(sample)
    if len(aligned) < 2:
        raise DecryptError(
            "fewer than two HP samples align to Replay API frames within tolerance"
        )
    return aligned


def _identity_rows(
    rows: Any,
    *,
    label: str,
    require_manifest_stable: bool = False,
) -> Dict[str, Mapping[str, Any]]:
    if not isinstance(rows, list) or len(rows) != 10:
        raise DecryptError(f"{label} must contain exactly 10 participants")
    out: Dict[str, Mapping[str, Any]] = {}
    for index, raw in enumerate(rows):
        row = _object(raw, f"{label}[{index}]")
        source_identity: Optional[Mapping[str, Any]] = None
        if require_manifest_stable:
            source_identity = _object(
                row.get("sourceIdentity"),
                f"{label}[{index}].sourceIdentity",
            )
            if source_identity.get("stable") is not True:
                raise DecryptError(f"{label}[{index}] is not marked stable")
        key = _stable_identity(row, label=f"{label}[{index}]")
        if source_identity is not None and source_identity.get("key") != key:
            raise DecryptError(
                f"{label}[{index}] stable identity key does not match participant"
            )
        if key in out:
            raise DecryptError(f"{label} has duplicate stable identity {key!r}")
        out[key] = row
    return out


def _exact_match_contract(
    replay_manifest: Mapping[str, Any],
    hp_evidence: Mapping[str, Any],
    coverage: Mapping[str, Any],
    game_info: Mapping[str, Any],
) -> None:
    replay_match = _object(replay_manifest.get("match"), "replay manifest match")
    hp_match = _object(hp_evidence.get("match"), "HP evidence match")
    for key in ("platformId", "matchCode", "gameId", "gameName"):
        left = replay_match.get(key)
        right = hp_match.get(key)
        if left in (None, "") or right in (None, "") or str(left) != str(right):
            raise DecryptError(
                f"same-match contract failed for {key}: replay={left!r} hp={right!r}"
            )
    match_code = str(replay_match["matchCode"])
    try:
        replay_game_id = int(replay_match["gameId"])
        stream_game_id = int(game_info.get("gameID") or 0)
    except (TypeError, ValueError):
        raise DecryptError("match/game_info gameID is invalid") from None
    if not match_code.isdigit() or str(replay_game_id) != match_code:
        raise DecryptError("replay manifest matchCode/gameId is inconsistent")
    if str(replay_match["gameName"]) != match_code:
        raise DecryptError("replay manifest gameName must equal exact match code")
    if stream_game_id != replay_game_id:
        raise DecryptError("canonical game_info gameID does not match source manifests")
    stream_name = str(game_info.get("gameName") or "")
    if stream_name != match_code:
        raise DecryptError("canonical game_info gameName does not match source manifests")
    stream_platform = str(game_info.get("platformID") or "")
    if stream_platform != str(replay_match["platformId"]):
        raise DecryptError("canonical game_info platformID does not match source manifests")
    coverage_game_id = coverage.get("gameID")
    if coverage_game_id not in (None, ""):
        try:
            coverage_game_id_int = int(coverage_game_id)
        except (TypeError, ValueError):
            raise DecryptError("canonical coverage gameID is invalid") from None
        if coverage_game_id_int != replay_game_id:
            raise DecryptError(
                "canonical coverage gameID does not match source manifests"
            )

    replay_rofl = _object(replay_manifest.get("rofl"), "replay manifest rofl")
    hp_rofl = _object(hp_evidence.get("rofl"), "HP evidence rofl")
    for key in ("patch", "build"):
        left = str(replay_rofl.get(key) or "")
        right = str(hp_rofl.get(key) or "")
        if not left or not right or left != right:
            raise DecryptError(
                f"ROFL {key} mismatch or missing: replay={left!r} hp={right!r}"
            )
    replay_hash = str(replay_rofl.get("sha256") or "").lower()
    hp_hash = str(hp_rofl.get("sha256") or "").lower()
    if replay_hash or hp_hash:
        if (
            not re.fullmatch(r"[0-9a-f]{64}", replay_hash)
            or not re.fullmatch(r"[0-9a-f]{64}", hp_hash)
            or replay_hash != hp_hash
        ):
            raise DecryptError("ROFL SHA-256 mismatch or missing from one source")
    replay_roster_hash = str(replay_manifest.get("rosterHash") or "")
    hp_roster_hash = str(hp_evidence.get("rosterHash") or "")
    if (
        not re.fullmatch(r"[0-9a-fA-F]{64}", replay_roster_hash)
        or replay_roster_hash != hp_roster_hash
    ):
        raise DecryptError("roster hash mismatch or missing")


def _validate_product_sources(
    rows: Sequence[Mapping[str, Any]],
    replay_manifest: Mapping[str, Any],
    hp_evidence: Mapping[str, Any],
) -> tuple[
    Mapping[str, Any],
    Mapping[str, Any],
    Dict[int, int],
    Dict[int, str],
    List[dict[str, Any]],
    int,
]:
    coverage = next(
        (row for row in rows if row.get("rfc461Schema") == "rofl_coverage"),
        None,
    )
    game_info = next(
        (row for row in rows if row.get("rfc461Schema") == "game_info"),
        None,
    )
    if coverage is None or game_info is None:
        raise DecryptError("product fusion requires canonical coverage and game_info")
    provenance = _object(coverage.get("provenance"), "canonical provenance")
    if provenance.get("hpCoverage") != "none":
        raise DecryptError("product HP fusion requires an unfused hpCoverage=none source")
    if any(
        provenance.get(key) is True
        for key in ("publicationBlocked", "researchOnly", "schemaProof")
    ):
        raise DecryptError("product fusion refuses fixture/research/schema-proof source")
    source_text = " ".join(
        str(value or "").casefold()
        for value in (
            coverage.get("source"),
            provenance.get("source"),
            provenance.get("sourceKind"),
            provenance.get("notes"),
        )
    )
    if any(
        marker in source_text
        for marker in (
            "fixture",
            "schema_proof",
            "schema-proof",
            "research",
            "static",
            "synthetic",
        )
    ):
        raise DecryptError("product fusion refuses non-product source provenance")
    gates = _object(replay_manifest.get("productGates"), "replay manifest productGates")
    if (
        gates.get("stableIdentityComplete") is not True
        or gates.get("activeReplayIdentityVerified") is not True
        or gates.get("captureComplete") is not True
    ):
        raise DecryptError("replay manifest lacks captured stable-identity product gates")

    _exact_match_contract(replay_manifest, hp_evidence, coverage, game_info)
    manifest_identities = _identity_rows(
        replay_manifest.get("participants"),
        label="replay manifest participants",
        require_manifest_stable=True,
    )
    stream_identities = _identity_rows(
        game_info.get("participants"),
        label="canonical game_info participants",
    )
    if set(manifest_identities) != set(stream_identities):
        raise DecryptError("canonical roster identities do not match replay manifest")

    if hp_evidence.get("schema") != TRUSTED_EVIDENCE_SCHEMA:
        raise DecryptError(
            f"HP evidence schema must be {TRUSTED_EVIDENCE_SCHEMA!r}"
        )
    hp_provenance = _object(hp_evidence.get("provenance"), "HP evidence provenance")
    if hp_provenance.get("sourceKind") != TRUSTED_HEALTH_SOURCE:
        raise DecryptError("HP evidence sourceKind is not timed identity-bound decrypt")
    if (
        hp_provenance.get("timed") is not True
        or hp_provenance.get("staticSnapshot") is not False
        or hp_provenance.get("fixture") is not False
        or hp_provenance.get("createHeroOrderFallback") is not False
    ):
        raise DecryptError(
            "HP evidence must be timed, non-static, non-fixture, and not CreateHero-order"
        )

    binding = _object(hp_evidence.get("identityBinding"), "HP identityBinding")
    if (
        binding.get("method") != TRUSTED_BINDING_METHOD
        or binding.get("complete") is not True
    ):
        raise DecryptError("HP evidence lacks complete stable identity/netId binding")
    binding_identities = _identity_rows(
        binding.get("participants"),
        label="HP identity binding participants",
    )
    if set(binding_identities) != set(manifest_identities):
        raise DecryptError("HP identity binding roster does not match replay roster")
    pid_by_identity = {
        identity: int(row["participantID"])
        for identity, row in stream_identities.items()
    }
    net_ids: set[int] = set()
    pid_to_net: Dict[int, int] = {}
    pid_to_identity: Dict[int, str] = {}
    pid_to_roster_label: Dict[int, Dict[str, str]] = {}
    for identity, row in binding_identities.items():
        try:
            net_id = int(row.get("netId"))
        except (TypeError, ValueError):
            raise DecryptError(f"binding {identity!r} has invalid netId") from None
        if net_id <= 0 or net_id in net_ids:
            raise DecryptError(f"binding has invalid/duplicate netId {net_id!r}")
        net_ids.add(net_id)
        participant_id = pid_by_identity[identity]
        pid_to_net[participant_id] = net_id
        pid_to_identity[participant_id] = identity
        champ = str(row.get("champion") or "").strip()
        full = str(row.get("fullRiotId") or "").strip()
        if not champ or not full or "#" not in full:
            raise DecryptError(
                f"binding {identity!r} missing champion/fullRiotId for roster labels"
            )
        pid_to_roster_label[participant_id] = {
            "championName": champ,
            "fullRiotId": full,
            "playerName": full.split("#", 1)[0],
        }

    timing = _object(hp_evidence.get("timing"), "HP evidence timing")
    if timing.get("unit") != "milliseconds" or timing.get("clock") != "replay_game_time":
        raise DecryptError("HP evidence timing must use replay_game_time milliseconds")
    try:
        tolerance_ms = int(timing.get("toleranceMs"))
    except (TypeError, ValueError):
        raise DecryptError("HP evidence toleranceMs missing/invalid") from None
    if not 0 <= tolerance_ms <= MAX_PRODUCT_TIME_TOLERANCE_MS:
        raise DecryptError(
            f"HP evidence tolerance must be 0..{MAX_PRODUCT_TIME_TOLERANCE_MS}ms"
        )

    raw_samples = hp_evidence.get("samples")
    if not isinstance(raw_samples, list) or len(raw_samples) < 2:
        raise DecryptError("product HP evidence requires at least two timed samples")
    samples: List[dict[str, Any]] = []
    seen_times: set[int] = set()
    for sample_index, raw_sample in enumerate(raw_samples):
        sample = _object(raw_sample, f"HP sample[{sample_index}]")
        try:
            game_time_ms = int(sample.get("gameTimeMs"))
        except (TypeError, ValueError):
            raise DecryptError(f"HP sample[{sample_index}] is untimed") from None
        if game_time_ms < 0 or game_time_ms in seen_times:
            raise DecryptError("HP sample times must be unique non-negative replay times")
        seen_times.add(game_time_ms)
        raw_units = sample.get("units")
        if not isinstance(raw_units, list) or len(raw_units) != 10:
            raise DecryptError(f"HP sample[{sample_index}] must contain 10 bound units")
        by_net: Dict[int, Tuple[float, float]] = {}
        for unit_index, raw_unit in enumerate(raw_units):
            unit = _object(raw_unit, f"HP sample[{sample_index}].units[{unit_index}]")
            try:
                net_id = int(unit.get("netId"))
                hp = float(unit.get("mHP"))
                hp_max = float(unit.get("mMaxHP"))
            except (TypeError, ValueError):
                raise DecryptError("HP sample has invalid netId/mHP/mMaxHP") from None
            if unit.get("mMaxHPExplicit") is not True:
                raise DecryptError("product HP sample requires explicit mMaxHP evidence")
            if (
                net_id not in net_ids
                or net_id in by_net
                or not math.isfinite(hp)
                or not math.isfinite(hp_max)
                or hp < 0
                or hp_max <= 100
                or hp > hp_max
            ):
                raise DecryptError(
                    f"HP sample has invalid/unbound values netId={net_id}: {hp}/{hp_max}"
                )
            by_net[net_id] = (hp, hp_max)
        if set(by_net) != net_ids:
            raise DecryptError("HP sample netIds do not exactly match validated binding")
        samples.append({"gameTimeMs": game_time_ms, "byNetId": by_net})
    samples.sort(key=lambda sample: sample["gameTimeMs"])
    return (
        coverage,
        game_info,
        pid_to_net,
        pid_to_identity,
        pid_to_roster_label,
        samples,
        tolerance_ms,
    )


def _hp_by_participant_from_probe(probe: Mapping[str, Any]) -> Dict[int, Tuple[float, float]]:
    snap = probe.get("hpSnapshot") or {}
    heroes = snap.get("heroes") or []
    if not heroes:
        raise DecryptError("probe hpSnapshot.heroes missing — run a successful decrypt first")
    out: Dict[int, Tuple[float, float]] = {}
    for h in heroes:
        pid = int(h["participantID"])
        hp = float(h["mHP"])
        hp_max = float(h["mMaxHP"])
        if not (0 < hp <= hp_max and hp_max > 100):
            raise DecryptError(f"invalid HP for pid={pid}: {hp}/{hp_max}")
        out[pid] = (hp, hp_max)
    if len(out) < 10:
        raise DecryptError(f"need HP for 10 participants, got {len(out)}")
    return out


def _hp_timeline_from_events(
    events: Sequence[Mapping[str, Any]],
) -> List[Tuple[float, Dict[int, Tuple[float, float]]]]:
    """Build (time_s, pid→(hp,hpMax)) samples by replaying Replication in order."""
    # participantID mapping via CreateHero order
    heroes = []
    seen = set()
    for e in events:
        h = e.get("CreateHero") if isinstance(e, Mapping) else None
        if not isinstance(h, Mapping):
            continue
        nid = int(h["net_id"])
        if nid in seen:
            continue
        seen.add(nid)
        heroes.append({"net_id": nid, "participantID": len(heroes) + 1})
        if len(heroes) >= 10:
            break
    by_net = {h["net_id"]: h["participantID"] for h in heroes}
    hp: Dict[int, float] = {}
    hp_max: Dict[int, float] = {}
    samples: List[Tuple[float, Dict[int, Tuple[float, float]]]] = []

    def flush(t: float) -> None:
        row: Dict[int, Tuple[float, float]] = {}
        for nid, pid in by_net.items():
            if nid not in hp and nid not in hp_max:
                continue
            cur = hp.get(nid)
            mx = hp_max.get(nid)
            if mx is None:
                mx = max(cur or 1.0, 1.0)
            if cur is None:
                cur = mx
            mx = max(mx, cur, 1.0)
            row[pid] = (float(cur), float(mx))
        if len(row) >= 10 and all(0 < a <= b and b > 100 for a, b in row.values()):
            samples.append((t, dict(row)))

    for e in events:
        if not isinstance(e, Mapping) or "Replication" not in e:
            continue
        payload = e["Replication"]
        if not isinstance(payload, Mapping):
            continue
        try:
            t = float(payload.get("time"))
        except (TypeError, ValueError):
            continue
        for nid_s, rep in (payload.get("net_id_to_replication_datas") or {}).items():
            nid = int(nid_s)
            if nid not in by_net or not isinstance(rep, Mapping):
                continue
            name = (rep.get("name") or "").strip()
            data = rep.get("data") or {}
            val = None
            if isinstance(data, Mapping):
                for k in ("Float", "Int", "Uint"):
                    if k in data:
                        val = float(data[k])
                        break
            if val is None:
                continue
            if name == "mHP":
                hp[nid] = val
            elif name == "mMaxHP":
                hp_max[nid] = val
        flush(t)
    return samples


def _nearest_hp(
    samples: Sequence[Tuple[float, Dict[int, Tuple[float, float]]]],
    time_s: float,
    tol_s: float,
) -> Optional[Dict[int, Tuple[float, float]]]:
    if not samples:
        return None
    best = None
    best_dt = None
    for t, row in samples:
        dt = abs(t - time_s)
        if best_dt is None or dt < best_dt:
            best_dt = dt
            best = row
    if best_dt is None or best_dt > tol_s:
        return None
    return best


def fuse_product(
    rows: Sequence[Mapping[str, Any]],
    *,
    replay_manifest: Mapping[str, Any],
    hp_evidence: Mapping[str, Any],
    time_tolerance_ms: Optional[int] = None,
) -> tuple[List[dict], dict[str, Any]]:
    """Fuse only timed, same-match, identity-bound Replication HP evidence."""
    working_rows = backfill_game_info_identities_from_manifest(rows, replay_manifest)
    evidence = dict(hp_evidence)
    frame_times = [
        int(row.get("gameTime") or 0)
        for row in working_rows
        if row.get("rfc461Schema") == "stats_update"
    ]
    timing = dict(evidence.get("timing") or {})
    try:
        evidence_tol = int(timing.get("toleranceMs"))
    except (TypeError, ValueError):
        raise DecryptError("HP evidence toleranceMs missing/invalid") from None
    if not 0 <= evidence_tol <= MAX_PRODUCT_TIME_TOLERANCE_MS:
        raise DecryptError(
            f"HP evidence tolerance must be 0..{MAX_PRODUCT_TIME_TOLERANCE_MS}ms"
        )
    evidence["samples"] = align_hp_samples_to_stats_frames(
        list(evidence.get("samples") or []),
        frame_times,
        max_delta_ms=MAX_PRODUCT_TIME_TOLERANCE_MS,
    )
    timing["toleranceMs"] = evidence_tol
    timing["unit"] = timing.get("unit") or "milliseconds"
    timing["clock"] = timing.get("clock") or "replay_game_time"
    timing["alignmentNote"] = (
        "Replication decrypt times snapped to nearest Replay API 1Hz frame "
        f"within {MAX_PRODUCT_TIME_TOLERANCE_MS}ms"
    )
    evidence["timing"] = timing
    (
        coverage,
        _game_info,
        pid_to_net,
        pid_to_identity,
        pid_to_roster_label,
        samples,
        evidence_tolerance,
    ) = _validate_product_sources(working_rows, replay_manifest, evidence)
    tolerance_ms = evidence_tolerance
    if time_tolerance_ms is not None:
        requested = int(time_tolerance_ms)
        if requested < 0 or requested > evidence_tolerance:
            raise DecryptError(
                "requested product tolerance must be non-negative and no wider "
                "than HP evidence tolerance"
            )
        tolerance_ms = requested

    stats = [row for row in working_rows if row.get("rfc461Schema") == "stats_update"]
    if not stats:
        raise DecryptError("product fusion requires stats_update frames")
    expected_pids = set(pid_to_net)
    for row in stats:
        participants = row.get("participants")
        if not isinstance(participants, list) or len(participants) != 10:
            raise DecryptError("every product stats frame must contain 10 participants")
        frame_pids = {int(participant.get("participantID")) for participant in participants}
        if frame_pids != expected_pids:
            raise DecryptError("stats participant identities do not match validated binding")
        for participant in participants:
            if "health" in participant or "healthMax" in participant:
                raise DecryptError("product fusion refuses pre-materialized HP source rows")
            if participant.get("healthSource") not in (
                "unavailable_replay_api",
                "unavailable",
                "unknown",
            ):
                raise DecryptError("product fusion source HP is not explicitly unknown")
            if any(field in participant for field in COMBAT_FIELDS):
                raise DecryptError(
                    "HP-only fusion refuses combat values without separate evidence"
                )
            if participant.get("combatStatsSource") not in (
                "unavailable_replay_api",
                "unavailable",
                "unknown",
            ) or participant.get("abilityRanksSource") not in (
                "unavailable_replay_api",
                "unavailable",
                "unknown",
            ):
                raise DecryptError(
                    "HP-only fusion requires combat and ability ranks to remain unknown"
                )

    def _apply_roster_labels(participant: Mapping[str, Any], pid: int) -> dict:
        fused = dict(participant)
        labels = pid_to_roster_label[pid]
        # Capture frames can scramble championName/playerName onto the wrong
        # participantID while HP still binds correctly by identity→pid→netId.
        fused["championName"] = labels["championName"]
        fused["playerName"] = labels["playerName"]
        fused["summonerName"] = labels["fullRiotId"]
        champ = fused.get("champion")
        if isinstance(champ, Mapping):
            nested = dict(champ)
            nested["raw"] = labels["championName"]
            nested["asset"] = labels["championName"]
            fused["champion"] = nested
        return fused

    out: List[dict] = []
    fused_frames = 0
    fused_rows = 0
    sample_times_used: set[int] = set()
    for original in working_rows:
        if original.get("rfc461Schema") == "rofl_coverage":
            out.append(dict(original))
            continue
        if original.get("rfc461Schema") == "game_info":
            gi = dict(original)
            gi_participants = []
            for participant in original.get("participants") or []:
                pid = int(participant["participantID"])
                gi_participants.append(_apply_roster_labels(participant, pid))
            gi["participants"] = gi_participants
            out.append(gi)
            continue
        if original.get("rfc461Schema") != "stats_update":
            out.append(dict(original))
            continue
        frame_time = int(original.get("gameTime") or 0)
        nearest_overall = min(
            samples,
            key=lambda sample: abs(int(sample["gameTimeMs"]) - frame_time),
        )
        aligned = sorted(
            (
                sample
                for sample in samples
                if int(sample["gameTimeMs"]) not in sample_times_used
                and abs(int(sample["gameTimeMs"]) - frame_time) <= tolerance_ms
            ),
            key=lambda sample: abs(int(sample["gameTimeMs"]) - frame_time),
        )
        nearest = aligned[0] if aligned else None
        sample_time = int((nearest or nearest_overall)["gameTimeMs"])
        delta_ms = abs(sample_time - frame_time)
        if nearest is None:
            unmatched = dict(original)
            unmatched["participants"] = [
                _apply_roster_labels(participant, int(participant["participantID"]))
                for participant in original.get("participants") or []
            ]
            unmatched["hpEvidence"] = {
                "source": TRUSTED_HEALTH_SOURCE,
                "coverage": "unknown_no_aligned_sample",
                "nearestSampleGameTimeMs": sample_time,
                "nearestSampleDeltaMs": delta_ms,
                "timeToleranceMs": tolerance_ms,
            }
            out.append(unmatched)
            continue
        sample_times_used.add(sample_time)
        participants = []
        for participant in original.get("participants") or []:
            pid = int(participant["participantID"])
            net_id = pid_to_net[pid]
            hp, hp_max = nearest["byNetId"][net_id]
            fused = _apply_roster_labels(participant, pid)
            fused["health"] = hp
            fused["healthMax"] = hp_max
            fused["healthSource"] = TRUSTED_HEALTH_SOURCE
            fused["healthCoverage"] = "known_at_sampled_frame"
            fused["healthSampleGameTimeMs"] = sample_time
            fused["healthSampleDeltaMs"] = delta_ms
            fused["healthNetId"] = net_id
            fused["healthIdentityKey"] = pid_to_identity[pid]
            fused["healthIdentityBinding"] = TRUSTED_BINDING_METHOD
            fused["healthMaxEvidence"] = "explicit_mMaxHP"
            fused["mMaxHPExplicit"] = True
            # HP proves neither combat stats nor ability ranks.
            fused["combatStatsSource"] = "unavailable_replay_api"
            fused["abilityRanksSource"] = "unavailable_replay_api"
            participants.append(fused)
            fused_rows += 1
        fused_frame = dict(original)
        fused_frame["participants"] = participants
        fused_frame["hpEvidence"] = {
            "source": TRUSTED_HEALTH_SOURCE,
            "coverage": "known_at_sampled_frame",
            "sampleGameTimeMs": sample_time,
            "sampleDeltaMs": delta_ms,
            "timeToleranceMs": tolerance_ms,
        }
        out.append(fused_frame)
        fused_frames += 1

    if fused_frames == 0:
        raise DecryptError("no canonical frame aligned to trusted HP samples")
    hp_coverage = "full" if fused_frames == len(stats) else "partial"
    evidence_sha = hashlib.sha256(
        json.dumps(
            evidence,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    product_provenance = dict(coverage.get("provenance") or {})
    product_provenance.update(
        {
            "hpCoverage": hp_coverage,
            "hpEvidenceMode": TRUSTED_EVIDENCE_MODE,
            "hpEvidenceSchema": TRUSTED_EVIDENCE_SCHEMA,
            "hpEvidenceSource": TRUSTED_HEALTH_SOURCE,
            "hpEvidenceSha256": evidence_sha,
            "hpEvidenceTimed": True,
            "hpStaticSnapshot": False,
            "hpFixtureEvidence": False,
            "hpCreateHeroOrderFallback": False,
            "hpIdentityBinding": TRUSTED_BINDING_METHOD,
            "hpRosterHash": evidence["rosterHash"],
            "hpTimeUnit": "milliseconds",
            "hpTimeClock": "replay_game_time",
            "hpTimeToleranceMs": tolerance_ms,
            "hpSampleCoverage": {
                "statsFrames": len(stats),
                "fusedFrames": fused_frames,
                "unmatchedFrames": len(stats) - fused_frames,
                "fusedParticipantRows": fused_rows,
                "sampleCount": len(samples),
                "sampleTimesUsed": len(sample_times_used),
            },
        }
    )
    notes = str(product_provenance.get("notes") or "").strip()
    product_provenance["notes"] = (
        (notes + " " if notes else "")
        + "HP uses timed same-match Replication samples with validated stable "
        "identity-to-netId binding and explicit mMaxHP. Combat stats and ability "
        "ranks remain unavailable."
    )
    product_coverage = dict(coverage)
    decoded = list(product_coverage.get("decoded") or [])
    if "health_rofl2_replication_timed_identity_bound" not in decoded:
        decoded.append("health_rofl2_replication_timed_identity_bound")
    product_coverage["decoded"] = decoded
    missing = list(product_coverage.get("missing") or [])
    if hp_coverage == "full":
        missing = [field for field in missing if field not in ("health", "healthMax")]
    product_coverage["missing"] = missing
    product_coverage["provenance"] = product_provenance
    if "notes" in product_coverage:
        product_coverage["notes"] = product_provenance["notes"]
    coverage_index = next(
        index
        for index, row in enumerate(out)
        if row.get("rfc461Schema") == "rofl_coverage"
    )
    out[coverage_index] = product_coverage
    summary = {
        "ok": True,
        "schema": TRUSTED_EVIDENCE_SCHEMA,
        "healthSource": TRUSTED_HEALTH_SOURCE,
        "coverage": hp_coverage,
        "statsFrames": len(stats),
        "fusedFrames": fused_frames,
        "unmatchedFrames": len(stats) - fused_frames,
        "sampleCount": len(samples),
        "sampleTimesUsed": len(sample_times_used),
        "timeToleranceMs": tolerance_ms,
        "identityBinding": TRUSTED_BINDING_METHOD,
        "rosterHash": evidence["rosterHash"],
        "evidenceSha256": evidence_sha,
        "combatStatsKnown": False,
        "abilityRanksKnown": False,
        "alignedEvidence": evidence,
    }
    return out, summary


def fuse(
    rows: List[dict],
    *,
    hp_by_pid: Optional[Dict[int, Tuple[float, float]]] = None,
    hp_samples: Optional[List[Tuple[float, Dict[int, Tuple[float, float]]]]] = None,
    time_tol_s: float = 2.0,
    static_snapshot: bool = False,
) -> List[dict]:
    out: List[dict] = []
    fused_frames = 0
    for row in rows:
        schema = row.get("rfc461Schema")
        if schema == "rofl_coverage":
            cov = dict(row)
            decoded = list(cov.get("decoded") or [])
            if "health_rofl2_replication_decrypt" not in decoded:
                decoded.append("health_rofl2_replication_decrypt")
            cov["decoded"] = decoded
            missing = [
                m
                for m in (cov.get("missing") or [])
                if m not in ("health", "healthMax")
            ]
            if "abilityRanks" not in missing:
                missing.append("abilityRanks")
            if "combatStats" not in missing:
                missing.append("combatStats")
            cov["missing"] = missing
            prov = dict(cov.get("provenance") or {})
            if static_snapshot:
                prov["hpCoverage"] = "snapshot_fused"
                prov["sourceKind"] = STATIC_SNAPSHOT_SOURCE_KIND
                prov["researchOnly"] = True
                prov["publicationBlocked"] = True
                prov["schemaProof"] = False
                notes = prov.get("notes") or ""
                prov["notes"] = (
                    (notes + " " if notes else "")
                    + "RESEARCH/DEMO ONLY: static HP snapshot fused onto every frame. "
                    "Not timed same-match product evidence; publicationBlocked."
                ).strip()
            else:
                prov["hpCoverage"] = "research_timed_fused"
                prov["sourceKind"] = TIMED_RESEARCH_SOURCE_KIND
                prov["researchOnly"] = True
                prov["publicationBlocked"] = True
                prov["schemaProof"] = False
                notes = prov.get("notes") or ""
                prov["notes"] = (
                    (notes + " " if notes else "")
                    + "RESEARCH/DEMO ONLY: timed HP uses CreateHero/order fallback "
                    "without validated stable identity-to-netId binding. "
                    "Ability ranks/combat remain unavailable; publicationBlocked."
                ).strip()
            cov["provenance"] = prov
            if "notes" in cov:
                cov["notes"] = prov["notes"]
            out.append(cov)
            continue

        if schema != "stats_update":
            out.append(row)
            continue

        game_time_ms = int(row.get("gameTime") or 0)
        time_s = game_time_ms / 1000.0
        frame_hp = hp_by_pid
        if hp_samples is not None:
            nearest = _nearest_hp(hp_samples, time_s, time_tol_s)
            if nearest is not None:
                frame_hp = nearest
            elif not static_snapshot:
                frame_hp = None

        if frame_hp is None:
            out.append(row)
            continue

        new_row = dict(row)
        parts = []
        for p in row.get("participants") or []:
            pid = int(p["participantID"])
            if pid not in frame_hp:
                parts.append(p)
                continue
            hp, hp_max = frame_hp[pid]
            q = dict(p)
            q["health"] = hp
            q["healthMax"] = hp_max
            q["healthSource"] = HEALTH_SOURCE
            q["abilityRanksSource"] = ABILITY_RANKS_SOURCE
            # Keep combat unavailable unless the upstream row already has
            # trustworthy combat fields from another source.
            if q.get("combatStatsSource") in (None, "unavailable_replay_api"):
                q["combatStatsSource"] = DEFAULT_COMBAT_STATS_SOURCE
            parts.append(q)
        new_row["participants"] = parts
        out.append(new_row)
        fused_frames += 1

    if fused_frames == 0:
        raise DecryptError("no stats_update frames received fused HP")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--jsonl", type=Path, required=True, help="Replay API rfc461 JSONL")
    ap.add_argument("--probe", type=Path, default=None, help="Successful decrypt probe JSON")
    ap.add_argument(
        "--events",
        type=Path,
        default=None,
        help="Optional maknee-shaped events JSON for time-varying HP samples",
    )
    ap.add_argument(
        "--time-tol-s",
        type=float,
        default=2.0,
        help="Max |decrypt_time - frame_time| when using --events samples",
    )
    ap.add_argument(
        "--static-snapshot",
        action="store_true",
        help=(
            "Apply probe hpSnapshot to every frame (research/demo only; "
            "marks publicationBlocked and cannot pass product gates)"
        ),
    )
    ap.add_argument(
        "--product",
        action="store_true",
        help="Require timed same-match stable-identity HP evidence",
    )
    ap.add_argument(
        "--replay-manifest",
        type=Path,
        default=None,
        help="ROFL ingest manifest for the Replay API canonical stream",
    )
    ap.add_argument(
        "--hp-evidence",
        type=Path,
        default=None,
        help=f"Trusted {TRUSTED_EVIDENCE_SCHEMA} timed HP evidence",
    )
    ap.add_argument(
        "--time-tol-ms",
        type=int,
        default=None,
        help="Optional narrower product alignment tolerance",
    )
    ap.add_argument("-o", "--output", type=Path, required=True)
    args = ap.parse_args()

    rows = _load_jsonl(args.jsonl)
    if args.product:
        if args.probe is not None or args.events is not None or args.static_snapshot:
            print(
                "product fusion does not accept legacy probe/events/static options",
                file=sys.stderr,
            )
            return 1
        if args.replay_manifest is None or args.hp_evidence is None:
            print(
                "product fusion requires --replay-manifest and --hp-evidence",
                file=sys.stderr,
            )
            return 1
        try:
            replay_manifest = json.loads(
                args.replay_manifest.read_text(encoding="utf-8")
            )
            hp_evidence = json.loads(args.hp_evidence.read_text(encoding="utf-8"))
            fused, summary = fuse_product(
                rows,
                replay_manifest=_object(replay_manifest, "replay manifest"),
                hp_evidence=_object(hp_evidence, "HP evidence"),
                time_tolerance_ms=args.time_tol_ms,
            )
        except (OSError, json.JSONDecodeError, DecryptError, ValueError) as exc:
            print(f"product fuse error: {exc}", file=sys.stderr)
            return 1
        aligned = summary.pop("alignedEvidence", None)
        if isinstance(aligned, dict):
            tmp = args.hp_evidence.with_name(
                f".{args.hp_evidence.name}.{os.getpid()}.tmp"
            )
            tmp.write_text(json.dumps(aligned, indent=2) + "\n", encoding="utf-8")
            os.replace(tmp, args.hp_evidence)
        _write_jsonl(args.output, fused)
        print(json.dumps({"output": str(args.output), **summary}, indent=2))
        return 0

    if (
        args.replay_manifest is not None
        or args.hp_evidence is not None
        or args.time_tol_ms is not None
    ):
        print(
            "--replay-manifest/--hp-evidence/--time-tol-ms require --product",
            file=sys.stderr,
        )
        return 1
    hp_by_pid = None
    hp_samples = None
    static = bool(args.static_snapshot)

    if args.events is not None:
        match = json.loads(args.events.read_text(encoding="utf-8"))
        events = match.get("events") or (match.get("match") or {}).get("events")
        if not isinstance(events, list):
            print("events file missing events[]", file=sys.stderr)
            return 1
        hp_samples = _hp_timeline_from_events(events)
        if not hp_samples:
            # fall back to single snapshot extraction
            snap = extract_hp_snapshot_from_events(events)
            if not snap.get("ok"):
                print("could not build HP samples from events", file=sys.stderr)
                return 1
            hp_by_pid = {
                int(h["participantID"]): (float(h["mHP"]), float(h["mMaxHP"]))
                for h in snap["heroes"]
            }
            static = True
    elif args.probe is not None:
        probe = json.loads(args.probe.read_text(encoding="utf-8"))
        if not probe.get("ok"):
            print(
                f"probe not ok: {probe.get('decryptStatus')} {probe.get('error')}",
                file=sys.stderr,
            )
            return 1
        hp_by_pid = _hp_by_participant_from_probe(probe)
        static = True if args.static_snapshot or hp_samples is None else static
    else:
        print("need --probe and/or --events", file=sys.stderr)
        return 1

    try:
        fused = fuse(
            rows,
            hp_by_pid=hp_by_pid,
            hp_samples=hp_samples,
            time_tol_s=args.time_tol_s,
            static_snapshot=static,
        )
    except DecryptError as e:
        print(f"fuse error: {e}", file=sys.stderr)
        return 1

    _write_jsonl(args.output, fused)
    print(f"wrote {args.output} lines={len(fused)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
