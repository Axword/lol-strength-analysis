/**
 * Sqrt-time trade bins for cross-check diagnostics.
 *
 * Idea: split a trade of length T into pieces of width √T, measure
 * signed HP-error variance in each piece, rank pieces to decide WHERE
 * to investigate. Early high-variance pieces get a compounding weight
 * (error there poisons later seconds).
 *
 * Anti-overfit (hard):
 * - Diagnostic ranking only — never a fit target / loss to minimize on
 *   the same fight.
 * - Skip bins with < minSamples (variance undefined).
 * - Do not tune kit numbers from one check's top bin; require the same
 *   phase to rank high on ≥2 independent checks (or full+burst) before
 *   treating it as a real bug class.
 */
export type ErrPoint = {
  tSec: number
  signedErr: number
  absErr: number
}

export type SqrtBin = {
  index: number
  tStartSec: number
  tEndSec: number
  n: number
  maeHp: number | null
  meanSignedErr: number | null
  /** Sample variance of (modelHp − actualHp). null if n < minSamples. */
  varianceSignedErr: number | null
  rmsErr: number | null
  /** (binsLeft / nBins) — early slices weigh more for investigation order. */
  compoundWeight: number
  /** variance * compoundWeight when variance known; else null. */
  priority: number | null
}

export type SqrtBinAnalysis = {
  schema: 'pro-grid-sqrt-bin-v1'
  diagnosticOnly: true
  doNotFitOnThisSample: true
  durationSec: number
  pieceWidthSec: number
  binCount: number
  minSamples: number
  bins: SqrtBin[]
  /** Highest priority first; empty if nothing measurable. */
  optimizeOrder: Array<{
    index: number
    tStartSec: number
    tEndSec: number
    varianceSignedErr: number
    priority: number
    reason: string
  }>
  antiOverfit: {
    rule: string
    confirmBeforeActing: string
  }
}

export function sqrtPieceWidthSec(durationSec: number): number {
  return Math.sqrt(Math.max(durationSec, 1e-9))
}

function mean(xs: number[]): number {
  return xs.reduce((s, x) => s + x, 0) / xs.length
}

function sampleVariance(xs: number[]): number | null {
  if (xs.length < 2) return null
  const m = mean(xs)
  let acc = 0
  for (const x of xs) acc += (x - m) * (x - m)
  return acc / (xs.length - 1)
}

/**
 * Bin error points into √T-wide slices over [0, durationSec].
 */
export function analyzeSqrtBins(
  errors: ErrPoint[],
  durationSec: number,
  minSamples = 2,
): SqrtBinAnalysis {
  const T = Math.max(durationSec, 1e-9)
  const pieceW = sqrtPieceWidthSec(T)
  const binCount = Math.max(1, Math.ceil(T / pieceW))
  const buckets: number[][] = Array.from({ length: binCount }, () => [])
  const absBuckets: number[][] = Array.from({ length: binCount }, () => [])

  for (const e of errors) {
    if (!Number.isFinite(e.tSec) || !Number.isFinite(e.signedErr)) continue
    let idx = Math.floor(e.tSec / pieceW)
    if (idx < 0) idx = 0
    if (idx >= binCount) idx = binCount - 1
    buckets[idx]!.push(e.signedErr)
    absBuckets[idx]!.push(e.absErr)
  }

  const bins: SqrtBin[] = []
  for (let i = 0; i < binCount; i++) {
    const signed = buckets[i]!
    const abs = absBuckets[i]!
    const n = signed.length
    const compoundWeight = (binCount - i) / binCount
    const varianceSignedErr = n >= minSamples ? sampleVariance(signed) : null
    const meanSignedErr = n > 0 ? mean(signed) : null
    const maeHp = n > 0 ? mean(abs) : null
    const rmsErr =
      n > 0 ? Math.sqrt(mean(signed.map((x) => x * x))) : null
    const priority =
      varianceSignedErr == null ? null : varianceSignedErr * compoundWeight
    bins.push({
      index: i,
      tStartSec: i * pieceW,
      tEndSec: Math.min(T, (i + 1) * pieceW),
      n,
      maeHp,
      meanSignedErr,
      varianceSignedErr,
      rmsErr,
      compoundWeight,
      priority,
    })
  }

  const optimizeOrder = bins
    .filter(
      (b): b is SqrtBin & { varianceSignedErr: number; priority: number } =>
        b.varianceSignedErr != null && b.priority != null,
    )
    .sort((a, b) => b.priority - a.priority)
    .map((b) => ({
      index: b.index,
      tStartSec: b.tStartSec,
      tEndSec: b.tEndSec,
      varianceSignedErr: b.varianceSignedErr,
      priority: b.priority,
      reason:
        b.index === 0
          ? 'early slice — high compounding (error feeds later seconds)'
          : b.index === binCount - 1
            ? 'late slice — finishing / lethal window'
            : 'mid trade',
    }))

  return {
    schema: 'pro-grid-sqrt-bin-v1',
    diagnosticOnly: true,
    doNotFitOnThisSample: true,
    durationSec: T,
    pieceWidthSec: pieceW,
    binCount,
    minSamples,
    bins,
    optimizeOrder,
    antiOverfit: {
      rule: 'Rank investigation only. Never minimize these variances as a loss on the same fight.',
      confirmBeforeActing:
        'Same phase (early/mid/late by bin index fraction) must rank top-2 on ≥2 independent checks before changing engine math.',
    },
  }
}

