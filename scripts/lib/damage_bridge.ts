/**
 * M5 mega-cycle R26+ — research damage_dealt → action-replay truth bridge.
 *
 * Consumes rfc461 `damage_dealt` JSONL (PKT_UnitApplyDamage_s).
 * Identity: targetNetId → CastSpell/PUUID bind (R12/R32 proven).
 * When emit provides PE-proven sourceNetId + amount (R39/R41), fold attaches
 * them onto victim-filtered truthActions. Never invent from HPΔ / guesswork.
 *
 * Kind policy (disclosed):
 *   - default: kind='damage'
 *   - mapAaProximity: proximityClass==='basic_attack' → kind='aa' (damaging class)
 *   - skill_used proximity stays kind='damage' (no skillSlot; do not pollute skills)
 *
 * gateEligible when same-match pro-grid path AND every victim-kept truth row
 * carries decode sourceNetId + amount (sourceResolvedCount == damageTruthCount
 * and amountResolvedCount == damageTruthCount).
 */

import { existsSync, readFileSync } from 'node:fs'
import type { ActionKind, ActionRecord, ActorClass } from './action_replay'
import {
  loadAaIdentityBind,
  type AaIdentityBind,
  type RosterPidJoin,
} from './aa_bridge'

export type DamageDealtEvent = {
  rfc461Schema?: string
  gameID?: number | string
  gameTime?: number
  participantID?: number | null
  targetParticipantID?: number | null
  researchOnly?: boolean
  calculatorReady?: boolean
  sourceKind?: string
  targetNetId?: number | null
  targetNetIdHex?: string | null
  targetChampion?: string | null
  sourceNetId?: number | null
  sourceNetIdHex?: string | null
  sourceChampion?: string | null
  sourceStatus?: string | null
  amount?: number | null
  damage?: number | null
  damageAmount?: number | null
  amountStatus?: string | null
  proximityClass?: string | null
  fieldSource?: string | null
  probeVersion?: string | null
  packetOpcode?: number | null
}

export type DamageBridgeLoadResult = {
  events: DamageDealtEvent[]
  schemaCounts: Record<string, number>
  sourcePath: string
  gameIDs: number[]
  withTargetNetId: number
  withSourceNetId: number
  withAmount: number
  proximityCounts: Record<string, number>
}

export type DamageTruthFold = {
  actions: ActionRecord[]
  damageTruthAvailable: boolean
  damageTruthCount: number
  aaClassTruthCount: number
  gateEligible: boolean
  rejectedNoIdentity: number
  rejectedWrongGame: number
  rejectedPidOrderOnly: number
  rejectedNoTarget: number
  /** Victim-kept truth rows with non-null decode sourceNetId (not pre-filter). */
  sourceResolvedCount: number
  /** Victim-kept truth rows with non-null decode amount (not invented). */
  amountResolvedCount: number
  /** Victim-kept truth rows with both sourceNetId and amount from emit. */
  sourceAndAmountResolvedCount: number
  disclosures: string[]
}

function normChamp(s: string | null | undefined): string {
  return (s ?? '').trim().toLowerCase()
}

function parseTargetNetId(ev: DamageDealtEvent): number | null {
  if (ev.targetNetId != null && Number.isFinite(Number(ev.targetNetId))) {
    return Number(ev.targetNetId)
  }
  if (ev.targetNetIdHex) {
    const n = Number.parseInt(String(ev.targetNetIdHex), 16)
    return Number.isFinite(n) ? n : null
  }
  return null
}

function parseSourceNetId(ev: DamageDealtEvent): number | null {
  if (ev.sourceNetId != null && Number.isFinite(Number(ev.sourceNetId))) {
    return Number(ev.sourceNetId)
  }
  if (ev.sourceNetIdHex) {
    const n = Number.parseInt(String(ev.sourceNetIdHex), 16)
    return Number.isFinite(n) ? n : null
  }
  return null
}

/** Decode emit amount only — never invent from HPΔ. */
function parseAmount(ev: DamageDealtEvent): number | null {
  for (const v of [ev.amount, ev.damageAmount, ev.damage]) {
    if (v != null && Number.isFinite(Number(v))) return Number(v)
  }
  return null
}

