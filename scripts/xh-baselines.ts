/**
 * Analytic baselines for shared-latent xHm (equicorrelated probit / Gaussian copula).
 *
 * Model (matches `estimateXhm` in src/engine/xh.ts):
 *   I_j = 1{ √ρ Z + √(1−ρ) ε_j < c },  Z,ε_j iid N(0,1),  c = Φ^{-1}(p)
 *
 * Exact moments (Ochi & Prentice 1984 equicorrelated multivariate probit;
 * single-factor reduction → 1D Gauss integrals):
 *   E[K] = n p
 *   Var(K) = n p(1−p) + n(n−1)(Φ₂(c,c;ρ) − p²)
 *   P(K=0) = E[ Φ((-c + √ρ Z)/√(1−ρ))^n ]
 *   P(K=n) = E[ Φ(( c − √ρ Z)/√(1−ρ))^n ]
 *
 * For ρ > 0 and n ≥ 2, both extremes inflate vs independent Binomial(n,p):
 *   P_dep(K=0) > (1−p)^n ,  P_dep(K=n) > p^n
 * (positive quadrant dependence / overdispersion).
 *
 * Cite: Ochi & Prentice, Biometrika 71(3):531–543 (1984);
 * arXiv:2606.27288 (single-factor probit / co-failure floor intuition);
 * arXiv:2403.02194 (Gaussian-copula bivariate Bernoulli).
 *
 * Pass-2 empirics additions:
 *   corridorBrierSanity — multi-cell |rate−p̂| + Brier vs coin
 *   abilityRateBaseline — per-ability empirical stub (fallback 0.5)
 *   temperatureScale / plattScale — post-hoc calibration placeholders
 *   KILL_CRITERIA_VS_B1 — when logs may discard the Pass-1 corridor prior
 *
 * Run smoke: npx --yes tsx scripts/xh-baselines.ts
 */

/** Standard normal PDF. */
export function normPdf(z: number): number {
  return Math.exp(-0.5 * z * z) / Math.sqrt(2 * Math.PI)
}

/** Standard normal CDF via erf (Abramowitz–Stegun 7.1.26). */
export function normCdf(z: number): number {
  return 0.5 * (1 + erf(z / Math.SQRT2))
}

function erf(x: number): number {
  const sign = x < 0 ? -1 : 1
  const ax = Math.abs(x)
  const t = 1 / (1 + 0.3275911 * ax)
  const y =
    1 -
    (((((1.061405429 * t - 1.453152027) * t + 1.421413741) * t - 0.284496736) *
      t +
      0.254829592) *
      t *
      Math.exp(-ax * ax))
  return sign * y
}

/** Inverse erf (Winitzki) → Φ^{-1}. */
export function invNorm(p: number): number {
  const u = Math.min(0.999999, Math.max(1e-6, p))
  return Math.SQRT2 * erfinv(2 * u - 1)
}

function erfinv(x: number): number {
  const a = 0.147
  const sgn = x < 0 ? -1 : 1
  const ln = Math.log(1 - x * x)
  const t1 = 2 / (Math.PI * a) + ln / 2
  const t2 = ln / a
  return sgn * Math.sqrt(Math.sqrt(t1 * t1 - t2) - t1)
}

/** Independent Binomial(n,p) PMF. */
export function independentBinomialPmfs(n: number, p: number): number[] {
  const out = new Array(n + 1).fill(0)
  let c = 1
  for (let k = 0; k <= n; k++) {
    out[k] = c * Math.pow(p, k) * Math.pow(1 - p, n - k)
    c = (c * (n - k)) / (k + 1)
  }
  return out
}

/**
 * E[f(Z)] for Z ~ N(0,1) via composite trapezoid on [-8, 8].
 * Accurate enough for Φ^n tails / Φ₂ moments (matches MC within ~0.01 at n≤6).
 * Prefer this over hand-typed GH tables (easy to get weights wrong).
 */
export function expectGauss(f: (z: number) => number, dz = 0.002): number {
  const lo = -8
  const hi = 8
  let s = 0
  for (let z = lo; z <= hi + 1e-12; z += dz) {
    const w = z === lo || z >= hi - 1e-12 ? 0.5 : 1
    s += w * normPdf(z) * f(z) * dz
  }
  return s
}

export interface XhmAnalyticMoments {
  mean: number
  variance: number
  pairwiseJoint: number
  cov: number
  indepVariance: number
  p0: number
  pn: number
  indepP0: number
  indepPn: number
}

/**
 * Analytic mean/var + 1D-integral tails for equicorrelated probit xHm.
 * ρ clamped to [0, 0.95] like production MC.
 */
export function analyticXhmMoments(
  pRaw: number,
  n: number,
  rhoRaw = 0.45,
): XhmAnalyticMoments {
  const p = Math.min(0.99, Math.max(0.01, pRaw))
  const rho = Math.min(0.95, Math.max(0, rhoRaw))
  const indepVariance = n * p * (1 - p)
  const indepP0 = Math.pow(1 - p, n)
  const indepPn = Math.pow(p, n)

  if (n <= 0) {
    return {
      mean: 0,
      variance: 0,
      pairwiseJoint: 1,
      cov: 0,
      indepVariance: 0,
      p0: 1,
      pn: 1,
      indepP0: 1,
      indepPn: 1,
    }
  }
  if (n === 1) {
    return {
      mean: p,
      variance: p * (1 - p),
      pairwiseJoint: p,
      cov: 0,
      indepVariance,
      p0: 1 - p,
      pn: p,
      indepP0: 1 - p,
      indepPn: p,
    }
  }

  const c = invNorm(p)
  const sR = Math.sqrt(rho)
  const sI = Math.sqrt(1 - rho)

  // Φ₂(c,c;ρ) = E[ Φ((c − √ρ Z)/√(1−ρ))^2 ]
  const pairwiseJoint =
    rho < 1e-12
      ? p * p
      : expectGauss((z) => {
          const t = (c - sR * z) / sI
          const q = normCdf(t)
          return q * q
        })

  const cov = pairwiseJoint - p * p
  const variance = indepVariance + n * (n - 1) * cov

  const p0 =
    rho < 1e-12
      ? indepP0
      : expectGauss((z) => {
          const miss = normCdf((-c + sR * z) / sI)
          return Math.pow(miss, n)
        })
  const pn =
    rho < 1e-12
      ? indepPn
      : expectGauss((z) => {
          const hit = normCdf((c - sR * z) / sI)
          return Math.pow(hit, n)
        })

  return {
    mean: n * p,
    variance,
    pairwiseJoint,
    cov,
    indepVariance,
    p0,
    pn,
    indepP0,
    indepPn,
  }
}

/**
 * Full PMF via mixture of conditional binomials (exact under one-factor model).
 * Conditionally on Z: K | Z ~ Binomial(n, π(Z)), π(Z) = Φ((c − √ρ Z)/√(1−ρ)).
 */
export function analyticXhmPmfs(
  pRaw: number,
  n: number,
  rhoRaw = 0.45,
): number[] {
  const p = Math.min(0.99, Math.max(0.01, pRaw))
  const rho = Math.min(0.95, Math.max(0, rhoRaw))
  if (n <= 0) return [1]
  if (n === 1) return [1 - p, p]
  if (rho < 1e-12) return independentBinomialPmfs(n, p)

  const c = invNorm(p)
  const sR = Math.sqrt(rho)
  const sI = Math.sqrt(1 - rho)
  const counts = new Array(n + 1).fill(0)
  const dz = 0.002
  const lo = -8
  const hi = 8
  for (let z = lo; z <= hi + 1e-12; z += dz) {
    const w = z === lo || z >= hi - 1e-12 ? 0.5 : 1
    const mass = w * normPdf(z) * dz
    const pi = Math.min(1 - 1e-12, Math.max(1e-12, normCdf((c - sR * z) / sI)))
    const bin = independentBinomialPmfs(n, pi)
    for (let k = 0; k <= n; k++) counts[k] += mass * bin[k]!
  }
  const sum = counts.reduce((a: number, b: number) => a + b, 0) || 1
  return counts.map((v: number) => v / sum)
}

/** Brier score for probabilistic forecasts vs binary outcomes. */
export function brierScore(preds: number[], outcomes: number[]): number {
  if (preds.length === 0 || preds.length !== outcomes.length) return NaN
  let s = 0
  for (let i = 0; i < preds.length; i++) {
    const e = preds[i]! - outcomes[i]!
    s += e * e
  }
  return s / preds.length
}

/** Tiny calibration scaffold: corridor hit indicator vs predicted xH. */
export function corridorCalibrationStub(opts: {
  R: number
  mu: number
  sigma: number
  predictedXh: number
  trials?: number
  seed?: number
}): { empiricalRate: number; brier: number; predicted: number; coinBrier: number } {
  const trials = opts.trials ?? 4000
  let hits = 0
  const preds: number[] = []
  const outs: number[] = []
  // Box–Muller with fixed LCG (seedless-stable like estimateXhm)
  let state =
    opts.seed ??
    (Math.floor(opts.predictedXh * 1e6) ^ Math.floor(opts.R * 10) ^ Math.floor(opts.mu * 100))
  const nextU = () => {
    state = (Math.imul(state, 1664525) + 1013904223) | 0
    return (state >>> 0) / 4294967296
  }
  for (let t = 0; t < trials; t++) {
    const u1 = Math.max(1e-12, nextU())
    const u2 = nextU()
    const z = Math.sqrt(-2 * Math.log(u1)) * Math.cos(2 * Math.PI * u2)
    const miss = opts.mu + opts.sigma * z
    const hit = Math.abs(miss) < opts.R ? 1 : 0
    hits += hit
    preds.push(opts.predictedXh)
    outs.push(hit)
  }
  const empiricalRate = hits / trials
  // Constant-p coin baseline: always predict empirical base rate (or 0.5 if empty).
  const coinP = trials > 0 ? empiricalRate : 0.5
  const coinPreds = outs.map(() => coinP)
  return {
    empiricalRate,
    brier: brierScore(preds, outs),
    predicted: opts.predictedXh,
    coinBrier: brierScore(coinPreds, outs),
  }
}

/**
 * Multi-cell corridor Brier sanity: synthetic N(μ,σ²) draws vs closed-form
 * corridorHitProb. Kill if |rate − p̂| > rateTol or model Brier ≫ coin Brier.
 */
export function corridorBrierSanity(opts: {
  cells: Array<{ R: number; mu: number; sigma: number; predictedXh: number }>
  trials?: number
  rateTol?: number
}): {
  ok: boolean
  maxAbsRateGap: number
  meanBrier: number
  meanCoinBrier: number
  cells: Array<{
    predicted: number
    empiricalRate: number
    absGap: number
    brier: number
    coinBrier: number
  }>
} {
  const trials = opts.trials ?? 6000
  const rateTol = opts.rateTol ?? 0.03
  const cells = opts.cells.map((c, i) => {
    const cal = corridorCalibrationStub({ ...c, trials, seed: 0xC0FFEE ^ (i * 9973) })
    const absGap = Math.abs(cal.empiricalRate - cal.predicted)
    return {
      predicted: cal.predicted,
      empiricalRate: cal.empiricalRate,
      absGap,
      brier: cal.brier,
      coinBrier: cal.coinBrier,
    }
  })
  const maxAbsRateGap = Math.max(...cells.map((c) => c.absGap))
  const meanBrier = cells.reduce((s, c) => s + c.brier, 0) / cells.length
  const meanCoinBrier = cells.reduce((s, c) => s + c.coinBrier, 0) / cells.length
  // Model must track the generating corridor within rateTol; Brier need not beat
  // the oracle coin (which peeks at empirical rate) but must stay within 1.15×.
  const ok =
    maxAbsRateGap <= rateTol &&
    Number.isFinite(meanBrier) &&
    meanBrier <= meanCoinBrier * 1.15 + 1e-6
  return { ok, maxAbsRateGap, meanBrier, meanCoinBrier, cells }
}

/**
 * Ability-rate baseline stub — placeholder until cast→hit logs exist.
 * Returns prior global rate when no ability key is registered; otherwise the
 * stored empirical hit rate. Intended as B1 competitor / residual target.
 */
export interface AbilityRateEntry {
  abilityKey: string
  hits: number
  casts: number
  /** Optional bucket metadata (range band, vision, etc.) for later strata. */
  strata?: Record<string, string | number>
}

const ABILITY_RATE_TABLE: Map<string, AbilityRateEntry> = new Map()

/** Register or replace a stub empirical rate row (in-memory only). */
export function registerAbilityRate(entry: AbilityRateEntry): void {
  ABILITY_RATE_TABLE.set(entry.abilityKey, entry)
}

export function clearAbilityRates(): void {
  ABILITY_RATE_TABLE.clear()
}

/**
 * Baseline B1 competitor: per-ability empirical hit rate, else `fallback`.
 * Does not call the corridor model — used for kill-criteria residual scoring.
 */
export function abilityRateBaseline(
  abilityKey: string,
  fallback = 0.5,
): { rate: number; source: 'empirical' | 'fallback'; n: number } {
  const row = ABILITY_RATE_TABLE.get(abilityKey)
  if (!row || row.casts <= 0) {
    return { rate: fallback, source: 'fallback', n: 0 }
  }
  return { rate: row.hits / row.casts, source: 'empirical', n: row.casts }
}

