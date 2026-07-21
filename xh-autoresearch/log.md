# xH autoresearch log

## Baseline (orchestrator, pre–Pass 1)

- Replaced multiplicative priors with σ-corridor model in `src/engine/xh.ts`
- Eval harness: `npm run eval:xh`
- Fixed: T_avail independent of t_go (fast missile invariant)
- Fixed: far fixture in-range
- **math_pass_rate = 20/20 (1.0000)**

## Pass 1 — all KEEP applied

| Axis | Status | What landed |
|------|--------|-------------|
| geo | KEEP | `interceptTimeGo` + ZEM `lateralMissFromLead` + isotropic 2/π |
| aim | KEEP | Schmidt/SDN σ_aim, lineup T_avail, timing noise; drop blind×1.25 |
| vision | KEEP | LKP geo mean, reachable-set σ_belief, softVision mixture |
| strategy | KEEP | Flash envelope for worst, windup dodge window, ready budgets |
| empirics | KEEP | Analytic equicorrelated-probit `estimateXhm`; extreme-cell eval; `scripts/xh-baselines.ts` |

Bugfix during apply: `Math.SQRT3` → `Math.sqrt(3)` (NaN’d belief σ).

**Post Pass 1: math_pass_rate = 41/41 (1.0000)**

## Pass 2 — all KEEP applied

| Axis | Status | What landed |
|------|--------|-------------|
| vision | KEEP | `softVisionAt` + `resolveCastVisionSoft`; overlay/combat wired; mixture-of-CDFs ∫L b |
| empirics | KEEP | Brier / ability-rate / Platt stubs + kill criteria in eval + baselines |
| geo | KEEP | Explicit lead angle + heading-error miss; `interceptInMissileRange` (drop ×1.05); ability `missileWidth`/`missileSpeed` |
| aim | KEEP | Fitts ID urgency gate; angular ∥ lateral; correction SDN; width-aware `schmidtAimSigma` |
| strategy | KEEP | Precommit residual on worst; `bands.mix` via `neMixCorridorVal`; `flashCdRemainingSec`; combat passes Flash/dash ready |

**Post Pass 2: math_pass_rate = 65/65 (1.0000)**

## Pass 3 — all KEEP applied

| Axis | Status | What landed |
|------|--------|-------------|
| empirics | KEEP | ρ MoM, ECE/CRPS/log-loss, online/strata ability hooks, σ-scale kill probes |
| geo | KEEP | `propagateLosFrame` + `ballisticRayMiss` μ; cast∧reach split; `releaseDelaySec` |
| aim | KEEP | Visuomotor delay + intermittent corr; release–urgency/aperture timing; FoW on σ_corr; U_max |
| vision | KEEP | Fix spotted τ sign; √t + Flash-in-belief + brush cap; softVision→σ_seen |
| strategy | KEEP | Ghost/charges/CC-break; NE unknown→packet mix + π_down; `xhDodgeBand`; hint fix |

**Post Pass 3: math_pass_rate = 88/88 (1.0000)**

## Pass 4 — all KEEP applied

| Axis | Status | What landed |
|------|--------|-------------|
| empirics | KEEP | Platt held-out gain, MCE/adaptive ECE, wrong-ρ/Var/tail CRPS, PIT |
| geo | KEEP | Capsule segment CPA + accel ZEM extra; LOS collapse fix; `missileMaxTravelUu` |
| aim | KEEP | Weber horizon + WK motor/clock split + prep→release; angular floor |
| vision | KEEP | Occupancy slow-growth sat; multi-mean via `beliefMeanSeen`; no_lkp factor |
| strategy | KEEP | CombatResult xH dodge row; MS/CC into estimateXh; smarter `xhDodgeBand` |

**Post Pass 4: math_pass_rate = 103/103 (1.0000)**

## Pass 5 — all KEEP applied

| Axis | Status | What landed |
|------|--------|-------------|
| empirics | KEEP | Temp held-out gain, Murphy REL/RES, count log-loss/ECE, triple-ρ MoM, cond ECE, PIT KS |
| geo | KEEP | `engagementHorizonSec`; lead/μ/accel on `t_eng`; reach vs `Ltravel` |
| aim | KEEP | Weber on `t_go_mis` only; foreperiod `κ_fp·T_prep`; crossing-time clock |
| vision | KEEP | Complete no_lkp (null-geo); soft σ_occ asymptote; combat wards plumbing |
| strategy | KEEP | Shared band aggregator; Ghost live-MS/flag; UI packet-policy highlight |

