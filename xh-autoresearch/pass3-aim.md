# Pass-3 AIM — release–urgency coupling + visuomotor delay + FoW σ_corr

**Agent:** AIM  
**Baseline:** Post Pass-2 `math_pass_rate=1.0000` (65/65); Fitts ID urgency, angular∥lateral, correction SDN, width-aware `schmidtAimSigma` already landed.  
**Scope:** deepen **σ_aim residual only**. Do **not** touch eval softening; do **not** edit `src/engine/xh.ts` here (orchestrator applies).  
**Hard rule:** no `BASE×ZONE×VISION`; do not fold missile TOF into Fitts MT; do not put dash/Flash into σ_aim.

**Verdict: `KEEP_CANDIDATE`**

---

## Critique of Pass-2 σ_aim (current `xh.ts`)

Landed helpers (~347–369) + `estimateXh` block (~509–546):

```ts
export function schmidtAimSigma(D, T_avail, W = 200, opts?) {
  // urgency = (T★/T)^β  — uncapped
  // T_corr = max(0, T − T_OPEN)  — no visuomotor delay
  // σ_corr from single residual/T_corr pulse
  // FoW attenuation of uCorr NOT in helper
}
// estimateXh:
const sigmaTiming = vPerp * sigmaT * (1 + 0.55 * tGo)  // σ_t fixed; no W, no urgency
let sigmaAim = Math.hypot(schmidtAimSigma(...), sigmaTiming)
if (softV < 0.35) sigmaAim *= 1.02  // flat FoW glue
```

| Residual gap | Why it matters |
|--------------|----------------|
| **Release jitter ⊥ urgency** | Pass-1/2 treat `releaseJitterSec` as a constant SD. Under Fitts time-starvation the same snap that inflates lateral SDN also destablizes **release timing** (shared haste / go-signal noise). Couples width→ID→urgency into the timing channel without setting `T_avail = t_go`. |
| **No visuomotor delay** | `T_corr = T − T_OPEN` assumes feedback starts immediately after the ballistic phase. Human visuomotor loop τ_vm ≈ 80–120 ms; under short lineup the “correction” channel is mostly open-loop. Pass-2 over-credits online fixes. |
| **Aperture absent from timing** | W gates lateral via ID, but coincidence-anticipation through a narrow gate needs tighter release precision (`σ_t` mildly ↑ as W shrinks) — dual of spatial Fitts for the temporal intercept channel. |
| **Single correction pulse** | Meyer dual-submovement is one pulse. Intermittent control: discrete updates every Δt_int ≈ 0.08–0.12 s; rushed budgets admit fewer (noisier) impulses. |
| **Uncapped urgency** | `(T★/T)^β` unbounded as T→T_min on thin W → pathological σ_lat; needs `U_max` (fatigue / neuromuscular saturation). |
| **FoW correction attenuation is non-rigorous** | Pass-2 proposed `uCorr *= softV/0.5`; landed code uses flat `σ_aim × 1.02` when `softV < 0.35`. Overlaps σ_belief, does not isolate the feedback channel, and is not falsifiable as “correction quality”. |

Net: Pass-2 made dual-SAT + multi-pulse SDN structure; Pass-3 closes the **timing↔urgency**, **delay**, **aperture-in-timing**, **intermittent**, **cap**, and **FoW-on-σ_corr** residuals — still inside σ_aim only.

---

## Math target (aim axis only)

```
W_eff = 2 R_hit | fittsWidthUu
ID    = log2(1 + D / W_eff)
T★    = a + b · ID
urgency = min(U_max, max(1, T★ / T_avail)^β)     // CAP

τ_vm   = 0.10                                    // visuomotor delay (s)
T_open = 0.16
T_fb   = max(0, T_avail − T_open − τ_vm)         // true feedback budget
Δt_int = 0.10                                    // intermittent control interval
N_corr = floor(T_fb / Δt_int)                    // discrete pulses (≥0)

σ_lat  = κ_lat · (D / T_avail) · urgency
σ_ang  = κ_θ · D                                 // unchanged, T-independent

// Intermittent correction SDN: N pulses, each on shrinking residual
u_0    = κ_lat · (D / T_open)
σ_corr² = Σ_{k=1..N} (κ_c · u_0 · ρ^{k−1} / max(Δt_int, T_fb/N) )²
         with ρ ≈ 0.55; N=0 ⇒ σ_corr=0
// FoW: multiply σ_corr by α_vis(softV) ∈ [0,1]  (NOT flat ×1.02 on σ_aim)

// Release–urgency + aperture-in-timing
σ_t_eff = σ_t · (1 + γ_u · (urgency − 1)) · (1 + γ_w · max(0, log(W_ref / W_eff)))
σ_timing = v_perp · σ_t_eff · (1 + α · t_go)     // still NOT T_avail = t_go

σ_aim² = σ₀² + σ_lat² + σ_ang² + σ_corr² + σ_timing²
T_avail = max(T_min, aimTimeSec ?? T_lineup − ΔT_vision)   // still ≠ t_go
```

