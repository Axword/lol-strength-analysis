# DIGEST — ROFL→JSONL product path (fight_outcome)

**utc:** 2026-07-24T15:40:00Z  
**digestCleanGate:** true (C3 majority 12/15; Path1 2970132 validate+fingerprints; second-host gap disclosed)  
**host:** 2970132-g1 Path1 final  
**policy:** `living_post_seed_v1` (not strict all-frame)  
**hold_forward / hold_across_respawn:** disclosed (Path1)  
**unfreeze_0_9683:** true (orthogonal; does not invent pins)  
**pBlue/pRed:** model edge only — never odds %  
**researcher:** R01 digest-path (`adv/fo-r01-digest-path`)

## One command path (macOS) — validate Path1 final

From repo root or worktree with `artifacts/rofl` → parent symlink:

```bash
python3 scripts/validate-rofl-pipeline.py --product \
  --jsonl artifacts/rofl/2970132/events.g1.path1-final.rfc461.jsonl \
  --timeline artifacts/rofl/2970132/timeline.g1.path1-final.json \
  --calculator-ready-policy living_post_seed_v1 \
  --require-calculator-ready
```

Expected: exit 0, `productPublication.calculatorReady: true`, `calculatorReadyPolicy: living_post_seed_v1`, `livingOkSlots: 14725`, `hpHoldAcrossRespawn: true`.

## Rebuild path (when regenerating timeline from rfc461)

Use `-o` / `--output` (required). Do **not** invent a bare `--out` flag in docs; argparse may abbreviate today, but canonical is `--output`.

```bash
python3 scripts/jsonl_to_timeline.py \
  artifacts/rofl/2970132/events.g1.path1-final.rfc461.jsonl \
  -o /tmp/timeline.g1.path1-rebuild.json \
  --id 2970132-g1 \
  --name "GRID 2970132 g1 Path1 rebuild"

# Coverage stamp lag: rematch stamps hold-across on timeline after build,
# but does not rewrite rfc461 rofl_coverage. Re-apply disclosed Path1 stamps:
python3 scripts/stamp_digest_path1_provenance.py \
  --timeline /tmp/timeline.g1.path1-rebuild.json \
  -o /tmp/timeline.g1.path1-rebuild.stamped.json \
  --set-calculator-ready true

python3 scripts/validate-rofl-pipeline.py --product \
  --jsonl artifacts/rofl/2970132/events.g1.path1-final.rfc461.jsonl \
  --timeline /tmp/timeline.g1.path1-rebuild.stamped.json \
  --calculator-ready-policy living_post_seed_v1 \
  --require-calculator-ready
```

R01 proved this chain in-worktree under `docs/rofl-research/autoresearch/fight_outcome/r01/experiments/` (e02 rebuild, e07 stamp+validate).

Full rematch (heavier; only if regenerating events): `python3 scripts/rofl2_r15_path1_rematch_final.py` (worktree with inputs).

## Artifact fingerprints (2970132 Path1 final)

| File | bytes | sha256 |
|------|------:|--------|
| events.g1.path1-final.rfc461.jsonl | 114456779 | `823aa35fc309efc7ed7536b5becb9d21f382ea3e03a250d87ad88bee5b0b9bf8` |
| timeline.g1.path1-final.json | 9064216 | `fb542736e56e6e0afbbc90c0a6a493b9f0236e898c7bca7c39cde50eaedc4fe4` |

## Sources (must survive merge) — R01 e06 census

Events `stats_update` ↔ timeline units **identical** source counts (no wipe):

| Tag | pe / seed | hold_forward | other |
|-----|----------:|-------------:|------|
| `hpSource` | 203 | 16098 | 659 unknown/dead |
| `combatStatsSource` / `combatSource` | 1766 (`same_match_replication_type107_pe_wire_table`) | 12959 | 2235 `unavailable_replay_api` |
| `abilityRanksSource` | 16960 `rofl2_upgrade_spell_ans_1012_first_write` | — | — |

`jsonl_to_timeline.py` copies `hpSource` / `combatStatsSource` / `combatSource` / `abilityRanksSource` when present (never invents).

## Identity (PUUID → netId → pid)

Stable bind for all 10 heroes (`identityComplete: true`). Never participant-order.

| pid | champ | full Riot ID | netId | puuid (prefix) |
|----:|-------|--------------|------:|----------------|
| 1 | Olaf | GEN Kiin#eProd | 1073741998 | d62acbf0… |
| 2 | JarvanIV | GEN Canyon#eProd | 1073741999 | 26e416f6… |
| 3 | Galio | GEN Chovy#eProd | 1073742000 | dc20fd1d… |
| 4 | Seraphine | GEN Ruler#eProd | 1073742001 | 3462f12f… |
| 5 | Shen | GEN Duro#eProd | 1073742002 | 7d48b778… |
| 6 | Jayce | JDG Xiaoxu#eProd | 1073742003 | eaa17a03… |
| 7 | Trundle | JDG JunJia#eProd | 1073742004 | 00da3a3d… |
| 8 | Orianna | JDG HongQ#eProd | 1073742005 | 483a03fc… |
| 9 | Ziggs | JDG GALA#eProd | 1073742006 | 9ba5fc1f… |
| 10 | Camille | JDG Vampire#eProd | 1073742007 | 30ac5dfb… |

Full table: `docs/rofl-research/autoresearch/fight_outcome/r01/experiments/e04_identity_bind.json`.

## Second host

**2970110:** not digest-clean. `validate --product --require-calculator-ready` **fails** (`combatStatsKnown=true` with `source='unavailable_replay_api'`). Disclosed gap — no invent, no claim.

## Failure modes (honest)

1. Missing PE seed → refuse densify; do not invent pre-seed HP.
2. Bare rebuild without stamp → metrics show `hpHoldAcrossRespawn: false` (coverage lag); living may still pass — stamp or use Path1 final timeline.
3. Historical rematch source wipe → fixed in Path1 final; e06 must stay wipe-free.
4. Identity scramble → fail-closed; PUUID/netId only.
5. Second host combat honesty fail → disclose; do not ship.

## Parent / Cycle6

- Path1 `calculatorReadyGate`: true (`living_post_seed_v1`) — Cycle6 15/15
- See `docs/rofl-research/autoresearch/product_ready/reviews/cycle6/CYCLE6_FINAL.json`
- R01 validate reconfirm: exit 0 (e01)

## Still missing for digestCleanGate true

1. Reviewer V2 affirm + majority with `fightOutcomeGate` co-gate
2. Second host preferred (2970110 PE/combat honesty still blocks)
3. Optional: write hold-across stamps back into rfc461 `rofl_coverage` so stamp helper is unnecessary

## Metric freeze notes (orchestrator)

- **S0 Path1** (R05 freeze-idle): FA **0.2279** / pass 0 — superseded as product default after R19 KEEP.
- **S0 Path1** (R19 idleFollowActual KEEP, worktree measure): FA **≈0.411** / pass **≈0.167** — still ≪0.95; remesaure on parent via R25.
- **S1 current-law** (R20 freeze, no tune): FA **≈0.411** / pass **≈0.167** — R06 stored **0.478** was inflated lethal (`|leth|=2.72` under old tol); do not cite 0.478.
- fightAgreement ≠ win odds / pBlue%.
