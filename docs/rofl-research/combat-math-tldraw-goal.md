# /goal — Combat math ×3 + tldraw offline boards

Copy everything below the line into a new chat as `/goal …`.

---

```text
/goal Build all three combat-math research slices against slim GRID SQLite, with tldraw Offline boards as the development visualization layer. Self-correct until targeted tests pass.

## Dev visualization (do first, ~10 min)
1. Ensure tldraw Desktop is running (`~/Library/Application Support/tldraw/server.json`).
2. Follow `docs/canvases/README.md`. User (or agent) opens/saves:
   - `docs/canvases/combat-research.tldraw` (overview)
   - `docs/canvases/kill-window-1v1.tldraw`
   - `docs/canvases/regen-extended-fight.tldraw`
   - `docs/canvases/xh-utility.tldraw`
3. Smoke: `sh "$HOME/skills/tldraw-offline/tq" POST /api/search 'return await api.getDocs()'`
4. For each slice: dump a tiny JSON extract from
   `artifacts/pro-grid/2970110/timeline.g1.slim.sqlite` into
   `docs/canvases/_data/` → draw via `tldraw-offline` (`/exec` or durable script).
5. Canvas is a VIEW only. Source of truth = SQLite + engine code. Never invent HP/combat/ranks.

## Hard constraints
- Prefer `timeline.*.slim.sqlite` over fat JSONL/ROFL for research windows.
- Do not claim `calculatorReady` / do not publish to `public/data/matches/`.
- Do not downsample frame rate to “fit” the board — subsample windows in time, keep native density in data.
- Utility abilities with 0 base damage must still affect AA counts / xH / kite (Nasus W, etc.).
- pBlue/pRed stay model edge, not calibrated odds %.
- Use existing engine paths (`src/engine/…`) — extend, don’t fork a parallel combat model.
- tldraw ≠ product UI; ≠ Cursor `.canvas.tsx`.

## Slice 1 — Calibrate 1v1 damage vs kill window
1. Pick one champion_kill from 2970110 sqlite (killer/victim PUUIDs, t_ms).
2. Extract ±N seconds of frames for those two pids (HP, combat, ranks, positions).
3. Run existing timed planner / damage path; compare predicted lethal time vs actual kill.
4. Write audit notes (assumptions, omit/stop reasons) + tldraw board: time axis, HP bars, ability→AA markers, lethal tick.
5. Unit/fixture test on the extract JSON (no secrets; small).

## Slice 2 — Extended fight + resource regen
1. Pick a longer multi-engage window (same match or second kill) where HP regenerates between bursts.
2. Model regen (healthRegen from frames when present; else wiki/disclosed prior — never fake zeros as known).
3. Compare model HP trajectory to sqlite frames; board shows actual vs model curves + error band.
4. Tests for regen tick math + one regression fixture.

## Slice 3 — xH / utility (slows, CC follow-up)
1. From sqlite skill_used + positions, pick a CC land then follow-up skillshot window.
2. Wire/verify `xhUtilityMultiplier` / crowdControlled path uses target mobility (incl. objective MS when known).
3. Board: range rings, CC window highlight, follow-up xH before/after.
4. Tests for utility-with-zero-damage still changing AA/xH; CC raises follow-up xH inside window.

## Integration / verify
```bash
npm run test:grid
# plus new combat / xH / regen unit tests you add
# optional: existing engine test suite slice
```
tldraw lint clean on each board (`helpers.getLints()`). Overview board links the three slices with bound arrows.

## Out of scope
- Auto kiting / terrain % / engage-success long horizon
- Match-level calculatorReady / product registry publish
- Scrim GRID pulls
- Committing raw JSONL/ROFL/.env

## Done when
- All three slices have: data extract, engine work, tests green, and an openable `.tldraw` board under `docs/canvases/`.
- `docs/canvases/README.md` still accurate.
- Honest write-up of gaps (what GRID sqlite can/cannot feed each slice) in `docs/rofl-research/axword-product-horizon.md` or a short sibling.
```
