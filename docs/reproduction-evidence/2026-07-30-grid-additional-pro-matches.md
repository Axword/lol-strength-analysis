# Additional professional-match evidence: GRID 2977166 and 2977164

On 2026-07-30, two additional public professional matches were acquired from
GRID after the approved pro-only query path was verified. The query was
bounded to League of Legends `ESPORTS` series in the July 2026 window and
filtered through the repository's Central Data tournament/team guard. No
scrim, practice, tryout, or private-feed query was used.

The GRID capability catalog was verified before the query:

- catalog version: `1.0.0`
- catalog SHA-256: `94fb8703d8bcdaab416c1b5f8ce727d5f486789267ae66e5b06f784766d127ed`
- central-data schema SHA-256: `9950e21b2986a87ac202f5bc87aa2007ccb52b40fe2e0975647502a7e648f4b0`
- series-state schema SHA-256: `a1786edb0624fa162b85d8e9ecf1422fa6699ff6d608da1be1cd00fc18c33632`
- file-list response: sanitized metadata only; provider download URLs were not retained

## Acquired matches

| GRID series | Tournament | Teams | Riot match | Files | Research validation |
|---|---|---|---|---|---|
| `2977166` | KeSPA Cup 2026, Group Stage Alpha | KT Rolster vs Gen.G Esports | `LOLTMNT02-440807` | Riot LiveStats, GRID events, ROFL | pass: 1,443 dense frames, 10 moving participants, 55 kills |
| `2977164` | KeSPA Cup 2026, Group Stage Alpha | BNK FearX vs Gen.G Esports | `LOLTMNT02-440749` | Riot LiveStats, GRID events, ROFL | pass: 1,636 dense frames, 10 moving participants, 29 kills |

The GRID events and ROFL rosters have exact 10-player PUUID overlap for both
matches. Canonical replay names were derived from the validated LiveStats
`platformID` and `gameID`; the raw series-keyed files remain preserved.

## Artifact receipts

The following hashes are local private research receipts. They do not grant
hosting, redistribution, publication, calculator, calibration, or market
authority.

### 2977166 / LOLTMNT02-440807

- raw Riot LiveStats: `4c035b9b7c306474dc7170bb0b08b9ad3fd1107ef181680752b2c5e471738711`
- raw GRID events ZIP: `6b80b32c5dc96eb92b3074a4080728a49ae42068bc2c1890b7f6a3d01d25de0b`
- raw ROFL: `2b22e1520688f595e47e42fa16ff7f6fb1e84244f0ba9b380363774d0287c58a`
- research rfc461: `526e30f5e2a3301222e9fd22cc0882849bc531fed6e69c67b809eeb934d9b1c1`
- slim SQLite: `888c97637937cfef0ac488b687901b5ead16fdeb2a47b856c48f7f7846818c19`
- research timeline: `fc50874b086dfb46a878165aa7fe31171f436c7f4855a679d7d87c57add63aeb`

### 2977164 / LOLTMNT02-440749

- raw Riot LiveStats: `9a2d78a235f2a07ad1eb0684216790608991fb936b9c3812b2539881acd00a8d`
- raw GRID events ZIP: `7f4213f5b08024b0cc3c39e62dbb72db532d8f6f192cfe4bf907182f2e070`
- raw ROFL: `c7eb19b1af18fd622a13abe74dd67183b413c54b50eda3d0741533d31d881a04`
- research rfc461: `bbfa6354d65108f546556ada80f6e14a2621595841a9e75d200d82e5a579f5e3`
- slim SQLite: `c0ea088b96eb5092931678ae8dd47cd6f589d5b1f6c3f0e20a23987ffdc7176a`
- research timeline: `4cdcf0bc34542d2e22ec36c4d97ff6af2c403bf8a56ad6c1c2c6a92ee07d2c10`

## Product gate result

Both research timelines pass the non-product `--require-live-positions` gate.
Both correctly fail `validate-rofl-pipeline.py --product` because the GRID
adapter is not an independently fused product source. The packet-level
promotion attempt on both canonical ROFLs emitted zero accepted timed HP
samples and remained fail-closed:

- `useReplicationPrologueOk=false`
- identity binding incomplete; only CreateHero/order fallback was available
- `calculatorReady=false`
- no product timeline or public registry entry was written

