/**
 * Gated / action-aligned kill-window overlay.
 *
 * Research-proven point-process path shared by the crosscheck harness and
 * product simulateKillWindow. Experimental until separate calibration —
 * never win odds / never calculatorReady.
 *
 * Imports simulateMatchup from combat (combat must not import this module).
 */
import { simulateMatchup } from './combat'
import { classifyMatchupModelTrust } from './modelTrust'
import { resolveFightDuration } from './fightDuration'
import type {
  FighterLoadout,
  KillWindowActionMark,
  KillWindowMarkSelection,
  MatchupInput,
  MatchupResult,
  MatchupTimingResult,
  XhMode,
} from './types'

export type { KillWindowActionMark, KillWindowMarkSelection } from './types'

function loadoutAlive(f: FighterLoadout): boolean {
  if (f.alive === false) return false
  if (f.hpPct != null && f.hpPct <= 0) return false
  if (f.liveStats?.hp != null && f.liveStats.hp <= 0) return false
  return true
}

export type KillWindowFinishAa = {
  afterLastMark?: boolean
  maxAa?: number
  aaAtEachMark?: boolean
  /** Only apply finish AAs within this many sec before killOffsetSec (0 = until end) */
  windowSec?: number
}

export type KillWindowSeriesOptions = {
  atk: FighterLoadout
  def: FighterLoadout
  /** Sample times (and optional truth HP for series alignment only) */
  actual: { tSec: number; hp: number; hpMax?: number }[]
  marks: KillWindowActionMark[]
  castPulseSec?: number
  /** Hold defender HP flat until this offset (gate idle) */
  engageSec?: number | null
  idleHp?: number | null
  /**
   * Pre-engage idle honesty: mirror observed victim HP until engageSec, then
   * start combat from actual HP at engage (not frozen window-start HP).
   * Default false preserves freeze-idle. Research earlyBand lift — not invent.
   */
  idleFollowActual?: boolean
  aaFiller?: boolean
  maxAaBetweenMarks?: number
  /** Default share for ally marks when mark.share unset */
  allyPulseShare?: number
  finishAa?: KillWindowFinishAa
  killOffsetSec?: number | null
  perSlotPulse?: boolean
  pulseBySlot?: Record<number, number>
  /** xH for cast pulses — default off (research parity) */
  xhMode?: XhMode
  /** Optional per-mark loadouts (same order as post-engage filtered marks) */
  markLoadouts?: Array<{ atk: FighterLoadout; def: FighterLoadout } | null>
}

/** Log-matchable model action emitted by the simulator (action-replay GOAL). */
export type KillWindowModelAction = {
  tSec: number
  actorClass: 'killer' | 'ally'
  kind: 'skill' | 'aa' | 'item' | 'summoner'
  skillSlot?: number
  shareHint?: number
}

export type KillWindowSeriesResult = {
  model: { tSec: number; hp: number }[]
  firstLethalSec: number | null
  markCount: number
  method: 'kill_window_gate_action'
  /** What the simulator actually applied — pulses/AA at marks, finish AA (action-replay GOAL). */
  modelActions: KillWindowModelAction[]
}

export type SelectMarksInput = {
  marks: KillWindowActionMark[]
  selection: KillWindowMarkSelection
  engageSec?: number | null
  /** Victim HP samples — only used by near_hp_drop / cusum engage helpers */
  actual?: { tSec: number; hp: number }[]
  markNearDropSec?: number
  markDropMinHp?: number
  markAlwaysNearKillSec?: number
  killOffsetSec?: number | null
  cusumK?: number
  cusumH?: number
  /**
   * Min gap between kept killer marks (disclosed throttle; not a damage coeff).
   * Ally marks unaffected. 0 = keep all.
   * When markDensityWindowSec > 0, gap applies only inside high-density clusters.
   */
  markMinGapSec?: number
  /**
   * When killOffsetSec is known, keep only killer marks in the last N seconds
   * before the kill event (plus finish_window). 0 = off. Uses kill event time,
   * not HP-drop peeking.
   */
  markFinishHorizonSec?: number
  /** Keep at most N most-recent killer marks (0 = off). */
  maxKillerMarks?: number
  /**
   * Rolling window (sec) for density-triggered throttle. 0 = classic global
   * markMinGap (research BEST). When >0 with markMinGapSec>0, min-gap only
   * applies when local killer-mark count in the window exceeds
   * markDenseMaxPerWindow. Low-density poke keeps all post-engage marks.
   */
  markDensityWindowSec?: number
  /**
   * Max killer marks in markDensityWindowSec before min-gap activates.
   * Default 1 ⇒ more than one mark per window is "dense" (spam).
   */
  markDenseMaxPerWindow?: number
  /**
   * R23/R35: retain last real killer skill in [engage−N, engage) so CUSUM
   * lag does not drop the tripping cast (e.g. Galio W). 0 = off.
   */
  preEngageOpenerSec?: number
  /**
   * Sparse gate: only inject opener when post-engage killer mark count ≤ N.
   * 0 = always inject when openerSec>0 (naive; hurts dense chains).
   */
  preEngageOpenerMaxPostMarks?: number
  /**
   * R39: pulse share for sparse preEngageOpener marks (0–1]. Default 1.
   * Attenuates opener cast damage without dropping the mark.
   */
  preEngageOpenerShare?: number
  /**
   * When set, only these skillSlots receive preEngageOpenerShare; other opener
   * slots keep share 1. Empty/absent ⇒ all opener slots use openerShare.
   * Product: [2] attenuates Galio W without touching S1 Vayne Q openers.
   */
  preEngageOpenerShareSlots?: number[]
  /**
   * R24/R35: keep killer marks in [engage−lead, engage) at full share.
   * 0 = off. Independent of openerSec (lead can replace opener).
   */
  markPreEngageLeadSec?: number
  /**
   * R24/R35: keep earlier real killer skills in (engage−far, engage−lead]
   * with attenuated share. 0 = off.
   */
  markPreEngageFarSec?: number
  /** Far-window pulse share (0–1]. Default 0.35. Never invents marks. */
  markPreEngageFarShare?: number
  /**
   * When true (default for opener-only), shift returned engageSec to the
   * retained near opener so idle/AA gate starts on the real cast.
   * Far poke leaves CUSUM engage intact (AA filler stays post-CUSUM).
   */
  preEngageShiftEngageToOpener?: boolean
}

