# Pass-7 GEO — capsule Minkowski travel budget (R_hit tip pad)

**Axis:** geometry / kinematics (deepen Pass-6 residual only)  
**Verdict:** `KEEP_CANDIDATE`  
**Do not edit `src/engine/xh.ts` in this pass** (orchestrator applies). Snippets are copy-paste for the keeper apply.

Eval baseline at proposal time: **148/148** (`npm run eval:xh`). Do **not** re-propose Pass-1…6 KEEP work (`interceptTimeGo`, lead/heading, `interceptInMissileRange`, width/speed, `propagateLosFrame`, `ballisticRayMiss`/`ballisticSegmentMiss`/`ballisticSegmentCpa`, cast∧reach, `releaseDelaySec`, capsule `R_hit` / tip CPA, accel ZEM, `missileMaxTravelUu`, LOS collapse, `engagementHorizonSec`, lead/μ on `t_eng`, reach vs `Ltravel`, CPA-epoch accel clock, delay+`t_cpa`, muSeen accel parity) unless fixing a clear regression.

No BASE×ZONE×VISION. No PN / mid-flight steering.

---

## 1) Critique of Pass-6 residual geometry

Pass-6 aligned accel-ZEM to delay+CPA and restored muSeen parity. Residuals vs open-loop **capsule** engagement (segment ⊕ disk):

1. **Tip / horizon / reach still pad with champ radius only.**  
   Pass-4 defined `R_hit = capsuleHitRadius(w) = w/2 + R_c` as the Minkowski radius of the stadium and used Euclidean segment CPA for μ. But travel budget stays `L_eff = Ltravel + CHAMP_RADIUS`, and reach is `V_m t_go ≤ Ltravel + R_c`. Longitudinal tip contact of a capsule extends **`R_hit` past the centerline tip**, not merely `R_c`. Wide missiles are under-budgeted by `w/2` on tip lifetime and reach.

2. **Corridor lethality already uses full `R_hit`; kinematics do not.**  
   `corridorHitProb(R_hit, μ, σ)` admits hits out to the capsule radius, while `engagementHorizonSec` / segment clamp / reach die `w/2` early. That is an internal geometry inconsistency, not an aim/vision/σ issue.

3. **Do not replace the 1D corridor integral.**  
   Full 2D stadium CDF remains deferred (Pass-3/4). This pass only aligns the **travel pad** with the already-shipped capsule radius. Lead clock stays Pass-5 `t_eng`; CPA/accel clock stays Pass-6.

4. **Thin-missile equivalence.**  
   When `w → 0`, `R_hit → R_c` ⇒ `L_eff` and reach pad ≡ Pass-6. Mid-range in-reach shots with `V_m t_go ≪ L` keep `t_eng = t_go` (ordinal class preserved).

Do **not** re-open CPA vs abreast μ. Do **not** touch aim/vision/strategy σ. Do **not** change `accelZemClockSec` / `ballisticSegmentCpa` formulas.

---

## 2) Exact TypeScript snippets (copy-paste ready)

### 2a) New helper (after `capsuleHitRadius`)

```typescript
/**
 * Capsule (stadium) centerline travel budget: segment length L plus Minkowski
 * tip radius R_hit = w/2 + R_c. Open-loop tip contact / horizon / reach pad.
 * arXiv:2604.17811 (miss → hit with finite extent); Minkowski segment⊕disk.
 */
export function capsuleTravelBudgetUu(
  maxTravelUu: number,
  missileWidth: number,
  champRadius = CHAMP_RADIUS,
): number {
  return Math.max(1, maxTravelUu) + capsuleHitRadius(missileWidth, champRadius)
}
```

### 2b) Patch inside `estimateXh` (replace `L_eff` + reach pad only)

Keep Pass-5/6 lead / CPA / accel / muSeen structure. Only the travel pad changes:

```typescript
  const Ltravel = input.missileMaxTravelUu ?? input.abilityRange
  const L_eff = capsuleTravelBudgetUu(Ltravel, width) // was Ltravel + CHAMP_RADIUS
  const tEng = engagementHorizonSec(tGoMis, vMissile, L_eff)
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
  const zemClock = accelZemClockSec(T_delay, cpa.tCpaSec)
  const zemExtra = boundedAccelZemExtra(
    zemClock,
    input.residualAccelUuPerSec2 ?? 0,
  )
  const muBias = cpa.missUu + zemExtra
  // factors unchanged (still expose t_eng / t_cpa / L_travel)
```

Reach gate — pad with full capsule radius (4th arg overrides default champ-only):

```typescript
    const castOk = inCastRange(distance, input.abilityRange)
    const reachOk = interceptInMissileRange(
      tGoMis,
      vMissile,
      Ltravel,
      R_hit, // was default CHAMP_RADIUS
    )
    inRange = castOk && reachOk
```

`muSeen` already consumes `L_eff` — no further edit once `L_eff` uses the helper.

**Thin equivalence:** `missileWidth → 0` ⇒ `R_hit = R_c` ⇒ bit-identical to Pass-6 tip/reach pads.

Leave dodge on full `tGoMis`. Leave lead on `t_eng`. Leave accel on delay+`t_cpa`.

---

## 3) New invariant check(s) to ADD to eval (string form)

Import: `capsuleTravelBudgetUu`, `capsuleHitRadius` (plus existing horizon / CPA / `estimateXh`).

