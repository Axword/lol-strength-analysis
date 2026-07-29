# R44 hypotheses (auto-picked)

1. **H0 baseline** — Product density + legacy burst-window truth → c1-burst F1=0 (truth=0 model=1).
2. **H1 truth=burst-only ablate** — `--truth-burst-window-only` confirms legacy F1=0.
3. **H2 domain expand no remap** — Lead skills enter truth but negative tSec vs remapped model → F1=0.
4. **H3 domain + engage remap** — Mirror R31 mark remap for truth matching → F1=0.667 KEEP.
5. **H4 tau 0.15** — Same F1=0.667 (matches already |dt|≈0).
6. **H5 ally truth** — Extra ally skill lowers recall → F1=0.500 (discard for default).
7. **H6 no pre-burst lead** — Removes mark domain; c1-burst F1 back to 0 (confirms coupling).
8. **H7 lead 3.5** — Pulls Galio W; truth=3 model=1 → F1=0.500 (worse; R31 lead 2.5 stands).
9. **H8 zero-dmg echo** — Pad unmatched truth → raw F1=1.0 REJECT (forbid #13).

Product KEEP = H3 only (S0 FA↑ S1 flat). Secondary actionCoverage only — not fightOutcomeGate.
