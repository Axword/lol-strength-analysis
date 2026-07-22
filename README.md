# LoL strength analysis

React + TypeScript + Vite app for combat / timeline analysis.

- Product notes: [`PRODUCT.md`](PRODUCT.md), [`DESIGN.md`](DESIGN.md)
- Replay format research (ROFL1/ROFL2 → why it is not live-stats JSONL): [`docs/rofl-format.md`](docs/rofl-format.md)
- Combat calculator trust boundary and acceptance evidence: [`docs/combat-trust-boundary.md`](docs/combat-trust-boundary.md)

---

# React + TypeScript + Vite

This template provides a minimal setup to get React working in Vite with HMR and some Oxlint rules.

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react) uses [Oxc](https://oxc.rs)
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react-swc) uses [SWC](https://swc.rs/)

## React Compiler

The React Compiler is not enabled on this template because of its impact on dev & build performances. To add it, see [this documentation](https://react.dev/learn/react-compiler/installation).

## Expanding the Oxlint configuration

If you are developing a production application, we recommend enabling type-aware lint rules by installing `oxlint-tsgolint` and editing `.oxlintrc.json`:

```json
{
  "$schema": "./node_modules/oxlint/configuration_schema.json",
  "plugins": ["react", "typescript", "oxc"],
  "options": {
    "typeAware": true
  },
  "rules": {
    "react/rules-of-hooks": "error",
    "react/only-export-components": ["warn", { "allowConstantExport": true }]
  }
}
```

See the [Oxlint rules documentation](https://oxc.rs/docs/guide/usage/linter/rules) for the full list of rules and categories.
# LoL Strength Analysis

Desk-side research console for reading **fight strength** from LoL match state — scoreboard, map, loadouts, vision, and skillshot hit chance — not a betting tip engine or a stream overlay.

## Goal

Turn live or replayed game state (positions, fog of war, objectives, items/ranks) into **auditable fight judgments**:

1. Read the match as one instrument (scoreboard + map + timeline).
2. Select an NvM (one or both teams).
3. Send it into a combat calculator that respects HP budgets, utility, and skillshot uncertainty (**xH** / **xHm**).

Success looks like: an analyst can scrub a timestamp, spot a fight, and trust why the model prefers blue or red — including dodge bands and fog — without losing context.

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
- Polished teamfight win-odds productization (worst/typical/best ranges exist in spirit; end-to-end UX incomplete)  
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

- Not a **betting / odds** product or parlay tipster  
- Not a **PN / homing** skillshot simulator (missiles do not steer mid-flight)  
- Not an **oracle FoW** tool (blind casts do not treat true position as known)  
- Not a **stream overlay** or spectator entertainment UI  
- Not a substitute for replay coaching judgment — it is a structured prior + state calculator  
- Not “AI said they win” without inspectable σ factors and bands  

## Future goals

1. **Calibrate xH** on labeled historic skillshots; keep the σ factorization, tighten parameters.  
2. **Close the map → calculator → result** loop for 5v5 with clear worst/typical/best fight odds.  
3. **Ship FoW/LKP** from vision or feed-derived scrubbers into the same softVision path.  
4. **Library of matches** with career/gold-vs-win context at scrub time.  
5. **Exportable fight cards** (assumptions, bands, xH factors) for research notes.  
6. Optional: stadium geometry and richer belief packs without reintroducing multiplicative zone×vision glue.

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
- [`xh-autoresearch/program.md`](./xh-autoresearch/program.md) — xH math loop protocol  
- [`xh-autoresearch/log.md`](./xh-autoresearch/log.md) — keep/discard decisions per pass  

## License / status

Private research prototype. APIs and balance numbers track approximate patch data and will drift.
