/**
 * P5 Track 2 / R14 — browser-safe research AA/damage identity fold + playhead filter.
 *
 * Builds on R13 flag-gated overlay. Ports a no-`fs` subset of aa_bridge identity:
 * R22/R25 CastSpell + PUUID pid stamp → netId→champion/participantId.
 * Rejects unbound rows and pid-from-order (createHeroOrderFallback / invent).
 * Never invents AA/damage from HPΔ. researchOnly / not calculatorReady.
 */

export type ResearchActionKind = 'basic_attack' | 'damage_dealt'

export type ResearchActionRow = {
  kind: ResearchActionKind
  tSec: number
  tMs: number
  sourceNetId: number | null
  sourceChampion: string | null
  sourceParticipantId?: number | null
  targetNetId: number | null
  targetChampion: string | null
  targetParticipantId?: number | null
  amount: number | null
  researchOnly: true
  calculatorReady: false
}

export type ResearchIdentityParticipant = {
  netId: number
  champion: string
  participantID: number | null
  puuid?: string | null
  fullRiotId?: string | null
  pidStampMethod?: string | null
}

export type ResearchIdentityBind = {
  method: string
  complete: boolean
  createHeroOrderFallback: boolean
  pidStampMethod: string | null
  pidStampComplete: boolean
  seriesId?: string | null
  gameIndex?: number | null
  /** netId → champion from winners + participants */
  netIdToChampion: Map<number, string>
  byNetId: Map<number, ResearchIdentityParticipant>
}

export type ResearchActionOverlaySlim = {
  schema: string
  researchOnly: true
  calculatorReady: false
  label: string
  match?: {
    seriesId?: string
    gameIndex?: number
    gameID?: number
  }
  identity?: {
    method?: string
    winners?: Record<string, string>
    netIdToChampion?: Record<string, string>
    createHeroOrderFallback?: boolean
    complete?: boolean
    /** Optional embedded R22/R25-style participants (browser-safe). */
    participants?: Array<{
      netId?: number
      champion?: string
      participantID?: number | null
      puuid?: string | null
      fullRiotId?: string | null
      pidStampMethod?: string | null
    }>
    pidStampMethod?: string | null
    pidStampComplete?: boolean
  }
  window?: {
    killWindowStartSec?: number
    killWindowEndSec?: number
    knownKillSecond?: number
    label?: string
  }
  disclosures?: string[]
  events: ResearchActionRow[]
  stats?: {
    eventsKept?: number
    rejectedUnbound?: number
    schemaCounts?: Record<string, number>
  }
}

export type ResearchOverlayLoadResult = {
  ok: boolean
  rows: ResearchActionRow[]
  slim: ResearchActionOverlaySlim | null
  identity: ResearchIdentityBind | null
  disclosure: string
  rejectedUnbound: number
  rejectedOrderPid: number
  sourceUrl: string | null
  identityUrl: string | null
}

export type FoldResearchResult = {
  rows: ResearchActionRow[]
  rejectedUnbound: number
  rejectedOrderPid: number
  disclosure: string
}

export const RESEARCH_AA_OVERLAY_QUERY = 'researchAaOverlay'
export const DEFAULT_RESEARCH_OVERLAY_URL =
  '/data/research/aa-overlay/2970110-g1.slim.json'
/** R22 PUUID-stamped CastSpell identity (browser-safe subset). */
export const DEFAULT_RESEARCH_IDENTITY_URL =
  '/data/research/aa-overlay/2970110-g1.identity.json'
export const DEFAULT_PLAYHEAD_WINDOW_SEC = 20
export const DEFAULT_RESEARCH_SERIES_ID = '2970110'
export const DEFAULT_RESEARCH_GAME_INDEX = 1

const ALLOWED_PID_STAMP_METHODS = new Set([
  'slim_roster_puuid_join',
  'slim_roster_fullriotid_join',
  'puuid_join',
  'fullriotid_join',
])

/** URL/query flag — default OFF unless explicitly 1/true. */
export function readResearchAaOverlayFlag(
  search: string | null | undefined = typeof window !== 'undefined'
    ? window.location.search
    : '',
): boolean {
  if (!search) return false
  const q = new URLSearchParams(
    search.startsWith('?') ? search : `?${search}`,
  )
  const v = q.get(RESEARCH_AA_OVERLAY_QUERY) ?? q.get('researchAa')
  return v === '1' || v === 'true'
}

