# Pass-7 AIM — clock aperture⊥cross + σ_r0 refractory + super-foreperiod

**Agent:** AIM  
**Baseline:** Post Pass-6 KEEP `math_pass_rate=1.0000` (148/148). Landed: Fitts/SDN/τ_vm/intermittent/U_max/FoW-σ_corr/WK split/Weber-on-`t_go_mis`/κ_fp/crossing/Σ_θ0/clock⊥motor/`σ_ref`/mild super-Weber.  
**Scope:** deepen **σ_aim residual only**. Do **not** touch eval softening; do **not** edit `src/engine/xh.ts` here (orchestrator applies).  
**Hard rule:** no `BASE×ZONE×VISION`; do **not** set `T_avail=t_go`; no dash/Flash in σ_aim.

**Verdict: `KEEP_CANDIDATE`**

---

## Critique of Pass-6 σ_aim (current `xh.ts`)

Landed `schmidtAimSigma` (~554–…) + timing (~824–866):

```ts
// schmidtAimSigma: Fitts∩U_max, τ_vm, intermittent N, α_vis on σ_corr, Σ_θ0 ✓
// estimateXh timing (Pass-6):
σ_motor  = hypot(σ_t0·(1+γ_u(U−1))/(1+λ_prep·T_prep), σ_t0·γ_ref·exp(−T_fb/τ_ref))
σ_clock  = σ_c0·κ_clk·(1+γ_w·aperture)·(1+γ_x·cross)   // ← residual product
σ_weber  = κ_w·t_go_mis·(1+γ_sw·max(0,t_go_mis−T_wref))
σ_fp     = κ_fp·T_prep                                  // ← residual linear
σ_t      = hypot(motor, clock, weber, fp)
σ_timing = v_perp·σ_t
```

Eval / probe evidence (148/148, margins expose residue):

| Check | Observed | Residue |
|-------|----------|---------|
| Pass-5 U-shape long≥mid | `137.9` vs `137.8` | **Δ≈0.1 uu** — linear κ_fp still drowned / cancelled |
| Pass-6 clock⊥motor gap@jitter | ratio `≈0.99` | motor⊥clock bases OK; **inside-clock** product remains |
| Probe: ap+cross interaction excess | both−neither exceeds (ap−neither)+(cr−neither) by **~0.47 uu** | aperture×cross **product** invents non-additive coincidence demand |
| Probe: σ_ref∝σ_t0 | starve Δjit `1.2` vs rich `2.7` (spatial-confounded) | open-loop release residue still **scaled by voluntary jitter** |

| Residual gap | Why it matters |
|--------------|----------------|
| **Clock still aperture×cross product** | Pass-6 split motor⊥clock bases, but left `(1+γ_w a)·(1+γ_x c)` inside σ_clock. Wing–Kristofferson / coincidence gates: **spatial aperture** and **crossing-time** are independent anticipatory variance sources. Product over-counts thin∧fast and fails the additive (hypot) null that motor⊥clock already adopted across channels. |
| **Refractory still slave to σ_t0** | `σ_ref=σ_t0·γ_ref·exp(−T_fb/τ_ref)` ties unfinished intermittent residue to release-jitter knob. Harris dual-submovement / event-driven pulses: open-loop go-signal residue has its own base **σ_r0**, orthogonal to voluntary `releaseJitterSec`. When jitter→floor, Pass-6 under-noises snap releases relative to the intermittent story. |
| **Linear foreperiod still razor-thin** | Pass-5/6 `κ_fp·T_prep` yields ~0.05–0.1 uu long−mid on the U-shape fixture — same drowning Pass-6 fixed for Weber with mild super-linear growth. Niemi–Näätänen / SET: long predictable foreperiods accumulate **super-linear** trigger-interval CV drift. Mirror Pass-6: `·(1+γ_fp·max(0,T_prep−T_fpref))` on σ_fp only. |
| **Already KEEP — do not re-propose** | Fitts ID, τ_vm, intermittent N, U_max, α_vis-on-σ_corr, WK urgency↔motor / aperture↔clock *routing*, prep↓motor form, Weber-on-`t_go_mis`, κ_fp *identity*, crossing-time *log gate*, Σ_θ0, clock⊥motor `σ_c0`, refractory *exp form*, mild super-Weber, drop ×1.02, lineup≠TOF. |

