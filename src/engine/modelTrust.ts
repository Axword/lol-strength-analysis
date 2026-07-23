/**
 * Runtime matchup model-confidence classifier.
 *
 * Distinguishes hand-modeled CORE 1v1 attention from experimental cells
 * (generated kits and/or NvM). Never claims calibrated win probability,
 * and never implies full item/rune/passive validation.
 */
import { CHAMPIONS, isCoreChampion, resolveChampionId } from '../data/champions'
import { GAME_CHAMPIONS } from '../data/generatedGameChamps'
import type { FighterLoadout, MatchupInput } from './types'

export type MatchupModelClass = 'manual_kit_1v1' | 'experimental'

/** Per-champion modeling attention tier — not patch validation. */
export type ChampionModelingTier = 'core' | 'generated' | 'unresolved'

export type ModelTrustBadge =
  | 'Manual kits · uncalibrated'
  | 'Experimental · uncalibrated'

export interface ChampionModelTrustEntry {
  championId: string
  side: 'blue' | 'red'
  /** Index in the side's loadout array (input order). */
  index: number
  alive: boolean
  tier: ChampionModelingTier
}

/**
 * Serializable model-confidence contract attached to MatchupResult.
 * No wall-clock fields. `calibrated` is always false today.
 */
export interface MatchupModelTrust {
  calibrated: false
  class: MatchupModelClass
  badge: ModelTrustBadge
  /** Deterministic, sorted machine-readable reason codes. */
  reasons: string[]
  champions: ChampionModelTrustEntry[]
}

/** Matches combat.ts: alive===false, hpPct<=0, or liveStats.hp<=0 ⇒ dead. */
function isAlive(f: FighterLoadout): boolean {
  if (f.alive === false) return false
  if (f.hpPct != null && f.hpPct <= 0) return false
  if (f.liveStats?.hp != null && f.liveStats.hp <= 0) return false
  return true
}

/** Locale-independent code-point order for serializable arrays. */
function compareCodePoint(a: string, b: string): number {
  return a < b ? -1 : a > b ? 1 : 0
}

export function championModelingTier(championId: string): ChampionModelingTier {
  const resolved = resolveChampionId(championId)
  if (isCoreChampion(resolved) || isCoreChampion(championId)) return 'core'
  if (resolved in GAME_CHAMPIONS || championId in GAME_CHAMPIONS) return 'generated'
  // Meraki-generated kits (and any other CHAMPIONS entry) stay experimental.
  if (resolved in CHAMPIONS || championId in CHAMPIONS) return 'generated'
  return 'unresolved'
}

function livingLoadouts(
  side: 'blue' | 'red',
  fighters: FighterLoadout[],
): ChampionModelTrustEntry[] {
  return fighters.map((f, index) => ({
    championId: f.championId,
    side,
    index,
    alive: isAlive(f),
    tier: championModelingTier(f.championId),
  }))
}

/**
 * Pure classifier: living roster + CORE membership → model class.
 * Always returns calibrated: false.
 */
export function classifyMatchupModelTrust(
  input: MatchupInput,
): MatchupModelTrust {
  const champions = [
    ...livingLoadouts('blue', input.blue),
    ...livingLoadouts('red', input.red),
  ]
  const living = champions.filter((c) => c.alive)
  const blueLiving = living.filter((c) => c.side === 'blue')
  const redLiving = living.filter((c) => c.side === 'red')
  const is1v1 = blueLiving.length === 1 && redLiving.length === 1
  const bothCore =
    is1v1 &&
    blueLiving[0]!.tier === 'core' &&
    redLiving[0]!.tier === 'core'

  const modelClass: MatchupModelClass =
    bothCore ? 'manual_kit_1v1' : 'experimental'

  const reasons = new Set<string>()
  reasons.add('calibrated:false')
  reasons.add(`class:${modelClass}`)
  reasons.add(`living_roster:${blueLiving.length}v${redLiving.length}`)

  if (!is1v1) {
    reasons.add('reason:nvm')
  }
  for (const c of living) {
    reasons.add(`tier:${c.championId}=${c.tier}`)
    if (c.tier !== 'core') {
      reasons.add(
        c.tier === 'generated'
          ? 'reason:generated_fighter'
          : 'reason:unresolved_fighter',
      )
    }
  }
  if (is1v1 && bothCore) {
    reasons.add('reason:both_fighters_core')
  } else if (is1v1 && !bothCore) {
    reasons.add('reason:non_core_1v1')
  }

  // Items/runes/passives are never claimed validated.
  reasons.add('scope:kits_only_no_item_rune_passive_validation')

  const sortedReasons = [...reasons].sort(compareCodePoint)

  return {
    calibrated: false,
    class: modelClass,
    badge:
      modelClass === 'manual_kit_1v1'
        ? 'Manual kits · uncalibrated'
        : 'Experimental · uncalibrated',
    reasons: sortedReasons,
    champions,
  }
}
