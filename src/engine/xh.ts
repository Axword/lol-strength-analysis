/**
 * Physically factored skillshot hit probability (xH).
 *
 * Replaces multiplicative mobility×zone×vision priors with:
 *   xH = P(|M − μ| < R_hit),  M ~ N(μ, σ²)
 *   σ² = σ_aim² + σ_juke² + σ_belief²
 *
 * Grounded in adversarial arXiv synthesis (collision/lead, Schmidt–Fitts aim
 * noise, LKP belief under FoW, dash-budget dodge, shared-latent xHm).
 * Still a prior until cast→hit logs recalibrate σ scales — not a fitted MLE.
 */

import type { MapPosition } from '../game/types'
import type { AbilityDefinition, DamagePacket, XhMode } from './types'
import {
  isVisibleToTeam,
  type TerrainMeta,
  type VisionUnit,
  type VisionWard,
} from './vision'

export type { XhMode }

export type MobilityClass =
  | 'immobile'
  | 'boots'
  | 'one_dash'
  | 'two_dash'
  | 'high'

export type MapZone =
  | 'lane'
  | 'river'
  | 'jungle'
  | 'brush'
  | 'pit'
  | 'base'
  | 'unknown'

export type VisionRelation = 'mutual' | 'ambush' | 'blind' | 'unknown'

/** Kit mobility tags — used only to infer default dash budget, not as P(hit). */
export const CHAMPION_MOBILITY: Record<string, MobilityClass> = {
  Syndra: 'immobile',
  Jhin: 'immobile',
  Annie: 'immobile',
  Lux: 'immobile',
  Darius: 'boots',
  Garen: 'boots',
  Malphite: 'boots',
  Galio: 'one_dash',
  Leona: 'one_dash',
  Gnar: 'one_dash',
  Ambessa: 'one_dash',
  Camille: 'two_dash',
  Gragas: 'one_dash',
  Jax: 'one_dash',
  LeeSin: 'two_dash',
  Akali: 'high',
  Ahri: 'two_dash',
  Naafiri: 'two_dash',
}

export function mobilityOf(championId: string): MobilityClass {
  return CHAMPION_MOBILITY[championId] ?? 'one_dash'
}

export function zoneAt(pos: MapPosition | undefined): MapZone {
  if (!pos) return 'unknown'
  const { x, y } = pos
  if (x < 0.18 && y < 0.18) return 'base'
  if (x > 0.82 && y > 0.82) return 'base'
  const distDrake = Math.hypot(x - 0.62, y - 0.42)
  const distBaron = Math.hypot(x - 0.38, y - 0.58)
  if (distDrake < 0.07 || distBaron < 0.07) return 'pit'
  const river = Math.abs(x + y - 1)
  if (river < 0.1 && x > 0.22 && x < 0.78) return 'river'
  const brushes = [
    [0.22, 0.55],
    [0.35, 0.72],
    [0.55, 0.28],
    [0.72, 0.48],
    [0.48, 0.52],
  ]
  for (const [bx, by] of brushes) {
    if (Math.hypot(x - bx, y - by) < 0.055) return 'brush'
  }
  const onLane =
    Math.abs(x - y) < 0.12 || (x < 0.28 && y > 0.55) || (x > 0.55 && y < 0.28)
  if (!onLane && x > 0.15 && x < 0.85 && y > 0.15 && y < 0.85) return 'jungle'
  return 'lane'
}

const MAP_SPAN = 14870
/** Typical champion gameplay radius (game units). */
const CHAMP_RADIUS = 65
/** Default missile speeds (uu/s) by range band. */
const DEFAULT_MS_SHORT = 1600
const DEFAULT_MS_LONG = 2000

export function distanceGameUnits(a: MapPosition, b: MapPosition): number {
  const dx = (a.x - b.x) * MAP_SPAN
  const dy = (a.y - b.y) * MAP_SPAN
  return Math.hypot(dx, dy)
}

/** @deprecated Kept for overlay tooltips; no longer the primary model. */
export const VISION_XH_MULT = {
  mutual: 1,
  ambush: 1.14,
  blind: 0.55,
  unknown: 1,
} as const

export interface XhEstimateInput {
  targetChampionId: string
  casterPosition?: MapPosition
  targetPosition?: MapPosition
  abilityRange: number
  skillshotLengthPenalty?: boolean
  vision?: VisionRelation
  /** Missile speed (game units / sec). */
  missileSpeed?: number
  /** Missile width (game units). */
  missileWidth?: number
  /** Target MS; default 335. */
  targetMovespeed?: number
  /** Override dash readiness; default inferred from mobility class. */
  dashReady?: boolean
  flashReady?: boolean
  crowdControlled?: boolean
  /**
   * Seconds since last seen (blind / LKP). Ignored when vision is mutual/ambush.
   * Default 2s when blind and unspecified.
   */
  lastKnownAgeSec?: number
  /** Partial lead skill in [0,1]; 1 = perfect collision-triangle lead. */
  leadSkill?: number
  /**
   * Target velocity along LOS (uu/s); + = fleeing from caster.
   * Default 0 (unknown / isotropic mean radial).
   */
  targetRadialVel?: number
  /**
   * Target velocity perpendicular to LOS (uu/s).
   * Default: MS * (2/π) isotropic E[|sin θ|].
   */
  targetPerpVel?: number
  /** Pre-release aim / lineup budget (s). Default from vision; NOT missile TOF. */
  aimTimeSec?: number
  /** Release-time jitter SD (s) for interception timing noise. Default 0.045. */
  releaseJitterSec?: number
  /** LKP / filter mean; when set under FoW, geometry aims here not at oracle pose. */
  beliefMeanPosition?: MapPosition
  /** Continuous visibility ∈[0,1]; if set, mixes seen/lost belief kernels. */
  softVision?: number
  /** Best sensor margin / radius (Koopman); deepens σ_seen when set. */
  softVisionMarginNorm?: number
  /** Opponent sees caster while caster is dark (opponent_only FoW). */
  spottedByTarget?: boolean
  /** Override Fitts target width (uu). Default = 2·R_hit. */
  fittsWidthUu?: number
  /**
   * Flash CD remaining (s). If set: >0 ⇒ Flash down; 0 ⇒ Flash up.
   * Overrides flashReady when provided.
   */
  flashCdRemainingSec?: number
  /** Prior mass on Flash-up when flashReady unset. Default 0.35. */
  flashUpPrior?: number
  /** Cast / delayed-missile release delay (s). Default 0.28. */
  releaseDelaySec?: number
  /** Dash charges remaining (0..N). Undefined → boolean dashReady path. */
  dashChargesRemaining?: number
  /** Ghost (or similar) active → higher strafe coeff when MS not already buffed. */
  ghostActive?: boolean
  /** Cleanse / QSS ready while CC'd → partial discrete juke restore. */
  ccBreakReady?: boolean
  /** Prior mass on Flash when known down (NE mix). Default 0.20. */
  flashUpPriorDown?: number
  /** Residual |a_perp| bound (uu/s²) for accel-free ZEM extra. Default 0. */
  residualAccelUuPerSec2?: number
  /** Missile max travel (uu); tip clamp. Default = abilityRange. */
  missileMaxTravelUu?: number
  /** Soft/live component mean under penumbra (multi-mean mix). */
  beliefMeanSeen?: MapPosition
  /** Optional multi-modal FoW hypotheses (Σ w Φ_corr). */
  beliefHypotheses?: {
    weight: number
    mean: MapPosition
    ageSec?: number
    sigmaBelief?: number
    zone?: MapZone
  }[]
}

