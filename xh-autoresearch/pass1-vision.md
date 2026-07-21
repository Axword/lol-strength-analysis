# Pass-1 VISION — Belief / FoW / LKP deepen

**Axis:** vision  
**Agent:** Pass-1 VISION  
**Against:** `src/engine/xh.ts` @ σ-corridor baseline (`math_pass_rate=20/20`)  
**Constraint honored:** no edits to `xh.ts` / eval; proposal only.  
**Verdict:** **KEEP_CANDIDATE**

---

## 0. Status vs adversarial canvas

The canvas (`xh-vision-adversarial-review.canvas.tsx`) still describes `VISION_XH_MULT` as the primary model. **That critique is partially obsolete:**

| Canvas claim | Current code |
|---|---|
| Blind = oracle geometry × 0.55 | Deprecated table; blind enters via `σ_belief = MS · age · 0.55` (+ `σ_aim × 1.25`) |
| No LKP Δt | `lastKnownAgeSec` exists; eval `stale LKP < fresh` **PASS** |
| Ambush = flat ×1.14 | Ambush = longer `reactionSec` (0.38 vs 0.22), not a hit-rate scalar |
| `unknown` → mutual ×1 | `unknown` → `σ_belief = MS · 0.35` (nonzero) |

**Residual P0 that remains:** blind/unknown still **aim and range-check the true `targetPosition`**, then smear with isotropic `σ_belief`. That is

\[
xH = P\big(|M| < R_{\mathrm{hit}}\big),\quad M\sim\mathcal N(\mu_{\mathrm{oracle}},\,\sigma_{\mathrm{aim}}^2+\sigma_{\mathrm{juke}}^2+\sigma_{\mathrm{belief}}^2)
\]

not the imperfect-info object

\[
xH(a^\star)=\int L\big(\mathrm{proj}(a^\star),x;R_{\mathrm{hit}}\big)\,b(x)\,dx,\quad a^\star=\arg\max_a\int L\,b.
\]

Convolving lethality about the **oracle mean** is still god-eye; literature requires decisions over the **posterior** (arXiv:2604.17811, 2602.11373). Soft ward edges and reachable-set age decay are still missing.

---

## 1. Critique (concrete, line-level)

### 1.1 God-eye mean under “belief” (P0)

```337:345:src/engine/xh.ts
  if (vision === 'blind') {
    const age = input.lastKnownAgeSec ?? 2
    // Truncated diffusion scale ~ MS * age * κ (not aiming at oracle point).
    sigmaBelief = ms * age * 0.55
    factors.push(`belief:lkp_age:${age.toFixed(1)}s`)
  } else if (vision === 'unknown') {
    sigmaBelief = ms * 0.35
  }
```

Distance / `inRange` / `zoneAt` / `tGo` / `muBias` all still consume `input.targetPosition` (true feed pose). Comment claims “not aiming at oracle point”; math still does. There is **no** `lastKnownPosition` / `beliefMean` on `XhEstimateInput` — only age — so the mean of \(b\) cannot leave the oracle.

**Failure modes the eval does not catch:**

- Fresh blind (`age=0.3`) with true pose far from LKP still gets high xH if σ_belief is small — predictive cast along LKP heading underrated only via age, not via mean displacement.
- Stale blind still range-gates on true position: `inRange` can be true while LKP is OOR (or vice versa).

### 1.2 Linear age is wrong scale + uncapped (P1)

`σ_belief ∝ age` (not \(\sqrt{\mathrm{age}}\)) is OK for **unknown constant heading** ballistic smear \(v_{\perp}t\), but:

1. No **reachable-set truncation**: support radius \(R_{\max}=v_{\max}\cdot\Delta t\) (plus dash budget). Untruncated Gaussian puts mass outside the map / through walls.
2. Coefficient `0.55` is a vibe κ; for a **uniform disk** of radius \(R=v\Delta t\), 1D projected SD is \(R/\sqrt{3}\approx 0.577\,v\Delta t\) — close numerically, but should be derived and capped:
   \(\sigma_{\mathrm{belief}}=\min\!\big(\kappa\,v\,\Delta t,\; R_{\max}/\sqrt{3}\big)\).
3. Dash-ready targets expand support faster than boots — currently mobility only affects σ_juke after reaction, not belief support.

### 1.3 Double FoW penalty (P1)

Blind applies **both** `sigmaAim *= 1.25` and `σ_belief`. Aim inflation under FoW should come from **measurement / belief uncertainty**, not a second ad-hoc scalar on Fitts noise (arXiv:2602.11373: use full posterior, don’t stack independent “fog knobs”). Prefer: keep σ_aim geometry-pure; put FoW entirely in \(b\) / σ_belief (+ soft vis mixture).

