/**
 * Combat item passives layered onto the wiki/DDragon catalog.
 * Stats stay in generated data; procs/DoTs/shred live here.
 */
import type { CombatStats, DamagePacket, ItemDefinition } from '../engine/types'

export type ItemPassiveHooks = Pick<
  ItemDefinition,
  'onAbilityMagic' | 'onAbilityPhysical'
> & {
  /** Armor shred 0–1 applied for the fight (e.g. Cleaver full stacks). */
  armorShred?: (ctx: ItemPassiveContext) => number
  /** Damage amp 0–1 (e.g. Liandry vs high-HP). */
  damageAmp?: (ctx: ItemPassiveContext) => number
  /** Extra packets over the fight window (burns, etc.). */
  fightPackets?: (ctx: ItemPassiveContext) => DamagePacket[]
}

export interface ItemPassiveContext {
  attacker: CombatStats
  defender: CombatStats
  durationSec: number
  /** Ability casts that can proc spellblade this window */
  abilityProcs: number
}

/** Sheen line — Spellblade on next AA after an ability. */
function spellbladePhysical(
  name: string,
  baseAdMult: number,
): ItemPassiveHooks {
  return {
    onAbilityPhysical: (ad) => {
      // Fallback when base AD unknown at call site — combat prefers fightPackets.
      return ad * baseAdMult * 0.35
    },
    fightPackets: (ctx) => {
      if (ctx.abilityProcs <= 0) return []
      // One Spellblade proc per window (Sheen ICD ≈ fight-relevant).
      const raw = ctx.attacker.baseAd * baseAdMult
      return [
        {
          raw,
          type: 'physical',
          source: `${name} (Spellblade)`,
          slot: 'AA',
        },
      ]
    },
  }
}

/**
 * Liandry's Torment (6653):
 * - Burn ≈ % max HP magic over ~3s, scaled lightly with AP, stretched to fight length
 * - Capstone amp vs higher-HP targets (theorycraft curve when bonus HP unknown)
 */
const LIANDRY: ItemPassiveHooks = {
  damageAmp: (ctx) => {
    // Soft stand-in for 0–12% vs bonus HP: ~3% at 3k max HP, caps at 12%.
    return Math.min(0.12, Math.max(0, ctx.defender.hpMax / 100_000))
  },
  fightPackets: (ctx) => {
    const ap = Math.max(0, ctx.attacker.ap)
    const pct = 0.01 + 0.015 * (ap / 100)
    // Full burn cycle is ~3s; scale by fight length so longer windows tick more.
    const cycles = Math.max(0.35, ctx.durationSec / 3)
    const raw = ctx.defender.hpMax * pct * Math.min(2.2, cycles)
    return [
      {
        raw,
        type: 'magical',
        source: "Liandry's Torment (burn)",
        slot: 'P',
      },
    ]
  },
}

/**
 * Black Cleaver (3071): 5% armor / stack, max 6 → 30%.
 * Assume near-full stacks in all-in / extended windows; partial in short.
 */
const BLACK_CLEAVER: ItemPassiveHooks = {
  armorShred: (ctx) => {
    const stacks =
      ctx.durationSec >= 12 ? 6 : ctx.durationSec >= 6 ? 5 : ctx.durationSec >= 3.5 ? 4 : 3
    return Math.min(0.3, stacks * 0.05)
  },
}

export const ITEM_PASSIVES: Record<string, ItemPassiveHooks> = {
  '3057': spellbladePhysical('Sheen', 1.0),
  '3100': spellbladePhysical("Lich Bane", 0.75), // magic in real game; approximate as physical* for now via onAbility — override below
  '3078': spellbladePhysical('Trinity Force', 2.0),
  '3071': BLACK_CLEAVER,
  '6653': LIANDRY,
}

// Lich Bane is magic spellblade — replace with magic packets
ITEM_PASSIVES['3100'] = {
  fightPackets: (ctx) => {
    if (ctx.abilityProcs <= 0) return []
    const raw = ctx.attacker.baseAd * 0.75 + ctx.attacker.ap * 0.4
    return [
      {
        raw,
        type: 'magical',
        source: 'Lich Bane (Spellblade)',
        slot: 'AA',
      },
    ]
  },
}

export function getItemPassive(itemId: string): ItemPassiveHooks | null {
  return ITEM_PASSIVES[itemId] ?? null
}
