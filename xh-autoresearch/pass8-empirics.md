# Pass-8 EMPIRICS — isotonic / joint-LL / Cox / cond-coverage / stratified-ability / variogram / Spiegelhalter

**Verdict: KEEP_CANDIDATE**

Proposal only — **do not** edit `src/engine/xh.ts`, and do not soften Pass-2…7
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
`energyWrongRhoMinGain=0.02`, `winklerWrongRhoMinGain=0.05`). Deepen residual
only in `scripts/xh-baselines.ts` + `scripts/eval-xh-math.ts` when
orchestrator applies.

Expected post-apply: `math_pass_rate=1.0000` with **+8–10** new empirics
asserts (158 → ~166–168), no BASE×ZONE×VISION.

Baseline confirmed: **158/158** (`npm run eval:xh`).

---

## Critique — what Pass-1…7 left shallow

Pass-7 EMPIRICS **only landed** energy + Winkler wrong-ρ kills. The rest of the
Pass-7 proposal never shipped; those debts plus two new calib/xHm residuals
are the Pass-8 deepen.

| Gap | Today | Why it bites |
|-----|-------|--------------|
| **Isotonic (PAV) gate dead** | Temp / Platt / Beta parametric only | Monotone nonparametric shape warps those 1–3-param maps miss; same `calibrationMinBrierGain` gate still unused for PAV |
| **Count LL ≠ joint LL** | `−log q_K` on K=∑I; energy on I | Matching count PMF + energy can still miss exact I-vector likelihood; multivariate Bernoulli log-score on I refutes ρ=0 when margins match |
| **No Cox reliability regression** | ECE / MCE / Murphy REL | Slope≠1 or intercept≠0 on logit(p̂) vs outcomes is the classical calibration residual; complements bin ECE |
| **Unconditional PI only** | Global 90% coverage + Winkler | Mid/high predicted-mean bands can undercover while low-mean bands overcover; tertile-conditional coverage catches it |
| **Ability kill is global-only** | Single ability key | Strata keys (`ability\|vision\|range`) already exist; residual kill never exercises stratified empirical vs biased corridor |
| **Energy ≠ pairwise geometry** | L1 energy on I | Energy can pass while pairwise lag structure is wrong; variogram score kills dependence misspecification energy dilutes |
| **No classical Z residual** | ECE / Cox slope | Spiegelhalter Z is a single-number calibration kill complementary to Cox; fires on mean-variance mismatch ECE bins smear |

Already landed (do **not** re-propose): analytic equicorrelated-probit xHm;
corridor Brier vs coin; ability-rate / Platt / Temp / Beta stubs+fitters;
ρ pairwise+triple MoM; ECE/CRPS/log-loss; online/strata ability hooks;
σ-scale kill; Platt/Temp/Beta held-out gain; MCE/adaptive ECE; wrong-ρ/Var/tail
CRPS; discrete PIT ECE+KS; Murphy REL/RES + identity + BSS; count
log-loss/count-bin ECE; conditional ECE; DSS; central PI coverage; ability
residual kill (global); energy + Winkler wrong-ρ; `KILL_CRITERIA_VS_B1`
Pass-2…7 fields.

---

## Minimal falsifiable math (synthetic OK)

### 1. Isotonic (PAV) held-out gain gate (Pass-7 unpaid)

Pool-adjacent-violators isotonic regression: map raw p̂ → monotone calibrated
probs minimizing train Brier (nonparametric). Same held-out gate as Pass-2:

- Identity corridor: gain < `calibrationMinBrierGain` → **no-op**
- Corrupt bias (+0.12) or beta warp: gain ≥ `calibrationMinBrierGain` → apply;
  post-isotonic ECE ≤ `eceTol`

Do **not** lower `calibrationMinBrierGain`. Complements Temp/Platt/Beta without
replacing them.

Cite: Zadrozny & Elkan 2002; Niculescu-Mizil & Caruana 2005 (isotonic calib).

