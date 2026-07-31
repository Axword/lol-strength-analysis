/**
 * R14 P5 Track 2 — browser-safe identity fold + playhead filter contracts.
 * ≥8 experiments. Never invent AA/damage. Reject unbound / order-pid.
 */
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import {
  filterRowsNearPlayhead,
  foldEventsWithIdentity,
  foldResearchOverlaySlim,
  parseIdentityWinners,
  parseResearchIdentityArtifact,
  parseResearchOverlayJson,
  readResearchAaOverlayFlag,
  rowsFromHpCurveAloneForbidden,
  rowsFromTimelineActionBridge,
  timelineMatchesDefaultResearchOverlay,
  filterRowsForSelectedChampions,
  productSendAttachedResearchActions,
  type ResearchActionOverlaySlim,
  type ResearchActionRow,
} from '../researchActionOverlay'

const root = join(dirname(fileURLToPath(import.meta.url)), '../../..')
const slimPath = join(
  root,
  'public/data/research/aa-overlay/2970110-g1.slim.json',
)
const identityPath = join(
  root,
  'public/data/research/aa-overlay/2970110-g1.identity.json',
)
const identityR22Path = join(
  root,
  'docs/rofl-research/product_ready/r22/castspell-identity-2970110-g1-pid-stamped.json',
)
const identityR25Path = join(
  root,
  'docs/rofl-research/product_ready/r14/2970137-g1.identity.json',
)

let experiment = 0
function exp(name: string, fn: () => void) {
  experiment++
  fn()
  console.log(`E${experiment} PASS — ${name}`)
}

exp('flag default OFF (empty / missing query)', () => {
  assert.equal(readResearchAaOverlayFlag(''), false)
  assert.equal(readResearchAaOverlayFlag('?foo=1'), false)
  assert.equal(readResearchAaOverlayFlag('?researchAaOverlay=0'), false)
})

exp('external research overlay is refused for a different match', () => {
  assert.equal(
    timelineMatchesDefaultResearchOverlay({
      provenance: { gridSeriesId: '2970132', gridGameIndex: 1 },
    }),
    false,
  )
  assert.equal(
    timelineMatchesDefaultResearchOverlay({
      provenance: { gridSeriesId: '2970110', gridGameIndex: 2 },
    }),
    false,
  )
  assert.equal(
    timelineMatchesDefaultResearchOverlay({
      provenance: { gridSeriesId: '2970110', gridGameIndex: 1 },
    }),
    true,
  )
})

exp('R22 identity artifact parses 10/10 PUUID pid stamps', () => {
  const raw = JSON.parse(readFileSync(identityPath, 'utf8'))
  const bind = parseResearchIdentityArtifact(raw)
  assert.ok(bind)
  assert.equal(bind!.createHeroOrderFallback, false)
  assert.equal(bind!.pidStampMethod, 'slim_roster_puuid_join')
  assert.equal(bind!.byNetId.size, 10)
  assert.equal(bind!.netIdToChampion.get(0x400000b7), 'Camille')
  assert.equal(bind!.byNetId.get(0x400000b7)?.participantID, 10)
  assert.equal(bind!.byNetId.get(0x400000ae)?.participantID, 1)
  // Full R22 artifact also parses (browser-safe, no fs inside parse).
  const full = parseResearchIdentityArtifact(
    JSON.parse(readFileSync(identityR22Path, 'utf8')),
  )
  assert.ok(full)
  assert.equal(full!.byNetId.size, 10)
  assert.equal(full!.createHeroOrderFallback, false)
})

exp('Zaahen≠Wukong; MonkeyKing key stable (no rewrite)', () => {
  const map = parseIdentityWinners({
    '0x400000b7': 'Camille',
    '0x40000099': 'Zaahen',
    '0x40000098': 'MonkeyKing',
  })
  assert.equal(map.get(0x40000099), 'Zaahen')
  assert.equal(map.get(0x40000098), 'MonkeyKing')
  assert.notEqual(map.get(0x40000099), 'Wukong')
  assert.notEqual(map.get(0x40000098), 'Wukong')
  const bind = parseResearchIdentityArtifact({
    createHeroOrderFallback: false,
    winners: {
      '0x40000099': 'Zaahen',
      '0x40000098': 'MonkeyKing',
    },
    identityBinding: {
      complete: true,
      createHeroOrderFallback: false,
      pidStampMethod: 'slim_roster_puuid_join',
      participants: [
        {
          netId: 0x40000099,
          champion: 'Zaahen',
          participantID: 3,
          pidStampMethod: 'slim_roster_puuid_join',
        },
        {
          netId: 0x40000098,
          champion: 'MonkeyKing',
          participantID: 4,
          pidStampMethod: 'slim_roster_puuid_join',
        },
      ],
    },
  })
  assert.equal(bind!.netIdToChampion.get(0x40000099), 'Zaahen')
  assert.equal(bind!.netIdToChampion.get(0x40000098), 'MonkeyKing')
})

