# R18 NOTES — path1-lethal

**Branch:** `adv/fo-r18-path1-lethal`  
**Worktree:** `~/.codex/worktrees/rofl-fo-r18`  
**never_edited_parent:** true (docs mirrored to parent `fight_outcome/r18/` only)  
**Unfreeze 0.9683:** authorized — no `best.json` product rewrite (S1 regress)

## Path1 FA (product selector cusum_engage_then_skills)

| | FA | pass |
|--|---:|-----:|
| **before (e0 / R05)** | **0.2279** | 0 |
| **after best research (e11)** | **0.2414** | 0 |
| product defaults after | **0.2279** (unchanged) | 0 |

Δ research = **+0.0134**. No product KEEP.

## What moved

- **e11** (`--no-aa-at-mark` + keep finish-aa): Olaf→Trundle |lethErr| 2.81→**1.14**; check02 burst ship A2 passes; pathBand up on c2 full.
- Pure timed planner (cusum_gate allin/short/extended) **hurts** Path1 FA (~0.199) — loses Olaf kills; Galio still no model kill.
- Galio→Trundle: still `modelKilled=false` on all candidates.
- Olaf→Camille full: still |lethErr|~18s (earlyPoisoned).

## S1 holdout (2970137, no tune)

| config | FA |
|--------|---:|
| product e0 | **0.5185** |
| e11 research | 0.3961 |
| e8 research | 0.3775 |

S1 regress → **do not flip** product aa-at-mark / finish-aa defaults.

## Keepable harness (not product)

- `scripts/crosscheck_action_aligned.ts --sim-mode short|allin|extended`
- `--suite 2970132-g1` → `docs/canvases/_data/crosschecks-2970132-g1.json`
- `scripts/r18_path1_lethal_sweep.sh`
- `scripts/fight_agreement_suite.ts` S0 wire → Path1 primary file

## Confidence

fightAgreement = kill-window suite agreement — **NOT** win odds / pBlue-pRed %.
