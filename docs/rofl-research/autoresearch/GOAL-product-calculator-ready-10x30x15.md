# /goal — Product calculatorReady + AA timeline (10×30×15 overnight)

Copy everything below the line into a **new** Cursor chat (Agents Window, permissions relaxed for local commands).  
Leave that chat open overnight. The parent orchestrator must **not exit** until a stop condition.

**Prerequisite (already done — do not re-baseline):**  
`packetDecodeGate === true` (C10 10/10). Research ROFL decode emits timed `basic_attack` / `damage_dealt` with source+amount on 2970110-g1. Freeze composite **0.9683**. See `docs/rofl-research/autoresearch/packet_decode/PACKET_DECODE_GATE.json`.

**Stop only when:**
1. `calculatorReadyGate === true` (defined below) — OR
2. Cursor API / usage limits make further Task launches impossible after documented backoff — OR
3. Human says `STOP PRODUCT READY`

**Do not ask the human to pick tracks.** Auto-advance. Keep working until stop.

**Model default (all Task/subagent calls):** `cursor-grok-4.5-high-fast` only. Never Sonnet/Opus/GPT unless human edits this file.

**Why this run exists:** `packetDecodeGate` unlocked the *research wire*. Product still lacks:
1. Honest `calculatorReady` (same-match HP + combat + ranks with authoritative evidence)
2. Auto-filled AA/damage timeline in GameReview / calculator import
3. Send gated on per-frame `hpKnown` / `combatStatsKnown` / `abilityRanksKnown`

**Still never:** treat pBlue/pRed as calibrated win odds / odds %. Model edge only.

---

