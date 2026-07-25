/**
 * R22 P8 H1 — aa_bridge loadAaIdentityBind consumes PUUID-stamped participantID.
 * Never invents pid from createHeroEvents order.
 */
import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { loadAaIdentityBind } from '../lib/aa_bridge'

const STAMPED = resolve(
  'docs/rofl-research/product_ready/r22/castspell-identity-2970110-g1-pid-stamped.json',
)
const RAW_R32 = resolve(
  'docs/rofl-research/packet_decode/r32/castspell-identity-2970110-g1.json',
)

describe('R22 PUUID pid stamp → aa_bridge', () => {
  it('raw R32 bind has null participantID', () => {
    if (!existsSync(RAW_R32)) return
    const bind = loadAaIdentityBind(RAW_R32)
    expect(bind).not.toBeNull()
    expect(bind!.complete).toBe(true)
    expect(bind!.createHeroOrderFallback).toBe(false)
    const pids = [...bind!.byNetId.values()].map((p) => p.participantID ?? null)
    expect(pids.every((p) => p == null)).toBe(true)
  })

  it('stamped artifact exposes 10/10 participantID via PUUID join', () => {
    if (!existsSync(STAMPED)) {
      expect(existsSync(STAMPED), 'run r22_stamp_pid_puuid_join.py first').toBe(true)
      return
    }
    const raw = JSON.parse(readFileSync(STAMPED, 'utf8')) as {
      identityBinding: {
        pidStampMethod?: string
        createHeroOrderFallback?: boolean
        participants: Array<{
          participantID?: number
          puuid?: string
          netId: number
        }>
      }
      createHeroOrderFallback?: boolean
      identityPidComplete?: boolean
      calculatorReady?: boolean
    }
    expect(raw.identityBinding.pidStampMethod).toBe('slim_roster_puuid_join')
    expect(raw.identityBinding.createHeroOrderFallback).toBe(false)
    expect(raw.identityPidComplete).toBe(true)
    expect(raw.calculatorReady).toBe(false)

    const bind = loadAaIdentityBind(STAMPED)
    expect(bind).not.toBeNull()
    expect(bind!.byNetId.size).toBe(10)
    const pids = [...bind!.byNetId.values()].map((p) => p.participantID)
    expect(pids.every((p) => p != null && p >= 1 && p <= 10)).toBe(true)
    expect(new Set(pids).size).toBe(10)

    // Poison check: stamped rows must match artifact participants, not invent order.
    for (const p of raw.identityBinding.participants) {
      const row = bind!.byNetId.get(p.netId)
      expect(row?.participantID).toBe(p.participantID)
      expect(row?.puuid).toBe(p.puuid)
    }
  })
})
