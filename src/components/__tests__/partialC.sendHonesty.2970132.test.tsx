/**
 * R12 / Cycle6 — Send honesty e2e (2970132-g1 Path1 living_post_seed).
 *
 * Proves product Send/import opens for living units with
 * hpKnown+combatStatsKnown+abilityRanksKnown on path1-final,
 * and fail-closes when sparse-frame units (pre-combat-seed / pre-HP-seed)
 * are included. Jayce is triple-known after Path1 hold-forward — sparse
 * combat still blocks at early frames (e.g. t=131).
 *
 * Match-level calculatorReady (living_post_seed_v1) is not the Send switch;
 * per-unit known flags still gate Send.
 */
import assert from 'node:assert/strict'
import { readFileSync, existsSync } from 'node:fs'
import { resolve } from 'node:path'
import { createServer } from 'vite'
import {
  abilityRanksAreKnown,
  combatStatsAreKnown,
  hpIsKnown,
  unitToLoadout,
  type TimelineUnitFrame,
} from '../../game/timeline'
import { productSendAttachedResearchActions } from '../../game/researchActionOverlay'

const ROOT = resolve(import.meta.dirname, '../../..')
const TIMELINE = resolve(
  ROOT,
  'artifacts/rofl/2970132/timeline.g1.path1-final.json',
)

/** Champions with ≥1 living triple-known snapshot on Path1 final. */
const TRIPLE = [
  'Trundle',
  'JarvanIV',
  'Olaf',
  'Galio',
  'Shen',
  'Camille',
  'Seraphine',
  'Jayce',
  'Ziggs',
  'Orianna',
] as const

/** Same-frame 1v1 Send example (both sides triple-known). */
const EXAMPLE_FRAME_T = 112_005

type AuditUnit = {
  champ: string
  name: string
  team: 100 | 200
  pid: number
  t: number
  hpKnown: boolean
  combatStatsKnown: boolean
  abilityRanksKnown: boolean
  alive: boolean
  hp: number
  hpMax: number
  ad: number
  ap: number
  armor: number
  mr: number
  as: number
  q: number
  w: number
  e: number
  r: number
  level: number
}

function teamSide(team: 100 | 200): 'blue' | 'red' {
  return team === 100 ? 'blue' : 'red'
}

function loadTimeline() {
  assert.equal(existsSync(TIMELINE), true, `missing ${TIMELINE}`)
  return JSON.parse(readFileSync(TIMELINE, 'utf8')) as {
    frames: Array<{ t: number; units: TimelineUnitFrame[] }>
    provenance?: { calculatorReady?: boolean; combatStatsKnownWouldEmit?: boolean }
  }
}

function loadTripleSnaps(): Record<string, AuditUnit> {
  const tl = loadTimeline()
  assert.equal(tl.provenance?.calculatorReady, true)
  assert.equal(tl.provenance?.calculatorReadyPolicy, 'living_post_seed_v1')
  const snaps: Record<string, AuditUnit> = {}
  for (const fr of tl.frames) {
    for (const u of fr.units) {
      const champ = u.champ
      if (!TRIPLE.includes(champ as (typeof TRIPLE)[number])) continue
      if (snaps[champ]) continue
      if (
        u.alive !== false &&
        u.hpKnown === true &&
        u.combatStatsKnown === true &&
        u.abilityRanksKnown === true
      ) {
        snaps[champ] = auditFromUnit(fr.t, u)
      }
    }
  }
  return snaps
}

function auditFromUnit(t: number, u: TimelineUnitFrame): AuditUnit {
  return {
    champ: u.champ,
    name: u.name,
    team: u.team as 100 | 200,
    pid: u.pid,
    t,
    hpKnown: u.hpKnown === true,
    combatStatsKnown: u.combatStatsKnown === true,
    abilityRanksKnown: u.abilityRanksKnown === true,
    alive: u.alive !== false,
    hp: u.hp,
    hpMax: u.hpMax,
    ad: u.ad,
    ap: u.ap,
    armor: u.armor,
    mr: u.mr,
    as: u.as,
    q: u.q,
    w: u.w,
    e: u.e,
    r: u.r,
    level: u.level,
  }
}

