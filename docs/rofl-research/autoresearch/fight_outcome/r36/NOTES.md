# R36 NOTES — ally-attrib

**Branch:** `adv/fo-r36-ally-attrib`  
**Worktree:** `/Users/river/.codex/worktrees/rofl-fo-r36`  
**never_edited_parent:** true (code); docs mirrored to parent `fight_outcome/r36/`  
**FA ≠ odds**

## Next action

Orchestrator PARENT_MERGE KEEP defaults (`openerAllyAttrib=local_skill_share`, allyMin=5, killerMin=1, full-window gate).

## Mandate

Teamfight opener overkill (check03): packet/timeline ally damage attribution — **not** global share. Prefer same-match `skill_used` allyMarks with disclosed shares. No invent HP/combat. KEEP only if S0↑ and S1 flat+.

## Root cause (from R26 + remeasure)

- Not idle / not false_all_in.
- Olaf→Camille full: early 5s killerSkills=2 allySkills=8; model full-share 1v1 → earlyPoisoned + lethErr≈−18s.
- Slim SQLite has `skill_used` (no `damage_dealt`) → skill_used local share is the honest attribution available without invent.

## KEEP recipe (e7/e8)

```
openerAllyAttrib: local_skill_share
openerAllyWindowSec: 5
openerAllyLocalSec: 2
openerAllyMin: 5
openerKillerMin: 1
# gate uses check.windowMs[0] (full), never burst-shifted start
# allyMarks disclosed logOnly only when activated
```

Per-mark share = killer/(killer+ally) skill_used counts in ±2s of the mark. Finish marks with no local allies keep share=1.

## Metrics

| | e0 | e7 KEEP | Δ |
|--|---:|---:|--:|
| c3 earlyMae | 476 | 89.5 | −386.5 |
| c3 earlyPoisoned | Y | N | cleared |
| c3 lethErr | −18.27 | 0.00 | fixed |
| S0 FA | 0.5938 | **0.7217** | **+0.1279** |
| S0 pass | 0.333 | 0.333 | flat |
| S1 FA | 0.5620 | **0.5620** | **0.000** |
| S1 pass | 0.333 | 0.333 | flat |

fightAgreement = kill-window suite agreement — **NOT** calibrated win odds.

## Why not R26 global share

R26 `killerPulseShare=0.20` + `assistAllyMin=5` lifted S0 but **regressed S1** (Cass windows also hit allyMin). Local per-mark shares + killerMin=1 skip late-join killers (Cass opener has 0 killer skills).

## Repro

```bash
npx --yes tsx scripts/crosscheck_action_aligned.ts \
  --suite 2970132-g1-holdout \
  --mark-selection cusum_engage_then_skills \
  --dense-window 1.0 --dense-max 1 --mark-min-gap 0.4 \
  --out docs/rofl-research/autoresearch/fight_outcome/r36/experiments/e8_default_keep_smoke.json

npx --yes tsx scripts/fight_agreement_suite.ts \
  --from-eval docs/rofl-research/autoresearch/fight_outcome/r36/experiments/e7_local_fullgate.json \
  --suite-label S0 --out-dir docs/rofl-research/autoresearch/fight_outcome/r36/experiments
```

## Files

- `scripts/lib/opener_ally_attrib.ts` (new)
- `scripts/crosscheck_action_aligned.ts` (wire + KEEP defaults)
- `src/engine/killWindowProduct.ts` (`skillMarksFromTimeline` R36 attrib)
- `src/engine/types.ts` (`logOnly` on marks)
