# FUR-parity 10-pass adversarial freeze (2026-07-22)

Five-role review against Pass 10 exit criteria. External critic subagents were
unavailable (API limit); this is the same checklist run locally against green
artifacts.

**Trust boundary (updated):** `npm run rofl:live-fur` / `rofl:schema-proof` is a
**schema plumbing proof only**. It remaps live Replication HP onto the FUR
fixture CreateHero roster and keeps fixture combat/ranks. That must never be
treated as a real-match product gate or calculator-ready publication.
Real-match calculator readiness requires same-match identity-bound positions +
HP + combat + ranks that pass `validate-rofl-pipeline.py --product`.

| Role | Result | Notes |
|------|--------|-------|
| Honesty | PASS (schema) | `explicit_max` requires wire `(5,1)`; no synthetic heroes; live-fur remaps live HP onto fixture CreateHero net_ids and keeps fixture combat Replication (disclosed; `publicationBlocked` / `schemaProof`) |
| FUR schema | PASS | `/tmp/fur_parity_e2e` and `/tmp/live_fur_e2e` prove `schemasOk/fieldsOk` under generic `validate_fur`; checklist lists `barracks_minion_*` |
| RE/binary | PASS | `USE_REPLICATION=0x100785924` prologue-tested; type 107 **not** claimed as native Use map entry; stub + vector apply documented |
| Mapper | PASS | Live decrypt events → maknee JSONL → rebuild → generic `validate_fur` green (schema); `--strict-product` correctly rejects this fixture/CreateHero-order path |
| Product gate | SCHEMA ONLY | Fixture merge lights `hpKnown`/`combatStatsKnown`/`abilityRanksKnown` for plumbing tests; **not** a real-match publish. Product publication must use `--product` and reject schema-proof / static-snapshot / synthetic path provenance |

## Commands frozen green

```bash
npm run rofl:replication-decode -- \
  "$HOME/Documents/League of Legends/Replays/BR1-3264361042.rofl" \
  --json-out docs/rofl-research/replication-decode-BR1-3264361042.json

npm run rofl:fur-parity
npm run rofl:schema-proof -- \
  "$HOME/Documents/League of Legends/Replays/BR1-3264361042.rofl" \
  --out-dir /tmp/live_fur_schema_proof
# alias: npm run rofl:live-fur -- <rofl> --out-dir ...
# emits live_fur_schema_proof_timeline.json; public/data output is refused
```

No P0 findings for schema plumbing. Do not overclaim calculator readiness for real matches from this path.
