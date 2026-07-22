import type { TeamObjectives } from './objectives'
import {
  combatModsFromObjectives,
  countDragonStacks,
  formatDragonTags,
  GRUB,
  grubTickDamage,
  grubTouchBriefCeilingTrue,
  grubTouchGoldEquivalent,
} from './objectives'

/** Compact career snapshot attached to timeline units. */
export interface ChampCareerStats {
  kills: number
  deaths: number
  assists: number
  cs: number
  jungleCs: number
  visionScore: number
  dmgTotal: number
  dmgToChamps: number
  physToChamps: number
  magicToChamps: number
  trueToChamps: number
  dmgTaken: number
  dmgTakenFromChamps: number
  selfMitigated: number
  dmgToTurrets: number
  dmgToBuildings: number
  dmgToObjectives: number
  ccToChamps: number
  healOnTeammates: number
  shieldOnTeammates: number
  /**
   * Cumulative Touch-of-the-Void true damage from wiki burn model
   * (structure AA refresh + Hunger mite uptime). Monotonic in time.
   */
  touchDmg?: number
  touchTick?: number
  touchStacks?: number
  hungerActive?: boolean
  touchRanged?: boolean
  /** Integrated burn-active seconds (enricher). */
  touchBurnSec?: number
  /** Hunger mite summons counted by enricher. */
  touchHungerProcs?: number
  /** Accepted structure-AA refresh inferences. */
  touchRefreshAa?: number
  touchRejectedFar?: number
  touchRejectedAbility?: number
  /** Turret rises coincident with skill_used / item active (vetoed). */
  touchRejectedSkill?: number
  touchRefreshMite?: number
  touchConfidence?: 'high' | 'medium' | 'low'
  touchModel?: string
  /** Feed attack speed as % of base (100 = baseline). */
  asPct: number
  cdr: number
  lifeSteal: number
  spellVamp: number
  hpRegen: number
  /** Lifetime gold earned (Riot totalGold). */
  gold: number
  /** Unspent gold in inventory (Riot currentGold). */
  goldBag?: number
}

/**
 * Per-champ quantified use of the team's dragon buffs.
 * Each term is a proxy of “who converted the buff into outcome.”
 */
export interface DrakeAttribution {
  /** Infernal %AD/%AP → phys×p/(1+p) + magic×p/(1+p). */
  infernalBonusDmg: number
  /** Mountain % resists share of self-mitigated: mit×p/(1+p). */
  mountainMitigated: number
  /** Cloud (+ soul) MS % — team buff; not distance-traveled. */
  cloudMsPct: number
  /** Chemtech blight heal/shield power share of ally heal+shield (tracked attribution; not combat-applied). */
  chemHspBonus: number
  /** Chemtech blight tenacity % (tracked; not combat-applied). */
  chemTenacityPct: number
  /** Hextech dragon AH (permanent stacks only). */
  hexAh: number
  /** Hextech dragon AS %. */
  hexAsPct: number
  /** Chemtech soul fight amp share — always 0 without threshold-time evidence. */
  soulBonusDmg: number
  /** Chemtech soul DR share — always 0 without threshold-time evidence. */
  soulMitigated: number
  /** Ocean stacks (regen disclosed; not quantified without timed HP series). */
  oceanStacks: number
  /** Short quantity lines for the cell. */
  quantities: string[]
  /** Wiki tags (team state). */
  tags: string[]
  /** Sort: summed damage-like use (amp + mitigated + HSP bonus). */
  sortValue: number
}

/** Zaahen-style Touch audit trail (assumptions + reproducible terms). */
export interface GrubTouchAudit {
  stacks: number
  ranged: boolean
  role: 'melee' | 'ranged'
  tick: number
  tickInterval: number
  trueDps: number
  burnDuration: number
  /** One full 4s burn cycle: 8 ticks × tick. */
  cycleTrueDmg: number
  /** Model cumulative Touch true (enricher) — estimated, not feed. */
  touchTrue: number
  /** Burn-active seconds (measured or touchTrue/dps). */
  burnUptimeSec: number
  turretDmg: number
  /**
   * Turret − Touch only when confidence is high and residual trusted.
   * Otherwise null — mixed Riot turret stat must not subtract true DoT.
   */
  residualTurret: number | null
  residualTrusted: boolean
  /** Touch / turret when residual trusted; else null. */
  touchShare: number | null
  plateHp: number
  plateGold: number
  /** touchTrue / plateHp × plateGold. */
  plateProgressGold: number
  hungerActive: boolean
  hungerProcs: number
  refreshAa: number
  rejectedFar: number
  rejectedAbility: number
  rejectedSkill: number
  refreshMite: number
  confidence: 'high' | 'medium' | 'low'
  flags: string[]
  modelVersion: string
  /** Article brief-ceiling scenario (8s, Hunger omitted), not measured gold. */
  briefCeilingTrue: number
  briefCeilingPlateGold: number
  assumptions: string[]
}

