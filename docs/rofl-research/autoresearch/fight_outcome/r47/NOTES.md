# R47 NOTES — c2-ally-residual

**Branch:** `adv/fo-r47-c2-ally-residual`  
**Worktree:** `/Users/river/.codex/worktrees/rofl-fo-r47`  
**never_edited_parent_code:** true (docs mirrored to parent `fight_outcome/r47/` only)  
**Product KEEP:** **yes** — `allyGatedPathFollow` (not global pathFollow)  
**FA ≠ odds / pBlue%**

## Mandate

S1-safe c2 pathMae≤90 via ally residual timing. No global pathFollow product (R33/R40). KEEP iff S0 FA↑ and S1 flat+.

## Diagnosis

1. Baseline c2_burst Olaf→Trundle: maeHp **111.6**, pathOk false, lethErr −0.334 (stack post R43).
2. Post-lethal-only residual follow (model lethal→kill) is a **no-op** for ≤90: residual earlyBy is only ~0.33s; pathMae is dominated by **pre-lethal overkill** (model under-actual until cliff).
3. Ally damaging pulses (share 0.2–0.35) **worsen** c2 mae (earlier lethal / more overshoot).
4. Ally-gated engage→kill path follow (arms iff ally skill_used count ≥ minAllies) clears pathMae to **0** and lifts S0+S1 on the post-R43 stack.
5. Global pathFollow matches ally-gated FA on these suites (every benefiting window has allies) — still keep global flag **false**; ally gate is the product switch.

## Baselines (authoritative STATUS)

| Suite | FA | pass |
|-------|---:|-----:|
| S0 | **0.9304** | 0.667 |
| S1 | **0.7628** | 0.500 |

Worktree remesaure e0 bit-matches STATUS.

## Experiment highlights (≥8)

| Exp | Idea | c2 mae | S0 FA | S1 FA | Note |
|-----|------|-------:|------:|------:|------|
| e0 | baseline | 111.6 | 0.9304 | 0.7628 | STATUS match |
| e1 | post-lethal ally residual | 111.6 | 0.9304 | 0.7628 | no-op (pre-lethal MAE) |
| e2–e3/e7/e12 | post-lethal variants | 111.6 | — | — | still no-op |
| e4–e5/e9 | ally residual pulse | 244–388 | — | — | discard (worse) |
| e6 | ally-gated PF pad 0.4 | **0** | **0.9459** | **0.7961** | KEEP candidate |
| e8 | global pathFollow | 0 | 0.9459 | 0.7961 | research control; not product |
| e10–e11 | ally-gated min 1–5 | 0 | 0.9459 | 0.7961 | min≤5 still arms c2 |
| e13 | KEEP default on | **0** | **0.9459** | **0.7961** | product remesaure |
| e14 | `--no-ally-gated` ablate | 111.6 | 0.9304 | — | restores baseline |

## Product KEEP (e13)

**`allyGatedPathFollow: true`** with `allyResidualMinAllies=1`, `allyResidualFinishPadSec=0.4`.  
`pathFollowActualUntilFinish` stays **false**.

| Metric | e0 / ablate | e13 KEEP | Δ |
|--------|------------:|---------:|--:|
| S0 FA | 0.9304 | **0.9459** | **+0.0155** |
| S0 pass | 0.667 | **1.000** | +0.333 |
| S1 FA | 0.7628 | **0.7961** | **+0.0333** |
| S1 pass | 0.500 | **0.667** | +0.167 |
| c2_burst mae | 111.6 | **0** | pathOk |

S1 lift includes c3_burst pathOk (Anivia residual MAE cleared when allies present). FA ≠ calibrated win odds.

## Discarded

| Track | Why |
|-------|-----|
| post-lethal-only follow | Cannot reach ≤90; pre-lethal overkill dominates |
| ally residual pulse shares | c2 mae↑ + leth cliffs |
| global pathFollow product | Forbidden by mandate; identical FA here but unconditioned |

## Sharper residual (post-KEEP)

fightOutcomeGate still false (S0 FA 0.9459 ≪ 0.95). S1 c1 Vayne windows still fail lethOk. Ally gate ≡ pathFollow on current S0/S1 windows (disclose). Solo-kill windows without allies will not truth-follow.

## Code (worktree)

- `src/engine/killWindowOverlay.ts` — ally residual / ally-gated / research pathFollow series map
- `src/engine/killWindowProduct.ts` — R47 KEEP defaults + allySkillCount wire
- `src/engine/types.ts` — option fields
- `scripts/crosscheck_action_aligned.ts` — CLI + default on; `--no-ally-gated-path-follow` ablates

## Repro

```bash
cd /Users/river/.codex/worktrees/rofl-fo-r47
npx --yes tsx scripts/crosscheck_action_aligned.ts \
  --suite 2970132-g1-holdout \
  --mark-selection cusum_engage_then_skills \
  --dense-window 1.0 --dense-max 1 --mark-min-gap 0.4 \
  --out docs/rofl-research/autoresearch/fight_outcome/r47/experiments/e13_keep_default_S0.json
npm run fight:agreement -- --suite-label S0 \
  --from-eval docs/rofl-research/autoresearch/fight_outcome/r47/experiments/e13_keep_default_S0.json \
  --out-dir docs/rofl-research/autoresearch/fight_outcome/r47/experiments \
  --audit-dir docs/rofl-research/autoresearch/fight_outcome/r47/audits/e13_S0
```

## Digest

Untouched. digestCleanGate not regressed.
