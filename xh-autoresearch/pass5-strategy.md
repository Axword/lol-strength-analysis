# Pass-5 STRATEGY — σ_juke / bands→UI residual only

**Axis:** strategy (σ_juke ready-state + dodge bands → CombatResult fidelity)  
**Status:** `KEEP_CANDIDATE`  
**Constraint:** critique + snippets only; **do not edit** production files in this pass.  
**Eval at write:** `math_pass_rate=103/103 (1.0000)` post Pass-4 KEEP. Deepen residual only; do not re-propose landed KEEP work; no `BASE×ZONE×VISION`.

---

## 0. Already landed (do NOT re-propose)

| Pass | Landed |
|------|--------|
| 1 | Flash envelope for worst; windup dodge window; ready budgets; soft `dodgeScale` |
| 2 | Precommit residual; `bands.mix` via `neMixCorridorVal`; `flashCdRemainingSec`; combat Flash/dash ready |
| 3 | Ghost/charges/CC-break; NE unknown→packet mix + π_down; `MatchupResult.xhDodgeBand`; Expected-cell hint → dodge-budget copy |
| 4 | CombatResult xH dodge row (`DodgeCell`); MS / hard-CC into `meanXhVsEnemies`→`estimateXh`; smarter stub range (first skillshot, not literal 900) |

Eval strategy probes (envelope / mix / precommit / CD / charges / NE unknown / Ghost channel) are green. Residual is **shared aggregator + UI policy highlight + Ghost/CC/vision parity on the displayed bands**, not another σ_juke formula rewrite.

---

## 1. Critique (Pass-5 failure modes)

### 1.1 Smoking gun: dodge row still ≠ damage xH path

Pass-4 rendered `result.xhDodgeBand`, but the field is still a **separate blue→red IIFE**, not the aggregator that scales packets:

```ts
// combat.ts simulateMatchup — still dual-path
xhDodgeBand: (() => {
  const blue = input.blue.find(isAlive)
  const red = input.red.find(isAlive)
  …
  const est = estimateXh({
    …,
    abilityRange: skillshotRange, // first blue skillshot only
    // no vision / softVision / spottedByTarget
    // no crowdControlled
    // no utilMult scaling on returned bands
  })
  return est.bands ? { … } : undefined
})()
```

Meanwhile `meanXhVsEnemies` still returns a **scalar** and drops `est.bands`:

```ts
return Math.min(0.97, est.xH * utilMult)  // bands discarded
```

So the dodge row can disagree with Expected-mode packet % whenever FoW, CC, utilMult, NvM average, or ability range differ. Pass-4 “smarter stub” fixed the literal `900` constant; the structural dual-path remains.

**Prefer this deepen over any new mobility×P(hit) tag.** One shared band builder for packets + UI.

### 1.2 Ghost strafeCoeff is dead without live MS bump

```ts
ghostActive:
  (enemy.summonerSpells ?? []).some((s) => /ghost/i.test(s)) &&
  ms >= stats.movespeed * 1.05,
```

`buildStats` never applies Ghost; without `liveStats.movespeed`, `ms === stats.movespeed` → predicate always false → equipped Ghost never raises `strafeCoeff` 0.45→0.55. Pass-3/4 Ghost channel only fires when timeline already inflated MS. Do **not** add Ghost×BASE — either feed buffed MS, or set `ghostActive` from an explicit buff/timeline flag (loadout field), keeping σ_juke continuous-strafe only.

### 1.3 UI always marks `typical` active

```tsx
<DodgeCell label="typical" … active />
// mix rendered but never active — even when flashReady === undefined
```

Engine packet policy: Flash CD unknown → `xH = bands.mix`. UI still highlights “observed budget” while damage may use NE mix. Missing one-line caption (`packet: typical | mix`). Strength Expected hint still says “dodge budget: depleted / observed / Flash envelope” — redundant with the dodge row and still not the remake semantics.

### 1.4 Stub omits vision + hard CC; fallback path omits everything

| input | `meanXhVsEnemies` | `xhDodgeBand` stub | OOR fallback in meanXh |
|-------|-------------------|--------------------|------------------------|
| softVision / spotted | yes | **no** | **no** |
| `crowdControlled` | from `targetDebuffs.hardCc` | **no** | **no** |
| `targetMovespeed` / Ghost | yes (fragile Ghost) | MS yes; Ghost same fragile | **no** |
| utilMult on % | yes (scalar) | **no** | yes (scalar only) |
| ability range | per-packet | first blue skillshot | per-call range |

Displayed bands never flatten under CC and never mix FoW belief — product users see “Flash envelope” % that ignore Pass-3/4 σ_juke inputs already wired on the damage path.

### 1.5 Slow → MS still half-plumbed

`xhUtilityMultiplier` raises scalar xH on slow/CC, but σ_juke still uses full `targetMovespeed` unless live overlay already slowed. Residual: optional `ms * (1 - k·enemySlow)` into `estimateXh` only — **not** a new mobility tag. Skip if orchestrator wants utilMult-only this pass; document as optional §2.3b.

