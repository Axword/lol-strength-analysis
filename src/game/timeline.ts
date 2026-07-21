import type { FighterLoadout } from '../engine/types'
import { CHAMPIONS } from '../data/champions'
import { KEYSTONE_ID_TO_SLUG, resolveRuneId } from '../data/runes'
import type { GameSnapshot, GameUnit, LaneRole, TeamSide } from './types'
import { formatGameTime } from './parseSnapshot'

export interface TimelineParticipant {
  participantID: number
  summonerName: string
  championName: string
  teamID: number
  role: string
  keystoneID?: number
}

export interface TimelineUnitFrame {
  pid: number
  champ: string
  name: string
  team: number
  role: string
  level: number
  hp: number
  hpMax: number
  alive: boolean
  ad: number
  ap: number
  armor: number
  mr: number
  as: number
  x: number
  y: number
  items: number[]
  q: number
  w: number
  e: number
  r: number
  career?: import('../engine/careerStats').ChampCareerStats
}

export interface TimelineFrame {
  t: number
  units: TimelineUnitFrame[]
  score?: import('../engine/objectives').ScoreboardState
  wards?: import('../engine/vision').VisionWard[]
  mapObjects?: import('./types').MapObjectsState
}

export interface GameTimeline {
  id: string
  name: string
  patch: string
  source: string
  /** Native stats_update interval in the Riot feed (~1000ms for this file). */
  cadenceMs?: number
  participants: TimelineParticipant[]
  frameCount: number
  durationMs: number
  frames: TimelineFrame[]
}

/** Consumables / trinkets / lane quests — skip in roster + calculator slots. */
const NON_COMBAT_ITEMS = new Set([
  '2003', '2010', '2031', '2055', '3340', '3341', '3363', '3364', '3513',
  '3599', '2422', '0',
  // Role quest trackers (not real inventory)
  '1201', '1202', '1203', '1204', '1205', '1206', '1207', '1208', '1209',
  '1210', '1211', '1222',
])

function combatItemIds(items: number[]): string[] {
  const out: string[] = []
  for (const id of items) {
    if (id == null || id === 0) continue
    const sid = String(id)
    if (sid === 'None' || sid === 'null') continue
    if (NON_COMBAT_ITEMS.has(sid)) continue
    out.push(sid)
    if (out.length >= 6) break
  }
  return out
}

function runeFromKeystone(keystoneID?: number): string | null {
  if (keystoneID == null || !Number.isFinite(keystoneID)) return null
  const mapped = KEYSTONE_ID_TO_SLUG[keystoneID]
  if (mapped) return mapped
  const resolved = resolveRuneId(keystoneID)
  return resolved?.id ?? null
}

function roleToLane(role: string): LaneRole {
  switch (role) {
    case 'Top':
      return 'top'
    case 'Jungle':
      return 'jungle'
    case 'Middle':
      return 'mid'
    case 'Bottom':
      return 'bot'
    case 'Support':
      return 'support'
    default:
      return 'mid'
  }
}

function teamSide(teamID: number): TeamSide {
  return teamID === 100 ? 'blue' : 'red'
}

export function unitToLoadout(
  u: TimelineUnitFrame,
  keystoneID?: number,
): FighterLoadout {
  const hpPct = u.hpMax > 0 ? u.hp / u.hpMax : u.alive ? 1 : 0
  return {
    championId: u.champ,
    level: u.level,
    itemIds: combatItemIds(u.items),
    runeId: runeFromKeystone(keystoneID),
    ranks: {
      Q: u.q,
      W: u.w,
      E: u.e,
      R: u.r,
    },
    abilityRank: Math.max(1, u.q, u.w, u.e),
    alive: u.alive !== false && u.hp > 0,
    hpPct,
    position: { x: u.x, y: u.y },
    liveStats: {
      hp: Math.max(0, u.hp),
      hpMax: Math.max(1, u.hpMax),
      armor: u.armor,
      mr: u.mr,
      ad: u.ad,
      ap: u.ap,
      // Feed `as` is % of base (100 = baseline). Convert with champ base APS.
      attackSpeed: (() => {
        const base = CHAMPIONS[u.champ]?.stats.attackspeed ?? 0.625
        return Math.max(0.2, base * ((u.as || 100) / 100))
      })(),
    },
  }
}

export function frameToSnapshot(
  timeline: GameTimeline,
  frameIndex: number,
): GameSnapshot {
  const frame = timeline.frames[Math.min(timeline.frames.length - 1, Math.max(0, frameIndex))]
  return frameDataToSnapshot(timeline, frame, frame.t / 1000)
}

