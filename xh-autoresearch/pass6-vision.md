# Pass-6 VISION — zone-discipline · margin→σ_seen · occupancy hypotheses

**Axis:** vision  
**Agent:** Pass-6 VISION  
**Against:** Post Pass-5 KEEP (`math_pass_rate=129/129`) — complete no_lkp (null-geo), soft σ_occ asymptote (`u≤0.72`), combat wards plumbing  
**Constraint honored:** **no edits** to `xh.ts` / `vision.ts` / combat / eval. Proposal only.  
**Do not re-propose:** LKP geo mean API, κ=1/√3, softVisionAt / resolveCastVisionSoft shell, mixture-of-CDFs ∫L b, spotted τ sign, √t / Flash-belief / brush cap, softV→σ_seen *exponential form*, `beliefMeanSeen` binary multi-mean, `aEff` slow-growth, factor-only `belief:no_lkp_guard`, complete null-geo openLoop (`geoPos=undefined`, `leadSkill=0`, σ floor), soft asymptote `u≤0.72` *as shipped*, combat `wards` plumbing.  
**Verdict:** **KEEP_CANDIDATE**

---

## 0. What Pass-1–5 fixed vs what remains

| Landed claim | Status @ Pass-6 |
|---|---|
| Reachable-set `σ_belief` + √t + Flash + brush + `aEff` | **Shipped** |
| SoftVision mixture-of-CDFs ∫L b + `beliefMeanSeen` | **Shipped** (binary means) |
| Complete no_lkp null-geo + `leadSkill=0` + σ floor | **Shipped** |
| Soft σ_occ asymptote `u≤0.72` | **Shipped**; still **zone-oracle** under openLoop |
| Combat / overlay ward plumbing | **Shipped** |
| `softVisionAt` margin → σ_seen | **Unshipped** — margin collapsed into `v` only |
| Weighted `beliefHypotheses[]` | **Unshipped** |

Program residual (Pass-6 deepen **σ_belief / soft vision only**):

1. **Open-loop zone discipline** — null-geo pose is honest; zone / brush / `σ_occ` still read oracle `targetPosition`.  
2. **Sensor margin → σ_seen** — Koopman penumbra discarded after logistic.  
3. **Occupancy multi-hypothesis** — after soft asymptote, single Gaussian ≠ brush-exit / river modes.  
4. Optional: tighten ancient asymptote residual (eval tol `occ+450` is loose) via hypotheses, not by re-litigating `u≤0.72`.

No BASE×ZONE×VISION. Zone scale on aim/juke may stay.

---

## 1. Critique (concrete residuals)

### 1.1 Open-loop zone still god-eyes (P0 — hard-rule residue)

```628:639:src/engine/xh.ts
  const fowDark = softV < 0.85 || vision === 'blind'
  const hasBelief = !!input.beliefMeanPosition
  // FoW: aim/range from belief mean when LKP provided; without LKP do not god-eye.
  let openLoopBelief = false
  let geoPos = input.targetPosition
  if (fowDark && hasBelief) {
    geoPos = input.beliefMeanPosition
  } else if (fowDark && !hasBelief) {
    openLoopBelief = true
    geoPos = undefined
  }
  const targetZone = zoneAt(geoPos ?? input.targetPosition)
```

Pass-5 closed μ / distance / lead. Residual: when `geoPos` is undefined, `zoneAt(… ?? input.targetPosition)` still labels **oracle** zone → `occupancySigma(targetZone)`, brush Cap, `zoneSigmaScale`. Floor uses `casterZone` while LKP path uses oracle `targetZone`:

```912:915:src/engine/xh.ts
  const sigmaLost = openLoopBelief
    ? Math.max(sigmaLostRaw, occupancySigma(casterZone))
    : sigmaLostRaw
```

Blind without belief must not know the target sits in brush vs lane. Hard rule: *Blind casts must not treat true position as known without belief.* Zone is position-derived state.

### 1.2 softV→σ_seen ignores sensor margin (P0 deepen of soft vision)

