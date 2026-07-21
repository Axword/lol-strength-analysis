# Pass-1 GEO — collision triangle / t_go / lateral miss

**Axis:** geometry / kinematics  
**Verdict:** `KEEP_CANDIDATE`

---

## 1) Critique of current geometry

In `estimateXh` (≈ lines 279–287):

```ts
const tGo = dist / Math.max(200, vMissile)
const vPerp = ms * 0.4
const muBias = vPerp * tGo * (1 - leadSkill)
```

Problems vs arXiv-aligned intercept kinematics:

1. **`t_go = R / V_m` is range/speed only.** Classical closing-speed / collision-course form is `t_go ≈ R / V_c` with `V_c = V_m − v_radial` (exact on a collision course; see arXiv:2403.14997). A non-maneuvering intercept with known `(v_radial, v_perp)` is the **collision-triangle quadratic** `|r + v t| = V_m t`. Fleeing along LOS must lengthen `t_go`; approaching must shorten it. Current code ignores radial motion entirely.

2. **`vPerp = 0.4 · MS` is ad-hoc.** Under unknown heading (isotropic), `E[|sin θ|] = 2/π ≈ 0.637`, not 0.4. Bias scale is therefore systematically wrong when heading is not supplied.

3. **Lead is only a scalar on bias — no intercept geometry.** Comments claim “collision-triangle lead,” but there is no lead angle / intercept time. For a **ballistic** (non-homing) skillshot this is exactly open-loop lead: perfect lead ⇒ zero-effort miss (ZEM) = 0 for constant-velocity target; aim-at-current ⇒ ZEM ≈ `v_perp · t_go` (linearized lateral miss). Partial `leadSkill` interpolates residual ZEM. Do **not** add PN/homing mid-flight (program hard rule).

4. **Corridor hit `P(|M−μ|<R_hit)` is already the right lethality wrapper** (cookie-cutter + Gaussian miss). Keep it; fix how `μ` and `t_go` are produced.

No BASE×ZONE×VISION resurrection in this patch.

---

## 2) Exact TypeScript snippets (copy-paste ready)

### 2a) Insert helpers (after `corridorHitProb`, before `zoneSigmaScale`)

```typescript
/**
 * Collision-triangle intercept time for constant-speed ballistic missile vs
 * constant-velocity target in the LOS frame: r=(R,0), v=(vRadial, vPerp).
 * Solve |r + v t|² = (V_m t)² → A t² + B t + C = 0.
 * Positive vRadial = target fleeing along LOS.
 * arXiv:2403.14997 (t_go / collision course); arXiv:2312.09562 (collision triangle).
 */
export function interceptTimeGo(
  rangeUu: number,
  missileSpeed: number,
  vRadial = 0,
  vPerp = 0,
): number {
  const Vm = Math.max(200, missileSpeed)
  const R = Math.max(1, rangeUu)
  const A = vRadial * vRadial + vPerp * vPerp - Vm * Vm
  const B = 2 * R * vRadial
  const C = R * R
  if (Math.abs(A) < 1e-6) {
    // Linear: 2 R vRadial t + R² = 0 → needs closing (vRadial < 0)
    if (B >= -1e-9) return R / Vm
    return Math.max(0.05, -C / B)
  }
  const disc = B * B - 4 * A * C
  if (disc < 0) {
    // No real intercept on that heading — fall back to fly-to-current.
    return R / Vm
  }
  const s = Math.sqrt(disc)
  const t1 = (-B - s) / (2 * A)
  const t2 = (-B + s) / (2 * A)
  const hits = [t1, t2].filter((t) => t > 0.05)
  return hits.length ? Math.min(...hits) : R / Vm
}

/**
 * Lateral miss (ZEM) for ballistic aim with partial lead.
 * leadSkill=1 → perfect collision-triangle lead → μ=0 (non-maneuvering).
 * leadSkill=0 → aim at current position → μ ≈ |v_perp| t_go.
 * Skillshots do not steer; this is open-loop residual, not PN.
 * arXiv:2511.21633 (ZEM = predicted miss under zero future control);
 * arXiv:2604.17811 (miss → hit/kill probability).
 */
export function lateralMissFromLead(
  tGo: number,
  vPerp: number,
  leadSkill: number,
): number {
  const lead = Math.min(1, Math.max(0, leadSkill))
  return Math.abs(vPerp) * Math.max(0, tGo) * (1 - lead)
}

/** Isotropic heading prior: E[|sin θ|] = 2/π. */
export const ISOTROPIC_PERP_FRAC = 2 / Math.PI
```

