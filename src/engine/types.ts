export type DamageType = 'physical' | 'magical' | 'true'

export type AbilitySlot = 'P' | 'Q' | 'W' | 'E' | 'R' | 'AA'

export interface ChampionBaseStats {
  hp: number
  hpperlevel: number
  mp: number
  mpperlevel: number
  movespeed: number
  armor: number
  armorperlevel: number
  spellblock: number
  spellblockperlevel: number
  attackrange: number
  hpregen: number
  hpregenperlevel: number
  mpregen: number
  mpregenperlevel: number
  crit: number
  critperlevel: number
  attackdamage: number
  attackdamageperlevel: number
  attackspeedperlevel: number
  attackspeed: number
}

export interface DamagePacket {
  raw: number
  type: DamageType
  source: string
  slot: AbilitySlot
  skillshot?: boolean
  xH?: number
  rawBeforeXh?: number
  fighterIndex?: number
  /** Skipped due to HP budget / death */
  omitted?: boolean
}

export interface CombatStats {
  level: number
  /** Current HP at fight start (live) or max HP (theorycraft) */
  hp: number
  /** Max HP for reference */
  hpMax: number
  armor: number
  mr: number
  ad: number
  ap: number
  attackSpeed: number
  critChance: number
  critDamage: number
  lethality: number
  armorPenPercent: number
  magicPenFlat: number
  magicPenPercent: number
  healShieldPower: number
  omnivamp: number
  abilityHaste: number
  range: number
  movespeed: number
  /** Base AD at this level (for bonus-AD ratios) */
  baseAd: number
  /** HP regen per second (champ + items) */
  hpRegen: number
}

export interface AbilityRanks {
  Q: number
  W: number
  E: number
  R: number
}

export interface AbilityUtility {
  /** Enemy movespeed slow fraction 0–1 (Zilean E, Nasus W, …) */
  enemySlow?: number
  /** Enemy attack-speed slow fraction 0–1 (Nasus W wither) */
  enemyAsSlow?: number
  /** Stun / root / knockup / suppression in the trade window */
  hardCc?: boolean
  /** Self or ally MS buff fraction 0–1 (Zilean E on ally) */
  selfMsBuff?: number
  /** Armor reduction applied to the target for this fight 0–1 */
  armorShred?: number
  /** Magic resist reduction applied to the target 0–1 */
  mrShred?: number
  /** Extra damage dealt while the effect holds 0–1 */
  damageAmp?: number
  /** Self damage reduction 0–1 (Garen W, etc.) */
  damageReduction?: number
  /** Marks engage / soft-lock CC (pull, knock-up engage, …) */
  engageCc?: boolean
}

/**
 * Aggregated utility affecting one side during the trade.
 * Utility-only casts (0 damage) still contribute here — never skip them.
 */
export interface ResolvedUtility {
  enemySlow: number
  enemyAsSlow: number
  hardCc: boolean
  selfMsBuff: number
  armorShred: number
  mrShred: number
  damageAmp: number
  damageReduction: number
  sources: string[]
}

export interface AbilityDefinition {
  slot: Exclude<AbilitySlot, 'AA' | 'P'>
  name: string
  range: number
  cooldown: number
  skillshot: boolean
  /** Skillshot missile width (uu); overrides range-band default when set. */
  missileWidth?: number
  /** Skillshot missile speed (uu/s); overrides range-band default when set. */
  missileSpeed?: number
  /** Pre-missile cast / delay (s); overrides estimateXh default when set. */
  releaseDelaySec?: number
  /** Max missile travel (uu); defaults to `range` when unset. */
  missileMaxTravelUu?: number
  engageCc?: boolean
  /**
   * Non-damage fight effects. Required for slows/CC even when `damage` is empty.
   * Wiki generators must keep abilities that only populate this field.
   */
  utility?:
    | AbilityUtility
    | ((
        attacker: CombatStats,
        defender: CombatStats,
        ctx: AbilityContext,
      ) => AbilityUtility)
  damage: (
    attacker: CombatStats,
    defender: CombatStats,
    ctx: AbilityContext,
  ) => DamagePacket[]
}