exp('bound row kept with R22 pid stamp (Camille→Leona)', () => {
  const identity = parseResearchIdentityArtifact(
    JSON.parse(readFileSync(identityPath, 'utf8')),
  )
  const folded = foldEventsWithIdentity(
    [
      {
        kind: 'damage_dealt',
        tSec: 202.1,
        tMs: 202_100,
        sourceNetId: 0x400000b7,
        sourceChampion: null,
        sourceParticipantId: null,
        targetNetId: 0x400000b2,
        targetChampion: null,
        amount: 40,
        researchOnly: true,
        calculatorReady: false,
      },
    ],
    identity,
  )
  assert.equal(folded.rejectedUnbound, 0)
  assert.equal(folded.rows.length, 1)
  assert.equal(folded.rows[0].sourceChampion, 'Camille')
  assert.equal(folded.rows[0].targetChampion, 'Leona')
  assert.equal(folded.rows[0].sourceParticipantId, 10)
  assert.equal(folded.rows[0].targetParticipantId, 5)
})

exp('unbound netId rows rejected (no ghost champs)', () => {
  const identity = parseResearchIdentityArtifact(
    JSON.parse(readFileSync(identityPath, 'utf8')),
  )
  const folded = foldEventsWithIdentity(
    [
      {
        kind: 'basic_attack',
        tSec: 202,
        tMs: 202_000,
        sourceNetId: 999,
        sourceChampion: 'GhostChamp',
        targetNetId: 998,
        targetChampion: 'AlsoGhost',
        amount: null,
        researchOnly: true,
        calculatorReady: false,
      },
      {
        kind: 'damage_dealt',
        tSec: 202.1,
        tMs: 202_100,
        sourceNetId: 0x400000b7,
        sourceChampion: null,
        targetNetId: 0x400000b2,
        targetChampion: null,
        amount: 40,
        researchOnly: true,
        calculatorReady: false,
      },
    ],
    identity,
  )
  assert.equal(folded.rejectedUnbound, 1)
  assert.equal(folded.rows.length, 1)
  assert.equal(folded.rows[0].sourceChampion, 'Camille')
})

exp('createHeroOrderFallback / pid-from-order refused', () => {
  const identity = parseResearchIdentityArtifact({
    createHeroOrderFallback: true,
    winners: { '0x400000b7': 'Camille' },
    identityBinding: {
      createHeroOrderFallback: true,
      participants: [
        {
          netId: 0x400000b7,
          champion: 'Camille',
          participantID: 1,
          pidStampMethod: 'create_hero_order',
        },
      ],
    },
  })
  const folded = foldEventsWithIdentity(
    [
      {
        kind: 'basic_attack',
        tSec: 202,
        tMs: 202_000,
        sourceNetId: 0x400000b7,
        sourceChampion: 'Camille',
        targetNetId: null,
        targetChampion: null,
        amount: null,
        researchOnly: true,
        calculatorReady: false,
      },
    ],
    identity,
  )
  assert.equal(folded.rows.length, 0)
  assert.ok(folded.rejectedOrderPid >= 1)
  assert.match(folded.disclosure, /pid-from-order|createHeroOrderFallback/i)
})

exp('scrambled event pid vs R22 stamp rejected (not ghost-bound)', () => {
  const identity = parseResearchIdentityArtifact(
    JSON.parse(readFileSync(identityPath, 'utf8')),
  )
  // Camille is pid 10 via PUUID; pretend order-pid 1 (Ambessa's slot).
  const folded = foldEventsWithIdentity(
    [
      {
        kind: 'basic_attack',
        tSec: 202,
        tMs: 202_000,
        sourceNetId: 0x400000b7,
        sourceChampion: 'Camille',
        sourceParticipantId: 1,
        targetNetId: 0x400000b2,
        targetChampion: 'Leona',
        targetParticipantId: 5,
        amount: null,
        researchOnly: true,
        calculatorReady: false,
      },
    ],
    identity,
  )
  assert.equal(folded.rows.length, 0)
  assert.equal(folded.rejectedOrderPid, 1)
})

