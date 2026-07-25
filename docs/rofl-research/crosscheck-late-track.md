# Late-track investigation (2970110) — no fit

**Status:** investigation only. Do not change damage coefficients from this note.

## Method
For each check’s **full** window, take the highest-priority **late** √T bin (usually 15–20s when T=25).
Compare start HP, drop, lethal timing, killer `skill_used`.

## Results

| Check | Late class | Actual→model @ late start | Actual drop | Model drop | Lethal err | Plain English |
|-------|------------|---------------------------|-------------|------------|------------|---------------|
| 01 Camille→Leona | `lethal_ok_path_off` / path mismatch | 442 vs ~136 | 243 | ~83 | **−0.35s** | Kill clock OK; model already shredded victim early |
| 02 Syndra→Camille | **`early_poisoned`** | ~849 vs ~188 (≤30% actual) | 692 | ~188 | +1.64s | Late variance mostly early poison — model already shredded |
| 03 Ezreal→LeeSin | **`finish_under`** | 987 vs ~1246 | 291 | negative/flat | +3.28s | Real finish happens; 1v1 model barely moves HP |

Kill payloads here have **no assist IDs** — cannot prove assists from wire; still treat 03 as multi-fighter risk.

## What this means

1. **Check 02 late is not a late bug.**  
   `early_poisoned` = fix **engage gate** (early track). Tuning finish damage would be overfitting.

2. **Check 01:** lethal timing is already good. Remaining error is path (early/mid overdamage compounding into late). Same family as early `sparse_engage`, not a new “finisher coeff.”

3. **Check 03:** only clear **late-native** underdamage. Do not buff Ezreal globally to chase this — would worsen 01/02.

## Dual-track map (both active)

```
early: false_all_in / sparse_engage  →  engage gating
late:  early_poisoned (ignore as late) | finish_under (03 only) | lethal_ok_path_off (01)
```

## Diagnostic command

```bash
npx --yes tsx scripts/crosscheck_kill_window.ts --check 2 --segment full
# lateTrack.earlyPoisoned === true  → do not tune late
```

## Anti-overfit
- If `earlyPoisoned`: **stop late work on that check.**
- Never one coefficient for early+late.
- Holdout game before any engine change.
