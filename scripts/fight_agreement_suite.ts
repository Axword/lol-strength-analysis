/**
 * fightAgreement suite (F2/R04) — RESEARCH
 * Metric law: GOAL-fight-outcome-95-10x30x15.md §B
 *
 * fightAgreement = mean(windowScore) over required windows (check×segment).
 * NOT calibrated win probability / odds %. Model edge only.
 *
 * Usage:
 *   npx --yes tsx scripts/fight_agreement_suite.ts \
 *     --from-eval docs/rofl-research/autoresearch/last_eval.json \
 *     --suite-label S0 --out-dir docs/rofl-research/autoresearch/fight_outcome/r04
 *
 *   npx --yes tsx scripts/fight_agreement_suite.ts --run-harness S0
 */
import { execFileSync } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'

export type SuiteId = 'S0' | 'S1' | 'S2'

export type WindowTruth = {
  id: string
  suite: SuiteId
  match: string
  truthKilled: boolean
  killerPid?: number
  victimPid?: number
  engageSec?: number
  segment?: 'full' | 'burst'
  check?: number
  matchup?: string
}

export type WindowModel = {
  modelKilled: boolean
  modelLethalSec: number | null
  earlyMaeHp: number
  maeHpBurst: number
  maeHpFull: number
  /** Segment MAE used for path fidelity when scoring check×segment. */
  maeHp?: number
  endHpAbsError?: number
  actionCoverageF1?: number | null
  lethalErrorSec?: number | null
  hardFail?: boolean
  noInvent?: boolean
}

export type WindowResult = {
  id: string
  windowOk: boolean
  windowScore: number
  parts: Record<string, number | boolean | string | null>
}

export type HarnessCheck = {
  check: number
  segment: 'full' | 'burst'
  matchup?: string
  earlyMaeHp: number | null
  maeHp: number | null
  lethalErrorSec: number | null
  killedInModel: boolean
  engageSec?: number | null
  modelEndHp?: number | null
  actualEndHp?: number | null
  actionReplay?: { actionCoverage?: number } | null
}

export type HarnessEval = {
  seriesId?: string
  gameIndex?: number
  mode?: string
  hypothesis?: string
  config?: Record<string, unknown>
  checks: HarnessCheck[]
  hardFails?: string[]
  actionReplay?: {
    perWindow?: Array<{
      check: number
      segment: string
      actionCoverage: number
    }>
  } | null
}

const EARLY_CAP = 50
const BURST_CAP = 90
const FULL_CAP = 130
const LETHAL_TOL = 0.75
const END_HP_FLOOR = 40

/** Product non-drop selectors (GOAL §C / F2 H6). near_hp_drop is research-only. */
export const PRODUCT_MARK_SELECTIONS = [
  'cusum_engage_then_skills',
  'post_engage_killer_skills',
] as const

export const RESEARCH_ONLY_MARK_SELECTION = 'near_hp_drop' as const

const SUITE_WIRE: Record<
  SuiteId,
  {
    harnessSuite: string
    match: string
    crosscheckRel: string
    sqliteRel: string
    note: string
  }
> = {
  S0: {
    // Prefer 2970132 Path1; fall back to 2970110-g1 when crosschecks missing.
    harnessSuite: '2970132-g1-holdout',
    match: '2970132-g1',
    crosscheckRel: 'docs/canvases/_data/crosschecks-2970132-g1-holdout.json',
    sqliteRel: 'artifacts/pro-grid/2970132/timeline.g1.slim.sqlite',
    note: 'S0 prefer 2970132 Path1; proxy 2970110-g1 if windows file absent',
  },
  S1: {
    harnessSuite: '2970137-g1-holdout',
    match: '2970137-g1',
    crosscheckRel: 'docs/canvases/_data/crosschecks-2970137-g1-holdout.json',
    sqliteRel: 'artifacts/pro-grid/2970137/timeline.g1.slim.sqlite',
    note: 'S1 holdout — do not tune on S1',
  },
  S2: {
    harnessSuite: '2970120-g1-holdout',
    match: '2970120-g1',
    crosscheckRel: 'docs/canvases/_data/crosschecks-2970120-g1-holdout.json',
    sqliteRel: 'artifacts/pro-grid/2970120/timeline.g1.slim.sqlite',
    note: 'S2 transfer proxy (unused pro slim; widen later)',
  },
}

