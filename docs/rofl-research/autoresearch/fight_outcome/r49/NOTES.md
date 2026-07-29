# R49 NOTES — s1-passrate-vayne-cass

**Branch:** `adv/fo-r49-s1-passrate-vayne-cass`  
**Worktree:** `/Users/river/.codex/worktrees/rofl-fo-r49`  
**never_edited_parent_code:** true (docs mirrored to parent `fight_outcome/r49/`)  
**Product KEEP:** **yes** — Vayne CORE (Q tumble + Silver Bolts fold)  
**FA ≠ odds / pBlue%**

## Next action

Orchestrator: absorb **KEEP** Vayne CORE. S1 pass 0.500→**0.667**, FA 0.7628→**0.8322**; S0 FA/pass flat (no regress). Residual: c1_burst leth 0.75027 (1e-4 over tol) + Anivia c3_burst pathMae 198.

## Mandate

Lift S1 pass via Vayne burst miss-kill + Cassio coverage without S0 regress. Never invent. No pathFollow product.

## Diagnosis

1. **Vayne→Ambessa:** Meraki W modeled as CD-8 cast; real Silver Bolts is on-hit true %maxHP. Burst marks=1 (Q only) left `modelEndHp≈38`. Full killed late (`|leth|≈2.05`).
2. **Cassio→Viktor:** already `windowOk`; coverage weak (truth 18 / model 5, F1≈0.43–0.50). Density / poison-amp levers either no-op or overkill.

## Product KEEP (e1 / e1b)

**Vayne CORE** in `src/data/champions.ts`:
- Q Tumble: wiki %AD empowered AA + attack reset; fold **1× Silver Bolts** (`W% × targetMaxHp` true) when W ranked (non-short)
- W: utility stub (damage via Q fold)
- E Condemn: base + 50% bonus AD
- R Final Hour: utility steroid stub (R-pulse stays 0)

| Metric | e0 baseline | e1 KEEP | Δ |
|--------|------------:|--------:|--:|
| S1 FA | 0.7628 | **0.8322** | **+0.0694** |
| S1 pass | 0.500 | **0.667** | **+0.167** |
| S0 FA | 0.9304 | **0.9304** | flat |
| S0 pass | 0.667 | 0.667 | 0 |
| c1 full | leth 2.05 fail | leth **0.091** **windowOk** | |
| c1 burst | miss endHP38 | leth 0.75027 kill; **lethalOk false** (tol 0.75) | |

## Discarded

| Exp | Why |
|-----|-----|
| e2/e4/e5 + Cassio CORE 1.75× E | Cassio early overkill \|leth\|≈2.77; S1 pass↓ |
| e3 `--repin-each-mark` | S0 Galio miss-kill; S1 collapse |
| e6–e9 Condemn silver-bolt fold | c1 full overkill leth −1.87; pass back to 0.5 |
| e10 `--aa-at-mark` | S0+S1 overkill; pass↓ |
| gap0.25 / densOff | no Cassio coverage lift without leth regress |

## Cassio coverage (honest residual)

Coverage stuck at F1 0.435/0.500 under parent dens (gap0.4 / win1.0). More E marks need gap≪0.4 but poison-amp kit dumps overkill. Out of safe KEEP scope this round — disclose, do not invent marks.

## Repro

```bash
cd /Users/river/.codex/worktrees/rofl-fo-r49
npx --yes tsx scripts/crosscheck_action_aligned.ts \
  --suite 2970137-g1-holdout \
  --mark-selection cusum_engage_then_skills \
  --dense-window 1.0 --dense-max 1 --mark-min-gap 0.4 --near-kill-sec 1.5 \
  --out docs/rofl-research/autoresearch/fight_outcome/r49/experiments/e1b_s1.json
npm run fight:agreement -- --suite-label S1 \
  --from-eval docs/rofl-research/autoresearch/fight_outcome/r49/experiments/e1b_s1.json \
  --out-dir docs/rofl-research/autoresearch/fight_outcome/r49/experiments
```

## Digest

Untouched. digestCleanGate not regressed.
