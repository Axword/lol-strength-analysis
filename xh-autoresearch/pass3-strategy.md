# Pass-3 STRATEGY — Ghost/charges/CC-break, NE policy, bands→UI

**Axis:** strategy (σ_juke / ready-state / strategic bands residual)  
**Status:** `KEEP_CANDIDATE`  
**Constraint:** critique + snippets only; **do not edit** `src/engine/xh.ts` in this pass.  
**Eval at write:** `math_pass_rate=65/65 (1.0000)` post Pass-2 KEEP. Deepen only; do not re-propose landed work; do not soften checks.

---

## 0. Already landed (do NOT re-propose)

| Pass | Landed |
|------|--------|
| 1 | Flash envelope for worst; windup dodge window; ready budgets; soft `dodgeScale` |
| 2 | Precommit residual (~40 uu envelope-only); `bands.mix` via `neMixCorridorVal`; `flashCdRemainingSec`; combat passes Flash/dash ready |

Probe sanity (post Pass-2): envelope / mix / precommit / CD clock asserts green (F–J in eval). Residual is **product plumbing + ready-state fidelity**, not the envelope bug.

---

## 1. Critique (Pass-3 failure modes)

### 1.1 Smoking gun: dodge bands still never reach the fight UI

Pass-2 §2.1 sketched `XhDodgeBands` / `xhDodgeBand` on `MatchupResult`. **Not applied.**

```ts
// combat.ts — still scalar-only
function meanXhVsEnemies(…): number {
  …
  return Math.min(0.97, est.xH * utilMult)  // drops est.bands entirely
}
```

`CombatResult` strength band is still the three `xhMode` remakes; middle hint remains **“mobility + zone + vision”** (prior-era copy). Attackers still cannot see Pass-1/2 dodge envelope in the verdict.

**Prefer this deepen over new mobility tags:** expose `{worst,typical,mix,best}` as fight metadata; keep packet scalar on typical (or mix policy §1.5).

### 1.2 Ghost MS never enters σ_juke

`XhEstimateInput.targetMovespeed` exists and strafe = `ms * w * 0.45`, but `meanXhVsEnemies` never passes:

- live `enemy` combat `movespeed` (Ghost / MS buffs / slows already in stats)
- nor a `ghostActive` flag

Ghost-holding targets are modeled as 335 default. That understates **continuous** juke (not discrete Flash). Do **not** invent a Ghost×BASE prior — feed MS.

### 1.3 Multiple dash charges collapsed to boolean

```ts
dashBudgetFromMobility: one_dash→425, two_dash→700, high→900
dashReady?: boolean  // all-or-nothing into dashTyp
```

Riven / Ahri / Nidalee-style multi-charge kits: `dashReady=true` dumps full kit budget; `false` zeroes typical. No `dashChargesRemaining` → typical cannot sit between depleted and full kit. Worst envelope already uses `max(dashTyp, kitDash)` — good — but typical is coarse.

### 1.4 Cleanse / QSS vs CC path

CC → `jukeFromBudget` early-return: strafe-only, **no** dash/Flash, bands flat (eval D/J green — keep).

Gap: defender with Cleanse / QSS / Mikael’s can break hard CC inside reaction+windup. Today `crowdControlled=true` forever flattens envelope even if loadout has a break tool ready. That overstates xH vs breakable CC.

Do **not** ignore CC; model a **partial restore** of discrete budget when `ccBreakReady` and window allows cast+break.

### 1.5 NE mix policy still half-wired

`neMixCorridorVal` known-down and unknown branches are **identical** (`π=0.35` mix of typical/worst). Packet always returns `xH = typical.xH`; mix only lives in `bands.mix`. Combat never reads mix when `flashReady === undefined`.

So FoW / map-import “Flash CD unknown” fights still scale damage with Flash-down typical, while the strategic prior sits unused. Policy choice needed (document, don’t invent a second σ tag).

### 1.6 Ambush reaction vs buffered Flash / precommit scale

- Ambush `τ=0.38` is constant; `spottedByTarget` only bumps **blind**, not ambush. Ambush with telegraph already visible (defender facing cast) should not always get the full surprise delay.
- Precommit is a flat `min(40, 0.35·R_hit)` on **worst only** when `dodgeWindow≈0`. It does not scale with buffered Flash intent (envelope already assumes 400 uu Flash, but precommit SD is tiny vs Flash impulse). Point-blank Flash-up envelope separation is eval-green but shallow — buffered Flash should widen worst a bit more without resurrecting full `dodgeScale(w>0)` discrete at true zero window.

---

## 2. Minimal patch (orchestrator apply order)

