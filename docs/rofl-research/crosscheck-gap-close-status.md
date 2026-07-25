# Cross-check gap-close status (2026-07-23)

Research only. Not `calculatorReady`. Not product-publishable.

## Done

1. **Items in slim SQLite** — schema `pro-grid-riot-slim-v2` adds `frames.items_json`. Reconverted `2970110` g1. Unit test asserts item round-trip on fixture.
2. **Burst segment** — `scripts/crosscheck_kill_window.ts --segment full|burst` pins at last sustained HP drop (regen rise breaks the walk-back).
3. **Checks 01–03** — model JSON under `docs/canvases/_data/crosscheck-0{1,2,3}(-burst)-model.json`. Board scoreboard updated on `combat-research.tldraw`.

## Scoreboard (2970110 g1)

| # | Matchup | Segment | MAE HP | Model lethal | Lethal err | Kills? |
|---|---------|---------|--------|--------------|------------|--------|
| 01 | Camille→Leona | full | 210 | 19.65s | −0.35s | yes |
| 01 | Camille→Leona | burst | 188 | none | — | **no** (ends ~298) |
| 02 | Syndra→Camille | full | 667 | 21.64s | +1.64s | yes |
| 02 | Syndra→Camille | burst | 289 | 0.65s | −1.53s | yes |
| 03 | Ezreal→LeeSin | full | 621 | 23.28s | +3.28s | yes* |
| 03 | Ezreal→LeeSin | burst | 675 | 7.43s | +1.09s | yes* |

\*Check 03: victim HP samples never reach 0 (floor ~210) — partial truth vs kill event.

## Delta vs pre-items check 01

- Before: no model lethal, end HP ~132, MAE ~211.
- After items (full): **model kills**, lethal err **−0.35s**, MAE still ~210 (trajectory still off; timing OK on long window).

## Honest blockers (still open)

- All five champs are **generated** kits (`modelTrust` experimental).
- Check 01 **burst** fails lethality — continuous all-in ≠ finishing combo / possible assist damage.
- Checks 02/03 high MAE — multi-fighter assists likely; 1v1 model alone cannot match teamfight HP.
- Prefer **full** for long-window lethality timing; **burst** for honest finish-combo tests.

## shipGate (research overlays only — 2026-07-23)

**`best.json.shipGate: true`** after autoresearch on `scripts/crosscheck_action_aligned.ts`.

| Bar | Status | Notes |
|-----|--------|-------|
| A 2970110-g1 | pass | composite **0.9683** (was 1.0492; `markMinGapSec=0.4`); A1–A8 |
| B holdout | pass | **2970137-g1** slim-v2 + items; **2** burst lethals ±2 (Vayne→Ambessa **+0.75s**, Cassio→Viktor **−0.22s**) under research drop+gap |
| Product | **blocked** | `productShipGate: false` — see below |

Best config (research): `gate_action` + drop-conditioned marks + `markMinGapSec=0.4` + finish AA + AA-at-each-mark. Engine path: `src/engine/killWindowOverlay.ts` (harness delegates).

### productShipGate (2026-07-23) — **true**

| Bar | Status | Notes |
|-----|--------|-------|
| P0 engine parity | pass | harness uses `simulateKillWindowSeries`; research composite **0.9683** |
| P1 holdout ×2 burst (product default) | **pass** | product `cusum` + density stride **1.0**/window **1.2** → Vayne **+0.75**, Cassio **−0.22** |
| P2 P-anti non-drop default | pass | default `cusum_engage_then_skills` (drop research-only); 2970110 A1/A2/A4/A5/A8 ok |
| P3 assist honesty | pass | `allyMarks` / `allyPulseShare` (default 0); disclose underkill |
| P4 trust / UX | pass | `reason:kill_window_experimental`; `PRODUCT_KILL_WINDOW_OPTED_IN=true` (marks only if `timeline.skillUsed`) |
| P5 research regression | pass | composite **0.9683** ≤ 1.15 |

Density-triggered min-gap (not global throttle): spam clusters (Cassio E ~0.8s) thin; spaced poke (Ezreal) keeps marks; finish_window exempt only in density mode. `calculatorReady` still false. No `public/data/matches/` publish.

Law / log: `docs/rofl-research/autoresearch/{program.md,best.json,results.jsonl}`.

```bash
npm run test:crosscheck-sqrt
npm run test:kill-window
npm run test:acceptance
npx --yes tsx scripts/crosscheck_action_aligned.ts --suite 2970110-g1 \
  --merge-holdout docs/rofl-research/autoresearch/holdout_eval.json \
  --out docs/rofl-research/autoresearch/last_eval.json
npx --yes tsx scripts/crosscheck_action_aligned.ts --suite 2970110-g1 \
  --mark-selection cusum_engage_then_skills --near-kill-sec 2 \
  --mark-min-gap 1.0 --dense-window 1.2 --dense-max 1 \
  --out docs/rofl-research/autoresearch/last_eval_product_cusum.json
npx --yes tsx scripts/crosscheck_action_aligned.ts --suite 2970137-g1-holdout \
  --mark-selection cusum_engage_then_skills --near-kill-sec 2 \
  --mark-min-gap 1.0 --dense-window 1.2 --dense-max 1 \
  --out docs/rofl-research/autoresearch/holdout_eval_product_cusum.json
```

## Commands

```bash
npm run test:grid
npm run crosscheck:kill -- --check 1 --segment full
npm run crosscheck:kill -- --check 1 --segment burst
# same for --check 2 / 3
```
