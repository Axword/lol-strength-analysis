import {
  analysisRecordFilename,
  canonicalAnalysisJson,
  createAnalysisRecord,
} from '../analysisRecord'
import { emptyMatchup, simulateMatchup } from '../combat'

let passed = 0

function assert(condition: unknown, name: string): asserts condition {
  if (!condition) throw new Error(`FAIL ${name}`)
  passed += 1
}

const matchup = emptyMatchup('Gragas', 'Darius')
const result = simulateMatchup(matchup)
const fixed = {
  matchup,
  result,
  contextLabel: 'BR1 123456 · 18:42 · river fight',
  createdAt: '2026-07-29T12:00:00.000Z',
  sourceRevision: '0123456789abcdef',
  trackedSourceDirty: false,
} as const

const first = createAnalysisRecord(fixed)
const second = createAnalysisRecord(fixed)

assert(
  first.schema === 'lol-strength-analysis/analysis-record@1',
  'schema is explicit',
)
assert(
  first.usePolicy.audience === 'bookmaker_internal_research',
  'buyer policy is explicit',
)
assert(first.usePolicy.calibrated === false, 'calibration is false')
assert(
  first.usePolicy.marketPriceEligible === false,
  'market price use is blocked',
)
assert(
  first.producer.sourceRevision === fixed.sourceRevision,
  'source revision is included',
)
assert(
  first.contentFingerprint.value === second.contentFingerprint.value,
  'same analysis has stable fingerprint',
)
assert(first.recordId === second.recordId, 'same analysis has stable record id')
assert(
  first.output.modelEdge.blueScore === result.pBlue,
  'blue model score is preserved',
)
assert(
  first.output.modelEdge.redScore === result.pRed,
  'red model score is preserved',
)
assert(
  !canonicalAnalysisJson(first.output).includes('"pBlue"'),
  'probability-shaped score key is absent from evidence output',
)
assert(
  analysisRecordFilename(first) ===
    'lol-analysis-br1-123456-18-42-river-fight-2026-07-29-' +
      `${first.contentFingerprint.value.slice(0, 8)}.json`,
  'filename is stable and safe',
)

const changedMatchup = {
  ...matchup,
  durationSec: 9,
}
const changed = createAnalysisRecord({
  ...fixed,
  matchup: changedMatchup,
  result: simulateMatchup(changedMatchup),
})
assert(
  changed.contentFingerprint.value !== first.contentFingerprint.value,
  'changed analysis changes fingerprint',
)

console.log(`analysis record: ${passed} checks passed`)
