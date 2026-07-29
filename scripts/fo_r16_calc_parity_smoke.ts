/**
 * R16 calc-parity smoke — prove Calculator Send math ≡ harness overlay math.
 *
 * Same pins → simulateKillWindowMatchup (Calculator) endHp/lethal ≡
 * simulateKillWindowSeries (harness core). Dead excluded. Known-flags fail-closed.
 * Notes say model edge / experimental — never odds %.
 *
 * Usage:
 *   npx --yes tsx scripts/fo_r16_calc_parity_smoke.ts
 *   npm run smoke:calc-parity
 */
import assert from 'node:assert/strict'
import { readFileSync, mkdirSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { createServer } from 'vite'
import { defaultLoadout } from '../src/engine/combat'
import {
  PRODUCT_KILL_WINDOW_DEFAULTS,
  maybeAttachKillWindow,
} from '../src/engine/killWindowProduct'
import {
  selectKillWindowMarks,
  simulateKillWindowMatchup,
  simulateKillWindowSeries,
  type KillWindowActionMark,
} from '../src/engine/killWindowOverlay'
import type { FighterLoadout, MatchupInput } from '../src/engine/types'
import {
  abilityRanksAreKnown,
  combatStatsAreKnown,
  hpIsKnown,
} from '../src/game/timeline'

const __dirname = dirname(fileURLToPath(import.meta.url))
const ROOT = join(__dirname, '..')
const OUT_DIR = join(
  ROOT,
  'docs/rofl-research/autoresearch/fight_outcome/r16',
)
const PARENT_OUT = join(
  '/Users/river/Projects/lol-strength-analysis',
  'docs/rofl-research/autoresearch/fight_outcome/r16',
)

type ExpResult = {
  id: string
  hypothesis: string
  keep: boolean
  pass: boolean
  notes: string
  metrics?: Record<string, number | string | boolean | null>
}

const experiments: ExpResult[] = []

function pinned(
  championId: string,
  hp: number,
  hpMax: number,
  combat: { ad: number; armor: number; attackSpeed: number; mr?: number },
  ranks = { Q: 5, W: 5, E: 5, R: 3 },
): FighterLoadout {
  return {
    ...defaultLoadout(championId),
    level: 11,
    ranks,
    itemIds: [],
    alive: true,
    liveStats: {
      hp,
      hpMax,
      ad: combat.ad,
      ap: 0,
      armor: combat.armor,
      mr: combat.mr ?? 40,
      attackSpeed: combat.attackSpeed,
    },
  }
}

function seriesFromMatchup(input: MatchupInput) {
  const kw = input.killWindow!
  const atk = input.blue.filter((f) => f.alive !== false)[0]!
  const def = input.red.filter((f) => f.alive !== false)[0]!
  const actual =
    kw.actualHpSeries?.length
      ? kw.actualHpSeries
      : Array.from({ length: 9 }, (_, i) => ({
          tSec: i,
          hp: def.liveStats!.hp!,
          hpMax: def.liveStats!.hpMax,
        }))
  const rawMarks: KillWindowActionMark[] = [
    ...(kw.actionMarks ?? []),
    ...(kw.allyMarks ?? []).map((m) => ({ ...m, ally: true as const })),
  ]
  const selection = kw.markSelection ?? 'cusum_engage_then_skills'
  const selected = selectKillWindowMarks({
    marks: rawMarks,
    selection,
    engageSec: kw.engageSec ?? null,
    actual,
    killOffsetSec: kw.killOffsetSec ?? null,
    markAlwaysNearKillSec: kw.markAlwaysNearKillSec ?? 1.5,
    markMinGapSec: kw.markMinGapSec ?? 0,
    markDensityWindowSec: kw.markDensityWindowSec ?? 0,
    markDenseMaxPerWindow: kw.markDenseMaxPerWindow ?? 1,
  })
  return simulateKillWindowSeries({
    atk,
    def,
    actual,
    marks: selected.marks.filter((m) => !m.ally),
    allyMarks: selected.marks.filter((m) => m.ally),
    castPulseSec: kw.castPulseSec ?? 0.4,
    engageSec: selected.engageSec,
    idleHp: def.liveStats!.hp,
    idleFollowActual: kw.idleFollowActual ?? PRODUCT_KILL_WINDOW_DEFAULTS.idleFollowActual ?? false,
    aaFiller: kw.aaFiller ?? false,
    maxAaBetweenMarks: kw.maxAaBetweenMarks ?? 6,
    allyPulseShare: kw.allyPulseShare ?? 0,
    finishAa: kw.finishAa ?? PRODUCT_KILL_WINDOW_DEFAULTS.finishAa ?? {
      afterLastMark: true,
      maxAa: 4,
      aaAtEachMark: false,
    },
    killOffsetSec: kw.killOffsetSec ?? null,
    perSlotPulse: kw.perSlotPulse ?? PRODUCT_KILL_WINDOW_DEFAULTS.perSlotPulse ?? false,
    pulseBySlot: kw.pulseBySlot ?? PRODUCT_KILL_WINDOW_DEFAULTS.pulseBySlot,
    xhMode: 'off',
  })
}

function assertCalcHarnessParity(label: string, input: MatchupInput) {
  const calc = simulateKillWindowMatchup({ ...input, xhMode: 'off' })
  const harness = seriesFromMatchup({ ...input, xhMode: 'off' })
  const calcEnd = calc.red.targets?.[0]?.hpRemaining ?? calc.red.hpRemaining
  const harnessEnd = harness.model[harness.model.length - 1]?.hp ?? null
  assert.ok(harnessEnd != null, `${label}: harness series empty`)
  assert.ok(
    Math.abs(Number(calcEnd) - Number(harnessEnd)) < 1e-6,
    `${label}: endHp calc=${calcEnd} harness=${harnessEnd}`,
  )
  const calcLethal = calc.timing?.firstLethalSec ?? null
  const harnessLethal = harness.firstLethalSec
  if (calcLethal == null || harnessLethal == null) {
    assert.equal(
      calcLethal,
      harnessLethal,
      `${label}: lethal null mismatch calc=${calcLethal} harness=${harnessLethal}`,
    )
  } else {
    assert.ok(
      Math.abs(calcLethal - harnessLethal) < 1e-6,
      `${label}: lethal calc=${calcLethal} harness=${harnessLethal}`,
    )
  }
  assert.equal(
    calc.timing?.method,
    'kill_window_gate_action',
    `${label}: calc must claim kill_window_gate_action`,
  )
  return {
    endHp: Number(calcEnd),
    lethalSec: calcLethal,
    markCount: harness.markCount,
  }
}

function baseCamilleLeonaInput(overrides: Partial<MatchupInput> = {}): MatchupInput {
  const atk = pinned('Camille', 2200, 2400, {
    ad: 220,
    armor: 90,
    attackSpeed: 1.2,
  })
  const def = pinned('Leona', 900, 2800, {
    ad: 100,
    armor: 120,
    attackSpeed: 0.7,
  })
  const actual = Array.from({ length: 9 }, (_, i) => ({
    tSec: i * 0.5,
    hp: 900,
    hpMax: 2800,
  }))
  const marks: KillWindowActionMark[] = [
    { tSec: 0.2, skillSlot: 3 },
    { tSec: 0.6, skillSlot: 1 },
    { tSec: 1.1, skillSlot: 4 },
    { tSec: 1.6, skillSlot: 2 },
  ]
  return {
    blue: [atk],
    red: [def],
    engager: 'blue',
    mode: 'allin',
    durationSec: 4,
    xhMode: 'off',
    killWindow: {
      ...PRODUCT_KILL_WINDOW_DEFAULTS,
      markSelection: 'cusum_engage_then_skills',
      engageSec: 0,
      actionMarks: marks,
      actualHpSeries: actual,
      killOffsetSec: 2,
    },
    ...overrides,
  }
}

function loadS0Pins(checkIndex: number): MatchupInput | null {
  const path = join(ROOT, 'docs/canvases/_data/crosschecks-2970132-g1.json')
  let raw: {
    crossChecks: Array<{
      killerChamp: string
      victimChamp: string
      tMs: number
      windowMs: [number, number]
      victimHpStart: number
      victimHpMax: number
      victimHp: Array<{
        game_time_ms: number
        health: number
        health_max: number
        attack_damage: number
        armor: number
        magic_resist: number
        attack_speed: number
        ability1_level: number
        ability2_level: number
        ability3_level: number
        ability4_level: number
        alive: number
      }>
      killerHp?: Array<{
        game_time_ms: number
        health: number
        health_max: number
        attack_damage: number
        armor: number
        magic_resist: number
        attack_speed: number
        ability1_level: number
        ability2_level: number
        ability3_level: number
        ability4_level: number
      }>
    }>
  }
  try {
    raw = JSON.parse(readFileSync(path, 'utf8'))
  } catch {
    return null
  }
  const cc = raw.crossChecks[checkIndex]
  if (!cc) return null
  const t0 = cc.windowMs[0]
  const victimStart = cc.victimHp.find((r) => r.alive === 1) ?? cc.victimHp[0]
  if (!victimStart) return null
  const killerRows = cc.killerHp ?? []
  const killerStart = killerRows[0]
  const atk = pinned(
    cc.killerChamp,
    killerStart?.health ?? 2000,
    killerStart?.health_max ?? 2200,
    {
      ad: killerStart?.attack_damage ?? 180,
      armor: killerStart?.armor ?? 80,
      attackSpeed: (killerStart?.attack_speed ?? 100) / 100,
      mr: killerStart?.magic_resist ?? 40,
    },
    {
      Q: killerStart?.ability1_level ?? 5,
      W: killerStart?.ability2_level ?? 5,
      E: killerStart?.ability3_level ?? 5,
      R: killerStart?.ability4_level ?? 3,
    },
  )
  const def = pinned(
    cc.victimChamp,
    cc.victimHpStart,
    cc.victimHpMax,
    {
      ad: victimStart.attack_damage,
      armor: victimStart.armor,
      attackSpeed: victimStart.attack_speed / 100,
      mr: victimStart.magic_resist,
    },
    {
      Q: victimStart.ability1_level,
      W: victimStart.ability2_level,
      E: victimStart.ability3_level,
      R: victimStart.ability4_level,
    },
  )
  const actual = cc.victimHp.map((r) => ({
    tSec: (r.game_time_ms - t0) / 1000,
    hp: r.health,
    hpMax: r.health_max,
  }))
  // Honest marks from victim HP drops — product selector filters; no invented skills.
  const marks: KillWindowActionMark[] = []
  for (let i = 1; i < actual.length; i++) {
    const d = actual[i - 1]!.hp - actual[i]!.hp
    if (d > 40) marks.push({ tSec: actual[i]!.tSec, skillSlot: 1 })
  }
  if (!marks.length) {
    marks.push({ tSec: Math.max(0, actual[Math.floor(actual.length / 2)]?.tSec ?? 1), skillSlot: 1 })
  }
  return {
    blue: [atk],
    red: [def],
    engager: 'blue',
    mode: 'extended',
    durationSec: Math.max(4, (cc.windowMs[1] - cc.windowMs[0]) / 1000),
    xhMode: 'off',
    killWindow: {
      ...PRODUCT_KILL_WINDOW_DEFAULTS,
      markSelection: 'cusum_engage_then_skills',
      engageSec: marks[0]!.tSec,
      actionMarks: marks,
      actualHpSeries: actual,
      killOffsetSec: actual.find((a) => a.hp <= 0)?.tSec ?? null,
    },
  }
}

function record(exp: ExpResult) {
  experiments.push(exp)
  const mark = exp.pass ? 'PASS' : 'FAIL'
  console.log(`${exp.id} ${mark} — ${exp.hypothesis} | ${exp.notes}`)
}

async function main() {
  mkdirSync(OUT_DIR, { recursive: true })
  mkdirSync(PARENT_OUT, { recursive: true })

  // e0 — synthetic Send↔harness parity (cusum product default)
  {
    const id = 'e0'
    try {
      const m = assertCalcHarnessParity('e0', baseCamilleLeonaInput())
      record({
        id,
        hypothesis: 'Send→overlay parity (synthetic Camille→Leona, cusum)',
        keep: true,
        pass: true,
        notes: `endHp=${m.endHp} lethal=${m.lethalSec} marks=${m.markCount}`,
        metrics: m,
      })
    } catch (err) {
      record({
        id,
        hypothesis: 'Send→overlay parity (synthetic Camille→Leona, cusum)',
        keep: false,
        pass: false,
        notes: String(err),
      })
    }
  }

  // e1 — post_engage product selector parity
  {
    const id = 'e1'
    try {
      const input = baseCamilleLeonaInput()
      input.killWindow = {
        ...input.killWindow!,
        markSelection: 'post_engage_killer_skills',
        engageSec: 0.5,
      }
      const m = assertCalcHarnessParity('e1', input)
      record({
        id,
        hypothesis: 'Send→overlay parity (post_engage_killer_skills)',
        keep: true,
        pass: true,
        notes: `endHp=${m.endHp} lethal=${m.lethalSec}`,
        metrics: m,
      })
    } catch (err) {
      record({
        id,
        hypothesis: 'Send→overlay parity (post_engage_killer_skills)',
        keep: false,
        pass: false,
        notes: String(err),
      })
    }
  }

  // e2 — maybeAttachKillWindow product helper → same parity
  {
    const id = 'e2'
    try {
      const base = baseCamilleLeonaInput()
      const { killWindow: _drop, ...rest } = base
      const attached = maybeAttachKillWindow(rest, {
        actionMarks: base.killWindow!.actionMarks,
        engageSec: 0,
        actualHpSeries: base.killWindow!.actualHpSeries,
        killOffsetSec: 2,
      })
      assert.ok(attached.killWindow?.actionMarks?.length, 'attach marks')
      const m = assertCalcHarnessParity('e2', attached)
      record({
        id,
        hypothesis: 'maybeAttachKillWindow → Calculator path parity',
        keep: true,
        pass: true,
        notes: `endHp=${m.endHp} lethal=${m.lethalSec}`,
        metrics: m,
      })
    } catch (err) {
      record({
        id,
        hypothesis: 'maybeAttachKillWindow → Calculator path parity',
        keep: false,
        pass: false,
        notes: String(err),
      })
    }
  }

  // e3 — dead excluded from overlay living filter + Send import
  {
    const id = 'e3'
    const vite = await createServer({
      server: { middlewareMode: true },
      appType: 'custom',
      logLevel: 'silent',
      root: ROOT,
    })
    try {
      const {
        buildLivingSendImport,
        livingSelectedUnits,
      } = (await vite.ssrLoadModule(
        '/src/components/GameReview.tsx',
      )) as typeof import('../src/components/GameReview')
      const selected = [
        {
          loadout: { championId: 'Camille' },
          team: 'blue' as const,
          alive: true,
          hpKnown: true,
          combatStatsKnown: true,
          abilityRanksKnown: true,
        },
        {
          loadout: { championId: 'Galio' },
          team: 'blue' as const,
          alive: false,
          hpKnown: false,
          combatStatsKnown: false,
          abilityRanksKnown: false,
        },
        {
          loadout: { championId: 'Leona' },
          team: 'red' as const,
          alive: true,
          hpKnown: true,
          combatStatsKnown: true,
          abilityRanksKnown: true,
        },
      ]
      const living = livingSelectedUnits(selected)
      assert.deepEqual(
        living.map((u) => u.loadout.championId),
        ['Camille', 'Leona'],
      )
      const parity = buildLivingSendImport(selected)
      assert.equal(parity.deadExcludedCount, 1)
      assert.deepEqual(
        parity.blue.map((u) => u.championId),
        ['Camille'],
      )
      assert.equal(parity.canSend, true)
      assert.equal(parity.lacksKnownCombatState, false)

      const deadDef = pinned('Leona', 0, 2800, {
        ad: 100,
        armor: 120,
        attackSpeed: 0.7,
      })
      deadDef.alive = false
      const input = baseCamilleLeonaInput({ red: [deadDef] })
      const calc = simulateKillWindowMatchup(input)
      assert.match(
        calc.notes.join(' '),
        /missing HP pins|non-1v1|continuous fallback/i,
        'dead defender refuses kill-window invent',
      )
      record({
        id,
        hypothesis: 'Dead excluded — import + overlay refuse corpse pins',
        keep: true,
        pass: true,
        notes: `deadExcludedCount=${parity.deadExcludedCount}; overlay fallback disclosed`,
      })
    } catch (err) {
      record({
        id,
        hypothesis: 'Dead excluded — import + overlay refuse corpse pins',
        keep: false,
        pass: false,
        notes: String(err),
      })
    } finally {
      await vite.close()
    }
  }

  // e4 — known-flags fail-closed
  {
    const id = 'e4'
    try {
      assert.equal(hpIsKnown({}), false)
      assert.equal(combatStatsAreKnown({}), false)
      assert.equal(abilityRanksAreKnown({}), false)
      assert.equal(hpIsKnown({ hpKnown: false }), false)
      assert.equal(hpIsKnown({ hpKnown: true }), true)
      const vite = await createServer({
        server: { middlewareMode: true },
        appType: 'custom',
        logLevel: 'silent',
        root: ROOT,
      })
      try {
        const {
          selectedLacksKnownCombatState,
          calculatorTrustBlockReason,
          buildLivingSendImport,
        } = (await vite.ssrLoadModule(
          '/src/components/GameReview.tsx',
        )) as typeof import('../src/components/GameReview')
        assert.equal(
          selectedLacksKnownCombatState([
            {
              hpKnown: true,
              combatStatsKnown: true,
              abilityRanksKnown: true,
            },
          ]),
          false,
        )
        assert.equal(
          selectedLacksKnownCombatState([{ hpKnown: true }]),
          true,
          'absent combat/ranks fail-closed',
        )
        const blocked = buildLivingSendImport([
          {
            loadout: { championId: 'Camille' },
            team: 'blue',
            alive: true,
            hpKnown: true,
            // combat/ranks absent
          },
          {
            loadout: { championId: 'Leona' },
            team: 'red',
            alive: true,
            hpKnown: true,
            combatStatsKnown: true,
            abilityRanksKnown: true,
          },
        ])
        assert.equal(blocked.lacksKnownCombatState, true)
        const reason = calculatorTrustBlockReason({
          research: false,
          positionBlocked: false,
          combatStateBlocked: blocked.lacksKnownCombatState,
          missingFieldLabel: blocked.trustGap,
        })
        assert.ok(reason, 'Send blocked when living lacks known flags')
        assert.match(reason!, /Camille/i)
        record({
          id,
          hypothesis: 'Partial C honesty — known-flags fail-closed gate Send',
          keep: true,
          pass: true,
          notes: `trustGap=${blocked.trustGap}; block=${reason}`,
        })
      } finally {
        await vite.close()
      }
    } catch (err) {
      record({
        id,
        hypothesis: 'Partial C honesty — known-flags fail-closed gate Send',
        keep: false,
        pass: false,
        notes: String(err),
      })
    }
  }

  // e5 — missing pins → no invent
  {
    const id = 'e5'
    try {
      const atk = defaultLoadout('Camille')
      const def = defaultLoadout('Leona')
      delete (atk as { liveStats?: unknown }).liveStats
      delete (def as { liveStats?: unknown }).liveStats
      const r = simulateKillWindowMatchup({
        blue: [atk],
        red: [def],
        engager: 'blue',
        mode: 'extended',
        durationSec: 8,
        xhMode: 'off',
        killWindow: {
          actionMarks: [{ tSec: 1, skillSlot: 1 }],
          markSelection: 'cusum_engage_then_skills',
          engageSec: 0,
        },
      })
      assert.ok(
        r.notes.some((n) => /missing HP pins/i.test(n)),
        'disclose continuous fallback',
      )
      assert.notEqual(r.timing?.method, 'kill_window_gate_action')
      record({
        id,
        hypothesis: 'No invent — missing HP pins refuse kill-window claim',
        keep: true,
        pass: true,
        notes: `method=${r.timing?.method ?? 'none'}`,
      })
    } catch (err) {
      record({
        id,
        hypothesis: 'No invent — missing HP pins refuse kill-window claim',
        keep: false,
        pass: false,
        notes: String(err),
      })
    }
  }

  // e6–e8 — S0 Path1 checks 0..2 pin parity (FA context 0.228; parity ≠ FA lift)
  for (let i = 0; i < 3; i++) {
    const id = `e${6 + i}`
    const input = loadS0Pins(i)
    try {
      assert.ok(input, `S0 check${i + 1} pins loadable`)
      const m = assertCalcHarnessParity(id, input!)
      record({
        id,
        hypothesis: `S0 Path1 check0${i + 1} Send↔harness pin parity (FA context 0.228)`,
        keep: true,
        pass: true,
        notes: `${input!.blue[0]!.championId}→${input!.red[0]!.championId} endHp=${m.endHp} lethal=${m.lethalSec}`,
        metrics: {
          ...m,
          contextFightAgreement: 0.228,
          note: 'parity proof only — not FA improvement',
        },
      })
    } catch (err) {
      record({
        id,
        hypothesis: `S0 Path1 check0${i + 1} Send↔harness pin parity (FA context 0.228)`,
        keep: false,
        pass: false,
        notes: String(err),
      })
    }
  }

  // e9 — no odds copy on kill-window path notes
  {
    const id = 'e9'
    try {
      const calc = simulateKillWindowMatchup(baseCamilleLeonaInput())
      const blob = [...calc.notes, ...(calc.timing?.caveats ?? [])].join(' | ')
      assert.doesNotMatch(blob, /\bodds\b|\bwin %\b|\bwin probability\b/i)
      assert.match(blob, /model edge|experimental|not_calibrated_win_odds/i)
      record({
        id,
        hypothesis: 'No odds copy — model edge / experimental language only',
        keep: true,
        pass: true,
        notes: blob.slice(0, 160),
      })
    } catch (err) {
      record({
        id,
        hypothesis: 'No odds copy — model edge / experimental language only',
        keep: false,
        pass: false,
        notes: String(err),
      })
    }
  }

  // e10 — Calculator module routes killWindow → simulateKillWindowMatchup
  {
    const id = 'e10'
    try {
      const src = readFileSync(
        join(ROOT, 'src/components/Calculator.tsx'),
        'utf8',
      )
      assert.match(src, /simulateKillWindowMatchup/)
      assert.match(src, /killWindow\?\.actionMarks/)
      const overlay = readFileSync(
        join(ROOT, 'src/engine/killWindowOverlay.ts'),
        'utf8',
      )
      assert.match(overlay, /export function simulateKillWindowSeries/)
      assert.match(overlay, /export function simulateKillWindowMatchup/)
      record({
        id,
        hypothesis: 'Smoke command wiring — Calculator imports shared overlay',
        keep: true,
        pass: true,
        notes: 'Calculator.tsx routes marks → simulateKillWindowMatchup; harness uses Series',
      })
    } catch (err) {
      record({
        id,
        hypothesis: 'Smoke command wiring — Calculator imports shared overlay',
        keep: false,
        pass: false,
        notes: String(err),
      })
    }
  }

  const passed = experiments.filter((e) => e.pass).length
  const failed = experiments.filter((e) => !e.pass).length
  const payload = {
    researcher: 'r16',
    slug: 'calc-parity',
    utc: new Date().toISOString(),
    n: experiments.length,
    passed,
    failed,
    allPass: failed === 0,
    experiments,
    smokeCommand: 'npm run smoke:calc-parity',
    never_edited_parent: true,
    context: {
      S0_Path1_product_FA: 0.228,
      note: 'Parity proves Send≡harness math; does not raise fightAgreement',
    },
  }

  const resultsPath = join(OUT_DIR, 'results.jsonl')
  writeFileSync(
    resultsPath,
    experiments.map((e) => JSON.stringify({ t: payload.utc, ...e })).join('\n') +
      '\n',
  )
  writeFileSync(join(OUT_DIR, 'smoke_report.json'), JSON.stringify(payload, null, 2))
  writeFileSync(
    join(PARENT_OUT, 'results.jsonl'),
    experiments.map((e) => JSON.stringify({ t: payload.utc, ...e })).join('\n') +
      '\n',
  )
  writeFileSync(
    join(PARENT_OUT, 'smoke_report.json'),
    JSON.stringify(payload, null, 2),
  )

  console.log('')
  console.log(`R16 calc-parity smoke: ${passed}/${experiments.length} PASS`)
  if (failed) {
    process.exitCode = 1
  }
}

main().catch((err) => {
  console.error(err)
  process.exit(1)
})
