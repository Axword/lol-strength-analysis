#!/usr/bin/env python3
"""Phase B E5: structural MOVEMENT_PATH discovery (ROFL-X MIT prior art).

Hypothesis: 16.14 arm64 movement is a factory class with ROFL-X layout —
object size ~48, decoded payload pointer at +0x18 and byte size at +0x20 —
then PathPacket (u16 flags/count, u32 id, f32 speed, compressed coords).

Citation (facts only; no code copy):
  Toastaspiring/ROFL-X (MIT) documents MOVEMENT_PATH on patches 15.1–15.5
  with that object layout; 15.5 opcode example 980; 16.8 sample flags 982 as
  a high-frequency candidate with unresolved decoder config.

Method: enumerate observed opcodes → factory size/vtable/Deserialize/Use →
score Deserialize bodies for pointer+size signature (penalize vector strides)
→ hook discovered alloc helpers → PathPacket + oracle on decoded entity id.

No live Replay API, no arbitrary byte brute force, no unlicensed vendoring.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
import tempfile
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rofl2_probe import extract_segments, parse_rofl2  # noqa: E402
from rofl2_unicorn_packet_drive import (  # noqa: E402
    ALLOCATOR,
    ALLOC_SIZE,
    ARENA_BASE,
    BUF_BASE,
    BUF_SIZE,
    DEFAULT_LEAGUE_BINARY,
    FREE_FN,
    HEAP_BASE,
    HEAP_SIZE,
    MEMCPY_FN,
    MEMSET_FN,
    SCRATCH,
    STACK_BASE,
    STACK_SIZE,
    TYPE_COUNT_GLOBAL,
    TYPE_COUNT_VALUE,
    BumpHeap,
    create_packet,
    deserialize_packet,
    extract_blocks_py,
    install_block_runtime_hooks,
    install_unmapped_stub,
    map_binary,
)
from rofl2_movement_decode import (  # noqa: E402
    DEFAULT_LOG,
    PROVENANCE,
    _load_oracle_positions,
    append_speed_record,
)
from rofl2_movement_emulator_probe import (  # noqa: E402
    PathParseError,
    parse_compressed_path_packet,
    scan_ptr_len_buffers,
)
from rofl2_movement_wire_scan import (  # noqa: E402
    ACCEPT_MAX_MAX_ERROR,
    ACCEPT_MAX_MEDIAN_ERROR,
    ACCEPT_MAX_P95_ERROR,
    ACCEPT_MIN_COMPARED_SAMPLES,
    ACCEPT_MIN_STABLE_ENTITIES,
    PROVEN_HERO_NET_ID_SET,
    optimal_oracle_assignment,
)
from rofl_speed_bench import utc_now_iso  # noqa: E402

try:
    import rofl2_accessor_spike as spike
except Exception:  # noqa: BLE001
    spike = None  # type: ignore

PROBE_VERSION = "e5-structural-roflx-v1"
ROFLX_OBJECT_SIZE = 48
PTR_OFF = 0x18
SIZE_OFF = 0x20
# Game allocator used by vector growth on this build (derived from call sites).
VECTOR_ALLOC_VA = 0x10162EB4C
VECTOR_FREE_VA = 0x10162EBAC


def _setup_unicorn(league_binary: Path, work_dir: Path):
    if spike is None:
        raise RuntimeError("rofl2_accessor_spike unavailable")
    from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM

    work_dir.mkdir(parents=True, exist_ok=True)
    arm64_path = work_dir / "LeagueofLegends.arm64"
    spike.thin_arm64(Path(league_binary), arm64_path)
    data = arm64_path.read_bytes()
    segments = spike._parse_segments(data)
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
    return mu, heap


def install_vector_allocator_hooks(mu: Any, heap: BumpHeap) -> List[str]:
    """Hook arm64 helpers seen at ROFL-X-like +0x18 growth sites."""
    from unicorn import UC_HOOK_CODE
    from unicorn.arm64_const import (
        UC_ARM64_REG_LR,
        UC_ARM64_REG_PC,
        UC_ARM64_REG_X0,
        UC_ARM64_REG_X1,
    )

    installed: List[str] = []

    def on_alloc(uc: Any, address: int, size: int, user: Any) -> None:
        a0 = uc.reg_read(UC_ARM64_REG_X0)
        a1 = uc.reg_read(UC_ARM64_REG_X1)
        req = None
        if 1 <= a0 <= 0x100000:
            req = int(a0)
        elif HEAP_BASE <= a0 < HEAP_BASE + HEAP_SIZE and 1 <= a1 <= 0x100000:
            req = int(a1)
        if req is None:
            return
        p = heap.alloc(req)
        try:
            uc.mem_write(p, b"\x00" * req)
        except Exception:  # noqa: BLE001
            pass
        uc.reg_write(UC_ARM64_REG_X0, p)
        uc.reg_write(UC_ARM64_REG_PC, uc.reg_read(UC_ARM64_REG_LR))

    def on_free(uc: Any, address: int, size: int, user: Any) -> None:
        uc.reg_write(UC_ARM64_REG_PC, uc.reg_read(UC_ARM64_REG_LR))

    for va, cb, name in (
        (VECTOR_ALLOC_VA, on_alloc, "vector_alloc"),
        (VECTOR_FREE_VA, on_free, "vector_free"),
    ):
        mu.hook_add(UC_HOOK_CODE, cb, begin=va, end=va)
        installed.append(f"{name}@{hex(va)}")
    return installed


def enumerate_opcode_blocks(rofl: Path) -> Tuple[Counter, Dict[int, List[dict]]]:
    info = parse_rofl2(rofl)
    extracted = extract_segments(info["payload"])
    counts: Counter = Counter()
    samples: Dict[int, List[dict]] = defaultdict(list)
    for seg in extracted["segments"]:
        if int(seg.get("type") or 0) != 1:
            continue
        for b in extract_blocks_py(seg["bytes"], max_blocks=500_000):
            op = int(b["channel"])
            counts[op] += 1
            pay = b["payload"] or b""
            if len(samples[op]) < 40 and 60.0 <= float(b["time"]) <= 1200.0:
                samples[op].append(
                    {
                        "time": float(b["time"]),
                        "param": int(b.get("param") or 0),
                        "payload": pay,
                    }
                )
    return counts, samples


def factory_scan(mu: Any, heap: BumpHeap, opcodes: Sequence[int]) -> List[dict]:
    rows = []
    for op in opcodes:
        created = create_packet(mu, heap, int(op))
        pkt = created.get("packet") or 0
        vtable = created.get("vtable") or 0
        deser = created.get("deserialize") or 0
        use = None
        if vtable:
            try:
                use = struct.unpack("<Q", bytes(mu.mem_read(vtable + 16, 8)))[0]
            except Exception:  # noqa: BLE001
                use = None
        rows.append(
            {
                "opcode": int(op),
                "ok": bool(pkt and deser),
                "heapDelta": int(created.get("heapDelta") or 0),
                "storedType": created.get("storedType"),
                "vtable": hex(vtable) if vtable else None,
                "deserialize": hex(deser) if deser else None,
                "deserializeVa": int(deser) if deser else 0,
                "usePacket": hex(use) if use else None,
            }
        )
    return rows


def group_by_deserialize(factory_rows: Sequence[Mapping[str, Any]]) -> Dict[str, List[dict]]:
    g: Dict[str, List[dict]] = defaultdict(list)
    for r in factory_rows:
        key = str(r.get("deserialize") or "none")
        g[key].append(dict(r))
    return dict(g)


def score_deserialize_signature(mu: Any, deser_va: int, *, max_depth: int = 2) -> dict:
    """Score ROFL-X pointer(+0x18)+size(+0x20) signature; penalize 0x18-stride vectors."""
    from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM

    md = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
    seen: Set[int] = set()

    def walk(va: int, depth: int) -> dict:
        if va in seen or depth > max_depth or not va:
            return {
                "str_x_18": 0,
                "str_w_20": 0,
                "stride18": 0,
                "alloc_then_str_x18": 0,
                "bl": [],
            }
        seen.add(va)
        acc = {
            "str_x_18": 0,
            "str_w_20": 0,
            "stride18": 0,
            "alloc_then_str_x18": 0,
            "bl": [],
        }
        try:
            code = bytes(mu.mem_read(va, 0x500))
        except Exception:  # noqa: BLE001
            return acc
        insns = list(md.disasm(code, va))
        for i, insn in enumerate(insns):
            m, o = insn.mnemonic, insn.op_str
            if m in ("str", "stur") and o.startswith("x") and "#0x18" in o:
                # x0 or other — count pointer-width stores to +0x18
                if o.split(",")[0].strip().startswith("x"):
                    acc["str_x_18"] += 1
            if (m in ("str", "stur") and o.startswith("w") and "#0x20" in o) or (
                m == "stp" and "#0x20" in o and o.strip().startswith("w")
            ):
                acc["str_w_20"] += 1
            if (m in ("umaddl", "madd") and "#0x18" in o) or (
                m == "mov" and o.endswith("#0x18")
            ):
                acc["stride18"] += 1
            if m == "bl":
                try:
                    tgt = int(o.replace("#", ""), 16)
                    acc["bl"].append(tgt)
                except ValueError:
                    pass
                # alloc → str x0,[reg,#0x18] within next 12 insns
                is_alloc = tgt in (
                    ALLOCATOR,
                    ALLOC_SIZE,
                    VECTOR_ALLOC_VA,
                    0x101F31B28,
                )
                if is_alloc:
                    for j in range(i + 1, min(i + 14, len(insns))):
                        nxt = insns[j]
                        if nxt.mnemonic in ("str", "stur") and nxt.op_str.startswith(
                            "x0,"
                        ):
                            if "#0x18" in nxt.op_str:
                                acc["alloc_then_str_x18"] += 1
                                break
                        if nxt.mnemonic == "bl":
                            break
            if m == "ret" and i > 12:
                break
            if i >= 220:
                break
        if depth < max_depth:
            for tgt in acc["bl"][:8]:
                if 0x101000000 <= tgt <= 0x102000000:
                    ch = walk(tgt, depth + 1)
                    for k in (
                        "str_x_18",
                        "str_w_20",
                        "stride18",
                        "alloc_then_str_x18",
                    ):
                        acc[k] += ch[k]
        return acc

    raw = walk(int(deser_va), 0)
    score = 0
    if raw["str_x_18"] > 0:
        score += 4
    if raw["str_w_20"] > 0:
        score += 4
    if raw["alloc_then_str_x18"] > 0:
        score += 5
    if raw["stride18"] > 0:
        score -= 6
    byte_buffer = (
        raw["str_x_18"] > 0
        and raw["str_w_20"] > 0
        and raw["stride18"] == 0
        and raw["alloc_then_str_x18"] > 0
    )
    # Weaker: stores without proven alloc-then-store (often scalar false positives)
    weak = raw["str_x_18"] > 0 and raw["str_w_20"] > 0 and raw["stride18"] == 0
    return {
        **raw,
        "score": score,
        "byteBufferCandidate": bool(byte_buffer),
        "weakByteBufferShape": bool(weak and not byte_buffer),
        "vectorStrideRejected": raw["stride18"] > 0 and raw["alloc_then_str_x18"] > 0,
    }


def false_positive_signature_fixture() -> dict:
    """Synthetic disasm-like feature bag that must not pass as MOVEMENT_PATH."""
    # Scalar stores / float at #0x18 without alloc→ptr.
    return {
        "str_x_18": 0,
        "str_w_20": 1,
        "stride18": 0,
        "alloc_then_str_x18": 0,
        "score": 4,
        "byteBufferCandidate": False,
        "weakByteBufferShape": False,
        "vectorStrideRejected": False,
    }


def score_from_features(features: Mapping[str, Any]) -> dict:
    """Pure scoring used by tests (no Capstone)."""
    raw = {
        "str_x_18": int(features.get("str_x_18") or 0),
        "str_w_20": int(features.get("str_w_20") or 0),
        "stride18": int(features.get("stride18") or 0),
        "alloc_then_str_x18": int(features.get("alloc_then_str_x18") or 0),
    }
    score = 0
    if raw["str_x_18"] > 0:
        score += 4
    if raw["str_w_20"] > 0:
        score += 4
    if raw["alloc_then_str_x18"] > 0:
        score += 5
    if raw["stride18"] > 0:
        score -= 6
    byte_buffer = (
        raw["str_x_18"] > 0
        and raw["str_w_20"] > 0
        and raw["stride18"] == 0
        and raw["alloc_then_str_x18"] > 0
    )
    weak = raw["str_x_18"] > 0 and raw["str_w_20"] > 0 and raw["stride18"] == 0
    return {
        **raw,
        "score": score,
        "byteBufferCandidate": bool(byte_buffer),
        "weakByteBufferShape": bool(weak and not byte_buffer),
        "vectorStrideRejected": raw["stride18"] > 0 and raw["alloc_then_str_x18"] > 0,
    }


def probe_candidate_runtime(
    mu: Any,
    heap: BumpHeap,
    *,
    opcode: int,
    samples: Sequence[Mapping[str, Any]],
    max_samples: int = 25,
) -> dict:
    path_hits: List[dict] = []
    heap_ptr_hits = 0
    ok_n = 0
    examples = []
    for s in list(samples)[:max_samples]:
        created = create_packet(mu, heap, int(opcode))
        pkt = created.get("packet") or 0
        deser = created.get("deserialize") or 0
        if not pkt or not deser:
            continue
        pay = s["payload"]
        pva = BUF_BASE + 0x01800000
        if len(pay) > BUF_SIZE - 0x01800000:
            continue
        mu.mem_write(pva, pay)
        before = len(heap.allocs)
        des = deserialize_packet(
            mu,
            packet=pkt,
            deserialize_fn=deser,
            buf_va=pva,
            buf_len=len(pay),
            cursor_off=0,
        )
        if des.get("ok"):
            ok_n += 1
        after = bytes(mu.mem_read(pkt, 0x40))
        ptr = struct.unpack_from("<Q", after, PTR_OFF)[0]
        sz = struct.unpack_from("<I", after, SIZE_OFF)[0]
        new_allocs = heap.allocs[before:]
        cands: List[bytes] = []
        if HEAP_BASE <= ptr < HEAP_BASE + HEAP_SIZE and 8 <= sz <= 0x10000:
            heap_ptr_hits += 1
            try:
                cands.append(bytes(mu.mem_read(ptr, sz)))
            except Exception:  # noqa: BLE001
                pass
        for base, n in new_allocs:
            if 8 <= n <= 0x8000:
                try:
                    cands.append(bytes(mu.mem_read(base, n)))
                except Exception:  # noqa: BLE001
                    pass
        for buf in scan_ptr_len_buffers(
            after,
            heap_allocs=heap.allocs[-40:],
            read_mem=lambda p, n: bytes(mu.mem_read(p, n)),
        ):
            if buf.get("buffer"):
                cands.append(buf["buffer"])
        got = None
        for cand in cands:
            try:
                pp = parse_compressed_path_packet(cand)
            except PathParseError:
                continue
            if not pp.full_consume:
                continue
            if not (50.0 <= pp.speed <= 2000.0):
                continue
            got = pp
            path_hits.append(
                {
                    "time": float(s["time"]),
                    "netId": int(pp.entity_id),
                    "x": pp.waypoints[0][0],
                    "z": pp.waypoints[0][1],
                    "points": [{"x": x, "z": z} for x, z in pp.waypoints],
                    "speed": pp.speed,
                    "hero": int(pp.entity_id) in PROVEN_HERO_NET_ID_SET,
                }
            )
            break
        if len(examples) < 4:
            examples.append(
                {
                    "time": round(float(s["time"]), 3),
                    "payloadLen": len(pay),
                    "ok": bool(des.get("ok")),
                    "consumed": des.get("consumed"),
                    "ptr18": hex(ptr),
                    "size20": sz,
                    "newAllocs": [{"ptr": hex(p), "size": n} for p, n in new_allocs[:4]],
                    "path": None
                    if got is None
                    else {
                        "entityId": hex(got.entity_id),
                        "speed": got.speed,
                        "waypoints": len(got.waypoints),
                    },
                }
            )
    return {
        "opcode": opcode,
        "samplesTried": min(max_samples, len(samples)),
        "deserializeOk": ok_n,
        "heapPtrAt18": heap_ptr_hits,
        "pathFullConsume": len(path_hits),
        "heroPathCount": sum(1 for p in path_hits if p["hero"]),
        "pathSamples": path_hits,
        "examples": examples,
    }


def run_e5_scan(
    rofl: Path,
    *,
    oracle_jsonl: Path,
    league_binary: Path = DEFAULT_LEAGUE_BINARY,
    work_dir: Optional[Path] = None,
    max_runtime_samples: int = 25,
) -> dict:
    t0 = time.perf_counter()
    if work_dir is None:
        work_dir = Path(tempfile.mkdtemp(prefix="lol-e5-scan-"))
    mu, heap = _setup_unicorn(Path(league_binary), Path(work_dir))
    extra_hooks = install_vector_allocator_hooks(mu, heap)
    counts, samples = enumerate_opcode_blocks(rofl)
    opcodes = sorted(counts)
    factory_rows = factory_scan(mu, heap, opcodes)
    for r in factory_rows:
        r["blockCount"] = int(counts.get(int(r["opcode"]), 0))

    size_hist = Counter(int(r["heapDelta"]) for r in factory_rows if r["ok"])
    size48 = [r for r in factory_rows if r["ok"] and int(r["heapDelta"]) == ROFLX_OBJECT_SIZE]
    deser_groups = group_by_deserialize(size48)

    # Score size-48 first
    scored48 = []
    for r in size48:
        sig = score_deserialize_signature(mu, int(r["deserializeVa"]))
        scored48.append({**r, "signature": sig})
    scored48.sort(
        key=lambda x: (
            -int(x["signature"]["byteBufferCandidate"]),
            -int(x["signature"]["score"]),
            -int(x["blockCount"]),
        )
    )

    # Extend to any size with strong byte-buffer signature (alloc→ptr+size, no stride)
    extended = []
    for r in factory_rows:
        if not r["ok"]:
            continue
        if int(r["heapDelta"]) == ROFLX_OBJECT_SIZE:
            continue
        sig = score_deserialize_signature(mu, int(r["deserializeVa"]))
        if sig["byteBufferCandidate"] or sig["alloc_then_str_x18"] > 0:
            extended.append({**r, "signature": sig})
    extended.sort(
        key=lambda x: (-int(x["signature"]["byteBufferCandidate"]), -x["blockCount"])
    )

    # Runtime probe: strong size-48 + extended strong + top weak size-48 for evidence
    runtime_targets = []
    for r in scored48:
        sig = r["signature"]
        if sig["byteBufferCandidate"] or sig["vectorStrideRejected"] or sig["alloc_then_str_x18"]:
            runtime_targets.append(r)
    for r in extended[:8]:
        runtime_targets.append(r)
    # Also include a few weak shapes (document false positives)
    for r in scored48:
        if r["signature"]["weakByteBufferShape"] and r not in runtime_targets:
            runtime_targets.append(r)
        if len([t for t in runtime_targets if t["signature"].get("weakByteBufferShape")]) >= 5:
            break

    # Dedup by opcode
    seen_ops = set()
    uniq_targets = []
    for r in runtime_targets:
        op = int(r["opcode"])
        if op in seen_ops:
            continue
        seen_ops.add(op)
        uniq_targets.append(r)

    oracle = _load_oracle_positions(oracle_jsonl) if oracle_jsonl.is_file() else []
    runtime_reports = []
    winner = None
    for r in uniq_targets[:20]:
        op = int(r["opcode"])
        rt = probe_candidate_runtime(
            mu,
            heap,
            opcode=op,
            samples=samples.get(op) or [],
            max_samples=max_runtime_samples,
        )
        rt["heapDelta"] = r["heapDelta"]
        rt["signature"] = r["signature"]
        rt["deserialize"] = r["deserialize"]
        oracle_qa = None
        accepted = False
        if rt["pathSamples"] and oracle:
            oracle_qa = optimal_oracle_assignment(
                rt["pathSamples"], oracle, tolerance_s=0.5
            )
            accepted = bool(
                oracle_qa.get("methodPassed")
                and int(oracle_qa.get("assignmentCount") or 0)
                >= ACCEPT_MIN_STABLE_ENTITIES
                and int(oracle_qa.get("comparedSamples") or 0)
                >= ACCEPT_MIN_COMPARED_SAMPLES
                and float(oracle_qa.get("medianError") or 1e9) <= ACCEPT_MAX_MEDIAN_ERROR
                and float(oracle_qa.get("p95Error") or 1e9) <= ACCEPT_MAX_P95_ERROR
                and float(oracle_qa.get("maxError") or 1e9) <= ACCEPT_MAX_MAX_ERROR
            )
        rt["oracleQa"] = (
            {
                k: (oracle_qa or {}).get(k)
                for k in (
                    "assignmentCount",
                    "comparedSamples",
                    "medianError",
                    "p95Error",
                    "maxError",
                    "methodPassed",
                    "productEligible",
                )
            }
            if oracle_qa
            else None
        )
        rt["accepted"] = accepted
        # Drop bulky path samples from disk report except counts
        slim = dict(rt)
        slim["pathSamples"] = rt["pathSamples"][:3]
        runtime_reports.append(slim)
        if accepted and winner is None:
            winner = rt

    # Historical opcode notes
    prior_ops = {
        "roflx_15_5_example": 980,
        "roflx_16_8_candidate": 982,
        "public_025b": 0x025B,
    }
    prior_present = {
        name: {"opcode": op, "blockCount": int(counts.get(op, 0))}
        for name, op in prior_ops.items()
    }

    wall_ms = (time.perf_counter() - t0) * 1000
    # Exact structural blocker summary
    strong_byte = [r for r in scored48 if r["signature"]["byteBufferCandidate"]]
    vectorish = [r for r in scored48 if r["signature"]["vectorStrideRejected"]]
    blocker = None
    if winner is None:
        blocker = {
            "kind": "no_roflx_byte_buffer_movement_class",
            "detail": (
                "Among observed opcodes, no Deserialize both (1) matches ROFL-X "
                "byte-buffer pointer@+0x18 + size@+0x20 with alloc→store and "
                "(2) materializes a PathPacket-full-consume buffer under hooked "
                "allocators. Closest size-48 alloc→+0x18 hit is a 0x18-stride "
                "element vector (not a PathPacket byte payload)."
            ),
            "closestOpcode": (vectorish[0]["opcode"] if vectorish else None),
            "closestDeserialize": (vectorish[0]["deserialize"] if vectorish else None),
            "size48ClassCount": len(size48),
            "strongByteBufferSize48": len(strong_byte),
            "vectorStrideSize48": [
                {"opcode": r["opcode"], "deserialize": r["deserialize"], "blocks": r["blockCount"]}
                for r in vectorish[:5]
            ],
            "priorArtOpcodesAbsent": [
                k for k, v in prior_present.items() if v["blockCount"] == 0
            ],
        }

    return {
        "ok": True,
        "phase": "B-E5",
        "probeVersion": PROBE_VERSION,
        "provenance": PROVENANCE,
        "attribution": {
            "roflX": "Toastaspiring/ROFL-X (MIT) — MOVEMENT_PATH layout facts only; no code copied",
            "layoutPrior": {
                "objectSize": ROFLX_OBJECT_SIZE,
                "payloadPtrOff": PTR_OFF,
                "payloadSizeOff": SIZE_OFF,
                "parser": "PathPacket compressed coords",
            },
        },
        "productEligible": False,
        "browserSafe": False,
        "pureBrowserDecoderDerived": False,
        "extraAllocatorHooks": extra_hooks,
        "inventory": {
            "uniqueOpcodes": len(opcodes),
            "totalBlocks": int(sum(counts.values())),
            "factoryOk": sum(1 for r in factory_rows if r["ok"]),
            "sizeHistogram": [
                {"size": s, "classes": n} for s, n in sorted(size_hist.items())
            ],
            "size48Classes": len(size48),
            "size48UniqueDeserialize": len(deser_groups),
            "priorArtOpcodes": prior_present,
        },
        "size48Ranked": [
            {
                "opcode": r["opcode"],
                "blockCount": r["blockCount"],
                "deserialize": r["deserialize"],
                "usePacket": r["usePacket"],
                "signature": r["signature"],
            }
            for r in scored48[:20]
        ],
        "extendedSignatureHits": [
            {
                "opcode": r["opcode"],
                "heapDelta": r["heapDelta"],
                "blockCount": r["blockCount"],
                "deserialize": r["deserialize"],
                "signature": r["signature"],
            }
            for r in extended[:15]
        ],
        "runtimeProbes": runtime_reports,
        "winner": (
            {
                "opcode": winner["opcode"],
                "heapDelta": winner["heapDelta"],
                "pathFullConsume": winner["pathFullConsume"],
                "oracleQa": winner["oracleQa"],
            }
            if winner
            else None
        ),
        "winnerFound": winner is not None,
        "structuralBlocker": blocker,
        "falsePositiveGuard": score_from_features(false_positive_signature_fixture()),
        "endToEndWallMs": round(wall_ms, 3),
        "keep": "keep-research" if winner is not None else "discard",
        "reason": (
            f"E5 movement opcode={winner['opcode']} PathPacket+oracle passed"
            if winner
            else "E5 discard: no ROFL-X byte-buffer MOVEMENT_PATH class among "
            "observed 16.14 opcodes; closest alloc→+0x18 is vector stride"
        ),
        "nextSingleVariableHypothesis": (
            "E6: full-match emit from proven movement class"
            if winner
            else "E6: resolve arm64 movement via UsePacket/world bind or "
            "Windows-offset remap of MOVEMENT_PATH fields (ROFL-X), after "
            "confirming registrar type name — not opcode frequency alone"
        ),
    }


def build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("rofl", type=Path)
    ap.add_argument(
        "--oracle-jsonl",
        type=Path,
        default=Path("artifacts/rofl/3264361042/events.rfc461.jsonl"),
    )
    ap.add_argument("--league-binary", type=Path, default=DEFAULT_LEAGUE_BINARY)
    ap.add_argument("--json-out", type=Path, default=None)
    ap.add_argument("--max-runtime-samples", type=int, default=25)
    ap.add_argument("--append-speed-run", action="store_true")
    ap.add_argument("--log", type=Path, default=DEFAULT_LOG)
    ap.add_argument("--hypothesis", default="")
    ap.add_argument("--diff-label", default="phase-b-e5-structural")
    ap.add_argument("--match-code", default="3264361042")
    ap.add_argument("--dry-run", action="store_true")
    return ap


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    if not args.rofl.is_file():
        print(f"missing rofl: {args.rofl}", file=sys.stderr)
        return 2
    report = run_e5_scan(
        args.rofl,
        oracle_jsonl=args.oracle_jsonl,
        league_binary=args.league_binary,
        max_runtime_samples=int(args.max_runtime_samples),
    )
    if args.append_speed_run:
        rec = append_speed_record(
            log=args.log,
            hypothesis=args.hypothesis
            or "E5: ROFL-X structural MOVEMENT_PATH scan on 16.14 factory",
            diff_label=args.diff_label,
            keep="discard" if not report.get("winnerFound") else report["keep"],
            reason=report["reason"],
            wall_ms=float(report["endToEndWallMs"]),
            match_code=args.match_code,
            dry_run=args.dry_run,
            extra={
                "phase": "B-E5",
                "winnerFound": report["winnerFound"],
                "winner": report.get("winner"),
                "structuralBlocker": report.get("structuralBlocker"),
                "pureBrowserDecoderDerived": report.get("pureBrowserDecoderDerived"),
                "browserSafe": report.get("browserSafe"),
                "endToEndWallMs": report.get("endToEndWallMs"),
                "nextSingleVariableHypothesis": report.get(
                    "nextSingleVariableHypothesis"
                ),
                "statsUpdateCount": 0,
                "source": "offline_e5_structural_roflx",
                "researchKeep": report.get("keep"),
                "ts": utc_now_iso(),
            },
        )
        report["speedRun"] = rec

    if args.json_out is not None:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        report["jsonOut"] = str(args.json_out)

    summary = {
        "phase": report["phase"],
        "winnerFound": report["winnerFound"],
        "winner": report.get("winner"),
        "structuralBlocker": report.get("structuralBlocker"),
        "endToEndWallMs": report["endToEndWallMs"],
        "keep": report["keep"],
        "reason": report["reason"],
        "browserSafe": report["browserSafe"],
        "pureBrowserDecoderDerived": report["pureBrowserDecoderDerived"],
        "inventory": report.get("inventory"),
        "topSize48": (report.get("size48Ranked") or [])[:8],
        "runtimeDigest": [
            {
                "opcode": r["opcode"],
                "size": r.get("heapDelta"),
                "pathFull": r.get("pathFullConsume"),
                "heapPtr18": r.get("heapPtrAt18"),
                "sigScore": (r.get("signature") or {}).get("score"),
                "byteBuf": (r.get("signature") or {}).get("byteBufferCandidate"),
                "vectorReject": (r.get("signature") or {}).get("vectorStrideRejected"),
                "accepted": r.get("accepted"),
            }
            for r in report.get("runtimeProbes") or []
        ],
        "nextSingleVariableHypothesis": report.get("nextSingleVariableHypothesis"),
        "jsonOut": report.get("jsonOut"),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