export interface XhEstimate {
  xH: number
  inRange: boolean
  distance: number | null
  targetMobility: MobilityClass
  targetZone: MapZone
  casterZone: MapZone
  vision: VisionRelation
  factors: string[]
  /** Strategic bands (dodge depleted / typical / Flash envelope + optional NE mix). */
  bands?: { worst: number; typical: number; best: number; mix?: number }
  /** Debug σ components (game units). */
  sigma?: { aim: number; juke: number; belief: number; total: number }
}

function defaultMissileSpeed(range: number): number {
  return range >= 900 ? DEFAULT_MS_LONG : DEFAULT_MS_SHORT
}

function defaultMissileWidth(range: number): number {
  // Longer skillshots tend to be thinner corridors in LoL kits.
  if (range >= 1200) return 70
  if (range >= 900) return 90
  return 120
}

function dashBudgetFromMobility(m: MobilityClass): number {
  switch (m) {
    case 'immobile':
      return 0
    case 'boots':
      return 0
    case 'one_dash':
      return 425
    case 'two_dash':
      return 700
    case 'high':
      return 900
  }
}

/** Standard normal CDF via erf. */
function normCdf(z: number): number {
  return 0.5 * (1 + erf(z / Math.SQRT2))
}

function erf(x: number): number {
  // Abramowitz–Stegun 7.1.26
  const sign = x < 0 ? -1 : 1
  const ax = Math.abs(x)
  const t = 1 / (1 + 0.3275911 * ax)
  const y =
    1 -
    (((((1.061405429 * t - 1.453152027) * t + 1.421413741) * t - 0.284496736) *
      t +
      0.254829592) *
      t *
      Math.exp(-ax * ax))
  return sign * y
}

/**
 * P(|X| < R) for X ~ N(μ, σ²) — 1D corridor hit (cookie-cutter + Gaussian miss).
 * arXiv-style soft lethality / firing theory on lateral miss.
 */
export function corridorHitProb(R: number, mu: number, sigma: number): number {
  if (!(R > 0)) return 0
  if (!(sigma > 1e-6)) return Math.abs(mu) <= R ? 1 : 0
  return normCdf((R - mu) / sigma) - normCdf((-R - mu) / sigma)
}

/**
 * Collision-triangle intercept time for constant-speed ballistic missile vs
 * constant-velocity target in the LOS frame: r=(R,0), v=(vRadial, vPerp).
 * Solve |r + v t|² = (V_m t)² → A t² + B t + C = 0.
 * Positive vRadial = target fleeing along LOS.
 * arXiv:2403.14997 (t_go / collision course); arXiv:2312.09562 (collision triangle).
 */
export function interceptTimeGo(
  rangeUu: number,
  missileSpeed: number,
  vRadial = 0,
  vPerp = 0,
): number {
  const Vm = Math.max(200, missileSpeed)
  const R = Math.max(1, rangeUu)
  const A = vRadial * vRadial + vPerp * vPerp - Vm * Vm
  const B = 2 * R * vRadial
  const C = R * R
  if (Math.abs(A) < 1e-6) {
    if (B >= -1e-9) return R / Vm
    return Math.max(0.05, -C / B)
  }
  const disc = B * B - 4 * A * C
  if (disc < 0) {
    return R / Vm
  }
  const s = Math.sqrt(disc)
  const t1 = (-B - s) / (2 * A)
  const t2 = (-B + s) / (2 * A)
  const hits = [t1, t2].filter((t) => t > 0.05)
  return hits.length ? Math.min(...hits) : R / Vm
}

/**
 * Lateral miss (ZEM) for ballistic aim with partial lead.
 * leadSkill=1 → perfect collision-triangle lead → μ=0 (non-maneuvering).
 * leadSkill=0 → aim at current position → μ ≈ |v_perp| t_go.
 * arXiv:2511.21633 (ZEM); arXiv:2604.17811 (miss → hit probability).
 */
export function lateralMissFromLead(
  tGo: number,
  vPerp: number,
  leadSkill: number,
): number {
  const lead = Math.min(1, Math.max(0, leadSkill))
  return Math.abs(vPerp) * Math.max(0, tGo) * (1 - lead)
}

/** Isotropic heading prior: E[|sin θ|] = 2/π. */
export const ISOTROPIC_PERP_FRAC = 2 / Math.PI

/**
 * Required open-loop lead angle (rad) off current LOS for collision-triangle intercept.
 * arXiv:1906.02113; arXiv:2312.09562.
 */
export function requiredLeadAngle(
  tGo: number,
  rangeUu: number,
  vRadial = 0,
  vPerp = 0,
): number {
  const t = Math.max(0, tGo)
  return Math.atan2(vPerp * t, rangeUu + vRadial * t)
}

/**
 * Lateral miss from heading error δ = λ* − λ_aim.
 * Identity: |sin λ*| V_m t_go = |v_perp| t_go on the collision triangle.
 */
export function lateralMissFromHeadingError(
  tGo: number,
  missileSpeed: number,
  leadRequiredRad: number,
  leadAchievedRad: number,
): number {
  const Vm = Math.max(200, missileSpeed)
  const delta = leadRequiredRad - leadAchievedRad
  return Math.abs(Math.sin(delta)) * Vm * Math.max(0, tGo)
}

/** Ballistic reach: V_m t_go ≤ R_max + champ radius (replaces abilityRange×1.05). */
export function interceptInMissileRange(
  tGo: number,
  missileSpeed: number,
  abilityRange: number,
  champRadius = CHAMP_RADIUS,
): boolean {
  const reach = Math.max(200, missileSpeed) * Math.max(0, tGo)
  return reach <= abilityRange + champRadius
}

/**
 * First-contact time on the collision triangle with lethal radius R_hit.
 * Center intercept t0 from interceptTimeGo; open-loop only — no PN.
 */
export function firstContactTimeGo(
  tGoCenterSec: number,
  rangeUu: number,
  hitRadiusUu: number,
): number {
  const t0 = Math.max(0, tGoCenterSec)
  const R = Math.max(1, rangeUu)
  const Rh = Math.max(0, hitRadiusUu)
  if (Rh < 1e-9) return t0
  if (R <= Rh) return Math.min(t0, 0.05)
  return Math.max(0.05, t0 * (1 - Rh / R))
}

