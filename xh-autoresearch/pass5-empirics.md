# Pass-5 EMPIRICS — temperature / Murphy / count-score / higher-order ρ residual

**Verdict: KEEP_CANDIDATE**

Proposal only — **do not** edit `src/engine/xh.ts`, and do not soften Pass-2/3/4
kill thresholds (`corridorRateTol=0.03`, `brierVsCoinMaxRatio=1.15`,
`abilityResidualTol=0.08`, `minBrierGainToKill=0.01`,
`calibrationMinBrierGain=0.005`, `rhoAbsErrTol=0.05`, `eceTol=0.025`,
`logLossVsCoinMaxRatio=1.2`, `sigmaScaleRelTol=0.08`,
`sigmaScaleMinBrierGain=0.005`, `mceTol=0.06`, `varRelTol=0.08`,
`crpsWrongRhoMinGain=0.02`, `pitEceTol=0.04`). Deepen residual only in
`scripts/xh-baselines.ts` + `scripts/eval-xh-math.ts` when orchestrator applies.

Expected post-apply: `math_pass_rate=1.0000` with **+8–10** new empirics
asserts (103 → ~111–113), no BASE×ZONE×VISION.

Baseline confirmed: **103/103** (`npm run eval:xh`).

---

## Critique — what Pass-1…4 left shallow

| Gap | Today | Why it bites |
|-----|-------|--------------|
| **Temperature fit gate dead** | `temperatureScale` identity-only; Pass-4 exercised Platt affine | 1-param Guo temperature is the usual first post-hoc step; gate never fires on T≠1 corruption |
| **Brier is aggregate only** | mean Brier + coin ratio | Flat climatology can look “calibrated” while resolution≈0; need Murphy REL/RES/UNC split |
| **Count log-score unused** | CRPS + binary log-loss only | Wrong-ρ can pass CRPS gain yet fail strictly proper count log-loss (−log q_k) |
| **No categorical count ECE** | PIT histogram uniformity only | Uniform PIT ≠ reliable P(K=k); need equal-width count-bin \|freq−q_k\| ECE |
| **ρ MoM is pairwise-only** | \|ρ̂−ρ★\| on π₁₁ + Var(K) | Triple joint π₁₁₁ can refute a ρ that matches pairs; teamfight wipe mass is higher-order |
| **Conditional ECE absent** | Global / adaptive ECE | Mid-p̂ cells can hide high-σ miscalibration; tertile-conditional ECE catches it |
| **PIT KS unused** | Binned PIT ECE only | Continuous KS on randomized PIT is a sharper uniformity kill than 10-bin mean abs |

Already landed (do **not** re-propose): analytic equicorrelated-probit xHm;
corridor Brier vs coin; ability-rate / Platt / temperature *stubs*; ρ MoM;
ECE/CRPS/log-loss; online/strata ability hooks; σ-scale kill; Platt held-out
gain; MCE/adaptive ECE; wrong-ρ/Var/tail CRPS; discrete PIT ECE;
`KILL_CRITERIA_VS_B1` Pass-2…4 fields.

---

## Minimal falsifiable math (synthetic OK)

### 1. Synthetic temperature fit + held-out gain gate

Corrupt closed-form corridor preds with `temperatureScale(p★, T_corrupt≠1)`
(e.g. T=1.6). Fit `T̂` by 1D grid on train (minimize Brier); apply
`temperatureScale` on held-out.

**Contracts (additive):**

- Identity (T=1 raw): held-out Brier gain ≤ `calibrationMinBrierGain` → **no-op**
  (reuse Pass-2 gate — do **not** lower it).
- Corrupt T=1.6: gain ≥ `calibrationMinBrierGain` → apply allowed; post-temp
  ECE ≤ `eceTol`.

Cite: Guo et al. ICML 2017. Complements Pass-4 Platt (2-param) with the
standard 1-param path.

```ts
export function fitTemperature(
  preds: number[],
  outcomes: number[],
): number // T̂ on grid ∈ [0.5, 3]

export function temperatureHeldOutGainSanity(opts: {
  cells: Array<{ R: number; mu: number; sigma: number }>
  corruptT?: number // default 1 — identity path
  trainFrac?: number
  trialsPerCell?: number
}): {
  rawBrier: number
  calibratedBrier: number
  gain: number
  shouldApply: boolean
  T: number
}
```

