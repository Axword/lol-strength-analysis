# Phase C Cycle1 BRIEF — fightOutcome

utc: 2026-07-24T15:44:00Z
model: Auto
researchers_done_at_trigger: 6 (R01–R04, R06–R07; R02–R04,R07 earlier)

## Vote law
Vote `fightOutcomeGate: true` only if YOU personally affirm A–I on evidence.
Do NOT vote false solely because other reviewers unfinished.
Vote false only for concrete A–I failure.
Also affirm/deny `digestCleanGate`.

## Current measured (NOT win odds)
- S0 product CUSUM FA **0.4217** / pass 0.167 (2970110 proxy; 2970132 crosschecks missing)
- S0 research-drop 0.6018 (not product default)
- S1 FA **0.478** / pass 0.333 (R06)
- S2 FA **0.634** / pass 0.333 (R06)
- Gate needs S0+S1 ≥0.95 — **not met**
- unfreeze 0.9683: no FA KEEP yet (R07 flat)
- digest: Path1 validate green; source-preserve 0/0/0; 2970110 PE gap disclosed

## Evidence roots
- `docs/rofl-research/autoresearch/fight_outcome/`
- DIGEST.md, PARENT_MERGE.md, r01–r07 summaries, audits/
- GOAL-fight-outcome-95-10x30x15.md
- CYCLE6_FINAL.json (calculatorReady prereq only)

## Output
Write `/Users/river/Projects/lol-strength-analysis/docs/rofl-research/autoresearch/fight_outcome/reviews/cycle1/V{N}.json`
Fields: reviewer, role, fightOutcomeGate true|false, digestCleanGate true|false, confidence, evidence[], failures[], notes
