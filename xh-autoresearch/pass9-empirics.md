# Pass-9 EMPIRICS — ICI / HL / spherical / AD-PIT / cond-Winkler / quartet-ρ / twCRPS

**Verdict: KEEP_CANDIDATE**

Proposal only — **do not** edit `src/engine/xh.ts`, and do not soften Pass-2…8
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
`spiegelhalterAbsTol=2.0`). Deepen residual only in
`scripts/xh-baselines.ts` + `scripts/eval-xh-math.ts` when
orchestrator applies.

Expected post-apply: `math_pass_rate=1.0000` with **+8–10** new empirics
asserts (195 → ~203–205), no BASE×ZONE×VISION.

Baseline confirmed: **195/195** (`npm run eval:xh`).

---

## Critique — what Pass-1…8 left shallow

Pass-8 EMPIRICS landed isotonic / joint-LL / Cox / cond-coverage /
stratified-ability / variogram / Spiegelhalter. Residual calib/xHm depth
still missing:

| Gap | Today | Why it bites |
|-----|-------|--------------|
| **Bin ECE ≠ continuous reliability curve** | Equal-width / adaptive ECE + MCE | Bin edges smear local bias; ICI averages \|calib(p)−p\| over the empirical p̂ law and catches smooth warps ECE bins miss |
| **No classical HL GOF** | Spiegelhalter Z + Cox slope | Decile χ² is the textbook residual complementary to mean-variance Z and logit slope; fires on mid-decile clumps Z can dilute |
| **Only Brier/log proper scores on binary** | Brier + log-loss (+ BSS) | Spherical score is a third strictly proper rule; ranking vs coin / bias kill can diverge from Brier when p̂ hugs {0,1} |
| **PIT KS is max-gap only** | PIT ECE + KS | KS ignores ordered tail weight; Anderson–Darling A² is tail-sensitive uniformity on randomized discrete PIT |
| **Winkler is unconditional** | Global wrong-ρ Winkler + tertile coverage freq | Coverage can look honest in a tertile while interval width+miss score still prefers wrong ρ; tertile-conditional Winkler kills that |
| **ρ MoM stops at triples** | Pairwise + triple π₁₁₁ | 4-target wipe mass needs π₁₁₁₁; a ρ that matches triples can still miss quartet joint |
| **Tail CRPS only scores extreme draws** | Filter k∈{0,n} then CRPS | Extreme-atom twCRPS scores P(K=0)/P(K=n) on *every* draw; wrong ρ misprices wipe/all-hit CDF even when k is mid |

Already landed (do **not** re-propose): analytic equicorrelated-probit xHm;
corridor Brier vs coin; ability-rate / Platt / Temp / Beta stubs+fitters;
ρ pairwise+triple MoM; ECE/CRPS/log-loss; online/strata ability hooks;
σ-scale kill; Platt/Temp/Beta held-out gain; MCE/adaptive ECE; wrong-ρ/Var/tail
CRPS; discrete PIT ECE+KS; Murphy REL/RES + identity + BSS; count
log-loss/count-bin ECE; conditional ECE; DSS; central PI coverage; ability
residual kill (global+stratified); energy + Winkler wrong-ρ; isotonic PAV;
joint Bernoulli LL; Cox; tertile-conditional coverage; variogram;
Spiegelhalter Z; `KILL_CRITERIA_VS_B1` Pass-2…8 fields.

---

## Minimal falsifiable math (synthetic OK)

### 1. Integrated Calibration Index (ICI)

Austin–Steyerberg ICI: mean absolute gap between the empirical calibration
curve and the diagonal under the law of p̂.

Implement via equal-count adaptive bins (reuse adaptive-ECE partitioning):
for each observation i in bin g, contribute \|acc_g − p̂_i\|; average over n.

- True corridor → `ici ≤ iciTol` with **new** `iciTol=0.03`
- Deliberate bias (+0.12) → `ici > iciTol` (kill)

Do **not** soften `eceTol` / `mceTol` / `spiegelhalterAbsTol`.

Cite: Austin & Steyerberg, Stat. Med. 2019 (ICI); complements bin ECE.

