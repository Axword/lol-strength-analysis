import type { MapPosition, TeamSide } from '../game/types'

export type TerrainClass =
  | 'void'
  | 'wall'
  | 'jungle'
  | 'brush'
  | 'river'
  | 'lane'
  | 'base_blue'
  | 'base_red'
  | 'pit'

export interface TerrainMeta {
  width: number
  height: number
  sourceImage: string
  maskImage: string
  vision: {
    championSightRadiusNorm: number
    wardSightRadiusNorm: number
    blueTrinketRadiusNorm: number
    brushHidesUnlessInsideOrWard: boolean
    wallBlocksVision: boolean
  }
}

export interface VisionWard {
  id: string
  team: TeamSide
  type: string
  x: number
  y: number
  visionRadius: number
}

export interface VisionUnit {
  id: string
  team: TeamSide
  position: MapPosition
  alive?: boolean
}

/**
 * Cell / unit vision relative to a viewer team:
 * - visible: viewer has vision
 * - opponent_only: viewer does NOT, but the other team does
 * - nobody: neither team has vision (true fog)
 */
export type VisionPresence = 'visible' | 'opponent_only' | 'nobody'

export interface FogGrid {
  resolution: number
  /** 0 = viewer sees, 1 = opponent-only, 2 = nobody */
  kind: Uint8Array
  /** Overlay opacity 0..1 */
  opacity: Float32Array
}

let terrainMeta: TerrainMeta | null = null
let maskPixels: Uint8Array | null = null
let maskW = 0
let maskH = 0

const CLASS_BY_INDEX: TerrainClass[] = [
  'void',
  'wall',
  'jungle',
  'brush',
  'river',
  'lane',
  'base_blue',
  'base_red',
  'pit',
]

/** Known SR brush blobs in game-normalized coords (fallback when mask lacks brush). */
export const BRUSH_ZONES: { x: number; y: number; r: number }[] = [
  { x: 0.22, y: 0.55, r: 0.035 },
  { x: 0.35, y: 0.72, r: 0.04 },
  { x: 0.55, y: 0.28, r: 0.04 },
  { x: 0.72, y: 0.48, r: 0.035 },
  { x: 0.48, y: 0.52, r: 0.03 },
  { x: 0.3, y: 0.42, r: 0.03 },
  { x: 0.68, y: 0.58, r: 0.03 },
  { x: 0.42, y: 0.35, r: 0.028 },
  { x: 0.58, y: 0.65, r: 0.028 },
]

export async function loadTerrain(): Promise<TerrainMeta> {
  if (terrainMeta && maskPixels) return terrainMeta
  const res = await fetch('/map/terrain.json')
  if (!res.ok) throw new Error(`terrain meta ${res.status}`)
  terrainMeta = (await res.json()) as TerrainMeta
  const img = new Image()
  img.crossOrigin = 'anonymous'
  img.src = terrainMeta.maskImage
  await new Promise<void>((resolve, reject) => {
    img.onload = () => resolve()
    img.onerror = () => reject(new Error('terrain mask load failed'))
  })
  const canvas = document.createElement('canvas')
  canvas.width = img.width
  canvas.height = img.height
  const ctx = canvas.getContext('2d')!
  ctx.drawImage(img, 0, 0)
  const data = ctx.getImageData(0, 0, img.width, img.height).data
  maskW = img.width
  maskH = img.height
  maskPixels = new Uint8Array(maskW * maskH)
  for (let i = 0; i < maskW * maskH; i++) {
    maskPixels[i] = data[i * 4] // R channel holds class index in our L mask
  }
  return terrainMeta
}

