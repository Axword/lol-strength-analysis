import type { ItemDefinition } from '../engine/types'
import { ALL_ITEMS, DDRAGON_PATCH } from './generated/allItems'
import { GAME_ITEMS } from './generatedGameItems'

/**
 * Merge catalogs without letting the sparse GAME_ITEMS override wipe
 * richer DDragon/Meraki stats (abilityHaste, attackSpeed, etc.).
 */
function mergeItemCatalogs(
  base: Record<string, ItemDefinition>,
  overlay: Record<string, ItemDefinition>,
): Record<string, ItemDefinition> {
  const out: Record<string, ItemDefinition> = { ...base }
  for (const [id, item] of Object.entries(overlay)) {
    const prev = out[id]
    if (!prev) {
      out[id] = item
      continue
    }
    out[id] = {
      ...prev,
      ...item,
      // Prefer complete stat bags: overlay fills gaps, base keeps AH/AS/etc.
      stats: { ...item.stats, ...prev.stats },
      name: prev.name || item.name,
      gold: prev.gold || item.gold,
      category: prev.category || item.category,
    }
  }
  return out
}

/** Full item catalog from lolwiki ingest (DDragon + Meraki stats). */
export const ITEMS: Record<string, ItemDefinition> = mergeItemCatalogs(
  ALL_ITEMS,
  GAME_ITEMS,
)

export const ITEM_LIST = Object.values(ITEMS).sort((a, b) =>
  a.name.localeCompare(b.name),
)

export const ITEMS_BY_CATEGORY = ITEM_LIST.reduce(
  (acc, item) => {
    ;(acc[item.category] ??= []).push(item)
    return acc
  },
  {} as Record<string, ItemDefinition[]>,
)

export function itemIconUrl(id: string): string {
  return `https://ddragon.leagueoflegends.com/cdn/${DDRAGON_PATCH}/img/item/${id}.png`
}

export function resolveItem(id: string | number | null | undefined): ItemDefinition | null {
  if (id == null || id === '' || id === 'None' || id === 'null') return null
  return ITEMS[String(id)] ?? null
}

export { DDRAGON_PATCH }
