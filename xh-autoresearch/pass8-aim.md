# Pass-8 AIM — Schmidt⊥Fitts-rush + radial timing + Σ_τvm

**Agent:** AIM  
**Baseline:** Post Pass-7 KEEP `math_pass_rate=1.0000` (158/158). Landed: Fitts/SDN/τ_vm/intermittent/U_max/FoW-σ_corr/WK split/Weber-on-`t_go_mis`/κ_fp/crossing/Σ_θ0/clock⊥motor/`σ_r0`/clock aperture⊥cross/super-Weber/super-fp.  
**Scope:** deepen **σ_aim residual only**. Do **not** touch eval softening; do **not** edit `src/engine/xh.ts` here (orchestrator applies).  
**Hard rule:** no `BASE×ZONE×VISION`; do **not** set `T_avail=t_go`; no dash/Flash in σ_aim.

**Verdict: `KEEP_CANDIDATE`**

---

## Critique of Pass-7 σ_aim (current `xh.ts`)

Landed `schmidtAimSigma` (~573–624) + timing (~851–898):

```ts
// schmidtAimSigma:
σ_lat = κ_lat · (D / T) · urgency          // ← residual product
// estimateXh timing (Pass-7):
σ_motor  = hypot(σ_t0·(1+γ_u(U−1))/(1+λ_prep·T_prep), σ_r0·exp(−T_fb/τ_ref))
σ_clock  = σ_c0·κ_clk·hypot(1, γ_w·aperture, γ_x·cross)
σ_weber  = κ_w·t_go_mis·(1+γ_sw·max(0,t_go_mis−T_wref))
σ_fp     = κ_fp·T_prep·(1+γ_fp·max(0,T_prep−T_fpref))
σ_t      = hypot(motor, clock, weber, fp)
σ_timing = v_perp · σ_t                    // ← radial silent
```

Eval / probe evidence (158/158, margins expose residue):

| Check | Observed | Residue |
|-------|----------|---------|
| Probe: D∧U four-cell excess | `(far∧snap)−(far+snap)` **≈682 uu** | urgency **multiplies** Schmidt `D/T` — invents far×snap coincidence beyond irreducible `D×(1/T)` |
| Probe: head-on / radial Weber | `v_perp→0` ⇒ slow−fast **Δ≈0** even at `|v_rad|=200` | timing miss only via `v_perp`; fleeing/closing LOS never projects TOF/release SD into σ_aim |
| Probe: τ_vm deterministic | `τ_vm` only subtracts from `T_fb` | neuromotor delay is a **random** source (WK / visuomotor jitter); missing base `Σ_τ` in σ_t |

| Residual gap | Why it matters |
|--------------|----------------|
| **Spatial still urgency×(D/T) product** | Pass-2/3 put Fitts haste on σ_lat as `·U`. Schmidt’s law is already `∝D/T`; multiplying by urgency double-counts time-starvation and creates a far∧snap product excess (~682) far above the irreducible Schmidt `D×(1/T)` excess (~426). Same independence move Pass-7 used inside the clock: **hypot**, not product. Rush is an orthogonal tremor / haste floor, not a gain on velocity demand. |
| **Timing projects only through v_perp** | Interceptive error is `|v_rel|·δt` along the relative-velocity direction (Tresilian / Bootsma). Radial flee/close is silent today, so Weber/super-Weber never speak on near-head-on skillshots. |
| **No Σ_τvm in σ_t** | Pass-3 landed deterministic `τ_vm` for feedback budget only. Delay *jitter* (~20–30 ms) is an independent timing source — neither voluntary `releaseJitterSec` nor anticipatory clock aperture. |
| **Already KEEP — do not re-propose** | Fitts ID, τ_vm *identity* (feedback subtract), intermittent N, U_max, α_vis-on-σ_corr, WK urgency↔motor / aperture↔clock *routing*, prep↓motor form, Weber-on-`t_go_mis`, κ_fp *identity*, crossing *log*, Σ_θ0, clock⊥motor `σ_c0`, `σ_r0` refractory, aperture⊥cross hypot, super-Weber, super-fp, drop ×1.02, lineup≠TOF. Do **not** rewrite motor as `·(1+γ_u(U−1))` → different algebraic form unless needed for regression — spatial rush hypot is the product fix. |