The public player-facing patch for this work is 26.14. The ROFL metadata
reports the internal replay/build label `16.14.794.9266`; that label is used
only to select and describe the packet-decoder family, not as the public patch
name. The corresponding internal packet proof for these two matches still
needs a proven identity/fusion path. No HP, combat stats, ranks, basic attacks,
or damage were copied from another match. This is the remaining multi-match
product-readiness blocker, separate from durable hosting and the later
second-machine reproduction.

OE was not needed for this acquisition: GRID supplied exact professional
series identity, paired event files, and replay files for both candidates.

## Additional 16.13 build-matched games: GRID 2970136 games 2 and 3

The same approved professional series supplied two more games from the
Dplus KIA vs Gen.G Esports match set. Their public patch label is **26.14**;
the ROFLs embed the internal 16.13 replay/build family used by the decoder.
They are kept as separate research matches and were never merged with game 1
or with the 2970137 holdout.

| Game | Riot match | Dense frames | Duration | Identity | Research HP | Research combat | Ranks |
|---|---|---:|---:|---|---|---|---|
| 2 | `LOLTMNT01-429309` | 2,443 | 2,441,314 ms | 10/10 exact PUUID, 10 champions | 83 hits, 10/10 heroes ≥2 aligned samples | 10/10 FUR-complete, 1,612 timed samples | 1,737 events, 10/10 heroes, monotonic |
| 3 | `LOLTMNT01-429312` | 2,244 | 2,242,213 ms | 10/10 exact PUUID, 10 champions | 77 hits, 10/10 heroes ≥2 aligned samples | 10/10 FUR-complete, 1,603 timed samples | 1,637 events, 10/10 heroes, monotonic |

Both non-product `--require-live-positions` validations passed. The research
timelines also contain identity-bound overlays: game 2 has 4,717 accepted
basic attacks and 5,282 damage rows; game 3 has 4,788 accepted basic attacks
and 7,323 damage rows. Damage amounts remain unknown where the proven wire
does not provide them.

The product validation was rerun for both matches and failed closed with the
same honest result: `FAIL: product gate: productEligible=false cannot publish`.
This is now a source-boundary blocker, not a missing-match-data blocker:
GRID provides dense positions and same-match HP/combat/rank research evidence,
but the GRID adapter is not an independently fused product source. No product
timeline or public registry entry was written.

The product ingest was also opened for both ROFLs. Inspect completed with
stable 10-player manifests and the correct ROFL hashes/build metadata. A
bounded 2-second Replay API capture probe for game 2 failed closed before any
capture write with `active replay preflight GET failed:
['playback', 'playerlist', 'allgamedata']`. That means the local replay client
was not serving an active replay during this probe; it does not authorize
substituting GRID positions into the product path. The machine-readable receipt
is `artifacts/pro-grid/2970136/research/product-readiness-summary.json`. The
product ingest command now carries the player-facing label explicitly:
`python3 scripts/rofl_ingest.py inspect <PLATFORM>-<matchCode>.rofl --force
--public-patch 26.14`. The resulting manifests record `patch` and
`publicPatch` as `26.14`, while retaining the embedded replay patch (`16.13`)
and full build (`16.13.790.6961`) as separate fields.

Artifact receipts for the two games:

- raw ROFL game 2: `8717b367b80079024033b235db8f09aa29b95c1ee48f128b1004b37b8aac7d08`
- raw ROFL game 3: `5a5d2435a29f9c517692953f8edf8d5671d1c2daa4cb91b5512ac22619a73f81`
- raw Riot LiveStats game 2: `89ff1fffb62e448a0f19ee4a27db130043df5e3bc764aaff7b4da36864559350`
- raw Riot LiveStats game 3: `575d9b673e555d5c43645ef3d31c1b18798071e41de6fa32524005a6c18fee7c`
- research rfc461 game 2: `25e3fd8bf6b4be019ea025ef8c890068a3094133f51cfe1fa12ce28ba0acc1d1`
- research rfc461 game 3: `4efecba51a919123583acd4a7b1114015640c221dabee69003c1d8dfe24b461c`
- research timeline game 2: `d717bc942f8446bfde38472818f790030c406ea76c351427a0d3fee8930bbf60`
- research timeline game 3: `4765b3f4098eda4891b1d2f470b74dbf79f8c461e2e1d0276744cd4c84b4d695`
- identity receipts: game 2 `205649fbcc3c516f1f23b068c84f7db67e72fd67b56529d49a5c2bd6cb728503`, game 3 `581249f8060957d6ed9812e6ec6a70ddb5c96782d4ee5af5c36c261227d96995`
- HP research candidates: game 2 `c292e18bdbb5aa3175c162b0395d5cff90a03bdfebad1724ea6021b4c099f094`, game 3 `449c734b5581e8cffffe1208e760d9ce5a2ddb67d6f7da5f756b7e12b052fafa`
- combat research receipts: game 2 `b8f626d3bb4ae98054bc7bed5b201fb8cec647b3c9873942059efe7652617f37`, game 3 `2d4aab696475b9a14efbabc043b9aa6a80c0b1e39ed26dab306c2b8ed3aeda73`
- rank receipts: game 2 `5456470fcc37398f2a2a7b2f24759eb37ea6bd0f0b7e47a9422338a022878264`, game 3 `4b6f313d002279cb3552f5593bdade9a6e5aebd76378b0ad5366e0c46836c0a5`

