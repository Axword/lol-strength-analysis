# R43 NOTES — s1-anivia-sylas-lethal

**Branch:** `adv/fo-r43-s1-anivia-sylas-lethal`  
**Worktree:** `/Users/river/.codex/worktrees/rofl-fo-r43`  
**never_edited_parent_code:** true (docs mirrored to parent `fight_outcome/r43/`)  
**Product KEEP:** yes — Anivia CORE (Q double + E chill×2 + Q-fold Glacial Storm 7 ticks)  
**FA ≠ odds / pBlue%**

## Mandate

Lift S1 Anivia→Sylas miss-kill (c3 full/burst leth null, huge mae) without inventing pins/ranks and without S0 regress.

## Diagnosis

1. Pins honest: Anivia/Sylas `hp_known`/`combat_known`/`ranks_known` all 1 at window (AP148, E5, R2). Not a PE/combat invent block.
2. Product `pulseBySlot[4]=0` zeroes R marks; 0.4s kit-dump rarely casts R, so fattening R packets alone no-ops (e9).
3. Meraki Anivia under-counts Flash Frost double-hit + Frostbite chill amp + storm DPS.
4. Global R-pulse=0.4 kills Anivia but regresses S0 Olaf path/leth (e3) — discard.

## Product KEEP (e12)

**Anivia CORE** in `src/data/champions.ts`:
- Q: pass+detonate; when R ranked, fold **7** Glacial Storm ticks into Q dump (R-pulse stays 0)
- E: chilled ×2 in extended/all-in
- R: 1-tick stub (introspection); storm carried via Q-fold
- W: utility wall (never skip for 0 damage)

| Metric | Baseline (e0/e0b) | e12 KEEP | Δ |
|--------|------------------:|---------:|--:|
| S1 FA | 0.5810 | **0.7095** | **+0.1285** |
| S1 pass | 0.333 | **0.500** | +0.167 |
| S0 FA | 0.7740 | **0.7740** | **flat** |
| S0 pass | 0.333 | 0.333 | 0 |
| c3 full | miss / mae335 | **kill \|leth\|=0.125** / mae71.4 / **windowOk** | |
| c3 burst | miss / mae647 | **kill \|leth\|=0.125** / mae198 / earlyMae267 | leth ok; early/path still fail |

Authoritative STATUS S0 0.7766 vs worktree remesaure 0.7740 = pre-existing residual_hp wire gap (not introduced here).

## Discarded

| Exp | Why |
|-----|-----|
| e1/e2 global R pulse | miss-kill remains; flat dump |
| e3 S0 R pulse | Olaf mae/leth regress |
| e6 CORE+R pulse | kill but \|leth\|=1.04>0.75 + needs global R |
| e7/e8 finish/AA | still miss |
| e9 fat R only | no dump cast effect |
| e10 fold6 | leth +2.45 late |
| e11 fold≥8 | leth −1.04 early cliff |
| e13 ally-truth | assistProbe=0; no lift |

## Sharper residual (post-KEEP)

c3_burst still fails windowOk: earlyMae≈267 (burst onset vs fat Q dumps) and mae≈198>90. Full window is clean. fightOutcomeGate stays false (FA≪0.95).

## Repro

```bash
cd /Users/river/.codex/worktrees/rofl-fo-r43
npx --yes tsx scripts/crosscheck_action_aligned.ts \
  --suite 2970137-g1-holdout \
  --mark-selection cusum_engage_then_skills \
  --dense-window 1.0 --dense-max 1 --mark-min-gap 0.4 \
  --out docs/rofl-research/autoresearch/fight_outcome/r43/experiments/e12_s1_qfold7.json
npm run fight:agreement -- --suite-label S1 \
  --from-eval docs/rofl-research/autoresearch/fight_outcome/r43/experiments/e12_s1_qfold7.json \
  --out-dir docs/rofl-research/autoresearch/fight_outcome/r43/experiments \
  --audit-dir docs/rofl-research/autoresearch/fight_outcome/r43/audits/e12_s1
```

## Digest

Untouched. digestCleanGate not regressed.
