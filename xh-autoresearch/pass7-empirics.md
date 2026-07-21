# Pass-7 EMPIRICS — energy / Winkler / isotonic / joint-LL / Cox / stratified-ability residual

**Verdict: KEEP_CANDIDATE**

Proposal only — **do not** edit `src/engine/xh.ts`, and do not soften Pass-2…6
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
`energyWrongRhoMinGain=0.02`). Deepen residual only in
`scripts/xh-baselines.ts` + `scripts/eval-xh-math.ts` when orchestrator applies.

Expected post-apply: `math_pass_rate=1.0000` with **+8–10** new empirics
asserts (148 → ~156–158), no BASE×ZONE×VISION.

Baseline confirmed: **148/148** (`npm run eval:xh`).

---

## Critique — what Pass-1…6 left shallow

| Gap | Today | Why it bites |
|-----|-------|--------------|
| **Energy score constant dead** | `energyWrongRhoMinGain=0.02` in `KILL_CRITERIA_VS_B1` | Pass-6 proposed I-vector energy; never shipped `binaryEnergyScore` / kill sanity — constant is inert |
| **Coverage ≠ interval score** | Frequency `|cov−(1−α)|` only | Honest coverage can still prefer wide wrong-ρ intervals; Winkler interval score kills width+miss jointly |
| **Parametric calib only** | Temp / Platt / Beta families | Monotone nonparametric isotonic (PAV) catches shape warps those 1–3-param maps miss; gate still uses same `calibrationMinBrierGain` |
| **Count LL ≠ joint LL** | `−log q_K` on K=∑I | Matching count PMF can hide wrong pairwise/joint geometry; multivariate Bernoulli log-score on I refutes ρ=0 when margins match |
| **No Cox reliability regression** | ECE / MCE / Murphy REL | Slope≠1 or intercept≠0 on logit(p̂) vs outcomes is the classical calibration residual; complements bin ECE |
| **Ability kill is global-only** | Single ability key | Strata keys (`ability\|vision\|range`) already exist; residual kill never exercises stratified empirical vs biased corridor |
| **Unconditional PI only** | Global 90% coverage | Mid/high predicted-mean bands can undercover while low-mean bands overcover; tertile-conditional coverage catches it |

Already landed (do **not** re-propose): analytic equicorrelated-probit xHm;
corridor Brier vs coin; ability-rate / Platt / Temp / Beta stubs+fitters;
ρ pairwise+triple MoM; ECE/CRPS/log-loss; online/strata ability hooks;
σ-scale kill; Platt/Temp/Beta held-out gain; MCE/adaptive ECE; wrong-ρ/Var/tail
CRPS; discrete PIT ECE+KS; Murphy REL/RES + identity + BSS; count
log-loss/count-bin ECE; conditional ECE; DSS; central PI coverage;
ability residual kill (global); `KILL_CRITERIA_VS_B1` Pass-2…6 fields
(including inert `energyWrongRhoMinGain`).

---

## Minimal falsifiable math (synthetic OK)

### 1. Energy score on hit-indicator vectors (land Pass-6 debt)

Sample I ∈ {0,1}^n under equicorrelated probit (same latent draw as
`drawXhmCounts` but keep the vector). Energy score with L1 (Hamming):

\[
\mathrm{ES}(P,y)=\mathbb{E}\|X-y\|_1 - \tfrac12\mathbb{E}\|X-X'\|_1
\]

Approximate expectations by M paired draws from the forecast law
(analytic one-factor sampler). Mean ES under ρ★ draws: require
`es(ρ★) + energyWrongRhoMinGain ≤ es(ρ=0)` with existing
`energyWrongRhoMinGain=0.02` — **do not raise or lower**.

Cite: Gneiting & Raftery, JASA 2007 (energy score); scores the joint, not only K.

```ts
export function drawXhmIndicators(
  p: number,
  n: number,
  rho: number,
  seed: number,
): number[] // length-n binary; shares latent Z with count sampler

export function binaryEnergyScore(
  sampleForecast: () => number[], // length-n binary
  y: number[],
  pairedDraws?: number, // default 64
): number

export function xhmWrongRhoEnergyKillSanity(opts: {
  p: number
  n: number
  rhoStar: number
  rhoWrong?: number
  trials?: number
  pairedDraws?: number
}): {
  esStar: number
  esWrong: number
  gain: number
  shouldKillWrongRho: boolean
}
```

### 2. Winkler interval score + wrong-ρ kill

For central (1−α) predictive interval [L,U] from analytic PMF and observed k:

\[
S_\alpha(L,U,k)=(U-L)
  + \tfrac{2}{\alpha}(L-k)\mathbf{1}\{k<L\}
  + \tfrac{2}{\alpha}(k-U)\mathbf{1}\{k>U\}
\]

Mean over ρ★ draws. Contract: `winkler(ρ★) + winklerWrongRhoMinGain ≤ winkler(ρ=0)`
with **new** `winklerWrongRhoMinGain=0.05`. Complements Pass-6 coverage
frequency (do **not** lower `coverageAbsTol`).

Cite: Winkler 1972; Gneiting & Raftery 2007 (interval score).

```ts
export function winklerIntervalScore(
  lo: number,
  hi: number,
  k: number,
  alpha = 0.1,
): number

export function xhmWrongRhoWinklerKillSanity(opts: {
  p: number
  n: number
  rhoStar: number
  rhoWrong?: number
  alpha?: number
  trials?: number
}): {
  winkStar: number
  winkWrong: number
  gain: number
  shouldKillWrongRho: boolean
}
```