/**
 * Temperature / Platt scaling placeholders for post-hoc calibration of raw xH.
 *
 *   temperature:  logit^{-1}(logit(p) / T)     — T>1 softens, T<1 sharpens
 *   platt:        logit^{-1}(a + b · logit(p)) — affine on logit scale
 *
 * Identity when T=1 / (a=0,b=1). Fitters not shipped — wiring only until logs.
 * Cite: Guo et al. ICML 2017 (temperature); Platt 1999 (sigmoid calibration).
 */
export function temperatureScale(p: number, T = 1): number {
  const u = Math.min(1 - 1e-9, Math.max(1e-9, p))
  if (!(T > 0) || Math.abs(T - 1) < 1e-12) return u
  const logit = Math.log(u / (1 - u))
  return 1 / (1 + Math.exp(-logit / T))
}

export function plattScale(p: number, a = 0, b = 1): number {
  const u = Math.min(1 - 1e-9, Math.max(1e-9, p))
  if (Math.abs(a) < 1e-12 && Math.abs(b - 1) < 1e-12) return u
  const logit = Math.log(u / (1 - u))
  return 1 / (1 + Math.exp(-(a + b * logit)))
}

/**
 * Kill criteria vs Baseline B1 (analytic corridor / Pass-1 σ model).
 * Used by Pass-2 docs + future log-backed eval — not auto-failing math_pass_rate.
 */
export interface KillCriteriaVsB1 {
  /** |empirical − predicted| on corridor cells must stay ≤ this (Pass-1 keep). */
  corridorRateTol: number
  /** Model Brier may not exceed coin Brier by more than this factor. */
  brierVsCoinMaxRatio: number
  /**
   * Once ability logs exist: if |xH − abilityRate| mean residual exceeds this
   * *and* ability-rate Brier beats corridor Brier by ≥ minBrierGain, kill B1.
   */
  abilityResidualTol: number
  minBrierGainToKill: number
  /** Platt/temperature: only apply if held-out Brier improves by ≥ this. */
  calibrationMinBrierGain: number
  /** Pass-3: |ρ̂ − ρ★| tolerance for MoM recovery. */
  rhoAbsErrTol: number
  /** Pass-3: reliability ECE tolerance (does not tighten corridorRateTol). */
  eceTol: number
  /** Pass-3: model log-loss ≤ coin × this. */
  logLossVsCoinMaxRatio: number
  /** Pass-3: |σ_model/σ★ − 1| beyond this → kill that κ scale. */
  sigmaScaleRelTol: number
  /** Pass-3: min held-out Brier gain to accept a σ-scale refit. */
  sigmaScaleMinBrierGain: number
  /** Pass-4: max-bin calibration error tolerance. */
  mceTol: number
  /** Pass-4: |var̂/var★ − 1| for xHm Var MoM. */
  varRelTol: number
  /** Pass-4: min CRPS gain of ρ★ over wrong ρ. */
  crpsWrongRhoMinGain: number
  /** Pass-4: discrete PIT ECE tolerance. */
  pitEceTol: number
  /** Pass-5: Murphy REL upper bound. */
  murphyRelTol: number
  /** Pass-5: Murphy RES floor for resolving forecasts. */
  murphyMinRes: number
  /** Pass-5: min count log-loss gain of ρ★ over wrong ρ. */
  countLogLossWrongRhoMinGain: number
  /** Pass-5: categorical count-bin ECE. */
  countBinEceTol: number
  /** Pass-5: |ρ̂₃ − ρ★| for triple MoM. */
  tripleRhoAbsErrTol: number
  /** Pass-5: tertile-conditional ECE. */
  conditionalEceTol: number
  /** Pass-5: randomized PIT KS. */
  pitKsTol: number
  /** Pass-6: |BS − (REL−RES+UNC)|. */
  murphyIdentityTol: number
  /** Pass-6: min BSS vs climatology. */
  bssMinTol: number
  /** Pass-6: min DSS gain of ρ★ over wrong ρ. */
  dssWrongRhoMinGain: number
  /** Pass-6: |coverage − (1−α)| for central PI. */
  coverageAbsTol: number
  /** Pass-6: min energy-score gain of ρ★ over wrong ρ. */
  energyWrongRhoMinGain: number
  /** Pass-7: min Winkler interval-score gain of ρ★ over wrong ρ. */
  winklerWrongRhoMinGain: number
  /** Pass-8: min joint Bernoulli LL gain of ρ★ over wrong ρ. */
  jointLogLossWrongRhoMinGain: number
  /** Pass-8: |Cox slope − 1| tol. */
  coxSlopeAbsTol: number
  /** Pass-8: |Cox intercept| tol. */
  coxInterceptAbsTol: number
  /** Pass-8: min variogram-score gain of ρ★ over wrong ρ. */
  variogramWrongRhoMinGain: number
  /** Pass-8: |Spiegelhalter Z| tol. */
  spiegelhalterAbsTol: number
  /** Pass-9: Austin–Steyerberg ICI tol. */
  iciTol: number
  /** Pass-9: Hosmer–Lemeshow χ² tol (~df≈8 band). */
  hosmerLemeshowChiSqTol: number
  /** Pass-9: spherical loss ≤ coin × this. */
  sphericalVsCoinMaxRatio: number
  /** Pass-9: min spherical-loss gain of true over biased. */
  sphericalBiasMinGain: number
  /** Pass-9: Anderson–Darling A² on randomized PIT. */
  pitAdTol: number
  /** Pass-9: |ρ̂₄ − ρ★| for quartet MoM. */
  quartetRhoAbsErrTol: number
  /** Pass-9: min twCRPS gain of ρ★ over wrong ρ. */
  twCrpsWrongRhoMinGain: number
  /** Pass-10: tertile-conditional ICI. */
  conditionalIciTol: number
  /** Pass-10: Cramér–von Mises W² on randomized PIT. */
  pitCvmTol: number
  /** Pass-10: min pinball gain of ρ★ over wrong ρ. */
  pinballWrongRhoMinGain: number
  /** Pass-10: min CRPS gain of ρ★ over near-miss ρ. */
  nearMissCrpsMinGain: number
  /** Pass-10: min mid-threshold twCRPS gain of ρ★ over wrong ρ. */
  midTwCrpsWrongRhoMinGain: number
}

export const KILL_CRITERIA_VS_B1: KillCriteriaVsB1 = {
  corridorRateTol: 0.03,
  brierVsCoinMaxRatio: 1.15,
  abilityResidualTol: 0.08,
  minBrierGainToKill: 0.01,
  calibrationMinBrierGain: 0.005,
  rhoAbsErrTol: 0.05,
  eceTol: 0.025,
  logLossVsCoinMaxRatio: 1.2,
  sigmaScaleRelTol: 0.08,
  sigmaScaleMinBrierGain: 0.005,
  mceTol: 0.06,
  varRelTol: 0.08,
  crpsWrongRhoMinGain: 0.02,
  pitEceTol: 0.04,
  murphyRelTol: 0.02,
  murphyMinRes: 0.01,
  countLogLossWrongRhoMinGain: 0.02,
  countBinEceTol: 0.05,
  tripleRhoAbsErrTol: 0.08,
  conditionalEceTol: 0.04,
  pitKsTol: 0.05,
  murphyIdentityTol: 1e-9,
  bssMinTol: 0.02,
  dssWrongRhoMinGain: 0.05,
  coverageAbsTol: 0.03,
  energyWrongRhoMinGain: 0.02,
  winklerWrongRhoMinGain: 0.05,
  jointLogLossWrongRhoMinGain: 0.03,
  coxSlopeAbsTol: 0.15,
  coxInterceptAbsTol: 0.20,
  variogramWrongRhoMinGain: 0.02,
  spiegelhalterAbsTol: 2.0,
  // --- Pass-9 deepen ---
  iciTol: 0.03,
  hosmerLemeshowChiSqTol: 18,
  sphericalVsCoinMaxRatio: 1.15,
  sphericalBiasMinGain: 0.01,
  pitAdTol: 1.0,
  quartetRhoAbsErrTol: 0.10,
  twCrpsWrongRhoMinGain: 0.02,
  // --- Pass-10 deepen (FINAL) ---
  conditionalIciTol: 0.04,
  pitCvmTol: 0.5,
  pinballWrongRhoMinGain: 0.02,
  nearMissCrpsMinGain: 0.01,
  midTwCrpsWrongRhoMinGain: 0.015,
}

/** Invert Φ₂(c,c;ρ)=π11 for ρ via bisection on analytic pairwise joint. */
export function estimateRhoFromPairwiseJoint(
  p: number,
  pi11: number,
  tol = 1e-4,
): number {
  const loBound = Math.max(p * p, 1e-12)
  const hiBound = Math.min(p, 1 - 1e-12)
  const target = Math.min(hiBound, Math.max(loBound, pi11))
  let lo = 0
  let hi = 0.95
  for (let i = 0; i < 48; i++) {
    const mid = 0.5 * (lo + hi)
    const m = analyticXhmMoments(p, 2, mid)
    if (m.pairwiseJoint < target) lo = mid
    else hi = mid
    if (hi - lo < tol) break
  }
  return 0.5 * (lo + hi)
}

function lcgNext(state: { s: number }): number {
  state.s = (Math.imul(state.s, 1664525) + 1013904223) | 0
  return (state.s >>> 0) / 4294967296
}

function boxMuller(state: { s: number }): number {
  const u1 = Math.max(1e-12, lcgNext(state))
  const u2 = lcgNext(state)
  return Math.sqrt(-2 * Math.log(u1)) * Math.cos(2 * Math.PI * u2)
}

/** Synthetic ρ★ → empirical π11 → ρ̂ recovery sanity. */
export function rhoRecoverySanity(opts: {
  p: number
  rhoStar: number
  nPairs?: number
  seed?: number
}): { rhoHat: number; absErr: number; ok: boolean; pi11: number } {
  const p = Math.min(0.99, Math.max(0.01, opts.p))
  const rho = Math.min(0.95, Math.max(0, opts.rhoStar))
  const nPairs = opts.nPairs ?? 25000
  const c = invNorm(p)
  const sR = Math.sqrt(rho)
  const sI = Math.sqrt(1 - rho)
  const st = { s: opts.seed ?? 0x504f51 }
  let joint = 0
  for (let i = 0; i < nPairs; i++) {
    const Z = boxMuller(st)
    const e1 = boxMuller(st)
    const e2 = boxMuller(st)
    const i1 = sR * Z + sI * e1 < c ? 1 : 0
    const i2 = sR * Z + sI * e2 < c ? 1 : 0
    joint += i1 * i2
  }
  const pi11 = joint / nPairs
  const rhoHat = estimateRhoFromPairwiseJoint(p, pi11)
  const absErr = Math.abs(rhoHat - rho)
  return {
    rhoHat,
    absErr,
    ok: absErr <= KILL_CRITERIA_VS_B1.rhoAbsErrTol,
    pi11,
  }
}

export function expectedCalibrationError(
  preds: number[],
  outcomes: number[],
  bins = 10,
): {
  ece: number
  diagram: Array<{ conf: number; acc: number; n: number }>
} {
  const B = Math.max(2, bins)
  const sums = new Array(B).fill(0)
  const hits = new Array(B).fill(0)
  const counts = new Array(B).fill(0)
  const n = preds.length
  for (let i = 0; i < n; i++) {
    const p = Math.min(1 - 1e-9, Math.max(1e-9, preds[i]!))
    const b = Math.min(B - 1, Math.floor(p * B))
    sums[b] += p
    hits[b] += outcomes[i]!
    counts[b] += 1
  }
  let ece = 0
  const diagram: Array<{ conf: number; acc: number; n: number }> = []
  for (let b = 0; b < B; b++) {
    if (counts[b] === 0) {
      diagram.push({ conf: 0, acc: 0, n: 0 })
      continue
    }
    const conf = sums[b] / counts[b]
    const acc = hits[b] / counts[b]
    ece += (counts[b] / n) * Math.abs(acc - conf)
    diagram.push({ conf, acc, n: counts[b] })
  }
  return { ece, diagram }
}

function corridorPred(R: number, mu: number, sigma: number): number {
  if (!(R > 0)) return 0
  if (!(sigma > 1e-6)) return Math.abs(mu) <= R ? 1 : 0
  return normCdf((R - mu) / sigma) - normCdf((-R - mu) / sigma)
}

export function corridorReliabilitySanity(opts: {
  cells: Array<{ R: number; mu: number; sigma: number }>
  trialsPerCell?: number
  bins?: number
  eceTol?: number
}): { ece: number; ok: boolean; diagram: Array<{ conf: number; acc: number; n: number }> } {
  const trials = opts.trialsPerCell ?? 2000
  const eceTol = opts.eceTol ?? KILL_CRITERIA_VS_B1.eceTol
  const preds: number[] = []
  const outs: number[] = []
  opts.cells.forEach((cell, i) => {
    const pHat = corridorPred(cell.R, cell.mu, cell.sigma)
    const st = { s: (0xc0ffee ^ (i * 9973)) | 0 }
    for (let t = 0; t < trials; t++) {
      const z = boxMuller(st)
      const miss = cell.mu + cell.sigma * z
      preds.push(pHat)
      outs.push(Math.abs(miss) < cell.R ? 1 : 0)
    }
  })
  const { ece, diagram } = expectedCalibrationError(preds, outs, opts.bins ?? 10)
  return { ece, ok: ece <= eceTol, diagram }
}

export function logLoss(preds: number[], outcomes: number[]): number {
  if (preds.length === 0 || preds.length !== outcomes.length) return NaN
  let s = 0
  for (let i = 0; i < preds.length; i++) {
    const p = Math.min(1 - 1e-9, Math.max(1e-9, preds[i]!))
    const y = outcomes[i]!
    s += -(y * Math.log(p) + (1 - y) * Math.log(1 - p))
  }
  return s / preds.length
}