/**
 * External research overlays are match-specific. Refuse loading the bundled
 * 2970110-g1 rows for any other timeline, even when the query flag is enabled.
 */
export function timelineMatchesDefaultResearchOverlay(
  timeline: TimelineActionBridgeInput | null | undefined,
): boolean {
  if (!timeline) return false
  return (
    String(timeline.provenance?.gridSeriesId ?? '') ===
      DEFAULT_RESEARCH_SERIES_ID &&
    Number(timeline.provenance?.gridGameIndex) === DEFAULT_RESEARCH_GAME_INDEX
  )
}

export function parseNetIdKey(key: string): number | null {
  if (!key) return null
  const nid =
    key.startsWith('0x') || key.startsWith('0X')
      ? Number.parseInt(key, 16)
      : Number(key)
  return Number.isFinite(nid) ? nid : null
}

export function parseIdentityWinners(
  winners: Record<string, string> | null | undefined,
): Map<number, string> {
  const map = new Map<number, string>()
  if (!winners) return map
  for (const [k, champ] of Object.entries(winners)) {
    if (!champ) continue
    const nid = parseNetIdKey(k)
    if (nid == null) continue
    map.set(nid, champ)
  }
  return map
}

/**
 * Browser-safe R22/R25 identity parse (no fs).
 * Accepts full CastSpell pid-stamped JSON or research-aa-identity-browser-v1.
 * Never invents participantID from CreateHero / sorted-netId order.
 */
export function parseResearchIdentityArtifact(
  data: unknown,
): ResearchIdentityBind | null {
  if (!data || typeof data !== 'object') return null
  const root = data as Record<string, unknown>
  const bindRaw =
    root.identityBinding && typeof root.identityBinding === 'object'
      ? (root.identityBinding as Record<string, unknown>)
      : null

  const createHeroOrderFallback = Boolean(
    bindRaw?.createHeroOrderFallback ?? root.createHeroOrderFallback,
  )

  const winners = parseIdentityWinners(
    (root.winners as Record<string, string> | undefined) ?? undefined,
  )
  const byNetId = new Map<number, ResearchIdentityParticipant>()
  const netIdToChampion = new Map<number, string>(winners)

  const participants = Array.isArray(bindRaw?.participants)
    ? bindRaw!.participants
    : Array.isArray(root.participants)
      ? root.participants
      : []

  for (const raw of participants) {
    if (!raw || typeof raw !== 'object') continue
    const p = raw as Record<string, unknown>
    const nid = Number(p.netId)
    const champion = typeof p.champion === 'string' ? p.champion : null
    if (!Number.isFinite(nid) || !champion) continue
    // Never rewrite keys: Zaahen stays Zaahen; MonkeyKing stays MonkeyKing.
    netIdToChampion.set(nid, champion)
    const pidRaw = p.participantID
    const participantID =
      pidRaw != null && Number.isFinite(Number(pidRaw)) ? Number(pidRaw) : null
    const pidStampMethod =
      typeof p.pidStampMethod === 'string' ? p.pidStampMethod : null
    // Drop pid unless artifact discloses a non-order stamp method.
    const stampedPid =
      participantID != null &&
      pidStampMethod != null &&
      ALLOWED_PID_STAMP_METHODS.has(pidStampMethod)
        ? participantID
        : participantID != null &&
            (bindRaw?.pidStampMethod != null || root.pidStampMethod != null) &&
            ALLOWED_PID_STAMP_METHODS.has(
              String(bindRaw?.pidStampMethod ?? root.pidStampMethod),
            )
          ? participantID
          : null
    byNetId.set(nid, {
      netId: nid,
      champion,
      participantID: stampedPid,
      puuid: typeof p.puuid === 'string' ? p.puuid : null,
      fullRiotId: typeof p.fullRiotId === 'string' ? p.fullRiotId : null,
      pidStampMethod,
    })
  }

  // Champion-only winners when participants missing — pid stays null (no invent).
  for (const [nid, champ] of winners) {
    if (!byNetId.has(nid)) {
      byNetId.set(nid, {
        netId: nid,
        champion: champ,
        participantID: null,
        pidStampMethod: null,
      })
    }
  }

  if (netIdToChampion.size === 0 && byNetId.size === 0) return null

  const pidStampMethodRaw = bindRaw?.pidStampMethod ?? root.pidStampMethod
  return {
    method: String(
      bindRaw?.method ?? root.method ?? 'unknown',
    ),
    complete: Boolean(bindRaw?.complete ?? root.complete),
    createHeroOrderFallback,
    pidStampMethod:
      typeof pidStampMethodRaw === 'string' ? pidStampMethodRaw : null,
    pidStampComplete: Boolean(
      bindRaw?.pidStampComplete ?? root.pidStampComplete,
    ),
    seriesId:
      root.series != null
        ? String(root.series)
        : root.seriesId != null
          ? String(root.seriesId)
          : null,
    gameIndex:
      root.gameIndex != null && Number.isFinite(Number(root.gameIndex))
        ? Number(root.gameIndex)
        : null,
    netIdToChampion,
    byNetId,
  }
}

