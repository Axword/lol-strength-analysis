# Pass-5 VISION — complete no_lkp · σ_occ asymptote · ward/margin plumbing

**Axis:** vision  
**Agent:** Pass-5 VISION  
**Against:** Post Pass-4 KEEP (`math_pass_rate=103/103`) — softVision mix, spotted τ, √t/Flash/brush, softV→σ_seen, occupancy slow-growth (`aEff`), `beliefMeanSeen` multi-mean, `belief:no_lkp_guard` **factor**  
**Constraint honored:** **no edits** to `xh.ts` / `vision.ts` / combat / eval. Proposal only.  
**Do not re-propose:** LKP geo mean API, κ=1/√3, softVisionAt / resolveCastVisionSoft shell, mixture-of-CDFs, spotted τ sign, √t / Flash-belief / brush cap, softV→σ_seen exponential, `beliefMeanSeen` binary multi-mean, `aEff` slow-growth, tagging `belief:no_lkp_guard` alone.  
**Verdict:** **KEEP_CANDIDATE**

---

## 0. What Pass-1–4 fixed vs what remains

| Landed claim | Status @ Pass-5 |
|---|---|
| Reachable-set `σ_belief` + √t + Flash + brush | **Shipped** in `sigmaBeliefLkp` |
| SoftVision mixture-of-CDFs ∫L b | **Shipped**; equal-mean unless `beliefMeanSeen` set |
| `beliefMeanSeen` → distinct `μ_s` | **Shipped** (optional path) |
| Occupancy **slow-growth** `aEff = T_SAT + 0.2(a−T_SAT)` | **Shipped**; still **no** zone `σ_occ` asymptote |
| `belief:no_lkp_guard` factor | **Shipped**; **μ / range still god-eye** when LKP unset |
| Overlay passes `wards`; combat omits | **Unchanged** — combat `resolveCastVisionSoft` has no `wards` |
| `softVisionAt` margin → σ_seen | **Unshipped** — margin discarded; σ_seen from softV only |

Program residual (Pass-5 deepen **σ_belief / soft vision only**):

1. **Complete god-eye guard** — factor without behavior change still violates program hard rule.  
2. **σ_occ asymptote** — slow-growth ≠ saturation to zone occupancy prior.  
3. **Combat ward plumbing** (+ optional margin→σ_seen).  
4. Optional: `beliefHypotheses[]` for occupancy modes once σ_occ saturates.

No BASE×ZONE×VISION. Zone scale on aim/juke may stay.

---

## 1. Critique (concrete residuals)

### 1.1 no_lkp factor without mean discipline (P0 — program hard rule)

```593:603:src/engine/xh.ts
  const fowDark = softV < 0.85 || vision === 'blind'
  const hasBelief = !!input.beliefMeanPosition
  // FoW geometry: aim/range from belief mean when dark enough and LKP provided.
  const geoPos =
    fowDark && hasBelief
      ? input.beliefMeanPosition
      : input.targetPosition
  ...
  if (fowDark && !hasBelief) factors.push('belief:no_lkp_guard')
```

Hard rule: *Blind casts must not treat true position as known without belief spread.*

Pass-4 tagged the failure mode but left the math god-eye: when callers omit `beliefMeanPosition` (combat + overlay always do), FoW still locks **distance / `t_go` / `muBias` / in-range** to oracle `targetPosition`, then smears with `σ_lost`. Tag ≠ posterior. Eval `belief-aim off LKP` only tests *with* LKP; `onTruth` blind fixtures still *are* the silent god-eye path.

### 1.2 Occupancy slow-growth ≠ σ_occ asymptote (P0 residual)

```828:838:src/engine/xh.ts
    const T_SAT = 8
    const aEff = a <= T_SAT ? a : T_SAT + 0.2 * (a - T_SAT)
    let Rmax = ms * aEff + dash + flash
    ...
    const sigSqrt = 55 * Math.sqrt(aEff)
    let sig = Math.hypot(35, kappa * Rmax, sigSqrt)
```

