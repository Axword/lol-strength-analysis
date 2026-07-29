# ROFL → JSONL speed research program

Autoresearch-style notebook for cutting ROFL → rfc461 JSONL wall time.
One mutable subject per run, fixed wall budget, hard quality gates, keep or discard.

## Protocol

1. State one hypothesis and one change (diff label).
2. Run under a **fixed 60 s wall budget** on a bounded window (default: first 60 output frames, or an equivalent 60-frame slice such as minutes 5–6).
3. Measure primary metric `msPerOutputFrame = wallMs / statsUpdateCount`.
4. Secondary: `wallSecondsPerMatchMinute = wallSeconds / (matchDurationMs / 60000)`.
5. Apply quality gates. Fail closed on malformed/incomplete artifacts.
6. Append one JSON object to [`speed-runs.jsonl`](speed-runs.jsonl). Keep only if gates pass inside budget; otherwise discard.
7. Never claim a live Replay API rerun unless the run actually executed the guarded capture path.

### Quality gates

- Exactly 10 identity-stable participants per `stats_update` (PUUID or full Riot ID in `game_info`, IDs `1..10` stable across frames).
- Zero `fountain_placeholder` rows.
- Monotonic timestamps on the requested on-grid cadence (default 1000 ms).
- No HP / combat / ability-rank fabrication (unknown / omitted / `unavailable_*` sources allowed).
- Optional oracle-position comparison when an oracle JSONL is supplied.

### Fixed budget convention

Default experiment budget: **60 seconds** wall clock.
Bounded window: enough work to emit a comparable slice (typically **60 frames** at 1 Hz), not a full-match live capture.

Harness:

```bash
npm run rofl:speed-bench -- --eval-jsonl artifacts/rofl/3264361042/events.rfc461.jsonl \
  --wall-ms 2641475.556 --match-code 3264361042 --match-duration-ms 1625998 \
  --hypothesis "historical checkpoint baseline" --diff-label "baseline" --dry-run

# Bounded Replay API window (guarded path; requires open matching replay)
npm run rofl:speed-bench -- --replay-api \
  --rofl "$HOME/Documents/League of Legends/Replays/BR1-3264361042.rofl" \
  --out-jsonl /tmp/speed-window.jsonl \
  --start-ms 60000 --end-ms 119000 --step-ms 1000 \
  --budget-seconds 60 --match-code 3264361042 \
  --hypothesis "..." --diff-label "..."
```

## Measured product baseline (3264361042)

Source: historical capture checkpoint / validation artifacts under `artifacts/rofl/3264361042/`
(not a live rerun). Label in the run log: `source=historical_checkpoint`.

| Quantity | Value |
|---|---|
| Frames (`stats_update`) | **1566** at 1 Hz from t=60s |
| Mean frame (`averageFrameMs`) | **1686.766 ms** |
| Implied wall | 1566 × 1686.766 ms = **2,641,475.556 ms ≈ 44.0 min** |
| Match duration | **1,625,998 ms ≈ 27.10 match-minutes** |
| `wallSecondsPerMatchMinute` | 2641.476 s / 27.100 min ≈ **97.47 s / match-minute** |
| Validation | `validation.json`: ok, 0 fountain placeholders, cadence 1000 ms, `hpCoverage=none` |

## Target math (N = 1566)

| Goal | Total wall | Required `msPerOutputFrame` | Speedup vs 1686.766 ms |
|---|---|---|---|
| 1-minute drop-and-load | **60 s** | 60000 / 1566 ≈ **38.3 ms** | ≈ **44×** |
| Stretch 100× | **26.4 s** | 26400 / 1566 ≈ **16.9 ms** | **100×** |

Replay API full-match capture remains the honest position oracle / backup.
Offline ROFL packet → Waypoint / replication → rfc461 is the only path that can honestly hit these ceilings while preserving native 1 Hz identity-bound positions.

## Keep / discard rules

- **Keep** only when: command completes inside the fixed budget, quality gates pass, and (for speed claims) metrics are recorded from real wall time + emitted `stats_update` count.
- **Discard** on: budget timeout, command failure, gate failure, malformed JSONL, missing output, or fabricated HP/combat/ranks.
- Timing breakdowns (seek / focus / liveclient / select / emit) are diagnostic only — never correctness assertions.
- On budget timeout with a durable partial JSONL, the harness may still score complete lines (`partial=true`, `completedExpectedSchedule=false`) for diagnostics; keep is always **discard**.

## Phase A results (Replay API micro-opts)

Evidence in [`speed-runs.jsonl`](speed-runs.jsonl). Stage bottleneck from instrumented partial `speed-f2aeb003b550`: selection ≈ **1557 ms/frame** (≈66% of ~2351 ms internal total); seek/focus/liveclient/emit are secondary.

| Run | Window | Strategy | ms/frame | Oracle | Keep |
|---|---|---|---|---|---|
| exp-a5 | 20f @ 700–719s | full + default settle | **2073.258** | 200 cmp, med/max 0 | keep |
| exp-a6 | same 20f | compact + `--final-settle 0` | **941.406** | 200 cmp, med/max 0 | keep |
| **matched speedup** | | | **2.202×** (2073.258 / 941.406) | | |
| exp-a3 | 60f @ 600–659s | compact + zero settle | **864.223** (51.853 s) | 600 cmp, med 0 / max 4.117 | keep |
| exp-a1 | 30f other window | compact only | 1794 (internal stage total 2350.9→1745.8 ≈1.35× same-session) | none | keep; **not** same-window vs a5/a6 |
| exp-a4 | matched 60f full+zero | full + zero settle | timed out (~53 frames) | — | **discard** |
| f2aeb003b550 | 60f instrumented | full baseline | budget exceeded (partial) | — | **discard** |

**Conclusion:** best honest Replay API rate still projects **~22–25 min/full match** at 1566 frames (864–941 ms/frame), nowhere near the 60 s / ~38 ms target. Track 1 promotes **compact + zero final-settle** to the product capture default (still cannot hit 60 s alone). Phase B offline packet digest remains the only path to ~44×/100×.

## Experimental: compact cached selection

**Not a product default.** Capture still defaults to full detach → select → attach (3 render POSTs + 1 GET per participant).

Opt-in after the first frame has populated the selection-key cache:

```bash
# Direct capture CLI
npm run rofl:replay-jsonl -- \
  --rofl "$HOME/Documents/League of Legends/Replays/BR1-3264361042.rofl" \
  --out /tmp/window.jsonl --start-ms 700000 --end-ms 719000 \
  --cached-selection-strategy compact --final-settle 0

# Speed bench forwarding (REMAINDER args after --replay-extra; no extra --)
npm run rofl:speed-bench -- --replay-api \
  --rofl "$HOME/Documents/League of Legends/Replays/BR1-3264361042.rofl" \
  --out-jsonl /tmp/speed-window.jsonl \
  --start-ms 700000 --end-ms 719000 --step-ms 1000 \
  --budget-seconds 60 --match-code 3264361042 \
  --replay-extra --cached-selection-strategy compact --final-settle 0
```

Compact path: one composite render POST (`selectionName` + `cameraAttached=true` + zero `selectionOffset` + `cameraMode=focus`), one settle/GET, then the same `classify_focus_readback` identity+coordinate proof. Any unproven/stale readback immediately falls back to the full 3-POST reassertion for that participant. Never accept unproven coordinates.

## Phase B results (offline 0x025B movement — E0/E1)

Clean-room decoder: [`scripts/rofl2_movement_decode.py`](../../scripts/rofl2_movement_decode.py).
Protocol facts from public 2026 research (movement id `0x025B`, 6-byte schema, per-field ciphers, packed 14-bit X/Z); LUT taken from local League binary `0x231e0d0` (sha256 `328528d6…c04b`, identical to published macos LUT bytes). **No unlicensed source vendored.** Provenance label: `offline_rofl2_025b_research`. Oracle QA assignment is research-only (`research_only_not_product`), never product identity binding.

Evidence: [`speed-runs.jsonl`](speed-runs.jsonl), summary [`movement-025b-BR1-3264361042.json`](movement-025b-BR1-3264361042.json).

### Commands

