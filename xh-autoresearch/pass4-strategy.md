# Pass-4 STRATEGY — σ_juke / bands→UI residual only

**Axis:** strategy (σ_juke ready-state + dodge bands → CombatResult)  
**Status:** `KEEP_CANDIDATE`  
**Constraint:** critique + snippets only; **do not edit** production files in this pass.  
**Eval at write:** `math_pass_rate=88/88 (1.0000)` post Pass-3 KEEP. Deepen residual only; do not re-propose landed KEEP work; no `BASE×ZONE×VISION`.

---

## 0. Already landed (do NOT re-propose)

| Pass | Landed |
|------|--------|
| 1 | Flash envelope for worst; windup dodge window; ready budgets; soft `dodgeScale` |
| 2 | Precommit residual; `bands.mix` via `neMixCorridorVal`; `flashCdRemainingSec`; combat Flash/dash ready |
| 3 | Ghost/charges/CC-break; NE unknown→packet mix + π_down; `MatchupResult.xhDodgeBand`; Expected-cell hint → dodge-budget copy |

Eval strategy probes (envelope / mix / precommit / CD / charges / NE unknown) are green. Residual is **product surfacing + combat band plumbing fidelity**, not another σ_juke formula rewrite.

---

## 1. Critique (Pass-4 failure modes)

### 1.1 Smoking gun: `xhDodgeBand` computed, never shown

Pass-3 attached dodge SSKPs to `MatchupResult`, but `CombatResult.tsx` still only renders **strength remakes** (`missShots` / `expected` / `hitAll`). `result.xhDodgeBand` is unused.

```tsx
// CombatResult.tsx — hint fixed, numbers absent
<BandCell
  label="Expected xH"
  hint="dodge budget: depleted / observed / Flash envelope"
  …
/>
// no read of result.xhDodgeBand.{worst,typical,mix,best}
```

Attackers still cannot see Pass-1–3 envelope math as percentages. The middle strength cell answers “trade under expected xH mode,” not “defender Flash-up vs depleted corridor.”

**Prefer this deepen over any new mobility×P(hit) tag.** Surface the existing bands; do not invent kit priors.

### 1.2 `xhDodgeBand` stub is a thin demo, not fight math

```ts
// combat.ts simulateMatchup return
xhDodgeBand: (() => {
  const blue = input.blue.find(isAlive)
  const red = input.red.find(isAlive)
  …
  const est = estimateXh({
    targetChampionId: red.championId,
    abilityRange: 900,           // hardcoded — ignores packet ability
    // no vision / softVision / MS / ghost / crowdControlled
    …
  })
  return est.bands ? { … } : undefined
})()
```

Gaps vs `meanXhVsEnemies`:

| input | damage path | `xhDodgeBand` stub |
|-------|-------------|--------------------|
| ability range | per-packet | always 900 |
| vision / softVision / spotted | yes | no |
| `targetMovespeed` / Ghost | partial | no |
| CC / `ccBreakReady` | break only; **no `crowdControlled`** | break only |
| direction | each caster→enemies | blue→red first alive only |
| utilMult | yes | no |

So even if UI rendered the field tomorrow, NvM / FoW / Ghost / CC fights would show a mismatched envelope.

### 1.3 `meanXhVsEnemies` still drops `est.bands`

```ts
function meanXhVsEnemies(…): number {
  …
  return Math.min(0.97, est.xH * utilMult)  // bands discarded
}
```

`FighterResult` has no `xhBands`; only match-level stub. Packet scalar correctly uses typical/mix policy, but per-fighter dodge metadata never reaches UI details / ability log.

### 1.4 Ghost / MS still starved in the typed loadout path

`FighterLoadout.liveStats` Pick is:

```ts
Pick<CombatStats, 'hp' | 'hpMax' | 'armor' | 'mr' | 'ad' | 'ap' | 'attackSpeed'>
```

— **no `movespeed`**. Combat tries:

```ts
enemy.liveStats && 'movespeed' in (enemy.liveStats as object)
  ? (enemy.liveStats as { movespeed?: number }).movespeed
  : undefined
```

`computeStats` already has MS (Ghost buff / slows / Cloud), but it is never passed into `estimateXh`. Meanwhile `ghostActive` fires on **Ghost equipped**, not buff-active — overstates continuous strafe when Ghost is on CD and understates when MS is in live stats without the summoner string.

Do **not** add a Ghost×BASE prior — plumb `stats.movespeed` (and only then optional `ghostActive` coeff).

### 1.5 Hard CC never reaches σ_juke from combat

`estimateXh` honors `crowdControlled`, but `meanXhVsEnemies` / `xhDodgeBand` never set it from utility (Nasus W / roots / stuns). Pass-3 CC-break path is dead in product fights: break tool ready, but `cc` is always false → full discrete budget. Eval M-style reopen is engine-only.

