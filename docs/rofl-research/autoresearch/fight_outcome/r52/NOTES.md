# R52 NOTES — olaf-kit-dump-honesty

**Branch:** `adv/fo-r52-olaf-kit-dump-honesty`  
**Worktree:** `/Users/river/.codex/worktrees/rofl-fo-r52`  
**never_edited_parent_code:** true (docs mirrored OK)  
**Product KEEP:** **YES** (e21)  
**FA ≠ odds / pBlue%**

## Next action

Orchestrator PARENT_MERGE product defaults in `killWindowProduct.ts` + harness EXPERIMENT (Olaf→Trundle Q+E + aaWeave3). No pathFollow.

## Mandate

Diagnose Olaf kit-dump cliff; honest slot packets without FA regress / without pathFollow. KEEP iff S0 FA↑ and S1 flat+.

## Diagnosis (extends R40 floor ~101)

1. Kit dump (`simulateMatchup` pulse) one-shots at any pulseSec in (0,1] — softens are dead.
2. Global / Olaf-only slot+weave recovers c2 lethOk and can beat R40 floor (best **97.5** via Q+E+aa3) but **Camille c3 early-lethal** (|leth|≈8.8–10) → S0 FA 0.9304→~0.85.
3. Same early-lethal cliff as R40 once lethErr snaps to −0.33 on c2: residual MAE is post-overkill 0-vs-truth until kill.
4. **Victim scope Trundle** keeps Camille on kit-dump → c3 unchanged; c2 pathBand 0.76→0.917 → S0 FA↑; S1 bit-flat (no Olaf/Trundle hosts).
5. pathFollow not used for KEEP (R33/R40 S1 regress lesson).

## Baselines (compound remesaure)

| Suite | FA | pass | c2_burst mae | pathOk |
|-------|---:|-----:|-------------:|:------:|
| S0 e0 kit-dump | **0.9304** | 0.667 | **111.6** | false |
| S1 e0 | **0.7628** | 0.500 | — | — |

## Experiment highlights (≥8; 30+ evals)

| Exp | Idea | c2 mae | c3 leth | S0 FA | S1 FA | Note |
|-----|------|-------:|--------:|------:|------:|------|
| e0 | kit dump | 111.6 | 0 | 0.9304 | 0.7628 | reference |
| e1 | global slot binary | 462.6 | miss | — | — | underkill |
| e2 | global slot+aa4 | 102.0 | −10.1 | **0.784** | — | FA↓ |
| e13 | Olaf QE+aa3 | **97.5** | −8.8 | **0.848** | 0.7628 | mae best; c3 cliff |
| e21 | Olaf→Trundle QE+aa3 | **97.5** | 0 | **0.9356** | **0.7628** | **KEEP** |
| e23 | Trundle aa4 blend0.1 | 101.1 | 0 | 0.9343 | — | R40 floor; weaker FA |

## KEEP recipe (e21)

```
slotScopedPulse      = true
slotScopedChampionIds = ['Olaf']
slotScopedVictimIds   = ['Trundle']
slotScopedSlots       = [1, 3]   # Q+E
slotScopedAaWeave     = 3
slotKitBlend          = 0
pathFollow            = false
```

## Metrics (KEEP remesaure)

| | e0 | e21 KEEP | Δ |
|--|---:|---:|--:|
| S0 FA | 0.9304 | **0.9356** | +0.0052 |
| S0 pass | 0.667 | 0.667 | 0 |
| S1 FA | 0.7628 | 0.7628 | 0 (bit) |
| S1 pass | 0.500 | 0.500 | 0 |
| c2_burst mae | 111.6 | **97.5** | −14.1 |
| c2_burst pathOk | false | false | still >90 |

## Residual

- c2 pathMae 97.5 ≪90 still fails pathOk / windowOk; passRate unchanged 0.667.
- fightOutcomeGate false. FA ≠ odds.
- Global slot packets remain research-only (Camille cliff).

## Reproduce

```bash
cd /Users/river/.codex/worktrees/rofl-fo-r52
npx --yes tsx scripts/crosscheck_action_aligned.ts \
  --suite 2970132-g1-holdout --mode gate_action \
  --mark-selection cusum_engage_then_skills \
  --dense-window 1.0 --dense-max 1 --mark-min-gap 0.4 \
  --out docs/rofl-research/autoresearch/fight_outcome/r52/experiments/e21_keep_default_remeasure.json
npm run fight:agreement -- --suite-label S0 \
  --from-eval docs/rofl-research/autoresearch/fight_outcome/r52/experiments/e21_keep_default_remeasure.json \
  --out-dir docs/rofl-research/autoresearch/fight_outcome/r52/experiments/fa_e21_keep_S0
```

## Digest

Untouched. digestCleanGate not regressed.
