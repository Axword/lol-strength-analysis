# Pass-5 AIM — post-release Weber + foreperiod + crossing-time aperture

**Agent:** AIM  
**Baseline:** Post Pass-4 KEEP `math_pass_rate=1.0000` (103/103). Landed: Fitts/SDN/τ_vm/intermittent/U_max/FoW-σ_corr/Weber/WK/prep/angular floor.  
**Scope:** deepen **σ_aim residual only**. Do **not** touch eval softening; do **not** edit `src/engine/xh.ts` here (orchestrator applies).  
**Hard rule:** no `BASE×ZONE×VISION`; do **not** set `T_avail=t_go`; no dash/Flash in σ_aim.

**Verdict: `KEEP_CANDIDATE`**

---

## Critique of Pass-4 σ_aim (current `xh.ts`)

Landed `schmidtAimSigma` (~475–526) + timing (~731–753):

```ts
// schmidtAimSigma: Fitts∩U_max, τ_vm, intermittent N, α_vis on σ_corr, Σ_θ0 floor ✓
// estimateXh timing:
σ_motor  = σ_t0·(1+γ_u(U−1))/(1+λ_prep·T_prep)
σ_clock  = σ_t0·κ_clk·(1+γ_w·log(W_ref/W))
σ_weber  = κ_w · t_go          // t_go = T_delay + t_go_mis  ← residual
σ_t     = hypot(motor, clock, weber)
σ_timing = v_perp · σ_t
```

Eval evidence (103/103, but margins expose residue):

| Check | Observed | Residue |
|-------|----------|---------|
| Pass-4 Weber slow≥fast | `136.6` vs `136.4` | κ_w·Δt_go ≈ noise; horizon drowned by σ_spatial |
| Pass-4 prep long≤snap | `158.1` vs `158.1` | **exact tie** — prep↓motor cancelled by Weber↑ on `T_delay` inside `t_go` |

| Residual gap | Why it matters |
|--------------|----------------|
| **Weber on full `t_go` double-counts windup** | `T_prep` already shrinks σ_motor (Pass-4). Folding the same `releaseDelaySec` into `σ_weber=κ_w·(T_delay+t_go_mis)` **inflates** horizon as prep lengthens → net σ_aim flat. Coincidence-anticipation / SET times the **intercept interval after release**, not committed cast windup. Still **not** `T_avail=t_go`. |
| **No foreperiod Weber** | Predictable prep improves go-signal *motor* precision (λ_prep) but the timed foreperiod itself accumulates clock drift (Niemi–Näätänen / WK interval). Missing `κ_fp·T_prep` ⇒ no U-shape; only monotonic “longer always quieter,” which Pass-4 cannot even express once cancellation bites. |
| **Aperture is spatial-log only** | `log(W_ref/W)` ignores how fast the target *crosses* the corridor. Tresilian / Bootsma: temporal hit-window `T_cross=W/\|v_perp\|` sets coincidence demand. Fast strafe + thin W binds the clock harder than thin W alone. |
| **Already KEEP — do not re-propose** | Fitts ID, τ_vm, intermittent N, U_max, α_vis-on-σ_corr, WK motor↔urgency / clock↔aperture split, prep↓motor form, Σ_θ0, drop ×1.02, lineup≠TOF. |

Net: Pass-4 factorized timing; Pass-5 fixes the **horizon identity** (post-release only), adds **foreperiod drift**, and deepens clock via **crossing-time** — still inside σ_aim only.

---

## Math target (aim axis only)

```
// Spatial (unchanged Pass-3/4 structure)
urgency = min(U_max, (T★/T_avail)^β)
σ_spatial = schmidtAimSigma(D, T_avail, W, {softVision, urgencyOut})  // as landed

// Timing deepen (Pass-5)
σ_t0     = max(0.02, releaseJitterSec)
T_prep   = max(0, releaseDelaySec)
aperture = max(0, log(W_ref / W_eff))
T_cross  = W_eff / max(|v_perp|, v_eps)          // temporal gate through corridor
cross    = max(0, log(T_xref / max(T_cross, eps)))

σ_motor  = σ_t0 · (1 + γ_u · (urgency − 1)) / (1 + λ_prep · T_prep)   // unchanged form
σ_clock  = σ_t0 · κ_clk · (1 + γ_w · aperture) · (1 + γ_x · cross)
σ_weber  = κ_w · t_go_mis                        // POST-RELEASE TOF only (≠ T_delay)
σ_fp     = κ_fp · T_prep                         // foreperiod Weber on go-signal interval
σ_t_eff  = hypot(σ_motor, σ_clock, σ_weber, σ_fp)

σ_timing = v_perp · σ_t_eff
σ_aim²   = σ_spatial² + σ_timing²

T_avail = max(T_min, aimTimeSec ?? T_lineup − ΔT_vision)   // still ≠ t_go
```

