import type { AbilitySlot, CombatStats, TradeMode } from './types'

/**
 * Fight capability (v2) — replaces absolute HP% → allowed-slot / auto-count cliffs.
 *
 * What changed:
 * - Gone: bands at 65% / 40% / 15% that banned W/R/AA or forced autos to 1.
 * - Alive fighters may use every ranked ability that mode + CD allow.
 * - Autos come from AS × window × uptime; HP% alone never maps to {full, 66%, 1, 0}.
 * - Low HP shortens the *effective window* only when `surviveSec` is modeled
 *   (incoming pressure → time-to-death), not via static slot bans.
 *
 * Still approximate:
 * - Aggregate / NvM path uses a conservative DPS prior for surviveSec (not full kits).
 * - Timed 1v1 (CORE or Meraki) leaves surviveSec unset and stops at first lethal.
 * - No cast-animation desync / animation cancel fidelity.
 */

export type AbilityRanks = { Q: number; W: number; E: number; R: number }

export interface FightCapability {
  allowed: Set<AbilitySlot>
  omitted: AbilitySlot[]
  /** Short user-visible reasons (CD / rank / death / survival truncate). */
  omissionNotes: string[]
  note: string | null
  /** Window used for cast/auto counts (≤ requested duration). */
  effectiveSec: number
}

const ALL_SHORT: AbilitySlot[] = ['Q', 'W', 'E', 'AA']
const ALL_ALLIN: AbilitySlot[] = ['Q', 'W', 'E', 'R', 'AA']

/**
 * Which casts a living fighter can attempt in the fight window.
 * Dead → empty. Rank 0 / short-mode R → omitted with notes. HP% does not ban slots.
 */
export function abilityBudget(
  hpPct: number,
  mode: TradeMode,
  hasUltRank: boolean,
  opts?: {
    durationSec?: number
    /** Modeled death time; truncates effectiveSec when inside the window. */
    surviveSec?: number | null
    ranks?: AbilityRanks
  },
): FightCapability {
  const full = mode === 'short' ? ALL_SHORT : ALL_ALLIN
  const durationSec = Math.max(0, opts?.durationSec ?? (mode === 'short' ? 3.5 : mode === 'allin' ? 8 : 16))

  if (hpPct <= 0) {
    return {
      allowed: new Set(),
      omitted: full,
      omissionNotes: ['dead at start — excluded from combat'],
      note: 'Dead — excluded from combat.',
      effectiveSec: 0,
    }
  }

  const survive =
    opts?.surviveSec != null && Number.isFinite(opts.surviveSec)
      ? Math.max(0, opts.surviveSec)
      : durationSec
  const effectiveSec = Math.min(durationSec, survive)

  const ranks = opts?.ranks
  const allowed = new Set<AbilitySlot>()
  const omitted: AbilitySlot[] = []
  const omissionNotes: string[] = []

  const consider = (slot: AbilitySlot) => {
    if (slot === 'AA') {
      if (effectiveSec <= 0) {
        omitted.push('AA')
        omissionNotes.push('omitted AA: no surviving window')
        return
      }
      allowed.add('AA')
      return
    }
    if (slot === 'R' && mode === 'short') {
      omitted.push('R')
      omissionNotes.push('omitted R: short trade mode')
      return
    }
    const rank =
      ranks != null
        ? ranks[slot]
        : slot === 'R'
          ? hasUltRank
            ? 1
            : 0
          : 1
    // Rank 0: not allowed, but not listed in omittedSlots (never learned).
    if (rank <= 0) {
      omissionNotes.push(`omitted ${slot}: rank 0`)
      return
    }
    if (effectiveSec <= 0) {
      omitted.push(slot)
      omissionNotes.push(`omitted ${slot}: died before cast window`)
      return
    }
    allowed.add(slot)
  }

  for (const slot of full) consider(slot)

  let note: string | null = null
  if (effectiveSec + 1e-9 < durationSec) {
    note = `Effective window ${effectiveSec.toFixed(1)}s of ${durationSec.toFixed(1)}s (modeled survival; not HP-band slot bans).`
  }

  return { allowed, omitted, omissionNotes, note, effectiveSec }
}

/**
 * Autos from AS×window baseline. HP% never applies {1.0, 0.66, 1, 0} cliffs.
 * Scale only when effectiveSec < durationSec (modeled death / truncate).
 */
export function autosForBudget(
  hpPct: number,
  _mode: TradeMode,
  baseAutos: number,
  opts?: { effectiveSec?: number; durationSec?: number },
): number {
  if (hpPct <= 0) return 0
  const dur = opts?.durationSec
  const eff = opts?.effectiveSec
  if (
    dur != null &&
    dur > 0 &&
    eff != null &&
    Number.isFinite(eff) &&
    eff + 1e-9 < dur
  ) {
    return Math.max(0, Math.floor(baseAutos * (Math.max(0, eff) / dur)))
  }
  return Math.max(0, baseAutos)
}

/**
 * Conservative time-to-death from opposing stats (aggregate / NvM path only).
 * Underestimates burst so low-HP casters are not fake-capped to one AA.
 * Timed 1v1 must leave surviveSec unset and rely on chronological first-lethal.
 */
export function estimateSurviveSec(opts: {
  hp: number
  armor: number
  mr: number
  enemies: CombatStats[]
  durationSec: number
}): number {
  const { hp, durationSec } = opts
  if (hp <= 0) return 0
  if (durationSec <= 0) return 0
  if (!opts.enemies.length) return durationSec

  let dps = 0
  for (const e of opts.enemies) {
    const aa =
      Math.max(0, e.ad) * Math.max(0.4, e.attackSpeed) * 0.75
    // Modest spell share — not a full kit replay.
    const spell = Math.max(0, e.ap) * 0.22 + Math.max(0, e.ad) * 0.12
    const mitPhys = 100 / (100 + Math.max(0, opts.armor))
    const mitMag = 100 / (100 + Math.max(0, opts.mr))
    dps += aa * mitPhys + spell * mitMag
  }

  if (dps < 8) return durationSec
  const t = hp / dps
  // Only truncate when death is clearly inside the window.
  if (t >= durationSec * 0.9) return durationSec
  return Math.max(0.5, Math.min(durationSec, t))
}
