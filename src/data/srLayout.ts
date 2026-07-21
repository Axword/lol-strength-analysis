/**
 * Static Summoner's Rift layout — structures + jungle camps.
 * Game units use Riot live-stats xz (span 14870). Norm: x/z ÷ 14870.
 *
 * Camp anchors are median epic_monster_kill positions from this match's
 * JSONL (both sides independently — 180° mirror is several hundred units off).
 */
export const MAP_SPAN = 14870

export type StructureKind = 'turret' | 'inhibitor' | 'nexus'
export type CampKind =
  | 'blue_buff'
  | 'red_buff'
  | 'wolves'
  | 'raptors'
  | 'krugs'
  | 'gromp'
  | 'scuttle'
  | 'dragon_pit'
  | 'baron_pit'

export type TeamId = 100 | 200
export type Lane = 'top' | 'mid' | 'bot' | null
export type TurretTier = 'outer' | 'inner' | 'base' | 'nexus' | null

export interface SrStructure {
  id: string
  kind: StructureKind
  team: TeamId
  lane: Lane
  tier: TurretTier
  /** Riot game x */
  gx: number
  /** Riot game z */
  gz: number
  x: number
  y: number
}

export interface SrCamp {
  id: string
  kind: CampKind
  /** Owning side for buffs/small camps; null for river/pits */
  team: TeamId | null
  label: string
  gx: number
  gz: number
  x: number
  y: number
  /** Respawn after clear (ms). */
  respawnMs: number | null
  /** First spawn game time (ms). Camp is down until this before any clear. */
  firstSpawnMs: number
}

export function riotToNorm(gx: number, gz: number): { x: number; y: number } {
  return {
    x: Math.min(1, Math.max(0, gx / MAP_SPAN)),
    y: Math.min(1, Math.max(0, gz / MAP_SPAN)),
  }
}

function mirror(gx: number, gz: number): { gx: number; gz: number } {
  return { gx: MAP_SPAN - gx, gz: MAP_SPAN - gz }
}

function struct(
  id: string,
  kind: StructureKind,
  team: TeamId,
  lane: Lane,
  tier: TurretTier,
  gx: number,
  gz: number,
): SrStructure {
  const n = riotToNorm(gx, gz)
  return { id, kind, team, lane, tier, gx, gz, x: n.x, y: n.y }
}

function camp(
  id: string,
  kind: CampKind,
  team: TeamId | null,
  label: string,
  gx: number,
  gz: number,
  respawnMs: number | null,
  firstSpawnMs: number,
): SrCamp {
  const n = riotToNorm(gx, gz)
  return { id, kind, team, label, gx, gz, x: n.x, y: n.y, respawnMs, firstSpawnMs }
}

/** Blue (100) structures from this match's building_destroyed + seed. */
const BLUE_STRUCTURE_DEFS: Array<{
  id: string
  kind: StructureKind
  lane: Lane
  tier: TurretTier
  gx: number
  gz: number
}> = [
  { id: 't_outer_top', kind: 'turret', lane: 'top', tier: 'outer', gx: 981, gz: 10441 },
  { id: 't_outer_mid', kind: 'turret', lane: 'mid', tier: 'outer', gx: 5846, gz: 6396 },
  { id: 't_outer_bot', kind: 'turret', lane: 'bot', tier: 'outer', gx: 10504, gz: 1029 },
  { id: 't_inner_top', kind: 'turret', lane: 'top', tier: 'inner', gx: 1512, gz: 6699 },
  { id: 't_inner_mid', kind: 'turret', lane: 'mid', tier: 'inner', gx: 5048, gz: 4812 },
  { id: 't_inner_bot', kind: 'turret', lane: 'bot', tier: 'inner', gx: 6919, gz: 1483 },
  { id: 't_base_top', kind: 'turret', lane: 'top', tier: 'base', gx: 1169, gz: 4287 },
  { id: 't_base_mid', kind: 'turret', lane: 'mid', tier: 'base', gx: 3651, gz: 3696 },
  { id: 't_base_bot', kind: 'turret', lane: 'bot', tier: 'base', gx: 4281, gz: 1253 },
  { id: 't_nexus_a', kind: 'turret', lane: 'mid', tier: 'nexus', gx: 1748, gz: 2270 },
  { id: 't_nexus_b', kind: 'turret', lane: 'mid', tier: 'nexus', gx: 2177, gz: 1807 },
  { id: 'i_top', kind: 'inhibitor', lane: 'top', tier: null, gx: 1170, gz: 3570 },
  { id: 'i_mid', kind: 'inhibitor', lane: 'mid', tier: null, gx: 3210, gz: 3217 },
  { id: 'i_bot', kind: 'inhibitor', lane: 'bot', tier: null, gx: 3468, gz: 1230 },
  { id: 'nexus', kind: 'nexus', lane: null, tier: null, gx: 1550, gz: 1660 },
]

