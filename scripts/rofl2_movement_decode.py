#!/usr/bin/env python3
"""Offline ROFL2 0x025B movement decode (Phase B E0/E1 research).

Clean-room implementation from public protocol facts + our patch-matched
binary. Reuses ``rofl2_probe`` segment inflate and ``extract_blocks_py``
block framing. Does **not** vendor unlicensed third-party source.

Protocol facts (public research, 2026; attribution only — no code copy):
  - Wire packet id for movement on recent patches: ``0x025B`` (not legacy ``0x61``)
  - Payload: 6-byte LE schema + ordered fields with per-byte ciphers
  - Packed position varint: ``x = v & 0x3fff``, ``z = (v >> 14) & 0x3fff``
  - Embedded 256-byte LUT matches League binary ``0x231e0d0`` (sha256 below)

Provenance label for emitted research events: ``offline_rofl2_025b_research``.
Never product-identity-binds netId→participant from oracle QA.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rofl2_probe import extract_segments, parse_rofl2  # noqa: E402
from rofl2_unicorn_packet_drive import extract_blocks_py  # noqa: E402
from rofl_speed_bench import append_run_record, new_run_id, utc_now_iso  # noqa: E402

DECODER_VERSION = "offline-025b-v1"
MOVEMENT_PACKET_ID = 0x025B
PROVENANCE = "offline_rofl2_025b_research"
DEFAULT_LOG = Path(__file__).resolve().parents[1] / "docs/rofl-research/speed-runs.jsonl"
DEFAULT_LEAGUE_BINARY = Path(
    "/Applications/League of Legends.app/Contents/LoL/Game/"
    "LeagueofLegends.app/Contents/MacOS/LeagueofLegends"
)
# File offset in the 16.14 macOS LeagueofLegends binary (verified locally).
LUT_BINARY_OFFSET = 0x231E0D0
LUT_SHA256 = "328528d693ab5d96a815b6706694025a980e609019304aeb2e5e32797011c04b"
# Independently extracted from the local patch binary (not third-party source).
GENERATED_LUT_BIN = (
    Path(__file__).resolve().parents[1]
    / "docs/rofl-research/generated/cipher-lut-16.14.bin"
)
GENERATED_LUT_MANIFEST = (
    Path(__file__).resolve().parents[1]
    / "docs/rofl-research/generated/cipher-lut-16.14.manifest.json"
)

# Schema bit layout + read-type sets (public protocol facts; independently coded).
SCHEMA_FIELDS: Dict[int, Tuple[int, int]] = {
    1: (0x17, 3),
    2: (0x1D, 1),
    3: (0x04, 3),
    4: (0x1A, 3),
    5: (0x0D, 3),
    6: (0x01, 3),
    7: (0x10, 3),
    8: (0x0A, 3),
    9: (0x1F, 3),
    10: (0x22, 3),
    11: (0x1E, 1),
    12: (0x25, 3),
    13: (0x00, 1),
    14: (0x07, 3),
    15: (0x28, 1),
    16: (0x13, 3),
    17: (0x16, 1),
}
FIELD_READ_TYPES: Dict[int, frozenset] = {
    1: frozenset({0, 1, 4, 5}),
    3: frozenset({0, 1, 4, 6}),
    4: frozenset({1, 2, 3, 4, 5, 7}),
    5: frozenset({0, 3, 5, 7}),
    6: frozenset({2, 4, 5, 6}),
    7: frozenset({1, 5, 6, 7}),
    8: frozenset({1, 2, 4, 5, 6, 7}),
    9: frozenset({0, 1, 2, 5}),
    10: frozenset({1, 2, 3, 7}),
    12: frozenset({1, 4, 5, 6}),
    14: frozenset({1, 2, 4, 5}),
    16: frozenset({0, 2, 3, 6}),
}

class MovementDecodeError(RuntimeError):
    """Fail-closed decode / inventory error."""


def ror8(v: int, n: int) -> int:
    return ((v >> n) | (v << (8 - n))) & 0xFF


def bitswap(b: int) -> int:
    """Nibble-pair bitswap used by several field ciphers (public protocol fact)."""
    hi = (b & 0xD5) << 1
    lo = (b >> 1) & 0x55
    return (hi | lo) & 0xFF


def _read_verified_lut_bytes(blob: bytes, *, context: str) -> bytes:
    if len(blob) != 256:
        raise MovementDecodeError(f"{context}: expected 256-byte LUT, got {len(blob)}")
    digest = hashlib.sha256(blob).hexdigest()
    if digest != LUT_SHA256:
        raise MovementDecodeError(f"{context}: sha256 mismatch: {digest}")
    return bytes(blob)


def load_generated_lut_cache(
    bin_path: Optional[Path] = None,
    manifest_path: Optional[Path] = None,
) -> Tuple[bytes, str]:
    """Load independently-derived LUT cache + verify generated manifest hash."""
    bin_p = Path(bin_path) if bin_path else GENERATED_LUT_BIN
    man_p = Path(manifest_path) if manifest_path else GENERATED_LUT_MANIFEST
    if not bin_p.is_file():
        raise MovementDecodeError(f"missing generated LUT cache: {bin_p}")
    if not man_p.is_file():
        raise MovementDecodeError(f"missing generated LUT manifest: {man_p}")
    man = json.loads(man_p.read_text(encoding="utf-8"))
    if str(man.get("sha256") or "") != LUT_SHA256:
        raise MovementDecodeError("generated LUT manifest sha256 constant mismatch")
    lut = _read_verified_lut_bytes(bin_p.read_bytes(), context=str(bin_p))
    if hashlib.sha256(lut).hexdigest() != str(man["sha256"]):
        raise MovementDecodeError("generated LUT bytes/manifest sha256 mismatch")
    return lut, f"generated_cache:{bin_p.name}:sha256={LUT_SHA256}"


def load_lut(league_binary: Optional[Path] = None) -> Tuple[bytes, str]:
    """Load 256-byte LUT from patch binary, else generated manifest-backed cache.

    Never embeds third-party LUT bytes in source. Runtime prefers the local
    League binary; CI/tests without the game use the independently extracted
    cache under ``docs/rofl-research/generated/``.
    """
    path = Path(league_binary) if league_binary else DEFAULT_LEAGUE_BINARY
    if path.is_file():
        blob = path.read_bytes()
        end = LUT_BINARY_OFFSET + 256
        if end > len(blob):
            raise MovementDecodeError(f"binary too small for LUT at {hex(LUT_BINARY_OFFSET)}")
        lut = _read_verified_lut_bytes(
            blob[LUT_BINARY_OFFSET:end],
            context=f"league_binary:{path}:{hex(LUT_BINARY_OFFSET)}",
        )
        return lut, f"league_binary:{path}:offset={hex(LUT_BINARY_OFFSET)}"
    return load_generated_lut_cache()


CipherFn = Callable[[int], int]


def make_ciphers(lut: bytes) -> Dict[int, Tuple[str, CipherFn]]:
    """Per-field Pass-1 byte transforms (documented public cipher recipes)."""

    def fad5c0(b: int) -> int:
        b = ror8(b, 2)
        b ^= 0x15
        b = bitswap(b)
        b = ror8(b, 7)
        return (~b) & 0xFF

    def fab3c0(b: int) -> int:
        b = (b + 0x50) & 0xFF
        idx = ((b << 6) | (b >> 2)) & 0xFF
        b = lut[idx]
        b = (b - 0x62) & 0xFF
        b ^= 0x36
        b = (b + 0x62) & 0xFF
        return b

    def fb82b0(b: int) -> int:
        b = ror8(b, 2)
        b = (b + 3) & 0xFF
        b ^= 0xF5
        b = bitswap(b)
        b = ror8(b, 4)
        b = bitswap(b)
        return (~b) & 0xFF

    def fadd60(b: int) -> int:
        b = (b - 0x70) & 0xFF
        b = ror8(b, 5)
        b = bitswap(b)
        b = (~b) & 0xFF
        b = lut[b]
        b = lut[b]
        return ror8(b, 2)

    def fae670(b: int) -> int:
        b = lut[b]
        b = ror8(b, 1)
        b = (b - 0x71) & 0xFF
        b = ror8(b, 6)
        b ^= 0x91
        return bitswap(b)

    def fab5b0(b: int) -> int:
        b = ror8(b, 3)
        b = (b + 0x19) & 0xFF
        b = ror8(b, 4)
        b ^= 0xAA
        return (b - 0x45) & 0xFF

    def fb8fc0(b: int) -> int:
        b = (b + 0x2F) & 0xFF
        b = bitswap(b)
        b = (~b) & 0xFF
        b = (b - 0x57) & 0xFF
        b = ror8(b, 7)
        return bitswap(b)

    def fab410(b: int) -> int:
        b = (~b) & 0xFF
        b = ror8(b, 2)
        b ^= 0x5A
        b = ror8(b, 6)
        b = (b - 0x34) & 0xFF
        return b ^ 0x4D

    def faf080(b: int) -> int:
        b = (b - 0x62) & 0xFF
        b = bitswap(b)
        return (b + 7) & 0xFF

    def fb6120(b: int) -> int:
        b = ror8(b, 5)
        b = (b + 0x6B) & 0xFF
        b = (~b) & 0xFF
        b = (b + 0x3A) & 0xFF
        combined = ((b << 3) | (b >> 5)) & 0xFF
        b = lut[combined]
        b = ror8(b, 3)
        return bitswap(b)

    def fb9a80(b: int) -> int:
        b = lut[b]
        b ^= 0xD8
        b = ror8(b, 2)
        b = (b - 0x36) & 0xFF
        b = ror8(b, 4)
        return (b + 0x21) & 0xFF

    def fb3cc0(b: int) -> int:
        b = lut[b]
        b = (b - 0x62) & 0xFF
        b = ror8(b, 3)
        b = bitswap(b)
        b = (b + 0x5F) & 0xFF
        b = lut[b]
        return bitswap(b)

    return {
        1: ("varint", fad5c0),
        3: ("1byte", fab3c0),
        4: ("varint", fb82b0),
        5: ("varint", fadd60),
        6: ("varint", fae670),
        7: ("1byte", fab5b0),
        8: ("varint", fb8fc0),
        9: ("1byte", fab410),
        10: ("varint", faf080),
        12: ("4byte_be", fb6120),
        14: ("1byte", fb9a80),
        16: ("4byte_float_bswap", fb3cc0),
    }


def invert_cipher(cipher: CipherFn) -> CipherFn:
    table = [0] * 256
    seen = [False] * 256
    for plain in range(256):
        out = cipher(plain) & 0xFF
        if seen[out]:
            raise MovementDecodeError("cipher is not a permutation")
        seen[out] = True
        table[out] = plain
    return lambda b, _t=table: _t[b & 0xFF]


def read_varint(
    data: bytes,
    pos: int,
    cipher: CipherFn,
    *,
    signed: bool = False,
) -> Tuple[int, int]:
    """Read a ciphered protobuf-style varint.

    Entity netIds use the high 0x40xxxxxx range, so default is **unsigned**.
    Optional ``signed`` applies the public 30-bit sign convention when needed.
    """
    result = 0
    shift = 0
    while pos < len(data):
        decoded = cipher(data[pos])
        pos += 1
        result |= (decoded & 0x7F) << shift
        shift += 7
        if not (decoded & 0x80):
            break
        if shift > 35:
            raise MovementDecodeError("varint overflow")
    else:
        raise MovementDecodeError("varint underflow")
    if signed and (result & (1 << 30)):
        result = -(result ^ (1 << 30))
    return int(result), pos


def write_varint(
    value: int,
    cipher_inv: CipherFn,
    *,
    signed: bool = False,
) -> bytes:
    if signed and value < 0:
        value = (-int(value)) | (1 << 30)
    out = bytearray()
    v = int(value) & 0xFFFFFFFF
    while True:
        byte = v & 0x7F
        v >>= 7
        if v:
            byte |= 0x80
            out.append(cipher_inv(byte))
        else:
            out.append(cipher_inv(byte))
            break
    return bytes(out)


def pack_xz(x: int, z: int) -> int:
    if not (0 <= x <= 0x3FFF and 0 <= z <= 0x3FFF):
        raise MovementDecodeError("coords out of 14-bit range")
    return (int(z) << 14) | int(x)


def unpack_xz(packed: int) -> Tuple[int, int]:
    return int(packed) & 0x3FFF, (int(packed) >> 14) & 0x3FFF


@dataclass
class MovementSample:
    time_s: float
    net_id: int
    x: int
    z: int
    speed: Optional[float] = None
    state: Optional[int] = None
    sequence: Optional[int] = None
    waypoint_indicator: Optional[int] = None
    movement_sub_type: Optional[int] = None
    channel: int = MOVEMENT_PACKET_ID
    payload_len: int = 0
    has_container: bool = False
    fields_present: List[int] = field(default_factory=list)

    def as_dict(self) -> dict:
        d = {
            "time": float(self.time_s),
            "netId": int(self.net_id),
            "x": int(self.x),
            "z": int(self.z),
            "channel": int(self.channel),
            "payloadLen": int(self.payload_len),
            "nativePointSample": True,
            "fieldsPresent": list(self.fields_present),
        }
        if self.speed is not None:
            d["speed"] = float(self.speed)
        if self.state is not None:
            d["state"] = int(self.state)
        if self.sequence is not None:
            d["sequence"] = int(self.sequence)
        if self.waypoint_indicator is not None:
            d["waypointIndicator"] = int(self.waypoint_indicator)
        if self.movement_sub_type is not None:
            d["movementSubType"] = int(self.movement_sub_type)
        if self.has_container:
            d["hasContainer"] = True
        return d


@dataclass
class DecodeResult:
    ok: bool
    sample: Optional[MovementSample] = None
    error: Optional[str] = None
    consumed: int = 0
    total: int = 0


def decode_025b_payload(
    data: bytes,
    *,
    time_s: float,
    lut: bytes,
    require_full_consume: bool = True,
    channel: int = MOVEMENT_PACKET_ID,
) -> DecodeResult:
    """Decode one 0x025B payload. Fail closed on schema/stream errors."""
    if len(data) < 6:
        return DecodeResult(False, error="payload shorter than 6-byte schema", total=len(data))
    ciphers = make_ciphers(lut)
    schema = int.from_bytes(data[:6], "little")
    pos = 6
    values: Dict[int, Any] = {}
    present: List[int] = []
    has_container = False

    try:
        for fnum in range(1, 18):
            dl, nbits = SCHEMA_FIELDS[fnum]
            tc = (schema >> dl) & ((1 << nbits) - 1)
            if fnum == 17:
                if tc == 1:
                    has_container = True
                    pos = len(data)
                break
            if fnum == 13:
                continue
            if tc not in FIELD_READ_TYPES.get(fnum, frozenset()):
                continue
            if fnum not in ciphers:
                continue
            rtype, cipher = ciphers[fnum]
            if rtype == "varint":
                val, pos = read_varint(data, pos, cipher)
            elif rtype == "1byte":
                if pos >= len(data):
                    raise MovementDecodeError(f"f{fnum} 1byte underflow")
                val = cipher(data[pos])
                pos += 1
            elif rtype == "4byte_be":
                if pos + 4 > len(data):
                    raise MovementDecodeError(f"f{fnum} 4byte underflow")
                raw = 0
                for _ in range(4):
                    raw = ((raw << 8) | cipher(data[pos])) & 0xFFFFFFFF
                    pos += 1
                val = raw
            elif rtype == "4byte_float_bswap":
                if pos + 4 > len(data):
                    raise MovementDecodeError(f"f{fnum} float underflow")
                raw = 0
                for _ in range(4):
                    raw = ((raw << 8) | cipher(data[pos])) & 0xFFFFFFFF
                    pos += 1
                le = struct.unpack("<I", struct.pack(">I", raw))[0]
                val = struct.unpack("<f", struct.pack("<I", le))[0]
            else:
                raise MovementDecodeError(f"unknown reader {rtype}")
            values[fnum] = val
            present.append(fnum)
    except MovementDecodeError as exc:
        return DecodeResult(False, error=str(exc), consumed=pos, total=len(data))

    if require_full_consume and not has_container and pos != len(data):
        return DecodeResult(
            False,
            error=f"trailing undecoded bytes: consumed={pos} total={len(data)}",
            consumed=pos,
            total=len(data),
        )
    if 4 not in values or 10 not in values:
        return DecodeResult(
            False,
            error="missing required fields f4/f10",
            consumed=pos,
            total=len(data),
        )

    net_id = int(values[4]) & 0xFFFFFFFF
    if net_id == 0:
        return DecodeResult(False, error="invalid netId=0", consumed=pos, total=len(data))
    x, z = unpack_xz(int(values[10]))
    if not (0 <= x <= 0x3FFF and 0 <= z <= 0x3FFF):
        return DecodeResult(False, error="coords outside 14-bit domain", consumed=pos, total=len(data))

    sample = MovementSample(
        time_s=float(time_s),
        net_id=net_id,
        x=x,
        z=z,
        speed=float(values[16]) if 16 in values else None,
        state=int(values[6]) if 6 in values else None,
        sequence=int(values[14]) if 14 in values else None,
        waypoint_indicator=int(values[7]) if 7 in values else None,
        movement_sub_type=int(values[9]) if 9 in values else None,
        channel=int(channel),
        payload_len=len(data),
        has_container=has_container,
        fields_present=present,
    )
    return DecodeResult(True, sample=sample, consumed=pos, total=len(data))


def build_schema_bytes(field_type_codes: Mapping[int, int]) -> bytes:
    schema = 0
    for fnum, (dl, nbits) in SCHEMA_FIELDS.items():
        tc = int(field_type_codes.get(fnum, 0)) & ((1 << nbits) - 1)
        schema |= tc << dl
    return schema.to_bytes(6, "little")


def encode_minimal_025b(
    *,
    net_id: int,
    x: int,
    z: int,
    lut: bytes,
    state: Optional[int] = None,
    sequence: Optional[int] = None,
    speed: Optional[float] = None,
) -> bytes:
    """Synthesize a minimal valid 0x025B payload for roundtrip tests."""
    ciphers = make_ciphers(lut)
    inv = {f: invert_cipher(fn) for f, (_t, fn) in ciphers.items()}

    # Type codes: present fields use a known-read code; others use a skip code.
    tcs = {
        1: 2,
        2: 0,
        3: 2,
        4: 1,
        5: 1,
        6: 0 if state is None else 2,
        7: 0,
        8: 0,
        9: 3,
        10: 1,
        11: 0,
        12: 0,
        13: 0,
        14: 0 if sequence is None else 1,
        15: 0,
        16: 1 if speed is None else 0,
        17: 0,
    }
    body = bytearray(build_schema_bytes(tcs))
    body.extend(write_varint(net_id & 0xFFFFFFFF, inv[4]))
    if state is not None:
        body.extend(write_varint(int(state), inv[6]))
    body.extend(write_varint(pack_xz(x, z), inv[10]))
    if sequence is not None:
        body.append(inv[14](int(sequence) & 0xFF))
    if speed is not None:
        # Decoder reassembles 4 ciphered bytes big-endian then bswaps to LE float.
        # Wire plaintext bytes are therefore the LE float encoding.
        le = struct.pack("<f", float(speed))
        for b in le:
            body.append(inv[16](b))
    return bytes(body)


def inventory_rofl(
    rofl: Path,
    *,
    max_time_s: Optional[float] = None,
    max_blocks_per_chunk: int = 500_000,
) -> dict:
    """E0: time ROFL read + zstd inflate + block walk only (no product emit)."""
    t0 = time.perf_counter()
    info = parse_rofl2(rofl)
    t_read = time.perf_counter()
    extracted = extract_segments(info["payload"])
    t_inflate = time.perf_counter()

    channel_hist: Counter = Counter()
    packet_count = 0
    total_payload_bytes = 0
    frames = 0
    movement_025b = 0
    max_t = 0.0
    chunks = 0
    keyframes = 0

    for seg in extracted["segments"]:
        st = int(seg.get("type") or 0)
        if st == 1:
            chunks += 1
        elif st == 2:
            keyframes += 1
        body = seg.get("bytes") or b""
        if not body:
            continue
        blocks = extract_blocks_py(body, max_blocks=max_blocks_per_chunk)
        for b in blocks:
            t = float(b["time"])
            if max_time_s is not None and t > float(max_time_s):
                continue
            frames += 1
            packet_count += 1
            ch = int(b["channel"]) & 0xFFFF
            channel_hist[ch] += 1
            total_payload_bytes += len(b["payload"])
            if ch == MOVEMENT_PACKET_ID:
                movement_025b += 1
            if t > max_t:
                max_t = t
    t_walk = time.perf_counter()

    top = [{"channel": c, "count": n} for c, n in channel_hist.most_common(25)]
    return {
        "ok": True,
        "mode": "inventory",
        "rofl": str(rofl),
        "gameVersion": (info.get("meta") or {}).get("gameVersion"),
        "matchId": (info.get("meta") or {}).get("matchId")
        or (info.get("meta") or {}).get("gameId"),
        "fileBytes": int(info.get("size") or 0),
        "segments": {
            "chunks": chunks,
            "keyframes": keyframes,
            "total": len(extracted["segments"]),
        },
        "packetCount": packet_count,
        "payloadBytes": total_payload_bytes,
        "frames": frames,
        "maxTimeS": round(max_t, 3),
        "movementPacketId": MOVEMENT_PACKET_ID,
        "movement025bCount": movement_025b,
        "channelHistogramTop": top,
        "timingMs": {
            "roflRead": round((t_read - t0) * 1000, 3),
            "zstdInflate": round((t_inflate - t_read) * 1000, 3),
            "blockWalk": round((t_walk - t_inflate) * 1000, 3),
            "wall": round((t_walk - t0) * 1000, 3),
        },
        "productEligible": False,
        "reason": (
            "movement packet 0x025B absent under current block framing"
            if movement_025b == 0
            else "inventory only; decode required before any product claim"
        ),
    }


def iter_movement_blocks(
    rofl: Path,
    *,
    packet_id: int = MOVEMENT_PACKET_ID,
    max_time_s: Optional[float] = None,
    min_time_s: float = 0.0,
    max_blocks_per_chunk: int = 500_000,
) -> Iterable[dict]:
    info = parse_rofl2(rofl)
    extracted = extract_segments(info["payload"])
    for seg in extracted["segments"]:
        if int(seg.get("type") or 0) != 1:
            continue
        for b in extract_blocks_py(seg["bytes"], max_blocks=max_blocks_per_chunk):
            t = float(b["time"])
            if t < min_time_s:
                continue
            if max_time_s is not None and t > float(max_time_s):
                continue
            if int(b["channel"]) != int(packet_id):
                continue
            yield b


def decode_rofl_movements(
    rofl: Path,
    *,
    lut: bytes,
    packet_id: int = MOVEMENT_PACKET_ID,
    max_time_s: Optional[float] = None,
    min_time_s: float = 0.0,
) -> dict:
    t0 = time.perf_counter()
    info = parse_rofl2(rofl)
    samples: List[MovementSample] = []
    failures: Counter = Counter()
    seen_ids: Counter = Counter()
    coord_ok = 0

    for b in iter_movement_blocks(
        rofl,
        packet_id=packet_id,
        max_time_s=max_time_s,
        min_time_s=min_time_s,
    ):
        res = decode_025b_payload(
            b["payload"],
            time_s=float(b["time"]),
            lut=lut,
            channel=int(b["channel"]),
        )
        if not res.ok or res.sample is None:
            failures[res.error or "decode_failed"] += 1
            continue
        samples.append(res.sample)
        seen_ids[res.sample.net_id] += 1
        if 0 <= res.sample.x <= 15000 and 0 <= res.sample.z <= 15000:
            coord_ok += 1

    wall_ms = (time.perf_counter() - t0) * 1000
    champion_like = [
        nid for nid, _ in seen_ids.most_common() if (nid & 0xFF000000) == 0x40000000
    ]
    return {
        "ok": len(samples) > 0,
        "mode": "decode",
        "decoderVersion": DECODER_VERSION,
        "provenance": PROVENANCE,
        "gameVersion": (info.get("meta") or {}).get("gameVersion"),
        "packetId": int(packet_id),
        "decodedCount": len(samples),
        "uniqueNetIds": len(seen_ids),
        "championLikeNetIds": champion_like[:10],
        "championLikeNetIdCount": len(champion_like),
        "coordInMapApproxCount": coord_ok,
        "failureHistogram": dict(failures.most_common(20)),
        "wallMs": round(wall_ms, 3),
        "samples": [s.as_dict() for s in samples],
        "productEligible": False,
        "kind": "position_samples",
        "nativeMultiWaypoint": False,
    }


def samples_to_maknee_events(
    samples: Sequence[Mapping[str, Any]],
    *,
    game_version: Optional[str] = None,
    packet_id: int = MOVEMENT_PACKET_ID,
) -> dict:
    """Emit one-point WaypointGroup events; never claim native multi-waypoint."""
    events = []
    for s in samples:
        nid = int(s["netId"])
        events.append(
            {
                "WaypointGroup": {
                    "time": float(s["time"]),
                    "waypoints": {
                        str(nid): [{"x": int(s["x"]), "z": int(s["z"])}],
                    },
                    "nativePointSample": True,
                    "kind": "position_samples",
                }
            }
        )
    return {
        "ok": True,
        "provenance": PROVENANCE,
        "decoderVersion": DECODER_VERSION,
        "gameVersion": game_version,
        "patchBuild": game_version,
        "packetId": int(packet_id),
        "nativeMultiWaypoint": False,
        "kind": "position_samples",
        "productEligible": False,
        "eventCount": len(events),
        "events": events,
    }


def _load_oracle_positions(oracle_jsonl: Path) -> List[dict]:
    rows = []
    with oracle_jsonl.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            schema = obj.get("rfc461Schema") or obj.get("eventType") or obj.get("type")
            if schema not in (None, "stats_update") and "participants" not in obj:
                continue
            gt = obj.get("gameTime")
            if gt is None:
                continue
            # Product oracle uses gameTime in milliseconds.
            t_s = float(gt) / 1000.0
            parts = []
            for p in obj.get("participants") or []:
                pos = p.get("position") or {}
                if pos.get("x") is None or pos.get("z") is None:
                    continue
                pid = p.get("participantID") or p.get("participantId")
                if pid is None:
                    continue
                parts.append(
                    {
                        "participantID": int(pid),
                        "x": float(pos["x"]),
                        "z": float(pos["z"]),
                    }
                )
            if parts:
                rows.append({"time": t_s, "participants": parts})
    return rows


def research_oracle_assignment(
    samples: Sequence[Mapping[str, Any]],
    oracle_jsonl: Path,
    *,
    tolerance_s: float = 0.75,
    max_dist: float = 350.0,
) -> dict:
    """Research-only netId→participantID QA. Never product identity binding."""
    oracle = _load_oracle_positions(oracle_jsonl)
    if not oracle:
        return {
            "ok": False,
            "productEligible": False,
            "label": "research_only_not_product",
            "error": "oracle has no position frames",
        }

    # Group samples by netId
    by_nid: Dict[int, List[Tuple[float, float, float]]] = defaultdict(list)
    for s in samples:
        by_nid[int(s["netId"])].append((float(s["time"]), float(s["x"]), float(s["z"])))

    # For each netId, score against each participant via nearest-time matches
    participant_ids = sorted(
        {
            int(p["participantID"])
            for fr in oracle
            for p in fr["participants"]
        }
    )
    scores: Dict[int, Dict[int, List[float]]] = defaultdict(lambda: defaultdict(list))
    for nid, pts in by_nid.items():
        for t, x, z in pts:
            # find oracle frame within tolerance
            best_fr = None
            best_dt = None
            for fr in oracle:
                dt = abs(fr["time"] - t)
                if dt <= tolerance_s and (best_dt is None or dt < best_dt):
                    best_dt = dt
                    best_fr = fr
            if best_fr is None:
                continue
            for p in best_fr["participants"]:
                dist = math.hypot(x - p["x"], z - p["z"])
                if dist <= max_dist:
                    scores[nid][int(p["participantID"])].append(dist)

    # Greedy unique assignment
    candidates = []
    for nid, pid_map in scores.items():
        for pid, dists in pid_map.items():
            if not dists:
                continue
            med = sorted(dists)[len(dists) // 2]
            candidates.append((med, -len(dists), nid, pid, len(dists)))
    candidates.sort()
    used_nids = set()
    used_pids = set()
    assignment = []
    for med, _neg_n, nid, pid, n in candidates:
        if nid in used_nids or pid in used_pids:
            continue
        used_nids.add(nid)
        used_pids.add(pid)
        assignment.append(
            {
                "netId": nid,
                "participantID": pid,
                "matches": n,
                "medianDist": round(med, 3),
            }
        )

    return {
        "ok": len(assignment) >= 1,
        "productEligible": False,
        "label": "research_only_not_product",
        "toleranceS": tolerance_s,
        "maxDist": max_dist,
        "oracleFrames": len(oracle),
        "sampleCount": len(samples),
        "uniqueNetIds": len(by_nid),
        "assignmentCount": len(assignment),
        "assignment": assignment,
        "unassignedNetIds": sorted(set(by_nid) - used_nids)[:50],
        "unassignedParticipantIDs": sorted(set(participant_ids) - used_pids),
        "note": (
            "netId→participantID derived only for QA alignment; "
            "do not use as product identity binding"
        ),
    }


def append_speed_record(
    *,
    log: Path,
    hypothesis: str,
    diff_label: str,
    keep: str,
    reason: str,
    wall_ms: float,
    match_code: str,
    extra: Mapping[str, Any],
    dry_run: bool = False,
) -> dict:
    record = {
        "runId": new_run_id(),
        "ts": utc_now_iso(),
        "matchCode": match_code,
        "backend": "offline-025b",
        "hypothesis": hypothesis,
        "diffLabel": diff_label,
        "wallMs": round(float(wall_ms), 3),
        "keep": keep,
        "reason": reason,
        "productEligible": False,
        "decoderVersion": DECODER_VERSION,
        "provenance": PROVENANCE,
    }
    record.update(dict(extra))
    if not dry_run:
        append_run_record(log, record)
    return record


def _match_code_from_rofl(rofl: Path, info_meta: Optional[Mapping[str, Any]] = None) -> str:
    name = rofl.stem
    if name.upper().startswith("BR1-"):
        return name.split("-", 1)[1]
    if info_meta:
        for k in ("matchId", "gameId"):
            if info_meta.get(k):
                return str(info_meta[k])
    return name


def build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("rofl", type=Path, nargs="?", help="Path to .rofl")
    ap.add_argument(
        "--mode",
        choices=(
            "inventory",
            "decode",
            "maknee-events",
            "oracle-assign",
            "full",
            "scan-wire-ids",
        ),
        default="inventory",
    )
    ap.add_argument(
        "--scan-wire-ids",
        action="store_true",
        help="Alias for --mode scan-wire-ids (Phase B E2 wire-id remap)",
    )
    ap.add_argument(
        "--packet-id",
        type=lambda s: int(s, 0),
        default=None,
        help="Wire channel/packet id to decode (default 0x025B; set after E2 winner)",
    )
    ap.add_argument("--max-time-s", type=float, default=None, help="Inclusive max packet time")
    ap.add_argument("--min-time-s", type=float, default=0.0)
    ap.add_argument("--sample-cap", type=int, default=400, help="E2 bounded samples/channel")
    ap.add_argument("--deep-cap", type=int, default=25000, help="E2 deep decode cap/channel")
    ap.add_argument("--shortlist-size", type=int, default=12)
    ap.add_argument(
        "--try-unicorn",
        action="store_true",
        default=True,
        help="Optional Packet::Packet factory map for shortlist (default on)",
    )
    ap.add_argument("--no-try-unicorn", action="store_true")
    ap.add_argument("--league-binary", type=Path, default=DEFAULT_LEAGUE_BINARY)
    ap.add_argument("--json-out", type=Path, default=None)
    ap.add_argument("--events-out", type=Path, default=None)
    ap.add_argument("--oracle-jsonl", type=Path, default=None)
    ap.add_argument(
        "--oracle-tolerance-s",
        type=float,
        default=0.5,
        help="Oracle time align tolerance seconds (E2 default 0.5 = 500ms)",
    )
    ap.add_argument("--log", type=Path, default=DEFAULT_LOG)
    ap.add_argument("--hypothesis", default="")
    ap.add_argument("--diff-label", default="phase-b-e0-e1")
    ap.add_argument("--append-speed-run", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--match-code", default="")
    return ap


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    if args.rofl is None:
        print("rofl path required", file=sys.stderr)
        return 2
    rofl = Path(args.rofl)
    if not rofl.is_file():
        print(f"missing rofl: {rofl}", file=sys.stderr)
        return 2

    if args.scan_wire_ids:
        args.mode = "scan-wire-ids"
    packet_id = int(args.packet_id) if args.packet_id is not None else MOVEMENT_PACKET_ID
    try_unicorn = bool(args.try_unicorn) and not bool(args.no_try_unicorn)

    lut, lut_prov = load_lut(args.league_binary)
    report: dict

    if args.mode == "scan-wire-ids":
        from rofl2_movement_wire_scan import scan_wire_ids

        t0 = time.perf_counter()
        report = scan_wire_ids(
            rofl,
            lut=lut,
            oracle_jsonl=Path(args.oracle_jsonl) if args.oracle_jsonl else None,
            sample_cap=int(args.sample_cap),
            deep_cap=int(args.deep_cap),
            max_time_s=args.max_time_s,
            min_time_s=args.min_time_s,
            oracle_tolerance_s=float(args.oracle_tolerance_s),
            shortlist_size=int(args.shortlist_size),
            try_unicorn=try_unicorn,
            league_binary=Path(args.league_binary),
        )
        report["lutProvenance"] = lut_prov
        report["decoderVersion"] = DECODER_VERSION
        wall_ms = report.get("endToEndWallMs") or ((time.perf_counter() - t0) * 1000)
        keep = "discard"
        reason = report.get("reason") or "E2 scan complete"
        # Research keep only if winner; still not product.
        if report.get("winnerFound"):
            keep = "discard"  # research candidate recorded; product keep stays false
            reason = report["reason"] + "; research-only (not product)"
        if args.append_speed_run:
            rec = append_speed_record(
                log=args.log,
                hypothesis=args.hypothesis
                or "E2: wire packet-id remap scan vs 0x025B schema+oracle",
                diff_label=args.diff_label or "phase-b-e2.1-blockparam",
                keep="discard",
                reason=reason,
                wall_ms=float(wall_ms),
                match_code=args.match_code or _match_code_from_rofl(rofl),
                dry_run=args.dry_run,
                extra={
                    "phase": report.get("phase") or "B-E2.1",
                    "methodology": report.get("methodology"),
                    "winnerFound": bool(report.get("winnerFound")),
                    "winner": report.get("winner"),
                    "channelsScanned": report.get("channelsScanned"),
                    "endToEndWallMs": report.get("endToEndWallMs"),
                    "nextSingleVariableHypothesis": report.get(
                        "nextSingleVariableHypothesis"
                    ),
                    "statsUpdateCount": 0,
                    "source": "offline_wire_id_scan_e2_1",
                    "researchKeep": report.get("keep"),
                    "priorE2": report.get("priorE2"),
                },
            )
            report["speedRun"] = rec

        # If winner and events requested, run configurable packet-id decode.
        if report.get("winnerFound") and report.get("winner"):
            win_id = int(report["winner"]["channel"])
            decoded = decode_rofl_movements(
                rofl,
                lut=lut,
                packet_id=win_id,
                max_time_s=args.max_time_s,
                min_time_s=args.min_time_s,
            )
            report["winnerFullDecode"] = {
                k: decoded[k]
                for k in decoded
                if k != "samples"
            }
            report["winnerFullDecode"]["samplePreview"] = (decoded.get("samples") or [])[
                :10
            ]
            if args.events_out is not None:
                events = samples_to_maknee_events(
                    decoded.get("samples") or [],
                    game_version=decoded.get("gameVersion"),
                    packet_id=win_id,
                )
                args.events_out.parent.mkdir(parents=True, exist_ok=True)
                args.events_out.write_text(
                    json.dumps(events, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                report["eventsOut"] = str(args.events_out)

    elif args.mode == "inventory":
        report = inventory_rofl(rofl, max_time_s=args.max_time_s)
        report["lutProvenance"] = lut_prov
        report["decoderVersion"] = DECODER_VERSION
        keep = "discard"
        reason = report["reason"]
        if report["movement025bCount"] == 0:
            reason = (
                "E0: 0x025B count=0 under extract_blocks_py channel framing; "
                "no product emit"
            )
        if args.append_speed_run:
            rec = append_speed_record(
                log=args.log,
                hypothesis=args.hypothesis
                or "E0 inventory: ROFL read+zstd+block walk; count 0x025B",
                diff_label=args.diff_label or "phase-b-e0-inventory",
                keep=keep,
                reason=reason,
                wall_ms=report["timingMs"]["wall"],
                match_code=args.match_code or _match_code_from_rofl(rofl),
                dry_run=args.dry_run,
                extra={
                    "phase": "B-E0",
                    "movement025bCount": report["movement025bCount"],
                    "packetCount": report["packetCount"],
                    "payloadBytes": report["payloadBytes"],
                    "timingMs": report["timingMs"],
                    "channelHistogramTop": report["channelHistogramTop"][:10],
                    "statsUpdateCount": 0,
                    "source": "offline_inventory",
                },
            )
            report["speedRun"] = rec
    else:
        t0 = time.perf_counter()
        decoded = decode_rofl_movements(
            rofl,
            lut=lut,
            packet_id=packet_id,
            max_time_s=args.max_time_s,
            min_time_s=args.min_time_s,
        )
        decoded["lutProvenance"] = lut_prov
        samples = decoded.get("samples") or []
        report = dict(decoded)

        if args.mode in ("maknee-events", "full"):
            events = samples_to_maknee_events(
                samples,
                game_version=decoded.get("gameVersion"),
                packet_id=packet_id,
            )
            report["maknee"] = {
                k: events[k]
                for k in events
                if k != "events"
            }
            if args.events_out is not None:
                args.events_out.parent.mkdir(parents=True, exist_ok=True)
                args.events_out.write_text(
                    json.dumps(events, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                report["eventsOut"] = str(args.events_out)

        if args.mode in ("oracle-assign", "full") and args.oracle_jsonl:
            from rofl2_movement_wire_scan import optimal_oracle_assignment

            oracle_frames = _load_oracle_positions(Path(args.oracle_jsonl))
            report["oracleAssignment"] = optimal_oracle_assignment(
                samples,
                oracle_frames,
                tolerance_s=float(args.oracle_tolerance_s),
            )

        wall_ms = (time.perf_counter() - t0) * 1000
        report["endToEndWallMs"] = round(wall_ms, 3)

        keep = "discard"
        if decoded["decodedCount"] > 0 and decoded.get("ok"):
            keep = "keep-research" if wall_ms <= 60_000 else "discard"
            reason = (
                f"decoded {decoded['decodedCount']} samples on packet_id="
                f"{packet_id:#x} ({decoded['uniqueNetIds']} netIds)"
            )
            if wall_ms > 60_000:
                reason += f"; wall {wall_ms:.0f}ms > 60s target"
        else:
            inv = inventory_rofl(rofl, max_time_s=args.max_time_s)
            report["inventory"] = {
                "movement025bCount": inv["movement025bCount"],
                "packetCount": inv["packetCount"],
                "timingMs": inv["timingMs"],
                "channelHistogramTop": inv["channelHistogramTop"][:10],
            }
            reason = (
                f"E1 discard: packet_id={packet_id:#x} decoded=0; "
                f"movement025bCount={inv['movement025bCount']}; "
                f"decodeFailures={decoded.get('failureHistogram')}"
            )

        if args.append_speed_run:
            rec = append_speed_record(
                log=args.log,
                hypothesis=args.hypothesis
                or "E1: clean-room 0x025B-schema movement decode",
                diff_label=args.diff_label or "phase-b-e1-025b",
                keep="discard",
                reason=reason,
                wall_ms=wall_ms,
                match_code=args.match_code or _match_code_from_rofl(rofl),
                dry_run=args.dry_run,
                extra={
                    "phase": "B-E1",
                    "packetId": packet_id,
                    "decodedCount": decoded["decodedCount"],
                    "uniqueNetIds": decoded["uniqueNetIds"],
                    "championLikeNetIds": decoded.get("championLikeNetIds"),
                    "failureHistogram": decoded.get("failureHistogram"),
                    "movement025bCount": (report.get("inventory") or {}).get(
                        "movement025bCount"
                    ),
                    "statsUpdateCount": 0,
                    "source": "offline_025b_decode",
                    "researchKeep": keep,
                },
            )
            report["speedRun"] = rec
            report["discardReason"] = reason

    # Drop huge sample arrays from stdout when writing to file
    stdout_report = dict(report)
    if args.json_out is not None:
        # Compact scan report for disk: drop per-channel decoded sample caches
        disk_report = dict(report)
        if "allChannelsCompact" in disk_report and args.mode == "scan-wire-ids":
            # already compact
            pass
        for key in ("samples",):
            if key in disk_report and isinstance(disk_report[key], list) and len(disk_report[key]) > 50:
                disk_report[key] = disk_report[key][:50]
                disk_report[f"{key}Truncated"] = True
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(
            json.dumps(disk_report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        stdout_report["jsonOut"] = str(args.json_out)
        if "samples" in stdout_report and len(stdout_report.get("samples") or []) > 20:
            stdout_report["samples"] = stdout_report["samples"][:20]
            stdout_report["samplesTruncated"] = True
        if "allChannelsCompact" in stdout_report:
            stdout_report["allChannelsCompact"] = stdout_report["allChannelsCompact"][:15]
            stdout_report["channelsCompactTruncated"] = True

    print(json.dumps(stdout_report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
