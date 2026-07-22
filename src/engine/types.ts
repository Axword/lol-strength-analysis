export type DamageType = 'physical' | 'magical' | 'true'

export type AbilitySlot = 'P' | 'Q' | 'W' | 'E' | 'R' | 'AA'

export type ChampionForm = 'mini' | 'mega'

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
  /**
   * Attack-speed ratio for bonus AS%. When omitted, theorycraft falls back to
   * `attackspeed` (documented approximation for kits without Meraki ratio).
   */
  attackspeedratio?: number
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
  /**
   * Champion attack-speed ratio used to convert bonus AS% (items/Hextech/growth)
   * into attacks/sec. Live-pinned AS ignores further ratio math.
   */
  attackSpeedRatio: number
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

/**
 * Optional execution timing for the bounded timed-manual-1v1 planner.
 * Absent fields receive deterministic conservative defaults in rotation.ts /
 * combat.ts. Does not affect the aggregate-window path.
 */
export interface AbilityExecutionTiming {
  /** Seconds the caster is locked after starting this action. */
  castLockSec?: number
  /** Delay from action start to damage impact. */
  impactDelaySec?: number
  /** Resets the auto-attack timer (e.g. Darius W). */
  attackReset?: boolean
  /**
   * Empowered auto: the ability damage packet already includes the AA
   * portion — do not emit a separate base-AD AA for the same hit.
   */
  empoweredAuto?: boolean
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
  /** Optional form/state gate for generated kits (for example Gnar R). */
  available?: (ctx: AbilityContext) => boolean
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
  /** Optional timed-execution metadata (manual 1v1 planner only). */
  execution?: AbilityExecutionTiming
}

export interface AbilityContext {
  mode: TradeMode
  ranks: AbilityRanks
  /** @deprecated use ranks — kept for transitional call sites */
  abilityRank: number
  hasEngagerAdvantage: boolean
  /** Explicit champion form when a kit has mutually exclusive packets. */
  form?: ChampionForm
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
  /** Explicit form for form-dependent kits; absent uses the kit's documented default. */
  form?: ChampionForm
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
  /**
   * Optional theorycraft fight length in seconds.
   * When set, overrides the preset window for `mode` (autos, casts, DoTs).
   */
  durationSec?: number
  /**
   * Fraction of attack-speed autos that actually land (0–1).
   * Models kiting / disengage — default 1.
   */
  aaUptime?: number
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
  /** Deterministic enemy target receiving this fighter's single-target packets. */
  targetIndex?: number
}

export interface TargetResult {
  index: number
  championId: string
  championName: string
  hpStart: number
  hpMax: number
  incomingDamage: number
  sustainHeal: number
  damageReduction: number
  hpRemaining: number
  killed: boolean
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
  /** Effective outgoing damage from this side into the opposing focus target. */
  damagePctOfEnemy: number
  /** Whether this side killed an opposing target; targets[] remains own health. */
  kills: boolean
  lockedOut: boolean
  avgXh?: number
  /** Utility this side applied onto the enemy (slows, shred, …) */
  outgoingUtility?: ResolvedUtility
  /** Utility applied onto this side by the enemy */
  incomingUtility?: ResolvedUtility
  /** Target-by-target post-sustain results under the declared focus policy. */
  targets?: TargetResult[]
  /** Index in the opposing living roster receiving this side's damage. */
  focusTargetIndex?: number
  /** Per-owner defensive utility; never max-merged across a team pool. */
  defensiveUtilityByTarget?: ResolvedUtility[]
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

/** How damage was scheduled for this matchup result. */
export type CombatResolutionMethod = 'timed_manual_1v1' | 'aggregate_window'

/**
 * One scheduled / executed combat action for later UI timelines.
 * All times are seconds from fight start; impactSec <= requested window.
 */
export interface TimedCombatEvent {
  side: 'blue' | 'red'
  fighterIndex: number
  slot: AbilitySlot
  source: string
  castIndex: number
  startSec: number
  impactSec: number
  attackReset?: boolean
  /** Raw pre-mitigation damage at impact (omitted for non-damaging markers). */
  raw?: number
  /** True when this event was suppressed because the caster already died. */
  suppressed?: boolean
}

/**
 * Serializable event-timing contract for MatchupResult.
 * Optional / backward-safe — older consumers ignore it.
 */
export interface MatchupTimingResult {
  method: CombatResolutionMethod
  /** Requested theorycraft / mode window (seconds). */
  requestedDurationSec: number
  /** Elapsed time actually resolved (may end early on lethal). */
  executedDurationSec: number
  /** When the fight stopped resolving (death or window end). */
  resolvedSec?: number
  /** First moment any living focus target reached <= 0 HP (pre-end sustain). */
  firstLethalSec?: number
  blueDeathSec?: number
  redDeathSec?: number
  events: TimedCombatEvent[]
  /** Deterministic, stable-sorted caveat codes / short phrases. */
  caveats: string[]
}

export interface MatchupResult {
  blue: SideResult
  red: SideResult
  winner: 'blue' | 'red' | 'draw'
  /**
   * Heuristic blue ranking score in [0, 1] (with pRed ≈ 1 − pBlue).
   * Not a calibrated win probability, odds, or chance — UI must not present it as %.
   */
  pBlue?: number
  pRed?: number
  /** Runtime model-confidence contract; calibrated is always false today. */
  modelTrust?: import('./modelTrust').MatchupModelTrust
  notes: string[]
  xhMode: XhMode
  strengthBand?: StrengthBand
  /** Dodge-envelope SSKP bands (not xhMode remakes). */
  xhDodgeBand?: XhDodgeBands
  /** Which dodge cell matches packet Expected scalar (typical vs NE mix). */
  xhPacketPolicy?: 'typical' | 'mix'
  /** Leftover-HP% winner (legacy poke metric) — not used as primary verdict */
  tradeHpWinner?: 'blue' | 'red' | 'draw'
  /** Theorycraft assumptions shown under the result (item procs, duration, …) */
  assumptions?: string[]
  /** Serializable cast/attack timing (timed manual 1v1 or aggregate fallback). */
  timing?: MatchupTimingResult
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
