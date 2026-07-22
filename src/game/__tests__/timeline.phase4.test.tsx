import assert from 'node:assert/strict'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { createServer } from 'vite'
import type { ChampCareerStats } from '../../engine/careerStats'
import {
  snapshotAtTime,
  type GameTimeline,
  type TimelineUnitFrame,
} from '../timeline'

function unit(
  x: number,
  y: number,
  career?: ChampCareerStats,
): TimelineUnitFrame {
  return {
    pid: 1,
    champ: 'Gnar',
    name: 'player',
    team: 100,
    role: 'Top',
    level: 1,
    hp: 0,
    hpMax: 0,
    alive: true,
    hpKnown: false,
    combatStatsKnown: false,
    abilityRanksKnown: false,
    ad: 0,
    ap: 0,
    armor: 0,
    mr: 0,
    as: 100,
    x,
    y,
    positionSource: 'replay_api_focus_selection',
    items: [],
    q: 0,
    w: 0,
    e: 0,
    r: 0,
    career,
  }
}

function timeline(
  first: TimelineUnitFrame,
  second: TimelineUnitFrame,
): GameTimeline {
  return {
    id: 'phase4',
    name: 'Phase 4',
    patch: '16.14',
    source: 'replay_api_playback',
    cadenceMs: 1000,
    participants: [
      {
        participantID: 1,
        summonerName: 'player',
        championName: 'Gnar',
        teamID: 100,
        role: 'Top',
      },
    ],
    frameCount: 2,
    durationMs: 1000,
    frames: [
      { t: 0, units: [first] },
      { t: 1000, units: [second] },
    ],
  }
}

const partial: ChampCareerStats = {
  careerSource: 'liveclient_allgamedata_scores',
  careerCoverage: 'scores_only',
  fieldSources: {
    kills: 'liveclient_allgamedata_scores',
    deaths: 'liveclient_allgamedata_scores',
    assists: 'liveclient_allgamedata_scores',
    cs: 'liveclient_allgamedata_scores',
    visionScore: 'liveclient_allgamedata_scores',
  },
  kills: 0,
  deaths: 0,
  assists: 0,
  cs: 0,
  visionScore: 0,
  unavailableFields: ['damage', 'gold', 'jungleCs', 'objectives'],
}

{
  const continuous = timeline(unit(0.1, 0.2), unit(0.3, 0.4))
  const middle = snapshotAtTime(continuous, 500)
  assert.equal(middle.units[0].position.x, 0.2)
  assert.equal(middle.units[0].position.y, 0.30000000000000004)
  assert.equal(snapshotAtTime(continuous, 1000).units[0].position.x, 0.3)
}

{
  const destination = unit(0.9, 0.9)
  destination.motionFromPrevious = {
    kind: 'discontinuity',
    classification: 'unexplained',
    fromTimeMs: 0,
    toTimeMs: 1000,
    deltaMs: 1000,
    distanceMapUnits: 12000,
    plausibleLimitMapUnits: 1850,
    evidence: ['no_relocation_evidence'],
  }
  const discontinuous = timeline(unit(0.1, 0.1), destination)
  assert.equal(snapshotAtTime(discontinuous, 500).units[0].position.x, 0.1)
  assert.equal(snapshotAtTime(discontinuous, 999).units[0].position.x, 0.1)
  assert.equal(snapshotAtTime(discontinuous, 1000).units[0].position.x, 0.9)
}

{
  const vite = await createServer({
    appType: 'custom',
    server: { middlewareMode: true },
  })
  const { ChampHistoryBoard, farmVisionDisplay } = await vite.ssrLoadModule(
    '/src/components/ChampHistoryBoard.tsx',
  )
  const display = farmVisionDisplay(partial)
  assert.deepEqual(display, {
    cs: '0',
    vision: '0',
    jungleCs: '—',
    source: 'liveclient scores',
  })

  const snapshot = snapshotAtTime(timeline(unit(0.1, 0.1, partial), unit(0.1, 0.1, partial)), 0)
  const html = renderToStaticMarkup(
    React.createElement(ChampHistoryBoard, { snapshot }),
  )
  assert.match(html, /0\/0\/0/)
  assert.match(html, /liveclient scores/)
  assert.match(html, /unavailable/)
  assert.match(html, /—/)
  assert.doesNotMatch(html, />0<em>unavailable/)
  await vite.close()
}

console.log('timeline phase4 tests: ok')