export interface GrubAttribution {
  stacks: number
  tick: number
  ranged: boolean
  touchDmg: number
  hungerActive: boolean
  note: string
  audit: GrubTouchAudit
  sortValue: number
}

function pctLabel(p: number): string {
  const n = p * 100
  return Number.isInteger(n) ? `${n}%` : `${n.toFixed(1)}%`
}

function shareFromPercent(base: number, p: number): number {
  if (base <= 0 || p <= 0) return 0
  return (base * p) / (1 + p)
}

/**
 * Quantify how much each champ converted team dragon buffs into
 * damage amp, mitigation, HSP, etc. Cloud MS is magnitude only (no pathing).
 * Chemtech Soul amp/DR is never attributed as always-on — requires threshold
 * timing evidence (zero quantified soul amp/mit this batch).
 */
export function attributeDrakeBuffs(
  obj: TeamObjectives | null | undefined,
  c?: ChampCareerStats | null,
  gameTimeSec = 25 * 60,
): DrakeAttribution {
  const tags = formatDragonTags(obj)
  if (obj?.baronActive) tags.push('baron AD/AP (no OV)')
  if (obj?.elderActive) tags.push('elder (unmodeled burn/execute)')
  if (obj?.hasSoul && obj.soulType === 'chemtech') {
    tags.push('chem soul ≤50% HP (conditional; unattributed)')
  }

  const empty: DrakeAttribution = {
    infernalBonusDmg: 0,
    mountainMitigated: 0,
    cloudMsPct: 0,
    chemHspBonus: 0,
    chemTenacityPct: 0,
    hexAh: 0,
    hexAsPct: 0,
    soulBonusDmg: 0,
    soulMitigated: 0,
    oceanStacks: 0,
    quantities: [],
    tags,
    sortValue: 0,
  }
  if (!obj) return empty

  const mods = combatModsFromObjectives(obj, gameTimeSec)
  // Applied Cloud Soul passive MS only — permanent Cloud OoC MS is not in mods.movespeedPct.
  const cloudMsPct = mods.movespeedPct
  const chemTenacityPct = mods.tenacity
  const hexAh = mods.abilityHaste
  const hexAsPct = mods.attackSpeedPercent
  const oceanStacks = countDragonStacks(obj, 'ocean')

  if (!c) {
    const quantities: string[] = []
    if (mods.adPercent > 0) quantities.push(`${pctLabel(mods.adPercent)} AD/AP`)
    if (mods.armorPercent > 0) quantities.push(`${pctLabel(mods.armorPercent)} resists`)
    if (cloudMsPct > 0) quantities.push(`${pctLabel(cloudMsPct)} MS (soul)`)
    if (chemTenacityPct > 0 || mods.healShieldPower > 0) {
      quantities.push(
        `${pctLabel(Math.max(chemTenacityPct, mods.healShieldPower))} tenacity/HSP (tracked)`,
      )
    }
    if (hexAh > 0) quantities.push(`+${hexAh} AH`)
    if (hexAsPct > 0) quantities.push(`+${pctLabel(hexAsPct)} AS`)
    // Never quantify always-on Chem Soul amp from mods.damageAmp (stays 0 this batch).
    if (oceanStacks > 0) quantities.push(`ocean ×${oceanStacks} (unmodeled regen)`)
    if (obj.hasSoul && obj.soulType === 'chemtech') {
      quantities.push('chem soul conditional (0 quantified)')
    }
    return {
      ...empty,
      cloudMsPct,
      chemTenacityPct,
      hexAh,
      hexAsPct,
      oceanStacks,
      quantities,
      tags,
      sortValue: quantities.length,
    }
  }

  const infernalBonusDmg =
    shareFromPercent(c.physToChamps, mods.adPercent) +
    shareFromPercent(c.magicToChamps, mods.apPercent)

  const mountainMitigated = shareFromPercent(c.selfMitigated, mods.armorPercent)

  const chemHspBonus = shareFromPercent(
    (c.healOnTeammates || 0) + (c.shieldOnTeammates || 0),
    mods.healShieldPower,
  )

  // Chem Soul amp/DR: zero without threshold-time evidence (mods.damageAmp stays 0).
  const soulBonusDmg = 0
  const soulMitigated = 0

  const quantities: string[] = []
  if (infernalBonusDmg > 0) quantities.push(`+${Math.round(infernalBonusDmg)} amp`)
  if (mountainMitigated > 0) quantities.push(`+${Math.round(mountainMitigated)} mit`)
  if (chemHspBonus > 0) quantities.push(`+${Math.round(chemHspBonus)} HSP (tracked)`)
  if (cloudMsPct > 0) quantities.push(`${pctLabel(cloudMsPct)} MS (soul)`)
  if (chemTenacityPct > 0 && chemHspBonus <= 0)
    quantities.push(`${pctLabel(chemTenacityPct)} tenacity (tracked)`)
  if (hexAh > 0) quantities.push(`+${hexAh} AH`)
  if (hexAsPct > 0) quantities.push(`+${pctLabel(hexAsPct)} AS`)
  if (oceanStacks > 0 && quantities.length === 0) {
    quantities.push(`ocean ×${oceanStacks} (unmodeled regen)`)
  }
  if (obj.hasSoul && obj.soulType === 'chemtech') {
    quantities.push('chem soul conditional (0 quantified)')
  }

  const sortValue = infernalBonusDmg + mountainMitigated + chemHspBonus

  return {
    infernalBonusDmg,
    mountainMitigated,
    cloudMsPct,
    chemHspBonus,
    chemTenacityPct,
    hexAh,
    hexAsPct,
    soulBonusDmg,
    soulMitigated,
    oceanStacks,
    quantities,
    tags,
    sortValue: sortValue > 0 ? sortValue : tags.length,
  }
}