Net: Pass-6 closed WK **base** independence + refractory *shape* + super-Weber; Pass-7 finishes **inside-clock hypot**, **refractory base ⊥ σ_t0**, and **super-foreperiod** — still inside σ_aim only.

---

## Math target (aim axis only)

```
// Spatial (unchanged Pass-3…6 structure)
urgency = min(U_max, (T★/T_avail)^β)
σ_spatial = schmidtAimSigma(D, T_avail, W, {softVision, urgencyOut})  // as landed

// Timing deepen (Pass-7) — keep Pass-6 σ_c0 / Weber / T_fb identities
σ_t0     = max(0.02, releaseJitterSec)          // MOTOR base only
σ_c0     = 0.036                                 // CLOCK base (s), ⟂ σ_t0
σ_r0     = 0.018                                 // REFRACTORY base (s), ⟂ σ_t0
T_prep   = max(0, releaseDelaySec)
aperture = max(0, log(W_ref / W_eff))
T_cross  = W_eff / max(|v_perp|, v_eps)
cross    = max(0, log(T_xref / max(T_cross, eps)))

T_OPEN = 0.16;  τ_vm = 0.1                       // match schmidtAimSigma
T_fb   = max(0, T_avail − T_OPEN − τ_vm)
σ_ref  = σ_r0 · exp(−T_fb / τ_ref)               // NOT ×σ_t0

σ_motor  = hypot(σ_t0·(1+γ_u·(urgency−1))/(1+λ_prep·T_prep), σ_ref)
σ_clock  = σ_c0 · κ_clk · hypot(1, γ_w·aperture, γ_x·cross)  // aperture ⊥ cross
σ_weber  = κ_w · t_go_mis · (1 + γ_sw · max(0, t_go_mis − T_wref))  // unchanged
σ_fp     = κ_fp · T_prep · (1 + γ_fp · max(0, T_prep − T_fpref))
σ_t_eff  = hypot(σ_motor, σ_clock, σ_weber, σ_fp)

σ_timing = v_perp · σ_t_eff
σ_aim²   = σ_spatial² + σ_timing²

T_avail = max(T_min, aimTimeSec ?? T_lineup − ΔT_vision)   // still ≠ t_go
```

- **Clock hypot:** thin∧fast no longer multiplies aperture×cross; components add in quadrature under shared `σ_c0·κ_clk`.
- **σ_r0 refractory:** snap / starved `T_fb` keep release residue as jitter→floor; feedback-rich still decays via `exp(−T_fb/τ_ref)`.
- **Super-foreperiod:** very-long prep widens σ_fp faster than linear — healthier long≥mid margin; short/mid prep unchanged at first order.
- Spatial helper / angular floor / FoW-on-σ_corr / Weber / cross log-gate / motor⊥clock bases untouched in *form*.

Blind / softV: keep Pass-3 `T_visionCut` + α_vis on σ_corr. Do **not** put softV on σ_weber / σ_clock / σ_fp; do **not** reintroduce flat FoW glue on σ_aim.

---

## Copy-paste patch (for orchestrator → `xh.ts`)

Replace **only** the Wing–Kristofferson + Weber timing block inside `estimateXh` (keep `schmidtAimSigma` as-is):

