# Pass-6 GEO — CPA-epoch accel ZEM + delay clock / muSeen parity

**Axis:** geometry / kinematics (deepen Pass-5 residual only)  
**Verdict:** `KEEP_CANDIDATE`  
**Do not edit `src/engine/xh.ts` in this pass** (orchestrator applies). Snippets are copy-paste for the keeper apply.

Eval baseline at proposal time: **129/129** (`npm run eval:xh`). Do **not** re-propose Pass-1…5 KEEP work (`interceptTimeGo`, lead/heading, `interceptInMissileRange`, width/speed, `propagateLosFrame`, `ballisticRayMiss`/`ballisticSegmentMiss`, cast∧reach, `releaseDelaySec`, capsule tip, `missileMaxTravelUu`, LOS collapse, `engagementHorizonSec`, lead/μ on `t_eng`, reach vs `Ltravel`) unless fixing a clear regression.

No BASE×ZONE×VISION. No PN / mid-flight steering.

---

## 1) Critique of Pass-5 residual geometry

Pass-5 aligned lead / segment μ / accel extra / reach with tip horizon \(t_\text{eng}=\min(t_\text{go},L/V_m)\). Residuals vs open-loop ballistic engagement:

1. **Accel ZEM still integrates to the tip/horizon pad, not the CPA epoch.**  
   `boundedAccelZemExtra(tEng, A)` accumulates \(\tfrac12 A t_\text{eng}^2\) even when `ballisticSegmentMiss`’s closest approach is at \(t_\text{cpa}<t_\text{eng}\) (glancing / early CPA on the finite segment). Open-loop ZEM is the miss **at the engagement epoch used for μ** — that epoch is \(t_\text{cpa}\), not the unused tip remainder. Still a bound (no PN): \(|\Delta\mathrm{ZEM}|\le\tfrac12 A t_\text{cpa}^2\) under \(|a_\perp|\le A\).

2. **Fire-control delay is excluded from the accel envelope.**  
   Constant-\(v\) motion during `releaseDelaySec` is already folded via `propagateLosFrame`, but the **accel residual** beyond that assumption runs from cast→CPA. Multi-segment TOF clock: \(t_A=T_\text{delay}+t_\text{cpa}\). Pass-5 left A on post-release `t_eng` only, so long windups under \(A>0\) understate μ.

3. **Soft-vision `muSeen` drops accel ZEM (parity bug).**  
   Lost-component `muBias = segMiss + zemExtra`, but the `beliefMeanSeen` branch sets `muSeen = ballisticSegmentMiss(...)` with **no** `zemExtra`. Same \(A\) must apply to both mixture arms; otherwise penumbra systematically ignores residual accel.

4. **Default path must stay bit-identical when \(A=0\).**  
   All three changes are no-ops for the default kit path (`residualAccelUuPerSec2` unset/0). Lead / `t_eng` / reach / capsule / delay propagate stay Pass-5.

Do **not** replace `corridorHitProb` with a 2D capsule integral. Do **not** touch aim/vision/strategy σ. Do **not** change `engagementHorizonSec` lead clock (Pass-5 KEEP).

---

## 2) Exact TypeScript snippets (copy-paste ready)

### 2a) New helpers (after `ballisticSegmentMiss`; keep Pass-4/5 helpers)