function touchAssumptions(
  ranged: boolean,
  hungerActive: boolean,
  residualTrusted: boolean,
): string[] {
  return [
    'Touch true is an inferred burn model (touch-v5), not a Riot feed counter.',
    'SR structures seeded at t=0; plate/destroy events refine and remove them.',
    'Refresh only when near an enemy structure, turret-delta fits AD/AS AA budget, and no skill/item cast in the same window.',
    'While burn is already active, small turret-stat rises matching tick DPS are treated as Touch ticks (not far rejects).',
    'Ability-sized spikes and skill-coincident rises are vetoed — that filtering raises confidence, it does not lower it.',
    `Attack type ${ranged ? 'ranged' : 'melee'} from champion index (forms/transforms may be wrong).`,
    `Burn ${GRUB.totvBurnDuration}s from refreshing AA; first tick after 0.5s; one maintained burn (not stacked cycles).`,
    'Continuous DPS = tick/0.5 (Zaahen article uses discrete 0.5s ticks).',
    residualTrusted
      ? 'Residual turret trusted only at high confidence (clean AA refreshes dominate).'
      : 'Residual turret NOT trusted — Riot turret stat is mixed; do not subtract Touch true from it.',
    hungerActive
      ? `Hunger @${GRUB.hungerAtStacks}: mite refreshes counted in live estimate; article brief ceiling O omits mites.`
      : 'Hunger inactive (< 3 stacks).',
    `Brief ${GRUB.preferredSiegeSeconds}s ceiling = ${GRUB.preferredSiegeSeconds}×DPS true / ${GRUB.plateHpFirst} HP plate × ${GRUB.plateGold}g (article O; Hunger omitted).`,
    'Excluded: Reinforced Armor, backdoor, minions, allies, latency, animation cancels.',
    'VOD path: scripts/touch_vod_probe.py cuts ambiguous siege windows for AA/ability labels.',
  ]
}

/**
 * Prefer enriched cumulative touchDmg. Builds Zaahen-style audit trail.
 */
