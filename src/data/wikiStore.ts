/**
 * Runtime access to the ingested lolwiki snapshot under /data/lolwiki/.
 * Full champion kits (~13MB) stay on disk and load on demand.
 */

export interface LolWikiMeta {
  patch: string
  ingestedAt: string
  counts: {
    items: number
    runes: number
    keystones: number
    summoners: number
    champions: number
  }
}

let metaCache: LolWikiMeta | null = null
let champsCache: Record<string, unknown> | null = null

export async function loadWikiMeta(): Promise<LolWikiMeta> {
  if (metaCache) return metaCache
  const res = await fetch('/data/lolwiki/meta.json')
  if (!res.ok) throw new Error(`lolwiki meta ${res.status}`)
  metaCache = (await res.json()) as LolWikiMeta
  return metaCache
}

/** Full Meraki champion document (abilities, stats, lore, …). */
export async function loadChampionWiki(id: string): Promise<unknown | null> {
  const all = await loadAllChampionsWiki()
  return all[id] ?? null
}

export async function loadAllChampionsWiki(): Promise<Record<string, unknown>> {
  if (champsCache) return champsCache
  const res = await fetch('/data/lolwiki/champions-full.json')
  if (!res.ok) throw new Error(`lolwiki champions ${res.status}`)
  champsCache = (await res.json()) as Record<string, unknown>
  return champsCache
}

export async function loadItemsWiki(): Promise<Record<string, unknown>> {
  const res = await fetch('/data/lolwiki/items-full.json')
  if (!res.ok) throw new Error(`lolwiki items ${res.status}`)
  return res.json() as Promise<Record<string, unknown>>
}

export async function loadRunesWiki(): Promise<Record<string, unknown>> {
  const res = await fetch('/data/lolwiki/runes-full.json')
  if (!res.ok) throw new Error(`lolwiki runes ${res.status}`)
  return res.json() as Promise<Record<string, unknown>>
}
