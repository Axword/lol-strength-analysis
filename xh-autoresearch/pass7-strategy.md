# Pass-7 STRATEGY — σ_juke / bands fidelity residual only

**Axis:** strategy (σ_juke ready-state + dodge bands → CombatResult fidelity)  
**Status:** `KEEP_CANDIDATE`  
**Constraint:** critique + snippets only; **do not edit** production files in this pass.  
**Eval at write:** `math_pass_rate=148/148 (1.0000)` post Pass-6 KEEP. Deepen residual only; do not re-propose landed KEEP work; no `BASE×ZONE×VISION`; **no new mobility×P(hit) tags**.

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

Eval strategy probes through Pass-6 (envelope / mix / precommit / CD / charges / NE / Ghost / avg bands / utilMult / effectiveTargetMs / Ghost liveMs) are green. Residual is **Ghost×slow predicate split + fallback MS parity + NvM/multi-skillshot band average**, not another `jukeFromBudget` rewrite or mobility×P(hit) tag.

---

## 1. Critique (Pass-7 failure modes)

### 1.1 Smoking gun: Ghost flag consumes slowed MS

Pass-6 correctly feeds `effectiveTargetMs` into `targetMovespeed`, but the same slowed value is reused for the Ghost predicate:

```ts
// combat.ts estimateXhRowVsEnemy — post Pass-6
const ms = effectiveTargetMs(enemy, stats.movespeed, targetDebuffs)
…
targetMovespeed: ms,
ghostActive: ghostBuffActive(enemy, ms, stats.movespeed), // ← ms already × msFactor
```

Under Ghost live bump + slow, e.g. `live=400`, `base=335`, `enemySlow=0.4`:

- `msFactor = 1 − min(0.45, 0.22) = 0.78` → `ms = 312`
- threshold `base × 1.05 = 351.75` → **Ghost false** even though Ghost is active

σ_juke then loses strafeCoeff 0.55→0.45 **and** already runs on slowed MS — double penalty, and the Ghost channel regresses exactly when util is applied (the case Pass-6 wired into bands). Explicit `ghostActive: true` still works; the liveMs-bump path does not.

**Prefer this deepen over any new mobility×P(hit) tag.** Split raw live MS (Ghost predicate) from slowed MS (`targetMovespeed` / σ_juke strafe).

### 1.2 Fallback still omits `effectiveTargetMs`

Pass-6 §2.2 required fallback parity. Primary path passes slowed MS; OOR/no-pos fallback still does not:

```ts
// meanXhRowVsEnemies fallback — still
const est = estimateXh({
  …
  // no targetMovespeed
  ghostActive: ghostBuffActive(
    fallback,
    fallback.liveStats?.movespeed ?? buildStats(fallback).movespeed,
    buildStats(fallback).movespeed,
  ),
})
```

So no-position / OOR rows ignore slow→σ_juke while utilMult still scales the scalar — same half-plumb Pass-6 closed on the primary path only.

### 1.3 Displayed dodge bands ≠ packet NvM average (Pass-6 §1.5 deferred)

`xhDodgeBand` still:

- first living blue → first living red  
- **first** blue skillshot range only  

Packets (`scalePacketsWithXh`) average every living caster×enemy at **per-ability** skillshot range with the same util/vision/wards. Multi-skillshot kits (Lux Q+E+R, Ziggs, …) and NvM fights can show a dodge row that disagrees with Expected packet xH even after Pass-5/6 util parity.

This is the remaining **product fidelity** gap; `averageXhRows` already exists — wire it.

### 1.4 Incomplete Pass-6 eval locks

Landed Pass-6 strategy asserts only:

- `effectiveTargetMs` shrinks under slow  
- `ghostBuffActive` trusts liveMs without liveStats  

Proposed Y (CC flattens fight bands), Z (slow → σ_juke ≤ open), and exact autos-law AA never shipped. Pass-7 should lock those plus the Ghost×slow split and NvM band parity — without softening 148.

### 1.5 Out of scope (do not chase this pass)

- New MobilityClass / zone / vision multiplicative tags  
- Rewriting Flash envelope, precommit, π priors, charges, CC-break, `neMixCorridorVal`, `jukeFromBudget`  
- Hexflash second envelope  
- Geo width / aim SDN / belief LKP / xHm empirics  
- Re-proposing Pass-6 fight-util stub / `effectiveTargetMs` helper / remake hint / caption  
- BASE×ZONE×VISION  
- Dropping utilMult slow channel (dual channel with σ_juke MS is intentional)

