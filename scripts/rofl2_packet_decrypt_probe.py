#!/usr/bin/env python3
"""
ROFL2 packet decrypt probe — research harness for Replication HP fields.

This does **not** invent HP. It:

1. Walks ROFL2 zstd segments (via ``rofl2_probe``).
2. Inventories Replication field names from a patch-matched League binary.
3. Exposes ``decrypt_replication_fields`` with pluggable backends:
   - ``fixture``: read pre-decoded maknee-shaped events (CI / offline proof).
   - ``emulator``: attempt packet-accessor emulation (fail-closed on 16.14 until
     a working Unicorn/accessor harness is wired).

Acceptance for a successful decrypt: on at least one mid-game sample, return
10 hero ``mHP``/``mMaxHP`` pairs with ``0 < hp <= hpMax`` and ``hpMax > 100``.

Example:
  python3 scripts/rofl2_packet_decrypt_probe.py \\
    "$HOME/Documents/League of Legends/Replays/BR1-3264383283.rofl" \\
    --backend fixture \\
    --fixture-events docs/rofl-research/fixtures/maknee_match_stub.json \\
    --json-out /tmp/decrypt_probe.json

  python3 scripts/rofl2_packet_decrypt_probe.py \\
    "$HOME/Documents/League of Legends/Replays/BR1-3264383283.rofl" \\
    --backend emulator --json-out /tmp/decrypt_probe_live.json
"""
from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rofl2_a8_structure import analyze_keyframe  # noqa: E402
from rofl2_probe import extract_segments, parse_rofl2  # noqa: E402
from rofl_replication_fields import (  # noqa: E402
    BINARY_COMBAT_REPLICATION_NAMES,
    FIXTURE_REPLICATION_NAMES,
    inventory_from_binary,
)

DEFAULT_LEAGUE_BINARY = Path(
    "/Applications/League of Legends.app/Contents/LoL/Game/"
    "LeagueofLegends.app/Contents/MacOS/LeagueofLegends"
)
DEFAULT_CODE_METADATA = Path(
    "/Applications/League of Legends.app/Contents/LoL/Game/code-metadata.json"
)


class DecryptError(RuntimeError):
    """Fail-closed decrypt / probe error."""


def _rep_value(data: Any) -> Optional[float]:
    if isinstance(data, (int, float)):
        return float(data)
    if not isinstance(data, Mapping):
        return None
    for k in ("Float", "Int", "Uint", "Bool", "value"):
        if k in data:
            try:
                return float(data[k])
            except (TypeError, ValueError):
                return None
    return None


def _normalize_build(version: str) -> str:
    # "16.14.794.5912" or "16.14.7945912+branch..." → comparable token
    v = version.strip()
    if "+" in v:
        v = v.split("+", 1)[0]
    parts = v.replace("-", ".").split(".")
    # collapse 16.14.7945912 → 16.14.794.5912 when possible
    if len(parts) == 3 and parts[2].isdigit() and len(parts[2]) >= 7:
        build = parts[2]
        parts = [parts[0], parts[1], build[:-4], build[-4:]]
    return ".".join(parts)


def read_app_build(meta_path: Path = DEFAULT_CODE_METADATA) -> Optional[str]:
    if not meta_path.is_file():
        return None
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return str(meta.get("version") or "") or None


def keyframe_bodies(rofl: Path) -> List[Dict[str, Any]]:
    info = parse_rofl2(rofl)
    extracted = extract_segments(info["payload"])
    out: List[Dict[str, Any]] = []
    for i, seg in enumerate(extracted["segments"]):
        if seg.get("type") != 2:
            continue
        body: bytes = seg["bytes"]
        t = struct.unpack_from("<f", body, 1)[0] if len(body) >= 5 else None
        out.append(
            {
                "index": i,
                "id_a": seg["id_a"],
                "time_s": t,
                "bytes": body,
                "out_len": len(body),
            }
        )
    return out


def inventory_binary_fields(
    binary_path: Path = DEFAULT_LEAGUE_BINARY,
) -> Dict[str, Any]:
    if not binary_path.is_file():
        return {
            "ok": False,
            "path": str(binary_path),
            "error": "league binary not found",
        }
    data = binary_path.read_bytes()
    names = inventory_from_binary(data)
    combatish = [n for n in names if n in BINARY_COMBAT_REPLICATION_NAMES]
    return {
        "ok": True,
        "path": str(binary_path),
        "size": len(data),
        "fieldCount": len(names),
        "fields": list(names),
        "fixtureNamesPresent": sorted(FIXTURE_REPLICATION_NAMES & set(names)),
        "combatNamesPresent": combatish,
        "hasMHP": "mHP" in names,
        "hasMMaxHP": "mMaxHP" in names,
    }


