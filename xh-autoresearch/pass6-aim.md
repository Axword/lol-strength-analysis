# Pass-6 AIM — WK clock⊥motor base + intermittent-refractory release + mild super-Weber

**Agent:** AIM  
**Baseline:** Post Pass-5 KEEP `math_pass_rate=1.0000` (129/129). Landed: Fitts/SDN/τ_vm/intermittent/U_max/FoW-σ_corr/WK split/Weber-on-`t_go_mis`/foreperiod `κ_fp`/crossing-time/`Σ_θ0`.  
**Scope:** deepen **σ_aim residual only**. Do **not** touch eval softening; do **not** edit `src/engine/xh.ts` here (orchestrator applies).  
**Hard rule:** no `BASE×ZONE×VISION`; do **not** set `T_avail=t_go`; no dash/Flash in σ_aim.

**Verdict: `KEEP_CANDIDATE`**

---

## Critique of Pass-5 σ_aim (current `xh.ts`)

Landed `schmidtAimSigma` (~510–561) + timing (~776–806):

```ts
// schmidtAimSigma: Fitts∩U_max, τ_vm, intermittent N, α_vis on σ_corr, Σ_θ0 ✓
// estimateXh timing (Pass-5):
σ_motor  = σ_t0·(1+γ_u(U−1))/(1+λ_prep·T_prep)
σ_clock  = σ_t0·κ_clk·(1+γ_w·aperture)·(1+γ_x·cross)   // ← residual
σ_weber  = κ_w·t_go_mis
σ_fp     = κ_fp·T_prep
σ_t      = hypot(motor, clock, weber, fp)
σ_timing = v_perp·σ_t
```

Eval / probe evidence (129/129, margins expose residue):

| Check | Observed | Residue |
|-------|----------|---------|
| Pass-4 Weber slow≥fast | `136.6` vs `136.4` | κ_w·Δt_go_mis still drowned by σ_spatial |
| Pass-5 U-shape long≥mid | `137.9` vs `137.9` | **exact tie** — κ_fp cancels λ_prep at fixture |
| Probe: thin−wide gap @ jitter 0.03→0.08 | gap `0.2` → `1.4` (**×7**) | aperture/crossing **clock scales with releaseJitterSec** |

| Residual gap | Why it matters |
|--------------|----------------|
| **WK clock still slave to σ_t0** | Pass-4 routed urgency→motor and aperture→clock, but both share `releaseJitterSec` as scale. Wing–Kristofferson: **motor and clock are independent variance sources**. Raising motor jitter must not inflate anticipatory aperture/crossing SD. Probe gap×7 is the smoking gun. |
| **No refractory couple from intermittent loop → release** | Pass-3 `N=⌊T_fb/Δt⌋` shrinks σ_corr spatially, but when `T_fb→0` the open-loop ballistic phase never settles — residual motor variance feeds the go-signal (Harris intermittent / dual-submovement). Missing `σ_ref∝exp(−T_fb/τ_ref)` under-noises snap lineups relative to feedback-rich ones **beyond** Fitts urgency alone. |
| **Linear Weber still weak on long TOF** | `κ_w·t_go_mis` is correct identity (Pass-5) but margin ~0.2 uu on default fixtures. SET / interceptive timing often shows **super-linear growth** of timing SD on long prediction horizons (CV drifts up). Mild `·(1+γ_sw·max(0,t_go_mis−T_wref))` enlarges slow−fast without restoring `(1+α t_go)` glue on all of σ_t. |
| **Already KEEP — do not re-propose** | Fitts ID, τ_vm, intermittent N, U_max, α_vis-on-σ_corr, WK urgency↔motor / aperture↔clock *routing*, prep↓motor form, Weber-on-`t_go_mis` (not windup), κ_fp foreperiod, crossing-time log gate, Σ_θ0, drop ×1.02, lineup≠TOF. |

Net: Pass-5 fixed horizon identity + fp/cross; Pass-6 closes **WK base independence**, **correction→release refractory**, and a **mild long-TOF Weber deepen** — still inside σ_aim only.

