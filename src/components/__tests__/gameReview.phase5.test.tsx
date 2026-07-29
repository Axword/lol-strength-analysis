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
  const { MatchCoverageBadges, MatchPicker, calculatorTrustBlockReason } =
    (await vite.ssrLoadModule(
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
} finally {
  await vite.close()
}

console.log('phase 5 game review selector tests passed')
