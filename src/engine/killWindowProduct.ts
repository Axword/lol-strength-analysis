/**
 * Product call-site helpers for the experimental kill-window path.
 * Opt-in after best.json.productShipGate === true.
 */
import type { KillWindowActionMark, KillWindowInputOptions, MatchupInput } from './types'

/**
 * Flip only after best.json.productShipGate === true.
 * Until then, map Send keeps continuous simulateMatchup.
 */
export const PRODUCT_KILL_WINDOW_OPTED_IN = true

/** Default product mark selection (P-anti: non-drop + density throttle). */
export const PRODUCT_KILL_WINDOW_DEFAULTS: Omit<
  KillWindowInputOptions,
  'actionMarks' | 'allyMarks' | 'actualHpSeries'
> = {
  markSelection: 'cusum_engage_then_skills',
  castPulseSec: 0.4,
  allyPulseShare: 0,
  /**
   * R30 KEEP: no AA-at-mark (death-coupled finish; aa-at-mark over-killed Olaf→Trundle).
   * Trailing finish AA retained. FA ≠ odds.
   */
  finishAa: { afterLastMark: true, maxAa: 4, aaAtEachMark: false },
  markAlwaysNearKillSec: 2,
  /** Density stride: thin Cassio-like spam; spaced poke keeps marks. */
  markMinGapSec: 1.0,
  markDensityWindowSec: 1.2,
  markDenseMaxPerWindow: 1,
  /**
   * R35 KEEP: sparse pre-CUSUM opener (Galio W retain). maxPost=3 skips dense
   * Olaf chains. S0 FA↑ and S1 FA↑ under R30 law — not host-gated. FA ≠ odds.
   */
  preEngageOpenerSec: 0.5,
  preEngageOpenerMaxPostMarks: 3,
  /**
   * R39 KEEP (+R41 same fix): attenuate W-slot (skillSlot=2) opener pulse only.
   * Full W+tornado overkills Galio→Trundle (|leth| 1.84→0.36); S1 Vayne Q
   * opener (slot 1) stays share=1. Prefer slot filter over Path1 host gate.
   * FA ≠ odds.
   */
  preEngageOpenerShare: 0.18,
  preEngageOpenerShareSlots: [2],
  /** R19: truth-follow idle — S0 earlyBand + S1 FA lift; FA ≠ odds. */
  idleFollowActual: true,
  /**
   * R30 KEEP: per-slot pulses with R=0 (steroid/utility ult default pulse).
   * Damage ults still resolve via Q/W/E + finish AA. Not a pin invent.
   */
  perSlotPulse: true,
  pulseBySlot: { 1: 0.4, 2: 0.35, 3: 0.55, 4: 0 },
  /**
   * R31 KEEP: burst mark-domain lead — load real killer skills from
   * [burstStart − 2.5s, burstEnd], remap onto CUSUM engage. HP burst onset
   * stays legacy (earlyBand). Lead 3.5 (includes Galio W) regresses S1.
   * Pre-engage lead stays off (R24/R31 S0 Olaf + S1 risk). FA ≠ odds.
   */
  markPreBurstSkillLeadSec: 2.5,
  markPreBurstSkillShare: 1,
  markPreEngageLeadSec: 0,
  /**
   * R42 KEEP: delay remapped pre-burst marks 0.3s after CUSUM engage.
   * Lifts c1-burst earlyMae/pathMae; marks=2 + |leth|≤0.75 preserved; S1 flat+.
   * FA ≠ odds.
   */
  markPreBurstDelaySec: 0.3,
}

/**
 * Expand burst skill load start for R31 KEEP pre-burst lead (mark domain only).
 * HP burst onset stays harness `detectBurstStartMs` / legacy walk.
 */
export function burstSkillLoadStartMs(
  burstStartMs: number,
  leadSec: number = PRODUCT_KILL_WINDOW_DEFAULTS.markPreBurstSkillLeadSec ?? 0,
): number {
  if (!(leadSec > 0)) return burstStartMs
  return burstStartMs - Math.round(leadSec * 1000)
}

/** Optional skill_used rows on a product timeline (never invented). */
export type TimelineSkillUsedEvent = {
  tMs: number
  participantId: number
  skillSlot: number
}

/**
 * Build killer/ally action marks from timeline skill_used when present.
 * Returns null when timeline has no skill events — caller keeps continuous.
 *
 * R36 KEEP: when opener has ≥openerAllyMin allies AND ≥openerKillerMin killer
 * skills (from window start), apply per-mark local skill_used shares and
 * disclose opener allyMarks as logOnly (no invent). FA ≠ odds.
 */