```179:210:src/engine/vision.ts
export function softVisionAt(
  ...
): number {
  ...
    const margin = r - dist(a.position, target)
    best = Math.max(best, 1 / (1 + Math.exp(-kappa * margin)))
  ...
  return best
}
```

```916:916:src/engine/xh.ts
  const sigmaSeen = Math.hypot(18, 55 * Math.exp(-2.8 * softV))
```

Koopman soft-detection already computes `margin = r − d` per champ/ward, then throws it away. Two casts with equal softV (e.g. both ≈0.55) can sit deep in penumbra vs barely inside — σ_meas should track **bestMarginNorm = margin / r_sensor**, not only the logistic collapse. Pass-5 deferred this; combat wards now make margin informative.

Do **not** replace the Pass-3 softV exponential when margin is absent — additive path only.

### 1.3 Soft asymptote saturates to one Gaussian (P1)

```892:896:src/engine/xh.ts
    const sigmaOcc = occupancySigma(opts.zone ?? targetZone)
    const u = Math.min(0.72, a / T_SAT)
    if (reach <= sigmaOcc) return reach
    return reach * (1 - u) + sigmaOcc * u
```

`u≤0.72` + single `σ_occ(zone)` is correct *shape*, but ancient support is still unimodal. FoW search priors after contact loss are typically **multi-modal** (brush pockets, river choke, jungle quadrant). Binary `beliefMeanSeen` only covers penumbra vs LKP — not occupancy exit modes. Eval V15b tol `occ+450` leaves little pressure on content.

### 1.4 `hasBelief` ignores hypotheses (P1 API gap)

```629:629:src/engine/xh.ts
  const hasBelief = !!input.beliefMeanPosition
```

Once `beliefHypotheses[]` lands, FoW with hypotheses-only (no single LKP mean) must count as belief — else openLoop triggers incorrectly. Wire `hasBelief` to hypotheses in the same KEEP slice.

---

## 2. Proposed minimal deepen (orchestrator → later)

**Scope:** zone-discipline under openLoop + margin→σ_seen + optional `beliefHypotheses[]`. No BASE×ZONE×VISION. Do not re-litigate Pass-1–5 KEEP shape (null-geo, `u≤0.72`, wards, softV exp, mixture shell).

### 2.1 Open-loop zone = caster / unknown (behavior)

```ts
const fowDark = softV < 0.85 || vision === 'blind'
const hasBelief =
  !!input.beliefMeanPosition || !!(input.beliefHypotheses?.length)

let openLoopBelief = false
let geoPos = input.targetPosition
if (fowDark && hasBelief) {
  geoPos =
    input.beliefMeanPosition ??
    dominantHypothesisMean(input.beliefHypotheses!)
} else if (fowDark && !hasBelief) {
  openLoopBelief = true
  geoPos = undefined
}

// Zone from belief pose only — never oracle under openLoop.
const targetZone = openLoopBelief
  ? casterZone // or zoneAt(input.beliefZoneHint) if callers pass a prior
  : zoneAt(geoPos ?? input.targetPosition)

// sigmaBeliefLkp / brushCap / zScale already read targetZone —
// openLoop now shares caster-centric occupancy with the σ floor.
```

**Eval-safe:** fixtures that need brush Cap under blind must set `beliefMeanPosition` (and optionally `beliefZoneHint`). Default no-LKP must **not** get oracle brush Cap or lane vs brush σ_occ split.

### 2.2 Margin-aware σ_seen (soft vision deepen)

```ts
// vision.ts — additive return (compat wrapper ok)
export function softVisionAt(...): number // keep
export function softVisionDetailAt(...): {
  v: number
  bestMarginNorm: number // margin / r_sensor of winning sensor; −∞ if none
}

// resolveCastVisionSoft → softVision + optional softVisionMarginNorm

// xh.ts
const sigmaSeen =
  input.softVisionMarginNorm != null
    ? Math.hypot(
        18,
        55 * Math.exp(-2.8 * Math.max(0, input.softVisionMarginNorm)),
      )
    : Math.hypot(18, 55 * Math.exp(-2.8 * softV)) // Pass-3 KEEP fallback
```