```typescript
/**
 * Finite-segment ballistic CPA + engagement epoch.
 * μ uses missUu; accel-ZEM integrates to tCpaSec (not tip pad).
 * Open-loop only — no PN.
 * arXiv:2511.21633 (ZEM at terminal/engagement epoch);
 * arXiv:2403.14997 (t_go / engagement clock).
 */
export function ballisticSegmentCpa(
  rangeUu: number,
  vRadial: number,
  vPerp: number,
  missileSpeed: number,
  aimAngleRad: number,
  tMax: number,
  maxTravelUu: number,
): { missUu: number; tCpaSec: number } {
  const Vm = Math.max(200, missileSpeed)
  const L = Math.max(1, maxTravelUu)
  const tSeg = Math.min(Math.max(0, tMax), L / Vm)
  const R = Math.max(1, rangeUu)
  const c = Math.cos(aimAngleRad)
  const s = Math.sin(aimAngleRad)
  const wx = vRadial - Vm * c
  const wy = vPerp - Vm * s
  const w2 = wx * wx + wy * wy
  let tStar = 0
  if (w2 > 1e-12) {
    tStar = -(R * wx) / w2
  }
  const t = Math.min(Math.max(0, tSeg), Math.max(0, tStar))
  const mx = Vm * t * c
  const my = Vm * t * s
  const px = R + vRadial * t
  const py = vPerp * t
  return { missUu: Math.hypot(px - mx, py - my), tCpaSec: t }
}

/**
 * Accel-envelope clock: fire-control delay + flight to CPA.
 * Constant-v delay is in propagateLosFrame; A-residual spans cast→CPA.
 * arXiv:2312.09562 (multi-segment engagement); arXiv:2511.21633 (ZEM bound).
 */
export function accelZemClockSec(
  releaseDelaySec: number,
  tCpaFlightSec: number,
): number {
  return Math.max(0, releaseDelaySec) + Math.max(0, tCpaFlightSec)
}
```

Optional DRY (same file): reimplement `ballisticSegmentMiss` as:

```typescript
export function ballisticSegmentMiss(
  rangeUu: number,
  vRadial: number,
  vPerp: number,
  missileSpeed: number,
  aimAngleRad: number,
  tMax: number,
  maxTravelUu: number,
): number {
  return ballisticSegmentCpa(
    rangeUu,
    vRadial,
    vPerp,
    missileSpeed,
    aimAngleRad,
    tMax,
    maxTravelUu,
  ).missUu
}
```

### 2b) Patch inside `estimateXh` (replace segMiss / zemExtra / muBias only)

Keep `tEng` / `lamStar` / `lamAim` / reach gate exactly as Pass-5:

```typescript
  const lamAim = lamStar * leadSkill
  const cpa = ballisticSegmentCpa(
    distRel,
    vRadial,
    vPerp,
    vMissile,
    lamAim,
    tEng,
    L_eff,
  )
  const zemClock = accelZemClockSec(T_delay, cpa.tCpaSec)
  const zemExtra = boundedAccelZemExtra(
    zemClock, // was tEng — CPA epoch + delay
    input.residualAccelUuPerSec2 ?? 0,
  )
  const muBias = cpa.missUu + zemExtra
  factors.push(
    `t_go:${tGo.toFixed(2)}s`,
    `t_eng:${tEng.toFixed(2)}s`,
    `t_cpa:${cpa.tCpaSec.toFixed(2)}s`,
    `t_delay:${T_delay.toFixed(2)}s`,
    `lead_deg:${((lamStar * 180) / Math.PI).toFixed(1)}`,
    `R_hit:${Math.round(R_hit)}`,
    `L_travel:${Math.round(Ltravel)}`,
  )
```

### 2c) Soft-vision multi-mean μ (accel parity)

```typescript
    const tS = interceptTimeGo(atS.rangeUu, vMissile, atS.vRadial, atS.vPerp)
    const tEngS = engagementHorizonSec(tS, vMissile, L_eff)
    const lamS = requiredLeadAngle(tEngS, atS.rangeUu, atS.vRadial, atS.vPerp)
    const cpaS = ballisticSegmentCpa(
      atS.rangeUu,
      atS.vRadial,
      atS.vPerp,
      vMissile,
      lamS * leadSkill,
      tEngS,
      L_eff,
    )
    const zemS = boundedAccelZemExtra(
      accelZemClockSec(T_delay, cpaS.tCpaSec),
      input.residualAccelUuPerSec2 ?? 0,
    )
    muSeen = cpaS.missUu + zemS
```

**Zero-opt-in equivalence:** `A=0` ⇒ `zemExtra=0`, `muBias=cpa.missUu` ≡ Pass-5 `ballisticSegmentMiss`, `muSeen` ≡ Pass-5 miss (parity fix is also a no-op when \(A=0\)).

Leave dodge window on full `tGoMis` (strategy clock). Leave lead on `tEng` (Pass-5).

