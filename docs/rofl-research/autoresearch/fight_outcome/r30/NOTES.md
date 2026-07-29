# R30 NOTES — olaf-lethal-timing

**Branch:** `adv/fo-r30-olaf-lethal-timing`  
**Worktree:** `/Users/river/.codex/worktrees/rofl-fo-r30`  
**never_edited_parent_code:** true (docs mirrored to parent `fight_outcome/r30/` only)  
**Product KEEP:** yes (worktree engine + harness defaults)  
**FA ≠ odds / pBlue%**

## Mandate

Shrink Olaf→Trundle `|lethalErrorSec|` toward ≤0.75. Opener vs finish separate. No invent pins; no S1 tune; no mark/density/regen sweeps. Product KEEP iff S0 FA↑ and S1 not regress.

## Diagnosis (FINISH track)

c2 earlyMae already honest (0 / 9.5) → **not opener**.  
Baseline model lethal locks to **Q@18.863** vs truth kill@20.0 → `lethErr = -2.81` (early overdamage).  
R@14.96 modeled as a full cast pulse invents nuke damage for a steroid/utility ult.

## KEEP config (e8 = e7b)

1. `aaAtEachMark: false` (keep trailing finish AA)
2. `perSlotPulse: true` with `pulseBySlot R=0` (slots 1/2/3 unchanged)

| Metric | Before (R25/e0) | After (e8 KEEP) | Δ |
|--------|----------------:|----------------:|--:|
| Olaf→Trundle \|lethErr\| | 2.81 | **0.33** | −2.48 |
| S0 FA | 0.4107 | **0.5897** | **+0.179** |
| S0 pass | 0.167 | **0.333** | +0.167 |
| S1 FA | 0.4170 | **0.5620** | **+0.145** |
| S1 pass | 0.000 | **0.333** | +0.333 |

c2 windows: lethalOk **true** (still fail pathMae — residual).

## Rejected / research-only

| Exp | Result |
|-----|--------|
| finish-aa-max / no-finish-aa alone | no c2 move (lethal at mark, not trailing AA) |
| finish-horizon 2 | c2 miss-kill |
| e7c R/W=0 keep aa-at-mark | S0↑ but **S1 regress** 0.417→0.404 → no KEEP |
| R18-style no-aa alone | S0 only +0.012; lethErr 1.14 still >0.75 |

## Product files touched (worktree only)

- `src/engine/killWindowProduct.ts` — defaults
- `src/engine/killWindowOverlay.ts` — simulateKillWindowMatchup defaults
- `scripts/crosscheck_action_aligned.ts` — EXPERIMENT + `--pulse-by-slot` CLI

## Repro

```bash
cd /Users/river/.codex/worktrees/rofl-fo-r30
npx --yes tsx scripts/crosscheck_action_aligned.ts \
  --suite 2970132-g1-holdout \
  --mark-selection cusum_engage_then_skills \
  --dense-window 1.0 --dense-max 1 --mark-min-gap 0.4 \
  --out docs/rofl-research/autoresearch/fight_outcome/r30/experiments/e8_product_keep.json
npm run fight:agreement -- \
  --suite-label S0 \
  --from-eval docs/rofl-research/autoresearch/fight_outcome/r30/experiments/e8_product_keep.json \
  --out-dir docs/rofl-research/autoresearch/fight_outcome/r30/experiments \
  --audit-dir docs/rofl-research/autoresearch/fight_outcome/r30/audits/e8_product_keep
```

## Digest

`validate-rofl-pipeline.py --product` Path1 2970132 still green (untouched). digestCleanGate not regressed.

## Handoff

- Orchestrator PARENT_MERGE: product defaults above; update `best.json` fightAgreement → 0.5897 with `unfrozenFromComposite: 0.9683`.
- Residual blockers: c1 Galio miss-kill (R24/R28); c3 earlyPoisoned (R26); c2 pathMae after lethalOk.
