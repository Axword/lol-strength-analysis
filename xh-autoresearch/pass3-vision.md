# Pass-3 VISION — σ_belief / soft-vision residual deepen

**Axis:** vision  
**Agent:** Pass-3 VISION  
**Against:** Post Pass-2 KEEP (`math_pass_rate=65/65`) — LKP geo mean, reachable-set `σ_belief`, `softVisionAt` + `resolveCastVisionSoft`, mixture-of-CDFs ∫L b  
**Constraint honored:** **no edits** to `xh.ts` / `vision.ts` / eval. Proposal only.  
**Do not re-propose:** LKP geo mean, reachable κ=1/√3, softVision mixture API, `softVisionAt`, `resolveCastVisionSoft`, mixture-of-CDFs (already KEEP).  
**Verdict:** **KEEP_CANDIDATE**

---

## 0. What Pass-1–2 fixed vs what remains

| Landed claim | Status @ Pass-3 |
|---|---|
| LKP geo via `beliefMeanPosition` when `softV<0.85` | **Shipped**; overlay/combat still omit LKP age/pos |
| Reachable-set `σ_belief` (`κ=1/√3`, dash expand) | **Shipped**; kernel shape + dash/Flash coupling still crude |
| SoftVision mixture-of-CDFs (not Var-mix) | **Shipped**; `μ_s=μ_ℓ` always — no multi-hypothesis means |
| `softVisionAt` + `resolveCastVisionSoft` | **Shipped**; combat path drops `wards`; V6–V9 never appended |
| `spottedByTarget` → `τ += 0.08` under blind | **Shipped**; **sign/semantics conflict** with intended POSG (see §1.4) |

Program residual: deepen **σ_belief / soft vision** only — aging kernel, dash-budget support, ward↔σ coupling, spotted reaction vs belief, brush prior, multi-hypothesis LKP.

---

## 1. Critique (concrete residuals)

### 1.1 Aging kernel is pure ballistic-linear (P0 residual)

```591:597:src/engine/xh.ts
  function sigmaBeliefLkp(ageSec: number, dashBudgetUu: number): number {
    const a = Math.max(0, ageSec)
    const kappa = 1 / Math.sqrt(3)
    const Rmax = ms * a + dashBudgetUu * Math.min(1, a / 0.5)
    const sig = Math.hypot(35, kappa * Rmax)
    return Math.min(sig, Math.max(35, Rmax))
  }
```

Support radius \(R_{\max}=v\Delta t\) is correct for **fixed unknown heading** (uniform disk → 1D SD \(R/\sqrt{3}\)). Residual errors:

1. **No heading-diffusion / √t term.** After LKP, players change direction; Brownian / Ornstein–Uhlenbeck heading noise grows as \(\sigma_\perp\sim\sqrt{D_h\,\Delta t}\), not only \(v\Delta t\). Pure linear overstates short-age smear relative to mid-age path entropy (and understates late branching).
2. **No terrain / wall truncation.** Reachable set is an open disk; river walls and base gates truncate support — isotropic Gaussian still puts mass through walls.
3. **No rediscovery / map-prior saturation.** Age→30 still expands as \(v\cdot 30\); only the hit CDF + `ancient` eval bound keep xH low. A proper lost-contact prior eventually mixes toward a **zone occupancy** prior (jungle quadrant, not infinite disk).

Minimal deepen (shape only — keep κ and floor 35):

\[
R_{\mathrm{walk}}=v\Delta t,\quad
\sigma_{\sqrt{}}=\kappa_{\sqrt{}}\sqrt{\Delta t},\quad
R_{\max}=R_{\mathrm{walk}}+R_{\mathrm{dash}},\quad
\sigma_{\mathrm{lost}}=\min\!\big(\hypot(35,\kappa R_{\max},\sigma_{\sqrt{}}),\,R_{\max}\big).
\]

Preserve monotone `stale < fresh` by keeping the walk term dominant for \(\Delta t\gtrsim 1\).

### 1.2 Dash-budget in reachable set double-duties with σ_juke (P1)

Current: `dashBudgetUu * Math.min(1, a/0.5)` with **same** `dashReadyObs` that feeds `σ_juke`.

