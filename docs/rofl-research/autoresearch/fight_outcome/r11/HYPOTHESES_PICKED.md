# R11 — F4 hypotheses auto-picked (planner-utility)

Source: `rooms/f4/HYPOTHESES.md` (no invent). Mandate slug: **planner-utility**.

| # | Hypothesis | Priority | R11 result |
|---|------------|----------|------------|
| 3 | **Utility-only keep** — Nasus W / slows reshape AA even at 0 base damage | **1 (primary)** | **KEEP_contract** — timed planner no longer skips `utility` / `engageCc` at 0 damage; Spellblade still ignores utility-only casts; probe pass (Nasus W, Zilean E, Camille R extended) |
| 4 | Front-loaded scoring — avoid AA-pad after first-lethal | 2 | **partial** — `UTILITY_PLANNER_PROXY_DAMAGE=12` (env-tunable) so CC schedules; proxy sweep FA-flat on S0 gate_action |
| 1 | Death-coupled truncate — stop at first lethal | 3 | **verified** — existing acceptance + killWindow; no regress |
| 2 | No HP% ability bans | 4 | **verified** — low-HP timed Darius still casts; Nasus W kept |
| 5 | Engage t=0 — opener on clock; defender reaction | 5 | **verified** — existing engage acceptance; untouched |
| 6 | Parity with Send | deferred | Same timed path; FA harness still gate_action mark pulses (not full rotation) |

## Deferred / disclosed

- **Camille Q empty Meraki stub** (`damage: () => []`, no utility/engageCc/attackReset) — still skipped; invent refused. Sharper S0 FA blocker for Q-mark pulses.
- Proxy / wither-cap sweeps: **no FA lift** vs product baseline 0.4217 (gate_action insensitive on S0 kits).

## S0 product FA (cusum_engage_then_skills)

| Config | fightAgreement | fightPassRate |
|--------|---------------:|--------------:|
| R04 baseline / R11 all sweeps | **0.4217** | 0.1667 |

**fightAgreement ≠ win odds.**
