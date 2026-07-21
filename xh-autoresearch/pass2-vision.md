# Pass-2 VISION — Soft wards · opponent_only · honest ∫L b

**Axis:** vision  
**Agent:** Pass-2 VISION  
**Against:** Pass-1 KEEP (`math_pass_rate=41/41`) — LKP geo, reachable-set `σ_belief`, softVision variance mix, optional `beliefMeanPosition` / `spottedByTarget`  
**Constraint honored:** **no edits to `xh.ts`** (or eval). Proposal + `vision.ts` / overlay-combat wiring only.  
**Verdict:** **KEEP_CANDIDATE**

---

## 0. What Pass-1 fixed vs what remains

| Pass-1 claim | Status in code today |
|---|---|
| Reachable-set `σ_belief` (`κ=1/√3`, dash expand) | **Shipped** in `estimateXh` |
| SoftVision variance mix `√(v σ_s²+(1−v)σ_ℓ²)` | **Shipped**; callers almost never pass `softVision` |
| `beliefMeanPosition` for FoW geometry | **API + geo path**; overlay/combat still feed **oracle** `targetPosition` only |
| `spottedByTarget` → `τ += 0.08` under blind | **API only**; `resolveCastVision` returns early on blind and **never** sets it |
| `softVisionAt` from wards | **Not implemented** — still hard disks in `teamHasVisionAt` |
| Honest \(xH=\int L\,b\) | Still **one** corridor CDF about a shared mean + mixed σ — not mixture-of-CDFs |

Program residual (log.md Pass 2): *wire beliefMean from FoW scrubber* + deepen FoW. This pass deepens the **sensor → belief → cast** contract without touching the σ-corridor core in `xh.ts`.

---

## 1. Critique (concrete)

### 1.1 Overlay / combat still god-eye (P0 wiring)

```78:85:src/engine/xhOverlay.ts
        const est = estimateXh({
          targetChampionId: enemy.loadout.championId,
          casterPosition: caster.position,
          targetPosition: enemy.position,
          abilityRange: ability.range,
          skillshotLengthPenalty: ability.range >= 900,
          vision,
        })
```

Same pattern in `combat.ts` (~190). Ternary `resolveCastVision` runs, but:

- no `softVision` / `beliefMeanPosition` / `lastKnownAgeSec` / `spottedByTarget`
- wards optional on overlay, **absent** on combat path
- Map UI already has `classifyVision` / `isSpottedByEnemy` richer than xH

Net: Pass-1 math is inert in product paths.

### 1.2 `resolveCastVision` drops opponent_only (P0)

```637:654:src/engine/xh.ts
  const casterSees = isVisibleToTeam(...)
  if (!casterSees) return 'blind'
  const targetSees = isVisibleToTeam(...)
  return targetSees ? 'mutual' : 'ambush'
```

When caster is dark, **targetSees is never evaluated**. That is exactly `opponent_only` on the caster cell (`classifyVision` kind=1): you do not see them; they see the cast telegraph. Pass-1 `spottedByTarget` was the POSG fix; defaults never fire.

### 1.3 Soft ward cliff still in `vision.ts` (P1)

Hard disk:

```166:170:src/engine/vision.ts
  if (dist({ x: w.x, y: w.y }, target) <= r) return true
```

Edge of ward → full blind → default `age=2`, `softV=0`. Soft logistic was proposed Pass-1 §2.3 and never landed in `vision.ts`.

### 1.4 Variance mix ≠ \(\mathbb{E}_b[L]\) (P1 math)

Pass-1 used (shared aim mean):

\[
\sigma_b^2 = v\,\sigma_s^2+(1-v)\,\sigma_\ell^2
\]

then one `corridorHitProb(R, μ_\text{lead}, \sqrt{\sigma_\text{aim}^2+\sigma_\text{juke}^2+\sigma_b^2})`.

Literature object (arXiv:2604.17811):

\[
xH(a^\star)=\int L\big(\mathrm{proj}(a^\star),x;R\big)\,b(x)\,dx.
\]

For **1D corridor lethality** \(L=\mathbf{1}_{|m|<R}\) and **Gaussian-mixture** belief

\[
b=v\,\mathcal N(\mu_s,\sigma_s^2)+(1-v)\,\mathcal N(\mu_\ell,\sigma_\ell^2),
\]

with fixed aim \(a^\star\) (lock to belief mean / LKP), the integral **is closed-form**:

\[
xH=v\,\Phi_\text{corr}(R;\mu_s^\perp,\sigma_{\text{tot},s})
+(1-v)\,\Phi_\text{corr}(R;\mu_\ell^\perp,\sigma_{\text{tot},\ell})
\]

where \(\Phi_\text{corr}=\) existing `corridorHitProb`, and

\[
\sigma_{\text{tot},k}^2=\sigma_\text{aim}^2+\sigma_\text{juke}^2+\sigma_k^2.
\]

If \(\mu_s\neq\mu_\ell\), the variance-only mix **misses** the between-component mean gap \(v(1-v)(\mu_s-\mu_\ell)^2\) **and** wrongly averages lethality through a single Gaussian. When \(\mu_s=\mu_\ell\) (common aim), the mixture-of-CDFs still differs from CDF-of-mixture-σ (Jensen); for soft lethality both are fine priors, but **mixture-of-CDFs is the honest \(\int L\,b\)**.

Optional second-order (when means coincide): equal-mean variance mix is a cheap lower-bound proxy; prefer mixture-of-CDFs whenever `softVision` is set.

---

## 2. Proposed deepen (no `xh.ts` edits this agent)

### 2.1 `softVisionAt` in `vision.ts` (implement here / orchestrator)

```ts
/** Soft visibility ∈[0,1]; hard disk is lim κ→∞. Koopman lateral-range shape. */
export function softVisionAt(
  target: MapPosition,
  viewerTeam: TeamSide,
  units: VisionUnit[],
  wards: VisionWard[],
  meta?: TerrainMeta | null,
  kappa = 80, // 1/norm-units
): number {
  const champR = meta?.vision.championSightRadiusNorm ?? 0.09
  const living = units.filter((u) => u.team === viewerTeam && u.alive !== false)
  const targetInBrush = inBrush(target)
  let best = 0

  for (const a of living) {
    let r = champR
    if (targetInBrush) {
      // Brush: only strong if ally also in brush nearby (match hard rule)
      if (!(inBrush(a.position) && dist(a.position, target) < 0.05 + 1 / kappa)) {
        continue
      }
      r = 0.05
    }
    const margin = r - dist(a.position, target)
    best = Math.max(best, 1 / (1 + Math.exp(-kappa * margin)))
  }

  for (const w of wards) {
    if (w.team !== viewerTeam) continue
    const r = w.visionRadius || meta?.vision.wardSightRadiusNorm || 0.055
    const margin = r - dist({ x: w.x, y: w.y }, target)
    best = Math.max(best, 1 / (1 + Math.exp(-kappa * margin)))
  }
  return best
}
```

Keep `teamHasVisionAt` as hard classifier for FoW grid / markers (`classifyVision`). Soft path is **additive** for xH / scrubber.

**Brush note:** soft path should not invent vision through brush; mirror hard brush gate so ward-edge soft does not over-light brush interiors.

### 2.2 `opponent_only` → `spottedByTarget` defaults

Do **not** change ternary `VisionRelation` semantics (combat API). Add a thin resolver beside it (new export; orchestrator can later fold into `xh.ts`):

```ts
// vision.ts or small xhVisionBridge.ts — NOT editing xh.ts this pass
export interface CastVisionResolved {
  vision: 'mutual' | 'ambush' | 'blind' | 'unknown'
  /** Continuous caster→target visibility from wards/champs. */
  softVision: number
  /** Target team sees caster (opponent_only on caster). */
  spottedByTarget: boolean
}

export function resolveCastVisionSoft(input: {
  casterPosition?: MapPosition
  targetPosition?: MapPosition
  casterTeam: TeamSide
  targetTeam: TeamSide
  units: VisionUnit[]
  wards?: VisionWard[]
  meta?: TerrainMeta | null
}): CastVisionResolved {
  if (!input.casterPosition || !input.targetPosition) {
    return { vision: 'unknown', softVision: 0.5, spottedByTarget: false }
  }
  const wards = input.wards ?? []
  const softVision = softVisionAt(
    input.targetPosition,
    input.casterTeam,
    input.units,
    wards,
    input.meta,
  )
  const casterSees = softVision >= 0.5 // or keep hard isVisibleToTeam for ternary
  const spottedByTarget = isVisibleToTeam(
    input.casterPosition,
    input.casterTeam,
    input.targetTeam,
    input.units,
    wards,
    input.meta,
  )
  // Prefer hard disks for ternary labels so FoW overlay ↔ xH relation stay aligned:
  const hardCasterSees = isVisibleToTeam(
    input.targetPosition,
    input.targetTeam,
    input.casterTeam,
    input.units,
    wards,
    input.meta,
  )
  if (!hardCasterSees) {
    return { vision: 'blind', softVision, spottedByTarget }
  }
  return {
    vision: spottedByTarget ? 'mutual' : 'ambush',
    softVision,
    spottedByTarget: false, // mutual/ambush already encode target vision
  }
}
```

