/**
 * Bounded combat-model coverage audit.
 *
 * Measures the gap between ingested wiki knowledge and combat behavior that is
 * actually modeled in this repository. Read-only over the rest of the tree —
 * does not mutate engine, UI, or generated data.
 *
 * Usage:
 *   npx --yes tsx scripts/audit-combat-coverage.ts
 *   npx --yes tsx scripts/audit-combat-coverage.ts --json
 *   npx --yes tsx scripts/audit-combat-coverage.ts --check
 *   npx --yes tsx scripts/audit-combat-coverage.ts --strict
 *   npx --yes tsx scripts/audit-combat-coverage.ts --self-test
 */
import { execFileSync } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { CHAMPIONS, DDRAGON as RUNTIME_DDRAGON } from '../src/data/champions'
import { WIKI_CHAMPION_INDEX } from '../src/data/generated/championIndex'
import {
  ALL_ITEMS,
  DDRAGON_PATCH as ITEMS_DDRAGON_PATCH,
} from '../src/data/generated/allItems'
import {
  ALL_RUNES,
  KEYSTONE_RUNES,
  type WikiRune,
} from '../src/data/generated/allRunes'
import { GAME_CHAMPIONS } from '../src/data/generatedGameChamps'
import { ITEM_PASSIVES } from '../src/data/itemPassives'
import { ITEMS } from '../src/data/items'
import { RUNES } from '../src/data/runes'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const REPO_ROOT = path.resolve(__dirname, '..')

/**
 * Repo currently has no explicit patch/numerical/empirical validation ledger
 * for champion kits, keystones, or item behavior. Until that exists,
 * fullTrustedCoverage must remain false.
 */
const HAS_EXPLICIT_VALIDATION_EVIDENCE = false

/** No per-item review ledger classifying stats-only vs combat-relevant hooks. */
const HAS_ITEM_REVIEW_LEDGER = false

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type ChampionModelTier =
  | 'wiki_only'
  | 'generated'
  | 'curated'
  | 'curated_override'

export interface ChampionCoverageRow {
  id: string
  name: string
  /** Modeling attention tier — not a claim of patch correctness. */
  modeling: ChampionModelTier
  inWikiIndex: boolean
  inGameChampions: boolean
  inCuratedCore: boolean
  inRuntimeChampions: boolean
  abilitySlotCount: number
  hasPassiveDamageHook: boolean
  hasUtilityAbility: boolean
  /** True when a damage() fn exists — NOT a claim of accuracy. */
  hasDamageFunctions: boolean
}

export interface TimelineChampionRow {
  championName: string
  modeling: ChampionModelTier | 'unresolved'
  inWikiIndex: boolean
  inRuntimeChampions: boolean
  missingCombatDefinition: boolean
}

export interface TimelineCoverage {
  file: string
  id: string
  name: string
  patch: string
  committed: boolean
  builtinId: string | null
  participants: number
  champions: TimelineChampionRow[]
  missingCombatDefinitions: string[]
  unresolvedWikiIds: string[]
  generatedOnly: string[]
  curatedOrOverride: string[]
}

export interface StructuralIssue {
  code: string
  message: string
}

export interface CoverageReport {
  /** Stable snapshot time from lolwiki meta (not wall-clock). */
  snapshotAt: string | null
  repoRoot: string
  counts: {
    wikiChampionIndex: number
    runtimeChampions: number
    gameChampions: number
    curatedCore: number
    curatedOverrides: number
    curatedOnly: number
    wikiOnlyChampions: number
    /** Runtime calculator catalog (`ITEMS` / `ITEM_LIST`). */
    runtimeItems: number
    /** Generated DDragon/Meraki base before GAME_ITEMS merge. */
    generatedAllItems: number
    itemPassives: number
    itemNoHookUnreviewed: number
    itemsSummonersRiftJson: number
    runes: number
    keystones: number
    keystonesWithCombatHooks: number
    keystonesWithoutCombatHooks: number
  }
  coverage: {
    /** Hand-authored CORE kits (including overrides). Unvalidated. */
    curatedManualModelIds: string[]
    generatedUnvalidatedIds: string[]
    wikiOnlyIds: string[]
    /**
     * True only when every wiki champion has a CORE manual model, every
     * keystone has a hook, committed timeline participants are manual-modeled,
     * and every runtime item is explicitly reviewed/classified (ledger).
     * Does NOT imply trusted/validated accuracy.
     */
    fullManualModelCoverage: boolean
    /**
     * Requires explicit patch/numerical/empirical validation evidence in
     * addition to full manual modeling. Never true merely because CORE is full.
     */
    fullTrustedCoverage: boolean
    gapsBlockingManualModelCoverage: string[]
    gapsBlockingTrustedCoverage: string[]
    hasExplicitValidationEvidence: boolean
    hasItemReviewLedger: boolean
  }
  champions: ChampionCoverageRow[]
  items: {
    /** Runtime ITEMS ids with explicit ITEM_PASSIVES behavior hooks. */
    passiveIds: string[]
    passiveUnknownItemIds: string[]
    /** Runtime items without an explicit behavior hook (unreviewed / no ledger). */
    noHookUnreviewedCount: number
    generatedAllItemsCount: number
    runtimeItemsCount: number
  }
  runes: {
    keystones: Array<{
      slug: string
      riotId: number
      combatModel: string | null
      hasCombatHook: boolean
    }>
    keystonesMissingHooks: string[]
  }
  provenance: {
    lolwikiMetaPatch: string | null
    lolwikiIngestedAt: string | null
    itemsDdragonPatch: string | null
    runtimeChampionDdragon: string | null
    metaCounts: Record<string, number> | null
    observedVsMeta: Array<{
      field: string
      meta: number | null
      observed: number
      ok: boolean
    }>
    timelinePatches: Array<{ file: string; patch: string }>
    patchNotes: string[]
  }
  timelines: TimelineCoverage[]
  structuralIssues: StructuralIssue[]
  modelingGaps: string[]
}

