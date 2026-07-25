import assert from 'node:assert/strict'
import {
  analyzeSqrtBins,
  binPhase,
  consensusPhases,
  sqrtPieceWidthSec,
  type ErrPoint,
} from '../lib/crosscheck_sqrt_bins.ts'

function pts(pairs: Array<[number, number]>): ErrPoint[] {
  return pairs.map(([tSec, signedErr]) => ({
    tSec,
    signedErr,
    absErr: Math.abs(signedErr),
  }))
}

{
  const w = sqrtPieceWidthSec(25)
  assert.equal(w, 5)
  const a = analyzeSqrtBins(
    pts([
      [0.5, 10],
      [1.5, 12],
      [5.5, 100],
      [6.5, -100],
      [20.5, 1],
      [21.5, 2],
    ]),
    25,
  )
  assert.equal(a.diagnosticOnly, true)
  assert.equal(a.doNotFitOnThisSample, true)
  assert.equal(a.pieceWidthSec, 5)
  assert.equal(a.binCount, 5)
  // Mid bin (5–10) has huge swing → highest variance
  const mid = a.bins[1]!
  assert.ok(mid.varianceSignedErr != null && mid.varianceSignedErr > 1000)
  assert.equal(a.optimizeOrder[0]!.index, 1)
  assert.equal(binPhase(0, 5), 'early')
  assert.equal(binPhase(2, 5), 'mid')
  assert.equal(binPhase(4, 5), 'late')
}

{
  // n=1 bin → variance null (anti-overfit / undefined)
  const a = analyzeSqrtBins(pts([[0.1, 50]]), 1, 2)
  assert.equal(a.bins[0]!.varianceSignedErr, null)
  assert.equal(a.optimizeOrder.length, 0)
}

{
  const c = consensusPhases([
    {
      check: 1,
      segment: 'full',
      matchup: 'A',
      topPhase: 'early',
      topBinIndex: 0,
      topPriority: 1,
      top2Phases: ['early', 'late'],
    },
    {
      check: 2,
      segment: 'full',
      matchup: 'B',
      topPhase: 'early',
      topBinIndex: 0,
      topPriority: 2,
      top2Phases: ['early', 'mid'],
    },
    {
      check: 3,
      segment: 'full',
      matchup: 'C',
      topPhase: 'late',
      topBinIndex: 4,
      topPriority: 3,
      top2Phases: ['late', 'early'],
    },
  ])
  assert.equal(c.actionablePhase, 'early')
  assert.equal(c.phaseCounts.early, 2)
  // Dual track: early+late both in ≥2 top-2s
  assert.deepEqual(c.activeTracks, ['early', 'late'])
}

{
  const c = consensusPhases([
    { check: 1, segment: 'full', matchup: 'A', topPhase: 'early', topBinIndex: 0, topPriority: 1 },
    { check: 2, segment: 'full', matchup: 'B', topPhase: 'mid', topBinIndex: 1, topPriority: 2 },
    { check: 3, segment: 'full', matchup: 'C', topPhase: 'late', topBinIndex: 2, topPriority: 3 },
  ])
  assert.equal(c.actionablePhase, null)
}

{
  // Tie for first → no action (anti-overfit)
  const c = consensusPhases([
    { check: 1, segment: 'full', matchup: 'A', topPhase: 'early', topBinIndex: 0, topPriority: 1 },
    { check: 2, segment: 'full', matchup: 'B', topPhase: 'early', topBinIndex: 0, topPriority: 2 },
    { check: 3, segment: 'full', matchup: 'C', topPhase: 'late', topBinIndex: 2, topPriority: 3 },
    { check: 4, segment: 'burst', matchup: 'D', topPhase: 'late', topBinIndex: 2, topPriority: 4 },
  ])
  assert.equal(c.phaseCounts.early, 2)
  assert.equal(c.phaseCounts.late, 2)
  assert.equal(c.actionablePhase, null)
}

console.log('crosscheck_sqrt_bins: ok')
