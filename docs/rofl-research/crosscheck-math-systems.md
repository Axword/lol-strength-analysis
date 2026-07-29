# Math systems for kill-window calibration (arXiv notes)

Research pointers only. Not a product change. Anti-overfit still applies.

## Do we agree to continue?
Yes. Burst gate showed real progress (early MAE down) and a sharp remaining failure mode (lethal lost). That is a reason to go further, not stop — with **holdout + dual-track** still required before `combat.ts`.

Your check 02 burst JSON in one sentence:
- Baseline already in a real fight (4 skills, 665 HP drop) → not `false_all_in`.
- Gate still helps path MAE (−134 full / −241 early) but **kills lethal** (`killedInModel: false`).
- Naive ≡ re-pin (`deltaRepinVsNaive = 0`) because engage ≈ burst start.

So the next math problem is not “find engage” on idle windows. It is **action-aligned damage** inside an already-engaged burst.

---

## Systems that map onto our pipeline

### 1) Marked temporal point processes (casts → HP jumps)
**Idea:** Treat `skill_used` (+ AA proxies) as a marked point process; HP is a jump process driven by those marks, not a continuous all-in clock.

| Piece | Maps to |
|-------|---------|
| event times | `skill_used.game_time_ms` |
| marks | slot, caster pid, maybe range/hit |
| state | victim HP (and optional shield) |

**arXiv / proceedings**
- Differentiable change-point detection with TPPs / Transformer Hawkes: [Koley et al., AISTATS 2023](https://proceedings.mlr.press/v206/koley23a.html) (DCPD + THP)
- Marked TPPs + continuous state: [Decoupled MTPP + Neural ODEs](https://arxiv.org/abs/2406.06149); [S2P2 state-space point processes (NeurIPS 2025)](https://proceedings.neurips.cc/paper_files/paper/2025/file/ee39348acc798915d2d15a8bbbd417b8-Paper-Conference.pdf)
- Classical intensity models: Neural Hawkes (Mei & Eisner); Transformer Hawkes (Zuo et al.)

**Why it fits burst check 02:** Baseline fights from t=0; reality has 4 casts at specific times. A mark-driven simulator only applies damage when a cast mark fires → keeps lethal if marks include the finishing combo.

**Next experiment (~1–2 h):** `action_aligned` dry-run — between casts, HP holds (regen optional); on each killer `skill_used`, apply one kit line (or `simulateMatchup` for Δt=cast window). Score MAE + lethal vs gate.

---

### 2) Change-point / CUSUM engage detection (idle → fight)
**Idea:** Engage is a distributional change in (HP slope, cast rate), not only “first skill.”

**arXiv**
- [Li et al., Automatic CPD via deep learning](https://arxiv.org/abs/2211.03860)
- Score-based CPD for spatio-temporal point processes: [arXiv:2602.04798](https://arxiv.org/abs/2602.04798) (when + where)

**Why it fits full check 02:** First-skill engage at 17.7s worked; CPD on HP derivative + cast intensity would generalize when first skill is a poke, not the all-in.

**Next experiment:** CUSUM on 1 Hz `ΔHP` and cast counts; compare engage time vs first-skill; re-run gate.

---

### 3) Piecewise / switched dynamical systems (phases)
**Idea:** Explicit modes — `idle | trade | disengage | finish` — each with its own damage rate. Switching times from CPD or skills.

Classic continuous analogue: **Lanchester attrition** (HP′ = −α·enemy strength). Game AI uses this for RTS armies ([Stanescu et al., StarCraft Lanchester](https://cdn.aaai.org/ojs/12780/12780-52-16297-1-2-20201228.pdf); [Laryushin, IEEE ToG 2023](https://doi.org/10.1109/tg.2022.3149275)). Useful bit for us: piecewise attrition rates between cast marks — not fitting α on one Syndra kill.

**Why it fits dual tracks:** Early false_all_in = wrong mode (trade while idle). Burst lethal loss = wrong mode duration (gated clock too short / missing finish marks).

---

### 4) State-space filtering (optional later)
Kalman / IMM: treat model HP as prediction, live-stats HP as observation; estimate a latent “damage efficiency” per phase.  
Useful for **diagnostics** (where bias accumulates). Dangerous as a fit target on one game (overfit). Keep holdout.

Military tracking papers exist; LoL-specific HP filters do not — borrow the structure, not the domain claims.

---

### 5) LoL papers (context, not the kill-window math)
These optimize **match win / player skill**, not 1v1 HP trajectories:
- [SIDO performance model](https://arxiv.org/abs/2403.04873) — Bayesian gold/damage with team context
- [Action2Score](https://arxiv.org/pdf/2207.10297) — embed actions → win contribution
- [Real-time result prediction](https://arxiv.org/abs/2309.02449) — LightGBM on macro features

Useful later for assists / teamfight (check 03). **Not** the next lever for burst lethal.

---

## Ranked next moves (do now → later)

| Priority | Move | Time | Ship risk |
|----------|------|------|-----------|
| 1 | **Action-aligned sim** (marks = `skill_used`) on burst 01–03 | ~1–2 h | Low (research overlay) |
| 2 | CPD/CUSUM engage vs first-skill on full windows | ~1 h | Low |
| 3 | Multi-fighter attribution (damage share) for check 03 | half day | Medium (needs assist/proxy) |
| 4 | Latent efficiency filter across many kills | days | High overfitting if tuned on 2970110 only |

**Recommended now:** action-aligned burst overlay. Same anti-overfit bar as gate (`shipGate` stays false until lethal ±2s + transfer + holdout).

---

## Anti-overfit reminder
- Math that fits one Syndra→Camille burst is still not calibrated.
- Prefer structures that use **observed casts** (identifiable) over free damage multipliers.
- Holdout game before any `combat.ts` change.