/**
 * Free-propagate target in cast-time LOS frame, re-basis velocity at release.
 * Multi-segment TOF: delay then ballistic. No mid-course PN.
 */
export function propagateLosFrame(
  rangeUu: number,
  vRadial: number,
  vPerp: number,
  delaySec: number,
): { rangeUu: number; vRadial: number; vPerp: number } {
  const td = Math.max(0, delaySec)
  const R = Math.max(1, rangeUu)
  const px = R + vRadial * td
  const py = vPerp * td
  const Rp = Math.hypot(px, py)
  if (!(Rp > 1e-6)) {
    // Coincident after delay: LOS undefined — preserve speed, radial 0.
    const spd = Math.hypot(vRadial, vPerp)
    return { rangeUu: 1, vRadial: 0, vPerp: spd }
  }
  const ux = px / Rp
  const uy = py / Rp
  const vRadp = vRadial * ux + vPerp * uy
  const vPerpp = -vRadial * uy + vPerp * ux
  return { rangeUu: Rp, vRadial: vRadp, vPerp: vPerpp }
}

/**
 * Closest approach of constant-v target vs ballistic aim ray (open-loop).
 * Prefer for μ when aim ≠ λ*; keep lateralMissFromHeadingError for identity tests.
 */
export function ballisticRayMiss(
  rangeUu: number,
  vRadial: number,
  vPerp: number,
  missileSpeed: number,
  aimAngleRad: number,
  tMax: number,
): number {
  const Vm = Math.max(200, missileSpeed)
  const R = Math.max(1, rangeUu)
  const c = Math.cos(aimAngleRad)
  const s = Math.sin(aimAngleRad)
  const wx = vRadial - Vm * c
  const wy = vPerp - Vm * s
  const w2 = wx * wx + wy * wy
  let tStar = 0
  if (w2 > 1e-12) {
    tStar = -(R * wx) / w2
  }
  const t = Math.min(Math.max(0, tMax), Math.max(0, tStar))
  const mx = Vm * t * c
  const my = Vm * t * s
  const px = R + vRadial * t
  const py = vPerp * t
  return Math.hypot(px - mx, py - my)
}

/**
 * Accel-bounded open-loop ZEM extra (no PN): |ΔZEM| ≤ ½ A t² under |a_perp|≤A.
 * Default A=0. Distinct from dash/Flash σ_juke.
 */
export function boundedAccelZemExtra(
  tGoSec: number,
  aMaxPerpUuPerSec2 = 0,
): number {
  const t = Math.max(0, tGoSec)
  return 0.5 * Math.max(0, aMaxPerpUuPerSec2) * t * t
}

/**
 * Finite-segment ballistic CPA: clamp engagement to missile travel length L.
 */
export function ballisticSegmentMiss(
  rangeUu: number,
  vRadial: number,
  vPerp: number,
  missileSpeed: number,
  aimAngleRad: number,
  tMax: number,
  maxTravelUu: number,
): number {
  return ballisticSegmentCpa(
    rangeUu,
    vRadial,
    vPerp,
    missileSpeed,
    aimAngleRad,
    tMax,
    maxTravelUu,
  ).missUu
}

/**
 * Finite-segment ballistic CPA + engagement epoch.
 * μ uses missUu; accel-ZEM integrates to tCpaSec (not tip pad).
 */
export function ballisticSegmentCpa(
  rangeUu: number,
  vRadial: number,
  vPerp: number,
  missileSpeed: number,
  aimAngleRad: number,
  tMax: number,
  maxTravelUu: number,
): { missUu: number; tCpaSec: number } {
  const Vm = Math.max(200, missileSpeed)
  const L = Math.max(1, maxTravelUu)
  const tSeg = Math.min(Math.max(0, tMax), L / Vm)
  const R = Math.max(1, rangeUu)
  const c = Math.cos(aimAngleRad)
  const s = Math.sin(aimAngleRad)
  const wx = vRadial - Vm * c
  const wy = vPerp - Vm * s
  const w2 = wx * wx + wy * wy
  let tStar = 0
  if (w2 > 1e-12) {
    tStar = -(R * wx) / w2
  }
  const t = Math.min(Math.max(0, tSeg), Math.max(0, tStar))
  const mx = Vm * t * c
  const my = Vm * t * s
  const px = R + vRadial * t
  const py = vPerp * t
  return { missUu: Math.hypot(px - mx, py - my), tCpaSec: t }
}

/**
 * Earliest open-loop time in [0, tCpa] at which center separation ≤ R_hit
 * along relative motion p(t)=(R+w_x t, w_y t) vs ballistic aim ray.
 * If the path never enters the lethal disk, returns tCpa (center CPA).
 * Accel-ZEM uses this contact epoch; corridor μ still uses center missUu.
 */
export function ballisticFirstContactSec(
  rangeUu: number,
  vRadial: number,
  vPerp: number,
  missileSpeed: number,
  aimAngleRad: number,
  tCpaSec: number,
  hitRadiusUu: number,
): number {
  const tCpa = Math.max(0, tCpaSec)
  const Rh = Math.max(0, hitRadiusUu)
  if (Rh < 1e-9) return tCpa
  const Vm = Math.max(200, missileSpeed)
  const R = Math.max(1, rangeUu)
  if (R <= Rh) return Math.min(tCpa, 0.05)
  const c = Math.cos(aimAngleRad)
  const s = Math.sin(aimAngleRad)
  const wx = vRadial - Vm * c
  const wy = vPerp - Vm * s
  const A = wx * wx + wy * wy
  const B = 2 * R * wx
  const C = R * R - Rh * Rh
  if (A < 1e-12) {
    if (Math.abs(wx) < 1e-12) return tCpa
    const tA = (-R + Rh) / wx
    const tB = (-R - Rh) / wx
    const hits = [tA, tB].filter((t) => t >= -1e-9 && t <= tCpa + 1e-9)
    if (!hits.length) return tCpa
    return Math.max(0, Math.min(...hits))
  }
  const disc = B * B - 4 * A * C
  if (disc < 0) return tCpa
  const sdisc = Math.sqrt(disc)
  const t1 = (-B - sdisc) / (2 * A)
  const t2 = (-B + sdisc) / (2 * A)
  const hits = [t1, t2].filter((t) => t >= -1e-9 && t <= tCpa + 1e-9)
  if (!hits.length) return tCpa
  return Math.max(0, Math.min(...hits))
}

/**
 * Accel-envelope clock: fire-control delay + flight to CPA.
 */
export function accelZemClockSec(
  releaseDelaySec: number,
  tCpaFlightSec: number,
): number {
  return Math.max(0, releaseDelaySec) + Math.max(0, tCpaFlightSec)
}