| Issue | Why |
|---|---|
| **Belief dash ≠ dodge dash** | Reachable-set dash expands *where they might be* while dark; juke dash is *reaction-window* displacement after cast. Same binary readiness couples FoW support to post-telegraph dodge. |
| **Flash absent from \(R_{\max}\)** | Flash is in worst/typical juke only. A 2s-dark target can have Flashed; belief support should optionally include `flashBudgetUu` when `flashReady` / prior says up — else LKP disk is too tight under Flash-up priors. |
| **0.5s full-ramp is vibe** | Dash is near-instant; better: step `1_{age≥t_cast}` or `min(1, age/t_dash)` with \(t_{\mathrm{dash}}\approx 0.15\), not 0.5s linear. |
| **Soft mix double-count risk** | Under `softV∈(0,1)`, lost component has dash-inflated `σ_lost` **and** both CDF arms carry dash in `σ_juke`. Prefer: belief dash only in `σ_lost`; keep juke dash as reaction-only (already mostly true) — document the split so future Flash-in-belief does not stack again. |

Sketch:

```ts
// Belief support only — do NOT reuse dodgeWindow scaling.
const dashBelief = dashReadyObs ? kitDash : 0
const flashBelief =
  softV < 0.5 && (flashReadyObs === true || flashCdUnknown)
    ? (flashReadyObs === true ? 400 : 400 * (input.flashUpPrior ?? 0.35))
    : 0
const Rmax =
  ms * a +
  dashBelief * (a >= 0.12 ? 1 : a / 0.12) +
  flashBelief * (a >= 0.2 ? 1 : 0)
```

### 1.3 Ward / vision-radius ↔ σ_seen decoupling (P1)

`softVisionAt` correctly soft-margins with champ/ward radii, but `estimateXh` locks:

```ts
const sigmaSeen = 25  // constant
```

and mixes only via Bernoulli weight \(v=\texttt{softVision}\). Residuals:

1. **Depth-in-disk ignored.** Target deep inside a ward (\(v\approx 1\), large positive margin) vs barely inside (\(v\approx 0.6\)) share the same `σ_seen=25`. Sensor noise should shrink with margin / rise near the penumbra (range-dependent detection; Koopman lateral-range).
2. **Combat drops wards.** `meanXhVsEnemies` calls `resolveCastVisionSoft` **without** `wards` — softVision stays champ-disk-only in combat while overlay passes wards. Same fight, two FoW contracts.
3. **Radius meta unused in belief.** `meta.vision.wardSightRadiusNorm` / champ sight affect \(v\) only; never scale `σ_seen`. Control wards / pix / sweeper radius changes should tighten measurement when \(v\) high.

Minimal coupling (no new fog scalar stack — fold into mixture components):

```ts
// marginNorm ≈ soft-logit inverse; or pass softVision + optional visionMargin
const sigmaSeen = Math.hypot(
  18,
  40 * Math.exp(-3 * softV), // penumbra → larger meas. noise
)
```

Or, better API later: `softVisionAt` returns `{ v, bestMarginNorm }` and

\(\sigma_{\mathrm{seen}}=\hypot(18,\,\sigma_0 e^{-\beta\cdot\mathrm{margin}/r})\).

### 1.4 `spottedByTarget` reaction sign vs belief (P0 semantics)

```488:489:src/engine/xh.ts
  let tau = reactionSec(vision)
  if (input.spottedByTarget && vision === 'blind') tau += 0.08
```

POSG intent (`opponent_only` on **caster**): you are dark on them, **they see your cast telegraph** → defender should dodge **better** → **lower** caster xH.

But `dodgeWindow = T_windup + t_go - τ`. **Increasing** `τ` *shrinks* the dodge window → *decreases* `σ_juke` → *raises* xH. Pass-2 V6 asserted the opposite direction (`spotted ≤ unspotted`) and never landed in eval — current code would **fail** that assert.

Also: spotted only touches `τ`; `σ_belief` / soft mix unchanged. Correct split:

