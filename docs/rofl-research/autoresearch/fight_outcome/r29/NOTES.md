# R29 NOTES — anti-odds-copy (F10)

## State
- digestCleanGate: true (C3 12/15)
- fightOutcomeGate: false (S0 Path1 FA ≈0.411 ≪ 0.95 after R19 idleFollowActual)
- fightAgreement ≠ win probability / odds % / pBlue

## What ran
1. `npm run test:anti-odds` (extended for F10/R29)
2. `npm run test:model-trust-reasons` (17 passed)
3. Manual scan CombatResult / Faq / modelTrust / gameStateOdds

## Odds-copy failures found (pre-KEEP)
| Surface | Finding | Action |
|---------|---------|--------|
| `src/engine/gameStateOdds.ts` | File header "Fight win odds"; JSDoc `P(blue wins the fight)` | KEEP — rewrite to heuristic model-edge |
| `src/engine/combat.ts` | Comment `→ P(blue)` on `oddsFromTradeHp` | KEEP — heuristic model-edge |
| CombatResult / Faq winner+band+nvm / modelTrust UI | None (V12 anti-odds already PASS) | no strip needed |
| Product UI forbidden patterns | 0 hits | pass |

## KEEP (copy-only)
- Faq: new `model-edge-not-odds` section (fightAgreement = kill-window suite agreement ≠ odds)
- gameStateOdds + combat comment clarifies (symbols `FightOdds` / `estimateFightOdds` kept)
- Audit extended: dual write `fight_outcome/r29/` + P10; branch `adv/fo-r29-anti-odds-copy`; faq + gameStateOdds required checks

## Unfreeze 0.9683
- Authorized; history preserved
- `docs/rofl-research/autoresearch/best.json` composite **0.9683** — **not rewritten** this run

## Out of mandate (disclose only)
- Faq `hp-budget` still claims absolute HP% ability bans — conflicts with death-coupled planner law; not odds-copy; leave for planner/FAQ follow-up

## PARENT_MERGE handoff
Copy-only paths if orchestrator merges:
- `src/components/Faq.tsx`
- `src/engine/gameStateOdds.ts`
- `src/engine/combat.ts` (comment only)
- `scripts/product_anti_odds_audit.ts`
- `docs/rofl-research/autoresearch/fight_outcome/r29/*`
