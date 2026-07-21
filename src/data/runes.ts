import type { DamagePacket, RuneDefinition, TradeMode, CombatStats } from '../engine/types'
import {
  ALL_RUNES,
  KEYSTONE_ID_TO_SLUG,
  KEYSTONE_RUNES,
  RUNE_BY_RIOT_ID,
  RUNE_BY_SLUG,
  type WikiRune,
} from './generated/allRunes'

function packet(
  raw: number,
  type: DamagePacket['type'],
  source: string,
  slot: DamagePacket['slot'] = 'P',
  extra: Partial<DamagePacket> = {},
): DamagePacket {
  return { raw, type, source, slot, ...extra }
}

type TradeFn = (
  a: CombatStats,
  d: CombatStats,
  mode: TradeMode,
) => DamagePacket[]

/** Combat models for every keystone — including utility-only (Spellbook). */
const COMBAT_MODELS: Record<string, TradeFn> = {
  electrocute: (a, _d, mode) => {
    const base = 30 + 9 * a.level
    const raw = base + 0.4 * Math.max(0, a.ad - a.baseAd) + 0.25 * a.ap
    return [packet(mode === 'allin' ? raw : raw * 0.85, 'magical', 'Electrocute')]
  },
  darkHarvest: (a, _d, mode) => {
    if (mode !== 'allin') return []
    const raw = 20 + 5 * a.level + 0.25 * a.ap + 0.15 * a.ad + 40
    return [packet(raw, 'magical', 'Dark Harvest')]
  },
  hailOfBlades: (a, _d, mode) => {
    const hits = mode === 'allin' ? 3 : 2
    return [packet(a.ad * 0.35 * hits, 'physical', `Hail of Blades (×${hits})`, 'AA')]
  },
  pta: (a) => [packet(40 + 8 * a.level, 'physical', 'Press the Attack')],
  lethalTempo: (a, _d, mode) => {
    const extras = mode === 'allin' ? 2 : 1
    return [packet(a.ad * 0.9 * extras, 'physical', `Lethal Tempo (+${extras} AA)`, 'AA')]
  },
  fleetFootwork: (a) => [
    packet(15 + 10 * a.level + 0.1 * a.ad, 'physical', 'Fleet Footwork'),
  ],
  conqueror: (a, _d, mode) => {
    const stacks = mode === 'allin' ? 12 : 6
    const adaptive = stacks * (1.2 + 0.2 * a.level)
    const asTrue = mode === 'allin' ? adaptive * 0.1 : 0
    return [
      packet(adaptive, a.ad >= a.ap ? 'physical' : 'magical', `Conqueror (${stacks})`),
      ...(asTrue ? [packet(asTrue, 'true', 'Conqueror true')] : []),
    ]
  },
  aery: (a, _d, mode) => {
    const raw = 10 + 5 * a.level + 0.15 * a.ap + 0.1 * a.ad
    return [packet(mode === 'allin' ? raw * 2 : raw, 'magical', 'Summon Aery')]
  },
  comet: (a, _d, mode) => {
    const raw = 30 + 5 * a.level + 0.2 * a.ap + 0.1 * a.ad
    return [
      packet(mode === 'allin' ? raw * 1.5 : raw, 'magical', 'Arcane Comet', 'P', {
        skillshot: true,
      }),
    ]
  },
  phaseRush: () => [], // utility MS — applied via rune utility hook later
  grasp: (a, _d, mode) => {
    if (mode === 'short') {
      return [packet(3.5 + 0.02 * a.hpMax, 'magical', 'Grasp of the Undying')]
    }
    return [packet((3.5 + 0.02 * a.hpMax) * 2, 'magical', 'Grasp (×2)')]
  },
  aftershock: (a) => [
    packet(25 + 8 * a.level + 0.08 * a.hpMax, 'magical', 'Aftershock'),
  ],
  guardian: () => [], // shield utility
  glacialAugment: () => [], // slow utility
  firstStrike: (a, _d, mode) => {
    const raw = 10 + 5 * a.level + (a.ad + a.ap) * 0.07
    return [packet(mode === 'allin' ? raw * 1.4 : raw, 'true', 'First Strike')]
  },
  /**
   * Unsealed Spellbook — no direct damage. Value is summoner flexibility.
   * Swap CD / pool rules live on the WikiRune.spellbook blob + loadout.spellbookState.
   */
  spellbook: () => [],
}

function treeName(tree: string): RuneDefinition['tree'] {
  if (
    tree === 'Domination' ||
    tree === 'Precision' ||
    tree === 'Sorcery' ||
    tree === 'Resolve' ||
    tree === 'Inspiration'
  ) {
    return tree
  }
  return 'Inspiration'
}

function toDefinition(wiki: WikiRune): RuneDefinition {
  const modelKey = wiki.combatModel || wiki.slug
  return {
    id: wiki.combatModel || wiki.slug,
    riotId: wiki.riotId,
    slug: wiki.slug,
    name: wiki.name,
    tree: treeName(wiki.tree),
    description: stripHtml(wiki.shortDescription || wiki.longDescription),
    isKeystone: wiki.isKeystone,
    spellbook: wiki.spellbook,
    tradeBonus: COMBAT_MODELS[modelKey],
  }
}

function stripHtml(s: string): string {
  return s.replace(/<[^>]+>/g, '').replace(/&nbsp;/g, ' ').trim()
}

/** All runes (keystones + minors) from the ingested wiki snapshot. */
export const RUNES: Record<string, RuneDefinition> = Object.fromEntries(
  Object.values(ALL_RUNES).map((r) => {
    const def = toDefinition(r)
    return [def.id, def]
  }),
)

/** Also index by riot id string so timeline ids resolve. */
for (const r of Object.values(ALL_RUNES)) {
  const def = RUNES[r.combatModel || r.slug]
  if (def) {
    RUNES[String(r.riotId)] = def
    RUNES[r.slug] = def
  }
}

export const RUNE_LIST = KEYSTONE_RUNES.map((r) => RUNES[r.combatModel || r.slug]).filter(
  Boolean,
) as RuneDefinition[]

export const ALL_RUNE_LIST = Object.values(ALL_RUNES).map(toDefinition)

export function resolveRuneId(
  id: string | number | null | undefined,
): RuneDefinition | null {
  if (id == null || id === '' || id === 'null' || id === 'None') return null
  if (typeof id === 'number') {
    const wiki = RUNE_BY_RIOT_ID[id]
    if (wiki) return RUNES[wiki.combatModel || wiki.slug] ?? null
    return RUNES[KEYSTONE_ID_TO_SLUG[id]] ?? null
  }
  if (RUNES[id]) return RUNES[id]
  const bySlug = RUNE_BY_SLUG[id]
  if (bySlug) return RUNES[bySlug.combatModel || bySlug.slug] ?? null
  const asNum = Number(id)
  if (Number.isFinite(asNum)) return resolveRuneId(asNum)
  return null
}

export { KEYSTONE_ID_TO_SLUG, KEYSTONE_RUNES, ALL_RUNES, RUNE_BY_RIOT_ID }
