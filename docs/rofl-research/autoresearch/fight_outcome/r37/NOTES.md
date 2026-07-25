# R37 NOTES — holdout-s1-remeasure (wave2)

**Branch:** `adv/fo-r37-holdout-s1-remeasure`  
**Worktree:** `/Users/river/.codex/worktrees/rofl-fo-r37`  
**never_edited_parent_code:** true (docs mirrored to parent `fight_outcome/r37/`)  
**FA ≠ odds**

## Mandate

Remeasure S0 + S1 under **current product defaults** after parent merge of R28 Galio CORE + R30 `aaAtEachMark=false` / `pulseBySlot R=0`. No tune on S1. Freeze JSON + audits. Remeasure-only — no product KEEP.

## One-liner

**S0 FA 0.5938 / pass 0.333 (n=6). S1 FA 0.5620 / pass 0.333 (n=6, no tune).** Gate false (≪0.95).

## Product defaults measured

| Knob | Value |
|------|-------|
| markSelection | `cusum_engage_then_skills` |
| idleFollowActual | true (R19) |
| aaAtEachMark | false (R30) |
| pulseBySlot | Q/W/E 0.4/0.35/0.55; **R=0** (R30) |
| dense | window 1.0 / max 1 / gap 0.4 |
| Galio CORE | present (R28) |

## Repro

```bash
cd /Users/river/.codex/worktrees/rofl-fo-r37
npx --yes tsx scripts/crosscheck_action_aligned.ts \
  --suite 2970132-g1-holdout \
  --mark-selection cusum_engage_then_skills \
  --dense-window 1.0 --dense-max 1 --mark-min-gap 0.4 \
  --out docs/rofl-research/autoresearch/fight_outcome/r37/experiments/s0_product_defaults.json
npm run fight:agreement -- \
  --suite-label S0 \
  --from-eval docs/rofl-research/autoresearch/fight_outcome/r37/experiments/s0_product_defaults.json \
  --out-dir docs/rofl-research/autoresearch/fight_outcome/r37 \
  --audit-dir docs/rofl-research/autoresearch/fight_outcome/r37/audits/s0
# S1: same flags, suite 2970137-g1-holdout → s1_product_defaults.json / audits/s1
```

## Measured

| Suite | FA | passRate | vs R30 | vs R25 |
|-------|-----|----------|--------|--------|
| S0 2970132 Path1 | **0.5938** | 0.333 | +0.004 vs 0.5897 | +0.183 vs 0.411 |
| S1 2970137 holdout | **0.5620** | 0.333 | ≈0 vs 0.562 | +0.145 vs 0.417 |

Pass windows: S0 `c2_full` Olaf→Trundle + `c3_burst` Olaf→Camille; S1 `c2_full`+`c2_burst` Cassio→Viktor.

## Failing residuals (audits/)

**S0:** c1_full Galio lethErr=2.61 (kills late); c1_burst miss-kill 0 marks; c2_burst pathMae; c3_full earlyMae=476 + lethErr≈18s.

**S1:** c1_full lethErr=2.05; c1_burst miss-kill + earlyMae 77.8; c3 Anivia→Sylas miss-kill (full+burst pathMae).

## Sharper blocker

R28+R30 product defaults **confirmed** (S1 bit-match R30; S0 slightly above from Galio CORE). Do not re-litigate R30 pulse/AA KEEP. Remaining FA≪0.95 is lethal timing + Camille earlyPoisoned + S1 Anivia miss-kill / Vayne burst marks.

## Isolation

- Harness outs under `fight_outcome/r37/` only
- freezeEvalWire: worktree `best.json` + `PACKET_DECODE_GATE.json` symlinks (assert ok)
- No product code change this round (`never_edited_parent_code: true`)
