/**
 * Objective-model acceptance: auditable applied vs disclosed-only contract.
 * Run: npm run test:objectives
 */
import { attributeDrakeBuffs } from '../careerStats'
import {
  defaultLoadout,
  ghostActiveForXh,
  ghostComparisonBaselineMs,
  simulateMatchup,
} from '../combat'
import { gameStateLogit, estimateFightOdds } from '../gameStateOdds'
import {
  applyObjectiveModsToStats,
  baronHandBonusesAtMinute,
  combatModsFromObjectives,
  countDragonStacks,
  elementalDragons,
  emptyTeamObjectives,
  fightDamageAmp,
  formatObjectiveAssumptionLines,
  GRUB,
  grubTickDamage,
  grubTouchBriefCeilingTrue,
  grubTouchGoldEquivalent,
  type TeamObjectives,
} from '../objectives'
import { buildStats } from '../stats'
import { softCapMovespeed } from '../statStacking'
import type { FighterLoadout, SideResult } from '../types'

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

function stubSide(): SideResult {
  return {
    side: 'blue',
    label: 'stub',
    fighters: [],
    stats: {} as SideResult['stats'],
    packets: [],
    rawTotal: 0,
    mitigatedTotal: 100,
    hpRemaining: 1000,
    hpRemainingPct: 1,
    damagePctOfEnemy: 0.4,
    kills: false,
    lockedOut: false,
    targets: [],
  }
}

function stubLoadout(): FighterLoadout {
  return {
    championId: 'Garen',
    level: 11,
    itemIds: [],
    runeId: null,
    ranks: { Q: 5, W: 1, E: 1, R: 1 },
    abilityRank: 3,
    alive: true,
    hpPct: 1,
  }
}

// --- a. Fourth dragon counted and contributes its stack + soul ---
{
  const obj = team({
    dragons: ['infernal', 'mountain', 'cloud', 'infernal'],
    dragonCount: 4,
    hasSoul: true,
    soulType: 'infernal',
  })
  assert(elementalDragons(obj).length === 4, 'fourth dragon kept in elementalDragons')
  assert(countDragonStacks(obj, 'infernal') === 2, 'fourth kill adds permanent Infernal stack')
  const mods = combatModsFromObjectives(obj, 25 * 60)
  assert(nearly(mods.adPercent, 0.06), 'two Infernal stacks → 6% AD', `${mods.adPercent}`)
  assert(nearly(mods.apPercent, 0.06), 'two Infernal stacks → 6% AP', `${mods.apPercent}`)
  assert(
    !elementalDragons(team({ dragons: ['infernal', 'elemental'] })).includes('elemental'),
    'legacy literal elemental ignored',
  )
}

// --- b. Permanent values ---
{
  const obj = team({
    dragons: ['infernal', 'mountain', 'hextech', 'chemtech', 'ocean', 'cloud'],
    dragonCount: 6,
  })
  const mods = combatModsFromObjectives(obj, 20 * 60)
  assert(nearly(mods.adPercent, 0.03) && nearly(mods.apPercent, 0.03), 'Infernal +3% AD/AP')
  assert(nearly(mods.armorPercent, 0.05) && nearly(mods.mrPercent, 0.05), 'Mountain +5% resists')
  assert(mods.abilityHaste === 5 && nearly(mods.attackSpeedPercent, 0.05), 'Hextech +5 AH / +5% AS')
  assert(nearly(mods.healShieldPower, 0.06), 'Chemtech +6% HSP tracked on mods')
  assert(nearly(mods.tenacity, 0.06), 'Chemtech +6% tenacity tracked')
  assert(
    mods.applied.every((l) => !/Chemtech/.test(l)),
    'Chemtech not listed as combat-applied',
  )
  assert(
    mods.disclosedOnly.some((l) => /Chemtech/.test(l) && /heal\/shield/.test(l) && /tracked only/i.test(l)),
    'Chemtech HSP disclosed as tracked-only',
  )
  assert(
    mods.disclosedOnly.some((l) => /Chemtech/.test(l) && /tenacity/.test(l) && /tracked only/i.test(l)),
    'Chemtech tenacity disclosed as tracked-only',
  )
  assert(nearly(mods.movespeedPct, 0), 'Cloud permanent OoC MS not applied in combat')
  assert(
    mods.disclosedOnly.some((l) => /Ocean/.test(l) && /2% missing HP/.test(l)),
    'Ocean disclosed as 2% missing HP / 5s',
  )
  assert(
    mods.disclosedOnly.some((l) => /Cloud/.test(l) && /out-of-combat MS/.test(l)),
    'Cloud permanent disclosed OoC MS / slow resist',
  )
}