---

## 3) New invariant check(s) to ADD to eval (string form)

Import: `ballisticSegmentCpa`, `accelZemClockSec` (plus existing `ballisticSegmentMiss`, `boundedAccelZemExtra`, `engagementHorizonSec`).

```typescript
// --- geometry deepen (Pass-6 GEO) ---
{
  const R = 1000
  const Vm = 1600
  const vp = 220
  const L = R + 65
  const tg = interceptTimeGo(R, Vm, 0, vp)
  const te = engagementHorizonSec(tg, Vm, L)
  const lam = requiredLeadAngle(te, R, 0, vp) * 0.55
  const miss = ballisticSegmentMiss(R, 0, vp, Vm, lam, te, L)
  const cpa = ballisticSegmentCpa(R, 0, vp, Vm, lam, te, L)
  assert(
    'Pass-6: segment CPA miss ≡ ballisticSegmentMiss',
    Math.abs(cpa.missUu - miss) < 1e-12,
    `cpa=${cpa.missUu} miss=${miss}`,
  )
  assert(
    'Pass-6: t_cpa ∈ [0, t_eng]',
    cpa.tCpaSec >= -1e-12 && cpa.tCpaSec <= te + 1e-12,
    `tCpa=${cpa.tCpaSec} te=${te}`,
  )
}
{
  const clock = accelZemClockSec(0.28, 0.5)
  assert(
    'Pass-6: accel clock = delay + t_cpa',
    Math.abs(clock - 0.78) < 1e-12,
    `clock=${clock}`,
  )
  assert(
    'Pass-6: accel ZEM at delay+cpa ≥ flight-only',
    boundedAccelZemExtra(clock, 800) >=
      boundedAccelZemExtra(0.5, 800) - 1e-9,
  )
}
{
  // Early CPA: tip-long segment, aim nearly on LOS → CPA before tip.
  const cpaEarly = ballisticSegmentCpa(800, -100, 40, 2000, 0.02, 2.0, 5000)
  assert(
    'Pass-6: glancing CPA can bind before tMax',
    cpaEarly.tCpaSec < 2.0 - 1e-6,
    `tCpa=${cpaEarly.tCpaSec}`,
  )
}
{
  const longDelayA = estimateXh(
    base({
      residualAccelUuPerSec2: 700,
      releaseDelaySec: 0.55,
      targetPerpVel: 200,
      leadSkill: 0.7,
      dashReady: false,
      crowdControlled: true,
    }),
  )
  const shortDelayA = estimateXh(
    base({
      residualAccelUuPerSec2: 700,
      releaseDelaySec: 0.05,
      targetPerpVel: 200,
      leadSkill: 0.7,
      dashReady: false,
      crowdControlled: true,
    }),
  )
  assert(
    'Pass-6: delay-inclusive accel ZEM: longer delay → xH ≤ shorter (A>0)',
    longDelayA.inRange &&
      shortDelayA.inRange &&
      longDelayA.xH <= shortDelayA.xH + 1e-6,
    `long=${longDelayA.xH.toFixed(3)} short=${shortDelayA.xH.toFixed(3)}`,
  )
}
{
  // mid/near are eval fixtures; seen-mean slightly offset from near.
  const seen = { x: (mid.x + near.x) / 2, y: near.y }
  const withA = estimateXh(
    base({
      residualAccelUuPerSec2: 900,
      targetPerpVel: 210,
      leadSkill: 0.65,
      dashReady: false,
      crowdControlled: true,
      beliefMeanPosition: near,
      beliefMeanSeen: seen,
      softVision: 0.45,
      vision: 'unknown',
      lastKnownAgeSec: 1.2,
    }),
  )
  const noA = estimateXh(
    base({
      residualAccelUuPerSec2: 0,
      targetPerpVel: 210,
      leadSkill: 0.65,
      dashReady: false,
      crowdControlled: true,
      beliefMeanPosition: near,
      beliefMeanSeen: seen,
      softVision: 0.45,
      vision: 'unknown',
      lastKnownAgeSec: 1.2,
    }),
  )
  if (withA.inRange && noA.inRange) {
    assert(
      'Pass-6: muSeen accel parity: A>0 → xH ≤ A=0 (soft multi-mean)',
      withA.xH <= noA.xH + 1e-6,
      `A=${withA.xH.toFixed(3)} 0=${noA.xH.toFixed(3)}`,
    )
  }
}
{
  // A=0 default path: still in-range finite (bit-identical class).
  const def = estimateXh(
    base({
      leadSkill: 0.7,
      targetPerpVel: 200,
      dashReady: false,
      crowdControlled: true,
      residualAccelUuPerSec2: 0,
    }),
  )
  assert('Pass-6: default A=0 still in range', def.inRange === true)
  assert('Pass-6: default A=0 xH finite', Number.isFinite(def.xH) && def.xH > 0)
  assert(
    'Pass-6: factors expose t_cpa',
    def.factors.some((f) => f.startsWith('t_cpa:')),
    def.factors.join(','),
  )
}
```

