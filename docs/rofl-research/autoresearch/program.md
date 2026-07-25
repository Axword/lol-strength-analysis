# program.md — Kill-window autoresearch (LoL strength analysis)

Karpathy-style autonomous loop adapted to **combat cross-check research**.
This is **not** nanochat training. Same discipline: fixed budget, one metric, keep/discard, repeat.

Human edits **this file**. Agent mostly edits experiment code + logs results.

---

## Objective

Get model HP trajectories + lethal timing close to real pro kills from local GRID Riot live-stats / slim SQLite / ROFL-adjacent dumps — without overfitting one fight and without claiming `calculatorReady`.

**Primary series (dev):** `artifacts/pro-grid/2970110/timeline.g1.slim.sqlite`  
**Checks:** Camille→Leona, Syndra→Camille, Ezreal→LeeSin (`docs/canvases/_data/crosschecks-2970110-g1.json`)  
**Holdout (required before any product claim):** another series under `artifacts/pro-grid/*/timeline.g*.slim.sqlite` not used for tuning.

---

## Files

| File | Role |
|------|------|
| `docs/rofl-research/autoresearch/program.md` | **This file** — goals, metrics, constraints (human-owned) |
| `scripts/crosscheck_kill_window.ts` | Baseline continuous sim + gate research (may extend) |
| `scripts/crosscheck_action_aligned.ts` | **Primary experiment file** — agent creates/modifies this |
| `docs/rofl-research/autoresearch/results.jsonl` | Append-only experiment log |
| `docs/rofl-research/autoresearch/best.json` | Best kept config + metrics |
| `docs/canvases/_data/` | Crosscheck extracts / model JSON outputs |
| `src/engine/combat.ts` / `killWindowOverlay.ts` | Product-wire unlock under `GOAL-product-wire.md` only; still never `calculatorReady` |

Data prep (do not invent HP/items):

- Slim SQLite already built via `npm run grid:riot-to-sqlite`
- Raw JSONL: `artifacts/pro-grid/events_*_*_riot.jsonl` (gitignored, local)
- ROFL files under `artifacts/pro-grid/` are for identity/pairing only in this loop unless a later experiment explicitly needs them

---

## Metric (lower composite = better)

Per experiment, run checks **01, 02, 03** on both `--segment full` and `--segment burst` when applicable.

For each check×segment compute:

- `earlyMaeHp`, `maeHp` (full window)
- `lethalErrorSec` (null if no model kill)
- `killedInModel` vs actual kill in window
- track flags: `falseAllIn`, `earlyPoisoned` (diagnostics)

**Composite score** (report all parts; optimize composite):

```
composite =
  0.35 * mean(earlyMaeHp over checks) / 100
+ 0.25 * mean(maeHp over checks) / 100
+ 0.25 * mean(|lethalErrorSec| for checks that should kill; use 5.0 if missing lethal)
+ 0.15 * latePoisonPenalty   # 1.0 if any earlyPoisoned else 0
```

**Hard fails (discard immediately even if composite looks good):**

1. Check 03 early MAE worsens by >50 vs baseline continuous sim
2. Invented HP/items/ranks (unknown → fabricated)
3. Any edit to `src/engine/combat.ts` without ship bar
4. Scrim / non-pro GRID API use
5. Setting `calculatorReady` or publishing to `public/data/matches/`

**Ship bar** (all required; still research until holdout):

- Check 02 early MAE ≪ baseline (idle/false-all-in fixed on full)
- Burst check 02: `killedInModel` true and `|lethalErrorSec| ≤ 2`
- Burst check 01: path improved; lethal honest (kill or documented miss)
- Check 03 early not hurt (>50 MAE)
- Holdout series: same ship bar directionally

Until ship bar + holdout: `shipGate: false`, no product wiring.

---

## Experiment loop (autoresearch)

Each experiment ≤ **10 minutes** wall clock (Mac OK; no GPU required).

1. Read `best.json` (if any) and last 5 lines of `results.jsonl`.
2. State hypothesis in one sentence (no user multiple-choice).
3. Edit **only** `scripts/crosscheck_action_aligned.ts` (create if missing) and optionally tiny helpers under `scripts/lib/`. Prefer extending overlays; do not touch product combat.
4. Run evaluation:

```bash
npm run test:crosscheck-sqrt
npx --yes tsx scripts/crosscheck_action_aligned.ts --suite 2970110-g1 --out docs/rofl-research/autoresearch/last_eval.json
```

5. Compute composite; append one JSON line to `results.jsonl`:

```json
{"t":"ISO-time","hypothesis":"...","keep":false,"composite":1.23,"notes":"...","path":"docs/rofl-research/autoresearch/last_eval.json"}
```

6. **Keep** only if composite < `best.json.composite` AND no hard fail → update `best.json`.
7. **Discard** code changes that lose; revert experiment file to last kept version (git checkout that file only).
8. Repeat. Do **not** ask the human to choose early vs late vs gate — pick the next hypothesis from the failure mode of the last run.

### Hypothesis queue (agent advances automatically)

Start here; skip items already beaten by `best.json`:

1. Baseline continuous `simulateMatchup` (record baseline metrics)
2. Engage gate + re-pin (already partially done — re-score into this harness)
3. **Action-aligned:** damage only on `skill_used` marks (marked point process)
4. Action-aligned + AA filler between marks using live attackSpeed (bounded)
5. CPD/CUSUM engage vs first-skill (full windows)
6. Multi-caster damage share proxy for check 03 (research only; no fake assists)
7. Holdout series evaluation of current best

Background math (do not block on reading all papers): `docs/rofl-research/crosscheck-math-systems.md`

---

## Constraints (hard)

- Research overlays only until ship bar + holdout.
- Unknown fields stay unknown.
- Pro GRID only; no scrims.
- No secrets in commits (`GRID_API_KEY`, `.env`).
- Prefer ADHD-readable logs: one table per experiment in stdout.
- tldraw boards optional; **truth = SQLite + eval JSON**.
- Do not stop after one attempt — loop until budget (human sets overnight / N experiments) or ship bar on holdout.

---

## Human kickoff prompt

See `docs/rofl-research/autoresearch/GOAL.md` — paste that entire `/goal` block into a **new** Cursor agent thread with permissions relaxed for local commands.
