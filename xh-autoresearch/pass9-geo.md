# Pass-9 GEO — CPA first-contact accel epoch + muSeen contact parity

**Axis:** geometry / kinematics (deepen Pass-8 residual only)  
**Verdict:** `KEEP_CANDIDATE`  
**Do not edit `src/engine/xh.ts` in this pass** (orchestrator applies). Snippets are copy-paste for the keeper apply.

Eval baseline at proposal time: **195/195** (`npm run eval:xh`). Do **not** re-propose Pass-1…8 KEEP work (`interceptTimeGo`, lead/heading, `interceptInMissileRange`, width/speed, `propagateLosFrame`, `ballisticRayMiss`/`ballisticSegmentMiss`/`ballisticSegmentCpa`, cast∧reach, `releaseDelaySec`, capsule `R_hit` / tip CPA, accel ZEM, `missileMaxTravelUu`, LOS collapse, `engagementHorizonSec`, lead/μ on `t_eng`, reach vs `Ltravel`, CPA-epoch accel clock, delay+`t_cpa`, `capsuleTravelBudgetUu`, `firstContactTimeGo` / center `t_go` for dodge/reach) unless fixing a clear regression.

No BASE×ZONE×VISION. No PN / mid-flight steering. Do **not** set `T_avail = t_go`.

---

## 1) Critique of Pass-8 residual geometry

Pass-8 folded Minkowski `R_hit` into the **engagement clock** via collision-triangle `firstContactTimeGo` → `t_eng` for lead / segment CPA. Center `t_go` still drives dodge lifetime and Pass-7 reach. Residuals vs open-loop **finite-extent** ballistic corridor:

1. **`muSeen` never got the contact clock (Pass-8 apply gap).**  
   Main path and belief-hypothesis arms use `tContact = firstContactTimeGo(...)` then `engagementHorizonSec(tContact, ...)`. Soft-vision `beliefMeanSeen` still does `engagementHorizonSec(tS, ...)` on **center** `tS`. Penumbra lead/CPA/accel therefore disagree with the lost/hyp arms under the same `R_hit` — a parity hole, not new physics.

2. **Accel ZEM still integrates to center CPA, not lethal first contact.**  
   Pass-6 keyed `boundedAccelZemExtra` to delay+`t_cpa` where `t_cpa` is Euclidean **center** closest approach. When the open-loop path penetrates the capsule (`missUu < R_hit`), first contact is the earlier root of `|p(t)| = R_hit` along relative motion `p(t) = (R + w_x t,\, w_y t)`. Accel residual that can still reshape miss **before** the disk is entered should stop at that contact epoch — same finite-extent philosophy as Pass-8’s `t_contact`, now on the CPA/accel axis. μ stays center `missUu` for the 1D corridor (do **not** replace `corridorHitProb`).

3. **Do not replace the 1D corridor integral.**  
   Full 2D stadium CDF remains deferred. Do **not** undo `firstContactTimeGo` / `capsuleTravelBudgetUu`. Do **not** re-open triangle vs general `|r+vt|=0` for `t_eng`. Do **not** touch aim/vision/strategy σ. Dodge/Weber stay on center `tGoMis`.

4. **Thin / zero-extent / A=0 equivalence.**  
   `R_hit → 0` ⇒ first-contact CPA root ≡ center coincidence when attainable, else `t_cpa` ⇒ accel clock ≡ Pass-8. `A → 0` ⇒ `zemExtra = 0` regardless of clock (default kit μ bit-identical aside from the muSeen contact-parity fix under softV∈(0,1)).

Do **not** set engagement `t_eng = t_go` center again. Do **not** feed contact into reach/dodge.

---

## 2) Exact TypeScript snippets (copy-paste ready)

### 2a) New helper (after `ballisticSegmentCpa` / near `accelZemClockSec`)

