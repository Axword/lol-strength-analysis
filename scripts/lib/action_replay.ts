/**
 * Action-replay matching (GOAL-action-replay-95.md).
 *
 * Truth vs model action inventories, bipartite greedy-by-time matching,
 * and the actionCoverage (F1) score. Research instrumentation only —
 * "95% confidence" here means actionCoverage >= 0.95 (matched-action F1),
 * NEVER a calibrated win probability / odds.
 */

export type ActionKind = 'skill' | 'aa' | 'item' | 'summoner' | 'damage'
export type ActorClass = 'killer' | 'ally'

export type ActionRecord = {
  tSec: number
  actorClass: ActorClass
  kind: ActionKind
  /** 1-4 for Q/W/E/R; omit or 0 when slot is unknown */
  skillSlot?: number
  /** Disclosed share applied (ally pulse share, etc.) — audit only, not matched on */
  shareHint?: number
  /**
   * PE-proven UnitApplyDamage source netId when emit provides it (R39/R41/R45).
   * Never invent; omit/null when emit lacks a proven sourceNetId.
   */
  sourceNetId?: number | null
  /**
   * PE-proven damage amount when emit provides it (R39/R41/R45).
   * Never invent; omit/null when emit lacks amount.
   */
  amount?: number | null
}

export type ActionMatch = {
  truthIdx: number
  modelIdx: number
  dtSec: number
}

export type ActionCoverageResult = {
  truthCount: number
  modelCount: number
  matchedCount: number
  precision: number
  recall: number
  actionCoverage: number
  matches: ActionMatch[]
  unmatchedTruth: number[]
  unmatchedModel: number[]
}

function slotCompatible(a: ActionRecord, b: ActionRecord): boolean {
  if (a.kind !== 'skill') return true
  const as = a.skillSlot ?? 0
  const bs = b.skillSlot ?? 0
  if (as === 0 || bs === 0) return true // both/either slot-unknown
  return as === bs
}

/**
 * Bipartite greedy-by-time matcher.
 * A truth action T matches model action M iff: same actorClass, same kind,
 * same skillSlot (or either unknown) when kind==='skill', |dt| <= tau,
 * and neither has been claimed yet. Greedy = process candidate pairs sorted
 * by |dt| ascending so the closest-in-time pairs win first (stable, no
 * flood credit for a cluster of finish AAs against one truth AA).
 */
export function matchActions(
  truth: ActionRecord[],
  model: ActionRecord[],
  tauSec = 0.25,
): ActionCoverageResult {
  type Candidate = { ti: number; mi: number; dt: number }
  const candidates: Candidate[] = []
  for (let ti = 0; ti < truth.length; ti++) {
    const t = truth[ti]!
    for (let mi = 0; mi < model.length; mi++) {
      const m = model[mi]!
      if (t.actorClass !== m.actorClass) continue
      if (t.kind !== m.kind) continue
      if (!slotCompatible(t, m)) continue
      const dt = Math.abs(t.tSec - m.tSec)
      if (dt > tauSec + 1e-9) continue
      candidates.push({ ti, mi, dt })
    }
  }
  candidates.sort((a, b) => a.dt - b.dt)

  const truthClaimed = new Array(truth.length).fill(false)
  const modelClaimed = new Array(model.length).fill(false)
  const matches: ActionMatch[] = []
  for (const c of candidates) {
    if (truthClaimed[c.ti] || modelClaimed[c.mi]) continue
    truthClaimed[c.ti] = true
    modelClaimed[c.mi] = true
    matches.push({ truthIdx: c.ti, modelIdx: c.mi, dtSec: c.dt })
  }
  matches.sort((a, b) => a.truthIdx - b.truthIdx)

  const matchedCount = matches.length
  const truthCount = truth.length
  const modelCount = model.length
  const precision = matchedCount / Math.max(1, modelCount)
  const recall = matchedCount / Math.max(1, truthCount)
  const actionCoverage =
    (2 * precision * recall) / Math.max(1e-9, precision + recall)

  const unmatchedTruth: number[] = []
  for (let i = 0; i < truth.length; i++) if (!truthClaimed[i]) unmatchedTruth.push(i)
  const unmatchedModel: number[] = []
  for (let i = 0; i < model.length; i++) if (!modelClaimed[i]) unmatchedModel.push(i)

  return {
    truthCount,
    modelCount,
    matchedCount,
    precision,
    recall,
    actionCoverage,
    matches,
    unmatchedTruth,
    unmatchedModel,
  }
}

export type ActionReplayAudit = {
  schema: 'pro-grid-action-replay-audit-v1'
  series: string
  gameIndex: number
  check: number
  segment: string
  matchup: string
  tau: number
  truthActions: ActionRecord[]
  modelActions: ActionRecord[]
  coverage: ActionCoverageResult
  byKind: Record<
    string,
    { truthCount: number; modelCount: number; matchedCount: number; actionCoverage: number }
  >
  disclosures: string[]
}

/** Per-kind coverage breakdown for the audit JSON (skill vs aa vs item vs summoner). */
export function breakdownByKind(
  truth: ActionRecord[],
  model: ActionRecord[],
  coverage: ActionCoverageResult,
): ActionReplayAudit['byKind'] {
  const kinds = new Set<ActionKind>([
    ...truth.map((t) => t.kind),
    ...model.map((m) => m.kind),
  ])
  const matchedTruthIdx = new Set(coverage.matches.map((m) => m.truthIdx))
  const out: ActionReplayAudit['byKind'] = {}
  for (const kind of kinds) {
    const truthN = truth.filter((t) => t.kind === kind).length
    const modelN = model.filter((m) => m.kind === kind).length
    const matchedN = coverage.matches.filter(
      (m) => truth[m.truthIdx]?.kind === kind,
    ).length
    const precision = matchedN / Math.max(1, modelN)
    const recall = matchedN / Math.max(1, truthN)
    const f1 = (2 * precision * recall) / Math.max(1e-9, precision + recall)
    out[kind] = {
      truthCount: truthN,
      modelCount: modelN,
      matchedCount: matchedN,
      actionCoverage: f1,
    }
  }
  void matchedTruthIdx
  return out
}
