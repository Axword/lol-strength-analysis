# Pass-10 EMPIRICS (FINAL) — cond-ICI / CvM-PIT / pinball / near-miss-ρ / mid-twCRPS

**Verdict: KEEP_CANDIDATE**

Proposal only — **do not** edit `src/engine/xh.ts`, and do not soften Pass-2…9
kill thresholds (`corridorRateTol=0.03`, `brierVsCoinMaxRatio=1.15`,
`abilityResidualTol=0.08`, `minBrierGainToKill=0.01`,
`calibrationMinBrierGain=0.005`, `rhoAbsErrTol=0.05`, `eceTol=0.025`,
`logLossVsCoinMaxRatio=1.2`, `sigmaScaleRelTol=0.08`,
`sigmaScaleMinBrierGain=0.005`, `mceTol=0.06`, `varRelTol=0.08`,
`crpsWrongRhoMinGain=0.02`, `pitEceTol=0.04`, `murphyRelTol=0.02`,
`murphyMinRes=0.01`, `countLogLossWrongRhoMinGain=0.02`,
`countBinEceTol=0.05`, `tripleRhoAbsErrTol=0.08`,
`conditionalEceTol=0.04`, `pitKsTol=0.05`, `murphyIdentityTol=1e-9`,
`bssMinTol=0.02`, `dssWrongRhoMinGain=0.05`, `coverageAbsTol=0.03`,
`energyWrongRhoMinGain=0.02`, `winklerWrongRhoMinGain=0.05`,
`jointLogLossWrongRhoMinGain=0.03`, `coxSlopeAbsTol=0.15`,
`coxInterceptAbsTol=0.20`, `variogramWrongRhoMinGain=0.02`,
`spiegelhalterAbsTol=2.0`, `iciTol=0.03`, `hosmerLemeshowChiSqTol=18`,
`sphericalVsCoinMaxRatio=1.15`, `sphericalBiasMinGain=0.01`,
`pitAdTol=1.0`, `quartetRhoAbsErrTol=0.10`,
`twCrpsWrongRhoMinGain=0.02`). Deepen residual only in
`scripts/xh-baselines.ts` + `scripts/eval-xh-math.ts` when
orchestrator applies.

Expected post-apply: `math_pass_rate=1.0000` with **+8–10** new empirics
asserts (225 → ~233–235), no BASE×ZONE×VISION.

Baseline confirmed: **225/225** (`npm run eval:xh`).

---

## Critique — what Pass-1…9 left shallow

Pass-9 EMPIRICS landed ICI / HL / spherical / AD-PIT / cond-Winkler /
quartet-ρ / twCRPS. Classical stack is dense; residual fails that still
escape Pass-2…9 kills:

| Gap | Today | Why it bites |
|-----|-------|--------------|
| **ICI is unconditional** | Global ICI + cond ECE + cond coverage + cond Winkler | Mid-p tertile can warp while pool ICI ≤ `iciTol`; same reason cond ECE exists for bin ECE |
| **PIT trilogy incomplete** | PIT ECE + KS (sup) + AD (tail) | Cramér–von Mises ∫(Fₙ−F)² catches mid-support clumps KS max-gap and AD tail weights both miss |
| **Wrong-ρ always ρ=0** | All wrong-ρ CRPS/LL/DSS/energy/Winkler/variogram/joint-LL/twCRPS | Independence is an easy foil; near-miss ρ=0.25 can look “close enough” under ρ=0 distance while still mispricing vs ρ★ |
| **Interval score only** | Winkler (width+miss on [ℓ,u]) | Single-quantile pinball kills α-level quantile miscalibration that interval averaging dilutes |
| **twCRPS extremes only** | Extreme-atom weight on {0,n} | Mid-count threshold weight (k ≥ ⌈n/2⌉) catches CDF mass shifts away from wipe/all-hit that extreme-atom twCRPS ignores |

Already landed (do **not** re-propose): analytic equicorrelated-probit xHm;
corridor Brier vs coin; ability-rate / Platt / Temp / Beta / Isotonic
stubs+fitters; ρ pairwise+triple+quartet MoM; ECE/CRPS/log-loss;
online/strata ability hooks; σ-scale kill; Platt/Temp/Beta/Isotonic
held-out gain; MCE/adaptive ECE; wrong-ρ/Var/tail CRPS; discrete PIT
ECE+KS+AD; Murphy REL/RES + identity + BSS; count log-loss/count-bin
ECE; conditional ECE; DSS; central PI coverage; ability residual kill
(global+stratified); energy + Winkler wrong-ρ; joint Bernoulli LL; Cox;
tertile-conditional coverage; variogram; Spiegelhalter Z; ICI; HL χ²;
spherical; cond Winkler; twCRPS extremes; `KILL_CRITERIA_VS_B1`
Pass-2…9 fields.

