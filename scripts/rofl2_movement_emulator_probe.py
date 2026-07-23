#!/usr/bin/env python3
"""Phase B E3: movement encoding probe (Unicorn Deserialize + pure PathPacket).

Hypothesis: strongest identity/cadence channel (351 / 0x15f) carries encrypted
movement that patch-specific Deserialize expands into a compressed-path buffer.

Public facts used (no unlicensed source vendored):
  - Riot Replay API is camera/playback only (no ROFL packet decode).
  - Research (Mowokuma/ROFL, no license — method only): after movement
    Deserialize, read dynamic payload buffer then parse PathPacket:
      u16 flags/count, u32 entity id, f32 speed, optional byte,
      compressed bitmask + absolute/relative u16 coords;
      x = i16*2 + 7358, z = i16*2 + 7412.
  - Our arm64 Packet::Packet + Deserialize already driven in
    ``rofl2_unicorn_packet_drive.py``.

Product constraint: emulator is research-only to derive a pure decoder/config.
Never a Vercel/browser runtime dependency.
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
from dataclasses import dataclass
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
    PROVEN_HERO_NET_IDS,
    PROVEN_HERO_NET_ID_SET,
    optimal_oracle_assignment_by_block_param,
)
from rofl_speed_bench import utc_now_iso  # noqa: E402

try:
    import rofl2_accessor_spike as spike
except Exception:  # noqa: BLE001
    spike = None  # type: ignore

E3_CHANNELS_PRIMARY = (351,)
E3_CHANNELS_FALLBACK = (259, 1194, 921, 398, 632)
PATH_COORD_X0 = 7358.0
PATH_COORD_Z0 = 7412.0
DECODER_CONFIG_VERSION = "pathpacket-compressed-v1"
PROBE_VERSION = "e3-emulator-pathpacket-v1"


class PathParseError(RuntimeError):
    pass


@dataclass
class PathPacket:
    entity_id: int
    speed: float
    waypoints: List[Tuple[float, float]]
    parsing_type: int
    consumed: int
    total: int

    @property
    def full_consume(self) -> bool:
        return self.consumed == self.total

    def as_dict(self) -> dict:
        return {
            "entityId": self.entity_id,
            "speed": self.speed,
            "waypointCount": len(self.waypoints),
            "waypoints": [{"x": x, "z": z} for x, z in self.waypoints],
            "parsingType": self.parsing_type,
            "consumed": self.consumed,
            "total": self.total,
            "fullConsume": self.full_consume,
        }


def _sign_extend_u16(v: int) -> int:
    v &= 0xFFFF
    return v if v < 0x8000 else v - 0x10000


def transform_encoded_coord(encoded_u16: int) -> float:
    """Public research transform: map i16 grid → Summoner's Rift units."""
    return float(_sign_extend_u16(encoded_u16)) * 2.0 + PATH_COORD_X0


def transform_encoded_coord_z(encoded_u16: int) -> float:
    return float(_sign_extend_u16(encoded_u16)) * 2.0 + PATH_COORD_Z0