export interface AbilityContext {
  mode: TradeMode
  ranks: AbilityRanks
  /** @deprecated use ranks — kept for transitional call sites */
  abilityRank: number
  hasEngagerAdvantage: boolean
}

export interface ChampionDefinition {
  id: string
  name: string
  title: string
  tags: string[]
  stats: ChampionBaseStats
  passiveName: string
  abilities: AbilityDefinition[]
  passiveDamage?: (
    attacker: CombatStats,
    defender: CombatStats,
    ctx: AbilityContext,
  ) => DamagePacket[]
  autoAttacksInTrade: (mode: TradeMode) => number
}

export interface ItemDefinition {
  id: string
  name: string
  gold: number
  category: 'starter' | 'boots' | 'damage' | 'tank' | 'fighter' | 'mage'
  stats: Partial<{
    ad: number
    ap: number
    hp: number
    mana: number
    armor: number
    mr: number
    attackSpeed: number
    critChance: number
    lethality: number
    armorPenPercent: number
    magicPenFlat: number
    magicPenPercent: number
    abilityHaste: number
    movespeed: number
    omnivamp: number
  }>
  onAbilityMagic?: number
  onAbilityPhysical?: (ad: number) => number
}

export interface RuneDefinition {
  id: string
  name: string
  tree: 'Domination' | 'Precision' | 'Sorcery' | 'Resolve' | 'Inspiration'
  description: string
  riotId?: number
  slug?: string
  isKeystone?: boolean
  /** Present only for Unsealed Spellbook (8360) */
  spellbook?: {
    kind: 'unsealed_spellbook'
    initialSwapCooldownSec: number
    minSwapCooldownSec: number
    swapCooldownReductionOnSummonerCastSec: number
    uniqueSummonersOnly: boolean
    replacesOneSummonerSlot: boolean
    offerCount: number
    notes: string[]
  }
  tradeBonus?: (
    attacker: CombatStats,
    defender: CombatStats,
    mode: TradeMode,
  ) => DamagePacket[]
}

export type TradeMode = 'short' | 'allin' | 'extended'

export interface FighterLoadout {
  championId: string
  level: number
  itemIds: string[]
  runeId: string | null
  /** Per-ability ranks from timeline / manual edit */
  ranks: AbilityRanks
  /**
   * @deprecated Prefer `ranks`. Still accepted as a fallback when ranks omitted.
   */
  abilityRank?: number
  alive?: boolean
  /** Current HP fraction 0–1 at fight start */
  hpPct?: number
  liveStats?: Partial<
    Pick<
      CombatStats,
      'hp' | 'hpMax' | 'armor' | 'mr' | 'ad' | 'ap' | 'attackSpeed' | 'movespeed'
    >
  >
  position?: { x: number; y: number }
  /** Equipped summoner spells (DDragon keys), e.g. ['Flash','Ignite'] */
  summonerSpells?: [string, string]
  /** Seconds until Flash available; 0 = ready. Undefined = unknown CD. */
  flashCdRemainingSec?: number
  /** Override dash readiness for xH (kit CD / timeline). */
  dashReady?: boolean
  /** Dash charges remaining for multi-dash kits. */
  dashChargesRemaining?: number
  /** Cleanse/QSS CD remaining; 0 = ready. */
  ccBreakCdRemainingSec?: number
  /** Explicit Ghost buff active (timeline); not inferred from spell alone. */
  ghostActive?: boolean
  /** Override hard CC for xH when utility merge misses it. */
  crowdControlled?: boolean
  /** Unsealed Spellbook swap state when keystone is Spellbook */
  spellbookState?: {
    /** Summoners currently offered by the book */
    offered: string[]
    /** Seconds until next swap is available */
    swapCooldownRemainingSec: number
    swapsUsed: number
  }
}

