/**
 * Kill-window overlay acceptance: idle gate + finish lethal + no invented pins.
 * Research-derived path — experimental; never calculatorReady.
 */
import { defaultLoadout } from '../combat'
import {
  selectKillWindowMarks,
  simulateKillWindowSeries,
  simulateKillWindowMatchup,
} from '../killWindowOverlay'
import type { FighterLoadout } from '../types'

type Check = { name: string; detail?: string }
const passed: Check[] = []

function assert(condition: unknown, name: string, detail?: string): asserts condition {
  if (!condition) {
    throw new Error(`FAIL ${name}${detail ? ` — ${detail}` : ''}`)
  }
  passed.push({ name, detail })
}

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

// ── Idle gate (Syndra-like false-all-in): HP flat until engage ──────────────
{
  const atk = pinned('Syndra', 1800, 2000, { ad: 80, armor: 40, attackSpeed: 0.7 })
  const def = pinned('Camille', 1600, 2000, { ad: 100, armor: 80, attackSpeed: 0.9 })
  const actual = Array.from({ length: 21 }, (_, i) => ({
    tSec: i,
    hp: 1600,
    hpMax: 2000,
  }))
  // Marks before engage must not damage; post-engage mark pulses.
  const series = simulateKillWindowSeries({
    atk,
    def,
    actual,
    engageSec: 12,
    idleHp: 1600,
    marks: [
      { tSec: 3, skillSlot: 1 },
      { tSec: 8, skillSlot: 2 },
      { tSec: 13, skillSlot: 1 },
    ],
    castPulseSec: 0.4,
    finishAa: { afterLastMark: false, aaAtEachMark: false },
    xhMode: 'off',
  })
  const early = series.model.filter((m) => m.tSec <= 12)
  const earlyMae =
    early.reduce((s, m) => s + Math.abs(m.hp - 1600), 0) / Math.max(1, early.length)
  assert(earlyMae < 1e-6, 'idle gate keeps defender HP flat until engage', `mae=${earlyMae}`)
  assert(
    (series.model.find((m) => m.tSec >= 13)?.hp ?? 1600) < 1600,
    'post-engage mark deals damage',
  )
}

// ── Truth-follow idle (R19): rising actual HP pre-engage → earlyMae≈0 ────────
{
  const atk = pinned('Galio', 1500, 1600, { ad: 75, armor: 40, attackSpeed: 0.7 })
  const def = pinned('Trundle', 1261, 1349, { ad: 146, armor: 54, attackSpeed: 1.0 })
  const actual = [
    { tSec: 0, hp: 1261, hpMax: 1349 },
    { tSec: 1, hp: 1283, hpMax: 1349 },
    { tSec: 2, hp: 1447, hpMax: 1447 },
    { tSec: 3, hp: 1447, hpMax: 1447 },
    { tSec: 4, hp: 1447, hpMax: 1447 },
    { tSec: 15, hp: 1400, hpMax: 1447 },
    { tSec: 16, hp: 1400, hpMax: 1447 },
  ]
  const freeze = simulateKillWindowSeries({
    atk,
    def,
    actual,
    engageSec: 15,
    idleHp: 1261,
    idleFollowActual: false,
    marks: [{ tSec: 16, skillSlot: 1 }],
    castPulseSec: 0.4,
    finishAa: { afterLastMark: false, aaAtEachMark: false },
    xhMode: 'off',
  })
  const follow = simulateKillWindowSeries({
    atk,
    def,
    actual,
    engageSec: 15,
    idleHp: 1261,
    idleFollowActual: true,
    marks: [{ tSec: 16, skillSlot: 1 }],
    castPulseSec: 0.4,
    finishAa: { afterLastMark: false, aaAtEachMark: false },
    xhMode: 'off',
  })
  const earlyActual = actual.filter((a) => a.tSec <= 4)
  const freezeMae =
    earlyActual.reduce(
      (s, a) => s + Math.abs((freeze.model.find((m) => m.tSec === a.tSec)?.hp ?? 0) - a.hp),
      0,
    ) / earlyActual.length
  const followMae =
    earlyActual.reduce(
      (s, a) => s + Math.abs((follow.model.find((m) => m.tSec === a.tSec)?.hp ?? 0) - a.hp),
      0,
    ) / earlyActual.length
  assert(freezeMae > 50, 'freeze idle earlyMae high on level-up', `mae=${freezeMae}`)
  assert(followMae < 1e-6, 'truth-follow idle earlyMae≈0', `mae=${followMae}`)
  assert(
    (follow.model.find((m) => m.tSec === 15)?.hp ?? 0) === 1400,
    'truth-follow pins combat start at engage actual HP',
  )
}

