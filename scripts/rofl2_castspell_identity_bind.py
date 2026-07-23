#!/usr/bin/env python3
"""Phase A bind via PKT_NPC_CastSpellAns_s (opcode 197) champion string release.

Online prior art (maknee decoded packets): CastSpellAns carries caster netId +
spell/champion identity. On 16.14 Windows PE, MakeFunction registration maps
``PKT_NPC_CastSpellAns_s`` → opcode **197**. Fresh Unicorn Deserialize per
packet releases a unique roster champion string on the object/pointers.

This is CreateHero-*equivalent* champion↔netId evidence (not AE..B7 order).

Example:
  npm run rofl:castspell-identity-bind -- \\
    --rofl \"$HOME/Documents/League of Legends/Replays/BR1-3264361042.rofl\" \\
    --events-out docs/rofl-research/create-hero-from-castspell-BR1-3264361042.json \\
    --json-out docs/rofl-research/castspell-identity-BR1-3264361042.json
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
from rofl2_create_hero_discover import (  # noqa: E402
    DEFAULT_PE,
    DEFAULT_ROFL,
    PROVEN_HERO_NET_IDS,
    PROVEN_HERO_NET_ID_SET,
    emit_create_hero_events,
    roster_from_rofl,
)
from rofl2_probe import extract_segments, parse_rofl2  # noqa: E402
from rofl2_replication_timed_hp import attempt_identity_binding  # noqa: E402
from rofl2_unicorn_packet_drive import extract_blocks_py  # noqa: E402
from rofl2_win_pe_e11_reconstructed_drive import deserialize_body  # noqa: E402
from rofl2_win_pe_e8_movement import map_semantic_registrations  # noqa: E402
from rofl2_win_pe_packet_discover import (  # noqa: E402
    WinX64PacketEmu,
    enumerate_rofl,
    official_provenance,
    scan_msvc_packet_types,
)
from rofl_speed_bench import utc_now_iso  # noqa: E402

PROBE_VERSION = "castspell-identity-bind-v1"
MATCH_CODE = "3264361042"
DEFAULT_REPORT = Path(
    "docs/rofl-research/castspell-identity-BR1-3264361042.json"
)
DEFAULT_EVENTS = Path(
    "docs/rofl-research/create-hero-from-castspell-BR1-3264361042.json"
)

# E8 MakeFunction TypeDescriptor for AIBaseClient CastSpellAns handler (16.14).
CASTSPELL_TD_VA = "0x141e661b0"
CASTSPELL_PKT = "PKT_NPC_CastSpellAns_s"
# Observed registration opcode on this PE; verified via map_semantic_registrations.
CASTSPELL_OPCODE_FALLBACK = 197

CHAMP_ALIASES = {
    "wukong": "MonkeyKing",
    "monkeyking": "MonkeyKing",
    "leblanc": "Leblanc",
}


def resolve_castspell_opcode(binary: Any) -> Dict[str, Any]:
    td_info = {
        CASTSPELL_PKT: {
            "pkt": CASTSPELL_PKT,
            "typeDescriptorVa": CASTSPELL_TD_VA,
            "nameVa": hex(int(CASTSPELL_TD_VA, 16) + 0x10),
        }
    }
    mapped = map_semantic_registrations(binary, td_info)
    row = mapped.get(CASTSPELL_PKT) or {}
    opcode = row.get("opcode")
    if opcode is None:
        opcode = CASTSPELL_OPCODE_FALLBACK
        row = {
            **row,
            "ok": True,
            "opcode": opcode,
            "note": "fallback_opcode_197_after_registration_miss",
        }
    return {"pkt": CASTSPELL_PKT, "opcode": int(opcode), "registration": row}


def _roster_champ_names(roster: Sequence[Mapping[str, Any]]) -> List[str]:
    names: List[str] = []
    for row in roster:
        champ = row.get("champion")
        if isinstance(champ, Mapping):
            raw = champ.get("raw") or champ.get("asset") or champ.get("display")
            if raw:
                names.append(str(raw))
        elif isinstance(champ, str) and champ:
            names.append(champ)
    return names


def _needles(roster_names: Sequence[str]) -> List[bytes]:
    out: List[bytes] = []
    for name in roster_names:
        out.append(name.encode("ascii", errors="ignore"))
        for suf in ("Q", "W", "E", "R", "Q1", "Q2", "Q3", "R1", "R2", "P", "BasicAttack"):
            out.append(f"{name}{suf}".encode("ascii", errors="ignore"))
        if name == "MonkeyKing":
            out.append(b"Wukong")
            out.append(b"WukongQ")
        if name.casefold() == "leblanc":
            out.append(b"LeBlanc")
            out.append(b"LeBlancQ")
    return list({n for n in out if n})


def normalize_champion(token: str, roster_names: Sequence[str]) -> Optional[str]:
    t = token.strip()
    if not t:
        return None
    alias = CHAMP_ALIASES.get(t.casefold())
    if alias:
        t = alias
    for name in roster_names:
        if t == name or t.startswith(name):
            return name
        if name.casefold() == "leblanc" and t.casefold().startswith("leblanc"):
            return name
        if name == "MonkeyKing" and t.casefold().startswith("wukong"):
            return name
    return None


def _scan_blob(blob: bytes, needles: Sequence[bytes]) -> List[str]:
    return [n.decode("latin1") for n in needles if n in blob]


def collect_hero_cast_blocks(
    rofl: Path, opcode: int, *, per_hero: int = 8
) -> Dict[int, List[dict]]:
    info = parse_rofl2(rofl)
    extracted = extract_segments(info["payload"])
    by_hero: Dict[int, List[dict]] = defaultdict(list)
    for seg in extracted["segments"]:
        if int(seg.get("type") or 0) != 1:
            continue
        for blk in extract_blocks_py(seg["bytes"], max_blocks=500_000):
            if int(blk["channel"]) != opcode:
                continue
            param = int(blk.get("param") or 0)
            if param not in PROVEN_HERO_NET_ID_SET:
                continue
            if len(by_hero[param]) >= per_hero:
                continue
            by_hero[param].append(
                {
                    "time": float(blk["time"]),
                    "param": param,
                    "payload": blk["payload"] or b"",
                }
            )
    return dict(by_hero)


def attribute_champions(
    *,
    binary: Any,
    factory: Mapping[str, Any],
    opcode: int,
    by_hero: Mapping[int, Sequence[dict]],
    roster_names: Sequence[str],
) -> Tuple[Dict[int, str], Dict[int, List[dict]], Dict[int, Counter]]:
    needles = _needles(roster_names)
    votes: Dict[int, Counter] = defaultdict(Counter)
    samples: Dict[int, List[dict]] = defaultdict(list)

    for net_id in PROVEN_HERO_NET_IDS:
        blocks = list(by_hero.get(net_id) or [])
        for blk in blocks:
            emu = WinX64PacketEmu(binary)
            body = deserialize_body(opcode, blk["payload"])
            fac = emu.construct(
                ctor_va=int(factory["ctorVa"]),
                object_size=int(factory["objectSize"]),
                expected_opcode=opcode,
                expected_vptr=int(factory["vptr"]),
            )
            if not fac.get("ok"):
                continue
            obj = int(fac["obj"])
            deser = emu.deserialize(
                obj=obj,
                deser_va=int(factory["deserializeVa"]),
                payload=body,
                object_size=int(factory["objectSize"]),
            )
            after = bytes(emu.mu.mem_read(obj, int(factory["objectSize"])))
            hits = set(_scan_blob(after, needles))
            for off in range(0, len(after) - 7, 8):
                ptr = struct.unpack_from("<Q", after, off)[0]
                if 0x300000000 <= ptr < 0x310000000:
                    try:
                        blob = bytes(emu.mu.mem_read(ptr, 96))
                    except Exception:  # noqa: BLE001
                        continue
                    hits.update(_scan_blob(blob, needles))
            ability = []
            for h in hits:
                if any(h.startswith(name) and h != name for name in roster_names):
                    ability.append(h)
                elif h.casefold().startswith("wukong") and h.casefold() != "wukong":
                    ability.append(h)
                elif h.casefold().startswith("leblanc") and h.casefold() != "leblanc":
                    ability.append(h)
            chosen: Optional[str] = None
            if ability:
                cc = Counter(
                    normalize_champion(h, roster_names) for h in ability
                )
                cc = Counter({k: v for k, v in cc.items() if k})
                if cc:
                    chosen = cc.most_common(1)[0][0]
                    votes[net_id][chosen] += 3
            else:
                norms = [
                    c
                    for c in (normalize_champion(h, roster_names) for h in hits)
                    if c
                ]
                uniq = sorted(set(norms))
                if len(uniq) == 1:
                    chosen = uniq[0]
                    votes[net_id][chosen] += 1
            samples[net_id].append(
                {
                    "time": blk["time"],
                    "retAl": deser.get("retAl"),
                    "consumed": deser.get("consumed"),
                    "hits": sorted(hits),
                    "chosen": chosen,
                }
            )

    winners: Dict[int, str] = {}
    used: set = set()
    ranked: List[Tuple[int, int, str]] = []
    for net_id in PROVEN_HERO_NET_IDS:
        if not votes[net_id]:
            continue
        champ, score = votes[net_id].most_common(1)[0]
        ranked.append((score, net_id, champ))
    ranked.sort(reverse=True)
    for score, net_id, champ in ranked:
        if champ in used:
            for alt, alt_score in votes[net_id].most_common():
                if alt not in used:
                    champ = alt
                    score = alt_score
                    break
            else:
                continue
        winners[net_id] = champ
        used.add(champ)
    return winners, dict(samples), dict(votes)


def run_bind(
    *,
    rofl: Path,
    pe: Path,
    per_hero: int = 8,
) -> Dict[str, Any]:
    t0 = time.perf_counter()
    roster = roster_from_rofl(rofl)
    roster_names = _roster_champ_names(roster)
    binary = load_binary(pe)
    reg = resolve_castspell_opcode(binary)
    opcode = int(reg["opcode"])
    counts, _ = enumerate_rofl(rofl)
    factories, coverage = scan_msvc_packet_types(binary, counts)
    factory = next((r for r in factories if int(r["opcode"]) == opcode), None)
    if not factory:
        return {
            "ok": False,
            "blocker": {
                "kind": "castspell_factory_missing",
                "detail": f"opcode {opcode} factory not recovered",
            },
            "productEligible": False,
        }

    by_hero = collect_hero_cast_blocks(rofl, opcode, per_hero=per_hero)
    winners, samples, votes = attribute_champions(
        binary=binary,
        factory=factory,
        opcode=opcode,
        by_hero=by_hero,
        roster_names=roster_names,
    )

    events: List[Dict[str, Any]] = []
    binding: Dict[str, Any]
    complete = False
    if len(winners) == 10 and len(set(winners.values())) == 10:
        events = emit_create_hero_events(winners)
        create_rows = [
            {
                "net_id": int(e["CreateHero"]["net_id"]),
                "champion": e["CreateHero"]["champion"],
                "participantID": e["CreateHero"]["participantID"],
            }
            for e in events
        ]
        binding = attempt_identity_binding(roster, create_hero_rows=create_rows)
        complete = bool(binding.get("complete"))
    else:
        binding = attempt_identity_binding(
            roster,
            replication_net_ids=PROVEN_HERO_NET_IDS,
            create_hero_rows=None,
        )

    wall_ms = (time.perf_counter() - t0) * 1000.0
    blocker = None
    if not complete:
        blocker = {
            "kind": "castspell_champion_bind_incomplete",
            "detail": (
                f"recovered {len(winners)}/10 distinct champion↔netId pairs "
                "from CastSpellAns Deserialize"
            ),
            "winners": {hex(k): v for k, v in winners.items()},
        }

    return {
        "ok": complete,
        "probeVersion": PROBE_VERSION,
        "ts": utc_now_iso(),
        "matchCode": MATCH_CODE,
        "wallMs": round(wall_ms, 3),
        "priorArt": {
            "maknee": "CastSpellAns carries caster netId + spell/champion identity",
            "pePacket": CASTSPELL_PKT,
            "opcode": opcode,
        },
        "registration": reg,
        "official": official_provenance(
            size=pe.stat().st_size,
            sha256=str(getattr(binary, "sha256", "") or ""),
        ),
        "binaryManifest": research_manifest(
            binary,
            patch="16.14",
            extra={"probeVersion": PROBE_VERSION},
        ),
        "constructorCoverage": coverage,
        "rosterChampions": roster_names,
        "factory": {
            "opcode": opcode,
            "objectSize": factory.get("objectSize"),
            "deserializeVa": hex(int(factory["deserializeVa"])),
            "ctorVa": hex(int(factory["ctorVa"])),
        },
        "samplesPerHero": {hex(k): len(v) for k, v in samples.items()},
        "sampleHead": {
            hex(k): (v[:2] if v else []) for k, v in samples.items()
        },
        "votes": {
            hex(k): v.most_common() for k, v in votes.items()
        },
        "winners": {hex(k): v for k, v in winners.items()},
        "createHeroEvents": events if complete else [],
        "identityBinding": binding,
        "blocker": blocker,
        "productEligible": complete,
        "createHeroOrderFallback": bool(binding.get("createHeroOrderFallback")),
        "method": "castspell_ans_champion_string",
        "note": (
            "CreateHero-equivalent bind via PKT_NPC_CastSpellAns_s Deserialize "
            "champion string release; not CreateHero-order / AE..B7 order"
        ),
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rofl", type=Path, default=DEFAULT_ROFL)
    ap.add_argument("--pe", type=Path, default=DEFAULT_PE)
    ap.add_argument("--json-out", type=Path, default=DEFAULT_REPORT)
    ap.add_argument("--events-out", type=Path, default=DEFAULT_EVENTS)
    ap.add_argument("--per-hero", type=int, default=8)
    args = ap.parse_args(argv)

    if not args.rofl.is_file() or not args.pe.is_file():
        print("missing ROFL or PE", file=sys.stderr)
        return 2

    report = run_bind(rofl=args.rofl, pe=args.pe, per_hero=max(1, args.per_hero))
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(
        json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8"
    )
    print(f"wrote {args.json_out}")
    if report.get("ok") and report.get("createHeroEvents"):
        args.events_out.parent.mkdir(parents=True, exist_ok=True)
        args.events_out.write_text(
            json.dumps({"events": report["createHeroEvents"]}, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"wrote events {args.events_out}")
    print(
        f"ok={report.get('ok')} productEligible={report.get('productEligible')} "
        f"bindComplete={(report.get('identityBinding') or {}).get('complete')} "
        f"blocker={(report.get('blocker') or {}).get('kind')}"
    )
    return 0 if report.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