```typescript
/**
 * Earliest open-loop time in [0, tCpa] at which center separation ≤ R_hit
 * along relative motion p(t)=(R+w_x t, w_y t) vs ballistic aim ray.
 * If the path never enters the lethal disk, returns tCpa (center CPA).
 * Accel-ZEM uses this contact epoch; corridor μ still uses center missUu.
 * Open-loop only — no PN.
 * arXiv:2604.17811 (miss → hit with finite extent);
 * arXiv:2511.21633 (ZEM at engagement/contact epoch);
 * arXiv:2312.09562 (collision geometry / relative quadratic).
 */
export function ballisticFirstContactSec(
  rangeUu: number,
  vRadial: number,
  vPerp: number,
  missileSpeed: number,
  aimAngleRad: number,
  tCpaSec: number,
  hitRadiusUu: number,
): number {
  const tCpa = Math.max(0, tCpaSec)
  const Rh = Math.max(0, hitRadiusUu)
  if (Rh < 1e-9) return tCpa
  const Vm = Math.max(200, missileSpeed)
  const R = Math.max(1, rangeUu)
  if (R <= Rh) return Math.min(tCpa, 0.05)
  const c = Math.cos(aimAngleRad)
  const s = Math.sin(aimAngleRad)
  const wx = vRadial - Vm * c
  const wy = vPerp - Vm * s
  const A = wx * wx + wy * wy
  const B = 2 * R * wx
  const C = R * R - Rh * Rh
  if (A < 1e-12) {
    // Near-collinear / tiny |w|: 1D roots of (R + w_x t)² = R_hit².
    if (Math.abs(wx) < 1e-12) return tCpa
    const tA = (-R + Rh) / wx
    const tB = (-R - Rh) / wx
    const hits = [tA, tB].filter((t) => t >= -1e-9 && t <= tCpa + 1e-9)
    if (!hits.length) return tCpa
    return Math.max(0, Math.min(...hits))
  }
  const disc = B * B - 4 * A * C
  if (disc < 0) return tCpa
  const sdisc = Math.sqrt(disc)
  const t1 = (-B - sdisc) / (2 * A)
  const t2 = (-B + sdisc) / (2 * A)
  const hits = [t1, t2].filter((t) => t >= -1e-9 && t <= tCpa + 1e-9)
  if (!hits.length) return tCpa
  return Math.max(0, Math.min(...hits))
}
```

### 2b) Patch inside `estimateXh` — main path accel clock

Keep Pass-5…8 lead / `t_eng` / `L_eff` / center `t_cpa` factors. Only feed accel from first contact:

```typescript
  const cpa = ballisticSegmentCpa(
    distRel,
    vRadial,
    vPerp,
    vMissile,
    lamAim,
    tEng,
    L_eff,
  )
  const tHit = ballisticFirstContactSec(
    distRel,
    vRadial,
    vPerp,
    vMissile,
    lamAim,
    cpa.tCpaSec,
    R_hit,
  )
  const zemClock = accelZemClockSec(T_delay, tHit) // was cpa.tCpaSec
  const zemExtra = boundedAccelZemExtra(
    zemClock,
    input.residualAccelUuPerSec2 ?? 0,
  )
  const muBias = cpa.missUu + zemExtra
  factors.push(
    `t_go:${tGo.toFixed(2)}s`,
    `t_contact:${tContact.toFixed(2)}s`,
    `t_eng:${tEng.toFixed(2)}s`,
    `t_cpa:${cpa.tCpaSec.toFixed(2)}s`,
    `t_hit:${tHit.toFixed(2)}s`,
    `t_delay:${T_delay.toFixed(2)}s`,
    // ... existing lead / R_hit / L_travel
  )
```

### 2c) `muSeen` — Pass-8 contact parity + Pass-9 hit clock

```typescript
    const tS = interceptTimeGo(atS.rangeUu, vMissile, atS.vRadial, atS.vPerp)
    const tContactS = firstContactTimeGo(tS, atS.rangeUu, R_hit)
    const tEngS = engagementHorizonSec(tContactS, vMissile, L_eff) // was tS
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
    const tHitS = ballisticFirstContactSec(
      atS.rangeUu,
      atS.vRadial,
      atS.vPerp,
      vMissile,
      lamS * leadSkill,
      cpaS.tCpaSec,
      R_hit,
    )
    const zemS = boundedAccelZemExtra(
      accelZemClockSec(T_delay, tHitS),
      input.residualAccelUuPerSec2 ?? 0,
    )
    muSeen = cpaS.missUu + zemS
```

### 2d) Hypothesis arms — same accel hit clock

```typescript
        const tContactH = firstContactTimeGo(tH, atH.rangeUu, R_hit)
        const tEngH = engagementHorizonSec(tContactH, vMissile, L_eff)
        const lamH = requiredLeadAngle(
          tEngH,
          atH.rangeUu,
          atH.vRadial,
          atH.vPerp,
        )
        const aimH = lamH * leadSkill
        const cpaH = ballisticSegmentCpa(
          atH.rangeUu,
          atH.vRadial,
          atH.vPerp,
          vMissile,
          aimH,
          tEngH,
          L_eff,
        )
        const tHitH = ballisticFirstContactSec(
          atH.rangeUu,
          atH.vRadial,
          atH.vPerp,
          vMissile,
          aimH,
          cpaH.tCpaSec,
          R_hit,
        )
        const zemH = boundedAccelZemExtra(
          accelZemClockSec(T_delay, tHitH),
          input.residualAccelUuPerSec2 ?? 0,
        )
```

Leave dodge / Weber on full center `tGoMis`. Leave reach on center `tGoMis` + Pass-7 `R_hit`. Leave `L_eff = capsuleTravelBudgetUu(...)`. Leave `t_eng` on Pass-8 `t_contact`.