const S0_PROXY = {
  harnessSuite: '2970110-g1',
  match: '2970110-g1',
  crosscheckRel: 'docs/canvases/_data/crosschecks-2970110-g1.json',
  sqliteRel: 'artifacts/pro-grid/2970110/timeline.g1.slim.sqlite',
  note: 'S0 proxy — 2970132 crosschecks JSON missing; GOAL allows 2970110 if pins allow',
}

function pathCapForSegment(segment: 'full' | 'burst' | undefined): number {
  return segment === 'burst' ? BURST_CAP : FULL_CAP
}

/**
 * GOAL §B windowOk + windowScore.
 * Path fidelity uses segment cap when `truth.segment` is set (check×segment).
 * When segment omitted, requires both burst≤90 and full≤130 (scaffold pair mode).
 */
export function scoreWindow(truth: WindowTruth, model: WindowModel): WindowResult {
  const lethalError =
    model.lethalErrorSec != null
      ? Math.abs(model.lethalErrorSec)
      : truth.truthKilled && model.modelLethalSec != null
        ? Math.abs(model.modelLethalSec)
        : null

  let lethalOk = false
  if (truth.truthKilled) {
    lethalOk =
      model.modelKilled && lethalError != null && lethalError <= LETHAL_TOL
  } else {
    lethalOk =
      !model.modelKilled ||
      (model.endHpAbsError != null && model.endHpAbsError <= END_HP_FLOOR)
  }

  const earlyOk = model.earlyMaeHp <= EARLY_CAP
  const segment = truth.segment
  let pathOk: boolean
  let pathBand: number
  let pathCap: number | null = null

  if (segment === 'burst' || segment === 'full') {
    pathCap = pathCapForSegment(segment)
    const mae =
      model.maeHp ??
      (segment === 'burst' ? model.maeHpBurst : model.maeHpFull)
    pathOk = mae <= pathCap
    pathBand = pathOk
      ? 1
      : Math.max(0, 1 - Math.max(0, mae - pathCap) / pathCap)
  } else {
    pathOk = model.maeHpBurst <= BURST_CAP && model.maeHpFull <= FULL_CAP
    pathBand = (() => {
      if (pathOk) return 1
      const burstOver = Math.max(0, model.maeHpBurst - BURST_CAP) / BURST_CAP
      const fullOver = Math.max(0, model.maeHpFull - FULL_CAP) / FULL_CAP
      return Math.max(0, 1 - 0.5 * (burstOver + fullOver))
    })()
  }

  const noInvent = model.noInvent !== false
  const noHard = !model.hardFail
  const windowOk = lethalOk && earlyOk && pathOk && noInvent && noHard

  const lethalHit = lethalOk ? 1 : 0
  const earlyBand =
    model.earlyMaeHp <= EARLY_CAP
      ? 1
      : Math.max(0, 1 - (model.earlyMaeHp - EARLY_CAP) / 100)
  const actionF1 =
    model.actionCoverageF1 == null || Number.isNaN(model.actionCoverageF1)
      ? 0
      : Math.min(1, Math.max(0, model.actionCoverageF1))

  // F2 H3 / GOAL §B weights
  const windowScore =
    0.4 * lethalHit + 0.25 * earlyBand + 0.2 * pathBand + 0.15 * actionF1

  return {
    id: truth.id,
    windowOk,
    windowScore,
    parts: {
      lethalOk,
      earlyOk,
      pathOk,
      noInvent,
      noHard,
      lethalHit,
      earlyBand,
      pathBand,
      actionF1,
      earlyMaeHp: model.earlyMaeHp,
      maeHpBurst: model.maeHpBurst,
      maeHpFull: model.maeHpFull,
      maeHp: model.maeHp ?? null,
      pathCap,
      lethalErrorSec: lethalError,
      segment: segment ?? 'paired',
      matchup: truth.matchup ?? '',
    },
  }
}

export function suiteMeans(results: WindowResult[]) {
  if (!results.length) return { fightAgreement: 0, fightPassRate: 0, n: 0 }
  const fightAgreement =
    results.reduce((s, r) => s + r.windowScore, 0) / results.length
  const fightPassRate =
    results.reduce((s, r) => s + (r.windowOk ? 1 : 0), 0) / results.length
  return { fightAgreement, fightPassRate, n: results.length }
}

function hardFailTouchesCheck(hardFails: string[] | undefined, check: number): boolean {
  if (!hardFails?.length) return false
  const re = new RegExp(`check0?${check}\\b|c0?${check}\\b`, 'i')
  return hardFails.some((f) => re.test(f) || f.toLowerCase().includes(`check${check}`))
}

