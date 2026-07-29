# Product Roadmap

## Product decision

As of 2026-07-29, LoL Strength Analysis is being built for an internal
bookmaker research desk. The primary users are trading-support, quantitative,
and model-risk analysts reviewing professional League of Legends matches.

The product is not marketed to teams, coaches, affiliates, or bettors. The
first commercial shape is a private replay-based research pilot. Live desk
alerts and market integration come later.

## Current output contract

The app currently produces a heuristic Blue or Red model edge from match state
and combat pressure. It does not produce a calibrated win probability, fair
price, market line, or recommendation.

Every product phase must preserve these rules:

- Unknown replay fields remain unknown and block dependent actions.
- Model edge is labeled as an uncalibrated research score.
- Research agreement gates are validation evidence, not price confidence.
- No market-facing claim ships without holdout, calibration, and model-risk
  review.
- GRID use remains limited to professional series. Scrims, practice games,
  tryouts, and private scrim feeds are out of scope.

## Primary workflow

1. Load a verified professional match or replay bundle.
2. Scrub to the decision timestamp.
3. Read scoreboard, objectives, positions, vision, and source coverage.
4. Select the living combatants.
5. Run the modeled fight.
6. Inspect model edge, strength bands, action timing, trust reasons, and
   assumptions.
7. Export an evidence record for independent review or rerun.

## Delivery phases

### Phase 0: Reproducible foundation

Status: in progress.

Deliverables:

- A clean build and CI baseline.
- Provider-neutral match bundles with checksums and provenance.
- Fail-closed replay validation for identity, positions, HP, combat stats, and
  ability ranks.
- A documented product boundary between research outputs and market prices.

Exit gate:

- A second machine can fetch one approved bundle, verify it, build the app, and
  reproduce the same analysis input without private local paths.

### Phase 1: Private bookmaker research pilot

Status: started.

Deliverables:

- Bookmaker-specific product positioning and navigation copy.
- An analysis evidence record containing the selected state, model result,
  trust classification, assumptions, and build revision.
- A provenance and readiness summary for every loaded match.
- A research queue for saved timestamps and analyst notes.
- A compact comparison view for two evidence records from the same match.

Exit gate:

- An internal analyst can review a professional match, export a judgment, and
  have another analyst reproduce and challenge it without oral context.

### Phase 2: Evaluation and reliability

Status: gated.

Deliverables:

- Frozen evaluation definitions for fight outcome, action replay, and
  calculator readiness.
- Match-, series-, patch-, league-, and champion-held-out reporting.
- Calibration diagnostics that are separate from directional agreement.
- Explicit coverage and abstention reporting.
- Regression review for model and data changes.

Exit gate:

- Holdout behavior is stable enough for model-risk review, and every reported
  metric has a declared estimand, denominator, and exclusion policy.

### Phase 3: Market workflow integration

Status: locked until Phase 2.

Deliverables:

- Read-only import of the bookmaker's internal line and timestamp.
- Side-by-side model-edge and market-movement research.
- Decision logs, analyst overrides, and audit history.
- Role-based access for trading-support, quant, and model-risk users.

Exit gate:

- The desk can study model-versus-market divergence without the app generating
  or publishing a price.

### Phase 4: Calibrated pricing research

Status: locked until Phase 3 evidence is approved.

Deliverables:

- A separately identified pricing estimand.
- Calibrated probabilities with reliability diagrams, uncertainty intervals,
  leakage checks, and temporal holdouts.
- Champion, patch, league, and data-coverage abstention policies.
- Independent approval criteria for any fair-price comparison.

Exit gate:

- Model-risk review authorizes a bounded internal pricing experiment. Until
  then, the product continues to expose model edge only.

### Phase 5: Live desk pilot

Status: future.

Deliverables:

- Low-latency professional-match ingest with source-health monitoring.
- Alerting only where data and model coverage pass the approved live policy.
- Incident replay, late-data handling, and complete audit logs.
- Human confirmation before any downstream trading action.

Exit gate:

- A time-boxed internal pilot demonstrates reliable operations, honest
  abstention, and reversible use.

## Next three iterations

1. Ship positioning, this roadmap, and analysis evidence export.
2. Prove the clean-host reproduction path with one approved professional match.
3. Add match-level provenance/readiness and a saved research queue.

## Decision log

- 2026-07-29: Primary buyer changed from a broad analyst/player audience to an
  internal bookmaker research desk.
- 2026-07-29: Phase 1 confirmed as replay-based research. Live trading support
  is deferred.
- 2026-07-29: Current product output remains heuristic model edge. Calibrated
  price comparison requires later evidence and approval.
