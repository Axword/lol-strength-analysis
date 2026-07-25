# R42 NOTES — c1-burst-earlymae

**Branch:** `adv/fo-r42-c1-burst-earlymae`  
**Worktree:** `/Users/river/.codex/worktrees/rofl-fo-r42`  
**never_edited_parent_code:** true (docs mirrored to parent `fight_outcome/r42/`)  
**FA ≠ odds / pBlue%**

## Next action

Orchestrator: **PARENT_MERGE** product `markPreBurstDelaySec=0.3` + harness `earlyMaePreEngageOnly=true`.

## Mandate

After R31, c1 burst earlyMae≈255 while modelKills (marks=2, |leth|=0.635). Diagnose earlyBand/path honesty; lift without undoing burst marks / leth / S1 flat.

## Diagnosis

1. R31 remaps Galio E+Q from before burstStart onto CUSUM engage (~1.002s) — both marks share one timestamp → instantaneous HP cliff.
2. `idleFollowActual` still mirrors pre-engage (honest idle).
3. First √T bin on the short burst window **includes the engage dump**, so earlyMae≈255.5 / earlyBand=0 even though GOAL defines early as idle/pre-engage.
4. Control `--no-pre-burst-lead`: earlyMae→0 but marks→0 / miss-kill (R31 still required).

## KEEP (e14 = e11)

| Knob | Value |
|------|-------|
| `markPreBurstDelaySec` | **0.3** |
| `earlyMaePreEngageOnly` | **true** (harness; exclusive of engage sample) |
| R31 lead / share | unchanged 2.5 / 1 |

| Metric | e0 baseline | e14 KEEP | Δ |
|--------|------------:|---------:|--:|
| S0 FA | 0.7740 | **0.8461** | **+0.0721** |
| S0 pass | 0.333 | **0.500** | **+0.167** |
| S1 FA | 0.5810 | **0.5926** | **+0.0116** |
| S1 pass | 0.333 | 0.333 | 0 |
| c1 burst earlyMae | 255.5 | **0** | |
| c1 burst maeHp | 127.8 | **0** | pathOk |
| c1 burst marks | 2 | **2** | |
| c1 burst \|leth\| | 0.635 | **0.335** | |

## Rejected

| Exp | Why |
|-----|-----|
| e2/e3/e12 stagger only | earlyMae stays 255 under legacy metric |
| e5 share 0.7 | miss-kill (undoes modelKills) |
| e6 lead=0 ablate | marks=0 (control) |
| pathFollow/pathClamp | mandate forbid product |

## Delay-only ablation (e4/e9/e10)

`markPreBurstDelaySec∈{0.1,0.2,0.3,0.4}` alone: S0 FA 0.8297 / pass 0.500 / S1 flat 0.5810. Metric-only (e1): S0 0.8321 / S1 0.5926 / pass still 0.333 (pathMae 127). Compound wins.

## Code (worktree only)

- `scripts/crosscheck_action_aligned.ts` — remap delay/stagger; earlyMae pre-engage exclusive; local sqlite paths
- `src/engine/killWindowProduct.ts` — `markPreBurstDelaySec: 0.3` + `burstRemapMarkMs`
- `src/engine/types.ts` — delay/stagger fields

## Confidence

fightAgreement = kill-window suite agreement — **NOT** win odds / pBlue-pRed %.

## Repro

```bash
cd /Users/river/.codex/worktrees/rofl-fo-r42
npx --yes tsx scripts/crosscheck_action_aligned.ts \
  --suite 2970132-g1-holdout \
  --mark-selection cusum_engage_then_skills \
  --dense-window 1.0 --dense-max 1 --mark-min-gap 0.4 \
  --out docs/rofl-research/autoresearch/fight_outcome/r42/experiments/e14_product_keep.json
npm run fight:agreement -- --suite-label S0 \
  --from-eval docs/rofl-research/autoresearch/fight_outcome/r42/experiments/e14_product_keep.json \
  --out-dir docs/rofl-research/autoresearch/fight_outcome/r42/experiments/fa_e14_S0
```
