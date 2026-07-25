# R26 NOTES — check03-poison

**Branch:** `adv/fo-r26-check03-poison`  
**Worktree:** `/Users/river/.codex/worktrees/rofl-fo-r26`  
**never_edited_parent:** true (code); docs mirrored to parent `fight_outcome/r26/`  
**FA ≠ odds**

## Next action

Absorb **NO PRODUCT KEEP**. Research path: assist-gated multi-caster share stays harness/CLI-only.

## Mandate

Diagnose Path1 check03 Olaf→Camille full earlyPoisoned residual after R19 `idleFollowActual`. Own opener/early only — not Galio miss-kill (R18/R24). No one-coefficient early+late.

## Root cause (measured)

1. **Not idle freeze.** R19 already fixed that (earlyMae 527→476; still poison).
2. **Teamfight opener overkill.** First 5s: Olaf skills=2, ally skills=8 (Jarvan/Galio/Seraphine/Shen). Near-kill `assistProbe` (±2s) shows 0 allies — **wrong window for early poison**.
3. Model applies full Olaf 1v1 pulse (+ AA-at-mark) at first mark (~1.73s) → `lethalErrorSec≈−18.3` while actual death ~20s → late-bin model HP≈0 vs actual high → `earlyPoisoned`.
4. `false_all_in` = false (killer skills present in early bin).

Measured early skill-count share proxy: `2/(2+8)=0.20` (counts only — not damage invent).

## Experiments (auto)

| id | change | c3 earlyMae | poison | c2 kill | note |
|----|--------|------------:|:------:|:-------:|------|
| e0 | product idleFollow | 476 | Y | Y | baseline |
| e1 | no-aa-at-mark | 476 | Y | Y | Q pulse alone still lethal |
| e6 | global share0.40+no-aa | 106 | N | **N** | one-coeff trap |
| e8 | assist share0.40+no-aa | 106 | N | Y | research; S1 aa risk |
| **e12** | assist share0.20 + aaScaled | **89.6** | **N** | Y | S0 FA↑; **S1 FA↓** |

Engine honesty: `aaAtEachMark` now multiplies by `mark.share` (default share=1 → noop).

## KEEP decision

**NO PRODUCT KEEP** — S1 regresses (c2 Cass→Viktor also has allySkills5s=8; same gate steals lethals).

| | e0 | e12 | Δ |
|--|---:|---:|--:|
| check03 earlyMae | 476 | 89.6 | **−386.4** |
| S0 FA | 0.4107 | 0.5455 | **+0.1348** |
| S1 FA | 0.4170 | 0.3607 | **−0.0563** |

Room research best: `r26/best.json` (e12). Parent `autoresearch/best.json` **not** rewritten.

## Sharper blocker

Need multi-caster share that is **not** a global ally-count threshold colliding with S1 teamfights — e.g. damage-attribution from same-match packets, or victim-side HP residual share — without inventing pins. Opener vs finish remain separate tracks.

## Repro

```bash
npx --yes tsx scripts/crosscheck_action_aligned.ts \
  --suite 2970132-g1-holdout \
  --mark-selection cusum_engage_then_skills \
  --dense-window 1.0 --dense-max 1 --mark-min-gap 0.4 \
  --killer-pulse-share 0.20 --assist-ally-min 5 \
  --out docs/rofl-research/autoresearch/fight_outcome/r26/experiments/e12_assist_share_0p20_aaScaled.json
```
