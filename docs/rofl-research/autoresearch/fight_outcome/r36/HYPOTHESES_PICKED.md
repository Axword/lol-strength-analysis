# R36 HYPOTHESES_PICKED — ally-attrib (wave2)

Auto-picked from R26 handoff + C5 sharper blocker (check03 non-global share).

| id | hypothesis | result |
|----|------------|--------|
| H0 | Remeasure e0 product baseline (R30 KEEP) | MEASURED c3 earlyMae=476 poison Y lethErr≈−18.3 |
| H1 | opener_skill_share (global opener coeff on early marks only) + ally logOnly | PARTIAL earlyMae 100; poison still Y; lethErr −14 |
| H2 | opener_hp_neighborhood | DISCARD earlyMae worse than H1 |
| H3 | opener_skill_share window=10s | DISCARD poison remains; c2 path risk |
| H4 | local_skill_share allyMin5 (per-mark ±2s) | S0 KEEP-shaped (poison clear) but S1 c2 miss-kill |
| H5 | local + allyMin5 + killerMin1 | S0 good; S1 still tiny FAΔ from burst-gate / disclose |
| H6 | disclose allyMarks only when activated | S1 still Δ from burst-shifted opener |
| **H7** | **local_skill_share + allyMin5 + killerMin1 + gate on full windowMs[0]** | **KEEP: S0 FA↑ +0.128; S1 FA flat 0.000** |

Never asked human. Opener vs finish separate. FA ≠ odds.
