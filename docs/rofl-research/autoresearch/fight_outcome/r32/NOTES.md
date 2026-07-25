# R32 NOTES — check03-share (wave2)

**Branch:** `adv/fo-r32-check03-share`  
**Worktree:** `/Users/river/.codex/worktrees/rofl-fo-r32`  
**never_edited_parent:** true (code); docs mirrored to parent `fight_outcome/r32/`  
**FA ≠ odds**

## Next action

Orchestrator: **PARENT_MERGE** product `killerShareMode=residual_hp` (engine + `killWindowProduct` defaults).

## Mandate

R26 assist-gated share=0.20 cleared Path1 c3 earlyMae but S1 regress (allyMin one-coeff). Find attribution that lifts c3 without global/assist share colliding S1.

## Root cause (reconfirmed)

Path1 c3 Olaf→Camille: probe lethal ~1.73s vs actual death ~20.7s (`earlyBy≈18.97s`). Actual drop at lethal ref ≈259 HP vs modelDump 1308 → residual share ≈0.198 (matches R26 skill-count proxy 0.20). Mechanism = opener 1v1 full-share overkill in teamfight — not idle.

S1 c2 Cass→Viktor: `earlyBy≈0.84s` ≪ 8s gate → residual **does not apply** → lethals preserved.

## Experiments

| id | change | c3 earlyMae | poison | S0 FA | S1 FA |
|----|--------|------------:|:------:|------:|------:|
| e0b | share=none (R30) | 476 | Y | 0.5938 | 0.5620 |
| **e5** | **residual_hp (product)** | **100.4** | **N** | **0.7307** | **0.5620** |
| e2 | residual opener-pad=3 | 100.4 | Y | — | — |
| e3 | assist_gated 0.20 | ~100 | N | 0.7309 | **0.3595** |

## KEEP decision

**PRODUCT KEEP** — S0 FA +0.1369; S1 FA flat (0.0000Δ).

| | e0b | e5 | Δ |
|--|---:|---:|--:|
| check03 earlyMae | 476 | 100.42 | **−375.58** |
| S0 FA | 0.5938 | 0.7307 | **+0.1369** |
| S1 FA | 0.5620 | 0.5620 | **0.0000** |

## Code (worktree only)

- `src/engine/killWindowOverlay.ts`: `attributeResidualHpShare`, `killerShareMode`, aaAtEachMark×share
- `src/engine/killWindowProduct.ts`: default `killerShareMode=residual_hp`
- `src/engine/types.ts`: KillWindowInputOptions share fields
- `scripts/crosscheck_action_aligned.ts`: CLI + assist_gated ablation

## Residual

c3 earlyMae 100 still >50 earlyBand hard cap (windowOk early still fails) — path/lethal lift only. Galio miss-kill / pathMae remain other rooms. fightOutcomeGate still false (FA≪0.95).

## Repro

```bash
npx --yes tsx scripts/crosscheck_action_aligned.ts \
  --suite 2970132-g1-holdout \
  --mark-selection cusum_engage_then_skills \
  --dense-window 1.0 --dense-max 1 --mark-min-gap 0.4 \
  --mode gate_action \
  --out docs/rofl-research/autoresearch/fight_outcome/r32/experiments/e5_product_keep_residual.json
```
