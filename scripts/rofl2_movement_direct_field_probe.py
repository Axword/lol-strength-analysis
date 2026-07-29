#!/usr/bin/env python3
"""Phase B E4: channel-351 direct-field layout probe (arm64 Deserialize).

Hypothesis: channel 351 is a direct-field encrypted sample packet (object size
32), not a dynamic PathPacket. Derive layout from local 16.14 arm64 binary
``Deserialize @ 0x1014866b8`` via Capstone + Unicorn write traces.

No Replay API, no unlicensed source copy. Emulator is research-only; a pure
browser decoder is marked only if movement fields are proven from binary
constants (not oracle curve-fitting).
"""
from __future__ import annotations

import argparse
import json
import math
import struct
import sys
import tempfile
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rofl2_probe import extract_segments, parse_rofl2  # noqa: E402
from rofl2_unicorn_packet_drive import (  # noqa: E402
    ARENA_BASE,
    BUF_BASE,
    BUF_SIZE,
    DEFAULT_LEAGUE_BINARY,
    HEAP_BASE,
    HEAP_SIZE,
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
from rofl2_movement_wire_scan import (  # noqa: E402
    ACCEPT_MAX_MAX_ERROR,
    ACCEPT_MAX_MEDIAN_ERROR,
    ACCEPT_MAX_P95_ERROR,
    ACCEPT_MIN_COMPARED_SAMPLES,
    ACCEPT_MIN_STABLE_ENTITIES,
    PROVEN_HERO_NET_ID_SET,
    optimal_oracle_assignment_by_block_param,
)
from rofl_speed_bench import utc_now_iso  # noqa: E402

try:
    import rofl2_accessor_spike as spike
except Exception:  # noqa: BLE001
    spike = None  # type: ignore

CHANNEL_PRIMARY = 351
CHANNEL_FALLBACK_IF_LAYOUT_MATCH = (259, 1194)
DESER_351 = 0x1014866B8
USE_351 = 0x1015019A0
JUMP_TABLE_SCHEMA = 0x10204FEE0
ENTITY_LUT_VA = 0x10205CD30
READER_A = 0x10152137C
READER_B = 0x101521284
READER_C = 0x10152156C
READER_D = 0x101521474
W15_HOOKS = (0x1015213FC, 0x101521304, 0x1015215EC, 0x1015214F4)
EXPECTED_HEAP_DELTA_351 = 32
PROBE_VERSION = "e4-direct-field-351-v1"
DECODER_CONFIG_VERSION = "ch351-direct-field-v1"


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


def disassemble_range(mu: Any, va: int, size: int = 0x180) -> List[dict]:
    from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM

    md = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
    rows = []
    for insn in md.disasm(bytes(mu.mem_read(va, size)), va):
        rows.append(
            {
                "va": hex(insn.address),
                "mnemonic": insn.mnemonic,
                "op": insn.op_str,
            }
        )
        if insn.mnemonic == "ret" and insn.address > va + 0x20:
            break
    return rows


def extract_object_fields(obj: bytes) -> dict:
    if len(obj) < 0x1C:
        raise ValueError("object too small")
    stored_type = struct.unpack_from("<I", obj, 0x8)[0]
    inner = struct.unpack_from("<I", obj, 0xC)[0]
    f10 = struct.unpack_from("<I", obj, 0x10)[0]
    f14 = struct.unpack_from("<I", obj, 0x14)[0]
    return {
        "storedType": stored_type,
        "innerEntityId": inner,
        "field10": f10,
        "field14": f14,
        "byte18": obj[0x18] if len(obj) > 0x18 else None,
        "byte19": obj[0x19] if len(obj) > 0x19 else None,
        "raw0_28": obj[:0x1C].hex(),
    }


def schema_from_payload(payload: bytes) -> Optional[int]:
    if not payload:
        return None
    return (payload[0] >> 3) & 7


def collect_channel_blocks(rofl: Path, channel: int) -> List[dict]:
    info = parse_rofl2(rofl)
    extracted = extract_segments(info["payload"])
    out: List[dict] = []
    for seg in extracted["segments"]:
        if int(seg.get("type") or 0) != 1:
            continue
        for b in extract_blocks_py(seg["bytes"], max_blocks=500_000):
            if int(b["channel"]) != int(channel):
                continue
            out.append(
                {
                    "time": float(b["time"]),
                    "channel": int(b["channel"]),
                    "param": int(b.get("param") or 0),
                    "payload": b["payload"] or b"",
                }
            )
    return out


def factory_layout(mu: Any, heap: BumpHeap, channel: int) -> dict:
    created = create_packet(mu, heap, int(channel))
    pkt = created.get("packet") or 0
    vtable = created.get("vtable") or 0
    deser = created.get("deserialize") or 0
    use = None
    if vtable:
        try:
            use = struct.unpack("<Q", bytes(mu.mem_read(vtable + 16, 8)))[0]
        except Exception:  # noqa: BLE001
            use = None
    obj = bytes(mu.mem_read(pkt, 0x40)) if pkt else b""
    return {
        "channel": channel,
        "ok": bool(pkt and deser),
        "heapDelta": created.get("heapDelta"),
        "storedType": created.get("storedType"),
        "vtable": hex(vtable) if vtable else None,
        "deserialize": hex(deser) if deser else None,
        "usePacket": hex(use) if use else None,
        "initialObjPrefix": obj[:0x28].hex() if obj else None,
        "matches351Layout": int(created.get("heapDelta") or 0) == EXPECTED_HEAP_DELTA_351
        and int(created.get("storedType") or -1) == channel,
    }


def deserialize_sample(
    mu: Any,
    heap: BumpHeap,
    *,
    channel: int,
    payload: bytes,
    capture_w15: bool = False,
) -> dict:
    from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_WRITE
    from unicorn.arm64_const import UC_ARM64_REG_W15

    created = create_packet(mu, heap, int(channel))
    pkt = created.get("packet") or 0
    deser = created.get("deserialize") or 0
    if not pkt or not deser:
        return {"ok": False, "error": "create_packet failed"}
    before = bytes(mu.mem_read(pkt, 0x30))
    pva = BUF_BASE + 0x01C00000
    mu.mem_write(pva, payload)
    writes: List[dict] = []
    state = {"w15": None}

    def on_write(_uc, _access, address, size, value, _user):
        if pkt <= address < pkt + 0x30:
            writes.append(
                {
                    "off": int(address - pkt),
                    "size": int(size),
                    "value": int(value) & ((1 << (8 * size)) - 1),
                }
            )

    def on_code(uc, address, _size, _user):
        if address in W15_HOOKS:
            state["w15"] = int(uc.reg_read(UC_ARM64_REG_W15)) & 0xFFFFFFFF

    h_w = mu.hook_add(UC_HOOK_MEM_WRITE, on_write)
    h_c = None
    if capture_w15:
        h_c = mu.hook_add(UC_HOOK_CODE, on_code, begin=0x101521000, end=0x101522000)
    des = deserialize_packet(
        mu,
        packet=pkt,
        deserialize_fn=deser,
        buf_va=pva,
        buf_len=len(payload),
        cursor_off=0,
    )
    mu.hook_del(h_w)
    if h_c is not None:
        mu.hook_del(h_c)
    after = bytes(mu.mem_read(pkt, 0x30))
    fields = extract_object_fields(after)
    changed = []
    for off in range(0, 0x28, 4):
        b = struct.unpack_from("<I", before, off)[0]
        a = struct.unpack_from("<I", after, off)[0]
        if a != b:
            changed.append({"off": off, "before": hex(b), "after": hex(a)})
    return {
        "ok": bool(des.get("ok")),
        "consumed": des.get("consumed"),
        "fullPayloadConsume": des.get("consumed") == len(payload),
        "callReturned": (des.get("call") or {}).get("returned"),
        "schema": schema_from_payload(payload),
        "payloadLen": len(payload),
        "fields": fields,
        "changedWords": changed,
        "writes": writes[:24],
        "w15PreSimd": state["w15"],
        "note": "call success alone is not semantic proof",
    }


def classify_inner_bands(inner_ctr: Mapping[int, int]) -> dict:
    bands = Counter()
    for k, v in inner_ctr.items():
        if k in PROVEN_HERO_NET_ID_SET:
            bands["proven_hero_AE_B7"] += v
        elif 0x40000000 <= k <= 0x400000FF:
            bands["net_0x400000xx"] += v
        elif 0x40000100 <= k <= 0x40000FFF:
            bands["net_0x40000xxx"] += v
        elif 0x40001000 <= k <= 0x4000FFFF:
            bands["net_0x4000xxxx"] += v
        else:
            bands["other"] += v
    return dict(bands)


def field_interpretations(f10: int, w15: Optional[int]) -> Dict[str, Tuple[float, float]]:
    """Only interpretations justified by 4-byte field / varint accumulator structure."""
    out: Dict[str, Tuple[float, float]] = {}
    u16a, u16b = f10 & 0xFFFF, (f10 >> 16) & 0xFFFF
    i16a = struct.unpack("<h", struct.pack("<H", u16a))[0]
    i16b = struct.unpack("<h", struct.pack("<H", u16b))[0]
    out["f10_u16_pair"] = (float(u16a), float(u16b))
    out["f10_i16_pair"] = (float(i16a), float(i16b))
    out["f10_i16_map"] = (i16a * 2.0 + 7358.0, i16b * 2.0 + 7412.0)
    out["f10_packed14"] = (float(f10 & 0x3FFF), float((f10 >> 14) & 0x3FFF))
    f32_x = float(struct.unpack("<f", struct.pack("<I", f10))[0])
    # Only one f32 fits in the 4-byte +0x10 slot; pair would need +0x14 jointly.
    out["f10_f32_x_only"] = (f32_x, 0.0)
    if w15 is not None:
        wu16a, wu16b = w15 & 0xFFFF, (w15 >> 16) & 0xFFFF
        wi16a = struct.unpack("<h", struct.pack("<H", wu16a))[0]
        wi16b = struct.unpack("<h", struct.pack("<H", wu16b))[0]
        out["w15_u16_pair"] = (float(wu16a), float(wu16b))
        out["w15_i16_pair"] = (float(wi16a), float(wi16b))
        out["w15_i16_map"] = (wi16a * 2.0 + 7358.0, wi16b * 2.0 + 7412.0)
        out["w15_packed14"] = (float(w15 & 0x3FFF), float((w15 >> 14) & 0x3FFF))
    return out


def score_coord_hypothesis(
    rows: Sequence[Mapping[str, Any]],
    oracle: Sequence[Mapping[str, Any]],
    *,
    key: str,
) -> dict:
    samples = []
    for r in rows:
        xz = (r.get("interpretations") or {}).get(key)
        if not xz:
            continue
        x, z = float(xz[0]), float(xz[1])
        if not (math.isfinite(x) and math.isfinite(z)):
            continue
        samples.append(
            {
                "time": float(r["time"]),
                "blockParam": int(r["param"]),
                "x": x,
                "z": z,
                "netId": int(r["innerEntityId"]),
            }
        )
    if len(samples) < 20:
        return {
            "key": key,
            "sampleCount": len(samples),
            "accepted": False,
            "error": "insufficient_samples",
        }
    qa = optimal_oracle_assignment_by_block_param(
        samples, oracle, tolerance_s=0.5, min_samples_per_param=4
    )
    accepted = bool(
        qa.get("methodPassed")
        and int(qa.get("assignmentCount") or 0) >= ACCEPT_MIN_STABLE_ENTITIES
        and int(qa.get("comparedSamples") or 0) >= ACCEPT_MIN_COMPARED_SAMPLES
        and float(qa.get("medianError") or 1e9) <= ACCEPT_MAX_MEDIAN_ERROR
        and float(qa.get("p95Error") or 1e9) <= ACCEPT_MAX_P95_ERROR
        and float(qa.get("maxError") or 1e9) <= ACCEPT_MAX_MAX_ERROR
    )
    return {
        "key": key,
        "sampleCount": len(samples),
        "heroParams": len({s["blockParam"] for s in samples}),
        "oracleQa": {
            k: qa.get(k)
            for k in (
                "assignmentCount",
                "comparedSamples",
                "medianError",
                "p95Error",
                "maxError",
                "methodPassed",
                "productEligible",
                "grouping",
            )
        },
        "accepted": accepted,
    }


def false_correlation_guard_samples() -> List[dict]:
    """Synthetic fields that look numeric but must fail oracle gates."""
    rows = []
    for i, param in enumerate(sorted(PROVEN_HERO_NET_ID_SET)[:6]):
        for t in (60.0, 61.0, 62.0, 63.0, 64.0, 65.0, 66.0, 67.0):
            # Constant packed junk unrelated to map positions.
            f10 = 0x0C0C0C44 ^ (i * 0x101)
            rows.append(
                {
                    "time": t + i * 0.01,
                    "param": param,
                    "innerEntityId": 0x40000001 + i,
                    "interpretations": field_interpretations(f10, f10 ^ 0x55),
                }
            )
    return rows


def probe_channel_351(
    mu: Any,
    heap: BumpHeap,
    blocks: Sequence[Mapping[str, Any]],
    oracle: Sequence[Mapping[str, Any]],
    *,
    corr_cap: int = 400,
) -> dict:
    size_hist = Counter(len(b["payload"]) for b in blocks)
    schema_hist = Counter(schema_from_payload(b["payload"]) for b in blocks)
    hero_param_blocks = [b for b in blocks if int(b["param"]) in PROVEN_HERO_NET_ID_SET]

    # Factory / disasm once
    factory = factory_layout(mu, heap, CHANNEL_PRIMARY)
    deser_disasm = disassemble_range(mu, DESER_351, 0x200)
    jump = list(bytes(mu.mem_read(JUMP_TABLE_SCHEMA, 8)))
    entity_lut_prefix = bytes(mu.mem_read(ENTITY_LUT_VA, 16)).hex()
    import hashlib

    entity_lut_sha = hashlib.sha256(bytes(mu.mem_read(ENTITY_LUT_VA, 256))).hexdigest()

    # Full inventory via Deserialize
    inner_ctr: Counter = Counter()
    ok_n = fail_n = hero_inner_n = 0
    field_change_offs: Counter = Counter()
    consumed_ok: Counter = Counter()
    schema_ok: Counter = Counter()
    corr_rows: List[dict] = []
    write_examples: List[dict] = []

    for i, b in enumerate(blocks):
        capture = len(corr_rows) < corr_cap and int(b["param"]) in PROVEN_HERO_NET_ID_SET
        row = deserialize_sample(
            mu,
            heap,
            channel=CHANNEL_PRIMARY,
            payload=b["payload"],
            capture_w15=capture,
        )
        if row.get("ok"):
            ok_n += 1
            schema_ok[row.get("schema")] += 1
            consumed_ok[row.get("consumed")] += 1
        else:
            fail_n += 1
        fields = row.get("fields") or {}
        inner = int(fields.get("innerEntityId") or 0)
        if inner:
            inner_ctr[inner] += 1
            if inner in PROVEN_HERO_NET_ID_SET:
                hero_inner_n += 1
        for ch in row.get("changedWords") or []:
            field_change_offs[int(ch["off"])] += 1
        if len(write_examples) < 6 and row.get("ok"):
            write_examples.append(
                {
                    "time": round(float(b["time"]), 3),
                    "paramHex": hex(int(b["param"])),
                    "payloadLen": len(b["payload"]),
                    "schema": row.get("schema"),
                    "consumed": row.get("consumed"),
                    "innerHex": hex(inner),
                    "field10Hex": hex(int(fields.get("field10") or 0)),
                    "field14Hex": hex(int(fields.get("field14") or 0)),
                    "w15PreSimd": row.get("w15PreSimd"),
                    "changedWords": row.get("changedWords"),
                }
            )
        if capture and row.get("ok"):
            f10 = int(fields.get("field10") or 0)
            corr_rows.append(
                {
                    "time": float(b["time"]),
                    "param": int(b["param"]),
                    "innerEntityId": inner,
                    "field10": f10,
                    "w15PreSimd": row.get("w15PreSimd"),
                    "interpretations": field_interpretations(f10, row.get("w15PreSimd")),
                }
            )

    # Coordinate hypothesis scoring (binary-structure justified only)
    keys = sorted({k for r in corr_rows for k in (r.get("interpretations") or {})})
    coord_scores = [score_coord_hypothesis(corr_rows, oracle, key=k) for k in keys]
    coord_scores.sort(
        key=lambda s: (
            not s.get("accepted"),
            float(((s.get("oracleQa") or {}).get("medianError")) or 1e12),
            -int((s.get("oracleQa") or {}).get("comparedSamples") or 0),
        )
    )
    false_guard = [
        score_coord_hypothesis(false_correlation_guard_samples(), oracle, key=k)
        for k in ("f10_i16_map", "w15_i16_map", "f10_packed14")
    ]

    movement_proven = any(s.get("accepted") for s in coord_scores)
    semantic = {
        "isMovement": False if not movement_proven else True,
        "conclusion": (
            "channel_351_direct_field_non_hero_entity_reference"
            if not movement_proven
            else "channel_351_direct_field_movement"
        ),
        "evidence": [
            "Deserialize writes stored type at +0x8 and entity id at +0xc after LUT varint precheck",
            "Schemas 0/2/5/7 call encrypted 4-byte readers into +0x10; no heap vector/path buffer",
            f"inner entity ids decoded on {sum(inner_ctr.values())}/{len(blocks)} blocks; "
            f"proven-hero inners={hero_inner_n}",
            "coordinate interpretations of +0x10 / pre-SIMD w15 fail oracle gates",
        ],
    }

    return {
        "channel": CHANNEL_PRIMARY,
        "channelHex": hex(CHANNEL_PRIMARY),
        "factory": factory,
        "binary": {
            "deserialize": hex(DESER_351),
            "usePacketExpected": hex(USE_351),
            "jumpTableSchema": jump,
            "entityLutVa": hex(ENTITY_LUT_VA),
            "entityLutSha256": entity_lut_sha,
            "entityLutPrefixHex": entity_lut_prefix,
            "readers": {
                "schema0": hex(READER_A),
                "schema2": hex(READER_B),
                "schema5": hex(READER_C),
                "schema7": hex(READER_D),
            },
            "deserializeDisasmHead": deser_disasm[:40],
        },
        "inventory": {
            "blockCount": len(blocks),
            "heroParamBlockCount": len(hero_param_blocks),
            "payloadSizeHistogram": [
                {"size": s, "count": n} for s, n in size_hist.most_common(8)
            ],
            "schemaHistogram": [
                {"schema": s, "count": n} for s, n in schema_hist.most_common()
            ],
            "deserializeOk": ok_n,
            "deserializeFail": fail_n,
            "innerEntityNonzero": sum(inner_ctr.values()),
            "uniqueInnerEntityIds": len(inner_ctr),
            "provenHeroInnerCount": hero_inner_n,
            "innerBands": classify_inner_bands(inner_ctr),
            "topInnerEntityIds": [
                {"idHex": hex(i), "count": c} for i, c in inner_ctr.most_common(15)
            ],
            "changedWordOffsets": dict(field_change_offs),
            "schemaOkHistogram": dict(schema_ok),
            "consumedOkHistogram": dict(consumed_ok.most_common(8)),
        },
        "objectLayout": {
            "+0x08": "u32 storedType (0x15f)",
            "+0x0c": "u32 innerEntityId (LUT-varint decrypted; not blockParam)",
            "+0x10": "u32 encrypted direct field (SIMD byte scramble) or schema default",
            "+0x14": "u32 second encrypted field (secondary jump table)",
            "+0x18": "u8 tertiary field / default",
            "heapAllocations": 0,
            "dynamicPathBuffer": False,
        },
        "writeExamples": write_examples,
        "coordinateHypotheses": coord_scores[:12],
        "falseCorrelationGuard": false_guard,
        "movementProven": movement_proven,
        "semantic": semantic,
        "corrSampleCount": len(corr_rows),
    }


def probe_fallback_layout_only(
    mu: Any, heap: BumpHeap, rofl: Path, channels: Sequence[int]
) -> List[dict]:
    out = []
    for ch in channels:
        fac = factory_layout(mu, heap, ch)
        entry = {"factory": fac, "probedDeep": False, "reason": None}
        if not fac.get("matches351Layout"):
            entry["reason"] = (
                f"heapDelta={fac.get('heapDelta')} != {EXPECTED_HEAP_DELTA_351}; "
                "skip deep direct-field probe (no broad brute force)"
            )
            out.append(entry)
            continue
        # Layout match path (not expected for 259/1194 on this build)
        blocks = collect_channel_blocks(rofl, ch)[:200]
        hero_inner = 0
        for b in blocks[:50]:
            row = deserialize_sample(mu, heap, channel=ch, payload=b["payload"])
            inner = int((row.get("fields") or {}).get("innerEntityId") or 0)
            if inner in PROVEN_HERO_NET_ID_SET:
                hero_inner += 1
        entry["probedDeep"] = True
        entry["sampleDeser"] = {"n": min(50, len(blocks)), "heroInners": hero_inner}
        out.append(entry)
    return out


def pure_decoder_stub(*, movement_proven: bool) -> dict:
    return {
        "decoderVersion": DECODER_CONFIG_VERSION,
        "channel": CHANNEL_PRIMARY,
        "productEligible": False,
        "browserSafe": False,
        "requiresLeagueBinary": not movement_proven,
        "requiresUnicorn": not movement_proven,
        "movementProven": movement_proven,
        "note": (
            "No pure movement decoder derived: channel 351 fields are direct "
            "encrypted entity-reference samples, not proven map coordinates."
            if not movement_proven
            else "Movement proven — fill transforms from binary constants only."
        ),
        "layoutConstantsFromBinary": {
            "storedTypeOff": 0x8,
            "innerEntityOff": 0xC,
            "field10Off": 0x10,
            "field14Off": 0x14,
            "objectSize": EXPECTED_HEAP_DELTA_351,
            "schemaBits": "payload[0] bits 3..5",
        },
    }


def run_e4_probe(
    rofl: Path,
    *,
    oracle_jsonl: Path,
    league_binary: Path = DEFAULT_LEAGUE_BINARY,
    corr_cap: int = 400,
    work_dir: Optional[Path] = None,
) -> dict:
    t0 = time.perf_counter()
    oracle = _load_oracle_positions(oracle_jsonl) if oracle_jsonl.is_file() else []
    if work_dir is None:
        work_dir = Path(tempfile.mkdtemp(prefix="lol-e4-probe-"))
    mu, heap = _setup_unicorn(Path(league_binary), Path(work_dir))
    blocks = collect_channel_blocks(rofl, CHANNEL_PRIMARY)
    primary = probe_channel_351(mu, heap, blocks, oracle, corr_cap=corr_cap)
    fallbacks = probe_fallback_layout_only(
        mu, heap, rofl, CHANNEL_FALLBACK_IF_LAYOUT_MATCH
    )
    wall_ms = (time.perf_counter() - t0) * 1000
    movement_proven = bool(primary.get("movementProven"))
    return {
        "ok": True,
        "phase": "B-E4",
        "probeVersion": PROBE_VERSION,
        "provenance": PROVENANCE,
        "productEligible": False,
        "pureBrowserDecoderDerived": False,
        "browserSafe": False,
        "pureDecoderConfig": pure_decoder_stub(movement_proven=movement_proven),
        "channel351": primary,
        "fallbackChannels": fallbacks,
        "winnerFound": movement_proven,
        "endToEndWallMs": round(wall_ms, 3),
        "keep": "keep-research" if movement_proven else "discard",
        "reason": (
            "E4 channel 351 direct-field movement proven from binary layout + oracle gates"
            if movement_proven
            else "E4 discard: channel 351 is direct-field non-hero entity packet; "
            "no coordinate field passes gates; 259/1194 layouts do not match"
        ),
        "nextSingleVariableHypothesis": (
            "E5: search movement among non-hero-param channels / UsePacket-driven "
            "types with PathPacket or 025B after confirming factory wire id from "
            "binary registrar (not identity-cadence hero-param ranking alone)"
            if not movement_proven
            else "E5: emit pure decoder + 1Hz research candidate"
        ),
        "acceptance": {
            "minHeroes": ACCEPT_MIN_STABLE_ENTITIES,
            "minCompared": ACCEPT_MIN_COMPARED_SAMPLES,
            "median": ACCEPT_MAX_MEDIAN_ERROR,
            "p95": ACCEPT_MAX_P95_ERROR,
            "max": ACCEPT_MAX_MAX_ERROR,
        },
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
    ap.add_argument("--corr-cap", type=int, default=400)
    ap.add_argument("--append-speed-run", action="store_true")
    ap.add_argument("--log", type=Path, default=DEFAULT_LOG)
    ap.add_argument("--hypothesis", default="")
    ap.add_argument("--diff-label", default="phase-b-e4-direct-field")
    ap.add_argument("--match-code", default="3264361042")
    ap.add_argument("--dry-run", action="store_true")
    return ap


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    if not args.rofl.is_file():
        print(f"missing rofl: {args.rofl}", file=sys.stderr)
        return 2
    report = run_e4_probe(
        args.rofl,
        oracle_jsonl=args.oracle_jsonl,
        league_binary=args.league_binary,
        corr_cap=int(args.corr_cap),
    )
    if args.append_speed_run:
        rec = append_speed_record(
            log=args.log,
            hypothesis=args.hypothesis
            or "E4: channel 351 direct-field layout from arm64 Deserialize",
            diff_label=args.diff_label,
            keep=report["keep"] if report.get("winnerFound") else "discard",
            reason=report["reason"],
            wall_ms=float(report["endToEndWallMs"]),
            match_code=args.match_code,
            dry_run=args.dry_run,
            extra={
                "phase": "B-E4",
                "winnerFound": report["winnerFound"],
                "pureBrowserDecoderDerived": report.get("pureBrowserDecoderDerived"),
                "semantic": (report.get("channel351") or {}).get("semantic"),
                "inventory": {
                    k: (report.get("channel351") or {}).get("inventory", {}).get(k)
                    for k in (
                        "blockCount",
                        "provenHeroInnerCount",
                        "uniqueInnerEntityIds",
                        "innerBands",
                    )
                },
                "endToEndWallMs": report.get("endToEndWallMs"),
                "nextSingleVariableHypothesis": report.get(
                    "nextSingleVariableHypothesis"
                ),
                "statsUpdateCount": 0,
                "source": "offline_e4_direct_field",
                "researchKeep": report.get("keep"),
                "ts": utc_now_iso(),
            },
        )
        report["speedRun"] = rec

    # Compact disk report: trim long disasm
    disk = dict(report)
    ch = disk.get("channel351")
    if isinstance(ch, dict) and isinstance(ch.get("binary"), dict):
        ch = dict(ch)
        binary = dict(ch["binary"])
        binary["deserializeDisasmHead"] = binary.get("deserializeDisasmHead", [])[:24]
        ch["binary"] = binary
        disk["channel351"] = ch

    if args.json_out is not None:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(
            json.dumps(disk, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        report["jsonOut"] = str(args.json_out)

    inv = (report.get("channel351") or {}).get("inventory") or {}
    best = ((report.get("channel351") or {}).get("coordinateHypotheses") or [{}])[0]
    summary = {
        "phase": report.get("phase"),
        "semantic": (report.get("channel351") or {}).get("semantic"),
        "winnerFound": report.get("winnerFound"),
        "pureBrowserDecoderDerived": report.get("pureBrowserDecoderDerived"),
        "productEligible": report.get("productEligible"),
        "endToEndWallMs": report.get("endToEndWallMs"),
        "keep": report.get("keep"),
        "reason": report.get("reason"),
        "inventory": {
            "blockCount": inv.get("blockCount"),
            "innerEntityNonzero": inv.get("innerEntityNonzero"),
            "provenHeroInnerCount": inv.get("provenHeroInnerCount"),
            "uniqueInnerEntityIds": inv.get("uniqueInnerEntityIds"),
            "innerBands": inv.get("innerBands"),
        },
        "bestCoordHypothesis": best,
        "fallbackChannels": [
            {
                "channel": (f.get("factory") or {}).get("channel"),
                "heapDelta": (f.get("factory") or {}).get("heapDelta"),
                "matches351Layout": (f.get("factory") or {}).get("matches351Layout"),
                "reason": f.get("reason"),
            }
            for f in report.get("fallbackChannels") or []
        ],
        "nextSingleVariableHypothesis": report.get("nextSingleVariableHypothesis"),
        "jsonOut": report.get("jsonOut"),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
