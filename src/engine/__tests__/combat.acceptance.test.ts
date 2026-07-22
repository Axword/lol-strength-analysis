import {
  defaultLoadout,
  simulateMatchup,
  withBlueFighterItemBuild,
} from '../combat'
import { sumMitigated } from '../damage'
import { classifyMatchupModelTrust } from '../modelTrust'
import { planRotation, type RotationActionCandidate } from '../rotation'
import { autoAttackDamage, buildStats } from '../stats'
import { CHAMPIONS, CORE_CHAMPION_IDS, isCoreChampion } from '../../data/champions'
import type { CombatStats, FighterLoadout, MatchupInput, MatchupResult } from '../types'

type Check = { name: string; detail?: string }

const passed: Check[] = []

function assert(condition: unknown, name: string, detail?: string): asserts condition {
  if (!condition) {
    throw new Error(`FAIL ${name}${detail ? ` — ${detail}` : ''}`)
  }
  passed.push({ name, detail })
}

function fighter(
  championId: string,
  overrides: Partial<FighterLoadout> = {},
): FighterLoadout {
  return {
    ...defaultLoadout(championId),
    level: 18,
    ranks: { Q: 5, W: 5, E: 5, R: 3 },
    ...overrides,
  }
}

function fight(
  blue: FighterLoadout[],
  red: FighterLoadout[],
  overrides: Partial<MatchupInput> = {},
): MatchupResult {
  return simulateMatchup({
    blue,
    red,
    engager: 'neither',
    mode: 'allin',
    durationSec: 8,
    xhMode: 'off',
    ...overrides,
  })
}

function finiteResult(result: MatchupResult): boolean {
  const sides = [result.blue, result.red]
  return sides.every((side) => {
    const targets = side.targets ?? []
    return [side.mitigatedTotal, side.hpRemaining, side.hpRemainingPct]
      .every(Number.isFinite) &&
      targets.every((target) =>
        [
          target.hpStart,
          target.hpMax,
          target.incomingDamage,
          target.sustainHeal,
          target.hpRemaining,
        ].every(Number.isFinite),
      )
  })
}

function packetSources(result: MatchupResult, side: 'blue' | 'red'): string[] {
  return result[side].packets.map((packet) => packet.source)
}

// Gate 0: CORE ID export is stable and does not change merge semantics.
{
  assert(CORE_CHAMPION_IDS.length >= 10, 'CORE_CHAMPION_IDS exposes hand-modeled kits')
  assert(
    CORE_CHAMPION_IDS.every((id, i, arr) => {
      if (i === 0) return true
      const prev = arr[i - 1]!
      return prev < id
    }),
    'CORE_CHAMPION_IDS is in ascending code-point order',
  )
  assert(
    JSON.stringify([...CORE_CHAMPION_IDS]) ===
      JSON.stringify(
        [...CORE_CHAMPION_IDS].sort((a, b) => (a < b ? -1 : a > b ? 1 : 0)),
      ),
    'CORE_CHAMPION_IDS matches code-point comparator exactly',
  )
  assert(isCoreChampion('Darius') && isCoreChampion('Nasus'), 'CORE includes Darius and Nasus')
  assert(!isCoreChampion('Gnar'), 'Gnar remains generated-only (not CORE)')
}

// Gate 1: kills are post-sustain state, not pre-heal damage >= HP.
// Uses a generated kit so aggregate_window sustain (full-window) still applies.
{
  const result = fight(
    [fighter('Gnar', { level: 1, itemIds: ['3072'], hpPct: 0.2, form: 'mega' })],
    [fighter('Zilean', { level: 1, ranks: { Q: 1, W: 0, E: 0, R: 0 } })],
  )
  assert(result.timing?.method === 'aggregate_window', 'Gate 1 stays on aggregate_window (generated Blue)')
  const target = result.blue.targets?.[0]
  assert(!!target, 'kills-vs-heal target exists')
  assert(
    target.incomingDamage > target.hpStart && target.hpRemaining > 0,
    'kills-vs-heal preserves a target saved by sustain',
    `incoming=${target.incomingDamage.toFixed(1)} start=${target.hpStart.toFixed(1)} left=${target.hpRemaining.toFixed(1)}`,
  )
  assert(target.killed === false && result.red.kills === false, 'kills derive from post-sustain HP')
  assert(result.blue.kills === (result.red.targets ?? []).some((target) => target.killed), 'Blue kill flag points at Red targets')
  assert(result.winner === 'blue' && (result.pBlue ?? 0) > 0.5, 'one-sided kill produces Blue winner and model-score direction')
}

// Gate 1b: asymmetric directional accounting and defender DR.
{
  const baseline = fight([fighter('Darius')], [fighter('Garen', { ranks: { Q: 5, W: 0, E: 5, R: 3 } })])
  const guarded = fight([fighter('Darius')], [fighter('Garen', { ranks: { Q: 5, W: 5, E: 5, R: 3 } })])
  assert(baseline.blue.kills === (baseline.red.targets ?? []).some((target) => target.killed), 'asymmetric baseline Blue kill direction')
  assert(baseline.red.kills === (baseline.blue.targets ?? []).some((target) => target.killed), 'asymmetric baseline Red kill direction')
  assert((guarded.red.targets?.[0]?.damageReduction ?? 0) > 0, 'defender DR is recorded on the Red target')
  assert(guarded.blue.mitigatedTotal < baseline.blue.mitigatedTotal, 'Red defender DR reduces Blue outgoing damage')
  assert(Math.abs(guarded.red.mitigatedTotal - baseline.red.mitigatedTotal) < 1e-6, 'Red defender DR does not reduce Red outgoing damage')
  assert(
    Math.abs(
      guarded.blue.damagePctOfEnemy -
        guarded.blue.mitigatedTotal / (guarded.red.targets?.[0]?.hpStart ?? 1),
    ) < 1e-9,
    'Blue damagePctOfEnemy uses Blue outgoing damage against Red HP',
  )
}

