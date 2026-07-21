# Pass-9 VISION — softV-composed σ_belief · Flash-on-lost

**Axis:** vision  
**Agent:** Pass-9 VISION  
**Against:** Post Pass-8 KEEP (`math_pass_rate=195/195`) — softV⊕hypotheses CDF composition, mixture 2nd-moment σ_belief (lost modes only), FoW-local hyp kinematics (+ shared aim/lead isotropic under FoW+hyp)  
**Constraint honored:** **no edits** to `xh.ts` / `vision.ts` / combat / overlay / eval. Proposal only.  
**Do not re-propose:** LKP geo mean API, κ=1/√3, softVisionAt / softVisionDetailAt / resolveCastVisionSoft shell, mixture-of-CDFs ∫L b *shell*, spotted τ sign, √t / Flash-belief / brush Cap *as forms*, softV→σ_seen *exponential form*, margin→σ_seen *form*, `beliefMeanSeen` binary multi-mean, `aEff` slow-growth, factor-only `belief:no_lkp_guard`, complete null-geo openLoop (`geoPos=undefined`, `leadSkill=0`, σ floor), soft asymptote `u≤0.72`, combat `wards` plumbing, open-loop zone=caster, `beliefHypotheses[]` API + pack path, `hasBelief`∨hypotheses wire, overlay margin plumbing, softV⊕hypotheses *CDF* composition, lost-mode-only 2nd moment, FoW-local hyp / shared aim kinematics.  
**Verdict:** **KEEP_CANDIDATE**

---

## 0. What Pass-1–8 fixed vs what remains

| Landed claim | Status @ Pass-9 |
|---|---|
| Reachable-set `σ_belief` + √t + Flash + brush + `aEff` | **Shipped** |
| SoftVision mixture-of-CDFs ∫L b + `beliefMeanSeen` | **Shipped** |
| Complete no_lkp null-geo + `leadSkill=0` + σ floor | **Shipped** |
| Soft σ_occ asymptote `u≤0.72` | **Shipped** |
| Combat / overlay ward + margin plumbing | **Shipped** |
| Open-loop zone = caster | **Shipped** |
| Weighted `beliefHypotheses[]` + `hasBelief`∨hypotheses | **Shipped** |
| softV⊕hypotheses CDF compose + lost-mode 2nd moment + FoW-local kinematics | **Shipped** (Pass-8) |

Program residual (Pass-9 deepen **σ_belief / soft vision only**):

1. **softV-composed σ_belief honesty** — Pass-8 fixed between-mode Var(μ) *inside* the lost pack and composed softV into **xH**, but reported `sigma.belief` still ignores the softV×seen arm (hyp path) and still omits \(s(1-s)(\mu_s-\mu_\ell)^2\) on the binary softV path.  
2. **Flash-in-belief hard gate at softV=0.5** — `flashBelief` zeros globally when `softV ≥ 0.5`, including on lost / hyp mass under softV⊕hypotheses. Soft discontinuity (~50 uu jump at the gate with Flash ready); lost channel should keep FoW Flash support whenever the cast is still FoW-dark (`softV < 0.85`).  

No BASE×ZONE×VISION. No god-eye (preserve null-geo + caster zone under openLoop; do not read oracle pose/zone/vel when belief is the info set). Do not undo `u≤0.72` or null-geo openLoop. Do not re-litigate Pass-8 CDF composition / hyp kinematics — deepen the **reported belief second moment** and Flash-on-lost consistency under that composition.

---

## 1. Critique (concrete residuals)

### 1.1 softV⊕hypotheses reports dark-only σ_belief (P0 — mixture honesty)

```1146:1160:src/engine/xh.ts
      let belief2 = 0
      for (const r of rows) {
        belief2 += r.w * (r.sigB * r.sigB + (r.mu - muBar) ** 2)
      }
      const xH =
        softV * corridorHitProb(R_hit, muSeen, sigS) + (1 - softV) * xLost
      const belief = Math.sqrt(belief2)
      ...
          belief,
```

