import { CHAMPIONS } from '../data/champions'
import { ITEMS } from '../data/items'
import { resolveRuneId } from '../data/runes'
import { sumMitigated, sumRaw } from './damage'
import { abilityBudget, autosForBudget } from './hpBudget'
import {
  applyObjectiveModsToStats,
  combatModsFromObjectives,
  emptyMods,
  type ObjectiveCombatMods,
} from './objectives'
import { autoAttackDamage, buildStats, ranksFromLoadout } from './stats'
import {
  applyShredToStats,
  autosAfterUtility,
  damageDealtMultiplier,
  damageTakenMultiplier,
  emptyResolvedUtility,
  mergeUtility,
  resolveUtility,
  xhUtilityMultiplier,
} from './utility'
import {
  abilityCastsInFight,
  autosForDuration,
  fightDurationSec,
  sustainHeal,
} from './fightDuration'
import { estimateFightOdds } from './gameStateOdds'
import { applyXhModeToPacket, estimateXh, type XhMode } from './xh'
import { resolveCastVisionSoft } from './vision'
import type {
  AbilityDefinition,
  AbilitySlot,
  CombatStats,
  DamagePacket,
  FighterLoadout,
  FighterResult,
  MatchupInput,
  MatchupResult,
  ResolvedUtility,
  SideResult,
  StrengthBand,
  TradeMode,
} from './types'

function isAlive(loadout: FighterLoadout): boolean {
  if (loadout.alive === false) return false
  if (loadout.hpPct != null && loadout.hpPct <= 0) return false
  if (loadout.liveStats?.hp != null && loadout.liveStats.hp <= 0) return false
  return true
}

/** Flash ready from equipped summoners + optional CD clock. Undefined = CD unknown. */
function flashReadyFromLoadout(f: FighterLoadout): boolean | undefined {
  const spells = f.summonerSpells ?? []
  const hasFlash = spells.some((s) => /flash/i.test(s))
  if (!hasFlash && spells.length > 0) return false
  if (f.flashCdRemainingSec != null) return f.flashCdRemainingSec <= 0
  if (spells.length === 0) return undefined
  return undefined
}

function modsForSide(
  side: 'blue' | 'red',
  input: MatchupInput,
): ObjectiveCombatMods {
  if (!input.objectives) return emptyMods()
  return combatModsFromObjectives(
    input.objectives[side],
    input.objectives.gameTimeSec,
  )
}

/** Defender-side incoming damage reduction from objectives (Chemtech Soul, etc.). */
function objectiveDamageTakenMultiplier(mods: ObjectiveCombatMods): number {
  return 1 - Math.min(0.5, mods.damageReduction)
}

function amplifyWithObjectives(
  packets: DamagePacket[],
  mods: ObjectiveCombatMods,
  fighterIndex: number,
): DamagePacket[] {
  const amp = 1 + mods.damageAmp
  const out: DamagePacket[] = packets.map((p) => ({
    ...p,
    raw: p.raw * amp,
    ...(p.rawBeforeXh != null ? { rawBeforeXh: p.rawBeforeXh * amp } : {}),
  }))
  if (mods.trueDamageOnHit > 0) {
    const autos = packets.filter((p) => p.slot === 'AA' && !p.omitted).length
    if (autos > 0) {
      out.push({
        raw: mods.trueDamageOnHit * autos,
        type: 'true',
        source: 'Elder dragon burn',
        slot: 'AA',
        fighterIndex,
      })
    }
  }
  return out
}

function hpPctOf(loadout: FighterLoadout, stats: CombatStats): number {
  if (loadout.hpPct != null) return Math.max(0, Math.min(1, loadout.hpPct))
  if (stats.hpMax > 0) return Math.max(0, Math.min(1, stats.hp / stats.hpMax))
  return stats.hp > 0 ? 1 : 0
}

function averageStats(statsList: CombatStats[]): CombatStats {
  const n = statsList.length || 1
  const sum = statsList.reduce(
    (acc, s) => ({
      level: acc.level + s.level,
      hp: acc.hp + s.hp,
      hpMax: acc.hpMax + s.hpMax,
      armor: acc.armor + s.armor,
      mr: acc.mr + s.mr,
      ad: acc.ad + s.ad,
      ap: acc.ap + s.ap,
      attackSpeed: acc.attackSpeed + s.attackSpeed,
      critChance: acc.critChance + s.critChance,
      critDamage: acc.critDamage + s.critDamage,
      lethality: acc.lethality + s.lethality,
      armorPenPercent: acc.armorPenPercent + s.armorPenPercent,
      magicPenFlat: acc.magicPenFlat + s.magicPenFlat,
      magicPenPercent: acc.magicPenPercent + s.magicPenPercent,
      healShieldPower: acc.healShieldPower + s.healShieldPower,
      omnivamp: acc.omnivamp + s.omnivamp,
      abilityHaste: acc.abilityHaste + s.abilityHaste,
      range: acc.range + s.range,
      movespeed: acc.movespeed + s.movespeed,
      baseAd: acc.baseAd + s.baseAd,
      hpRegen: acc.hpRegen + s.hpRegen,
    }),
    {
      level: 0, hp: 0, hpMax: 0, armor: 0, mr: 0, ad: 0, ap: 0, attackSpeed: 0,
      critChance: 0, critDamage: 0, lethality: 0, armorPenPercent: 0,
      magicPenFlat: 0, magicPenPercent: 0, healShieldPower: 0, omnivamp: 0,
      abilityHaste: 0, range: 0, movespeed: 0, baseAd: 0, hpRegen: 0,
    },
  )

  return {
    level: sum.level / n,
    hp: sum.hp,
    hpMax: sum.hpMax,
    armor: sum.armor / n,
    mr: sum.mr / n,
    ad: sum.ad / n,
    ap: sum.ap / n,
    attackSpeed: sum.attackSpeed / n,
    critChance: sum.critChance / n,
    critDamage: sum.critDamage / n,
    lethality: sum.lethality / n,
    armorPenPercent: sum.armorPenPercent / n,
    magicPenFlat: sum.magicPenFlat / n,
    magicPenPercent: sum.magicPenPercent / n,
    healShieldPower: sum.healShieldPower / n,
    omnivamp: sum.omnivamp / n,
    abilityHaste: sum.abilityHaste / n,
    range: sum.range / n,
    movespeed: sum.movespeed / n,
    baseAd: sum.baseAd / n,
    hpRegen: sum.hpRegen,
  }
}

