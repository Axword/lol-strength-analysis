const MAP_SPAN = 14870

const CHAMP_ID_FIX: Record<string, string> = {
  chogath: 'Chogath',
  missfortune: 'MissFortune',
  monkeyking: 'MonkeyKing',
  jarvaniv: 'JarvanIV',
  leesin: 'LeeSin',
  masteryi: 'MasterYi',
  tahmkench: 'TahmKench',
  xinzhao: 'XinZhao',
  aurelionsol: 'AurelionSol',
  belveth: 'Belveth',
  renataglasc: 'Renata',
  nunu: 'Nunu',
  kogmaw: 'KogMaw',
  reksai: 'RekSai',
  ksante: 'KSante',
  drmundo: 'DrMundo',
  twistedfate: 'TwistedFate',
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function champId(raw: unknown): string {
  const text = String(raw || '').trim()
  if (!text) return 'Unknown'
  const key = text.toLowerCase().replace(/[^a-z0-9]/g, '')
  if (CHAMP_ID_FIX[key]) return CHAMP_ID_FIX[key]
  if (text[0] === text[0].toUpperCase() && !text.includes(' ')) return text
  return text[0].toUpperCase() + text.slice(1)
}

function riotToNorm(x: number, z: number): { x: number; y: number } {
  return {
    x: Math.round(Math.max(0, Math.min(1, x / MAP_SPAN)) * 1e5) / 1e5,
    y: Math.round(Math.max(0, Math.min(1, z / MAP_SPAN)) * 1e5) / 1e5,
  }
}

function canonicalGameTimeMs(value: unknown): number {
  const n = Number(value)
  if (!Number.isFinite(n) || n < 0 || Math.abs(n - Math.round(n)) > 1e-6) {
    throw new Error(`Invalid rfc461 gameTime: ${String(value)}`)
  }
  return Math.round(n)
}

function itemIds(items: unknown): number[] {
  if (!Array.isArray(items)) return []
  const out: number[] = []
  for (const item of items) {
    const raw = isRecord(item) ? item.itemID ?? item.itemId ?? 0 : item
    const n = Number(raw)
    if (Number.isFinite(n) && n > 0) out.push(Math.trunc(n))
  }
  return out
}

function healthKnown(participant: Record<string, unknown>): boolean {
  const source = participant.healthSource
  if (source === 'unavailable_replay_api' || source === 'unavailable' || source === 'unknown') {
    return false
  }
  return 'health' in participant || 'healthMax' in participant
}

function combatStatsKnown(participant: Record<string, unknown>): boolean {
  const source = participant.combatStatsSource
  if (source === 'unavailable_replay_api' || source === 'unavailable' || source === 'unknown') {
    return false
  }
  return (
    'attackDamage' in participant ||
    'abilityPower' in participant ||
    'armor' in participant ||
    'magicResist' in participant ||
    'attackSpeed' in participant ||
    source == null
  )
}

function abilityRanksKnown(participant: Record<string, unknown>): boolean {
  const source = participant.abilityRanksSource
  return !(source === 'unavailable_replay_api' || source === 'unavailable' || source === 'unknown')
}

function looksLikeRfc461Jsonl(text: string): boolean {
  for (const line of text.split(/\r?\n/)) {
    const trimmed = line.trim()
    if (!trimmed) continue
    try {
      const row = JSON.parse(trimmed) as unknown
      return isRecord(row) && typeof row.rfc461Schema === 'string'
    } catch {
      return false
    }
  }
  return false
}

/** Build a GameTimeline-shaped object from canonical rfc461 JSONL text (browser-safe). */
export function buildTimelineFromRfc461Jsonl(
  text: string,
  opts: { id?: string; name?: string; patch?: string; artifact?: string } = {},
): Record<string, unknown> {
  let gameInfo: Record<string, unknown> | null = null
  let coverage: Record<string, unknown> | null = null
  let gameEnd: Record<string, unknown> | null = null
  const statsRows: Record<string, unknown>[] = []

  for (const line of text.split(/\r?\n/)) {
    const trimmed = line.trim()
    if (!trimmed) continue
    let row: unknown
    try {
      row = JSON.parse(trimmed)
    } catch {
      throw new Error('JSONL contains a non-JSON line.')
    }
    if (!isRecord(row)) throw new Error('JSONL rows must be objects.')
    const schema = row.rfc461Schema
    if (schema === 'rofl_coverage') coverage = row
    else if (schema === 'game_info') gameInfo = row
    else if (schema === 'stats_update') statsRows.push(row)
    else if (schema === 'game_end') gameEnd = row
  }

  if (!gameInfo) throw new Error('JSONL missing game_info.')
  if (statsRows.length === 0) throw new Error('JSONL missing stats_update rows.')

  const participants = (Array.isArray(gameInfo.participants) ? gameInfo.participants : []).map(
    (raw, index) => {
      if (!isRecord(raw)) throw new Error(`game_info participant ${index + 1} is invalid.`)
      return {
        participantID: Number(raw.participantID),
        summonerName: String(raw.summonerName || raw.playerName || ''),
        championName: champId(raw.championName || 'Unknown'),
        teamID: Number(raw.teamID || 100),
        role: String(raw.role || 'NONE'),
        keystoneID: raw.keystoneID as number | undefined,
      }
    },
  )

  const source =
    coverage && typeof coverage.source === 'string' ? coverage.source : 'live_stats_jsonl'

  const frames = statsRows.map((row) => {
    const t = canonicalGameTimeMs(row.gameTime || 0)
    const units = (Array.isArray(row.participants) ? row.participants : []).map((raw) => {
      if (!isRecord(raw)) throw new Error(`stats_update at ${t} has an invalid participant.`)
      const pos = isRecord(raw.position) ? raw.position : {}
      const { x, y } = riotToNorm(Number(pos.x || 0), Number(pos.z || 0))
      const hpKnown = healthKnown(raw)
      const combatKnown = combatStatsKnown(raw)
      const ranksKnown = abilityRanksKnown(raw)
      const hp = hpKnown ? Number(raw.health || 0) : 0
      const hpMax = hpKnown ? Number(raw.healthMax || hp || 1) : 0
      return {
        pid: Number(raw.participantID),
        champ: champId(raw.championName || 'Unknown'),
        name: String(raw.playerName || raw.summonerName || ''),
        team: Number(raw.teamID || 100),
        role: String(raw.role || 'NONE'),
        level: Number(raw.level || 1),
        hp: Math.round(hp),
        hpMax: Math.round(hpMax),
        alive: raw.alive !== false,
        hpKnown,
        combatStatsKnown: combatKnown,
        abilityRanksKnown: ranksKnown,
        ad: combatKnown ? Math.round(Number(raw.attackDamage || 0)) : 0,
        ap: combatKnown ? Math.round(Number(raw.abilityPower || 0)) : 0,
        armor: combatKnown ? Math.round(Number(raw.armor || 0)) : 0,
        mr: combatKnown ? Math.round(Number(raw.magicResist || 0)) : 0,
        as: combatKnown ? Math.round(Number(raw.attackSpeed || 100)) : 100,
        x,
        y,
        positionSource:
          typeof raw.positionSource === 'string'
            ? raw.positionSource
            : source === 'rofl2'
              ? 'fountain_placeholder'
              : 'live_stats_position',
        items: itemIds(raw.items),
        q: Number(raw.ability1Level || 0),
        w: Number(raw.ability2Level || 0),
        e: Number(raw.ability3Level || 0),
        r: Number(raw.ability4Level || 0),
      }
    })
    return { t, units }
  })

  let durationMs = frames[frames.length - 1]?.t ?? 0
  if (gameEnd?.gameTime != null) {
    durationMs = Math.max(durationMs, canonicalGameTimeMs(gameEnd.gameTime))
  }

  const cadenceMs = frames.length >= 2 ? Math.max(1, frames[1].t - frames[0].t) : 1000
  const gameId = Number(gameInfo.gameID || 0)
  const matchCode =
    gameId > 0
      ? String(gameId)
      : String(opts.id || opts.name || 'local_jsonl').replace(/\D+/g, '') || 'local'

  const provenance: Record<string, unknown> = {
    ...((isRecord(coverage?.provenance) ? coverage.provenance : {}) as Record<string, unknown>),
  }
  if (!provenance.source) {
    Object.assign(provenance, {
      source,
      sourceKind: 'rfc461_jsonl',
      artifact: opts.artifact || 'local.jsonl',
      gameTimeUnit: 'milliseconds',
      coordinateSystem: 'riot_live_stats_sr',
      coordinateOffset: { x: 7500, z: 7500 },
      positionCoverage: 'full',
      hpCoverage: 'unknown',
      rosterMapping: 'game_info_participantID',
      placeholderPolicy: 'explicit_positionSource_only',
      notes: 'Opened from local rfc461 JSONL in Game Review.',
    })
  }
  provenance.matchCode = provenance.matchCode || matchCode
  if (gameId > 0) provenance.gameId = gameId
  if (opts.artifact) provenance.artifact = opts.artifact

  return {
    id: opts.id || matchCode,
    name: opts.name || matchCode,
    patch: opts.patch || String(gameInfo.gameVersion || 'unknown'),
    source,
    provenance,
    cadenceMs,
    participants,
    frameCount: frames.length,
    durationMs,
    frames,
    hasScoreboard: false,
    hasVision: false,
    hasCareerStats: false,
    hasMapObjects: false,
  }
}

export function isLikelyRfc461JsonlFile(fileName: string, text: string): boolean {
  return fileName.toLowerCase().endsWith('.jsonl') || looksLikeRfc461Jsonl(text)
}
