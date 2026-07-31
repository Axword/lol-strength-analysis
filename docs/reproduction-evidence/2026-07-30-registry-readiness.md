# Published registry readiness audit

This is a read-only audit of the current `public/data/matches/index.json`.
It describes the product registry only; private GRID and replay artifacts are
not promoted by this document.

| Match | Product validated | Stable identity | HP | Combat | Ranks | Match-level calculator ready |
|---|---:|---:|---|---|---|---:|
| `3264361042` | yes | yes | partial | partial at sampled frames | full at sampled frames | no |
| `3264383283` | yes | yes | none | none | none | no |

The registry therefore contains two validated product entries and zero
match-level `calculatorReady` entries. `3264361042` can still permit a
per-playhead Send when every selected living unit has explicit HP, combat, and
rank known-flags; that per-selection path does not upgrade the match-level
registry gate.

The private 2970132 calculator-ready replay remains outside
`public/data/matches/` because durable artifact hosting does not grant
publication authorization. Its exact bundle is now available through the
isolated Vercel reproduction host, with the hosting receipt recorded in
[`2026-07-30-vercel-repro-hosting.md`](2026-07-30-vercel-repro-hosting.md).
The 2970137 holdout and the newly acquired GRID 2970136 games 2 and 3 remain
research-only. Their same-match identity, HP, combat, rank, and dense-position
evidence is preserved, but the GRID source adapter still fails the product
publication gate. The remaining delivery gates are a genuinely separate-
machine reproduction and independently product-ready matches before claiming
multi-match readiness.

The later approved GRID series `2972471` (T1 vs KT Rolster) adds two more
research-validated professional matches, `LOLTMNT02-441926` and
`LOLTMNT02-441944`. Both remain outside the registry because their source
adapter is `grid_riot_livestats` and their embedded build is
`16.14.794.9266`; see
[`2026-07-31-grid-2972471-pro-matches.md`](2026-07-31-grid-2972471-pro-matches.md).
