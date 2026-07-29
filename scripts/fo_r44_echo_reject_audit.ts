/**
 * R44 E8 — zero-damage log-echo REJECT control (GOAL forbid #13).
 * Demonstrates that inventing shareHint=0 modelActions to pad F1 is forbidden
 * as fightOutcomeGate / actionReplayGate evidence — even when raw F1≈1.
 *
 * Research only. FA ≠ odds. never_edited_parent_code.
 */
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { matchActions, type ActionRecord } from './lib/action_replay'

const outPath = resolve(
  'docs/rofl-research/autoresearch/fight_outcome/r44/experiments/e8_echo_reject.json',
)

const auditPath = resolve(
  'docs/rofl-research/autoresearch/fight_outcome/r44/experiments/e3_audits/2970132-g1-c1-burst.json',
)

type Audit = {
  truthActions: ActionRecord[]
  modelActions: ActionRecord[]
  coverage: { actionCoverage: number; truthCount: number; modelCount: number }
}

const audit = JSON.parse(readFileSync(auditPath, 'utf8')) as Audit
const truth = audit.truthActions
const honestModel = audit.modelActions
const honest = matchActions(truth, honestModel, 0.25)

// Forbidden: pad model with zero-dmg skill echoes for every unmatched truth.
const echoPad: ActionRecord[] = truth
  .filter((t, i) => !honest.matches.some((m) => m.truthIdx === i))
  .map((t) => ({
    ...t,
    shareHint: 0,
  }))
const echoedModel = [...honestModel, ...echoPad].sort((a, b) => a.tSec - b.tSec)
const echoed = matchActions(truth, echoedModel, 0.25)

const result = {
  schema: 'fo-r44-echo-reject-v1',
  window: 'S0_2970132-g1_c1_burst',
  honest: {
    truthCount: honest.truthCount,
    modelCount: honest.modelCount,
    matchedCount: honest.matchedCount,
    actionCoverage: honest.actionCoverage,
    gateEligible: true,
    note: 'real model skill pulse(s) only; shareHint from kit damage path',
  },
  zeroDmgEcho: {
    truthCount: echoed.truthCount,
    modelCount: echoed.modelCount,
    matchedCount: echoed.matchedCount,
    actionCoverage: echoed.actionCoverage,
    echoPadCount: echoPad.length,
    gateEligible: false,
    rejectReason:
      'zero_damage_log_echo: shareHint=0 modelActions must not earn actionReplayGate / fightOutcomeGate secondary credit (GOAL forbid #13 / R14)',
  },
  verdict: 'REJECT_ECHO_KEEP_HONEST',
  fightOutcomeGateEvidence: false,
  actionReplayGateEvidence: false,
  confidence:
    'actionCoverage is log-matched F1 — NOT win odds / NOT calibrated probability',
}

mkdirSync(dirname(outPath), { recursive: true })
writeFileSync(outPath, JSON.stringify(result, null, 2) + '\n')
console.log(JSON.stringify(result, null, 2))
