# Pass-10 VISION (FINAL) — ageDefault FoW-gate align

**Axis:** vision  
**Agent:** Pass-10 VISION (FINAL)  
**Against:** Post Pass-9 KEEP (`math_pass_rate=225/225`) — softV-composed σ_belief 2nd moment (hyp + binary), Flash-on-lost at `softV < 0.85`  
**Constraint honored:** **no edits** to `xh.ts` / `vision.ts` / combat / overlay / eval. Proposal only.  
**Do not re-propose:** LKP geo mean API, κ=1/√3, softVisionAt / softVisionDetailAt / resolveCastVisionSoft shell, mixture-of-CDFs ∫L b *shell*, spotted τ sign, √t / Flash-belief / brush Cap *as forms*, softV→σ_seen *exponential form*, margin→σ_seen *form*, `beliefMeanSeen` binary multi-mean, `aEff` slow-growth, factor-only `belief:no_lkp_guard`, complete null-geo openLoop (`geoPos=undefined`, `leadSkill=0`, σ floor), soft asymptote `u≤0.72`, combat `wards` plumbing, open-loop zone=caster, `beliefHypotheses[]` API + pack path, `hasBelief`∨hypotheses wire, overlay margin plumbing, softV⊕hypotheses *CDF* composition, lost-mode-only / softV-composed 2nd moment, FoW-local hyp / shared aim kinematics, Flash-on-lost *gate value* `softV < 0.85` (already landed — do not re-open form or move back to 0.5).  
**Verdict:** **KEEP_CANDIDATE**

---

## 0. What Pass-1–9 fixed vs what remains

| Landed claim | Status @ Pass-10 |
|---|---|
| Reachable-set `σ_belief` + √t + Flash + brush + `aEff` | **Shipped** |
| SoftVision mixture-of-CDFs ∫L b + `beliefMeanSeen` | **Shipped** |
| Complete no_lkp null-geo + `leadSkill=0` + σ floor | **Shipped** |
| Soft σ_occ asymptote `u≤0.72` | **Shipped** |
| Combat / overlay ward + margin plumbing | **Shipped** |
| Open-loop zone = caster | **Shipped** |
| Weighted `beliefHypotheses[]` + `hasBelief`∨hypotheses | **Shipped** |
| softV⊕hypotheses CDF compose + lost-mode 2nd moment + FoW-local kinematics | **Shipped** (Pass-8) |
| softV-composed σ_belief 2nd moment + Flash-on-lost (`softV < 0.85`) | **Shipped** (Pass-9) |

Program residual (Pass-10 FINAL deepen **σ_belief / soft vision only**):

1. **`ageDefault` still hard-cuts at softV=0.5** — Pass-9 aligned Flash-on-lost / hyp pack / `fowDark` to `softV < 0.85`, but unset `lastKnownAgeSec` still uses `ageDefault = softV < 0.5 ? 2 : 0`. Under penumbra (`0.5 ≤ softV < 0.85`) with no explicit age, `age=0` zeros √t and Flash/dash age gates inside `sigmaBeliefLkp` (`flash * (a ≥ 0.2 ? 1 : 0)`), so Pass-9 Flash-on-lost is **inert** unless callers pass age. Soft discontinuity ~370 uu at softV=0.5 when age unset (probe below).

No BASE×ZONE×VISION. No god-eye (preserve null-geo + caster zone under openLoop). Do not undo `u≤0.72` or null-geo openLoop. Do not re-litigate Pass-8/9 CDF composition, softV-composed 2nd moment, or Flash *budget form* — only align the **default LKP age gate** with the already-shipped FoW threshold.

---

## 1. Critique (concrete residual)

### 1.1 ageDefault cliffs at softV=0.5 (P0 — FoW-gate inconsistency)

```897:898:src/engine/xh.ts
  const ageDefault = softV < 0.5 ? 2 : 0
  const age = input.lastKnownAgeSec ?? ageDefault
```

vs landed Pass-9 Flash / hyp / openLoop FoW gate:

```1089:1090:src/engine/xh.ts
  const flashBelief =
    softV < 0.85 && (flashReadyObs === true || flashCdUnknown)
```

Probe (`beliefMeanPosition=near`, `flashReady: true`, **no** `lastKnownAgeSec`):

