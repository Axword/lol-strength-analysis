# R15 NOTES — action-wire (Path1 2970132)

## State
- Room F5; primary = wire emit proof; secondary = honest actionCoverage F1.
- R05 baseline Path1 product cusum FA=**0.228** pass=0 (Galio→Trundle no kill + early MAE; Olaf lethal timing).

## Wire emit (KEEP)
- Emit: `product_ready/r08/emit/emit_2970132_basic_attack_damage.jsonl` (69197 lines, gameID=2970132).
- basic_attack: attackerNetId via `r28_pe_opcode_remap_block_param` (no amount).
- damage_dealt: sourceNetId+amount via `r39_unit_apply_damage_fields` (55229 amt>0).
- All 6 check×segment windows have PE source+amount ticks.
- Wire rematch F1 (damage_dealt, shareHint=amount>0): **1.0** — not actionReplayGate.

## ActionCoverage (secondary)
| Exp | emitDamaging | harness mean AC | FA-joined actionF1 | FA | Pass |
|-----|-------------:|----------------:|-------------------:|---:|-----:|
| E0 echo | false | 0.904 | 0 (forced) | 0.251 | 0.167 |
| E1 damaging | true | 0.491 | 0.491 | 0.157 | 0.000 |

- E0 high AC is zero-dmg `modelAaEchoFromTruth` — **REJECT** for gate.
- E1 zero echo (shareHint>0 only); mean AC 0.491 ≪ 0.95; gate95=false.
- E1 FA **worse** than R05 (AA overmark hurts early/path); no FA KEEP.

## Gaps
- Galio→Trundle still no burst kill on E1; Olaf lethal |err|>0.75.
- identity.gateEligible=false on stamped artifact → aaGateEligible false.
- Never treat wire rematch F1 or echo AC as fightOutcomeGate / actionReplayGate.

## Confidence
fightAgreement / actionCoverage = suite agreement — **NOT** win odds / pBlue-pRed %.
