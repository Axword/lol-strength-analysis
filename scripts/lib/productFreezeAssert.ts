/**
 * Shared freeze assert for eval / KEEP writers (P10 Track2 freezeEvalWire).
 * Assert-only — never rewrites freeze upward.
 */
import { existsSync, readFileSync } from 'node:fs'
import { join, resolve } from 'node:path'

export const FREEZE_COMPOSITE = 0.9683
export const PARENT_FORBIDDEN = '/Users/river/Projects/lol-strength-analysis'

export type FreezeAssertResult = {
  ok: boolean
  worktree: string
  never_edited_parent: boolean
  composite: number | null
  shipGate: boolean | null
  productShipGate: boolean | null
  packetDecodeGate: boolean | null
  failures: string[]
}

function readJson<T>(path: string): T {
  return JSON.parse(readFileSync(path, 'utf8')) as T
}

/** Assert ship freeze pins. Does not mutate files. */
export function assertProductFreeze(root = process.cwd()): FreezeAssertResult {
  const worktree = resolve(root)
  const failures: string[] = []
  const never_edited_parent =
    worktree !== PARENT_FORBIDDEN && worktree.includes('/.codex/worktrees/')
  if (!never_edited_parent) failures.push('never_edited_parent')

  const bestPath = join(worktree, 'docs/rofl-research/autoresearch/best.json')
  const packetPath = join(
    worktree,
    'docs/rofl-research/autoresearch/packet_decode/PACKET_DECODE_GATE.json',
  )
  if (!existsSync(bestPath)) failures.push(`missing ${bestPath}`)
  if (!existsSync(packetPath)) failures.push(`missing ${packetPath}`)

  let composite: number | null = null
  let shipGate: boolean | null = null
  let productShipGate: boolean | null = null
  let packetDecodeGate: boolean | null = null

  if (existsSync(bestPath)) {
    const best = readJson<{
      composite?: number
      shipGate?: boolean
      productShipGate?: boolean
    }>(bestPath)
    composite = best.composite ?? null
    shipGate = best.shipGate ?? null
    productShipGate = best.productShipGate ?? null
    if (best.composite !== FREEZE_COMPOSITE) {
      failures.push(`composite got ${best.composite} want ${FREEZE_COMPOSITE}`)
    }
    if (best.shipGate !== true) failures.push(`shipGate got ${best.shipGate}`)
    if (best.productShipGate !== true) {
      failures.push(`productShipGate got ${best.productShipGate}`)
    }
  }

  if (existsSync(packetPath)) {
    const packet = readJson<{ packetDecodeGate?: boolean }>(packetPath)
    packetDecodeGate = packet.packetDecodeGate ?? null
    if (packet.packetDecodeGate !== true) {
      failures.push(`packetDecodeGate got ${packet.packetDecodeGate}`)
    }
  }

  return {
    ok: failures.length === 0,
    worktree,
    never_edited_parent,
    composite,
    shipGate,
    productShipGate,
    packetDecodeGate,
    failures,
  }
}

/** Hard-fail helper for KEEP writers. */
export function requireProductFreeze(root = process.cwd()): void {
  const r = assertProductFreeze(root)
  if (!r.ok) {
    throw new Error(
      `product freeze assert failed: ${r.failures.join('; ')} (worktree=${r.worktree})`,
    )
  }
}