Do **not** soften existing checks. Pass-4/5 LOS / horizon / accel ordinals remain.

The soft multi-mean block uses existing eval fixtures `mid` / `near` plus explicit `beliefMeanPosition` / `lastKnownAgeSec` so FoW auto-fill stays deterministic.

---

## 4) Mental regression vs existing 129/129

| Check family | Risk | Why safe / watch |
|--------------|------|------------------|
| corridor\* / xHm / empirics | none | untouched |
| Pass-5 horizon / lead / reach | none | `tEng` / `lamStar` / reach gate unchanged |
| Pass-3/4 ray/segment miss values at A=0 | none | `missUu` ≡ prior `ballisticSegmentMiss` |
| Pass-4 accel ZEM A>0 → lower xH | none | still true; clock ≥ prior `tEng` when delay>0 (stricter μ) |
| Pass-5 short-L accel clamp | low | CPA≤tEng ⇒ A-extra ≤ prior tip-pad extra when delay=0; with default delay, slightly larger envelope (correct) |
| point-blank / lead hi-lo / approach-flee | none | A=0 path |
| aim / vision / strategy σ | none | no σ edits; dodge still full `tGoMis` |
| **new** delay-inclusive A ordering | n/a | intentional |
| **new** muSeen+A parity | n/a | fixes Pass-5 omission |

**Watch:** callers that set `residualAccelUuPerSec2>0` with default `releaseDelaySec≈0.28` will see slightly **lower** xH than Pass-5 (delay enters A-clock). Default \(A=0\) unchanged.

---

## 5) arXiv ids cited

| id | Role |
|----|------|
| [2511.21633](https://arxiv.org/abs/2511.21633) | ZEM at terminal/engagement epoch (CPA clock, not tip pad) |
| [2403.14997](https://arxiv.org/abs/2403.14997) | Engagement / \(t_\text{go}\) chain (flight segment of multi-TOF) |
| [2312.09562](https://arxiv.org/abs/2312.09562) | Collision-triangle / multi-segment engagement framing |
| [2604.17811](https://arxiv.org/abs/2604.17811) | Miss → corridor hit probability (unchanged `corridorHitProb`) |
| [1906.02113](https://arxiv.org/abs/1906.02113) | Open-loop lead (unchanged; still on `t_eng`) |

No PN. Capsule tip / `engagementHorizonSec` lead remain Pass-4/5; this pass only aligns **accel-ZEM clock** to delay+CPA and restores **muSeen** accel parity.

---

## 6) Verdict

**`KEEP_CANDIDATE`**

Minimal GEO deepen only: (1) `ballisticSegmentCpa` so accel-ZEM uses \(t_\text{cpa}\) not tip pad, (2) `accelZemClockSec = T_\text{delay}+t_\text{cpa}\) for cast→CPA envelope, (3) softVision `muSeen` gets the same zem extra. Default \(A=0\) path ≡ Pass-5 miss/lead/reach. Does not revive BASE×ZONE×VISION, does not add PN, does not re-propose Pass-1…5 lead/horizon helpers.

KEEP_CANDIDATE