function teamLabel(loadouts: FighterLoadout[]): string {
  const names = loadouts.map(
    (l) => CHAMPIONS[l.championId]?.name ?? l.championId,
  )
  if (!names.length) return 'Empty'
  if (names.length <= 2) return names.join(' + ')
  return `${names[0]} + ${names.length - 1} more`
}

function ccBreakReadyFromLoadout(f: FighterLoadout): boolean {
  const spells = f.summonerSpells ?? []
  const hasBreak = spells.some((s) =>
    /cleanse|quicksilver|qss|mikael/i.test(s),
  )
  if (!hasBreak) return false
  if (f.ccBreakCdRemainingSec == null) return true
  return f.ccBreakCdRemainingSec <= 0
}

/** Ghost strafe only with explicit buff or live MS bump — not spell-equipped alone. */
export function ghostBuffActive(
  f: FighterLoadout,
  liveMs: number,
  baseMs: number,
): boolean {
  if (f.ghostActive === true) return true
  const hasGhost = (f.summonerSpells ?? []).some((s) => /ghost/i.test(s))
  if (!hasGhost) return false
  return liveMs >= baseMs * 1.05
}

/** Autos MS law → σ_juke targetMovespeed (not utilMult alone). */
export function effectiveTargetMs(
  enemy: FighterLoadout,
  baseMs: number,
  util: ResolvedUtility,
): number {
  const live = enemy.liveStats?.movespeed ?? baseMs
  const msFactor = 1 - Math.min(0.45, (util.enemySlow ?? 0) * 0.55)
  return live * msFactor
}

export type XhRow = {
  xH: number
  bands?: {
    worst: number
    typical: number
    best: number
    mix?: number
  }
}

export function scaleXhBands(
  bands: NonNullable<XhRow['bands']>,
  utilMult: number,
): NonNullable<XhRow['bands']> {
  const scale = (p: number) => Math.min(0.97, p * utilMult)
  return {
    worst: scale(bands.worst),
    typical: scale(bands.typical),
    best: scale(bands.best),
    mix: bands.mix != null ? scale(bands.mix) : undefined,
  }
}

export function averageXhRows(rows: XhRow[]): XhRow {
  const n = rows.length
  if (!n) return { xH: 1 }
  const mean = (xs: number[]) => xs.reduce((a, b) => a + b, 0) / xs.length
  const withBands = rows.filter((r) => r.bands)
  return {
    xH: mean(rows.map((r) => r.xH)),
    bands: withBands.length
      ? {
          worst: mean(withBands.map((r) => r.bands!.worst)),
          typical: mean(withBands.map((r) => r.bands!.typical)),
          best: mean(withBands.map((r) => r.bands!.best)),
          mix: withBands.every((r) => r.bands!.mix != null)
            ? mean(withBands.map((r) => r.bands!.mix!))
            : undefined,
        }
      : undefined,
  }
}

type VisionUnit = {
  id: string
  team: 'blue' | 'red'
  position: NonNullable<FighterLoadout['position']>
  alive?: boolean
}

type XhCast = {
  slot: AbilitySlot
  range: number
  ability: AbilityDefinition
}

/** Same filters as collectFighterDamage skillshot packet emission. */
export function skillshotCastsForFight(
  loadout: FighterLoadout,
  mode: TradeMode,
  lockedOut = false,
): XhCast[] {
  const champ = CHAMPIONS[loadout.championId]
  if (!champ) return []
  const ranks = ranksFromLoadout(loadout)
  const stats = buildStats(loadout)
  const hpPct = hpPctOf(loadout, stats)
  if (hpPct <= 0) return []
  const budget = abilityBudget(hpPct, mode, ranks.R > 0)
  const ctx = {
    mode,
    ranks,
    abilityRank: Math.max(ranks.Q, ranks.W, ranks.E, 1),
    hasEngagerAdvantage: false,
  }
  const out: XhCast[] = []
  const pushAbility = (ability: AbilityDefinition, castCopies: number) => {
    if (!ability.skillshot) return
    if (mode === 'short' && ability.slot === 'R') return
    if (!budget.allowed.has(ability.slot)) return
    if (ranks[ability.slot] <= 0) return
    if (lockedOut && ability.engageCc) return
    const hits = ability.damage(stats, stats, ctx).filter((p) => p.skillshot)
    if (!hits.length) return
    for (let c = 0; c < castCopies; c++) {
      for (let h = 0; h < hits.length; h++) {
        out.push({ slot: ability.slot, range: ability.range, ability })
      }
    }
  }
  if (lockedOut) {
    for (const ability of champ.abilities) {
      pushAbility(ability, 1)
    }
  } else {
    for (const ability of champ.abilities) {
      const casts = abilityCastsInFight(mode, ability.slot, stats.abilityHaste)
      pushAbility(ability, Math.max(1, casts))
    }
  }
  return out
}

