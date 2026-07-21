# Pass-8 VISION — softV⊕hypotheses · mixture 2nd moment · FoW-local kinematics

**Axis:** vision  
**Agent:** Pass-8 VISION  
**Against:** Post Pass-7 KEEP (`math_pass_rate=158/158`) — `beliefHypotheses[]` multi-modal pack, `hasBelief`∨hypotheses, overlay `softVisionMarginNorm`  
**Constraint honored:** **no edits** to `xh.ts` / `vision.ts` / combat / overlay / eval. Proposal only.  
**Do not re-propose:** LKP geo mean API, κ=1/√3, softVisionAt / softVisionDetailAt / resolveCastVisionSoft shell, mixture-of-CDFs ∫L b *shell*, spotted τ sign, √t / Flash-belief / brush Cap, softV→σ_seen *exponential form*, margin→σ_seen *form*, `beliefMeanSeen` binary multi-mean, `aEff` slow-growth, factor-only `belief:no_lkp_guard`, complete null-geo openLoop (`geoPos=undefined`, `leadSkill=0`, σ floor), soft asymptote `u≤0.72`, combat `wards` plumbing, open-loop zone=caster, `beliefHypotheses[]` API + pack path, `hasBelief`∨hypotheses wire, overlay margin plumbing.  
**Verdict:** **KEEP_CANDIDATE**

---

## 0. What Pass-1–7 fixed vs what remains

| Landed claim | Status @ Pass-8 |
|---|---|
| Reachable-set `σ_belief` + √t + Flash + brush + `aEff` | **Shipped** |
| SoftVision mixture-of-CDFs ∫L b + `beliefMeanSeen` | **Shipped** (binary means) |
| Complete no_lkp null-geo + `leadSkill=0` + σ floor | **Shipped** |
| Soft σ_occ asymptote `u≤0.72` | **Shipped** |
| Combat / overlay ward + margin plumbing | **Shipped** |
| Open-loop zone = caster | **Shipped** |
| Weighted `beliefHypotheses[]` + `hasBelief`∨hypotheses | **Shipped** (Pass-7) |

Program residual (Pass-8 deepen **σ_belief / soft vision only**):

1. **softV ⊕ hypotheses composition** — Pass-7 pack replaces the softVision seen/lost mix whenever `beliefHypotheses?.length && softV < 0.85`; penumbra / `σ_seen` / `beliefMeanSeen` vanish under multi-modal FoW.  
2. **Mixture second moment** — reported `σ_belief = √(Σ w σ_k²)` omits between-mode Var(μ); mode separation is invisible in `sigma.belief` even when xH correctly mixes CDFs.  
3. **FoW-local kinematics** — each hypothesis recomputes range from `h.mean` but still propagates with shared `vRadial0`/`vPerp0` from caller input (combat = live oracle vel). Soft god-eye through kinematics.  

No BASE×ZONE×VISION. No god-eye (preserve null-geo + caster zone under openLoop; do not read oracle pose/zone/vel when belief is the info set). Do not re-litigate `u≤0.72` or the hypotheses API shape — deepen content inside it.

---

## 1. Critique (concrete residuals)

### 1.1 Hypotheses kill softVision mix (P0 — σ_belief / soft vision)

```1051:1118:src/engine/xh.ts
    if (input.beliefHypotheses?.length && softV < 0.85) {
      ...
      // Σ w Φ_corr over modes only — no softV · seen term
      return { xH: clamp01(xH), sigma: { ..., belief: Math.sqrt(belief2), ... } }
    }
    const sigS = Math.hypot(aim, juke, sigmaSeen, 12)
    const sigL = Math.hypot(aim, juke, sigmaLost, 12)
    const xH =
      softV * corridorHitProb(R_hit, muSeen, sigS) +
      (1 - softV) * corridorHitProb(R_hit, muBias, sigL)
```

Pass-2–3 residual was “∫L b, not Var-mix.” Pass-7 correctly mixed occupancy modes, but under soft penumbra (`0 < softV < 0.85`) the right object is:

\[
xH = s\,\Phi_{\mathrm{seen}}(\mu_s,\sigma_s) + (1-s)\sum_k w_k\,\Phi(\mu_k,\sigma_k).
\]