---

## 2. Minimal patch (orchestrator apply order)

Hard rules: no `BASE×ZONE×VISION`; no PN; strategy only varies σ_juke **inputs** + combat/UI plumbing. Prefer bands↔packet fidelity over new mobility×P(hit) tags.

### 2.1 Split raw live MS vs slowed MS (highest priority)

```ts
function estimateXhRowVsEnemy(…): XhRow | null {
  …
  const stats = buildStats(enemy)
  const liveMs = enemy.liveStats?.movespeed ?? stats.movespeed
  const msJuke = effectiveTargetMs(enemy, stats.movespeed, targetDebuffs)
  const hardCc =
    targetDebuffs.hardCc === true || enemy.crowdControlled === true
  const est = estimateXh({
    …
    targetMovespeed: msJuke,
    crowdControlled: hardCc,
    ccBreakReady: ccBreakReadyFromLoadout(enemy),
    ghostActive: ghostBuffActive(enemy, liveMs, stats.movespeed),
  })
  …
}
```

Do **not** change `ghostBuffActive` signature or `jukeFromBudget` / Ghost strafeCoeff.

### 2.2 Fallback MS + Ghost parity

```ts
const stats = buildStats(fallback)
const liveMs = fallback.liveStats?.movespeed ?? stats.movespeed
const msJuke = effectiveTargetMs(fallback, stats.movespeed, targetDebuffs)
const est = estimateXh({
  …
  targetMovespeed: msJuke,
  crowdControlled:
    targetDebuffs.hardCc === true || fallback.crowdControlled === true,
  ghostActive: ghostBuffActive(fallback, liveMs, stats.movespeed),
  // same ready / charges / flash plumbing as today
})
```

### 2.3 NvM / multi-skillshot dodge bands (Pass-6 §1.5 now)

```ts
function fightDodgeBands(
  casters: FighterLoadout[],
  enemies: FighterLoadout[],
  outgoing: ResolvedUtility,
  visionUnits: VisionUnit[],
  casterTeam: 'blue' | 'red',
  wards?: VisionWard[],
): XhRow['bands'] {
  const livingC = casters.filter(isAlive)
  const livingE = enemies.filter(isAlive)
  if (!livingC.length || !livingE.length) return undefined
  const rows = livingC.flatMap((b) => {
    const ranges =
      CHAMPIONS[b.championId]?.abilities
        ?.filter((a) => a.skillshot)
        .map((a) => a.range) ?? [900]
    return ranges.map((r) =>
      meanXhRowVsEnemies(b, livingE, r, outgoing, visionUnits, casterTeam, wards),
    )
  })
  return averageXhRows(rows.filter((r) => r.bands)).bands
}

// simulateMatchup:
xhDodgeBand: fightDodgeBands(
  input.blue,
  input.red,
  primary.blue.outgoingUtility ?? emptyResolvedUtility(),
  visionUnits,
  'blue',
  input.wards,
),
```

Export `fightDodgeBands` (or keep internal + thin eval wrapper) so invariants can assert without React. Optional: red→blue second row later — skip unless headroom; attacker POV blue→red is enough.

### 2.4 Tiny UI (only if policy drifts)

Caption/active-cell already match mix≠null. No UI change required unless `xhPacketPolicy === 'mix'` while averaged `mix` is undefined — then coerce policy from the returned bands (same rule as caption). Prefer one-liner over redesign.

---

## 3. New invariants (add to `eval-xh-math.ts` — do not soften 148)

