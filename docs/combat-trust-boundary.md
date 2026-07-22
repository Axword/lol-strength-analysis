# Combat calculator trust boundary

Status: acceptance-tested engine behavior, not calibrated fight probabilities.

`pBlue` / `pRed` on `MatchupResult` are **heuristic ranking scores** used for
who-is-stronger UI and strength bands. They are **not** calibrated win
probabilities, odds, or chances. The Calculator labels them as model edge /
heuristic model score and never renders them with a `%` as win probability.

## Model confidence contract

`simulateMatchup` attaches a serializable `modelTrust` object
(`src/engine/modelTrust.ts`):

| Field | Meaning |
|-------|---------|
| `calibrated` | Always `false` today |
| `class` | `manual_kit_1v1` or `experimental` |
| `badge` | `Manual kits · uncalibrated` or `Experimental · uncalibrated` |
| `reasons` | Deterministic, sorted machine-readable codes (no wall-clock) |
| `champions[].tier` | `core` \| `generated` \| `unresolved` |

Classification rules:

- **manual-kit 1v1** — exactly one living fighter per side, and both are CORE
  (`CORE_CHAMPION_IDS` from `champions.ts`). CORE means hand-modeled
  **attention**, not trusted or validated combat.
- **experimental** — any NvM roster, or any living fighter that is generated /
  unresolved (not CORE).

The classifier does **not** claim item, rune, or passive validation. Full
coverage audit remains in `docs/combat-model-coverage.md` /
`scripts/audit-combat-coverage.ts`.

## Resolution contract

- Kills are derived from each concrete target's post-sustain `hpRemaining <= 0`.
- Single-target packets use the first living enemy in input order as the focus target.
- All living attackers stack on that target simultaneously; the model does not retarget after a focus target dies.
- HP meters sum living target HP against the summed max-HP pool for display. Target records retain incoming damage, sustain, mitigation, defensive reduction, and killed state.
- Percent-max-HP packets and Liandry read the focus target's actual `hpMax`; physical and magical mitigation read that target's armor/MR.
- Defensive utility is owner/target-scoped. It is not max-merged over a summed team pool; ally-targeted protection is not simulated.
- Each fighter can cast at most one ultimate in a window. Engage timing is modeled only for short fights up to 4 seconds; longer windows explicitly ignore the engage selector.
- A/B compare is an item-only comparison for Blue fighter 1. Other Blue fighters and the compared fighter's champion/level/HP/runes remain unchanged.

Gnar uses an explicit `form` when supplied. Without one, the compatibility rule is Mega when R is ranked and Mini otherwise; only one form's packets emit.

### Timed manual 1v1 vs aggregate fallback

When **exactly one living CORE fighter per side** and **neither side is
short-window engage-locked**, damage is scheduled with a **bounded beam**
cast/attack planner (`src/engine/rotation.ts`) and resolved chronologically
(`timing.method = timed_manual_1v1`):

- Best-found under fixed beam/expansion limits — **not** globally optimal and
  **not** calibrated.
- Equal impact timestamps are simultaneous; both sides' damage applies before
  deaths; a dead fighter's later actions are suppressed.
- HP regen applies only over elapsed time; omnivamp only from damage actually
  dealt. End-of-window sustain must not resurrect after lethal damage.
- After the first lethal timestamp (either side), resolution stops: no later
  execution, `resolvedSec` / `executedDurationSec` equal `firstLethalSec`
  (requested duration only when nobody dies). Equal-time mutual kills remain.
- Utility-only effects (slows, shred, DR, …) remain **whole-window** in v1.
- Planner candidate scores use target-effective (mitigated) damage; emitted
  packets remain raw.
- The bounded planner may choose a later-ready action (implicit wait for a
  cooldown recast) rather than only expanding the globally earliest filler;
  search remains best-found under beam/expansion caps, not globally optimal.
- Planner candidate scores apply the selected `xhMode` to skillshots before
  mitigation (zero-xH / out-of-range shots do not outrank guaranteed damage);
  `xhMode=off` leaves skillshot raw unchanged for scoring. Emitted packets
  remain raw / xH-scaled as today.
- Item `abilityProcs` (Spellblade / similar) come from the scheduled plan's
  non-AA actions, not the pre-plan aggregate cast estimate.
- Champion duration/aggregate passive packets and duration-based item
  `fightPackets` attach to the **last** scheduled damaging action (approx);
  legacy on-ability/rune procs attach to the first eligible non-AA ability.
- Unannotated ability execution timing uses conservative defaults (0.15s lock /
  0.1s impact) and emits `timing:default_execution_metadata:<champ>:<slots>` —
  not claimed as precise kit timing.

Every other matchup — all NvM cells, any generated/unresolved fighter, and
engage-locked short windows — keeps the prior **aggregate packet-count** path
(`timing.method = aggregate_window`). Aggregate results are not an executable
cast sequence.

`MatchupResult.timing` is optional/backward-safe and JSON-serializable for a
later UI timeline (start/impact seconds, slot/source, cast index, reset flag,
requested vs executed/resolved time, method, deterministic caveats).

`calibrated` remains **false** for every cell.

## Evidence

`npm run test:acceptance` exercises the combat invariants (including the
1..5 × 1..5 NvM matrix) plus model-trust gates: CORE 1v1 → manual-kit,
generated 1v1 → experimental, NvM → experimental, `calibrated: false`, and
deterministic reasons. Timed-manual gates cover Darius AA→W reset sequencing,
determinism, lethal suppression, mutual equal-time kills, and aggregate NvM
fallback.

`npm run eval:xh` passes mathematical xH invariants, including the
duration-aware Ahri cast multiset check.

These checks establish implementation invariants and falsifiability. They do
**not** establish calibrated win probabilities. No NvM cell and no CORE kit is
promoted to calibrated or trusted.