Current gate is all-or-nothing: any hypotheses array zeros the seen channel. Callers who supply brush/river/jungle modes under partial vision lose Koopman margin → `σ_seen` and `beliefMeanSeen`. Compose; do not replace.

### 1.2 Reported σ_belief drops between-mode variance (P0 — mixture honesty)

```1100:1101:src/engine/xh.ts
        xH += w * corridorHitProb(R_hit, muK, sigK)
        belief2 += w * sigB * sigB
```

xH uses mixture-of-CDFs (correct). Debug / `sigma.belief` / ancient tol path uses only \(E[\sigma_k^2]\). For a mixture,

\[
\sigma_{\mathrm{belief}}^2 = \sum_k w_k\sigma_k^2 + \sum_k w_k(\mu_k-\bar\mu)^2.
\]

Two equal modes with identical `σ_k` but large lateral separation should raise reported belief smear and typically lower corridor mass — Pass-7 only asserts “multi ≠ uni,” not separation monotone. Residual blocks tightening `occ+450` and makes `sigma.belief` lie about support width.

### 1.3 Shared oracle kinematics under FoW modes (P0 — no-god-eye contract)

```1058:1088:src/engine/xh.ts
        const atH = propagateLosFrame(dH, vRadial0, vPerp0, T_delay)
        ...
        const cpaH = ballisticSegmentCpa(
          atH.rangeUu, atH.vRadial, atH.vPerp, ...
        )
```

`vRadial0`/`vPerp0` come from `input.targetRadialVel` / `targetPerpVel` (else isotropic from live `ms`). Combat always has oracle pose; under FoW + hypotheses the info set is {modes}, not live vel. Propagating every mode with the true perp/radial velocity is a soft god-eye: μ_k tracks the live heading even when means are LKP occupancy guesses.

Hard rule remains: blind/dark without belief must not read oracle pose/zone; **with** belief, kinematics must be belief-local (isotropic or per-mode), not oracle vel.

### 1.4 Out of scope / already closed

- Re-opening open-loop zone=caster, null-geo, `u≤0.72`, softV/margin exponential forms, hypotheses API, hasBelief wire, overlay margin.  
- Historic hit-rate MLE / particle filters / LKP scrubber product wiring (engine deepen first).  
- BASE×ZONE×VISION.  
- Editing production / eval in this agent.

---

## 2. Proposed minimal deepen (orchestrator → later)

**Scope:** softV⊕hypotheses composition + mixture 2nd-moment σ_belief + FoW-local kinematics on hyp modes. No BASE×ZONE×VISION. Do not re-litigate Pass-1–7 KEEP shape.

### 2.1 Compose softV with occupancy modes (primary)

```ts
function pack(sigmaJuke: number) {
  const aim = sigmaAim * zScale
  const juke = sigmaJuke * zScale
  const sigS = Math.hypot(aim, juke, sigmaSeen, 12)

  if (input.beliefHypotheses?.length && softV < 0.85) {
    const hs = normalizeWeights(input.beliefHypotheses)
    let xLost = 0
    let belief2 = 0
    let muBar = 0
    const rows: { w: number; mu: number; sigB: number }[] = []
    for (const h of hs) {
      const { muK, sigB } = modeMissAndBelief(h) // §2.3 kinematics
      const w = h.weight
      xLost += w * corridorHitProb(R_hit, muK, Math.hypot(aim, juke, sigB, 12))
      rows.push({ w, mu: muK, sigB })
      muBar += w * muK
    }
    for (const r of rows) {
      belief2 += r.w * (r.sigB * r.sigB + (r.mu - muBar) ** 2)
    }
    const xH =
      softV * corridorHitProb(R_hit, muSeen, sigS) + (1 - softV) * xLost
    const belief = Math.sqrt(belief2)
    return {
      xH: clamp01(xH),
      sigma: {
        aim,
        juke,
        belief,
        total: Math.hypot(aim, juke, belief, 12),
      },
    }
  }
  // else: existing softV mix + beliefMeanSeen path — do not re-litigate
}
```

Preserve: `softV → 0` ⇒ pure hypotheses mix; `softV → 1` ⇒ seen channel dominates (hypotheses ignored when `softV ≥ 0.85`, same gate). Equal softV with deeper margin still tightens σ_seen (Pass-6/7).

### 2.2 Mixture 2nd moment (always with hypotheses)