// ---------------------------------------------------------------------------
// Source parsing (CORE_CHAMPIONS is not exported)
// ---------------------------------------------------------------------------

function extractObjectKeysAfterConst(
  source: string,
  constName: string,
): string[] {
  const marker = `const ${constName}`
  const start = source.indexOf(marker)
  if (start < 0) return []
  const brace = source.indexOf('{', start)
  if (brace < 0) return []
  let depth = 0
  let end = -1
  for (let i = brace; i < source.length; i++) {
    const ch = source[i]
    if (ch === '{') depth++
    else if (ch === '}') {
      depth--
      if (depth === 0) {
        end = i
        break
      }
    }
  }
  if (end < 0) return []
  const block = source.slice(brace, end + 1)
  const keys = new Set<string>()
  for (const m of block.matchAll(/^  ([A-Za-z][A-Za-z0-9_]*):/gm)) {
    keys.add(m[1])
  }
  return [...keys].sort((a, b) => a.localeCompare(b))
}

function readCuratedCoreIds(): string[] {
  const src = fs.readFileSync(
    path.join(REPO_ROOT, 'src/data/champions.ts'),
    'utf8',
  )
  return extractObjectKeysAfterConst(src, 'CORE_CHAMPIONS')
}

function listBuiltinTimelineIds(): string[] {
  const src = fs.readFileSync(
    path.join(REPO_ROOT, 'src/game/timeline.ts'),
    'utf8',
  )
  const m = src.match(/export type BuiltinTimelineId\s*=\s*([^;\n]+)/)
  if (!m) return []
  return [...m[1].matchAll(/'([^']+)'/g)].map((x) => x[1])
}

function gitTrackedFiles(globPattern: string): string[] {
  try {
    const out = execFileSync(
      'git',
      ['ls-files', '-z', '--', globPattern],
      { cwd: REPO_ROOT, encoding: 'buffer' },
    )
    return out
      .toString('utf8')
      .split('\0')
      .filter(Boolean)
      .sort((a, b) => a.localeCompare(b))
  } catch {
    return []
  }
}

function loadJsonFile<T>(rel: string): T {
  return JSON.parse(
    fs.readFileSync(path.join(REPO_ROOT, rel), 'utf8'),
  ) as T
}

// ---------------------------------------------------------------------------
// Classification
// ---------------------------------------------------------------------------

function classifyChampion(
  id: string,
  curated: Set<string>,
  game: Set<string>,
  runtime: Set<string>,
  wiki: Set<string>,
): ChampionModelTier {
  const inCurated = curated.has(id)
  const inGame = game.has(id)
  if (inCurated && inGame) return 'curated_override'
  if (inCurated) return 'curated'
  if (inGame || runtime.has(id)) return 'generated'
  if (wiki.has(id)) return 'wiki_only'
  return 'wiki_only'
}

function inspectChampionDef(id: string): Pick<
  ChampionCoverageRow,
  | 'abilitySlotCount'
  | 'hasPassiveDamageHook'
  | 'hasUtilityAbility'
  | 'hasDamageFunctions'
  | 'name'
> {
  const def = CHAMPIONS[id]
  if (!def) {
    const wiki = WIKI_CHAMPION_INDEX[id as keyof typeof WIKI_CHAMPION_INDEX] as
      | { name?: string }
      | undefined
    return {
      name: wiki?.name ?? id,
      abilitySlotCount: 0,
      hasPassiveDamageHook: false,
      hasUtilityAbility: false,
      hasDamageFunctions: false,
    }
  }
  return {
    name: def.name,
    abilitySlotCount: def.abilities.length,
    hasPassiveDamageHook: typeof def.passiveDamage === 'function',
    hasUtilityAbility: def.abilities.some((a) => a.utility != null),
    hasDamageFunctions: def.abilities.some((a) => typeof a.damage === 'function'),
  }
}

function keystoneHasCombatHook(rune: WikiRune): boolean {
  const modelKey = rune.combatModel || rune.slug
  const def = RUNES[modelKey] ?? RUNES[rune.slug] ?? RUNES[String(rune.riotId)]
  return typeof def?.tradeBonus === 'function'
}

function isManualModel(tier: ChampionModelTier | 'unresolved'): boolean {
  return tier === 'curated' || tier === 'curated_override'
}

/**
 * Compute coverage flags. Manual model fullness never implies trust —
 * trust additionally requires explicit validation evidence.
 */
