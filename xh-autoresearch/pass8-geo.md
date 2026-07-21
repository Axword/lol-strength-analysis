# Pass-8 GEO — first-contact extent clock (R_hit on t_eng)

**Axis:** geometry / kinematics (deepen Pass-7 residual only)  
**Verdict:** `KEEP_CANDIDATE`  
**Do not edit `src/engine/xh.ts` in this pass** (orchestrator applies). Snippets are copy-paste for the keeper apply.

Eval baseline at proposal time: **158/158** (`npm run eval:xh`). Do **not** re-propose Pass-1…7 KEEP work (`interceptTimeGo`, lead/heading, `interceptInMissileRange`, width/speed, `propagateLosFrame`, `ballisticRayMiss`/`ballisticSegmentMiss`/`ballisticSegmentCpa`, cast∧reach, `releaseDelaySec`, capsule `R_hit` / tip CPA, accel ZEM, `missileMaxTravelUu`, LOS collapse, `engagementHorizonSec`, lead/μ on `t_eng`, reach vs `Ltravel`, CPA-epoch accel clock, delay+`t_cpa`, muSeen accel parity, `capsuleTravelBudgetUu`) unless fixing a clear regression.

No BASE×ZONE×VISION. No PN / mid-flight steering.

---

## 1) Critique of Pass-7 residual geometry

Pass-7 aligned tip / horizon / reach pads with Minkowski `R_hit = w/2 + R_c` via `capsuleTravelBudgetUu`. Residuals vs open-loop **finite-extent** engagement:

1. **Engagement clock is still zero-radius (center coincidence).**  
   `t_go = interceptTimeGo(...)` solves `|r + v t| = V_m t` — centers meet. Corridor lethality and Pass-7 travel already admit hits at separation `R_hit`. On the collision triangle, relative motion is collinear with `r + w t_0 = 0` and `|w| = R/t_0`, so center separation is `R(1 − t/t_0)`. First contact is at  
   \(t_\text{contact} = t_0\,(1 − R_\text{hit}/R)\)  
   (clamp when \(R \le R_\text{hit}\)). Lead / segment CPA / `t_eng` should use this extent clock; center `t_go` remains the right input for dodge lifetime and Pass-7 reach path length.

2. **Travel pad ≠ contact epoch.**  
   `L_eff = L + R_hit` answers “how far can the tip disk’s budget extend.” It does **not** advance the time at which a mid-range in-reach shot first enters the capsule. Pass-7 closed the pad inconsistency; the residual is the **time** domain.

3. **Do not replace the 1D corridor integral.**  
   Full 2D stadium CDF remains deferred. Do **not** undo `capsuleTravelBudgetUu` (Pass-7 KEEP). Do **not** touch aim/vision/strategy σ. Accel clock stays delay+`t_cpa` on CPA from the (possibly shortened) `t_eng`.

4. **Thin / zero-extent equivalence.**  
   `R_hit → 0` ⇒ `t_contact = t_0` bit-identical to Pass-7. Default mid-range shots with `V_m t_0 ≪ L_eff` keep `t_eng = t_contact` (ordinal class preserved; contact only shortens the clock slightly).

Do **not** re-open CPA vs abreast μ. Do **not** split body/reach pads (would regress Pass-7 horizon KEEP).

---

## 2) Exact TypeScript snippets (copy-paste ready)

### 2a) New helper (after `interceptTimeGo` / near capsule helpers)

```typescript
/**
 * First-contact time on the collision triangle with lethal radius R_hit.
 * Center intercept t0 from interceptTimeGo; collinear close ⇒ separation
 * R(1 − t/t0). Open-loop only — no PN.
 * arXiv:2604.17811 (miss → hit with finite extent);
 * arXiv:2403.14997 (t_go / engagement clock);
 * arXiv:2312.09562 (collision triangle).
 */
export function firstContactTimeGo(
  tGoCenterSec: number,
  rangeUu: number,
  hitRadiusUu: number,
): number {
  const t0 = Math.max(0, tGoCenterSec)
  const R = Math.max(1, rangeUu)
  const Rh = Math.max(0, hitRadiusUu)
  if (Rh < 1e-9) return t0
  if (R <= Rh) return Math.min(t0, 0.05)
  return Math.max(0.05, t0 * (1 - Rh / R))
}
```

### 2b) Patch inside `estimateXh` (engagement clock only)