xH = \(s\,\Phi_{\mathrm{seen}} + (1-s)\sum w_k\Phi_k\) (Pass-8 ✓). Reported belief is still \(\sqrt{\sum w(\sigma_k^2+(\mu_k-\bar\mu)^2)}\) — the **lost** measure only. Under penumbra, deep `softVisionMarginNorm` tightens Φ_seen (V23) but `sigma.belief` barely moves except via incidental Flash gating (§1.3). The softV-composed belief measure is

\[
b = s\,\mathcal{K}(\mu_s,\sigma_{\mathrm{seen}}) + (1-s)\sum_k w_k\,\mathcal{K}(\mu_k,\sigma_k),
\]

with second moment

\[
\sigma_b^2 = s\,\sigma_{\mathrm{seen}}^2 + (1-s)\,\sigma_{\mathrm{lost\text{-}mix}}^2 + s(1-s)(\mu_s-\bar\mu_{\mathrm{lost}})^2.
\]

### 1.2 Binary softV path still drops between-μ (P0 — same honesty gap)

```1164:1170:src/engine/xh.ts
    const xH =
      softV * corridorHitProb(R_hit, muSeen, sigS) +
      (1 - softV) * corridorHitProb(R_hit, muBias, sigL)
    const belief = Math.sqrt(
      softV * sigmaSeen * sigmaSeen + (1 - softV) * sigmaLost * sigmaLost,
    )
```

When `beliefMeanSeen` shifts \(\mu_s\) off LKP \(\mu_\ell\), xH changes but `sigma.belief` is identical (probe: coloc vs +0.14 mean → Δbelief = 0). Pass-2 residual was “∫L b, not Var-mix” for lethality; Pass-8 closed between-mode Var for hyp modes; the softV **binary** arm still reports \(E[\sigma^2]\) without \(s(1-s)(\mu_s-\mu_\ell)^2\).

### 1.3 Flash-in-belief hard-cuts at softV = 0.5 (P1 — soft vision discontinuity)

```1028:1033:src/engine/xh.ts
  const flashBelief =
    softV < 0.5 && (flashReadyObs === true || flashCdUnknown)
      ? flashReadyObs === true
        ? 400
        : 400 * (input.flashUpPrior ?? 0.35)
      : 0
```

Probe (`flashReady: true`, age 8): softV 0.49 → σ_belief ≈ 705; softV 0.50 → ≈ 653. Under softV⊕hypotheses at softV=0.55, lost modes inherit `flashBelief=0` even though (1−s) mass is still FoW-dark. Flash support belongs on the **lost / hyp** channel for `softV < 0.85` (same gate as hyp pack), not a second hard cut at 0.5. Do not re-open √t / brush Cap / Flash *form* — only the softV gating of an already-shipped budget.

### 1.4 Out of scope / already closed

- Re-opening open-loop zone=caster, null-geo, `u≤0.72`, softV/margin exponential forms, hypotheses API, hasBelief wire, overlay margin, Pass-8 CDF compose / hyp kinematics / shared aim isotropic.  
- Auto-synthesizing default occupancy modes from map graph; combat LKP scrubber product wiring.  
- Historic hit-rate MLE / particle filters.  
- BASE×ZONE×VISION.  
- Editing production / eval in this agent.

---

## 2. Proposed minimal deepen (orchestrator → later)

**Scope:** softV-composed σ_belief 2nd moment (hyp + binary) + Flash-on-lost under `softV < 0.85`. No BASE×ZONE×VISION. Do not re-litigate Pass-1–8 KEEP shape; do not undo `u≤0.72` or null-geo openLoop.

### 2.1 softV-composed belief second moment (primary)

```ts
// Shared helper — belief-axis only (no aim/juke):
function softBeliefSecondMoment(opts: {
  softV: number
  sigmaSeen: number
  muSeen: number
  lostBelief2: number // already Σ w(σ²+(μ−μ̄)²) or σ_lost²
  muLost: number
}): number {
  const s = clamp01(opts.softV)
  return (
    s * opts.sigmaSeen * opts.sigmaSeen +
    (1 - s) * opts.lostBelief2 +
    s * (1 - s) * (opts.muSeen - opts.muLost) ** 2
  )
}
```

**Hyp pack** (replace `belief = Math.sqrt(belief2)`):