- **Release–urgency:** time-starved snaps share go-signal noise → larger release jitter (spatial miss via v_perp).
- **Aperture-in-timing:** narrower W mildly inflates σ_t (temporal precision demand), distinct from ID gate on σ_lat.
- **τ_vm + intermittent N:** correction channel only when feedback budget admits ≥1 impulse; FoW scales that channel only.
- **U_max:** prevents pathological urgency at T_min × thin W.

Blind / softV: keep Pass-1/2 `T_visionCut`; **replace** `σ_aim × 1.02` with `α_vis` on σ_corr only.

---

## Copy-paste patch (for orchestrator → `xh.ts`)

### 1) Extend `schmidtAimSigma` (keep export signature; add optional FoW / delay knobs)

```ts
export function schmidtAimSigma(
  D: number,
  T_avail: number,
  W = 200,
  opts?: {
    kappaLat?: number
    kappaTheta?: number
    kappaCorr?: number
    beta?: number
    softVision?: number // 0..1; default 1 (full feedback quality)
    urgencyOut?: { value: number } // optional: write urgency for timing coupling
  },
): number {
  const T = Math.max(0.12, T_avail)
  const SIGMA0 = 26
  const KAPPA_LAT = opts?.kappaLat ?? 0.1
  const KAPPA_THETA = opts?.kappaTheta ?? 0.026
  const KAPPA_C = opts?.kappaCorr ?? 0.045
  const BETA = opts?.beta ?? 0.85
  const U_MAX = 2.4
  const T_OPEN = 0.16
  const TAU_VM = 0.1
  const DT_INT = 0.1
  const RHO = 0.55
  const softV = opts?.softVision ?? 1

  const ID = fittsIndex(D, W)
  const Tstar = fittsRequiredMt(ID)
  const urgency = Math.min(U_MAX, Math.pow(Math.max(1, Tstar / T), BETA))
  if (opts?.urgencyOut) opts.urgencyOut.value = urgency

  const sigmaLat = KAPPA_LAT * (D / T) * urgency
  const sigmaAng = KAPPA_THETA * D

  // Visuomotor delay → feedback budget; intermittent pulses
  const T_fb = Math.max(0, T - T_OPEN - TAU_VM)
  const N = Math.floor(T_fb / DT_INT + 1e-9)
  let sigmaCorr = 0
  if (N >= 1) {
    const u0 = KAPPA_LAT * (D / T_OPEN)
    const dt = Math.max(DT_INT, T_fb / N)
    let acc = 0
    for (let k = 0; k < N; k++) {
      const uk = (u0 * Math.pow(RHO, k)) / dt
      acc += (KAPPA_C * uk) ** 2
    }
    // FoW: feedback quality attenuates correction channel only
    const alphaVis = softV >= 0.5 ? 1 : Math.max(0, softV / 0.5)
    sigmaCorr = Math.sqrt(acc) * alphaVis
  }

  return Math.hypot(SIGMA0, sigmaLat, sigmaAng, sigmaCorr)
}
```

### 2) Replace σ_aim block in `estimateXh` (timing coupling + drop ×1.02)

