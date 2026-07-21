# xH Autoresearch Program

Autonomous improvement loop for skillshot hit probability (`src/engine/xh.ts`),
patterned after karpathy/autoresearch but scored on **mathematical correctness**
(arxiv-aligned invariants), not neural val_bpb.

## Files

| File | Role |
|------|------|
| `src/engine/xh.ts` | Model under test (agents may modify) |
| `scripts/eval-xh-math.ts` | Fixed eval harness (**do not weaken tests to pass**) |
| `xh-autoresearch/program.md` | This file (human / orchestrator edits goals) |
| `xh-autoresearch/log.md` | Keep/discard decisions per pass |

## Metric

Run: `npx --yes tsx scripts/eval-xh-math.ts`

Primary score: **`math_pass_rate`** (fraction of invariant checks passed). Secondary:
`calibration_sanity` (ordering constraints). Higher is better. Never delete or
soften a failing invariant to improve the score.

## Factorization target (arxiv synthesis)

```
xH ≈ P(|miss − μ| < R_hit) under σ² = σ_aim² + σ_juke² + σ_belief²
```

- Geometry: lead / \(t_\text{go}\) / width corridor (not mobility×zone product)
- Aim: Schmidt–Fitts style \(\sigma \propto D/T_\text{avail}\)
- Vision: belief / LKP inflation of \(\sigma\), not oracle position × 0.55
- Dodge: dash/Flash **ready** budget in reaction window vs TOF
- xHm: shared-latent dependence, not independent Binomial

## Pass protocol

1. Five subagents each own one axis (geo / aim / vision / strategy / empirics).
2. Each proposes a minimal patch + cites arxiv id + expected invariant gains.
3. Orchestrator applies keepers only if `math_pass_rate` does not drop.
4. Repeat for **10 passes total** (Pass 1…10). After each wave, deepen remaining failures / math residue — do not re-propose already-landed KEEP work unless a regression appears.
5. Log keep/discard in `xh-autoresearch/log.md`.

Current: **Pass 10 (FINAL) complete** (235/235). Autoresearch loop finished.

## Hard rules

- Do not reintroduce multiplicative `BASE_XH × ZONE × VISION` as the primary model.
- Do not import PN/homing guidance as if skillshots steer.
- Blind casts must not treat true position as known without belief spread.
- Preserve public API used by `combat.ts` / `xhOverlay.ts` (`estimateXh`, `estimateXhm`, `resolveCastVision`).
