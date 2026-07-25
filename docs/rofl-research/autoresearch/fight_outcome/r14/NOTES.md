# R14 — action-noecho (F5)

**Branch:** `adv/fo-r14-action-noecho`  
**Worktree:** `/Users/river/.codex/worktrees/rofl-fo-r14`  
**never_edited_parent:** true

## Auto-picked F5 hypotheses
1. Honest F1 (reject zero-dmg echo)
2. Secondary only (0.15 weight)
3. Wire emit proof (source+amount)
4. Coverage gaps disclosed
5. Suite join into fightAgreement

## Headline
- Honest c1-full damage F1 = **1.0000** (gateEligible=true)
- Echo F1 = **1.0000** → **REJECT** (forbid #13); FA credit = 0
- S0 product FA (f1=0) = 0.3494 → honest partial = 0.3744

## Reproduce
```bash
cd /Users/river/.codex/worktrees/rofl-fo-r14
npx --yes tsx scripts/fo_r14_action_noecho_audit.ts
```

pBlue/pRed / fightAgreement ≠ win odds.
