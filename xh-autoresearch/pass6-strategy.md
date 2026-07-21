# Pass-6 STRATEGY — σ_juke / bands→product fidelity residual only

**Axis:** strategy (σ_juke ready-state + dodge bands → CombatResult fidelity)  
**Status:** `KEEP_CANDIDATE`  
**Constraint:** critique + snippets only; **do not edit** production files in this pass.  
**Eval at write:** `math_pass_rate=129/129 (1.0000)` post Pass-5 KEEP. Deepen residual only; do not re-propose landed KEEP work; no `BASE×ZONE×VISION`.

---

## 0. Already landed (do NOT re-propose)

| Pass | Landed |
|------|--------|
| 1 | Flash envelope for worst; windup dodge window; ready budgets; soft `dodgeScale` |
| 2 | Precommit residual; `bands.mix` via `neMixCorridorVal`; `flashCdRemainingSec`; combat Flash/dash ready |
| 3 | Ghost/charges/CC-break; NE unknown→packet mix + π_down; `MatchupResult.xhDodgeBand`; Expected-cell hint → dodge-budget copy |
| 4 | CombatResult xH dodge row (`DodgeCell`); MS / hard-CC into `meanXhVsEnemies`→`estimateXh`; smarter stub range (first skillshot) |
| 5 | `averageXhRows` / `scaleXhBands` / `ghostBuffActive`; shared `estimateXhRowVsEnemy` + wards; `xhPacketPolicy` + mix/typical highlight; eval U–W |

Eval strategy probes through Pass-5 (envelope / mix / precommit / CD / charges / NE / Ghost channel / avg bands / utilMult scale / Ghost predicate) are green. Residual is **fight-utility parity on displayed bands + slow→σ_juke MS + leftover UI copy**, not another aggregator rewrite or mobility×P(hit) tag.

---

## 1. Critique (Pass-6 failure modes)

### 1.1 Smoking gun: dodge row still ignores fight utility

Pass-5 wired `xhDodgeBand` through `meanXhRowVsEnemies`, but the stub still passes **`emptyResolvedUtility()`**:

```ts
// combat.ts simulateMatchup — post Pass-5
xhDodgeBand: (() => {
  …
  const row = meanXhRowVsEnemies(
    blue,
    [red],
    skillshotRange,
    emptyResolvedUtility(), // ← utilMult=1, hardCc never from kit slows/CC
    visionUnits,
    'blue',
    input.wards,
  )
  return row.bands
})()
```

Meanwhile packets use `blueOutgoing` / `redOutgoing` from `collectSideUtility` (Nasus W, engage CC, etc.):

```ts
const xH = meanXhVsEnemies(loadout, enemies, range, targetDebuffs, …)
// targetDebuffs = outgoing onto defender → xhUtilityMultiplier + crowdControlled
```

So under any fight with slows/hard CC, **displayed dodge % disagree with Expected packet xH** even though both call the same helper. Pass-5 assert X (“CC flattens fight bands”) never landed — only U–W.

**Prefer this deepen over any new mobility×P(hit) tag.** Feed `primary.blue.outgoingUtility` (or recompute once) into the dodge builder.

### 1.2 Slow → MS still half-plumbed (σ_juke vs utilMult)

`xhUtilityMultiplier` raises the scalar / scaled bands when `enemySlow > 0`, but `estimateXh` still gets full live MS:

```ts
const ms = enemy.liveStats?.movespeed ?? stats.movespeed
// … no enemySlow factor
targetMovespeed: ms,
```

Autos already apply the same slow law in `autosAfterUtility`:

```ts
const msFactor = 1 - Math.min(0.45, incoming.enemySlow * 0.55)
```

Residual: pass `ms * msFactor` into `targetMovespeed` so σ_juke continuous-strafe shrinks under slow — **not** a new mobility tag, and not a rewrite of `jukeFromBudget`. Hard CC already collapses via `crowdControlled`; this closes the slow channel only.

### 1.3 Expected strength hint still dodge-budget language

Pass-5 caption under xH dodge is correct (`packet: typical | mix`). Strength remake middle cell still says:

```tsx
hint="dodge budget: depleted / observed / Flash envelope"
```

That confuses remakes (hit_all / expected / miss_shots) with the dodge envelope row. Retarget to trade-under-packet copy (Pass-5 §2.2 leftover).

### 1.4 Fallback + Ghost predicate edge fidelity

