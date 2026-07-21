# Pass-6 EMPIRICS — beta / BSS / DSS / coverage / ability-kill residual

**Verdict: KEEP_CANDIDATE**

Proposal only — **do not** edit `src/engine/xh.ts`, and do not soften Pass-2…5
kill thresholds (`corridorRateTol=0.03`, `brierVsCoinMaxRatio=1.15`,
`abilityResidualTol=0.08`, `minBrierGainToKill=0.01`,
`calibrationMinBrierGain=0.005`, `rhoAbsErrTol=0.05`, `eceTol=0.025`,
`logLossVsCoinMaxRatio=1.2`, `sigmaScaleRelTol=0.08`,
`sigmaScaleMinBrierGain=0.005`, `mceTol=0.06`, `varRelTol=0.08`,
`crpsWrongRhoMinGain=0.02`, `pitEceTol=0.04`, `murphyRelTol=0.02`,
`murphyMinRes=0.01`, `countLogLossWrongRhoMinGain=0.02`,
`countBinEceTol=0.05`, `tripleRhoAbsErrTol=0.08`,
`conditionalEceTol=0.04`, `pitKsTol=0.05`). Deepen residual only in
`scripts/xh-baselines.ts` + `scripts/eval-xh-math.ts` when orchestrator applies.

Expected post-apply: `math_pass_rate=1.0000` with **+8–10** new empirics
asserts (129 → ~137–139), no BASE×ZONE×VISION.

Baseline confirmed: **129/129** (`npm run eval:xh`).

---

## Critique — what Pass-1…5 left shallow

| Gap | Today | Why it bites |
|-----|-------|--------------|
| **Beta calib gate dead** | Temp (1-param) + Platt (2-param) only | Asymmetric logit warps (a≠−b on log-p / log-(1−p)) need Kull’s 3-param family; Platt can underfit |
| **Murphy identity unchecked** | REL/RES/UNC reported | Algebraic `BS = REL − RES + UNC` never asserted — silent binning bugs slip through |
| **No Brier skill score** | RES floor vs climatology only | BSS = 1 − BS/BS_clim is the standard skill kill; RES>0 ≠ meaningful skill vs coin |
| **Count mean+var score unused** | CRPS + count log-loss | DSS kills Var(K) misspecification even when CRPS gain is marginal; complements wrong-ρ CRPS/LL |
| **No predictive-interval coverage** | PIT ECE/KS + count-bin ECE | Uniform PIT ≠ honest central (1−α) interval coverage for wipe/all-hit mass |
| **Ability residual kill never fires** | Constants + stub table only | Pass-2 `abilityResidualTol`/`minBrierGainToKill` is dead until a synthetic planted kill path exists |
| **Energy score on I-vector absent** | Scores on K=∑I only | Matching count PMF can still miss pairwise/joint geometry; energy on hit indicators refutes ρ=0 when margins match |

Already landed (do **not** re-propose): analytic equicorrelated-probit xHm;
corridor Brier vs coin; ability-rate / Platt / temperature stubs+fitters;
ρ pairwise+triple MoM; ECE/CRPS/log-loss; online/strata ability hooks;
σ-scale kill; Platt/Temp held-out gain; MCE/adaptive ECE; wrong-ρ/Var/tail
CRPS; discrete PIT ECE; Murphy REL/RES; count log-loss/count-bin ECE;
conditional ECE; PIT KS; `KILL_CRITERIA_VS_B1` Pass-2…5 fields.

---

## Minimal falsifiable math (synthetic OK)

### 1. Beta calibration fit + held-out gain gate

Beta family (Kull et al.):

\[
\operatorname{logit} m(p) = c + a\log p + b\log(1-p)
\]

Identity: \(a=1,\,b=-1,\,c=0\) → \(m(p)=p\). Corrupt with
`(a,b,c)=(0.6,-1.4,0.3)`; fit grid on train (minimize Brier); apply on
held-out.

**Contracts (additive):**

- Identity raw corridor: held-out Brier gain ≤ `calibrationMinBrierGain` → **no-op**
  (reuse Pass-2 gate — do **not** lower it).
