# Pass-9 STRATEGY — bands↔packet weight / soft-lock fidelity residual

**Axis:** strategy (σ_juke ready-state + dodge bands → CombatResult / packet fidelity)  
**Status:** `KEEP_CANDIDATE`  
**Constraint:** critique + snippets only; **do not edit** production files in this pass.  
**Eval at write:** `math_pass_rate=195/195 (1.0000)` post Pass-8 KEEP. Deepen residual only; do not re-propose landed KEEP work; no `BASE×ZONE×VISION`; **no new mobility×P(hit) tags**.

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
| 8 | `skillshotCastsForFight` cast multiset; OOR zeros kept in `fightDodgeBands`; `xhPacketPolicy` from mix≠typical; missile width/speed/release plumbed into combat row |

Eval strategy probes through Pass-8 (cast-set short/unranked R, OOR synthetic pull-down, Flash-up mix≡typical, Flash-unknown mix&lt;typical, wider missile corridor) are green. σ_juke ready-state (Flash envelope / Ghost×slow / charges / CC-break / MS / utilMult) is closed enough — **do not chase another ready predicate**. Residual is **weight / soft-lock / packet-presence parity** between displayed bands and Expected `avgXh`.

---

## 1. Critique (Pass-9 failure modes)

### 1.1 Smoking gun: cast multiset ≠ skillshot **packet** multiset

Pass-8 aligned filters (ranks / budget / short / multi-cast) but still emits **one band row per cast**:

```ts
// skillshotCastsForFight
const casts = abilityCastsInFight(mode, ability.slot, stats.abilityHaste)
for (let c = 0; c < Math.max(1, casts); c++) {
  out.push({ slot: ability.slot, range: ability.range, ability })
}
```

Packets expand each cast by every `skillshot: true` damage line:

```ts
// collectFighterDamage
const base = prefix(ability.damage(attackerStats, shreddedDefender, ctx))
for (let c = 0; c < casts; c++) {
  packets.push(...base.map((p) => ({ ...p, source: casts > 1 ? `${p.source} ×${c + 1}` : p.source })))
}
// scalePacketsWithXh → avgPacketXh averages every skillshot packet equally
```

Ahri Q returns **two** skillshot packets (out + return); Lee/Aatrox similarly. `blue.avgXh` weights Q 2× vs E 1×; `xhDodgeBand` weights Q 1× vs E 1×. Same `meanXhRowVsEnemies` per ability, different averages — product typical/mix vs Avg xH still disagree on multi-hit kits.

**Prefer this deepen over any new mobility×P(hit) tag.** Expand the band multiset by skillshot packet count per cast (or average bands from the same emission list `scalePacketsWithXh` sees).

### 1.2 Soft-lock path: bands ignore `lockedOut`; packets change cast set + multiplicity

```ts
// fightDodgeBands — always
skillshotCastsForFight(b, mode, false)

// collectFighterDamage lockedOut branch — single reactive cast, skip engageCc, ×0.5 raw
if (lockedOut) {
  for (const ability of champ.abilities) {
    if (ability.engageCc) continue
    …
    packets.push(...prefix(partial)) // no abilityCastsInFight loop
  }
}
```

Short-mode soft-lock: Expected skillshot set drops engage skillshots and collapses multi-cast → one reactive cast; dodge row still averages the full unlocked multiset. Wire `sideLocked('blue', input)` (or equivalent) into `fightDodgeBands` / cast helper and mirror the **reactive single-cast non-engage** emission — do not rewrite Flash envelope / Ghost predicate.

### 1.3 Packet-presence filter still optional (utility-only skillshots)

`skillshotCastsForFight` includes every `ability.skillshot` even when `damage()` emits no `skillshot: true` packets. Packets never attach xH to those casts. Pass-8 optional tighten remains: skip casts with zero skillshot damage lines once multiplicity expansion lands (same `damage()` call).

### 1.4 Eval locks incomplete / synthetic

Pass-8 AH builds a **hand-rolled** `averageXhRows([near, flat0])` — does not force a long skillshot OOR inside `fightDodgeBands`. AJ asserts `estimateXh` width, not combat `estimateXhRowVsEnemy` / `meanXhRowVsEnemies`. Pass-7 AC–AF still `void fightDodgeBands`. No ε assert `|activeBandCell − blue.avgXh|` under expected/mix policy on a shared multiset.

### 1.5 σ_juke ready-state: SKIP deepen this pass

Flash envelope, precommit, NE mix, Ghost×slow raw liveMs, charges, CC-break, `effectiveTargetMs`, utilMult dual-channel are green. Further ready-state work would be Hexflash / second envelopes / mobility×P(hit) tags — **out of scope**. Prefer bands↔packet fidelity only.

### 1.6 Out of scope (do not chase this pass)