```ts
export function fitIsotonicCalib(
  preds: number[],
  outcomes: number[],
): { breaks: number[]; values: number[] } // step function on sorted p̂

export function isotonicScale(
  p: number,
  fit: { breaks: number[]; values: number[] },
): number

export function isotonicHeldOutGainSanity(opts: {
  cells: Array<{ R: number; mu: number; sigma: number }>
  bias?: number
  trainFrac?: number
  trialsPerCell?: number
}): {
  rawBrier: number
  calibratedBrier: number
  gain: number
  shouldApply: boolean
}
```

### 2. Multivariate Bernoulli joint log-score (I-vector) (Pass-7 unpaid)

For observed y ∈ {0,1}^n and forecast law P_ρ (one-factor probit),

\[
\mathrm{LL}_{\mathrm{joint}} = -\log P_\rho(I=y)
\]

Exact under the model via 1D Gauss mixture:
\(P(I=y)=\mathbb{E}[\prod_j \pi(Z)^{y_j}(1-\pi(Z))^{1-y_j}]\).

Contract: draws from ρ★=0.5 →
`ll_joint(ρ★) + jointLogLossWrongRhoMinGain ≤ ll_joint(ρ=0)` with
`jointLogLossWrongRhoMinGain=0.03`. Do **not** lower
`countLogLossWrongRhoMinGain` / `energyWrongRhoMinGain`.

Cite: Gneiting & Raftery 2007 (logarithmic score on multivariate outcomes);
Ochi & Prentice 1984 (conditional independence given Z).

```ts
export function jointBernoulliLogProb(
  p: number,
  rho: number,
  y: number[],
): number // log P(I=y); clamp ≥ log(1e-12)

export function xhmWrongRhoJointLogLossKillSanity(opts: {
  p: number
  n: number
  rhoStar: number
  rhoWrong?: number
  trials?: number
}): {
  llStar: number
  llWrong: number
  gain: number
  shouldKillWrongRho: boolean
}
```

### 3. Cox calibration slope / intercept residual (Pass-7 unpaid)

Logistic regression of outcomes on `logit(p̂)`:

\[
\operatorname{logit}\mathbb{P}(Y=1)=\alpha + \beta\cdot\operatorname{logit}(\hat p)
\]

True corridor → `|β−1| ≤ coxSlopeAbsTol` and `|α| ≤ coxInterceptAbsTol`.
Deliberate bias (+0.12) → `|β−1| > coxSlopeAbsTol` **or**
`|α| > coxInterceptAbsTol` (kill miscalibrated map).

New tols: `coxSlopeAbsTol=0.15`, `coxInterceptAbsTol=0.20`. Do **not**
soften `eceTol` / `mceTol`.

Cite: Cox 1958; Miller et al. 1991 (calibration slope); Guo et al. 2017.

```ts
export function coxCalibrationFit(
  preds: number[],
  outcomes: number[],
): { intercept: number; slope: number }

export function corridorCoxSanity(opts: {
  cells: Array<{ R: number; mu: number; sigma: number }>
  bias?: number
  trialsPerCell?: number
}): {
  intercept: number
  slope: number
  ok: boolean // |slope-1| and |intercept| within tols when bias=0
  shouldKillBiased: boolean // true when bias≠0 trips tols
}
```

### 4. Tertile-conditional PI coverage (Pass-7 unpaid)

Split ρ★ draws into tertiles of predicted mean μ=n·p (or of realized
forecast-cell p when multi-cell). Within each tertile, check
`|cov_t − (1−α)| ≤ coverageAbsTol` under correct ρ; wrong ρ=0 must fail
≥1 tertile **or** have mean |cov−target| worse by ≥0.02.

Reuse existing `coverageAbsTol=0.03` — do **not** loosen. New flag only:
`conditionalCoverageOk`.

```ts
export function xhmConditionalCoverageSanity(opts: {
  cells: Array<{ p: number; n: number; rhoStar: number }>
  alpha?: number
  trialsPerCell?: number
}): {
  covByTertile: number[]
  okStar: boolean
  okKillWrong: boolean
}
```

### 5. Stratified ability residual kill (Pass-7 unpaid)

Plant: outcomes ~ Bern(p★) in strata `LuxQ|fog|mid`; corridor locked to
biased `p_corr=clip(p★+0.15)`; ability table stores stratified empirical
via `abilityRateKey` + `updateAbilityRate`.

