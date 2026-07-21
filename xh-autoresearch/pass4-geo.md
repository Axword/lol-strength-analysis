# Pass-4 GEO — capsule tip / accel-free ZEM / LOS edges

**Axis:** geometry / kinematics (deepen Pass-3 residual only)  
**Verdict:** `KEEP_CANDIDATE`  
**Do not edit `src/engine/xh.ts` in this pass** (orchestrator conflict). Snippets are copy-paste for the keeper apply.

Eval baseline at proposal time: **88/88** (`npm run eval:xh`). Do **not** re-propose Pass-1…3 KEEP work (`interceptTimeGo`, lead angle/heading-error, `interceptInMissileRange`, ability width/speed, `propagateLosFrame`, `ballisticRayMiss`, cast∧reach, `releaseDelaySec`).

No BASE×ZONE×VISION. No PN / mid-flight steering.

---

## 1) Critique of Pass-3 geometry (what remains)

Pass-3 landed release-frame LOS, ray-CPA μ, cast∧reach, and delay. Residuals vs open-loop ballistic engagement:

1. **Ray CPA still treats the missile as an infinite-lifetime ray clamped only by \(t_\text{go}\).**  
   LoL skillshots are **finite segments** of travel length \(L \approx R_\text{cast}\) (or kit `missileMaxTravel`). Closest approach after the tip has expired must use the **endpoint**, not a virtual point past max range. Tip misses are Euclidean (radial + lateral); the infinite-slab cookie-cutter \(R_\text{hit}=w/2+R_c\) is still fine as the Minkowski radius of a **capsule** (segment ⊕ disk), but μ must be distance-to-segment, not distance-to-infinite-ray.

2. **Constant-\(v\) μ is still intentional — do not add PN.**  
   Accel belongs in a **bound**, not a guidance loop. Under \(|a_\perp|\le A\) with zero missile control, open-loop ZEM grows by at most \(\tfrac12 A t^2\) beyond the constant-\(v\) predicted miss (classic accel-bounded ZEM envelope). That residual is kinematic geometry, distinct from dash/Flash \(\sigma_\text{juke}\). Default \(A=0\) keeps ordinals; kits/callers opt in via `residualAccelUuPerSec2`.

