/**
 * P4 T1 / R10 — Product timeline AA/damage schema + parse experiments.
 * Never invent from HPΔ. Order-only pid rejected. skillUsed coexistence.
 */
import assert from 'node:assert/strict'
import { parseGameTimelineJson, type GameTimeline } from '../timeline'

function baseTimeline(extra: Partial<GameTimeline> = {}): GameTimeline {
  return {
    id: 'r10-aa-schema',
    name: 'R10 AA schema',
    patch: '16.14',
    source: 'test',
    participants: [
      {
        participantID: 1,
        summonerName: 'a',
        championName: 'Gnar',
        teamID: 100,
        role: 'Top',
      },
    ],
    frameCount: 1,
    durationMs: 1000,
    frames: [
      {
        t: 0,
        units: [
          {
            pid: 1,
            champ: 'Gnar',
            name: 'a',
            team: 100,
            role: 'Top',
            level: 1,
            hp: 0,
            hpMax: 0,
            alive: true,
            hpKnown: false,
            combatStatsKnown: false,
            abilityRanksKnown: false,
            ad: 0,
            ap: 0,
            armor: 0,
            mr: 0,
            as: 100,
            x: 0.1,
            y: 0.1,
            items: [],
            q: 0,
            w: 0,
            e: 0,
            r: 0,
          },
        ],
      },
    ],
    ...extra,
  }
}

const results: Array<{ id: string; ok: boolean; note: string }> = []

function exp(id: string, fn: () => void, note: string) {
  try {
    fn()
    results.push({ id, ok: true, note })
  } catch (err) {
    results.push({
      id,
      ok: false,
      note: `${note} :: ${(err as Error).message}`,
    })
    throw err
  }
}

// E1 — missing AA/damage arrays OK (unknown stays absent)
exp('E1_missing_ok', () => {
  const tl = parseGameTimelineJson(JSON.stringify(baseTimeline()))
  assert.equal(tl.basicAttack, undefined)
  assert.equal(tl.damageDealt, undefined)
  assert.equal(tl.actionEvents, undefined)
}, 'missing events parse OK')

// E2 — valid identity-bound basicAttack accepted
exp('E2_basic_attack_accept', () => {
  const tl = parseGameTimelineJson(
    JSON.stringify(
      baseTimeline({
        basicAttack: [
          {
            tMs: 39520,
            participantId: 8,
            netId: 1073742005,
            sourceKind: 'rofl_packet_r41',
            researchOnly: true,
          },
        ],
      }),
    ),
  )
  assert.equal(tl.basicAttack?.length, 1)
  assert.equal(tl.basicAttack?.[0].netId, 1073742005)
}, 'identity-bound basicAttack accepted')

// E3 — order-only pid (no netId) rejected
exp('E3_order_only_reject', () => {
  assert.throws(
    () =>
      parseGameTimelineJson(
        JSON.stringify({
          ...baseTimeline(),
          basicAttack: [{ tMs: 1000, participantId: 1 }],
        }),
      ),
    /order-only pid/,
  )
}, 'participantId without netId rejected')

// E4 — damage_dealt with PE amount accepted; amount optional
exp('E4_damage_amount', () => {
  const withAmt = parseGameTimelineJson(
    JSON.stringify(
      baseTimeline({
        damageDealt: [
          {
            tMs: 40221,
            participantId: 8,
            netId: 1073742005,
            targetNetId: 1073742417,
            amount: 1,
            sourceKind: 'rofl_packet_r41',
          },
        ],
      }),
    ),
  )
  assert.equal(withAmt.damageDealt?.[0].amount, 1)
  const noAmt = parseGameTimelineJson(
    JSON.stringify(
      baseTimeline({
        damageDealt: [
          {
            tMs: 40221,
            participantId: 8,
            netId: 1073742005,
          },
        ],
      }),
    ),
  )
  assert.equal(noAmt.damageDealt?.[0].amount, undefined)
}, 'damage amount optional; never required invent')

// E5 — skillUsed coexistence (parallel channel; not collapsed)
exp('E5_skillUsed_coexist', () => {
  const tl = parseGameTimelineJson(
    JSON.stringify(
      baseTimeline({
        skillUsed: [{ tMs: 5000, participantId: 1, skillSlot: 2 }],
        basicAttack: [
          { tMs: 5100, participantId: 1, netId: 1073741998 },
        ],
        damageDealt: [
          { tMs: 5200, participantId: 1, netId: 1073741998, amount: 50 },
        ],
      }),
    ),
  )
  assert.equal(tl.skillUsed?.length, 1)
  assert.equal(tl.skillUsed?.[0].skillSlot, 2)
  assert.equal(tl.basicAttack?.length, 1)
  assert.equal(tl.damageDealt?.length, 1)
}, 'skillUsed parallel; AA/damage not collapsed')

// E6 — unified actionEvents kind discriminant
exp('E6_actionEvents_kind', () => {
  const tl = parseGameTimelineJson(
    JSON.stringify(
      baseTimeline({
        actionEvents: [
          { kind: 'basic_attack', tMs: 1, participantId: 1, netId: 99 },
          {
            kind: 'damage_dealt',
            tMs: 2,
            participantId: 1,
            netId: 99,
            amount: 3,
          },
        ],
      }),
    ),
  )
  assert.equal(tl.actionEvents?.length, 2)
  assert.throws(
    () =>
      parseGameTimelineJson(
        JSON.stringify({
          ...baseTimeline(),
          actionEvents: [
            { kind: 'skill_used', tMs: 1, participantId: 1, netId: 99 },
          ],
        }),
      ),
    /kind must be/,
  )
}, 'actionEvents kind gate; skill_used not allowed')

// E7 — round-trip JSON preserves events
exp('E7_round_trip', () => {
  const original = baseTimeline({
    provenance: {
      aaCoverage: 'research_overlay',
      damageCoverage: 'research_overlay',
    },
    basicAttack: [{ tMs: 10, participantId: 2, netId: 42 }],
    damageDealt: [{ tMs: 11, participantId: 2, netId: 42, amount: 7 }],
  })
  const parsed = parseGameTimelineJson(JSON.stringify(original))
  assert.deepEqual(parsed.basicAttack, original.basicAttack)
  assert.deepEqual(parsed.damageDealt, original.damageDealt)
  assert.equal(parsed.provenance?.aaCoverage, 'research_overlay')
}, 'round-trip parse preserves AA/damage + provenance')

// E8 — empty arrays allowed (explicit none) vs missing (unknown)
exp('E8_empty_array_ok', () => {
  const tl = parseGameTimelineJson(
    JSON.stringify(baseTimeline({ basicAttack: [], damageDealt: [] })),
  )
  assert.deepEqual(tl.basicAttack, [])
  assert.deepEqual(tl.damageDealt, [])
}, 'empty arrays parse (explicit none)')

console.log(
  JSON.stringify(
    {
      suite: 'timeline.aaDamage.schema',
      researcher: 'R10',
      track: 'P4-T1',
      passed: results.filter((r) => r.ok).length,
      total: results.length,
      results,
    },
    null,
    2,
  ),
)
console.log('timeline aaDamage schema tests: ok')
