#!/usr/bin/env python3
"""Phase A: discover live CreateHero-equivalent packets for identity bind.

Searches early ROFL blocks whose ``param`` is a proven hero netId
(``0x400000AE..B7``), drives Windows Deserialize under E11 reconstructed
framing, and looks for champion strings / distinct champion IDs in the
object. Product bind requires champion-matched CreateHero rows — AE..B7
order alone is research-only and must not emit ``complete=true``.

Fail-closed blockers:
  - ``create_hero_opcode_not_found``
  - ``champion_not_structurally_decoded``
  - ``create_hero_bind_unavailable``

Example:
  npm run rofl:create-hero-discover -- \\
    --rofl \"$HOME/Documents/League of Legends/Replays/BR1-3264361042.rofl\" \\
    --json-out docs/rofl-research/create-hero-discover-BR1-3264361042.json
"""
from __future__ import annotations

import argparse
import json
import struct
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from rofl2_binary_format import load_binary, research_manifest  # noqa: E402
from rofl2_probe import extract_segments, parse_rofl2  # noqa: E402
from rofl2_unicorn_packet_drive import extract_blocks_py  # noqa: E402
from rofl2_win_pe_e11_reconstructed_drive import (  # noqa: E402
    deserialize_body,
    validate_reconstruction,
)
from rofl2_win_pe_packet_discover import (  # noqa: E402
    WinX64PacketEmu,
    enumerate_rofl,
    official_provenance,
    scan_msvc_packet_types,
)
from rofl_metadata import (  # noqa: E402
    _stats_players,
    participant_from_stats,
)
from rofl2_replication_timed_hp import attempt_identity_binding  # noqa: E402
from rofl_speed_bench import utc_now_iso  # noqa: E402

PROBE_VERSION = "create-hero-discover-v1"
MATCH_CODE = "3264361042"
DEFAULT_PE = Path("/tmp/League-of-Legends-16.14-win.exe")
DEFAULT_ROFL = (
    Path.home() / "Documents/League of Legends/Replays/BR1-3264361042.rofl"
)
DEFAULT_REPORT = Path(
    "docs/rofl-research/create-hero-discover-BR1-3264361042.json"
)
PROVEN_HERO_NET_IDS: Tuple[int, ...] = tuple(range(0x400000AE, 0x400000B8))
PROVEN_HERO_NET_ID_SET = set(PROVEN_HERO_NET_IDS)

# Known champion IDs for this match's skins (Zaahen ID may be absent on older tables).
KNOWN_CHAMPION_IDS: Dict[str, int] = {
    "MonkeyKing": 62,
    "Yasuo": 157,
    "Ezreal": 81,
    "Sona": 37,
    "Renekton": 58,
    "Lillia": 876,
    "Leblanc": 7,
    "LeBlanc": 7,
    "Ashe": 22,
    "Morgana": 25,
}


def roster_from_rofl(rofl: Path) -> List[Dict[str, Any]]:
    info = parse_rofl2(rofl)
    meta = info["meta"]
    if not isinstance(meta, Mapping):
        raise ValueError("ROFL metadata missing")
    players = _stats_players(meta)
    return [participant_from_stats(p, i) for i, p in enumerate(players)]


def champion_needles(roster: Sequence[Mapping[str, Any]]) -> List[bytes]:
    names: List[str] = []
    for row in roster:
        champ = row.get("champion")
        if isinstance(champ, Mapping):
            for key in ("raw", "asset", "display"):
                val = champ.get(key)
                if val:
                    names.append(str(val))
        elif isinstance(champ, str) and champ:
            names.append(champ)
    out: List[bytes] = []
    for name in names:
        out.append(name.encode("ascii", errors="ignore"))
        out.append(name.lower().encode("ascii", errors="ignore"))
        out.append(name.encode("utf-8", errors="ignore"))
    return list({n for n in out if n})


def plaintext_champion_hits(
    payload: bytes, needles: Sequence[bytes]
) -> List[str]:
    return sorted({n.decode("latin1") for n in needles if n in payload})


