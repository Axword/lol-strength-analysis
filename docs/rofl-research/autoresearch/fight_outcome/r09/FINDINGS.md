# R09 FINDINGS — unfreeze-regen (F3.H3)

**Verdict:** no KEEP. Best fightAgreement remains E0 baseline **0.5351** (Δ = 0). All regen variants worse on S0-2970110-g1.

## What shipped (research path, default off)

- `killWindowOverlay.simulateKillWindowSeries` optional `regen` (combat / listed / opener_only / finish_only / split)
- Idle/pre-engage rate **0** (false-all-in gate preserved)
- Listed rate from `buildStats` champ+items (or `--regen-hps`); combat residual default ×0.3
- Opener vs finish fracs stay separate
- Harness CLI: `--regen`, `--regen-frac`, `--regen-opener-frac`, `--regen-finish-frac`, `--regen-hps`, `--regen-finish-start`
- Engine↔harness parity: harness delegates only

## Best delta

| id | regen | fightAgreement | Δ vs E0 |
|----|-------|---------------:|--------:|
| e0 | off | **0.5351** | 0 |
| e3 | combat + product cusum | 0.4848 | −0.0503 |
| e11 | listed opener_only | 0.4758 | −0.0593 |

## Why regen hurt

Regen raises defender HP between marks → more false-survive / worse lethalHit on checks that already underkill late, without fixing check02 burst path MAE. Opener-only and finish-only splits both lost vs hold-flat.

## Still true

- fightAgreement ≠ win odds / pBlue pRed = model edge only
- Product selectors unchanged (non-drop)
- best.json not updated (no FA improvement)
- Unfreeze 0.9683 authorized; KEEP requires FA beat without invent
