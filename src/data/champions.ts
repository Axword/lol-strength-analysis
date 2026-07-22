import type { AbilityContext, AbilityDefinition, ChampionDefinition } from '../engine/types'
import { bonusAd, rankOf } from '../engine/types'
import { GAME_CHAMPIONS } from './generatedGameChamps'

const DDRAGON = '16.14.1'

function rankValue(values: number[], rank: number): number {
  const idx = Math.min(values.length, Math.max(1, rank)) - 1
  return values[idx]
}

function aa(shortCount: number, allinCount: number) {
  return (m: 'short' | 'allin' | 'extended') => {
    if (m === 'short') return shortCount
    if (m === 'allin') return allinCount
    return allinCount * 2 + 2
  }
}

function makeChamp(
  partial: Omit<ChampionDefinition, 'abilities' | 'autoAttacksInTrade'> & {
    abilities: AbilityDefinition[]
    autos: [number, number]
  },
): ChampionDefinition {
  const { autos, ...rest } = partial
  return {
    ...rest,
    autoAttacksInTrade: aa(autos[0], autos[1]),
  }
}

/** Approximate patch 16.x numbers — good enough for v1 relative compare. */
const CORE_CHAMPIONS: Record<string, ChampionDefinition> = {
  Gragas: makeChamp({
    id: 'Gragas',
    name: 'Gragas',
    title: 'the Rabble Rouser',
    tags: ['Fighter', 'Mage'],
    passiveName: 'Happy Hour',
    stats: {
      hp: 640, hpperlevel: 115, mp: 400, mpperlevel: 47, movespeed: 330,
      armor: 38, armorperlevel: 5, spellblock: 32, spellblockperlevel: 2.05,
      attackrange: 125, hpregen: 5.5, hpregenperlevel: 0.5, mpregen: 6, mpregenperlevel: 0.8,
      crit: 0, critperlevel: 0, attackdamage: 64, attackdamageperlevel: 3.5,
      // attackspeedratio from local Meraki champions-full.json (Gragas ratio ≠ base).
      attackspeedperlevel: 2.05, attackspeed: 0.675, attackspeedratio: 0.625,
    },
    autos: [1, 3],
    abilities: [
      {
        slot: 'Q',
        name: 'Barrel Roll',
        range: 850,
        cooldown: 8,
        skillshot: true,
        damage: (a, _d, ctx) => {
          const base = rankValue([80, 120, 160, 200, 240], rankOf(ctx, 'Q'))
          const raw = base + 0.8 * a.ap
          return [{ raw, type: 'magical', source: 'Barrel Roll', slot: 'Q', skillshot: true }]
        },
      },
      {
        slot: 'W',
        name: 'Drunken Rage',
        range: 250,
        cooldown: 5,
        skillshot: false,
        damage: (a, d, ctx) => {
          const base = rankValue([20, 50, 80, 110, 140], rankOf(ctx, 'W'))
          // Wiki: +7% of target's maximum health (flat by rank) + 70% AP
          const raw = base + 0.7 * a.ap + 0.07 * d.hpMax
          return [{ raw, type: 'magical', source: 'Drunken Rage', slot: 'W' }]
        },
      },
      {
        slot: 'E',
        name: 'Body Slam',
        range: 600,
        cooldown: 13,
        skillshot: true,
        engageCc: true,
        damage: (a, _d, ctx) => {
          const base = rankValue([80, 125, 170, 215, 260], rankOf(ctx, 'E'))
          const raw = base + 0.6 * a.ap
          return [{ raw, type: 'magical', source: 'Body Slam', slot: 'E', skillshot: true }]
        },
      },
      {
        slot: 'R',
        name: 'Explosive Cask',
        range: 1000,
        cooldown: 100,
        skillshot: true,
        damage: (a, _d, ctx) => {
          const base = rankValue([200, 300, 400], rankOf(ctx, 'R'))
          const raw = base + 0.8 * a.ap
          return [{ raw, type: 'magical', source: 'Explosive Cask', slot: 'R', skillshot: true }]
        },
      },
    ],
  }),

  Darius: makeChamp({
    id: 'Darius',
    name: 'Darius',
    title: 'the Hand of Noxus',
    tags: ['Fighter', 'Tank'],
    passiveName: 'Hemorrhage',
    stats: {
      hp: 652, hpperlevel: 114, mp: 263, mpperlevel: 58, movespeed: 340,
      armor: 37, armorperlevel: 5.2, spellblock: 32, spellblockperlevel: 2.05,
      attackrange: 175, hpregen: 10, hpregenperlevel: 0.95, mpregen: 6.6, mpregenperlevel: 0.35,
      crit: 0, critperlevel: 0, attackdamage: 64, attackdamageperlevel: 5,
      attackspeedperlevel: 1, attackspeed: 0.625, attackspeedratio: 0.625,
    },
    autos: [2, 4],
    passiveDamage: (a, _d, ctx) => {
      // 5 stacks bleed approx as bonus true damage chunk in all-in
      if (ctx.mode !== 'allin') {
        return [{
          raw: 0.3 * a.ad * 3,
          type: 'physical',
          source: 'Hemorrhage (3 stacks)',
          slot: 'P',
        }]
      }
      return [{
        raw: 0.3 * a.ad * 5 + (15 + a.level * 5),
        type: 'true',
        source: 'Noxian Guillotine reset bleed',
        slot: 'P',
      }]
    },
    abilities: [
      {
        slot: 'Q',
        name: 'Decimate',
        range: 425,
        cooldown: 7,
        skillshot: false,
        damage: (a, _d, ctx) => {
          // Meraki: blade = base + 100% AD
          const blade = rankValue([50, 80, 110, 140, 170], rankOf(ctx, 'Q')) + 1.0 * a.ad
          return [{ raw: blade, type: 'physical', source: 'Decimate (blade)', slot: 'Q' }]
        },
      },
      {
        slot: 'W',
        name: 'Crippling Strike',
        range: 300,
        cooldown: 5,
        skillshot: false,
        // Empowered auto + attack reset: packet already includes AA + bonus.
        execution: {
          attackReset: true,
          empoweredAuto: true,
          castLockSec: 0.15,
          impactDelaySec: 0.1,
        },
        damage: (a, _d, ctx) => {
          // Wiki: bonus physical = 40/45/50/55/60% AD on the empowered basic attack.
          // Total = AD + bonus = AD × (1 + ratio). One packet only — no second base-AD AA.
          const ratio = rankValue([0.4, 0.45, 0.5, 0.55, 0.6], rankOf(ctx, 'W'))
          return [{
            raw: a.ad * (1 + ratio),
            type: 'physical',
            source: 'Crippling Strike',
            slot: 'W',
          }]
        },
      },
      {
        slot: 'E',
        name: 'Apprehend',
        range: 535,
        cooldown: 18,
        skillshot: false,
        engageCc: true,
        utility: (_a, _d, ctx) => ({
          // Meraki: 20/25/30/35/40% armor pen as shred proxy for the trade
          armorShred: rankValue([0.2, 0.25, 0.3, 0.35, 0.4], rankOf(ctx, 'E')),
          hardCc: true,
          engageCc: true,
        }),
        damage: () => [],
      },
      {
        slot: 'R',
        name: 'Noxian Guillotine',
        range: 460,
        cooldown: 120,
        skillshot: false,
        damage: (a, _d, ctx) => {
          const base = rankValue([125, 250, 375], rankOf(ctx, 'R'))
          const raw = base + 0.75 * bonusAd(a)
          return [{ raw, type: 'true', source: 'Noxian Guillotine', slot: 'R' }]
        },
      },
    ],
  }),

  Ahri: makeChamp({
    id: 'Ahri',
    name: 'Ahri',
    title: 'the Nine-Tailed Fox',
    tags: ['Mage', 'Assassin'],
    passiveName: 'Essence Theft',
    stats: {
      hp: 590, hpperlevel: 96, mp: 418, mpperlevel: 25, movespeed: 330,
      armor: 21, armorperlevel: 4.7, spellblock: 30, spellblockperlevel: 1.3,
      attackrange: 550, hpregen: 2.5, hpregenperlevel: 0.6, mpregen: 8, mpregenperlevel: 0.8,
      crit: 0, critperlevel: 0, attackdamage: 53, attackdamageperlevel: 3,
      attackspeedperlevel: 2.2, attackspeed: 0.668, attackspeedratio: 0.625,
    },
    autos: [1, 2],
    abilities: [
      {
        slot: 'Q',
        name: 'Orb of Deception',
        range: 970,
        cooldown: 7,
        skillshot: true,
        damage: (a, _d, ctx) => {
          const base = rankValue([40, 65, 90, 115, 140], rankOf(ctx, 'Q'))
          const one = base + 0.5 * a.ap
          return [
            { raw: one, type: 'magical', source: 'Orb (out)', slot: 'Q', skillshot: true },
            { raw: one, type: 'true', source: 'Orb (return)', slot: 'Q', skillshot: true },
          ]
        },
      },
      {
        slot: 'W',
        name: 'Fox-Fire',
        range: 700,
        cooldown: 9,
        skillshot: false,
        damage: (a, _d, ctx) => {
          const base = rankValue([40, 60, 80, 100, 120], rankOf(ctx, 'W'))
          const first = base + 0.4 * a.ap
          const second = first * 0.3
          return [
            { raw: first, type: 'magical', source: 'Fox-Fire 1', slot: 'W' },
            { raw: second, type: 'magical', source: 'Fox-Fire 2', slot: 'W' },
          ]
        },
      },
      {
        slot: 'E',
        name: 'Charm',
        range: 975,
        cooldown: 12,
        skillshot: true,
        engageCc: true,
        damage: (a, _d, ctx) => {
          const base = rankValue([80, 120, 160, 200, 240], rankOf(ctx, 'E'))
          return [{ raw: base + 0.85 * a.ap, type: 'magical', source: 'Charm', slot: 'E', skillshot: true }]
        },
      },
      {
        slot: 'R',
        name: 'Spirit Rush',
        range: 450,
        cooldown: 130,
        skillshot: false,
        damage: (a, _d, ctx) => {
          const base = rankValue([60, 90, 120], rankOf(ctx, 'R'))
          const dash = base + 0.35 * a.ap
          return [
            { raw: dash, type: 'magical', source: 'Spirit Rush 1', slot: 'R' },
            { raw: dash, type: 'magical', source: 'Spirit Rush 2', slot: 'R' },
            { raw: dash, type: 'magical', source: 'Spirit Rush 3', slot: 'R' },
          ]
        },
      },
    ],
  }),

  Garen: makeChamp({
    id: 'Garen',
    name: 'Garen',
    title: 'the Might of Demacia',
    tags: ['Fighter', 'Tank'],
    passiveName: 'Perseverance',
    stats: {
      hp: 690, hpperlevel: 98, mp: 0, mpperlevel: 0, movespeed: 340,
      armor: 38, armorperlevel: 4.2, spellblock: 32, spellblockperlevel: 2.05,
      attackrange: 175, hpregen: 8, hpregenperlevel: 0.5, mpregen: 0, mpregenperlevel: 0,
      crit: 0, critperlevel: 0, attackdamage: 69, attackdamageperlevel: 4.5,
      attackspeedperlevel: 3.65, attackspeed: 0.625, attackspeedratio: 0.625,
    },
    autos: [2, 4],
    abilities: [
      {
        slot: 'Q',
        name: 'Decisive Strike',
        range: 300,
        cooldown: 8,
        skillshot: false,
        engageCc: true,
        damage: (a, _d, ctx) => {
          const base = rankValue([30, 60, 90, 120, 150], rankOf(ctx, 'Q'))
          return [{ raw: base + 0.5 * a.ad, type: 'physical', source: 'Decisive Strike', slot: 'Q' }]
        },
      },
      {
        slot: 'W',
        name: 'Courage',
        range: 0,
        cooldown: 22,
        skillshot: false,
        utility: (_a, _d, ctx) => ({
          // Tenacity + damage reduction window — approximate DR for the trade
          damageReduction: rankValue([0.3, 0.32, 0.34, 0.36, 0.38], rankOf(ctx, 'W')),
        }),
        damage: () => [],
      },
      {
        slot: 'E',
        name: 'Judgment',
        range: 325,
        cooldown: 9,
        skillshot: false,
        damage: (a, _d, ctx) => {
          const spins = 6
          const per = rankValue([4, 8, 12, 16, 20], rankOf(ctx, 'E')) + 0.36 * a.ad
          return [{ raw: per * spins, type: 'physical', source: `Judgment (${spins} spins)`, slot: 'E' }]
        },
      },
      {
        slot: 'R',
        name: 'Demacian Justice',
        range: 400,
        cooldown: 120,
        skillshot: false,
        damage: (_a, d, ctx) => {
          const base = rankValue([150, 300, 450], rankOf(ctx, 'R'))
          // Meraki: +25% of target's missing health
          const missing = Math.max(0, d.hpMax - d.hp)
          return [{ raw: base + 0.25 * missing, type: 'true', source: 'Demacian Justice', slot: 'R' }]
        },
      },
    ],
  }),

  Jax: makeChamp({
    id: 'Jax',
    name: 'Jax',
    title: 'Grandmaster at Arms',
    tags: ['Fighter', 'Assassin'],
    passiveName: 'Relentless Assault',
    stats: {
      hp: 665, hpperlevel: 100, mp: 339, mpperlevel: 52, movespeed: 350,
      armor: 36, armorperlevel: 4.2, spellblock: 32, spellblockperlevel: 2.05,
      attackrange: 125, hpregen: 8.5, hpregenperlevel: 0.55, mpregen: 7.6, mpregenperlevel: 0.7,
      crit: 0, critperlevel: 0, attackdamage: 68, attackdamageperlevel: 4.25,
      attackspeedperlevel: 3.4, attackspeed: 0.638, attackspeedratio: 0.638,
    },
    autos: [3, 5],
    abilities: [
      {
        slot: 'Q',
        name: 'Leap Strike',
        range: 700,
        cooldown: 8,
        skillshot: false,
        engageCc: true,
        damage: (a, _d, ctx) => {
          const base = rankValue([65, 105, 145, 185, 225], rankOf(ctx, 'Q'))
          return [{ raw: base + 1.0 * bonusAd(a), type: 'physical', source: 'Leap Strike', slot: 'Q' }]
        },
      },
      {
        slot: 'W',
        name: 'Empower',
        range: 250,
        cooldown: 7,
        skillshot: false,
        damage: (a, _d, ctx) => {
          const base = rankValue([50, 85, 120, 155, 190], rankOf(ctx, 'W'))
          return [{ raw: base + 0.6 * a.ap, type: 'magical', source: 'Empower', slot: 'W' }]
        },
      },
      {
        slot: 'E',
        name: 'Counter Strike',
        range: 300,
        cooldown: 14,
        skillshot: false,
        damage: (a, d, ctx) => {
          const base = rankValue([40, 70, 100, 130, 160], rankOf(ctx, 'E'))
          const raw = base + 0.7 * a.ap + 0.035 * d.hpMax
          return [{ raw, type: 'magical', source: 'Counter Strike', slot: 'E' }]
        },
      },
      {
        slot: 'R',
        name: 'Grandmaster-At-Arms',
        range: 250,
        cooldown: 80,
        skillshot: false,
        damage: (a, _d, ctx) => {
          const base = rankValue([100, 175, 250], rankOf(ctx, 'R'))
          // 3 empowered-auto passive procs in an all-in window
          const proc = (base + 1.0 * a.ap) * 3
          return [{ raw: proc, type: 'magical', source: 'R procs (×3)', slot: 'R' }]
        },
      },
    ],
  }),

  Lux: makeChamp({
    id: 'Lux',
    name: 'Lux',
    title: 'the Lady of Luminosity',
    tags: ['Mage', 'Support'],
    passiveName: 'Illumination',
    stats: {
      hp: 580, hpperlevel: 99, mp: 480, mpperlevel: 23.5, movespeed: 330,
      armor: 19, armorperlevel: 5.2, spellblock: 30, spellblockperlevel: 1.3,
      attackrange: 550, hpregen: 5.5, hpregenperlevel: 0.55, mpregen: 8, mpregenperlevel: 0.8,
      crit: 0, critperlevel: 0, attackdamage: 54, attackdamageperlevel: 3.3,
      attackspeedperlevel: 2, attackspeed: 0.669, attackspeedratio: 0.625,
    },
    autos: [1, 2],
    passiveDamage: (a) => [
      {
        raw: 20 + 8 * a.level + 0.2 * a.ap,
        type: 'magical',
        source: 'Illumination',
        slot: 'P',
      },
    ],
    abilities: [
      {
        slot: 'Q',
        name: 'Light Binding',
        range: 1175,
        cooldown: 11,
        skillshot: true,
        engageCc: true,
        damage: (a, _d, ctx) => {
          const base = rankValue([80, 120, 160, 200, 240], rankOf(ctx, 'Q'))
          return [{ raw: base + 0.65 * a.ap, type: 'magical', source: 'Light Binding', slot: 'Q', skillshot: true }]
        },
      },
      {
        slot: 'W',
        name: 'Prismatic Barrier',
        range: 1075,
        cooldown: 14,
        skillshot: false,
        utility: (a, _d, ctx) => ({
          // Shield as equivalent damage reduction proxy for short window
          damageReduction: Math.min(
            0.35,
            (rankValue([40, 55, 70, 85, 100], rankOf(ctx, 'W')) + 0.4 * a.ap) /
              Math.max(400, a.hpMax * 0.35),
          ),
        }),
        damage: () => [],
      },
      {
        slot: 'E',
        name: 'Lucent Singularity',
        range: 1100,
        cooldown: 10,
        skillshot: true,
        damage: (a, _d, ctx) => {
          const base = rankValue([65, 115, 165, 215, 265], rankOf(ctx, 'E'))
          return [{ raw: base + 0.8 * a.ap, type: 'magical', source: 'Lucent Singularity', slot: 'E', skillshot: true }]
        },
      },
      {
        slot: 'R',
        name: 'Final Spark',
        range: 3340,
        cooldown: 60,
        skillshot: true,
        damage: (a, _d, ctx) => {
          const base = rankValue([300, 400, 500], rankOf(ctx, 'R'))
          return [{ raw: base + 1.2 * a.ap, type: 'magical', source: 'Final Spark', slot: 'R', skillshot: true }]
        },
      },
    ],
  }),

  Annie: makeChamp({
    id: 'Annie',
    name: 'Annie',
    title: 'the Dark Child',
    tags: ['Mage'],
    passiveName: 'Pyromania',
    stats: {
      hp: 560, hpperlevel: 100, mp: 418, mpperlevel: 25, movespeed: 335,
      armor: 19, armorperlevel: 4.7, spellblock: 30, spellblockperlevel: 1.3,
      attackrange: 625, hpregen: 5.5, hpregenperlevel: 0.55, mpregen: 8, mpregenperlevel: 0.8,
      crit: 0, critperlevel: 0, attackdamage: 50, attackdamageperlevel: 2.65,
      attackspeedperlevel: 1.36, attackspeed: 0.61, attackspeedratio: 0.625,
    },
    autos: [1, 2],
    abilities: [
      {
        slot: 'Q',
        name: 'Disintegrate',
        range: 625,
        cooldown: 4,
        skillshot: false,
        damage: (a, _d, ctx) => {
          const base = rankValue([80, 120, 160, 200, 240], rankOf(ctx, 'Q'))
          return [{ raw: base + 0.8 * a.ap, type: 'magical', source: 'Disintegrate', slot: 'Q' }]
        },
      },
      {
        slot: 'W',
        name: 'Incinerate',
        range: 600,
        cooldown: 8,
        skillshot: false,
        damage: (a, _d, ctx) => {
          const base = rankValue([70, 120, 170, 220, 270], rankOf(ctx, 'W'))
          return [{ raw: base + 0.85 * a.ap, type: 'magical', source: 'Incinerate', slot: 'W' }]
        },
      },
      {
        slot: 'E',
        name: 'Molten Shield',
        range: 0,
        cooldown: 12,
        skillshot: false,
        utility: (_a, _d, ctx) => ({
          damageReduction: rankValue([0.1, 0.12, 0.14, 0.16, 0.18], rankOf(ctx, 'E')),
        }),
        damage: (a, _d, ctx) => {
          const base = rankValue([25, 35, 45, 55, 65], rankOf(ctx, 'E'))
          return [{ raw: base + 0.4 * a.ap, type: 'magical', source: 'Molten Shield reflect', slot: 'E' }]
        },
      },
      {
        slot: 'R',
        name: 'Summon: Tibbers',
        range: 600,
        cooldown: 120,
        skillshot: false,
        engageCc: true,
        damage: (a, _d, ctx) => {
          const base = rankValue([150, 275, 400], rankOf(ctx, 'R'))
          return [{ raw: base + 0.75 * a.ap, type: 'magical', source: 'Tibbers initial', slot: 'R' }]
        },
      },
    ],
  }),

  Malphite: makeChamp({
    id: 'Malphite',
    name: 'Malphite',
    title: 'Shard of the Monolith',
    tags: ['Tank', 'Fighter'],
    passiveName: 'Granite Shield',
    stats: {
      hp: 665, hpperlevel: 104, mp: 280, mpperlevel: 60, movespeed: 335,
      armor: 37, armorperlevel: 4.95, spellblock: 28, spellblockperlevel: 2.05,
      attackrange: 125, hpregen: 7, hpregenperlevel: 0.55, mpregen: 7.3, mpregenperlevel: 0.55,
      crit: 0, critperlevel: 0, attackdamage: 62, attackdamageperlevel: 4,
      attackspeedperlevel: 3.4, attackspeed: 0.736, attackspeedratio: 0.638,
    },
    autos: [1, 3],
    abilities: [
      {
        slot: 'Q',
        name: 'Seismic Shard',
        range: 625,
        cooldown: 8,
        skillshot: false,
        damage: (a, _d, ctx) => {
          const base = rankValue([70, 120, 170, 220, 270], rankOf(ctx, 'Q'))
          return [{ raw: base + 0.6 * a.ap, type: 'magical', source: 'Seismic Shard', slot: 'Q' }]
        },
      },
      {
        slot: 'W',
        name: 'Thunderclap',
        range: 250,
        cooldown: 10,
        skillshot: false,
        damage: (a, _d, ctx) => {
          const base = rankValue([30, 40, 50, 60, 70], rankOf(ctx, 'W'))
          return [{ raw: base + 0.2 * a.ap + 0.15 * a.armor, type: 'physical', source: 'Thunderclap', slot: 'W' }]
        },
      },
      {
        slot: 'E',
        name: 'Ground Slam',
        range: 400,
        cooldown: 7,
        skillshot: false,
        damage: (a, _d, ctx) => {
          const base = rankValue([70, 110, 150, 190, 230], rankOf(ctx, 'E'))
          return [{ raw: base + 0.6 * a.ap + 0.4 * a.armor, type: 'magical', source: 'Ground Slam', slot: 'E' }]
        },
      },
      {
        slot: 'R',
        name: 'Unstoppable Force',
        range: 1000,
        cooldown: 130,
        skillshot: false,
        engageCc: true,
        damage: (a, _d, ctx) => {
          const base = rankValue([200, 300, 400], rankOf(ctx, 'R'))
          return [{ raw: base + 0.9 * a.ap, type: 'magical', source: 'Unstoppable Force', slot: 'R' }]
        },
      },
    ],
  }),

  /** Reference utility-only kits — zero base damage still changes fights. */
  Nasus: makeChamp({
    id: 'Nasus',
    name: 'Nasus',
    title: 'the Curator of the Sands',
    tags: ['Fighter', 'Tank'],
    passiveName: 'Soul Eater',
    stats: {
      hp: 631, hpperlevel: 104, mp: 326, mpperlevel: 62, movespeed: 350,
      armor: 34, armorperlevel: 4.7, spellblock: 32, spellblockperlevel: 2.05,
      attackrange: 125, hpregen: 9, hpregenperlevel: 0.9, mpregen: 7.45, mpregenperlevel: 0.5,
      crit: 0, critperlevel: 0, attackdamage: 67, attackdamageperlevel: 4,
      attackspeedperlevel: 3.48, attackspeed: 0.638, attackspeedratio: 0.638,
    },
    autos: [2, 4],
    abilities: [
      {
        slot: 'Q',
        name: 'Siphoning Strike',
        range: 200,
        cooldown: 7,
        skillshot: false,
        damage: (a, _d, ctx) => {
          const base = rankValue([30, 50, 70, 90, 110], rankOf(ctx, 'Q'))
          // stacks omitted — base Q only
          return [{ raw: base + a.ad, type: 'physical', source: 'Siphoning Strike', slot: 'Q' }]
        },
      },
      {
        slot: 'W',
        name: 'Wither',
        range: 700,
        cooldown: 15,
        skillshot: false,
        // Meraki: escalating MS + AS slow — peak ~99% AS / high MS at max rank
        utility: (_a, _d, ctx) => {
          const r = rankOf(ctx, 'W')
          return {
            enemySlow: rankValue([0.35, 0.45, 0.55, 0.65, 0.75], r),
            enemyAsSlow: rankValue([0.475, 0.6, 0.725, 0.85, 0.975], r),
          }
        },
        damage: () => [],
      },
      {
        slot: 'E',
        name: 'Spirit Fire',
        range: 650,
        cooldown: 12,
        skillshot: false,
        utility: (_a, _d, ctx) => ({
          armorShred: rankValue([0.15, 0.2, 0.25, 0.3, 0.35], rankOf(ctx, 'E')),
        }),
        damage: (a, _d, ctx) => {
          const initial = rankValue([55, 95, 135, 175, 215], rankOf(ctx, 'E')) + 0.6 * a.ap
          return [{ raw: initial, type: 'magical', source: 'Spirit Fire', slot: 'E' }]
        },
      },
      {
        slot: 'R',
        name: 'Fury of the Sands',
        range: 0,
        cooldown: 120,
        skillshot: false,
        damage: (a, d, ctx) => {
          const per = rankValue([0.03, 0.04, 0.05], rankOf(ctx, 'R')) + 0.01 * (a.ap / 100)
          return [{ raw: per * d.hpMax * 3, type: 'magical', source: 'Fury ticks (approx)', slot: 'R' }]
        },
      },
    ],
  }),

  Zilean: makeChamp({
    id: 'Zilean',
    name: 'Zilean',
    title: 'the Chronokeeper',
    tags: ['Support', 'Mage'],
    passiveName: 'Time in a Bottle',
    stats: {
      hp: 574, hpperlevel: 96, mp: 452, mpperlevel: 50, movespeed: 335,
      armor: 24, armorperlevel: 5, spellblock: 30, spellblockperlevel: 1.3,
      attackrange: 550, hpregen: 5.5, hpregenperlevel: 0.5, mpregen: 11.35, mpregenperlevel: 0.8,
      crit: 0, critperlevel: 0, attackdamage: 52, attackdamageperlevel: 3,
      attackspeedperlevel: 2.13, attackspeed: 0.625, attackspeedratio: 0.625,
    },
    autos: [1, 2],
    abilities: [
      {
        slot: 'Q',
        name: 'Time Bomb',
        range: 900,
        cooldown: 10,
        skillshot: true,
        damage: (a, _d, ctx) => {
          const base = rankValue([75, 115, 165, 230, 300], rankOf(ctx, 'Q'))
          return [{ raw: base + 0.9 * a.ap, type: 'magical', source: 'Time Bomb', slot: 'Q', skillshot: true }]
        },
      },
      {
        slot: 'W',
        name: 'Rewind',
        range: 0,
        cooldown: 14,
        skillshot: false,
        damage: () => [],
      },
      {
        slot: 'E',
        name: 'Time Warp',
        range: 550,
        cooldown: 15,
        skillshot: false,
        // Targeted: enemy slow OR ally MS. In enemy-facing trades we model the slow.
        utility: (_a, _d, ctx) => {
          const r = rankOf(ctx, 'E')
          const amount = rankValue([0.4, 0.55, 0.7, 0.85, 0.99], r)
          return { enemySlow: amount }
        },
        damage: () => [],
      },
      {
        slot: 'R',
        name: 'Chronoshift',
        range: 900,
        cooldown: 120,
        skillshot: false,
        // Revive is out of v1 scope — treat as large effective DR for the window
        utility: (_a, _d, ctx) => ({
          damageReduction: rankValue([0.35, 0.4, 0.45], rankOf(ctx, 'R')),
        }),
        damage: () => [],
      },
    ],
  }),
}