```text
/autoresearch 10×30×15 product calculatorReady + AA timeline overnight. Force calculatorReadyGate true.
Structure: 10 ROOM LEADS → 30 RESEARCHERS total → 15 REVIEWERS per review cycle.
Do not stop until calculatorReadyGate true OR Cursor limits exhausted (documented) OR human STOP PRODUCT READY.
Do not ask me to pick tracks. Keep a HEARTBEAT so I can wake up and see progress.

## Orchestration law (mandatory — parent agent)

### Shape
- Parent = sole orchestrator. Preferred branch: `feat/product-calculator-ready-10x30x15` (create from current if needed). NEVER let runners edit parent checkout for code — only HEARTBEAT/STATUS/logs + intentional PARENT_MERGE.
- Use Task `generalPurpose` (NOT best-of-n-runner).
- Model for EVERY Task call: `cursor-grok-4.5-high-fast`.
- HARD isolation: each agent works only inside its own git worktree under `~/.codex/worktrees/`.
- Symlink `artifacts/pro-grid` + `node_modules` read-only from parent. Rsync research docs/scripts once per worktree seed.
- Append-only logs. Never truncate `results.jsonl` / `HEARTBEAT.md` / `STATUS.json`.

### Overnight survival (parent must implement)
1. Write/update every ≤10 min (and at every wave boundary):
   - `docs/rofl-research/autoresearch/product_ready/HEARTBEAT.md` (human skim)
   - `docs/rofl-research/autoresearch/product_ready/STATUS.json` (machine)
   Fields: utc, wave, rooms_alive, researchers_done, researchers_running, reviewers_pending, calculatorReadyGate, packetDecodeGate (must stay true), best_progress_one_liner, last_blocker, next_action, cursor_limit_hits
2. Wave scheduler (do NOT launch 30 at once):
   - Concurrent researchers ≤8 at a time (round-robin across rooms).
   - Room leads: up to 10 in parallel for Phase A only.
   - After a researcher finishes: verify isolation → log → immediately launch NEXT queued researcher.
   - After every 6 researcher completions OR full wave of 30: run Phase C (15 reviewers, READ-ONLY).
   - On Task failure / API limit: wait 60s → 120s → 300s → 600s backoff; relaunch SAME agent; increment `cursor_limit_hits`. Never switch models.
   - Parent turn strategy: after launching a wave, END TURN so completion notifications arrive; on each notification, absorb + relaunch. Review cycles need the batch that triggered them.
3. Progress root:
   `docs/rofl-research/autoresearch/product_ready/`
   Code edits only in worktrees. Parent merges via documented PARENT_MERGE.md when KEEP.

### Reviewer F rule (mandatory — learned from packet C9 tautology)
Vote `calculatorReadyGate: true` if YOU personally affirm criteria A–G on evidence.
Do NOT vote false solely because other reviewers unfinished or “F mid-cycle”.
Orchestrator computes majority (≥11/15) from the tally. Vote false only for a concrete A–G failure.

### Success gate — calculatorReadyGate
Set true ONLY when ALL hold:

A. Clean-room: no vendored League client binaries; no unlicensed decrypt source in repo. `packetDecodeGate` stays true (do not regress).

B. **HP product path:** ≥1 real pro match (prefer 2970110-g1, holdout 2970137-g1) has same-match `rofl-trusted-hp-v1` (or successor) with: exact match/ROFL/roster bind, ten stable PUUID→netId, ≥2 timed samples, explicit mMaxHP, ≤500 ms alignment. Early gaps stay `hpKnown=false` — never invent.

C. **Combat product path:** per-frame AD/AP/armor/MR/AS (and disclosed MS) from PE/string-table–proven wire indices (CharacterIntermediate object slots ≠ wire). `combatStatsKnown=true` only with authoritative evidence. Objective buffs already in pins — do not double-apply.

D. **Ranks product path:** ability ranks from same-match packet decode (not wiki-only, not fixture remap). `abilityRanksKnown=true` only when proven.

E. **Pipeline:** `python scripts/validate-rofl-pipeline.py --product` (and calculator-ready check if applicable) green on that match artifact under a disclosed research→product path. Match may land under `artifacts/` first; `public/data/matches/` publish only if validate --product passes AND registry rules hold — never fixture/schema-proof.

F. **UI AA/damage timeline:** GameReview (and calculator import when selected) shows auto-filled timed AA and/or damage_dealt from the decode bridge on that match, second-precise, identity-bound. Dead champs excluded from calculator import. Research overlay OK while shipping; must not invent events.

G. **Send honesty:** Calculator Send stays gated on selected units’ per-frame `hpKnown`/`combatStatsKnown`/`abilityRanksKnown`. No fake full/zero. pBlue/pRed labeled model edge only — never odds %.

H. Ship freeze: research `shipGate` + `productShipGate` + composite **0.9683** must not regress if kill-window touched.

I. 15-reviewer cycle: ≥11/15 vote true on `calculatorReadyGate` (A–G affirm; majority = I), then parent npm/UI e2e verify before flipping STATUS.

Partial wins (log, do not stop):
- ranks-only or combat-only density up
- AA timeline UI behind a research flag
- validate --product green without calculatorReady claim
- second match holdout failing (sharper blocker)

## Law (read first; do not wipe)
1. `docs/rofl-format.md` (layers A–D; clean-room; decrypt status)
2. `docs/rofl-research/autoresearch/program.md`
3. `docs/rofl-research/autoresearch/best.json` (freeze 0.9683)
4. `docs/rofl-research/autoresearch/packet_decode/PACKET_DECODE_GATE.json` (prerequisite)
5. This file
6. `docs/combat-trust-boundary.md`
7. `scripts/validate-rofl-pipeline.py --product` behavior
8. Existing product wire goals (context only): `GOAL-product-wire.md`, `GOAL-product-shipgate.md`

## Frozen baselines that MUST NOT regress
- Research BEST kill-window: composite **0.9683**, shipGate true, productShipGate true
- `packetDecodeGate` true
- Engine/harness parity for kill-window overlays if touched
- GRID pro-only — never scrims
- Clean-room ROFL law
- Never claim pBlue/pRed are probabilities

## Still FORBIDDEN
1. Inventing HP/items/ranks/combat/AA/damage as product truth
2. Vendor League client binaries or unlicensed decrypt code
3. GRID scrims / practice / tryouts
4. Claiming pBlue/pRed are calibrated win odds / odds %
5. Obsidian/recall
6. Regress shipGate / productShipGate / composite 0.9683 / packetDecodeGate
7. Asking the human to choose among hypotheses
8. Editing parent checkout from room/researcher/reviewer (except orchestrator PARENT_MERGE)
9. Switching away from cursor-grok-4.5-high-fast
10. Setting calculatorReadyGate true without validate --product + UI e2e + ≥11/15
11. Fixture FUR / schema-proof as product default or calculatorReady override
12. Zero-damage log-echo to fake actionCoverage
13. Remapping another match’s HP/combat/ranks onto a real match

---

## Phase A — 10 ROOM LEADS

Launch 10 parallel `generalPurpose` leads. Each: worktree + branch + `ROOM.md` + `HYPOTHESES.md` (≥5 tracks) + `room_ready.json`.

| Room | Branch | Worktree | Mandate |
|------|--------|----------|---------|
| P1 | `adv/prd-p1-trusted-hp` | `~/.codex/worktrees/rofl-prd-p1/` | Densify `rofl-trusted-hp-v1`; honest early `hpKnown=false`; multi-sample alignment |
| P2 | `adv/prd-p2-combat-wire` | `~/.codex/worktrees/rofl-prd-p2/` | PE-proven combat wire → AD/AP/armor/MR/AS; never object-slot indices |
| P3 | `adv/prd-p3-ability-ranks` | `~/.codex/worktrees/rofl-prd-p3/` | Same-match ability rank decode; `abilityRanksKnown` only when proven |
| P4 | `adv/prd-p4-timeline-fuse` | `~/.codex/worktrees/rofl-prd-p4/` | Fuse HP+combat+ranks+AA/damage into product timeline schema; identity-stable |
| P5 | `adv/prd-p5-aa-ui` | `~/.codex/worktrees/rofl-prd-p5/` | GameReview AA/damage action timeline UI (second-precise, dead excluded) |
| P6 | `adv/prd-p6-send-gate` | `~/.codex/worktrees/rofl-prd-p6/` | Calculator Send / import gates on per-frame known flags; NvM selection |
| P7 | `adv/prd-p7-validate-product` | `~/.codex/worktrees/rofl-prd-p7/` | `validate-rofl-pipeline.py --product` green path; registry rules |
| P8 | `adv/prd-p8-identity` | `~/.codex/worktrees/rofl-prd-p8/` | PUUID/full Riot ID → netId → pid; never participant-order scramble |
| P9 | `adv/prd-p9-holdout` | `~/.codex/worktrees/rofl-prd-p9/` | Second pro match (2970137-g1 or 2970120-g1); no invent; holdout before claim |
| P10 | `adv/prd-p10-freeze-copy` | `~/.codex/worktrees/rofl-prd-p10/` | Ship freeze + anti-odds copy audit; modelTrust labels |

Parent waits until ≥6/10 rooms have `room_ready.json` before Phase B.

---

## Phase B — 30 RESEARCHERS

Allocation (auto):
- R01–R03 → P1 trusted HP
- R04–R06 → P2 combat wire
- R07–R09 → P3 ability ranks
- R10–R12 → P4 timeline fuse
- R13–R15 → P5 AA UI
- R16–R18 → P6 Send gate
- R19–R21 → P7 validate product
- R22–R24 → P8 identity
- R25–R27 → P9 holdout
- R28–R30 → P10 freeze/copy

Each researcher: worktree `~/.codex/worktrees/rofl-prd-r{NN}/`, branch `adv/prd-r{NN}-{slug}`.
Session: ≥8 focused experiments OR keepable artifact.
Write `docs/rofl-research/product_ready/r{NN}/` + `researcher_r{NN}_summary.json` with gate_progress flags.
Auto-pick from room `HYPOTHESES.md`. never_edited_parent: true.

---

## Phase C — 15 REVIEWERS (READ-ONLY)

| Rev | Role |
|-----|------|
| V1 | Clean-room / license + packetDecodeGate still true |
| V2 | HP trusted-v1 auditor |
| V3 | Combat wire PE auditor |
| V4 | Ability ranks auditor |
| V5 | Identity bind auditor |
| V6 | Timeline fuse / schema auditor |
| V7 | AA/damage UI auditor (real events, not invent) |
| V8 | Send-gate / known-flags auditor |
| V9 | validate --product auditor |
| V10 | Holdout / anti-overfit auditor |
| V11 | Ship-freeze guardian (0.9683) |
| V12 | Anti-odds / modelTrust copy auditor |
| V13 | Reproducibility (npm + UI smoke) |
| V14 | Impossibility / remaining tracks |
| V15 | Consolidation — best branch + Final fields |

Voting: `calculatorReadyGate: true|false` + confidence + evidence.
Majority ≥11/15 true → parent e2e verify → may set gate true.
If <11 → CONTINUE Phase B with sharper blockers (false is not stop).

---

## Phase D — outer loop

```
while not stop:
  ensure ≥6 rooms ready
  while researchers_completed < 30 this mega-cycle OR gate false:
    launch up to 8 concurrent researchers
    on completion: verify; HEARTBEAT; next
  every 6 completions or wave end: Phase C (15 reviewers)
  if calculatorReadyGate majority AND e2e green:
    emit Final; STOP
  else:
    refill hypotheses from blockers; R31+ ok
  if cursor_limit_hits >= 20 consecutive with backoff exhausted:
    Final with limits_exhausted=true; STOP