export type SelectMarksResult = {
  marks: KillWindowActionMark[]
  engageSec: number | null
  selection: KillWindowMarkSelection
  /** CUSUM / input engage before any opener shift (AA-gate reference). */
  cusumEngageSec?: number | null
  keptReasons: Array<{
    tSec: number
    skillSlot: number
    ally: boolean
    keptReason:
      | 'drop'
      | 'finish_window'
      | 'post_engage'
      | 'no_filter'
      | 'idle_skip'
      | 'pre_engage_opener'
      | 'pre_engage_lead'
      | 'pre_engage_far'
  }>
}

function cloneLoadout(l: FighterLoadout): FighterLoadout {
  return {
    ...l,
    ...(l.ranks ? { ranks: { ...l.ranks } } : {}),
    itemIds: [...l.itemIds],
    liveStats: l.liveStats ? { ...l.liveStats } : undefined,
  }
}

function withHp(l: FighterLoadout, hp: number): FighterLoadout {
  const c = cloneLoadout(l)
  if (c.liveStats) c.liveStats.hp = Math.max(0, hp)
  return c
}

/** Physical AA damage from live AD/armor pins (no invented stats). */
export function killWindowPhysicalAaDamage(
  atk: FighterLoadout,
  def: FighterLoadout,
): number {
  const ad = atk.liveStats?.ad ?? 0
  const armor = def.liveStats?.armor ?? 0
  if (ad <= 0) return 0
  return ad * (100 / (100 + Math.max(0, armor)))
}

/** One cast-pulse of simulateMatchup damage × share. */
export function killWindowPulseDamage(
  atk: FighterLoadout,
  def: FighterLoadout,
  pulseSec: number,
  share = 1,
  xhMode: XhMode = 'off',
): number {
  if (pulseSec <= 0 || share <= 0) return 0
  const start = def.liveStats?.hp ?? 0
  if (start <= 0) return 0
  // Continuous pulse only — strip killWindow to avoid recursion.
  const r = simulateMatchup({
    blue: [atk],
    red: [def],
    engager: 'blue',
    mode: 'extended',
    durationSec: Math.max(0.05, pulseSec),
    xhMode,
  })
  const end = r.red.targets?.[0]?.hpRemaining ?? 0
  return Math.max(0, (start - end) * share)
}

/** CUSUM engage on observed HP drops (opt-in; not product mark filter). */
export function cusumEngageSec(
  actual: { tSec: number; hp: number }[],
  k = 8,
  h = 45,
): number | null {
  if (actual.length < 3) return null
  let s = 0
  for (let i = 1; i < actual.length; i++) {
    const dmg = Math.max(0, actual[i - 1]!.hp - actual[i]!.hp)
    s = Math.max(0, s + dmg - k)
    if (s >= h) return actual[i]!.tSec
  }
  return null
}

/**
 * Select action marks. Product default must be non-drop
 * (`post_engage_killer_skills` or `cusum_engage_then_skills`).
 * `near_hp_drop` is research/attribution only.
 */
