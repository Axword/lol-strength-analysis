# R11 NOTES — planner-utility

## Contract fix (KEEP)

`collectFighterDamageTimed` previously did:

```ts
if (expectedDamage <= 0 && !ability.execution?.attackReset) continue
```

That dropped Nasus W / Zilean E / Camille R (engageCc, 0 damage). Now keep when `ability.utility || ability.engageCc`, with planner proxy score `UTILITY_PLANNER_PROXY_DAMAGE` (default 12, env override). `abilityProcs` for Spellblade counts **damaging** casts only.

## Why S0 FA did not move

1. Product measure uses `gate_action` mark pulses, not full timed rotations — proxy sweeps are FA-identical at 0.4217.
2. Wither/hardCC env sweeps also FA-flat on Camille/Syndra/Ezreal windows (AA-wither not the binding error).
3. Camille Q Meraki stub is empty — Q marks contribute 0 kit damage (disclose; no invent).

## Binding errors (from audits / harness)

- c2 path MAE / lethal timing (Syndra→Camille)
- c3 early MAE + false-kill / miss (Ezreal→LeeSin)
- c1 burst earlyBand (earlyMaeHp 126)

Utility-keep is still required product honesty for calculator Send timed path.

## Files touched (worktree only)

- `src/engine/combat.ts` — utility/engageCc keep + proxy + Spellblade filter
- `src/engine/utility.ts` — env caps (defaults unchanged)
- `src/engine/__tests__/combat.acceptance.test.ts` — Nasus W + Zilean E keep asserts
- `scripts/r11_*.ts` — probes/sweeps
- `scripts/fight_agreement_suite.ts` — copied for local measure