---

## Minimal falsifiable math (synthetic OK)

### 1. Tertile-conditional ICI

Reuse Pass-9 `integratedCalibrationIndex` within predicted-p̂ tertiles
(same split style as Pass-5 `conditionalEceByTertile` / Pass-8 cond
coverage). Per tertile t:

`ici_t ≤ conditionalIciTol` with **new** `conditionalIciTol=0.04`
(mirror `conditionalEceTol`; do **not** lower `iciTol` / `eceTol` /
`conditionalEceTol`).

- True corridor → all tertiles ok
- Bias (+0.12) → ≥1 tertile trips `conditionalIciTol`

```ts
export function conditionalIciByTertile(
  preds: number[],
  outcomes: number[],
  bins?: number, // default 10 equal-count inside each tertile
): { icis: number[]; ok: boolean }

export function corridorConditionalIciSanity(opts: {
  cells: Array<{ R: number; mu: number; sigma: number }>
  bias?: number
  trialsPerCell?: number
}): {
  icis: number[]
  ok: boolean
  shouldKillBiased: boolean
}
```

Cite: Austin–Steyerberg ICI (Pass-9) + tertile conditioning pattern (Pass-5/8).

### 2. Cramér–von Mises on randomized discrete PIT

Same randomized PIT U as Pass-4/5/9 (Czado–Gneiting–Held). CvM vs
Uniform(0,1):

\[
W^2=n\int_0^1\bigl(F_n(u)-u\bigr)^2\,du
=\frac{1}{12n}+\sum_{i=1}^n\Bigl(U_{(i)}-\frac{2i-1}{2n}\Bigr)^2
\]

- Draws from ρ★ scored under ρ★ PMF → `W² ≤ pitCvmTol` with **new**
  `pitCvmTol=0.5` (finite-sample band; do **not** lower `pitKsTol` /
  `pitAdTol` / `pitEceTol`)
- Same draws scored under ρ=0 → `W²` fails tol **or** exceeds star by ≥0.15

```ts
export function discretePitCramerVonMises(
  pmf: number[],
  draws: number[],
  seed?: number,
): { cvm: number; ok: boolean }

export function xhmPitCvmSanity(opts: {
  p: number
  n: number
  rhoStar: number
  trials?: number
}): {
  cvmStar: number
  cvmWrong: number
  okStar: boolean
  okKillWrong: boolean
}
```

Cite: Anderson 1962 (CvM); Czado, Gneiting, Held 2009 (randomized PIT).

### 3. Pinball / quantile score wrong-ρ

For central predictive quantile q_α from the analytic count CDF (left-
continuous / right-continuous consistent with existing PI builder),
pinball loss:

\[
S_\alpha(q,k)=(1\{k\le q\}-\alpha)\,(q-k)
\]

Mean over ρ★ draws at α∈{0.1,0.9} (or average of both):
`pin(ρ★) + pinballWrongRhoMinGain ≤ pin(ρ=0)` with **new**
`pinballWrongRhoMinGain=0.02`. Do **not** lower
`winklerWrongRhoMinGain` / `coverageAbsTol`.

Distinct from Winkler (scores the whole interval); pinball scores one
quantile level.

Cite: Gneiting & Raftery, JASA 2007 (quantile / pinball score).

```ts
export function pinballScore(q: number, k: number, alpha: number): number

export function predictiveQuantile(pmf: number[], alpha: number): number

export function xhmWrongRhoPinballKillSanity(opts: {
  p: number
  n: number
  rhoStar: number
  rhoWrong?: number
  alphas?: number[] // default [0.1, 0.9]
  trials?: number
}): {
  pinStar: number
  pinWrong: number
  gain: number
  shouldKillWrongRho: boolean
}
```

### 4. Near-miss ρ wrong-ρ kill (CRPS)

Reuse Pass-4 `meanCrpsCount` / `xhmWrongRhoCrpsKillSanity` pattern, but
set `rhoWrong=0.25` (not 0) against `rhoStar=0.5`:

`crps(ρ★) + nearMissCrpsMinGain ≤ crps(ρ=0.25)` with **new**
`nearMissCrpsMinGain=0.01` (stricter foil → smaller gain floor than
`crpsWrongRhoMinGain=0.02`). Do **not** lower `crpsWrongRhoMinGain` /
`twCrpsWrongRhoMinGain` / `energyWrongRhoMinGain`.

Independence kills stay as-is; this assert is additive.

```ts
export function xhmNearMissRhoCrpsKillSanity(opts: {
  p: number
  n: number
  rhoStar: number
  rhoNear?: number // default 0.25
  trials?: number
}): {
  crpsStar: number
  crpsNear: number
  gain: number
  shouldKillNearMiss: boolean
}
```

### 5. Mid-threshold twCRPS

Gneiting–Ranjan threshold weight on mid-count atom / half-support:

\[
\mathrm{twCRPS}_{\mathrm{mid}}(F,k)
=\bigl(F(m_{-})-1\{k\le m\}\bigr)^2
\]

with m=⌊n/2⌋ (CDF at mid threshold). Score every draw (not filtered).
Mean over ρ★ draws:
`twMid(ρ★) + midTwCrpsWrongRhoMinGain ≤ twMid(ρ=0)` with **new**
`midTwCrpsWrongRhoMinGain=0.015`. Do **not** lower
`twCrpsWrongRhoMinGain` / `crpsWrongRhoMinGain`.

Distinct from Pass-9 extreme-atom twCRPS and Pass-4 filtered tail CRPS.

```ts
export function twCrpsMidThreshold(pmf: number[], k: number): number

export function xhmWrongRhoMidTwCrpsKillSanity(opts: {
  p: number
  n: number
  rhoStar: number
  rhoWrong?: number
  trials?: number
}): {
  twStar: number
  twWrong: number
  gain: number
  shouldKillWrongRho: boolean
}
```

### 6. Additive kill constants only (never raise Pass-2…9)

```ts
export const KILL_CRITERIA_VS_B1 = {
  // --- Pass-2…9 unchanged (including ICI / HL / spherical / AD / quartet / twCRPS) ---
  // ... existing fields verbatim ...
  // --- Pass-10 deepen (FINAL) ---
  conditionalIciTol: 0.04,
  pitCvmTol: 0.5,
  pinballWrongRhoMinGain: 0.02,
  nearMissCrpsMinGain: 0.01,
  midTwCrpsWrongRhoMinGain: 0.015,
} as const
```

---

## Exact eval asserts to add (do not weaken existing)

In `scripts/eval-xh-math.ts` (additive block after Pass-9 empirics):

```ts
// --- empirics deepen (Pass-10 EMPIRICS FINAL) ---
{
  const cells = [
    { R: 50, mu: 10, sigma: 30 },
    { R: 80, mu: 0, sigma: 40 },
    { R: 40, mu: 35, sigma: 25 },
  ]
  const iciC = corridorConditionalIciSanity({
    cells,
    bias: 0,
    trialsPerCell: 3000,
  })
  assert(
    'cond ICI: true corridor tertiles ≤ conditionalIciTol',
    iciC.ok,
    `icis=${iciC.icis.map((x) => x.toFixed(4)).join(',')}`,
  )
  const iciCBad = corridorConditionalIciSanity({
    cells,
    bias: 0.12,
    trialsPerCell: 3000,
  })
  assert(
    'cond ICI: biased corridor trips ≥1 tertile',
    iciCBad.shouldKillBiased,
    `icis=${iciCBad.icis.map((x) => x.toFixed(4)).join(',')}`,
  )
}
{
  const cvm = xhmPitCvmSanity({
    p: 0.55,
    n: 4,
    rhoStar: 0.5,
    trials: 8000,
  })
  assert(
    'PIT CvM: ρ★ PMF W² ≤ pitCvmTol',
    cvm.okStar,
    `cvmStar=${cvm.cvmStar.toFixed(3)}`,
  )
  assert(
    'PIT CvM: wrong ρ=0 worse / fails tol',
    cvm.okKillWrong,
    `cvmWrong=${cvm.cvmWrong.toFixed(3)}`,
  )
  const pin = xhmWrongRhoPinballKillSanity({
    p: 0.55,
    n: 4,
    rhoStar: 0.5,
    trials: 8000,
  })
  assert(
    'wrong-ρ pinball: ρ=0 loses by ≥ pinballWrongRhoMinGain',
    pin.shouldKillWrongRho,
    `gain=${pin.gain.toFixed(3)}`,
  )
  const near = xhmNearMissRhoCrpsKillSanity({
    p: 0.55,
    n: 4,
    rhoStar: 0.5,
    rhoNear: 0.25,
    trials: 8000,
  })
  assert(
    'near-miss ρ CRPS: ρ=0.25 loses by ≥ nearMissCrpsMinGain',
    near.shouldKillNearMiss,
    `gain=${near.gain.toFixed(3)}`,
  )
  const mid = xhmWrongRhoMidTwCrpsKillSanity({
    p: 0.55,
    n: 4,
    rhoStar: 0.5,
    trials: 8000,
  })
  assert(
    'wrong-ρ mid-twCRPS: ρ=0 loses by ≥ midTwCrpsWrongRhoMinGain',
    mid.shouldKillWrongRho,
    `gain=${mid.gain.toFixed(3)}`,
  )
}
assert(
  'Pass-10 kill-criteria deepen fields finite',
  Number.isFinite(KILL_CRITERIA_VS_B1.conditionalIciTol) &&
    KILL_CRITERIA_VS_B1.pitCvmTol > 0 &&
    KILL_CRITERIA_VS_B1.pinballWrongRhoMinGain > 0 &&
    KILL_CRITERIA_VS_B1.nearMissCrpsMinGain > 0 &&
    KILL_CRITERIA_VS_B1.midTwCrpsWrongRhoMinGain > 0,
  JSON.stringify(KILL_CRITERIA_VS_B1),
)
```

