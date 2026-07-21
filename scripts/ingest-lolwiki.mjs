#!/usr/bin/env node
/**
 * Ingest the full LoL knowledge base from:
 *   - Data Dragon (items, runes, summoners, version)
 *   - Meraki Analytics (item passives/actives, full champion kits)
 *   - Community Dragon (perk metadata)
 *
 * This is the canonical "entire game data" snapshot used by the calculator.
 * Re-run: `npm run ingest:lolwiki`
 *
 * NEVER drop utility-only abilities, runes, or items — zero damage ≠ skip.
 */
import { createWriteStream } from 'node:fs'
import { mkdir, writeFile, readFile } from 'node:fs/promises'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { pipeline } from 'node:stream/promises'
import { Readable } from 'node:stream'

const __dirname = dirname(fileURLToPath(import.meta.url))
const ROOT = join(__dirname, '..')
const WIKI = join(ROOT, 'public/data/lolwiki')
const GEN = join(ROOT, 'src/data/generated')

async function fetchJson(url) {
  const res = await fetch(url)
  if (!res.ok) throw new Error(`${res.status} ${url}`)
  return res.json()
}

async function fetchToFile(url, dest) {
  const res = await fetch(url)
  if (!res.ok) throw new Error(`${res.status} ${url}`)
  await pipeline(Readable.fromWeb(res.body), createWriteStream(dest))
}

function flatStat(block, key) {
  const s = block?.[key]
  if (!s) return 0
  return Number(s.flat || 0) || 0
}

function pctStat(block, key) {
  const s = block?.[key]
  if (!s) return 0
  return Number(s.percent || 0) || 0
}

function categorizeItem(name, tags = [], gold = 0) {
  const t = new Set(tags.map((x) => String(x).toLowerCase()))
  const n = name.toLowerCase()
  if (t.has('boots') || n.includes('boot') || n.includes('greaves') || n.includes('treads') || n.includes('shoes')) {
    return 'boots'
  }
  if (gold > 0 && gold <= 500 && (n.includes("doran") || n.includes(' Cull') || n.includes('cull') || n.includes('shield') && gold < 500)) {
    return 'starter'
  }
  if (t.has('tank') || t.has('aura') || n.includes('thornmail') || n.includes('randuin') || n.includes('force of nature')) {
    return 'tank'
  }
  if (t.has('fighter') || t.has('life steal') || n.includes('trinity') || n.includes('sundered') || n.includes('eclipse')) {
    return 'fighter'
  }
  if (t.has('mage') || t.has('spell damage') || n.includes('rabadon') || n.includes('ludens') || n.includes('liandry') || n.includes('shadowflame')) {
    return 'mage'
  }
  return 'damage'
}

/** DDragon map ids: 11 = Summoner's Rift. Exclude ARAM(12), Arena(30), TFT/other. */
const SUMMONERS_RIFT_MAP_ID = '11'

function isSummonersRiftItem(maps) {
  if (!maps || typeof maps !== 'object') return false
  return maps[SUMMONERS_RIFT_MAP_ID] === true || maps[11] === true
}

function ddragonItemStats(stats = {}) {
  const out = {}
  if (stats.FlatPhysicalDamageMod) out.ad = stats.FlatPhysicalDamageMod
  if (stats.FlatMagicDamageMod) out.ap = stats.FlatMagicDamageMod
  if (stats.FlatHPPoolMod) out.hp = stats.FlatHPPoolMod
  if (stats.FlatArmorMod) out.armor = stats.FlatArmorMod
  if (stats.FlatSpellBlockMod) out.mr = stats.FlatSpellBlockMod
  if (stats.PercentAttackSpeedMod) out.attackSpeed = stats.PercentAttackSpeedMod
  if (stats.FlatCritChanceMod) out.critChance = stats.FlatCritChanceMod
  if (stats.FlatMovementSpeedMod) out.movespeed = stats.FlatMovementSpeedMod
  if (stats.PercentMovementSpeedMod) out.movespeed = (out.movespeed || 0) // percent handled separately
  if (stats.FlatMPPoolMod) out.mana = stats.FlatMPPoolMod
  // Percent armor pen / lethality often missing on ddragon — filled from Meraki
  return out
}

