# /goal — ROFL / packet decode unlock (5×25×10 overnight)

Copy everything below the line into a **new** Cursor chat (Agents Window, permissions relaxed for local commands).  
Leave that chat open overnight. The parent orchestrator must **not exit** until a stop condition.

**Stop only when:**
1. `packetDecodeGate === true` (defined below) — OR
2. Cursor API / usage limits make further Task launches impossible after documented backoff — OR
3. Human says `STOP PACKET DECODE`

**Do not ask the human to pick tracks.** Auto-advance. Keep working until stop.

**Model default (all Task/subagent calls):** `cursor-grok-4.5-high-fast` only. Never Sonnet/Opus/GPT unless human edits this file.

**Why this run exists:** Grid riot livestats has `skill_used` + `summoner_spell_used` (+ fat `item_active_ability_used` currently dropped by slim). It has **no AA / basic-attack / damage-tick events**. Action-replay ≥0.95 is blocked on AA-heavy windows until a **clean-room ROFL/packet decode** (or honest metric-law change) supplies those classes. This run builds the decode path.

---

```text
/autoresearch 5×25×10 ROFL packet-decode overnight. Force packetDecodeGate true.
Structure: 5 arxiv-maths ROOM LEADS → each room scaffolds adversarial tracks for 25 RESEARCHERS total → 10 REVIEWERS per review cycle.
Do not stop until packetDecodeGate true OR Cursor limits exhausted (documented) OR human STOP PACKET DECODE.
Do not ask me to pick tracks. Keep a HEARTBEAT so I can wake up and see progress.

## Orchestration law (mandatory — parent agent)

### Shape
- Parent = sole orchestrator. Parent stays on `feat/grid-riot-livestats-rfc461` (or current feature branch). NEVER let runners edit parent checkout.
- Use Task `generalPurpose` (NOT best-of-n-runner — collides on parent checkout).
- Model for EVERY Task call: `cursor-grok-4.5-high-fast`.
- HARD isolation: each agent works only inside its own git worktree under `~/.codex/worktrees/`.
- Symlink `artifacts/pro-grid` + `node_modules` read-only from parent. Prefer rsync dirty parent research tree once per worktree seed.
- Append-only logs. Never truncate `results.jsonl` / `HEARTBEAT.md` / `STATUS.json`.

### Overnight survival (parent must implement)
1. Write/update every ≤10 min (and at every wave boundary):
   - `docs/rofl-research/autoresearch/packet_decode/HEARTBEAT.md` (human skim)
   - `docs/rofl-research/autoresearch/packet_decode/STATUS.json` (machine)
   Fields: utc, wave, rooms_alive, researchers_done, researchers_running, reviewers_pending, packetDecodeGate, best_progress_one_liner, last_blocker, next_action, cursor_limit_hits
2. Wave scheduler (do NOT launch 25 at once — Cursor will die):
   - Concurrent researchers ≤5 at a time (one per room, or round-robin).
   - Rooms may run in parallel (≤5 room leads).
   - After a researcher finishes: verify isolation → log → immediately launch NEXT queued researcher in that room (or global queue).
   - After each full wave of 25 researcher completions OR every 5 completions: run a REVIEW CYCLE of up to 10 reviewers (see Phase C). Reviewers are READ-ONLY.
   - On Task failure / API limit: wait 60s → 120s → 300s → 600s backoff; relaunch SAME agent id/prompt on same model; increment `cursor_limit_hits`. Never switch models.
   - Parent turn strategy: after launching a wave, END TURN so completion notifications arrive; on each notification, do follow-up (verify + relaunch next) without waiting for all 25 if the queue still has work — EXCEPT review cycles require the wave's researcher batch to finish first.
3. Progress artifacts live under parent path:
   `docs/rofl-research/autoresearch/packet_decode/`
   but CODE edits only in worktrees. Parent may update HEARTBEAT/STATUS/GOAL notes only.

### Success gate — packetDecodeGate
Set true ONLY when ALL hold:
A. Clean-room: no vendored League client binaries; no copy of unlicensed third-party decrypt source into the repo. Protocol facts + in-repo probes only (see docs/rofl-format.md).
B. A research emitter produces **timed basic-attack OR damage OR Replication-derived auto-attack proxies** that are:
   - bound to participant/netId identity on a real local `.rofl` OR maknee-shaped decoded events from OUR decode path (fixture decode alone is not enough for gate true),
   - written as rfc461-compatible research events (new schema name disclosed, e.g. `basic_attack` / `damage_dealt` / proven Replication field stream),
   - reproducible via a documented npm script in the winning worktree.
C. On ≥1 pro kill window from artifacts/pro-grid (prefer 2970110-g1 checks): action-replay audit shows truthActions include the new class with count>0 AND model can emit matching damaging actions (or disclosed skill+AA solvable inventory improves honestly). Do NOT invent events.
D. Fixture FUR / schema-proof paths remain labeled research; `calculatorReady` stays false; no `public/data/matches/` publish.
E. Research `shipGate` + `productShipGate` freeze (composite ≈0.9683) MUST NOT regress if kill-window harness is touched. Prefer packet work that does not edit kill-window defaults.
F. 10-reviewer cycle: ≥7/10 vote true on packetDecodeGate, OR unanimous false with sharper blocker (then continue researching — false vote is NOT a stop).

Partial wins (log, do not stop):
- stream sync / Deserialize binds improved
- Replication combat wire index proof
- item_active_ability_used restored into slim-v3 (parallel unlock; does NOT satisfy AA gate alone)
- AA proxy from HPΔ documented as research-only (NOT gate evidence)

## Law (read first; do not wipe)
1. `docs/rofl-format.md` (layers A–D; clean-room; decrypt status table)
2. `docs/rofl-research/autoresearch/program.md`
3. `docs/rofl-research/autoresearch/best.json` (freeze shipGate/productShipGate/composite 0.9683)
4. This file
5. `docs/rofl-research/autoresearch/GOAL-action-replay-95.md` (why AA class matters)
6. Existing probes: `scripts/rofl2_packet_decrypt_probe.py`, `rofl2_packet_taxonomy.py`, `rofl2_unicorn_packet_drive.py`, `rofl2_replication_decode.py`, `rofl2_replication_timed_hp.py`, `rofl_replication_fields.py`, `maknee_packets_to_jsonl.py`, `rfc461_emit.py`
7. `docs/combat-trust-boundary.md` if present

## Frozen baselines that MUST NOT regress
- Research BEST kill-window: composite **0.9683**, shipGate true, productShipGate true
- Engine/harness parity for kill-window overlays if touched
- GRID pro-only (`scripts/grid_api.py` guards) — never scrims
- calculatorReady false; no public match publish
- Clean-room ROFL law

## Still FORBIDDEN
1. calculatorReady true / publish public/data/matches
2. Invent HP/items/ranks/combat/skill/AA/item-active events as product truth
3. Vendor League client binaries or unlicensed decrypt code
4. GRID scrims / practice / tryouts
5. Claim pBlue/pRed are probabilities
6. Obsidian/recall
7. Regress shipGate or productShipGate
8. Asking the human to choose among hypotheses
9. Editing parent checkout from room/researcher/reviewer
10. Switching away from cursor-grok-4.5-high-fast
11. Claiming packetDecodeGate true without reproducible script + audit JSON + reviewer majority
12. Treating fixture-only schema-proof as real-match decode unlock
13. Using zero-damage log-echo to fake actionCoverage progress

---

## Phase A — 5 ROOM LEADS (arxiv-maths / protocol knowledge)

Launch 5 parallel `generalPurpose` leads. Each creates a ROOM: worktree + branch + `ROOM.md` + hypothesis queue that will feed researchers.

| Room | Branch | Worktree | Mandate (math / protocol lens) |
|------|--------|----------|--------------------------------|
| M1 | `adv/pkt-m1-stream-sync` | `~/.codex/worktrees/rofl-pkt-m1/` | Framing / information theory of chunk→block→packet stream sync; Unicorn factory; type-107 Replication candidate; fix `packet_factory_driven_need_stream_sync` / `packet_deserialize_partial` |
| M2 | `adv/pkt-m2-replication-aa` | `~/.codex/worktrees/rofl-pkt-m2/` | Replication field algebra: mHP/mMaxHP done — hunt AA / on-hit / attack-speed / missile / damage-applied names in 16.14 inventory; prove wire indices (CharacterIntermediate slots ≠ wire) |
| M3 | `adv/pkt-m3-cast-missile` | `~/.codex/worktrees/rofl-pkt-m3/` | CastSpellAns / missile / basic-attack packet taxonomy; map to rfc461 `basic_attack` or disclosed schema; PE/string-table proofs |
| M4 | `adv/pkt-m4-identity-fuse` | `~/.codex/worktrees/rofl-pkt-m4/` | netId↔PUUID↔participant bind; timed samples; fuse decode onto Replay API positions without inventing HP; rofl-trusted-hp-v1 toward attack events |
| M5 | `adv/pkt-m5-bridge-actionreplay` | `~/.codex/worktrees/rofl-pkt-m5/` | Bridge: decoded AA/damage → action_replay truthActions + modelActions; slim-v3 also restore `item_active_ability_used` as parallel class; keep ship gates |

### Room lead deliverables (before spawning researchers)
1. `ROOM.md` — problem statement, invariants, forbidden moves, success tests
2. `HYPOTHESES.md` — ordered queue ≥5 adversarial tracks for that room
3. `arxiv_notes.md` — short notes citing relevant ideas (stream sync, HMM/change-point for keyframe cadence, bipartite matching later, coding/framing). No need for literal arXiv PDF fetch if offline — use known methods; if web available, prefer real citations.
4. Seed smoke: run relevant existing npm scripts; log baseline blockers from docs/rofl-format.md § Field decrypt status
5. Write `room_ready.json` with `{room, ready:true, tracks: [...]}`

Parent waits until ≥3/5 rooms have `room_ready.json` before Phase B (relaunch stuck rooms).

---

## Phase B — 25 RESEARCHERS (adversarial; wave-scheduled)

Total N_researchers = 25 across rooms (default allocation: 5 per room).  
Each researcher: own branch+worktree OR dedicated subdirectory + git branch under its room worktree (prefer `~/.codex/worktrees/rofl-pkt-r{NN}/` with branch `adv/pkt-r{NN}-{slug}`).

### Allocation (auto; do not ask human)
- R01–R05 → M1 stream-sync
- R06–R10 → M2 replication-AA
- R11–R15 → M3 cast/missile
- R16–R20 → M4 identity-fuse
- R21–R25 → M5 action-replay bridge

### Per-researcher law
1. Verify `pwd` + branch before first edit
2. Session target ≥8 focused experiments OR until a keepable decode artifact
3. Append `docs/rofl-research/autoresearch/packet_decode/results.jsonl` lines via copying summary into parent packet_decode log OR write in-worktree results and parent merges into HEARTBEAT (parent consolidates)
4. Auto-pick next hypothesis from room `HYPOTHESES.md` — never ask human
5. On keep: write `artifacts` under worktree `docs/rofl-research/packet_decode/r{NN}/`
6. Final `researcher_r{NN}_summary.json` with: experiments, kept/discarded, blocker, gate_progress {stream_sync, replication_aa, basic_attack_events, identity_bind, action_replay_bridge}, never_edited_parent

### Adversarial angles (samples; rooms may refine)
- Wrong framing offsets; endian; length-prefix vs sentinel
- Type-107 false positive; alternate UsePacket nodes
- Attack fields that are client-only / not replicated
- Missile IDs vs slot IDs; targeted vs skillshot
- Identity scramble traps (participant order ≠ netId)
- Bridge that invents AA from HPΔ (must label research-only; cannot claim gate)
- Slim item_active restore without claiming AA unlock

---

## Phase C — 10 REVIEWERS (per review cycle; READ-ONLY)

After each researcher wave batch (see scheduler), launch 10 reviewers in parallel on `cursor-grok-4.5-high-fast`:

| Rev | Role |
|-----|------|
| V1 | Clean-room / license skeptic — reject vendored decrypt |
| V2 | Stream-sync auditor — does Deserialize actually bind? |
| V3 | Replication wire-index auditor — PE/string-table proof? |
| V4 | AA/basic-attack event auditor — real events or invented? |
| V5 | Identity-bind auditor — PUUID/netId stable? |
| V6 | Action-replay metric auditor — F1 honesty; reject ghosts |
| V7 | Ship-gate guardian — composite/shipGate/productShipGate intact? |
| V8 | Reproducibility — npm script + inputs → same outputs? |
| V9 | Impossibility / remaining-track judge |
| V10 | Consolidation judge — best branch; fill Final fields draft |

### Reviewer voting
- Each returns `packetDecodeGate: true|false` + confidence + evidence paths
- Majority ≥7/10 true → parent may set gate true AFTER verify script
- If <7 true → parent merges sharper blockers into HEARTBEAT and **continues Phase B** (new wave of researchers on remaining tracks). Review false is not stop.
- Tie on secondary issues (which branch) must not block; gate bit is primary.

---

## Phase D — outer loop (overnight)

```
while not stop:
  ensure rooms ready (relaunch dead room leads)
  while researchers_completed < 25 in this mega-cycle OR gate false:
    launch up to 5 concurrent researchers from queue
    on completion: verify isolation; update HEARTBEAT; enqueue next
  run Phase C (10 reviewers)
  if packetDecodeGate true by majority AND verify scripts green:
    emit Final message; STOP
  else:
    refill hypothesis queues from reviewer blockers
    start next mega-cycle (R26+ numbering ok; keep summaries)
  if cursor_limit_hits >= 20 consecutive failures with backoff exhausted:
    emit Final message with limits_exhausted=true; STOP