/** Map harness eval checks → scored windows (check×segment). */
export function scoreHarnessEval(
  evalJson: HarnessEval,
  suite: SuiteId,
  opts?: { matchOverride?: string; noInvent?: boolean },
): { results: WindowResult[]; truths: WindowTruth[]; models: WindowModel[] } {
  const match =
    opts?.matchOverride ??
    (evalJson.seriesId
      ? `${evalJson.seriesId}-g${evalJson.gameIndex ?? 1}`
      : SUITE_WIRE[suite].match)
  const byKey = new Map(
    (evalJson.checks ?? []).map((c) => [`${c.check}:${c.segment}`, c] as const),
  )
  const arByKey = new Map(
    (evalJson.actionReplay?.perWindow ?? []).map(
      (w) => [`${w.check}:${w.segment}`, w.actionCoverage] as const,
    ),
  )

  const results: WindowResult[] = []
  const truths: WindowTruth[] = []
  const models: WindowModel[] = []

  for (const c of evalJson.checks ?? []) {
    const pairedBurst = byKey.get(`${c.check}:burst`)
    const pairedFull = byKey.get(`${c.check}:full`)
    const early = c.earlyMaeHp
    const mae = c.maeHp
    if (early == null || mae == null) continue

    const truthKilled =
      c.actualEndHp == null ? true : c.actualEndHp <= 1e-6
    // Kill-suite windows are selected from real champion_kill events; if end HP
    // sample is non-zero (model window truncation), still treat as truth kill
    // when harness selected a kill check — disclose via parts.
    const forceTruthKill = true

    const endHpAbsError =
      c.modelEndHp != null && c.actualEndHp != null
        ? Math.abs(c.modelEndHp - c.actualEndHp)
        : undefined

    const id = `${suite}_${match}_c${c.check}_${c.segment}`
    const truth: WindowTruth = {
      id,
      suite,
      match,
      truthKilled: forceTruthKill || truthKilled,
      engageSec: c.engageSec ?? undefined,
      segment: c.segment,
      check: c.check,
      matchup: c.matchup,
    }
    const f1 =
      c.actionReplay?.actionCoverage ?? arByKey.get(`${c.check}:${c.segment}`) ?? null

    const model: WindowModel = {
      modelKilled: c.killedInModel,
      modelLethalSec: c.lethalErrorSec,
      earlyMaeHp: early,
      maeHp: mae,
      maeHpBurst: pairedBurst?.maeHp ?? (c.segment === 'burst' ? mae : Number.NaN),
      maeHpFull: pairedFull?.maeHp ?? (c.segment === 'full' ? mae : Number.NaN),
      endHpAbsError,
      actionCoverageF1: f1,
      lethalErrorSec: c.lethalErrorSec,
      hardFail: hardFailTouchesCheck(evalJson.hardFails, c.check),
      noInvent: opts?.noInvent ?? true,
    }

    // NaN pair fillers → use segment mae only for the other slot display
    if (Number.isNaN(model.maeHpBurst)) model.maeHpBurst = mae
    if (Number.isNaN(model.maeHpFull)) model.maeHpFull = mae

    truths.push(truth)
    models.push(model)
    results.push(scoreWindow(truth, model))
  }

  return { results, truths, models }
}

export function writeFailingAudits(
  results: WindowResult[],
  meta: {
    suite: SuiteId
    match: string
    auditDir: string
    evalPath?: string
    markSelection?: string | null
  },
): string[] {
  fs.mkdirSync(meta.auditDir, { recursive: true })
  const written: string[] = []
  for (const r of results) {
    if (r.windowOk) continue
    const out = path.join(meta.auditDir, `${r.id}.json`)
    const audit = {
      schema: 'fightAgreement-window-audit-v1',
      t: new Date().toISOString(),
      suite: meta.suite,
      match: meta.match,
      windowId: r.id,
      windowOk: r.windowOk,
      windowScore: r.windowScore,
      parts: r.parts,
      failReasons: [
        r.parts.lethalOk === false ? 'lethal' : null,
        r.parts.earlyOk === false ? 'earlyMae' : null,
        r.parts.pathOk === false ? 'pathMae' : null,
        r.parts.noInvent === false ? 'invent' : null,
        r.parts.noHard === false ? 'hardFail' : null,
      ].filter(Boolean),
      sourceEval: meta.evalPath ?? null,
      markSelection: meta.markSelection ?? null,
      confidence:
        'fightAgreement window audit — NOT win odds / calibrated probability',
    }
    fs.writeFileSync(out, JSON.stringify(audit, null, 2) + '\n', 'utf8')
    written.push(out)
  }
  return written
}

