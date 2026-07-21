# Pass-8 STRATEGY — bands↔packet fidelity residual only

**Axis:** strategy (σ_juke ready-state + dodge bands → CombatResult / packet fidelity)  
**Status:** `KEEP_CANDIDATE`  
**Constraint:** critique + snippets only; **do not edit** production files in this pass.  
**Eval at write:** `math_pass_rate=158/158 (1.0000)` post Pass-7 KEEP. Deepen residual only; do not re-propose landed KEEP work; no `BASE×ZONE×VISION`; **no new mobility×P(hit) tags**.

---

## 0. Already landed (do NOT re-propose)

| Pass | Landed |
|------|--------|
| 1 | Flash envelope for worst; windup dodge window; ready budgets; soft `dodgeScale` |
| 2 | Precommit residual; `bands.mix` via `neMixCorridorVal`; `flashCdRemainingSec`; combat Flash/dash ready |
| 3 | Ghost/charges/CC-break; NE unknown→packet mix + π_down; `MatchupResult.xhDodgeBand`; Expected-cell hint → dodge-budget copy |
| 4 | CombatResult xH dodge row (`DodgeCell`); MS / hard-CC into `meanXhVsEnemies`→`estimateXh`; smarter stub range (first skillshot) |
| 5 | `averageXhRows` / `scaleXhBands` / `ghostBuffActive`; shared `estimateXhRowVsEnemy` + wards; `xhPacketPolicy` + mix/typical highlight; eval U–W |
| 6 | Fight `outgoingUtility` into dodge bands; `effectiveTargetMs` (autos MS law); Ghost trusts `liveMs` arg; remake hint “trade under packet xH”; caption mix edge |
| 7 | Ghost predicate on raw `liveMs` (not slowed); fallback MS parity; `fightDodgeBands` NvM × kit-skillshot average |

Eval strategy probes through Pass-7 (envelope / mix / precommit / CD / charges / NE / Ghost×slow liveMs / avg bands / utilMult / effectiveTargetMs) are green. Residual is **cast-set / weight / OOR / policy parity between displayed bands and Expected packet xH**, not another Ghost predicate, `jukeFromBudget` rewrite, or mobility×P(hit) tag.

---

## 1. Critique (Pass-8 failure modes)

### 1.1 Smoking gun: dodge cast set ≠ packet skillshot set

Pass-7 `fightDodgeBands` averages **every kit ability with `skillshot: true`**:

```ts
const ranges =
  CHAMPIONS[b.championId]?.abilities
    ?.filter((a) => a.skillshot)
    .map((a) => a.range) ?? [900]
```

Packets (`collectFighterDamage` → `scalePacketsWithXh`) only attach xH to skillshot **damage packets** that survive:

- `ranks[slot] > 0`
- `abilityBudget` / HP omit
- `mode === 'short'` skips `R`
- `lockedOut` engage filtering
- `abilityCastsInFight` multi-cast (same slot counted N times)

So low-HP short trades, unranked ultimates, and multi-cast Qs can show a dodge row whose typical/mix disagree with `avgXh` / Expected remake even though both call `meanXhRowVsEnemies`.

**Prefer this deepen over any new mobility×P(hit) tag.** Build dodge rows from the **same cast multiset** packets use (slot × casts), not the raw kit skillshot list.

### 1.2 OOR rows dropped from bands, kept as 0 in packets

```ts
// fightDodgeBands
return averageXhRows(rows.filter((r) => r.bands)).bands

// meanXhRowVsEnemies — fully OOR with positions
if (caster.position && living.some((e) => e.position)) return { xH: 0 } // no bands
```

`scalePacketsWithXh` still writes `xH: 0` onto that skillshot packet. Lux R beyond range while Q/E hit: **dodge typical averages Q+E only; `avgXh` includes R=0**. Filter-to-banded-rows is the product fidelity bug; do not invent a new σ tag to “fix” the mismatch.

### 1.3 `xhPacketPolicy` is first-red Flash, not fight-average mix presence

```ts
xhPacketPolicy: (() => {
  const red = input.red.find(isAlive)
  const flash = flashReadyFromLoadout(red)
  return flash === undefined ? 'mix' : 'typical'
})(),
```

`averageXhRows` sets `mix` only when **every** row has mix. NvM (one Flash-unknown, one Flash-up) → policy `'mix'` while averaged `mix === undefined` → caption/highlight fall back to typical (Pass-6 caption edge). Derive policy from the **returned** `xhDodgeBand` (mix≠null ⇒ mix), or from the same row multiset — not a separate first-enemy Flash peek.

### 1.4 Shared row still omits ability missile geo (both paths)

`abilityXhPreview` passes `missileWidth` / `missileSpeed` / `releaseDelaySec`; combat `estimateXhRowVsEnemy` only passes `abilityRange`. Packets and bands agree with each other but disagree with kit geo. When aligning cast sets, plumb slot→ability missile fields into the shared row helper so both surfaces use the same σ corridor. Still **no** new mobility tags.

### 1.5 Incomplete Pass-7 eval locks (debt)

Landed Pass-7 strategy assert only:

- Ghost stays active under slow when raw liveMs buffed  

