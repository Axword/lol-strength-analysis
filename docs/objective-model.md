# Objective model (auditable combat effects)

Accuracy stance: **apply only what the combat engine can represent exactly**. Timed or conditional procs are **disclosed and excluded** — never replaced by fabricated flat, on-AA, or always-on damage.

Source of truth for values is Riot / League wiki mechanics stated in prose below. This document does not fetch remote APIs at runtime.

## Data contract: `TeamObjectives.dragons`

- Each entry is one **actual elemental dragon kill**.
- The **fourth** kill is a real permanent stack **and** grants Soul (`hasSoul` / `soulType`). It is **not** a soul-only sentinel.
- `elementalDragons` / `countDragonStacks` keep all real kills. Only the legacy literal `"elemental"` (pseudo-label) is ignored.
- Fight-odds prior (`gameStateOdds`) counts four real kills **plus** the soul bonus — it must not subtract one stack merely because `hasSoul` is true.

## Permanent elemental dragons (applied vs disclosed)

| Type | Effect | Combat treatment |
|------|--------|------------------|
| Infernal | +3% total AD/AP per matching stack | **Applied** (`adPercent` / `apPercent`) |
| Mountain | +5% armor/MR per stack | **Applied** (`armorPercent` / `mrPercent`) |
| Hextech | +5 ability haste and +5% attack speed per stack | **Applied** |
| Chemtech | +6% tenacity and +6% heal/shield power per stack | **Tracked only** (career attribution). Not combat-applied — no HSP/tenacity consumer in combat/utility yet |
| Cloud | +5% slow resist and +5% **out-of-combat** MS per stack | **Disclosed only** — OoC MS must not inflate in-combat `movespeed` |
| Ocean | Restores 2% missing HP per 5 seconds | **Disclosed only** — can tick in combat; not invented as heal without timed regen |

Authoritative `liveStats` / absolute dummy pins for AD, AP, armor, MR, attack speed, or movespeed are **not re-buffed** — Riot live values already include active objective buffs. Ability haste may still apply (no live AH channel).

## Manual theorycraft stacking (not live pins)

Local evidence and formulas live in `src/engine/statStacking.ts`. Do not claim wiki exactness beyond these sources:

| Rule | Formula / order | Source in repo |
|------|-----------------|----------------|
| Per-level growth | `base + perLevel × (n−1)×(0.7025 + 0.0175×(n−1))` | Riot growth curve (documented); replaces naive `×(n−1)` |
| Attack speed | `baseAS + bonusAS% × AS_ratio` where item `attackSpeed: 0.5` means +50% bonus AS; Hextech adds through the same ratio | CORE ratios from Meraki `champions-full.json` `stats.attackSpeedRatio.flat`; kits without ratio fall back to `attackspeed` |
| Rabadon + Baron + Infernal | `(item/base flat AP + Baron flat) × (1+Infernal) × (1+0.30)` | Item 3089 Magical Opus 30% from `items-summoners-rift.json` |
| Cloud Soul MS | `softCap(rawFlat × (1+0.15))` once; bands 415 / 490 | Wiki soft-cap algebra; live MS remains absolute |

**xH integration:** Defender objective-resolved MS (via `resolveFighterCombatStats`) is the `baseMs` passed into `effectiveTargetMs` / `estimateXh` on both aggregate and timed paths (`scalePacketsWithXh` → `meanXhRowVsEnemies`). Authoritative `liveStats.movespeed` still wins and is never re-buffed. Caster Hextech AH reaches `skillshotCastsForFight` / dodge bands through optional resolved caster stats.

## Dragon souls (this batch)

| Soul | Exact effect (wiki) | Treatment |
|------|---------------------|-----------|
| Cloud | +15% passive MS; +60% MS for 6s after R (30s CD) | **Passive +15% applied** where no live MS override; R burst disclosed only |
| Chemtech | +13% damage dealt and damage reduction while own HP ≤ 50% | Helper `fightDamageAmp(obj, hpPct)` is thresholded (0 above 50%, 0.13 at/below). **Not** applied as always-on team `damageAmp`/`damageReduction` |
| Infernal | Adaptive explosion 100 + 22.5% bAD + 13.5% AP + 2.75% bHP, 3s CD | Disclosed only — **zero** fake packets |
| Hextech | 25–50 true by level, 8s CD | Disclosed only |
| Mountain | Shield 220 + 16% bAD + 12% AP + 12% bHP after 5s without damage | Disclosed only |
| Ocean | Heal 150 + 26% bAD + 17% AP + 7% bHP + mana over 4s | Disclosed only |

There is **no** `trueDamageOnHit` objective path. No soul or Elder effect emits fabricated per-AA true damage.

## Elder dragon

- Burn: 75–225 true over 2.25s, plus execute below 20% HP.
- **Disclosed only** until timed proc / threshold state exists.
- Zero fabricated per-AA true damage, amp, DR, sustain, or shield.

## Hand of Baron (Patch 9.2)

Official published anchors (AD / AP at Baron **slain** minute):

| Minute | AD | AP |
|--------|----|----|
| 20:00 | 12 | 20 |
| 30:00 | 26 | 43 |
| 40:00 | 48 | 80 |

- Values are **fixed at slain time** (do not keep scaling while the buff is held).
- Riot Patch 9.2 states scaling **accelerates over time** and increments every second. Riot does **not** publish the hidden in-between formula.
- This repo uses a continuous **quadratic** through the three anchors (separately for AD and AP), clamped before 20:00 and after 40:00. The curve between anchors is **inferred**; the anchors are official.
- Slain time: when `baronEndsAtMs` is known → `endsAtMs / 1000 − 180`; otherwise current game time with an explicit fallback disclosure.
- **No omnivamp** on the champion Hand of Baron buff (AD/AP + minion empower only).

## Void Grubs (V26.11, structure-only)

- Max 3 stacks. Touch-of-the-Void true ticks every 0.5s:
  - Melee: `[0, 4, 12, 16]`
  - Ranged: `[0, 2, 6, 8]`
- Hunger of the Void at 3 stacks (Voidmite cadence) — structure combat only.
- **Never** applied to champion PvP DPS or fight odds.
- Gold-equivalent `8s / 900 HP / 120g` is a **documented article scenario** (brief-ceiling plate progress), not live turret forecasting.

## Modifier contract

`ObjectiveCombatMods` exposes:

- `applied` — effects written into `CombatStats` / packet multipliers **where no authoritative live override blocks the field**
- `disclosedOnly` — exact wiki effects excluded or tracked-only (missing consumer / timing / threshold)
- `notes` — combined convenience list (`[disclosed]` prefix on disclosed lines)

Assumptions footers prioritize Blue/Red objective applied+disclosed lines (and the live-override provenance caveat) ahead of optional item/Gnar/dummy detail so the 16-line cap cannot starve them. Do not claim “wiki-correct” for unmodeled procs.

## Career attribution

`attributeDrakeBuffs` may tag conditional / unmodeled souls (e.g. Chemtech Soul ≤50% HP) but **quantified** Chem Soul amp/DR stays **zero** without threshold-time evidence.

## Tests

```bash
npm run test:objectives
```

Covers fourth-dragon stacks, permanent values, Cloud OoC vs Cloud Soul, Chem helper threshold, Baron anchors + slain inference, no omnivamp, no fake Soul/Elder fields, grub tables, and `gameStateOdds` fourth-dragon counting.
