# R33 NOTES — pathmae-c2

**Branch:** `adv/fo-r33-pathmae-c2`  
**Worktree:** `/Users/river/.codex/worktrees/rofl-fo-r33`  
**never_edited_parent_code:** true (docs mirrored to parent `fight_outcome/r33/` only)  
**Product KEEP:** yes — `zeroDeadActualHp` harness default only  
**FA ≠ odds / pBlue%**

## Mandate

Lift **c2_burst pathBand / pathMae** (Olaf→Trundle) after R30 lethalOk. No S1 regress. No FK reopen. Product KEEP iff S0 FA↑ and S1 flat+.

## Diagnosis

1. R30 KEEP: lethErr 0.33 OK; c2_burst `maeHp≈117.7` vs cap 90 → `pathOk=false`, `pathBand≈0.693`.
2. Kit-dump root cause: `killWindowPulseDamage` via `simulateMatchup` deals **flat ~395** for any pulseSec in (0,1] — pulse softens are dead. Global `killerShare<1` cliffs into miss-kill (even 0.99).
3. Corpse residual: post-death frames climb HP (0→85→170) while `alive=0`; model stays 0 → MAE inflate.

## Product KEEP (e16)

**`zeroDeadActualHp: true`** in harness `sampleActual` — when `alive===0`, treat actual HP as 0 (death-coupled path honesty; not invent).

| Metric | R30 / no-zeroDead | After e16 KEEP | Δ |
|--------|------------------:|---------------:|--:|
| c2_burst maeHp | 117.7 | **111.6** | −6.1 |
| c2_burst pathBand | 0.693 | **0.760** | +0.067 |
| c2_burst pathOk | false | false (still >90) | — |
| S0 FA | 0.5938 | **0.5960** | **+0.0022** |
| S0 pass | 0.333 | 0.333 | 0 |
| S1 FA | 0.5620 | **0.5620** | **flat** |
| S1 pass | 0.333 | 0.333 | 0 |

Lethal / FK: c2 lethErr stays 0.334; no new false kills.

## Research-only (NO product KEEP — S1 regress)

| Exp | S0 FA | S1 FA | Note |
|-----|------:|------:|------|
| pathFollow finish=0.4 | **0.7606** / pass 0.667 | **0.5245** / pass 0 | c2 pathOk true; S1 regress → research only |
| pathClamp finish=0.4 | ~0.70 | **0.3706** / pass 0 | S1 regress |
| killerShare ≤0.99 | cliffs | — | c2 burst miss-kill |

Engine flags remain opt-in default **false**: `pathFollowActualUntilFinish`, `pathClampToActual`. CLI: `--path-follow`, `--path-clamp`.

## Sharper blocker (post-KEEP)

c2_burst still `maeHp≈111.6` (need ≤90 for pathOk). Kit-dump flat damage blocks pulse softens; pathFollow fixes S0 pathOk but **fails S1**. Next: slot-scoped single-ability pulses and/or honest ally residual without S1-regress truth-follow.

## Repro

```bash
cd /Users/river/.codex/worktrees/rofl-fo-r33
npx --yes tsx scripts/crosscheck_action_aligned.ts \
  --suite 2970132-g1-holdout \
  --mark-selection cusum_engage_then_skills \
  --dense-window 1.0 --dense-max 1 --mark-min-gap 0.4 \
  --out docs/rofl-research/autoresearch/fight_outcome/r33/experiments/e16_zero_dead_keep.json
npm run fight:agreement -- --suite-label S0 \
  --from-eval docs/rofl-research/autoresearch/fight_outcome/r33/experiments/e16_zero_dead_keep.json \
  --out-dir docs/rofl-research/autoresearch/fight_outcome/r33/experiments \
  --audit-dir docs/rofl-research/autoresearch/fight_outcome/r33/audits/e16_zero_dead_keep
```

## Digest

Untouched. digestCleanGate not regressed.