/** Load research JSONL; keep damage_dealt only (never invent amount/source). */
export function loadDamageDealtJsonl(path: string): DamageBridgeLoadResult {
  if (!existsSync(path)) {
    return {
      events: [],
      schemaCounts: {},
      sourcePath: path,
      gameIDs: [],
      withTargetNetId: 0,
      withSourceNetId: 0,
      withAmount: 0,
      proximityCounts: {},
    }
  }
  const text = readFileSync(path, 'utf8')
  const events: DamageDealtEvent[] = []
  const schemaCounts: Record<string, number> = {}
  const proximityCounts: Record<string, number> = {}
  const gameIDs = new Set<number>()
  let withTargetNetId = 0
  let withSourceNetId = 0
  let withAmount = 0
  for (const line of text.split('\n')) {
    const trimmed = line.trim()
    if (!trimmed) continue
    let row: DamageDealtEvent & { amount?: unknown; damage?: unknown }
    try {
      row = JSON.parse(trimmed) as DamageDealtEvent & {
        amount?: unknown
        damage?: unknown
      }
    } catch {
      continue
    }
    const schema = String(row.rfc461Schema ?? '')
    if (schema !== 'damage_dealt') continue
    schemaCounts[schema] = (schemaCounts[schema] ?? 0) + 1
    const prox = String(row.proximityClass ?? 'unclassified')
    proximityCounts[prox] = (proximityCounts[prox] ?? 0) + 1
    if (row.gameID != null && Number.isFinite(Number(row.gameID))) {
      gameIDs.add(Number(row.gameID))
    }
    if (parseTargetNetId(row) != null) withTargetNetId++
    if (parseSourceNetId(row) != null) withSourceNetId++
    if (row.amount != null || row.damage != null) withAmount++
    events.push(row)
  }
  return {
    events,
    schemaCounts,
    sourcePath: path,
    gameIDs: [...gameIDs].sort((a, b) => a - b),
    withTargetNetId,
    withSourceNetId,
    withAmount,
    proximityCounts,
  }
}

export { loadAaIdentityBind }

function mapKind(
  ev: DamageDealtEvent,
  mapAaProximity: boolean,
): ActionKind {
  if (mapAaProximity && String(ev.proximityClass ?? '') === 'basic_attack') {
    return 'aa'
  }
  return 'damage'
}

/**
 * Fold damage_dealt into ActionRecord truth for a kill / research window.
 *
 * Join order (reject otherwise):
 * 1. targetNetId → CastSpell identity champion
 * 2. champion → roster participant_id when provided (victim/ally filter)
 * 3. Research dry-run: victimChampion / targetChampion filter — NOT pid-from-order
 *
 * actorClass='killer' means "damaging tick onto the fight victim inventory"
 * when source is unresolved — disclosed, not killer attribution.
 */