function identityFromSlim(
  slim: ResearchActionOverlaySlim,
): ResearchIdentityBind | null {
  if (!slim.identity) return null
  return parseResearchIdentityArtifact({
    method: slim.identity.method,
    createHeroOrderFallback: slim.identity.createHeroOrderFallback,
    complete: slim.identity.complete,
    winners: slim.identity.winners,
    pidStampMethod: slim.identity.pidStampMethod,
    pidStampComplete: slim.identity.pidStampComplete,
    identityBinding: {
      method: slim.identity.method,
      complete: slim.identity.complete,
      createHeroOrderFallback: slim.identity.createHeroOrderFallback,
      pidStampMethod: slim.identity.pidStampMethod,
      pidStampComplete: slim.identity.pidStampComplete,
      participants: slim.identity.participants,
    },
  })
}

function resolveChamp(
  netId: number | null,
  labeled: string | null | undefined,
  identity: ResearchIdentityBind | null,
): string | null {
  if (netId != null && identity) {
    const fromId = identity.netIdToChampion.get(netId)
    if (fromId) return fromId
  }
  return labeled ?? null
}

function resolvePid(
  netId: number | null,
  identity: ResearchIdentityBind | null,
): number | null {
  if (netId == null || !identity) return null
  const row = identity.byNetId.get(netId)
  return row?.participantID ?? null
}

/**
 * Fold emit-like rows with supplied identity.
 * - Maps attacker/target netId → champion / participantId via identity only
 * - Rejects createHeroOrderFallback (pid-from-order)
 * - Rejects unbound netIds (no ghost champs)
 * - Never trusts event participantId as order-pid authority
 */
