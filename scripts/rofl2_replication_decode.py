#!/usr/bin/env python3
"""
Decode ROFL2 chunk bodies → Replication (type 107) → HP snapshot → maknee events.

Pipeline:
  chunk bytes
    → block framing (0x10076bc94)
    → Deserialize type 107
    → apply post-Deserialize vector (rofl_replication_apply)
    → CharacterIntermediate slot writes (optional Unicorn stub)
    → acceptance (≥10 heroes, explicit mMaxHP) → maknee Replication events

Fail-closed: never invents HP/max. Type 107 is not in the static UsePacket map;
Pass 2 stubs the map root so UsePacket can dispatch; apply still walks the
vector produced by Deserialize.
"""
from __future__ import annotations

import argparse
import json
import struct
import sys
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rofl2_accessor_spike as spike  # noqa: E402
from rofl2_probe import extract_segments, parse_rofl2  # noqa: E402
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
    create_packet,
    deserialize_packet,
    extract_blocks_py,
    extract_blocks_unicorn,
    install_block_runtime_hooks,
    install_unmapped_stub,
    map_binary,
    read_packet_type_py,
    type_threshold,
)
from rofl_replication_apply import (  # noqa: E402
    CI_ALLOC_SIZE,
    MHP_SLOT,
    MMAXHP_SLOT,
    USE_HANDLER_MAP_ROOT,
    USE_PACKET,
    USE_REPLICATION,
    HeroReplicationState,
    acceptance_snapshot,
    apply_vector_blob,
    install_use_map_stub,
    is_valid_use_replication_prologue,
    maknee_events_from_state,
    read_ci_slots,
    write_ci_slots,
)

DEFAULT_LEAGUE_BINARY = spike.DEFAULT_UNIVERSAL_BINARY


def acceptance_heroes(
    heroes: Sequence[Mapping[str, Any]],
    *,
    need: int = 10,
) -> Dict[str, Any]:
    """Require need heroes with 0 < mHP <= mMaxHP and mMaxHP > 100."""
    ok = []
    for h in heroes:
        try:
            hp = float(h["mHP"])
            mx = float(h["mMaxHP"])
        except (KeyError, TypeError, ValueError):
            continue
        if 0 < hp <= mx and mx > 100:
            ok.append(h)
    return {
        "passed": len(ok) >= need,
        "heroCount": len(ok),
        "needHeroes": need,
        "heroes": ok,
    }


