# Pass-10 STRATEGY (FINAL) — bands↔packet fidelity closed

**Axis:** strategy (σ_juke ready-state + dodge bands → CombatResult / packet fidelity)  
**Status:** `SKIP`  
**Constraint:** critique only; **do not edit** production files in this pass.  
**Eval at write:** `math_pass_rate=225/225 (1.0000)` post Pass-9 KEEP. Prefer bands↔packet fidelity over new mobility×P(hit) tags; no `BASE×ZONE×VISION`.

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
| 9 | Packet-emission cast multiset (skillshot damage lines × casts + packet-presence skip); `lockedOut` reactive single-cast into `fightDodgeBands` / `skillshotCastsForFight` |

Eval strategy probes through Pass-9 (cast-set short/unranked R, OOR retention, Flash-up mix≡typical, Flash-unknown mix≠typical under empty util, multi-line Lee Q weight, lockedOut engage drop) are green. σ_juke ready-state and bands↔packet emission parity are **closed**.

---

## 1. Critique (Pass-10 — residual hunt)

### 1.1 Smoking gun from Pass-9: closed in production

Pass-9 KEEP is live in `combat.ts`:

```ts
// skillshotCastsForFight — packet-faithful multiset
const hits = ability.damage(stats, stats, ctx).filter((p) => p.skillshot)
if (!hits.length) return
for (let c = 0; c < castCopies; c++) {
  for (let h = 0; h < hits.length; h++) {
    out.push({ slot: ability.slot, range: ability.range, ability })
  }
}
// lockedOut → pushAbility(ability, 1) + engageCc skip
```

```ts
// simulateMatchup
fightDodgeBands(..., sideLocked('blue', input))
```

Probe (post Pass-9, 225/225): `|activeBandCell − blue.avgXh| = 0` for Lux 1v1, Lux+Ahri NvM, Lux+LeeSin multi-hit Q, soft-lock Lux vs Malphite short, and Flash-unknown under the same util the sim applies. Multi-line kits in corpus (LeeSin Q, Naafiri Q, Gnar Q/E) expand correctly (Lee Q → 2 lines × casts).

**No production deepen remains on bands↔packet weight / soft-lock.**

### 1.2 Apparent Flash-unknown flatten is util, not fidelity

`simulateMatchup` → Lux Q `hardCc` collapses dodge envelope so `mix≡typical≡worst` and policy `'typical'`. Same `outgoingUtility` into packets and bands — both paths agree. Empty-util `fightDodgeBands` still shows mix≠typical for Flash-CD-unknown (Pass-8 lock). Do **not** “fix” CC-collapsed mix by retagging mobility.

### 1.3 Cosmetic / harness-only leftovers (not KEEP)

| Item | Why SKIP for FINAL |
|------|-------------------|
| Double `fightDodgeBands` in `simulateMatchup` (band + policy) | Pure dedupe; no score / product drift |
| `fightPacketXhMean` export | Optional; ε=0 already holds without it |
| Eval AN (cell≈avgXh), AM (real OOR inside `fightDodgeBands`), AO (combat-row missile), Pass-7 AC–AF | Harness debt only — Pass-9 landed AK/AL; product already matches. Sealing asserts is orchestrator hygiene, not a strategy KEEP patch |
| Red→blue second dodge row | Explicitly out of scope since Pass-7 |
| Damage-gold-weighted avgXh | Product contract is equal skillshot-packet average |

### 1.4 σ_juke ready-state: SKIP (unchanged)

Flash envelope, precommit, NE mix, Ghost×slow raw liveMs, charges, CC-break, `effectiveTargetMs`, utilMult dual-channel are green through Pass-9. Further ready-state work would be Hexflash / second envelopes / **mobility×P(hit) tags** — forbidden on FINAL and unnecessary for bands↔packet.

### 1.5 Out of scope (do not chase)

- New MobilityClass / zone / vision multiplicative tags  
- Rewriting Flash envelope, precommit, π priors, charges, CC-break, `neMixCorridorVal`, `jukeFromBudget`, Ghost predicate  
- Hexflash second envelope  
- Geo/aim/vision formula changes  
- Re-proposing Pass-8/9 cast multiset / OOR / policy / packet-emission / lockedOut  
- BASE×ZONE×VISION  
- PN / homing guidance  

---

## 2. Minimal patch

**None.** Orchestrator should not apply a strategy production patch on Pass-10.

If harness hygiene is desired outside KEEP scoring, optional eval-only seals (do not soften 225):

```ts
// AN — lock Pass-9 empirical parity (LeeSin or Lux, expected, Flash-up)
assert('|activeCell − blue.avgXh| < 1e-9', …)

// Finish Pass-7 AC–AF if still `void fightDodgeBands`
```

These are **not** a STRATEGY KEEP_CANDIDATE — no `combat.ts` / `xh.ts` change required.

---

## 3. New invariants

**None required for KEEP.** Rate stays 225/225 with no strategy patch.

---

## 4. arXiv / theory cites (closure)

| id / ref | use |
|----------|-----|
| [arXiv:2604.17811](https://arxiv.org/abs/2604.17811) Kill-prob vs miss | Displayed SSKP bands already average the same hit hypotheses as Expected packet xH (Pass-9 emission + lock) |
| [arXiv:2511.21633](https://arxiv.org/abs/2511.21633) Bang-Bang Evasion | σ_juke hypotheses on packets match dodge row — no further reweight or mobility retag |
| Classic cookie-cutter / Washburn | UI % still \(P(\|M\|<R)\) under σ; no PN / BASE×ZONE×VISION |

---

## 5. Expected gains vs regressions

| gap | Pass-10 action |
|-----|----------------|
| Multi-hit / soft-lock / packet-presence drift | **Closed** (Pass-9) — no further patch |
| Active cell vs Avg xH | **ε=0** empirically — optional eval seal only |
| New mobility×P(hit) | **Reject** |
| Ready-state deepen | **Reject** |

**Regressions avoided by SKIP:** touching landed Pass-1–9 KEEP; inventing FINAL tags that cannot improve bands↔packet.

---

## 6. Decision

**`SKIP`**

Rationale: Pass-9 closed the last strategy product residual (packet-emission cast multiset + `lockedOut` in `fightDodgeBands`). Post-landing probes show active dodge cell ≡ `blue.avgXh` across 1v1, NvM, multi-hit, and soft-lock. Remaining items are cosmetic dedupe or eval harness debt — not bands↔packet bugs. Prefer fidelity over tags: with fidelity done, **do not** add mobility×P(hit) tags or reopen σ_juke ready-state on FINAL.

1. No strategy production patch.  
2. Optional eval AN/AC–AF seals only if orchestrator wants free locks — not KEEP.  
3. Hard rules: no `BASE×ZONE×VISION`; no new mobility×hit tags.

**Verdict: SKIP — bands↔packet fidelity closed at Pass-9; FINAL strategy axis idle.**
