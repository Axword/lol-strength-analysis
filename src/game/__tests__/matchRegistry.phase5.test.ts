import assert from 'node:assert/strict'
import {
  MATCH_REGISTRY_URL,
  defaultRegistryMatch,
  loadMatchRegistry,
  loadRegisteredTimeline,
  parseMatchRegistryJson,
} from '../timeline'

const matchCode = '3264361042'

function registryJson(overrides: Record<string, unknown> = {}): string {
  return JSON.stringify({
    version: 1,
    defaultMatchCode: matchCode,
    matches: [
      {
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
          champions: Array.from({ length: 10 }, (_, index) => ({
            teamId: index < 5 ? 100 : 200,
            display: `Champion ${index}`,
            asset: `Champion${index}`,
          })),
        },
        coverage: {
          positions: 'full_at_sampled_frames',
          history: 'kda_total_cs_vision_at_sampled_frames',
          hp: 'none',
          combat: 'none',
          ranks: 'none',
        },
        productGates: {
          productValidated: true,
          stableIdentityComplete: true,
          hpTrusted: false,
          calculatorReady: false,
        },
      },
    ],
    ...overrides,
  })
}

function timelineJson(): string {
  return JSON.stringify({
    id: matchCode,
    name: matchCode,
    patch: '16.14',
    source: 'replay_api_playback',
    provenance: {
      matchCode,
      gameId: Number(matchCode),
      positionCoverage: 'full_at_sampled_frames',
      hpCoverage: 'none',
    },
    participants: [
      {
        participantID: 1,
        summonerName: 'Player#BR1',
        championName: 'Zaahen',
        teamID: 100,
        role: 'Top',
      },
    ],
    frameCount: 1,
    durationMs: 61_000,
    frames: [{ t: 61_000, units: [] }],
  })
}

const parsed = parseMatchRegistryJson(registryJson())
assert.equal(defaultRegistryMatch(parsed)?.matchCode, matchCode)
assert.equal(parsed.matches[0].coverage.hp, 'none')
assert.equal(parsed.matches[0].productGates.calculatorReady, false)

const empty = parseMatchRegistryJson(
  JSON.stringify({ version: 1, defaultMatchCode: null, matches: [] }),
)
assert.equal(defaultRegistryMatch(empty), null)

assert.throws(
  () =>
    parseMatchRegistryJson(
      registryJson({
        matches: [
          {
            ...parsed.matches[0],
            timelineUrl: '../legacy.json',
          },
        ],
      }),
    ),
  /timelineUrl is unsafe/,
)

assert.throws(
  () => parseMatchRegistryJson(registryJson({ defaultMatchCode: '3264383283' })),
  /defaultMatchCode/,
)

const requests: string[] = []
const fetchRegistry = (async (input: RequestInfo | URL) => {
  requests.push(String(input))
  return new Response(registryJson(), { status: 200 })
}) as typeof fetch
const loaded = await loadMatchRegistry(fetchRegistry)
assert.equal(requests[0], MATCH_REGISTRY_URL)
assert.equal(loaded.matches.length, 1)

const fetchTimeline = (async (input: RequestInfo | URL) => {
  requests.push(String(input))
  return new Response(timelineJson(), { status: 200 })
}) as typeof fetch
const timeline = await loadRegisteredTimeline(loaded.matches[0], fetchTimeline)
assert.equal(requests[1], `/data/matches/${matchCode}/timeline.json`)
assert.equal(timeline.id, matchCode)

const mismatchedTimeline = (async () =>
  new Response(timelineJson().replaceAll(matchCode, '3264383283'), {
    status: 200,
  })) as typeof fetch
await assert.rejects(
  loadRegisteredTimeline(loaded.matches[0], mismatchedTimeline),
  /identity does not match registry/,
)

console.log('phase 5 match registry loader tests passed')
