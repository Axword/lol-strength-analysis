# /goal — Product-wire kill-window overlays (post research shipGate)

Copy everything below the line into a **new** Cursor chat (permissions relaxed for local commands).  
Do not micro-manage tracks — the agent follows this goal + `program.md` (amended by the **Explicit unlocks** section below).

**Prerequisite already done (do not re-baseline from zero):**  
`docs/rofl-research/autoresearch/best.json` has `shipGate: true`, composite **1.0492**, holdout **2970137-g1**.

---

```text
/autoresearch Close the remaining PRODUCT gap: wire research-proven kill-window overlays into `src/engine/combat.ts` (and thin call sites) so product map→calculator / simulateMatchup paths get idle-gate + action-aligned finishing behavior — WITHOUT claiming calibrated win odds or calculatorReady. Self-correct until product-gate eval is green and experiments are logging; do not ask me to pick tracks.

## Law & frozen research baseline (read first; do not wipe)
1. Read end-to-end:
   - `docs/rofl-research/autoresearch/program.md` (still law for metrics/hard fails)
   - `docs/rofl-research/autoresearch/best.json` (research shipGate true — frozen overlay config)
   - `docs/rofl-research/autoresearch/GOAL-product-wire.md` (this goal)
   - `docs/rofl-research/crosscheck-gap-close-status.md` (shipGate section)
   - `docs/combat-trust-boundary.md` if present
2. Research harness truth stays:
   - Dev: `artifacts/pro-grid/2970110/timeline.g1.slim.sqlite` + `docs/canvases/_data/crosschecks-2970110-g1.json`
   - Holdout: `2970137-g1-holdout` + slim-v2 with `items_json`
   - Overlay file: `scripts/crosscheck_action_aligned.ts`
   - Log: `docs/rofl-research/autoresearch/results.jsonl` (append; do not truncate)
3. Frozen BEST research config (must not regress research shipGate without beating it):
   - mode: gate_action
   - castPulseSec: 0.4
   - aaFiller: false
   - finishAaAfterLastMark: true
   - finishAaMax: 4
   - aaAtEachMark: true
   - markNearDropSec: 0.75 / markDropMinHp: 15
   - markAlwaysNearKillSec: 1.5
   - useDropConditioning: true (labeled hit-attribution; see Product rule P-anti below)
   - composite: 1.0492 ; shipGate research: true

## Explicit unlocks (THIS GOAL ONLY — paste unlocks these)
These were previously forbidden. They are NOW ALLOWED under the constraints below:

### UNLOCK-1 — `src/engine/combat.ts`
ALLOWED to edit `src/engine/combat.ts` to implement a **gated / action-aligned extended fight path** that product can call.
Also allowed: thin types in `src/engine/types.ts`, tiny pure helpers under `src/engine/` (e.g. `killWindowOverlay.ts` if cleaner), and product call-site switches that opt into the new path.
NOT a blank check: see Forbidden and Product ship bar.

### UNLOCK-2 — Product simulation API surface
ALLOWED to add opt-in options on `simulateMatchup` (or a sibling `simulateMatchupGated` / `simulateKillWindow`) such as:
- `engageSec` / `idleUntilSec` (hold defender HP flat until engage)
- `actionMarks?: { tSec, skillSlot?, share? }[]` (point-process pulses)
- `finishAa?: { afterLastMark, maxAa, aaAtEachMark }`
- `castPulseSec`
- `xhMode` stays respected; do not silently turn xH on
Default product behavior without the new options MUST remain backward-compatible (existing tests must not break unless updated intentionally for the new path).

### UNLOCK-3 — Extract overlay logic from harness into engine
ALLOWED (and preferred) to move shared mark-pulse / finish-AA / gate-idle math from `scripts/crosscheck_action_aligned.ts` into `src/engine/*`, then have the harness call the engine so research and product cannot drift.
Harness may keep SQLite I/O, suite scoring, shipChecklist, assistProbe.

### UNLOCK-4 — Engine unit/integration tests
ALLOWED to add/extend tests under `src/**` and `scripts/tests/**` that lock:
- idle early MAE on a Syndra-like false-all-in fixture
- finish lethal ±2s on Camille→Leona-like burst fixture
- no invented HP/items when pins missing
Use research extracts or minimal synthetic fixtures — never remap another match’s HP onto a real match.

### UNLOCK-5 — Research holdout tightening (still required before productShipGate)
ALLOWED to keep iterating research overlays / holdout extract selection so holdout check02-style burst lethal also lands ±2s (currently −3.56 on Cassio→Viktor under best config). Product shipGate requires this.

## Still FORBIDDEN (hard — discard / stop if violated)
1. Setting `calculatorReady: true` anywhere.
2. Publishing to `public/data/matches/` or claiming product-calibrated win odds / odds %.
3. Inventing HP, items, ranks, combat stats when unknown.
4. Fitting a single global damage multiplier / AD coeff to one kill (Camille→Leona or any one check).
5. GRID scrim / practice / tryout pulls — pro series only; local `artifacts/pro-grid/` OK.
6. Claiming pBlue/pRed are probabilities.
7. Using Obsidian/recall for this workspace.
8. Shipping drop-conditioning that peeks at the HP series being predicted as the ONLY product path — see P-anti.
9. Reverting research shipGate without a better composite + checklist (keep research bar green).

## What “close the gap” means (productShipGate)
Set `best.json.productShipGate: true` only when ALL of the following pass. Until then `productShipGate: false` even if research `shipGate` stays true.

### Product bar P0 — Parity: engine == research harness
1. With BEST config options, running product `simulateMatchup` (or sibling) on the same pins/marks as the harness reproduces 2970110-g1 checklist A1–A8 (same tolerances as research shipGate).
2. Harness `scripts/crosscheck_action_aligned.ts` uses the engine path (not a duplicated pulse implementation) for gate_action / finish AA / AA-at-mark.
3. `npm run test:crosscheck-sqrt` green; any new engine tests green; existing combat tests green or intentionally updated with rationale in results.jsonl.

### Product bar P1 — Holdout transfer (stricter than research B)
On `2970137-g1-holdout` (items required):
1. Check02-style early idle MAE ≪ that suite’s continuous baseline (same A1 rule).
2. **At least two** burst segments with `killedInModel` and `|lethalErrorSec| ≤ 2` (research B only needed one; product needs two).
3. Check03 early not hurt >50 vs continuous baseline.
4. No hard fails.

If holdout cannot hit two burst lethals honestly (assists/items/kit), document blocker in `best.json.productBlockers` and keep `productShipGate: false` — do not fake.

### Product bar P2 — Anti-circular product path (P-anti)
Product default kill-window path MUST offer a mode that does **not** select marks by looking at victim HP drops:
- Required: `markSelection: 'post_engage_killer_skills' | 'cusum_engage_then_skills'` (names flexible)
- Drop-conditioning may remain as an opt-in research/attribution mode (`markSelection: 'near_hp_drop'`) but must NOT be the product default.
- Non-drop product default must still:
  - pass A1 (idle) and A2 (check02 burst lethal ±2) on 2970110-g1
  - pass P1 holdout (two burst lethals ±2) OR document why assists make it impossible and keep productShipGate false
- Record both modes’ composites in `best.json.productModes`.

### Product bar P3 — Assist honesty
Check01 (Camille→Leona) has proven ally `skill_used` near kill (pids 9/8/7, count≈6). Product must:
1. Expose optional `allyMarks` / `allyPulseShare` (default 0 in product UI unless timeline supplies allies).
2. Never invent assists when marks absent.
3. Document in `best.json` that 1v1 without allies may underkill teamfight finishes — model edge, not odds.

### Product bar P4 — Trust / UX disclosure
1. `modelTrust` / UI copy: research-derived kill-window path is **experimental** until separate calibration study; never “win %”.
2. Dead champions still excluded from calculator imports.
3. Missing pins → refuse or degrade honestly (no fake full HP / zero items).

### Product bar P5 — Regression pack
Keep research composite on 2970110-g1 ≤ 1.15 (noise band above 1.0492) under product-backed harness, or beat it.
No check03 early hard-fail (>50 vs continuous).

## Exact remaining failure modes (work in this order; auto-advance)
### F0 — Engine extraction drift
Symptom: harness still duplicates pulse math; product cannot call it.
Fix: extract → wire harness → prove parity (P0).

### F1 — Holdout check02 burst lethal −3.56 (Cassio→Viktor)
Symptom: early MAE great; lethal outside ±2.
Fix class: finish marks / pulse / AA structure that transfers; NOT a Cassio-specific coeff.
Re-run holdout after every keep that changes finish logic.

### F2 — Product default cannot use HP-drop mark filter
Symptom: P-anti blocks ship.
Fix: non-drop mark selection + finish AA; may need CUSUM/first-skill engage; guard check03 early.

### F3 — Assist underkill on product 1v1
Symptom: Camille→Leona needs AA-at-mark to kill; allies present in truth.
Fix: optional ally share when timeline provides marks; disclose when absent.

### F4 — Test / call-site gaps
Symptom: map Send / calculator still uses continuous all-in only.
Fix: opt-in wire from map import when skill marks + engage known; leave old path default until productShipGate.

## Step-by-step execution (do all; self-correct)

### Step 0 — Setup (~5 min)
```bash
npm run test:crosscheck-sqrt
npx --yes tsx scripts/crosscheck_action_aligned.ts --suite 2970110-g1 \
  --merge-holdout docs/rofl-research/autoresearch/holdout_eval.json \
  --out docs/rofl-research/autoresearch/last_eval.json
```
Confirm composite ≈ 1.0492 and research shipGate true. If drift >0.02 composite or checklist regresses, STOP and diagnose before product edits.

### Step 1 — Extract engine API (~30–60 min)
1. Design minimal options object (UNLOCK-2). Prefer additive options on `simulateMatchup` or a clear sibling to avoid breaking callers.
2. Port gate-idle + mark pulses + finish AA + AA-at-mark from harness into engine (UNLOCK-1/3).
3. Point harness gate_action path at engine.
4. Re-run Step 0 smoke; composite must stay ≈1.0492; append results line.
5. Keep only if parity holds; else revert engine + harness to last green.

### Step 2 — Engine tests (~20–40 min)
Add fixtures/tests for idle gate + finish lethal. Green before Step 3.

### Step 3 — Product default = non-drop marks (P-anti) (~30–90 min)
1. Implement `post_engage_killer_skills` (and optional CUSUM engage) as product default mark selection.
2. Drop filter remains research opt-in only.
3. Tune finish AA / near-kill keep / per-slot pulse (disclosed constants, not fit-to-one-kill) until:
   - 2970110 A1+A2+A4 still pass on product default mode
   - check03 early hard-fail clean
4. Log each experiment ≤10 min wall clock; keep/discard vs composite + checklist.

### Step 4 — Holdout P1 (≥2 burst lethals) (~30–60 min)
1. Re-eval `2970137-g1-holdout` on product default mode.
2. If only one burst lethal ±2: experiment finish-window / AA / re-pin-each-mark / small ally share only when assistProbe>0.
3. If items missing on a series: reconvert via `npm run grid:riot-to-sqlite` from local riot JSONL; pro-only.
4. Update `best.json.holdout` + `productShipGate` false until two burst lethals pass.

### Step 5 — Call-site opt-in (~20–40 min) — only after P0+P1+P2 green on eval
Wire map/calculator import to pass marks+engage into the new path when:
- timeline has skill_used for selected killer
- HP/combat/ranks known for selected living units
Else keep continuous path + disclose.
Do not enable by default in UI until `productShipGate: true`.

### Step 6 — Freeze (~15 min)
Update:
- `docs/rofl-research/autoresearch/best.json` → `productShipGate`, `productModes`, `productBlockers`
- `docs/rofl-research/crosscheck-gap-close-status.md` → “productShipGate” section
- `docs/rofl-research/autoresearch/program.md` only if metric/law needs a one-line amendment (human-owned; keep short)
Final verify commands below.

## Autoresearch loop rules
- ≤10 minutes wall clock per experiment.
- Metric: research composite + product checklist (P0–P5); keep if no hard fail AND (composite ≤ best+noise OR product checklist gains required items without regressing required passes).
- Append every run to `results.jsonl`.
- Revert discarded code (git checkout specific files) when a keep fails.
- Never ask human early vs late vs gate — advance from failure mode F0→F4.
- Do not stop after one experiment. Session target: productShipGate true OR N≥8 new experiments with blockers documented.

## Hypothesis queue (auto-advance)
1. Extract gate+pulses+finishAA into engine; harness parity.
2. Product default non-drop marks + finish AA; restore A1/A2/A4 on 2970110.
3. Holdout two burst lethals ±2 (finish / re-pin / assist share if assistProbe>0).
4. Per-slot pulse table (disclosed) if finish still short — no AD mult fit.
5. CUSUM engage only if idle regressions return.
6. Opt-in call-site behind productShipGate.
7. Freeze docs + best.json.

## Done when
- `npm run test:crosscheck-sqrt` green
- Engine/harness parity on 2970110 (research shipGate still true)
- `productShipGate: true` in best.json OR honest blockers listed (assists/items/kit) with productShipGate false
- Holdout 2970137 eval JSON refreshed
- Final message includes: research composite, productShipGate, P0–P5 pass/fail, kept vs discarded, explicit “calculatorReady still false”

## Verify
```bash
npm run test:crosscheck-sqrt
npx --yes tsx scripts/crosscheck_action_aligned.ts --suite 2970110-g1 \
  --merge-holdout docs/rofl-research/autoresearch/holdout_eval.json \
  --out docs/rofl-research/autoresearch/last_eval.json
npx --yes tsx scripts/crosscheck_action_aligned.ts --suite 2970137-g1-holdout \
  --out docs/rofl-research/autoresearch/holdout_eval.json
# plus whatever test script you add for engine kill-window path, e.g.:
# npm test -- kill-window   # or project-equivalent
```

## Final message MUST include
1. research composite + research shipGate (must stay true)
2. productShipGate true/false
3. P0–P5 checklist
4. whether product default is non-drop (P-anti)
5. holdout burst lethals count (±2)
6. kept vs discarded this session
7. explicit: calculatorReady false; no public/data/matches publish
```
