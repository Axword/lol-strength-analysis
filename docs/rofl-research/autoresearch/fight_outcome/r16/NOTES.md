# R16 — calc-parity (F6)

**Branch:** `adv/fo-r16-calc-parity`  
**Worktree:** `/Users/river/.codex/worktrees/rofl-fo-r16`  
**never_edited_parent:** true  
**utc:** 2026-07-24T15:54:15Z

## Auto-picked (rooms/f6/HYPOTHESES.md)

1. Send→overlay parity
2. Dead excluded
3. Smoke command
4. Partial C honesty (fail-closed known-flags)
5. No odds copy

## Prove

Calculator Send (when `killWindow.actionMarks` attached) calls `simulateKillWindowMatchup` → same `simulateKillWindowSeries` math the harness uses. Identical endHp + firstLethalSec on same pins.

## Final smoke

```bash
cd /Users/river/.codex/worktrees/rofl-fo-r16
npm run smoke:calc-parity
# alias: npm run fo:r16-calc-parity
```

Expected: `R16 calc-parity smoke: 11/11 PASS`

Also green: `npm run test:kill-window` (20 passed).

## Context (not raised)

S0 Path1 product FA **0.228** (R05) — parity does **not** improve fightAgreement; Criterion G evidence only.

## KEEP artifact

- `src/engine/killWindowOverlay.ts` + `killWindowProduct.ts` (shared math)
- `src/components/Calculator.tsx` routes marks → `simulateKillWindowMatchup`
- Fail-closed `hpIsKnown` / `combatStatsAreKnown` / `abilityRanksAreKnown`
- Living-only Send helpers (`buildLivingSendImport`, dead excluded)
- `scripts/fo_r16_calc_parity_smoke.ts` + `npm run smoke:calc-parity`