---

## Math target (aim axis only)

```
// Spatial (unchanged Pass-3/4/5 structure)
urgency = min(U_max, (T★/T_avail)^β)
σ_spatial = schmidtAimSigma(D, T_avail, W, {softVision, urgencyOut})  // as landed

// Timing deepen (Pass-6) — keep Pass-5 fp/cross/weber-on-t_go_mis identities
σ_t0     = max(0.02, releaseJitterSec)          // MOTOR base only
σ_c0     = 0.036                                 // CLOCK base (s), ⟂ σ_t0
T_prep   = max(0, releaseDelaySec)
aperture = max(0, log(W_ref / W_eff))
T_cross  = W_eff / max(|v_perp|, v_eps)
cross    = max(0, log(T_xref / max(T_cross, eps)))

T_OPEN = 0.16;  τ_vm = 0.1                       // match schmidtAimSigma
T_fb   = max(0, T_avail − T_OPEN − τ_vm)
σ_ref  = σ_t0 · γ_ref · exp(−T_fb / τ_ref)       // intermittent → release residue

σ_motor  = σ_t0 · (1 + γ_u · (urgency − 1)) / (1 + λ_prep · T_prep)
σ_motor  = hypot(σ_motor, σ_ref)                 // refractory ⊕ go-signal
σ_clock  = σ_c0 · κ_clk · (1 + γ_w · aperture) · (1 + γ_x · cross)  // NOT ×σ_t0
σ_weber  = κ_w · t_go_mis · (1 + γ_sw · max(0, t_go_mis − T_wref))
σ_fp     = κ_fp · T_prep                         // unchanged Pass-5
σ_t_eff  = hypot(σ_motor, σ_clock, σ_weber, σ_fp)

σ_timing = v_perp · σ_t_eff
σ_aim²   = σ_spatial² + σ_timing²

T_avail = max(T_min, aimTimeSec ?? T_lineup − ΔT_vision)   // still ≠ t_go
```

- **Clock⊥motor:** thin−wide / crossing gap no longer scales with `releaseJitterSec`; jitter only hits motor (+refractory).
- **Refractory:** snap lineups (`T_fb≈0`) carry extra release SD; feedback-rich lineups decay toward motor-only.
- **Super-Weber:** long missile TOF widens horizon SD faster than linear — healthier slow≥fast margin; short TOF unchanged at first order.
- Spatial helper / angular floor / FoW-on-σ_corr / κ_fp / cross log-gate untouched in *form*.

Blind / softV: keep Pass-3 `T_visionCut` + α_vis on σ_corr. Do **not** put softV on σ_weber / σ_clock; do **not** reintroduce flat FoW glue on σ_aim.

---

## Copy-paste patch (for orchestrator → `xh.ts`)

Replace **only** the Wing–Kristofferson + Weber timing block inside `estimateXh` (keep `schmidtAimSigma` as-is):