```ts
// After first pass for μ̄:
belief2 += w * (sigB * sigB + (muK - muBar) * (muK - muBar))
```

Optional factor: `belief:mixture_modes:${hs.length}` when between-mode term > 0. Do not fatten unimodal LKP past `u≤0.72` — separation lives in the mixture, not in κ.

### 2.3 FoW-local kinematics on hyp modes (no oracle vel)

```ts
function modeMissAndBelief(h: Hypothesis) {
  const dH = distanceGameUnits(caster, h.mean)
  // Belief-local: isotropic perp, zero radial — not input.target*Vel
  const vRad = 0
  const vPerp = ms * ISOTROPIC_PERP_FRAC
  const atH = propagateLosFrame(dH, vRad, vPerp, T_delay)
  // ... same intercept / CPA / ZEM chain as today ...
  const zH = h.zone ?? zoneAt(h.mean)
  const sigB =
    h.sigmaBelief ??
    sigmaBeliefLkp({
      ageSec: h.ageSec ?? age,
      dashBudgetUu: dashReadyObs ? kitDash : 0,
      flashBudgetUu: flashBelief,
      brushCapUu: zH === 'brush' ? 280 : undefined,
      zone: zH,
    })
  return { muK, sigB }
}
```

**Eval-safe:** fixtures that need intentional live-heading under FoW must put that heading into mode means (or set a single LKP + explicit vel only on the non-hyp path). Hypotheses-only / multi-mode FoW must not inherit oracle `targetPerpVel`.

Preserve openLoop: no hypotheses + no LKP ⇒ `geoPos=undefined`, caster zone, isotropic floor — unchanged.

### 2.4 Out of scope this pass

- Replacing `u≤0.72` with `u→1`; auto-synthesizing default occupancy modes from map graph.  
- Re-opening open-loop zone / null-geo / margin forms / hasBelief wire / hypotheses API fields.  
- Combat LKP scrubber product wiring (defer until engine composition is green).  
- Historic MLE, particle filters, BASE×ZONE×VISION.  
- Editing production files in this agent.

---

## 3. New eval asserts (additive — do not soften 158)

```ts
// V23: softV ⊕ hypotheses — penumbra raises xH vs pure-dark multi-mode
const dark = estimateXh(base({
  vision: 'blind', softVision: 0, lastKnownAgeSec: 8,
  beliefHypotheses: [
    { weight: 0.5, mean: near, zone: 'brush' },
    { weight: 0.5, mean: { x: near.x + 0.04, y: near.y }, zone: 'river' },
  ],
}))
const penumbra = estimateXh(base({
  vision: 'blind', softVision: 0.55, softVisionMarginNorm: 0.5,
  lastKnownAgeSec: 8,
  beliefMeanSeen: near,
  beliefHypotheses: [
    { weight: 0.5, mean: near, zone: 'brush' },
    { weight: 0.5, mean: { x: near.x + 0.04, y: near.y }, zone: 'river' },
  ],
}))
assert('Pass-8: softV⊕hypotheses ≥ dark multi-mode xH', penumbra.xH + 1e-9 >= dark.xH)

// V24: mode separation raises σ_belief (2nd moment)
const tight = estimateXh(base({
  vision: 'blind', softVision: 0, lastKnownAgeSec: 10,
  beliefHypotheses: [
    { weight: 0.5, mean: near, zone: 'jungle' },
    { weight: 0.5, mean: { x: near.x + 0.01, y: near.y }, zone: 'jungle' },
  ],
}))
const split = estimateXh(base({
  vision: 'blind', softVision: 0, lastKnownAgeSec: 10,
  beliefHypotheses: [
    { weight: 0.5, mean: near, zone: 'jungle' },
    { weight: 0.5, mean: { x: near.x + 0.12, y: near.y }, zone: 'river' },
  ],
}))
assert(
  'Pass-8: separated modes → larger σ_belief',
  !!split.sigma && !!tight.sigma &&
    split.sigma.belief >= tight.sigma.belief + 1e-6,
)

// V25: hyp modes ignore oracle perp vel (no soft god-eye)
const iso = estimateXh(base({
  vision: 'blind', softVision: 0, lastKnownAgeSec: 4,
  targetPerpVel: undefined,
  beliefHypotheses: [{ weight: 1, mean: near, zone: 'jungle' }],
}))
const oracleVel = estimateXh(base({
  vision: 'blind', softVision: 0, lastKnownAgeSec: 4,
  targetPerpVel: 420,
  beliefHypotheses: [{ weight: 1, mean: near, zone: 'jungle' }],
}))
assert(
  'Pass-8: FoW hypotheses use belief-local kinematics',
  Math.abs(iso.xH - oracleVel.xH) < 1e-9 &&
    !!iso.sigma && !!oracleVel.sigma &&
    Math.abs(iso.sigma.belief - oracleVel.sigma.belief) < 1e-9,
)

// Preserve: no-LKP ≠ god-eye, open-loop zone=caster, ancient xH ≤ mid,
// ancient σ ≲ occ+tol, softVision edge>dark, spotted≤unspotted,
// ambush≥mutual, hypotheses-only ≠ openLoop, no BASE×ZONE×VISION.
```

