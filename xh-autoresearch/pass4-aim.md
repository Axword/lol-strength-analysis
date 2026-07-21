# Pass-4 AIM — Weber timing + Wing–Kristofferson split + prep→release

**Agent:** AIM  
**Baseline:** Post Pass-3 `math_pass_rate=1.0000` (88/88); Fitts/SDN/τ_vm/intermittent/release-urgency/U_max/FoW-on-σ_corr already landed.  
**Scope:** deepen **σ_aim residual only**. Do **not** touch eval softening; do **not** edit `src/engine/xh.ts` here (orchestrator applies).  
**Hard rule:** no `BASE×ZONE×VISION`; do **not** set `T_avail=t_go`; no dash/Flash in σ_aim.

**Verdict: `KEEP_CANDIDATE`**

---

## Critique of Pass-3 σ_aim (current `xh.ts`)

Landed `schmidtAimSigma` (~418–472) + `estimateXh` timing (~639–680):

```ts
// schmidtAimSigma: Fitts urgency∩U_max, τ_vm, intermittent N, α_vis on σ_corr ✓
// estimateXh timing:
const sigmaT =
  sigmaT0 * (1 + GAMMA_U * (urgency - 1)) * (1 + GAMMA_W * apertureTerm)
const sigmaTiming = vPerp * sigmaT * (1 + 0.55 * tGo)  // ad-hoc linear TOF
// releaseDelaySec / T_windup used for dodge window only — never σ_aim
// σ_ang = κ_θ · D  — no near-range retinotopic floor
```

| Residual gap | Why it matters |
|--------------|----------------|
| **Linear TOF glue `(1+α t_go)`** | Pass-1/3 put prediction horizon in timing, but the form is a flat multiplier on *all* of σ_t. Scalar expectancy / coincidence-anticipation: timing SD grows **with the timed interval** (Weber), i.e. a horizon *component* `κ_w·t_go`, not a scale on release motor noise. Still **not** `T_avail=t_go`. |
| **Urgency×aperture product on one σ_t** | Pass-3 multiplies `(1+γ_u(U−1))·(1+γ_w log W)` into a **single** release SD. Wing–Kristofferson: interval variance = **clock + motor**. Fitts haste / go-signal noise → **motor**; narrow aperture (temporal gate) → **clock / anticipation**. Product double-counts thin-W into both spatial ID (already in σ_lat) and a fused timing channel. |
| **`releaseDelaySec` unused by aim** | Geo already exposes cast windup / delayed release. Longer committed prep improves go-signal timing (lower motor release noise) **without** lengthening Fitts `T_avail` or folding TOF into MT. Currently windup only widens dodge window — asymmetric vs aim. |
| **Angular channel has no floor** | `κ_θ·D→0` at point-blank; retinotopic / directional encoding still has a small bearing floor. Prevents pathological near-D under-noise when timing/corr dominate. |
| **Already KEEP — do not re-propose** | Fitts ID gate, τ_vm, intermittent N, U_max, FoW α_vis on σ_corr, drop ×1.02, lineup≠TOF. |

Net: Pass-3 closed spatial feedback residuals; Pass-4 closes the **timing-channel factorization** (Weber ⊕ WK) and the missing **prep→release** couple — still inside σ_aim only.

---

## Math target (aim axis only)

```
// Spatial (unchanged Pass-3 structure)
urgency = min(U_max, (T★/T_avail)^β)
σ_spatial = schmidtAimSigma(D, T_avail, W, {softVision, urgencyOut})  // as landed

// Wing–Kristofferson split + Weber horizon (timing channel only)
σ_t0     = max(0.02, releaseJitterSec)
T_prep   = max(0, releaseDelaySec)            // existing input; default 0.28
aperture = max(0, log(W_ref / W_eff))

σ_motor  = σ_t0 · (1 + γ_u · (urgency − 1)) / (1 + λ_prep · T_prep)
σ_clock  = σ_t0 · κ_clk · (1 + γ_w · aperture)
σ_weber  = κ_w · t_go                         // SET / coincidence horizon
σ_t_eff  = hypot(σ_motor, σ_clock, σ_weber)

σ_timing = v_perp · σ_t_eff                   // DROP (1+0.55·t_go) multiplier

// Angular floor inside schmidtAimSigma (minimal)
σ_ang = hypot(κ_θ · D, Σ_θ0)                  // Σ_θ0 ≈ 8 uu

σ_aim² = σ_spatial² + σ_timing²               // σ_spatial already ⊕ σ₀,lat,ang,corr
T_avail = max(T_min, aimTimeSec ?? T_lineup − ΔT_vision)   // still ≠ t_go
```