Keep Pass-5…7 lead / CPA / accel / `L_eff` / reach structure. Only feed `t_eng` from first contact:

```typescript
  const tGoMis = interceptTimeGo(distRel, vMissile, vRadial, vPerp)
  const tGo = T_delay + tGoMis
  const Ltravel = input.missileMaxTravelUu ?? input.abilityRange
  const L_eff = capsuleTravelBudgetUu(Ltravel, width)
  const tContact = firstContactTimeGo(tGoMis, distRel, R_hit)
  const tEng = engagementHorizonSec(tContact, vMissile, L_eff) // was tGoMis
  const lamStar = requiredLeadAngle(tEng, distRel, vRadial, vPerp)
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
  // zemClock / muBias unchanged
  factors.push(
    `t_go:${tGo.toFixed(2)}s`,
    `t_contact:${tContact.toFixed(2)}s`,
    `t_eng:${tEng.toFixed(2)}s`,
    // ... existing t_cpa / t_delay / lead / R_hit / L_travel
  )
```

Reach gate — **still** center path + Pass-7 `R_hit` pad (do not switch reach onto `tContact`):

```typescript
    const reachOk = interceptInMissileRange(
      tGoMis, // center intercept path length
      vMissile,
      Ltravel,
      R_hit,
    )
```

`muSeen` branch — same contact clock:

```typescript
    const tS = interceptTimeGo(atS.rangeUu, vMissile, atS.vRadial, atS.vPerp)
    const tContactS = firstContactTimeGo(tS, atS.rangeUu, R_hit)
    const tEngS = engagementHorizonSec(tContactS, vMissile, L_eff)
```

Leave dodge / Weber on full center `tGoMis` (missile still exists until tip death / center TOF). Leave accel on delay+`t_cpa`. Leave `L_eff = capsuleTravelBudgetUu(...)`.

**Zero-extent equivalence:** `hitRadiusUu → 0` ⇒ `t_contact = t_go` ⇒ bit-identical to Pass-7 engagement wiring.

---

## 3) New invariant check(s) to ADD to eval (string form)

Import: `firstContactTimeGo` (plus existing `interceptTimeGo`, `engagementHorizonSec`, `estimateXh`).

```typescript
// --- geometry deepen (Pass-8 GEO) ---
{
  const t0 = interceptTimeGo(1000, 1600, 0, 200)
  assert(
    'Pass-8: zero extent → firstContact ≡ center t_go',
    Math.abs(firstContactTimeGo(t0, 1000, 0) - t0) < 1e-12,
  )
  const tC = firstContactTimeGo(t0, 1000, 135)
  assert(
    'Pass-8: R_hit > 0 → firstContact < center t_go',
    tC < t0 - 1e-9,
    `tC=${tC} t0=${t0}`,
  )
  assert(
    'Pass-8: firstContact = t0·(1 − R_hit/R)',
    Math.abs(tC - t0 * (1 - 135 / 1000)) < 1e-12,
  )
}
{
  assert(
    'Pass-8: overlapping range → immediate contact floor',
    firstContactTimeGo(1.0, 50, 65) <= 0.05 + 1e-12,
  )
}
{
  const L = 400
  const Vm = 1600
  const t0 = 1.5
  const tC = firstContactTimeGo(t0, 900, 135)
  const teCenter = engagementHorizonSec(t0, Vm, L)
  const teContact = engagementHorizonSec(tC, Vm, L)
  assert(
    'Pass-8: contact horizon ≤ center horizon',
    teContact <= teCenter + 1e-12,
    `contact=${teContact} center=${teCenter}`,
  )
}
{
  // A=0 mid-range: exposing t_contact must not flip in-range / destroy CPA factor.
  const def = estimateXh(
    base({
      leadSkill: 0.7,
      targetPerpVel: 200,
      dashReady: false,
      crowdControlled: true,
      residualAccelUuPerSec2: 0,
    }),
  )
  assert('Pass-8: default A=0 still in range', def.inRange === true)
  assert(
    'Pass-8: default path exposes t_contact',
    def.factors.some((f) => f.startsWith('t_contact:')),
    def.factors.join(','),
  )
  assert(
    'Pass-8: default path still exposes t_cpa',
    def.factors.some((f) => f.startsWith('t_cpa:')),
    def.factors.join(','),
  )
}
{
  // Wider capsule (larger R_hit) → weakly earlier contact clock (geo-only, A=0).
  const wide = estimateXh(
    base({
      missileWidth: 200,
      leadSkill: 0.55,
      targetPerpVel: 180,
      targetRadialVel: 0,
      dashReady: false,
      crowdControlled: true,
      residualAccelUuPerSec2: 0,
    }),
  )
  const thin = estimateXh(
    base({
      missileWidth: 40,
      leadSkill: 0.55,
      targetPerpVel: 180,
      targetRadialVel: 0,
      dashReady: false,
      crowdControlled: true,
      residualAccelUuPerSec2: 0,
    }),
  )
  const tcWide = Number(
    wide.factors.find((f) => f.startsWith('t_contact:'))?.slice(10, -1),
  )
  const tcThin = Number(
    thin.factors.find((f) => f.startsWith('t_contact:'))?.slice(10, -1),
  )
  if (Number.isFinite(tcWide) && Number.isFinite(tcThin)) {
    assert(
      'Pass-8: wider R_hit → t_contact ≤ thinner',
      tcWide <= tcThin + 1e-9,
      `wide=${tcWide} thin=${tcThin}`,
    )
  }
}
{
  // Pass-7 short-L reach_oor must survive (reach still on center t_go + R_hit).
  const tipOor = estimateXh(
    base({
      targetPosition: far,
      abilityRange: 1175,
      missileMaxTravelUu: 200,
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
    'Pass-8: short Ltravel still reach_oor under center-path reach',
    tipOor.inRange === false && tipOor.factors.includes('reach_oor'),
    `inRange=${tipOor.inRange} factors=${tipOor.factors.join(',')}`,
  )
}
```