- **Post-release Weber:** slow missiles widen horizon SD via `t_go_mis` only; lengthening windup no longer self-cancels λ_prep.
- **Foreperiod:** moderate prep ↓σ_motor; very long prep ↑σ_fp → mild U-shape on σ_aim vs `T_prep`.
- **Crossing-time:** high `|v_perp|` / thin W inflates **clock** only (not Fitts `T_avail`, not σ_juke).
- Spatial helper / angular floor / FoW-on-σ_corr untouched.

Blind / softV: keep Pass-3 `T_visionCut` + α_vis on σ_corr. Do **not** reintroduce flat FoW glue on σ_aim; do **not** put softV on σ_weber (vision-axis / σ_belief owns that).

---

## Copy-paste patch (for orchestrator → `xh.ts`)

Replace **only** the Wing–Kristofferson + Weber timing block inside `estimateXh` (keep `schmidtAimSigma` as-is):

```ts
  // Wing–Kristofferson + post-release Weber + foreperiod + crossing (NOT T_avail = t_go)
  const sigmaT0 = Math.max(0.02, input.releaseJitterSec ?? 0.045)
  const T_prep = Math.max(0, input.releaseDelaySec ?? T_delay)
  const W_REF = 160
  const T_XREF = 0.35 // s; reference corridor crossing time
  const V_EPS = 60 // uu/s floor so T_cross stays finite
  const GAMMA_U = 0.4
  const GAMMA_W = 0.18
  const GAMMA_X = 0.22 // crossing-time → clock
  const KAPPA_CLK = 0.55
  const KAPPA_WEBER = 0.055 // slightly ↑ now that horizon is t_go_mis-only
  const KAPPA_FP = 0.028 // foreperiod Weber (s SD per 1s prep)
  const LAMBDA_PREP = 1.25 // modest ↑ once Weber no longer cancels prep
  const apertureTerm = Math.max(0, Math.log(W_REF / Math.max(40, W_eff)))
  const T_cross = W_eff / Math.max(Math.abs(vPerp), V_EPS)
  const crossTerm = Math.max(0, Math.log(T_XREF / Math.max(T_cross, 1e-3)))
  const sigmaMotor =
    (sigmaT0 * (1 + GAMMA_U * (urgency - 1))) / (1 + LAMBDA_PREP * T_prep)
  const sigmaClock =
    sigmaT0 * KAPPA_CLK * (1 + GAMMA_W * apertureTerm) * (1 + GAMMA_X * crossTerm)
  const sigmaWeber = KAPPA_WEBER * tGoMis // post-release intercept horizon
  const sigmaFp = KAPPA_FP * T_prep
  const sigmaT = Math.hypot(sigmaMotor, sigmaClock, sigmaWeber, sigmaFp)
  const sigmaTiming = vPerp * sigmaT

  let sigmaAim = Math.hypot(sigmaSpatial, sigmaTiming)
  if (casterZone === 'brush') {
    sigmaAim *= 0.94
    factors.push('aim:caster_brush')
  }
  factors.push('aim:fitts+sdn+vm+wk+weber+fp+cross+timing')
```

**Calibration knobs (if eval margins shrink):** lower `KAPPA_FP` first (0.02–0.028), then `GAMMA_X`, then `KAPPA_WEBER`. Do **not** restore `κ_w·t_go` with windup. Do **not** soften eval.

**Expected invariant gains:** prep strict↓σ_aim on timing-dominant fixtures; Weber slow≥fast with healthier margin; crossing gap thin−wide grows with `|v_perp|`; foreperiod U-shape (mid≤snap, very-long≥mid); Pass-1…4 Schmidt/Fitts/FoW-on-corr inequalities hold (spatial helper unchanged).

---

## New invariants to add to `scripts/eval-xh-math.ts`

Do **not** remove or weaken existing checks. Append after Pass-4 AIM block:

```ts
// --- aim deepen (Pass-5 AIM): post-release Weber, foreperiod, crossing-time ---

// Prep↓motor is visible once Weber ignores windup (timing-dominant fixture)
const p5Snap = estimateXh(
  base({
    aimTimeSec: 0.4,
    releaseDelaySec: 0.05,
    releaseJitterSec: 0.08,
    targetPerpVel: 480,
    targetMovespeed: 480,
    dashReady: false,
    crowdControlled: true,
  }),
)
const p5Mid = estimateXh(
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
const p5LongFp = estimateXh(
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
  'Pass-5: mid prep → smaller sigma.aim than snap (λ_prep; Weber≠windup)',
  !!p5Snap.sigma && !!p5Mid.sigma && p5Mid.sigma.aim < p5Snap.sigma.aim,
  `snap=${p5Snap.sigma?.aim.toFixed(1)} mid=${p5Mid.sigma?.aim.toFixed(1)}`,
)
assert(
  'Pass-5: very long prep → sigma.aim ≥ mid (foreperiod Weber κ_fp·T_prep)',
  !!p5LongFp.sigma &&
    !!p5Mid.sigma &&
    p5LongFp.sigma.aim + 1e-6 >= p5Mid.sigma.aim,
  `long=${p5LongFp.sigma?.aim.toFixed(1)} mid=${p5Mid.sigma?.aim.toFixed(1)}`,
)

// Post-release Weber: missile TOF only — slow ≥ fast at matched windup
const p5WebFast = estimateXh(
  base({
    missileSpeed: 3000,
    aimTimeSec: 0.35,
    releaseJitterSec: 0.05,
    releaseDelaySec: 0.28,
    targetPerpVel: 400,
    dashReady: false,
    crowdControlled: true,
  }),
)
const p5WebSlow = estimateXh(
  base({
    missileSpeed: 700,
    aimTimeSec: 0.35,
    releaseJitterSec: 0.05,
    releaseDelaySec: 0.28,
    targetPerpVel: 400,
    dashReady: false,
    crowdControlled: true,
  }),
)
assert(
  'Pass-5: slower missile → sigma.aim ≥ faster (Weber on t_go_mis)',
  !!p5WebSlow.sigma &&
    !!p5WebFast.sigma &&
    p5WebSlow.sigma.aim + 1e-6 >= p5WebFast.sigma.aim,
  `slow=${p5WebSlow.sigma?.aim.toFixed(1)} fast=${p5WebFast.sigma?.aim.toFixed(1)}`,
)

// Crossing-time: thin−wide σ_aim gap grows with |v_perp| (clock gate, T_avail fixed)
const crossThinFast = estimateXh(
  base({
    fittsWidthUu: 55,
    aimTimeSec: 0.45,
    releaseJitterSec: 0.06,
    releaseDelaySec: 0.28,
    targetPerpVel: 520,
    dashReady: false,
    crowdControlled: true,
  }),
)
const crossWideFast = estimateXh(
  base({
    fittsWidthUu: 240,
    aimTimeSec: 0.45,
    releaseJitterSec: 0.06,
    releaseDelaySec: 0.28,
    targetPerpVel: 520,
    dashReady: false,
    crowdControlled: true,
  }),
)
const crossThinSlow = estimateXh(
  base({
    fittsWidthUu: 55,
    aimTimeSec: 0.45,
    releaseJitterSec: 0.06,
    releaseDelaySec: 0.28,
    targetPerpVel: 100,
    dashReady: false,
    crowdControlled: true,
  }),
)
const crossWideSlow = estimateXh(
  base({
    fittsWidthUu: 240,
    aimTimeSec: 0.45,
    releaseJitterSec: 0.06,
    releaseDelaySec: 0.28,
    targetPerpVel: 100,
    dashReady: false,
    crowdControlled: true,
  }),
)
assert(
  'Pass-5: thin−wide σ_aim gap ≥ at higher |v_perp| (crossing-time clock)',
  !!crossThinFast.sigma &&
    !!crossWideFast.sigma &&
    !!crossThinSlow.sigma &&
    !!crossWideSlow.sigma &&
    crossThinFast.sigma.aim - crossWideFast.sigma.aim + 1e-6 >=
      crossThinSlow.sigma.aim - crossWideSlow.sigma.aim,
  `gap_hi=${(crossThinFast.sigma!.aim - crossWideFast.sigma!.aim).toFixed(1)} gap_lo=${(crossThinSlow.sigma!.aim - crossWideSlow.sigma!.aim).toFixed(1)}`,
)

// Guard: factor tag + T_avail still lineup (not TOF budget)
assert(
  'Pass-5: factors expose T_avail (lineup)',
  p5WebFast.factors.some((f) => f.startsWith('T_avail:')),
  p5WebFast.factors.join(','),
)
assert(
  'Pass-5: aim factor tag mentions fp/cross path',
  p5WebFast.factors.some((f) => f.includes('fp') || f.includes('cross')),
  p5WebFast.factors.join(','),
)
```

