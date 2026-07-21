# Pass-1 EMPIRICS — calibration / xHm dependence / scoring

**Verdict: KEEP_CANDIDATE**

Eval after this pass (existing checks preserved + 3 new extreme-cell asserts):
`math_pass_rate=1.0000` (includes prior corridor/geo/aim checks plus new xHm P0/Pn inflation).

`src/engine/xh.ts` was **not** edited (EMPIRICS constraint). Proposal below is for a later apply pass.

---

## What is wrong / shallow today

1. **`estimateXhm` is MC-only** (LCG + invNorm, ≤4000 trials). Moments are noisy; no closed form; hard to score against analytic invariants.
2. **Eval only checked mean + Var↑**. That is necessary but not sufficient for positive dependence: an overdispersed mixture can inflate variance while **under**-pricing joint miss / joint hit.
3. **No calibration score** on the 1D corridor model `P(|M−μ|<R)` vs synthetic Gaussian draws (Brier / rate gap).

---

## Shared-latent model (matches production)

\[
I_j=\mathbf{1}\{\sqrt{\rho}\,Z+\sqrt{1-\rho}\,\varepsilon_j < c\},\quad
c=\Phi^{-1}(p),\quad Z,\varepsilon_j\sim N(0,1)\ \mathrm{iid}
\]

This is the **equicorrelated multivariate probit** / single-factor Gaussian copula (Ochi & Prentice, *Biometrika* 1984; Gaussian-copula Bernoulli — e.g. arXiv:2403.02194; co-failure / single-factor intuition — arXiv:2606.27288).

### Analytic moments (exact under the model)

| Object | Formula |
|--------|---------|
| \(\mathbb{E}[K]\) | \(np\) |
| \(\mathrm{Var}(K)\) | \(np(1-p)+n(n-1)(\Phi_2(c,c;\rho)-p^2)\) |
| \(\Phi_2(c,c;\rho)\) | \(\mathbb{E}[\Phi((c-\sqrt{\rho}Z)/\sqrt{1-\rho})^2]\) |
| \(P(K=0)\) | \(\mathbb{E}[\Phi((-c+\sqrt{\rho}Z)/\sqrt{1-\rho})^n]\) |
| \(P(K=n)\) | \(\mathbb{E}[\Phi((c-\sqrt{\rho}Z)/\sqrt{1-\rho})^n]\) |
| Full PMF | \(K\mid Z\sim\mathrm{Bin}(n,\pi(Z))\), \(\pi(Z)=\Phi((c-\sqrt{\rho}Z)/\sqrt{1-\rho})\) |

1D integrals over \(Z\sim N(0,1)\) replace MC. Implemented in `scripts/xh-baselines.ts` (`analyticXhmMoments`, `analyticXhmPmfs`) via trapezoid on \([-8,8]\).

### Empirical check (p=0.55, n=4, ρ=0.5)

| Metric | Independent Bin | Analytic | Current MC `estimateXhm` |
|--------|-----------------|----------|---------------------------|
| Var(K) | 0.990 | **1.977** | 1.972 |
| P(K=0) | 0.041 | **0.161** (×3.93) | 0.161 |
| P(K=n) | 0.092 | **0.244** (×2.66) | 0.243 |

MC already agrees with analytics within ~0.001 — so production dependence is *directionally* correct; the win is **determinism + stronger eval + optional analytic replace**.

For ρ→0, extremes collapse to binomial (MC noise ~0.01); for ρ>0 both tails inflate (positive quadrant dependence / overdispersion).

---

## Eval hardening (shipped this pass)

In `scripts/eval-xh-math.ts`, **added** (did not weaken):

1. `xHm P(K=0) inflates vs independent binomial` — require `P0 > 1.5 × (1−p)^n` at (p=0.55,n=4,ρ=0.5).
2. `xHm P(K=n) inflates vs independent binomial` — same for `p^n`.
3. `xHm ρ→0 extremes ≈ independent binomial` — `|Δ| < 0.02` on both extremes.

These catch a “variance-only fake” (e.g. fattening middle mass while suppressing all-hit / all-miss).

---

## Baseline scaffold (shipped)

`scripts/xh-baselines.ts`:

- `analyticXhmMoments` / `analyticXhmPmfs`
- `independentBinomialPmfs`
- `brierScore` + `corridorCalibrationStub` (synthetic |M|<R vs predicted xH)

Smoke: `npx --yes tsx scripts/xh-baselines.ts`

---

## Proposed production patch (do **not** apply in EMPIRICS; KEEP for orchestrator)

Replace MC body of `estimateXhm` with `analyticXhmPmfs` (or inline the same 1D mixture), keeping API `(singleXh, enemiesInRange, rho) → number[]`.

**Expected invariant gains:**

- Deterministic PMF (no LCG seed artifacts).
- Exact mean `np`; exact Var formula.
- Tails match analytics within integration tolerance ≪ MC SE.
- Faster for n≤10 (O(grid × n) vs O(trials × n)).

**Risk:** erfinv / Φ quality at extreme p; clamp ρ∈[0,0.95] already present — keep.

**Calibration follow-up (scoring):** add optional eval that for `corridorHitProb(R,μ,σ)`, empirical hit rate from N(μ,σ²) draws is within ±0.03 of prediction and Brier < independent coin baseline — uses `corridorCalibrationStub`.

---

## Citations

- Ochi Y., Prentice R.L. Likelihood inference in a correlated probit regression model. *Biometrika* 71(3):531–543 (1984). Equicorrelated MVN orthant → 1D integrals.
- arXiv:2403.02194 — Gaussian-copula bivariate Bernoulli / dependence separate from margins.
- arXiv:2606.27288 — single-factor probit / co-failure floor (why P(all miss) matters beyond pairwise ρ).
- Program factorization: xHm = shared-latent dependence, not independent Binomial.

---

## Decision

**KEEP_CANDIDATE** — analytic xHm + extreme-cell eval + baselines scaffold deepen dependence/scoring without touching multiplicative priors or weakening math checks. Orchestrator should (1) keep the new eval asserts, (2) optionally swap `estimateXhm` to analytic PMF in a later apply pass, (3) add corridor Brier sanity when scoring axis opens.