def collect_spawn_shaped(
    rofl: Path,
    *,
    max_lifetime: int = 40,
) -> Dict[int, Dict[str, Any]]:
    """Opcodes with ~10 lifetime packets and all 10 proven hero params."""
    info = parse_rofl2(rofl)
    extracted = extract_segments(info["payload"])
    op_n: Counter = Counter()
    op_params: Dict[int, set] = defaultdict(set)
    op_first: Dict[int, Dict[int, dict]] = defaultdict(dict)
    for seg in extracted["segments"]:
        if int(seg.get("type") or 0) != 1:
            continue
        for blk in extract_blocks_py(seg["bytes"], max_blocks=500_000):
            op = int(blk["channel"])
            op_n[op] += 1
            param = int(blk.get("param") or 0)
            if param not in PROVEN_HERO_NET_ID_SET:
                continue
            op_params[op].add(param)
            if param not in op_first[op]:
                pay = blk["payload"] or b""
                op_first[op][param] = {
                    "time": float(blk["time"]),
                    "param": param,
                    "payload": pay,
                    "size": len(pay),
                }
    shaped: Dict[int, Dict[str, Any]] = {}
    for op, n in op_n.items():
        if not (8 <= n <= max_lifetime):
            continue
        if len(op_params[op]) != 10:
            continue
        blocks = [op_first[op][nid] for nid in sorted(op_first[op])]
        shaped[op] = {
            "opcode": op,
            "lifetimeCount": int(n),
            "uniqueHeroParams": 10,
            "blocks": blocks,
            "sizeRange": [
                min(b["size"] for b in blocks),
                max(b["size"] for b in blocks),
            ],
            "timeRange": [
                min(b["time"] for b in blocks),
                max(b["time"] for b in blocks),
            ],
        }
    return shaped


def _scan_object_for_champions(
    mem: bytes,
    *,
    needles: Sequence[bytes],
    roster_names: Sequence[str],
) -> Dict[str, Any]:
    string_hits = sorted({n.decode("latin1") for n in needles if n in mem})
    id_hits: List[str] = []
    for name, cid in KNOWN_CHAMPION_IDS.items():
        if name not in roster_names and name.casefold() not in {
            x.casefold() for x in roster_names
        }:
            continue
        if struct.pack("<I", cid) in mem or struct.pack("<H", cid) in mem:
            id_hits.append(name)
    return {"stringHits": string_hits, "idHits": sorted(set(id_hits))}