export function attributeGrubTouchFromCareer(
  c: ChampCareerStats | null | undefined,
  teamStacks: number,
): GrubAttribution {
  const stacks = Math.min(
    GRUB.maxStacks,
    Math.max(0, c?.touchStacks ?? teamStacks ?? 0),
  )
  const ranged = c?.touchRanged ?? false
  const tick = c?.touchTick ?? grubTickDamage(stacks, ranged)
  const touchDmg = Math.max(0, c?.touchDmg ?? 0)
  const hungerActive = c?.hungerActive ?? stacks >= GRUB.hungerAtStacks
  const hungerProcs = Math.max(0, c?.touchHungerProcs ?? 0)
  const refreshAa = Math.max(0, c?.touchRefreshAa ?? 0)
  const rejectedFar = Math.max(0, c?.touchRejectedFar ?? 0)
  const rejectedAbility = Math.max(0, c?.touchRejectedAbility ?? 0)
  const rejectedSkill = Math.max(0, c?.touchRejectedSkill ?? 0)
  const refreshMite = Math.max(0, c?.touchRefreshMite ?? 0)
  const trueDps = tick > 0 ? tick / GRUB.totvTickInterval : 0
  const cycleTrueDmg =
    tick > 0 ? tick * (GRUB.totvBurnDuration / GRUB.totvTickInterval) : 0
  const burnUptimeSec =
    c?.touchBurnSec != null && c.touchBurnSec > 0
      ? c.touchBurnSec
      : trueDps > 0
        ? touchDmg / trueDps
        : 0
  const turretDmg = Math.max(0, c?.dmgToTurrets ?? 0)

  let confidence: 'high' | 'medium' | 'low' =
    c?.touchConfidence ?? (touchDmg > 0 ? 'medium' : 'low')
  const flags: string[] = []
  if (rejectedFar > 0) flags.push('far_from_turret_rejected')
  if (rejectedAbility > 0) flags.push('ability_sized_delta_rejected')
  if (rejectedSkill > 0) flags.push('skill_coincident_rejected')
  if (refreshMite > 0) flags.push('hunger_mite_refresh')
  flags.push('static_attack_type')
  if (c?.touchModel == null && touchDmg > 0) {
    flags.push('legacy_enrichment')
    confidence = 'low'
  }

  const residualTrusted = confidence === 'high' && touchDmg > 0
  const residualTurret = residualTrusted
    ? Math.max(0, turretDmg - touchDmg)
    : null
  const touchShare =
    residualTrusted && turretDmg > 0 ? touchDmg / turretDmg : null
  if (!residualTrusted && touchDmg > 0) flags.push('residual_untrusted')

  const plateProgressGold =
    touchDmg > 0 ? (touchDmg / GRUB.plateHpFirst) * GRUB.plateGold : 0
  const briefCeilingTrue = Math.round(
    grubTouchBriefCeilingTrue(stacks, GRUB.preferredSiegeSeconds, ranged),
  )
  const briefCeilingPlateGold = grubTouchGoldEquivalent(
    stacks,
    GRUB.preferredSiegeSeconds,
    ranged,
  )
  if (touchDmg > briefCeilingTrue * 3 && briefCeilingTrue > 0) {
    flags.push('exceeds_brief_ceiling')
  }

  const role = ranged ? 'ranged' : 'melee'
  let note: string
  if (stacks <= 0) note = 'no grubs'
  else if (touchDmg > 0) {
    note = `est. ${stacks} stk · ${tick}/0.5s ${role} · ${confidence}${hungerActive ? ' · Hunger' : ''}`
  } else {
    note = `${stacks} stk · ${tick}/0.5s ${role} ready${hungerActive ? ' · Hunger' : ''}`
  }

  const audit: GrubTouchAudit = {
    stacks,
    ranged,
    role,
    tick,
    tickInterval: GRUB.totvTickInterval,
    trueDps,
    burnDuration: GRUB.totvBurnDuration,
    cycleTrueDmg,
    touchTrue: touchDmg,
    burnUptimeSec,
    turretDmg,
    residualTurret,
    residualTrusted,
    touchShare,
    plateHp: GRUB.plateHpFirst,
    plateGold: GRUB.plateGold,
    plateProgressGold,
    hungerActive,
    hungerProcs,
    refreshAa,
    rejectedFar,
    rejectedAbility,
    rejectedSkill,
    refreshMite,
    confidence,
    flags,
    modelVersion: c?.touchModel ?? 'unknown',
    briefCeilingTrue,
    briefCeilingPlateGold,
    assumptions: touchAssumptions(ranged, hungerActive, residualTrusted),
  }

  return {
    stacks,
    tick,
    ranged,
    touchDmg,
    hungerActive,
    note,
    audit,
    // Prefer plate-eq for ranking when we have a model estimate
    sortValue: touchDmg > 0 ? plateProgressGold : stacks,
  }
}

