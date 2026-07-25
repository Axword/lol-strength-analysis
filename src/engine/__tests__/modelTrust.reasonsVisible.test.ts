/**
 * P10 Track4 — modelTrustReasonsVisible acceptance.
 * Kill-window matchups always Experimental; top reasons deterministic;
 * assumptions parity line present. Never odds %.
 */
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { simulateMatchup } from '../combat'
import {
  classifyMatchupModelTrust,
  pickVisibleTrustReasons,
  type MatchupModelTrust,
} from '../modelTrust'
import type { FighterLoadout, MatchupInput } from '../types'

function fighter(championId: string, patch: Partial<FighterLoadout> = {}): FighterLoadout {
  return {
    championId,
    level: 11,
    itemIds: [],
    runeId: null,
    ranks: { Q: 5, W: 3, E: 1, R: 2 },
    abilityRank: 5,
    alive: true,
    hpPct: 1,
    ...patch,
  }
}

function baseInput(patch: Partial<MatchupInput> = {}): MatchupInput {
  return {
    blue: [fighter('Darius')],
    red: [fighter('Gragas')],
    engager: 'neither',
    mode: 'allin',
    durationSec: 8,
    xhMode: 'off',
    ...patch,
  }
}

let passed = 0
function ok(cond: boolean, msg: string): void {
  assert.equal(cond, true, msg)
  passed += 1
  console.log(`PASS ${msg}`)
}

{
  const a = pickVisibleTrustReasons([
    'tier:Darius=core',
    'calibrated:false',
    'class:experimental',
    'scope:kill_window_not_calibrated_win_odds',
    'reason:kill_window_experimental',
    'living_roster:1v1',
  ])
  ok(a[0] === 'calibrated:false', 'visible reasons prioritize calibrated:false')
  ok(
    a.includes('scope:kill_window_not_calibrated_win_odds'),
    'visible reasons include kill-window anti-odds scope',
  )
  ok(a.length <= 6, 'visible reasons capped at 6')
}

{
  const kw = classifyMatchupModelTrust(
    baseInput({
      killWindow: {
        actionMarks: [{ tSec: 1, skillSlot: 1 }],
      },
    }),
  )
  ok(kw.calibrated === false, 'kill-window calibrated=false')
  ok(kw.class === 'experimental', 'kill-window forces experimental class')
  ok(
    kw.badge === 'Experimental · uncalibrated',
    'kill-window badge Experimental · uncalibrated',
  )
  ok(
    kw.reasons.includes('scope:kill_window_not_calibrated_win_odds'),
    'kill-window reason scope:kill_window_not_calibrated_win_odds',
  )
  const visible = pickVisibleTrustReasons(kw.reasons)
  ok(
    visible.includes('calibrated:false') &&
      visible.includes('scope:kill_window_not_calibrated_win_odds'),
    'visible pick keeps anti-odds codes for kill-window',
  )
}

{
  const result = simulateMatchup(
    baseInput({
      killWindow: {
        actionMarks: [{ tSec: 0.5, skillSlot: 0 }],
      },
    }),
  )
  const trust = result.modelTrust as MatchupModelTrust
  ok(trust?.class === 'experimental', 'simulateMatchup kill-window → experimental')
  ok(
    result.assumptions?.some((line) =>
      /ModelTrust reasons \(visible\):/.test(line),
    ) === true,
    'assumptions include ModelTrust reasons (visible) parity line',
  )
  ok(
    result.assumptions?.some((line) =>
      /calibrated:false/.test(line) &&
      /kill_window_not_calibrated_win_odds/.test(line),
    ) === true,
    'assumptions visible line carries calibrated:false + kill-window anti-odds',
  )
  ok(
    result.assumptions?.some((line) =>
      /not calibrated win probabilities/i.test(line),
    ) === true,
    'assumptions still deny calibrated win probabilities',
  )
}

{
  // UI string surface contracts (file-level; CombatResult renders chips).
  const combatUi = readFileSync('src/components/CombatResult.tsx', 'utf8')
  ok(
    /data-testid=["']trust-reasons["']/.test(combatUi),
    'CombatResult has data-testid=trust-reasons',
  )
  ok(/pickVisibleTrustReasons/.test(combatUi), 'CombatResult uses pickVisibleTrustReasons')
  ok(/`model edge /.test(combatUi), 'BandCell label is model edge')
  ok(!/`score \$\{/.test(combatUi), 'BandCell no bare score template')
  const faq = readFileSync('src/components/Faq.tsx', 'utf8')
  ok(!/fight-odds/i.test(faq) && !/fight odds/i.test(faq), 'Faq has no fight-odds copy')
}

console.log(`modelTrust.reasonsVisible: ${passed} passed`)
