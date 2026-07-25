# R53 NOTES — s1-vayne-letherr

**Branch:** `adv/fo-r53-s1-vayne-letherr`  
**Worktree:** `/Users/river/.codex/worktrees/rofl-fo-r53`  
**never_edited_parent_code:** true (docs mirrored to parent `fight_outcome/r53/`)  
**Product KEEP:** yes — Vayne CORE (Tumble AA+bonus + Silver Bolts ×0.65 Q-fold)  
**FA ≠ odds / pBlue%**

## Next action

Orchestrator PARENT_MERGE: absorb Vayne CORE from `src/data/champions.ts` (E2/E8). No harness knob change.

## Mandate

S1 Vayne→Ambessa c1 full |leth| 2.05→≤0.75 without invent and without S0 regress. FA≠odds.

## Diagnosis

1. Pins honest at window (AD97, Q3/W1/E1/R1, Ambessa armor54 / hpMax1239). Not invent.
2. Product marks: E + R + Q + Q. `pulseBySlot[4]=0` correctly zeroes Final Hour (steroid).
3. Meraki models Silver Bolts as a **castable W** and Tumble as **bonus-only**, so kit-dump pulses under-count empowered AA + 3rd-hit true damage.
4. After E/Q/Q pulses, residual HP needs **4 finish AA** → firstLethal≈22.05 vs truth 20.0 → |leth|=2.05.

## Product KEEP (E2 / E8 verify)

**Vayne CORE** in `src/data/champions.ts`:
- Q Tumble: auto + bonus AD ratio; fold Silver Bolts ×**0.65** into Q dump (R-pulse stays 0)
- W: utility stub (passive; never skip for 0 cast damage)
- E: Condemn (physical + hard CC)
- R: Final Hour steroid stub (tiny AD; utility MS) — damage ult still pulse-0

| Metric | Baseline (e0) | E2/E8 KEEP | Δ |
|--------|--------------:|----------:|--:|
| S1 c1_full \|leth\| | 2.05 | **0.09** | **−1.96** |
| S1 FA | 0.7628 | **0.8322** | **+0.0694** |
| S1 pass | 0.500 | **0.667** | +0.167 |
| S0 FA | 0.9304 | **0.9304** | **flat** |
| S0 pass | 0.667 | 0.667 | 0 |
| c1_burst | miss / null | kill leth=0.75 | leth band edge |

## Discarded

| Exp | Why |
|-----|-----|
| E1 full bolt + P passive | overshoot c1_full leth −0.89 (\|leth\|=0.89>0.75) |
| E3 finishAa max 6 | no-op (lethal already on 4th AA timing) |
| E4 aaAtEachMark | overshoot leth −1.82; S0-unsafe pattern |
| E5 R-pulse 0.25 global | leth −0.89; would risk S0 Olaf (R43 lesson) |
| E6 openerSec 2.5 | flat \|leth\|=2.05 (early Q still density/gap filtered) |
| E7 Q pulse 0.7 | flat (pulse floor damage insensitive to +0.3s) |

## Residual

- c1_burst lethalOk false at leth=0.7503 (strict ≤0.75 edge); pathOk.
- c3_burst Anivia pathMae 198 (pre-existing R43 residual).
- fightOutcomeGate false (FA≪0.95). FA ≠ odds.

## Repro

```bash
cd /Users/river/.codex/worktrees/rofl-fo-r53
npx --yes tsx scripts/crosscheck_action_aligned.ts \
  --suite 2970137-g1-holdout \
  --mark-selection cusum_engage_then_skills \
  --dense-window 1.0 --dense-max 1 --mark-min-gap 0.4 \
  --out docs/rofl-research/autoresearch/fight_outcome/r53/experiments/e8_keep_verify_S1.json
npm run fight:agreement -- --suite-label S1 \
  --from-eval docs/rofl-research/autoresearch/fight_outcome/r53/experiments/e8_keep_verify_S1.json \
  --out-dir docs/rofl-research/autoresearch/fight_outcome/r53/experiments/fa_e8_S1
```

## Digest

Untouched. digestCleanGate not regressed.
