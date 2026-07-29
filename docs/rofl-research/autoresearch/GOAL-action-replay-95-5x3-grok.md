# /goal — Action-replay 95% (5×3 Grok-only rematch)

Copy everything below the line into a **new** Cursor chat (permissions relaxed for local commands).  
Orchestrator + all runners + all reviewers must use **only** model `cursor-grok-4.5-high-fast` (Grok 4.5 high-fast). Do **not** use Sonnet/Opus/GPT for this run.

**Do not stop** until `best.json.actionReplayGate === true` **OR** you publish a sharper impossibility proof after exhausting the queue below (session target **N≥20** experiments **per runner** before allowing an impossibility stop).

**Prerequisite (do not wipe):**  
`best.json` has research `shipGate: true`, `productShipGate: true`, composite **0.9683**.  
Prior 5×3 session (Sonnet) agreed **`actionReplayGate: false`** with **partial** impossibility — AA/item-active event gaps proven; ally model marks + AA pairing + pulse time-scaling still open. This rematch continues that gate; it does not reset ship gates.

---

```text
/autoresearch 5×3 Grok-only rematch. Force actionReplayGate true. Stop only when every damaging action in a trade is reconstructed with ≥95% action-coverage confidence on the defined suites — OR honestly prove impossible without forbidden methods (then leave actionReplayGate false with a sharper blocker). Exhaust the hypothesis queue first; session target N≥20 experiments per runner. Do not ask me to pick tracks.

## Orchestration law (mandatory — parent agent)
Use exactly this shape. Model for EVERY Task/subagent call: `cursor-grok-4.5-high-fast` only. Never Sonnet/Opus/GPT.

### Phase A — 5 adversarial runners (parallel, isolated)
Launch 5 `generalPurpose` subagents (NOT best-of-n-runner — that previously collided on the parent checkout). Each runner gets:
1. Its own git branch + worktree under `~/.codex/worktrees/action-replay-grok-r{N}/`
2. Branch names:
   - R1 `adversarial/ar95-grok-r1-skill-aa` — skill/AA pairing honesty (no zero-dmg log-echo as gate evidence)
   - R2 `adversarial/ar95-grok-r2-ally-model` — ally model marks + windowed ally truth together
   - R3 `adversarial/ar95-grok-r3-solvable-set` — AA-only / empty-truth window solvable-set exclusion + S2 honesty
   - R4 `adversarial/ar95-grok-r4-slot-dot` — slot-aware mark retention so DoT/poison can fire; Ignite already proven
   - R5 `adversarial/ar95-grok-r5-pulse-shipbar` — only if a NEW disclosed ship bar allows it: time-scaled cast pulses (combat.ts); else document blocker and advance other tracks
3. HARD isolation: ALL edits/evals/git only inside that worktree. FORBIDDEN to edit `/Users/river/Projects/lol-strength-analysis`. Parent stays on `feat/grid-riot-livestats-rfc461` (or current feature branch). Verify `pwd` + `git branch` before first edit.
4. Seed each worktree once from parent (rsync code/docs; symlink `artifacts/pro-grid` + `node_modules` read-only). Prefer starting from prior R2 instrumentation if present at `~/.codex/worktrees/action-replay-r2` (copy `scripts/lib/action_replay.ts` + modelActions emission) — rebuild R0 if missing.
5. Each runner does the FULL goal loop (smoke → queue → S0/S1/S2/S3) with its adversarial angle first, then auto-advances. N≥20 experiments each. Append `results.jsonl` in THEIR worktree only.

### Phase B — wait until all 5 finish
Do not launch reviewers early. If a runner dies on API limit, relaunch THAT runner on `cursor-grok-4.5-high-fast` only.

### Phase C — 3 adversarial reviewers (must agree)
After all 5 finish, launch 3 reviewers on `cursor-grok-4.5-high-fast`:
- A gate skeptic — try to find a true path OR prove false
- B evidence/metric auditor — audit F1 honesty; reject zero-damage log-echo as gate evidence
- C consolidation judge — fill GOAL Final message fields; pick best consolidation branch

Reviewers are READ-ONLY. They must AGREE on `actionReplayGate` true|false. If they disagree on the gate bit, relaunch a fourth tie-break reviewer on the same model with both votes. Secondary dissent (e.g. which branch to merge) may be noted but must not block the gate vote.

### Phase D — parent final message
Parent emits the Final message (below). Do NOT merge into parent unless the human later asks. Keep `calculatorReady` false.

## The human promise this gate must earn (plain language)
Given an official pro-match riot JSONL / slim SQLite for a known kill window, the system must:
1. List every killer (and disclosed ally) damaging action in that window from logs (`skill_used`, bounded AA structure, optional item/summoner when evented).
2. Replay those actions through the engine so the model HP path + lethal timing match truth tightly enough that we can say: “we reconstructed this trade’s actions,” not merely “lethal ±2s.”
3. Report a per-window **actionCoverage** score ≥ 0.95 (definition below) with audit JSON a human can spot-check.

This is NOT “calibrated win %.” This is NOT `calculatorReady`. This IS log-grounded action replay fidelity.

## Law (read first; do not wipe)
1. `docs/rofl-research/autoresearch/program.md`
2. `docs/rofl-research/autoresearch/best.json` (freeze: research shipGate true, productShipGate true, composite 0.9683)
3. `docs/rofl-research/autoresearch/GOAL-action-replay-95-5x3-grok.md` (this file)
4. `docs/rofl-research/autoresearch/GOAL-action-replay-95.md` (metric law background)
5. `docs/rofl-research/crosscheck-gap-close-status.md`
6. `docs/combat-trust-boundary.md` if present

## Frozen baselines that MUST NOT regress
- Dev: `artifacts/pro-grid/2970110/timeline.g1.slim.sqlite` + `docs/canvases/_data/crosschecks-2970110-g1.json`
- Holdout: `2970137-g1-holdout` + slim-v2 `items_json`
- Transfer S2: prefer `2970120` + `docs/canvases/_data/crosschecks-2970120-g1-holdout.json`
- Engine: `src/engine/killWindowOverlay.ts` (shared pulses/finish AA/mark select/density)
- Harness: `scripts/crosscheck_action_aligned.ts` (must keep calling engine)
- Research BEST: gate_action + drop marks + markMinGap 0.4 → composite **0.9683**, shipGate true
- Product BEST: `cusum_engage_then_skills` + density stride 1.0 / window 1.2 → productShipGate true
- Log: append `docs/rofl-research/autoresearch/results.jsonl` in the runner worktree (never truncate)

## Prior-session ceilings (start from honesty, do not claim as done)
- Baseline instrumentation-only S0 mean coverage ≈ 0.51
- Best prior lift with zero-damage log-echo ≈ 0.77 — **does NOT earn the gate** and does NOT count toward the human promise (modelActions must be what the simulator actually applied as damaging actions)
- Slim SQLite: has `skill_used` + `summoner_spell_used`; **no AA events**; item rows are purchase/sell/destroy only (no active-use)
- S2 AA-only kills can yield F1=0 under empty truth — disclose solvable-set rules before gaming the denominator

## Metric law — actionReplay (primary)
Same as `GOAL-action-replay-95.md`:
- truthActions / modelActions schema
- bipartite greedy match: actor class, kind, skillSlot, |Δt|≤τ (default 0.25s)
- actionCoverage = F1
- Gate: actionCoverage ≥ 0.95 on EVERY required S0+S1 window; S2 ≥5/6 ≥0.95 and none <0.85; S3 product-selector coverage on required bursts
- Secondary HP/lethal bars unchanged (lethal |err|≤0.5 when kill expected; earlyMae≤40; burst mae≤80; full mae≤120; no program.md hard fails)
- Audits under `docs/rofl-research/autoresearch/action_audits/`
- “95%” = actionCoverage F1 only — never win probability

### Honesty amendments from prior reviewers (binding)
1. Zero-damage `logOnlyReplay` / ghost modelActions may be logged as a diagnostic, but **cannot** be used to claim gate progress or “reconstructed this trade.”
2. Do not freeze a new research composite unless ship checklist stays green AND coverage/HP bars improve without forbidden methods.
3. Full impossibility requires exhausting the queue below — AA/item schema gaps alone are **partial**, not a stop.

## Suites (unchanged)
- S0: 2970110-g1 — 6 windows, all ≥0.95 + secondary bars
- S1: 2970137-g1-holdout — same
- S2: 2970120 (or unused pro slim) — ≥5/6 ≥0.95, none <0.85
- S3: product `cusum_engage_then_skills` + density 1.0/1.2 — product-selector coverage ≥0.95 on required S0+S1 bursts for 1v1-solvable checks

## Still FORBIDDEN
1. `calculatorReady: true`
2. Publish `public/data/matches/` or claim calibrated win odds
3. Invent HP/items/ranks/combat/skill/AA/item-active events
4. Global AD/damage coeff fit to one kill
5. GRID scrims / practice / tryouts
6. Claim pBlue/pRed are probabilities
7. Obsidian/recall
8. Drop-conditioning as the ONLY product path
9. Regress research shipGate or productShipGate
10. Asking the human to choose among hypotheses
11. Claiming “95% confidence” without actionCoverage + audit JSON
12. Unmatched finish-AA spam counted as success
13. Editing the parent repo from a runner (isolation break)
14. Using any model other than `cursor-grok-4.5-high-fast` for runners/reviewers

## Hypothesis queue (auto-advance; do not stop after one)
1. R0 baseline freeze — confirm actionCoverage emission works; log S0/S1/S2/S3 under research BEST + product BEST (expect ≪0.95).
2. Damaging skill-only inventory — modelActions = applied pulses only (no AA, no zero-dmg ghosts); measure AA residual separately.
3. AA pairing without inventing truth — emit model AA only when AS-period aligned AND accept unmatched AA as precision cost; OR cluster finish AA; never invent AA events. Optimize F1+lethal together.
4. Ally model marks — when assistProbe>0, emit ally pulses from log `skill_used` (windowed near-kill, team_id checked) with allyPulseShare ∈ {0.2,0.35,0.5}; truth+model both count.
5. Solvable-set disclosure — windows with zero killer skill_used (AA-only) excluded from S2 “solvable” set only after proving no skill rows; report separately.
6. Slot-aware mark retention — keep Q/W/E/R diversity under density/drop so Cassio-class DoT can attach; disclosed constants; no HP-drop peek for DoT.
7. Summoner/item — Ignite (`summoner_spell_used`) when evented; item-actives stay impossible-from-schema unless new event class appears.
8. Re-pin each mark — known frames only; coverage must not fall.
9. Product-selector coverage (S3) under non-drop marks — same audits.
10. τ 0.25→0.15 only after S0+S1 ≥0.95 at 0.25.
11. Optional combat.ts pulse time-scaling — ONLY under a new disclosed ship bar that does not regress composite/shipGate/productShipGate; otherwise document as blocked and continue.
12. When S0+S1+S2+S3 green: set `actionReplayGate=true` in that worktree’s best.json; reviewers must confirm before parent reports true.

## Step-by-step (parent)
### Step 0 — Smoke on parent (~5 min)
```bash
npm run test:crosscheck-sqrt
npm run test:kill-window
npm run test:acceptance
npx --yes tsx scripts/crosscheck_action_aligned.ts --suite 2970110-g1 \
  --merge-holdout docs/rofl-research/autoresearch/holdout_eval.json \
  --out docs/rofl-research/autoresearch/last_eval.json