// Gate 2: percent-max-HP packets use the concrete focus target, not a team average.
// Attacker is generated (Gnar) so 1v1 and 1v5 both stay on aggregate_window.
{
  const target = () => fighter('Gragas', {
    liveStats: { hp: 3000, hpMax: 3000, armor: 100, mr: 50 },
  })
  const one = fight([fighter('Gnar', { itemIds: ['6653'], form: 'mega' })], [target()])
  const five = fight([fighter('Gnar', { itemIds: ['6653'], form: 'mega' })], [target(), target(), target(), target(), target()])
  assert(one.timing?.method === 'aggregate_window', 'Gate 2 1v1 stays aggregate (generated)')
  assert(
    Math.abs((one.red.targets?.[0]?.incomingDamage ?? 0) - (five.red.targets?.[0]?.incomingDamage ?? 0)) < 1e-6,
    'percent-HP 1v1 vs 1v5 keeps focus-target scaling stable',
  )
  assert(
    (five.red.targets ?? []).slice(1).every((targetResult) => targetResult.incomingDamage === 0),
    'percent-HP 1v5 does not multiply single-target damage across a pooled bar',
  )
  const largerTarget = fight(
    [fighter('Gnar', { itemIds: ['6653'], form: 'mega' })],
    [fighter('Gragas', { liveStats: { hp: 5000, hpMax: 5000, armor: 100, mr: 50 } })],
  )
  assert(
    (largerTarget.red.targets?.[0]?.incomingDamage ?? 0) > (one.red.targets?.[0]?.incomingDamage ?? 0),
    'percent-HP damage increases with actual target max HP',
  )
}

// Gate 3: focus fire is deterministic and preserves N-to-1 stacking.
{
  const one = fight([fighter('Darius')], [fighter('Gragas')])
  const two = fight([fighter('Darius'), fighter('Darius')], [fighter('Gragas')])
  const split = fight([fighter('Darius')], [fighter('Gragas'), fighter('Nasus')])
  assert((two.red.targets?.[0]?.incomingDamage ?? 0) > (one.red.targets?.[0]?.incomingDamage ?? 0), 'N-to-1 attackers stack on one target')
  assert((split.red.targets?.[0]?.incomingDamage ?? 0) > 0, 'focus target receives damage')
  assert(split.red.targets?.[1]?.incomingDamage === 0, 'non-focus target receives no single-target packets')
  assert(split.assumptions?.some((line) => /focus:.*input order/i.test(line)), 'focus order is surfaced in assumptions')
}

// Gate 4: armor/MR and defensive utility resolve per target.
{
  const lowArmor = fight([fighter('Darius')], [fighter('Gragas', { liveStats: { armor: 0, mr: 50 } })])
  const highArmor = fight([fighter('Darius')], [fighter('Gragas', { liveStats: { armor: 300, mr: 50 } })])
  assert(
    (lowArmor.red.targets?.[0]?.incomingDamage ?? 0) > (highArmor.red.targets?.[0]?.incomingDamage ?? 0),
    'focus-target armor changes physical mitigation',
  )
  const guarded = fight(
    [fighter('Darius')],
    [fighter('Garen', { ranks: { Q: 5, W: 5, E: 5, R: 3 } }), fighter('Darius')],
  )
  assert((guarded.red.targets?.[0]?.damageReduction ?? 0) > 0, 'defensive utility applies to its owner target')
  assert((guarded.red.targets?.[1]?.damageReduction ?? 0) === 0, 'defensive utility is not max-merged across NvM targets')
  const wither = fight(
    [fighter('Darius'), fighter('Darius')],
    [fighter('Nasus')],
  )
  assert(
    (wither.blue.fighters[0]?.packets.filter((packet) => packet.slot === 'AA').length ?? 0) <
      (wither.blue.fighters[1]?.packets.filter((packet) => packet.slot === 'AA').length ?? 0),
    'single-target slow utility follows the focus target instead of the whole roster',
  )
}

// Gate 5: Gnar emits exactly one form packet family.
{
  const mini = fight([fighter('Gnar', { form: 'mini' })], [fighter('Gragas')])
  const mega = fight([fighter('Gnar', { form: 'mega' })], [fighter('Gragas')])
  const automatic = fight([fighter('Gnar')], [fighter('Gragas')])
  const miniSources = packetSources(mini, 'blue').join(' | ')
  const megaSources = packetSources(mega, 'blue').join(' | ')
  assert(/Boomerang Throw/.test(miniSources) && !/Boulder Toss/.test(miniSources), 'Gnar Mini emits Mini Q only')
  assert(/Hyper/.test(miniSources) && !/Wallop/.test(miniSources), 'Gnar Mini emits Mini W only')
  assert(/Hop/.test(miniSources) && !/Crunch/.test(miniSources), 'Gnar Mini emits Mini E only')
  assert(/Boulder Toss/.test(megaSources) && !/Boomerang Throw/.test(megaSources), 'Gnar Mega emits Mega Q only')
  assert(/Wallop/.test(megaSources) && !/Hyper/.test(megaSources), 'Gnar Mega emits Mega W only')
  assert(/Crunch/.test(megaSources) && !/Hop/.test(megaSources), 'Gnar Mega emits Mega E only')
  assert(!/GNAR!/.test(miniSources) && /GNAR!/.test(megaSources), 'Gnar R is gated by form')
  assert(packetSources(automatic, 'blue').some((source) => /Boulder Toss/.test(source)), 'Gnar default is Mega when R is ranked')
}

// Gate 6: duration ladder produces an honest monotone packet budget.
{
  const durations = [3.5, 8, 16]
  const totals = durations.map((durationSec) =>
    fight([fighter('Darius')], [fighter('Gragas')], {
      durationSec,
      mode: durationSec <= 4 ? 'short' : durationSec <= 10 ? 'allin' : 'extended',
    }).blue.rawTotal,
  )
  assert(totals[1] >= totals[0] && totals[2] >= totals[1], 'duration ladder does not reduce the attack budget', totals.map((n) => n.toFixed(1)).join(' < '))
}

// Gate 7: engage is a short-window contract, not a silent 8/16s no-op.
{
  const longNeutral = fight([fighter('Gragas')], [fighter('Darius')], { mode: 'allin', durationSec: 8, engager: 'neither' })
  const longBlue = fight([fighter('Gragas')], [fighter('Darius')], { mode: 'allin', durationSec: 8, engager: 'blue' })
  assert(Math.abs(longNeutral.red.rawTotal - longBlue.red.rawTotal) < 1e-6, 'engage is explicitly inactive outside short fights')
  const shortNeutral = fight([fighter('Gragas')], [fighter('Darius')], { mode: 'short', durationSec: 3.5, engager: 'neither' })
  const shortBlue = fight([fighter('Gragas')], [fighter('Darius')], { mode: 'short', durationSec: 3.5, engager: 'blue' })
  assert(shortNeutral.red.rawTotal !== shortBlue.red.rawTotal, 'short engage changes the late-reaction model')
}

