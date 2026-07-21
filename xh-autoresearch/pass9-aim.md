# Pass-9 AIM — Schmidt-scaled intermittent + accel→σ_aim

**Agent:** AIM  
**Baseline:** Post Pass-8 KEEP `math_pass_rate=1.0000` (195/195). Landed: Schmidt⊥Fitts-rush (`hypot(D/T, rush)`), radial∥timing `hypot(|v_perp|,κ_rad|v_rad|)·σ_t`, `Σ_τvm≈24ms` in timing hypot.  
**Scope:** deepen **σ_aim residual only**. Do **not** touch eval softening; do **not** edit `src/engine/xh.ts` here (orchestrator applies).  
**Hard rule:** no `BASE×ZONE×VISION`; do **not** set `T_avail=t_go`; no dash/Flash in σ_aim.

**Verdict: `KEEP_CANDIDATE`**

---

## Critique of Pass-8 σ_aim (current `xh.ts`)

Landed `schmidtAimSigma` (~590–644) + timing (~879–935):

```ts
// schmidtAimSigma (Pass-8 spatial):
σ_lat  = hypot(κ_lat·(D/T), κ_rush·max(0,U−1))   // ✓ rush ⊥ Schmidt
σ_ang  = hypot(κ_θ·D, Σ_θ0)
// intermittent corr (Pass-3 form, untouched since):
u0     = κ_lat · (D / T_OPEN)                     // ← residual: frozen open-loop
dt     = max(Δt_int, T_fb / N)
σ_corr² = Σ_k (κ_c · u0 · ρ^k / dt)²              // ← grows toward sat as N↑
σ_spatial = hypot(σ₀, σ_lat, σ_ang, σ_corr)

// estimateXh timing (Pass-8):
σ_t      = hypot(motor, clock, weber, fp, Σ_τvm)
v_time   = hypot(|v_perp|, κ_rad·|v_rad|)
σ_timing = v_time · σ_t
σ_aim    = hypot(σ_spatial, σ_timing)             // ← accel silent
// geo (elsewhere): μ += ½|A| t_zem²               // variance missing
```

Eval / probe evidence (195/195, margins expose residue):

| Check | Observed | Residue |
|-------|----------|---------|
| Probe: T_avail sweep @ U=1 | σ_aim **127.7 → 158.3** from T=0.45→0.9 (**+30.6 uu**) | past Fitts T★ (~0.19s) longer lineup **raises** We — anti-Fitts |
| Probe: `u0=κ·D/T_OPEN` | first pulse sized on frozen ballistic `T_OPEN`; as `dt→Δt_int`, σ_corr climbs **~67→145** toward sat | correction SDN does not track shrinking Schmidt demand `D/T` |
| Probe: `residualAccel` 0→900 | **Δσ_aim = 0**; `mu_bias` 135→217 | accel is μ-only (geo ZEM); aim SD ignores jerkiness of intercept |
| Pass-8 D∧U excess | **~267** (≤500) | product fix holds — do not reopen |
| Pass-8 radial Weber | **Δ≈0.47** (≥0.4) | radial∥timing holds; do not stuff `|v_rad|` into clock cross (would double-count with `v_time`) |

| Residual gap | Why it matters |
|--------------|----------------|
| **Intermittent u0 frozen on T_OPEN** | Pass-3 sized correction pulses as open-loop ballistic commands at `T_OPEN`. Under long `T_fb`, `N` grows and `dt↓→Δt_int`, so early-pulse SDN **inflates toward an asymptote independent of** current `D/T`. Net: after urgency floor, extra lineup time adds correction noise faster than Schmidt `D/T` shrinks → anti-Fitts rise (~+31 uu). Meyer / intermittent control: secondary pulses scale with **remaining primary demand**, i.e. current Schmidt velocity `D/T`, not a frozen open-loop amp. |
| **Accel → μ only** | `boundedAccelZemExtra` shifts lead miss, but σ_aim is blind to `|A|`. Predictive intercept under residual accel (Bootsma / SDN): unmodeled transverse accel is a **variance** source, not only bias. Geo Pass-9 may retarget the ZEM *clock*; AIM still needs `σ_accel` on the aim axis. |
| **Already KEEP — do not re-propose** | Fitts ID, τ_vm *identity* (feedback subtract), intermittent *N/ρ structure*, U_max, α_vis-on-σ_corr, WK urgency↔motor / aperture↔clock, prep↓motor, Weber-on-`t_go_mis`, κ_fp, crossing *log*, Σ_θ0, clock⊥motor `σ_c0`, `σ_r0`, aperture⊥cross, super-Weber, super-fp, Schmidt⊥rush, radial∥`v_time`, Σ_τvm, drop ×1.02, lineup≠TOF. Do **not** put `|v_rad|` into `T_cross` (double-counts Pass-8 projection). Do **not** restore `σ_lat∝urgency`. |