exp('playhead ±20s filter is second-precise (ms)', () => {
  const rows: ResearchActionRow[] = [
    {
      kind: 'basic_attack',
      tSec: 180,
      tMs: 180_000,
      sourceNetId: 1,
      sourceChampion: 'Camille',
      targetNetId: null,
      targetChampion: null,
      amount: null,
      researchOnly: true,
      calculatorReady: false,
    },
    {
      kind: 'damage_dealt',
      tSec: 202,
      tMs: 202_000,
      sourceNetId: 1,
      sourceChampion: 'Camille',
      targetNetId: 2,
      targetChampion: 'Leona',
      amount: 10,
      researchOnly: true,
      calculatorReady: false,
    },
    {
      kind: 'basic_attack',
      tSec: 240,
      tMs: 240_000,
      sourceNetId: 1,
      sourceChampion: 'Camille',
      targetNetId: null,
      targetChampion: null,
      amount: null,
      researchOnly: true,
      calculatorReady: false,
    },
  ]
  const near = filterRowsNearPlayhead(rows, 202_000, 20)
  assert.equal(near.length, 1)
  assert.equal(near[0].tMs, 202_000)
  const wider = filterRowsNearPlayhead(rows, 202_000, 25)
  assert.equal(wider.length, 2)
  // boundary: exactly ±20s inclusive
  const edge = filterRowsNearPlayhead(rows, 202_000, 20)
  assert.ok(edge.every((r) => Math.abs(r.tMs - 202_000) <= 20_000))
})

exp('HP curve helper never yields AA/damage rows', () => {
  assert.deepEqual(rowsFromHpCurveAloneForbidden(), [])
})

exp('2970110-g1 slim + R22 identity fold keeps kill-window rows with pids', () => {
  const text = readFileSync(slimPath, 'utf8')
  const slim = parseResearchOverlayJson(text)
  assert.ok(slim)
  assert.equal(slim!.calculatorReady, false)
  const identity = parseResearchIdentityArtifact(
    JSON.parse(readFileSync(identityPath, 'utf8')),
  )
  const folded = foldResearchOverlaySlim(slim, identity)
  assert.ok(folded.rows.length >= 1, 'expected identity-bound rows')
  const atKill = folded.rows.filter((r) => r.tSec >= 201.5 && r.tSec <= 202.5)
  assert.ok(
    atKill.length >= 1,
    `expected ≥1 event near t=202s, got ${atKill.length}`,
  )
  for (const row of atKill) {
    assert.ok(row.sourceChampion || row.targetChampion)
    assert.equal(row.researchOnly, true)
    assert.equal(row.calculatorReady, false)
    if (row.sourceNetId != null && identity!.netIdToChampion.has(row.sourceNetId)) {
      assert.equal(
        row.sourceParticipantId,
        identity!.byNetId.get(row.sourceNetId)?.participantID ?? null,
      )
    }
  }
  const nearPlayhead = filterRowsNearPlayhead(folded.rows, 202_000, 20)
  assert.ok(nearPlayhead.length >= 1, 'playhead filter must keep kill-second rows')
})

exp('R25 holdout identity parses; refuse cross-match remap into 2970110 fold', () => {
  const r25 = parseResearchIdentityArtifact(
    JSON.parse(readFileSync(identityR25Path, 'utf8')),
  )
  assert.ok(r25)
  assert.equal(r25!.createHeroOrderFallback, false)
  assert.ok(r25!.byNetId.size >= 1)
  // Same netId space must not silently remap 2970110 Camille onto holdout champs.
  const r22 = parseResearchIdentityArtifact(
    JSON.parse(readFileSync(identityPath, 'utf8')),
  )!
  const camille22 = r22.netIdToChampion.get(0x400000b7)
  const champ25 = r25!.netIdToChampion.get(0x400000b7)
  if (champ25 != null && camille22 != null && champ25 !== camille22) {
    // Holdout reused netId with different champ — fold must use supplied identity only.
    const folded = foldEventsWithIdentity(
      [
        {
          kind: 'basic_attack',
          tSec: 100,
          tMs: 100_000,
          sourceNetId: 0x400000b7,
          sourceChampion: null,
          targetNetId: null,
          targetChampion: null,
          amount: null,
          researchOnly: true,
          calculatorReady: false,
        },
      ],
      r25,
    )
    assert.equal(folded.rows[0]?.sourceChampion, champ25)
    assert.notEqual(folded.rows[0]?.sourceChampion, 'Camille')
  } else {
    // Distinct roster OK — still must not invent rows from empty events.
    assert.equal(foldEventsWithIdentity([], r25).rows.length, 0)
  }
})