- **Weber:** slow missiles widen the *horizon component* of timing SD; fast missiles shrink it — preserves `slower missile → σ_aim ≥ faster` without TOF→T_avail.
- **WK split:** urgency no longer multiplies aperture; thin-W timing inflation is clock-only; haste is motor-only.
- **Prep→release:** longer windup ↓ σ_motor; short snap-cast ↑ motor release noise. Orthogonal to Fitts lineup budget.
- **Angular floor:** near-D bearing floor; far-D still κ_θ·D-dominated.

Blind / softV: keep Pass-3 `T_visionCut` + α_vis on σ_corr. Do **not** reintroduce flat FoW glue on σ_aim.

---

## Copy-paste patch (for orchestrator → `xh.ts`)

### 1) Angular floor inside `schmidtAimSigma` (one-line deepen)

```ts
  // replace: const sigmaAng = KAPPA_THETA * D
  const SIGMA_ANG0 = 8 // retinotopic / bearing floor (uu lateral)
  const sigmaAng = Math.hypot(KAPPA_THETA * D, SIGMA_ANG0)
```

Leave intermittent / τ_vm / U_max / α_vis untouched.

### 2) Replace timing block in `estimateXh` (Weber + WK + prep)

```ts
  // --- σ_aim: Pass-3 spatial + Pass-4 Weber/WK/prep timing ---
  const T_min = 0.12
  const T_lineup = 0.38
  const T_visionCut =
    softV < 0.15
      ? age < 0.25
        ? 0.03
        : 0.14
      : softV < 0.5
        ? 0.08
        : vision === 'unknown'
          ? 0.06
          : 0
  const T_avail = Math.max(T_min, input.aimTimeSec ?? T_lineup - T_visionCut)
  factors.push(`T_avail:${T_avail.toFixed(2)}s`)

  const D = dist
  const W_eff = Math.max(40, input.fittsWidthUu ?? 2 * R_hit)
  const urgencyHold = { value: 1 }
  const sigmaSpatial = schmidtAimSigma(D, T_avail, W_eff, {
    softVision: softV,
    urgencyOut: urgencyHold,
  })
  const urgency = urgencyHold.value
  const ID = fittsIndex(D, W_eff)
  factors.push(`fitts_ID:${ID.toFixed(2)}`, `urgency:${urgency.toFixed(2)}`)

  // Wing–Kristofferson + Weber horizon (NOT T_avail = t_go)
  const sigmaT0 = Math.max(0.02, input.releaseJitterSec ?? 0.045)
  const T_prep = Math.max(0, input.releaseDelaySec ?? T_delay)
  const W_REF = 160
  const GAMMA_U = 0.4
  const GAMMA_W = 0.18
  const KAPPA_CLK = 0.55
  const KAPPA_WEBER = 0.04 // s of timing SD per 1s TOF horizon
  const LAMBDA_PREP = 1.1
  const apertureTerm = Math.max(0, Math.log(W_REF / Math.max(40, W_eff)))
  const sigmaMotor =
    (sigmaT0 * (1 + GAMMA_U * (urgency - 1))) / (1 + LAMBDA_PREP * T_prep)
  const sigmaClock = sigmaT0 * KAPPA_CLK * (1 + GAMMA_W * apertureTerm)
  const sigmaWeber = KAPPA_WEBER * tGo
  const sigmaT = Math.hypot(sigmaMotor, sigmaClock, sigmaWeber)
  const sigmaTiming = vPerp * sigmaT

  let sigmaAim = Math.hypot(sigmaSpatial, sigmaTiming)
  if (casterZone === 'brush') {
    sigmaAim *= 0.94
    factors.push('aim:caster_brush')
  }
  factors.push('aim:fitts+sdn+vm+wk+weber+timing')
```

