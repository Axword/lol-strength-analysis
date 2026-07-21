# Pass-7 VISION — beliefHypotheses · hasBelief wire · overlay margin

**Axis:** vision  
**Agent:** Pass-7 VISION  
**Against:** Post Pass-6 KEEP (`math_pass_rate=148/148`) — open-loop `targetZone=casterZone`, `softVisionMarginNorm` → σ_seen, null-geo, soft `u≤0.72`, combat wards + margin  
**Constraint honored:** **no edits** to `xh.ts` / `vision.ts` / combat / overlay / eval. Proposal only.  
**Do not re-propose:** LKP geo mean API, κ=1/√3, softVisionAt / softVisionDetailAt / resolveCastVisionSoft shell, mixture-of-CDFs ∫L b, spotted τ sign, √t / Flash-belief / brush Cap, softV→σ_seen *exponential form*, margin→σ_seen *form*, `beliefMeanSeen` binary multi-mean, `aEff` slow-growth, factor-only `belief:no_lkp_guard`, complete null-geo openLoop (`geoPos=undefined`, `leadSkill=0`, σ floor), soft asymptote `u≤0.72`, combat `wards` plumbing, open-loop zone=caster.  
**Verdict:** **KEEP_CANDIDATE**

---

## 0. What Pass-1–6 fixed vs what remains

| Landed claim | Status @ Pass-7 |
|---|---|
| Reachable-set `σ_belief` + √t + Flash + brush + `aEff` | **Shipped** |
| SoftVision mixture-of-CDFs ∫L b + `beliefMeanSeen` | **Shipped** (binary means) |
| Complete no_lkp null-geo + `leadSkill=0` + σ floor | **Shipped** |
| Soft σ_occ asymptote `u≤0.72` | **Shipped**; still **unimodal** |
| Combat / overlay ward plumbing | **Shipped** (combat); overlay still drops margin |
| Open-loop zone = caster | **Shipped** (Pass-6) |
| `softVisionMarginNorm` → σ_seen | **Shipped** in `xh.ts` + combat; **overlay omits** |
| Weighted `beliefHypotheses[]` | **Unshipped** (deferred Pass-4…6) |

Program residual (Pass-7 deepen **σ_belief / soft vision only**):

1. **Occupancy multi-hypothesis** — after soft asymptote, single Gaussian ≠ brush-exit / river / jungle modes; eval V15b tol `occ+450` still loose on content.  
2. **`hasBelief` ignores hypotheses** — API gap: hypotheses-only FoW must not fall into openLoop / god-eye.  
3. **Overlay margin plumbing** — Pass-6 KEEP intent incomplete: `resolveCastVisionSoft` returns `softVisionMarginNorm`, combat forwards it, `xhOverlay` does not → overlay σ_seen still softV-only.  

No BASE×ZONE×VISION. No god-eye (preserve null-geo + caster zone under openLoop). Do not re-litigate `u≤0.72` — use hypotheses instead.

---

## 1. Critique (concrete residuals)

### 1.1 Soft asymptote still one Gaussian (P0 — σ_belief content)

```931:957:src/engine/xh.ts
  function sigmaBeliefLkp(opts: {
    ageSec: number
    ...
  }): number {
    ...
    const sigmaOcc = occupancySigma(opts.zone ?? targetZone)
    const u = Math.min(0.72, a / T_SAT)
    if (reach <= sigmaOcc) return reach
    return reach * (1 - u) + sigmaOcc * u
  }
```

Pass-5–6 correctly refuse \(u\to 1\) runaway and refuse oracle zone under openLoop. Residual is **support shape**: FoW search after contact loss is typically multi-modal (brush pocket / river choke / jungle quadrant). Binary `beliefMeanSeen` only covers penumbra vs LKP — not occupancy exit modes. Prefer 2–3 weighted closed-form modes over fattening one Gaussian past `u≤0.72`.

### 1.2 `hasBelief` still LKP-only (P0 — no-god-eye contract)

```672:685:src/engine/xh.ts
  const fowDark = softV < 0.85 || vision === 'blind'
  const hasBelief = !!input.beliefMeanPosition
  ...
  const targetZone = openLoopBelief
    ? casterZone
    : zoneAt(geoPos ?? input.targetPosition)
```

Once `beliefHypotheses[]` lands, FoW with hypotheses-only (no single `beliefMeanPosition`) must count as belief — else `openLoopBelief` fires, `geoPos=undefined`, and zone collapses to caster even when callers supplied a multi-mode prior. That would be a **false openLoop** (belief present, treated as none). Wire `hasBelief` in the same KEEP slice as hypotheses.

