# R39 NOTES — passrate-failing-windows

**Branch:** `adv/fo-r39-passrate-failing-windows`  
**Worktree:** `/Users/river/.codex/worktrees/rofl-fo-r39`  
**never_edited_parent_code:** true (docs mirrored to parent `fight_outcome/r39/`)  
**Product KEEP:** yes — W-slot opener share 0.18  
**FA ≠ odds / pBlue%**

## Mandate

Lift `fightPassRate` from 0.333 by auditing the 4 failing S0 windows; KEEP iff S0 FA↑ and S1 flat+. Selector stays `cusum_engage_then_skills`. No pathFollow/pathClamp product.

## Parent stack baseline (post-R31 compound)

| Suite | FA | pass |
|-------|---:|-----:|
| S0 2970132 Path1 | **0.7766** | 0.333 |
| S1 2970137 | **0.5810** | 0.333 |

Worktree remesaure e0: S0 FA **0.7740** / pass 0.333 (bit-close; c1 mae drift 141.9 vs 131.6).

## Failing S0 audits (e0 / parent stack)

| Window | Fail | Root |
|--------|------|------|
| c1_full Galio→Trundle | lethal + path | Full W opener + E+Q → \|leth\|=1.84; maeFull≈132–142 |
| c1_burst | early + path | pre-burst remaps E+Q onto engage; earlyMae=255.5; maeBurst=127.8 |
| c2_burst Olaf→Trundle | path | maeBurst=111.6 (>90); kit-dump flat pulse (R33); lethOk |
| c3_full Olaf→Camille | early + path | earlyMae=89.5; maeFull=159.3; ally attrib already on |

## KEEP (e19/e20)

`preEngageOpenerShare=0.18` + `preEngageOpenerShareSlots=[2]` (W only).

Retains Galio W mark (action coverage) but attenuates charged-W pulse so tornado+E+Q land in lethal band. S1 Vayne opener is slot **1** → untouched → S1 FA flat.

| Metric | Before (e0 / auth) | After KEEP | Δ |
|--------|-------------------:|-----------:|--:|
| S0 FA | 0.7740 (auth 0.7766) | **0.8416** | **+0.0676** (+0.0650 vs auth) |
| S0 pass | 0.333 | **0.500** | **+0.167** |
| S1 FA | 0.5810 | **0.5810** | **0** |
| S1 pass | 0.333 | 0.333 | 0 |
| c1_full \|leth\| | 1.84 | **0.36** | windowOk |
| c1_full marks | 3 (W+E+Q) | **3** (W retained) | |

## Rejected

| Exp | Why |
|-----|-----|
| finishAa / pulse softens | no-op on kit-dump flat damage (R33) |
| pre-burst share <1 | S0 FA regress; A4 lethal risk |
| maxKillerMarks 4 | S0 FA crash; Olaf leth regress |
| openerSec=0 | S0↑ but **S1 FA 0.581→0.562** |
| global openerShare 0.16–0.20 | S0↑ but **S1 FA →0.54** (Vayne Q opener) |
| tornado 0.12 | path MAE only; lethErr unchanged (W dominates) |
| pathFollow/pathClamp | forbidden product (S1 regress known) |

## Residual blockers (handoff)

1. **c2_burst pathMae 111.6→≤90** — kit-dump; pulse/finish no-op; pathFollow S1-unsafe  
2. **c1_burst earlyMae 255.5 + pathMae 127.8** — pre-burst remap piles E+Q at engage; early sqrt-bin polluted  
3. **c3_full earlyMae 89.5 + pathMae 159** — need stronger multi-caster residual without S1 collision  

## Repro

```bash
cd /Users/river/.codex/worktrees/rofl-fo-r39
npx --yes tsx scripts/crosscheck_action_aligned.ts \
  --suite 2970132-g1-holdout \
  --mark-selection cusum_engage_then_skills \
  --dense-window 1.0 --dense-max 1 --mark-min-gap 0.4 \
  --out docs/rofl-research/autoresearch/fight_outcome/r39/experiments/e20_product_keep_verify_S0.json
npx --yes tsx scripts/fight_agreement_suite.ts \
  --from-eval docs/rofl-research/autoresearch/fight_outcome/r39/experiments/e20_product_keep_verify_S0.json \
  --suite-label S0 --out-dir docs/rofl-research/autoresearch/fight_outcome/r39/experiments/fa_e20_S0
```

## Files (worktree only)

- `src/engine/killWindowOverlay.ts` — opener share + slot filter  
- `src/engine/killWindowProduct.ts` — KEEP defaults  
- `src/engine/types.ts` — option fields  
- `scripts/crosscheck_action_aligned.ts` — CLI + EXPERIMENT defaults  

fightAgreement = kill-window suite agreement — **NOT** win odds.
