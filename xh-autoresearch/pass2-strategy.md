# Pass-2 STRATEGY — bands → combat, NE mix, precommit, summoner CDs

**Axis:** strategy (σ_juke / ready-state / strategic bands → combat surface)  
**Status:** `KEEP_CANDIDATE`  
**Constraint:** critique + snippets only; **do not edit** `src/engine/xh.ts` in this pass.  
**Eval at write:** `math_pass_rate=41/41 (1.0000)` post Pass-1 KEEP (Flash envelope + windup dodge window). Deepen only; do not weaken checks.

---

## 0. Pass-1 residue (what is already green)

| Landed | Still shallow |
|--------|----------------|
| `worst` uses Flash envelope even when `flashReady=false` | Envelope is binary Flash-on; no CD clock |
| Windup `T_windup=0.28` shared with defender reaction | True `dodgeWindow=0` still flattens all three bands |
| Typical conditions on observed dash/Flash | Combat never passes ready flags from loadout |
| Soft `dodgeScale`; CC flattens bands | `XhEstimate.bands` computed then **dropped** before UI |
| Eval A–D strategy asserts green | No mixed-strategy / Nash toy over {best,typ,worst} |

Probe (post Pass-1): mid-range Akali dash-up / Flash-down →  
`bands ≈ { worst: 0.27, typical: 0.29, best: 0.63 }` — envelope works.  
Point-blank ambush fast missile → `worst ≡ typical ≡ best ≈ 0.995` — precommit still absent.

---

## 1. Critique (Pass-2 failure modes)

### 1.1 Smoking gun: combat strength band ≠ dodge bands

`estimateXh` returns `{ worst, typical, best }` dodge-budget SSKPs, but:

```ts
// combat.ts meanXhVsEnemies — keeps only scalar typical
const est = estimateXh({ … /* no dashReady / flashReady */ })
return Math.min(0.97, est.xH * utilMult)
```

`MatchupResult.strengthBand` is a **different** object: three full `simulateMatchup` runs under `xhMode ∈ {miss_shots, expected, hit_all}`. UI (`CombatResult`) labels the middle cell “Expected xH” with hint **“mobility + zone + vision”** — prior-era copy, and still not the Pass-1 dodge envelope.

So the product already ships a “strength band” visual, but it answers “what if every skillshot hits / whiffs,” not “what if defender Flash is up / down.” Attackers cannot see Pass-1 strategy math in the fight verdict.

### 1.2 No NE mix toy over corridor pure strategies

Bands are three **pure** defender hypotheses:

| pure | σ_juke | attacker-facing xH |
|------|--------|--------------------|
| best | strafe only (depleted) | highest |
| typical | observed dash/Flash | mid |
| worst | kit dash ceiling + Flash envelope | lowest |

Bang-bang evasion (Pass-1 cite arXiv:2511.21633) and SSKP-vs-miss (arXiv:2604.17811) motivate reporting a **mixed** corridor value when the attacker does not know which pure the defender will play (Flash CD unknown, dash buffered, etc.). Today there is no `xH_ne` / `xH_mix` — only three points and a discarded typical scalar.

Without a mix, calibration / empirics cannot score “strategic prior when CD unknown” separately from “oracle ready-state.”

### 1.3 Precommit residual still missing

Pass-1 §2.4 was optional and **not applied**. When `T_windup + t_go ≤ τ`:

```ts
dodgeWindow = 0 → dodgeScale(0) = 0 → discrete dash/Flash = 0
→ sigmaJukeWorst ≡ sigmaJukeTypical ≡ sigmaJukeBest
```

even if Flash is “up” in the envelope. Ambush point-blank with full kit looks identical to CC immobile for **band width** (all clamped high). That understates anticipation / buffered Flash during cast telegraph — the same windup clock we already added for post-missile reaction.

### 1.4 Summoner CD inputs are boolean + unwired

`XhEstimateInput` has `flashReady?: boolean` only. `FighterLoadout.summonerSpells` exists (Flash/Ghost/…), but `meanXhVsEnemies` never:

- sets `flashReady` from equipped Flash + remaining CD  
- passes `dashReady` from kit / timeline  
- models Ghost (MS inflate → strafe σ) or Cleanse/Quicksilver (CC path escape)

Default path: kit-prior dash, Flash treated as **down** (`flashReady === true` required). Map→calculator imports therefore systematically overstate typical xH vs Flash-holding targets.

---

## 2. Deepening plan (orchestrator apply order)

Do **not** resurrect `BASE_XH × ZONE × VISION`. Keep σ-corridor; strategy only varies σ_juke (and combat plumbing).

