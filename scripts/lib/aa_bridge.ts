/**
 * M5 Track 3 — research AA bridge adapter.
 *
 * Maps rfc461 `basic_attack` / `damage_dealt` JSONL (ROFL decode path) →
 * ActionRecord{kind:'aa'} for action-replay truth inventories.
 *
 * Identity: attackerNetId → CastSpell/PUUID bind only. Rejects pid-from-order
 * (sorted netId ordinal) when an identity artifact is supplied.
 * Never invents AA from HPΔ. Never sets calculatorReady / packetDecodeGate.
 */

import { existsSync, readFileSync } from 'node:fs'
import type { ActionRecord, ActorClass } from './action_replay'

export type BasicAttackEvent = {
  rfc461Schema?: string
  gameID?: number | string
  gameTime?: number
  participantID?: number | null
  targetParticipantID?: number | null
  researchOnly?: boolean
  calculatorReady?: boolean
  sourceKind?: string
  attackerNetId?: number | null
  attackerNetIdHex?: string | null
  attackerChampion?: string | null
  targetNetId?: number | null
  targetChampion?: string | null
  fieldSource?: string
  probeVersion?: string
}

export type AaIdentityParticipant = {
  puuid?: string
  fullRiotId?: string
  netId: number
  champion: string
  /** Live/roster participant id when known via PUUID join — never invent from order */
  participantID?: number | null
}

export type AaIdentityBind = {
  path: string
  method: string
  complete: boolean
  createHeroOrderFallback: boolean
  /**
   * When explicitly false, fold keeps gateEligible=false even on pro same-match
   * (e.g. spatial roster join without CastSpell string release / criterion C).
   * Undefined → derive from createHeroOrderFallback + proGridPath as before.
   */
  gateEligible?: boolean
  /** netId → champion (CastSpell winners / spatial join) */
  netIdToChampion: Map<number, string>
  /** netId → bind row */
  byNetId: Map<number, AaIdentityParticipant>
  /** champion (casefold) → netId */
  championToNetId: Map<string, number>
}

export type AaBridgeLoadResult = {
  events: BasicAttackEvent[]
  schemaCounts: Record<string, number>
  sourcePath: string
  gameIDs: number[]
  withAttackerNetId: number
  withTargetNetId: number
}

export type AaTruthFold = {
  actions: ActionRecord[]
  aaTruthAvailable: boolean
  aaTruthCount: number
  gateEligible: boolean
  rejectedNoIdentity: number
  rejectedWrongGame: number
  rejectedPidOrderOnly: number
  disclosures: string[]
}

function normChamp(s: string | null | undefined): string {
  return (s ?? '').trim().toLowerCase()
}

function parseNetId(ev: BasicAttackEvent): number | null {
  if (ev.attackerNetId != null && Number.isFinite(Number(ev.attackerNetId))) {
    return Number(ev.attackerNetId)
  }
  if (ev.attackerNetIdHex) {
    const n = Number.parseInt(String(ev.attackerNetIdHex), 16)
    return Number.isFinite(n) ? n : null
  }
  return null
}

/** Load research JSONL; keep basic_attack + damage_dealt only. */
export function loadAaResearchJsonl(path: string): AaBridgeLoadResult {
  if (!existsSync(path)) {
    return {
      events: [],
      schemaCounts: {},
      sourcePath: path,
      gameIDs: [],
      withAttackerNetId: 0,
      withTargetNetId: 0,
    }
  }
  const text = readFileSync(path, 'utf8')
  const events: BasicAttackEvent[] = []
  const schemaCounts: Record<string, number> = {}
  const gameIDs = new Set<number>()
  let withAttackerNetId = 0
  let withTargetNetId = 0
  for (const line of text.split('\n')) {
    const trimmed = line.trim()
    if (!trimmed) continue
    let row: BasicAttackEvent
    try {
      row = JSON.parse(trimmed) as BasicAttackEvent
    } catch {
      continue
    }
    const schema = String(row.rfc461Schema ?? '')
    if (schema !== 'basic_attack' && schema !== 'damage_dealt') continue
    schemaCounts[schema] = (schemaCounts[schema] ?? 0) + 1
    if (row.gameID != null && Number.isFinite(Number(row.gameID))) {
      gameIDs.add(Number(row.gameID))
    }
    if (parseNetId(row) != null) withAttackerNetId++
    if (row.targetNetId != null) withTargetNetId++
    events.push(row)
  }
  return {
    events,
    schemaCounts,
    sourcePath: path,
    gameIDs: [...gameIDs].sort((a, b) => a - b),
    withAttackerNetId,
    withTargetNetId,
  }
}