// Gate 8: every 1..5 x 1..5 cell is exercised with cross-side invariants.
{
  const roster = ['Gragas', 'Darius', 'Ahri', 'Gnar', 'Nasus']
  let cells = 0
  for (let blueCount = 1; blueCount <= 5; blueCount++) {
    for (let redCount = 1; redCount <= 5; redCount++) {
      const result = fight(
        roster.slice(0, blueCount).map((id) => fighter(id)),
        roster.slice(0, redCount).map((id) => fighter(id)),
      )
      assert(finiteResult(result), `matrix ${blueCount}v${redCount} finite`)
      assert(result.blue.kills === (result.red.targets ?? []).some((target) => target.killed), `matrix ${blueCount}v${redCount} Blue kill direction`)
      assert(result.red.kills === (result.blue.targets ?? []).some((target) => target.killed), `matrix ${blueCount}v${redCount} Red kill direction`)
      for (const side of [result.blue, result.red]) {
        assert(side.hpRemaining >= 0 && side.hpRemainingPct >= 0 && side.hpRemainingPct <= 1.001, `matrix ${blueCount}v${redCount} HP bounds`)
      }
      assert(result.modelTrust?.calibrated === false, `matrix ${blueCount}v${redCount} calibrated=false`)
      if (blueCount > 1 || redCount > 1) {
        assert(result.modelTrust?.class === 'experimental', `matrix ${blueCount}v${redCount} experimental`)
      }
      cells += 1
    }
  }
  console.log(`NvM matrix: ${cells}/25 cells exercised; finite HP, target-specific kills, and bounded pooling invariants passed.`)
  console.log('NvM trust report: all 25 cells remain untrusted for calibrated fight odds; the engine now exposes deterministic focus assumptions and target-level evidence.')
}

// Gate 9: A/B is an item-only comparison for Blue fighter 1.
{
  const input: MatchupInput = {
    blue: [fighter('Darius'), fighter('Nasus')],
    red: [fighter('Gragas')],
    engager: 'neither',
    mode: 'allin',
    durationSec: 8,
    xhMode: 'off',
  }
  const compared = withBlueFighterItemBuild(input, ['3072'])
  assert(compared.blue[0]?.itemIds.join(',') === '3072', 'A/B changes Blue fighter 1 items')
  assert(compared.blue[0]?.championId === input.blue[0]?.championId, 'A/B keeps Blue fighter 1 identity')
  assert(compared.blue[1] === input.blue[1] && compared.red === input.red, 'A/B leaves other fighters and Red unchanged')
}

// Gate 10: model-trust classifier — CORE 1v1, generated, NvM, calibrated, reasons.
{
  const coreInput: MatchupInput = {
    blue: [fighter('Darius')],
    red: [fighter('Gragas')],
    engager: 'neither',
    mode: 'allin',
    durationSec: 8,
    xhMode: 'off',
  }
  const coreA = classifyMatchupModelTrust(coreInput)
  const coreB = classifyMatchupModelTrust(coreInput)
  assert(coreA.class === 'manual_kit_1v1', 'CORE 1v1 classifies as manual_kit_1v1')
  assert(coreA.calibrated === false, 'CORE 1v1 calibrated=false')
  assert(coreA.badge === 'Manual kits · uncalibrated', 'CORE 1v1 badge')
  assert(
    JSON.stringify(coreA.reasons) === JSON.stringify(coreB.reasons),
    'model-trust reasons are deterministic',
  )
  assert(
    JSON.stringify(coreA.reasons) ===
      JSON.stringify(
        [...coreA.reasons].sort((a, b) => (a < b ? -1 : a > b ? 1 : 0)),
      ),
    'model-trust reasons are in ascending code-point order',
  )
  assert(
    coreA.reasons.includes('calibrated:false') &&
      coreA.reasons.includes('class:manual_kit_1v1') &&
      coreA.reasons.includes('reason:both_fighters_core'),
    'CORE 1v1 reasons include class and both_fighters_core',
  )
  assert(
    coreA.champions.every((c) => c.tier === 'core'),
    'CORE 1v1 champion tiers are core',
  )

  const coreFight = fight([fighter('Darius')], [fighter('Gragas')])
  assert(coreFight.modelTrust?.class === 'manual_kit_1v1', 'simulateMatchup attaches manual_kit_1v1 trust')
  assert(coreFight.modelTrust?.calibrated === false, 'simulateMatchup calibrated=false')
  assert(
    coreFight.assumptions?.some((line) =>
      /pBlue\/pRed are heuristic ranking scores, not calibrated win probabilities/i.test(
        line,
      ),
    ),
    'assumptions state heuristic scores are not calibrated win probabilities',
  )

  const generated = classifyMatchupModelTrust({
    ...coreInput,
    blue: [fighter('Gnar')],
    red: [fighter('Darius')],
  })
  assert(generated.class === 'experimental', 'generated champion 1v1 is experimental')
  assert(generated.calibrated === false, 'generated 1v1 calibrated=false')
  assert(generated.badge === 'Experimental · uncalibrated', 'generated badge')
  assert(
    generated.champions.some((c) => c.championId === 'Gnar' && c.tier === 'generated'),
    'Gnar modeling tier is generated',
  )
  assert(generated.reasons.includes('reason:generated_fighter'), 'generated reasons flag generated_fighter')

  const nvm = classifyMatchupModelTrust({
    ...coreInput,
    blue: [fighter('Darius'), fighter('Nasus')],
    red: [fighter('Gragas')],
  })
  assert(nvm.class === 'experimental', 'NvM classifies as experimental')
  assert(nvm.calibrated === false, 'NvM calibrated=false')
  assert(nvm.reasons.includes('reason:nvm'), 'NvM reasons include reason:nvm')
  assert(nvm.reasons.includes('living_roster:2v1'), 'NvM living roster code is 2v1')

  const deadExcluded = classifyMatchupModelTrust({
    ...coreInput,
    blue: [fighter('Darius'), fighter('Nasus', { alive: false })],
    red: [fighter('Gragas')],
  })
  assert(
    deadExcluded.class === 'manual_kit_1v1',
    'dead teammates are ignored for manual-kit 1v1 living roster',
  )
  assert(
    deadExcluded.reasons.includes('living_roster:1v1'),
    'alive:false extra yields living_roster:1v1',
  )

  const hpPctDead = classifyMatchupModelTrust({
    ...coreInput,
    blue: [fighter('Darius'), fighter('Nasus', { hpPct: 0 })],
    red: [fighter('Gragas')],
  })
  assert(hpPctDead.class === 'manual_kit_1v1', 'hpPct:0 extra keeps CORE matchup manual_kit_1v1')
  assert(
    hpPctDead.reasons.includes('living_roster:1v1'),
    'hpPct:0 extra yields living_roster:1v1',
  )
  assert(
    hpPctDead.champions.some((c) => c.championId === 'Nasus' && c.alive === false),
    'hpPct:0 marks Nasus dead in champions[]',
  )

  const liveHpDead = classifyMatchupModelTrust({
    ...coreInput,
    blue: [
      fighter('Darius'),
      fighter('Nasus', { liveStats: { hp: 0, hpMax: 2000 } }),
    ],
    red: [fighter('Gragas')],
  })
  assert(
    liveHpDead.class === 'manual_kit_1v1',
    'liveStats.hp:0 extra keeps CORE matchup manual_kit_1v1',
  )
  assert(
    liveHpDead.reasons.includes('living_roster:1v1'),
    'liveStats.hp:0 extra yields living_roster:1v1',
  )
  assert(
    liveHpDead.champions.some((c) => c.championId === 'Nasus' && c.alive === false),
    'liveStats.hp:0 marks Nasus dead in champions[]',
  )
}