export function computeCoverageFlags(args: {
  curatedManualModelCount: number
  wikiChampionCount: number
  keystonesMissingHooks: string[]
  timelines: TimelineCoverage[]
  hasItemReviewLedger: boolean
  hasExplicitValidationEvidence: boolean
}): {
  fullManualModelCoverage: boolean
  fullTrustedCoverage: boolean
  gapsBlockingManualModelCoverage: string[]
  gapsBlockingTrustedCoverage: string[]
} {
  const gapsManual: string[] = []

  if (args.curatedManualModelCount < args.wikiChampionCount) {
    gapsManual.push(
      `curated/manual-model champions ${args.curatedManualModelCount}/${args.wikiChampionCount} (wiki index)`,
    )
  }
  if (args.keystonesMissingHooks.length > 0) {
    gapsManual.push(
      `keystones missing combat hooks: ${args.keystonesMissingHooks.join(', ')}`,
    )
  }
  for (const tl of args.timelines) {
    if (tl.missingCombatDefinitions.length > 0) {
      gapsManual.push(
        `${tl.file}: missing combat defs for ${tl.missingCombatDefinitions.join(', ')}`,
      )
    }
    const nonManual = tl.champions
      .filter((c) => !isManualModel(c.modeling))
      .map((c) => c.championName)
    if (nonManual.length > 0) {
      gapsManual.push(
        `${tl.file}: participants not curated/manual-model: ${nonManual.join(', ')}`,
      )
    }
  }
  if (!args.hasItemReviewLedger) {
    gapsManual.push(
      'no item review ledger: runtime items are not explicitly classified as stats-only vs combat-relevant (cannot treat no-hook rows as reviewed)',
    )
  }

  const fullManualModelCoverage =
    args.wikiChampionCount > 0 &&
    args.curatedManualModelCount === args.wikiChampionCount &&
    args.keystonesMissingHooks.length === 0 &&
    args.timelines.every(
      (tl) =>
        tl.missingCombatDefinitions.length === 0 &&
        tl.unresolvedWikiIds.length === 0 &&
        tl.champions.every((c) => isManualModel(c.modeling)),
    ) &&
    args.hasItemReviewLedger

  const gapsTrusted: string[] = [...gapsManual]
  if (!args.hasExplicitValidationEvidence) {
    gapsTrusted.push(
      'no explicit patch/numerical/empirical validation evidence for combat models (CORE/manual presence is not validation)',
    )
  }

  // Trust never follows from manual coverage alone.
  const fullTrustedCoverage =
    fullManualModelCoverage && args.hasExplicitValidationEvidence

  return {
    fullManualModelCoverage,
    fullTrustedCoverage,
    gapsBlockingManualModelCoverage: gapsManual,
    gapsBlockingTrustedCoverage: gapsTrusted,
  }
}

// ---------------------------------------------------------------------------
// Report builder
// ---------------------------------------------------------------------------