Hard rules: no `BASE×ZONE×VISION`; no PN; strategy only varies σ_juke + combat/UI plumbing. Prefer bands→UI over new mobility×P(hit) tags.

### 2.1 Expose dodge bands through combat → UI (highest priority)

**types.ts:**

```ts
export interface XhDodgeBands {
  worst: number
  typical: number
  best: number
  mix?: number
}

export interface FighterResult {
  // …
  avgXh?: number
  xhBands?: XhDodgeBands
}

export interface MatchupResult {
  // …
  strengthBand?: StrengthBand
  /** Dodge-envelope SSKP (not xhMode remakes). */
  xhDodgeBand?: XhDodgeBands
}
```

**combat.ts** — return bands; plumb MS + optional ready extras:

```ts
function meanXhVsEnemies(…): { xH: number; bands: XhDodgeBands } {
  const rows = living.map((enemy) => {
    const flash = flashReadyFromLoadout(enemy)
    const est = estimateXh({
      targetChampionId: enemy.championId,
      casterPosition: caster.position,
      targetPosition: enemy.position,
      abilityRange,
      vision: resolved?.vision ?? 'unknown',
      softVision: resolved?.softVision,
      spottedByTarget: resolved?.spottedByTarget,
      dashReady: enemy.dashReady,
      dashChargesRemaining: enemy.dashChargesRemaining,
      flashReady: flash,
      flashCdRemainingSec: enemy.flashCdRemainingSec,
      targetMovespeed: enemyLiveMs(enemy), // from computeStats / liveStats
      crowdControlled: /* utility hard-CC flag */,
      ccBreakReady: ccBreakReadyFromLoadout(enemy),
      ghostActive: summonerActive(enemy, /ghost/i),
    })
    const scale = (p: number) => Math.min(0.97, p * utilMult)
    // Policy: CD unknown → packet uses mix; else typical (§2.5)
    const packet =
      flash === undefined && est.bands?.mix != null
        ? est.bands.mix
        : est.xH
    return {
      xH: scale(packet),
      bands: {
        worst: scale(est.bands!.worst),
        typical: scale(est.bands!.typical),
        best: scale(est.bands!.best),
        mix: est.bands?.mix != null ? scale(est.bands.mix) : undefined,
      },
    }
  })
  return averageRows(rows)
}
```

**CombatResult:** keep miss/expected/hit_all; add dodge row; fix hint:

```
xH dodge   [ worst | typical | mix | best ]
hint: "dodge budget: depleted / observed / Flash envelope"
```

Replace `"mobility + zone + vision"`.

### 2.2 Ghost / MS → strafe only (no tag prior)

```ts
// Inside jukeFromBudget / estimateXh apply:
const ms = input.targetMovespeed ?? 335
const strafeCoeff = input.ghostActive ? 0.55 : 0.45  // was fixed 0.45
const strafe = ms * w * strafeCoeff
```

Combat must pass `targetMovespeed` from stats (Ghost buff already in `movespeed`). `ghostActive` only nudges coeff when buff edge-case isn’t in stats yet. **Never** multiply BASE×Ghost.

### 2.3 Dash charges (budget fraction, not new MobilityClass)

```ts
// XhEstimateInput
dashChargesRemaining?: number  // 0..N; undefined → boolean dashReady path

// typical dash uu:
const chargesMax = targetMobility === 'two_dash' ? 2
  : targetMobility === 'high' ? 3 : 1
const dashTyp = (() => {
  if (input.dashChargesRemaining != null) {
    const frac = Math.min(1, Math.max(0, input.dashChargesRemaining / chargesMax))
    return kitDash * frac
  }
  return dashReadyObs ? kitDash : 0
})()
// worst envelope unchanged: Math.max(dashTyp, kitDash) + Flash 400
```

Still distance budget → σ_juke; not a hit mult.

### 2.4 CC break (Cleanse / QSS) — partial discrete restore

```ts
function ccBreakReadyFromLoadout(f: FighterLoadout): boolean {
  const spells = f.summonerSpells ?? []
  if (spells.some((s) => /cleanse|quicksilver|qss|mikael/i.test(s))) {
    // optional: f.cleanseCdRemainingSec <= 0
    return f.ccBreakCdRemainingSec == null || f.ccBreakCdRemainingSec <= 0
  }
  return false
}

// In jukeFromBudget when cc && ccBreakReady && window >= 0.15:
// treat as soft-CC for discrete only (strafe still reduced):
if (cc && !(input.ccBreakReady && w >= 0.15)) {
  return ms * w * 0.15
}
if (cc && input.ccBreakReady && w >= 0.15) {
  const s = dodgeScale(Math.max(0, w - 0.12)) // break cast tax
  const strafe = ms * w * 0.20
  const discrete = Math.hypot(dashUu * s * 0.25, flashUu * s * 0.25)
  return Math.hypot(strafe * 0.55, discrete)
}
```