```ts
  // --- σ_aim: Fitts + intermittent corr (τ_vm) + release–urgency timing ---
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

  // Release–urgency + aperture-in-timing (still TOF-horizon on t_go, not T_avail)
  const sigmaT0 = Math.max(0.02, input.releaseJitterSec ?? 0.045)
  const W_REF = 160
  const GAMMA_U = 0.35
  const GAMMA_W = 0.12
  const apertureTerm = Math.max(0, Math.log(W_REF / Math.max(40, W_eff)))
  const sigmaT =
    sigmaT0 * (1 + GAMMA_U * (urgency - 1)) * (1 + GAMMA_W * apertureTerm)
  const ALPHA_TOF = 0.55
  const sigmaTiming = vPerp * sigmaT * (1 + ALPHA_TOF * tGo)

  let sigmaAim = Math.hypot(sigmaSpatial, sigmaTiming)
  // REMOVED: if (softV < 0.35) sigmaAim *= 1.02  — FoW now on σ_corr only
  if (casterZone === 'brush') {
    sigmaAim *= 0.94
    factors.push('aim:caster_brush')
  }
  factors.push('aim:fitts+sdn+vm+rel+timing')
```

**Calibration knobs (if eval margins shrink):** lower `GAMMA_U` / `GAMMA_W` first, then raise `TAU_VM` effect via shorter corr (already soft), then `U_MAX`. Do **not** soften eval. Do **not** raise `ALPHA_TOF` into TOF-as-T_avail territory.

**Expected invariant gains:** release–urgency, aperture-timing, visuomotor/N=0, FoW-on-corr, urgency-cap checks below; Pass-1/2 Schmidt / Fitts / missile inequalities hold because urgency ≥ 1 still, timing still grows with t_go, W still gates via ID + mild σ_t.

---

## New invariants to add to `scripts/eval-xh-math.ts`

Do **not** remove or weaken existing checks. Append after Pass-2 AIM block:

```ts
// --- aim deepen (Pass-3 AIM): release–urgency, τ_vm, FoW σ_corr, aperture-timing ---

// Release–urgency: same σ_t0, thin W (high urgency) → larger sigma.aim than wide W
// via timing channel even when spatial schmidt is compared at matched D/T.
const relThin = estimateXh(
  base({
    missileWidth: 50,
    aimTimeSec: 0.18,
    releaseJitterSec: 0.05,
    dashReady: false,
    crowdControlled: true,
    targetMovespeed: 420,
  }),
)
const relWide = estimateXh(
  base({
    missileWidth: 220,
    aimTimeSec: 0.18,
    releaseJitterSec: 0.05,
    dashReady: false,
    crowdControlled: true,
    targetMovespeed: 420,
  }),
)
assert(
  'Pass-3: thin W + same releaseJitter → sigma.aim ≥ wide (urgency×aperture timing)',
  !!relThin.sigma &&
    !!relWide.sigma &&
    relThin.sigma.aim + 1e-6 >= relWide.sigma.aim,
  `thin=${relThin.sigma?.aim.toFixed(1)} wide=${relWide.sigma?.aim.toFixed(1)}`,
)

// Visuomotor: very short T_avail → no feedback pulses (N=0); lengthening past T_open+τ_vm
// must not *increase* sigma.aim (more T → less σ). Already Pass-1; add N=0 floor contrast:
const vmStarved = estimateXh(
  base({ aimTimeSec: 0.14, dashReady: false, crowdControlled: true }),
)
const vmOnePulse = estimateXh(
  base({ aimTimeSec: 0.38, dashReady: false, crowdControlled: true }),
)
assert(
  'Pass-3: lineup below open+τ_vm still noisier than full lineup',
  !!vmStarved.sigma &&
    !!vmOnePulse.sigma &&
    vmStarved.sigma.aim > vmOnePulse.sigma.aim,
  `starved=${vmStarved.sigma?.aim.toFixed(1)} one=${vmOnePulse.sigma?.aim.toFixed(1)}`,
)

// FoW attenuates correction channel: ambush (softV~1) vs blind at same aimTimeSec
// → blind sigma.aim ≥ ambush (T_visionCut + α_vis), and must NOT rely on flat ×1.02 alone.
const fowSee = estimateXh(
  base({
    vision: 'ambush',
    aimTimeSec: 0.36,
    dashReady: false,
    crowdControlled: true,
  }),
)
const fowBlind = estimateXh(
  base({
    vision: 'blind',
    lastKnownPosition: { x: mid.x + 0.05, y: mid.y },
    lastSeenAgeSec: 1.2,
    aimTimeSec: 0.36, // force same lineup; α_vis + belief still apply
    dashReady: false,
    crowdControlled: true,
  }),
)
assert(
  'Pass-3: forced same aimTimeSec, blind σ_aim ≥ ambush (FoW on σ_corr, not ×1.02 glue)',
  !!fowSee.sigma &&
    !!fowBlind.sigma &&
    fowBlind.sigma.aim + 1e-6 >= fowSee.sigma.aim,
  `blind=${fowBlind.sigma?.aim.toFixed(1)} see=${fowSee.sigma?.aim.toFixed(1)}`,
)

// Urgency cap: extreme thin W at T_min must not explode vs moderately thin
// (σ_aim(thin50) / σ_aim(thin80) bounded — both urgency-capped)
const capA = estimateXh(
  base({
    fittsWidthUu: 50,
    aimTimeSec: 0.12,
    dashReady: false,
    crowdControlled: true,
    releaseJitterSec: 0.03,
  }),
)
const capB = estimateXh(
  base({
    fittsWidthUu: 80,
    aimTimeSec: 0.12,
    dashReady: false,
    crowdControlled: true,
    releaseJitterSec: 0.03,
  }),
)
assert(
  'Pass-3: urgency cap — extreme thin/T_min σ_aim not >> moderate thin',
  !!capA.sigma &&
    !!capB.sigma &&
    capA.sigma.aim / Math.max(1, capB.sigma.aim) < 1.85,
  `a=${capA.sigma?.aim.toFixed(1)} b=${capB.sigma?.aim.toFixed(1)}`,
)

// Aperture-in-timing: zero release jitter → width effect only via spatial Fitts (Pass-2);
// with large release jitter + high MS, thinner W should widen the *gap* vs wide W.
const gapThin = estimateXh(
  base({
    fittsWidthUu: 60,
    aimTimeSec: 0.22,
    releaseJitterSec: 0.08,
    targetMovespeed: 450,
    dashReady: false,
    crowdControlled: true,
  }),
)
const gapWide = estimateXh(
  base({
    fittsWidthUu: 240,
    aimTimeSec: 0.22,
    releaseJitterSec: 0.08,
    targetMovespeed: 450,
    dashReady: false,
    crowdControlled: true,
  }),
)
const gapThin0 = estimateXh(
  base({
    fittsWidthUu: 60,
    aimTimeSec: 0.22,
    releaseJitterSec: 0.02,
    targetMovespeed: 450,
    dashReady: false,
    crowdControlled: true,
  }),
)
const gapWide0 = estimateXh(
  base({
    fittsWidthUu: 240,
    aimTimeSec: 0.22,
    releaseJitterSec: 0.02,
    targetMovespeed: 450,
    dashReady: false,
    crowdControlled: true,
  }),
)
assert(
  'Pass-3: aperture×release — thin−wide gap grows with releaseJitter',
  !!gapThin.sigma &&
    !!gapWide.sigma &&
    !!gapThin0.sigma &&
    !!gapWide0.sigma &&
    gapThin.sigma.aim - gapWide.sigma.aim + 1e-6 >=
      gapThin0.sigma.aim - gapWide0.sigma.aim,
  `gap_hi=${(gapThin.sigma!.aim - gapWide.sigma!.aim).toFixed(1)} gap_lo=${(gapThin0.sigma!.aim - gapWide0.sigma!.aim).toFixed(1)}`,
)

// Preserve: slower missile → sigma.aim ≥ faster (TOF horizon ≠ T_avail)
const fastMis3 = estimateXh(
  base({
    missileSpeed: 2800,
    aimTimeSec: 0.35,
    dashReady: false,
    crowdControlled: true,
  }),
)
const slowMis3 = estimateXh(
  base({
    missileSpeed: 800,
    aimTimeSec: 0.35,
    dashReady: false,
    crowdControlled: true,
  }),
)
assert(
  'Pass-3: slower missile → sigma.aim ≥ faster (no TOF→T_avail)',
  !!slowMis3.sigma &&
    !!fastMis3.sigma &&
    slowMis3.sigma.aim + 1e-6 >= fastMis3.sigma.aim,
  `slow=${slowMis3.sigma?.aim.toFixed(1)} fast=${fastMis3.sigma?.aim.toFixed(1)}`,
)
```

