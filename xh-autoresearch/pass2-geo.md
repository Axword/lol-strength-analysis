# Pass-2 GEO — lead angle / ability width / t_go edge-range

**Axis:** geometry / kinematics (deepen Pass-1)  
**Verdict:** `KEEP_CANDIDATE`  
**Do not edit `src/engine/xh.ts` in this pass** (orchestrator conflict). Snippets are copy-paste for the keeper apply.

Eval baseline at proposal time: **41/41** (`npm run eval:xh`). Proposals below are designed not to regress those checks.

---

## 1) Critique of Pass-1 geometry (what remains)

Pass-1 shipped `interceptTimeGo`, `lateralMissFromLead`, isotropic `2/π`. Remaining gaps vs collision-triangle kinematics:

1. **Lead is still a scalar on lateral ZEM, not an explicit lead angle.**  
   Collision-triangle aiming is a **heading** \(\lambda^\star\) off current LOS. Heading error \(\delta = \lambda^\star - \lambda_{\text{aim}}\) maps to lateral miss \(\approx V_m t_\text{go}\sin\delta\) (exact chord at intercept for constant-speed ballistic).  
   Pass-1’s \(\mu = |v_\perp| t_\text{go}(1-s)\) is the **small-angle / linear-ZEM** special case. For large lateral rates it under-penalizes partial lead (\(s\in(0,1)\)) because \(\sin(s\lambda^\star) \neq s\sin\lambda^\star\). Skillshots still do **not** steer mid-flight (no PN).

2. **Edge-range uses ad-hoc `abilityRange * 1.05`.**  
   In `estimateXh`, `inRange = distance <= abilityRange * 1.05` before kinematics. Physical ballistic reach is the intercept path length \(V_m t_\text{go}\) (by construction of the collision triangle). Replace the 5% fudge with hitbox-aware reach:  
   \(V_m t_\text{go} \le R_{\max} + R_{\text{champ}}\).  
   Stationary \(v=0\) ⇒ \(V_m t_\text{go}=D\), so in-range iff \(D \le R_{\max}+65\) — similar magnitude to 5% on long shots, but derived. Fleeing near max range can correctly go OOR while current \(D\) is still inside cast range.

3. **Width is range-band heuristic only.**  
   `defaultMissileWidth(range)` is fine as fallback; kits already know corridor width when callers pass `missileWidth`. Cheap deepen: optional `missileWidth` / `missileSpeed` on `AbilityDefinition` + wire `abilityXhPreview`. Do **not** invent BASE×ZONE×VISION.

No multiplicative prior resurrection. No PN/homing.

---

## 2) Exact TypeScript snippets (copy-paste ready)

### 2a) New helpers (after `lateralMissFromLead` / `ISOTROPIC_PERP_FRAC`)

```typescript
/**
 * Required open-loop lead angle (rad) off current LOS for the collision-triangle
 * intercept: aim at r + v t_go. Ballistic skillshots set heading once; no mid-course PN.
 * arXiv:1906.02113 (lead angle L / heading error on collision triangle);
 * arXiv:2312.09562 (collision-triangle geometry).
 */
export function requiredLeadAngle(
  tGo: number,
  rangeUu: number,
  vRadial = 0,
  vPerp = 0,
): number {
  const t = Math.max(0, tGo)
  return Math.atan2(vPerp * t, rangeUu + vRadial * t)
}

/**
 * Lateral miss from heading error δ = λ* − λ_aim.
 * On the collision triangle, |sin λ*| V_m t_go = |v_perp| t_go (identity).
 * arXiv:1906.02113 (HE); arXiv:2511.21633 (ZEM as predicted miss under zero control).
 */
export function lateralMissFromHeadingError(
  tGo: number,
  missileSpeed: number,
  leadRequiredRad: number,
  leadAchievedRad: number,
): number {
  const Vm = Math.max(200, missileSpeed)
  const delta = leadRequiredRad - leadAchievedRad
  return Math.abs(Math.sin(delta)) * Vm * Math.max(0, tGo)
}

/**
 * Reach budget for ballistic skillshot: intercept path length vs cast range + champ radius.
 * Replaces ad-hoc abilityRange * 1.05. arXiv:2403.14997 (t_go path on collision course).
 */
export function interceptInMissileRange(
  tGo: number,
  missileSpeed: number,
  abilityRange: number,
  champRadius = CHAMP_RADIUS,
): boolean {
  const reach = Math.max(200, missileSpeed) * Math.max(0, tGo)
  return reach <= abilityRange + champRadius
}
```