### 2.1 Expose dodge bands in combat output (sketch)

**Types** (`types.ts` — apply pass, not this file):

```ts
/** Dodge-budget SSKP bands from estimateXh (attacker POV). */
export interface XhDodgeBands {
  worst: number   // full envelope (Flash assumed)
  typical: number // observed ready state
  best: number    // depleted
  /** Optional NE / mix corridor value when CD unknown — see §2.2 */
  mix?: number
}

export interface FighterResult {
  // …
  avgXh?: number
  xhBands?: XhDodgeBands  // mean across skillshot targets
}

export interface MatchupResult {
  // …
  /** Existing: hit_all / expected / miss_shots fight outcomes */
  strengthBand?: StrengthBand
  /** NEW: aggregate dodge-envelope xH (not xhMode remakes) */
  xhDodgeBand?: XhDodgeBands
}
```

**combat.ts sketch** — return bands from the estimator, do not re-simulate:

```ts
function meanXhVsEnemies(…): { xH: number; bands: XhDodgeBands } {
  const rows = living.map((enemy) => {
    const est = estimateXh({
      targetChampionId: enemy.championId,
      casterPosition: caster.position,
      targetPosition: enemy.position,
      abilityRange,
      vision,
      dashReady: enemy.dashReady,           // §2.4
      flashReady: flashReadyFromLoadout(enemy),
      flashCdRemainingSec: enemy.flashCdRemainingSec,
      crowdControlled: /* from utility */,
    })
    const util = xhUtilityMultiplier(targetDebuffs)
    const scale = (p: number) => Math.min(0.97, p * util)
    return {
      xH: scale(est.xH),
      bands: {
        worst: scale(est.bands!.worst),
        typical: scale(est.bands!.typical),
        best: scale(est.bands!.best),
        mix: est.bands?.mix != null ? scale(est.bands.mix) : undefined,
      },
    }
  })
  // mean components across living enemies in range
  return averageRows(rows)
}
```

**UI sketch** (`CombatResult`): keep existing miss/expected/hit_all row; add a second compact row (or replace the stale hint) for dodge envelope:

```
xH dodge band   [ worst 27% | typical 29% | mix 31% | best 63% ]
```

Update hint from “mobility + zone + vision” → “dodge budget: depleted / observed / Flash envelope.” Prefer visual strength (who is favored under envelope) over raw σ dumps — aligns with product preference for win/strength bands.

**Preserve API:** `applyXhModeToPacket` still consumes scalar `xH` (typical or mix — pick one policy and document). Bands are additive metadata.

### 2.2 NE mix toy corridor valuation

Defender pure set after packing σ:

\[
\mathcal{A}=\{a_\text{best},a_\text{typ},a_\text{worst}\},\quad
u(a)=\mathrm{corridorHitProb}(R,\mu,\sigma(a))
\]

Attacker has committed the cast (ballistic cookie-cutter — **no** PN). Defender chooses mixed strategy \(\pi\) over \(\mathcal{A}\) to **minimize** hit probability when ready-state is uncertain.

**Toy NE / indifference mix** (closed form, no solver loop):

```ts
/**
 * When Flash CD is unknown (flashReady unset) and dodgeWindow > 0,
 * mix typical (Flash-down obs) vs worst (Flash-up envelope).
 * Indifference prior: π_flash = clip( remaining_uncertainty, 0.15..0.55 )
 * Else if both ready known: mix degenerates to typical (π=1 on observed).
 *
 * xH_mix = Σ π_i xH_i  (linear in SSKP — valid because attacker already fixed aim;
 * not a re-optimization of μ).
 */
export function neMixCorridorVal(bands: {
  worst: number; typical: number; best: number
}, opts: {
  flashReady?: boolean
  flashCdUnknown?: boolean
  /** Prior mass on Flash-up when unknown. Default 0.35. */
  piFlash?: number
}): number {
  if (opts.flashReady === true) {
    // observed Flash up → typical already includes Flash; slight pull to worst unused
    return bands.typical
  }
  if (opts.flashReady === false && !opts.flashCdUnknown) {
    // known down: mix envelope fear vs observed
    const pi = opts.piFlash ?? 0.35
    return (1 - pi) * bands.typical + pi * bands.worst
  }
  // unspecified: strategic prior between typical-obs and envelope
  const pi = opts.piFlash ?? 0.35
  return (1 - pi) * bands.typical + pi * bands.worst
}
```

Wire into `estimateXh` return (apply pass):

