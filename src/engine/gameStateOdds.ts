/**
 * Fight win odds from game state + combat pressure.
 *
 * Grounded in FUR vs G2 kill clusters (events_2970115_1_riot.jsonl):
 * after ~16m with Red gold lead, every clustered fight went Red; Red won the map.
 * A pure leftover-HP% verdict can call Blue the winner on a light poke while Red
 * is +6k with baron — that is rejected here.
 */

import type { TeamObjectives } from './objectives'
import type { FighterLoadout, SideResult } from './types'

export interface FightOddsInput {
  blue: TeamObjectives | null | undefined
  red: TeamObjectives | null | undefined
  blueLoadouts: FighterLoadout[]
  redLoadouts: FighterLoadout[]
  blueCombat: SideResult
  redCombat: SideResult
}

export interface FightOdds {
  /** P(blue wins the fight), 0..1 */
  pBlue: number
  pRed: number
  winner: 'blue' | 'red' | 'draw'
  /** Confidence gap |pBlue - 0.5| */
  edge: number
  priorLogit: number
  combatLogit: number
  factors: string[]
}

function sigmoid(x: number): number {
  if (x > 20) return 1
  if (x < -20) return 0
  return 1 / (1 + Math.exp(-x))
}

function meanLevel(loadouts: FighterLoadout[]): number {
  const living = loadouts.filter((l) => l.alive !== false && (l.hpPct == null || l.hpPct > 0))
  const list = living.length ? living : loadouts
  if (!list.length) return 1
  return list.reduce((s, l) => s + (l.level || 1), 0) / list.length
}

function livingCount(loadouts: FighterLoadout[]): number {
  return loadouts.filter((l) => l.alive !== false && (l.hpPct == null || l.hpPct > 0)).length
}

/** Objective / gold / level prior in blue-minus-red logit space. */
export function gameStateLogit(
  blue: TeamObjectives | null | undefined,
  red: TeamObjectives | null | undefined,
  blueLoadouts: FighterLoadout[],
  redLoadouts: FighterLoadout[],
): { logit: number; factors: string[] } {
  const factors: string[] = []
  if (!blue || !red) {
    return { logit: 0, factors: ['no_scoreboard'] }
  }

  const goldDelta = blue.gold - red.gold // blue − red
  const goldTerm = (goldDelta / 4000) * 1.45
  factors.push(`goldΔ ${Math.round(goldDelta)}`)

  const lvB = meanLevel(blueLoadouts)
  const lvR = meanLevel(redLoadouts)
  const levelTerm = (lvB - lvR) * 0.4
  factors.push(`lvl ${lvB.toFixed(1)} vs ${lvR.toFixed(1)}`)

  // Map-control prior: baron/elder/soul/towers/kills/gold — not champ DPS (grubs are structure-only).
  let obj = 0
  if (blue.baronActive) obj += 1.15
  if (red.baronActive) obj -= 1.15
  if (blue.elderActive) obj += 1.35
  if (red.elderActive) obj -= 1.35
  const blueDrakes = Math.max(0, blue.dragonCount - (blue.hasSoul ? 1 : 0))
  const redDrakes = Math.max(0, red.dragonCount - (red.hasSoul ? 1 : 0))
  obj += (blueDrakes - redDrakes) * 0.38
  if (blue.hasSoul) obj += 0.85
  if (red.hasSoul) obj -= 0.85
  obj += (blue.towers - red.towers) * 0.14
  obj += ((blue.kills - red.kills) / 5) * 0.45
  if (blue.baronActive || red.baronActive) {
    factors.push(blue.baronActive ? 'baron blue LIVE' : 'baron red LIVE')
  }
  if (blue.dragonCount || red.dragonCount) {
    factors.push(`drakes ${blue.dragonCount}-${red.dragonCount}`)
  }

  // Numbers alive — a near-dead fifth still counts as living but is weak;
  // also penalize being down a body if someone is fully dead.
  const aliveTerm = (livingCount(blueLoadouts) - livingCount(redLoadouts)) * 0.55

  const logit = goldTerm + levelTerm + obj + aliveTerm
  return { logit, factors }
}

/**
 * Combat pressure logit. Absolute HP removed matters more than leftover HP%.
 * Light poke (both sides barely scratched) is down-weighted so game state leads.
 */
export function combatPressureLogit(
  blue: SideResult,
  red: SideResult,
): { logit: number; weight: number; factors: string[] } {
  const blueP = blue.damagePctOfEnemy
  const redP = red.damagePctOfEnemy
  const total = blueP + redP
  // Full teamfight pressure ~0.7+ combined; poke ~0.3
  const weight = Math.min(1, Math.max(0.2, total / 0.75))
  const logit = 2.8 * (blueP - redP)
  return {
    logit,
    weight,
    factors: [
      `pressure B${Math.round(blueP * 100)}%/R${Math.round(redP * 100)}%`,
      `combatWeight ${weight.toFixed(2)}`,
    ],
  }
}

export function estimateFightOdds(input: FightOddsInput): FightOdds {
  const prior = gameStateLogit(
    input.blue,
    input.red,
    input.blueLoadouts,
    input.redLoadouts,
  )
  const combat = combatPressureLogit(input.blueCombat, input.redCombat)
  const logit = prior.logit + combat.weight * combat.logit
  const pBlue = sigmoid(logit)
  const pRed = 1 - pBlue
  const edge = Math.abs(pBlue - 0.5)

  let winner: FightOdds['winner'] = 'draw'
  // Require a real edge — 55/45 is still "lean"; 60/40 calls it
  if (pBlue >= 0.58) winner = 'blue'
  else if (pRed >= 0.58) winner = 'red'

  // Extreme game-state: never call the behind side the winner on poke alone
  if (
    input.blue &&
    input.red &&
    Math.abs(input.blue.gold - input.red.gold) >= 5000 &&
    combat.weight < 0.55
  ) {
    const goldLeader = input.blue.gold >= input.red.gold ? 'blue' : 'red'
    if (winner !== goldLeader && winner !== 'draw') {
      winner = goldLeader
    }
    if (winner === 'draw') winner = goldLeader
  }

  // Baron LIVE with gold lead: floor the favorite
  if (input.red?.baronActive && (input.red.gold - (input.blue?.gold ?? 0)) >= 3000) {
    if (pRed < 0.7) {
      return {
        pBlue: 1 - 0.72,
        pRed: 0.72,
        winner: 'red',
        edge: 0.22,
        priorLogit: prior.logit,
        combatLogit: combat.logit,
        factors: [...prior.factors, ...combat.factors, 'baron+gold floor'],
      }
    }
  }
  if (input.blue?.baronActive && (input.blue.gold - (input.red?.gold ?? 0)) >= 3000) {
    if (pBlue < 0.7) {
      return {
        pBlue: 0.72,
        pRed: 1 - 0.72,
        winner: 'blue',
        edge: 0.22,
        priorLogit: prior.logit,
        combatLogit: combat.logit,
        factors: [...prior.factors, ...combat.factors, 'baron+gold floor'],
      }
    }
  }

  return {
    pBlue,
    pRed,
    winner,
    edge,
    priorLogit: prior.logit,
    combatLogit: combat.logit,
    factors: [...prior.factors, ...combat.factors],
  }
}
