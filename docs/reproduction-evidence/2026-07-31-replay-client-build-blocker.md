# Replay client build blocker: 2970136 game 2

Date: 2026-07-31

This note records the exact external blocker encountered while attempting to
open the approved second professional match for Replay API capture.

## Target

- GRID series: `2970136`
- Game: 2
- Riot match code: `LOLTMNT01-429309`
- Local ROFL: `artifacts/pro-grid/replay_riot_2970136_2.rofl`
- Embedded replay build: `16.13.790.6961`
- Player-facing project patch label: `26.14`

The player-facing patch label is deliberately separate from the embedded Riot
build. The latter is the value that must match the installed game client for
Replay API playback.

## Attempt and result

The replay was copied to the logged-in League client’s standard replay folder
and opened through the client’s supported Watch path. Riot reached the game
client, then stopped with this exact compatibility error:

> This replay was created by an older version of League of Legends
> (`16.13.790.6961`). You are running version `16.15.0.0000`. These versions
> are incompatible. The game will now exit.

The Replay API was therefore not active for this match. No capture, HP/combat
fusion, product finalization, or publication was performed. `game.cfg` was not
changed.

## Reproduction guard

Run this read-only preflight before attempting playback:

```bash
npm run rofl:replay-api -- \
  --rofl artifacts/pro-grid/replay_riot_2970136_2.rofl \
  --require-build-match
```

`--require-build-match` exits `5` when the installed client is not an exact
build match. It does not launch the replay or mutate client configuration.
The phased `rofl_ingest.py capture` path now performs the same local check
before acquiring its controller lock or making any Replay API request, so an
incompatible client leaves the managed capture artifacts untouched.

## Product boundary

The GRID timeline remains research-only. GRID positions cannot be substituted
for same-match Replay API positions, and this build mismatch does not authorize
the second match to become `calculatorReady`. A compatible `16.13.790.6961`
client/build environment, or an approved second machine that has one, is still
required for this product-capture path.

## Exact handoff when a compatible client is available

Do not open the replay or query the Replay API until the local preflight passes.
The preflight is intentionally independent of login state and makes zero API
requests:

```bash
npm run rofl:replay-api -- \
  --rofl artifacts/pro-grid/replay_riot_2970136_2.rofl \
  --require-build-match
```

The required result is `buildMatch: true` for both
`16.13.790.6961` values. Only after that result should the logged-in operator
copy the ROFL into the League replay folder and open it through the supported
Watch route. Once the replay is visibly active, run the resumable product
capture/build/validate sequence:

```bash
python3 scripts/rofl_ingest.py inspect \
  artifacts/pro-grid/replay_riot_2970136_2.rofl \
  --force --public-patch 26.14

python3 scripts/rofl_ingest.py capture \
  artifacts/pro-grid/replay_riot_2970136_2.rofl \
  --force --public-patch 26.14

python3 scripts/rofl_ingest.py build \
  artifacts/pro-grid/replay_riot_2970136_2.rofl \
  --public-patch 26.14

python3 scripts/rofl_ingest.py validate \
  artifacts/pro-grid/replay_riot_2970136_2.rofl \
  --public-patch 26.14
```

The capture is resumable and writes only under the match artifact directory.
It must produce Replay API positions plus same-match HP, combat, and ability
rank evidence before finalization is attempted. If the preflight fails, stop:
do not pass `--allow-build-mismatch`, do not copy GRID fields into the product
timeline, and do not publish a registry entry.

The separate hosted-bundle reproduction can be completed from any clean
checkout without League or private local paths:

```bash
npm run repro:hosted -- \
  --manifest \
  https://97gks2fobqkgppwx.public.blob.vercel-storage.com/lol-strength-analysis/repro/2970132/v2/repro-bundle.g1.calculator-ready.json \
  --out /tmp/lol-strength-analysis-repro
```

That command is already validated from this machine. A second-machine result
still needs the operator, machine, checkout revision, and literal command
output recorded separately; this document does not claim that result has
occurred.