### 1.4 Hard ward / champ disks (P1)

```166:170:src/engine/vision.ts
  for (const w of wards) {
    if (w.team !== viewerTeam) continue
    const r = w.visionRadius || meta?.vision.wardSightRadiusNorm || 0.055
    if (dist({ x: w.x, y: w.y }, target) <= r) return true
  }
```

`resolveCastVision` → binary `blind|ambush|mutual`. Soft sensor (Koopman lateral-range; arXiv:2410.13587 noisy sensors) wants continuous visibility weight \(v\in[0,1]\) and a **mixture belief**:

\[
b = v\cdot\mathcal N(x_{\mathrm{meas}},\sigma_{\mathrm{meas}}^2)+(1-v)\cdot b_{\mathrm{lost}}(\mathrm{LKP},\Delta t).
\]

Edge fights (target just outside ward) currently cliff to full blind default age=2s.

### 1.5 UI FoW richer than xH (P2)

`classifyVision` exposes `visible | opponent_only | nobody`. xH collapses to casterSees/targetSees. `opponent_only` (you are dark but spotted) is a distinct POSG info set: caster belief lost + target reaction of **mutual** (they see the cast). Should tighten τ_react even while σ_belief is large.

---

## 2. Proposed math (VBHM-lite, API-preserving)

Keep public `estimateXh` / `resolveCastVision` / `estimateXhm`. Extend input optionally:

```ts
// Additive fields on XhEstimateInput (all optional → backward compatible)
beliefMeanPosition?: MapPosition  // LKP / filter mean; if absent + blind, fall back to targetPosition (legacy)
lastKnownAgeSec?: number          // already present
softVision?: number               // ∈[0,1]; 1=fully seen. If set, overrides ternary for belief mix
spottedByTarget?: boolean         // opponent_only: they see caster while caster blind
```

### 2.1 Closed-form belief corridor (no particle loop required)

Assume lateral projection. Let aim lock to belief mean (LKP). Oracle lateral residual of true pose vs LKP:

```ts
/** Lateral miss of true pose relative to aim-at-LKP (game uu). */
function lateralOracleResidual(
  caster: MapPosition,
  aim: MapPosition,
  truth: MapPosition,
): number {
  // 2D → signed distance of truth to the aim ray; for corridor model use
  // perpendicular component in map plane.
  const ax = (aim.x - caster.x) * MAP_SPAN
  const ay = (aim.y - caster.y) * MAP_SPAN
  const len = Math.hypot(ax, ay) || 1
  const tx = (truth.x - caster.x) * MAP_SPAN
  const ty = (truth.y - caster.y) * MAP_SPAN
  // cross / |a| = signed perp distance
  return (ax * ty - ay * tx) / len
}
```

Hit under Gaussian belief about LKP **plus** aim/juke noise is still one corridor CDF if we aim at LKP:

\[
\mu = \underbrace{v_\perp t_{\mathrm{go}}(1-\ell)}_{\text{lead residual at belief mean}}
     + \underbrace{\delta_\perp}_{\text{truth vs LKP (diagnostic)}},
\quad
\sigma^2=\sigma_{\mathrm{aim}}^2+\sigma_{\mathrm{juke}}^2+\sigma_{\mathrm{belief}}^2.
\]

For **FoW expected damage in replay** (production): set \(\delta_\perp=0\) and do **not** feed true pose into geometry — use `beliefMeanPosition` for dist / tGo / zone. Keep true pose only for oracle diagnostic band.

For **eval calibration against known outcomes**: optional `truthPosition` can set \(\delta_\perp\) so god-eye vs belief-aim is measurable.

### 2.2 Reachable-set capped LKP diffusion

```ts
function sigmaBeliefLkp(opts: {
  ms: number
  ageSec: number
  dashBudgetUu: number // 0 if depleted / boots
  kappa?: number       // default 1/Math.sqrt(3) ≈ 0.577 (uniform disk → 1D)
}): number {
  const age = Math.max(0, opts.ageSec)
  const kappa = opts.kappa ?? 1 / Math.SQRT3
  // Support radius: walk + optional dash fraction usable while dark
  const Rmax = opts.ms * age + opts.dashBudgetUu * Math.min(1, age / 0.5)
  // Projected SD of Unif(disk R) ≈ R/√3; also Brownian-style floor for tiny age
  const sig = Math.hypot(35, kappa * Rmax) // 35uu = measurement jitter at loss instant
  return Math.min(sig, Rmax) // never exceed support radius as SD proxy
}
```