function buildReport(): CoverageReport {
  const curatedIds = readCuratedCoreIds()
  const curatedSet = new Set(curatedIds)
  const gameIds = Object.keys(GAME_CHAMPIONS).sort((a, b) => a.localeCompare(b))
  const gameSet = new Set(gameIds)
  const runtimeIds = Object.keys(CHAMPIONS).sort((a, b) => a.localeCompare(b))
  const runtimeSet = new Set(runtimeIds)
  const wikiIds = Object.keys(WIKI_CHAMPION_INDEX).sort((a, b) =>
    a.localeCompare(b),
  )
  const wikiSet = new Set(wikiIds)

  const curatedOverrides = curatedIds.filter((id) => gameSet.has(id))
  const curatedOnly = curatedIds.filter((id) => !gameSet.has(id))
  const wikiOnly = wikiIds.filter((id) => !runtimeSet.has(id))
  const generatedOnly = gameIds.filter((id) => !curatedSet.has(id))

  const allChampionIds = [...new Set([...wikiIds, ...runtimeIds])].sort((a, b) =>
    a.localeCompare(b),
  )

  const champions: ChampionCoverageRow[] = allChampionIds.map((id) => {
    const modeling = classifyChampion(
      id,
      curatedSet,
      gameSet,
      runtimeSet,
      wikiSet,
    )
    const inspected = inspectChampionDef(id)
    return {
      id,
      modeling,
      inWikiIndex: wikiSet.has(id),
      inGameChampions: gameSet.has(id),
      inCuratedCore: curatedSet.has(id),
      inRuntimeChampions: runtimeSet.has(id),
      ...inspected,
    }
  })

  const curatedManualModelIds = curatedIds
    .slice()
    .sort((a, b) => a.localeCompare(b))

  const passiveIds = Object.keys(ITEM_PASSIVES).sort((a, b) =>
    a.localeCompare(b, undefined, { numeric: true }),
  )
  const runtimeItemIds = Object.keys(ITEMS).sort((a, b) =>
    a.localeCompare(b, undefined, { numeric: true }),
  )
  const runtimeItemSet = new Set(runtimeItemIds)
  const generatedAllItemIds = Object.keys(ALL_ITEMS)
  const passiveUnknownItemIds = passiveIds.filter((id) => !runtimeItemSet.has(id))
  const noHookUnreviewedCount = Math.max(
    0,
    runtimeItemIds.length - passiveIds.filter((id) => runtimeItemSet.has(id)).length,
  )

  let itemsSummonersRiftJson = 0
  try {
    const sr = loadJsonFile<Record<string, unknown>>(
      'public/data/lolwiki/items-summoners-rift.json',
    )
    itemsSummonersRiftJson = Object.keys(sr).length
  } catch {
    itemsSummonersRiftJson = 0
  }

  const keystoneRows = KEYSTONE_RUNES.map((r) => ({
    slug: r.slug,
    riotId: r.riotId,
    combatModel: r.combatModel,
    hasCombatHook: keystoneHasCombatHook(r),
  })).sort((a, b) => a.slug.localeCompare(b.slug))

  const keystonesMissingHooks = keystoneRows
    .filter((r) => !r.hasCombatHook)
    .map((r) => r.slug)

  let meta: {
    patch?: string
    ingestedAt?: string
    counts?: Record<string, number>
  } | null = null
  try {
    meta = loadJsonFile('public/data/lolwiki/meta.json')
  } catch {
    meta = null
  }

  const observedVsMeta: CoverageReport['provenance']['observedVsMeta'] = [
    {
      field: 'champions',
      meta: meta?.counts?.champions ?? null,
      observed: wikiIds.length,
      ok: meta?.counts?.champions === wikiIds.length,
    },
    {
      field: 'runes',
      meta: meta?.counts?.runes ?? null,
      observed: Object.keys(ALL_RUNES).length,
      ok: meta?.counts?.runes === Object.keys(ALL_RUNES).length,
    },
    {
      field: 'keystones',
      meta: meta?.counts?.keystones ?? null,
      observed: KEYSTONE_RUNES.length,
      ok: meta?.counts?.keystones === KEYSTONE_RUNES.length,
    },
    {
      field: 'itemsSummonersRift',
      meta: meta?.counts?.itemsSummonersRift ?? null,
      observed: itemsSummonersRiftJson,
      ok: meta?.counts?.itemsSummonersRift === itemsSummonersRiftJson,
    },
  ]

  const patchNotes: string[] = []
  const metaPatch = meta?.patch ?? null
  if (metaPatch && ITEMS_DDRAGON_PATCH && metaPatch !== ITEMS_DDRAGON_PATCH) {
    patchNotes.push(
      `lolwiki meta patch ${metaPatch} ≠ items DDRAGON_PATCH ${ITEMS_DDRAGON_PATCH}`,
    )
  }
  if (
    RUNTIME_DDRAGON &&
    ITEMS_DDRAGON_PATCH &&
    RUNTIME_DDRAGON !== ITEMS_DDRAGON_PATCH
  ) {
    patchNotes.push(
      `runtime champion DDRAGON ${RUNTIME_DDRAGON} ≠ items DDRAGON_PATCH ${ITEMS_DDRAGON_PATCH}`,
    )
  }
  if (runtimeItemIds.length !== generatedAllItemIds.length) {
    patchNotes.push(
      `runtime ITEMS (${runtimeItemIds.length}) ≠ generated ALL_ITEMS (${generatedAllItemIds.length}) — calculator merges GAME_ITEMS onto ALL_ITEMS`,
    )
  }
  if (itemsSummonersRiftJson !== runtimeItemIds.length) {
    patchNotes.push(
      `SR items JSON (${itemsSummonersRiftJson}) ≠ runtime ITEMS (${runtimeItemIds.length}) — map/object rows filtered or GAME overlay adds`,
    )
  }

  const committedTimelineFiles = gitTrackedFiles('public/data/*_timeline.json')
  const builtinIds = listBuiltinTimelineIds()
  const timelines: TimelineCoverage[] = []

  for (const rel of committedTimelineFiles) {
    const abs = path.join(REPO_ROOT, rel)
    let data: {
      id?: string
      name?: string
      patch?: string
      participants?: Array<{ championName?: string }>
    }
    try {
      data = JSON.parse(fs.readFileSync(abs, 'utf8'))
    } catch (err) {
      timelines.push({
        file: rel,
        id: path.basename(rel),
        name: '(unreadable)',
        patch: '',
        committed: true,
        builtinId: null,
        participants: 0,
        champions: [],
        missingCombatDefinitions: [],
        unresolvedWikiIds: ['(malformed JSON)'],
        generatedOnly: [],
        curatedOrOverride: [],
      })
      void err
      continue
    }

    const base = path.basename(rel, '_timeline.json')
    const builtinId = builtinIds.includes(base) ? base : null
    const names = (data.participants ?? [])
      .map((p) => p.championName)
      .filter((n): n is string => typeof n === 'string' && n.length > 0)

    const uniqueNames = [...new Set(names)].sort((a, b) => a.localeCompare(b))
    const champRows: TimelineChampionRow[] = uniqueNames.map((championName) => {
      const inWiki = wikiSet.has(championName)
      const inRuntime = runtimeSet.has(championName)
      const modeling = inRuntime
        ? classifyChampion(
            championName,
            curatedSet,
            gameSet,
            runtimeSet,
            wikiSet,
          )
        : inWiki
          ? 'wiki_only'
          : 'unresolved'
      return {
        championName,
        modeling,
        inWikiIndex: inWiki,
        inRuntimeChampions: inRuntime,
        missingCombatDefinition: !inRuntime,
      }
    })

    timelines.push({
      file: rel,
      id: data.id ?? base,
      name: data.name ?? base,
      patch: data.patch ?? '',
      committed: true,
      builtinId,
      participants: names.length,
      champions: champRows,
      missingCombatDefinitions: champRows
        .filter((c) => c.missingCombatDefinition)
        .map((c) => c.championName),
      unresolvedWikiIds: champRows
        .filter((c) => c.modeling === 'unresolved')
        .map((c) => c.championName),
      generatedOnly: champRows
        .filter((c) => c.modeling === 'generated')
        .map((c) => c.championName),
      curatedOrOverride: champRows
        .filter((c) => isManualModel(c.modeling))
        .map((c) => c.championName),
    })

    if (data.patch && metaPatch) {
      const metaMajorMinor = String(metaPatch).split('.').slice(0, 2).join('.')
      if (!String(data.patch).startsWith(metaMajorMinor)) {
        patchNotes.push(
          `${rel} patch ${data.patch} vs lolwiki meta ${metaPatch}`,
        )
      }
    }
  }

  for (const bid of builtinIds) {
    const expected = `public/data/${bid}_timeline.json`
    const committed = committedTimelineFiles.includes(expected)
    const existsOnDisk = fs.existsSync(path.join(REPO_ROOT, expected))
    if (!committed && existsOnDisk) {
      patchNotes.push(
        `builtin timeline '${bid}' exists on disk but is not git-committed — excluded from committed coverage`,
      )
    } else if (!committed && !existsOnDisk) {
      patchNotes.push(
        `builtin timeline '${bid}' referenced in timeline.ts but file missing`,
      )
    }
  }

  const flags = computeCoverageFlags({
    curatedManualModelCount: curatedManualModelIds.length,
    wikiChampionCount: wikiIds.length,
    keystonesMissingHooks,
    timelines,
    hasItemReviewLedger: HAS_ITEM_REVIEW_LEDGER,
    hasExplicitValidationEvidence: HAS_EXPLICIT_VALIDATION_EVIDENCE,
  })

  // Always surface item hook vs unreviewed split (not a fake “need hooks for all”).
  const itemHookNote = `explicit ITEM_PASSIVES behavior hooks ${passiveIds.length}; no-hook/unreviewed runtime items ${noHookUnreviewedCount}`

  const structuralIssues = collectStructuralIssues({
    meta,
    wikiIds,
    runtimeIds,
    gameIds,
    curatedIds,
    wikiSet,
    timelines,
    passiveUnknownItemIds,
    observedVsMeta,
  })

  const modelingGaps: string[] = [
    ...flags.gapsBlockingTrustedCoverage,
    itemHookNote,
    `wiki-only champions (no runtime combat object): ${wikiOnly.length}`,
    `generated (Meraki/GAME) unvalidated kits: ${generatedOnly.length}`,
  ]

  return {
    snapshotAt: meta?.ingestedAt ?? null,
    repoRoot: REPO_ROOT,
    counts: {
      wikiChampionIndex: wikiIds.length,
      runtimeChampions: runtimeIds.length,
      gameChampions: gameIds.length,
      curatedCore: curatedIds.length,
      curatedOverrides: curatedOverrides.length,
      curatedOnly: curatedOnly.length,
      wikiOnlyChampions: wikiOnly.length,
      runtimeItems: runtimeItemIds.length,
      generatedAllItems: generatedAllItemIds.length,
      itemPassives: passiveIds.length,
      itemNoHookUnreviewed: noHookUnreviewedCount,
      itemsSummonersRiftJson: itemsSummonersRiftJson,
      runes: Object.keys(ALL_RUNES).length,
      keystones: KEYSTONE_RUNES.length,
      keystonesWithCombatHooks: keystoneRows.filter((r) => r.hasCombatHook)
        .length,
      keystonesWithoutCombatHooks: keystonesMissingHooks.length,
    },
    coverage: {
      curatedManualModelIds,
      generatedUnvalidatedIds: generatedOnly,
      wikiOnlyIds: wikiOnly,
      fullManualModelCoverage: flags.fullManualModelCoverage,
      fullTrustedCoverage: flags.fullTrustedCoverage,
      gapsBlockingManualModelCoverage: flags.gapsBlockingManualModelCoverage,
      gapsBlockingTrustedCoverage: flags.gapsBlockingTrustedCoverage,
      hasExplicitValidationEvidence: HAS_EXPLICIT_VALIDATION_EVIDENCE,
      hasItemReviewLedger: HAS_ITEM_REVIEW_LEDGER,
    },
    champions,
    items: {
      passiveIds,
      passiveUnknownItemIds,
      noHookUnreviewedCount,
      generatedAllItemsCount: generatedAllItemIds.length,
      runtimeItemsCount: runtimeItemIds.length,
    },
    runes: {
      keystones: keystoneRows,
      keystonesMissingHooks,
    },
    provenance: {
      lolwikiMetaPatch: metaPatch,
      lolwikiIngestedAt: meta?.ingestedAt ?? null,
      itemsDdragonPatch: ITEMS_DDRAGON_PATCH ?? null,
      runtimeChampionDdragon: RUNTIME_DDRAGON ?? null,
      metaCounts: meta?.counts ?? null,
      observedVsMeta,
      timelinePatches: timelines.map((t) => ({ file: t.file, patch: t.patch })),
      patchNotes: [...new Set(patchNotes)].sort((a, b) => a.localeCompare(b)),
    },
    timelines,
    structuralIssues,
    modelingGaps,
  }
}