```typescript
// --- geometry deepen (Pass-7 GEO) ---
{
  assert(
    'Pass-7: capsule travel = L + R_hit',
    Math.abs(capsuleTravelBudgetUu(1000, 140) - (1000 + capsuleHitRadius(140))) <
      1e-12,
  )
  assert(
    'Pass-7: thin width → champ-only pad (Pass-6 equiv)',
    Math.abs(capsuleTravelBudgetUu(800, 0) - (800 + 65)) < 1e-12,
  )
  assert(
    'Pass-7: wider missile → strictly larger travel budget',
    capsuleTravelBudgetUu(800, 200) > capsuleTravelBudgetUu(800, 40) + 1e-9,
  )
}
{
  const L = 400
  const w = 120
  const budget = capsuleTravelBudgetUu(L, w)
  const teChamp = engagementHorizonSec(1.5, 1600, L + 65)
  const teCap = engagementHorizonSec(1.5, 1600, budget)
  assert(
    'Pass-7: capsule horizon ≥ champ-only horizon when tip binds',
    teCap >= teChamp - 1e-12,
    `cap=${teCap} champ=${teChamp}`,
  )
}
{
  // Near tip-binding: wider missile (larger L_eff) must not lower xH vs thin.
  const tipWide = estimateXh(
    base({
      targetPosition: far,
      abilityRange: 1175,
      missileMaxTravelUu: 520,
      missileSpeed: 1400,
      missileWidth: 200,
      leadSkill: 0.55,
      targetPerpVel: 180,
      targetRadialVel: 0,
      dashReady: false,
      crowdControlled: true,
      residualAccelUuPerSec2: 0,
    }),
  )
  const tipThin = estimateXh(
    base({
      targetPosition: far,
      abilityRange: 1175,
      missileMaxTravelUu: 520,
      missileSpeed: 1400,
      missileWidth: 40,
      leadSkill: 0.55,
      targetPerpVel: 180,
      targetRadialVel: 0,
      dashReady: false,
      crowdControlled: true,
      residualAccelUuPerSec2: 0,
    }),
  )
  if (tipWide.inRange && tipThin.inRange) {
    assert(
      'Pass-7: wider tip pad → xH ≥ thinner (A=0, tip-ish)',
      tipWide.xH >= tipThin.xH - 1e-6,
      `wide=${tipWide.xH.toFixed(3)} thin=${tipThin.xH.toFixed(3)}`,
    )
  }
}
{
  // Pass-5 short-L reach_oor must survive larger pad (still far beyond 200+R_hit).
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
    'Pass-7: short Ltravel still reach_oor under R_hit pad',
    tipOor.inRange === false && tipOor.factors.includes('reach_oor'),
    `inRange=${tipOor.inRange} factors=${tipOor.factors.join(',')}`,
  )
}
{
  const def = estimateXh(
    base({
      leadSkill: 0.7,
      targetPerpVel: 200,
      dashReady: false,
      crowdControlled: true,
      residualAccelUuPerSec2: 0,
    }),
  )
  assert('Pass-7: default A=0 still in range', def.inRange === true)
  assert(
    'Pass-7: default path still exposes t_cpa',
    def.factors.some((f) => f.startsWith('t_cpa:')),
    def.factors.join(','),
  )
}
```

Do **not** soften existing Pass-4…6 checks. Champ-only horizon unit tests that pass an explicit `L` (not via `estimateXh`) remain valid.

---

## 4) Mental regression vs existing 148/148

| Check family | Risk | Why safe / watch |
|--------------|------|------------------|
| corridor\* / xHm / empirics | none | untouched |
| Pass-6 CPA / accel clock / muSeen | none | formulas unchanged; only `L_eff` pad |
| Pass-5 horizon unit (explicit L) | none | helpers unchanged |
| Pass-5 short-L reach_oor | low | 200+R_hit still ≪ far intercept path |
| point-blank / lead hi-lo / approach-flee | none | mid-range `t_eng=t_go` when L covers |
| tip-binding A=0 ordinals | low | wider ⇒ weakly longer horizon ⇒ ≤ miss / ≥ xH |
| aim / vision / strategy σ | none | no σ edits |
| **new** width→travel monotone | n/a | intentional Minkowski consistency |

**Watch:** kits with large `missileWidth` near tip-binding gain a small reach/horizon boost (`+w/2`). Thin `w→0` ≡ Pass-6. Do not treat this as a license to revive slab×zone priors.

---

## 5) arXiv ids cited

| id | Role |
|----|------|
| [2604.17811](https://arxiv.org/abs/2604.17811) | Miss → hit with finite extent (capsule radius already in `R_hit`) |
| [2403.14997](https://arxiv.org/abs/2403.14997) | Engagement / tip lifetime clock (pad only; lead still `t_eng`) |
| [2312.09562](https://arxiv.org/abs/2312.09562) | Collision-triangle framing (unchanged) |
| [2511.21633](https://arxiv.org/abs/2511.21633) | ZEM / CPA epoch (Pass-6 KEEP; untouched) |

No PN. No 2D corridor integral. Pass-5 lead horizon and Pass-6 CPA accel clock stay; this pass only completes the **Minkowski tip pad** `L + R_hit`.

---

## 6) Verdict

**`KEEP_CANDIDATE`**

Minimal GEO deepen only: `capsuleTravelBudgetUu` so tip clamp / `t_eng` / reach use `L + R_hit` instead of `L + R_c`, matching Pass-4’s capsule radius. Thin width ≡ Pass-6. Does not revive BASE×ZONE×VISION, does not add PN, does not re-propose Pass-1…6 CPA/lead/accel KEEP work.

KEEP_CANDIDATE
