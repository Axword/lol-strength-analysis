/**
 * Objective calculus: Void Grubs (structure-only), permanent dragon stacks,
 * dragon souls, Hand of Baron, and Elder.
 *
 * Accuracy stance: apply only effects the combat engine can represent exactly.
 * Timed/conditional procs are disclosed and excluded — never replaced by fake
 * flat, on-AA, or always-on damage.
 *
 * Permanent dragon values follow current Summoner's Rift wiki tables
 * (aligned with patch 26.11 grub Touch tables and current elemental permanent
 * bonuses). Hand of Baron AD/AP anchors are from Riot Patch 9.2 (published
 * 20:00 / 30:00 / 40:00 values); the continuous curve between anchors is an
 * audit-friendly inferred quadratic, not a published Riot formula.
 */

import {
  composeTheorycraftAp,
  softCapMovespeed,
} from './statStacking'

export type DragonType =
  | 'infernal'
  | 'mountain'
  | 'cloud'
  | 'ocean'
  | 'hextech'
  | 'chemtech'
  /** Legacy pseudo-label only — never a real permanent stack. */
  | 'elemental'

export interface TeamObjectives {
  towers?: number
  inhibs?: number
  kills?: number
  gold?: number
  roleQuests?: number
  voidGrubs?: number
  /**
   * One actual elemental type per dragon kill. The fourth entry is a real
   * permanent stack that also grants Soul — not a soul-only sentinel.
   */
  dragons?: DragonType[]
  dragonCount?: number
  hasSoul?: boolean
  soulType?: DragonType | null
  barons?: number
  baronActive?: boolean
  baronEndsAtMs?: number | null
  elders?: number
  elderActive?: boolean
  elderEndsAtMs?: number | null
  heralds?: number
}

export interface ScoreFieldCoverage {
  coverage: 'known' | 'unavailable'
  source?: string
}

export interface ScoreboardState {
  t: number
  blue: TeamObjectives
  red: TeamObjectives
  /** blue gold − red gold */
  goldDelta?: number
  goldLeader?: 'blue' | 'red' | 'even'
  coverage?: Record<string, ScoreFieldCoverage>
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

/** Hand of Baron duration (seconds). Used to infer slain time from endsAt. */
export const BARON_BUFF_DURATION_SEC = 180

/**
 * Official Patch 9.2 Hand of Baron AD/AP anchors (minute → AD, AP).
 * In-between values use {@link baronHandBonusesAtMinute} (inferred quadratic).
 */
export const BARON_HAND_ANCHORS = [
  { minute: 20, ad: 12, ap: 20 },
  { minute: 30, ad: 26, ap: 43 },
  { minute: 40, ad: 48, ap: 80 },
] as const

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
 * Explicit scenario — not live turret forecasting.
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

/**
 * Actual elemental dragon kills that grant permanent stacks.
 * Keeps the fourth kill (which also grants Soul). Ignores only the legacy
 * literal `"elemental"` pseudo-label if present in older feeds.
 */
export function elementalDragons(obj: TeamObjectives | undefined | null): DragonType[] {
  if (!obj?.dragons?.length) return []
  return obj.dragons.filter((d) => d !== 'elemental')
}

export function countDragonStacks(
  obj: TeamObjectives | undefined | null,
  type: DragonType,
): number {
  if (type === 'elemental') return 0
  return elementalDragons(obj).filter((d) => d === type).length
}

/** Short labels for history / scoreboard display (applied permanent values). */
export function formatDragonTags(obj: TeamObjectives | undefined | null): string[] {
  if (!obj) return []
  const tags: string[] = []

  const infernal = countDragonStacks(obj, 'infernal')
  if (infernal > 0) tags.push(`infernal ${infernal * 3}% AD/AP`)

  const mountain = countDragonStacks(obj, 'mountain')
  if (mountain > 0) tags.push(`mountain ${mountain * 5}% armor/MR`)

  const cloud = countDragonStacks(obj, 'cloud')
  if (cloud > 0) tags.push(`cloud ${cloud * 5}% slow resist / OoC MS`)

  const chemtech = countDragonStacks(obj, 'chemtech')
  if (chemtech > 0) tags.push(`chem ${chemtech * 6}% tenacity/HSP`)

  const hextech = countDragonStacks(obj, 'hextech')
  if (hextech > 0) tags.push(`hex ${hextech * 5} AH / ${hextech * 5}% AS`)

  const ocean = countDragonStacks(obj, 'ocean')
  if (ocean > 0) tags.push(`ocean ${ocean}× (2% missing HP / 5s — unmodeled)`)

  if (obj.hasSoul && obj.soulType && obj.soulType !== 'elemental') {
    tags.push(`${obj.soulType} soul`)
  }

  return tags
}

/**
 * Chemtech Soul fight-time damage amp helper — exact 13% when HP ≤ 50%.
 * Thresholded only; callers must not treat this as always-on without HP evidence.
 */
export function fightDamageAmp(
  obj: TeamObjectives | undefined | null,
  hpPct?: number,
): number {
  if (!obj?.hasSoul || obj.soulType !== 'chemtech') return 0
  if (hpPct !== undefined && hpPct > 0.5) return 0
  if (hpPct === undefined) return 0
  return 0.13
}

/**
 * Combat modifiers from permanent / active objectives for champion fights.
 * Grubs are structure-only and never amp champ DPS here.
 *
 * `applied` = effects written into CombatStats / packet multipliers this batch.
 * `disclosedOnly` = exact wiki effects excluded for missing proc/timing state.
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
  omnivamp: number
  adBonus: number
  apBonus: number
  abilityHaste: number
  attackSpeedPercent: number
  /**
   * Chemtech blight tenacity — tracked for career attribution only.
   * No CombatStats tenacity channel; never combat-applied.
   */
  tenacity: number
  /**
   * Chemtech blight heal/shield power — tracked for career attribution only.
   * No combat/utility consumer of healShieldPower yet; never combat-applied.
   */
  healShieldPower: number
  /** Effects written into CombatStats / packet multipliers when no live override blocks the field. */
  applied: string[]
  /** Exact effects disclosed / tracked but not combat-applied. */
  disclosedOnly: string[]
  /** applied + disclosedOnly (UI convenience). */
  notes: string[]
  /** Baron slain-time assumption when baron is active. */
  baronSlainAssumption?: string
}

