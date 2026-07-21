# Pass-1 STRATEGY — dodge / dash-CD / strategic bands

**Axis:** strategy (σ_juke, ready-state conditioning, worst/typical/best bands)  
**Status:** `KEEP_CANDIDATE`  
**Constraint honored:** critique + snippets only; **do not edit** `src/engine/xh.ts` in this pass.  
**Eval:** `math_pass_rate=1.0000` (20/20) at time of write — proposals must not weaken existing checks.

---

## 1. Critique (concrete failure modes)

### 1.1 Smoking gun: `bands.worst === bands.typical` always

In `estimateXh`, juke budgets are:

```ts
sigmaJukeTypical = jukeSigma({ useDash: true, useFlash: flashReady })
sigmaJukeWorst   = jukeSigma({ useDash: true, useFlash: true }) // comment: “assume Flash up”
sigmaJukeBest    = jukeSigma({ useDash: false, useFlash: false })
```

But inside `jukeSigma`:

```ts
if (opts.useFlash && flashReady) dash += 400 * …
```

So the worst-case path still gates Flash on **observed** `flashReady`. Therefore:

| `flashReady` | typical Flash | worst Flash | result |
|---|---|---|---|
| `true` | yes | yes | worst ≡ typical |
| `false` | no | no | worst ≡ typical |

**Empirical check** (near mid, mutual, Akali, dash+flash ready):  
`bands = { worst: 0.413, typical: 0.413, best: 0.663 }` — only `best` separates.  
Same pattern at far/slow and far/fast. The existing eval only checks `best ≥ typical ≥ worst`, which holds with equality.

**Intent vs code:** comment says strategic envelope (“assume Flash up”); implementation does not. Worst band is dead weight.

### 1.2 Hard cliff when `dodgeWindow ≤ 0.02` collapses all three bands

```ts
const dodgeWindow = Math.max(0, tGo - tau)
if (cc || dodgeWindow <= 0.02) return ms * dodgeWindow * 0.15  // identical for all opts
```

Probes:

| scenario | t_go | τ | dodgeWindow | bands identical? |
|---|---:|---:|---:|---|
| point-blank fast (free or CC) | 0.07 | 0.22 | 0 | yes |
| near ambush full budget | 0.37 | 0.38 | 0 | yes (σ_juke=0) |
| near mutual depleted | 0.37 | 0.22 | 0.15 | yes (no dash/flash → best=typ=worst) |

Ambush with full kit should **not** look like an unreactable point-blank for band width: defender had cast telegraph + TOF; only post-missile reaction is ≤0.

Root cause: dodge window is **missile-TOF-only**. Aim already uses a separate windup `T_avail≈0.42`, but defender reaction does not share that clock. That is inconsistent with LoL telegraph/windup (and with bang-bang evasion timing against delayed estimators — see cites).

### 1.3 Mobility tags — partially correct, one leak

**Good (keep):** `dashBudgetFromMobility` is distance budget (uu), not a hit mult. Depleted Akali ≡ Lux under eval (`|ΔxH|<0.08`).

**Leak:** default `dashReady` is inferred from kit class (`!== immobile && !== boots`). That is fine as a **prior when CD unknown**, but bands/typical should document:

- `dashReady === undefined` → kit-prior ready  
- `dashReady === false` → budget 0 in **typical**; kit ceiling only in **worst envelope**  
- never multiply BASE×mobility

Also: when `dashReady=true`, kit budget still differs (Galio 425 vs Akali 900). That is correct *if* ready — not a tag×prior resurrection.

### 1.4 CC path zeroes discrete dodge correctly, but bands stay flat

CC → early return in `jukeSigma` ignores dash/Flash. Physically right for hard CC. Bands should still allow optional **strafe residual** only; forcing `worst=typical=best` is OK under CC **if** documented. Prefer invariant: under CC, `worst ≈ typical ≈ best` within ε.

### 1.5 What “strategic bands” should mean (attacker POV)

Align with file comment: *(dodge depleted / typical / full budget)*:

| band | meaning | σ_juke |
|---|---|---|
| **best** | defender depleted / no discrete dodge | strafe only |
| **typical** | condition on **observed** `dashReady` / `flashReady` | observed budgets |
| **worst** | strategic envelope: kit dash ceiling + Flash **assumed available** (CD unknown / future fight) | max plausible |

Equality only when envelope ≡ observed ≡ depleted (true point-blank with no pre-commit, or CC).

---

## 2. Proposed minimal patch (snippets for Pass-2 applier)

Do **not** reintroduce `BASE_XH × ZONE × VISION`. Keep corridor + σ factorization.