---

## 4. arXiv / cites (Pass-8 focus)

| ID | Use |
|---|---|
| [2604.17811](https://arxiv.org/abs/2604.17811) | ∫L b — soft visibility mass × belief measures compose, not replace |
| [2009.08922](https://arxiv.org/abs/2009.08922) | Multi-hypothesis FoW; mixture moments beyond unimodal σ |
| [1812.00054](https://arxiv.org/abs/1812.00054) | Region priors; between-mode separation is state uncertainty |
| [2602.11373](https://arxiv.org/abs/2602.11373) | Full posterior — no oracle velocity under FoW info sets |
| [2306.11301](https://arxiv.org/abs/2306.11301) | Reachable / occupancy modes; kinematics local to support |
| [2410.13587](https://arxiv.org/abs/2410.13587) | Sensor margin stays on seen channel when composed with lost modes |

---

## 5. Expected metric impact

| Change | Current 158 | After asserts |
|---|---|---|
| softV⊕hypotheses | Fixes penumbra drop | Enables V23 |
| Mixture 2nd moment | Honest `σ_belief` under split modes | Enables V24; may help tighten ancient tol later |
| FoW-local kinematics | Closes soft god-eye via vel | Enables V25; preserves no-god-eye |
| Legacy LKP + softV mix / openLoop | Unchanged when no hypotheses | Stay 158/158 then 158+k/158+k |

**Primary score:** expect stay `158/158` after additive deepen; then `158+k/158+k` with V23/V24/V25.

---

## 6. Minimal patch plan (orchestrator)

1. **Compose** `softV·Φ_seen + (1−softV)·Σ w_k Φ_k` inside hypotheses pack (keep `softV ≥ 0.85` gate).  
2. **Second moment** `Σ w(σ_k² + (μ_k−μ̄)²)` for reported `sigma.belief`.  
3. **Belief-local kinematics** on hyp modes (`vRad=0`, isotropic `vPerp`; ignore `input.target*Vel`).  
4. Append V23, V24, V25 to `eval-xh-math.ts`.  

**Out of scope:** re-proposing null-geo / open-loop zone=caster / `u≤0.72` / combat wards / softV exp / margin form / mixture shell / spotted τ / √t-Flash-brush / beliefMeanSeen / aEff / beliefHypotheses API / hasBelief wire / overlay margin, BASE×ZONE×VISION, editing production files in this agent.

---

## 7. Decision

**KEEP_CANDIDATE**

Rationale: Pass-7 landed multi-modal occupancy and closed false-openLoop / overlay margin. Pass-8 residual is still **σ_belief content under soft vision**: compose penumbra with modes, report mixture second moments so separation is measurable, and strip oracle velocity from FoW hyp kinematics — still inside \(\sigma^2=\sigma_{\mathrm{aim}}^2+\sigma_{\mathrm{juke}}^2+\sigma_{\mathrm{belief}}^2\). No god-eye.

**SKIP** only if Pass-8 bandwidth must fix a failing geo/aim/strategy invariant; vision harness is green (158/158), but softV⊕hypotheses still drops the seen channel and hyp modes still inherit live vel.

---

**One-line verdict:** KEEP_CANDIDATE — softV⊕hypotheses + mixture 2nd moment + FoW-local kinematics; do not re-litigate hypotheses API / hasBelief / overlay margin / u≤0.72 / null-geo.