Keep all Pass-2…9 Brier / ECE / ρ MoM / σ-scale / Platt / Temp / Beta /
Isotonic / MCE / Var / wrong-ρ CRPS+LL+DSS+energy+Winkler+joint-LL+variogram /
Murphy / BSS / PI coverage / cond-coverage / count-bin / triple+quartet-ρ /
cond ECE / PIT ECE+KS+AD / Cox / Spiegelhalter / ICI / HL / spherical /
cond Winkler / twCRPS extremes / ability-kill asserts verbatim.

---

## Citations

- Austin & Steyerberg, Stat. Med. 2019 — ICI (conditional reuse).
- Anderson 1962; Czado, Gneiting, Held 2009 — CvM on randomized PIT.
- Gneiting & Raftery, JASA 2007 — quantile / pinball score.
- Gneiting & Ranjan, Mon. Weather Rev. 2011 — threshold-weighted CRPS
  (mid-threshold weight).
- Pass-4 EMPIRICS: `crpsWrongRhoMinGain` (reuse; never soften) — near-miss
  is additive with a separate floor.
- Pass-5 EMPIRICS: `conditionalEceTol` / `pitKsTol` (reuse; never soften).
- Pass-7/9 EMPIRICS: `winklerWrongRhoMinGain` / `twCrpsWrongRhoMinGain` /
  `iciTol` / `pitAdTol` (reuse; never soften).

---

## Regression / risk

- **Do not** tighten or loosen any Pass-2…9 numeric kill thresholds.
- Cond ICI: empty tertile → skip/merge; raise `trialsPerCell` before
  blaming `conditionalIciTol`; never lower `iciTol` / `conditionalEceTol`.
- CvM: clamp U to `(1e-9,1−1e-9)`; raise N before touching `pitCvmTol`;
  never lower `pitKsTol` / `pitAdTol`.
- Pinball: quantile from analytic CDF must match PI builder’s discrete
  convention; raise trials before blaming `pinballWrongRhoMinGain`; never
  lower `winklerWrongRhoMinGain`.
- Near-miss: if gain vs ρ=0.25 is flaky, raise trials — do **not** raise
  `nearMissCrpsMinGain` into `crpsWrongRhoMinGain` territory or soften
  independence kills.
- Mid-twCRPS: keep extreme-atom asserts; mid weight is complementary.
- Cond-ICI / CvM-PIT / pinball / near-miss / mid-twCRPS stay
  baselines-only — never multiply into `estimateXh` (no BASE×ZONE×VISION).
- No production `xh.ts` change this pass.

---

## Decision

**KEEP_CANDIDATE** — final empirics deepen with tertile-conditional ICI,
Cramér–von Mises PIT, pinball wrong-ρ, near-miss ρ CRPS, and mid-threshold
twCRPS; leave Pass-2…9 thresholds untouched; no `xh.ts` edit.

**One-line verdict:** KEEP_CANDIDATE — cond-ICI/CvM-PIT + pinball/near-miss-ρ + mid-twCRPS close residual calib/xHm gaps without softening Pass-2…9 kills.
