# Pass-4 EMPIRICS — calibration residual / multi-hit CRPS–ρ residual

**Verdict: KEEP_CANDIDATE**

Proposal only — **do not** edit `src/engine/xh.ts`, and do not soften Pass-2/3
kill thresholds (`corridorRateTol=0.03`, `brierVsCoinMaxRatio=1.15`,
`abilityResidualTol=0.08`, `minBrierGainToKill=0.01`,
`calibrationMinBrierGain=0.005`, `rhoAbsErrTol=0.05`, `eceTol=0.025`,
`logLossVsCoinMaxRatio=1.2`, `sigmaScaleRelTol=0.08`,
`sigmaScaleMinBrierGain=0.005`). Deepen residual only in
`scripts/xh-baselines.ts` + `scripts/eval-xh-math.ts` when orchestrator applies.

Expected post-apply: `math_pass_rate=1.0000` with **+8–10** new empirics
asserts (88 → ~96–98), no BASE×ZONE×VISION.

Baseline confirmed: **88/88** (`npm run eval:xh`).

---

## Critique — what Pass-1…3 left shallow

| Gap | Today | Why it bites |
|-----|-------|--------------|
| **Platt/T fit gate unexercised** | Identity stubs only; `calibrationMinBrierGain` never fires | Cannot refute a miscalibrated logit map; gate is dead code until synthetic fitter exists |
| **ECE is equal-width only** | Global ECE ≤ 0.025 | Mid-bin bias + empty tails can hide max-bin error (MCE); adaptive bins catch sparse extremes |
| **No deliberate miscalibration kill** | Correct Φ always passes | Need negative control: biased p̂ (e.g. +0.12) must trip ECE/Brier while true corridor stays green |
| **ρ MoM is pairwise-only** | `|ρ̂−ρ★|≤0.05` on π₁₁ | Teamfight xHm cares about Var(K) / P(K=0),P(K=n); wrong ρ can match π₁₁ yet miss overdispersion |
| **CRPS mean-only** | `meanCrps(dep) ≤ meanCrps(indep)` | Does not kill a **wrong-ρ** analytic PMF; wipe-tail residual (k=0 / k=n) unchecked |
| **No discrete count reliability** | Binary ECE only | xHm needs PIT / count-bin ECE so multi-hit forecast is calibrated as a distribution |

Already landed (do **not** re-propose): analytic equicorrelated-probit xHm;
corridor Brier vs coin; ability-rate / Platt / temperature stubs; ρ MoM;
ECE/CRPS/log-loss; online/strata ability hooks; σ-scale kill probes;
`KILL_CRITERIA_VS_B1` Pass-2+3 fields.

---

## Minimal falsifiable math (synthetic OK)

### 1. Synthetic Platt / temperature fit + held-out gain gate

Generate corridor draws with true p★ = Φ-corridor; corrupt predictions to
`p_raw = clip(p★ + bias)` (or `temperatureScale(p★, T≠1)`). Fit affine logit
`(â,b̂)` by Newton / grid on train split; apply `plattScale` on held-out.

**Contracts (additive):**

- Identity raw corridor: held-out Brier gain of fitted Platt ≤ `calibrationMinBrierGain`
  → **do not apply** (gate green / no-op).
- Biased raw (`bias=+0.12`): fitted Platt Brier gain ≥ `calibrationMinBrierGain`
  → apply allowed; post-Platt `|rate−p̂|` back within `corridorRateTol`.

Cite: Platt 1999; Guo et al. ICML 2017. Do **not** lower `calibrationMinBrierGain`.

```ts
export function fitPlattLogit(
  preds: number[],
  outcomes: number[],
): { a: number; b: number }

export function plattHeldOutGainSanity(opts: {
  cells: Array<{ R: number; mu: number; sigma: number }>
  bias?: number // default 0 — identity path
  trainFrac?: number
  trialsPerCell?: number
}): {
  rawBrier: number
  calibratedBrier: number
  gain: number
  shouldApply: boolean // gain >= calibrationMinBrierGain
  a: number
  b: number
}
```

### 2. MCE + adaptive-bin ECE (complement equal-width)

| Metric | Definition | Synthetic kill |
|--------|------------|----------------|
| **MCE** | max_b \|acc_b − conf_b\| over occupied equal-width bins | true corridor ≤ **0.06** (looser than ECE; catches single bad bin) |
| **Adaptive ECE** | equal-*count* quantile bins (B=10) | ≤ `eceTol` (same 0.025 — do not raise) |

Biased p̂ (+0.12) must yield `ece > eceTol` **or** `mce > mceTol`.

```ts
export function maxCalibrationError(
  preds: number[],
  outcomes: number[],
  bins = 10,
): number

export function adaptiveEce(
  preds: number[],
  outcomes: number[],
  bins = 10,
): number

export function corridorMiscalibrationKillSanity(opts: {
  cells: Array<{ R: number; mu: number; sigma: number }>
  bias: number
  trialsPerCell?: number
}): { ece: number; mce: number; shouldKill: boolean }
```

### 3. Multi-hit residual: Var(K) MoM + wrong-ρ CRPS + tail CRPS

Under equicorrelated probit:

\[
\mathrm{Var}(K)=np(1-p)+n(n-1)(\Phi_2(c,c;\rho)-p^2).
\]

**Var residual:** draw n=4, ρ★=0.5, p=0.55; compare empirical var to
`analyticXhmMoments`. Require `|var̂/var★ − 1| ≤ varRelTol` (**0.08**).