- Corrupt warp: gain ≥ `calibrationMinBrierGain` → apply allowed; post-beta
  ECE ≤ `eceTol`.

Cite: Kull, Silva Filho, Flach — AISTATS 2017. Complements Pass-4 Platt /
Pass-5 Temp without replacing them.

```ts
/** Identity at a=1, b=-1, c=0. */
export function betaScale(p: number, a = 1, b = -1, c = 0): number {
  const u = Math.min(1 - 1e-9, Math.max(1e-9, p))
  if (Math.abs(a - 1) < 1e-12 && Math.abs(b + 1) < 1e-12 && Math.abs(c) < 1e-12)
    return u
  const z = c + a * Math.log(u) + b * Math.log(1 - u)
  return 1 / (1 + Math.exp(-z))
}

export function fitBetaCalib(
  preds: number[],
  outcomes: number[],
): { a: number; b: number; c: number }

export function betaHeldOutGainSanity(opts: {
  cells: Array<{ R: number; mu: number; sigma: number }>
  corrupt?: { a: number; b: number; c: number } // default identity
  trainFrac?: number
  trialsPerCell?: number
}): {
  rawBrier: number
  calibratedBrier: number
  gain: number
  shouldApply: boolean
  a: number
  b: number
  c: number
}
```

Wire corrupt path via extending `sampleCorridorCells` with
`corruptBeta?: { a; b; c }` (additive; leave Platt/Temp paths untouched).

### 2. Murphy BS identity + Brier Skill Score

For any equal-width Murphy decomposition, require

\[
\bigl|\mathrm{BS} - (\mathrm{REL} - \mathrm{RES} + \mathrm{UNC})\bigr|
  \le \texttt{murphyIdentityTol}\quad(=10^{-9})
\]

Brier skill vs climatology:

\[
\mathrm{BSS} = 1 - \frac{\mathrm{BS}}{\mathrm{BS}_{\mathrm{clim}}},\quad
\mathrm{BS}_{\mathrm{clim}}=\bar y(1-\bar y).
\]

**Synthetic kill:** true corridor → `BSS ≥ bssMinTol` (**0.02**);
climatology forecasts → `|BSS| ≤ 1e-9`.

Cite: Murphy 1973; Wilks Statistical Methods in the Atmospheric Sciences.

```ts
export function murphyIdentitySanity(
  preds: number[],
  outcomes: number[],
  bins = 10,
): { absGap: number; ok: boolean }

export function brierSkillScore(preds: number[], outcomes: number[]): number

export function corridorBssSanity(opts: {
  cells: Array<{ R: number; mu: number; sigma: number }>
  trialsPerCell?: number
}): { bss: number; climBss: number; ok: boolean }
```

### 3. Dawid–Sebastiani score + wrong-ρ kill

For count forecast with mean μ and variance σ² from analytic moments:

\[
\mathrm{DSS} = \frac{(k-\mu)^2}{\sigma^2} + \log(\sigma^2)
\]

(mean over draws; clamp σ²≥1e-12). Proper for Gaussian approx of K;
sensitive to Var misspecification that CRPS can dilute.

**Contract:** draws from ρ★=0.5 →
`dss(ρ★) + dssWrongRhoMinGain ≤ dss(ρ_wrong=0)` with
`dssWrongRhoMinGain=0.05`. Do **not** lower `crpsWrongRhoMinGain` /
`countLogLossWrongRhoMinGain`.

Cite: Dawid & Sebastiani 1999; Gneiting & Raftery 2007.

```ts
export function dawidSebastianiScore(
  mu: number,
  variance: number,
  draws: number[],
): number

export function xhmWrongRhoDssKillSanity(opts: {
  p: number
  n: number
  rhoStar: number
  rhoWrong?: number
  trials?: number
}): {
  dssStar: number
  dssWrong: number
  gain: number
  shouldKillWrongRho: boolean
}
```

### 4. Central predictive-interval coverage for xHm