function loadAtFrame(champ: string, frameT: number): AuditUnit {
  const tl = loadTimeline()
  for (const fr of tl.frames) {
    if (fr.t !== frameT) continue
    for (const u of fr.units) {
      if (u.champ === champ) return auditFromUnit(fr.t, u)
    }
  }
  throw new Error(`no ${champ} at t=${frameT}`)
}

function loadJayceSparseCombat(): AuditUnit {
  const u = loadAtFrame('Jayce', 131)
  assert.equal(u.hpKnown, true)
  assert.equal(u.combatStatsKnown, false)
  return u
}

/** Path1 HP hold leaves only early Olaf pre-seed living HP-unknown. */
function loadOlafSparseHp(): AuditUnit {
  const u = loadAtFrame('Olaf', 131)
  assert.equal(u.hpKnown, false)
  assert.equal(u.alive, true)
  return u
}

function loadJarvanSparseCombat(): AuditUnit {
  const u = loadAtFrame('JarvanIV', 131)
  assert.equal(u.hpKnown, true)
  assert.equal(u.combatStatsKnown, false)
  return u
}

function toSendUnit(u: AuditUnit) {
  return {
    loadout: { championId: u.champ, hpPct: u.hpMax > 0 ? u.hp / u.hpMax : undefined },
    team: teamSide(u.team),
    alive: u.alive,
    hpKnown: u.hpKnown,
    combatStatsKnown: u.combatStatsKnown,
    abilityRanksKnown: u.abilityRanksKnown,
    hpPct: u.hpMax > 0 ? u.hp / u.hpMax : undefined,
  }
}

function toTimelineUnit(u: AuditUnit): TimelineUnitFrame {
  return {
    pid: u.pid,
    champ: u.champ,
    name: u.name,
    team: u.team,
    role: 'Unknown',
    level: u.level,
    hp: u.hp,
    hpMax: u.hpMax,
    alive: u.alive,
    ad: u.ad,
    ap: u.ap,
    armor: u.armor,
    mr: u.mr,
    as: u.as,
    x: 0.5,
    y: 0.5,
    items: [],
    q: u.q,
    w: u.w,
    e: u.e,
    r: u.r,
    hpKnown: u.hpKnown,
    combatStatsKnown: u.combatStatsKnown,
    abilityRanksKnown: u.abilityRanksKnown,
  }
}

const vite = await createServer({
  server: { middlewareMode: true },
  appType: 'custom',
  logLevel: 'silent',
})

const results: Array<{ id: string; ok: boolean; note: string }> = []
function exp(id: string, note: string, fn: () => void) {
  try {
    fn()
    results.push({ id, ok: true, note })
    console.log(`${id} PASS — ${note}`)
  } catch (err) {
    results.push({ id, ok: false, note: `${note}: ${err}` })
    console.error(`${id} FAIL — ${note}: ${err}`)
    throw err
  }
}