export function terrainAt(pos: MapPosition): TerrainClass {
  if (!maskPixels || !terrainMeta) {
    if (BRUSH_ZONES.some((z) => Math.hypot(pos.x - z.x, pos.y - z.y) < z.r)) {
      return 'brush'
    }
    return 'jungle'
  }
  // image y=0 at top (red); game y=0 at bottom (blue)
  const ix = Math.min(maskW - 1, Math.max(0, Math.floor(pos.x * maskW)))
  const iy = Math.min(maskH - 1, Math.max(0, Math.floor((1 - pos.y) * maskH)))
  const idx = maskPixels[iy * maskW + ix] ?? 2
  return CLASS_BY_INDEX[idx] ?? 'jungle'
}

export function inBrush(pos: MapPosition): boolean {
  if (terrainAt(pos) === 'brush') return true
  return BRUSH_ZONES.some((z) => Math.hypot(pos.x - z.x, pos.y - z.y) < z.r)
}

function dist(a: MapPosition, b: MapPosition) {
  return Math.hypot(a.x - b.x, a.y - b.y)
}

export function otherTeam(team: TeamSide): TeamSide {
  return team === 'blue' ? 'red' : 'blue'
}

/**
 * Whether `viewerTeam` has vision coverage on a map point
 * (ally champs + wards). Brush cells need a ward or an ally also in brush.
 */
export function teamHasVisionAt(
  target: MapPosition,
  viewerTeam: TeamSide,
  units: VisionUnit[],
  wards: VisionWard[],
  meta?: TerrainMeta | null,
): boolean {
  const champR = meta?.vision.championSightRadiusNorm ?? 0.09
  const living = units.filter((u) => u.team === viewerTeam && u.alive !== false)
  const targetInBrush = inBrush(target)

  for (const a of living) {
    if (dist(a.position, target) <= champR) {
      if (!targetInBrush) return true
      if (inBrush(a.position) && dist(a.position, target) < 0.05) return true
    }
  }

  for (const w of wards) {
    if (w.team !== viewerTeam) continue
    const r = w.visionRadius || meta?.vision.wardSightRadiusNorm || 0.055
    if (dist({ x: w.x, y: w.y }, target) <= r) return true
  }

  return false
}

/**
 * Soft visibility ∈[0,1]; hard disk is lim κ→∞ (Koopman-style lateral range).
 * Brush interiors stay dark unless an ally is also in brush nearby.
 */
export function softVisionAt(
  target: MapPosition,
  viewerTeam: TeamSide,
  units: VisionUnit[],
  wards: VisionWard[],
  meta?: TerrainMeta | null,
  kappa = 80,
): number {
  return softVisionDetailAt(target, viewerTeam, units, wards, meta, kappa).v
}

/** Soft visibility plus winning-sensor margin / radius (for σ_seen). */
export function softVisionDetailAt(
  target: MapPosition,
  viewerTeam: TeamSide,
  units: VisionUnit[],
  wards: VisionWard[],
  meta?: TerrainMeta | null,
  kappa = 80,
): { v: number; bestMarginNorm: number } {
  const champR = meta?.vision.championSightRadiusNorm ?? 0.09
  const living = units.filter((u) => u.team === viewerTeam && u.alive !== false)
  const targetInBrush = inBrush(target)
  let best = 0
  let bestMarginNorm = Number.NEGATIVE_INFINITY

  for (const a of living) {
    let r = champR
    if (targetInBrush) {
      if (!(inBrush(a.position) && dist(a.position, target) < 0.05 + 1 / kappa)) {
        continue
      }
      r = 0.05
    }
    const margin = r - dist(a.position, target)
    const v = 1 / (1 + Math.exp(-kappa * margin))
    if (v >= best) {
      best = v
      bestMarginNorm = margin / Math.max(1e-6, r)
    }
  }

  for (const w of wards) {
    if (w.team !== viewerTeam) continue
    const r = w.visionRadius || meta?.vision.wardSightRadiusNorm || 0.055
    const margin = r - dist({ x: w.x, y: w.y }, target)
    const v = 1 / (1 + Math.exp(-kappa * margin))
    if (v >= best) {
      best = v
      bestMarginNorm = margin / Math.max(1e-6, r)
    }
  }
  return { v: best, bestMarginNorm }
}

