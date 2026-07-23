#!/usr/bin/env node
/**
 * Build compact Meraki ability kit data for all wiki champions.
 *
 * Source: public/data/lolwiki/champions-full.json
 * Output: src/data/generated/merakiAbilityKits.ts
 *
 * Damage formulas are first-pass Meraki leveling mirrors (experimental).
 * CORE hand kits and existing GAME_CHAMPIONS still win at merge time.
 */
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..')
const SRC = join(ROOT, 'public/data/lolwiki/champions-full.json')
const OUT = join(ROOT, 'src/data/generated/merakiAbilityKits.ts')

const DAMAGE_ATTR_PRIORITY = [
  /^physical damage$/i,
  /^magic damage$/i,
  /^true damage$/i,
  /^total physical damage$/i,
  /^total magic damage$/i,
  /^bonus physical damage$/i,
  /^bonus magic damage$/i,
  /^minimum physical damage$/i,
  /^minimum magic damage$/i,
  /physical damage/i,
  /magic damage/i,
  /true damage/i,
]

function firstNumber(value) {
  if (value == null) return null
  if (typeof value === 'number' && Number.isFinite(value)) return value
  const m = String(value).match(/(\d+(?:\.\d+)?)/)
  return m ? Number(m[1]) : null
}

function cooldownSec(ability) {
  const mods = ability?.cooldown?.modifiers
  if (!Array.isArray(mods) || !mods.length) return 8
  const values = mods[0]?.values
  if (!Array.isArray(values) || !values.length) return 8
  const n = Number(values[0])
  return Number.isFinite(n) && n > 0 ? n : 8
}

function abilityRange(ability, skillshot) {
  const fromTarget = firstNumber(ability?.targetRange)
  if (fromTarget != null && fromTarget > 0 && fromTarget < 5000) return fromTarget
  const fromWidth = firstNumber(ability?.width)
  if (skillshot && fromWidth != null && fromWidth > 50) return Math.max(600, fromWidth * 4)
  return skillshot ? 900 : 550
}

function isSkillshot(ability) {
  const targeting = String(ability?.targeting || '')
  return /direction/i.test(targeting)
}

function damageTypeOf(ability, attr) {
  const raw = `${ability?.damageType || ''} ${attr || ''}`.toLowerCase()
  if (raw.includes('true')) return 'true'
  if (raw.includes('physical')) return 'physical'
  return 'magical'
}

function pickDamageLeveling(ability) {
  const rows = []
  for (const effect of ability?.effects || []) {
    for (const leveling of effect?.leveling || []) {
      const attr = String(leveling?.attribute || '')
      if (!/damage/i.test(attr)) continue
      if (/taken|reduction|shield|heal/i.test(attr)) continue
      rows.push(leveling)
    }
  }
  if (!rows.length) return null
  for (const re of DAMAGE_ATTR_PRIORITY) {
    const hit = rows.find((r) => re.test(String(r.attribute || '')))
    if (hit) return hit
  }
  return rows[0]
}

function parseRatioUnit(unit) {
  const u = String(unit || '').trim().toLowerCase()
  if (!u) return null
  if (u === '% ap') return { stat: 'ap', per: 100 }
  if (u === '% ad') return { stat: 'ad', per: 100 }
  if (u === '% bonus ad') return { stat: 'bonusAd', per: 100 }
  if (u === '% per 100 ap') return { stat: 'ap', per: 100, perHundred: true }
  if (u === '% per 100 bonus ad') return { stat: 'bonusAd', per: 100, perHundred: true }
  if (u.includes("target's maximum health") || u.includes('maximum health')) {
    return { stat: 'targetMaxHp', per: 100 }
  }
  if (u.includes('missing health')) return { stat: 'targetMissingHp', per: 100 }
  return null
}

function compactDamage(leveling, ability) {
  if (!leveling) return null
  const mods = Array.isArray(leveling.modifiers) ? leveling.modifiers : []
  let base = null
  const ratios = []
  for (const mod of mods) {
    const values = Array.isArray(mod.values) ? mod.values.map(Number) : []
    if (!values.length || values.some((v) => !Number.isFinite(v))) continue
    const units = mod.units || []
    const unit = units.find((u) => String(u || '').trim()) || ''
    const ratio = parseRatioUnit(unit)
    if (ratio) {
      // Coefficient is the (usually flat across ranks) first value.
      const coeff = values[0]
      ratios.push({ ...ratio, values: values.map((v) => v / (ratio.per || 100)) })
      // Keep per-rank ratio values when they vary; factory uses rankValue.
      void coeff
    } else if (!String(unit).trim()) {
      base = values
    }
  }
  if (!base && !ratios.length) return null
  return {
    type: damageTypeOf(ability, leveling.attribute),
    base: base || [0, 0, 0, 0, 0].slice(0, Math.max(3, ...(ratios.map((r) => r.values.length)))),
    ratios: ratios.map((r) => ({
      stat: r.stat,
      values: r.values,
    })),
  }
}