```ts
bands: {
  worst: worst.xH,
  typical: typical.xH,
  best: best.xH,
  mix: neMixCorridorVal(
    { worst: worst.xH, typical: typical.xH, best: best.xH },
    {
      flashReady: input.flashReady,
      flashCdUnknown: input.flashReady === undefined,
      piFlash: input.flashUpPrior,
    },
  ),
}
```

**Policy choice for packet scaling:** keep `xH = typical.xH` when ready known; when `flashReady === undefined`, optionally set `xH = bands.mix` so FoW/CD-unknown casts use the NE toy. Document in `factors`: `juke:ne_mix:π=0.35`.

**Eval toy (addition, do not soften):**  
`mix` lies in `[worst, typical]` when Flash unknown; equals `typical` when Flash known up; strictly `< typical` when Flash known down and `piFlash>0`.

Cites: mixed strategies over discrete bang-bang impulses (arXiv:2511.21633); soft lethality expectation under maneuver hypothesis set (arXiv:2604.17811). Still **not** homing guidance.

### 2.3 Precommit residual (land Pass-1 §2.4 properly)

When telegraph existed but post-missile window is zero, allow a small envelope-only lateral SD:

```ts
const T_windup = 0.28
const dodgeWindow = Math.max(0, T_windup + tGo - tau)

// Anticipation / buffered Flash during windup — envelope ONLY
const precommitUu =
  !cc && dodgeWindow <= 1e-6 && T_windup > tau * 0.45 ? 40 : 0

const sigmaJukeBest = jukeFromBudget(dodgeWindow, 0, 0)
const sigmaJukeTypical = jukeFromBudget(dodgeWindow, dashTyp, flashTyp)
let sigmaJukeWorst = jukeFromBudget(
  dodgeWindow,
  Math.max(dashTyp, kitDash),
  400,
)
if (precommitUu > 0) {
  sigmaJukeWorst = Math.hypot(sigmaJukeWorst, precommitUu)
}
```

Cap: `precommitUu ≤ 0.35 * R_hit` so point-blank CC (`cc=true`) stays `xH>0.85` and bands stay flat under CC.

Expected: ambush point-blank + Flash envelope → `worst < typical ≈ best` by a few points, not a full dash hypot.

### 2.4 Summoner CD inputs

**Input surface** (apply to `XhEstimateInput`):

```ts
flashReady?: boolean
/** Seconds until Flash available; 0 = ready. If set, overrides flashReady. */
flashCdRemainingSec?: number
/** Prior P(Flash up) when CD unknown. Default 0.35. */
flashUpPrior?: number
/** Ghost (or similar) active → MS already in targetMovespeed; optional extra strafe scale. */
ghostActive?: boolean
/** Exhaust on caster → optional leadSkill / σ_aim hook (strategy owns only MS side). */
```

**Helpers** (combat / parseSnapshot — outside xh.ts ok):

```ts
function flashReadyFromLoadout(f: FighterLoadout): boolean | undefined {
  const spells = f.summonerSpells ?? []
  const hasFlash = spells.some((s) => /flash/i.test(s))
  if (!hasFlash) return false
  if (f.flashCdRemainingSec == null) return undefined // unknown → NE mix
  return f.flashCdRemainingSec <= 0
}
```

**Inside juke (apply pass):**

```ts
const flashReadyObs =
  input.flashCdRemainingSec != null
    ? input.flashCdRemainingSec <= 0
    : input.flashReady === true
const flashTyp = flashReadyObs ? 400 : 0
// worst envelope still assumes 400 Flash uu regardless of CD
```

Ghost: prefer feeding buffed `targetMovespeed` from combat stats (already) over a second mobility mult. Optional `ghostActive` only scales strafe coeff `0.45 → 0.55`, never a BASE×tag prior.

Timeline feed: when scrubber exposes summoner CD remaining, plumb into loadout; until then `undefined` → mix prior, not silent Flash-down.

---

## 3. New invariants (add to `eval-xh-math.ts` — do not soften old 41)

