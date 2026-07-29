/**
 * Bounded deterministic cast/attack rotation planner.
 *
 * Best-found under fixed beam/expansion limits — not globally optimal,
 * not calibrated. No randomness, wall-clock, localeCompare, or
 * iteration-order dependence: candidates are sorted by stable id
 * (code-point) before search.
 *
 * Attack-reset empowered autos (e.g. Darius W):
 * - May start after cast/global lock + own cooldown even when ordinary AA
 *   is not ready (they do not wait on aaReady).
 * - After the empowered attack, the next ordinary AA is ready only after a
 *   full attack interval from that W start (not merely castLock).
 * - Effective-reset utilization (ordinary AA consumed since last reset)
 *   is a deterministic secondary objective after total expected damage so
 *   equal-damage plans prefer AA → W reset over W-first.
 *
 * Front-loading: primary rank uses score + frontLoaded/duration so early
 * casts outrank equal-total AA-padding that parks abilities after a
 * first-lethal truncate (e.g. Meraki Yasuo E dumped at t>4s). Attack-reset
 * utilization remains the next tie-break so AA→W still beats W-first when
 * totals match.
 */

import type { AbilitySlot } from './types'

/** Locale-independent code-point order. */
function compareCodePoint(a: string, b: string): number {
  return a < b ? -1 : a > b ? 1 : 0
}

export interface RotationActionCandidate {
  /** Stable id used for code-point tie breaks (e.g. "AA", "W:Crippling Strike"). */
  id: string
  slot: AbilitySlot
  /** Numeric expected-damage score used by the bounded search. */
  expectedDamage: number
  /** Base cooldown seconds before haste (ignored for pure AA). */
  cooldownSec: number
  /** Action / cast lock after start before another action may begin. */
  castLockSec: number
  /** Delay from start to damage impact. */
  impactDelaySec: number
  /** Resets the auto-attack timer after this action starts. */
  attackReset: boolean
  /**
   * Empowered auto: damage packet already includes the AA portion;
   * must not emit a separate base-AD AA for the same hit.
   * With attackReset, does not wait on aaReady to start.
   */
  empoweredAuto: boolean
  /** Maximum casts of this candidate in the window. */
  maxCasts: number
}

export interface PlanRotationParams {
  candidates: RotationActionCandidate[]
  /** Seconds between ordinary auto-attack starts (1 / attackSpeed). */
  attackIntervalSec: number
  durationSec: number
  /** Max ordinary AA actions (empowered autos do not count against this). */
  aaCap: number
  /** Optional delay before the fighter may act (engage reaction, etc.). */
  startDelaySec?: number
  /**
   * Optional initial ordinary-AA ready time (defaults to startDelaySec).
   * Attack-reset empowered autos ignore this gate; ordinary AAs do not.
   */
  aaReadySec?: number
  abilityHaste: number
  /** Beam width (default 8). */
  beamWidth?: number
  /** Hard expansion cap (default 400). */
  maxExpansions?: number
}

export interface PlannedAction {
  id: string
  slot: AbilitySlot
  startSec: number
  impactSec: number
  castIndex: number
  attackReset: boolean
  empoweredAuto: boolean
}

export interface RotationPlan {
  actions: PlannedAction[]
  /** Sum of expectedDamage for the best-found plan. */
  score: number
  /**
   * Count of attack-resets that followed an ordinary AA since the prior
   * reset (effective-reset utilization secondary objective).
   */
  effectiveResets: number
  /** Always bounded_beam — never claim global optimality. */
  method: 'bounded_beam'
  expansions: number
}

const DEFAULT_BEAM = 8
const DEFAULT_MAX_EXPANSIONS = 400
const TIME_EPS = 1e-9

interface SearchState {
  busyUntil: number
  aaReady: number
  readyAt: number[]
  castsUsed: number[]
  aaUsed: number
  /** Ordinary AA landed since the last attack-reset (or fight start). */
  aaSinceReset: boolean
  effectiveResets: number
  /** Sum of (durationSec − resetStart) for effective resets — prefer earlier weaves. */
  resetEarliness: number
  /**
   * Σ expectedDamage × (durationSec − startSec). Prefer earlier damage among
   * equal-total plans so lethal truncates do not erase parked abilities.
   */
  frontLoaded: number
  actions: PlannedAction[]
  score: number
  fingerprint: string
}

function hasteCooldown(baseSec: number, abilityHaste: number): number {
  if (!(baseSec > 0)) return 0
  return (baseSec * 100) / (100 + Math.max(0, abilityHaste))
}

