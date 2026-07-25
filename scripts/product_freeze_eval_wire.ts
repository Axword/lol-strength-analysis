/**
 * P10 Track2 — freezeEvalWire.
 *
 * Hook for scripts that write best.json / last_eval*.json:
 * call requireProductFreeze() (or this CLI) before KEEP.
 * Assert-only; never rewrites freeze upward.
 *
 * Dry-run: --probe-drift temporarily mutates composite, expects FAIL, restores.
 */
import { copyFileSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { join, resolve } from 'node:path'
import {
  assertProductFreeze,
  FREEZE_COMPOSITE,
  requireProductFreeze,
} from './lib/productFreezeAssert'

const ROOT = resolve(process.cwd())
const BEST = join(ROOT, 'docs/rofl-research/autoresearch/best.json')
const OUT_DIR = join(
  ROOT,
  'docs/rofl-research/autoresearch/product_ready/rooms/P10',
)

function main(): void {
  const probe = process.argv.includes('--probe-drift')
  mkdirSync(OUT_DIR, { recursive: true })

  if (!probe) {
    const r = assertProductFreeze(ROOT)
    const report = {
      schema: 'product-freeze-eval-wire-v1',
      researcher: 'R30',
      track: 'freezeEvalWire',
      utc: new Date().toISOString(),
      worktree: ROOT,
      branch: 'adv/prd-r30-freeze',
      never_edited_parent: r.never_edited_parent,
      mode: 'assert',
      freeze: {
        composite: FREEZE_COMPOSITE,
        shipGate: true,
        productShipGate: true,
        packetDecodeGate: true,
      },
      result: r,
      hook: {
        module: 'scripts/lib/productFreezeAssert.ts',
        keep_writer_call: 'requireProductFreeze()',
        kill_window_writer:
          'scripts/crosscheck_action_aligned.ts asserts before last_eval/KEEP write',
        npm: 'npm run test:freeze-eval-wire',
      },
      calculatorReady: false,
      ok: r.ok,
    }
    const out = join(OUT_DIR, 'freeze_eval_wire_report.json')
    writeFileSync(out, JSON.stringify(report, null, 2) + '\n')
    console.log(r.ok ? 'PASS freezeEvalWire assert' : 'FAIL freezeEvalWire assert')
    for (const f of r.failures) console.log(`  - ${f}`)
    console.log(`wrote ${out}`)
    if (!r.ok) process.exit(1)
    requireProductFreeze(ROOT)
    console.log('FREEZE EVAL WIRE OK — KEEP writers may call requireProductFreeze()')
    return
  }

  // Adversarial: drift composite away from pin → must FAIL; restore → green.
  const backup = `${BEST}.r30-probe.bak`
  copyFileSync(BEST, backup)
  let driftFailed = false
  let restoreOk = false
  let writerRefused = false
  try {
    const best = JSON.parse(readFileSync(BEST, 'utf8')) as { composite: number }
    best.composite = 0.9999
    writeFileSync(BEST, JSON.stringify(best, null, 2) + '\n')
    const drifted = assertProductFreeze(ROOT)
    driftFailed = !drifted.ok
    // Simulate kill-window KEEP writer refusal path.
    try {
      requireProductFreeze(ROOT)
    } catch {
      writerRefused = true
    }
    copyFileSync(backup, BEST)
    restoreOk = assertProductFreeze(ROOT).ok
  } finally {
    try {
      copyFileSync(backup, BEST)
    } catch {
      /* restore best-effort */
    }
  }

  const ok = driftFailed && restoreOk && writerRefused
  const report = {
    schema: 'product-freeze-eval-wire-v1',
    researcher: 'R30',
    track: 'freezeEvalWire',
    utc: new Date().toISOString(),
    worktree: ROOT,
    branch: 'adv/prd-r30-freeze',
    never_edited_parent: true,
    mode: 'probe-drift',
    drift_failed_as_expected: driftFailed,
    writer_refused_as_expected: writerRefused,
    restore_ok: restoreOk,
    calculatorReady: false,
    ok,
  }
  const out = join(OUT_DIR, 'freeze_eval_wire_probe.json')
  writeFileSync(out, JSON.stringify(report, null, 2) + '\n')
  console.log(
    `probe-drift: drift_fail=${driftFailed} restore_ok=${restoreOk} → ${ok ? 'PASS' : 'FAIL'}`,
  )
  console.log(`wrote ${out}`)
  if (!ok) process.exit(1)
}

main()
