/**
 * Turn compact Meraki ability kit data into runtime ChampionDefinitions.
 * Experimental / unvalidated — CORE and hand GAME kits still win at merge.
 */
import type {
  AbilityDefinition,
  AbilitySlot,
  ChampionDefinition,
  CombatStats,
  DamagePacket,
  DamageType,
} from '../engine/types'
import { bonusAd, rankOf } from '../engine/types'
import {
  MERAKI_ABILITY_KITS,
  type MerakiAbilityDamage,
  type MerakiAbilityKit,
  type MerakiChampionKit,
  type MerakiRatioStat,
} from './generated/merakiAbilityKits'

function rankValue(values: number[], rank: number): number {
  if (!values.length) return 0
  const idx = Math.min(values.length, Math.max(1, rank)) - 1
  return values[idx] ?? 0
}

function aa(shortCount: number, allinCount: number) {
  return (m: 'short' | 'allin' | 'extended') => {
    if (m === 'short') return shortCount
    if (m === 'allin') return allinCount
    return allinCount * 2 + 2
  }
}

function ratioStatValue(
  stat: MerakiRatioStat,
  attacker: CombatStats,
  defender: CombatStats,
): number {
  switch (stat) {
    case 'ap':
      return attacker.ap
    case 'ad':
      return attacker.ad
    case 'bonusAd':
      return bonusAd(attacker)
    case 'targetMaxHp':
      return defender.hpMax
    case 'targetMissingHp':
      return Math.max(0, defender.hpMax - defender.hp)
    default:
      return 0
  }
}

function damageFn(slot: AbilitySlot, name: string, spec: MerakiAbilityDamage | null, skillshot: boolean) {
  if (!spec) {
    return () => [] as DamagePacket[]
  }
  return (
    attacker: CombatStats,
    defender: CombatStats,
    ctx: { ranks?: Partial<Record<AbilitySlot, number>>; abilityRank?: number },
  ): DamagePacket[] => {
    const rank = Math.max(1, rankOf(ctx as never, slot))
    if (rankOf(ctx as never, slot) <= 0) return []
    let raw = rankValue(spec.base, rank)
    for (const ratio of spec.ratios) {
      raw += rankValue(ratio.values, rank) * ratioStatValue(ratio.stat, attacker, defender)
    }
    if (!(raw > 0)) return []
    return [
      {
        raw,
        type: spec.type as DamageType,
        source: name,
        slot,
        ...(skillshot ? { skillshot: true } : {}),
      },
    ]
  }
}

function toAbility(kit: MerakiAbilityKit): AbilityDefinition {
  const slot = kit.slot
  return {
    slot,
    name: kit.name,
    range: kit.range,
    cooldown: kit.cooldown,
    skillshot: kit.skillshot,
    damage: damageFn(slot, kit.name, kit.damage, kit.skillshot),
  }
}

export function championFromMerakiKit(kit: MerakiChampionKit): ChampionDefinition {
  return {
    id: kit.id,
    name: kit.name,
    title: kit.title,
    tags: kit.tags,
    passiveName: kit.passiveName,
    stats: kit.stats,
    abilities: kit.abilities.map(toAbility),
    autoAttacksInTrade: aa(kit.autos[0], kit.autos[1]),
  }
}

export const MERAKI_GENERATED_CHAMPIONS: Record<string, ChampionDefinition> =
  Object.fromEntries(
    Object.entries(MERAKI_ABILITY_KITS).map(([id, kit]) => [
      id,
      championFromMerakiKit(kit),
    ]),
  )