Kill when both Pass-2 conditions hold on the **stratified** posterior
(unchanged tols). Identity control: bias=0 → no kill. Clear table after.

```ts
export function stratifiedAbilityResidualKillSanity(opts: {
  pStar: number
  ability: string
  strata: { vision: string; rangeBand: string }
  corridorBias?: number
  casts?: number
  trials?: number
}): {
  key: string
  residual: number
  brierGain: number
  shouldKillB1: boolean
}
```

### 6. Variogram score on hit-indicator vectors (Pass-8 new)

For binary vectors with lag weight w_{ij}=1 (all pairs), Scheuerer–Hamill
variogram score:

\[
\mathrm{VS}(P,y)=\sum_{i<j}\bigl(
  |y_i-y_j| - \mathbb{E}_P|X_i-X_j|
\bigr)^2
\]

Approximate \(\mathbb{E}_P|X_i-X_j|\) by M draws from the one-factor sampler
(or analytic pairwise under equicorrelated probit:
\(\mathbb{E}|I_i-I_j|=2(p-\pi_{11})\)).

Contract: draws from ρ★=0.5 →
`vs(ρ★) + variogramWrongRhoMinGain ≤ vs(ρ=0)` with
`variogramWrongRhoMinGain=0.02`. Do **not** lower
`energyWrongRhoMinGain` / `winklerWrongRhoMinGain`.

Cite: Scheuerer & Hamill, MWR 2015 (variogram score); Gneiting & Raftery 2007.

```ts
export function binaryVariogramScore(
  sampleForecast: () => number[], // length-n binary
  y: number[],
  pairedDraws?: number, // default 64
): number

export function xhmWrongRhoVariogramKillSanity(opts: {
  p: number
  n: number
  rhoStar: number
  rhoWrong?: number
  trials?: number
  pairedDraws?: number
}): {
  vsStar: number
  vsWrong: number
  gain: number
  shouldKillWrongRho: boolean
}
```

Export `drawXhmIndicators` (currently file-private) for reuse with energy /
variogram / joint-LL samplers.

### 7. Spiegelhalter Z calibration residual (Pass-8 new)

Classical single-number calibration kill (Spiegelhalter 1986):

\[
Z = \frac{\sum_i (y_i-\hat p_i)}
         {\sqrt{\sum_i \hat p_i(1-\hat p_i)}}
\]

True corridor → `|Z| ≤ spiegelhalterAbsTol` (**2.0**). Deliberate bias
(+0.12) → `|Z| > spiegelhalterAbsTol`. Do **not** soften `eceTol` /
`coxSlopeAbsTol`.

Cite: Spiegelhalter, Stat. Med. 1986; complements Cox slope without IRLS.

```ts
export function spiegelhalterZ(
  preds: number[],
  outcomes: number[],
): number

export function corridorSpiegelhalterSanity(opts: {
  cells: Array<{ R: number; mu: number; sigma: number }>
  bias?: number
  trialsPerCell?: number
}): {
  z: number
  ok: boolean // |z| ≤ tol when bias=0
  shouldKillBiased: boolean
}
```

### 8. Additive kill constants only (never raise Pass-2…7)

```ts
export const KILL_CRITERIA_VS_B1 = {
  // --- Pass-2…7 unchanged (including energyWrongRhoMinGain / winklerWrongRhoMinGain) ---
  // ... existing fields verbatim ...
  // --- Pass-8 deepen ---
  jointLogLossWrongRhoMinGain: 0.03,
  coxSlopeAbsTol: 0.15,
  coxInterceptAbsTol: 0.20,
  variogramWrongRhoMinGain: 0.02,
  spiegelhalterAbsTol: 2.0,
} as const
```

---

## Exact eval asserts to add (do not weaken existing)

In `scripts/eval-xh-math.ts` (additive block after Pass-7 empirics):

