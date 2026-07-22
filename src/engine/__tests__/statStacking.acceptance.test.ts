/**
 * Manual theorycraft stat-stacking acceptance.
 * Run: npm run test:stat-stacking
 *
 * Local evidence: Meraki champions-full.json (AS ratio), items-summoners-rift.json
 * id 3089 Magical Opus 30%, Riot growth / MS soft-cap formulas (documented in
 * src/engine/statStacking.ts). Does not claim wiki exactness beyond those sources.
 */
import { CHAMPIONS } from '../../data/champions'
import {
  applyObjectiveModsToStats,
  combatModsFromObjectives,
  emptyMods,
  emptyTeamObjectives,
  type TeamObjectives,
} from '../objectives'
import { buildStats, resolveFighterCombatStats } from '../stats'
import {
  bonusAttackSpeedFromGrowth,
  composeTheorycraftAp,
  growStat,
  growthMultiplier,
  RABADON_AP_AMP,
  softCapMovespeed,
  totalAttackSpeed,
} from '../statStacking'
import type { FighterLoadout } from '../types'

type Check = { name: string; detail?: string }
const passed: Check[] = []

function assert(condition: unknown, name: string, detail?: string): asserts condition {
  if (!condition) {
    throw new Error(`FAIL ${name}${detail ? ` — ${detail}` : ''}`)
  }
  passed.push({ name, detail })
}

function nearly(a: number, b: number, eps = 1e-9): boolean {
  return Math.abs(a - b) <= eps
}

function team(partial: Partial<TeamObjectives>): TeamObjectives {
  return { ...emptyTeamObjectives(), ...partial }
}

function loadout(
  championId: string,
  overrides: Partial<FighterLoadout> = {},
): FighterLoadout {
  return {
    championId,
    level: 11,
    itemIds: [],
    runeId: null,
    ranks: { Q: 5, W: 3, E: 3, R: 1 },
    abilityRank: 3,
    alive: true,
    hpPct: 1,
    ...overrides,
  }
}

// --- mid-level growth is interpolated, not naive linear ---
{
  assert(nearly(growthMultiplier(18), 17), 'growth multiplier @18 = 17')
  assert(nearly(growthMultiplier(11), 8.775), 'growth multiplier @11 = 8.775')
  const garen = CHAMPIONS.Garen!.stats
  const hp11 = growStat(garen.hp, garen.hpperlevel, 11)
  const naive = garen.hp + garen.hpperlevel * 10
  assert(nearly(hp11, garen.hp + garen.hpperlevel * 8.775), 'Garen HP @11 uses growth curve')
  assert(hp11 < naive - 1, 'Garen HP @11 below naive linear', `${hp11} vs ${naive}`)
  const built = buildStats(loadout('Garen', { level: 11 }))
  assert(nearly(built.hpMax, hp11), 'buildStats HP matches growStat @11')
}

// --- AS ratio unequal to base AS (Gragas Meraki local evidence) ---
{
  const g = CHAMPIONS.Gragas!.stats
  assert(g.attackspeedratio != null, 'Gragas CORE carries Meraki attackspeedratio')
  assert(
    Math.abs((g.attackspeedratio ?? g.attackspeed) - g.attackspeed) > 1e-6,
    'Gragas AS ratio ≠ base AS (falsifier)',
    `base=${g.attackspeed} ratio=${g.attackspeedratio}`,
  )
  const ratio = g.attackspeedratio!
  const level = 11
  const growthBonus = bonusAttackSpeedFromGrowth(g.attackspeedperlevel, level)
  // Wit's End id 3091: +50% bonus AS in generated catalog
  const withItem = buildStats(loadout('Gragas', { level, itemIds: ['3091'] }))
  const expected = totalAttackSpeed(g.attackspeed, ratio, growthBonus + 0.5)
  assert(nearly(withItem.attackSpeed, expected), 'item AS% scales through ratio', `${withItem.attackSpeed} vs ${expected}`)
  const wrongAdd = g.attackspeed * (1 + (g.attackspeedperlevel * (level - 1)) / 100) + 0.5
  assert(
    Math.abs(withItem.attackSpeed - wrongAdd) > 0.01,
    'item AS is not naive base*(1+g) + flat add',
    `${withItem.attackSpeed} vs wrong ${wrongAdd}`,
  )

  const hex = combatModsFromObjectives(
    team({ dragons: ['hextech'], dragonCount: 1 }),
    20 * 60,
  )
  const base = buildStats(loadout('Gragas', { level, itemIds: [] }))
  const withHex = applyObjectiveModsToStats(base, hex, undefined)
  assert(
    nearly(withHex.attackSpeed, base.attackSpeed + 0.05 * ratio),
    'Hextech +5% AS adds through ratio',
    `${withHex.attackSpeed}`,
  )
}

