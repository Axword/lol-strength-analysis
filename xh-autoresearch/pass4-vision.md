# Pass-4 VISION — multi-mean LKP · ward plumbing · occupancy saturation

**Axis:** vision  
**Agent:** Pass-4 VISION  
**Against:** Post Pass-3 KEEP (`math_pass_rate=88/88`) — mixture-of-CDFs ∫L b, spotted τ fix, √t + Flash-in-belief + brush cap, softVision→σ_seen  
**Constraint honored:** **no edits** to `xh.ts` / `vision.ts` / combat / eval. Proposal only.  
**Do not re-propose:** LKP geo mean API, κ=1/√3, softVisionAt / resolveCastVisionSoft, mixture-of-CDFs shell, spotted τ sign, √t / Flash-belief / brush cap, softV→σ_seen exponential.  
**Verdict:** **KEEP_CANDIDATE**

---

## 0. What Pass-1–3 fixed vs what remains

| Landed claim | Status @ Pass-4 |
|---|---|
| Reachable-set `σ_belief` + √t + Flash budget + brush cap | **Shipped** in `sigmaBeliefLkp` |
| SoftVision mixture-of-CDFs (not Var-mix) | **Shipped**; **`μ_s = μ_ℓ = μ_bias(geoPos)` always** |
| `softVisionAt` + `resolveCastVisionSoft` | **Shipped**; overlay passes `wards`; **combat omits wards** |
| Spotted τ **decreases** under blind (POSG) | **Shipped** + eval assert |
| `softVision → σ_seen` penumbra | **Shipped** via `hypot(18, 55·e^{−2.8 softV})` |
| `beliefMeanPosition` / `lastKnownAgeSec` | **API only**; overlay/combat never scrub LKP — **blind still aims oracle pose** when LKP unset |

Program residual (Pass-4 deepen **σ_belief / soft vision only**):

1. **Multi-mean** mixture (seen vs LKP / exit hypotheses).  
2. **Ward plumbing** in combat (+ optional margin→σ_seen).  
3. **Occupancy prior saturation** (ancient age → zone prior, not \(v\cdot 30\) disk).  
4. **God-eye guard:** blind must not treat true pose as known without belief.

No BASE×ZONE×VISION. Zone scale on aim/juke may stay; do not resurrect fog hit-rate scalars.

---

## 1. Critique (concrete residuals)

### 1.1 Multi-mean still single-mean (P0 residual)

Mixture-of-CDFs is honest for

\[
b = v\,\mathcal N(\mu_s,\sigma_s^2)+(1-v)\,\mathcal N(\mu_\ell,\sigma_\ell^2),
\]

but `pack()` forces shared lateral mean:

```790:792:src/engine/xh.ts
    const xH =
      softV * corridorHitProb(R_hit, muBias, sigS) +
      (1 - softV) * corridorHitProb(R_hit, muBias, sigL)
```

`muBias` is computed once from `geoPos` (LKP if provided else **oracle**). Residuals vs arXiv:2604.17811:

1. Penumbra should aim **seen** near live measurement and **lost** near LKP — between-component gap \(v(1-v)(\mu_s-\mu_\ell)^2\) is exactly what Var-mix missed and mixture-of-CDFs can capture **only if means differ**.
2. No exit / occupancy modes (brush exit vs river, jungle quadrant). Need optional weighted hypotheses still closed-form:

\[
xH=\sum_k w_k\,\Phi_{\mathrm{corr}}(R;\mu_k^\perp,\sigma_{\mathrm{tot},k}).
\]

3. Without multi-mean, softVision only blends σ widths — underestimates miss when live pose and LKP disagree.

### 1.2 Blind god-eye mean when LKP unset (P0 — program hard rule)

```539:543:src/engine/xh.ts
  const geoPos =
    softV < 0.85 && input.beliefMeanPosition
      ? input.beliefMeanPosition
      : input.targetPosition
```

Hard rule: *Blind casts must not treat true position as known without belief spread.*

Today: if callers omit `beliefMeanPosition` (combat + overlay always do), FoW casts still lock distance / `t_go` / `muBias` / in-range to **oracle** `targetPosition`, then smear with `σ_lost`. That is belief **spread without belief mean** — still god-eye.

Product paths:

```203:209:src/engine/combat.ts
        ? resolveCastVisionSoft({
            casterPosition: caster.position,
            targetPosition: enemy.position,
            casterTeam,
            targetTeam: casterTeam === 'blue' ? 'red' : 'blue',
            units: visionUnits,
          })
```

