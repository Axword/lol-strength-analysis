# Pass-2 AIM — Fitts ID gate + correction SDN + angular∥lateral

**Agent:** AIM  
**Baseline:** Post Pass-1 `math_pass_rate=1.0000` (41/41); Schmidt/SDN σ_aim + lineup `T_avail` + timing noise already landed.  
**Scope:** deepen σ_aim only. Do **not** touch eval softening; do **not** edit `src/engine/xh.ts` here (orchestrator applies).  
**Hard rule:** no `BASE×ZONE×VISION` product priors.

**Verdict: `KEEP_CANDIDATE`**

---

## Critique of Pass-1 σ_aim (current `xh.ts`)

Landed block (~389–420):

```ts
const vAim = D / T_avail
let sigmaAim = Math.hypot(SIGMA0, KAPPA_V * vAim, KAPPA_THETA * D, sigmaTiming)
```

| Residual gap | Why it matters |
|--------------|----------------|
| **No Fitts width / ID** | Schmidt uses prescribed `T`; Fitts is the dual — required MT grows with `ID = log₂(1 + D/W)`. Narrow corridor (small `R_hit`) at fixed `T_avail` is time-starved; Pass-1 treats a 50uu-wide Lux Q like a 220uu skillshot for aim noise (width only enters the hit CDF, not σ_aim). |
| **Single SDN channel on primary command** | Harris–Wolpert SDN applies to **every** motor pulse, including late corrective submovements. Pass-1 only puts SDN on `D/T_avail`. Meyer / Crossman–Goodeve: residual after the ballistic phase drives a second command `u_corr ∝ residual/T_corr` whose noise is also signal-dependent. |
| **`κ_θ·D` conflates angular with lateral** | Bearing (direction) encoding error projects as `σ_ang_lat ≈ θ_sd·D` and is largely **T-independent**. Lateral channel SDN scales with aim velocity `D/T`. Collapsing both into one hypot hides which channel a fixture stresses and blocks an angular-vs-lateral invariant. |
| **`schmidtAimSigma(D,T)` ignores W** | Export is not width-aware; cannot unit-test Fitts gating without going through full `estimateXh`. |
| **Timing still OK** | Keep `σ_timing = v_perp·σ_t·(1+α t_go)` — do **not** set `T_avail = t_go`. |

Net: Pass-1 made aim physically real; Pass-2 makes it **dual-SAT** (Schmidt + Fitts) and **multi-pulse SDN** without leaving the σ-corridor factorization.

---

## Math target (aim axis only)

```
W_eff = 2 R_hit                         // full corridor width (uu)
ID    = log2(1 + D / W_eff)             // Shannon–Fitts (MacKenzie)
T★    = a + b · ID                      // Fitts-required MT (s)
urgency = max(1, T★ / T_avail)^β        // time-starved gate (≥1)

T_open = 0.16                           // ballistic / open-loop phase
T_corr = max(0, T_avail − T_open)       // online correction budget

σ_lat  = κ_lat · (D / T_avail) · urgency          // lateral SDN (primary)
u_corr = 1_{T_corr>ε} · [κ_lat · (D / T_open)] / T_corr
σ_corr = κ_c · u_corr                              // SDN on correction magnitude
σ_ang  = κ_θ · D                                   // angular → lateral; T-independent
σ_timing = v_perp · σ_t · (1 + α · t_go)           // unchanged intercept timing

σ_aim² = σ₀² + σ_lat² + σ_ang² + σ_corr² + σ_timing²
T_avail = max(T_min, aimTimeSec ?? T_lineup − ΔT_vision)   // still NOT t_go
```

- **Fitts ID gate:** when `T_avail < T★`, urgency > 1 inflates lateral SDN — narrow/far aims need more time (arXiv:2410.02966 offline+online OFC with SDN recovers Fitts).
- **Correction SDN:** second pulse magnitude ∝ residual/T_corr; rushed online fixes inject noise (Meyer dual-submovement; FITTS phase-2 feedback channel arXiv:1804.05021).
- **Angular ∥ lateral:** separate channels so width gates lateral/correction, not pure bearing noise.

Blind / low `softV`: already shortens `T_avail` (Pass-1). Optionally attenuate the correction channel further under FoW (visual feedback quality) — see snippet — without a flat `σ_aim×1.25`.

---

