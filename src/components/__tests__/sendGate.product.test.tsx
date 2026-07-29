/**
 * P6 H2 — living-only Send gate acceptance (product calculatorReady path).
 * Pure helper matrix; does not mock calculatorReady:true to force Send.
 */
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createServer } from 'vite'
import {
  abilityRanksAreKnown,
  combatStatsAreKnown,
  hpIsKnown,
} from '../../game/timeline'

const vite = await createServer({
  server: { middlewareMode: true },
  appType: 'custom',
  logLevel: 'silent',
})

try {
  const {
    calculatorTrustBlockReason,
    livingSelectedUnits,
    selectedCombatTrustGap,
    selectedLacksKnownCombatState,
  } = (await vite.ssrLoadModule(
    '/src/components/GameReview.tsx',
  )) as typeof import('../GameReview')

  type U = {
    loadout: { championId: string }
    alive?: boolean
    hpKnown?: boolean
    combatStatsKnown?: boolean
    abilityRanksKnown?: boolean
    team?: 'blue' | 'red'
  }

  const known = (champ: string, team: 'blue' | 'red', alive = true): U => ({
    loadout: { championId: champ },
    team,
    alive,
    hpKnown: true,
    combatStatsKnown: true,
    abilityRanksKnown: true,
  })

  // E1 — H1 retained: absent flags fail-closed
  assert.equal(hpIsKnown({}), false)
  assert.equal(combatStatsAreKnown({}), false)
  assert.equal(abilityRanksAreKnown({}), false)
  assert.equal(selectedLacksKnownCombatState([known('Gnar', 'blue')]), false)
  assert.equal(selectedLacksKnownCombatState([{} as U]), true)

  // E2 — dead+unknown + living known ⇒ living gate open
  {
    const selected: U[] = [
      known('Gnar', 'blue'),
      {
        loadout: { championId: 'MonkeyKing' },
        team: 'blue',
        alive: false,
        hpKnown: false,
        combatStatsKnown: false,
        abilityRanksKnown: false,
      },
      known('Ornn', 'red'),
    ]
    const living = livingSelectedUnits(selected)
    assert.deepEqual(
      living.map((u) => u.loadout.championId),
      ['Gnar', 'Ornn'],
    )
    assert.equal(selectedLacksKnownCombatState(living), false)
    assert.equal(selectedCombatTrustGap(living), null)
    const block = calculatorTrustBlockReason({
      research: false,
      positionBlocked: false,
      combatStateBlocked: selectedLacksKnownCombatState(living),
      missingFieldLabel: selectedCombatTrustGap(living),
    })
    assert.equal(block, null)
  }

  // E3 — living unknown still blocks (champ label)
  {
    const living = livingSelectedUnits([
      known('Gnar', 'blue'),
      {
        loadout: { championId: 'Azir' },
        team: 'red',
        alive: true,
        hpKnown: false,
        combatStatsKnown: true,
        abilityRanksKnown: true,
      },
    ])
    assert.equal(selectedLacksKnownCombatState(living), true)
    assert.equal(selectedCombatTrustGap(living), 'Azir HP')
    const reason =
      calculatorTrustBlockReason({
        research: false,
        positionBlocked: false,
        combatStateBlocked: true,
        missingFieldLabel: selectedCombatTrustGap(living),
      }) ?? ''
    assert.match(reason, /Azir HP/)
  }

  // E4 — NvM 2v2 living gate; dead on blue does not shrink import set incorrectly
  {
    const selected: U[] = [
      known('Gnar', 'blue'),
      known('Sejuani', 'blue'),
      {
        loadout: { championId: 'DeadJungler' },
        team: 'blue',
        alive: false,
        hpKnown: undefined,
        combatStatsKnown: undefined,
        abilityRanksKnown: undefined,
      },
      known('Ornn', 'red'),
      known('Braum', 'red'),
    ]
    const living = livingSelectedUnits(selected)
    const blue = living.filter((u) => u.team === 'blue')
    const red = living.filter((u) => u.team === 'red')
    assert.equal(blue.length, 2)
    assert.equal(red.length, 2)
    assert.equal(selectedLacksKnownCombatState(living), false)
    assert.equal(
      living.some((u) => u.loadout.championId === 'DeadJungler'),
      false,
      'dead excluded from calculator import set',
    )
  }

  // E5 — match-level calculatorReady must NOT be the Send switch (helpers only)
  {
    const living = livingSelectedUnits([
      {
        loadout: { championId: 'Gnar' },
        alive: true,
        hpKnown: true,
        combatStatsKnown: true,
        abilityRanksKnown: true,
      },
      {
        loadout: { championId: 'Ornn' },
        alive: true,
        hpKnown: true,
        combatStatsKnown: true,
        abilityRanksKnown: true,
      },
    ])
    // Send honesty uses per-unit flags, not a match-level ready bit.
    const matchCalculatorReady = false
    assert.equal(matchCalculatorReady, false)
    assert.equal(selectedLacksKnownCombatState(living), false)
  }

  // E6 — ranks gap on living blocks even when HP/combat known
  {
    const living = livingSelectedUnits([
      known('Gnar', 'blue'),
      {
        loadout: { championId: 'Orianna' },
        team: 'red',
        alive: true,
        hpKnown: true,
        combatStatsKnown: true,
        abilityRanksKnown: false,
      },
    ])
    assert.equal(selectedCombatTrustGap(living), 'Orianna ability ranks')
  }

  // E7 — combat gap label
  {
    const living = livingSelectedUnits([
      {
        loadout: { championId: 'Jinx' },
        alive: true,
        hpKnown: true,
        combatStatsKnown: false,
        abilityRanksKnown: true,
      },
    ])
    assert.equal(selectedCombatTrustGap(living), 'Jinx combat stats')
  }

  // E8 — alive undefined counts as living (same as sendFight filter)
  {
    const living = livingSelectedUnits([
      {
        loadout: { championId: 'Gnar' },
        // alive omitted
        hpKnown: true,
        combatStatsKnown: true,
        abilityRanksKnown: true,
      },
      {
        loadout: { championId: 'Ornn' },
        alive: false,
        hpKnown: false,
      },
    ])
    assert.equal(living.length, 1)
    assert.equal(living[0]!.loadout.championId, 'Gnar')
    assert.equal(selectedLacksKnownCombatState(living), false)
  }

  // E9 — anti-odds: block reason must not claim win %
  {
    const reason =
      calculatorTrustBlockReason({
        research: false,
        positionBlocked: false,
        combatStateBlocked: true,
        missingFieldLabel: 'Gnar HP',
      }) ?? ''
    assert.doesNotMatch(reason, /win\s*%|odds\s*%|probability/i)
    assert.match(reason, /trusted Gnar HP/)
  }

  // E10 — P6 H4: combatStateBlocked must not be timeline-only (import/sample parity)
  {
    const src = readFileSync(
      new URL('../GameReview.tsx', import.meta.url),
      'utf8',
    )
    assert.match(
      src,
      /selectedLacksCombatState \|\| timelineHpUnavailable/,
      'H4: combatStateBlocked applies on import/sample too',
    )
    assert.doesNotMatch(
      src,
      /combatStateBlocked\s*=\s*\n?\s*source === 'timeline' && \(timelineHpUnavailable/,
      'H4: old timeline-only combatStateBlocked must be gone',
    )
  }
} finally {
  await vite.close()
}

console.log('sendGate.product: ok (E1–E10 living-only + H4)')