No `wards`, no LKP age/pos. Overlay passes wards + softVision but still oracle `targetPosition` only.

### 1.3 Combat ward plumbing (P1)

`softVisionAt` correctly soft-margins champ **and** ward radii, but combat `resolveCastVisionSoft` never receives `wards` → softVision is champ-disk-only in fight math while overlay includes wards. Same fight, two FoW contracts.

Also: `σ_seen` uses softV only; `softVisionAt` already computes per-sensor **margin** but discards it. Margin→σ_seen (Koopman) is a small deepen once the return type carries `bestMarginNorm`.

### 1.4 Occupancy prior saturation (P1)

Even with √t + brush cap, ancient age still grows with walk term:

\[
R_{\max}\approx v\Delta t + \mathrm{dash} + \mathrm{flash}.
\]

At `age=30`, support is map-scale; only `clamp01` + eval “ancient finite” keep xH low. A proper lost-contact prior **saturates** toward a **zone occupancy** prior (jungle quadrant / river band / brush blob), not an infinite disk:

\[
\sigma_{\mathrm{lost}}(\Delta t)
  \xrightarrow{\Delta t\to\infty}
  \sigma_{\mathrm{occ}}(\mathrm{zone}),
\quad
\sigma_{\mathrm{occ}}\ll v\cdot 30.
\]

Minimal: blend reachable kernel toward zone prior after \(T_{\mathrm{sat}}\):

\[
\sigma_{\ell}
  =\mathrm{sat}\big(\sigma_{\mathrm{reach}}(\Delta t),\,\sigma_{\mathrm{occ}},\,\Delta t/T_{\mathrm{sat}}\big).
\]

Optional: when saturated, split mass into 2–3 occupancy modes (same multi-hypothesis API as §1.1) instead of one fat Gaussian.

### 1.5 Product scrubber still missing (wiring, not re-propose soft API)

Still no LKP scrubber → `beliefMeanPosition` + `lastKnownAgeSec` from timeline FoW transitions. Multi-mean and god-eye guard are blocked in product until scrubber exists; Pass-4 must still specify engine API + eval so KEEP does not paint into a corner.

---

## 2. Proposed minimal deepen (orchestrator → later)

**Scope:** multi-mean mix + occupancy saturation + god-eye guard + combat wards (+ optional margin). No BASE×ZONE×VISION. Blind without belief must not lock μ to oracle.

### 2.1 Multi-mean / multi-hypothesis mixture

```ts
// XhEstimateInput additive (backward compatible):
// beliefMeanSeen?: MapPosition   // soft/live component mean
// beliefHypotheses?: {
//   weight: number
//   mean: MapPosition
//   ageSec?: number
//   sigmaBelief?: number
// }[]

function pack(...) {
  if (input.beliefHypotheses?.length) {
    const hs = normalizeWeights(input.beliefHypotheses)
    let xH = 0
    for (const h of hs) {
      const muK = lateralMissAtMean(h.mean) // same ballisticRayMiss path as geoPos
      const sigK = Math.hypot(
        aim, juke,
        h.sigmaBelief ?? sigmaBeliefLkp({ ageSec: h.ageSec ?? age, ... }),
        12,
      )
      xH += h.weight * corridorHitProb(R_hit, muK, sigK)
    }
    return { xH: clamp01(xH), sigma: ... }
  }
  if (input.beliefMeanSeen && softV > 0 && softV < 1) {
    const muS = lateralMissAtMean(input.beliefMeanSeen)
    const muL = lateralMissAtMean(geoPos) // LKP / belief mean
    return {
      xH: clamp01(
        softV * corridorHitProb(R_hit, muS, sigS) +
          (1 - softV) * corridorHitProb(R_hit, muL, sigL),
      ),
      ...
    }
  }
  // else: equal-mean mix (current Pass-3)
}
```

### 2.2 God-eye guard (belief mean required under FoW)