Net: Pass-7 finished inside-clock hypot + σ_r0 + super-fp; Pass-8 finishes **spatial urgency independence**, **radial∥timing projection**, and **Σ_τvm** — still inside σ_aim only.

---

## Math target (aim axis only)

```
// Spatial deepen (Pass-8) — keep τ_vm / intermittent / α_vis / Σ_θ0
urgency = min(U_max, (T★/T_avail)^β)
σ_schmidt = κ_lat · (D / T)                         // pure Schmidt velocity
σ_rush    = κ_rush · max(0, urgency − 1)            // Fitts haste floor (uu), ⟂ D/T
σ_lat     = hypot(σ_schmidt, σ_rush)                // NOT · urgency
σ_ang     = hypot(κ_θ · D, Σ_θ0)
σ_corr    = …                                       // unchanged intermittent + α_vis
σ_spatial = hypot(σ₀, σ_lat, σ_ang, σ_corr)

// Timing deepen (Pass-8) — keep Pass-7 motor/clock/weber/fp identities
σ_t0, σ_c0, σ_r0, aperture⊥cross, super-Weber, super-fp   // as landed
Σ_τvm    = 0.024                                    // neuromotor delay jitter (s)
σ_t_eff  = hypot(σ_motor, σ_clock, σ_weber, σ_fp, Σ_τvm)

v_time   = hypot(|v_perp|, κ_rad · |v_rad|)          // relative-velocity projection
σ_timing = v_time · σ_t_eff

σ_aim²   = σ_spatial² + σ_timing²
T_avail  = max(T_min, aimTimeSec ?? T_lineup − ΔT_vision)   // still ≠ t_go
```

- **Schmidt⊥rush:** far∧snap no longer multiplies haste into `D/T`; urgency still gates motor (Pass-3/4 KEEP) and still caps via `U_max`.
- **Radial timing:** flee/close LOS projects the same σ_t through `κ_rad·|v_rad|`; head-on Weber becomes audible without setting `T_avail=t_go`.
- **Σ_τvm:** irreducible delay jitter in the timing hypot — independent of `releaseJitterSec` and clock aperture.
- Angular / corr / FoW-on-σ_corr / WK bases / refractory / super-fp untouched in *form*.

Blind / softV: keep Pass-3 `T_visionCut` + α_vis on σ_corr. Do **not** put softV on σ_weber / σ_clock / σ_fp / Σ_τvm; do **not** reintroduce flat FoW glue on σ_aim.

---

## Copy-paste patch (for orchestrator → `xh.ts`)

### 1) Inside `schmidtAimSigma` — replace lateral line only

```ts
  const urgency = Math.min(U_MAX, Math.pow(Math.max(1, Tstar / T), BETA))
  if (opts?.urgencyOut) opts.urgencyOut.value = urgency

  const KAPPA_RUSH = 90 // uu; Fitts haste floor ⟂ Schmidt D/T
  const sigmaSchmidt = KAPPA_LAT * (D / T)
  const sigmaRush = KAPPA_RUSH * Math.max(0, urgency - 1)
  const sigmaLat = Math.hypot(sigmaSchmidt, sigmaRush)
  const SIGMA_ANG0 = 8
  const sigmaAng = Math.hypot(KAPPA_THETA * D, SIGMA_ANG0)
```

### 2) Timing block in `estimateXh` — extend Pass-7 hypot + radial projection

