# Calculator-ready replay evidence: 2970132 game 1

## Result

On 2026-07-29, one real professional match completed the local product path:

- GRID series: `2970132`
- GRID game: `1`
- Riot platform/game: `LOLTMNT01-428534`
- Patch/build: `16.13` / `16.13.790.6961`
- Teams: GEN vs JDG
- Raw replay SHA-256:
  `303c9ff1b2fea35f53a8a14697d6daa7303b4159de4a6fbc9716d6147ca9b61c`

The result is `calculatorReady: true` under the disclosed
`living_post_seed_v1` policy. This is not a strict-all-frame claim.

## Same-match binding

The finalizer verifies all of these before decoding actions:

1. The raw replay hash equals the replay manifest and identity evidence hash.
2. The replay, manifest, identity evidence, and timeline contain the same ten
   PUUIDs.
3. Participant ID, full Riot ID, and champion agree for all ten players.
4. The ten hero netIds form a one-to-one mapping with those participant IDs.
5. Match code, GRID series/game, patch, and client build agree.
6. `createHeroOrderFallback` is false.

The stale standalone research identity artifact is not promoted or trusted as
the final match authority. The finalizer rebuilds the binding from the
match-bound replay manifest, raw replay roster, and embedded identity evidence.
No fixture or cross-match label mapping is used.

## Calculator gate

The current product validator reports:

| Check | Result |
|---|---:|
| PE HP seed coverage | 10 / 10 heroes |
| PE combat seed coverage | 10 / 10 heroes |
| Ability-rank density | 16,960 / 16,960 |
| Required living post-seed slots | 14,725 |
| Known living post-seed slots | 14,725 |
| Missing living post-seed slots | 0 |
| Honest pre-seed unavailable slots | 1,577 |
| Honest dead slots | 658 |
| Strict all-frame ready | false |
| Living post-seed ready | true |

The policy permits only pre-seed and dead slots to remain unavailable. It still
requires every living post-seed selected unit to carry honest HP, combat stats,
and ability ranks. The gate also requires trusted same-match HP evidence and
native live positions.

## Basic-attack timeline

The action finalizer scans the raw ROFL block stream using a patch/build-pinned
opcode registry. It keeps only proven basic-attack packet channels whose
`block.param` is one of the ten identity-bound hero netIds.

- Identity-bound basic attacks: `3,479`
- Heroes represented: `10 / 10`
- Attack targets: unavailable
- Damage amounts: unavailable
- HP-delta inference: none
- External research overlay: not used
- Effect on `calculatorReady`: none

The final output contains the same 3,479 rows in canonical rfc461 and the
GameTimeline. The validator compares both representations row-for-row, checks
the one-to-one netId/participant mapping, verifies source hashes, and rejects
research-only or participant-order rows.

## Browser verification

The generated timeline was loaded through the running app's local timeline
picker.

At 8:00:

1. The `Action timeline` control enabled automatically.
2. The panel displayed `101 / 3479` decoded attacks around the playhead.
3. No request for the bundled `2970110` research overlay occurred.
4. Selecting `Both` selected the living GEN and JDG 5v5 rosters.
5. `Send 5v5` became enabled.
6. Send opened the Calculator with all ten champions and their same-frame HP,
   combat stats, items, and ability ranks.
7. The browser console reported zero errors.

The Calculator correctly labeled the NvM result experimental and uncalibrated.
Its model edge is not a win probability or odds.

## Reproduction

Private GRID/replay inputs remain gitignored:

```bash
npm run rofl:finalize-calculator-ready -- \
  --rofl artifacts/pro-grid/replay_riot_2970132_1.rofl \
  --source-jsonl artifacts/rofl/2970132/events.g1.path1-final.rfc461.jsonl \
  --source-timeline artifacts/rofl/2970132/timeline.g1.path1-final.json \
  --replay-manifest artifacts/rofl/2970132/replay-manifest.g1.json \
  --identity-evidence artifacts/rofl/2970132/trusted-hp-perhero.g1.product.json \
  --output-jsonl artifacts/rofl/2970132/events.g1.calculator-ready.rfc461.jsonl \
  --output-timeline artifacts/rofl/2970132/timeline.g1.calculator-ready.json \
  --summary artifacts/rofl/2970132/calculator-ready.g1.summary.json
```

The final local outputs from this run:

| Artifact | Bytes | SHA-256 |
|---|---:|---|
| rfc461 JSONL | 115,241,489 | `81bc5e3430a59b6600fb5e06292ae1ce73cf466cc26155e0b18af02b92affa5c` |
| GameTimeline | 9,497,431 | `17219d85cc19470d711238e4c788a56346b9eeb14dd1179ca8100e8b1e196b74` |
| Validation summary | 5,727 | `68df1f7f518dc57767b292bc7065e285650aae3bb0f42bd627b53992b20c1188` |

Direct validation:

```bash
python3 scripts/validate-rofl-pipeline.py \
  --product \
  --require-calculator-ready \
  --calculator-ready-policy living_post_seed_v1 \
  --require-aa-timeline \
  --jsonl artifacts/rofl/2970132/events.g1.calculator-ready.rfc461.jsonl \
  --timeline artifacts/rofl/2970132/timeline.g1.calculator-ready.json
```

## Trust boundary

- No match was added to `public/data/matches/`.
- No public hosting or deployment was attempted.
- Content hashes prove integrity, not publication rights.
- `calculatorReady` means the Calculator can consume honest same-match state.
- AA timeline coverage means decoded attack starts, not full action-replay
  fidelity.
- Neither gate establishes calibrated fight outcome accuracy or betting odds.
