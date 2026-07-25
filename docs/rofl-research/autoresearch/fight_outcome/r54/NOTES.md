# R54 — compound-audit-pack

**Branch:** `adv/fo-r54-compound-audit-pack`  
**Worktree:** `/Users/river/.codex/worktrees/rofl-fo-r54`  
**never_edited_parent_code:** true (docs mirror OK)  
**Product KEEP:** NO  
**FA ≠ odds / pBlue%**

## Next action

Orchestrator: absorb `sharper_blockers.json`. Assign owners to **pathMae** (+21.6 c2_burst, +29.3 c3_full) and **S1 Vayne leth** — not actionF1, not density, not pathFollow.

## Mandate

Failing-window audit package + sharper blockers for FO≪0.95. KEEP only if real FA/pass lift with S1 flat+.

## Remesaure (post R43 compound stack)

| Suite | FA | pass | vs 0.95 | failing |
|-------|---:|-----:|--------:|---------|
| S0 2970132-g1 | **0.9304** | 0.667 | −0.0196 | c2_burst pathMae, c3_full pathMae |
| S1 2970137-g1 | **0.7628** | 0.500 | −0.1872 | c1 leth/miss, c3_burst pathMae |
| S2 2954868-g1 | **0.5861** | 0.333 | ≪0.90 | Cassio miss, LeeSin earlyPoisoned |

S0/S1 match STATUS. S2 above R45 STATUS 0.4075 because Camille→Vayne leth now passes under R39/R42 stack; Cassio+LeeSin still block.

## Sharper blockers (ranked)

1. **S0 c2_burst pathMae 111.6>90** (+21.6) — R40 floor ~101 NO KEEP; pathFollow forbidden
2. **S0 c3_full pathMae 159.3>130** (+29.3) — Olaf→Camille spacing
3. **S1 Vayne→Ambessa leth** — full |err|=2.05; burst miss-kill (holdout)
4. **S1 Anivia c3_burst pathMae 198>90** — post R43 Q-fold lethOk; fat dump vs burst
5. **S2 Cassio miss-kill** — burst pathMae 145.6
6. **S2 LeeSin earlyPoisoned** — |leth| 8.75/16.2; diagnostic class
7. **actionF1 secondary ceiling** — w=0.15; all-F1=1 cannot close S0→0.95 alone
8. **passRate flips** — S0 needs ≥2; S1 ≥3; S2 ≥4

## Ablations (do not fix FO)

| Exp | Undo | Result |
|-----|------|--------|
| E07 | R44 truth domain | FA 0.9304→0.9137; pathMae unchanged |
| E08 | R42 delay | S1 leth/path unchanged |
| E09 | R33 zeroDead | c2_burst mae 111.6→117.7 **worse** |
| E10 | R39 W-share→1.0 | pathMae flat |

## Experiments (14)

E01–E03 suite remesaure · E04 FA gap decomp · E05 failing catalog · E06 pathMae Δ · E07–E10 ablations · E11 actionF1 ceiling · E12 passRate flips · E13 ablation table · E14 sharper pack

## Reproduce

```bash
cd /Users/river/.codex/worktrees/rofl-fo-r54
npx --yes tsx scripts/crosscheck_action_aligned.ts \
  --suite 2970132-g1-holdout --mark-selection cusum_engage_then_skills \
  --dense-window 1.0 --dense-max 1 --mark-min-gap 0.4 \
  --out docs/rofl-research/autoresearch/fight_outcome/r54/experiments/e01_stack_s0.json
npm run fight:agreement -- --suite-label S0 \
  --from-eval docs/rofl-research/autoresearch/fight_outcome/r54/experiments/e01_stack_s0.json \
  --out-dir docs/rofl-research/autoresearch/fight_outcome/r54/experiments \
  --audit-dir docs/rofl-research/autoresearch/fight_outcome/r54/audits/e01_stack_s0
```

## Digest

Untouched. digestCleanGate not regressed. fightOutcomeGate false. FA ≠ odds.
