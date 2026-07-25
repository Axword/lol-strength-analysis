# R03 Failure modes — digest validate (F1)

**utc:** 2026-07-24T15:39:52Z  
**researcher:** R03 digest-validate  
**policy:** `living_post_seed_v1` (strict all-frame stays false by design)

## Clear errors (do not invent)

| Mode | Symptom | Correct response |
|------|---------|------------------|
| Missing PE seed | `heroesWithPeHpSeed` / `heroesWithPeCombatSeed` &lt; 10 under living policy | Refuse densify / hold-forward invent; keep pre-seed `hpKnown`/`combatStatsKnown` false |
| Invent temptation | Fill pre-seed or dead slots to force `strictAllFrameCalculatorReady` | Hard fail; living_post_seed allows miss only on disclosed pre-seed + dead |
| Placeholder combat as known | `combatStatsKnown=true` with `combatStatsSource=unavailable_replay_api` or missing | validate `--product` FAIL (seen on 2970110 t=97029 pid=3) |
| Silent source wipe | Known true but `hpSource` / `combatStatsSource` / `abilityRanksSource` absent | Audit fail; `jsonl_to_timeline.py` must copy tags from rfc461 (R03: miss_when_known=0 on Path1 final) |
| Identity scramble | Bind by CreateHero / participant order instead of PUUID → netId → pid | Fail-closed; Path1 uses `stable_identity_to_net_id` (10/10) |
| Naive rebuild footgun | `jsonl_to_timeline` alone → new sha; drops `hpHoldAcrossRespawn` composer provenance | Still may validate living green, but **not** Path1 final package; use fingerprints or `rofl2_r15_path1_rematch_final.py` |
| Second-host PE gap | 2970110 FUR 7/10; no Path1 living package | Disclose gap; do not claim digestClean second host |
| Rematch/rsync | Copy another match’s HP/combat/ranks onto a real match | Banned (`copy_2970110_hp` etc.); same-match only |
| Odds misread | Treat `calculatorReady` / pBlue/pRed as win % | Model edge only; not calibrated odds |

## Observed this run

1. **2970132 Path1 final** — validate exit 0; pe 10/10; living 14725/14725; ranks dens 1.0.
2. **2970110 product-fuse** — validate exit 1; combat known without valid PE evidence.
3. **Rebuild smoke** — per-unit source combos identical; provenance composer flags not bit-restored.

## Not failure

- `strictAllFrameCalculatorReady: false` on Path1 under living_post_seed_v1 (pre-seed + dead unknown by design).
- Holding HP/combat post-seed via disclosed `hold_forward` / `hpHoldAcrossRespawn`.
