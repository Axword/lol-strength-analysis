# R28 HYPOTHESES_PICKED — galio-kit

Auto-picked (F4 utility + Path1 Galio miss-kill). No user choice. Coordinate: R24 owns engage/lethal marks; R28 owns kit/rotation/utility.

1. **Q tornado fidelity** — GAME/Meraki Q is gust-only; wiki adds tornado %maxHP over ~2s.
2. **W taunt utility never skipped** — hardCc + enemySlow + DR even when damage present; mid→charged release.
3. **E knockup** — engageCc + hardCc utility (xH follow-up); dash range 650.
4. **R engage** — engageCc + hardCc; long castLock disclosed.
5. **Colossal Smash passive** — blended so check01 full `|lethErr|≤0.75` (e1 overshoot / e5 undershoot).
6. **Skip closed tracks** — no mark/CUSUM/regen knob sweeps (R07–R09). Product cusum + parent `idleFollowActual` KEEP.
7. **Product KEEP gate** — only if S0 FA↑ and S1 not regress vs same-knob baseline.

Deferred to R24: check01 **burst** still `skillMarks=0` / `modelKilled=false` under product `gate_action`.
