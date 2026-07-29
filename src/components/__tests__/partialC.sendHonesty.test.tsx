/**
 * R12 follow-up — partial C Send honesty e2e (2970110-g1).
 *
 * Proves product Send/import opens for living FUR-complete units with
 * hpKnown+combatStatsKnown+abilityRanksKnown, and fail-closes when
 * Camille/Jhin/Leona (combatStatsKnown=false) are included.
 *
 * Match-level calculatorReady stays false — not the Send switch.
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
const TIMELINE = resolve(ROOT, 'artifacts/rofl/2970110/timeline.g1.product-fuse.json')

const FUR = [
  'Ambessa',
  'LeeSin',
  'Syndra',
  'Gnar',
  'Naafiri',
  'Cassiopeia',
  'Ezreal',
] as const
const TAIL = ['Camille', 'Jhin', 'Leona'] as const

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

function loadTripleSnaps(): Record<string, AuditUnit> {
  assert.equal(existsSync(TIMELINE), true, `missing ${TIMELINE}`)
  const tl = JSON.parse(readFileSync(TIMELINE, 'utf8')) as {
    frames: Array<{ t: number; units: TimelineUnitFrame[] }>
    provenance?: { calculatorReady?: boolean }
  }
  assert.equal(tl.provenance?.calculatorReady === true, false)
  const snaps: Record<string, AuditUnit> = {}
  for (const fr of tl.frames) {
    for (const u of fr.units) {
      const champ = u.champ
      if (!FUR.includes(champ as (typeof FUR)[number])) continue
      if (snaps[champ]) continue
      if (
        u.alive !== false &&
        u.hpKnown === true &&
        u.combatStatsKnown === true &&
        u.abilityRanksKnown === true
      ) {
        snaps[champ] = {
          champ,
          name: u.name,
          team: u.team as 100 | 200,
          pid: u.pid,
          t: fr.t,
          hpKnown: true,
          combatStatsKnown: true,
          abilityRanksKnown: true,
          alive: true,
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
    }
  }
  return snaps
}

function loadTailUnknownCombat(): Record<string, AuditUnit> {
  const tl = JSON.parse(readFileSync(TIMELINE, 'utf8')) as {
    frames: Array<{ t: number; units: TimelineUnitFrame[] }>
  }
  const out: Record<string, AuditUnit> = {}
  for (const fr of tl.frames) {
    for (const u of fr.units) {
      const champ = u.champ
      if (!TAIL.includes(champ as (typeof TAIL)[number])) continue
      if (out[champ]) continue
      // Prefer a frame where HP is known but combat is not — honesty case.
      if (u.hpKnown === true && u.combatStatsKnown !== true && u.abilityRanksKnown === true) {
        out[champ] = {
          champ,
          name: u.name,
          team: u.team as 100 | 200,
          pid: u.pid,
          t: fr.t,
          hpKnown: true,
          combatStatsKnown: false,
          abilityRanksKnown: true,
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
    }
  }
  // Fallback: any living frame with combat unknown
  for (const fr of tl.frames) {
    for (const u of fr.units) {
      const champ = u.champ
      if (!TAIL.includes(champ as (typeof TAIL)[number])) continue
      if (out[champ]) continue
      if (u.combatStatsKnown === true) {
        throw new Error(`${champ} unexpectedly combatStatsKnown=true`)
      }
      out[champ] = {
        champ,
        name: u.name,
        team: u.team as 100 | 200,
        pid: u.pid,
        t: fr.t,
        hpKnown: u.hpKnown === true,
        combatStatsKnown: false,
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
  }
  return out
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

  const furSnaps = loadTripleSnaps()
  const tailSnaps = loadTailUnknownCombat()

  exp('E1', 'all 7 FUR heroes have ≥1 triple-known living snapshot', () => {
    assert.deepEqual(Object.keys(furSnaps).sort(), [...FUR].sort())
    for (const champ of FUR) {
      const u = furSnaps[champ]!
      assert.equal(hpIsKnown(u), true)
      assert.equal(combatStatsAreKnown(u), true)
      assert.equal(abilityRanksAreKnown(u), true)
    }
  })

  exp('E2', 'Camille/Jhin/Leona never combatStatsKnown on fused timeline', () => {
    const tl = JSON.parse(readFileSync(TIMELINE, 'utf8')) as {
      frames: Array<{ units: Array<{ champ: string; combatStatsKnown?: boolean }> }>
    }
    for (const fr of tl.frames) {
      for (const u of fr.units) {
        if (TAIL.includes(u.champ as (typeof TAIL)[number])) {
          assert.equal(u.combatStatsKnown === true, false, u.champ)
        }
      }
    }
    assert.deepEqual(Object.keys(tailSnaps).sort(), [...TAIL].sort())
  })

  exp('E3', 'known-only FUR 1v1 Send opens (Syndra vs Gnar)', () => {
    const selected = [toSendUnit(furSnaps.Syndra!), toSendUnit(furSnaps.Gnar!)]
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

  exp('E4', 'known-only multi FUR selection Send opens (≥2 per side)', () => {
    const selected = [
      toSendUnit(furSnaps.Ambessa!),
      toSendUnit(furSnaps.LeeSin!),
      toSendUnit(furSnaps.Syndra!),
      toSendUnit(furSnaps.Gnar!),
      toSendUnit(furSnaps.Naafiri!),
      toSendUnit(furSnaps.Cassiopeia!),
      toSendUnit(furSnaps.Ezreal!),
    ]
    const parity = buildLivingSendImport(selected)
    assert.equal(parity.canSend, true)
    assert.equal(parity.lacksKnownCombatState, false)
    assert.equal(parity.blue.length, 3)
    assert.equal(parity.red.length, 4)
    assert.equal(parity.trustGap, null)
  })

  exp('E5', 'including Camille blocks Send (combat stats gap)', () => {
    const selected = [
      toSendUnit(furSnaps.Syndra!),
      toSendUnit(furSnaps.Gnar!),
      toSendUnit(tailSnaps.Camille!),
    ]
    const parity = buildLivingSendImport(selected)
    assert.equal(parity.canSend, true) // ≥1 per team still true
    assert.equal(parity.lacksKnownCombatState, true)
    assert.equal(selectedCombatTrustGap(selected), 'Camille combat stats')
    const reason =
      calculatorTrustBlockReason({
        research: false,
        positionBlocked: false,
        combatStateBlocked: true,
        missingFieldLabel: parity.trustGap,
      }) ?? ''
    assert.match(reason, /Camille combat stats/)
    assert.doesNotMatch(reason, /win\s*%|odds\s*%|probability/i)
  })

  exp('E6', 'including Jhin or Leona blocks Send', () => {
    for (const tail of ['Jhin', 'Leona'] as const) {
      const selected = [
        toSendUnit(furSnaps.Ambessa!),
        toSendUnit(furSnaps.Ezreal!),
        toSendUnit(tailSnaps[tail]!),
      ]
      const parity = buildLivingSendImport(selected)
      assert.equal(parity.lacksKnownCombatState, true, tail)
      assert.equal(parity.trustGap, `${tail} combat stats`, tail)
    }
  })

  exp('E7', 'unitToLoadout imports combat pins for FUR known; omits for Camille', () => {
    const furLoad = unitToLoadout(toTimelineUnit(furSnaps.Syndra!))
    assert.ok(furLoad.liveStats?.ad != null && furLoad.liveStats.ad > 0)
    assert.ok(furLoad.ranks != null)
    const cam = unitToLoadout(toTimelineUnit(tailSnaps.Camille!))
    assert.equal(cam.liveStats?.ad, undefined)
    assert.equal(cam.liveStats?.armor, undefined)
    // HP may be known on Camille — ok to pin HP without inventing combat
    if (tailSnaps.Camille!.hpKnown) {
      assert.ok(cam.liveStats?.hp != null)
    }
  })

  exp('E8', 'match-level calculatorReady false is not the Send switch', () => {
    const tl = JSON.parse(readFileSync(TIMELINE, 'utf8')) as {
      provenance?: { calculatorReady?: boolean; combatStatsKnownWouldEmit?: boolean }
    }
    assert.equal(tl.provenance?.calculatorReady === true, false)
    assert.equal(tl.provenance?.combatStatsKnownWouldEmit === true, false)
    const selected = [toSendUnit(furSnaps.LeeSin!), toSendUnit(furSnaps.Naafiri!)]
    const parity = buildLivingSendImport(selected)
    assert.equal(parity.canSend, true)
    assert.equal(parity.lacksKnownCombatState, false)
  })

  exp('E9', 'research AA overlay does not attach to product Send', () => {
    const selected = [toSendUnit(furSnaps.Syndra!), toSendUnit(furSnaps.Gnar!)]
    const fakeRows = [
      {
        kind: 'basic_attack' as const,
        tSec: 200,
        tMs: 200_000,
        sourceNetId: 1,
        sourceChampion: 'Camille',
        targetNetId: 2,
        targetChampion: 'Leona',
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

  exp('E10', 'sendFight disabled when calculatorBlocked (unknown combat)', () => {
    // Mirrors GameReview: disabled={!canSend || calculatorBlocked}
    const selected = [
      toSendUnit(furSnaps.Syndra!),
      toSendUnit(furSnaps.Gnar!),
      toSendUnit(tailSnaps.Leona!),
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
console.log(
  JSON.stringify(
    {
      suite: 'partialC.sendHonesty',
      match: '2970110-g1',
      passed: results.filter((r) => r.ok).length,
      failed: failed.length,
      results,
      send_known_only_ok: results.some((r) => r.id === 'E3' && r.ok) &&
        results.some((r) => r.id === 'E4' && r.ok),
      send_blocks_unknown: results.some((r) => r.id === 'E5' && r.ok) &&
        results.some((r) => r.id === 'E6' && r.ok),
      calculatorReady: false,
    },
    null,
    2,
  ),
)

if (failed.length) {
  process.exit(1)
}
console.log('partialC.sendHonesty: ok (E1–E10)')
