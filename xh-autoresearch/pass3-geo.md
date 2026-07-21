# Pass-3 GEO — delayed release / ray CPA / cast≠reach

**Axis:** geometry / kinematics (deepen Pass-2 residual only)  
**Verdict:** `KEEP_CANDIDATE`  
**Do not edit `src/engine/xh.ts` in this pass** (orchestrator conflict). Snippets are copy-paste for the keeper apply.

Eval baseline at proposal time: **65/65** (`npm run eval:xh`). Do **not** re-propose Pass-1/2 KEEP work (`interceptTimeGo`, `lateralMissFromLead`, isotropic 2/π, `requiredLeadAngle`, `lateralMissFromHeadingError`, `interceptInMissileRange`, ability width/speed passthrough).

No BASE×ZONE×VISION. No PN / mid-flight steering.

---

## 1) Critique of Pass-2 geometry (what remains)

Pass-2 made lead an explicit heading and replaced `×1.05` with \(V_m t_\text{go}\) reach. Residuals vs open-loop ballistic engagement:

1. **Constant-velocity μ is intentional — do not “fix” it with fake accel.**  
   Collision-triangle / ZEM μ assumes non-maneuvering target (arXiv:2511.21633). Strafe/dash/Flash belong in \(\sigma_\text{juke}\) (strategy), not a geo PN loop. Pass-3 leaves constant-\(v\) for the **predicted** intercept; the geo bug is elsewhere.

2. **Windup is strategy-only; multi-segment TOF is missing.**  
   `T_windup = 0.28` only lengthens `dodgeWindow`. Physically the timeline is  
   \(\underbrace{T_\text{delay}}_{\text{cast / delayed missile}} + \underbrace{t_\text{missile}}_{\text{ballistic}}\).  
   During delay the target free-propagates and the **LOS frame rotates**; lead \(\lambda^\star\) and \(t_\text{go}\) must be solved from the **release** pose, not cast-time \((R,0)\). Treating delay as pure dodge budget under-states lateral walk-off before the missile even exists (Ez delayed Q, windup skillshots).

3. **Partial-lead miss uses the wrong clock.**  
   `lateralMissFromHeadingError(t_go, V_m, λ*, λ_aim) = |sin δ| V_m t_go` with collision-triangle \(t_\text{go}\) is exact only on the **collision heading** identity (\(\delta=0\) or the zero-lead chord). When \(\lambda_\text{aim}\neq\lambda^\star\), the missile does **not** arrive at the collision point at that \(t_\text{go}\). The corridor miss is the **closest approach of the aim ray** to the constant-\(v\) target track (2D CPA), not the collision-triangle chord. Keep `lateralMissFromHeadingError` for Pass-2 unit identity; `estimateXh` should switch μ to ray-CPA.