### 1.6 Out of scope (do not chase this pass)

- New MobilityClass / zone / vision multiplicative tags  
- Rewriting Flash envelope, precommit, π priors, charges, CC-break math (landed)  
- Hexflash second envelope  
- Geo width / aim SDN / belief LKP / xHm empirics  
- BASE×ZONE×VISION  

---

## 2. Minimal patch (orchestrator apply order)

Hard rules: no `BASE×ZONE×VISION`; no PN; strategy only varies σ_juke inputs + combat/UI plumbing. Prefer bands→UI fidelity over new mobility×P(hit) tags.

### 2.1 Shared band aggregator (replace stub + scalar-only mean)

```ts
type XhRow = { xH: number; bands?: XhDodgeBands }

function averageXhRows(rows: XhRow[]): XhRow {
  const n = rows.length
  if (!n) return { xH: 1 }
  const mean = (xs: number[]) => xs.reduce((a, b) => a + b, 0) / xs.length
  const withBands = rows.filter((r) => r.bands)
  return {
    xH: mean(rows.map((r) => r.xH)),
    bands: withBands.length
      ? {
          worst: mean(withBands.map((r) => r.bands!.worst)),
          typical: mean(withBands.map((r) => r.bands!.typical)),
          best: mean(withBands.map((r) => r.bands!.best)),
          mix: withBands.every((r) => r.bands!.mix != null)
            ? mean(withBands.map((r) => r.bands!.mix!))
            : undefined,
        }
      : undefined,
  }
}

function estimateXhRowVsEnemy(/* same args as today’s map body */): XhRow | null {
  const est = estimateXh({ /* vision + MS + CC + Ghost + ready as meanXh today */ })
  if (caster.position && enemy.position && !est.inRange) return null
  const scale = (p: number) => Math.min(0.97, p * utilMult)
  const flash = flashReadyFromLoadout(enemy)
  const packet =
    flash === undefined && est.bands?.mix != null ? est.bands.mix : est.xH
  return {
    xH: scale(packet),
    bands: est.bands && {
      worst: scale(est.bands.worst),
      typical: scale(est.bands.typical),
      best: scale(est.bands.best),
      mix: est.bands.mix != null ? scale(est.bands.mix) : undefined,
    },
  }
}

function meanXhVsEnemies(…): XhRow {
  …
  const usable = living.map(…).filter(Boolean)
  if (!usable.length) return fallbackRow(/* same inputs as primary path */)
  return averageXhRows(usable)
}
```

Wire `MatchupResult.xhDodgeBand` from the **same** helper used for primary expected packets (document: fight-average of living blue→red skillshot rows at representative range, or first blue skillshot range — pick one; drop the separate IIFE). Fallback path must pass MS/CC/Ghost/vision too.

Optional: `FighterResult.xhBands` for ability-log hover — nice-to-have, not required if match-level row matches packet policy.

### 2.2 CombatResult: active cell = packet policy

```tsx
const flashUnk = /* primary red flashReady === undefined */
const packetPolicy = flashUnk && result.xhDodgeBand.mix != null ? 'mix' : 'typical'

{result.xhDodgeBand && (
  <div className="strength-band dodge-band" aria-label="Skillshot dodge envelope">
    <p className="band-title">xH dodge</p>
    <p className="band-caption">packet: {packetPolicy}{flashUnk ? ' (Flash CD unknown)' : ''}</p>
    <div className="band-row dodge-row">
      <DodgeCell label="worst" hint="Flash envelope" value={…} />
      <DodgeCell label="typical" hint="observed budget" value={…} active={packetPolicy === 'typical'} />
      {mix != null && (
        <DodgeCell label="mix" hint="NE Flash prior" value={mix} active={packetPolicy === 'mix'} />
      )}
      <DodgeCell label="best" hint="depleted" value={…} />
    </div>
  </div>
)}
```

Retarget Expected strength hint away from dodge-budget language (e.g. “trade under packet xH”) so remakes vs dodge envelope stay distinct.

### 2.3 Ghost / MS / CC plumbing fidelity only

```ts
// Prefer explicit buff when present; else MS-elevated live overlay; never “equipped alone”
function ghostBuffActive(f: FighterLoadout, statsMs: number, baseMs: number): boolean {
  if (f.ghostActive === true) return true  // add optional loadout flag
  return (
    (f.summonerSpells ?? []).some((s) => /ghost/i.test(s)) &&
    f.liveStats?.movespeed != null &&
    f.liveStats.movespeed >= baseMs * 1.05
  )
}

function hardCcOn(f: FighterLoadout, util: ResolvedUtility): boolean {
  return util.hardCc === true || f.crowdControlled === true  // optional loadout override
}
```

Stub + mean path both call these. Do **not** change `jukeFromBudget` unless CC plumbing proves an eval gap.

**§2.3b (optional):** `targetMovespeed: ms * (1 - Math.min(0.45, util.enemySlow * 0.55))` so slows enter σ_juke strafe, not only utilMult.

