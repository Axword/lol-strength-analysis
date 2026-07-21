# Pass-3 EMPIRICS — ρ recovery / reliability / σ-scale kill

**Verdict: KEEP_CANDIDATE**

Proposal only — **do not** edit `src/engine/xh.ts`, and do not soften Pass-2
kill thresholds (`corridorRateTol=0.03`, `brierVsCoinMaxRatio=1.15`,
`abilityResidualTol=0.08`, `minBrierGainToKill=0.01`,
`calibrationMinBrierGain=0.005`). Deepen residual only in
`scripts/xh-baselines.ts` + `scripts/eval-xh-math.ts` when orchestrator applies.

Expected post-apply: `math_pass_rate=1.0000` with **+8–10** new empirics
asserts (65 → ~73–75), no BASE×ZONE×VISION.

---

## Critique — what Pass-1/2 left shallow

| Gap | Today | Why it bites |
|-----|-------|--------------|
| **ρ estimation** | `estimateXhm(..., rho=0.45)` hardcoded; moments check *direction* only | Wrong ρ misprices teamfight multi-hit / wipe tails; no estimator to refute 0.45 |
| **Ability-conditional rates** | Flat `hits/casts` stub, no strata | B1 kill needs ability×vision×range residual — global rate alone is confounded |
| **Reliability diagram / ECE** | Cell-mean `|rate−p̂|` only | Passes while mid-bins overconfident and tails underconfident |
| **Proper scores beyond Brier** | Brier + coin ratio only | Log-loss / CRPS catch sharp miscalibration Brier forgives; xHm needs count score |
| **Online update hooks** | `registerAbilityRate` overwrite | No sequential posterior / EWMA contract for streaming cast→hit |
| **σ-scale kill** | Kill whole B1 corridor prior | Need *which* κ (aim / juke / belief) fails when μ,R known and Φ is correct |

Already landed (do **not** re-propose): analytic equicorrelated-probit xHm;
corridor Brier vs coin; ability-rate / Platt / temperature stubs; `KILL_CRITERIA_VS_B1`.

---

## Minimal falsifiable math (synthetic OK)

### 1. Method-of-moments ρ̂ from pairwise Φ₂

Under the Pass-1 model, pairwise joint hit rate is

\[
\pi_{11}=\Phi_2(c,c;\rho)=\mathbb{E}\!\left[\Phi\!\big((c-\sqrt{\rho}Z)/\sqrt{1-\rho}\big)^2\right],\quad c=\Phi^{-1}(p).
\]

Invert numerically: given empirical \(\hat\pi_{11}\) (or from synthetic draws),
solve \(\rho\in[0,0.95]\) for \(\Phi_2(c,c;\rho)=\hat\pi_{11}\).

**Falsify without VOD logs:** draw equicorrelated Bernoulli at known ρ★,
recover ρ̂ within `|ρ̂−ρ★|≤0.05` (n_pairs≥2e4). Cite Ochi & Prentice 1984;
tetrachoric / Gaussian-copula Bernoulli — arXiv:2403.02194.

```ts
/** Invert Φ₂(c,c;ρ)=π11 for ρ (bisection). */
export function estimateRhoFromPairwiseJoint(
  p: number,
  pi11: number,
  tol = 1e-4,
): number {
  const c = invNorm(p)
  const loBound = Math.max(p * p, 1e-12)
  const hiBound = Math.min(p, 1 - 1e-12) // Frechet–Hoeffding
  const target = Math.min(hiBound, Math.max(loBound, pi11))
  let lo = 0, hi = 0.95
  for (let i = 0; i < 48; i++) {
    const mid = 0.5 * (lo + hi)
    const m = analyticXhmMoments(p, 2, mid)
    if (m.pairwiseJoint < target) lo = mid
    else hi = mid
    if (hi - lo < tol) break
  }
  return 0.5 * (lo + hi)
}

/** Synthetic: generate ρ★ → empirical π11 → ρ̂. */
export function rhoRecoverySanity(opts: {
  p: number
  rhoStar: number
  nPairs?: number
  seed?: number
}): { rhoHat: number; absErr: number; ok: boolean } {
  // ... LCG Box–Muller shared Z, independent ε_j; I_j = 1{√ρ Z + √(1−ρ)ε < c}
  // pi11 = mean(I1*I2); rhoHat = estimateRhoFromPairwiseJoint(p, pi11)
  // ok = |rhoHat - rhoStar| <= 0.05
}
```