// --- c. Cloud Soul passive applied; permanent Cloud OoC not ---
{
  const permanentOnly = combatModsFromObjectives(
    team({ dragons: ['cloud', 'cloud'], dragonCount: 2 }),
    20 * 60,
  )
  assert(nearly(permanentOnly.movespeedPct, 0), 'Cloud drake stacks: no in-combat MS')

  const withSoul = combatModsFromObjectives(
    team({
      dragons: ['cloud', 'cloud', 'mountain', 'cloud'],
      dragonCount: 4,
      hasSoul: true,
      soulType: 'cloud',
    }),
    20 * 60,
  )
  assert(nearly(withSoul.movespeedPct, 0.15), 'Cloud Soul passive +15% MS applied')
  assert(
    withSoul.disclosedOnly.some(
      (l) => /60%/.test(l) && /after R/.test(l) && /30s/.test(l),
    ),
    'Cloud Soul R burst disclosed with 30s cooldown',
  )
}

// --- d. Chem helper threshold ---
{
  const chem = team({
    dragons: ['chemtech', 'chemtech', 'chemtech', 'chemtech'],
    dragonCount: 4,
    hasSoul: true,
    soulType: 'chemtech',
  })
  assert(fightDamageAmp(chem, 0.51) === 0, 'Chem Soul helper 0 above 50%')
  assert(fightDamageAmp(chem, 0.5) === 0.13, 'Chem Soul helper 0.13 at 50%')
  assert(fightDamageAmp(chem, 0.2) === 0.13, 'Chem Soul helper 0.13 below 50%')
  assert(fightDamageAmp(chem, undefined) === 0, 'Chem Soul helper 0 without HP evidence')
  const mods = combatModsFromObjectives(chem, 25 * 60)
  assert(mods.damageAmp === 0 && mods.damageReduction === 0, 'Chem Soul not always-on in mods')
}

// --- e. Baron anchors + endsAt inference + zero omnivamp ---
{
  const a20 = baronHandBonusesAtMinute(20)
  const a30 = baronHandBonusesAtMinute(30)
  const a40 = baronHandBonusesAtMinute(40)
  assert(nearly(a20.ad, 12) && nearly(a20.ap, 20), 'Baron anchors @20m = 12/20')
  assert(nearly(a30.ad, 26) && nearly(a30.ap, 43), 'Baron anchors @30m = 26/43')
  assert(nearly(a40.ad, 48) && nearly(a40.ap, 80), 'Baron anchors @40m = 48/80')
  assert(nearly(baronHandBonusesAtMinute(10).ad, 12), 'Baron clamped before 20')
  assert(nearly(baronHandBonusesAtMinute(50).ad, 48), 'Baron clamped after 40')

  // Slain at 20:00 → ends at 23:00 (1380s) when duration is 180s
  const endsAtKnown = combatModsFromObjectives(
    team({
      baronActive: true,
      barons: 1,
      baronEndsAtMs: (20 * 60 + 180) * 1000,
    }),
    25 * 60,
  )
  assert(nearly(endsAtKnown.adBonus, 12) && nearly(endsAtKnown.apBonus, 20), 'Baron endsAt → slain@20')
  assert(endsAtKnown.omnivamp === 0, 'Baron omnivamp is zero (endsAt path)')

  const fallback = combatModsFromObjectives(
    team({ baronActive: true, barons: 1 }),
    30 * 60,
  )
  assert(nearly(fallback.adBonus, 26) && nearly(fallback.apBonus, 43), 'Baron fallback uses game time')
  assert(
    fallback.disclosedOnly.some((l) => /fallback/i.test(l) || /unknown/i.test(l)),
    'Baron fallback assumption disclosed',
  )
  assert(fallback.omnivamp === 0, 'Baron omnivamp is zero (fallback path)')
}

