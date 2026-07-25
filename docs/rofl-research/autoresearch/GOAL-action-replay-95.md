# /goal — Action-replay 95% (every cast/AA explained)

Copy everything below the line into a **new** Cursor chat (permissions relaxed for local commands).  
Do not micro-manage tracks — the agent follows this goal + `program.md`.  
**Do not stop** until `best.json.actionReplayGate === true` **OR** you publish an impossibility proof after exhausting the queue (session target **N≥20** experiments before allowing an impossibility stop).

**Prerequisite already done (do not wipe):**  
`best.json` has research `shipGate: true`, `productShipGate: true`, composite **0.9683**.  
Those gates stay green. This goal adds a **new** gate: `actionReplayGate`.

---

```text
/autoresearch Force actionReplayGate true. Stop only when every damaging action in a trade is reconstructed with ≥95% action-coverage confidence on the defined suites — OR honestly prove impossible without forbidden methods (then leave actionReplayGate false with a sharper blocker). Exhaust the hypothesis queue first; session target N≥20 experiments. Do not ask me to pick tracks.

## The human promise this gate must earn (plain language)
Given an official pro-match riot JSONL / slim SQLite for a known kill window, the system must:
1. List every killer (and disclosed ally) damaging action in that window from logs (`skill_used`, bounded AA structure, optional item/summoner when evented).
2. Replay those actions through the engine so the model HP path + lethal timing match truth tightly enough that we can say: “we reconstructed this trade’s actions,” not merely “lethal ±2s.”
3. Report a per-window **actionCoverage** score ≥ 0.95 (definition below) with audit JSON a human can spot-check.

This is NOT “calibrated win %.” This is NOT `calculatorReady`. This IS log-grounded action replay fidelity.

## Law (read first; do not wipe)
1. `docs/rofl-research/autoresearch/program.md`
2. `docs/rofl-research/autoresearch/best.json` (freeze: research shipGate true, productShipGate true, composite 0.9683)
3. `docs/rofl-research/autoresearch/GOAL-action-replay-95.md` (this file)
4. `docs/rofl-research/crosscheck-gap-close-status.md`
5. `docs/combat-trust-boundary.md` if present
6. `docs/rofl-research/crosscheck-math-systems.md` (background only)

## Frozen baselines that MUST NOT regress
- Dev: `artifacts/pro-grid/2970110/timeline.g1.slim.sqlite` + `docs/canvases/_data/crosschecks-2970110-g1.json`
- Holdout: `2970137-g1-holdout` + slim-v2 `items_json`
- Engine: `src/engine/killWindowOverlay.ts` (shared pulses/finish AA/mark select/density)
- Harness: `scripts/crosscheck_action_aligned.ts` (must keep calling engine)
- Research BEST: gate_action + drop marks + markMinGap 0.4 → composite **0.9683**, shipGate true
- Product BEST: `cusum_engage_then_skills` + density stride 1.0 / window 1.2 → productShipGate true
- Log: append `docs/rofl-research/autoresearch/results.jsonl` (never truncate)

## New metric law — actionReplay (primary)

### Action inventory (truth side)
For each check×segment window, build `truthActions[]` from slim SQLite / riot events, sorted by time:
- `skill_used` by killer (required)
- `skill_used` by same-team allies in window (optional; disclose count; never invent if absent)
- AA proxies ONLY when structurally forced by engine finish rules already shipped (aaAtEachMark / finishAa) OR when a future experiment adds an evented AA source — never invent random AAs
- Item actives / summoners ONLY if an event row exists in the dump (else omit + disclose)

Each truth action: `{ tSec, actorPid, kind: 'skill'|'aa'|'item'|'summoner', skillSlot?, shareHint? }`

### Model inventory (replay side)
From the kill-window path, emit `modelActions[]` with the same schema (what the simulator actually applied: pulse at mark, AA-at-mark, finish AA, ally pulse).

### Matching (bipartite, greedy by time)
A truth action T matches model action M iff ALL:
1. Same actor class (killer vs ally) — ally↔ally, killer↔killer
2. Same kind (skill/aa/…)
3. If skill: same skillSlot (1–4) OR both slot-unknown
4. |T.tSec − M.tSec| ≤ **τ** where default τ = **0.25s** (disclosed; may tighten to 0.15 if data supports)
5. Each model action matches at most one truth action and vice versa

### Scores (report all; optimize actionCoverage then HP)
```
precision = matched / max(1, |modelActions|)
recall    = matched / max(1, |truthActions|)
actionCoverage = 2 * precision * recall / max(1e-9, precision + recall)   # F1
```
**Gate threshold:** `actionCoverage ≥ 0.95` on EVERY required window (below).

### Secondary (must also pass — “almost perfect” is not lethal-only)
For each required window:
1. `|lethalErrorSec| ≤ 0.5` when actual kill occurs in window; if victim HP floor never hits 0, lethal may be null BUT then `endHpAbsError ≤ 30` and disclose floor
2. `earlyMaeHp ≤ 40` (idle / pre-engage honesty)
3. `maeHp ≤ 80` on burst; `maeHp ≤ 120` on full (tighten only if already beating)
4. No hard fails from program.md (esp. check03 early >50 vs continuous)
5. Per-action audit written under `docs/rofl-research/autoresearch/action_audits/<series>-g<n>-c<check>-<seg>.json`

### Confidence wording (mandatory honesty)
“95% confidence” in this repo means **actionCoverage ≥ 0.95 (F1 of matched actions)** under the match rules above — NOT a calibrated Bayesian posterior, NOT odds, NOT win probability.  
UI/docs must say: **“action replay coverage ≥95% (log-matched)”** — never “95% sure we win.”

### Composite for this goal (lower better; secondary to coverage gate)
```
replayComposite =
  0.45 * (1 - mean(actionCoverage))