// Gate 11: timed manual 1v1 — Darius AA then W reset; determinism; lethal; NvM aggregate.
{
  const dariusShort = simulateMatchup({
    blue: [
      fighter('Darius', {
        level: 6,
        ranks: { Q: 3, W: 1, E: 1, R: 1 },
        hpPct: 1,
        itemIds: [],
        runeId: null,
      }),
    ],
    red: [
      fighter('Gragas', {
        level: 6,
        ranks: { Q: 3, W: 1, E: 1, R: 1 },
        hpPct: 1,
        itemIds: [],
        runeId: null,
      }),
    ],
    engager: 'neither',
    mode: 'short',
    durationSec: 3.5,
    xhMode: 'off',
  })

  assert(
    dariusShort.timing?.method === 'timed_manual_1v1',
    'CORE 1v1 short uses timed_manual_1v1',
  )
  assert(dariusShort.modelTrust?.calibrated === false, 'timed path calibrated=false')

  const blueEvents = (dariusShort.timing?.events ?? []).filter(
    (e) => e.side === 'blue' && !e.suppressed,
  )
  const aaIdx = blueEvents.findIndex((e) => e.slot === 'AA')
  const wIdx = blueEvents.findIndex((e) => e.slot === 'W')
  assert(aaIdx >= 0, 'Darius 3.5s timed log includes an ordinary AA')
  assert(wIdx >= 0, 'Darius 3.5s timed log includes W (Crippling Strike)')
  assert(aaIdx < wIdx, 'ordinary AA precedes W in the timed log')
  assert(
    blueEvents[wIdx]!.impactSec - blueEvents[aaIdx]!.impactSec < 2.5,
    'W follows AA within a realistic short interval',
    `dt=${(blueEvents[wIdx]!.impactSec - blueEvents[aaIdx]!.impactSec).toFixed(3)}`,
  )
  assert(
    blueEvents.filter((e) => e.slot === 'W').length === 1,
    'W appears exactly once in the timed event log',
  )
  const wPackets = dariusShort.blue.packets.filter((p) => p.slot === 'W' && !p.omitted)
  assert(wPackets.length === 1, 'W damage counted once (no double base-AD packet)')
  assert(
    !/Auto/.test(wPackets[0]?.source ?? '') || /Crippling/.test(wPackets[0]?.source ?? ''),
    'W packet is Crippling Strike, not a second Auto label',
  )
  assert(
    blueEvents.every(
      (e) =>
        Number.isFinite(e.startSec) &&
        Number.isFinite(e.impactSec) &&
        e.startSec >= 0 &&
        e.impactSec >= 0 &&
        e.impactSec <= 3.5 + 1e-9,
    ),
    'timed events are finite, nonnegative, impact within requested window',
  )
  const sortedOk = blueEvents.every((e, i, arr) => {
    if (i === 0) return true
    const prev = arr[i - 1]!
    if (e.impactSec !== prev.impactSec) return e.impactSec >= prev.impactSec
    return true
  })
  assert(sortedOk, 'timed events are stable-sorted by impact')

  // Determinism: identical input → deep-equal timing.
  const dariusShortB = simulateMatchup({
    blue: [
      fighter('Darius', {
        level: 6,
        ranks: { Q: 3, W: 1, E: 1, R: 1 },
        hpPct: 1,
        itemIds: [],
        runeId: null,
      }),
    ],
    red: [
      fighter('Gragas', {
        level: 6,
        ranks: { Q: 3, W: 1, E: 1, R: 1 },
        hpPct: 1,
        itemIds: [],
        runeId: null,
      }),
    ],
    engager: 'neither',
    mode: 'short',
    durationSec: 3.5,
    xhMode: 'off',
  })
  assert(
    JSON.stringify(dariusShort.timing) === JSON.stringify(dariusShortB.timing),
    'identical input deep-equals timing',
  )
  assert(
    JSON.stringify(dariusShort) === JSON.stringify(dariusShortB),
    'identical input deep-equals full result',
  )

  // JSON-serializable timing (no NaN / undefined holes in required fields).
  const serialized = JSON.parse(JSON.stringify(dariusShort)) as MatchupResult
  assert(serialized.timing?.method === 'timed_manual_1v1', 'timing survives JSON round-trip')
  assert(
    Array.isArray(serialized.timing?.events) && Array.isArray(serialized.timing?.caveats),
    'timing events/caveats JSON-serializable',
  )

  // Low-HP abilityBudget still omits W.
  const lowHp = simulateMatchup({
    blue: [
      fighter('Darius', {
        level: 6,
        ranks: { Q: 3, W: 1, E: 1, R: 1 },
        hpPct: 0.2,
        itemIds: [],
        runeId: null,
      }),
    ],
    red: [fighter('Gragas', { level: 6 })],
    engager: 'neither',
    mode: 'short',
    durationSec: 3.5,
    xhMode: 'off',
  })
  assert(
    !(lowHp.timing?.events ?? []).some((e) => e.side === 'blue' && e.slot === 'W' && !e.suppressed),
    'low-HP budget omits W from timed log',
  )
  assert(
    lowHp.blue.fighters[0]?.omittedSlots?.includes('W'),
    'low-HP omittedSlots includes W',
  )

  // Prefix: 1.0s damaging actions ⊆ 3.5s plan (by impact time).
  const short1 = simulateMatchup({
    blue: [fighter('Darius', { level: 6, ranks: { Q: 3, W: 1, E: 1, R: 1 }, itemIds: [], runeId: null })],
    red: [fighter('Gragas', { level: 6, itemIds: [], runeId: null })],
    engager: 'neither',
    mode: 'short',
    durationSec: 1.0,
    xhMode: 'off',
  })
  const short35 = simulateMatchup({
    blue: [fighter('Darius', { level: 6, ranks: { Q: 3, W: 1, E: 1, R: 1 }, itemIds: [], runeId: null })],
    red: [fighter('Gragas', { level: 6, itemIds: [], runeId: null })],
    engager: 'neither',
    mode: 'short',
    durationSec: 3.5,
    xhMode: 'off',
  })
  const prefixKeys = (short1.timing?.events ?? [])
    .filter((e) => e.side === 'blue' && !e.suppressed && (e.raw ?? 0) > 0)
    .map((e) => `${e.slot}:${e.castIndex}@${e.startSec.toFixed(4)}`)
  const longerKeys = new Set(
    (short35.timing?.events ?? [])
      .filter((e) => e.side === 'blue' && !e.suppressed && (e.raw ?? 0) > 0)
      .map((e) => `${e.slot}:${e.castIndex}@${e.startSec.toFixed(4)}`),
  )
  assert(
    prefixKeys.every((k) => longerKeys.has(k)),
    '1.0s damaging plan is a time prefix of the 3.5s plan',
    `missing=${prefixKeys.filter((k) => !longerKeys.has(k)).join(',')}`,
  )

  // Lethal early event stops the fight for BOTH sides at firstLethalSec.
  const lethal = simulateMatchup({
    blue: [
      fighter('Darius', {
        level: 18,
        ranks: { Q: 5, W: 5, E: 5, R: 3 },
        itemIds: [],
        runeId: null,
      }),
    ],
    red: [
      fighter('Zilean', {
        level: 1,
        ranks: { Q: 1, W: 0, E: 0, R: 0 },
        hpPct: 0.05,
        itemIds: [],
        runeId: null,
      }),
    ],
    engager: 'neither',
    mode: 'allin',
    durationSec: 8,
    xhMode: 'off',
  })
  assert(lethal.timing?.method === 'timed_manual_1v1', 'lethal case is timed_manual_1v1')
  assert(lethal.red.targets?.[0]?.killed === true, 'low-HP Red is killed')
  const redDeath = lethal.timing?.redDeathSec
  assert(redDeath != null, 'redDeathSec is set')
  assert(
    lethal.timing?.firstLethalSec === redDeath,
    'firstLethalSec equals redDeathSec for one-sided lethal',
  )
  assert(
    lethal.timing?.resolvedSec === lethal.timing?.firstLethalSec &&
      lethal.timing?.executedDurationSec === lethal.timing?.firstLethalSec,
    'resolved/executed equal firstLethalSec (not full 8s window)',
    `resolved=${lethal.timing?.resolvedSec} first=${lethal.timing?.firstLethalSec} req=${lethal.timing?.requestedDurationSec}`,
  )
  assert(
    (lethal.timing?.resolvedSec ?? 0) < 8 - 1e-9,
    'resolvedSec is strictly before requested 8s when someone dies',
  )
  const afterLethal = (lethal.timing?.events ?? []).filter(
    (e) => !e.suppressed && e.impactSec > (lethal.timing?.firstLethalSec ?? 0) + 1e-9,
  )
  assert(
    afterLethal.length === 0,
    'zero unsuppressed events from either side after first lethal',
    `n=${afterLethal.length} slots=${afterLethal.map((e) => `${e.side}:${e.slot}@${e.impactSec}`).join(',')}`,
  )
  const redAfterDeath = (lethal.timing?.events ?? []).filter(
    (e) => e.side === 'red' && !e.suppressed && e.impactSec > (redDeath ?? 0) + 1e-9,
  )
  assert(redAfterDeath.length === 0, 'dead Red has no later unsuppressed events')
  assert(
    !lethal.blue.packets.some((p) => /Noxian Guillotine/.test(p.source)),
    'survivor does not land post-lethal R on a corpse in the short lethal window',
  )

  // Equal-time lethal can produce mutual kill — force via tiny HP both sides
  // and large short burst (same window, CORE 1v1 timed).
  const mutual = simulateMatchup({
    blue: [
      fighter('Darius', {
        level: 18,
        ranks: { Q: 5, W: 5, E: 5, R: 3 },
        hpPct: 0.02,
        itemIds: [],
        runeId: null,
      }),
    ],
    red: [
      fighter('Darius', {
        level: 18,
        ranks: { Q: 5, W: 5, E: 5, R: 3 },
        hpPct: 0.02,
        itemIds: [],
        runeId: null,
      }),
    ],
    engager: 'neither',
    mode: 'allin',
    durationSec: 8,
    xhMode: 'off',
  })
  assert(mutual.timing?.method === 'timed_manual_1v1', 'mutual case timed')
  assert(
    mutual.blue.targets?.[0]?.killed === true && mutual.red.targets?.[0]?.killed === true,
    'equal-time / symmetric lethal can produce mutual kill',
  )

  // Aggregate NvM remains aggregate_window and finite.
  const nvmTimedGate = fight(
    [fighter('Darius'), fighter('Nasus')],
    [fighter('Gragas')],
  )
  assert(nvmTimedGate.timing?.method === 'aggregate_window', 'NvM uses aggregate_window')
  assert(finiteResult(nvmTimedGate), 'NvM aggregate result remains finite')
  assert(nvmTimedGate.modelTrust?.calibrated === false, 'NvM calibrated=false')
}