## Copy-paste patch (for orchestrator → `xh.ts`)

### 1) Optional input (defaults preserve API)

```ts
// Add to XhEstimateInput (optional):
  /** Override Fitts target width (uu). Default = 2·R_hit from missile+champ. */
  fittsWidthUu?: number
```

### 2) Replace helpers — extend / replace `schmidtAimSigma`

```ts
/** Shannon–Fitts index; W is full corridor width (uu). */
export function fittsIndex(D: number, W: number): number {
  const w = Math.max(1, W)
  return Math.log2(1 + Math.max(0, D) / w) // MacKenzie: log2(1 + D/W)
}

/** Fitts-required movement time (s) for game-scale lineup snaps. */
export function fittsRequiredMt(ID: number): number {
  const A = 0.06
  const B = 0.07
  return A + B * Math.max(0, ID)
}

/**
 * Pass-2 aim SD (uu): lateral SDN (Fitts-gated) ⊕ angular ⊕ correction SDN.
 * T_avail = lineup only (not TOF). W = full corridor width.
 */
export function schmidtAimSigma(
  D: number,
  T_avail: number,
  W = 200,
  opts?: { kappaLat?: number; kappaTheta?: number; kappaCorr?: number; beta?: number },
): number {
  const T = Math.max(0.12, T_avail)
  const SIGMA0 = 26
  const KAPPA_LAT = opts?.kappaLat ?? 0.1
  const KAPPA_THETA = opts?.kappaTheta ?? 0.026
  const KAPPA_C = opts?.kappaCorr ?? 0.045
  const BETA = opts?.beta ?? 0.85
  const T_OPEN = 0.16

  const ID = fittsIndex(D, W)
  const Tstar = fittsRequiredMt(ID)
  const urgency = Math.pow(Math.max(1, Tstar / T), BETA)
  const sigmaLat = KAPPA_LAT * (D / T) * urgency
  const sigmaAng = KAPPA_THETA * D

  const T_corr = Math.max(0, T - T_OPEN)
  const residual = KAPPA_LAT * (D / T_OPEN)
  const uCorr = T_corr > 0.02 ? residual / T_corr : 0
  const sigmaCorr = KAPPA_C * uCorr

  return Math.hypot(SIGMA0, sigmaLat, sigmaAng, sigmaCorr)
}
```

### 3) Replace σ_aim block inside `estimateXh` (keep t_go / juke / belief / timing structure)

```ts
  // --- σ_aim: Fitts-gated lateral SDN + angular + correction SDN + timing ---
  // T_avail = pre-release lineup only. Never set T_avail = t_go.
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
  const ID = fittsIndex(D, W_eff)
  const Tstar = fittsRequiredMt(ID)
  const BETA = 0.85
  const urgency = Math.pow(Math.max(1, Tstar / T_avail), BETA)
  factors.push(`fitts_ID:${ID.toFixed(2)}`, `urgency:${urgency.toFixed(2)}`)

  const SIGMA0 = 26
  const KAPPA_LAT = 0.1
  const KAPPA_THETA = 0.026
  const KAPPA_C = 0.045
  const T_OPEN = 0.16

  // Lateral channel: primary command SDN × Fitts urgency
  const sigmaLat = KAPPA_LAT * (D / T_avail) * urgency
  // Angular / bearing channel → lateral at range (T-independent)
  const sigmaAng = KAPPA_THETA * D

  // Correction SDN: residual after ballistic phase / T_corr (Meyer dual-submovement)
  const T_corr = Math.max(0, T_avail - T_OPEN)
  const residual = KAPPA_LAT * (D / T_OPEN)
  let uCorr = T_corr > 0.02 ? residual / T_corr : 0
  // FoW: weak visual feedback → less useful online correction (open-loop residual remains in lat/ang)
  if (softV < 0.5) uCorr *= softV / 0.5
  const sigmaCorr = KAPPA_C * uCorr

  // Interception timing (unchanged factorization; reinforces slow-missile disadvantage)
  const sigmaT = Math.max(0.02, input.releaseJitterSec ?? 0.045)
  const ALPHA_TOF = 0.55
  const sigmaTiming = vPerp * sigmaT * (1 + ALPHA_TOF * tGo)

  let sigmaAim = Math.hypot(SIGMA0, sigmaLat, sigmaAng, sigmaCorr, sigmaTiming)
  if (casterZone === 'brush') {
    sigmaAim *= 0.94
    factors.push('aim:caster_brush')
  }
  factors.push('aim:fitts+sdn_lat+ang+corr+timing')
```