### 2.1 Explicit budgets + soft gate (fixes worst≡typical)

```ts
/** Soft ramp: 0 at w=0, ~1 by wRef. Avoids hard cliff at 0.02. */
function dodgeScale(w: number, wRef = 0.35): number {
  if (!(w > 0)) return 0
  return Math.min(1, w / wRef)
}

function jukeFromBudget(
  dodgeWindow: number,
  ms: number,
  dashUu: number,
  flashUu: number,
  cc: boolean,
): number {
  if (cc) return ms * Math.max(0, dodgeWindow) * 0.15
  const w = Math.max(0, dodgeWindow)
  const strafe = ms * w * 0.45
  const s = dodgeScale(w)
  // Discrete displacement ~ bang-bang terminal set (bounded lateral impulse)
  const discrete = Math.hypot(dashUu * s * 0.35, flashUu * s * 0.35)
  return Math.hypot(strafe * 0.55, discrete)
}
```

### 2.2 Windup-aware dodge window (fixes ambush band collapse)

```ts
// Share aim windup clock with defender reaction (telegraph), not TOF alone.
const T_windup = 0.28 // cast/line-up visible before missile spawn
const tau = reactionSec(vision)
const dodgeWindow = Math.max(0, T_windup + tGo - tau)
```

Expected: near ambush (`tGo≈0.37`, `τ=0.38`) → `dodgeWindow≈0.27` → Flash/dash envelope can separate bands.

### 2.3 Ready-state conditioning + strategic envelope

```ts
const kitDash = dashBudgetFromMobility(targetMobility)
// Prior only when unspecified; explicit false must zero typical dash.
const dashReadyObs =
  input.dashReady ??
  (targetMobility !== 'immobile' && targetMobility !== 'boots')
const flashReadyObs = input.flashReady === true

const dashTyp = dashReadyObs ? kitDash : 0
const flashTyp = flashReadyObs ? 400 : 0

// best: depleted
const sigmaJukeBest = jukeFromBudget(dodgeWindow, ms, 0, 0, cc)
// typical: observed CD state
const sigmaJukeTypical = jukeFromBudget(dodgeWindow, ms, dashTyp, flashTyp, cc)
// worst: envelope — kit dash ceiling + Flash (ignore observed Flash CD)
const sigmaJukeWorst = jukeFromBudget(
  dodgeWindow,
  ms,
  Math.max(dashTyp, kitDash), // kit potential
  400,                        // Flash envelope (comment intent)
  cc,
)
```

**Preserve eval “kit tag alone…”:** typical still uses `dashTyp=0` when `dashReady:false`, so Akali≡Lux on `xH`. Worst may diverge by kit ceiling — that is the point of bands, not of point estimate.

### 2.4 Optional: tiny pre-commit residual when `tGo < τ` but windup existed

If Pass-2 wants separation at true point-blank with Flash “up” in envelope only:

```ts
// After computing sigma* ; if dodgeWindow==0 && !cc && kitDash+400 envelope:
// allow ε lateral from buffered input (anticipation), capped small vs R_hit
const precommit = (!cc && T_windup > tau * 0.5) ? 40 : 0 // uu SD floor for envelope only
// add only into sigmaJukeWorst via Math.hypot(..., precommit)
```

Keep floor small so point-blank CC stays `xH>0.85`.

---

## 3. New invariants (propose **additions** to `eval-xh-math.ts` — do not soften old ones)