| Channel | Spotted (opponent sees caster) | Unspotted blind |
|---|---|---|
| Belief \(b\) | unchanged (you still don't see them) | lost LKP |
| Dodge | **more** juke / **smaller** `τ` (they react to telegraph) | less juke (they may not know cast) |

Minimal fix:

```ts
// They see the cast → react sooner (smaller τ), not later.
if (input.spottedByTarget && vision === 'blind') tau = Math.max(0.08, tau - 0.06)
```

Do **not** shrink `σ_belief` when spotted — that would reintroduce “fog knobs” collapsing posterior because the *enemy* has info.

### 1.5 Brush prior is zone-scale only (P1)

```392:395:src/engine/xh.ts
    case 'brush':
      return 1.12
```

`zScale` multiplies **aim and juke** only; `σ_seen` / `σ_lost` unscaled. Soft brush gate in `softVisionAt` is good for *sensors*, but belief still treats brush LKP as an open disk:

- Mass should concentrate on the **brush blob** (multi-cell occupancy prior), not isotropic walk into river.
- Soft ward *does* light brush (matches hard + live LoL); champ soft correctly requires ally-in-brush. Residual: when LKP is brush and `softV=0`, prefer a **truncated reachable set** (brush union + exits) over full \(v\Delta t\) disk.

Minimal: if `zoneAt(geoPos)==='brush'`, cap walk smear by brush characteristic radius (~0.05–0.08 norm → ~few hundred uu) until age forces an exit hypothesis:

```ts
const brushCap = targetZone === 'brush' ? 280 : Infinity
const Rmax = Math.min(brushCap + ms * Math.max(0, a - 1.5), ms * a + dashTerm)
```

(exit after ~1.5s dark — auditable constant).

### 1.6 Multi-hypothesis LKP still single-mean (P1)

Mixture-of-CDFs is honest for \(b=v\mathcal N(\mu_s,\sigma_s^2)+(1-v)\mathcal N(\mu_\ell,\sigma_\ell^2)\), but code forces **`μ_s = μ_ℓ = μ_bias(geoPos)`**:

```616:618:src/engine/xh.ts
    const xH =
      softV * corridorHitProb(R_hit, muBias, sigS) +
      (1 - softV) * corridorHitProb(R_hit, muBias, sigL)
```

Residuals vs arXiv:2604.17811 / POSG particle beliefs:

1. Penumbra should aim seen-component near **live measurement** and lost-component near **LKP** — between-component gap \(v(1-v)(\mu_s-\mu_\ell)^2\) is exactly what Var-mix missed and mixture-of-CDFs can capture **only if means differ**.
2. No path hypotheses (river vs jungle exit, scrub vs pixel brush). Need optional `beliefHypotheses?: { weight; mean; ageSec }[]` with \(\sum w=1\), still closed-form:

\[
xH=\sum_k w_k\,\Phi_{\mathrm{corr}}(R;\mu_k^\perp,\sigma_{\mathrm{tot},k}).
\]

3. Overlay/combat never pass `beliefMeanPosition` / `lastKnownAgeSec` — multi-hypothesis is blocked until single-LKP scrubber exists; still specify the API so Pass-3 doesn’t paint into a corner.

### 1.7 Product-path residue (wiring, not re-propose soft API)

Already wired: softVision + spotted flags on overlay; combat soft resolver **sans wards**. Still missing: LKP scrubber → `beliefMeanPosition` + `lastKnownAgeSec`. Blind defaults still aim oracle pose when LKP unset — eval-safe legacy, but FoW xH in product remains god-eye mean.

---

## 2. Proposed minimal deepen (orchestrator → `xh.ts` / `vision.ts` later)

**Scope:** σ_belief kernel + spotted τ sign + soft meas. noise + optional multi-mean mix. No BASE×ZONE×VISION. Blind must not treat true pose as known without belief spread (keep geoPos rule).

### 2.1 Aging kernel + dash/Flash belief split

```ts
function sigmaBeliefLkp(opts: {
  ms: number
  ageSec: number
  dashBudgetUu: number
  flashBudgetUu?: number
  brushCapUu?: number
}): number {
  const a = Math.max(0, opts.ageSec)
  const kappa = 1 / Math.sqrt(3)
  const dash = opts.dashBudgetUu * (a >= 0.12 ? 1 : a / 0.12)
  const flash = (opts.flashBudgetUu ?? 0) * (a >= 0.2 ? 1 : 0)
  let Rmax = opts.ms * a + dash + flash
  if (opts.brushCapUu != null) {
    // Stay-in-brush prior, then allow exit smear
    Rmax = Math.min(Rmax, opts.brushCapUu + opts.ms * Math.max(0, a - 1.5))
  }
  const sigSqrt = 55 * Math.sqrt(a) // heading diffusion (uu); keep modest vs walk
  const sig = Math.hypot(35, kappa * Rmax, sigSqrt)
  return Math.min(sig, Math.max(35, Rmax))
}
```

### 2.2 Soft radius → σ_seen

```ts
const sigmaSeen = Math.hypot(18, 55 * Math.exp(-2.8 * softV))
```

### 2.3 Spotted τ (correct POSG direction)

```ts
if (input.spottedByTarget && vision === 'blind') {
  tau = Math.max(0.08, tau - 0.06) // telegraph → earlier dodge
}
```

### 2.4 Multi-mean mixture (optional fields; backward compatible)

```ts
// XhEstimateInput additive:
// beliefMeanSeen?: MapPosition  // soft/live component mean
// beliefHypotheses?: { weight: number; mean: MapPosition; sigmaBelief?: number }[]

// In pack(), if beliefHypotheses?.length:
//   xH = Σ w_k corridorHitProb(R, mu_k, hypot(aim,juke,σ_k,12))
// else if beliefMeanSeen && softV in (0,1):
//   muS = lead residual at beliefMeanSeen; muL at geoPos (LKP)
//   xH = softV * Φ(muS,sigS) + (1-softV) * Φ(muL,sigL)
// else: equal-mean mix (current)
```

### 2.5 Vision bridge: pass wards on combat; optional margin

```ts
// combat meanXhVsEnemies — thread wards when available
resolveCastVisionSoft({ ..., wards: input.wards ?? [] })
```

`softVisionAt` can later return margin for σ_seen; not required for first KEEP if exponential-in-`softV` proxy lands.

---

## 3. New eval asserts (additive — do not soften 65)

```ts
// V6: spottedByTarget lowers blind xH (telegraph → more dodge)
const blindDark = estimateXh(base({
  vision: 'blind', lastKnownAgeSec: 1, spottedByTarget: false, dashReady: true,
}))
const blindLit = estimateXh(base({
  vision: 'blind', lastKnownAgeSec: 1, spottedByTarget: true, dashReady: true,
}))
assert('spotted blind ≤ unspotted blind', blindLit.xH <= blindDark.xH + 1e-9)

// V10: aging kernel — mid-age σ_belief grows sub-ballistic vs pure linear proxy
// (expose sigma.belief or factor); fresh < mid < ancient monotone in σ or 1/xH
const a1 = estimateXh(base({ vision: 'blind', lastKnownAgeSec: 1 }))
const a4 = estimateXh(base({ vision: 'blind', lastKnownAgeSec: 4 }))
const a16 = estimateXh(base({ vision: 'blind', lastKnownAgeSec: 16 }))
assert('belief age monotone xH', a16.xH <= a4.xH + 1e-9 && a4.xH <= a1.xH + 1e-9)
// Optional: a4.sigma.belief < ms*4/√3 + dash + tol  (√t does not explode past walk)

// V11: Flash-up expands blind belief support (lower xH) vs Flash-down same age
const flashUp = estimateXh(base({
  vision: 'blind', lastKnownAgeSec: 2, flashReady: true, dashReady: false,
}))
const flashDown = estimateXh(base({
  vision: 'blind', lastKnownAgeSec: 2, flashReady: false, dashReady: false,
}))
assert('Flash-up blind ≤ Flash-down blind', flashUp.xH <= flashDown.xH + 1e-9)

// V12: softVision penumbra σ_seen — softV=0.9 xH ≥ softV=0.5 at same age (meas. tighter)
const deep = estimateXh(base({ vision: 'blind', softVision: 0.9, lastKnownAgeSec: 2 }))
const pen = estimateXh(base({ vision: 'blind', softVision: 0.5, lastKnownAgeSec: 2 }))
assert('deep soft ≥ penumbra soft', deep.xH >= pen.xH - 1e-9)

// V13: multi-mean — displaced beliefMeanSeen vs LKP lowers mix vs equal-mean same softV
// (only after beliefMeanSeen API lands)

// V14: softVisionAt continuous at ward edge (vision.ts unit — not xH)
```

Preserve: stale\<fresh, belief-aim off LKP, softVision edge\>dark, ancient finite, ambush≥mutual, no BASE×ZONE×VISION.

---

## 4. arXiv / cites (Pass-3 focus)

| ID | Use |
|---|---|
| [2604.17811](https://arxiv.org/abs/2604.17811) | \(\int L\,b\) with **distinct** component means; multi-hypothesis mix |
| [2602.11373](https://arxiv.org/abs/2602.11373) | Full posterior; don’t collapse \(b\) when opponent is informed |
| [2306.11301](https://arxiv.org/abs/2306.11301) | Sparse-detection reachable sets / adversarial search |
| [2410.13587](https://arxiv.org/abs/2410.13587) | Noisy sensors → range-dependent measurement noise |
| [2405.18703](https://arxiv.org/abs/2405.18703) | POSG info sets — spotted ≠ thinner belief |
| [1812.00054](https://arxiv.org/abs/1812.00054) | FoW as state estimation + dynamics (√t / process noise) |
| Koopman 1956 | Soft detection effort; penumbra ↔ σ_meas |
| [2009.08922](https://arxiv.org/abs/2009.08922) | Approximate multi-hypothesis beliefs under FoW |

---

## 5. Expected metric impact

| Change | Current 65 | After asserts |
|---|---|---|
| Spotted τ sign flip | May change blind+spotted xH ordering | Enables V6 (would fail today) |
| √t + brush cap + Flash-in-belief | Should preserve stale\<fresh if walk dominates | Enables V10–V11 |
| σ_seen(softV) | Soft edge may rise slightly vs Pass-2 | Enables V12; keep V3 |
| Multi-mean optional | No change if unset | Enables V13 later |
| Legacy (no new fields) | Keep ordering | Stay 65/65 then 65+k |

**Primary score:** expect stay `65/65` until V6/V10–V12 land; then `65+k/65+k`.

---

## 6. Minimal patch plan (orchestrator)

1. Fix spotted `τ` **sign** (`−0.06`, floor 0.08) — highest-value one-liner; unlocks V6.
2. `sigmaBeliefLkp`: add modest √t term; dash step ~0.12s; optional Flash belief budget; brush cap when `targetZone==='brush'`.
3. `sigmaSeen = hypot(18, 55·e^{−2.8 softV})` — ward-radius coupling proxy without new inputs.
4. Thread `wards` into combat `resolveCastVisionSoft`.
5. Optional API: `beliefMeanSeen` / `beliefHypotheses` for multi-mean mix (equal-mean fallback).
6. Append V6, V10–V12 to `eval-xh-math.ts` after (1)–(3).

**Out of scope:** historic hit-rate MLE, particle filters, editing files in this agent, re-proposing softVisionAt / mixture-of-CDFs / LKP geo mean.

---

## 7. Decision

**KEEP_CANDIDATE**

Rationale: Pass-1–2 made belief *exist* (reachable σ, soft sensors, honest ∫L b). Pass-3 residuals are kernel **shape** (√t + brush truncate), **support budgets** (dash timing / Flash-in-belief), **sensor→σ_seen** coupling, **POSG spotted τ sign**, and **multi-mean** hypotheses — all minimal, eval-additive, and still inside `σ²=σ_aim²+σ_juke²+σ_belief²` without god-eye blind or BASE×ZONE×VISION.

**SKIP** only if Pass-3 bandwidth must fix a failing geo/aim invariant; vision harness is green, but spotted semantics are currently inverted relative to the intended POSG assert.

---

**One-line verdict:** KEEP_CANDIDATE — fix spotted τ sign, add √t/brush/Flash belief support + softV→σ_seen, then multi-mean LKP; do not re-litigate mixture-of-CDFs.