```
Confirm composite ≈ 0.9683 and shipGate/productShipGate true. If drift >0.02, STOP and fix before launching runners.

### Step 1 — Create 5 worktrees + launch 5 Grok runners
Create branches/worktrees as named above. Launch all 5 in parallel with model `cursor-grok-4.5-high-fast`. Pass full isolation paths in each prompt.

### Step 2 — On each completion notification
Verify that runner did not touch parent. Do not launch reviewers until 5/5 done. Relaunch failed runners on the same Grok model.

### Step 3 — Launch 3 Grok reviewers; require gate agreement
### Step 4 — Emit Final message (parent)

## Verify (green before claiming true)
```bash
# inside the winning worktree
npm run test:crosscheck-sqrt
npm run test:kill-window
npm run test:acceptance
npx --yes tsx scripts/crosscheck_action_aligned.ts --suite 2970110-g1 \
  --merge-holdout docs/rofl-research/autoresearch/holdout_eval.json \
  --out docs/rofl-research/autoresearch/last_eval.json
npx --yes tsx scripts/crosscheck_action_aligned.ts --suite 2970137-g1-holdout \
  --out docs/rofl-research/autoresearch/holdout_eval.json
npx --yes tsx scripts/crosscheck_action_aligned.ts --suite 2970110-g1 \
  --mark-selection cusum_engage_then_skills --near-kill-sec 2 \
  --mark-min-gap 1.0 --dense-window 1.2 --dense-max 1 \
  --out docs/rofl-research/autoresearch/last_eval_product_cusum.json
