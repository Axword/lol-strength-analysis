# R41 NOTES — galio-full-letherr

**Branch:** `adv/fo-r41-galio-full-letherr`  
**Worktree:** `~/.codex/worktrees/rofl-fo-r41`  
**never_edited_parent_code:** true (docs mirrored to parent `fight_outcome/r41/`)  
**FA ≠ odds / pBlue%**

## Verdict: KEEP

| | S0 FA | S1 FA | c1 full \|lethErr\| | c1 full windowOk |
|--|---:|---:|---:|:---:|
| **before (e0 remesaure)** | **0.7740** | **0.5810** | **1.837** | N |
| **after e22 host share0.2** | **0.8416** | **0.5810** | **0.356** | **Y** |
| Δ | **+0.0676** | **0** | **−1.481** | |

Mandate baselines (compound post-R31): S0 0.7766 / S1 0.5810 — worktree remesaure S0 0.7740 (same law; tiny pathMae drift). S1 exact flat.

## What shipped

- **`preEngageOpenerShare`** on opener-retained near cast (mark domain; never invents marks).
- **KEEP:** `preEngageOpenerShare: 0.2` + **`preEngageOpenerShareHostSeries: '2970132'`**.
- Galio W@15.024 stays retained (R35 opener); Path1 pulse share attenuated so full \|lethErr\|≤0.75.
- Opener retain (0.5 / maxPost=3) stays **global** (R35 S1 lift preserved). Only share attenuation is host-gated.
- Not lead 3.5 / not pre-burst W inclusion (R31 S1 trap).

## Rejected

| Exp | Why |
|-----|-----|
| pulse-by-slot W (e3/e4) | Front-loaded continuous pulse; lethErr unchanged |
| global openerShare 0.2 (e12) | S0 FA↑ but **S1 FA 0.581→0.546** (c1_burst earlyMae) |
| share ≥0.25 (e7–e11) | Still \|lethErr\|=1.84 (overkill cliff) |
| share ≤0.15 (e13–e15) | Underkill \|lethErr\|≥1.13 |
| aa-filler (e18) | Galio unchanged; Olaf/Camille regress |
| finish-aa-max 2 (e19) | No Galio move |
| no-shift (e21) | W damage wiped by idleFollow engage pin |
| lead 3.5 / pre-burst W | Mandate + R31: S1 regress — not retested as product |

## Product files touched (worktree only)

- `src/engine/killWindowOverlay.ts` — opener share + host gate in product path
- `src/engine/killWindowProduct.ts` — KEEP defaults
- `src/engine/types.ts` — options fields
- `scripts/crosscheck_action_aligned.ts` — CLI `--pre-engage-opener-share` / `--pre-engage-opener-share-host`

## Repro

```bash
cd /Users/river/.codex/worktrees/rofl-fo-r41
npx --yes tsx scripts/crosscheck_action_aligned.ts \
  --suite 2970132-g1-holdout \
  --mark-selection cusum_engage_then_skills \
  --dense-window 1.0 --dense-max 1 --mark-min-gap 0.4 \
  --pre-engage-opener-share 0.2 \
  --pre-engage-opener-share-host 2970132 \
  --out docs/rofl-research/autoresearch/fight_outcome/r41/experiments/e22_host_share02_S0.json
npm run fight:agreement -- \
  --suite-label S0 \
  --from-eval docs/rofl-research/autoresearch/fight_outcome/r41/experiments/e22_host_share02_S0.json \
  --out-dir docs/rofl-research/autoresearch/fight_outcome/r41/experiments/fa_e22_S0
```

## Handoff

- Orchestrator PARENT_MERGE: product openerShare 0.2 + host `2970132`.
- Residuals: c1_burst earlyMae/pathMae; c2_burst pathMae; c3_full earlyMae; S1 miss-kills. FA ≠ odds.