// Gate 12: Darius W = AD × (1 + rank% AD), one empowered AA — not AD + flat 40–60.
{
  const w = CHAMPIONS.Darius?.abilities.find((a) => a.slot === 'W')
  assert(!!w, 'Darius W ability exists')
  assert(w.execution?.empoweredAuto === true && w.execution?.attackReset === true, 'Darius W stays empowered-auto attack reset')

  const ad = 300
  const attacker = {
    level: 18,
    hp: 3000,
    hpMax: 3000,
    armor: 100,
    mr: 50,
    ad,
    ap: 0,
    attackSpeed: 1,
    attackSpeedRatio: 0.625,
    critChance: 0,
    critDamage: 1.75,
    lethality: 0,
    armorPenPercent: 0,
    magicPenFlat: 0,
    magicPenPercent: 0,
    healShieldPower: 0,
    omnivamp: 0,
    abilityHaste: 0,
    range: 175,
    movespeed: 340,
    baseAd: 100,
    hpRegen: 0,
  } satisfies CombatStats
  const defender = { ...attacker, ad: 0 }

  const pkt = (rank: number) =>
    w.damage(attacker, defender, {
      mode: 'short',
      ranks: { Q: 3, W: rank, E: 1, R: 1 },
      abilityRank: 3,
      hasEngagerAdvantage: false,
    })

  const w1 = pkt(1)
  const w5 = pkt(5)
  assert(w1.length === 1 && w5.length === 1, 'W emits exactly one packet (empowered AA)')
  assert(
    Math.abs(w1[0]!.raw - ad * 1.4) < 1e-9,
    'W1 total = AD × (1 + 0.40)',
    `raw=${w1[0]!.raw} expected=${ad * 1.4}`,
  )
  assert(
    Math.abs(w5[0]!.raw - ad * 1.6) < 1e-9,
    'W5 total = AD × (1 + 0.60)',
    `raw=${w5[0]!.raw} expected=${ad * 1.6}`,
  )
  // Nontrivial AD: flat 40/60 would yield 340/360 — must not match ratio totals 420/480.
  assert(
    Math.abs(w1[0]!.raw - (ad + 40)) > 50 && Math.abs(w5[0]!.raw - (ad + 60)) > 50,
    'W formula is %AD ratio, not flat 40–60',
    `w1=${w1[0]!.raw} flat340=${ad + 40} w5=${w5[0]!.raw} flat360=${ad + 60}`,
  )

  // Timed fight still counts W once at the ratio total (nontrivial live AD).
  const timed = simulateMatchup({
    blue: [
      fighter('Darius', {
        level: 18,
        ranks: { Q: 3, W: 5, E: 1, R: 1 },
        itemIds: [],
        runeId: null,
        liveStats: { ad: 300 },
      }),
    ],
    red: [fighter('Gragas', { level: 18, itemIds: [], runeId: null })],
    engager: 'neither',
    mode: 'short',
    durationSec: 3.5,
    xhMode: 'off',
  })
  const wPackets = timed.blue.packets.filter((p) => p.slot === 'W' && !p.omitted)
  assert(wPackets.length === 1, 'timed fight still emits exactly one W packet')
  assert(
    Math.abs((wPackets[0]?.raw ?? 0) - 300 * 1.6) < 1e-6,
    'timed W5 raw follows AD × 1.6 with liveStats.ad=300',
    `raw=${wPackets[0]?.raw}`,
  )
}