### 2. Reliability diagram + ECE (corridor)

Bin predicted p̂ into B equal-width bins; ECE = Σ (|B_b|/N) |acc_b − conf_b|.
Synthetic: draw from true corridor Φ, predict same closed form → ECE ≤ **0.025**
(B=10, N≥1e4). Complements Pass-2 maxAbsRateGap without tightening it.

Cite: Naeini et al. AAAI 2015 (ECE); Guo et al. ICML 2017 (reliability).

```ts
export function expectedCalibrationError(
  preds: number[],
  outcomes: number[],
  bins = 10,
): { ece: number; diagram: Array<{ conf: number; acc: number; n: number }> }

export function corridorReliabilitySanity(opts: {
  cells: Array<{ R: number; mu: number; sigma: number }>
  trialsPerCell?: number
  bins?: number
  eceTol?: number // default 0.025 — do NOT raise corridorRateTol
}): { ece: number; ok: boolean; diagram: ... }
```

### 3. Strictly proper scores beyond Brier

| Score | Use | Synthetic kill |
|-------|-----|----------------|
| **Log loss** | −y log p − (1−y)log(1−p) | model ≤ coin×1.20 (slightly looser than Brier 1.15; log-loss noisier) |
| **CRPS** (xHm) | for count PMF q vs observed k: Σ_m (F(m)−1{k≤m})² | analytic PMF CRPS ≤ indep Bin CRPS when ρ★>0 on overdispersed draws |

Cite: Gneiting & Raftery, JASA 2007 (proper scoring); Hersbach 2000 (CRPS).

```ts
export function logLoss(preds: number[], outcomes: number[]): number
export function crpsFromPmfs(pmf: number[], k: number): number
export function meanCrpsCount(
  pmf: number[],
  draws: number[],
): number // mean CRPS over observed counts
```

Do **not** replace Brier kill rows — add parallel asserts.

### 4. Ability-conditional rates + online hooks

Strata key = `ability|vision|rangeBand`. Shrinkage toward global via Beta prior
(Jeffreys α=β=0.5) so empty strata → fallback without inventing BASE×ZONE×VISION
multipliers (rates are empirical competitors, not σ factors).

Online: `updateAbilityRate(key, hit: 0|1)` increments hits/casts (conjugate Beta);
optional EWMA `rate ← (1−λ)rate + λ hit` with λ∈(0,1). Contract:
after N i.i.d. Bern(p) updates, `|rate−p|≤3√(p(1−p)/N)`.

```ts
export function abilityRateKey(
  ability: string,
  strata?: { vision?: string; rangeBand?: string },
): string // "LuxQ|mutual|mid"

export function updateAbilityRate(key: string, hit: 0 | 1): AbilityRateEntry
export function abilityRatePosterior(
  key: string,
  priorA = 0.5,
  priorB = 0.5,
): { mean: number; n: number; source: 'empirical' | 'prior' }
```

### 5. When to kill a **σ scale** (not whole B1)

Isolate: fix known (R, μ), generate M~N(μ, σ★²), predict with `corridorHitProb(R,μ,σ_model)`.

| Case | Action |
|------|--------|
| `|σ_model − σ★|/σ★ ≤ 0.08` and ECE/Brier pass | Keep κ scales |
| Rate gap > `corridorRateTol` **or** ECE > 0.025 while Φ form correct | **Kill offending σ scale** (refit κ_aim / κ_juke / κ_belief), not the Φ corridor |
| After scale refit, held-out Brier gain < `calibrationMinBrierGain` | Keep prior κ; do not apply |
| Ability residual kill (Pass-2) still fires | Prefer ability tables **over** σ refit if ability Brier gain ≥ `minBrierGainToKill` |

Extend constants (**additive only** — never raise Pass-2 thresholds):