export type XhMode = 'off' | 'expected' | 'hit_all' | 'miss_shots'

export interface MatchupInput {
  blue: FighterLoadout[]
  red: FighterLoadout[]
  engager: 'blue' | 'red' | 'neither'
  mode: TradeMode
  xhMode?: XhMode
  /** Live objective state for both sides (dragons/baron/elder/grubs…) */
  objectives?: {
    blue: import('./objectives').TeamObjectives
    red: import('./objectives').TeamObjectives
    gameTimeSec: number
  }
  /** Optional vision wards for softVision (combat ↔ overlay parity). */
  wards?: import('./vision').VisionWard[]
}

export interface FighterResult {
  index: number
  championId: string
  championName: string
  stats: CombatStats
  packets: DamagePacket[]
  rawTotal: number
  mitigatedTotal: number
  lockedOut: boolean
  avgXh?: number
  /** Abilities omitted due to low HP budget */
  omittedSlots?: AbilitySlot[]
  dead?: boolean
}

export interface SideResult {
  side: 'blue' | 'red'
  label: string
  fighters: FighterResult[]
  stats: CombatStats
  packets: DamagePacket[]
  rawTotal: number
  mitigatedTotal: number
  hpRemaining: number
  hpRemainingPct: number
  damagePctOfEnemy: number
  kills: boolean
  lockedOut: boolean
  avgXh?: number
  /** Utility this side applied onto the enemy (slows, shred, …) */
  outgoingUtility?: ResolvedUtility
  /** Utility applied onto this side by the enemy */
  incomingUtility?: ResolvedUtility
}

export interface StrengthBand {
  hitAll: {
    blueHpPct: number
    redHpPct: number
    winner: 'blue' | 'red' | 'draw'
    pBlue?: number
  }
  expected: {
    blueHpPct: number
    redHpPct: number
    winner: 'blue' | 'red' | 'draw'
    pBlue?: number
  }
  missShots: {
    blueHpPct: number
    redHpPct: number
    winner: 'blue' | 'red' | 'draw'
    pBlue?: number
  }
}

export interface XhDodgeBands {
  worst: number
  typical: number
  best: number
  mix?: number
}

export interface MatchupResult {
  blue: SideResult
  red: SideResult
  winner: 'blue' | 'red' | 'draw'
  /** Calibrated P(blue wins fight) when scoreboard is present */
  pBlue?: number
  pRed?: number
  notes: string[]
  xhMode: XhMode
  strengthBand?: StrengthBand
  /** Dodge-envelope SSKP bands (not xhMode remakes). */
  xhDodgeBand?: XhDodgeBands
  /** Which dodge cell matches packet Expected scalar (typical vs NE mix). */
  xhPacketPolicy?: 'typical' | 'mix'
  /** Leftover-HP% winner (legacy poke metric) — not used as primary verdict */
  tradeHpWinner?: 'blue' | 'red' | 'draw'
}

export function normalizeRanks(
  ranks?: Partial<AbilityRanks> | null,
  fallback = 1,
): AbilityRanks {
  return {
    Q: clampRank(ranks?.Q ?? fallback, 5),
    W: clampRank(ranks?.W ?? fallback, 5),
    E: clampRank(ranks?.E ?? fallback, 5),
    R: clampRank(ranks?.R ?? Math.min(3, fallback), 3),
  }
}

function clampRank(n: number, max: number): number {
  if (!Number.isFinite(n) || n < 0) return 0
  return Math.min(max, Math.max(0, Math.floor(n)))
}

export function rankOf(ctx: AbilityContext, slot: keyof AbilityRanks): number {
  const r = ctx.ranks?.[slot]
  if (r != null && r > 0) return r
  if (slot === 'R') return Math.min(3, Math.max(0, ctx.abilityRank))
  return Math.max(1, ctx.abilityRank)
}

export function bonusAd(attacker: CombatStats): number {
  return Math.max(0, attacker.ad - attacker.baseAd)
}