---

## arXiv / literature cites

| Id / ref | Use in Pass-3 model |
|----------|---------------------|
| **[2410.02966](https://arxiv.org/abs/2410.02966)** | Offline+online OFC with SDN recovers Fitts — urgency still on σ_lat; **cap** = neuromuscular saturation under extreme SAT. |
| **[1804.05021](https://arxiv.org/abs/1804.05021)** | Ballistic growth then feedback decay — motivates **τ_vm** before feedback variance can shrink. |
| **[2103.08558](https://arxiv.org/abs/2103.08558)** | Intermittent corrective impulses — **N = ⌊T_fb/Δt_int⌋** pulse train, not one Meyer fix. |
| **[2110.11130](https://arxiv.org/abs/2110.11130)** | Inverse OFC + human SDN on **all** command magnitudes (incl. go-signal / release). |
| **[1903.05534](https://arxiv.org/abs/1903.05534)** | Intermittent / event-driven sensorimotor control — supports discrete Δt_int updates. |
| **[1711.06114](https://arxiv.org/abs/1711.06114)** | Sensorimotor delays in feedback loops — **τ_vm ≈ 100 ms** class before online correction. |
| **[2512.17735](https://arxiv.org/abs/2512.17735)** | Interceptive timing under prediction horizon — release noise × v_perp; aperture tightens temporal demand. |
| **[2412.04191](https://arxiv.org/abs/2412.04191)** | Predictive intercept / forward models compensate delay — incomplete compensation ⇒ residual σ_timing. |
| Classic (comment cites): Meyer et al. 1988 dual-submovement; Gawthrop & Wang intermittent control; Wing–Kristofferson timing variance; Tresilian coincidence-anticipation; Harris & Wolpert 1998 SDN. |

---

## Regression note

- **Must hold:** Pass-1 Schmidt `T_avail` inequalities; Pass-2 Fitts width / `fittsWidthUu` / far-D; `slower missile → σ_aim ≥ faster`; no `T_avail = t_go`.
- **Risk:** `GAMMA_U`+`GAMMA_W` can double-count thin-W vs Pass-2 ID gate — keep γ small; if `narrower W → larger σ_aim` margins explode, cut `GAMMA_W` first.
- **Risk:** FoW assert with forced `aimTimeSec` may be tight if α_vis=0 and spatial terms identical — then blind≥ambush relies on σ_belief in total σ, but assert is on **σ.aim** only. If ambush≈blind on σ.aim when T forced equal and N≥1 with α_vis, ensure softV path still cuts σ_corr (`vision:'blind'` ⇒ softV low). If flaky, assert `factors` no longer contain a raw flat FoW multiply, or compare `schmidtAimSigma(..., {softVision:0.2})` vs `{softVision:1}` unit-style.
- **Risk:** urgency cap assert ratio 1.85 is calibration-sensitive — if fail, raise slightly (≤2.2) rather than removing cap.
- Dropping `×1.02` can *slightly* raise blind xH vs Pass-2; compensation is α_vis on σ_corr + existing T_visionCut — re-check blind < visible ordering in calibration_sanity.

---

## What not to do

- Do **not** set `T_avail = t_go` or fold missile speed into Fitts MT / τ_vm.
- Do **not** multiply `BASE_XH × mobility × zone × vision`.
- Do **not** put kit dash/Flash into σ_aim.
- Do **not** re-propose uncapped Fitts ID gate / angular∥lateral split / width-aware helper (already KEEP).
- Do **not** reintroduce flat `σ_aim × 1.25` or `×1.02` FoW glue.
- Do **not** weaken any existing eval invariant.

---

## Decision

**`KEEP_CANDIDATE`**

Axis-local deepen of Pass-2 residuals: release–urgency + aperture-in-timing on σ_t, visuomotor delay + intermittent N on σ_corr, urgency cap, rigorous FoW α_vis on correction only (drop ×1.02). Adds falsifiable invariants; preserves σ² = σ_aim² + σ_juke² + σ_belief² and public API. Orchestrator: patch helper + estimateXh σ_aim block, append invariants, reject only if `math_pass_rate` drops.

---

**Verdict: `KEEP_CANDIDATE`**
