#!/usr/bin/env python3
"""Phase B E2/E2.1: wire packet-id remap scanner for offline 0x025B-schema movement.

Single variable: observed block ``channel`` may not equal public ``0x025B``.
Applies the clean-room 025B schema decoder parametrically across **every**
observed channel. Schema-shaped decode success is never proof of movement;
oracle alignment + stability gates decide ranking.

E2.1 correction: public 0x025B research and same-match replication acceptance
filter by block ``param`` equal to champion netIds
``0x400000AE .. 0x400000B7`` (1073741998..1073742007). QA groups tracks by
``blockParam``, not decoded inner f4 netId (diagnostics only).

Research-only. Never product-binds identity.
"""
from __future__ import annotations

import math
import random
import statistics
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from rofl2_probe import extract_segments, parse_rofl2
from rofl2_unicorn_packet_drive import extract_blocks_py
from rofl2_movement_decode import (
    DEFAULT_LEAGUE_BINARY,
    MOVEMENT_PACKET_ID,
    PROVENANCE,
    _load_oracle_positions,
    decode_025b_payload,
    load_lut,
)

# Explicit acceptance thresholds (movement candidate).
ACCEPT_MIN_STABLE_ENTITIES = 5
ACCEPT_MIN_COMPARED_SAMPLES = 80
ACCEPT_MAX_MEDIAN_ERROR = 120.0
ACCEPT_MAX_P95_ERROR = 350.0
ACCEPT_MAX_MAX_ERROR = 800.0
ACCEPT_MIN_SUCCESS_RATIO = 0.12
ACCEPT_MIN_FULL_CONSUME_RATIO = 0.10
ACCEPT_MIN_COORD_PLAUSIBLE_RATIO = 0.55
ACCEPT_MIN_COORD_SPAN = 400.0  # max(x)-min(x) or z
ACCEPT_MIN_UNIQUE_NET_IDS = 5
ACCEPT_MIN_CHANNEL_COUNT = 8_000  # tens of thousands/match expected; floor for midgame
ACCEPT_MIN_TIME_COVERAGE_S = 20.0
ACCEPT_MIN_HERO_PARAMS = 10
ACCEPT_MIN_HERO_BLOCKS = 5_000
ACCEPT_MIN_SAMPLES_PER_HERO_PARAM = 8
DEFAULT_ORACLE_TOLERANCE_S = 0.5  # <=500 ms
DEFAULT_SAMPLE_CAP = 400
DEFAULT_DEEP_CAP = 25_000
MAP_COORD_MIN = 0
MAP_COORD_MAX = 15000

# Proven champion netIds on BR1-3264361042 (and public 0x025B param filter).
PROVEN_HERO_NET_IDS: Tuple[int, ...] = tuple(range(0x400000AE, 0x400000B8))
PROVEN_HERO_NET_ID_SET = frozenset(PROVEN_HERO_NET_IDS)


@dataclass
class ChannelBucket:
    channel: int
    count: int = 0
    payload_size_sum: int = 0
    payload_size_min: Optional[int] = None
    payload_size_max: Optional[int] = None
    # Reservoir of sizes for percentiles (bounded).
    payload_size_reservoir: List[int] = field(default_factory=list)
    params: Counter = field(default_factory=Counter)
    hero_params: Counter = field(default_factory=Counter)
    hero_block_count: int = 0
    time_min: Optional[float] = None
    time_max: Optional[float] = None
    samples: List[dict] = field(default_factory=list)  # bounded raw blocks
    hero_samples: List[dict] = field(default_factory=list)  # prefer hero-param samples