```ts
// --- empirics deepen (Pass-8 EMPIRICS) ---
{
  const jll = xhmWrongRhoJointLogLossKillSanity({
    p: 0.55,
    n: 4,
    rhoStar: 0.5,
    trials: 4000,
  })
  assert(
    'wrong-ρ joint LL: ρ=0 loses to ρ★ by ≥ jointLogLossWrongRhoMinGain',
    jll.shouldKillWrongRho,
    `gain=${jll.gain.toFixed(3)}`,
  )
  const vs = xhmWrongRhoVariogramKillSanity({
    p: 0.55,
    n: 4,
    rhoStar: 0.5,
    trials: 6000,
    pairedDraws: 64,
  })
  assert(
    'wrong-ρ variogram: ρ=0 loses to ρ★ by ≥ variogramWrongRhoMinGain',
    vs.shouldKillWrongRho,
    `gain=${vs.gain.toFixed(3)}`,
  )
}
{
  const cells = [
    { R: 50, mu: 10, sigma: 30 },
    { R: 80, mu: 0, sigma: 40 },
    { R: 40, mu: 35, sigma: 25 },
  ]
  const idIso = isotonicHeldOutGainSanity({ cells, bias: 0, trialsPerCell: 3000 })
  assert(
    'Isotonic gate: identity corridor gain < calibrationMinBrierGain (no-op)',
    !idIso.shouldApply,
    `gain=${idIso.gain.toFixed(4)}`,
  )
  const badIso = isotonicHeldOutGainSanity({
    cells,
    bias: 0.12,
    trialsPerCell: 4000,
  })
  assert(
    'Isotonic gate: biased corridor gain ≥ calibrationMinBrierGain',
    badIso.shouldApply,
    `gain=${badIso.gain.toFixed(4)}`,
  )
  const coxOk = corridorCoxSanity({ cells, bias: 0, trialsPerCell: 3000 })
  assert(
    'Cox calib: true corridor slope≈1, intercept≈0',
    coxOk.ok,
    `a=${coxOk.intercept.toFixed(3)} b=${coxOk.slope.toFixed(3)}`,
  )
  const coxBad = corridorCoxSanity({ cells, bias: 0.12, trialsPerCell: 3000 })
  assert(
    'Cox calib: biased corridor trips slope/intercept tols',
    coxBad.shouldKillBiased,
    `a=${coxBad.intercept.toFixed(3)} b=${coxBad.slope.toFixed(3)}`,
  )
  const spOk = corridorSpiegelhalterSanity({ cells, bias: 0, trialsPerCell: 3000 })
  assert(
    'Spiegelhalter Z: true corridor |Z| ≤ spiegelhalterAbsTol',
    spOk.ok,
    `z=${spOk.z.toFixed(3)}`,
  )
  const spBad = corridorSpiegelhalterSanity({
    cells,
    bias: 0.12,
    trialsPerCell: 3000,
  })
  assert(
    'Spiegelhalter Z: biased corridor trips |Z| tol',
    spBad.shouldKillBiased,
    `z=${spBad.z.toFixed(3)}`,
  )
}
{
  const covC = xhmConditionalCoverageSanity({
    cells: [
      { p: 0.35, n: 4, rhoStar: 0.5 },
      { p: 0.55, n: 4, rhoStar: 0.5 },
      { p: 0.75, n: 4, rhoStar: 0.5 },
    ],
    trialsPerCell: 6000,
  })
  assert(
    'xHm conditional 90% PI: tertiles honest under ρ★',
    covC.okStar,
    `cov=${covC.covByTertile.map((c) => c.toFixed(3)).join(',')}`,
  )
  assert(
    'xHm conditional 90% PI: wrong ρ=0 worse in ≥1 tertile',
    covC.okKillWrong,
  )
  const sk = stratifiedAbilityResidualKillSanity({
    pStar: 0.55,
    ability: 'LuxQ',
    strata: { vision: 'fog', rangeBand: 'mid' },
    corridorBias: 0.15,
    casts: 400,
  })
  assert(
    'stratified ability residual kill trips',
    sk.shouldKillB1,
    `key=${sk.key} res=${sk.residual.toFixed(3)}`,
  )
  const skKeep = stratifiedAbilityResidualKillSanity({
    pStar: 0.55,
    ability: 'LuxQ',
    strata: { vision: 'fog', rangeBand: 'mid' },
    corridorBias: 0,
    casts: 400,
  })
  assert(
    'stratified ability identity → no kill',
    !skKeep.shouldKillB1,
    `res=${skKeep.residual.toFixed(3)}`,
  )
}
assert(
  'Pass-8 kill-criteria deepen fields finite',
  Number.isFinite(KILL_CRITERIA_VS_B1.jointLogLossWrongRhoMinGain) &&
    KILL_CRITERIA_VS_B1.coxSlopeAbsTol > 0 &&
    KILL_CRITERIA_VS_B1.coxInterceptAbsTol > 0 &&
    KILL_CRITERIA_VS_B1.variogramWrongRhoMinGain > 0 &&
    KILL_CRITERIA_VS_B1.spiegelhalterAbsTol > 0,
  JSON.stringify(KILL_CRITERIA_VS_B1),
)
```