```ts
  // WK + σ_r0 + super-fp + Σ_τvm + radial timing (NOT T_avail = t_go)
  const sigmaT0 = Math.max(0.02, input.releaseJitterSec ?? 0.045)
  const SIGMA_C0 = 0.036
  const SIGMA_R0 = 0.018
  const SIGMA_TAU = 0.024 // neuromotor delay jitter (s); ⟂ σ_t0 / σ_c0
  const T_prep = Math.max(0, input.releaseDelaySec ?? T_delay)
  const W_REF = 160
  const T_XREF = 0.35
  const V_EPS = 60
  const T_OPEN_AIM = 0.16
  const TAU_VM_AIM = 0.1
  const GAMMA_U = 0.4
  const GAMMA_W = 0.18
  const GAMMA_X = 0.22
  const TAU_REF = 0.22
  const GAMMA_SW = 0.45
  const T_WREF = 0.45
  const GAMMA_FP = 0.55
  const T_FPREF = 0.55
  const KAPPA_CLK = 0.55
  const KAPPA_WEBER = 0.055
  const KAPPA_FP = 0.055
  const LAMBDA_PREP = 1.25
  const KAPPA_RAD = 0.85 // radial∥ timing projection (≤1)
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
    KAPPA_WEBER * tGoMis * (1 + GAMMA_SW * Math.max(0, tGoMis - T_WREF))
  const sigmaFp =
    KAPPA_FP * T_prep * (1 + GAMMA_FP * Math.max(0, T_prep - T_FPREF))
  const sigmaT = Math.hypot(
    sigmaMotor,
    sigmaClock,
    sigmaWeber,
    sigmaFp,
    SIGMA_TAU,
  )
  const vTime = Math.hypot(Math.abs(vPerp), KAPPA_RAD * Math.abs(vRadial))
  const sigmaTiming = vTime * sigmaT

  let sigmaAim = Math.hypot(sigmaSpatial, sigmaTiming)
  if (casterZone === 'brush') {
    sigmaAim *= 0.94
    factors.push('aim:caster_brush')
  }
  factors.push('aim:fitts+sdn+vm+wk+weber+fp+cross+ref+tau+rad+timing')
```

**Calibration knobs (if eval margins shrink):** lower `KAPPA_RUSH` first (60–90) if snap fixtures overshoot; then `KAPPA_RAD` (0.6–0.85) if radial Weber stresses slow-missile overlays; then `SIGMA_TAU` (0.018–0.028). Do **not** restore `σ_lat∝urgency`. Do **not** restore `σ_timing=v_perp·σ_t` only. Do **not** soften eval.

**Expected invariant gains:** D∧U excess drops below ~500 (product fails today at ~682); radial flee + slow missile ⇒ σ_aim ≥ fast at `v_perp≈0`; Σ_τvm keeps a jitter-floor timing presence; Pass-1…7 Schmidt/Fitts/fp/cross/Weber/clock/ref inequalities hold.

---

## New invariants to add to `scripts/eval-xh-math.ts`

Do **not** remove or weaken existing checks. Append after Pass-7 AIM block:

```ts
// --- aim deepen (Pass-8 AIM): Schmidt⊥rush, radial timing, Σ_τvm ---

// Schmidt⊥Fitts-rush: far∧snap must not show product-scale excess
const p8Near = estimateXh(
  base({
    targetPosition: near,
    aimTimeSec: 0.55,
    fittsWidthUu: 180,
    targetPerpVel: 40,
    dashReady: false,
    crowdControlled: true,
  }),
)
const p8Far = estimateXh(
  base({
    targetPosition: far,
    aimTimeSec: 0.55,
    fittsWidthUu: 180,
    targetPerpVel: 40,
    dashReady: false,
    crowdControlled: true,
  }),
)
const p8Snap = estimateXh(
  base({
    targetPosition: near,
    aimTimeSec: 0.14,
    fittsWidthUu: 180,
    targetPerpVel: 40,
    dashReady: false,
    crowdControlled: true,
  }),
)
const p8Both = estimateXh(
  base({
    targetPosition: far,
    aimTimeSec: 0.14,
    fittsWidthUu: 180,
    targetPerpVel: 40,
    dashReady: false,
    crowdControlled: true,
  }),
)
const dD = (p8Far.sigma?.aim ?? 0) - (p8Near.sigma?.aim ?? 0)
const dU = (p8Snap.sigma?.aim ?? 0) - (p8Near.sigma?.aim ?? 0)
const dBoth = (p8Both.sigma?.aim ?? 0) - (p8Near.sigma?.aim ?? 0)
const excessDU = dBoth - dD - dU
assert(
  'Pass-8: D∧U σ_aim excess ≤ Schmidt-irreducible band (not urgency×D/T product)',
  !!p8Near.sigma &&
    !!p8Far.sigma &&
    !!p8Snap.sigma &&
    !!p8Both.sigma &&
    excessDU <= 500,
  `excess=${excessDU.toFixed(1)} both=${dBoth.toFixed(1)} d+u=${(dD + dU).toFixed(1)}`,
)

// Radial timing: head-on flee still hears Weber / TOF
const p8RadFast = estimateXh(
  base({
    aimTimeSec: 0.4,
    releaseDelaySec: 0.25,
    releaseJitterSec: 0.045,
    targetPerpVel: 5,
    targetRadialVel: 220,
    missileSpeed: 2800,
    missileWidth: 160,
    dashReady: false,
    crowdControlled: true,
  }),
)
const p8RadSlow = estimateXh(
  base({
    aimTimeSec: 0.4,
    releaseDelaySec: 0.25,
    releaseJitterSec: 0.045,
    targetPerpVel: 5,
    targetRadialVel: 220,
    missileSpeed: 800,
    missileWidth: 160,
    dashReady: false,
    crowdControlled: true,
  }),
)
assert(
  'Pass-8: radial flee + slow missile → sigma.aim ≥ fast (radial∥timing)',
  !!p8RadSlow.sigma &&
    !!p8RadFast.sigma &&
    p8RadSlow.sigma.aim + 1e-6 >= p8RadFast.sigma.aim,
  `slow=${p8RadSlow.sigma?.aim.toFixed(1)} fast=${p8RadFast.sigma?.aim.toFixed(1)}`,
)
assert(
  'Pass-8: radial Weber margin ≥ 0.4 uu at v_perp≈0 (not silent)',
  !!p8RadSlow.sigma &&
    !!p8RadFast.sigma &&
    p8RadSlow.sigma.aim - p8RadFast.sigma.aim + 1e-6 >= 0.4,
  `Δ=${(p8RadSlow.sigma!.aim - p8RadFast.sigma!.aim).toFixed(2)}`,
)

// Σ_τvm present: factor tag + timing still responds with floor jitter
const p8Tau = estimateXh(
  base({
    aimTimeSec: 0.45,
    releaseJitterSec: 0.02,
    releaseDelaySec: 0.2,
    targetPerpVel: 420,
    dashReady: false,
    crowdControlled: true,
  }),
)
assert(
  'Pass-8: factors expose tau+rad aim path',
  p8Tau.factors.some((f) => f.includes('tau') && f.includes('rad')),
  p8Tau.factors.join(','),
)
assert(
  'Pass-8: factors expose T_avail (lineup)',
  p8Tau.factors.some((f) => f.startsWith('T_avail:')),
  p8Tau.factors.join(','),
)
```

---

## arXiv / literature cites