// --- f. Infernal/Hextech/Mountain/Ocean Souls and Elder: no fabricated fields ---
{
  for (const soulType of ['infernal', 'hextech', 'mountain', 'ocean'] as const) {
    const mods = combatModsFromObjectives(
      team({
        dragons: ['infernal', 'mountain', 'cloud', soulType],
        dragonCount: 4,
        hasSoul: true,
        soulType,
      }),
      30 * 60,
    )
    assert(mods.damageAmp === 0, `${soulType} soul: no damageAmp`)
    assert(mods.damageReduction === 0, `${soulType} soul: no DR`)
    assert(mods.omnivamp === 0, `${soulType} soul: no omnivamp`)
    assert(
      !('trueDamageOnHit' in mods),
      `${soulType} soul: no trueDamageOnHit field`,
    )
    assert(
      mods.disclosedOnly.some((l) => new RegExp(soulType, 'i').test(l)),
      `${soulType} soul disclosed`,
    )
  }
  const elder = combatModsFromObjectives(team({ elderActive: true, elders: 1 }), 35 * 60)
  assert(elder.damageAmp === 0 && elder.omnivamp === 0, 'Elder: no amp/omnivamp')
  assert(!('trueDamageOnHit' in elder), 'Elder: no trueDamageOnHit field')
  assert(
    elder.disclosedOnly.some((l) => /Elder/.test(l) && /75/.test(l) && /execute/i.test(l)),
    'Elder burn/execute disclosed',
  )
}

// --- g. Grub values + structure-only ---
{
  assert(grubTickDamage(1, false) === 4 && grubTickDamage(1, true) === 2, 'grub 1-stack ticks')
  assert(grubTickDamage(2, false) === 12 && grubTickDamage(2, true) === 6, 'grub 2-stack ticks')
  assert(grubTickDamage(3, false) === 16 && grubTickDamage(3, true) === 8, 'grub 3-stack ticks')
  assert(GRUB.hungerAtStacks === 3, 'Hunger at 3')
  assert(
    nearly(grubTouchBriefCeilingTrue(3, 8, false), 256),
    'article 8s melee ceiling 256 true',
  )
  assert(
    nearly(grubTouchGoldEquivalent(3, 8, false), (256 / 900) * 120),
    'article 900HP/120g gold-eq',
  )
  const mods = combatModsFromObjectives(team({ voidGrubs: 3 }), 12 * 60)
  assert(
    mods.adPercent === 0 &&
      mods.apPercent === 0 &&
      mods.damageAmp === 0 &&
      mods.adBonus === 0,
    'grubs do not amp champ combat',
  )
  assert(
    mods.disclosedOnly.some((l) => /structure/i.test(l)),
    'grubs disclosed as structure-only',
  )
}

// --- h. gameStateOdds counts fourth dragon + soul ---
{
  const blue = team({
    dragons: ['infernal', 'mountain', 'cloud', 'hextech'],
    dragonCount: 4,
    hasSoul: true,
    soulType: 'hextech',
    gold: 10000,
    towers: 3,
    kills: 5,
  })
  const red = team({
    dragons: ['infernal'],
    dragonCount: 1,
    gold: 10000,
    towers: 3,
    kills: 5,
  })
  const withSoul = estimateFightOdds({
    blue,
    red,
    blueLoadouts: [stubLoadout()],
    redLoadouts: [stubLoadout()],
    blueCombat: stubSide(),
    redCombat: stubSide(),
  })
  const withoutFourth = estimateFightOdds({
    blue: team({
      dragons: ['infernal', 'mountain', 'cloud'],
      dragonCount: 3,
      hasSoul: false,
      gold: 10000,
      towers: 3,
      kills: 5,
    }),
    red,
    blueLoadouts: [stubLoadout()],
    redLoadouts: [stubLoadout()],
    blueCombat: stubSide(),
    redCombat: stubSide(),
  })
  assert(
    withSoul.pBlue > withoutFourth.pBlue,
    'fourth dragon + soul raises blue prior vs 3-drake no-soul',
    `pBlue ${withSoul.pBlue} vs ${withoutFourth.pBlue}`,
  )
}