function estimateXhRowVsEnemy(
  caster: FighterLoadout,
  enemy: FighterLoadout,
  abilityRange: number,
  targetDebuffs: ResolvedUtility,
  visionUnits: VisionUnit[],
  casterTeam: 'blue' | 'red',
  wards?: import('./vision').VisionWard[],
  ability?: AbilityDefinition,
): XhRow | null {
  const utilMult = xhUtilityMultiplier(targetDebuffs)
  const resolved =
    caster.position && enemy.position
      ? resolveCastVisionSoft({
          casterPosition: caster.position,
          targetPosition: enemy.position,
          casterTeam,
          targetTeam: casterTeam === 'blue' ? 'red' : 'blue',
          units: visionUnits,
          wards: wards ?? [],
        })
      : null
  const flash = flashReadyFromLoadout(enemy)
  const stats = buildStats(enemy)
  const liveMs = enemy.liveStats?.movespeed ?? stats.movespeed
  const msJuke = effectiveTargetMs(enemy, stats.movespeed, targetDebuffs)
  const hardCc =
    targetDebuffs.hardCc === true || enemy.crowdControlled === true
  const range = ability?.range ?? abilityRange
  const est = estimateXh({
    targetChampionId: enemy.championId,
    casterPosition: caster.position,
    targetPosition: enemy.position,
    abilityRange: range,
    missileWidth: ability?.missileWidth,
    missileSpeed: ability?.missileSpeed,
    releaseDelaySec: ability?.releaseDelaySec,
    missileMaxTravelUu: ability?.missileMaxTravelUu ?? ability?.range,
    skillshotLengthPenalty: range >= 900,
    vision: resolved?.vision ?? 'unknown',
    softVision: resolved?.softVision,
    softVisionMarginNorm: resolved?.softVisionMarginNorm,
    spottedByTarget: resolved?.spottedByTarget,
    dashReady: enemy.dashReady,
    dashChargesRemaining: enemy.dashChargesRemaining,
    flashReady: flash,
    flashCdRemainingSec: enemy.flashCdRemainingSec,
    targetMovespeed: msJuke,
    crowdControlled: hardCc,
    ccBreakReady: ccBreakReadyFromLoadout(enemy),
    ghostActive: ghostBuffActive(enemy, liveMs, stats.movespeed),
  })
  if (caster.position && enemy.position && !est.inRange) return null
  const scale = (p: number) => Math.min(0.97, p * utilMult)
  const packet =
    flash === undefined && est.bands?.mix != null ? est.bands.mix : est.xH
  return {
    xH: scale(packet),
    bands: est.bands ? scaleXhBands(est.bands, utilMult) : undefined,
  }
}

function meanXhRowVsEnemies(
  caster: FighterLoadout,
  enemies: FighterLoadout[],
  abilityRange: number,
  targetDebuffs: ResolvedUtility,
  visionUnits: VisionUnit[],
  casterTeam: 'blue' | 'red',
  wards?: import('./vision').VisionWard[],
  ability?: AbilityDefinition,
): XhRow {
  const living = enemies.filter(isAlive)
  if (!living.length) return { xH: 1 }
  const utilMult = xhUtilityMultiplier(targetDebuffs)
  const rows = living
    .map((enemy) =>
      estimateXhRowVsEnemy(
        caster,
        enemy,
        abilityRange,
        targetDebuffs,
        visionUnits,
        casterTeam,
        wards,
        ability,
      ),
    )
    .filter((r): r is XhRow => r != null)
  if (!rows.length) {
    if (caster.position && living.some((e) => e.position)) return { xH: 0 }
    const fallback = living[0]
    const flash = flashReadyFromLoadout(fallback)
    const stats = buildStats(fallback)
    const liveMs = fallback.liveStats?.movespeed ?? stats.movespeed
    const msJuke = effectiveTargetMs(fallback, stats.movespeed, targetDebuffs)
    const range = ability?.range ?? abilityRange
    const est = estimateXh({
      targetChampionId: fallback.championId,
      abilityRange: range,
      missileWidth: ability?.missileWidth,
      missileSpeed: ability?.missileSpeed,
      releaseDelaySec: ability?.releaseDelaySec,
      missileMaxTravelUu: ability?.missileMaxTravelUu ?? ability?.range,
      skillshotLengthPenalty: range >= 900,
      dashReady: fallback.dashReady,
      dashChargesRemaining: fallback.dashChargesRemaining,
      flashReady: flash,
      flashCdRemainingSec: fallback.flashCdRemainingSec,
      ccBreakReady: ccBreakReadyFromLoadout(fallback),
      targetMovespeed: msJuke,
      crowdControlled:
        targetDebuffs.hardCc === true || fallback.crowdControlled === true,
      ghostActive: ghostBuffActive(fallback, liveMs, stats.movespeed),
    })
    const packet =
      flash === undefined && est.bands?.mix != null ? est.bands.mix : est.xH
    return {
      xH: Math.min(0.97, packet * utilMult),
      bands: est.bands ? scaleXhBands(est.bands, utilMult) : undefined,
    }
  }
  return averageXhRows(rows)
}