**Post Pass 5: math_pass_rate = 129/129 (1.0000)**

## Pass 6 — all KEEP applied

| Axis | Status | What landed |
|------|--------|-------------|
| geo | KEEP | `ballisticSegmentCpa` + accel clock delay+`t_cpa`; muSeen ZEM parity |
| aim | KEEP | WK clock ⊥ motor (`σ_c0`); refractory release; mild super-Weber |
| vision | KEEP | Open-loop zone = caster; `softVisionMarginNorm` → σ_seen |
| strategy | KEEP | Fight util into dodge bands; `effectiveTargetMs`; Ghost trusts liveMs |
| empirics | KEEP | Beta calib, Murphy identity+BSS, DSS, PI coverage, ability residual kill |

**Post Pass 6: math_pass_rate = 148/148 (1.0000)**

## Pass 7 — all KEEP applied

| Axis | Status | What landed |
|------|--------|-------------|
| geo | KEEP | `capsuleTravelBudgetUu` — tip/horizon/reach pad = `L+R_hit` |
| aim | KEEP | Clock aperture⊥cross hypot; `σ_r0` refractory; super-foreperiod |
| vision | KEEP | `beliefHypotheses[]` multi-modal; hasBelief∨hypotheses; overlay margin |
| strategy | KEEP | Ghost on raw liveMs; fallback MS; `fightDodgeBands` NvM average |
| empirics | KEEP | Energy + Winkler wrong-ρ kills (landed Pass-6 energy debt) |

**Post Pass 7: math_pass_rate = 158/158 (1.0000)**

## Pass 8 — all KEEP applied

| Axis | Status | What landed |
|------|--------|-------------|
| geo | KEEP | `firstContactTimeGo` — extent clock on `t_eng` (center `t_go` kept for dodge/reach) |
| aim | KEEP | Schmidt⊥Fitts-rush hypot; radial∥timing; `Σ_τvm` delay jitter |
| vision | KEEP | softV⊕hypotheses compose; mixture 2nd-moment σ_belief; FoW-local hyp kinematics |
| strategy | KEEP | Cast multiset `skillshotCastsForFight`; OOR zeros in bands; policy from mix≠typical; missile fields plumbed |
| empirics | KEEP | Isotonic PAV; joint LL; Cox; cond coverage; stratified ability; variogram; Spiegelhalter |

**Post Pass 8: math_pass_rate = 195/195 (1.0000)**

## Pass 9 — all KEEP applied

| Axis | Status | What landed |
|------|--------|-------------|
| geo | KEEP | `ballisticFirstContactSec` accel epoch; muSeen/hyp contact parity |
| aim | KEEP | Corr pulses ∝ D/T; `σ_accel = κ_a·|ZEM|` in σ_aim hypot |
| vision | KEEP | softV-composed σ_belief 2nd moment; Flash-on-lost at softV&lt;0.85 |
| strategy | KEEP | Packet-emission cast multiset; lockedOut into fightDodgeBands |
| empirics | KEEP | ICI, HL χ², spherical, AD-PIT, cond Winkler, quartet ρ, twCRPS |

**Post Pass 9: math_pass_rate = 225/225 (1.0000)**

## Pass 10 (FINAL) — KEEP applied; geo/aim/strategy SKIP

| Axis | Status | What landed |
|------|--------|-------------|
| geo | SKIP | Pass-9 closed last kinematics residual; 2D stadium CDF deferred |
| aim | SKIP | Pass-9 closed corr∝D/T + σ_accel; no further σ_aim residue |
| vision | KEEP | `ageDefault` FoW gate aligned to softV&lt;0.85 (no 0.5 cliff) |
| strategy | SKIP | Pass-9 closed packet multiset + lockedOut; active cell ≡ avgXh |
| empirics | KEEP | Cond ICI, CvM-PIT, pinball, near-miss ρ CRPS, mid-twCRPS |

**Post Pass 10: math_pass_rate = 235/235 (1.0000)** — autoresearch loop complete.
