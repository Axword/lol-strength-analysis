import { CHAMPIONS } from '../data/champions'
import type { GameUnit } from '../game/types'
import {
  estimateXh,
  estimateXhm,
  zoneAt,
} from './xh'
import {
  resolveCastVisionSoft,
  type TerrainMeta,
  type VisionWard,
} from './vision'

export interface SkillshotXhLink {
  casterId: string
  targetId: string
  abilitySlot: string
  abilityName: string
  abilityRange: number
  xH: number
  inRange: boolean
  distance: number | null
  targetMobility: string
  targetZone: string
  casterZone: string
  vision: string
}

export interface CasterXhSummary {
  casterId: string
  championId: string
  links: SkillshotXhLink[]
  /** Mean xH across in-range skillshot→target pairs */
  avgXh: number | null
  /** xHm distribution for the longest in-range AOE-ish skillshot vs all enemies in that range */
  xhm?: { abilityName: string; probs: number[]; enemiesInRange: number }
}

export interface SnapshotXhOptions {
  wards?: VisionWard[]
  terrain?: TerrainMeta | null
}

/** Build xH links from selected casters toward enemy units on the snapshot. */
export function buildSnapshotXh(
  units: GameUnit[],
  casterIds: string[],
  options: SnapshotXhOptions = {},
): CasterXhSummary[] {
  const byId = new Map(units.map((u) => [u.id, u]))
  const summaries: CasterXhSummary[] = []
  const visionUnits = units.map((u) => ({
    id: u.id,
    team: u.team,
    position: u.position,
    alive: u.alive,
  }))
  const wards = options.wards ?? []

  for (const casterId of casterIds) {
    const caster = byId.get(casterId)
    if (!caster) continue
    const champ = CHAMPIONS[caster.loadout.championId]
    if (!champ) continue

    const enemies = units.filter((u) => u.team !== caster.team)
    const links: SkillshotXhLink[] = []

    for (const ability of champ.abilities) {
      if (!ability.skillshot) continue
      for (const enemy of enemies) {
        const resolved = resolveCastVisionSoft({
          casterPosition: caster.position,
          targetPosition: enemy.position,
          casterTeam: caster.team,
          targetTeam: enemy.team,
          units: visionUnits,
          wards,
          meta: options.terrain,
        })
        const est = estimateXh({
          targetChampionId: enemy.loadout.championId,
          casterPosition: caster.position,
          targetPosition: enemy.position,
          abilityRange: ability.range,
          skillshotLengthPenalty: ability.range >= 900,
          vision: resolved.vision,
          softVision: resolved.softVision,
          softVisionMarginNorm: resolved.softVisionMarginNorm,
          spottedByTarget: resolved.spottedByTarget,
        })
        links.push({
          casterId,
          targetId: enemy.id,
          abilitySlot: ability.slot,
          abilityName: ability.name,
          abilityRange: ability.range,
          xH: est.xH,
          inRange: est.inRange,
          distance: est.distance,
          targetMobility: est.targetMobility,
          targetZone: est.targetZone,
          casterZone: est.casterZone,
          vision: est.vision,
        })
      }
    }

    const inRangeLinks = links.filter((l) => l.inRange)
    const avgXh =
      inRangeLinks.length > 0
        ? inRangeLinks.reduce((s, l) => s + l.xH, 0) / inRangeLinks.length
        : null

    // xHm on the longest skillshot that has anyone in range
    let xhm: CasterXhSummary['xhm']
    const skillshots = champ.abilities.filter((a) => a.skillshot)
    const sorted = [...skillshots].sort((a, b) => b.range - a.range)
    for (const ability of sorted) {
      const inR = enemies.filter((e) => {
        const est = estimateXh({
          targetChampionId: e.loadout.championId,
          casterPosition: caster.position,
          targetPosition: e.position,
          abilityRange: ability.range,
        })
        return est.inRange
      })
      if (inR.length >= 1) {
        const resolved = resolveCastVisionSoft({
          casterPosition: caster.position,
          targetPosition: inR[0].position,
          casterTeam: caster.team,
          targetTeam: inR[0].team,
          units: visionUnits,
          wards,
          meta: options.terrain,
        })
        const single = estimateXh({
          targetChampionId: inR[0].loadout.championId,
          casterPosition: caster.position,
          targetPosition: inR[0].position,
          abilityRange: ability.range,
          vision: resolved.vision,
          softVision: resolved.softVision,
          softVisionMarginNorm: resolved.softVisionMarginNorm,
          spottedByTarget: resolved.spottedByTarget,
        }).xH
        xhm = {
          abilityName: ability.name,
          enemiesInRange: inR.length,
          probs: estimateXhm(single, inR.length),
        }
        break
      }
    }

    summaries.push({
      casterId,
      championId: caster.loadout.championId,
      links,
      avgXh,
      xhm,
    })
  }

  return summaries
}

export function unitZoneLabel(unit: GameUnit): string {
  return zoneAt(unit.position)
}
