# R10 HYPOTHESES_PICKED — F4 timed-planner

Auto-picked from `rooms/f4/HYPOTHESES.md` (no invent; no user choice).

1. **Death-coupled truncate** — Stop planner at first lethal; no post-death casts.  
   → Exercised via `cusum_gate` / `gate_repin` / `baseline` → `simulateMatchup` → `timed_manual_1v1`.

2. **No HP% ability bans** — Low HP still schedules abilities with survival timing.  
   → Product `abilityBudget` (already shipped); no re-introduction of HP% cliffs.

3. **Utility-only keep** — Nasus W / slows reshape AA counts even at 0 base damage.  
   → Left to product combat utility path; not ablated this session.

4. **Front-loaded scoring** — Avoid AA-pad after first-lethal truncate on long windows.  
   → Product `planRotation` frontLoaded; varied window via `--sim-mode allin|extended|short`.

5. **Engage t=0** — Opener on clock; defender reaction delay; no engageCc abuse.  
   → `--sim-mode short` + CUSUM/skill engage gate (idle until engage).

6. **Parity with Send** — Same timed path as calculator import.  
   → Gated `simulateMatchup` is the Send 1v1 timed path (not mark overlay).

Deferred / blocked: product selector flip (needs S1+S2); hybrid mark+planner finish.
