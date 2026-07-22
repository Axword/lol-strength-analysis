import type {
  AbilityContext,
  AbilityDefinition,
  AbilityUtility,
  CombatStats,
  ResolvedUtility,
} from './types'

/**
 * Utility-only abilities (Nasus W, Zilean E, etc.) must never be dropped
 * just because they deal 0 damage — slows/CC reshape fight outcomes.
 */
export function resolveUtility(
  ability: AbilityDefinition,
  attacker: CombatStats,
  defender: CombatStats,
  ctx: AbilityContext,
): AbilityUtility | null {
  if (!ability.utility) {
    if (ability.engageCc) return { hardCc: true, engageCc: true }
    return null
  }
  const u =
    typeof ability.utility === 'function'
      ? ability.utility(attacker, defender, ctx)
      : ability.utility
  if (ability.engageCc) {
    return { ...u, hardCc: u.hardCc ?? true, engageCc: true }
  }
  return u
}

export function emptyResolvedUtility(): ResolvedUtility {
  return {
    enemySlow: 0,
    enemyAsSlow: 0,
    hardCc: false,
    selfMsBuff: 0,
    armorShred: 0,
    mrShred: 0,
    damageAmp: 0,
    damageReduction: 0,
    sources: [],
  }
}

/** Merge utility casts — take strongest of each kind. */
export function mergeUtility(
  into: ResolvedUtility,
  next: AbilityUtility,
  source: string,
): ResolvedUtility {
  const sources = into.sources.includes(source)
    ? into.sources
    : [...into.sources, source]
  return {
    enemySlow: Math.max(into.enemySlow, next.enemySlow ?? 0),
    enemyAsSlow: Math.max(into.enemyAsSlow, next.enemyAsSlow ?? 0),
    hardCc: into.hardCc || !!next.hardCc || !!next.engageCc,
    selfMsBuff: Math.max(into.selfMsBuff, next.selfMsBuff ?? 0),
    armorShred: Math.max(into.armorShred, next.armorShred ?? 0),
    mrShred: Math.max(into.mrShred, next.mrShred ?? 0),
    damageAmp: Math.max(into.damageAmp, next.damageAmp ?? 0),
    damageReduction: Math.max(into.damageReduction, next.damageReduction ?? 0),
    sources,
  }
}

/**
 * How many autos survive under incoming MS/AS slows.
 * Nasus W-style wither cuts AS hard; MS slows cut chase autos for melee.
 */
export function autosAfterUtility(
  baseAutos: number,
  incoming: ResolvedUtility,
  opts?: { durationSec?: number },
): number {
  if (baseAutos <= 0) return 0
  const asFactor = 1 - Math.min(0.85, incoming.enemyAsSlow)
  // MS slow mainly eats chase/reposition autos, not point-blank ones
  const msFactor = 1 - Math.min(0.45, incoming.enemySlow * 0.55)
  // Engage hard-CC is a brief lock, not a full-window wither.
  // Only apply the heavy AA cut in short windows (≤6s).
  const dur = opts?.durationSec
  const hardCcFactor =
    incoming.hardCc && (dur == null || dur <= 6) ? 0.65 : incoming.hardCc ? 0.92 : 1
  return Math.max(0, Math.round(baseAutos * asFactor * msFactor * hardCcFactor))
}

/** Skillshots land more often when the target is slowed / hard-CCed. */
export function xhUtilityMultiplier(targetDebuffs: ResolvedUtility): number {
  let m = 1
  m += Math.min(0.22, targetDebuffs.enemySlow * 0.28)
  m += Math.min(0.12, targetDebuffs.enemyAsSlow * 0.1)
  if (targetDebuffs.hardCc) m += 0.18
  return m
}

/** Apply shred from attackers onto the defender pool used for mitigation. */
export function applyShredToStats(
  defender: CombatStats,
  attackerUtility: ResolvedUtility,
): CombatStats {
  if (!attackerUtility.armorShred && !attackerUtility.mrShred) return defender
  return {
    ...defender,
    armor: defender.armor * (1 - Math.min(0.5, attackerUtility.armorShred)),
    mr: defender.mr * (1 - Math.min(0.5, attackerUtility.mrShred)),
  }
}

/** Incoming damage reduction from self utility (e.g. Garen W). */
export function damageTakenMultiplier(selfUtility: ResolvedUtility): number {
  return 1 - Math.min(0.5, selfUtility.damageReduction)
}

export function damageDealtMultiplier(attackerUtility: ResolvedUtility): number {
  return 1 + Math.min(0.4, attackerUtility.damageAmp)
}

export function describeUtility(u: ResolvedUtility): string | null {
  if (!u.sources.length) return null
  const bits: string[] = []
  if (u.enemySlow > 0) bits.push(`${Math.round(u.enemySlow * 100)}% slow`)
  if (u.enemyAsSlow > 0) bits.push(`${Math.round(u.enemyAsSlow * 100)}% AS wither`)
  if (u.hardCc) bits.push('hard CC')
  if (u.selfMsBuff > 0) bits.push(`+${Math.round(u.selfMsBuff * 100)}% MS`)
  if (u.armorShred > 0) bits.push(`${Math.round(u.armorShred * 100)}% armor shred`)
  if (u.mrShred > 0) bits.push(`${Math.round(u.mrShred * 100)}% MR shred`)
  if (u.damageAmp > 0) bits.push(`+${Math.round(u.damageAmp * 100)}% dmg amp`)
  if (u.damageReduction > 0) {
    bits.push(`${Math.round(u.damageReduction * 100)}% dmg reduction`)
  }
  if (!bits.length) return null
  return `Utility (${u.sources.join(', ')}): ${bits.join(', ')}`
}
