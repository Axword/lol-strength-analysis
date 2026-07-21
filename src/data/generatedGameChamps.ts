import type { AbilityDefinition, ChampionDefinition } from '../engine/types'
import { bonusAd, rankOf } from '../engine/types'

function rankValue(values: number[], rank: number): number {
  if (!values.length) return 0
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

/** Ability numbers from Meraki Analytics (League wiki data mirror). */
export const GAME_CHAMPIONS: Record<string, ChampionDefinition> = {
  LeeSin: makeChamp({
    id: 'LeeSin',
    name: "Lee Sin",
    title: "the Blind Monk",
    tags: ["ASSASSIN", "DIVER", "FIGHTER"],
    passiveName: "Flurry",
    stats: {"hp": 645, "hpperlevel": 108, "mp": 200, "mpperlevel": 0, "movespeed": 345, "armor": 36, "armorperlevel": 4.9, "spellblock": 32, "spellblockperlevel": 2.05, "attackrange": 125, "hpregen": 7.5, "hpregenperlevel": 0.7, "mpregen": 50, "mpregenperlevel": 0, "crit": 0, "critperlevel": 0, "attackdamage": 66, "attackdamageperlevel": 3.7, "attackspeedperlevel": 3, "attackspeed": 0.651},
    autos: [1, 3],
    abilities: [
      {
        slot: 'Q',
        name: "Sonic Wave",
        range: 1200,
        cooldown: 10,
        skillshot: true,
        engageCc: true,
        damage: (a, d, ctx) => {
          if (rankOf(ctx, 'Q') <= 0) return []
          const base = rankValue([55, 80, 105, 130, 155], Math.max(1, rankOf(ctx, 'Q'))) + 1.15 * bonusAd(a)
          const missingPct = d.hpMax > 0 ? Math.max(0, 1 - d.hp / d.hpMax) : 0
          // Resonating Strike: same base, increased by 0–100% based on missing HP (wiki)
          const resonate = base * (1 + missingPct)
          return [
            { raw: base, type: 'physical' as const, source: 'Sonic Wave', slot: 'Q' as const, skillshot: true },
            { raw: resonate, type: 'physical' as const, source: 'Resonating Strike', slot: 'Q' as const, skillshot: true },
          ]
        },
      },
      {
        slot: 'W',
        name: "Safeguard",
        range: 700,
        cooldown: 12,
        skillshot: false,
        engageCc: false,
        utility: (a, _d, ctx) => ({
          damageReduction: Math.min(
            0.3,
            (rankValue([70, 115, 160, 205, 250], Math.max(1, rankOf(ctx, 'W'))) + 0.8 * a.ap) /
              Math.max(400, a.hpMax * 0.3),
          ),
        }),
        damage: () => [],
      },
      {
        slot: 'E',
        name: "Tempest",
        range: 450,
        cooldown: 8,
        skillshot: false,
        engageCc: false,
        damage: (a, _d, ctx) => {
          if (rankOf(ctx, 'E') <= 0) return []
          return [{ raw: (rankValue([35, 60, 85, 110, 135], Math.max(1, rankOf(ctx,'E')))) + (1.0*a.ad), type: 'magical' as const, source: "Tempest", slot: 'E' as const }]
        },
      },
      {
        slot: 'R',
        name: "Dragon's Rage",
        range: 375,
        cooldown: 110,
        skillshot: false,
        engageCc: true,
        damage: (a, _d, ctx) => {
          if (rankOf(ctx, 'R') <= 0) return []
          return [{ raw: (rankValue([175, 400, 625], Math.max(1, rankOf(ctx,'R')))) + (2.0*bonusAd(a)), type: 'physical' as const, source: "Dragon's Rage", slot: 'R' as const }]
        },
      }
    ],
  }),
  Naafiri: makeChamp({
    id: 'Naafiri',
    name: "Naafiri",
    title: "the Hound of a Hundred Bites",
    tags: ["ASSASSIN", "FIGHTER"],
    passiveName: "We Are More",
    stats: {"hp": 610, "hpperlevel": 105, "mp": 400, "mpperlevel": 55, "movespeed": 340, "armor": 28, "armorperlevel": 4.2, "spellblock": 32, "spellblockperlevel": 2.05, "attackrange": 125, "hpregen": 7.5, "hpregenperlevel": 0.7, "mpregen": 7.5, "mpregenperlevel": 1, "crit": 0, "critperlevel": 0, "attackdamage": 55, "attackdamageperlevel": 2, "attackspeedperlevel": 2.1, "attackspeed": 0.663},
    autos: [1, 3],
    abilities: [
      {
        slot: 'Q',
        name: "Darkin Daggers",
        range: 900,
        cooldown: 9,
        skillshot: true,
        engageCc: false,
        damage: (a, _d, ctx) => {
          if (rankOf(ctx, 'Q') <= 0) return []
          const r = Math.max(1, rankOf(ctx, 'Q'))
          const initial = rankValue([35, 40, 45, 50, 55], r) + 0.2 * bonusAd(a)
          const bonus = rankValue([30, 45, 60, 75, 90], r) + 0.4 * bonusAd(a)
          return [
            { raw: initial, type: 'physical' as const, source: 'Darkin Daggers', slot: 'Q' as const, skillshot: true },
            { raw: bonus, type: 'physical' as const, source: 'Darkin Daggers (pack)', slot: 'Q' as const, skillshot: true },
          ]
        },
      },
      {
        slot: 'W',
        name: "The Call of the Pack",
        range: 400,
        cooldown: 26,
        skillshot: false,
        engageCc: false,
        damage: () => [],
      },
      {
        slot: 'E',
        name: "Eviscerate",
        range: 400,
        cooldown: 11,
        skillshot: true,
        engageCc: true,
        damage: (a, _d, ctx) => {
          if (rankOf(ctx, 'E') <= 0) return []
          return [{ raw: (rankValue([15, 25, 35, 45, 55], Math.max(1, rankOf(ctx,'E')))) + (0.4*bonusAd(a)), type: 'physical' as const, source: "Eviscerate", slot: 'E' as const, skillshot: true }]
        },
      },
      {
        slot: 'R',
        name: "Hounds' Pursuit",
        range: 900,
        cooldown: 110,
        skillshot: false,
        engageCc: true,
        damage: (a, _d, ctx) => {
          if (rankOf(ctx, 'R') <= 0) return []
          return [{ raw: (rankValue([150, 250, 350], Math.max(1, rankOf(ctx,'R')))) + (1.2*bonusAd(a)), type: 'physical' as const, source: "Hounds' Pursuit", slot: 'R' as const }]
        },
      }
    ],
  }),
  Ambessa: makeChamp({
    id: 'Ambessa',
    name: "Ambessa",
    title: "Matriarch of War",
    tags: ["ASSASSIN", "DIVER", "FIGHTER"],
    passiveName: "Drakehound's Step",
    stats: {"hp": 630, "hpperlevel": 110, "mp": 200, "mpperlevel": 0, "movespeed": 335, "armor": 35, "armorperlevel": 4.9, "spellblock": 32, "spellblockperlevel": 2.05, "attackrange": 125, "hpregen": 8.5, "hpregenperlevel": 0.75, "mpregen": 50, "mpregenperlevel": 0, "crit": 0, "critperlevel": 0, "attackdamage": 63, "attackdamageperlevel": 3, "attackspeedperlevel": 2.5, "attackspeed": 0.625},
    autos: [1, 3],
    abilities: [
      {
        slot: 'Q',
        name: "Cunning Sweep",
        range: 375,
        cooldown: 14,
        skillshot: false,
        engageCc: false,
        damage: (a, _d, ctx) => {
          if (rankOf(ctx, 'Q') <= 0) return []
          return [{ raw: (rankValue([20, 30, 40, 50, 60], Math.max(1, rankOf(ctx,'Q')))) + (0.3*bonusAd(a) + 0.01*bonusAd(a)), type: 'physical' as const, source: "Cunning Sweep", slot: 'Q' as const }, { raw: (rankValue([25, 37.5, 50, 62.5, 75], Math.max(1, rankOf(ctx,'Q')))) + (0.45*bonusAd(a) + 0.01*bonusAd(a)), type: 'physical' as const, source: "Sundering Slam", slot: 'Q' as const }]
        },
      },
      {
        slot: 'W',
        name: "Repudiation",
        range: 650,
        cooldown: 18,
        skillshot: false,
        engageCc: false,
        damage: (a, _d, ctx) => {
          if (rankOf(ctx, 'W') <= 0) return []
          return [{ raw: (rankValue([50, 75, 100, 125, 150], Math.max(1, rankOf(ctx,'W')))) + (0.5*bonusAd(a)), type: 'physical' as const, source: "Repudiation", slot: 'W' as const }]
        },
      },
      {
        slot: 'E',
        name: "Lacerate",
        range: 325,
        cooldown: 13,
        skillshot: true,
        engageCc: true,
        damage: (a, _d, ctx) => {
          if (rankOf(ctx, 'E') <= 0) return []
          return [{ raw: (rankValue([40, 60, 80, 100, 120], Math.max(1, rankOf(ctx,'E')))) + (0.4*bonusAd(a)), type: 'physical' as const, source: "Lacerate", slot: 'E' as const, skillshot: true }]
        },
      },
      {
        slot: 'R',
        name: "Public Execution",
        range: 475,
        cooldown: 130,
        skillshot: false,
        engageCc: true,
        damage: (a, _d, ctx) => {
          if (rankOf(ctx, 'R') <= 0) return []
          return [{ raw: (rankValue([150, 250, 350], Math.max(1, rankOf(ctx,'R')))) + (0.8*bonusAd(a)), type: 'physical' as const, source: "Public Execution", slot: 'R' as const }]
        },
      }
    ],
  }),
  Akali: makeChamp({
    id: 'Akali',
    name: "Akali",
    title: "the Rogue Assassin",
    tags: ["ASSASSIN"],
    passiveName: "Assassin's Mark",
    stats: {"hp": 600, "hpperlevel": 119, "mp": 200, "mpperlevel": 0, "movespeed": 345, "armor": 23, "armorperlevel": 4.7, "spellblock": 37, "spellblockperlevel": 2.05, "attackrange": 125, "hpregen": 9, "hpregenperlevel": 0.9, "mpregen": 50, "mpregenperlevel": 0, "crit": 0, "critperlevel": 0, "attackdamage": 62, "attackdamageperlevel": 3.3, "attackspeedperlevel": 3.2, "attackspeed": 0.625},
    autos: [1, 3],
    abilities: [
      {
        slot: 'Q',
        name: "Five Point Strike",
        range: 550,
        cooldown: 1.5,
        skillshot: true,
        engageCc: false,
        damage: (a, _d, ctx) => {
          if (rankOf(ctx, 'Q') <= 0) return []
          return [{ raw: (rankValue([45, 70, 95, 120, 145], Math.max(1, rankOf(ctx,'Q')))) + (0.65*a.ad + 0.6*a.ap), type: 'magical' as const, source: "Five Point Strike", slot: 'Q' as const, skillshot: true }]
        },
      },
      {
        slot: 'W',
        name: "Twilight Shroud",
        range: 300,
        cooldown: 20,
        skillshot: false,
        engageCc: false,
        damage: () => [],
      },
      {
        slot: 'E',
        name: "Shuriken Flip",
        range: 650,
        cooldown: 16,
        skillshot: true,
        engageCc: true,
        damage: (a, _d, ctx) => {
          if (rankOf(ctx, 'E') <= 0) return []
          return [{ raw: (rankValue([21, 42, 63, 84, 105], Math.max(1, rankOf(ctx,'E')))) + (0.3*a.ad + 0.33*a.ap), type: 'magical' as const, source: "Shuriken Flip", slot: 'E' as const, skillshot: true }]
        },
      },
      {
        slot: 'R',
        name: "Perfect Execution",
        range: 675,
        cooldown: 120,
        skillshot: true,
        engageCc: true,
        damage: (a, _d, ctx) => {
          if (rankOf(ctx, 'R') <= 0) return []
          return [{ raw: (rankValue([110, 220, 330], Math.max(1, rankOf(ctx,'R')))) + (0.5*bonusAd(a) + 0.3*a.ap), type: 'magical' as const, source: "Perfect Execution", slot: 'R' as const, skillshot: true }]
        },
      }
    ],
  }),
  Camille: makeChamp({
    id: 'Camille',
    name: "Camille",
    title: "the Steel Shadow",
    tags: ["ASSASSIN", "DIVER", "FIGHTER"],
    passiveName: "Adaptive Defenses",
    stats: {"hp": 650, "hpperlevel": 99, "mp": 339, "mpperlevel": 52, "movespeed": 340, "armor": 35, "armorperlevel": 5, "spellblock": 32, "spellblockperlevel": 2.05, "attackrange": 125, "hpregen": 8.5, "hpregenperlevel": 0.8, "mpregen": 8.15, "mpregenperlevel": 0.75, "crit": 0, "critperlevel": 0, "attackdamage": 68, "attackdamageperlevel": 3.8, "attackspeedperlevel": 2.5, "attackspeed": 0.644},
    autos: [1, 3],
    abilities: [
      {
        slot: 'Q',
        name: "Precision Protocol",
        range: 175,
        cooldown: 9,
        skillshot: false,
        engageCc: false,
        damage: () => [],
      },
      {
        slot: 'W',
        name: "Tactical Sweep",
        range: 650,
        cooldown: 17,
        skillshot: true,
        engageCc: false,
        damage: (a, _d, ctx) => {
          if (rankOf(ctx, 'W') <= 0) return []
          return [{ raw: (rankValue([50, 75, 100, 125, 150], Math.max(1, rankOf(ctx,'W')))) + (0.6*bonusAd(a)), type: 'physical' as const, source: "Tactical Sweep", slot: 'W' as const, skillshot: true }]
        },
      },
      {
        slot: 'E',
        name: "Hookshot",
        range: 800,
        cooldown: 16,
        skillshot: true,
        engageCc: true,
        damage: (a, _d, ctx) => {
          if (rankOf(ctx, 'E') <= 0) return []
          return [{ raw: (rankValue([60, 90, 120, 150, 180], Math.max(1, rankOf(ctx,'E')))) + (0.75*bonusAd(a)), type: 'physical' as const, source: "Wall Dive", slot: 'E' as const, skillshot: true }]
        },
      },
      {
        slot: 'R',
        name: "The Hextech Ultimatum",
        range: 475,
        cooldown: 140,
        skillshot: false,
        engageCc: true,
        damage: () => [],
      }
    ],
  }),
  Jhin: makeChamp({
    id: 'Jhin',
    name: "Jhin",
    title: "the Virtuoso",
    tags: ["CATCHER", "MAGE", "MARKSMAN"],
    passiveName: "Whisper",
    stats: {"hp": 655, "hpperlevel": 107, "mp": 300, "mpperlevel": 50, "movespeed": 330, "armor": 24, "armorperlevel": 4.7, "spellblock": 30, "spellblockperlevel": 1.3, "attackrange": 550, "hpregen": 3.75, "hpregenperlevel": 0.55, "mpregen": 6, "mpregenperlevel": 0.8, "crit": 0, "critperlevel": 0, "attackdamage": 59, "attackdamageperlevel": 4.4, "attackspeedperlevel": 3, "attackspeed": 0.625},
    autos: [1, 3],
    abilities: [
      {
        slot: 'Q',
        name: "Dancing Grenade",
        range: 550,
        cooldown: 7,
        skillshot: true,
        engageCc: false,
        damage: (a, _d, ctx) => {
          if (rankOf(ctx, 'Q') <= 0) return []
          return [{ raw: (rankValue([44, 69, 94, 119, 144], Math.max(1, rankOf(ctx,'Q')))) + (0.44*a.ad + 0.6*a.ap), type: 'physical' as const, source: "Dancing Grenade", slot: 'Q' as const, skillshot: true }]
        },
      },
      {
        slot: 'W',
        name: "Deadly Flourish",
        range: 3000,
        cooldown: 12,
        skillshot: true,
        engageCc: false,
        damage: (a, _d, ctx) => {
          if (rankOf(ctx, 'W') <= 0) return []
          return [{ raw: (rankValue([60, 95, 130, 165, 200], Math.max(1, rankOf(ctx,'W')))) + (0.5*a.ad), type: 'physical' as const, source: "Deadly Flourish", slot: 'W' as const, skillshot: true }]
        },
      },
      {
        slot: 'E',
        name: "Captive Audience",
        range: 750,
        cooldown: 2,
        skillshot: false,
        engageCc: false,
        damage: (a, _d, ctx) => {
          if (rankOf(ctx, 'E') <= 0) return []
          return [{ raw: (rankValue([20, 80, 140, 200, 260], Math.max(1, rankOf(ctx,'E')))) + (1.2*a.ad + 1.0*a.ap), type: 'magical' as const, source: "Captive Audience", slot: 'E' as const }]
        },
      },
      {
        slot: 'R',
        name: "Curtain Call",
        range: 3500,
        cooldown: 120,
        skillshot: true,
        engageCc: false,
        damage: (a, _d, ctx) => {
          if (rankOf(ctx, 'R') <= 0) return []
          return [{ raw: (rankValue([64, 128, 192], Math.max(1, rankOf(ctx,'R')))) + (0.25*a.ad), type: 'physical' as const, source: "Curtain Call", slot: 'R' as const, skillshot: true }]
        },
      }
    ],
  }),
  Gnar: makeChamp({
    id: 'Gnar',
    name: "Gnar",
    title: "the Missing Link",
    tags: ["FIGHTER", "SPECIALIST", "TANK"],
    passiveName: "Rage Gene",
    stats: {"hp": 540, "hpperlevel": 79, "mp": 100, "mpperlevel": 0, "movespeed": 335, "armor": 32, "armorperlevel": 3.7, "spellblock": 30, "spellblockperlevel": 1.3, "attackrange": 175, "hpregen": 4.5, "hpregenperlevel": 1.25, "mpregen": 0, "mpregenperlevel": 0, "crit": 0, "critperlevel": 0, "attackdamage": 60, "attackdamageperlevel": 3.2, "attackspeedperlevel": 6, "attackspeed": 0.625},
    autos: [1, 3],
    abilities: [
      {
        slot: 'Q',
        name: "Boomerang Throw",
        range: 1100,
        cooldown: 20,
        skillshot: true,
        engageCc: false,
        damage: (a, _d, ctx) => {
          if (rankOf(ctx, 'Q') <= 0) return []
          return [{ raw: (rankValue([5, 45, 85, 125, 165], Math.max(1, rankOf(ctx,'Q')))) + (1.25*a.ad), type: 'physical' as const, source: "Boomerang Throw", slot: 'Q' as const, skillshot: true }, { raw: (rankValue([45, 90, 135, 180, 225], Math.max(1, rankOf(ctx,'Q')))) + (1.4*a.ad), type: 'physical' as const, source: "Boulder Toss", slot: 'Q' as const, skillshot: true }]
        },
      },
      {
        slot: 'W',
        name: "Hyper",
        range: 425,
        cooldown: 8,
        skillshot: false,
        engageCc: false,
        damage: (a, d, ctx) => {
          if (rankOf(ctx, 'W') <= 0) return []
          return [{ raw: (rankValue([0, 10, 20, 30, 40], Math.max(1, rankOf(ctx,'W')))) + (0.06*d.hp + 1.0*a.ap), type: 'magical' as const, source: "Hyper", slot: 'W' as const }, { raw: (rankValue([45, 75, 105, 135, 165], Math.max(1, rankOf(ctx,'W')))) + (1.0*a.ad), type: 'physical' as const, source: "Wallop", slot: 'W' as const }]
        },
      },
      {
        slot: 'E',
        name: "Hop",
        range: 475,
        cooldown: 22,
        skillshot: true,
        engageCc: true,
        damage: (_a, d, ctx) => {
          if (rankOf(ctx, 'E') <= 0) return []
          return [{ raw: (rankValue([50, 85, 120, 155, 190], Math.max(1, rankOf(ctx,'E')))) + (0.06*d.hp), type: 'physical' as const, source: "Hop", slot: 'E' as const, skillshot: true }, { raw: (rankValue([80, 115, 150, 185, 220], Math.max(1, rankOf(ctx,'E')))) + (0.06*d.hp), type: 'physical' as const, source: "Crunch", slot: 'E' as const, skillshot: true }]
        },
      },
      {
        slot: 'R',
        name: "GNAR!",
        range: 590,
        cooldown: 90,
        skillshot: true,
        engageCc: true,
        damage: (a, _d, ctx) => {
          if (rankOf(ctx, 'R') <= 0) return []
          return [{ raw: (rankValue([200, 300, 400], Math.max(1, rankOf(ctx,'R')))) + (0.5*bonusAd(a) + 1.0*a.ap), type: 'physical' as const, source: "GNAR!", slot: 'R' as const, skillshot: true }]
        },
      }
    ],
  }),
  Galio: makeChamp({
    id: 'Galio',
    name: "Galio",
    title: "the Colossus",
    tags: ["MAGE", "TANK", "WARDEN"],
    passiveName: "Colossal Smash",
    stats: {"hp": 600, "hpperlevel": 126, "mp": 410, "mpperlevel": 40, "movespeed": 340, "armor": 24, "armorperlevel": 4.7, "spellblock": 32, "spellblockperlevel": 2.05, "attackrange": 150, "hpregen": 8, "hpregenperlevel": 0.8, "mpregen": 9.5, "mpregenperlevel": 0.7, "crit": 0, "critperlevel": 0, "attackdamage": 59, "attackdamageperlevel": 3.5, "attackspeedperlevel": 1.5, "attackspeed": 0.625},
    autos: [1, 3],
    abilities: [
      {
        slot: 'Q',
        name: "Winds of War",
        range: 825,
        cooldown: 11,
        skillshot: true,
        engageCc: false,
        damage: (a, _d, ctx) => {
          if (rankOf(ctx, 'Q') <= 0) return []
          return [{ raw: (rankValue([70, 105, 140, 175, 210], Math.max(1, rankOf(ctx,'Q')))) + (0.7*a.ap), type: 'magical' as const, source: "Winds of War", slot: 'Q' as const, skillshot: true }]
        },
      },
      {
        slot: 'W',
        name: "Shield of Durand",
        range: 275,
        cooldown: 18,
        skillshot: false,
        engageCc: false,
        damage: (a, d, ctx) => {
          if (rankOf(ctx, 'W') <= 0) return []
          return [{ raw: (rankValue([20, 30, 40, 50, 60], Math.max(1, rankOf(ctx,'W')))) + (0.04*a.ap + 0.01*d.hp + 0.3*a.ap), type: 'magical' as const, source: "Shield of Durand", slot: 'W' as const }]
        },
      },
      {
        slot: 'E',
        name: "Justice Punch",
        range: 650,
        cooldown: 11,
        skillshot: true,
        engageCc: true,
        damage: (a, _d, ctx) => {
          if (rankOf(ctx, 'E') <= 0) return []
          return [{ raw: (rankValue([90, 130, 170, 210, 250], Math.max(1, rankOf(ctx,'E')))) + (0.9*a.ap), type: 'magical' as const, source: "Justice Punch", slot: 'E' as const, skillshot: true }]
        },
      },
      {
        slot: 'R',
        name: "Hero's Entrance",
        range: 4000,
        cooldown: 180,
        skillshot: true,
        engageCc: true,
        damage: (a, _d, ctx) => {
          if (rankOf(ctx, 'R') <= 0) return []
          return [{ raw: (rankValue([150, 250, 350], Math.max(1, rankOf(ctx,'R')))) + (0.7*a.ap), type: 'magical' as const, source: "Hero's Entrance", slot: 'R' as const, skillshot: true }]
        },
      }
    ],
  }),
  Syndra: makeChamp({
    id: 'Syndra',
    name: "Syndra",
    title: "the Dark Sovereign",
    tags: ["BURST", "MAGE"],
    passiveName: "Transcendent",
    stats: {"hp": 563, "hpperlevel": 104, "mp": 480, "mpperlevel": 40, "movespeed": 330, "armor": 25, "armorperlevel": 4.6, "spellblock": 30, "spellblockperlevel": 1.3, "attackrange": 550, "hpregen": 6.5, "hpregenperlevel": 0.6, "mpregen": 8, "mpregenperlevel": 0.8, "crit": 0, "critperlevel": 0, "attackdamage": 54, "attackdamageperlevel": 2.9, "attackspeedperlevel": 2, "attackspeed": 0.658},
    autos: [1, 3],
    abilities: [
      {
        slot: 'Q',
        name: "Dark Sphere",
        range: 800,
        cooldown: 7,
        skillshot: true,
        engageCc: false,
        damage: (a, _d, ctx) => {
          if (rankOf(ctx, 'Q') <= 0) return []
          return [{ raw: (rankValue([75, 110, 145, 180, 215], Math.max(1, rankOf(ctx,'Q')))) + (0.6*a.ap), type: 'magical' as const, source: "Dark Sphere", slot: 'Q' as const, skillshot: true }]
        },
      },
      {
        slot: 'W',
        name: "Force of Will",
        range: 950,
        cooldown: 12,
        skillshot: true,
        engageCc: false,
        damage: (a, _d, ctx) => {
          if (rankOf(ctx, 'W') <= 0) return []
          return [{ raw: (rankValue([70, 105, 140, 175, 210], Math.max(1, rankOf(ctx,'W')))) + (0.65*a.ap), type: 'magical' as const, source: "Force of Will", slot: 'W' as const, skillshot: true }]
        },
      },
      {
        slot: 'E',
        name: "Scatter the Weak",
        range: 650,
        cooldown: 17,
        skillshot: true,
        engageCc: false,
        damage: (a, _d, ctx) => {
          if (rankOf(ctx, 'E') <= 0) return []
          return [{ raw: (rankValue([60, 95, 130, 165, 200], Math.max(1, rankOf(ctx,'E')))) + (0.6*a.ap), type: 'magical' as const, source: "Scatter the Weak", slot: 'E' as const, skillshot: true }]
        },
      },
      {
        slot: 'R',
        name: "Unleashed Power",
        range: 675,
        cooldown: 120,
        skillshot: true,
        engageCc: false,
        damage: (a, _d, ctx) => {
          if (rankOf(ctx, 'R') <= 0) return []
          return [{ raw: (rankValue([90, 130, 170], Math.max(1, rankOf(ctx,'R')))) + (0.2*a.ap), type: 'magical' as const, source: "Unleashed Power", slot: 'R' as const, skillshot: true }]
        },
      }
    ],
  }),
  Leona: makeChamp({
    id: 'Leona',
    name: "Leona",
    title: "the Radiant Dawn",
    tags: ["SUPPORT", "TANK", "VANGUARD"],
    passiveName: "Sunlight",
    stats: {"hp": 646, "hpperlevel": 101, "mp": 302, "mpperlevel": 40, "movespeed": 335, "armor": 43, "armorperlevel": 4.8, "spellblock": 32, "spellblockperlevel": 2.05, "attackrange": 125, "hpregen": 8.5, "hpregenperlevel": 0.85, "mpregen": 6, "mpregenperlevel": 0.8, "crit": 0, "critperlevel": 0, "attackdamage": 60, "attackdamageperlevel": 3, "attackspeedperlevel": 2.9, "attackspeed": 0.625},
    autos: [1, 3],
    abilities: [
      {
        slot: 'Q',
        name: "Shield of Daybreak",
        range: 175,
        cooldown: 5,
        skillshot: false,
        engageCc: false,
        damage: (a, _d, ctx) => {
          if (rankOf(ctx, 'Q') <= 0) return []
          return [{ raw: (rankValue([10, 35, 60, 85, 110], Math.max(1, rankOf(ctx,'Q')))) + (0.3*a.ap), type: 'magical' as const, source: "Shield of Daybreak", slot: 'Q' as const }]
        },
      },
      {
        slot: 'W',
        name: "Eclipse",
        range: 450,
        cooldown: 14,
        skillshot: false,
        engageCc: false,
        damage: (_a, _d, ctx) => {
          if (rankOf(ctx, 'W') <= 0) return []
          return [{ raw: rankValue([8, 12, 16, 20, 24], Math.max(1, rankOf(ctx,'W'))), type: 'physical' as const, source: "Eclipse", slot: 'W' as const }]
        },
      },
      {
        slot: 'E',
        name: "Zenith Blade",
        range: 900,
        cooldown: 12,
        skillshot: true,
        engageCc: true,
        damage: (a, _d, ctx) => {
          if (rankOf(ctx, 'E') <= 0) return []
          return [{ raw: (rankValue([50, 90, 130, 170, 210], Math.max(1, rankOf(ctx,'E')))) + (0.4*a.ap), type: 'magical' as const, source: "Zenith Blade", slot: 'E' as const, skillshot: true }]
        },
      },
      {
        slot: 'R',
        name: "Solar Flare",
        range: 1200,
        cooldown: 90,
        skillshot: true,
        engageCc: true,
        damage: (a, _d, ctx) => {
          if (rankOf(ctx, 'R') <= 0) return []
          return [{ raw: (rankValue([150, 225, 300], Math.max(1, rankOf(ctx,'R')))) + (0.8*a.ap), type: 'magical' as const, source: "Solar Flare", slot: 'R' as const, skillshot: true }]
        },
      }
    ],
  }),
  Gragas: makeChamp({
    id: 'Gragas',
    name: "Gragas",
    title: "the Rabble Rouser",
    tags: ["FIGHTER", "MAGE", "VANGUARD"],
    passiveName: "Happy Hour",
    stats: {"hp": 640, "hpperlevel": 115, "mp": 400, "mpperlevel": 47, "movespeed": 330, "armor": 38, "armorperlevel": 5, "spellblock": 32, "spellblockperlevel": 2.05, "attackrange": 125, "hpregen": 5.5, "hpregenperlevel": 0.5, "mpregen": 6, "mpregenperlevel": 0.8, "crit": 0, "critperlevel": 0, "attackdamage": 64, "attackdamageperlevel": 3.5, "attackspeedperlevel": 2.05, "attackspeed": 0.675},
    autos: [1, 3],
    abilities: [
      {
        slot: 'Q',
        name: "Barrel Roll",
        range: 850,
        cooldown: 10,
        skillshot: true,
        engageCc: false,
        damage: (a, _d, ctx) => {
          if (rankOf(ctx, 'Q') <= 0) return []
          return [{ raw: (rankValue([80, 120, 160, 200, 240], Math.max(1, rankOf(ctx,'Q')))) + (0.8*a.ap), type: 'magical' as const, source: "Barrel Roll", slot: 'Q' as const, skillshot: true }]
        },
      },
      {
        slot: 'W',
        name: "Drunken Rage",
        range: 250,
        cooldown: 5,
        skillshot: false,
        engageCc: false,
        damage: (a, d, ctx) => {
          if (rankOf(ctx, 'W') <= 0) return []
          return [{ raw: (rankValue([20, 50, 80, 110, 140], Math.max(1, rankOf(ctx,'W')))) + (0.7*a.ap + 0.07*d.hpMax), type: 'magical' as const, source: "Drunken Rage", slot: 'W' as const }]
        },
      },
      {
        slot: 'E',
        name: "Body Slam",
        range: 600,
        cooldown: 14,
        skillshot: true,
        engageCc: true,
        damage: (a, _d, ctx) => {
          if (rankOf(ctx, 'E') <= 0) return []
          return [{ raw: (rankValue([80, 125, 170, 215, 260], Math.max(1, rankOf(ctx,'E')))) + (0.6*a.ap), type: 'magical' as const, source: "Body Slam", slot: 'E' as const, skillshot: true }]
        },
      },
      {
        slot: 'R',
        name: "Explosive Cask",
        range: 1000,
        cooldown: 100,
        skillshot: true,
        engageCc: false,
        damage: (a, _d, ctx) => {
          if (rankOf(ctx, 'R') <= 0) return []
          return [{ raw: (rankValue([200, 300, 400], Math.max(1, rankOf(ctx,'R')))) + (0.8*a.ap), type: 'magical' as const, source: "Explosive Cask", slot: 'R' as const, skillshot: true }]
        },
      }
    ],
  }),
  Darius: makeChamp({
    id: 'Darius',
    name: "Darius",
    title: "the Hand of Noxus",
    tags: ["FIGHTER", "JUGGERNAUT", "TANK"],
    passiveName: "Hemorrhage",
    stats: {"hp": 652, "hpperlevel": 114, "mp": 263, "mpperlevel": 58, "movespeed": 340, "armor": 37, "armorperlevel": 5.2, "spellblock": 32, "spellblockperlevel": 2.05, "attackrange": 175, "hpregen": 10, "hpregenperlevel": 0.95, "mpregen": 6.6, "mpregenperlevel": 0.35, "crit": 0, "critperlevel": 0, "attackdamage": 64, "attackdamageperlevel": 5, "attackspeedperlevel": 1, "attackspeed": 0.625},
    autos: [1, 3],
    abilities: [
      {
        slot: 'Q',
        name: "Decimate",
        range: 425,
        cooldown: 9,
        skillshot: false,
        engageCc: false,
        damage: (a, _d, ctx) => {
          if (rankOf(ctx, 'Q') <= 0) return []
          return [{ raw: (rankValue([50, 80, 110, 140, 170], Math.max(1, rankOf(ctx,'Q')))) + (1.0*a.ad), type: 'physical' as const, source: "Decimate", slot: 'Q' as const }]
        },
      },
      {
        slot: 'W',
        name: "Crippling Strike",
        range: 300,
        cooldown: 5,
        skillshot: false,
        engageCc: false,
        damage: () => [],
      },
      {
        slot: 'E',
        name: "Apprehend",
        range: 535,
        cooldown: 26,
        skillshot: false,
        engageCc: true,
        damage: () => [],
      },
      {
        slot: 'R',
        name: "Noxian Guillotine",
        range: 460,
        cooldown: 120,
        skillshot: false,
        engageCc: false,
        damage: (a, _d, ctx) => {
          if (rankOf(ctx, 'R') <= 0) return []
          return [{ raw: (rankValue([125, 250, 375], Math.max(1, rankOf(ctx,'R')))) + (0.75*bonusAd(a)), type: 'true' as const, source: "Noxian Guillotine", slot: 'R' as const }]
        },
      }
    ],
  }),
  Ahri: makeChamp({
    id: 'Ahri',
    name: "Ahri",
    title: "the Nine-Tailed Fox",
    tags: ["ASSASSIN", "BURST", "MAGE"],
    passiveName: "Essence Theft",
    stats: {"hp": 590, "hpperlevel": 104, "mp": 418, "mpperlevel": 25, "movespeed": 330, "armor": 21, "armorperlevel": 4.2, "spellblock": 30, "spellblockperlevel": 1.3, "attackrange": 550, "hpregen": 2.5, "hpregenperlevel": 0.6, "mpregen": 8, "mpregenperlevel": 0.8, "crit": 0, "critperlevel": 0, "attackdamage": 53, "attackdamageperlevel": 3, "attackspeedperlevel": 2.2, "attackspeed": 0.668},
    autos: [1, 3],
    abilities: [
      {
        slot: 'Q',
        name: "Orb of Deception",
        range: 970,
        cooldown: 7,
        skillshot: true,
        engageCc: false,
        damage: (a, _d, ctx) => {
          if (rankOf(ctx, 'Q') <= 0) return []
          return [{ raw: (rankValue([40, 65, 90, 115, 140], Math.max(1, rankOf(ctx,'Q')))) + (0.5*a.ap), type: 'physical' as const, source: "Orb of Deception", slot: 'Q' as const, skillshot: true }]
        },
      },
      {
        slot: 'W',
        name: "Fox-Fire",
        range: 700,
        cooldown: 10,
        skillshot: false,
        engageCc: false,
        damage: (a, _d, ctx) => {
          if (rankOf(ctx, 'W') <= 0) return []
          return [{ raw: (rankValue([40, 60, 80, 100, 120], Math.max(1, rankOf(ctx,'W')))) + (0.4*a.ap), type: 'magical' as const, source: "Fox-Fire", slot: 'W' as const }]
        },
      },
      {
        slot: 'E',
        name: "Charm",
        range: 975,
        cooldown: 12,
        skillshot: true,
        engageCc: true,
        damage: (a, _d, ctx) => {
          if (rankOf(ctx, 'E') <= 0) return []
          return [{ raw: (rankValue([80, 120, 160, 200, 240], Math.max(1, rankOf(ctx,'E')))) + (0.85*a.ap), type: 'magical' as const, source: "Charm", slot: 'E' as const, skillshot: true }]
        },
      },
      {
        slot: 'R',
        name: "Spirit Rush",
        range: 450,
        cooldown: 140,
        skillshot: false,
        engageCc: false,
        damage: (a, _d, ctx) => {
          if (rankOf(ctx, 'R') <= 0) return []
          return [{ raw: (rankValue([60, 90, 120], Math.max(1, rankOf(ctx,'R')))) + (0.35*a.ap), type: 'magical' as const, source: "Spirit Rush", slot: 'R' as const }]
        },
      }
    ],
  }),
  Lux: makeChamp({
    id: 'Lux',
    name: "Lux",
    title: "the Lady of Luminosity",
    tags: ["ARTILLERY", "BURST", "MAGE"],
    passiveName: "Illumination",
    stats: {"hp": 580, "hpperlevel": 99, "mp": 480, "mpperlevel": 23.5, "movespeed": 330, "armor": 21, "armorperlevel": 5.2, "spellblock": 30, "spellblockperlevel": 1.3, "attackrange": 550, "hpregen": 5.5, "hpregenperlevel": 0.55, "mpregen": 7, "mpregenperlevel": 0.8, "crit": 0, "critperlevel": 0, "attackdamage": 54, "attackdamageperlevel": 3.3, "attackspeedperlevel": 3, "attackspeed": 0.669},
    autos: [1, 3],
    abilities: [
      {
        slot: 'Q',
        name: "Light Binding",
        range: 1175,
        cooldown: 11,
        skillshot: true,
        engageCc: true,
        damage: (a, _d, ctx) => {
          if (rankOf(ctx, 'Q') <= 0) return []
          return [{ raw: (rankValue([80, 120, 160, 200, 240], Math.max(1, rankOf(ctx,'Q')))) + (0.65*a.ap), type: 'magical' as const, source: "Light Binding", slot: 'Q' as const, skillshot: true }]
        },
      },
      {
        slot: 'W',
        name: "Prismatic Barrier",
        range: 1075,
        cooldown: 14,
        skillshot: false,
        engageCc: false,
        damage: () => [],
      },
      {
        slot: 'E',
        name: "Lucent Singularity",
        range: 1100,
        cooldown: 10,
        skillshot: true,
        engageCc: false,
        damage: (a, _d, ctx) => {
          if (rankOf(ctx, 'E') <= 0) return []
          return [{ raw: (rankValue([65, 115, 165, 215, 265], Math.max(1, rankOf(ctx,'E')))) + (0.8*a.ap), type: 'magical' as const, source: "Lucent Singularity", slot: 'E' as const, skillshot: true }]
        },
      },
      {
        slot: 'R',
        name: "Final Spark",
        range: 3340,
        cooldown: 60,
        skillshot: true,
        engageCc: false,
        damage: (a, _d, ctx) => {
          if (rankOf(ctx, 'R') <= 0) return []
          return [{ raw: (rankValue([300, 400, 500], Math.max(1, rankOf(ctx,'R')))) + (1.2*a.ap), type: 'magical' as const, source: "Final Spark", slot: 'R' as const, skillshot: true }]
        },
      }
    ],
  }),
  Annie: makeChamp({
    id: 'Annie',
    name: "Annie",
    title: "the Dark Child",
    tags: ["BURST", "MAGE", "SUPPORT"],
    passiveName: "Pyromania",
    stats: {"hp": 560, "hpperlevel": 96, "mp": 418, "mpperlevel": 25, "movespeed": 335, "armor": 23, "armorperlevel": 4, "spellblock": 30, "spellblockperlevel": 1.3, "attackrange": 625, "hpregen": 5.5, "hpregenperlevel": 0.55, "mpregen": 8, "mpregenperlevel": 0.8, "crit": 0, "critperlevel": 0, "attackdamage": 50, "attackdamageperlevel": 2.65, "attackspeedperlevel": 1.36, "attackspeed": 0.61},
    autos: [1, 3],
    abilities: [
      {
        slot: 'Q',
        name: "Disintegrate",
        range: 625,
        cooldown: 4,
        skillshot: false,
        engageCc: false,
        damage: (a, _d, ctx) => {
          if (rankOf(ctx, 'Q') <= 0) return []
          return [{ raw: (rankValue([80, 120, 160, 200, 240], Math.max(1, rankOf(ctx,'Q')))) + (0.8*a.ap), type: 'magical' as const, source: "Disintegrate", slot: 'Q' as const }]
        },
      },
      {
        slot: 'W',
        name: "Incinerate",
        range: 600,
        cooldown: 7,
        skillshot: false,
        engageCc: false,
        damage: (a, _d, ctx) => {
          if (rankOf(ctx, 'W') <= 0) return []
          return [{ raw: (rankValue([70, 115, 160, 205, 250], Math.max(1, rankOf(ctx,'W')))) + (0.8*a.ap), type: 'magical' as const, source: "Incinerate", slot: 'W' as const }]
        },
      },
      {
        slot: 'E',
        name: "Molten Shield",
        range: 0,
        cooldown: 12,
        skillshot: false,
        engageCc: false,
        damage: (a, _d, ctx) => {
          if (rankOf(ctx, 'E') <= 0) return []
          return [{ raw: (rankValue([25, 35, 45, 55, 65], Math.max(1, rankOf(ctx,'E')))) + (0.4*a.ap), type: 'magical' as const, source: "Molten Shield", slot: 'E' as const }]
        },
      },
      {
        slot: 'R',
        name: "Summon: Tibbers",
        range: 600,
        cooldown: 130,
        skillshot: false,
        engageCc: true,
        damage: (a, _d, ctx) => {
          if (rankOf(ctx, 'R') <= 0) return []
          return [{ raw: (rankValue([150, 275, 400], Math.max(1, rankOf(ctx,'R')))) + (0.75*a.ap), type: 'magical' as const, source: "Summon: Tibbers", slot: 'R' as const }]
        },
      }
    ],
  }),
  Malphite: makeChamp({
    id: 'Malphite',
    name: "Malphite",
    title: "Shard of the Monolith",
    tags: ["MAGE", "TANK", "VANGUARD"],
    passiveName: "Granite Shield",
    stats: {"hp": 665, "hpperlevel": 104, "mp": 280, "mpperlevel": 60, "movespeed": 335, "armor": 37, "armorperlevel": 4.95, "spellblock": 28, "spellblockperlevel": 2.05, "attackrange": 125, "hpregen": 7, "hpregenperlevel": 0.55, "mpregen": 7.3, "mpregenperlevel": 0.55, "crit": 0, "critperlevel": 0, "attackdamage": 62, "attackdamageperlevel": 4, "attackspeedperlevel": 3.4, "attackspeed": 0.736},
    autos: [1, 3],
    abilities: [
      {
        slot: 'Q',
        name: "Seismic Shard",
        range: 625,
        cooldown: 8,
        skillshot: false,
        engageCc: false,
        damage: (a, _d, ctx) => {
          if (rankOf(ctx, 'Q') <= 0) return []
          return [{ raw: (rankValue([70, 120, 170, 220, 270], Math.max(1, rankOf(ctx,'Q')))) + (0.6*a.ap), type: 'magical' as const, source: "Seismic Shard", slot: 'Q' as const }]
        },
      },
      {
        slot: 'W',
        name: "Thunderclap",
        range: 250,
        cooldown: 10,
        skillshot: false,
        engageCc: false,
        damage: (a, _d, ctx) => {
          if (rankOf(ctx, 'W') <= 0) return []
          return [{ raw: (rankValue([30, 40, 50, 60, 70], Math.max(1, rankOf(ctx,'W')))) + (0.2*a.ap), type: 'physical' as const, source: "Thunderclap", slot: 'W' as const }]
        },
      },
      {
        slot: 'E',
        name: "Ground Slam",
        range: 400,
        cooldown: 7,
        skillshot: false,
        engageCc: false,
        damage: (a, _d, ctx) => {
          if (rankOf(ctx, 'E') <= 0) return []
          return [{ raw: (rankValue([70, 110, 150, 190, 230], Math.max(1, rankOf(ctx,'E')))) + (0.6*a.ap), type: 'magical' as const, source: "Ground Slam", slot: 'E' as const }]
        },
      },
      {
        slot: 'R',
        name: "Unstoppable Force",
        range: 1000,
        cooldown: 130,
        skillshot: true,
        engageCc: true,
        damage: (a, _d, ctx) => {
          if (rankOf(ctx, 'R') <= 0) return []
          return [{ raw: (rankValue([200, 300, 400], Math.max(1, rankOf(ctx,'R')))) + (0.9*a.ap), type: 'magical' as const, source: "Unstoppable Force", slot: 'R' as const, skillshot: true }]
        },
      }
    ],
  }),
  Garen: makeChamp({
    id: 'Garen',
    name: "Garen",
    title: "The Might of Demacia",
    tags: ["FIGHTER", "JUGGERNAUT", "TANK"],
    passiveName: "Perseverance",
    stats: {"hp": 690, "hpperlevel": 98, "mp": 0, "mpperlevel": 0, "movespeed": 340, "armor": 38, "armorperlevel": 4.2, "spellblock": 32, "spellblockperlevel": 1.55, "attackrange": 175, "hpregen": 8, "hpregenperlevel": 0.5, "mpregen": 0, "mpregenperlevel": 0, "crit": 0, "critperlevel": 0, "attackdamage": 69, "attackdamageperlevel": 4.5, "attackspeedperlevel": 3.65, "attackspeed": 0.625},
    autos: [1, 3],
    abilities: [
      {
        slot: 'Q',
        name: "Decisive Strike",
        range: 300,
        cooldown: 8,
        skillshot: false,
        engageCc: true,
        damage: (a, _d, ctx) => {
          if (rankOf(ctx, 'Q') <= 0) return []
          return [{ raw: (rankValue([30, 60, 90, 120, 150], Math.max(1, rankOf(ctx,'Q')))) + (0.5*a.ad), type: 'physical' as const, source: "Decisive Strike", slot: 'Q' as const }]
        },
      },
      {
        slot: 'W',
        name: "Courage",
        range: 0,
        cooldown: 22,
        skillshot: false,
        engageCc: false,
        damage: () => [],
      },
      {
        slot: 'E',
        name: "Judgment",
        range: 325,
        cooldown: 9,
        skillshot: false,
        engageCc: false,
        damage: (a, _d, ctx) => {
          if (rankOf(ctx, 'E') <= 0) return []
          return [{ raw: (rankValue([4, 7, 10, 13, 16], Math.max(1, rankOf(ctx,'E')))) + (0.36*a.ad), type: 'physical' as const, source: "Judgment", slot: 'E' as const }]
        },
      },
      {
        slot: 'R',
        name: "Demacian Justice",
        range: 400,
        cooldown: 120,
        skillshot: false,
        engageCc: false,
        damage: (_a, d, ctx) => {
          if (rankOf(ctx, 'R') <= 0) return []
          return [{ raw: (rankValue([150, 250, 350], Math.max(1, rankOf(ctx,'R')))) + (0.25*d.hp), type: 'true' as const, source: "Demacian Justice", slot: 'R' as const }]
        },
      }
    ],
  }),
  Jax: makeChamp({
    id: 'Jax',
    name: "Jax",
    title: "Grandmaster at Arms",
    tags: ["ASSASSIN", "FIGHTER", "SKIRMISHER"],
    passiveName: "Relentless Assault",
    stats: {"hp": 665, "hpperlevel": 103, "mp": 339, "mpperlevel": 52, "movespeed": 350, "armor": 36, "armorperlevel": 4.2, "spellblock": 32, "spellblockperlevel": 2.05, "attackrange": 125, "hpregen": 8.5, "hpregenperlevel": 0.55, "mpregen": 8.2, "mpregenperlevel": 0.7, "crit": 0, "critperlevel": 0, "attackdamage": 68, "attackdamageperlevel": 4.25, "attackspeedperlevel": 3.4, "attackspeed": 0.638},
    autos: [1, 3],
    abilities: [
      {
        slot: 'Q',
        name: "Leap Strike",
        range: 700,
        cooldown: 8,
        skillshot: false,
        engageCc: true,
        damage: (a, _d, ctx) => {
          if (rankOf(ctx, 'Q') <= 0) return []
          return [{ raw: (rankValue([65, 105, 145, 185, 225], Math.max(1, rankOf(ctx,'Q')))) + (1.0*bonusAd(a)), type: 'physical' as const, source: "Leap Strike", slot: 'Q' as const }]
        },
      },
      {
        slot: 'W',
        name: "Empower",
        range: 250,
        cooldown: 7,
        skillshot: false,
        engageCc: false,
        damage: (a, _d, ctx) => {
          if (rankOf(ctx, 'W') <= 0) return []
          return [{ raw: (rankValue([50, 85, 120, 155, 190], Math.max(1, rankOf(ctx,'W')))) + (0.6*a.ap), type: 'magical' as const, source: "Empower", slot: 'W' as const }]
        },
      },
      {
        slot: 'E',
        name: "Counter Strike",
        range: 300,
        cooldown: 17,
        skillshot: false,
        engageCc: false,
        damage: (a, d, ctx) => {
          if (rankOf(ctx, 'E') <= 0) return []
          return [{ raw: (rankValue([40, 70, 100, 130, 160], Math.max(1, rankOf(ctx,'E')))) + (0.7*a.ap + 0.035*d.hp), type: 'magical' as const, source: "Counter Strike", slot: 'E' as const }]
        },
      },
      {
        slot: 'R',
        name: "Grandmaster-at-Arms",
        range: 250,
        cooldown: 110,
        skillshot: false,
        engageCc: false,
        damage: (a, _d, ctx) => {
          if (rankOf(ctx, 'R') <= 0) return []
          return [{ raw: (rankValue([75, 130, 185], Math.max(1, rankOf(ctx,'R')))) + (0.6*a.ap), type: 'magical' as const, source: "Grandmaster-at-Arms", slot: 'R' as const }]
        },
      }
    ],
  })
}

export const DDRAGON_VERSION = '16.14.1'
