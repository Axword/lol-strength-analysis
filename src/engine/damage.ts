import type { CombatStats, DamagePacket, DamageType } from './types'

/** Effective armor after lethality + % pen (standard LoL order of operations). */
export function effectiveArmor(defender: CombatStats, attacker: CombatStats): number {
  const afterPercent = defender.armor * (1 - attacker.armorPenPercent)
  const lethality =
    attacker.lethality * (0.6 + (0.4 * attacker.level) / 18)
  return Math.max(0, afterPercent - lethality)
}

export function effectiveMr(defender: CombatStats, attacker: CombatStats): number {
  const afterPercent = defender.mr * (1 - attacker.magicPenPercent)
  return Math.max(0, afterPercent - attacker.magicPenFlat)
}

export function mitigate(
  raw: number,
  type: DamageType,
  attacker: CombatStats,
  defender: CombatStats,
): number {
  if (raw <= 0) return 0
  if (type === 'true') return raw
  if (type === 'physical') {
    const armor = effectiveArmor(defender, attacker)
    return (raw * 100) / (100 + armor)
  }
  const mr = effectiveMr(defender, attacker)
  return (raw * 100) / (100 + mr)
}

export function sumMitigated(
  packets: DamagePacket[],
  attacker: CombatStats,
  defender: CombatStats,
): number {
  return packets.reduce(
    (sum, p) => sum + mitigate(p.raw, p.type, attacker, defender),
    0,
  )
}

export function sumRaw(packets: DamagePacket[]): number {
  return packets.reduce((sum, p) => sum + p.raw, 0)
}
