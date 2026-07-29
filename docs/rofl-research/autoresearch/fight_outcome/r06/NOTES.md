# R06 — metric-suites (F2.H5)

**Branch:** `adv/fo-r06-metric-suites`  
**Worktree:** `~/.codex/worktrees/rofl-fo-r06`  
**never_edited_parent:** true

## Done
1. Wired S1: `2970137-g1-holdout` + `2970120-g1-holdout` into `scripts/fight_agreement_suite.ts`.
2. Wired S2: unused pro slim `2954868-g1` (+ transfer extract).
3. Disclosed Camille/PE structural hole (`camille_pe_holes.json`).
4. Measure-only on S1/S2 with product non-drop `cusum_engage_then_skills` — **no tune on S1**.

## Suite status (measure)
| Suite | Wired | fightAgreement | fightPassRate | Gate |
|-------|-------|----------------|---------------|------|
| S1 | yes | 0.478 | 0.333 | fail (≥0.95) |
| S2 | yes | 0.634 | 0.333 | fail (≥0.90) |

## Commands
```bash
npx --yes tsx scripts/fight_agreement_suite.ts --mode wire
npx --yes tsx scripts/fight_agreement_suite.ts --mode measure --suites S1,S2
```

## Honesty
fightAgreement ≠ win odds. Camille PE invent refused.
