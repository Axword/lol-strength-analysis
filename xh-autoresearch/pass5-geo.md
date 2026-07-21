# Pass-5 GEO — finite engagement horizon / reach≡travel

**Axis:** geometry / kinematics (deepen Pass-4 residual only)  
**Verdict:** `KEEP_CANDIDATE`  
**Do not edit `src/engine/xh.ts` in this pass** (orchestrator conflict). Snippets are copy-paste for the keeper apply.

Eval baseline at proposal time: **103/103** (`npm run eval:xh`). Do **not** re-propose Pass-1…4 KEEP work (`interceptTimeGo`, lead/heading, `interceptInMissileRange`, width/speed, `propagateLosFrame`, `ballisticRayMiss`/`ballisticSegmentMiss`, cast∧reach, `releaseDelaySec`, capsule tip, accel ZEM extra, `missileMaxTravelUu`, LOS collapse).

No BASE×ZONE×VISION. No PN / mid-flight steering.

---

## 1) Critique of Pass-4 geometry (what remains)

Pass-4 landed tip-clamped segment CPA, capsule `R_hit`, accel-free \(\tfrac12 A t^2\), `missileMaxTravelUu`, and LOS collapse. Residuals vs open-loop ballistic engagement:

1. **Lead still solved on the unreachable intercept clock.**  
   `lamStar = requiredLeadAngle(tGoMis, …)` uses full collision-triangle \(t_\text{go}\), then `ballisticSegmentMiss` clamps CPA to \(T_L=L/V_m\). When \(T_L < t_\text{go}\) (short travel / tip binds), perfect lead aims at a point the missile never reaches. Finite-horizon collision triangle: aim at the target pose at \(t_\text{eng}=\min(t_\text{go},T_L)\). That is still open-loop lead — not PN.

2. **Reach gate ignores `missileMaxTravelUu`.**  
   Cast∧reach uses `interceptInMissileRange(tGoMis, V_m, abilityRange)` while μ tip uses `Ltravel`. Pass-4 watch note: short \(L\) lowers xH without flipping OOR. Correct kinematics: **missile reach budget is \(L\)**, cast legality stays `abilityRange`. Default \(L=\texttt{abilityRange}\) ⇒ identical to Pass-4.

3. **Accel ZEM extra accumulates past tip death.**  
   `boundedAccelZemExtra(tGoMis, A)` integrates over intercept \(t_\text{go}\) even when the segment dies at \(T_L\). Bound the same horizon: \(\tfrac12 A t_\text{eng}^2\).

4. **Default path must stay bit-identical when \(L=R_\text{cast}\).**  
   For in-reach intercepts, \(V_m t_\text{go} \le R+R_c = L_\text{eff}\) ⇒ \(t_\text{eng}=t_\text{go}\). Horizon + reach wiring are no-ops on the default kit path (preserves 103/103 ordinals).

Do **not** replace `corridorHitProb` with a 2D capsule integral. Do **not** touch aim/vision/strategy σ.

---

## 2) Exact TypeScript snippets (copy-paste ready)

### 2a) New helper (after `ballisticSegmentMiss`; keep Pass-4 helpers unchanged)

```typescript
/**
 * Finite engagement horizon: missile dies at tip travel L/V_m.
 * Lead / CPA / accel-ZEM use t_eng = min(t_go, L/V_m), not unreachable
 * intercept time. Open-loop only — no PN.
 * arXiv:2403.14997 (finite t_go / engagement horizon);
 * arXiv:2312.09562 (collision triangle at engagement epoch).
 */
export function engagementHorizonSec(
  tGoInterceptSec: number,
  missileSpeed: number,
  maxTravelUu: number,
): number {
  const Vm = Math.max(200, missileSpeed)
  const tL = Math.max(1, maxTravelUu) / Vm
  return Math.min(Math.max(0, tGoInterceptSec), tL)
}
```

### 2b) Patch inside `estimateXh` (after `Ltravel`; keep delay / cast∧reach structure)

Replace lead / μ / reach wiring only:

```typescript
  const Ltravel = input.missileMaxTravelUu ?? input.abilityRange
  const L_eff = Ltravel + CHAMP_RADIUS
  const tEng = engagementHorizonSec(tGoMis, vMissile, L_eff)
  const lamStar = requiredLeadAngle(tEng, distRel, vRadial, vPerp)
  const lamAim = lamStar * leadSkill
  const segMiss = ballisticSegmentMiss(
    distRel,
    vRadial,
    vPerp,
    vMissile,
    lamAim,
    tEng, // was tGoMis — horizon already ≤ L/V_m
    L_eff,
  )
  const zemExtra = boundedAccelZemExtra(
    tEng, // was tGoMis
    input.residualAccelUuPerSec2 ?? 0,
  )
  const muBias = segMiss + zemExtra
  factors.push(
    `t_go:${tGo.toFixed(2)}s`,
    `t_eng:${tEng.toFixed(2)}s`,
    `t_delay:${T_delay.toFixed(2)}s`,
    `lead_deg:${((lamStar * 180) / Math.PI).toFixed(1)}`,
    `R_hit:${Math.round(R_hit)}`,
    `L_travel:${Math.round(Ltravel)}`,
  )
```

Reach gate (cast still on `abilityRange`):

```typescript
    const castOk = inCastRange(distance, input.abilityRange)
    // Missile travel budget = Ltravel (default ≡ abilityRange).
    const reachOk = interceptInMissileRange(tGoMis, vMissile, Ltravel)
    inRange = castOk && reachOk
```

### 2c) Soft-vision multi-mean μ (same horizon)

Where `muSeen` is built from `beliefMeanSeen`, mirror the same `tEng` / `L_eff` / lead clock (do not leave seen-component on full `tS` while lost uses `tEng`).

```typescript
    const tS = interceptTimeGo(atS.rangeUu, vMissile, atS.vRadial, atS.vPerp)
    const tEngS = engagementHorizonSec(tS, vMissile, L_eff)
    const lamS = requiredLeadAngle(tEngS, atS.rangeUu, atS.vRadial, atS.vPerp)
    muSeen = ballisticSegmentMiss(
      atS.rangeUu,
      atS.vRadial,
      atS.vPerp,
      vMissile,
      lamS * leadSkill,
      tEngS,
      L_eff,
    )
```

**Zero-opt-in equivalence:** default `missileMaxTravelUu = abilityRange` and in-reach ⇒ \(t_\text{eng}=t_\text{go}\), reach gate ≡ Pass-4, μ ≡ Pass-4 segment CPA.

Leave dodge window on full `tGoMis` (strategy clock); geo lead/μ/A only.

---

## 3) New invariant check(s) to ADD to eval (string form)

Import: `engagementHorizonSec` (plus existing `ballisticSegmentMiss`, `ballisticRayMiss`, `interceptTimeGo`, `requiredLeadAngle`).

```typescript
// --- geometry deepen (Pass-5 GEO) ---
{
  const R = 1000
  const Vm = 1600
  const L = R + 65
  const tg = interceptTimeGo(R, Vm, 0, 200)
  const te = engagementHorizonSec(tg, Vm, L)
  assert(
    'horizon ≡ t_go when L covers in-reach intercept',
    Math.abs(te - tg) < 1e-12,
    `te=${te.toFixed(6)} tg=${tg.toFixed(6)}`,
  )
}
{
  const te = engagementHorizonSec(1.2, 1600, 400) // T_L = 0.25
  assert(
    'horizon clamps to L/V_m when tip binds',
    Math.abs(te - 400 / 1600) < 1e-12,
    `te=${te}`,
  )
}
{
  // Finite-horizon lead beats unreachable-intercept lead under short L.
  const R = 1000
  const Vm = 1600
  const vp = 250
  const L = 350
  const tg = interceptTimeGo(R, Vm, 0, vp)
  const te = engagementHorizonSec(tg, Vm, L)
  const lamFar = requiredLeadAngle(tg, R, 0, vp) // unreachable clock
  const lamHor = requiredLeadAngle(te, R, 0, vp) // tip clock
  const missFar = ballisticSegmentMiss(R, 0, vp, Vm, lamFar, te, L)
  const missHor = ballisticSegmentMiss(R, 0, vp, Vm, lamHor, te, L)
  assert(
    'finite-horizon lead ≤ unreachable-intercept lead miss (short L)',
    missHor <= missFar + 1e-9,
    `hor=${missHor.toFixed(2)} far=${missFar.toFixed(2)}`,
  )
}
{
  const tipOor = estimateXh(
    base({
      targetPosition: far,
      abilityRange: 1175,
      missileMaxTravelUu: 200, // travel << cast
      missileSpeed: 1200,
      missileWidth: 70,
      leadSkill: 0.8,
      targetPerpVel: 0,
      targetRadialVel: 0,
      dashReady: false,
      crowdControlled: true,
    }),
  )
  assert(
    'short Ltravel → reach OOR (cast may still be legal)',
    tipOor.inRange === false && tipOor.factors.includes('reach_oor'),
    `inRange=${tipOor.inRange} factors=${tipOor.factors.join(',')}`,
  )
}
{
  const shortA = estimateXh(
    base({
      residualAccelUuPerSec2: 900,
      missileMaxTravelUu: 400,
      abilityRange: 1175,
      targetPerpVel: 220,
      leadSkill: 0.7,
      dashReady: false,
      crowdControlled: true,
    }),
  )
  // If still inRange under this L, A>0 must not raise xH vs A=0 on same horizon.
  const short0 = estimateXh(
    base({
      residualAccelUuPerSec2: 0,
      missileMaxTravelUu: 400,
      abilityRange: 1175,
      targetPerpVel: 220,
      leadSkill: 0.7,
      dashReady: false,
      crowdControlled: true,
    }),
  )
  if (shortA.inRange && short0.inRange) {
    assert(
      'horizon-clamped accel ZEM: A>0 → xH ≤ A=0 (short L)',
      shortA.xH <= short0.xH + 1e-6,
      `A=${shortA.xH.toFixed(3)} 0=${short0.xH.toFixed(3)}`,
    )
  }
}
{
  // Default L=R: horizon no-op vs Pass-4 numerics on a fixed fixture.
  const def = estimateXh(
    base({
      leadSkill: 0.7,
      targetPerpVel: 200,
      dashReady: false,
      crowdControlled: true,
      residualAccelUuPerSec2: 0,
    }),
  )
  assert('default path still in range', def.inRange === true)
  assert('default xH finite', Number.isFinite(def.xH) && def.xH > 0)
}
```

