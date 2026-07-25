#!/usr/bin/env python3
"""Gate B2 / P3-H1: decode PKT_NPC_UpgradeSpellAns_s → identity-bound ranks.

Patch facts:
  - 16.14 (BR1): opcode **636**, first-write level@+0x10 / slot@+0x11
  - 16.13 (pro 2970110): opcode **1012** (R15 MakeFunction→register_hub),
    first-write slot@+0x12 / level@+0x13 (BR1 offsets miss ciphered packets)

Capture first UC_HOOK_MEM_WRITE per offset before in-place cipher.
Never fixture-remaps maknee/BR1 ranks onto another match.
NetId→champion uses CastSpellAns identity winners (R32 on pro).

Examples:
  npm run rofl:upgrade-spell-ranks -- \\
    --rofl \"$HOME/Documents/League of Legends/Replays/BR1-3264361042.rofl\" \\
    --json-out docs/rofl-research/upgrade-spell-ranks-BR1-3264361042.json

  npm run rofl:upgrade-spell-ranks -- \\
    --rofl artifacts/pro-grid/replay_riot_2970110_1.rofl \\
    --pe /tmp/League-of-Legends-16.13-win.exe \\
    --identity docs/rofl-research/packet_decode/r32/castspell-identity-2970110-g1.json \\
    --match-code 2970110-g1 --resilient \\
    --json-out docs/rofl-research/upgrade-spell-ranks-2970110-g1.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from rofl2_binary_format import load_binary, research_manifest  # noqa: E402
from rofl2_create_hero_discover import (  # noqa: E402
    DEFAULT_PE,
    DEFAULT_ROFL,
    PROVEN_HERO_NET_ID_SET,
    PROVEN_HERO_NET_IDS,
)
from rofl2_probe import (  # noqa: E402
    extract_segments,
    extract_segments_resilient,
    parse_rofl2,
)
from rofl2_unicorn_packet_drive import extract_blocks_py  # noqa: E402
from rofl2_win_pe_e11_reconstructed_drive import deserialize_body  # noqa: E402
from rofl2_win_pe_e8_movement import (  # noqa: E402
    _hex,
    demangle_msvc_name,
    map_semantic_registrations,
)
from rofl2_win_pe_packet_discover import (  # noqa: E402
    WinX64PacketEmu,
    enumerate_rofl,
    scan_msvc_packet_types,
)
from rofl_speed_bench import utc_now_iso  # noqa: E402

PROBE_VERSION = "upgrade-spell-ranks-v2"
MATCH_CODE = "3264361042"
UPGRADE_SPELL_PKT = "PKT_NPC_UpgradeSpellAns_s"
UPGRADE_SPELL_OPCODE_FALLBACK_16_14 = 636
UPGRADE_SPELL_OPCODE_16_13 = 1012
LEVEL_OFFSET_16_14 = 0x10
SLOT_OFFSET_16_14 = 0x11
SLOT_OFFSET_16_13 = 0x12
LEVEL_OFFSET_16_13 = 0x13
# Legacy export for fuse_replay_api_ranks (BR1 16.14 source tag).
ABILITY_RANKS_SOURCE = "rofl2_upgrade_spell_ans_636_first_write"
LEVEL_OFFSET = LEVEL_OFFSET_16_14
SLOT_OFFSET = SLOT_OFFSET_16_14
UPGRADE_SPELL_OPCODE_FALLBACK = UPGRADE_SPELL_OPCODE_FALLBACK_16_14
R15_REMAP = Path(
    "docs/rofl-research/packet_decode/r15/pe_opcode_remap_16_13.json"
)
BR1_IDENTITY_CHAMPS = frozenset(
    {
        "Zaahen",
        "MonkeyKing",
        "Yasuo",
        "Ezreal",
        "Sona",
        "Renekton",
        "Lillia",
        "Leblanc",
        "Ashe",
        "Morgana",
    }
)
DEFAULT_OUT = Path("docs/rofl-research/upgrade-spell-ranks-BR1-3264361042.json")
CASTSPELL_IDENTITY = Path(
    "docs/rofl-research/castspell-identity-BR1-3264361042.json"
)


def find_upgrade_td(binary: Any) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for seg in binary.segments:
        if seg.name not in (".rdata", ".data"):
            continue
        blob = binary.data[seg.fileoff : seg.fileoff + seg.filesize]
        needle = UPGRADE_SPELL_PKT.encode("ascii")
        start = 0
        while True:
            j = blob.find(needle, start)
            if j < 0:
                break
            k = j
            while k > 0 and blob[k : k + 4] != b".?AV":
                k -= 1
                if j - k > 500:
                    break
            if blob[k : k + 4] == b".?AV" and b"MakeFunction" in blob[k:j]:
                name = blob[k : k + 360].split(b"\x00", 1)[0].decode(
                    "ascii", "replace"
                )
                name_va = seg.vmaddr + k
                out[UPGRADE_SPELL_PKT] = {
                    "pkt": UPGRADE_SPELL_PKT,
                    "typeDescriptorVa": _hex(name_va - 16),
                    "nameVa": _hex(name_va),
                    "mangled": name,
                    "demangled": demangle_msvc_name(name),
                }
                return out
            start = j + 1
    return out


def resolve_upgrade_opcode(
    binary: Any, *, prefer_opcode: Optional[int] = None
) -> Dict[str, Any]:
    td = find_upgrade_td(binary)
    mapped = map_semantic_registrations(binary, td) if td else {}
    row = mapped.get(UPGRADE_SPELL_PKT) or {}
    opcode = row.get("opcode")
    source = "map_semantic_registrations"
    if opcode is None and prefer_opcode is not None:
        opcode = int(prefer_opcode)
        source = "cli_prefer_opcode"
        row = {**row, "ok": True, "opcode": opcode, "note": source}
    if opcode is None and R15_REMAP.is_file():
        remap = json.loads(R15_REMAP.read_text(encoding="utf-8"))
        pkt = (remap.get("packets") or {}).get(UPGRADE_SPELL_PKT) or {}
        if pkt.get("ok") and pkt.get("opcode") is not None:
            opcode = int(pkt["opcode"])
            source = "r15_pe_opcode_remap_16_13"
            row = {
                **row,
                "ok": True,
                "opcode": opcode,
                "note": source,
                "r15": {
                    "evidence": pkt.get("evidence"),
                    "factory": pkt.get("factory"),
                },
            }
    if opcode is None:
        opcode = UPGRADE_SPELL_OPCODE_FALLBACK_16_14
        source = "fallback_opcode_636"
        row = {
            **row,
            "ok": True,
            "opcode": opcode,
            "note": "fallback_opcode_636_after_registration_miss",
        }
    return {
        "pkt": UPGRADE_SPELL_PKT,
        "opcode": int(opcode),
        "registration": row,
        "opcodeSource": source,
    }


def collect_upgrade_blocks(
    rofl: Path, opcode: int, *, resilient: bool = False
) -> Tuple[List[dict], Dict[str, Any]]:
    info = parse_rofl2(rofl)
    if resilient:
        extracted = extract_segments_resilient(info["payload"])
        segs = extracted.get("segments") or []
        walker = {
            "mode": "resilient",
            "segments": len(segs),
            "summary": {
                "leftover": extracted.get("leftover"),
                "skip_count": extracted.get("skip_count"),
            },
        }
    else:
        extracted = extract_segments(info["payload"])
        segs = [
            s
            for s in (extracted.get("segments") or [])
            if int(s.get("type") or 0) == 1
        ]
        walker = {"mode": "type1", "segments": len(segs)}

    rows: List[dict] = []
    for seg in segs:
        raw = seg.get("bytes") if "bytes" in seg else seg.get("payload")
        if raw is None:
            continue
        for blk in extract_blocks_py(raw, max_blocks=500_000):
            if int(blk["channel"]) != opcode:
                continue
            param = int(blk.get("param") or 0)
            if param not in PROVEN_HERO_NET_ID_SET:
                continue
            rows.append(
                {
                    "time": float(blk["time"]),
                    "netId": param,
                    "payload": blk["payload"] or b"",
                }
            )
    rows.sort(key=lambda r: r["time"])
    return rows, walker


def pick_level_slot(first: Mapping[int, int]) -> Optional[Tuple[int, int, str]]:
    """Return (level, slot, layoutId) from first-write map."""
    lv14 = first.get(LEVEL_OFFSET_16_14)
    sl14 = first.get(SLOT_OFFSET_16_14)
    if (
        lv14 is not None
        and sl14 is not None
        and 1 <= int(lv14) <= 5
        and 0 <= int(sl14) <= 3
    ):
        return int(lv14), int(sl14), "16.14_level@0x10_slot@0x11"
    sl13 = first.get(SLOT_OFFSET_16_13)
    lv13 = first.get(LEVEL_OFFSET_16_13)
    if (
        lv13 is not None
        and sl13 is not None
        and 1 <= int(lv13) <= 5
        and 0 <= int(sl13) <= 3
    ):
        return int(lv13), int(sl13), "16.13_slot@0x12_level@0x13"
    return None


def decode_first_writes(
    *,
    binary: Any,
    factory: Mapping[str, Any],
    opcode: int,
    blocks: Sequence[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    from unicorn import UC_HOOK_MEM_WRITE

    object_size = int(factory["objectSize"])
    deser_va = int(factory["deserializeVa"])
    out: List[Dict[str, Any]] = []
    for blk in blocks:
        emu = WinX64PacketEmu(binary)
        body = deserialize_body(opcode, blk["payload"])
        fac = emu.construct(
            ctor_va=int(factory["ctorVa"]),
            object_size=object_size,
            expected_opcode=opcode,
            expected_vptr=int(factory["vptr"]),
        )
        if not fac.get("ok"):
            continue
        obj = int(fac["obj"])
        first: Dict[int, int] = {}

        def hook(_uc, _access, address, size, value, _user):  # type: ignore[no-untyped-def]
            if size != 1:
                return
            if obj <= address < obj + object_size:
                off = int(address - obj)
                if off not in first:
                    first[off] = int(value) & 0xFF

        emu.mu.hook_add(UC_HOOK_MEM_WRITE, hook)
        deser = emu.deserialize(
            obj=obj,
            deser_va=deser_va,
            payload=body,
            object_size=object_size,
        )
        picked = pick_level_slot(first)
        if picked is None:
            continue
        level, slot, layout_id = picked
        out.append(
            {
                "time": float(blk["time"]),
                "gameTimeMs": int(round(float(blk["time"]) * 1000)),
                "netId": int(blk["netId"]),
                "slot": int(slot),
                "level": int(level),
                "layoutId": layout_id,
                "payloadHex": (blk["payload"] or b"").hex(),
                "consumed": deser.get("consumed"),
                "retAl": deser.get("retAl"),
                "firstWrites": {str(k): v for k, v in sorted(first.items())},
            }
        )
    return out


def load_identity_winners(path: Path = CASTSPELL_IDENTITY) -> Dict[int, str]:
    if not path.is_file():
        return {}
    report = json.loads(path.read_text(encoding="utf-8"))
    winners = report.get("winners") or {}
    out: Dict[int, str] = {}
    for k, v in winners.items():
        try:
            out[int(k, 16) if isinstance(k, str) else int(k)] = str(v)
        except (TypeError, ValueError):
            continue
    return out


def build_cumulative_ranks(
    events: Sequence[Mapping[str, Any]],
) -> Tuple[Dict[int, List[int]], List[Dict[str, Any]]]:
    ranks: Dict[int, List[int]] = {
        nid: [0, 0, 0, 0] for nid in PROVEN_HERO_NET_IDS
    }
    snapshots: List[Dict[str, Any]] = []
    for ev in events:
        nid = int(ev["netId"])
        slot = int(ev["slot"])
        level = int(ev["level"])
        cur = ranks.setdefault(nid, [0, 0, 0, 0])
        cur[slot] = max(cur[slot], level)
        snapshots.append(
            {
                "gameTimeMs": ev["gameTimeMs"],
                "netId": nid,
                "slot": slot,
                "level": level,
                "ranksAfter": list(cur),
            }
        )
    return ranks, snapshots


def _identity_exclusive(
    winners: Mapping[int, str], *, match_code: str
) -> Dict[str, Any]:
    champs = set(winners.values())
    br1_overlap = sorted(champs & BR1_IDENTITY_CHAMPS)
    # Same champion name can appear across matches (Ezreal). Fixture-remap
    # means applying the BR1 10-champ roster onto a non-BR1 match.
    is_br1_roster = champs == BR1_IDENTITY_CHAMPS
    is_br1_match = "3264361042" in str(match_code)
    remap = is_br1_roster and not is_br1_match
    return {
        "winners": len(winners),
        "distinctChampions": len(champs),
        "isBr1Match": is_br1_match,
        "isBr1RosterRemap": remap,
        "br1NameOverlap": br1_overlap,
        "exclusive": len(winners) == 10 and len(champs) == 10 and not remap,
    }


def run_decode(
    *,
    rofl: Path,
    pe: Path,
    identity: Path = CASTSPELL_IDENTITY,
    match_code: str = MATCH_CODE,
    resilient: bool = False,
    prefer_opcode: Optional[int] = None,
    patch: str = "auto",
) -> Dict[str, Any]:
    t0 = time.perf_counter()
    binary = load_binary(pe)
    pe_patch = patch
    if pe_patch == "auto":
        pe_name = pe.name.lower()
        if "16.13" in pe_name:
            pe_patch = "16.13"
        elif "16.14" in pe_name:
            pe_patch = "16.14"
        else:
            pe_patch = "unknown"

    if prefer_opcode is None and pe_patch == "16.13":
        prefer_opcode = UPGRADE_SPELL_OPCODE_16_13

    reg = resolve_upgrade_opcode(binary, prefer_opcode=prefer_opcode)
    opcode = int(reg["opcode"])

    # Seed factory scan with the resolved opcode even when naive enumerate
    # misses resilient-only channels.
    naive_counts, _ = enumerate_rofl(rofl)
    scan_counts = dict(naive_counts or {})
    scan_counts[opcode] = max(int(scan_counts.get(opcode) or 0), 100)
    factories, coverage = scan_msvc_packet_types(binary, scan_counts)
    factory = next((r for r in factories if int(r["opcode"]) == opcode), None)
    if not factory:
        return {
            "ok": False,
            "schema": "rofl-upgrade-spell-ranks-v0",
            "probeVersion": PROBE_VERSION,
            "matchCode": match_code,
            "blocker": {
                "kind": "upgrade_spell_factory_missing",
                "detail": f"opcode {opcode} factory not recovered",
            },
            "abilityRanksTrusted": False,
            "productEligible": False,
        }

    blocks, walker = collect_upgrade_blocks(
        rofl, opcode, resilient=resilient
    )
    # Auto-fallback: if type1 walker empty and opcode is 16.13 path, retry resilient.
    if not blocks and not resilient:
        blocks, walker = collect_upgrade_blocks(rofl, opcode, resilient=True)
        walker = {**walker, "autoPromotedFromType1": True}

    events = decode_first_writes(
        binary=binary,
        factory=factory,
        opcode=opcode,
        blocks=blocks,
    )
    winners = load_identity_winners(identity)
    identity_meta = _identity_exclusive(winners, match_code=match_code)
    final_ranks, snapshots = build_cumulative_ranks(events)

    heroes_hit = {e["netId"] for e in events}
    slots_seen = {e["slot"] for e in events}
    levels_seen = {e["level"] for e in events}
    layout_counts: Dict[str, int] = defaultdict(int)
    for e in events:
        layout_counts[str(e.get("layoutId") or "unknown")] += 1

    by_hero: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
    for snap in snapshots:
        by_hero[int(snap["netId"])].append(snap)
    monotonic = True
    for _nid, seq in by_hero.items():
        last = [0, 0, 0, 0]
        for snap in seq:
            ranks_after = list(snap["ranksAfter"])
            if any(ranks_after[i] < last[i] for i in range(4)):
                monotonic = False
                break
            last = ranks_after
        if not monotonic:
            break

    skill_point_sum = sum(sum(final_ranks.get(nid, [0, 0, 0, 0])) for nid in PROVEN_HERO_NET_IDS)
    complete = (
        len(heroes_hit) == 10
        and slots_seen == {0, 1, 2, 3}
        and levels_seen >= {1, 2, 3}
        and 1 in levels_seen
        and monotonic
        and len(events) >= 50
        and len(winners) == 10
        and identity_meta["exclusive"]
        and skill_point_sum >= 50
    )
    wall_ms = (time.perf_counter() - t0) * 1000.0
    blocker = None
    if not complete:
        blocker = {
            "kind": "ability_ranks_incomplete",
            "detail": (
                f"UpgradeSpellAns decode produced {len(events)} events across "
                f"{len(heroes_hit)}/10 heroes; slots={sorted(slots_seen)} "
                f"levels={sorted(levels_seen)} monotonic={monotonic} "
                f"identityWinners={len(winners)} exclusive="
                f"{identity_meta['exclusive']} skillPointSum={skill_point_sum} "
                f"opcode={opcode} walker={walker.get('mode')}"
            ),
        }

    final_by_champ = {
        winners[nid]: {
            "netId": nid,
            "netIdHex": hex(nid),
            "ranks": final_ranks.get(nid, [0, 0, 0, 0]),
        }
        for nid in PROVEN_HERO_NET_IDS
        if nid in winners
    }

    primary_layout = (
        max(layout_counts.items(), key=lambda kv: kv[1])[0]
        if layout_counts
        else None
    )
    source_tag = (
        f"rofl2_upgrade_spell_ans_{opcode}_first_write"
        if complete
        else f"rofl2_upgrade_spell_ans_{opcode}_incomplete"
    )

    return {
        "ok": bool(complete),
        "schema": "rofl-upgrade-spell-ranks-v0",
        "probeVersion": PROBE_VERSION,
        "ts": utc_now_iso(),
        "matchCode": match_code,
        "wallMs": round(wall_ms, 3),
        "pkt": UPGRADE_SPELL_PKT,
        "opcode": opcode,
        "opcodeSource": reg.get("opcodeSource"),
        "registration": reg.get("registration"),
        "factory": {
            "opcode": opcode,
            "objectSize": factory.get("objectSize"),
            "deserializeVa": hex(int(factory["deserializeVa"])),
            "ctorVa": hex(int(factory["ctorVa"])),
            "vptr": hex(int(factory["vptr"])),
        },
        "fieldLayout": {
            "capture": "first_mem_write_before_cipher",
            "layouts": {
                "16.14": {
                    "levelOffset": LEVEL_OFFSET_16_14,
                    "slotOffset": SLOT_OFFSET_16_14,
                },
                "16.13": {
                    "slotOffset": SLOT_OFFSET_16_13,
                    "levelOffset": LEVEL_OFFSET_16_13,
                },
            },
            "layoutCounts": dict(layout_counts),
            "primaryLayout": primary_layout,
            "selection": (
                "prefer_16.14_level@0x10_slot@0x11_else_"
                "16.13_slot@0x12_level@0x13"
            ),
            "levelRange": [1, 5],
            "slotRange": [0, 3],
        },
        "walker": walker,
        "blockCount": len(blocks),
        "naiveEnumerateCount": int(naive_counts.get(opcode) or 0),
        "eventCount": len(events),
        "heroesHit": len(heroes_hit),
        "slotsSeen": sorted(slots_seen),
        "levelsSeen": sorted(levels_seen),
        "skillPointSum": skill_point_sum,
        "monotonic": monotonic,
        "identityPath": str(identity),
        "identityExclusive": identity_meta,
        "identityWinners": {hex(k): v for k, v in winners.items()},
        "finalRanksByChampion": final_by_champ,
        "eventsHead": events[:16],
        "events": events,
        "snapshots": snapshots,
        "abilityRanksSource": source_tag,
        "abilityRanksTrusted": bool(complete),
        "productEligible": bool(complete and identity_meta["exclusive"]),
        "blocker": blocker,
        "binaryManifest": research_manifest(
            binary, patch=pe_patch, extra={"probeVersion": PROBE_VERSION}
        ),
        "constructorCoverage": coverage,
        "note": (
            f"PKT_NPC_UpgradeSpellAns_s opcode {opcode} first-write decode; "
            "CastSpellAns remains identity-only; never fixture-remap ranks."
        ),
        "neverEditedParent": True,
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rofl", type=Path, default=DEFAULT_ROFL)
    ap.add_argument("--pe", type=Path, default=DEFAULT_PE)
    ap.add_argument("--identity", type=Path, default=CASTSPELL_IDENTITY)
    ap.add_argument("--match-code", type=str, default=MATCH_CODE)
    ap.add_argument("--json-out", type=Path, default=DEFAULT_OUT)
    ap.add_argument(
        "--resilient",
        action="store_true",
        help="Use extract_segments_resilient (required for pro 16.13 ROFL)",
    )
    ap.add_argument(
        "--prefer-opcode",
        type=int,
        default=None,
        help="Force UpgradeSpellAns opcode (1012 on 16.13, 636 on 16.14)",
    )
    ap.add_argument(
        "--patch",
        type=str,
        default="auto",
        help="PE patch label for manifest (auto|16.13|16.14)",
    )
    args = ap.parse_args(argv)
    if not args.rofl.is_file():
        print(f"missing ROFL {args.rofl}", file=sys.stderr)
        return 2
    if not args.pe.is_file():
        print(f"missing PE {args.pe}", file=sys.stderr)
        return 2
    report = run_decode(
        rofl=args.rofl,
        pe=args.pe,
        identity=args.identity,
        match_code=args.match_code,
        resilient=bool(args.resilient),
        prefer_opcode=args.prefer_opcode,
        patch=args.patch,
    )
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(
        json.dumps(report, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {args.json_out}")
    print(
        f"ok={report.get('ok')} events={report.get('eventCount')} "
        f"trusted={report.get('abilityRanksTrusted')} "
        f"opcode={report.get('opcode')} "
        f"blocker={(report.get('blocker') or {}).get('kind')}"
    )
    return 0 if report.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
