/**
 * Objective calculus ported/adapted from parlay-risk-sim (void grubs)
 * plus wiki combat buffs for dragons / baron / elder.
 */

export type DragonType =
  | 'infernal'
  | 'mountain'
  | 'cloud'
  | 'ocean'
  | 'hextech'
  | 'chemtech'
  | 'elemental'

export interface TeamObjectives {
  towers: number
  inhibs: number
  kills: number
  gold: number
  roleQuests: number
  voidGrubs: number
  dragons: DragonType[]
  dragonCount: number
  hasSoul: boolean
  soulType: DragonType | null
  barons: number
  baronActive: boolean
  baronEndsAtMs?: number | null
  elders: number
  elderActive: boolean
  elderEndsAtMs?: number | null
  heralds: number
}

export interface ScoreboardState {
  t: number
  blue: TeamObjectives
  red: TeamObjectives
  /** blue gold − red gold */
  goldDelta: number
  goldLeader: 'blue' | 'red' | 'even'
}

/** Wiki V26.11 / current SR — camp is 3 Voidgrubs (no respawn since V25.09). */
export const GRUB = {
  goldPerGrub: 30,
  xpPerGrub: 65,
  maxStacks: 3,
  /** Melee tick damage every 0.5s at stacks 0..3 */
  totvTickMeleeByStack: [0, 4, 12, 16] as const,
  /** Ranged tick damage every 0.5s at stacks 0..3 */
  totvTickRangedByStack: [0, 2, 6, 8] as const,
  totvTickInterval: 0.5,
  totvBurnDuration: 4,
  /** Hunger of the Void at 3 stacks: 1 Voidmite / 15s while in structure combat */
  hungerAtStacks: 3,
  hungerMiteCd: 15,
  hungerMites: 1,
  plateGold: 120,
  /**
   * First outer plate HP used for article-style gold-eq (Void_Grubs_koimari:
   * 256 true @ 3-stack melee / 900 HP → 34.13g). Not a live turret HP forecast.
   */
  plateHpFirst: 900,
  preferredSiegeSeconds: 8,
} as const

export function grubTickDamage(stacks: number, ranged: boolean): number {
  const s = Math.min(GRUB.maxStacks, Math.max(0, Math.floor(stacks)))
  const table = ranged ? GRUB.totvTickRangedByStack : GRUB.totvTickMeleeByStack
  return table[s] ?? 0
}

export function grubPackageGold(stacks: number): number {
  return GRUB.goldPerGrub * Math.min(GRUB.maxStacks, Math.max(0, stacks))
}

/** Touch burn DPS (true) at stack count — wiki tick / interval. */
export function grubTouchDps(stacks: number, ranged = false): number {
  const tick = grubTickDamage(stacks, ranged)
  return tick <= 0 ? 0 : tick / GRUB.totvTickInterval
}

/**
 * Article brief-siege ceiling O (Hunger mites omitted, matching PDF §2.6).
 * 3-stack melee @ 8s → 256 true → 34.13g plate progress @ 900 HP / 120g.
 */
export function grubTouchGoldEquivalent(
  stacks: number,
  siegeSeconds = GRUB.preferredSiegeSeconds,
  ranged = false,
): number {
  const dps = grubTouchDps(stacks, ranged)
  if (dps <= 0) return 0
  const totalDmg = dps * siegeSeconds
  return (totalDmg / GRUB.plateHpFirst) * GRUB.plateGold
}

/** Brief-ceiling Touch true damage (same window as grubTouchGoldEquivalent). */
export function grubTouchBriefCeilingTrue(
  stacks: number,
  siegeSeconds = GRUB.preferredSiegeSeconds,
  ranged = false,
): number {
  return grubTouchDps(stacks, ranged) * siegeSeconds
}

export function describeGrubs(stacks: number): string {
  const s = Math.min(GRUB.maxStacks, Math.max(0, stacks))
  if (s <= 0) return '0 grubs'
  const cash = grubPackageGold(s)
  const melee = grubTickDamage(s, false)
  const ranged = grubTickDamage(s, true)
  const hunger =
    s >= GRUB.hungerAtStacks
      ? ` · Hunger (${GRUB.hungerMites} mite / ${GRUB.hungerMiteCd}s)`
      : ''
  return `${s} grub${s === 1 ? '' : 's'} → ${cash}g · Touch ${melee}/${ranged} melee/ranged per 0.5s${hunger}`
}

