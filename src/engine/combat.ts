import { CHAMPIONS, getChampion } from '../data/champions'
import { ITEMS } from '../data/items'
import { resolveRuneId } from '../data/runes'
import { mitigate, sumMitigated, sumRaw } from './damage'
import { abilityBudget, autosForBudget, estimateSurviveSec } from './hpBudget'
import {
  combatModsFromObjectives,
  emptyMods,
  formatObjectiveAssumptionLines,
  hasAuthoritativeCombatLiveStats,
  type ObjectiveCombatMods,
} from './objectives'
import { autoAttackDamage, buildStats, resolveFighterCombatStats, ranksFromLoadout } from './stats'
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
import { getItemPassive } from '../data/itemPassives'
import {
  abilityCastsInFight,
  autosForDuration,
  resolveFightDuration,
  sustainHeal,
} from './fightDuration'
import { estimateFightOdds } from './gameStateOdds'
import { classifyMatchupModelTrust } from './modelTrust'
import {
  planRotation,
  sortPlannedActions,
  type PlannedAction,
  type RotationActionCandidate,
} from './rotation'
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
  MatchupTimingResult,
  ResolvedUtility,
  SideResult,
  StrengthBand,
  TimedCombatEvent,
  TradeMode,
} from './types'

/** Locale-independent code-point order for serializable caveat lists. */
function compareCodePoint(a: string, b: string): number {
  return a < b ? -1 : a > b ? 1 : 0
}

function abilityAvailable(
  ability: AbilityDefinition,
  ctx: {
    mode: TradeMode
    ranks: ReturnType<typeof ranksFromLoadout>
    abilityRank: number
    hasEngagerAdvantage: boolean
    form?: FighterLoadout['form']
  },
): boolean {
  return !ability.available || ability.available(ctx)
}

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

/**
 * Defender-side incoming damage reduction from objectives.
 * Chemtech Soul DR is disclosed-only this batch (not always-on), so damageReduction
 * stays 0 unless a future timed threshold path sets it.
 */
function objectiveDamageTakenMultiplier(mods: ObjectiveCombatMods): number {
  return 1 - Math.min(0.5, mods.damageReduction)
}

/** Apply objective damageAmp only — no fabricated per-AA / Elder / soul packets. */
function amplifyWithObjectives(
  packets: DamagePacket[],
  mods: ObjectiveCombatMods,
  _fighterIndex: number,
): DamagePacket[] {
  const amp = 1 + mods.damageAmp
  if (amp === 1) return packets
  return packets.map((p) => ({
    ...p,
    raw: p.raw * amp,
    ...(p.rawBeforeXh != null ? { rawBeforeXh: p.rawBeforeXh * amp } : {}),
  }))
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
      attackSpeedRatio: acc.attackSpeedRatio + s.attackSpeedRatio,
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
      attackSpeedRatio: 0,
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
    attackSpeedRatio: sum.attackSpeedRatio / n,
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
    (l) => getChampion(l.championId)?.name ?? l.championId,
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

/**
 * Ghost strafe only with explicit buff or live MS bump — not spell-equipped alone.
 * Callers must supply a baseline that is NOT the same authoritative live MS pin
 * (see {@link ghostComparisonBaselineMs} / {@link ghostActiveForXh} for xH).
 */
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

/**
 * Objective-resolved MS with only the live movespeed pin removed (other live
 * pins kept). Used as the Ghost inference baseline so Cloud Soul theorycraft
 * speed is in the baseline, while an elevated live MS can still prove Ghost.
 */
export function ghostComparisonBaselineMs(
  enemy: FighterLoadout,
  enemyMods?: ObjectiveCombatMods | null,
): number {
  const live = enemy.liveStats
  let withoutLiveMs: FighterLoadout = enemy
  if (live && live.movespeed != null) {
    const { movespeed: _drop, ...rest } = live
    withoutLiveMs = {
      ...enemy,
      liveStats: Object.keys(rest).length > 0 ? rest : undefined,
    }
  }
  return resolveFighterCombatStats(withoutLiveMs, enemyMods ?? emptyMods())
    .movespeed
}

/**
 * Shared Ghost flag for positioned and fallback xH paths.
 * - explicit ghostActive true wins
 * - no authoritative live movespeed → never infer Ghost from theoretical/objective MS
 * - otherwise compare live MS to {@link ghostComparisonBaselineMs} (≥ 1.05×)
 */
export function ghostActiveForXh(
  enemy: FighterLoadout,
  enemyMods?: ObjectiveCombatMods | null,
): boolean {
  if (enemy.ghostActive === true) return true
  const hasGhost = (enemy.summonerSpells ?? []).some((s) => /ghost/i.test(s))
  if (!hasGhost) return false
  const liveMs = enemy.liveStats?.movespeed
  if (liveMs == null || !Number.isFinite(liveMs)) return false
  const baseline = ghostComparisonBaselineMs(enemy, enemyMods)
  return ghostBuffActive(enemy, liveMs, baseline)
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

/** Resolve target combat stats for xH juke MS (objective-aware; live MS absolute). */
function targetStatsForXh(
  enemy: FighterLoadout,
  enemyMods?: ObjectiveCombatMods | null,
): CombatStats {
  return resolveFighterCombatStats(enemy, enemyMods ?? emptyMods())
}

/** Resolve caster combat stats for cast budget / Hextech AH (optional mods). */
function casterStatsForXh(
  caster: FighterLoadout,
  casterMods?: ObjectiveCombatMods | null,
): CombatStats {
  return resolveFighterCombatStats(caster, casterMods ?? emptyMods())
}

/** Same filters as collectFighterDamage skillshot packet emission. */
export function skillshotCastsForFight(
  loadout: FighterLoadout,
  mode: TradeMode,
  lockedOut = false,
  /**
   * Optional pre-resolved caster stats (Hextech AH, etc.).
   * When omitted, falls back to buildStats(loadout) for backward compatibility.
   */
  casterStats?: CombatStats,
): XhCast[] {
  const champ = getChampion(loadout.championId)
  if (!champ) return []
  const ranks = ranksFromLoadout(loadout)
  const stats = casterStats ?? buildStats(loadout)
  const hpPct = hpPctOf(loadout, stats)
  if (hpPct <= 0) return []
  const durationSec = resolveFightDuration({ mode })
  const budget = abilityBudget(hpPct, mode, ranks.R > 0, {
    durationSec,
    ranks,
  })
  const ctx = {
    mode,
    ranks,
    abilityRank: Math.max(ranks.Q, ranks.W, ranks.E, 1),
    hasEngagerAdvantage: false,
    form: loadout.form,
  }
  const out: XhCast[] = []
  const pushAbility = (ability: AbilityDefinition, castCopies: number) => {
    if (!ability.skillshot) return
    if (!abilityAvailable(ability, ctx)) return
    if (mode === 'short' && ability.slot === 'R') return
    if (!budget.allowed.has(ability.slot)) return
    if (ranks[ability.slot] <= 0) return
    if (lockedOut && ability.engageCc) return
    const hits = ability.damage(stats, stats, ctx).filter((p) => p.skillshot)
    if (!hits.length) return
    for (let c = 0; c < castCopies; c++) {
      // xH dodge bands weight cast opportunities, not every damage line in a
      // multi-packet cast (Ahri Q out+return is one cast opportunity).
      out.push({ slot: ability.slot, range: ability.range, ability })
    }
  }
  if (lockedOut) {
    for (const ability of champ.abilities) {
      pushAbility(ability, 1)
    }
  } else {
    const castDur =
      budget.effectiveSec + 1e-9 < durationSec ? budget.effectiveSec : undefined
    for (const ability of champ.abilities) {
      const casts = abilityCastsInFight(
        mode,
        ability.slot,
        stats.abilityHaste,
        castDur,
        ability.cooldown,
      )
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
  enemyMods?: ObjectiveCombatMods | null,
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
  const stats = targetStatsForXh(enemy, enemyMods)
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
    ghostActive: ghostActiveForXh(enemy, enemyMods),
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
  enemyMods?: ObjectiveCombatMods | null,
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
        enemyMods,
      ),
    )
    .filter((r): r is XhRow => r != null)
  if (!rows.length) {
    if (caster.position && living.some((e) => e.position)) return { xH: 0 }
    const fallback = living[0]
    const flash = flashReadyFromLoadout(fallback)
    const stats = targetStatsForXh(fallback, enemyMods)
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
      ghostActive: ghostActiveForXh(fallback, enemyMods),
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
  /** Optional objective mods so Hextech AH and defender Cloud Soul MS reach xH. */
  objectiveMods?: {
    casterMods?: ObjectiveCombatMods | null
    enemyMods?: ObjectiveCombatMods | null
  },
): XhRow['bands'] {
  const livingC = casters.filter(isAlive)
  const livingE = enemies.filter(isAlive)
  if (!livingC.length || !livingE.length) return undefined
  const rows = livingC.flatMap((b) => {
    const casterResolved = casterStatsForXh(b, objectiveMods?.casterMods)
    return skillshotCastsForFight(b, mode, lockedOut, casterResolved).map(
      (cast) => {
        const row = meanXhRowVsEnemies(
          b,
          livingE,
          cast.range,
          outgoing,
          visionUnits,
          casterTeam,
          wards,
          cast.ability,
          objectiveMods?.enemyMods,
        )
        // Keep OOR zeros in the average (do not drop band-less rows).
        if (!row.bands) {
          return {
            xH: row.xH,
            bands: { worst: row.xH, typical: row.xH, best: row.xH },
          }
        }
        return row
      },
    )
  })
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
  enemyMods?: ObjectiveCombatMods | null,
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
    enemyMods,
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
  enemyMods?: ObjectiveCombatMods | null,
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
      enemyMods,
    )
    return applyXhModeToPacket({ ...p, rawBeforeXh: p.raw }, xH, mode)
  })
}

