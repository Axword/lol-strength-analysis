# /goal — Autoresearch kill-window calibration

Copy everything below the line into a **new** Cursor chat. Do not micro-manage early/late — the agent follows `program.md`.

---

```text
/goal Autoresearch loop for kill-window combat calibration against local GRID Riot live-stats / slim SQLite (and ROFL only for pairing/identity). Self-correct until eval harness is green and experiments are logging; then run the experiment loop without asking me to pick tracks.

## Setup (do first, ~5 min)
1. Read `docs/rofl-research/autoresearch/program.md` end-to-end — that file is law.
2. Confirm data exists:
   - `artifacts/pro-grid/2970110/timeline.g1.slim.sqlite`
   - `docs/canvases/_data/crosschecks-2970110-g1.json`
3. Create if missing:
   - `scripts/crosscheck_action_aligned.ts` (primary experiment file)
   - `docs/rofl-research/autoresearch/results.jsonl` (empty ok)
   - `docs/rofl-research/autoresearch/best.json` with baseline after first eval
4. Smoke: `npm run test:crosscheck-sqrt` must pass.

## Autoresearch rules (Karpathy-style, adapted)
- Fixed budget: ≤10 minutes wall clock per experiment.
- Modify primarily `scripts/crosscheck_action_aligned.ts` (+ tiny `scripts/lib/*` if needed).
- Do NOT modify `src/engine/combat.ts` until ship bar + holdout in program.md.
- Metric: composite in program.md (early MAE, full MAE, lethal error, poison penalty).
- Keep only if composite improves and no hard fail; else revert the experiment file.
- Append every run to `docs/rofl-research/autoresearch/results.jsonl`.
- Never ask the human to choose “early vs late vs gate” — read last failure mode and pick the next hypothesis from program.md queue.
- Do not stop after one experiment. Continue until you hit N=8 experiments this session (or ship bar on 2970110), then stop and summarize best.json.

## Starting hypothesis queue
1. Record continuous baseline metrics (checks 01–03 × full + burst).
2. Port/score existing gate+repin into the harness.
3. Implement action-aligned damage on `skill_used` marks (marked point process).
4. Compare composite; keep/discard.
5. Iterate (AA filler, CPD engage, check03 multi-fighter proxy) as needed.
6. If a config beats baseline on ship-bar items, evaluate one holdout slim sqlite under artifacts/pro-grid/.

## Hard constraints
- Research only: never calculatorReady / never publish public/data/matches/.
- Unknown HP/combat/ranks/items stay unknown — never invent.
- GRID key pro-only; no scrim pulls.
- Anti-overfit: no single damage coefficient fit to one kill; prefer identifiable structure (casts, engage, re-pin).
- Context: docs/rofl-research/crosscheck-gate-research.md, crosscheck-math-systems.md, crosscheck-gap-close-status.md.

## Done when (this session)
- Harness runs: `npx --yes tsx scripts/crosscheck_action_aligned.ts --suite 2970110-g1`
- ≥8 experiment lines in results.jsonl OR ship-bar metrics documented in best.json
- Final message: best composite, what was kept, what failed, whether holdout was run, shipGate true/false

## Verify
```bash
npm run test:crosscheck-sqrt
npx --yes tsx scripts/crosscheck_action_aligned.ts --suite 2970110-g1 --out docs/rofl-research/autoresearch/last_eval.json
```
```
