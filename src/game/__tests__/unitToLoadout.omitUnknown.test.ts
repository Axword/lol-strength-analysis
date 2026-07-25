/**
 * P6 H3 — unitToLoadout omit unknowns (no fake QWER=0 / abilityRank:1).
 * Product calculatorReady G_send.no_fake_zero_loadout.
 */
import assert from 'node:assert/strict'
import {
  abilityRanksAreKnown,
  combatStatsAreKnown,
  hpIsKnown,
  loadoutHasProvenRanks,
  loadoutLooksLikeFakeZeroRanks,
  unitToLoadout,
  type TimelineUnitFrame,
} from '../timeline'

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

const results: Array<{ id: string; ok: boolean; note: string }> = []

function exp(id: string, note: string, fn: () => void) {
  try {
    fn()
    results.push({ id, ok: true, note })
  } catch (err) {
    results.push({ id, ok: false, note: `${note}: ${err}` })
    throw err
  }
}

// E1 — Reproduce pre-fix shape is the fake-zero detector target
exp('E1', 'fake-zero detector matches QWER=0 + abilityRank:1', () => {
  assert.equal(
    loadoutLooksLikeFakeZeroRanks({ ranks: { Q: 0, W: 0, E: 0, R: 0 }, abilityRank: 1 }),
    true,
  )
  assert.equal(
    loadoutLooksLikeFakeZeroRanks({ ranks: { Q: 3, W: 1, E: 1, R: 1 }, abilityRank: 3 }),
    false,
  )
})

// E2 — abilityRanksKnown undefined ⇒ omit ranks + abilityRank
exp('E2', 'undefined abilityRanksKnown omits ranks and abilityRank', () => {
  const loadout = unitToLoadout(
    baseUnit({ abilityRanksKnown: undefined, hpKnown: true, combatStatsKnown: true }),
  )
  assert.equal(loadout.ranks, undefined)
  assert.equal(loadout.abilityRank, undefined)
  assert.equal(loadoutHasProvenRanks(loadout), false)
  assert.equal(loadoutLooksLikeFakeZeroRanks(loadout), false)
})

// E3 — abilityRanksKnown false ⇒ omit (same as undefined)
exp('E3', 'explicit false abilityRanksKnown omits ranks', () => {
  const loadout = unitToLoadout(
    baseUnit({ abilityRanksKnown: false, hpKnown: true, combatStatsKnown: true }),
  )
  assert.equal(loadout.ranks, undefined)
  assert.equal(loadout.abilityRank, undefined)
  assert.equal(abilityRanksAreKnown({ abilityRanksKnown: false }), false)
})

// E4 — known ranks emit real QWER (not zeros, not omitted)
exp('E4', 'abilityRanksKnown true emits frame ranks', () => {
  const loadout = unitToLoadout(
    baseUnit({
      abilityRanksKnown: true,
      hpKnown: true,
      combatStatsKnown: true,
      q: 3,
      w: 1,
      e: 2,
      r: 1,
    }),
  )
  assert.deepEqual(loadout.ranks, { Q: 3, W: 1, E: 2, R: 1 })
  assert.equal(loadout.abilityRank, 3)
  assert.equal(loadoutHasProvenRanks(loadout), true)
  assert.equal(loadoutLooksLikeFakeZeroRanks(loadout), false)
})

// E5 — combatStatsKnown false/absent ⇒ no AD/AP/armor/MR/AS liveStats
exp('E5', 'unknown combat omits combat liveStats', () => {
  const absent = unitToLoadout(
    baseUnit({ combatStatsKnown: undefined, hpKnown: true, abilityRanksKnown: true }),
  )
  assert.equal(absent.liveStats?.ad, undefined)
  assert.equal(absent.liveStats?.armor, undefined)
  assert.equal(absent.liveStats?.hp, 800)

  const explicit = unitToLoadout(
    baseUnit({ combatStatsKnown: false, hpKnown: true, abilityRanksKnown: true }),
  )
  assert.equal(explicit.liveStats?.ad, undefined)
  assert.equal(combatStatsAreKnown({ combatStatsKnown: false }), false)
})