/** Collect utility from one fighter, including zero-damage slows/CC. */
function collectFighterUtility(
  loadout: FighterLoadout,
  mode: TradeMode,
  attackerStats: CombatStats,
  defenderStats: CombatStats,
  lockedOut: boolean,
): ResolvedUtility {
  const champ = getChampion(loadout.championId)
  if (!champ || hpPctOf(loadout, attackerStats) <= 0) {
    return emptyResolvedUtility()
  }
  const ranks = ranksFromLoadout(loadout)
  const hpPct = hpPctOf(loadout, attackerStats)
  const budget = abilityBudget(hpPct, mode, ranks.R > 0, {
    durationSec: resolveFightDuration({ mode }),
    ranks,
  })
  const ctx = {
    mode,
    ranks,
    abilityRank: Math.max(ranks.Q, ranks.W, ranks.E, 1),
    hasEngagerAdvantage: false,
    form: loadout.form,
  }
  let resolved = emptyResolvedUtility()
  for (const ability of champ.abilities) {
    if (mode === 'short' && ability.slot === 'R') continue
    if (!budget.allowed.has(ability.slot)) continue
    if (ranks[ability.slot] <= 0) continue
    if (!abilityAvailable(ability, ctx)) continue
    // Soft-locked side still applies reactive utility (slows), not engage CC.
    if (lockedOut && ability.engageCc) continue
    const util = resolveUtility(ability, attackerStats, defenderStats, ctx)
    if (util) {
      resolved = mergeUtility(resolved, util, `${champ.name} ${ability.slot}`)
    }
  }
  return resolved
}

/**
 * Collect utility from every living attacker against one concrete target.
 * Self-defence is projected away before it is applied to enemy packets.
 */
function collectSideUtility(
  loadouts: FighterLoadout[],
  mode: TradeMode,
  attackerStatsList: CombatStats[],
  defenderStats: CombatStats,
  lockedOut: boolean,
): ResolvedUtility {
  let resolved = emptyResolvedUtility()
  loadouts.filter(isAlive).forEach((loadout, index) => {
    const own = collectFighterUtility(
      loadout,
      mode,
      attackerStatsList[index],
      defenderStats,
      lockedOut,
    )
    resolved = mergeUtility(resolved, own, `${loadout.championId} utility`)
  })
  return resolved
}

function enemyFacingUtility(u: ResolvedUtility): ResolvedUtility {
  return { ...u, selfMsBuff: 0, damageReduction: 0 }
}

function selfFacingUtility(u: ResolvedUtility): ResolvedUtility {
  return {
    ...u,
    enemySlow: 0,
    enemyAsSlow: 0,
    hardCc: false,
    armorShred: 0,
    mrShred: 0,
    damageAmp: 0,
  }
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
  fightOpts?: { durationSec?: number; aaUptime?: number; surviveSec?: number | null },
  /** Target-side objective mods so Cloud Soul MS reaches xH packet scaling. */
  enemyMods?: ObjectiveCombatMods | null,
): {
  packets: DamagePacket[]
  lockedOut: boolean
  omittedSlots: AbilitySlot[]
  omissionNotes: string[]
  budgetNote: string | null
  /** Per-fighter item shred/amp merged for mitigation */
  itemUtility: ResolvedUtility
} {
  const champ = getChampion(loadout.championId)
  if (!champ) {
    return {
      packets: [],
      lockedOut,
      omittedSlots: [],
      omissionNotes: [],
      budgetNote: null,
      itemUtility: emptyResolvedUtility(),
    }
  }

  const durationSec = resolveFightDuration({
    mode,
    durationSec: fightOpts?.durationSec,
  })
  const ranks = ranksFromLoadout(loadout)
  const hpPct = hpPctOf(loadout, attackerStats)
  const budget = abilityBudget(hpPct, mode, ranks.R > 0, {
    durationSec,
    surviveSec: fightOpts?.surviveSec,
    ranks,
  })
  const castDurationSec =
    budget.effectiveSec + 1e-9 < durationSec
      ? budget.effectiveSec
      : fightOpts?.durationSec
  const packets: DamagePacket[] = []
  const ctx = {
    mode,
    ranks,
    abilityRank: Math.max(ranks.Q, ranks.W, ranks.E, 1),
    hasEngagerAdvantage: false,
    form: loadout.form,
  }

  // Count ability procs for spellblade / burn windows before building packets
  let abilityProcs = 0
  if (!lockedOut) {
    for (const ability of champ.abilities) {
      if (mode === 'short' && ability.slot === 'R') continue
      if (!budget.allowed.has(ability.slot)) continue
      if (ranks[ability.slot] <= 0) continue
      if (!abilityAvailable(ability, ctx)) continue
      abilityProcs += abilityCastsInFight(
        mode,
        ability.slot,
        attackerStats.abilityHaste,
        castDurationSec,
        ability.cooldown,
      )
    }
  }

  let fighterOutgoing = outgoing
  const passivePackets: DamagePacket[] = []
  for (const itemId of loadout.itemIds) {
    const passive = getItemPassive(itemId)
    if (!passive) continue
    const item = ITEMS[itemId]
    const label = item?.name ?? itemId
    const pctx = {
      attacker: attackerStats,
      defender: defenderTeamStats,
      durationSec,
      abilityProcs,
    }
    if (passive.armorShred) {
      const shred = passive.armorShred(pctx)
      if (shred > 0) {
        fighterOutgoing = mergeUtility(
          fighterOutgoing,
          { armorShred: shred },
          label,
        )
      }
    }
    if (passive.damageAmp) {
      const amp = passive.damageAmp(pctx)
      if (amp > 0) {
        fighterOutgoing = mergeUtility(
          fighterOutgoing,
          { damageAmp: amp },
          label,
        )
      }
    }
    if (passive.fightPackets && !lockedOut) {
      passivePackets.push(...passive.fightPackets(pctx))
    }
  }

  const shreddedDefender = applyShredToStats(defenderTeamStats, fighterOutgoing)
  const dmgMult = damageDealtMultiplier(fighterOutgoing)

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
      omissionNotes: budget.omissionNotes,
      budgetNote: budget.note,
      itemUtility: fighterOutgoing,
    }
  }

  if (!lockedOut) {
    for (const ability of champ.abilities) {
      if (mode === 'short' && ability.slot === 'R') continue
      if (!budget.allowed.has(ability.slot)) continue
      if (ranks[ability.slot] <= 0) continue
      if (!abilityAvailable(ability, ctx)) continue
      const casts = abilityCastsInFight(
        mode,
        ability.slot,
        attackerStats.abilityHaste,
        castDurationSec,
        ability.cooldown,
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
        // Prefer duration-aware passives; skip legacy flat procs when present
        if (getItemPassive(itemId)) continue
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
    }

    if (passivePackets.length) {
      packets.push(...prefix(passivePackets))
    }
  }

  const baseAutos = autosForDuration(
    mode,
    attackerStats.attackSpeed,
    champ.autoAttacksInTrade(mode),
    {
      // AS × effective surviving window (already survival-truncated). Do not
      // also scale again via autosForBudget effectiveSec/duration ratio.
      durationSec: castDurationSec ?? fightOpts?.durationSec,
      aaUptime: fightOpts?.aaUptime,
    },
  )
  let autos = lockedOut
    ? Math.min(1, autosForBudget(hpPct, mode, baseAutos))
    : autosForBudget(hpPct, mode, baseAutos)
  autos = autosAfterUtility(autos, incoming, {
    durationSec: fightOpts?.durationSec ?? durationSec,
  })
  if (fighterOutgoing.selfMsBuff >= 0.3 && autos < baseAutos) {
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
      if (!abilityAvailable(ability, ctx)) continue
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
    fighterOutgoing,
    visionUnits,
    casterTeam,
    wards,
    enemyMods,
  )

  const omissionNotes = [...budget.omissionNotes]
  if (lockedOut) {
    for (const ability of champ.abilities) {
      if (!ability.engageCc) continue
      if (ranks[ability.slot] <= 0) continue
      omissionNotes.push(
        `omitted ${ability.slot}: locked out (engage CC, short window)`,
      )
    }
  }

  return {
    packets: withXh,
    lockedOut,
    omittedSlots: budget.omitted,
    omissionNotes,
    budgetNote: budget.note,
    itemUtility: fighterOutgoing,
  }
}

/** Conservative defaults when AbilityDefinition.execution timing fields are absent. */
function executionDefaults(ability: AbilityDefinition): {
  castLockSec: number
  impactDelaySec: number
  attackReset: boolean
  empoweredAuto: boolean
  usedDefaultTiming: boolean
} {
  const hasCast = ability.execution?.castLockSec != null
  const hasImpact =
    ability.execution?.impactDelaySec != null || ability.releaseDelaySec != null
  return {
    castLockSec: ability.execution?.castLockSec ?? 0.15,
    impactDelaySec:
      ability.execution?.impactDelaySec ?? ability.releaseDelaySec ?? 0.1,
    attackReset: ability.execution?.attackReset ?? false,
    empoweredAuto: ability.execution?.empoweredAuto ?? false,
    usedDefaultTiming: !hasCast || !hasImpact,
  }
}

const AA_EXECUTION = {
  castLockSec: 0.05,
  impactDelaySec: 0.05,
  attackReset: false,
  empoweredAuto: false,
} as const

/** Living fighter has a kit the timed planner can schedule (CORE or Meraki). */
function hasResolvableKit(loadout: FighterLoadout): boolean {
  const champ = getChampion(loadout.championId)
  return !!champ && champ.abilities.length > 0
}

/**
 * Timed 1v1: exactly one living fighter per side with a resolvable kit
 * (CORE or Meraki/generated). Short-window engage still uses the timed path:
 * engager acts from t=0 (the engage skill/auto is on the clock); the locked
 * side starts after a reaction delay and cannot use engageCc. NvM / unresolved
 * kits stay on aggregate_window. modelTrust stays experimental for Meraki.
 */
