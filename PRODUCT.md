# Product

## Register

product

## Users

Internal bookmaker trading-support, quantitative, and model-risk analysts
studying professional live or replayed match state. They work at a desk,
compare fights across timestamps, and need density without chrome. The product
is not marketed to teams, coaches, affiliates, or bettors. Primary glance
target on the main screen is the competitive scoreboard (kills, gold delta,
towers, objectives), then the map.

## Product Purpose

Turn verified game state (map positions, vision, objectives, loadouts) into
auditable fight-strength judgments for private bookmaker research. Success is
reading the scoreboard and map as one instrument, selecting an NvM, sending it
to the calculator without losing context, and exporting the evidence behind the
result.

The current product exposes heuristic model edge, not a calibrated win
probability or market price. Replay-based research is Phase 1. Live desk alerts
and any pricing workflow require later holdout, calibration, and model-risk
gates. See [`ROADMAP.md`](ROADMAP.md).

## Brand Personality

Clean, precise, arxiv, in a warm Anthropic dark with Apple quiet chrome. Research console at night: cream type on charcoal, coral used sparingly, no spectacle.

## Anti-references

- Purple-on-white / indigo SaaS dashboards
- Generic AI “hero + cards + glow” layouts
- Warm cream + terracotta editorial marketing pages
- Broadsheet / newspaper column chrome
- Esports stream overlays as the whole UI language
- Decorative dark-mode neon and multi-layer shadows

## Design Principles

1. **Scoreboard first** — Match state leads; controls and chrome support it.
2. **One instrument** — Map, FoW, timeline, and actions read as a single console, not stacked widgets.
3. **Arxiv calm** — Typography and spacing do the hierarchy; color is semantic (blue/red, live, spotted), not decorative.
4. **Task density** — Prefer information over ornament; every control earns its place.
5. **Familiar product grammar** — Tabs, scrubbers, and buttons behave like trusted tools (Linear/Figma density), not custom novelty.
6. **Evidence before action** — Every judgment can expose its input state, trust boundary, assumptions, and source revision.

## Accessibility & Inclusion

Target WCAG AA contrast on text and controls. Respect `prefers-reduced-motion`. Do not encode critical state in color alone (pair LIVE / spotted / FoW with labels or patterns). Keyboard-reachable primary actions (tab switch, scrub, send fight).