/**
 * Gnar's generated Meraki packets contain both mutually-exclusive forms.
 * Keep the generated catalog as the source, but gate packets at the combat
 * boundary: explicit form wins; otherwise R-ranked means Mega, else Mini.
 */
function gnarForm(ctx: AbilityContext): 'mini' | 'mega' {
  return ctx.form ?? (rankOf(ctx, 'R') > 0 ? 'mega' : 'mini')
}

function withGnarForm(champion: ChampionDefinition): ChampionDefinition {
  if (champion.id !== 'Gnar') return champion
  return {
    ...champion,
    abilities: champion.abilities.map((ability) => {
      if (!['Q', 'W', 'E', 'R'].includes(ability.slot)) return ability
      const baseDamage = ability.damage
      return {
        ...ability,
        available:
          ability.slot === 'R'
            ? (ctx: AbilityContext) => gnarForm(ctx) === 'mega'
            : ability.available,
        damage: (a, d, ctx) => {
          const form = gnarForm(ctx)
          if (ability.slot === 'R' && form !== 'mega') return []
          const packets = baseDamage(a, d, ctx)
          if (ability.slot === 'Q') {
            return packets.filter((p) =>
              form === 'mega'
                ? /Boulder Toss/i.test(p.source)
                : /Boomerang Throw/i.test(p.source),
            )
          }
          if (ability.slot === 'W') {
            return packets.filter((p) =>
              form === 'mega' ? /Wallop/i.test(p.source) : /Hyper/i.test(p.source),
            )
          }
          if (ability.slot === 'E') {
            return packets.filter((p) =>
              form === 'mega' ? /Crunch/i.test(p.source) : /Hop/i.test(p.source),
            )
          }
          return packets
        },
      }
    }),
  }
}

