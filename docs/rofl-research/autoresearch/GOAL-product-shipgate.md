# /goal — Force `productShipGate: true` (do not stop)

Copy everything below the line into a **new** Cursor chat (permissions relaxed for local commands).  
Do not ask the human to pick tracks. Self-correct until `best.json.productShipGate === true`.

**Prerequisite already done (do not re-baseline from zero):**
- Research `shipGate: true`, composite **0.9683**, `markMinGapSec: 0.4`
- Engine extract live: `src/engine/killWindowOverlay.ts` (harness delegates)
- Product default API exists: `cusum_engage_then_skills` (2970110 A1–A8 with `--near-kill-sec 2 --mark-min-gap 0`)
- **Only blocker for productShipGate:** holdout P1 under **non-drop** product default — Cassio→Viktor burst lethal **−3.49** (need ≥2 burst lethals ±2). Research drop path already has 2.

---

```text
/autoresearch Force productShipGate true. Do not stop until best.json.productShipGate is true OR you honestly prove it is impossible without forbidden methods (then leave productShipGate false with a sharper blocker — but exhaust the hypothesis queue first; session target N≥12 experiments). Do not ask me to pick tracks.

## Law (read first; do not wipe)
1. `docs/rofl-research/autoresearch/program.md`
2. `docs/rofl-research/autoresearch/best.json` (current freeze — research shipGate true, productShipGate false)
3. `docs/rofl-research/autoresearch/GOAL-product-wire.md` (unlocks still apply)
4. `docs/rofl-research/crosscheck-gap-close-status.md` (productShipGate section)
5. `docs/combat-trust-boundary.md`

## Frozen research baseline (must not regress)
- Dev: `artifacts/pro-grid/2970110/timeline.g1.slim.sqlite` + `docs/canvases/_data/crosschecks-2970110-g1.json`
- Holdout: `2970137-g1-holdout` + slim-v2 with `items_json`
- Engine: `src/engine/killWindowOverlay.ts` (shared pulses/finish AA/mark select)
- Harness: `scripts/crosscheck_action_aligned.ts` (must keep calling engine)
- Research BEST config:
  - mode: gate_action
  - castPulseSec: 0.4
  - finishAaAfterLastMark: true, finishAaMax: 4, aaAtEachMark: true
  - markNearDropSec: 0.75 / markDropMinHp: 15 / markAlwaysNearKillSec: 1.5
  - useDropConditioning: true (research only)
  - markMinGapSec: 0.4
  - composite: **0.9683** ; shipGate: true
- Log: append `docs/rofl-research/autoresearch/results.jsonl` (never truncate)

## Product ship bar (ALL required → productShipGate true)
### P0 — Parity (already green; keep green)
Engine == harness on research BEST; `npm run test:crosscheck-sqrt` + `npm run test:kill-window` + acceptance combat green.

### P1 — Holdout under PRODUCT DEFAULT (the failure)
On `2970137-g1-holdout` with **product default markSelection** (non-drop):
1. Check02-style early idle MAE ≪ continuous baseline
2. **≥2** burst segments with `killedInModel` and `|lethalErrorSec| ≤ 2`
3. Check03 early not hurt >50 vs continuous
4. No hard fails

Today: cusum product default gets check01 burst +0.75 (pass) and check02 Cassio→Viktor **−3.49** (fail). Research drop+gap already gets check02 **−0.22**.

### P2 — P-anti (non-negotiable)
Product default MUST be non-drop:
- `markSelection: 'cusum_engage_then_skills'` (preferred) or `'post_engage_killer_skills'`
- `near_hp_drop` research-only — must NOT be product default
- Product default must still pass 2970110 A1 + A2 (+ keep A4/A5/A8 clean)
- Record both modes in `best.json.productModes`

### P3 — Assist honesty
`allyMarks` / `allyPulseShare` (default 0); never invent assists; disclose 1v1 underkill.

### P4 — Trust
Kill-window experimental; never win %; missing pins refuse/degrade; dead excluded.
`PRODUCT_KILL_WINDOW_OPTED_IN` may flip to true ONLY after productShipGate true.

### P5 — Research regression
2970110 research composite ≤ 1.15 (prefer ≤ 0.9683+noise); no check03 early hard-fail.

## Still FORBIDDEN
1. `calculatorReady: true`
2. Publish `public/data/matches/` or claim calibrated win odds / odds %
3. Invent HP/items/ranks/combat when unknown
4. Fit a single global damage multiplier / AD coeff to one kill
5. GRID scrims / practice / tryouts
6. Claim pBlue/pRed are probabilities
7. Obsidian/recall
8. Ship drop-conditioning as the ONLY product path
9. Regress research shipGate without beating composite + checklist
10. Asking the human to choose among hypotheses

## Exact blocker to close (work this; auto-advance)
### F1★ — Product non-drop holdout check02 lethal −3.49 (Cassio→Viktor)
Symptom: model kills ~3.5s too early under cusum + all post-engage marks (mark spam / E ticks).
Research drop+markMinGap0.4 lands −0.22 — so the damage model can finish correctly when marks are thinned; product cannot peek HP drops.

**Failed already (do not repeat as-is):**
- bare `post_engage_killer_skills` → DEV check03 early hardFail (+394)
- global `markMinGap` on product cusum → breaks DEV A4 / incomplete holdout
- `markFinishHorizonSec` → DEV check03 early hardFail (+632)
- `maxKillerMarks=7` → holdout 2 lethals ±2 BUT DEV check03 early hardFail (+632)
  Root cause diagnosed: throttling away early post-engage marks makes model idle while actual poke drops → early MAE explodes on Ezreal→LeeSin.

**Tradeoff law (must respect):**
- DEV check03 needs *some* early post-engage marks to track poke (MAE).
- Holdout check02 needs *fewer / later / weaker* marks near finish to avoid early lethal.
- One global “keep last N” or “min gap everywhere” fails. Need **phase-aware** or **density-aware** non-drop rules.

## Hypothesis queue (auto-advance; do not stop after one)
1. **Density-triggered throttle:** apply `markMinGap` / `maxKillerMarks` only when killer-mark rate exceeds a disclosed threshold (e.g. >1 mark / 0.5s in a rolling window). Low-density fights (Ezreal poke spaced out, Vayne) keep all post-CUSUM marks; Cassio spam gets throttled.
2. **Per-slot pulse table (disclosed, not fit-to-one-kill):** enable `perSlotPulse` with bounded Q/W/E/R seconds; Cassio E spam pulses shorter than R. Re-check DEV A4 + holdout check02. No AD mult.
3. **Re-pin each mark (`--repin-each-mark`)** under product cusum: pins may reduce overkill if stats drift; combine with (1) if needed.
4. **Finish-AA structure only after last mark in a local cluster** (gap-defined clusters), not after every spam tick — still no HP-drop peek.
5. **Two-phase engage:** CUSUM (or first sustained skill cluster) for idle gate; mark admission = post-engage ∪ finish_window(near kill event when known). For live product without kill time, finish_window off; for crosscheck eval killOffsetSec is OK (event time ≠ HP series peek).
6. **Ally share only when assistProbe>0** on holdout segments that still underkill — never invent; if check02 is overkill not underkill, do not add allies.
7. **CUSUM param sweep (k,h)** only if idle/engage placement is wrong on holdout burst — keep DEV A1/A5.
8. **Holdout extract honesty:** if Cassio→Viktor is multi-assister and 1v1 cannot land ±2 without drop peek, document with assistProbe counts and try a *different second holdout burst* that is honestly 1v1-solvable — but you still need ≥2 burst lethals ±2 on the suite; prefer fixing check02 over swapping extracts.
9. When P1 green under product default: set `PRODUCT_KILL_WINDOW_OPTED_IN=true`, wire Send marks when timeline has `skill_used` + known pins, freeze `best.json.productShipGate=true`, update status doc.

## Step-by-step execution
### Step 0 — Smoke (~5 min)
```bash
npm run test:crosscheck-sqrt
npm run test:kill-window
npx --yes tsx scripts/crosscheck_action_aligned.ts --suite 2970110-g1 \
  --merge-holdout docs/rofl-research/autoresearch/holdout_eval.json \
  --out docs/rofl-research/autoresearch/last_eval.json