export interface CastVisionResolved {
  vision: 'mutual' | 'ambush' | 'blind' | 'unknown'
  softVision: number
  softVisionMarginNorm?: number
  /** Target team sees caster (opponent_only on caster cell). */
  spottedByTarget: boolean
}

/**
 * Soft FoW bridge for xH: continuous softVision + opponent_only on caster.
 * Ternary labels still use hard disks so FoW overlay stays aligned.
 */
export function resolveCastVisionSoft(input: {
  casterPosition?: MapPosition
  targetPosition?: MapPosition
  casterTeam: TeamSide
  targetTeam: TeamSide
  units: VisionUnit[]
  wards?: VisionWard[]
  meta?: TerrainMeta | null
}): CastVisionResolved {
  if (!input.casterPosition || !input.targetPosition) {
    return { vision: 'unknown', softVision: 0.5, spottedByTarget: false }
  }
  const wards = input.wards ?? []
  const detail = softVisionDetailAt(
    input.targetPosition,
    input.casterTeam,
    input.units,
    wards,
    input.meta,
  )
  const softVision = detail.v
  const softVisionMarginNorm = Number.isFinite(detail.bestMarginNorm)
    ? detail.bestMarginNorm
    : undefined
  const spottedByTarget = isVisibleToTeam(
    input.casterPosition,
    input.casterTeam,
    input.targetTeam,
    input.units,
    wards,
    input.meta,
  )
  const hardCasterSees = isVisibleToTeam(
    input.targetPosition,
    input.targetTeam,
    input.casterTeam,
    input.units,
    wards,
    input.meta,
  )
  if (!hardCasterSees) {
    return { vision: 'blind', softVision, softVisionMarginNorm, spottedByTarget }
  }
  return {
    vision: spottedByTarget ? 'mutual' : 'ambush',
    softVision,
    softVisionMarginNorm,
    spottedByTarget: false,
  }
}

/**
 * Whether `viewerTeam` can see a unit at `target`.
 * Allies are always visible to their own team.
 */
export function isVisibleToTeam(
  target: MapPosition,
  targetTeam: TeamSide,
  viewerTeam: TeamSide,
  allies: VisionUnit[],
  wards: VisionWard[],
  meta?: TerrainMeta | null,
): boolean {
  if (targetTeam === viewerTeam) return true
  return teamHasVisionAt(target, viewerTeam, allies, wards, meta)
}

/** Classify a cell relative to `viewerTeam`. */
export function classifyVision(
  pos: MapPosition,
  viewerTeam: TeamSide,
  units: VisionUnit[],
  wards: VisionWard[],
  meta?: TerrainMeta | null,
): VisionPresence {
  const mine = teamHasVisionAt(pos, viewerTeam, units, wards, meta)
  if (mine) return 'visible'
  const theirs = teamHasVisionAt(pos, otherTeam(viewerTeam), units, wards, meta)
  return theirs ? 'opponent_only' : 'nobody'
}

/** Unit marker state from the viewer's FoW (enemies only — allies always render). */
export function unitVisionPresence(
  unit: VisionUnit,
  viewerTeam: TeamSide,
  units: VisionUnit[],
  wards: VisionWard[],
  meta?: TerrainMeta | null,
): VisionPresence {
  if (unit.team === viewerTeam) return 'visible'
  return classifyVision(unit.position, viewerTeam, units, wards, meta)
}

/**
 * Whether an ally at `pos` is currently spotted by the enemy team.
 * Used for "they see you" rings on friendly markers.
 */
export function isSpottedByEnemy(
  pos: MapPosition,
  allyTeam: TeamSide,
  units: VisionUnit[],
  wards: VisionWard[],
  meta?: TerrainMeta | null,
): boolean {
  return teamHasVisionAt(pos, otherTeam(allyTeam), units, wards, meta)
}

