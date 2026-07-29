# Sqrt-time bins (anti-overfit)

## What it is
For a trade of length `T` seconds, split into pieces of width `√T`.  
In each piece, measure variance of `(modelHp − actualHp)`.  
Rank pieces by `priority = variance × compoundWeight` (early pieces weigh more).

**This is a flashlight, not a fit target.**

## Anti-overfit rules (hard)
1. Never minimize bin variance as a loss on the same fight.
2. Never change kit/engine numbers from one check’s top bin.
3. `activeTracks` = phases in ≥2 checks’ top-2 (dual tracks OK). Never one coefficient for two tracks.
4. After any real engine change: re-score on a **holdout** game (Phase C).

## Commands (~1 min)

```bash
npm run test:crosscheck-sqrt
npm run crosscheck:kill -- --check 1 --segment full
npm run crosscheck:sqrt -- --segment full
```

## Current signal (2970110 g1)

| Lens | `#1` glance | `activeTracks` |
|------|-------------|----------------|
| full | late | **late + early** |
| burst | early | **early + mid** |

Dual-track brief: `docs/rofl-research/crosscheck-dual-track.md`.