export function foldEventsWithIdentity(
  events: Array<Partial<ResearchActionRow> | null | undefined>,
  identity: ResearchIdentityBind | null,
): FoldResearchResult {
  if (!Array.isArray(events) || events.length === 0) {
    return {
      rows: [],
      rejectedUnbound: 0,
      rejectedOrderPid: 0,
      disclosure:
        'No decode actions — research emit/slim missing (not invented)',
    }
  }

  if (identity?.createHeroOrderFallback) {
    return {
      rows: [],
      rejectedUnbound: 0,
      rejectedOrderPid: events.length,
      disclosure:
        'Identity createHeroOrderFallback=true — refusing pid-from-order overlay',
    }
  }

  const rows: ResearchActionRow[] = []
  let rejectedUnbound = 0
  let rejectedOrderPid = 0

  for (const raw of events) {
    if (!raw || (raw.kind !== 'basic_attack' && raw.kind !== 'damage_dealt')) {
      rejectedUnbound++
      continue
    }
    const tSec = Number(raw.tSec)
    const tMs =
      raw.tMs != null && Number.isFinite(Number(raw.tMs))
        ? Number(raw.tMs)
        : Number.isFinite(tSec)
          ? Math.round(tSec * 1000)
          : NaN
    if (!Number.isFinite(tSec) || !Number.isFinite(tMs)) {
      rejectedUnbound++
      continue
    }

    const sourceNetId =
      raw.sourceNetId != null && Number.isFinite(Number(raw.sourceNetId))
        ? Number(raw.sourceNetId)
        : null
    const targetNetId =
      raw.targetNetId != null && Number.isFinite(Number(raw.targetNetId))
        ? Number(raw.targetNetId)
        : null

    const eventSourcePid =
      raw.sourceParticipantId != null &&
      Number.isFinite(Number(raw.sourceParticipantId))
        ? Number(raw.sourceParticipantId)
        : null
    const eventTargetPid =
      raw.targetParticipantId != null &&
      Number.isFinite(Number(raw.targetParticipantId))
        ? Number(raw.targetParticipantId)
        : null

    // Scrambled / disagreeing pid vs stamped identity → reject (no ghost bind).
    // If identity has champ but no stamped pid: strip event pid (never invent).
    if (identity) {
      const stampedSource = resolvePid(sourceNetId, identity)
      if (
        sourceNetId != null &&
        eventSourcePid != null &&
        stampedSource != null &&
        eventSourcePid !== stampedSource
      ) {
        rejectedOrderPid++
        continue
      }
      const stampedTarget = resolvePid(targetNetId, identity)
      if (
        targetNetId != null &&
        eventTargetPid != null &&
        stampedTarget != null &&
        eventTargetPid !== stampedTarget
      ) {
        rejectedOrderPid++
        continue
      }
    }

    // When identity supplied, source netId must be in the bind (no unbound ghosts).
    if (
      identity &&
      sourceNetId != null &&
      !identity.netIdToChampion.has(sourceNetId)
    ) {
      rejectedUnbound++
      continue
    }

    const sourceChampion = resolveChamp(
      sourceNetId,
      raw.sourceChampion,
      identity,
    )
    const targetChampion = resolveChamp(
      targetNetId,
      raw.targetChampion,
      identity,
    )

    if (!sourceChampion && !targetChampion) {
      rejectedUnbound++
      continue
    }

    const amount =
      raw.amount != null && Number.isFinite(Number(raw.amount))
        ? Number(raw.amount)
        : null

    rows.push({
      kind: raw.kind,
      tSec,
      tMs,
      sourceNetId,
      sourceChampion,
      // Pid only from stamped identity — never event/order invent.
      sourceParticipantId: resolvePid(sourceNetId, identity),
      targetNetId,
      targetChampion,
      targetParticipantId: resolvePid(targetNetId, identity),
      amount,
      researchOnly: true,
      calculatorReady: false,
    })
  }

  rows.sort((a, b) => a.tMs - b.tMs)
  return {
    rows,
    rejectedUnbound,
    rejectedOrderPid,
    disclosure:
      rows.length === 0
        ? 'No identity-bound research AA/damage rows after fold'
        : 'research overlay · not calculatorReady',
  }
}

/**
 * Fold a slim overlay artifact for UI.
 * Prefer external R22/R25 identity when supplied; else slim.identity.
 * Rejects createHeroOrderFallback / unbound / order-pid invent.
 */
export function foldResearchOverlaySlim(
  slim: ResearchActionOverlaySlim | null | undefined,
  identityOverride: ResearchIdentityBind | null = null,
): FoldResearchResult {
  if (!slim || !Array.isArray(slim.events)) {
    return {
      rows: [],
      rejectedUnbound: 0,
      rejectedOrderPid: 0,
      disclosure:
        'No decode actions — research emit/slim missing (not invented)',
    }
  }
  if (slim.identity?.createHeroOrderFallback) {
    return {
      rows: [],
      rejectedUnbound: 0,
      rejectedOrderPid: slim.events.length,
      disclosure:
        'Identity createHeroOrderFallback=true — refusing pid-from-order overlay',
    }
  }

  const identity =
    identityOverride ??
    identityFromSlim(slim) ??
    parseResearchIdentityArtifact({
      method: slim.identity?.method,
      createHeroOrderFallback: slim.identity?.createHeroOrderFallback,
      complete: slim.identity?.complete,
      winners: slim.identity?.winners,
      // winners-only path: no pid stamp — pids stay null (honest).
    })

  const folded = foldEventsWithIdentity(slim.events, identity)
  return {
    ...folded,
    disclosure:
      folded.rows.length === 0
        ? folded.disclosure
        : slim.label || folded.disclosure,
  }
}