function collectStructuralIssues(args: {
  meta: { patch?: string; counts?: Record<string, number> } | null
  wikiIds: string[]
  runtimeIds: string[]
  gameIds: string[]
  curatedIds: string[]
  wikiSet: Set<string>
  timelines: TimelineCoverage[]
  passiveUnknownItemIds: string[]
  observedVsMeta: CoverageReport['provenance']['observedVsMeta']
}): StructuralIssue[] {
  const issues: StructuralIssue[] = []

  if (!args.meta) {
    issues.push({
      code: 'meta_missing',
      message: 'public/data/lolwiki/meta.json missing or unreadable',
    })
  } else {
    if (!args.meta.patch || typeof args.meta.patch !== 'string') {
      issues.push({
        code: 'meta_malformed',
        message: 'lolwiki meta.json missing string patch field',
      })
    }
    if (!args.meta.counts || typeof args.meta.counts !== 'object') {
      issues.push({
        code: 'meta_malformed',
        message: 'lolwiki meta.json missing counts object',
      })
    }
  }

  for (const row of args.observedVsMeta) {
    if (
      row.field === 'champions' ||
      row.field === 'runes' ||
      row.field === 'keystones'
    ) {
      if (row.meta != null && !row.ok) {
        issues.push({
          code: 'impossible_counts',
          message: `meta.counts.${row.field}=${row.meta} but observed ${row.observed}`,
        })
      }
    }
  }

  if (KEYSTONE_RUNES.length > Object.keys(ALL_RUNES).length) {
    issues.push({
      code: 'impossible_counts',
      message: `keystones (${KEYSTONE_RUNES.length}) > runes (${Object.keys(ALL_RUNES).length})`,
    })
  }

  const dupRuntime = findDuplicates(args.runtimeIds)
  if (dupRuntime.length) {
    issues.push({
      code: 'duplicate_ids',
      message: `duplicate CHAMPIONS keys: ${dupRuntime.join(', ')}`,
    })
  }
  const dupGame = findDuplicates(args.gameIds)
  if (dupGame.length) {
    issues.push({
      code: 'duplicate_ids',
      message: `duplicate GAME_CHAMPIONS keys: ${dupGame.join(', ')}`,
    })
  }
  const dupCurated = findDuplicates(args.curatedIds)
  if (dupCurated.length) {
    issues.push({
      code: 'duplicate_ids',
      message: `duplicate CORE_CHAMPIONS keys: ${dupCurated.join(', ')}`,
    })
  }

  for (const id of args.gameIds) {
    if (!args.wikiSet.has(id)) {
      issues.push({
        code: 'unknown_ids',
        message: `GAME_CHAMPIONS id '${id}' not in wiki champion index`,
      })
    }
  }
  for (const id of args.curatedIds) {
    if (!args.wikiSet.has(id)) {
      issues.push({
        code: 'unknown_ids',
        message: `CORE_CHAMPIONS id '${id}' not in wiki champion index`,
      })
    }
  }

  for (const id of args.passiveUnknownItemIds) {
    issues.push({
      code: 'unknown_ids',
      message: `ITEM_PASSIVES id '${id}' not in runtime ITEMS catalog`,
    })
  }

  for (const tl of args.timelines) {
    for (const name of tl.unresolvedWikiIds) {
      issues.push({
        code: 'timeline_unresolved',
        message: `${tl.file}: champion '${name}' not in wiki index or runtime CHAMPIONS`,
      })
    }
  }

  return issues
}