// Gate 13: pure planner — attack-reset empowered auto vs aaReady / full-interval rearm.
{
  const interval = 1.6
  const aa: RotationActionCandidate = {
    id: 'AA',
    slot: 'AA',
    expectedDamage: 100,
    cooldownSec: 0,
    castLockSec: 0.05,
    impactDelaySec: 0.05,
    attackReset: false,
    empoweredAuto: false,
    maxCasts: 4,
  }
  const w: RotationActionCandidate = {
    id: 'W:Crippling Strike',
    slot: 'W',
    expectedDamage: 140,
    cooldownSec: 5,
    castLockSec: 0.15,
    impactDelaySec: 0.1,
    attackReset: true,
    empoweredAuto: true,
    maxCasts: 1,
  }

  const plan = planRotation({
    candidates: [aa, w],
    attackIntervalSec: interval,
    durationSec: 3.5,
    aaCap: 4,
    abilityHaste: 0,
  })
  assert(plan.method === 'bounded_beam', 'planner remains bounded_beam (best-found)')
  assert(plan.effectiveResets >= 1, 'AA→W plan records an effective reset')

  const aa0 = plan.actions.find((a) => a.slot === 'AA' && a.castIndex === 1)
  const wAct = plan.actions.find((a) => a.slot === 'W')
  assert(!!aa0 && !!wAct, 'plan includes ordinary AA and W')
  assert(aa0.startSec <= 1e-9, 'ordinary AA starts at t0')
  assert(
    aa0.startSec < wAct.startSec,
    'canonical weave: ordinary AA before W reset',
  )
  // After AA, aaReady = interval; W must still be allowed before that (reset interrupt).
  assert(
    wAct.startSec + 1e-9 < interval,
    'W starts shortly after AA despite ordinary aaReady still later',
    `W@${wAct.startSec} interval=${interval}`,
  )
  assert(
    wAct.startSec >= aa0.startSec + aa.castLockSec - 1e-9,
    'W respects AA cast lock (global busy)',
  )

  const aaAfterW = plan.actions
    .filter((a) => a.slot === 'AA' && a.startSec > wAct.startSec + 1e-9)
    .sort((a, b) => a.startSec - b.startSec)[0]
  assert(!!aaAfterW, 'a later ordinary AA exists after W')
  assert(
    aaAfterW.startSec + 1e-9 >= wAct.startSec + interval,
    'next ordinary AA waits a full attack interval after W (not castLock)',
    `AA2@${aaAfterW.startSec} W@${wAct.startSec} need>=${wAct.startSec + interval}`,
  )
  assert(
    aaAfterW.startSec > wAct.startSec + w.castLockSec + 0.2,
    'W-first-style castLock rearm is rejected — interval rearm enforced',
  )

  // Equal damage AA+W vs W+AA: secondary effective-reset prefers AA then W (not W first).
  assert(
    plan.actions[0]?.slot === 'AA',
    'equal-damage best-found prefers ordinary AA before W (effective-reset tie-break)',
    `first=${plan.actions[0]?.id}`,
  )

  // After any attack-reset empowered auto, ordinary AA waits a full interval.
  for (const reset of plan.actions.filter(
    (a) => a.empoweredAuto && a.attackReset,
  )) {
    const nextAa = plan.actions
      .filter((a) => a.slot === 'AA' && a.startSec > reset.startSec + 1e-9)
      .sort((a, b) => a.startSec - b.startSec)[0]
    if (!nextAa) continue
    assert(
      nextAa.startSec + 1e-9 >= reset.startSec + interval,
      'reset cannot create a free immediate AA (full interval rearm)',
      `AA@${nextAa.startSec} W@${reset.startSec} castLockWouldBe=${reset.startSec + w.castLockSec}`,
    )
  }

  // Force a true W-first plan: ordinary AA not ready at t0, but reset W may still start.
  const wFirst = planRotation({
    candidates: [aa, w],
    attackIntervalSec: interval,
    durationSec: 3.5,
    aaCap: 4,
    abilityHaste: 0,
    aaReadySec: 99,
  })
  const forcedW = wFirst.actions.find((a) => a.slot === 'W')
  const forcedAa = wFirst.actions
    .filter((a) => a.slot === 'AA')
    .sort((a, b) => a.startSec - b.startSec)[0]
  assert(!!forcedW && forcedW.startSec <= 1e-9, 'W-first: reset W starts at t0 while aaReady is blocked')
  assert(!!forcedAa, 'W-first: ordinary AA still schedules after reset')
  assert(
    forcedAa.startSec + 1e-9 >= forcedW.startSec + interval,
    'W-first cannot create a free immediate AA (full interval rearm)',
    `AA@${forcedAa.startSec} W@${forcedW.startSec} castLockWouldBe=${forcedW.startSec + w.castLockSec}`,
  )
  assert(
    forcedAa.startSec > forcedW.startSec + w.castLockSec + 0.5,
    'W-first post-W AA is not castLock-immediate',
  )

  // Determinism of pure planner.
  const planB = planRotation({
    candidates: [aa, w],
    attackIntervalSec: interval,
    durationSec: 3.5,
    aaCap: 4,
    abilityHaste: 0,
  })
  assert(
    JSON.stringify(plan) === JSON.stringify(planB),
    'pure planner output is deterministic',
  )
}