### 2.4 Tiny UI-facing factor only

No new σ tags. Caption in §2.2 is enough. Do not invent kit priors or zone×hit chips.

---

## 3. New invariants (add to `eval-xh-math.ts` — do not soften 103)

Engine math already covers Ghost/charges/NE. Pass-5 locks **plumbing contracts** (pure helpers), not React:

```ts
// U. averageXhRows preserves order + mix bracket
const avg = averageXhRows([
  { xH: 0.4, bands: { worst: 0.3, typical: 0.4, best: 0.6, mix: 0.35 } },
  { xH: 0.5, bands: { worst: 0.4, typical: 0.5, best: 0.7, mix: 0.45 } },
])
assert('avg bands ordered', avg.bands!.worst <= avg.bands!.typical && avg.bands!.typical <= avg.bands!.best)
assert('avg mix in [worst,typical]', avg.bands!.mix! >= avg.bands!.worst - 1e-9 && avg.bands!.mix! <= avg.bands!.typical + 1e-9)

// V. utilMult scales bands componentwise (export scale helper or fightDodgeBands)
const raw = { worst: 0.4, typical: 0.5, best: 0.6, mix: 0.45 }
const scaled = scaleBands(raw, 1.18)
assert('scaled typical', Math.abs(scaled.typical - Math.min(0.97, 0.5 * 1.18)) < 1e-9)

// W. Ghost equipped + no live MS bump ⇒ ghostBuffActive false; + live MS bump ⇒ true
assert('ghost dead without live MS', ghostBuffActive(ghostEquipOnly, 335, 335) === false)
assert('ghost live MS', ghostBuffActive(ghostWithLiveMs, 400, 335) === true)

// X. fight band builder: vision/CC change displayed bands vs open-lane baseline
const open = fightDodgeBands({ vision: 'mutual', crowdControlled: false, … })
const cc = fightDodgeBands({ vision: 'mutual', crowdControlled: true, … })
assert('CC flattens fight bands', cc.bands!.best - cc.bands!.worst < open.bands!.best - open.bands!.worst + 1e-6)
```

Regression watch: Pass-1–4 strategy asserts (envelope / mix / precommit / CD / charges / NE unknown packet / Ghost channel / MS strafe); kit tag alone; CC point-blank; faster missile → higher xH; Flash-up ⇒ mix===typical.

---

## 4. arXiv / theory cites (Pass-5 deepen)

| id / ref | use |
|----------|-----|
| [arXiv:2604.17811](https://arxiv.org/abs/2604.17811) Kill-prob vs miss | Displayed SSKP bands must match the packet scalar’s hypothesis set |
| [arXiv:2511.21633](https://arxiv.org/abs/2511.21633) Bang-Bang Evasion | Active UI cell = defender mixed strategy actually used (typical vs Flash-envelope mix) |
| [arXiv:1804.05021](https://arxiv.org/abs/1804.05021) / [2410.02966](https://arxiv.org/abs/2410.02966) Fitts / SDN | Ghost/MS → σ_juke strafe only; fix dead Ghost predicate, do not retag aim |
| Classic cookie-cutter / Washburn | UI % still \(P(\|M\|<R)\) under σ; no PN |

---

## 5. Expected gains vs regressions

| gap | after Pass-5 apply |
|-----|--------------------|
| Dodge row ≠ packet xH | Shared `averageXhRows` / `estimateXhRowVsEnemy` |
| Ghost equipped never bumps strafe | Explicit buff flag and/or live-MS-only predicate |
| typical always active | Active = packet policy; caption under dodge row |
| Stub blind to FoW/CC/utilMult | Same inputs + scaled bands as damage path |
| Pass-4 Q–T never landed | Eval U–X on exported helpers |

**Out of scope:** geo/aim/vision formula changes; new MobilityClass hit tags; BASE×ZONE×VISION; Hexflash second envelope; rewriting landed σ_juke envelope math.

---

## 6. Decision

**`KEEP_CANDIDATE`**

Rationale: Passes 1–4 fixed envelope / precommit / NE / Ghost / charges / CC-break, surfaced a dodge row, and plumbed MS/CC into the **damage** path (103/103). Pass-5 residual is almost entirely **fidelity**:

1. Unify stub + `meanXhVsEnemies` into one band aggregator (vision/CC/utilMult/range parity).  
2. Highlight mix vs typical from packet policy; caption under dodge row.  
3. Fix dead Ghost-without-live-MS predicate; optional slow→MS for σ_juke only.

Orchestrator should apply §§2–3 in `combat.ts` / types / `CombatResult` (+ light CSS), export tiny helpers for eval U–X, re-run `npm run eval:xh`, keep only if rate stays 103/103 before new asserts, then ≥ all new checks.

**Verdict: KEEP_CANDIDATE — unify dodge bands with packet xH path; fix Ghost/UI policy fidelity; no new mobility×P(hit) tags.**