function findDuplicates(ids: string[]): string[] {
  const seen = new Set<string>()
  const dups = new Set<string>()
  for (const id of ids) {
    if (seen.has(id)) dups.add(id)
    seen.add(id)
  }
  return [...dups]
}

// ---------------------------------------------------------------------------
// Output
// ---------------------------------------------------------------------------

function formatHuman(report: CoverageReport): string {
  const lines: string[] = []
  const c = report.counts
  const cov = report.coverage
  lines.push('Combat model coverage audit')
  lines.push('===========================')
  if (report.snapshotAt) {
    lines.push(`lolwiki snapshotAt: ${report.snapshotAt}`)
  }
  lines.push('')
  lines.push('Counts')
  lines.push('------')
  lines.push(`  wiki champion index:          ${c.wikiChampionIndex}`)
  lines.push(`  runtime CHAMPIONS:            ${c.runtimeChampions}`)
  lines.push(`  GAME_CHAMPIONS (generated):   ${c.gameChampions}`)
  lines.push(`  curated CORE_CHAMPIONS:       ${c.curatedCore}`)
  lines.push(`    overrides of GAME:          ${c.curatedOverrides}`)
  lines.push(`    curated-only (no GAME):     ${c.curatedOnly}`)
  lines.push(`  wiki-only (no runtime):       ${c.wikiOnlyChampions}`)
  lines.push(`  runtime ITEMS (calculator):   ${c.runtimeItems}`)
  lines.push(`  generated ALL_ITEMS (base):   ${c.generatedAllItems}`)
  lines.push(`  SR items JSON:                ${c.itemsSummonersRiftJson}`)
  lines.push(`  explicit ITEM_PASSIVES hooks: ${c.itemPassives}`)
  lines.push(`  no-hook/unreviewed items:     ${c.itemNoHookUnreviewed}`)
  lines.push(`  runes:                        ${c.runes}`)
  lines.push(`  keystones:                    ${c.keystones}`)
  lines.push(`  keystones with combat hooks:  ${c.keystonesWithCombatHooks}`)
  lines.push(`  keystones missing hooks:      ${c.keystonesWithoutCombatHooks}`)
  lines.push('')
  lines.push('Modeling (CORE ≠ validated / trusted)')
  lines.push('-------------------------------------')
  lines.push(
    `  curated/manual-model ids (${cov.curatedManualModelIds.length}): ${cov.curatedManualModelIds.join(', ') || '(none)'}`,
  )
  lines.push(
    `  generated unvalidated (${cov.generatedUnvalidatedIds.length}): ${cov.generatedUnvalidatedIds.join(', ') || '(none)'}`,
  )
  lines.push(
    `  fullManualModelCoverage: ${cov.fullManualModelCoverage ? 'YES' : 'NO'}`,
  )
  lines.push(
    `  fullTrustedCoverage: ${cov.fullTrustedCoverage ? 'YES' : 'NO'}`,
  )
  lines.push('  gaps (manual model):')
  for (const g of cov.gapsBlockingManualModelCoverage) {
    lines.push(`    - ${g}`)
  }
  lines.push('  gaps (trusted — includes validation evidence gate):')
  for (const g of cov.gapsBlockingTrustedCoverage) {
    lines.push(`    - ${g}`)
  }
  lines.push('')
  lines.push('Provenance / patch drift')
  lines.push('------------------------')
  lines.push(`  lolwiki meta patch:     ${report.provenance.lolwikiMetaPatch}`)
  lines.push(`  lolwiki ingestedAt:     ${report.provenance.lolwikiIngestedAt}`)
  lines.push(`  items DDRAGON_PATCH:    ${report.provenance.itemsDdragonPatch}`)
  lines.push(
    `  runtime champion DDRAGON: ${report.provenance.runtimeChampionDdragon}`,
  )
  for (const row of report.provenance.observedVsMeta) {
    lines.push(
      `  meta.${row.field}: meta=${row.meta} observed=${row.observed} ${row.ok ? 'OK' : 'DRIFT'}`,
    )
  }
  for (const note of report.provenance.patchNotes) {
    lines.push(`  note: ${note}`)
  }
  lines.push('')
  lines.push('Committed timelines')
  lines.push('-------------------')
  if (report.timelines.length === 0) {
    lines.push('  (none)')
  }
  for (const tl of report.timelines) {
    lines.push(
      `  ${tl.file}  id=${tl.id}  patch=${tl.patch}  builtin=${tl.builtinId ?? '—'}  participants=${tl.participants}`,
    )
    lines.push(
      `    champions: ${tl.champions.map((x) => `${x.championName}[${x.modeling}]`).join(', ')}`,
    )
    if (tl.missingCombatDefinitions.length) {
      lines.push(
        `    missing combat definitions: ${tl.missingCombatDefinitions.join(', ')}`,
      )
    }
    if (tl.unresolvedWikiIds.length) {
      lines.push(`    unresolved wiki ids: ${tl.unresolvedWikiIds.join(', ')}`)
    }
  }
  lines.push('')
  lines.push('Keystones missing combat hooks')
  lines.push('------------------------------')
  lines.push(
    `  ${report.runes.keystonesMissingHooks.join(', ') || '(none)'}`,
  )
  lines.push('')
  lines.push(
    `ITEM_PASSIVES hooks: ${report.items.passiveIds.join(', ') || '(none)'}`,
  )
  lines.push(
    `Structural issues: ${report.structuralIssues.length === 0 ? 'none' : report.structuralIssues.length}`,
  )
  for (const issue of report.structuralIssues) {
    lines.push(`  [${issue.code}] ${issue.message}`)
  }
  lines.push('')
  lines.push(
    'Reminder: a damage/utility function existing is modeling intent, not trusted accuracy. CORE/manual-model ≠ validated.',
  )
  return lines.join('\n')
}