/**
 * Finite engagement horizon: missile dies at tip travel L/V_m.
 * Lead / CPA / accel-ZEM use t_eng = min(t_go, L/V_m), not unreachable
 * intercept time. Open-loop only — no PN.
 */
export function engagementHorizonSec(
  tGoInterceptSec: number,
  missileSpeed: number,
  maxTravelUu: number,
): number {
  const Vm = Math.max(200, missileSpeed)
  const tL = Math.max(1, maxTravelUu) / Vm
  return Math.min(Math.max(0, tGoInterceptSec), tL)
}

/** Zone occupancy prior SD (uu) — σ_belief asymptote under FoW. */
export function occupancySigma(zone: MapZone): number {
  switch (zone) {
    case 'brush':
      return 280
    case 'pit':
      return 300
    case 'river':
      return 380
    case 'jungle':
      return 420
    case 'base':
      return 240
    case 'lane':
      return 520
    default:
      return 480
  }
}

/** Capsule (stadium) hit radius: segment half-width ⊕ champ disk. */
export function capsuleHitRadius(
  missileWidth: number,
  champRadius = CHAMP_RADIUS,
): number {
  return Math.max(1, missileWidth) / 2 + champRadius
}

/**
 * Capsule centerline travel budget: segment length L plus Minkowski tip R_hit.
 */
export function capsuleTravelBudgetUu(
  maxTravelUu: number,
  missileWidth: number,
  champRadius = CHAMP_RADIUS,
): number {
  return Math.max(1, maxTravelUu) + capsuleHitRadius(missileWidth, champRadius)
}

/** Cast-time legality: current center within cast range + hitbox. */
export function inCastRange(
  distanceUu: number,
  abilityRange: number,
  champRadius = CHAMP_RADIUS,
): boolean {
  return distanceUu <= abilityRange + champRadius
}

/** Shannon–Fitts index; W is full corridor width (uu). */
export function fittsIndex(D: number, W: number): number {
  const w = Math.max(1, W)
  return Math.log2(1 + Math.max(0, D) / w)
}

/** Fitts-required movement time (s) for game-scale lineup snaps. */
export function fittsRequiredMt(ID: number): number {
  return 0.06 + 0.07 * Math.max(0, ID)
}

/**
 * Pass-3 aim SD: Fitts + intermittent corr (τ_vm) + FoW on σ_corr.
 * T_avail = lineup only (not TOF). W = full corridor width.
 */
export function schmidtAimSigma(
  D: number,
  T_avail: number,
  W = 200,
  opts?: {
    kappaLat?: number
    kappaTheta?: number
    kappaCorr?: number
    beta?: number
    softVision?: number
    urgencyOut?: { value: number }
  },
): number {
  const T = Math.max(0.12, T_avail)
  const SIGMA0 = 26
  const KAPPA_LAT = opts?.kappaLat ?? 0.1
  const KAPPA_THETA = opts?.kappaTheta ?? 0.026
  const KAPPA_C = opts?.kappaCorr ?? 0.045
  const BETA = opts?.beta ?? 0.85
  const U_MAX = 2.4
  const T_OPEN = 0.16
  const TAU_VM = 0.1
  const DT_INT = 0.1
  const RHO = 0.55
  const softV = opts?.softVision ?? 1

  const ID = fittsIndex(D, W)
  const Tstar = fittsRequiredMt(ID)
  const urgency = Math.min(U_MAX, Math.pow(Math.max(1, Tstar / T), BETA))
  if (opts?.urgencyOut) opts.urgencyOut.value = urgency

  const sigmaLat = Math.hypot(
    KAPPA_LAT * (D / T),
    90 * Math.max(0, urgency - 1),
  )
  const SIGMA_ANG0 = 8
  const sigmaAng = Math.hypot(KAPPA_THETA * D, SIGMA_ANG0)

  const T_fb = Math.max(0, T - T_OPEN - TAU_VM)
  const N = Math.floor(T_fb / DT_INT + 1e-9)
  let sigmaCorr = 0
  if (N >= 1) {
    const u0 = KAPPA_LAT * (D / T)
    const dt = Math.max(DT_INT, T_fb / N)
    let acc = 0
    for (let k = 0; k < N; k++) {
      const uk = (u0 * Math.pow(RHO, k)) / dt
      acc += (KAPPA_C * uk) ** 2
    }
    const alphaVis = softV >= 0.5 ? 1 : Math.max(0, softV / 0.5)
    sigmaCorr = Math.sqrt(acc) * alphaVis
  }

  return Math.hypot(SIGMA0, sigmaLat, sigmaAng, sigmaCorr)
}

/**
 * NE toy mix over typical vs Flash-envelope worst.
 * Unknown CD uses higher π than known-down.
 */
export function neMixCorridorVal(
  bands: { worst: number; typical: number; best: number },
  opts: {
    flashReady?: boolean
    flashCdUnknown?: boolean
    piFlash?: number
    piFlashDown?: number
  },
): number {
  if (opts.flashReady === true) return bands.typical
  const piUnk = opts.piFlash ?? 0.35
  const piDown = opts.piFlashDown ?? 0.2
  if (opts.flashReady === false && !opts.flashCdUnknown) {
    return (1 - piDown) * bands.typical + piDown * bands.worst
  }
  return (1 - piUnk) * bands.typical + piUnk * bands.worst
}

function zoneSigmaScale(zone: MapZone): number {
  switch (zone) {
    case 'brush':
      return 1.12
    case 'jungle':
      return 1.08
    case 'river':
      return 1.04
    case 'pit':
      return 1.06
    case 'base':
      return 0.98
    case 'lane':
      return 1
    default:
      return 1.03
  }
}

/**
 * Reaction delay (s): ambush lengthens defender reaction (surprise);
 * blind shortens useful aim but expands belief — handled in σ_belief.
 */
function reactionSec(vision: VisionRelation): number {
  switch (vision) {
    case 'ambush':
      return 0.38
    case 'blind':
      return 0.18
    case 'mutual':
      return 0.22
    default:
      return 0.25
  }
}