```ts
// AC. Ghost×slow: predicate uses raw liveMs; juke uses slowed MS
const live = 400
const base = 335
const slowed = effectiveTargetMs(ghostLoad, base, { enemySlow: 0.4, hardCc: false })
assert('Ghost liveMs still true under slow', ghostBuffActive(ghostLoad, live, base) === true)
assert('slowed MS < live', slowed < live)
const open = estimateXh({ targetMovespeed: live, ghostActive: true, …pointBlank })
const slowGhost = estimateXh({ targetMovespeed: slowed, ghostActive: true, …pointBlank })
assert('slow+Ghost: σ_juke ≤ open Ghost', slowGhost.sigma!.juke <= open.sigma!.juke + 1e-9)
const killGhost = estimateXh({ targetMovespeed: slowed, ghostActive: false, … })
assert('Ghost flag still lowers σ vs same slowed MS', slowGhost.sigma!.juke + 1e-9 >= killGhost.sigma!.juke)
// (strafeCoeff 0.55 vs 0.45 — direction: Ghost ⇒ larger σ_juke)

// AD. fallback / row path: slow shrinks σ_juke (export estimateXhRowVsEnemy or fight helper)
const rowOpen = estimateXhRowOrFight({ util: empty, … })
const rowSlow = estimateXhRowOrFight({ util: { enemySlow: 0.4, hardCc: false }, … })
assert('slow → row σ_juke ≤ open', /* via exposed sigma or xH↑ */)
assert('slow → row xH ≥ open', rowSlow.xH >= rowOpen.xH - 1e-9)

// AE. CC flattens fight bands (Pass-6 Y, finally)
assert('CC flattens fight bands', cc.bands!.best - cc.bands!.worst < open.bands!.best - open.bands!.worst + 1e-6)

// AF. NvM / multi-range average ordered + uses >1 skillshot when kit has them
const multi = fightDodgeBands([lux], [target], empty, vision, 'blue')
const single = meanXhRowVsEnemies(lux, [target], luxQRange, empty, vision, 'blue').bands
assert('multi bands ordered', multi!.worst <= multi!.typical && multi!.typical <= multi!.best)
// optional: |multi.typical - single.typical| can be >0 when Q≠E≠R ranges — document, don't require inequality if ranges equal
```

Regression watch: Pass-1–6 strategy asserts; kit tag alone; Flash-up ⇒ mix===typical; Ghost without bump false; `effectiveTargetMs` shrink; utilMult scales bands; wards softVision path.

---

## 4. arXiv / theory cites (Pass-7 deepen)

| id / ref | use |
|----------|-----|
| [arXiv:2511.21633](https://arxiv.org/abs/2511.21633) Bang-Bang Evasion | Ghost is a continuous-strafe regime flag; must not be gated by the same scalar that already shrinks strafe budget under slow |
| [arXiv:2604.17811](https://arxiv.org/abs/2604.17811) Kill-prob vs miss | Displayed SSKP bands = average over the same cast set as packet Expected xH (NvM × skillshot ranges) |
| [arXiv:1804.05021](https://arxiv.org/abs/1804.05021) / [2410.02966](https://arxiv.org/abs/2410.02966) Fitts / SDN | MS enters σ_juke only; Ghost coeff is regime, not a hit mult |
| Classic cookie-cutter / Washburn | UI % still \(P(\|M\|<R)\) under σ; no PN / BASE×ZONE×VISION |

---

## 5. Expected gains vs regressions

| gap | after Pass-7 apply |
|-----|--------------------|
| Ghost+slow kills Ghost flag | Predicate on raw `liveMs`; juke on `effectiveTargetMs` |
| Fallback ignores slow→MS | Same MS/Ghost helpers as primary row |
| Dodge row ≠ multi-skillshot / NvM packets | `fightDodgeBands` + `averageXhRows` |
| Pass-6 Y/Z incomplete in eval | Locks AC–AF |

**Out of scope:** geo/aim/vision formula changes; new MobilityClass hit tags; BASE×ZONE×VISION; Hexflash; rewriting landed Pass-1–6 KEEP.

---

## 6. Decision

**`KEEP_CANDIDATE`**

Rationale: Pass-6 closed fight-util → bands and slow→MS (148/148), but composed Ghost detection with the slowed MS scalar, left fallback without `targetMovespeed`, and deferred NvM/multi-skillshot averaging — so product bands can still disagree with packets and Ghost+slow double-penalizes.

1. Split raw live MS (Ghost) from slowed MS (σ_juke); fallback parity.  
2. Average dodge bands over living casters × skillshot ranges (same util/vision as packets).  
3. Lock eval AC–AF (Ghost×slow, slow/CC fight rows, multi-range order).

Orchestrator should apply §§2–3 in `combat.ts` (+ export helpers for eval), re-run `npm run eval:xh`, keep only if rate stays 148/148 before new asserts, then ≥ all new checks.

**Verdict: KEEP_CANDIDATE — Ghost×slow split + fallback MS + NvM band average; no new mobility×P(hit) tags.**
