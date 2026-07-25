/**
 * P5 Track 3 / R15 — anti-invent + dead-excluded Send parity.
 * Proves: empty emit ⇒ empty rows; HPΔ never invents AA/damage UI;
 * Send excludes alive===false; overlay never bypasses known-flag gates;
 * copy never says odds % for model edge.
 */
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createServer } from 'vite'
import {
  foldResearchOverlaySlim,
  holdoutMissingEmitDisclosure,
  productAaTimelineWhenOverlayOff,
  productSendAttachedResearchActions,
  productSendAttachesResearchActions,
  rowsFromHpCurveAloneForbidden,
  visibleResearchOverlayRows,
  type ResearchActionRow,
} from '../../game/researchActionOverlay'

const fakeOverlayRows: ResearchActionRow[] = [
  {
    kind: 'basic_attack',
    tSec: 202,
    tMs: 202_000,
    sourceNetId: 1,
    sourceChampion: 'Camille',
    targetNetId: 2,
    targetChampion: 'Leona',
    amount: 42,
    researchOnly: true,
    calculatorReady: false,
  },
  {
    kind: 'damage_dealt',
    tSec: 202.1,
    tMs: 202_100,
    sourceNetId: 1,
    sourceChampion: 'Camille',
    targetNetId: 2,
    targetChampion: 'Leona',
    amount: 80,
    researchOnly: true,
    calculatorReady: false,
  },
]

const vite = await createServer({
  server: { middlewareMode: true },
  appType: 'custom',
  logLevel: 'silent',
})

let experiment = 0
function exp(name: string, fn: () => void) {
  experiment++
  fn()
  console.log(`E${experiment} PASS — ${name}`)
}