3. **`propagateLosFrame` singularity when \(R'\to 0\).**  
   After delay, an approaching target can land on the caster. Current code returns cast-time \((v_r,v_p)\) unchanged — wrong basis (LOS undefined). Stable fix: preserve speed, put all into perp, clamp \(R'=1\). Overshoot (\(p_x<0\)) is already handled by \(\hat u = p/\|p\|\); add an eval identity that \(|v|\) is preserved across the flip.

4. **Ability delay is wired; segment length is not.**  
   `releaseDelaySec` already flows `AbilityDefinition → abilityXhPreview → estimateXh`. Missing geo field: optional `missileMaxTravelUu` (defaults to `ability.range`) so tip clamp matches kit range, not an assumed infinite ray at \(V_m t_\text{go}\).

5. **Slab vs capsule (document + μ only).**  
   Do **not** replace `corridorHitProb` with a 2D integral. Keep 1D corridor with \(R_\text{hit}=w/2+R_c\) as capsule radius; sharpen **μ** via segment CPA. That is the minimal tip deepen Pass-3 deferred.

---

## 2) Exact TypeScript snippets (copy-paste ready)

### 2a) Harden `propagateLosFrame` (replace body; same signature)

```typescript
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
  if (!(Rp > 1e-6)) {
    // Coincident after delay: LOS undefined — preserve speed, radial 0.
    const spd = Math.hypot(vRadial, vPerp)
    return { rangeUu: 1, vRadial: 0, vPerp: spd }
  }
  const ux = px / Rp
  const uy = py / Rp
  const vRadp = vRadial * ux + vPerp * uy
  const vPerpp = -vRadial * uy + vPerp * ux
  return { rangeUu: Rp, vRadial: vRadp, vPerp: vPerpp }
}
```

### 2b) New helpers (after `ballisticRayMiss`; keep ray helper for Pass-3 identity tests)

```typescript
/**
 * Accel-bounded open-loop ZEM extra (no PN): |ΔZEM| ≤ ½ A t² under |a_perp|≤A.
 * Default unused (A=0). Distinct from dash/Flash σ_juke.
 * arXiv:2511.21633 (ZEM); arXiv:1909.04189 (accel-bounded miss envelopes).
 */
export function boundedAccelZemExtra(
  tGoSec: number,
  aMaxPerpUuPerSec2 = 0,
): number {
  const t = Math.max(0, tGoSec)
  return 0.5 * Math.max(0, aMaxPerpUuPerSec2) * t * t
}

/**
 * Finite-segment ballistic CPA: clamp engagement to missile travel length L.
 * Tip/capsule: miss is distance to segment (endpoint past max range), not
 * infinite ray. Capsule radius remains w/2+R_champ in corridorHitProb.
 * arXiv:2604.17811 (miss→hit); Minkowski segment⊕disk = stadium/capsule.
 */
export function ballisticSegmentMiss(
  rangeUu: number,
  vRadial: number,
  vPerp: number,
  missileSpeed: number,
  aimAngleRad: number,
  tMax: number,
  maxTravelUu: number,
): number {
  const Vm = Math.max(200, missileSpeed)
  const L = Math.max(1, maxTravelUu)
  const tSeg = Math.min(Math.max(0, tMax), L / Vm)
  return ballisticRayMiss(
    rangeUu,
    vRadial,
    vPerp,
    Vm,
    aimAngleRad,
    tSeg,
  )
}

/** Capsule (stadium) hit radius: segment half-width ⊕ champ disk. */
export function capsuleHitRadius(
  missileWidth: number,
  champRadius = CHAMP_RADIUS,
): number {
  return Math.max(1, missileWidth) / 2 + champRadius
}
```

### 2c) Optional inputs (geo only)

```typescript
// on XhEstimateInput:
/** Residual |a_perp| bound (uu/s²) for accel-free ZEM extra. Default 0. */
residualAccelUuPerSec2?: number
/** Missile max travel (uu); tip clamp. Default = abilityRange. */
missileMaxTravelUu?: number

// on AbilityDefinition (cheap, like width/speed/delay):
/** Max missile travel (uu); defaults to `range` when unset. */
missileMaxTravelUu?: number
```

Wire in `abilityXhPreview`:

```typescript
  return estimateXh({
    ...input,
    abilityRange: ability.range,
    missileWidth: input.missileWidth ?? ability.missileWidth,
    missileSpeed: input.missileSpeed ?? ability.missileSpeed,
    releaseDelaySec: input.releaseDelaySec ?? ability.releaseDelaySec,
    missileMaxTravelUu:
      input.missileMaxTravelUu ?? ability.missileMaxTravelUu ?? ability.range,
    skillshotLengthPenalty: ability.range >= 900,
  })
```

### 2d) Patch μ / R_hit inside `estimateXh` (keep Pass-3 delay + cast∧reach)

Replace width/`R_hit` and `muBias` construction only:

```typescript
  const width = input.missileWidth ?? defaultMissileWidth(range)
  const R_hit = capsuleHitRadius(width) // same numeric as width/2+CHAMP_RADIUS
  // ... existing propagateLosFrame / tGoMis / lamStar / lamAim ...
  const Ltravel = input.missileMaxTravelUu ?? input.abilityRange
  const segMiss = ballisticSegmentMiss(
    distRel,
    vRadial,
    vPerp,
    vMissile,
    lamAim,
    tGoMis,
    Ltravel + CHAMP_RADIUS, // tip includes hitbox reach past nominal cast edge
  )
  const zemExtra = boundedAccelZemExtra(
    tGoMis,
    input.residualAccelUuPerSec2 ?? 0,
  )
  const muBias = segMiss + zemExtra
  factors.push(
    `t_go:${tGo.toFixed(2)}s`,
    `t_delay:${T_delay.toFixed(2)}s`,
    `lead_deg:${((lamStar * 180) / Math.PI).toFixed(1)}`,
    `R_hit:${Math.round(R_hit)}`,
    `L_travel:${Math.round(Ltravel)}`,
  )
```

**Zero-opt-in equivalence:** `missileMaxTravelUu` default = `abilityRange` and \(A=0\) ⇒ for in-range intercepts with \(V_m t_\text{go} \le L\), `ballisticSegmentMiss` ≡ `ballisticRayMiss` (Pass-3). Tip only bites when CPA time would exceed \(L/V_m\) (partial lead near max range / short missiles).

Keep `ballisticRayMiss` exported for Pass-3 eval identity.

---

## 3) New invariant check(s) to ADD to eval (string form)

Import: `ballisticSegmentMiss`, `boundedAccelZemExtra`, `capsuleHitRadius`.

```typescript
// --- geometry deepen (Pass-4 GEO) ---
{
  // LOS coincident after delay: stable frame, |v| preserved.
  const c = propagateLosFrame(100, -500, 0, 0.25) // lands at origin
  assert(
    'LOS collapse: R\' clamped, |v| preserved',
    c.rangeUu === 1 && Math.abs(Math.hypot(c.vRadial, c.vPerp) - 500) < 1e-6,
    `R'=${c.rangeUu} |v|=${Math.hypot(c.vRadial, c.vPerp).toFixed(3)}`,
  )
}
{
  // Overshoot past caster: px<0 flips û; |v| identity.
  const o = propagateLosFrame(200, -800, 100, 0.5)
  assert(
    'LOS overshoot: |v| preserved after re-basis',
    Math.abs(Math.hypot(o.vRadial, o.vPerp) - Math.hypot(-800, 100)) < 1e-6,
  )
  assert('LOS overshoot: range = |p|', o.rangeUu > 1)
}
{
  const R = 1000
  const Vm = 1600
  const vp = 200
  const tg = interceptTimeGo(R, Vm, 0, vp)
  const lam = requiredLeadAngle(tg, R, 0, vp)
  const ray = ballisticRayMiss(R, 0, vp, Vm, lam, tg)
  const seg = ballisticSegmentMiss(R, 0, vp, Vm, lam, tg, R + 65)
  assert(
    'segment ≡ ray when L covers intercept',
    Math.abs(seg - ray) < 1e-9,
    `seg=${seg.toFixed(6)} ray=${ray.toFixed(6)}`,
  )
}
{
  // Tip: very short travel ⇒ endpoint miss ≫ long segment at zero lead.
  const short = ballisticSegmentMiss(1000, 0, 250, 1600, 0, 1.0, 200)
  const long = ballisticSegmentMiss(1000, 0, 250, 1600, 0, 1.0, 2000)
  assert(
    'tip clamp: short L → larger miss than long L (zero lead)',
    short > long + 50,
    `short=${short.toFixed(1)} long=${long.toFixed(1)}`,
  )
}
assert(
  'capsule radius = w/2 + champ',
  Math.abs(capsuleHitRadius(140) - (70 + 65)) < 1e-12,
)
assert(
  'boundedAccelZemExtra: ½ A t²',
  Math.abs(boundedAccelZemExtra(0.5, 800) - 100) < 1e-9,
)
assert('boundedAccelZemExtra: A=0 → 0', boundedAccelZemExtra(1.2, 0) === 0)
{
  const tippy = estimateXh(
    base({
      targetPosition: far,
      abilityRange: 1175,
      missileMaxTravelUu: 400, // artificially short tip
      missileSpeed: 1200,
      missileWidth: 70,
      leadSkill: 0.3,
      targetPerpVel: 280,
      dashReady: false,
      crowdControlled: true,
      residualAccelUuPerSec2: 0,
    }),
  )
  const full = estimateXh(
    base({
      targetPosition: far,
      abilityRange: 1175,
      missileMaxTravelUu: 1175,
      missileSpeed: 1200,
      missileWidth: 70,
      leadSkill: 0.3,
      targetPerpVel: 280,
      dashReady: false,
      crowdControlled: true,
      residualAccelUuPerSec2: 0,
    }),
  )
  assert(
    'short missile travel lowers xH vs full travel (tip)',
    tippy.xH < full.xH,
    `tip=${tippy.xH.toFixed(3)} full=${full.xH.toFixed(3)}`,
  )
}
{
  const withA = estimateXh(
    base({
      residualAccelUuPerSec2: 900,
      targetPerpVel: 220,
      leadSkill: 0.7,
      dashReady: false,
      crowdControlled: true,
    }),
  )
  const noA = estimateXh(
    base({
      residualAccelUuPerSec2: 0,
      targetPerpVel: 220,
      leadSkill: 0.7,
      dashReady: false,
      crowdControlled: true,
    }),
  )
  assert(
    'accel ZEM extra lowers xH vs A=0 (same lead)',
    withA.xH < noA.xH,
    `A=${withA.xH.toFixed(3)} 0=${noA.xH.toFixed(3)}`,
  )
}
```

Do **not** soften existing checks. Pass-3 ray-CPA / propagate / cast∧reach tests remain (`ballisticRayMiss` kept).

---

## 4) Mental regression vs existing 88/88

| Check family | Risk | Why safe / watch |
|--------------|------|------------------|
| corridor\* / xHm / empirics | none | untouched |
| Pass-3 ray CPA identity | none | `ballisticRayMiss` kept; segment wraps it |
| Pass-3 propagate v=0 / perp grow | none | singularity branch only when \(R'\approx0\) |
| lead hi/lo, approach/flee | low | default \(L=R\), \(A=0\) ⇒ μ unchanged in-range |
| point-blank CC high | none | tip irrelevant; \(A=0\) |
| max-range mobile < PB | low | tip can only **lower** far xH → ordering stronger |
| faster missile → higher xH | low | shorter \(t\) still dominates; tip less binding when fast |
| fleeing edge OOR | none | cast∧reach unchanged |
| aim / vision / strategy σ | none | no σ model edits; delay clock unchanged |
| **new** tip / A ordering | n/a | additive asserts; default path ≡ Pass-3 |

**Watch:** `Ltravel + CHAMP_RADIUS` tip budget must not accidentally widen reach gating — reach still uses `interceptInMissileRange(tGoMis, …)` only. If a future kit sets `missileMaxTravelUu ≪ range`, expect lower xH (correct) without flipping OOR cast gate.

---

## 5) arXiv ids cited

| id | Role |
|----|------|
| [2511.21633](https://arxiv.org/abs/2511.21633) | ZEM / zero-control predicted miss; accel-bounded envelope without guidance |
| [1909.04189](https://arxiv.org/abs/1909.04189) | Accel-bounded miss / capture geometry (open-loop bounds, not PN) |
| [2604.17811](https://arxiv.org/abs/2604.17811) | Miss → corridor hit probability (unchanged `corridorHitProb`) |
| [2403.14997](https://arxiv.org/abs/2403.14997) | \(t_\text{go}\) / finite engagement horizon (segment lifetime) |
| [2312.09562](https://arxiv.org/abs/2312.09562) | Collision triangle at release epoch (Pass-3 carry; LOS re-basis) |

No PN. Capsule = segment ⊕ disk (computational geometry / firing theory), radius shared with existing slab \(R_\text{hit}\).

---

## 6) Verdict

**`KEEP_CANDIDATE`**

Minimal GEO deepen only: (1) finite-segment tip CPA for μ, (2) accel-free \(\tfrac12 A t^2\) ZEM extra with default \(A=0\), (3) LOS collapse/overshoot re-basis edges, (4) `missileMaxTravelUu` ability wiring. Preserves Pass-1…3 helpers and public API. Default path ≡ Pass-3 numerics for in-range intercepts. Does not touch aim/vision/strategy σ models, does not revive BASE×ZONE×VISION, does not add PN.

KEEP_CANDIDATE
