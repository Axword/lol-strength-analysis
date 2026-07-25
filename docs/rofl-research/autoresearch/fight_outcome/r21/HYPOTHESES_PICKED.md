# R21 HYPOTHESES PICKED — path1-falsekill

Auto-picked (no human multiple-choice). Skipped closed mark/regen knob sweeps.

| id | Hypothesis | Result |
|----|------------|--------|
| H1 | Continuous 0.4s full-DPS pulse overkills (root cause of R12 c3 actualEndHp=210 FK + Path1 early-lethal) | **Confirmed**: smoke Olaf→Camille continuous≈832 HP / slot Q≈224 |
| H2 | `pulseMode=slot_ability` (kit Q/W/E/R only) stops survivor FK | Partial: alone still FK with AA pad; with noAA stops FK but hard-fails early / starves lethals |
| H3 | R19 coord: `idleFollowActual` clears early hard-fail when paired with slot_ability | **Confirmed** on e11/e14 (early hardFail cleared vs e4) |
| H4 | e14 recipe: slot_ability + idleFollow + noAA + share0.55 stops 2970110 c3 FK | **FK 0.5→0**; starves c1/c2 lethals (R18 conflict); S1 FA drops |
| H5 | e8 Path1: slot_ability + idleFollow + aaFiller lifts Path1 suite FA | Path1 suite FA 0.2946→0.556; does **not** stop 2970110 FK; S1 worsens → no product KEEP |

Deferred to R18/R19: lethal restore under FK-safe pulse; early-band product default for idleFollow.