// ---------------------------------------------------------------------------
// Modes
// ---------------------------------------------------------------------------

function runCheck(report: CoverageReport): { ok: boolean; lines: string[] } {
  if (report.structuralIssues.length === 0) {
    return {
      ok: true,
      lines: ['--check OK: no structural consistency failures'],
    }
  }
  return {
    ok: false,
    lines: [
      `--check FAILED: ${report.structuralIssues.length} structural issue(s)`,
      ...report.structuralIssues.map((i) => `  [${i.code}] ${i.message}`),
    ],
  }
}

function runStrict(report: CoverageReport): { ok: boolean; lines: string[] } {
  if (report.coverage.fullTrustedCoverage) {
    return {
      ok: true,
      lines: [
        '--strict OK: full trusted combat coverage (manual model + validation evidence)',
      ],
    }
  }
  const reasons = report.coverage.gapsBlockingTrustedCoverage
  return {
    ok: false,
    lines: [
      '--strict FAILED: project is below full trusted combat coverage',
      ...reasons.map((r) => `  - ${r}`),
      'Manual modeling (CORE) is not validation; do not treat stubs or hand kits as trusted without evidence.',
    ],
  }
}

function runSelfTest(): { ok: boolean; lines: string[] } {
  const lines: string[] = ['--self-test']
  const failures: string[] = []

  const fixture = `
const CORE_CHAMPIONS: Record<string, unknown> = {
  Alpha: makeChamp({ id: 'Alpha', nested: { a: 1 } }),
  Beta: makeChamp({ id: 'Beta' }),
}
`
  const keys = extractObjectKeysAfterConst(fixture, 'CORE_CHAMPIONS')
  if (keys.join(',') !== 'Alpha,Beta') {
    failures.push(`extractObjectKeysAfterConst got ${keys.join(',')}`)
  } else {
    lines.push('  ok extractObjectKeysAfterConst')
  }

  if (findDuplicates(['a', 'b', 'a']).join(',') !== 'a') {
    failures.push('findDuplicates failed')
  } else {
    lines.push('  ok findDuplicates')
  }

  const report = buildReport()
  let parsed: CoverageReport
  try {
    parsed = JSON.parse(JSON.stringify(report)) as CoverageReport
  } catch (err) {
    failures.push(`JSON serialize failed: ${String(err)}`)
    parsed = report
  }
  if (typeof parsed.counts?.wikiChampionIndex !== 'number') {
    failures.push('missing counts.wikiChampionIndex')
  } else {
    lines.push('  ok JSON shape')
  }

  // Runtime ITEMS is the calculator catalog source of truth
  const runtimeCount = Object.keys(ITEMS).length
  const allItemsCount = Object.keys(ALL_ITEMS).length
  if (report.counts.runtimeItems !== runtimeCount) {
    failures.push(
      `runtimeItems ${report.counts.runtimeItems} ≠ Object.keys(ITEMS).length ${runtimeCount}`,
    )
  } else if (report.counts.generatedAllItems !== allItemsCount) {
    failures.push(
      `generatedAllItems ${report.counts.generatedAllItems} ≠ ALL_ITEMS ${allItemsCount}`,
    )
  } else if (runtimeCount === allItemsCount) {
    // Still ok if equal, but current repo should differ (merge adds GAME rows).
    lines.push('  ok runtime ITEMS count source (equals ALL_ITEMS in this tree)')
  } else {
    lines.push(
      `  ok runtime ITEMS count source (${runtimeCount} vs ALL_ITEMS ${allItemsCount})`,
    )
  }

  if (
    report.counts.itemPassives + report.counts.itemNoHookUnreviewed !==
    report.counts.runtimeItems
  ) {
    failures.push(
      `itemPassives (${report.counts.itemPassives}) + noHook (${report.counts.itemNoHookUnreviewed}) ≠ runtimeItems (${report.counts.runtimeItems})`,
    )
  } else {
    lines.push('  ok item hook / no-hook partition')
  }

  // Deterministic human output
  const h1 = formatHuman(report)
  const h2 = formatHuman(buildReport())
  if (h1 !== h2) {
    failures.push('human output not byte-stable across two builds')
  } else if (h1.includes('generatedAt:')) {
    failures.push('human output must not include wall-clock generatedAt')
  } else {
    lines.push('  ok deterministic human output')
  }

  // Manual coverage alone cannot imply trust
  const hypothetical = computeCoverageFlags({
    curatedManualModelCount: report.counts.wikiChampionIndex,
    wikiChampionCount: report.counts.wikiChampionIndex,
    keystonesMissingHooks: [],
    timelines: report.timelines.map((tl) => ({
      ...tl,
      missingCombatDefinitions: [],
      unresolvedWikiIds: [],
      champions: tl.champions.map((c) => ({
        ...c,
        modeling: 'curated' as const,
        missingCombatDefinition: false,
      })),
    })),
    hasItemReviewLedger: true,
    hasExplicitValidationEvidence: false,
  })
  if (!hypothetical.fullManualModelCoverage) {
    failures.push('hypothetical full manual model should be true')
  }
  if (hypothetical.fullTrustedCoverage) {
    failures.push(
      'fullTrustedCoverage must stay false without validation evidence even when manual model is complete',
    )
  } else {
    lines.push('  ok full manual coverage does not imply trust')
  }

  const syntheticIssues = collectStructuralIssues({
    meta: { patch: '0.0.0', counts: { champions: 999, runes: 1, keystones: 99 } },
    wikiIds: ['Aatrox'],
    runtimeIds: ['Aatrox'],
    gameIds: ['Aatrox'],
    curatedIds: ['Aatrox'],
    wikiSet: new Set(['Aatrox']),
    timelines: [
      {
        file: 'public/data/fake_timeline.json',
        id: 'fake',
        name: 'fake',
        patch: '0',
        committed: true,
        builtinId: null,
        participants: 1,
        champions: [
          {
            championName: 'NotAChamp',
            modeling: 'unresolved',
            inWikiIndex: false,
            inRuntimeChampions: false,
            missingCombatDefinition: true,
          },
        ],
        missingCombatDefinitions: ['NotAChamp'],
        unresolvedWikiIds: ['NotAChamp'],
        generatedOnly: [],
        curatedOrOverride: [],
      },
    ],
    passiveUnknownItemIds: ['999999'],
    observedVsMeta: [
      { field: 'champions', meta: 999, observed: 1, ok: false },
      {
        field: 'runes',
        meta: 1,
        observed: Object.keys(ALL_RUNES).length,
        ok: false,
      },
      {
        field: 'keystones',
        meta: 99,
        observed: KEYSTONE_RUNES.length,
        ok: false,
      },
    ],
  })
  const codes = new Set(syntheticIssues.map((i) => i.code))
  for (const need of [
    'impossible_counts',
    'timeline_unresolved',
    'unknown_ids',
  ]) {
    if (!codes.has(need)) failures.push(`synthetic missing code ${need}`)
  }
  if (codes.has('impossible_counts')) {
    lines.push('  ok synthetic structural detection')
  }

  const check = runCheck(report)
  if (!check.ok) {
    failures.push(`live --check unexpected fail: ${check.lines.join(' | ')}`)
  } else {
    lines.push('  ok live --check')
  }

  const strict = runStrict(report)
  if (report.coverage.fullTrustedCoverage) {
    failures.push(
      'fullTrustedCoverage unexpectedly true — refuse to claim trust without evidence',
    )
  } else if (strict.ok) {
    failures.push('--strict unexpectedly passed while fullTrustedCoverage is false')
  } else if (
    !strict.lines.some((l) =>
      l.includes('no explicit patch/numerical/empirical validation evidence'),
    )
  ) {
    failures.push('--strict must mention missing validation evidence')
  } else {
    lines.push('  ok live --strict fails with validation gate')
  }

  if (report.counts.wikiChampionIndex < 100) {
    failures.push('wiki index unexpectedly small')
  }
  if (report.counts.curatedCore < 1) {
    failures.push('expected at least one curated champion')
  }
  if (report.counts.itemPassives < 1) {
    failures.push('expected at least one ITEM_PASSIVE')
  }

  if (failures.length) {
    return {
      ok: false,
      lines: [...lines, ...failures.map((f) => `  FAIL ${f}`)],
    }
  }
  return { ok: true, lines: [...lines, 'self-test passed'] }
}