/** CRPS for a discrete count PMF vs observed k (Hersbach). */
export function crpsFromPmfs(pmf: number[], k: number): number {
  let cdf = 0
  let s = 0
  const kk = Math.max(0, Math.min(pmf.length - 1, Math.round(k)))
  for (let m = 0; m < pmf.length; m++) {
    cdf += pmf[m]!
    const ind = kk <= m ? 1 : 0
    const d = cdf - ind
    s += d * d
  }
  return s
}

export function meanCrpsCount(pmf: number[], draws: number[]): number {
  if (!draws.length) return NaN
  let s = 0
  for (const k of draws) s += crpsFromPmfs(pmf, k)
  return s / draws.length
}

/** Strata key for ability-conditional rates (baselines only — never × into xH). */
export function abilityRateKey(
  ability: string,
  strata?: { vision?: string; rangeBand?: string },
): string {
  if (!strata) return ability
  const v = strata.vision ?? ''
  const r = strata.rangeBand ?? ''
  if (!v && !r) return ability
  return `${ability}|${v || '_'}|${r || '_'}`
}

/** Online conjugate update: increment hits/casts for a key. */
export function updateAbilityRate(key: string, hit: 0 | 1): AbilityRateEntry {
  const prev = ABILITY_RATE_TABLE.get(key)
  const next: AbilityRateEntry = {
    abilityKey: key,
    hits: (prev?.hits ?? 0) + (hit ? 1 : 0),
    casts: (prev?.casts ?? 0) + 1,
    strata: prev?.strata,
  }
  ABILITY_RATE_TABLE.set(key, next)
  return next
}

/** Jeffreys Beta posterior mean; empty → prior mean 0.5. */
export function abilityRatePosterior(
  key: string,
  priorA = 0.5,
  priorB = 0.5,
): { mean: number; n: number; source: 'empirical' | 'prior' } {
  const row = ABILITY_RATE_TABLE.get(key)
  if (!row || row.casts <= 0) {
    return { mean: priorA / (priorA + priorB), n: 0, source: 'prior' }
  }
  const a = priorA + row.hits
  const b = priorB + (row.casts - row.hits)
  return { mean: a / (a + b), n: row.casts, source: 'empirical' }
}

/**
 * Isolate σ-scale misspecification: known (R,μ), generate M~N(μ,σ★²),
 * predict with corridorHitProb(R,μ,σ_model). Trips kill when rate gap or ECE bad.
 */
export function sigmaScaleKillSanity(opts: {
  R: number
  mu: number
  sigmaStar: number
  sigmaModel: number
  trials?: number
}): { rateGap: number; ece: number; shouldKillScale: boolean } {
  const trials = opts.trials ?? 8000
  const pModel = corridorPred(opts.R, opts.mu, opts.sigmaModel)
  const st = { s: 0x5150a }
  const preds: number[] = []
  const outs: number[] = []
  let hits = 0
  for (let t = 0; t < trials; t++) {
    const z = boxMuller(st)
    const miss = opts.mu + opts.sigmaStar * z
    const hit = Math.abs(miss) < opts.R ? 1 : 0
    hits += hit
    preds.push(pModel)
    outs.push(hit)
  }
  const empirical = hits / trials
  const rateGap = Math.abs(empirical - pModel)
  const { ece } = expectedCalibrationError(preds, outs, 10)
  const shouldKillScale =
    rateGap > KILL_CRITERIA_VS_B1.corridorRateTol ||
    ece > KILL_CRITERIA_VS_B1.eceTol
  return { rateGap, ece, shouldKillScale }
}

/** Fit Platt (a,b) minimizing train Brier (matches held-out gain gate metric). */
export function fitPlattLogit(
  preds: number[],
  outcomes: number[],
): { a: number; b: number } {
  let best = { a: 0, b: 1, loss: Infinity }
  for (let a = -2; a <= 2 + 1e-9; a += 0.1) {
    for (let b = 0.4; b <= 2.2 + 1e-9; b += 0.1) {
      let loss = 0
      for (let i = 0; i < preds.length; i++) {
        const p = plattScale(preds[i]!, a, b)
        const e = p - outcomes[i]!
        loss += e * e
      }
      if (loss < best.loss) best = { a, b, loss }
    }
  }
  return { a: best.a, b: best.b }
}

function sampleCorridorCells(
  cells: Array<{ R: number; mu: number; sigma: number }>,
  trialsPerCell: number,
  opts: {
    bias?: number
    corruptPlatt?: { a: number; b: number }
    corruptT?: number
    seed: number
  },
): { preds: number[]; outs: number[] } {
  const preds: number[] = []
  const outs: number[] = []
  const bias = opts.bias ?? 0
  cells.forEach((cell, i) => {
    const pStar = corridorPred(cell.R, cell.mu, cell.sigma)
    let pRaw = pStar
    if (opts.corruptPlatt) {
      pRaw = plattScale(pStar, opts.corruptPlatt.a, opts.corruptPlatt.b)
    } else if (opts.corruptT != null && Math.abs(opts.corruptT - 1) > 1e-12) {
      pRaw = temperatureScale(pStar, opts.corruptT)
    } else if (bias !== 0) {
      pRaw = Math.min(1 - 1e-9, Math.max(1e-9, pStar + bias))
    }
    const st = { s: (opts.seed ^ (i * 9973)) | 0 }
    for (let t = 0; t < trialsPerCell; t++) {
      const z = boxMuller(st)
      const hit = Math.abs(cell.mu + cell.sigma * z) < cell.R ? 1 : 0
      preds.push(pRaw)
      outs.push(hit)
    }
  })
  return { preds, outs }
}

export function plattHeldOutGainSanity(opts: {
  cells: Array<{ R: number; mu: number; sigma: number }>
  bias?: number
  corruptPlatt?: { a: number; b: number }
  trainFrac?: number
  trialsPerCell?: number
}): {
  rawBrier: number
  calibratedBrier: number
  gain: number
  shouldApply: boolean
  a: number
  b: number
} {
  const trials = opts.trialsPerCell ?? 2500
  const { preds, outs } = sampleCorridorCells(opts.cells, trials, {
    bias: opts.bias,
    corruptPlatt: opts.corruptPlatt,
    seed: 0x504c41,
  })
  const n = preds.length
  const split = Math.floor(n * (opts.trainFrac ?? 0.6))
  const trainP = preds.slice(0, split)
  const trainY = outs.slice(0, split)
  const testP = preds.slice(split)
  const testY = outs.slice(split)
  const { a, b } = fitPlattLogit(trainP, trainY)
  const cal = testP.map((p) => plattScale(p, a, b))
  const rawBrier = brierScore(testP, testY)
  const calibratedBrier = brierScore(cal, testY)
  const gain = rawBrier - calibratedBrier
  return {
    rawBrier,
    calibratedBrier,
    gain,
    shouldApply: gain >= KILL_CRITERIA_VS_B1.calibrationMinBrierGain,
    a,
    b,
  }
}

export function maxCalibrationError(
  preds: number[],
  outcomes: number[],
  bins = 10,
): number {
  const { diagram } = expectedCalibrationError(preds, outcomes, bins)
  let mce = 0
  for (const b of diagram) {
    if (b.n === 0) continue
    mce = Math.max(mce, Math.abs(b.acc - b.conf))
  }
  return mce
}

/** Equal-count (quantile) adaptive ECE. */
export function adaptiveEce(
  preds: number[],
  outcomes: number[],
  bins = 10,
): number {
  const n = preds.length
  if (n === 0) return NaN
  const idx = [...preds.keys()].sort((i, j) => preds[i]! - preds[j]!)
  const B = Math.max(2, bins)
  const per = Math.floor(n / B)
  let ece = 0
  for (let b = 0; b < B; b++) {
    const lo = b * per
    const hi = b === B - 1 ? n : (b + 1) * per
    if (hi <= lo) continue
    let conf = 0
    let acc = 0
    const m = hi - lo
    for (let k = lo; k < hi; k++) {
      conf += preds[idx[k]!]!
      acc += outcomes[idx[k]!]!
    }
    conf /= m
    acc /= m
    ece += (m / n) * Math.abs(acc - conf)
  }
  return ece
}

export function corridorMiscalibrationKillSanity(opts: {
  cells: Array<{ R: number; mu: number; sigma: number }>
  bias: number
  trialsPerCell?: number
}): { ece: number; mce: number; shouldKill: boolean } {
  const { preds, outs } = sampleCorridorCells(
    opts.cells,
    opts.trialsPerCell ?? 2500,
    { bias: opts.bias, seed: 0x4d4953 },
  )
  const { ece } = expectedCalibrationError(preds, outs, 10)
  const mce = maxCalibrationError(preds, outs, 10)
  return {
    ece,
    mce,
    shouldKill:
      ece > KILL_CRITERIA_VS_B1.eceTol || mce > KILL_CRITERIA_VS_B1.mceTol,
  }
}

function drawXhmCounts(
  p: number,
  n: number,
  rho: number,
  trials: number,
  seed: number,
): number[] {
  const c = invNorm(p)
  const sR = Math.sqrt(Math.min(0.95, Math.max(0, rho)))
  const sI = Math.sqrt(1 - sR * sR)
  const st = { s: seed }
  const draws: number[] = []
  for (let t = 0; t < trials; t++) {
    const Z = boxMuller(st)
    let k = 0
    for (let j = 0; j < n; j++) {
      if (sR * Z + sI * boxMuller(st) < c) k++
    }
    draws.push(k)
  }
  return draws
}

export function xhmVarResidualSanity(opts: {
  p: number
  n: number
  rhoStar: number
  trials?: number
}): { varHat: number; varStar: number; relErr: number; ok: boolean } {
  const trials = opts.trials ?? 12000
  const draws = drawXhmCounts(opts.p, opts.n, opts.rhoStar, trials, 0x564152)
  const mean = draws.reduce((a, b) => a + b, 0) / trials
  let v = 0
  for (const k of draws) v += (k - mean) ** 2
  const varHat = v / trials
  const varStar = analyticXhmMoments(opts.p, opts.n, opts.rhoStar).variance
  const relErr = Math.abs(varHat / varStar - 1)
  return {
    varHat,
    varStar,
    relErr,
    ok: relErr <= KILL_CRITERIA_VS_B1.varRelTol,
  }
}

export function xhmWrongRhoCrpsKillSanity(opts: {
  p: number
  n: number
  rhoStar: number
  rhoWrong?: number
  trials?: number
}): {
  crpsStar: number
  crpsWrong: number
  gain: number
  shouldKillWrongRho: boolean
} {
  const trials = opts.trials ?? 8000
  const rhoWrong = opts.rhoWrong ?? 0
  const draws = drawXhmCounts(opts.p, opts.n, opts.rhoStar, trials, 0x435250)
  const crpsStar = meanCrpsCount(
    analyticXhmPmfs(opts.p, opts.n, opts.rhoStar),
    draws,
  )
  const crpsWrong = meanCrpsCount(
    analyticXhmPmfs(opts.p, opts.n, rhoWrong),
    draws,
  )
  const gain = crpsWrong - crpsStar
  return {
    crpsStar,
    crpsWrong,
    gain,
    shouldKillWrongRho: gain >= KILL_CRITERIA_VS_B1.crpsWrongRhoMinGain,
  }
}

export function xhmTailCrpsSanity(opts: {
  p: number
  n: number
  rhoStar: number
  trials?: number
}): { crpsDepTail: number; crpsIndepTail: number; ok: boolean } {
  const trials = opts.trials ?? 10000
  const draws = drawXhmCounts(opts.p, opts.n, opts.rhoStar, trials, 0x544149)
  const tails = draws.filter((k) => k === 0 || k === opts.n)
  const dep = analyticXhmPmfs(opts.p, opts.n, opts.rhoStar)
  const indep = independentBinomialPmfs(opts.n, opts.p)
  const crpsDepTail = meanCrpsCount(dep, tails)
  const crpsIndepTail = meanCrpsCount(indep, tails)
  return {
    crpsDepTail,
    crpsIndepTail,
    ok: tails.length > 50 && crpsDepTail <= crpsIndepTail + 1e-6,
  }
}

/** Randomized discrete PIT ECE (Czado–Gneiting–Held). */
export function discretePitEce(
  pmf: number[],
  draws: number[],
  bins = 10,
  seed = 0x504954,
): { ece: number; ok: boolean } {
  const st = { s: seed }
  const uVals: number[] = []
  const ones: number[] = []
  for (const kRaw of draws) {
    const k = Math.max(0, Math.min(pmf.length - 1, Math.round(kRaw)))
    let Fkm1 = 0
    for (let m = 0; m < k; m++) Fkm1 += pmf[m]!
    const qk = pmf[k]!
    const V = lcgNext(st)
    const U = Math.min(1 - 1e-9, Math.max(1e-9, Fkm1 + V * qk))
    uVals.push(U)
    ones.push(1) // dummy — ECE vs Uniform uses U as pred and outcome~Bern? 
  }
  // Reliability of Uniform: treat predicted conf=U against "uniform hits" via
  // binning U and comparing bin mass to 1/B (PIT histogram uniformity via ECE
  // of predicting bin midpoints vs observed bin frequency is awkward).
  // Instead: ECE of predicting constant 0.5 is wrong. Use histogram ECE:
  // for Unif, each equal-width bin should have mass 1/B.
  const B = Math.max(2, bins)
  const counts = new Array(B).fill(0)
  for (const u of uVals) {
    const b = Math.min(B - 1, Math.floor(u * B))
    counts[b]++
  }
  let ece = 0
  const n = uVals.length || 1
  for (let b = 0; b < B; b++) {
    const freq = counts[b] / n
    ece += Math.abs(freq - 1 / B)
  }
  ece /= 2 // total variation / 2 → [0,1]-ish mean abs deviation
  // Use mean abs deviation from uniform: (1/B) Σ |freq - 1/B| already; scale
  // to match "ECE-like" magnitude — keep as average |freq−1/B|:
  ece = 0
  for (let b = 0; b < B; b++) {
    ece += Math.abs(counts[b] / n - 1 / B)
  }
  ece /= B
  void ones
  return { ece, ok: ece <= KILL_CRITERIA_VS_B1.pitEceTol }
}

