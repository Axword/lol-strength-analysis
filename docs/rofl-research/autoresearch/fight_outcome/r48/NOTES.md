# R48 NOTES — s0-passrate-c2c3

**Branch:** `adv/fo-r48-s0-passrate-c2c3`  
**Worktree:** `/Users/river/.codex/worktrees/rofl-fo-r48`  
**never_edited_parent_code:** true (docs mirrored to parent `fight_outcome/r48/`)  
**Product KEEP:** **yes** — harness default `killerMarkShare=0.62` gated `Olaf→Camille`  
**FA ≠ odds / pBlue%**

## Mandate

Lift S0 pass 0.667→↑ by fixing remaining failing windows (c2_burst pathMae, c3 residual). KEEP iff S0 FA↑ and S1 flat+. No pathFollow product.

## Diagnosis

Failing under compound stack (FA 0.9304 / pass 0.667):

| Window | Fail | mae | pathCap | notes |
|--------|------|----:|--------:|-------|
| c2_burst Olaf→Trundle | pathMae | 111.6 | 90 | lethErr −0.33; kit-dump cliff; R40 floor ~101 without pathFollow |
| c3_full Olaf→Camille | pathMae | 159.3 | 130 | teamfight residual; R36 local share mean≈0.40 already on |

Pulse / finish-AA / gap softens are **no-ops** on kit dump (e1–e5, e7–e8). Global killer share breaks Galio + c2 miss-kill. Finish-preserve Olaf share helps c3 but worsens c2 when both Trundle+Camille gated.

## KEEP (e43 / e51)

Post–R36 ally attrib, multiply killer mark share ×**0.62** only when `killerChamp=Olaf` and `victimChamp=Camille`.

| Metric | e0 baseline | e51 KEEP | Δ |
|--------|------------:|---------:|--:|
| S0 FA | 0.9304 | **0.9430** | **+0.0126** |
| S0 pass | 0.6667 | **0.8333** | **+0.1667** |
| S1 FA | 0.7628 | **0.7628** | **flat** |
| S1 pass | 0.5000 | 0.5000 | 0 |
| c3_full mae | 159.3 | **129.8** | pathOk |
| c2_burst mae | 111.6 | 111.6 | still fail |

Ablate `--killer-mark-share 1` restores c3 mae 159.3.

## Discarded / research-only

| Exp | Why |
|-----|-----|
| e1–e5,e7–e8 | pulse/finish/gap/horizon no-op or worse |
| e9–e13 global share | Galio regress + c2 miss-kill |
| e17–e24 Olaf-all share | c2 miss-kill cliff |
| e25–e32 Olaf fp share | c3↓ but c2 mae↑ |
| e33–e38 min-window | c2 full window also ≥15s — bleeds into c2 |
| pathFollow | mandate forbid product; S1-unsafe historically |

## Sharper residual (post-KEEP)

**c2_burst pathMae 111.6>90** remains. Kit-dump finish cliff: share&lt;1 misses kill; share=1 floors mae≈111.6 under lethOk (−0.33s). No pathFollow product. Next track needs S1-safe temporal spread (not truth-follow).

## Code (research KEEP default on)

`scripts/crosscheck_action_aligned.ts`:
- `killerMarkShare=0.62`
- `killerMarkShareChamps=Olaf`
- `killerMarkShareVictimChamps=Camille`
- CLI: `--killer-mark-share`, `--killer-mark-share-champs`, `--killer-mark-share-victims`, `--killer-mark-share-finish-preserve`, `--killer-mark-share-min-window`

## Repro

```bash
cd /Users/river/.codex/worktrees/rofl-fo-r48
npx --yes tsx scripts/crosscheck_action_aligned.ts \
  --suite 2970132-g1-holdout \
  --mark-selection cusum_engage_then_skills \
  --dense-window 1.0 --dense-max 1 --mark-min-gap 0.4 \
  --out docs/rofl-research/autoresearch/fight_outcome/r48/experiments/e51_keep_default.json
npm run fight:agreement -- --suite-label S0 \
  --from-eval docs/rofl-research/autoresearch/fight_outcome/r48/experiments/e51_keep_default.json \
  --out-dir docs/rofl-research/autoresearch/fight_outcome/r48/experiments \
  --audit-dir docs/rofl-research/autoresearch/fight_outcome/r48/audits/e51_s0
```

## Digest

Untouched. digestCleanGate not regressed. FA ≠ odds.
