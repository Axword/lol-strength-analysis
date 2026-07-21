import type { AbilitySlot, TradeMode } from './types'

/**
 * Which casts a fighter can realistically get off given current HP%.
 * Low-HP champions do not get a full rotation (e.g. 10% Lee vs full HP assassin).
 */
export function abilityBudget(
  hpPct: number,
  mode: TradeMode,
  hasUltRank: boolean,
): { allowed: Set<AbilitySlot>; omitted: AbilitySlot[]; note: string | null } {
  const allShort: AbilitySlot[] = ['Q', 'W', 'E', 'AA']
  const allAllin: AbilitySlot[] = ['Q', 'W', 'E', 'R', 'AA']
  const full = mode === 'short' ? allShort : allAllin

  if (hpPct <= 0) {
    return {
      allowed: new Set(),
      omitted: full,
      note: 'Dead — excluded from combat.',
    }
  }

  const wantsUlt = mode !== 'short'

  if (hpPct >= 0.65) {
    const allowed = new Set(full)
    if (wantsUlt && !hasUltRank) allowed.delete('R')
    return { allowed, omitted: [], note: null }
  }

  if (hpPct >= 0.4) {
    // Can trade but not fully commit
    const allowed = new Set<AbilitySlot>(['Q', 'E', 'AA'])
    if (wantsUlt && hasUltRank && hpPct >= 0.5) allowed.add('R')
    if (hpPct >= 0.5) allowed.add('W')
    const omitted = full.filter((s) => !allowed.has(s))
    return {
      allowed,
      omitted,
      note: `HP ${Math.round(hpPct * 100)}% — shortened rotation (no full combo).`,
    }
  }

  if (hpPct >= 0.15) {
    const allowed = new Set<AbilitySlot>(['Q', 'AA'])
    if (wantsUlt && hasUltRank) {
      allowed.add('R')
    } else {
      allowed.add('E')
    }
    const omitted = full.filter((s) => !allowed.has(s))
    return {
      allowed,
      omitted,
      note: `HP ${Math.round(hpPct * 100)}% — critical; only gapclose + one follow-up.`,
    }
  }

  // < 15% — one action
  const allowed = new Set<AbilitySlot>(['Q'])
  const omitted = full.filter((s) => !allowed.has(s))
  return {
    allowed,
    omitted,
    note: `HP ${Math.round(hpPct * 100)}% — last-hit window only (single ability).`,
  }
}

export function autosForBudget(hpPct: number, mode: TradeMode, baseAutos: number): number {
  if (hpPct <= 0) return 0
  if (hpPct >= 0.65) return baseAutos
  if (hpPct >= 0.4) return Math.max(1, Math.floor(baseAutos * 0.66))
  if (hpPct >= 0.15) return 1
  return mode === 'short' ? 0 : 1
}