```ts
const belief = Math.sqrt(
  softBeliefSecondMoment({
    softV,
    sigmaSeen,
    muSeen,
    lostBelief2: belief2, // Pass-8 within+between modes
    muLost: muBar,
  }),
)
```

**Binary softV path** (replace Var-mix of σ only):

```ts
const belief = Math.sqrt(
  softBeliefSecondMoment({
    softV,
    sigmaSeen,
    muSeen,
    lostBelief2: sigmaLost * sigmaLost,
    muLost: muBias,
  }),
)
```

Preserve: `softV → 0` ⇒ pure lost / hyp 2nd moment (Pass-8 V24 unchanged); `softV ≥ 0.85` ⇒ hyp pack skipped (seen-dominated); equal softV with deeper margin still tightens σ_seen (Pass-6/7).

### 2.2 Flash-on-lost under FoW gate (secondary)

```ts
// Lost / hyp channel only — not a second cut at 0.5.
const flashBelief =
  softV < 0.85 && (flashReadyObs === true || flashCdUnknown)
    ? flashReadyObs === true
      ? 400
      : 400 * (input.flashUpPrior ?? 0.35)
    : 0
```

Seen channel stays Flash-free (`sigmaSeen` unchanged). Optional: scale Flash by `(1 - softV)` instead of a step — step at 0.85 matching hyp pack is enough to kill the 0.5 cliff and restore Flash on penumbra lost mass.

### 2.3 Out of scope this pass

- Replacing `u≤0.72` with `u→1`; auto-synthesizing default occupancy modes.  
- Re-opening open-loop zone / null-geo / margin forms / hasBelief wire / hypotheses API / Pass-8 CDF compose / FoW kinematics.  
- Combat LKP scrubber product wiring.  
- Historic MLE, particle filters, BASE×ZONE×VISION.  
- Editing production files in this agent.

---

## 3. New eval asserts (additive — do not soften 195)

```ts
// V26: softV⊕hypotheses → σ_belief shrinks vs pure-dark multi-mode
// (seen mass + tight margin in the composed 2nd moment)
const dark = estimateXh(base({
  vision: 'blind', softVision: 0, lastKnownAgeSec: 8, flashReady: false,
  beliefHypotheses: [
    { weight: 0.5, mean: near, zone: 'brush' },
    { weight: 0.5, mean: { x: near.x + 0.04, y: near.y }, zone: 'river' },
  ],
}))
const penumbra = estimateXh(base({
  vision: 'blind', softVision: 0.55, softVisionMarginNorm: 0.5,
  lastKnownAgeSec: 8, flashReady: false, beliefMeanSeen: near,
  beliefHypotheses: [
    { weight: 0.5, mean: near, zone: 'brush' },
    { weight: 0.5, mean: { x: near.x + 0.04, y: near.y }, zone: 'river' },
  ],
}))
assert(
  'Pass-9: softV⊕hypotheses → smaller σ_belief than dark multi-mode',
  !!penumbra.sigma && !!dark.sigma &&
    penumbra.sigma.belief + 1e-6 < dark.sigma.belief,
)

// V27: softV between-μ raises σ_belief (binary path)
const coloc = estimateXh(base({
  vision: 'blind', softVision: 0.4, lastKnownAgeSec: 6, flashReady: false,
  beliefMeanPosition: near, beliefMeanSeen: near,
}))
const splitMu = estimateXh(base({
  vision: 'blind', softVision: 0.4, lastKnownAgeSec: 6, flashReady: false,
  beliefMeanPosition: near,
  beliefMeanSeen: { x: near.x + 0.14, y: near.y },
}))
assert(
  'Pass-9: softV between-μ → larger σ_belief',
  !!splitMu.sigma && !!coloc.sigma &&
    splitMu.sigma.belief >= coloc.sigma.belief + 1e-6,
)

// V28: Flash-on-lost continuous across softV=0.5 under FoW
const lo = estimateXh(base({
  vision: 'blind', softVision: 0.49, lastKnownAgeSec: 8,
  beliefMeanPosition: near, flashReady: true,
}))
const hi = estimateXh(base({
  vision: 'blind', softVision: 0.51, lastKnownAgeSec: 8,
  beliefMeanPosition: near, flashReady: true,
}))
assert(
  'Pass-9: no Flash cliff at softV=0.5',
  !!lo.sigma && !!hi.sigma &&
    Math.abs(lo.sigma.belief - hi.sigma.belief) < 40,
)

// Preserve: V23 softV⊕hyp xH ≥ dark, V24 separated modes → larger σ_belief,
// V25 FoW hyp ignore oracle vel, no-LKP ≠ god-eye, open-loop zone=caster,
// ancient xH ≤ mid, ancient σ ≲ occ+tol, softVision edge>dark, spotted≤unspotted,
// ambush≥mutual, hypotheses-only ≠ openLoop, u≤0.72 asymptote, null-geo openLoop,
// no BASE×ZONE×VISION.
```

