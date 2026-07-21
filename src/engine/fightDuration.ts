import type { AbilitySlot, CombatStats, TradeMode } from './types'

/** Typical window lengths (seconds). JSONL fightDuration spans ~3–40s. */
export const FIGHT_DURATION_SEC: Record<TradeMode, number> = {
  short: 3.5,
  allin: 8,
  extended: 16,
}

export function fightDurationSec(mode: TradeMode): number {
  return FIGHT_DURATION_SEC[mode]
}

/**
 * Auto count from live attack speed × window, floored by champion trade priors.
 */
export function autosForDuration(
  mode: TradeMode,
  attackSpeed: number,
  champBaseAutos: number,
): number {
  const dur = fightDurationSec(mode)
  const fromAs = Math.floor(Math.max(0.4, attackSpeed) * dur * 0.92)
  if (mode === 'short') return Math.max(champBaseAutos, Math.min(fromAs, champBaseAutos + 1))
  if (mode === 'allin') return Math.max(champBaseAutos, fromAs)
  return Math.max(champBaseAutos + 2, fromAs)
}

/** How many times a basic ability lands in the window (ult stays ≤1). */
export function abilityCastsInFight(
  mode: TradeMode,
  slot: AbilitySlot,
  abilityHaste: number,
): number {
  if (slot === 'AA') return 1
  if (slot === 'R') return mode === 'short' ? 0 : 1

  const baseCd = slot === 'Q' ? 6.5 : slot === 'W' ? 10 : 8.5
  const cd = (baseCd * 100) / (100 + Math.max(0, abilityHaste))
  const dur = fightDurationSec(mode)

  if (mode === 'short') return 1
  if (mode === 'allin') {
    return Math.max(1, Math.min(2, 1 + Math.floor(Math.max(0, dur - 3.5) / cd)))
  }
  // extended — up to ~3–4 basic casts
  return Math.max(1, Math.min(4, Math.round(dur / cd)))
}

/**
 * In-fight sustain restored over the window.
 * - Omnivamp on damage this side dealt (all types, simplified).
 * - Residual combat HP regen ≈ 30% of listed regen (full regen is mostly OOC).
 */
export function sustainHeal(
  damageDealt: number,
  stats: CombatStats,
  durationSec: number,
): number {
  const vamp = Math.max(0, stats.omnivamp) * damageDealt
  const regen = Math.max(0, stats.hpRegen) * durationSec * 0.3
  return vamp + regen
}

export function pickTradeModeForGameTime(gameTimeSec: number): TradeMode {
  if (gameTimeSec >= 15 * 60) return 'extended'
  if (gameTimeSec >= 8 * 60) return 'allin'
  return 'short'
}
