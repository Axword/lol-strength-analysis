/**
 * F10 / R29 anti-odds + modelTrust copy audit (product UI surfaces).
 *
 * fightAgreement = kill-window suite agreement — NOT win probability / odds % / pBlue.
 * pBlue/pRed = heuristic model edge only — NEVER calibrated win odds / odds %.
 * Unfreeze research composite 0.9683 is disclosed history — do not rewrite best.json here.
 */
import { readFileSync, mkdirSync, writeFileSync, existsSync } from 'node:fs'
import { join, resolve } from 'node:path'

const ROOT = resolve(process.cwd())
const PARENT_FORBIDDEN = '/Users/river/Projects/lol-strength-analysis'
const OUT_DIRS = [
  join(ROOT, 'docs/rofl-research/autoresearch/fight_outcome/r29'),
  join(ROOT, 'docs/rofl-research/autoresearch/product_ready/rooms/P10'),
]

const PRODUCT_UI = [
  'src/components/Calculator.tsx',
  'src/components/CombatResult.tsx',
  'src/components/GameReview.tsx',
  'src/components/Faq.tsx',
  'src/App.tsx',
  'src/components/Scoreboard.tsx',
] as const

const MODEL_TRUST = 'src/engine/modelTrust.ts'
const COMBAT = 'src/engine/combat.ts'
const GAME_STATE_ODDS = 'src/engine/gameStateOdds.ts'

/** Forbidden product-facing odds language (case-insensitive). */
const FORBIDDEN: { id: string; re: RegExp; note: string }[] = [
  {
    id: 'odds_percent',
    re: /\bodds\s*%/i,
    note: 'never render odds %',
  },
  {
    id: 'fight_odds_hyphen',
    re: /fight-odds/i,
    note: 'use model edge / heuristic ranking, not fight-odds',
  },
  {
    id: 'fight_odds',
    re: /fight odds/i,
    note: 'use model edge / heuristic ranking, not fight odds',
  },
  {
    id: 'win_odds_claim',
    re: /(?<!not\s)(?<!never\s)(?<!calibrated\s)win odds/i,
    note: 'win odds claim without negation',
  },
  {
    id: 'chance_to_win',
    re: /chance to win/i,
    note: 'chance-to-win phrasing forbidden',
  },
  {
    id: 'calibrated_probability_claim',
    re: /(?<!not\s(?:a\s)?)(?<!never\s)calibrated (?:win )?probabilit/i,
    note: 'must not claim calibrated probability',
  },
  {
    id: 'pblue_as_percent_label',
    re: /pBlue[^\n]{0,40}%\s*(?:win|odds|chance)/i,
    note: 'pBlue must not be labeled as win/odds %',
  },
  {
    id: 'fight_agreement_as_win_pct',
    re: /fightAgreement[^\n]{0,60}(?:win\s*%|win probability|odds\s*%)/i,
    note: 'fightAgreement must not be framed as win % / odds',
  },
]

type Finding = {
  file: string
  id: string
  line: number
  excerpt: string
  note: string
}

type ReqCheck = { id: string; ok: boolean; detail?: string }

function fail(msg: string): never {
  console.error(`ANTI-ODDS AUDIT FAIL: ${msg}`)
  process.exit(1)
}

function neverParentOk(): boolean {
  const real = resolve(ROOT)
  // Researchers: worktree only. Parent post-KEEP verify: pass --allow-parent.
  if (process.argv.includes('--allow-parent')) return true
  if (real === PARENT_FORBIDDEN) return false
  return real.includes('/.codex/worktrees/')
}

function scanFile(rel: string): Finding[] {
  const abs = join(ROOT, rel)
  if (!existsSync(abs)) fail(`missing ${rel}`)
  const text = readFileSync(abs, 'utf8')
  const lines = text.split(/\r?\n/)
  const hits: Finding[] = []
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]!
    if (
      /never\s+(win odds|odds\s*%|calibrated)|not\s+(a\s+)?(win probability|calibrated|odds\s*%)|model edge,\s*not|ranking score,\s*not|model edge only|NOT calibrated|not P\(win\)|heuristic model-edge|heuristic ranking scores/i.test(
        line,
      )
    ) {
      continue
    }
    for (const rule of FORBIDDEN) {
      if (rule.re.test(line)) {
        hits.push({
          file: rel,
          id: rule.id,
          line: i + 1,
          excerpt: line.trim().slice(0, 160),
          note: rule.note,
        })
      }
    }
  }
  return hits
}