// ── Finish lethal (Camille→Leona-like burst): marks + AA-at-mark + finish AA ─
{
  const atk = pinned(
    'Camille',
    2200,
    2400,
    { ad: 220, armor: 90, attackSpeed: 1.2 },
    { Q: 5, W: 5, E: 5, R: 3 },
  )
  const def = pinned(
    'Leona',
    900,
    2800,
    { ad: 100, armor: 120, attackSpeed: 0.7 },
    { Q: 5, W: 5, E: 5, R: 3 },
  )
  const actual = Array.from({ length: 9 }, (_, i) => ({
    tSec: i * 0.5,
    hp: 900,
    hpMax: 2800,
  }))
  const series = simulateKillWindowSeries({
    atk,
    def,
    actual,
    engageSec: 0,
    idleHp: 900,
    marks: [
      { tSec: 0.2, skillSlot: 3 },
      { tSec: 0.6, skillSlot: 1 },
      { tSec: 1.1, skillSlot: 4 },
      { tSec: 1.6, skillSlot: 2 },
    ],
    castPulseSec: 0.4,
    finishAa: { afterLastMark: true, maxAa: 4, aaAtEachMark: true },
    xhMode: 'off',
  })
  assert(series.firstLethalSec != null, 'finish path produces model lethal')
  assert(
    Math.abs(series.firstLethalSec! - 2) <= 2 || series.firstLethalSec! <= 4,
    'lethal within burst window',
    `lethal=${series.firstLethalSec}`,
  )
  assert(
    (series.model[series.model.length - 1]?.hp ?? 1) <= 0,
    'model end HP lethal',
  )
}

// ── P-anti: product default mark selection is non-drop ───────────────────────
{
  const actual = [
    { tSec: 0, hp: 1000 },
    { tSec: 1, hp: 1000 },
    { tSec: 2, hp: 800 },
    { tSec: 3, hp: 800 },
    { tSec: 4, hp: 400 },
  ]
  const marks = [
    { tSec: 0.5, skillSlot: 1 },
    { tSec: 1.5, skillSlot: 2 },
    { tSec: 2.1, skillSlot: 1 },
    { tSec: 3.5, skillSlot: 3 },
  ]
  const drop = selectKillWindowMarks({
    marks,
    selection: 'near_hp_drop',
    engageSec: 0,
    actual,
    markNearDropSec: 0.75,
    markDropMinHp: 15,
  })
  const product = selectKillWindowMarks({
    marks,
    selection: 'post_engage_killer_skills',
    engageSec: 1.0,
    actual,
  })
  assert(drop.marks.length < marks.length, 'drop filter keeps subset')
  assert(
    product.marks.every((m) => m.tSec >= 1.0 - 1e-9),
    'product post_engage keeps only post-engage marks',
  )
  assert(
    product.marks.length === 3,
    'product keeps all post-engage marks without HP-drop peek',
    `n=${product.marks.length}`,
  )
}

// ── Density-triggered min-gap: spam thins; spaced poke keeps all ─────────────
{
  const spam = [0, 0.2, 0.4, 0.6, 0.8, 1.0].map((tSec) => ({
    tSec,
    skillSlot: 3,
  }))
  const spaced = [0, 1.2, 2.5, 4.0].map((tSec) => ({ tSec, skillSlot: 1 }))
  const denseSpam = selectKillWindowMarks({
    marks: spam,
    selection: 'post_engage_killer_skills',
    engageSec: 0,
    markMinGapSec: 0.4,
    markDensityWindowSec: 0.5,
    markDenseMaxPerWindow: 1,
  })
  const denseSpaced = selectKillWindowMarks({
    marks: spaced,
    selection: 'post_engage_killer_skills',
    engageSec: 0,
    markMinGapSec: 0.4,
    markDensityWindowSec: 0.5,
    markDenseMaxPerWindow: 1,
  })
  assert(
    denseSpam.marks.length < spam.length,
    'density min-gap thins spam cluster',
    `n=${denseSpam.marks.length}`,
  )
  assert(
    denseSpaced.marks.length === spaced.length,
    'density min-gap keeps spaced poke marks',
    `n=${denseSpaced.marks.length}`,
  )
}

// ── Missing pins: matchup sibling refuses inventing HP ───────────────────────
{
  const atk = defaultLoadout('Camille')
  const def = defaultLoadout('Leona')
  // No liveStats.hp — must not invent
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
      markSelection: 'post_engage_killer_skills',
      engageSec: 0,
    },
  })
  assert(
    r.notes.some((n) => /missing HP pins/i.test(n)),
    'missing pins disclose continuous fallback',
  )
  assert(
    r.timing?.method !== 'kill_window_gate_action',
    'missing pins do not claim kill-window timing',
  )
}

