## Learned User Preferences
- Prefer maximum native timeline granularity for game replays; do not downsample frames just to shrink JSON when positioning fidelity matters.
- Prefer combat/team-win results shown visually (who wins / strength bands), not only raw damage numbers; treat pBlue/pRed as heuristic model scores (“model edge”), never as calibrated win probabilities or odds %.
- Map → calculator flow should support multi-champion NvM selection, including selecting both teams at once.
- Map review should support zoom/pan and show turrets, inhibitors, nexus, and jungle camps with official LoL wiki icons, clear alive/dead availability at second precision, and larger structure/camp icons than champion markers.
- Dead champions must be excluded from calculator imports (do not count their combat stats); missing HP/combat fields from replay sources must stay unknown rather than faked as dead/full.
- Action timelines must respect remaining HP — a low-HP champion cannot dump a full skill rotation against a healthy opponent.
- Prefer a competitive-style map scoreboard (towers, gold with delta, kills, role quests, grubs, dragons, baron, elder) and include objective buffs in combat math.
- Fog of war should distinguish unseen-by-anyone vs unseen-by-opponents; vision presence should inform skillshot xH.
- Prefer dark Anthropic/Apple-like product-tool UI that feels integrated, not a collage of disconnected assets; avoid em dashes in user-visible copy.
- Prefer extended-fight modeling with resource regeneration, calibrated against actual match outcomes from the timeline feed.
- Champion-history board should separate AS from AH, show gold as total/items/bag, quantify cumulative dragon-buff effects (MS, damage amp, mitigation), and order columns by win-correlation at the current game time.
- Grub-touch estimates must be auditable (assumptions, burn uptime, tick rate, melee/ranged, plate-equivalent) so numbers are reproducible; prefer mining high-confidence proxies (including match VOD analysis) when confidence is low.

## Learned Workspace Facts
- Utility-only abilities (slows, withers, shields, MS buffs) must never be skipped for having zero base damage — e.g. Nasus W / Zilean E reshape AA counts, xH, and kite windows.
- Full game knowledge is ingested via `npm run ingest:lolwiki` into `public/data/lolwiki/` (all Summoner's Rift items only — not TFT/Arena/ARAM, all runes including Unsealed Spellbook, all summoners, all 171 Meraki champion kits). Do not ship a hand-curated subset as the source of truth.
- This repo is a LoL combat strength analysis app (React + TypeScript + Vite) with a phased roadmap: v1 isolated 1v1 calculator → v2 map/game-state import into the calculator → v3 xH/xHm → v4 teamfight win-odds ranges (worst/typical/best).
- xH is skillshot hit chance from similar historic situations (mobility buckets, map zones, only when enemies are in ability range); xHm is multi-target hit distribution; current code uses priors until historic rates replace them.
- Timeline ingest is Riot live-stats JSONL (`events_*_riot.jsonl`, `stats_update` / rfc461Schema) rebuilt into `GameTimeline` JSON in `public/data/` (e.g. `fur_vs_g2_timeline.json`); position cadence is ~1s. Raw `.rofl` is a separate encrypted spectator format; patch-matched client Replay API (`https://127.0.0.1:2999`) can capture real world positions via focus camera + player-identity selection (plain `playerName` primary), often without HP—emit rfc461 JSONL with unknown combat fields rather than inventing values (`docs/rofl-format.md`).
- Ability ranks from live game state are required for correct scalings; wiki kit data alone is not enough without per-ability rank.
- Void grub and dragon objective effects must follow wiki-accurate rules (e.g. grub count → tower damage ticks; dragon buff/soul types change combat) and feed damage calculations.
- Jungle camp spawn/respawn overlays must use current wiki timings (early-game camp clocks have changed); availability on the map must be second-precise from the timeline.
- VOD vision work lives under `vision/` with ~0.5s ffmpeg frame sampling and bbox object-detection labeling; annotation remains manual for now with Label Studio export structure kept for later revisit.
- Champion-history win-correlation / gold-vs-win curves can reuse research from sibling `parlay-risk-sim` when ranking or interpreting stats at a given game time.
- CORE/hand-curated champion kits mean modeling attention only—not patch-validated trust; `modelTrust` distinguishes manual-kit 1v1 vs experimental NvM/generated, with calibrated=false until empirical validation (`docs/combat-trust-boundary.md`, coverage audit via `scripts/audit-combat-coverage.ts`).
- Timed cast/AA rotation planning applies only to living CORE 1v1 (attack-reset empowered autos, stop at first lethal, xH-aware target-effective scoring); NvM and generated kits keep the aggregate-window fallback.