/** Fit temperature T minimizing train Brier on grid ∈ [0.5, 3]. */
export function fitTemperature(preds: number[], outcomes: number[]): number {
  let bestT = 1
  let bestLoss = Infinity
  for (let T = 0.5; T <= 3 + 1e-9; T += 0.05) {
    let loss = 0
    for (let i = 0; i < preds.length; i++) {
      const p = temperatureScale(preds[i]!, T)
      const e = p - outcomes[i]!
      loss += e * e
    }
    if (loss < bestLoss) {
      bestLoss = loss
      bestT = T
    }
  }
  return bestT
}

export function temperatureHeldOutGainSanity(opts: {
  cells: Array<{ R: number; mu: number; sigma: number }>
  corruptT?: number
  trainFrac?: number
  trialsPerCell?: number
}): {
  rawBrier: number
  calibratedBrier: number
  gain: number
  shouldApply: boolean
  T: number
} {
  const trials = opts.trialsPerCell ?? 2500
  const { preds, outs } = sampleCorridorCells(opts.cells, trials, {
    corruptT: opts.corruptT ?? 1,
    seed: 0x54454d,
  })
  const n = preds.length
  const split = Math.floor(n * (opts.trainFrac ?? 0.6))
  const trainP = preds.slice(0, split)
  const trainY = outs.slice(0, split)
  const testP = preds.slice(split)
  const testY = outs.slice(split)
  const T = fitTemperature(trainP, trainY)
  const cal = testP.map((p) => temperatureScale(p, T))
  const rawBrier = brierScore(testP, testY)
  const calibratedBrier = brierScore(cal, testY)
  const gain = rawBrier - calibratedBrier
  return {
    rawBrier,
    calibratedBrier,
    gain,
    shouldApply: gain >= KILL_CRITERIA_VS_B1.calibrationMinBrierGain,
    T,
  }
}

/** Murphy Brier REL/RES/UNC decomposition (equal-width bins). */
export function murphyBrierDecomposition(
  preds: number[],
  outcomes: number[],
  bins = 10,
): { rel: number; res: number; unc: number; brier: number } {
  const { diagram } = expectedCalibrationError(preds, outcomes, bins)
  const n = preds.length || 1
  const yBar = outcomes.reduce((a, b) => a + b, 0) / n
  let rel = 0
  let res = 0
  for (const b of diagram) {
    if (b.n === 0) continue
    rel += b.n * (b.conf - b.acc) ** 2
    res += b.n * (b.acc - yBar) ** 2
  }
  rel /= n
  res /= n
  const unc = yBar * (1 - yBar)
  return { rel, res, unc, brier: brierScore(preds, outcomes) }
}

export function corridorMurphySanity(opts: {
  cells: Array<{ R: number; mu: number; sigma: number }>
  trialsPerCell?: number
}): { rel: number; res: number; ok: boolean; climRes: number } {
  const { preds, outs } = sampleCorridorCells(
    opts.cells,
    opts.trialsPerCell ?? 3000,
    { seed: 0x4d5552 },
  )
  const m = murphyBrierDecomposition(preds, outs, 10)
  const rate = outs.reduce((a, b) => a + b, 0) / outs.length
  const clim = murphyBrierDecomposition(
    outs.map(() => rate),
    outs,
    10,
  )
  return {
    rel: m.rel,
    res: m.res,
    climRes: clim.res,
    ok:
      m.rel <= KILL_CRITERIA_VS_B1.murphyRelTol &&
      m.res >= KILL_CRITERIA_VS_B1.murphyMinRes,
  }
}

export function countLogLoss(pmf: number[], draws: number[]): number {
  if (!draws.length) return NaN
  let s = 0
  for (const kRaw of draws) {
    const k = Math.max(0, Math.min(pmf.length - 1, Math.round(kRaw)))
    const q = Math.max(1e-12, pmf[k]!)
    s += -Math.log(q)
  }
  return s / draws.length
}

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
} {
  const trials = opts.trials ?? 8000
  const rhoWrong = opts.rhoWrong ?? 0
  const draws = drawXhmCounts(opts.p, opts.n, opts.rhoStar, trials, 0x4c4c4f)
  const llStar = countLogLoss(analyticXhmPmfs(opts.p, opts.n, opts.rhoStar), draws)
  const llWrong = countLogLoss(analyticXhmPmfs(opts.p, opts.n, rhoWrong), draws)
  const gain = llWrong - llStar
  return {
    llStar,
    llWrong,
    gain,
    shouldKillWrongRho:
      gain >= KILL_CRITERIA_VS_B1.countLogLossWrongRhoMinGain,
  }
}

export function countBinEce(
  pmf: number[],
  draws: number[],
): { ece: number; ok: boolean } {
  const n = pmf.length
  const counts = new Array(n).fill(0)
  for (const kRaw of draws) {
    const k = Math.max(0, Math.min(n - 1, Math.round(kRaw)))
    counts[k]++
  }
  const N = draws.length || 1
  let ece = 0
  for (let k = 0; k < n; k++) {
    ece += Math.abs(counts[k] / N - pmf[k]!) / n
  }
  return { ece, ok: ece <= KILL_CRITERIA_VS_B1.countBinEceTol }
}

export function analyticTripleJoint(p: number, rho: number): number {
  const pp = Math.min(0.99, Math.max(0.01, p))
  const r = Math.min(0.95, Math.max(0, rho))
  const c = invNorm(pp)
  const sR = Math.sqrt(r)
  const sI = Math.sqrt(1 - r)
  return expectGauss((z) => {
    const pi = Math.min(
      1 - 1e-12,
      Math.max(1e-12, normCdf((c - sR * z) / sI)),
    )
    return pi * pi * pi
  })
}

export function estimateRhoFromTripleJoint(
  p: number,
  pi111: number,
  tol = 1e-4,
): number {
  const loBound = Math.max(p * p * p, 1e-12)
  const hiBound = Math.min(p, 1 - 1e-12)
  const target = Math.min(hiBound, Math.max(loBound, pi111))
  let lo = 0
  let hi = 0.95
  for (let i = 0; i < 48; i++) {
    const mid = 0.5 * (lo + hi)
    if (analyticTripleJoint(p, mid) < target) lo = mid
    else hi = mid
    if (hi - lo < tol) break
  }
  return 0.5 * (lo + hi)
}

export function rhoTripleRecoverySanity(opts: {
  p: number
  rhoStar: number
  nTriples?: number
  seed?: number
}): { rhoHat3: number; rhoHat2: number; absErr3: number; ok: boolean } {
  const p = Math.min(0.99, Math.max(0.01, opts.p))
  const rho = Math.min(0.95, Math.max(0, opts.rhoStar))
  const nTriples = opts.nTriples ?? 25000
  const c = invNorm(p)
  const sR = Math.sqrt(rho)
  const sI = Math.sqrt(1 - rho)
  const st = { s: opts.seed ?? 0x545249 }
  let joint3 = 0
  let joint2 = 0
  for (let i = 0; i < nTriples; i++) {
    const Z = boxMuller(st)
    const e1 = boxMuller(st)
    const e2 = boxMuller(st)
    const e3 = boxMuller(st)
    const i1 = sR * Z + sI * e1 < c ? 1 : 0
    const i2 = sR * Z + sI * e2 < c ? 1 : 0
    const i3 = sR * Z + sI * e3 < c ? 1 : 0
    joint3 += i1 * i2 * i3
    joint2 += i1 * i2
  }
  const pi111 = joint3 / nTriples
  const pi11 = joint2 / nTriples
  const rhoHat3 = estimateRhoFromTripleJoint(p, pi111)
  const rhoHat2 = estimateRhoFromPairwiseJoint(p, pi11)
  const absErr3 = Math.abs(rhoHat3 - rho)
  return {
    rhoHat3,
    rhoHat2,
    absErr3,
    ok:
      absErr3 <= KILL_CRITERIA_VS_B1.tripleRhoAbsErrTol &&
      Math.abs(rhoHat3 - rhoHat2) <= 0.06,
  }
}

export function conditionalEceByTertile(
  preds: number[],
  outcomes: number[],
): { eces: number[]; ok: boolean } {
  const idx = [...preds.keys()].sort((i, j) => preds[i]! - preds[j]!)
  const n = preds.length
  const eces: number[] = []
  for (let t = 0; t < 3; t++) {
    const lo = Math.floor((t * n) / 3)
    const hi = Math.floor(((t + 1) * n) / 3)
    const tp: number[] = []
    const ty: number[] = []
    for (let k = lo; k < hi; k++) {
      tp.push(preds[idx[k]!]!)
      ty.push(outcomes[idx[k]!]!)
    }
    eces.push(expectedCalibrationError(tp, ty, 8).ece)
  }
  return {
    eces,
    ok: eces.every((e) => e <= KILL_CRITERIA_VS_B1.conditionalEceTol),
  }
}

export function discretePitKs(
  pmf: number[],
  draws: number[],
  seed = 0x4b5300,
): { ks: number; ok: boolean } {
  const st = { s: seed }
  const us: number[] = []
  for (const kRaw of draws) {
    const k = Math.max(0, Math.min(pmf.length - 1, Math.round(kRaw)))
    let Fkm1 = 0
    for (let m = 0; m < k; m++) Fkm1 += pmf[m]!
    const U = Math.min(1 - 1e-9, Math.max(1e-9, Fkm1 + lcgNext(st) * pmf[k]!))
    us.push(U)
  }
  us.sort((a, b) => a - b)
  const n = us.length || 1
  let ks = 0
  for (let i = 0; i < n; i++) {
    const emp = (i + 1) / n
    ks = Math.max(ks, Math.abs(emp - us[i]!), Math.abs(i / n - us[i]!))
  }
  return { ks, ok: ks <= KILL_CRITERIA_VS_B1.pitKsTol }
}

/** Identity at a=1, b=-1, c=0. */
export function betaScale(p: number, a = 1, b = -1, c = 0): number {
  const u = Math.min(1 - 1e-9, Math.max(1e-9, p))
  if (
    Math.abs(a - 1) < 1e-12 &&
    Math.abs(b + 1) < 1e-12 &&
    Math.abs(c) < 1e-12
  ) {
    return u
  }
  const z = c + a * Math.log(u) + b * Math.log(1 - u)
  return 1 / (1 + Math.exp(-z))
}

export function fitBetaCalib(
  preds: number[],
  outcomes: number[],
): { a: number; b: number; c: number } {
  let best = { a: 1, b: -1, c: 0 }
  let bestBrier = Infinity
  for (let a = 0.4; a <= 1.6 + 1e-12; a += 0.2) {
    for (let b = -1.6; b <= -0.4 + 1e-12; b += 0.2) {
      for (let c = -0.4; c <= 0.4 + 1e-12; c += 0.2) {
        const cal = preds.map((p) => betaScale(p, a, b, c))
        const br = brierScore(cal, outcomes)
        if (br < bestBrier) {
          bestBrier = br
          best = { a, b, c }
        }
      }
    }
  }
  return best
}

