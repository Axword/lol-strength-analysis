# Engage-gate + re-pin research — no product change

**Status:** dry-run only (`--gate-research`). `combat.ts` unchanged. `shipGate: false`.

## Modes
| Mode | Idle | Fight loadouts |
|------|------|----------------|
| **naive** | hold window-start victim HP | window-start pins, clock `(t−engage)` |
| **repin** | same idle | **re-pin HP/combat/ranks/items at engage** |

## Command

```bash
npx --yes tsx scripts/crosscheck_kill_window.ts --check 2 --segment full --gate-research
# look at gateResearch.gatedRepin vs gatedNaive vs baseline
```

## Results (2970110 g1 full)

| Check | Engage | Early MAE base→repin | Late MAE base→repin | Lethal err repin | Poison | Killed |
|-------|--------|----------------------|---------------------|------------------|--------|--------|
| 01 | 2.2s | 158→**58** | 317→299 | **none** (lost) | false | no |
| 02 | 17.7s | 814→**0** | 629→738 (still worse) | **+2.8s** | true→**false** | **yes** |
| 03 | ~0s | unchanged | unchanged | +3.3s | false | yes |

vs naive: check 02 full MAE 545→**332**; late 840→**738**; lethal restored (naive had none).

Transfer: check 03 early Δ = 0 → OK.

## Plain English
1. **Re-pin helps check 02** (early fixed, poison cleared, kill comes back).
2. **Still not shippable:** check 01 loses lethal; check 02 late MAE still worse than baseline; lethal err 2.8s > 2s bar.
3. Root leftover: short post-engage clock + 1v1 vs real finish (assists / combo order), not “missing a damage coeff.”

## Ship bar (all must pass + holdout)
- Early MAE not worse on 01–03  
- Check 02 `earlyPoisoned` false  
- Lethal err within ±2s on 01–02  
- Late MAE not worse than baseline by >50 on 01–02  
- Check 03 early not hurt  

**Current: FAIL** → keep `shipGate: false`.

Summary (full): `docs/canvases/_data/crosscheck-gate-repin-summary.json`

---

## Burst-only gate (`--segment burst`)

Same naive + re-pin overlay on the short lethal window.

```bash
npx --yes tsx scripts/crosscheck_kill_window.ts --check 2 --segment burst --gate-research
```

### Results (2970110 g1 burst)

| Check | Engage | Early MAE base→repin | Full MAE base→repin | Lethal | Poison | Killed |
|-------|--------|----------------------|---------------------|--------|--------|--------|
| 01 | 0.57s | 67→**52** | 188→**122** | none (base none) | false | no |
| 02 | 0.43s | 480→**240** | 289→**155** | base −1.5 → **lost** | false | no |
| 03 | 2.54s | 728→**3** | 675→**287** | base +1.1 → **lost** | true→false | no |

Naive ≈ repin on 02 (engage near burst start; pins already close).  
Transfer: check 03 early **improves** (not hurt).

### Burst plain English
- Gate still helps **opener overdamage** on short windows.
- **Every check that used to kill loses lethal** under burst gate (02, 03).
- Burst is a harder bar than full: finish clock is only ~2–6s after engage.

**Burst shipGate: false** (same as full).

Summary (burst): `docs/canvases/_data/crosscheck-gate-burst-repin-summary.json`