```ts
export const KILL_CRITERIA_VS_B1 = {
  // --- Pass-2 (unchanged) ---
  corridorRateTol: 0.03,
  brierVsCoinMaxRatio: 1.15,
  abilityResidualTol: 0.08,
  minBrierGainToKill: 0.01,
  calibrationMinBrierGain: 0.005,
  // --- Pass-3 deepen ---
  rhoAbsErrTol: 0.05,
  eceTol: 0.025,
  logLossVsCoinMaxRatio: 1.2,
  sigmaScaleRelTol: 0.08, // |σ̂/σ★ − 1| beyond this → kill that κ
  sigmaScaleMinBrierGain: 0.005, // same spirit as Platt gate
} as const
```

Synthetic σ-scale probe:

```ts
export function sigmaScaleKillSanity(opts: {
  R: number; mu: number; sigmaStar: number
  sigmaModel: number // intentionally wrong vs star
  trials?: number
}): {
  rateGap: number
  shouldKillScale: boolean // rateGap > corridorRateTol OR ece > eceTol
}
```

---

## Eval asserts to add (do not weaken existing)

In `scripts/eval-xh-math.ts` (additive):

1. `ρ MoM: recover ρ★=0.5 within rhoAbsErrTol`
2. `ρ MoM: recover ρ★=0.2 within rhoAbsErrTol`
3. `ρ→0: pairwise joint ≈ p²` (sanity on Φ₂ invert edge)
4. `reliability ECE: corridor synthetic ≤ eceTol`
5. `log-loss: model ≤ coin×logLossVsCoinMaxRatio`
6. `CRPS: dependent xHm ≤ indep on overdispersed draws (ρ★=0.5)`
7. `online ability update: N=400 Bern(0.6) → |rate−0.6|≤0.08`
8. `strata key: LuxQ|blind|long ≠ LuxQ global until registered`
9. `σ-scale kill: wrong σ (1.5×) trips shouldKillScale`
10. `σ-scale keep: σ_model=σ★ does not trip; Pass-2 rateTol still holds`

Keep all Pass-2 Brier / identity / kill-constant asserts verbatim.

---

## Citations

- Ochi & Prentice, Biometrika 71(3):531–543 (1984) — equicorrelated probit moments / Φ₂.
- arXiv:2403.02194 — Gaussian-copula bivariate Bernoulli / dependence.
- arXiv:2606.27288 — single-factor co-failure floor intuition.
- Gneiting & Raftery, JASA 102(477):359–378 (2007) — strictly proper scoring rules.
- Hersbach, Weather & Forecasting 15:559–570 (2000) — CRPS.
- Naeini, Cooper, Hauskrecht, AAAI 2015 — ECE / reliability diagrams.
- Guo et al., ICML 2017 — temperature scaling + reliability.
- Platt 1999 — sigmoid calibration (Pass-2; apply gate unchanged).
- Dawid 1982 / Beta-Binomial conjugate — online rate updates.

---

## Regression / risk

- **Do not** tighten `corridorRateTol` below 0.03 or `brierVsCoinMaxRatio` below 1.15 without raising `trials` (Pass-2 risk note stands).
- ρ bisection must clamp π₁₁ to Frechet–Hoeffding `[p², p]` or empty bins yield NaN.
- Log-loss blows up at p∈{0,1} — clamp preds to `[1e-9,1−1e-9]` like Platt stubs.
- CRPS assert uses **analytic** `estimateXhm` / `analyticXhmPmfs` PMF vs synthetic dependent draws — not MC noise.
- Strata rates must stay **baselines**, never multiply into `estimateXh` (no BASE×ZONE×VISION resurrection).
- σ-scale kill is a **diagnostics contract** until cast logs exist; only synthetic probe gates `math_pass_rate`.

---

## Decision

**KEEP_CANDIDATE** — deepen empirics with ρ MoM recovery, ECE/reliability, log-loss+CRPS, online/strata ability hooks, and per-σ-scale kill probes; leave Pass-2 thresholds untouched; no `xh.ts` edit.

**One-line verdict:** KEEP_CANDIDATE — ρ MoM + ECE/CRPS + σ-scale kill probes deepen calibration without softening Pass-2 criteria.