/** Map bin index → coarse phase label shared across different T. */
export function binPhase(binIndex: number, binCount: number): 'early' | 'mid' | 'late' {
  if (binCount <= 1) return 'early'
  const frac = binIndex / (binCount - 1)
  if (frac <= 1 / 3) return 'early'
  if (frac <= 2 / 3) return 'mid'
  return 'late'
}

export type Phase = 'early' | 'mid' | 'late'

export type CheckSqrtSummary = {
  check: number
  segment: string
  matchup: string
  topPhase: Phase | null
  topBinIndex: number | null
  topPriority: number | null
  /** Phases in this check's top-2 optimizeOrder (trades are mixed). */
  top2Phases?: Phase[]
}

export type DualTrackConsensus = {
  phaseCounts: Record<Phase, number>
  /** Unique #1 leader if ≥2 votes and no tie — kept for CLI glance. */
  actionablePhase: Phase | null
  /**
   * Phases that appear in ≥2 checks' top-2. Both early+late can be active
   * (real trades are not pure one phase). Investigate each track separately;
   * do not collapse into one coefficient.
   */
  activeTracks: Phase[]
  trackSupport: Record<Phase, number>
  note: string
}

/**
 * Consensus across checks.
 * - `actionablePhase`: unique #1 (≥2 votes, no tie)
 * - `activeTracks`: every phase that lands in ≥2 checks' top-2
 *   (dual-track OK — trades are mixed early+late)
 */
export function consensusPhases(summaries: CheckSqrtSummary[]): DualTrackConsensus {
  const phaseCounts: Record<Phase, number> = { early: 0, mid: 0, late: 0 }
  const trackSupport: Record<Phase, number> = { early: 0, mid: 0, late: 0 }

  for (const s of summaries) {
    if (s.topPhase) phaseCounts[s.topPhase]++
    const top2 = s.top2Phases?.length
      ? s.top2Phases
      : s.topPhase
        ? [s.topPhase]
        : []
    const seen = new Set<Phase>()
    for (const p of top2) {
      if (seen.has(p)) continue
      seen.add(p)
      trackSupport[p]++
    }
  }

  const ranked = (Object.entries(phaseCounts) as Array<[Phase, number]>).sort(
    (a, b) => b[1] - a[1],
  )
  const [best, n] = ranked[0]!
  const second = ranked[1]?.[1] ?? 0
  const actionablePhase = n >= 2 && n > second ? best : null

  const activeTracks = (Object.entries(trackSupport) as Array<[Phase, number]>)
    .filter(([, c]) => c >= 2)
    .sort((a, b) => b[1] - a[1])
    .map(([p]) => p)

  let note: string
  if (activeTracks.length === 0) {
    note =
      `No active tracks (need a phase in ≥2 checks' top-2). ` +
      `Counts#1: early=${phaseCounts.early} mid=${phaseCounts.mid} late=${phaseCounts.late}. ` +
      `Do not change engine math yet.`
  } else if (activeTracks.length === 1) {
    note =
      `Active track: ${activeTracks[0]} (top-2 support). ` +
      `Investigate that error class; holdout before claiming a fix. ` +
      `Glance leader #1=${actionablePhase ?? 'none'}.`
  } else {
    note =
      `Dual tracks active: ${activeTracks.join(' + ')}. ` +
      `Trades are mixed — investigate each track separately; ` +
      `do not fit one coefficient to both. Holdout before claiming a fix.`
  }

  return { phaseCounts, actionablePhase, activeTracks, trackSupport, note }
}