**Calibration knobs (if eval margins shrink):** lower `BETA` (0.6–0.85) or `KAPPA_C` first; then `KAPPA_LAT`. Do **not** soften eval. Keep `ALPHA_TOF` unless `faster missile → higher xH` fails.

**Expected invariant gains:** new Fitts-ID / width / angular-vs-lateral / correction checks below; Pass-1 Schmidt `T_avail` + missile/timing inequalities should hold because urgency ≥ 1 and correction SDN shrinks as `T_avail` grows.

---

## New invariants to add to `scripts/eval-xh-math.ts`

Do **not** remove or weaken existing checks. Append after Pass-1 AIM block:

```ts
// --- aim / Fitts ID + correction SDN + angular∥lateral (Pass-2 AIM) ---

const wideFitts = estimateXh(
  base({
    missileWidth: 220,
    aimTimeSec: 0.28,
    dashReady: false,
    crowdControlled: true,
  }),
)
const thinFitts = estimateXh(
  base({
    missileWidth: 50,
    aimTimeSec: 0.28,
    dashReady: false,
    crowdControlled: true,
  }),
)
assert(
  'narrower W → larger sigma.aim (Fitts ID gate)',
  !!wideFitts.sigma &&
    !!thinFitts.sigma &&
    thinFitts.sigma.aim > wideFitts.sigma.aim,
  `thin=${thinFitts.sigma?.aim.toFixed(1)} wide=${wideFitts.sigma?.aim.toFixed(1)}`,
)
assert(
  'factors expose fitts_ID',
  thinFitts.factors.some((f) => f.startsWith('fitts_ID:')),
  thinFitts.factors.join(','),
)

const nearId = estimateXh(
  base({
    targetPosition: { x: mid.x + 0.012, y: mid.y },
    abilityRange: 700,
    missileWidth: 140,
    aimTimeSec: 0.3,
    dashReady: false,
    crowdControlled: true,
  }),
)
const farId = estimateXh(
  base({
    targetPosition: far,
    abilityRange: 1175,
    missileWidth: 140,
    aimTimeSec: 0.3,
    dashReady: false,
    crowdControlled: true,
    flashReady: false,
  }),
)
assert(
  'same T,W: farther D → larger sigma.aim (ID + D/T)',
  !!nearId.sigma && !!farId.sigma && farId.sigma.aim > nearId.sigma.aim,
  `near=${nearId.sigma?.aim.toFixed(1)} far=${farId.sigma?.aim.toFixed(1)}`,
)

// Angular channel: at very long T_avail, urgency→1 and σ_corr→0;
// remaining D-scaling is dominated by κ_θ·D (angular) + floor.
const angShort = estimateXh(
  base({
    targetPosition: { x: mid.x + 0.015, y: mid.y },
    abilityRange: 700,
    aimTimeSec: 0.55,
    dashReady: false,
    crowdControlled: true,
    targetMovespeed: 200,
    releaseJitterSec: 0.02,
  }),
)
const angFar = estimateXh(
  base({
    targetPosition: far,
    abilityRange: 1175,
    missileWidth: 160,
    aimTimeSec: 0.55,
    dashReady: false,
    crowdControlled: true,
    flashReady: false,
    targetMovespeed: 200,
    releaseJitterSec: 0.02,
  }),
)
assert(
  'long T_avail: farther D still raises sigma.aim (angular κ_θ·D)',
  !!angShort.sigma && !!angFar.sigma && angFar.sigma.aim > angShort.sigma.aim,
  `shortD=${angShort.sigma?.aim.toFixed(1)} farD=${angFar.sigma?.aim.toFixed(1)}`,
)

// Correction SDN: mid T (one rushed correction) vs long T (gentle/no correction)
const corrRush = estimateXh(
  base({ aimTimeSec: 0.2, dashReady: false, crowdControlled: true }),
)
const corrLong = estimateXh(
  base({ aimTimeSec: 0.5, dashReady: false, crowdControlled: true }),
)
assert(
  'rushed correction budget → larger sigma.aim than long lineup',
  !!corrRush.sigma &&
    !!corrLong.sigma &&
    corrRush.sigma.aim > corrLong.sigma.aim,
  `rush=${corrRush.sigma?.aim.toFixed(1)} long=${corrLong.sigma?.aim.toFixed(1)}`,
)

// Guard: urgency factor present when ID is high / T short
assert(
  'factors expose urgency',
  thinFitts.factors.some((f) => f.startsWith('urgency:')),
  thinFitts.factors.join(','),
)

// Preserve Pass-1 missile timing inequality under new σ_aim
const fastMis2 = estimateXh(
  base({
    missileSpeed: 2800,
    aimTimeSec: 0.35,
    dashReady: false,
    crowdControlled: true,
  }),
)
const slowMis2 = estimateXh(
  base({
    missileSpeed: 800,
    aimTimeSec: 0.35,
    dashReady: false,
    crowdControlled: true,
  }),
)
assert(
  'Pass-2: slower missile → sigma.aim ≥ faster (TOF horizon ≠ T_avail)',
  !!slowMis2.sigma &&
    !!fastMis2.sigma &&
    slowMis2.sigma.aim + 1e-6 >= fastMis2.sigma.aim,
  `slow=${slowMis2.sigma?.aim.toFixed(1)} fast=${fastMis2.sigma?.aim.toFixed(1)}`,
)
```

