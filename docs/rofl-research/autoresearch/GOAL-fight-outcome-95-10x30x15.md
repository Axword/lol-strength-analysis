# /goal — Calculator ≈ VOD fight @ ~95% (10×30×15 overnight)

Copy everything below the line into a **new** Cursor chat (Agents Window, permissions relaxed for local commands).  
Leave that chat open for multi-hour / overnight work. The parent orchestrator must **not exit** until a stop condition.

**What just finished (context — do not re-litigate):**  
`calculatorReadyGate === true` on **2970132-g1** under Path1 hold-forward + `living_post_seed_v1` (Cycle6 15/15 + parent e2e). That gate means honest Send pins (HP/combat/ranks), **not** fight prediction. See `docs/rofl-research/autoresearch/product_ready/reviews/cycle6/CYCLE6_FINAL.json`.

**This run’s human promise (plain language):**  
Import a pro fight into the calculator (without watching the VOD first), run the combat model, then check the actual kill window — model outcome should match reality at **~95%** under the metric below. Also: **unfreeze** research composite **0.9683**, and make **ROFL → JSONL digest** a clean, reproducible product path.

**Stop only when:**
1. `fightOutcomeGate === true` (defined below) — OR
2. Cursor API / usage limits make further Task launches impossible after documented backoff — OR
3. Human says `STOP FIGHT OUTCOME`

**Do not ask the human to pick tracks.** Auto-advance. Keep working until stop.

**Model default (all Task/subagent calls):** `cursor-grok-4.5-high-fast` only. Never Sonnet/Opus/GPT unless human edits this file.

**Still never:** claim pBlue/pRed as calibrated win odds / odds %. Model edge only. `fightOutcomeGate` is **not** a bookmaker probability.

---

```text
/autoresearch 10×30×15 fight-outcome ~95% overnight. Force fightOutcomeGate true.
Also: UNFREEZE research composite 0.9683 (may improve/replace under new metric law).
Also: cleaner ROFL→JSONL digest (single honest path, validate --product green, disclosed sources).
Structure: 10 ROOM LEADS → 30 RESEARCHERS total → 15 REVIEWERS per review cycle.
Do not stop until fightOutcomeGate true OR Cursor limits exhausted (documented) OR human STOP FIGHT OUTCOME.
Do not ask me to pick tracks. Keep a HEARTBEAT so I can wake up and see progress.

## Orchestration law (mandatory — parent agent)

### Shape
- Parent = sole orchestrator. Preferred branch: `feat/fight-outcome-95-10x30x15` (create from current if needed). NEVER let runners edit parent checkout for code — only HEARTBEAT/STATUS/logs + intentional PARENT_MERGE.
- Use Task `generalPurpose` (NOT best-of-n-runner).
- Model for EVERY Task call: `cursor-grok-4.5-high-fast`.
- HARD isolation: each agent works only inside its own git worktree under `~/.codex/worktrees/`.
- Symlink `artifacts/pro-grid` + `node_modules` (+ `artifacts/rofl` if present) read-only from parent. Rsync research docs/scripts once per worktree seed.
- Append-only logs. Never truncate `results.jsonl` / `HEARTBEAT.md` / `STATUS.json`.

### Overnight survival (parent must implement)
1. Write/update every ≤10 min (and at every wave boundary):
   - `docs/rofl-research/autoresearch/fight_outcome/HEARTBEAT.md` (human skim)
   - `docs/rofl-research/autoresearch/fight_outcome/STATUS.json` (machine)
   Fields: utc, wave, rooms_alive, researchers_done, researchers_running, reviewers_pending, fightOutcomeGate, calculatorReadyGate (must stay true on 2970132 Path1 unless honest regression disclosed), digestCleanGate, unfreeze_0_9683 (true), best_progress_one_liner, last_blocker, next_action, cursor_limit_hits, best_fightAgreement, best_composite_new
2. Wave scheduler (do NOT launch 30 at once):
   - Concurrent researchers ≤8 at a time (round-robin across rooms).
   - Room leads: up to 10 in parallel for Phase A only.
   - After a researcher finishes: verify isolation → log → immediately launch NEXT queued researcher.
   - After every 6 researcher completions OR full wave of 30: run Phase C (15 reviewers, READ-ONLY).
   - On Task failure / API limit: wait 60s → 120s → 300s → 600s backoff; relaunch SAME agent; increment `cursor_limit_hits`. Never switch models.
   - Parent turn strategy: after launching a wave, END TURN so completion notifications arrive; on each notification, absorb + relaunch.
3. Progress root:
   `docs/rofl-research/autoresearch/fight_outcome/`
   Code edits only in worktrees. Parent merges via documented PARENT_MERGE.md when KEEP.

### Reviewer F rule (mandatory)
Vote `fightOutcomeGate: true` if YOU personally affirm criteria A–I on evidence.
Do NOT vote false solely because other reviewers unfinished.
Orchestrator computes majority (≥11/15). Vote false only for a concrete A–I failure.

---

## Success gate — fightOutcomeGate

Set true ONLY when ALL hold:

### A. Honesty / clean-room
- No vendored League client binaries; no unlicensed decrypt source.
- `packetDecodeGate` stays true (do not regress).
- `calculatorReadyGate` Path1 claim on 2970132 remains honest (living_post_seed; no invent). Do not claim strict all-frame or 2970110 ready unless separately proven.
- pBlue/pRed still labeled model edge — never odds %.

### B. Metric law — fightAgreement (the “~95%” this goal earns)

**Plain meaning:** On a fixed suite of real kill windows, the calculator/kill-window model’s predicted fight outcome matches the timeline truth often enough that mean **fightAgreement ≥ 0.95**, with holdout, and no forbidden gaming.

**Per window (check×segment), compute a binary `windowOk` and a continuous `windowScore∈[0,1]`:**

Truth from slim SQLite / product timeline / Path1 final (same match only):
- victim dies in window? (`truthKilled`)
- killer pid / champ
- victim HP trajectory samples (early + full)
- engage time (CUSUM / post-engage product selectors preferred; `near_hp_drop` research-only)

Model from product calculator path / `killWindowOverlay` / timed planner (disclosed which):
- `modelKilled`, `modelLethalSec`, HP path

`windowOk` = ALL of:
1. **Lethal agreement:** if `truthKilled`: `modelKilled` AND `|lethalErrorSec| ≤ 0.75`; if not `truthKilled`: model must not false-kill OR disclose floor with `endHpAbsError ≤ 40`
2. **Early honesty:** `earlyMaeHp ≤ 50` (idle / pre-engage)
3. **Path fidelity:** burst `maeHp ≤ 90`; full `maeHp ≤ 130` (tighten only if already beating)
4. **No invent:** unknown HP/combat/ranks stay unknown; dead units excluded from Send/import
5. **No hard fails** from `program.md` (esp. check03 early >50 vs continuous baseline)

`windowScore` (for mean; report all parts):
```
windowScore =
  0.40 * lethalHit          # 1 if lethal rule ok else 0