```ts
export function integratedCalibrationIndex(
  preds: number[],
  outcomes: number[],
  bins?: number, // default 10 equal-count
): number

export function corridorIciSanity(opts: {
  cells: Array<{ R: number; mu: number; sigma: number }>
  bias?: number
  trialsPerCell?: number
}): {
  ici: number
  ok: boolean // ici ≤ iciTol when bias=0
  shouldKillBiased: boolean
}
```

### 2. Hosmer–Lemeshow χ² residual

Decile-of-risk GOF:

\[
X^2_{\mathrm{HL}}=\sum_{g=1}^{G}\frac{(O_g-E_g)^2}{E_g(1-\bar p_g)}
\]

with G=10 equal-count deciles, E_g=∑_{i∈g} p̂_i, O_g=∑ y_i,
p̄_g=E_g/n_g.

- True corridor → `X² ≤ hosmerLemeshowChiSqTol` (`hosmerLemeshowChiSqTol=18`,
  ~df≈8 critical band)
- Bias (+0.12) → `X² > hosmerLemeshowChiSqTol`

Do **not** soften `eceTol` / `coxSlopeAbsTol`.

Cite: Hosmer & Lemeshow 1980; Hosmer et al. 1997.

```ts
export function hosmerLemeshowChiSq(
  preds: number[],
  outcomes: number[],
  groups?: number, // default 10
): number

export function corridorHosmerLemeshowSanity(opts: {
  cells: Array<{ R: number; mu: number; sigma: number }>
  bias?: number
  trialsPerCell?: number
}): {
  chiSq: number
  ok: boolean
  shouldKillBiased: boolean
}
```

### 3. Spherical proper score (binary corridor)

Strictly proper spherical score (higher better) / loss L=−S:

\[
S(p,y)=\frac{yp+(1-y)(1-p)}{\sqrt{p^2+(1-p)^2}}
\]

Contracts (additive):

- True corridor: `meanLoss ≤ meanCoinLoss * sphericalVsCoinMaxRatio`
  with **new** `sphericalVsCoinMaxRatio=1.15` (mirror Brier ratio; do **not**
  lower `brierVsCoinMaxRatio`)
- Bias (+0.12): meanLoss worse than true by ≥ `sphericalBiasMinGain`
  (`sphericalBiasMinGain=0.01`) → kill miscalibrated map

Cite: Gneiting & Raftery, JASA 2007 (spherical score).

```ts
export function sphericalScore(p: number, y: number): number // S ∈ (0,1]
export function sphericalLoss(p: number, y: number): number // −S

export function corridorSphericalSanity(opts: {
  cells: Array<{ R: number; mu: number; sigma: number }>
  bias?: number
  trialsPerCell?: number
}): {
  meanLoss: number
  meanCoinLoss: number
  ok: boolean // vs-coin ratio when bias=0
  shouldKillBiased: boolean
}
```

### 4. Anderson–Darling on randomized discrete PIT

Same randomized PIT U as Pass-4/5 (Czado–Gneiting–Held). AD statistic
vs Uniform(0,1):

\[
A^2=-n-\frac1n\sum_{i=1}^n(2i-1)\bigl[\ln U_{(i)}+\ln(1-U_{(n+1-i)})\bigr]
\]

- Draws from ρ★ scored under ρ★ PMF → `A² ≤ pitAdTol` with **new**
  `pitAdTol=1.0` (finite-sample band; do **not** lower `pitKsTol` /
  `pitEceTol`)
- Same draws scored under ρ=0 → `A²` fails tol **or** exceeds star by ≥0.25

```ts
export function discretePitAndersonDarling(
  pmf: number[],
  draws: number[],
  seed?: number,
): { ad: number; ok: boolean }

export function xhmPitAdSanity(opts: {
  p: number
  n: number
  rhoStar: number
  trials?: number
}): {
  adStar: number
  adWrong: number
  okStar: boolean
  okKillWrong: boolean
}
```

### 5. Tertile-conditional Winkler wrong-ρ

Reuse Pass-7 `winklerIntervalScore` + Pass-8 tertile split on predicted
mean μ=n·p (multi-cell). Within each tertile, require

