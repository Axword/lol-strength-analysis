# Cycle7 REVIEW BRIEF (READ-ONLY)

**utc:** 2026-07-24T16:50:00Z  
**Model:** Auto  
**Wave2 closed:** R31–R38 (8/8). Wave3 R39–R46 launching in parallel.

## Gates to vote
- `fightOutcomeGate` — true only if evidence supports mean fightAgreement ≥0.95 on S0+S1 with passRate path, no invent, FA≠odds
- `digestCleanGate` — reaffirm Path1 DIGEST (C3–C6 already true)

## Authoritative metrics (post R31 PARENT_MERGE)
- S0 FA **0.7766** pass **0.333** (≪0.95)
- S1 FA **0.5810** pass **0.333**
- c1 burst: modelKills, 2 marks, |leth|=0.635; c1 full |leth|=1.84 residual
- c2 burst maeHp 111.6 pathOk false
- G: fo:send-smoke 8/8; calculatorReady Path1 living_post_seed_v1

## Stacked KEEPs
R19 idleFollow · R30 aa/pulse · R31 preBurst 2.5 · R32 residual_hp · R33 zeroDead · R34 tornado · R35 opener · R36 openerAlly

## Vote files
Write `reviews/cycle7/V{N}.json` with: fightOutcomeGate, digestCleanGate, confidence, one_liner, evidence[].
majority_needed 11/15. FA ≠ win odds.