// ---------------------------------------------------------------------------
// CLI
// ---------------------------------------------------------------------------

function parseArgs(argv: string[]) {
  return {
    json: argv.includes('--json'),
    check: argv.includes('--check'),
    strict: argv.includes('--strict'),
    selfTest: argv.includes('--self-test'),
  }
}

function main(): void {
  const args = parseArgs(process.argv.slice(2))

  if (args.selfTest) {
    const result = runSelfTest()
    console.log(result.lines.join('\n'))
    process.exit(result.ok ? 0 : 1)
  }

  const report = buildReport()

  if (args.json && !args.check && !args.strict) {
    console.log(JSON.stringify(report, null, 2))
    process.exit(0)
  }

  if (args.check || args.strict) {
    const parts: string[] = []
    let exit = 0

    if (args.check) {
      const result = runCheck(report)
      parts.push(...result.lines)
      if (!result.ok) exit = 1
    }
    if (args.strict) {
      const result = runStrict(report)
      parts.push(...result.lines)
      if (!result.ok) exit = 1
    }

    if (args.json) {
      console.log(
        JSON.stringify(
          {
            report,
            check: args.check ? runCheck(report) : undefined,
            strict: args.strict ? runStrict(report) : undefined,
          },
          null,
          2,
        ),
      )
    } else {
      console.log(parts.join('\n'))
    }
    process.exit(exit)
  }

  console.log(formatHuman(report))
  process.exit(0)
}

main()