function buildStructures(): SrStructure[] {
  const out: SrStructure[] = []
  for (const d of BLUE_STRUCTURE_DEFS) {
    out.push(struct(`blue_${d.id}`, d.kind, 100, d.lane, d.tier, d.gx, d.gz))
    const m = mirror(d.gx, d.gz)
    out.push(struct(`red_${d.id}`, d.kind, 200, d.lane, d.tier, m.gx, m.gz))
  }
  return out
}

/**
 * Jungle camps — spawn anchors + timers (Summoner's Rift, patch 26.1+).
 * First spawn (Riot 26.1 / wiki): wolves·blue·red·raptors 0:55; gromp·krugs 1:07;
 * scuttle 2:55; dragon/grubs 5:00; herald 14:00; baron 20:00.
 * Respawn: small 2:15, buffs 5:00, scuttle 2:30, dragon 5:00, baron 6:00.
 */
const FIRST_BUFF_WOLF_RAPTOR_MS = 55_000
const FIRST_GROMP_KRUG_MS = 67_000
const FIRST_SCUTTLE_MS = 175_000
const FIRST_DRAGON_MS = 300_000
const FIRST_GRUBS_MS = 300_000
const RESPAWN_SMALL_MS = 135_000
const RESPAWN_BUFF_MS = 300_000
const RESPAWN_SCUTTLE_MS = 150_000
const RESPAWN_DRAGON_MS = 300_000
const RESPAWN_BARON_MS = 360_000

