# Pass-10 GEO — FINAL residual audit

**Axis:** geometry / kinematics (deepen Pass-9 residual only)  
**Verdict:** `SKIP`  
**Do not edit `src/engine/xh.ts` in this pass.** No snippets / no new eval asserts.

Eval baseline at proposal time: **225/225** (`npm run eval:xh`). Do **not** re-propose Pass-1…9 KEEP work (`interceptTimeGo`, lead/heading, `interceptInMissileRange`, width/speed, `propagateLosFrame`, `ballisticRayMiss`/`ballisticSegmentMiss`/`ballisticSegmentCpa`, cast∧reach, `releaseDelaySec`, capsule `R_hit` / tip CPA, accel ZEM, `missileMaxTravelUu`, LOS collapse, `engagementHorizonSec`, lead/μ on `t_eng`, reach vs `Ltravel`, CPA-epoch accel clock, delay+`t_cpa`, `capsuleTravelBudgetUu`, `firstContactTimeGo` / center `t_go` for dodge/reach, `ballisticFirstContactSec`, muSeen/hyp contact parity) unless fixing a clear regression.

No BASE×ZONE×VISION. No PN / mid-flight steering. Do **not** set `T_avail = t_go`.

---

## 1) Critique of Pass-9 residual geometry

Pass-9 closed the last named open-loop **finite-extent clock** gaps:

| Landed (Pass-9) | Role |
|-----------------|------|
| `ballisticFirstContactSec` | Accel-ZEM epoch = earliest `|p(t)|=R_hit` along aim ray ≤ center `t_cpa` |
| muSeen / hyp arms | Pass-8 `firstContactTimeGo` → `t_eng` + Pass-9 `t_hit` parity with main |

Post–Pass-9 kinematics stack (intentional split preserved):

| Clock / pad | Source | Consumer |
|-------------|--------|----------|
| center `t_go` / `tGoMis` | `interceptTimeGo` | dodge lifetime, Weber, reach path length |
| triangle `t_contact` | `firstContactTimeGo` | lead / segment CPA horizon (`t_eng`) |
| tip pad `L_eff` | `capsuleTravelBudgetUu` | `engagementHorizonSec`, segment clamp, reach pad |
| center CPA `t_cpa`, `missUu` | `ballisticSegmentCpa` | corridor μ (1D), factors |
| ballistic `t_hit` | `ballisticFirstContactSec` | accel-ZEM only |

Residuals examined for a FINAL deepen — all **thin or out of GEO deepen scope**:

1. **Full 2D stadium / circular kill CDF (deferred since Pass-3/4).**  
   Replacing `corridorHitProb` with a bivariate miss integral would change the σ-corridor factorization itself, not deepen a kinematics clock. Explicitly deferred every geo pass (“do not replace the 1D corridor”). High ordinal risk at 225/225; not a minimal residual patch.

2. **Triangle `t_eng` vs ballistic `|r+vt|=R_hit` for lead.**  
   Pass-9 hard-deferred: do **not** re-open triangle vs general quadratic for `t_eng`. Accel already uses the ballistic contact root; lead planning stays collision-triangle contact. Unifying them is a redesign, not a thin deepen.

3. **μ clamp / contact-miss substitution when `missUu < R_hit`.**  
   CPA `missUu` is already the right open-loop geometric miss for the 1D corridor (penetrating ⇒ smaller μ ⇒ higher Φ). Swapping μ for 0 or `R_hit` at contact would distort hit mass without new physics.

4. **Lethal dwell / exit root (`t_exit − t_hit`).**  
   Exit time has no consumer in μ, reach, dodge, or accel (post-contact accel correctly ignored). Shipping an unused clock is dead code, not a deepen.

5. **Reach / dodge onto contact clocks.**  
   Pass-7/8/9 intentionally keep reach + dodge/Weber on **center** `t_go` (+ `R_hit` pad). Moving them onto `t_contact` / `t_hit` would regress those KEEP contracts.

6. **Zero-extent / A=0 equivalence already holds.**  
   `R_hit → 0` ⇒ `t_hit ≡ t_cpa`, `t_contact ≡ t_go`. `A → 0` ⇒ `zemExtra = 0` on all arms. No parity hole left analogous to Pass-9’s muSeen gap.

**Conclusion:** there is no remaining **kinematics-clock** residual that is (a) concrete, (b) additive, and (c) allowed under Pass-8/9 hard deferrals. The only named leftover is the 2D corridor integral — out of scope for a FINAL residual deepen.

Do **not** set engagement `t_eng = t_go` center. Do **not** feed contact into reach/dodge. Do **not** add PN.

---

## 2) Exact TypeScript snippets

**N/A — SKIP.** No production patch. Do not apply helpers or `estimateXh` wiring in this pass.

---

## 3) New invariant check(s)

**N/A — SKIP.** Do not append Pass-10 GEO asserts. Leave Pass-4…9 geometry checks untouched.

---

## 4) Mental regression vs existing 225/225

| Check family | Risk if we forced a KEEP | Why SKIP is safer |
|--------------|--------------------------|-------------------|
| corridor\* / xHm / empirics | **high** if 2D CDF | would rewrite hit mass |
| Pass-8 `t_contact` / `t_eng` | medium if unified with ballistic | Pass-9 forbade reopen |
| Pass-9 `t_hit` / accel | none if untouched | already correct |
| reach / dodge center `t_go` | medium if moved to contact | would regress Pass-7…9 |
| A=0 default μ | none | already bit-stable |
| aim / vision / strategy σ | n/a | out of axis |

Forcing a KEEP on thin residue risks eval churn for no closed math gap.

---

## 5) arXiv ids (audit only — no new cite required for SKIP)

| id | Role in stack (already landed) |
|----|--------------------------------|
| [2604.17811](https://arxiv.org/abs/2604.17811) | Miss → hit with finite extent (`R_hit` clocks + corridor) |
| [2511.21633](https://arxiv.org/abs/2511.21633) | ZEM at engagement / contact epoch |
| [2312.09562](https://arxiv.org/abs/2312.09562) | Relative quadratic / collision geometry |
| [2403.14997](https://arxiv.org/abs/2403.14997) | Engagement clock chain |

No PN. No 2D corridor integral this pass.

---

## 6) Verdict

**`SKIP`**

Pass-9 closed the last actionable GEO residual (`ballisticFirstContactSec` + muSeen/hyp contact parity). Remaining deferred work is the full 2D stadium CDF (explicitly out of residual-deepen scope) or forbidden reopenings (`t_eng` triangle↔ballistic, contact→reach/dodge). FINAL geo axis: hold the 225/225 kinematics stack; do not invent a thin KEEP.

SKIP