Invariant: hard CC **without** break stays flat/high; with break, `worst < typical` can reopen under slow missiles. Point-blank CC without window still `xH > 0.85`.

### 2.5 NE mix policy when CD unknown

Differentiate branches + use mix for packets when unknown:

```ts
export function neMixCorridorVal(bands, opts): number {
  if (opts.flashReady === true) return bands.typical
  const piUnk = opts.piFlash ?? 0.35
  const piDown = opts.piFlashDown ?? 0.20  // less fear when known down
  if (opts.flashReady === false && !opts.flashCdUnknown) {
    return (1 - piDown) * bands.typical + piDown * bands.worst
  }
  // unspecified / unknown CD — strategic prior
  return (1 - piUnk) * bands.typical + piUnk * bands.worst
}
```

```ts
// estimateXh return policy
const xH =
  flashCdUnknown && mix != null ? mix : typical.xH
// factors: juke:ne_mix:π=0.35 when unknown; juke:ne_mix_down:π=0.20 when known down
```

Eval already has mix∈[worst,typical] and known-down mix<typical — keep; add unknown π ≥ known-down π fear (mix_unknown ≤ mix_knownDown when same bands… actually unknown has higher π → lower mix). Assert: `mix_unknown + ε < mix_knownDown` only if same typical/worst — yes with πUnk>πDown.

### 2.6 Ambush τ trim + buffered-Flash precommit scale

```ts
let tau = reactionSec(vision)
if (input.spottedByTarget && vision === 'blind') tau += 0.08
// Defender already tracking caster cast → less surprise
if (input.spottedByTarget && vision === 'ambush') tau = Math.min(tau, 0.28)

const precommitUu = !cc && dodgeWindow <= 1e-6 && T_windup > tau * 0.45
  ? Math.min(
      // buffered Flash anticipation: scale with envelope intent, still ≪ full 400·0.35
      flashTypReady || flashCdUnknown ? 55 : 40,
      0.35 * R_hit,
    )
  : 0
// still envelope-only on sigmaJukeWorst
```

Keeps cookie-cutter; no PN.

---

## 3. New invariants (add to `eval-xh-math.ts` — do not soften 65)

```ts
// K. Ghost / high MS lowers typical vs default MS (strafe channel)
const baseMs = estimateXh(base({
  targetChampionId: 'Lux', dashReady: false, flashReady: false,
  targetMovespeed: 335, missileSpeed: 1000,
}))
const ghostMs = estimateXh(base({
  targetChampionId: 'Lux', dashReady: false, flashReady: false,
  targetMovespeed: 335 * 1.24, ghostActive: true, missileSpeed: 1000,
}))
assert('Ghost/MS: higher MS ⇒ lower or equal xH', ghostMs.xH <= baseMs.xH + 1e-9)
assert('Ghost/MS: material strafe gap', baseMs.xH - ghostMs.xH > 0.01)

// L. Partial dash charges sit between 0 and full kit
const ch0 = estimateXh(base({
  targetChampionId: 'Akali', dashChargesRemaining: 0, flashReady: false, missileSpeed: 1000,
}))
const ch1 = estimateXh(base({
  targetChampionId: 'Akali', dashChargesRemaining: 1, flashReady: false, missileSpeed: 1000,
}))
const chFull = estimateXh(base({
  targetChampionId: 'Akali', dashReady: true, flashReady: false, missileSpeed: 1000,
}))
assert('charges: 0 ≈ depleted typical', Math.abs(ch0.xH - ch0.bands!.best) < 0.03)
assert('charges: partial between depleted and full', ch1.xH < ch0.xH - 1e-6 && ch1.xH > chFull.xH + 1e-6)

// M. CC + break tool can reopen envelope under slow missile
const ccFlat = estimateXh(base({
  targetChampionId: 'Akali', dashReady: true, flashReady: true,
  crowdControlled: true, missileSpeed: 1000,
}))
const ccBreak = estimateXh(base({
  targetChampionId: 'Akali', dashReady: true, flashReady: true,
  crowdControlled: true, ccBreakReady: true, missileSpeed: 1000,
}))
assert('CC no-break: bands flat', ccFlat.bands!.best - ccFlat.bands!.worst < 0.01)
assert('CC+break: worst < typical (envelope reopen)', ccBreak.bands!.worst + 1e-6 < ccBreak.bands!.typical)
assert('CC+break still high at moderate range', ccBreak.xH > 0.55)

// N. NE: unknown fears Flash more than known-down (π_unk ≥ π_down)
const b = { worst: 0.30, typical: 0.50, best: 0.70 }
const mixUnk = neMixCorridorVal(b, { flashCdUnknown: true, piFlash: 0.35 })
const mixDown = neMixCorridorVal(b, { flashReady: false, flashCdUnknown: false, piFlash: 0.35 })
// After patch with piDown=0.20:
assert('ne: unknown mix ≤ known-down mix', mixUnk <= mixDown + 1e-9)

// O. Ambush + spottedByTarget trims τ ⇒ dodgeWindow↑ ⇒ xH down vs pure ambush
const amb = estimateXh(base({
  vision: 'ambush', targetChampionId: 'Akali', dashReady: true, flashReady: true,
  missileSpeed: 1200, spottedByTarget: false,
}))
const ambSeen = estimateXh(base({
  vision: 'ambush', targetChampionId: 'Akali', dashReady: true, flashReady: true,
  missileSpeed: 1200, spottedByTarget: true,
}))
assert('ambush track: spotted ⇒ xH ≤ surprise ambush', ambSeen.xH <= amb.xH + 1e-9)

// P. Precommit Flash-up ≥ Flash-unknown residual separation (worst gap)
const pbFlash = estimateXh(base({
  vision: 'ambush', targetChampionId: 'Akali', dashReady: true, flashReady: true,
  targetPosition: { x: mid.x + 0.008, y: mid.y }, missileSpeed: 3000, abilityRange: 700,
}))
assert('precommit Flash-up: band spread', pbFlash.bands!.typical - pbFlash.bands!.worst > 0.005)
```