exp('missing slim ⇒ empty rows + disclosure (no invent)', () => {
  const folded = foldResearchOverlaySlim(null)
  assert.equal(folded.rows.length, 0)
  assert.match(folded.disclosure, /missing|invented/i)
})

exp('winners-only identity strips event order-pid (no invent, row kept)', () => {
  const slim: ResearchActionOverlaySlim = {
    schema: 'test',
    researchOnly: true,
    calculatorReady: false,
    label: 'research overlay · not calculatorReady',
    identity: {
      winners: { '0x400000b7': 'Camille', '0x400000b2': 'Leona' },
      createHeroOrderFallback: false,
    },
    events: [
      {
        kind: 'damage_dealt',
        tSec: 202.1,
        tMs: 202_100,
        sourceNetId: 0x400000b7,
        sourceChampion: null,
        sourceParticipantId: 99, // untrusted order invent
        targetNetId: 0x400000b2,
        targetChampion: null,
        targetParticipantId: 98,
        amount: 40,
        researchOnly: true,
        calculatorReady: false,
      },
    ],
  }
  const folded = foldResearchOverlaySlim(slim)
  assert.equal(folded.rows.length, 1)
  assert.equal(folded.rows[0].sourceChampion, 'Camille')
  assert.equal(folded.rows[0].sourceParticipantId, null)
  assert.equal(folded.rows[0].targetParticipantId, null)
})

// --- R10 follow-up: timeline fuse → UI bridge (F) ---

exp('timeline bridge maps identity-bound basicAttack + damageDealt', () => {
  const bridged = rowsFromTimelineActionBridge({
    participants: [
      { participantID: 8, championName: 'Camille' },
      { participantID: 3, championName: 'Leona' },
    ],
    basicAttack: [
      { tMs: 202_100, participantId: 8, netId: 0x400000b7, targetNetId: 0x400000b2, targetParticipantId: 3 },
    ],
    damageDealt: [
      {
        tMs: 202_150,
        participantId: 8,
        netId: 0x400000b7,
        targetNetId: 0x400000b2,
        targetParticipantId: 3,
        amount: 42,
      },
    ],
    provenance: { aaCoverage: 'research_overlay', calculatorReady: false },
  })
  assert.equal(bridged.source, 'timeline_bridge')
  assert.equal(bridged.rows.length, 2)
  assert.equal(bridged.rows[0].kind, 'basic_attack')
  assert.equal(bridged.rows[0].sourceChampion, 'Camille')
  assert.equal(bridged.rows[0].sourceParticipantId, 8)
  assert.equal(bridged.rows[1].kind, 'damage_dealt')
  assert.equal(bridged.rows[1].amount, 42)
  assert.equal(bridged.rows[0].researchOnly, true)
  assert.equal(bridged.rows[0].calculatorReady, false)
  assert.match(bridged.disclosure, /separate from calculator readiness/)
})

exp('timeline bridge rejects missing netId/pid (no invent)', () => {
  const bridged = rowsFromTimelineActionBridge({
    basicAttack: [
      { tMs: 1000, participantId: 1, netId: 0 } as {
        tMs: number
        participantId: number
        netId: number
      },
    ],
  })
  assert.equal(bridged.rows.length, 0)
  assert.ok(bridged.rejectedMissingIdentity >= 1)
})

exp('timeline bridge empty when arrays absent (honest)', () => {
  const bridged = rowsFromTimelineActionBridge({
    participants: [{ participantID: 1, championName: 'Camille' }],
  })
  assert.equal(bridged.source, 'empty')
  assert.equal(bridged.rows.length, 0)
  assert.match(bridged.disclosure, /not invented/)
})

exp('selected-champion filter + Send never attaches bridge rows', () => {
  const bridged = rowsFromTimelineActionBridge({
    participants: [
      { participantID: 8, championName: 'Camille' },
      { participantID: 3, championName: 'Leona' },
    ],
    damageDealt: [
      {
        tMs: 1000,
        participantId: 8,
        netId: 0x400000b7,
        targetParticipantId: 3,
        targetNetId: 0x400000b2,
        amount: 1,
      },
    ],
  })
  const filtered = filterRowsForSelectedChampions(bridged.rows, ['Camille'])
  assert.equal(filtered.length, 1)
  assert.deepEqual(productSendAttachedResearchActions(bridged.rows), [])
  const none = filterRowsForSelectedChampions(bridged.rows, ['Ezreal'])
  assert.equal(none.length, 0)
})

console.log(`\nresearchActionOverlay Track2: ${experiment} experiments passed`)
assert.ok(experiment >= 8, `need ≥8 experiments, got ${experiment}`)
