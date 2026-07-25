# R12 NOTES — planner-death (F4)

## Next action
Absorb summary; no KEEP to merge. Blocker unchanged: check2 path MAE ~323 + check3 full false-kill (actualEndHp=210).

## State
- 11 experiments (e0–e10) on S0 proxy 2970110-g1, product cusum densestride.
- never_edited_parent: true
- Acceptance: 363 combat invariants (death-coupled / front-load weave / low-HP cast) passed.

## Measured fightAgreement (NOT win odds)
| id | FA | pass | note |
|----|-----:|-----:|------|
| e0 | 0.4848 | 0.167 | product baseline (this harness) |
| e7 | 0.4853 | 0.167 | timed_short pulse — tie (+0.0004), not KEEP |
| e4/e5/e6 | 0.4848 | 0.167 | front-load weight / pulse0.25 flat on short pulses |
| e1 | 0.4762 | 0.167 | no finish AA — slight loss |
| e10 | 0.4391 | 0.000 | fixes c3 full false-kill but hard-fails early + misses lethals |
| e2/e3/e8/e9 | ≤0.35 | 0 | worse / hard fails |

STATUS reference product FA 0.4217 was R04 suite scorer; R12 from_eval e0 = 0.4848 on same selector — disclose scorer path, do not claim lift vs STATUS without re-score parity.

## Findings
1. **Death-coupled truncate** already in timed resolve + overlay `hp<=0` break. Trailing finish AA / aa-at-mark removal hurts check1 lethals more than it helps check3.
2. **Front-load weight** has no effect on 0.4s cast pulses (everything is early). Acceptance weave tests still pass at product weight=1.
3. **No HP% ability bans** — `abilityBudget` + timed path (no surviveSec cliffs) confirmed via acceptance.
4. **check3 false-kill** survives product pulses: full window modelEndHp=0 vs actual 210. e10 (no AA pad + share0.65) stops the false-kill but hard-fails check03 early MAE and drops FA.
5. **check2 path MAE** ~323 stuck across product-like knobs — not a planner front-load issue.

## Knobs added (defaults = product)
- `setResearchFrontLoadWeight` / `--front-load-weight`
- `--pulse-mode timed_full|timed_short|physical_aa`
- `--killer-pulse-share`

## Verdict
NO KEEP. Sharper blocker: need mark/pulse honesty that stops survivor overkill without starving true kills / early idle — orthogonal to front-load weight on short pulses.