**Zero-extent equivalence:** `hitRadiusUu → 0` ⇒ `t_hit = t_cpa` ⇒ accel ≡ Pass-8. **A=0:** `zemExtra = 0` on all arms.

---

## 3) New invariant check(s) to ADD to eval (string form)

Import: `ballisticFirstContactSec`, `ballisticSegmentCpa` (plus existing `firstContactTimeGo`, `interceptTimeGo`, `estimateXh`).

```typescript
// --- geometry deepen (Pass-9 GEO) ---
{
  // Zero extent → first-contact CPA epoch ≡ center t_cpa
  const cpa = ballisticSegmentCpa(1000, 0, 200, 1600, 0.05, 2.0, 2000)
  assert(
    'Pass-9: zero extent → t_hit ≡ t_cpa',
    Math.abs(
      ballisticFirstContactSec(1000, 0, 200, 1600, 0.05, cpa.tCpaSec, 0) -
        cpa.tCpaSec,
    ) < 1e-12,
  )
}
{
  // Penetrating path (near-perfect lead, wide R_hit): t_hit ≤ t_cpa
  const Vm = 1600
  const R = 900
  const vPerp = 0
  const vRad = 0
  const t0 = interceptTimeGo(R, Vm, vRad, vPerp)
  const lam = requiredLeadAngle(t0, R, vRad, vPerp) // ~0
  const cpa = ballisticSegmentCpa(R, vRad, vPerp, Vm, lam, t0, 2000)
  const Rh = 135
  const tHit = ballisticFirstContactSec(R, vRad, vPerp, Vm, lam, cpa.tCpaSec, Rh)
  assert(
    'Pass-9: penetrating aim → t_hit ≤ t_cpa',
    tHit <= cpa.tCpaSec + 1e-12,
    `tHit=${tHit} tCpa=${cpa.tCpaSec} miss=${cpa.missUu}`,
  )
  assert(
    'Pass-9: penetrating aim → t_hit < t_cpa when miss < R_hit',
    cpa.missUu >= Rh - 1e-6 || tHit < cpa.tCpaSec - 1e-9,
    `miss=${cpa.missUu} Rh=${Rh} tHit=${tHit} tCpa=${cpa.tCpaSec}`,
  )
}
{
  // Miss outside disk → t_hit stays at center CPA
  const cpa = ballisticSegmentCpa(1000, 0, 400, 1600, 0, 2.0, 2000)
  const Rh = 40
  const tHit = ballisticFirstContactSec(
    1000,
    0,
    400,
    1600,
    0,
    cpa.tCpaSec,
    Rh,
  )
  assert(
    'Pass-9: miss ≥ R_hit → t_hit ≡ t_cpa',
    cpa.missUu + 1e-6 < Rh || Math.abs(tHit - cpa.tCpaSec) < 1e-12,
    `miss=${cpa.missUu} tHit=${tHit} tCpa=${cpa.tCpaSec}`,
  )
}
{
  // A=0 default: still in-range; expose t_hit; t_cpa retained
  const def = estimateXh(
    base({
      leadSkill: 0.7,
      targetPerpVel: 200,
      dashReady: false,
      crowdControlled: true,
      residualAccelUuPerSec2: 0,
    }),
  )
  assert('Pass-9: default A=0 still in range', def.inRange === true)
  assert(
    'Pass-9: default path exposes t_hit',
    def.factors.some((f) => f.startsWith('t_hit:')),
    def.factors.join(','),
  )
  assert(
    'Pass-9: default path still exposes t_cpa',
    def.factors.some((f) => f.startsWith('t_cpa:')),
    def.factors.join(','),
  )
  assert(
    'Pass-9: default path still exposes t_contact',
    def.factors.some((f) => f.startsWith('t_contact:')),
    def.factors.join(','),
  )
  const tHit = Number(def.factors.find((f) => f.startsWith('t_hit:'))?.slice(6, -1))
  const tCpa = Number(def.factors.find((f) => f.startsWith('t_cpa:'))?.slice(6, -1))
  if (Number.isFinite(tHit) && Number.isFinite(tCpa)) {
    assert(
      'Pass-9: t_hit ≤ t_cpa on default path',
      tHit <= tCpa + 1e-9,
      `tHit=${tHit} tCpa=${tCpa}`,
    )
  }
}
{
  // A>0: wider R_hit → weakly earlier accel contact clock (geo-only)
  const wide = estimateXh(
    base({
      missileWidth: 200,
      leadSkill: 0.85,
      targetPerpVel: 0,
      targetRadialVel: 0,
      dashReady: false,
      crowdControlled: true,
      residualAccelUuPerSec2: 400,
    }),
  )
  const thin = estimateXh(
    base({
      missileWidth: 40,
      leadSkill: 0.85,
      targetPerpVel: 0,
      targetRadialVel: 0,
      dashReady: false,
      crowdControlled: true,
      residualAccelUuPerSec2: 400,
    }),
  )
  const thWide = Number(
    wide.factors.find((f) => f.startsWith('t_hit:'))?.slice(6, -1),
  )
  const thThin = Number(
    thin.factors.find((f) => f.startsWith('t_hit:'))?.slice(6, -1),
  )
  if (Number.isFinite(thWide) && Number.isFinite(thThin)) {
    assert(
      'Pass-9: wider R_hit → t_hit ≤ thinner (A>0 path)',
      thWide <= thThin + 1e-9,
      `wide=${thWide} thin=${thThin}`,
    )
  }
}
{
  // Pass-8 short-L reach_oor must survive (reach still center t_go + R_hit)
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
    'Pass-9: short Ltravel still reach_oor under center-path reach',
    tipOor.inRange === false && tipOor.factors.includes('reach_oor'),
    `inRange=${tipOor.inRange} factors=${tipOor.factors.join(',')}`,
  )
}
{
  // muSeen soft-vision path must use contact clock (parity with main/hyp)
  // When softV∈(0,1) + beliefMeanSeen, factors still expose t_contact from main;
  // assert helper firstContact wiring does not regress center≡zero-extent.
  const t0 = interceptTimeGo(1000, 1600, 0, 200)
  assert(
    'Pass-9: muSeen parity helper — zero extent firstContact ≡ t0',
    Math.abs(firstContactTimeGo(t0, 1000, 0) - t0) < 1e-12,
  )
  assert(
    'Pass-9: muSeen parity helper — R_hit shortens contact',
    firstContactTimeGo(t0, 1000, 135) < t0 - 1e-9,
  )
}
```