From analytic PMF q, build central (1−α) interval [L,U] (smallest interval
with mass ≥ 1−α, or equal-tail CDF quantiles). Coverage =
fraction of ρ★ draws in [L,U].

**Contracts:**

- Correct PMF, α=0.1, N≥8e3: `|cov − 0.9| ≤ coverageAbsTol` (**0.03**).
- Wrong ρ=0 interval on same draws: `|cov − 0.9| > coverageAbsTol`
  **or** `|cov_wrong − 0.9| > |cov_star − 0.9| + 0.02`.

Distinct from PIT uniformity (Pass-4/5): this is interval honesty for wipe
bands.

Cite: Gneiting & Raftery 2007 (interval score / coverage); Czado et al. 2009.

```ts
export function centralPredictiveInterval(
  pmf: number[],
  alpha = 0.1,
): { lo: number; hi: number; mass: number }

export function xhmIntervalCoverageSanity(opts: {
  p: number
  n: number
  rhoStar: number
  rhoWrong?: number
  alpha?: number
  trials?: number
}): {
  covStar: number
  covWrong: number
  okStar: boolean
  okKillWrong: boolean
}
```

### 5. Energy score on hit-indicator vectors

Sample I ∈ {0,1}^n under equicorrelated probit (same latent draw as
`drawXhmCounts` but keep the vector). Energy score with L1 (Hamming):

\[
\mathrm{ES}(P,y)=\mathbb{E}\|X-y\|_1 - \tfrac12\mathbb{E}\|X-X'\|_1
\]

Approximate expectations by M paired draws from the forecast law
(analytic one-factor sampler). Mean ES under ρ★ draws: require
`es(ρ★) + energyWrongRhoMinGain ≤ es(ρ=0)` with
`energyWrongRhoMinGain=0.02`.

Cite: Gneiting & Raftery 2007 (energy score); scores the joint, not only K.

```ts
export function binaryEnergyScore(
  sampleForecast: () => number[], // length-n binary
  y: number[],
  pairedDraws?: number,
): number

export function xhmWrongRhoEnergyKillSanity(opts: {
  p: number
  n: number
  rhoStar: number
  rhoWrong?: number
  trials?: number
}): {
  esStar: number
  esWrong: number
  gain: number
  shouldKillWrongRho: boolean
}
```

### 6. Ability residual kill path (synthetic — finally exercise Pass-2)

Plant: true outcomes ~ Bern(p★); corridor forecast locked to a **biased**
constant `p_corr = clip(p★+0.15)`; ability table stores empirical rate ≈ p★
(with n≥200 casts).

**Kill when both:**

1. `mean |p_corr − abilityRate| > abilityResidualTol` (0.08 — unchanged)
2. ability-rate Brier beats corridor Brier by ≥ `minBrierGainToKill` (0.01)

Identity control: corridor = true p★ and ability ≈ p★ → `shouldKillB1=false`.

Do **not** lower Pass-2 thresholds; this only makes the dead gate live.

```ts
export function abilityResidualKillSanity(opts: {
  pStar: number
  corridorBias?: number // default 0.15 for kill path; 0 for identity
  casts?: number
  trials?: number
}): {
  residual: number
  abilityBrier: number
  corridorBrier: number
  brierGain: number
  shouldKillB1: boolean
}
```

### 7. Additive kill constants only (never raise Pass-2…5)