// Gate 14: stop-at-lethal totals, passive anchor, mitigated score, plan procs, default timing.
{
  // (1) Survivor does not damage a corpse — blue packets only from events ≤ firstLethal.
  const corpse = simulateMatchup({
    blue: [fighter('Darius', { level: 18, ranks: { Q: 5, W: 5, E: 5, R: 3 }, itemIds: [], runeId: null })],
    red: [fighter('Zilean', { level: 1, ranks: { Q: 1, W: 0, E: 0, R: 0 }, hpPct: 0.05, itemIds: [], runeId: null })],
    engager: 'neither',
    mode: 'allin',
    durationSec: 8,
    xhMode: 'off',
  })
  const lethalT = corpse.timing?.firstLethalSec ?? -1
  assert(lethalT >= 0, 'corpse case has firstLethalSec')
  const blueEventRaw = (corpse.timing?.events ?? [])
    .filter((e) => e.side === 'blue' && !e.suppressed)
    .reduce((s, e) => s + (e.raw ?? 0), 0)
  assert(
    Math.abs(blueEventRaw - corpse.blue.rawTotal) < 1e-6,
    'blue rawTotal equals sum of unsuppressed timed event raw (no post-lethal packets)',
    `events=${blueEventRaw} total=${corpse.blue.rawTotal}`,
  )
  assert(
    !(corpse.timing?.events ?? []).some(
      (e) => e.side === 'blue' && !e.suppressed && e.impactSec > lethalT + 1e-9,
    ),
    'survivor deals no unsuppressed damage after lethal (no corpse farming)',
  )

  // (2) Darius aggregate passive anchors to last damaging action — first AA is ordinary AA raw.
  const bleed = simulateMatchup({
    blue: [
      fighter('Darius', {
        level: 6,
        ranks: { Q: 3, W: 1, E: 1, R: 1 },
        itemIds: [],
        runeId: null,
        liveStats: { ad: 200 },
      }),
    ],
    red: [fighter('Gragas', { level: 6, itemIds: [], runeId: null })],
    engager: 'neither',
    mode: 'short',
    durationSec: 3.5,
    xhMode: 'off',
  })
  const firstAaEvt = (bleed.timing?.events ?? [])
    .filter((e) => e.side === 'blue' && e.slot === 'AA' && !e.suppressed)
    .sort((a, b) => a.impactSec - b.impactSec)[0]
  assert(!!firstAaEvt, 'bleed case has an ordinary AA event')
  const statsAd = buildStats(
    fighter('Darius', {
      level: 6,
      ranks: { Q: 3, W: 1, E: 1, R: 1 },
      liveStats: { ad: 200 },
    }),
  )
  const ordinaryAa = autoAttackDamage(statsAd)
  assert(
    Math.abs((firstAaEvt.raw ?? 0) - ordinaryAa) < 1e-6,
    'first AA raw equals ordinary AA raw (passive not front-loaded onto t0/first AA)',
    `aaEvt=${firstAaEvt.raw} ordinary=${ordinaryAa}`,
  )
  const passivePkt = bleed.blue.packets.find((p) => /Hemorrhage|Guillotine reset bleed|Noxian Guillotine reset/i.test(p.source))
  assert(!!passivePkt, 'aggregate passive packet still present')
  const lastBlue = [...(bleed.timing?.events ?? [])]
    .filter((e) => e.side === 'blue' && !e.suppressed && (e.raw ?? 0) > 0)
    .sort((a, b) => a.impactSec - b.impactSec)
    .at(-1)
  assert(!!lastBlue, 'has last blue damaging event')
  // Passive is folded into last hit's event raw (≥ last action's own damage).
  assert(
    (lastBlue.raw ?? 0) + 1e-6 >= (passivePkt.raw ?? 0),
    'aggregate passive is anchored on a late damaging event, not first AA',
  )

  // (3) Planner score is target-effective: high armor / low MR prefers magic over higher raw physical.
  const atk: CombatStats = {
    level: 10, hp: 2000, hpMax: 2000, armor: 50, mr: 30, ad: 100, ap: 100,
    attackSpeed: 1, attackSpeedRatio: 0.625, critChance: 0, critDamage: 1.75, lethality: 0,
    armorPenPercent: 0, magicPenFlat: 0, magicPenPercent: 0,
    healShieldPower: 0, omnivamp: 0, abilityHaste: 0, range: 550,
    movespeed: 330, baseAd: 60, hpRegen: 0,
  }
  const tanky: CombatStats = {
    ...atk, armor: 400, mr: 10, ad: 0, ap: 0,
  }
  const phys = [{ raw: 300, type: 'physical' as const, source: 'Phys', slot: 'Q' as const }]
  const mag = [{ raw: 180, type: 'magical' as const, source: 'Mag', slot: 'W' as const }]
  const physEff = sumMitigated(phys, atk, tanky)
  const magEff = sumMitigated(mag, atk, tanky)
  assert(phys[0]!.raw > mag[0]!.raw, 'raw physical exceeds raw magical')
  assert(magEff > physEff, 'mitigated magical exceeds mitigated physical vs high armor/low MR')
  const scored = planRotation({
    candidates: [
      {
        id: 'Q:Phys',
        slot: 'Q',
        expectedDamage: physEff,
        cooldownSec: 10,
        castLockSec: 0.2,
        impactDelaySec: 0.05,
        attackReset: false,
        empoweredAuto: false,
        maxCasts: 1,
      },
      {
        id: 'W:Mag',
        slot: 'W',
        expectedDamage: magEff,
        cooldownSec: 10,
        castLockSec: 0.2,
        impactDelaySec: 0.05,
        attackReset: false,
        empoweredAuto: false,
        maxCasts: 1,
      },
    ],
    attackIntervalSec: 1.5,
    // Only one action fits — mutually exclusive boundary.
    durationSec: 0.12,
    aaCap: 0,
    abilityHaste: 0,
  })
  assert(
    scored.actions.length === 1 && scored.actions[0]?.id === 'W:Mag',
    'mitigated scorer selects higher effective damage under mutual exclusion',
    `actions=${scored.actions.map((a) => a.id).join(',')} physEff=${physEff.toFixed(1)} magEff=${magEff.toFixed(1)}`,
  )

  // (4) Item abilityProcs from actual plan — utility-only cast is not a plan
  // ability action, so Spellblade must not fire (old estimate counted E casts).
  const sheenUtil = simulateMatchup({
    blue: [
      fighter('Zilean', {
        level: 6,
        ranks: { Q: 0, W: 0, E: 3, R: 0 },
        itemIds: ['3057'],
        runeId: null,
      }),
    ],
    red: [fighter('Gragas', { level: 6, itemIds: [], runeId: null })],
    engager: 'neither',
    mode: 'short',
    durationSec: 3.5,
    xhMode: 'off',
  })
  assert(sheenUtil.timing?.method === 'timed_manual_1v1', 'sheen util case is timed')
  assert(
    !sheenUtil.blue.packets.some((p) => /Spellblade/i.test(p.source)),
    'Spellblade omitted when plan has no damaging ability actions (utility-only E)',
    sheenUtil.blue.packets.map((p) => p.source).join(' | '),
  )
  // Control: a damaging ability in-plan still allows Spellblade.
  const sheenQ = simulateMatchup({
    blue: [
      fighter('Zilean', {
        level: 6,
        ranks: { Q: 3, W: 0, E: 0, R: 0 },
        itemIds: ['3057'],
        runeId: null,
      }),
    ],
    red: [fighter('Gragas', { level: 6, itemIds: [], runeId: null })],
    engager: 'neither',
    mode: 'short',
    durationSec: 3.5,
    xhMode: 'off',
  })
  assert(
    sheenQ.blue.packets.some((p) => /Spellblade/i.test(p.source)),
    'Spellblade present when plan schedules a damaging ability',
  )

  // (5) Default execution timing caveat for unannotated slots.
  const defaults = simulateMatchup({
    blue: [fighter('Darius', { level: 6, ranks: { Q: 3, W: 1, E: 1, R: 1 }, itemIds: [], runeId: null })],
    red: [fighter('Gragas', { level: 6, itemIds: [], runeId: null })],
    engager: 'neither',
    mode: 'short',
    durationSec: 3.5,
    xhMode: 'off',
  })
  const defaultCaveat = (defaults.timing?.caveats ?? []).find((c) =>
    c.startsWith('timing:default_execution_metadata:Darius:'),
  )
  assert(!!defaultCaveat, 'emits timing:default_execution_metadata:Darius:<slots>')
  assert(
    /timing:default_execution_metadata:Darius:/.test(defaultCaveat) &&
      defaultCaveat.includes('Q') &&
      !defaultCaveat.includes('W'),
    'default caveat lists unannotated slots (Q) and omits annotated W',
    defaultCaveat,
  )
}