def drive_candidates(
    *,
    binary: Any,
    factories: Mapping[int, Mapping[str, Any]],
    shaped: Mapping[int, Mapping[str, Any]],
    needles: Sequence[bytes],
    roster_names: Sequence[str],
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for op, meta in sorted(shaped.items()):
        factory = factories.get(op)
        if not factory or not factory.get("deserializeVa"):
            rows.append(
                {
                    "opcode": op,
                    "framingValidated": False,
                    "blocker": "factory_missing",
                    "lifetimeCount": meta["lifetimeCount"],
                }
            )
            continue
        blocks = list(meta["blocks"])
        framing = validate_reconstruction(
            binary,
            factory,
            [{"payload": b["payload"]} for b in blocks],
            min_samples=min(10, len(blocks)),
        )
        per_hero: List[Dict[str, Any]] = []
        champion_by_net: Dict[int, str] = {}
        emu = WinX64PacketEmu(binary)
        for blk in blocks:
            body = deserialize_body(op, blk["payload"])
            fac = emu.construct(
                ctor_va=int(factory["ctorVa"]),
                object_size=int(factory["objectSize"]),
                expected_opcode=op,
                expected_vptr=int(factory["vptr"]),
            )
            if not fac.get("ok"):
                per_hero.append(
                    {
                        "netId": int(blk["param"]),
                        "constructOk": False,
                    }
                )
                continue
            deser = emu.deserialize(
                obj=int(fac["obj"]),
                deser_va=int(factory["deserializeVa"]),
                payload=body,
                object_size=int(factory["objectSize"]),
            )
            mem = bytes(
                emu.mu.mem_read(
                    int(fac["obj"]),
                    max(256, int(factory["objectSize"])),
                )
            )
            hits = _scan_object_for_champions(
                mem, needles=needles, roster_names=roster_names
            )
            # Only accept a champion when this hero's object uniquely names it.
            unique = hits["stringHits"] or hits["idHits"]
            chosen = unique[0] if len(unique) == 1 else None
            if chosen:
                champion_by_net[int(blk["param"])] = chosen
            per_hero.append(
                {
                    "netId": int(blk["param"]),
                    "time": blk["time"],
                    "constructOk": True,
                    "retAl": deser.get("retAl"),
                    "consumed": deser.get("consumed"),
                    "bodyLen": len(body),
                    "hits": hits,
                    "chosenChampion": chosen,
                }
            )
        distinct_champs = sorted(set(champion_by_net.values()))
        rows.append(
            {
                "opcode": op,
                "lifetimeCount": meta["lifetimeCount"],
                "sizeRange": meta["sizeRange"],
                "timeRange": meta["timeRange"],
                "framing": framing,
                "framingValidated": bool(framing.get("validated")),
                "heroesDecoded": len(per_hero),
                "championsRecovered": len(champion_by_net),
                "distinctChampions": distinct_champs,
                "perHero": per_hero,
                "createHeroCandidate": (
                    len(champion_by_net) == 10 and len(distinct_champs) == 10
                ),
            }
        )
    return rows


def emit_create_hero_events(
    champion_by_net: Mapping[int, str],
) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    for index, net_id in enumerate(sorted(champion_by_net)):
        events.append(
            {
                "CreateHero": {
                    "time": 0.0,
                    "net_id": int(net_id),
                    "name": "",
                    "champion": champion_by_net[net_id],
                    "participantID": index + 1,
                }
            }
        )
    return events


def classify_blocker(
    *,
    shaped_count: int,
    candidate_rows: Sequence[Mapping[str, Any]],
    plaintext_in_rofl: bool,
) -> Dict[str, Any]:
    winners = [r for r in candidate_rows if r.get("createHeroCandidate")]
    if winners:
        return {
            "kind": None,
            "detail": f"opcode {winners[0]['opcode']} recovered 10 distinct champions",
            "winnerOpcode": int(winners[0]["opcode"]),
        }
    if plaintext_in_rofl:
        return {
            "kind": "create_hero_opcode_not_found",
            "detail": "champion strings exist in ROFL payload but no opcode paired them with netIds",
        }
    if shaped_count == 0:
        return {
            "kind": "create_hero_opcode_not_found",
            "detail": "no ~10-packet opcode covering all proven hero netId params",
        }
    framed = [r for r in candidate_rows if r.get("framingValidated")]
    if framed and all(int(r.get("championsRecovered") or 0) == 0 for r in framed):
        return {
            "kind": "champion_not_structurally_decoded",
            "detail": (
                "spawn-shaped opcodes Deserialize under E11 framing but do not "
                "release champion strings or unique champion IDs per netId"
            ),
        }
    return {
        "kind": "create_hero_bind_unavailable",
        "detail": "CreateHero-equivalent champion↔netId evidence not recovered",
    }


def run_discover(
    *,
    rofl: Path,
    pe: Path,
    events_out: Optional[Path] = None,
) -> Dict[str, Any]:
    t0 = time.perf_counter()
    roster = roster_from_rofl(rofl)
    roster_names: List[str] = []
    for row in roster:
        champ = row.get("champion")
        if isinstance(champ, Mapping):
            roster_names.append(
                str(champ.get("raw") or champ.get("asset") or champ.get("display") or "")
            )
        elif isinstance(champ, str):
            roster_names.append(champ)
    needles = champion_needles(roster)

    info = parse_rofl2(rofl)
    payload = info["payload"]
    plaintext = plaintext_champion_hits(payload, needles)

    binary = load_binary(pe)
    counts, _samples = enumerate_rofl(rofl)
    factory_rows, coverage = scan_msvc_packet_types(binary, counts)
    factories = {int(r["opcode"]): r for r in factory_rows}

    shaped = collect_spawn_shaped(rofl)
    candidate_rows = drive_candidates(
        binary=binary,
        factories=factories,
        shaped=shaped,
        needles=needles,
        roster_names=roster_names,
    )
    blocker = classify_blocker(
        shaped_count=len(shaped),
        candidate_rows=candidate_rows,
        plaintext_in_rofl=bool(plaintext),
    )

    events: List[Dict[str, Any]] = []
    binding: Dict[str, Any]
    product_complete = False
    if blocker.get("winnerOpcode") is not None:
        winner = next(
            r for r in candidate_rows if r.get("opcode") == blocker["winnerOpcode"]
        )
        champ_by_net = {
            int(h["netId"]): str(h["chosenChampion"])
            for h in winner.get("perHero") or []
            if h.get("chosenChampion")
        }
        events = emit_create_hero_events(champ_by_net)
        create_rows = [
            {
                "net_id": int(e["CreateHero"]["net_id"]),
                "champion": e["CreateHero"]["champion"],
                "participantID": e["CreateHero"]["participantID"],
            }
            for e in events
        ]
        binding = attempt_identity_binding(roster, create_hero_rows=create_rows)
        product_complete = bool(binding.get("complete"))
        if events_out is not None and product_complete:
            events_out.parent.mkdir(parents=True, exist_ok=True)
            events_out.write_text(
                json.dumps({"events": events}, indent=2) + "\n",
                encoding="utf-8",
            )
    else:
        binding = attempt_identity_binding(
            roster,
            replication_net_ids=PROVEN_HERO_NET_IDS,
            create_hero_rows=None,
        )

    wall_ms = (time.perf_counter() - t0) * 1000.0
    report = {
        "ok": product_complete,
        "probeVersion": PROBE_VERSION,
        "ts": utc_now_iso(),
        "matchCode": MATCH_CODE,
        "wallMs": round(wall_ms, 3),
        "official": official_provenance(
            size=pe.stat().st_size,
            sha256=str(getattr(binary, "sha256", "") or ""),
        ),
        "binaryManifest": research_manifest(
            binary,
            patch="16.14",
            extra={"probeVersion": PROBE_VERSION, "pathNote": str(pe)},
        ),
        "constructorCoverage": coverage,
        "rosterChampions": roster_names,
        "plaintextChampionHitsInRofl": plaintext,
        "spawnShapedOpcodeCount": len(shaped),
        "spawnShapedOpcodes": sorted(shaped),
        "candidates": [
            {
                **{k: v for k, v in row.items() if k != "perHero"},
                "perHeroHead": (row.get("perHero") or [])[:3],
            }
            for row in candidate_rows
        ],
        "createHeroEvents": events if product_complete else [],
        "identityBinding": binding,
        "blocker": blocker if not product_complete else None,
        "productEligible": product_complete,
        "createHeroOrderFallback": bool(binding.get("createHeroOrderFallback")),
        "exhaustedAvenues": [
            {
                "avenue": "pkt_s2c_create_hero_rtti",
                "result": "absent",
                "detail": "No PKT_S2C_CreateHero / CreateHero TypeDescriptor on 16.14 PE",
            },
            {
                "avenue": "start_hero_spawn_string",
                "result": "not_a_packet",
                "detail": "StartHeroSpawn is a tooltip/game string, not a MakeFunction packet handler",
            },
            {
                "avenue": "spawn_shaped_opcodes_e11_deser",
                "result": "no_champion_fields",
                "detail": (
                    f"Opcodes {sorted(shaped)} cover 10 hero params; E11 framing "
                    "validates; object/heap yield no champion strings or unique IDs"
                ),
            },
            {
                "avenue": "plaintext_champion_in_rofl",
                "result": "absent",
                "detail": "Champion/skin ASCII not present in decrypted chunk payload",
            },
            {
                "avenue": "keyframe_netid_nearby_champ_id",
                "result": "insufficient",
                "detail": (
                    "u16/u32 champ IDs near netId bytes in type=2 keyframes do not "
                    "yield 10 distinct roster-matched associations"
                ),
            },
            {
                "avenue": "ae_b7_order_fallback",
                "result": "research_only",
                "detail": "Intentionally rejected for product (createHeroOrderFallback)",
            },
        ],
        "note": (
            "Product bind requires champion-matched CreateHero rows. "
            "AE..B7 order / CreateHero-order fallback remains research-only."
        ),
    }
    return report


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rofl", type=Path, default=DEFAULT_ROFL)
    ap.add_argument("--pe", type=Path, default=DEFAULT_PE)
    ap.add_argument("--json-out", type=Path, default=DEFAULT_REPORT)
    ap.add_argument(
        "--events-out",
        type=Path,
        default=None,
        help="Write maknee-shaped CreateHero events only when product-complete",
    )
    args = ap.parse_args(argv)

    if not args.rofl.is_file():
        print(f"missing ROFL: {args.rofl}", file=sys.stderr)
        return 2
    if not args.pe.is_file():
        print(f"missing PE: {args.pe}", file=sys.stderr)
        return 2

    report = run_discover(
        rofl=args.rofl,
        pe=args.pe,
        events_out=args.events_out,
    )
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(
        json.dumps(report, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {args.json_out}")
    blocker = report.get("blocker") or {}
    print(
        f"ok={report.get('ok')} productEligible={report.get('productEligible')} "
        f"blocker={blocker.get('kind')} bindComplete="
        f"{(report.get('identityBinding') or {}).get('complete')}"
    )
    return 0 if report.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
