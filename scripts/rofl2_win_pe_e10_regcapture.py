#!/usr/bin/env python3
"""E10: Windows 16.14 register-level coordinate discovery (Maknee-style).

Search for plaintext hero X/Z transiently present in XMM/GPR (or object writes)
during constructed factory→Deserialize, using same-match BR1 Replay API only as
QA/search oracle.

Hard constraints: no live API, no plan edit, no commit, no binary vendoring,
no learned affine / arbitrary curve fitting. Axis swap only if train+holdout
both improve. Known ``2*i16 + SR_center`` only when integer/cvt structure fits.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
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
from rofl2_movement_decode import (  # noqa: E402
    _load_oracle_positions,
    append_speed_record,
)
from rofl2_movement_wire_scan import (  # noqa: E402
    PROVEN_HERO_NET_ID_SET,
    PROVEN_HERO_NET_IDS,
    optimal_oracle_assignment,
)
from rofl2_probe import extract_segments, parse_rofl2  # noqa: E402
from rofl2_unicorn_packet_drive import extract_blocks_py  # noqa: E402
from rofl2_win_pe_packet_discover import (  # noqa: E402
    BUF_BASE,
    EXPECTED_SHA256,
    SCRATCH_BASE,
    STACK_BASE,
    WinX64PacketEmu,
    enumerate_rofl,
    official_provenance,
    scan_msvc_packet_types,
)

PROBE_VERSION = "e10-win-pe-regcapture-v1"
MATCH_CODE = "3264361042"
DEFAULT_PE = Path("/tmp/League-of-Legends-16.14-win.exe")
DEFAULT_ROFL = Path.home() / "Documents/League of Legends/Replays/BR1-3264361042.rofl"
DEFAULT_ORACLE = Path("artifacts/rofl/3264361042/events.rfc461.jsonl")
DEFAULT_REPORT = Path("docs/rofl-research/movement-win-pe-e10-BR1-3264361042.json")
SPEED_LOG = Path("docs/rofl-research/speed-runs.jsonl")
E21_REPORT = Path("docs/rofl-research/movement-wire-scan-E2.1-BR1-3264361042.json")

# E2.1 all-10 hero-param channels (priority order) + E8 semantic movement ops.
E21_PRIORITY = [
    351,
    259,
    1194,
    921,
    398,
    632,
    210,
    243,
    774,
    861,
    197,
    908,
    788,
    535,
    920,
]
E8_MOVEMENT_OPS = [1104, 58, 513, 840, 420, 450]
# Broad SR search range (not product clip).
SR_MIN = -200.0
SR_MAX = 16000.0
# Mowokuma/ROFL public PathPacket centers (test only with i16 structure).
SR_CENTER_X = 7358
SR_CENTER_Z = 7412

ACCEPT_MIN_SAMPLES = 80
ACCEPT_MIN_HEROES = 5
ACCEPT_MAX_MEDIAN = 120.0
ACCEPT_MAX_P95 = 350.0
ACCEPT_MAX_MAX = 800.0
SEARCH_TOL = 150.0
ORACLE_TOL_S = 0.5

MAX_INSNS = 80_000
SAMPLE_EVERY = 48
MAX_XMM = 8
MAX_TRAIN_PER_OP = 10
MAX_HOLDOUT_PER_OP = 8
MAX_OPS = 18
MAX_DEPTH_HELPERS = 3  # documented bound; capture stays in Deserialize call tree via insn cap


def _hex(v: Optional[int]) -> Optional[str]:
    return None if v is None else hex(int(v))


def load_e21_priority() -> List[int]:
    if E21_REPORT.is_file():
        try:
            rows = json.loads(E21_REPORT.read_text()).get("heroParamChannelTable") or []
            out = [
                int(r["channel"])
                for r in rows
                if r.get("hasAll10HeroParams") and int(r.get("heroBlockCount") or 0) >= 500
            ]
            if out:
                return out[:15]
        except Exception:  # noqa: BLE001
            pass
    return list(E21_PRIORITY)


def collect_hero_samples(
    rofl: Path,
    opcodes: Sequence[int],
    *,
    train_n: int,
    holdout_n: int,
    min_time_s: float = 60.0,
    max_time_s: float = 1600.0,
) -> Dict[int, Dict[str, List[dict]]]:
    """Collect hero-param blocks across early/mid/late eras inside oracle window."""
    want = set(int(o) for o in opcodes)
    buckets: Dict[int, List[dict]] = defaultdict(list)
    info = parse_rofl2(rofl)
    for seg in extract_segments(info["payload"])["segments"]:
        if int(seg.get("type") or 0) != 1:
            continue
        for b in extract_blocks_py(seg["bytes"], max_blocks=500_000):
            op = int(b["channel"])
            if op not in want:
                continue
            t = float(b["time"])
            if t < min_time_s or t > max_time_s:
                continue
            param = int(b.get("param") or 0)
            if param not in PROVEN_HERO_NET_ID_SET:
                continue
            pay = b.get("payload") or b""
            if len(pay) < 4:
                continue
            buckets[op].append(
                {
                    "time": t,
                    "param": param,
                    "payload": pay,
                    "wireSize": len(pay),
                }
            )
    out: Dict[int, Dict[str, List[dict]]] = {}
    need = train_n + holdout_n
    for op, rows in buckets.items():
        rows = sorted(rows, key=lambda r: r["time"])
        if len(rows) < max(6, need // 2):
            continue
        t0, t1 = rows[0]["time"], rows[-1]["time"]
        span = max(1e-3, t1 - t0)
        thirds: List[List[dict]] = [[] for _ in range(3)]
        for r in rows:
            idx = min(2, int(3 * (r["time"] - t0) / span))
            thirds[idx].append(r)
        picked: List[dict] = []
        per = max(1, (need + 2) // 3)
        for bucket in thirds:
            if not bucket:
                continue
            step = max(1, len(bucket) // per)
            picked.extend(bucket[::step][:per])
        by_hero: Dict[int, List[dict]] = defaultdict(list)
        for r in picked:
            by_hero[int(r["param"])].append(r)
        diversified: List[dict] = []
        heroes = list(by_hero.keys())
        i = 0
        while len(diversified) < need and heroes:
            h = heroes[i % len(heroes)]
            if by_hero[h]:
                diversified.append(by_hero[h].pop(0))
            else:
                heroes = [x for x in heroes if by_hero[x]]
                if not heroes:
                    break
                continue
            i += 1
        if len(diversified) < need:
            seen = {(r["time"], r["param"]) for r in diversified}
            for r in rows:
                key = (r["time"], r["param"])
                if key in seen:
                    continue
                diversified.append(r)
                if len(diversified) >= need:
                    break
        diversified = sorted(diversified, key=lambda r: r["time"])
        train, hold = [], []
        for i, r in enumerate(diversified):
            (hold if i % 3 == 2 else train).append(r)
        out[op] = {"train": train[:train_n], "holdout": hold[:holdout_n]}
    return out


def nearest_oracle_frame(
    frames: Sequence[Mapping[str, Any]],
    times: Sequence[float],
    t: float,
    tol_s: float = ORACLE_TOL_S,
) -> Optional[Mapping[str, Any]]:
    if not frames:
        return None
    lo, hi = 0, len(times) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        if times[mid] < t:
            lo = mid + 1
        else:
            hi = mid - 1
    best = None
    best_dt = None
    for i in (lo - 2, lo - 1, lo, lo + 1):
        if 0 <= i < len(frames):
            dt = abs(times[i] - t)
            if dt <= tol_s and (best_dt is None or dt < best_dt):
                best_dt = dt
                best = frames[i]
    return best


def _f32_ok(v: float) -> bool:
    return v == v and SR_MIN <= v <= SR_MAX and abs(v) > 1e-3


def interpret_i16_pair(raw: bytes) -> Optional[Tuple[float, float]]:
    """Public PathPacket integer transform — only when two i16 present and non-trivial."""
    if len(raw) < 4:
        return None
    ix, iz = struct.unpack_from("<hh", raw, 0)
    if ix == 0 and iz == 0:
        return None
    if abs(ix) < 8 and abs(iz) < 8:
        return None
    x = float(2 * ix + SR_CENTER_X)
    z = float(2 * iz + SR_CENTER_Z)
    if _f32_ok(x) and _f32_ok(z):
        return x, z
    return None


class RegCapture:
    """Bounded instruction sampling of XMM lanes + GPR low32-as-f32 + obj writes."""

    def __init__(self, emu: WinX64PacketEmu, *, obj: int, object_size: int):
        from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_WRITE, UC_MEM_WRITE
        from unicorn.x86_const import (
            UC_X86_REG_EAX,
            UC_X86_REG_ECX,
            UC_X86_REG_EDX,
            UC_X86_REG_R8D,
            UC_X86_REG_R9D,
            UC_X86_REG_XMM0,
            UC_X86_REG_XMM1,
            UC_X86_REG_XMM2,
            UC_X86_REG_XMM3,
            UC_X86_REG_XMM4,
            UC_X86_REG_XMM5,
            UC_X86_REG_XMM6,
            UC_X86_REG_XMM7,
        )

        self.emu = emu
        self.obj = obj
        self.object_size = max(object_size, 64)
        self.insn = 0
        self.fault_pcs: List[str] = []
        self.hits: List[dict] = []  # {pc, site, value, kind}
        self.write_hits: List[dict] = []
        self._xmm = [
            UC_X86_REG_XMM0,
            UC_X86_REG_XMM1,
            UC_X86_REG_XMM2,
            UC_X86_REG_XMM3,
            UC_X86_REG_XMM4,
            UC_X86_REG_XMM5,
            UC_X86_REG_XMM6,
            UC_X86_REG_XMM7,
        ][:MAX_XMM]
        self._gpr = [
            ("eax", UC_X86_REG_EAX),
            ("ecx", UC_X86_REG_ECX),
            ("edx", UC_X86_REG_EDX),
            ("r8d", UC_X86_REG_R8D),
            ("r9d", UC_X86_REG_R9D),
        ]
        self._hooks = []

        def on_code(uc, address, size, user):  # noqa: ANN001, ARG001
            self.insn += 1
            if self.insn > MAX_INSNS:
                uc.emu_stop()
                return
            if self.insn % SAMPLE_EVERY != 0:
                return
            pc = int(address)
            # XMM lanes
            for xi, reg in enumerate(self._xmm):
                try:
                    val = uc.reg_read(reg)
                    if isinstance(val, (bytes, bytearray, memoryview)):
                        raw = bytes(val)[:16]
                    elif isinstance(val, int):
                        raw = int(val).to_bytes(16, "little", signed=False)
                    else:
                        continue
                except Exception:  # noqa: BLE001
                    continue
                for lane in range(4):
                    f = struct.unpack_from("<f", raw, lane * 4)[0]
                    if _f32_ok(f):
                        self.hits.append(
                            {
                                "pc": pc,
                                "site": f"xmm{xi}[{lane}]",
                                "value": float(f),
                                "kind": "xmm",
                            }
                        )
                # i16 transform only when structure is non-trivial (not center-only).
                pair = interpret_i16_pair(raw[:4])
                if pair and abs(pair[0] - SR_CENTER_X) > 50 and abs(pair[1] - SR_CENTER_Z) > 50:
                    self.hits.append(
                        {
                            "pc": pc,
                            "site": f"xmm{xi}.i16xz",
                            "value": pair[0],
                            "valueZ": pair[1],
                            "kind": "i16_transform",
                        }
                    )
            # GPR low32 as f32
            for name, reg in self._gpr:
                try:
                    g = int(uc.reg_read(reg)) & 0xFFFFFFFF
                    f = struct.unpack("<f", struct.pack("<I", g))[0]
                except Exception:  # noqa: BLE001
                    continue
                if _f32_ok(f):
                    self.hits.append(
                        {"pc": pc, "site": name, "value": float(f), "kind": "gpr"}
                    )

        def on_write(uc, access, address, size, value, user):  # noqa: ANN001, ARG001
            if access != UC_MEM_WRITE:
                return
            if not (self.obj <= int(address) < self.obj + self.object_size):
                return
            if size not in (4, 8):
                return
            off = int(address) - self.obj
            try:
                if size == 4:
                    raw = struct.pack("<I", int(value) & 0xFFFFFFFF)
                    f = struct.unpack("<f", raw)[0]
                    if _f32_ok(f):
                        self.write_hits.append(
                            {
                                "pc": int(uc.reg_read(emu._regs["rip"])),
                                "site": f"obj+{off}",
                                "value": float(f),
                                "kind": "obj_write",
                            }
                        )
                else:
                    raw = struct.pack("<Q", int(value) & 0xFFFFFFFFFFFFFFFF)
                    for lane, base in enumerate((0, 4)):
                        f = struct.unpack_from("<f", raw, base)[0]
                        if _f32_ok(f):
                            self.write_hits.append(
                                {
                                    "pc": int(uc.reg_read(emu._regs["rip"])),
                                    "site": f"obj+{off}+{base}",
                                    "value": float(f),
                                    "kind": "obj_write",
                                }
                            )
            except Exception:  # noqa: BLE001
                return

        self._hooks.append(emu.mu.hook_add(UC_HOOK_CODE, on_code))
        try:
            self._hooks.append(
                emu.mu.hook_add(
                    UC_HOOK_MEM_WRITE,
                    on_write,
                    begin=obj,
                    end=obj + self.object_size,
                )
            )
        except Exception:  # noqa: BLE001
            # Some Unicorn builds want unrestricted mem hooks; skip writes.
            pass

    def close(self) -> None:
        for h in self._hooks:
            try:
                self.emu.mu.hook_del(h)
            except Exception:  # noqa: BLE001
                pass


def deserialize_with_capture(
    emu: WinX64PacketEmu,
    *,
    obj: int,
    deser_va: int,
    payload: bytes,
    object_size: int,
) -> dict:
    cap = RegCapture(emu, obj=obj, object_size=object_size)
    stop = STACK_BASE + 0x880
    emu.mu.mem_write(stop, b"\xc3")
    buf = BUF_BASE + 0x10000
    emu.mu.mem_write(buf, payload + b"\x00" * 16)
    cursor_slot = SCRATCH_BASE + 0x2000
    emu.mu.mem_write(cursor_slot, struct.pack("<Q", buf))
    end = buf + len(payload)
    rsp = STACK_BASE + 0x100000 - 0x80
    emu.mu.mem_write(rsp, struct.pack("<Q", stop))
    emu._set("rsp", rsp - 0x20)
    emu._set("rbp", rsp)
    emu._set("rcx", obj)
    emu._set("rdx", cursor_slot)
    emu._set("r8", end)
    emu._set("r9", 0)
    emu._set("rax", 0)
    err = None
    fail_pc = None
    try:
        emu.mu.emu_start(deser_va, stop, timeout=8_000_000, count=MAX_INSNS + 1000)
    except Exception as exc:  # noqa: BLE001
        err = str(exc)
        try:
            fail_pc = hex(emu._reg("rip"))
        except Exception:  # noqa: BLE001
            fail_pc = None
        if fail_pc:
            cap.fault_pcs.append(fail_pc)
    consumed = max(0, struct.unpack("<Q", bytes(emu.mu.mem_read(cursor_slot, 8)))[0] - buf)
    # Final object scan for f32
    try:
        after = bytes(emu.mu.mem_read(obj, max(object_size, 0x40)))
    except Exception:  # noqa: BLE001
        after = b""
    for off in range(0, max(0, len(after) - 3), 4):
        f = struct.unpack_from("<f", after, off)[0]
        if _f32_ok(f):
            cap.hits.append(
                {
                    "pc": deser_va,
                    "site": f"final_obj+{off}",
                    "value": float(f),
                    "kind": "final_obj",
                }
            )
    cap.close()
    return {
        "error": err,
        "failurePc": fail_pc,
        "consumed": consumed,
        "insns": cap.insn,
        "hits": cap.hits,
        "writeHits": cap.write_hits,
        "faultPcs": list(cap.fault_pcs),
        "retAl": emu._reg("rax") & 0xFF,
    }


def match_hits_to_oracle(
    hits: Sequence[Mapping[str, Any]],
    frame: Mapping[str, Any],
    *,
    tol: float = SEARCH_TOL,
) -> List[dict]:
    """Tag hits that land near any participant x or z (search only)."""
    out = []
    parts = frame.get("participants") or []
    for h in hits:
        v = float(h["value"])
        # paired i16 transform emits both
        if h.get("kind") == "i16_transform" and "valueZ" in h:
            vz = float(h["valueZ"])
            for p in parts:
                pid = int(p["participantID"])
                dx = abs(v - float(p["x"]))
                dz = abs(vz - float(p["z"]))
                if dx <= tol and dz <= tol:
                    out.append(
                        {
                            **h,
                            "axis": "pair",
                            "participantID": pid,
                            "err": math.hypot(dx, dz),
                            "oracleX": float(p["x"]),
                            "oracleZ": float(p["z"]),
                        }
                    )
            continue
        for p in parts:
            pid = int(p["participantID"])
            dx = abs(v - float(p["x"]))
            dz = abs(v - float(p["z"]))
            if dx <= tol and dx <= dz:
                out.append(
                    {
                        **h,
                        "axis": "x",
                        "participantID": pid,
                        "err": dx,
                        "oracleX": float(p["x"]),
                        "oracleZ": float(p["z"]),
                    }
                )
            elif dz <= tol:
                out.append(
                    {
                        **h,
                        "axis": "z",
                        "participantID": pid,
                        "err": dz,
                        "oracleX": float(p["x"]),
                        "oracleZ": float(p["z"]),
                    }
                )
    return out


def build_pair_candidates(
    sample_matches: Sequence[Mapping[str, Any]],
) -> Dict[Tuple, List[dict]]:
    """
    Aggregate (opcode, pcX, siteX, pcZ, siteZ, swap) → list of {time,netId,x,z,err}.
    Direct pairs only; swap is a separate key.
    """
    # Group matches by sample id
    by_sample: Dict[Any, List[dict]] = defaultdict(list)
    for m in sample_matches:
        by_sample[m["sampleKey"]].append(m)

    pairs: Dict[Tuple, List[dict]] = defaultdict(list)
    for sk, ms in by_sample.items():
        # Prefer i16 pair hits
        for m in ms:
            if m.get("axis") == "pair":
                key = (
                    m["opcode"],
                    m["pc"],
                    m["site"],
                    m["pc"],
                    m["site"],
                    False,
                    "i16_transform",
                )
                pairs[key].append(
                    {
                        "time": m["time"],
                        "netId": m["netId"],
                        "x": float(m["value"]),
                        "z": float(m["valueZ"]),
                        "err": m["err"],
                        "participantID": m["participantID"],
                    }
                )
        xs = [m for m in ms if m.get("axis") == "x"]
        zs = [m for m in ms if m.get("axis") == "z"]
        # Same participant only
        for mx in xs:
            for mz in zs:
                if mx["participantID"] != mz["participantID"]:
                    continue
                if mx["kind"] != mz["kind"] and not (
                    mx["kind"] in ("xmm", "gpr", "obj_write", "final_obj")
                ):
                    continue
                for swap in (False, True):
                    if swap:
                        x, z = float(mz["value"]), float(mx["value"])
                        key = (
                            mx["opcode"],
                            mz["pc"],
                            mz["site"],
                            mx["pc"],
                            mx["site"],
                            True,
                            "direct",
                        )
                    else:
                        x, z = float(mx["value"]), float(mz["value"])
                        key = (
                            mx["opcode"],
                            mx["pc"],
                            mx["site"],
                            mz["pc"],
                            mz["site"],
                            False,
                            "direct",
                        )
                    err = math.hypot(x - float(mx["oracleX"]), z - float(mx["oracleZ"]))
                    pairs[key].append(
                        {
                            "time": mx["time"],
                            "netId": mx["netId"],
                            "x": x,
                            "z": z,
                            "err": err,
                            "participantID": mx["participantID"],
                        }
                    )
    return pairs


def score_pair_list(rows: Sequence[Mapping[str, Any]]) -> dict:
    if not rows:
        return {
            "n": 0,
            "heroes": 0,
            "median": None,
            "p95": None,
            "max": None,
            "ok": False,
        }
    # Dedup by (netId,time) keeping min err
    best: Dict[Tuple[int, float], dict] = {}
    for r in rows:
        k = (int(r["netId"]), round(float(r["time"]), 3))
        if k not in best or float(r["err"]) < float(best[k]["err"]):
            best[k] = r
    vals = sorted(float(r["err"]) for r in best.values())
    heroes = len({int(r["netId"]) for r in best.values()})
    med = float(statistics.median(vals))
    p95 = float(vals[int(0.95 * (len(vals) - 1))])
    mx = float(vals[-1])
    return {
        "n": len(vals),
        "heroes": heroes,
        "median": round(med, 3),
        "p95": round(p95, 3),
        "max": round(mx, 3),
        "ok": (
            len(vals) >= ACCEPT_MIN_SAMPLES
            and heroes >= ACCEPT_MIN_HEROES
            and med <= ACCEPT_MAX_MEDIAN
            and p95 <= ACCEPT_MAX_P95
            and mx <= ACCEPT_MAX_MAX
        ),
    }


def run_capture_pass(
    binary,
    factories: Mapping[int, Mapping[str, Any]],
    samples_by_op: Mapping[int, Sequence[dict]],
    oracle_frames: Sequence[Mapping[str, Any]],
    *,
    label: str,
) -> Tuple[List[dict], dict]:
    oracle_times = [float(fr["time"]) for fr in oracle_frames]
    all_matches: List[dict] = []
    meta = {
        "label": label,
        "opcodesAttempted": 0,
        "samplesAttempted": 0,
        "constructOk": 0,
        "deserializeRuns": 0,
        "faultPcs": Counter(),
        "hitCounts": Counter(),
    }
    for op, rows in samples_by_op.items():
        fac = factories.get(op)
        if not fac or not fac.get("deserializeVa") or not fac.get("ctorVa"):
            continue
        meta["opcodesAttempted"] += 1
        for i, blk in enumerate(rows):
            meta["samplesAttempted"] += 1
            emu = WinX64PacketEmu(binary)
            fac_res = emu.construct(
                ctor_va=int(fac["ctorVa"]),
                object_size=int(fac.get("objectSize") or 64),
                expected_opcode=op,
                expected_vptr=int(fac["vptr"]),
            )
            if not fac_res.get("ok"):
                continue
            meta["constructOk"] += 1
            fr = nearest_oracle_frame(oracle_frames, oracle_times, float(blk["time"]))
            if fr is None:
                continue
            cap = deserialize_with_capture(
                emu,
                obj=int(fac_res["obj"]),
                deser_va=int(fac["deserializeVa"]),
                payload=blk["payload"],
                object_size=int(fac.get("objectSize") or 64),
            )
            meta["deserializeRuns"] += 1
            for fp in cap.get("faultPcs") or []:
                meta["faultPcs"][fp] += 1
            if cap.get("failurePc"):
                meta["faultPcs"][cap["failurePc"]] += 1
            hits = list(cap.get("hits") or []) + list(cap.get("writeHits") or [])
            meta["hitCounts"]["rawHits"] += len(hits)
            matched = match_hits_to_oracle(hits, fr, tol=SEARCH_TOL)
            meta["hitCounts"]["oracleTagged"] += len(matched)
            sk = (op, i, float(blk["time"]), int(blk["param"]))
            for m in matched:
                all_matches.append(
                    {
                        **m,
                        "opcode": op,
                        "time": float(blk["time"]),
                        "netId": int(blk["param"]),
                        "sampleKey": sk,
                        "split": label,
                    }
                )
    meta["faultPcs"] = dict(meta["faultPcs"].most_common(12))
    meta["hitCounts"] = dict(meta["hitCounts"])
    return all_matches, meta


def evaluate_candidates(
    train_matches: Sequence[Mapping[str, Any]],
    holdout_matches: Sequence[Mapping[str, Any]],
) -> dict:
    train_pairs = build_pair_candidates(train_matches)
    hold_pairs = build_pair_candidates(holdout_matches)

    ranked = []
    for key, rows in train_pairs.items():
        tr = score_pair_list(rows)
        if tr["n"] < 10:
            continue
        hr = score_pair_list(hold_pairs.get(key) or [])
        opcode, pcx, sitex, pcz, sitez, swap, kind = key
        ranked.append(
            {
                "opcode": opcode,
                "pcX": _hex(pcx),
                "siteX": sitex,
                "pcZ": _hex(pcz),
                "siteZ": sitez,
                "swap": swap,
                "kind": kind,
                "train": tr,
                "holdout": hr,
                "bothOk": bool(tr["ok"] and hr["ok"]),
                "rankScore": (
                    (0 if not tr["ok"] else 1000)
                    + (0 if not hr.get("ok") else 500)
                    + tr["n"]
                    + 0.1 * (hr["n"] or 0)
                    - (tr["median"] or 1e6) / 10.0
                ),
            }
        )
    ranked.sort(key=lambda r: -r["rankScore"])

    # Axis-swap gate: only accept swap if both splits improve vs unswapped twin
    winners = [r for r in ranked if r["bothOk"]]
    if winners:
        w = winners[0]
        if w["swap"]:
            twin = next(
                (
                    r
                    for r in ranked
                    if r["opcode"] == w["opcode"]
                    and r["pcX"] == w["pcZ"]
                    and r["pcZ"] == w["pcX"]
                    and r["siteX"] == w["siteZ"]
                    and r["siteZ"] == w["siteX"]
                    and r["swap"] is False
                ),
                None,
            )
            if twin and (
                (twin["train"]["median"] or 1e9) <= (w["train"]["median"] or 0)
                or (twin["holdout"]["median"] or 1e9) <= (w["holdout"]["median"] or 0)
            ):
                # Swap does not improve both — demote
                w = None
                winners = [r for r in winners if not r["swap"]] or winners[1:]
                w = winners[0] if winners else None
        winner = w
    else:
        winner = None

    return {
        "rankedTop": ranked[:20],
        "winner": winner,
        "winnerFound": winner is not None,
        "trainPairKeys": len(train_pairs),
        "holdoutPairKeys": len(hold_pairs),
    }


def run_e10(
    *,
    pe_path: Path,
    rofl: Path,
    oracle_jsonl: Path,
    report_path: Path,
    dry_run: bool = False,
) -> dict:
    t0 = time.perf_counter()
    if not pe_path.is_file():
        raise FileNotFoundError(pe_path)
    binary = load_binary(pe_path)
    if binary.platform != "windows" or binary.format != "pe64" or binary.arch != "x86_64":
        raise ValueError(
            f"expected windows pe64 x86_64, got {binary.platform}/{binary.format}/{binary.arch}"
        )
    if binary.sha256 != EXPECTED_SHA256:
        raise ValueError(f"SHA256 mismatch: got {binary.sha256}, expected {EXPECTED_SHA256}")

    prov = official_provenance(size=pe_path.stat().st_size, sha256=binary.sha256)
    man = research_manifest(
        binary, patch="16.14", extra={"probeVersion": PROBE_VERSION, "official": prov}
    )

    counts, _ = enumerate_rofl(rofl)
    rows, coverage = scan_msvc_packet_types(binary, counts)
    factories = {int(r["opcode"]): r for r in rows}

    priority = load_e21_priority()
    opcodes = []
    for op in priority + E8_MOVEMENT_OPS + [107, 556]:
        if op in factories and op not in opcodes:
            opcodes.append(op)
        if len(opcodes) >= MAX_OPS:
            break

    sample_sets = collect_hero_samples(
        rofl, opcodes, train_n=MAX_TRAIN_PER_OP, holdout_n=MAX_HOLDOUT_PER_OP
    )
    # Prefer cadence/payload variability: sort ops by distinct wire sizes * heroes in train
    def var_score(op: int) -> float:
        tr = sample_sets.get(op, {}).get("train") or []
        sizes = {len(s["payload"]) for s in tr}
        heroes = {s["param"] for s in tr}
        return len(sizes) * 10 + len(heroes) + math.log1p(counts.get(op, 0))

    ordered_ops = sorted(sample_sets.keys(), key=var_score, reverse=True)
    train_map = {op: sample_sets[op]["train"] for op in ordered_ops}
    hold_map = {op: sample_sets[op]["holdout"] for op in ordered_ops}

    oracle = _load_oracle_positions(oracle_jsonl) if oracle_jsonl.is_file() else []

    train_matches, train_meta = run_capture_pass(
        binary, factories, train_map, oracle, label="train"
    )
    hold_matches, hold_meta = run_capture_pass(
        binary, factories, hold_map, oracle, label="holdout"
    )

    # Fallback: if hero-param path yields nothing, scan a few high-block opcodes
    # whose decoded object contains a proven netId even when blockParam does not.
    fallback_meta = None
    if len(train_matches) < 20:
        fb_ops = [
            op
            for op, _ in sorted(counts.items(), key=lambda kv: -kv[1])[:8]
            if op in factories
        ]
        fb_samples: Dict[int, List[dict]] = {}
        info = parse_rofl2(rofl)
        for op in fb_ops:
            got = []
            for seg in extract_segments(info["payload"])["segments"]:
                if int(seg.get("type") or 0) != 1:
                    continue
                for b in extract_blocks_py(seg["bytes"], max_blocks=200_000):
                    if int(b["channel"]) != op:
                        continue
                    pay = b.get("payload") or b""
                    # netId somewhere in payload as LE u32
                    if not any(
                        struct.pack("<I", nid) in pay for nid in PROVEN_HERO_NET_IDS
                    ):
                        continue
                    # synthetic param = first proven netId found
                    param = next(
                        nid
                        for nid in PROVEN_HERO_NET_IDS
                        if struct.pack("<I", nid) in pay
                    )
                    got.append(
                        {
                            "time": float(b["time"]),
                            "param": param,
                            "payload": pay,
                            "wireSize": len(pay),
                        }
                    )
                    if len(got) >= 6:
                        break
                if len(got) >= 6:
                    break
            if got:
                fb_samples[op] = got
        fb_matches, fallback_meta = run_capture_pass(
            binary, factories, fb_samples, oracle, label="fallback_netid_in_payload"
        )
        train_matches = list(train_matches) + fb_matches

    eval_res = evaluate_candidates(train_matches, hold_matches)
    winner = eval_res.get("winner")

    wall_ms = (time.perf_counter() - t0) * 1000.0
    pure = False
    browser_safe = False
    product_eligible = False

    report = {
        "ok": bool(eval_res.get("winnerFound")),
        "probeVersion": PROBE_VERSION,
        "hypothesis": "phase-b-e10-win-pe-regcapture",
        "matchCode": MATCH_CODE,
        "wallMs": round(wall_ms, 3),
        "wallTargetMs": 60000,
        "wallPass": wall_ms <= 60000,
        "official": prov,
        "binaryManifest": man,
        "constructorCoverage": coverage,
        "opcodesPrioritized": opcodes,
        "opcodesWithHeroSamples": ordered_ops,
        "sampleCounts": {
            op: {
                "train": len(sample_sets[op]["train"]),
                "holdout": len(sample_sets[op]["holdout"]),
            }
            for op in ordered_ops
        },
        "trainCapture": train_meta,
        "holdoutCapture": hold_meta,
        "fallbackCapture": fallback_meta,
        "evaluation": {
            "winnerFound": eval_res.get("winnerFound"),
            "winner": winner,
            "rankedTop": eval_res.get("rankedTop"),
            "trainPairKeys": eval_res.get("trainPairKeys"),
            "holdoutPairKeys": eval_res.get("holdoutPairKeys"),
            "gates": {
                "minSamples": ACCEPT_MIN_SAMPLES,
                "minHeroes": ACCEPT_MIN_HEROES,
                "maxMedian": ACCEPT_MAX_MEDIAN,
                "maxP95": ACCEPT_MAX_P95,
                "maxMax": ACCEPT_MAX_MAX,
                "searchTol": SEARCH_TOL,
            },
        },
        "pureDecoderDerived": pure,
        "browserSafe": browser_safe,
        "productEligible": product_eligible,
        "identity": {
            "stableNetIdKeys": True,
            "createHeroBindingDecoded": False,
            "productEligible": False,
            "note": "oracle assignment is QA/search only",
        },
        "browserNotes": {
            "ifRegisterCaptureOnly": (
                "browserSafe=false; remote Blob / background-worker fallback only"
            ),
            "uploadLeagueBinary": False,
        },
        "blocker": (
            None
            if winner
            else (
                "no_stable_register_xz_pair_passed_train_holdout_gates; "
                "plaintext_coords_not_observed_in_bounded_deserialize_capture"
            )
        ),
        "method": {
            "style": "maknee_int3_register_capture_analogue",
            "sampleEveryInsns": SAMPLE_EVERY,
            "maxInsns": MAX_INSNS,
            "maxXmm": MAX_XMM,
            "interpretations": ["xmm_f32_lanes", "gpr_low32_f32", "obj_write_f32", "i16_2_plus_center"],
            "noLearnedAffine": True,
            "axisSwapRequiresBothSplitsImprove": True,
        },
    }

    keep = "keep" if winner else "discard"
    reason = (
        f"E10 winner opcode={winner['opcode']} pcX={winner['pcX']} siteX={winner['siteX']}"
        if winner
        else "E10 no stable XMM/GPR/object XZ pair passed train+holdout oracle gates"
    )
    if not dry_run:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        append_speed_record(
            log=SPEED_LOG,
            hypothesis="phase-b-e10-win-pe-regcapture",
            diff_label="e10-register-capture-xz",
            keep=keep,
            reason=reason,
            wall_ms=wall_ms,
            match_code=MATCH_CODE,
            extra={
                "decoderVersion": PROBE_VERSION,
                "winnerFound": bool(winner),
                "winner": winner,
                "browserSafe": browser_safe,
                "productEligible": product_eligible,
                "pureDecoderDerived": pure,
                "trainTagged": train_meta.get("hitCounts"),
                "holdoutTagged": hold_meta.get("hitCounts"),
            },
        )
    return report


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pe", type=Path, default=DEFAULT_PE)
    ap.add_argument("--rofl", type=Path, default=DEFAULT_ROFL)
    ap.add_argument("--oracle", type=Path, default=DEFAULT_ORACLE)
    ap.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    report = run_e10(
        pe_path=args.pe,
        rofl=args.rofl,
        oracle_jsonl=args.oracle,
        report_path=args.report,
        dry_run=args.dry_run,
    )
    w = (report.get("evaluation") or {}).get("winner")
    print(
        json.dumps(
            {
                "ok": report.get("ok"),
                "wallMs": report.get("wallMs"),
                "winnerFound": report.get("evaluation", {}).get("winnerFound"),
                "winner": w,
                "trainCapture": report.get("trainCapture"),
                "holdoutCapture": report.get("holdoutCapture"),
                "browserSafe": report.get("browserSafe"),
                "productEligible": report.get("productEligible"),
                "blocker": report.get("blocker"),
                "report": str(args.report),
            },
            indent=2,
        )
    )
    return 0 if report.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
