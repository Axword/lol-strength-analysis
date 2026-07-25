# R23 HYPOTHESES_PICKED — Path1 lethal2

Auto-picked from F4/F6 + R18 deferrals (no invent; no user choice).

1. **Pre-CUSUM opener retain** — Keep last real killer `skill_used` in `[engage−N, engage)` so Galio W is not dropped when CUSUM fires after the taunt.
2. **Sparse gate** — Only inject opener when post-engage killer marks ≤3 (Galio) so dense Olaf chains do not get early poke.
3. **EngageSec → opener** — When opener retained, gate idle at the real cast (AA filler / pulses start on engage).
4. **Path1 suite wire** — `--suite 2970132-g1` + scorer match from eval `seriesId`.
5. **No product flip without S1 improve** — e5 S1 flat ≠ improve; e7/e10 regress → product `preEngageOpenerSec=0`.
6. **Skip closed tracks** — no flat mark/CUSUM k-h / regen knob sweeps (R07/R08/R09); Criterion G owned by R16/R17.

Deferred: Galio `|lethErr|≤0.75` (best 1.13 with aa-filler); burst 0 marks; Olaf→Camille full `|lethErr|~18` (R19 early / R21 falsekill).
