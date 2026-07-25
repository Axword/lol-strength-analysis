# R21 NOTES — path1-falsekill

## Next action
Absorb: **NO product KEEP**. FK stop exists as research recipe; needs R18 lethal restore without re-FK + S1 non-regress.

## State
- Worktree: `~/.codex/worktrees/rofl-fo-r21` · branch `adv/fo-r21-path1-falsekill`
- never_edited_parent: true (docs synced to parent `fight_outcome/r21/` only)
- Product selectors unchanged: `cusum_engage_then_skills`, continuous pulse default

## Headline numbers (FA ≠ win odds)

### False-kill (2970110 c3-full, actualEndHp=210)
| recipe | FK? | modelEnd | earlyMAE | hardFail | lethals c1/c2 |
|--------|-----|----------|----------|----------|---------------|
| e0b product continuous | **YES** | 0 | 580 | no | 4/4 |
| e4 slot_ability noAA | NO | 507 | 1134 | **YES** | 1/4 |
| e14 slot+idleFollow+noAA+share0.55 | **NO** | 814 | 658 | no | 0/4 |

**falseKillRate (survivor windows actualEndHp>40):** 0.50 → **0.00** (e14)

### Path1 2970132 FA (product cusum density 1.0/1.2)
| id | suite FA | honest FA | note |
|----|----------|-----------|------|
| e0 continuous | **0.2946** | 0.2946 | STATUS ref 0.228 was R05; R19/R21 e0 = 0.2946 |
| e7 slot+idleFollow | 0.3890 | 0.3890 | early↑; starves c2 lethals |
| e8 slot+idle+aaFiller | **0.5561** | 0.4228 | best Path1 lift; S1 regress |

### S1 2970137 (holdout — no tune)
| id | FA | vs s1_e0 |
|----|-----|----------|
| s1_e0 continuous | **0.4563** | — |
| s1_e7 / e8 / e14 | 0.34 / 0.35 / 0.29 | all worse |

## Mechanism
Skill marks were applying a **full 0.4s continuous `simulateMatchup` DPS dump** (includes AAs + all abilities), then `aaAtEachMark` double-counted. Path1 Olaf Q at engage could early-zero Camille (~18s early). Survivor FK (Ezreal→LeeSin endHp=210) is the same over-damage class.

New research APIs (defaults = product continuous / idleFollow false):
- `pulseMode: 'continuous' | 'slot_ability'`
- `killerPulseShare`
- `idleFollowActual` (R19 coord; not product default)

## Coordinate
- **R18 lethal:** e14/e7 starve true kills — do not merge FK recipe as product without lethal restore
- **R19 early:** idleFollow helps early hard-fail; R19 owns productizing it
- **R13/R14:** actionF1 secondary only; used harness actionCoverage as-is (no echo credit)

## Verdict
**NO_KEEP** for product. Research evidence: FK stoppable via slot-scoped pulses; Path1 FA measurable; S1 gate blocks KEEP.