/** Second-precise playhead window filter (ms timestamps). */
export function filterRowsNearPlayhead(
  rows: ResearchActionRow[],
  playheadMs: number,
  windowSec: number = DEFAULT_PLAYHEAD_WINDOW_SEC,
): ResearchActionRow[] {
  if (!Number.isFinite(playheadMs) || !Number.isFinite(windowSec)) return []
  const half = Math.max(0, windowSec) * 1000
  const lo = playheadMs - half
  const hi = playheadMs + half
  return rows.filter((r) => r.tMs >= lo && r.tMs <= hi)
}

/**
 * Track 5 — when selection exists, keep rows that touch a selected champion.
 * Empty selection ⇒ no extra filter (playhead window still applies upstream).
 */
export function filterRowsForSelectedChampions(
  rows: ResearchActionRow[],
  selectedChampions: readonly string[] | null | undefined,
): ResearchActionRow[] {
  if (!selectedChampions || selectedChampions.length === 0) return rows
  const want = new Set(
    selectedChampions.map((c) => c.trim().toLowerCase()).filter(Boolean),
  )
  if (want.size === 0) return rows
  return rows.filter((r) => {
    const src = r.sourceChampion?.trim().toLowerCase()
    const tgt = r.targetChampion?.trim().toLowerCase()
    return (src != null && want.has(src)) || (tgt != null && want.has(tgt))
  })
}

/**
 * Track 3 — research overlay OFF must not fake a product AA timeline.
 * When disabled, callers see zero rows regardless of loaded emit.
 */
export function visibleResearchOverlayRows(
  enabled: boolean,
  rows: ResearchActionRow[],
): ResearchActionRow[] {
  return enabled ? rows : []
}

/**
 * Track 3 / G_send — product Send never attaches research AA/damage rows.
 * Unbound or invented overlay events cannot enter the calculator import path.
 */
export function productSendAttachesResearchActions(): false {
  return false
}

/**
 * P5 Track 3 — product Send never attaches research overlay AA/damage.
 * Always returns [] so invented/unbound AA cannot enter the import payload.
 */
export function productSendAttachedResearchActions(
  _overlayRows: ResearchActionRow[] | null | undefined,
): ResearchActionRow[] {
  return []
}

/**
 * Flag OFF ⇒ no product AA timeline rows (research overlay must not fake product).
 * Flag ON is still research-only; product auto-fill remains a separate fuse (F).
 */
export function productAaTimelineWhenOverlayOff(
  _overlayEnabled: boolean,
): ResearchActionRow[] {
  return []
}

/** Honest empty disclosure when holdout emit/slim is absent. */
export function holdoutMissingEmitDisclosure(matchLabel: string): string {
  return `No decode actions for ${matchLabel} — emit/slim missing (not invented)`
}

/** Track 6 — holdout overlay URL; missing file ⇒ honest empty (no invent). */
export const HOLDOUT_RESEARCH_OVERLAY_URL =
  '/data/research/aa-overlay/2970137-g1.slim.json'

/**
 * Adversarial: HP curve alone must never create AA/damage rows.
 * This helper documents the contract — callers must not pass HP deltas here.
 */
export function rowsFromHpCurveAloneForbidden(): ResearchActionRow[] {
  return []
}

/** Minimal timeline shape for product fuse → research AA panel bridge (R10 F). */
export type TimelineActionBridgeInput = {
  basicAttack?: ReadonlyArray<{
    tMs: number
    participantId: number
    netId: number
    targetParticipantId?: number
    targetNetId?: number
    researchOnly?: boolean
  }>
  damageDealt?: ReadonlyArray<{
    tMs: number
    participantId: number
    netId: number
    targetParticipantId?: number
    targetNetId?: number
    amount?: number
    researchOnly?: boolean
  }>
  actionEvents?: ReadonlyArray<{
    kind: ResearchActionKind
    tMs: number
    participantId: number
    netId: number
    targetParticipantId?: number
    targetNetId?: number
    amount?: number
    researchOnly?: boolean
  }>
  participants?: ReadonlyArray<{
    participantID: number
    championName?: string
  }>
  provenance?: {
    aaCoverage?: string
    damageCoverage?: string
    calculatorReady?: boolean
    gridSeriesId?: string
    gridGameIndex?: number
  }
}