/** @deprecated tower-share proxy — use attributeGrubTouchFromCareer */
export function attributeGrubTouch(
  stacks: number,
  _towersTaken: number,
  _champTurretDmg: number,
  _teamTurretDmg: number,
): GrubAttribution {
  return attributeGrubTouchFromCareer(
    {
      touchStacks: stacks,
      touchDmg: 0,
      touchTick: GRUB.totvTickMeleeByStack[Math.min(GRUB.maxStacks, stacks)] ?? 0,
      hungerActive: stacks >= GRUB.hungerAtStacks,
      touchRanged: false,
    } as ChampCareerStats,
    stacks,
  )
}

export function estimateGrubStructureDamage(
  stacks: number,
  _towersTaken: number,
): number {
  return Math.round(grubTouchGoldEquivalent(stacks))
}

export function grubAttributionNote(
  stacks: number,
  _towersTaken?: number,
  _teamTurretDmg?: number,
): string {
  if (stacks <= 0) return 'No void grubs'
  const melee = GRUB.totvTickMeleeByStack[Math.min(GRUB.maxStacks, stacks)]
  const ranged = GRUB.totvTickRangedByStack[Math.min(GRUB.maxStacks, stacks)]
  const hunger =
    stacks >= GRUB.hungerAtStacks ? ' · Hunger (1 mite / 15s)' : ''
  return `${stacks} grub${stacks === 1 ? '' : 's'}: Touch ${melee}/${ranged} melee/ranged per 0.5s${hunger}`
}

export interface SustainAttribution {
  healAlly: number
  shieldAlly: number
  supportTotal: number
  lifeSteal: number
  spellVamp: number
  omnivampItems: number
  hpRegen: number
  sortValue: number
}

export function attributeSustain(
  c: ChampCareerStats,
  itemOmnivamp: number,
): SustainAttribution {
  const healAlly = c.healOnTeammates || 0
  const shieldAlly = c.shieldOnTeammates || 0
  const supportTotal = healAlly + shieldAlly
  const lifeSteal = c.lifeSteal || 0
  const spellVamp = c.spellVamp || 0
  const omnivampItems = itemOmnivamp
  const hpRegen = c.hpRegen || 0
  const sortValue =
    supportTotal + hpRegen * 30 + (lifeSteal + spellVamp + omnivampItems * 100) * 20
  return {
    healAlly,
    shieldAlly,
    supportTotal,
    lifeSteal,
    spellVamp,
    omnivampItems,
    hpRegen,
    sortValue,
  }
}

/** Format Touch audit for tooltip / details (Zaahen-style). */
export function formatGrubTouchAudit(audit: GrubTouchAudit): string {
  const residualLine = audit.residualTrusted
    ? `residual (trusted): ${Math.round(audit.residualTurret ?? 0)} · Touch share ${(
        (audit.touchShare ?? 0) * 100
      ).toFixed(1)}%`
    : `residual: untrusted (turret feed ${Math.round(audit.turretDmg)} is mixed — not turret−Touch)`
  const lines = [
    `model ${audit.modelVersion} · confidence ${audit.confidence}`,
    `stacks ${audit.stacks} · ${audit.role} · ${audit.tick} true / ${audit.tickInterval}s → ${audit.trueDps} DPS`,
    `full cycle (4s): ${audit.cycleTrueDmg} true`,
    `Touch true (estimated): ${Math.round(audit.touchTrue)}`,
    `burn uptime: ${audit.burnUptimeSec.toFixed(1)}s`,
    `refreshes: ${audit.refreshAa} clean AA · skill-veto ${audit.rejectedSkill} · size-reject ${audit.rejectedAbility} · far ${audit.rejectedFar} · mite ${audit.refreshMite}`,
    residualLine,
    `plate progress: ${audit.plateProgressGold.toFixed(1)}g of ${audit.plateGold}g / ${audit.plateHp} HP plate`,
    audit.hungerActive
      ? `Hunger active · mite procs (model): ${audit.hungerProcs}`
      : 'Hunger inactive',
    `brief ${GRUB.preferredSiegeSeconds}s ceiling (scenario, no mite): ${audit.briefCeilingTrue} true ≈ ${audit.briefCeilingPlateGold.toFixed(1)}g`,
    audit.flags.length ? `flags: ${audit.flags.join(', ')}` : '',
    '',
    'Assumptions:',
    ...audit.assumptions.map((a) => `• ${a}`),
  ]
  return lines.filter(Boolean).join('\n')
}
