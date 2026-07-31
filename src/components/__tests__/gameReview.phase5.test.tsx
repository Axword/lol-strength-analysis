import assert from 'node:assert/strict'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { createServer } from 'vite'
import type { MatchRegistry } from '../../game/timeline'

const registry: MatchRegistry = {
  version: 1,
  defaultMatchCode: '3264361042',
  matches: ['3264361042', '3264383283'].map((matchCode) => ({
    matchCode,
    gameId: Number(matchCode),
    name: matchCode,
    timelineUrl: `${matchCode}/timeline.json`,
    manifestUrl: `${matchCode}/manifest.json`,
    patch: '16.14',
    durationMs: 61_000,
    roster: {
      participantCount: 10,
      blueCount: 5,
      redCount: 5,
      champions: [],
    },
    coverage: {
      positions: 'full_at_sampled_frames',
      history: 'kda_total_cs_vision_at_sampled_frames',
      hp: 'none',
      combat: 'none',
      ranks: 'none',
    },
    productGates: {
      productValidated: true as const,
      stableIdentityComplete: true as const,
      hpTrusted: false,
      calculatorReady: false,
    },
  })),
}

const vite = await createServer({
  server: { middlewareMode: true },
  appType: 'custom',
  logLevel: 'silent',
})

try {
  const {
    MatchCoverageBadges,
    MatchPicker,
    ResearchActionOverlayPanel,
    calculatorTrustBlockReason,
    livingSelectedUnits,
    selectedCombatTrustGap,
    selectedLacksKnownCombatState,
  } = (await vite.ssrLoadModule(
    '/src/components/GameReview.tsx',
  )) as typeof import('../GameReview')

  const published = renderToStaticMarkup(
    React.createElement(MatchPicker, {
      registry,
      value: 'match:3264361042',
      localTimelineName: null,
      onChange: () => undefined,
    }),
  )
  assert.match(published, /Published matches/)
  assert.match(published, /3264361042 \(default\)/)
  assert.match(published, /3264383283/)
  assert.match(published, /Research fixtures/)
  assert.match(published, /FUR parity fixture \(demo\)/)
  assert.match(published, /Maknee packet fixture \(demo\)/)
  assert.doesNotMatch(published, /live_fur/)

  const empty = renderToStaticMarkup(
    React.createElement(MatchPicker, {
      registry: { version: 1, defaultMatchCode: null, matches: [] },
      value: '',
      localTimelineName: null,
      onChange: () => undefined,
    }),
  )
  assert.match(empty, /No product match selected/)
  assert.doesNotMatch(empty, /Published matches/)
  assert.match(empty, /Research fixtures/)

  const coverage = renderToStaticMarkup(
    React.createElement(MatchCoverageBadges, {
      entry: registry.matches[0],
      research: false,
    }),
  )
  assert.match(coverage, /Published match coverage/)
  assert.match(coverage, /<strong>Pos<\/strong> native/)
  assert.match(coverage, /<strong>Hist<\/strong> KDA\/CS\/vision/)
  assert.match(coverage, /<strong>HP<\/strong> none/)
  assert.match(coverage, /<strong>Calc<\/strong> blocked/)

  const partialHpEntry = {
    ...registry.matches[0],
    coverage: { ...registry.matches[0].coverage, hp: 'partial' },
    productGates: {
      ...registry.matches[0].productGates,
      hpTrusted: true,
      calculatorReady: false,
    },
  }
  const partialCoverage = renderToStaticMarkup(
    React.createElement(MatchCoverageBadges, {
      entry: partialHpEntry,
      research: false,
    }),
  )
  assert.match(partialCoverage, /<strong>Calc<\/strong> partial HP · Send per frame/)
  assert.doesNotMatch(partialCoverage, /<strong>Calc<\/strong> ready/)

  const research = renderToStaticMarkup(
    React.createElement(MatchCoverageBadges, {
      entry: null,
      research: true,
    }),
  )
  assert.match(research, /Research fixture coverage/)
  assert.match(research, /demo only · calculator blocked/)
  assert.match(
    calculatorTrustBlockReason({
      research: true,
      positionBlocked: false,
      combatStateBlocked: false,
    }) ?? '',
    /Research fixtures/,
  )
  assert.equal(
    calculatorTrustBlockReason({
      research: false,
      positionBlocked: false,
      combatStateBlocked: false,
    }),
    null,
  )
  assert.match(
    calculatorTrustBlockReason({
      research: false,
      positionBlocked: false,
      combatStateBlocked: true,
      missingFieldLabel: 'MonkeyKing HP',
    }) ?? '',
    /MonkeyKing HP/,
  )

  // P6 H1 / S2 — fail-closed: absent flags block Send (undefined ≠ known)
  assert.equal(selectedLacksKnownCombatState([{}]), true)
  assert.equal(
    selectedCombatTrustGap([{ loadout: { championId: 'Gnar' } }]),
    'Gnar HP',
  )
  assert.equal(
    selectedLacksKnownCombatState([
      {
        loadout: { championId: 'Gnar' },
        hpKnown: true,
        combatStatsKnown: true,
        abilityRanksKnown: true,
      },
    ]),
    false,
  )
  assert.equal(
    selectedCombatTrustGap([
      {
        loadout: { championId: 'Gnar' },
        hpKnown: true,
        combatStatsKnown: true,
        abilityRanksKnown: true,
      },
    ]),
    null,
  )
  assert.equal(
    selectedCombatTrustGap([
      {
        loadout: { championId: 'MonkeyKing' },
        hpKnown: false,
        combatStatsKnown: true,
        abilityRanksKnown: true,
      },
    ]),
    'MonkeyKing HP',
  )

  // P6 H2 / S1 — dead+unknown must not false-block when living picks are known
  const deadUnknownAlly = {
    loadout: { championId: 'MonkeyKing' },
    alive: false,
    hpKnown: false,
    combatStatsKnown: false,
    abilityRanksKnown: false,
  }
  const livingKnownBlue = {
    loadout: { championId: 'Gnar' },
    alive: true,
    hpKnown: true,
    combatStatsKnown: true,
    abilityRanksKnown: true,
  }
  const livingKnownRed = {
    loadout: { championId: 'Ornn' },
    alive: true,
    hpKnown: true,
    combatStatsKnown: true,
    abilityRanksKnown: true,
  }
  const mixedSelection = [livingKnownBlue, deadUnknownAlly, livingKnownRed]
  const livingOnly = livingSelectedUnits(mixedSelection)
  assert.equal(livingOnly.length, 2)
  assert.equal(
    livingOnly.every((u) => u.loadout.championId !== 'MonkeyKing'),
    true,
    'dead excluded from living set',
  )
  assert.equal(selectedLacksKnownCombatState(livingOnly), false)
  assert.equal(selectedCombatTrustGap(livingOnly), null)
  // regress guard: all-selected (incl dead) would still block — gate must use livingOnly
  assert.equal(selectedLacksKnownCombatState(mixedSelection), true)

  // P6 H2 / S3 — living+unknown still blocks with champ-specific label
  const livingUnknown = {
    loadout: { championId: 'Azir' },
    alive: true,
    hpKnown: false,
    combatStatsKnown: true,
    abilityRanksKnown: true,
  }
  const livingGapSel = livingSelectedUnits([livingKnownBlue, livingUnknown])
  assert.equal(selectedLacksKnownCombatState(livingGapSel), true)
  assert.equal(selectedCombatTrustGap(livingGapSel), 'Azir HP')

  // P6 H2 / S1 NvM 2v2 — living counts; dead on either side ignored by gate
  const nvm = livingSelectedUnits([
    livingKnownBlue,
    {
      loadout: { championId: 'Sejuani' },
      alive: true,
      hpKnown: true,
      combatStatsKnown: true,
      abilityRanksKnown: true,
    },
    livingKnownRed,
    {
      loadout: { championId: 'Braum' },
      alive: true,
      hpKnown: true,
      combatStatsKnown: true,
      abilityRanksKnown: true,
    },
    deadUnknownAlly,
  ])
  assert.equal(nvm.length, 4)
  assert.equal(selectedLacksKnownCombatState(nvm), false)
  assert.equal(`${nvm.length}`, '4')

  const embeddedActions = renderToStaticMarkup(
    React.createElement(ResearchActionOverlayPanel, {
      enabled: true,
      rows: [
        {
          kind: 'basic_attack',
          tSec: 120,
          tMs: 120_000,
          sourceNetId: 1001,
          sourceChampion: 'Olaf',
          sourceParticipantId: 1,
          targetNetId: null,
          targetChampion: null,
          amount: null,
          researchOnly: true,
          calculatorReady: false,
        },
      ],
      disclosure:
        'embedded replay actions · identity_bound_replay_packets · separate from calculator readiness',
      playheadMs: 120_000,
      loading: false,
      embeddedProductActions: true,
    }),
  )
  assert.match(
    embeddedActions,
    /decoded action timeline · separate from calculator gate/,
  )
  assert.match(embeddedActions, /data-action-source="embedded"/)
  assert.match(embeddedActions, /Olaf/)
  assert.doesNotMatch(embeddedActions, /2970110/)
} finally {
  await vite.close()
}

console.log('phase 5 game review selector tests passed')
