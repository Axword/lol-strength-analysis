# Durable reproduction hosting: calculator-ready 2970132 game 1

This record now distinguishes the original upload from the corrected
replacement. The player-facing patch is `26.14`. The embedded replay/Data
Dragon label is `16.13` / `16.13.790.6961`; that source label must not be shown
as the current public patch.

## Existing hosted manifest (superseded)

- bundle ID: `loltmnt01-428534-5aece0a16d9eeb94`
- manifest: https://wghjyoun15ojykmg.public.blob.vercel-storage.com/lol-strength-analysis/repro/2970132/repro-bundle.g1.calculator-ready.json
- access: the public Blob objects remain readable; no Vercel credential is
  embedded in the manifest

This upload is not the current deliverable. Its manifest reports embedded
`patch: 16.13` and has no `publicPatch`. The ordinary bundle fetch still
verifies its hashes and same-match identity, but the portable product entry
point correctly rejects it for the current public patch.

The original upload contained these content-addressed artifacts:

| Artifact | Bytes | SHA-256 |
|---|---:|---|
| `LOLTMNT01-428534.rofl` | 21,651,328 | `303c9ff1b2fea35f53a8a14697d6daa7303b4159de4a6fbc9716d6147ca9b61c` |
| `events.g1.calculator-ready.rfc461.jsonl` | 115,241,489 | `81bc5e3430a59b6600fb5e06292ae1ce73cf466cc26155e0b18af02b92affa5c` |
| `timeline.g1.calculator-ready.json` | 9,497,431 | `17219d85cc19470d711238e4c788a56346b9eeb14dd1179ca8100e8b1e196b74` |

## Corrected durable replacement

- bundle ID: `loltmnt01-428534-74f2861f2bb0bbce`
- public patch: `26.14`
- embedded replay patch/build: `16.13` / `16.13.790.6961`
- manifest:
  `https://97gks2fobqkgppwx.public.blob.vercel-storage.com/lol-strength-analysis/repro/2970132/v2/repro-bundle.g1.calculator-ready.json`
- canonical JSONL object:
  `https://97gks2fobqkgppwx.public.blob.vercel-storage.com/lol-strength-analysis/repro/2970132/v2/events.g1.calculator-ready.public-26.14.rfc461.jsonl`
- timeline object:
  `https://97gks2fobqkgppwx.public.blob.vercel-storage.com/lol-strength-analysis/repro/2970132/v2/timeline.g1.calculator-ready.public-26.14.json`
- ROFL object:
  `https://97gks2fobqkgppwx.public.blob.vercel-storage.com/lol-strength-analysis/repro/2970132/v2/LOLTMNT01-428534.rofl`
- corrected canonical JSONL: 115,241,489 bytes,
  `68fa93016d8a5e775d13603611541b3371f207536b000e999cd293a99d3a6af9`
- corrected timeline: 9,497,477 bytes,
  `060b4b2b992ceb87d9b39b8f2ed4a7a0cd17d13b9b543d8e1e2951e2fd9e5bb9`

The corrected manifest was uploaded after local verification. Its local
manifest and timeline pass:

```bash
npm run repro:bundle -- verify \
  --manifest /tmp/repro-bundle-public-26.14.json \
  --root /tmp/lol-strength-analysis-remote-fetch-fHsVRU

python3 scripts/validate-rofl-pipeline.py --product \
  --require-calculator-ready \
  --calculator-ready-policy living_post_seed_v1 \
  --require-aa-timeline \
  --jsonl /tmp/lol-strength-analysis-remote-fetch-fHsVRU/events.g1.calculator-ready.public-26.14.rfc461.jsonl \
  --timeline /tmp/lol-strength-analysis-remote-fetch-fHsVRU/timeline.g1.calculator-ready.public-26.14.json
```

The product receipt reports `calculatorReady=true`, `strictAllFrame=false`,
and 3,479 identity-bound basic attacks across all ten participants.

## Verification of the corrected durable upload

The exact portable entry point was run from a fresh directory against the
public Vercel Blob manifest:

```bash
npm run repro:hosted -- \
  --manifest https://97gks2fobqkgppwx.public.blob.vercel-storage.com/lol-strength-analysis/repro/2970132/v2/repro-bundle.g1.calculator-ready.json \
  --out /tmp/lol-strength-vercel-v2-build-retry
```

The public manifest downloaded all three artifacts, passed SHA-256 and
same-match verification, and passed the product gate with
`calculatorReady=true`, `living_post_seed_v1`, `strictAllFrame=false`, and
3,479 identity-bound attacks across all ten participants. The app build also
passed from that fresh hosted transfer. The first build-enabled attempt hit a
transient ROFL read timeout; a new-directory retry completed successfully.

The exact `repro:hosted` entry point was also exercised against a fresh
loopback HTTP host with the corrected manifest; fetch, hash verification,
same-match verification, and the product gate all passed.

## Verification of the original upload

The local canonical-name staging check passed with
`npm run repro:bundle -- verify --manifest ... --root ...`.

The remote clean-directory check then ran:

```bash
npm run repro:bundle -- fetch \
  --manifest https://wghjyoun15ojykmg.public.blob.vercel-storage.com/lol-strength-analysis/repro/2970132/repro-bundle.g1.calculator-ready.json \
  --out /tmp/lol-strength-analysis-remote-fetch
```

It downloaded all three artifacts into a fresh directory and passed the
same-match and SHA-256 checks, producing bundle ID
`loltmnt01-428534-5aece0a16d9eeb94`. With the corrected portable entry point,
the same URL then fails closed with:

```text
fetched reproduction manifest does not carry the expected public patch '26.14': patch='16.13', publicPatch=None
```

The portable second-machine command is now:

```bash
npm run repro:hosted -- \
  --manifest https://97gks2fobqkgppwx.public.blob.vercel-storage.com/lol-strength-analysis/repro/2970132/v2/repro-bundle.g1.calculator-ready.json \
  --out artifacts/repro-bundles/LOLTMNT01-428534
```

It fetches the bundle, reruns the product gate with
`living_post_seed_v1`, requires the identity-bound basic-attack timeline, and
builds the app.

The corrected replacement was uploaded on 2026-07-31 through the existing
`scryglass` project’s encrypted production Blob credentials. This changed Blob
objects only; no Vercel application deployment or public match-registry entry
was changed.

This is a fresh hosted transfer from the current machine, not the required
second-machine reproduction. The bundle remains research evidence:
same-match integrity does not establish calibration, publication authority, or
betting eligibility.

## Vercel team access check

A fresh Vercel team listing, including the connected Vercel integration,
exposes only the authenticated personal scope `marimari00s-projects`; the
host/team scope is not available to this session. Team membership remains
unconfirmed, but the accessible `scryglass` project’s existing Blob store was
sufficient for this isolated `v2` upload.
