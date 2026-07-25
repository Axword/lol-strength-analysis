# R45 NOTES — s2-transfer-remeasure

**Branch:** `adv/fo-r45-s2-transfer-remeasure`  
**Worktree:** `/Users/river/.codex/worktrees/rofl-fo-r45`  
**never_edited_parent_code:** true (docs mirrored to parent `fight_outcome/r45/`)  
**FA ≠ odds**

## Mandate

S2 unused-pro transfer remesaure under current product defaults + lift without invent. Not 2970132/2970137. GRID pro-only (local dump; no API).

## Series choice

**`2954868-g1`** — see `SERIES_CHOICE.md`. GEN vs T1 pro slim; R06 transfer extract; not S0/S1 tune hosts.

## Product defaults measured

| Knob | Value |
|------|-------|
| markSelection | `cusum_engage_then_skills` |
| idleFollowActual | true (R19) |
| aaAtEachMark | false (R30) |
| pulseBySlot | Q/W/E 0.4/0.35/0.55; **R=0** (R30) |
| preBurstLead | 2.5 (R31) |
| killerShareMode | residual_hp (R32) |
| zeroDeadActualHp | true (R33) |
| preEngageOpener | 0.5 / maxPost 3 (R35) |
| openerAllyAttrib | local_skill_share (R36) |
| dense | window 1.0 / max 1 / gap 0.4 |

## Repro

```bash
cd /Users/river/.codex/worktrees/rofl-fo-r45
npx --yes tsx scripts/crosscheck_action_aligned.ts \
  --suite 2954868-g1-transfer \
  --mark-selection cusum_engage_then_skills \
  --dense-window 1.0 --dense-max 1 --mark-min-gap 0.4 \
  --no-action-replay-audit \
  --out docs/rofl-research/autoresearch/fight_outcome/r45/experiments/e01_s2_baseline.json
npx --yes tsx scripts/fight_agreement_suite.ts \
  --suite-label S2 \
  --from-eval docs/rofl-research/autoresearch/fight_outcome/r45/experiments/e01_s2_baseline.json \
  --out-dir docs/rofl-research/autoresearch/fight_outcome/r45/experiments/e01_fa \
  --audit-dir docs/rofl-research/autoresearch/fight_outcome/r45/audits/e01_baseline
```

## Measured (S2)

| Run | FA | passRate | note |
|-----|-----|----------|------|
| **e01 baseline** | **0.4075** | **0.000** | n=6 check×segment; product defaults |
| best lift e17 | 0.4482 | 0.000 | post_engage + pre-burst 0 — still ≪0.90 |
| R06 stored (legacy) | 0.6335 | 0.333 | n=3 scaffold; lethalOk with \|lethErr\|=1.24 — **not** current §B law |

Authoritative S0/S1 baselines (mandate, not retuned here): S0 **0.7766** / S1 **0.5810**.

## Experiments (18)

e01 baseline; e02–e18 CLI ablations (idleFollow, aa-at-mark, pre-burst ±, density, openerAlly, pre-engage opener, post_engage, finishAa, R-pulse, near-kill, ally-share). **None** reach FA≥0.90 or any windowOk under product law. No invent. No pathFollow/pathClamp product. No FK reopen.

## Failing residuals (e01)

- **c1 Camille→Vayne:** kills but late — \|lethErr\| 1.24 full / 3.77 burst (tol 0.75); early+path OK.
- **c2 Cassio→Ambessa:** miss-kill both segments; burst pathMae 145.6 (>90).
- **c3 LeeSin→Ziggs:** earlyPoisoned; pathMae 161/329; lethErr 8.75/16.5s.

## Verdict

**NO KEEP** — no product default change. S2 FA 0.4075 ≪ gate 0.90; passRate 0. Best research lift +0.041 FA still pass 0 and would require S0↑/S1 flat+ proof (not attempted as product; selector swap alone is not KEEP).

## Sharper blocker

Transfer suite fails **lethal timing + miss-kill + earlyPoisoned** on 2954868-g1 under current product stack — not a density-throttle or idleFollow gap. Camille→Vayne kills ~1.2–3.8s late; Cassio never kills Ambessa; LeeSin→Ziggs poisoned path. FA ≠ odds.

## Isolation

- Harness outs under `fight_outcome/r45/` only
- Suite wire `2954868-g1-transfer` in worktree harness/suite scripts only
- No `src/engine/*` product KEEP edits this round