// --- Rabadon + Baron + Infernal ordering ---
{
  const baronAp = 20 // Patch 9.2 anchor @20m
  const infernal = 0.03
  const itemAp = 130 // Rabadon flat from local item catalog
  const expected = composeTheorycraftAp({
    flatAp: itemAp,
    baronAp,
    infernalApPercent: infernal,
    rabadonAmp: RABADON_AP_AMP,
  })
  // (130+20)*1.03*1.30
  assert(nearly(expected, 150 * 1.03 * 1.3), 'compose AP = (flat+Baron)×Infernal×Rabadon')

  const mods = emptyMods()
  mods.apBonus = baronAp
  mods.apPercent = infernal
  const resolved = resolveFighterCombatStats(
    loadout('Lux', {
      level: 11,
      itemIds: ['3089'],
    }),
    {
      ...mods,
      applied: [],
      disclosedOnly: [],
      notes: [],
    },
  )
  // Lux has 0 base AP; only Rabadon flat 130 + baron + amps
  assert(
    nearly(resolved.ap, expected),
    'resolveFighterCombatStats Rabadon+Baron+Infernal',
    `${resolved.ap} vs ${expected}`,
  )

  const oldWrong = (itemAp * 1.3 + baronAp) * (1 + infernal)
  assert(
    Math.abs(resolved.ap - oldWrong) > 1,
    'differs from old (Rabadon-before-Baron) ordering',
    `${resolved.ap} vs old ${oldWrong}`,
  )

  const livePin = resolveFighterCombatStats(
    loadout('Lux', {
      level: 11,
      itemIds: ['3089'],
      liveStats: { ap: 999 },
    }),
    { ...mods, applied: [], disclosedOnly: [], notes: [] },
  )
  assert(nearly(livePin.ap, 999), 'live AP pin skips Rabadon+Baron+Infernal')
}

// --- Cloud Soul MS soft caps once; live MS absolute ---
{
  assert(nearly(softCapMovespeed(400), 400), 'MS ≤415 uncapped')
  assert(nearly(softCapMovespeed(450), 450 * 0.8 + 83), 'MS mid soft cap 415–490')
  assert(nearly(softCapMovespeed(500), 500 * 0.5 + 230), 'MS high soft cap >490')

  const cloud = combatModsFromObjectives(
    team({
      dragons: ['cloud', 'cloud', 'mountain', 'cloud'],
      dragonCount: 4,
      hasSoul: true,
      soulType: 'cloud',
    }),
    25 * 60,
  )
  assert(nearly(cloud.movespeedPct, 0.15), 'Cloud Soul +15% on mods')

  // Force raw uncapped base so *1.15 crosses 415.
  const baseStats = buildStats(loadout('Garen', { level: 11 }))
  const inflated = { ...baseStats, movespeed: 400 }
  const capped = applyObjectiveModsToStats(inflated, cloud, undefined)
  const raw = 400 * 1.15 // 460
  assert(raw > 415 && raw <= 490, 'fixture crosses mid soft-cap band')
  assert(
    nearly(capped.movespeed, softCapMovespeed(raw)),
    'Cloud Soul then soft-cap exactly once',
    `${capped.movespeed} vs ${softCapMovespeed(raw)}`,
  )
  assert(
    Math.abs(capped.movespeed - raw) > 1,
    'soft cap changes the uncapped product',
  )

  // Crossing 490
  const high = applyObjectiveModsToStats(
    { ...baseStats, movespeed: 450 },
    cloud,
    undefined,
  )
  const highRaw = 450 * 1.15 // 517.5
  assert(highRaw > 490, 'fixture crosses high soft-cap')
  assert(
    nearly(high.movespeed, softCapMovespeed(highRaw)),
    'Cloud Soul high-band soft-cap once',
    `${high.movespeed}`,
  )

  const liveMs = applyObjectiveModsToStats(
    baseStats,
    cloud,
    { movespeed: 777 },
  )
  assert(nearly(liveMs.movespeed, 777), 'authoritative live MS untouched by Cloud/soft-cap')
}

console.log(`stat-stacking acceptance: ${passed.length} checks passed`)
for (const p of passed) {
  console.log(`  ✓ ${p.name}${p.detail ? ` (${p.detail})` : ''}`)
}