export function estimateXh(input: XhEstimateInput): XhEstimate {
  const targetMobility = mobilityOf(input.targetChampionId)
  const casterZone = zoneAt(input.casterPosition)
  const vision = input.vision ?? 'unknown'
  const softV =
    input.softVision ??
    (vision === 'blind' ? 0 : vision === 'unknown' ? 0.5 : 1)
  const fowDark = softV < 0.85 || vision === 'blind'
  const hasBelief =
    !!input.beliefMeanPosition || !!(input.beliefHypotheses?.length)
  // FoW: aim/range from belief mean when LKP/hypotheses provided; else no god-eye.
  let openLoopBelief = false
  let geoPos = input.targetPosition
  if (fowDark && hasBelief) {
    geoPos =
      input.beliefMeanPosition ??
      (() => {
        const hs = input.beliefHypotheses!
        let best = hs[0]!
        for (const h of hs) if (h.weight > best.weight) best = h
        return best.mean
      })()
  } else if (fowDark && !hasBelief) {
    openLoopBelief = true
    geoPos = undefined
  }
  const targetZone = openLoopBelief
    ? casterZone
    : zoneAt(geoPos ?? input.targetPosition)
  const factors: string[] = [`model:sigma_corridor`, `target:${targetMobility}`]
  if (hasBelief && geoPos !== input.targetPosition) factors.push('geo:belief_mean')
  if (openLoopBelief) factors.push('belief:no_lkp_guard')

  let distance: number | null = null
  if (input.casterPosition && geoPos) {
    distance = distanceGameUnits(input.casterPosition, geoPos)
  }

  const range = Math.max(1, input.abilityRange)
  const dist = distance ?? range * 0.55
  const vMissile = input.missileSpeed ?? defaultMissileSpeed(range)
  const width = input.missileWidth ?? defaultMissileWidth(range)
  const R_hit = capsuleHitRadius(width)

  const ms = input.targetMovespeed ?? 335
  // Open-loop FoW without LKP: isotropic miss (no lead on oracle pose).
  const leadSkill = openLoopBelief
    ? 0
    : Math.min(1, Math.max(0, input.leadSkill ?? 0.55))
  // Under FoW multi-hypothesis packs, strip oracle LOS kinematics from the
  // shared aim/lead path too (belief-local isotropic) — matches hyp modes.
  const fowHyp =
    !!input.beliefHypotheses?.length && softV < 0.85
  const vRadial0 = fowHyp ? 0 : (input.targetRadialVel ?? 0)
  const vPerp0 = fowHyp
    ? ms * ISOTROPIC_PERP_FRAC
    : (input.targetPerpVel ?? ms * ISOTROPIC_PERP_FRAC)
  const T_delay = Math.max(0, input.releaseDelaySec ?? 0.28)
  const atRelease = propagateLosFrame(dist, vRadial0, vPerp0, T_delay)
  const vRadial = atRelease.vRadial
  const vPerp = atRelease.vPerp
  const distRel = atRelease.rangeUu
  const tGoMis = interceptTimeGo(distRel, vMissile, vRadial, vPerp)
  const tGo = T_delay + tGoMis
  const Ltravel = input.missileMaxTravelUu ?? input.abilityRange
  const L_eff = capsuleTravelBudgetUu(Ltravel, width)
  const tContact = firstContactTimeGo(tGoMis, distRel, R_hit)
  const tEng = engagementHorizonSec(tContact, vMissile, L_eff)
  const lamStar = requiredLeadAngle(tEng, distRel, vRadial, vPerp)
  const lamAim = lamStar * leadSkill
  const cpa = ballisticSegmentCpa(
    distRel,
    vRadial,
    vPerp,
    vMissile,
    lamAim,
    tEng,
    L_eff,
  )
  const tHit = ballisticFirstContactSec(
    distRel,
    vRadial,
    vPerp,
    vMissile,
    lamAim,
    cpa.tCpaSec,
    R_hit,
  )
  const zemClock = accelZemClockSec(T_delay, tHit)
  const zemExtra = boundedAccelZemExtra(
    zemClock,
    input.residualAccelUuPerSec2 ?? 0,
  )
  const muBias = cpa.missUu + zemExtra
  factors.push(
    `t_go:${tGo.toFixed(2)}s`,
    `t_contact:${tContact.toFixed(2)}s`,
    `t_eng:${tEng.toFixed(2)}s`,
    `t_cpa:${cpa.tCpaSec.toFixed(2)}s`,
    `t_hit:${tHit.toFixed(2)}s`,
    `t_delay:${T_delay.toFixed(2)}s`,
    `lead_deg:${((lamStar * 180) / Math.PI).toFixed(1)}`,
    `R_hit:${Math.round(R_hit)}`,
    `L_travel:${Math.round(Ltravel)}`,
  )

  // Cast-time legality ∧ missile intercept reach (travel budget = Ltravel).
  let inRange = true
  if (input.casterPosition && geoPos && distance != null) {
    const castOk = inCastRange(distance, input.abilityRange)
    const reachOk = interceptInMissileRange(tGoMis, vMissile, Ltravel, R_hit)
    inRange = castOk && reachOk
    if (!inRange) {
      return {
        xH: 0,
        inRange: false,
        distance,
        targetMobility,
        targetZone,
        casterZone,
        vision,
        factors: [
          ...factors,
          'out_of_range',
          castOk ? 'reach_oor' : 'cast_oor',
        ],
        bands: { worst: 0, typical: 0, best: 0, mix: 0 },
      }
    }
  }

  let tau = reactionSec(vision)
  // They see the cast → react sooner (smaller τ), not later.
  if (input.spottedByTarget && vision === 'blind') {
    tau = Math.max(0.08, tau - 0.06)
  }
  if (input.spottedByTarget && vision === 'ambush') {
    tau = Math.max(0.22, tau - 0.08)
  }
  const T_windup = T_delay
  const dodgeWindow = Math.max(0, T_windup + tGoMis - tau)
  factors.push(`vision:${vision}`, `tau_react:${tau.toFixed(2)}`, `softV:${softV.toFixed(2)}`)

  const kitDashEarly = dashBudgetFromMobility(targetMobility)
  const dashReadyEarly =
    input.dashReady ??
    (targetMobility !== 'immobile' && targetMobility !== 'boots')
  const ageDefault = softV < 0.85 ? 2 : 0
  const age = input.lastKnownAgeSec ?? ageDefault

  // Flash CD clock → ready observation
  let flashReadyObs: boolean | undefined = input.flashReady
  if (input.flashCdRemainingSec != null) {
    flashReadyObs = input.flashCdRemainingSec <= 0
  }
  const flashCdUnknown = flashReadyObs === undefined
  const flashTypReady = flashReadyObs === true

  // --- σ_aim: Fitts + intermittent corr (τ_vm) + release–urgency timing ---
  const T_min = 0.12
  const T_lineup = 0.38
  const T_visionCut =
    softV < 0.15
      ? age < 0.25
        ? 0.03
        : 0.14
      : softV < 0.5
        ? 0.08
        : vision === 'unknown'
          ? 0.06
          : 0
  const T_avail = Math.max(T_min, input.aimTimeSec ?? T_lineup - T_visionCut)
  factors.push(`T_avail:${T_avail.toFixed(2)}s`)

  const D = dist
  const W_eff = Math.max(40, input.fittsWidthUu ?? 2 * R_hit)
  const urgencyHold = { value: 1 }
  const sigmaSpatial = schmidtAimSigma(D, T_avail, W_eff, {
    softVision: softV,
    urgencyOut: urgencyHold,
  })
  const urgency = urgencyHold.value
  const ID = fittsIndex(D, W_eff)
  factors.push(`fitts_ID:${ID.toFixed(2)}`, `urgency:${urgency.toFixed(2)}`)

  // WK + σ_r0 + super-fp + Σ_τvm + radial timing (NOT T_avail = t_go)
  const sigmaT0 = Math.max(0.02, input.releaseJitterSec ?? 0.045)
  const SIGMA_C0 = 0.036
  const SIGMA_R0 = 0.018
  const SIGMA_TAU = 0.024
  const T_prep = Math.max(0, input.releaseDelaySec ?? T_delay)
  const W_REF = 160
  const T_XREF = 0.35
  const V_EPS = 60
  const T_OPEN_AIM = 0.16
  const TAU_VM_AIM = 0.1
  const GAMMA_U = 0.4
  const GAMMA_W = 0.18
  const GAMMA_X = 0.22
  const TAU_REF = 0.22
  const GAMMA_SW = 0.45
  const T_WREF = 0.45
  const GAMMA_FP = 0.55
  const T_FPREF = 0.55
  const KAPPA_CLK = 0.55
  const KAPPA_WEBER = 0.055
  const KAPPA_FP = 0.055
  const LAMBDA_PREP = 1.25
  const KAPPA_RAD = 0.95
  const apertureTerm = Math.max(0, Math.log(W_REF / Math.max(40, W_eff)))
  const T_cross = W_eff / Math.max(Math.abs(vPerp), V_EPS)
  const crossTerm = Math.max(0, Math.log(T_XREF / Math.max(T_cross, 1e-3)))
  const T_fbAim = Math.max(0, T_avail - T_OPEN_AIM - TAU_VM_AIM)
  const sigmaRef = SIGMA_R0 * Math.exp(-T_fbAim / TAU_REF)
  const sigmaMotor = Math.hypot(
    (sigmaT0 * (1 + GAMMA_U * (urgency - 1))) / (1 + LAMBDA_PREP * T_prep),
    sigmaRef,
  )
  const sigmaClock =
    SIGMA_C0 *
    KAPPA_CLK *
    Math.hypot(1, GAMMA_W * apertureTerm, GAMMA_X * crossTerm)
  const sigmaWeber =
    KAPPA_WEBER * tGoMis * (1 + GAMMA_SW * Math.max(0, tGoMis - T_WREF))
  const sigmaFp =
    KAPPA_FP * T_prep * (1 + GAMMA_FP * Math.max(0, T_prep - T_FPREF))
  const sigmaT = Math.hypot(
    sigmaMotor,
    sigmaClock,
    sigmaWeber,
    sigmaFp,
    SIGMA_TAU,
  )
  const vTime = Math.hypot(Math.abs(vPerp), KAPPA_RAD * Math.abs(vRadial))
  const sigmaTiming = vTime * sigmaT

  // Pass-9: accel variance twin of boundedAccelZemExtra
  const KAPPA_A = 0.28
  const sigmaAccel = KAPPA_A * Math.abs(zemExtra)
  let sigmaAim = Math.hypot(sigmaSpatial, sigmaTiming, sigmaAccel)
  if (casterZone === 'brush') {
    sigmaAim *= 0.94
    factors.push('aim:caster_brush')
  }
  factors.push(
    'aim:fitts+sdn+vm+wk+weber+fp+cross+ref+tau+rad+corrDT+accel+timing',
  )

  // --- σ_juke: ready-conditioned budgets + Flash envelope for worst ---
  const cc = input.crowdControlled === true
  const ccBreak = input.ccBreakReady === true
  const kitDash = kitDashEarly
  const dashReadyObs = dashReadyEarly
  const chargesMax =
    targetMobility === 'two_dash' ? 2 : targetMobility === 'high' ? 3 : 1
  const dashTyp =
    input.dashChargesRemaining != null
      ? kitDash *
        Math.min(1, Math.max(0, input.dashChargesRemaining / chargesMax))
      : dashReadyObs
        ? kitDash
        : 0
  const flashTyp = flashTypReady ? 400 : 0
  const strafeCoeff = input.ghostActive ? 0.55 : 0.45

  function dodgeScale(w: number, wRef = 0.35): number {
    if (!(w > 0)) return 0
    return Math.min(1, w / wRef)
  }

  function jukeFromBudget(
    window: number,
    dashUu: number,
    flashUu: number,
  ): number {
    const w = Math.max(0, window)
    if (cc && !(ccBreak && w >= 0.15)) {
      return ms * w * 0.15
    }
    if (cc && ccBreak && w >= 0.15) {
      const s = dodgeScale(Math.max(0, w - 0.12))
      const strafe = ms * w * 0.2
      const discrete = Math.hypot(dashUu * s * 0.25, flashUu * s * 0.25)
      return Math.hypot(strafe * 0.55, discrete)
    }
    const strafe = ms * w * strafeCoeff
    const s = dodgeScale(w)
    const discrete = Math.hypot(dashUu * s * 0.35, flashUu * s * 0.35)
    return Math.hypot(strafe * 0.55, discrete)
  }

  const flashBuffered =
    flashTypReady || flashCdUnknown ? 1 + 0.35 * (input.flashUpPrior ?? 0.35) : 1
  const precommitUu =
    !cc && dodgeWindow <= 1e-6 && T_windup > tau * 0.45
      ? Math.min(55 * flashBuffered, 0.4 * R_hit)
      : 0

  const sigmaJukeBest = jukeFromBudget(dodgeWindow, 0, 0)
  const sigmaJukeTypical = jukeFromBudget(dodgeWindow, dashTyp, flashTyp)
  let sigmaJukeWorst = jukeFromBudget(
    dodgeWindow,
    Math.max(dashTyp, kitDash),
    400,
  )
  if (precommitUu > 0) {
    sigmaJukeWorst = Math.hypot(sigmaJukeWorst, precommitUu)
    factors.push('juke:precommit')
  }

  // --- σ_belief: reachable-set LKP + soft vision mixture ---
  function sigmaBeliefLkp(opts: {
    ageSec: number
    dashBudgetUu: number
    flashBudgetUu?: number
    brushCapUu?: number
    zone?: MapZone
  }): number {
    const a = Math.max(0, opts.ageSec)
    const kappa = 1 / Math.sqrt(3)
    const dash = opts.dashBudgetUu * (a >= 0.12 ? 1 : a / 0.12)
    const flash = (opts.flashBudgetUu ?? 0) * (a >= 0.2 ? 1 : 0)
    // Occupancy saturation: walk smear grows slowly after T_sat, then → σ_occ.
    const T_SAT = 8
    const aEff = a <= T_SAT ? a : T_SAT + 0.2 * (a - T_SAT)
    let Rmax = ms * aEff + dash + flash
    if (opts.brushCapUu != null) {
      Rmax = Math.min(Rmax, opts.brushCapUu + ms * Math.max(0, a - 1.5))
    }
    const sigSqrt = 55 * Math.sqrt(aEff)
    let reach = Math.hypot(35, kappa * Rmax, sigSqrt)
    reach = Math.min(reach, Math.max(35, Rmax))
    const sigmaOcc = occupancySigma(opts.zone ?? targetZone)
    // Asymptote toward zone occupancy, but never fully collapse (keeps ancient xH low).
    const u = Math.min(0.72, a / T_SAT)
    if (reach <= sigmaOcc) return reach
    return reach * (1 - u) + sigmaOcc * u
  }

  const flashBelief =
    softV < 0.85 && (flashReadyObs === true || flashCdUnknown)
      ? flashReadyObs === true
        ? 400
        : 400 * (input.flashUpPrior ?? 0.35)
      : 0
  const sigmaLostRaw = sigmaBeliefLkp({
    ageSec: age,
    dashBudgetUu: dashReadyObs ? kitDash : 0,
    flashBudgetUu: flashBelief,
    brushCapUu: targetZone === 'brush' ? 280 : undefined,
    zone: targetZone,
  })
  // No-LKP FoW: floor belief smear at occupancy prior (unknown pose).
  const sigmaLost = openLoopBelief
    ? Math.max(sigmaLostRaw, occupancySigma(casterZone))
    : sigmaLostRaw
  const sigmaSeen =
    input.softVisionMarginNorm != null
      ? Math.hypot(
          18,
          55 * Math.exp(-2.8 * Math.max(0, input.softVisionMarginNorm)),
        )
      : Math.hypot(18, 55 * Math.exp(-2.8 * softV))
  if (softV < 0.99) factors.push(`belief:lkp_age:${age.toFixed(1)}s`)

  const zScale = zoneSigmaScale(targetZone)
  if (zScale !== 1) factors.push(`zone_scale:${zScale.toFixed(2)}`)

  // Multi-mean: optional seen-component lateral miss (penumbra).
  let muSeen = muBias
  if (input.beliefMeanSeen && input.casterPosition && softV > 0 && softV < 1) {
    const dSeen = distanceGameUnits(input.casterPosition, input.beliefMeanSeen)
    const atS = propagateLosFrame(dSeen, vRadial0, vPerp0, T_delay)
    const tS = interceptTimeGo(atS.rangeUu, vMissile, atS.vRadial, atS.vPerp)
    const tContactS = firstContactTimeGo(tS, atS.rangeUu, R_hit)
    const tEngS = engagementHorizonSec(tContactS, vMissile, L_eff)
    const lamS = requiredLeadAngle(tEngS, atS.rangeUu, atS.vRadial, atS.vPerp)
    const cpaS = ballisticSegmentCpa(
      atS.rangeUu,
      atS.vRadial,
      atS.vPerp,
      vMissile,
      lamS * leadSkill,
      tEngS,
      L_eff,
    )
    const tHitS = ballisticFirstContactSec(
      atS.rangeUu,
      atS.vRadial,
      atS.vPerp,
      vMissile,
      lamS * leadSkill,
      cpaS.tCpaSec,
      R_hit,
    )
    const zemS = boundedAccelZemExtra(
      accelZemClockSec(T_delay, tHitS),
      input.residualAccelUuPerSec2 ?? 0,
    )
    muSeen = cpaS.missUu + zemS
    factors.push('belief:multi_mean')
  }

  function pack(sigmaJuke: number): {
    xH: number
    sigma: { aim: number; juke: number; belief: number; total: number }
  } {
    const aim = sigmaAim * zScale
    const juke = sigmaJuke * zScale
    const sigS = Math.hypot(aim, juke, sigmaSeen, 12)
    if (input.beliefHypotheses?.length && softV < 0.85) {
      const raw = input.beliefHypotheses
      const wSum = raw.reduce((s, h) => s + Math.max(0, h.weight), 0) || 1
      let xLost = 0
      let muBar = 0
      const rows: { w: number; mu: number; sigB: number }[] = []
      for (const h of raw) {
        const w = Math.max(0, h.weight) / wSum
        const dH = input.casterPosition
          ? distanceGameUnits(input.casterPosition, h.mean)
          : dist
        // FoW-local kinematics: isotropic belief vel, not oracle heading.
        const vRadH = 0
        const vPerpH = ms * ISOTROPIC_PERP_FRAC
        const atH = propagateLosFrame(dH, vRadH, vPerpH, T_delay)
        const tH = interceptTimeGo(
          atH.rangeUu,
          vMissile,
          atH.vRadial,
          atH.vPerp,
        )
        const tContactH = firstContactTimeGo(tH, atH.rangeUu, R_hit)
        const tEngH = engagementHorizonSec(tContactH, vMissile, L_eff)
        const lamH = requiredLeadAngle(
          tEngH,
          atH.rangeUu,
          atH.vRadial,
          atH.vPerp,
        )
        const aimH = lamH * leadSkill
        const cpaH = ballisticSegmentCpa(
          atH.rangeUu,
          atH.vRadial,
          atH.vPerp,
          vMissile,
          aimH,
          tEngH,
          L_eff,
        )
        const tHitH = ballisticFirstContactSec(
          atH.rangeUu,
          atH.vRadial,
          atH.vPerp,
          vMissile,
          aimH,
          cpaH.tCpaSec,
          R_hit,
        )
        const zemH = boundedAccelZemExtra(
          accelZemClockSec(T_delay, tHitH),
          input.residualAccelUuPerSec2 ?? 0,
        )
        const muK = cpaH.missUu + zemH
        const zH = h.zone ?? zoneAt(h.mean)
        const sigB =
          h.sigmaBelief ??
          sigmaBeliefLkp({
            ageSec: h.ageSec ?? age,
            dashBudgetUu: dashReadyObs ? kitDash : 0,
            flashBudgetUu: flashBelief,
            brushCapUu: zH === 'brush' ? 280 : undefined,
            zone: zH,
          })
        xLost += w * corridorHitProb(R_hit, muK, Math.hypot(aim, juke, sigB, 12))
        rows.push({ w, mu: muK, sigB })
        muBar += w * muK
      }
      let belief2 = 0
      for (const r of rows) {
        belief2 += r.w * (r.sigB * r.sigB + (r.mu - muBar) ** 2)
      }
      const xH =
        softV * corridorHitProb(R_hit, muSeen, sigS) + (1 - softV) * xLost
      const s = Math.min(1, Math.max(0, softV))
      const belief = Math.sqrt(
        s * sigmaSeen * sigmaSeen +
          (1 - s) * belief2 +
          s * (1 - s) * (muSeen - muBar) ** 2,
      )
      factors.push(`belief:mixture_modes:${rows.length}`)
      return {
        xH: clamp01(xH),
        sigma: {
          aim,
          juke,
          belief,
          total: Math.hypot(aim, juke, belief, 12),
        },
      }
    }
    const sigL = Math.hypot(aim, juke, sigmaLost, 12)
    const xH =
      softV * corridorHitProb(R_hit, muSeen, sigS) +
      (1 - softV) * corridorHitProb(R_hit, muBias, sigL)
    const s = Math.min(1, Math.max(0, softV))
    const belief = Math.sqrt(
      s * sigmaSeen * sigmaSeen +
        (1 - s) * sigmaLost * sigmaLost +
        s * (1 - s) * (muSeen - muBias) ** 2,
    )
    const total = Math.hypot(aim, juke, belief, 12)
    return {
      xH: clamp01(xH),
      sigma: { aim, juke, belief, total },
    }
  }

  const typical = pack(sigmaJukeTypical)
  const worst = pack(sigmaJukeWorst)
  const best = pack(sigmaJukeBest)
  const mix = neMixCorridorVal(
    { worst: worst.xH, typical: typical.xH, best: best.xH },
    {
      flashReady: flashReadyObs,
      flashCdUnknown,
      piFlash: input.flashUpPrior,
      piFlashDown: input.flashUpPriorDown,
    },
  )
  if (flashCdUnknown) factors.push('juke:ne_mix')
  else if (flashReadyObs === false) factors.push('juke:ne_mix_down')

  if (input.skillshotLengthPenalty && range >= 900) {
    factors.push('long_skillshot_width')
  }

  factors.push(
    `sigma:${Math.round(typical.sigma.total)}`,
    `mu_bias:${Math.round(muBias)}`,
  )

  // CD unknown → packet uses NE mix; else observed typical.
  const xH = flashCdUnknown ? mix : typical.xH

  return {
    xH,
    inRange,
    distance,
    targetMobility,
    targetZone,
    casterZone,
    vision,
    factors,
    bands: {
      worst: worst.xH,
      typical: typical.xH,
      best: best.xH,
      mix,
    },
    sigma: typical.sigma,
  }
}