export function selectKillWindowMarks(input: SelectMarksInput): SelectMarksResult {
  const {
    marks: raw,
    selection,
    engageSec: engageIn = null,
    actual = [],
    markNearDropSec = 0.75,
    markDropMinHp = 15,
    markAlwaysNearKillSec = 1.5,
    killOffsetSec = null,
    cusumK = 8,
    cusumH = 45,
    markMinGapSec = 0,
    markFinishHorizonSec = 0,
    maxKillerMarks = 0,
    markDensityWindowSec = 0,
    markDenseMaxPerWindow = 1,
    preEngageOpenerSec = 0,
    preEngageOpenerMaxPostMarks = 0,
    preEngageOpenerShare = 1,
    preEngageOpenerShareSlots = undefined as number[] | undefined,
    markPreEngageLeadSec = 0,
    markPreEngageFarSec = 0,
    markPreEngageFarShare = 0.35,
    preEngageShiftEngageToOpener = true,
  } = input

  let engageSec = engageIn
  if (selection === 'cusum_engage_then_skills') {
    engageSec = cusumEngageSec(actual, cusumK, cusumH) ?? engageIn
  }
  const cusumEngageSecKept = engageSec

  const sorted = [...raw].sort((a, b) => a.tSec - b.tSec)
  const keptReasons: SelectMarksResult['keptReasons'] = []
  let marks: KillWindowActionMark[] = []

  if (selection === 'near_hp_drop') {
    // Research/attribution: do not pre-filter by engage here — gate idle in
    // simulateKillWindowSeries owns post-engage timing.
    const dropTimes: number[] = []
    for (let i = 1; i < actual.length; i++) {
      const d = actual[i - 1]!.hp - actual[i]!.hp
      if (d >= markDropMinHp) dropTimes.push(actual[i]!.tSec)
    }
    const killT = killOffsetSec ?? Infinity
    for (const m of sorted) {
      if (
        !m.ally &&
        markAlwaysNearKillSec > 0 &&
        Number.isFinite(killT) &&
        m.tSec >= killT - markAlwaysNearKillSec &&
        m.tSec <= killT + 0.5
      ) {
        marks.push(m)
        keptReasons.push({
          tSec: m.tSec,
          skillSlot: m.skillSlot ?? 0,
          ally: !!m.ally,
          keptReason: 'finish_window',
        })
        continue
      }
      if (dropTimes.some((dt) => Math.abs(dt - m.tSec) <= markNearDropSec)) {
        marks.push(m)
        keptReasons.push({
          tSec: m.tSec,
          skillSlot: m.skillSlot ?? 0,
          ally: !!m.ally,
          keptReason: 'drop',
        })
      }
    }
  } else {
    // Product-safe: all post-engage killer (and optional ally) skills — no HP-drop peek.
    // Finish-window / finish-horizon use kill *event* time (when known), not HP drops.
    const killT = killOffsetSec ?? Infinity
    for (const m of sorted) {
      const inFinish =
        !m.ally &&
        markAlwaysNearKillSec > 0 &&
        Number.isFinite(killT) &&
        m.tSec >= killT - markAlwaysNearKillSec &&
        m.tSec <= killT + 0.5
      const inHorizon =
        !m.ally &&
        markFinishHorizonSec > 0 &&
        Number.isFinite(killT) &&
        m.tSec >= killT - markFinishHorizonSec &&
        m.tSec <= killT + 0.5
      if (
        !inFinish &&
        !inHorizon &&
        engageSec != null &&
        m.tSec < engageSec - 1e-9
      ) {
        continue
      }
      if (
        markFinishHorizonSec > 0 &&
        Number.isFinite(killT) &&
        !m.ally &&
        !inHorizon &&
        !inFinish
      ) {
        // Horizon mode: drop early post-engage spam outside the finish horizon.
        continue
      }
      marks.push(m)
      keptReasons.push({
        tSec: m.tSec,
        skillSlot: m.skillSlot ?? 0,
        ally: !!m.ally,
        keptReason: inFinish || inHorizon ? 'finish_window' : 'post_engage',
      })
    }

    // Pre-engage retain (real skill_used only — never invent). Near lead / opener
    // at full share; far poke attenuated. Sparse maxPost skips dense Olaf chains.
    const preEngageOn =
      preEngageOpenerSec > 0 ||
      markPreEngageLeadSec > 0 ||
      markPreEngageFarSec > 0
    if (engageSec != null && preEngageOn) {
      const preEngageSec = engageSec
      const postKillerCount = marks.filter((m) => !m.ally).length
      const leadSec = Math.max(0, markPreEngageLeadSec, preEngageOpenerSec)
      const farSec = Math.max(0, markPreEngageFarSec)
      const farShare = Math.min(1, Math.max(0, markPreEngageFarShare))
      const sparseOk =
        preEngageOpenerMaxPostMarks <= 0 ||
        postKillerCount <= preEngageOpenerMaxPostMarks
      const already = new Set(
        marks.map(
          (m) =>
            `${m.tSec.toFixed(4)}|${m.skillSlot ?? 0}|${m.ally ? 1 : 0}`,
        ),
      )
      const preCandidates = sorted.filter(
        (m) =>
          !m.ally &&
          (m.kind ?? 'skill') === 'skill' &&
          m.tSec < preEngageSec - 1e-9,
      )

      if (sparseOk && leadSec > 0) {
        const near = preCandidates.filter(
          (m) => m.tSec >= preEngageSec - leadSec - 1e-9,
        )
        // Opener mode (no explicit lead): keep only the last near cast.
        const nearKeep =
          markPreEngageLeadSec > 0
            ? near
            : near.length
              ? [near[near.length - 1]!]
              : []
        const openerShare = Math.min(
          1,
          Math.max(
            0,
            Number.isFinite(preEngageOpenerShare) ? preEngageOpenerShare : 1,
          ),
        )
        const slotFilter =
          preEngageOpenerShareSlots && preEngageOpenerShareSlots.length > 0
            ? new Set(preEngageOpenerShareSlots)
            : null
        for (const m of nearKeep) {
          const key = `${m.tSec.toFixed(4)}|${m.skillSlot ?? 0}|0`
          if (already.has(key)) continue
          already.add(key)
          // Lead mode keeps full share; sparse opener may attenuate (R39).
          let share: number
          if (markPreEngageLeadSec > 0) {
            share = m.share ?? 1
          } else if (slotFilter && !slotFilter.has(m.skillSlot ?? -1)) {
            share = m.share ?? 1
          } else if (Number.isFinite(m.share)) {
            share = Math.min(1, Math.max(0, m.share as number))
          } else {
            share = openerShare
          }
          marks.push({ ...m, share })
          keptReasons.push({
            tSec: m.tSec,
            skillSlot: m.skillSlot ?? 0,
            ally: false,
            keptReason:
              markPreEngageLeadSec > 0 ? 'pre_engage_lead' : 'pre_engage_opener',
          })
        }
      }

      if (sparseOk && farSec > leadSec && farShare > 0) {
        const far = preCandidates.filter(
          (m) =>
            m.tSec >= preEngageSec - farSec - 1e-9 &&
            m.tSec < preEngageSec - leadSec - 1e-9,
        )
        for (const m of far) {
          const key = `${m.tSec.toFixed(4)}|${m.skillSlot ?? 0}|0`
          if (already.has(key)) continue
          already.add(key)
          marks.push({ ...m, share: m.share ?? farShare })
          keptReasons.push({
            tSec: m.tSec,
            skillSlot: m.skillSlot ?? 0,
            ally: false,
            keptReason: 'pre_engage_far',
          })
        }
      }

      // Chronological order after injecting pre-engage marks.
      const paired = marks
        .map((m, i) => ({ m, reason: keptReasons[i]! }))
        .sort((a, b) => a.m.tSec - b.m.tSec)
      marks = paired.map((x) => x.m)
      keptReasons.length = 0
      keptReasons.push(...paired.map((x) => x.reason))

      // R23: shift idle/AA engage to near opener when no far poke retained.
      const hasFar = keptReasons.some((r) => r.keptReason === 'pre_engage_far')
      const nearOpener = keptReasons.find(
        (r) =>
          r.keptReason === 'pre_engage_opener' ||
          r.keptReason === 'pre_engage_lead',
      )
      if (
        preEngageShiftEngageToOpener &&
        !hasFar &&
        nearOpener != null &&
        engageSec != null
      ) {
        engageSec = nearOpener.tSec
      }
    }
  }

  // Disclosed killer-mark throttle (anti-spam); does not peek HP drops.
  // Density mode: min-gap only when local rate exceeds markDenseMaxPerWindow
  // in markDensityWindowSec (Cassio spam vs Ezreal spaced poke).
  // Finish-window marks (near kill event) are never gap-dropped — preserves
  // short burst lethals (Camille) while still thinning mid-fight E spam.
  if (markMinGapSec > 0 && marks.length > 1) {
    const throttled: KillWindowActionMark[] = []
    const throttledReasons: SelectMarksResult['keptReasons'] = []
    let lastKillerT = -Infinity
    const densityOn = markDensityWindowSec > 0
    const killerCandidates = marks.filter((m) => !m.ally)
    for (let i = 0; i < marks.length; i++) {
      const m = marks[i]!
      const reason = keptReasons[i]!
      if (m.ally) {
        throttled.push(m)
        throttledReasons.push(reason)
        continue
      }
      // Finish-window exempt only in density mode (product). Research global
      // min-gap must still thin finish spam so composite stays ≤0.9683 band.
      let applyGap = true
      if (densityOn) {
        if (reason.keptReason === 'finish_window') {
          applyGap = false
        } else {
          const t0 = m.tSec - markDensityWindowSec
          let local = 0
          for (const k of killerCandidates) {
            if (k.tSec > t0 + 1e-12 && k.tSec <= m.tSec + 1e-12) local++
          }
          applyGap = local > markDenseMaxPerWindow
        }
      }
      if (applyGap && m.tSec - lastKillerT + 1e-9 < markMinGapSec) continue
      throttled.push(m)
      throttledReasons.push(reason)
      lastKillerT = m.tSec
    }
    marks = throttled
    keptReasons.length = 0
    keptReasons.push(...throttledReasons)
  }

  if (maxKillerMarks > 0) {
    const killers = marks
      .map((m, i) => ({ m, i, reason: keptReasons[i]! }))
      .filter((x) => !x.m.ally)
    const allies = marks
      .map((m, i) => ({ m, i, reason: keptReasons[i]! }))
      .filter((x) => x.m.ally)
    const keptKillers = killers.slice(-maxKillerMarks)
    const merged = [...allies, ...keptKillers].sort((a, b) => a.m.tSec - b.m.tSec)
    marks = merged.map((x) => x.m)
    keptReasons.length = 0
    keptReasons.push(...merged.map((x) => x.reason))
  }

  return {
    marks,
    engageSec,
    selection,
    cusumEngageSec: cusumEngageSecKept,
    keptReasons,
  }
}

