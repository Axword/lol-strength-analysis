# R24 HYPOTHESES_PICKED — galio-kill (Cycle3)

Auto-picked from R18 deferral + mandate (no invent; no user choice).

1. **CUSUM 1 Hz lag** — Galio W@15.024 sits 0.334s before CUSUM@15.358; product cusum drops the tripping cast → modelEndHp≈306, no kill.
2. **Near pre-engage lead** — keep killer marks in `[engage−lead, engage)` with full share (`--pre-engage-lead 0.4`).
3. **Far pre-engage poke (attenuated)** — keep earlier real skills in `(lead, far]` with disclosed share `<1` (`--pre-engage-far 5 --pre-engage-far-share 0.45`); do not invent events; do not open AA filler before CUSUM.
4. **maxKillerMarks=4** — drop early post-engage spam (helps Olaf path on Path1; hurts S1).
5. **No product KEEP without S1** — any lead/far/maxMarks config that lifts Path1 Galio lethalHit regresses S1 FA 0.5185→~0.34.

Deferred: burst Galio lethalHit (burstStart 502021 is after all Galio skills); Olaf→Camille full |lethErr|~16–18.