`aEff` slows ballistic runaway but ancient support still grows without bound (\(0.2\,v\Delta t\)). Lost-contact priors in FoW literature saturate toward a **zone occupancy** kernel:

\[
\sigma_\ell(\Delta t)\xrightarrow{\Delta t\to\infty}\sigma_{\mathrm{occ}}(\mathrm{zone})\ll v\cdot 30.
\]

Pass-4 proposed `sat(reach, σ_occ, Δt/T_sat)`; KEEP landed only the slow-growth half. Residual: expose `sigma.belief` monotone mid→ancient with hard ceiling near `σ_occ(zone)`.

### 1.3 Combat still omits wards (P1 — prefer plumbing)

```203:209:src/engine/combat.ts
        ? resolveCastVisionSoft({
            casterPosition: caster.position,
            targetPosition: enemy.position,
            casterTeam,
            targetTeam: casterTeam === 'blue' ? 'red' : 'blue',
            units: visionUnits,
          })
```

`MatchupInput` has no `wards` / terrain. Overlay threads wards; fight math is champ-disk-only softVision. Same second of game → two FoW contracts. Prefer plumbing over inventing a combat-only softVision scalar.

### 1.4 softV→σ_seen still ignores sensor margin (P1)

```853:853:src/engine/xh.ts
  const sigmaSeen = Math.hypot(18, 55 * Math.exp(-2.8 * softV))
```

`softVisionAt` already computes Koopman margins per champ/ward sensor, then collapses to `v∈[0,1]`. Penumbra σ_meas should track **best margin / r_sensor**, not only the logistic. Deepen once return type carries `bestMarginNorm`.

### 1.5 Multi-mean binary only (P2)

`beliefMeanSeen` enables two-component means; no weighted exit/occupancy hypotheses. After σ_occ saturation, split mass into 2–3 zone modes via optional `beliefHypotheses[]` (Pass-4 sketch) — only if bandwidth remains after P0/P1.

---

## 2. Proposed minimal deepen (orchestrator → later)

**Scope:** complete no_lkp behavior + σ_occ asymptote + combat wards (+ optional margin). No BASE×ZONE×VISION. Do not re-litigate Pass-1–4 KEEP shape.

### 2.1 Complete god-eye guard (behavior)

```ts
const fowDark = softV < 0.85 || vision === 'blind'
const hasBelief =
  !!input.beliefMeanPosition || !!(input.beliefHypotheses?.length)

let geoPos = input.targetPosition
let openLoopBelief = false
if (fowDark && hasBelief) {
  geoPos = input.beliefMeanPosition ?? dominantHypothesisMean(input.beliefHypotheses!)
} else if (fowDark && !hasBelief) {
  factors.push('belief:no_lkp_guard')
  openLoopBelief = true
  // Do NOT lock μ / distance to oracle.
  // Option A (minimal, eval-safe): treat pose as unknown —
  //   distance = abilityRange * 0.55 (existing null-geo fallback band),
  //   muBias ← isotropic open-loop (leadSkill→0 path or |v_perp| t_go),
  //   force σ_lost ≥ σ_occ(zoneAt(caster) or 'unknown').
  // Option B: require callers to set beliefMeanPosition; if missing under FoW,
  //   geoPos = undefined → same null-geo path + σ_occ floor.
}
// Explicit beliefMeanPosition === targetPosition remains the “I believe the truth” test contract.
```

**Eval-safe contract:** fixtures that intend oracle+age must set `beliefMeanPosition: targetPosition`. Default blind-without-LKP must **differ** from that path (ΔxH or factor **and** non-oracle μ).

### 2.2 Zone occupancy asymptote in `sigmaBeliefLkp`