### 2b) Optional input fields on `XhEstimateInput`

```typescript
  /**
   * Target velocity along LOS (uu/s); + = fleeing from caster.
   * Default 0 (unknown / isotropic mean radial).
   */
  targetRadialVel?: number
  /**
   * Target velocity perpendicular to LOS (uu/s).
   * Default: MS * (2/π) isotropic E[|sin θ|].
   */
  targetPerpVel?: number
```

### 2c) Replace the tGo / muBias block inside `estimateXh`

```typescript
  const ms = input.targetMovespeed ?? 335
  const leadSkill = Math.min(1, Math.max(0, input.leadSkill ?? 0.55))
  const vRadial = input.targetRadialVel ?? 0
  const vPerp = input.targetPerpVel ?? ms * ISOTROPIC_PERP_FRAC
  const tGo = interceptTimeGo(dist, vMissile, vRadial, vPerp)
  const muBias = lateralMissFromLead(tGo, vPerp, leadSkill)
  factors.push(`t_go:${tGo.toFixed(2)}s`, `R_hit:${Math.round(R_hit)}`)
```

(Remove the old `tGo = dist / …`, `vPerp = ms * 0.4`, and the duplicate `factors.push(t_go…)` that currently sits above the lead block — keep a single `t_go` factor after the new computation. Leave σ_aim / σ_juke / σ_belief and `corridorHitProb` unchanged.)

---

## 3) New invariant check(s) to ADD to eval (string form)

Add imports: `interceptTimeGo`, `lateralMissFromLead`, `ISOTROPIC_PERP_FRAC`.

```typescript
// --- geometry / collision-triangle ---
assert(
  'intercept t_go @ v=0 ≈ R/V_m',
  Math.abs(interceptTimeGo(1000, 2000, 0, 0) - 0.5) < 1e-6,
)
assert(
  'fleeing radial lengthens t_go vs approaching',
  interceptTimeGo(1000, 1600, 300, 0) > interceptTimeGo(1000, 1600, -300, 0),
)
assert(
  'perfect lead → lateral miss 0',
  lateralMissFromLead(0.5, 200, 1) === 0,
)
assert(
  'zero lead → miss = |v_perp| t_go',
  Math.abs(lateralMissFromLead(0.5, 200, 0) - 100) < 1e-9,
)
const leadHi = estimateXh(base({ leadSkill: 1, targetPerpVel: 250 }))
const leadLo = estimateXh(base({ leadSkill: 0, targetPerpVel: 250 }))
assert(
  'better lead → higher xH (same kinematics)',
  leadHi.xH > leadLo.xH,
  `hi=${leadHi.xH.toFixed(3)} lo=${leadLo.xH.toFixed(3)}`,
)
const approach = estimateXh(
  base({ targetRadialVel: -280, targetPerpVel: 200, leadSkill: 0.5 }),
)
const flee = estimateXh(
  base({ targetRadialVel: 280, targetPerpVel: 200, leadSkill: 0.5 }),
)
assert(
  'approaching along LOS → higher xH than fleeing',
  approach.xH > flee.xH,
  `ap=${approach.xH.toFixed(3)} fl=${flee.xH.toFixed(3)}`,
)
```

Do **not** soften existing checks.

---

## 4) arXiv ids cited

| id | Role |
|----|------|
| [2403.14997](https://arxiv.org/abs/2403.14997) | Linearization about collision triangle; `t_go` exact on collision course (`R/V_c`) |
| [2312.09562](https://arxiv.org/abs/2312.09562) | Collision-course / collision-triangle definition |
| [2511.21633](https://arxiv.org/abs/2511.21633) | Zero-effort miss (ZEM) as predicted miss under zero future control — matches ballistic skillshot |
| [2604.17811](https://arxiv.org/abs/2604.17811) | Miss distance → hit/kill probability (soft lethality; keep `corridorHitProb`) |

---

## 5) Verdict

**`KEEP_CANDIDATE`**

Minimal, API-compatible (optional velocity fields + exported pure helpers), fixes the main kinematic gap (closing `t_go` + ZEM lead residual), adds falsifiable invariants, and does not touch aim/vision/xHm axes or revive multiplicative priors.