- New MobilityClass / zone / vision multiplicative tags  
- Rewriting Flash envelope, precommit, π priors, charges, CC-break, `neMixCorridorVal`, `jukeFromBudget`, Ghost predicate  
- Hexflash second envelope  
- Geo/aim/vision formula changes (missile fields already plumbed)  
- Re-proposing Pass-8 cast-set / OOR flat bands / policy mix≠typical / missile plumbing  
- BASE×ZONE×VISION  
- Red→blue second dodge row  
- Damage-**gold**-weighted avgXh (equal packet average is the product contract; match that, do not invent DPS weights)

---

## 2. Minimal patch (orchestrator apply order)

Hard rules: no `BASE×ZONE×VISION`; no PN; strategy only varies σ_juke **inputs** + combat/UI plumbing. Prefer bands↔packet fidelity over new mobility×P(hit) tags.

### 2.1 Packet-emission multiset (highest priority)

Replace or extend `skillshotCastsForFight` so each entry matches one skillshot damage packet `collectFighterDamage` would emit:

```ts
export function skillshotCastsForFight(
  loadout: FighterLoadout,
  mode: TradeMode,
  lockedOut = false,
): XhCast[] {
  const champ = CHAMPIONS[loadout.championId]
  if (!champ) return []
  const ranks = ranksFromLoadout(loadout)
  const stats = buildStats(loadout)
  const hpPct = hpPctOf(loadout, stats)
  if (hpPct <= 0) return []
  const budget = abilityBudget(hpPct, mode, ranks.R > 0)
  const ctx = {
    mode,
    ranks,
    abilityRank: Math.max(ranks.Q, ranks.W, ranks.E, 1),
    hasEngagerAdvantage: false,
  }
  // Defender stats unused for skillshot flags; empty/avg ok for emission count.
  const defender = stats
  const out: XhCast[] = []

  const pushAbility = (ability: AbilityDefinition, castCopies: number) => {
    if (!ability.skillshot) return
    if (mode === 'short' && ability.slot === 'R') return
    if (!budget.allowed.has(ability.slot)) return
    if (ranks[ability.slot] <= 0) return
    if (lockedOut && ability.engageCc) return
    const hits = ability
      .damage(stats, defender, ctx)
      .filter((p) => p.skillshot)
    if (!hits.length) return // packet-presence: utility-only skillshot skipped
    for (let c = 0; c < castCopies; c++) {
      for (let h = 0; h < hits.length; h++) {
        out.push({ slot: ability.slot, range: ability.range, ability })
      }
    }
  }

  if (lockedOut) {
    for (const ability of champ.abilities) {
      pushAbility(ability, 1) // reactive single cast — mirrors collectFighterDamage
    }
  } else {
    for (const ability of champ.abilities) {
      const casts = abilityCastsInFight(mode, ability.slot, stats.abilityHaste)
      pushAbility(ability, Math.max(1, casts))
    }
  }
  return out
}
```

`fightDodgeBands` already maps casts → `meanXhRowVsEnemies(..., cast.ability)` and keeps OOR flat bands — no change to that skeleton once the multiset is packet-faithful.

### 2.2 Soft-lock into dodge bands

```ts
// simulateMatchup — reuse sideLocked for blue POV
const blueLocked = sideLocked('blue', input)
…
return fightDodgeBands(
  input.blue, input.red, primary.blue.outgoingUtility ?? emptyResolvedUtility(),
  visionUnits, 'blue', input.wards, input.mode ?? 'extended',
  blueLocked,
)
```

Thread `lockedOut` through `fightDodgeBands` → `skillshotCastsForFight(b, mode, lockedOut)`. Do **not** change Ghost/MS/Flash helpers.

### 2.3 Optional: single bands compute + scalar export

Dedupe the double `fightDodgeBands` call for `xhDodgeBand` / `xhPacketPolicy`. Optional eval helper:

```ts
export function fightPacketXhMean(/* same args as fightDodgeBands */): number | undefined {
  // averageXhRows(rows).xH over the same packet multiset (incl. OOR zeros)
}
```

Assert `|fightPacketXhMean − blue.avgXh| < ε` on Ahri (or any 2× skillshot kit) under `xhMode: 'expected'` when policy matches active cell (mix vs typical).

### 2.4 Policy unchanged

Keep Pass-8 rule:

```ts
bands?.mix != null && Math.abs(bands.mix - bands.typical) > 1e-9 ? 'mix' : 'typical'
```

Do not revert to first-red Flash peek.

---

## 3. New invariants (add to `eval-xh-math.ts` — do not soften 195)