function clamp01(x: number): number {
  if (!Number.isFinite(x)) return 0
  return Math.min(0.995, Math.max(0.005, x))
}

/**
 * Shared-latent multi-hit PMF via equicorrelated probit (analytic 1D mixture).
 * Conditionally on Z: K|Z ~ Bin(n, π(Z)), π = Φ((c−√ρ Z)/√(1−ρ)), c=Φ^{-1}(p).
 * Ochi & Prentice 1984; replaces MC for determinism.
 */
export function estimateXhm(
  singleXh: number,
  enemiesInRange: number,
  rho = 0.45,
): number[] {
  const n = Math.max(0, enemiesInRange)
  const p = Math.min(0.99, Math.max(0.01, singleXh))
  const rhoClamped = Math.min(0.95, Math.max(0, rho))
  if (n === 0) return [1]
  if (n === 1) return [1 - p, p]
  if (rhoClamped < 1e-12) return binomialPmfs(n, p)

  const c = invNormCdf(p)
  const sR = Math.sqrt(rhoClamped)
  const sI = Math.sqrt(1 - rhoClamped)
  const counts = new Array(n + 1).fill(0)
  const dz = 0.002
  const lo = -8
  const hi = 8
  for (let z = lo; z <= hi + 1e-12; z += dz) {
    const w = z === lo || z >= hi - 1e-12 ? 0.5 : 1
    const mass = w * normPdf(z) * dz
    const pi = Math.min(
      1 - 1e-12,
      Math.max(1e-12, normCdf((c - sR * z) / sI)),
    )
    const bin = binomialPmfs(n, pi)
    for (let k = 0; k <= n; k++) counts[k] += mass * bin[k]!
  }
  const sum = counts.reduce((a: number, b: number) => a + b, 0) || 1
  return counts.map((v: number) => v / sum)
}

