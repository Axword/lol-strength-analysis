import { CHAMPIONS } from '../data/champions'
import { ITEMS } from '../data/items'
import type { CombatStats, FighterLoadout } from './types'
import { normalizeRanks } from './types'

function scale(base: number, perLevel: number, level: number): number {
  return base + perLevel * (level - 1)
}

export function buildStats(loadout: FighterLoadout): CombatStats {
  const champ = CHAMPIONS[loadout.championId]
  if (!champ) throw new Error(`Unknown champion: ${loadout.championId}`)

  const level = Math.min(18, Math.max(1, loadout.level))
  const s = champ.stats
  const baseAd = scale(s.attackdamage, s.attackdamageperlevel, level)

  let ad = baseAd
  let ap = 0
  let hpMax = scale(s.hp, s.hpperlevel, level)
  let armor = scale(s.armor, s.armorperlevel, level)
  let mr = scale(s.spellblock, s.spellblockperlevel, level)
  let attackSpeed =
    s.attackspeed * (1 + (s.attackspeedperlevel * (level - 1)) / 100)
  let critChance = 0
  let lethality = 0
  let armorPenPercent = 0
  let magicPenFlat = 0
  let magicPenPercent = 0
  let abilityHaste = 0
  let movespeed = s.movespeed
  let omnivamp = 0
  let hpRegen = scale(s.hpregen, s.hpregenperlevel, level)

  for (const itemId of loadout.itemIds) {
    const item = ITEMS[itemId]
    if (!item) continue
    const st = item.stats
    ad += st.ad ?? 0
    ap += st.ap ?? 0
    hpMax += st.hp ?? 0
    armor += st.armor ?? 0
    mr += st.mr ?? 0
    attackSpeed += st.attackSpeed ?? 0
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

  if (loadout.itemIds.includes('3089') && !loadout.liveStats?.ap) {
    ap *= 1.3
  }

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

export function autoAttackDamage(stats: CombatStats): number {
  const critMult = 1 + stats.critChance * (stats.critDamage - 1)
  return stats.ad * critMult
}

export function ranksFromLoadout(loadout: FighterLoadout) {
  if (loadout.ranks) return normalizeRanks(loadout.ranks)
  return normalizeRanks(undefined, loadout.abilityRank ?? 1)
}