/** Average dodge bands across living casters × budgeted skillshot cast multiset. */
export function fightDodgeBands(
  casters: FighterLoadout[],
  enemies: FighterLoadout[],
  outgoing: ResolvedUtility,
  visionUnits: VisionUnit[],
  casterTeam: 'blue' | 'red',
  wards?: import('./vision').VisionWard[],
  mode: TradeMode = 'extended',
  lockedOut = false,
): XhRow['bands'] {
  const livingC = casters.filter(isAlive)
  const livingE = enemies.filter(isAlive)
  if (!livingC.length || !livingE.length) return undefined
  const rows = livingC.flatMap((b) =>
    skillshotCastsForFight(b, mode, lockedOut).map((cast) => {
      const row = meanXhRowVsEnemies(
        b,
        livingE,
        cast.range,
        outgoing,
        visionUnits,
        casterTeam,
        wards,
        cast.ability,
      )
      // Keep OOR zeros in the average (do not drop band-less rows).
      if (!row.bands) {
        return {
          xH: row.xH,
          bands: { worst: row.xH, typical: row.xH, best: row.xH },
        }
      }
      return row
    }),
  )
  if (!rows.length) return undefined
  return averageXhRows(rows).bands
}

function meanXhVsEnemies(
  caster: FighterLoadout,
  enemies: FighterLoadout[],
  abilityRange: number,
  targetDebuffs: ResolvedUtility,
  visionUnits: VisionUnit[],
  casterTeam: 'blue' | 'red',
  wards?: import('./vision').VisionWard[],
  ability?: AbilityDefinition,
): number {
  return meanXhRowVsEnemies(
    caster,
    enemies,
    abilityRange,
    targetDebuffs,
    visionUnits,
    casterTeam,
    wards,
    ability,
  ).xH
}

function scalePacketsWithXh(
  packets: DamagePacket[],
  loadout: FighterLoadout,
  enemies: FighterLoadout[],
  champAbilities: AbilityDefinition[],
  mode: XhMode,
  targetDebuffs: ResolvedUtility,
  visionUnits: VisionUnit[],
  casterTeam: 'blue' | 'red',
  wards?: import('./vision').VisionWard[],
): DamagePacket[] {
  return packets.map((p) => {
    if (!p.skillshot) return { ...p, rawBeforeXh: p.raw }
    const ability = champAbilities.find((a) => a.slot === p.slot)
    const range = ability?.range ?? 600
    const xH = meanXhVsEnemies(
      loadout,
      enemies,
      range,
      targetDebuffs,
      visionUnits,
      casterTeam,
      wards,
      ability,
    )
    return applyXhModeToPacket({ ...p, rawBeforeXh: p.raw }, xH, mode)
  })
}

/**
 * Collect utility from every castable ability — including 0-damage slows/CC.
 * Never skip an ability just because damage() returns [].
 */
function collectSideUtility(
  loadouts: FighterLoadout[],
  mode: TradeMode,
  attackerStatsList: CombatStats[],
  defenderTeamStats: CombatStats,
  lockedOut: boolean,
): ResolvedUtility {
  let resolved = emptyResolvedUtility()
  const living = loadouts.filter(isAlive)
  living.forEach((loadout, index) => {
    const champ = CHAMPIONS[loadout.championId]
    if (!champ) return
    const ranks = ranksFromLoadout(loadout)
    const stats = attackerStatsList[index]
    const hpPct = hpPctOf(loadout, stats)
    if (hpPct <= 0) return
    const budget = abilityBudget(hpPct, mode, ranks.R > 0)
    const ctx = {
      mode,
      ranks,
      abilityRank: Math.max(ranks.Q, ranks.W, ranks.E, 1),
      hasEngagerAdvantage: false,
    }

    for (const ability of champ.abilities) {
      if (mode === 'short' && ability.slot === 'R') continue
      if (!budget.allowed.has(ability.slot)) continue
      if (ranks[ability.slot] <= 0) continue
      // Soft-locked side still applies reactive utility (slows), not engage CC
      if (lockedOut && ability.engageCc) continue

      const util = resolveUtility(ability, stats, defenderTeamStats, ctx)
      if (!util) continue
      // Even with zero damage packets, utility still applies
      resolved = mergeUtility(
        resolved,
        util,
        `${champ.name} ${ability.slot}`,
      )
    }
  })
  return resolved
}