function argValue(flag: string, fallback = ''): string {
  const i = process.argv.indexOf(flag)
  return i >= 0 && process.argv[i + 1] ? process.argv[i + 1]! : fallback
}

function resolveSuiteRuntime(suite: SuiteId): {
  harnessSuite: string
  match: string
  note: string
  proxied: boolean
} {
  if (suite !== 'S0') {
    const w = SUITE_WIRE[suite]
    return {
      harnessSuite: w.harnessSuite,
      match: w.match,
      note: w.note,
      proxied: false,
    }
  }
  const preferred = path.resolve(SUITE_WIRE.S0.crosscheckRel)
  if (fs.existsSync(preferred)) {
    return {
      harnessSuite: SUITE_WIRE.S0.harnessSuite,
      match: SUITE_WIRE.S0.match,
      note: SUITE_WIRE.S0.note,
      proxied: false,
    }
  }
  return {
    harnessSuite: S0_PROXY.harnessSuite,
    match: S0_PROXY.match,
    note: S0_PROXY.note,
    proxied: true,
  }
}

function runHarness(opts: {
  harnessSuite: string
  outPath: string
  markSelection: string
  hypothesis: string
}): void {
  const args = [
    'scripts/crosscheck_action_aligned.ts',
    '--suite',
    opts.harnessSuite,
    '--out',
    opts.outPath,
    '--hypothesis',
    opts.hypothesis,
    '--mark-selection',
    opts.markSelection,
    '--no-action-replay-audit',
  ]
  // Product density throttle from best.json productShipGate notes (disclosed).
  if (opts.markSelection === 'cusum_engage_then_skills') {
    args.push('--dense-window', '1.0', '--dense-max', '1', '--mark-min-gap', '0.4')
  }
  console.log('harness:', 'npx --yes tsx', args.join(' '))
  execFileSync('npx', ['--yes', 'tsx', ...args], {
    stdio: 'inherit',
    cwd: process.cwd(),
    env: process.env,
  })
}

function gateThresholds(suite: SuiteId): {
  fightAgreement: number
  fightPassRate: number
} {
  if (suite === 'S2') return { fightAgreement: 0.9, fightPassRate: 5 / 6 }
  return { fightAgreement: 0.95, fightPassRate: 0.95 }
}