### 1.6 Out of scope (do not chase this pass)

- New MobilityClass / zone / vision multiplicative tags  
- Rewriting Flash envelope, precommit formula, or π priors (landed)  
- Hexflash as a second Flash envelope (defer; CD-unknown mix already covers uncertainty)  
- Geo width / aim SDN / belief LKP / xHm empirics  

---

## 2. Minimal patch (orchestrator apply order)

Hard rules: no `BASE×ZONE×VISION`; no PN; strategy only varies σ_juke inputs + combat/UI plumbing. Prefer bands→UI over new mobility×P(hit) tags.

### 2.1 Surface dodge bands in CombatResult (highest priority)

Keep miss / expected / hit_all. Add a dedicated dodge row from `result.xhDodgeBand`:

```tsx
{result.xhDodgeBand && (
  <div className="dodge-band" aria-label="Skillshot dodge envelope">
    <p className="band-title">xH dodge</p>
    <div className="band-row dodge-row">
      <DodgeCell label="worst" hint="Flash envelope" value={result.xhDodgeBand.worst} />
      <DodgeCell label="typical" hint="observed budget" value={result.xhDodgeBand.typical} active />
      {result.xhDodgeBand.mix != null && (
        <DodgeCell label="mix" hint="NE Flash prior" value={result.xhDodgeBand.mix} />
      )}
      <DodgeCell label="best" hint="depleted" value={result.xhDodgeBand.best} />
    </div>
  </div>
)}
```

```tsx
function DodgeCell({ label, hint, value, active }: {
  label: string; hint: string; value: number; active?: boolean
}) {
  return (
    <div className={`band-cell dodge-cell ${active ? 'active' : ''}`}>
      <span className="band-label">{label}</span>
      <span className="band-hint">{hint}</span>
      <strong className="dodge-pct">{Math.round(value * 100)}%</strong>
    </div>
  )
}
```

Eyebrow / Expected hint stay dodge-budget language (already fixed). Optional: mark `mix` active when packet policy used Flash-unknown (`xhMode === 'expected'` + mix≈avg path — document only; UI highlight if `mix` present and Flash CD unknown on primary target).

### 2.2 One shared band aggregator (replace stub)

```ts
function meanXhVsEnemies(…): { xH: number; bands?: XhDodgeBands } {
  const rows = living.map((enemy) => {
    const flash = flashReadyFromLoadout(enemy)
    const statsMs = enemyStatsMs(enemy) // from computeStats / liveStats.movespeed
    const est = estimateXh({
      …existing,
      targetMovespeed: statsMs,
      ghostActive: ghostBuffActive(enemy), // buff edge, not merely equipped
      crowdControlled: hardCcOn(enemy, targetDebuffs),
      ccBreakReady: ccBreakReadyFromLoadout(enemy),
    })
    const scale = (p: number) => Math.min(0.97, p * utilMult)
    const packet =
      flash === undefined && est.bands?.mix != null
        ? est.bands.mix
        : est.xH
    return {
      xH: scale(packet),
      bands: est.bands && {
        worst: scale(est.bands.worst),
        typical: scale(est.bands.typical),
        best: scale(est.bands.best),
        mix: est.bands.mix != null ? scale(est.bands.mix) : undefined,
      },
    }
  })
  return averageXhRows(rows) // mean xH; mean bands componentwise
}
```

Wire `MatchupResult.xhDodgeBand` from the **same** aggregator used for primary expected packets (first blue skillshot range vs red, or fight-average of living pairs — pick one and document). Drop hardcoded `abilityRange: 900`.

Optional: `FighterResult.xhBands` for ability-log hover; not required if match-level row ships.

### 2.3 MS / Ghost / CC plumbing only (no new σ tags)

```ts
// types.ts — allow MS on live overlay
liveStats?: Partial<Pick<CombatStats,
  'hp' | 'hpMax' | 'armor' | 'mr' | 'ad' | 'ap' | 'attackSpeed' | 'movespeed'>>

function enemyStatsMs(f: FighterLoadout): number | undefined {
  return f.liveStats?.movespeed // else leave undefined → xh default 335
}

function ghostBuffActive(f: FighterLoadout): boolean {
  // Prefer MS already in liveStats; coeff nudge only if Ghost buff flagged without MS
  return f.ghostActive === true
}

function hardCcOn(f: FighterLoadout, util: ResolvedUtility): boolean {
  return util.hardCc === true || f.crowdControlled === true
}
```

Do **not** change `jukeFromBudget` math unless CC plumbing proves eval gap; Pass-3 restore path already exists.

### 2.4 Tiny UI-facing factor (optional, only if bands still opaque)

When rendering, show which packet policy applied:

```
packet: typical | mix (Flash CD unknown)
```

as a one-line caption under the dodge row — still not a mobility×hit tag.

---

## 3. New invariants (add to `eval-xh-math.ts` — do not soften 88)

