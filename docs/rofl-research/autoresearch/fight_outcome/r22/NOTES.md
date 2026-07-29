# R22 NOTES — Camille Q wire

## What changed

`src/data/generatedGameChamps.ts` Camille Q was `damage: () => []` (overrides Meraki).
Wired wiki-proven first cast:

- `execution.attackReset` + `empoweredAuto` (wiki: both casts reset AA)
- packet `AD × (1 + 0.20..0.40)` physical (wiki bonus %AD + base AA, Darius W pattern)
- `utility.selfMsBuff` 0.25..0.45 (wiki bonus MS)

## Evidence

| Source | Result |
|--------|--------|
| lolwiki Camille.Q | Bonus Physical 20–40% AD; MS 25–45%; attack reset |
| Meraki kit | Same %AD ratios (was emptied by GAME stub) |
| PE strings (r04) | PrecisionProtocol=0, CamilleQ=0 — **no PE coeffs** |
| 2970110 slim | Camille pid10, **84** Q casts; c1 window **4** Q |
| 2970132 Path1 | Camille pid10, **71** Q casts; S0 killers Galio/Olaf |

## FA impact (Path1 2970132 S0)

- `fightAgreement=0.2946`, `fightPassRate=0.1667` (n=6)
- Windows: Galio→Trundle, Olaf→Trundle, Olaf→Camille — **no Camille killer**
- Q wire cannot move this FA; gate_action still ignores planner/kit-slot packets for mark damage
- FA ≠ odds

## Still open (sharper blockers)

1. PE cannot supply Q coeffs / recast true-mix — wiki first-cast only
2. Path1 S0 windows need Camille-as-killer (or F9 VOD windows) for Q FA lever
3. gate_action pulse ≠ timed kit plan (R11 sharpener stands)

## Isolation

- Worktree: `/Users/river/.codex/worktrees/rofl-fo-r22` branch `adv/fo-r22-camille-q-wire`
- `never_edited_parent` code: true (docs mirrored to parent fight_outcome/r22 only)
