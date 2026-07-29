# R24 NOTES — galio-kill

**Branch:** `adv/fo-r24-galio-kill`  
**Worktree:** `~/.codex/worktrees/rofl-fo-r24`  
**never_edited_parent:** true (docs mirrored to parent `fight_outcome/r24/` only)  
**FA ≠ odds**

## Path1 FA (product selector cusum_engage_then_skills)

| | FA | Galio full kill | Galio \|lethErr\| | c1 lethalHit |
|--|---:|:---:|---:|:---:|
| **before (e0 / R05)** | **0.2279** | N | null | 0 |
| **after best research (e49)** | **0.5030** | Y | **0.356** | **1** |
| product defaults after | **0.2279** (unchanged) | N | null | 0 |

Δ research = **+0.275**. No product KEEP.

## What moved

- Root cause: product density+CUSUM kept only E@16.36 + finish Q@18.16; W@15.024 discarded → endHp≈306.
- **e49** (`lead0.4 + far5 + farShare0.45 + maxKillerMarks4`, no aa-filler): Galio full model kill with lethErr=−0.356 → lethalHit under LETHAL_TOL=0.75; Path1 FA 0.503.
- **e43** (same + aa-filler, farShare0.35): also Galio lethalHit; FA 0.464.
- Burst Galio still no kill: `detectBurstStartMs` → 502021, after all Galio `skill_used`.

## S1 holdout (2970137, no tune)

| config | FA |
|--------|---:|
| product e0 | **0.5185** |
| e49 research | 0.3379 |
| lead0.4 only | 0.3740 |

S1 regress → **do not flip** product `killWindowProduct` / aa / density defaults.

## Keepable harness (not product)

- Suite wire: `--suite 2970132-g1` → `crosschecks-2970132-g1.json`
- Knobs: `--pre-engage-lead`, `--pre-engage-far`, `--pre-engage-far-share`, `--max-killer-marks`
- Engine: `markPreEngageLeadSec` / `FarSec` / `FarShare` in `selectKillWindowMarks` + pre-engage poke path in `simulateKillWindowSeries`
- Scorer: `scripts/fight_agreement_suite.ts --from-eval`

## Confidence

fightAgreement = kill-window suite agreement — **NOT** win odds / pBlue-pRed %.