Do **not** soften existing checks. Pass-4 LOS / accel and Pass-3 ray-CPA remain.

---

## 4) Mental regression vs existing 103/103

| Check family | Risk | Why safe / watch |
|--------------|------|------------------|
| corridor\* / xHm / empirics | none | untouched |
| Pass-3/4 ray/segment helpers | none | wrappers only; new `engagementHorizonSec` |
| lead hi/lo, approach/flee | none | default \(L=R\) ⇒ \(t_\text{eng}=t_\text{go}\) in-reach |
| Pass-4 accel ZEM | none | same when \(t_\text{eng}=t_\text{go}\); short-\(L\) uses smaller \(t\) |
| point-blank CC high | none | tip/horizon irrelevant |
| max-range mobile < PB | low | short \(L\) can OOR (stricter); default unchanged |
| fleeing edge OOR | none | reach still \(V_m t_\text{go}\) vs budget; budget default \(=R\) |
| aim / vision / strategy σ | none | dodge clock still full `tGoMis`; no σ edits |
| **new** short-\(L\) reach_oor | n/a | intentional consistency with tip travel |

**Watch:** callers that set `missileMaxTravelUu ≪ abilityRange` and expected soft tip-in-range xH will now see `reach_oor` (xH=0). That matches cast∧reach semantics; document in apply notes.

---

## 5) arXiv ids cited

| id | Role |
|----|------|
| [2403.14997](https://arxiv.org/abs/2403.14997) | Finite engagement horizon / \(t_\text{go}\) chain (tip lifetime) |
| [2312.09562](https://arxiv.org/abs/2312.09562) | Collision triangle at engagement epoch (horizon lead) |
| [2511.21633](https://arxiv.org/abs/2511.21633) | ZEM / zero-control miss (accel bound still open-loop) |
| [2604.17811](https://arxiv.org/abs/2604.17811) | Miss → corridor hit probability (unchanged `corridorHitProb`) |
| [1906.02113](https://arxiv.org/abs/1906.02113) | Open-loop lead angle (Pass-2 carry; horizon clock only) |

No PN. Capsule tip / segment CPA / LOS collapse remain Pass-4; this pass only aligns lead + reach + accel clocks with tip travel.

---

## 6) Verdict

**`KEEP_CANDIDATE`**

Minimal GEO deepen only: (1) `engagementHorizonSec` so lead/μ/accel use tip lifetime when \(L/V_m < t_\text{go}\), (2) reach gate on `Ltravel` (cast still `abilityRange`), (3) softVision multi-mean μ on the same horizon. Default \(L=R\) in-reach path ≡ Pass-4. Does not revive BASE×ZONE×VISION, does not add PN, does not re-propose Pass-1…4 helpers.

KEEP_CANDIDATE