function stateFingerprint(actions: PlannedAction[]): string {
  if (!actions.length) return ''
  return actions
    .map(
      (a) =>
        `${a.id}@${a.startSec.toFixed(6)}>${a.impactSec.toFixed(6)}#${a.castIndex}`,
    )
    .join('|')
}

function scoreKey(score: number): number {
  // Order-independent compare so AA→W vs W→AA with the same action
  // damages still tie on primary score (float addition is not associative).
  return Math.round(score * 1e6) / 1e6
}

function compareStates(a: SearchState, b: SearchState, durationSec: number): number {
  // Primary: total expected damage + mean front-load (damage × remaining window / duration).
  // Early casts get ~+expectedDamage; end-of-window casts get ~0. Stops AA-padding
  // from parking abilities after a first-lethal truncate while keeping reset tie-breaks.
  const denom = Math.max(durationSec, TIME_EPS)
  const as = scoreKey(a.score + a.frontLoaded / denom)
  const bs = scoreKey(b.score + b.frontLoaded / denom)
  if (as !== bs) return bs - as
  if (a.effectiveResets !== b.effectiveResets) {
    return b.effectiveResets - a.effectiveResets
  }
  const ae = scoreKey(a.resetEarliness)
  const be = scoreKey(b.resetEarliness)
  if (ae !== be) return be - ae
  return compareCodePoint(a.fingerprint, b.fingerprint)
}

function cloneState(s: SearchState): SearchState {
  return {
    busyUntil: s.busyUntil,
    aaReady: s.aaReady,
    readyAt: s.readyAt.slice(),
    castsUsed: s.castsUsed.slice(),
    aaUsed: s.aaUsed,
    aaSinceReset: s.aaSinceReset,
    effectiveResets: s.effectiveResets,
    resetEarliness: s.resetEarliness,
    frontLoaded: s.frontLoaded,
    actions: s.actions.slice(),
    score: s.score,
    fingerprint: s.fingerprint,
  }
}

function isOrdinaryAa(cand: RotationActionCandidate): boolean {
  return cand.slot === 'AA' && !cand.empoweredAuto
}

/** Attack-reset empowered auto: starts without waiting on aaReady. */
function isAttackResetEmpowered(cand: RotationActionCandidate): boolean {
  return cand.empoweredAuto && cand.attackReset
}

/**
 * Pure deterministic bounded beam search over cast/attack sequences.
 * Returns the best-found plan under fixed limits (not globally optimal).
 *
 * Expands every feasible next action at its own earliest legal start (not only
 * the globally earliest). Choosing a later-ready cooldown recast is therefore
 * representable without an explicit no-op wait state (no infinite idling).
 */
