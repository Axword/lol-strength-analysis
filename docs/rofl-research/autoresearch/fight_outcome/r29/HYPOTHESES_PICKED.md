# R29 HYPOTHESES — anti-odds-copy (F10)

Auto-picked from `rooms/f10/HYPOTHESES.md` (no human choice):

1. **H1 Wording audit** — "fight outcome agreement ≥95% (kill-window suite)" ≠ win %
   - Result: **KEEP** — Faq section `model-edge-not-odds` discloses fightAgreement as suite agreement, never bookmaker odds / pBlue%.

2. **H2 modelTrust** — calibrated:false visible; freeze-history for 0.9683 unfreeze
   - Result: **PASS_existing** — CombatResult `trust-reasons` DOM + `scope:kill_window_not_calibrated_win_odds`; `best.json` composite **0.9683 untouched** (disclose only).

3. **H3 CombatResult/Faq strip odds-like copy** — model edge only
   - Result: **KEEP** — product CombatResult already clean; stripped engine odds claims in `gameStateOdds.ts` / `combat.ts` comments (`P(blue wins)` / `Fight win odds` → heuristic model-edge); Faq already denied odds % on winner/strength-band/nvm.

Deferred: renaming `FightOdds` / `estimateFightOdds` symbols (API churn, not user copy); Faq `hp-budget` absolute HP% ability-ban wording (out of anti-odds mandate — disclosed in NOTES).