function shouldUseTimedManual1v1(input: MatchupInput): boolean {
  const blueLiving = input.blue.filter(isAlive)
  const redLiving = input.red.filter(isAlive)
  if (blueLiving.length !== 1 || redLiving.length !== 1) return false
  if (!hasResolvableKit(blueLiving[0]!) || !hasResolvableKit(redLiving[0]!)) {
    return false
  }
  return true
}

/** Defender reaction delay after the engager opens (short-window engage only). */
const ENGAGE_REACTION_DELAY_SEC = 0.5

function aggregateTimingResult(
  durationSec: number,
  extraCaveats: string[] = [],
): MatchupTimingResult {
  const caveats = [
    'resolution:aggregate_window',
    'planner:not_applied',
    ...extraCaveats,
  ].sort(compareCodePoint)
  return {
    method: 'aggregate_window',
    requestedDurationSec: durationSec,
    executedDurationSec: durationSec,
    resolvedSec: durationSec,
    events: [],
    caveats,
  }
}

interface TimedHit {
  side: 'blue' | 'red'
  fighterIndex: number
  startSec: number
  impactSec: number
  slot: AbilitySlot
  source: string
  castIndex: number
  attackReset: boolean
  packets: DamagePacket[]
  /** Stable key for attaching supplemental procs. */
  actionId: string
}

function attachPacketsToHit(hit: TimedHit, extra: DamagePacket[]): void {
  hit.packets = hit.packets.concat(extra)
}

