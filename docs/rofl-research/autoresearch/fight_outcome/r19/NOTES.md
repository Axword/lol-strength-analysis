# R19 — Path1 earlyBand / idle honesty

**Branch:** `adv/fo-r19-path1-early`  
**Worktree:** `/Users/river/.codex/worktrees/rofl-fo-r19`  
**never_edited_parent:** true (code); docs mirrored to parent `fight_outcome/r19/`  
**FA ≠ odds**

## Mandate

Lift 2970132 Path1 S0 earlyBand (R05 Galio→Trundle earlyMae 116/233, cap 50). Product cusum. Skip mark/regen knob sweeps. Own early/idle honesty; R18 owns lethal.

## Root cause (measured, not invented)

Freeze-idle pins model HP at window-start (~1261) while Trundle levels 6→7 (actual 1261→1447) in the first √T bin. Frozen MAE ≈ **116** = exact check01 full earlyMae. Not false_all_in (no pre-engage damage invent).

## KEEP

`idleFollowActual: true` — mirror observed victim HP until `engageSec`, then start combat from actual HP at engage.

- Product: `PRODUCT_KILL_WINDOW_DEFAULTS.idleFollowActual`
- Engine: `simulateKillWindowSeries` / `simulateKillWindowMatchup`
- Harness: default on; `--no-idle-follow-actual` ablation

## Discarded / handoff

| Exp | Result |
|-----|--------|
| E2 post_engage + idle-follow | earlyMae blows out (c1 487); discard |
| E6/E8 no aa-at-mark | S0/S1 FA lift but finish-AA adjacent to R18 lethal — **research only**, product `aaAtEachMark` unchanged |
| check03 earlyPoisoned | still true after idle-follow (476 earlyMae) — **R18 lethal/opener** |

## Repro

```bash
npx --yes tsx scripts/crosscheck_action_aligned.ts \
  --suite 2970132-g1-holdout \
  --mark-selection cusum_engage_then_skills \
  --dense-window 1.0 --dense-max 1 --mark-min-gap 0.4 \
  --out docs/rofl-research/autoresearch/fight_outcome/r19/experiments/e5_default_idle_follow.json
```
