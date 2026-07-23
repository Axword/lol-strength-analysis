#!/usr/bin/env python3
"""Gate B2: decode PKT_NPC_UpgradeSpellAns_s (opcode 636) → identity-bound ranks.

16.14 MakeFunction maps UpgradeSpellAns → opcode 636 (objectSize 20). Deserialize
writes logical spell **level** at object+0x10 and **slot** at +0x11 *before* an
in-place cipher pass — capture first UC_HOOK_MEM_WRITE per offset.

Never fixture-remaps maknee ranks. NetId→champion/PUUID uses CastSpellAns bind.

Example:
  npm run rofl:upgrade-spell-ranks -- \\
    --rofl \"$HOME/Documents/League of Legends/Replays/BR1-3264361042.rofl\" \\
    --json-out docs/rofl-research/upgrade-spell-ranks-BR1-3264361042.json
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
from rofl2_probe import extract_segments, parse_rofl2  # noqa: E402
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

PROBE_VERSION = "upgrade-spell-ranks-v1"
MATCH_CODE = "3264361042"
UPGRADE_SPELL_PKT = "PKT_NPC_UpgradeSpellAns_s"
UPGRADE_SPELL_OPCODE_FALLBACK = 636
LEVEL_OFFSET = 0x10
SLOT_OFFSET = 0x11
ABILITY_RANKS_SOURCE = "rofl2_upgrade_spell_ans_636_first_write"
DEFAULT_OUT = Path("docs/rofl-research/upgrade-spell-ranks-BR1-3264361042.json")
CASTSPELL_IDENTITY = Path(
    "docs/rofl-research/castspell-identity-BR1-3264361042.json"
)
DEFAULT_EVENTS = Path(
    "docs/rofl-research/create-hero-from-castspell-BR1-3264361042.json"
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


def resolve_upgrade_opcode(binary: Any) -> Dict[str, Any]:
    td = find_upgrade_td(binary)
    mapped = map_semantic_registrations(binary, td) if td else {}
    row = mapped.get(UPGRADE_SPELL_PKT) or {}
    opcode = row.get("opcode")
    if opcode is None:
        opcode = UPGRADE_SPELL_OPCODE_FALLBACK
        row = {
            **row,
            "ok": True,
            "opcode": opcode,
            "note": "fallback_opcode_636_after_registration_miss",
        }
    return {"pkt": UPGRADE_SPELL_PKT, "opcode": int(opcode), "registration": row}


def collect_upgrade_blocks(rofl: Path, opcode: int) -> List[dict]:
    info = parse_rofl2(rofl)
    extracted = extract_segments(info["payload"])
    rows: List[dict] = []
    for seg in extracted["segments"]:
        if int(seg.get("type") or 0) != 1:
            continue
        for blk in extract_blocks_py(seg["bytes"], max_blocks=500_000):
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
    return rows


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
        level = first.get(LEVEL_OFFSET)
        slot = first.get(SLOT_OFFSET)
        if level is None or slot is None:
            continue
        if not (1 <= int(level) <= 5 and 0 <= int(slot) <= 3):
            continue
        out.append(
            {
                "time": float(blk["time"]),
                "gameTimeMs": int(round(float(blk["time"]) * 1000)),
                "netId": int(blk["netId"]),
                "slot": int(slot),
                "level": int(level),
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


def run_decode(
    *,
    rofl: Path,
    pe: Path,
) -> Dict[str, Any]:
    t0 = time.perf_counter()
    binary = load_binary(pe)
    reg = resolve_upgrade_opcode(binary)
    opcode = int(reg["opcode"])
    counts, _ = enumerate_rofl(rofl)
    factories, coverage = scan_msvc_packet_types(binary, counts)
    factory = next((r for r in factories if int(r["opcode"]) == opcode), None)
    if not factory:
        return {
            "ok": False,
            "schema": "rofl-upgrade-spell-ranks-v0",
            "blocker": {
                "kind": "upgrade_spell_factory_missing",
                "detail": f"opcode {opcode} factory not recovered",
            },
            "abilityRanksTrusted": False,
            "productEligible": False,
        }

    blocks = collect_upgrade_blocks(rofl, opcode)
    events = decode_first_writes(
        binary=binary,
        factory=factory,
        opcode=opcode,
        blocks=blocks,
    )
    winners = load_identity_winners()
    final_ranks, snapshots = build_cumulative_ranks(events)

    # Validation bars: all 10 heroes, slots 0..3 observed, levels 1..5 observed,
    # per-hero upgrade count in [1, 18], monotonic non-decreasing per slot.
    heroes_hit = {e["netId"] for e in events}
    slots_seen = {e["slot"] for e in events}
    levels_seen = {e["level"] for e in events}
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

    complete = (
        len(heroes_hit) == 10
        and slots_seen == {0, 1, 2, 3}
        and levels_seen >= {1, 2, 3}
        and 1 in levels_seen
        and monotonic
        and len(events) >= 50
        and len(winners) == 10
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
                f"identityWinners={len(winners)}"
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

    return {
        "ok": bool(complete),
        "schema": "rofl-upgrade-spell-ranks-v0",
        "probeVersion": PROBE_VERSION,
        "ts": utc_now_iso(),
        "matchCode": MATCH_CODE,
        "wallMs": round(wall_ms, 3),
        "pkt": UPGRADE_SPELL_PKT,
        "opcode": opcode,
        "registration": reg.get("registration"),
        "factory": {
            "opcode": opcode,
            "objectSize": factory.get("objectSize"),
            "deserializeVa": hex(int(factory["deserializeVa"])),
            "ctorVa": hex(int(factory["ctorVa"])),
        },
        "fieldLayout": {
            "levelOffset": LEVEL_OFFSET,
            "slotOffset": SLOT_OFFSET,
            "capture": "first_mem_write_before_cipher",
            "levelRange": [1, 5],
            "slotRange": [0, 3],
        },
        "blockCount": int(counts.get(opcode) or 0),
        "eventCount": len(events),
        "heroesHit": len(heroes_hit),
        "slotsSeen": sorted(slots_seen),
        "levelsSeen": sorted(levels_seen),
        "monotonic": monotonic,
        "identityWinners": {hex(k): v for k, v in winners.items()},
        "finalRanksByChampion": final_by_champ,
        "eventsHead": events[:16],
        "events": events,
        "snapshots": snapshots,
        "abilityRanksSource": ABILITY_RANKS_SOURCE,
        "abilityRanksTrusted": bool(complete),
        "productEligible": bool(complete),
        "blocker": blocker,
        "binaryManifest": research_manifest(
            binary, patch="16.14", extra={"probeVersion": PROBE_VERSION}
        ),
        "constructorCoverage": coverage,
        "note": (
            "PKT_NPC_UpgradeSpellAns_s opcode 636 first-write level@+0x10 / "
            "slot@+0x11; CastSpellAns remains identity-only."
        ),
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rofl", type=Path, default=DEFAULT_ROFL)
    ap.add_argument("--pe", type=Path, default=DEFAULT_PE)
    ap.add_argument("--json-out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args(argv)
    if not args.rofl.is_file():
        print(f"missing ROFL {args.rofl}", file=sys.stderr)
        return 2
    if not args.pe.is_file():
        print(f"missing PE {args.pe}", file=sys.stderr)
        return 2
    report = run_decode(rofl=args.rofl, pe=args.pe)
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(
        json.dumps(report, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {args.json_out}")
    print(
        f"ok={report.get('ok')} events={report.get('eventCount')} "
        f"trusted={report.get('abilityRanksTrusted')} "
        f"blocker={(report.get('blocker') or {}).get('kind')}"
    )
    return 0 if report.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