**Calibration knobs (if eval margins shrink):** lower `KAPPA_WEBER` first (0.025–0.04), then `GAMMA_W`, then `LAMBDA_PREP`. Do **not** soften eval. Do **not** restore `(1+α t_go)` multiplier on top of Weber (double horizon).

**Expected invariant gains:** Weber slow≥fast, WK urgency-vs-aperture separation, prep↓σ_aim, angular floor near-D; Pass-1/2/3 Schmidt/Fitts/missile/FoW-on-corr inequalities hold because spatial helper unchanged aside from Σ_θ0 floor and timing still grows with t_go via σ_weber.

---

## New invariants to add to `scripts/eval-xh-math.ts`

Do **not** remove or weaken existing checks. Append after Pass-3 AIM block:

```ts
// --- aim deepen (Pass-4 AIM): Weber horizon, WK split, prep→release ---

// Weber: same releaseJitter + aimTime; slower missile → larger σ_aim via κ_w·t_go
const webFast = estimateXh(
  base({
    missileSpeed: 2800,
    aimTimeSec: 0.35,
    releaseJitterSec: 0.04,
    releaseDelaySec: 0.28,
    dashReady: false,
    crowdControlled: true,
  }),
)
const webSlow = estimateXh(
  base({
    missileSpeed: 800,
    aimTimeSec: 0.35,
    releaseJitterSec: 0.04,
    releaseDelaySec: 0.28,
    dashReady: false,
    crowdControlled: true,
  }),
)
assert(
  'Pass-4: slower missile → sigma.aim ≥ faster (Weber horizon ≠ T_avail)',
  !!webSlow.sigma &&
    !!webFast.sigma &&
    webSlow.sigma.aim + 1e-6 >= webFast.sigma.aim,
  `slow=${webSlow.sigma?.aim.toFixed(1)} fast=${webFast.sigma?.aim.toFixed(1)}`,
)

// Prep→release: longer windup → smaller σ_aim (motor release), same T_avail / t_go
const prepShort = estimateXh(
  base({
    aimTimeSec: 0.32,
    releaseDelaySec: 0.05,
    releaseJitterSec: 0.05,
    dashReady: false,
    crowdControlled: true,
    targetMovespeed: 420,
  }),
)
const prepLong = estimateXh(
  base({
    aimTimeSec: 0.32,
    releaseDelaySec: 0.55,
    releaseJitterSec: 0.05,
    dashReady: false,
    crowdControlled: true,
    targetMovespeed: 420,
  }),
)
assert(
  'Pass-4: longer releaseDelay → smaller sigma.aim (prep↓motor; T_avail fixed)',
  !!prepShort.sigma &&
    !!prepLong.sigma &&
    prepShort.sigma.aim > prepLong.sigma.aim,
  `short=${prepShort.sigma?.aim.toFixed(1)} long=${prepLong.sigma?.aim.toFixed(1)}`,
)

// WK: urgency (thin W, short T) raises σ even when aperture term matched via fittsWidth
// vs wide W at same T — motor channel; and aperture gap grows with releaseJitter
// when urgency≈1 (long T_avail).
const wkRushThin = estimateXh(
  base({
    fittsWidthUu: 55,
    aimTimeSec: 0.16,
    releaseJitterSec: 0.05,
    releaseDelaySec: 0.2,
    dashReady: false,
    crowdControlled: true,
    targetMovespeed: 400,
  }),
)
const wkRushWide = estimateXh(
  base({
    fittsWidthUu: 240,
    aimTimeSec: 0.16,
    releaseJitterSec: 0.05,
    releaseDelaySec: 0.2,
    dashReady: false,
    crowdControlled: true,
    targetMovespeed: 400,
  }),
)
assert(
  'Pass-4: rushed thin W → sigma.aim ≥ wide (urgency→motor WK)',
  !!wkRushThin.sigma &&
    !!wkRushWide.sigma &&
    wkRushThin.sigma.aim + 1e-6 >= wkRushWide.sigma.aim,
  `thin=${wkRushThin.sigma?.aim.toFixed(1)} wide=${wkRushWide.sigma?.aim.toFixed(1)}`,
)

const wkLongThin = estimateXh(
  base({
    fittsWidthUu: 55,
    aimTimeSec: 0.55,
    releaseJitterSec: 0.08,
    releaseDelaySec: 0.28,
    dashReady: false,
    crowdControlled: true,
    targetMovespeed: 450,
  }),
)
const wkLongWide = estimateXh(
  base({
    fittsWidthUu: 240,
    aimTimeSec: 0.55,
    releaseJitterSec: 0.08,
    releaseDelaySec: 0.28,
    dashReady: false,
    crowdControlled: true,
    targetMovespeed: 450,
  }),
)
const wkLongThin0 = estimateXh(
  base({
    fittsWidthUu: 55,
    aimTimeSec: 0.55,
    releaseJitterSec: 0.02,
    releaseDelaySec: 0.28,
    dashReady: false,
    crowdControlled: true,
    targetMovespeed: 450,
  }),
)
const wkLongWide0 = estimateXh(
  base({
    fittsWidthUu: 240,
    aimTimeSec: 0.55,
    releaseJitterSec: 0.02,
    releaseDelaySec: 0.28,
    dashReady: false,
    crowdControlled: true,
    targetMovespeed: 450,
  }),
)
assert(
  'Pass-4: long T — thin−wide σ_aim gap grows with releaseJitter (clock/aperture)',
  !!wkLongThin.sigma &&
    !!wkLongWide.sigma &&
    !!wkLongThin0.sigma &&
    !!wkLongWide0.sigma &&
    wkLongThin.sigma.aim - wkLongWide.sigma.aim + 1e-6 >=
      wkLongThin0.sigma.aim - wkLongWide0.sigma.aim,
  `gap_hi=${(wkLongThin.sigma!.aim - wkLongWide.sigma!.aim).toFixed(1)} gap_lo=${(wkLongThin0.sigma!.aim - wkLongWide0.sigma!.aim).toFixed(1)}`,
)

// Angular floor: very near D still has finite σ_aim above pure timing-at-zero-D fantasy;
// farther D at long T still raises σ_aim (κ_θ·D dominates floor).
const angNear4 = estimateXh(
  base({
    targetPosition: { x: mid.x + 0.01, y: mid.y },
    abilityRange: 700,
    aimTimeSec: 0.5,
    releaseJitterSec: 0.02,
    targetMovespeed: 200,
    dashReady: false,
    crowdControlled: true,
  }),
)
const angFar4 = estimateXh(
  base({
    targetPosition: far,
    abilityRange: 1175,
    missileWidth: 160,
    aimTimeSec: 0.5,
    releaseJitterSec: 0.02,
    targetMovespeed: 200,
    dashReady: false,
    crowdControlled: true,
    flashReady: false,
  }),
)
assert(
  'Pass-4: long T — farther D → larger sigma.aim (angular ⊕ floor)',
  !!angNear4.sigma &&
    !!angFar4.sigma &&
    angFar4.sigma.aim > angNear4.sigma.aim,
  `near=${angNear4.sigma?.aim.toFixed(1)} far=${angFar4.sigma?.aim.toFixed(1)}`,
)

// Guard: factors still expose T_avail; must not encode t_go as aim budget
assert(
  'Pass-4: factors expose T_avail (lineup)',
  webFast.factors.some((f) => f.startsWith('T_avail:')),
  webFast.factors.join(','),
)
assert(
  'Pass-4: aim factor tag mentions wk/weber path',
  webFast.factors.some((f) => f.includes('wk') || f.includes('weber')),
  webFast.factors.join(','),
)
```

