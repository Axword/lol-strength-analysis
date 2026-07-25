# R35 NOTES — preengage-s1safe

**Branch:** `adv/fo-r35-preengage-s1safe`  
**Worktree:** `/Users/river/.codex/worktrees/rofl-fo-r35`  
**never_edited_parent_code:** true (docs mirrored to parent `fight_outcome/r35/`)  
**Product KEEP:** yes (sparse opener defaults)  
**FA ≠ odds / pBlue%**

## Mandate

R23/R24 preEngageOpener / pre-engage lead restore Galio W but S1 regressed under older law. Find **S1-safe** variant (sparse maxPost, far-share, host-gated). Product KEEP only if S0↑ and S1 not regress.

## Baseline (R30 product law)

| Suite | FA | pass |
|-------|-----:|-----:|
| S0 2970132 Path1 | **0.5938** | 0.333 |
| S1 2970137 | **0.5620** | 0.333 |

Galio→Trundle full: W still dropped; kill via E+Q; `|lethErr|=2.61` → lethalHit=0.

## KEEP (e1 = e9 = product defaults)

`preEngageOpenerSec=0.5` + `preEngageOpenerMaxPostMarks=3` (structural; **no host gate**).

| Metric | Before (e0) | After KEEP | Δ |
|--------|------------:|-----------:|--:|
| S0 FA | 0.5938 | **0.6021** | **+0.0083** |
| S1 FA | 0.5620 | **0.5810** | **+0.0191** |
| Galio W retained | N | **Y** (`pre_engage_opener` @15.024) | |
| Galio \|lethErr\| | 2.61 | 1.84 | still >0.75 |

Host-gated e5/e7 match S0 lift with S1 flat — also KEEP-legal; structural e1 preferred (S1↑ too).

## Rejected

| Exp | Why |
|-----|-----|
| e2/e8 lead0.4 | S0 FA −0.20 (earlyBand) |
| e3 R24 farShare+maxMarks | S0 −0.20; S1 −0.22 |
| e4 host-gated e3 | S0 still −0.20; S1 still regresses via maxKillerMarks on host |
| e6 sparse+far host | S0↑ less than e1; Galio over-early (−3.64) |

## Product files touched (worktree only)

- `src/engine/killWindowOverlay.ts` — select/simulate pre-engage knobs
- `src/engine/killWindowProduct.ts` — KEEP defaults
- `src/engine/types.ts` — KillWindowInputOptions fields
- `scripts/crosscheck_action_aligned.ts` — CLI + host gate + suite `2970132-g1`

## Repro

```bash
cd /Users/river/.codex/worktrees/rofl-fo-r35
npx --yes tsx scripts/crosscheck_action_aligned.ts \
  --suite 2970132-g1-holdout \
  --mark-selection cusum_engage_then_skills \
  --dense-window 1.0 --dense-max 1 --mark-min-gap 0.4 \
  --out docs/rofl-research/autoresearch/fight_outcome/r35/experiments/e_keep_verify_S0.json
npm run fight:agreement -- \
  --suite-label S0 \
  --from-eval docs/rofl-research/autoresearch/fight_outcome/r35/experiments/e_keep_verify_S0.json \
  --out-dir docs/rofl-research/autoresearch/fight_outcome/r35/experiments
```

## Handoff

- Orchestrator PARENT_MERGE: product sparse opener defaults; best FA → **0.6021** (S1 **0.5810**).
- Residual: Galio lethalHit still 0 (`|lethErr|=1.84`); burst 0 marks; far-share unsafe under idleFollow.
- FA = fight-outcome suite agreement — **not** win odds.