```ts
const fowDark = softV < 0.85 || vision === 'blind'
const hasBelief = !!input.beliefMeanPosition || !!input.beliefHypotheses?.length

let geoPos = input.targetPosition
if (fowDark && hasBelief) {
  geoPos = input.beliefMeanPosition ?? dominantHypothesisMean(input.beliefHypotheses!)
} else if (fowDark && !hasBelief) {
  // Do NOT lock μ / range to oracle. Aim open-loop at last-known-unknown:
  // isotropic mean miss + saturated occupancy σ (eval may pass synthetic LKP).
  factors.push('belief:no_lkp_guard')
  // Option A (minimal): inflate σ_lost floor to σ_occ and zero lead (muBias from
  //   isotropic prior, ignore targetPosition for μ — still may use for tests via
  //   explicit beliefMeanPosition === targetPosition).
  // Option B: require callers to set beliefMeanPosition; estimateXh treats missing
  //   LKP under FoW as geoPos = caster+range*LOS guess with σ_occ only.
}
```

**Eval-safe contract:** fixtures that intend oracle+age must set `beliefMeanPosition: targetPosition` explicitly. Default blind-without-LKP must **not** silently god-eye.

### 2.3 Occupancy saturation in `sigmaBeliefLkp`

```ts
function sigmaBeliefLkp(opts: {
  ageSec: number
  dashBudgetUu: number
  flashBudgetUu?: number
  brushCapUu?: number
  zone?: MapZone
}): number {
  const reach = /* existing √t + dash/Flash + brush Cap path — do not re-litigate */
  const sigmaOcc = occupancySigma(opts.zone ?? 'unknown') // e.g. jungle 420, river 380,
  // brush 280, lane 520, pit 300, base 240, unknown 480
  const T_SAT = 8 // seconds to full occupancy mix
  const a = Math.max(0, opts.ageSec)
  const u = Math.min(1, a / T_SAT)
  // Approach occ from below without breaking fresh < mid < ancient monotone in 1/xH:
  // use harmonic-style saturate: once reach > occ, blend toward occ.
  if (reach <= sigmaOcc) return reach
  return reach * (1 - u) + sigmaOcc * u
}

function occupancySigma(zone: MapZone): number {
  switch (zone) {
    case 'brush': return 280
    case 'pit': return 300
    case 'river': return 380
    case 'jungle': return 420
    case 'base': return 240
    case 'lane': return 520
    default: return 480
  }
}
```

Preserve: `age=1` σ < `age=4` σ on typical MS (walk still dominates before \(T_{\mathrm{sat}}\)); `age=30` σ ≲ σ_occ + tol (not \(v\cdot 30\)).

### 2.4 Combat wards + optional margin

```ts
// combat meanXhVsEnemies — thread wards when available on fight input
resolveCastVisionSoft({ ..., wards: input.wards ?? [], meta: input.terrain })

// vision.ts later (optional KEEP slice):
export function softVisionAt(...): { v: number; bestMarginNorm: number }
// σ_seen = hypot(18, σ0 * exp(-β * margin / r_sensor))  — replace softV proxy when margin present
```

First KEEP can ship combat `wards` alone; margin API is additive.

---

## 3. New eval asserts (additive — do not soften 88)

```ts
// V13: multi-mean — displaced beliefMeanSeen vs LKP lowers mix vs equal-mean same softV
const equal = estimateXh(base({
  vision: 'blind', softVision: 0.5, lastKnownAgeSec: 2,
  beliefMeanPosition: near,
}))
const split = estimateXh(base({
  vision: 'blind', softVision: 0.5, lastKnownAgeSec: 2,
  beliefMeanPosition: near,
  beliefMeanSeen: { x: near.x + 0.05, y: near.y },
}))
assert('multi-mean split ≤ equal-mean', split.xH <= equal.xH + 1e-9)

// V15: occupancy saturation — ancient σ_belief ≲ σ_occ (expose sigma.belief)
const a4 = estimateXh(base({
  vision: 'blind', lastKnownAgeSec: 4, beliefMeanPosition: near, softVision: 0,
}))
const a30 = estimateXh(base({
  vision: 'blind', lastKnownAgeSec: 30, beliefMeanPosition: near, softVision: 0,
}))
assert('ancient xH ≤ mid-age xH', a30.xH <= a4.xH + 1e-9)
assert(
  'ancient belief not ballistic runaway',
  !!a30.sigma && a30.sigma.belief < 335 * 30 / Math.sqrt(3) * 0.5,
  `σb=${a30.sigma?.belief.toFixed(0)}`,
)

// V16: god-eye guard — FoW without LKP must not match oracle-aim same age
const oracleAim = estimateXh(base({
  vision: 'blind', lastKnownAgeSec: 2, softVision: 0,
  beliefMeanPosition: near, // explicit: “I believe the truth”
}))
const noLkp = estimateXh(base({
  vision: 'blind', lastKnownAgeSec: 2, softVision: 0,
  // beliefMeanPosition unset → guard path
}))
assert('no-LKP FoW ≠ silent god-eye', Math.abs(noLkp.xH - oracleAim.xH) > 0.02
  || noLkp.factors.includes('belief:no_lkp_guard'))

// V17: combat ward contract (integration / vision unit) — softVisionAt with ward
// at edge > softVisionAt without ward (vision.ts); document combat must pass wards

// Preserve: stale<fresh, belief-aim off LKP, softVision edge>dark, ancient finite,
// spotted≤unspotted, ambush≥mutual, no BASE×ZONE×VISION.
```

