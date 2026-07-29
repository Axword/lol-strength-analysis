import assert from 'node:assert/strict'
import {
  abilityRanksAreKnown,
  combatStatsAreKnown,
  hpIsKnown,
  legacyFailOpenHpIsKnown,
  unitToLoadout,
  type TimelineUnitFrame,
} from '../timeline'
import {
  buildTimelineFromRfc461Jsonl,
  inferAbilityRanksKnown,
  inferCombatStatsKnown,
  inferHealthKnown,
} from '../rfc461Jsonl'

function baseUnit(overrides: Partial<TimelineUnitFrame> = {}): TimelineUnitFrame {
  return {
    pid: 1,
    champ: 'Gnar',
    name: 'player',
    team: 100,
    role: 'Top',
    level: 6,
    hp: 800,
    hpMax: 1000,
    alive: true,
    ad: 100,
    ap: 0,
    armor: 40,
    mr: 30,
    as: 100,
    x: 0.2,
    y: 0.3,
    items: [3071],
    q: 3,
    w: 1,
    e: 1,
    r: 1,
    ...overrides,
  }
}

// E1 — helpers: undefined is NOT known
{
  const u = {}
  assert.equal(hpIsKnown(u), false)
  assert.equal(combatStatsAreKnown(u), false)
  assert.equal(abilityRanksAreKnown(u), false)
  assert.equal(legacyFailOpenHpIsKnown(u), true, 'legacy path remains disclosed fail-open')
}

// E2 — helpers: explicit false stays unknown
{
  const u = { hpKnown: false, combatStatsKnown: false, abilityRanksKnown: false }
  assert.equal(hpIsKnown(u), false)
  assert.equal(combatStatsAreKnown(u), false)
  assert.equal(abilityRanksAreKnown(u), false)
}

// E3 — helpers: explicit true is known
{
  const u = { hpKnown: true, combatStatsKnown: true, abilityRanksKnown: true }
  assert.equal(hpIsKnown(u), true)
  assert.equal(combatStatsAreKnown(u), true)
  assert.equal(abilityRanksAreKnown(u), true)
}

// E4 — unitToLoadout omits combat/HP when flags absent (no fake known zeros path for stats)
{
  const loadout = unitToLoadout(baseUnit({ hpKnown: undefined, combatStatsKnown: undefined }))
  assert.equal(loadout.hpPct, undefined)
  assert.equal(loadout.liveStats, undefined)
}

// E4b — H3: unknown ranks omit QWER / abilityRank (never fake zeros)
{
  const loadout = unitToLoadout(baseUnit({ abilityRanksKnown: undefined }))
  assert.equal(loadout.ranks, undefined)
  assert.equal(loadout.abilityRank, undefined)
}

// E5 — rfc461 combat: source==null alone is NOT known
{
  assert.equal(inferCombatStatsKnown({}), false)
  assert.equal(inferCombatStatsKnown({ combatStatsSource: null }), false)
  assert.equal(
    inferCombatStatsKnown({ combatStatsSource: 'unavailable_replay_api', attackDamage: 100 }),
    false,
  )
  assert.equal(inferCombatStatsKnown({ attackDamage: 120, armor: 40 }), true)
  assert.equal(
    inferCombatStatsKnown({
      combatStatsSource: 'grid_riot_livestats',
      attackDamage: 120,
      armor: 40,
    }),
    true,
  )
}

// E6 — rfc461 ranks: missing source / missing slots ⇒ false
{
  assert.equal(inferAbilityRanksKnown({}), false)
  assert.equal(inferAbilityRanksKnown({ ability1Level: 3, ability2Level: 1 }), false)
  assert.equal(
    inferAbilityRanksKnown({ abilityRanksSource: 'unavailable', ability1Level: 3 }),
    false,
  )
  assert.equal(
    inferAbilityRanksKnown({ abilityRanksSource: 'grid_riot_livestats' }),
    false,
    'source without slots is unknown',
  )
  assert.equal(
    inferAbilityRanksKnown({
      abilityRanksSource: 'rofl2_upgrade_spell_ans_636_first_write',
      ability1Level: 3,
      ability2Level: 1,
      ability3Level: 1,
      ability4Level: 1,
    }),
    true,
  )
}

// E7 — rfc461 health stays field-gated (unavailable blocks even with numbers)
{
  assert.equal(inferHealthKnown({ health: 800, healthMax: 1000 }), true)
  assert.equal(
    inferHealthKnown({ health: 800, healthMax: 1000, healthSource: 'unavailable' }),
    false,
  )
  assert.equal(inferHealthKnown({}), false)
}

// E8 — buildTimelineFromRfc461Jsonl emits *Known:false without combat/ranks proof
{
  const jsonl = [
    JSON.stringify({
      rfc461Schema: 'game_info',
      gameID: 2970110,
      gameVersion: '16.13',
      participants: [
        {
          participantID: 1,
          summonerName: 'A',
          championName: 'Gnar',
          teamID: 100,
          role: 'TOP',
        },
      ],
    }),
    JSON.stringify({
      rfc461Schema: 'stats_update',
      gameTime: 1000,
      participants: [
        {
          participantID: 1,
          championName: 'Gnar',
          teamID: 100,
          level: 6,
          alive: true,
          position: { x: 1000, z: 1000 },
          // no health / combat / ranks fields or sources
        },
      ],
    }),
  ].join('\n')

  const tl = buildTimelineFromRfc461Jsonl(jsonl, { id: 'r16-failclosed' }) as {
    frames: Array<{ units: Array<Record<string, unknown>> }>
  }
  const u = tl.frames[0].units[0]
  assert.equal(u.hpKnown, false)
  assert.equal(u.combatStatsKnown, false)
  assert.equal(u.abilityRanksKnown, false)
}

console.log('knownFlags.failClosed: ok (E1–E8)')