`void fightDodgeBands` — AF (multi bands ordered), AE (CC flattens fight bands), AD (slow→row σ/xH), and full AC (Ghost flag raises σ_juke vs same slowed MS) never shipped. Pass-8 should lock cast-set / OOR / policy invariants **and** finish that debt without softening 158.

### 1.6 Out of scope (do not chase this pass)

- New MobilityClass / zone / vision multiplicative tags  
- Rewriting Flash envelope, precommit, π priors, charges, CC-break, `neMixCorridorVal`, `jukeFromBudget`  
- Hexflash second envelope  
- Geo width / aim SDN / belief LKP / xHm empirics (except plumbing existing ability missile fields into the shared combat row)  
- Re-proposing Pass-7 Ghost×slow split / fallback MS / `fightDodgeBands` export  
- BASE×ZONE×VISION  
- Red→blue second dodge row (attacker POV blue→red is enough unless headroom)  
- Dropping utilMult slow channel (dual channel with σ_juke MS is intentional)

---

## 2. Minimal patch (orchestrator apply order)

Hard rules: no `BASE×ZONE×VISION`; no PN; strategy only varies σ_juke **inputs** + combat/UI plumbing. Prefer bands↔packet fidelity over new mobility×P(hit) tags.

### 2.1 Cast multiset helper (highest priority)

```ts
type XhCast = { slot: AbilitySlot; range: number; ability: AbilityDefinition }

/** Same filters as collectFighterDamage skillshot loop (ranks / budget / short / lockedOut). */
function skillshotCastsForFight(
  loadout: FighterLoadout,
  mode: TradeMode,
  lockedOut: boolean,
): XhCast[] {
  const champ = CHAMPIONS[loadout.championId]
  if (!champ) return []
  const ranks = ranksFromLoadout(loadout)
  const hpPct = hpPctOf(loadout, buildStats(loadout))
  const budget = abilityBudget(hpPct, mode, ranks.R > 0)
  const out: XhCast[] = []
  for (const ability of champ.abilities) {
    if (!ability.skillshot) continue
    if (mode === 'short' && ability.slot === 'R') continue
    if (!budget.allowed.has(ability.slot)) continue
    if (ranks[ability.slot] <= 0) continue
    if (lockedOut && ability.engageCc) continue
    const casts = abilityCastsInFight(mode, ability.slot, buildStats(loadout).abilityHaste)
    for (let c = 0; c < Math.max(1, casts); c++) {
      out.push({ slot: ability.slot, range: ability.range, ability })
    }
  }
  return out
}
```

Optional tighten: only include slots that actually emitted a `skillshot: true` damage packet (mirrors empty-damage utility skillshots). Prefer cast-list parity first; packet-presence filter if eval shows leftover drift.

### 2.2 `fightDodgeBands` = average over that multiset (incl. OOR zeros)

```ts
export function fightDodgeBands(
  casters: FighterLoadout[],
  enemies: FighterLoadout[],
  outgoing: ResolvedUtility,
  visionUnits: VisionUnit[],
  casterTeam: 'blue' | 'red',
  wards?: VisionWard[],
  mode: TradeMode = 'extended',
): XhRow['bands'] {
  const livingC = casters.filter(isAlive)
  const livingE = enemies.filter(isAlive)
  if (!livingC.length || !livingE.length) return undefined
  const rows = livingC.flatMap((b) =>
    skillshotCastsForFight(b, mode, /* lockedOut */ false).map((cast) => {
      const row = meanXhRowVsEnemies(
        b, livingE, cast.range, outgoing, visionUnits, casterTeam, wards,
        cast.ability, // → missileWidth / missileSpeed / releaseDelaySec
      )
      // Keep OOR { xH: 0 } in the average — synthesize flat bands at 0 so
      // filter(r => r.bands) no longer drops them.
      if (!row.bands) {
        return { xH: row.xH, bands: { worst: row.xH, typical: row.xH, best: row.xH } }
      }
      return row
    }),
  )
  if (!rows.length) return undefined
  return averageXhRows(rows).bands
}
```

Wire `simulateMatchup` with the same `TradeMode` primary uses (`input.mode` / extended default). Do **not** change Ghost/MS helpers.

### 2.3 Plumb ability missile fields into shared row

```ts
function estimateXhRowVsEnemy(…, ability?: AbilityDefinition): XhRow | null {
  const est = estimateXh({
    …
    abilityRange: ability?.range ?? abilityRange,
    missileWidth: ability?.missileWidth,
    missileSpeed: ability?.missileSpeed,
    releaseDelaySec: ability?.releaseDelaySec,
    skillshotLengthPenalty: (ability?.range ?? abilityRange) >= 900,
    // MS / Ghost / CC / vision unchanged from Pass-7
  })
  …
}
```

`scalePacketsWithXh` should resolve the same ability by `p.slot` and pass it through `meanXhVsEnemies` → row helper (one path).

### 2.4 Policy from returned bands

```ts
const bands = fightDodgeBands(…, primaryMode)
xhDodgeBand: bands,
xhPacketPolicy: bands?.mix != null ? 'mix' : 'typical',
```