**Default rule:** whenever `vision==='blind'`, set `spottedByTarget` from enemy coverage on **caster** position (same predicate as `isSpottedByEnemy`). Map `opponent_only` on the *target* cell is unrelated; the POSG flag is “they see *me*.”

`τ` bump already in Pass-1 (`+0.08` when blind+spotted) is enough for Pass-2; do not stack another fog knob.

### 2.3 Honest closed-form \(\int L\,b\) (orchestrator → `xh.ts` later)

When `input.softVision` is defined (or soft bridge always passes it), replace single pack with two-component lethality mix. **Sketch only** (do not apply in this agent):

```ts
// Inside estimateXh pack(), after sigmaAim / sigmaJuke / sigmaSeen / sigmaLost:
function packMix(sigmaJuke: number): { xH: number; sigma: ... } {
  const aim = sigmaAim * zScale
  const juke = sigmaJuke * zScale
  const sigS = Math.hypot(aim, juke, sigmaSeen, 12)
  const sigL = Math.hypot(aim, juke, sigmaLost, 12)

  // Lateral means under fixed aim-at-beliefMean (geoPos):
  //   seen component: measurement near geo if lit; use muBias (lead residual)
  //   lost component: same aim → same muBias unless truth residual diagnostic
  const muS = muBias
  const muL = muBias
  // If beliefMean ≠ optional truth diagnostic, add δ_⊥ only on oracle band — not production.

  const xH =
    softV * corridorHitProb(R_hit, muS, sigS) +
    (1 - softV) * corridorHitProb(R_hit, muL, sigL)

  // Report effective belief σ for debug (rms of components, not Var-mix fake):
  const beliefEff = Math.sqrt(
    softV * sigmaSeen * sigmaSeen + (1 - softV) * sigmaLost * sigmaLost,
  )
  return {
    xH: clamp01(xH),
    sigma: { aim, juke, belief: beliefEff, total: Math.hypot(aim, juke, beliefEff, 12) },
  }
}
```

**When \(\mu_s=\mu_\ell\):** this is exactly \(\mathbb{E}_{k\sim\mathrm{Bern}(v)}[\Phi_\text{corr}(\sigma_k)]\), i.e. \(\int L\,b\) for the two-Gaussian mixture.

**When ward soft-edge implies \(\mu_s\approx\) live pose and \(\mu_\ell=\) LKP:** pass optional `beliefMeanSeen` later; until scrubber exists, keep \(\mu_s=\mu_\ell=\mu_\text{lead}(\text{geoPos})\) — still more honest than Var-mix through one CDF.

**Jensen note for eval:** mixture-of-CDFs at equal mean is **≥** CDF(Var-mix) for the usual concave-in-σ hit curve near operating point — expect slight **↑** softVision edge xH vs Pass-1; V3 (`edge > dark`) stays; stale/fresh monotone preserved via `σ_lost(age)`.

### 2.4 Overlay / combat wiring sketch (product path)

```ts
// xhOverlay.ts — buildSnapshotXh link loop
const resolved = resolveCastVisionSoft({
  casterPosition: caster.position,
  targetPosition: enemy.position,
  casterTeam: caster.team,
  targetTeam: enemy.team,
  units: visionUnits,
  wards,
  meta: options.terrain,
})

// LKP from scrubber when available (Pass-2 empirics / map timeline):
const lkp = options.lkpByUnitId?.get(enemy.id) // { pos, ageSec } | undefined

const est = estimateXh({
  targetChampionId: enemy.loadout.championId,
  casterPosition: caster.position,
  targetPosition: enemy.position,
  abilityRange: ability.range,
  skillshotLengthPenalty: ability.range >= 900,
  vision: resolved.vision,
  softVision: resolved.softVision,
  spottedByTarget: resolved.spottedByTarget,
  beliefMeanPosition:
    resolved.vision === 'blind' ? (lkp?.pos ?? undefined) : undefined,
  lastKnownAgeSec:
    resolved.vision === 'blind' ? (lkp?.ageSec ?? undefined) : undefined,
})
```