### 2. Murphy Brier decomposition (REL / RES / UNC)

For equal-width bins (B=10), Murphy (1973):

\[
\mathrm{BS} = \underbrace{\tfrac{1}{N}\sum_b n_b(\mathrm{conf}_b-\mathrm{acc}_b)^2}_{\mathrm{REL}}
  - \underbrace{\tfrac{1}{N}\sum_b n_b(\mathrm{acc}_b-\bar y)^2}_{\mathrm{RES}}
  + \underbrace{\bar y(1-\bar y)}_{\mathrm{UNC}}.
\]

**Synthetic kill:** true corridor → `REL ≤ murphyRelTol` (**0.02**) and
`RES ≥ murphyMinRes` (**0.01**). Constant-p̂ climatology (always predict
global rate) must have `RES ≈ 0` (≤ murphyMinRes) while true corridor
resolves above that floor.

Cite: Murphy, J. Appl. Meteor. 1973; Brocker–Smith 2007.

```ts
export function murphyBrierDecomposition(
  preds: number[],
  outcomes: number[],
  bins = 10,
): { rel: number; res: number; unc: number; brier: number }

export function corridorMurphySanity(opts: {
  cells: Array<{ R: number; mu: number; sigma: number }>
  trialsPerCell?: number
}): { rel: number; res: number; ok: boolean; climRes: number }
```

### 3. Count log-score + wrong-ρ kill (complement CRPS)

For observed k and PMF q: \(\mathrm{LL} = -\log q_k\) (clamp q_k≥1e-12).
Mean count log-loss on ρ★ draws: require
`ll(ρ★) + countLogLossWrongRhoMinGain ≤ ll(ρ_wrong=0)` with
`countLogLossWrongRhoMinGain=0.02` (same spirit as `crpsWrongRhoMinGain` —
do **not** lower CRPS gain).

Cite: Gneiting & Raftery 2007 (logarithmic score).

```ts
export function countLogLoss(pmf: number[], draws: number[]): number

export function xhmWrongRhoLogLossKillSanity(opts: {
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

### 4. Count-bin categorical ECE for xHm

Given draws from ρ★ and forecast PMF q, form empirical freq \(\hat f_k\) and

\[
\mathrm{ECE}_{\mathrm{count}} = \sum_{k=0}^{n} \tfrac{1}{n+1}\,|\hat f_k - q_k|.
\]

Correct PMF: ≤ `countBinEceTol` (**0.05**). Wrong ρ=0: exceeds tol **or**
> correct + 0.01.

Distinct from Pass-4 PIT (uniformity of randomized CDF transforms).

```ts
export function countBinEce(
  pmf: number[],
  draws: number[],
): { ece: number; ok: boolean }
```

### 5. Triple-wise π₁₁₁ → ρ consistency

Under equicorrelated probit,

\[
\pi_{111}=\mathbb{E}\!\left[\Phi\!\big((c-\sqrt{\rho}Z)/\sqrt{1-\rho}\big)^3\right].
\]

Invert π₁₁₁ for ρ̂₃ (bisection on analytic triple joint); synthetic ρ★=0.5,
n_triples≥2e4 → `|ρ̂₃−ρ★| ≤ tripleRhoAbsErrTol` (**0.08**, looser than
pairwise 0.05 — cubic tails noisier). Also: |ρ̂₃ − ρ̂_pairwise| ≤ 0.06 on
same draws (consistency).

Cite: Ochi & Prentice 1984 (higher-order equicorrelated moments).

```ts
export function analyticTripleJoint(p: number, rho: number): number

export function estimateRhoFromTripleJoint(p: number, pi111: number): number

export function rhoTripleRecoverySanity(opts: {
  p: number
  rhoStar: number
  nTriples?: number
  seed?: number
}): { rhoHat3: number; rhoHat2: number; absErr3: number; ok: boolean }
```

### 6. Conditional ECE by p̂ tertiles + PIT KS

Split synthetic corridor preds into tertiles by p̂; each tertile ECE ≤
`conditionalEceTol` (**0.04**). Biased +0.12 must fail ≥1 tertile.

Randomized PIT U_i: one-sample KS statistic
\(D_n=\sup|F_n(u)-u|\); correct PMF → D_n ≤ `pitKsTol` (**0.05**) at
N≥5e3; wrong ρ=0 exceeds or > correct + 0.01.

Cite: Czado–Gneiting–Held 2009; Massey 1951 (KS).

```ts
export function conditionalEceByTertile(
  preds: number[],
  outcomes: number[],
): { eces: number[]; ok: boolean }