```bash
# E0 inventory (bounded 60s packet time)
npm run rofl:movement-decode -- \
  "$HOME/Documents/League of Legends/Replays/BR1-3264361042.rofl" \
  --mode inventory --max-time-s 60 --append-speed-run \
  --hypothesis "E0 inventory bounded 60s window" \
  --diff-label "phase-b-e0-inventory-60s" \
  --json-out /tmp/rofl-025b-inventory-60s.json

# E1 decode + maknee point-samples + oracle QA (bounded 60s)
npm run rofl:movement-decode -- \
  "$HOME/Documents/League of Legends/Replays/BR1-3264361042.rofl" \
  --mode full --max-time-s 60 \
  --oracle-jsonl artifacts/rofl/3264361042/events.rfc461.jsonl \
  --append-speed-run \
  --hypothesis "E1 clean-room 0x025B decode bounded 60s" \
  --diff-label "phase-b-e1-025b-60s" \
  --json-out /tmp/rofl-025b-decode-60s.json \
  --events-out /tmp/rofl-025b-events-60s.json

# Full-match inventory + decode
npm run rofl:movement-decode -- \
  "$HOME/Documents/League of Legends/Replays/BR1-3264361042.rofl" \
  --mode inventory --append-speed-run \
  --diff-label "phase-b-e0-inventory-full" \
  --json-out /tmp/rofl-025b-inventory-full.json

npm run rofl:movement-decode -- \
  "$HOME/Documents/League of Legends/Replays/BR1-3264361042.rofl" \
  --mode decode --append-speed-run \
  --diff-label "phase-b-e1-025b-full" \
  --json-out /tmp/rofl-025b-decode-full.json
```

### Measured on BR1-3264361042 (16.14)

| Run | Scope | Wall | Packets | `0x025B` | Decoded | Keep |
|---|---|---|---|---|---|---|
| E0 60s | inventory ≤60s | **3209.537 ms** | 16,093 | **0** | — | **discard** |
| E1 60s | decode ≤60s | **3026.148 ms** | — | 0 | **0** | **discard** |
| E0 full | inventory all | **4052.015 ms** | 1,468,025 | **0** | — | **discard** |
| E1 full | decode all | **2885.051 ms** | — | 0 | **0** | **discard** |

Full-match inventory breakdown: read **4.9 ms**, zstd **57.7 ms**, block walk **3989 ms**. Offline walk alone is already ≪60 s; movement is not present as channel/`packet_id` `0x025B` under `extract_blocks_py` framing.

Top full-match channels (not `0x025B`=603): 53, 491, 246, 632, 532, 788, 556, …

**Verdict:** `0x025B` does **not** work on this match under current framing — **0** packets, **0** decodes. Fail closed; no product emit. Next single-variable hypothesis: confirm UsePacket/factory wire id for movement on build **16.14.794.5912** (possible remap vs public `0x025B`). Do not promote cross-channel schema-shaped false positives.

Focused tests: `python3 -m unittest scripts.tests.test_rofl_movement_decode`.

## Phase B E2 (wire packet-id remap)

Single variable: observed block `channel` may differ from public `0x025B` on 16.14.
Scanner: [`scripts/rofl2_movement_wire_scan.py`](../../scripts/rofl2_movement_wire_scan.py) via `--scan-wire-ids`.
Applies the clean-room 025B schema decoder to **every** observed channel; schema-shaped success is **never** acceptance. Ranking requires Hungarian oracle assignment (≤500 ms), ≥5 stable entities, ≥80 compared samples, and spatial-error ceilings. Optional Unicorn `Packet::Packet` factory map is best-effort and cannot suppress offline ranking.

### Command

```bash
npm run rofl:movement-decode -- \
  "$HOME/Documents/League of Legends/Replays/BR1-3264361042.rofl" \
  --scan-wire-ids \
  --oracle-jsonl artifacts/rofl/3264361042/events.rfc461.jsonl \
  --oracle-tolerance-s 0.5 \
  --sample-cap 300 --deep-cap 12000 --shortlist-size 10 \
  --append-speed-run \
  --hypothesis "E2 wire packet-id remap vs 025B schema+oracle" \
  --diff-label "phase-b-e2-wire-scan" \
  --json-out docs/rofl-research/movement-wire-scan-BR1-3264361042.json
```

If a winner ever passes gates, decode with configurable id (research events only):

```bash
npm run rofl:movement-decode -- \
  "$HOME/Documents/League of Legends/Replays/BR1-3264361042.rofl" \
  --mode decode --packet-id 0x???? \
  --events-out /tmp/rofl-025b-remap-events.json
```

### Measured on BR1-3264361042

| Quantity | Value |
|---|---|
| End-to-end wall | **37788.979 ms** |
| Channels scanned | **217** |
| Winner | **none** |
| Keep | **discard** |
| Unicorn factory (optional) | ok (did not alter offline discard) |

Top shortlist (all rejected; schema≠movement):

| Channel | Hex | Score | Oracle assign / compared | Median err | Primary FP reasons |
|---|---|---|---|---|---|
| 290 | 0x122 | 42.8 | 7 / 7 | 461 | insufficient comparisons; high spatial error |
| 556 | 0x22c | 37.1 | 8 / 8 | 538 | insufficient comparisons; high spatial error |
| 173 | 0xad | 32.3 | 6 / 6 | 512 | count below movement scale; high error |
| 197 | 0xc5 | 31.2 | 6 / 6 | 536 | count below movement scale; high error |
| 778 | 0x30a | 30.7 | 3 / 6 | 579 | unstable entities; high error |

Evidence: [`movement-wire-scan-BR1-3264361042.json`](movement-wire-scan-BR1-3264361042.json), [`speed-runs.jsonl`](speed-runs.jsonl) (`phase-b-e2-wire-scan`).

**Verdict:** no wire-id remap winner on this match. Schema-shaped hits exist but fail oracle/stability gates. Next single-variable hypothesis: **movement encoding change** (not just id) — legacy `0x61` multi-waypoint group framing and/or alternate cipher/schema on 16.14.

Focused tests: `python3 -m unittest scripts.tests.test_rofl_movement_wire_scan`.

## Phase B E2.1 (corrected: blockParam / hero netId QA)

Historical E2 (`movement-wire-scan-BR1-3264361042.json`, wall **37788.979 ms**, no winner) remains **discarded**. It ranked by schema-shaped decode and grouped oracle tracks by decoded inner f4 `netId`, which exploded into hundreds of IDs and starved comparisons.

E2.1 correction (public 0x025B param filter + same-match replication acceptance):
champion netIds **`0x400000AE..0x400000B7`** (`1073741998..1073742007`). Rank channels by all-10 hero **block `param`** counts first; QA assigns **blockParam ↔ participant** (Hungarian); decoded inner ID is diagnostic only. Hero params alone never accept.

### Command

```bash
npm run rofl:movement-decode -- \
  "$HOME/Documents/League of Legends/Replays/BR1-3264361042.rofl" \
  --scan-wire-ids \
  --oracle-jsonl artifacts/rofl/3264361042/events.rfc461.jsonl \
  --oracle-tolerance-s 0.5 \
  --sample-cap 400 --deep-cap 15000 --shortlist-size 10 \
  --append-speed-run \
  --hypothesis "E2.1 blockParam hero-netId QA vs wire-id remap" \
  --diff-label "phase-b-e2.1-blockparam" \
  --json-out docs/rofl-research/movement-wire-scan-E2.1-BR1-3264361042.json
```

### Measured on BR1-3264361042

| Quantity | Value |
|---|---|
| End-to-end wall | **57251.043 ms** |
| Winner | **none** |
| Keep | **discard** |

Top channels by hero-param coverage (all 10 proven netIds):

| Channel | Hex | Hero blocks | Per-hero (ae..b7) highlights |
|---|---|---|---|
| **351** | **0x15f** | **10083** | 882 / 1988 / 1680 / 1062 / 782 / 935 / 436 / 782 / 924 / 612 |
| 259 | 0x103 | 9242 | 823 / 2247 / 544 / 706 / 940 / 1776 / 1230 / 77 / 484 / 415 |
| 1194 | 0x4aa | 8249 | 1295 / 690 / 524 / 774 / 682 / 991 / 1484 / 135 / 1275 / 399 |
| 921 | 0x399 | 7025 | 997 / 1143 / 516 / 612 / 1405 / 461 / 450 / 345 / 641 / 455 |
| 398 | 0x18e | 6894 | 979 / 1129 / 501 / 602 / 1388 / 453 / 436 / 332 / 630 / 444 |
| 632 | 0x278 | 6857 | 1245 / 1422 / 449 / 538 / 747 / 765 / 679 / 366 / 359 / 287 |

