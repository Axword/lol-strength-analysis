# R25 NOTES — Path1 remesaure after idleFollowActual KEEP

**Branch:** `adv/fo-r25-path1-remeasure`  
**Worktree:** `/Users/river/.codex/worktrees/rofl-fo-r25`  
**never_edited_parent_code:** true (docs mirrored to parent `fight_outcome/r25/`)  
**FA ≠ odds**

## Mandate

Remeasure authoritative S0 Path1 FA on **2970132-g1** after parent merge of R19 `idleFollowActual: true`. Score S1 under current law (no tune). Audits for failing windows. Remeasure-only — no product KEEP.

## One-liner

**S0 FA 0.4107 / pass 0.167 (n=6) — bit-match R19 0.411; +0.183 vs R05 0.228. S1 FA 0.4170 / pass 0 (no tune).**

## Repro

```bash
cd /Users/river/.codex/worktrees/rofl-fo-r25
npx --yes tsx scripts/crosscheck_action_aligned.ts \
  --suite 2970132-g1-holdout \
  --mark-selection cusum_engage_then_skills \
  --dense-window 1.0 --dense-max 1 --mark-min-gap 0.4 \
  --out docs/rofl-research/autoresearch/fight_outcome/r25/s0_path1_idle_follow.json
npm run fight:agreement -- \
  --suite-label S0 \
  --from-eval docs/rofl-research/autoresearch/fight_outcome/r25/s0_path1_idle_follow.json \
  --out-dir docs/rofl-research/autoresearch/fight_outcome/r25 \
  --audit-dir docs/rofl-research/autoresearch/fight_outcome/r25/audits/s0
```

(Symlink `docs/canvases/_data/crosschecks-2970132-g1-holdout.json` → Path1 windows if worktree lacks canvases.)

## Measured

| Suite | FA | passRate | vs prior |
|-------|-----|----------|----------|
| S0 2970132 Path1 | **0.4107** | 0.167 | = R19 e1; R05 was 0.228 |
| S1 2970137 holdout | **0.4170** | 0.000 | = R19 e4; no tune |

earlyMae S0 (idle-follow on): c1 0/0, c2 0/9.5, c3 **476**/0 — R19 KEEP still holds; c3 earlyPoisoned residual unchanged.

Only S0 pass window: c3-burst Olaf→Camille (score 0.9).

## Sharper blocker (post-remesaure)

**Idle honesty is closed.** Do not re-litigate `idleFollowActual`.

Remaining FA ≪ 0.95 is **lethal / finish timing** (weight 0.4 on lethalHit):

1. **c1 Galio→Trundle** — miss-kill (`lethalOk=false`; earlyOk=true after idle-follow)
2. **c2 Olaf→Trundle** — kill yes but `lethErr≈2.81s` > 0.75 tol; path MAE over burst/full caps
3. **c3 Olaf→Camille full** — earlyPoisoned (`earlyMae=476`) + `lethErr≈18.3s` — opener/finish (R18), not idle

Handoff: R18 lethal miss-kill / earlyPoisoned. Orchestrator may cite S0 FA **0.411** as authoritative Path1 post-KEEP measure.

## Isolation

- Harness outs under `fight_outcome/r25/` only
- freezeEvalWire: seeded worktree `best.json` + `PACKET_DECODE_GATE.json` symlinks (assert ok; never_edited_parent)
- No product code change this round