| softV | ageDefault | σ_belief |
|---|---|---|
| 0.49 | 2.0s | ~402 |
| 0.50 | 0.0s | ~29 |
| 0.84 | 0.0s | ~22 |

Δ(σ_belief) ≈ **373 uu** across softV=0.5 — larger than the Flash cliff Pass-9 closed (~50 uu with explicit age). With explicit `lastKnownAgeSec: 8`, softV 0.49→0.51 is smooth (~552→542) and Pass-9 V28-class asserts hold; the hole is **only** the unset-age default under penumbra.

Effect inside `sigmaBeliefLkp`: `a=0` ⇒ `sigSqrt=0`, Flash/dash age ramps off, reach collapses toward floor — so `flashBelief=400` under `softV∈[0.5,0.85)` never enters the reachable set when age is defaulted. Pass-9 KEEP intent (“Flash support on lost mass whenever FoW-dark”) is incomplete for the common fallback path.

Pass-9 optional continuous Flash×(1−s) and the softV=0.85 Flash step (Δ≈35 uu with age=8) are **out of scope** — step-at-0.85 was accepted; do not re-open.

### 1.2 Out of scope / already closed

- Re-opening softV-composed 2nd moment, Flash-on-lost *gate value*, CDF compose, hyp kinematics, open-loop zone=caster, null-geo, `u≤0.72`, softV/margin exponential forms, hypotheses API, hasBelief wire, overlay margin.  
- Auto-synthesizing default occupancy modes; combat LKP scrubber product wiring.  
- Historic hit-rate MLE / particle filters; BASE×ZONE×VISION.  
- Editing production / eval in this agent.

---

## 2. Proposed minimal deepen (orchestrator → later)

**Scope:** align unset-age FoW default with `softV < 0.85` (same gate as `fowDark` / hyp pack / Flash-on-lost). No BASE×ZONE×VISION. Do not undo `u≤0.72` or null-geo openLoop. Do not re-litigate Pass-1–9 KEEP shape.

### 2.1 ageDefault FoW-gate align (primary — one line)

```ts
// Match fowDark / hyp pack / flashBelief — not the legacy softV=0.5 cut.
const ageDefault = softV < 0.85 ? 2 : 0
const age = input.lastKnownAgeSec ?? ageDefault
```

Preserve: explicit `lastKnownAgeSec` always wins; `softV → 1` / seen-dominated ⇒ ageDefault 0; `softV → 0` ⇒ ageDefault 2 (unchanged); Pass-9 softV-composed σ_belief + Flash-on-lost with explicit age bit-identical for fixtures that already pass age.

Optional (not required): `ageDefault = softV < 0.85 ? 2 * (1 - softV / 0.85) : 0` — continuous fade. Prefer the step match to Pass-9 Flash/hyp gate; do not invent a third threshold.

### 2.2 Out of scope this pass

- Replacing `u≤0.72` with `u→1`; continuous Flash×(1−softV); moving Flash/hyp gate off 0.85.  
- Re-opening softV-composed moment / CDF compose / FoW kinematics / null-geo / open-loop zone / margin forms.  
- Combat LKP scrubber; historic MLE; BASE×ZONE×VISION.  
- Editing production files in this agent.

---

## 3. New eval asserts (additive — do not soften 225)

```ts
// V29: unset age under penumbra keeps FoW aging (no softV=0.5 age cliff)
const ageLo = estimateXh(base({
  vision: 'blind', softVision: 0.49, flashReady: true,
  beliefMeanPosition: near,
  // lastKnownAgeSec intentionally omitted
}))
const ageHi = estimateXh(base({
  vision: 'blind', softVision: 0.51, flashReady: true,
  beliefMeanPosition: near,
}))
assert(
  'Pass-10: no ageDefault cliff at softV=0.5',
  !!ageLo.sigma && !!ageHi.sigma &&
    Math.abs(ageLo.sigma.belief - ageHi.sigma.belief) < 80,
)

// V30: penumbra unset-age still admits Flash-on-lost vs seen-dominated
const penNoAge = estimateXh(base({
  vision: 'blind', softVision: 0.7, flashReady: true,
  beliefMeanPosition: near,
}))
const seenNoAge = estimateXh(base({
  vision: 'blind', softVision: 0.9, flashReady: true,
  beliefMeanPosition: near,
}))
assert(
  'Pass-10: penumbra unset-age Flash/FoW σ_belief > softV=0.9',
  !!penNoAge.sigma && !!seenNoAge.sigma &&
    penNoAge.sigma.belief + 1e-6 > seenNoAge.sigma.belief,
)

// Preserve: V26 softV⊕hyp σ_belief < dark, V27 between-μ, V28 Flash softV0.55>0.9,
// V23–V25, no-LKP ≠ god-eye, open-loop zone=caster, ancient xH/σ, softVision edge,
// spotted≤unspotted, ambush≥mutual, hypotheses-only ≠ openLoop, u≤0.72 asymptote,
// null-geo openLoop, no BASE×ZONE×VISION. Explicit-age fixtures stay green.
```

