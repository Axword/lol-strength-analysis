# R17 NOTES — calc-send / Criterion G

**utc:** 2026-07-24T15:54:36Z  
**worktree only:** `~/.codex/worktrees/rofl-fo-r17` · branch `adv/fo-r17-calc-send`  
**never_edited_parent (code):** true — research docs mirrored to parent `fight_outcome/r17/` by mandate  

## Verdict

Criterion G scaffolding **PROVEN** for V8:

1. Calculator Send kill-window path (`simulateKillWindowMatchup`) shares math with harness (`simulateKillWindowSeries`) on post-select marks — endHp bitwise-agree on E1/E2.
2. Dead excluded from Send import (`buildLivingSendImport`).
3. Known-flags fail-closed; sparse combat blocks Send.
4. One Final smoke: `npm run fo:send-smoke`.
5. No odds % copy on product UI.

**fightOutcomeGate remains false** — S0 Path1 FA still 0.228 (R05). R17 does not claim FA lift.

## Smoke (Final parent e2e step 3)

```bash
cd ~/.codex/worktrees/rofl-fo-r17
npm run fo:send-smoke
```

Expected: `8 pass / 0 fail`, writes `send_parity_smoke.json`.

## Supporting suite (all green this run)

| Command | Result |
|---------|--------|
| `npm run fo:send-smoke` | 8/8 |
| `npm run test:known-flags` | E1–E8 ok |
| `npm run test:send-gate` | E1–E10 ok |
| `npm run test:track3-send-parity` | 9/9 |
| `npm run test:kill-window` | 20 passed |
| `npm run test:anti-odds` | ANTI-ODDS AUDIT OK |
| `npx tsx src/components/__tests__/partialC.sendHonesty.2970132.test.tsx` | E1–E10 ok |

## Contract detail (E1)

`simulateKillWindowMatchup` runs `selectKillWindowMarks` then `simulateKillWindowSeries`.  
Harness parity requires feeding **post-select** marks into series — raw marks + density inside series alone is a different path (documented trap; not invent).

## Residual for V8 / next mega-cycle

- Map `sendFight` still ships continuous pins (no auto-attach of timeline skill marks). Overlay parity is proven for the Calculator path when `killWindow.actionMarks` are attached (product opt-in / research attach). Do not invent marks to raise FA.
- S0 FA 0.228 / R10 timed proxy 0.5019 with S1 regression — F3/F4, not F6.