/** Live/dummy fields that already include objective buffs (do not re-apply). */
export type ObjectiveLiveStatOverrides = Partial<
  Pick<
    import('./types').CombatStats,
    'ad' | 'ap' | 'armor' | 'mr' | 'attackSpeed' | 'movespeed'
  >
>

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
    omnivamp: 0,
    adBonus: 0,
    apBonus: 0,
    abilityHaste: 0,
    attackSpeedPercent: 0,
    tenacity: 0,
    healShieldPower: 0,
    applied: [],
    disclosedOnly: [],
    notes: [],
  }
}

function pushApplied(m: ObjectiveCombatMods, line: string): void {
  m.applied.push(line)
  m.notes.push(line)
}

function pushDisclosed(m: ObjectiveCombatMods, line: string): void {
  m.disclosedOnly.push(line)
  m.notes.push(`[disclosed] ${line}`)
}

/**
 * Infer Baron slain game-time (seconds).
 * When `baronEndsAtMs` is known: endsAt/1000 − 180.
 * Otherwise: current game time, labeled as fallback.
 */
export function inferBaronSlainGameTimeSec(
  obj: TeamObjectives,
  gameTimeSec: number,
): { slainSec: number; assumption: string } {
  if (obj.baronEndsAtMs != null && Number.isFinite(obj.baronEndsAtMs)) {
    return {
      slainSec: obj.baronEndsAtMs / 1000 - BARON_BUFF_DURATION_SEC,
      assumption:
        'Baron slain time inferred from baronEndsAtMs/1000 − 180 (buff duration)',
    }
  }
  return {
    slainSec: gameTimeSec,
    assumption:
      'Baron slain time unknown; using current game time as fallback (disclosed)',
  }
}

/**
 * Hand of Baron AD/AP at a given game minute.
 *
 * Official anchors (Riot Patch 9.2): 12/20 @ 20:00, 26/43 @ 30:00, 48/80 @ 40:00.
 * Between anchors: unique continuous quadratic through those three points
 * (inferred — Riot does not publish the hidden in-between formula).
 * Clamped before 20 and after 40. Values are fixed at Baron slain time.
 */
export function baronHandBonusesAtMinute(minute: number): { ad: number; ap: number } {
  const t = Math.max(20, Math.min(40, minute))
  // AD: 0.04 t² − 0.6 t + 8  through (20,12), (30,26), (40,48)
  const ad = 0.04 * t * t - 0.6 * t + 8
  // AP: 0.07 t² − 1.2 t + 16 through (20,20), (30,43), (40,80)
  const ap = 0.07 * t * t - 1.2 * t + 16
  return { ad, ap }
}

export function baronHandBonusesAtSlainSec(slainSec: number): { ad: number; ap: number } {
  return baronHandBonusesAtMinute(slainSec / 60)
}