def parse_compressed_path_packet(
    payload: bytes,
    *,
    require_full_consume: bool = True,
    max_waypoints: int = 32,
    speed_range: Tuple[float, float] = (1.0, 5000.0),
    coord_range: Tuple[float, float] = (-500.0, 16000.0),
) -> PathPacket:
    """Strict independent PathPacket parser (public protocol facts).

    Layout:
      u16 parsing_type  (bit0 = optional byte; >>1 = waypoint count)
      u32 entity_id
      f32 speed
      [u8] optional if bit0 set
      bitmask bytes when count > 1
      per-waypoint absolute u16 or relative u8 pairs
    """
    if len(payload) < 10:
        raise PathParseError("payload shorter than PathPacket header")
    pos = 0
    parsing_type = struct.unpack_from("<H", payload, pos)[0]
    pos += 2
    entity_id = struct.unpack_from("<I", payload, pos)[0]
    pos += 4
    speed = struct.unpack_from("<f", payload, pos)[0]
    pos += 4
    if not math.isfinite(speed) or not (speed_range[0] <= speed <= speed_range[1]):
        raise PathParseError(f"implausible speed {speed}")
    if parsing_type & 1:
        if pos >= len(payload):
            raise PathParseError("optional byte underflow")
        pos += 1
    count = (parsing_type >> 1) & 0x7FFF
    if count == 0 or count > max_waypoints:
        raise PathParseError(f"invalid waypoint count {count}")
    bitmask_start = pos
    if count > 1:
        bitmask_len = ((count - 2) >> 2) + 1
        if pos + bitmask_len > len(payload):
            raise PathParseError("bitmask underflow")
        pos += bitmask_len
    temp_arr = payload[bitmask_start:]
    x_coord = 0
    y_coord = 0
    bit_i = 0
    waypoints: List[Tuple[float, float]] = []
    for wi in range(count):
        abs_x = True
        abs_y = True
        if wi != 0:
            if (bit_i >> 3) >= len(temp_arr) or ((bit_i + 1) >> 3) >= len(temp_arr):
                raise PathParseError("bitmask index overflow")
            bit0 = (temp_arr[bit_i >> 3] >> (bit_i & 7)) & 1
            bit1 = (temp_arr[(bit_i + 1) >> 3] >> ((bit_i + 1) & 7)) & 1
            abs_x = bit0 == 0
            abs_y = bit1 == 0
            bit_i += 2
        if abs_x:
            if pos + 2 > len(payload):
                raise PathParseError("x abs underflow")
            x_coord = struct.unpack_from("<H", payload, pos)[0]
            pos += 2
        else:
            if pos >= len(payload):
                raise PathParseError("x rel underflow")
            x_coord = (x_coord + payload[pos]) & 0xFFFF
            pos += 1
        if abs_y:
            if pos + 2 > len(payload):
                raise PathParseError("z abs underflow")
            y_coord = struct.unpack_from("<H", payload, pos)[0]
            pos += 2
        else:
            if pos >= len(payload):
                raise PathParseError("z rel underflow")
            y_coord = (y_coord + payload[pos]) & 0xFFFF
            pos += 1
        x = transform_encoded_coord(x_coord)
        z = transform_encoded_coord_z(y_coord)
        if not (coord_range[0] <= x <= coord_range[1] and coord_range[0] <= z <= coord_range[1]):
            raise PathParseError(f"coord out of range ({x},{z})")
        waypoints.append((x, z))
    if require_full_consume and pos != len(payload):
        raise PathParseError(f"trailing undecoded bytes consumed={pos} total={len(payload)}")
    return PathPacket(
        entity_id=entity_id,
        speed=float(speed),
        waypoints=waypoints,
        parsing_type=int(parsing_type),
        consumed=pos,
        total=len(payload),
    )


def scan_ptr_len_buffers(
    obj: bytes,
    *,
    heap_allocs: Sequence[Tuple[int, int]],
    read_mem,
    min_size: int = 8,
    max_size: int = 0x10000,
) -> List[dict]:
    """Find pointer+length(/cap) dynamic buffers in a packet object."""
    cands: List[dict] = []
    seen = set()
    for off in range(0, max(0, len(obj) - 15), 8):
        ptr = struct.unpack_from("<Q", obj, off)[0]
        for base, n in heap_allocs:
            if not (base <= ptr < base + n):
                continue
            for size_off, fmt in ((8, "<I"), (8, "<Q"), (16, "<I"), (16, "<Q")):
                if off + size_off + struct.calcsize(fmt) > len(obj):
                    continue
                size = int(struct.unpack_from(fmt, obj, off + size_off)[0])
                if not (min_size <= size <= max_size):
                    continue
                if ptr + size > base + n:
                    continue
                key = (off, ptr, size)
                if key in seen:
                    continue
                seen.add(key)
                try:
                    buf = bytes(read_mem(ptr, size))
                except Exception as exc:  # noqa: BLE001
                    cands.append(
                        {
                            "objOff": off,
                            "ptr": hex(ptr),
                            "size": size,
                            "sizeOff": off + size_off,
                            "error": str(exc),
                        }
                    )
                    continue
                cands.append(
                    {
                        "objOff": off,
                        "ptr": hex(ptr),
                        "size": size,
                        "sizeOff": off + size_off,
                        "prefixHex": buf[:24].hex(),
                        "buffer": buf,
                    }
                )
            break
    return cands