/**
 * Marked point-process overlay: damage jumps on skill marks.
 * Between marks: hold HP; optional AA filler / finish AA / AA-at-mark.
 */
export function simulateKillWindowSeries(
  opts: KillWindowSeriesOptions,
): KillWindowSeriesResult {
  const {
    atk: atk0,
    def: def0,
    actual,
    marks,
    castPulseSec = 0.4,
    engageSec = null,
    idleHp = null,
    idleFollowActual = false,
    aaFiller = false,
    maxAaBetweenMarks = 6,
    allyPulseShare = 0,
    finishAa,
    killOffsetSec = null,
    perSlotPulse = false,
    pulseBySlot = {},
    xhMode = 'off',
    markLoadouts,
  } = opts

  const finishAaAfterLastMark = finishAa?.afterLastMark ?? false
  const finishAaMax = finishAa?.maxAa ?? 4
  const finishAaWindowSec = finishAa?.windowSec ?? 0
  const aaAtEachMark = finishAa?.aaAtEachMark ?? false

  type Jump = { tSec: number; hpAfter: number }
  const jumps: Jump[] = []
  const modelActions: KillWindowModelAction[] = []
  const startIdle = idleHp ?? def0.liveStats?.hp ?? actual[0]?.hp ?? 0
  const hpAtOrBefore = (tSec: number): number => {
    let hpSample = actual[0]?.hp ?? startIdle
    for (const a of actual) {
      if (a.tSec <= tSec + 1e-9) hpSample = a.hp
      else break
    }
    return hpSample
  }
  // Truth-follow: pin combat start to observed HP at engage (level-up/regen honest).
  const combatStartHp =
    idleFollowActual && engageSec != null
      ? hpAtOrBefore(engageSec)
      : startIdle
  let hp = combatStartHp
  let firstLethalSec: number | null = null
  let lastT = engageSec != null ? engageSec : 0
  let atk = cloneLoadout(atk0)
  let def = withHp(def0, hp)

  if (idleFollowActual && engageSec != null) {
    // Pre-engage samples mirror actual in the series map below; jump only at engage.
    jumps.push({ tSec: engageSec, hpAfter: combatStartHp })
  } else {
    jumps.push({ tSec: 0, hpAfter: startIdle })
    if (engageSec != null && engageSec > 0) {
      jumps.push({ tSec: engageSec, hpAfter: startIdle })
    }
  }

  const sorted = [...marks]
    .sort((a, b) => a.tSec - b.tSec)
    .filter((m) => {
      // Item/summoner inventory marks are timed log events — keep even pre-engage
      // so action-replay can match truth without inventing damage.
      // Decode AA marks stay engage-gated like skills (idle gate must not take
      // pre-engage physical AA damage).
      // Pre-engage skill retain (share set by selectKillWindowMarks) may fire
      // before engageSec; AA filler / idleFollow still gate at engageSec.
      const kind = m.kind ?? 'skill'
      if (kind === 'item' || kind === 'summoner') return true
      if (
        kind === 'skill' &&
        m.share != null &&
        m.share > 0 &&
        engageSec != null &&
        m.tSec < engageSec - 1e-9
      ) {
        return true
      }
      if (engageSec != null && m.tSec < engageSec - 1e-9) return false
      return true
    })

  for (let mi = 0; mi < sorted.length; mi++) {
    const m = sorted[mi]!
    const tSec = m.tSec
    if (tSec < -1e-6) continue
    const actionKind = m.kind ?? 'skill'

    // Item/summoner: disclosed inventory emission. Default non-damage (shareHint=0)
    // so AA filler / finish AA / ship HP path stay unchanged. Optional kit-linked
    // pulse only when caller sets share>0 AND logOnly is not set — never HPΔ invent.
    if (actionKind === 'item' || actionKind === 'summoner') {
      const itemShare = m.logOnly === false && (m.share ?? 0) > 0 ? (m.share as number) : 0
      if (itemShare > 0 && hp > 0) {
        const pin = markLoadouts?.[mi]
        if (pin) {
          atk = cloneLoadout(pin.atk)
          def = withHp(pin.def, hp)
        }
        const slotPulse = castPulseSec
        const dmg = killWindowPulseDamage(atk, def, slotPulse, itemShare, xhMode)
        hp = Math.max(0, hp - dmg)
        def = withHp(def, hp)
        jumps.push({ tSec, hpAfter: hp })
        if (hp <= 0 && firstLethalSec == null) firstLethalSec = tSec
      }
      modelActions.push({
        tSec,
        actorClass: m.ally ? 'ally' : 'killer',
        kind: actionKind,
        shareHint: itemShare,
      })
      // Do NOT advance lastT — item inventory must not shift AA filler/finish timing.
      continue
    }

    // Evented/decode-timed AA mark: kit physical damage (shareHint>0). Not log-echo.
    // Post-lethal / zero-AD: omit modelAction (death-coupled; never shareHint=0 fake).
    if (actionKind === 'aa') {
      const pin = markLoadouts?.[mi]
      if (pin) {
        atk = cloneLoadout(pin.atk)
        def = withHp(pin.def, hp)
      }
      const aaShare = m.logOnly ? 0 : (m.share ?? 1)
      if (aaShare > 0 && hp > 0) {
        const aaDmg = killWindowPhysicalAaDamage(atk, def) * aaShare
        if (aaDmg > 0) {
          hp = Math.max(0, hp - aaDmg)
          def = withHp(def, hp)
          jumps.push({ tSec, hpAfter: hp })
          modelActions.push({
            tSec,
            actorClass: m.ally ? 'ally' : 'killer',
            kind: 'aa',
            shareHint: aaShare,
          })
          if (hp <= 0 && firstLethalSec == null) firstLethalSec = tSec
          lastT = tSec
        }
      }
      continue
    }

    const pin = markLoadouts?.[mi]
    if (pin) {
      atk = cloneLoadout(pin.atk)
      def = withHp(pin.def, hp)
    }

    if (aaFiller && tSec > lastT + 1e-6) {
      const gap = tSec - lastT
      const as = atk.liveStats?.attackSpeed ?? 0.7
      const period = 1 / Math.max(0.2, as)
      const nAa = Math.min(maxAaBetweenMarks, Math.floor(gap / period))
      const aaDmg = killWindowPhysicalAaDamage(atk, def)
      for (let i = 0; i < nAa && hp > 0; i++) {
        const hitT = lastT + (i + 1) * period
        if (hitT > tSec + 1e-9) break
        hp = Math.max(0, hp - aaDmg)
        def = withHp(def, hp)
        jumps.push({ tSec: hitT, hpAfter: hp })
        modelActions.push({
          tSec: hitT,
          actorClass: 'killer',
          kind: 'aa',
          shareHint: aaDmg > 0 ? 1 : 0,
        })
        if (hp <= 0 && firstLethalSec == null) firstLethalSec = hitT
      }
    }

    if (hp <= 0) break

    const slotPulse =
      perSlotPulse && m.skillSlot != null && m.skillSlot > 0
        ? (pulseBySlot[m.skillSlot] ?? castPulseSec)
        : castPulseSec
    const share = m.logOnly ? 0 : (m.share ?? (m.ally ? allyPulseShare : 1))
    const dmg = m.logOnly ? 0 : killWindowPulseDamage(atk, def, slotPulse, share, xhMode)
    hp = Math.max(0, hp - dmg)
    def = withHp(def, hp)
    jumps.push({ tSec, hpAfter: hp })
    modelActions.push({
      tSec,
      actorClass: m.ally ? 'ally' : 'killer',
      kind: 'skill',
      skillSlot: m.skillSlot,
      shareHint: share,
    })
    if (hp <= 0 && firstLethalSec == null) firstLethalSec = tSec

    if (aaAtEachMark && !m.ally && !m.logOnly && hp > 0) {
      const aaDmg = killWindowPhysicalAaDamage(atk, def)
      hp = Math.max(0, hp - aaDmg)
      def = withHp(def, hp)
      const aaT = tSec + 0.05
      jumps.push({ tSec: aaT, hpAfter: hp })
      modelActions.push({
        tSec: aaT,
        actorClass: 'killer',
        kind: 'aa',
        shareHint: aaDmg > 0 ? 1 : 0,
      })
      if (hp <= 0 && firstLethalSec == null) firstLethalSec = aaT
    }

    lastT = tSec
  }

  const endT = actual[actual.length - 1]?.tSec ?? lastT
  const applyTrailingAa = aaFiller || finishAaAfterLastMark
  if (applyTrailingAa && hp > 0 && endT > lastT + 1e-6) {
    let aaStart = lastT
    if (finishAaAfterLastMark && !aaFiller) {
      if (finishAaWindowSec > 0 && killOffsetSec != null) {
        aaStart = Math.max(lastT, killOffsetSec - finishAaWindowSec)
      }
    }
    const gap = endT - aaStart
    const as = atk.liveStats?.attackSpeed ?? 0.7
    const period = 1 / Math.max(0.2, as)
    const cap = finishAaAfterLastMark && !aaFiller ? finishAaMax : maxAaBetweenMarks
    const nAa = Math.min(cap, Math.floor(Math.max(0, gap) / period))
    const aaDmg = killWindowPhysicalAaDamage(atk, def)
    for (let i = 0; i < nAa && hp > 0; i++) {
      const hitT = aaStart + (i + 1) * period
      if (hitT < lastT - 1e-9) continue
      hp = Math.max(0, hp - aaDmg)
      jumps.push({ tSec: hitT, hpAfter: hp })
      modelActions.push({
        tSec: hitT,
        actorClass: 'killer',
        kind: 'aa',
        shareHint: aaDmg > 0 ? 1 : 0,
      })
      if (hp <= 0 && firstLethalSec == null) firstLethalSec = hitT
    }
  }

  modelActions.sort((a, b) => a.tSec - b.tSec)

  const model = actual.map((a) => {
    if (
      idleFollowActual &&
      engageSec != null &&
      a.tSec < engageSec - 1e-9
    ) {
      // Idle honesty: no combat invent — mirror observed HP until engage.
      return { tSec: a.tSec, hp: a.hp }
    }
    let hpAt = jumps[0]!.hpAfter
    for (const j of jumps) {
      if (j.tSec <= a.tSec + 1e-9) hpAt = j.hpAfter
      else break
    }
    return { tSec: a.tSec, hp: hpAt }
  })

  return {
    model,
    firstLethalSec,
    markCount: sorted.length,
    method: 'kill_window_gate_action',
    modelActions,
  }
}