Engine math already covers Ghost/charges/NE. Pass-4 asserts should lock **plumbing contracts** the UI depends on (pure functions / exported helpers), not React:

```ts
// Q. Band average helper preserves order worst ≤ mix? ≤ typical ≤ best
const avg = averageXhRows([
  { xH: 0.4, bands: { worst: 0.3, typical: 0.4, best: 0.6, mix: 0.35 } },
  { xH: 0.5, bands: { worst: 0.4, typical: 0.5, best: 0.7, mix: 0.45 } },
])
assert('avg bands ordered', avg.bands!.worst <= avg.bands!.typical && avg.bands!.typical <= avg.bands!.best)
assert('avg mix in [worst,typical]', avg.bands!.mix! >= avg.bands!.worst - 1e-9 && avg.bands!.mix! <= avg.bands!.typical + 1e-9)

// R. CC flag flattens; break reopen (engine already — keep regression if combat exports hardCcOn)
const flat = estimateXh(base({
  targetChampionId: 'Akali', dashReady: true, flashReady: true,
  crowdControlled: true, missileSpeed: 1000,
}))
assert('CC flat bands', flat.bands!.best - flat.bands!.worst < 0.01)

// S. MS from input lowers typical vs default (Ghost channel already Pass-3 — keep)
const slow = estimateXh(base({
  targetChampionId: 'Lux', dashReady: false, flashReady: false,
  targetMovespeed: 335, missileSpeed: 1000,
}))
const fast = estimateXh(base({
  targetChampionId: 'Lux', dashReady: false, flashReady: false,
  targetMovespeed: 415, missileSpeed: 1000,
}))
assert('MS strafe: faster ⇒ xH ≤', fast.xH <= slow.xH + 1e-9)
```

If orchestrator extracts `averageXhRows` / fight-band builder to a testable module, add:

```ts
// T. Fight band builder uses ability range (not 900 default) when provided
const short = fightDodgeBands({ abilityRange: 600, … })
const long = fightDodgeBands({ abilityRange: 1200, … })
assert('range enters band builder', short.typical !== long.typical || short.worst !== long.worst)
```

Regression watch: Pass-1–3 strategy asserts A–P / charges / NE unknown packet; kit tag alone; CC point-blank; faster missile → higher xH; Flash-up ⇒ mix===typical.

---

## 4. arXiv / theory cites (Pass-4 deepen)

| id / ref | use |
|----------|-----|
| [arXiv:2604.17811](https://arxiv.org/abs/2604.17811) Kill-prob vs miss | Report pure + mixed SSKP bands to the decision surface (UI), not only scalar packet |
| [arXiv:2511.21633](https://arxiv.org/abs/2511.21633) Bang-Bang Evasion | Worst/typical/best remain discrete-budget hypotheses; UI labels map to envelope / observed / depleted |
| [arXiv:1804.05021](https://arxiv.org/abs/1804.05021) / [2410.02966](https://arxiv.org/abs/2410.02966) Fitts / SDN | MS→σ_juke strafe only; do not retag aim or invent Ghost×hit |
| Classic cookie-cutter / Washburn | Displayed % still \(P(\|M\|<R)\) under σ; no PN |

---

## 5. Expected gains vs regressions

| gap | after Pass-4 apply |
|-----|--------------------|
| Bands invisible in fight UI | Dodge row: worst / typical / mix / best % |
| Stub ≠ damage path | Shared aggregator; real range + vision + MS + CC |
| `meanXh` drops bands | Returns + averages `XhDodgeBands` |
| MS typed out of liveStats | Include `movespeed`; feed `estimateXh` |
| CC never set from combat | `crowdControlled` from utility → σ_juke flatten/break |

**Out of scope:** geo/aim/vision formula changes; new MobilityClass hit tags; BASE×ZONE×VISION; Hexflash second envelope.

---

## 6. Decision

**`KEEP_CANDIDATE`**

Rationale: Passes 1–3 fixed internal envelope / precommit / NE / Ghost / charges / CC-break and attached `xhDodgeBand` (88/88). Pass-4 residual is almost entirely **product surface**:

1. Render dodge SSKP bands in `CombatResult` (prefer over new mobility×hit tags).  
2. Replace the hardcoded blue→red `abilityRange:900` stub with the same band aggregator as damage xH.  
3. Plumb MS + hard-CC into that path so the visible bands match σ_juke inputs already in `xh.ts`.

Orchestrator should apply §§2–3 in `combat.ts` / types / `CombatResult` (+ light CSS), optional tiny eval Q–T, re-run `npm run eval:xh`, keep only if rate stays 88/88 before new asserts, then ≥ all new checks.

**Verdict: KEEP_CANDIDATE — surface xhDodgeBand in CombatResult; unify combat band plumbing (MS/CC/range); no new mobility×P(hit) tags.**