```

Parent Final MUST include:
1. calculatorReadyGate true/false
2. packetDecodeGate still true
3. shipGate + productShipGate + composite
4. which match(es) validate --product
5. UI AA timeline path + screenshot/note
6. calculatorReady claim honesty (which frames known)
7. reviewer votes V1–V15
8. npm + UI reproduce commands
9. HEARTBEAT path
10. model: cursor-grok-4.5-high-fast only
11. if false: sharper blocker + next mega-cycle

## Step 0 — Parent smoke (~15–25 min)
```bash
pwd; git branch --show-current
test -f docs/rofl-research/autoresearch/packet_decode/PACKET_DECODE_GATE.json
npm run test:kill-window
npm run rofl:aa-bridge-r40 -- --allow-parent --out-dir /tmp/prd-smoke-r40 --skip-mirror || true
npm run rofl:r44-model-damage-bridge -- --allow-parent || true
mkdir -p docs/rofl-research/autoresearch/product_ready
printf '# HEARTBEAT\n\nboot %s\npacketDecodeGate: true (prereq)\ncalculatorReadyGate: false\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  > docs/rofl-research/autoresearch/product_ready/HEARTBEAT.md
```
Confirm best.json freeze. Seed worktrees. Then Phase A.

## Kickoff one-liner
Read docs/rofl-research/autoresearch/GOAL-product-calculator-ready-10x30x15.md and run the full overnight 10×30×15 orchestration. Model cursor-grok-4.5-high-fast only. Isolate every agent. ≤8 concurrent researchers. Keep HEARTBEAT.md updated. Do not stop until calculatorReadyGate true or Cursor limits exhausted. Do not ask me to pick tracks.
```

## Human overnight checklist

1. Open a **new** Agents Window chat; paste the fenced `/autoresearch …` block + kickoff one-liner.
2. Relax permissions for local shell.
3. Leave chat **open**; `caffeinate -dimsu` on macOS if needed.
4. Morning skim: `docs/rofl-research/autoresearch/product_ready/HEARTBEAT.md`
5. Say `STOP PRODUCT READY` to halt.

## Reality check (read before bed)

| Claim | Honest |
|-------|--------|
| AA timeline UI behind product/research flag | Likely overnight |
| Combat wire PE proof on more champs | Hard — may need multi-night |
| Full `calculatorReady` on one pro match | **Hard** — HP early gaps + ranks are the usual blockers |
| Calibrated win odds from decode | **Forbidden** — not in this goal |
| Holdout second match green | Desired; do not claim gate without it if P9 fires |