function collectFighterDamageTimed(
  loadout: FighterLoadout,
  mode: TradeMode,
  attackerStats: CombatStats,
  defenderTeamStats: CombatStats,
  fighterIndex: number,
  enemies: FighterLoadout[],
  xhMode: XhMode,
  outgoing: ResolvedUtility,
  incoming: ResolvedUtility,
  casterTeam: 'blue' | 'red',
  visionUnits: VisionUnit[],
  wards: import('./vision').VisionWard[] | undefined,
  fightOpts: { durationSec?: number; aaUptime?: number },
  startDelaySec: number,
  /** Target-side objective mods so Cloud Soul MS reaches timed xH scaling. */
  enemyMods?: ObjectiveCombatMods | null,
  /** Short-window engage lock: no engageCc; startDelay already applied by caller. */
  lockedOut = false,
): {
  packets: DamagePacket[]
  omittedSlots: AbilitySlot[]
  omissionNotes: string[]
  budgetNote: string | null
  itemUtility: ResolvedUtility
  hits: TimedHit[]
  caveats: string[]
  planActions: PlannedAction[]
} {
  const champ = getChampion(loadout.championId)
  const caveats: string[] = [
    'resolution:timed_manual_1v1',
    'planner:bounded_beam_best_found_not_global',
    'utility:whole_window_v1',
  ]
  if (lockedOut) {
    caveats.push(`engage:defender_reaction_delay:${ENGAGE_REACTION_DELAY_SEC}`)
  }
  if (!champ) {
    return {
      packets: [],
      omittedSlots: [],
      omissionNotes: [],
      budgetNote: null,
      itemUtility: emptyResolvedUtility(),
      hits: [],
      caveats: [...caveats, 'timing:no_champion'].sort(compareCodePoint),
      planActions: [],
    }
  }

  const durationSec = resolveFightDuration({
    mode,
    durationSec: fightOpts.durationSec,
  })
  const ranks = ranksFromLoadout(loadout)
  const hpPct = hpPctOf(loadout, attackerStats)
  // Timed path: full requested window for planning; first-lethal stops later hits.
  // Do not apply aggregate surviveSec cliffs here.
  const budget = abilityBudget(hpPct, mode, ranks.R > 0, {
    durationSec,
    ranks,
  })
  const omissionNotes = [...budget.omissionNotes]
  const ctx = {
    mode,
    ranks,
    abilityRank: Math.max(ranks.Q, ranks.W, ranks.E, 1),
    hasEngagerAdvantage: false,
    form: loadout.form,
  }

  // Shred/amp first (duration-based; abilityProcs not required for Cleaver/Liandry amp).
  let fighterOutgoing = outgoing
  for (const itemId of loadout.itemIds) {
    const passive = getItemPassive(itemId)
    if (!passive) continue
    const item = ITEMS[itemId]
    const label = item?.name ?? itemId
    const pctx = {
      attacker: attackerStats,
      defender: defenderTeamStats,
      durationSec,
      abilityProcs: 0,
    }
    if (passive.armorShred) {
      const shred = passive.armorShred(pctx)
      if (shred > 0) {
        fighterOutgoing = mergeUtility(
          fighterOutgoing,
          { armorShred: shred },
          label,
        )
      }
    }
    if (passive.damageAmp) {
      const amp = passive.damageAmp(pctx)
      if (amp > 0) {
        fighterOutgoing = mergeUtility(
          fighterOutgoing,
          { damageAmp: amp },
          label,
        )
      }
    }
  }

  const shreddedDefender = applyShredToStats(defenderTeamStats, fighterOutgoing)
  const dmgMult = damageDealtMultiplier(fighterOutgoing)

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
      omittedSlots: budget.omitted,
      omissionNotes,
      budgetNote: budget.note,
      itemUtility: fighterOutgoing,
      hits: [],
      caveats: [...caveats, 'timing:dead_at_start'].sort(compareCodePoint),
      planActions: [],
    }
  }

  const candidates: RotationActionCandidate[] = []
  const defaultSlots: string[] = []

  for (const ability of champ.abilities) {
    if (mode === 'short' && ability.slot === 'R') continue
    if (lockedOut && ability.engageCc) {
      if (ranks[ability.slot] > 0) {
        omissionNotes.push(
          `omitted ${ability.slot}: locked out (engage CC, short window)`,
        )
      }
      continue
    }
    if (!budget.allowed.has(ability.slot)) continue
    if (ranks[ability.slot] <= 0) continue
    if (!abilityAvailable(ability, ctx)) continue
    const basePackets = prefix(
      ability.damage(attackerStats, shreddedDefender, ctx),
    )
    // Planner score: xH-scaled (selected xhMode) then target-effective mitigated.
    // Returned/emitted packets still go through scalePacketsWithXh at emit time.
    const scoredPackets = scalePacketsWithXh(
      basePackets,
      loadout,
      enemies,
      champ.abilities,
      xhMode,
      fighterOutgoing,
      visionUnits,
      casterTeam,
      wards,
      enemyMods,
    )
    const expectedDamage = sumMitigated(
      scoredPackets,
      attackerStats,
      shreddedDefender,
    )
    if (expectedDamage <= 0 && !ability.execution?.attackReset) continue
    const ex = executionDefaults(ability)
    if (ex.usedDefaultTiming) defaultSlots.push(ability.slot)
    const maxCasts = abilityCastsInFight(
      mode,
      ability.slot,
      attackerStats.abilityHaste,
      fightOpts.durationSec,
      ability.cooldown,
    )
    candidates.push({
      id: `${ability.slot}:${ability.name}`,
      slot: ability.slot,
      expectedDamage: Math.max(expectedDamage, ex.attackReset ? 1e-6 : 0),
      cooldownSec: ability.cooldown,
      castLockSec: ex.castLockSec,
      impactDelaySec: ex.impactDelaySec,
      attackReset: ex.attackReset,
      empoweredAuto: ex.empoweredAuto,
      maxCasts,
    })
  }

  if (defaultSlots.length) {
    const sorted = [...new Set(defaultSlots)].sort(compareCodePoint)
    caveats.push(
      `timing:default_execution_metadata:${champ.id}:${sorted.join(',')}`,
    )
  }

  const baseAutos = autosForDuration(
    mode,
    attackerStats.attackSpeed,
    champ.autoAttacksInTrade(mode),
    {
      durationSec: fightOpts.durationSec,
      aaUptime: fightOpts.aaUptime,
    },
  )
  let autos = autosForBudget(hpPct, mode, baseAutos, {
    effectiveSec: budget.effectiveSec,
    durationSec,
  })
  autos = autosAfterUtility(autos, incoming, {
    durationSec: fightOpts.durationSec ?? durationSec,
  })
  if (fighterOutgoing.selfMsBuff >= 0.3 && autos < baseAutos) {
    autos = Math.min(baseAutos, autos + 1)
  }
  if (!budget.allowed.has('AA')) autos = 0

  const aaBase = prefix([
    {
      raw: autoAttackDamage(attackerStats),
      type: 'physical' as const,
      source: 'Auto',
      slot: 'AA' as const,
    },
  ])
  const aaScored = scalePacketsWithXh(
    aaBase,
    loadout,
    enemies,
    champ.abilities,
    xhMode,
    fighterOutgoing,
    visionUnits,
    casterTeam,
    wards,
    enemyMods,
  )
  const aaExpected = sumMitigated(aaScored, attackerStats, shreddedDefender)
  if (autos > 0 && aaExpected > 0) {
    candidates.push({
      id: 'AA',
      slot: 'AA',
      expectedDamage: aaExpected,
      cooldownSec: 0,
      castLockSec: AA_EXECUTION.castLockSec,
      impactDelaySec: AA_EXECUTION.impactDelaySec,
      attackReset: false,
      empoweredAuto: false,
      maxCasts: autos,
    })
  }

  const attackInterval = 1 / Math.max(0.4, attackerStats.attackSpeed)
  const plan = planRotation({
    candidates,
    attackIntervalSec: attackInterval,
    durationSec,
    aaCap: autos,
    startDelaySec,
    abilityHaste: attackerStats.abilityHaste,
  })

  // abilityProcs from the actual scheduled plan (non-AA abilities only).
  const abilityProcs = plan.actions.filter((a) => a.slot !== 'AA').length

  const itemFightPackets: DamagePacket[] = []
  for (const itemId of loadout.itemIds) {
    const passive = getItemPassive(itemId)
    if (!passive?.fightPackets) continue
    const pctx = {
      attacker: attackerStats,
      defender: defenderTeamStats,
      durationSec,
      abilityProcs,
    }
    itemFightPackets.push(...passive.fightPackets(pctx))
  }

  const hits: TimedHit[] = []
  const packets: DamagePacket[] = []

  for (const action of sortPlannedActions(plan.actions)) {
    if (action.slot === 'AA' && !action.empoweredAuto) {
      const aaPackets = prefix([
        {
          raw: autoAttackDamage(attackerStats),
          type: 'physical',
          source: `Auto ${action.castIndex}`,
          slot: 'AA',
        },
      ])
      const withXh = scalePacketsWithXh(
        aaPackets,
        loadout,
        enemies,
        champ.abilities,
        xhMode,
        fighterOutgoing,
        visionUnits,
        casterTeam,
        wards,
        enemyMods,
      )
      packets.push(...withXh)
      hits.push({
        side: casterTeam,
        fighterIndex,
        startSec: action.startSec,
        impactSec: action.impactSec,
        slot: 'AA',
        source: withXh[0]?.source ?? `${champ.name}: Auto ${action.castIndex}`,
        castIndex: action.castIndex,
        attackReset: false,
        packets: withXh,
        actionId: action.id,
      })
      continue
    }

    const ability = champ.abilities.find(
      (a) => a.slot === action.slot && `${a.slot}:${a.name}` === action.id,
    )
    if (!ability) continue
    const base = prefix(ability.damage(attackerStats, shreddedDefender, ctx))
    const labeled = base.map((p) => ({
      ...p,
      source:
        action.castIndex > 1 ? `${p.source} ×${action.castIndex}` : p.source,
    }))
    const withXh = scalePacketsWithXh(
      labeled,
      loadout,
      enemies,
      champ.abilities,
      xhMode,
      fighterOutgoing,
      visionUnits,
      casterTeam,
      wards,
    enemyMods,
    )
    packets.push(...withXh)
    hits.push({
      side: casterTeam,
      fighterIndex,
      startSec: action.startSec,
      impactSec: action.impactSec,
      slot: action.slot,
      source: withXh[0]?.source ?? `${champ.name}: ${ability.name}`,
      castIndex: action.castIndex,
      attackReset: action.attackReset,
      packets: withXh,
      actionId: action.id,
    })
  }

  const lastDamaging = hits.length ? hits[hits.length - 1] : undefined
  const firstNonAa = hits.find((h) => h.slot !== 'AA')

  // Aggregate champion passive → last scheduled damaging action (not t0/first AA).
  if (champ.passiveDamage && budget.allowed.has('Q') && lastDamaging) {
    const withXh = scalePacketsWithXh(
      prefix(champ.passiveDamage(attackerStats, shreddedDefender, ctx)),
      loadout,
      enemies,
      champ.abilities,
      xhMode,
      fighterOutgoing,
      visionUnits,
      casterTeam,
      wards,
    enemyMods,
    )
    packets.push(...withXh)
    attachPacketsToHit(lastDamaging, withXh)
    caveats.push('timing:supplemental_proc_approx')
  } else if (champ.passiveDamage && budget.allowed.has('Q') && !lastDamaging) {
    caveats.push('timing:supplemental_omitted_no_anchor')
  }

  // Duration-based item fightPackets (Spellblade/burn) → last damaging action.
  if (itemFightPackets.length && lastDamaging) {
    const withXh = scalePacketsWithXh(
      prefix(itemFightPackets),
      loadout,
      enemies,
      champ.abilities,
      xhMode,
      fighterOutgoing,
      visionUnits,
      casterTeam,
      wards,
    enemyMods,
    )
    packets.push(...withXh)
    attachPacketsToHit(lastDamaging, withXh)
    caveats.push('timing:supplemental_proc_approx')
  } else if (itemFightPackets.length && !lastDamaging) {
    caveats.push('timing:supplemental_omitted_no_anchor')
  }

  // Legacy on-ability / rune packets → first eligible non-AA ability (not first AA).
  const legacySupplemental: DamagePacket[] = []
  if (budget.allowed.has('Q') || budget.allowed.has('E')) {
    for (const itemId of loadout.itemIds) {
      if (getItemPassive(itemId)) continue
      const item = ITEMS[itemId]
      if (!item) continue
      if (item.onAbilityMagic) {
        legacySupplemental.push(
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
        legacySupplemental.push(
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
      legacySupplemental.push(
        ...prefix(rune.tradeBonus(attackerStats, shreddedDefender, mode)),
      )
    }
  }
  if (legacySupplemental.length) {
    const withXh = scalePacketsWithXh(
      legacySupplemental,
      loadout,
      enemies,
      champ.abilities,
      xhMode,
      fighterOutgoing,
      visionUnits,
      casterTeam,
      wards,
    enemyMods,
    )
    const anchor = firstNonAa ?? lastDamaging
    if (anchor) {
      packets.push(...withXh)
      attachPacketsToHit(anchor, withXh)
      caveats.push('timing:supplemental_proc_approx')
    } else {
      caveats.push('timing:supplemental_omitted_no_anchor')
    }
  }

  return {
    packets,
    omittedSlots: budget.omitted,
    omissionNotes,
    budgetNote: budget.note,
    itemUtility: fighterOutgoing,
    hits,
    caveats: [...new Set(caveats)].sort(compareCodePoint),
    planActions: plan.actions,
  }
}

function resolveTimedPair(
  blueBuilt: {
    side: SideResult
    hits: TimedHit[]
    stats: CombatStats
    itemUtility: ResolvedUtility
    caveats: string[]
  },
  redBuilt: {
    side: SideResult
    hits: TimedHit[]
    stats: CombatStats
    itemUtility: ResolvedUtility
    caveats: string[]
  },
  durationSec: number,
  enemyModsBlue: ObjectiveCombatMods,
  enemyModsRed: ObjectiveCombatMods,
): {
  blue: SideResult
  red: SideResult
  timing: MatchupTimingResult
} {
  const blueDr = damageTakenMultiplier(
    blueBuilt.side.defensiveUtilityByTarget?.[0] ?? emptyResolvedUtility(),
  )
  const redDr = damageTakenMultiplier(
    redBuilt.side.defensiveUtilityByTarget?.[0] ?? emptyResolvedUtility(),
  )
  const blueShredded = applyShredToStats(
    blueBuilt.stats,
    redBuilt.itemUtility,
  )
  const redShredded = applyShredToStats(
    redBuilt.stats,
    blueBuilt.itemUtility,
  )
  const objBlue = objectiveDamageTakenMultiplier(enemyModsBlue)
  const objRed = objectiveDamageTakenMultiplier(enemyModsRed)

  type Live = {
    hp: number
    hpMax: number
    hpStart: number
    dead: boolean
    deathSec: number | undefined
    incoming: number
    sustain: number
    dealtMitigated: number
  }

  const blueLive: Live = {
    hp: blueBuilt.stats.hp > 0 ? blueBuilt.stats.hp : blueBuilt.stats.hpMax,
    hpMax: blueBuilt.stats.hpMax,
    hpStart: blueBuilt.stats.hp > 0 ? blueBuilt.stats.hp : blueBuilt.stats.hpMax,
    dead: false,
    deathSec: undefined,
    incoming: 0,
    sustain: 0,
    dealtMitigated: 0,
  }
  const redLive: Live = {
    hp: redBuilt.stats.hp > 0 ? redBuilt.stats.hp : redBuilt.stats.hpMax,
    hpMax: redBuilt.stats.hpMax,
    hpStart: redBuilt.stats.hp > 0 ? redBuilt.stats.hp : redBuilt.stats.hpMax,
    dead: false,
    deathSec: undefined,
    incoming: 0,
    sustain: 0,
    dealtMitigated: 0,
  }

  const allHits = [...blueBuilt.hits, ...redBuilt.hits].sort((a, b) => {
    if (a.impactSec !== b.impactSec) return a.impactSec - b.impactSec
    if (a.startSec !== b.startSec) return a.startSec - b.startSec
    const bySide = compareCodePoint(a.side, b.side)
    if (bySide !== 0) return bySide
    return compareCodePoint(a.source, b.source)
  })

  const events: TimedCombatEvent[] = []
  let lastT = 0
  let firstLethalSec: number | undefined
  let cursor = 0

  const applyRegen = (live: Live, stats: CombatStats, dt: number) => {
    if (live.dead || dt <= 0) return
    const heal = Math.max(0, stats.hpRegen) * dt * 0.3
    if (heal <= 0) return
    live.hp = Math.min(live.hpMax, live.hp + heal)
    live.sustain += heal
  }

  while (cursor < allHits.length) {
    const t = allHits[cursor]!.impactSec
    if (t > durationSec + 1e-9) break

    const dt = Math.max(0, t - lastT)
    applyRegen(blueLive, blueBuilt.stats, dt)
    applyRegen(redLive, redBuilt.stats, dt)
    lastT = t

    const group: TimedHit[] = []
    while (
      cursor < allHits.length &&
      Math.abs(allHits[cursor]!.impactSec - t) <= 1e-9
    ) {
      group.push(allHits[cursor]!)
      cursor++
    }

    // Simultaneous damage: compute all mitigated hits from living casters,
    // then apply before declaring deaths.
    type Pending = {
      hit: TimedHit
      mitigated: number
      raw: number
      suppressed: boolean
    }
    const pending: Pending[] = group.map((hit) => {
      const casterDead = hit.side === 'blue' ? blueLive.dead : redLive.dead
      if (casterDead) {
        return { hit, mitigated: 0, raw: 0, suppressed: true }
      }
      const attackerStats =
        hit.side === 'blue' ? blueBuilt.stats : redBuilt.stats
      const defenderStats = hit.side === 'blue' ? redShredded : blueShredded
      const dr = hit.side === 'blue' ? redDr * objRed : blueDr * objBlue
      let mitigated = 0
      let raw = 0
      for (const p of hit.packets) {
        raw += p.raw
        mitigated += mitigate(p.raw, p.type, attackerStats, defenderStats) * dr
      }
      return { hit, mitigated, raw, suppressed: false }
    })

    let blueDamageThisTick = 0
    let redDamageThisTick = 0
    for (const p of pending) {
      if (p.suppressed) {
        events.push({
          side: p.hit.side,
          fighterIndex: p.hit.fighterIndex,
          slot: p.hit.slot,
          source: p.hit.source,
          castIndex: p.hit.castIndex,
          startSec: p.hit.startSec,
          impactSec: p.hit.impactSec,
          attackReset: p.hit.attackReset || undefined,
          raw: 0,
          suppressed: true,
        })
        continue
      }
      if (p.hit.side === 'blue') {
        redLive.incoming += p.mitigated
        redLive.hp -= p.mitigated
        blueDamageThisTick += p.mitigated
      } else {
        blueLive.incoming += p.mitigated
        blueLive.hp -= p.mitigated
        redDamageThisTick += p.mitigated
      }
      events.push({
        side: p.hit.side,
        fighterIndex: p.hit.fighterIndex,
        slot: p.hit.slot,
        source: p.hit.source,
        castIndex: p.hit.castIndex,
        startSec: p.hit.startSec,
        impactSec: p.hit.impactSec,
        attackReset: p.hit.attackReset || undefined,
        raw: p.raw,
      })
    }

    // Omnivamp from damage actually dealt this tick (dealer heal).
    if (!blueLive.dead && blueDamageThisTick > 0) {
      const vamp = Math.max(0, blueBuilt.stats.omnivamp) * blueDamageThisTick
      if (vamp > 0) {
        blueLive.hp = Math.min(blueLive.hpMax, blueLive.hp + vamp)
        blueLive.sustain += vamp
      }
      blueLive.dealtMitigated += blueDamageThisTick
    }
    if (!redLive.dead && redDamageThisTick > 0) {
      const vamp = Math.max(0, redBuilt.stats.omnivamp) * redDamageThisTick
      if (vamp > 0) {
        redLive.hp = Math.min(redLive.hpMax, redLive.hp + vamp)
        redLive.sustain += vamp
      }
      redLive.dealtMitigated += redDamageThisTick
    }

    // Deaths after simultaneous application — no resurrection.
    if (!blueLive.dead && blueLive.hp <= 0 && blueLive.hpStart > 0) {
      blueLive.hp = 0
      blueLive.dead = true
      blueLive.deathSec = t
      if (firstLethalSec == null) firstLethalSec = t
    }
    if (!redLive.dead && redLive.hp <= 0 && redLive.hpStart > 0) {
      redLive.hp = 0
      redLive.dead = true
      redLive.deathSec = t
      if (firstLethalSec == null) firstLethalSec = t
    }

    // Stop damage at first lethal; still record later planned hits as suppressed
    // so UI notes can cite "caster dead" / audit the cut rotation.
    if (blueLive.dead || redLive.dead) {
      while (cursor < allHits.length) {
        const hit = allHits[cursor]!
        cursor++
        if (hit.impactSec > durationSec + 1e-9) break
        events.push({
          side: hit.side,
          fighterIndex: hit.fighterIndex,
          slot: hit.slot,
          source: hit.source,
          castIndex: hit.castIndex,
          startSec: hit.startSec,
          impactSec: hit.impactSec,
          attackReset: hit.attackReset || undefined,
          raw: 0,
          suppressed: true,
        })
      }
      break
    }
  }

  // Fight ends at first lethal (or full window if nobody dies). No trailing
  // regen past the resolved stop — end-of-window sustain must not continue.
  if (blueLive.dead) blueLive.hp = 0
  if (redLive.dead) redLive.hp = 0

  const executedEvents = events.filter((e) => !e.suppressed)
  const bluePackets = executedEvents
    .filter((e) => e.side === 'blue')
    .flatMap((e) => {
      const hit = blueBuilt.hits.find(
        (h) =>
          h.impactSec === e.impactSec &&
          h.source === e.source &&
          h.castIndex === e.castIndex,
      )
      return hit?.packets ?? []
    })
  const redPackets = executedEvents
    .filter((e) => e.side === 'red')
    .flatMap((e) => {
      const hit = redBuilt.hits.find(
        (h) =>
          h.impactSec === e.impactSec &&
          h.source === e.source &&
          h.castIndex === e.castIndex,
      )
      return hit?.packets ?? []
    })

  const blueMitigated = blueLive.dealtMitigated
  const redMitigated = redLive.dealtMitigated

  const blueTarget = {
    index: 0,
    championId: blueBuilt.side.fighters[0]?.championId ?? '',
    championName: blueBuilt.side.fighters[0]?.championName ?? '',
    hpStart: blueLive.hpStart,
    hpMax: blueLive.hpMax > 0 ? blueLive.hpMax : blueLive.hpStart,
    incomingDamage: blueLive.incoming,
    sustainHeal: blueLive.sustain,
    damageReduction: 1 - blueDr,
    hpRemaining: Math.max(0, blueLive.hp),
    killed: blueLive.dead,
  }
  const redTarget = {
    index: 0,
    championId: redBuilt.side.fighters[0]?.championId ?? '',
    championName: redBuilt.side.fighters[0]?.championName ?? '',
    hpStart: redLive.hpStart,
    hpMax: redLive.hpMax > 0 ? redLive.hpMax : redLive.hpStart,
    incomingDamage: redLive.incoming,
    sustainHeal: redLive.sustain,
    damageReduction: 1 - redDr,
    hpRemaining: Math.max(0, redLive.hp),
    killed: redLive.dead,
  }

  const blue: SideResult = {
    ...blueBuilt.side,
    packets: bluePackets,
    rawTotal: sumRaw(bluePackets),
    mitigatedTotal: blueMitigated,
    fighters: blueBuilt.side.fighters.map((f, i) =>
      i === 0
        ? {
            ...f,
            packets: bluePackets,
            rawTotal: sumRaw(bluePackets),
            mitigatedTotal: blueMitigated,
          }
        : f,
    ),
    hpRemaining: blueTarget.hpRemaining,
    hpRemainingPct:
      blueTarget.hpMax > 0 ? blueTarget.hpRemaining / blueTarget.hpMax : 0,
    damagePctOfEnemy:
      redTarget.hpStart > 0 ? blueMitigated / redTarget.hpStart : 0,
    kills: redTarget.killed,
    targets: [blueTarget],
    avgXh: avgPacketXh(bluePackets),
  }
  const red: SideResult = {
    ...redBuilt.side,
    packets: redPackets,
    rawTotal: sumRaw(redPackets),
    mitigatedTotal: redMitigated,
    fighters: redBuilt.side.fighters.map((f, i) =>
      i === 0
        ? {
            ...f,
            packets: redPackets,
            rawTotal: sumRaw(redPackets),
            mitigatedTotal: redMitigated,
          }
        : f,
    ),
    hpRemaining: redTarget.hpRemaining,
    hpRemainingPct:
      redTarget.hpMax > 0 ? redTarget.hpRemaining / redTarget.hpMax : 0,
    damagePctOfEnemy:
      blueTarget.hpStart > 0 ? redMitigated / blueTarget.hpStart : 0,
    kills: blueTarget.killed,
    targets: [redTarget],
    avgXh: avgPacketXh(redPackets),
  }

  // resolved/executed = first lethal; requested duration only when nobody dies.
  const stopSec = firstLethalSec ?? durationSec

  const caveats = [
    ...blueBuilt.caveats,
    ...redBuilt.caveats,
    'sustain:elapsed_regen_and_dealt_omnivamp_only',
    'kill:no_end_window_sustain_resurrect',
    'kill:stop_at_first_lethal_timestamp',
  ]
  const timing: MatchupTimingResult = {
    method: 'timed_manual_1v1',
    requestedDurationSec: durationSec,
    executedDurationSec: stopSec,
    resolvedSec: stopSec,
    firstLethalSec,
    blueDeathSec: blueLive.deathSec,
    redDeathSec: redLive.deathSec,
    events: events
      .slice()
      .sort((a, b) => {
        if (a.impactSec !== b.impactSec) return a.impactSec - b.impactSec
        if (a.startSec !== b.startSec) return a.startSec - b.startSec
        const bySide = compareCodePoint(a.side, b.side)
        if (bySide !== 0) return bySide
        return compareCodePoint(a.source, b.source)
      }),
    caveats: [...new Set(caveats)].sort(compareCodePoint),
  }

  return { blue, red, timing }
}

function sideHasEngage(loadouts: FighterLoadout[]): boolean {
  return loadouts.some((l) =>
    getChampion(l.championId)?.abilities.some((a) => a.engageCc),
  )
}

function avgPacketXh(packets: DamagePacket[]): number | undefined {
  const shots = packets.filter((p) => p.skillshot && p.xH != null)
  if (!shots.length) return undefined
  return shots.reduce((s, p) => s + (p.xH ?? 0), 0) / shots.length
}

function sideLocked(side: 'blue' | 'red', input: MatchupInput): boolean {
  if (input.mode !== 'short' || resolveFightDuration(input) > 4) return false
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
  const fighterStats = living.map((l) => resolveFighterCombatStats(l, selfMods))
  const enemyStats = livingEnemies.map((l) =>
    resolveFighterCombatStats(l, enemyMods),
  )
  const teamStats =
    fighterStats.length > 0
      ? averageStats(fighterStats)
      : {
          level: 1, hp: 0, hpMax: 0, armor: 0, mr: 0, ad: 0, ap: 0,
          attackSpeed: 0.6, attackSpeedRatio: 0.625, critChance: 0, critDamage: 1.75, lethality: 0,
          armorPenPercent: 0, magicPenFlat: 0, magicPenPercent: 0,
          healShieldPower: 0, omnivamp: 0, abilityHaste: 0, range: 0,
          movespeed: 0, baseAd: 0, hpRegen: 0,
        }
  const focusTargetIndex = livingEnemies.length > 0 ? 0 : undefined
  const focusTargetStats =
    focusTargetIndex != null ? enemyStats[focusTargetIndex] : teamStats
  const enemyFacing = enemyFacingUtility(outgoing)

  const fighters: FighterResult[] = []
  const allPackets: DamagePacket[] = []
  const defensiveUtilityByTarget: ResolvedUtility[] = []
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
    const ownUtility = collectFighterUtility(
      loadout,
      input.mode,
      fighterStats[index],
      focusTargetStats,
      lockedOut,
    )
    const fighterOutgoing = mergeUtility(
      enemyFacing,
      selfFacingUtility(ownUtility),
      `${loadout.championId} self utility`,
    )
    // The opponent's single-target utility follows the same first-living
    // focus policy; it does not slow or CC every member of an NvM roster.
    const fighterIncoming =
      index === 0 ? enemyFacingUtility(incoming) : emptyResolvedUtility()
    const durationSec = resolveFightDuration(input)
    const self = fighterStats[index]!
    const surviveSec = estimateSurviveSec({
      hp: self.hp > 0 ? self.hp : self.hpMax * Math.max(0, hpPctOf(loadout, self)),
      armor: self.armor,
      mr: self.mr,
      enemies: enemyStats,
      durationSec,
    })
    const collected = collectFighterDamage(
      loadout,
      input.mode,
      fighterStats[index],
      focusTargetStats,
      lockedOut,
      index,
      livingEnemies,
      xhMode,
      fighterOutgoing,
      fighterIncoming,
      side,
      visionUnits,
      input.wards,
      {
        durationSec: input.durationSec,
        aaUptime: input.aaUptime,
        surviveSec,
      },
      enemyMods,
    )
    const packets = amplifyWithObjectives(
      collected.packets,
      selfMods,
      index,
    )
    const shreddedEnemy = applyShredToStats(
      focusTargetStats,
      collected.itemUtility,
    )
    const mitigated =
      sumMitigated(packets, fighterStats[index], shreddedEnemy) *
      objectiveDamageTakenMultiplier(enemyMods)
    defensiveUtilityByTarget.push(selfFacingUtility(ownUtility))
    fighters.push({
      index,
      championId: loadout.championId,
      championName: getChampion(loadout.championId)?.name ?? loadout.championId,
      stats: fighterStats[index],
      packets,
      rawTotal: sumRaw(packets),
      mitigatedTotal: mitigated,
      lockedOut,
      avgXh: avgPacketXh(packets),
      omittedSlots: collected.omittedSlots,
      omissionNotes: collected.omissionNotes,
      budgetNote: collected.budgetNote,
      targetIndex: focusTargetIndex,
    })
    allPackets.push(...packets)
  })

  loadouts.filter((l) => !isAlive(l)).forEach((loadout, i) => {
    fighters.push({
      index: living.length + i,
      championId: loadout.championId,
      championName: getChampion(loadout.championId)?.name ?? loadout.championId,
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

  const targets = living.map((loadout, index) => {
    const stats = fighterStats[index]
    const hpStart = stats.hp > 0 ? stats.hp : stats.hpMax
    return {
      index,
      championId: loadout.championId,
      championName: getChampion(loadout.championId)?.name ?? loadout.championId,
      hpStart,
      hpMax: stats.hpMax > 0 ? stats.hpMax : hpStart,
      incomingDamage: 0,
      sustainHeal: sustainHeal(fighters[index]?.mitigatedTotal ?? 0, stats, resolveFightDuration(input)),
      damageReduction: 0,
      hpRemaining: hpStart,
      killed: false,
    }
  })

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
    targets,
    focusTargetIndex,
    defensiveUtilityByTarget,
  }
}

function finalizePair(
  blue: SideResult,
  red: SideResult,
): { blue: SideResult; red: SideResult } {
  const blueTargetUtility =
    blue.defensiveUtilityByTarget?.[red.focusTargetIndex ?? 0] ??
    emptyResolvedUtility()
  const redTargetUtility =
    red.defensiveUtilityByTarget?.[blue.focusTargetIndex ?? 0] ??
    emptyResolvedUtility()
  const blueDr = damageTakenMultiplier(blueTargetUtility)
  const redDr = damageTakenMultiplier(redTargetUtility)

  const resolveSide = (
    side: SideResult,
    opposing: SideResult,
    ownDefenderDr: number,
  ): SideResult => {
    const targetList = (side.targets ?? []).map((target) => ({ ...target }))
    for (const target of targetList) {
      target.hpRemaining = Math.min(
        target.hpMax,
        Math.max(0, target.hpStart + target.sustainHeal),
      )
    }
    const opposingFocus = opposing.focusTargetIndex
    const incoming =
      opposingFocus == null ? 0 : opposing.mitigatedTotal * ownDefenderDr
    if (opposingFocus != null && targetList[opposingFocus]) {
      const target = targetList[opposingFocus]
      target.incomingDamage = incoming
      target.damageReduction = 1 - ownDefenderDr
      target.hpRemaining = Math.min(
        target.hpMax,
        Math.max(0, target.hpStart - incoming + target.sustainHeal),
      )
      // Kill state is intentionally post-sustain, not pre-heal dealt >= HP.
      target.killed = target.hpRemaining <= 0 && target.hpStart > 0
    }
    const hpMaxPool = targetList.reduce((sum, target) => sum + target.hpMax, 0)
    const hpRemaining = targetList.reduce(
      (sum, target) => sum + target.hpRemaining,
      0,
    )
    return {
      ...side,
      hpRemaining,
      hpRemainingPct: hpMaxPool > 0 ? hpRemaining / hpMaxPool : 0,
      targets: targetList,
    }
  }

  // Health outcomes are own-side state; outgoing damage belongs to the
  // opposite side's focused target and is reduced by that target's DR.
  const blueHealth = resolveSide(blue, red, blueDr)
  const redHealth = resolveSide(red, blue, redDr)
  const blueEffectiveDamage = blue.mitigatedTotal * redDr
  const redEffectiveDamage = red.mitigatedTotal * blueDr
  const blueFocusedEnemy = redHealth.targets?.[blue.focusTargetIndex ?? 0]
  const redFocusedEnemy = blueHealth.targets?.[red.focusTargetIndex ?? 0]

  return {
    blue: {
      ...blueHealth,
      fighters: blue.fighters.map((fighter) => ({
        ...fighter,
        mitigatedTotal: fighter.mitigatedTotal * redDr,
      })),
      mitigatedTotal: blueEffectiveDamage,
      damagePctOfEnemy:
        blueFocusedEnemy && blueFocusedEnemy.hpStart > 0
          ? blueEffectiveDamage / blueFocusedEnemy.hpStart
          : 0,
      kills: !!redHealth.targets?.some((target) => target.killed),
    },
    red: {
      ...redHealth,
      fighters: red.fighters.map((fighter) => ({
        ...fighter,
        mitigatedTotal: fighter.mitigatedTotal * blueDr,
      })),
      mitigatedTotal: redEffectiveDamage,
      damagePctOfEnemy:
        redFocusedEnemy && redFocusedEnemy.hpStart > 0
          ? redEffectiveDamage / redFocusedEnemy.hpStart
          : 0,
      kills: !!blueHealth.targets?.some((target) => target.killed),
    },
  }
}

function pickHpWinner(blue: SideResult, red: SideResult): MatchupResult['winner'] {
  if (blue.kills && !red.kills) return 'blue'
  if (red.kills && !blue.kills) return 'red'

  // Long windows often lethal both ways. 0%/0% leftover is not "even" —
  // rank by overkill (damage / enemy pool): who would finish first.
  if (blue.kills && red.kills) {
    const blueOver = blue.damagePctOfEnemy
    const redOver = red.damagePctOfEnemy
    if (blueOver > redOver + 0.02) return 'blue'
    if (redOver > blueOver + 0.02) return 'red'
    // Near-tie overkill → fall through to raw leftover (both ~0) then draw
  }

  if (blue.hpRemainingPct > red.hpRemainingPct + 0.005) return 'blue'
  if (red.hpRemainingPct > blue.hpRemainingPct + 0.005) return 'red'
  return 'draw'
}

/** Map leftover-HP / overkill margin → P(blue) when no scoreboard is present. */
function oddsFromTradeHp(blue: SideResult, red: SideResult): number {
  let edge: number
  let steep = 4.2
  if (blue.kills && red.kills) {
    edge = blue.damagePctOfEnemy - red.damagePctOfEnemy
    steep = 5
  } else if (blue.kills && !red.kills) {
    edge = 1.15 + Math.min(0.9, Math.max(0, blue.damagePctOfEnemy - 1))
    steep = 5
  } else if (red.kills && !blue.kills) {
    edge = -(1.15 + Math.min(0.9, Math.max(0, red.damagePctOfEnemy - 1)))
    steep = 5
  } else {
    edge = blue.hpRemainingPct - red.hpRemainingPct
  }
  const p = 1 / (1 + Math.exp(-edge * steep))
  const lo = blue.kills || red.kills ? 0.06 : 0.12
  return Math.max(lo, Math.min(1 - lo, p))
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
    const pBlue = oddsFromTradeHp(blue, red)
    return {
      winner: tradeHpWinner,
      pBlue,
      pRed: 1 - pBlue,
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
    attackSpeed: 0.6, attackSpeedRatio: 0.625, critChance: 0, critDamage: 1.75, lethality: 0,
    armorPenPercent: 0, magicPenFlat: 0, magicPenPercent: 0,
    healShieldPower: 0, omnivamp: 0, abilityHaste: 0, range: 0,
    movespeed: 0, baseAd: 0, hpRegen: 0,
  }
}

function runOnce(input: MatchupInput, xhMode: XhMode) {
  const durationSec = resolveFightDuration(input)
  if (shouldUseTimedManual1v1(input)) {
    return runOnceTimed(input, xhMode, durationSec)
  }

  const blueLocked = sideLocked('blue', input)
  const redLocked = sideLocked('red', input)

  const blueLiving = input.blue.filter(isAlive)
  const redLiving = input.red.filter(isAlive)
  const blueMods = modsForSide('blue', input)
  const redMods = modsForSide('red', input)
  const blueStats = blueLiving.map((l) => resolveFighterCombatStats(l, blueMods))
  const redStats = redLiving.map((l) => resolveFighterCombatStats(l, redMods))
  const blueTeam = blueStats.length > 0 ? averageStats(blueStats) : emptyTeamStats()
  const redTeam = redStats.length > 0 ? averageStats(redStats) : emptyTeamStats()
  const blueFocus = blueStats[0] ?? blueTeam
  const redFocus = redStats[0] ?? redTeam

  const blueOutgoing = enemyFacingUtility(collectSideUtility(
    input.blue,
    input.mode,
    blueStats,
    redFocus,
    blueLocked,
  ))
  const redOutgoing = enemyFacingUtility(collectSideUtility(
    input.red,
    input.mode,
    redStats,
    blueFocus,
    redLocked,
  ))

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
  const { blue, red } = finalizePair(blueBuilt, redBuilt)
  const decided = decideWinner(input, blue, red)
  const timingExtra: string[] = []
  if (blueLiving.length !== 1 || redLiving.length !== 1) {
    timingExtra.push('fallback:nvm_roster')
  } else if (
    !hasResolvableKit(blueLiving[0]!) ||
    !hasResolvableKit(redLiving[0]!)
  ) {
    timingExtra.push('fallback:unresolvable_kit')
  }
  return {
    blue,
    red,
    winner: decided.winner,
    pBlue: decided.pBlue,
    pRed: decided.pRed,
    tradeHpWinner: decided.tradeHpWinner,
    timing: aggregateTimingResult(durationSec, timingExtra),
  }
}

function runOnceTimed(
  input: MatchupInput,
  xhMode: XhMode,
  durationSec: number,
) {
  const blueLocked = sideLocked('blue', input)
  const redLocked = sideLocked('red', input)
  const blueMods = modsForSide('blue', input)
  const redMods = modsForSide('red', input)
  const blueLoadout = input.blue.find(isAlive)!
  const redLoadout = input.red.find(isAlive)!
  const blueStats = resolveFighterCombatStats(blueLoadout, blueMods)
  const redStats = resolveFighterCombatStats(redLoadout, redMods)

  const blueOutgoing = enemyFacingUtility(
    collectSideUtility(
      input.blue,
      input.mode,
      [blueStats],
      redStats,
      blueLocked,
    ),
  )
  const redOutgoing = enemyFacingUtility(
    collectSideUtility(
      input.red,
      input.mode,
      [redStats],
      blueStats,
      redLocked,
    ),
  )

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

  const blueOwn = collectFighterUtility(
    blueLoadout,
    input.mode,
    blueStats,
    redStats,
    blueLocked,
  )
  const redOwn = collectFighterUtility(
    redLoadout,
    input.mode,
    redStats,
    blueStats,
    redLocked,
  )
  const blueFighterOutgoing = mergeUtility(
    enemyFacingUtility(blueOutgoing),
    selfFacingUtility(blueOwn),
    `${blueLoadout.championId} self utility`,
  )
  const redFighterOutgoing = mergeUtility(
    enemyFacingUtility(redOutgoing),
    selfFacingUtility(redOwn),
    `${redLoadout.championId} self utility`,
  )

  // Engager opens at t=0 (engage skill/auto is a real timed action). Locked
  // defender waits ENGAGE_REACTION_DELAY_SEC and cannot use engageCc.
  const blueTimed = collectFighterDamageTimed(
    blueLoadout,
    input.mode,
    blueStats,
    redStats,
    0,
    [redLoadout],
    xhMode,
    blueFighterOutgoing,
    enemyFacingUtility(redOutgoing),
    'blue',
    visionUnits,
    input.wards,
    { durationSec: input.durationSec, aaUptime: input.aaUptime },
    blueLocked ? ENGAGE_REACTION_DELAY_SEC : 0,
    redMods,
    blueLocked,
  )
  const redTimed = collectFighterDamageTimed(
    redLoadout,
    input.mode,
    redStats,
    blueStats,
    0,
    [blueLoadout],
    xhMode,
    redFighterOutgoing,
    enemyFacingUtility(blueOutgoing),
    'red',
    visionUnits,
    input.wards,
    { durationSec: input.durationSec, aaUptime: input.aaUptime },
    redLocked ? ENGAGE_REACTION_DELAY_SEC : 0,
    blueMods,
    redLocked,
  )

  const bluePackets = amplifyWithObjectives(blueTimed.packets, blueMods, 0)
  const redPackets = amplifyWithObjectives(redTimed.packets, redMods, 0)
  const remapHits = (
    hits: TimedHit[],
    side: 'blue' | 'red',
  ): TimedHit[] => {
    return hits.map((h) => ({
      ...h,
      side,
      packets: amplifyWithObjectives(h.packets, side === 'blue' ? blueMods : redMods, 0),
    }))
  }

  const blueSideStub: SideResult = {
    side: 'blue',
    label: teamLabel([blueLoadout]),
    fighters: [
      {
        index: 0,
        championId: blueLoadout.championId,
        championName: getChampion(blueLoadout.championId)?.name ?? blueLoadout.championId,
        stats: blueStats,
        packets: bluePackets,
        rawTotal: sumRaw(bluePackets),
        mitigatedTotal: 0,
        lockedOut: blueLocked,
        avgXh: avgPacketXh(bluePackets),
        omittedSlots: blueTimed.omittedSlots,
        omissionNotes: blueTimed.omissionNotes,
        budgetNote: blueTimed.budgetNote,
        targetIndex: 0,
      },
    ],
    stats: blueStats,
    packets: bluePackets,
    rawTotal: sumRaw(bluePackets),
    mitigatedTotal: 0,
    hpRemaining: 0,
    hpRemainingPct: 0,
    damagePctOfEnemy: 0,
    kills: false,
    lockedOut: blueLocked,
    outgoingUtility: blueOutgoing,
    incomingUtility: redOutgoing,
    targets: [],
    focusTargetIndex: 0,
    defensiveUtilityByTarget: [selfFacingUtility(blueOwn)],
  }
  const redSideStub: SideResult = {
    side: 'red',
    label: teamLabel([redLoadout]),
    fighters: [
      {
        index: 0,
        championId: redLoadout.championId,
        championName: getChampion(redLoadout.championId)?.name ?? redLoadout.championId,
        stats: redStats,
        packets: redPackets,
        rawTotal: sumRaw(redPackets),
        mitigatedTotal: 0,
        lockedOut: redLocked,
        avgXh: avgPacketXh(redPackets),
        omittedSlots: redTimed.omittedSlots,
        omissionNotes: redTimed.omissionNotes,
        budgetNote: redTimed.budgetNote,
        targetIndex: 0,
      },
    ],
    stats: redStats,
    packets: redPackets,
    rawTotal: sumRaw(redPackets),
    mitigatedTotal: 0,
    hpRemaining: 0,
    hpRemainingPct: 0,
    damagePctOfEnemy: 0,
    kills: false,
    lockedOut: redLocked,
    outgoingUtility: redOutgoing,
    incomingUtility: blueOutgoing,
    targets: [],
    focusTargetIndex: 0,
    defensiveUtilityByTarget: [selfFacingUtility(redOwn)],
  }

  const { blue, red, timing } = resolveTimedPair(
    {
      side: blueSideStub,
      hits: remapHits(blueTimed.hits, 'blue'),
      stats: blueStats,
      itemUtility: blueTimed.itemUtility,
      caveats: blueTimed.caveats,
    },
    {
      side: redSideStub,
      hits: remapHits(redTimed.hits, 'red'),
      stats: redStats,
      itemUtility: redTimed.itemUtility,
      caveats: redTimed.caveats,
    },
    durationSec,
    blueMods,
    redMods,
  )

  // Dead teammates (if any) appended like buildSide.
  const appendDead = (
    side: SideResult,
    loadouts: FighterLoadout[],
  ): SideResult => {
    const dead = loadouts.filter((l) => !isAlive(l))
    if (!dead.length) return side
    const extra: FighterResult[] = dead.map((loadout, i) => ({
      index: side.fighters.length + i,
      championId: loadout.championId,
      championName: getChampion(loadout.championId)?.name ?? loadout.championId,
      stats: buildStats({
        ...loadout,
        alive: false,
        liveStats: { ...loadout.liveStats, hp: 0 },
      }),
      packets: [],
      rawTotal: 0,
      mitigatedTotal: 0,
      lockedOut: false,
      omittedSlots: ['Q', 'W', 'E', 'R', 'AA'],
      dead: true,
    }))
    return { ...side, fighters: [...side.fighters, ...extra] }
  }

  const blueFinal = appendDead(blue, input.blue)
  const redFinal = appendDead(red, input.red)
  const decided = decideWinner(input, blueFinal, redFinal)
  return {
    blue: blueFinal,
    red: redFinal,
    winner: decided.winner,
    pBlue: decided.pBlue,
    pRed: decided.pRed,
    tradeHpWinner: decided.tradeHpWinner,
    timing,
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
  if (primary.blue.kills && primary.red.kills) {
    notes.push(
      `Both sides lethal in ${resolveFightDuration(input).toFixed(0)}s — ranked by overkill (${Math.round(primary.blue.damagePctOfEnemy * 100)}% vs ${Math.round(primary.red.damagePctOfEnemy * 100)}% of enemy HP).`,
    )
  }

  if (
    primary.timing?.method === 'timed_manual_1v1' &&
    primary.timing.firstLethalSec != null
  ) {
    notes.push(
      `stopped at ${primary.timing.firstLethalSec.toFixed(2)}s: first lethal`,
    )
    const suppressed = (primary.timing.events ?? []).filter((e) => e.suppressed)
    for (const e of suppressed.slice(0, 4)) {
      const label =
        e.slot === 'AA' ? `Auto ${e.castIndex}` : `${e.slot} ×${e.castIndex}`
      notes.push(`suppressed ${label}: caster dead`)
    }
  }

  for (const f of [...primary.blue.fighters, ...primary.red.fighters]) {
    if (f.dead) continue
    if (f.budgetNote) {
      notes.push(`${f.championName}: ${f.budgetNote}`)
    }
    for (const omit of f.omissionNotes ?? []) {
      notes.push(`${f.championName}: ${omit}`)
    }
    // Fallback only when omittedSlots lack actionable omissionNotes.
    if (
      f.omittedSlots?.length &&
      !(f.omissionNotes ?? []).some((n) => /omitted /i.test(n))
    ) {
      notes.push(
        `${f.championName} omitted ${f.omittedSlots.join('/')}: no surviving window`,
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
      `Leftover HP% leaned ${primary.tradeHpWinner}; model score favors ${primary.winner} from gold/objectives.`,
    )
  }

  const durationSec = resolveFightDuration(input)
  const aaUptime = input.aaUptime ?? 1
  const modelTrust = classifyMatchupModelTrust(input)
  const assumptions = buildTheorycraftAssumptions(
    input,
    durationSec,
    aaUptime,
    modelTrust,
  )

  return {
    blue: primary.blue,
    red: primary.red,
    winner: primary.winner,
    pBlue: primary.pBlue,
    pRed: primary.pRed,
    modelTrust,
    tradeHpWinner: primary.tradeHpWinner,
    notes: [...new Set(notes)].slice(0, 12),
    xhMode,
    assumptions,
    timing: primary.timing,
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
      const blueMods = modsForSide('blue', input)
      const redMods = modsForSide('red', input)
      return fightDodgeBands(
        input.blue,
        input.red,
        primary.blue.outgoingUtility ?? emptyResolvedUtility(),
        visionUnits,
        'blue',
        input.wards,
        input.mode ?? 'extended',
        sideLocked('blue', input),
        { casterMods: blueMods, enemyMods: redMods },
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
      const blueMods = modsForSide('blue', input)
      const redMods = modsForSide('red', input)
      const bands = fightDodgeBands(
        input.blue,
        input.red,
        primary.blue.outgoingUtility ?? emptyResolvedUtility(),
        visionUnits,
        'blue',
        input.wards,
        input.mode ?? 'extended',
        sideLocked('blue', input),
        { casterMods: blueMods, enemyMods: redMods },
      )
      return bands?.mix != null &&
        Math.abs(bands.mix - bands.typical) > 1e-9
        ? ('mix' as const)
        : ('typical' as const)
    })(),
  }
}

/**
 * Honest A/B scope: replace only one Blue fighter's item list.
 * The calculator deliberately uses the default fighterIndex 0 and labels it
 * as Blue fighter 1; no team-wide build mutation is implied.
 */
export function withBlueFighterItemBuild(
  input: MatchupInput,
  itemIds: string[],
  fighterIndex = 0,
): MatchupInput {
  return {
    ...input,
    blue: input.blue.map((fighter, index) =>
      index === fighterIndex ? { ...fighter, itemIds: [...itemIds] } : fighter,
    ),
  }
}

function buildTheorycraftAssumptions(
  input: MatchupInput,
  durationSec: number,
  aaUptime: number,
  modelTrust = classifyMatchupModelTrust(input),
): string[] {
  const timed = shouldUseTimedManual1v1(input)
  const lines: string[] = [
    `Fight window ${durationSec.toFixed(1)}s · AA uptime ${Math.round(aaUptime * 100)}%.`,
    input.mode === 'short' && durationSec <= 4
      ? timed && (sideLocked('blue', input) || sideLocked('red', input))
        ? `Engage: opener acts at t=0 (skill/auto on the clock); defender starts after ${ENGAGE_REACTION_DELAY_SEC}s and cannot use engage CC.`
        : 'Engage: late-reaction advantage is modeled only for this short window.'
      : 'Engage: ignored outside the short window; longer-fight engage timing is not modeled.',
    `Model confidence: ${modelTrust.badge} (${modelTrust.class}); pBlue/pRed are heuristic ranking scores, not calibrated win probabilities.`,
    timed
      ? 'Resolution: timed_manual_1v1 — chronological bounded-beam cast/AA plan stopped at first lethal (not globally optimal, not calibrated); utility whole-window; default castLock/impact when Meraki kits lack execution metadata; ability CDs assumed ready at t=0.'
      : 'Resolution: aggregate_window fallback — packet counts over the fight window (cast/auto counts from CD/AS; NvM low HP truncates only via modeled survival DPS prior, not absolute slot bans).',
  ]
  const isNvM = input.blue.length > 1 || input.red.length > 1
  if (isNvM) {
    const redFocus = input.red.find(isAlive)
    const blueFocus = input.blue.find(isAlive)
    lines.push(
      `NvM focus: Blue targets ${redFocus ? getChampion(redFocus.championId)?.name ?? redFocus.championId : 'none'}; Red targets ${blueFocus ? getChampion(blueFocus.championId)?.name ?? blueFocus.championId : 'none'} (input order, living only).`,
      'NvM resolution: simultaneous focus fire; no retarget after a focused target dies.',
      'NvM pooling: HP meter sums living targets, but kill flags are target-specific and post-sustain.',
      'Defensive utility is owner/target-scoped; ally-targeted protection is not spread across the team pool.',
      'Ult cap: at most one R cast per fighter in the window; custom windows remain capped.',
      'NvM trust: relative damage is falsifiable; heuristic model scores and retarget timing remain uncalibrated.',
    )
  } else if (timed) {
    lines.push(
      '1v1 timed resolution: chronological impacts; equal timestamps are simultaneous; lethal stops later actions; regen/omnivamp only over elapsed dealt damage.',
    )
    if (modelTrust.class === 'experimental') {
      lines.push(
        'Meraki/generated timed 1v1: experimental and uncalibrated; default execution timing disclosed in timing.caveats when kit metadata is missing.',
      )
    }
  } else {
    lines.push('1v1 resolution: both fighters attack the other fighter; HP and mitigation are target-specific.')
  }

  // Objective applied/disclosed lines are prioritized over optional item/Gnar/dummy
  // detail so a crowded 5v5 assumptions cap cannot starve them.
  const hasLiveOverride = [...input.blue, ...input.red].some((f) =>
    hasAuthoritativeCombatLiveStats(f.liveStats),
  )
  if (input.objectives || hasLiveOverride) {
    lines.push(
      'Authoritative live/dummy AD/AP/armor/MR/AS/MS fields are not re-buffed by objectives.',
    )
  }
  if (input.objectives) {
    lines.push(
      ...formatObjectiveAssumptionLines(
        combatModsFromObjectives(input.objectives.blue, input.objectives.gameTimeSec),
      ).map((l) => `Blue ${l}`),
      ...formatObjectiveAssumptionLines(
        combatModsFromObjectives(input.objectives.red, input.objectives.gameTimeSec),
      ).map((l) => `Red ${l}`),
    )
  }

  const optional: string[] = []
  const itemIds = new Set(
    [...input.blue, ...input.red].flatMap((f) => f.itemIds),
  )
  if (itemIds.has('3078')) {
    optional.push('Trinity Force: one Spellblade proc (200% base AD) in the window.')
  }
  if (itemIds.has('3057')) {
    optional.push('Sheen: one Spellblade proc (100% base AD) in the window.')
  }
  if (itemIds.has('3100')) {
    optional.push('Lich Bane: one Spellblade proc (75% base AD + 40% AP) as magic.')
  }
  if (itemIds.has('3071')) {
    const stacks =
      durationSec >= 12 ? 6 : durationSec >= 6 ? 5 : durationSec >= 3.5 ? 4 : 3
    optional.push(
      `Black Cleaver: ~${stacks} stacks → ${stacks * 5}% armor shred for mitigation.`,
    )
  }
  if (itemIds.has('6653')) {
    optional.push(
      "Liandry's: %max-HP burn scaled to fight length + soft amp vs high HP.",
    )
  }
  if ([...input.blue, ...input.red].some((f) => f.championId === 'Gnar')) {
    optional.push(
      'Gnar form: explicit Mini/Mega wins; otherwise Mega when R is ranked, Mini otherwise. Only one form packet set emits.',
    )
  }
  const target = input.red[0]
  if (target?.liveStats?.hpMax != null || target?.liveStats?.armor != null) {
    const hp = target.liveStats?.hpMax ?? target.liveStats?.hp
    const ar = target.liveStats?.armor
    const mr = target.liveStats?.mr
    const bits = [
      hp != null ? `${Math.round(hp)} HP` : null,
      ar != null ? `${Math.round(ar)} armor` : null,
      mr != null ? `${Math.round(mr)} MR` : null,
    ].filter(Boolean)
    if (bits.length) {
      optional.push(`Dummy target pinned at ${bits.join(' / ')}.`)
    }
  }
  for (const line of optional) {
    if (lines.length >= 16) break
    lines.push(line)
  }
  return lines.slice(0, 16)
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
    // Default neither so the sample ability log has fight clocks. Toggle Engage
    // to blue/red to model opener-at-t=0 + defender reaction delay (still timed).
    engager: 'neither',
    mode: 'short',
    xhMode: 'expected',
  }
}

export type { TradeMode }
