# Reproducible match bundles

A reproducible match bundle lets another machine fetch and verify the exact
inputs used for replay research:

- the original `.rofl`;
- the canonical rfc461 `.jsonl`;
- the derived timeline `.json`;
- one small manifest containing identity evidence, byte sizes, SHA-256 hashes,
  and direct download URLs.

This is the portable boundary between local replay work and repeatable testing.
It is provider-neutral: GitHub Releases, object storage, a static HTTPS host, or
another service can hold the bytes.

The design is informed by the
[GRU minion-wave project](https://jperezlafuente.github.io/GRU-project/):
old-patch replay availability, raw-to-processed lineage, and exact match-time
alignment matter as much as the final model output.

## Trust boundary

`scripts/repro_bundle.py` only creates a manifest when all three files pass the
same-match check:

1. the ROFL filename and trailing metadata agree on Riot platform and game ID;
2. the rfc461 `game_info` row has the same platform and game ID;
3. the ROFL and JSONL contain the same ten PUUIDs;
4. the ROFL, JSONL, and timeline contain the same ten champions;
5. every embedded replay/Data Dragon patch label agrees; when the timeline
   carries a player-facing `publicPatch`, that label is recorded separately.

The manifest then pins every file by byte size and SHA-256.

In a manifest, `match.publicPatch` and `match.patch` are the player-facing
patch label. `match.embeddedPatch` and `match.build` preserve the Riot replay
and Data Dragon source labels. For the current release, the public patch is
`26.14`; an embedded `16.13` or `16.14` value is source/build metadata, not a
different current public patch.

This proves bundle integrity and same-match identity. It does **not** prove that
the timeline is calculator-ready, calibrated, licensed for publication, or
eligible for `public/data/matches/`. Those remain separate validators and
authority decisions.

Bundles are fixed to professional competitive data. Scrims, practice games,
tryouts, and private feeds are out of scope.

## Create a local manifest

Use a ROFL named with its real Riot identity:
`<PLATFORM>-<matchCode>.rofl`.

```bash
npm run repro:bundle -- create \
  --rofl artifacts/pro-grid/BR1-1234567890.rofl \
  --jsonl artifacts/pro-grid/1234567890/events.rfc461.jsonl \
  --json artifacts/pro-grid/1234567890/timeline.json \
  --out artifacts/pro-grid/1234567890/repro-bundle.json
```

Without URLs, the manifest is complete for local verification but reports
`remoteReady: false`.

## Add cloud URLs

When the three artifacts are available under one direct HTTPS directory:

```bash
npm run repro:bundle -- create \
  --rofl artifacts/pro-grid/BR1-1234567890.rofl \
  --jsonl artifacts/pro-grid/1234567890/events.rfc461.jsonl \
  --json artifacts/pro-grid/1234567890/timeline.json \
  --url-base https://downloads.example.org/matches/BR1-1234567890/ \
  --out artifacts/pro-grid/1234567890/repro-bundle.json
```

If a host gives each file an unrelated URL, provide explicit overrides:

```bash
npm run repro:bundle -- create \
  --rofl artifacts/pro-grid/BR1-1234567890.rofl \
  --jsonl artifacts/pro-grid/1234567890/events.rfc461.jsonl \
  --json artifacts/pro-grid/1234567890/timeline.json \
  --artifact-url replay_rofl=https://host.example/replay-download \
  --artifact-url canonical_rfc461_jsonl=https://host.example/events-download \
  --artifact-url timeline_json=https://host.example/timeline-download \
  --out artifacts/pro-grid/1234567890/repro-bundle.json
```

Upload `repro-bundle.json` after the three artifacts. The URLs must be direct
downloads over HTTPS. A browser-only folder page is not a direct artifact URL.
Never put a GRID key, cloud token, cookie, or signed private credential in the
manifest. Time-limited signed URLs also make the bundle non-durable and should
be avoided.

## Fetch on another machine

```bash
npm run repro:bundle -- fetch \
  --manifest https://downloads.example.org/matches/BR1-1234567890/repro-bundle.json \
  --out artifacts/repro-bundles/BR1-1234567890
```

Downloads use temporary files and move into place only after the declared size
has been received. The command then rechecks all hashes and reruns the
same-match identity checks locally.

Existing matching files are reused. Existing non-matching files are never
overwritten.

For a product-ready hosted bundle, the repository also provides one command
that fetches the manifest, reruns the product calculator gate, requires the
identity-bound basic-attack timeline, and builds the app:

```bash
npm run repro:hosted -- \
  --manifest https://downloads.example.org/matches/BR1-1234567890/repro-bundle.json \
  --out artifacts/repro-bundles/BR1-1234567890
```

This command is a reproducibility aid, not a substitute for an independent
machine. The second-machine evidence must still record the machine, checkout,
and successful command output.

## Verify an existing local copy

```bash
npm run repro:bundle -- verify \
  --manifest artifacts/repro-bundles/BR1-1234567890/repro-bundle.json \
  --root artifacts/repro-bundles/BR1-1234567890
```

A successful result includes:

```json
{
  "ok": true,
  "schema": "lol-strength-repro-bundle-v1",
  "sameMatch": "verified"
}
```

## Recommended hosting workflow

1. Keep raw artifacts out of Git.
2. Upload immutable, access-approved files to the chosen host.
3. Create the manifest from the exact uploaded local bytes.
4. Upload the manifest last.
5. Test the public manifest URL from a clean machine.
6. Record the manifest URL in the experiment or PR that consumes it.

The machine-readable contract is
[`docs/schemas/repro-bundle-v1.schema.json`](schemas/repro-bundle-v1.schema.json).
The repository validator remains the authoritative implementation because it
also checks cross-file identity and content, which JSON Schema alone cannot do.