export type TimelineActionBridgeResult = {
  rows: ResearchActionRow[]
  disclosure: string
  source: 'timeline_bridge' | 'empty'
  rejectedMissingIdentity: number
}

/**
 * R10 F — map identity-bound timeline basicAttack/damageDealt/actionEvents
 * into research overlay rows for GameReview. Never invents from HPΔ.
 * Requires netId + participantId on every kept row (order-only rejected upstream).
 * The panel row type stays non-calculator input. Product AA may be displayed,
 * but it remains separate from the calculatorReady decision and Send payload.
 */
export function rowsFromTimelineActionBridge(
  timeline: TimelineActionBridgeInput | null | undefined,
): TimelineActionBridgeResult {
  if (!timeline) {
    return {
      rows: [],
      disclosure: 'No timeline — decode bridge absent (not invented)',
      source: 'empty',
      rejectedMissingIdentity: 0,
    }
  }

  const champByPid = new Map<number, string>()
  for (const p of timeline.participants ?? []) {
    const pid = Number(p.participantID)
    const name = typeof p.championName === 'string' ? p.championName.trim() : ''
    if (Number.isFinite(pid) && pid > 0 && name) champByPid.set(pid, name)
  }

  const raw: Array<{
    kind: ResearchActionKind
    tMs: number
    participantId: number
    netId: number
    targetParticipantId?: number
    targetNetId?: number
    amount?: number
  }> = []

  for (const ev of timeline.basicAttack ?? []) {
    raw.push({
      kind: 'basic_attack',
      tMs: ev.tMs,
      participantId: ev.participantId,
      netId: ev.netId,
      targetParticipantId: ev.targetParticipantId,
      targetNetId: ev.targetNetId,
    })
  }
  for (const ev of timeline.damageDealt ?? []) {
    raw.push({
      kind: 'damage_dealt',
      tMs: ev.tMs,
      participantId: ev.participantId,
      netId: ev.netId,
      targetParticipantId: ev.targetParticipantId,
      targetNetId: ev.targetNetId,
      amount: ev.amount,
    })
  }
  for (const ev of timeline.actionEvents ?? []) {
    if (ev.kind !== 'basic_attack' && ev.kind !== 'damage_dealt') continue
    raw.push({
      kind: ev.kind,
      tMs: ev.tMs,
      participantId: ev.participantId,
      netId: ev.netId,
      targetParticipantId: ev.targetParticipantId,
      targetNetId: ev.targetNetId,
      amount: ev.amount,
    })
  }

  if (raw.length === 0) {
    return {
      rows: [],
      disclosure:
        'No timeline AA/damage arrays — decode bridge absent (not invented)',
      source: 'empty',
      rejectedMissingIdentity: 0,
    }
  }

  const rows: ResearchActionRow[] = []
  let rejectedMissingIdentity = 0
  for (const ev of raw) {
    const tMs = Number(ev.tMs)
    const netId = Number(ev.netId)
    const pid = Number(ev.participantId)
    if (
      !Number.isFinite(tMs) ||
      !Number.isFinite(netId) ||
      netId <= 0 ||
      !Number.isFinite(pid) ||
      pid <= 0
    ) {
      rejectedMissingIdentity++
      continue
    }
    const targetNetId =
      ev.targetNetId != null && Number.isFinite(Number(ev.targetNetId))
        ? Number(ev.targetNetId)
        : null
    const targetPid =
      ev.targetParticipantId != null &&
      Number.isFinite(Number(ev.targetParticipantId)) &&
      Number(ev.targetParticipantId) > 0
        ? Number(ev.targetParticipantId)
        : null
    const amount =
      ev.kind === 'damage_dealt' &&
      ev.amount != null &&
      Number.isFinite(Number(ev.amount))
        ? Number(ev.amount)
        : null
    rows.push({
      kind: ev.kind,
      tSec: tMs / 1000,
      tMs,
      sourceNetId: netId,
      sourceChampion: champByPid.get(pid) ?? null,
      sourceParticipantId: pid,
      targetNetId,
      targetChampion:
        targetPid != null ? (champByPid.get(targetPid) ?? null) : null,
      targetParticipantId: targetPid,
      amount,
      researchOnly: true,
      calculatorReady: false,
    })
  }

  rows.sort((a, b) => a.tMs - b.tMs)
  const aaCov = timeline.provenance?.aaCoverage ?? 'research_overlay'
  return {
    rows,
    disclosure:
      rows.length === 0
        ? 'Timeline AA/damage present but no identity-bound rows kept'
        : `embedded replay actions · ${aaCov} · separate from calculator readiness`,
    source: rows.length > 0 ? 'timeline_bridge' : 'empty',
    rejectedMissingIdentity,
  }
}