```ts
function occupancySigma(zone: MapZone): number {
  switch (zone) {
    case 'brush': return 280
    case 'pit': return 300
    case 'river': return 380
    case 'jungle': return 420
    case 'base': return 240
    case 'lane': return 520
    default: return 480
  }
}

function sigmaBeliefLkp(opts: {
  ageSec: number
  dashBudgetUu: number
  flashBudgetUu?: number
  brushCapUu?: number
  zone?: MapZone
}): number {
  // Keep existing √t + dash/Flash + brush Cap + aEff slow-growth — do not re-litigate.
  const reach = /* current path with aEff */
  const sigmaOcc = occupancySigma(opts.zone ?? 'unknown')
  const T_SAT = 8
  const u = Math.min(1, Math.max(0, opts.ageSec) / T_SAT)
  // Once reach exceeds occ, blend toward occ (asymptote), not keep growing via aEff alone.
  if (reach <= sigmaOcc) return reach
  return reach * (1 - u) + sigmaOcc * u
}
```

Preserve: `age=1` σ < `age=4` σ (walk dominates pre-\(T_{\mathrm{sat}}\)); `age=30` σ ≲ σ_occ + tol.

### 2.3 Combat wards + MatchupInput plumbing

```ts
// types.ts — additive
// MatchupInput.wards?: VisionWard[]
// MatchupInput.terrain?: TerrainMeta | null

// combat meanXhVsEnemies — thread wards when available
resolveCastVisionSoft({
  ...,
  wards: input.wards ?? [],
  meta: input.terrain,
})
```

First KEEP can ship combat `wards` alone; margin API additive.

### 2.4 Optional margin→σ_seen

```ts
// vision.ts
export function softVisionAt(...): { v: number; bestMarginNorm: number }
// σ_seen = hypot(18, σ0 * exp(-β * max(0, bestMarginNorm))) when margin present
// else keep softV exponential (Pass-3 KEEP)
```

### 2.5 Optional `beliefHypotheses` (only after 2.1–2.2)

Reuse Pass-4 sketch: weighted `{weight, mean, ageSec?, sigmaBelief?}[]` → Σ w_k Φ_corr. Prefer when σ_occ saturation wants brush-exit vs river modes; not required for Pass-5 KEEP if P0/P1 land first.

---

## 3. New eval asserts (additive — do not soften 103)

```ts
// V16b: god-eye guard *behavior* — FoW without LKP ≠ explicit-truth LKP
const oracleAim = estimateXh(base({
  vision: 'blind', lastKnownAgeSec: 2, softVision: 0,
  beliefMeanPosition: near, // explicit: “I believe the truth”
}))
const noLkp = estimateXh(base({
  vision: 'blind', lastKnownAgeSec: 2, softVision: 0,
  // beliefMeanPosition unset → guard path
}))
assert(
  'no-LKP FoW ≠ silent god-eye',
  Math.abs(noLkp.xH - oracleAim.xH) > 0.02
    || (noLkp.factors.includes('belief:no_lkp_guard')
        && (noLkp.distance == null
            || Math.abs((noLkp.distance ?? 0) - (oracleAim.distance ?? 0)) > 1)),
)

// V15b: occupancy asymptote — ancient σ_belief ≲ σ_occ (not aEff runaway)
const a4 = estimateXh(base({
  vision: 'blind', lastKnownAgeSec: 4, beliefMeanPosition: near, softVision: 0,
}))
const a30 = estimateXh(base({
  vision: 'blind', lastKnownAgeSec: 30, beliefMeanPosition: near, softVision: 0,
}))
assert('ancient xH ≤ mid-age xH', a30.xH <= a4.xH + 1e-9)
assert(
  'ancient belief ≲ σ_occ',
  !!a30.sigma && a30.sigma.belief <= 520 + 40, // lane/unknown occ + tol
  `σb=${a30.sigma?.belief.toFixed(0)}`,
)

// V13 already enabled by beliefMeanSeen — append if missing:
const equal = estimateXh(base({
  vision: 'blind', softVision: 0.5, lastKnownAgeSec: 2,
  beliefMeanPosition: near,
}))
const split = estimateXh(base({
  vision: 'blind', softVision: 0.5, lastKnownAgeSec: 2,
  beliefMeanPosition: near,
  beliefMeanSeen: { x: near.x + 0.05, y: near.y },
}))
assert('multi-mean split ≤ equal-mean', split.xH <= equal.xH + 1e-9)

// V17: softVisionAt ward edge > no-ward (vision unit); combat must pass wards

// Preserve: stale<fresh, belief-aim off LKP, softVision edge>dark, ancient finite,
// spotted≤unspotted, ambush≥mutual, no BASE×ZONE×VISION.
```

