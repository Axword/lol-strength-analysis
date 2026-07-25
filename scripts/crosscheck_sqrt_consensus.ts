/**
 * Build anti-overfit consensus from existing crosscheck model JSON files.
 *
 *   npx --yes tsx scripts/crosscheck_sqrt_consensus.ts \
 *     --glob 'docs/canvases/_data/crosscheck-0*-model.json'
 *
 * Does NOT change engine math. Only ranks which trade phase (early/mid/late)
 * shows high √T-bin variance across checks. Act only if ≥2 checks agree.
 */
import { readFileSync, writeFileSync, mkdirSync, readdirSync } from 'node:fs'
import { dirname, resolve, join } from 'node:path'
import {
  binPhase,
  consensusPhases,
  type CheckSqrtSummary,
  type Phase,
} from './lib/crosscheck_sqrt_bins'

function argValue(flag: string, fallback = ''): string {
  const i = process.argv.indexOf(flag)
  return i >= 0 && process.argv[i + 1] ? process.argv[i + 1]! : fallback
}

type ModelFile = {
  checkIndex: number
  segment: string
  matchup: string
  sqrtBins?: {
    binCount: number
    optimizeOrder: Array<{
      index: number
      varianceSignedErr: number
      priority: number
    }>
  }
  focus?: { phase: Phase | null }
}

function listModelFiles(dir: string, segmentFilter: string | null): string[] {
  return readdirSync(dir)
    .filter((name) => /^crosscheck-\d+.*-model\.json$/.test(name) || /^crosscheck-\d+-model\.json$/.test(name))
    .filter((name) => {
      if (segmentFilter === 'full') return /crosscheck-\d+-model\.json$/.test(name) && !name.includes('burst')
      if (segmentFilter === 'burst') return name.includes('burst')
      return true
    })
    .map((name) => join(dir, name))
    .sort()
}

function defaultOut(segmentFilter: string | null): string {
  if (segmentFilter === 'full') return 'docs/canvases/_data/crosscheck-sqrt-consensus-full.json'
  if (segmentFilter === 'burst') return 'docs/canvases/_data/crosscheck-sqrt-consensus-burst.json'
  return 'docs/canvases/_data/crosscheck-sqrt-consensus.json'
}

function main() {
  const dir = resolve(argValue('--dir', 'docs/canvases/_data'))
  const segmentFilter = argValue('--segment', '') || null
  const outPath = resolve(argValue('--out', defaultOut(segmentFilter)))

  const paths = listModelFiles(dir, segmentFilter)
  const summaries: CheckSqrtSummary[] = []
  const perFile: Array<Record<string, unknown>> = []

  for (const p of paths) {
    const m = JSON.parse(readFileSync(p, 'utf8')) as ModelFile
    if (!m.sqrtBins?.optimizeOrder?.length) {
      perFile.push({ file: p, skipped: 'missing sqrtBins — re-run crosscheck:kill' })
      continue
    }
    const top = m.sqrtBins.optimizeOrder[0]!
    const phase =
      m.focus?.phase ?? binPhase(top.index, m.sqrtBins.binCount)
    const top2Phases = [
      ...new Set(
        m.sqrtBins.optimizeOrder.slice(0, 2).map((b) => binPhase(b.index, m.sqrtBins!.binCount)),
      ),
    ] as Phase[]
    const row: CheckSqrtSummary = {
      check: m.checkIndex,
      segment: m.segment,
      matchup: m.matchup,
      topPhase: phase,
      topBinIndex: top.index,
      topPriority: top.priority,
      top2Phases,
    }
    summaries.push(row)
    perFile.push({
      file: p,
      ...row,
      topVariance: top.varianceSignedErr,
    })
  }

  const consensus = consensusPhases(summaries)
  const tracks = consensus.activeTracks
  const report = {
    schema: 'pro-grid-sqrt-consensus-v2',
    diagnosticOnly: true,
    doNotFitOnThisSample: true,
    generatedFrom: paths,
    perFile,
    consensus,
    nextAction:
      tracks.length === 0
        ? 'No engine change. Collect more checks or inspect per-file bins manually.'
        : tracks.length === 1
          ? `Investigate ${tracks[0]}-trade error class without fitting to one kill. Holdout after any change.`
          : `Dual tracks: ${tracks.join(' + ')}. Work each track separately (opener vs finish). Never one coefficient for both. Holdout after any change.`,
  }

  mkdirSync(dirname(outPath), { recursive: true })
  writeFileSync(outPath, JSON.stringify(report, null, 2) + '\n', 'utf8')
  console.log(
    JSON.stringify(
      {
        ok: true,
        out: outPath,
        activeTracks: consensus.activeTracks,
        trackSupport: consensus.trackSupport,
        actionablePhase: consensus.actionablePhase,
        note: consensus.note,
        nextAction: report.nextAction,
      },
      null,
      2,
    ),
  )
}

main()