function collectFighterDamage(
  loadout: FighterLoadout,
  mode: TradeMode,
  attackerStats: CombatStats,
  defenderTeamStats: CombatStats,
  lockedOut: boolean,
  fighterIndex: number,
  enemies: FighterLoadout[],
  xhMode: XhMode,
  /** Utility we apply onto the enemy (shred, amp, slows for xH) */
  outgoing: ResolvedUtility,
  /** Utility the enemy applied onto us (withers our autos) */
  incoming: ResolvedUtility,
  casterTeam: 'blue' | 'red',
  visionUnits: VisionUnit[],
  wards?: import('./vision').VisionWard[],
): { packets: DamagePacket[]; lockedOut: boolean; omittedSlots: AbilitySlot[]; budgetNote: string | null } {
  const champ = CHAMPIONS[loadout.championId]
  if (!champ) {
    return { packets: [], lockedOut, omittedSlots: [], budgetNote: null }
  }

  const ranks = ranksFromLoadout(loadout)
  const hpPct = hpPctOf(loadout, attackerStats)
  const budget = abilityBudget(hpPct, mode, ranks.R > 0)
  const packets: DamagePacket[] = []
  const ctx = {
    mode,
    ranks,
    abilityRank: Math.max(ranks.Q, ranks.W, ranks.E, 1),
    hasEngagerAdvantage: false,
  }

  const shreddedDefender = applyShredToStats(defenderTeamStats, outgoing)
  const dmgMult = damageDealtMultiplier(outgoing)

  const prefix = (list: DamagePacket[]) =>
    list.map((p) => ({
      ...p,
      raw: p.raw * dmgMult,
      fighterIndex,
      source: p.source.startsWith(`${champ.name}:`)
        ? p.source
        : `${champ.name}: ${p.source}`,
    }))

  if (hpPct <= 0) {
    return {
      packets: [],
      lockedOut,
      omittedSlots: budget.omitted,
      budgetNote: budget.note,
    }
  }

  if (!lockedOut) {
    for (const ability of champ.abilities) {
      if (mode === 'short' && ability.slot === 'R') continue
      if (!budget.allowed.has(ability.slot)) continue
      if (ranks[ability.slot] <= 0) continue
      // Cast even if damage is empty — utility already collected separately;
      // damage packets may still be [].
      const casts = abilityCastsInFight(
        mode,
        ability.slot,
        attackerStats.abilityHaste,
      )
      const base = prefix(ability.damage(attackerStats, shreddedDefender, ctx))
      for (let c = 0; c < casts; c++) {
        packets.push(
          ...base.map((p) => ({
            ...p,
            source: casts > 1 ? `${p.source} ×${c + 1}` : p.source,
          })),
        )
      }
    }

    if (champ.passiveDamage && budget.allowed.has('Q')) {
      packets.push(
        ...prefix(champ.passiveDamage(attackerStats, shreddedDefender, ctx)),
      )
    }

    if (budget.allowed.has('Q') || budget.allowed.has('E')) {
      for (const itemId of loadout.itemIds) {
        const item = ITEMS[itemId]
        if (!item) continue
        if (item.onAbilityMagic) {
          packets.push(
            ...prefix([
              {
                raw: item.onAbilityMagic,
                type: 'magical',
                source: `${item.name} proc`,
                slot: 'Q',
              },
            ]),
          )
        }
        if (item.onAbilityPhysical) {
          packets.push(
            ...prefix([
              {
                raw: item.onAbilityPhysical(attackerStats.ad),
                type: 'physical',
                source: `${item.name} proc`,
                slot: 'Q',
              },
            ]),
          )
        }
      }

      const rune = loadout.runeId ? resolveRuneId(loadout.runeId) : null
      if (rune?.tradeBonus) {
        packets.push(
          ...prefix(rune.tradeBonus(attackerStats, shreddedDefender, mode)),
        )
      }
      if (rune?.spellbook) {
        // Spellbook contributes notes via simulateMatchup; no damage packets.
      }
    }
  }

  const baseAutos = autosForDuration(
    mode,
    attackerStats.attackSpeed,
    champ.autoAttacksInTrade(mode),
  )
  let autos = lockedOut
    ? Math.min(1, autosForBudget(hpPct, mode, baseAutos))
    : autosForBudget(hpPct, mode, baseAutos)
  // Enemy slows / withers cut our AA count (Nasus W, Zilean E, …)
  autos = autosAfterUtility(autos, incoming)
  // Our own MS buff can claw one AA back in short trades
  if (outgoing.selfMsBuff >= 0.3 && autos < baseAutos) {
    autos = Math.min(baseAutos, autos + 1)
  }

  if (budget.allowed.has('AA')) {
    for (let i = 0; i < autos; i++) {
      packets.push(
        ...prefix([
          {
            raw: autoAttackDamage(attackerStats),
            type: 'physical',
            source: `Auto ${i + 1}${lockedOut ? ' (late)' : ''}`,
            slot: 'AA',
          },
        ]),
      )
    }
  }

  if (lockedOut) {
    for (const ability of champ.abilities) {
      if (mode === 'short' && ability.slot === 'R') continue
      if (ability.engageCc) continue
      if (!budget.allowed.has(ability.slot)) continue
      if (ranks[ability.slot] <= 0) continue
      const partial = ability
        .damage(attackerStats, shreddedDefender, ctx)
        .map((p) => ({
          ...p,
          raw: p.raw * 0.5,
          source: `${p.source} (react)`,
        }))
      packets.push(...prefix(partial))
    }
  }

  const withXh = scalePacketsWithXh(
    packets,
    loadout,
    enemies,
    champ.abilities,
    xhMode,
    outgoing, // enemy is debuffed by our slows → higher xH
    visionUnits,
    casterTeam,
    wards,
  )

  return {
    packets: withXh,
    lockedOut,
    omittedSlots: budget.omitted,
    budgetNote: budget.note,
  }
}

