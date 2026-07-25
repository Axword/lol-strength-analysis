# R13 NOTES — action-f1

## Done (Phase C Cycle1 context)
1. **Honest F1** — `scripts/lib/honest_action_f1.ts` strips AA/damage with shareHint≤0 and amount≤0.
2. **Echo reject** — damage-bridge audit raw F1=1.0 → fightAgreementF1=0 (E01 KEEP).
3. **Secondary 0.15** — windowScore weight proven; max FA lift from F1 ≤0.15 (E03/E07).
4. **Wire emit** — r41 emit: 14447 basic_attack + 53369 damage_dealt; 53286 PE source+amount>0 (E04).
5. **Suite join** — honest F1 into fightAgreement scorer; S0 honest FA ≈**0.348** (raw 0.330).

## Numbers (NOT win odds)
| Suite | Context STATUS | R13 note |
|-------|----------------|----------|
| S0 | 0.4217 | Remeasure honest ≈0.348 (2970110 proxy, cusum) |
| S1 | 0.478 | ≪0.95 — not retuned |
| S2 | 0.634 | ≪0.90 — not retuned |

## Isolation
- Worktree: `~/.codex/worktrees/rofl-fo-r13` branch `adv/fo-r13-action-f1`
- Docs synced to parent `fight_outcome/r13/` only
- `never_edited_parent_code: true`

## Gate
`fightOutcomeGateEvidence: false` — F1 secondary cannot carry gate.
