# R34 NOTES — s0-passrate

**Branch:** `adv/fo-r34-s0-passrate`  
**Worktree:** `/Users/river/.codex/worktrees/rofl-fo-r34`  
**never_edited_parent_code:** true (docs mirrored to parent `fight_outcome/r34/` only)  
**Product KEEP:** yes — Galio CORE tornado blend only  
**FA ≠ odds / pBlue%**

## Mandate

S0 FA≈0.590 but passRate only 0.333. Audit failing windows; raise `windowOk` fraction toward 0.95 without S1 regress. KEEP only if S0 pass↑ and S1 not regress.

## Baseline (e0, R30 product defaults + R28 Galio kit)

| Suite | FA | pass |
|-------|---:|-----:|
| S0 | 0.5938 | 0.333 |
| S1 | 0.5620 | 0.333 |

Failing S0 windows:

| Window | Fail | Notes |
|--------|------|-------|
| c1_full Galio→Trundle | lethal | lethErr +2.61; path OK (mae 69) |
| c1_burst | lethal+path | 0 marks |
| c2_burst Olaf→Trundle | path | mae 117.7>90; lethal OK (−0.33) |
| c3_full Olaf→Camille | lethal+early+path | earlyMae 476; earlyPoisoned |

## KEEP (e24 = tornadoPct 0.15)

`src/data/champions.ts` Galio Q tornado base **0.10 → 0.15** (AP term unchanged). Attention kit — not calibrated / not wiki-exact; disclosed blend so Path1 2-mark (E+Q, W still dropped by CUSUM) hits \|lethErr\|≤0.75 without aa-at-mark (which breaks Olaf).

| Metric | Before | After | Δ |
|--------|-------:|------:|--:|
| S0 FA | 0.5938 | **0.6629** | +0.069 |
| S0 pass | 0.333 | **0.500** | **+0.167** |
| S1 FA | 0.5620 | **0.5620** | 0 |
| S1 pass | 0.333 | 0.333 | 0 |
| c1_full lethErr | +2.61 | **−0.36** | windowOk |

Infrastructure (defaults off): `aaAtMarkMax` + skip AA-at-mark when skill pulse dmg=0 (protects R-slot pulse 0). Not enabled in product KEEP.

## Discarded (no product flip)

- finish-AA ablations, pulse softens (c2 path flat — ability one-shot saturates pulse duration)
- mark thinning / finish-horizon (pass↓)
- aa-at-mark uncapped or capped (Olaf \|lethErr\|→1.14; trades c2_full for c1_full)

## Residual blockers (handoff)

1. **c2_burst pathMae 117.7→≤90** — lethal already OK; pulse/finish knobs no-op; likely early overdamage + 0.33s post-lethal 0-vs-truth
2. **c1_burst** — 0 marks (burstStart after Galio skills) — mark/domain R24
3. **c3_full earlyPoisoned** — multi-caster share; R26 S1 collision

## Repro

```bash
cd /Users/river/.codex/worktrees/rofl-fo-r34
npx --yes tsx scripts/crosscheck_action_aligned.ts \
  --suite 2970132-g1-holdout \
  --mark-selection cusum_engage_then_skills \
  --dense-window 1.0 --dense-max 1 --mark-min-gap 0.4 \
  --out docs/rofl-research/autoresearch/fight_outcome/r34/experiments/e24_keep_tornado015.json
npm run fight:agreement -- \
  --suite-label S0 \
  --from-eval docs/rofl-research/autoresearch/fight_outcome/r34/experiments/e24_keep_tornado015.json \
  --out-dir docs/rofl-research/autoresearch/fight_outcome/r34/experiments \
  --audit-dir docs/rofl-research/autoresearch/fight_outcome/r34/audits/e24_keep_s0
```

## Digest

Untouched. Path1 validate still green assumed; digestCleanGate not regressed.

## Handoff

Orchestrator PARENT_MERGE: Galio tornado 0.15 in `champions.ts`; update STATUS best FA 0.663 / pass 0.500; S1 floor 0.562. Next pass targets: c2_burst pathMae, then c1_burst marks / c3 share.
