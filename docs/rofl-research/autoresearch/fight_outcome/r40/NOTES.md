# R40 NOTES — c2-pathmae-slot-pulse

**Branch:** `adv/fo-r40-c2-pathmae-slot-pulse`  
**Worktree:** `/Users/river/.codex/worktrees/rofl-fo-r40`  
**never_edited_parent_code:** true (docs mirrored to parent `fight_outcome/r40/` only)  
**Product KEEP:** **NO**  
**FA ≠ odds / pBlue%**

## Mandate

Lift c2_burst pathMae from ~111.6 to ≤90 (pathOk) via slot-scoped single-ability pulses / kit-dump honesty. No pathFollow S1 regress. KEEP only if S0 FA↑ and S1 flat+.

## Diagnosis

1. Kit dump (`simulateMatchup` pulse) one-shots victim HP at any pulseSec in (0,1] — pulse softens are dead.
2. Pure slot-scoped Meraki ability once underkills (c2 modelEnd≈1221, miss-kill, mae≈463).
3. Slot + AA weave recovers lethOk at weave≥~3.5, best non-follow mae≈101–103 (still >90).
4. Once lethErr snaps to baseline −0.33, pathMae floors ~101: early overkill + 0.33s model=0 vs truth HP. zeroDead already on.
5. Series pathFollow (finish pad 0.4) makes c2 pathOk (mae=0) but breaks Galio c1_burst kill and **S1 FA regresses** (0.581→0.531, pass 0) — research only, same R33 lesson.

## Baselines (this worktree remesaure)

| Suite | FA | pass | c2_burst mae | pathOk |
|-------|---:|-----:|-------------:|:------:|
| S0 e0 kit-dump | **0.7740** | 0.333 | **111.6** | false |
| S1 e0 | **0.5810** | 0.333 | — | — |

Authoritative compound post-R31 was S0 0.7766 / S1 0.5810 (bit-match S1).

## Experiment highlights (≥8; 33 evals on disk)

| Exp | Idea | c2 mae | leth | S0 FA | S1 FA | Note |
|-----|------|-------:|-----:|------:|------:|------|
| e0 | kit dump baseline | 111.6 | −0.33 | 0.774 | 0.581 | reference |
| e1 | slot binary | 462.6 | miss | — | — | underkill |
| e8 | slot+aaWeave4 | 102.0 | −0.33 | **0.687** | **0.567** | FA↓ both |
| e12 | weave4+blend0.10 | 101.1 | −0.33 | 0.687 | 0.571 | best non-follow mae |
| e21 | kit+pathFollow0.4 | **0.0** | −0.33 | 0.758 | **0.531** | pathOk; S1 regress; c1 miss |
| e25–e29 | fractional weave | 103–122 | cliff | — | — | cannot break −0.33 floor without miss |

## Verdict: **NO KEEP**

- No config hits pathMae≤90 **and** S0 FA↑ **and** S1 flat+.
- Slot-scoped honesty is real (kit dump exposed) but Meraki single-ability + AA weave cannot close the ≤90 gap without truth-follow.
- pathFollow remains research-only (S1 pass→0).
- Product defaults stay off: `slotScopedPulse=false`, `pathFollowActualUntilFinish=false`.

## Sharper blocker

**c2_burst pathMae floor ≈101 under lethOk (−0.33s) without truth-follow.** Kit-dump one-shot and slot+weave share the same early-lethal cliff; residual MAE is post-overkill 0-vs-truth until kill. pathFollow clears pathOk on S0 but fails S1 (and Galio c1). Next track needs S1-safe ally/residual damage timing — not global pathFollow and not invent.

## Code (research opt-in, default off)

- `killWindowSlotPulseDamage` + `slotScopedPulse` / `slotScopedAaWeave` / `slotKitBlend` / `slotPulseHpFracCap` / `pathFollowActualUntilFinish`
- CLI: `--slot-scoped-pulse`, `--slot-scoped-aa-weave N`, `--slot-kit-blend`, `--slot-hp-frac-cap`, `--path-follow`, `--path-follow-finish`

## Repro

```bash
cd /Users/river/.codex/worktrees/rofl-fo-r40
npx --yes tsx scripts/crosscheck_action_aligned.ts \
  --suite 2970132-g1-holdout \
  --mark-selection cusum_engage_then_skills \
  --dense-window 1.0 --dense-max 1 --mark-min-gap 0.4 \
  --out docs/rofl-research/autoresearch/fight_outcome/r40/experiments/e0_baseline.json
npm run fight:agreement -- --suite-label S0 \
  --from-eval docs/rofl-research/autoresearch/fight_outcome/r40/experiments/e0_baseline.json \
  --out-dir docs/rofl-research/autoresearch/fight_outcome/r40/experiments \
  --audit-dir docs/rofl-research/autoresearch/fight_outcome/r40/audits/e0
```

## Digest

Untouched. digestCleanGate not regressed.