Decoder/oracle on shortlist: **351** has **0** 025B-schema successes (hero-param presence ≠ movement encoding). Best schema-shaped false positive **921** (`succ≈0.45`) still yields **0** oracle assignments (best median spatial error ~8–10k). No methodPassed (`raw_decoded_point` / continuity track).

Evidence: [`movement-wire-scan-E2.1-BR1-3264361042.json`](movement-wire-scan-E2.1-BR1-3264361042.json); prior E2 preserved at [`movement-wire-scan-BR1-3264361042.json`](movement-wire-scan-BR1-3264361042.json).

**Verdict:** still no wire-id remap winner. The strongest hero-param channel (**351 / 0x15f**) does not decode under the public 025B schema. Next single-variable hypothesis: **movement encoding change** on 16.14 for that wire id (legacy `0x61` multi-waypoint / alternate cipher-schema), probing channel **351** first.

## Phase B E3 (PathPacket + Unicorn Deserialize buffer)

Single variable: channel **351** (then fallback hero-param channels) may carry **encrypted** movement that patch-specific `Deserialize` expands into a compressed PathPacket buffer.

### Research inputs (facts only; no unlicensed vendoring)

- **Riot:** local Replay API exposes camera/playback; **no** raw ROFL packet decode.
- **Public method (Mowokuma/ROFL, no license — do not copy source):** run patch movement `Deserialize` under Unicorn, read dynamic payload buffer, parse PathPacket (`u16` flags/count, `u32` entity, `f32` speed, optional byte, compressed bitmask/deltas; `x=i16*2+7358`, `z=i16*2+7412`). Windows patch example movement net id **980** is **absent** on this ROFL (`count=0`).
- **Product / Vercel:** emulator is research-only to derive a **compact pure decoder/config**. Ship browser Worker/WASM or Blob + background worker. **Never** upload League binary / Unicorn as a Vercel Function dependency (4.5MB / native).

Probe: [`scripts/rofl2_movement_emulator_probe.py`](../../scripts/rofl2_movement_emulator_probe.py).

### Command

```bash
npm run rofl:movement-emulator-probe -- \
  "$HOME/Documents/League of Legends/Replays/BR1-3264361042.rofl" \
  --oracle-jsonl artifacts/rofl/3264361042/events.rfc461.jsonl \
  --max-samples 40 --append-speed-run \
  --hypothesis "E3 PathPacket after Unicorn Deserialize buffer" \
  --diff-label "phase-b-e3-pathpacket" \
  --json-out docs/rofl-research/movement-emulator-probe-BR1-3264361042.json
```

### Measured on BR1-3264361042

| Quantity | Value |
|---|---|
| End-to-end wall | **17016.344 ms** |
| Winner | **none** |
| Pure browser decoder derived | **false** |
| Keep / productEligible | **discard** / **false** |

Channel digest (hero-param blocks, PathPacket / Unicorn buffer):

| Channel | Hex | Hero blocks | Size mode | Raw PathPacket | Unicorn path buffers | Factory Deserialize |
|---|---|---|---|---|---|---|
| **351** | **0x15f** | **10046** | 9 B (5024) | 0 | 0 | `0x1014866b8` (ok create; no path buffer) |
| 259 | 0x103 | 8717 | 9 B | 0 | 0 | ok create; no path buffer |
| 1194 | 0x4aa | 8246 | 60 B | 0 | 0 | ok create; no path buffer |
| 921 | 0x399 | 6912 | 23 B | 0 | 0 | ok create; no path buffer |
| 398 | 0x18e | 6862 | 7 B | 0 | 0 | ok create; no path buffer |
| 632 | 0x278 | 6855 | 18 B | 0 | 0 | ok create; no path buffer |

Evidence: [`movement-emulator-probe-BR1-3264361042.json`](movement-emulator-probe-BR1-3264361042.json), [`speed-runs.jsonl`](speed-runs.jsonl) (`phase-b-e3-pathpacket`).

Gates unchanged: ≥5 hero blockParams, ≥80 comparisons, median/p95/max error ceilings, PathPacket **full consume**. Oracle is QA only.

**Verdict:** E3 **discard**. Channel 351 is identity-strong but ciphertext-sized (mode **9 B**); `create_packet`+`Deserialize` return/consume without materializing a PathPacket dynamic buffer under current arm64 Unicorn stubs. Zero raw PathPacket full-consume across all six channels. Research-only pure PathPacket config (`pathpacket-compressed-v1`) is recorded with `requiresLeagueBinary=false` / `productEligible=false` — **not** derived as a proven browser decoder.

**Next single-variable hypothesis (E4):** channel 351 direct-field object layout from arm64 `Deserialize` (not PathPacket buffer offsets).

Focused tests: `python3 -m unittest scripts.tests.test_rofl_movement_emulator_probe`.

## Phase B E4 (channel 351 direct-field layout)

Single variable: channel **351** is a **32-byte direct-field** packet (`Deserialize @ 0x1014866b8`), not a PathPacket vector. Layout derived from local 16.14 arm64 via Capstone + Unicorn write traces (no unlicensed source copy; no Replay API).

Probe: [`scripts/rofl2_movement_direct_field_probe.py`](../../scripts/rofl2_movement_direct_field_probe.py).

### Binary layout (351)

| Offset | Field |
|---|---|
| `+0x08` | `u32` stored type `0x15f` |
| `+0x0c` | `u32` inner entity id (LUT-varint precheck @ `0x101775b60`, LUT VA `0x10205cd30`) |
| `+0x10` | `u32` encrypted direct field (schema jump → readers) or default |
| `+0x14` | `u32` second encrypted field (secondary jump table) |
| `+0x18` | `u8` tertiary / default |
| heap | **no** dynamic path buffer (`heapDelta=32`) |

Schema from `payload[0]` bits 3..5; observed schemas **0/2/5/7** only.

### Command

```bash
npm run rofl:movement-direct-field -- \
  "$HOME/Documents/League of Legends/Replays/BR1-3264361042.rofl" \
  --oracle-jsonl artifacts/rofl/3264361042/events.rfc461.jsonl \
  --corr-cap 400 --append-speed-run \
  --hypothesis "E4 channel 351 direct-field from arm64 Deserialize" \
  --diff-label "phase-b-e4-direct-field" \
  --json-out docs/rofl-research/movement-direct-field-BR1-3264361042.json
```

### Measured on BR1-3264361042

| Quantity | Value |
|---|---|
| End-to-end wall | **7818.323 ms** |
| Blocks / inner ids decoded | **10795 / 10795** |
| Proven-hero inner ids (`AE..B7`) | **0** |
| Unique inners | **159** (bands: `0x400000xx` 5433, `0x40000xxx` 2573, `0x4000xxxx` 2789) |
| Best coord hypothesis | `f10_packed14`: assign 1 / cmp 40 / med **1165.8** (gates fail) |
| Pure browser decoder | **false** |
| Keep / productEligible | **discard** / **false** |

Fallback 259/1194: factory `heapDelta=48` ≠ 32 → **layout mismatch**; deep probe skipped (no brute force).

Evidence: [`movement-direct-field-BR1-3264361042.json`](movement-direct-field-BR1-3264361042.json), [`speed-runs.jsonl`](speed-runs.jsonl) (`phase-b-e4-direct-field`).

**Verdict:** channel 351 is a **direct-field non-hero entity-reference** packet (likely targeting minions/wards/other netIds), **not** movement. Coordinate interpretations of `+0x10` / pre-SIMD plaintext fail oracle gates.

