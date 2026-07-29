# R15 HYPOTHESES_PICKED — F5 action-coverage / action-wire

Auto-picked all 5 from `rooms/f5/HYPOTHESES.md` (no invent; no user choice).

1. **Honest F1** — GOAL-action-replay-95 match rules; reject zero-dmg log-echo.
   → E0 echo AC=0.904 REJECTED; E1 emitDamaging AC=0.491 eligible secondary.

2. **Secondary only** — actionCoverage is 0.15 of windowScore; never sole gate evidence.
   → FA join uses actionF1 as secondary; lethal/path still dominate fails.

3. **Wire emit proof** — basic_attack/damage_dealt with source+amount PE-proven.
   → `wire_emit_proof.json` PASS on all 6 Path1 windows (R28 AA + R39/R41 damage).

4. **Coverage gaps** — Disclose missing action classes; do not invent.
   → basic_attack has no amount; identity.gateEligible=false; skill marks incomplete vs AA truth.

5. **Suite join** — Feed F1 into fightAgreement scorer when available.
   → E1 joins honest F1; E0 forces actionF1=0 (echo reject).