+ 0.25 * earlyBand          # 1 if earlyMaeHp≤50 else max(0, 1 - (earlyMaeHp-50)/100)
+ 0.20 * pathBand           # 1 if maeHp under cap else tapered
+ 0.15 * actionCoverageF1   # from GOAL-action-replay-95.md match rules; 0 if unavailable (disclose)
```

**Suite mean:**
```
fightAgreement = mean(windowScore over required windows)
fightPassRate  = mean(windowOk)   # fraction of windows fully ok
```

**Gate threshold (all required):**
- Dev suite S0: `fightAgreement ≥ 0.95` AND `fightPassRate ≥ 0.95`
- Holdout S1: same
- Transfer S2: `fightAgreement ≥ 0.90` AND `fightPassRate ≥ 5/6`, none `< 0.80`
- Every failing window must have an audit JSON under `docs/rofl-research/autoresearch/fight_outcome/audits/`

**Confidence wording (mandatory):**
“~95%” here means **fightAgreement ≥ 0.95 under this metric** — NOT a calibrated Bayesian posterior, NOT book odds, NOT “95% sure we win the map.”
UI/docs: **“fight outcome agreement ≥95% (kill-window suite)”** — never “95% win probability.”

### C. Unfreeze 0.9683 (authorized for this run)

- Research composite **0.9683** is **NOT frozen**. Agents MAY change mark selection, density, pulses, regen, timed planner scoring, etc., if fightAgreement improves.
- On KEEP that beats old BEST on fightAgreement (and does not invent): update `docs/rofl-research/autoresearch/best.json` with:
  - `unfrozenFromComposite: 0.9683`
  - new `composite` / `fightAgreement` / config
  - `shipGate` / `productShipGate` redefined honestly under new bars OR left false until bars met
- Old 0.9683 remains in git history + `results.jsonl` as baseline; do not delete history.
- Engine↔harness parity still required if overlays touched (`crosscheck_action_aligned` == engine).
- Product default kill-window selectors stay non-drop (`cusum_engage_then_skills` / `post_engage_killer_skills`) unless a KEEP proves better on S0+S1+S2 and reviewers affirm.

### D. Digest clean — digestCleanGate (required co-gate)

`digestCleanGate === true` only when:
1. **One documented command path** ROFL (or paired riot JSONL) → rfc461 JSONL → timeline JSON for a pro match, runnable on macOS, no rematch/rsync footguns.
2. Sources explicit: `hpSource` / `combatSource` / `abilityRanksSource` preserved end-to-end (no strip on merge).
3. Identity: PUUID/full Riot ID → netId → pid; never participant-order scramble.
4. `python scripts/validate-rofl-pipeline.py --product` green on digest output for ≥1 match (2970132 Path1 OK; prefer also a second host).
5. Living policy disclosed (`living_post_seed_v1` vs strict); hold_forward disclosed when used; never invent pre-seed.
6. Smoke doc: `docs/rofl-research/autoresearch/fight_outcome/DIGEST.md` with exact commands + expected hashes/sizes.
7. “Cleaner” means: fewer manual rematch steps, no silent source wipe, deterministic output, clear failure modes.

`fightOutcomeGate` requires `digestCleanGate` true (co-requisite).

### E. Suites (data)

| Suite | Series | Notes |
|-------|--------|-------|
| S0 Dev | Prefer **2970132-g1** Path1 final (calculatorReady host) + also run 2970110-g1 checks if pins allow | Same-match only; no fixture remap |
| S1 Holdout | **2970137-g1** and/or **2970120-g1** | Must not tune on S1; Camille/combat holes → disclose, do not invent |
| S2 Transfer | Unused pro slim under `artifacts/pro-grid/` | ≥1 series |
| Crosschecks | Reuse/adapt `docs/canvases/_data/crosschecks-*.json` | ≥3 checks/game when available |

Primary experiment surfaces:
- `scripts/crosscheck_action_aligned.ts` / kill-window harness
- `src/engine/killWindowOverlay.ts` + timed planner paths used by calculator Send
- Digest scripts: `jsonl_to_timeline.py`, fuse/hold-forward Path1 chain, `validate-rofl-pipeline.py`

### F. Holdout before claim
No `fightOutcomeGate` true on S0 alone. S1 must meet thresholds (or publish impossibility with sharper blocker after exhausting queue — still leave gate false).

### G. UI / calculator path
Prove the **product calculator** path (Send import or shared engine entry), not only a research script:
- Selected units at kill-window playhead → model fight → compare to timeline truth
- Dead excluded; known-flags gate intact
- One npm/tsx smoke command in Final

### H. Anti-overfit / anti-gaming
Forbidden as gate evidence:
- Zero-damage log-echo “actions”
- Fitting one fight’s HP with a single coefficient across early+late when both tracks fire (investigate opener vs finish separately)
- Remapping another match’s pins onto a real match
- Claiming Grid zip alone without digest fuse when Path1 sources required

### I. Review majority + parent e2e
≥11/15 reviewers vote `fightOutcomeGate: true`, then parent re-runs:
1. Digest smoke from DIGEST.md
2. S0+S1 fightAgreement scripts
3. Calculator/Send smoke
Only then flip `STATUS.fightOutcomeGate`.

---

## Law (read first; do not wipe)
1. `docs/rofl-format.md` (layers A–D; clean-room)
2. `docs/rofl-research/autoresearch/program.md` (hard fails; track diagnostics)
3. `docs/rofl-research/autoresearch/best.json` (**unfrozen** this run — see C)
4. `docs/rofl-research/autoresearch/packet_decode/PACKET_DECODE_GATE.json`
5. `docs/rofl-research/autoresearch/product_ready/reviews/cycle6/CYCLE6_FINAL.json` (prior gate)
6. This file
7. `docs/combat-trust-boundary.md`
8. `GOAL-action-replay-95.md` (actionCoverage F1 definition — secondary term only)
9. GRID pro-only rule (`.cursor/rules/grid-api-pro-only.mdc`)

## Still FORBIDDEN
1. Inventing HP/items/ranks/combat/AA/damage as product truth
2. Vendor League client binaries or unlicensed decrypt code
3. GRID scrims / practice / tryouts
4. Claiming pBlue/pRed / fightAgreement as calibrated win odds
5. Obsidian/recall
6. Asking the human to choose among hypotheses
7. Editing parent checkout from room/researcher/reviewer (except orchestrator PARENT_MERGE)
8. Switching away from cursor-grok-4.5-high-fast
9. Setting fightOutcomeGate true without S1 holdout + digestCleanGate + ≥11/15 + parent e2e
10. Fixture FUR / schema-proof as product default
11. Quietly re-freezing 0.9683 to block better fightAgreement KEEPs
12. Treating calculatorReadyGate as fight prediction

## Partial wins (log, do not stop)
- digestCleanGate true alone
- S0 ≥0.95 but S1 short (sharper holdout blocker)
- actionCoverage lift without fightAgreement gate
- New best.json under unfreeze with shipGate still false
- Second-match Path1 densify without outcome gate

---

## Phase A — 10 ROOM LEADS

Launch 10 parallel `generalPurpose` leads. Each: worktree + branch + `ROOM.md` + `HYPOTHESES.md` (≥5 tracks) + `room_ready.json`.

| Room | Branch | Worktree | Mandate |
|------|--------|----------|---------|
| F1 | `adv/fo-f1-digest-clean` | `~/.codex/worktrees/rofl-fo-f1/` | Single ROFL→rfc461→timeline path; preserve sources; DIGEST.md; digestCleanGate |
| F2 | `adv/fo-f2-metric-harness` | `~/.codex/worktrees/rofl-fo-f2/` | Implement fightAgreement scorer + audits; wire S0/S1/S2 |
| F3 | `adv/fo-f3-unfreeze-kw` | `~/.codex/worktrees/rofl-fo-f3/` | Unfreeze 0.9683; kill-window / mark / density / regen experiments vs fightAgreement |
| F4 | `adv/fo-f4-timed-planner` | `~/.codex/worktrees/rofl-fo-f4/` | Timed cast/AA planner ↔ real kill windows; death-coupled; no HP% ability bans |
| F5 | `adv/fo-f5-action-coverage` | `~/.codex/worktrees/rofl-fo-f5/` | Honest actionCoverage F1 (no zero-dmg echo); secondary term |
| F6 | `adv/fo-f6-calc-path` | `~/.codex/worktrees/rofl-fo-f6/` | Product calculator Send → same math as harness; parity proof |
| F7 | `adv/fo-f7-holdout` | `~/.codex/worktrees/rofl-fo-f7/` | 2970137 / 2970120 / unused pro; no invent; Camille holes disclosed |
| F8 | `adv/fo-f8-path1-extend` | `~/.codex/worktrees/rofl-fo-f8/` | Extend Path1 living densify to holdout hosts if PE seeds exist; never invent |
| F9 | `adv/fo-f9-vod-align` | `~/.codex/worktrees/rofl-fo-f9/` | Align suite windows to actual fight times; optional VOD/notes only as labels — truth remains timeline/SQLite |
| F10 | `adv/fo-f10-anti-odds` | `~/.codex/worktrees/rofl-fo-f10/` | Copy/UI: fightAgreement ≠ odds; modelTrust calibrated:false; freeze-history disclosure |

Parent waits until ≥6/10 rooms have `room_ready.json` before Phase B.

---

## Phase B — 30 RESEARCHERS

Allocation (auto):
- R01–R03 → F1 digest clean
- R04–R06 → F2 metric harness
- R07–R09 → F3 unfreeze kill-window
- R10–R12 → F4 timed planner
- R13–R15 → F5 action coverage
- R16–R18 → F6 calculator path parity
- R19–R21 → F7 holdout
- R22–R24 → F8 Path1 extend
- R25–R27 → F9 VOD/window align
- R28–R30 → F10 anti-odds / disclosure

Each researcher: worktree `~/.codex/worktrees/rofl-fo-r{NN}/`, branch `adv/fo-r{NN}-{slug}`.
Session: ≥8 focused experiments OR keepable artifact.
Write under `docs/rofl-research/autoresearch/fight_outcome/r{NN}/` + `researcher_r{NN}_summary.json`.
Auto-pick from room `HYPOTHESES.md`. never_edited_parent: true.

Hypothesis priority (auto-pick; do not ask human):
1. Digest source-preservation / single-command path
2. fightAgreement harness green on S0 baseline (measure first)
3. Unfreeze experiments that lift lethalHit + earlyBand without invent
4. Holdout densify only with PE evidence
5. Calculator↔harness parity
6. Action coverage honesty
7. Impossibility sharpeners when blocked

---

## Phase C — 15 REVIEWERS (READ-ONLY)

| Rev | Role |
|-----|------|
| V1 | Clean-room + packetDecodeGate + calculatorReady honesty |
| V2 | digestCleanGate auditor (DIGEST.md reproduce) |
| V3 | fightAgreement metric honesty (no gaming) |
| V4 | Unfreeze auditor (0.9683 history preserved; new BEST justified) |
| V5 | S0 suite auditor |
| V6 | S1 holdout auditor |
| V7 | S2 transfer auditor |
| V8 | Calculator↔harness parity |
| V9 | Timed planner / death-coupled honesty |
| V10 | ActionCoverage secondary (reject zero-dmg echo) |
| V11 | Path1 / known-flags / no invent |
| V12 | Anti-odds / wording (“agreement” ≠ win %) |
| V13 | Reproducibility (digest + suite commands) |
| V14 | Impossibility / remaining tracks |
| V15 | Consolidation — best branch + Final fields |

Voting: `fightOutcomeGate: true|false` + `digestCleanGate` affirm + confidence + evidence.
Majority ≥11/15 true → parent e2e → may set STATUS gate true.
If <11 → CONTINUE Phase B (false is not stop).

---

## Phase D — outer loop

```
while not stop:
  ensure ≥6 rooms ready
  while researchers_completed < 30 this mega-cycle OR fightOutcomeGate false:
    launch up to 8 concurrent researchers
    on completion: verify; HEARTBEAT; next
  every 6 completions or wave end: Phase C (15 reviewers)
  if fightOutcomeGate majority AND digestCleanGate AND e2e green:
    emit Final; STOP
  else:
    refill hypotheses from blockers; R31+ ok
  if cursor_limit_hits >= 20 consecutive with backoff exhausted:
    Final with limits_exhausted=true; STOP