---

## 4. arXiv / cites (Pass-10 focus)

| ID | Use |
|---|---|
| [2602.11373](https://arxiv.org/abs/2602.11373) | Partial-observation support budgets must share one observability gate — age default ∈ same FoW partition as Flash/hyp |
| [2410.13587](https://arxiv.org/abs/2410.13587) | Sensor soft-visibility continuum; hard cuts on nuisance defaults recreate cliff artifacts |
| [2009.08922](https://arxiv.org/abs/2009.08922) | Multi-hypothesis FoW — missing last-seen time still requires a FoW-local aging prior, not a second softV=0.5 cut |
| [2306.11301](https://arxiv.org/abs/2306.11301) | Occupancy / reachable support under partial observation — age enters the reachable kernel consistently with visibility mass |

---

## 5. Expected metric impact

| Change | Current 225 | After asserts |
|---|---|---|
| `ageDefault` ↔ `softV < 0.85` | Kills softV=0.5 age cliff; restores Flash/√t under penumbra when age unset | Enables V29, V30 |
| Pass-9 softV-composed σ_belief / Flash-on-lost / u≤0.72 / null-geo | Unchanged for explicit-age fixtures | Stay 225/225 then 225+k/225+k |

**Primary score:** expect stay `225/225` after additive deepen; then `225+k/225+k` with V29/V30.

---

## 6. Minimal patch plan (orchestrator)

1. **Align** `ageDefault = softV < 0.85 ? 2 : 0` (match `fowDark` / hyp / Flash-on-lost).  
2. Append V29, V30 to `eval-xh-math.ts`.  

**Out of scope:** re-proposing null-geo / open-loop zone=caster / `u≤0.72` / combat wards / softV exp / margin form / mixture shell / spotted τ / √t-Flash-brush *forms* / beliefMeanSeen / aEff / beliefHypotheses API / hasBelief wire / overlay margin / Pass-8 CDF compose / FoW kinematics / Pass-9 softV-composed moment / Flash gate *value*, BASE×ZONE×VISION, continuous Flash×(1−s), editing production files in this agent.

---

## 7. Decision

**KEEP_CANDIDATE**

Rationale: Pass-9 landed softV-composed σ_belief and Flash-on-lost at `softV < 0.85`, and the harness is green (225/225) for **explicit-age** fixtures. Pass-10 FINAL residual is the leftover softV=0.5 **`ageDefault` cliff**: under penumbra with unset `lastKnownAgeSec`, age=0 nullifies √t and Flash age ramps, so Pass-9 Flash-on-lost never enters `σ_belief`. One-line gate align with `fowDark` — still inside \(\sigma^2=\sigma_{\mathrm{aim}}^2+\sigma_{\mathrm{juke}}^2+\sigma_{\mathrm{belief}}^2\). No god-eye. Do not undo `u≤0.72` or null-geo openLoop.

**SKIP** only if FINAL bandwidth must fix a failing geo/aim/strategy/empirics invariant and product always supplies `lastKnownAgeSec` (then the cliff is unreachable in-app). Vision harness is green, but the FoW default age gate still lies relative to Pass-9’s softV&lt;0.85 contract.

---

**One-line verdict:** KEEP_CANDIDATE — align `ageDefault` to `softV < 0.85` (FoW gate parity with Flash-on-lost / hyp pack); do not re-litigate Pass-9 σ_belief compose / Flash form / u≤0.72 / null-geo.