// --- career: no always-on Chem Soul amp/DR ---
{
  const attr = attributeDrakeBuffs(
    team({
      dragons: ['chemtech', 'chemtech', 'chemtech', 'chemtech'],
      dragonCount: 4,
      hasSoul: true,
      soulType: 'chemtech',
    }),
    {
      kills: 0,
      deaths: 0,
      assists: 0,
      cs: 0,
      jungleCs: 0,
      visionScore: 0,
      dmgTotal: 10000,
      dmgToChamps: 8000,
      physToChamps: 4000,
      magicToChamps: 4000,
      trueToChamps: 0,
      dmgTaken: 5000,
      dmgTakenFromChamps: 4000,
      selfMitigated: 2000,
      dmgToTurrets: 0,
      dmgToBuildings: 0,
      dmgToObjectives: 0,
      healOnTeammates: 1000,
      shieldOnTeammates: 500,
      ccToChamps: 0,
      asPct: 100,
      cdr: 0,
      lifeSteal: 0,
      spellVamp: 0,
      hpRegen: 0,
      gold: 5000,
    },
    25 * 60,
  )
  assert(attr.soulBonusDmg === 0 && attr.soulMitigated === 0, 'career Chem Soul quantified = 0')
  assert(
    attr.quantities.some((q) => /chem soul conditional/i.test(q)) ||
      attr.tags.some((t) => /chem soul/i.test(t)),
    'career tags Chem Soul as conditional',
  )
}

// --- assumptions contract (applied vs disclosedOnly) ---
{
  const mods = combatModsFromObjectives(
    team({
      dragons: ['cloud', 'ocean', 'infernal', 'cloud'],
      dragonCount: 4,
      hasSoul: true,
      soulType: 'cloud',
      baronActive: true,
      baronEndsAtMs: (20 * 60 + 180) * 1000,
      elderActive: true,
      voidGrubs: 3,
    }),
    25 * 60,
  )
  const lines = formatObjectiveAssumptionLines(mods)
  assert(
    lines.some((l) => /^Objectives applied:/.test(l) && /Cloud Soul/.test(l) && /Baron Hand/.test(l)),
    'assumptions list applied Cloud Soul + Baron',
  )
  assert(
    lines.some(
      (l) =>
        /^Objectives disclosed only:/.test(l) &&
        /Elder/.test(l) &&
        /Ocean/.test(l) &&
        /structure/i.test(l),
    ),
    'assumptions list disclosed Elder/Ocean/grubs',
  )
  assert(mods.omnivamp === 0, 'assumptions path: Baron still zero omnivamp')
}

// --- i. Crowded 5v5 assumptions keep objective applied + disclosed ---
{
  const crowdedItems = ['3078', '3057', '3100', '3071', '6653'] as const
  const blue = ['Gnar', 'Ahri', 'LeeSin', 'Jhin', 'Leona'].map((id, i) => ({
    ...defaultLoadout(id),
    level: 13,
    itemIds: [...crowdedItems],
    ranks: { Q: 5, W: 5, E: 5, R: 3 },
    alive: true,
    hpPct: 1,
    liveStats:
      i === 0
        ? { ad: 200, ap: 150, armor: 80, mr: 60, attackSpeed: 1.2, movespeed: 370 }
        : undefined,
  }))
  const red = ['Darius', 'Syndra', 'Gragas', 'Jax', 'Galio'].map((id) => ({
    ...defaultLoadout(id),
    level: 13,
    itemIds: [...crowdedItems],
    ranks: { Q: 5, W: 5, E: 5, R: 3 },
    alive: true,
    hpPct: 1,
  }))
  const result = simulateMatchup({
    blue,
    red,
    engager: 'neither',
    mode: 'allin',
    durationSec: 8,
    xhMode: 'off',
    objectives: {
      gameTimeSec: 28 * 60,
      blue: team({
        dragons: ['infernal', 'mountain', 'cloud', 'infernal'],
        dragonCount: 4,
        hasSoul: true,
        soulType: 'infernal',
        baronActive: true,
        baronEndsAtMs: (20 * 60 + 180) * 1000,
        elderActive: true,
        voidGrubs: 3,
        gold: 40000,
        towers: 5,
        kills: 12,
      }),
      red: team({
        dragons: ['hextech', 'ocean'],
        dragonCount: 2,
        gold: 38000,
        towers: 4,
        kills: 10,
      }),
    },
  })
  const assumptions = result.assumptions ?? []
  assert(assumptions.length <= 16, 'assumptions capped at 16', `${assumptions.length}`)
  assert(
    assumptions.some((l) => /not re-buffed by objectives/i.test(l)),
    'crowded 5v5 keeps live-override provenance caveat',
  )
  assert(
    assumptions.some((l) => /Blue Objectives applied:/.test(l)),
    'crowded 5v5 keeps Blue objectives applied',
  )
  assert(
    assumptions.some((l) => /Blue Objectives disclosed only:/.test(l)),
    'crowded 5v5 keeps Blue objectives disclosed-only',
  )
  assert(
    assumptions.some((l) => /Red Objectives applied:/.test(l) || /Red Objectives disclosed only:/.test(l)),
    'crowded 5v5 keeps Red objective lines',
  )
}

