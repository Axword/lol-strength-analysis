import type {
  MatchupInput,
  MatchupResult,
  SideResult,
  StrengthBand,
} from './types'

declare const __BUILD_REVISION__: string | null
declare const __BUILD_TRACKED_DIRTY__: boolean | null

export const ANALYSIS_RECORD_SCHEMA =
  'lol-strength-analysis/analysis-record@1' as const

interface EvidenceBandCell {
  blueHpPct: number
  redHpPct: number
  winner: 'blue' | 'red' | 'draw'
  blueScore?: number
}

interface EvidenceStrengthBand {
  hitAll: EvidenceBandCell
  expected: EvidenceBandCell
  missShots: EvidenceBandCell
}

export interface AnalysisRecord {
  schema: typeof ANALYSIS_RECORD_SCHEMA
  recordId: string
  contentFingerprint: {
    algorithm: 'fnv1a-64'
    value: string
  }
  createdAt: string
  producer: {
    app: 'lol-strength-analysis'
    sourceRevision: string | null
    trackedSourceDirty: boolean | null
  }
  context: {
    label: string | null
  }
  usePolicy: {
    audience: 'bookmaker_internal_research'
    outputKind: 'heuristic_model_edge'
    calibrated: false
    marketPriceEligible: false
    status: 'research_only'
    limitations: string[]
  }
  input: MatchupInput
  output: {
    winner: MatchupResult['winner']
    modelEdge: {
      blueScore: number
      redScore: number
      scale: '0_to_1'
    }
    blue: SideResult
    red: SideResult
    modelTrust: MatchupResult['modelTrust']
    notes: string[]
    xhMode: MatchupResult['xhMode']
    strengthBand?: EvidenceStrengthBand
    xhDodgeBand: MatchupResult['xhDodgeBand']
    xhPacketPolicy: MatchupResult['xhPacketPolicy']
    tradeHpWinner: MatchupResult['tradeHpWinner']
    assumptions: MatchupResult['assumptions']
    timing: MatchupResult['timing']
  }
}

export interface CreateAnalysisRecordOptions {
  matchup: MatchupInput
  result: MatchupResult
  contextLabel?: string | null
  createdAt?: string
  sourceRevision?: string | null
  trackedSourceDirty?: boolean | null
}

function finiteScore(value: number | undefined, fallback: number): number {
  if (value == null || !Number.isFinite(value)) return fallback
  return Math.max(0, Math.min(1, value))
}

function evidenceBandCell(cell: StrengthBand['expected']): EvidenceBandCell {
  const { pBlue, ...rest } = cell
  return {
    ...rest,
    ...(pBlue == null ? {} : { blueScore: finiteScore(pBlue, 0.5) }),
  }
}

function evidenceStrengthBand(
  band: StrengthBand | undefined,
): EvidenceStrengthBand | undefined {
  if (!band) return undefined
  return {
    hitAll: evidenceBandCell(band.hitAll),
    expected: evidenceBandCell(band.expected),
    missShots: evidenceBandCell(band.missShots),
  }
}

function runtimeBuildRevision(): string | null {
  return typeof __BUILD_REVISION__ === 'string' ? __BUILD_REVISION__ : null
}

function runtimeTrackedSourceDirty(): boolean | null {
  return typeof __BUILD_TRACKED_DIRTY__ === 'boolean'
    ? __BUILD_TRACKED_DIRTY__
    : null
}

function canonicalize(value: unknown): unknown {
  if (value == null || typeof value === 'string' || typeof value === 'boolean') {
    return value
  }
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) {
      throw new Error('Analysis records cannot contain non-finite numbers.')
    }
    return value
  }
  if (Array.isArray(value)) return value.map(canonicalize)
  if (typeof value === 'object') {
    const source = value as Record<string, unknown>
    const ordered: Record<string, unknown> = {}
    for (const key of Object.keys(source).sort()) {
      if (source[key] !== undefined) ordered[key] = canonicalize(source[key])
    }
    return ordered
  }
  throw new Error(`Analysis records cannot contain ${typeof value} values.`)
}

export function canonicalAnalysisJson(value: unknown): string {
  return JSON.stringify(canonicalize(value))
}

function fnv1a64(value: string): string {
  let hash = 0xcbf29ce484222325n
  const prime = 0x100000001b3n
  const mask = 0xffffffffffffffffn
  for (const byte of new TextEncoder().encode(value)) {
    hash ^= BigInt(byte)
    hash = (hash * prime) & mask
  }
  return hash.toString(16).padStart(16, '0')
}

export function createAnalysisRecord({
  matchup,
  result,
  contextLabel = null,
  createdAt = new Date().toISOString(),
  sourceRevision = runtimeBuildRevision(),
  trackedSourceDirty = runtimeTrackedSourceDirty(),
}: CreateAnalysisRecordOptions): AnalysisRecord {
  const parsedCreatedAt = new Date(createdAt)
  if (!Number.isFinite(parsedCreatedAt.getTime())) {
    throw new Error('createdAt must be a valid ISO-8601 timestamp.')
  }

  const blueScore = finiteScore(result.pBlue, 0.5)
  const redScore = finiteScore(result.pRed, 1 - blueScore)
  const recordContent = {
    schema: ANALYSIS_RECORD_SCHEMA,
    producer: {
      app: 'lol-strength-analysis' as const,
      sourceRevision,
      trackedSourceDirty,
    },
    context: {
      label: contextLabel?.trim() || null,
    },
    usePolicy: {
      audience: 'bookmaker_internal_research' as const,
      outputKind: 'heuristic_model_edge' as const,
      calibrated: false as const,
      marketPriceEligible: false as const,
      status: 'research_only' as const,
      limitations: [
        'Model edge is a heuristic ranking score, not a calibrated win probability.',
        'This record is not eligible to generate or publish a market price.',
        'Research agreement metrics are validation evidence, not price confidence.',
        'The content fingerprint is for record correlation, not authorization or tamper proofing.',
      ],
    },
    input: matchup,
    output: {
      winner: result.winner,
      modelEdge: {
        blueScore,
        redScore,
        scale: '0_to_1' as const,
      },
      blue: result.blue,
      red: result.red,
      modelTrust: result.modelTrust,
      notes: result.notes,
      xhMode: result.xhMode,
      strengthBand: evidenceStrengthBand(result.strengthBand),
      xhDodgeBand: result.xhDodgeBand,
      xhPacketPolicy: result.xhPacketPolicy,
      tradeHpWinner: result.tradeHpWinner,
      assumptions: result.assumptions,
      timing: result.timing,
    },
  }
  const fingerprint = fnv1a64(canonicalAnalysisJson(recordContent))

  return canonicalize({
    ...recordContent,
    recordId: `analysis-${fingerprint}`,
    contentFingerprint: {
      algorithm: 'fnv1a-64' as const,
      value: fingerprint,
    },
    createdAt: parsedCreatedAt.toISOString(),
  }) as AnalysisRecord
}

export function analysisRecordFilename(record: AnalysisRecord): string {
  const context = record.context.label
    ?.toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 48)
  const date = record.createdAt.slice(0, 10)
  return [
    'lol-analysis',
    context || 'manual',
    date,
    record.contentFingerprint.value.slice(0, 8),
  ].join('-') + '.json'
}