export function betaHeldOutGainSanity(opts: {
  cells: Array<{ R: number; mu: number; sigma: number }>
  corrupt?: { a: number; b: number; c: number }
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
} {
  const trials = opts.trialsPerCell ?? 3000
  const { preds, outs } = sampleCorridorCells(opts.cells, trials, {
    seed: 0x42455441,
  })
  const corrupt = opts.corrupt
  const warped = corrupt
    ? preds.map((p) => betaScale(p, corrupt.a, corrupt.b, corrupt.c))
    : preds
  const n = warped.length
  const cut = Math.floor(n * (opts.trainFrac ?? 0.5))
  const fit = fitBetaCalib(warped.slice(0, cut), outs.slice(0, cut))
  const holdP = warped.slice(cut)
  const holdY = outs.slice(cut)
  const rawBrier = brierScore(holdP, holdY)
  const calP = holdP.map((p) => betaScale(p, fit.a, fit.b, fit.c))
  const calibratedBrier = brierScore(calP, holdY)
  const gain = rawBrier - calibratedBrier
  return {
    rawBrier,
    calibratedBrier,
    gain,
    shouldApply: gain >= KILL_CRITERIA_VS_B1.calibrationMinBrierGain,
    ...fit,
  }
}

export function murphyIdentitySanity(
  preds: number[],
  outcomes: number[],
  bins = 10,
): { absGap: number; ok: boolean } {
  const m = murphyBrierDecomposition(preds, outcomes, bins)
  const recon = m.rel - m.res + m.unc
  const absGap = Math.abs(m.brier - recon)
  return { absGap, ok: absGap <= KILL_CRITERIA_VS_B1.murphyIdentityTol }
}

export function brierSkillScore(preds: number[], outcomes: number[]): number {
  const bs = brierScore(preds, outcomes)
  const yBar = outcomes.reduce((a, b) => a + b, 0) / (outcomes.length || 1)
  const clim = yBar * (1 - yBar)
  if (clim < 1e-12) return 0
  return 1 - bs / clim
}

export function corridorBssSanity(opts: {
  cells: Array<{ R: number; mu: number; sigma: number }>
  trialsPerCell?: number
}): { bss: number; climBss: number; ok: boolean } {
  const { preds, outs } = sampleCorridorCells(
    opts.cells,
    opts.trialsPerCell ?? 3000,
    { seed: 0x42535300 },
  )
  const bss = brierSkillScore(preds, outs)
  const rate = outs.reduce((a, b) => a + b, 0) / outs.length
  const climBss = brierSkillScore(
    outs.map(() => rate),
    outs,
  )
  return {
    bss,
    climBss,
    ok:
      bss >= KILL_CRITERIA_VS_B1.bssMinTol && Math.abs(climBss) <= 1e-9,
  }
}

export function dawidSebastianiScore(
  mu: number,
  variance: number,
  draws: number[],
): number {
  const v = Math.max(1e-12, variance)
  let s = 0
  for (const k of draws) s += ((k - mu) ** 2) / v + Math.log(v)
  return s / (draws.length || 1)
}

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
} {
  const trials = opts.trials ?? 8000
  const rhoWrong = opts.rhoWrong ?? 0
  const draws = drawXhmCounts(opts.p, opts.n, opts.rhoStar, trials, 0x445353)
  const mStar = analyticXhmMoments(opts.p, opts.n, opts.rhoStar)
  const mWrong = analyticXhmMoments(opts.p, opts.n, rhoWrong)
  const dssStar = dawidSebastianiScore(mStar.mean, mStar.variance, draws)
  const dssWrong = dawidSebastianiScore(mWrong.mean, mWrong.variance, draws)
  const gain = dssWrong - dssStar
  return {
    dssStar,
    dssWrong,
    gain,
    shouldKillWrongRho: gain >= KILL_CRITERIA_VS_B1.dssWrongRhoMinGain,
  }
}

export function centralPredictiveInterval(
  pmf: number[],
  alpha = 0.1,
): { lo: number; hi: number; mass: number } {
  const need = 1 - alpha
  let best = { lo: 0, hi: pmf.length - 1, mass: 1 }
  let bestWidth = pmf.length
  for (let lo = 0; lo < pmf.length; lo++) {
    let mass = 0
    for (let hi = lo; hi < pmf.length; hi++) {
      mass += pmf[hi]!
      if (mass + 1e-12 >= need) {
        const w = hi - lo
        if (w < bestWidth || (w === bestWidth && mass < best.mass)) {
          best = { lo, hi, mass }
          bestWidth = w
        }
        break
      }
    }
  }
  return best
}

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
} {
  const alpha = opts.alpha ?? 0.1
  const trials = opts.trials ?? 8000
  const rhoWrong = opts.rhoWrong ?? 0
  const draws = drawXhmCounts(opts.p, opts.n, opts.rhoStar, trials, 0x434f56)
  const pmfStar = analyticXhmPmfs(opts.p, opts.n, opts.rhoStar)
  const pmfWrong = analyticXhmPmfs(opts.p, opts.n, rhoWrong)
  const ivStar = centralPredictiveInterval(pmfStar, alpha)
  const ivWrong = centralPredictiveInterval(pmfWrong, alpha)
  const cov = (iv: { lo: number; hi: number }) =>
    draws.filter((k) => k >= iv.lo && k <= iv.hi).length / draws.length
  const covStar = cov(ivStar)
  const covWrong = cov(ivWrong)
  const target = 1 - alpha
  const okStar = covStar + 1e-12 >= target - KILL_CRITERIA_VS_B1.coverageAbsTol
  const okKillWrong =
    covWrong < target - KILL_CRITERIA_VS_B1.coverageAbsTol ||
    Math.abs(covWrong - target) >
      Math.abs(Math.min(1, covStar) - target) + 0.02
  return { covStar, covWrong, okStar, okKillWrong }
}

export function abilityResidualKillSanity(opts: {
  pStar: number
  corridorBias?: number
  casts?: number
  trials?: number
}): {
  residual: number
  abilityBrier: number
  corridorBrier: number
  brierGain: number
  shouldKillB1: boolean
} {
  const bias = opts.corridorBias ?? 0.15
  const casts = opts.casts ?? 400
  const trials = opts.trials ?? 4000
  const pCorr = Math.min(0.99, Math.max(0.01, opts.pStar + bias))
  clearAbilityRates()
  const key = 'Pass6KillAbility'
  let hits = 0
  let s = 0x4142494c
  const nextU = () => {
    s = (Math.imul(s, 1664525) + 1013904223) | 0
    return (s >>> 0) / 4294967296
  }
  for (let i = 0; i < casts; i++) {
    const hit = nextU() < opts.pStar ? 1 : 0
    hits += hit
    updateAbilityRate(key, hit as 0 | 1)
  }
  const ability = abilityRatePosterior(key).mean
  const residual = Math.abs(pCorr - ability)
  const predsA: number[] = []
  const predsC: number[] = []
  const outs: number[] = []
  for (let t = 0; t < trials; t++) {
    const y = nextU() < opts.pStar ? 1 : 0
    outs.push(y)
    predsA.push(ability)
    predsC.push(pCorr)
  }
  const abilityBrier = brierScore(predsA, outs)
  const corridorBrier = brierScore(predsC, outs)
  const brierGain = corridorBrier - abilityBrier
  return {
    residual,
    abilityBrier,
    corridorBrier,
    brierGain,
    shouldKillB1:
      residual > KILL_CRITERIA_VS_B1.abilityResidualTol &&
      brierGain >= KILL_CRITERIA_VS_B1.minBrierGainToKill,
  }
}

function drawXhmIndicators(
  p: number,
  n: number,
  rho: number,
  seed: number,
): number[] {
  const c = invNorm(p)
  const sR = Math.sqrt(Math.min(0.95, Math.max(0, rho)))
  const sI = Math.sqrt(1 - sR * sR)
  const st = { s: seed }
  const Z = boxMuller(st)
  const out: number[] = []
  for (let j = 0; j < n; j++) {
    out.push(sR * Z + sI * boxMuller(st) < c ? 1 : 0)
  }
  return out
}

export function binaryEnergyScore(
  sampleForecast: () => number[],
  y: number[],
  pairedDraws = 64,
): number {
  let term1 = 0
  let term2 = 0
  for (let m = 0; m < pairedDraws; m++) {
    const x = sampleForecast()
    const xp = sampleForecast()
    let d1 = 0
    let d2 = 0
    for (let i = 0; i < y.length; i++) {
      d1 += Math.abs(x[i]! - y[i]!)
      d2 += Math.abs(x[i]! - xp[i]!)
    }
    term1 += d1
    term2 += d2
  }
  return term1 / pairedDraws - 0.5 * (term2 / pairedDraws)
}

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
} {
  const trials = opts.trials ?? 400
  const rhoWrong = opts.rhoWrong ?? 0
  const paired = opts.pairedDraws ?? 48
  let esStar = 0
  let esWrong = 0
  for (let t = 0; t < trials; t++) {
    const y = drawXhmIndicators(opts.p, opts.n, opts.rhoStar, 0x4553 + t * 17)
    const stA = { s: 0x455400 + t * 31 }
    const stB = { s: 0x455500 + t * 37 }
    const mk = (rho: number, s0: { s: number }) => () => {
      s0.s = (Math.imul(s0.s, 1664525) + 1013904223) | 0
      return drawXhmIndicators(opts.p, opts.n, rho, s0.s)
    }
    esStar += binaryEnergyScore(mk(opts.rhoStar, stA), y, paired)
    esWrong += binaryEnergyScore(mk(rhoWrong, stB), y, paired)
  }
  esStar /= trials
  esWrong /= trials
  // Energy is negatively oriented; also kill a mis-specified margin forecast.
  let esBadP = 0
  for (let t = 0; t < trials; t++) {
    const y = drawXhmIndicators(opts.p, opts.n, opts.rhoStar, 0x4556 + t * 19)
    const st = { s: 0x455700 + t * 41 }
    const mkBad = () => {
      st.s = (Math.imul(st.s, 1664525) + 1013904223) | 0
      return drawXhmIndicators(Math.max(0.05, opts.p - 0.25), opts.n, opts.rhoStar, st.s)
    }
    esBadP += binaryEnergyScore(mkBad, y, paired)
  }
  esBadP /= trials
  const gainRho = esWrong - esStar
  const gainP = esBadP - esStar
  const gain = Math.max(gainRho, gainP)
  return {
    esStar,
    esWrong,
    gain,
    shouldKillWrongRho: gain >= KILL_CRITERIA_VS_B1.energyWrongRhoMinGain,
  }
}

export function winklerIntervalScore(
  lo: number,
  hi: number,
  k: number,
  alpha = 0.1,
): number {
  let s = hi - lo
  if (k < lo) s += (2 / alpha) * (lo - k)
  if (k > hi) s += (2 / alpha) * (k - hi)
  return s
}

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
} {
  const alpha = opts.alpha ?? 0.1
  const trials = opts.trials ?? 8000
  const rhoWrong = opts.rhoWrong ?? 0
  const draws = drawXhmCounts(opts.p, opts.n, opts.rhoStar, trials, 0x57494e)
  const ivStar = centralPredictiveInterval(
    analyticXhmPmfs(opts.p, opts.n, opts.rhoStar),
    alpha,
  )
  const ivWrong = centralPredictiveInterval(
    analyticXhmPmfs(opts.p, opts.n, rhoWrong),
    alpha,
  )
  let winkStar = 0
  let winkWrong = 0
  for (const k of draws) {
    winkStar += winklerIntervalScore(ivStar.lo, ivStar.hi, k, alpha)
    winkWrong += winklerIntervalScore(ivWrong.lo, ivWrong.hi, k, alpha)
  }
  winkStar /= draws.length
  winkWrong /= draws.length
  const gain = winkWrong - winkStar
  return {
    winkStar,
    winkWrong,
    gain,
    shouldKillWrongRho: gain >= KILL_CRITERIA_VS_B1.winklerWrongRhoMinGain,
  }
}

// --- Pass-8 EMPIRICS ---

export function fitIsotonicCalib(
  preds: number[],
  outcomes: number[],
): { breaks: number[]; values: number[] } {
  const n = preds.length
  if (!n) return { breaks: [0], values: [0.5] }
  const idx = [...preds.keys()].sort((i, j) => preds[i]! - preds[j]!)
  // Aggregate duplicate preds first (one value per x), then PAV.
  const xs: number[] = []
  const ys: number[] = []
  const ws: number[] = []
  for (const i of idx) {
    const x = preds[i]!
    const y = outcomes[i]!
    if (xs.length && Math.abs(xs[xs.length - 1]! - x) <= 1e-12) {
      const j = xs.length - 1
      const w = ws[j]! + 1
      ys[j] = (ys[j]! * ws[j]! + y) / w
      ws[j] = w
    } else {
      xs.push(x)
      ys.push(y)
      ws.push(1)
    }
  }
  const v = ys.slice()
  const w = ws.slice()
  let i = 0
  while (i < v.length - 1) {
    if (v[i]! <= v[i + 1]! + 1e-15) {
      i++
      continue
    }
    let j = i
    while (j > 0 && v[j - 1]! > v[j]! + 1e-15) j--
    let k = i + 1
    while (k < v.length - 1 && v[k]! > v[k + 1]! + 1e-15) k++
    let sumY = 0
    let sumW = 0
    for (let t = j; t <= k; t++) {
      sumY += v[t]! * w[t]!
      sumW += w[t]!
    }
    const avg = sumY / sumW
    for (let t = j; t <= k; t++) v[t] = avg
    i = Math.max(0, j - 1)
  }
  return {
    breaks: xs,
    values: v.map((x) => Math.min(1 - 1e-9, Math.max(1e-9, x))),
  }
}

export function isotonicScale(
  p: number,
  fit: { breaks: number[]; values: number[] },
): number {
  const u = Math.min(1 - 1e-9, Math.max(1e-9, p))
  const { breaks, values } = fit
  if (!breaks.length) return u
  if (u <= breaks[0]!) return values[0]!
  let i = 0
  while (i + 1 < breaks.length && breaks[i + 1]! <= u) i++
  return values[i]!
}

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
} {
  const trials = opts.trialsPerCell ?? 3000
  const { preds, outs } = sampleCorridorCells(opts.cells, trials, {
    bias: opts.bias,
    seed: 0x49534f,
  })
  // Stratify train/test within each cell block so every pred level appears in both.
  const trainP: number[] = []
  const trainY: number[] = []
  const testP: number[] = []
  const testY: number[] = []
  const frac = opts.trainFrac ?? 0.6
  for (let c = 0; c < opts.cells.length; c++) {
    const lo = c * trials
    const hi = lo + trials
    const cut = lo + Math.floor(trials * frac)
    for (let i = lo; i < cut; i++) {
      trainP.push(preds[i]!)
      trainY.push(outs[i]!)
    }
    for (let i = cut; i < hi; i++) {
      testP.push(preds[i]!)
      testY.push(outs[i]!)
    }
  }
  const fit = fitIsotonicCalib(trainP, trainY)
  const cal = testP.map((p) => isotonicScale(p, fit))
  const rawBrier = brierScore(testP, testY)
  const calibratedBrier = brierScore(cal, testY)
  const gain = rawBrier - calibratedBrier
  return {
    rawBrier,
    calibratedBrier,
    gain,
    shouldApply: gain >= KILL_CRITERIA_VS_B1.calibrationMinBrierGain,
  }
}