/**
 * Load CastSpell / PUUID identity artifact.
 * Prefers identityBinding.participants (PUUID↔netId↔champion).
 * Does not trust createHeroEvents.participantID alone (that is sorted-netId order).
 */
export function loadAaIdentityBind(path: string): AaIdentityBind | null {
  if (!existsSync(path)) return null
  const data = JSON.parse(readFileSync(path, 'utf8')) as {
    method?: string
    createHeroOrderFallback?: boolean
    gateEligible?: boolean
    winners?: Record<string, string>
    identityBinding?: {
      method?: string
      complete?: boolean
      createHeroOrderFallback?: boolean
      gateEligible?: boolean
      participants?: Array<{
        puuid?: string
        fullRiotId?: string
        netId?: number
        champion?: string
        participantID?: number
      }>
    }
    createHeroEvents?: Array<{
      CreateHero?: {
        net_id?: number
        champion?: string
        participantID?: number
      }
    }>
  }
  const bind = data.identityBinding
  const netIdToChampion = new Map<number, string>()
  const byNetId = new Map<number, AaIdentityParticipant>()
  const championToNetId = new Map<string, number>()

  for (const [k, champ] of Object.entries(data.winners ?? {})) {
    const nid = Number.parseInt(k, 16)
    if (!Number.isFinite(nid) || !champ) continue
    netIdToChampion.set(nid, champ)
    championToNetId.set(normChamp(champ), nid)
  }

  for (const p of bind?.participants ?? []) {
    const nid = Number(p.netId)
    if (!Number.isFinite(nid) || !p.champion) continue
    netIdToChampion.set(nid, p.champion)
    championToNetId.set(normChamp(p.champion), nid)
    byNetId.set(nid, {
      puuid: p.puuid,
      fullRiotId: p.fullRiotId,
      netId: nid,
      champion: p.champion,
      // Keep participantID only when the artifact explicitly supplies it
      // (PUUID join or same-match spatial roster join — never sorted-netId invent).
      participantID: p.participantID ?? null,
    })
  }

  // Champion-only rows from winners when participants missing.
  for (const [nid, champ] of netIdToChampion) {
    if (!byNetId.has(nid)) {
      byNetId.set(nid, {
        netId: nid,
        champion: champ,
        participantID: null,
      })
    }
  }

  const gateEligibleRaw = bind?.gateEligible ?? data.gateEligible
  return {
    path,
    method: String(bind?.method ?? data.method ?? 'unknown'),
    complete: Boolean(bind?.complete),
    createHeroOrderFallback: Boolean(
      bind?.createHeroOrderFallback ?? data.createHeroOrderFallback,
    ),
    gateEligible:
      typeof gateEligibleRaw === 'boolean' ? gateEligibleRaw : undefined,
    netIdToChampion,
    byNetId,
    championToNetId,
  }
}

export type RosterPidJoin = {
  /** champion_name (asset) → participant_id from slim sqlite / livestats */
  championToPid: Map<string, number>
  /** participant_id → team_id */
  pidToTeam: Map<number, number>
  /** Expected gameID from meta (optional gate) */
  gameID?: number | null
  seriesId?: string | null
}

/**
 * Fold decode-path AA events into ActionRecord truth for a kill window.
 *
 * Join order (reject otherwise):
 * 1. attackerNetId → CastSpell identity champion
 * 2. champion → roster participant_id (PUUID/livestats roster) when provided
 * 3. If no roster: keep events keyed by netId/champion for research dry-run
 *    using killerChampion / allyChampions filters — still NOT pid-from-order.
 */