/**
 * FoW grid for overlay.
 * kind: 0 viewer-clear, 1 opponent-only (you blind, they see), 2 nobody (true fog).
 */
export function buildFogGrid(
  viewerTeam: TeamSide,
  units: VisionUnit[],
  wards: VisionWard[],
  resolution = 64,
  meta?: TerrainMeta | null,
): FogGrid {
  const kind = new Uint8Array(resolution * resolution)
  const opacity = new Float32Array(resolution * resolution)
  const champR = meta?.vision.championSightRadiusNorm ?? 0.09
  const livingViewer = units.filter(
    (u) => u.team === viewerTeam && u.alive !== false,
  )
  const livingOpp = units.filter(
    (u) => u.team === otherTeam(viewerTeam) && u.alive !== false,
  )
  const wardsViewer = wards.filter((w) => w.team === viewerTeam)
  const wardsOpp = wards.filter((w) => w.team === otherTeam(viewerTeam))

  const covers = (
    pos: MapPosition,
    living: VisionUnit[],
    teamWards: VisionWard[],
  ): boolean => {
    const brush = inBrush(pos)
    for (const a of living) {
      if (dist(a.position, pos) <= champR) {
        if (!brush) return true
        if (inBrush(a.position) && dist(a.position, pos) < 0.05) return true
      }
    }
    for (const w of teamWards) {
      if (dist({ x: w.x, y: w.y }, pos) <= (w.visionRadius || 0.055)) return true
    }
    return false
  }

  for (let j = 0; j < resolution; j++) {
    for (let i = 0; i < resolution; i++) {
      const pos = {
        x: (i + 0.5) / resolution,
        y: (j + 0.5) / resolution,
      }
      const mine = covers(pos, livingViewer, wardsViewer)
      const theirs = covers(pos, livingOpp, wardsOpp)
      const terrain = terrainAt(pos)
      const idx = j * resolution + i

      if (mine) {
        kind[idx] = 0
        opacity[idx] = terrain === 'wall' ? 0.15 : 0
      } else if (theirs) {
        // Out of your vision, but opponent has vision
        kind[idx] = 1
        let fog = 0.42
        if (terrain === 'brush') fog = 0.5
        if (terrain === 'wall') fog = 0.55
        opacity[idx] = fog
      } else {
        // Out of anyone's vision — true fog
        kind[idx] = 2
        let fog = 0.82
        if (terrain === 'wall') fog = 0.92
        if (terrain === 'brush') fog = 0.88
        opacity[idx] = fog
      }
    }
  }
  return { resolution, kind, opacity }
}

/** Shared/god FoW: only darken cells neither team sees. */
export function buildSharedFogGrid(
  units: VisionUnit[],
  wards: VisionWard[],
  resolution = 64,
  meta?: TerrainMeta | null,
): FogGrid {
  const kind = new Uint8Array(resolution * resolution)
  const opacity = new Float32Array(resolution * resolution)
  for (let j = 0; j < resolution; j++) {
    for (let i = 0; i < resolution; i++) {
      const pos = {
        x: (i + 0.5) / resolution,
        y: (j + 0.5) / resolution,
      }
      const blue = teamHasVisionAt(pos, 'blue', units, wards, meta)
      const red = teamHasVisionAt(pos, 'red', units, wards, meta)
      const idx = j * resolution + i
      const terrain = terrainAt(pos)
      if (blue || red) {
        kind[idx] = blue && red ? 0 : 1
        // Soft tint when only one side sees (contested info)
        opacity[idx] = blue && red ? 0 : 0.28
        if (terrain === 'wall' && blue && red) opacity[idx] = 0.12
      } else {
        kind[idx] = 2
        opacity[idx] = terrain === 'wall' ? 0.92 : 0.8
      }
    }
  }
  return { resolution, kind, opacity }
}