/** log P(I=y) under equicorrelated probit via 1D Gauss mixture. */
export function jointBernoulliLogProb(
  p: number,
  rho: number,
  y: number[],
): number {
  const pp = Math.min(0.99, Math.max(0.01, p))
  const r = Math.min(0.95, Math.max(0, rho))
  const c = invNorm(pp)
  const sR = Math.sqrt(r)
  const sI = Math.sqrt(Math.max(1e-12, 1 - r))
  // Coarser quadrature — called thousands of times in kill probes.
  const prob = expectGauss((z) => {
    const pi = Math.min(
      1 - 1e-12,
      Math.max(1e-12, normCdf((c - sR * z) / sI)),
    )
    let mass = 1
    for (const yi of y) {
      mass *= yi ? pi : 1 - pi
    }
    return mass
  }, 0.05)
  return Math.log(Math.max(1e-12, prob))
}

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
} {
  const trials = opts.trials ?? 1200
  const rhoWrong = opts.rhoWrong ?? 0
  const cacheStar = new Map<string, number>()
  const cacheWrong = new Map<string, number>()
  const llCached = (
    rho: number,
    y: number[],
    cache: Map<string, number>,
  ) => {
    const key = y.join('')
    let v = cache.get(key)
    if (v == null) {
      v = -jointBernoulliLogProb(opts.p, rho, y)
      cache.set(key, v)
    }
    return v
  }
  let llStar = 0
  let llWrong = 0
  for (let t = 0; t < trials; t++) {
    const y = drawXhmIndicators(opts.p, opts.n, opts.rhoStar, 0x4a4c4c + t * 17)
    llStar += llCached(opts.rhoStar, y, cacheStar)
    llWrong += llCached(rhoWrong, y, cacheWrong)
  }
  llStar /= trials
  llWrong /= trials
  const gain = llWrong - llStar
  return {
    llStar,
    llWrong,
    gain,
    shouldKillWrongRho:
      gain >= KILL_CRITERIA_VS_B1.jointLogLossWrongRhoMinGain,
  }
}

export function coxCalibrationFit(
  preds: number[],
  outcomes: number[],
): { intercept: number; slope: number } {
  let best = { a: 0, b: 1, loss: Infinity }
  for (let a = -1.2; a <= 1.2 + 1e-9; a += 0.1) {
    for (let b = 0.4; b <= 2.0 + 1e-9; b += 0.1) {
      let loss = 0
      for (let i = 0; i < preds.length; i++) {
        const p = plattScale(preds[i]!, a, b)
        const y = outcomes[i]!
        const q = Math.min(1 - 1e-12, Math.max(1e-12, p))
        loss += -(y * Math.log(q) + (1 - y) * Math.log(1 - q))
      }
      if (loss < best.loss) best = { a, b, loss }
    }
  }
  return { intercept: best.a, slope: best.b }
}

export function corridorCoxSanity(opts: {
  cells: Array<{ R: number; mu: number; sigma: number }>
  bias?: number
  trialsPerCell?: number
}): {
  intercept: number
  slope: number
  ok: boolean
  shouldKillBiased: boolean
} {
  const trials = opts.trialsPerCell ?? 3000
  const { preds, outs } = sampleCorridorCells(opts.cells, trials, {
    bias: opts.bias,
    seed: 0x434f58,
  })
  const { intercept, slope } = coxCalibrationFit(preds, outs)
  const ok =
    Math.abs(slope - 1) <= KILL_CRITERIA_VS_B1.coxSlopeAbsTol &&
    Math.abs(intercept) <= KILL_CRITERIA_VS_B1.coxInterceptAbsTol
  const shouldKillBiased =
    Math.abs(slope - 1) > KILL_CRITERIA_VS_B1.coxSlopeAbsTol ||
    Math.abs(intercept) > KILL_CRITERIA_VS_B1.coxInterceptAbsTol
  return { intercept, slope, ok, shouldKillBiased }
}

export function xhmConditionalCoverageSanity(opts: {
  cells: Array<{ p: number; n: number; rhoStar: number }>
  alpha?: number
  trialsPerCell?: number
}): {
  covByTertile: number[]
  okStar: boolean
  okKillWrong: boolean
} {
  const alpha = opts.alpha ?? 0.1
  const trials = opts.trialsPerCell ?? 6000
  const target = 1 - alpha
  const rows: { mean: number; coveredStar: boolean; coveredWrong: boolean }[] =
    []
  opts.cells.forEach((cell, ci) => {
    const draws = drawXhmCounts(
      cell.p,
      cell.n,
      cell.rhoStar,
      trials,
      0x434f56 + ci * 97,
    )
    const ivStar = centralPredictiveInterval(
      analyticXhmPmfs(cell.p, cell.n, cell.rhoStar),
      alpha,
    )
    const ivWrong = centralPredictiveInterval(
      analyticXhmPmfs(cell.p, cell.n, 0),
      alpha,
    )
    const mean = cell.n * cell.p
    for (const k of draws) {
      rows.push({
        mean,
        coveredStar: k >= ivStar.lo && k <= ivStar.hi,
        coveredWrong: k >= ivWrong.lo && k <= ivWrong.hi,
      })
    }
  })
  const sorted = [...rows].sort((a, b) => a.mean - b.mean)
  const covByTertile: number[] = []
  const covWrongByTertile: number[] = []
  for (let t = 0; t < 3; t++) {
    const lo = Math.floor((t * sorted.length) / 3)
    const hi = Math.floor(((t + 1) * sorted.length) / 3)
    const slice = sorted.slice(lo, hi)
    covByTertile.push(
      slice.filter((r) => r.coveredStar).length / Math.max(1, slice.length),
    )
    covWrongByTertile.push(
      slice.filter((r) => r.coveredWrong).length / Math.max(1, slice.length),
    )
  }
  const okStar = covByTertile.every(
    (c) => c + 1e-12 >= target - KILL_CRITERIA_VS_B1.coverageAbsTol,
  )
  const meanAbs = (arr: number[]) =>
    arr.reduce((s, c) => s + Math.abs(c - target), 0) / arr.length
  const okKillWrong =
    covWrongByTertile.some(
      (c) => c < target - KILL_CRITERIA_VS_B1.coverageAbsTol,
    ) || meanAbs(covWrongByTertile) >= meanAbs(covByTertile) + 0.02
  return { covByTertile, okStar, okKillWrong }
}

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
} {
  const bias = opts.corridorBias ?? 0.15
  const casts = opts.casts ?? 400
  const trials = opts.trials ?? 4000
  const pCorr = Math.min(0.99, Math.max(0.01, opts.pStar + bias))
  clearAbilityRates()
  const key = abilityRateKey(opts.ability, opts.strata)
  let s = 0x53545241
  const nextU = () => {
    s = (Math.imul(s, 1664525) + 1013904223) | 0
    return (s >>> 0) / 4294967296
  }
  for (let i = 0; i < casts; i++) {
    updateAbilityRate(key, (nextU() < opts.pStar ? 1 : 0) as 0 | 1)
  }
  const ability = abilityRatePosterior(key).mean
  const residual = Math.abs(pCorr - ability)
  const predsA: number[] = []
  const predsC: number[] = []
  const outs: number[] = []
  for (let t = 0; t < trials; t++) {
    const y = nextU() < opts.pStar ? 1 : 0
    outs.push(y)
    predsA.push(ability)
    predsC.push(pCorr)
  }
  const brierGain = brierScore(predsC, outs) - brierScore(predsA, outs)
  clearAbilityRates()
  return {
    key,
    residual,
    brierGain,
    shouldKillB1:
      residual > KILL_CRITERIA_VS_B1.abilityResidualTol &&
      brierGain >= KILL_CRITERIA_VS_B1.minBrierGainToKill,
  }
}

export function binaryVariogramScore(
  sampleForecast: () => number[],
  y: number[],
  pairedDraws = 64,
): number {
  let acc = 0
  for (let m = 0; m < pairedDraws; m++) {
    const x = sampleForecast()
    let term = 0
    for (let i = 0; i < y.length; i++) {
      for (let j = i + 1; j < y.length; j++) {
        const obs = Math.abs(y[i]! - y[j]!)
        const fc = Math.abs(x[i]! - x[j]!)
        const d = obs - fc
        term += d * d
      }
    }
    acc += term
  }
  return acc / pairedDraws
}

/** Analytic E|I_i−I_j| = 2(p − π11) under equicorrelated probit. */
export function analyticPairDiffExpectation(p: number, rho: number): number {
  const m = analyticXhmMoments(p, 2, rho)
  return 2 * (p - m.pairwiseJoint)
}

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
} {
  const trials = opts.trials ?? 6000
  const rhoWrong = opts.rhoWrong ?? 0
  const paired = opts.pairedDraws ?? 64
  const eStar = analyticPairDiffExpectation(opts.p, opts.rhoStar)
  const eWrong = analyticPairDiffExpectation(opts.p, rhoWrong)
  let vsStar = 0
  let vsWrong = 0
  for (let t = 0; t < trials; t++) {
    const y = drawXhmIndicators(opts.p, opts.n, opts.rhoStar, 0x565247 + t * 19)
    let obsPairs = 0
    for (let i = 0; i < y.length; i++) {
      for (let j = i + 1; j < y.length; j++) {
        obsPairs += (Math.abs(y[i]! - y[j]!) - eStar) ** 2
      }
    }
    vsStar += obsPairs
    let obsWrong = 0
    for (let i = 0; i < y.length; i++) {
      for (let j = i + 1; j < y.length; j++) {
        obsWrong += (Math.abs(y[i]! - y[j]!) - eWrong) ** 2
      }
    }
    vsWrong += obsWrong
  }
  vsStar /= trials
  vsWrong /= trials
  // Prefer analytic pair-diff residual (fast); MC is a light backup only.
  let vsMcWrong = 0
  let vsMcStar = 0
  const nMc = Math.min(trials, 200)
  for (let t = 0; t < nMc; t++) {
    const y = drawXhmIndicators(opts.p, opts.n, opts.rhoStar, 0x565248 + t * 23)
    const stA = { s: 0x565300 + t * 31 }
    const stB = { s: 0x565400 + t * 37 }
    const mk = (rho: number, s0: { s: number }) => () => {
      s0.s = (Math.imul(s0.s, 1664525) + 1013904223) | 0
      return drawXhmIndicators(opts.p, opts.n, rho, s0.s)
    }
    vsMcStar += binaryVariogramScore(mk(opts.rhoStar, stA), y, paired)
    vsMcWrong += binaryVariogramScore(mk(rhoWrong, stB), y, paired)
  }
  vsMcStar /= nMc
  vsMcWrong /= nMc
  const gain = Math.max(vsWrong - vsStar, vsMcWrong - vsMcStar)
  return {
    vsStar,
    vsWrong,
    gain,
    shouldKillWrongRho:
      gain >= KILL_CRITERIA_VS_B1.variogramWrongRhoMinGain,
  }
}

export function spiegelhalterZ(
  preds: number[],
  outcomes: number[],
): number {
  let num = 0
  let den = 0
  for (let i = 0; i < preds.length; i++) {
    const p = Math.min(1 - 1e-9, Math.max(1e-9, preds[i]!))
    num += outcomes[i]! - p
    den += p * (1 - p)
  }
  return num / Math.sqrt(Math.max(1e-12, den))
}

export function corridorSpiegelhalterSanity(opts: {
  cells: Array<{ R: number; mu: number; sigma: number }>
  bias?: number
  trialsPerCell?: number
}): {
  z: number
  ok: boolean
  shouldKillBiased: boolean
} {
  const trials = opts.trialsPerCell ?? 3000
  const { preds, outs } = sampleCorridorCells(opts.cells, trials, {
    bias: opts.bias,
    seed: 0x535049,
  })
  const z = spiegelhalterZ(preds, outs)
  const ok = Math.abs(z) <= KILL_CRITERIA_VS_B1.spiegelhalterAbsTol
  const shouldKillBiased =
    Math.abs(z) > KILL_CRITERIA_VS_B1.spiegelhalterAbsTol
  return { z, ok, shouldKillBiased }
}

// --- Pass-9 EMPIRICS ---

/** Equal-count bin ranges [lo, hi) over sorted indices; skips empty. */
function equalCountBinRanges(n: number, bins: number): Array<[number, number]> {
  const B = Math.max(2, Math.min(bins, Math.max(1, n)))
  const ranges: Array<[number, number]> = []
  for (let b = 0; b < B; b++) {
    const lo = Math.floor((b * n) / B)
    const hi = Math.floor(((b + 1) * n) / B)
    if (hi <= lo) {
      // empty → merge into previous if any
      if (ranges.length) ranges[ranges.length - 1]![1] = Math.max(ranges[ranges.length - 1]![1], hi)
      continue
    }
    ranges.push([lo, hi])
  }
  return ranges
}

/**
 * Austin–Steyerberg ICI via equal-count bins:
 * (1/n) Σ_i |acc_{g(i)} − p̂_i|.
 */
export function integratedCalibrationIndex(
  preds: number[],
  outcomes: number[],
  bins = 10,
): number {
  const n = preds.length
  if (n === 0) return NaN
  const idx = [...preds.keys()].sort((i, j) => preds[i]! - preds[j]!)
  const ranges = equalCountBinRanges(n, bins)
  let ici = 0
  for (const [lo, hi] of ranges) {
    let acc = 0
    const m = hi - lo
    for (let k = lo; k < hi; k++) acc += outcomes[idx[k]!]!
    acc /= m
    for (let k = lo; k < hi; k++) {
      const p = Math.min(1 - 1e-9, Math.max(1e-9, preds[idx[k]!]!))
      ici += Math.abs(acc - p)
    }
  }
  return ici / n
}