---

## 4. arXiv / cites (Pass-9 focus)

| ID | Use |
|---|---|
| [2604.17811](https://arxiv.org/abs/2604.17811) | ∫L b — soft visibility mass × belief measures compose in moments, not only CDFs |
| [2009.08922](https://arxiv.org/abs/2009.08922) | Multi-hypothesis FoW; mixture moments across visibility components |
| [1812.00054](https://arxiv.org/abs/1812.00054) | Between-component separation is state uncertainty |
| [2410.13587](https://arxiv.org/abs/2410.13587) | Sensor margin on seen channel; lost mass keeps FoW support budgets |
| [2602.11373](https://arxiv.org/abs/2602.11373) | Full posterior — Flash / dash budgets on unobserved mass, not hard softV cut |
| [2306.11301](https://arxiv.org/abs/2306.11301) | Occupancy / reachable support local to lost modes under partial observation |

---

## 5. Expected metric impact

| Change | Current 195 | After asserts |
|---|---|---|
| softV-composed σ_belief | Fixes penumbra / between-μ honesty | Enables V26, V27 |
| Flash-on-lost (`softV < 0.85`) | Kills softV=0.5 cliff; restores Flash on hyp lost mass | Enables V28 |
| Pass-8 CDF compose / hyp kinematics / u≤0.72 / null-geo | Unchanged | Stay 195/195 then 195+k/195+k |

**Primary score:** expect stay `195/195` after additive deepen; then `195+k/195+k` with V26/V27/V28.

---

## 6. Minimal patch plan (orchestrator)

1. **Compose** softV into reported `sigma.belief` via \(s\sigma_s^2+(1-s)\sigma_{\ell\text{-}mix}^2+s(1-s)(\mu_s-\mu_\ell)^2\) (hyp + binary).  
2. **Flash-on-lost:** gate `flashBelief` at `softV < 0.85` (match hyp pack), not `softV < 0.5`.  
3. Append V26, V27, V28 to `eval-xh-math.ts`.  

**Out of scope:** re-proposing null-geo / open-loop zone=caster / `u≤0.72` / combat wards / softV exp / margin form / mixture shell / spotted τ / √t-Flash-brush *forms* / beliefMeanSeen / aEff / beliefHypotheses API / hasBelief wire / overlay margin / Pass-8 CDF compose / FoW kinematics, BASE×ZONE×VISION, editing production files in this agent.

---

## 7. Decision

**KEEP_CANDIDATE**

Rationale: Pass-8 landed softV⊕hypotheses **CDF** composition, lost-mode 2nd moments, and FoW-local kinematics. Pass-9 residual is still **σ_belief content under soft vision**: report the softV-composed second moment (seen⊕lost / seen⊕modes) so penumbra and `beliefMeanSeen` gaps are measurable, and stop hard-cutting Flash off the lost channel at softV=0.5 — still inside \(\sigma^2=\sigma_{\mathrm{aim}}^2+\sigma_{\mathrm{juke}}^2+\sigma_{\mathrm{belief}}^2\). No god-eye. Do not undo `u≤0.72` or null-geo openLoop.

**SKIP** only if Pass-9 bandwidth must fix a failing geo/aim/strategy invariant; vision harness is green (195/195), but softV-composed `sigma.belief` still lies and Flash still cliffs at 0.5.

---

**One-line verdict:** KEEP_CANDIDATE — softV-composed σ_belief 2nd moment + Flash-on-lost (`softV < 0.85`); do not re-litigate Pass-8 CDF compose / hyp kinematics / u≤0.72 / null-geo.
