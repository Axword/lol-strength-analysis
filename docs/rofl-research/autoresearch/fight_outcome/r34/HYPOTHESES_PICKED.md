# R34 HYPOTHESES_PICKED — s0-passrate

Auto-picked (no human choice). Mandate: raise S0 `fightPassRate` toward 0.95; KEEP iff S0 pass↑ and S1 not regress. FA ≠ odds.

| ID | Hypothesis | Result |
|----|------------|--------|
| H0 | Remeasure R30 baseline S0 FA≈0.59 / pass 0.333; audit failing windows | MEASURED |
| H1 | Soften finish-AA max → cut c2_burst pathMae | DISCARD (c2 path unchanged; Galio lose kill) |
| H2 | Soften per-slot E/Q pulses → cut c2 pathMae | DISCARD (pulse saturates; MAE identical) |
| H3 | Thin marks / finish-horizon / near-kill | DISCARD (pass↓) |
| H4 | Uncapped aa-at-mark restores Galio lethal | DISCARD product (Olaf \|lethErr\| 0.33→1.14; trade windows) |
| H5 | Cap aa-at-mark (max 1–2) + skip zero-pulse | DISCARD product (Olaf still breaks at max1) |
| H6 | Galio tornadoPct 0.15 (wiki~0.10 blend) | **KEEP** — c1_full windowOk; S0 pass 0.333→0.500; S1 FA flat |
| H7 | c2_burst pathMae 117→≤90 without leth regress | BLOCKED this wave (pulse/finish no-ops; residual handoff) |

## Passability rank (pre-KEEP)

1. **c2_burst** — only pathMae (117.7>90); score 0.904 — closest but pulse-insensitive
2. **c1_full** — only lethal (+2.61>0.75); path+early OK — **flipped by H6**
3. **c1_burst** — 0 marks (burstStart after skills)
4. **c3_full** — earlyPoisoned (R26 S1-colliding share)
