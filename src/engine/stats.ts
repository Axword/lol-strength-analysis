import { getChampion } from '../data/champions'
import { ITEMS } from '../data/items'
import type { ObjectiveCombatMods } from './objectives'
import { applyObjectiveModsToStats } from './objectives'
import {
  bonusAttackSpeedFromGrowth,
  growStat,
  RABADON_AP_AMP,
  RABADON_ITEM_ID,
  totalAttackSpeed,
} from './statStacking'
import type { CombatStats, FighterLoadout } from './types'
import { normalizeRanks } from './types'

export function buildStats(loadout: FighterLoadout): CombatStats {
  const champ = getChampion(loadout.championId)
  if (!champ) throw new Error(`Unknown champion: ${loadout.championId}`)

  const level = Math.min(18, Math.max(1, loadout.level))
  const s = champ.stats
  const baseAd = growStat(s.attackdamage, s.attackdamageperlevel, level)
  // Local Meraki ratio when present on the kit; else fall back to base AS.
  const asRatio = s.attackspeedratio ?? s.attackspeed

  let ad = baseAd
  let ap = 0
  let hpMax = growStat(s.hp, s.hpperlevel, level)
  let armor = growStat(s.armor, s.armorperlevel, level)
  let mr = growStat(s.spellblock, s.spellblockperlevel, level)
  let bonusAsFraction = bonusAttackSpeedFromGrowth(s.attackspeedperlevel, level)
  let critChance = 0
  let lethality = 0
  let armorPenPercent = 0
  let magicPenFlat = 0
  let magicPenPercent = 0
  let abilityHaste = 0
  // Flat MS only here; additive % (Cloud Soul) + soft cap happen in objective compose.
  let movespeed = s.movespeed
  let omnivamp = 0
  let hpRegen = growStat(s.hpregen, s.hpregenperlevel, level)

  for (const itemId of loadout.itemIds) {
    const item = ITEMS[itemId]
    if (!item) continue
    const st = item.stats
    ad += st.ad ?? 0
    ap += st.ap ?? 0
    hpMax += st.hp ?? 0
    armor += st.armor ?? 0
    mr += st.mr ?? 0
    // Item attackSpeed is a bonus AS fraction (0.5 = +50%), not attacks/sec.
    bonusAsFraction += st.attackSpeed ?? 0
    critChance += st.critChance ?? 0
    lethality += st.lethality ?? 0
    armorPenPercent += st.armorPenPercent ?? 0
    magicPenFlat += st.magicPenFlat ?? 0
    magicPenPercent += st.magicPenPercent ?? 0
    abilityHaste += st.abilityHaste ?? 0
    movespeed += st.movespeed ?? 0
    omnivamp += st.omnivamp ?? 0
    hpRegen += (st as { hpRegen?: number }).hpRegen ?? 0
  }

  // Rabadon Magical Opus is deferred to objective compose so Baron flat AP is
  // included before the 30% total-AP amp (manual theorycraft only).
  const attackSpeed = totalAttackSpeed(s.attackspeed, asRatio, bonusAsFraction)

  const live = loadout.liveStats
  const resolvedMax = live?.hpMax ?? hpMax
  // Current HP: live.hp if present, else hpPct * max, else full
  let current = live?.hp
  if (current == null && loadout.hpPct != null) {
    current = resolvedMax * loadout.hpPct
  }
  if (current == null) current = resolvedMax
  if (loadout.alive === false) current = 0

  return {
    level,
    hp: Math.max(0, current),
    hpMax: resolvedMax,
    armor: live?.armor ?? armor,
    mr: live?.mr ?? mr,
    ad: live?.ad ?? ad,
    ap: live?.ap ?? ap,
    attackSpeed: live?.attackSpeed ?? attackSpeed,
    attackSpeedRatio: asRatio,
    critChance: Math.min(1, critChance),
    critDamage: 1.75,
    lethality,
    armorPenPercent: Math.min(1, armorPenPercent),
    magicPenFlat,
    magicPenPercent: Math.min(1, magicPenPercent),
    healShieldPower: 0,
    omnivamp,
    abilityHaste,
    range: s.attackrange,
    movespeed,
    baseAd,
    hpRegen,
  }
}

/**
 * Full manual/live fighter resolve: buildStats → objective mods (with Rabadon
 * after Baron+Infernal when AP is not live-pinned).
 */
export function resolveFighterCombatStats(
  loadout: FighterLoadout,
  mods: ObjectiveCombatMods,
): CombatStats {
  const built = buildStats(loadout)
  const rabadonAmp =
    loadout.liveStats?.ap == null && loadout.itemIds.includes(RABADON_ITEM_ID)
      ? RABADON_AP_AMP
      : 0
  return applyObjectiveModsToStats(built, mods, loadout.liveStats, { rabadonAmp })
}

export function autoAttackDamage(stats: CombatStats): number {
  const critMult = 1 + stats.critChance * (stats.critDamage - 1)
  return stats.ad * critMult
}

export function ranksFromLoadout(loadout: FighterLoadout) {
  if (loadout.ranks) return normalizeRanks(loadout.ranks)
  return normalizeRanks(undefined, loadout.abilityRank ?? 1)
}