Keep `lateralMissFromLead` exported unchanged so Pass-1 unit checks (`perfect lead → 0`, `zero lead → |v_perp|t_go`) stay green. `estimateXh` switches to the heading-error path (equivalent at \(s\in\{0,1\}\); better for partial lead).

### 2b) Optional ability kinematics (`src/engine/types.ts` — cheap)

```typescript
export interface AbilityDefinition {
  // ...existing fields...
  /** Skillshot missile width (uu); overrides range-band default when set. */
  missileWidth?: number
  /** Skillshot missile speed (uu/s); overrides range-band default when set. */
  missileSpeed?: number
}
```

### 2c) Wire `abilityXhPreview` (bottom of `xh.ts`)

```typescript
export function abilityXhPreview(
  ability: AbilityDefinition,
  input: Omit<XhEstimateInput, 'abilityRange'>,
): XhEstimate {
  return estimateXh({
    ...input,
    abilityRange: ability.range,
    missileWidth: input.missileWidth ?? ability.missileWidth,
    missileSpeed: input.missileSpeed ?? ability.missileSpeed,
    skillshotLengthPenalty: ability.range >= 900,
  })
}
```

### 2d) Replace geo / in-range block inside `estimateXh`

**Reorder:** compute kinematics **before** the out-of-range early return (today OOR returns before `t_go`).

```typescript
  const range = Math.max(1, input.abilityRange)
  const dist = distance ?? range * 0.55
  const vMissile = input.missileSpeed ?? defaultMissileSpeed(range)
  const width = input.missileWidth ?? defaultMissileWidth(range)
  const R_hit = width / 2 + CHAMP_RADIUS

  const ms = input.targetMovespeed ?? 335
  const leadSkill = Math.min(1, Math.max(0, input.leadSkill ?? 0.55))
  const vRadial = input.targetRadialVel ?? 0
  const vPerp = input.targetPerpVel ?? ms * ISOTROPIC_PERP_FRAC
  const tGo = interceptTimeGo(dist, vMissile, vRadial, vPerp)
  const lamStar = requiredLeadAngle(tGo, dist, vRadial, vPerp)
  const lamAim = lamStar * leadSkill // fraction of collision-triangle lead
  const muBias = lateralMissFromHeadingError(tGo, vMissile, lamStar, lamAim)
  factors.push(
    `t_go:${tGo.toFixed(2)}s`,
    `lead_deg:${((lamStar * 180) / Math.PI).toFixed(1)}`,
    `R_hit:${Math.round(R_hit)}`,
  )

  // Edge-range via intercept path length (not abilityRange * 1.05).
  if (input.casterPosition && geoPos && distance != null) {
    inRange = interceptInMissileRange(tGo, vMissile, input.abilityRange)
    if (!inRange) {
      return {
        xH: 0,
        inRange: false,
        distance,
        targetMobility,
        targetZone,
        casterZone,
        vision,
        factors: [...factors, 'out_of_range', `reach:${Math.round(vMissile * tGo)}`],
        bands: { worst: 0, typical: 0, best: 0 },
      }
    }
  }
```

Remove the old early `inRange = distance <= input.abilityRange * 1.05` return that currently sits **above** the kinematics block; keep a single OOR exit after `t_go`.

`defaultMissileWidth` / `defaultMissileSpeed` stay as fallbacks — width-from-ability is optional override only.

---

## 3) New invariant check(s) to ADD to eval (string form)

Import: `requiredLeadAngle`, `lateralMissFromHeadingError`, `interceptInMissileRange`.

