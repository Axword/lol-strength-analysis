import type { GameSnapshot, SnapshotImportResult, TeamSide } from './types'

function isFinite01(n: unknown): n is number {
  return typeof n === 'number' && Number.isFinite(n) && n >= 0 && n <= 1
}

export function parseSnapshotJson(raw: string): SnapshotImportResult {
  let data: unknown
  try {
    data = JSON.parse(raw)
  } catch {
    return { ok: false, error: 'Invalid JSON.' }
  }

  if (!data || typeof data !== 'object') {
    return { ok: false, error: 'Snapshot must be an object.' }
  }

  const s = data as Record<string, unknown>
  if (!Array.isArray(s.units) || s.units.length === 0) {
    return { ok: false, error: 'Snapshot needs a non-empty units array.' }
  }

  const units: GameSnapshot['units'] = []
  for (const u of s.units) {
    if (!u || typeof u !== 'object') {
      return { ok: false, error: 'Each unit must be an object.' }
    }
    const unit = u as Record<string, unknown>
    const loadout = unit.loadout as Record<string, unknown> | undefined
    const position = unit.position as Record<string, unknown> | undefined
    if (!loadout || typeof loadout.championId !== 'string') {
      return { ok: false, error: 'Each unit needs loadout.championId.' }
    }
    if (!position || !isFinite01(position.x) || !isFinite01(position.y)) {
      return { ok: false, error: 'Each unit needs position {x,y} in 0–1.' }
    }
    if (unit.team !== 'blue' && unit.team !== 'red') {
      return { ok: false, error: 'Each unit needs team "blue" or "red".' }
    }
    const team: TeamSide = unit.team

    units.push({
      id: String(unit.id ?? `${team}-${loadout.championId}`),
      team,
      role: (unit.role as GameSnapshot['units'][0]['role']) ?? 'mid',
      summonerName: String(unit.summonerName ?? loadout.championId),
      loadout: {
        championId: loadout.championId,
        level: Number(loadout.level ?? 1),
        itemIds: Array.isArray(loadout.itemIds)
          ? loadout.itemIds.map(String)
          : [],
        runeId:
          loadout.runeId === null || loadout.runeId === undefined
            ? null
            : String(loadout.runeId),
        ranks: {
          Q: Number((loadout.ranks as { Q?: number } | undefined)?.Q ?? loadout.abilityRank ?? 1),
          W: Number((loadout.ranks as { W?: number } | undefined)?.W ?? 1),
          E: Number((loadout.ranks as { E?: number } | undefined)?.E ?? 1),
          R: Number((loadout.ranks as { R?: number } | undefined)?.R ?? 0),
        },
        abilityRank: Number(loadout.abilityRank ?? 1),
        alive: unit.alive !== false,
        hpPct:
          typeof unit.hpPct === 'number'
            ? Math.min(1, Math.max(0, unit.hpPct))
            : 1,
      },
      position: { x: position.x, y: position.y },
      hpPct:
        typeof unit.hpPct === 'number'
          ? Math.min(1, Math.max(0, unit.hpPct))
          : undefined,
      alive: unit.alive !== false,
    })
  }

  const snapshot: GameSnapshot = {
    id: String(s.id ?? `import-${Date.now()}`),
    name: String(s.name ?? 'Imported snapshot'),
    patch: String(s.patch ?? 'unknown'),
    gameTimeSec: Number(s.gameTimeSec ?? 0),
    map: 'summoners_rift',
    units,
    notes: s.notes ? String(s.notes) : undefined,
  }

  return { ok: true, snapshot }
}

export function formatGameTime(sec: number): string {
  const m = Math.floor(sec / 60)
  const s = Math.floor(sec % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}