npx --yes tsx scripts/crosscheck_action_aligned.ts --suite 2970137-g1-holdout \
  --mark-selection cusum_engage_then_skills --near-kill-sec 2 \
  --mark-min-gap 1.0 --dense-window 1.2 --dense-max 1 \
  --out docs/rofl-research/autoresearch/holdout_eval_product_cusum.json
# S2 command as defined after extract exists
```

## Final message MUST include
1. research composite + research shipGate (must stay true)
2. productShipGate (must stay true)
3. actionReplayGate true/false
4. per-suite mean actionCoverage + worst window (cite winning runner)
5. S0/S1/S2/S3 pass/fail table
6. whether “95%” is actionCoverage F1 (yes) — explicit non-probability disclaimer
7. kept vs discarded this session
8. explicit: calculatorReady false; no public/data/matches publish
9. if false: impossibility proof with action-class gaps (DoT/item/AA/ally) OR remaining tracks if not exhausted
10. model used: cursor-grok-4.5-high-fast for all 5+3; confirmation no other models
11. reviewer agreement: A/B/C gate votes
```

## Kickoff one-liner (paste as first user message after the block, optional)

```text
Read docs/rofl-research/autoresearch/GOAL-action-replay-95-5x3-grok.md and run the full 5×3 Grok-only orchestration. Model cursor-grok-4.5-high-fast only. Isolate each runner. Do not ask me to pick tracks.
```