// ── Track 2: item marks emit kind=item without shifting skill AA timing ─────
{
  const atk = pinned('Camille', 2200, 2400, {
    ad: 220,
    armor: 90,
    attackSpeed: 1.0,
  })
  const def = pinned('Leona', 1200, 2800, {
    ad: 100,
    armor: 120,
    attackSpeed: 0.7,
  })
  const actual = Array.from({ length: 21 }, (_, i) => ({
    tSec: i,
    hp: 1200,
    hpMax: 2800,
  }))
  const base = simulateKillWindowSeries({
    atk,
    def,
    actual,
    engageSec: 2,
    idleHp: 1200,
    marks: [
      { tSec: 3, skillSlot: 1 },
      { tSec: 6, skillSlot: 2 },
    ],
    castPulseSec: 0.4,
    finishAa: { afterLastMark: true, maxAa: 2, aaAtEachMark: true },
    xhMode: 'off',
  })
  const withItem = simulateKillWindowSeries({
    atk,
    def,
    actual,
    engageSec: 2,
    idleHp: 1200,
    marks: [
      { tSec: 3, skillSlot: 1 },
      { tSec: 4.5, kind: 'item', logOnly: true },
      { tSec: 6, skillSlot: 2 },
    ],
    castPulseSec: 0.4,
    finishAa: { afterLastMark: true, maxAa: 2, aaAtEachMark: true },
    xhMode: 'off',
  })
  const itemActs = withItem.modelActions.filter((a) => a.kind === 'item')
  assert(itemActs.length === 1, 'item mark emits one kind=item modelAction')
  assert(
    Math.abs(itemActs[0]!.tSec - 4.5) < 1e-9,
    'item modelAction keeps event time',
    `t=${itemActs[0]?.tSec}`,
  )
  assert(
    (itemActs[0]!.shareHint ?? 0) === 0,
    'default item emission is non-damage (shareHint=0)',
  )
  const skillBase = base.modelActions.filter((a) => a.kind === 'skill').length
  const skillWith = withItem.modelActions.filter((a) => a.kind === 'skill').length
  assert(skillBase === skillWith, 'item inventory does not drop skill modelActions')
  const endHpBase = base.model[base.model.length - 1]!.hp
  const endHpItem = withItem.model[withItem.model.length - 1]!.hp
  assert(
    Math.abs(endHpBase - endHpItem) < 1e-6,
    'non-damage item mark leaves HP path unchanged',
    `base=${endHpBase} item=${endHpItem}`,
  )
}

{
  const atk = pinned('Camille', 2000, 2000, { ad: 100, armor: 40, attackSpeed: 1.0 })
  const def = pinned('Leona', 1200, 1200, { ad: 80, armor: 0, attackSpeed: 0.7 })
  const actual = Array.from({ length: 8 }, (_, i) => ({
    tSec: i,
    hp: 1200,
    hpMax: 1200,
  }))
  const base = simulateKillWindowSeries({
    atk,
    def,
    actual,
    engageSec: 1,
    idleHp: 1200,
    marks: [{ tSec: 2, skillSlot: 1 }],
    castPulseSec: 0.4,
    finishAa: { afterLastMark: false, maxAa: 0, aaAtEachMark: false },
    xhMode: 'off',
  })
  const withAa = simulateKillWindowSeries({
    atk,
    def,
    actual,
    engageSec: 1,
    idleHp: 1200,
    marks: [
      { tSec: 2, skillSlot: 1 },
      { tSec: 3, kind: 'aa', share: 1 },
    ],
    castPulseSec: 0.4,
    finishAa: { afterLastMark: false, maxAa: 0, aaAtEachMark: false },
    xhMode: 'off',
  })
  const aaActs = withAa.modelActions.filter((a) => a.kind === 'aa')
  assert(aaActs.length === 1, 'one evented aa modelAction')
  assert((aaActs[0]!.shareHint ?? 0) > 0, 'damaging aa shareHint>0')
  const endBase = base.model[base.model.length - 1]!.hp
  const endAa = withAa.model[withAa.model.length - 1]!.hp
  assert(endAa < endBase - 1e-6, 'evented aa adds kit physical damage vs skill-only', `base=${endBase} aa=${endAa}`)
}

console.log(`killWindow.acceptance: ${passed.length} passed`)
for (const p of passed) {
  console.log(`  ok  ${p.name}${p.detail ? ` (${p.detail})` : ''}`)
}