function requiredLabels(): ReqCheck[] {
  const combatUi = readFileSync(join(ROOT, 'src/components/CombatResult.tsx'), 'utf8')
  const trust = readFileSync(join(ROOT, MODEL_TRUST), 'utf8')
  const calc = readFileSync(join(ROOT, 'src/components/Calculator.tsx'), 'utf8')
  const review = readFileSync(join(ROOT, 'src/components/GameReview.tsx'), 'utf8')
  const app = readFileSync(join(ROOT, 'src/App.tsx'), 'utf8')
  const scoreboard = readFileSync(
    join(ROOT, 'src/components/Scoreboard.tsx'),
    'utf8',
  )
  const combatEngine = readFileSync(join(ROOT, COMBAT), 'utf8')
  const faq = readFileSync(join(ROOT, 'src/components/Faq.tsx'), 'utf8')
  const gameStateOdds = readFileSync(join(ROOT, GAME_STATE_ODDS), 'utf8')

  return [
    {
      id: 'combat_model_edge_headline',
      ok: /Blue model edge/.test(combatUi) && /Red model edge/.test(combatUi),
      detail: 'CombatResult headlines must say model edge',
    },
    {
      id: 'combat_not_win_probability',
      ok: /not a win probability/.test(combatUi),
      detail: 'CombatResult subline must deny win probability',
    },
    {
      id: 'combat_heuristic_model_score',
      ok: /heuristic model score/.test(combatUi),
      detail: 'CombatResult must label pBlue/pRed as heuristic model score',
    },
    {
      id: 'combat_trust_badge',
      ok:
        /trustBadge/.test(combatUi) &&
        /trust\?\.badge/.test(combatUi) &&
        /Manual kits · uncalibrated/.test(trust) &&
        /Experimental · uncalibrated/.test(trust),
      detail: 'CombatResult must surface modelTrust badges from classifier',
    },
    {
      id: 'band_model_edge_not_bare_score',
      ok: /`model edge /.test(combatUi) || /model edge \$\{/.test(combatUi),
      detail: 'BandCell must say model edge, not bare score (odds-like)',
    },
    {
      id: 'modelTrust_calibrated_false',
      ok: /calibrated:\s*false/.test(trust) && /calibrated: false/.test(trust),
      detail: 'modelTrust.calibrated must be typed/returned false',
    },
    {
      id: 'modelTrust_kill_window_not_odds',
      ok: /kill_window_not_calibrated_win_odds/.test(trust),
      detail: 'kill-window path must add anti-odds reason code',
    },
    {
      id: 'modelTrust_reasons_visible_not_tooltip_only',
      ok:
        /data-testid=["']trust-reasons["']/.test(combatUi) &&
        /pickVisibleTrustReasons/.test(combatUi) &&
        /pickVisibleTrustReasons/.test(trust) &&
        /ModelTrust reasons \(visible\)/.test(combatEngine),
      detail:
        'CombatResult must render trust reasons in DOM (not title= only); assumptions parity',
    },
    {
      id: 'calculator_kill_window_not_win_pct',
      ok: /not win %/.test(calc) || /experimental;\s*not win/.test(calc),
      detail: 'Calculator kill-window path must disclose not win %',
    },
    {
      id: 'send_honesty_chip_visible',
      ok:
        /model edge only/.test(review) &&
        /not odds\s*%/.test(review) &&
        /send-honesty-chip/.test(review) &&
        /interface Props/.test(review) &&
        /onSendToCalculator/.test(review),
      detail:
        'GameReview Send path must show visible model-edge honesty chip (Props intact)',
    },
    {
      id: 'faq_no_fight_odds',
      ok: !/fight-odds/i.test(faq) && !/fight odds/i.test(faq),
      detail: 'Faq must not say fight-odds / fight odds (V12 residual)',
    },
    {
      id: 'faq_fight_agreement_not_win_pct',
      ok:
        /fightAgreement/.test(faq) &&
        /kill-window suite/.test(faq) &&
        /never calibrated win probability/.test(faq) &&
        /never odds\s*%/.test(faq),
      detail:
        'Faq must disclose fightAgreement as kill-window suite agreement ≠ win % / odds',
    },
    {
      id: 'game_state_odds_comments_model_edge',
      ok:
        /heuristic fight model-edge/i.test(gameStateOdds) &&
        /not P\(win\), not odds %/i.test(gameStateOdds) &&
        !/P\(blue wins the fight\)/i.test(gameStateOdds) &&
        !/Fight win odds from game state/i.test(gameStateOdds),
      detail:
        'gameStateOdds comments must say model-edge, not P(win) / Fight win odds',
    },
    {
      id: 'app_shell_no_odds_claims',
      ok: !/\bodds\s*%/i.test(app) && !/chance to win/i.test(app),
      detail: 'App shell must not claim odds % / chance to win',
    },
    {
      id: 'scoreboard_no_odds_claims',
      ok: !/\bodds\s*%/i.test(scoreboard) && !/fight-odds/i.test(scoreboard),
      detail: 'Scoreboard must not claim odds % / fight-odds',
    },
  ]
}

function main(): void {
  if (!neverParentOk()) fail(`refuse parent checkout: ${ROOT}`)

  const findings = [...PRODUCT_UI, GAME_STATE_ODDS].flatMap(scanFile)
  const required = requiredLabels()
  const requiredOk = required.every((r) => r.ok)
  const antiOddsOk = findings.length === 0 && requiredOk
  const onParent = resolve(ROOT) === PARENT_FORBIDDEN

  const report = {
    schema: 'product-anti-odds-audit-v1',
    room: 'f10',
    researcher: 'R29',
    track: 'anti-odds-copy',
    utc: new Date().toISOString(),
    worktree: ROOT,
    branch: onParent ? 'feat/fight-outcome-95-10x30x15' : 'adv/fo-r29-anti-odds-copy',
    never_edited_parent: !onParent,
    allow_parent: onParent,
    unfreeze_0_9683: {
      authorized: true,
      best_json_touched: false,
      preserved_composite: 0.9683,
      note: 'Unfreeze authorized for fightAgreement experiments; best.json composite 0.9683 history preserved (no rewrite this run)',
    },
    scanned: [...PRODUCT_UI, MODEL_TRUST, COMBAT, GAME_STATE_ODDS],
    forbidden_hits: findings,
    required,
    gate_progress: {
      H_freeze: null as boolean | null,
      anti_odds: antiOddsOk,
      G_send_honesty_chip: required.some(
        (r) => r.id === 'send_honesty_chip_visible' && r.ok,
      ),
      G_model_trust_reasons_visible: required.some(
        (r) => r.id === 'modelTrust_reasons_visible_not_tooltip_only' && r.ok,
      ),
      faq_fight_agreement_disclosure: required.some(
        (r) => r.id === 'faq_fight_agreement_not_win_pct' && r.ok,
      ),
    },
    calculatorReady: false,
    fightOutcomeGateEvidence: false,
    confidence:
      'fightAgreement is kill-window suite agreement — NOT win probability / odds % / pBlue',
    ok: antiOddsOk,
  }

  for (const outDir of OUT_DIRS) {
    mkdirSync(outDir, { recursive: true })
    const outPath = join(outDir, 'anti_odds_audit_report.json')
    writeFileSync(outPath, JSON.stringify(report, null, 2) + '\n')
    console.log(`wrote ${outPath}`)
  }

  for (const r of required) {
    console.log(
      `${r.ok ? 'PASS' : 'FAIL'} required:${r.id}${r.detail ? ` — ${r.detail}` : ''}`,
    )
  }
  if (findings.length) {
    for (const f of findings) {
      console.log(`FAIL ${f.file}:${f.line} [${f.id}] ${f.excerpt}`)
    }
  } else {
    console.log('PASS no forbidden odds phrasing in product UI + gameStateOdds comments')
  }
  if (!antiOddsOk) fail(`${findings.length} forbidden hit(s); requiredOk=${requiredOk}`)
  console.log(
    'ANTI-ODDS AUDIT OK — model edge + fightAgreement≠odds + trust reasons visible',
  )
}

main()
