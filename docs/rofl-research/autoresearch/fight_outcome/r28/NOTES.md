# R28 NOTES — galio-kit

**Branch:** `adv/fo-r28-galio-kit`  
**Worktree:** `/Users/river/.codex/worktrees/rofl-fo-r28`  
**never_edited_parent:** true (docs mirrored to parent `fight_outcome/r28/` only)  
**Coordinate:** R24 = engage/lethal marks; R28 = kit/utility/rotation

## Verdict

| | |
|--|--|
| **Product KEEP** | **YES** — CORE Galio in `src/data/champions.ts` |
| **check01 full `modelKilled`** | **true** (`\|lethErr\|=0.36≤0.75`) |
| **check01 burst `modelKilled`** | **false** (0 marks — R24) |
| FA ≠ odds | fightAgreement is kill-window suite agreement only |

## Path1 S0 (same knobs: cusum, idleFollow, nearKill2, gap1, dense1.2)

| config | FA | pass | Galio→Trundle full |
|--------|---:|-----:|--------------------|
| **e0** no CORE Galio | **0.3440** | 0 | endHp≈376, no kill |
| **e6** CORE Galio (KEEP) | **0.4130** | **0.167** | kill, lethErr **−0.36**, windowOk |

ΔS0 = **+0.069**. c1_full windowScore **0.91** (lethalHit+early+path).

## S1 holdout (2970137 — no tune)

| config | FA |
|--------|---:|
| e0b no CORE | **0.5609** |
| e6b with CORE | **0.5609** |

Flat (S1 killers not Galio). **Not regress** → KEEP allowed.

## Kit deltas (vs GAME Galio)

- **Q:** gust + tornado `%maxHP` (was gust-only)
- **W:** charged damage + **taunt utility** (hardCc/slow/DR) — never skip for 0 dmg
- **E/R:** engageCc + hardCc; E range 650
- **P:** Colossal Smash blended (e1 full → leth −1.79; e5 soft → +2.61; e6 blend → **−0.36**)

## Experiment ladder (check01 full)

| id | kill | lethErr | endHp | note |
|----|------|--------:|------:|------|
| e0 | N | — | 376 | GAME kit baseline |
| e1 | Y | −1.79 | 0 | full tornado+maxW+full smash — early |
| e2–e4 | N | — | 212→28 | soften toward kill |
| e5 | Y | +2.61 | 0 | soft smash — late |
| **e6** | **Y** | **−0.36** | **0** | **KEEP** |
| e7 | Y | −0.36 | 0 | perSlotPulse flat |
| e8/e9 | N full / Y burst | burst 0.65 | — | timed cusum_gate — Olaf regress; research only |

## R24 handoff

Product `gate_action` burst still **0 skill marks**. Timed `cusum_gate`+kit can kill burst (leth≈0.65) but loses Olaf full kills — do **not** flip product mode. Prefer R24 `markPreEngageLead` / finish-window for W@498682.

## Confidence

fightAgreement = kill-window suite agreement — **NOT** win odds / pBlue-pRed %.
