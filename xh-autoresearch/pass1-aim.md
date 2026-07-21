# Pass-1 AIM — Schmidt–Fitts / SDN / T_avail / interception

**Agent:** AIM  
**Baseline:** `math_pass_rate=1.0000` (20/20) on `scripts/eval-xh-math.ts`  
**Scope:** deepen σ_aim only. Do **not** touch eval softening; do **not** edit `src/engine/xh.ts` here (conflict — orchestrator applies).  
**Hard rule:** no mobility×zone product priors.

**Verdict: `KEEP_CANDIDATE`**

---

## Critique of current σ_aim

Current block (`estimateXh`):

```ts
const T_avail = Math.max(0.12, 0.42)
const D = dist
let sigmaAim = Math.hypot(35, 0.12 * (D / T_avail), 0.04 * D)
```

| Issue | Why it matters |
|-------|----------------|
| **`T_avail` is a constant** | `Math.max(0.12, 0.42)` ≡ `0.42`. Schmidt’s law is `We ≈ a + b·(D/T)` with **prescribed** movement time `T`. Fixed `T` collapses Schmidt to “σ ∝ D” — no speed–accuracy knob. |
| **TOF correctly excluded from T** | Comment is right: using `t_go` as aim time falsely punishes fast missiles. Keep lineup ≠ TOF. |
| **No SDN structure** | Harris–Wolpert SDN: control noise **variance** scales with command magnitude (≈ aim velocity `D/T`). Formula is ad-hoc linear mix, not `σ₀ ⊕ κ·(D/T)`. |
| **Double D-scaling** | Both `0.12·(D/T)` and `0.04·D` track range; with fixed `T` they are collinear. Prefer one Schmidt velocity term + one angular term (or drop angular). |
| **Interception timing missing** | Lead residual lives only in `muBias = vPerp·tGo·(1−leadSkill)`. Release-time jitter and long-horizon lead **noise** (not bias) never enter `σ_aim`. Slow missiles should widen aim/planning noise via prediction horizon, not via fake larger `T_avail`. |
| **Blind×1.25 on σ_aim** | Partially overlaps σ_belief. Prefer shorter effective `T_avail` under blind (less closed-loop correction) rather than a flat multiplier — keeps factorization clean. |

Net: geometry/juke/belief carry most of the eval; aim is the weakest physical factor despite the program’s “Schmidt–Fitts” bullet.

---

## Math target (aim axis only)

```
σ_aim² = σ₀² + (κ_v · D / T_avail)² + (κ_θ · D)² + σ_timing²
T_avail = max(T_min, T_lineup − ΔT_vision)     // NOT t_go
σ_timing = v_perp · σ_t_release · (1 + α · t_go) // interception horizon
```

- **Schmidt (linear We vs D/T):** Wright & Meyer–style linear speed–accuracy under temporal constraint; Fitts is the dual (time vs ID) — we need Schmidt form for open-loop skillshot snaps.
- **SDN:** κ_v·(D/T) is the SD form of signal-dependent motor noise on the aim command.
- **Interception:** coincidence-anticipation / predictive intercept — timing error × lateral target speed; mild growth with `t_go` (longer prediction horizon).

---

## Copy-paste patch (for orchestrator → `xh.ts`)

### 1) Extend input (optional; defaults preserve API)

```ts
// Add to XhEstimateInput:
  /** Pre-release aim / lineup budget (s). Default from vision; NOT missile TOF. */
  aimTimeSec?: number
  /** Release-time jitter SD (s) for interception timing noise. Default 0.045. */
  releaseJitterSec?: number
```

### 2) Replace σ_aim block (keep t_go / juke / belief unchanged)