```ts
  // WK clock hypot + σ_r0 refractory + super-foreperiod (NOT T_avail = t_go)
  const sigmaT0 = Math.max(0.02, input.releaseJitterSec ?? 0.045)
  const SIGMA_C0 = 0.036 // anticipatory clock base (s); independent of releaseJitter
  const SIGMA_R0 = 0.018 // ≈ Pass-6 default σ_t0·γ_ref; ⟂ sigmaT0
  const T_prep = Math.max(0, input.releaseDelaySec ?? T_delay)
  const W_REF = 160
  const T_XREF = 0.35
  const V_EPS = 60
  const T_OPEN_AIM = 0.16 // match schmidtAimSigma open-loop phase
  const TAU_VM_AIM = 0.1
  const GAMMA_U = 0.4
  const GAMMA_W = 0.18
  const GAMMA_X = 0.22
  const TAU_REF = 0.22
  const GAMMA_SW = 0.45 // mild super-Weber above T_wref (Pass-6)
  const T_WREF = 0.45
  const GAMMA_FP = 0.55 // mild super-foreperiod above T_fpref
  const T_FPREF = 0.55 // s; onset of long-prep CV drift
  const KAPPA_CLK = 0.55
  const KAPPA_WEBER = 0.055
  const KAPPA_FP = 0.055
  const LAMBDA_PREP = 1.25
  const apertureTerm = Math.max(0, Math.log(W_REF / Math.max(40, W_eff)))
  const T_cross = W_eff / Math.max(Math.abs(vPerp), V_EPS)
  const crossTerm = Math.max(0, Math.log(T_XREF / Math.max(T_cross, 1e-3)))
  const T_fbAim = Math.max(0, T_avail - T_OPEN_AIM - TAU_VM_AIM)
  const sigmaRef = SIGMA_R0 * Math.exp(-T_fbAim / TAU_REF)
  const sigmaMotor = Math.hypot(
    (sigmaT0 * (1 + GAMMA_U * (urgency - 1))) / (1 + LAMBDA_PREP * T_prep),
    sigmaRef,
  )
  const sigmaClock =
    SIGMA_C0 *
    KAPPA_CLK *
    Math.hypot(1, GAMMA_W * apertureTerm, GAMMA_X * crossTerm)
  const sigmaWeber =
    KAPPA_WEBER *
    tGoMis *
    (1 + GAMMA_SW * Math.max(0, tGoMis - T_WREF))
  const sigmaFp =
    KAPPA_FP * T_prep * (1 + GAMMA_FP * Math.max(0, T_prep - T_FPREF))
  const sigmaT = Math.hypot(sigmaMotor, sigmaClock, sigmaWeber, sigmaFp)
  const sigmaTiming = vPerp * sigmaT

  let sigmaAim = Math.hypot(sigmaSpatial, sigmaTiming)
  if (casterZone === 'brush') {
    sigmaAim *= 0.94
    factors.push('aim:caster_brush')
  }
  factors.push('aim:fitts+sdn+vm+wk+weber+fp+cross+ref+timing')
```

**Calibration knobs (if eval margins shrink):** lower `GAMMA_FP` first (0.35–0.55), then raise `SIGMA_R0` slightly if snap refractory margin collapses at floor jitter, then bump `GAMMA_W`/`GAMMA_X` if thin−wide / crossing asserts lose margin after product→hypot. Do **not** restore `(1+γ_w a)·(1+γ_x c)`. Do **not** restore `σ_ref∝σ_t0`. Do **not** soften eval.

**Expected invariant gains:** ap+cross interaction ≤ additive null (hypot); floor-jitter starved≥rich refractory still holds; long−mid foreperiod margin ≥0.5 uu; Pass-1…6 Schmidt/Fitts/fp/cross/Weber/clock⊥motor inequalities hold.

---

## New invariants to add to `scripts/eval-xh-math.ts`

Do **not** remove or weaken existing checks. Append after Pass-6 AIM block:

