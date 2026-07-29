# R10 — planner-lethal (F4)

**Branch:** `adv/fo-r10-planner-lethal`  
**Worktree:** `~/.codex/worktrees/rofl-fo-r10`  
**never_edited_parent:** true (docs mirrored to parent `fight_outcome/r10/` only)  
**Unfreeze 0.9683:** authorized — no `best.json` rewrite (S1 regress)

## Auto-picked (rooms/f4/HYPOTHESES.md)

1. Death-coupled truncate  
2. No HP% ability bans  
3. Utility-only keep  
4. Front-loaded scoring  
5. Engage t=0  
6. Parity with Send  

## What ran

13 experiments. Harness knob: `--sim-mode short|allin|extended` on continuous/gated `simulateMatchup` (death-coupled `timed_manual_1v1`). Scorer: `fight_agreement_from_eval.ts`. Metric = **fightAgreement ≠ odds**.

| id | mode | sim | FA (S0) | Δe0 |
|----|------|-----|--------:|----:|
| e0 | gate_action cusum | — | 0.4848 | 0 |
| **e5** | **cusum_gate** | **allin** | **0.5019** | **+0.017** |
| e4 | cusum_gate | short | 0.4985 | +0.014 |
| e1/e9/e10 | cusum_gate | extended/allin | ≤0.5019 | ≤+0.017 |
| e2/e6/e7 | gate_repin | * | ~0.28 | −0.20 |
| e3/e8 | baseline | * | ≤0.21 | −0.27 |

Holdout S1 (no tune): timed allin **0.2822** vs mark overlay **0.5185**.

## Verdict

- Keepable research artifact: `--sim-mode` + sweep under `r10/`.  
- **No product KEEP** — S1 timed loses; S0 passRate still 0; Camille→Leona c1 still misses lethal on planner.  
- vs R04 product FA 0.4217: e5 **+0.080**; still ≪ 0.95.

## Next for orchestrator

Hybrid: keep CUSUM engage gate + death-coupled timed finish for lethalHit, retain mark pulses for actionF1 / Camille c1 — do not flip product selectors on S0 alone.