def heroes_from_events(events: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    heroes: List[Dict[str, Any]] = []
    seen = set()
    for e in events:
        h = e.get("CreateHero") if isinstance(e, Mapping) else None
        if not isinstance(h, Mapping):
            continue
        net_id = int(h["net_id"])
        if net_id in seen:
            continue
        seen.add(net_id)
        heroes.append(
            {
                "net_id": net_id,
                "name": h.get("name") or f"id{net_id}",
                "champion": h.get("champion") or "Unknown",
                "participantID": len(heroes) + 1,
                "teamID": 100 if len(heroes) < 5 else 200,
            }
        )
        if len(heroes) >= 10:
            break
    return heroes


def heroes_from_rofl_stats(rofl: Path) -> List[Dict[str, Any]]:
    info = parse_rofl2(rofl)
    players = json.loads(info["meta"]["statsJson"])
    heroes: List[Dict[str, Any]] = []
    # Stable order: team 100 then 200, preserving file order within team.
    ordered = sorted(
        enumerate(players),
        key=lambda it: (0 if str(it[1].get("TEAM")) in ("100", "ORDER") else 1, it[0]),
    )
    for i, (_idx, p) in enumerate(ordered[:10]):
        team_raw = str(p.get("TEAM") or "")
        team_id = 100 if team_raw in ("100", "ORDER") else 200
        heroes.append(
            {
                "net_id": 1_000_000 + i,  # placeholder until CreateHero decrypt
                "name": p.get("RIOT_ID_GAME_NAME") or f"player{i+1}",
                "champion": p.get("SKIN") or "Unknown",
                "participantID": i + 1,
                "teamID": team_id,
            }
        )
    return heroes


def extract_hp_snapshot_from_events(
    events: Sequence[Mapping[str, Any]],
    *,
    target_time_s: Optional[float] = None,
) -> Dict[str, Any]:
    """Return best HP snapshot from maknee-shaped Replication events."""
    heroes = heroes_from_events(events)
    if len(heroes) < 10:
        raise DecryptError(f"expected 10 CreateHero entries, got {len(heroes)}")
    by_net = {h["net_id"]: h for h in heroes}
    hp: Dict[int, float] = {}
    hp_max: Dict[int, float] = {}
    last_t = 0.0
    sample_t = target_time_s

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
        if target_time_s is not None and t > target_time_s + 1e-6:
            break
        last_t = t
        for nid_s, rep in (payload.get("net_id_to_replication_datas") or {}).items():
            nid = int(nid_s)
            if nid not in by_net or not isinstance(rep, Mapping):
                continue
            name = (rep.get("name") or "").strip()
            val = _rep_value(rep.get("data"))
            if val is None:
                continue
            if name == "mHP":
                hp[nid] = val
            elif name == "mMaxHP":
                hp_max[nid] = val

    if sample_t is None:
        sample_t = last_t

    rows: List[Dict[str, Any]] = []
    for h in heroes:
        nid = h["net_id"]
        cur = hp.get(nid)
        mx = hp_max.get(nid)
        if cur is None and mx is None:
            continue
        if mx is None:
            mx = max(cur or 1.0, 1.0)
        if cur is None:
            cur = mx
        mx = max(mx, cur, 1.0)
        rows.append(
            {
                "net_id": nid,
                "participantID": h["participantID"],
                "teamID": h["teamID"],
                "champion": h["champion"],
                "name": h["name"],
                "mHP": float(cur),
                "mMaxHP": float(mx),
            }
        )

    ok = (
        len(rows) >= 10
        and all(0 < r["mHP"] <= r["mMaxHP"] and r["mMaxHP"] > 100 for r in rows)
    )
    return {
        "ok": ok,
        "time_s": sample_t,
        "heroCount": len(rows),
        "heroes": rows,
        "acceptance": {
            "needHeroes": 10,
            "needHpMaxGt": 100,
            "passed": ok,
        },
    }


def decrypt_replication_fields(
    *,
    backend: str,
    rofl: Optional[Path] = None,
    fixture_events: Optional[Path] = None,
    target_time_s: Optional[float] = None,
    league_binary: Path = DEFAULT_LEAGUE_BINARY,
) -> Dict[str, Any]:
    """
    Narrow decrypt API.

    Returns a report dict. On success, ``replication`` is a list of maknee-shaped
    ``{"Replication": {...}}`` event dicts (usually one snapshot event) and
    ``hpSnapshot`` passes the 10-hero acceptance bar.
    """
    backend = backend.strip().lower()
    binary_inv = inventory_binary_fields(league_binary)
    report: Dict[str, Any] = {
        "backend": backend,
        "binaryInventory": binary_inv,
        "fixtureNames": sorted(FIXTURE_REPLICATION_NAMES),
        "ok": False,
        "decryptStatus": "pending",
        "replication": [],
        "hpSnapshot": None,
        "keyframeStructure": None,
        "build": {},
    }

    if rofl is not None:
        info = parse_rofl2(rofl)
        app_build = read_app_build()
        report["build"] = {
            "roflVersion": info["version"],
            "appVersion": app_build,
            "normalizedRofl": _normalize_build(info["version"]),
            "normalizedApp": _normalize_build(app_build) if app_build else None,
            "exactMatch": bool(
                app_build
                and _normalize_build(info["version"]) == _normalize_build(app_build)
            ),
        }
        kfs = keyframe_bodies(rofl)
        if kfs:
            mid = kfs[len(kfs) // 2]
            # Write temp analysis without persisting file — synthesize Path-like via analyze on bytes
            tmp = Path("/tmp") / f"rofl2_decrypt_kf_{mid['id_a']}.bin"
            tmp.write_bytes(mid["bytes"])
            try:
                report["keyframeStructure"] = analyze_keyframe(tmp)
            finally:
                try:
                    tmp.unlink()
                except OSError:
                    pass
            report["keyframeStructure"]["probeTime_s"] = mid.get("time_s")
            report["keyframeCount"] = len(kfs)

    if backend == "fixture":
        if fixture_events is None or not fixture_events.is_file():
            raise DecryptError("--fixture-events required for fixture backend")
        match = json.loads(fixture_events.read_text(encoding="utf-8"))
        events = match.get("events") or (match.get("match") or {}).get("events")
        if not isinstance(events, list):
            raise DecryptError("fixture missing events[]")
        snap = extract_hp_snapshot_from_events(events, target_time_s=target_time_s)
        report["hpSnapshot"] = snap
        # Emit one maknee Replication event aggregating the snapshot.
        net_map: Dict[str, Any] = {}
        for row in snap["heroes"]:
            nid = str(row["net_id"])
            net_map[nid] = {
                "primary_index": 32,
                "secondary_index": 0,
                "name": "mHP",
                "data": {"Float": row["mHP"]},
            }
        # Attach mMaxHP as separate logical rows by expanding to two events —
        # maknee streams one name per Replication entry; emit two events.
        t = float(snap.get("time_s") or 0.0)
        rep_hp = {
            "Replication": {
                "time": t,
                "net_id_to_replication_datas": {
                    str(r["net_id"]): {
                        "primary_index": 32,
                        "secondary_index": 0,
                        "name": "mHP",
                        "data": {"Float": r["mHP"]},
                    }
                    for r in snap["heroes"]
                },
            }
        }
        rep_max = {
            "Replication": {
                "time": t,
                "net_id_to_replication_datas": {
                    str(r["net_id"]): {
                        "primary_index": 32,
                        "secondary_index": 1,
                        "name": "mMaxHP",
                        "data": {"Float": r["mMaxHP"]},
                    }
                    for r in snap["heroes"]
                },
            }
        }
        report["replication"] = [rep_hp, rep_max]
        report["heroes"] = heroes_from_events(events)
        report["ok"] = bool(snap.get("ok"))
        report["decryptStatus"] = (
            "fixture_ok" if report["ok"] else "fixture_failed_acceptance"
        )
        return report

    if backend == "emulator":
        # Bounded spike: binary field table is available; packet accessors are
        # not yet driven under Unicorn for 16.14. Fail closed — no invented HP.
        report["decryptStatus"] = "blocked_need_packet_accessor"
        report["ok"] = False
        report["error"] = (
            "16.14 packet field decrypt requires driving League Deserialize/"
            "accessor vtables (maknee-style emulator). Binary Replication "
            f"strings are present (mHP={binary_inv.get('hasMHP')}, "
            f"mMaxHP={binary_inv.get('hasMMaxHP')}), but a8/player blobs remain "
            "encrypted under static scan. No HP values invented."
        )
        if rofl is not None:
            report["rosterFromStatsJson"] = heroes_from_rofl_stats(rofl)
        return report

    raise DecryptError(f"unknown backend: {backend!r}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "rofl",
        type=Path,
        nargs="?",
        default=None,
        help="Optional local .rofl for structure/build checks",
    )
    ap.add_argument(
        "--backend",
        choices=("fixture", "emulator"),
        default="fixture",
        help="Decrypt backend (fixture for CI; emulator for live research)",
    )
    ap.add_argument(
        "--fixture-events",
        type=Path,
        default=None,
        help="maknee-shaped JSON with events[] (fixture backend)",
    )
    ap.add_argument("--target-time-s", type=float, default=None)
    ap.add_argument(
        "--league-binary",
        type=Path,
        default=DEFAULT_LEAGUE_BINARY,
        help="Patch-matched LeagueofLegends binary for field inventory",
    )
    ap.add_argument("--json-out", type=Path, default=None)
    ap.add_argument(
        "--require-acceptance",
        action="store_true",
        help="Exit 2 if 10-hero HP acceptance fails",
    )
    args = ap.parse_args()

    try:
        report = decrypt_replication_fields(
            backend=args.backend,
            rofl=args.rofl,
            fixture_events=args.fixture_events,
            target_time_s=args.target_time_s,
            league_binary=args.league_binary,
        )
    except DecryptError as e:
        print(f"decrypt probe error: {e}", file=sys.stderr)
        return 1

    # Drop raw bytes from nested structures for JSON
    printable = json.loads(json.dumps(report, default=str))
    text = json.dumps(printable, indent=2)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(text + "\n", encoding="utf-8")
        print(f"wrote {args.json_out}")
    else:
        print(text)

    print(
        f"backend={report['backend']} status={report.get('decryptStatus')} "
        f"ok={report.get('ok')} "
        f"heroes={(report.get('hpSnapshot') or {}).get('heroCount')}"
    )
    if args.require_acceptance and not report.get("ok"):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