```ts
// --- aim deepen (Pass-7 AIM): clock aperture⊥cross, σ_r0 refractory, super-fp ---

// Clock hypot: aperture∧cross must be subadditive (no product excess)
const p7Neither = estimateXh(
  base({
    fittsWidthUu: 220,
    targetPerpVel: 80,
    aimTimeSec: 0.5,
    releaseDelaySec: 0.3,
    releaseJitterSec: 0.04,
    dashReady: false,
    crowdControlled: true,
  }),
)
const p7Ap = estimateXh(
  base({
    fittsWidthUu: 50,
    targetPerpVel: 80,
    aimTimeSec: 0.5,
    releaseDelaySec: 0.3,
    releaseJitterSec: 0.04,
    dashReady: false,
    crowdControlled: true,
  }),
)
const p7Cr = estimateXh(
  base({
    fittsWidthUu: 220,
    targetPerpVel: 600,
    aimTimeSec: 0.5,
    releaseDelaySec: 0.3,
    releaseJitterSec: 0.04,
    dashReady: false,
    crowdControlled: true,
  }),
)
const p7Both = estimateXh(
  base({
    fittsWidthUu: 50,
    targetPerpVel: 600,
    aimTimeSec: 0.5,
    releaseDelaySec: 0.3,
    releaseJitterSec: 0.04,
    dashReady: false,
    crowdControlled: true,
  }),
)
const dAp = (p7Ap.sigma?.aim ?? 0) - (p7Neither.sigma?.aim ?? 0)
const dCr = (p7Cr.sigma?.aim ?? 0) - (p7Neither.sigma?.aim ?? 0)
const dBoth = (p7Both.sigma?.aim ?? 0) - (p7Neither.sigma?.aim ?? 0)
assert(
  'Pass-7: aperture∧cross σ_aim excess ≤ additive (clock hypot, not product)',
  !!p7Neither.sigma &&
    !!p7Ap.sigma &&
    !!p7Cr.sigma &&
    !!p7Both.sigma &&
    dBoth <= dAp + dCr + 0.15,
  `both=${dBoth.toFixed(2)} ap+cr=${(dAp + dCr).toFixed(2)} excess=${(dBoth - dAp - dCr).toFixed(2)}`,
)

// Refractory base ⊥ σ_t0: at floor jitter, starved T_fb still ≥ rich lineup
const p7StarveFloor = estimateXh(
  base({
    aimTimeSec: 0.14,
    fittsWidthUu: 200,
    releaseJitterSec: 0.02,
    releaseDelaySec: 0.2,
    targetPerpVel: 450,
    dashReady: false,
    crowdControlled: true,
  }),
)
const p7RichFloor = estimateXh(
  base({
    aimTimeSec: 0.55,
    fittsWidthUu: 200,
    releaseJitterSec: 0.02,
    releaseDelaySec: 0.2,
    targetPerpVel: 450,
    dashReady: false,
    crowdControlled: true,
  }),
)
assert(
  'Pass-7: floor jitter + starved T_fb → sigma.aim ≥ rich (σ_r0 refractory)',
  !!p7StarveFloor.sigma &&
    !!p7RichFloor.sigma &&
    p7StarveFloor.sigma.aim + 1e-6 >= p7RichFloor.sigma.aim,
  `starve=${p7StarveFloor.sigma?.aim.toFixed(1)} rich=${p7RichFloor.sigma?.aim.toFixed(1)}`,
)

// Super-foreperiod: very-long prep ≥ mid with visible margin (not 0.05 uu tie)
const p7FpMid = estimateXh(
  base({
    aimTimeSec: 0.4,
    releaseDelaySec: 0.4,
    releaseJitterSec: 0.08,
    targetPerpVel: 480,
    targetMovespeed: 480,
    dashReady: false,
    crowdControlled: true,
  }),
)
const p7FpLong = estimateXh(
  base({
    aimTimeSec: 0.4,
    releaseDelaySec: 1.25,
    releaseJitterSec: 0.08,
    targetPerpVel: 480,
    targetMovespeed: 480,
    dashReady: false,
    crowdControlled: true,
  }),
)
assert(
  'Pass-7: very-long prep → sigma.aim ≥ mid (super-foreperiod)',
  !!p7FpLong.sigma &&
    !!p7FpMid.sigma &&
    p7FpLong.sigma.aim + 1e-6 >= p7FpMid.sigma.aim,
  `long=${p7FpLong.sigma?.aim.toFixed(1)} mid=${p7FpMid.sigma?.aim.toFixed(1)}`,
)
assert(
  'Pass-7: long−mid foreperiod margin ≥ 0.5 uu (not spatial-drowned tie)',
  !!p7FpLong.sigma &&
    !!p7FpMid.sigma &&
    p7FpLong.sigma.aim - p7FpMid.sigma.aim + 1e-6 >= 0.5,
  `Δ=${(p7FpLong.sigma!.aim - p7FpMid.sigma!.aim).toFixed(2)}`,
)

// Guard: factor tag + T_avail still lineup
assert(
  'Pass-7: factors expose T_avail (lineup)',
  p7FpMid.factors.some((f) => f.startsWith('T_avail:')),
  p7FpMid.factors.join(','),
)
assert(
  'Pass-7: aim factor tag mentions ref path',
  p7FpMid.factors.some((f) => f.includes('ref')),
  p7FpMid.factors.join(','),
)
```

---

## arXiv / literature cites