def collect_channel_blocks(
    rofl: Path,
    channel: int,
    *,
    hero_only: bool = True,
    max_samples: int = 200,
    min_time_s: float = 60.0,
    max_time_s: Optional[float] = None,
) -> Tuple[List[dict], dict]:
    info = parse_rofl2(rofl)
    extracted = extract_segments(info["payload"])
    sizes: Counter = Counter()
    first_bytes: Counter = Counter()
    schema6: Counter = Counter()
    all_hero = 0
    samples: List[dict] = []
    for seg in extracted["segments"]:
        if int(seg.get("type") or 0) != 1:
            continue
        for b in extract_blocks_py(seg["bytes"], max_blocks=500_000):
            if int(b["channel"]) != int(channel):
                continue
            param = int(b.get("param") or 0)
            if hero_only and param not in PROVEN_HERO_NET_ID_SET:
                continue
            t = float(b["time"])
            if t < min_time_s:
                continue
            if max_time_s is not None and t > max_time_s:
                continue
            pay = b["payload"] or b""
            all_hero += 1
            sizes[len(pay)] += 1
            if pay:
                first_bytes[pay[0]] += 1
            if len(pay) >= 6:
                schema6[pay[:6].hex()] += 1
            if len(samples) < max_samples:
                samples.append(
                    {
                        "time": t,
                        "channel": channel,
                        "param": param,
                        "payload": pay,
                        "prefixHex": pay[:16].hex(),
                    }
                )
    hist = {
        "channel": channel,
        "channelHex": hex(channel),
        "heroBlockCount": all_hero,
        "payloadSizeHistogram": [
            {"size": s, "count": n} for s, n in sizes.most_common(12)
        ],
        "firstByteHistogram": [
            {"byte": b, "count": n} for b, n in first_bytes.most_common(12)
        ],
        "prefix6HistogramTop": [
            {"hex": h, "count": n} for h, n in schema6.most_common(8)
        ],
        "sampleCount": len(samples),
        "redactedSamplePrefixes": [
            {
                "time": round(s["time"], 3),
                "paramHex": hex(s["param"]),
                "len": len(s["payload"]),
                "prefixHex": s["prefixHex"],
            }
            for s in samples[:6]
        ],
    }
    return samples, hist


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
    try:
        mu.mem_write(TYPE_COUNT_GLOBAL, struct.pack("<I", TYPE_COUNT_VALUE))
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"type_count global write failed: {exc}") from exc
    return mu, heap


