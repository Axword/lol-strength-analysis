/**
 * Research cross-check: simulateMatchup on a GRID kill window.
 *
 *   npx --yes tsx scripts/crosscheck_kill_window.ts \
 *     --input docs/canvases/_data/crosschecks-2970110-g1.json \
 *     --check 1 --segment burst \
 *     --out docs/canvases/_data/crosscheck-01-burst-model.json
 *
 * Segments:
 *   full  — whole extract window
 *   burst — from last sustained HP drop into kill (ignores mid-window regen)
 *
 * Honest limits: generated kits may remain; research only; not calculatorReady.
 */
import { readFileSync, writeFileSync, mkdirSync, existsSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { DatabaseSync } from 'node:sqlite'
import { simulateMatchup } from '../src/engine/combat'
import { getChampion } from '../src/data/champions'
import type { FighterLoadout, MatchupResult } from '../src/engine/types'
import { analyzeSqrtBins, binPhase } from './lib/crosscheck_sqrt_bins'

type FrameRow = {
  game_time_ms: number
  health: number | null
  health_max: number | null
  level?: number | null
  attack_damage?: number | null
  ability_power?: number | null
  armor?: number | null
  magic_resist?: number | null
  attack_speed?: number | null
  ability1_level?: number | null
  ability2_level?: number | null
  ability3_level?: number | null
  ability4_level?: number | null
  alive?: number | null
  items_json?: string | null
}

type CrossCheck = {
  tMs: number
  killerId: number
  victimId: number
  killerChamp: string
  victimChamp: string
  killerName: string
  victimName: string
  windowMs: [number, number]
  killerLevel?: number
  victimLevel?: number
  victimHp: FrameRow[]
  killerHp: FrameRow[]
}

type CrossCheckFile = {
  seriesId: string
  matchHint?: string
  crossChecks: CrossCheck[]
}

function argValue(flag: string, fallback = ''): string {
  const i = process.argv.indexOf(flag)
  return i >= 0 && process.argv[i + 1] ? process.argv[i + 1]! : fallback
}

function asPercentAs(champId: string, asWire: number | null | undefined): number {
  const base = getChampion(champId)?.stats.attackspeed ?? 0.625
  const pct = asWire == null || Number.isNaN(asWire) ? 100 : asWire
  return Math.max(0.2, base * (pct / 100))
}

function parseItemIds(frame: FrameRow): string[] {
  if (!frame.items_json) return []
  try {
    const raw = JSON.parse(frame.items_json) as unknown
    if (!Array.isArray(raw)) return []
    return raw
      .map((id) => Number(id))
      .filter((id) => Number.isFinite(id) && id > 0)
      .map((id) => String(id))
  } catch {
    return []
  }
}

function loadoutFromFrame(champId: string, level: number, frame: FrameRow): FighterLoadout {
  const hp = frame.health
  const hpMax = frame.health_max
  if (hp == null || hpMax == null || hpMax <= 0) {
    throw new Error(`missing HP pins for ${champId}`)
  }
  return {
    championId: champId,
    level: Math.max(1, level || Number(frame.level ?? 1)),
    itemIds: parseItemIds(frame),
    runeId: null,
    ranks: {
      Q: Math.max(0, Number(frame.ability1_level ?? 0)),
      W: Math.max(0, Number(frame.ability2_level ?? 0)),
      E: Math.max(0, Number(frame.ability3_level ?? 0)),
      R: Math.max(0, Number(frame.ability4_level ?? 0)),
    },
    alive: frame.alive !== 0,
    liveStats: {
      hp,
      hpMax,
      ad: Number(frame.attack_damage ?? 0),
      ap: Number(frame.ability_power ?? 0),
      armor: Number(frame.armor ?? 0),
      mr: Number(frame.magic_resist ?? 30),
      attackSpeed: asPercentAs(champId, frame.attack_speed),
    },
  }
}

/** Nearest frame by game_time_ms (for engage re-pin). */
function nearestFrame(rows: FrameRow[], targetMs: number): FrameRow | null {
  const usable = rows.filter((r) => r.health != null && r.health_max != null)
  if (!usable.length) return null
  let best = usable[0]!
  let bestD = Math.abs(best.game_time_ms - targetMs)
  for (const r of usable) {
    const d = Math.abs(r.game_time_ms - targetMs)
    if (d < bestD) {
      best = r
      bestD = d
    }
  }
  return best
}

/**
 * Detect last lethal burst: walk backward from the kill sample while HP is
 * flat or falling. Stop when the previous sample shows meaningful regen
 * (HP rose by more than 5). That puts the burst pin after disengage/heal.
 */
function detectBurstStartMs(victimHp: FrameRow[], killMs: number): number {
  const rows = victimHp
    .filter((r) => r.health != null)
    .sort((a, b) => a.game_time_ms - b.game_time_ms)
  if (rows.length < 2) return rows[0]?.game_time_ms ?? Math.max(0, killMs - 5000)

  // Prefer the last sample at/before kill; else first post-kill zero/min.
  let i = rows.length - 1
  while (i > 0 && rows[i]!.game_time_ms > killMs) i--
  // If that sample is still full HP, step forward to the first drop after it.
  while (i + 1 < rows.length && (rows[i]!.health as number) > 0) {
    const next = rows[i + 1]!.health as number
    if (next < (rows[i]!.health as number) - 5) break
    if (rows[i + 1]!.game_time_ms > killMs + 2000) break
    i++
  }

  while (i > 0) {
    const cur = rows[i]!.health as number
    const prev = rows[i - 1]!.health as number
    // Meaningful heal / disengage regen → burst starts at current index.
    if (prev < cur - 5) break
    // Falling or flat (allow 5 HP noise): include previous sample.
    i--
  }
  return rows[i]!.game_time_ms
}

function sliceFrames(rows: FrameRow[], startMs: number, endMs: number): FrameRow[] {
  return rows.filter((r) => r.game_time_ms >= startMs && r.game_time_ms <= endMs)
}

function sampleActual(rows: FrameRow[], windowStartMs: number) {
  return rows
    .filter((r) => r.health != null && r.health_max != null)
    .map((r) => ({
      tSec: (r.game_time_ms - windowStartMs) / 1000,
      hp: r.health as number,
      hpMax: r.health_max as number,
    }))
}

/** Count killer skill_used in [startMs, endMs] from slim sqlite (diagnostic). */
function countKillerSkills(
  sqlitePath: string | null,
  killerId: number,
  startMs: number,
  endMs: number,
): number | null {
  if (!sqlitePath || !existsSync(sqlitePath)) return null
  const db = new DatabaseSync(sqlitePath, { readOnly: true })
  try {
    const row = db
      .prepare(
        `SELECT COUNT(*) AS n FROM events
         WHERE schema = 'skill_used'
           AND participant_id = ?
           AND game_time_ms >= ? AND game_time_ms <= ?`,
      )
      .get(killerId, startMs, endMs) as { n: number } | undefined
    return Number(row?.n ?? 0)
  } finally {
    db.close()
  }
}

/** First killer skill_used time (sec from windowStart), or null. */
function firstKillerSkillSec(
  sqlitePath: string | null,
  killerId: number,
  windowStartMs: number,
  windowEndMs: number,
): number | null {
  if (!sqlitePath || !existsSync(sqlitePath)) return null
  const db = new DatabaseSync(sqlitePath, { readOnly: true })
  try {
    const row = db
      .prepare(
        `SELECT MIN(game_time_ms) AS t FROM events
         WHERE schema = 'skill_used'
           AND participant_id = ?
           AND game_time_ms >= ? AND game_time_ms <= ?`,
      )
      .get(killerId, windowStartMs, windowEndMs) as { t: number | null } | undefined
    if (row?.t == null) return null
    return (Number(row.t) - windowStartMs) / 1000
  } finally {
    db.close()
  }
}

/** First time actual victim HP drops by > threshold from series start. */
function firstVictimDropSec(
  actual: { tSec: number; hp: number }[],
  dropThreshold = 30,
): number | null {
  if (actual.length < 2) return null
  const startHp = actual[0]!.hp
  for (const a of actual) {
    if (startHp - a.hp > dropThreshold) return a.tSec
  }
  return null
}

function maeOf(
  actual: { tSec: number; hp: number }[],
  model: { tSec: number; hp: number }[],
  t0 = 0,
  t1 = Infinity,
): number | null {
  let sum = 0
  let n = 0
  for (let i = 0; i < actual.length; i++) {
    const a = actual[i]!
    const m = model[i]
    if (!m || a.tSec < t0 - 1e-9 || a.tSec > t1 + 1e-9) continue
    sum += Math.abs(m.hp - a.hp)
    n++
  }
  return n === 0 ? null : sum / n
}

/**
 * Early-track class (diagnostic only — does not change simulateMatchup).
 * falseAllIn: model would fight while reality shows no casts + flat HP.
 */
function classifyEarlyBin(opts: {
  actualDrop: number | null
  modelDrop: number | null
  killerSkills: number | null
  meanSignedErr: number | null
}): {
  class: 'false_all_in' | 'sparse_engage' | 'teamfight_under' | 'mixed' | 'unknown'
  falseAllIn: boolean
  note: string
} {
  const { actualDrop, modelDrop, killerSkills, meanSignedErr } = opts
  if (actualDrop == null || modelDrop == null) {
    return {
      class: 'unknown',
      falseAllIn: false,
      note: 'missing early-bin HP samples',
    }
  }
  // Require observed skill count === 0 (unknown sqlite → do not claim false_all_in).
  const falseAllIn = killerSkills === 0 && actualDrop < 30 && modelDrop > 80
  if (falseAllIn) {
    return {
      class: 'false_all_in',
      falseAllIn: true,
      note: 'No real casts + flat HP; model still deals damage. Fix class = engage gate, not kit coeff.',
    }
  }
  if (killerSkills != null && killerSkills <= 1 && (meanSignedErr ?? 0) < -50) {
    return {
      class: 'sparse_engage',
      falseAllIn: false,
      note: 'Few killer casts vs continuous model clock.',
    }
  }
  if ((meanSignedErr ?? 0) > 100 && actualDrop > modelDrop + 200) {
    return {
      class: 'teamfight_under',
      falseAllIn: false,
      note: 'Actual drop >> model — assists/AoE likely. Do not buff 1v1 damage.',
    }
  }
  return {
    class: 'mixed',
    falseAllIn: false,
    note: 'No single early class dominant.',
  }
}

/**
 * Late-track class (diagnostic only).
 * early_poisoned: model already ~dead before late bin — do not "fix late."
 */
function classifyLateBin(opts: {
  modelHpAtLateStart: number | null
  actualHpAtLateStart: number | null
  actualDrop: number | null
  modelDrop: number | null
  meanSignedErr: number | null
  lethalErrorSec: number | null
  killedInModel: boolean
}): {
  class:
    | 'early_poisoned'
    | 'finish_path_mismatch'
    | 'finish_under'
    | 'lethal_ok_path_off'
    | 'mixed'
    | 'unknown'
  earlyPoisoned: boolean
  note: string
} {
  const {
    modelHpAtLateStart,
    actualHpAtLateStart,
    actualDrop,
    modelDrop,
    meanSignedErr,
    lethalErrorSec,
    killedInModel,
  } = opts
  if (modelHpAtLateStart == null || actualHpAtLateStart == null) {
    return {
      class: 'unknown',
      earlyPoisoned: false,
      note: 'missing late-bin HP samples',
    }
  }
  // Model already shredded while victim still healthy → late variance is mostly
  // early-track poison (not a separate finish bug). Threshold: model ≤30% of
  // actual at late start (and victim still meaningful HP).
  const earlyPoisoned =
    actualHpAtLateStart >= 200 &&
    modelHpAtLateStart <= Math.max(30, 0.3 * actualHpAtLateStart)
  if (earlyPoisoned) {
    return {
      class: 'early_poisoned',
      earlyPoisoned: true,
      note: 'Model already far below actual before late bin. Fix early track first — do not tune finish damage.',
    }
  }
  if (
    actualDrop != null &&
    modelDrop != null &&
    actualDrop > modelDrop + 150 &&
    (meanSignedErr ?? 0) > 0
  ) {
    return {
      class: 'finish_under',
      earlyPoisoned: false,
      note: 'Actual finish drop >> model; model HP stays high. Assists/AoE or missing burst — not a global AD buff.',
    }
  }
  if (
    killedInModel &&
    lethalErrorSec != null &&
    Math.abs(lethalErrorSec) <= 1.0 &&
    (meanSignedErr == null || Math.abs(meanSignedErr) > 100)
  ) {
    return {
      class: 'lethal_ok_path_off',
      earlyPoisoned: false,
      note: 'Kill clock close; HP path still wrong in late bin.',
    }
  }
  if (
    actualDrop != null &&
    modelDrop != null &&
    Math.abs(actualDrop - modelDrop) > 100
  ) {
    return {
      class: 'finish_path_mismatch',
      earlyPoisoned: false,
      note: 'Late HP drop shape differs (combo timing / cast order).',
    }
  }
  return {
    class: 'mixed',
    earlyPoisoned: false,
    note: 'No single late class dominant.',
  }
}

function runModelSeries(
  atk: FighterLoadout,
  def: FighterLoadout,
  actual: { tSec: number; hp: number; hpMax: number }[],
  durationSec: number,
): { model: { tSec: number; hp: number }[]; full: MatchupResult } {
  const model = actual.map((a) => {
    const dur = Math.max(0.05, a.tSec)
    const r = simulateMatchup({
      blue: [atk],
      red: [def],
      engager: 'blue',
      mode: 'extended',
      durationSec: dur,
      xhMode: 'off',
    })
    return { tSec: a.tSec, hp: r.red.targets?.[0]?.hpRemaining ?? 0 }
  })
  const full = simulateMatchup({
    blue: [atk],
    red: [def],
    engager: 'blue',
    mode: 'extended',
    durationSec,
    xhMode: 'off',
  })
  return { model, full }
}

type GateMode = 'naive' | 'repin'

/**
 * Research-only engage gate. Does NOT change product combat.ts.
 *
 * - naive: fight loadouts = window-start pins; clock = (t − engageSec)
 * - repin: idle holds window-start victim HP; post-engage fights with
 *   loadouts re-pinned at engage time (HP/combat/ranks/items)
 */
function runGatedModelSeries(
  atkIdle: FighterLoadout,
  defIdle: FighterLoadout,
  actual: { tSec: number; hp: number; hpMax: number }[],
  durationSec: number,
  engageSec: number,
  mode: GateMode = 'naive',
  atkEngage?: FighterLoadout,
  defEngage?: FighterLoadout,
): { model: { tSec: number; hp: number }[]; full: MatchupResult } {
  const idleHp = defIdle.liveStats?.hp ?? actual[0]?.hp ?? 0
  const fightAtk = mode === 'repin' && atkEngage ? atkEngage : atkIdle
  const fightDef = mode === 'repin' && defEngage ? defEngage : defIdle
  const model = actual.map((a) => {
    if (a.tSec <= engageSec + 1e-9) {
      return { tSec: a.tSec, hp: idleHp }
    }
    const dur = Math.max(0.05, a.tSec - engageSec)
    const r = simulateMatchup({
      blue: [fightAtk],
      red: [fightDef],
      engager: 'blue',
      mode: 'extended',
      durationSec: dur,
      xhMode: 'off',
    })
    return { tSec: a.tSec, hp: r.red.targets?.[0]?.hpRemaining ?? 0 }
  })
  const gatedDur = Math.max(0.05, durationSec - engageSec)
  const full = simulateMatchup({
    blue: [fightAtk],
    red: [fightDef],
    engager: 'blue',
    mode: 'extended',
    durationSec: gatedDur,
    xhMode: 'off',
  })
  return { model, full }
}

function scoreGatedSeries(opts: {
  actual: { tSec: number; hp: number; hpMax: number }[]
  baselineModel: { tSec: number; hp: number }[]
  gatedModel: { tSec: number; hp: number }[]
  gatedFull: MatchupResult
  engageSec: number
  killOffsetSec: number
  earlyEndSec: number
  lateBin: { tStartSec: number; tEndSec: number } | null | undefined
  lateActual: { tSec: number; hp: number }[]
  lateActualDrop: number | null
  baselineMae: number | null
  baselineEarlyPoisoned: boolean
}): {
  maeHp: number | null
  earlyMaeHp: number | null
  lateMaeHp: number | null
  lethalErrorSec: number | null
  earlyPoisoned: boolean
  lateClass: string
  killedInModel: boolean
  delta: {
    maeHp: number | null
    earlyMaeHp: number | null
    lateMaeHp: number | null
  }
} {
  const {
    actual,
    baselineModel,
    gatedModel,
    gatedFull,
    engageSec,
    killOffsetSec,
    earlyEndSec,
    lateBin,
    lateActual,
    lateActualDrop,
    baselineMae,
    baselineEarlyPoisoned,
  } = opts
  const gatedLethal =
    gatedFull.timing?.firstLethalSec == null
      ? null
      : gatedFull.timing.firstLethalSec + engageSec
  const gatedLethalErr =
    gatedLethal == null ? null : gatedLethal - killOffsetSec
  const gatedKilled =
    (gatedFull.red.targets?.[0]?.hpRemaining ?? 1) <= 0 ||
    gatedFull.timing?.firstLethalSec != null
  const gLateModel = lateBin
    ? gatedModel.filter(
        (a) =>
          a.tSec >= lateBin.tStartSec - 1e-6 && a.tSec <= lateBin.tEndSec + 1e-6,
      )
    : []
  const gLateDrop =
    gLateModel.length >= 2
      ? gLateModel[0]!.hp - gLateModel[gLateModel.length - 1]!.hp
      : null
  let meanSigned: number | null = null
  if (gLateModel.length && lateActual.length) {
    let s = 0
    let n = 0
    for (const a of lateActual) {
      const gm = gatedModel.find((m) => Math.abs(m.tSec - a.tSec) < 1e-6)
      if (!gm) continue
      s += gm.hp - a.hp
      n++
    }
    meanSigned = n ? s / n : null
  }
  const gLateCls = classifyLateBin({
    modelHpAtLateStart: gLateModel[0]?.hp ?? null,
    actualHpAtLateStart: lateActual[0]?.hp ?? null,
    actualDrop: lateActualDrop,
    modelDrop: gLateDrop,
    meanSignedErr: meanSigned,
    lethalErrorSec: gatedLethalErr,
    killedInModel: gatedKilled,
  })
  const maeGated = maeOf(actual, gatedModel)
  const earlyMaeBase = maeOf(actual, baselineModel, 0, earlyEndSec)
  const earlyMaeGated = maeOf(actual, gatedModel, 0, earlyEndSec)
  const lateMaeBase =
    lateBin == null
      ? null
      : maeOf(actual, baselineModel, lateBin.tStartSec, lateBin.tEndSec)
  const lateMaeGated =
    lateBin == null
      ? null
      : maeOf(actual, gatedModel, lateBin.tStartSec, lateBin.tEndSec)
  void baselineEarlyPoisoned
  return {
    maeHp: maeGated,
    earlyMaeHp: earlyMaeGated,
    lateMaeHp: lateMaeGated,
    lethalErrorSec: gatedLethalErr,
    earlyPoisoned: gLateCls.earlyPoisoned,
    lateClass: gLateCls.class,
    killedInModel: gatedKilled,
    delta: {
      maeHp: baselineMae != null && maeGated != null ? maeGated - baselineMae : null,
      earlyMaeHp:
        earlyMaeBase != null && earlyMaeGated != null
          ? earlyMaeGated - earlyMaeBase
          : null,
      lateMaeHp:
        lateMaeBase != null && lateMaeGated != null
          ? lateMaeGated - lateMaeBase
          : null,
    },
  }
}

function main() {
  const inputPath = resolve(
    argValue('--input', 'docs/canvases/_data/crosschecks-2970110-g1.json'),
  )
  const checkN = Math.max(1, Number(argValue('--check', '1')))
  const segment = (argValue('--segment', 'full') || 'full').toLowerCase()
  const gateResearch = process.argv.includes('--gate-research')
  const outPath = resolve(
    argValue(
      '--out',
      `docs/canvases/_data/crosscheck-0${checkN}-${segment}-model.json`,
    ),
  )

  const file = JSON.parse(readFileSync(inputPath, 'utf8')) as CrossCheckFile
  const check = file.crossChecks[checkN - 1]
  if (!check) throw new Error(`missing cross-check #${checkN}`)

  const defaultSqlite = resolve(
    `artifacts/pro-grid/${file.seriesId}/timeline.g1.slim.sqlite`,
  )
  const sqlitePath = argValue('--sqlite', defaultSqlite)

  let windowStart = check.windowMs[0]
  let windowEnd = Math.max(check.windowMs[1], check.tMs + 2000)
  let burstStartMs: number | null = null

  if (segment === 'burst') {
    burstStartMs = detectBurstStartMs(check.victimHp, check.tMs)
    windowStart = burstStartMs
    windowEnd = check.tMs + 2000
  } else if (segment !== 'full') {
    throw new Error(`unknown --segment ${segment} (use full|burst)`)
  }

  const killerRows = sliceFrames(check.killerHp, windowStart, windowEnd)
  const victimRows = sliceFrames(check.victimHp, windowStart, windowEnd)
  const killerFrame = killerRows[0] ?? check.killerHp.find((r) => r.game_time_ms >= windowStart)
  const victimFrame = victimRows[0] ?? check.victimHp.find((r) => r.game_time_ms >= windowStart)
  if (!killerFrame || !victimFrame) throw new Error('missing segment start frames')

  const durationSec = Math.max(1, (windowEnd - windowStart) / 1000)
  const killOffsetSec = (check.tMs - windowStart) / 1000

  const atk = loadoutFromFrame(
    check.killerChamp,
    check.killerLevel ?? Number(killerFrame.level ?? 1),
    killerFrame,
  )
  const def = loadoutFromFrame(
    check.victimChamp,
    check.victimLevel ?? Number(victimFrame.level ?? 1),
    victimFrame,
  )

  const actual = sampleActual(victimRows.length ? victimRows : check.victimHp, windowStart)
  const { model, full } = runModelSeries(atk, def, actual, durationSec)

  const errors = actual.map((a, i) => ({
    tSec: a.tSec,
    actualHp: a.hp,
    modelHp: model[i]!.hp,
    absErr: Math.abs(model[i]!.hp - a.hp),
    signedErr: model[i]!.hp - a.hp,
  }))
  const mae =
    errors.length === 0 ? null : errors.reduce((s, e) => s + e.absErr, 0) / errors.length

  const sqrtBins = analyzeSqrtBins(
    errors.map((e) => ({
      tSec: e.tSec,
      signedErr: e.signedErr,
      absErr: e.absErr,
    })),
    durationSec,
  )
  const top = sqrtBins.optimizeOrder[0]
  const topPhase =
    top == null ? null : binPhase(top.index, sqrtBins.binCount)

  const earlyBin = sqrtBins.bins[0]
  const earlyEndSec = earlyBin?.tEndSec ?? sqrtBins.pieceWidthSec
  const earlyActual = actual.filter((a) => a.tSec <= earlyEndSec + 1e-6)
  const earlyModel = model.filter((a) => a.tSec <= earlyEndSec + 1e-6)
  const actualDrop =
    earlyActual.length >= 2
      ? earlyActual[0]!.hp - earlyActual[earlyActual.length - 1]!.hp
      : null
  const modelDrop =
    earlyModel.length >= 2
      ? earlyModel[0]!.hp - earlyModel[earlyModel.length - 1]!.hp
      : null
  const earlyEndMs = windowStart + Math.round(earlyEndSec * 1000)
  const killerSkills = countKillerSkills(
    sqlitePath,
    check.killerId,
    windowStart,
    earlyEndMs,
  )
  const earlyTrack = {
    tRangeSec: [0, earlyEndSec] as [number, number],
    actualHpDrop: actualDrop,
    modelHpDrop: modelDrop,
    killerSkillUsed: killerSkills,
    meanSignedErr: earlyBin?.meanSignedErr ?? null,
    maeHp: earlyBin?.maeHp ?? null,
    ...classifyEarlyBin({
      actualDrop,
      modelDrop,
      killerSkills,
      meanSignedErr: earlyBin?.meanSignedErr ?? null,
    }),
    diagnosticOnly: true as const,
    doNotFitOnThisSample: true as const,
  }

  const modelFirstLethalSec = full.timing?.firstLethalSec ?? null
  const lethalErrorSec =
    modelFirstLethalSec == null ? null : modelFirstLethalSec - killOffsetSec
  const killedInModel =
    (full.red.targets?.[0]?.hpRemaining ?? 1) <= 0 || modelFirstLethalSec != null

  // Prefer highest-priority late-phase bin; else last bin.
  const lateCandidates = sqrtBins.bins.filter(
    (b) => binPhase(b.index, sqrtBins.binCount) === 'late',
  )
  const lateBin =
    (lateCandidates.length
      ? [...lateCandidates].sort(
          (a, b) => (b.priority ?? -1) - (a.priority ?? -1),
        )[0]
      : null) ?? sqrtBins.bins[sqrtBins.bins.length - 1]
  const lateActual = lateBin
    ? actual.filter(
        (a) => a.tSec >= lateBin.tStartSec - 1e-6 && a.tSec <= lateBin.tEndSec + 1e-6,
      )
    : []
  const lateModel = lateBin
    ? model.filter(
        (a) => a.tSec >= lateBin.tStartSec - 1e-6 && a.tSec <= lateBin.tEndSec + 1e-6,
      )
    : []
  const lateActualDrop =
    lateActual.length >= 2
      ? lateActual[0]!.hp - lateActual[lateActual.length - 1]!.hp
      : null
  const lateModelDrop =
    lateModel.length >= 2
      ? lateModel[0]!.hp - lateModel[lateModel.length - 1]!.hp
      : null
  const lateKillerSkills = lateBin
    ? countKillerSkills(
        sqlitePath,
        check.killerId,
        windowStart + Math.round(lateBin.tStartSec * 1000),
        windowStart + Math.round(lateBin.tEndSec * 1000),
      )
    : null
  const lateTrack = {
    tRangeSec: lateBin
      ? ([lateBin.tStartSec, lateBin.tEndSec] as [number, number])
      : null,
    actualHpAtStart: lateActual[0]?.hp ?? null,
    modelHpAtStart: lateModel[0]?.hp ?? null,
    actualHpDrop: lateActualDrop,
    modelHpDrop: lateModelDrop,
    killerSkillUsed: lateKillerSkills,
    meanSignedErr: lateBin?.meanSignedErr ?? null,
    maeHp: lateBin?.maeHp ?? null,
    varianceSignedErr: lateBin?.varianceSignedErr ?? null,
    lethalErrorSec,
    ...classifyLateBin({
      modelHpAtLateStart: lateModel[0]?.hp ?? null,
      actualHpAtLateStart: lateActual[0]?.hp ?? null,
      actualDrop: lateActualDrop,
      modelDrop: lateModelDrop,
      meanSignedErr: lateBin?.meanSignedErr ?? null,
      lethalErrorSec,
      killedInModel,
    }),
    diagnosticOnly: true as const,
    doNotFitOnThisSample: true as const,
  }

  const summary = {
    schema: 'pro-grid-crosscheck-model-v4',
    seriesId: file.seriesId,
    matchHint: file.matchHint,
    checkIndex: checkN,
    segment,
    burstStartMs,
    matchup: `${check.killerChamp} → ${check.victimChamp}`,
    players: `${check.killerName} → ${check.victimName}`,
    windowMs: [windowStart, windowEnd] as [number, number],
    durationSec,
    actualKillOffsetSec: killOffsetSec,
    modelFirstLethalSec,
    lethalErrorSec,
    method: full.timing?.method ?? null,
    winner: full.winner,
    itemIds: { killer: atk.itemIds, victim: def.itemIds },
    modelTrust: full.modelTrust,
    metrics: {
      maeHp: mae,
      actualEndHp: actual[actual.length - 1]?.hp ?? null,
      modelEndHp: model[model.length - 1]?.hp ?? null,
      modelEndHpFullWindow: full.red.targets?.[0]?.hpRemaining ?? null,
    },
    sqrtBins,
    focus: {
      phase: topPhase,
      binIndex: top?.index ?? null,
      tRangeSec: top ? ([top.tStartSec, top.tEndSec] as [number, number]) : null,
      priority: top?.priority ?? null,
      varianceSignedErr: top?.varianceSignedErr ?? null,
      note: 'Diagnostic only — do not fit engine coeffs to this bin on this fight.',
    },
    earlyTrack,
    lateTrack,
    verdict: {
      killedInModel,
    },
    caveats: [
      ...(full.timing?.caveats ?? []),
      atk.itemIds.length === 0 ? 'killer itemIds empty at segment start' : 'killer items pinned',
      def.itemIds.length === 0 ? 'victim itemIds empty at segment start' : 'victim items pinned',
      'sqrtBins: diagnostic ranking only — anti-overfit',
      earlyTrack.falseAllIn
        ? 'earlyTrack:false_all_in — engage gate class (not kit coeff)'
        : `earlyTrack:${earlyTrack.class}`,
      lateTrack.earlyPoisoned
        ? 'lateTrack:early_poisoned — fix early first'
        : `lateTrack:${lateTrack.class}`,
      'research only — not calculatorReady',
    ],
    actual,
    model,
    errors,
  } as Record<string, unknown>

  if (gateResearch) {
    const skillEngage = firstKillerSkillSec(
      sqlitePath,
      check.killerId,
      windowStart,
      windowEnd,
    )
    const dropEngage = firstVictimDropSec(actual)
    let engageSec: number | null = null
    let engageSource: 'killer_skill' | 'victim_hp_drop' | 'none' = 'none'
    if (skillEngage != null) {
      engageSec = skillEngage
      engageSource = 'killer_skill'
    } else if (dropEngage != null) {
      engageSec = dropEngage
      engageSource = 'victim_hp_drop'
    }

    const earlyMaeBase = maeOf(actual, model, 0, earlyEndSec)
    const lateMaeBase =
      lateBin == null
        ? null
        : maeOf(actual, model, lateBin.tStartSec, lateBin.tEndSec)
    const baselineBlock = {
      maeHp: mae,
      earlyMaeHp: earlyMaeBase,
      lateMaeHp: lateMaeBase,
      lethalErrorSec,
      earlyPoisoned: lateTrack.earlyPoisoned,
      falseAllIn: earlyTrack.falseAllIn,
      killedInModel,
    }

    const scoreOptsBase = {
      actual,
      baselineModel: model,
      engageSec: engageSec ?? 0,
      killOffsetSec,
      earlyEndSec,
      lateBin,
      lateActual,
      lateActualDrop,
      baselineMae: mae,
      baselineEarlyPoisoned: lateTrack.earlyPoisoned,
    }

    let naiveScore: ReturnType<typeof scoreGatedSeries> | null = null
    let repinScore: ReturnType<typeof scoreGatedSeries> | null = null
    let engagePin: {
      killerHp: number
      victimHp: number
      alignMs: number
      itemIds: { killer: string[]; victim: string[] }
    } | null = null

    if (engageSec != null) {
      const engageMs = windowStart + Math.round(engageSec * 1000)
      const kEngFrame =
        nearestFrame(check.killerHp, engageMs) ??
        nearestFrame(killerRows, engageMs)
      const vEngFrame =
        nearestFrame(check.victimHp, engageMs) ??
        nearestFrame(victimRows, engageMs)
      if (!kEngFrame || !vEngFrame) {
        throw new Error(`missing engage re-pin frames at t+${engageSec}s`)
      }
      const atkEngage = loadoutFromFrame(
        check.killerChamp,
        Number(kEngFrame.level ?? check.killerLevel ?? 1),
        kEngFrame,
      )
      const defEngage = loadoutFromFrame(
        check.victimChamp,
        Number(vEngFrame.level ?? check.victimLevel ?? 1),
        vEngFrame,
      )
      engagePin = {
        killerHp: atkEngage.liveStats!.hp,
        victimHp: defEngage.liveStats!.hp,
        alignMs: Math.max(
          Math.abs(kEngFrame.game_time_ms - engageMs),
          Math.abs(vEngFrame.game_time_ms - engageMs),
        ),
        itemIds: { killer: atkEngage.itemIds, victim: defEngage.itemIds },
      }

      const naive = runGatedModelSeries(atk, def, actual, durationSec, engageSec, 'naive')
      naiveScore = scoreGatedSeries({
        ...scoreOptsBase,
        gatedModel: naive.model,
        gatedFull: naive.full,
      })

      const repin = runGatedModelSeries(
        atk,
        def,
        actual,
        durationSec,
        engageSec,
        'repin',
        atkEngage,
        defEngage,
      )
      repinScore = scoreGatedSeries({
        ...scoreOptsBase,
        gatedModel: repin.model,
        gatedFull: repin.full,
      })
    }

    const preferRepin = repinScore != null
    const primary = preferRepin ? repinScore : naiveScore

    summary.gateResearch = {
      schema: 'pro-grid-gate-research-v2',
      diagnosticOnly: true,
      doNotFitOnThisSample: true,
      productPathUnchanged: true,
      engageSec,
      engageSource,
      engagePin,
      baseline: baselineBlock,
      /** @deprecated use gatedNaive — kept for older readers */
      gated: primary,
      gatedNaive: naiveScore,
      gatedRepin: repinScore,
      delta: primary?.delta ?? null,
      deltaRepinVsNaive:
        naiveScore && repinScore
          ? {
              maeHp:
                naiveScore.maeHp != null && repinScore.maeHp != null
                  ? repinScore.maeHp - naiveScore.maeHp
                  : null,
              earlyMaeHp:
                naiveScore.earlyMaeHp != null && repinScore.earlyMaeHp != null
                  ? repinScore.earlyMaeHp - naiveScore.earlyMaeHp
                  : null,
              lateMaeHp:
                naiveScore.lateMaeHp != null && repinScore.lateMaeHp != null
                  ? repinScore.lateMaeHp - naiveScore.lateMaeHp
                  : null,
              lethalErrorSec:
                naiveScore.lethalErrorSec != null &&
                repinScore.lethalErrorSec != null
                  ? repinScore.lethalErrorSec - naiveScore.lethalErrorSec
                  : null,
            }
          : null,
      shipGate: false,
      transferNote:
        'Prefer gatedRepin. Ship only if early wins hold, lethal ±2s, late not worse, check03 early not hurt — plus holdout.',
      note: 'Research overlay only. Not wired into simulateMatchup / calculator.',
    }
    ;(summary.caveats as string[]).push(
      'gateResearch: naive+repin overlay only — not product',
    )
  }

  mkdirSync(dirname(outPath), { recursive: true })
  writeFileSync(outPath, JSON.stringify(summary, null, 2) + '\n', 'utf8')
  const gate = summary.gateResearch as Record<string, unknown> | undefined
  console.log(
    JSON.stringify(
      {
        ok: true,
        out: outPath,
        check: checkN,
        segment,
        matchup: summary.matchup,
        itemIds: summary.itemIds,
        actualKillOffsetSec: killOffsetSec,
        modelFirstLethalSec: summary.modelFirstLethalSec,
        lethalErrorSec: summary.lethalErrorSec,
        maeHp: mae,
        modelEndHp: summary.metrics.modelEndHpFullWindow,
        killedInModel: summary.verdict.killedInModel,
        sqrtBins: {
          pieceWidthSec: sqrtBins.pieceWidthSec,
          binCount: sqrtBins.binCount,
          focusPhase: topPhase,
          optimizeOrder: sqrtBins.optimizeOrder.slice(0, 3).map((b) => ({
            index: b.index,
            t: [b.tStartSec, b.tEndSec],
            variance: b.varianceSignedErr,
            priority: b.priority,
          })),
        },
        earlyTrack: {
          class: earlyTrack.class,
          falseAllIn: earlyTrack.falseAllIn,
          actualHpDrop: earlyTrack.actualHpDrop,
          modelHpDrop: earlyTrack.modelHpDrop,
          killerSkillUsed: earlyTrack.killerSkillUsed,
        },
        lateTrack: {
          class: lateTrack.class,
          earlyPoisoned: lateTrack.earlyPoisoned,
          tRangeSec: lateTrack.tRangeSec,
          actualHpAtStart: lateTrack.actualHpAtStart,
          modelHpAtStart: lateTrack.modelHpAtStart,
          actualHpDrop: lateTrack.actualHpDrop,
          modelHpDrop: lateTrack.modelHpDrop,
          killerSkillUsed: lateTrack.killerSkillUsed,
          lethalErrorSec: lateTrack.lethalErrorSec,
        },
        ...(gate
          ? {
              gateResearch: {
                engageSec: gate.engageSec,
                engageSource: gate.engageSource,
                engagePin: gate.engagePin,
                baseline: gate.baseline,
                gatedNaive: gate.gatedNaive,
                gatedRepin: gate.gatedRepin,
                deltaRepinVsNaive: gate.deltaRepinVsNaive,
                shipGate: gate.shipGate,
              },
            }
          : {}),
      },
      null,
      2,
    ),
  )
}

main()
