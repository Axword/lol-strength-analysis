# Axword × product horizon

Working plan from Discord (2026-07) plus current repo gates. Local pro-play dump lives in gitignored `artifacts/pro-grid/`.

## Do now (pipeline)

1. **ROFL decrypt trust** — first real-match gate reached on 2026-07-29 for GRID `2970132`, game 1 / Riot `LOLTMNT01-428534`. Product validation passes under the explicit `living_post_seed_v1` policy: all ten heroes have PE HP and combat seeds, ability-rank density is 1.0, and all 14,725 required living post-seed slots have honest HP+combat+ranks. Strict all-frame readiness remains false because 1,577 pre-seed and 658 dead slots stay unavailable rather than being filled.
2. **GRID Riot live-stats (preferred timeline)** — `npm run grid:riot-to-sqlite` writes slim research SQLite (`meta` / `roster` / `frames` / `events`) as `artifacts/pro-grid/<seriesId>/timeline.gN.slim.sqlite` (~2% of raw JSONL; tracked). Catalog: `SQLITE_INDEX.json`. Optional fat rfc461: `npm run grid:riot-to-rfc461 -- --out …` (gitignored). Provenance `sourceKind=grid_riot_livestats`. Never `productEligible` / never `calculatorReady` from this path alone.
3. **GRID sparse side channel** — `npm run grid:to-rfc461` converts series zip envelopes → research rfc461. Sparse snapshots only (kills / abilities / objectives). Keep as side channel when riot live-stats is present.
4. **Paired fixtures** — same `seriesId` on `replay_riot_<id>_N.rofl` + `events_<id>_grid.jsonl.zip` + `events_<id>_N_riot.jsonl`. PUUID join already proves 10/10 same-match on 5 pairs (`npm run grid:manifest`). Still missing: ROFL for `2970136`, GRID for `2919595` / `2954867`.
5. **Rename before product ingest** — dump names use Grid series ids. Derive `PLATFORM-matchCode` only from riot live-stats `game_info.platformID` + `gameID` (`npm run grid:rename-report`). Example: `replay_riot_2970110_1.rofl` → `LOLTMNT01-426746.rofl`. Do not guess platform from ROFL trailing metadata (often lacks `platformId`/`gameId`).
6. **GRID API** — `scripts/grid_api.py`. Auth via gitignored `.env` `GRID_API_KEY`. **Pro only:** Central Data `type: ESPORTS` + tournament name + scrim-name block (no override). Official File Download: `GET /file-download/list/{seriesId}` then `fullURL`. Send `User-Agent` or Cloudflare 1010. Refs: [File Download how-to](https://grid.helpjuice.com/cloud9-x-jetbrains-hackathon/how-do-i-use-the-file-download-api), [OA quickstart](https://grid.helpjuice.com/client-help/open-access-quickstart) (OA has no File Download / no LoL).

## GRID → calculator trust (honest fuse draft)

| Gate | Sparse Grid zip | Riot live-stats (`events-riot`) | Product ROFL fuse (required) |
|------|-----------------|----------------------------------|------------------------------|
| Positions | Sparse full-state only | Dense ~1 Hz when present | Replay API or proven packet waypoints |
| `hpKnown` | Only on sparse snapshots | Yes when `health`+`healthMax` on wire | `rofl-trusted-hp-v1` identity-bound decrypt |
| `combatStatsKnown` | No (armor-only ≠ combat) | Yes when AD/AP/armor/MR/AS all present | PE / combat wire proven |
| `abilityRanksKnown` | No (ready flags only) | Yes when `abilityNLevel` present (0 valid) | `UpgradeSpellAns` same-match bind |
| Roster join | PUUID via `RIOT_PUUID` links | PUUID + `riotId.displayName#tagLine` | PUUID / full Riot ID → netId |
| `productEligible` | Always false | Always false from adapter | Only after `validate-rofl-pipeline.py --product` |
| `calculatorReady` | Never | Never from GRID alone | Same-match positions+HP+combat+ranks |

**Fuse plan (draft, not shipped):** when ROFL + riot live-stats coexist for the same PUUID set:

1. Rename ROFL to `suggestedProductRofl` from riot `game_info`.
2. Prefer Replay API / ROFL decrypt for product positions + trusted HP; use riot live-stats as a **research cross-check** (density reference, ability-level timeline, combat pins) — do not publish GRID-only timelines into `public/data/matches/`.
3. Ability ranks from riot live-stats are wire-present and usable for research scalings, but product `abilityRanksKnown` still wants same-match packet proof unless a future gate explicitly accepts live-stats ranks with provenance.
4. Early MonkeyKing-style `mMaxHP` gaps remain a ROFL-decrypt problem; riot live-stats may show HP earlier — that does **not** auto-flip match-level `calculatorReady`.

## Combat model (Axword asks)

| Ask | Status |
|-----|--------|
| CC raises follow-up xH | Shipped (`xhUtilityMultiplier` / `crowdControlled` in `src/engine/xh.ts`) |
| Slows / MS vs dodge | Partial (utility multipliers); no full relative-MS sim |
| Kiting / AA-move cancel | Horizon — `aaUptime` knob only; needs replay profiles |
| Engage / engage-success + range | Partial short-window `engageCc`; long-window / “never enter” later |
| Terrain advantage % | Horizon — after ~good 1v1, backtest vs history |
| Minions | No |

## Honest blockers (do not fake)

- Offline continuous positions: `waypoints_not_structurally_decoded` (Replay API only for product positions).
- Sparse GRID zip: HP/position only on full-state events, not 1 Hz; abilities are ready flags, not ranks.
- Riot live-stats can satisfy per-frame HP/combat/ranks markers, but **not** match-level `calculatorReady` without ROFL identity fuse + `--product` validation.
- Strict all-frame readiness still has honest early/dead gaps. The shipped `living_post_seed_v1` policy allows only pre-seed/dead slots to remain unavailable; every living post-seed slot must be known.
- Never publish GRID research outputs to `public/data/matches/` from this path.

## Current milestone and next iterations

The first complete local product path is documented in
`docs/reproduction-evidence/2026-07-29-calculator-ready-2970132-game-1.md`.
It includes same-match provenance, the independent AA timeline gate, and a real
browser Review → Send 5v5 → Calculator check.

Next roadmap:

1. Reproduce the same gate on a second pro match without changing the policy or packet registry.
2. Decode and bind attack targets and damage amounts only from proven packet fields; keep them unavailable until then.
3. Add a compact local match package/loader so an authorized operator does not need to choose separate files.
4. Keep public registry and deployment blocked until GRID/replay publication authority is explicit.
5. Evaluate action-replay/fight agreement separately. Neither `calculatorReady` nor AA packet coverage is calibrated outcome accuracy or betting odds.

## Commands

```bash
npm run grid:manifest
npm run grid:rename-report
npm run grid:download -- --series-id 2970110 --include events-grid,events-riot,replay-riot
npm run grid:riot-to-sqlite -- \
  --input artifacts/pro-grid/events_2970110_1_riot.jsonl \
  --sqlite artifacts/pro-grid/2970110/timeline.slim.sqlite \
  --series-id 2970110 \
  --join-rofl artifacts/pro-grid/replay_riot_2970110_1.rofl
npm run grid:riot-to-rfc461 -- \
  --input artifacts/pro-grid/events_2970110_1_riot.jsonl \
  --out artifacts/pro-grid/2970110/events.riot.rfc461.research.jsonl \
  --summary artifacts/pro-grid/2970110/riot.summary.json \
  --join-rofl artifacts/pro-grid/replay_riot_2970110_1.rofl
npm run grid:to-rfc461 -- \
  --input artifacts/pro-grid/events_2970110_grid.jsonl.zip \
  --out artifacts/pro-grid/2970110/events.rfc461.research.jsonl \
  --summary artifacts/pro-grid/2970110/summary.json
npm run test:grid
npm run test:rofl-decrypt
npm run rofl:product-pipeline -- --skip-live-discover
npm run rofl:finalize-calculator-ready -- \
  --rofl artifacts/pro-grid/replay_riot_2970132_1.rofl \
  --source-jsonl artifacts/rofl/2970132/events.g1.path1-final.rfc461.jsonl \
  --source-timeline artifacts/rofl/2970132/timeline.g1.path1-final.json \
  --replay-manifest artifacts/rofl/2970132/replay-manifest.g1.json \
  --identity-evidence artifacts/rofl/2970132/trusted-hp-perhero.g1.product.json \
  --output-jsonl artifacts/rofl/2970132/events.g1.calculator-ready.rfc461.jsonl \
  --output-timeline artifacts/rofl/2970132/timeline.g1.calculator-ready.json \
  --summary artifacts/rofl/2970132/calculator-ready.g1.summary.json
```
