/**
 * Manual theorycraft stat stacking helpers.
 *
 * Growth formula and MS soft caps follow Riot / League wiki champion-statistic
 * and movement-speed rules. Attack-speed ratio values for CORE kits are taken
 * from local Meraki ingest (`public/data/lolwiki/champions-full.json`,
 * `stats.attackSpeedRatio.flat`). Rabadon Magical Opus 30% is from local
 * `public/data/lolwiki/items-summoners-rift.json` id 3089.
 *
 * These helpers do not invent missing ratios: callers fall back to base AS when
 * `attackspeedratio` is absent on a kit definition.
 */

/** Growth factor at champion level n: (n−1)×(0.7025 + 0.0175×(n−1)). Equals 17 at 18. */
export function growthMultiplier(level: number): number {
  const n = Math.min(18, Math.max(1, Math.floor(level)))
  return (n - 1) * (0.7025 + 0.0175 * (n - 1))
}

/** Interpolated per-level growth (not naive linear mid-levels). */
export function growStat(base: number, perLevel: number, level: number): number {
  return base + perLevel * growthMultiplier(level)
}

/**
 * Bonus attack-speed fraction from level growth.
 * `perLevelPercent` is the champion table value (e.g. 3.65 means +3.65% AS per growth step).
 */
export function bonusAttackSpeedFromGrowth(
  perLevelPercent: number,
  level: number,
): number {
  return (perLevelPercent / 100) * growthMultiplier(level)
}

/**
 * Total attacks/sec = base AS + bonusAS% × AS ratio.
 * Item `attackSpeed: 0.5` means +50% bonus AS (fraction 0.5), not +0.5 AS.
 */
export function totalAttackSpeed(
  baseAs: number,
  asRatio: number,
  bonusAsFraction: number,
): number {
  return baseAs + bonusAsFraction * asRatio
}

/**
 * Movement-speed soft caps (wiki): raw≤415 unchanged; (415,490] → raw×0.8+83;
 * raw>490 → raw×0.5+230. Apply exactly once after all flat + additive % MS.
 */
export function softCapMovespeed(raw: number): number {
  if (raw <= 415) return raw
  if (raw <= 490) return raw * 0.8 + 83
  return raw * 0.5 + 230
}

/** Local wiki item 3089 Magical Opus — increase total AP by 30%. */
export const RABADON_ITEM_ID = '3089'
export const RABADON_AP_AMP = 0.3

/**
 * Compose theorycraft AP: (item/base flat + Baron flat) × (1+Infernal) × (1+Rabadon).
 * Skip entirely when AP is live-pinned.
 */
export function composeTheorycraftAp(args: {
  flatAp: number
  baronAp: number
  infernalApPercent: number
  rabadonAmp: number
  liveAp?: number | null
}): number {
  if (args.liveAp != null) return args.liveAp
  const afterObjectives =
    (args.flatAp + args.baronAp) * (1 + args.infernalApPercent)
  return afterObjectives * (1 + Math.max(0, args.rabadonAmp))
}