def probe_channel_unicorn(
    mu: Any,
    heap: BumpHeap,
    samples: Sequence[Mapping[str, Any]],
    *,
    channel: int,
    max_samples: int = 40,
) -> dict:
    """create_packet + deserialize_packet; scan object/heap for path buffers."""
    created = create_packet(mu, heap, int(channel))
    vtable = created.get("vtable") or 0
    deser = created.get("deserialize") or 0
    use_packet = None
    if vtable:
        try:
            use_packet = struct.unpack("<Q", bytes(mu.mem_read(vtable + 16, 8)))[0]
        except Exception:  # noqa: BLE001
            use_packet = None
    factory = {
        "packet": bool(created.get("packet")),
        "storedType": created.get("storedType"),
        "vtable": hex(vtable) if vtable else None,
        "deserialize": hex(deser) if deser else None,
        "usePacket": hex(use_packet) if use_packet else None,
        "heapDelta": created.get("heapDelta"),
        "callError": (created.get("call") or {}).get("error"),
    }
    if not created.get("packet") or not deser:
        return {
            "ok": False,
            "factory": factory,
            "error": "create_packet failed",
            "samples": [],
            "pathFromRaw": 0,
            "pathFromBuffers": 0,
        }

    rows = []
    path_raw = 0
    path_buf = 0
    decoded_for_qa: List[dict] = []

    for s in list(samples)[:max_samples]:
        pay = s["payload"]
        # Fresh packet object each sample.
        created_i = create_packet(mu, heap, int(channel))
        pkt = created_i.get("packet") or 0
        deser_i = created_i.get("deserialize") or deser
        if not pkt or not deser_i:
            rows.append({"status": "create_failed"})
            continue
        allocs_before = len(heap.allocs)
        ptr_before = heap.ptr
        obj_before = bytes(mu.mem_read(pkt, 0x80))
        pva = BUF_BASE + 0x01800000
        mu.mem_write(pva, pay)
        des = deserialize_packet(
            mu,
            packet=pkt,
            deserialize_fn=deser_i,
            buf_va=pva,
            buf_len=len(pay),
            cursor_off=0,
        )
        obj_after = bytes(mu.mem_read(pkt, 0x80))
        new_allocs = heap.allocs[allocs_before:]
        # Object qword diffs (summary)
        diffs = []
        for off in range(0, 0x40, 8):
            b = struct.unpack_from("<Q", obj_before, off)[0]
            a = struct.unpack_from("<Q", obj_after, off)[0]
            if a != b:
                diffs.append({"off": off, "before": hex(b), "after": hex(a)})

        raw_path = None
        raw_err = None
        try:
            raw_path = parse_compressed_path_packet(pay)
            path_raw += 1
        except PathParseError as exc:
            raw_err = str(exc)

        buffers = scan_ptr_len_buffers(
            obj_after,
            heap_allocs=heap.allocs[-30:],
            read_mem=lambda ptr, n: bytes(mu.mem_read(ptr, n)),
        )
        # Also try every new alloc as a whole buffer candidate.
        for base, n in new_allocs:
            if 8 <= n <= 0x4000:
                try:
                    buffers.append(
                        {
                            "objOff": None,
                            "ptr": hex(base),
                            "size": n,
                            "sizeOff": None,
                            "prefixHex": bytes(mu.mem_read(base, min(n, 24))).hex(),
                            "buffer": bytes(mu.mem_read(base, n)),
                            "source": "new_alloc",
                        }
                    )
                except Exception:  # noqa: BLE001
                    pass

        buf_hits = []
        for buf in buffers:
            blob = buf.get("buffer")
            if not blob:
                continue
            try:
                pp = parse_compressed_path_packet(blob)
            except PathParseError:
                continue
            path_buf += 1
            buf_hits.append(
                {
                    "objOff": buf.get("objOff"),
                    "ptr": buf.get("ptr"),
                    "size": buf.get("size"),
                    "path": pp.as_dict(),
                }
            )
            if pp.full_consume and pp.entity_id in PROVEN_HERO_NET_ID_SET:
                decoded_for_qa.append(
                    {
                        "time": float(s["time"]),
                        "blockParam": int(s["param"]),
                        "netId": int(pp.entity_id),
                        "x": pp.waypoints[0][0],
                        "z": pp.waypoints[0][1],
                        "points": [{"x": x, "z": z} for x, z in pp.waypoints],
                        "speed": pp.speed,
                        "fullConsume": True,
                        "source": "unicorn_buffer",
                    }
                )

        if raw_path and raw_path.full_consume:
            decoded_for_qa.append(
                {
                    "time": float(s["time"]),
                    "blockParam": int(s["param"]),
                    "netId": int(raw_path.entity_id),
                    "x": raw_path.waypoints[0][0],
                    "z": raw_path.waypoints[0][1],
                    "points": [{"x": x, "z": z} for x, z in raw_path.waypoints],
                    "speed": raw_path.speed,
                    "fullConsume": True,
                    "source": "raw_payload",
                }
            )

        rows.append(
            {
                "time": round(float(s["time"]), 3),
                "paramHex": hex(int(s["param"])),
                "payloadLen": len(pay),
                "prefixHex": pay[:12].hex(),
                "deserialize": {
                    "ok": bool(des.get("ok")),
                    "consumed": des.get("consumed"),
                    "x0": des.get("x0"),
                    "returned": (des.get("call") or {}).get("returned"),
                    "error": (des.get("call") or {}).get("error"),
                    "fullPayloadConsume": des.get("consumed") == len(pay),
                },
                "heapDelta": heap.ptr - ptr_before,
                "newAllocs": [{"ptr": hex(p), "size": n} for p, n in new_allocs[:6]],
                "objectQwordDiffs": diffs[:8],
                "rawPathError": raw_err,
                "rawPath": raw_path.as_dict() if raw_path else None,
                "bufferCandidates": [
                    {k: v for k, v in b.items() if k != "buffer"} for b in buffers[:6]
                ],
                "pathFromBuffers": buf_hits[:4],
            }
        )

    return {
        "ok": True,
        "factory": factory,
        "sampleRows": rows,
        "pathFromRaw": path_raw,
        "pathFromBuffers": path_buf,
        "decodedForQa": decoded_for_qa,
        "note": (
            "call return / consumed alone is not semantic success; "
            "PathPacket full-consume + oracle gates required"
        ),
    }


