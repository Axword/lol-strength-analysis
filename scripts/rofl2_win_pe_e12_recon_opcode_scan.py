#!/usr/bin/env python3
"""E12: Multi-hero live-position scan via E11 reconstructed Deserialize path.

Single variable: with reconstructed framing + decrypt-access capture proven on
opcode 58, scan high-coverage opcodes that touch ≥5 proven hero netIds and
find which releases plaintext X/Z that pass same-match Replay API gates.

Hard constraints: no live API, no plan edit, no commit, no binary vendoring,
no learned affine. Axis-swap only.
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

from unicorn import UC_HOOK_MEM_WRITE  # noqa: E402
from unicorn.x86_const import UC_X86_REG_RIP  # noqa: E402

from rofl2_binary_format import load_binary, research_manifest  # noqa: E402
from rofl2_movement_decode import (  # noqa: E402
    _load_oracle_positions,
    append_speed_record,
)
from rofl2_movement_wire_scan import (  # noqa: E402
    PROVEN_HERO_NET_ID_SET,
    PROVEN_HERO_NET_IDS,
)
from rofl2_probe import extract_segments, parse_rofl2  # noqa: E402
from rofl2_unicorn_packet_drive import extract_blocks_py  # noqa: E402
from rofl2_win_pe_e11_reconstructed_drive import (  # noqa: E402
    MARKER_1,
    MARKER_2,
    OPCODE_DIRECT_INPUT,
    OPCODE_FACE_DIRECTION,
    OPCODE_SET_MOVEMENT_DRIVER,
    encode_type,
)
from rofl2_win_pe_packet_discover import (  # noqa: E402
    WinX64PacketEmu,
    enumerate_rofl,
    official_provenance,
    scan_msvc_packet_types,
)

PROBE_VERSION = "e12-win-pe-recon-opcode-scan-v1"
MATCH_CODE = "3264361042"
DEFAULT_PE = Path("/tmp/League-of-Legends-16.14-win.exe")
DEFAULT_ROFL = Path.home() / "Documents/League of Legends/Replays/BR1-3264361042.rofl"
DEFAULT_ORACLE = Path("artifacts/rofl/3264361042/events.rfc461.jsonl")
DEFAULT_REPORT = Path("docs/rofl-research/movement-win-pe-e12-BR1-3264361042.json")
SPEED_LOG = Path("docs/rofl-research/speed-runs.jsonl")
E21_REPORT = Path("docs/rofl-research/movement-wire-scan-E2.1-BR1-3264361042.json")

EXCLUDE_CONTROLS = frozenset(
    {OPCODE_DIRECT_INPUT, OPCODE_FACE_DIRECTION, OPCODE_SET_MOVEMENT_DRIVER}
)
REPLICATION_TYPE = 107

ACCEPT_MIN_SAMPLES = 80
ACCEPT_MIN_HEROES = 5
ACCEPT_MAX_MEDIAN = 120.0
ACCEPT_MAX_P95 = 350.0
ACCEPT_MAX_MAX = 800.0
ORACLE_TOL_S = 0.5
SR_MIN = -200.0
SR_MAX = 16000.0

# Wall discipline caps.
MAX_CANDIDATES = 22
FRAMING_SAMPLES = 6
SCREEN_SAMPLES = 14
PROMOTE_TOP = 3
PROMOTE_TRAIN = 45
PROMOTE_HOLD = 45
MAX_PAIR_OFFSET = 128


def select_marker(
    binary: Any,
    factory: Mapping[str, Any],
    blocks: Sequence[dict],
    *,
    n: int = FRAMING_SAMPLES,
) -> dict:
    """Prefer 1-byte 0xA6; fall back to 2-byte 0xC6FA; fail-closed if neither beats raw."""
    op = int(factory["opcode"])
    idxs = _era_indices(len(blocks), n)
    best: Optional[dict] = None
    for marker in (MARKER_1, MARKER_2, b""):
        ok = 0
        cons: List[int] = []
        for i in idxs:
            body = marker + blocks[i]["payload"]
            emu = WinX64PacketEmu(binary)
            fr = emu.construct(
                ctor_va=int(factory["ctorVa"]),
                object_size=int(factory["objectSize"]),
                expected_opcode=op,
                expected_vptr=int(factory["vptr"]),
            )
            if not fr.get("ok"):
                continue
            r = emu.deserialize(
                obj=fr["obj"],
                deser_va=int(factory["deserializeVa"]),
                payload=body,
                object_size=int(factory["objectSize"]),
            )
            c = int(r.get("consumed") or 0)
            cons.append(c)
            if r.get("retAl") and c >= max(1, int(0.75 * len(body))):
                ok += 1
        avg = (sum(cons) / len(cons)) if cons else 0.0
        row = {
            "markerHex": marker.hex() or "empty",
            "markerLen": len(marker),
            "ok": ok,
            "n": len(idxs),
            "avgConsumed": round(avg, 3),
        }
        if best is None or row["ok"] > best["ok"] or (
            row["ok"] == best["ok"] and row["avgConsumed"] > best["avgConsumed"]
        ):
            best = row
            best["marker"] = marker
    assert best is not None
    # Score raw separately.
    raw_ok = 0
    raw_cons: List[int] = []
    for i in idxs:
        body = blocks[i]["payload"]
        emu = WinX64PacketEmu(binary)
        fr = emu.construct(
            ctor_va=int(factory["ctorVa"]),
            object_size=int(factory["objectSize"]),
            expected_opcode=op,
            expected_vptr=int(factory["vptr"]),
        )
        if not fr.get("ok"):
            continue
        r = emu.deserialize(
            obj=fr["obj"],
            deser_va=int(factory["deserializeVa"]),
            payload=body,
            object_size=int(factory["objectSize"]),
        )
        c = int(r.get("consumed") or 0)
        raw_cons.append(c)
        if r.get("retAl") and c >= max(1, int(0.75 * len(body))):
            raw_ok += 1
    raw_avg = (sum(raw_cons) / len(raw_cons)) if raw_cons else 0.0
    validated = bool(
        best["marker"]
        and best["ok"] > raw_ok
        and best["ok"] >= max(1, int(0.5 * best["n"]))
    )
    return {
        "opcode": op,
        "encodeTypeHex": encode_type(op).hex(),
        "selectedMarkerHex": best["markerHex"],
        "selectedMarkerLen": best["markerLen"],
        "reconOk": best["ok"],
        "rawOk": raw_ok,
        "avgConsumedRecon": best["avgConsumed"],
        "avgConsumedRaw": round(raw_avg, 3),
        "samples": best["n"],
        "validated": validated,
        "marker": best["marker"],
    }


def _era_indices(n: int, k: int) -> List[int]:
    if n <= 0:
        return []
    k = min(k, n)
    if k == 1:
        return [0]
    return sorted({int(round(i * (n - 1) / (k - 1))) for i in range(k)})


def _f32_map(v: float) -> bool:
    return v == v and SR_MIN <= v <= SR_MAX and abs(v) > 50.0


def load_e21_channels() -> List[int]:
    if E21_REPORT.is_file():
        try:
            rows = json.loads(E21_REPORT.read_text()).get("heroParamChannelTable") or []
            out = [
                int(r["channel"])
                for r in rows
                if r.get("hasAll10HeroParams")
                and int(r.get("heroBlockCount") or 0) >= 500
            ]
            if out:
                return out
        except Exception:  # noqa: BLE001
            pass
    return [351, 259, 1194, 921, 398, 632, 210, 243, 774, 861, 197, 908, 788, 535, 920]


def collect_hero_blocks(rofl: Path) -> Tuple[Dict[int, List[dict]], Dict[int, dict], Counter]:
    """Return blocks_by_op (hero-param only), hero_stats, segment_type_counts."""
    info = parse_rofl2(rofl)
    segs = extract_segments(info["payload"])["segments"]
    seg_types = Counter(int(s.get("type") or -1) for s in segs)
    blocks: Dict[int, List[dict]] = defaultdict(list)
    stats: Dict[int, dict] = defaultdict(lambda: {"n": 0, "heroes": set()})
    repl: List[dict] = []
    for seg in segs:
        st = int(seg.get("type") or 0)
        if st != 1:
            continue
        for b in extract_blocks_py(seg["bytes"], max_blocks=500_000):
            op = int(b["channel"])
            param = int(b.get("param") or 0)
            row = {
                "time": float(b["time"]),
                "param": param,
                "payload": b.get("payload") or b"",
                "wireSize": len(b.get("payload") or b""),
            }
            if op == REPLICATION_TYPE:
                repl.append(row)
            if param in PROVEN_HERO_NET_ID_SET:
                stats[op]["n"] += 1
                stats[op]["heroes"].add(param)
                blocks[op].append(row)
    for op in blocks:
        blocks[op].sort(key=lambda r: r["time"])
    if repl:
        repl.sort(key=lambda r: r["time"])
        blocks[REPLICATION_TYPE] = repl
        stats[REPLICATION_TYPE] = {
            "n": len(repl),
            "heroes": set(),  # blockParam not hero-netId for 107
        }
    for op, st in stats.items():
        st["heroes"] = set(st["heroes"])
        st["heroCount"] = len(st["heroes"])
    return dict(blocks), dict(stats), seg_types


def pick_candidates(stats: Mapping[int, dict], factories: Mapping[int, Any]) -> List[int]:
    e21 = set(load_e21_channels())
    cands: List[int] = []
    for op, st in stats.items():
        if op in EXCLUDE_CONTROLS:
            continue
        if op not in factories:
            continue
        fac = factories[op]
        if not fac.get("deserializeVa") or not fac.get("ctorVa") or not fac.get("objectSize"):
            continue
        heroes = int(st.get("heroCount") or 0)
        n = int(st.get("n") or 0)
        if op == REPLICATION_TYPE or op in e21 or (heroes >= 5 and n >= 500):
            cands.append(op)
        elif heroes >= 5 and n >= 1000:
            cands.append(op)
    # Priority: E2.1 first, then by hero block count.
    e21_list = [o for o in load_e21_channels() if o in cands]
    rest = sorted(
        (o for o in cands if o not in e21_list),
        key=lambda o: (-int(stats[o].get("n") or 0), o),
    )
    ordered = e21_list + rest
    if REPLICATION_TYPE in cands and REPLICATION_TYPE not in ordered:
        ordered.append(REPLICATION_TYPE)
    elif REPLICATION_TYPE in ordered:
        ordered = [o for o in ordered if o != REPLICATION_TYPE] + [REPLICATION_TYPE]
    return ordered[:MAX_CANDIDATES]


def diversify(blocks: Sequence[dict], n: int, *, require_heroes: bool) -> List[dict]:
    if not blocks:
        return []
    if require_heroes:
        by: Dict[int, List[dict]] = defaultdict(list)
        for b in blocks:
            by[int(b["param"])].append(b)
        out: List[dict] = []
        heroes = list(by.keys())
        if not heroes:
            return []
        per = max(1, (n + len(heroes) - 1) // len(heroes))
        for h in heroes:
            rows = by[h]
            for i in range(min(per, len(rows))):
                out.append(rows[int(i * (len(rows) - 1) / max(1, per - 1))])
        seen = set()
        uniq = []
        for b in sorted(out, key=lambda r: r["time"]):
            key = (round(b["time"], 3), b["param"])
            if key in seen:
                continue
            seen.add(key)
            uniq.append(b)
        return uniq[:n]
    idxs = _era_indices(len(blocks), n)
    return [blocks[i] for i in idxs]


def capture_writes(
    binary: Any,
    factory: Mapping[str, Any],
    blocks: Sequence[dict],
    marker: bytes,
) -> List[dict]:
    op = int(factory["opcode"])
    osz = max(int(factory["objectSize"]), 64)
    out: List[dict] = []
    for b in blocks:
        emu = WinX64PacketEmu(binary)
        fr = emu.construct(
            ctor_va=int(factory["ctorVa"]),
            object_size=osz,
            expected_opcode=op,
            expected_vptr=int(factory["vptr"]),
        )
        if not fr.get("ok"):
            continue
        obj = int(fr["obj"])
        writes: List[dict] = []

        def on_write(uc: Any, access: int, address: int, size: int, value: int, user: Any) -> None:
            if size == 4:
                f32 = struct.unpack("<f", struct.pack("<I", value & 0xFFFFFFFF))[0]
                if _f32_map(f32):
                    writes.append(
                        {
                            "off": int(address - obj),
                            "f": float(f32),
                            "pc": int(uc.reg_read(UC_X86_REG_RIP)),
                        }
                    )
            elif size == 8:
                raw = struct.pack("<Q", value & 0xFFFFFFFFFFFFFFFF)
                for i, f32 in enumerate(struct.unpack("<ff", raw)):
                    if _f32_map(f32):
                        writes.append(
                            {
                                "off": int(address + 4 * i - obj),
                                "f": float(f32),
                                "pc": int(uc.reg_read(UC_X86_REG_RIP)),
                            }
                        )

        h = emu.mu.hook_add(UC_HOOK_MEM_WRITE, on_write)
        body = marker + b["payload"]
        r = emu.deserialize(
            obj=obj,
            deser_va=int(factory["deserializeVa"]),
            payload=body,
            object_size=osz,
        )
        try:
            emu.mu.hook_del(h)
        except Exception:  # noqa: BLE001
            pass
        # Final object snapshot for offsets still holding map floats.
        try:
            mem = bytes(emu.mu.mem_read(obj, osz))
            for off in range(0, len(mem) - 3, 4):
                f32 = struct.unpack_from("<f", mem, off)[0]
                if _f32_map(f32) and not any(w["off"] == off for w in writes):
                    writes.append({"off": off, "f": float(f32), "pc": 0})
        except Exception:  # noqa: BLE001
            pass
        out.append(
            {
                "t": float(b["time"]),
                "param": int(b["param"]),
                "retAl": int(r.get("retAl") or 0),
                "consumed": int(r.get("consumed") or 0),
                "bodyLen": len(body),
                "writes": writes,
            }
        )
    return out


def nearest_oracle(
    oracle: Sequence[dict], t: float, *, tol_s: float = ORACLE_TOL_S
) -> Optional[Dict[int, Tuple[float, float]]]:
    best = None
    best_dt = 1e9
    for row in oracle:
        dt = abs(float(row["time"]) - t)
        if dt < best_dt:
            best_dt = dt
            best = row
    if best is None or best_dt > tol_s:
        return None
    return {
        int(p["participantID"]): (float(p["x"]), float(p["z"]))
        for p in best["participants"]
    }


def extract_offset_pairs(writes: Sequence[dict]) -> List[Tuple[int, int, float, float]]:
    by_off: Dict[int, float] = {}
    for w in writes:
        off = int(w["off"])
        if 0 <= off <= MAX_PAIR_OFFSET:
            by_off[off] = float(w["f"])
    offs = sorted(by_off)
    pairs = []
    for i, a in enumerate(offs):
        for b in offs[i + 1 : i + 4]:
            if b - a > 16:
                break
            pairs.append((a, b, by_off[a], by_off[b]))
    return pairs


def score_pair_key(
    captures: Sequence[dict],
    oracle: Sequence[dict],
    off_x: int,
    off_z: int,
    *,
    swap: bool = False,
) -> dict:
    errs: List[float] = []
    heroes: set = set()
    for cap in captures:
        pos = nearest_oracle(oracle, float(cap["t"]))
        if pos is None:
            continue
        by_off = {int(w["off"]): float(w["f"]) for w in cap["writes"]}
        if off_x not in by_off or off_z not in by_off:
            continue
        x, z = by_off[off_x], by_off[off_z]
        if swap:
            x, z = z, x
        heroes.add(int(cap["param"]))
        errs.append(min(math.hypot(x - ox, z - oz) for ox, oz in pos.values()))
    if not errs:
        return {"n": 0, "heroes": 0, "ok": False}
    srt = sorted(errs)
    med = statistics.median(srt)
    p95 = srt[min(len(srt) - 1, int(round(0.95 * (len(srt) - 1))))]
    mx = srt[-1]
    return {
        "n": len(srt),
        "heroes": len(heroes),
        "median": med,
        "p95": p95,
        "max": mx,
        "ok": (
            len(srt) >= ACCEPT_MIN_SAMPLES
            and len(heroes) >= ACCEPT_MIN_HEROES
            and med <= ACCEPT_MAX_MEDIAN
            and p95 <= ACCEPT_MAX_P95
            and mx <= ACCEPT_MAX_MAX
        ),
    }


def rank_pairs(captures: Sequence[dict], oracle: Sequence[dict]) -> List[dict]:
    bucket: Dict[Tuple[int, int, bool], List[float]] = defaultdict(list)
    hero_bucket: Dict[Tuple[int, int, bool], set] = defaultdict(set)
    for cap in captures:
        pos = nearest_oracle(oracle, float(cap["t"]))
        if pos is None:
            continue
        for ox, oz, x, z in extract_offset_pairs(cap["writes"]):
            d = min(math.hypot(x - a, z - b) for a, b in pos.values())
            ds = min(math.hypot(z - a, x - b) for a, b in pos.values())
            bucket[(ox, oz, False)].append(d)
            bucket[(ox, oz, True)].append(ds)
            hero_bucket[(ox, oz, False)].add(int(cap["param"]))
            hero_bucket[(ox, oz, True)].add(int(cap["param"]))
    ranked = []
    for key, errs in bucket.items():
        if len(errs) < 3:
            continue
        srt = sorted(errs)
        ox, oz, swap = key
        ranked.append(
            {
                "offX": ox,
                "offZ": oz,
                "swap": swap,
                "n": len(errs),
                "heroes": len(hero_bucket[key]),
                "median": statistics.median(srt),
                "p95": srt[min(len(srt) - 1, int(round(0.95 * (len(srt) - 1))))],
                "max": srt[-1],
            }
        )
    ranked.sort(key=lambda r: (r["median"], r["p95"], -r["n"]))
    return ranked


def classify_blocker(
    *,
    framing_ok: int,
    framing_fail: int,
    with_writes: int,
    evaluated: Sequence[dict],
    seg_types: Mapping[int, int],
) -> dict:
    qa_best = None
    for row in evaluated:
        hold = (row.get("holdout") or {})
        if hold.get("median") is None:
            continue
        if qa_best is None or hold["median"] < qa_best["holdout"]["median"]:
            qa_best = row
    if framing_ok == 0:
        kind = "no_multi_hero_framing"
        detail = "no candidate opcode validated reconstructed framing vs raw"
    elif with_writes == 0:
        kind = "helpers_incomplete_beyond_58"
        detail = (
            "multi-hero opcodes deserialize under recon but released no map-range "
            "f32 writes (encrypt-at-rest / non-float layout beyond DirectInput END_READ)"
        )
    elif qa_best is None or not (qa_best.get("holdout") or {}).get("ok"):
        # Type-1 chunk scan produced map floats that fail live-position gates.
        kind = "position_not_in_chunk_packets"
        best_med = (qa_best or {}).get("holdout", {}).get("median")
        detail = (
            f"type-1 chunk opcodes with multi-hero coverage frame OK and some emit "
            f"map-range floats, but none pass Replay API gates "
            f"(best holdout med={None if best_med is None else round(best_med, 1)}; "
            f"segTypes={dict(seg_types)}; next: type-2 keyframe hypothesis)"
        )
    else:
        kind = "none"
        detail = "winner found"
    return {
        "kind": kind,
        "detail": detail,
        "framingValidatedCount": framing_ok,
        "framingFailedCount": framing_fail,
        "opcodesWithMapWrites": with_writes,
        "segmentTypeCounts": {str(k): int(v) for k, v in seg_types.items()},
        "bestNearMiss": (
            {
                "opcode": qa_best.get("opcode"),
                "offX": qa_best.get("offX"),
                "offZ": qa_best.get("offZ"),
                "swap": qa_best.get("swap"),
                "train": qa_best.get("train"),
                "holdout": qa_best.get("holdout"),
            }
            if qa_best
            else None
        ),
    }


def run_e12(
    *,
    pe_path: Path,
    rofl: Path,
    oracle_jsonl: Path,
    report_path: Path,
    dry_run: bool = False,
) -> dict:
    t0 = time.perf_counter()
    binary = load_binary(pe_path)
    prov = official_provenance(size=pe_path.stat().st_size, sha256=binary.sha256)
    man = research_manifest(
        binary, patch="16.14", extra={"probeVersion": PROBE_VERSION, "official": prov}
    )
    counts, _ = enumerate_rofl(rofl)
    rows, coverage = scan_msvc_packet_types(binary, counts)
    factories = {int(r["opcode"]): r for r in rows}
    for op, fac in factories.items():
        fac["opcode"] = op

    blocks, stats, seg_types = collect_hero_blocks(rofl)
    candidates = pick_candidates(stats, factories)
    oracle = _load_oracle_positions(oracle_jsonl)

    framing_rows: Dict[str, dict] = {}
    screen_rows: List[dict] = []
    framing_ok = 0
    framing_fail = 0
    with_writes = 0

    for op in candidates:
        fac = factories[op]
        bl = blocks.get(op) or []
        if len(bl) < 6:
            continue
        require_heroes = op != REPLICATION_TYPE
        frame_samples = diversify(bl, FRAMING_SAMPLES, require_heroes=require_heroes)
        fr = select_marker(binary, fac, frame_samples, n=FRAMING_SAMPLES)
        fr_pub = {k: v for k, v in fr.items() if k != "marker"}
        framing_rows[str(op)] = fr_pub
        if not fr["validated"]:
            framing_fail += 1
            continue
        framing_ok += 1
        marker = fr["marker"]
        screen = diversify(bl, SCREEN_SAMPLES, require_heroes=require_heroes)
        caps = capture_writes(binary, fac, screen, marker)
        n_writes = sum(len(c["writes"]) for c in caps)
        if n_writes > 0:
            with_writes += 1
        ranked = rank_pairs(caps, oracle) if n_writes else []
        screen_rows.append(
            {
                "opcode": op,
                "heroCount": int(stats.get(op, {}).get("heroCount") or 0),
                "heroBlocks": int(stats.get(op, {}).get("n") or 0),
                "markerHex": fr["selectedMarkerHex"],
                "screenSamples": len(caps),
                "deserOk": sum(
                    1
                    for c in caps
                    if c["retAl"] and c["consumed"] >= int(0.7 * c["bodyLen"])
                ),
                "mapWriteCount": n_writes,
                "topPairs": ranked[:5],
            }
        )

    # Promote top opcodes by best screen median among pairs with ≥5 samples.
    promotable = []
    for row in screen_rows:
        for p in row.get("topPairs") or []:
            if p["n"] >= 5:
                promotable.append({**row, "pair": p})
                break
    promotable.sort(key=lambda r: (r["pair"]["median"], r["pair"]["p95"]))
    promoted = promotable[:PROMOTE_TOP]

    evaluations: List[dict] = []
    winner = None
    for row in promoted:
        op = int(row["opcode"])
        fac = factories[op]
        pair = row["pair"]
        marker = bytes.fromhex(row["markerHex"]) if row["markerHex"] != "empty" else b""
        bl = blocks.get(op) or []
        require_heroes = op != REPLICATION_TYPE
        picked = diversify(
            bl, PROMOTE_TRAIN + PROMOTE_HOLD, require_heroes=require_heroes
        )
        picked = sorted(picked, key=lambda r: r["time"])
        mid = len(picked) // 2
        train_b, hold_b = picked[:mid], picked[mid:]
        train_caps = capture_writes(binary, fac, train_b, marker)
        hold_caps = capture_writes(binary, fac, hold_b, marker)
        # Prefer direct; accept swap only if both splits improve.
        tr_d = score_pair_key(
            train_caps, oracle, pair["offX"], pair["offZ"], swap=False
        )
        ho_d = score_pair_key(
            hold_caps, oracle, pair["offX"], pair["offZ"], swap=False
        )
        tr_s = score_pair_key(
            train_caps, oracle, pair["offX"], pair["offZ"], swap=True
        )
        ho_s = score_pair_key(
            hold_caps, oracle, pair["offX"], pair["offZ"], swap=True
        )
        use_swap = bool(
            tr_s.get("n", 0) >= 10
            and ho_s.get("n", 0) >= 10
            and (tr_s.get("median") or 1e18) < (tr_d.get("median") or 1e18)
            and (ho_s.get("median") or 1e18) < (ho_d.get("median") or 1e18)
        )
        train = tr_s if use_swap else tr_d
        hold = ho_s if use_swap else ho_d
        ev = {
            "opcode": op,
            "offX": pair["offX"],
            "offZ": pair["offZ"],
            "swap": use_swap,
            "markerHex": row["markerHex"],
            "train": train,
            "holdout": hold,
            "winner": bool(train.get("ok") and hold.get("ok")),
        }
        evaluations.append(ev)
        if ev["winner"] and winner is None:
            winner = {
                "opcode": op,
                "offX": pair["offX"],
                "offZ": pair["offZ"],
                "swap": use_swap,
                "layout": f"obj+{pair['offX']}/+{pair['offZ']} f32 pair via MEM_WRITE",
                "train": train,
                "holdout": hold,
            }

    wall_ms = (time.perf_counter() - t0) * 1000.0
    blocker = classify_blocker(
        framing_ok=framing_ok,
        framing_fail=framing_fail,
        with_writes=with_writes,
        evaluated=evaluations,
        seg_types=seg_types,
    )

    report = {
        "ok": bool(winner),
        "probeVersion": PROBE_VERSION,
        "hypothesis": "phase-b-e12-recon-opcode-scan",
        "matchCode": MATCH_CODE,
        "wallMs": round(wall_ms, 3),
        "wallTargetMs": 60_000,
        "wallPass": wall_ms <= 60_000,
        "official": prov,
        "binaryManifest": man,
        "constructorCoverage": coverage,
        "excludedControls": sorted(EXCLUDE_CONTROLS),
        "candidates": candidates,
        "framingValidation": framing_rows,
        "screen": screen_rows,
        "promoted": evaluations,
        "evaluation": {
            "winnerFound": bool(winner),
            "winner": winner,
            "gates": {
                "minSamples": ACCEPT_MIN_SAMPLES,
                "minHeroes": ACCEPT_MIN_HEROES,
                "maxMedian": ACCEPT_MAX_MEDIAN,
                "maxP95": ACCEPT_MAX_P95,
                "maxMax": ACCEPT_MAX_MAX,
                "oracleTolS": ORACLE_TOL_S,
            },
        },
        "blocker": blocker,
        "pureDecoderDerived": False,
        "browserSafe": False,
        "productEligible": False,
        "identity": {
            "createHeroBindingDecoded": False,
            "productEligible": False,
            "note": "oracle assignment is QA/search only",
        },
        "method": {
            "framing": "encode_type||marker||wire; Deserialize body=marker||wire",
            "capture": "UC_HOOK_MEM_WRITE map-range f32 + post-object scan",
            "noLearnedAffine": True,
            "caps": {
                "maxCandidates": MAX_CANDIDATES,
                "framingSamples": FRAMING_SAMPLES,
                "screenSamples": SCREEN_SAMPLES,
                "promoteTop": PROMOTE_TOP,
                "promoteTrain": PROMOTE_TRAIN,
                "promoteHold": PROMOTE_HOLD,
            },
        },
    }

    keep = "keep" if winner else "discard"
    reason = (
        f"E12 winner opcode={winner['opcode']} off={winner['offX']}/{winner['offZ']}"
        if winner
        else f"E12 blocker={blocker['kind']}: {blocker['detail'][:180]}"
    )
    if not dry_run:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        append_speed_record(
            log=SPEED_LOG,
            hypothesis="phase-b-e12-recon-opcode-scan",
            diff_label="e12-multi-hero-recon-scan",
            keep=keep,
            reason=reason,
            wall_ms=wall_ms,
            match_code=MATCH_CODE,
            extra={
                "decoderVersion": PROBE_VERSION,
                "winnerFound": bool(winner),
                "winner": winner,
                "blocker": blocker,
                "browserSafe": False,
                "productEligible": False,
                "pureDecoderDerived": False,
                "framingValidatedCount": framing_ok,
                "opcodesWithMapWrites": with_writes,
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
    report = run_e12(
        pe_path=args.pe,
        rofl=args.rofl,
        oracle_jsonl=args.oracle,
        report_path=args.report,
        dry_run=args.dry_run,
    )
    print(
        json.dumps(
            {
                "ok": report.get("ok"),
                "wallMs": report.get("wallMs"),
                "winnerFound": (report.get("evaluation") or {}).get("winnerFound"),
                "winner": (report.get("evaluation") or {}).get("winner"),
                "blocker": report.get("blocker"),
                "framingValidatedCount": (report.get("blocker") or {}).get(
                    "framingValidatedCount"
                ),
                "opcodesWithMapWrites": (report.get("blocker") or {}).get(
                    "opcodesWithMapWrites"
                ),
                "browserSafe": report.get("browserSafe"),
                "productEligible": report.get("productEligible"),
                "report": str(args.report),
            },
            indent=2,
        )
    )
    return 0 if report.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
