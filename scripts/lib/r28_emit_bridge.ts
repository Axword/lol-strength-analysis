/**
 * R35 — normalize R28 PE-remap research emit → aa_bridge / damage_bridge shapes.
 *
 * R28 JSONL uses:
 *   gameTime (ms) + gameTimeSec, netId (block.param), no attacker/target fields.
 * Bridges expect:
 *   gameTime in seconds, attackerNetId (basic_attack) / targetNetId (damage_dealt).
 *
 * Never invents events, amounts, or sourceNetId. calculatorReady stays false.
 */

import { existsSync, readFileSync } from 'node:fs'
import type { BasicAttackEvent } from './aa_bridge'
import type { DamageDealtEvent } from './damage_bridge'

export type R28RawEvent = {
  rfc461Schema?: string
  gameID?: number | string
  gameTime?: number
  gameTimeSec?: number
  netId?: number | null
  opcode?: number | null
  pkt?: string | null
  attackKind?: string | null
  sourceKind?: string | null
  identityBind?: string | null
  damageAmount?: unknown
  calculatorReady?: boolean
}

export type R28LoadResult = {
  sourcePath: string
  gameIDs: number[]
  basicAttack: BasicAttackEvent[]
  damageDealt: DamageDealtEvent[]
  schemaCounts: Record<string, number>
  withNetId: number
  rejectedNoNetId: number
  rejectedBadTime: number
}

function gameTimeSec(row: R28RawEvent): number | null {
  if (row.gameTimeSec != null && Number.isFinite(Number(row.gameTimeSec))) {
    return Number(row.gameTimeSec)
  }
  const ms = Number(row.gameTime)
  if (!Number.isFinite(ms)) return null
  // R28 emit uses millisecond gameTime; reject absurd second-scale values for ms path.
  if (ms > 1e6 || ms < 0) return ms / 1000
  // Ambiguous small values: prefer ms→sec when gameTimeSec absent and ms looks like ms.
  return ms / 1000
}

/** Load R28 emit JSONL into bridge-compatible event arrays (same-match only). */
export function loadR28EmitJsonl(path: string): R28LoadResult {
  if (!existsSync(path)) {
    return {
      sourcePath: path,
      gameIDs: [],
      basicAttack: [],
      damageDealt: [],
      schemaCounts: {},
      withNetId: 0,
      rejectedNoNetId: 0,
      rejectedBadTime: 0,
    }
  }
  const text = readFileSync(path, 'utf8')
  const basicAttack: BasicAttackEvent[] = []
  const damageDealt: DamageDealtEvent[] = []
  const schemaCounts: Record<string, number> = {}
  const gameIDs = new Set<number>()
  let withNetId = 0
  let rejectedNoNetId = 0
  let rejectedBadTime = 0

  for (const line of text.split('\n')) {
    const trimmed = line.trim()
    if (!trimmed) continue
    let row: R28RawEvent
    try {
      row = JSON.parse(trimmed) as R28RawEvent
    } catch {
      continue
    }
    const schema = String(row.rfc461Schema ?? '')
    if (schema !== 'basic_attack' && schema !== 'damage_dealt') continue
    schemaCounts[schema] = (schemaCounts[schema] ?? 0) + 1

    const t = gameTimeSec(row)
    if (t == null || !Number.isFinite(t)) {
      rejectedBadTime++
      continue
    }
    const nid = row.netId != null ? Number(row.netId) : NaN
    if (!Number.isFinite(nid) || nid === 0) {
      rejectedNoNetId++
      continue
    }
    withNetId++
    if (row.gameID != null && Number.isFinite(Number(row.gameID))) {
      gameIDs.add(Number(row.gameID))
    }

    if (schema === 'basic_attack') {
      basicAttack.push({
        rfc461Schema: 'basic_attack',
        gameID: row.gameID,
        gameTime: t,
        researchOnly: true,
        calculatorReady: false,
        sourceKind: String(row.sourceKind ?? 'rofl_packet_pe_opcode_remap_research'),
        attackerNetId: nid,
        attackerNetIdHex: `0x${nid.toString(16)}`,
        fieldSource: 'r28_block_param_as_attacker_netId',
        probeVersion: 'r28-pe-opcode-remap-16.13-v1',
      })
    } else {
      damageDealt.push({
        rfc461Schema: 'damage_dealt',
        gameID: row.gameID,
        gameTime: t,
        researchOnly: true,
        calculatorReady: false,
        sourceKind: String(row.sourceKind ?? 'rofl_packet_pe_opcode_remap_research'),
        targetNetId: nid,
        targetNetIdHex: `0x${nid.toString(16)}`,
        sourceNetId: null,
        sourceStatus: 'unresolved_in_r28_emit',
        amountStatus: 'null_not_invented',
        proximityClass: null,
        fieldSource: 'r28_block_param_as_target_netId',
        probeVersion: 'r28-pe-opcode-remap-16.13-v1',
        packetOpcode: row.opcode ?? null,
      })
    }
  }

  return {
    sourcePath: path,
    gameIDs: [...gameIDs].sort((a, b) => a - b),
    basicAttack,
    damageDealt,
    schemaCounts,
    withNetId,
    rejectedNoNetId,
    rejectedBadTime,
  }
}