function merakiItemStats(mstats = {}) {
  const out = {}
  const ad = flatStat(mstats, 'attackDamage')
  const ap = flatStat(mstats, 'abilityPower')
  const hp = flatStat(mstats, 'health')
  const armor = flatStat(mstats, 'armor')
  const mr = flatStat(mstats, 'magicResistance')
  const as = pctStat(mstats, 'attackSpeed')
  const crit = pctStat(mstats, 'criticalStrikeChance')
  const msFlat = flatStat(mstats, 'movespeed') || flatStat(mstats, 'movementSpeed')
  const lethality = flatStat(mstats, 'lethality') || flatStat(mstats, 'armorPenetration')
  const armorPenPct = pctStat(mstats, 'armorPenetration')
  const magicPenFlat = flatStat(mstats, 'magicPenetration')
  const magicPenPct = pctStat(mstats, 'magicPenetration')
  const ah = flatStat(mstats, 'abilityHaste') || flatStat(mstats, 'cooldownReduction')
  const omni = pctStat(mstats, 'omnivamp') || pctStat(mstats, 'lifesteal')
  if (ad) out.ad = ad
  if (ap) out.ap = ap
  if (hp) out.hp = hp
  if (armor) out.armor = armor
  if (mr) out.mr = mr
  if (as) out.attackSpeed = as / 100
  if (crit) out.critChance = crit / 100
  if (msFlat) out.movespeed = msFlat
  if (lethality) out.lethality = lethality
  if (armorPenPct) out.armorPenPercent = armorPenPct / 100
  if (magicPenFlat) out.magicPenFlat = magicPenFlat
  if (magicPenPct) out.magicPenPercent = magicPenPct / 100
  if (ah) out.abilityHaste = ah
  if (omni) out.omnivamp = omni / 100
  return out
}

function slugify(name) {
  return String(name)
    .normalize('NFKD')
    .replace(/[^\w\s-]/g, '')
    .trim()
    .replace(/\s+/g, '')
    .replace(/^./, (c) => c.toLowerCase())
}

/** Hand-authored combat models keyed by riot perk id — rest still catalogued. */
function keystoneCombatModel(riotId, key) {
  const models = {
    8112: 'electrocute',
    8128: 'darkHarvest',
    9923: 'hailOfBlades',
    8005: 'pta',
    8008: 'lethalTempo',
    8021: 'fleetFootwork',
    8010: 'conqueror',
    8214: 'aery',
    8229: 'comet',
    8230: 'phaseRush',
    8437: 'grasp',
    8439: 'aftershock',
    8465: 'guardian',
    8351: 'glacialAugment',
    8360: 'spellbook',
    8369: 'firstStrike',
  }
  return models[riotId] || null
}