| Id / ref | Use in Pass-8 model |
|----------|---------------------|
| **[2410.02966](https://arxiv.org/abs/2410.02966)** | OFC+SDN recovers Fitts — justifies urgency as a **separate** haste source, not a gain multiplying Schmidt `D/T`. |
| **[2110.11130](https://arxiv.org/abs/2110.11130)** | Inverse OFC + SDN — command-dependent velocity noise (Schmidt) ⊥ planning/haste residuals (rush floor). |
| **[2512.17735](https://arxiv.org/abs/2512.17735)** | Interceptive timing under prediction horizon — timing SD projects through relative motion, including radial close/flee. |
| **[2412.04191](https://arxiv.org/abs/2412.04191)** | Predictive intercept / forward models — uncompensated TOF residual along the engagement axis, not only isotropic strafe. |
| **[1804.05021](https://arxiv.org/abs/1804.05021)** | Aimed-movement phases — visuomotor delay is stochastic; deterministic τ_vm for `T_fb` stays, **Σ_τvm** enters release timing variance. |
| Classic (comment cites): Schmidt et al. 1979 (We∝D/T, no Fitts gain); Tresilian / Bootsma & van Wieringen (coincidence anticipation along `v_rel`); Wing & Kristofferson 1973 (delay jitter as independent timing source); Harris & Wolpert SDN. |

---

## Regression note

- **Must hold:** Pass-1…7 Schmidt/Fitts/τ_vm/U_max/FoW-on-σ_corr/WK routing/Weber-on-`t_go_mis`/fp U-shape/crossing/clock⊥motor/`σ_r0`/aperture⊥cross/super-Weber/super-fp; **no** `T_avail=t_go`.
- **Risk:** `KAPPA_RUSH` too large → snap fixtures approach old product blow-up; keep rush as floor (~90 uu at U=2 ≈ 90, vs product adding hundreds×). Prefer **KAPPA_RUSH∈[60,110]**.
- **Risk:** `KAPPA_RAD` too large → radial flee + slow missile tanks xH on overlay; watch calibration. Prefer **0.6–0.85**.
- **Risk:** `SIGMA_TAU` too large → timing floor drowns prep↓motor / thin−wide clock margins; cut τ before touching Fitts knobs.
- **Risk:** D∧U assert threshold `500` allows irreducible Schmidt `D×(1/T)` excess (~420–430) and rejects product (~680+). Pre-fix product must fail until patch lands.
- **Risk:** Radial fixtures must stay in cast∧reach range (near pose, `missileWidth` pad); if OOR, nudge speed/width — do not soften assert.
- Do **not** stack `(1+α t_go)` on whole σ_t; do **not** put rush multiply back onto `D/T`; do **not** fold missile speed into Fitts MT.

---

## What not to do

- Do **not** set `T_avail = t_go` or fold missile speed into Fitts MT / τ_vm.
- Do **not** multiply `BASE_XH × mobility × zone × vision`.
- Do **not** put kit dash/Flash into σ_aim.
- Do **not** re-propose Pass-1…7 Fitts/SDN/τ_vm/intermittent/U_max/α_vis/WK *routing*/prep↓motor/Weber-on-`t_go_mis`/κ_fp/crossing/`σ_c0`/`σ_r0`/aperture⊥cross/super-Weber/super-fp — only Schmidt⊥rush, radial timing, Σ_τvm.
- Do **not** put softV / FoW scale on σ_weber, σ_clock, σ_fp, Σ_τvm, or whole σ_aim.
- Do **not** weaken any existing eval invariant.

---

## Decision

**`KEEP_CANDIDATE`**

Axis-local deepen of Pass-7 spatial/timing residual: detach Fitts haste from Schmidt velocity (**σ_lat = hypot(D/T, rush)**), project timing through **radial∥v_perp**, and add neuromotor **Σ_τvm** into the timing hypot. Adds falsifiable invariants (esp. D∧U excess cap that current product fails; radial Weber at `v_perp≈0`); preserves σ² = σ_aim² + σ_juke² + σ_belief² and public API. Orchestrator: patch `schmidtAimSigma` lateral + timing block only, append invariants, reject only if `math_pass_rate` drops.

---

**Verdict: `KEEP_CANDIDATE`**