Hard rule remains: blind without belief must not read oracle pose / oracle zone.

### 1.3 Overlay drops Pass-6 margin (P1 — softVision → σ_seen incomplete)

```81:90:src/engine/xhOverlay.ts
        const est = estimateXh({
          ...
          softVision: resolved.softVision,
          spottedByTarget: resolved.spottedByTarget,
        })
```

Combat already passes `softVisionMarginNorm: resolved?.softVisionMarginNorm`. Overlay does not. Same `resolveCastVisionSoft` → two σ_seen contracts. Plumbing only; do not change margin→σ_seen formula.

### 1.4 Out of scope / already closed

- Re-opening open-loop zone=caster, null-geo, `u≤0.72`, softV exponential, combat wards.  
- Historic hit-rate MLE / particle filters.  
- BASE×ZONE×VISION.  
- Editing production / eval in this agent.

---

## 2. Proposed minimal deepen (orchestrator → later)

**Scope:** `beliefHypotheses[]` pack path + `hasBelief` wire + overlay `softVisionMarginNorm`. No BASE×ZONE×VISION. Do not re-litigate Pass-1–6 KEEP shape.

### 2.1 `beliefHypotheses[]` occupancy modes (primary)

```ts
// XhEstimateInput additive:
beliefHypotheses?: {
  weight: number
  mean: MapPosition
  ageSec?: number
  sigmaBelief?: number
  zone?: MapZone
}[]

function dominantHypothesisMean(hs: NonNullable<XhEstimateInput['beliefHypotheses']>) {
  let best = hs[0]!
  for (const h of hs) if (h.weight > best.weight) best = h
  return best.mean
}

function pack(sigmaJuke: number) {
  if (input.beliefHypotheses?.length) {
    const hs = normalizeWeights(input.beliefHypotheses)
    let xH = 0
    let belief2 = 0
    for (const h of hs) {
      const muK = lateralMissAtMean(h.mean) // same ballisticSegmentMiss / CPA path as geoPos
      const sigB =
        h.sigmaBelief ??
        sigmaBeliefLkp({
          ageSec: h.ageSec ?? age,
          dashBudgetUu: dashReadyObs ? kitDash : 0,
          flashBudgetUu: flashBelief,
          brushCapUu: (h.zone ?? zoneAt(h.mean)) === 'brush' ? 280 : undefined,
          zone: h.zone ?? zoneAt(h.mean),
        })
      const sigK = Math.hypot(aim, juke, sigB, 12)
      xH += h.weight * corridorHitProb(R_hit, muK, sigK)
      belief2 += h.weight * sigB * sigB
    }
    return {
      xH: clamp01(xH),
      sigma: { aim, juke, belief: Math.sqrt(belief2), total: Math.hypot(aim, juke, Math.sqrt(belief2), 12) },
    }
  }
  // else: existing softV mix + beliefMeanSeen path — do not re-litigate
}
```

Prefer 2–3 modes when age ≥ T_SAT (e.g. brush 0.4 / river 0.35 / jungle 0.25) instead of fattening one Gaussian past `u≤0.72`.

### 2.2 `hasBelief` + geoPos (no false openLoop)

```ts
const hasBelief =
  !!input.beliefMeanPosition || !!(input.beliefHypotheses?.length)

if (fowDark && hasBelief) {
  geoPos =
    input.beliefMeanPosition ??
    dominantHypothesisMean(input.beliefHypotheses!)
} else if (fowDark && !hasBelief) {
  openLoopBelief = true
  geoPos = undefined
}
// targetZone: openLoop → casterZone (Pass-6 KEEP); else zoneAt(geoPos)
```

**Eval-safe:** fixtures that need brush Cap under blind must set LKP or a brush-weighted hypothesis. Default no-LKP / no-hypotheses must **not** get oracle brush Cap or lane-vs-brush σ_occ split.

### 2.3 Overlay margin plumbing (Pass-6 completion)

```ts
// xhOverlay.ts — additive only
softVision: resolved.softVision,
softVisionMarginNorm: resolved.softVisionMarginNorm,
spottedByTarget: resolved.spottedByTarget,
```

Preserve: softVision edge > dark; equal softV with deeper margin → lower σ_seen / higher xH (already V19 / Pass-6 assert).

### 2.4 Out of scope this pass

- Replacing `u≤0.72` with `u→1` (re-litigates Pass-5; use hypotheses).  
- Re-opening open-loop zone / null-geo / margin exponential form.  
- Historic MLE, particle filters, BASE×ZONE×VISION.  
- Editing production files in this agent.

---

## 3. New eval asserts (additive — do not soften 148)

