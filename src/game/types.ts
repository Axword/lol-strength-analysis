import type { FighterLoadout } from '../engine/types'
import type { ScoreboardState } from '../engine/objectives'
import type { VisionWard } from '../engine/vision'

/** Normalized map coords: x 0→1 blue→red botlane axis, y 0→1 bottom→top (blue base ≈ low y). */
export interface MapPosition {
  x: number
  y: number
}

export type TeamSide = 'blue' | 'red'

export type LaneRole = 'top' | 'jungle' | 'mid' | 'bot' | 'support'

export interface GameUnit {
  id: string
  team: TeamSide
  role: LaneRole
  summonerName: string
  loadout: FighterLoadout
  position: MapPosition
  /** Provenance of the replay position; placeholders must not enter combat/xH. */
  positionSource?: string
  /** Current HP fraction 0–1 if known from replay */
  hpPct?: number
  alive?: boolean
  /** When false, HP is unknown — do not treat as dead/full. */
  hpKnown?: boolean
  /** When false, AD/AP/armor/MR overrides are unavailable. */
  combatStatsKnown?: boolean
  /** When false, ability ranks are unavailable — calculator must stay blocked. */
  abilityRanksKnown?: boolean
  /** Cumulative career + live combat stats at this frame */
  career?: import('../engine/careerStats').ChampCareerStats
}

export type MapStructureKind = 'turret' | 'inhibitor' | 'nexus'
export type MapCampKind =
  | 'blue_buff'
  | 'red_buff'
  | 'wolves'
  | 'raptors'
  | 'krugs'
  | 'gromp'
  | 'scuttle'
  | 'dragon_pit'
  | 'baron_pit'

export interface MapStructureState {
  id: string
  kind: MapStructureKind
  team: TeamSide
  lane?: string | null
  tier?: string | null
  x: number
  y: number
  alive: boolean
}

export interface MapCampState {
  id: string
  kind: MapCampKind
  team: TeamSide | null
  label: string
  x: number
  y: number
  alive: boolean
  /** Game time (ms) when this camp next becomes available. Present when down. */
  respawnsAtMs?: number
  /** Game time (ms) of last clear (if any). */
  clearedAtMs?: number
}

export interface MapObjectsState {
  structures: MapStructureState[]
  camps: MapCampState[]
}

export interface GameSnapshot {
  id: string
  name: string
  patch: string
  /** Game time in seconds */
  gameTimeSec: number
  map: 'summoners_rift'
  units: GameUnit[]
  notes?: string
  score?: ScoreboardState
  wards?: VisionWard[]
  mapObjects?: MapObjectsState
}

export type SnapshotImportResult =
  | {
      ok: true
      snapshot: GameSnapshot
    }
  | {
      ok: false
      error: string
    }
