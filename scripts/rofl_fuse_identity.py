"""Shared identity→pid→netId binding helpers for product fuse scripts."""
from __future__ import annotations

from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

from rofl2_packet_decrypt_probe import DecryptError


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


def identity_binding_rows(
    castspell_identity: Mapping[str, Any],
) -> Dict[str, Dict[str, Any]]:
    """Map stable identity → {netId, championName, fullRiotId, playerName}."""
    binding = castspell_identity.get("identityBinding")
    participants = []
    if isinstance(binding, Mapping):
        participants = list(binding.get("participants") or [])
    if len(participants) != 10:
        # Fall back to winners alone — labels incomplete.
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


def pid_bindings_from_game_info(
    rows: Sequence[Mapping[str, Any]],
    castspell_identity: Mapping[str, Any],
) -> Tuple[Dict[int, int], Dict[int, Dict[str, str]], Dict[int, str]]:
    """Build pid→netId and pid→roster labels from game_info + CastSpell binding.

    Never trusts per-frame championName strings (capture can scramble labels).
    """
    game_info = next(
        (row for row in rows if row.get("rfc461Schema") == "game_info"),
        None,
    )
    if game_info is None:
        raise DecryptError("product fuse requires game_info for identity→pid bind")
    binding_by_identity = identity_binding_rows(castspell_identity)
    # If only champ: keys (winners fallback), also index by champion for join.
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
        if bound is None:
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
        if bound is None:
            raise DecryptError(
                f"game_info pid={pid} identity {key!r} missing from CastSpell binding"
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