Do **not** soften existing Pass-4…7 checks. Dodge/Weber still keyed off center `t_go` — do not add asserts that require dodge shrinkage.

---

## 4) Mental regression vs existing 158/158

| Check family | Risk | Why safe / watch |
|--------------|------|------------------|
| corridor\* / xHm / empirics | none | untouched |
| Pass-7 `capsuleTravelBudgetUu` / reach pad | none | helper + reach wiring unchanged |
| Pass-6 CPA / accel clock / muSeen | low | formulas unchanged; `t_eng` input may shorten slightly |
| Pass-5 horizon unit (explicit L) | none | helpers unchanged |
| Pass-5/7 short-L reach_oor | none | reach still center `t_go` + `R_hit` |
| point-blank / lead hi-lo / approach-flee | low | contact shortens `t_eng` weakly; perfect lead still μ≈0 on horizon |
| tip-binding A=0 ordinals | low | `L_eff` pad intact; contact ≤ center before tip clamp |
| aim / vision / strategy σ | none | dodge/Weber stay on center `tGoMis` |
| **new** width→earlier `t_contact` | n/a | intentional finite-extent consistency |

**Watch:** kits with large `missileWidth` (large `R_hit`) get a slightly earlier lead/CPA epoch (`×(1−R_hit/R)`). Zero extent ≡ Pass-7. Do not treat this as a license to revive slab×zone priors or PN.

---

## 5) arXiv ids cited

| id | Role |
|----|------|
| [2604.17811](https://arxiv.org/abs/2604.17811) | Miss → hit with finite extent (R_hit enters the **clock**, not only pad) |
| [2403.14997](https://arxiv.org/abs/2403.14997) | Engagement / t_go chain (contact vs center) |
| [2312.09562](https://arxiv.org/abs/2312.09562) | Collision-triangle collinear close ⇒ `t_contact = t_0(1 − R_hit/R)` |
| [2511.21633](https://arxiv.org/abs/2511.21633) | ZEM / CPA epoch (Pass-6 KEEP; untouched) |

No PN. No 2D corridor integral. Pass-7 Minkowski travel pad stays; this pass only folds `R_hit` into the **first-contact engagement clock** for lead/CPA/`t_eng`.

---

## 6) Verdict

**`KEEP_CANDIDATE`**

Minimal GEO deepen only: `firstContactTimeGo` so lead / segment CPA / `t_eng` use collision-triangle first contact at separation `R_hit`, while center `t_go` still drives dodge and Pass-7 reach. Zero extent ≡ Pass-7. Does not revive BASE×ZONE×VISION, does not add PN, does not re-propose Pass-1…7 travel/CPA/lead KEEP work.

KEEP_CANDIDATE
