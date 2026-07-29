# R38 NOTES — suite-audit-gaps

**utc:** 2026-07-24T16:26:03.636Z  
**verdict:** KEEP (docs-only)  
**gate:** fightOutcomeGateEvidence=false (audit coverage ≠ FA≥0.95)

## What was wrong

1. r27 suite `auditRel` pointed at stable ids `S0_2970132-g1_c{n}_{seg}` but parent `audits/` only had legacy `2970132-g1_check0N_*`.
2. `S1_2970120-g1_c*_*.json` missing entirely (only legacy `S1-2970120-g1-check2/3.json`).
3. `S0_2970110-g1_c*_*.json` existed but were **mislabeled** (Galio/Olaf matchups from r05 2970132 proxy).

## What we did (no invent)

| Suite member | Failing windows | Source |
|---|---|---|
| S0 2970132 Path1 | c1_full, c1_burst, c2_burst, c3_full | R30 e8 product KEEP |
| S1 2970137 | c1_full, c1_burst, c3_full, c3_burst | R30 e8 product KEEP |
| S1 2970120 | all 6 under product_dense | R20 audits + score |
| S0 2970110 | c1_burst, c2_full, c2_burst, c3_full, c3_burst | R12 e0 measured FA |

Pass windows (no failing-audit required): S0 c2_full + c3_burst; S1-2970137 c2_*; S0-2970110 c1_full.

## Coverage

failingExpected=19 missingAfter=[] badMatchup=[]
