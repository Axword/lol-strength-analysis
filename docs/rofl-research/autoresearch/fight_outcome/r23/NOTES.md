# R23 NOTES — path1-lethal2

**Branch:** `adv/fo-r23-path1-lethal2`  
**Worktree:** `~/.codex/worktrees/rofl-fo-r23`  
**never_edited_parent:** true (docs mirrored to parent `fight_outcome/r23/` only)  
**Unfreeze 0.9683:** authorized — no `best.json` product rewrite (S1 never improves)

## Path1 FA (product selector cusum_engage_then_skills)

| | FA | pass |
|--|---:|-----:|
| **before (e0 / R05)** | **0.2279** | 0 |
| **after best research (e7)** | **0.2503** | 0 |
| **after S1-flat research (e5)** | **0.2326** | 0 |
| product defaults after | **0.2279** (unchanged) | 0 |

Δ research peak = **+0.0224** (e7). Δ S1-flat = **+0.0047** (e5). No product KEEP.

## Root cause (Galio→Trundle)

CUSUM `engageSec=15.358` fires **0.334s after** Galio W (`15.024`). Product post-engage filter drops W → only E+Q → `modelEndHp=306`. `assistProbeAllySkills2s=0` (no multi-caster bailout). Burst still 0 marks.

## What moved

- **e5** (`preEngageOpenerSec=0.5` + `maxPost=3`): sparse gate keeps Galio W, skips Olaf early poke; Galio **model kill** restored; `|lethErr|=2.61` still >0.75 → `lethalHit=0`; **S1 FA flat 0.514**.
- **e7** (e5 + `--no-aa-at-mark`): S0 peak 0.250 via Olaf death-coupled (R18 pattern); Galio no kill; **S1 regress 0.390**.
- **e10** (e5 + `--aa-filler`): Galio `|lethErr| 2.61→1.13`; S1 slight regress 0.506.
- Naive opener without sparse (e1): FA **0.193** (Olaf collateral).

## S1 holdout (2970137, no tune)

| config | FA |
|--------|---:|
| product e0 | **0.5143** |
| e5 sparse | **0.5143** (flat) |
| e10 aa-filler | 0.5057 |
| e7 death-coupled | 0.3900 |

Mandate: **no product KEEP without S1 improve** → product `preEngageOpenerSec` stays **0**.

## Keepable harness (not product)

- `selectKillWindowMarks({ preEngageOpenerSec, preEngageOpenerMaxPostMarks })`
- CLI: `--pre-engage-opener-sec` / `--pre-engage-opener-max-post`
- `--suite 2970132-g1` → `crosschecks-2970132-g1.json`
- Scorer S0 wire → Path1 primary file (not holdout / not 2970110 proxy label)

## Confidence

fightAgreement = kill-window suite agreement — **NOT** win odds / pBlue-pRed %.