/** Snapshot at an arbitrary game time — lerps champ positions between frames. */
export function snapshotAtTime(timeline: GameTimeline, timeMs: number): GameSnapshot {
  const frames = timeline.frames
  if (!frames.length) {
    return frameToSnapshot(timeline, 0)
  }
  const t = Math.max(0, Math.min(timeMs, timeline.durationMs || frames[frames.length - 1].t))
  const i = findFrameIndex(timeline, t)
  const a = frames[i]
  const b = frames[Math.min(frames.length - 1, i + 1)]
  if (a === b || b.t <= a.t || t <= a.t) {
    return frameDataToSnapshot(timeline, a, t / 1000)
  }
  if (t >= b.t) {
    return frameDataToSnapshot(timeline, b, t / 1000)
  }
  const alpha = (t - a.t) / (b.t - a.t)
  return lerpFramesToSnapshot(timeline, a, b, alpha, t / 1000)
}

function frameDataToSnapshot(
  timeline: GameTimeline,
  frame: TimelineFrame,
  gameTimeSec: number,
): GameSnapshot {
  const keystoneByPid = new Map(
    timeline.participants.map((p) => [p.participantID, p.keystoneID]),
  )

  const units: GameUnit[] = frame.units.map((u) => ({
    id: `p${u.pid}`,
    team: teamSide(u.team),
    role: roleToLane(u.role),
    summonerName: u.name,
    loadout: unitToLoadout(u, keystoneByPid.get(u.pid)),
    position: { x: u.x, y: u.y },
    hpPct: u.hpMax > 0 ? u.hp / u.hpMax : 0,
    alive: u.alive !== false && u.hp > 0,
    career: u.career,
  }))

  return {
    id: `${timeline.id}-t${Math.round(gameTimeSec * 1000)}`,
    name: `${timeline.name} @ ${formatGameTime(gameTimeSec)}`,
    patch: timeline.patch,
    gameTimeSec,
    map: 'summoners_rift',
    units,
    notes: `Live frame from ${timeline.source}`,
    score: frame.score,
    wards: frame.wards,
    mapObjects: frame.mapObjects,
  }
}

function lerp(a: number, b: number, t: number) {
  return a + (b - a) * t
}

function lerpFramesToSnapshot(
  timeline: GameTimeline,
  a: TimelineFrame,
  b: TimelineFrame,
  alpha: number,
  gameTimeSec: number,
): GameSnapshot {
  const keystoneByPid = new Map(
    timeline.participants.map((p) => [p.participantID, p.keystoneID]),
  )
  const nextByPid = new Map(b.units.map((u) => [u.pid, u]))

  // Discrete state (score / wards / camps) from the earlier frame until the next tick
  const base = a
  const units: GameUnit[] = base.units.map((u) => {
    const v = nextByPid.get(u.pid)
    const aliveA = u.alive !== false && u.hp > 0
    const aliveB = v ? v.alive !== false && v.hp > 0 : aliveA
    // Don't lerp through the map on death/respawn teleports
    const canLerp = Boolean(v && aliveA && aliveB)
    const x = canLerp ? lerp(u.x, v!.x, alpha) : u.x
    const y = canLerp ? lerp(u.y, v!.y, alpha) : u.y
    const hp = canLerp ? lerp(u.hp, v!.hp, alpha) : u.hp
    const hpMax = u.hpMax > 0 ? u.hpMax : 1
    return {
      id: `p${u.pid}`,
      team: teamSide(u.team),
      role: roleToLane(u.role),
      summonerName: u.name,
      loadout: unitToLoadout(u, keystoneByPid.get(u.pid)),
      position: { x, y },
      hpPct: hp / hpMax,
      alive: aliveA,
      career: u.career,
    }
  })

  // Camp timers are absolute ms — recompute alive from playhead for smooth badges
  let mapObjects = base.mapObjects
  if (mapObjects) {
    const tMs = gameTimeSec * 1000
    mapObjects = {
      ...mapObjects,
      camps: mapObjects.camps.map((c) => {
        if (c.respawnsAtMs == null) return c
        const alive = tMs >= c.respawnsAtMs
        return alive
          ? { ...c, alive: true, respawnsAtMs: undefined }
          : { ...c, alive: false, respawnsAtMs: c.respawnsAtMs }
      }),
    }
  }

  return {
    id: `${timeline.id}-t${Math.round(gameTimeSec * 1000)}`,
    name: `${timeline.name} @ ${formatGameTime(gameTimeSec)}`,
    patch: timeline.patch,
    gameTimeSec,
    map: 'summoners_rift',
    units,
    notes: `Live frame from ${timeline.source}`,
    score: base.score,
    wards: base.wards,
    mapObjects,
  }
}

export function findFrameIndex(timeline: GameTimeline, timeMs: number): number {
  const frames = timeline.frames
  if (!frames.length) return 0
  let lo = 0
  let hi = frames.length - 1
  while (lo < hi) {
    const mid = Math.ceil((lo + hi) / 2)
    if (frames[mid].t <= timeMs) lo = mid
    else hi = mid - 1
  }
  return lo
}

export async function loadFurVsG2Timeline(): Promise<GameTimeline> {
  const res = await fetch('/data/fur_vs_g2_timeline.json')
  if (!res.ok) throw new Error(`Failed to load timeline (${res.status})`)
  return res.json() as Promise<GameTimeline>
}