Properties:

- `age→0` ⇒ σ_belief → ~35uu (fresh loss ≠ Dirac, not 0 and not default 2s).
- Monotone in age (preserves `stale < fresh`).
- Capped by reachable set (Koopman / S&T coverage; arXiv:2306.11301).

### 2.3 Soft ward edge → continuous \(v\)

```ts
/** Soft visibility in [0,1]; hard disk is lim κ→∞. */
export function softVisionAt(
  target: MapPosition,
  viewerTeam: TeamSide,
  units: VisionUnit[],
  wards: VisionWard[],
  meta?: TerrainMeta | null,
  kappa = 80, // steepness in 1/norm-units
): number {
  const champR = meta?.vision.championSightRadiusNorm ?? 0.09
  let best = 0
  for (const a of units.filter((u) => u.team === viewerTeam && u.alive !== false)) {
    const margin = champR - dist(a.position, target)
    best = Math.max(best, 1 / (1 + Math.exp(-kappa * margin)))
  }
  for (const w of wards.filter((w) => w.team === viewerTeam)) {
    const r = w.visionRadius || meta?.vision.wardSightRadiusNorm || 0.055
    const margin = r - dist({ x: w.x, y: w.y }, target)
    best = Math.max(best, 1 / (1 + Math.exp(-kappa * margin)))
  }
  return best
}

/** Mixture σ: seen kernel + lost LKP kernel. */
function mixBeliefSigma(v: number, sigmaSeen: number, sigmaLost: number): number {
  // Variance mixture about shared aim (conservative): 
  // Var = v σ_s² + (1-v) σ_ℓ² + v(1-v)(μ_s−μ_ℓ)² ; with μ_s=μ_ℓ=LKP →
  return Math.sqrt(v * sigmaSeen * sigmaSeen + (1 - v) * sigmaLost * sigmaLost)
}
```

Wire into estimate (sketch):

```ts
const v = input.softVision ?? (vision === 'blind' ? 0 : vision === 'unknown' ? 0.5 : 1)
const age = input.lastKnownAgeSec ?? (v < 0.5 ? 2 : 0)
const sigmaLost = sigmaBeliefLkp({ ms, ageSec: age, dashBudgetUu: dashReady ? kitDash : 0 })
const sigmaSeen = 25 // tracking jitter while lit
sigmaBelief = mixBeliefSigma(v, sigmaSeen, sigmaLost)

// Drop sigmaAim *= 1.25 blind inflate — FoW lives in belief only.

// Geometry under FoW: prefer belief mean
const geoPos = (v < 0.85 && input.beliefMeanPosition)
  ? input.beliefMeanPosition
  : input.targetPosition
```

Ambush / spotted:

```ts
const tau =
  reactionSec(vision) +
  (input.spottedByTarget && vision === 'blind' ? 0.08 : 0) // you are lit; they react sooner
```

### 2.4 Ternary `resolveCastVision` stays; soft path optional

Do **not** break combat/overlay callers. Soft path activates when `softVision` or `beliefMeanPosition` is provided by the map scrubber. Default blind without LKP position keeps today’s behavior (eval-safe), then orchestrator tightens defaults once new invariants exist.

---

## 3. New invariants (strengthen eval — do not soften old ones)

Add to `scripts/eval-xh-math.ts` **after** keepers land (orchestrator). All must be additive:

```ts
// V1: belief-aim displacement — truth off LKP must lower xH vs aim-on-truth
// (requires beliefMeanPosition API)
const onTruth = estimateXh(base({ vision: 'blind', lastKnownAgeSec: 1 }))
const offLkp = estimateXh(
  base({
    vision: 'blind',
    lastKnownAgeSec: 1,
    beliefMeanPosition: { x: mid.x - 0.04, y: mid.y }, // displaced LKP
    // targetPosition remains true near mid
  }),
)
assert('belief-aim off LKP ≤ oracle-aim same age', offLkp.xH <= onTruth.xH + 1e-9)

// V2: age→0 blind ≈ mutual geometry (tiny measurement jitter only)
const justLost = estimateXh(base({ vision: 'blind', lastKnownAgeSec: 0 }))
assert(
  'fresh loss not catastrophic vs mutual',
  justLost.xH > mutual.xH * 0.85,
  `justLost=${justLost.xH.toFixed(3)} mutual=${mutual.xH.toFixed(3)}`,
)

// V3: softVision monotone
const edge = estimateXh(base({ vision: 'blind', softVision: 0.7, lastKnownAgeSec: 3 }))
const dark = estimateXh(base({ vision: 'blind', softVision: 0.0, lastKnownAgeSec: 3 }))
assert('softVision edge > full dark', edge.xH > dark.xH)

// V4: reachable cap — huge age cannot explode σ beyond ~ v*age + dash
const ancient = estimateXh(base({ vision: 'blind', lastKnownAgeSec: 30 }))
assert(
  'ancient LKP still finite and < fresh mutual floor',
  ancient.xH < 0.2 && Number.isFinite(ancient.xH),
)

// V5: no double-count regression — blind age=0 must not apply extra aim inflate
// that drives justLost << mutual by >15% beyond belief jitter
```