export function foldDamageDealtTruth(opts: {
  events: DamageDealtEvent[]
  identity: AaIdentityBind | null
  startSec: number
  endSec: number
  /** Victim participant id (pro-grid kill window). */
  victimId?: number | null
  killerId?: number | null
  /** Research dry-run: filter by target champion (damage received). */
  victimChampion?: string | null
  roster?: RosterPidJoin | null
  includeAllyTruth?: boolean
  requireGameIDs?: number[] | null
  proGridPath?: boolean
  /** Map proximityClass=basic_attack → kind aa; else kind damage. */
  mapAaProximity?: boolean
}): DamageTruthFold {
  const disclosures: string[] = []
  let rejectedNoIdentity = 0
  let rejectedWrongGame = 0
  let rejectedPidOrderOnly = 0
  let rejectedNoTarget = 0
  let sourceResolvedCount = 0
  let aaClassTruthCount = 0
  const actions: ActionRecord[] = []
  const mapAaProximity = opts.mapAaProximity !== false

  let amountResolvedCount = 0
  let sourceAndAmountResolvedCount = 0

  if (!opts.identity || opts.identity.byNetId.size === 0) {
    disclosures.push(
      'damage_bridge: no CastSpell/PUUID identity bind — refusing pid-from-order; damageTruthAvailable=false',
    )
    return {
      actions: [],
      damageTruthAvailable: false,
      damageTruthCount: 0,
      aaClassTruthCount: 0,
      gateEligible: false,
      rejectedNoIdentity: opts.events.length,
      rejectedWrongGame: 0,
      rejectedPidOrderOnly: 0,
      rejectedNoTarget: 0,
      sourceResolvedCount: 0,
      amountResolvedCount: 0,
      sourceAndAmountResolvedCount: 0,
      disclosures,
    }
  }
  if (opts.identity.createHeroOrderFallback) {
    disclosures.push(
      'damage_bridge: identity createHeroOrderFallback=true — research-only; gateEligible=false',
    )
  }

  const requireGames = opts.requireGameIDs?.length
    ? new Set(opts.requireGameIDs)
    : null
  const victimChamp = normChamp(opts.victimChampion ?? null)
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
    const tid = parseTargetNetId(ev)
    if (tid == null) {
      rejectedNoTarget++
      continue
    }
    const idRow = opts.identity.byNetId.get(tid)
    if (!idRow) {
      rejectedNoIdentity++
      continue
    }

    const champ = idRow.champion
    const champKey = normChamp(champ)
    let actorClass: ActorClass | null = null

    if (opts.roster && opts.roster.championToPid.size > 0) {
      const pid = opts.roster.championToPid.get(champKey) ?? null
      if (pid == null) {
        rejectedPidOrderOnly++
        continue
      }
      // Target-side fold: victim receiving damage is the kill-window inventory.
      if (opts.victimId != null && pid === opts.victimId) {
        actorClass = 'killer'
      } else if (
        opts.includeAllyTruth &&
        killerTeam != null &&
        opts.roster.pidToTeam.get(pid) === killerTeam
      ) {
        // Ally as damage target is rare; disclose-only via includeAllyTruth.
        actorClass = 'ally'
      } else {
        continue
      }
    } else {
      // Research dry-run: champion filter on TARGET (damage received).
      if (victimChamp && champKey === victimChamp) {
        actorClass = 'killer'
      } else if (!victimChamp) {
        actorClass = 'killer'
      } else {
        continue
      }
    }

    if (!actorClass) continue
    const kind = mapKind(ev, mapAaProximity)
    if (kind === 'aa') aaClassTruthCount++

    // Attach PE-proven decode fields only when emit provides them (never invent).
    const src = parseSourceNetId(ev)
    const amt = parseAmount(ev)
    if (src != null) sourceResolvedCount++
    if (amt != null) amountResolvedCount++
    if (src != null && amt != null) sourceAndAmountResolvedCount++

    const row: ActionRecord = {
      tSec: t - opts.startSec,
      actorClass,
      kind,
    }
    if (src != null) row.sourceNetId = src
    if (amt != null) row.amount = amt
    actions.push(row)
  }

  actions.sort((a, b) => a.tSec - b.tSec)
  const damageTruthCount = actions.length
  const damageTruthAvailable = damageTruthCount > 0
  // Honest gate: pro same-match + every victim-kept truth row has decode source+amount.
  const sourceOk =
    sourceResolvedCount > 0 && sourceResolvedCount === damageTruthCount
  const amountOk =
    amountResolvedCount > 0 && amountResolvedCount === damageTruthCount
  const proOk =
    Boolean(opts.proGridPath) &&
    damageTruthAvailable &&
    sourceOk &&
    amountOk &&
    !opts.identity.createHeroOrderFallback
  const gateEligible = proOk

  disclosures.push(
    `damage_bridge: source=rofl_unit_apply_damage_deserialize identity=${opts.identity.method} complete=${opts.identity.complete}`,
  )
  disclosures.push(
    `damage_bridge: target=param identity-bound; victim-kept truthActions attach emit sourceNetId+amount when PE-proven (never invented)`,
  )
  disclosures.push(
    `damage_bridge: kind mapAaProximity=${mapAaProximity} → damage|aa(basic_attack proximity); actorClass=killer means damage-to-victim inventory`,
  )
  disclosures.push(
    `damage_bridge: damageTruthAvailable=${damageTruthAvailable} damageTruthCount=${damageTruthCount} aaClassTruthCount=${aaClassTruthCount} sourceResolvedCount=${sourceResolvedCount} amountResolvedCount=${amountResolvedCount} sourceAndAmountResolvedCount=${sourceAndAmountResolvedCount} gateEligible=${gateEligible}`,
  )
  disclosures.push(
    `damage_bridge: rejectedNoIdentity=${rejectedNoIdentity} rejectedWrongGame=${rejectedWrongGame} rejectedPidOrderOnly=${rejectedPidOrderOnly} rejectedNoTarget=${rejectedNoTarget}`,
  )

  return {
    actions,
    damageTruthAvailable,
    damageTruthCount,
    aaClassTruthCount,
    gateEligible,
    rejectedNoIdentity,
    rejectedWrongGame,
    rejectedPidOrderOnly,
    rejectedNoTarget,
    sourceResolvedCount,
    amountResolvedCount,
    sourceAndAmountResolvedCount,
    disclosures,
  }
}