function sideHasEngage(loadouts: FighterLoadout[]): boolean {
  return loadouts.some((l) =>
    CHAMPIONS[l.championId]?.abilities.some((a) => a.engageCc),
  )
}

function avgPacketXh(packets: DamagePacket[]): number | undefined {
  const shots = packets.filter((p) => p.skillshot && p.xH != null)
  if (!shots.length) return undefined
  return shots.reduce((s, p) => s + (p.xH ?? 0), 0) / shots.length
}

function sideLocked(side: 'blue' | 'red', input: MatchupInput): boolean {
  if (input.mode !== 'short') return false
  if (input.engager === 'neither' || input.engager === side) return false
  const engagers = input[input.engager].filter(isAlive)
  return sideHasEngage(engagers)
}

function buildSide(
  side: 'blue' | 'red',
  loadouts: FighterLoadout[],
  enemyLoadouts: FighterLoadout[],
  input: MatchupInput,
  lockedOut: boolean,
  xhMode: XhMode,
  outgoing: ResolvedUtility,
  incoming: ResolvedUtility,
): SideResult {
  const living = loadouts.filter(isAlive)
  const livingEnemies = enemyLoadouts.filter(isAlive)
  const selfMods = modsForSide(side, input)
  const enemyMods = modsForSide(side === 'blue' ? 'red' : 'blue', input)
  const fighterStats = living.map((l) =>
    applyObjectiveModsToStats(buildStats(l), selfMods),
  )
  const enemyStats = livingEnemies.map((l) =>
    applyObjectiveModsToStats(buildStats(l), enemyMods),
  )
  const teamStats =
    fighterStats.length > 0
      ? averageStats(fighterStats)
      : {
          level: 1, hp: 0, hpMax: 0, armor: 0, mr: 0, ad: 0, ap: 0,
          attackSpeed: 0.6, critChance: 0, critDamage: 1.75, lethality: 0,
          armorPenPercent: 0, magicPenFlat: 0, magicPenPercent: 0,
          healShieldPower: 0, omnivamp: 0, abilityHaste: 0, range: 0,
          movespeed: 0, baseAd: 0, hpRegen: 0,
        }
  const enemyTeamStats =
    enemyStats.length > 0 ? averageStats(enemyStats) : teamStats

  const fighters: FighterResult[] = []
  const allPackets: DamagePacket[] = []
  const enemySide = side === 'blue' ? 'red' : 'blue'
  const visionUnits = [
    ...loadouts
      .filter((f) => f.position)
      .map((f, i) => ({
        id: `${side}-${i}`,
        team: side as 'blue' | 'red',
        position: f.position!,
        alive: isAlive(f),
      })),
    ...enemyLoadouts
      .filter((f) => f.position)
      .map((f, i) => ({
        id: `${enemySide}-${i}`,
        team: enemySide as 'blue' | 'red',
        position: f.position!,
        alive: isAlive(f),
      })),
  ]

  living.forEach((loadout, index) => {
    const collected = collectFighterDamage(
      loadout,
      input.mode,
      fighterStats[index],
      enemyTeamStats,
      lockedOut,
      index,
      livingEnemies,
      xhMode,
      outgoing,
      incoming,
      side,
      visionUnits,
      input.wards,
    )
    const packets = amplifyWithObjectives(
      collected.packets,
      selfMods,
      index,
    )
    const shreddedEnemy = applyShredToStats(enemyTeamStats, outgoing)
    const mitigated =
      sumMitigated(packets, fighterStats[index], shreddedEnemy) *
      objectiveDamageTakenMultiplier(enemyMods)
    fighters.push({
      index,
      championId: loadout.championId,
      championName: CHAMPIONS[loadout.championId]?.name ?? loadout.championId,
      stats: fighterStats[index],
      packets,
      rawTotal: sumRaw(packets),
      mitigatedTotal: mitigated,
      lockedOut,
      avgXh: avgPacketXh(packets),
      omittedSlots: collected.omittedSlots,
    })
    allPackets.push(...packets)
  })

  loadouts.filter((l) => !isAlive(l)).forEach((loadout, i) => {
    fighters.push({
      index: living.length + i,
      championId: loadout.championId,
      championName: CHAMPIONS[loadout.championId]?.name ?? loadout.championId,
      stats: buildStats({ ...loadout, alive: false, liveStats: { ...loadout.liveStats, hp: 0 } }),
      packets: [],
      rawTotal: 0,
      mitigatedTotal: 0,
      lockedOut: false,
      omittedSlots: ['Q', 'W', 'E', 'R', 'AA'],
      dead: true,
    })
  })

  let mitigatedTotal = 0
  for (const f of fighters) mitigatedTotal += f.mitigatedTotal

  return {
    side,
    label: teamLabel(living.length ? living : loadouts),
    fighters,
    stats: teamStats,
    packets: allPackets,
    rawTotal: sumRaw(allPackets),
    mitigatedTotal,
    hpRemaining: 0,
    hpRemainingPct: 0,
    damagePctOfEnemy: 0,
    kills: false,
    lockedOut,
    avgXh: avgPacketXh(allPackets),
    outgoingUtility: outgoing,
    incomingUtility: incoming,
  }
}