// --- j. gameStateLogit: 4 vs 3 real kills, both hasSoul → exact +0.38 ---
{
  const base = {
    gold: 12000,
    towers: 4,
    kills: 8,
    hasSoul: true,
    soulType: 'infernal' as const,
  }
  const four = team({
    ...base,
    dragons: ['infernal', 'mountain', 'cloud', 'infernal'],
    dragonCount: 4,
  })
  const three = team({
    ...base,
    dragons: ['infernal', 'mountain', 'cloud'],
    dragonCount: 3,
  })
  const red = team({ dragons: [], dragonCount: 0, gold: 12000, towers: 4, kills: 8 })
  const loadouts = [stubLoadout()]
  const logit4 = gameStateLogit(four, red, loadouts, loadouts).logit
  const logit3 = gameStateLogit(three, red, loadouts, loadouts).logit
  assert(
    nearly(logit4 - logit3, 0.38),
    'gameStateLogit 4 vs 3 real drakes (both soul) delta = 0.38',
    `${logit4 - logit3}`,
  )
}

// --- k. Baron endsAt fixed across different current game times ---
{
  const endsAt = (22 * 60 + 180) * 1000 // slain at 22:00
  const early = combatModsFromObjectives(
    team({ baronActive: true, barons: 1, baronEndsAtMs: endsAt }),
    23 * 60,
  )
  const late = combatModsFromObjectives(
    team({ baronActive: true, barons: 1, baronEndsAtMs: endsAt }),
    28 * 60,
  )
  assert(
    nearly(early.adBonus, late.adBonus) && nearly(early.apBonus, late.apBonus),
    'Baron AD/AP identical at two current times with same endsAt',
    `${early.adBonus}/${early.apBonus} vs ${late.adBonus}/${late.apBonus}`,
  )
}