+ 0.20 * mean(earlyMaeHp) / 100
+ 0.15 * mean(maeHp) / 100
+ 0.15 * mean(|lethalErrorSec| or 2.0 if missing when kill expected)
+ 0.05 * latePoisonPenalty
```
Keep if: no hard fail AND (coverage gate gains on failing windows OR replayComposite improves) AND research/product ship gates stay green.

## Suites required for actionReplayGate true (ALL)

### S0 — Dev full suite (2970110-g1)
Checks 01, 02, 03 × full + burst → **6 windows**.  
Every window: actionCoverage ≥ 0.95 AND secondary HP/lethal bars above.

### S1 — Holdout suite (2970137-g1-holdout)
Same 6-window rule.

### S2 — Transfer suite (NEW — pick one unused pro slim under artifacts/pro-grid/)
Pick a series/game NOT used to tune density/drop (prefer another LCK/LEC/LCS public series already local).  
Build extract with ≥3 kill windows (same style as crosschecks JSON).  
Require actionCoverage ≥ 0.95 on **≥5 of 6** windows AND no window below 0.85.  
If local dumps lack a third series, convert from local riot JSONL via `npm run grid:riot-to-sqlite` (pro-only). Do NOT call GRID for scrims.

### S3 — Product path honesty
Re-score S0+S1 under product default (`cusum_engage_then_skills` + density 1.0/1.2) for lethal/HP bars already owned by productShipGate.  
Action coverage may use research mark inventory for audit, but you MUST also report coverage when marks are selected by the **product non-drop** selector (no HP-drop peek).  
`actionReplayGate` requires product-selector coverage ≥ 0.95 on S0+S1 burst windows for checks that are 1v1-solvable; teamfight windows may use disclosed ally marks from logs (still never invent).

## Still FORBIDDEN
1. `calculatorReady: true`
2. Publish `public/data/matches/` or claim calibrated win odds / odds %
3. Invent HP/items/ranks/combat/skill marks when unknown
4. Fit a single global damage multiplier / AD coeff to one kill
5. GRID scrims / practice / tryouts
6. Claim pBlue/pRed are probabilities
7. Obsidian/recall
8. Ship drop-conditioning as the ONLY product path (product default stays non-drop)
9. Regress research shipGate or productShipGate without beating their bars
10. Asking the human to choose among hypotheses
11. Claiming “95% confidence” without emitting actionCoverage + audit JSON
12. Counting unmatched finish-AA spam as success (precision must stay high — no mark/AA flood)

## Exact blockers to close (work in order; auto-advance)
### R0 — Instrumentation
Harness lacks truthActions/modelActions/actionCoverage.  
Fix: extend `scripts/crosscheck_action_aligned.ts` (+ tiny `scripts/lib/action_replay.ts`) to emit coverage + audits. Engine may emit modelActions from `simulateKillWindowSeries`.

### R1 — Skill-slot fidelity
Pulses ignore slot identity / wrong pulse length → coverage fails on Q/W/E/R sequences.  
Fix: perSlotPulse disclosed table; slot-aware matching; no per-champ coeff fit.

### R2 — AA chronology
aaAtEachMark / finishAa create model AAs with no truth twin (precision crash) OR miss real AA damage (recall crash).  
Fix: AA only when AS-period aligned to marks OR when an evented AA source exists; cluster finish AA after last mark in gap-defined clusters (product density already related).

### R3 — Multi-actor / assists
Check01-like windows: ally casts in truth; 1v1 replay under-covers.  
Fix: include ally `skill_used` from logs with disclosed `allyPulseShare` (or per-mark share); never invent allies. Coverage counts ally actions.

### R4 — DoT / poison / passive ticks
Cassio E / poison / passive HP slopes between marks — mark-only pulses leave HP MAE high even if skills match.  
Fix: disclosed DoT tick overlays tied to skill application (wiki-timed), not HP-drop peek. If impossible from events alone, document as R4 blocker with evidence.

### R5 — Item / summoner spikes
Sudden HP cliffs without skill_used (ignite, RP, Goredrinker, etc.).  
Fix: parse item/summoner events when present in slim/riot; else disclose gap and exclude that window from S2 “solvable” set only after proving no event exists.

### R6 — Re-pin drift
Long windows: AD/AP/armor drift → matched actions but HP diverges.  
Fix: `--repin-each-mark` with known frames only; measure coverage + MAE together.

### R7 — Transfer failure
S2 series fails coverage.  
Fix: do not retune to one new kill; prefer structure that keeps S0/S1 green; if kit/event gaps dominate, expand extract honesty and impossibility notes.

## Hypothesis queue (auto-advance; do not stop after one)
1. **R0 instrumentation** — emit truth/model actions + actionCoverage; freeze baseline coverage numbers for 2970110/2970137 under research BEST and product BEST (expect ≪0.95 today).
2. **Strict skill-only replay** — modelActions = pulses at selected marks only (no AA). Maximize skill recall/precision; measure AA residual as separate bucket.
3. **Slot-aware pulses** — enable perSlotPulse bounded Q/W/E/R seconds; re-score coverage.
4. **AA pairing** — allow AA-at-mark only when matching a truth AA proxy within τ; finish AA only inside last cluster; kill precision floods.
5. **Ally log share** — when assistProbe>0, attach ally marks from SQLite; tune allyPulseShare ∈ {0.2,0.35,0.5} disclosed; never invent.
6. **Re-pin each mark** — product + research; coverage must not fall.
7. **DoT tick overlay** — wiki-timed poison/DoT after applying E (Cassio-class); disclosed constants; holdout check02 HP mae must drop without wrecking coverage.
8. **Item/summoner event parse** — if rows exist in payload_json/schema; else document absence.
9. **Tighten τ 0.25→0.15** once coverage ≥0.95 at 0.25 on S0+S1.
10. **Build S2 transfer extract** + eval; keep only if S0/S1 stay green.
11. **Product-selector coverage** — same audits under cusum+density marks (no drop peek).
12. When S0+S1+S2+S3 green: set `best.json.actionReplayGate=true`, update status doc, keep calculatorReady false.

## Step-by-step execution
### Step 0 — Smoke (~5 min)
```bash
npm run test:crosscheck-sqrt
npm run test:kill-window
npm run test:acceptance
npx --yes tsx scripts/crosscheck_action_aligned.ts --suite 2970110-g1 \
  --merge-holdout docs/rofl-research/autoresearch/holdout_eval.json \
  --out docs/rofl-research/autoresearch/last_eval.json