If `fittsWidthUu` is added, an optional override check:

```ts
const forcedNarrow = estimateXh(
  base({ fittsWidthUu: 60, aimTimeSec: 0.28, dashReady: false, crowdControlled: true }),
)
const forcedWide = estimateXh(
  base({ fittsWidthUu: 280, aimTimeSec: 0.28, dashReady: false, crowdControlled: true }),
)
assert(
  'fittsWidthUu override: narrower → larger sigma.aim',
  !!forcedNarrow.sigma &&
    !!forcedWide.sigma &&
    forcedNarrow.sigma.aim > forcedWide.sigma.aim,
)
```

---

## arXiv / literature cites

| Id / ref | Use in Pass-2 model |
|----------|---------------------|
| **[2410.02966](https://arxiv.org/abs/2410.02966)** | Offline + online OFC with SDN recovers Fitts SAT — justifies **urgency / ID gate** on lateral σ when `T_avail < T★`. |
| **[1804.05021](https://arxiv.org/abs/1804.05021)** | FITTS: aimed trajectories = ballistic variance growth then feedback variance decay — maps to **T_open / T_corr** split and correction channel. |
| **[2103.08558](https://arxiv.org/abs/2103.08558)** | Intermittent corrective impulses / dual-submovement variability — supports **σ_corr ∝ u_corr**. |
| **[2110.11130](https://arxiv.org/abs/2110.11130)** | Inverse OFC + human SDN — multiplicative noise on **all** command magnitudes (primary + correction). |
| **[2107.00814](https://arxiv.org/abs/2107.00814)** | Limb-production review; Harris–Wolpert SDN as minimum-variance core. |
| Classic (non-arXiv, comment cites): Fitts 1954; MacKenzie Shannon-Fitts `log₂(1+D/W)`; Schmidt et al. 1979 (We∝D/T); Meyer et al. 1988 optimized dual-submovement; Crossman & Goodeve 1983 iterative corrections; Harris & Wolpert 1998 *Nature*; van Beers et al. 2004 (directional / execution noise anisotropy — angular vs extent). |

---

## What not to do

- Do **not** set `T_avail = t_go` or fold missile speed into the Fitts MT.
- Do **not** multiply `BASE_XH × mobility × zone × vision`.
- Do **not** put kit dash/Flash into σ_aim (still σ_juke / budgets).
- Do **not** gate `σ_belief` or `μ_bias` with Fitts ID — aim axis only.
- Do **not** import PN/homing mid-flight steering.
- Do **not** weaken `faster missile → higher xH` or Pass-1 Schmidt `T_avail` checks.

---

## Decision

**`KEEP_CANDIDATE`**

Axis-local deepen of Pass-1: Fitts ID urgency on lateral SDN, separate angular channel, Meyer-style correction SDN, same lineup `T_avail` + timing factorization. Adds falsifiable width/ID/correction invariants; preserves σ² = σ_aim² + σ_juke² + σ_belief² and public API. Orchestrator: apply helper + σ_aim replacement (+ optional `fittsWidthUu`), append invariants, reject only if `math_pass_rate` drops.