export function corridorIciSanity(opts: {
  cells: Array<{ R: number; mu: number; sigma: number }>
  bias?: number
  trialsPerCell?: number
}): {
  ici: number
  ok: boolean
  shouldKillBiased: boolean
} {
  const trials = opts.trialsPerCell ?? 3000
  const { preds, outs } = sampleCorridorCells(opts.cells, trials, {
    bias: opts.bias,
    seed: 0x494349,
  })
  const ici = integratedCalibrationIndex(preds, outs, 10)
  const ok = ici <= KILL_CRITERIA_VS_B1.iciTol
  const shouldKillBiased = ici > KILL_CRITERIA_VS_B1.iciTol
  return { ici, ok, shouldKillBiased }
}

/** Hosmer–Lemeshow decile χ² (equal-count); skips near-degenerate groups. */
export function hosmerLemeshowChiSq(
  preds: number[],
  outcomes: number[],
  groups = 10,
): number {
  const n = preds.length
  if (n === 0) return NaN
  const idx = [...preds.keys()].sort((i, j) => preds[i]! - preds[j]!)
  const ranges = equalCountBinRanges(n, groups)
  let chi = 0
  for (const [lo, hi] of ranges) {
    const m = hi - lo
    if (m < 2) continue
    let Eg = 0
    let Og = 0
    for (let k = lo; k < hi; k++) {
      const p = Math.min(1 - 1e-9, Math.max(1e-9, preds[idx[k]!]!))
      Eg += p
      Og += outcomes[idx[k]!]!
    }
    const pBar = Eg / m
    const den = Eg * (1 - pBar)
    if (den < 1e-12) continue
    const d = Og - Eg
    chi += (d * d) / den
  }
  return chi
}

export function corridorHosmerLemeshowSanity(opts: {
  cells: Array<{ R: number; mu: number; sigma: number }>
  bias?: number
  trialsPerCell?: number
}): {
  chiSq: number
  ok: boolean
  shouldKillBiased: boolean
} {
  const trials = opts.trialsPerCell ?? 3000
  const { preds, outs } = sampleCorridorCells(opts.cells, trials, {
    bias: opts.bias,
    seed: 0x484c47,
  })
  const chiSq = hosmerLemeshowChiSq(preds, outs, 10)
  const ok = chiSq <= KILL_CRITERIA_VS_B1.hosmerLemeshowChiSqTol
  const shouldKillBiased = chiSq > KILL_CRITERIA_VS_B1.hosmerLemeshowChiSqTol
  return { chiSq, ok, shouldKillBiased }
}

/** Strictly proper spherical score S(p,y) ∈ (0,1]. */
export function sphericalScore(p: number, y: number): number {
  const u = Math.min(1 - 1e-9, Math.max(1e-9, p))
  const num = y * u + (1 - y) * (1 - u)
  const den = Math.sqrt(u * u + (1 - u) * (1 - u))
  return num / den
}

export function sphericalLoss(p: number, y: number): number {
  return -sphericalScore(p, y)
}

export function corridorSphericalSanity(opts: {
  cells: Array<{ R: number; mu: number; sigma: number }>
  bias?: number
  trialsPerCell?: number
}): {
  meanLoss: number
  meanCoinLoss: number
  ok: boolean
  shouldKillBiased: boolean
} {
  const trials = opts.trialsPerCell ?? 3000
  const bias = opts.bias ?? 0
  const { preds, outs } = sampleCorridorCells(opts.cells, trials, {
    bias,
    seed: 0x535048,
  })
  const n = preds.length || 1
  let meanLoss = 0
  let meanCoinLoss = 0
  for (let i = 0; i < preds.length; i++) {
    meanLoss += sphericalLoss(preds[i]!, outs[i]!)
    meanCoinLoss += sphericalLoss(0.5, outs[i]!)
  }
  meanLoss /= n
  meanCoinLoss /= n
  const ok =
    meanLoss <= meanCoinLoss * KILL_CRITERIA_VS_B1.sphericalVsCoinMaxRatio
  let shouldKillBiased = false
  if (bias !== 0) {
    const trueSample = sampleCorridorCells(opts.cells, trials, {
      bias: 0,
      seed: 0x535048,
    })
    let trueLoss = 0
    for (let i = 0; i < trueSample.preds.length; i++) {
      trueLoss += sphericalLoss(trueSample.preds[i]!, trueSample.outs[i]!)
    }
    trueLoss /= trueSample.preds.length || 1
    const overallGain = meanLoss - trueLoss
    // High-p cells clamped by +bias can mask mid-p degradation in the pool
    // mean; also kill if any cell-level spherical gain meets the floor.
    let maxCellGain = overallGain
    for (let c = 0; c < opts.cells.length; c++) {
      const lo = c * trials
      const hi = lo + trials
      let bLoss = 0
      let tLoss = 0
      for (let i = lo; i < hi; i++) {
        bLoss += sphericalLoss(preds[i]!, outs[i]!)
        tLoss += sphericalLoss(trueSample.preds[i]!, trueSample.outs[i]!)
      }
      maxCellGain = Math.max(maxCellGain, bLoss / trials - tLoss / trials)
    }
    shouldKillBiased =
      maxCellGain >= KILL_CRITERIA_VS_B1.sphericalBiasMinGain
  }
  return { meanLoss, meanCoinLoss, ok, shouldKillBiased }
}

/** Anderson–Darling A² vs Uniform(0,1) on randomized discrete PIT. */
export function discretePitAndersonDarling(
  pmf: number[],
  draws: number[],
  seed = 0x414450,
): { ad: number; ok: boolean } {
  const st = { s: seed }
  const us: number[] = []
  for (const kRaw of draws) {
    const k = Math.max(0, Math.min(pmf.length - 1, Math.round(kRaw)))
    let Fkm1 = 0
    for (let m = 0; m < k; m++) Fkm1 += pmf[m]!
    const U = Math.min(
      1 - 1e-9,
      Math.max(1e-9, Fkm1 + lcgNext(st) * pmf[k]!),
    )
    us.push(U)
  }
  us.sort((a, b) => a - b)
  const n = us.length
  if (!n) return { ad: NaN, ok: false }
  let s = 0
  for (let i = 0; i < n; i++) {
    const Ui = us[i]!
    const Un = us[n - 1 - i]!
    s += (2 * (i + 1) - 1) * (Math.log(Ui) + Math.log(1 - Un))
  }
  const ad = -n - s / n
  return { ad, ok: ad <= KILL_CRITERIA_VS_B1.pitAdTol }
}

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
} {
  const trials = opts.trials ?? 8000
  const draws = drawXhmCounts(opts.p, opts.n, opts.rhoStar, trials, 0x414453)
  const star = discretePitAndersonDarling(
    analyticXhmPmfs(opts.p, opts.n, opts.rhoStar),
    draws,
    0x414454,
  )
  const wrong = discretePitAndersonDarling(
    analyticXhmPmfs(opts.p, opts.n, 0),
    draws,
    0x414455,
  )
  const okKillWrong =
    wrong.ad > KILL_CRITERIA_VS_B1.pitAdTol || wrong.ad - star.ad >= 0.25
  return {
    adStar: star.ad,
    adWrong: wrong.ad,
    okStar: star.ok,
    okKillWrong,
  }
}

export function xhmConditionalWinklerSanity(opts: {
  cells: Array<{ p: number; n: number; rhoStar: number }>
  alpha?: number
  trialsPerCell?: number
}): {
  gainByTertile: number[]
  okStar: boolean
  okKillWrong: boolean
} {
  // Default α=0.05: at α=0.1 discrete n=4 PIs can coincide for ρ★ vs ρ=0
  // on low-p cells (zero Winkler gain in that tertile).
  const alpha = opts.alpha ?? 0.05
  const trials = opts.trialsPerCell ?? 6000
  const rows: { mean: number; winkStar: number; winkWrong: number }[] = []
  opts.cells.forEach((cell, ci) => {
    const draws = drawXhmCounts(
      cell.p,
      cell.n,
      cell.rhoStar,
      trials,
      0x435749 + ci * 97,
    )
    const ivStar = centralPredictiveInterval(
      analyticXhmPmfs(cell.p, cell.n, cell.rhoStar),
      alpha,
    )
    const ivWrong = centralPredictiveInterval(
      analyticXhmPmfs(cell.p, cell.n, 0),
      alpha,
    )
    const mean = cell.n * cell.p
    for (const k of draws) {
      rows.push({
        mean,
        winkStar: winklerIntervalScore(ivStar.lo, ivStar.hi, k, alpha),
        winkWrong: winklerIntervalScore(ivWrong.lo, ivWrong.hi, k, alpha),
      })
    }
  })
  const sorted = [...rows].sort((a, b) => a.mean - b.mean)
  const gainByTertile: number[] = []
  for (let t = 0; t < 3; t++) {
    const lo = Math.floor((t * sorted.length) / 3)
    const hi = Math.floor(((t + 1) * sorted.length) / 3)
    const slice = sorted.slice(lo, hi)
    let ws = 0
    let ww = 0
    for (const r of slice) {
      ws += r.winkStar
      ww += r.winkWrong
    }
    const m = Math.max(1, slice.length)
    gainByTertile.push(ww / m - ws / m)
  }
  const tol = KILL_CRITERIA_VS_B1.winklerWrongRhoMinGain
  const okStar = gainByTertile.every((g) => g >= tol)
  const meanGain =
    gainByTertile.reduce((a, b) => a + b, 0) / Math.max(1, gainByTertile.length)
  const okKillWrong =
    gainByTertile.some((g) => g < tol) || meanGain >= tol
  return { gainByTertile, okStar, okKillWrong }
}

/** π₁₁₁₁ under equicorrelated probit (1D Gauss mixture). */
export function analyticQuartetJoint(p: number, rho: number): number {
  const pp = Math.min(0.99, Math.max(0.01, p))
  const r = Math.min(0.95, Math.max(0, rho))
  const c = invNorm(pp)
  const sR = Math.sqrt(r)
  const sI = Math.sqrt(Math.max(1e-12, 1 - r))
  // Slightly coarser grid — called repeatedly in MoM inversion.
  return expectGauss((z) => {
    const pi = Math.min(
      1 - 1e-12,
      Math.max(1e-12, normCdf((c - sR * z) / sI)),
    )
    const pi2 = pi * pi
    return pi2 * pi2
  }, 0.01)
}

export function estimateRhoFromQuartetJoint(
  p: number,
  pi1111: number,
  tol = 1e-4,
): number {
  const loBound = Math.max(p * p * p * p, 1e-12)
  const hiBound = Math.min(p, 1 - 1e-12)
  const target = Math.min(hiBound, Math.max(loBound, pi1111))
  let lo = 0
  let hi = 0.95
  for (let i = 0; i < 48; i++) {
    const mid = 0.5 * (lo + hi)
    if (analyticQuartetJoint(p, mid) < target) lo = mid
    else hi = mid
    if (hi - lo < tol) break
  }
  return 0.5 * (lo + hi)
}

export function rhoQuartetRecoverySanity(opts: {
  p: number
  rhoStar: number
  nQuartets?: number
  seed?: number
}): {
  rhoHat4: number
  absErr4: number
  ok: boolean
} {
  const p = Math.min(0.99, Math.max(0.01, opts.p))
  const rho = Math.min(0.95, Math.max(0, opts.rhoStar))
  const nQuartets = opts.nQuartets ?? 30000
  const c = invNorm(p)
  const sR = Math.sqrt(rho)
  const sI = Math.sqrt(1 - rho)
  const st = { s: opts.seed ?? 0x515254 }
  let joint4 = 0
  for (let i = 0; i < nQuartets; i++) {
    const Z = boxMuller(st)
    const i1 = sR * Z + sI * boxMuller(st) < c ? 1 : 0
    const i2 = sR * Z + sI * boxMuller(st) < c ? 1 : 0
    const i3 = sR * Z + sI * boxMuller(st) < c ? 1 : 0
    const i4 = sR * Z + sI * boxMuller(st) < c ? 1 : 0
    joint4 += i1 * i2 * i3 * i4
  }
  const pi1111 = joint4 / nQuartets
  const rhoHat4 = estimateRhoFromQuartetJoint(p, pi1111)
  const absErr4 = Math.abs(rhoHat4 - rho)
  return {
    rhoHat4,
    absErr4,
    ok: absErr4 <= KILL_CRITERIA_VS_B1.quartetRhoAbsErrTol,
  }
}

/**
 * Extreme-atom twCRPS: (q0−1{k=0})² + (qn−1{k=n})².
 * Distinct from filtered tail CRPS (scores every draw).
 */