```
Confirm research composite ≈ 0.9683 and shipGate/productShipGate still true in best.json. If research composite drifts >0.02 or checklist regresses, STOP and fix before R0 features.

### Step 1 — Baseline coverage (must log) (~15–30 min)
Implement R0. Run research + product evals. Append results with actionCoverage per check×seg. Expect many windows <0.95 — that is the starting deficit, not a keep.

### Step 2 — Autoresearch loop until gate
Each experiment ≤10 min wall clock:
1. One-sentence hypothesis (from queue / last failureMode)
2. Edit engine/harness/lib only as needed (combat.ts only if unlock still applies from GOAL-product-wire AND needed for replay emission)
3. Eval S0; if improved, S1; periodically S2
4. Append results.jsonl
5. Keep if no hard fail AND coverage/HP bars improve without regressing shipGate/productShipGate
6. Else revert the experiment files (`git checkout -- <files>`)

Definition of done for the loop:
- actionCoverage ≥ 0.95 on all S0+S1 required windows
- secondary HP/lethal bars pass
- S2 transfer rule pass
- S3 product-selector coverage pass on required bursts
- research composite ≤ 1.15 (prefer ≤ 0.9683+noise)
- productShipGate remains true

### Step 3 — Freeze actionReplayGate true
Update:
- `best.json`: `actionReplayGate: true`, `actionReplay` block with per-suite coverage tables, clear blockers
- `crosscheck-gap-close-status.md` — new actionReplayGate section
- Keep `PRODUCT_KILL_WINDOW_OPTED_IN` true only if productShipGate still true
- Do NOT set calculatorReady

### Autoresearch rules
- ≤10 minutes wall clock per experiment
- Append every run to results.jsonl
- Revert discarded code
- Never ask human early vs late vs gate vs DoT vs assists — auto-advance from failureMode R0→R7
- Do not stop after one experiment — continue until actionReplayGate true
- If after ≥20 serious attempts gate still impossible without drop peek / AD fit / inventing events: stop with actionReplayGate false and impossibility proof (which action classes lack log support; which windows are multi-assister beyond evented allies; coverage ceiling with evidence)

## Verify (must be green before claiming true)
```bash
npm run test:crosscheck-sqrt
npm run test:kill-window
npm run test:acceptance
npx --yes tsx scripts/crosscheck_action_aligned.ts --suite 2970110-g1 \
  --merge-holdout docs/rofl-research/autoresearch/holdout_eval.json \
  --out docs/rofl-research/autoresearch/last_eval.json