**LUT hygiene:** removed hardcoded unlicensed-style fallback LUT bytes from `rofl2_movement_decode.py`. Runtime loads patch binary or independently extracted cache [`generated/cipher-lut-16.14.bin`](generated/cipher-lut-16.14.bin) + [`generated/cipher-lut-16.14.manifest.json`](generated/cipher-lut-16.14.manifest.json) (sha256 `328528d6…c04b`).

**Next (E5):** find movement via binary registrar / UsePacket wire id, not hero-param cadence ranking alone.

Focused tests: `python3 -m unittest scripts.tests.test_rofl_movement_direct_field_probe`.

## Phase B E5 (ROFL-X structural MOVEMENT_PATH scan)

Single variable: discover movement by **factory object structure**, not opcode folklore.

Prior art (cite only; no code copy): [Toastaspiring/ROFL-X](https://github.com/Toastaspiring/ROFL-X) (**MIT**) documents `MOVEMENT_PATH` on 15.1–15.5 as a ~**48-byte** packet object with decoded payload **pointer at +0x18** and **size at +0x20**, then PathPacket (`u16` flags/count, `u32` id, `f32` speed, compressed coords). Example movement opcode **980** on 15.5; a 16.8 sample flags **982** as a high-frequency candidate with unresolved decoder config.

Probe: [`scripts/rofl2_movement_structural_scan.py`](../../scripts/rofl2_movement_structural_scan.py).

### Method

1. Enumerate every observed opcode once; factory → `heapDelta`, vtable, Deserialize, Use; group by Deserialize.
2. Score size-48 Deserialize bodies for ROFL-X signature; require `alloc → str x0,[obj,#0x18]` plus size@+0x20; **reject** `0x18`-stride element vectors.
3. Hook vector alloc/free helpers derived from those call sites (`0x10162eb4c` / `0x10162ebac`); re-run Deserialize; PathPacket full-consume; oracle on **decoded entity id**.
4. Extend only to non-48 classes with the same strong byte-buffer signature.

### Measured on BR1-3264361042

| Quantity | Value |
|---|---|
| End-to-end wall | **4523.226 ms** |
| Opcodes / size-48 classes | **217** / **40** |
| Strong ROFL-X byte-buffer (size 48) | **0** |
| Closest structural hit | **855** (`Deserialize 0x101491050`) — alloc→+0x18 **but** `0x18`-stride vector |
| Constructed factory (top size-48) | **24/24** vptr+opcode ok |
| PathPacket / oracle | **0** / n/a |
| Prior-art opcodes 980 / 982 / 0x025B | **0 / 0 / 0** blocks |
| Pure browser decoder | **false** |
| Keep / productEligible | **discard** / **false** |

Evidence: [`movement-structural-scan-BR1-3264361042.json`](movement-structural-scan-BR1-3264361042.json), [`speed-runs.jsonl`](speed-runs.jsonl) (`phase-b-e5-structural`).

**Structural blocker:** no observed 16.14 opcode is a ROFL-X **byte-buffer** MOVEMENT_PATH class. Opcode **855** is the only size-48 `alloc→str x0,[+#0x18]` hit and stores a vector of **24-byte elements**, not PathPacket bytes. Product browser path remains blocked until a pure decoder/config is derived (`browserSafe=false` while emulation is required).

**Next (E6):** Pivot semantic discovery to exact-patch **x86-64** (Mac universal thin / Windows PE). ARM64 cannot validate Windows x86 layout priors (`+0x18`/`+0x20`).

Focused tests: `python3 -m unittest scripts.tests.test_rofl_movement_structural_scan`.

## Phase B E6 (exact-patch x86-64 constructor discovery)

Single variable: derive MOVEMENT_PATH from **exact-patch x86-64** factories (not Mac ARM64 layout assumptions), while keeping the product decoder OS-neutral (Windows+Mac, no League binary / Unicorn at runtime).

Why: wire stream is platform-neutral; vtables/struct layout/allocators are arch-specific. ROFL-X/MIT and Mowokuma prior art are Windows x86-64. Constructor technique (store packet id at `this+8`, RIP-relative vtable) implemented from public facts only — no third-party source copied.

Probe: [`scripts/rofl2_x86_packet_discover.py`](../../scripts/rofl2_x86_packet_discover.py) + format abstraction [`scripts/rofl2_binary_format.py`](../../scripts/rofl2_binary_format.py).

### Method

1. `lipo -thin x86_64` on installed 16.14 universal Mach-O (never commit); PE32+ section parse + synthetic fixtures for Windows path.
2. Enumerate factories: `mov edi, SIZE; call new; mov word [rax+8], OPCODE`; recover Itanium vptr via RIP LEA+0x10; read Deserialize/Use.
3. Validate constructor-stored ids against observed ROFL opcodes.
4. Rank MOVEMENT_PATH structurally (size~48, bufferish Deserialize, frequency/variability) — factory evidence, not numeric proximity alone.
5. Unicorn **x86-64** Deserialize on strong candidates; strict PathPacket; oracle on decoded entity id (≥80 samples, ≥5 heroes, med≤120 / p95≤350 / max≤800, ≤500 ms).
6. If proven: emit pure wire/TS/WASM manifest (`browserSafe` / `productEligible`). If emulator still required: keep those false, document offline per-patch manifest → shared browser decoder architecture.

### Measured on BR1-3264361042

| Quantity | Value |
|---|---|
| End-to-end wall | **15739.476 ms** |
| Binary | Mac Mach-O **x86_64** thin, sha256 `6c9e3919…b34e` |
| Factory stubs / unique opcodes | **907** / covered **187/217** (86.18%) |
| Constructor id matches key | **187** |
| Prior-art opcode **980** | factory **exists**, objectSize=**32** (not 48), **0** ROFL blocks |
| Top structural ranks | **660** (sz32, mish), **556** (sz48, 37k blocks), **321**/780/58 (sz28, mish) |
| PathPacket samples / oracle | **0** / n/a |
| Pure browser decoder derived | **false** |
| Keep / productEligible / browserSafe | **discard** / **false** / **false** |
| Windows | format support tested (synthetic PE); **real PE binary not validated** |

Evidence: [`movement-x86-discover-BR1-3264361042.json`](movement-x86-discover-BR1-3264361042.json), [`speed-runs.jsonl`](speed-runs.jsonl) (`phase-b-e6-x86`).

**Blocker:** x86 constructor/vtable map is solid, but no candidate yielded PathPacket buffers under Unicorn that pass oracle gates. 16.14 remapped away from classic ROFL-X 48-byte/+0x18/+0x20 MOVEMENT_PATH (980≠48B; no 980 traffic on this match).

**Invalidity (caught in E7a):** E6 Unicorn drive **fabricated** zero objects (opcode@+8 only) and never called `stubVa`. Vtable recovery could bleed into the next factory stub (660 falsely used Deserialize `0x101339180` instead of `0x1014894f0`). Treat E6 PathPacket negatives as **invalid**; see E7a.

**Production architecture (documented; not yet derived):** offline per-patch manifests from PE (Windows) or Mach-O x86_64 (Mac); one shared TS/WASM browser decoder for Windows+Mac; optional Blob+Worker for unknown patches. Never ship League binary or Unicorn to end users.

**Next (E7a):** Call discovered factory stubs under SysV, validate vptr/opcode, then Deserialize — single variable “properly constructed x86 packet object.”

Focused tests: `python3 -m unittest scripts.tests.test_rofl_x86_packet_discover`.

## Phase B E7a (constructed x86 factory drive)

Single variable: **properly constructed** x86 packet objects (call `stubVa`), invalidating E6 fabricated-object negatives.

Probe: [`scripts/rofl2_x86_unicorn_drive.py`](../../scripts/rofl2_x86_unicorn_drive.py) + `--e7a` on [`scripts/rofl2_x86_packet_discover.py`](../../scripts/rofl2_x86_packet_discover.py).

### Method

1. Fix vptr recovery (stop before next stub; follow shared ctor `jmp` tail).
2. Unicorn SysV: enter factory stub with `rbx=result_slot`, hook evidenced `operator new`, validate vptr + opcode@+8 before Deserialize.
3. One emu map per sample flow: construct → Deserialize; scan heap `ptr+size` / `begin/end/cap`.
4. Primary opcode **660** (sz32, 1721 blocks); fallback **556** only if 660 fails semantically.
5. Spread samples across match (660 starts ~144s); full-block PathPacket+oracle only if hits appear.

### Measured on BR1-3264361042

| Quantity | Value |
|---|---|
| End-to-end wall | **21547.429 ms** |
| Factory validation (660) | **ok** — vptr `0x102647ee0`, opcode 660, stub `0x1012d960b` |
| Correct Deserialize (660) | **`0x1014894f0`** (E6 had wrong `0x101339180`) |
| 660 probe | factoryOk **40/40**, deserOk **26/40**, PathPacket **0** |
| 660 semantic | **netId@+0xc field packet**, not PathPacket |
| 556 fallback | factoryOk **40/40**, PathPacket **0** |
| Oracle | n/a (0 decoded paths) |
| Pure / browserSafe / productEligible | **false** / **false** / **false** |
| E6 fabricated negatives | **invalid** |

Evidence: [`movement-x86-e7a-constructed-BR1-3264361042.json`](movement-x86-e7a-constructed-BR1-3264361042.json), [`speed-runs.jsonl`](speed-runs.jsonl) (`phase-b-e7a-constructed`).

**Next (E7b):** official Windows 16.14 PE MSVC discovery (prior-art platform).

Focused tests: `python3 -m unittest scripts.tests.test_rofl_x86_e7a_constructed`.

## Phase B E7b (official Windows 16.14 PE MSVC discovery)

Single variable: run semantic discovery on the **real official Windows x86-64 PE** (platform prior art was built for), with MSVC ctor/vtable + Windows ABI Unicorn — not Mac Itanium offsets.

### Provenance (binary not committed)

| Field | Value |
|---|---|
| Source | Riot PatchSieve BR1 official |
| Version | `16.14.7945912+branch.releases-16-14...platform.windows` |
| Manifest | `https://lol.secure.dyn.riotcdn.net/channels/public/releases/952B478DFC66B0AB.manifest` |
| SHA256 | `34de26710352fcf4360b27691cecf77843a0ea338cd455be4fabb63fb467984f` |
| Normalized ROFL build | **16.14.794.5912** |
| Local path | `/tmp/League-of-Legends-16.14-win.exe` (never commit) |

Probe: [`scripts/rofl2_win_pe_packet_discover.py`](../../scripts/rofl2_win_pe_packet_discover.py).

### Method

1. Load PE via `rofl2_binary_format`; validate machine amd64, sections, SHA256.
2. MSVC discovery: `mov word [rcx+8], imm16`; final RIP `lea`→`mov [rcx],reg` vptr (**no** Itanium +0x10); vtable +0 dtor / +8 Deserialize / +16 Use; size from `mov ecx,size; call operator_new; call ctor`.
3. Rank ~48B + large Deserialize + +0x18/+0x20 (verify); 980 only weak prior.
4. Unicorn **Windows ABI** (RCX/RDX/R8): construct then Deserialize; heap ptr+size / begin/end/cap; strict PathPacket + oracle.

### Measured on BR1-3264361042

| Quantity | Value |
|---|---|
| End-to-end wall | **7796.240 ms** |
| Constructor coverage | **217/217** ROFL opcodes (100%); 209 sized factories |
| Prior-art **980** | factory **exists**, objectSize=**32** (not 48), Deserialize `0x14102cf50`, **0** ROFL blocks |
| Top ranks | **107**/556/210 (size 48); none `movementish` byte-buffer |
| Constructed factory (top size-48) | **24/24** vptr+opcode ok |
| PathPacket / oracle | **0** / n/a |
| Windows real PE validated | **true** |
| Pure / browserSafe / productEligible | **false** / **false** / **false** |

Evidence: [`movement-win-pe-e7b-BR1-3264361042.json`](movement-win-pe-e7b-BR1-3264361042.json), [`speed-runs.jsonl`](speed-runs.jsonl) (`phase-b-e7b-win-pe`).

**Blocker:** On exact-patch Windows 16.14, classic ROFL-X MOVEMENT_PATH (48B + PathPacket buffer @+0x18/+0x20) is **not** present as prior-art opcode 980 (now size-32 field packet) and no observed size-48 class proves a variable byte-buffer PathPacket under constructed Deserialize.

**Next (E8):** MSVC RTTI + MakeFunction registration mapping to name the replacement movement opcodes, then constructed field capture — not frequency ranking alone.

Focused tests: `python3 -m unittest scripts.tests.test_rofl_win_pe_packet_discover`.

## Phase B E8 (MSVC RTTI + semantic registration → decode attempt)

Single variable: identify the post-WaypointGroup movement packets on official Windows 16.14 via strict MSVC x64 RTTI and MakeFunction handler registrations, then decode under constructed Windows ABI.

### Method

1. Strict COL decode for every E7b factory vptr (`signature==1`, `pSelf`, TD bounds, `.?AV`/`.?AU` name grammar). No string-proximity naming.
2. MakeFunction `<lambda_1>` TypeDescriptors naming `PKT_*Movement*` / Follow / Face / SyncCircular → typeid stub → std::function vtable → register wrapper or inline `mov r8d, imm; call hub` (`0x1406f78b0`). Opcode from registration immediate, not ROFL frequency.
3. Constructed Windows-ABI Deserialize + write/pre-reencrypt capture for mapped opcodes; oracle QA only.

### Measured on BR1-3264361042

| Quantity | Value |
|---|---|
| End-to-end wall | **14910.902 ms** |
| Factory RTTI coverage | **0 / 218** (packet vptrs RTTI-stripped; ~109 valid COLs are mostly `std::`) |
| Semantic opcodes | **SetMovementDriver=1104**, **DirectInput=58**, **AddFollowPosition=513**, **AddFollowTeleport=840**, **FaceDirection=420**, **SyncCircular=450** |
| ROFL blocks (mapped) | 1104:6 · 58:220 · 513:0 · 840:0 · 420:13353 · 450:12 |
| Maplike plaintext XYZ / oracle | **0** / n/a (gates not met) |
| Pure / browserSafe / productEligible | **false** / **false** / **false** |

Evidence: [`movement-win-pe-e8-BR1-3264361042.json`](movement-win-pe-e8-BR1-3264361042.json), [`speed-runs.jsonl`](speed-runs.jsonl) (`phase-b-e8-rtti-registration`).

**Blocker:** Registration mapping succeeded; constructed Deserialize still fails to yield oracle-grade positions (DirectInput 3×f32 path often short-consumes / faults mid encrypt-at-rest helpers; SetMovementDriver vectors do not materialize). No WaypointGroup string on this PE.

**Next:** Finish decrypt-access-release capture for opcodes 1104+58 (hook remaining unmapped helpers), bind handler-target identity without `blockParam`, then re-run oracle gates.

Focused tests: `python3 -m unittest scripts.tests.test_rofl_win_pe_e8_movement`.

Probe: `npm run rofl:win-pe-e8` / [`scripts/rofl2_win_pe_e8_movement.py`](../../scripts/rofl2_win_pe_e8_movement.py), RTTI: [`scripts/rofl2_win_pe_rtti.py`](../../scripts/rofl2_win_pe_rtti.py).

## Phase B E9 (type-107 Replication meet-in-the-middle)

Single variable: treat channel/type **107** Replication as the native position candidate, sandwiching BR1 ROFL decode against same-match Replay API numeric oracle and FUR JSONL schema/cadence only (no FUR ROFL).

### Method

1. Reconstruct wire payloads as `encode_type(107) || 0xA6 || wire_payload` (byte-identical to Unicorn `block_extract`); Deserialize with cursor after type byte.
2. Parse post-Deserialize vectors with existing replication grammar; test candidate `(0,0)/(0,1)` pairs.
3. BR1 Replay API QA (≤500 ms, ≥500 updates / 10 heroes, med≤120 / p95≤350 / max≤800). FUR JSONL = schema/cadence/field-presence only.
4. Remove false gold mapping for `(0,0)/(0,1)` without inventing position semantics.

### Measured on BR1-3264361042

| Quantity | Value |
|---|---|
| End-to-end wall | **18840.989 ms** (≤60 s target) |
| Channel-107 blocks | **14801** |
| Framing | **`6ba6 \|\| wire_payload`** (prefix equals Unicorn extract) |
| Pure blob↔body parity | **false** (encrypt-at-rest transform; fail closed) |
| Bank0 candidate updates | **~30761** @ **~0.5 s** median cadence (all 10 heroes) |
| Blob f32 hits within 40u of oracle x/z | **0** |
| BR1 oracle QA | **fail** (assignment/gates; not positions) |
| `(0,0)/(0,1)` semantic | **unclassified** (gold label removed; position claim rejected) |
| browserSafe / productEligible | **false** / **false** |

Evidence: [`movement-replication-e9-BR1-3264361042.json`](movement-replication-e9-BR1-3264361042.json), [`speed-runs.jsonl`](speed-runs.jsonl) (`phase-b-e9-replication-position`).

**Blocker:** Type-107 Deserialize framing is solved, but bank0 HF pairs are **not** oracle positions (zero plaintext f32 hits; near-constant ~1.44-unit 0.5 s drift). Native position source remains open; pure decrypt for browser Worker still blocked.

**Meet-in-the-middle boundaries:** A=BR1 ROFL 16.14 type-107 · B=BR1 Replay API JSONL (exact numeric) · C=FUR–G2 `events_2970115_1_riot.jsonl` gameID 426848 / LOLTMNT01 / 16.13 (schema only). FUR ROFL unavailable by design — not searched, not a blocker.

Focused tests: `python3 -m unittest scripts.tests.test_rofl_replication_position_e9`.

Probe: `npm run rofl:replication-position-e9` / [`scripts/rofl2_replication_position_e9.py`](../../scripts/rofl2_replication_position_e9.py).

## Phase B E10 (Windows register-level coordinate discovery)

Single variable: plaintext hero X/Z may exist only transiently in XMM/GPR (or object writes) during Windows MSVC `Deserialize`, before encrypt-at-rest — Maknee-style register capture under constructed Unicorn x64 ABI.

### Method

1. Official PE `/tmp/League-of-Legends-16.14-win.exe` (SHA256 `34de2671…`); E7b factory map (217/217).
2. Priority: E2.1 all-10 hero-param channels (cadence/payload variability), plus E8 semantic movement opcodes.
3. Bounded CODE sampling every 48 insns (cap 80k): XMM0–7 f32 lanes, GPR low32-as-f32, object writes; optional `2*i16+SR_center` only for non-trivial i16 pairs (no learned affine).
4. Train/holdout era split; pair keys `(opcode,pcX,siteX,pcZ,siteZ,swap)`; axis swap only if both splits improve; gates ≥80 samples / ≥5 heroes / med≤120 / p95≤350 / max≤800.

### Measured on BR1-3264361042

| Quantity | Value |
|---|---|
| End-to-end wall | **20217.930 ms** (≤60 s) |
| Opcodes with hero samples | **16** (351, 259, 1194, … + 420/58) |
| Train / holdout deserialize runs | **150** / **90** (construct OK 100%) |
| Raw SR-range hits → oracle-tagged | train **736→69**, holdout **511→9** |
| Stable XZ pair keys (train) | **0** |
| Winner opcode/PC/register | **none** |
| pure / browserSafe / productEligible | **false** / **false** / **false** |

Evidence: [`movement-win-pe-e10-BR1-3264361042.json`](movement-win-pe-e10-BR1-3264361042.json), [`speed-runs.jsonl`](speed-runs.jsonl) (`phase-b-e10-win-pe-regcapture`).

**Blocker:** No stable register/object XZ pair passed train+holdout gates under bounded Deserialize capture (frequent fetch faults to `0x0` / helper PCs; single-axis oracle tags do not form same-sample pairs). Native position source still open. Register-capture-only path would remain `browserSafe=false` (Blob/background-worker fallback).

Focused tests: `python3 -m unittest scripts.tests.test_rofl_win_pe_e10_regcapture`.

Probe: `npm run rofl:win-pe-e10` / [`scripts/rofl2_win_pe_e10_regcapture.py`](../../scripts/rofl2_win_pe_e10_regcapture.py).

## Phase B — E11 reconstructed Deserialize drive (Windows 16.14)

**Single variable:** Feed Windows Deserialize the Unicorn-style reconstructed buffer (`encode_type(op) || marker || wire`), not raw `extract_blocks_py` payloads; finish decrypt-access-release for opcodes **58** / **1104**; QA against BR1 Replay API.

### Method

1. Reconstruct: `encode_type` from `TYPE_COUNT_VALUE=0x55D`; marker `0xA6` (1-byte bit header for 58/420) or `0xC6FA` (2-byte for 1104). Validate ≥50 early/mid/late samples: recon consume/retAl ≫ raw (fail-closed).
2. Hook DirectInput END_READ `0x140E66BAB` (plaintext Vector3 at `obj+0x10` before re-encrypt) — not sparse every-48 sampling.
3. SetMovementDriver buffer writers + FaceDirection negative control.
4. Train/holdout oracle QA: ≥80 / ≥5 heroes / med≤120 / p95≤350 / max≤800; direct or axis-swap only.

### Measured on BR1-3264361042

| Quantity | Value |
|---|---|
| End-to-end wall | **~12.3 s** (≤60 s) |
| Framing validated | **58**: rawOk 0 / reconOk 50; **1104**: rawOk 0 / reconOk 6 |
| DirectInput END_READ captures | **220 / 220** map-range XZ (1 netId) |
| SetMovementDriver map-range floats | **0** (small decrypted scalars only) |
| Oracle QA (nearest, direct) | med **~731** / p95 **~3825** / max **~3915** — **fail** |
| Winner opcode/PC/register | **none** |
| pure / browserSafe / productEligible | **false** / **false** / **false** |

Evidence: [`movement-win-pe-e11-BR1-3264361042.json`](movement-win-pe-e11-BR1-3264361042.json), [`speed-runs.jsonl`](speed-runs.jsonl) (`phase-b-e11-reconstructed-drive`).

**Blocker:** `opcodes_not_position_carriers` — reconstruction **validated**; DirectInput helpers **complete** (plaintext released); Replay API live-position gates **fail** (single netId; consecutive deltas superhuman for locomotion). E10 gap closed; native live-position source still open.

Focused tests: `python3 -m unittest scripts.tests.test_rofl_win_pe_e11_reconstructed_drive`.

Probe: `npm run rofl:win-pe-e11` / [`scripts/rofl2_win_pe_e11_reconstructed_drive.py`](../../scripts/rofl2_win_pe_e11_reconstructed_drive.py).

## Phase B — E12 multi-hero recon opcode scan (Windows 16.14)

**Single variable:** Reuse E11 reconstructed Deserialize + map-range MEM_WRITE capture; scan high-coverage multi-hero opcodes for plaintext X/Z that pass Replay API gates.

### Method

1. Candidates: E2.1 all-10 ≥500 hero blocks + top ≥5-hero / ≥500–1000 block ops + type 107; exclude 58/420/1104 controls.
2. Per opcode: marker select (`0xA6` then `0xC6FA`) fail-closed vs raw; screen MEM_WRITE map-range f32 pairs; promote top-3 to train/holdout QA.
3. Gates: ≥80 / ≥5 heroes / med≤120 / p95≤350 / max≤800; axis-swap only if both splits improve.

### Measured on BR1-3264361042

| Quantity | Value |
|---|---|
| End-to-end wall | **~13.0 s** (≤60 s) |
| Framing validated / failed | **20** / **2** |
| Opcodes with map-range writes | **7** |
| Best near-miss | **908** `obj+16/+20` — train med **~183** (10 heroes, n=42); holdout med **~191** (n=45) — **fail** |
| Winner | **none** |
| Segment types | type1=55, type2=28 |
| pure / browserSafe / productEligible | **false** / **false** / **false** |

Evidence: [`movement-win-pe-e12-BR1-3264361042.json`](movement-win-pe-e12-BR1-3264361042.json), [`speed-runs.jsonl`](speed-runs.jsonl) (`phase-b-e12-recon-opcode-scan`).

**Blocker:** `position_not_in_chunk_packets` — multi-hero reconstructed framing works; some type-1 opcodes emit map-range floats; none pass live-position QA. Next hypothesis: type-2 keyframe segments.

Focused tests: `python3 -m unittest scripts.tests.test_rofl_win_pe_e12_recon_opcode_scan`.

Probe: `npm run rofl:win-pe-e12` / [`scripts/rofl2_win_pe_e12_recon_opcode_scan.py`](../../scripts/rofl2_win_pe_e12_recon_opcode_scan.py).

## Phase B — E13 type-2 keyframe positions (Windows 16.14)

**Single variable:** Parse type-2 keyframes with reconstructed Deserialize / structured blob scan; QA multi-hero X/Z at keyframe times (±500 ms).

### Method

1. Inventory type-2: count, ~60s cadence, header `u8|f32`, a8/player-blob layout (10 blobs, proven netId AE..B7 order).
2. Treat naive `extract_blocks_py` on KF as ghost-prone (e.g. opcode 491, no factory); only Deserialize channels that also exist in type-1 with matching modal wire sizes.
3. Static map-range f32 (+ optional i16-near-netId) in player blobs; filtered block MEM_WRITE pairs.
4. Train/holdout by early/mid/late keyframes; gates ≥80 / ≥5 / med≤120 / p95≤350 / max≤800.

### Measured on BR1-3264361042

| Quantity | Value |
|---|---|
| End-to-end wall | **~33.8 s** (≤60 s) |
| Keyframes / chunks | **28** / **55** |
| Cadence | **~60.01 s** median (not 1Hz) |
| Layout | header `u8=1\|f32`; 10 player blobs + a8; netId order AE..B7 **27/27** |
| Ghost channel 491 | **102480** hero-looking blocks, **no factory** |
| Blob static QA | fails (nearest holdout med hundreds–thousands) |
| Best near-miss | filtered block **130** `+24/+32` holdout med **~489** — **fail** |
| Winner | **none** |
| pure / browserSafe / productEligible | **false** / **false** / **false** |

Evidence: [`movement-win-pe-e13-BR1-3264361042.json`](movement-win-pe-e13-BR1-3264361042.json), [`speed-runs.jsonl`](speed-runs.jsonl) (`phase-b-e13-keyframe-positions`).

**Blocker:** `keyframes_floats_not_oracle_positions` (+ framing differs from chunks). Cadence honesty: even a future keyframe decode would be ~60s anchors only; native continuous stream still open.

Focused tests: `python3 -m unittest scripts.tests.test_rofl_win_pe_e13_keyframe_positions`.

Probe: `npm run rofl:win-pe-e13` / [`scripts/rofl2_win_pe_e13_keyframe_positions.py`](../../scripts/rofl2_win_pe_e13_keyframe_positions.py).

## Phase B — E14 PathController / GetPosition slots (Windows 16.14)

**Single variable:** Plaintext live positions appear only via PathController / GetPosition (or equivalent object slots) after reconstructed Deserialize+Use/enqueue — not by scanning packet-object floats.

### Method

1. Static: recover GetPosition (`lea rax,[rcx+0x20]; ret` @ `0x1403030c0`), PathController at hero+`0x28d0`, XYZ at PC+`0x20` (= hero+`0x28f0`); note `mPosition` string has **0** LEA xrefs.
2. Unicorn: stub PathController → GetPosition geometry proof; inspect packet virt Use (size/clone, not world apply).
3. Feed reconstructed 58 / 908; capture packet XYZ; absolute-poke proven GetPosition slot; readback via getter; train/holdout QA (axis-swap only).
4. Document `PathSetPositionCore@0x140389200` writes **normalized direction**, not absolute map XYZ.

### Measured on BR1-3264361042

| Quantity | Value |
|---|---|
| End-to-end wall | **~20.5 s** (≤60 s) |
| Getter / slot | **`0x1403030c0`** → PC+`0x20` / hero+`0x28f0` (geometry proof **ok**; 59 callers) |
| Packet virt Use | size getters (`mov eax,0x1c/0x50/0x40; ret`) — **not** PathController apply |
| PathSetPositionCore | direction normalize into +0x20 — **not** absolute world write |
| DI 58 via getter | 120/120 GetPosition round-trip; **1** hero; holdout fails gates |
| 908 via getter | best near-miss; holdout med **~191**, p95~790, max~2643, 10 heroes — **fail** |
| Winner | **none** |
| pure / browserSafe / productEligible | **false** / **false** / **false** |

Evidence: [`movement-win-pe-e14-BR1-3264361042.json`](movement-win-pe-e14-BR1-3264361042.json), [`speed-runs.jsonl`](speed-runs.jsonl) (`phase-b-e14-position-getters`).

**Blocker:** `getters_found_but_values_not_oracle`. Slots/getter identity recovered (HP-analogue geometry), but reconstructed packet floats through GetPosition are still not Replay API live positions; true locomotion apply still needs a full AIBase/PathController heap (`pathcontroller_heap_not_emulatable` for real Use-path binding). Cadence: no 1Hz claim — DI sparse/single-hero; 908 higher coverage but not oracle.

Focused tests: `python3 -m unittest scripts.tests.test_rofl_win_pe_e14_position_getters`.

Probe: `npm run rofl:win-pe-e14` / [`scripts/rofl2_win_pe_e14_position_getters.py`](../../scripts/rofl2_win_pe_e14_position_getters.py).

## Phase B — E15 absolute writers into GetPosition slot (Windows 16.14)

**Single variable:** Which functions store absolute map-range f32 into PathController+`0x20` (GetPosition slot), and can those writers be driven from reconstructed ROFL packets to pass oracle QA?

### Method

1. Static scan of non-stack `movss` Vector3 stores to `+0x20/+0x28`; classify (direction normalize vs copy vs scale).
2. Focus PathController code region; inventory PathSetCore / PathSetAbsolute callers.
3. Unicorn proof: PathSetAbsolute → absolute at PC+`0xa0`, direction at PC+`0x20`.
4. Related drive: reconstructed 58/908 XYZ → PathSetAbsolute → abs getter `@0x140305350`; train/holdout QA.

### Measured on BR1-3264361042

| Quantity | Value |
|---|---|
| End-to-end wall | **~15.3 s** (≤60 s) |
| Absolute writers to PC+`0x20` | **0** |
| PC-region +0x20 Vector3 writer | only **PathSetPositionCore** `@0x14038930b` — **direction_normalize** |
| Absolute world slot | **PC+`0xa0`** via PathSetAbsolute `@0x1403891a0`; getter `lea rax,[rcx+0xa0]` `@0x140305350` |
| Proof | +0xa0 holds map XYZ; +0x20 holds unit direction after PathSetAbsolute |
| Related QA (+0xa0) | 908 holdout med **~191** — fail (same floats as E14) |
| Winner on GetPosition+0x20 | **none** |
| pure / browserSafe / productEligible | **false** / **false** / **false** |

Evidence: [`movement-win-pe-e15-BR1-3264361042.json`](movement-win-pe-e15-BR1-3264361042.json), [`speed-runs.jsonl`](speed-runs.jsonl) (`phase-b-e15-position-writers`).

**Blocker:** `no_absolute_pc20_writers` (alias `position_slot_not_absolute_store`). GetPosition slot is facing/direction; live absolute XYZ is a different slot (+0xa0). Packet XYZ through PathSetAbsolute still `writers_values_not_oracle`. Next: path-integration / waypoint state, not more packet-float fishing into +0x20.

Focused tests: `python3 -m unittest scripts.tests.test_rofl_win_pe_e15_position_writers`.

Probe: `npm run rofl:win-pe-e15` / [`scripts/rofl2_win_pe_e15_position_writers.py`](../../scripts/rofl2_win_pe_e15_position_writers.py).

## Phase B — E16 PathSetAbsolute callers / path integration (Windows 16.14)

**Single variable:** Who calls PathSetAbsolute, with what sources, and does any ROFL-reachable path produce oracle XYZ — or is continuous position only produced by integrating waypoint/driver state each tick?

### Method

1. Enumerate call/jmp sites to PathSetAbsolute `@0x1403891a0`; classify (hero snap, facing/normalize, UpdatePC follow-on, temp stub).
2. Check packet Deserialize bodies (58/420/908/1104) for PathSetAbsolute reachability.
3. Inventory `addss`/`mulss` writers into PC+`0xa0` (tick integration); document UpdatePC/`PATH_APPLY` (+0x40 path vector).
4. Bounded Unicorn: PathSetAbsolute snap with reconstructed 58/908 XYZ + QA; integrator stub mutation proof (no fake waypoint walk).

### Measured on BR1-3264361042

| Quantity | Value |
|---|---|
| End-to-end wall | **~17.5 s** (≤60 s) |
| PathSetAbsolute callers | **30** — snap 4 / facing 11 / after UpdatePC 2 / temp stub 6 / unknown 7 |
| Packet deser → PathSetAbsolute | **58/420/908/1104 = false** |
| Integration writers to +0xa0 | **16** funcs with addss/mulss-before-store |
| UpdatePC / PATH_APPLY | writes **PC+0x40**, not absolute +0xa0 |
| Snap QA (packet → PathSetAbsolute) | 908 holdout med **~191** — fail |
| Waypoint structural decode | **none** → no naive walk |
| Winner | **none** |
| pure / browserSafe / productEligible | **false** / **false** / **false** |

Evidence: [`movement-win-pe-e16-BR1-3264361042.json`](movement-win-pe-e16-BR1-3264361042.json), [`speed-runs.jsonl`](speed-runs.jsonl) (`phase-b-e16-pathsetabsolute-callers`).

**Blocker:** `position_is_integrated_not_stored` (secondary `pathsetabsolute_callers_not_rofl_reachable`; snap QA `callers_values_not_oracle`; sim `integration_requires_full_sim`). Continuous Replay API positions align with tick integration into +0xa0 plus occasional snaps — not with packet XYZ carriers from E11–E15.

Focused tests: `python3 -m unittest scripts.tests.test_rofl_win_pe_e16_pathsetabsolute_callers`.

Probe: `npm run rofl:win-pe-e16` / [`scripts/rofl2_win_pe_e16_pathsetabsolute_callers.py`](../../scripts/rofl2_win_pe_e16_pathsetabsolute_callers.py).

## Track 1 — Product Replay API defaults (compact + zero settle)

**Single variable:** Promote the matched 2.202× keep (compact cached selection + `final_settle=0`) to product defaults; add research `--defer-liveclient` positions-only bench mode.

### Changes

- [`scripts/rofl_replay_api_to_jsonl.py`](../../scripts/rofl_replay_api_to_jsonl.py): `DEFAULT_FINAL_SETTLE=0.0`, `DEFAULT_CACHED_SELECTION_STRATEGY=compact`; argparse/help updated; `--selection full` via `--cached-selection-strategy full` remains explicit fallback; unproven compact still full-reasserts.
- `--defer-liveclient`: skip per-frame liveclient wait; emit identity-proven positions from initial roster only (no per-frame level/items/KDA).
- Ingest inherits defaults (does not pass overrides).

### Honesty

Replay API still cannot hit ≤60 s/match (~864 ms/frame best → ~22–25 min full). Defaults lock in the proven micro-opt; offline integrator / packet path remains the only ≤60 s candidate.

### Live bench

`live_bench_blocked`: `/replay/playback` 404 while liveclient responds (see `speed-runs.jsonl` `speed-track1-compact-default`). Unit tests cover defaults / full fallback / `--defer-liveclient`.

Focused tests: `python3 -m unittest scripts.tests.test_rofl_live_history scripts.tests.test_rofl_replay_api_to_jsonl`.

## Track 2 — Timed type-107 HP evidence

Emitter: `npm run rofl:replication-timed-hp` / [`scripts/rofl2_replication_timed_hp.py`](../../scripts/rofl2_replication_timed_hp.py).

Walks type-107 across chunks (default `--max-blocks 8000`), keeps `(5,0)/(5,1)` → mHP/mMaxHP with explicit max, emits ≥2 timed samples once 10-hero acceptance unlocks, writes a `rofl-trusted-hp-v1` candidate plus fuse dry-run. CreateHero/PUUID→netId bind is attempted; order-only fallback stays research (`productEligible=false`). Combat not trusted. Same-match ROFL SHA / roster hash are copied from trailing metadata when available.

Focused tests: `python3 -m unittest scripts.tests.test_rofl_replication_timed_hp`.

Artifacts: `docs/rofl-research/trusted-hp-candidate-BR1-3264361042.json`, `docs/rofl-research/timed-hp-report-BR1-3264361042.json` (live Unicorn: 5 samples; fuse dry-run **rejects** incomplete CreateHero/PUUID→netId bind).

## Track 3 — E17 path-integrator spike (Windows 16.14)

**Single variable:** Structurally decoded SetMovementDriver (**1104**) path state + fixed-dt tick integration into PathController+`0xa0` vs Replay API oracle. Fail closed if waypoints / driver state are not recovered.

### Method

1. Reuse E11 reconstruct (`encode_type || marker || wire`); E14–E16 offsets/QA helpers.
2. Hook 1104 Deserialize MEM_WRITE + post-deser buffers for path-blob / speed / waypoint-count; PathPacket full-consume only.
3. If path+speed+netId recovered → integrate polyline at `dt=1/30` into +0xa0 via PathSetAbsolute → abs getter; train/holdout QA (axis-swap only).
4. Else blocker: `waypoints_not_structurally_decoded` / `driver_state_incomplete` / `integration_requires_full_sim`.
5. Negative controls: 908 poke → PathSetAbsolute; FaceDirection (not position).

### Measured on BR1-3264361042

| Quantity | Value |
|---|---|
| End-to-end wall | **~12.6 s** (≤60 s) |
| Framing 1104 | rawOk **0** / reconOk **1** (validated; 6/6 blocks) |
| Structural path / speed / netId | **0** / **0** / **0** |
| PathPacket full-consume | **0** (bufs still `0/1/2` + `5/10/5`) |
| Integrated samples | **0** (refused — no waypoints) |
| 908 negative control | holdout med **~217** (n=20) — fail as expected |
| Winner | **none** |
| pure / browserSafe / productEligible | **false** / **false** / **false** |

Evidence: [`movement-win-pe-e17-BR1-3264361042.json`](movement-win-pe-e17-BR1-3264361042.json), [`speed-runs.jsonl`](speed-runs.jsonl) (`phase-b-e17-path-integrator`).

**Blocker:** `waypoints_not_structurally_decoded`. E16’s integration hypothesis stands, but 1104 still does not release map-range waypoint state under reconstructed Deserialize — cannot tick-integrate into +0xa0 without inventing paths.

Focused tests: `python3 -m unittest scripts.tests.test_rofl_win_pe_e17_path_integrator`.

Probe: `npm run rofl:win-pe-e17` / [`scripts/rofl2_win_pe_e17_path_integrator.py`](../../scripts/rofl2_win_pe_e17_path_integrator.py).

## Product roadmap (hybrid → calculator → speed)

Orchestrator: `npm run rofl:product-pipeline` / [`scripts/rofl_product_pipeline.py`](../../scripts/rofl_product_pipeline.py).

| Phase | Script | Gate / blocker on BR1-3264361042 |
|---|---|---|
| A CreateHero | `npm run rofl:create-hero-discover` | `champion_not_structurally_decoded` — spawn-shaped opcodes Deserialize but do not release champion↔netId; exhausted: no `PKT_CreateHero` RTTI, `StartHeroSpawn` not a packet, no plaintext skins in ROFL, keyframe netId↔champ-id association insufficient, AE..B7 order research-only |
| A timed HP fuse | existing `rofl:replication-timed-hp` | fuse rejects until Gate A complete |
| B combat | `npm run rofl:replication-combat-inventory` | `combat_wire_unproven` (inventory only; e.g. `mFlatMagicDamageMod`) |
| B ranks | `npm run rofl:ability-ranks-probe` | `ability_ranks_wire_unproven` |
| C offline positions | E17 report | `waypoints_not_structurally_decoded` → **Replay API only** for product positions |
| D publish | pipeline `D_publish` | `product_gates_incomplete` — no registry / calculatorReady |

**Honesty:** Hybrid trusted HP and calculator Send remain closed until CreateHero champion bind + combat + ranks prove out. Do not publish CreateHero-order HP as product.