Update existing blind fixtures that relied on implicit oracle mean to set `beliefMeanPosition: targetPosition` so Pass-1/3 ordering stays green.

---

## 4. arXiv / cites (Pass-4 focus)

| ID | Use |
|---|---|
| [2604.17811](https://arxiv.org/abs/2604.17811) | \(\int L\,b\) with **distinct** component means |
| [2602.11373](https://arxiv.org/abs/2602.11373) | Full posterior; no oracle mean under FoW |
| [2009.08922](https://arxiv.org/abs/2009.08922) | Multi-hypothesis beliefs under FoW |
| [2306.11301](https://arxiv.org/abs/2306.11301) | Reachable sets → occupancy / search priors |
| [1812.00054](https://arxiv.org/abs/1812.00054) | FoW state estimation; prior saturation |
| [2410.13587](https://arxiv.org/abs/2410.13587) | Sensor margin → measurement noise |
| Koopman 1956 | Soft detection; ward margin ↔ σ_meas |

---

## 5. Expected metric impact

| Change | Current 88 | After asserts |
|---|---|---|
| Multi-mean optional | No change if unset | Enables V13 |
| Occupancy sat | Ancient xH may rise slightly vs pure walk (still low) | Enables V15; keep ancient finite |
| God-eye guard | May change default blind-without-LKP | Requires fixture `beliefMeanPosition` updates; enables V16 |
| Combat wards | Product-only; eval unchanged unless unit test | V17 optional |
| Legacy equal-mean + explicit LKP | Keep ordering | Stay 88/88 then 88+k/88+k |

**Primary score:** expect stay `88/88` after fixture LKP annotations; then `88+k/88+k` with V13/V15/V16.

---

## 6. Minimal patch plan (orchestrator)

1. **God-eye guard** — FoW without `beliefMeanPosition` / hypotheses must not aim oracle; annotate eval fixtures with explicit LKP.  
2. **Occupancy saturation** in `sigmaBeliefLkp` (zone σ_occ + \(T_{\mathrm{sat}}\approx 8\)).  
3. **Multi-mean API** — `beliefMeanSeen` + optional `beliefHypotheses`; equal-mean fallback.  
4. Thread **`wards` (+ meta)** into combat `resolveCastVisionSoft`.  
5. Optional: `softVisionAt` → `{ v, bestMarginNorm }` for σ_seen.  
6. Append V13, V15–V16 (V17) to `eval-xh-math.ts` after (1)–(3).

**Out of scope:** historic hit-rate MLE, particle filters, re-proposing softVisionAt / mixture-of-CDFs shell / spotted τ / √t-Flash-brush / softV→σ_seen, BASE×ZONE×VISION, editing production files in this agent.

---

## 7. Decision

**KEEP_CANDIDATE**

Rationale: Pass-3 made belief *shape* honest (√t, Flash support, brush cap, σ_seen, spotted τ). Pass-4 residuals are **belief content**: multi-mean ∫L b, occupancy saturation instead of ballistic runaway, combat ward parity, and the program hard rule that blind without LKP must not god-eye the true pose — all still inside \(\sigma^2=\sigma_{\mathrm{aim}}^2+\sigma_{\mathrm{juke}}^2+\sigma_{\mathrm{belief}}^2\).

**SKIP** only if Pass-4 bandwidth must fix a failing geo/aim/strategy invariant; vision harness is green (88/88), but product FoW still aims oracle and equal-mean soft mix leaves the ∫L b residue.

---

**One-line verdict:** KEEP_CANDIDATE — multi-mean LKP + occupancy sat + god-eye guard + combat wards; do not re-litigate √t/Flash/brush/σ_seen/spotted τ.