function finalizePair(
  blue: SideResult,
  red: SideResult,
  durationSec: number,
): { blue: SideResult; red: SideResult } {
  const blueRaw = blue.mitigatedTotal
  const redRaw = red.mitigatedTotal
  const blueDr = damageTakenMultiplier(blue.outgoingUtility ?? emptyResolvedUtility())
  const redDr = damageTakenMultiplier(red.outgoingUtility ?? emptyResolvedUtility())

  const blueDealt = blueRaw * redDr
  const redDealt = redRaw * blueDr

  const blueHeal = sustainHeal(blueDealt, blue.stats, durationSec)
  const redHeal = sustainHeal(redDealt, red.stats, durationSec)

  const bluePool = blue.stats.hp > 0 ? blue.stats.hp : blue.stats.hpMax
  const redPool = red.stats.hp > 0 ? red.stats.hp : red.stats.hpMax
  const blueCap = blue.stats.hpMax > 0 ? blue.stats.hpMax : bluePool
  const redCap = red.stats.hpMax > 0 ? red.stats.hpMax : redPool

  const blueHpLeft = Math.min(blueCap, Math.max(0, bluePool - redDealt + blueHeal))
  const redHpLeft = Math.min(redCap, Math.max(0, redPool - blueDealt + redHeal))

  return {
    blue: {
      ...blue,
      mitigatedTotal: blueDealt,
      hpRemaining: blueHpLeft,
      hpRemainingPct: bluePool > 0 ? blueHpLeft / bluePool : 0,
      damagePctOfEnemy: redPool > 0 ? blueDealt / redPool : 0,
      kills: blueDealt >= redPool && redPool > 0,
    },
    red: {
      ...red,
      mitigatedTotal: redDealt,
      hpRemaining: redHpLeft,
      hpRemainingPct: redPool > 0 ? redHpLeft / redPool : 0,
      damagePctOfEnemy: bluePool > 0 ? redDealt / bluePool : 0,
      kills: redDealt >= bluePool && bluePool > 0,
    },
  }
}

function pickHpWinner(blue: SideResult, red: SideResult): MatchupResult['winner'] {
  if (blue.kills && !red.kills) return 'blue'
  if (red.kills && !blue.kills) return 'red'
  if (blue.hpRemainingPct > red.hpRemainingPct + 0.005) return 'blue'
  if (red.hpRemainingPct > blue.hpRemainingPct + 0.005) return 'red'
  return 'draw'
}

function decideWinner(
  input: MatchupInput,
  blue: SideResult,
  red: SideResult,
): {
  winner: MatchupResult['winner']
  pBlue: number
  pRed: number
  tradeHpWinner: MatchupResult['winner']
  factors: string[]
} {
  const tradeHpWinner = pickHpWinner(blue, red)
  if (!input.objectives) {
    return {
      winner: tradeHpWinner,
      pBlue: tradeHpWinner === 'blue' ? 0.62 : tradeHpWinner === 'red' ? 0.38 : 0.5,
      pRed: tradeHpWinner === 'red' ? 0.62 : tradeHpWinner === 'blue' ? 0.38 : 0.5,
      tradeHpWinner,
      factors: ['no_scoreboard'],
    }
  }
  const odds = estimateFightOdds({
    blue: input.objectives.blue,
    red: input.objectives.red,
    blueLoadouts: input.blue,
    redLoadouts: input.red,
    blueCombat: blue,
    redCombat: red,
  })
  return {
    winner: odds.winner,
    pBlue: odds.pBlue,
    pRed: odds.pRed,
    tradeHpWinner,
    factors: odds.factors,
  }
}

function emptyTeamStats(): CombatStats {
  return {
    level: 1, hp: 0, hpMax: 0, armor: 0, mr: 0, ad: 0, ap: 0,
    attackSpeed: 0.6, critChance: 0, critDamage: 1.75, lethality: 0,
    armorPenPercent: 0, magicPenFlat: 0, magicPenPercent: 0,
    healShieldPower: 0, omnivamp: 0, abilityHaste: 0, range: 0,
    movespeed: 0, baseAd: 0, hpRegen: 0,
  }
}

function runOnce(input: MatchupInput, xhMode: XhMode) {
  const blueLocked = sideLocked('blue', input)
  const redLocked = sideLocked('red', input)

  const blueLiving = input.blue.filter(isAlive)
  const redLiving = input.red.filter(isAlive)
  const blueMods = modsForSide('blue', input)
  const redMods = modsForSide('red', input)
  const blueStats = blueLiving.map((l) =>
    applyObjectiveModsToStats(buildStats(l), blueMods),
  )
  const redStats = redLiving.map((l) =>
    applyObjectiveModsToStats(buildStats(l), redMods),
  )
  const blueTeam = blueStats.length > 0 ? averageStats(blueStats) : emptyTeamStats()
  const redTeam = redStats.length > 0 ? averageStats(redStats) : emptyTeamStats()

  const blueOutgoing = collectSideUtility(
    input.blue,
    input.mode,
    blueStats,
    redTeam,
    blueLocked,
  )
  const redOutgoing = collectSideUtility(
    input.red,
    input.mode,
    redStats,
    blueTeam,
    redLocked,
  )

  const blueBuilt = buildSide(
    'blue',
    input.blue,
    input.red,
    input,
    blueLocked,
    xhMode,
    blueOutgoing,
    redOutgoing,
  )
  const redBuilt = buildSide(
    'red',
    input.red,
    input.blue,
    input,
    redLocked,
    xhMode,
    redOutgoing,
    blueOutgoing,
  )
  const { blue, red } = finalizePair(blueBuilt, redBuilt, fightDurationSec(input.mode))
  const decided = decideWinner(input, blue, red)
  return {
    blue,
    red,
    winner: decided.winner,
    pBlue: decided.pBlue,
    pRed: decided.pRed,
    tradeHpWinner: decided.tradeHpWinner,
  }
}

