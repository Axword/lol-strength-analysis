# R49 hypotheses — s1-passrate-vayne-cass

**Mandate:** S1 pass 0.5→↑ via Vayne burst miss-kill + Cassio coverage; no S0 regress. FA≠odds. Never invent.

**Baseline (STATUS / R43 compound):** S0 FA 0.9304 pass 0.667 · S1 FA 0.7628 pass 0.500

## Diagnosis (from stack_r43 eval + slim SQLite)

1. **Vayne→Ambessa c1_burst** miss-kill: `modelEndHp≈38`, `lethErrorSec=null`, marks=1 (Q opener only). Full window kills late (`|leth|≈2.05`).
2. Meraki Vayne: W Silver Bolts modeled as CD-8 cast (passive on-hit); R Final Hour pulse=0 (steroid AD 97→132 not re-pinned).
3. **Cassio→Viktor** already `windowOk`; coverage weak (`actionF1≈0.43–0.50`, truth 18 skills / model 5) — E-only marks, Q/W thinned.

## Hypotheses

| ID | Lever | Expected |
|----|-------|----------|
| H0 | Baseline remesaure (stack dens 1.0/gap0.4) | Confirm FA/pass |
| H1 | Vayne CORE: Q tumble + Silver Bolt fold into Q; R utility | Burst kill / leth↑ |
| H2 | H1 + E Condemn wall bonus (×1.5 when R ranked) | Extra physical |
| H3 | `--repin-each-mark` (honest AD after R) | Post-R Q/AA use pin AD |
| H4 | `--finish-aa-max 6` | Close 38 HP residual |
| H5 | `--near-kill-sec 2` (product default) | More finish marks |
| H6 | Cassio denser E: `--mark-min-gap 0.25` dens1 | Coverage↑; watch overkill |
| H7 | Cassio CORE: Twin Fang poison amp ×1.2 when Q ranked | Coverage/leth honesty |
| H8 | H1+H3 compound | Best Vayne pass flip |
| H9 | Ablate: global R-pulse 0.4 | Expect S0 regress (discard) |

KEEP iff S0 FA↑ and S1 flat+ (prefer pass↑). No pathFollow product.