| gap | detail |
|-----|--------|
| OOR/no-pos fallback | still omits `targetMovespeed` (and thus slow→MS) while primary path passes MS |
| `ghostBuffActive` | requires `f.liveStats?.movespeed != null` **and** `liveMs >= baseMs * 1.05` — redundant; if caller already passes bumped `liveMs`, liveStats-null still false |
| Caption edge | `xhPacketPolicy === 'mix'` but `mix == null` → caption “typical (Flash CD unknown)” |

Tiny plumbing only; do not retouch NE π math.

### 1.5 Optional deepen: NvM / multi-skillshot band average

Stub remains first living blue→red at first blue skillshot range. Packets average every living caster×enemy at per-ability range. Optional Pass-6b: `averageXhRows` over living blue skillshot ranges × living red (same utility/vision/wards). Skip if orchestrator wants §1.1–1.3 only this pass.

### 1.6 Out of scope (do not chase this pass)

- New MobilityClass / zone / vision multiplicative tags  
- Rewriting Flash envelope, precommit, π priors, charges, CC-break, `neMixCorridorVal`  
- Hexflash second envelope  
- Geo width / aim SDN / belief LKP / xHm empirics  
- Re-proposing Pass-5 aggregator / Ghost live-MS flag / packet-policy highlight  
- BASE×ZONE×VISION  

---

## 2. Minimal patch (orchestrator apply order)

Hard rules: no `BASE×ZONE×VISION`; no PN; strategy only varies σ_juke **inputs** + combat/UI plumbing. Prefer bands↔packet fidelity over new mobility×P(hit) tags.

### 2.1 Fight utility into dodge bands (replace empty stub)

```ts
// After primary = runOnce(…): reuse collected outgoing onto red
xhDodgeBand: (() => {
  const blue = input.blue.find(isAlive)
  const red = input.red.find(isAlive)
  if (!blue || !red) return undefined
  const skillshotRange =
    CHAMPIONS[blue.championId]?.abilities?.find((a) => a.skillshot)?.range ?? 900
  const visionUnits = /* same full-team builder as buildSide, not 1+1 only */
  const debuffs =
    primary.blue.outgoingUtility ?? emptyResolvedUtility()
  const row = meanXhRowVsEnemies(
    blue,
    [red],
    skillshotRange,
    debuffs,
    visionUnits,
    'blue',
    input.wards,
  )
  return row.bands
})()
```

Export a tiny `fightDodgeBands(…)` (or reuse `estimateXhRowVsEnemy` + known util) so eval can assert CC/slow without mounting React.

### 2.2 Slow → targetMovespeed (σ_juke only)

```ts
function effectiveTargetMs(
  enemy: FighterLoadout,
  baseMs: number,
  util: ResolvedUtility,
): number {
  const live = enemy.liveStats?.movespeed ?? baseMs
  const msFactor = 1 - Math.min(0.45, util.enemySlow * 0.55) // match autosAfterUtility
  return live * msFactor
}

// in estimateXhRowVsEnemy (+ fallback):
targetMovespeed: effectiveTargetMs(enemy, stats.movespeed, targetDebuffs),
```

Do **not** change `jukeFromBudget` / Ghost strafeCoeff. Fallback path must pass the same MS helper.

### 2.3 Ghost predicate trust liveMs; UI copy cleanup

```ts
export function ghostBuffActive(
  f: FighterLoadout,
  liveMs: number,
  baseMs: number,
): boolean {
  if (f.ghostActive === true) return true
  const hasGhost = (f.summonerSpells ?? []).some((s) => /ghost/i.test(s))
  if (!hasGhost) return false
  // Trust explicit liveMs bump OR liveStats bump — not equipped alone
  return liveMs >= baseMs * 1.05
}
```

```tsx
// CombatResult — remake cell
hint="trade under packet xH"

// Caption: only append Flash-unknown when mix cell is the active policy
packet:{' '}
{packetPolicy}
{packetPolicy === 'mix' ? ' (Flash CD unknown)' : ''}
```

Where `packetPolicy = result.xhPacketPolicy === 'mix' && mix != null ? 'mix' : 'typical'`.

### 2.4 Optional NvM band average (§1.5)

```ts
const rows = livingBlue.flatMap((b) => {
  const ranges = CHAMPIONS[b.championId]?.abilities
    ?.filter((a) => a.skillshot)
    .map((a) => a.range) ?? [900]
  return ranges.map((r) =>
    meanXhRowVsEnemies(b, livingRed, r, blueOutgoing, visionUnits, 'blue', wards),
  )
})
return averageXhRows(rows.filter((r) => r.bands)).bands
```

Only if §2.1–2.3 leave headroom; not required for KEEP.

---

## 3. New invariants (add to `eval-xh-math.ts` — do not soften 129)