// --- l. Live overrides not double-buffed; manual theorycraft still buffed ---
{
  const obj = team({
    dragons: ['infernal', 'mountain', 'hextech', 'chemtech'],
    dragonCount: 4,
    hasSoul: true,
    soulType: 'cloud',
    baronActive: true,
    baronEndsAtMs: (20 * 60 + 180) * 1000,
  })
  const mods = combatModsFromObjectives(obj, 25 * 60)
  assert(nearly(mods.healShieldPower, 0.06), 'provenance fixture tracks Chemtech HSP')
  assert(nearly(mods.movespeedPct, 0.15), 'Cloud Soul still on mods even without cloud permanent')
  const manualLoadout: FighterLoadout = {
    ...defaultLoadout('Garen'),
    level: 11,
    itemIds: [],
    ranks: { Q: 5, W: 3, E: 3, R: 1 },
  }
  const manualBase = buildStats(manualLoadout)
  const manualBuffed = applyObjectiveModsToStats(manualBase, mods, undefined)
  assert(manualBuffed.ad > manualBase.ad, 'manual theorycraft AD receives Baron+Infernal')
  assert(manualBuffed.ap > manualBase.ap, 'manual theorycraft AP receives Baron+Infernal')
  assert(manualBuffed.armor > manualBase.armor, 'manual theorycraft armor receives Mountain')
  assert(manualBuffed.mr > manualBase.mr, 'manual theorycraft MR receives Mountain')
  assert(
    nearly(
      manualBuffed.attackSpeed,
      manualBase.attackSpeed + 0.05 * manualBase.attackSpeedRatio,
    ),
    'manual Hextech AS adds through attackSpeedRatio',
  )
  assert(
    nearly(
      manualBuffed.movespeed,
      softCapMovespeed(manualBase.movespeed * 1.15),
    ),
    'manual theorycraft MS receives Cloud Soul then soft-caps once',
  )
  assert(
    manualBuffed.abilityHaste === manualBase.abilityHaste + 5,
    'manual theorycraft AH receives Hextech',
  )
  assert(
    manualBuffed.healShieldPower === manualBase.healShieldPower,
    'Chemtech HSP does not mutate CombatStats',
  )

  const livePins = {
    ad: 250,
    ap: 180,
    armor: 100,
    mr: 90,
    attackSpeed: 1.4,
    movespeed: 400,
  }
  const liveLoadout: FighterLoadout = { ...manualLoadout, liveStats: livePins }
  const liveBuilt = buildStats(liveLoadout)
  const liveOut = applyObjectiveModsToStats(liveBuilt, mods, liveLoadout.liveStats)
  assert(nearly(liveOut.ad, livePins.ad), 'live AD not re-buffed', `${liveOut.ad}`)
  assert(nearly(liveOut.ap, livePins.ap), 'live AP not re-buffed', `${liveOut.ap}`)
  assert(nearly(liveOut.armor, livePins.armor), 'live armor not re-buffed', `${liveOut.armor}`)
  assert(nearly(liveOut.mr, livePins.mr), 'live MR not re-buffed', `${liveOut.mr}`)
  assert(
    nearly(liveOut.attackSpeed, livePins.attackSpeed),
    'live AS not re-buffed',
    `${liveOut.attackSpeed}`,
  )
  assert(
    nearly(liveOut.movespeed, livePins.movespeed),
    'live MS not re-buffed (absolute)',
    `${liveOut.movespeed}`,
  )
  assert(
    liveOut.abilityHaste === liveBuilt.abilityHaste + 5,
    'live path still applies Hextech AH',
  )

  const simManual = simulateMatchup({
    blue: [manualLoadout],
    red: [defaultLoadout('Darius')],
    engager: 'neither',
    mode: 'allin',
    durationSec: 8,
    xhMode: 'off',
    objectives: { gameTimeSec: 25 * 60, blue: obj, red: emptyTeamObjectives() },
  })
  const simLive = simulateMatchup({
    blue: [liveLoadout],
    red: [defaultLoadout('Darius')],
    engager: 'neither',
    mode: 'allin',
    durationSec: 8,
    xhMode: 'off',
    objectives: { gameTimeSec: 25 * 60, blue: obj, red: emptyTeamObjectives() },
  })
  assert(
    nearly(simLive.blue.stats.ad, livePins.ad),
    'simulateMatchup live AD unchanged by objectives',
    `${simLive.blue.stats.ad}`,
  )
  assert(
    simManual.blue.stats.ad > buildStats(manualLoadout).ad,
    'simulateMatchup manual AD receives objectives',
  )
  assert(
    (simLive.assumptions ?? []).some((l) => /not re-buffed by objectives/i.test(l)),
    'simulateMatchup assumptions include live provenance caveat',
  )
}

// --- m. Soul/Elder procs add zero combat damage vs identical permanents ---
{
  const permanents = team({
    dragons: ['infernal', 'mountain', 'cloud', 'hextech'],
    dragonCount: 4,
    hasSoul: false,
    gold: 15000,
    towers: 3,
    kills: 6,
  })
  const withProcs = team({
    ...permanents,
    hasSoul: true,
    soulType: 'infernal',
    elderActive: true,
    elders: 1,
  })
  const blue = [defaultLoadout('Garen')]
  const red = [defaultLoadout('Darius')]
  const baseFight = simulateMatchup({
    blue,
    red,
    engager: 'neither',
    mode: 'allin',
    durationSec: 8,
    xhMode: 'off',
    objectives: { gameTimeSec: 30 * 60, blue: permanents, red: emptyTeamObjectives() },
  })
  const procFight = simulateMatchup({
    blue,
    red,
    engager: 'neither',
    mode: 'allin',
    durationSec: 8,
    xhMode: 'off',
    objectives: { gameTimeSec: 30 * 60, blue: withProcs, red: emptyTeamObjectives() },
  })
  assert(
    nearly(baseFight.blue.mitigatedTotal, procFight.blue.mitigatedTotal),
    'Infernal Soul+Elder add no mitigated damage',
    `${baseFight.blue.mitigatedTotal} vs ${procFight.blue.mitigatedTotal}`,
  )
  assert(
    nearly(baseFight.red.mitigatedTotal, procFight.red.mitigatedTotal),
    'Infernal Soul+Elder add no incoming mitigated on red',
    `${baseFight.red.mitigatedTotal} vs ${procFight.red.mitigatedTotal}`,
  )
  assert(
    baseFight.blue.packets.length === procFight.blue.packets.length,
    'Infernal Soul+Elder add no extra damage packets',
    `${baseFight.blue.packets.length} vs ${procFight.blue.packets.length}`,
  )
  assert(
    !procFight.blue.packets.some((p) => /elder|soul/i.test(p.source)),
    'no Elder/Soul packet sources',
  )
}