```
Confirm research composite ≈ 0.9683 and shipGate true. If drift >0.02 or checklist regresses, STOP and fix before product experiments.

### Step 1 — Reproduce product blocker (~5 min)
```bash
npx --yes tsx scripts/crosscheck_action_aligned.ts --suite 2970110-g1 \
  --mark-selection cusum_engage_then_skills --near-kill-sec 2 --mark-min-gap 0 \
  --out docs/rofl-research/autoresearch/last_eval_product_cusum.json --log-results
npx --yes tsx scripts/crosscheck_action_aligned.ts --suite 2970137-g1-holdout \
  --mark-selection cusum_engage_then_skills --near-kill-sec 2 --mark-min-gap 0 \
  --out docs/rofl-research/autoresearch/holdout_eval_product_cusum.json --log-results
```
Expect: DEV A1–A8 pass; holdout check02 burst ≈ −3.5.

### Step 2 — Implement density-aware non-drop throttle in engine (~30–60 min)
Edit `src/engine/killWindowOverlay.ts` `selectKillWindowMarks` (and harness CLI flags). Prefer:
- `markMinGapSec` active only inside high-density clusters
- OR rolling max marks per T seconds
Keep research drop path behavior unchanged when `markSelection=near_hp_drop` (research BEST must stay green).

### Step 3 — Autoresearch loop until P1 green
Each experiment ≤10 min wall clock:
1. One-sentence hypothesis
2. Edit engine/harness only as needed
3. Eval DEV product mode + holdout product mode
4. Append results.jsonl
5. Keep if: no hard fail AND (product P1 gains without losing DEV A1/A2/A4/A5/A8) AND research BEST still shipGate
6. Else revert the experiment files

**Definition of done for the loop:** product default non-drop has holdout **≥2** burst lethals ±2 AND DEV checklist A1,A2,A4,A5,A8 clean AND research composite ≤1.15.

### Step 4 — Freeze productShipGate true
Update:
- `best.json`: `productShipGate: true`, clear/resolve `productBlockers`, refresh `productModes`, holdout product paths
- `crosscheck-gap-close-status.md` productShipGate section → pass
- `PRODUCT_KILL_WINDOW_OPTED_IN = true` in `src/engine/killWindowProduct.ts`
- Wire GameReview Send to pass real `skill_used` marks when available (else continuous); never invent marks/HP
- Final verify commands below

## Autoresearch rules
- ≤10 minutes wall clock per experiment
- Append every run to results.jsonl
- Revert discarded code (git checkout specific files)
- Never ask human early vs late vs gate
- Do not stop after one experiment — continue until productShipGate true
- If after ≥12 serious attempts P1 is still impossible without drop peek or AD fit: stop with productShipGate false and a precise impossibility proof (assistProbe, mark timelines, why density throttle cannot separate check03 vs check02). Prefer success.

## Verify (must be green before claiming true)
```bash
npm run test:crosscheck-sqrt
npm run test:kill-window
npm run test:acceptance
npx --yes tsx scripts/crosscheck_action_aligned.ts --suite 2970110-g1 \
  --merge-holdout docs/rofl-research/autoresearch/holdout_eval.json \
  --out docs/rofl-research/autoresearch/last_eval.json
npx --yes tsx scripts/crosscheck_action_aligned.ts --suite 2970110-g1 \
  --mark-selection cusum_engage_then_skills --near-kill-sec 2 --mark-min-gap 0 \
  --out docs/rofl-research/autoresearch/last_eval_product_cusum.json
npx --yes tsx scripts/crosscheck_action_aligned.ts --suite 2970137-g1-holdout \
  --mark-selection cusum_engage_then_skills --near-kill-sec 2 --mark-min-gap 0 \
  --out docs/rofl-research/autoresearch/holdout_eval_product_cusum.json
```
(Adjust product CLI flags to match the kept product default config.)

## Final message MUST include
1. research composite + research shipGate (must stay true)
2. productShipGate **true** (or impossibility proof if false)
3. P0–P5 checklist
4. product default markSelection (must be non-drop)
5. holdout burst lethals count under product default (±2)
6. kept vs discarded this session
7. explicit: calculatorReady false; no public/data/matches publish
8. whether PRODUCT_KILL_WINDOW_OPTED_IN flipped true
```