```ts
export const KILL_CRITERIA_VS_B1 = {
  // --- Pass-2 (unchanged) ---
  corridorRateTol: 0.03,
  brierVsCoinMaxRatio: 1.15,
  abilityResidualTol: 0.08,
  minBrierGainToKill: 0.01,
  calibrationMinBrierGain: 0.005,
  // --- Pass-3 (unchanged) ---
  rhoAbsErrTol: 0.05,
  eceTol: 0.025,
  logLossVsCoinMaxRatio: 1.2,
  sigmaScaleRelTol: 0.08,
  sigmaScaleMinBrierGain: 0.005,
  // --- Pass-4 (unchanged) ---
  mceTol: 0.06,
  varRelTol: 0.08,
  crpsWrongRhoMinGain: 0.02,
  pitEceTol: 0.04,
  // --- Pass-5 (unchanged) ---
  murphyRelTol: 0.02,
  murphyMinRes: 0.01,
  countLogLossWrongRhoMinGain: 0.02,
  countBinEceTol: 0.05,
  tripleRhoAbsErrTol: 0.08,
  conditionalEceTol: 0.04,
  pitKsTol: 0.05,
  // --- Pass-6 deepen ---
  murphyIdentityTol: 1e-9,
  bssMinTol: 0.02,
  dssWrongRhoMinGain: 0.05,
  coverageAbsTol: 0.03,
  energyWrongRhoMinGain: 0.02,
} as const
```

---

## Exact eval asserts to add (do not weaken existing)

In `scripts/eval-xh-math.ts` (additive block after Pass-5 empirics):

```ts
// --- empirics deepen (Pass-6 EMPIRICS) ---
{
  const cells = [
    { R: 50, mu: 10, sigma: 30 },
    { R: 80, mu: 0, sigma: 40 },
    { R: 40, mu: 35, sigma: 25 },
  ]
  const idB = betaHeldOutGainSanity({ cells, trialsPerCell: 3000 })
  assert(
    'Beta gate: identity corridor gain < calibrationMinBrierGain (no-op)',
    !idB.shouldApply,
    `gain=${idB.gain.toFixed(4)}`,
  )
  const badB = betaHeldOutGainSanity({
    cells,
    corrupt: { a: 0.6, b: -1.4, c: 0.3 },
    trialsPerCell: 4000,
  })
  assert(
    'Beta gate: corrupt warp gain ≥ calibrationMinBrierGain',
    badB.shouldApply,
    `gain=${badB.gain.toFixed(4)} a=${badB.a.toFixed(2)}`,
  )
  const bss = corridorBssSanity({ cells, trialsPerCell: 3000 })
  assert(
    'BSS: true corridor ≥ bssMinTol; clim ~ 0',
    bss.ok && Math.abs(bss.climBss) < 1e-9,
    `bss=${bss.bss.toFixed(4)} clim=${bss.climBss.toFixed(4)}`,
  )
  // Murphy identity on same corridor sample
  const preds: number[] = []
  const outs: number[] = []
  // ... sampleCorridorCells-equivalent fill ...
  const id = murphyIdentitySanity(preds, outs, 10)
  assert(
    'Murphy identity: |BS − (REL−RES+UNC)| ≤ murphyIdentityTol',
    id.ok,
    `gap=${id.absGap}`,
  )
}
{
  const dss = xhmWrongRhoDssKillSanity({
    p: 0.55,
    n: 4,
    rhoStar: 0.5,
    trials: 10000,
  })
  assert(
    'wrong-ρ DSS: ρ=0 loses to ρ★ by ≥ dssWrongRhoMinGain',
    dss.shouldKillWrongRho,
    `gain=${dss.gain.toFixed(3)}`,
  )
  const cov = xhmIntervalCoverageSanity({
    p: 0.55,
    n: 4,
    rhoStar: 0.5,
    trials: 10000,
  })
  assert(
    'xHm 90% PI: |cov★−0.9| ≤ coverageAbsTol',
    cov.okStar,
    `cov=${cov.covStar.toFixed(3)}`,
  )
  assert(
    'xHm 90% PI: wrong ρ=0 coverage worse (or outside tol)',
    cov.okKillWrong,
    `covW=${cov.covWrong.toFixed(3)} covS=${cov.covStar.toFixed(3)}`,
  )
  const es = xhmWrongRhoEnergyKillSanity({
    p: 0.55,
    n: 4,
    rhoStar: 0.5,
    trials: 6000,
  })
  assert(
    'wrong-ρ energy: ρ=0 loses to ρ★ by ≥ energyWrongRhoMinGain',
    es.shouldKillWrongRho,
    `gain=${es.gain.toFixed(3)}`,
  )
  const kill = abilityResidualKillSanity({
    pStar: 0.55,
    corridorBias: 0.15,
    casts: 400,
    trials: 4000,
  })
  assert(
    'ability residual kill: biased corridor + empirical rate → shouldKillB1',
    kill.shouldKillB1,
    `res=${kill.residual.toFixed(3)} gain=${kill.brierGain.toFixed(3)}`,
  )
  const keep = abilityResidualKillSanity({
    pStar: 0.55,
    corridorBias: 0,
    casts: 400,
    trials: 4000,
  })
  assert(
    'ability residual kill: identity corridor → no kill',
    !keep.shouldKillB1,
    `res=${keep.residual.toFixed(3)}`,
  )
}
assert(
  'Pass-6 kill-criteria deepen fields finite',
  Number.isFinite(KILL_CRITERIA_VS_B1.bssMinTol) &&
    KILL_CRITERIA_VS_B1.dssWrongRhoMinGain > 0 &&
    KILL_CRITERIA_VS_B1.coverageAbsTol > 0 &&
    KILL_CRITERIA_VS_B1.energyWrongRhoMinGain > 0 &&
    KILL_CRITERIA_VS_B1.murphyIdentityTol > 0,
  JSON.stringify(KILL_CRITERIA_VS_B1),
)
```

