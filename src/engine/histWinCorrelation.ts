/**
 * Champion-history column ordering by win-relevance at game time.
 *
 * Grounded in parlay-risk-sim research (pro OE + draft phase models):
 * - `draft_phase_beatdown.json` win_given_gold.gold_k ≈ 0.80@10 → 0.46@25
 *   (~19pp → ~11pp map WR per +1k gold near even)
 * - `metric_correlation_matrix.json`: gold15 (r≈0.53) > gold10 (r≈0.43);
 *   end tower/baron/dragon dominate raw r but are team outcomes, not champ cells
 * - Fight-gold alone is weak (AUC~0.59); champ damage is the best fight proxy
 *   available on this board once gold is accounted for
 *
 * Champ-level proxies are scored relative to those findings — not a new fit.
 */

export type HistStatKey =
  | 'gold'
  | 'dmg'
  | 'taken'
  | 'mitigated'
  | 'ccOrTurret'
  | 'drake'
  | 'grub'
  | 'as'
  | 'ah'
  | 'extra'

export type HistPhase = 'early' | 'mid' | 'late'

/** Minutes used in parlay `win_given_gold` fits. */
const GOLD_K_BY_MINUTE: Array<{ min: number; goldK: number }> = [
  { min: 10, goldK: 0.797 },
  { min: 15, goldK: 0.572 },
  { min: 20, goldK: 0.498 },
  { min: 25, goldK: 0.462 },
]

export function histPhase(gameTimeSec: number): HistPhase {
  const m = gameTimeSec / 60
  if (m < 14) return 'early'
  if (m < 25) return 'mid'
  return 'late'
}

/** Interpolated gold_k (logit per 1k gold lead) at this minute. */
export function goldWinCoefAtMinute(gameTimeSec: number): number {
  const m = Math.max(0, gameTimeSec / 60)
  if (m <= GOLD_K_BY_MINUTE[0].min) return GOLD_K_BY_MINUTE[0].goldK
  for (let i = 1; i < GOLD_K_BY_MINUTE.length; i++) {
    const a = GOLD_K_BY_MINUTE[i - 1]
    const b = GOLD_K_BY_MINUTE[i]
    if (m <= b.min) {
      const t = (m - a.min) / (b.min - a.min)
      return a.goldK + (b.goldK - a.goldK) * t
    }
  }
  return GOLD_K_BY_MINUTE[GOLD_K_BY_MINUTE.length - 1].goldK
}

/** ≈ percentage points of map WR per +100g near even (sigmoid slope/10). */
export function goldPpPer100gAtEven(gameTimeSec: number): number {
  const betaPerGold = goldWinCoefAtMinute(gameTimeSec) / 1000
  // d(sigmoid)/dx at 0 = 0.25 * β; ×100 gold ×100 for pp
  return 0.25 * betaPerGold * 100 * 100
}

/**
 * Relative win-relevance weights for board columns (higher = more predictive).
 * Gold anchor tracks parlay gold_k; others are phase proxies for champ stats.
 */
export function histStatWeights(
  gameTimeSec: number,
  tab: 'champs' | 'all',
): Record<HistStatKey, number> {
  const phase = histPhase(gameTimeSec)
  const goldK = goldWinCoefAtMinute(gameTimeSec)
  // Scale gold to a comfortable 0–100 board weight (~80 @10, ~46 @25).
  // Gold stays #1 among champ cells (parlay win_given_gold); other weights
  // are relative proxies and are capped strictly below gold.
  const gold = goldK * 100
  const below = (w: number) => Math.min(w, gold - 1)

  if (phase === 'early') {
    return {
      gold,
      dmg: below(48),
      grub: below(42), // void-grub window; structure value
      ccOrTurret: below(tab === 'all' ? 28 : 36), // CC fights; turrets rare
      taken: below(32),
      mitigated: below(28),
      extra: below(tab === 'all' ? 40 : 30), // CS path ≈ gold path early
      drake: below(18),
      as: below(14),
      ah: below(14),
    }
  }
  if (phase === 'mid') {
    return {
      gold,
      dmg: below(58), // fights convert gold
      ccOrTurret: below(tab === 'all' ? 52 : 40), // towers / CC setup
      drake: below(46),
      taken: below(36),
      mitigated: below(34),
      extra: below(tab === 'all' ? 32 : 28),
      grub: below(16), // post-grubs
      as: below(16),
      ah: below(16),
    }
  }
  // late — tower pressure + damage rise as closeout proxies under gold
  return {
    gold,
    dmg: below(62),
    ccOrTurret: below(tab === 'all' ? 58 : 38),
    taken: below(42),
    mitigated: below(40),
    drake: below(36),
    extra: below(tab === 'all' ? 28 : 26),
    as: below(18),
    ah: below(18),
    grub: below(8),
  }
}

export interface HistColumnRank {
  key: HistStatKey
  weight: number
}

export function histColumnsByWinCorrelation(
  gameTimeSec: number,
  tab: 'champs' | 'all',
): HistColumnRank[] {
  const w = histStatWeights(gameTimeSec, tab)
  return (Object.keys(w) as HistStatKey[])
    .map((key) => ({ key, weight: w[key] }))
    .sort((a, b) => b.weight - a.weight)
}

export function histOrderNote(gameTimeSec: number): string {
  const phase = histPhase(gameTimeSec)
  const pp = goldPpPer100gAtEven(gameTimeSec)
  return `Columns ordered by win relevance @ ${Math.floor(gameTimeSec / 60)}m (${phase}) — gold ≈ ${pp.toFixed(1)}pp map WR / +100g near even (parlay-risk-sim win_given_gold)`
}