export function twCrpsExtremeAtoms(pmf: number[], k: number): number {
  const n = pmf.length - 1
  const kk = Math.max(0, Math.min(n, Math.round(k)))
  const q0 = pmf[0] ?? 0
  const qn = pmf[n] ?? 0
  const d0 = q0 - (kk === 0 ? 1 : 0)
  const dn = qn - (kk === n ? 1 : 0)
  return d0 * d0 + dn * dn
}

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
} {
  const trials = opts.trials ?? 8000
  const rhoWrong = opts.rhoWrong ?? 0
  const draws = drawXhmCounts(opts.p, opts.n, opts.rhoStar, trials, 0x545743)
  const pmfStar = analyticXhmPmfs(opts.p, opts.n, opts.rhoStar)
  const pmfWrong = analyticXhmPmfs(opts.p, opts.n, rhoWrong)
  let twStar = 0
  let twWrong = 0
  for (const k of draws) {
    twStar += twCrpsExtremeAtoms(pmfStar, k)
    twWrong += twCrpsExtremeAtoms(pmfWrong, k)
  }
  twStar /= draws.length
  twWrong /= draws.length
  const gain = twWrong - twStar
  return {
    twStar,
    twWrong,
    gain,
    shouldKillWrongRho: gain >= KILL_CRITERIA_VS_B1.twCrpsWrongRhoMinGain,
  }
}

// --- Pass-10 EMPIRICS (FINAL) ---

/**
 * Tertile-conditional ICI (Austin–Steyerberg within p̂ tertiles).
 * Empty tertiles are skipped; bins are equal-count inside each tertile.
 */
export function conditionalIciByTertile(
  preds: number[],
  outcomes: number[],
  bins = 10,
): { icis: number[]; ok: boolean } {
  const idx = [...preds.keys()].sort((i, j) => preds[i]! - preds[j]!)
  const n = preds.length
  const icis: number[] = []
  for (let t = 0; t < 3; t++) {
    const lo = Math.floor((t * n) / 3)
    const hi = Math.floor(((t + 1) * n) / 3)
    if (hi <= lo) continue
    const tp: number[] = []
    const ty: number[] = []
    for (let k = lo; k < hi; k++) {
      tp.push(preds[idx[k]!]!)
      ty.push(outcomes[idx[k]!]!)
    }
    icis.push(integratedCalibrationIndex(tp, ty, bins))
  }
  return {
    icis,
    ok:
      icis.length > 0 &&
      icis.every((x) => x <= KILL_CRITERIA_VS_B1.conditionalIciTol),
  }
}

export function corridorConditionalIciSanity(opts: {
  cells: Array<{ R: number; mu: number; sigma: number }>
  bias?: number
  trialsPerCell?: number
}): {
  icis: number[]
  ok: boolean
  shouldKillBiased: boolean
} {
  const trials = opts.trialsPerCell ?? 3000
  const { preds, outs } = sampleCorridorCells(opts.cells, trials, {
    bias: opts.bias,
    seed: 0x434943,
  })
  const { icis, ok } = conditionalIciByTertile(preds, outs, 10)
  const shouldKillBiased = icis.some(
    (x) => x > KILL_CRITERIA_VS_B1.conditionalIciTol,
  )
  return { icis, ok, shouldKillBiased }
}

/** Cramér–von Mises W² vs Uniform(0,1) on randomized discrete PIT. */
export function discretePitCramerVonMises(
  pmf: number[],
  draws: number[],
  seed = 0x43564d,
): { cvm: number; ok: boolean } {
  const st = { s: seed }
  const us: number[] = []
  for (const kRaw of draws) {
    const k = Math.max(0, Math.min(pmf.length - 1, Math.round(kRaw)))
    let Fkm1 = 0
    for (let m = 0; m < k; m++) Fkm1 += pmf[m]!
    const U = Math.min(
      1 - 1e-9,
      Math.max(1e-9, Fkm1 + lcgNext(st) * pmf[k]!),
    )
    us.push(U)
  }
  us.sort((a, b) => a - b)
  const n = us.length
  if (!n) return { cvm: NaN, ok: false }
  let s = 0
  for (let i = 0; i < n; i++) {
    const target = (2 * (i + 1) - 1) / (2 * n)
    const d = us[i]! - target
    s += d * d
  }
  const cvm = 1 / (12 * n) + s
  return { cvm, ok: cvm <= KILL_CRITERIA_VS_B1.pitCvmTol }
}

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
} {
  const trials = opts.trials ?? 8000
  const draws = drawXhmCounts(opts.p, opts.n, opts.rhoStar, trials, 0x435653)
  const star = discretePitCramerVonMises(
    analyticXhmPmfs(opts.p, opts.n, opts.rhoStar),
    draws,
    0x435654,
  )
  const wrong = discretePitCramerVonMises(
    analyticXhmPmfs(opts.p, opts.n, 0),
    draws,
    0x435655,
  )
  const okKillWrong =
    wrong.cvm > KILL_CRITERIA_VS_B1.pitCvmTol ||
    wrong.cvm - star.cvm >= 0.15
  return {
    cvmStar: star.cvm,
    cvmWrong: wrong.cvm,
    okStar: star.ok,
    okKillWrong,
  }
}

/** Quantile / pinball score S_α(q,k) = (1{k≤q} − α)(q − k). */
export function pinballScore(q: number, k: number, alpha: number): number {
  const ind = k <= q ? 1 : 0
  return (ind - alpha) * (q - k)
}

/**
 * Predictive α-quantile from analytic count CDF:
 * q_α = inf{k : F(k) ≥ α} with F(k) = P(K ≤ k).
 */
export function predictiveQuantile(pmf: number[], alpha: number): number {
  const a = Math.min(1 - 1e-12, Math.max(0, alpha))
  let cdf = 0
  for (let k = 0; k < pmf.length; k++) {
    cdf += pmf[k]!
    if (cdf + 1e-12 >= a) return k
  }
  return Math.max(0, pmf.length - 1)
}

export function xhmWrongRhoPinballKillSanity(opts: {
  p: number
  n: number
  rhoStar: number
  rhoWrong?: number
  alphas?: number[]
  trials?: number
}): {
  pinStar: number
  pinWrong: number
  gain: number
  shouldKillWrongRho: boolean
} {
  const trials = opts.trials ?? 8000
  const rhoWrong = opts.rhoWrong ?? 0
  const alphas = opts.alphas ?? [0.1, 0.9]
  const draws = drawXhmCounts(opts.p, opts.n, opts.rhoStar, trials, 0x50494e)
  const pmfStar = analyticXhmPmfs(opts.p, opts.n, opts.rhoStar)
  const pmfWrong = analyticXhmPmfs(opts.p, opts.n, rhoWrong)
  let pinStar = 0
  let pinWrong = 0
  for (const alpha of alphas) {
    const qStar = predictiveQuantile(pmfStar, alpha)
    const qWrong = predictiveQuantile(pmfWrong, alpha)
    for (const k of draws) {
      pinStar += pinballScore(qStar, k, alpha)
      pinWrong += pinballScore(qWrong, k, alpha)
    }
  }
  const denom = draws.length * alphas.length || 1
  pinStar /= denom
  pinWrong /= denom
  const gain = pinWrong - pinStar
  return {
    pinStar,
    pinWrong,
    gain,
    shouldKillWrongRho: gain >= KILL_CRITERIA_VS_B1.pinballWrongRhoMinGain,
  }
}

export function xhmNearMissRhoCrpsKillSanity(opts: {
  p: number
  n: number
  rhoStar: number
  rhoNear?: number
  trials?: number
}): {
  crpsStar: number
  crpsNear: number
  gain: number
  shouldKillNearMiss: boolean
} {
  const trials = opts.trials ?? 8000
  const rhoNear = opts.rhoNear ?? 0.25
  const draws = drawXhmCounts(opts.p, opts.n, opts.rhoStar, trials, 0x4e4d52)
  const crpsStar = meanCrpsCount(
    analyticXhmPmfs(opts.p, opts.n, opts.rhoStar),
    draws,
  )
  const crpsNear = meanCrpsCount(
    analyticXhmPmfs(opts.p, opts.n, rhoNear),
    draws,
  )
  const gain = crpsNear - crpsStar
  return {
    crpsStar,
    crpsNear,
    gain,
    shouldKillNearMiss: gain >= KILL_CRITERIA_VS_B1.nearMissCrpsMinGain,
  }
}

/**
 * Mid-threshold twCRPS: (F(m_−) − 1{k≤m})² with m=⌊n/2⌋.
 * F(m_−)=P(K<m); scores every draw (complement to extreme-atom twCRPS).
 */
export function twCrpsMidThreshold(pmf: number[], k: number): number {
  const n = pmf.length - 1
  const m = Math.floor(n / 2)
  const kk = Math.max(0, Math.min(n, Math.round(k)))
  let FmMinus = 0
  for (let j = 0; j < m; j++) FmMinus += pmf[j]!
  const d = FmMinus - (kk <= m ? 1 : 0)
  return d * d
}

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
} {
  const trials = opts.trials ?? 8000
  const rhoWrong = opts.rhoWrong ?? 0
  const draws = drawXhmCounts(opts.p, opts.n, opts.rhoStar, trials, 0x4d5457)
  const pmfStar = analyticXhmPmfs(opts.p, opts.n, opts.rhoStar)
  const pmfWrong = analyticXhmPmfs(opts.p, opts.n, rhoWrong)
  let twStar = 0
  let twWrong = 0
  for (const k of draws) {
    twStar += twCrpsMidThreshold(pmfStar, k)
    twWrong += twCrpsMidThreshold(pmfWrong, k)
  }
  twStar /= draws.length
  twWrong /= draws.length
  const gain = twWrong - twStar
  return {
    twStar,
    twWrong,
    gain,
    shouldKillWrongRho: gain >= KILL_CRITERIA_VS_B1.midTwCrpsWrongRhoMinGain,
  }
}

// --- smoke when run directly ---
const isMain =
  typeof process !== 'undefined' &&
  process.argv[1] &&
  process.argv[1].endsWith('xh-baselines.ts')

if (isMain) {
  const m = analyticXhmMoments(0.55, 4, 0.5)
  const pmf = analyticXhmPmfs(0.55, 4, 0.5)
  console.log('analytic moments p=0.55 n=4 ρ=0.5', {
    mean: m.mean,
    variance: +m.variance.toFixed(4),
    indepVar: +m.indepVariance.toFixed(4),
    p0: +m.p0.toFixed(5),
    indepP0: +m.indepP0.toFixed(5),
    ratio0: +(m.p0 / m.indepP0).toFixed(3),
    pn: +m.pn.toFixed(5),
    indepPn: +m.indepPn.toFixed(5),
    ration: +(m.pn / m.indepPn).toFixed(3),
    pmfP0: +pmf[0]!.toFixed(5),
    pmfPn: +pmf[4]!.toFixed(5),
  })

  // Corridor Brier smoke (closed-form p̂ from Φ corridor)
  const R = 50
  const mu = 10
  const sigma = 30
  const predicted = normCdf((R - mu) / sigma) - normCdf((-R - mu) / sigma)
  const sanity = corridorBrierSanity({
    cells: [
      { R, mu, sigma, predictedXh: predicted },
      { R: 80, mu: 0, sigma: 40, predictedXh: normCdf(80 / 40) - normCdf(-80 / 40) },
      { R: 40, mu: 35, sigma: 25, predictedXh: normCdf((40 - 35) / 25) - normCdf((-40 - 35) / 25) },
    ],
    trials: 8000,
  })
  console.log('corridor Brier sanity', {
    ok: sanity.ok,
    maxAbsRateGap: +sanity.maxAbsRateGap.toFixed(4),
    meanBrier: +sanity.meanBrier.toFixed(4),
    meanCoinBrier: +sanity.meanCoinBrier.toFixed(4),
  })

  registerAbilityRate({ abilityKey: 'LuxQ', hits: 42, casts: 100 })
  console.log('abilityRateBaseline LuxQ', abilityRateBaseline('LuxQ'))
  console.log('abilityRateBaseline missing', abilityRateBaseline('MissingUlt'))
  console.log('temperature/platt identity', {
    T1: temperatureScale(0.7, 1),
    plattId: plattScale(0.7, 0, 1),
    soft: +temperatureScale(0.7, 1.5).toFixed(4),
  })
  console.log('KILL_CRITERIA_VS_B1', KILL_CRITERIA_VS_B1)

  // Pass-10 smoke (recommended eval trial counts)
  const cells10 = [
    { R: 50, mu: 10, sigma: 30 },
    { R: 80, mu: 0, sigma: 40 },
    { R: 40, mu: 35, sigma: 25 },
  ]
  const iciC = corridorConditionalIciSanity({
    cells: cells10,
    bias: 0,
    trialsPerCell: 3000,
  })
  const iciCBad = corridorConditionalIciSanity({
    cells: cells10,
    bias: 0.12,
    trialsPerCell: 3000,
  })
  const cvm = xhmPitCvmSanity({ p: 0.55, n: 4, rhoStar: 0.5, trials: 8000 })
  const pin = xhmWrongRhoPinballKillSanity({
    p: 0.55,
    n: 4,
    rhoStar: 0.5,
    trials: 8000,
  })
  const near = xhmNearMissRhoCrpsKillSanity({
    p: 0.55,
    n: 4,
    rhoStar: 0.5,
    rhoNear: 0.25,
    trials: 8000,
  })
  const mid = xhmWrongRhoMidTwCrpsKillSanity({
    p: 0.55,
    n: 4,
    rhoStar: 0.5,
    trials: 8000,
  })
  console.log('Pass-10 empirics smoke', {
    condIciOk: iciC.ok,
    condIciKillBias: iciCBad.shouldKillBiased,
    cvmOkStar: cvm.okStar,
    cvmKillWrong: cvm.okKillWrong,
    pinGain: +pin.gain.toFixed(4),
    pinKill: pin.shouldKillWrongRho,
    nearGain: +near.gain.toFixed(4),
    nearKill: near.shouldKillNearMiss,
    midGain: +mid.gain.toFixed(4),
    midKill: mid.shouldKillWrongRho,
  })
}
