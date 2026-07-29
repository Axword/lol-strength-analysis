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

/** Resolve fight window: explicit theorycraft override or trade-mode preset. */
export function resolveFightDuration(input: {
  mode: TradeMode
  durationSec?: number
}): number {
  if (input.durationSec != null && Number.isFinite(input.durationSec)) {
    return Math.max(1, Math.min(40, input.durationSec))
  }
  return fightDurationSec(input.mode)
}

/**
 * Auto count from live attack speed × window, floored by champion trade priors.
 */
export function autosForDuration(
  mode: TradeMode,
  attackSpeed: number,
  champBaseAutos: number,
  opts?: { durationSec?: number; aaUptime?: number },
): number {
  const dur = opts?.durationSec ?? fightDurationSec(mode)
  const uptime = Math.max(0, Math.min(1, opts?.aaUptime ?? 1))
  const fromAs = Math.floor(Math.max(0.4, attackSpeed) * dur * 0.92 * uptime)
  if (mode === 'short' && opts?.durationSec == null) {
    return Math.max(champBaseAutos, Math.min(fromAs, champBaseAutos + 1))
  }
  if (mode === 'allin' && opts?.durationSec == null) {
    return Math.max(Math.round(champBaseAutos * uptime), fromAs)
  }
  // Extended or custom duration — trust AS × window × uptime
  const floor = Math.max(0, Math.round((champBaseAutos + (mode === 'extended' ? 2 : 0)) * uptime))
  return Math.max(floor, fromAs)
}

/** How many times a basic ability lands in the window (ult stays ≤1). */
export function abilityCastsInFight(
  mode: TradeMode,
  slot: AbilitySlot,
  abilityHaste: number,
  durationSec?: number,
  /** Ability base CD when known; falls back to slot priors. */
  baseCooldownSec?: number,
): number {
  if (slot === 'AA') return 1
  const dur = durationSec ?? fightDurationSec(mode)
  if (slot === 'R') return dur < 4 ? 0 : 1

  const baseCd =
    baseCooldownSec != null && baseCooldownSec > 0
      ? baseCooldownSec
      : slot === 'Q'
        ? 6.5
        : slot === 'W'
          ? 10
          : 8.5
  const cd = (baseCd * 100) / (100 + Math.max(0, abilityHaste))

  if (durationSec == null) {
    if (mode === 'short') return 1
    if (mode === 'allin') {
      return Math.max(1, Math.min(2, 1 + Math.floor(Math.max(0, dur - 3.5) / cd)))
    }
    return Math.max(1, Math.min(4, Math.ceil(dur / cd)))
  }

  // Custom duration — cast at t=0 then every CD (ceil window / CD, capped).
  // Short-CD gapcloses (e.g. Yasuo E ~0.5s) need headroom above the old ×8 cap.
  if (dur < 2.5) return 1
  const cap = baseCd <= 1.5 ? 16 : 8
  return Math.max(1, Math.min(cap, Math.ceil(dur / cd)))
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