// Gate 15: intentional wait for cooldown recast; xH-aware planner scoring.
{
  // (A) Filler must not force out a waited high-value recast.
  const waitPlan = planRotation({
    candidates: [
      {
        id: 'A',
        slot: 'Q',
        expectedDamage: 1,
        cooldownSec: 0.2,
        castLockSec: 0.2,
        impactDelaySec: 0,
        attackReset: false,
        empoweredAuto: false,
        maxCasts: 10,
      },
      {
        id: 'B',
        slot: 'W',
        expectedDamage: 100,
        cooldownSec: 1,
        castLockSec: 0.1,
        impactDelaySec: 0,
        attackReset: false,
        empoweredAuto: false,
        maxCasts: 2,
      },
    ],
    attackIntervalSec: 1,
    durationSec: 1,
    aaCap: 0,
    abilityHaste: 0,
  })
  const bCasts = waitPlan.actions.filter((a) => a.id === 'B')
  assert(bCasts.length === 2, 'wait-capable plan schedules both B casts', `n=${bCasts.length} actions=${waitPlan.actions.map((a) => `${a.id}@${a.startSec}`).join(',')}`)
  assert(
    waitPlan.score >= 200 - 1e-9,
    'wait-capable plan score >= 200 (B@0 then B@1, not filler A spam)',
    `score=${waitPlan.score}`,
  )
  assert(
    Math.abs(bCasts[0]!.startSec) <= 1e-9 &&
      Math.abs(bCasts[1]!.startSec - 1) <= 1e-9,
    'canonical waited recast is B@0 then B@1',
    `starts=${bCasts.map((a) => a.startSec).join(',')}`,
  )

  // (B) Zero-xH / out-of-range skillshot must not outrank guaranteed damage.
  // Map positions are normalized [0,1]; 1000uu ≈ outside Gragas Q (850) with vision.
  const near = { x: 0.5, y: 0.5 }
  const justOor = { x: 0.5 + 1000 / 14870, y: 0.5 }
  const xhAware = simulateMatchup({
    blue: [
      fighter('Gragas', {
        level: 18,
        ranks: { Q: 5, W: 5, E: 0, R: 0 },
        itemIds: [],
        runeId: null,
        position: near,
      }),
    ],
    red: [
      fighter('Nasus', {
        level: 18,
        ranks: { Q: 1, W: 0, E: 0, R: 0 },
        itemIds: [],
        runeId: null,
        position: justOor,
      }),
    ],
    engager: 'neither',
    mode: 'short',
    durationSec: 3.5,
    aaUptime: 0,
    xhMode: 'expected',
  })
  assert(xhAware.timing?.method === 'timed_manual_1v1', 'xH-aware case is timed')
  const blueSlots = (xhAware.timing?.events ?? [])
    .filter((e) => e.side === 'blue' && !e.suppressed && (e.raw ?? 0) > 0)
    .map((e) => e.slot)
  assert(
    blueSlots.includes('W') && !blueSlots.includes('Q'),
    'zero-xH Gragas Q is not selected over guaranteed W',
    `slots=${blueSlots.join(',')} packets=${xhAware.blue.packets.map((p) => p.source).join(' | ')}`,
  )

  // xhMode=off: skillshot raw unchanged for scoring — Q may still schedule.
  const xhOff = simulateMatchup({
    blue: [
      fighter('Gragas', {
        level: 18,
        ranks: { Q: 5, W: 5, E: 0, R: 0 },
        itemIds: [],
        runeId: null,
        position: near,
      }),
    ],
    red: [
      fighter('Nasus', {
        level: 18,
        ranks: { Q: 1, W: 0, E: 0, R: 0 },
        itemIds: [],
        runeId: null,
        position: justOor,
      }),
    ],
    engager: 'neither',
    mode: 'short',
    durationSec: 3.5,
    aaUptime: 0,
    xhMode: 'off',
  })
  assert(
    (xhOff.timing?.events ?? []).some(
      (e) => e.side === 'blue' && e.slot === 'Q' && !e.suppressed,
    ),
    'xhMode=off still allows out-of-range Q into the plan (raw scoring unchanged)',
  )
}

console.log(`Combat acceptance: ${passed.length} invariants passed.`)