```ts
// A. Worst must use Flash envelope even when flashReady=false
const env = estimateXh(base({
  targetChampionId: 'Akali',
  dashReady: true,
  flashReady: false,
  missileSpeed: 1000, // ensure dodgeWindow > 0 under windup fix
}))
assert(
  'bands: worst < typical when dash ready, flash CD (envelope)',
  !!env.bands && env.bands.worst + 1e-6 < env.bands.typical,
  JSON.stringify(env.bands),
)

// B. Typical conditions on ready; depleted typical ≡ best
const dep = estimateXh(base({
  targetChampionId: 'Akali',
  dashReady: false,
  flashReady: false,
  missileSpeed: 1000,
}))
assert(
  'bands: depleted ⇒ typical ≈ best',
  !!dep.bands && Math.abs(dep.bands.typical - dep.bands.best) < 0.02,
  JSON.stringify(dep.bands),
)
assert(
  'bands: depleted still allows worst < typical via Flash envelope',
  !!dep.bands && dep.bands.worst + 1e-6 < dep.bands.typical,
  JSON.stringify(dep.bands),
)

// C. Ambush with budget must not flatten all bands (windup-aware window)
const amb = estimateXh(base({
  vision: 'ambush',
  targetChampionId: 'Akali',
  dashReady: true,
  flashReady: true,
  targetPosition: near,
  missileSpeed: 1200,
}))
assert(
  'ambush+budget: band spread (best−worst) > 0.02',
  !!amb.bands && amb.bands.best - amb.bands.worst > 0.02,
  JSON.stringify(amb.bands),
)

// D. CC ⇒ flat bands (no discrete dodge)
const ccBands = estimateXh(base({
  targetChampionId: 'Akali',
  dashReady: true,
  flashReady: true,
  crowdControlled: true,
  missileSpeed: 1000,
}))
assert(
  'CC ⇒ bands within 0.01',
  !!ccBands.bands &&
    ccBands.bands.best - ccBands.bands.worst < 0.01,
  JSON.stringify(ccBands.bands),
)

// E. Ready false: kit tag must not move typical (existing spirit, explicit)
const luxT = estimateXh(base({ targetChampionId: 'Lux', dashReady: false }))
const akaT = estimateXh(base({ targetChampionId: 'Akali', dashReady: false, flashReady: false }))
assert('typical ignores kit when dashes down', Math.abs(luxT.xH - akaT.xH) < 0.08)
```

Expected score impact: +4–5 new checks; old 20 must stay green. If windup constant too large, re-check `faster missile → higher xH` and `ambush ≥ mutual` (ambush τ longer → more dodge → lower or equal xH; current check is ambush ≥ mutual×0.98 which is **hit** inequality — longer τ should *raise* xH by cutting dodge; windup adds the same constant to both, so ordering preserved).

---

## 4. arXiv / theory cites (strategy axis)

| id / ref | use in model |
|---|---|
| [arXiv:2511.21633](https://arxiv.org/abs/2511.21633) Bang-Bang Evasion (Mudrik & Oshman) | Discrete bounded lateral impulses dominate random strafe; justifies dash/Flash as bang-bang budget, not continuous MS×t only. Stochastic optimality of bang-bang → envelope bands over maneuver set. |
| [arXiv:2603.05363](https://arxiv.org/abs/2603.05363) Estimation delays in stochastic guidance | Abrupt maneuvers create an uncertainty interval after switch; timing vs delay = reaction/TOF structure. Motivates separating **telegraph/windup** clock from pure missile TOF. |
| [arXiv:1804.05021](https://arxiv.org/abs/1804.05021) FITTS trajectory variability | Endpoint variance grows with amplitude/time pressure — keep σ_aim Schmidt/Fitts; strategy must not steal aim into mobility mult. |
| [arXiv:2410.02966](https://arxiv.org/abs/2410.02966) Fitts + signal-dependent motor noise | Supports additive noise factorization; dodge is extra process noise / control impulse, not a multiplicative prior. |
| [arXiv:2604.17811](https://arxiv.org/abs/2604.17811) Kill-probability vs miss-distance | Soft lethality / SSKP over miss PDF ↔ our `corridorHitProb(R, μ, σ)`; bands = SSKP under alternate defender maneuver hypotheses. |
| Classic cookie-cutter / firing theory (Washburn notes; DTIC ADA022936) | P(hit)=P(\|M\|<R) under Gaussian miss — already in code; bands vary σ_juke only. |

**Do not** import PN/homing guidance as if skillshots steer (program hard rule). Evasion cites are for **defender** discrete maneuvers vs ballistic cookie-cutter, not missile guidance.

---

## 5. Expected invariant gains

| failure | after patch |
|---|---|
| worst ≡ typical always | worst < typical whenever Flash envelope > observed Flash |
| ambush near → flat bands | windup+tGo−τ > 0 → spread spread |
| dodgeWindow≤0.02 hard zero | soft scale + windup; true zero only if T_windup+tGo≤τ |
| kit tag bleed into typical | unchanged when `dashReady:false` |
| CC | remains high xH; bands flat |

Regression watch: `dash+flash ready lowers xH vs depleted` (typical), `CC raises xH`, `kit tag alone…`, `faster missile → higher xH`.

---

## 6. Decision

**`KEEP_CANDIDATE`**

Rationale: one real logic bug (worst Flash envelope never applied), one structural clock bug (TOF-only dodge → ambush/point-blank band collapse), and a clean ready-state / kit-budget split that deepens strategy **without** resurrecting mobility×zone priors or weakening eval. Pass-2 should apply §§2–3, re-run `npx --yes tsx scripts/eval-xh-math.ts`, keep only if `math_pass_rate` does not drop.
