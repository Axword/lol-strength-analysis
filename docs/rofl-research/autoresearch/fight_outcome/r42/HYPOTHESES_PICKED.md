# R42 HYPOTHESES — c1-burst-earlymae

**Auto-picked** (do not ask human). FA ≠ odds.

## Diagnosis (confirmed)

R31 remaps Galio E+Q onto CUSUM engage at one timestamp. `idleFollowActual` is honest pre-engage; first √T bin still scores the engage dump → earlyMae≈255.5 while marks=2 / |leth|=0.635.

## Results

| id | title | result |
|----|-------|--------|
| H0 | Baseline remesaure | earlyMae 255.5, marks 2, \|leth\| 0.635, S0 FA 0.7740 / S1 0.5810 |
| H1 | earlyMae pre-engage exclusive | KEEP-part: S0 0.8321 / S1 0.5926; pathMae still 127 |
| H2 | Stagger remapped marks | DISCARD — earlyMae stays 255 under legacy metric |
| H3 | Soft share 0.7 | DISCARD — miss-kill |
| H4 | Delay remap 0.1–0.4s | KEEP-part: S0 0.8297 pass 0.500 / S1 flat; path+early clear |
| H5 | Ablate lead=0 | CONTROL — marks 0 |
| H6 | Delay 0.3 + earlyMae pre-engage | **KEEP product** S0 0.8461 / S1 0.5926 |
| H7 | pathFollow/pathClamp | FORBIDDEN for product |

## Product KEEP

`markPreBurstDelaySec=0.3` + harness `earlyMaePreEngageOnly=true`. R31 lead 2.5 / share 1 unchanged.