export function skillMarksFromTimeline(input: {
  skillUsed?: TimelineSkillUsedEvent[] | null
  killerParticipantId: number
  allyParticipantIds?: number[]
  /** Window start (absolute game ms). */
  windowStartMs: number
  /** Window end (absolute game ms). */
  windowEndMs: number
  /** Opener horizon sec for activation gate (default 5). */
  openerWindowSec?: number
  /** Local share half-window sec (default 2). */
  localWindowSec?: number
  openerAllyMin?: number
  openerKillerMin?: number
  /** Apply R36 local attrib (default true). */
  applyOpenerAllyAttrib?: boolean
}): {
  actionMarks: KillWindowActionMark[]
  allyMarks: KillWindowActionMark[]
  openerAllyAttrib?: {
    activated: boolean
    scaledKillerMarks: number
    allyMarksDisclosed: number
    note: string
  }
} | null {
  const events = input.skillUsed
  if (!events?.length) return null
  const t0 = input.windowStartMs
  const t1 = input.windowEndMs
  if (!(t1 > t0)) return null
  const allySet = new Set(input.allyParticipantIds ?? [])
  const openerSec = input.openerWindowSec ?? 5
  const localSec = input.localWindowSec ?? 2
  const allyMin = input.openerAllyMin ?? 5
  const killerMin = input.openerKillerMin ?? 1
  const applyAttrib = input.applyOpenerAllyAttrib !== false

  let killerOpener = 0
  let allyOpener = 0
  const openerAllyEvents: TimelineSkillUsedEvent[] = []
  const openerEndMs = t0 + Math.round(openerSec * 1000)
  for (const e of events) {
    if (e.tMs < t0 || e.tMs > openerEndMs) continue
    if (e.participantId === input.killerParticipantId) killerOpener++
    else if (allySet.has(e.participantId)) {
      allyOpener++
      openerAllyEvents.push(e)
    }
  }
  const activated =
    applyAttrib && allyOpener >= allyMin && killerOpener >= killerMin
  const localMs = Math.round(localSec * 1000)

  const actionMarks: KillWindowActionMark[] = []
  const allyMarks: KillWindowActionMark[] = []
  let scaled = 0
  for (const e of events) {
    if (e.tMs < t0 || e.tMs > t1) continue
    const tSec = (e.tMs - t0) / 1000
    const slot = e.skillSlot > 0 ? e.skillSlot : undefined
    if (e.participantId === input.killerParticipantId) {
      let share: number | undefined
      if (activated) {
        let k = 0
        let a = 0
        for (const s of events) {
          if (Math.abs(s.tMs - e.tMs) > localMs) continue
          if (s.participantId === input.killerParticipantId) k++
          else if (allySet.has(s.participantId)) a++
        }
        if (a > 0) {
          share = Math.max(0.05, k / Math.max(1, k + a))
          scaled++
        }
      }
      actionMarks.push(
        share != null ? { tSec, skillSlot: slot, share } : { tSec, skillSlot: slot },
      )
    } else if (allySet.has(e.participantId) && activated && e.tMs <= openerEndMs) {
      allyMarks.push({ tSec, skillSlot: slot, ally: true, logOnly: true, share: 0 })
    }
  }
  if (!actionMarks.length) return null
  return {
    actionMarks,
    allyMarks,
    openerAllyAttrib: {
      activated,
      scaledKillerMarks: scaled,
      allyMarksDisclosed: allyMarks.length,
      note: activated
        ? `R36 local±${localSec}s skill_used shares; opener ally=${allyOpener} killer=${killerOpener}`
        : `R36 attrib off (ally=${allyOpener}/min${allyMin} killer=${killerOpener}/min${killerMin})`,
    },
  }
}

/**
 * Attach kill-window options when product ship gate is open and marks exist.
 * Missing marks / pins → returns input unchanged (continuous path).
 */
export function maybeAttachKillWindow(
  matchup: MatchupInput,
  opts: {
    actionMarks?: KillWindowInputOptions['actionMarks']
    allyMarks?: KillWindowInputOptions['allyMarks']
    engageSec?: number
    actualHpSeries?: KillWindowInputOptions['actualHpSeries']
    killOffsetSec?: number
  },
): MatchupInput {
  if (!PRODUCT_KILL_WINDOW_OPTED_IN) return matchup
  if (!opts.actionMarks?.length) return matchup
  const blue = matchup.blue.filter((f) => f.alive !== false)
  const red = matchup.red.filter((f) => f.alive !== false)
  if (blue.length !== 1 || red.length !== 1) return matchup
  if (
    blue[0]?.liveStats?.hp == null ||
    red[0]?.liveStats?.hp == null
  ) {
    return matchup
  }
  return {
    ...matchup,
    killWindow: {
      ...PRODUCT_KILL_WINDOW_DEFAULTS,
      actionMarks: opts.actionMarks,
      allyMarks: opts.allyMarks,
      engageSec: opts.engageSec,
      actualHpSeries: opts.actualHpSeries,
      killOffsetSec: opts.killOffsetSec,
      allyPulseShare: opts.allyMarks?.length
        ? PRODUCT_KILL_WINDOW_DEFAULTS.allyPulseShare
        : 0,
    },
  }
}