`wink_t(ρ★) + winklerWrongRhoMinGain ≤ wink_t(ρ=0)`.

Aggregate: `okStar` if all tertiles meet the gain; `okKillWrong` if ≥1
tertile fails for wrong ρ (or mean gain across tertiles ≥ tol).

Reuse existing `winklerWrongRhoMinGain=0.05` — do **not** lower.
Also do **not** loosen `coverageAbsTol`.

```ts
export function xhmConditionalWinklerSanity(opts: {
  cells: Array<{ p: number; n: number; rhoStar: number }>
  alpha?: number
  trialsPerCell?: number
}): {
  gainByTertile: number[]
  okStar: boolean
  okKillWrong: boolean
}
```

### 6. Quartet ρ MoM (π₁₁₁₁)

Analytic 4-way joint under equicorrelated probit:

\[
\pi_{1111}=\mathbb{E}\bigl[\Phi\bigl((c-\sqrt\rho\,Z)/\sqrt{1-\rho}\bigr)^4\bigr]
\]

Invert MoM → ρ̂₄. Contract: synthetic ρ★=0.5 draws →
`|ρ̂₄ − ρ★| ≤ quartetRhoAbsErrTol` with **new**
`quartetRhoAbsErrTol=0.10`. Do **not** lower `tripleRhoAbsErrTol` /
`rhoAbsErrTol`.

Cite: Ochi & Prentice 1984 (one-factor); extends Pass-5 triple MoM.

```ts
export function analyticQuartetJoint(p: number, rho: number): number

export function estimateRhoFromQuartetJoint(
  p: number,
  pi1111: number,
  tol?: number,
): number

export function rhoQuartetRecoverySanity(opts: {
  p: number
  rhoStar: number
  nQuartets?: number
  seed?: number
}): {
  rhoHat4: number
  absErr4: number
  ok: boolean
}
```

### 7. Threshold-weighted CRPS on extreme atoms (twCRPS)

Score every draw k against wipe/all-hit atoms (Gneiting–Ranjan style
indicator weight on thresholds {0,n}):

\[
\mathrm{twCRPS}(F,k)=\bigl(F(0)-1\{k=0\}\bigr)^2
  +\bigl(F(n)-1\{k=n\}\bigr)^2
\]

where F(n)=P(K=n)=q_n (atom mass; not CDF at n−). Mean over ρ★ draws:
`tw(ρ★) + twCrpsWrongRhoMinGain ≤ tw(ρ=0)` with **new**
`twCrpsWrongRhoMinGain=0.02`. Do **not** lower `crpsWrongRhoMinGain` /
`energyWrongRhoMinGain` / `variogramWrongRhoMinGain`.

Distinct from Pass-4 tail CRPS (which *filters* to extreme draws then
applies full CRPS).

Cite: Gneiting & Ranjan, MWR 2011 (threshold-weighted CRPS).