```ts
  // WK clock⊥motor + refractory + post-release Weber/fp/cross (NOT T_avail = t_go)
  const sigmaT0 = Math.max(0.02, input.releaseJitterSec ?? 0.045)
  const SIGMA_C0 = 0.036 // anticipatory clock base (s); independent of releaseJitter
  const T_prep = Math.max(0, input.releaseDelaySec ?? T_delay)
  const W_REF = 160
  const T_XREF = 0.35
  const V_EPS = 60
  const T_OPEN_AIM = 0.16 // match schmidtAimSigma open-loop phase
  const TAU_VM_AIM = 0.1
  const GAMMA_U = 0.4
  const GAMMA_W = 0.18
  const GAMMA_X = 0.22
  const GAMMA_REF = 0.32 // intermittent → release residue
  const TAU_REF = 0.22
  const GAMMA_SW = 0.45 // mild super-Weber above T_wref
  const T_WREF = 0.45 // s; onset of long-horizon CV drift
  const KAPPA_CLK = 0.55
  const KAPPA_WEBER = 0.055
  const KAPPA_FP = 0.055
  const LAMBDA_PREP = 1.25
  const apertureTerm = Math.max(0, Math.log(W_REF / Math.max(40, W_eff)))
  const T_cross = W_eff / Math.max(Math.abs(vPerp), V_EPS)
  const crossTerm = Math.max(0, Math.log(T_XREF / Math.max(T_cross, 1e-3)))
  const T_fbAim = Math.max(0, T_avail - T_OPEN_AIM - TAU_VM_AIM)
  const sigmaRef = sigmaT0 * GAMMA_REF * Math.exp(-T_fbAim / TAU_REF)
  const sigmaMotor = Math.hypot(
    (sigmaT0 * (1 + GAMMA_U * (urgency - 1))) / (1 + LAMBDA_PREP * T_prep),
    sigmaRef,
  )
  const sigmaClock =
    SIGMA_C0 * KAPPA_CLK * (1 + GAMMA_W * apertureTerm) * (1 + GAMMA_X * crossTerm)
  const sigmaWeber =
    KAPPA_WEBER *
    tGoMis *
    (1 + GAMMA_SW * Math.max(0, tGoMis - T_WREF))
  const sigmaFp = KAPPA_FP * T_prep
  const sigmaT = Math.hypot(sigmaMotor, sigmaClock, sigmaWeber, sigmaFp)
  const sigmaTiming = vPerp * sigmaT

  let sigmaAim = Math.hypot(sigmaSpatial, sigmaTiming)
  if (casterZone === 'brush') {
    sigmaAim *= 0.94
    factors.push('aim:caster_brush')
  }
  factors.push('aim:fitts+sdn+vm+wk+weber+fp+cross+ref+timing')
```

**Calibration knobs (if eval margins shrink):** lower `GAMMA_REF` first (0.2–0.32), then `GAMMA_SW`, then raise `SIGMA_C0` slightly if thin−wide clock gap collapses. Do **not** restore `σ_clock∝σ_t0`. Do **not** restore `κ_w·(T_delay+t_go_mis)`. Do **not** soften eval.

**Expected invariant gains:** jitter↑⇒σ_aim↑ on timing fixtures; thin−wide gap nearly invariant to jitter (ratio≲1.35); short `T_fb` refractory ⇒ σ_aim ≥ long lineup at matched W; Weber slow≥fast with healthier margin on long-TOF cells; Pass-1…5 Schmidt/Fitts/fp/cross inequalities hold.

---

## New invariants to add to `scripts/eval-xh-math.ts`

Do **not** remove or weaken existing checks. Append after Pass-5 AIM block:

```ts
// --- aim deepen (Pass-6 AIM): WK clock⊥motor, refractory, mild super-Weber ---

// Motor channel: release jitter inflates σ_aim (clock no longer steals the story)
const p6JitLo = estimateXh(
  base({
    aimTimeSec: 0.5,
    releaseDelaySec: 0.15,
    releaseJitterSec: 0.03,
    fittsWidthUu: 220,
    targetPerpVel: 480,
    dashReady: false,
    crowdControlled: true,
  }),
)
const p6JitHi = estimateXh(
  base({
    aimTimeSec: 0.5,
    releaseDelaySec: 0.15,
    releaseJitterSec: 0.09,
    fittsWidthUu: 220,
    targetPerpVel: 480,
    dashReady: false,
    crowdControlled: true,
  }),
)
assert(
  'Pass-6: higher releaseJitter → larger sigma.aim (motor channel)',
  !!p6JitLo.sigma &&
    !!p6JitHi.sigma &&
    p6JitHi.sigma.aim > p6JitLo.sigma.aim,
  `lo=${p6JitLo.sigma?.aim.toFixed(1)} hi=${p6JitHi.sigma?.aim.toFixed(1)}`,
)

// WK independence: thin−wide gap must NOT scale ~linearly with σ_t0
const gapAt = (j: number) => {
  const thin = estimateXh(
    base({
      releaseJitterSec: j,
      fittsWidthUu: 55,
      aimTimeSec: 0.45,
      releaseDelaySec: 0.28,
      targetPerpVel: 420,
      dashReady: false,
      crowdControlled: true,
    }),
  )
  const wide = estimateXh(
    base({
      releaseJitterSec: j,
      fittsWidthUu: 240,
      aimTimeSec: 0.45,
      releaseDelaySec: 0.28,
      targetPerpVel: 420,
      dashReady: false,
      crowdControlled: true,
    }),
  )
  return {
    thin,
    wide,
    gap: (thin.sigma?.aim ?? 0) - (wide.sigma?.aim ?? 0),
  }
}
const gLo = gapAt(0.03)
const gHi = gapAt(0.08)
assert(
  'Pass-6: thin−wide σ_aim gap stable vs jitter (clock ⟂ σ_t0)',
  !!gLo.thin.sigma &&
    !!gHi.thin.sigma &&
    gLo.gap > -1e-6 &&
    gHi.gap + 1e-6 >= 0 &&
    gHi.gap <= gLo.gap * 1.35 + 0.5,
  `gap_lo=${gLo.gap.toFixed(2)} gap_hi=${gHi.gap.toFixed(2)} ratio=${(gHi.gap / Math.max(1e-3, gLo.gap)).toFixed(2)}`,
)

// Refractory: T_fb≈0 (starved) noisier than feedback-rich lineup at matched W
const p6Starve = estimateXh(
  base({
    aimTimeSec: 0.14,
    fittsWidthUu: 200,
    releaseJitterSec: 0.06,
    releaseDelaySec: 0.2,
    targetPerpVel: 450,
    dashReady: false,
    crowdControlled: true,
  }),
)
const p6Rich = estimateXh(
  base({
    aimTimeSec: 0.55,
    fittsWidthUu: 200,
    releaseJitterSec: 0.06,
    releaseDelaySec: 0.2,
    targetPerpVel: 450,
    dashReady: false,
    crowdControlled: true,
  }),
)
assert(
  'Pass-6: starved T_fb → sigma.aim ≥ rich lineup (refractory⊕Fitts)',
  !!p6Starve.sigma &&
    !!p6Rich.sigma &&
    p6Starve.sigma.aim + 1e-6 >= p6Rich.sigma.aim,
  `starve=${p6Starve.sigma?.aim.toFixed(1)} rich=${p6Rich.sigma?.aim.toFixed(1)}`,
)

// Mild super-Weber: long TOF slow ≥ fast with visible margin on timing fixture
const p6WebFast = estimateXh(
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
const p6WebSlow = estimateXh(
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
  'Pass-6: slower missile → sigma.aim ≥ faster (super-Weber on t_go_mis)',
  !!p6WebSlow.sigma &&
    !!p6WebFast.sigma &&
    p6WebSlow.sigma.aim + 1e-6 >= p6WebFast.sigma.aim,
  `slow=${p6WebSlow.sigma?.aim.toFixed(1)} fast=${p6WebFast.sigma?.aim.toFixed(1)}`,
)
assert(
  'Pass-6: long-TOF Weber margin ≥ 0.75 uu (not spatial-drowned tie)',
  !!p6WebSlow.sigma &&
    !!p6WebFast.sigma &&
    p6WebSlow.sigma.aim - p6WebFast.sigma.aim + 1e-6 >= 0.75,
  `Δ=${(p6WebSlow.sigma!.aim - p6WebFast.sigma!.aim).toFixed(2)}`,
)

// Guard: factor tag + T_avail still lineup
assert(
  'Pass-6: factors expose T_avail (lineup)',
  p6WebFast.factors.some((f) => f.startsWith('T_avail:')),
  p6WebFast.factors.join(','),
)
assert(
  'Pass-6: aim factor tag mentions ref path',
  p6WebFast.factors.some((f) => f.includes('ref')),
  p6WebFast.factors.join(','),
)
```