function normPdf(z: number): number {
  return Math.exp(-0.5 * z * z) / Math.sqrt(2 * Math.PI)
}

function binomialPmfs(n: number, p: number): number[] {
  const out = new Array(n + 1).fill(0)
  let coef = 1
  for (let k = 0; k <= n; k++) {
    out[k] = coef * Math.pow(p, k) * Math.pow(1 - p, n - k)
    coef = (coef * (n - k)) / (k + 1)
  }
  return out
}

function invNormCdf(p: number): number {
  const u = Math.min(0.999999, Math.max(1e-6, p))
  return Math.SQRT2 * erfinv(2 * u - 1)
}

function erfinv(x: number): number {
  const a = 0.147
  const sgn = x < 0 ? -1 : 1
  const ln = Math.log(1 - x * x)
  const t1 = 2 / (Math.PI * a) + ln / 2
  const t2 = ln / a
  return sgn * Math.sqrt(Math.sqrt(t1 * t1 - t2) - t1)
}

export function applyXhModeToPacket(
  packet: DamagePacket,
  xH: number,
  mode: XhMode,
): DamagePacket {
  if (!packet.skillshot || mode === 'off' || mode === 'hit_all') {
    return {
      ...packet,
      xH: packet.skillshot
        ? mode === 'hit_all' || mode === 'off'
          ? 1
          : packet.xH
        : undefined,
      rawBeforeXh: packet.rawBeforeXh ?? packet.raw,
    }
  }
  if (mode === 'miss_shots') {
    return {
      ...packet,
      rawBeforeXh: packet.rawBeforeXh ?? packet.raw,
      xH: 0,
      raw: 0,
    }
  }
  const before = packet.rawBeforeXh ?? packet.raw
  return {
    ...packet,
    rawBeforeXh: before,
    xH,
    raw: before * xH,
  }
}

