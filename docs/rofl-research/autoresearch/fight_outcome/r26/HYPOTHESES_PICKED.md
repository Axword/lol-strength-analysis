# R26 HYPOTHESES_PICKED — check03-poison (auto)

**Suite:** Path1 `2970132-g1-holdout` · product `cusum_engage_then_skills` · `idleFollowActual=true` (R19 KEEP)  
**Owns:** check03 Olaf→Camille full earlyPoisoned residual (earlyMae≈476)  
**Does not own:** Galio miss-kill (R18/R24) · do not one-coefficient early+late  

`false_all_in` / `early_poisoned` = diagnostics only (program.md).

## Auto-picked from program.md queue + failure mode

| # | Hypothesis (one sentence) | Source | Status |
|---|---------------------------|--------|--------|
| H1 | **Multi-caster share:** check03 full is a teamfight; Olaf 1v1 pulses at share=1 overkill Camille at first mark (~1.73s) while actual dies ~20s — apply research `killerPulseShare<1` from measured ally skill pressure (no invent pins). | program #6 | run |
| H2 | **Opener AA honesty:** `aaAtEachMark` stacks physical AA on first engage skill → instant lethal; `--no-aa-at-mark` separates opener overdamage from finish AA (R18 research adjacency; product default unchanged unless S0↑ & S1 flat). | program #4 + R19 handoff | run |
| H3 | **Opener vs finish separate:** early √T bin poison is opener overdamage, not idle freeze (R19 already fixed idle); do not retune finish/regen knobs to mask early (GOAL H). | program + GOAL §H | run (diagnose) |
| H4 | **CUSUM engage vs first-skill:** engageSec≈first Q; if engage detection is late/early vs actual HP cliff, marks misalign — measure only, no near_hp_drop product flip. | program #5 | measure |
| H5 | **Assist-window census (not near-kill only):** `assistProbe` ±2s of kill shows 0 allies, but first 5s has Jarvan/Galio/Seraphine/Shen casting — early poison needs early-window ally census. | diagnostic sharpen | run |

## Skipped (closed / other rooms)

- markMinGap / density / CUSUM K-H / regen sweeps (F3/R07–R09 closed)
- Galio lethal / miss-kill (R18/R24)
- Camille Q wire FA lever (R22; Camille not killer on Path1 S0)
- Inventing HP/items/ranks or S1 tuning

## KEEP bar (mandate)

Product KEEP only if **S0 FA↑** and **S1 not regress**. Research room `best.json` unfreeze 0.9683 OK; do not rewrite parent `best.json` without KEEP proof.