```

Parent Final message (each stop) MUST include:
1. packetDecodeGate true/false
2. shipGate + productShipGate + composite (must stay green)
3. calculatorReady false; no publish
4. clean-room confirmation
5. best progress artifact paths + npm commands to reproduce
6. which action classes unlocked (AA / item_active / damage / none)
7. reviewer votes V1–V10
8. rooms + researchers completed counts
9. HEARTBEAT path + last utc
10. model confirmation: cursor-grok-4.5-high-fast only
11. if false: sharper blocker + next mega-cycle plan (unless limits_exhausted)

## Step 0 — Parent smoke (~10–20 min) before any launch
```bash
pwd; git branch --show-current
npm run test:crosscheck-sqrt
npm run test:kill-window
# Packet/decrypt probes that exist locally (skip if ROFL path missing; document):
npm run rofl:decrypt-probe -- --backend fixture \
  --fixture-events docs/rofl-research/fixtures/decrypt_hp_acceptance.json \
  --require-acceptance --json-out /tmp/decrypt_probe_smoke.json || true
mkdir -p docs/rofl-research/autoresearch/packet_decode
echo "# HEARTBEAT\n\nboot $(date -u +%Y-%m-%dT%H:%M:%SZ)" > docs/rofl-research/autoresearch/packet_decode/HEARTBEAT.md
```
Confirm ship freeze still true in best.json. Seed worktrees. Then Phase A.

## Parallel cheap win (M5 may schedule early)
Restore `item_active_ability_used` into slim allowlist (fat rfc461 already has it). This unlocks item-actives for action-replay but **does not** set packetDecodeGate. Log as `itemActiveSlimV3` progress separately.

## Kickoff one-liner
Read docs/rofl-research/autoresearch/GOAL-rofl-packet-decode-5x25x10.md and run the full overnight 5×25×10 orchestration. Model cursor-grok-4.5-high-fast only. Isolate every agent. Wave-schedule researchers (≤5 concurrent). Keep HEARTBEAT.md updated. Do not stop until packetDecodeGate true or Cursor limits exhausted. Do not ask me to pick tracks.
```

## Human overnight checklist (outside the paste block)

1. Open a **new** Agents Window chat; paste the fenced `/autoresearch …` block + kickoff one-liner.
2. Relax permissions for local shell / network if probes need them.
3. Leave that chat **open**; do not close the laptop lid without preventing sleep (`caffeinate -dimsu` on macOS).
4. Morning skim: `docs/rofl-research/autoresearch/packet_decode/HEARTBEAT.md`
5. Say `STOP PACKET DECODE` in that chat to halt.

## Reality check (read before bed)

| Claim | Honest |
|-------|--------|
| Item-actives via slim-v3 | Likely overnight |
| Stream sync / Deserialize progress | Likely overnight |
| Full clean-room AA event unlock on live ROFL | **Hard** — may take multiple nights; this run maximizes parallel attack surface |
| actionReplayGate 0.95 | Only after AA class exists OR metric law changes (out of scope unless M5 proves bridge) |