Preserve: softVision edge > dark; equal softV with deeper margin → **lower** σ_seen / higher xH.

### 2.3 `beliefHypotheses[]` occupancy modes (after 2.1–2.2)

```ts
// XhEstimateInput additive:
beliefHypotheses?: {
  weight: number
  mean: MapPosition
  ageSec?: number
  sigmaBelief?: number
  zone?: MapZone
}[]

function pack(sigmaJuke: number) {
  if (input.beliefHypotheses?.length) {
    const hs = normalizeWeights(input.beliefHypotheses)
    let xH = 0
    let belief2 = 0
    for (const h of hs) {
      const muK = lateralMissAtMean(h.mean) // same ballisticSegmentMiss path
      const sigB =
        h.sigmaBelief ??
        sigmaBeliefLkp({
          ageSec: h.ageSec ?? age,
          zone: h.zone ?? zoneAt(h.mean),
          ...
        })
      const sigK = Math.hypot(aim, juke, sigB, 12)
      xH += h.weight * corridorHitProb(R_hit, muK, sigK)
      belief2 += h.weight * sigB * sigB
    }
    return {
      xH: clamp01(xH),
      sigma: { aim, juke, belief: Math.sqrt(belief2), total: ... },
    }
  }
  // else: existing softV mix + beliefMeanSeen path — do not re-litigate
}
```

Prefer 2–3 modes when age ≥ T_SAT (e.g. brush 0.4 / river 0.35 / jungle 0.25) instead of fattening one Gaussian past `u≤0.72`.

### 2.4 Out of scope this pass

- Replacing `u≤0.72` with `u→1` (would re-litigate Pass-5 KEEP; use hypotheses instead).  
- Historic hit-rate MLE, particle filters.  
- BASE×ZONE×VISION.  
- Editing production / eval in this agent.

---

## 3. New eval asserts (additive — do not soften 129)

```ts
// V18: open-loop zone ≠ oracle zone Cap
const inBrushTruth = /* target in brush, caster in lane, no LKP */
const noLkp = estimateXh(base({
  vision: 'blind', softVision: 0, lastKnownAgeSec: 4,
  beliefMeanPosition: undefined,
  casterPosition: lanePos, targetPosition: brushPos,
}))
const withLkpBrush = estimateXh(base({
  vision: 'blind', softVision: 0, lastKnownAgeSec: 4,
  beliefMeanPosition: brushPos,
  casterPosition: lanePos, targetPosition: brushPos,
}))
assert(
  'no-LKP must not inherit oracle brush Cap / zone',
  noLkp.targetZone !== 'brush' || noLkp.factors.includes('belief:no_lkp_guard'),
)
assert(
  'LKP-in-brush belief σ ≤ no-LKP (or Cap differs)',
  !!noLkp.sigma && !!withLkpBrush.sigma &&
    (withLkpBrush.sigma.belief <= noLkp.sigma.belief + 1e-6
      || noLkp.targetZone !== withLkpBrush.targetZone),
)

// V19: margin→σ_seen — deeper penumbra, same softV proxy path
const shallow = estimateXh(base({
  vision: 'mutual', softVision: 0.55, softVisionMarginNorm: 0.05,
}))
const deep = estimateXh(base({
  vision: 'mutual', softVision: 0.55, softVisionMarginNorm: 0.55,
}))
assert(
  'deeper margin → lower σ_seen / higher xH',
  !!deep.sigma && !!shallow.sigma &&
    deep.sigma.belief <= shallow.sigma.belief + 1e-9 &&
    deep.xH >= shallow.xH - 1e-9,
)

// V20: multi-hypothesis ≤ equal-weight single fat mode (or ≤ equal-mean mix)
const uni = estimateXh(base({
  vision: 'blind', softVision: 0, lastKnownAgeSec: 12,
  beliefMeanPosition: near,
}))
const multi = estimateXh(base({
  vision: 'blind', softVision: 0, lastKnownAgeSec: 12,
  beliefHypotheses: [
    { weight: 0.5, mean: near, zone: 'brush' },
    { weight: 0.5, mean: { x: near.x + 0.08, y: near.y }, zone: 'river' },
  ],
}))
assert('hypothesis mix ≤ unimodal LKP xH', multi.xH <= uni.xH + 1e-9)

// Preserve: no-LKP ≠ god-eye, ancient xH ≤ mid, ancient σ ≲ occ+tol,
// softVision edge>dark, spotted≤unspotted, ambush≥mutual, no BASE×ZONE×VISION.
```