### 3. Isotonic (PAV) held-out gain gate

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

### 4. Multivariate Bernoulli joint log-score (I-vector)

For observed y ∈ {0,1}^n and forecast law P_ρ (one-factor probit),

\[
\mathrm{LL}_{\mathrm{joint}} = -\log P_\rho(I=y)
\]

Exact under the model via 1D Gauss mixture:
\(P(I=y)=\mathbb{E}[\prod_j \pi(Z)^{y_j}(1-\pi(Z))^{1-y_j}]\).

Contract: draws from ρ★=0.5 →
`ll_joint(ρ★) + jointLogLossWrongRhoMinGain ≤ ll_joint(ρ=0)` with
`jointLogLossWrongRhoMinGain=0.03`. Do **not** lower
`countLogLossWrongRhoMinGain`.

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

### 5. Cox calibration slope / intercept residual

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

### 6. Tertile-conditional PI coverage

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

### 7. Stratified ability residual kill

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

### 8. Additive kill constants only (never raise Pass-2…6)

```ts
export const KILL_CRITERIA_VS_B1 = {
  // --- Pass-2…6 unchanged (including energyWrongRhoMinGain: 0.02) ---
  // ... existing fields verbatim ...
  // --- Pass-7 deepen ---
  winklerWrongRhoMinGain: 0.05,
  jointLogLossWrongRhoMinGain: 0.03,
  coxSlopeAbsTol: 0.15,
  coxInterceptAbsTol: 0.20,
} as const
```

---

## Exact eval asserts to add (do not weaken existing)

In `scripts/eval-xh-math.ts` (additive block after Pass-6 empirics):

```ts
// --- empirics deepen (Pass-7 EMPIRICS) ---
{
  const es = xhmWrongRhoEnergyKillSanity({
    p: 0.55,
    n: 4,
    rhoStar: 0.5,
    trials: 6000,
    pairedDraws: 64,
  })
  assert(
    'wrong-ρ energy: ρ=0 loses to ρ★ by ≥ energyWrongRhoMinGain',
    es.shouldKillWrongRho,
    `gain=${es.gain.toFixed(3)}`,
  )
  const wk = xhmWrongRhoWinklerKillSanity({
    p: 0.55,
    n: 4,
    rhoStar: 0.5,
    trials: 8000,
  })
  assert(
    'wrong-ρ Winkler: ρ=0 loses to ρ★ by ≥ winklerWrongRhoMinGain',
    wk.shouldKillWrongRho,
    `gain=${wk.gain.toFixed(3)}`,
  )
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
  'Pass-7 kill-criteria deepen fields finite',
  Number.isFinite(KILL_CRITERIA_VS_B1.energyWrongRhoMinGain) &&
    KILL_CRITERIA_VS_B1.winklerWrongRhoMinGain > 0 &&
    KILL_CRITERIA_VS_B1.jointLogLossWrongRhoMinGain > 0 &&
    KILL_CRITERIA_VS_B1.coxSlopeAbsTol > 0 &&
    KILL_CRITERIA_VS_B1.coxInterceptAbsTol > 0,
  JSON.stringify(KILL_CRITERIA_VS_B1),
)
```

Keep all Pass-2…6 Brier / ECE / ρ MoM / σ-scale / Platt / Temp / Beta /
MCE / Var / wrong-ρ CRPS+LL+DSS / Murphy / BSS / PI coverage / count-bin /
triple-ρ / cond ECE / PIT / ability-kill asserts verbatim.

---

## Citations

- Gneiting & Raftery, JASA 2007 — energy score; interval (Winkler) score;
  logarithmic score (joint).
- Winkler, JASA 1972 — interval score.
- Zadrozny & Elkan 2002; Niculescu-Mizil & Caruana, ICML 2005 — isotonic
  calibration (PAV).
- Cox 1958; Miller, Hui, Tierney 1991 — calibration slope/intercept.
- Ochi & Prentice, Biometrika 1984 — equicorrelated probit (I-sampler / joint).
- Pass-2 EMPIRICS: `abilityResidualTol` / `minBrierGainToKill` (reuse on strata).
- Pass-6 EMPIRICS: `energyWrongRhoMinGain` (land implementation; do not change).

---

## Regression / risk

- **Do not** tighten or loosen any Pass-2…6 numeric kill thresholds.
- Energy paired-draw noise: fix seeds; raise `trials`/`pairedDraws` before
  touching `energyWrongRhoMinGain`.
- Winkler: build intervals from **forecast** PMF (ρ under test), not from
  empirical quantiles of draws — otherwise wrong-ρ comparison collapses.
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
- Energy / Winkler / isotonic / joint-LL / Cox / stratified-ability stay
  baselines-only — never multiply into `estimateXh` (no BASE×ZONE×VISION).
- No production `xh.ts` change this pass.

---

## Decision

**KEEP_CANDIDATE** — deepen empirics by landing the dead energy-score kill,
adding Winkler interval + joint Bernoulli LL wrong-ρ kills, isotonic + Cox
calibration gates, tertile-conditional PI coverage, and stratified ability
residual kill; leave Pass-2…6 thresholds untouched; no `xh.ts` edit.

**One-line verdict:** KEEP_CANDIDATE — energy/Winkler/joint-LL + isotonic/Cox + stratified-ability deepen calibration/xHm without softening Pass-2…6 kills.