```

Parent Final MUST include:
1. fightOutcomeGate true/false
2. digestCleanGate true/false
3. fightAgreement + fightPassRate for S0/S1/S2
4. unfreeze: old 0.9683 → new best (or still baseline)
5. calculatorReadyGate still honest on 2970132
6. DIGEST.md reproduce commands
7. calculator/Send smoke path
8. reviewer votes V1–V15
9. HEARTBEAT path
10. model: cursor-grok-4.5-high-fast only
11. if false: sharper blocker + next mega-cycle

## Step 0 — Parent smoke (~20–30 min)
```bash
pwd; git branch --show-current
test -f docs/rofl-research/autoresearch/product_ready/reviews/cycle6/CYCLE6_FINAL.json
python3 -c "import json;print(json.load(open('docs/rofl-research/autoresearch/best.json')) )" | head
python3 scripts/validate-rofl-pipeline.py --product \
  --jsonl artifacts/rofl/2970132/events.g1.path1-final.rfc461.jsonl \
  --timeline artifacts/rofl/2970132/timeline.g1.path1-final.json \
  --calculator-ready-policy living_post_seed_v1 \
  --require-calculator-ready
npm run test:kill-window || true
mkdir -p docs/rofl-research/autoresearch/fight_outcome/audits
printf '# HEARTBEAT\n\nboot %s\nfightOutcomeGate: false\ndigestCleanGate: false\nunfreeze_0_9683: true\ncalculatorReadyGate: true (prereq Path1 2970132)\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  > docs/rofl-research/autoresearch/fight_outcome/HEARTBEAT.md
```
Confirm 0.9683 is marked unfrozen in STATUS. Seed worktrees. Then Phase A.

## Kickoff one-liner
Read docs/rofl-research/autoresearch/GOAL-fight-outcome-95-10x30x15.md and run the full overnight 10×30×15 orchestration. Model cursor-grok-4.5-high-fast only. Isolate every agent. ≤8 concurrent researchers. Unfreeze 0.9683. Force fightOutcomeGate + digestCleanGate. Keep HEARTBEAT.md updated. Do not stop until fightOutcomeGate true or Cursor limits exhausted. Do not ask me to pick tracks.
```

## Human overnight checklist

1. Open a **new** Agents Window chat; paste the fenced `/autoresearch …` block + kickoff one-liner.
2. Relax permissions for local shell.
3. Leave chat **open**; `caffeinate -dimsu` on macOS if needed.
4. Morning skim: `docs/rofl-research/autoresearch/fight_outcome/HEARTBEAT.md`
5. Say `STOP FIGHT OUTCOME` to halt.

## Reality check (read before bed)

| Claim | Honest |
|-------|--------|
| fightAgreement ≥0.95 on S0 (2970132) | Hard — lethal+HP bars are strict |
| Same on holdout (2970137/2970120) | **Harder** — PE/combat holes remain |
| Cleaner ROFL→JSONL digest | Likely overnight if scoped to source-preserve + one command |
| Unfreeze beats 0.9683 on new metric | Possible; may trade old composite |
| Calibrated win odds / book 95% | **Forbidden** — not this goal |
| calculatorReadyGate already true ⇒ fights match | **False** — prior gate was pins only |
