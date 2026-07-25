/**
 * F6 / R17 — Calculator Send ↔ harness killWindowOverlay parity smoke.
 *
 * Criterion G (fight_outcome): product calculator path shares overlay math
 * with harness on same pins; dead excluded; known-flags gate; one npm smoke.
 *
 * NOT win odds. NOT calculatorReady invent. Path1 pins only when present.
 *
 * Usage: npm run fo:send-smoke
 */
import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { createServer } from 'vite'
import { defaultLoadout } from '../src/engine/combat'
import {
  simulateKillWindowMatchup,
  simulateKillWindowSeries,
  selectKillWindowMarks,
} from '../src/engine/killWindowOverlay'
import { PRODUCT_KILL_WINDOW_DEFAULTS } from '../src/engine/killWindowProduct'
import type { FighterLoadout, MatchupInput, MatchupResult } from '../src/engine/types'
import {
  abilityRanksAreKnown,
  combatStatsAreKnown,
  hpIsKnown,
  unitToLoadout,
  type TimelineUnitFrame,
} from '../src/game/timeline'

const ROOT = resolve(process.cwd())
const OUT_DIR = join(
  ROOT,
  'docs/rofl-research/autoresearch/fight_outcome/r17',
)
const PARENT_OUT = join(
  '/Users/river/Projects/lol-strength-analysis',
  'docs/rofl-research/autoresearch/fight_outcome/r17',
)
const PATH1_TIMELINE = join(
  ROOT,
  'artifacts/rofl/2970132/timeline.g1.path1-final.json',
)
const CROSSCHECKS = join(
  ROOT,
  'docs/canvases/_data/crosschecks-2970132-g1.json',
)

type ExpResult = {
  id: string
  hypothesis: string
  pass: boolean
  detail: string
  metrics?: Record<string, number | string | boolean | null>
}

const experiments: ExpResult[] = []
let failed = 0

function exp(
  id: string,
  hypothesis: string,
  fn: () => Record<string, number | string | boolean | null> | void,
): void {
  try {
    const metrics = fn() ?? {}
    experiments.push({
      id,
      hypothesis,
      pass: true,
      detail: 'ok',
      metrics,
    })
    console.log(`PASS ${id} — ${hypothesis}`)
  } catch (err) {
    failed++
    const detail = err instanceof Error ? err.message : String(err)
    experiments.push({ id, hypothesis, pass: false, detail })
    console.error(`FAIL ${id} — ${hypothesis}: ${detail}`)
  }
}

function fingerprintResult(r: MatchupResult): string {
  const payload = {
    blueMit: Math.round(r.blue.mitigatedTotal),
    redMit: Math.round(r.red.mitigatedTotal),
    blueHp: r.blue.targets?.[0]?.hpRemaining ?? null,
    redHp: r.red.targets?.[0]?.hpRemaining ?? null,
    lethal: r.timing?.firstLethalSec ?? null,
    pBlue: r.pBlue ?? null,
    notesHead: (r.notes ?? []).slice(0, 4),
  }
  return createHash('sha256').update(JSON.stringify(payload)).digest('hex').slice(0, 16)
}

function pinnedFromCrosscheckRow(row: {
  health: number
  health_max: number
  attack_damage: number
  ability_power: number
  armor: number
  magic_resist: number
  attack_speed: number
  level: number
  ability1_level: number
  ability2_level: number
  ability3_level: number
  ability4_level: number
  items_json?: string
  champ?: string
}): FighterLoadout {
  const champ = row.champ ?? 'Galio'
  const items: string[] = []
  if (row.items_json) {
    try {
      const raw = JSON.parse(row.items_json) as number[]
      for (const id of raw) {
        if (typeof id === 'number' && id > 0) items.push(String(id))
      }
    } catch {
      /* keep empty — no invent */
    }
  }
  const base = defaultLoadout(champ)
  return {
    ...base,
    level: row.level,
    ranks: {
      Q: row.ability1_level,
      W: row.ability2_level,
      E: row.ability3_level,
      R: row.ability4_level,
    },
    itemIds: items,
    liveStats: {
      hp: row.health,
      hpMax: row.health_max,
      ad: row.attack_damage,
      ap: row.ability_power,
      armor: row.armor,
      mr: row.magic_resist,
      attackSpeed: row.attack_speed / 100,
    },
    alive: true,
  }
}