def score_object_field_correlation(
    mu: Any,
    heap: BumpHeap,
    samples: Sequence[Mapping[str, Any]],
    oracle_frames: Sequence[Mapping[str, Any]],
    *,
    channel: int,
    max_samples: int = 60,
) -> dict:
    """Research QA: score inline object fields vs oracle (no product binding)."""
    # Reuse a lightweight extract-after-deser loop
    rows = []
    for s in list(samples)[:max_samples]:
        created = create_packet(mu, heap, int(channel))
        pkt = created.get("packet") or 0
        deser = created.get("deserialize") or 0
        if not pkt or not deser:
            continue
        pay = s["payload"]
        pva = BUF_BASE + 0x01800000
        mu.mem_write(pva, pay)
        des = deserialize_packet(
            mu, packet=pkt, deserialize_fn=deser, buf_va=pva, buf_len=len(pay), cursor_off=0
        )
        if not des.get("ok"):
            continue
        obj = bytes(mu.mem_read(pkt, 0x40))
        rows.append({"time": float(s["time"]), "param": int(s["param"]), "obj": obj})

    if not rows or not oracle_frames:
        return {"ok": False, "error": "no rows/oracle", "top": []}

    oracle_times = [float(fr["time"]) for fr in oracle_frames]

    def nearest(t: float):
        lo, hi = 0, len(oracle_times) - 1
        best = None
        best_dt = None
        while lo <= hi:
            mid = (lo + hi) // 2
            if oracle_times[mid] < t:
                lo = mid + 1
            else:
                hi = mid - 1
        for i in (lo - 1, lo, lo + 1):
            if 0 <= i < len(oracle_frames):
                dt = abs(oracle_times[i] - t)
                if dt <= 0.5 and (best_dt is None or dt < best_dt):
                    best_dt = dt
                    best = oracle_frames[i]
        return best

    scored = []
    for off in range(8, 0x38, 2):
        extractors = []
        extractors.append(
            (
                f"i16@{off}",
                lambda obj, o=off: (
                    float(struct.unpack_from("<h", obj, o)[0]),
                    float(struct.unpack_from("<h", obj, o + 2)[0]),
                )
                if o + 4 <= len(obj)
                else None,
            )
        )
        extractors.append(
            (
                f"i16scale@{off}",
                lambda obj, o=off: (
                    transform_encoded_coord(struct.unpack_from("<H", obj, o)[0]),
                    transform_encoded_coord_z(struct.unpack_from("<H", obj, o + 2)[0]),
                )
                if o + 4 <= len(obj)
                else None,
            )
        )
        if off % 4 == 0:
            extractors.append(
                (
                    f"f32@{off}",
                    lambda obj, o=off: (
                        float(struct.unpack_from("<f", obj, o)[0]),
                        float(struct.unpack_from("<f", obj, o + 4)[0]),
                    )
                    if o + 8 <= len(obj)
                    else None,
                )
            )
        for name, ex in extractors:
            by_param: Dict[int, Dict[int, List[float]]] = defaultdict(
                lambda: defaultdict(list)
            )
            valid = 0
            for r in rows:
                fr = nearest(r["time"])
                if fr is None:
                    continue
                xz = ex(r["obj"])
                if xz is None:
                    continue
                x, z = xz
                if not (math.isfinite(x) and math.isfinite(z)):
                    continue
                if not (0 <= x <= 15000 and 0 <= z <= 15000):
                    continue
                valid += 1
                for p in fr["participants"]:
                    pid = int(p["participantID"])
                    by_param[r["param"]][pid].append(
                        math.hypot(x - float(p["x"]), z - float(p["z"]))
                    )
            # greedy unique assignment for scoring only
            cands = []
            for param, pidmap in by_param.items():
                for pid, ds in pidmap.items():
                    if ds:
                        cands.append((statistics_median(ds), param, pid, ds))
            cands.sort()
            used_p: set = set()
            used_pid: set = set()
            errs: List[float] = []
            assigns = 0
            for med, param, pid, ds in cands:
                if param in used_p or pid in used_pid:
                    continue
                used_p.add(param)
                used_pid.add(pid)
                assigns += 1
                errs.extend(ds)
            if assigns < 3 or not errs:
                continue
            errs.sort()
            scored.append(
                {
                    "field": name,
                    "validPoints": valid,
                    "assignmentCount": assigns,
                    "comparedSamples": len(errs),
                    "medianError": round(statistics_median(errs), 3),
                    "p95Error": round(errs[int(0.95 * (len(errs) - 1))], 3),
                    "maxError": round(max(errs), 3),
                }
            )
    scored.sort(key=lambda r: (r["medianError"], -r["comparedSamples"]))
    return {"ok": True, "top": scored[:12], "rowsScored": len(rows)}