// --- n. Cloud Soul defender MS reaches xH (timed CORE + aggregate share scalePacketsWithXh) ---
{
  const ahri = {
    ...defaultLoadout('Ahri'),
    level: 11,
    ranks: { Q: 5, W: 3, E: 3, R: 1 } as const,
    position: { x: 7000, y: 7000 },
    alive: true,
    hpPct: 1,
  }
  const garen = {
    ...defaultLoadout('Garen'),
    level: 11,
    ranks: { Q: 5, W: 3, E: 3, R: 1 } as const,
    position: { x: 7600, y: 7000 },
    alive: true,
    hpPct: 1,
  }
  const cloudRed = team({
    dragons: ['cloud', 'cloud', 'cloud', 'cloud'],
    dragonCount: 4,
    hasSoul: true,
    soulType: 'cloud',
  })
  const baseInput = {
    blue: [ahri],
    red: [garen],
    engager: 'neither' as const,
    mode: 'allin' as const,
    durationSec: 8,
    xhMode: 'expected' as const,
  }
  const noObj = simulateMatchup(baseInput)
  const withSoul = simulateMatchup({
    ...baseInput,
    objectives: {
      gameTimeSec: 25 * 60,
      blue: emptyTeamObjectives(),
      red: cloudRed,
    },
  })
  assert(
    nearly(withSoul.red.stats.movespeed, 391, 1e-6),
    'timed CORE: Cloud Soul defender resolved MS ≈ 391',
    `${withSoul.red.stats.movespeed}`,
  )
  assert(
    nearly(noObj.red.stats.movespeed, 340, 1e-6),
    'timed CORE: no-Soul defender MS stays base 340',
    `${noObj.red.stats.movespeed}`,
  )
  assert(
    (withSoul.blue.avgXh ?? 1) < (noObj.blue.avgXh ?? 0),
    'timed CORE: attacker avgXh strictly lower vs Cloud Soul MS',
    `${withSoul.blue.avgXh} vs ${noObj.blue.avgXh}`,
  )
  const skillMit = (r: typeof noObj) =>
    r.blue.packets
      .filter((p) => p.skillshot && !p.omitted)
      .reduce((s, p) => s + (p.raw ?? 0), 0)
  assert(
    skillMit(withSoul) < skillMit(noObj),
    'timed CORE: skillshot-weighted raw strictly lower vs Cloud Soul',
    `${skillMit(withSoul)} vs ${skillMit(noObj)}`,
  )
  assert(
    withSoul.blue.mitigatedTotal < noObj.blue.mitigatedTotal,
    'timed CORE: blue mitigatedTotal strictly lower vs Cloud Soul',
    `${withSoul.blue.mitigatedTotal} vs ${noObj.blue.mitigatedTotal}`,
  )

  const livePin = { movespeed: 340 as const }
  const liveBase = simulateMatchup({
    ...baseInput,
    red: [{ ...garen, liveStats: livePin }],
  })
  const liveSoul = simulateMatchup({
    ...baseInput,
    red: [{ ...garen, liveStats: livePin }],
    objectives: {
      gameTimeSec: 25 * 60,
      blue: emptyTeamObjectives(),
      red: cloudRed,
    },
  })
  assert(
    nearly(liveSoul.red.stats.movespeed, 340),
    'live MS pin absolute under Cloud Soul',
    `${liveSoul.red.stats.movespeed}`,
  )
  assert(
    nearly(liveSoul.blue.avgXh ?? 0, liveBase.blue.avgXh ?? 1),
    'live MS pin: Cloud Soul leaves avgXh unchanged',
    `${liveSoul.blue.avgXh} vs ${liveBase.blue.avgXh}`,
  )
  assert(
    nearly(liveSoul.blue.mitigatedTotal, liveBase.blue.mitigatedTotal),
    'live MS pin: Cloud Soul leaves mitigatedTotal unchanged',
    `${liveSoul.blue.mitigatedTotal} vs ${liveBase.blue.mitigatedTotal}`,
  )

  // Aggregate path (NvM) shares scalePacketsWithXh — Cloud Soul still lowers blue xH.
  const lux = {
    ...defaultLoadout('Lux'),
    level: 11,
    ranks: { Q: 5, W: 3, E: 3, R: 1 } as const,
    position: { x: 6900, y: 7000 },
    alive: true,
    hpPct: 1,
  }
  const nvmBase = simulateMatchup({
    ...baseInput,
    blue: [ahri, lux],
  })
  const nvmSoul = simulateMatchup({
    ...baseInput,
    blue: [ahri, lux],
    objectives: {
      gameTimeSec: 25 * 60,
      blue: emptyTeamObjectives(),
      red: cloudRed,
    },
  })
  assert(
    nearly(nvmSoul.red.stats.movespeed, 391, 1e-6),
    'aggregate NvM: Cloud Soul defender MS ≈ 391',
  )
  assert(
    (nvmSoul.blue.avgXh ?? 1) < (nvmBase.blue.avgXh ?? 0),
    'aggregate NvM: shares fixed xH helper — avgXh drops vs Cloud Soul',
    `${nvmSoul.blue.avgXh} vs ${nvmBase.blue.avgXh}`,
  )
}