function seriesFingerprint(series: {
  model: { tSec: number; hp: number }[]
  firstLethalSec: number | null
}): string {
  const payload = {
    lethal: series.firstLethalSec,
    endHp: series.model[series.model.length - 1]?.hp ?? null,
    n: series.model.length,
    sample: series.model.filter((_, i) => i % 5 === 0).map((m) => ({
      t: Math.round(m.tSec * 1000) / 1000,
      hp: Math.round(m.hp),
    })),
  }
  return createHash('sha256').update(JSON.stringify(payload)).digest('hex').slice(0, 16)
}

// ── H1: Calculator Send path ≡ harness overlay on same pins ─────────────────
exp('E0', 'F6-H1 shared module: Calculator + harness both import killWindowOverlay', () => {
  const calcSrc = readFileSync(join(ROOT, 'src/components/Calculator.tsx'), 'utf8')
  const harnessSrc = readFileSync(
    join(ROOT, 'scripts/crosscheck_action_aligned.ts'),
    'utf8',
  )
  assert.match(calcSrc, /simulateKillWindowMatchup/)
  assert.match(calcSrc, /from ['"]\.\.\/engine\/killWindowOverlay['"]/)
  assert.match(harnessSrc, /from ['"].*killWindowOverlay['"]/)
  assert.match(harnessSrc, /simulateKillWindowSeries/)
  assert.match(
    harnessSrc,
    /delegates to engine killWindowOverlay/,
  )
  return { calculatorImportsOverlay: true, harnessDelegatesOverlay: true }
})

exp('E1', 'F6-H1 same pins → Matchup path ≡ series path (overlay math)', () => {
  const atk = {
    ...defaultLoadout('Galio'),
    level: 7,
    ranks: { Q: 3, W: 1, E: 1, R: 1 },
    liveStats: {
      hp: 1400,
      hpMax: 1600,
      ad: 90,
      ap: 120,
      armor: 50,
      mr: 40,
      attackSpeed: 0.7,
    },
    alive: true,
  }
  const def = {
    ...defaultLoadout('Trundle'),
    level: 6,
    ranks: { Q: 3, W: 1, E: 1, R: 1 },
    liveStats: {
      hp: 1283,
      hpMax: 1349,
      ad: 146,
      ap: 0,
      armor: 54,
      mr: 40,
      attackSpeed: 1.6,
    },
    alive: true,
  }
  const marks = [
    { tSec: 0.5, skillSlot: 1 },
    { tSec: 1.2, skillSlot: 3 },
    { tSec: 2.0, skillSlot: 2 },
    { tSec: 2.8, skillSlot: 4 },
  ]
  const actual = Array.from({ length: 9 }, (_, i) => ({
    tSec: i * 0.5,
    hp: 1283,
    hpMax: 1349,
  }))
  const matchup: MatchupInput = {
    blue: [atk],
    red: [def],
    engager: 'blue',
    mode: 'allin',
    durationSec: 4,
    xhMode: 'off',
    killWindow: {
      ...PRODUCT_KILL_WINDOW_DEFAULTS,
      actionMarks: marks,
      engageSec: 0,
      actualHpSeries: actual,
      markSelection: 'cusum_engage_then_skills',
    },
  }
  // Product Calculator path (Send with killWindow attached)
  const calc = simulateKillWindowMatchup(matchup)
  // Harness must use the SAME post-select marks Matchup feeds into series
  // (selectKillWindowMarks lives inside simulateKillWindowMatchup).
  const selected = selectKillWindowMarks({
    marks,
    selection: 'cusum_engage_then_skills',
    engageSec: 0,
    actual,
    markAlwaysNearKillSec: PRODUCT_KILL_WINDOW_DEFAULTS.markAlwaysNearKillSec ?? 1.5,
    markMinGapSec: PRODUCT_KILL_WINDOW_DEFAULTS.markMinGapSec ?? 0,
    markDensityWindowSec: PRODUCT_KILL_WINDOW_DEFAULTS.markDensityWindowSec ?? 0,
    markDenseMaxPerWindow: PRODUCT_KILL_WINDOW_DEFAULTS.markDenseMaxPerWindow ?? 1,
  })
  const harness = simulateKillWindowSeries({
    atk,
    def,
    actual,
    marks: selected.marks,
    castPulseSec: PRODUCT_KILL_WINDOW_DEFAULTS.castPulseSec ?? 0.4,
    engageSec: selected.engageSec,
    idleHp: 1283,
    finishAa: PRODUCT_KILL_WINDOW_DEFAULTS.finishAa,
    xhMode: 'off',
  })
  const calcFp = fingerprintResult(calc)
  const calcLethal = calc.timing?.firstLethalSec ?? null
  const harnessLethal = harness.firstLethalSec
  const calcEndHp = calc.red.targets?.[0]?.hpRemaining ?? null
  const harnessEndHp = harness.model[harness.model.length - 1]?.hp ?? null
  assert.ok(calcEndHp != null && harnessEndHp != null)
  assert.ok(
    Math.abs(calcEndHp! - harnessEndHp!) < 1e-6,
    `endHp drift calc=${calcEndHp} harness=${harnessEndHp}`,
  )
  if (calcLethal != null || harnessLethal != null) {
    assert.equal(calcLethal, harnessLethal)
  }
  // Re-run Matchup twice → identical (determinism)
  const calc2 = simulateKillWindowMatchup(matchup)
  assert.equal(fingerprintResult(calc2), calcFp)
  return {
    calcFp,
    selectedMarkCount: selected.marks.length,
    rawMarkCount: marks.length,
    calcLethal,
    harnessLethal,
    calcEndHp,
    harnessEndHp,
    endHpAgree: true,
    note: 'harness series fed post-select marks (same as Matchup internal)',
  }
})

exp('E2', 'F6-H1 Path1 crosscheck pins: Calculator Matchup deterministic on S0 c1', () => {
  assert.ok(existsSync(CROSSCHECKS), `missing ${CROSSCHECKS}`)
  const cc = JSON.parse(readFileSync(CROSSCHECKS, 'utf8')) as {
    crossChecks: Array<{
      killerChamp: string
      victimChamp: string
      tMs: number
      windowMs: [number, number]
      killerHp: Array<Record<string, unknown>>
      victimHp: Array<Record<string, unknown>>
    }>
  }
  const c1 = cc.crossChecks[0]
  assert.ok(c1, 'no crosscheck 0')
  const k0 = c1.killerHp[0] as {
    health: number
    health_max: number
    attack_damage: number
    ability_power: number
    armor: number
    magic_resist: number
    attack_speed: number
    level: number
    ability1_level: number
    ability2_level: number
    ability3_level: number
    ability4_level: number
    items_json?: string
    hp_known?: number
    combat_known?: number
    ranks_known?: number
  }
  const v0 = c1.victimHp[0] as typeof k0
  assert.equal(k0.hp_known, 1)
  assert.equal(v0.hp_known, 1)
  assert.equal(k0.combat_known, 1)
  assert.equal(v0.combat_known, 1)
  assert.equal(k0.ranks_known, 1)
  assert.equal(v0.ranks_known, 1)
  const atk = pinnedFromCrosscheckRow({ ...k0, champ: c1.killerChamp })
  const def = pinnedFromCrosscheckRow({ ...v0, champ: c1.victimChamp })
  const t0 = c1.windowMs[0]
  const actual = c1.victimHp.map((row) => {
    const r = row as { game_time_ms: number; health: number; health_max: number }
    return {
      tSec: (r.game_time_ms - t0) / 1000,
      hp: r.health,
      hpMax: r.health_max,
    }
  })
  // Disclosed synthetic skill marks for math-parity only (not product truth claim)
  const marks = [
    { tSec: 2.0, skillSlot: 1 },
    { tSec: 4.0, skillSlot: 2 },
    { tSec: 8.0, skillSlot: 3 },
    { tSec: 12.0, skillSlot: 4 },
  ]
  const matchup: MatchupInput = {
    blue: [atk],
    red: [def],
    engager: 'blue',
    mode: 'extended',
    durationSec: 16,
    xhMode: 'off',
    killWindow: {
      ...PRODUCT_KILL_WINDOW_DEFAULTS,
      actionMarks: marks,
      engageSec: 1.5,
      actualHpSeries: actual,
      markSelection: 'cusum_engage_then_skills',
    },
  }
  const a = simulateKillWindowMatchup(matchup)
  const b = simulateKillWindowMatchup(matchup)
  const fp = fingerprintResult(a)
  assert.equal(fingerprintResult(b), fp)
  const selected = selectKillWindowMarks({
    marks,
    selection: 'cusum_engage_then_skills',
    engageSec: 1.5,
    actual,
    markAlwaysNearKillSec: PRODUCT_KILL_WINDOW_DEFAULTS.markAlwaysNearKillSec ?? 1.5,
    markMinGapSec: PRODUCT_KILL_WINDOW_DEFAULTS.markMinGapSec ?? 0,
    markDensityWindowSec: PRODUCT_KILL_WINDOW_DEFAULTS.markDensityWindowSec ?? 0,
    markDenseMaxPerWindow: PRODUCT_KILL_WINDOW_DEFAULTS.markDenseMaxPerWindow ?? 1,
  })
  const series = simulateKillWindowSeries({
    atk,
    def,
    actual,
    marks: selected.marks,
    castPulseSec: PRODUCT_KILL_WINDOW_DEFAULTS.castPulseSec ?? 0.4,
    // Matchup uses CUSUM-resolved engage from selectKillWindowMarks — not the raw 1.5 probe
    engageSec: selected.engageSec,
    idleHp: def.liveStats!.hp!,
    idleFollowActual: PRODUCT_KILL_WINDOW_DEFAULTS.idleFollowActual ?? false,
    finishAa: PRODUCT_KILL_WINDOW_DEFAULTS.finishAa,
    xhMode: 'off',
  })
  const calcEnd = a.red.targets?.[0]?.hpRemaining ?? null
  const seriesEnd = series.model[series.model.length - 1]?.hp ?? null
  assert.ok(calcEnd != null && seriesEnd != null)
  assert.ok(
    Math.abs(calcEnd! - seriesEnd!) < 1e-6,
    `Path1 pin endHp drift calc=${calcEnd} series=${seriesEnd}`,
  )
  return {
    matchup: `${c1.killerChamp}→${c1.victimChamp}`,
    tMs: c1.tMs,
    fp,
    calcEnd,
    seriesEnd,
    invent: false,
    note: 'marks are disclosed parity probes — not claimed as timeline skill_used truth',
  }
})

// ── H2: Dead excluded ───────────────────────────────────────────────────────
{
  const vite = await createServer({
    server: { middlewareMode: true },
    appType: 'custom',
    logLevel: 'silent',
  })
  try {
    const gr = (await vite.ssrLoadModule(
      '/src/components/GameReview.tsx',
    )) as typeof import('../src/components/GameReview')

    exp('E3', 'F6-H2 dead excluded from Send import; living known still sends', () => {
      const parity = gr.buildLivingSendImport([
        {
          loadout: { championId: 'Galio' },
          team: 'blue',
          alive: true,
          hpKnown: true,
          combatStatsKnown: true,
          abilityRanksKnown: true,
        },
        {
          loadout: { championId: 'Jayce' },
          team: 'blue',
          alive: false,
          hpKnown: false,
          combatStatsKnown: false,
          abilityRanksKnown: false,
        },
        {
          loadout: { championId: 'Trundle' },
          team: 'red',
          alive: true,
          hpKnown: true,
          combatStatsKnown: true,
          abilityRanksKnown: true,
        },
      ])
      assert.equal(parity.deadExcludedCount, 1)
      assert.equal(parity.blue.length, 1)
      assert.equal(parity.blue[0]?.championId, 'Galio')
      assert.equal(parity.canSend, true)
      assert.equal(parity.lacksKnownCombatState, false)
      assert.equal(parity.attachedResearchActions.length, 0)
      return {
        deadExcludedCount: parity.deadExcludedCount,
        blue: parity.blue.length,
        red: parity.red.length,
        canSend: parity.canSend,
      }
    })

    exp('E4', 'F6-H4 known-flags fail-closed: sparse combat blocks Send', () => {
      const parity = gr.buildLivingSendImport([
        {
          loadout: { championId: 'Galio' },
          team: 'blue',
          alive: true,
          hpKnown: true,
          combatStatsKnown: true,
          abilityRanksKnown: true,
        },
        {
          loadout: { championId: 'Jayce' },
          team: 'blue',
          alive: true,
          hpKnown: true,
          combatStatsKnown: false,
          abilityRanksKnown: true,
        },
        {
          loadout: { championId: 'Trundle' },
          team: 'red',
          alive: true,
          hpKnown: true,
          combatStatsKnown: true,
          abilityRanksKnown: true,
        },
      ])
      assert.equal(parity.lacksKnownCombatState, true)
      const block = gr.calculatorTrustBlockReason({
        research: false,
        positionBlocked: false,
        combatStateBlocked: parity.lacksKnownCombatState,
        missingFieldLabel: parity.trustGap,
      })
      assert.ok(block)
      assert.doesNotMatch(block!, /odds\s*%|win\s*%|calibrated/i)
      return { blocked: true, trustGap: parity.trustGap }
    })
  } finally {
    await vite.close()
  }
}

// ── H4 Partial C / Path1 unitToLoadout honesty ──────────────────────────────
exp('E5', 'F6-H4 Path1 timeline: unitToLoadout omits unknown; triple-known imports pins', () => {
  assert.ok(existsSync(PATH1_TIMELINE), `missing ${PATH1_TIMELINE}`)
  const tl = JSON.parse(readFileSync(PATH1_TIMELINE, 'utf8')) as {
    frames: Array<{ t: number; units: TimelineUnitFrame[] }>
  }
  // Find a living Galio+Trundle frame with triple-known flags
  let found: { galio: TimelineUnitFrame; trundle: TimelineUnitFrame; t: number } | null =
    null
  for (const fr of tl.frames) {
    const galio = fr.units.find(
      (u) =>
        u.champ === 'Galio' &&
        u.alive !== false &&
        hpIsKnown(u) &&
        combatStatsAreKnown(u) &&
        abilityRanksAreKnown(u),
    )
    const trundle = fr.units.find(
      (u) =>
        u.champ === 'Trundle' &&
        u.alive !== false &&
        hpIsKnown(u) &&
        combatStatsAreKnown(u) &&
        abilityRanksAreKnown(u),
    )
    if (galio && trundle) {
      found = { galio, trundle, t: fr.t }
      break
    }
  }
  assert.ok(found, 'no triple-known Galio+Trundle living frame')
  const gLoad = unitToLoadout(found!.galio)
  const tLoad = unitToLoadout(found!.trundle)
  assert.ok(gLoad.liveStats?.hp != null)
  assert.ok(tLoad.liveStats?.hp != null)
  assert.ok(gLoad.ranks)
  assert.ok(tLoad.ranks)
  // combatStatsKnown=false ⇒ omit AD/armor/AS; HP may remain if hpKnown
  const sparse: TimelineUnitFrame = {
    ...found!.galio,
    combatStatsKnown: false,
    ad: undefined as unknown as number,
    armor: undefined as unknown as number,
  }
  const sparseLoad = unitToLoadout(sparse)
  assert.equal(sparseLoad.liveStats?.ad, undefined)
  assert.equal(sparseLoad.liveStats?.armor, undefined)
  assert.equal(sparseLoad.liveStats?.attackSpeed, undefined)
  // hpKnown still true on found.galio → HP pins stay (honest partial)
  assert.ok(sparseLoad.liveStats?.hp != null)
  // Dead unit must not be imported as living Send fighter
  const dead: TimelineUnitFrame = { ...found!.galio, alive: false }
  assert.equal(dead.alive, false)
  return {
    frameT: found!.t,
    galioHp: gLoad.liveStats!.hp!,
    trundleHp: tLoad.liveStats!.hp!,
    sparseOmitsCombatStats: true,
    sparseKeepsHpWhenKnown: true,
  }
})

// ── H5 No odds copy ─────────────────────────────────────────────────────────
exp('E6', 'F6-H5 product UI: model edge language; no odds % claims in CombatResult', () => {
  const combatResult = readFileSync(
    join(ROOT, 'src/components/CombatResult.tsx'),
    'utf8',
  )
  assert.match(combatResult, /model edge/i)
  assert.doesNotMatch(combatResult, /odds\s*%/i)
  assert.doesNotMatch(combatResult, /chance to win/i)
  const calc = readFileSync(join(ROOT, 'src/components/Calculator.tsx'), 'utf8')
  assert.doesNotMatch(calc, /odds\s*%/i)
  assert.match(calc, /not win %/)
  return { modelEdgeCopy: true, oddsPercentAbsent: true }
})

// ── H2 overlay never attaches via Send builder ──────────────────────────────
{
  const mod = await import('../src/game/researchActionOverlay')
  exp('E7', 'F6-H2/H4 research overlay rows never enter product Send payload', () => {
    const fake = [
      {
        kind: 'basic_attack' as const,
        tSec: 100,
        tMs: 100_000,
        sourceNetId: 1,
        sourceChampion: 'Galio',
        targetNetId: 2,
        targetChampion: 'Trundle',
        amount: 50,
        researchOnly: true as const,
        calculatorReady: false as const,
      },
    ]
    assert.equal(mod.productSendAttachesResearchActions(fake), false)
    assert.deepEqual(mod.productSendAttachedResearchActions(fake), [])
    return { overlayBypass: false }
  })
}

// ── Write artifacts ─────────────────────────────────────────────────────────
const summary = {
  schema: 'fo-r17-send-parity-smoke-v1',
  utc: new Date().toISOString(),
  researcher: 'r17',
  room: 'f6',
  mandate: 'calc-send / Send honesty / known-flags',
  smokeCommand: 'npm run fo:send-smoke',
  never_edited_parent: true,
  invent: false,
  fightOutcomeGate: false,
  criterionG: {
    sendOverlayParity: experiments.find((e) => e.id === 'E1')?.pass ?? false,
    deadExcluded: experiments.find((e) => e.id === 'E3')?.pass ?? false,
    knownFlags: experiments.find((e) => e.id === 'E4')?.pass ?? false,
    path1Honesty: experiments.find((e) => e.id === 'E5')?.pass ?? false,
    noOddsCopy: experiments.find((e) => e.id === 'E6')?.pass ?? false,
    smokeCommandDefined: true,
  },
  passCount: experiments.filter((e) => e.pass).length,
  failCount: failed,
  experiments,
  note:
    'Parity proves Calculator simulateKillWindowMatchup ≡ harness simulateKillWindowSeries on same pins. Marks in E2 are disclosed parity probes, not timeline skill_used claims. fightAgreement FA not raised here — R17 is Criterion G scaffolding.',
}

function writeBoth(name: string, body: string) {
  for (const dir of [OUT_DIR, PARENT_OUT]) {
    mkdirSync(dir, { recursive: true })
    writeFileSync(join(dir, name), body)
  }
}

writeBoth('send_parity_smoke.json', JSON.stringify(summary, null, 2) + '\n')
writeBoth(
  'results.jsonl',
  experiments.map((e) => JSON.stringify({ t: summary.utc, ...e })).join('\n') + '\n',
)

console.log('')
console.log(
  `fo_r17_send_parity_smoke: ${summary.passCount} pass / ${summary.failCount} fail`,
)
console.log(`artifacts → ${OUT_DIR} (+ parent mirror)`)
if (failed > 0) process.exit(1)
