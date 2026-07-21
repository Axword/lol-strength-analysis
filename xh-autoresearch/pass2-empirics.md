# Pass-2 EMPIRICS — corridor Brier / ability rates / calibration kill criteria

**Verdict: KEEP_CANDIDATE**

Eval after this pass (existing checks preserved + 8 new empirics asserts):
`math_pass_rate=1.0000` (**49/49**) via `npm run eval:xh`.

`src/engine/xh.ts` was **not** edited (EMPIRICS constraint). All deepening lives in
`scripts/xh-baselines.ts` + `scripts/eval-xh-math.ts`.

---

## What Pass-1 left shallow

1. **Corridor calibration was stub-only** — `corridorCalibrationStub` existed but
   eval never asserted |empirical − p̂| or Brier vs a coin baseline.
2. **No ability-specific rate competitor** — B1 (σ-corridor) has nothing to lose
   to once cast→hit logs arrive.
3. **No post-hoc calibration hook** — temperature / Platt not wired; raw xH is
   treated as already calibrated.
4. **No kill criteria vs B1** — Pass-1 keep decision had no documented threshold
   for discarding the analytic corridor when logs disagree.

---

## Shipped this pass

### 1. Corridor Brier sanity (eval)

Multi-cell synthetic check via `corridorBrierSanity`:

- Draw `M ~ N(μ, σ²)`, hit iff `|M| < R`.
- Predict `p̂ = corridorHitProb(R, μ, σ)` (production closed form).
- Assert `|empiricalRate − p̂| ≤ corridorRateTol` (default **0.03**).
- Assert mean model Brier ≤ mean **coin** Brier × `brierVsCoinMaxRatio` (**1.15**).
  Coin peeks at the empirical cell rate (strong baseline); ratio slack absorbs
  MC noise without allowing a broken Φ corridor.

Cells span centered / offset μ and several σ so a wrong CDF or abs-vs-signed
miss definition fails.

### 2. Ability-rate baseline stub

`abilityRateBaseline(abilityKey, fallback=0.5)` + in-memory
`registerAbilityRate` / `clearAbilityRates`.

- **Empirical** when casts > 0: `hits/casts`.
- **Fallback** otherwise (no logs yet).

This is the B1 competitor for residual / Brier scoring once VOD or timeline
cast→hit labels exist. Not fitted here — wiring + eval smoke only.

### 3. Temperature / Platt placeholders

```
temperature:  σ(logit(p) / T)          // T>1 softens
platt:        σ(a + b · logit(p))      // affine on logit
```

Identity at `T=1` / `(a=0,b=1)`. Eval asserts identity + softening. Fitters
deferred until held-out cast logs; apply only if Brier gain ≥
`calibrationMinBrierGain`.

Cite: Guo et al. ICML 2017 (temperature); Platt 1999 (sigmoid calibration).

### 4. Kill criteria vs B1

**B1** = Pass-1 analytic σ-corridor prior (`corridorHitProb` + factored σ in
`xh.ts`), scored by math invariants + synthetic corridor calibration.

| Criterion | Threshold (`KILL_CRITERIA_VS_B1`) | Action |
|-----------|-----------------------------------|--------|
| Synthetic corridor rate gap | `corridorRateTol = 0.03` | Fail math eval / discard broken Φ |
| Model Brier vs coin | `brierVsCoinMaxRatio = 1.15` | Fail math eval if corridor mis-scored |
| Ability residual (logs) | mean `\|xH − abilityRate\| > 0.08` **and** ability Brier beats corridor by ≥ `0.01` | **Kill B1** → prefer ability tables / refit σ scales |
| Platt / temperature | held-out Brier gain < `0.005` | Do **not** apply post-hoc scale |

Until cast→hit logs exist, only the synthetic corridor rows gate `math_pass_rate`.
Ability / Platt kill rows are documented contracts for Pass-3+ empirics.

---

## Eval hardening (added, not weakened)

In `scripts/eval-xh-math.ts`:

1. `corridor Brier: |empirical−p̂| ≤ rateTol`
2. `corridor Brier: model ≤ coin×ratio (kill criteria)`
3. `ability-rate stub: registered empirical`
4. `ability-rate stub: missing → fallback 0.5`
5. `temperature identity at T=1`
6. `platt identity at a=0,b=1`
7. `temperature T>1 softens toward 0.5`
8. `kill-criteria constants finite`

---

## Baselines extensions (`scripts/xh-baselines.ts`)

| Export | Role |
|--------|------|
| `corridorBrierSanity` | Multi-cell rate + Brier vs coin |
| `abilityRateBaseline` / `registerAbilityRate` | Per-ability empirical stub |
| `temperatureScale` / `plattScale` | Post-hoc calibration placeholders |
| `KILL_CRITERIA_VS_B1` | Shared thresholds for eval + future log scoring |

Smoke: `npx --yes tsx scripts/xh-baselines.ts`

---

## Proposed production follow-ups (do **not** apply in EMPIRICS)

1. Wire FoW scrubber → `beliefMeanPosition` (vision axis) so belief cells enter
   the same Brier harness.
2. Mine cast→hit from timeline/VOD → fill `ABILITY_RATE_TABLE` by ability +
   strata; then enforce ability kill criteria offline.
3. Optional: replace MC `estimateXhm` with analytic PMF (Pass-1 KEEP still open).
4. Fit Platt `(a,b)` or temperature `T` only if held-out gain ≥ 0.005.

**Expected invariant gains:** calibration axis now fails loudly if corridor Φ
drifts; kill criteria prevent silent keep of a miscalibrated B1 once logs land.

**Risk:** coin baseline is oracle-ish (uses empirical rate); ratio 1.15 is
intentional slack — do not tighten below ~1.05 without larger `trials`.

---

## Citations

- Program factorization: `xH ≈ P(|miss − μ| < R)` under σ² = σ_aim² + σ_juke² + σ_belief².
- Brier score as proper scoring rule for probabilistic forecasts.
- Guo et al., On Calibration of Modern Neural Networks. ICML 2017 (temperature).
- Platt, Probabilistic Outputs for Support Vector Machines. 1999.
- Pass-1 EMPIRICS: Ochi & Prentice 1984 / arXiv:2403.02194 / arXiv:2606.27288 (xHm).

---

## Decision

**KEEP_CANDIDATE** — corridor Brier eval + ability-rate / Platt stubs + documented
kill criteria vs B1 deepen empirics without touching `xh.ts` or softening
invariants. Orchestrator should keep the new eval asserts; defer ability/Platt
fitters until logs exist.