Net: Pass-8 finished spatial urgency independence + radial timing + Σ_τvm; Pass-9 finishes **intermittent pulse scaling** and **accel variance** — still inside σ_aim only.

---

## Math target (aim axis only)

```
// Spatial deepen (Pass-9) — keep Pass-8 rush hypot / Σ_θ0 / α_vis / τ_vm identity
urgency = min(U_max, (T★/T_avail)^β)
σ_schmidt = κ_lat · (D / T)
σ_rush    = κ_rush · max(0, urgency − 1)
σ_lat     = hypot(σ_schmidt, σ_rush)

T_fb = max(0, T − T_OPEN − τ_vm)
N    = floor(T_fb / Δt_int)
// Pass-9: correction pulses track current Schmidt demand (not D/T_OPEN)
u0   = κ_lat · (D / T)                          // was κ_lat·(D/T_OPEN)
dt   = max(Δt_int, T_fb / N)                    // form unchanged
σ_corr² = Σ_{k=0..N−1} (κ_c · u0 · ρ^k / dt)²
σ_corr *= α_vis(softV)
σ_ang  = hypot(κ_θ · D, Σ_θ0)
σ_spatial = hypot(σ₀, σ_lat, σ_ang, σ_corr)

// Timing (Pass-8 identities unchanged)
σ_t      = hypot(motor, clock, weber, fp, Σ_τvm)
v_time   = hypot(|v_perp|, κ_rad · |v_rad|)
σ_timing = v_time · σ_t

// Accel deepen (Pass-9) — variance twin of geo boundedAccelZemExtra
A_res    = |residualAccelUuPerSec2|
t_zem    = accelZemClockSec(T_delay, t_cpa)     // same clock as μ ZEM
σ_accel  = κ_a · (½ A_res t_zem²)               // κ_a ∈ [0.2, 0.4]
σ_aim    = hypot(σ_spatial, σ_timing, σ_accel)

T_avail  = max(T_min, aimTimeSec ?? T_lineup − ΔT_vision)   // still ≠ t_go
```

- **Schmidt-scaled corr:** long lineup shrinks both primary `D/T` *and* correction pulse amp → Fitts-monotone past T★; snap / N=0 path bit-identical.
- **Accel σ:** `|A|>0` inflates σ_aim even when lead skill absorbs mean ZEM; A=0 ⇒ σ_accel=0 (bit-identical aside from corr scaling).
- Radial∥timing, rush hypot, Σ_τvm, clock aperture⊥cross, super-fp / Weber — untouched.

Blind / softV: keep α_vis on σ_corr only. Do **not** put softV on σ_weber / σ_clock / σ_fp / Σ_τvm / σ_accel; do **not** reintroduce flat FoW glue on σ_aim.

---

## Copy-paste patch (for orchestrator → `xh.ts`)

### 1) Inside `schmidtAimSigma` — correction `u0` only

```ts
  const T_fb = Math.max(0, T - T_OPEN - TAU_VM)
  const N = Math.floor(T_fb / DT_INT + 1e-9)
  let sigmaCorr = 0
  if (N >= 1) {
    // Pass-9: intermittent pulses ∝ current Schmidt demand D/T (not D/T_OPEN)
    const u0 = KAPPA_LAT * (D / T)
    const dt = Math.max(DT_INT, T_fb / N)
    let acc = 0
    for (let k = 0; k < N; k++) {
      const uk = (u0 * Math.pow(RHO, k)) / dt
      acc += (KAPPA_C * uk) ** 2
    }
    const alphaVis = softV >= 0.5 ? 1 : Math.max(0, softV / 0.5)
    sigmaCorr = Math.sqrt(acc) * alphaVis
  }
```

### 2) Timing / σ_aim block in `estimateXh` — add accel leg (after Pass-8 timing)

```ts
  const vTime = Math.hypot(Math.abs(vPerp), KAPPA_RAD * Math.abs(vRadial))
  const sigmaTiming = vTime * sigmaT

  // Pass-9: accel variance twin of boundedAccelZemExtra (μ already uses zemExtra)
  const KAPPA_A = 0.28 // fraction of |ZEM_accel| as aim SD
  const sigmaAccel = KAPPA_A * Math.abs(zemExtra)
  let sigmaAim = Math.hypot(sigmaSpatial, sigmaTiming, sigmaAccel)
  if (casterZone === 'brush') {
    sigmaAim *= 0.94
    factors.push('aim:caster_brush')
  }
  factors.push(
    'aim:fitts+sdn+vm+wk+weber+fp+cross+ref+tau+rad+corrDT+accel+timing',
  )
```