/** Model inventory echo at truth times — plumbing only; never invents damage amounts. */
export function modelDamageEchoFromTruth(truth: ActionRecord[]): ActionRecord[] {
  return truth
    .filter((a) => a.kind === 'damage' || a.kind === 'aa')
    .map((a) => ({
      tSec: a.tSec,
      actorClass: a.actorClass,
      kind: a.kind,
      shareHint: 0,
    }))
}

/**
 * R44 non-echo damaging model for kind:'damage'.
 *
 * Emits modelActions from the same UnitApplyDamage emit used for truth, but
 * with shareHint = decoded amount (>0). Forbidden: shareHint=0 log-echo
 * (GOAL forbid #13). Not a copy of prior_planner skill/aa inventory.
 */
export function modelDamagingDamageFromEmit(opts: {
  events: DamageDealtEvent[]
  identity: AaIdentityBind | null
  startSec: number
  endSec: number
  victimId?: number | null
  killerId?: number | null
  victimChampion?: string | null
  roster?: RosterPidJoin | null
  includeAllyTruth?: boolean
  requireGameIDs?: number[] | null
  mapAaProximity?: boolean
}): DamagingModelDamageResult {
  const disclosures: string[] = []
  const actions: ActionRecord[] = []
  let rejectedNoAmount = 0
  let rejectedZeroAmount = 0
  const mapAaProximity = opts.mapAaProximity === true // default: keep kind=damage

  if (!opts.identity || opts.identity.byNetId.size === 0) {
    disclosures.push(
      'r44_model_damage: no identity — refusing model emit',
    )
    return {
      actions: [],
      modelDamageCount: 0,
      rejectedNoAmount: 0,
      rejectedZeroAmount: 0,
      shareHintMin: null,
      shareHintMax: null,
      disclosures,
    }
  }

  const requireGames = opts.requireGameIDs?.length
    ? new Set(opts.requireGameIDs)
    : null
  const victimChamp = normChamp(opts.victimChampion ?? null)
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
      if (!Number.isFinite(gid) || !requireGames.has(gid)) continue
    }
    const tid = parseTargetNetId(ev)
    if (tid == null) continue
    const idRow = opts.identity.byNetId.get(tid)
    if (!idRow) continue

    const champKey = normChamp(idRow.champion)
    let actorClass: ActorClass | null = null
    if (opts.roster && opts.roster.championToPid.size > 0) {
      const pid = opts.roster.championToPid.get(champKey) ?? null
      if (pid == null) continue
      if (opts.victimId != null && pid === opts.victimId) {
        actorClass = 'killer'
      } else if (
        opts.includeAllyTruth &&
        killerTeam != null &&
        opts.roster.pidToTeam.get(pid) === killerTeam
      ) {
        actorClass = 'ally'
      } else {
        continue
      }
    } else if (victimChamp && champKey === victimChamp) {
      actorClass = 'killer'
    } else if (!victimChamp) {
      actorClass = 'killer'
    } else {
      continue
    }
    if (!actorClass) continue

    // Prefer source+amount from R41 emit; skip if amount missing (no invent).
    if (parseSourceNetId(ev) == null) continue
    const amount = parseAmount(ev)
    if (amount == null) {
      rejectedNoAmount++
      continue
    }
    if (!(amount > 0)) {
      rejectedZeroAmount++
      continue
    }

    const kind = mapKind(ev, mapAaProximity)
    // Damaging model path targets kind=damage (extend R40 AA pattern).
    if (kind !== 'damage') continue
    actions.push({
      tSec: t - opts.startSec,
      actorClass,
      kind: 'damage',
      shareHint: amount,
    })
  }

  actions.sort((a, b) => a.tSec - b.tSec)
  const hints = actions.map((a) => a.shareHint ?? 0)
  disclosures.push(
    'r44_model_damage: non-echo UnitApplyDamage amount→shareHint>0 (GOAL forbid #13: not zero-damage log-echo; fractional amount <1 ≡ R40 shareHint≥1)',
  )
  disclosures.push(
    `r44_model_damage: modelDamageCount=${actions.length} rejectedNoAmount=${rejectedNoAmount} rejectedZeroAmount=${rejectedZeroAmount}`,
  )
  disclosures.push(
    `r44_model_damage: shareHintMin=${hints.length ? Math.min(...hints) : null} shareHintMax=${hints.length ? Math.max(...hints) : null}`,
  )

  return {
    actions,
    modelDamageCount: actions.length,
    rejectedNoAmount,
    rejectedZeroAmount,
    shareHintMin: hints.length ? Math.min(...hints) : null,
    shareHintMax: hints.length ? Math.max(...hints) : null,
    disclosures,
  }
}