```ts
// F. Precommit: envelope separates at zero post-missile window
const pbAmb = estimateXh(base({
  vision: 'ambush',
  targetChampionId: 'Akali',
  dashReady: true,
  flashReady: true,
  targetPosition: { x: mid.x + 0.008, y: mid.y },
  missileSpeed: 3000,
  abilityRange: 700,
}))
assert(
  'precommit: ambush point-blank still worst < typical',
  !!pbAmb.bands && pbAmb.bands.worst + 1e-6 < pbAmb.bands.typical,
  JSON.stringify(pbAmb.bands),
)

// G. NE mix in [worst, typical] when Flash CD unknown
const unk = estimateXh(base({
  targetChampionId: 'Akali',
  dashReady: true,
  // flashReady omitted
  missileSpeed: 1000,
}))
assert(
  'ne mix: worst ≤ mix ≤ typical when Flash unknown',
  !!unk.bands &&
    unk.bands.mix != null &&
    unk.bands.mix + 1e-9 >= unk.bands.worst &&
    unk.bands.mix <= unk.bands.typical + 1e-9,
  JSON.stringify(unk.bands),
)

// H. Known Flash-down + piFlash>0 ⇒ mix < typical
const knownDown = estimateXh(base({
  targetChampionId: 'Akali',
  dashReady: true,
  flashReady: false,
  flashUpPrior: 0.35,
  missileSpeed: 1000,
}))
assert(
  'ne mix: known Flash down still fears envelope',
  !!knownDown.bands &&
    knownDown.bands.mix != null &&
    knownDown.bands.mix + 1e-6 < knownDown.bands.typical,
  JSON.stringify(knownDown.bands),
)

// I. flashCdRemainingSec>0 ⇒ typical Flash-off; worst still envelope
const onCd = estimateXh(base({
  targetChampionId: 'Akali',
  dashReady: true,
  flashCdRemainingSec: 120,
  missileSpeed: 1000,
}))
assert(
  'summoner CD: Flash on CD ⇒ typical ≈ dash-only (≫ best gap from worst)',
  !!onCd.bands && onCd.bands.worst + 1e-6 < onCd.bands.typical,
  JSON.stringify(onCd.bands),
)

// J. CC + precommit still flat / high
const ccPb = estimateXh(base({
  vision: 'ambush',
  crowdControlled: true,
  targetChampionId: 'Akali',
  flashReady: true,
  targetPosition: { x: mid.x + 0.008, y: mid.y },
  missileSpeed: 3000,
}))
assert('CC point-blank still high', ccPb.xH > 0.85)
assert(
  'CC ⇒ bands flat even with precommit path',
  !!ccPb.bands && ccPb.bands.best - ccPb.bands.worst < 0.01,
)
```

Regression watch: existing A–E strategy asserts; `faster missile → higher xH`; `dash+flash ready lowers xH`; kit tag alone; point-blank CC > 0.85.

---

## 4. arXiv / theory cites (Pass-2 deepen)

| id / ref | use |
|----------|-----|
| [arXiv:2511.21633](https://arxiv.org/abs/2511.21633) Bang-Bang Evasion | Discrete impulse set → pure strategies; mix π over Flash-up/down |
| [arXiv:2604.17811](https://arxiv.org/abs/2604.17811) Kill-prob vs miss | \(xH_\text{mix}=\sum\pi_i\,\mathrm{SSKP}(\sigma_i)\) under fixed aim |
| [arXiv:2603.05363](https://arxiv.org/abs/2603.05363) Estimation delays | Windup telegraph → precommit residual when TOF window is zero |
| Classic cookie-cutter / Washburn | Bands + mix still \(P(\|M\|<R)\); no PN/homing |

---

## 5. Expected gains vs regressions

| gap | after Pass-2 apply |
|-----|--------------------|
| Combat ignores dodge bands | `xhDodgeBand` + UI row; hint fixed |
| No strategic prior when Flash CD unknown | `bands.mix` / optional `xH=mix` |
| Point-blank flat bands | precommit envelope SD (~40 uu) |
| Flash always treated down in combat | `flashCdRemainingSec` / loadout plumbing |
| Ghost / MS | via `targetMovespeed`, not tag mult |

**Out of scope this axis:** ability-specific width/speed (geo/aim), beliefMean FoW scrubber (vision), analytic xHm already landed (empirics).

---

## 6. Decision

**`KEEP_CANDIDATE`**

Rationale: Pass-1 fixed the internal envelope/windup math (41/41). Pass-2’s remaining strategy debt is **product wiring + one unfinished residual + a small NE toy**:

1. Surface dodge bands beside (not instead of) hit_all/expected/miss_shots.  
2. Add `neMixCorridorVal` for Flash-CD uncertainty.  
3. Land precommit so zero-`dodgeWindow` envelope still separates.  
4. Promote summoner CD from boolean to timed input and wire loadouts.

Orchestrator should apply §§2–3 in a later edit of `xh.ts` / `combat.ts` / eval, re-run `npm run eval:xh` (or `npx --yes tsx scripts/eval-xh-math.ts`), keep only if `math_pass_rate` does not drop below 41/41 before new asserts, then ≥ all new F–J checks.