```ts
export function twCrpsExtremeAtoms(pmf: number[], k: number): number

export function xhmWrongRhoTwCrpsKillSanity(opts: {
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

### 8. Additive kill constants only (never raise Pass-2…8)

```ts
export const KILL_CRITERIA_VS_B1 = {
  // --- Pass-2…8 unchanged (including jointLogLoss / Cox / variogram / Spiegelhalter) ---
  // ... existing fields verbatim ...
  // --- Pass-9 deepen ---
  iciTol: 0.03,
  hosmerLemeshowChiSqTol: 18,
  sphericalVsCoinMaxRatio: 1.15,
  sphericalBiasMinGain: 0.01,
  pitAdTol: 1.0,
  quartetRhoAbsErrTol: 0.10,
  twCrpsWrongRhoMinGain: 0.02,
} as const
```

---

## Exact eval asserts to add (do not weaken existing)

In `scripts/eval-xh-math.ts` (additive block after Pass-8 empirics):

```ts
// --- empirics deepen (Pass-9 EMPIRICS) ---
{
  const cells = [
    { R: 50, mu: 10, sigma: 30 },
    { R: 80, mu: 0, sigma: 40 },
    { R: 40, mu: 35, sigma: 25 },
  ]
  const iciOk = corridorIciSanity({ cells, bias: 0, trialsPerCell: 3000 })
  assert(
    'ICI: true corridor ≤ iciTol',
    iciOk.ok,
    `ici=${iciOk.ici.toFixed(4)}`,
  )
  const iciBad = corridorIciSanity({ cells, bias: 0.12, trialsPerCell: 3000 })
  assert(
    'ICI: biased corridor trips iciTol',
    iciBad.shouldKillBiased,
    `ici=${iciBad.ici.toFixed(4)}`,
  )
  const hlOk = corridorHosmerLemeshowSanity({
    cells,
    bias: 0,
    trialsPerCell: 3000,
  })
  assert(
    'HL χ²: true corridor ≤ hosmerLemeshowChiSqTol',
    hlOk.ok,
    `chiSq=${hlOk.chiSq.toFixed(2)}`,
  )
  const hlBad = corridorHosmerLemeshowSanity({
    cells,
    bias: 0.12,
    trialsPerCell: 3000,
  })
  assert(
    'HL χ²: biased corridor trips tol',
    hlBad.shouldKillBiased,
    `chiSq=${hlBad.chiSq.toFixed(2)}`,
  )
  const sphOk = corridorSphericalSanity({
    cells,
    bias: 0,
    trialsPerCell: 3000,
  })
  assert(
    'Spherical: true corridor loss ≤ coin × sphericalVsCoinMaxRatio',
    sphOk.ok,
    `loss=${sphOk.meanLoss.toFixed(4)} coin=${sphOk.meanCoinLoss.toFixed(4)}`,
  )
  const sphBad = corridorSphericalSanity({
    cells,
    bias: 0.12,
    trialsPerCell: 3000,
  })
  assert(
    'Spherical: biased corridor trips sphericalBiasMinGain',
    sphBad.shouldKillBiased,
    `loss=${sphBad.meanLoss.toFixed(4)}`,
  )
}
{
  const ad = xhmPitAdSanity({
    p: 0.55,
    n: 4,
    rhoStar: 0.5,
    trials: 8000,
  })
  assert(
    'PIT AD: ρ★ PMF A² ≤ pitAdTol',
    ad.okStar,
    `adStar=${ad.adStar.toFixed(3)}`,
  )
  assert(
    'PIT AD: wrong ρ=0 worse / fails tol',
    ad.okKillWrong,
    `adWrong=${ad.adWrong.toFixed(3)}`,
  )
  const tw = xhmWrongRhoTwCrpsKillSanity({
    p: 0.55,
    n: 4,
    rhoStar: 0.5,
    trials: 8000,
  })
  assert(
    'wrong-ρ twCRPS extremes: ρ=0 loses by ≥ twCrpsWrongRhoMinGain',
    tw.shouldKillWrongRho,
    `gain=${tw.gain.toFixed(3)}`,
  )
  const q4 = rhoQuartetRecoverySanity({
    p: 0.55,
    rhoStar: 0.5,
    nQuartets: 30000,
  })
  assert(
    'quartet ρ MoM |ρ̂₄−ρ★| ≤ quartetRhoAbsErrTol',
    q4.ok,
    `err=${q4.absErr4.toFixed(3)} hat=${q4.rhoHat4.toFixed(3)}`,
  )
}
{
  const wC = xhmConditionalWinklerSanity({
    cells: [
      { p: 0.35, n: 4, rhoStar: 0.5 },
      { p: 0.55, n: 4, rhoStar: 0.5 },
      { p: 0.75, n: 4, rhoStar: 0.5 },
    ],
    trialsPerCell: 6000,
  })
  assert(
    'xHm conditional Winkler: tertiles prefer ρ★ by ≥ winklerWrongRhoMinGain',
    wC.okStar,
    `gain=${wC.gainByTertile.map((g) => g.toFixed(3)).join(',')}`,
  )
  assert(
    'xHm conditional Winkler: wrong ρ=0 fails ≥1 tertile',
    wC.okKillWrong,
  )
}
assert(
  'Pass-9 kill-criteria deepen fields finite',
  Number.isFinite(KILL_CRITERIA_VS_B1.iciTol) &&
    KILL_CRITERIA_VS_B1.hosmerLemeshowChiSqTol > 0 &&
    KILL_CRITERIA_VS_B1.sphericalVsCoinMaxRatio > 0 &&
    KILL_CRITERIA_VS_B1.sphericalBiasMinGain > 0 &&
    KILL_CRITERIA_VS_B1.pitAdTol > 0 &&
    KILL_CRITERIA_VS_B1.quartetRhoAbsErrTol > 0 &&
    KILL_CRITERIA_VS_B1.twCrpsWrongRhoMinGain > 0,
  JSON.stringify(KILL_CRITERIA_VS_B1),
)
```

Keep all Pass-2…8 Brier / ECE / ρ MoM / σ-scale / Platt / Temp / Beta /
Isotonic / MCE / Var / wrong-ρ CRPS+LL+DSS+energy+Winkler+joint-LL+variogram /
Murphy / BSS / PI coverage / cond-coverage / count-bin / triple-ρ / cond ECE /
PIT / Cox / Spiegelhalter / ability-kill asserts verbatim.

---

## Citations

- Austin & Steyerberg, Stat. Med. 2019 — Integrated Calibration Index.
- Hosmer & Lemeshow 1980; Hosmer, Hosmer, Le Cessie, Lemeshow 1997 — HL χ².
- Gneiting & Raftery, JASA 2007 — spherical score (strictly proper).
- Anderson & Darling 1952; Czado, Gneiting, Held 2009 — AD on randomized PIT.
- Winkler 1972; Gneiting & Raftery 2007 — interval score (conditional reuse).
- Ochi & Prentice, Biometrika 1984 — equicorrelated probit (quartet joint).
- Gneiting & Ranjan, Mon. Weather Rev. 2011 — threshold-weighted CRPS.
- Pass-2 EMPIRICS: `brierVsCoinMaxRatio` / `calibrationMinBrierGain` (reuse;
  never soften).
- Pass-5 EMPIRICS: `tripleRhoAbsErrTol` / `pitKsTol` (reuse; never soften).
- Pass-7/8 EMPIRICS: `winklerWrongRhoMinGain` / `spiegelhalterAbsTol` /
  `coxSlopeAbsTol` (reuse; never soften).

---

## Regression / risk

- **Do not** tighten or loosen any Pass-2…8 numeric kill thresholds.
- ICI: empty equal-count bins → merge neighbors; clamp p̂ to `[1e-9,1−1e-9]`.
  Flaky → more trials, not higher `iciTol` beyond necessity / never lower
  `eceTol`.
- HL: require n_g≥2 per decile; if E_g(1−p̄_g)≈0, skip/merge that decile
  before blaming `hosmerLemeshowChiSqTol`.
- Spherical: clamp p away from {0,1} in denom; coin baseline uses p=0.5.
- AD: clamp U to `(1e-9,1−1e-9)` before ln; raise N before touching
  `pitAdTol`; never lower `pitKsTol`.
- Conditional Winkler: raise `trialsPerCell` before blaming
  `winklerWrongRhoMinGain`.
- Quartet MoM: need more draws than triple (default ≥25k); do not lower
  `tripleRhoAbsErrTol` if quartet is noisy — only `quartetRhoAbsErrTol`
  may be the looser band.
- twCRPS: use atom masses q_0, q_n from analytic PMF; distinct from
  filtered tail CRPS asserts (keep both).
- ICI / HL / spherical / AD-PIT / cond-Winkler / quartet / twCRPS stay
  baselines-only — never multiply into `estimateXh` (no BASE×ZONE×VISION).
- No production `xh.ts` change this pass.

---

## Decision

**KEEP_CANDIDATE** — deepen empirics with ICI + Hosmer–Lemeshow + spherical
proper-score corridor kills, Anderson–Darling PIT, tertile-conditional
Winkler, quartet ρ MoM, and extreme-atom twCRPS wrong-ρ; leave Pass-2…8
thresholds untouched; no `xh.ts` edit.

**One-line verdict:** KEEP_CANDIDATE — ICI/HL/spherical + AD-PIT/cond-Winkler + quartet-ρ/twCRPS deepen calib/xHm without softening Pass-2…8 kills.