function buildAbility(slot, ability) {
  if (!ability) return null
  const skillshot = isSkillshot(ability)
  const leveling = pickDamageLeveling(ability)
  const damage = compactDamage(leveling, ability)
  return {
    slot,
    name: String(ability.name || slot),
    range: abilityRange(ability, skillshot),
    cooldown: cooldownSec(ability),
    skillshot,
    damage,
  }
}

function autosForChamp(champ) {
  const ranged = String(champ.attackType || '').toUpperCase() === 'RANGED'
  return ranged ? [2, 4] : [1, 3]
}

function flatStat(stats, key, fallback = 0) {
  const node = stats?.[key]
  if (!node) return fallback
  const n = Number(node.flat)
  return Number.isFinite(n) ? n : fallback
}

function perStat(stats, key, fallback = 0) {
  const node = stats?.[key]
  if (!node) return fallback
  const n = Number(node.perLevel)
  return Number.isFinite(n) ? n : fallback
}

function baseStats(champ) {
  const s = champ.stats || {}
  return {
    hp: flatStat(s, 'health', 500),
    hpperlevel: perStat(s, 'health', 80),
    mp: flatStat(s, 'mana', 0),
    mpperlevel: perStat(s, 'mana', 0),
    movespeed: flatStat(s, 'movespeed', 325),
    armor: flatStat(s, 'armor', 30),
    armorperlevel: perStat(s, 'armor', 3),
    spellblock: flatStat(s, 'magicResistance', 30),
    spellblockperlevel: perStat(s, 'magicResistance', 1.5),
    attackrange: flatStat(s, 'attackRange', 125),
    hpregen: flatStat(s, 'healthRegen', 5),
    hpregenperlevel: perStat(s, 'healthRegen', 0.5),
    mpregen: flatStat(s, 'manaRegen', 0),
    mpregenperlevel: perStat(s, 'manaRegen', 0),
    crit: 0,
    critperlevel: 0,
    attackdamage: flatStat(s, 'attackDamage', 60),
    attackdamageperlevel: perStat(s, 'attackDamage', 3),
    attackspeedperlevel: perStat(s, 'attackSpeed', 2),
    attackspeed: flatStat(s, 'attackSpeed', 0.625),
    attackspeedratio: flatStat(s, 'attackSpeedRatio', flatStat(s, 'attackSpeed', 0.625)),
  }
}

const wiki = JSON.parse(readFileSync(SRC, 'utf8'))
const kits = {}
let withDamage = 0
let abilities = 0

for (const [id, champ] of Object.entries(wiki)) {
  const ab = champ.abilities || {}
  const outAbs = []
  for (const slot of ['Q', 'W', 'E', 'R']) {
    const row = Array.isArray(ab[slot]) ? ab[slot][0] : null
    const built = buildAbility(slot, row)
    if (!built) continue
    outAbs.push(built)
    abilities += 1
    if (built.damage) withDamage += 1
  }
  kits[id] = {
    id,
    name: champ.name || id,
    title: champ.title || '',
    tags: Array.isArray(champ.roles) ? champ.roles.slice(0, 4) : [],
    passiveName: Array.isArray(ab.P) && ab.P[0]?.name ? ab.P[0].name : '',
    stats: baseStats(champ),
    autos: autosForChamp(champ),
    abilities: outAbs,
  }
}

mkdirSync(dirname(OUT), { recursive: true })
const body = `/* AUTO-GENERATED by scripts/generate-meraki-ability-kits.mjs — do not edit */
export type MerakiRatioStat = 'ap' | 'ad' | 'bonusAd' | 'targetMaxHp' | 'targetMissingHp'

export interface MerakiAbilityDamage {
  type: 'physical' | 'magical' | 'true'
  base: number[]
  ratios: { stat: MerakiRatioStat; values: number[] }[]
}

export interface MerakiAbilityKit {
  slot: 'Q' | 'W' | 'E' | 'R'
  name: string
  range: number
  cooldown: number
  skillshot: boolean
  damage: MerakiAbilityDamage | null
}

export interface MerakiChampionKit {
  id: string
  name: string
  title: string
  tags: string[]
  passiveName: string
  stats: import('../../engine/types').ChampionBaseStats
  autos: [number, number]
  abilities: MerakiAbilityKit[]
}

export const MERAKI_ABILITY_KITS: Record<string, MerakiChampionKit> = ${JSON.stringify(kits, null, 2)}

export const MERAKI_ABILITY_KIT_IDS = Object.keys(MERAKI_ABILITY_KITS)
`

writeFileSync(OUT, body)
console.log(
  JSON.stringify(
    {
      wrote: OUT,
      champions: Object.keys(kits).length,
      abilities,
      withDamage,
    },
    null,
    2,
  ),
)
