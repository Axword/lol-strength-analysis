# Pass-10 AIM (FINAL) — σ_aim saturated after Pass-9

**Agent:** AIM  
**Baseline:** Post Pass-9 KEEP `math_pass_rate=1.0000` (**225/225**). Landed: corr pulses `u0∝D/T` (not `D/T_OPEN`); `σ_accel=κ_a·|ZEM_accel|` in σ_aim hypot.  
**Scope:** deepen **σ_aim residual only** if any remains. Do **not** touch eval softening; do **not** edit `src/engine/xh.ts` here (orchestrator applies).  
**Hard rule:** no `BASE×ZONE×VISION`; do **not** set `T_avail=t_go`; no dash/Flash in σ_aim.

**Verdict: `SKIP`**

---

## Critique of Pass-9 σ_aim (current `xh.ts`)

Landed `schmidtAimSigma` (~636–689) + timing / σ_aim (~908–996):

```ts
// schmidtAimSigma (Pass-8+9 spatial):
σ_lat  = hypot(κ_lat·(D/T), κ_rush·max(0,U−1))   // Schmidt ⊥ rush
u0     = κ_lat · (D / T)                          // Pass-9: not D/T_OPEN
σ_corr² = Σ_k (κ_c · u0 · ρ^k / dt)² · α_vis²
σ_spatial = hypot(σ₀, σ_lat, σ_ang, σ_corr)

// estimateXh timing (Pass-8) + accel (Pass-9):
σ_t      = hypot(motor, clock, weber, fp, Σ_τvm)
v_time   = hypot(|v_perp|, κ_rad·|v_rad|)
σ_timing = v_time · σ_t
σ_accel  = κ_a · |zemExtra|                       // twin of μ ZEM
σ_aim    = hypot(σ_spatial, σ_timing, σ_accel)
```

Eval / probe evidence (225/225; Pass-9 invariants hold):

| Check | Observed | Residue? |
|-------|----------|----------|
| Pass-9 mono: T=0.9 vs T=0.45 @ U≈1 | **Δσ_aim ≈ −45** (long quieter) | closed — was +31 anti-Fitts sat |
| T-sweep 0.12→1.2 @ W=180, v_perp=40 | **strictly monotone ↓** (390→53) | no anti-Fitts kink remains |
| Pass-9 accel A=0→900 | **Δσ_aim ≈ +2.25** (≥1.5 floor) | closed — was μ-only |
| Snap T=0.14 ≫ lined T=0.9 | 334 vs 65 | N=0 / rush path intact |
| Amply-timed W sweep @ U=1 | W barely moves σ_aim | **not a bug** — Fitts W enters via T★→U and clock aperture; surplus MT plateaus accuracy (Schmidt is D/T) |
| softV α_vis on lined corr | softV↓ lowers σ_corr only (N≥1); snap N=0 bit-identical | FoW→σ_belief, not whole σ_aim — as designed |
| Radial / Σ_τvm / D∧U excess | Pass-8 margins still green | do not reopen |

| Candidate “gap” | Why not Pass-10 KEEP |
|-----------------|----------------------|
| **Amply-timed W silence** | Theory-correct once `T≥T★` (U=1); thin-W asserts already fire on urgency / snap fixtures. Re-stuffing W into σ_lat would reintroduce product-like Fitts glue. |
| **caster_brush ×0.94** | Pre-Pass-1 flat glue; cosmetic cleanup, not a falsifiable math deepen. Removing it risks zone/xH churn without a failing invariant. |
| **κ_a form (Wiener vs κ·\|ZEM\|)** | Pass-9 intentionally twinned μ; swapping to ∫-noise changes levels without a failing check. Calibration, not residue. |
| **\|v_rad\| into T_cross / looming τ** | Explicit Pass-8/9 ban — double-counts `v_time`. |
| **softV on σ_weber/clock/fp/Σ_τvm/σ_accel** | Explicit ban — belief owns FoW. |
| **Already KEEP — do not re-propose** | Fitts ID, τ_vm identity, intermittent N/ρ, U_max, α_vis-on-σ_corr, WK urgency↔motor / aperture↔clock, prep↓motor, Weber-on-`t_go_mis`, κ_fp, crossing log, Σ_θ0, `σ_c0`, `σ_r0`, aperture⊥cross, super-Weber, super-fp, Schmidt⊥rush, radial∥`v_time`, Σ_τvm, `u0∝D/T`, σ_accel, drop ×1.02, lineup≠TOF. Do **not** restore `u0∝D/T_OPEN` or `σ_lat∝urgency`. |