// --- o. Ghost inference provenance (live MS vs objective baseline; shared helper) ---
{
  const cloudMods = combatModsFromObjectives(
    team({
      dragons: ['cloud', 'cloud', 'cloud', 'cloud'],
      dragonCount: 4,
      hasSoul: true,
      soulType: 'cloud',
    }),
    25 * 60,
  )
  const garenGhost: FighterLoadout = {
    ...defaultLoadout('Garen'),
    level: 11,
    ranks: { Q: 5, W: 3, E: 3, R: 1 },
    summonerSpells: ['Flash', 'Ghost'],
    alive: true,
    hpPct: 1,
  }
  const baseline = ghostComparisonBaselineMs(garenGhost, cloudMods)
  assert(
    nearly(baseline, 391, 1e-6),
    'Ghost baseline with Cloud Soul (no live MS) ≈ 391',
    `${baseline}`,
  )

  // 1) Cloud Soul + Ghost equipped + no live MS → not inferred
  assert(
    ghostActiveForXh(garenGhost, cloudMods) === false,
    'truth: Cloud Soul + Ghost spell, no live MS → not inferred',
  )

  // 2) live MS equal to resolved Cloud Soul baseline → not inferred
  assert(
    ghostActiveForXh(
      { ...garenGhost, liveStats: { movespeed: 391, ad: 200 } },
      cloudMods,
    ) === false,
    'truth: live MS == Cloud Soul baseline 391 → not inferred',
  )
  // Baseline still strips only MS; other live pins preserved in resolve path
  assert(
    nearly(
      ghostComparisonBaselineMs(
        { ...garenGhost, liveStats: { movespeed: 450, ad: 200 } },
        cloudMods,
      ),
      391,
      1e-6,
    ),
    'baseline omits only live MS (Cloud Soul still applied)',
  )

  // 3) live MS above 1.05 × 391 (e.g. 450) → inferred
  assert(
    ghostActiveForXh(
      { ...garenGhost, liveStats: { movespeed: 450 } },
      cloudMods,
    ) === true,
    'truth: live MS 450 > 1.05×391 Cloud Soul baseline → inferred',
  )

  // 4) explicit ghostActive true wins
  assert(
    ghostActiveForXh(
      { ...garenGhost, ghostActive: true, liveStats: undefined },
      cloudMods,
    ) === true,
    'truth: explicit ghostActive true wins without live MS',
  )
  assert(
    ghostActiveForXh(
      {
        ...defaultLoadout('Garen'),
        ghostActive: true,
        summonerSpells: ['Flash', 'Ignite'],
      },
      cloudMods,
    ) === true,
    'truth: explicit ghostActive true even without Ghost summoner',
  )
}

console.log(`objectives acceptance: ${passed.length} checks passed`)
for (const p of passed) {
  console.log(`  ✓ ${p.name}${p.detail ? ` (${p.detail})` : ''}`)
}