Combat path: thread `wards` + same `resolveCastVisionSoft`; until LKP store exists, softVision + spottedByTarget alone remove the hard cliff / silent opponent_only.

**Dead champions:** already excluded upstream preference — do not invent softVision from dead ward hosts; `alive !== false` filter stays.

---

## 3. New invariants (additive; orchestrator after API/bridge)

Do **not** soften Pass-1 V1–V4. Append:

```ts
// V6: spottedByTarget (opponent_only) lowers blind xH via shorter dodge window
const blindDark = estimateXh(base({ vision: 'blind', lastKnownAgeSec: 1, spottedByTarget: false }))
const blindLit = estimateXh(base({ vision: 'blind', lastKnownAgeSec: 1, spottedByTarget: true }))
assert('spotted blind ≤ unspotted blind', blindLit.xH <= blindDark.xH + 1e-9)

// V7: softVisionAt ward edge is continuous (unit test in vision, not xH)
// softVisionAt(center) > softVisionAt(r+ε) > softVisionAt(r+3/κ) ≈ 0

// V8: mixture-of-CDF honesty — equal-mean softV=0.5 xH ≥ Var-mix proxy within tol
// (only after orchestrator lands packMix; skip until then)

// V9: resolveCastVisionSoft blind + enemy ward on caster ⇒ spottedByTarget true
```

Preserve: stale\<fresh, blind stale\<mutual, ambush≥mutual, belief-aim off LKP, softVision edge\>dark, ancient finite.

---

## 4. arXiv / cites (Pass-2 focus)

| ID | Use |
|---|---|
| [2604.17811](https://arxiv.org/abs/2604.17811) | \(xH=\mathbb{E}_{x\sim b}[L]\) → mixture-of-corridor-CDFs |
| [2602.11373](https://arxiv.org/abs/2602.11373) | Full posterior; no stacked fog scalars beyond \(b\) + τ |
| [2410.13587](https://arxiv.org/abs/2410.13587) | Noisy / soft sensors → continuous \(v\) |
| [2405.18703](https://arxiv.org/abs/2405.18703) | POSG info sets — `opponent_only` ≠ plain blind |
| Koopman 1956 | Soft detection effort / ward penumbra |
| [1812.00054](https://arxiv.org/abs/1812.00054) | FoW as state estimation feeding decisions |

---

## 5. Expected metric impact

| Change | Current 41 checks | New |
|---|---|---|
| `softVisionAt` only | No effect until wired | Enables V7 |
| `spottedByTarget` defaults via soft resolver | No effect until overlay/combat pass flag | Enables V6 / V9 |
| `packMix` ∫L b (xh later) | Should preserve ordering if equal-mean; soft edge may rise slightly | Enables V8 |
| Legacy path (`softVision` unset) | Unchanged defaults (`blind→0`, `unknown→0.5`) | Keep 41/41 |

**Primary score:** expect stay `41/41` until new asserts land; then `41+k/41+k` with k∈{2..4}.

---

## 6. Minimal patch plan (orchestrator)

1. **This axis / next apply:** add `softVisionAt` + `resolveCastVisionSoft` to `vision.ts` (pure; no `xh.ts`).
2. Wire `xhOverlay.ts` + `combat.ts` to pass `softVision`, `spottedByTarget`, wards; LKP when scrubber exists.
3. **Later (xh.ts owner):** replace Var-mix single CDF with mixture-of-`corridorHitProb` when `softVision` provided; leave legacy Var-mix only if needed for bit-identical baselines.
4. Append V6–V9 to `eval-xh-math.ts` after (3).

**Out of scope:** historic hit-rate MLE, xHm ρ, ability-specific width, particle filters, editing `xh.ts` in this agent.

---

## 7. Decision

**KEEP_CANDIDATE**

Rationale: Pass-1 put the right *fields* on `XhEstimateInput`; Pass-2 makes FoW **real** by (a) soft ward sensors in `vision.ts`, (b) defaulting `spottedByTarget` from the same opponent coverage the map already draws as `opponent_only`, (c) specifying the closed-form mixture-of-CDFs so \(\int L\,b\) is exact for 1D corridor + Gaussian mixture — without reintroducing `VISION_XH_MULT` or god-eye geometry when LKP is supplied.

**SKIP** only if Pass-2 bandwidth must go to aim/geo calibration failures; vision is not failing the harness, but product paths still cast as if Pass-1 never happened.
