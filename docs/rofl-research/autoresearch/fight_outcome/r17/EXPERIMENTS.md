# R17 EXPERIMENTS

| ID | Hypothesis | Pass | Key metric |
|----|------------|------|------------|
| E0 | H1 shared module imports | PASS | Calculator + harness → killWindowOverlay |
| E1 | H1 Matchup ≡ series endHp | PASS | endHp 289.7298034293832 both; selectedMarks 2/4 |
| E2 | H1 Path1 Galio→Trundle pins | PASS | endHp 1066.1948051948048 both; invent=false |
| E3 | H2 dead excluded | PASS | deadExcludedCount=1; canSend=true |
| E4 | H4 known-flags fail-closed | PASS | trustGap=Jayce combat stats |
| E5 | H4 Path1 unitToLoadout honesty | PASS | sparse omits AD/armor; keeps HP when known |
| E6 | H5 no odds copy | PASS | model edge present; odds % absent |
| E7 | H2/H4 overlay never on Send | PASS | productSendAttachesResearchActions=false |

## KEEP / DISCARD

- **KEEP (research scaffolding):** `scripts/fo_r17_send_parity_smoke.ts` + `npm run fo:send-smoke`
- **No product FA KEEP** — did not tune fightAgreement; authoritative S0 still 0.228
- **No invent** — E2 marks disclosed as parity probes only
