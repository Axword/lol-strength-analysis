# R51 NOTES — c1-burst-f1

**Branch:** `adv/fo-r51-c1-burst-f1`  
**Worktree:** `/Users/river/.codex/worktrees/rofl-fo-r51`  
**never_edited_parent_code:** true (docs mirrored OK)  
**Product KEEP:** **YES** — `sameTSecSkillCohort: true`  
**FA ≠ odds / pBlue%**

## Next action

Orchestrator: **PARENT_MERGE** product `sameTSecSkillCohort=true` (+ harness `--same-tsec-cohort` / default on). Secondary actionCoverage only — not fightOutcomeGate.

## Mandate

Honest c1-burst actionCoverage F1 0.667→↑ (no zero-dmg echo). Secondary only. KEEP iff S0 FA↑ and S1 flat+.

## Root cause (post R44)

1. R31+R42 remaps Galio E+Q onto CUSUM+0.3s → both marks at `tSec=1.302`, both kept (`finish_window`).
2. R44 truth-domain remaps the same two skills → truth=2.
3. Simulator processed marks **sequentially** and `if (hp <= 0) break` after lethal E → **Q never emitted** → model=1 → F1=0.667.
4. Not a density drop (marks already 2). Not missing slim events.

## KEEP recipe (E1)

```
sameTSecSkillCohort = true
# same-tSec killer skills: pulse from shared HP baseline, emit all modelActions,
# then apply summed damage once. Death-coupled across cohorts unchanged.
# Never shareHint=0 echo.
```

| Metric | e0b sequential | e1 KEEP | Δ |
|--|---:|---:|--:|
| S0 c1-burst F1 | 0.667 | **1.000** | +0.333 |
| S0 c1-burst truth/model/matched | 2/1/1 | **2/2/2** | |
| S0 FA | 0.9304 | **0.9387** | **+0.0083** |
| S0 pass | 0.667 | 0.667 | 0 |
| S1 FA | 0.7628 | **0.7628** | 0 |
| S1 pass | 0.500 | 0.500 | 0 |
| c1-burst mae/early/leth | 0 / 0 / −0.335 | unchanged | |

FA lift ≈ 0.15 × 0.333 / 6 — secondary actionF1 term only. Lethal/path unchanged on c1-burst.

## Echo control (E7)

Honest sequential F1=0.667. Zero-dmg `shareHint=0` pad → raw F1=1.0 → **REJECT** (forbid #13). Not fightOutcomeGate / actionReplayGate evidence.

## Experiments (n=10)

| Exp | Hypothesis | c1 F1 | S0 FA | Keep? |
|-----|------------|------:|------:|:-----:|
| e0b | sequential baseline | 0.667 | 0.9304 | no |
| **e1** | **same-tSec cohort dump** | **1.000** | **0.9387** | **yes** |
| e2 | dense-max 2 | 0.667 | 0.9304 | no |
| e3 | pre-burst share 0.5 | 0.800 | 0.8671 | no (FA↓ pass↓) |
| e4 | delay 0 | 0.667 | 0.9164 | no |
| e5 | lead 0 | 0.000 | 0.8137 | no |
| e6 | truth burst-window only | 0.000 | 0.9137 | no |
| e7 | zero-dmg echo pad | 1.000 raw | — | **REJECT** |
| e8 | cohort + share 0.7 | 1.000 | 0.9387 | redundant |
| e9 | Q-before-E slot order | 0.667 | 0.9304 | no (Q alone lethal) |

## Residual

- actionReplayGate still false (other windows F1≪0.95; c3-burst F1=0.333).
- fightOutcomeGate false. FA ≪ 0.95 as calibrated-odds claim (FA ≠ odds).
- c2_burst maeHp 111.6 still pathOk false (R40 floor).

## Reproduce

```bash
cd /Users/river/.codex/worktrees/rofl-fo-r51
npx --yes tsx scripts/crosscheck_action_aligned.ts \
  --suite 2970132-g1-holdout --mode gate_action \
  --mark-selection cusum_engage_then_skills \
  --dense-window 1.0 --dense-max 1 --mark-min-gap 0.4 \
  --same-tsec-cohort \
  --out docs/rofl-research/autoresearch/fight_outcome/r51/experiments/e1_cohort.json
npx --yes tsx scripts/fight_agreement_suite.ts \
  --from-eval docs/rofl-research/autoresearch/fight_outcome/r51/experiments/e1_cohort.json \
  --suite-label S0 --out-dir docs/rofl-research/autoresearch/fight_outcome/r51/experiments/fa_e1_cohort_S0
```