try {
  const {
    buildLivingSendImport,
    calculatorTrustBlockReason,
    livingSelectedUnits,
    selectedLacksKnownCombatState,
  } = (await vite.ssrLoadModule(
    '/src/components/GameReview.tsx',
  )) as typeof import('../GameReview')

  // (a) no emit ⇒ no rows
  exp('no emit ⇒ empty fold rows + disclosure', () => {
    const folded = foldResearchOverlaySlim(null)
    assert.equal(folded.rows.length, 0)
    assert.match(folded.disclosure, /missing|invented/i)
    assert.match(holdoutMissingEmitDisclosure('2970137-g1'), /not invented/i)
  })

  // (b) HP curve alone never creates AA/damage UI rows
  exp('HP curve alone never invents AA/damage rows', () => {
    assert.deepEqual(rowsFromHpCurveAloneForbidden(), [])
    assert.deepEqual(productAaTimelineWhenOverlayOff(true), [])
    assert.deepEqual(productAaTimelineWhenOverlayOff(false), [])
  })

  // Flag OFF hides loaded emit (anti-fake product AA timeline)
  exp('overlay flag OFF ⇒ visible rows empty even if emit loaded', () => {
    assert.equal(visibleResearchOverlayRows(false, fakeOverlayRows).length, 0)
    assert.equal(visibleResearchOverlayRows(true, fakeOverlayRows).length, 2)
  })

  // (c) Send still excludes alive===false
  exp('dead excluded from living Send import set', () => {
    const parity = buildLivingSendImport([
      {
        loadout: { championId: 'Gnar' },
        team: 'blue',
        alive: true,
        hpKnown: true,
        combatStatsKnown: true,
        abilityRanksKnown: true,
      },
      {
        loadout: { championId: 'MonkeyKing' },
        team: 'blue',
        alive: false,
        hpKnown: false,
        combatStatsKnown: false,
        abilityRanksKnown: false,
      },
      {
        loadout: { championId: 'Ornn' },
        team: 'red',
        alive: true,
        hpKnown: true,
        combatStatsKnown: true,
        abilityRanksKnown: true,
      },
    ])
    assert.equal(parity.deadExcludedCount, 1)
    assert.deepEqual(
      parity.blue.map((u) => u.championId),
      ['Gnar'],
    )
    assert.deepEqual(
      parity.red.map((u) => u.championId),
      ['Ornn'],
    )
    assert.equal(parity.canSend, true)
    assert.equal(parity.lacksKnownCombatState, false)
    assert.equal(
      livingSelectedUnits([
        { alive: false, loadout: { championId: 'Dead' } },
        { alive: true, loadout: { championId: 'Live' } },
      ]).length,
      1,
    )
  })

  // (d) overlay never bypasses known-flag Send gates
  exp('research overlay AA never attaches to product Send', () => {
    assert.equal(productSendAttachesResearchActions(), false)
    assert.deepEqual(productSendAttachedResearchActions(fakeOverlayRows), [])
    const parity = buildLivingSendImport(
      [
        {
          loadout: { championId: 'Gnar' },
          team: 'blue',
          alive: true,
          hpKnown: true,
          combatStatsKnown: true,
          abilityRanksKnown: true,
        },
        {
          loadout: { championId: 'Ornn' },
          team: 'red',
          alive: true,
          hpKnown: true,
          combatStatsKnown: true,
          abilityRanksKnown: true,
        },
      ],
      fakeOverlayRows,
    )
    assert.deepEqual(parity.attachedResearchActions, [])
  })

  exp('overlay cannot open Send when living known-flags missing', () => {
    const parity = buildLivingSendImport(
      [
        {
          loadout: { championId: 'Gnar' },
          team: 'blue',
          alive: true,
          hpKnown: true,
          combatStatsKnown: true,
          abilityRanksKnown: true,
        },
        {
          loadout: { championId: 'Azir' },
          team: 'red',
          alive: true,
          hpKnown: false,
          combatStatsKnown: true,
          abilityRanksKnown: true,
        },
      ],
      fakeOverlayRows,
    )
    assert.equal(parity.lacksKnownCombatState, true)
    assert.equal(parity.trustGap, 'Azir HP')
    assert.equal(parity.attachedResearchActions.length, 0)
    // Living selection still fails known-flag gate even with overlay present.
    assert.equal(
      selectedLacksKnownCombatState([
        {
          hpKnown: true,
          combatStatsKnown: true,
          abilityRanksKnown: true,
        },
        {
          hpKnown: false,
          combatStatsKnown: true,
          abilityRanksKnown: true,
        },
      ]),
      true,
    )
  })

  // Dead+unknown must not false-block when living picks are known (parity w/ H2)
  exp('dead+unknown does not false-block living known Send', () => {
    const parity = buildLivingSendImport([
      {
        loadout: { championId: 'Gnar' },
        team: 'blue',
        alive: true,
        hpKnown: true,
        combatStatsKnown: true,
        abilityRanksKnown: true,
      },
      {
        loadout: { championId: 'DeadJungler' },
        team: 'blue',
        alive: false,
        hpKnown: undefined,
        combatStatsKnown: undefined,
        abilityRanksKnown: undefined,
      },
      {
        loadout: { championId: 'Ornn' },
        team: 'red',
        alive: true,
        hpKnown: true,
        combatStatsKnown: true,
        abilityRanksKnown: true,
      },
    ])
    assert.equal(parity.lacksKnownCombatState, false)
    assert.equal(parity.trustGap, null)
    assert.equal(parity.canSend, true)
  })

  // (e) copy never says odds % for pBlue/pRed / Send block
  exp('Send block reason never claims odds % / win %', () => {
    const reason =
      calculatorTrustBlockReason({
        research: false,
        positionBlocked: false,
        combatStateBlocked: true,
        missingFieldLabel: 'Gnar HP',
      }) ?? ''
    assert.doesNotMatch(reason, /win\s*%|odds\s*%|probability|pBlue|pRed/i)
    assert.match(reason, /trusted Gnar HP/)
  })

  // H4 E10 verify (import-path parity formula present)
  exp('H4 E10 combatStateBlocked not timeline-only', () => {
    const src = readFileSync(
      new URL('../GameReview.tsx', import.meta.url),
      'utf8',
    )
    assert.match(src, /selectedLacksCombatState \|\| timelineHpUnavailable/)
    assert.doesNotMatch(
      src,
      /combatStateBlocked\s*=\s*\n?\s*source === 'timeline' && \(timelineHpUnavailable/,
    )
    // Props must stay JSX-free (R28 parse trap).
    assert.match(src, /interface Props \{\n  onSendToCalculator:/)
    assert.doesNotMatch(src, /interface Props \{[^}]*JSX\./)
  })
} finally {
  await vite.close()
}

console.log(`\ntrack3AntiInventSendParity: ${experiment} experiments passed`)