/** Opt-in product API: gated kill-window series from marks + pins. */
export function simulateKillWindow(
  opts: KillWindowSeriesOptions & {
    /** Ally marks merged with marks (share via allyPulseShare) */
    allyMarks?: KillWindowActionMark[]
  },
): KillWindowSeriesResult {
  const allyMarks = (opts.allyMarks ?? []).map((m) => ({ ...m, ally: true }))
  const marks = [...opts.marks, ...allyMarks]
  return simulateKillWindowSeries({ ...opts, marks })
}

/**
 * Product sibling of simulateMatchup: gated / action-aligned kill window.
 * Requires known HP pins + actionMarks. Missing pins → continuous fallback
 * with disclosure notes (no invented HP/items).
 *
 * Default markSelection is post_engage_killer_skills (P-anti).
 */
export function simulateKillWindowMatchup(input: MatchupInput): MatchupResult {
  const kw = input.killWindow
  const xhMode: XhMode = input.xhMode ?? 'expected'

  if (!kw?.actionMarks?.length) {
    const { killWindow: _drop, ...rest } = input
    return simulateMatchup(rest)
  }

  const blueLiving = input.blue.filter(loadoutAlive)
  const redLiving = input.red.filter(loadoutAlive)
  const atk = blueLiving[0]
  const def = redLiving[0]
  const pinsOk =
    blueLiving.length === 1 &&
    redLiving.length === 1 &&
    atk?.liveStats?.hp != null &&
    atk.liveStats.hpMax != null &&
    def?.liveStats?.hp != null &&
    def.liveStats.hpMax != null

  if (!pinsOk || !atk || !def) {
    const { killWindow: _drop, ...rest } = input
    const fallback = simulateMatchup(rest)
    return {
      ...fallback,
      notes: [
        ...fallback.notes,
        'Kill-window refused: missing HP pins or non-1v1 — continuous fallback (no invented HP).',
      ].slice(0, 12),
    }
  }

  const durationSec = resolveFightDuration(input)
  const engageSec = kw.engageSec ?? kw.idleUntilSec ?? null
  const actual =
    kw.actualHpSeries?.length
      ? kw.actualHpSeries
      : Array.from({ length: Math.max(2, Math.ceil(durationSec) + 1) }, (_, i) => ({
          tSec: Math.min(durationSec, i),
          hp: def.liveStats!.hp!,
          hpMax: def.liveStats!.hpMax,
        }))

  const rawMarks: KillWindowActionMark[] = [
    ...(kw.actionMarks ?? []),
    ...(kw.allyMarks ?? []).map((m) => ({ ...m, ally: true as const })),
  ]

  const selection = kw.markSelection ?? 'post_engage_killer_skills'
  const selected = selectKillWindowMarks({
    marks: rawMarks,
    selection,
    engageSec,
    actual,
    killOffsetSec: kw.killOffsetSec ?? null,
    markAlwaysNearKillSec: kw.markAlwaysNearKillSec ?? 1.5,
    markMinGapSec: kw.markMinGapSec ?? 0,
    markFinishHorizonSec: kw.markFinishHorizonSec ?? 0,
    maxKillerMarks: kw.maxKillerMarks ?? 0,
    markDensityWindowSec: kw.markDensityWindowSec ?? 0,
    markDenseMaxPerWindow: kw.markDenseMaxPerWindow ?? 1,
    // R35 KEEP defaults match killWindowProduct (sparse opener).
    preEngageOpenerSec: kw.preEngageOpenerSec ?? 0.5,
    preEngageOpenerMaxPostMarks: kw.preEngageOpenerMaxPostMarks ?? 3,
    // R39 KEEP: W-slot opener attenuate (Galio); other slots full share.
    preEngageOpenerShare: kw.preEngageOpenerShare ?? 0.18,
    preEngageOpenerShareSlots: kw.preEngageOpenerShareSlots ?? [2],
    markPreEngageLeadSec: kw.markPreEngageLeadSec ?? 0,
    markPreEngageFarSec: kw.markPreEngageFarSec ?? 0,
    markPreEngageFarShare: kw.markPreEngageFarShare ?? 0.35,
    preEngageShiftEngageToOpener: kw.preEngageShiftEngageToOpener ?? true,
  })

  // AA / idle gate: prefer CUSUM when far poke retained (do not open AA filler
  // on attenuated far casts). Near-only opener may shift selected.engageSec.
  const hasFarPoke = selected.keptReasons.some(
    (r) => r.keptReason === 'pre_engage_far',
  )
  const seriesEngage =
    hasFarPoke && selected.cusumEngageSec != null
      ? selected.cusumEngageSec
      : selected.engageSec

  const series = simulateKillWindow({
    atk,
    def,
    actual,
    marks: selected.marks.filter((m) => !m.ally),
    allyMarks: selected.marks.filter((m) => m.ally),
    castPulseSec: kw.castPulseSec ?? 0.4,
    engageSec: seriesEngage,
    idleHp: def.liveStats!.hp,
    idleFollowActual: kw.idleFollowActual ?? true,
    aaFiller: kw.aaFiller ?? false,
    maxAaBetweenMarks: kw.maxAaBetweenMarks ?? 6,
    allyPulseShare: kw.allyPulseShare ?? 0,
    finishAa: kw.finishAa ?? {
      afterLastMark: true,
      maxAa: 4,
      // R30 KEEP: aa-at-mark off (finish AA retained). FA ≠ odds.
      aaAtEachMark: false,
    },
    killOffsetSec: kw.killOffsetSec ?? null,
    // R30 KEEP: R-slot pulse 0 (utility/steroid ult default).
    perSlotPulse: kw.perSlotPulse ?? true,
    pulseBySlot: kw.pulseBySlot ?? { 1: 0.4, 2: 0.35, 3: 0.55, 4: 0 },
    xhMode,
  })

  const { killWindow: _drop, ...continuousInput } = input
  const continuous = simulateMatchup(continuousInput)
  const endHp =
    series.model[series.model.length - 1]?.hp ?? def.liveStats!.hp!
  const hpStart = def.liveStats!.hp!
  const hpMax = def.liveStats!.hpMax!
  const killed = endHp <= 0 || series.firstLethalSec != null
  const redTargets = (continuous.red.targets ?? []).map((t, i) =>
    i === 0
      ? {
          ...t,
          hpStart,
          hpMax,
          hpRemaining: Math.max(0, endHp),
          incomingDamage: Math.max(0, hpStart - Math.max(0, endHp)),
          killed,
        }
      : t,
  )
  const red = {
    ...continuous.red,
    targets: redTargets,
    hpRemaining: Math.max(0, endHp),
    hpRemainingPct: hpMax > 0 ? Math.max(0, endHp) / hpMax : 0,
  }
  const blue = {
    ...continuous.blue,
    kills: killed || continuous.blue.kills,
  }

  const timing: MatchupTimingResult = {
    method: 'kill_window_gate_action',
    requestedDurationSec: durationSec,
    executedDurationSec:
      series.firstLethalSec != null
        ? Math.min(durationSec, series.firstLethalSec)
        : durationSec,
    resolvedSec:
      series.firstLethalSec != null
        ? Math.min(durationSec, series.firstLethalSec)
        : durationSec,
    firstLethalSec: series.firstLethalSec ?? undefined,
    redDeathSec: series.firstLethalSec ?? undefined,
    events: continuous.timing?.events ?? [],
    caveats: [
      'kill_window_experimental',
      `mark_selection:${selection}`,
      'not_calibrated_win_odds',
      ...(kw.allyMarks?.length
        ? []
        : ['ally_marks_absent_1v1_may_underkill']),
    ],
  }

  const modelTrust = classifyMatchupModelTrust(input)
  const notes = [
    'Kill-window path (experimental): idle-gate + action marks — model edge, not win %.',
    ...(kw.allyMarks?.length
      ? []
      : ['No ally marks: 1v1 may underkill teamfight finishes.']),
    ...continuous.notes,
  ]

  return {
    ...continuous,
    blue,
    red,
    modelTrust,
    notes: [...new Set(notes)].slice(0, 12),
    timing,
  }
}