try {
  const {
    buildLivingSendImport,
    calculatorTrustBlockReason,
    selectedCombatTrustGap,
    selectedLacksKnownCombatState,
  } = (await vite.ssrLoadModule(
    '/src/components/GameReview.tsx',
  )) as typeof import('../GameReview')

  const tripleSnaps = loadTripleSnaps()
  const exampleJarvan = loadAtFrame('JarvanIV', EXAMPLE_FRAME_T)
  const exampleTrundle = loadAtFrame('Trundle', EXAMPLE_FRAME_T)
  const jayceSparseCombat = loadJayceSparseCombat()
  const olafSparseHp = loadOlafSparseHp()
  const jarvanSparseCombat = loadJarvanSparseCombat()

  exp('E1', '10 triple-known champions have living snapshots (Path1)', () => {
    assert.deepEqual(Object.keys(tripleSnaps).sort(), [...TRIPLE].sort())
    for (const champ of TRIPLE) {
      const u = tripleSnaps[champ]!
      assert.equal(hpIsKnown(u), true)
      assert.equal(combatStatsAreKnown(u), true)
      assert.equal(abilityRanksAreKnown(u), true)
    }
  })

  exp('E2', 'Jayce has living triple-known frames; pre-seed combat still sparse', () => {
    assert.ok(tripleSnaps.Jayce, 'Jayce triple snap missing')
    assert.equal(jayceSparseCombat.hpKnown, true)
    assert.equal(jayceSparseCombat.combatStatsKnown, false)
  })

  exp('E3', 'same-frame triple 1v1 Send opens (JarvanIV vs Trundle t=112005)', () => {
    assert.equal(exampleJarvan.t, EXAMPLE_FRAME_T)
    assert.equal(exampleTrundle.t, EXAMPLE_FRAME_T)
    const selected = [toSendUnit(exampleJarvan), toSendUnit(exampleTrundle)]
    const parity = buildLivingSendImport(selected)
    assert.equal(parity.canSend, true)
    assert.equal(parity.lacksKnownCombatState, false)
    assert.equal(parity.trustGap, null)
    assert.equal(selectedLacksKnownCombatState(selected), false)
    const block = calculatorTrustBlockReason({
      research: false,
      positionBlocked: false,
      combatStateBlocked: parity.lacksKnownCombatState,
      missingFieldLabel: parity.trustGap,
    })
    assert.equal(block, null)
  })

  exp('E4', 'multi triple-known selection Send opens (≥2 per side when available)', () => {
    const selected = [
      toSendUnit(tripleSnaps.Galio!),
      toSendUnit(tripleSnaps.JarvanIV!),
      toSendUnit(tripleSnaps.Olaf!),
      toSendUnit(tripleSnaps.Trundle!),
      toSendUnit(tripleSnaps.Camille!),
      toSendUnit(tripleSnaps.Ziggs!),
    ]
    const parity = buildLivingSendImport(selected)
    assert.equal(parity.canSend, true)
    assert.equal(parity.lacksKnownCombatState, false)
    assert.equal(parity.blue.length, 3)
    assert.equal(parity.red.length, 3)
    assert.equal(parity.trustGap, null)
  })

  exp('E5', 'including Jayce (combat unknown) blocks Send', () => {
    const selected = [
      toSendUnit(exampleJarvan),
      toSendUnit(exampleTrundle),
      toSendUnit(jayceSparseCombat),
    ]
    const parity = buildLivingSendImport(selected)
    assert.equal(parity.canSend, true)
    assert.equal(parity.lacksKnownCombatState, true)
    assert.equal(selectedCombatTrustGap(selected), 'Jayce combat stats')
    const reason =
      calculatorTrustBlockReason({
        research: false,
        positionBlocked: false,
        combatStateBlocked: true,
        missingFieldLabel: parity.trustGap,
      }) ?? ''
    assert.match(reason, /Jayce combat stats/)
    assert.doesNotMatch(reason, /win\s*%|odds\s*%|probability/i)
  })

  exp('E6', 'including Olaf (HP unknown) or Jarvan sparse combat blocks Send', () => {
    for (const [label, sparse] of [
      ['Olaf HP', olafSparseHp],
      ['JarvanIV combat stats', jarvanSparseCombat],
    ] as const) {
      const selected = [
        toSendUnit(tripleSnaps.Galio!),
        toSendUnit(tripleSnaps.Trundle!),
        toSendUnit(sparse),
      ]
      const parity = buildLivingSendImport(selected)
      assert.equal(parity.lacksKnownCombatState, true, label)
      assert.equal(parity.trustGap, label, label)
    }
  })

  exp('E7', 'unitToLoadout imports combat pins for triple-known; omits sparse Jayce', () => {
    const knownLoad = unitToLoadout(toTimelineUnit(tripleSnaps.Galio!))
    assert.ok(knownLoad.liveStats?.ad != null && knownLoad.liveStats.ad > 0)
    assert.ok(knownLoad.ranks != null)
    const sparseLoad = unitToLoadout(toTimelineUnit(jayceSparseCombat))
    assert.equal(sparseLoad.liveStats?.ad, undefined)
    assert.equal(sparseLoad.liveStats?.armor, undefined)
    if (jayceSparseCombat.hpKnown) {
      assert.ok(sparseLoad.liveStats?.hp != null)
    }
  })

  exp('E8', 'match-level calculatorReady true is not the Send switch', () => {
    const tl = loadTimeline()
    assert.equal(tl.provenance?.calculatorReady, true)
    assert.equal(tl.provenance?.calculatorReadyPolicy, 'living_post_seed_v1')
    // Sparse unit still blocks even when match-level ready is true.
    const withSparse = [
      toSendUnit(exampleJarvan),
      toSendUnit(exampleTrundle),
      toSendUnit(jayceSparseCombat),
    ]
    const blocked = buildLivingSendImport(withSparse)
    assert.equal(blocked.lacksKnownCombatState, true)
    const open = buildLivingSendImport([
      toSendUnit(exampleJarvan),
      toSendUnit(exampleTrundle),
    ])
    assert.equal(open.canSend, true)
    assert.equal(open.lacksKnownCombatState, false)
  })

  exp('E9', 'research AA overlay does not attach to product Send', () => {
    const selected = [toSendUnit(exampleJarvan), toSendUnit(exampleTrundle)]
    const fakeRows = [
      {
        kind: 'basic_attack' as const,
        tSec: 112,
        tMs: 112_000,
        sourceNetId: 1,
        sourceChampion: 'Jayce',
        targetNetId: 2,
        targetChampion: 'Trundle',
        amount: 40,
        researchOnly: true as const,
        calculatorReady: false as const,
      },
    ]
    const parity = buildLivingSendImport(selected, fakeRows)
    assert.deepEqual(parity.attachedResearchActions, [])
    assert.deepEqual(productSendAttachedResearchActions(fakeRows), [])
    assert.equal(parity.lacksKnownCombatState, false)
  })

  exp('E10', 'sendFight disabled when calculatorBlocked (sparse unit)', () => {
    const selected = [
      toSendUnit(exampleJarvan),
      toSendUnit(exampleTrundle),
      toSendUnit(jayceSparseCombat),
    ]
    const parity = buildLivingSendImport(selected)
    const calculatorBlocked =
      calculatorTrustBlockReason({
        research: false,
        positionBlocked: false,
        combatStateBlocked: parity.lacksKnownCombatState,
        missingFieldLabel: parity.trustGap,
      }) !== null
    const sendEnabled = parity.canSend && !calculatorBlocked
    assert.equal(sendEnabled, false)
  })
} finally {
  await vite.close()
}

const failed = results.filter((r) => !r.ok)
const summary = {
  suite: 'partialC.sendHonesty.2970132',
  match: '2970132-g1',
  timeline: 'artifacts/rofl/2970132/timeline.g1.path1-final.json',
  passed: results.filter((r) => r.ok).length,
  failed: failed.length,
  results,
  send_opens_on_triple_known:
    results.some((r) => r.id === 'E3' && r.ok) &&
    results.some((r) => r.id === 'E4' && r.ok),
  send_blocks_on_sparse:
    results.some((r) => r.id === 'E5' && r.ok) &&
    results.some((r) => r.id === 'E6' && r.ok),
  example_frame_t: EXAMPLE_FRAME_T,
  example_units: ['JarvanIV', 'Trundle'],
  calculatorReady: true,
  calculatorReadyPolicy: 'living_post_seed_v1',
}

console.log(JSON.stringify(summary, null, 2))

if (failed.length) {
  process.exit(1)
}
console.log('partialC.sendHonesty.2970132: ok (E1–E10)')