/** Elemental dragon kills only — excludes the 4th soul-only entry when hasSoul. */
export function elementalDragons(obj: TeamObjectives | undefined | null): DragonType[] {
  if (!obj?.dragons?.length) return []
  return obj.hasSoul ? obj.dragons.slice(0, -1) : obj.dragons
}

export function countDragonStacks(
  obj: TeamObjectives | undefined | null,
  type: DragonType,
): number {
  return elementalDragons(obj).filter((d) => d === type).length
}

/** Wiki-correct short labels for history / scoreboard display. */
export function formatDragonTags(obj: TeamObjectives | undefined | null): string[] {
  if (!obj) return []
  const tags: string[] = []

  const infernal = Math.min(4, countDragonStacks(obj, 'infernal'))
  if (infernal > 0) tags.push(`infernal ${infernal * 3}% AD/AP`)

  const mountain = countDragonStacks(obj, 'mountain')
  if (mountain > 0) tags.push(`mountain ${mountain * 5}% armor/MR`)

  const cloud = countDragonStacks(obj, 'cloud')
  if (cloud > 0) tags.push(`cloud ${cloud * 5}% MS (OoC)`)

  const chemtech = countDragonStacks(obj, 'chemtech')
  if (chemtech > 0) tags.push(`chem ${chemtech * 6}% tenacity/HSP`)

  const hextech = countDragonStacks(obj, 'hextech')
  if (hextech > 0) tags.push(`hex ${hextech * 5} AH / ${hextech * 5}% AS`)

  if (countDragonStacks(obj, 'ocean') > 0) tags.push('ocean regen (OoC)')

  if (obj.hasSoul && obj.soulType) {
    tags.push(`${obj.soulType} soul`)
  }

  return tags
}

/** Fight-time damage amp from objectives — chemtech soul only (elder is burn, not amp). */
export function fightDamageAmp(
  obj: TeamObjectives | undefined | null,
  hpPct?: number,
): number {
  if (!obj?.hasSoul || obj.soulType !== 'chemtech') return 0
  if (hpPct !== undefined && hpPct > 0.5) return 0
  return 0.13
}

/**
 * Combat modifiers from permanent / active objectives for champion fights.
 * Grubs are structure-centric (shown on scoreboard); they do not amp champ DPS.
 */
export interface ObjectiveCombatMods {
  damageAmp: number
  damageReduction: number
  armorBonus: number
  mrBonus: number
  armorPercent: number
  mrPercent: number
  adPercent: number
  apPercent: number
  movespeedPct: number
  trueDamageOnHit: number
  omnivamp: number
  adBonus: number
  apBonus: number
  abilityHaste: number
  attackSpeedPercent: number
  tenacity: number
  healShieldPower: number
  notes: string[]
}

export function emptyMods(): ObjectiveCombatMods {
  return {
    damageAmp: 0,
    damageReduction: 0,
    armorBonus: 0,
    mrBonus: 0,
    armorPercent: 0,
    mrPercent: 0,
    adPercent: 0,
    apPercent: 0,
    movespeedPct: 0,
    trueDamageOnHit: 0,
    omnivamp: 0,
    adBonus: 0,
    apBonus: 0,
    abilityHaste: 0,
    attackSpeedPercent: 0,
    tenacity: 0,
    healShieldPower: 0,
    notes: [],
  }
}