The repaired pro-series manifest now records GRID series `2970136` as paired
with all three Riot LiveStats files and the three ROFL files. OE was not
needed for this expansion.

## Existing held-out control: GRID 2970137 game 1

## Additional 16.13 build-match: GRID 2970136 game 1

The later patch-family check acquired game 1 of GRID series `2970136`,
`LOLTMNT01-428801` (Dplus KIA vs Gen.G Esports). Its ROFL embeds
`16.13.790.6961`. The resilient walker recovers `30,773` chunks and `53`
keyframes with `321` leftover bytes from `30,826` total segments. The official
Windows 16.13 PE receipt already recorded in the repository was restored only
to `/tmp` and hash-checked before decoding:

- PE SHA-256: `4e1dedc91b271abf7b5d769424ec585d72140503bc2494c801bc9c2585595f9f`
- PE size: `34,138,552` bytes
- manifest: `9A4D17E5BC0B96B4`

The build-matched research path now proves all ten CastSpell identity binds
and distinct champions, then emits a correctly game-labeled research overlay:

- identity: `10/10` heroes with samples, `10` distinct champions,
  `aaBridgeReady=true`
- PE-remapped research output: `26,517` basic-attack rows and `97,992`
  damage-carrier rows; the latter still has `damageAmount=null`
- identity-joined GameTimeline overlay: `5,715` basic attacks and `8,198`
  damage rows after rejecting non-hero/unbound net IDs
- research timeline: `2,922` dense stats frames, `2,922` HP/combat/rank
  frames, and all ten participants moving

The R28 emitter was fixed to require an explicit Riot game ID when ROFL
metadata omits it. This run uses `428801`; it no longer silently labels a new
match as the historical default `2970110`.

This remains research-only. The GRID adapter is not an independent product
fuse, emitted damage amounts are absent, and the product validator correctly
fails with `productEligible=false`; no public registry entry was written.

Artifact receipts:

- raw Riot LiveStats: `1ecdb4245a4b39b52f48ee0ef80da69b7b4ccf5dbdadaedbc5127c1ef9aaa745`
- raw GRID events ZIP: `4ebdfa0ddc364ad15de8ec5f876adac52640714cba18c68a2a3d5b8851bc8a76`
- raw ROFL: `a7527b972788a58203650d19c083ca725f1473a28f2faf05ecf6264c1b4b022c`
- research rfc461: `325d81feeceb3df34ef7cb77f3749aec0071b5655b10d4adfaeefa22db100709`
- research timeline: `3c110520747a1ad8596acc01ff23d5d96b026ddd2e82f3aa83841a4d50f3539b`
- research PE-remapped actions: `5bc110f20cd3213519ce31f8046cda15fc5cd4b7f3241e6d4802d94029acac60`

The checkout also contains an earlier professional holdout,
`LOLTMNT01-429386` from GRID series `2970137`. Its local research evidence
proves same-match CastSpell identity and 10/10 per-hero explicit-maximum-HP
coverage. The independent combat fuse is only 9/10: Camille's AD and armor
wire fields remain absent under the proven 16.13 embedded replay/build
decoder. The honest partial fuse keeps Camille unknown and leaves
`calculatorReady=false`; it is not promoted to the product registry and does
not borrow fields from another match.

This holdout narrows the multi-match blocker to the remaining same-match
combat-wire coverage rather than a missing roster or HP source. Evidence is
preserved in `artifacts/rofl/2970137/` and the R29 research notes; it does not
authorize a match-level product claim.

Receipts: raw ROFL SHA-256
`fe2e911ae15d2ac491038209ebceebcf5b069279b233122e396ce86aea281827`;
explicit-maximum-HP hits `63`; heroes with at least two matched HP samples
`10/10`; combat FUR-complete heroes `9/10`.