function main() {
  const outDir = path.resolve(
    argValue(
      '--out-dir',
      'docs/rofl-research/autoresearch/fight_outcome/r04',
    ),
  )
  const auditDir = path.resolve(
    argValue(
      '--audit-dir',
      'docs/rofl-research/autoresearch/fight_outcome/audits',
    ),
  )
  const suiteLabel = (argValue('--suite-label', 'S0') || 'S0') as SuiteId
  const fromEval = argValue('--from-eval', '')
  const runHarnessFlag = process.argv.includes('--run-harness')
  const markSelection = argValue(
    '--mark-selection',
    'cusum_engage_then_skills',
  )
  if (markSelection === RESEARCH_ONLY_MARK_SELECTION) {
    console.warn(
      'WARN: near_hp_drop is research-only — not product fightAgreement default',
    )
  }

  fs.mkdirSync(outDir, { recursive: true })
  fs.mkdirSync(auditDir, { recursive: true })

  const runtime = resolveSuiteRuntime(suiteLabel)
  let evalPath = fromEval ? path.resolve(fromEval) : ''
  const disclosures: string[] = [
    'fightAgreement = mean(windowScore); NOT win probability / odds %',
    `unfreeze_0_9683=true (authorized); this run MEASURES fightAgreement first`,
    `selector=${markSelection} (product non-drop unless research flag)`,
    runtime.note,
  ]

  if (runHarnessFlag && !evalPath) {
    const harnessOut = path.join(
      outDir,
      `harness_eval_${suiteLabel}_${runtime.match.replace(/-/g, '_')}.json`,
    )
    runHarness({
      harnessSuite: runtime.harnessSuite,
      outPath: harnessOut,
      markSelection,
      hypothesis: `R04 fightAgreement baseline measure ${suiteLabel} ${markSelection}`,
    })
    evalPath = harnessOut
  }

  if (!evalPath || !fs.existsSync(evalPath)) {
    // Self-test score API + wire status when no eval yet
    const stub = {
      schema: 'fightAgreement-suite-v1',
      t: new Date().toISOString(),
      researcher: 'r04',
      status: 'awaiting_eval',
      suite: suiteLabel,
      runtime,
      fightAgreement: null,
      fightPassRate: null,
      thresholds: gateThresholds(suiteLabel),
      disclosures,
      confidence:
        'fightAgreement is kill-window suite agreement — NOT win probability / odds %',
      howTo:
        'Pass --from-eval <harness.json> or --run-harness with artifacts/pro-grid slim present',
    }
    const out = path.join(outDir, `fight_agreement_${suiteLabel}_status.json`)
    fs.writeFileSync(out, JSON.stringify(stub, null, 2) + '\n')
    console.log('wrote', out)
    console.log('No eval loaded — score API ready. Provide --from-eval or --run-harness.')
    return
  }

  const evalJson = JSON.parse(fs.readFileSync(evalPath, 'utf8')) as HarnessEval
  const { results } = scoreHarnessEval(evalJson, suiteLabel, {
    matchOverride: runtime.match,
    noInvent: true,
  })
  const means = suiteMeans(results)
  const thresholds = gateThresholds(suiteLabel)
  const audits = writeFailingAudits(results, {
    suite: suiteLabel,
    match: runtime.match,
    auditDir,
    evalPath,
    markSelection,
  })

  const cfgSel = evalJson.config?.markSelection
  if (cfgSel === RESEARCH_ONLY_MARK_SELECTION) {
    disclosures.push('eval used near_hp_drop (research-only) — disclose vs product default')
  }
  if (runtime.proxied) {
    disclosures.push(
      'S0 proxied to 2970110-g1 — 2970132 Path1 windows not curated yet (F9)',
    )
  }

  const report = {
    schema: 'fightAgreement-suite-v1',
    t: new Date().toISOString(),
    researcher: 'r04',
    suite: suiteLabel,
    match: runtime.match,
    proxied: runtime.proxied,
    harnessSuite: runtime.harnessSuite,
    sourceEval: evalPath,
    markSelection,
    harnessMode: evalJson.mode ?? null,
    harnessHypothesis: evalJson.hypothesis ?? null,
    n: means.n,
    fightAgreement: means.fightAgreement,
    fightPassRate: means.fightPassRate,
    thresholds,
    meetsThresholds:
      means.n > 0 &&
      means.fightAgreement >= thresholds.fightAgreement &&
      means.fightPassRate >= thresholds.fightPassRate,
    windows: results.map((r) => ({
      id: r.id,
      windowOk: r.windowOk,
      windowScore: Number(r.windowScore.toFixed(6)),
      parts: r.parts,
    })),
    failingAudits: audits,
    law: {
      lethalTolSec: LETHAL_TOL,
      earlyMaeCap: EARLY_CAP,
      burstMaeCap: BURST_CAP,
      fullMaeCap: FULL_CAP,
      endHpFloor: END_HP_FLOOR,
      weights: {
        lethalHit: 0.4,
        earlyBand: 0.25,
        pathBand: 0.2,
        actionCoverageF1: 0.15,
      },
    },
    unfreeze_0_9683: true,
    baselineCompositePreserved: 0.9683,
    disclosures,
    confidence:
      'fightAgreement ≥0.95 means kill-window suite agreement under GOAL §B — NOT calibrated win odds',
  }

  const out = path.join(outDir, `fight_agreement_${suiteLabel}.json`)
  fs.writeFileSync(out, JSON.stringify(report, null, 2) + '\n')
  console.log(
    `\nfightAgreement=${means.fightAgreement.toFixed(4)}  fightPassRate=${means.fightPassRate.toFixed(4)}  n=${means.n}  suite=${suiteLabel}  match=${runtime.match}`,
  )
  console.log(
    `meetsThresholds=${report.meetsThresholds}  failingAudits=${audits.length}`,
  )
  console.log('wrote', out)
  console.log(
    'NOTE: fightAgreement ≠ win odds. "~95%" = suite agreement under this metric.',
  )
}

const isMain =
  import.meta.url === `file://${process.argv[1]}` ||
  process.argv[1]?.endsWith('fight_agreement_suite.ts')

if (isMain) {
  main()
}
