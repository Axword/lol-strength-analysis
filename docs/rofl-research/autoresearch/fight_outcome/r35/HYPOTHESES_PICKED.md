# R35 HYPOTHESES_PICKED — preengage-s1safe (wave2)

Auto-picked from R23/R24 residual + C5 V14 blocker (no invent; no user choice).

1. **Sparse maxPost opener** — `preEngageOpenerSec=0.5` + `preEngageOpenerMaxPostMarks=3` retains Galio W (0.334s pre-CUSUM) without dense Olaf early poke.
2. **Far-share ablation** — R24 `lead/far/farShare/maxKillerMarks` restores Galio lethalHit on older law but **regresses S0+S1 under R30** (earlyBand + double-count with idleFollow).
3. **Host-gated variants** — `--pre-engage-host-series 2970132` keeps S1 at product baseline by construction; useful research, but structural sparse already lifts S1 without host ID.
4. **Product KEEP bar** — S0↑ and S1 not regress (FA ≠ odds). Met by e1/e9 sparse opener.
5. **Reject naive lead / far** — e2–e4/e8 drop S0 FA ~0.20; no KEEP.

Deferred: Galio `|lethErr|≤0.75` (best KEEP −1.84); burst 0 marks; far-share under idleFollow.