```typescript
// --- geometry deepen (Pass-2 GEO) ---
assert(
  'required lead @ v_perp=0 → 0',
  Math.abs(requiredLeadAngle(0.5, 1000, 0, 0)) < 1e-12,
)
{
  const R = 1000
  const Vm = 1600
  const vp = 200
  const tg = interceptTimeGo(R, Vm, 0, vp)
  const lam = requiredLeadAngle(tg, R, 0, vp)
  const chord = lateralMissFromHeadingError(tg, Vm, lam, 0)
  assert(
    'collision-triangle identity: |sin λ*| V_m t_go = |v_perp| t_go',
    Math.abs(chord - Math.abs(vp) * tg) < 1e-6,
    `chord=${chord.toFixed(6)} vpT=${(Math.abs(vp) * tg).toFixed(6)}`,
  )
  assert(
    'perfect heading → miss 0',
    lateralMissFromHeadingError(tg, Vm, lam, lam) === 0,
  )
}
assert(
  'stationary edge: D ≤ R_max+R_champ via t_go reach',
  interceptInMissileRange(1175 / 1200, 1200, 1175) === true,
)
assert(
  'stationary beyond hitbox budget → OOR',
  interceptInMissileRange((1175 + 66) / 1200, 1200, 1175) === false,
)
{
  // Fleeing near max cast range: current D in cast range, intercept path exceeds budget.
  const D = 1100
  const Vm = 1200
  const Rmax = 1175
  const tg = interceptTimeGo(D, Vm, 280, 335 * ISOTROPIC_PERP_FRAC)
  assert(
    'fleeing near edge: t_go reach can OOR while D < R_max',
    D < Rmax && interceptInMissileRange(tg, Vm, Rmax) === false,
    `D=${D} reach=${(Vm * tg).toFixed(0)}`,
  )
}
const wideAbility = estimateXh(base({ missileWidth: 200 }))
const thinAbility = estimateXh(base({ missileWidth: 60 }))
assert(
  'ability/caller width still orders xH (wider > thinner)',
  wideAbility.xH > thinAbility.xH,
)
```

Do **not** soften existing checks. Pass-1 lead/approach/flee and corridor tests remain.

---

## 4) Mental regression vs existing 41/41

| Check family | Risk | Why safe |
|--------------|------|----------|
| corridor\* | none | untouched |
| point-blank / max-range / speed / width | low | same \(R_\text{hit}\), \(t_\text{go}\); far fixture reach≈1058 ≪ 1240 |
| OOR → 0 | none | corner dist ≫ 500 still OOR under reach test |
| lead hi/lo, approach/flee | low | \(s\in\{0,1\}\) identical to Pass-1 ZEM; partial lead only slightly stricter |
| intercept / lateralMissFromLead unit | none | helpers kept; new helpers additive |
| aim / bands / vision / xHm / kit-tag | none | no σ or xHm changes |

Fleeing-near-edge OOR is **new** physics; no current eval fixture sets high \(v_\text{radial}\) at the far edge.

---

## 5) arXiv ids cited

| id | Role |
|----|------|
| [1906.02113](https://arxiv.org/abs/1906.02113) | Required lead angle \(L\) on the collision triangle; heading error HE between aim and collision heading |
| [2403.14997](https://arxiv.org/abs/2403.14997) | \(t_\text{go}\) / closing on collision course; path length \(V_m t_\text{go}\) |
| [2312.09562](https://arxiv.org/abs/2312.09562) | Collision-triangle definition (Pass-1 carry) |
| [2511.21633](https://arxiv.org/abs/2511.21633) | ZEM as predicted miss under zero future control — ballistic open-loop residual |
| [2604.17811](https://arxiv.org/abs/2604.17811) | Miss → hit probability (keep `corridorHitProb`) |

---

## 6) Verdict

**`KEEP_CANDIDATE`**

Minimal deepen on the GEO axis only: explicit lead angle + heading-error miss, \(t_\text{go}\) reach instead of `* 1.05`, optional ability width/speed passthrough. Preserves Pass-1 helpers and public `estimateXh` / `estimateXhm` / `resolveCastVision` API. Does not touch aim/vision/strategy σ models, does not revive BASE×ZONE×VISION, does not add PN.