const GAME_CHAMPIONS_WITH_FORMS: Record<string, ChampionDefinition> = {
  ...GAME_CHAMPIONS,
  ...(GAME_CHAMPIONS.Gnar ? { Gnar: withGnarForm(GAME_CHAMPIONS.Gnar) } : {}),
}

export const CHAMPIONS: Record<string, ChampionDefinition> = {
  ...GAME_CHAMPIONS_WITH_FORMS,
  // Curated kits (damage, utility, passives) win over sparse wiki stubs.
  ...CORE_CHAMPIONS,
}

/**
 * Stable IDs of hand-authored CORE kits.
 * CORE means modeling attention only — not trusted, validated, or calibrated.
 * Sorted for deterministic consumers; merge precedence remains GAME then CORE.
 */
export const CORE_CHAMPION_IDS: readonly string[] = Object.freeze(
  Object.keys(CORE_CHAMPIONS).sort((a, b) => (a < b ? -1 : a > b ? 1 : 0)),
)

const CORE_CHAMPION_ID_SET: ReadonlySet<string> = new Set(CORE_CHAMPION_IDS)

/** True when the champion has a hand-authored CORE kit (attention ≠ trust). */
export function isCoreChampion(id: string): boolean {
  return CORE_CHAMPION_ID_SET.has(id)
}

export const CHAMPION_LIST = Object.values(CHAMPIONS)

export function championIconUrl(id: string): string {
  return `https://ddragon.leagueoflegends.com/cdn/${DDRAGON}/img/champion/${id}.png`
}

export { DDRAGON }