```ts
  // --- σ_aim: Schmidt–Fitts (We ∝ D/T) + SDN + interception timing ---
  // T_avail = pre-release lineup only. Never set T_avail = t_go
  // (that falsely hurts fast missiles via aim instead of via dodge window).
  const T_min = 0.12
  const T_lineup = 0.38
  // Blind: less useful closed-loop visual correction → shorter effective T (open-loop Schmidt regime).
  // Ambush/mutual: full lineup; caster already sees target.
  const T_visionCut =
    vision === 'blind' ? 0.14 : vision === 'unknown' ? 0.06 : 0
  const T_avail = Math.max(
    T_min,
    input.aimTimeSec ?? T_lineup - T_visionCut,
  )
  factors.push(`T_avail:${T_avail.toFixed(2)}s`)

  const D = dist
  const vAim = D / T_avail // Schmidt mean aim “velocity” (uu/s)
  // σ₀: additive neuromuscular floor
  // κ_v: Schmidt / SDN coefficient on D/T  (Harris–Wolpert SD ∝ |u|)
  // κ_θ: small angular aim noise → lateral at range (independent of T)
  const SIGMA0 = 28
  const KAPPA_V = 0.11
  const KAPPA_THETA = 0.028

  // Interception timing: release jitter × lateral target speed; grows mildly with t_go
  // (longer predictive horizon → noisier intercept plan). Does not replace muBias.
  const sigmaT = Math.max(0.02, input.releaseJitterSec ?? 0.045)
  const vPerpAim = ms * 0.4
  const ALPHA_TOF = 0.55
  const sigmaTiming = vPerpAim * sigmaT * (1 + ALPHA_TOF * tGo)

  let sigmaAim = Math.hypot(
    SIGMA0,
    KAPPA_V * vAim,
    KAPPA_THETA * D,
    sigmaTiming,
  )
  // Drop flat blind×1.25 — T_avail cut + σ_belief already cover FoW.
  if (casterZone === 'brush') {
    sigmaAim *= 0.94
    factors.push('aim:caster_brush')
  }
  factors.push(`aim:schmidt+sdn+timing`)
```

### 3) Optional tiny export for unit-style checks (eval can import)

```ts
/** Schmidt+SDN spatial aim SD (uu); T_avail must be lineup time, not TOF. */
export function schmidtAimSigma(D: number, T_avail: number): number {
  const T = Math.max(0.12, T_avail)
  return Math.hypot(28, 0.11 * (D / T), 0.028 * D)
}
```

**Calibration note:** After apply, re-run eval. If `point-blank CC` or `faster missile` margins shrink, lower `ALPHA_TOF` (0.35–0.55) or `KAPPA_V` first — do **not** soften eval.

**Expected invariant gains:** new aim-axis checks below; existing 20/20 should hold if `T_avail` stays independent of missile speed and timing noise only *reinforces* slow-missile disadvantage.

---

## New invariants to add to `scripts/eval-xh-math.ts`

Do **not** remove or weaken existing checks. Append:

```ts
// --- aim / Schmidt–SDN / interception (Pass-1 AIM) ---

const aimLongT = estimateXh(base({ aimTimeSec: 0.55, dashReady: false }))
const aimShortT = estimateXh(base({ aimTimeSec: 0.14, dashReady: false }))
assert(
  'shorter T_avail → lower xH (Schmidt)',
  aimShortT.xH < aimLongT.xH,
  `short=${aimShortT.xH.toFixed(3)} long=${aimLongT.xH.toFixed(3)}`,
)
assert(
  'shorter T_avail → larger sigma.aim',
  !!aimShortT.sigma &&
    !!aimLongT.sigma &&
    aimShortT.sigma.aim > aimLongT.sigma.aim,
  `σ_short=${aimShortT.sigma?.aim.toFixed(1)} σ_long=${aimLongT.sigma?.aim.toFixed(1)}`,
)

const nearAim = estimateXh(
  base({
    targetPosition: { x: mid.x + 0.015, y: mid.y },
    abilityRange: 700,
    aimTimeSec: 0.35,
    dashReady: false,
    crowdControlled: true,
  }),
)
const farAim = estimateXh(
  base({
    targetPosition: far,
    abilityRange: 1175,
    aimTimeSec: 0.35,
    missileWidth: 140,
    dashReady: false,
    crowdControlled: true,
    flashReady: false,
  }),
)
assert(
  'same T_avail: farther D → larger sigma.aim (Schmidt D/T)',
  !!nearAim.sigma &&
    !!farAim.sigma &&
    farAim.sigma.aim > nearAim.sigma.aim,
  `near=${nearAim.sigma?.aim.toFixed(1)} far=${farAim.sigma?.aim.toFixed(1)}`,
)

const slowMs = estimateXh(
  base({
    targetMovespeed: 250,
    aimTimeSec: 0.35,
    dashReady: false,
    crowdControlled: true,
  }),
)
const fastMs = estimateXh(
  base({
    targetMovespeed: 450,
    aimTimeSec: 0.35,
    dashReady: false,
    crowdControlled: true,
  }),
)
assert(
  'higher target MS → larger sigma.aim (interception timing)',
  !!fastMs.sigma &&
    !!slowMs.sigma &&
    fastMs.sigma.aim > slowMs.sigma.aim,
  `fastMS=${fastMs.sigma?.aim.toFixed(1)} slowMS=${slowMs.sigma?.aim.toFixed(1)}`,
)

const fastMis = estimateXh(
  base({
    missileSpeed: 2800,
    aimTimeSec: 0.35,
    dashReady: false,
    crowdControlled: true,
  }),
)
const slowMis = estimateXh(
  base({
    missileSpeed: 800,
    aimTimeSec: 0.35,
    dashReady: false,
    crowdControlled: true,
  }),
)
assert(
  'slower missile → sigma.aim ≥ faster (TOF horizon, not T_avail=t_go)',
  !!slowMis.sigma &&
    !!fastMis.sigma &&
    slowMis.sigma.aim + 1e-6 >= fastMis.sigma.aim,
  `slowMis=${slowMis.sigma?.aim.toFixed(1)} fastMis=${fastMis.sigma?.aim.toFixed(1)}`,
)

// Guard: T_avail must appear in factors and must not equal t_go string blindly
assert(
  'factors expose T_avail (lineup, not hidden)',
  aimLongT.factors.some((f) => f.startsWith('T_avail:')),
  aimLongT.factors.join(','),
)
```

If `aimTimeSec` is not yet on the type when eval is updated, orchestrator must land the input field in the same keep commit.

---

## arXiv / literature cites

| Id / ref | Use in model |
|----------|----------------|
| **[2410.02966](https://arxiv.org/abs/2410.02966)** | Fitts/Schmidt speed–accuracy under **signal-dependent motor noise** + planning variability (offline/online OC). Justifies `κ_v·(D/T)` term. |
| **[2110.11130](https://arxiv.org/abs/2110.11130)** | Inverse OFC with human SDN characteristics; reinforces multiplicative motor noise in σ. |
| **[1804.05021](https://arxiv.org/abs/1804.05021)** | FITTS trajectory variability — information-theoretic / feedback view of aimed-movement endpoint spread. |
| **[2107.00814](https://arxiv.org/abs/2107.00814)** | Computational limb-production review citing Harris–Wolpert SDN as core of minimum-variance aiming. |
| **[2512.17735](https://arxiv.org/abs/2512.17735)** | Interceptive location vs short-horizon prediction under active inference — supports **prediction-horizon** (∝ `t_go`) effect on intercept accuracy. |
| **[2412.04191](https://arxiv.org/abs/2412.04191)** | Predictive strategies for complex motor skills / interception — forward models compensate delay; timing uncertainty → spatial miss. |
| Classic (non-arXiv, cite in comments): Schmidt et al. 1979 *Psych Review* (motor-output variability / linear We∝D/T); Harris & Wolpert 1998 *Nature* 394:780 (SDN); Wright & Meyer 1983 (conditions for linear SAT). |

---

## What not to do

- Do **not** set `T_avail = t_go` or `T_avail = dist / missileSpeed`.
- Do **not** multiply BASE_XH × mobility × zone.
- Do **not** fold kit mobility class into σ_aim (dashes belong in σ_juke / budget).
- Do **not** weaken `faster missile → higher xH` — timing noise should **help** that inequality.

---

## Decision

**`KEEP_CANDIDATE`**

Minimal, axis-local, arXiv-aligned, adds falsifiable aim invariants, preserves σ factorization and public API. Orchestrator: apply σ_aim replacement + optional `aimTimeSec`/`releaseJitterSec`, then append invariants; reject only if `math_pass_rate` drops.