export function foldBasicAttackTruth(opts: {
  events: BasicAttackEvent[]
  identity: AaIdentityBind | null
  startSec: number
  endSec: number
  killerId?: number | null
  victimId?: number | null
  killerChampion?: string | null
  roster?: RosterPidJoin | null
  includeAllyTruth?: boolean
  /** When set, drop events whose gameID is not in this set (pro-grid gate path). */
  requireGameIDs?: number[] | null
  /** Research dry-run may allow fixture gameIDs; gateEligible stays false unless pro. */
  proGridPath?: boolean
}): AaTruthFold {
  const disclosures: string[] = []
  let rejectedNoIdentity = 0
  let rejectedWrongGame = 0
  let rejectedPidOrderOnly = 0
  const actions: ActionRecord[] = []

  if (!opts.identity || opts.identity.byNetId.size === 0) {
    disclosures.push(
      'aa_bridge: no CastSpell/PUUID identity bind — refusing pid-from-order; aaTruthAvailable=false',
    )
    return {
      actions: [],
      aaTruthAvailable: false,
      aaTruthCount: 0,
      gateEligible: false,
      rejectedNoIdentity: opts.events.length,
      rejectedWrongGame: 0,
      rejectedPidOrderOnly: 0,
      disclosures,
    }
  }
  if (opts.identity.createHeroOrderFallback) {
    disclosures.push(
      'aa_bridge: identity createHeroOrderFallback=true — research-only; gateEligible=false',
    )
  }

  const requireGames = opts.requireGameIDs?.length
    ? new Set(opts.requireGameIDs)
    : null
  const killerChamp = normChamp(opts.killerChampion ?? null)
  let killerTeam: number | null = null
  if (opts.roster && opts.killerId != null) {
    killerTeam = opts.roster.pidToTeam.get(opts.killerId) ?? null
  }

  for (const ev of opts.events) {
    const t = Number(ev.gameTime)
    if (!Number.isFinite(t) || t < opts.startSec - 1e-9 || t > opts.endSec + 1e-9) {
      continue
    }
    if (requireGames) {
      const gid = Number(ev.gameID)
      if (!Number.isFinite(gid) || !requireGames.has(gid)) {
        rejectedWrongGame++
        continue
      }
    }
    const nid = parseNetId(ev)
    if (nid == null) {
      rejectedNoIdentity++
      continue
    }
    const idRow = opts.identity.byNetId.get(nid)
    if (!idRow) {
      rejectedNoIdentity++
      continue
    }
    const champ = idRow.champion
    const champKey = normChamp(champ)

    let pid: number | null = null
    let actorClass: ActorClass | null = null

    // Prefer explicit identity participantID (spatial/PUUID bind) over champion
    // name join; never use JSONL participantID (sorted-netId ordinal).
    if (idRow.participantID != null && Number.isFinite(idRow.participantID)) {
      pid = Number(idRow.participantID)
    }

    if (opts.roster && opts.roster.championToPid.size > 0) {
      if (pid == null) {
        pid = opts.roster.championToPid.get(champKey) ?? null
      }
      if (pid == null) {
        // Do not fall back to JSONL participantID (often sorted-netId ordinal).
        rejectedPidOrderOnly++
        continue
      }
      if (opts.victimId != null && pid === opts.victimId) continue
      if (opts.killerId != null && pid === opts.killerId) {
        actorClass = 'killer'
      } else if (
        killerTeam != null &&
        opts.roster.pidToTeam.get(pid) === killerTeam &&
        opts.includeAllyTruth
      ) {
        actorClass = 'ally'
      } else {
        continue
      }
    } else {
      // Research dry-run: champion filter only (no roster pid order).
      if (killerChamp && champKey === killerChamp) {
        actorClass = 'killer'
      } else if (opts.includeAllyTruth && killerChamp && champKey !== killerChamp) {
        actorClass = 'ally'
      } else if (!killerChamp) {
        actorClass = 'killer'
      } else {
        continue
      }
    }

    if (!actorClass) continue
    actions.push({
      tSec: t - opts.startSec,
      actorClass,
      kind: 'aa',
    })
  }

  actions.sort((a, b) => a.tSec - b.tSec)
  const aaTruthCount = actions.length
  const aaTruthAvailable = aaTruthCount > 0
  const proOk =
    Boolean(opts.proGridPath) &&
    aaTruthAvailable &&
    !opts.identity.createHeroOrderFallback
  // Explicit identity.gateEligible=false blocks criterion-C (e.g. spatial bind
  // without CastSpell string release). Explicit true still requires proOk.
  let gateEligible = proOk
  if (opts.identity.gateEligible === false) gateEligible = false
  else if (opts.identity.gateEligible === true) gateEligible = proOk

  disclosures.push(
    `aa_bridge: source=rofl_basic_attack_deserialize identity=${opts.identity.method} complete=${opts.identity.complete}`,
  )
  disclosures.push(
    `aa_bridge: aaTruthAvailable=${aaTruthAvailable} aaTruthCount=${aaTruthCount} gateEligible=${gateEligible} (HPΔ invent forbidden; pro-grid path required for gate)`,
  )
  disclosures.push(
    `aa_bridge: rejectedNoIdentity=${rejectedNoIdentity} rejectedWrongGame=${rejectedWrongGame} rejectedPidOrderOnly=${rejectedPidOrderOnly}`,
  )

  return {
    actions,
    aaTruthAvailable,
    aaTruthCount,
    gateEligible,
    rejectedNoIdentity,
    rejectedWrongGame,
    rejectedPidOrderOnly,
    disclosures,
  }
}

/** Model inventory AA at truth times — adapter plumbing only; not gate evidence. */
export function modelAaEchoFromTruth(truthAa: ActionRecord[]): ActionRecord[] {
  return truthAa
    .filter((a) => a.kind === 'aa')
    .map((a) => ({
      tSec: a.tSec,
      actorClass: a.actorClass,
      kind: 'aa' as const,
      shareHint: 0,
    }))
}