```ts
// V20: multi-hypothesis ≤ equal-weight single fat mode (or ≤ equal-mean LKP)
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

// V21: hypotheses-only counts as belief (no false openLoop / no god-eye)
const hypOnly = estimateXh(base({
  vision: 'blind', softVision: 0, lastKnownAgeSec: 4,
  beliefMeanPosition: undefined,
  beliefHypotheses: [{ weight: 1, mean: near, zone: 'jungle' }],
}))
assert(
  'hypotheses-only is belief, not no_lkp openLoop',
  !hypOnly.factors.includes('belief:no_lkp_guard') &&
    hypOnly.distance != null,
)

// V22: overlay-contract margin (API path already in combat; assert estimateXh)
const deep = estimateXh(base({
  vision: 'mutual', softVision: 0.55, softVisionMarginNorm: 0.55,
  beliefMeanPosition: near,
}))
const shallow = estimateXh(base({
  vision: 'mutual', softVision: 0.55, softVisionMarginNorm: 0.05,
  beliefMeanPosition: near,
}))
assert(
  'Pass-7: deeper margin → lower σ_belief / higher xH',
  !!deep.sigma && !!shallow.sigma &&
    deep.sigma.belief <= shallow.sigma.belief + 1e-9 &&
    deep.xH >= shallow.xH - 1e-9,
)

// Preserve: no-LKP ≠ god-eye, open-loop zone=caster, ancient xH ≤ mid,
// ancient σ ≲ occ+tol, softVision edge>dark, spotted≤unspotted,
// ambush≥mutual, no BASE×ZONE×VISION.
```

---

## 4. arXiv / cites (Pass-7 focus)

| ID | Use |
|---|---|
| [2009.08922](https://arxiv.org/abs/2009.08922) | Multi-hypothesis beliefs under FoW |
| [1812.00054](https://arxiv.org/abs/1812.00054) | FoW state estimation; prior over regions not points |
| [2306.11301](https://arxiv.org/abs/2306.11301) | Reachable sets → occupancy / search priors |
| [2604.17811](https://arxiv.org/abs/2604.17811) | ∫L b — distinct hypothesis means |
| [2602.11373](https://arxiv.org/abs/2602.11373) | Full posterior — zone is state; no oracle under FoW |
| [2410.13587](https://arxiv.org/abs/2410.13587) | Sensor margin → measurement noise (overlay parity) |

---

## 5. Expected metric impact

| Change | Current 148 | After asserts |
|---|---|---|
| `beliefHypotheses[]` | Opt-in | Enables V20/V21 |
| `hasBelief` wire | Prevents false openLoop | Keeps no-god-eye |
| Overlay marginNorm | Contract parity | Enables V22; softV-only fallback unchanged |
| Legacy LKP + softV mix | Keep ordering | Stay 148/148 then 148+k/148+k |

**Primary score:** expect stay `148/148` after additive API; then `148+k/148+k` with V20/V21/V22.

---

## 6. Minimal patch plan (orchestrator)

1. **`beliefHypotheses[]`** pack path (Σ w_k Φ_corr) with per-mode `sigmaBeliefLkp` / zone / brush Cap.  
2. **`hasBelief`** ← LKP ∨ hypotheses; geoPos from dominant mean when LKP unset.  
3. **Overlay** forward `softVisionMarginNorm` (combat already does).  
4. Append V20, V21, V22 to `eval-xh-math.ts`.  

**Out of scope:** re-proposing null-geo / open-loop zone=caster / `u≤0.72` / combat wards / softV exp / margin form / mixture shell / spotted τ / √t-Flash-brush / beliefMeanSeen / aEff, BASE×ZONE×VISION, editing production files in this agent.

---

## 7. Decision

**KEEP_CANDIDATE**

Rationale: Pass-6 made zone honest under openLoop and wired Koopman margin into σ_seen. Pass-7 residual is **belief content under soft vision**: closed-form occupancy hypotheses after soft σ_occ saturation, wire `hasBelief` so hypotheses-only is not false openLoop, and finish overlay margin plumbing — still inside \(\sigma^2=\sigma_{\mathrm{aim}}^2+\sigma_{\mathrm{juke}}^2+\sigma_{\mathrm{belief}}^2\). No god-eye.

**SKIP** only if Pass-7 bandwidth must fix a failing geo/aim/strategy invariant; vision harness is green (148/148), but ancient support stays unimodal and overlay still discards sensor margin.

---

**One-line verdict:** KEEP_CANDIDATE — beliefHypotheses + hasBelief wire + overlay marginNorm; do not re-litigate open-loop zone / margin form / u≤0.72 / null-geo.