def _percentile(sorted_vals: Sequence[float], p: float) -> Optional[float]:
    if not sorted_vals:
        return None
    if len(sorted_vals) == 1:
        return float(sorted_vals[0])
    k = (len(sorted_vals) - 1) * (p / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return float(sorted_vals[int(k)])
    return float(sorted_vals[f] * (c - k) + sorted_vals[c] * (k - f))


def hungarian_assignment(
    cost: List[List[float]],
) -> Tuple[List[Tuple[int, int]], float]:
    """Minimize cost assignment. Prefers scipy; falls back to exhaustive for n<=10."""
    n_rows = len(cost)
    n_cols = len(cost[0]) if cost else 0
    if n_rows == 0 or n_cols == 0:
        return [], 0.0

    try:
        from scipy.optimize import linear_sum_assignment  # type: ignore

        import numpy as np

        mat = np.asarray(cost, dtype=float)
        ri, ci = linear_sum_assignment(mat)
        pairs = [(int(r), int(c)) for r, c in zip(ri, ci)]
        total = float(sum(mat[r, c] for r, c in pairs))
        return pairs, total
    except Exception:
        pass

    # Exhaustive for small bipartite graphs (typical 10×10).
    if n_rows > 10 or n_cols > 10:
        # Greedy fallback only when exhaustive is infeasible AND scipy missing.
        used_c = set()
        pairs = []
        total = 0.0
        order = sorted(
            ((cost[r][c], r, c) for r in range(n_rows) for c in range(n_cols)),
        )
        used_r = set()
        for cst, r, c in order:
            if r in used_r or c in used_c:
                continue
            used_r.add(r)
            used_c.add(c)
            pairs.append((r, c))
            total += cst
        return pairs, total

    # Pad to square
    n = max(n_rows, n_cols)
    big = 1e12
    pad = [[big] * n for _ in range(n)]
    for r in range(n_rows):
        for c in range(n_cols):
            pad[r][c] = float(cost[r][c])

    best_pairs: List[Tuple[int, int]] = []
    best_total = float("inf")

    def rec(row: int, used: List[bool], cur: List[Tuple[int, int]], acc: float) -> None:
        nonlocal best_pairs, best_total
        if acc >= best_total:
            return
        if row == n:
            real = [(r, c) for r, c in cur if r < n_rows and c < n_cols]
            best_pairs = real
            best_total = acc
            return
        for c in range(n):
            if used[c]:
                continue
            used[c] = True
            cur.append((row, c))
            rec(row + 1, used, cur, acc + pad[row][c])
            cur.pop()
            used[c] = False

    rec(0, [False] * n, [], 0.0)
    return best_pairs, float(best_total if best_pairs else 0.0)


def optimal_oracle_assignment(
    samples: Sequence[Mapping[str, Any]],
    oracle_frames: Sequence[Mapping[str, Any]],
    *,
    tolerance_s: float = DEFAULT_ORACLE_TOLERANCE_S,
    max_pair_dist: float = 2000.0,
) -> dict:
    """Research-only globally unique netId↔participant assignment (Hungarian).

    Aligns each decoded sample to the nearest 1 Hz oracle frame within
    ``tolerance_s`` (default 500 ms). Does **not** product-bind identity.
    """
    if not oracle_frames or not samples:
        return {
            "ok": False,
            "productEligible": False,
            "label": "research_only_not_product",
            "error": "empty samples or oracle",
            "assignmentCount": 0,
            "comparedSamples": 0,
        }

    oracle_times = [float(fr["time"]) for fr in oracle_frames]
    by_nid: Dict[int, List[Tuple[float, float, float]]] = defaultdict(list)
    for s in samples:
        by_nid[int(s["netId"])].append((float(s["time"]), float(s["x"]), float(s["z"])))

    participant_ids = sorted(
        {
            int(p["participantID"])
            for fr in oracle_frames
            for p in fr["participants"]
        }
    )
    net_ids = sorted(by_nid.keys())

    # dists[nid][pid] = list of spatial errors for time-aligned pairs
    dists: Dict[int, Dict[int, List[float]]] = defaultdict(lambda: defaultdict(list))
    aligned_pairs = 0

    for nid, pts in by_nid.items():
        for t, x, z in pts:
            # binary search nearest oracle time
            lo, hi = 0, len(oracle_times) - 1
            best_i = 0
            while lo <= hi:
                mid = (lo + hi) // 2
                if oracle_times[mid] < t:
                    lo = mid + 1
                else:
                    hi = mid - 1
            candidates_i = {max(0, lo - 1), min(len(oracle_times) - 1, lo), hi}
            best_dt = None
            best_fr = None
            for i in candidates_i:
                if i < 0 or i >= len(oracle_frames):
                    continue
                dt = abs(oracle_times[i] - t)
                if dt <= tolerance_s and (best_dt is None or dt < best_dt):
                    best_dt = dt
                    best_fr = oracle_frames[i]
            # also check neighbors of lo
            for i in (lo - 2, lo + 1):
                if 0 <= i < len(oracle_frames):
                    dt = abs(oracle_times[i] - t)
                    if dt <= tolerance_s and (best_dt is None or dt < best_dt):
                        best_dt = dt
                        best_fr = oracle_frames[i]
            if best_fr is None:
                continue
            aligned_pairs += 1
            for p in best_fr["participants"]:
                pid = int(p["participantID"])
                dist = math.hypot(x - float(p["x"]), z - float(p["z"]))
                dists[nid][pid].append(dist)

    if not net_ids or not participant_ids:
        return {
            "ok": False,
            "productEligible": False,
            "label": "research_only_not_product",
            "assignmentCount": 0,
            "comparedSamples": 0,
            "alignedPairs": aligned_pairs,
        }

    # Cost = median distance; missing pairs get large cost
    BIG = 1e9
    cost = []
    med_matrix = []
    for nid in net_ids:
        row = []
        med_row = []
        for pid in participant_ids:
            vals = dists[nid].get(pid) or []
            if not vals:
                row.append(BIG)
                med_row.append(None)
            else:
                m = float(statistics.median(vals))
                row.append(m if m <= max_pair_dist else BIG)
                med_row.append(m)
        cost.append(row)
        med_matrix.append(med_row)

    pairs, _total = hungarian_assignment(cost)
    assignment = []
    used_errors: List[float] = []
    compared = 0
    for ri, ci in pairs:
        if ri >= len(net_ids) or ci >= len(participant_ids):
            continue
        nid = net_ids[ri]
        pid = participant_ids[ci]
        vals = dists[nid].get(pid) or []
        if not vals or cost[ri][ci] >= BIG / 2:
            continue
        med = float(statistics.median(vals))
        assignment.append(
            {
                "netId": nid,
                "participantID": pid,
                "matches": len(vals),
                "medianDist": round(med, 3),
            }
        )
        used_errors.extend(vals)
        compared += len(vals)

    used_errors.sort()
    return {
        "ok": len(assignment) >= 1,
        "productEligible": False,
        "label": "research_only_not_product",
        "method": "hungarian",
        "toleranceS": tolerance_s,
        "oracleFrames": len(oracle_frames),
        "sampleCount": len(samples),
        "uniqueNetIds": len(net_ids),
        "assignmentCount": len(assignment),
        "assignment": assignment,
        "comparedSamples": compared,
        "alignedPairs": aligned_pairs,
        "medianError": round(float(statistics.median(used_errors)), 3) if used_errors else None,
        "p95Error": round(_percentile(used_errors, 95) or 0.0, 3) if used_errors else None,
        "maxError": round(max(used_errors), 3) if used_errors else None,
        "note": (
            "netId→participantID derived only for QA alignment; "
            "do not use as product identity binding"
        ),
    }


def _nearest_oracle_frame(
    oracle_frames: Sequence[Mapping[str, Any]],
    oracle_times: Sequence[float],
    t: float,
    tolerance_s: float,
) -> Optional[Mapping[str, Any]]:
    if not oracle_frames:
        return None
    lo, hi = 0, len(oracle_times) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        if oracle_times[mid] < t:
            lo = mid + 1
        else:
            hi = mid - 1
    best_dt = None
    best_fr = None
    for i in (lo - 2, lo - 1, lo, lo + 1, hi):
        if i is None or i < 0 or i >= len(oracle_frames):
            continue
        dt = abs(oracle_times[i] - t)
        if dt <= tolerance_s and (best_dt is None or dt < best_dt):
            best_dt = dt
            best_fr = oracle_frames[i]
    return best_fr


def evaluate_raw_point_errors(
    samples_by_param: Mapping[int, Sequence[Mapping[str, Any]]],
    assignment: Mapping[int, int],
    oracle_frames: Sequence[Mapping[str, Any]],
    *,
    tolerance_s: float,
) -> Tuple[List[float], int]:
    """Compare each decoded point to assigned participant at aligned oracle time."""
    oracle_times = [float(fr["time"]) for fr in oracle_frames]
    errors: List[float] = []
    compared = 0
    for param, pts in samples_by_param.items():
        pid = assignment.get(int(param))
        if pid is None:
            continue
        for s in pts:
            fr = _nearest_oracle_frame(oracle_frames, oracle_times, float(s["time"]), tolerance_s)
            if fr is None:
                continue
            pos = next(
                (
                    p
                    for p in fr["participants"]
                    if int(p["participantID"]) == int(pid)
                ),
                None,
            )
            if pos is None:
                continue
            # One sample may carry multiple points; evaluate each honestly.
            points = s.get("points") or [{"x": s["x"], "z": s["z"]}]
            best = min(
                math.hypot(float(pt["x"]) - float(pos["x"]), float(pt["z"]) - float(pos["z"]))
                for pt in points
            )
            errors.append(best)
            compared += 1
    return errors, compared


def evaluate_continuity_track_errors(
    samples_by_param: Mapping[int, Sequence[Mapping[str, Any]]],
    assignment: Mapping[int, int],
    oracle_frames: Sequence[Mapping[str, Any]],
    *,
    tolerance_s: float,
) -> Tuple[List[float], int]:
    """Continuity-constrained NN track seeded only by oracle for research QA.

    For each hero param, seed from the first time-aligned oracle participant
    position. Subsequent multi-point buckets pick the candidate nearest the
    previous track point. Oracle track is never product output.
    """
    oracle_times = [float(fr["time"]) for fr in oracle_frames]
    errors: List[float] = []
    compared = 0
    for param, pts in samples_by_param.items():
        pid = assignment.get(int(param))
        if pid is None:
            continue
        ordered = sorted(pts, key=lambda s: float(s["time"]))
        track: Optional[Tuple[float, float]] = None
        for s in ordered:
            fr = _nearest_oracle_frame(oracle_frames, oracle_times, float(s["time"]), tolerance_s)
            if fr is None:
                continue
            pos = next(
                (
                    p
                    for p in fr["participants"]
                    if int(p["participantID"]) == int(pid)
                ),
                None,
            )
            if pos is None:
                continue
            ox, oz = float(pos["x"]), float(pos["z"])
            points = s.get("points") or [{"x": s["x"], "z": s["z"]}]
            if track is None:
                # Seed only from oracle (research QA).
                track = (ox, oz)
            # Pick continuity-constrained nearest neighbor among candidates.
            chosen = min(
                points,
                key=lambda pt: math.hypot(
                    float(pt["x"]) - track[0], float(pt["z"]) - track[1]
                ),
            )
            cx, cz = float(chosen["x"]), float(chosen["z"])
            track = (cx, cz)
            errors.append(math.hypot(cx - ox, cz - oz))
            compared += 1
    return errors, compared


def optimal_oracle_assignment_by_block_param(
    samples: Sequence[Mapping[str, Any]],
    oracle_frames: Sequence[Mapping[str, Any]],
    *,
    tolerance_s: float = DEFAULT_ORACLE_TOLERANCE_S,
    max_pair_dist: float = 2000.0,
    hero_params: Sequence[int] = PROVEN_HERO_NET_IDS,
    min_samples_per_param: int = ACCEPT_MIN_SAMPLES_PER_HERO_PARAM,
) -> dict:
    """Research-only 10 blockParam ↔ 10 participant Hungarian assignment.

    Groups tracks by ``blockParam`` (wire identity). Decoded inner netId is
    diagnostic only and must not drive the assignment.
    """
    if not oracle_frames or not samples:
        return {
            "ok": False,
            "productEligible": False,
            "label": "research_only_not_product",
            "grouping": "blockParam",
            "error": "empty samples or oracle",
            "assignmentCount": 0,
            "comparedSamples": 0,
            "methodPassed": None,
        }

    hero_set = frozenset(int(x) for x in hero_params)
    by_param: Dict[int, List[dict]] = defaultdict(list)
    for s in samples:
        bp = int(s.get("blockParam") if s.get("blockParam") is not None else s.get("param") or 0)
        if hero_set and bp not in hero_set:
            continue
        by_param[bp].append(dict(s))

    # Require stable repeated samples per hero param.
    stable_params = sorted(
        p for p, pts in by_param.items() if len(pts) >= min_samples_per_param
    )
    participant_ids = sorted(
        {
            int(p["participantID"])
            for fr in oracle_frames
            for p in fr["participants"]
        }
    )
    oracle_times = [float(fr["time"]) for fr in oracle_frames]

    dists: Dict[int, Dict[int, List[float]]] = defaultdict(lambda: defaultdict(list))
    for param in stable_params:
        for s in by_param[param]:
            fr = _nearest_oracle_frame(
                oracle_frames, oracle_times, float(s["time"]), tolerance_s
            )
            if fr is None:
                continue
            points = s.get("points") or [{"x": s["x"], "z": s["z"]}]
            for p in fr["participants"]:
                pid = int(p["participantID"])
                best = min(
                    math.hypot(float(pt["x"]) - float(p["x"]), float(pt["z"]) - float(p["z"]))
                    for pt in points
                )
                dists[param][pid].append(best)

    if not stable_params or not participant_ids:
        return {
            "ok": False,
            "productEligible": False,
            "label": "research_only_not_product",
            "grouping": "blockParam",
            "assignmentCount": 0,
            "comparedSamples": 0,
            "stableHeroParams": len(stable_params),
            "methodPassed": None,
        }

    BIG = 1e9
    cost = []
    for param in stable_params:
        row = []
        for pid in participant_ids:
            vals = dists[param].get(pid) or []
            if not vals:
                row.append(BIG)
            else:
                m = float(statistics.median(vals))
                row.append(m if m <= max_pair_dist else BIG)
        cost.append(row)

    pairs, _ = hungarian_assignment(cost)
    assignment_list = []
    assign_map: Dict[int, int] = {}
    for ri, ci in pairs:
        if ri >= len(stable_params) or ci >= len(participant_ids):
            continue
        if cost[ri][ci] >= BIG / 2:
            continue
        param = stable_params[ri]
        pid = participant_ids[ci]
        vals = dists[param].get(pid) or []
        assign_map[param] = pid
        assignment_list.append(
            {
                "blockParam": param,
                "blockParamHex": hex(param),
                "participantID": pid,
                "matches": len(vals),
                "medianDist": round(float(statistics.median(vals)), 3) if vals else None,
                "decodedInnerNetIdDistinct": sorted(
                    {
                        int(s.get("decodedInnerNetId") or s.get("netId") or 0)
                        for s in by_param[param]
                    }
                )[:12],
            }
        )

    raw_errors, raw_compared = evaluate_raw_point_errors(
        {p: by_param[p] for p in assign_map},
        assign_map,
        oracle_frames,
        tolerance_s=tolerance_s,
    )
    track_errors, track_compared = evaluate_continuity_track_errors(
        {p: by_param[p] for p in assign_map},
        assign_map,
        oracle_frames,
        tolerance_s=tolerance_s,
    )

    def _summary(errors: List[float], compared: int) -> dict:
        es = sorted(errors)
        return {
            "comparedSamples": compared,
            "medianError": round(float(statistics.median(es)), 3) if es else None,
            "p95Error": round(_percentile(es, 95) or 0.0, 3) if es else None,
            "maxError": round(max(es), 3) if es else None,
        }

    raw_sum = _summary(raw_errors, raw_compared)
    track_sum = _summary(track_errors, track_compared)

    def _passes(summary: dict, n_assign: int) -> bool:
        med = summary.get("medianError")
        p95 = summary.get("p95Error")
        mx = summary.get("maxError")
        return (
            n_assign >= ACCEPT_MIN_STABLE_ENTITIES
            and int(summary.get("comparedSamples") or 0) >= ACCEPT_MIN_COMPARED_SAMPLES
            and med is not None
            and float(med) <= ACCEPT_MAX_MEDIAN_ERROR
            and p95 is not None
            and float(p95) <= ACCEPT_MAX_P95_ERROR
            and mx is not None
            and float(mx) <= ACCEPT_MAX_MAX_ERROR
        )

    method_passed = None
    chosen = raw_sum
    if _passes(raw_sum, len(assignment_list)):
        method_passed = "raw_decoded_point"
        chosen = raw_sum
    elif _passes(track_sum, len(assignment_list)):
        method_passed = "continuity_constrained_nn_track"
        chosen = track_sum

    return {
        "ok": len(assignment_list) >= 1,
        "productEligible": False,
        "label": "research_only_not_product",
        "grouping": "blockParam",
        "method": "hungarian_blockParam",
        "methodPassed": method_passed,
        "toleranceS": tolerance_s,
        "oracleFrames": len(oracle_frames),
        "sampleCount": len(samples),
        "stableHeroParams": len(stable_params),
        "assignmentCount": len(assignment_list),
        "assignment": assignment_list,
        "comparedSamples": chosen.get("comparedSamples"),
        "medianError": chosen.get("medianError"),
        "p95Error": chosen.get("p95Error"),
        "maxError": chosen.get("maxError"),
        "rawPointEval": raw_sum,
        "continuityTrackEval": track_sum,
        "note": (
            "blockParam→participantID for QA only; decoded inner netId is diagnostic; "
            "continuity track seeded by oracle is research-only, not product output"
        ),
    }


def hero_param_channel_table(
    buckets: Mapping[int, ChannelBucket],
) -> List[dict]:
    """Rank channels by proven hero-param coverage before any schema decode."""
    rows = []
    for ch, b in buckets.items():
        distinct = len(b.hero_params)
        coverage = (
            float(b.time_max) - float(b.time_min)
            if b.time_min is not None and b.time_max is not None
            else 0.0
        )
        per_hero = {
            hex(p): int(b.hero_params.get(p, 0)) for p in PROVEN_HERO_NET_IDS
        }
        rows.append(
            {
                "channel": ch,
                "channelHex": hex(ch),
                "totalBlocks": b.count,
                "heroBlockCount": b.hero_block_count,
                "distinctHeroParams": distinct,
                "hasAll10HeroParams": distinct >= 10,
                "perHeroParamCounts": per_hero,
                "timeMin": b.time_min,
                "timeMax": b.time_max,
                "timeCoverageS": round(coverage, 3),
                "heroParamScore": (
                    100.0 * (1 if distinct >= 10 else distinct / 10.0)
                    + 20.0 * min(b.hero_block_count, 20000) / 20000.0
                    + 5.0 * min(coverage, 1600) / 1600.0
                ),
            }
        )
    rows.sort(
        key=lambda r: (
            int(r["hasAll10HeroParams"]),
            int(r["distinctHeroParams"]),
            int(r["heroBlockCount"]),
            float(r["heroParamScore"]),
        ),
        reverse=True,
    )
    return rows


def collect_channel_buckets(
    rofl: Path,
    *,
    sample_cap: int = DEFAULT_SAMPLE_CAP,
    max_time_s: Optional[float] = None,
    min_time_s: float = 0.0,
    max_blocks_per_chunk: int = 500_000,
) -> Tuple[Dict[int, ChannelBucket], dict]:
    """One walk: count every channel; keep bounded raw samples per channel."""
    t0 = time.perf_counter()
    info = parse_rofl2(rofl)
    t_read = time.perf_counter()
    extracted = extract_segments(info["payload"])
    t_inflate = time.perf_counter()

    buckets: Dict[int, ChannelBucket] = {}
    total_blocks = 0
    for seg in extracted["segments"]:
        if int(seg.get("type") or 0) != 1:
            continue
        for b in extract_blocks_py(seg["bytes"], max_blocks=max_blocks_per_chunk):
            t = float(b["time"])
            if t < min_time_s:
                continue
            if max_time_s is not None and t > float(max_time_s):
                continue
            total_blocks += 1
            ch = int(b["channel"]) & 0xFFFF
            bucket = buckets.get(ch)
            if bucket is None:
                bucket = ChannelBucket(channel=ch)
                buckets[ch] = bucket
            bucket.count += 1
            pay = b["payload"]
            psz = len(pay)
            bucket.payload_size_sum += psz
            if bucket.payload_size_min is None or psz < bucket.payload_size_min:
                bucket.payload_size_min = psz
            if bucket.payload_size_max is None or psz > bucket.payload_size_max:
                bucket.payload_size_max = psz
            if len(bucket.payload_size_reservoir) < 512:
                bucket.payload_size_reservoir.append(psz)
            # Always track proven hero params exactly; cap other params.
            param = int(b.get("param") or 0)
            if param in PROVEN_HERO_NET_ID_SET:
                bucket.hero_params[param] += 1
                bucket.hero_block_count += 1
                bucket.params[param] += 1
            elif len(bucket.params) < 64 or param in bucket.params:
                bucket.params[param] += 1
            if bucket.time_min is None or t < bucket.time_min:
                bucket.time_min = t
            if bucket.time_max is None or t > bucket.time_max:
                bucket.time_max = t
            sample = {
                "time": t,
                "channel": ch,
                "param": param,
                "payload": pay,
            }
            if len(bucket.samples) < sample_cap:
                bucket.samples.append(sample)
            else:
                j = random.randint(0, bucket.count - 1)
                if j < sample_cap:
                    bucket.samples[j] = sample
            if param in PROVEN_HERO_NET_ID_SET:
                if len(bucket.hero_samples) < sample_cap:
                    bucket.hero_samples.append(sample)
                else:
                    j = random.randint(0, bucket.hero_block_count - 1)
                    if j < sample_cap:
                        bucket.hero_samples[j] = sample

    t_walk = time.perf_counter()
    meta = {
        "gameVersion": (info.get("meta") or {}).get("gameVersion"),
        "totalBlocks": total_blocks,
        "channelCount": len(buckets),
        "timingMs": {
            "roflRead": round((t_read - t0) * 1000, 3),
            "zstdInflate": round((t_inflate - t_read) * 1000, 3),
            "blockWalk": round((t_walk - t_inflate) * 1000, 3),
            "wall": round((t_walk - t0) * 1000, 3),
        },
    }
    return buckets, meta


def decode_channel_samples(
    samples: Sequence[Mapping[str, Any]],
    *,
    lut: bytes,
    channel: int,
) -> dict:
    attempted = 0
    success = 0
    full_consume = 0
    coord_plausible = 0
    xs: List[int] = []
    zs: List[int] = []
    net_ids: Counter = Counter()
    block_params: Counter = Counter()
    decoded: List[dict] = []
    fail_reasons: Counter = Counter()
    t0 = time.perf_counter()

    for b in samples:
        attempted += 1
        block_param = int(b.get("param") or 0)
        res = decode_025b_payload(
            b["payload"],
            time_s=float(b["time"]),
            lut=lut,
            channel=channel,
            require_full_consume=True,
        )
        if not res.ok or res.sample is None:
            res2 = decode_025b_payload(
                b["payload"],
                time_s=float(b["time"]),
                lut=lut,
                channel=channel,
                require_full_consume=False,
            )
            if res2.ok and res2.sample is not None:
                success += 1
                fail_reasons["success_but_trailing_bytes"] += 1
            else:
                fail_reasons[res.error or "decode_failed"] += 1
            continue
        success += 1
        full_consume += 1
        s = res.sample
        row = s.as_dict()
        row["blockParam"] = block_param
        row["decodedInnerNetId"] = int(row["netId"])
        # Keep netId as decoded inner for diagnostics; QA should use blockParam.
        decoded.append(row)
        net_ids[s.net_id] += 1
        block_params[block_param] += 1
        xs.append(s.x)
        zs.append(s.z)
        if MAP_COORD_MIN <= s.x <= MAP_COORD_MAX and MAP_COORD_MIN <= s.z <= MAP_COORD_MAX:
            coord_plausible += 1

    elapsed = max(time.perf_counter() - t0, 1e-9)
    x_span = (max(xs) - min(xs)) if xs else 0
    z_span = (max(zs) - min(zs)) if zs else 0
    return {
        "attempted": attempted,
        "success": success,
        "fullConsume": full_consume,
        "successRatio": (success / attempted) if attempted else 0.0,
        "fullConsumeRatio": (full_consume / attempted) if attempted else 0.0,
        "coordPlausible": coord_plausible,
        "coordPlausibleRatio": (coord_plausible / success) if success else 0.0,
        "uniqueNetIds": len(net_ids),
        "uniqueBlockParams": len(block_params),
        "netIdCountsTop": [
            {"netId": nid, "count": n} for nid, n in net_ids.most_common(15)
        ],
        "blockParamCountsTop": [
            {"blockParam": p, "count": n} for p, n in block_params.most_common(15)
        ],
        "netIdMin": min(net_ids) if net_ids else None,
        "netIdMax": max(net_ids) if net_ids else None,
        "coordXSpan": x_span,
        "coordZSpan": z_span,
        "coordSpan": max(x_span, z_span),
        "samplesPerSec": attempted / elapsed,
        "decodedSamples": decoded,
        "failureHistogram": dict(fail_reasons.most_common(12)),
    }


def _payload_size_stats_from_bucket(bucket: ChannelBucket) -> dict:
    if bucket.count <= 0:
        return {"n": 0}
    ss = sorted(bucket.payload_size_reservoir) if bucket.payload_size_reservoir else []
    return {
        "n": bucket.count,
        "min": bucket.payload_size_min,
        "p50": ss[len(ss) // 2] if ss else None,
        "p95": ss[int(0.95 * (len(ss) - 1))] if ss else None,
        "max": bucket.payload_size_max,
        "mean": round(bucket.payload_size_sum / bucket.count, 2),
        "reservoirN": len(ss),
    }


def _param_identity_pattern(params: Counter) -> dict:
    if not params:
        return {"distinctParams": 0}
    total = sum(params.values())
    top = params.most_common(5)
    dominant = top[0]
    return {
        "distinctParams": len(params),
        "dominantParam": dominant[0],
        "dominantShare": round(dominant[1] / total, 4) if total else 0.0,
        "topParams": [{"param": p, "count": n} for p, n in top],
        # Movement often reuses entity param / net-related identity on wire.
        "paramEqualsLow16OfCommonNetId": None,  # filled later if known
    }


def rank_channel_candidate(
    *,
    channel: int,
    count: int,
    decode_stats: Mapping[str, Any],
    payload_stats: Mapping[str, Any],
    param_pattern: Mapping[str, Any],
    time_min: Optional[float],
    time_max: Optional[float],
    oracle: Optional[Mapping[str, Any]],
) -> dict:
    """Apply explicit gates. Schema success alone never accepts."""
    reasons: List[str] = []
    success_ratio = float(decode_stats.get("successRatio") or 0)
    full_ratio = float(decode_stats.get("fullConsumeRatio") or 0)
    coord_ratio = float(decode_stats.get("coordPlausibleRatio") or 0)
    unique_n = int(decode_stats.get("uniqueNetIds") or 0)
    span = float(decode_stats.get("coordSpan") or 0)
    coverage = (
        float(time_max) - float(time_min)
        if time_min is not None and time_max is not None
        else 0.0
    )

    if success_ratio < ACCEPT_MIN_SUCCESS_RATIO:
        reasons.append(f"low_success_ratio:{success_ratio:.3f}")
    if full_ratio < ACCEPT_MIN_FULL_CONSUME_RATIO:
        reasons.append(f"low_full_consume_ratio:{full_ratio:.3f}")
    if coord_ratio < ACCEPT_MIN_COORD_PLAUSIBLE_RATIO:
        reasons.append(f"low_coord_plausible_ratio:{coord_ratio:.3f}")
    if unique_n < ACCEPT_MIN_UNIQUE_NET_IDS:
        reasons.append(f"few_unique_net_ids:{unique_n}")
    if span < ACCEPT_MIN_COORD_SPAN:
        reasons.append(f"low_coord_variation_span:{span}")
    if count < ACCEPT_MIN_CHANNEL_COUNT:
        reasons.append(f"channel_count_below_movement_scale:{count}")
    if coverage < ACCEPT_MIN_TIME_COVERAGE_S:
        reasons.append(f"low_time_coverage_s:{coverage:.1f}")

    # Schema-only is never enough.
    schema_ok = (
        success_ratio >= ACCEPT_MIN_SUCCESS_RATIO
        and full_ratio >= ACCEPT_MIN_FULL_CONSUME_RATIO
        and unique_n >= ACCEPT_MIN_UNIQUE_NET_IDS
    )
    if schema_ok and oracle is None:
        reasons.append("schema_only_no_oracle")

    oracle_pass = False
    oracle_summary: Dict[str, Any] = {}
    if oracle:
        oracle_summary = {
            "assignmentCount": oracle.get("assignmentCount"),
            "comparedSamples": oracle.get("comparedSamples"),
            "medianError": oracle.get("medianError"),
            "p95Error": oracle.get("p95Error"),
            "maxError": oracle.get("maxError"),
        }
        ac = int(oracle.get("assignmentCount") or 0)
        compared = int(oracle.get("comparedSamples") or 0)
        med = oracle.get("medianError")
        p95 = oracle.get("p95Error")
        mx = oracle.get("maxError")
        if ac < ACCEPT_MIN_STABLE_ENTITIES:
            reasons.append(f"unstable_entities:{ac}")
        if compared < ACCEPT_MIN_COMPARED_SAMPLES:
            reasons.append(f"insufficient_oracle_comparisons:{compared}")
        if med is None or float(med) > ACCEPT_MAX_MEDIAN_ERROR:
            reasons.append(f"median_error_high:{med}")
        if p95 is None or float(p95) > ACCEPT_MAX_P95_ERROR:
            reasons.append(f"p95_error_high:{p95}")
        if mx is None or float(mx) > ACCEPT_MAX_MAX_ERROR:
            reasons.append(f"max_error_high:{mx}")
        oracle_pass = (
            ac >= ACCEPT_MIN_STABLE_ENTITIES
            and compared >= ACCEPT_MIN_COMPARED_SAMPLES
            and med is not None
            and float(med) <= ACCEPT_MAX_MEDIAN_ERROR
            and p95 is not None
            and float(p95) <= ACCEPT_MAX_P95_ERROR
            and mx is not None
            and float(mx) <= ACCEPT_MAX_MAX_ERROR
        )
        if not oracle_pass and "schema_only_no_oracle" not in reasons:
            if schema_ok:
                reasons.append("schema_shaped_but_oracle_failed")

    accepted = bool(
        oracle_pass
        and schema_ok
        and coord_ratio >= ACCEPT_MIN_COORD_PLAUSIBLE_RATIO
        and span >= ACCEPT_MIN_COORD_SPAN
        and count >= ACCEPT_MIN_CHANNEL_COUNT
        and coverage >= ACCEPT_MIN_TIME_COVERAGE_S
    )
    if accepted:
        reasons = [r for r in reasons if not r.startswith("schema_only")]

    # Score for ranking (higher better); oracle-weighted.
    score = 0.0
    score += 10.0 * success_ratio
    score += 8.0 * full_ratio
    score += 5.0 * min(unique_n, 20) / 20.0
    score += 4.0 * min(span, 8000) / 8000.0
    score += 3.0 * min(count, 50000) / 50000.0
    if oracle:
        ac = int(oracle.get("assignmentCount") or 0)
        compared = int(oracle.get("comparedSamples") or 0)
        med = float(oracle.get("medianError") or 1e9)
        score += 20.0 * min(ac, 10) / 10.0
        score += 15.0 * min(compared, 500) / 500.0
        score += 25.0 * max(0.0, 1.0 - med / 500.0)
        if oracle_pass:
            score += 100.0

    return {
        "channel": channel,
        "channelHex": hex(channel),
        "count": count,
        "accepted": accepted,
        "oraclePass": oracle_pass,
        "schemaOk": schema_ok,
        "score": round(score, 3),
        "falsePositiveReasons": reasons,
        "successRatio": round(success_ratio, 4),
        "fullConsumeRatio": round(full_ratio, 4),
        "coordPlausibleRatio": round(coord_ratio, 4),
        "uniqueNetIds": unique_n,
        "coordSpan": span,
        "timeCoverageS": round(coverage, 3),
        "payloadSize": payload_stats,
        "paramPattern": param_pattern,
        "oracle": oracle_summary,
        "public025b": channel == MOVEMENT_PACKET_ID,
    }


def optional_unicorn_factory_map(
    channels: Sequence[int],
    *,
    league_binary: Path = DEFAULT_LEAGUE_BINARY,
    work_dir: Optional[Path] = None,
) -> dict:
    """Cheap Packet::Packet factory smoke for candidate wire ids.

    Emulator failures must not suppress the offline scanner — always returns
    a report dict with ok=False on failure.
    """
    import struct
    import tempfile

    out: Dict[str, Any] = {
        "ok": False,
        "attempted": list(channels),
        "results": [],
        "error": None,
        "note": "optional; offline ranking proceeds regardless",
    }
    if not channels:
        out["error"] = "no channels"
        return out
    if not Path(league_binary).is_file():
        out["error"] = "league binary missing"
        return out
    try:
        from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM

        import rofl2_accessor_spike as spike
        import rofl2_unicorn_packet_drive as drive
    except Exception as exc:  # noqa: BLE001
        out["error"] = f"import_failed:{exc}"
        return out
    try:
        if work_dir is None:
            work_dir = Path(tempfile.mkdtemp(prefix="lol-wire-scan-factory-"))
        work_dir.mkdir(parents=True, exist_ok=True)
        arm64_path = work_dir / "LeagueofLegends.arm64"
        spike.thin_arm64(Path(league_binary), arm64_path)
        data = arm64_path.read_bytes()
        segments = spike._parse_segments(data)
        mu = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
        drive.map_binary(mu, data, segments)
        for base, size in (
            (drive.ARENA_BASE, 0x00100000),
            (drive.HEAP_BASE, drive.HEAP_SIZE),
            (drive.STACK_BASE, drive.STACK_SIZE),
            (drive.BUF_BASE, drive.BUF_SIZE),
            (drive.SCRATCH, 0x00100000),
        ):
            try:
                mu.mem_map(base, size)
            except Exception:  # noqa: BLE001
                pass
        heap = drive.BumpHeap()
        drive.install_block_runtime_hooks(mu, heap)
        try:
            mu.mem_write(
                drive.TYPE_COUNT_GLOBAL, struct.pack("<I", drive.TYPE_COUNT_VALUE)
            )
        except Exception:  # noqa: BLE001
            pass
        results = []
        for ch in channels:
            info = drive.create_packet(mu, heap, int(ch))
            results.append(
                {
                    "channel": ch,
                    "packet": bool(info.get("packet")),
                    "storedType": info.get("storedType"),
                    "vtable": hex(info["vtable"]) if info.get("vtable") else None,
                    "deserialize": hex(info["deserialize"])
                    if info.get("deserialize")
                    else None,
                    "callError": (info.get("call") or {}).get("error"),
                }
            )
        out["results"] = results
        out["ok"] = any(r.get("packet") for r in results)
        return out
    except Exception as exc:  # noqa: BLE001
        out["error"] = f"unicorn_failed:{exc}"
        out["ok"] = False
        return out


def deep_decode_channel(
    rofl: Path,
    *,
    channel: int,
    lut: bytes,
    max_time_s: Optional[float] = None,
    min_time_s: float = 0.0,
    deep_cap: int = DEFAULT_DEEP_CAP,
    hero_params_only: bool = True,
) -> dict:
    """Decode up to deep_cap packets for one wire id (research full pass)."""
    samples_raw: List[dict] = []
    info = parse_rofl2(rofl)
    extracted = extract_segments(info["payload"])
    for seg in extracted["segments"]:
        if int(seg.get("type") or 0) != 1:
            continue
        for b in extract_blocks_py(seg["bytes"], max_blocks=500_000):
            t = float(b["time"])
            if t < min_time_s:
                continue
            if max_time_s is not None and t > float(max_time_s):
                continue
            if int(b["channel"]) != int(channel):
                continue
            param = int(b.get("param") or 0)
            if hero_params_only and param not in PROVEN_HERO_NET_ID_SET:
                continue
            samples_raw.append(
                {
                    "time": t,
                    "channel": channel,
                    "param": param,
                    "payload": b["payload"],
                }
            )
            if len(samples_raw) >= deep_cap:
                break
        if len(samples_raw) >= deep_cap:
            break
    stats = decode_channel_samples(samples_raw, lut=lut, channel=channel)
    stats["collected"] = len(samples_raw)
    stats["heroParamsOnly"] = bool(hero_params_only)
    stats["gameVersion"] = (info.get("meta") or {}).get("gameVersion")
    return stats


def scan_wire_ids(
    rofl: Path,
    *,
    lut: bytes,
    oracle_jsonl: Optional[Path] = None,
    sample_cap: int = DEFAULT_SAMPLE_CAP,
    deep_cap: int = DEFAULT_DEEP_CAP,
    max_time_s: Optional[float] = None,
    min_time_s: float = 0.0,
    oracle_tolerance_s: float = DEFAULT_ORACLE_TOLERANCE_S,
    shortlist_size: int = 12,
    try_unicorn: bool = True,
    league_binary: Path = DEFAULT_LEAGUE_BINARY,
) -> dict:
    """E2.1 scan: hero-param-first ranking, then schema+oracle on shortlist.

    Historical E2 (decoded-inner grouping) is preserved as discarded in docs;
    this function implements the corrected methodology.
    """
    t0 = time.perf_counter()
    buckets, walk_meta = collect_channel_buckets(
        rofl,
        sample_cap=sample_cap,
        max_time_s=max_time_s,
        min_time_s=min_time_s,
    )
    oracle_frames: List[dict] = []
    if oracle_jsonl and Path(oracle_jsonl).is_file():
        oracle_frames = _load_oracle_positions(Path(oracle_jsonl))

    hero_table = hero_param_channel_table(buckets)
    # First rank by all-10 hero params + movement-scale counts BEFORE schema.
    shortlist_meta = [
        r
        for r in hero_table
        if r["hasAll10HeroParams"] and r["heroBlockCount"] >= ACCEPT_MIN_HERO_BLOCKS
    ][:shortlist_size]
    if len(shortlist_meta) < shortlist_size:
        # Fill with remaining all-10 / high-hero channels.
        seen = {int(r["channel"]) for r in shortlist_meta}
        for r in hero_table:
            if int(r["channel"]) in seen:
                continue
            if r["distinctHeroParams"] >= 8:
                shortlist_meta.append(r)
                seen.add(int(r["channel"]))
            if len(shortlist_meta) >= shortlist_size:
                break

    deep_results: List[dict] = []
    for item in shortlist_meta:
        ch = int(item["channel"])
        bucket = buckets[ch]
        # Prefer hero-param reservoir for bounded decode, then deep hero-only.
        seed = bucket.hero_samples or bucket.samples
        seed_dec = decode_channel_samples(seed, lut=lut, channel=ch)
        deep = deep_decode_channel(
            rofl,
            channel=ch,
            lut=lut,
            max_time_s=max_time_s,
            min_time_s=min_time_s,
            deep_cap=deep_cap,
            hero_params_only=True,
        )
        decoded = deep.get("decodedSamples") or seed_dec.get("decodedSamples") or []
        oracle = None
        if oracle_frames and decoded:
            oracle = optimal_oracle_assignment_by_block_param(
                decoded,
                oracle_frames,
                tolerance_s=oracle_tolerance_s,
            )
        ranked = rank_channel_candidate(
            channel=ch,
            count=int(item["totalBlocks"]),
            decode_stats=deep if deep.get("attempted") else seed_dec,
            payload_stats=_payload_size_stats_from_bucket(bucket),
            param_pattern=_param_identity_pattern(bucket.params),
            time_min=item.get("timeMin"),
            time_max=item.get("timeMax"),
            oracle=oracle,
        )
        # Hero-param presence alone must not accept.
        hero_only_ok = bool(item["hasAll10HeroParams"]) and int(item["heroBlockCount"]) >= ACCEPT_MIN_HERO_BLOCKS
        if hero_only_ok and not ranked.get("oraclePass"):
            reasons = list(ranked.get("falsePositiveReasons") or [])
            if "hero_params_alone_not_sufficient" not in reasons:
                reasons.append("hero_params_alone_not_sufficient")
            ranked["falsePositiveReasons"] = reasons
            ranked["accepted"] = False

        # Override acceptance using blockParam methodPassed when present.
        if oracle and oracle.get("methodPassed"):
            ranked["oraclePass"] = True
            ranked["accepted"] = bool(
                ranked.get("schemaOk")
                and float(ranked.get("coordSpan") or 0) >= ACCEPT_MIN_COORD_SPAN
                and float(ranked.get("timeCoverageS") or 0) >= ACCEPT_MIN_TIME_COVERAGE_S
                and int(item["heroBlockCount"]) >= ACCEPT_MIN_HERO_BLOCKS
            )
            if ranked["accepted"]:
                ranked["falsePositiveReasons"] = [
                    r
                    for r in (ranked.get("falsePositiveReasons") or [])
                    if not r.startswith(
                        (
                            "hero_params_alone",
                            "schema_shaped",
                            "insufficient",
                            "median_error",
                            "p95_error",
                            "max_error",
                            "unstable",
                        )
                    )
                ]
            ranked["score"] = round(float(ranked.get("score") or 0) + 150.0, 3)

        deep_slim = {k: v for k, v in deep.items() if k != "decodedSamples"}
        deep_results.append(
            {
                **ranked,
                "heroBlockCount": item["heroBlockCount"],
                "distinctHeroParams": item["distinctHeroParams"],
                "perHeroParamCounts": item["perHeroParamCounts"],
                "deep": deep_slim,
                "oracleFull": {
                    k: oracle.get(k)
                    for k in (
                        "assignmentCount",
                        "comparedSamples",
                        "medianError",
                        "p95Error",
                        "maxError",
                        "assignment",
                        "method",
                        "methodPassed",
                        "grouping",
                        "label",
                        "productEligible",
                        "rawPointEval",
                        "continuityTrackEval",
                        "stableHeroParams",
                    )
                }
                if oracle
                else None,
                "sampleDecodedCount": len(decoded),
            }
        )

    deep_results.sort(
        key=lambda r: (
            int(bool(r.get("accepted"))),
            int(bool(r.get("oraclePass"))),
            float(r.get("score") or 0),
            int(r.get("heroBlockCount") or 0),
        ),
        reverse=True,
    )
    winners = [r for r in deep_results if r.get("accepted")]
    winner = winners[0] if winners else None

    unicorn = None
    if try_unicorn:
        top_chs = [int(r["channel"]) for r in deep_results[:8]]
        unicorn = optional_unicorn_factory_map(top_chs, league_binary=league_binary)

    wall_ms = (time.perf_counter() - t0) * 1000
    next_hyp = (
        "E3: confirm movement encoding change (not just wire id) — "
        "legacy 0x61 multi-waypoint group or alternate cipher/schema on 16.14"
        if winner is None
        else f"E3: full-match decode with --packet-id {winner['channel']} "
        "and cadence/identity product gates"
    )

    return {
        "ok": True,
        "mode": "scan-wire-ids",
        "phase": "B-E2.1",
        "methodology": "hero_param_first_blockParam_qa",
        "priorE2": {
            "phase": "B-E2",
            "keep": "discard",
            "note": "Historical E2 grouped by decoded inner netId; preserved discarded",
            "report": "docs/rofl-research/movement-wire-scan-BR1-3264361042.json",
        },
        "provenance": PROVENANCE,
        "productEligible": False,
        "publicPacketId": MOVEMENT_PACKET_ID,
        "provenHeroNetIds": list(PROVEN_HERO_NET_IDS),
        "provenHeroNetIdsHex": [hex(x) for x in PROVEN_HERO_NET_IDS],
        "walk": walk_meta,
        "acceptanceThresholds": {
            "minStableEntities": ACCEPT_MIN_STABLE_ENTITIES,
            "minComparedSamples": ACCEPT_MIN_COMPARED_SAMPLES,
            "maxMedianError": ACCEPT_MAX_MEDIAN_ERROR,
            "maxP95Error": ACCEPT_MAX_P95_ERROR,
            "maxMaxError": ACCEPT_MAX_MAX_ERROR,
            "minSuccessRatio": ACCEPT_MIN_SUCCESS_RATIO,
            "minFullConsumeRatio": ACCEPT_MIN_FULL_CONSUME_RATIO,
            "minCoordPlausibleRatio": ACCEPT_MIN_COORD_PLAUSIBLE_RATIO,
            "minCoordSpan": ACCEPT_MIN_COORD_SPAN,
            "minUniqueNetIds": ACCEPT_MIN_UNIQUE_NET_IDS,
            "minChannelCount": ACCEPT_MIN_CHANNEL_COUNT,
            "minTimeCoverageS": ACCEPT_MIN_TIME_COVERAGE_S,
            "minHeroParams": ACCEPT_MIN_HERO_PARAMS,
            "minHeroBlocks": ACCEPT_MIN_HERO_BLOCKS,
            "oracleToleranceS": oracle_tolerance_s,
            "qaGrouping": "blockParam",
            "note": "hero params alone never accept; schema alone never accept",
        },
        "channelsScanned": len(buckets),
        "heroParamChannelTable": hero_table[:40],
        "shortlistDeep": deep_results,
        "winner": (
            {
                "channel": winner["channel"],
                "channelHex": winner["channelHex"],
                "score": winner["score"],
                "count": winner["count"],
                "heroBlockCount": winner.get("heroBlockCount"),
                "oracle": winner.get("oracle"),
                "methodPassed": (winner.get("oracleFull") or {}).get("methodPassed"),
            }
            if winner
            else None
        ),
        "winnerFound": winner is not None,
        "unicornFactory": unicorn,
        "endToEndWallMs": round(wall_ms, 3),
        "nextSingleVariableHypothesis": next_hyp,
        "keep": "keep-research" if winner is not None else "discard",
        "reason": (
            f"E2.1 winner channel={winner['channel']} ({winner['channelHex']}) "
            f"method={(winner.get('oracleFull') or {}).get('methodPassed')}"
            if winner
            else "E2.1 no wire-id remap winner after blockParam QA; "
            "hero-param channels failed schema/oracle gates"
        ),
    }