export function combatModsFromObjectives(
  obj: TeamObjectives | undefined | null,
  gameTimeSec: number,
): ObjectiveCombatMods {
  const m = emptyMods()
  if (!obj) return m

  const infernalStacks = countDragonStacks(obj, 'infernal')
  if (infernalStacks > 0) {
    m.adPercent += infernalStacks * 0.03
    m.apPercent += infernalStacks * 0.03
    pushApplied(
      m,
      `Infernal ×${infernalStacks}: +${infernalStacks * 3}% AD/AP (where no authoritative live AD/AP override)`,
    )
  }

  const mountainStacks = countDragonStacks(obj, 'mountain')
  if (mountainStacks > 0) {
    m.armorPercent += mountainStacks * 0.05
    m.mrPercent += mountainStacks * 0.05
    pushApplied(
      m,
      `Mountain ×${mountainStacks}: +${mountainStacks * 5}% armor/MR (where no authoritative live armor/MR override)`,
    )
  }

  const cloudStacks = countDragonStacks(obj, 'cloud')
  if (cloudStacks > 0) {
    // Permanent Cloud: +5% slow resist and +5% out-of-combat MS per stack.
    // OoC MS must not inflate in-combat movespeed.
    pushDisclosed(
      m,
      `Cloud ×${cloudStacks}: +${cloudStacks * 5}% slow resist and +${cloudStacks * 5}% out-of-combat MS (not applied in combat)`,
    )
  }

  const chemtechStacks = countDragonStacks(obj, 'chemtech')
  if (chemtechStacks > 0) {
    // Tracked for career attribution only — no combat consumer of HSP or tenacity.
    m.tenacity += chemtechStacks * 0.06
    m.healShieldPower += chemtechStacks * 0.06
    pushDisclosed(
      m,
      `Chemtech ×${chemtechStacks}: +${chemtechStacks * 6}% heal/shield power (tracked only; no combat HSP consumer)`,
    )
    pushDisclosed(
      m,
      `Chemtech ×${chemtechStacks}: +${chemtechStacks * 6}% tenacity (tracked only; no CombatStats tenacity channel)`,
    )
  }

  const hextechStacks = countDragonStacks(obj, 'hextech')
  if (hextechStacks > 0) {
    m.abilityHaste += hextechStacks * 5
    m.attackSpeedPercent += hextechStacks * 0.05
    pushApplied(
      m,
      `Hextech ×${hextechStacks}: +${hextechStacks * 5} AH (always); +${hextechStacks * 5}% AS (where no authoritative live AS override)`,
    )
  }

  const oceanStacks = countDragonStacks(obj, 'ocean')
  if (oceanStacks > 0) {
    pushDisclosed(
      m,
      `Ocean ×${oceanStacks}: restores 2% missing HP per 5s (can tick in combat; not timed in this model)`,
    )
  }

  if (obj.hasSoul && obj.soulType && obj.soulType !== 'elemental') {
    switch (obj.soulType) {
      case 'cloud':
        m.movespeedPct += 0.15
        pushApplied(
          m,
          'Cloud Soul: +15% movespeed passive (where no authoritative live MS override)',
        )
        pushDisclosed(
          m,
          'Cloud Soul: +60% MS for 6s after R, 30s cooldown (timed; not modeled)',
        )
        break
      case 'chemtech':
        pushDisclosed(
          m,
          'Chemtech Soul: +13% damage dealt and −13% damage taken only while own HP ≤ 50% (thresholded helper available; not applied as always-on)',
        )
        break
      case 'infernal':
        pushDisclosed(
          m,
          'Infernal Soul: adaptive explosion 100 + 22.5% bAD + 13.5% AP + 2.75% bHP, 3s CD (proc; not modeled)',
        )
        break
      case 'hextech':
        pushDisclosed(
          m,
          'Hextech Soul: 25–50 true by level, 8s CD (proc; not modeled)',
        )
        break
      case 'mountain':
        pushDisclosed(
          m,
          'Mountain Soul: shield 220 + 16% bAD + 12% AP + 12% bHP after 5s without taking damage (timed; not modeled)',
        )
        break
      case 'ocean':
        pushDisclosed(
          m,
          'Ocean Soul: heal 150 + 26% bAD + 17% AP + 7% bHP plus mana over 4s (timed; not modeled)',
        )
        break
      default:
        pushDisclosed(m, `Dragon soul (${obj.soulType}): unmodeled`)
        break
    }
  }

  if (obj.baronActive) {
    const { slainSec, assumption } = inferBaronSlainGameTimeSec(obj, gameTimeSec)
    const { ad, ap } = baronHandBonusesAtSlainSec(slainSec)
    m.adBonus += ad
    m.apBonus += ap
    m.baronSlainAssumption = assumption
    pushApplied(
      m,
      `Baron Hand: +${ad.toFixed(2)} AD / +${ap.toFixed(2)} AP (fixed at slain ${(slainSec / 60).toFixed(2)}m; Patch 9.2 anchors, inferred quadratic between; where no authoritative live AD/AP override)`,
    )
    pushDisclosed(m, assumption)
    pushDisclosed(m, 'Baron Hand: no omnivamp (champion buff is AD/AP + minion empower only)')
  }

  if (obj.elderActive) {
    pushDisclosed(
      m,
      'Elder: 75–225 true burn over 2.25s plus <20% HP execute (timed/threshold; not modeled — zero fabricated per-AA damage)',
    )
  }

  if ((obj.voidGrubs ?? 0) > 0) {
    pushDisclosed(
      m,
      `${describeGrubs(obj.voidGrubs ?? 0)} — structure siege only, not champ DPS`,
    )
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

/**
 * Apply objective combat buffs onto resolved champion stats.
 *
 * When `liveStats` carries an authoritative field (timeline Riot stats_update or
 * absolute dummy pin), that field already includes live objective buffs — do not
 * layer Infernal/Mountain/Hex AS/Baron/Cloud Soul again on that field.
 * Ability haste still applies (no live AH channel). Chemtech HSP/tenacity are
 * never written into CombatStats (no combat consumer).
 *
 * Manual theorycraft compose order for AP: (flat + Baron) × (1+Infernal) × (1+Rabadon).
 * Hextech bonus AS% adds through `attackSpeedRatio`. Cloud Soul % MS then soft-caps once.
 */
export function applyObjectiveModsToStats(
  stats: import('./types').CombatStats,
  mods: ObjectiveCombatMods,
  liveStats?: ObjectiveLiveStatOverrides | null,
  theorycraft?: { rabadonAmp?: number },
): import('./types').CombatStats {
  const live = liveStats ?? undefined
  const ad =
    live?.ad != null ? stats.ad : (stats.ad + mods.adBonus) * (1 + mods.adPercent)
  const ap = composeTheorycraftAp({
    flatAp: stats.ap,
    baronAp: live?.ap != null ? 0 : mods.apBonus,
    infernalApPercent: live?.ap != null ? 0 : mods.apPercent,
    rabadonAmp: live?.ap != null ? 0 : (theorycraft?.rabadonAmp ?? 0),
    liveAp: live?.ap,
  })
  const armor =
    live?.armor != null
      ? stats.armor
      : (stats.armor + mods.armorBonus) * (1 + mods.armorPercent)
  const mr =
    live?.mr != null ? stats.mr : (stats.mr + mods.mrBonus) * (1 + mods.mrPercent)
  const asRatio = stats.attackSpeedRatio ?? 0.625
  const attackSpeed =
    live?.attackSpeed != null
      ? stats.attackSpeed
      : stats.attackSpeed + mods.attackSpeedPercent * asRatio
  // Authoritative live MS stays absolute. Theorycraft: % then soft-cap exactly once.
  const movespeed =
    live?.movespeed != null
      ? live.movespeed
      : softCapMovespeed(stats.movespeed * (1 + mods.movespeedPct))

  return {
    ...stats,
    ad,
    ap,
    armor,
    mr,
    attackSpeed,
    abilityHaste: stats.abilityHaste + mods.abilityHaste,
    // Intentionally omit mods.healShieldPower — tracked only until a consumer exists.
    healShieldPower: stats.healShieldPower,
    movespeed,
    omnivamp: stats.omnivamp + mods.omnivamp,
  }
}

/** Summarize applied vs disclosed objective effects for assumptions footers. */
export function formatObjectiveAssumptionLines(mods: ObjectiveCombatMods): string[] {
  const lines: string[] = []
  if (mods.applied.length) {
    lines.push(`Objectives applied: ${mods.applied.join('; ')}`)
  }
  if (mods.disclosedOnly.length) {
    lines.push(`Objectives disclosed only: ${mods.disclosedOnly.join('; ')}`)
  }
  return lines
}

/** True when a loadout pins any combat stat that must not be re-buffed. */
export function hasAuthoritativeCombatLiveStats(
  liveStats?: ObjectiveLiveStatOverrides | null,
): boolean {
  if (!liveStats) return false
  return (
    liveStats.ad != null ||
    liveStats.ap != null ||
    liveStats.armor != null ||
    liveStats.mr != null ||
    liveStats.attackSpeed != null ||
    liveStats.movespeed != null
  )
}