**Do not** remove or loosen: `stale LKP < fresh`, `blind stale < mutual`, ambush≥mutual, corridor unit tests.

---

## 4. arXiv / primary cites

| ID | Title (short) | Use in this pass |
|---|---|---|
| [2604.17811](https://arxiv.org/abs/2604.17811) | Kill-probability maximization / soft lethality | \(xH=\mathbb E_{x\sim b}[L(\mathrm{miss}(x))]\) — not α·oracle |
| [2602.11373](https://arxiv.org/abs/2602.11373) | Bayesian estimation–guidance (IMMPF posterior) | Decisions over full posterior PDF; drop stacked fog knobs |
| [2306.11301](https://arxiv.org/abs/2306.11301) | Adversarial S&T, sparse detections | LKP / motion filter under sparse vision |
| [2410.13587](https://arxiv.org/abs/2410.13587) | Sequential game target tracking, noisy sensors | Soft / noisy detection → engagement |
| [2405.18703](https://arxiv.org/abs/2405.18703) | POSG ↔ sparse POMDP / particle beliefs | \(b(s)\) sufficient statistic; ternary label insufficient |
| [1812.00054](https://arxiv.org/abs/1812.00054) | StarCraft Defogger | FoW = state estimation + dynamics |
| [2003.01927](https://arxiv.org/abs/2003.01927) | DefogGAN | Generative hidden-state / belief over pose |
| [2009.08922](https://arxiv.org/abs/2009.08922) | AI and Wargaming (FoW survey) | Exact FoW POMDP intractable → approximate belief |
| Koopman 1956 | Theory of Search II (OR) | Soft detection / effort; ward penumbra |

---

## 5. Expected invariant / metric impact

| Change | Existing eval | New vision invariants |
|---|---|---|
| Reachable-capped σ_belief (replace `ms*age*0.55`) | Should **preserve** stale\<fresh, blind\<mutual if κ≈0.55–0.58 | Enables V4 |
| Drop blind `σ_aim×1.25` | May **raise** fresh-blind slightly; keep stale≪mutual via σ_belief | Helps V2 / V5 |
| Optional `beliefMeanPosition` | No change if unset (legacy path) | Enables V1 |
| Optional `softVision` mixture | No change if unset | Enables V3 |
| Soft ward helper in `vision.ts` | No xH effect until wired | Upstream for map→calc |

**Primary score:** should stay `math_pass_rate=1.0` on current 20 checks if legacy path when new fields omitted. Net deepen = new checks V1–V5 without touching old asserts.

---

## 6. Minimal patch plan (for orchestrator — not applied here)

1. `vision.ts`: add `softVisionAt` (pure, no API break).
2. `xh.ts`: add optional input fields; implement `sigmaBeliefLkp` + mixture; route geometry through `beliefMeanPosition` when `vision==='blind'` and field set; remove blind aim inflate.
3. `eval-xh-math.ts`: append V1–V5 (only after API exists).
4. Map scrubber / `xhOverlay`: pass LKP age + last seen pos + softVision from timeline (separate pass).

**Out of scope this axis:** historic hit-rate MLE, xHm ρ, Fitts \(T_{\mathrm{avail}}\) retune.

---

## 7. Decision

**KEEP_CANDIDATE**

Rationale: baseline already killed ×0.55 multipliers and has monotone LKP age, but still **integrates noise about the oracle pose**. Soft edges + reachable-set belief + optional LKP mean are the minimal arXiv-aligned deepen that (a) does not weaken current eval when fields are absent, (b) unlocks stronger vision invariants, (c) matches program factorization `σ² = σ_aim² + σ_juke² + σ_belief²` with belief actually centered on LKP.

**SKIP** would only be justified if Pass-1 bandwidth must go to geo/aim failures — vision is not failing the harness, but it is the largest remaining theory gap vs program.md (“Blind casts must not treat true position as known without belief spread”).
