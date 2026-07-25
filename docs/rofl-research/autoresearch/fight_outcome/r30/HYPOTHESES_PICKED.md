# R30 HYPOTHESES — olaf-lethal-timing

Auto-picked from `program.md` + F3/F4 room queues. **No human choice.**  
Mandate: shrink **Olaf→Trundle** `|lethalErrorSec|` toward ≤0.75. Opener vs finish separate.  
Do **not** duplicate R24/R28 Galio miss-kill or R26 Camille earlyPoisoned.  
Closed: invent pins; S1 tuning; mark/density/regen knob sweeps.

Product KEEP only if **S0 FA↑** AND **S1 not regress**. Selector stays `cusum_engage_then_skills`.

## Queue (advance on failure mode)

1. **H1 Baseline remesaure (FINISH diagnosis)** — Product defaults after R19 idleFollowActual KEEP. Confirm c2 lethErr≈2.81; classify opener vs finish (earlyMae already ≤50 on c2 → finish track).
2. **H2 Death-coupled AA-at-mark suppress (FINISH)** — Replicate R18 e11 (`--no-aa-at-mark`, keep finish-aa) **under idle-follow**. Expect lethErr↓; gate product KEEP on S1 non-regress (R18 S1 regressed pre-idle).
3. **H3 Finish-AA horizon (FINISH)** — Bound trailing AAs near truth kill (`finishAaWindowSec` / finish-aa-max) without global aa-at-mark flip — surgical finish pad cut.
4. **H4 Finish-horizon marks only (FINISH)** — `markFinishHorizonSec` to prefer late marks; no density/gap sweep.
5. **H5 Opener check (OPENER — skip if H1 says finish)** — Only if earlyBand fails on c2; else skip (c2 earlyOk=true).
6. **H6 Combo KEEP candidate** — Best finish combo that lifts S0 FA without S1 regress; else **NO KEEP** + sharper blocker.

Deferred: near_hp_drop; Galio miss-kill; Camille earlyPoisoned; pulse/density/regen sweeps; invent HP/combat/ranks.