Engine math already covers Ghost/charges/NE. Pass-6 locks **utility→bands / slow→MS** contracts:

```ts
// Y. fight utility changes displayed bands vs empty util (Pass-5 X, finally)
const open = estimateXhRowOrFight({ util: empty, crowdControlled: false, … })
const cc = estimateXhRowOrFight({ util: { hardCc: true, enemySlow: 0 }, … })
assert('CC flattens fight bands', cc.bands!.best - cc.bands!.worst < open.bands!.best - open.bands!.worst + 1e-6)
assert('CC raises packet xH', cc.xH > open.xH - 1e-9)

// Z. slow shrinks σ_juke (strafe) without kit retag
const full = estimateXh({ targetMovespeed: 335, … })
const slowed = estimateXh({ targetMovespeed: 335 * (1 - Math.min(0.45, 0.4 * 0.55)), … })
assert('slow → σ_juke ≤ full', slowed.sigma!.juke <= full.sigma!.juke + 1e-9)
assert('slow → xH ≥ full (typical)', slowed.xH >= full.xH - 1e-9)

// AA. effectiveTargetMs matches autos MS law
assert('msFactor', Math.abs(effectiveTargetMs(f, 335, { enemySlow: 0.4, … }) - 335 * (1 - Math.min(0.45, 0.4 * 0.55))) < 1e-9)

// AB. ghostBuffActive(true) when liveMs bumped even if liveStats omitted
assert('ghost via liveMs arg', ghostBuffActive(ghostEquipOnly, 400, 335) === true)
assert('ghost dead at base liveMs', ghostBuffActive(ghostEquipOnly, 335, 335) === false)
```

Regression watch: Pass-1–5 strategy asserts (envelope / mix / precommit / CD / charges / NE / Ghost channel / avg bands / utilMult scale / Ghost+liveStats); kit tag alone; CC point-blank; faster missile → higher xH; Flash-up ⇒ mix===typical; wards softVision path.

---

## 4. arXiv / theory cites (Pass-6 deepen)

| id / ref | use |
|----------|-----|
| [arXiv:2604.17811](https://arxiv.org/abs/2604.17811) Kill-prob vs miss | Displayed SSKP bands must share the packet’s hypothesis set (incl. defender CC/slow state) |
| [arXiv:2511.21633](https://arxiv.org/abs/2511.21633) Bang-Bang Evasion | Slow reduces continuous evasion budget (strafe σ_juke), not a multiplicative hit tag |
| [arXiv:1804.05021](https://arxiv.org/abs/1804.05021) / [2410.02966](https://arxiv.org/abs/2410.02966) Fitts / SDN | MS enters σ_juke only; reuse autos MS law; do not retag aim |
| Classic cookie-cutter / Washburn | UI % still \(P(\|M\|<R)\) under σ; no PN / BASE×ZONE×VISION |

---

## 5. Expected gains vs regressions

| gap | after Pass-6 apply |
|-----|--------------------|
| Dodge row blind to fight CC/slow | `outgoingUtility` into `meanXhRowVsEnemies` |
| Slow only via utilMult, not σ_juke | `effectiveTargetMs` → `targetMovespeed` |
| Remake hint still dodge-budget | “trade under packet xH” |
| Ghost liveMs-only edge | Predicate trusts `liveMs` bump |
| Pass-5 assert X never landed | Eval Y–AB |

**Out of scope:** geo/aim/vision formula changes; new MobilityClass hit tags; BASE×ZONE×VISION; Hexflash; rewriting landed Pass-1–5 KEEP.

---

## 6. Decision

**`KEEP_CANDIDATE`**

Rationale: Pass-5 unified the aggregator and UI policy highlight (129/129), but the dodge stub still feeds **empty utility**, so product bands disagree with packets whenever slows/CC fire. Slow still boosts xH only via utilMult while σ_juke strafe sees full MS. Leftover remake-hint copy and tiny Ghost/fallback edges remain.

1. Wire fight `outgoingUtility` into dodge bands (same helper as packets).  
2. Plumb slow→`targetMovespeed` with the autos MS law; fallback parity.  
3. Retarget Expected remake hint; tighten Ghost liveMs / caption edge; lock eval Y–AB.

Orchestrator should apply §§2–3 in `combat.ts` / `utility` export if needed / `CombatResult` (+ light CSS if caption already styled), export helpers for eval, re-run `npm run eval:xh`, keep only if rate stays 129/129 before new asserts, then ≥ all new checks.

**Verdict: KEEP_CANDIDATE — fight-utility + slow→σ_juke MS into dodge/packet parity; no new mobility×P(hit) tags.**