// E6 — combat known attaches live combat pins
exp('E6', 'combatStatsKnown true attaches AD/armor pins', () => {
  const loadout = unitToLoadout(
    baseUnit({ combatStatsKnown: true, hpKnown: true, abilityRanksKnown: true, ad: 155, armor: 55 }),
  )
  assert.equal(loadout.liveStats?.ad, 155)
  assert.equal(loadout.liveStats?.armor, 55)
})

// E7 — hpKnown false/absent ⇒ no hpPct / liveStats.hp
exp('E7', 'unknown HP omits hpPct and liveStats.hp', () => {
  const loadout = unitToLoadout(
    baseUnit({ hpKnown: undefined, combatStatsKnown: true, abilityRanksKnown: true }),
  )
  assert.equal(loadout.hpPct, undefined)
  assert.equal(loadout.liveStats?.hp, undefined)
  assert.equal(hpIsKnown({ hpKnown: undefined }), false)
})

// E8 — all three unknown ⇒ empty overrides (no fake kit)
exp('E8', 'all unknown ⇒ no ranks, no combat, no hp', () => {
  const loadout = unitToLoadout(
    baseUnit({ hpKnown: false, combatStatsKnown: false, abilityRanksKnown: false }),
  )
  assert.equal(loadout.ranks, undefined)
  assert.equal(loadout.abilityRank, undefined)
  assert.equal(loadout.liveStats, undefined)
  assert.equal(loadout.hpPct, undefined)
  assert.equal(loadoutLooksLikeFakeZeroRanks(loadout), false)
})

// E9 — known path with legitimate all-zero ranks (level-1 unranked) still allowed when known
exp('E9', 'proven zero ranks ok when abilityRanksKnown true', () => {
  const loadout = unitToLoadout(
    baseUnit({
      abilityRanksKnown: true,
      hpKnown: true,
      combatStatsKnown: true,
      q: 0,
      w: 0,
      e: 0,
      r: 0,
      level: 1,
    }),
  )
  assert.deepEqual(loadout.ranks, { Q: 0, W: 0, E: 0, R: 0 })
  // abilityRank floor is Math.max(1, ...) — documented when ranks known
  assert.equal(loadout.abilityRank, 1)
  assert.equal(loadoutHasProvenRanks(loadout), true)
})

// E10 — Send still blocked upstream when living ranks unknown (R16/R17 KEEP)
exp('E10', 'living unknown ranks still fails known-flag helpers', () => {
  const living = {
    hpKnown: true,
    combatStatsKnown: true,
    abilityRanksKnown: false as boolean | undefined,
  }
  const lacks =
    !hpIsKnown(living) || !combatStatsAreKnown(living) || !abilityRanksAreKnown(living)
  assert.equal(lacks, true)
  // And the loadout built from that unit is not a fake-zero kit
  const loadout = unitToLoadout(baseUnit(living))
  assert.equal(loadoutLooksLikeFakeZeroRanks(loadout), false)
  assert.equal(loadout.ranks, undefined)
})

// E11 — no wiki kit substitution: omitted ranks ≠ invented Meraki ranks
exp('E11', 'omit path does not substitute wiki/default ranks object', () => {
  const loadout = unitToLoadout(baseUnit({ abilityRanksKnown: false, q: 5, w: 5, e: 5, r: 3 }))
  assert.equal(loadout.ranks, undefined)
  assert.notDeepEqual(loadout.ranks, { Q: 5, W: 5, E: 5, R: 3 })
  assert.notDeepEqual(loadout.ranks, { Q: 3, W: 1, E: 1, R: 1 })
})

// E12 — JSON serialisation of unknown loadout has no ranks key / no abilityRank key
exp('E12', 'serialized unknown loadout has no ranks/abilityRank keys', () => {
  const loadout = unitToLoadout(baseUnit({ abilityRanksKnown: undefined }))
  const json = JSON.stringify(loadout)
  const parsed = JSON.parse(json) as Record<string, unknown>
  assert.equal('ranks' in parsed, false)
  assert.equal('abilityRank' in parsed, false)
  assert.equal(parsed.level, 6)
})

console.log(
  `unitToLoadout.omitUnknown: ok (${results.map((r) => r.id).join(', ')})`,
)