export function planRotation(params: PlanRotationParams): RotationPlan {
  const durationSec = Math.max(0, params.durationSec)
  const startDelay = Math.max(0, params.startDelaySec ?? 0)
  const attackInterval = Math.max(0.05, params.attackIntervalSec)
  const aaCap = Math.max(0, Math.floor(params.aaCap))
  const beamWidth = Math.max(1, Math.floor(params.beamWidth ?? DEFAULT_BEAM))
  const maxExpansions = Math.max(
    1,
    Math.floor(params.maxExpansions ?? DEFAULT_MAX_EXPANSIONS),
  )
  const haste = Math.max(0, params.abilityHaste)
  const initialAaReady =
    params.aaReadySec != null && Number.isFinite(params.aaReadySec)
      ? Math.max(0, params.aaReadySec)
      : startDelay

  const sortedCandidates = params.candidates
    .map((c, originalIndex) => ({ c, originalIndex }))
    .sort((a, b) => {
      const byId = compareCodePoint(a.c.id, b.c.id)
      if (byId !== 0) return byId
      return a.originalIndex - b.originalIndex
    })
    .map((x) => x.c)

  const n = sortedCandidates.length
  const initial: SearchState = {
    busyUntil: startDelay,
    aaReady: initialAaReady,
    readyAt: sortedCandidates.map(() => startDelay),
    castsUsed: sortedCandidates.map(() => 0),
    aaUsed: 0,
    aaSinceReset: false,
    effectiveResets: 0,
    resetEarliness: 0,
    frontLoaded: 0,
    actions: [],
    score: 0,
    fingerprint: '',
  }

  let best = initial
  let beam: SearchState[] = [initial]
  let expansions = 0

  while (beam.length > 0 && expansions < maxExpansions) {
    const nextBeam: SearchState[] = []

    for (const state of beam) {
      type Option = {
        index: number
        startSec: number
        impactSec: number
        candidate: RotationActionCandidate
      }
      const options: Option[] = []

      for (let i = 0; i < n; i++) {
        const cand = sortedCandidates[i]!
        if (state.castsUsed[i]! >= cand.maxCasts) continue

        const ordinary = isOrdinaryAa(cand)
        if (ordinary && state.aaUsed >= aaCap) continue

        let startSec = Math.max(state.busyUntil, state.readyAt[i]!)
        // Ordinary AA (and non-reset empowered autos) wait on aaReady.
        // Attack-reset empowered autos do not — they may interrupt the timer.
        if (ordinary || (cand.empoweredAuto && !cand.attackReset)) {
          startSec = Math.max(startSec, state.aaReady)
        }

        const impactSec = startSec + Math.max(0, cand.impactDelaySec)
        if (impactSec > durationSec + TIME_EPS) continue
        if (startSec > durationSec + TIME_EPS) continue

        options.push({ index: i, startSec, impactSec, candidate: cand })
      }

      if (!options.length) continue

      // Expand all feasible starts (including later-ready cooldowns), not only
      // the globally earliest — otherwise filler can force out a waited recast.
      options.sort((a, b) => {
        if (Math.abs(a.startSec - b.startSec) > TIME_EPS) {
          return a.startSec - b.startSec
        }
        if (a.candidate.expectedDamage !== b.candidate.expectedDamage) {
          return b.candidate.expectedDamage - a.candidate.expectedDamage
        }
        return compareCodePoint(a.candidate.id, b.candidate.id)
      })

      for (const opt of options) {
        if (expansions >= maxExpansions) break
        expansions++

        const child = cloneState(state)
        const cand = opt.candidate
        const castIndex = child.castsUsed[opt.index]! + 1
        child.castsUsed[opt.index] = castIndex

        const ordinary = isOrdinaryAa(cand)
        if (ordinary) {
          child.aaUsed += 1
          child.aaSinceReset = true
        }

        if (isAttackResetEmpowered(cand) || (cand.attackReset && !ordinary)) {
          if (child.aaSinceReset) {
            child.effectiveResets += 1
            child.resetEarliness += Math.max(0, durationSec - opt.startSec)
          }
          child.aaSinceReset = false
        }

        const planned: PlannedAction = {
          id: cand.id,
          slot: cand.slot,
          startSec: opt.startSec,
          impactSec: opt.impactSec,
          castIndex,
          attackReset: cand.attackReset,
          empoweredAuto: cand.empoweredAuto,
        }
        child.actions = child.actions.concat(planned)
        child.score += cand.expectedDamage
        child.frontLoaded +=
          cand.expectedDamage * Math.max(0, durationSec - opt.startSec)
        child.fingerprint = stateFingerprint(child.actions)

        const lock = Math.max(0, cand.castLockSec)
        child.busyUntil = opt.startSec + lock

        if (!ordinary) {
          const cd = hasteCooldown(cand.cooldownSec, haste)
          child.readyAt[opt.index] = opt.startSec + cd
        }

        if (ordinary) {
          child.aaReady = opt.startSec + attackInterval
        } else if (isAttackResetEmpowered(cand) || cand.attackReset) {
          // Full attack interval from the reset attack — not castLock.
          // Prevents W-first from enabling an impossible AA 0.15s later.
          child.aaReady = opt.startSec + attackInterval
        }

        nextBeam.push(child)
        if (compareStates(child, best, durationSec) < 0) best = child
      }
    }

    if (!nextBeam.length) break
    nextBeam.sort((a, b) => compareStates(a, b, durationSec))
    beam = nextBeam.slice(0, beamWidth)
  }

  return {
    actions: best.actions,
    score: best.score,
    effectiveResets: best.effectiveResets,
    method: 'bounded_beam',
    expansions,
  }
}

/**
 * Truncate a plan to actions whose impact is within `durationSec`.
 * Used to assert shorter windows are time-prefixes of longer plans.
 */
export function truncatePlanByDuration(
  plan: RotationPlan,
  durationSec: number,
): PlannedAction[] {
  return plan.actions.filter((a) => a.impactSec <= durationSec + TIME_EPS)
}

/** Stable sort of planned actions by impact, then start, then id. */
export function sortPlannedActions(actions: PlannedAction[]): PlannedAction[] {
  return actions.slice().sort((a, b) => {
    if (a.impactSec !== b.impactSec) return a.impactSec - b.impactSec
    if (a.startSec !== b.startSec) return a.startSec - b.startSec
    const byId = compareCodePoint(a.id, b.id)
    if (byId !== 0) return byId
    return a.castIndex - b.castIndex
  })
}
