# R20 — holdout-s1 (F7)

**Branch:** `adv/fo-r20-holdout-s1`  
**Worktree:** `~/.codex/worktrees/rofl-fo-r20`  
**never_edited_parent:** true (docs dual-write to parent `fight_outcome/r20/` only)

## Mandate
Measure/disclose S1 holdout freeze. No invent. No S1 tune.

## Commands
```bash
# R06-protocol measure (primary freeze)
npx --yes tsx scripts/crosscheck_action_aligned.ts --suite 2970137-g1-holdout \
  --out docs/rofl-research/autoresearch/fight_outcome/r20/evals/S1-2970137-g1.r06proto.eval.json \
  --mark-selection cusum_engage_then_skills --mark-min-gap 0.4 --no-action-replay-audit
npx --yes tsx scripts/crosscheck_action_aligned.ts --suite 2970120-g1-holdout \
  --out docs/rofl-research/autoresearch/fight_outcome/r20/evals/S1-2970120-g1.r06proto.eval.json \
  --mark-selection cusum_engage_then_skills --mark-min-gap 0.4 --no-action-replay-audit
```

## Result
S1 freeze FA ≈0.411 / pass ≈0.167 under current LETHAL_TOL=0.75. Gate false.