export function resolveCastVision(input: {
  casterPosition?: MapPosition
  targetPosition?: MapPosition
  casterTeam: 'blue' | 'red'
  targetTeam: 'blue' | 'red'
  units: VisionUnit[]
  wards?: VisionWard[]
  meta?: TerrainMeta | null
}): VisionRelation {
  if (!input.casterPosition || !input.targetPosition) return 'unknown'
  const wards = input.wards ?? []
  const casterSees = isVisibleToTeam(
    input.targetPosition,
    input.targetTeam,
    input.casterTeam,
    input.units,
    wards,
    input.meta,
  )
  if (!casterSees) return 'blind'
  const targetSees = isVisibleToTeam(
    input.casterPosition,
    input.casterTeam,
    input.targetTeam,
    input.units,
    wards,
    input.meta,
  )
  return targetSees ? 'mutual' : 'ambush'
}

export function abilityXhPreview(
  ability: AbilityDefinition,
  input: Omit<XhEstimateInput, 'abilityRange'>,
): XhEstimate {
  return estimateXh({
    ...input,
    abilityRange: ability.range,
    missileWidth: input.missileWidth ?? ability.missileWidth,
    missileSpeed: input.missileSpeed ?? ability.missileSpeed,
    releaseDelaySec: input.releaseDelaySec ?? ability.releaseDelaySec,
    missileMaxTravelUu:
      input.missileMaxTravelUu ?? ability.missileMaxTravelUu ?? ability.range,
    skillshotLengthPenalty: ability.range >= 900,
  })
}
