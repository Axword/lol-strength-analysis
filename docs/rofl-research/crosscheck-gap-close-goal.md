# /goal — Cross-check gap close (items + segment + checks 02/03)

Copy everything below the line into a chat as `/goal …`, or run in-place after this file is written.

---

```text
/goal Close the Camille→Leona calibration gap and extend to checks 02/03. Self-correct until targeted checks/tests pass. Use tldraw board docs/canvases/combat-research.tldraw for YOU:/MARI:/AGENT: notes (readable text — no literal \n). Prefer slim SQLite under artifacts/pro-grid/.

## Context
- Check 01 (Camille→Leona) model MAE ~211 HP, no model lethal; actual kill @ 15s.
- Likely gaps: missing items in slim frames, generated kits, continuous all-in vs real disengage/regen.
- Rule: ≥3 cross-checks/game; Phase A = near-perfect on 3 games; then scale; then holdout.
- Engine: simulateMatchup via scripts/crosscheck_kill_window.ts / docs/canvases/_data/crosscheck-01-model.json.
- Board is a view; engine + SQLite are truth. Never calculatorReady / never publish to public/data/matches/.

## Do all three (in order)

### 1) Items into slim path
1. Find where GRID Riot live-stats / end-state exposes item IDs (frames items[], or end_state / game_info).
2. Extend scripts/grid_riot_events_to_rfc461.py slim SQLite:
   - Prefer `frames.items_json` (array of item ids per sample) OR a compact `items` table keyed by (game_time_ms, participant_id).
   - Keep unknown as NULL/empty — never invent items.
3. Reconvert at least 2970110 g1; refresh crosschecks-2970110-g1.json so killer/victim start frames carry itemIds.
4. Re-run check 01 model; record MAE / lethal delta vs previous (~211 / no lethal).
5. Unit test: fixture asserts items round-trip when present; absent stays empty.

### 2) Segment the fight (burst window)
1. From actual victim HP series, detect the final lethal burst (e.g. last sustained HP drop into 0, ignore mid-window regen rises).
2. Add `--segment burst|full` (or auto) to crosscheck_kill_window.ts:
   - `full` = current whole window
   - `burst` = pins at burst start (HP/combat/ranks/items) through kill
3. Run check 01 with burst segment; compare lethal timing + MAE to full.
4. Document on board: which segment wins for calibration (honest numbers).

### 3) Checks 02 and 03
1. Run the same pipeline (items if available + full and burst) for:
   - 02 Syndra→Camille @ 1089.2s
   - 03 Ezreal→LeeSin @ 1649.4s (note: short window may not show HP 0 — extend post-kill sample or mark partial)
2. Write docs/canvases/_data/crosscheck-02-model.json and crosscheck-03-model.json.
3. Update tldraw: status on xcheck1/2/3 cards + AGENT note with a 3-row scoreboard (MAE, modelLethal, actualKill, segment).
4. Do NOT claim success if model still misses — record blockers (items still missing, kit tier, multi-fighter assist, etc.).

## Verify
```bash
npm run test:grid
npx --yes tsx scripts/crosscheck_kill_window.ts --input docs/canvases/_data/crosschecks-2970110-g1.json --check 1 --out docs/canvases/_data/crosscheck-01-model.json
# plus check 2 and 3; burst flag once implemented
```
Board lint clean enough to read (no literal \\n in notes). Leave AGENT: sticky summarizing the 3-check scoreboard.

## Hard constraints
- Unknown items/HP/combat/ranks stay unknown.
- pBlue/pRed are model edge, not odds %.
- No scrim GRID pulls; no secrets committed.
- Prefer smallest change; extend existing slim sqlite + crosscheck script.

## Done when
- Slim sqlite can carry items when present on the wire.
- Check 01 has full + burst comparison numbers.
- Checks 01–03 have model JSON + board scoreboard.
- Honest blockers written (board AGENT note + short update in docs/rofl-research/combat-math-tldraw-goal.md or sibling).
```

**Status (2026-07-23):** completed — see `docs/rofl-research/crosscheck-gap-close-status.md`.