export function combatModsFromObjectives(
  obj: TeamObjectives | undefined | null,
  gameTimeSec: number,
): ObjectiveCombatMods {
  const m = emptyMods()
  if (!obj) return m

  const infernalStacks = Math.min(4, countDragonStacks(obj, 'infernal'))
  if (infernalStacks > 0) {
    m.adPercent += infernalStacks * 0.03
    m.apPercent += infernalStacks * 0.03
    m.notes.push(`Infernal ×${infernalStacks}: +${infernalStacks * 3}% AD/AP`)
  }

  const mountainStacks = countDragonStacks(obj, 'mountain')
  if (mountainStacks > 0) {
    m.armorPercent += mountainStacks * 0.05
    m.mrPercent += mountainStacks * 0.05
    m.notes.push(`Mountain ×${mountainStacks}: +${mountainStacks * 5}% armor/MR`)
  }

  const cloudStacks = countDragonStacks(obj, 'cloud')
  if (cloudStacks > 0) {
    m.movespeedPct += cloudStacks * 0.05
    m.notes.push(`Cloud ×${cloudStacks}: +${cloudStacks * 5}% MS (OoC only)`)
  }

  const chemtechStacks = countDragonStacks(obj, 'chemtech')
  if (chemtechStacks > 0) {
    m.tenacity += chemtechStacks * 0.06
    m.healShieldPower += chemtechStacks * 0.06
    m.notes.push(
      `Chemtech ×${chemtechStacks}: +${chemtechStacks * 6}% tenacity & heal/shield power`,
    )
  }

  const hextechStacks = countDragonStacks(obj, 'hextech')
  if (hextechStacks > 0) {
    m.abilityHaste += hextechStacks * 5
    m.attackSpeedPercent += hextechStacks * 0.05
    m.notes.push(
      `Hextech ×${hextechStacks}: +${hextechStacks * 5} AH, +${hextechStacks * 5}% AS`,
    )
  }

  const oceanStacks = countDragonStacks(obj, 'ocean')
  if (oceanStacks > 0) {
    m.notes.push(`Ocean ×${oceanStacks}: HP regen (OoC only — not modeled in combat)`)
  }

  if (obj.hasSoul && obj.soulType) {
    switch (obj.soulType) {
      case 'infernal':
        m.notes.push('Infernal Soul: on-hit explosion (simplified)')
        m.trueDamageOnHit += 30
        break
      case 'chemtech':
        m.damageAmp += 0.13
        m.damageReduction += 0.13
        m.notes.push('Chemtech Soul below 50% HP (applied always as simplified)')
        break
      case 'cloud':
        m.movespeedPct += 0.15
        m.notes.push('Cloud Soul +15% MS')
        break
      case 'mountain':
        m.notes.push('Mountain Soul: shield on taking damage')
        break
      case 'hextech':
        m.notes.push('Hextech Soul: chain lightning on ability/AA hit')
        break
      case 'ocean':
        m.notes.push('Ocean Soul: bonus damage and healing on hit')
        break
      default:
        m.notes.push(`Dragon soul (${obj.soulType})`)
        break
    }
  }

  if (obj.baronActive) {
    // Wiki-ish scaling with game time
    const t = Math.max(20, Math.min(50, gameTimeSec / 60))
    m.adBonus += 12 + t * 0.7
    m.apBonus += 20 + t * 1.2
    m.omnivamp += 0.08
    m.notes.push('Baron buff active (AD/AP/omnivamp)')
  }

  if (obj.elderActive) {
    m.trueDamageOnHit += 45 + gameTimeSec * 0.15
    m.notes.push('Elder active (burn)')
  }

  if (obj.voidGrubs > 0) {
    m.notes.push(describeGrubs(obj.voidGrubs) + ' — structure siege, not champ DPS')
  }

  return m
}

export function emptyTeamObjectives(): TeamObjectives {
  return {
    towers: 0,
    inhibs: 0,
    kills: 0,
    gold: 0,
    roleQuests: 0,
    voidGrubs: 0,
    dragons: [],
    dragonCount: 0,
    hasSoul: false,
    soulType: null,
    barons: 0,
    baronActive: false,
    elders: 0,
    elderActive: false,
    heralds: 0,
  }
}

/** Apply objective combat buffs onto resolved champion stats. */
export function applyObjectiveModsToStats(
  stats: import('./types').CombatStats,
  mods: ObjectiveCombatMods,
): import('./types').CombatStats {
  return {
    ...stats,
    ad: (stats.ad + mods.adBonus) * (1 + mods.adPercent),
    ap: (stats.ap + mods.apBonus) * (1 + mods.apPercent),
    armor: (stats.armor + mods.armorBonus) * (1 + mods.armorPercent),
    mr: (stats.mr + mods.mrBonus) * (1 + mods.mrPercent),
    attackSpeed: stats.attackSpeed * (1 + mods.attackSpeedPercent),
    abilityHaste: stats.abilityHaste + mods.abilityHaste,
    healShieldPower: stats.healShieldPower + mods.healShieldPower,
    movespeed: stats.movespeed * (1 + mods.movespeedPct),
    omnivamp: stats.omnivamp + mods.omnivamp,
  }
}