**Calibration knobs (if eval margins shrink):** lower `KAPPA_A` first (0.2–0.35) if high-accel fixtures tank xH overlays; corr `u0∝D/T` has no new knob — if long-T floor undershoots, prefer slight ↑ `KAPPA_C` (0.045→0.05) over restoring `D/T_OPEN`. Do **not** restore `u0∝D/T_OPEN`. Do **not** feed `|v_rad|` into `T_cross`. Do **not** soften eval.

**Expected invariant gains:** T=0.9 σ_aim ≤ T=0.45 (Fitts-monotone; today rises ~+31); `|A|>0` ⇒ σ_aim > A=0; Pass-1…8 Schmidt/Fitts/rush/radial/τvm inequalities hold; N=0 snaps unchanged.

---

## New invariants to add to `scripts/eval-xh-math.ts`

Do **not** remove or weaken existing checks. Append after Pass-8 AIM block:

```ts
// --- aim deepen (Pass-9 AIM): Schmidt-scaled corr + accel→σ_aim ---

// Fitts-monotone past T★: longer lineup must not raise σ_aim via corr sat
const p9MidT = estimateXh(
  base({
    aimTimeSec: 0.45,
    fittsWidthUu: 180,
    targetPerpVel: 40,
    dashReady: false,
    crowdControlled: true,
  }),
)
const p9LongT = estimateXh(
  base({
    aimTimeSec: 0.9,
    fittsWidthUu: 180,
    targetPerpVel: 40,
    dashReady: false,
    crowdControlled: true,
  }),
)
assert(
  'Pass-9: T=0.9 σ_aim ≤ T=0.45 (corr pulses ∝ D/T, not anti-Fitts sat)',
  !!p9MidT.sigma &&
    !!p9LongT.sigma &&
    p9LongT.sigma.aim <= p9MidT.sigma.aim + 1e-6,
  `mid=${p9MidT.sigma?.aim.toFixed(1)} long=${p9LongT.sigma?.aim.toFixed(1)} Δ=${((p9LongT.sigma?.aim ?? 0) - (p9MidT.sigma?.aim ?? 0)).toFixed(1)}`,
)

// Snap path still louder than lined (N=0 unchanged; short>long preserved)
const p9SnapT = estimateXh(
  base({
    aimTimeSec: 0.14,
    fittsWidthUu: 180,
    targetPerpVel: 40,
    dashReady: false,
    crowdControlled: true,
  }),
)
assert(
  'Pass-9: snap T=0.14 σ_aim > lined T=0.55 (N=0 / rush path intact)',
  !!p9SnapT.sigma &&
    !!p9MidT.sigma &&
    p9SnapT.sigma.aim > (p9LongT.sigma?.aim ?? 0),
  `snap=${p9SnapT.sigma?.aim.toFixed(1)} long=${p9LongT.sigma?.aim.toFixed(1)}`,
)

// Accel → σ_aim (μ-only today)
const p9Acc0 = estimateXh(
  base({
    aimTimeSec: 0.4,
    releaseDelaySec: 0.2,
    targetPerpVel: 180,
    residualAccelUuPerSec2: 0,
    missileSpeed: 1400,
    dashReady: false,
    crowdControlled: true,
  }),
)
const p9Acc1 = estimateXh(
  base({
    aimTimeSec: 0.4,
    releaseDelaySec: 0.2,
    targetPerpVel: 180,
    residualAccelUuPerSec2: 900,
    missileSpeed: 1400,
    dashReady: false,
    crowdControlled: true,
  }),
)
assert(
  'Pass-9: residualAccel → larger sigma.aim (accel variance, not μ-only)',
  !!p9Acc0.sigma &&
    !!p9Acc1.sigma &&
    p9Acc1.sigma.aim > p9Acc0.sigma.aim + 1e-6,
  `A0=${p9Acc0.sigma?.aim.toFixed(2)} A900=${p9Acc1.sigma?.aim.toFixed(2)}`,
)
assert(
  'Pass-9: accel σ_aim margin ≥ 1.5 uu at |A|=900',
  !!p9Acc0.sigma &&
    !!p9Acc1.sigma &&
    p9Acc1.sigma.aim - p9Acc0.sigma.aim + 1e-6 >= 1.5,
  `Δ=${(p9Acc1.sigma!.aim - p9Acc0.sigma!.aim).toFixed(2)}`,
)

const p9Tag = estimateXh(
  base({
    aimTimeSec: 0.5,
    targetPerpVel: 200,
    residualAccelUuPerSec2: 400,
    dashReady: false,
    crowdControlled: true,
  }),
)
assert(
  'Pass-9: factors expose corrDT+accel aim path',
  p9Tag.factors.some((f) => f.includes('corrDT') && f.includes('accel')),
  p9Tag.factors.join(','),
)
assert(
  'Pass-9: factors expose T_avail (lineup)',
  p9Tag.factors.some((f) => f.startsWith('T_avail:')),
  p9Tag.factors.join(','),
)
```

