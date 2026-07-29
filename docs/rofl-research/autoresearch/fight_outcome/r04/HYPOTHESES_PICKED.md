# R04 — F2 hypotheses auto-picked

Source: `rooms/f2/HYPOTHESES.md` (no invent).

| # | Hypothesis | R04 result |
|---|------------|------------|
| 1 | Baseline measure — implement suite; score S0 before KEEP | **done** — `scripts/fight_agreement_suite.ts`; S0 numbers below |
| 2 | windowOk law (lethal≤0.75, early≤50, burst≤90, full≤130, no invent, hard fails) | **encoded** in `scoreWindow` |
| 3 | windowScore weights 0.40/0.25/0.20/0.15 | **encoded** |
| 4 | Audit JSON under `fight_outcome/audits/` | **done** (failing windows) |
| 5 | S1/S2 wire; no tune on S1 | **S1 measured**; S2 path wired |
| 6 | Product non-drop CUSUM/post_engage; `near_hp_drop` research-only | **enforced** (warn on research selector) |

## S0 numbers (measure-first)

| Selector | fightAgreement | fightPassRate | n |
|----------|---------------:|--------------:|--:|
| product `cusum_engage_then_skills` | **0.4217** | 0.1667 | 6 |
| research-drop BEST (`last_eval`, composite 0.9683) | **0.6018** | 0.3333 | 6 |

S0 host proxied to **2970110-g1** (2970132 crosschecks JSON missing).

## S1 (no tune)

| Selector | fightAgreement | fightPassRate | n |
|----------|---------------:|--------------:|--:|
| product CUSUM | **0.3279** | 0.0000 | 6 |

**fightAgreement ≠ win odds.**
