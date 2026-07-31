# LoL Strength Analysis

Private bookmaker research workbench for reading **fight strength** from
professional LoL match state: scoreboard, map, loadouts, vision, and skillshot
hit chance.

The current output is a heuristic model edge for internal research. It is not a
calibrated win probability, fair price, market line, or recommendation.

## Goal

Turn verified live or replayed game state (positions, fog of war, objectives,
items/ranks) into **auditable fight judgments**:

1. Read the match as one instrument (scoreboard + map + timeline).
2. Select an NvM (one or both teams).
3. Send it into a combat calculator that respects HP budgets, utility, and
   skillshot uncertainty (**xH** / **xHm**).
4. Export the inputs, result, trust reasons, assumptions, and source revision as
   an evidence record.

Success looks like: an internal analyst can scrub a timestamp, spot a fight,
inspect why the model prefers Blue or Red, and hand the evidence to another
analyst for review.

## What the app does

| Surface | Role |
|---------|------|
| **Match console** | Competitive scoreboard (kills, gold Δ, towers, dragons/grubs/baron/elder) + scrubbable timeline |
| **Map** | Zoom/pan Summoner’s Rift with champs, structures, camps, FoW-aware presence |
| **Calculator** | Isolated or map-imported fights; extended/short modes; utility-aware damage |
| **Combat result** | Who wins / strength bands, packet xH, dodge typical–worst–best (and NE mix when Flash CD unknown) |
| **Wiki ingest** | Full SR kits/items/runes/summoners via `npm run ingest:lolwiki` |

### Skillshot model (xH)

Hit chance is a **σ-corridor**, not `BASE × ZONE × VISION`:

\[
xH \approx P(|miss - \mu| < R_{\mathrm{hit}}),\quad
\sigma^2 = \sigma_{\mathrm{aim}}^2 + \sigma_{\mathrm{juke}}^2 + \sigma_{\mathrm{belief}}^2
\]

- **Geometry** — ballistic lead / CPA / capsule width / travel budget  
- **Aim** — Schmidt–Fitts lineup (not missile TOF)  
- **Belief** — LKP / soft vision / multi-hypothesis FoW (no god-eye)  
- **Dodge** — Flash/dash **ready-state** budgets in the reaction window  
- **xHm** — shared-latent multi-hit dependence (not independent binomial)

Math lock-in: `npm run eval:xh` → **235/235** after a 10-pass autoresearch loop (`xh-autoresearch/`).

## What it looks like

Late-night **research console**: warm charcoal, cream type, coral accent sparingly. Scoreboard leads; map and roster sit in one bordered instrument. Dense, keyboard-reachable, WCAG-AA oriented — Anthropic/Apple quiet chrome, not esports neon or SaaS purple dashboards.

Primary glance path: **scoreboard → map → send fight → calculator result**.

## Quick start

```bash
npm install
npm run dev          # Vite app
npm run eval:xh      # xH math invariants (expect 235/235)
npm run ingest:lolwiki   # refresh wiki JSON under public/data/lolwiki/
```

Optional vision tooling (VOD frames / detector) lives under `vision/` — large datasets and weights are gitignored.

## What’s missing

- Historic empirical xH tables (mobility × zone × ability) replacing / calibrating corridor priors from real casts  
- Full **2D stadium** hit CDF (still 1D miss corridor)  
- Calibrated pricing research and model-versus-market comparison. These remain
  locked behind holdout, reliability, and model-risk gates.
- Automatic FoW/LKP scrubber from VODs (annotation pipeline exists; not productized)  
- Broad multi-match library UI (sample timelines ship; not a full VOD browser)  
- Mobile / touch-first layout (desk density first)  
- Signed-in sync, sharing, or cloud compute

## Known challenges

- **Timeline fidelity vs size** — Riot-ish ~1s position cadence; full-resolution JSON is large  
- **Kit completeness** — ranks, AH, utility-only spells, and objective buffs all matter; wiki alone is not enough without live ranks  
- **Fog honesty** — soft vision + hypotheses must not leak oracle pose/velocity  
- **Bands ↔ packets** — dodge UI must average the same cast multiset as Expected damage (multi-hit skillshots, soft-lock, OOR zeros)  
- **Objective rules** — grubs/dragons/souls change combat; wiki drift breaks trust if timings are wrong  
- **Vision ML** — frame sampling + labeling is slow; models are experimental  

## What this is *not*

- Not a consumer betting surface, tipster, or recommendation engine
- Not a market-making or calibrated pricing engine today
- Not a team or coaching product
- Not a **PN / homing** skillshot simulator (missiles do not steer mid-flight)  
- Not an **oracle FoW** tool (blind casts do not treat true position as known)  
- Not a **stream overlay** or spectator entertainment UI  
- Not “AI said they win” without inspectable factors, bands, and evidence

## Future goals

The gate-based delivery plan lives in [`ROADMAP.md`](./ROADMAP.md). Near-term
work focuses on a reproducible private research pilot. Calibrated price
comparison and live desk support are later phases.

## Repo map

| Path | Contents |
|------|----------|
| `src/engine/` | Combat, xH, vision soft, objectives, HP budgets |
| `src/components/` | Calculator, map, scoreboard, combat result, review |
| `public/data/` | Timelines + lolwiki ingest |
| `scripts/` | Eval, ingest, terrain, timeline helpers |
| `xh-autoresearch/` | Pass log + axis proposals for xH math |
| `vision/` | VOD frame / detector experiments |

## Docs

- [`PRODUCT.md`](./PRODUCT.md) — users, purpose, design principles  
- [`DESIGN.md`](./DESIGN.md) — visual system  
- [`ROADMAP.md`](./ROADMAP.md) — buyer decision, phases, and exit gates
- [`docs/reproducible-match-bundles.md`](./docs/reproducible-match-bundles.md) — remote bundle contract
- [`docs/reproduction-evidence/2026-07-28-grid-2966384-game-1.md`](./docs/reproduction-evidence/2026-07-28-grid-2966384-game-1.md) — real professional-match transfer proof
- [`docs/combat-trust-boundary.md`](./docs/combat-trust-boundary.md) — current model claims and limits
- [`xh-autoresearch/program.md`](./xh-autoresearch/program.md) — xH math loop protocol  
- [`xh-autoresearch/log.md`](./xh-autoresearch/log.md) — keep/discard decisions per pass  

## License / status

Private research prototype. APIs and balance numbers track approximate patch data and will drift.
