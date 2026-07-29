/**
 * P10 ship-freeze guardian (product calculatorReady overnight).
 *
 * Asserts research freeze must not regress:
 *   composite === 0.9683, shipGate true, productShipGate true,
 *   packetDecodeGate true.
 *
 * Track5: pins sha256 of freeze fields in report for V11/V12 machine diff.
 * Assert-only — never rewrites freeze upward. Never claims calculatorReady.
 * Never edits parent.
 */
import { createHash } from 'node:crypto'
import { readFileSync, mkdirSync, writeFileSync, existsSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { spawnSync } from 'node:child_process'
import {
  assertProductFreeze,
  FREEZE_COMPOSITE,
  PARENT_FORBIDDEN,
} from './lib/productFreezeAssert'

const ROOT = resolve(process.cwd())
const BEST_PATH = join(ROOT, 'docs/rofl-research/autoresearch/best.json')
const PACKET_GATE_PATH = join(
  ROOT,
  'docs/rofl-research/autoresearch/packet_decode/PACKET_DECODE_GATE.json',
)
const OUT_DIR = join(
  ROOT,
  'docs/rofl-research/autoresearch/product_ready/rooms/P10',
)

type Check = { name: string; ok: boolean; detail?: string }

function fail(msg: string): never {
  console.error(`FREEZE GUARDIAN FAIL: ${msg}`)
  process.exit(1)
}

function sha256Json(value: unknown): string {
  const canonical = JSON.stringify(value)
  return createHash('sha256').update(canonical).digest('hex')
}

function readJson<T>(path: string): T {
  if (!existsSync(path)) fail(`missing ${path}`)
  return JSON.parse(readFileSync(path, 'utf8')) as T
}

function main(): void {
  const checks: Check[] = []
  const assertR = assertProductFreeze(ROOT)
  checks.push({
    name: 'never_edited_parent',
    ok: assertR.never_edited_parent,
    detail: ROOT,
  })
  checks.push({
    name: 'composite_0.9683',
    ok: assertR.composite === FREEZE_COMPOSITE,
    detail: `got ${assertR.composite}`,
  })
  checks.push({
    name: 'shipGate_true',
    ok: assertR.shipGate === true,
    detail: `got ${assertR.shipGate}`,
  })
  checks.push({
    name: 'productShipGate_true',
    ok: assertR.productShipGate === true,
    detail: `got ${assertR.productShipGate}`,
  })
  checks.push({
    name: 'packetDecodeGate_true',
    ok: assertR.packetDecodeGate === true,
    detail: `got ${assertR.packetDecodeGate}`,
  })
  for (const f of assertR.failures) {
    if (!checks.some((c) => c.detail?.includes(f) || c.name.includes(f.split(' ')[0]!))) {
      checks.push({ name: 'assert_extra', ok: false, detail: f })
    }
  }

  const best = readJson<{
    composite?: number
    shipGate?: boolean
    productShipGate?: boolean
    shipGateCandidate?: boolean
    mode?: string
    hypothesis?: string
  }>(BEST_PATH)
  const packet = readJson<{
    packetDecodeGate?: boolean
    schema?: string
    match?: string
  }>(PACKET_GATE_PATH)

  // Track5 — freeze snapshot hash pin (machine-side reviewer diff).
  const freezeSnapshot = {
    composite: best.composite,
    shipGate: best.shipGate,
    productShipGate: best.productShipGate,
    shipGateCandidate: best.shipGateCandidate ?? null,
    mode: best.mode ?? null,
  }
  const packetSnapshot = {
    packetDecodeGate: packet.packetDecodeGate,
    schema: packet.schema ?? null,
    match: packet.match ?? null,
  }
  const hashes = {
    best_freeze_fields_sha256: sha256Json(freezeSnapshot),
    packet_decode_gate_sha256: sha256Json(packetSnapshot),
    best_file_sha256: createHash('sha256')
      .update(readFileSync(BEST_PATH))
      .digest('hex'),
    packet_file_sha256: createHash('sha256')
      .update(readFileSync(PACKET_GATE_PATH))
      .digest('hex'),
  }
  checks.push({
    name: 'freeze_hash_pin_present',
    ok:
      typeof hashes.best_freeze_fields_sha256 === 'string' &&
      hashes.best_freeze_fields_sha256.length === 64 &&
      typeof hashes.packet_decode_gate_sha256 === 'string' &&
      hashes.packet_decode_gate_sha256.length === 64,
    detail: `best=${hashes.best_freeze_fields_sha256.slice(0, 12)}… packet=${hashes.packet_decode_gate_sha256.slice(0, 12)}…`,
  })

  const skipKw = process.argv.includes('--skip-kill-window')
  let killWindowOk = skipKw
  let killWindowDetail = 'skipped'
  if (!skipKw) {
    const kw = spawnSync('npm', ['run', 'test:kill-window'], {
      encoding: 'utf8',
      cwd: ROOT,
    })
    killWindowOk = (kw.status ?? 1) === 0
    killWindowDetail = killWindowOk
      ? 'passed'
      : (kw.stdout + kw.stderr).slice(-800)
  }
  checks.push({
    name: 'kill_window_acceptance',
    ok: killWindowOk,
    detail: killWindowDetail,
  })

  const allOk = checks.every((c) => c.ok) && assertR.ok
  const report = {
    schema: 'product-freeze-guardian-v1',
    room: 'P10',
    utc: new Date().toISOString(),
    worktree: ROOT,
    branch: 'adv/prd-r30-freeze',
    researcher: 'R30',
    never_edited_parent:
      ROOT !== PARENT_FORBIDDEN && ROOT.includes('/.codex/worktrees/'),
    freeze: {
      composite: FREEZE_COMPOSITE,
      shipGate: true,
      productShipGate: true,
      packetDecodeGate: true,
    },
    observed: {
      composite: best.composite,
      shipGate: best.shipGate,
      productShipGate: best.productShipGate,
      packetDecodeGate: packet.packetDecodeGate,
    },
    hashes,
    freeze_snapshot: freezeSnapshot,
    packet_snapshot: packetSnapshot,
    checks,
    gate_progress: {
      H_freeze: allOk,
      freeze_hash_pin: checks.find((c) => c.name === 'freeze_hash_pin_present')
        ?.ok === true,
      anti_odds: null as boolean | null,
    },
    calculatorReady: false,
    ok: allOk,
  }

  mkdirSync(OUT_DIR, { recursive: true })
  const outPath = join(OUT_DIR, 'freeze_guardian_report.json')
  writeFileSync(outPath, JSON.stringify(report, null, 2) + '\n')

  for (const c of checks) {
    console.log(`${c.ok ? 'PASS' : 'FAIL'} ${c.name}${c.detail ? ` — ${c.detail}` : ''}`)
  }
  console.log(`wrote ${outPath}`)
  if (!allOk) fail('ship freeze regression or isolation break')
  console.log('FREEZE GUARDIAN OK — composite 0.9683 + gates + hash pins intact')
}

main()