Caption/active-cell already key off mix≠null — this removes the first-red Flash desync. Tiny UI change only if caption still lies; prefer engine fix.

### 2.5 Optional: expose scalar parity for eval

```ts
export function fightPacketXhMean(…): number | undefined {
  const bands = fightDodgeBands(…)
  // or averageXhRows(…).xH over the same multiset
  return averageXhRows(rows).xH
}
```

Assert `|fightPacketXhMean − activeBandCell| < ε` under expected/mix policy (ε ~ 1e-9 when policy matches).

---

## 3. New invariants (add to `eval-xh-math.ts` — do not soften 158)

```ts
// AG. Cast-set: short mode / unranked R excluded from fightDodgeBands
const full = fightDodgeBands([luxRankedR], [target], empty, vision, 'blue', undefined, 'extended')
const short = fightDodgeBands([luxRankedR], [target], empty, vision, 'blue', undefined, 'short')
assert('short omits R from band avg (or differs when R range ≠ Q/E)', /* document */)
const noR = fightDodgeBands([luxRanksR0], [target], empty, vision, 'blue', undefined, 'extended')
assert('unranked R omitted', /* noR uses Q+E only — ordered bands */)

// AH. OOR skillshot participates as ~0, does not vanish
const near = fightDodgeBands([caster], [inRange], …)
const mixed = fightDodgeBands([caster], [inRange], …) // with a long skillshot forced OOR via range stub
// or unit-level: averageXhRows keeps {xH:0, bands flat} in mean
assert('OOR zero pulls typical down vs in-range-only filter', mixed!.typical < near!.typical + 1e-9)

// AI. Policy ↔ mix presence
assert('mix≠null ⇒ policy mix', /* pure helper */)
assert('all Flash-up ⇒ mix undefined ⇒ policy typical', …)

// AJ. Shared missile geo: wider kit missile → higher row xH (same range)
assert('width plumbed through combat row', wide.xH + 1e-9 >= thin.xH)

// Finish Pass-7 debt (AC–AF) if still absent:
// AC Ghost flag raises σ_juke vs same slowed MS
// AD slow → row xH ≥ open
// AE CC flattens fight bands
// AF multi-range bands ordered
```

Regression watch: Pass-1–7 strategy asserts; Ghost×slow liveMs; Flash-up ⇒ mix===typical; utilMult scales bands; wards softVision; kit tag alone.

---

## 4. arXiv / theory cites (Pass-8 deepen)

| id / ref | use |
|----------|-----|
| [arXiv:2604.17811](https://arxiv.org/abs/2604.17811) Kill-prob vs miss | Displayed SSKP bands must average the **same cast hypothesis set** as Expected packet xH (budget × ranks × multi-cast × OOR zeros) |
| [arXiv:2511.21633](https://arxiv.org/abs/2511.21633) Bang-Bang Evasion | Dodge envelope is a report of σ_juke hypotheses already in the packet path — do not retag mobility |
| [arXiv:1804.05021](https://arxiv.org/abs/1804.05021) / [2410.02966](https://arxiv.org/abs/2410.02966) Fitts / SDN | Missile width/speed enter σ corridor via existing aim/geo; plumb kit fields, do not invent Ghost×hit |
| Classic cookie-cutter / Washburn | UI % still \(P(\|M\|<R)\) under σ; no PN / BASE×ZONE×VISION |

---

## 5. Expected gains vs regressions

| gap | after Pass-8 apply |
|-----|--------------------|
| Kit-all skillshots ≠ budgeted packets | `skillshotCastsForFight` multiset (ranks / budget / short / casts) |
| OOR dropped from bands, zeroed in packets | Keep OOR rows as flat bands at packet xH |
| Policy from first red Flash | Policy from returned `bands.mix` |
| Combat row ignores kit missile geo | Pass width/speed/release into shared `estimateXh` |
| Pass-7 AF/AE/AD incomplete | Locks AG–AJ (+ AC–AF debt) |

**Out of scope:** geo/aim/vision formula changes; new MobilityClass hit tags; BASE×ZONE×VISION; Hexflash; rewriting landed Pass-1–7 KEEP.

---

## 6. Decision

**`KEEP_CANDIDATE`**

Rationale: Pass-7 closed Ghost×slow + fallback MS + NvM `fightDodgeBands` (158/158), but the dodge row still enumerates raw kit skillshots, drops OOR rows that packets zero, and peeks first-enemy Flash for policy — so product bands can still disagree with Expected `avgXh`.

1. Average bands over the same cast multiset as `scalePacketsWithXh` (budget / ranks / short / multi-cast); keep OOR as zero-weight rows.  
2. Derive `xhPacketPolicy` from returned mix; plumb ability missile fields into the shared row.  
3. Lock eval AG–AJ (+ finish Pass-7 AC–AF debt).

Orchestrator should apply §§2–3 in `combat.ts` (+ thin exports for eval), re-run `npm run eval:xh`, keep only if rate stays 158/158 before new asserts, then ≥ all new checks.

**Verdict: KEEP_CANDIDATE — deepen bands↔packet cast-set / OOR / policy fidelity; no new mobility×P(hit) tags.**