---

## arXiv / literature cites

| Id / ref | Use in Pass-5 model |
|----------|---------------------|
| **[2512.17735](https://arxiv.org/abs/2512.17735)** | Interceptive timing under prediction horizon — Weber component belongs on **flight/intercept interval**, not cast windup. |
| **[2412.04191](https://arxiv.org/abs/2412.04191)** | Predictive intercept / forward models — residual timing SD tracks uncompensated **TOF**, supporting `κ_w·t_go_mis`. |
| **[2110.11130](https://arxiv.org/abs/2110.11130)** | Inverse OFC + SDN — go-signal / motor command noise stays on **motor** WK term (λ_prep unchanged in role). |
| **[1804.05021](https://arxiv.org/abs/1804.05021)** | Aimed-movement phases — prep/commitment ≠ online correction budget; foreperiod is pre-release clock, not Fitts MT. |
| **[1903.05534](https://arxiv.org/abs/1903.05534)** | Event-driven sensorimotor control — discrete go-signal; long predictable foreperiods still carry trigger-interval noise. |
| Classic (comment cites): Gibbon SET / Tresilian coincidence-anticipation (Weber on timed interval); Wing & Kristofferson 1973 (clock+motor); Niemi & Näätänen 1981 (foreperiod); Bootsma & van Wieringen / Lee τ (crossing-time / TTC aperture). |

---

## Regression note

- **Must hold:** Pass-1…3 Schmidt/Fitts/τ_vm/U_max/FoW-on-σ_corr; Pass-4 Weber slow≥fast and prep long≤snap on *existing* fixtures; **no** `T_avail=t_go`.
- **Risk:** `KAPPA_FP` too large → very-long prep flips Pass-4 `long≤snap` on default fixtures (0.45 vs 0.05). Keep κ_fp small; Pass-5 U-shape assert uses 1.25 s vs 0.4 s mid.
- **Risk:** `GAMMA_X` + `σ_timing∝v_perp` can over-inflate high-strafe cells — if point-blank / CC ordinals flip, cut γ_x before κ_w.
- **Risk:** Raising `KAPPA_WEBER` after switching to `t_go_mis` can enlarge slow–fast margin (desired) but also lower xH on long-range skillshots — watch overlay sanity, not eval softening.
- **Risk:** Geo still propagates with `T_delay`; prep fixtures must keep `aimTimeSec` fixed and prefer explicit `targetPerpVel` so timing channel dominates spatial drift.
- Do **not** stack `(1+α t_go)` multiplier on top of Weber hypot.

---

## What not to do

- Do **not** set `T_avail = t_go` or fold missile speed into Fitts MT / τ_vm.
- Do **not** multiply `BASE_XH × mobility × zone × vision`.
- Do **not** put kit dash/Flash into σ_aim.
- Do **not** re-propose Pass-3/4 Fitts/SDN/τ_vm/intermittent/U_max/α_vis/WK split/Σ_θ0/prep↓motor *form* (already KEEP) — only fix Weber identity + add fp/cross.
- Do **not** put softV / FoW scale on σ_weber or whole σ_aim (σ_belief / α_vis-on-σ_corr own vision).
- Do **not** weaken any existing eval invariant.

---

## Decision

**`KEEP_CANDIDATE`**

Axis-local deepen of Pass-4 timing residual: move Weber onto post-release `t_go_mis` (stop prep↔horizon cancellation), add foreperiod clock drift, deepen aperture with crossing-time. Adds falsifiable invariants; preserves σ² = σ_aim² + σ_juke² + σ_belief² and public API. Orchestrator: patch timing block only, append invariants, reject only if `math_pass_rate` drops.

---

**Verdict: `KEEP_CANDIDATE`**