def statistics_median(vals: Sequence[float]) -> float:
    s = sorted(vals)
    return float(s[len(s) // 2])


def pure_decoder_config() -> dict:
    """Browser-safe config only — no binary/emulator dependency."""
    return {
        "decoderVersion": DECODER_CONFIG_VERSION,
        "kind": "compressed_path_packet",
        "productEligible": False,
        "runtime": {
            "browserSafe": True,
            "requiresLeagueBinary": False,
            "requiresUnicorn": False,
            "vercelNote": (
                "Ship pure TS/WASM parser + this config via CDN/Blob + Worker; "
                "do not upload League binary or Unicorn to Vercel Functions "
                "(4.5MB limit / native deps)"
            ),
        },
        "header": {
            "parsingType": "u16le",
            "entityId": "u32le",
            "speed": "f32le",
            "optionalByteIfBit0": True,
            "waypointCount": "parsingType >> 1",
        },
        "coordinates": {
            "encoding": "absolute_u16_or_relative_u8_bitmask",
            "transform": {
                "x": "i16(encoded)*2 + 7358",
                "z": "i16(encoded)*2 + 7412",
            },
            "constants": {"x0": PATH_COORD_X0, "z0": PATH_COORD_Z0},
        },
        "acceptance": {
            "minStableHeroParams": ACCEPT_MIN_STABLE_ENTITIES,
            "minComparedSamples": ACCEPT_MIN_COMPARED_SAMPLES,
            "maxMedianError": ACCEPT_MAX_MEDIAN_ERROR,
            "maxP95Error": ACCEPT_MAX_P95_ERROR,
            "maxMaxError": ACCEPT_MAX_MAX_ERROR,
            "requireFullConsume": True,
        },
        "provenance": PROVENANCE,
        "attribution": (
            "Path layout/transform from public 2026 research method "
            "(Mowokuma/ROFL docs; no source vendored). Riot Replay API has no "
            "raw ROFL packet decode."
        ),
    }


def run_e3_probe(
    rofl: Path,
    *,
    oracle_jsonl: Path,
    league_binary: Path = DEFAULT_LEAGUE_BINARY,
    max_samples: int = 40,
    work_dir: Optional[Path] = None,
) -> dict:
    t0 = time.perf_counter()
    oracle = _load_oracle_positions(oracle_jsonl) if oracle_jsonl.is_file() else []
    channels = list(E3_CHANNELS_PRIMARY) + list(E3_CHANNELS_FALLBACK)
    channel_reports = []
    winner = None
    pure_ready = False

    mu = heap = None
    unicorn_error = None
    try:
        if work_dir is None:
            work_dir = Path(tempfile.mkdtemp(prefix="lol-e3-probe-"))
        mu, heap = _setup_unicorn(Path(league_binary), Path(work_dir))
    except Exception as exc:  # noqa: BLE001
        unicorn_error = str(exc)

    for ch in channels:
        samples, hist = collect_channel_blocks(
            rofl, ch, hero_only=True, max_samples=max(max_samples, 80)
        )
        # Raw PathPacket attempt on all collected samples
        raw_ok = 0
        raw_full = 0
        raw_decoded = []
        raw_fail: Counter = Counter()
        for s in samples:
            try:
                pp = parse_compressed_path_packet(s["payload"])
            except PathParseError as exc:
                raw_fail[str(exc).split(":")[0]] += 1
                continue
            raw_ok += 1
            if pp.full_consume:
                raw_full += 1
            if pp.full_consume and pp.entity_id == int(s["param"]):
                raw_decoded.append(
                    {
                        "time": float(s["time"]),
                        "blockParam": int(s["param"]),
                        "netId": pp.entity_id,
                        "x": pp.waypoints[0][0],
                        "z": pp.waypoints[0][1],
                        "points": [{"x": x, "z": z} for x, z in pp.waypoints],
                        "speed": pp.speed,
                        "fullConsume": True,
                        "source": "raw_payload",
                    }
                )

        unicorn = None
        field_corr = None
        if mu is not None and heap is not None:
            unicorn = probe_channel_unicorn(
                mu, heap, samples, channel=ch, max_samples=max_samples
            )
            field_corr = score_object_field_correlation(
                mu, heap, samples, oracle, channel=ch, max_samples=min(60, max_samples)
            )

        qa_samples = list(raw_decoded)
        if unicorn:
            qa_samples.extend(unicorn.get("decodedForQa") or [])
        oracle_qa = None
        if qa_samples and oracle:
            oracle_qa = optimal_oracle_assignment_by_block_param(
                qa_samples, oracle, tolerance_s=0.5
            )

        accepted = bool(
            oracle_qa
            and oracle_qa.get("methodPassed")
            and int(oracle_qa.get("assignmentCount") or 0) >= ACCEPT_MIN_STABLE_ENTITIES
            and int(oracle_qa.get("comparedSamples") or 0) >= ACCEPT_MIN_COMPARED_SAMPLES
        )
        report = {
            "channel": ch,
            "channelHex": hex(ch),
            "histogram": hist,
            "rawPathPacket": {
                "attempted": len(samples),
                "parsed": raw_ok,
                "fullConsume": raw_full,
                "entityMatchesParam": len(raw_decoded),
                "failureHistogram": dict(raw_fail.most_common(8)),
            },
            "unicorn": (
                {
                    k: unicorn.get(k)
                    for k in (
                        "ok",
                        "factory",
                        "pathFromRaw",
                        "pathFromBuffers",
                        "note",
                        "error",
                    )
                }
                | {
                    "sampleRows": (unicorn.get("sampleRows") or [])[:8],
                    "decodedQaCount": len(unicorn.get("decodedForQa") or []),
                }
                if unicorn
                else {"ok": False, "error": unicorn_error or "unicorn not initialized"}
            ),
            "objectFieldCorrelation": field_corr,
            "oracleQa": (
                {
                    k: oracle_qa.get(k)
                    for k in (
                        "assignmentCount",
                        "comparedSamples",
                        "medianError",
                        "p95Error",
                        "maxError",
                        "methodPassed",
                        "grouping",
                        "productEligible",
                        "stableHeroParams",
                    )
                }
                if oracle_qa
                else None
            ),
            "accepted": accepted,
            "failureSignatures": [],
        }
        if hist["heroBlockCount"] and hist["payloadSizeHistogram"]:
            top_size = hist["payloadSizeHistogram"][0]["size"]
            if top_size < 10:
                report["failureSignatures"].append(
                    f"payload_too_small_for_pathpacket_header:mode={top_size}"
                )
        if raw_ok == 0:
            report["failureSignatures"].append("raw_pathpacket_parse_zero")
        if unicorn and unicorn.get("pathFromBuffers", 0) == 0:
            report["failureSignatures"].append("unicorn_no_pathpacket_buffer")
        if unicorn and not any(
            (r.get("deserialize") or {}).get("fullPayloadConsume")
            for r in (unicorn.get("sampleRows") or [])
        ):
            # still record if some full consumes exist
            full_n = sum(
                1
                for r in (unicorn.get("sampleRows") or [])
                if (r.get("deserialize") or {}).get("fullPayloadConsume")
            )
            if full_n == 0:
                report["failureSignatures"].append("unicorn_no_full_payload_consume")
        if not accepted:
            report["failureSignatures"].append("oracle_gates_not_met")
        channel_reports.append(report)
        if accepted and winner is None:
            winner = report
            pure_ready = True

    wall_ms = (time.perf_counter() - t0) * 1000
    next_hyp = (
        "E4: derive arm64 mov_decrypt payload_offset/size_offset (Mowokuma-style "
        "patch config) and/or extend Unicorn stubs so Deserialize materializes "
        "the dynamic path buffer; channel 351 is identity-strong but ciphertext-"
        "sized (6–9B) under current stubs"
        if winner is None
        else "E4: productize pure PathPacket decoder + 1Hz emit with identity gates"
    )
    return {
        "ok": True,
        "phase": "B-E3",
        "probeVersion": PROBE_VERSION,
        "provenance": PROVENANCE,
        "productEligible": False,
        "pureBrowserDecoderDerived": bool(pure_ready),
        "pureDecoderConfig": pure_decoder_config(),
        "riotGithubNotes": {
            "riotReplayApi": "camera/playback only; no raw ROFL packet decode",
            "mowokumaMethod": (
                "Unicorn movement Deserialize → dynamic payload buffer → "
                "PathPacket compressed coords (x=i16*2+7358,z=i16*2+7412); "
                "Windows patch mov netid example 980 — not present on this ROFL; "
                "no source vendored"
            ),
            "vercel": (
                "Browser Worker/WASM or Blob background worker for pure decoder; "
                "never ship League binary / Unicorn as Vercel Function dependency"
            ),
        },
        "channels": channel_reports,
        "winner": (
            {
                "channel": winner["channel"],
                "channelHex": winner["channelHex"],
                "oracleQa": winner.get("oracleQa"),
            }
            if winner
            else None
        ),
        "winnerFound": winner is not None,
        "endToEndWallMs": round(wall_ms, 3),
        "keep": "keep-research" if winner is not None else "discard",
        "reason": (
            f"E3 winner channel={winner['channel']} pure PathPacket after emulator buffer"
            if winner
            else "E3 discard: no channel produced PathPacket buffers that pass "
            "oracle gates under current Unicorn stubs"
        ),
        "nextSingleVariableHypothesis": next_hyp,
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
    ap.add_argument("--max-samples", type=int, default=40)
    ap.add_argument("--append-speed-run", action="store_true")
    ap.add_argument("--log", type=Path, default=DEFAULT_LOG)
    ap.add_argument("--hypothesis", default="")
    ap.add_argument("--diff-label", default="phase-b-e3-pathpacket")
    ap.add_argument("--match-code", default="3264361042")
    ap.add_argument("--dry-run", action="store_true")
    return ap


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    if not args.rofl.is_file():
        print(f"missing rofl: {args.rofl}", file=sys.stderr)
        return 2
    report = run_e3_probe(
        args.rofl,
        oracle_jsonl=args.oracle_jsonl,
        league_binary=args.league_binary,
        max_samples=int(args.max_samples),
    )
    if args.append_speed_run:
        rec = append_speed_record(
            log=args.log,
            hypothesis=args.hypothesis
            or "E3: Unicorn Deserialize buffer + pure PathPacket encoding",
            diff_label=args.diff_label,
            keep="discard",
            reason=report["reason"],
            wall_ms=float(report["endToEndWallMs"]),
            match_code=args.match_code,
            dry_run=args.dry_run,
            extra={
                "phase": "B-E3",
                "winnerFound": report["winnerFound"],
                "winner": report.get("winner"),
                "pureBrowserDecoderDerived": report.get("pureBrowserDecoderDerived"),
                "endToEndWallMs": report.get("endToEndWallMs"),
                "nextSingleVariableHypothesis": report.get(
                    "nextSingleVariableHypothesis"
                ),
                "statsUpdateCount": 0,
                "source": "offline_e3_emulator_pathpacket",
                "researchKeep": report.get("keep"),
                "ts": utc_now_iso(),
            },
        )
        report["speedRun"] = rec

    # Compact disk report: strip bulky per-sample dumps already truncated
    disk = dict(report)
    if args.json_out is not None:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(
            json.dumps(disk, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        report["jsonOut"] = str(args.json_out)

    # stdout summary
    summary = {
        k: report.get(k)
        for k in (
            "phase",
            "winnerFound",
            "winner",
            "endToEndWallMs",
            "keep",
            "reason",
            "pureBrowserDecoderDerived",
            "nextSingleVariableHypothesis",
            "jsonOut",
            "productEligible",
        )
    }
    summary["channelDigest"] = [
        {
            "channel": c["channel"],
            "accepted": c["accepted"],
            "heroBlocks": c["histogram"]["heroBlockCount"],
            "sizeMode": (c["histogram"]["payloadSizeHistogram"] or [{}])[0],
            "rawParsed": c["rawPathPacket"]["parsed"],
            "unicornPathBuffers": (c.get("unicorn") or {}).get("pathFromBuffers"),
            "factory": ((c.get("unicorn") or {}).get("factory") or {}),
            "oracle": c.get("oracleQa"),
            "failures": c.get("failureSignatures"),
        }
        for c in report.get("channels") or []
    ]
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