**Wrong-ρ CRPS kill:** same draws; score analytic PMF at ρ_wrong=0 vs ρ★.
Require `meanCrps(ρ★) + crpsWrongRhoMinGain ≤ meanCrps(ρ_wrong)` with
`crpsWrongRhoMinGain=0.02`. This kills “independence pretending to be fine”
when dependence is real — complementary to Pass-3’s dep≤indep direction check.

**Tail CRPS:** restrict draws to empirical mass near k∈{0,n}; mean CRPS of
dependent PMF ≤ indep on those tails (or use analytic P0/Pn Brier on
indicators 1{K=0}, 1{K=n}).

```ts
export function xhmVarResidualSanity(opts: {
  p: number
  n: number
  rhoStar: number
  trials?: number
}): { varHat: number; varStar: number; relErr: number; ok: boolean }

export function xhmWrongRhoCrpsKillSanity(opts: {
  p: number
  n: number
  rhoStar: number
  rhoWrong?: number // default 0
  trials?: number
}): {
  crpsStar: number
  crpsWrong: number
  gain: number
  shouldKillWrongRho: boolean
}

export function xhmTailCrpsSanity(opts: {
  p: number
  n: number
  rhoStar: number
  trials?: number
}): { crpsDepTail: number; crpsIndepTail: number; ok: boolean }
```

### 4. Discrete PIT / count reliability for xHm

For each draw k, use randomized PIT: \(U = F(k-1) + V\cdot q(k)\), V~U(0,1)
(Czado–Gneiting–Held). Under correct PMF, U ~ Unif(0,1); bin into B=10,
require ECE_PIT ≤ **0.04** (slightly looser than binary `eceTol` — discrete +
randomization noise). Wrong-ρ PMF must fail ECE_PIT or exceed that tol.

Cite: Czado, Gneiting, Held, Biometrics 2009 (discrete PIT); Hersbach 2000.

```ts
export function discretePitEce(
  pmf: number[],
  draws: number[],
  bins = 10,
  seed?: number,
): { ece: number; ok: boolean }
```

### 5. Additive kill constants only (never raise Pass-2/3)

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
  // --- Pass-4 deepen ---
  mceTol: 0.06,
  varRelTol: 0.08,
  crpsWrongRhoMinGain: 0.02,
  pitEceTol: 0.04,
} as const
```

---

## Eval asserts to add (do not weaken existing)

In `scripts/eval-xh-math.ts` (additive):

1. `Platt gate: identity corridor gain < calibrationMinBrierGain (no-op)`
2. `Platt gate: biased +0.12 gain ≥ calibrationMinBrierGain`
3. `MCE: true corridor synthetic ≤ mceTol`
4. `adaptive ECE: true corridor ≤ eceTol`
5. `miscal kill: bias=+0.12 trips ECE or MCE`
6. `xHm Var MoM: |var̂/var★−1| ≤ varRelTol at ρ★=0.5`
7. `wrong-ρ CRPS: ρ=0 loses to ρ★ by ≥ crpsWrongRhoMinGain`
8. `tail CRPS: dep ≤ indep on {K=0}∪{K=n} mass`
9. `PIT ECE: correct xHm PMF ≤ pitEceTol`
10. `PIT ECE: wrong ρ=0 exceeds pitEceTol (or > correct)`

Keep all Pass-2/3 Brier / ECE / ρ MoM / σ-scale / ability asserts verbatim.

---

## Citations

- Platt 1999 — sigmoid calibration; held-out gain gate.
- Guo et al., ICML 2017 — temperature scaling + reliability.
- Naeini et al., AAAI 2015 — ECE; MCE as max-bin companion.
- Gneiting & Raftery, JASA 2007 — proper scores (Brier / CRPS family).
- Hersbach 2000 — CRPS; tail emphasis via indicator restriction.
- Ochi & Prentice, Biometrika 1984 — Var(K) / Φ₂ for equicorrelated probit.
- arXiv:2403.02194 — Gaussian-copula bivariate Bernoulli (ρ MoM context).
- Czado, Gneiting, Held, Biometrics 2009 — randomized PIT for count forecasts.
- Pass-3 EMPIRICS: ρ MoM + ECE/CRPS/log-loss + σ-scale probes (do not re-land).

---

## Regression / risk

- **Do not** tighten Pass-2 `corridorRateTol` / `brierVsCoinMaxRatio` or Pass-3
  `eceTol` / `rhoAbsErrTol`.
- Platt Newton must clamp preds to `[1e-9,1−1e-9]`; singular Hessian → fall back
  to grid on `(a,b)`.
- Adaptive ECE needs ≥B non-empty quantile bins — use N≥1e4 synthetic draws.
- Wrong-ρ CRPS gain is **one-sided** (star beats wrong); do not require indep to
  beat dep (Pass-3 already covers that direction).
- Var residual uses same LCG/Box–Muller family as `rhoRecoverySanity` for
  reproducibility; raise `trials` (≥8e3) before blaming the model.
- PIT randomization needs fixed seed in eval or assert becomes flaky.
- Strata / ability / σ-scale machinery stays baselines-only — never multiply into
  `estimateXh` (no BASE×ZONE×VISION).
- No production `xh.ts` change this pass; analytic xHm replace of MC remains a
  deferred Pass-1 KEEP.

---

## Decision

**KEEP_CANDIDATE** — deepen empirics with Platt held-out gain gate, MCE/adaptive
ECE + miscalibration negative control, xHm Var MoM, wrong-ρ/tail CRPS residual,
and discrete PIT count reliability; leave Pass-2/3 thresholds untouched; no
`xh.ts` edit.

**One-line verdict:** KEEP_CANDIDATE — Platt gain + MCE/PIT + wrong-ρ/Var CRPS residuals deepen calibration/xHm without softening Pass-2/3 kills.
