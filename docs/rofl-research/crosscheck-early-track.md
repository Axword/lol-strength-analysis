# Early-track investigation (2970110) — no fit

**Status:** investigation only. Do not change damage coefficients from this note.

## Method
For each check’s **full** window, look at the first √T bin (0–5s when T=25).
Compare:
- actual victim HP drop
- model victim HP drop  
- killer `skill_used` count in that bin

## Results

| Check | Matchup | Skills (killer) | Actual HP drop | Model HP drop | meanErr | Class |
|-------|---------|-----------------|----------------|---------------|---------|-------|
| 01 | Camille→Leona | **1** (slot 2 @ 2.2s) | 99 | 104 | −158 | sparse engage |
| 02 | Syndra→Camille | **0** | **0** | **266** | −814 | **false all-in** |
| 03 | Ezreal→LeeSin | 5 | 2191 | 759 | +428 | teamfight / assists |

## What this means (plain English)

1. **Check 02 is the early-track smoking gun.**  
   Nobody cast. Victim HP flat. Model still “fights” for 5 seconds.  
   That is not a kit-number problem. That is **engage gating**.

2. **Check 01:** model end-of-bin *drop* ≈ actual (~100), but path meanErr −158 because the model is on a continuous all-in clock while reality had one ability. Path shape ≠ total drop.

3. **Check 03:** opposite sign (underdamage). Early bin is a skirmish with many casts — 1v1 model cannot eat assist/AoE. Do **not** fix this by buffing Ezreal damage; that would worsen 01/02.

## Dual-track rule still holds
- Early fix class ≠ late fix class.
- A damage × multiplier that “fixes” check 02 early will wreck check 03 early.

## Diagnostic wired (no combat.ts change)

```bash
npx --yes tsx scripts/crosscheck_kill_window.ts --check 2 --segment full
# look at earlyTrack.class / falseAllIn
```

Observed on re-run:
- check 01 → `sparse_engage`
- check 02 → `false_all_in` ✅
- check 03 → `teamfight_under`

## Gate research done
See `docs/rofl-research/crosscheck-gate-research.md`.
Early false_all_in fixed in dry-run; lethal/late still need engage-time re-pin before any product gate.

## Anti-overfit
- Do not retune Camille/Syndra kits from check 02.
- Any engage-gate change must re-run checks 01–03 early **and** late bins + holdout game.