| Id / ref | Use in Pass-7 model |
|----------|---------------------|
| **[2110.11130](https://arxiv.org/abs/2110.11130)** | Inverse OFC + SDN — motor / go-signal noise separate from anticipatory clock; motivates keeping clock components as **independent** variance (hypot), not a fused product. |
| **[2103.08558](https://arxiv.org/abs/2103.08558)** | Intermittent corrective impulses / dual-submovement — unfinished pulse-train residue into release is its own source (**σ_r0**), not scaled by voluntary release jitter. |
| **[1903.05534](https://arxiv.org/abs/1903.05534)** | Event-driven sensorimotor control — discrete correction epochs; open-loop residue between last pulse and trigger has amplitude set by the pulse train, not by `releaseJitterSec`. |
| **[1804.05021](https://arxiv.org/abs/1804.05021)** | Aimed-movement phases — ballistic then feedback; starved `T_fb` never reaches low-variance feedback regime (refractory base remains). |
| **[2512.17735](https://arxiv.org/abs/2512.17735)** | Interceptive timing under prediction horizon — long timed intervals show CV drift; supports mild **super-foreperiod** on `T_prep` analogous to Pass-6 super-Weber on `t_go_mis`. |
| Classic (comment cites): Wing & Kristofferson 1973 (independent clock sources → hypot not product); Niemi & Näätänen 1981 (foreperiod); Gibbon SET (scalar timing / long-interval CV); Bootsma & van Wieringen / Tresilian (aperture vs crossing-time as separable coincidence gates); Harris & Wolpert SDN. |

---

## Regression note

- **Must hold:** Pass-1…6 Schmidt/Fitts/τ_vm/U_max/FoW-on-σ_corr/WK routing/Weber-on-`t_go_mis`/fp U-shape/crossing/clock⊥motor/refractory shape/super-Weber; **no** `T_avail=t_go`.
- **Risk:** `GAMMA_FP` too large → very-long prep may stress Pass-4/5 `long≤snap` on default fixtures; keep γ_fp mild and `T_fpref≈0.55` so mid (0.4 s) is untouched.
- **Risk:** `SIGMA_R0` too large → snap fixtures over-inflate beyond Fitts urgency; cut σ_r0 before touching Fitts knobs. Prefer **SIGMA_R0∈[0.014, 0.028]**; default **0.018** ≈ Pass-6 `0.045×0.32` at stock jitter (independence without level jump). Raise toward 0.028 only if floor-jitter refractory margin is soft.
- **Risk:** hypot clock lowers thin∧fast vs product — thin−wide / crossing asserts may lose margin; raise `GAMMA_W`/`GAMMA_X` slightly (≤0.28) before restoring product.
- **Risk:** Subadditivity assert uses `+0.15` cushion for spatial/Fitts leakage into the four-cell probe; pre-fix product excess ~0.47 must fail until patch lands.
- Do **not** stack `(1+α t_go)` multiplier on whole σ_t; do **not** put refractory inside `schmidtAimSigma` return (keep spatial helper API stable — recompute `T_fb` locally).

---

## What not to do

- Do **not** set `T_avail = t_go` or fold missile speed into Fitts MT / τ_vm.
- Do **not** multiply `BASE_XH × mobility × zone × vision`.
- Do **not** put kit dash/Flash into σ_aim.
- Do **not** re-propose Pass-1…6 Fitts/SDN/τ_vm/intermittent/U_max/α_vis/WK *routing*/prep↓motor/Weber-on-`t_go_mis`/κ_fp *identity*/crossing *log form*/`σ_c0` split/refractory *exp*/super-Weber — only clock hypot, σ_r0 base, super-fp.
- Do **not** put softV / FoW scale on σ_weber, σ_clock, σ_fp, or whole σ_aim.
- Do **not** weaken any existing eval invariant.

---

## Decision

**`KEEP_CANDIDATE`**

Axis-local deepen of Pass-6 timing residual: finish Wing–Kristofferson inside the clock (**aperture⊥crossing hypot**), detach intermittent→release residue onto **σ_r0 ⟂ σ_t0**, and mild **super-foreperiod** on long `T_prep`. Adds falsifiable invariants (esp. subadditive ap∧cross that current product fails; long−mid margin ≥0.5); preserves σ² = σ_aim² + σ_juke² + σ_belief² and public API. Orchestrator: patch timing block only, append invariants, reject only if `math_pass_rate` drops.

---

**Verdict: `KEEP_CANDIDATE`**