export function discretePitKs(
  pmf: number[],
  draws: number[],
  seed?: number,
): { ks: number; ok: boolean }
```

### 7. Additive kill constants only (never raise Pass-2/3/4)

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
  // --- Pass-5 deepen ---
  murphyRelTol: 0.02,
  murphyMinRes: 0.01,
  countLogLossWrongRhoMinGain: 0.02,
  countBinEceTol: 0.05,
  tripleRhoAbsErrTol: 0.08,
  conditionalEceTol: 0.04,
  pitKsTol: 0.05,
} as const
```

---

## Eval asserts to add (do not weaken existing)

In `scripts/eval-xh-math.ts` (additive):

1. `Temp gate: identity corridor gain < calibrationMinBrierGain (no-op)`
2. `Temp gate: corrupt T=1.6 gain ≥ calibrationMinBrierGain`
3. `Murphy: true corridor REL ≤ murphyRelTol and RES ≥ murphyMinRes`
4. `Murphy: climatology RES < murphyMinRes (no resolution)`
5. `wrong-ρ count log-loss: ρ=0 loses to ρ★ by ≥ countLogLossWrongRhoMinGain`
6. `count-bin ECE: correct xHm PMF ≤ countBinEceTol`
7. `count-bin ECE: wrong ρ=0 exceeds (or > correct)`
8. `ρ triple MoM: recover ρ★=0.5 within tripleRhoAbsErrTol`
9. `conditional ECE: true corridor tertiles ≤ conditionalEceTol`
10. `PIT KS: correct ≤ pitKsTol; wrong ρ=0 fails or worse`

Keep all Pass-2/3/4 Brier / ECE / ρ MoM / σ-scale / Platt / MCE / Var /
wrong-ρ CRPS / PIT ECE asserts verbatim.

---

## Citations

- Guo et al., ICML 2017 — temperature scaling + reliability (1-param fit gate).
- Platt 1999 — sigmoid calibration (Pass-4; leave gain threshold untouched).
- Murphy, J. Appl. Meteor. 12:595–600 (1973) — Brier REL/RES/UNC decomposition.
- Gneiting & Raftery, JASA 2007 — logarithmic score + CRPS as proper scores.
- Ochi & Prentice, Biometrika 1984 — equicorrelated probit higher-order joints.
- Czado, Gneiting, Held, Biometrics 2009 — randomized PIT; KS companion.
- Naeini et al., AAAI 2015 — ECE; conditional/tertile reliability.
- Pass-4 EMPIRICS: Platt/MCE/PIT/wrong-ρ/Var (do not re-land).

---

## Regression / risk

- **Do not** tighten Pass-2 `corridorRateTol` / `brierVsCoinMaxRatio`, Pass-3
  `eceTol` / `rhoAbsErrTol`, or Pass-4 `mceTol` / `pitEceTol` /
  `crpsWrongRhoMinGain` / `varRelTol`.
- Temperature grid must clamp preds to `[1e-9,1−1e-9]`; T̂ search ∈ [0.5, 3].
- Murphy RES floor is a **positive** control — do not confuse with REL tol.
- Triple MoM needs more trials than pairwise; raise `nTriples` (≥2e4) before
  blaming the analytic integral.
- Count log-loss clamp avoids −∞ on empty PMF bins from coarse quadrature.
- PIT KS uses fixed seed; flaky asserts → raise N, not `pitKsTol`.
- Strata / ability / σ-scale / temp / Platt stay baselines-only — never
  multiply into `estimateXh` (no BASE×ZONE×VISION).
- No production `xh.ts` change this pass.

---

## Decision

**KEEP_CANDIDATE** — deepen empirics with temperature held-out gain, Murphy
REL/RES, count log-loss + count-bin ECE, triple-wise ρ MoM, conditional ECE,
and PIT KS; leave Pass-2/3/4 thresholds untouched; no `xh.ts` edit.

**One-line verdict:** KEEP_CANDIDATE — temp/Murphy + count log-score/ECE + triple-ρ/PIT-KS deepen calibration/xHm without softening Pass-2/3/4 kills.