export function simulateMatchup(input: MatchupInput): MatchupResult {
  if (!input.blue.length || !input.red.length) {
    throw new Error('Both sides need at least one fighter')
  }

  const xhMode: XhMode = input.xhMode ?? 'expected'
  const notes: string[] = []

  const blueDead = input.blue.length - input.blue.filter(isAlive).length
  const redDead = input.red.length - input.red.filter(isAlive).length

  if (blueDead || redDead) {
    notes.push(`Dead excluded: blue ${blueDead}, red ${redDead}.`)
  }

  if (sideLocked('blue', input)) notes.push('Red engages — blue reacts late.')
  if (sideLocked('red', input)) notes.push('Blue engages — red reacts late.')

  const primary = runOnce(input, xhMode)
  for (const f of [...primary.blue.fighters, ...primary.red.fighters]) {
    if (f.omittedSlots?.length && !f.dead) {
      notes.push(
        `${f.championName} omitted ${f.omittedSlots.join('/')} (HP budget).`,
      )
    }
  }

  const hitAll = runOnce(input, 'hit_all')
  const expected = runOnce(input, 'expected')
  const missShots = runOnce(input, 'miss_shots')
  const strengthBand: StrengthBand = {
    hitAll: {
      blueHpPct: hitAll.blue.hpRemainingPct,
      redHpPct: hitAll.red.hpRemainingPct,
      winner: hitAll.winner,
      pBlue: hitAll.pBlue,
    },
    expected: {
      blueHpPct: expected.blue.hpRemainingPct,
      redHpPct: expected.red.hpRemainingPct,
      winner: expected.winner,
      pBlue: expected.pBlue,
    },
    missShots: {
      blueHpPct: missShots.blue.hpRemainingPct,
      redHpPct: missShots.red.hpRemainingPct,
      winner: missShots.winner,
      pBlue: missShots.pBlue,
    },
  }

  if (
    primary.tradeHpWinner &&
    primary.tradeHpWinner !== primary.winner &&
    input.objectives
  ) {
    notes.push(
      `Leftover HP% leaned ${primary.tradeHpWinner}; fight odds favor ${primary.winner} from gold/objectives.`,
    )
  }

  return {
    blue: primary.blue,
    red: primary.red,
    winner: primary.winner,
    pBlue: primary.pBlue,
    pRed: primary.pRed,
    tradeHpWinner: primary.tradeHpWinner,
    notes: [...new Set(notes)].slice(0, 8),
    xhMode,
    strengthBand,
    xhDodgeBand: (() => {
      const visionUnits: VisionUnit[] = [
        ...input.blue
          .filter((f) => f.position)
          .map((f, i) => ({
            id: `blue-${i}`,
            team: 'blue' as const,
            position: f.position!,
            alive: isAlive(f),
          })),
        ...input.red
          .filter((f) => f.position)
          .map((f, i) => ({
            id: `red-${i}`,
            team: 'red' as const,
            position: f.position!,
            alive: isAlive(f),
          })),
      ]
      return fightDodgeBands(
        input.blue,
        input.red,
        primary.blue.outgoingUtility ?? emptyResolvedUtility(),
        visionUnits,
        'blue',
        input.wards,
        input.mode ?? 'extended',
        sideLocked('blue', input),
      )
    })(),
    xhPacketPolicy: (() => {
      const visionUnits: VisionUnit[] = [
        ...input.blue
          .filter((f) => f.position)
          .map((f, i) => ({
            id: `blue-${i}`,
            team: 'blue' as const,
            position: f.position!,
            alive: isAlive(f),
          })),
        ...input.red
          .filter((f) => f.position)
          .map((f, i) => ({
            id: `red-${i}`,
            team: 'red' as const,
            position: f.position!,
            alive: isAlive(f),
          })),
      ]
      const bands = fightDodgeBands(
        input.blue,
        input.red,
        primary.blue.outgoingUtility ?? emptyResolvedUtility(),
        visionUnits,
        'blue',
        input.wards,
        input.mode ?? 'extended',
        sideLocked('blue', input),
      )
      return bands?.mix != null &&
        Math.abs(bands.mix - bands.typical) > 1e-9
        ? ('mix' as const)
        : ('typical' as const)
    })(),
  }
}

export function defaultLoadout(championId: string): FighterLoadout {
  return {
    championId,
    level: 6,
    itemIds: [],
    runeId: null,
    ranks: { Q: 3, W: 1, E: 1, R: 1 },
    abilityRank: 3,
    alive: true,
    hpPct: 1,
  }
}

export function emptyMatchup(
  blueId = 'Gragas',
  redId = 'Darius',
): MatchupInput {
  return {
    blue: [defaultLoadout(blueId)],
    red: [defaultLoadout(redId)],
    engager: 'blue',
    mode: 'short',
    xhMode: 'expected',
  }
}

export type { TradeMode }