Net: Pass-9 finished the last named AIM residuals. At **225/225** there is **no remaining axis-local σ_aim failure** to deepen without inventing work or reopening landed identities.

---

## Math target

**None.** Hold Pass-9 σ_aim factorization:

```
σ_aim = hypot(σ_spatial(D/T, rush, ang, corr∝D/T), σ_timing(v_time·σ_t), σ_accel)
T_avail = max(T_min, aimTimeSec ?? T_lineup − ΔT_vision)   // still ≠ t_go
```

No copy-paste patch. No new eval invariants on this axis.

---

## Copy-paste patch (for orchestrator → `xh.ts`)

**N/A — SKIP.** Do not modify `schmidtAimSigma` or the σ_aim timing/accel block.

---

## New invariants to add to `scripts/eval-xh-math.ts`

**None** from AIM. Do **not** remove or weaken existing Pass-1…9 AIM checks.

---

## arXiv / literature cites

| Id / ref | Relevance to SKIP |
|----------|-------------------|
| **[1804.05021](https://arxiv.org/abs/1804.05021)** | Aimed-movement phases — Pass-9 already scales secondary pulses with residual primary demand (`D/T`). |
| **[2410.02966](https://arxiv.org/abs/2410.02966)** | OFC+SDN Fitts recovery — mono T-sweep confirms surplus MT no longer inflates We via corr sat. |
| **[2512.17735](https://arxiv.org/abs/2512.17735)** / **[2412.04191](https://arxiv.org/abs/2412.04191)** | Accel as predictive uncertainty — Pass-9 `σ_accel` twin is in place; further form tweaks are calibration. |
| Classic: Schmidt We∝D/T; Meyer / Crossman–Goodeve intermittent; Harris & Wolpert SDN; Bootsma intercept — all represented in landed Pass-1…9 stack. |

---

## Regression note

- **Must hold:** Pass-1…9 Schmidt/Fitts/τ_vm/U_max/FoW-on-σ_corr/WK/Weber/fp/cross/`σ_c0`/`σ_r0`/super-*/Schmidt⊥rush/radial∥timing/Σ_τvm/corr∝D/T/σ_accel; **no** `T_avail=t_go`; D∧U excess ≤500.
- **Risk of forcing a KEEP:** any new spatial×timing cross, softV-on-σ_aim, `|v_rad|→T_cross`, dash/Flash-in-σ_aim, or `T_avail=t_go` would violate hard rules or double-count.
- Do **not** treat amply-timed W silence or brush×0.94 as Pass-10 deepen targets.

---

## What not to do

- Do **not** set `T_avail = t_go` or fold missile speed into Fitts MT / τ_vm.
- Do **not** multiply `BASE_XH × mobility × zone × vision`.
- Do **not** put kit dash/Flash into σ_aim.
- Do **not** re-propose Pass-1…9 AIM KEEP work (including Pass-9 `u0∝D/T` + `σ_accel`).
- Do **not** extend `T_cross` with `|v_rad|` / looming τ.
- Do **not** put softV / FoW scale on σ_weber, σ_clock, σ_fp, Σ_τvm, σ_accel, or whole σ_aim.
- Do **not** restore `u0 = κ·D/T_OPEN` or `σ_lat∝urgency`.
- Do **not** weaken any existing eval invariant.
- Do **not** invent a FINAL-pass patch for optics when the axis is green.

---

## Decision

**`SKIP`**

Pass-9 closed the last falsifiable AIM residues (anti-Fitts corr sat; accel μ-only). Probes at 225/225 show Fitts-monotone T-sweep, healthy accel Δσ, and intact snap/rush/radial/τvm identities. Remaining curiosities are theory-correct (W plateau at U=1) or pre-existing glue (caster_brush×0.94), not KEEP-worthy math deepen. AIM contributes **no patch** and **no new invariants** this final wave — preserve σ² = σ_aim² + σ_juke² + σ_belief² and public API as-is.

---

**Verdict: `SKIP`**