# plus whatever flag you add, e.g. --action-replay-audit
npx --yes tsx scripts/crosscheck_action_aligned.ts --suite 2970137-g1-holdout \
  --out docs/rofl-research/autoresearch/holdout_eval.json
# product path
npx --yes tsx scripts/crosscheck_action_aligned.ts --suite 2970110-g1 \
  --mark-selection cusum_engage_then_skills --near-kill-sec 2 \
  --mark-min-gap 1.0 --dense-window 1.2 --dense-max 1 \
  --out docs/rofl-research/autoresearch/last_eval_product_cusum.json
npx --yes tsx scripts/crosscheck_action_aligned.ts --suite 2970137-g1-holdout \
  --mark-selection cusum_engage_then_skills --near-kill-sec 2 \
  --mark-min-gap 1.0 --dense-window 1.2 --dense-max 1 \
  --out docs/rofl-research/autoresearch/holdout_eval_product_cusum.json
# S2 transfer suite command you define after extract exists
```

## Final message MUST include
1. research composite + research shipGate (must stay true)
2. productShipGate (must stay true)
3. actionReplayGate true/false
4. per-suite mean actionCoverage + worst window
5. S0/S1/S2/S3 pass/fail table
6. whether “95%” is actionCoverage F1 (yes) — explicit non-probability disclaimer
7. kept vs discarded this session
8. explicit: calculatorReady false; no public/data/matches publish
9. if false: impossibility proof with action-class gaps (DoT/item/AA/ally)
```