Regression watch: A–J strategy asserts; kit tag alone; CC point-blank > 0.85; faster missile → higher xH; `dash+flash ready lowers xH`; mix∈[worst,typical]; Flash-up ⇒ mix===typical.

---

## 4. arXiv / theory cites (Pass-3 deepen)

| id / ref | use |
|----------|-----|
| [arXiv:2511.21633](https://arxiv.org/abs/2511.21633) Bang-Bang Evasion | Multi-impulse charge budgets; Cleanse restores access to discrete bang-bang set |
| [arXiv:2604.17811](https://arxiv.org/abs/2604.17811) Kill-prob vs miss | `xH_mix=∑π_i SSKP(σ_i)`; packet policy when hypothesis prior ≠ oracle CD |
| [arXiv:2603.05363](https://arxiv.org/abs/2603.05363) Estimation delays | Ambush τ vs tracked caster (`spottedByTarget`); buffered precommit under delay |
| [arXiv:1804.05021](https://arxiv.org/abs/1804.05021) / [2410.02966](https://arxiv.org/abs/2410.02966) Fitts / SDN | Ghost MS is process-noise strafe amplitude, not aim retag — keep σ_aim untouched |
| Classic cookie-cutter / Washburn | Bands + mix still \(P(\|M\|<R)\); no PN |

---

## 5. Expected gains vs regressions

| gap | after Pass-3 apply |
|-----|--------------------|
| UI drops dodge bands | `xhDodgeBand` + row; hint fixed |
| Ghost / MS ignored | `targetMovespeed` (+ optional coeff) in combat→xh |
| Boolean-only dashes | `dashChargesRemaining` fraction of kitDash |
| CC ignores Cleanse/QSS | `ccBreakReady` partial discrete restore |
| Mix unused when CD unknown | packet `xH=mix`; π_down < π_unk |
| Ambush always full surprise | spotted ambush τ trim |
| Flat precommit | slight Flash-ready scale on envelope residual |

**Out of scope:** geo width/speed, vision LKP scrubber, xHm empirics, new MobilityClass tags as P(hit).

---

## 6. Decision

**`KEEP_CANDIDATE`**

Rationale: Pass-1/2 fixed internal envelope/windup/precommit/mix/CD clock (65/65). Pass-3 residual is ready-state fidelity + the still-missing product surface:

1. Surface dodge bands in combat/UI (prefer over new mobility×hit tags).  
2. Ghost/MS + dash charges + CC-break as **budget / strafe** inputs only.  
3. NE packet policy when Flash CD unknown + ambush/precommit timing polish.

Orchestrator should apply §§2–3 in `xh.ts` / `combat.ts` / types / `CombatResult` / eval, re-run `npm run eval:xh`, keep only if rate does not drop below 65/65 before new K–P asserts, then ≥ all new checks.

**Verdict: KEEP_CANDIDATE — expose dodge bands to combat/UI; deepen Ghost/charges/CC-break + NE unknown policy without new mobility×P(hit) tags.**