---

## arXiv / literature cites

| Id / ref | Use in Pass-4 model |
|----------|---------------------|
| **[2512.17735](https://arxiv.org/abs/2512.17735)** | Interceptive timing under prediction horizon — **Weber / SET** component `κ_w·t_go` on release timing, not Fitts MT. |
| **[2412.04191](https://arxiv.org/abs/2412.04191)** | Predictive intercept / forward models — incomplete compensation ⇒ residual timing SD grows with horizon. |
| **[2110.11130](https://arxiv.org/abs/2110.11130)** | Inverse OFC + human SDN — go-signal / motor command noise = **motor** WK term under urgency. |
| **[2410.02966](https://arxiv.org/abs/2410.02966)** | Offline+online OFC with SDN recovers Fitts — urgency stays on σ_lat; Pass-4 only **routes** haste into motor timing, does not re-gate Fitts. |
| **[1804.05021](https://arxiv.org/abs/1804.05021)** | Aimed-movement variability phases — prep/commitment before release ≠ online correction budget. |
| **[1903.05534](https://arxiv.org/abs/1903.05534)** | Event-driven sensorimotor control — discrete go-signal; windup length modulates release trigger noise. |
| Classic (comment cites): Wing & Kristofferson 1973 (clock+motor timing variance); Tresilian coincidence-anticipation; Gibbon scalar expectancy (Weber timing); van Beers et al. 2004 (directional noise floor / anisotropy). |

---

## Regression note

- **Must hold:** Pass-1 Schmidt `T_avail` inequalities; Pass-2 Fitts width / `fittsWidthUu` / far-D; Pass-3 thin-W release–urgency, FoW-on-σ_corr (no ×1.02), urgency cap behavior; `slower missile → σ_aim ≥ faster`; **no** `T_avail = t_go`.
- **Risk:** Replacing `(1+α t_go)` with `κ_w·t_go` in hypot can *shrink* slow–fast margin if `KAPPA_WEBER` too small — raise toward 0.05 before touching spatial knobs.
- **Risk:** `LAMBDA_PREP` with default `releaseDelaySec=0.28` lowers baseline σ_timing vs Pass-3; if point-blank / CC ordering flips, lower λ (0.6–1.1) rather than cutting Weber.
- **Risk:** Angular floor Σ_θ0=8 adds ~constant to near-D σ; far>near assert should still hold; if near≈far at long T, floor too large vs κ_θ·ΔD.
- **Risk:** Prep assert must keep `aimTimeSec` **fixed** — if orchestrator accidentally ties prep into T_avail, reject (violates hard rule spirit).
- Dropping product γ_u·γ_w may slightly flatten Pass-3 thin-vs-wide timing gap; spatial Fitts urgency + WK motor still cover `thin>wide` under rush.

---

## What not to do

- Do **not** set `T_avail = t_go` or fold missile speed into Fitts MT / τ_vm.
- Do **not** multiply `BASE_XH × mobility × zone × vision`.
- Do **not** put kit dash/Flash into σ_aim.
- Do **not** re-propose Pass-3 τ_vm / intermittent N / U_max / α_vis-on-σ_corr / drop ×1.02 (already KEEP).
- Do **not** stack `(1+α t_go)` **on top of** Weber hypot (double horizon).
- Do **not** weaken any existing eval invariant.

---

## Decision

**`KEEP_CANDIDATE`**

Axis-local deepen of Pass-3 timing residual: replace linear TOF glue with Weber horizon ⊕ Wing–Kristofferson motor/clock split, couple existing `releaseDelaySec` into motor release precision, add angular bearing floor. Adds falsifiable invariants; preserves σ² = σ_aim² + σ_juke² + σ_belief² and public API. Orchestrator: patch `sigmaAng` + timing block, append invariants, reject only if `math_pass_rate` drops.

---

**Verdict: `KEEP_CANDIDATE`**
