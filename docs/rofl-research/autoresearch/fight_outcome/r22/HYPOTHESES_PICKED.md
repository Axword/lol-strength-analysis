# R22 HYPOTHESES — camille-q-wire

Auto-picked (no human choice):

1. **H1 Wire first-cast Q from wiki %AD + attackReset** (KEEP if packets + timed plan include Q)
   - Evidence: lolwiki Bonus Physical Damage 20–40% AD; Meraki ratios match; Darius W empowered-AA packet pattern.
   - Same-match: 2970110 Camille Q casts=84 (4 in c1 window); 2970132 Q casts=71.
   - PE: PrecisionProtocol/CamilleQ float names = 0 (product_ready/r04) — refuse invent coeffs from PE.

2. **H2 Measure Path1 2970132 S0 FA** (measure only; expect flat)
   - Path1 S0 killers = Galio/Olaf — Camille Q kit not on FA pulse path.
   - gate_action still uses continuous `killWindowPulseDamage` (simulateMatchup pulse), not per-slot kit marks.

3. **H3 PE impossibility sharpener** (KEEP disclose)
   - Cannot PE-prove Q damage coefficients or recast true-mix from same-match ROFL wire.
   - Recast-after-1.5s true damage (wiki level mix) left unwired — needs cast-state; no invent.

Deferred: fixture-remap ranks/HP; inventing PE floats; claiming FA lift from Q on Path1 S0.