Keep all Pass-2…7 Brier / ECE / ρ MoM / σ-scale / Platt / Temp / Beta /
MCE / Var / wrong-ρ CRPS+LL+DSS+energy+Winkler / Murphy / BSS / PI coverage /
count-bin / triple-ρ / cond ECE / PIT / ability-kill asserts verbatim.

---

## Citations

- Zadrozny & Elkan 2002; Niculescu-Mizil & Caruana, ICML 2005 — isotonic
  calibration (PAV).
- Gneiting & Raftery, JASA 2007 — logarithmic score (joint); energy companion.
- Ochi & Prentice, Biometrika 1984 — equicorrelated probit (I-sampler / joint).
- Cox 1958; Miller, Hui, Tierney 1991 — calibration slope/intercept.
- Scheuerer & Hamill, Mon. Weather Rev. 2015 — variogram score.
- Spiegelhalter, Stat. Med. 1986 — Z calibration residual.
- Pass-2 EMPIRICS: `abilityResidualTol` / `minBrierGainToKill` /
  `calibrationMinBrierGain` (reuse; never soften).
- Pass-6/7 EMPIRICS: `coverageAbsTol` / `energyWrongRhoMinGain` /
  `winklerWrongRhoMinGain` (reuse; never soften).

---

## Regression / risk

- **Do not** tighten or loosen any Pass-2…7 numeric kill thresholds.
- Isotonic PAV must be nondecreasing; empty train bins → inherit neighbor;
  clamp preds to `[1e-9,1−1e-9]`. Flaky gain → more trials, not lower
  `calibrationMinBrierGain`.
- Joint LL: integrate with same `expectGauss` dz as analytic moments; clamp
  log-prob floor at `log(1e-12)`.
- Cox fit: use stable IRLS / grid on (α,β); avoid singular design when all
  p̂ identical (multi-cell corridor required).
- Conditional coverage: raise N before blaming `coverageAbsTol`.
- Stratified ability kill must `clearAbilityRates()` after; do not leak into
  global Pass-6 ability asserts.
- Variogram: prefer analytic pairwise \(\mathbb{E}|I_i-I_j|=2(p-\pi_{11})\)
  for the forecast term when available; else fix seeds and raise
  `trials`/`pairedDraws` before touching `variogramWrongRhoMinGain`.
- Spiegelhalter: clamp p̂ away from {0,1} so denom > 0; multi-cell sample
  required.
- Isotonic / joint-LL / Cox / cond-coverage / stratified-ability / variogram /
  Spiegelhalter stay baselines-only — never multiply into `estimateXh`
  (no BASE×ZONE×VISION).
- No production `xh.ts` change this pass.

---

## Decision

**KEEP_CANDIDATE** — deepen empirics by landing Pass-7 unpaid isotonic / joint
Bernoulli LL / Cox / tertile-conditional PI / stratified ability residual,
plus new variogram wrong-ρ and Spiegelhalter Z calib kills; leave Pass-2…7
thresholds untouched; no `xh.ts` edit.

**One-line verdict:** KEEP_CANDIDATE — isotonic/joint-LL/Cox + cond-coverage/stratified-ability + variogram/Spiegelhalter deepen calib/xHm without softening Pass-2…7 kills.