```ts
// AK. Multi-hit skillshot: cast helper emits 2 rows per Ahri Q cast
const ahriCasts = skillshotCastsForFight(ahriFull, 'extended', false)
assert(
  'Pass-9: Ahri Q contributes 2× packet weight vs E 1×',
  ahriCasts.filter((c) => c.slot === 'Q').length ===
    2 * /* casts of Q */ &&
    ahriCasts.filter((c) => c.slot === 'E').length ===
    1 * /* casts of E */,
)

// AL. Soft-lock drops engage skillshot from multiset + single cast
const open = skillshotCastsForFight(malphite, 'short', false)
const locked = skillshotCastsForFight(malphite, 'short', true)
assert('Pass-9: lockedOut omits engageCc skillshots', /* locked has no R if engage */)
assert('Pass-9: lockedOut uses 1 cast not abilityCastsInFight N', locked.length < open.length)

// AM. Real OOR inside fightDodgeBands (not hand-rolled averageXhRows)
// Lux with long R + close target where R OOR and Q/E in range — or stub range
assert('Pass-9: fightDodgeBands typical < in-range-only when one cast OOR', …)

// AN. Active band cell ≈ side avgXh under expected (ε ~ 1e-9 on shared multiset)
const result = simulateMatchup(ahriVsTargetExpected)
const cell =
  result.xhPacketPolicy === 'mix' && result.xhDodgeBand?.mix != null
    ? result.xhDodgeBand.mix
    : result.xhDodgeBand!.typical
assert(
  'Pass-9: dodge active cell ≈ blue.avgXh',
  Math.abs(cell - (result.blue.avgXh ?? cell)) < 1e-9,
)

// AO. Combat-row missile plumbing (not bare estimateXh)
// wide vs thin AbilityDefinition through meanXhRowVsEnemies / estimateXhRowVsEnemy
assert('Pass-9: wider ability.missileWidth → higher combat row xH', …)

// Finish Pass-7 debt if still absent:
// AC Ghost flag raises σ_juke vs same slowed MS
// AD slow → row xH ≥ open
// AE CC flattens fight bands
// AF multi-range bands ordered
```

Regression watch: Pass-1–8 strategy asserts; Ghost×slow liveMs; Flash-up ⇒ mix≡typical; cast short/unranked R; utilMult; wards softVision; policy mix≠typical epsilon.

---

## 4. arXiv / theory cites (Pass-9 deepen)

| id / ref | use |
|----------|-----|
| [arXiv:2604.17811](https://arxiv.org/abs/2604.17811) Kill-prob vs miss | Displayed SSKP bands must average the **same hit hypotheses** as Expected packet xH — including multi-hit cast expansions and soft-lock reactive sets |
| [arXiv:2511.21633](https://arxiv.org/abs/2511.21633) Bang-Bang Evasion | Dodge row reports σ_juke hypotheses already on packets — reweight emission, do not retag mobility |
| Classic cookie-cutter / Washburn | UI % still \(P(\|M\|<R)\) under σ; no PN / BASE×ZONE×VISION |
| Fitts / SDN (prior passes) | Missile width already in shared row — only lock combat-path eval (AO), no new aim tags |

---

## 5. Expected gains vs regressions

| gap | after Pass-9 apply |
|-----|--------------------|
| Ahri/Lee multi-hit: bands 1× cast, avgXh N× packets | Band multiset = skillshot packet emission count |
| Soft-lock short: bands full cast set, packets reactive | `lockedOut` + single-cast non-engage in cast helper |
| Utility-only skillshot in bands only | Packet-presence filter (`damage().filter(skillshot)`) |
| Synthetic OOR / bare estimateXh eval | AM–AO real `fightDodgeBands` / combat-row locks (+ AC–AF debt) |
| Active cell vs Avg xH drift | AN ε parity on shared multiset |

**Out of scope:** geo/aim/vision formula changes; new MobilityClass hit tags; BASE×ZONE×VISION; Hexflash; rewriting landed Pass-1–8 KEEP; σ_juke ready-state rewrites.

---

## 6. Decision

**`KEEP_CANDIDATE`**

Rationale: Pass-8 closed cast-set filters, OOR retention, policy-from-mix, and missile plumbing (195/195), but bands still weight **one row per cast** while Expected `avgXh` weights **one term per skillshot damage packet**, and soft-lock never reaches the dodge multiset. Product dodge typical/mix can still disagree with Avg xH on multi-hit kits and short soft-locks — without any σ_juke formula bug.

1. Expand band multiset to skillshot packet emission (incl. packet-presence skip); thread `lockedOut` reactive single-cast.  
2. Lock eval AK–AO (+ finish Pass-7 AC–AF debt); assert active band cell ≈ `blue.avgXh`.  
3. Do **not** add mobility×P(hit) tags or touch Flash/Ghost ready predicates.

Orchestrator should apply §§2–3 in `combat.ts` (+ thin exports for eval), re-run `npm run eval:xh`, keep only if rate stays 195/195 before new asserts, then ≥ all new checks.

**Verdict: KEEP_CANDIDATE — deepen bands↔packet packet-weight / soft-lock fidelity; σ_juke ready-state SKIP; no new mobility×P(hit) tags.**
