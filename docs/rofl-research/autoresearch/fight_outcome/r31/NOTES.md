# R31 NOTES — galio-burst-product

**Branch:** `adv/fo-r31-galio-burst-product`  
**Worktree:** `~/.codex/worktrees/rofl-fo-r31`  
**never_edited_parent code:** true (docs mirrored to parent `fight_outcome/r31/`)  
**FA ≠ odds**

## Verdict: KEEP

| | S0 FA | S1 FA | c1 burst modelKilled | c1 burst marks |
|--|---:|---:|:---:|---:|
| **before (R30)** | **0.5897** | **0.5620** | N | 0 |
| **after e40 product** | **0.6381** | **0.5620** | **Y** | **2** |
| Δ | **+0.0484** | **0** | | |

`|lethErr|=0.635 ≤ 0.75` on check01 burst.

## What shipped

- **HP burst onset:** legacy non-increasing walk (`detectKillBurstStartMs` exported) — do not heal-tolerate (hurts Olaf/Camille burst FA).
- **Mark domain:** `--pre-burst-lead 2.5` / `markPreBurstSkillLeadSec: 2.5` loads real skills before burstStart; remaps onto CUSUM engage @ share 1.
- Galio burst keeps **E + Q** (W needs lead≥3.34 → S1 regress; disclosed residual).
- Pre-engage lead stays **0** on product (R24 lesson + Olaf full overkill).

## Rejected

- Heal-tolerant / plateau-clip HP onset
- R24 e49 lead/far/maxMarks
- Pre-burst lead 3.5 (W) — S1 FA −0.024
- Global pre-engage lead — Olaf full lethErr 0.33→1.14

## Confidence

fightAgreement = kill-window suite agreement — **NOT** win odds / pBlue-pRed %.
