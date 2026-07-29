# R46 NOTES — pass-band-finish

**Branch:** `adv/fo-r46-pass-band-finish`  
**Worktree:** `/Users/river/.codex/worktrees/rofl-fo-r46`  
**never_edited_parent_code:** true (docs mirrored to parent `fight_outcome/r46/` only)  
**Product KEEP:** **NO**  
**FA ≠ odds / pBlue%**

## Next action

Orchestrator: absorb **NO KEEP**. passRate stuck at **0.333** under finish/density/nearKill sweeps. Hand off pathMae (c2_burst) / Galio leth / c1 burst early to R40–R42 — not finish-window.

## Mandate

Lift `fightPassRate` toward 0.95 via finish-window / density / `markAlwaysNearKill` / pass-band honesty. No S1 regress. No invent. No pathFollow/pathClamp product. KEEP iff S0 FA↑ and S1 flat+ **and** passRate↑.

## Baseline (e0 = parent-stack compound)

| Suite | FA | pass |
|-------|-----:|-----:|
| S0 2970132 Path1 | **0.7740** | **0.333** |
| S1 2970137 | **0.5810** | **0.333** |

Authoritative STATUS cites S0 **0.7766** (same stack; ±0.003 harness drift). Failing S0 windows unchanged in kind:

| Window | Fail | Residual |
|--------|------|----------|
| c1_full | lethal + path | \|leth\|≈1.84; mae≈142 |
| c1_burst | early + path | earlyMae 255; mae≈128; marks=2 finish |
| c2_burst | path only | mae **111.6** (need ≤90) — nearest flip |
| c3_full | early + path | earlyMae 89.5; mae≈159 |

## Best non-KEEP (e1 / e19)

`markAlwaysNearKillSec=2` (already product default; harness EXPERIMENT was 1.5):

| Metric | e0 | e1 nearKill2 | Δ |
|--------|-----:|-------------:|--:|
| S0 FA | 0.7740 | **0.7800** | **+0.006** |
| S0 pass | 0.333 | 0.333 | 0 |
| S1 FA | 0.5810 | 0.5810 | 0 |
| S1 pass | 0.333 | 0.333 | 0 |

e19 (`nearKill2` + `finishAaMax2`): S0 FA 0.780 / S1 FA **0.5853** / pass still 0.333 — FA↑ without windowOk flip.

**Rejected for KEEP:** passRate did not rise; mandate owns passRate, not FA-only.

## Rejected levers (n=20)

| Exp | Knob | Why |
|-----|------|-----|
| e2–e3 | nearKill 2.5 / 3.0 | FA same as e1; pass flat |
| e4 / e14 / e18 | dens gap≥1.0 (product dens 1.2/gap1.0) | **S1 FA → 0.44 / pass 0** |
| e5–e7 | finishHorizon 2.5–4 | S0 FA↓; S1 miss-kills |
| e8 | gap 0.8 dens1 | S1 FA −0.003 |
| e9 | densW 2.0 | FA same as e1; pass flat |
| e10 | maxKillerMarks 4 | pass↓; S1 collapse |
| e11 / e19 | finishAaMax 2 | FA↑; pass flat |
| e12 | no finish AA | S1 FA −0.017 |
| e13 | nearKill 0 | returns to e0 |
| e15 | global gap 1 densOff | pass↓; finish exemption lost |
| e16–e17 | gap 1.05–1.1 dens on | drops Olaf E; **c2 mae 111→208**; pass↓ |

## Pass-band honesty (disclosed)

1. Product `markAlwaysNearKillSec: 2` already matches e1; harness EXPERIMENT default **1.5** understates product FA by ~0.006. Not a passRate fix.
2. Product dens `win1.2 / gap1.0` is an **S1 landmine** (e4) vs parent-stack measure `win1.0 / gap0.4`. Do not PARENT_MERGE dens gap↑.
3. Finish-window exemption works (c2 has 2× `finish_window` marks). Mid-fight Olaf R→E spacing (~0.93–1.00s) sits just outside honest gap thinning; forcing gap≥1.05 thins E and **worsens** pathMae.
4. `finishHorizon` is not a passBand: it deletes post-engage spam and opens miss-kills (especially S1).

## Why passRate cannot move here

Nearest flip = c2_burst pathMae 111.6→≤90. Finish/density knobs either no-op (marks stay 6) or over-thin (mae↑ / S1 regress). Kit-dump flat pulse (R33) still blocks pulse softens. pathFollow/pathClamp forbidden for product (S1 regress). Out of r46 ownership.

## Repro

```bash
cd /Users/river/.codex/worktrees/rofl-fo-r46
npx --yes tsx scripts/crosscheck_action_aligned.ts \
  --suite 2970132-g1-holdout \
  --mark-selection cusum_engage_then_skills \
  --dense-window 1.0 --dense-max 1 --mark-min-gap 0.4 \
  --near-kill-sec 2.0 \
  --out docs/rofl-research/autoresearch/fight_outcome/r46/experiments/e1_2970132-g1-holdout.json
npm run fight:agreement -- \
  --suite-label S0 \
  --from-eval docs/rofl-research/autoresearch/fight_outcome/r46/experiments/e1_2970132-g1-holdout.json \
  --out-dir docs/rofl-research/autoresearch/fight_outcome/r46/experiments
```

## Handoff

- **NO KEEP** — no product / harness default merge from r46.
- Orchestrator: leave dens at parent-stack measure (gap 0.4 / win 1.0); do not ship product dens gap1.0.
- Next passRate owners: R40 c2 pathMae slot-pulse; R41 Galio full lethErr; R42 c1 burst earlyMae.