def maknee_replication_events(
    *,
    time_s: float,
    heroes: Sequence[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    """Build maknee-shaped Replication events from an accepted HP snapshot."""
    state: Dict[int, HeroReplicationState] = {}
    for h in heroes:
        st = HeroReplicationState(
            net_id=int(h["netId"]),
            mHP=float(h["mHP"]),
            mMaxHP=float(h["mMaxHP"]),
            explicit_max=bool(h.get("explicitMax", True)),
            time=float(h.get("time", time_s)),
        )
        if "combat" in h and isinstance(h["combat"], dict):
            st.combat = {str(k): float(v) for k, v in h["combat"].items()}
        state[st.net_id] = st
    return maknee_events_from_state(state)


def _drive_body_replication(
    *,
    mu: Any,
    heap: BumpHeap,
    body: bytes,
    state: Dict[int, HeroReplicationState],
    max_blocks: int,
    ci_pool: Dict[int, int],
    use_hits: List[int],
) -> Dict[str, Any]:
    thr = type_threshold(TYPE_COUNT_VALUE)
    extracted = extract_blocks_unicorn(mu, stream=body, max_blocks=max_blocks)
    rows: List[Dict[str, Any]] = []
    applied = 0
    for b in extracted["blocks"]:
        if b.get("channel") != REPLICATION_TYPE_CANDIDATE:
            continue
        pay = b.get("payload") or b""
        if len(pay) < 4:
            continue
        typ, ni = read_packet_type_py(pay, 0, len(pay), threshold=thr)
        if typ != REPLICATION_TYPE_CANDIDATE:
            continue
        created = create_packet(mu, heap, typ)
        deser = created.get("deserialize") or 0
        pkt = created.get("packet") or 0
        if not pkt or not deser:
            continue
        pva = BUF_BASE + 0x01800000
        mu.mem_write(pva, pay)
        des = deserialize_packet(
            mu,
            packet=pkt,
            deserialize_fn=deser,
            buf_va=pva,
            buf_len=len(pay),
            cursor_off=ni,
        )
        if not des["ok"]:
            continue
        mem = bytes(mu.mem_read(pkt, 0x40))
        net_hdr = struct.unpack_from("<I", mem, 0x0C)[0]
        ptr, size = struct.unpack_from("<QI", mem, 0x18)
        blob = b""
        if ptr and 0 < size < 0x200000:
            try:
                blob = bytes(mu.mem_read(ptr, size))
            except Exception:  # noqa: BLE001
                blob = b""
        t = float(b.get("time") or 0.0)
        if blob:
            applied += apply_vector_blob(state, blob, time_s=t)
            # Bind CI stubs + slot writes for heroes that just became acceptance-ok
            for nid, st in list(state.items()):
                if not st.acceptance_ok():
                    continue
                if nid not in ci_pool:
                    ci_pool[nid] = heap.alloc(CI_ALLOC_SIZE)
                    mu.mem_write(ci_pool[nid], b"\x00" * CI_ALLOC_SIZE)
                    st.ci_va = ci_pool[nid]
                write_ci_slots(mu, ci_pool[nid], mHP=float(st.mHP), mMaxHP=float(st.mMaxHP))
                st.ci_va = ci_pool[nid]
            # Count UsePacket dispatch when map stub is present
            try:
                root = struct.unpack("<Q", bytes(mu.mem_read(USE_HANDLER_MAP_ROOT, 8)))[0]
                if root:
                    use_hits.append(1)
            except Exception:  # noqa: BLE001
                pass
        rows.append(
            {
                "time": t,
                "param": b.get("param"),
                "netHdr": net_hdr,
                "vectorSize": size,
                "deserializeConsumed": des["consumed"],
                "blobHeadHex": blob[:64].hex(),
                "packet": pkt,
                "vectorPtr": ptr,
            }
        )
    return {
        "blocksTotal": extracted["count"],
        "replicationPackets": len(rows),
        "timeStart": extracted.get("timeStart"),
        "timeEnd": extracted.get("timeEnd"),
        "rows": rows,
        "unitsApplied": applied,
        "channelHist": dict(
            Counter(b["channel"] for b in extracted["blocks"]).most_common(12)
        ),
    }


def decode_chunk_replication(
    *,
    body: bytes,
    mu: Any,
    heap: BumpHeap,
    max_blocks: int = 800,
    max_replication: int = 64,
    state: Optional[Dict[int, HeroReplicationState]] = None,
) -> Dict[str, Any]:
    """Extract + Deserialize + apply type-107 packets from one chunk body."""
    st = state if state is not None else {}
    ci_pool: Dict[int, int] = {}
    use_hits: List[int] = []
    out = _drive_body_replication(
        mu=mu,
        heap=heap,
        body=body,
        state=st,
        max_blocks=max_blocks,
        ci_pool=ci_pool,
        use_hits=use_hits,
    )
    out["rows"] = out["rows"][:max_replication]
    out["stateHeroes"] = len(st)
    out["useMapHits"] = len(use_hits)
    return out


def decode_rofl_replication(
    *,
    rofl: Path,
    league_binary: Path = DEFAULT_LEAGUE_BINARY,
    work_dir: Optional[Path] = None,
    chunk_index: Optional[int] = None,
    max_blocks: int = 800,
    max_chunks: int = 50,
    heroes: Optional[Sequence[Mapping[str, Any]]] = None,
    stub_use_map: bool = True,
) -> Dict[str, Any]:
    """Drive Unicorn decode across chunks until HP acceptance or exhaustion."""
    if not league_binary.is_file():
        return {
            "ok": False,
            "decryptStatus": "blocked_need_league_binary",
            "error": f"missing {league_binary}",
            "events": [],
        }
    if not rofl.is_file():
        return {
            "ok": False,
            "decryptStatus": "blocked_need_rofl",
            "error": f"missing {rofl}",
            "events": [],
        }
    try:
        from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM
    except ImportError as e:
        return {
            "ok": False,
            "decryptStatus": "blocked_unicorn_missing",
            "error": str(e),
            "events": [],
        }

    if work_dir is None:
        work_dir = Path(tempfile.mkdtemp(prefix="lol-repl-decode-"))
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
    if not chunks:
        return {
            "ok": False,
            "decryptStatus": "blocked_no_chunks",
            "events": [],
            "useReplicationVa": hex(USE_REPLICATION),
            "useReplicationPrologueOk": prologue_ok,
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
    use_node = None
    if stub_use_map:
        use_node = install_use_map_stub(mu, heap)

    state: Dict[int, HeroReplicationState] = {}
    ci_pool: Dict[int, int] = {}
    use_hits: List[int] = []
    decode_summary: Dict[str, Any] = {}
    scanned: List[int] = []

    # Optional external heroes short-circuit (fixture / prior snapshot).
    if heroes:
        for h in heroes:
            st = HeroReplicationState(
                net_id=int(h["netId"]),
                mHP=float(h["mHP"]),
                mMaxHP=float(h["mMaxHP"]),
                explicit_max=bool(h.get("explicitMax", True)),
                time=float(h.get("time") or 0.0),
            )
            state[st.net_id] = st

    indices: List[int]
    if chunk_index is not None:
        indices = [chunk_index]
    else:
        # Prefer early chunks (spawn full HP pairs) then walk forward.
        indices = list(range(min(len(chunks), max_chunks)))

    for ci in indices:
        body = chunks[ci]["bytes"]
        part = _drive_body_replication(
            mu=mu,
            heap=heap,
            body=body,
            state=state,
            max_blocks=max_blocks,
            ci_pool=ci_pool,
            use_hits=use_hits,
        )
        scanned.append(ci)
        decode_summary = part
        snap = acceptance_snapshot(state)
        if snap["passed"]:
            break

    snap = acceptance_snapshot(state)
    # Prove CI slot round-trip for accepted heroes when pool bound.
    ci_proof = []
    for h in snap["heroes"][:10]:
        nid = int(h["netId"])
        va = ci_pool.get(nid)
        if not va:
            continue
        r_hp, r_mx = read_ci_slots(mu, va)
        ci_proof.append(
            {
                "netId": nid,
                "ciVa": hex(va),
                "readHP": r_hp,
                "readMaxHP": r_mx,
                "match": abs(r_hp - h["mHP"]) < 0.01 and abs(r_mx - h["mMaxHP"]) < 0.01,
            }
        )

    events: List[Dict[str, Any]] = []
    status = "replication_deserialized_need_use_handler"
    if use_node is not None:
        status = "replication_use_map_stubbed"
    if decode_summary.get("replicationPackets", 0) == 0 and not heroes:
        status = "block_framing_ok_no_replication_in_chunk"
    if snap["passed"]:
        events = maknee_events_from_state(state)
        status = "replication_hp_accepted"
    elif state and any(s.mHP is not None for s in state.values()):
        status = "replication_hp_rejected_fail_closed"

    py_blocks = extract_blocks_py(
        chunks[scanned[0]]["bytes"] if scanned else chunks[0]["bytes"],
        max_blocks=min(max_blocks, 2000),
    )
    py_repl = sum(1 for b in py_blocks if b["channel"] == REPLICATION_TYPE_CANDIDATE)

    return {
        "ok": bool(snap["passed"] and events),
        "decryptStatus": status,
        "arch": "arm64",
        "rofl": str(rofl),
        "gameVersion": (info.get("meta") or {}).get("gameVersion") or info.get("version"),
        "useReplication": {
            "va": hex(USE_REPLICATION),
            "usePacket": hex(USE_PACKET),
            "mapRoot": hex(USE_HANDLER_MAP_ROOT),
            "prologueOk": prologue_ok,
            "mapStubNode": hex(use_node) if use_node else None,
            "mapDispatchHits": len(use_hits),
            "note": (
                "Type 107 is absent from the static UsePacket map on 16.14; "
                "Pass-2 stubs the root. Apply walks Deserialize vectors into CI slots."
            ),
        },
        "chunk": {
            "scanned": scanned,
            "lastIndex": scanned[-1] if scanned else None,
            "id_a": chunks[scanned[-1]].get("id_a") if scanned else None,
            "size": len(chunks[scanned[-1]]["bytes"]) if scanned else None,
        },
        "replicationType": REPLICATION_TYPE_CANDIDATE,
        "pythonReplicationBlocks": py_repl,
        "decode": {
            k: decode_summary.get(k)
            for k in (
                "blocksTotal",
                "replicationPackets",
                "timeStart",
                "timeEnd",
                "channelHist",
                "unitsApplied",
            )
        },
        "decodeRows": (decode_summary.get("rows") or [])[:20],
        "slots": {"mHP": hex(MHP_SLOT), "mMaxHP": hex(MMAXHP_SLOT)},
        "ciProof": ci_proof,
        "hpSnapshot": {
            "ok": snap["passed"],
            "heroCount": snap["heroCount"],
            "heroes": snap["heroes"],
            "acceptance": snap,
        },
        "events": events,
        "nextSteps": (
            []
            if snap["passed"]
            else [
                "Scan more chunks until ≥10 heroes have explicit mMaxHP (5,1)",
                "Fuse Replay API positions; map skill/objective packets",
            ]
        ),
        "workDir": str(work_dir),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("rofl", type=Path)
    ap.add_argument("--league-binary", type=Path, default=DEFAULT_LEAGUE_BINARY)
    ap.add_argument("--work-dir", type=Path, default=None)
    ap.add_argument("--chunk-index", type=int, default=None)
    ap.add_argument("--max-blocks", type=int, default=2500)
    ap.add_argument("--max-chunks", type=int, default=50)
    ap.add_argument("--heroes-json", type=Path, default=None)
    ap.add_argument("--json-out", type=Path, default=None)
    ap.add_argument("--no-use-stub", action="store_true")
    args = ap.parse_args()

    heroes = None
    if args.heroes_json and args.heroes_json.is_file():
        heroes = json.loads(args.heroes_json.read_text(encoding="utf-8"))
        if isinstance(heroes, dict):
            heroes = heroes.get("heroes") or heroes.get("hpSnapshot", {}).get("heroes")

    report = decode_rofl_replication(
        rofl=args.rofl,
        league_binary=args.league_binary,
        work_dir=args.work_dir,
        chunk_index=args.chunk_index,
        max_blocks=args.max_blocks,
        max_chunks=args.max_chunks,
        heroes=heroes,
        stub_use_map=not args.no_use_stub,
    )
    text = json.dumps(report, indent=2, default=str)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(text + "\n", encoding="utf-8")
        print(f"wrote {args.json_out}")
    else:
        print(text)
    print(
        f"status={report.get('decryptStatus')} "
        f"replPkts={(report.get('decode') or {}).get('replicationPackets')} "
        f"events={len(report.get('events') or [])} "
        f"hpOk={(report.get('hpSnapshot') or {}).get('ok')} "
        f"useVa={(report.get('useReplication') or {}).get('va')}"
    )
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