Update existing blind fixtures that relied on implicit oracle mean to set `beliefMeanPosition: targetPosition` so Pass-1–4 ordering stays green after 2.1.

---

## 4. arXiv / cites (Pass-5 focus)

| ID | Use |
|---|---|
| [2602.11373](https://arxiv.org/abs/2602.11373) | Full posterior; no oracle mean under FoW |
| [2604.17811](https://arxiv.org/abs/2604.17811) | ∫L b — distinct means already partial; guard completes open-loop |
| [2306.11301](https://arxiv.org/abs/2306.11301) | Reachable sets → occupancy / search priors |
| [1812.00054](https://arxiv.org/abs/1812.00054) | FoW state estimation; prior saturation |
| [2410.13587](https://arxiv.org/abs/2410.13587) | Sensor margin → measurement noise |
| Koopman 1956 | Soft detection; ward margin ↔ σ_meas |

---

## 5. Expected metric impact

| Change | Current 103 | After asserts |
|---|---|---|
| Complete no_lkp | May change default blind-without-LKP | Fixture LKP annotations; enables V16b |
| σ_occ asymptote | Ancient σ may drop vs aEff-only | Enables V15b; keep ancient finite |
| Combat wards | Product-only | V17 optional |
| Margin→σ_seen | Additive soft API | Optional |
| Legacy equal-mean + explicit LKP | Keep ordering | Stay 103/103 then 103+k/103+k |

**Primary score:** expect stay `103/103` after fixture LKP annotations; then `103+k/103+k` with V16b/V15b/(V13).

---

## 6. Minimal patch plan (orchestrator)

1. **Complete god-eye guard** — FoW without belief must not aim/range oracle; annotate eval fixtures with explicit LKP.  
2. **σ_occ asymptote** on top of existing `aEff` (zone table + blend after reach>occ).  
3. Thread **`wards` (+ terrain)** into combat `resolveCastVisionSoft` / `MatchupInput`.  
4. Optional: `softVisionAt` → `{ v, bestMarginNorm }` for σ_seen; `beliefHypotheses[]`.  
5. Append V16b, V15b, V13 (if missing), V17 to `eval-xh-math.ts` after (1)–(2).

**Out of scope:** historic hit-rate MLE, particle filters, re-proposing softVisionAt / mixture shell / spotted τ / √t-Flash-brush / softV→σ_seen / beliefMeanSeen / aEff / factor-only no_lkp, BASE×ZONE×VISION, editing production files in this agent.

---

## 7. Decision

**KEEP_CANDIDATE**

Rationale: Pass-4 made belief APIs honest enough to *tag* residuals (`beliefMeanSeen`, `no_lkp` factor, slow-growth). Pass-5 residual is **belief discipline**: complete the hard rule (no oracle μ without LKP), asymptote σ_belief to zone occupancy instead of unbounded aEff, and plumb combat wards so softVision matches overlay — still inside \(\sigma^2=\sigma_{\mathrm{aim}}^2+\sigma_{\mathrm{juke}}^2+\sigma_{\mathrm{belief}}^2\).

**SKIP** only if Pass-5 bandwidth must fix a failing geo/aim/strategy invariant; vision harness is green (103/103), but product FoW still aims oracle when LKP unset and combat FoW ignores wards.

---

**One-line verdict:** KEEP_CANDIDATE — complete no_lkp (no oracle μ) + σ_occ asymptote + combat ward plumbing; do not re-litigate softV/√t/Flash/brush/multi-mean API.
