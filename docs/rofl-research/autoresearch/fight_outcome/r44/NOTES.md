# R44 — action-coverage-c1burst

**Branch:** `adv/fo-r44-action-coverage-c1burst`  
**Worktree:** `/Users/river/.codex/worktrees/rofl-fo-r44`  
**never_edited_parent_code:** true (docs mirrored OK)  
**FA ≠ odds / pBlue%**

## Next action

Orchestrator PARENT_MERGE harness truth-domain defaults in `scripts/crosscheck_action_aligned.ts` (R44 truth lead + engage remap). No engine pulse/kit change.

## Mandate

Honest actionCoverage F1 on S0 c1-burst (was F1=0 with truth=0 model≥1). Secondary metric only. Never claim fightOutcomeGate. No zero-dmg log-echo. KEEP product only if S0 FA↑ and S1 flat+.

## Root cause

1. R31 `markPreBurstSkillLeadSec=2.5` loads Galio E+Q from before HP-burst onset (Trundle heal 754→977 resets `detectBurstStartMs`).
2. Model remaps those skills onto CUSUM engage → emits ≥1 skill modelAction.
3. Truth inventory still filtered to `[burstStart, end]` → **truth=0** → F1=0.
4. Domain expand alone (E2) still F1=0: lead skills at negative tSec do not match remapped model times within τ=0.25s.

## KEEP recipe (E3)

```
truth filter start = skillLoadStart  # same as mark load when preBurstLead>0
tSec origin       = windowStart      # lead skills negative
truth remap       = onto same engageSec as mark remap
aaEcho            = disclose only; never fold shareHint=0 into modelActions
CLI ablations     = --truth-burst-window-only | --no-truth-pre-burst-remap
```

## Metrics

| | e0b (legacy truth) | e3 KEEP | Δ |
|--|---:|---:|--:|
| S0 c1-burst F1 | 0.000 | **0.667** | +0.667 |
| S0 c1-burst truth/model/matched | 0/1/0 | 2/1/1 | |
| S0 FA | 0.7740 | **0.7907** | +0.0167 |
| S0 pass | 0.333 | 0.333 | 0 |
| S1 FA | 0.5810 | 0.5810 | 0 |
| S1 pass | 0.333 | 0.333 | 0 |

FA lift = secondary actionF1 term only (0.15 × 0.667 / 6 ≈ 0.0167). Lethal/path unchanged on c1-burst.

## Echo control (E8)

Honest F1=0.667 gateEligible. Zero-dmg pad → raw F1=1.0 → **REJECT** (forbid #13). Not fightOutcomeGate / actionReplayGate evidence.

## Residual

- c1-burst F1=0.667≪0.95 (model emits 1 of 2 lead skills; second skipped post-lethal / same-tSec density).
- earlyMae 255 / pathMae 128 still fail windowOk; passRate 0.333.
- fightOutcomeGate false. actionReplayGate false.
- FA ≠ odds.

## Reproduce

```bash
cd /Users/river/.codex/worktrees/rofl-fo-r44
npx --yes tsx scripts/crosscheck_action_aligned.ts \
  --suite 2970132-g1-holdout --mode gate_action \
  --mark-selection cusum_engage_then_skills \
  --dense-window 1.0 --dense-max 1 --mark-min-gap 0.4 \
  --out docs/rofl-research/autoresearch/fight_outcome/r44/experiments/e3_domain_remap.json
npx --yes tsx scripts/fight_agreement_suite.ts \
  --from-eval docs/rofl-research/autoresearch/fight_outcome/r44/experiments/e3_domain_remap.json \
  --suite-label S0 --out-dir docs/rofl-research/autoresearch/fight_outcome/r44/experiments/fa_e3_S0
npx --yes tsx scripts/fo_r44_echo_reject_audit.ts
```
