# R31 HYPOTHESES_PICKED — galio-burst-product (wave2)

Auto-picked from Cycle5 residual + mandate (no invent; no user choice). FA ≠ odds.

Parent baseline after R30 KEEP: Path1 S0 FA≈0.590; Galio full 2 marks; **c1 burst skillMarks=0** (legacy `detectBurstStartMs` stops at Trundle heal 754→977@502021; all Galio skills earlier).

## Queue (executed)

1. **H1 baseline** — R30 product defaults; c1_burst marks=0, FA≈0.590 / S1≈0.562.
2. **H2 heal-tolerant HP burst onset** — walk through mid-fight heals. Gets marks but destroys Olaf/Camille burst earlyBand/path (S0↓).
3. **H3 pre-engage lead (R24-style)** — restores Galio W on full; Olaf full overkill; S1 regress when far/lead global.
4. **H4 burst-gated pre-engage** — maxEngage≤3 protects Olaf full; HP-onset change still hurts c2/c3 burst.
5. **H5 KEEP — pre-burst skill lead (mark domain only)** — legacy HP burst onset unchanged; load real skills from `[burstStart−lead, end]`, remap onto CUSUM engage.
   - lead **2.5s** @ share **1** → Galio E+Q on burst, `modelKilled`, `|lethErr|=0.635≤0.75`
   - lead **3.5s** (includes W) → S1 regress (NO KEEP)
   - lead **0.5s** (Q only) also KEEP but fewer marks

## KEEP rule

Product KEEP iff S0 FA↑ **and** S1 FA not regress. e40 product defaults meet this.