Do **not** soften existing Pass-4…8 checks. Do not assert dodge shrinkage. Do not require `t_hit` on OOR early-return paths that never build accel factors beyond the existing early factor list (OOR returns before `t_hit` — the reach_oor case above only checks `reach_oor`).

**Orchestrator note:** Main in-range path must push `t_hit:` (snippet 2b). OOR early return currently pushes `t_contact`/`t_cpa` from the pre-gate factor block — after 2b, OOR will also include `t_hit` if factors are built before the gate (same as today’s `t_cpa`). That is fine; do not special-case.

---

## 4) Mental regression vs existing 195/195

| Check family | Risk | Why safe / watch |
|--------------|------|------------------|
| corridor\* / xHm / empirics | none | untouched |
| Pass-7 travel pad / reach | none | reach still center `t_go` + `R_hit` |
| Pass-8 `firstContactTimeGo` / `t_eng` | none | lead horizon unchanged |
| Pass-6 CPA missUu / `t_cpa` factor | none | center CPA still computed + exposed |
| aim / vision / strategy σ | none | dodge/Weber on center `tGoMis` |
| A=0 default μ | none | `zemExtra=0`; clocks unused for μ |
| A>0 μ | low | earlier `t_hit` weakly shrinks accel extra when penetrating |
| softV muSeen | low | intentional Pass-8 contact parity |
| **new** width→earlier `t_hit` | n/a | finite-extent accel consistency |

**Watch:** kits with large `missileWidth` and `A>0` get a slightly smaller accel-ZEM when the ray penetrates early. Zero extent ≡ Pass-8 accel. Do not revive slab×zone priors or PN.

---

## 5) arXiv ids cited

| id | Role |
|----|------|
| [2604.17811](https://arxiv.org/abs/2604.17811) | Miss → hit with finite extent (`R_hit` on CPA **contact** epoch) |
| [2511.21633](https://arxiv.org/abs/2511.21633) | ZEM bound at engagement/contact epoch (deepen Pass-6 center CPA) |
| [2312.09562](https://arxiv.org/abs/2312.09562) | Relative-motion quadratic for `|p(t)|=R_hit` |
| [2403.14997](https://arxiv.org/abs/2403.14997) | Engagement clock chain (Pass-8 `t_contact` kept; this pass is CPA-side) |

No PN. No 2D corridor integral. Pass-8 triangle `t_eng` stays; this pass only (1) closes `muSeen` contact parity and (2) keys accel ZEM to ballistic first-contact ≤ center `t_cpa`.

---

## 6) Verdict

**`KEEP_CANDIDATE`**

Minimal GEO deepen: `ballisticFirstContactSec` so accel-ZEM uses lethal first contact along the open-loop ray when `miss < R_hit`, plus wire `muSeen` through Pass-8 `firstContactTimeGo` (parity with main/hyp). Center `t_cpa` / `t_go` / reach / dodge unchanged. Zero extent ≡ Pass-8 accel. Does not revive BASE×ZONE×VISION, does not add PN, does not set `T_avail=t_go`, does not re-propose Pass-1…8 travel/CPA/lead KEEP work.

KEEP_CANDIDATE
