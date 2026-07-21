# Design System

## Visual Theme
Late-night research console. Warm Anthropic charcoal with Apple’s quiet chrome: scoreboard-led, dense, no spectacle. Dark because the desk is dim and the work is focus, not because “tools are dark.”

## Color
- Strategy: Restrained
- Neutrals: warm near-black elevations (`--bg` → `--panel` → `--surface` → `--elevated`), cream text (`--ink`), soft secondary (`--muted`)
- Hairlines: white at ~10–18% (`--line`, `--line-strong`), never hard gray slabs
- Accent: coral-amber (`--accent`) ≤10% for primary CTA, focus, active tool (xH)
- Semantic only: `--blue` / `--red` teams, `--live` objectives, `--warn` gold lead / spotted
- Avoid: neon, purple SaaS, cold blue-black gamer dark, gold-on-black esports chrome

## Typography
- UI: system stack (Apple-like clarity)
- Data / clock / gold: IBM Plex Mono
- No display sports fonts; hierarchy via weight and size only

## Components
- App shell: slim header, underline tabs in cream
- Match console: one bordered instrument; internal hairlines only
- Primary button: cream fill on dark (`--ink` on `--bg`) or coral for Send
- Ghost: transparent + hairline
- Tonal: accent wash for active tools
- Radius: 8px console, 6px controls (Apple soft, not pill)

## Layout
Unchanged structure: scoreboard → scrubber → toolbar → map|roster as one console

## Motion
150ms state only; honor `prefers-reduced-motion`

## Do not
- Light paper scoreboard on a dark shell (or the reverse)
- Glow, multi-shadow, glass blur as decoration
- Side-stripe list accents
- Saturated full-bleed team gradients