async function main() {
  await mkdir(WIKI, { recursive: true })
  await mkdir(GEN, { recursive: true })

  console.log('Resolving patch…')
  const versions = await fetchJson('https://ddragon.leagueoflegends.com/api/versions.json')
  const patch = versions[0]
  console.log('Patch', patch)

  const [
    ddragonItems,
    ddragonRunes,
    ddragonSummoners,
    merakiItems,
  ] = await Promise.all([
    fetchJson(`https://ddragon.leagueoflegends.com/cdn/${patch}/data/en_US/item.json`),
    fetchJson(`https://ddragon.leagueoflegends.com/cdn/${patch}/data/en_US/runesReforged.json`),
    fetchJson(`https://ddragon.leagueoflegends.com/cdn/${patch}/data/en_US/summoner.json`),
    fetchJson('https://cdn.merakianalytics.com/riot/lol/resources/latest/en-US/items.json'),
  ])

  console.log('Downloading Meraki champions (full kits)…')
  const champsPath = join(WIKI, 'champions-full.json')
  await fetchToFile(
    'https://cdn.merakianalytics.com/riot/lol/resources/latest/en-US/champions.json',
    champsPath,
  )

  console.log('Downloading CDragon perks…')
  await fetchToFile(
    'https://raw.communitydragon.org/latest/plugins/rcp-be-lol-game-data/global/default/v1/perks.json',
    join(WIKI, 'perks-cdragon.json'),
  )

  // ——— Items ———
  const itemsFull = {}
  for (const [id, it] of Object.entries(ddragonItems.data)) {
    const meraki = merakiItems[id] || merakiItems[Number(id)]
    const stats = {
      ...ddragonItemStats(it.stats),
      ...(meraki ? merakiItemStats(meraki.stats) : {}),
    }
    const passives = (meraki?.passives || []).map((p) => ({
      name: p.name || null,
      unique: !!p.unique,
      effects: p.effects || p.description || null,
      description: typeof p === 'object' ? p.description || null : null,
    }))
    const active = meraki?.active
      ? {
          name: meraki.active.name || null,
          effects: meraki.active.effects || meraki.active.description || null,
        }
      : null

    const maps = it.maps || {}
    itemsFull[id] = {
      id,
      name: it.name,
      gold: it.gold?.total ?? 0,
      purchasable: !!it.gold?.purchasable,
      into: it.into || [],
      from: it.from || [],
      tags: it.tags || [],
      maps,
      onSummonersRift: isSummonersRiftItem(maps),
      description: it.description || '',
      plaintext: it.plaintext || '',
      stats,
      passives,
      active,
      category: categorizeItem(it.name, it.tags, it.gold?.total ?? 0),
      icon: `https://ddragon.leagueoflegends.com/cdn/${patch}/img/item/${id}.png`,
    }
  }

  await writeFile(join(WIKI, 'items-full.json'), JSON.stringify(itemsFull))

  // Calculator catalog: Summoner's Rift only (exclude ARAM / Arena / TFT / removed)
  const itemsSr = Object.fromEntries(
    Object.entries(itemsFull).filter(([, it]) => it.onSummonersRift),
  )
  await writeFile(join(WIKI, 'items-summoners-rift.json'), JSON.stringify(itemsSr))
  console.log(
    'Items',
    Object.keys(itemsFull).length,
    'total;',
    Object.keys(itemsSr).length,
    'on Summoner\'s Rift (map 11)',
  )

  // ——— Runes ———
  const runesFull = {}
  const riotIdToSlug = {}
  for (const tree of ddragonRunes) {
    for (let slotIndex = 0; slotIndex < tree.slots.length; slotIndex++) {
      const slot = tree.slots[slotIndex]
      for (const rune of slot.runes) {
        const slug = slugify(rune.key || rune.name)
        const combatModel = keystoneCombatModel(rune.id, rune.key)
        const entry = {
          id: String(rune.id),
          slug,
          riotId: rune.id,
          key: rune.key,
          name: rune.name,
          tree: tree.name,
          treeKey: tree.key,
          slotIndex,
          isKeystone: slotIndex === 0,
          shortDescription: rune.shortDesc || '',
          longDescription: rune.longDesc || '',
          icon: rune.icon
            ? `https://ddragon.leagueoflegends.com/cdn/img/${rune.icon}`
            : null,
          combatModel,
          // Unsealed Spellbook — wiki/Meraki specifics
          spellbook:
            rune.id === 8360
              ? {
                  kind: 'unsealed_spellbook',
                  // Swap CD starts high and drops toward a floor as you swap/cast.
                  initialSwapCooldownSec: 300,
                  minSwapCooldownSec: 60,
                  swapCooldownReductionOnSummonerCastSec: 25,
                  // You may not hold two of the same summoner; Smite has unique rules in ARAM/SR.
                  uniqueSummonersOnly: true,
                  replacesOneSummonerSlot: true,
                  // Offer pool rotates through unused summoners each swap.
                  offerCount: 2,
                  notes: [
                    'Gain a new summoner spell periodically; swapping replaces one equipped spell.',
                    'Using a summoner spell reduces the remaining Spellbook swap cooldown.',
                    'Cannot equip two copies of the same summoner spell.',
                    'Smite gained via Spellbook does not grant jungle item progress the same way as starting Smite (mode-dependent).',
                    'Ultimate Spellbook / Arena modes have separate rules — SR Rift uses classic Unsealed Spellbook.',
                  ],
                }
              : undefined,
        }
        runesFull[entry.id] = entry
        riotIdToSlug[rune.id] = slug
        riotIdToSlug[slug] = slug
        if (combatModel) riotIdToSlug[combatModel] = slug
      }
    }
  }
  await writeFile(join(WIKI, 'runes-full.json'), JSON.stringify(runesFull, null, 2))
  console.log('Runes', Object.keys(runesFull).length)

  // ——— Summoners ———
  const summonersFull = {}
  for (const [key, sp] of Object.entries(ddragonSummoners.data)) {
    summonersFull[sp.key || key] = {
      id: sp.id || key,
      key: sp.key,
      name: sp.name,
      description: sp.description,
      cooldown: Number(sp.cooldown?.[0] ?? sp.cooldownBurn ?? 0),
      range: Number(sp.range?.[0] ?? 0),
      modes: sp.modes || [],
      icon: `https://ddragon.leagueoflegends.com/cdn/${patch}/img/spell/${sp.id || key}.png`,
    }
  }
  await writeFile(join(WIKI, 'summoners-full.json'), JSON.stringify(summonersFull, null, 2))
  console.log('Summoners', Object.keys(summonersFull).length)

  // Champion index (names + ids) — full kits stay in champions-full.json
  const champs = JSON.parse(await readFile(champsPath, 'utf8'))
  const champIndex = {}
  for (const [id, c] of Object.entries(champs)) {
    champIndex[id] = {
      id: c.id || id,
      key: c.key,
      name: c.name,
      title: c.title,
      roles: c.roles || [],
      positions: c.positions || [],
      attackType: c.attackType,
      resource: c.resource,
      patchLastChanged: c.patchLastChanged,
      abilityNames: {
        P: c.abilities?.P?.[0]?.name,
        Q: c.abilities?.Q?.[0]?.name,
        W: c.abilities?.W?.[0]?.name,
        E: c.abilities?.E?.[0]?.name,
        R: c.abilities?.R?.[0]?.name,
      },
    }
  }
  await writeFile(join(WIKI, 'champions-index.json'), JSON.stringify(champIndex, null, 2))
  console.log('Champions', Object.keys(champIndex).length)

  const meta = {
    patch,
    ingestedAt: new Date().toISOString(),
    sources: {
      ddragon: `https://ddragon.leagueoflegends.com/cdn/${patch}/data/en_US/`,
      meraki: 'https://cdn.merakianalytics.com/riot/lol/resources/latest/en-US/',
      cdragon:
        'https://raw.communitydragon.org/latest/plugins/rcp-be-lol-game-data/global/default/v1/',
    },
    counts: {
      items: Object.keys(itemsFull).length,
      itemsSummonersRift: Object.keys(itemsSr).length,
      runes: Object.keys(runesFull).length,
      keystones: Object.values(runesFull).filter((r) => r.isKeystone).length,
      summoners: Object.keys(summonersFull).length,
      champions: Object.keys(champIndex).length,
    },
    policy: {
      utilityAbilities: 'never-skip-zero-damage',
      leeSinQ: 'single-cast-multi-packet',
      spellbook: 'modeled-as-keystone-with-swap-state',
      items: 'summoners-rift-map-11-only-in-calculator',
    },
  }
  await writeFile(join(WIKI, 'meta.json'), JSON.stringify(meta, null, 2))

  // ——— Generate TypeScript catalogs for the app bundle ———
  const purchasableItems = Object.values(itemsSr).filter(
    (it) => it.purchasable || Object.keys(it.stats).length > 0,
  )

  const itemsTs = `/* AUTO-GENERATED by scripts/ingest-lolwiki.mjs — do not edit */
import type { ItemDefinition } from '../../engine/types'

export const DDRAGON_PATCH = ${JSON.stringify(patch)}

export const ALL_ITEMS: Record<string, ItemDefinition> = {
${purchasableItems
  .map((it) => {
    const stats = JSON.stringify(it.stats)
    const passives = (it.passives || [])
      .map((p) => p.name || '')
      .filter(Boolean)
      .slice(0, 4)
    const desc = passives.length
      ? passives.join('; ')
      : (it.plaintext || '').slice(0, 120)
    return `  '${it.id}': {
    id: '${it.id}',
    name: ${JSON.stringify(it.name)},
    gold: ${it.gold},
    category: '${it.category}',
    stats: ${stats},
    plaintext: ${JSON.stringify(desc)},
  },`
  })
  .join('\n')}
}

export const ALL_ITEM_IDS = Object.keys(ALL_ITEMS)
`

  // Extend ItemDefinition usage - plaintext may not be on type; add optional or strip
  // I'll put plaintext only if we extend type - for now omit plaintext from ItemDefinition
  const itemsTsClean = `/* AUTO-GENERATED by scripts/ingest-lolwiki.mjs — do not edit */
import type { ItemDefinition } from '../../engine/types'

export const DDRAGON_PATCH = ${JSON.stringify(patch)}

export const ALL_ITEMS: Record<string, ItemDefinition> = {
${purchasableItems
  .map((it) => {
    const stats = JSON.stringify(it.stats)
    return `  '${it.id}': {
    id: '${it.id}',
    name: ${JSON.stringify(it.name)},
    gold: ${it.gold},
    category: '${it.category}',
    stats: ${stats},
  },`
  })
  .join('\n')}
}

export const ALL_ITEM_IDS = Object.keys(ALL_ITEMS)
`

  await writeFile(join(GEN, 'allItems.ts'), itemsTsClean)

  const runesTs = `/* AUTO-GENERATED by scripts/ingest-lolwiki.mjs — do not edit */
export interface WikiRune {
  id: string
  slug: string
  riotId: number
  key: string
  name: string
  tree: string
  treeKey: string
  slotIndex: number
  isKeystone: boolean
  shortDescription: string
  longDescription: string
  icon: string | null
  combatModel: string | null
  spellbook?: {
    kind: 'unsealed_spellbook'
    initialSwapCooldownSec: number
    minSwapCooldownSec: number
    swapCooldownReductionOnSummonerCastSec: number
    uniqueSummonersOnly: boolean
    replacesOneSummonerSlot: boolean
    offerCount: number
    notes: string[]
  }
}

export const ALL_RUNES: Record<string, WikiRune> = ${JSON.stringify(runesFull, null, 2)}

export const RUNE_BY_SLUG: Record<string, WikiRune> = Object.fromEntries(
  Object.values(ALL_RUNES).map((r) => [r.slug, r]),
)

export const RUNE_BY_RIOT_ID: Record<number, WikiRune> = Object.fromEntries(
  Object.values(ALL_RUNES).map((r) => [r.riotId, r]),
)

export const KEYSTONE_RUNES = Object.values(ALL_RUNES).filter((r) => r.isKeystone)

/** Map Riot keystone id → combat slug (and alias old sample-game ids). */
export const KEYSTONE_ID_TO_SLUG: Record<number, string> = {
${Object.values(runesFull)
  .filter((r) => r.isKeystone)
  .map((r) => `  ${r.riotId}: '${r.combatModel || r.slug}',`)
  .join('\n')}
  // legacy aliases used in sample snapshots
  9101: 'pta',
}

export const SLUG_TO_RIOT_ID: Record<string, number> = ${JSON.stringify(
    Object.fromEntries(
      Object.values(runesFull).flatMap((r) => {
        const pairs = [[r.slug, r.riotId]]
        if (r.combatModel && r.combatModel !== r.slug) {
          pairs.push([r.combatModel, r.riotId])
        }
        return pairs
      }),
    ),
    null,
    2,
  )}
`

  await writeFile(join(GEN, 'allRunes.ts'), runesTs)

  const summonsTs = `/* AUTO-GENERATED by scripts/ingest-lolwiki.mjs — do not edit */
export interface WikiSummoner {
  id: string
  key: string
  name: string
  description: string
  cooldown: number
  range: number
  modes: string[]
  icon: string
}

export const ALL_SUMMONERS: Record<string, WikiSummoner> = ${JSON.stringify(summonersFull, null, 2)}

export const SUMMONER_LIST = Object.values(ALL_SUMMONERS)
`

  await writeFile(join(GEN, 'allSummoners.ts'), summonsTs)

  const champIndexTs = `/* AUTO-GENERATED by scripts/ingest-lolwiki.mjs — do not edit */
export const WIKI_CHAMPION_INDEX = ${JSON.stringify(champIndex, null, 2)} as const
export const WIKI_CHAMPION_IDS = Object.keys(WIKI_CHAMPION_INDEX)
`

  await writeFile(join(GEN, 'championIndex.ts'), champIndexTs)

  console.log('Wrote', WIKI)
  console.log('Wrote', GEN)
  console.log(JSON.stringify(meta.counts, null, 2))
}

main().catch((err) => {
  console.error(err)
  process.exit(1)
})