const CAMP_DEFS: Array<{
  id: string
  kind: CampKind
  team: TeamId | null
  label: string
  gx: number
  gz: number
  respawnMs: number | null
  firstSpawnMs: number
}> = [
  // Blue-side jungle
  { id: 'blue_blue_buff', kind: 'blue_buff', team: 100, label: 'Blue buff', gx: 3720, gz: 7880, respawnMs: RESPAWN_BUFF_MS, firstSpawnMs: FIRST_BUFF_WOLF_RAPTOR_MS },
  { id: 'blue_gromp', kind: 'gromp', team: 100, label: 'Gromp', gx: 2300, gz: 8380, respawnMs: RESPAWN_SMALL_MS, firstSpawnMs: FIRST_GROMP_KRUG_MS },
  { id: 'blue_wolves', kind: 'wolves', team: 100, label: 'Wolves', gx: 3780, gz: 6500, respawnMs: RESPAWN_SMALL_MS, firstSpawnMs: FIRST_BUFF_WOLF_RAPTOR_MS },
  { id: 'blue_raptors', kind: 'raptors', team: 100, label: 'Raptors', gx: 7060, gz: 5320, respawnMs: RESPAWN_SMALL_MS, firstSpawnMs: FIRST_BUFF_WOLF_RAPTOR_MS },
  { id: 'blue_red_buff', kind: 'red_buff', team: 100, label: 'Red buff', gx: 7730, gz: 4050, respawnMs: RESPAWN_BUFF_MS, firstSpawnMs: FIRST_BUFF_WOLF_RAPTOR_MS },
  { id: 'blue_krugs', kind: 'krugs', team: 100, label: 'Krugs', gx: 8430, gz: 2540, respawnMs: RESPAWN_SMALL_MS, firstSpawnMs: FIRST_GROMP_KRUG_MS },
  // Red-side jungle (mirror)
  { id: 'red_blue_buff', kind: 'blue_buff', team: 200, label: 'Blue buff', gx: 11150, gz: 6990, respawnMs: RESPAWN_BUFF_MS, firstSpawnMs: FIRST_BUFF_WOLF_RAPTOR_MS },
  { id: 'red_gromp', kind: 'gromp', team: 200, label: 'Gromp', gx: 12570, gz: 6490, respawnMs: RESPAWN_SMALL_MS, firstSpawnMs: FIRST_GROMP_KRUG_MS },
  { id: 'red_wolves', kind: 'wolves', team: 200, label: 'Wolves', gx: 11090, gz: 8370, respawnMs: RESPAWN_SMALL_MS, firstSpawnMs: FIRST_BUFF_WOLF_RAPTOR_MS },
  { id: 'red_raptors', kind: 'raptors', team: 200, label: 'Raptors', gx: 7810, gz: 9550, respawnMs: RESPAWN_SMALL_MS, firstSpawnMs: FIRST_BUFF_WOLF_RAPTOR_MS },
  { id: 'red_red_buff', kind: 'red_buff', team: 200, label: 'Red buff', gx: 7140, gz: 10820, respawnMs: RESPAWN_BUFF_MS, firstSpawnMs: FIRST_BUFF_WOLF_RAPTOR_MS },
  { id: 'red_krugs', kind: 'krugs', team: 200, label: 'Krugs', gx: 6440, gz: 12330, respawnMs: RESPAWN_SMALL_MS, firstSpawnMs: FIRST_GROMP_KRUG_MS },
  // River / pits
  { id: 'scuttle_top', kind: 'scuttle', team: null, label: 'Scuttle (baron)', gx: 5056, gz: 8778, respawnMs: RESPAWN_SCUTTLE_MS, firstSpawnMs: FIRST_SCUTTLE_MS },
  { id: 'scuttle_bot', kind: 'scuttle', team: null, label: 'Scuttle (dragon)', gx: 9600, gz: 5800, respawnMs: RESPAWN_SCUTTLE_MS, firstSpawnMs: FIRST_SCUTTLE_MS },
  { id: 'dragon_pit', kind: 'dragon_pit', team: null, label: 'Dragon', gx: 10021, gz: 4529, respawnMs: RESPAWN_DRAGON_MS, firstSpawnMs: FIRST_DRAGON_MS },
  { id: 'baron_pit', kind: 'baron_pit', team: null, label: 'Baron / Grubs / Herald', gx: 4803, gz: 10235, respawnMs: RESPAWN_BARON_MS, firstSpawnMs: FIRST_GRUBS_MS },
]

function buildCamps(): SrCamp[] {
  return CAMP_DEFS.map((c) =>
    camp(c.id, c.kind, c.team, c.label, c.gx, c.gz, c.respawnMs, c.firstSpawnMs),
  )
}

export const SR_STRUCTURES: SrStructure[] = buildStructures()
export const SR_CAMPS: SrCamp[] = buildCamps()

export function structureById(id: string): SrStructure | undefined {
  return SR_STRUCTURES.find((s) => s.id === id)
}

export function campById(id: string): SrCamp | undefined {
  return SR_CAMPS.find((c) => c.id === id)
}

/** Match a destroy event to the nearest same-team structure. */
export function nearestStructure(
  team: TeamId,
  gx: number,
  gz: number,
  kind?: StructureKind | null,
  maxDist = 450,
): SrStructure | null {
  let best: SrStructure | null = null
  let bestD = maxDist
  for (const s of SR_STRUCTURES) {
    if (s.team !== team) continue
    if (kind && s.kind !== kind) continue
    const d = Math.hypot(s.gx - gx, s.gz - gz)
    if (d < bestD) {
      bestD = d
      best = s
    }
  }
  return best
}

export function nearestCamp(
  gx: number,
  gz: number,
  kind?: CampKind | null,
  maxDist = 1200,
): SrCamp | null {
  let best: SrCamp | null = null
  let bestD = maxDist
  for (const c of SR_CAMPS) {
    if (kind && c.kind !== kind) continue
    const d = Math.hypot(c.gx - gx, c.gz - gz)
    if (d < bestD) {
      bestD = d
      best = c
    }
  }
  return best
}