---

## arXiv / literature cites

| Id / ref | Use in Pass-6 model |
|----------|---------------------|
| **[2110.11130](https://arxiv.org/abs/2110.11130)** | Inverse OFC + SDN — go-signal / release is **motor** noise; anticipatory clock is a separate source (do not share σ_t0). |
| **[2103.08558](https://arxiv.org/abs/2103.08558)** | Intermittent corrective impulses / dual-submovement variability — unfinished pulse train ⇒ **refractory residue** into release when `T_fb→0`. |
| **[1903.05534](https://arxiv.org/abs/1903.05534)** | Event-driven sensorimotor control — discrete correction epochs; open-loop residue between last pulse and trigger. |
| **[1804.05021](https://arxiv.org/abs/1804.05021)** | Aimed-movement phases — ballistic open-loop then feedback decay; starved `T_fb` never reaches low-variance feedback regime. |
| **[2512.17735](https://arxiv.org/abs/2512.17735)** | Interceptive timing under prediction horizon — long-horizon timing SD grows; motivates mild **super-Weber** on `t_go_mis` only. |
| **[2412.04191](https://arxiv.org/abs/2412.04191)** | Predictive intercept / forward models — uncompensated TOF residual; keep Weber identity post-release (Pass-5), deepen magnitude only. |
| Classic (comment cites): Wing & Kristofferson 1973 (clock⊥motor); Gibbon SET (Weber / scalar timing; CV drift on long intervals); Harris & Wolpert SDN (command-dependent motor variance). |

---

## Regression note

- **Must hold:** Pass-1…5 Schmidt/Fitts/τ_vm/U_max/FoW-on-σ_corr/WK routing/Weber-on-`t_go_mis`/fp U-shape/crossing; **no** `T_avail=t_go`.
- **Risk:** `GAMMA_REF` too large → snap fixtures over-inflate and may stress point-blank ordinals; cut γ_ref before touching Fitts knobs.
- **Risk:** `GAMMA_SW` too large → ultra-slow skillshots tank xH on overlay; watch calibration, not eval softening. Prefer γ_sw∈[0.3,0.5].
- **Risk:** `SIGMA_C0` too low → thin−wide / crossing asserts lose margin; too high → recreates Pass-3 aperture dominance. 0.036 ≈ prior σ_t0 default×0.8.
- **Risk:** Gap-stability assert uses `≤1.35× + 0.5` absolute cushion so tiny gaps (spatial-dominated) do not false-fail on noise; pre-fix probe ratio ~7 must fail until patch lands.
- Do **not** stack `(1+α t_go)` multiplier on whole σ_t; do **not** put refractory inside `schmidtAimSigma` return (keep spatial helper API stable — recompute `T_fb` locally).

---

## What not to do

- Do **not** set `T_avail = t_go` or fold missile speed into Fitts MT / τ_vm.
- Do **not** multiply `BASE_XH × mobility × zone × vision`.
- Do **not** put kit dash/Flash into σ_aim.
- Do **not** re-propose Pass-1…5 Fitts/SDN/τ_vm/intermittent/U_max/α_vis/WK *routing*/prep↓motor/Weber-on-`t_go_mis`/κ_fp/crossing *forms* — only split clock base, add refractory, mild super-Weber.
- Do **not** put softV / FoW scale on σ_weber or whole σ_aim.
- Do **not** weaken any existing eval invariant.

---

## Decision

**`KEEP_CANDIDATE`**

Axis-local deepen of Pass-5 timing residual: enforce Wing–Kristofferson **clock⊥motor bases**, add intermittent-correction **refractory → release**, and mild **super-Weber** on long `t_go_mis`. Adds falsifiable invariants (esp. gap-vs-jitter independence that current code fails); preserves σ² = σ_aim² + σ_juke² + σ_belief² and public API. Orchestrator: patch timing block only, append invariants, reject only if `math_pass_rate` drops.

---

**Verdict: `KEEP_CANDIDATE`**