Update fixtures that relied on oracle brush Cap under blind-without-LKP to set explicit LKP.

---

## 4. arXiv / cites (Pass-6 focus)

| ID | Use |
|---|---|
| [2602.11373](https://arxiv.org/abs/2602.11373) | Full posterior — zone is state; no oracle zone under FoW |
| [1812.00054](https://arxiv.org/abs/1812.00054) | FoW state estimation; prior over regions not points |
| [2306.11301](https://arxiv.org/abs/2306.11301) | Reachable sets → occupancy / search priors |
| [2009.08922](https://arxiv.org/abs/2009.08922) | Multi-hypothesis beliefs under FoW |
| [2410.13587](https://arxiv.org/abs/2410.13587) | Sensor margin → measurement noise |
| [2604.17811](https://arxiv.org/abs/2604.17811) | ∫L b — distinct hypothesis means |
| Koopman 1956 | Soft detection; ward/champ margin ↔ σ_meas |

---

## 5. Expected metric impact

| Change | Current 129 | After asserts |
|---|---|---|
| Open-loop zone discipline | May change no-LKP brush Cap path | Fixture LKP for brush tests; enables V18 |
| Margin→σ_seen | Additive soft API | Enables V19; softV-only path unchanged |
| `beliefHypotheses[]` | Opt-in | Enables V20 |
| Legacy equal-mean + explicit LKP | Keep ordering | Stay 129/129 then 129+k/129+k |

**Primary score:** expect stay `129/129` after fixture zone annotations; then `129+k/129+k` with V18/V19/V20.

---

## 6. Minimal patch plan (orchestrator)

1. **Open-loop zone** — `targetZone = casterZone` (or belief hint) when `openLoopBelief`; extend `hasBelief` to hypotheses.  
2. **`softVisionDetailAt` / marginNorm** → `XhEstimateInput.softVisionMarginNorm` → σ_seen; keep softV exponential fallback.  
3. Optional **`beliefHypotheses[]`** pack path (Σ w_k Φ_corr).  
4. Append V18, V19, V20 to `eval-xh-math.ts` after (1)–(2).  

**Out of scope:** re-proposing null-geo / `u≤0.72` / combat wards / softV exp / mixture shell / spotted τ / √t-Flash-brush / beliefMeanSeen / aEff, BASE×ZONE×VISION, editing production files in this agent.

---

## 7. Decision

**KEEP_CANDIDATE**

Rationale: Pass-5 made pose honest under FoW (null-geo, soft σ_occ, ward plumbing). Pass-6 residual is **belief content under soft vision**: stop reading oracle zone for occupancy/brush Cap, wire Koopman margin into σ_seen, and allow closed-form occupancy hypotheses — still inside \(\sigma^2=\sigma_{\mathrm{aim}}^2+\sigma_{\mathrm{juke}}^2+\sigma_{\mathrm{belief}}^2\).

**SKIP** only if Pass-6 bandwidth must fix a failing geo/aim/strategy invariant; vision harness is green (129/129), but open-loop still god-eyes zone and softVision discards sensor margin.

---

**One-line verdict:** KEEP_CANDIDATE — open-loop zone discipline + margin→σ_seen + beliefHypotheses; do not re-litigate null-geo / u≤0.72 / wards.