**Pre-patch expectation:** mono assert fails (`Δ≈+30`); accel asserts fail (`Δ=0`). Post-patch both pass without softening.

---

## arXiv / literature cites

| Id / ref | Use in Pass-9 model |
|----------|---------------------|
| **[1804.05021](https://arxiv.org/abs/1804.05021)** | Aimed-movement phases / discrete corrections — secondary pulses scale with residual primary demand, not a frozen open-loop amp at `T_OPEN`. |
| **[2410.02966](https://arxiv.org/abs/2410.02966)** | OFC+SDN recovers Fitts — longer MT past requirement must not *inflate* endpoint We via stacked correction noise. |
| **[2110.11130](https://arxiv.org/abs/2110.11130)** | Inverse OFC + SDN — command-dependent noise; correction commands ∝ current `D/T` Schmidt velocity. |
| **[2512.17735](https://arxiv.org/abs/2512.17735)** | Interceptive timing under prediction horizon — residual target accel is a predictive uncertainty source (σ), not bias alone. |
| **[2412.04191](https://arxiv.org/abs/2412.04191)** | Forward-model intercept — uncompensated accel residual along engagement clock enters miss variance twin to ZEM extra. |
| Classic (comment cites): Meyer et al. discrete aiming / Crossman–Goodeve intermittent corrections; Harris & Wolpert SDN; Bootsma & van Wieringen coincidence anticipation under accelerating targets; Schmidt We∝D/T. |

---

## Regression note

- **Must hold:** Pass-1…8 Schmidt/Fitts/τ_vm/U_max/FoW-on-σ_corr/WK/Weber/fp/cross/clock⊥motor/`σ_r0`/super-Weber/super-fp/Schmidt⊥rush/radial∥timing/Σ_τvm; **no** `T_avail=t_go`; D∧U excess still ≤500.
- **Risk:** `u0∝D/T` lowers mid/long σ_aim — watch thin-W / aperture / crossing margins (still hypot-additive). Prefer **not** raising rush or Weber knobs to compensate.
- **Risk:** `KAPPA_A` too large → high-accel kits look unhittable even with good lead; keep **0.2–0.35** and assert floor 1.5 uu at A=900.
- **Risk:** Geo Pass-9 may change `zemClock` (first-contact accel epoch) → σ_accel shrinks slightly when ray penetrates early; A=0 still identical. Do not key σ_accel to dodge/Flash.
- **Risk:** Mono fixture must stay U≈1 (`aimTimeSec` 0.45/0.9, W=180); if urgency creeps >1, nudge T/W — do not soften assert.
- Do **not** put `|v_rad|` into crossing clock (Pass-8 `v_time` already projects radial; product excess).
- Do **not** stack `(1+α t_go)` on whole σ_t; do **not** fold missile speed into Fitts MT.

---

## What not to do

- Do **not** set `T_avail = t_go` or fold missile speed into Fitts MT / τ_vm.
- Do **not** multiply `BASE_XH × mobility × zone × vision`.
- Do **not** put kit dash/Flash into σ_aim.
- Do **not** re-propose Pass-1…8 Fitts/SDN/τ_vm/intermittent-*N*/U_max/α_vis/WK/prep/Weber/fp/cross/`σ_c0`/`σ_r0`/super-*/Schmidt⊥rush/radial∥timing/Σ_τvm — only **u0∝D/T** + **σ_accel**.
- Do **not** extend `T_cross` with `|v_rad|` / looming τ (double-counts `v_time`).
- Do **not** put softV / FoW scale on σ_weber, σ_clock, σ_fp, Σ_τvm, σ_accel, or whole σ_aim.
- Do **not** restore `u0 = κ·D/T_OPEN` or `σ_lat∝urgency`.
- Do **not** weaken any existing eval invariant.

---

## Decision

**`KEEP_CANDIDATE`**

Axis-local deepen of Pass-8 residual: scale intermittent correction pulses with current Schmidt demand (**`u0∝D/T`**) to kill anti-Fitts σ_corr saturation, and add **accel variance** `κ_a·|ZEM_accel|` into the σ_aim hypot (twin of geo μ extra). Adds falsifiable invariants (T=0.9≤T=0.45 mono — fails today at +31; accel Δσ≥1.5 — fails today at 0); preserves σ² = σ_aim² + σ_juke² + σ_belief² and public API. Orchestrator: patch `schmidtAimSigma` `u0` + σ_aim hypot accel leg only, append invariants, reject only if `math_pass_rate` drops.

---

**Verdict: `KEEP_CANDIDATE`**
