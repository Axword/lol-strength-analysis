/**
 * Map overlay icons — Riot client HUD squares (via Community Dragon) for
 * structures; League wiki monster squares for jungle camps / pits.
 * Bundled under public/map/icons/ so the app does not hotlink.
 */
import type { MapCampKind, MapStructureKind, TeamSide } from '../game/types'

const BASE = '/map/icons'

export function structureIconUrl(kind: MapStructureKind, team: TeamSide): string {
  const side = team === 'blue' ? 'blue' : 'red'
  switch (kind) {
    case 'turret':
      return `${BASE}/turret_${side}.png`
    case 'inhibitor':
      return `${BASE}/inhibitor_${side}.png`
    case 'nexus':
      return `${BASE}/nexus_${side}.png`
  }
}

export function campIconUrl(kind: MapCampKind): string {
  switch (kind) {
    case 'blue_buff':
      return `${BASE}/blue_buff.png`
    case 'red_buff':
      return `${BASE}/red_buff.png`
    case 'wolves':
      return `${BASE}/wolves.png`
    case 'raptors':
      return `${BASE}/raptors.png`
    case 'krugs':
      return `${BASE}/krugs.png`
    case 'gromp':
      return `${BASE}/gromp.png`
    case 'scuttle':
      return `${BASE}/scuttle.png`
    case 'dragon_pit':
      return `${BASE}/dragon.png`
    case 'baron_pit':
      return `${BASE}/baron.png`
  }
}

/** SVG pixel size on the 640×640 map (champs are ~28–32). */
export function structureMarkerSize(kind: MapStructureKind): number {
  switch (kind) {
    case 'nexus':
      return 28
    case 'inhibitor':
      return 24
    case 'turret':
      return 20
  }
}

/** Camp markers — blue/gromp pits are ~79px apart so 28px icons stay clear. */
export function campMarkerSize(kind: MapCampKind): number {
  switch (kind) {
    case 'dragon_pit':
    case 'baron_pit':
      return 36
    case 'blue_buff':
    case 'red_buff':
      return 30
    case 'scuttle':
      return 26
    default:
      return 28
  }
}