Keep all Pass-2…5 Brier / ECE / ρ MoM / σ-scale / Platt / Temp / MCE /
Var / wrong-ρ CRPS+LL / Murphy REL-RES / count-bin ECE / triple-ρ /
cond ECE / PIT ECE+KS asserts verbatim.

---

## Citations

- Kull, Silva Filho, Flach, AISTATS 2017 — beta calibration (3-param family).
- Platt 1999; Guo et al. ICML 2017 — leave gain threshold untouched (Pass-4/5).
- Murphy, J. Appl. Meteor. 1973 — REL/RES/UNC + BS identity; BSS via Wilks.
- Dawid & Sebastiani, 1999 — Dawid–Sebastiani score for mean/var forecasts.
- Gneiting & Raftery, JASA 2007 — proper scores; energy score; interval coverage.
- Czado, Gneiting, Held, Biometrics 2009 — discrete PIT companion (do not re-land).
- Ochi & Prentice, Biometrika 1984 — equicorrelated probit (xHm sampler reuse).
- Pass-2 EMPIRICS: ability residual kill constants (exercise, do not re-land stubs).

---

## Regression / risk

- **Do not** tighten any Pass-2…5 numeric kill thresholds.
- Beta grid must clamp preds to `[1e-9,1−1e-9]`; search a∈[0.3,2.2],
  b∈[−2.2,−0.3], c∈[−1,1] (coarse 0.1) — flaky gain → denser grid / more
  trials, not lower `calibrationMinBrierGain`.
- Murphy identity tol is numerical only (`1e-9`); do not confuse with
  `murphyRelTol`.
- DSS uses analytic moments of the **forecast** ρ, not sample moments of
  draws — otherwise wrong-ρ comparison collapses.
- Interval coverage: prefer equal-tail CDF quantiles for reproducibility;
  raise N before blaming `coverageAbsTol`.
- Energy score paired-draw noise: fix seeds; raise `trials`/`pairedDraws`
  before raising `energyWrongRhoMinGain`.
- Ability kill clears/`registerAbilityRate` must not leak into other asserts
  (call `clearAbilityRates()` after).
- Beta / BSS / DSS / coverage / energy / ability-kill stay baselines-only —
  never multiply into `estimateXh` (no BASE×ZONE×VISION).
- No production `xh.ts` change this pass.

---

## Decision

**KEEP_CANDIDATE** — deepen empirics with beta held-out gain, Murphy identity +
BSS, DSS + interval coverage + energy wrong-ρ kills, and a live ability
residual kill path; leave Pass-2…5 thresholds untouched; no `xh.ts` edit.

**One-line verdict:** KEEP_CANDIDATE — beta/BSS + DSS/coverage/energy + ability-kill deepen calibration/xHm without softening Pass-2…5 kills.
