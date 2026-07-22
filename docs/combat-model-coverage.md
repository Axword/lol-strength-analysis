# Combat model coverage

This document records the **measurable gap** between ingested full-game knowledge
(`npm run ingest:lolwiki` → `public/data/lolwiki/` + `src/data/generated/`) and
combat behavior that is **actually modeled** in the calculator/runtime.

Machine-readable source of truth:

```bash
npx --yes tsx scripts/audit-combat-coverage.ts
npx --yes tsx scripts/audit-combat-coverage.ts --json
npx --yes tsx scripts/audit-combat-coverage.ts --check
npx --yes tsx scripts/audit-combat-coverage.ts --strict
npx --yes tsx scripts/audit-combat-coverage.ts --self-test
```

Do **not** claim an ability is accurate merely because a `damage` / `utility`
function exists. Do **not** equate `CORE_CHAMPIONS` / hand-curated kits with
trusted or patch-validated combat. CORE proves modeling attention only.

---

## Measured counts (local repo)

Captured with `npx --yes tsx scripts/audit-combat-coverage.ts` (no network).
Human output is deterministic (stable `lolwiki snapshotAt`, no wall-clock).

| Metric | Count |
|--------|------:|
| Wiki champion index | 171 |
| Runtime `CHAMPIONS` | 20 |
| `GAME_CHAMPIONS` (generated Meraki kits) | 18 |
| Curated `CORE_CHAMPIONS` (manual-model, unvalidated) | 10 |
| Curated overrides of GAME entries | 8 |
| Curated-only (no GAME stub) | 2 (`Nasus`, `Zilean`) |
| Wiki-only (ingested, no runtime combat object) | 151 |
| Runtime `ITEMS` / `ITEM_LIST` (calculator catalog) | 292 |
| Generated `ALL_ITEMS` (base before GAME merge) | 281 |
| Summoner's Rift items JSON | 316 |
| Explicit `ITEM_PASSIVES` behavior hooks | 5 |
| No-hook / unreviewed runtime items | 287 |
| Runes | 62 |
| Keystones | 17 |
| Keystones with combat hooks (`tradeBonus`) | 16 |
| Keystones missing hooks | 1 (`deathfireTouch`) |

Provenance:

- lolwiki meta patch: **16.14.1**
- lolwiki `ingestedAt` / audit `snapshotAt`: **2026-07-21T11:09:46.616Z**
- items `DDRAGON_PATCH`: **16.14.1**
- runtime champion `DDRAGON`: **16.14.1**
- Committed timeline `fur_vs_g2_timeline.json` patch: **16.13.790.6961**
- Builtin `maknee_stub` exists on disk but is **not** git-committed → excluded

Coverage flags:

- `fullManualModelCoverage`: **NO**
- `fullTrustedCoverage`: **NO** (and cannot become YES without an explicit validation evidence ledger)

---

## Modeling tiers (not trust)

| Tier | Meaning | Validated / trusted? |
|------|---------|----------------------|
| `wiki_only` | In wiki index only; no runtime `ChampionDefinition` | No |
| `generated` | `GAME_CHAMPIONS` Meraki stub, not superseded by CORE | No — unvalidated |
| `curated` / `curated_override` | Hand-authored `CORE_CHAMPIONS` (manual-model) | **Still unvalidated** — attention ≠ patch correctness |
| `unresolved` | Timeline name not in wiki index or runtime | Structural `--check` failure |

`hasDamageFunctions === true` only means a callable exists.

### Coverage flags

| Flag | Meaning |
|------|---------|
| `fullManualModelCoverage` | Every wiki champion has a CORE manual model; every keystone has a hook; committed timeline participants are manual-modeled; **and** every runtime item is explicitly reviewed/classified via a review ledger |
| `fullTrustedCoverage` | `fullManualModelCoverage` **plus** explicit patch/numerical/empirical validation evidence |

Filling CORE for all 171 champions alone must **never** flip `fullTrustedCoverage`.

### Items

- Stats-only items may legitimately have no `ITEM_PASSIVES` hook.
- Current state: **5** explicit behavior hooks, **287** no-hook/unreviewed rows.
- Strict bar: every item **classified** (stats-only vs combat-relevant) and every combat-relevant passive/active **modeled** — not “fake hooks for boots.”
- No item review ledger exists → keep `--strict` red with that reason.

---

## CLI contract

| Mode | Exit | Behavior |
|------|------|----------|
| (default) | 0 | Deterministic human summary (byte-stable) |
| `--json` | 0 | Full `CoverageReport` JSON (`snapshotAt` from lolwiki meta) |
| `--check` | 0 / 1 | Structural failures only (IDs, unresolved timeline champs, impossible/malformed meta). Incomplete modeling does **not** fail |
| `--strict` | 0 / 1 | Nonzero while below **full trusted** coverage; includes missing validation-evidence gate and missing item-classification ledger |
| `--self-test` | 0 / 1 | Guards runtime `ITEMS` source, deterministic human output, and “manual ≠ trust” |

---

## Committed timeline coverage

Discovery: `git ls-files 'public/data/*_timeline.json'`, then
`participants[].championName` (no hardcoded roster).

### `public/data/fur_vs_g2_timeline.json`

- Participants: 10 — all have runtime combat defs (`generated`)
- None curated/manual-model: Akali, Ambessa, Camille, Galio, Gnar, Jhin, LeeSin, Leona, Naafiri, Syndra
- Missing combat definitions: none
- Unresolved wiki IDs: none

---

## Limitations

- Offline/local only.
- CORE kits can still be wrong vs live patch.
- `GAME_CHAMPIONS` formulas are not numerically validated by this audit.
- Runtime `ITEMS` (292) ⊃ generated `ALL_ITEMS` (281) via `GAME_ITEMS` merge.
- Legacy `deathfireTouch` keystone has no combat hook.
- Objectives / xH / HP-budget fidelity are out of scope.

---

## Prioritized next modeling queue (from evidence)

1. **Manual-model the FUR vs G2 roster** (currently `generated`): Lee Sin, Ambessa, Akali, Jhin, Camille, Gnar, Naafiri, Galio, Syndra, Leona.
2. **Register or retire `deathfireTouch`** for keystone hook completeness.
3. **Add an item review ledger** classifying each runtime item as stats-only vs combat-relevant; model hooks only where combat-relevant (expand beyond Sheen line / Cleaver / Liandry as needed).
4. **Add explicit validation evidence** (patch checks, numerical fixtures, timeline outcome calibration) before any kit is treated as trusted.
5. Broaden CORE beyond sample staples only after (1)–(4) have a path — never batch-promote wiki-only rows as “trusted.”

Re-run the audit after each batch; refresh the measured table from the script rather than editing counts by hand.