export function parseResearchOverlayJson(
  text: string,
): ResearchActionOverlaySlim | null {
  try {
    const data = JSON.parse(text) as ResearchActionOverlaySlim
    if (!data || typeof data !== 'object') return null
    if (!Array.isArray(data.events)) return null
    return {
      ...data,
      researchOnly: true,
      calculatorReady: false,
      label: data.label || 'research overlay · not calculatorReady',
      events: data.events,
    }
  } catch {
    return null
  }
}

export async function loadResearchActionOverlay(
  url: string = DEFAULT_RESEARCH_OVERLAY_URL,
  fetchImpl: typeof fetch = fetch,
  opts: { identityUrl?: string | null } = {},
): Promise<ResearchOverlayLoadResult> {
  const identityUrl =
    opts.identityUrl === undefined
      ? DEFAULT_RESEARCH_IDENTITY_URL
      : opts.identityUrl
  try {
    const res = await fetchImpl(url)
    if (!res.ok) {
      return {
        ok: false,
        rows: [],
        slim: null,
        identity: null,
        disclosure: `No decode actions — emit/slim missing (${res.status})`,
        rejectedUnbound: 0,
        rejectedOrderPid: 0,
        sourceUrl: url,
        identityUrl,
      }
    }
    const slim = parseResearchOverlayJson(await res.text())
    if (!slim) {
      return {
        ok: false,
        rows: [],
        slim: null,
        identity: null,
        disclosure: 'No decode actions — slim JSON invalid (not invented)',
        rejectedUnbound: 0,
        rejectedOrderPid: 0,
        sourceUrl: url,
        identityUrl,
      }
    }

    let identity: ResearchIdentityBind | null = null
    if (identityUrl) {
      try {
        const idRes = await fetchImpl(identityUrl)
        if (idRes.ok) {
          identity = parseResearchIdentityArtifact(await idRes.json())
        }
      } catch {
        identity = null
      }
    }

    const folded = foldResearchOverlaySlim(slim, identity)
    return {
      ok: folded.rows.length > 0,
      rows: folded.rows,
      slim,
      identity,
      disclosure: folded.disclosure,
      rejectedUnbound: folded.rejectedUnbound,
      rejectedOrderPid: folded.rejectedOrderPid,
      sourceUrl: url,
      identityUrl,
    }
  } catch {
    return {
      ok: false,
      rows: [],
      slim: null,
      identity: null,
      disclosure: 'No decode actions — failed to load research overlay',
      rejectedUnbound: 0,
      rejectedOrderPid: 0,
      sourceUrl: url,
      identityUrl,
    }
  }
}

export function formatResearchActionRow(row: ResearchActionRow): string {
  const t = `${Math.floor(row.tSec / 60)}:${String(Math.floor(row.tSec % 60)).padStart(2, '0')}.${String(Math.floor((row.tSec % 1) * 10))}`
  const src =
    row.sourceChampion ??
    (row.sourceNetId != null ? `net:${row.sourceNetId}` : '?')
  const tgt =
    row.targetChampion ??
    (row.targetNetId != null ? `net:${row.targetNetId}` : '—')
  const amt =
    row.amount != null && Number.isFinite(row.amount)
      ? ` ${Math.round(row.amount)}`
      : ''
  return `${t}  ${row.kind}  ${src} → ${tgt}${amt}`
}
