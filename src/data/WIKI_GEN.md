# LoL wiki / game-knowledge ingest

## What “entire wiki” means here

We snapshot **complete structured game data** used to drive every calculator
interaction, not a subset:

| Source | Contents |
|--------|----------|
| Data Dragon | All items, all runes (62), all summoner spells, patch version |
| Meraki Analytics | Item passives/actives, **all 171 champion kits** with full ability leveling |
| Community Dragon | Perk metadata |

On disk after `npm run ingest:lolwiki`:

```
public/data/lolwiki/
  meta.json
  items-full.json          # 700+ items + Meraki passives
  runes-full.json          # every rune incl. Unsealed Spellbook rules
  summoners-full.json
  champions-index.json
  champions-full.json      # ~13MB Meraki — every champion ability detail
  perks-cdragon.json
src/data/generated/
  allItems.ts / allRunes.ts / allSummoners.ts / championIndex.ts
```

## Policies

1. **Never skip utility-only abilities** (Nasus W, Zilean E, …) — zero base
   damage still emits a `utility` block.
2. **Lee Sin Q** = one cast, multi-packet (Sonic Wave + Resonating Strike).
3. **Unsealed Spellbook (8360)** is a first-class keystone with swap CD rules,
   unique-summoner constraint, and loadout `spellbookState` / `summonerSpells`.
4. Unknown timeline item/rune ids must **resolve or warn**, never silently
   become a fake “None” keystone when a Riot id exists.

# Calculator catalog: Summoner's Rift only

`ALL_ITEMS` / the fighter picker only includes items with DDragon
`maps["11"] === true` (Summoner's Rift). ARAM (12), Arena (30), TFT, and
removed/quest items are kept in `items-full.json` for archive but **not**
shipped into the combat UI catalog.
