"""Shared identity→pid→netId binding helpers for product fuse scripts.

Product path (R23 P8 H2): fail-closed. No champion-name fallback, no
CreateHero-order invent, no presentation-order join. Research may opt into
allow_champion_fallback=True explicitly; productEligible still requires
createHeroOrderFallback=false.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple, Union

from rofl2_packet_decrypt_probe import DecryptError

PathLike = Union[str, Path]


def stable_identity_key(row: Mapping[str, Any], *, label: str) -> str:
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
        or row.get("healthIdentityKey")
        or ""
    ).strip()
    if full.startswith("puuid:") or full.startswith("riotid:"):
        return full if full.startswith("puuid:") else f"riotid:{full[7:].casefold()}"
    if full and "#" in full:
        return f"riotid:{full.casefold()}"
    raise DecryptError(f"{label} lacks stable PUUID/full Riot ID")


def assert_product_identity_binding(castspell_identity: Mapping[str, Any]) -> None:
    """Refuse product-ineligible identity artifacts (order/champ fallbacks)."""
    binding = castspell_identity.get("identityBinding")
    if not isinstance(binding, Mapping):
        raise DecryptError("product identity requires identityBinding object")
    if binding.get("createHeroOrderFallback") is True:
        raise DecryptError(
            "product identity refuse: createHeroOrderFallback=true "
            "(CreateHero / AE..B7 order is research-only)"
        )
    if castspell_identity.get("createHeroOrderFallback") is True:
        raise DecryptError(
            "product identity refuse: top-level createHeroOrderFallback=true"
        )
    if castspell_identity.get("productEligible") is True and (
        binding.get("createHeroOrderFallback") is not False
    ):
        raise DecryptError(
            "productEligible=true requires createHeroOrderFallback=false"
        )
    participants = list(binding.get("participants") or [])
    if len(participants) != 10:
        raise DecryptError(
            f"product identity requires 10 identityBinding.participants, "
            f"got {len(participants)}"
        )
    for index, raw in enumerate(participants):
        if not isinstance(raw, Mapping):
            raise DecryptError(
                f"identityBinding.participants[{index}] is not an object"
            )
        puuid = str(raw.get("puuid") or "").strip()
        full = str(raw.get("fullRiotId") or "").strip()
        if not puuid and (not full or "#" not in full):
            raise DecryptError(
                f"product identity participants[{index}] missing PUUID/fullRiotId "
                "(champ-only / order-only binds are not product-complete)"
            )


def assert_identity_match_context(
    castspell_identity: Mapping[str, Any],
    *,
    expected_series: str,
    expected_game_index: int = 1,
) -> None:
    """Refuse cross-match identity artifacts (R24 P8 H3 / H7).

    AE..B7 netId ranges often collide across pro ROFL dumps; series+gameIndex
    must match before product fuse treats a CastSpell bind as same-match truth.
    """
    series = str(
        castspell_identity.get("series")
        or castspell_identity.get("gridSeriesId")
        or ""
    ).strip()
    if not series:
        raise DecryptError(
            "product identity refuse: missing series/gridSeriesId "
            "(cross-match remap tripwire)"
        )
    if series != str(expected_series).strip():
        raise DecryptError(
            f"product identity refuse: series {series!r} != expected "
            f"{expected_series!r} (never remap another match's CastSpell bind)"
        )
    raw_gi = castspell_identity.get("gameIndex")
    if raw_gi is None:
        raw_gi = castspell_identity.get("game_index")
    if raw_gi is None:
        raise DecryptError(
            "product identity refuse: missing gameIndex (cross-match remap tripwire)"
        )
    try:
        game_index = int(raw_gi)
    except (TypeError, ValueError) as exc:
        raise DecryptError(
            f"product identity refuse: invalid gameIndex {raw_gi!r}"
        ) from exc
    if game_index != int(expected_game_index):
        raise DecryptError(
            f"product identity refuse: gameIndex {game_index} != expected "
            f"{int(expected_game_index)} (never remap another match's CastSpell bind)"
        )


def assert_castspell_roster_champion_agree(
    castspell_identity: Mapping[str, Any],
    roster_rows: Sequence[Mapping[str, Any]],
) -> None:
    """Refuse PUUID joins where CastSpell champion ≠ same-match slim roster champ.

    Catches partial remaps that keep holdout PUUIDs but graft another match's
    winners/netId→champ table (shared GEN/T1 PUUID overlap across series games).
    """
    binding = castspell_identity.get("identityBinding")
    if not isinstance(binding, Mapping):
        raise DecryptError("castspell identityBinding missing for champ-agree audit")
    by_puuid: Dict[str, str] = {}
    for index, raw in enumerate(roster_rows):
        if not isinstance(raw, Mapping):
            raise DecryptError(f"roster_rows[{index}] is not an object")
        puuid = str(raw.get("puuid") or raw.get("PUUID") or "").strip()
        champ = str(
            raw.get("championName") or raw.get("champion_name") or ""
        ).strip()
        if not puuid or not champ:
            raise DecryptError(
                f"roster_rows[{index}] missing puuid/championName for champ-agree"
            )
        if puuid in by_puuid:
            raise DecryptError(f"duplicate roster puuid {puuid!r}")
        by_puuid[puuid] = champ
    mismatches: List[str] = []
    for index, raw in enumerate(binding.get("participants") or []):
        if not isinstance(raw, Mapping):
            raise DecryptError(f"participants[{index}] is not an object")
        puuid = str(raw.get("puuid") or "").strip()
        champ = str(raw.get("champion") or raw.get("championName") or "").strip()
        roster_champ = by_puuid.get(puuid)
        if roster_champ is None:
            raise DecryptError(
                f"participants[{index}] puuid={puuid!r} missing from slim roster "
                "(cross-match / incomplete roster)"
            )
        if roster_champ != champ:
            mismatches.append(
                f"{puuid[:8]}… castspell={champ!r} roster={roster_champ!r}"
            )
    if mismatches:
        raise DecryptError(
            "product identity refuse: CastSpell champion ≠ slim roster champion "
            f"for PUUID join ({'; '.join(mismatches[:3])})"
        )


def identity_binding_rows(
    castspell_identity: Mapping[str, Any],
    *,
    allow_champ_only: bool = False,
) -> Dict[str, Dict[str, Any]]:
    """Map stable identity → {netId, championName, fullRiotId, playerName}."""
    binding = castspell_identity.get("identityBinding")
    participants = []
    if isinstance(binding, Mapping):
        participants = list(binding.get("participants") or [])
    if len(participants) != 10:
        # Fall back to winners alone — labels incomplete (research only).
        if not allow_champ_only:
            raise DecryptError(
                "castspell identity binding incomplete (need 10 participants); "
                "champ-only winners fallback disabled for product"
            )
        winners = castspell_identity.get("winners") or {}
        if len(winners) != 10:
            raise DecryptError("castspell identity binding/winners incomplete (need 10)")
        out: Dict[str, Dict[str, Any]] = {}
        for raw_net, champ in winners.items():
            try:
                net_id = int(raw_net, 16) if isinstance(raw_net, str) else int(raw_net)
            except (TypeError, ValueError) as exc:
                raise DecryptError(f"invalid castspell winner netId {raw_net!r}") from exc
            # Without identity rows we can only key by synthetic champ key.
            out[f"champ:{champ}"] = {
                "netId": net_id,
                "championName": str(champ),
                "fullRiotId": "",
                "playerName": "",
            }
        return out

    out = {}
    for index, raw in enumerate(participants):
        if not isinstance(raw, Mapping):
            raise DecryptError(f"identityBinding.participants[{index}] is not an object")
        try:
            net_id = int(raw.get("netId"))
        except (TypeError, ValueError) as exc:
            raise DecryptError(
                f"identityBinding.participants[{index}] has invalid netId"
            ) from exc
        champ = str(raw.get("champion") or "").strip()
        full = str(raw.get("fullRiotId") or "").strip()
        if not champ or not full or "#" not in full:
            raise DecryptError(
                f"identityBinding.participants[{index}] missing champion/fullRiotId"
            )
        key = stable_identity_key(raw, label=f"identityBinding.participants[{index}]")
        if key in out:
            raise DecryptError(f"duplicate identity binding key {key!r}")
        out[key] = {
            "netId": net_id,
            "championName": champ,
            "fullRiotId": full,
            "playerName": full.split("#", 1)[0],
        }
    if len(out) != 10:
        raise DecryptError("castspell identityBinding must cover 10 identities")
    return out


def load_slim_roster_rows(sqlite_path: PathLike) -> List[Dict[str, Any]]:
    """Load roster(puuid, full_riot_id, participant_id, champion) from slim SQLite."""
    path = Path(sqlite_path)
    if not path.is_file():
        raise DecryptError(f"slim sqlite roster missing: {path}")
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        cols = {
            str(r[1]).casefold()
            for r in con.execute("PRAGMA table_info(roster)").fetchall()
        }
        need = {"participant_id", "puuid", "full_riot_id", "champion_name"}
        if not need.issubset(cols):
            raise DecryptError(
                f"slim roster missing columns {sorted(need - cols)} at {path}"
            )
        rows = con.execute(
            "SELECT participant_id, puuid, full_riot_id, champion_name, "
            "COALESCE(team_id, 0), COALESCE(summoner_name, '') "
            "FROM roster ORDER BY participant_id"
        ).fetchall()
    finally:
        con.close()
    out: List[Dict[str, Any]] = []
    for pid, puuid, full, champ, team, summoner in rows:
        out.append(
            {
                "participantID": int(pid),
                "puuid": str(puuid or "").strip(),
                "fullRiotId": str(full or "").strip(),
                "championName": str(champ or "").strip(),
                "teamID": int(team) if team is not None else 0,
                "summonerName": str(summoner or full or "").strip(),
            }
        )
    if len(out) != 10:
        raise DecryptError(f"slim roster must have exactly 10 rows, got {len(out)}")
    return out


def stamp_participant_ids_via_puuid_join(
    castspell_identity: Mapping[str, Any],
    roster_rows: Sequence[Mapping[str, Any]],
    *,
    join_key: str = "puuid",
) -> Dict[str, Any]:
    """Stamp identityBinding.participants[].participantID via slim-roster join.

    Product path: join_key 'puuid' (preferred) or 'fullRiotId'.
    Never reads createHeroEvents / AE..B7 order. Refuses missing/duplicate keys.
    """
    if join_key not in ("puuid", "fullRiotId"):
        raise DecryptError(f"unsupported join_key {join_key!r}")

    binding = castspell_identity.get("identityBinding")
    if not isinstance(binding, Mapping):
        raise DecryptError("castspell identityBinding missing")
    if binding.get("createHeroOrderFallback") is True:
        raise DecryptError("refuse stamp: createHeroOrderFallback=true")
    participants = list(binding.get("participants") or [])
    if len(participants) != 10:
        raise DecryptError(
            f"identityBinding.participants need 10, got {len(participants)}"
        )

    # Index roster by stable key — presentation order ignored.
    by_key: Dict[str, Mapping[str, Any]] = {}
    for index, raw in enumerate(roster_rows):
        if not isinstance(raw, Mapping):
            raise DecryptError(f"roster_rows[{index}] is not an object")
        try:
            pid = int(raw.get("participantID") or raw.get("participant_id"))
        except (TypeError, ValueError) as exc:
            raise DecryptError(f"roster_rows[{index}] invalid participantID") from exc
        if join_key == "puuid":
            key = str(raw.get("puuid") or raw.get("PUUID") or "").strip()
            if not key:
                raise DecryptError(f"roster_rows[{index}] missing puuid")
            norm = key
        else:
            key = str(
                raw.get("fullRiotId")
                or raw.get("full_riot_id")
                or raw.get("summonerName")
                or ""
            ).strip()
            if not key or "#" not in key:
                raise DecryptError(f"roster_rows[{index}] missing fullRiotId")
            norm = key.casefold()
        if norm in by_key:
            raise DecryptError(f"duplicate roster {join_key} {key!r}")
        by_key[norm] = {**dict(raw), "participantID": pid}

    if len(by_key) != 10:
        raise DecryptError(f"roster {join_key} index must be 10 unique, got {len(by_key)}")

    stamped: List[Dict[str, Any]] = []
    seen_pids: set[int] = set()
    seen_nets: set[int] = set()
    for index, raw in enumerate(participants):
        if not isinstance(raw, Mapping):
            raise DecryptError(f"participants[{index}] is not an object")
        try:
            net_id = int(raw.get("netId"))
        except (TypeError, ValueError) as exc:
            raise DecryptError(f"participants[{index}] invalid netId") from exc
        if net_id in seen_nets:
            raise DecryptError(f"duplicate netId {net_id}")
        seen_nets.add(net_id)

        if join_key == "puuid":
            key = str(raw.get("puuid") or "").strip()
            if not key:
                raise DecryptError(f"participants[{index}] missing puuid")
            match = by_key.get(key)
        else:
            key = str(raw.get("fullRiotId") or "").strip()
            if not key or "#" not in key:
                raise DecryptError(f"participants[{index}] missing fullRiotId")
            match = by_key.get(key.casefold())

        if match is None:
            raise DecryptError(
                f"participants[{index}] {join_key}={key!r} missing from slim roster"
            )
        # R24: CastSpell champ must equal same-match slim roster champ for this key.
        roster_champ = str(
            match.get("championName") or match.get("champion_name") or ""
        ).strip()
        bind_champ = str(raw.get("champion") or raw.get("championName") or "").strip()
        if roster_champ and bind_champ and roster_champ != bind_champ:
            raise DecryptError(
                f"participants[{index}] {join_key}={key!r} CastSpell champion "
                f"{bind_champ!r} ≠ slim roster {roster_champ!r} "
                "(refuse cross-match / fixture remap)"
            )
        pid = int(match["participantID"])
        if pid in seen_pids:
            raise DecryptError(f"duplicate stamped participantID {pid}")
        seen_pids.add(pid)

        row = dict(raw)
        row["participantID"] = pid
        row["pidStampMethod"] = f"slim_roster_{join_key}_join"
        stamped.append(row)

    if len(seen_pids) != 10 or min(seen_pids) != 1 or max(seen_pids) != 10:
        raise DecryptError(
            f"stamped participantIDs must be bijection 1..10, got {sorted(seen_pids)}"
        )

    out = dict(castspell_identity)
    new_binding = dict(binding)
    new_binding["participants"] = stamped
    new_binding["pidStampMethod"] = f"slim_roster_{join_key}_join"
    new_binding["pidStampComplete"] = True
    new_binding["createHeroOrderFallback"] = False
    new_binding["complete"] = True
    new_binding["note"] = (
        "participantID stamped via same-match slim roster "
        f"{join_key} join — never CreateHero order / AE..B7 invent"
    )
    out["identityBinding"] = new_binding
    out["createHeroOrderFallback"] = False
    out["pidStampMethod"] = f"slim_roster_{join_key}_join"
    out["pidStampComplete"] = True
    out["identityPidComplete"] = True
    # Still not calculatorReady — research gate flags stay honest.
    out["productEligible"] = False
    out["calculatorReady"] = False
    out["gateEligible"] = False
    out["note"] = (
        "R22/R23/R24 P8: participantID via slim-roster PUUID/fullRiotId join; "
        "CastSpell↔roster champ agree; createHeroOrderFallback=false; "
        "productEligible remains false until HP/combat/ranks"
    )
    assert_castspell_roster_champion_agree(out, roster_rows)
    return out


def game_info_rows_from_slim_roster(
    roster_rows: Sequence[Mapping[str, Any]],
    *,
    game_id: int = 0,
) -> List[Dict[str, Any]]:
    """Build a minimal rfc461 game_info row list from slim roster (identity keys only)."""
    participants = []
    for raw in roster_rows:
        full = str(raw.get("fullRiotId") or raw.get("full_riot_id") or "").strip()
        participants.append(
            {
                "participantID": int(raw.get("participantID") or raw.get("participant_id")),
                "teamID": int(raw.get("teamID") or raw.get("team_id") or 0),
                "championName": str(
                    raw.get("championName") or raw.get("champion_name") or ""
                ),
                "playerName": full.split("#", 1)[0] if full else "",
                "summonerName": full,
                "puuid": str(raw.get("puuid") or "").strip(),
                "role": "NONE",
            }
        )
    return [
        {
            "rfc461Schema": "game_info",
            "gameID": int(game_id),
            "participants": participants,
        }
    ]


def order_join_net_to_champ(
    castspell_identity: Mapping[str, Any],
    roster_rows: Sequence[Mapping[str, Any]],
) -> Dict[int, str]:
    """ANTI-PATTERN research helper: bind by presentation index / AE..B7 order.

    Pair sorted CastSpell netIds with roster rows in the order provided.
    Used only to prove scramble under presentation permutation — never product.
    """
    binding = castspell_identity.get("identityBinding")
    if not isinstance(binding, Mapping):
        raise DecryptError("identityBinding missing for order-join audit")
    parts = list(binding.get("participants") or [])
    if len(parts) != 10 or len(roster_rows) != 10:
        raise DecryptError("order-join audit requires 10 participants and 10 roster rows")
    nets = sorted(int(p["netId"]) for p in parts)
    out: Dict[int, str] = {}
    for net_id, raw in zip(nets, roster_rows):
        champ = str(raw.get("championName") or raw.get("champion_name") or "").strip()
        out[net_id] = champ
    return out


def identity_join_net_to_champ(
    castspell_identity: Mapping[str, Any],
    roster_rows: Sequence[Mapping[str, Any]],
) -> Dict[int, str]:
    """Product-shaped join: PUUID (else fullRiotId) → netId → champion from bind."""
    stamped = stamp_participant_ids_via_puuid_join(
        castspell_identity, roster_rows, join_key="puuid"
    )
    return {
        int(p["netId"]): str(p["champion"])
        for p in stamped["identityBinding"]["participants"]
    }


def winners_net_to_champ(castspell_identity: Mapping[str, Any]) -> Dict[int, str]:
    winners = castspell_identity.get("winners") or {}
    out: Dict[int, str] = {}
    for raw_net, champ in winners.items():
        net_id = int(raw_net, 16) if isinstance(raw_net, str) else int(raw_net)
        out[net_id] = str(champ)
    if len(out) != 10:
        # Fall back to identityBinding participants.
        binding = castspell_identity.get("identityBinding") or {}
        for raw in binding.get("participants") or []:
            out[int(raw["netId"])] = str(raw["champion"])
    if len(out) != 10:
        raise DecryptError("winners/net→champ incomplete")
    return out


def pid_bindings_from_game_info(
    rows: Sequence[Mapping[str, Any]],
    castspell_identity: Mapping[str, Any],
    *,
    allow_champion_fallback: bool = False,
    product_strict: bool = True,
    expected_series: Optional[str] = None,
    expected_game_index: int = 1,
    roster_rows: Optional[Sequence[Mapping[str, Any]]] = None,
) -> Tuple[Dict[int, int], Dict[int, Dict[str, str]], Dict[int, str]]:
    """Build pid→netId and pid→roster labels from game_info + CastSpell binding.

    Never trusts per-frame championName strings (capture can scramble labels).
    When identityBinding.participants already carry participantID (PUUID stamp),
    those pids must agree with game_info PUUID join — refuse order invent.

    Product default (R23 P8 H2): allow_champion_fallback=False, product_strict=True.
    Research escape hatch: allow_champion_fallback=True, product_strict=False.
    R24 P8 H3: when product_strict + expected_series, refuse cross-match series/gameIndex;
    when roster_rows provided, refuse CastSpell↔roster champ disagree.
    """
    if product_strict:
        assert_product_identity_binding(castspell_identity)
        allow_champion_fallback = False
        if expected_series is not None:
            assert_identity_match_context(
                castspell_identity,
                expected_series=expected_series,
                expected_game_index=expected_game_index,
            )
        if roster_rows is not None:
            assert_castspell_roster_champion_agree(castspell_identity, roster_rows)

    game_info = next(
        (row for row in rows if row.get("rfc461Schema") == "game_info"),
        None,
    )
    if game_info is None:
        raise DecryptError("product fuse requires game_info for identity→pid bind")
    binding_by_identity = identity_binding_rows(
        castspell_identity, allow_champ_only=allow_champion_fallback
    )
    # Optional: stamped participantID on CastSpell rows (R22 PUUID join).
    stamped_pid_by_identity: Dict[str, int] = {}
    binding = castspell_identity.get("identityBinding")
    if isinstance(binding, Mapping):
        for index, raw in enumerate(binding.get("participants") or []):
            if not isinstance(raw, Mapping) or raw.get("participantID") is None:
                continue
            try:
                key = stable_identity_key(raw, label=f"stamped participants[{index}]")
                stamped_pid_by_identity[key] = int(raw["participantID"])
            except (DecryptError, TypeError, ValueError):
                continue

    # Research-only: champ index for optional fallback.
    by_champ = {
        str(v["championName"]).casefold(): v
        for v in binding_by_identity.values()
        if v.get("championName")
    }

    pid_to_net: Dict[int, int] = {}
    pid_to_labels: Dict[int, Dict[str, str]] = {}
    pid_to_identity: Dict[int, str] = {}
    for index, raw in enumerate(game_info.get("participants") or []):
        if not isinstance(raw, Mapping):
            raise DecryptError(f"game_info participants[{index}] is not an object")
        try:
            pid = int(raw.get("participantID"))
        except (TypeError, ValueError) as exc:
            raise DecryptError(
                f"game_info participants[{index}] has invalid participantID"
            ) from exc
        try:
            key = stable_identity_key(raw, label=f"game_info participants[{index}]")
        except DecryptError:
            # Nested sourceIdentity from repaired manifests.
            source = raw.get("sourceIdentity")
            if isinstance(source, Mapping) and source.get("key"):
                key = str(source["key"])
            else:
                raise
        bound = binding_by_identity.get(key)
        if bound is None:
            # Try riotid/puuid alternate forms already in binding.
            for bkey, bval in binding_by_identity.items():
                if bkey.casefold() == key.casefold():
                    bound = bval
                    key = bkey
                    break
        used_champ_fallback = False
        if bound is None:
            if not allow_champion_fallback:
                raise DecryptError(
                    f"game_info pid={pid} identity {key!r} missing from CastSpell "
                    "binding (champion fallback disabled)"
                )
            champ = str(
                raw.get("championName")
                or (
                    (raw.get("champion") or {}).get("asset")
                    if isinstance(raw.get("champion"), Mapping)
                    else ""
                )
                or ""
            ).strip()
            aliases = {"Wukong": "MonkeyKing", "LeBlanc": "Leblanc"}
            champ = aliases.get(champ, champ)
            bound = by_champ.get(champ.casefold())
            used_champ_fallback = bound is not None
        if bound is None:
            raise DecryptError(
                f"game_info pid={pid} identity {key!r} missing from CastSpell binding"
            )
        stamped_pid = stamped_pid_by_identity.get(key)
        if stamped_pid is not None and stamped_pid != pid:
            raise DecryptError(
                f"game_info pid={pid} disagrees with PUUID-stamped participantID "
                f"{stamped_pid} for {key!r}"
            )
        if used_champ_fallback and stamped_pid is not None:
            raise DecryptError(
                f"refuse champ fallback when PUUID stamp present for {key!r}"
            )
        if pid in pid_to_net:
            raise DecryptError(f"duplicate game_info participantID {pid}")
        pid_to_net[pid] = int(bound["netId"])
        pid_to_labels[pid] = {
            "championName": str(bound["championName"]),
            "playerName": str(bound["playerName"]),
            "fullRiotId": str(bound["fullRiotId"]),
        }
        pid_to_identity[pid] = key
    if len(pid_to_net) != 10:
        raise DecryptError("game_info must bind exactly 10 participantIDs")
    return pid_to_net, pid_to_labels, pid_to_identity


def apply_roster_labels(
    participant: Mapping[str, Any],
    labels: Mapping[str, str],
) -> dict:
    fused = dict(participant)
    fused["championName"] = labels["championName"]
    fused["playerName"] = labels["playerName"]
    if labels.get("fullRiotId"):
        fused["summonerName"] = labels["fullRiotId"]
    champ = fused.get("champion")
    if isinstance(champ, Mapping):
        nested = dict(champ)
        nested["raw"] = labels["championName"]
        nested["asset"] = labels["championName"]
        fused["champion"] = nested
    return fused


def resolve_participant_net_id(
    participant: Mapping[str, Any],
    *,
    pid: int,
    pid_to_net: Mapping[int, int],
) -> int:
    """Prefer HP-fuse healthNetId when present; else identity→pid bind."""
    expected = int(pid_to_net[pid])
    raw = participant.get("healthNetId")
    if raw is None:
        return expected
    try:
        health_net = int(raw)
    except (TypeError, ValueError) as exc:
        raise DecryptError(f"pid={pid} has invalid healthNetId") from exc
    if health_net != expected:
        raise DecryptError(
            f"pid={pid} healthNetId {health_net:#x} disagrees with identity bind "
            f"{expected:#x}"
        )
    return expected