4. **Radial/perp frame is frozen at cast-time LOS.**  
   After delay, \(p = (R+v_r T_d,\ v_p T_d)\), new range \(R'=\|p\|\), and \((v_r',v_p')\) are \(v\) re-projected onto the updated LOS. Passing cast-time \((v_r,v_p)\) into `requiredLeadAngle` after a non-zero delay mis-aims the lead angle when \(v_p T_d\) is large.

5. **Cast range conflated with missile travel.**  
   `interceptInMissileRange` gates on \(V_m t_\text{go} \le R_\max+R_\text{champ}\). That is **intercept path length**, not “may I press the key.” Approaching targets can be cast-legal at \(D\) while intercept is closer; fleeing can be cast-legal at \(D\) while intercept path exceeds missile budget. Split:  
   - `inCastRange`: \(D \le R_\text{cast}+R_\text{champ}\) at **cast**  
   - `inMissileReach`: \(\|p_\text{intercept}-c\| \le R_\text{missile}+R_\text{champ}\) (usually \(R_\text{missile}=R_\text{cast}\))  
   `inRange = inCastRange && inMissileReach`.

6. **Hitbox vs width (document; only a tiny deepen).**  
   `R_hit = w/2 + R_\text{champ}` is the infinite-slab cookie-cutter (firing theory). Tip/capsule (finite segment + circle Minkowski) matters near max range / very short missiles; Pass-3 does **not** replace the slab — reach already adds \(R_\text{champ}\). Optional later: tip-overlap only if eval demands it.

---

## 2) Exact TypeScript snippets (copy-paste ready)

### 2a) New helpers (after `interceptInMissileRange`; keep Pass-2 helpers unchanged)

```typescript
/**
 * Free-propagate target in the cast-time LOS frame, then re-basis velocity
 * into the release-time LOS. Open-loop only — no mid-course PN.
 * Multi-segment TOF: delay then ballistic (arXiv:2403.14997 t_go chain;
 * arXiv:2312.09562 collision triangle at engagement epoch).
 */
export function propagateLosFrame(
  rangeUu: number,
  vRadial: number,
  vPerp: number,
  delaySec: number,
): { rangeUu: number; vRadial: number; vPerp: number } {
  const td = Math.max(0, delaySec)
  const R = Math.max(1, rangeUu)
  const px = R + vRadial * td
  const py = vPerp * td
  const Rp = Math.hypot(px, py)
  if (!(Rp > 1e-9)) {
    return { rangeUu: 1, vRadial, vPerp }
  }
  // û' = p'/R'; ê_perp' = (-uy, ux) left-handed in LOS plane
  const ux = px / Rp
  const uy = py / Rp
  const vRadp = vRadial * ux + vPerp * uy
  const vPerpp = -vRadial * uy + vPerp * ux
  return { rangeUu: Rp, vRadial: vRadp, vPerp: vPerpp }
}

/**
 * Exact lateral miss: closest approach of constant-v target vs ballistic
 * aim ray from caster (origin), speed V_m, heading aimAngleRad off cast LOS.
 * Clamped to missile lifetime [0, tMax]. Replaces |sin δ| V_m t_go for μ when
 * aim ≠ λ*. arXiv:2511.21633 (ZEM / zero-control miss); arXiv:2604.17811.
 */
export function ballisticRayMiss(
  rangeUu: number,
  vRadial: number,
  vPerp: number,
  missileSpeed: number,
  aimAngleRad: number,
  tMax: number,
): number {
  const Vm = Math.max(200, missileSpeed)
  const R = Math.max(1, rangeUu)
  const c = Math.cos(aimAngleRad)
  const s = Math.sin(aimAngleRad)
  // Relative velocity w = v − V_m û_aim in LOS frame
  const wx = vRadial - Vm * c
  const wy = vPerp - Vm * s
  const w2 = wx * wx + wy * wy
  let tStar = 0
  if (w2 > 1e-12) {
    // CPA of p(t)=r+v t vs m(t)=V_m t û: t* = −(r·w)/(w·w)
    tStar = -((R * wx) /* py=0 */) / w2
  }
  const t = Math.min(Math.max(0, tMax), Math.max(0, tStar))
  const mx = Vm * t * c
  const my = Vm * t * s
  const px = R + vRadial * t
  const py = vPerp * t
  return Math.hypot(px - mx, py - my)
}

/**
 * Cast-time legality: current (or belief) center within cast range + hitbox.
 * Distinct from intercept path reach (fleeing near edge).
 */
export function inCastRange(
  distanceUu: number,
  abilityRange: number,
  champRadius = CHAMP_RADIUS,
): boolean {
  return distanceUu <= abilityRange + champRadius
}
```

### 2b) Optional input (geo delay only — not aim)

```typescript
// on XhEstimateInput:
/** Cast / delayed-missile release delay (s). Default 0.28; geometry free-propagates before t_go. */
releaseDelaySec?: number
```

Optional on `AbilityDefinition` (cheap, like Pass-2 width/speed):

```typescript
/** Pre-missile cast / delay (s); overrides estimateXh default when set. */
releaseDelaySec?: number
```

Wire in `abilityXhPreview`: `releaseDelaySec: input.releaseDelaySec ?? ability.releaseDelaySec`.

### 2c) Replace geo block inside `estimateXh` (after width / R_hit; before OOR)

Keep Pass-2 `requiredLeadAngle` / `lateralMissFromHeadingError` exported for eval identity. Switch **μ** and **frame** as follows:

```typescript
  const ms = input.targetMovespeed ?? 335
  const leadSkill = Math.min(1, Math.max(0, input.leadSkill ?? 0.55))
  const vRadial0 = input.targetRadialVel ?? 0
  const vPerp0 = input.targetPerpVel ?? ms * ISOTROPIC_PERP_FRAC
  const T_delay = Math.max(0, input.releaseDelaySec ?? 0.28)
  const atRelease = propagateLosFrame(dist, vRadial0, vPerp0, T_delay)
  const vRadial = atRelease.vRadial
  const vPerp = atRelease.vPerp
  const distRel = atRelease.rangeUu
  const tGoMis = interceptTimeGo(distRel, vMissile, vRadial, vPerp)
  const tGo = T_delay + tGoMis // total engagement clock (dodge / factors)
  const lamStar = requiredLeadAngle(tGoMis, distRel, vRadial, vPerp)
  const lamAim = lamStar * leadSkill
  // Ray-CPA miss in the *release* LOS frame (aim angle off release LOS).
  const muBias = ballisticRayMiss(
    distRel,
    vRadial,
    vPerp,
    vMissile,
    lamAim,
    tGoMis,
  )
  factors.push(
    `t_go:${tGo.toFixed(2)}s`,
    `t_delay:${T_delay.toFixed(2)}s`,
    `lead_deg:${((lamStar * 180) / Math.PI).toFixed(1)}`,
    `R_hit:${Math.round(R_hit)}`,
  )

  let inRange = true
  if (input.casterPosition && geoPos && distance != null) {
    const castOk = inCastRange(distance, input.abilityRange)
    const reachOk = interceptInMissileRange(tGoMis, vMissile, input.abilityRange)
    inRange = castOk && reachOk
    if (!inRange) {
      return {
        xH: 0,
        inRange: false,
        distance,
        targetMobility,
        targetZone,
        casterZone,
        vision,
        factors: [
          ...factors,
          'out_of_range',
          castOk ? 'reach_oor' : 'cast_oor',
        ],
        bands: { worst: 0, typical: 0, best: 0, mix: 0 },
      }
    }
  }
```

**Dodge coupling (minimal, still geo-honest):** keep  
`dodgeWindow = max(0, T_delay + tGoMis - tau)`  
i.e. reuse `tGo` total — same numeric role as today’s `T_windup + tGo`, but `tGoMis` is now post-propagation. Remove the duplicate hardcoded `T_windup = 0.28` or set `T_windup = T_delay`.

**Zero-delay equivalence:** `T_delay=0` ⇒ `propagateLosFrame` identity ⇒ `ballisticRayMiss` at perfect lead → 0; at zero lead, CPA ≈ \(|v_\perp| t\) for lateral-dominant cases (assert below). Pass-2 heading-error helper remains for unit tests.

---

## 3) New invariant check(s) to ADD to eval (string form)

Import: `propagateLosFrame`, `ballisticRayMiss`, `inCastRange`.

```typescript
// --- geometry deepen (Pass-3 GEO) ---
{
  const id = propagateLosFrame(1000, 0, 0, 0.5)
  assert(
    'propagate delay @ v=0 → range unchanged',
    Math.abs(id.rangeUu - 1000) < 1e-9 && id.vRadial === 0 && id.vPerp === 0,
  )
}
{
  // Pure lateral walk-off: after delay, range grows and radial component appears.
  const p = propagateLosFrame(1000, 0, 300, 0.4)
  assert(
    'lateral delay: R\' = hypot(R, v_p T_d)',
    Math.abs(p.rangeUu - Math.hypot(1000, 120)) < 1e-6,
    `R'=${p.rangeUu.toFixed(3)}`,
  )
  assert(
    'lateral delay: re-based |v| preserved',
    Math.abs(Math.hypot(p.vRadial, p.vPerp) - 300) < 1e-6,
  )
}
{
  const R = 1000
  const Vm = 1600
  const vp = 200
  const tg = interceptTimeGo(R, Vm, 0, vp)
  const lam = requiredLeadAngle(tg, R, 0, vp)
  assert(
    'ray CPA @ perfect lead → ~0',
    ballisticRayMiss(R, 0, vp, Vm, lam, tg) < 1e-4,
    `miss=${ballisticRayMiss(R, 0, vp, Vm, lam, tg).toFixed(6)}`,
  )
  const zeroLead = ballisticRayMiss(R, 0, vp, Vm, 0, tg)
  assert(
    'ray CPA @ zero lead ≈ |v_perp|·t_go (lateral)',
    Math.abs(zeroLead - Math.abs(vp) * tg) < 1.0,
    `cpa=${zeroLead.toFixed(3)} vpT=${(Math.abs(vp) * tg).toFixed(3)}`,
  )
}
assert(
  'inCastRange: stationary edge with hitbox',
  inCastRange(1175, 1175) === true && inCastRange(1175 + 66, 1175) === false,
)
{
  // Approaching: cast OK at D, intercept path shorter — both gates pass.
  const D = 1100
  const Vm = 1200
  const Rmax = 1175
  const tg = interceptTimeGo(D, Vm, -280, 0)
  assert(
    'approach: cast OK and reach OK',
    inCastRange(D, Rmax) && interceptInMissileRange(tg, Vm, Rmax),
    `reach=${(Vm * tg).toFixed(0)}`,
  )
}
{
  const delayed = estimateXh(
    base({
      releaseDelaySec: 0.55,
      targetPerpVel: 280,
      leadSkill: 0.5,
      dashReady: false,
      crowdControlled: true,
    }),
  )
  const instant = estimateXh(
    base({
      releaseDelaySec: 0,
      targetPerpVel: 280,
      leadSkill: 0.5,
      dashReady: false,
      crowdControlled: true,
    }),
  )
  assert(
    'release delay lowers xH vs instant (same lead, lateral v)',
    delayed.xH < instant.xH,
    `delay=${delayed.xH.toFixed(3)} inst=${instant.xH.toFixed(3)}`,
  )
}
```

Do **not** soften existing checks. Pass-1/2 lead / approach-flee / reach / heading-error identity tests remain (helpers kept).

---

## 4) Mental regression vs existing 65/65

| Check family | Risk | Why safe / watch |
|--------------|------|------------------|
| corridor\* / xHm / empirics | none | untouched |
| Pass-2 heading-error identity | none | helpers kept; μ path additive |
| lead hi/lo, approach/flee | low | still ordered; delay default 0.28 applies equally |
| point-blank CC high | low | small \(T_d\), tiny walk-off; CC kills juke |
| max-range mobile < PB | low | delay hurts far more than PB → ordering stronger |
| faster missile → higher xH | low | shorter \(t_\text{mis}\) still dominates dodge + μ |
| fleeing edge OOR | low | reach still on \(t_\text{mis}\); cast gate additive |
| OOR corner | none | cast fails hard |
| aim Fitts / T_avail | none | no σ_aim change; timing noise still uses post-release \(v_\perp\) |
| bands / Flash / precommit | low | `dodgeWindow` uses same total clock shape |
| **new** delay ordering | n/a | additive assert only |

**Watch:** default `releaseDelaySec=0.28` changes absolute xH vs Pass-2 numbers but should not flip ordinal invariants. If any ordinal flips, orchestrator may default delay to `0` and require callers/abilities to opt in — still a KEEP if helpers+asserts land.

---

## 5) arXiv ids cited

| id | Role |
|----|------|
| [2403.14997](https://arxiv.org/abs/2403.14997) | \(t_\text{go}\) / closing; chain delay then ballistic segment |
| [2312.09562](https://arxiv.org/abs/2312.09562) | Collision triangle at the engagement (release) epoch |
| [2511.21633](https://arxiv.org/abs/2511.21633) | ZEM / zero-control predicted miss → ray CPA under open-loop aim |
| [1906.02113](https://arxiv.org/abs/1906.02113) | Lead angle still from release-frame \(\lambda^\star\) (Pass-2 carry) |
| [2604.17811](https://arxiv.org/abs/2604.17811) | Miss → corridor hit probability (unchanged `corridorHitProb`) |

Constant-\(v\) residual explicitly deferred to \(\sigma_\text{juke}\) (no PN). Capsule-vs-slab hitbox deferred.

---

## 6) Verdict

**`KEEP_CANDIDATE`**

Minimal GEO deepen only: (1) LOS free-propagate + re-basis across release delay, (2) ballistic ray-CPA for μ under partial lead, (3) split cast-range vs missile-reach gates. Preserves all Pass-1/2 helpers and public API. Does not touch aim/vision/strategy σ models beyond sharing `T_delay` with the existing dodge clock, does not revive BASE×ZONE×VISION, does not add PN.
