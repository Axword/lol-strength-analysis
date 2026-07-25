/**
 * Autoresearch harness: kill-window overlays on GRID slim SQLite.
 *
 *   npx --yes tsx scripts/crosscheck_action_aligned.ts --suite 2970110-g1
 *   npx --yes tsx scripts/crosscheck_action_aligned.ts --suite 2970110-g1 \
 *     --mode action_aligned_aa --out docs/rofl-research/autoresearch/last_eval.json
 *
 * Research only. Gate/pulse/finish-AA math lives in src/engine/killWindowOverlay.ts
 * (product-shared). Never calculatorReady / never public matches.
 *
 * Experiment knob: EXPERIMENT below (or --mode / --pulse-sec / --aa-filler).
 */
import { appendFileSync, existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { DatabaseSync } from 'node:sqlite'
import { simulateMatchup } from '../src/engine/combat'
import {
  selectKillWindowMarks,
  simulateKillWindowSeries,
  type KillWindowActionMark,
  type KillWindowMarkSelection,
} from '../src/engine/killWindowOverlay'
import { getChampion } from '../src/data/champions'
import type { FighterLoadout, MatchupResult } from '../src/engine/types'
import { analyzeSqrtBins, binPhase } from './lib/crosscheck_sqrt_bins'
import { assertProductFreeze } from './lib/productFreezeAssert'
import {
  matchActions,
  breakdownByKind,
  type ActionRecord,
  type ActionCoverageResult,
  type ActionReplayAudit,
} from './lib/action_replay'
import {
  applyOpenerAllyAttrib,
  type OpenerAllyAttribDisclosure,
  type OpenerAllyAttribMode,
} from './lib/opener_ally_attrib'
import {
  foldBasicAttackTruth,
  loadAaIdentityBind,
  loadAaResearchJsonl,
  modelAaEchoFromTruth,
  type AaBridgeLoadResult,
  type AaIdentityBind,
  type BasicAttackEvent,
  type RosterPidJoin,
} from './lib/aa_bridge'

// ─── Experiment config (agent edits this between runs) ───────────────────────
const EXPERIMENT = {
  /** Human-readable hypothesis for results.jsonl */
  hypothesis:
    'BEST: finish AA + AA-at-mark + nearKill 1.5s + drop marks + markMinGap 0.4',
  /** baseline | gate_repin | action_aligned | action_aligned_aa | gate_action | cusum_gate | multi_caster */
  mode: 'gate_action' as Mode,
  /** Seconds of simulateMatchup applied at each skill mark */
  castPulseSec: 0.4,
  /** AA filler between marks (action_aligned_aa / multi_caster / gate_action+aa) */
  aaFiller: false,
  /** Cap AA count between marks */
  maxAaBetweenMarks: 6,
  /** Ally skill marks get this fraction of a cast pulse (multi_caster) */
  allyPulseShare: 0.35,
  /** Skip marks in the first N seconds after window start (idle poke filter) */
  markIdleSkipSec: 0,
  /** If >0, keep only marks within this many sec of an actual HP drop ≥ dropMinHp */
  markNearDropSec: 0.75,
  markDropMinHp: 15,
  /** Always keep killer marks within this many sec before actual kill (finish window) */
  markAlwaysNearKillSec: 1.5,
  /** When false, skip HP-drop filter (non-circular mark selection) */
  useDropConditioning: true,
  /**
   * Product-facing mark selection. When set, overrides useDropConditioning.
   * Default null ⇒ research drop-conditioning when useDropConditioning.
   * Product default (P-anti): cusum_engage_then_skills via --mark-selection.
   */
  markSelection: null as KillWindowMarkSelection | null,
  /** Bounded AAs only after last killer mark (finish-only; no idle AA) */
  finishAaAfterLastMark: true,
  /** Cap finish-only AAs */
  finishAaMax: 4,
  /** Optional hard stop: only apply finish AAs within this many sec before kill (0 = until end) */
  finishAaWindowSec: 0,
  /**
   * R30 KEEP: no AA-at-mark (with R-slot pulse 0) — Olaf→Trundle |lethErr| 2.81→0.33;
   * S0 FA↑ and S1 FA↑. Use --aa-at-mark to ablate.
   */
  aaAtEachMark: false,
  /** Re-pin HP/combat/ranks/items at each mark time (known frames only) */
  rePinEachMark: false,
  /** Per-skillSlot pulse lengths (Q=1 W=2 E=3 R=4). R30 KEEP: R=0 utility/steroid default. */
  perSlotPulse: true,
  pulseBySlot: { 1: 0.4, 2: 0.35, 3: 0.55, 4: 0 } as Record<number, number>,
  /** CUSUM params for cusum_gate */
  cusumK: 8,
  cusumH: 45,
  /** Min gap between killer marks (0 = off). Disclosed throttle, not a coeff fit. */
  markMinGapSec: 0.4,
  /** Keep killer marks only in last N sec before kill event (0 = off). */
  markFinishHorizonSec: 0,
  /** Keep at most N most-recent killer marks (0 = off). */
  maxKillerMarks: 0,
  /**
   * Density-triggered min-gap window (0 = classic global gap = research BEST).
   * Product experiments: >0 so spaced poke (Ezreal) keeps marks; Cassio spam thins.
   */
  markDensityWindowSec: 0,
  /** Max killer marks in density window before min-gap applies (default 1). */
  markDenseMaxPerWindow: 1,
  /**
   * R35 KEEP: sparse pre-CUSUM opener. Product default 0.5 / maxPost=3.
   * CLI 0 disables. Host gate optional via --pre-engage-host-series.
   */
  preEngageOpenerSec: 0.5,
  preEngageOpenerMaxPostMarks: 3,
  /**
   * R39 KEEP (+R41): W-slot opener share 0.18. Slot filter keeps S1 Vayne Q
   * at full share (no Path1 host gate needed). FA ≠ odds.
   */
  preEngageOpenerShare: 0.18,
  preEngageOpenerShareSlots: [2] as number[],
  /** R24/R35 research: near lead / far attenuated poke. 0 = off. */
  markPreEngageLeadSec: 0,
  markPreEngageFarSec: 0,
  markPreEngageFarShare: 0.35,
  /**
   * R31 KEEP: burst mark-domain lead 2.5s @ share 1 (Galio E+Q onto engage).
   * Lead 3.5 / W inclusion regresses S1. Pre-engage lead stays off. FA ≠ odds.
   */
  markPreBurstSkillLeadSec: 2.5,
  markPreBurstSkillShare: 1,
  /**
   * R42 KEEP: delay remapped pre-burst marks after CUSUM engage.
   * `--pre-burst-delay 0` ablates.
   */
  markPreBurstDelaySec: 0.3,
  /**
   * R42: score earlyMae only on pre-engage samples when idleFollowActual.
   * `--no-early-mae-pre-engage` ablates to legacy √T bin.
   */
  earlyMaePreEngageOnly: true,
  /**
   * R44: when false (default), truth inventory uses the same pre-burst lead
   * domain as mark load + remaps pre-window skills onto engage for matching.
   * `--truth-burst-window-only` ablates back to legacy burst-window truth.
   */
  truthBurstWindowOnly: false,
  /**
   * R44: remap truth lead skills onto engage (mirror model). Disable with
   * `--no-truth-pre-burst-remap` to measure domain-expand without time align.
   */
  truthPreBurstRemap: true,
  /** Shift idle engage to near opener when no far poke (R23). */
  preEngageShiftEngageToOpener: true,
  /**
   * Host gate: only apply pre-engage knobs when suite seriesId is in this
   * CSV (default empty = apply whenever knobs >0). Research S1-safe: `2970132`.
   */
  preEngageHostSeries: '' as string,
  /** Action-replay: matching tolerance (GOAL default 0.25s). */
  actionReplayTauSec: 0.25,
  /** Action-replay: fold ally skill_used into truthActions + emit ally model pulses (R3). */
  includeAllyTruth: false,
  /**
   * Track 2: emit modelActions kind=item from evented item_active_ability_used
   * (disclosed non-damage by default; does not set packetDecodeGate).
   */
  emitItemModelActions: true,
  /** Optional kit-linked item pulse share (0 = inventory-only; never HPΔ invent). */
  itemPulseShare: 0,
  /**
   * Track 3: research rfc461 basic_attack / damage_dealt JSONL → truth kind=aa.
   * Empty = disabled. Requires CastSpell/PUUID identity; rejects pid-from-order.
   * gateEligible only when same-match pro-grid decode (not BR1 fixture cross-match).
   */
  basicAttackJsonl: '' as string,
  aaIdentityPath: '' as string,
  /**
   * R40: fold decode truth AA into kill-window marks as kind:'aa' with kit
   * physical damage (shareHint>0). Disables zero-damage modelAaEcho.
   * Research-only — does not rewrite ship freeze defaults.
   */
  emitDamagingModelAaFromTruth: false,
  /**
   * R19 early/idle honesty KEEP: mirror actual victim HP until engageSec.
   * CLI --no-idle-follow-actual restores freeze-idle ablation.
   */
  idleFollowActual: true,
  /**
   * R36 KEEP: per-mark local skill_used ally attribution (not global share).
   * Activates when opener has ≥5 ally AND ≥1 killer skill_used (full windowMs[0]).
   * Discloses allyMarks logOnly when active. FA ≠ odds.
   */
  openerAllyAttrib: 'local_skill_share' as
    | 'off'
    | 'opener_skill_share'
    | 'opener_hp_neighborhood'
    | 'local_skill_share',
  openerAllyWindowSec: 5,
  openerAllyDiscloseMarks: true,
  openerAllyLocalSec: 2,
  openerAllyMin: 5,
  openerKillerMin: 1,
  /**
   * R33 KEEP: when alive===0, treat actual HP as 0 (corpse residual honesty).
   * Lifts c2_burst pathBand; S1 flat. FA ≠ odds. --no-zero-dead-actual ablates.
   */
  zeroDeadActualHp: true,
}

type Mode =
  | 'baseline'
  | 'gate_repin'
  | 'action_aligned'
  | 'action_aligned_aa'
  | 'gate_action'
  | 'cusum_gate'
  | 'multi_caster'

type FrameRow = {
  game_time_ms: number
  health: number | null
  health_max: number | null
  level?: number | null
  attack_damage?: number | null
  ability_power?: number | null
  armor?: number | null
  magic_resist?: number | null
  attack_speed?: number | null
  ability1_level?: number | null
  ability2_level?: number | null
  ability3_level?: number | null
  ability4_level?: number | null
  alive?: number | null
  items_json?: string | null
  participant_id?: number | null
}

type CrossCheck = {
  tMs: number
  killerId: number
  victimId: number
  killerChamp: string
  victimChamp: string
  killerName: string
  victimName: string
  windowMs: [number, number]
  killerLevel?: number
  victimLevel?: number
  victimHp: FrameRow[]
  killerHp: FrameRow[]
}

type CrossCheckFile = {
  seriesId: string
  gameIndex?: number
  matchHint?: string
  crossChecks: CrossCheck[]
}

type SkillMark = {
  tMs: number
  participantId: number
  skillSlot: number
  ally: boolean
  /** Default skill; item marks come from item_active_ability_used (Track 2). */
  kind?: 'skill' | 'item' | 'aa'
  /** Force zero-damage inventory emission (items default true unless itemPulseShare>0). */
  logOnly?: boolean
  /** Optional kit-linked pulse share for item marks. */
  share?: number
}

type MarkDebug = {
  tMs: number
  tSec: number
  skillSlot: number
  ally: boolean
  keptReason:
    | 'drop'
    | 'finish_window'
    | 'no_filter'
    | 'idle_skip_drop'
    | 'pre_engage_opener'
    | 'pre_engage_lead'
    | 'pre_engage_far'
}

type AssistProbe = {
  allySkillUsedNearKill: number
  allyParticipants: number[]
  windowMs: [number, number]
}

type CheckMetrics = {
  check: number
  segment: 'full' | 'burst'
  matchup: string
  earlyMaeHp: number | null
  lateMaeHp: number | null
  lateMaeDeltaVsBaseline: number | null
  maeHp: number | null
  lethalErrorSec: number | null
  killedInModel: boolean
  falseAllIn: boolean
  earlyPoisoned: boolean
  engageSec: number | null
  skillMarks: number
  method: string
  modelEndHp: number | null
  actualEndHp: number | null
  assistProbe: AssistProbe | null
  markDebug: MarkDebug[]
  actionReplay: {
    truthCount: number
    modelCount: number
    matchedCount: number
    precision: number
    recall: number
    actionCoverage: number
    allyDisclosedCount: number
    summonerDisclosedCount: number
  } | null
}

type ShipChecklist = {
  A1_check02_full_early_idle: boolean
  A2_check02_burst_lethal_pm2: boolean
  A3_check01_burst_path_improved: boolean
  A4_strict_lethal_01_02_full_burst: boolean
  A5_check03_early_not_hurt: boolean
  A6_poison_clear_prefer: boolean
  A6_min_check03_burst_poison_clear: boolean
  A7_late_mae_01_02_not_hurt: boolean
  A8_hard_fails_clean: boolean
  holdout_B_directionally: boolean | null
  holdout_B_burst_lethal_pm2: boolean | null
  holdout_B_check03_early_ok: boolean | null
  details: Record<string, string | number | boolean | null>
}

type SuiteResult = {
  schema: 'pro-grid-action-aligned-suite-v1'
  t: string
  hypothesis: string
  mode: Mode
  seriesId: string
  gameIndex: number
  config: typeof EXPERIMENT
  checks: CheckMetrics[]
  composite: number
  parts: {
    meanEarlyMae: number
    meanMae: number
    meanLethalAbs: number
    latePoisonPenalty: number
  }
  hardFails: string[]
  shipChecklist: ShipChecklist
  shipGateCandidate: boolean
  shipGate: boolean
  shipNotes: string[]
  baselineComposite: number | null
  keepCandidate: boolean
  actionReplay: {
    meanActionCoverage: number | null
    worstWindow: { check: number; segment: string; actionCoverage: number } | null
    gate95: boolean
    perWindow: Array<{
      check: number
      segment: string
      matchup: string
      truthCount: number
      modelCount: number
      matchedCount: number
      precision: number
      recall: number
      actionCoverage: number
    }>
  } | null
}

function argValue(flag: string, fallback = ''): string {
  const i = process.argv.indexOf(flag)
  return i >= 0 && process.argv[i + 1] ? process.argv[i + 1]! : fallback
}

function asPercentAs(champId: string, asWire: number | null | undefined): number {
  const base = getChampion(champId)?.stats.attackspeed ?? 0.625
  const pct = asWire == null || Number.isNaN(asWire) ? 100 : asWire
  return Math.max(0.2, base * (pct / 100))
}

function parseItemIds(frame: FrameRow): string[] {
  if (!frame.items_json) return []
  try {
    const raw = JSON.parse(frame.items_json) as unknown
    if (!Array.isArray(raw)) return []
    return raw
      .map((id) => Number(id))
      .filter((id) => Number.isFinite(id) && id > 0)
      .map((id) => String(id))
  } catch {
    return []
  }
}

function loadoutFromFrame(champId: string, level: number, frame: FrameRow): FighterLoadout {
  const hp = frame.health
  const hpMax = frame.health_max
  if (hp == null || hpMax == null || hpMax <= 0) {
    throw new Error(`missing HP pins for ${champId}`)
  }
  return {
    championId: champId,
    level: Math.max(1, level || Number(frame.level ?? 1)),
    itemIds: parseItemIds(frame),
    runeId: null,
    ranks: {
      Q: Math.max(0, Number(frame.ability1_level ?? 0)),
      W: Math.max(0, Number(frame.ability2_level ?? 0)),
      E: Math.max(0, Number(frame.ability3_level ?? 0)),
      R: Math.max(0, Number(frame.ability4_level ?? 0)),
    },
    alive: frame.alive !== 0,
    liveStats: {
      hp,
      hpMax,
      ad: Number(frame.attack_damage ?? 0),
      ap: Number(frame.ability_power ?? 0),
      armor: Number(frame.armor ?? 0),
      mr: Number(frame.magic_resist ?? 30),
      attackSpeed: asPercentAs(champId, frame.attack_speed),
    },
  }
}

function nearestFrame(rows: FrameRow[], targetMs: number): FrameRow | null {
  const usable = rows.filter((r) => r.health != null && r.health_max != null)
  if (!usable.length) return null
  let best = usable[0]!
  let bestD = Math.abs(best.game_time_ms - targetMs)
  for (const r of usable) {
    const d = Math.abs(r.game_time_ms - targetMs)
    if (d < bestD) {
      best = r
      bestD = d
    }
  }
  return best
}

function detectBurstStartMs(victimHp: FrameRow[], killMs: number): number {
  const rows = victimHp
    .filter((r) => r.health != null)
    .sort((a, b) => a.game_time_ms - b.game_time_ms)
  if (rows.length < 2) return rows[0]?.game_time_ms ?? Math.max(0, killMs - 5000)

  let i = rows.length - 1
  while (i > 0 && rows[i]!.game_time_ms > killMs) i--
  while (i + 1 < rows.length && (rows[i]!.health as number) > 0) {
    const next = rows[i + 1]!.health as number
    if (next < (rows[i]!.health as number) - 5) break
    if (rows[i + 1]!.game_time_ms > killMs + 2000) break
    i++
  }
  while (i > 0) {
    const cur = rows[i]!.health as number
    const prev = rows[i - 1]!.health as number
    if (prev < cur - 5) break
    i--
  }
  return rows[i]!.game_time_ms
}

function sliceFrames(rows: FrameRow[], startMs: number, endMs: number): FrameRow[] {
  return rows.filter((r) => r.game_time_ms >= startMs && r.game_time_ms <= endMs)
}

function sampleActual(
  rows: FrameRow[],
  windowStartMs: number,
  opts?: { zeroDeadActualHp?: boolean },
) {
  const zeroDead = opts?.zeroDeadActualHp ?? false
  return rows
    .filter((r) => r.health != null && r.health_max != null)
    .map((r) => ({
      tSec: (r.game_time_ms - windowStartMs) / 1000,
      hp: zeroDead && r.alive === 0 ? 0 : (r.health as number),
      hpMax: r.health_max as number,
    }))
}

function maeOf(
  actual: { tSec: number; hp: number }[],
  model: { tSec: number; hp: number }[],
  t0 = 0,
  t1 = Infinity,
): number | null {
  let sum = 0
  let n = 0
  for (let i = 0; i < actual.length; i++) {
    const a = actual[i]!
    const m = model[i]
    if (!m || a.tSec < t0 - 1e-9 || a.tSec > t1 + 1e-9) continue
    sum += Math.abs(m.hp - a.hp)
    n++
  }
  return n === 0 ? null : sum / n
}

function countKillerSkills(
  sqlitePath: string | null,
  killerId: number,
  startMs: number,
  endMs: number,
): number | null {
  if (!sqlitePath || !existsSync(sqlitePath)) return null
  const db = new DatabaseSync(sqlitePath, { readOnly: true })
  try {
    const row = db
      .prepare(
        `SELECT COUNT(*) AS n FROM events
         WHERE schema = 'skill_used'
           AND participant_id = ?
           AND game_time_ms >= ? AND game_time_ms <= ?`,
      )
      .get(killerId, startMs, endMs) as { n: number } | undefined
    return Number(row?.n ?? 0)
  } finally {
    db.close()
  }
}

function firstKillerSkillSec(
  sqlitePath: string | null,
  killerId: number,
  windowStartMs: number,
  windowEndMs: number,
): number | null {
  if (!sqlitePath || !existsSync(sqlitePath)) return null
  const db = new DatabaseSync(sqlitePath, { readOnly: true })
  try {
    const row = db
      .prepare(
        `SELECT MIN(game_time_ms) AS t FROM events
         WHERE schema = 'skill_used'
           AND participant_id = ?
           AND game_time_ms >= ? AND game_time_ms <= ?`,
      )
      .get(killerId, windowStartMs, windowEndMs) as { t: number | null } | undefined
    if (row?.t == null) return null
    return (Number(row.t) - windowStartMs) / 1000
  } finally {
    db.close()
  }
}

function firstVictimDropSec(
  actual: { tSec: number; hp: number }[],
  dropThreshold = 30,
): number | null {
  if (actual.length < 2) return null
  const startHp = actual[0]!.hp
  for (const a of actual) {
    if (startHp - a.hp > dropThreshold) return a.tSec
  }
  return null
}

/** CUSUM on positive damage (HP drops). Returns engage sec or null. */
function cusumEngageSec(
  actual: { tSec: number; hp: number }[],
  k: number,
  h: number,
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

function loadSkillMarks(
  sqlitePath: string,
  killerId: number,
  victimId: number,
  startMs: number,
  endMs: number,
  includeAllies: boolean,
): SkillMark[] {
  if (!existsSync(sqlitePath)) return []
  const db = new DatabaseSync(sqlitePath, { readOnly: true })
  try {
    const rows = db
      .prepare(
        `SELECT game_time_ms, participant_id, payload_json FROM events
         WHERE schema = 'skill_used'
           AND game_time_ms >= ? AND game_time_ms <= ?
         ORDER BY game_time_ms ASC`,
      )
      .all(startMs, endMs) as {
      game_time_ms: number
      participant_id: number
      payload_json: string
    }[]

    // Ally heuristic: same side of the kill (not victim). Research proxy only.
    const out: SkillMark[] = []
    for (const r of rows) {
      const pid = Number(r.participant_id)
      if (pid === victimId) continue
      const isKiller = pid === killerId
      if (!isKiller && !includeAllies) continue
      let skillSlot = 0
      try {
        const p = JSON.parse(r.payload_json) as { skillSlot?: number }
        skillSlot = Number(p.skillSlot ?? 0)
      } catch {
        skillSlot = 0
      }
      out.push({
        tMs: Number(r.game_time_ms),
        participantId: pid,
        skillSlot,
        ally: !isKiller,
        kind: 'skill',
      })
    }
    return out
  } finally {
    db.close()
  }
}

/**
 * Evented item_active_ability_used → model mark inventory (Track 2).
 * Merged AFTER skill mark selection so density/gap filters never see items.
 * Default logOnly (non-damage); optional kit-linked share via itemPulseShare.
 */
function loadItemMarks(
  sqlitePath: string,
  killerId: number,
  victimId: number,
  startMs: number,
  endMs: number,
  includeAllies: boolean,
  itemPulseShare = 0,
): SkillMark[] {
  if (!existsSync(sqlitePath)) return []
  const db = new DatabaseSync(sqlitePath, { readOnly: true })
  try {
    const killerTeam = (
      db
        .prepare(`SELECT team_id FROM roster WHERE participant_id = ?`)
        .get(killerId) as { team_id: number } | undefined
    )?.team_id
    const rows = db
      .prepare(
        `SELECT game_time_ms, participant_id FROM events
         WHERE schema = 'item_active_ability_used'
           AND game_time_ms >= ? AND game_time_ms <= ?
         ORDER BY game_time_ms ASC`,
      )
      .all(startMs, endMs) as { game_time_ms: number; participant_id: number }[]
    const out: SkillMark[] = []
    const logOnly = !(itemPulseShare > 0)
    for (const r of rows) {
      const pid = Number(r.participant_id)
      if (pid === victimId) continue
      if (pid === killerId) {
        out.push({
          tMs: Number(r.game_time_ms),
          participantId: pid,
          skillSlot: 0,
          ally: false,
          kind: 'item',
          logOnly,
          share: itemPulseShare > 0 ? itemPulseShare : undefined,
        })
        continue
      }
      if (!includeAllies) continue
      const team = (
        db
          .prepare(`SELECT team_id FROM roster WHERE participant_id = ?`)
          .get(pid) as { team_id: number } | undefined
      )?.team_id
      if (killerTeam != null && team === killerTeam) {
        out.push({
          tMs: Number(r.game_time_ms),
          participantId: pid,
          skillSlot: 0,
          ally: true,
          kind: 'item',
          logOnly,
          share: itemPulseShare > 0 ? itemPulseShare : undefined,
        })
      }
    }
    return out
  } catch {
    // slim-v2 / DBs without item_active schema
    return []
  } finally {
    db.close()
  }
}

type TruthActionSet = {
  /** Killer skill_used — always in truthActions (required by law). */
  truth: ActionRecord[]
  /** Same-team ally skill_used in window — disclosed count; NOT yet folded */
  allyDisclosedCount: number
  /** killer/ally summoner_spell_used in window — disclosed; model never emits summoner damage yet */
  summonerDisclosedCount: number
  /**
   * slim-v3 `item_active_ability_used` present in DB allowlist.
   * When true, killer/ally item actives in-window may be folded into truth (evented only).
   * Does NOT imply model emits item damage or packetDecodeGate.
   */
  itemActiveTruthAvailable: boolean
  /** Count of evented item_active_ability_used folded into truth (killer + optional ally). */
  itemActiveTruthCount: number
  /**
   * True when research decode JSONL folded ≥1 kind=aa into truth (CastSpell/PUUID bind).
   * Slim SQLite alone never supplies AA. HPΔ proxies remain research-only, never gate evidence.
   */
  aaTruthAvailable: boolean
  aaTruthCount: number
  /** True only when same-match pro-grid decode path supplied the AA events. */
  aaGateEligible: boolean
  aaBridgeDisclosures: string[]
}

/**
 * Action-replay truth inventory (GOAL-action-replay-95.md).
 * Killer skill_used required; ally skill_used disclosed-but-excluded until
 * R3 (multi-actor/assists) experiment explicitly folds them in.
 * slim-v3: item_active_ability_used folded when present (evented only).
 */
function loadRosterPidJoin(sqlitePath: string): RosterPidJoin | null {
  if (!existsSync(sqlitePath)) return null
  const db = new DatabaseSync(sqlitePath, { readOnly: true })
  try {
    const championToPid = new Map<string, number>()
    const pidToTeam = new Map<number, number>()
    const rows = db
      .prepare(
        `SELECT participant_id, team_id, champion_name FROM roster ORDER BY participant_id`,
      )
      .all() as {
      participant_id: number
      team_id: number
      champion_name: string
    }[]
    for (const r of rows) {
      const pid = Number(r.participant_id)
      pidToTeam.set(pid, Number(r.team_id))
      championToPid.set(String(r.champion_name).trim().toLowerCase(), pid)
    }
    let gameID: number | null = null
    let seriesId: string | null = null
    try {
      const gid = db
        .prepare(`SELECT value FROM meta WHERE key = 'gameID'`)
        .get() as { value: string } | undefined
      if (gid?.value != null && Number.isFinite(Number(gid.value))) {
        gameID = Number(gid.value)
      }
      const sid = db
        .prepare(`SELECT value FROM meta WHERE key = 'seriesId'`)
        .get() as { value: string } | undefined
      seriesId = sid?.value ?? null
    } catch {
      // meta optional
    }
    return { championToPid, pidToTeam, gameID, seriesId }
  } finally {
    db.close()
  }
}

function buildTruthActions(opts: {
  sqlitePath: string
  killerId: number
  victimId: number
  /** Inclusive filter start (may precede burst window when pre-burst lead). */
  startMs: number
  endMs: number
  /**
   * Origin for ActionRecord.tSec (default = startMs).
   * R44: when truth filter expands to pre-burst lead, keep tSec relative to
   * the HP/model window start so lead skills are negative and matchable
   * after the same engage remap the model applies.
   */
  tSecOriginMs?: number
  includeAllyTruth?: boolean
  aaEvents?: BasicAttackEvent[]
  aaIdentity?: AaIdentityBind | null
  aaLoaded?: AaBridgeLoadResult | null
}): TruthActionSet {
  const {
    sqlitePath,
    killerId,
    victimId,
    startMs,
    endMs,
    tSecOriginMs = startMs,
    includeAllyTruth = false,
    aaEvents = [],
    aaIdentity = null,
    aaLoaded = null,
  } = opts
  if (!existsSync(sqlitePath)) {
    return {
      truth: [],
      allyDisclosedCount: 0,
      summonerDisclosedCount: 0,
      itemActiveTruthAvailable: false,
      itemActiveTruthCount: 0,
      aaTruthAvailable: false,
      aaTruthCount: 0,
      aaGateEligible: false,
      aaBridgeDisclosures: ['sqlite missing — no truth inventory'],
    }
  }
  const db = new DatabaseSync(sqlitePath, { readOnly: true })
  try {
    const killerTeam = (
      db
        .prepare(`SELECT team_id FROM roster WHERE participant_id = ?`)
        .get(killerId) as { team_id: number } | undefined
    )?.team_id

    const skillRows = db
      .prepare(
        `SELECT game_time_ms, participant_id, payload_json FROM events
         WHERE schema = 'skill_used'
           AND game_time_ms >= ? AND game_time_ms <= ?
         ORDER BY game_time_ms ASC`,
      )
      .all(startMs, endMs) as {
      game_time_ms: number
      participant_id: number
      payload_json: string
    }[]

    const truth: ActionRecord[] = []
    let allyDisclosedCount = 0
    for (const r of skillRows) {
      const pid = Number(r.participant_id)
      if (pid === victimId) continue
      let skillSlot = 0
      try {
        const p = JSON.parse(r.payload_json) as { skillSlot?: number }
        skillSlot = Number(p.skillSlot ?? 0)
      } catch {
        skillSlot = 0
      }
      const tSec = (Number(r.game_time_ms) - tSecOriginMs) / 1000
      if (pid === killerId) {
        truth.push({ tSec, actorClass: 'killer', kind: 'skill', skillSlot })
        continue
      }
      const team = (
        db
          .prepare(`SELECT team_id FROM roster WHERE participant_id = ?`)
          .get(pid) as { team_id: number } | undefined
      )?.team_id
      if (killerTeam != null && team === killerTeam) {
        allyDisclosedCount++
        if (includeAllyTruth) {
          truth.push({ tSec, actorClass: 'ally', kind: 'skill', skillSlot })
        }
      }
    }

    const summonerRows = db
      .prepare(
        `SELECT participant_id FROM events
         WHERE schema = 'summoner_spell_used'
           AND game_time_ms >= ? AND game_time_ms <= ?`,
      )
      .all(startMs, endMs) as { participant_id: number }[]
    let summonerDisclosedCount = 0
    for (const r of summonerRows) {
      const pid = Number(r.participant_id)
      if (pid === killerId) {
        summonerDisclosedCount++
        continue
      }
      const team = (
        db
          .prepare(`SELECT team_id FROM roster WHERE participant_id = ?`)
          .get(pid) as { team_id: number } | undefined
      )?.team_id
      if (killerTeam != null && team === killerTeam) summonerDisclosedCount++
    }

    // slim-v3: evented item actives (fat rfc461 already had these; slim dropped them until v3).
    let itemActiveTruthAvailable = false
    let itemActiveTruthCount = 0
    try {
      const schemaProbe = db
        .prepare(
          `SELECT 1 AS ok FROM events WHERE schema = 'item_active_ability_used' LIMIT 1`,
        )
        .get() as { ok: number } | undefined
      itemActiveTruthAvailable = schemaProbe != null
      if (itemActiveTruthAvailable) {
        const itemRows = db
          .prepare(
            `SELECT game_time_ms, participant_id FROM events
             WHERE schema = 'item_active_ability_used'
               AND game_time_ms >= ? AND game_time_ms <= ?
             ORDER BY game_time_ms ASC`,
          )
          .all(startMs, endMs) as { game_time_ms: number; participant_id: number }[]
        for (const r of itemRows) {
          const pid = Number(r.participant_id)
          if (pid === victimId) continue
          const tSec = (Number(r.game_time_ms) - tSecOriginMs) / 1000
          if (pid === killerId) {
            truth.push({ tSec, actorClass: 'killer', kind: 'item' })
            itemActiveTruthCount++
            continue
          }
          const team = (
            db
              .prepare(`SELECT team_id FROM roster WHERE participant_id = ?`)
              .get(pid) as { team_id: number } | undefined
          )?.team_id
          if (killerTeam != null && team === killerTeam && includeAllyTruth) {
            truth.push({ tSec, actorClass: 'ally', kind: 'item' })
            itemActiveTruthCount++
          }
        }
      }
    } catch {
      // Older slim DBs without the schema row — leave itemActiveTruthAvailable false.
      itemActiveTruthAvailable = false
      itemActiveTruthCount = 0
    }

    // Track 3: research decode JSONL → kind=aa (CastSpell/PUUID bind; no HPΔ invent).
    let aaTruthAvailable = false
    let aaTruthCount = 0
    let aaGateEligible = false
    let aaBridgeDisclosures: string[] = [
      'no evented AA source in slim SQLite — enable --basic-attack-jsonl for decode path',
    ]
    if (aaEvents.length > 0 && aaIdentity) {
      const roster = loadRosterPidJoin(sqlitePath)
      const killerChamp = (
        db
          .prepare(
            `SELECT champion_name FROM roster WHERE participant_id = ?`,
          )
          .get(killerId) as { champion_name: string } | undefined
      )?.champion_name
      const jsonlGames = aaLoaded?.gameIDs ?? []
      const metaGame = roster?.gameID ?? null
      const metaSeriesNum =
        roster?.seriesId != null && Number.isFinite(Number(roster.seriesId))
          ? Number(roster.seriesId)
          : null
      // Same-match accept: riot gameID and/or GRID seriesId (R15 emits seriesId as gameID).
      const acceptedGameIDs = [
        ...new Set(
          [metaGame, metaSeriesNum].filter(
            (x): x is number => x != null && Number.isFinite(x),
          ),
        ),
      ]
      const proGridPath =
        acceptedGameIDs.length > 0 &&
        jsonlGames.length > 0 &&
        jsonlGames.every((g) => acceptedGameIDs.includes(g))
      const fold = foldBasicAttackTruth({
        events: aaEvents,
        identity: aaIdentity,
        startSec: startMs / 1000,
        endSec: endMs / 1000,
        killerId,
        victimId,
        killerChampion: killerChamp ?? null,
        roster,
        includeAllyTruth,
        // Accept slim meta.gameID and/or seriesId so R15 series-tagged JSONL
        // folds; still rejects foreign BR1 fixture gameIDs.
        requireGameIDs: acceptedGameIDs.length > 0 ? acceptedGameIDs : null,
        proGridPath,
      })
      for (const a of fold.actions) truth.push(a)
      aaTruthAvailable = fold.aaTruthAvailable
      aaTruthCount = fold.aaTruthCount
      aaGateEligible = fold.gateEligible
      aaBridgeDisclosures = fold.disclosures
    }

    truth.sort((a, b) => a.tSec - b.tSec)
    return {
      truth,
      allyDisclosedCount,
      summonerDisclosedCount,
      itemActiveTruthAvailable,
      itemActiveTruthCount,
      aaTruthAvailable,
      aaTruthCount,
      aaGateEligible,
      aaBridgeDisclosures,
    }
  } finally {
    db.close()
  }
}

function cloneLoadout(l: FighterLoadout): FighterLoadout {
  return {
    ...l,
    ranks: { ...l.ranks },
    itemIds: [...l.itemIds],
    liveStats: l.liveStats ? { ...l.liveStats } : undefined,
  }
}

function runModelSeries(
  atk: FighterLoadout,
  def: FighterLoadout,
  actual: { tSec: number; hp: number; hpMax: number }[],
  durationSec: number,
): { model: { tSec: number; hp: number }[]; full: MatchupResult; firstLethalSec: number | null } {
  const model = actual.map((a) => {
    const dur = Math.max(0.05, a.tSec)
    const r = simulateMatchup({
      blue: [atk],
      red: [def],
      engager: 'blue',
      mode: 'extended',
      durationSec: dur,
      xhMode: 'off',
    })
    return { tSec: a.tSec, hp: r.red.targets?.[0]?.hpRemaining ?? 0 }
  })
  const full = simulateMatchup({
    blue: [atk],
    red: [def],
    engager: 'blue',
    mode: 'extended',
    durationSec,
    xhMode: 'off',
  })
  return {
    model,
    full,
    firstLethalSec: full.timing?.firstLethalSec ?? null,
  }
}

function runGatedModelSeries(
  atkIdle: FighterLoadout,
  defIdle: FighterLoadout,
  actual: { tSec: number; hp: number; hpMax: number }[],
  durationSec: number,
  engageSec: number,
  atkEngage: FighterLoadout,
  defEngage: FighterLoadout,
): { model: { tSec: number; hp: number }[]; firstLethalSec: number | null } {
  const idleHp = defIdle.liveStats?.hp ?? actual[0]?.hp ?? 0
  let firstLethalSec: number | null = null
  const model = actual.map((a) => {
    if (a.tSec <= engageSec + 1e-9) {
      return { tSec: a.tSec, hp: idleHp }
    }
    const dur = Math.max(0.05, a.tSec - engageSec)
    const r = simulateMatchup({
      blue: [atkEngage],
      red: [defEngage],
      engager: 'blue',
      mode: 'extended',
      durationSec: dur,
      xhMode: 'off',
    })
    const hp = r.red.targets?.[0]?.hpRemaining ?? 0
    if (hp <= 0 && firstLethalSec == null) {
      firstLethalSec =
        engageSec + (r.timing?.firstLethalSec ?? dur)
    }
    return { tSec: a.tSec, hp }
  })
  if (firstLethalSec == null) {
    const gatedDur = Math.max(0.05, durationSec - engageSec)
    const full = simulateMatchup({
      blue: [atkEngage],
      red: [defEngage],
      engager: 'blue',
      mode: 'extended',
      durationSec: gatedDur,
      xhMode: 'off',
    })
    if (full.timing?.firstLethalSec != null) {
      firstLethalSec = engageSec + full.timing.firstLethalSec
    } else if ((full.red.targets?.[0]?.hpRemaining ?? 1) <= 0) {
      firstLethalSec = engageSec + gatedDur
    }
  }
  return { model, firstLethalSec }
}

/**
 * Marked point-process overlay — delegates to engine killWindowOverlay
 * so research and product cannot drift.
 */
function runActionAlignedSeries(opts: {
  atk: FighterLoadout
  def: FighterLoadout
  actual: { tSec: number; hp: number; hpMax: number }[]
  windowStartMs: number
  marks: SkillMark[]
  pulseSec: number
  aaFiller: boolean
  maxAa: number
  allyShare: number
  /** Hold idle HP until this sec (gate_action); AA filler also waits */
  engageSec?: number | null
  idleHp?: number | null
  /** Mirror actual HP pre-engage (earlyBand honesty); default false */
  idleFollowActual?: boolean
  finishAaAfterLastMark?: boolean
  finishAaMax?: number
  finishAaWindowSec?: number
  killOffsetSec?: number | null
  aaAtEachMark?: boolean
  perSlotPulse?: boolean
  pulseBySlot?: Record<number, number>
  /** Optional per-mark loadouts (same order as filtered marks); research re-pin */
  markLoadouts?: Array<{ atk: FighterLoadout; def: FighterLoadout } | null>
}): {
  model: { tSec: number; hp: number }[]
  firstLethalSec: number | null
  markCount: number
  modelActions: ActionRecord[]
} {
  const engineMarks: KillWindowActionMark[] = opts.marks.map((m) => ({
    tSec: (m.tMs - opts.windowStartMs) / 1000,
    skillSlot: m.skillSlot,
    ally: m.ally,
    kind: m.kind ?? 'skill',
    logOnly: m.logOnly,
    share: m.share,
  }))
  const r = simulateKillWindowSeries({
    atk: opts.atk,
    def: opts.def,
    actual: opts.actual,
    marks: engineMarks,
    castPulseSec: opts.pulseSec,
    aaFiller: opts.aaFiller,
    maxAaBetweenMarks: opts.maxAa,
    allyPulseShare: opts.allyShare,
    engageSec: opts.engageSec ?? null,
    idleHp: opts.idleHp ?? null,
    idleFollowActual: opts.idleFollowActual ?? false,
    finishAa: {
      afterLastMark: opts.finishAaAfterLastMark ?? false,
      maxAa: opts.finishAaMax ?? 4,
      aaAtEachMark: opts.aaAtEachMark ?? false,
      windowSec: opts.finishAaWindowSec ?? 0,
    },
    killOffsetSec: opts.killOffsetSec ?? null,
    perSlotPulse: opts.perSlotPulse ?? false,
    pulseBySlot: opts.pulseBySlot ?? {},
    xhMode: 'off',
    markLoadouts: opts.markLoadouts,
  })
  return {
    model: r.model,
    firstLethalSec: r.firstLethalSec,
    markCount: r.markCount,
    modelActions: r.modelActions,
  }
}

function classifyEarlyBin(opts: {
  actualDrop: number | null
  modelDrop: number | null
  killerSkills: number | null
}): { falseAllIn: boolean } {
  const { actualDrop, modelDrop, killerSkills } = opts
  const falseAllIn =
    killerSkills === 0 &&
    actualDrop != null &&
    modelDrop != null &&
    actualDrop < 30 &&
    modelDrop > 80
  return { falseAllIn }
}

function classifyLatePoison(opts: {
  modelHpAtLateStart: number | null
  actualHpAtLateStart: number | null
  /** If actual never reaches low HP in the window, kill-event truth is incomplete — do not poison-flag */
  actualMinHpInWindow?: number | null
}): { earlyPoisoned: boolean } {
  const { modelHpAtLateStart, actualHpAtLateStart, actualMinHpInWindow } = opts
  if (modelHpAtLateStart == null || actualHpAtLateStart == null) {
    return { earlyPoisoned: false }
  }
  // Honest incomplete truth: victim HP samples never collapse (e.g. floor ~210 on check03)
  // while a kill event exists — poison would be a false diagnostic against 1v1 overlay.
  if (actualMinHpInWindow != null && actualMinHpInWindow >= 150) {
    return { earlyPoisoned: false }
  }
  const earlyPoisoned =
    actualHpAtLateStart >= 200 &&
    modelHpAtLateStart <= Math.max(30, 0.3 * actualHpAtLateStart)
  return { earlyPoisoned }
}

function mean(xs: number[]): number {
  if (!xs.length) return 0
  return xs.reduce((a, b) => a + b, 0) / xs.length
}

function computeComposite(checks: CheckMetrics[]): {
  composite: number
  parts: SuiteResult['parts']
} {
  const early = checks.map((c) => c.earlyMaeHp).filter((x): x is number => x != null)
  const mae = checks.map((c) => c.maeHp).filter((x): x is number => x != null)
  const lethalAbs = checks.map((c) =>
    c.lethalErrorSec == null ? 5.0 : Math.abs(c.lethalErrorSec),
  )
  const latePoisonPenalty = checks.some((c) => c.earlyPoisoned) ? 1.0 : 0
  const meanEarlyMae = mean(early)
  const meanMae = mean(mae)
  const meanLethalAbs = mean(lethalAbs)
  const composite =
    0.35 * (meanEarlyMae / 100) +
    0.25 * (meanMae / 100) +
    0.25 * meanLethalAbs +
    0.15 * latePoisonPenalty
  return {
    composite,
    parts: { meanEarlyMae, meanMae, meanLethalAbs, latePoisonPenalty },
  }
}

function lethalOk(c: CheckMetrics | undefined): boolean {
  return (
    !!c?.killedInModel &&
    c.lethalErrorSec != null &&
    Math.abs(c.lethalErrorSec) <= 2
  )
}

function evalShipChecklist(
  checks: CheckMetrics[],
  baselineByKey: Map<string, CheckMetrics>,
  hardFails: string[],
  opts?: { isHoldout?: boolean; holdoutFromDev?: ShipChecklist | null },
): {
  checklist: ShipChecklist
  shipGateCandidate: boolean
  shipGate: boolean
  notes: string[]
} {
  const notes: string[] = []
  const get = (n: number, seg: 'full' | 'burst') =>
    checks.find((c) => c.check === n && c.segment === seg)
  const base = (n: number, seg: 'full' | 'burst') => baselineByKey.get(`${n}:${seg}`)

  const c02full = get(2, 'full')
  const b02full = base(2, 'full')
  const A1 =
    !!c02full &&
    !!b02full &&
    c02full.earlyMaeHp != null &&
    b02full.earlyMaeHp != null &&
    c02full.earlyMaeHp < b02full.earlyMaeHp * 0.25
  notes.push(A1 ? 'A1 check02 full early MAE ≪ baseline' : 'FAIL A1: check02 full early')

  const c02burst = get(2, 'burst')
  const A2 = lethalOk(c02burst)
  notes.push(A2 ? 'A2 check02 burst lethal ±2s' : 'FAIL A2: check02 burst lethal')

  const c01burst = get(1, 'burst')
  const b01burst = base(1, 'burst')
  const A3 =
    !!c01burst &&
    !!b01burst &&
    c01burst.maeHp != null &&
    b01burst.maeHp != null &&
    c01burst.maeHp < b01burst.maeHp
  notes.push(A3 ? 'A3 check01 burst path improved' : 'FAIL A3: check01 burst path')

  const c01full = get(1, 'full')
  // Strict lethal: 01+02 full+burst all must kill within ±2 when real kill in window
  const A4 =
    lethalOk(c01full) && lethalOk(c01burst) && lethalOk(get(2, 'full')) && lethalOk(c02burst)
  notes.push(
    A4
      ? 'A4 strict lethal 01/02 full+burst'
      : 'FAIL A4: strict lethal (need 01+02 full+burst kill ±2s)',
  )

  const c03full = get(3, 'full')
  const b03full = base(3, 'full')
  const A5 =
    c03full?.earlyMaeHp != null &&
    b03full?.earlyMaeHp != null &&
    c03full.earlyMaeHp - b03full.earlyMaeHp <= 50
  notes.push(A5 ? 'A5 check03 early not hurt >50' : 'FAIL A5: check03 early hurt')

  const anyPoison = checks.some((c) => c.earlyPoisoned)
  const A6prefer = !anyPoison
  const A6min = !(get(3, 'burst')?.earlyPoisoned ?? false)
  notes.push(
    A6prefer
      ? 'A6 poison clear (all)'
      : A6min
        ? 'A6min check03 burst poison clear (prefer still fails)'
        : 'FAIL A6: check03 burst earlyPoisoned',
  )

  const lateOk = (n: number): boolean => {
    const c = get(n, 'full')
    const b = base(n, 'full')
    if (c?.lateMaeHp == null || b?.lateMaeHp == null) return true
    // Continuous false-all-in baselines often show late MAE≈0 because they die early
    // incorrectly — do not punish idle/gate fixes for that artifact.
    if (b.falseAllIn) return true
    return c.lateMaeHp - b.lateMaeHp <= 50
  }
  const A7 = lateOk(1) && lateOk(2)
  notes.push(
    A7
      ? 'A7 late MAE 01/02 not hurt >50 (skip if baseline falseAllIn)'
      : 'FAIL A7: late MAE 01/02 >+50',
  )

  const A8 = hardFails.length === 0
  notes.push(A8 ? 'A8 hard fails clean' : `FAIL A8: ${hardFails.join('; ')}`)

  let holdout_B_directionally: boolean | null = null
  let holdout_B_burst_lethal_pm2: boolean | null = null
  let holdout_B_check03_early_ok: boolean | null = null
  if (opts?.isHoldout) {
    // Holdout B (from goal): early idle direction + ≥1 burst lethal±2 + no c03 early hard-fail
    holdout_B_directionally = A1
    holdout_B_burst_lethal_pm2 = [get(1, 'burst'), get(2, 'burst'), get(3, 'burst')].some(
      (c) => lethalOk(c),
    )
    holdout_B_check03_early_ok = A5
    notes.push(
      holdout_B_directionally && holdout_B_burst_lethal_pm2 && holdout_B_check03_early_ok
        ? 'holdout B directional+≥1 burst lethal±2+early OK'
        : 'FAIL holdout B ship bar',
    )
  } else if (opts?.holdoutFromDev) {
    holdout_B_directionally = opts.holdoutFromDev.holdout_B_directionally
    holdout_B_burst_lethal_pm2 = opts.holdoutFromDev.holdout_B_burst_lethal_pm2
    holdout_B_check03_early_ok = opts.holdoutFromDev.holdout_B_check03_early_ok
    notes.push(
      holdout_B_directionally &&
        holdout_B_burst_lethal_pm2 &&
        holdout_B_check03_early_ok
        ? 'holdout B merged OK'
        : 'FAIL holdout B (merged)',
    )
  } else {
    notes.push('holdout B not evaluated in this suite run')
  }

  const checklist: ShipChecklist = {
    A1_check02_full_early_idle: A1,
    A2_check02_burst_lethal_pm2: A2,
    A3_check01_burst_path_improved: A3,
    A4_strict_lethal_01_02_full_burst: A4,
    A5_check03_early_not_hurt: A5,
    A6_poison_clear_prefer: A6prefer,
    A6_min_check03_burst_poison_clear: A6min,
    A7_late_mae_01_02_not_hurt: A7,
    A8_hard_fails_clean: A8,
    holdout_B_directionally,
    holdout_B_burst_lethal_pm2,
    holdout_B_check03_early_ok,
    details: {
      c01_full_lethal: c01full?.lethalErrorSec ?? null,
      c01_burst_lethal: c01burst?.lethalErrorSec ?? null,
      c02_burst_lethal: c02burst?.lethalErrorSec ?? null,
      c01_assist_full: c01full?.assistProbe?.allySkillUsedNearKill ?? null,
      c01_modelEndHp_burst: c01burst?.modelEndHp ?? null,
      c03_burst_poison: get(3, 'burst')?.earlyPoisoned ?? null,
      lateMaeDelta_01: c01full?.lateMaeDeltaVsBaseline ?? null,
      lateMaeDelta_02: c02full?.lateMaeDeltaVsBaseline ?? null,
    },
  }

  // Candidate = A ship bar without requiring holdout (A4 required for true)
  const shipGateCandidate =
    A1 && A2 && A3 && A4 && A5 && A6min && A7 && A8

  // On holdout suites, shipGate here means "holdout B pass" (combine with A in best.json).
  // On primary suites, shipGate stays false unless caller merges holdout B via holdoutFromDev.
  let shipGate = false
  if (opts?.isHoldout) {
    shipGate =
      A8 &&
      !!holdout_B_directionally &&
      !!holdout_B_burst_lethal_pm2 &&
      !!holdout_B_check03_early_ok
  } else if (opts?.holdoutFromDev) {
    const h = opts.holdoutFromDev
    shipGate =
      shipGateCandidate &&
      !!h.holdout_B_directionally &&
      !!h.holdout_B_burst_lethal_pm2 &&
      !!h.holdout_B_check03_early_ok
  }

  return { checklist, shipGateCandidate, shipGate, notes }
}

function hardFailsAgainstBaseline(
  checks: CheckMetrics[],
  baselineByKey: Map<string, CheckMetrics>,
): string[] {
  const fails: string[] = []
  const c03 = checks.find((c) => c.check === 3 && c.segment === 'full')
  const b03 = baselineByKey.get('3:full')
  if (
    c03?.earlyMaeHp != null &&
    b03?.earlyMaeHp != null &&
    c03.earlyMaeHp - b03.earlyMaeHp > 50
  ) {
    fails.push(
      `hardFail: check03 early MAE worsened by ${(c03.earlyMaeHp - b03.earlyMaeHp).toFixed(1)} (>50)`,
    )
  }
  return fails
}

function resolveMode(): Mode {
  const cli = argValue('--mode', '') as Mode | ''
  if (cli) return cli
  return EXPERIMENT.mode
}

function resolveSuitePaths(suite: string): {
  inputPath: string
  sqlitePath: string
  seriesId: string
  gameIndex: number
  isHoldout: boolean
} {
  if (suite === '2970110-g1') {
    return {
      inputPath: resolve('docs/canvases/_data/crosschecks-2970110-g1.json'),
      sqlitePath: resolve('artifacts/pro-grid/2970110/timeline.g1.slim.sqlite'),
      seriesId: '2970110',
      gameIndex: 1,
      isHoldout: false,
    }
  }
  if (suite === '2970120-g1-holdout') {
    return {
      inputPath: resolve('docs/canvases/_data/crosschecks-2970120-g1-holdout.json'),
      sqlitePath: resolve('artifacts/pro-grid/2970120/timeline.g1.slim.sqlite'),
      seriesId: '2970120',
      gameIndex: 1,
      isHoldout: true,
    }
  }
  if (suite === '2970137-g1-holdout') {
    return {
      inputPath: resolve('docs/canvases/_data/crosschecks-2970137-g1-holdout.json'),
      sqlitePath: resolve('artifacts/pro-grid/2970137/timeline.g1.slim.sqlite'),
      seriesId: '2970137',
      gameIndex: 1,
      isHoldout: true,
    }
  }
  if (suite === '2970132-g1-holdout') {
    return {
      inputPath: resolve('docs/canvases/_data/crosschecks-2970132-g1-holdout.json'),
      sqlitePath: resolve('artifacts/pro-grid/2970132/timeline.g1.slim.sqlite'),
      seriesId: '2970132',
      gameIndex: 1,
      isHoldout: true,
    }
  }
  if (suite === '2970132-g1') {
    return {
      inputPath: resolve('docs/canvases/_data/crosschecks-2970132-g1.json'),
      sqlitePath: resolve('artifacts/pro-grid/2970132/timeline.g1.slim.sqlite'),
      seriesId: '2970132',
      gameIndex: 1,
      isHoldout: false,
    }
  }
  throw new Error(
    `unknown --suite ${suite} (supported: 2970110-g1 | 2970132-g1 | 2970137-g1-holdout | 2970120-g1-holdout | 2970132-g1-holdout)`,
  )
}

function probeAssists(
  sqlitePath: string,
  killerId: number,
  victimId: number,
  killMs: number,
): AssistProbe {
  const windowMs: [number, number] = [killMs - 2000, killMs + 500]
  if (!existsSync(sqlitePath)) {
    return { allySkillUsedNearKill: 0, allyParticipants: [], windowMs }
  }
  const db = new DatabaseSync(sqlitePath, { readOnly: true })
  try {
    const killerTeam = (
      db
        .prepare(`SELECT team_id FROM roster WHERE participant_id = ?`)
        .get(killerId) as { team_id: number } | undefined
    )?.team_id
    const rows = db
      .prepare(
        `SELECT DISTINCT participant_id FROM events
         WHERE schema = 'skill_used'
           AND game_time_ms >= ? AND game_time_ms <= ?
           AND participant_id != ? AND participant_id != ?`,
      )
      .all(windowMs[0], windowMs[1], killerId, victimId) as {
      participant_id: number
    }[]
    const allyParticipants: number[] = []
    for (const r of rows) {
      const pid = Number(r.participant_id)
      if (killerTeam == null) {
        allyParticipants.push(pid)
        continue
      }
      const team = (
        db
          .prepare(`SELECT team_id FROM roster WHERE participant_id = ?`)
          .get(pid) as { team_id: number } | undefined
      )?.team_id
      if (team === killerTeam) allyParticipants.push(pid)
    }
    if (!allyParticipants.length) {
      return { allySkillUsedNearKill: 0, allyParticipants: [], windowMs }
    }
    const placeholders = allyParticipants.map(() => '?').join(',')
    const countRow = db
      .prepare(
        `SELECT COUNT(*) AS n FROM events
         WHERE schema = 'skill_used'
           AND game_time_ms >= ? AND game_time_ms <= ?
           AND participant_id IN (${placeholders})`,
      )
      .get(windowMs[0], windowMs[1], ...allyParticipants) as
      | { n: number }
      | undefined
    return {
      allySkillUsedNearKill: Number(countRow?.n ?? 0),
      allyParticipants,
      windowMs,
    }
  } finally {
    db.close()
  }
}

function runOneCheck(opts: {
  check: CrossCheck
  checkN: number
  segment: 'full' | 'burst'
  sqlitePath: string
  mode: Mode
  cfg: typeof EXPERIMENT
  seriesId?: string
  gameIndex?: number
  writeAudit?: boolean
  aaEvents?: BasicAttackEvent[]
  aaIdentity?: AaIdentityBind | null
  aaLoaded?: AaBridgeLoadResult | null
}): CheckMetrics {
  const {
    check,
    checkN,
    segment,
    sqlitePath,
    mode,
    cfg,
    seriesId,
    gameIndex,
    writeAudit,
    aaEvents = [],
    aaIdentity = null,
    aaLoaded = null,
  } = opts

  let windowStart = check.windowMs[0]
  let windowEnd = Math.max(check.windowMs[1], check.tMs + 2000)
  if (segment === 'burst') {
    windowStart = detectBurstStartMs(check.victimHp, check.tMs)
    windowEnd = check.tMs + 2000
  }

  const killerRows = sliceFrames(check.killerHp, windowStart, windowEnd)
  const victimRows = sliceFrames(check.victimHp, windowStart, windowEnd)
  const killerFrame =
    killerRows[0] ?? check.killerHp.find((r) => r.game_time_ms >= windowStart)
  const victimFrame =
    victimRows[0] ?? check.victimHp.find((r) => r.game_time_ms >= windowStart)
  if (!killerFrame || !victimFrame) throw new Error(`missing frames check ${checkN}`)

  const durationSec = Math.max(1, (windowEnd - windowStart) / 1000)
  const killOffsetSec = (check.tMs - windowStart) / 1000
  const atk = loadoutFromFrame(
    check.killerChamp,
    check.killerLevel ?? Number(killerFrame.level ?? 1),
    killerFrame,
  )
  const def = loadoutFromFrame(
    check.victimChamp,
    check.victimLevel ?? Number(victimFrame.level ?? 1),
    victimFrame,
  )
  const actual = sampleActual(victimRows.length ? victimRows : check.victimHp, windowStart, {
    zeroDeadActualHp: cfg.zeroDeadActualHp,
  })

  // Baseline continuous always computed for diagnostics / hard-fail ref when mode=baseline
  const baseline = runModelSeries(atk, def, actual, durationSec)

  const skillEngage = firstKillerSkillSec(
    sqlitePath,
    check.killerId,
    windowStart,
    windowEnd,
  )
  const dropEngage = firstVictimDropSec(actual)
  const cusumEngage = cusumEngageSec(actual, cfg.cusumK, cfg.cusumH)

  let engageSec: number | null = null
  if (mode === 'cusum_gate') {
    engageSec = cusumEngage ?? skillEngage ?? dropEngage
  } else if (mode === 'gate_repin') {
    engageSec = skillEngage ?? dropEngage
  }

  const includeAllies = mode === 'multi_caster'
  const preBurstLeadSec =
    segment === 'burst' ? (cfg.markPreBurstSkillLeadSec ?? 0) : 0
  const skillLoadStart =
    preBurstLeadSec > 0
      ? windowStart - Math.round(preBurstLeadSec * 1000)
      : windowStart
  /** Engage tSec (window-relative) used for R31 pre-burst mark remap; also truth match. */
  let preBurstRemapEngageSec: number | null = null
  let marks = loadSkillMarks(
    sqlitePath,
    check.killerId,
    check.victimId,
    skillLoadStart,
    windowEnd,
    includeAllies,
  )
  // Burst mark-domain expand: remap real pre-window skills onto CUSUM engage
  // so legacy HP burst onset (earlyBand) stays intact. No invented events.
  // R42: optional delay so coincident E+Q dump does not cliff earlyBand.
  if (preBurstLeadSec > 0) {
    const engageGuess =
      cusumEngageSec(actual, cfg.cusumK, cfg.cusumH) ??
      firstKillerSkillSec(sqlitePath, check.killerId, windowStart, windowEnd) ??
      0
    const delaySec = Math.max(0, cfg.markPreBurstDelaySec ?? 0)
    preBurstRemapEngageSec = Math.max(0, engageGuess + delaySec)
    const engageMs =
      windowStart + Math.round(preBurstRemapEngageSec * 1000)
    const share = cfg.markPreBurstSkillShare ?? 1
    marks = marks.map((m) => {
      if (m.ally || m.tMs >= windowStart) return m
      return {
        ...m,
        tMs: engageMs,
        share: (m.share ?? 1) * share,
      }
    })
  }
  const markDebug: MarkDebug[] = []
  if (cfg.markIdleSkipSec > 0) {
    const skipMs = windowStart + Math.round(cfg.markIdleSkipSec * 1000)
    marks = marks.filter((m) => m.tMs >= skipMs)
  }
  const markSelection: KillWindowMarkSelection | null =
    cfg.markSelection ??
    (cfg.useDropConditioning && cfg.markNearDropSec > 0
      ? 'near_hp_drop'
      : 'post_engage_killer_skills')
  let selectedEngageSec: number | null = null
  let selectedCusumEngageSec: number | null = null
  {
    const hostGate = (cfg.preEngageHostSeries ?? '').trim()
    const hostOk =
      !hostGate ||
      hostGate
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean)
        .includes(String(seriesId ?? ''))
    const peOpener = hostOk ? cfg.preEngageOpenerSec : 0
    const peMaxPost = hostOk ? cfg.preEngageOpenerMaxPostMarks : 0
    const peLead = hostOk ? cfg.markPreEngageLeadSec : 0
    const peFar = hostOk ? cfg.markPreEngageFarSec : 0
    const peFarShare = hostOk ? cfg.markPreEngageFarShare : 0
    const peShift = hostOk ? cfg.preEngageShiftEngageToOpener : true

    const engineMarks: KillWindowActionMark[] = marks.map((m) => ({
      tSec: (m.tMs - windowStart) / 1000,
      skillSlot: m.skillSlot,
      ally: m.ally,
      share: m.share,
      kind: m.kind === 'aa' || m.kind === 'item' ? m.kind : 'skill',
    }))
    // Engage for selection: first killer skill (CUSUM may refine)
    const selEngage =
      firstKillerSkillSec(sqlitePath, check.killerId, windowStart, windowEnd) ??
      null
    const selected = selectKillWindowMarks({
      marks: engineMarks,
      selection: markSelection,
      engageSec: selEngage,
      actual,
      markNearDropSec: cfg.markNearDropSec,
      markDropMinHp: cfg.markDropMinHp,
      markAlwaysNearKillSec: cfg.markAlwaysNearKillSec,
      killOffsetSec,
      cusumK: cfg.cusumK,
      cusumH: cfg.cusumH,
      markMinGapSec: cfg.markMinGapSec,
      markFinishHorizonSec: cfg.markFinishHorizonSec,
      maxKillerMarks: cfg.maxKillerMarks,
      markDensityWindowSec: cfg.markDensityWindowSec,
      markDenseMaxPerWindow: cfg.markDenseMaxPerWindow,
      preEngageOpenerSec: peOpener,
      preEngageOpenerMaxPostMarks: peMaxPost,
      preEngageOpenerShare: hostOk ? (cfg.preEngageOpenerShare ?? 1) : 1,
      preEngageOpenerShareSlots: hostOk
        ? cfg.preEngageOpenerShareSlots
        : undefined,
      markPreEngageLeadSec: peLead,
      markPreEngageFarSec: peFar,
      markPreEngageFarShare: peFarShare,
      preEngageShiftEngageToOpener: peShift,
    })
    selectedEngageSec = selected.engageSec
    selectedCusumEngageSec = selected.cusumEngageSec ?? selected.engageSec
    const keptSet = new Set(
      selected.marks.map(
        (m) =>
          `${m.tSec.toFixed(4)}|${m.skillSlot ?? 0}|${m.ally ? 1 : 0}`,
      ),
    )
    const shareByKey = new Map(
      selected.marks.map(
        (m) =>
          [
            `${m.tSec.toFixed(4)}|${m.skillSlot ?? 0}|${m.ally ? 1 : 0}`,
            m.share,
          ] as const,
      ),
    )
    const kept: SkillMark[] = []
    for (const m of marks) {
      const tSec = (m.tMs - windowStart) / 1000
      const key = `${tSec.toFixed(4)}|${m.skillSlot}|${m.ally ? 1 : 0}`
      if (!keptSet.has(key)) continue
      const share = shareByKey.get(key)
      kept.push(share != null ? { ...m, share } : m)
      const reason =
        selected.keptReasons.find(
          (r) =>
            Math.abs(r.tSec - tSec) < 1e-6 &&
            r.skillSlot === m.skillSlot &&
            r.ally === m.ally,
        )?.keptReason ?? 'no_filter'
      const debugReason: MarkDebug['keptReason'] =
        reason === 'post_engage'
          ? 'no_filter'
          : reason === 'idle_skip'
            ? 'idle_skip_drop'
            : reason === 'pre_engage_opener' ||
                reason === 'pre_engage_lead' ||
                reason === 'pre_engage_far'
              ? reason
              : reason === 'drop' || reason === 'finish_window'
                ? reason
                : 'no_filter'
      markDebug.push({
        tMs: m.tMs,
        tSec,
        skillSlot: m.skillSlot,
        ally: m.ally,
        keptReason: debugReason,
      })
    }
    marks = kept
  }

  // Track 2: merge evented item actives AFTER skill selection so gap/density
  // filters and ship HP path stay skill-identical (items default non-damage).
  if (cfg.emitItemModelActions) {
    const itemMarks = loadItemMarks(
      sqlitePath,
      check.killerId,
      check.victimId,
      windowStart,
      windowEnd,
      cfg.includeAllyTruth || includeAllies,
      cfg.itemPulseShare ?? 0,
    )
    if (itemMarks.length) {
      marks = [...marks, ...itemMarks].sort((a, b) => a.tMs - b.tMs)
    }
  }

  // R40: decode truth AA → kind:'aa' marks with kit physical damage (shareHint>0).
  // Research-only; skip zero-damage inventory echo later. Not a ship-default.
  let damagingAaMarkCount = 0
  if (
    cfg.emitDamagingModelAaFromTruth &&
    aaEvents.length > 0 &&
    aaIdentity
  ) {
    const earlyTruth = buildTruthActions({
      sqlitePath,
      killerId: check.killerId,
      victimId: check.victimId,
      startMs: windowStart,
      endMs: windowEnd,
      includeAllyTruth: cfg.includeAllyTruth,
      aaEvents,
      aaIdentity,
      aaLoaded,
    })
    const aaMarks: SkillMark[] = earlyTruth.truth
      .filter((a) => a.kind === 'aa')
      .map((a) => ({
        tMs: windowStart + Math.round(a.tSec * 1000),
        participantId:
          a.actorClass === 'killer' ? check.killerId : check.victimId,
        skillSlot: 0,
        ally: a.actorClass === 'ally',
        kind: 'aa' as const,
        share: 1,
      }))
    damagingAaMarkCount = aaMarks.length
    if (aaMarks.length) {
      marks = [...marks, ...aaMarks].sort((a, b) => a.tMs - b.tMs)
    }
  }


  // R36: opener ally attribution from same-match skill_used (not global share).
  // Opener gate uses FULL check.windowMs[0] (not burst-shifted start). FA ≠ odds.
  let openerAllyDisclosure: OpenerAllyAttribDisclosure | null = null
  if (cfg.openerAllyAttrib && cfg.openerAllyAttrib !== 'off') {
    const attribed = applyOpenerAllyAttrib({
      marks,
      sqlitePath,
      killerId: check.killerId,
      victimId: check.victimId,
      windowStartMs: check.windowMs[0],
      windowEndMs: windowEnd,
      attrib: {
        mode: cfg.openerAllyAttrib as OpenerAllyAttribMode,
        openerWindowSec: cfg.openerAllyWindowSec ?? 5,
        localWindowSec: cfg.openerAllyLocalSec ?? 2,
        openerAllyMin: cfg.openerAllyMin ?? 1,
        openerKillerMin: cfg.openerKillerMin ?? 0,
        discloseAllyMarks: cfg.openerAllyDiscloseMarks !== false,
        allyMarksLogOnly: true,
      },
    })
    marks = attribed.marks
    openerAllyDisclosure = attribed.disclosure
  }

  const aaFiller =
    cfg.emitDamagingModelAaFromTruth
      ? false
      : mode === 'action_aligned_aa' || mode === 'multi_caster' || cfg.aaFiller
  const useAction =
    mode === 'action_aligned' ||
    mode === 'action_aligned_aa' ||
    mode === 'gate_action' ||
    mode === 'multi_caster'
  const finishAaAfterLastMark = cfg.emitDamagingModelAaFromTruth
    ? false
    : cfg.finishAaAfterLastMark
  const aaAtEachMark = cfg.emitDamagingModelAaFromTruth
    ? false
    : cfg.aaAtEachMark

  let model: { tSec: number; hp: number }[]
  let firstLethalSec: number | null
  let method: string
  let markCount = 0
  let modelActionsOut: ActionRecord[] = []

  if (mode === 'baseline') {
    model = baseline.model
    firstLethalSec = baseline.firstLethalSec
    method = 'continuous_simulateMatchup'
  } else if (mode === 'gate_repin' || mode === 'cusum_gate') {
    if (mode === 'cusum_gate') {
      engageSec = cusumEngage ?? skillEngage ?? dropEngage
    } else {
      engageSec = skillEngage ?? dropEngage
    }
    if (engageSec == null) {
      model = baseline.model
      firstLethalSec = baseline.firstLethalSec
      method = `${mode}:fallback_baseline_no_engage`
    } else {
      const engageMs = windowStart + Math.round(engageSec * 1000)
      const kEng =
        nearestFrame(check.killerHp, engageMs) ?? nearestFrame(killerRows, engageMs)
      const vEng =
        nearestFrame(check.victimHp, engageMs) ?? nearestFrame(victimRows, engageMs)
      if (!kEng || !vEng) throw new Error('missing engage re-pin frames')
      const atkEngage = loadoutFromFrame(
        check.killerChamp,
        Number(kEng.level ?? check.killerLevel ?? 1),
        kEng,
      )
      const defEngage = loadoutFromFrame(
        check.victimChamp,
        Number(vEng.level ?? check.victimLevel ?? 1),
        vEng,
      )
      const gated = runGatedModelSeries(
        atk,
        def,
        actual,
        durationSec,
        engageSec,
        atkEngage,
        defEngage,
      )
      model = gated.model
      firstLethalSec = gated.firstLethalSec
      method = mode === 'cusum_gate' ? 'cusum_gate_repin' : 'gate_repin'
    }
  } else if (useAction) {
    // Re-pin at first killer mark when available
    let atkUse = atk
    let defUse = def
    const firstKillerMark = marks.find((m) => !m.ally)
    const hasFarPoke = markDebug.some((d) => d.keptReason === 'pre_engage_far')
    let gateEngage: number | null = null
    if (mode === 'gate_action') {
      if (markSelection === 'cusum_engage_then_skills' && selectedEngageSec != null) {
        // Far poke: keep CUSUM as AA/idle gate (do not open filler on attenuated casts).
        // Near opener / finish-window: selectedEngageSec may already be shifted.
        gateEngage = hasFarPoke
          ? (selectedCusumEngageSec ?? selectedEngageSec)
          : selectedEngageSec
        if (!hasFarPoke && firstKillerMark) {
          const firstKeptSec = (firstKillerMark.tMs - windowStart) / 1000
          if (firstKeptSec < gateEngage - 1e-9) {
            gateEngage = firstKeptSec
          }
        }
      } else {
        gateEngage = skillEngage ?? (firstKillerMark
          ? (firstKillerMark.tMs - windowStart) / 1000
          : null)
      }
    }
    if (firstKillerMark) {
      const pinMs =
        mode === 'gate_action' && gateEngage != null
          ? windowStart + Math.round(gateEngage * 1000)
          : firstKillerMark.tMs
      const kEng = nearestFrame(check.killerHp, pinMs)
      const vEng = nearestFrame(check.victimHp, pinMs)
      if (kEng && vEng) {
        atkUse = loadoutFromFrame(
          check.killerChamp,
          Number(kEng.level ?? check.killerLevel ?? 1),
          kEng,
        )
        defUse = loadoutFromFrame(
          check.victimChamp,
          Number(vEng.level ?? check.victimLevel ?? 1),
          vEng,
        )
      }
      engageSec = gateEngage ?? (firstKillerMark.tMs - windowStart) / 1000
    } else if (gateEngage != null) {
      engageSec = gateEngage
    }

    const actionEngage = mode === 'gate_action' ? engageSec : null
    let markLoadouts: Array<{ atk: FighterLoadout; def: FighterLoadout } | null> | undefined
    if (cfg.rePinEachMark) {
      const sortedMarks = [...marks]
        .sort((a, b) => a.tMs - b.tMs)
        .filter((m) => {
          const tSec = (m.tMs - windowStart) / 1000
          if (actionEngage != null && tSec < actionEngage - 1e-9) return false
          return true
        })
      markLoadouts = sortedMarks.map((m) => {
        const kEng = nearestFrame(check.killerHp, m.tMs)
        const vEng = nearestFrame(check.victimHp, m.tMs)
        if (!kEng || !vEng) return null
        return {
          atk: loadoutFromFrame(
            check.killerChamp,
            Number(kEng.level ?? check.killerLevel ?? 1),
            kEng,
          ),
          def: loadoutFromFrame(
            check.victimChamp,
            Number(vEng.level ?? check.victimLevel ?? 1),
            vEng,
          ),
        }
      })
    }

    const aligned = runActionAlignedSeries({
      atk: atkUse,
      def: defUse,
      actual,
      windowStartMs: windowStart,
      marks,
      pulseSec: cfg.castPulseSec,
      aaFiller,
      maxAa: cfg.maxAaBetweenMarks,
      allyShare: cfg.allyPulseShare,
      engageSec: actionEngage,
      idleHp: mode === 'gate_action' ? (def.liveStats?.hp ?? null) : null,
      idleFollowActual: cfg.idleFollowActual,
      finishAaAfterLastMark,
      finishAaMax: cfg.finishAaMax,
      finishAaWindowSec: cfg.finishAaWindowSec,
      killOffsetSec,
      aaAtEachMark,
      perSlotPulse: cfg.perSlotPulse,
      pulseBySlot: cfg.pulseBySlot,
      markLoadouts,
    })
    model = aligned.model
    firstLethalSec = aligned.firstLethalSec
    markCount = aligned.markCount
    modelActionsOut = aligned.modelActions
    method = mode
  } else {
    throw new Error(`unknown mode ${mode}`)
  }

  const errors = actual.map((a, i) => ({
    tSec: a.tSec,
    absErr: Math.abs((model[i]?.hp ?? 0) - a.hp),
    signedErr: (model[i]?.hp ?? 0) - a.hp,
  }))
  const maeHp =
    errors.length === 0 ? null : errors.reduce((s, e) => s + e.absErr, 0) / errors.length

  const sqrtBins = analyzeSqrtBins(
    errors.map((e) => ({
      tSec: e.tSec,
      signedErr: e.signedErr,
      absErr: e.absErr,
    })),
    durationSec,
  )
  const earlyEndSec = sqrtBins.bins[0]?.tEndSec ?? sqrtBins.pieceWidthSec
  // R42: GOAL early honesty = idle/pre-engage. When idleFollowActual, score
  // only samples strictly before engage (exclude engage dump from earlyMae).
  let earlyMaeEndSec = earlyEndSec
  let earlyMaeExclusiveEnd = false
  if (
    cfg.earlyMaePreEngageOnly &&
    cfg.idleFollowActual &&
    engageSec != null &&
    engageSec > 0
  ) {
    earlyMaeEndSec = Math.min(earlyEndSec, engageSec)
    earlyMaeExclusiveEnd = true
  }
  const earlyMaeRaw = earlyMaeExclusiveEnd
    ? maeOf(actual, model, 0, Math.max(0, earlyMaeEndSec - 1e-6))
    : maeOf(actual, model, 0, earlyMaeEndSec)
  // Vacuous pre-engage (engage≈0 / no samples): honest idle error = 0.
  const earlyMaeHp =
    earlyMaeRaw == null && earlyMaeExclusiveEnd ? 0 : (earlyMaeRaw as number)

  const earlyActual = actual.filter((a) =>
    earlyMaeExclusiveEnd
      ? a.tSec < earlyMaeEndSec - 1e-9
      : a.tSec <= earlyMaeEndSec + 1e-6,
  )
  const earlyModel = model.filter((a) =>
    earlyMaeExclusiveEnd
      ? a.tSec < earlyMaeEndSec - 1e-9
      : a.tSec <= earlyMaeEndSec + 1e-6,
  )
  const actualDrop =
    earlyActual.length >= 2
      ? earlyActual[0]!.hp - earlyActual[earlyActual.length - 1]!.hp
      : null
  const modelDrop =
    earlyModel.length >= 2
      ? earlyModel[0]!.hp - earlyModel[earlyModel.length - 1]!.hp
      : null
  const killerSkills = countKillerSkills(
    sqlitePath,
    check.killerId,
    windowStart,
    windowStart + Math.round(earlyEndSec * 1000),
  )
  const { falseAllIn } = classifyEarlyBin({ actualDrop, modelDrop, killerSkills })

  const lateCandidates = sqrtBins.bins.filter(
    (b) => binPhase(b.index, sqrtBins.binCount) === 'late',
  )
  const lateBin =
    (lateCandidates.length
      ? [...lateCandidates].sort(
          (a, b) => (b.priority ?? -1) - (a.priority ?? -1),
        )[0]
      : null) ?? sqrtBins.bins[sqrtBins.bins.length - 1]
  const lateActual = lateBin
    ? actual.filter(
        (a) =>
          a.tSec >= lateBin.tStartSec - 1e-6 && a.tSec <= lateBin.tEndSec + 1e-6,
      )
    : []
  const lateModel = lateBin
    ? model.filter(
        (a) =>
          a.tSec >= lateBin.tStartSec - 1e-6 && a.tSec <= lateBin.tEndSec + 1e-6,
      )
    : []
  const actualMinHpInWindow = actual.length
    ? Math.min(...actual.map((a) => a.hp))
    : null
  const { earlyPoisoned } = classifyLatePoison({
    modelHpAtLateStart: lateModel[0]?.hp ?? null,
    actualHpAtLateStart: lateActual[0]?.hp ?? null,
    actualMinHpInWindow,
  })
  const lateMaeHp = lateBin
    ? maeOf(actual, model, lateBin.tStartSec, lateBin.tEndSec)
    : null

  const lethalErrorSec =
    firstLethalSec == null ? null : firstLethalSec - killOffsetSec
  const killedInModel =
    firstLethalSec != null || (model[model.length - 1]?.hp ?? 1) <= 0

  const assistProbe = probeAssists(
    sqlitePath,
    check.killerId,
    check.victimId,
    check.tMs,
  )

  let actionReplay: CheckMetrics['actionReplay'] = null
  if (useAction) {
    // R44: truth filter uses the same mark-load domain as pre-burst lead.
    // tSec stays window-relative (lead skills negative) so we can remap onto
    // engage for matching — same transform as model marks. No invent.
    const truthDomainStart =
      preBurstLeadSec > 0 && !cfg.truthBurstWindowOnly
        ? skillLoadStart
        : windowStart
    const truthSet = buildTruthActions({
      sqlitePath,
      killerId: check.killerId,
      victimId: check.victimId,
      startMs: truthDomainStart,
      endMs: windowEnd,
      tSecOriginMs: windowStart,
      includeAllyTruth: cfg.includeAllyTruth,
      aaEvents,
      aaIdentity,
      aaLoaded,
    })
    const engageForTruthRemap =
      preBurstRemapEngageSec ??
      selectedCusumEngageSec ??
      selectedEngageSec ??
      0
    const truthRaw = truthSet.truth
    const truthForMatch =
      preBurstLeadSec > 0 &&
      !cfg.truthBurstWindowOnly &&
      cfg.truthPreBurstRemap !== false
        ? truthRaw.map((a) =>
            a.tSec < -1e-9
              ? { ...a, tSec: engageForTruthRemap }
              : a,
          )
        : truthRaw
    // Zero-damage inventory echo is FORBIDDEN as criterion-C evidence (GOAL #13).
    // Disclose echo count only — never fold shareHint=0 AA into modelActions for F1.
    const aaEcho = cfg.emitDamagingModelAaFromTruth
      ? []
      : modelAaEchoFromTruth(truthForMatch)
    const coverage: ActionCoverageResult = matchActions(
      truthForMatch,
      modelActionsOut,
      cfg.actionReplayTauSec,
    )
    const modelAaDamaging = modelActionsOut.filter(
      (a) => a.kind === 'aa' && (a.shareHint ?? 0) > 0,
    )
    const matchedDamagingAa = coverage.matches.filter((m) => {
      const t = truthForMatch[m.truthIdx]
      const md = modelActionsOut[m.modelIdx]
      return (
        t?.kind === 'aa' &&
        md?.kind === 'aa' &&
        (md.shareHint ?? 0) > 0
      )
    }).length
    actionReplay = {
      truthCount: coverage.truthCount,
      modelCount: coverage.modelCount,
      matchedCount: coverage.matchedCount,
      precision: coverage.precision,
      recall: coverage.recall,
      actionCoverage: coverage.actionCoverage,
      allyDisclosedCount: truthSet.allyDisclosedCount,
      summonerDisclosedCount: truthSet.summonerDisclosedCount,
    }
    if (writeAudit && seriesId != null && gameIndex != null) {
      const auditDir =
        argValue('--audit-dir', '') ||
        'docs/rofl-research/autoresearch/action_audits'
      const audit: ActionReplayAudit = {
        schema: 'pro-grid-action-replay-audit-v1',
        series: seriesId,
        gameIndex,
        check: checkN,
        segment,
        matchup: `${check.killerChamp}→${check.victimChamp}`,
        tau: cfg.actionReplayTauSec,
        truthActions: truthForMatch,
        modelActions: modelActionsOut,
        coverage,
        byKind: breakdownByKind(truthForMatch, modelActionsOut, coverage),
        disclosures: [
          ...truthSet.aaBridgeDisclosures,
          `aaTruthAvailable=${truthSet.aaTruthAvailable} aaTruthCount=${truthSet.aaTruthCount} aaGateEligible=${truthSet.aaGateEligible} (never invent from HPΔ; packetDecodeGate requires pro same-match decode)`,
          cfg.emitDamagingModelAaFromTruth
            ? `modelAaDamagingKitCount=${modelAaDamaging.length} matchedDamagingAa=${matchedDamagingAa} damagingAaMarks=${damagingAaMarkCount} (kit physical AA via kind:aa marks; shareHint>0; NO zero-damage echo; GOAL forbid #13)`
            : `modelAaEchoCount=${aaEcho.length} (DISCLOSED ONLY — not folded into modelActions; shareHint=0; GOAL forbid #13)`,
          `itemActiveTruthAvailable=${truthSet.itemActiveTruthAvailable} itemActiveTruthCount=${truthSet.itemActiveTruthCount} emitItemModelActions=${cfg.emitItemModelActions} itemPulseShare=${cfg.itemPulseShare ?? 0} (slim-v3 item_active_ability_used; model emits timed kind=item inventory${(cfg.itemPulseShare ?? 0) > 0 ? ' + disclosed kit pulse' : ' non-damage'}; item F1 gains do NOT set packetDecodeGate)`,
          `allyDisclosedCount=${truthSet.allyDisclosedCount} (ally skill_used near window; folded into truth only when includeAllyTruth=true; currently ${cfg.includeAllyTruth})`,
          `summonerDisclosedCount=${truthSet.summonerDisclosedCount} (evented summoner_spell_used; model does not emit summoner damage yet)`,
          `r44 truthDomainStartMs=${truthDomainStart} windowStartMs=${windowStart} preBurstLeadSec=${preBurstLeadSec} truthPreBurstRemap=${cfg.truthPreBurstRemap !== false && !cfg.truthBurstWindowOnly} engageRemapSec=${engageForTruthRemap} truthRawCount=${truthRaw.length} (honest mark-domain parity; FA≠odds; not fightOutcomeGate)`,
        ],
      }
      const auditPath = resolve(
        `${auditDir}/${seriesId}-g${gameIndex}-c${checkN}-${segment}.json`,
      )
      mkdirSync(dirname(auditPath), { recursive: true })
      writeFileSync(auditPath, JSON.stringify(audit, null, 2) + '\n', 'utf8')
    }
  }

  return {
    check: checkN,
    segment,
    matchup: `${check.killerChamp}→${check.victimChamp}`,
    earlyMaeHp,
    lateMaeHp,
    lateMaeDeltaVsBaseline: null,
    maeHp,
    lethalErrorSec,
    killedInModel,
    falseAllIn,
    earlyPoisoned,
    engageSec,
    skillMarks: markCount || marks.filter((m) => !m.ally).length,
    openerAllyAttrib: openerAllyDisclosure,
    method,
    modelEndHp: model[model.length - 1]?.hp ?? null,
    actualEndHp: actual[actual.length - 1]?.hp ?? null,
    assistProbe,
    markDebug: markDebug.filter((m) => !m.ally).slice(0, 24),
    actionReplay,
  }
}

function summarizeActionReplay(checks: CheckMetrics[]): SuiteResult['actionReplay'] {
  const withAr = checks.filter((c) => c.actionReplay != null)
  if (!withAr.length) return null
  const perWindow = withAr.map((c) => ({
    check: c.check,
    segment: c.segment,
    matchup: c.matchup,
    truthCount: c.actionReplay!.truthCount,
    modelCount: c.actionReplay!.modelCount,
    matchedCount: c.actionReplay!.matchedCount,
    precision: c.actionReplay!.precision,
    recall: c.actionReplay!.recall,
    actionCoverage: c.actionReplay!.actionCoverage,
  }))
  const mean =
    perWindow.reduce((s, w) => s + w.actionCoverage, 0) / perWindow.length
  const worst = [...perWindow].sort((a, b) => a.actionCoverage - b.actionCoverage)[0] ?? null
  const gate95 = perWindow.every((w) => w.actionCoverage >= 0.95)
  return {
    meanActionCoverage: mean,
    worstWindow: worst
      ? { check: worst.check, segment: worst.segment, actionCoverage: worst.actionCoverage }
      : null,
    gate95,
    perWindow,
  }
}

function printTable(checks: CheckMetrics[], composite: number, parts: SuiteResult['parts']) {
  console.log(
    [
      'chk',
      'seg',
      'earlyMAE',
      'mae',
      'lethErr',
      'kill',
      'poison',
      'falseAI',
      'marks',
      'method',
    ].join('\t'),
  )
  for (const c of checks) {
    console.log(
      [
        c.check,
        c.segment,
        c.earlyMaeHp?.toFixed(1) ?? 'null',
        c.maeHp?.toFixed(1) ?? 'null',
        c.lethalErrorSec?.toFixed(2) ?? 'null',
        c.killedInModel ? 'Y' : 'N',
        c.earlyPoisoned ? 'Y' : 'N',
        c.falseAllIn ? 'Y' : 'N',
        c.skillMarks,
        c.method,
      ].join('\t'),
    )
  }
  console.log(
    `composite=${composite.toFixed(4)}  early=${parts.meanEarlyMae.toFixed(1)}  mae=${parts.meanMae.toFixed(1)}  |leth|=${parts.meanLethalAbs.toFixed(2)}  poisonPen=${parts.latePoisonPenalty}`,
  )
}

function annotateLateDeltas(
  checks: CheckMetrics[],
  baselineByKey: Map<string, CheckMetrics>,
): void {
  for (const c of checks) {
    const b = baselineByKey.get(`${c.check}:${c.segment}`)
    if (c.lateMaeHp != null && b?.lateMaeHp != null) {
      c.lateMaeDeltaVsBaseline = c.lateMaeHp - b.lateMaeHp
    }
  }
}

function printShipChecklist(cl: ShipChecklist, candidate: boolean, gate: boolean) {
  const rows: Array<[string, boolean | null]> = [
    ['A1 early idle', cl.A1_check02_full_early_idle],
    ['A2 c02 burst leth', cl.A2_check02_burst_lethal_pm2],
    ['A3 c01 path', cl.A3_check01_burst_path_improved],
    ['A4 strict leth', cl.A4_strict_lethal_01_02_full_burst],
    ['A5 c03 early', cl.A5_check03_early_not_hurt],
    ['A6 poison prefer', cl.A6_poison_clear_prefer],
    ['A6min c03 burst', cl.A6_min_check03_burst_poison_clear],
    ['A7 late MAE', cl.A7_late_mae_01_02_not_hurt],
    ['A8 hard fails', cl.A8_hard_fails_clean],
  ]
  console.log(
    'shipChecklist:\t' +
      rows.map(([k, v]) => `${k}=${v == null ? '?' : v ? 'Y' : 'N'}`).join(' | '),
  )
  console.log(
    `shipGateCandidate=${candidate}  shipGate=${gate}  holdoutB=${cl.holdout_B_burst_lethal_pm2 == null ? 'n/a' : cl.holdout_B_burst_lethal_pm2 ? 'Y' : 'N'}`,
  )
}

function main() {
  const suite = argValue('--suite', '2970110-g1')
  const mode = resolveMode()
  const outPath = resolve(
    argValue('--out', 'docs/rofl-research/autoresearch/last_eval.json'),
  )
  const logResults = process.argv.includes('--log-results')
  const hypothesis = argValue('--hypothesis', EXPERIMENT.hypothesis)
  const diagnosePath = argValue('--diagnose-out', '')

  const pulseCli = argValue('--pulse-sec', '')
  const nearKillCli = argValue('--near-kill-sec', '')
  const finishAaMaxCli = argValue('--finish-aa-max', '')
  const allyShareCli = argValue('--ally-share', '')
  const cfg = {
    ...EXPERIMENT,
    mode,
    hypothesis,
    castPulseSec: pulseCli ? Number(pulseCli) : EXPERIMENT.castPulseSec,
    aaFiller:
      process.argv.includes('--aa-filler') ||
      mode === 'action_aligned_aa' ||
      mode === 'multi_caster' ||
      EXPERIMENT.aaFiller,
    finishAaAfterLastMark: process.argv.includes('--no-finish-aa')
      ? false
      : process.argv.includes('--finish-aa') || EXPERIMENT.finishAaAfterLastMark,
    finishAaMax: finishAaMaxCli
      ? Number(finishAaMaxCli)
      : EXPERIMENT.finishAaMax,
    aaAtEachMark: process.argv.includes('--no-aa-at-mark')
      ? false
      : process.argv.includes('--aa-at-mark') || EXPERIMENT.aaAtEachMark,
    markMinGapSec: (() => {
      const raw = argValue('--mark-min-gap', '')
      return raw ? Number(raw) : EXPERIMENT.markMinGapSec
    })(),
    markFinishHorizonSec: (() => {
      const raw = argValue('--finish-horizon', '')
      return raw ? Number(raw) : EXPERIMENT.markFinishHorizonSec
    })(),
    maxKillerMarks: (() => {
      const raw = argValue('--max-killer-marks', '')
      return raw ? Number(raw) : EXPERIMENT.maxKillerMarks
    })(),
    markDensityWindowSec: (() => {
      const raw = argValue('--dense-window', '')
      return raw ? Number(raw) : EXPERIMENT.markDensityWindowSec
    })(),
    markDenseMaxPerWindow: (() => {
      const raw = argValue('--dense-max', '')
      return raw ? Number(raw) : EXPERIMENT.markDenseMaxPerWindow
    })(),
    preEngageOpenerSec: (() => {
      const raw = argValue('--pre-engage-opener-sec', '')
      return raw ? Number(raw) : EXPERIMENT.preEngageOpenerSec
    })(),
    preEngageOpenerMaxPostMarks: (() => {
      const raw = argValue('--pre-engage-opener-max-post', '')
      return raw ? Number(raw) : EXPERIMENT.preEngageOpenerMaxPostMarks
    })(),
    preEngageOpenerShare: (() => {
      const raw = argValue('--pre-engage-opener-share', '')
      return raw ? Number(raw) : EXPERIMENT.preEngageOpenerShare
    })(),
    preEngageOpenerShareSlots: (() => {
      const raw = argValue('--pre-engage-opener-share-slots', '')
      if (!raw) return EXPERIMENT.preEngageOpenerShareSlots
      return raw
        .split(',')
        .map((s) => Number(s.trim()))
        .filter((n) => Number.isFinite(n) && n > 0)
    })(),
    markPreEngageLeadSec: (() => {
      const raw = argValue('--pre-engage-lead', '')
      return raw ? Number(raw) : EXPERIMENT.markPreEngageLeadSec
    })(),
    markPreEngageFarSec: (() => {
      const raw = argValue('--pre-engage-far', '')
      return raw ? Number(raw) : EXPERIMENT.markPreEngageFarSec
    })(),
    markPreEngageFarShare: (() => {
      const raw = argValue('--pre-engage-far-share', '')
      return raw ? Number(raw) : EXPERIMENT.markPreEngageFarShare
    })(),
    markPreBurstSkillLeadSec: (() => {
      if (process.argv.includes('--no-pre-burst-lead')) return 0
      const raw = argValue('--pre-burst-lead', '')
      return raw ? Number(raw) : EXPERIMENT.markPreBurstSkillLeadSec
    })(),
    markPreBurstSkillShare: (() => {
      const raw = argValue('--pre-burst-share', '')
      return raw ? Number(raw) : EXPERIMENT.markPreBurstSkillShare
    })(),
    markPreBurstDelaySec: (() => {
      const raw = argValue('--pre-burst-delay', '')
      return raw ? Number(raw) : EXPERIMENT.markPreBurstDelaySec
    })(),
    earlyMaePreEngageOnly: process.argv.includes('--no-early-mae-pre-engage')
      ? false
      : process.argv.includes('--early-mae-pre-engage') ||
        EXPERIMENT.earlyMaePreEngageOnly,
    truthBurstWindowOnly: process.argv.includes('--truth-burst-window-only'),
    truthPreBurstRemap: !process.argv.includes('--no-truth-pre-burst-remap'),
    preEngageShiftEngageToOpener: process.argv.includes('--no-pre-engage-shift')
      ? false
      : EXPERIMENT.preEngageShiftEngageToOpener,
    preEngageHostSeries: argValue(
      '--pre-engage-host-series',
      EXPERIMENT.preEngageHostSeries,
    ),
    rePinEachMark:
      process.argv.includes('--repin-each-mark') || EXPERIMENT.rePinEachMark,
    perSlotPulse:
      process.argv.includes('--per-slot-pulse') ||
      Boolean(argValue('--pulse-by-slot', '')) ||
      EXPERIMENT.perSlotPulse,
    pulseBySlot: (() => {
      const raw = argValue('--pulse-by-slot', '')
      if (!raw) return EXPERIMENT.pulseBySlot
      // Research: "1:0.4,2:0,3:0.4,4:0" — slot:pulseSec (utility slots may be 0).
      const out: Record<number, number> = { ...EXPERIMENT.pulseBySlot }
      for (const part of raw.split(',')) {
        const [ks, vs] = part.split(':')
        const k = Number(ks)
        const v = Number(vs)
        if (Number.isFinite(k) && Number.isFinite(v) && k > 0) out[k] = v
      }
      return out
    })(),
    useDropConditioning: process.argv.includes('--no-drop-filter')
      ? false
      : EXPERIMENT.useDropConditioning,
    markSelection: (() => {
      const raw = argValue('--mark-selection', '')
      if (
        raw === 'near_hp_drop' ||
        raw === 'post_engage_killer_skills' ||
        raw === 'cusum_engage_then_skills'
      ) {
        return raw
      }
      if (process.argv.includes('--no-drop-filter')) {
        return 'post_engage_killer_skills' as KillWindowMarkSelection
      }
      return EXPERIMENT.markSelection
    })(),
    markAlwaysNearKillSec: nearKillCli
      ? Number(nearKillCli)
      : EXPERIMENT.markAlwaysNearKillSec,
    allyPulseShare: allyShareCli
      ? Number(allyShareCli)
      : EXPERIMENT.allyPulseShare,
    actionReplayTauSec: (() => {
      const raw = argValue('--tau', '')
      return raw ? Number(raw) : EXPERIMENT.actionReplayTauSec
    })(),
    includeAllyTruth:
      process.argv.includes('--ally-truth') || EXPERIMENT.includeAllyTruth,
    emitItemModelActions: process.argv.includes('--no-item-model')
      ? false
      : process.argv.includes('--item-model') || EXPERIMENT.emitItemModelActions,
    itemPulseShare: (() => {
      const raw = argValue('--item-pulse-share', '')
      return raw ? Number(raw) : EXPERIMENT.itemPulseShare
    })(),
    basicAttackJsonl: argValue('--basic-attack-jsonl', EXPERIMENT.basicAttackJsonl),
    aaIdentityPath: argValue('--aa-identity', EXPERIMENT.aaIdentityPath),
    emitDamagingModelAaFromTruth:
      process.argv.includes('--emit-damaging-model-aa') ||
      EXPERIMENT.emitDamagingModelAaFromTruth,
    zeroDeadActualHp: process.argv.includes('--no-zero-dead-actual')
      ? false
      : process.argv.includes('--zero-dead-actual') || EXPERIMENT.zeroDeadActualHp,
    openerAllyAttrib: (() => {
      const raw = argValue('--opener-ally-attrib', '')
      if (
        raw === 'off' ||
        raw === 'opener_skill_share' ||
        raw === 'opener_hp_neighborhood' ||
        raw === 'local_skill_share'
      ) {
        return raw
      }
      return EXPERIMENT.openerAllyAttrib
    })(),
    openerAllyWindowSec: (() => {
      const raw = argValue('--opener-ally-window', '')
      return raw ? Number(raw) : EXPERIMENT.openerAllyWindowSec
    })(),
    openerAllyDiscloseMarks: process.argv.includes('--no-opener-ally-disclose')
      ? false
      : process.argv.includes('--opener-ally-disclose') ||
        EXPERIMENT.openerAllyDiscloseMarks,
    openerAllyLocalSec: (() => {
      const raw = argValue('--opener-ally-local', '')
      return raw ? Number(raw) : EXPERIMENT.openerAllyLocalSec
    })(),
    openerAllyMin: (() => {
      const raw = argValue('--opener-ally-min', '')
      return raw ? Number(raw) : EXPERIMENT.openerAllyMin
    })(),
    openerKillerMin: (() => {
      const raw = argValue('--opener-killer-min', '')
      return raw ? Number(raw) : EXPERIMENT.openerKillerMin
    })(),
    idleFollowActual: process.argv.includes('--no-idle-follow-actual')
      ? false
      : process.argv.includes('--idle-follow-actual') ||
        EXPERIMENT.idleFollowActual,
  }

  const resolved = resolveSuitePaths(suite)
  const { inputPath, seriesId, gameIndex, isHoldout } = resolved
  // Optional research override (e.g. slim-v3 under docs/.../r21/) — does not rewrite suite defaults.
  const sqliteOverride = argValue('--sqlite', '')
  const sqlitePath = sqliteOverride
    ? resolve(sqliteOverride)
    : resolved.sqlitePath
  if (!existsSync(inputPath)) throw new Error(`missing input ${inputPath}`)
  if (!existsSync(sqlitePath)) throw new Error(`missing sqlite ${sqlitePath}`)

  const aaJsonlPath = cfg.basicAttackJsonl ? resolve(cfg.basicAttackJsonl) : ''
  const aaIdPath = cfg.aaIdentityPath ? resolve(cfg.aaIdentityPath) : ''
  const aaLoaded = aaJsonlPath ? loadAaResearchJsonl(aaJsonlPath) : null
  const aaIdentity = aaIdPath ? loadAaIdentityBind(aaIdPath) : null
  const aaEvents = aaLoaded?.events ?? []

  const file = JSON.parse(readFileSync(inputPath, 'utf8')) as CrossCheckFile
  const segments: Array<'full' | 'burst'> = ['full', 'burst']
  const checkNs = [1, 2, 3]

  // Always compute baseline map for hard-fail / ship notes
  const baselineChecks: CheckMetrics[] = []
  for (const checkN of checkNs) {
    const check = file.crossChecks[checkN - 1]
    if (!check) throw new Error(`missing check ${checkN}`)
    for (const segment of segments) {
      baselineChecks.push(
        runOneCheck({
          check,
          checkN,
          segment,
          sqlitePath,
          mode: 'baseline',
          cfg: { ...cfg, mode: 'baseline' },
        }),
      )
    }
  }
  const baselineByKey = new Map(
    baselineChecks.map((c) => [`${c.check}:${c.segment}`, c] as const),
  )
  const baselineComposite = computeComposite(baselineChecks).composite

  let checks: CheckMetrics[]
  if (mode === 'baseline') {
    checks = baselineChecks
  } else {
    checks = []
    for (const checkN of checkNs) {
      const check = file.crossChecks[checkN - 1]!
      for (const segment of segments) {
        checks.push(
          runOneCheck({
            check,
            checkN,
            segment,
            sqlitePath,
            mode,
            cfg,
            seriesId,
            gameIndex,
            writeAudit: !process.argv.includes('--no-action-replay-audit'),
            aaEvents,
            aaIdentity,
            aaLoaded,
          }),
        )
      }
    }
  }
  annotateLateDeltas(checks, baselineByKey)

  const { composite, parts } = computeComposite(checks)
  const fails = hardFailsAgainstBaseline(checks, baselineByKey)
  let holdoutFromDev: ShipChecklist | null = null
  const mergeHoldoutPath = argValue('--merge-holdout', '')
  if (mergeHoldoutPath && existsSync(resolve(mergeHoldoutPath))) {
    const h = JSON.parse(readFileSync(resolve(mergeHoldoutPath), 'utf8')) as {
      shipChecklist?: ShipChecklist
    }
    holdoutFromDev = h.shipChecklist ?? null
  }
  const {
    checklist: shipChecklist,
    shipGateCandidate,
    shipGate,
    notes: shipNotes,
  } = evalShipChecklist(checks, baselineByKey, fails, {
    isHoldout,
    holdoutFromDev,
  })
  const keepCandidate = fails.length === 0 && composite < baselineComposite - 1e-9
  const actionReplaySummary = summarizeActionReplay(checks)

  const result: SuiteResult = {
    schema: 'pro-grid-action-aligned-suite-v1',
    t: new Date().toISOString(),
    hypothesis,
    mode,
    seriesId,
    gameIndex,
    config: cfg,
    checks,
    composite,
    parts,
    hardFails: fails,
    shipChecklist,
    shipGateCandidate,
    shipGate,
    shipNotes,
    baselineComposite,
    keepCandidate,
    actionReplay: actionReplaySummary,
  }

  // P10 freezeEvalWire: refuse last_eval / KEEP-candidate writes if freeze drifted.
  if (/last_eval/i.test(outPath) || keepCandidate) {
    const freeze = assertProductFreeze()
    if (!freeze.ok) {
      throw new Error(
        `freezeEvalWire: refuse write ${outPath}: ${freeze.failures.join('; ')}`,
      )
    }
  }

  mkdirSync(dirname(outPath), { recursive: true })
  writeFileSync(outPath, JSON.stringify(result, null, 2) + '\n', 'utf8')

  if (diagnosePath) {
    const c01 = {
      full: checks.find((c) => c.check === 1 && c.segment === 'full'),
      burst: checks.find((c) => c.check === 1 && c.segment === 'burst'),
      baselineFull: baselineByKey.get('1:full'),
      baselineBurst: baselineByKey.get('1:burst'),
    }
    const diag = {
      t: result.t,
      suite,
      mode,
      config: cfg,
      check01: c01,
      assistProbe: {
        full: c01.full?.assistProbe,
        burst: c01.burst?.assistProbe,
      },
      markDebug: {
        full: c01.full?.markDebug,
        burst: c01.burst?.markDebug,
      },
      modelEndHp: {
        full: c01.full?.modelEndHp,
        burst: c01.burst?.modelEndHp,
      },
      actualEndHp: {
        full: c01.full?.actualEndHp,
        burst: c01.burst?.actualEndHp,
      },
      shipChecklist,
    }
    const dp = resolve(diagnosePath)
    mkdirSync(dirname(dp), { recursive: true })
    writeFileSync(dp, JSON.stringify(diag, null, 2) + '\n', 'utf8')
    console.log(`diagnose=${dp}`)
  }

  console.log(`\n=== ${mode} | ${hypothesis} ===`)
  printTable(checks, composite, parts)
  if (actionReplaySummary) {
    console.log(
      `actionReplay: meanCoverage=${actionReplaySummary.meanActionCoverage!.toFixed(3)}  ` +
        `worst=${actionReplaySummary.worstWindow ? `c${actionReplaySummary.worstWindow.check}-${actionReplaySummary.worstWindow.segment}=${actionReplaySummary.worstWindow.actionCoverage.toFixed(3)}` : 'n/a'}  ` +
        `gate95=${actionReplaySummary.gate95}`,
    )
    for (const w of actionReplaySummary.perWindow) {
      console.log(
        `  c${w.check}-${w.segment}\t${w.matchup}\ttruth=${w.truthCount}\tmodel=${w.modelCount}\tmatched=${w.matchedCount}\tP=${w.precision.toFixed(2)}\tR=${w.recall.toFixed(2)}\tF1=${w.actionCoverage.toFixed(3)}`,
      )
    }
  }
  console.log(`baselineComposite=${baselineComposite.toFixed(4)}  keepCandidate=${keepCandidate}`)
  if (fails.length) console.log('HARD FAILS:', fails.join('; '))
  printShipChecklist(shipChecklist, shipGateCandidate, shipGate)
  console.log('shipNotes:', shipNotes.join(' | '))
  console.log(`out=${outPath}`)

  if (logResults) {
    const line = {
      t: result.t,
      hypothesis,
      keep: false, // caller decides keep vs best.json; instrumentation default false
      composite,
      baselineComposite,
      mode,
      hardFails: fails,
      shipGateCandidate,
      shipGate,
      shipChecklist,
      notes: shipNotes.join('; '),
      actionReplay: actionReplaySummary
        ? {
            meanActionCoverage: actionReplaySummary.meanActionCoverage,
            worstWindow: actionReplaySummary.worstWindow,
            gate95: actionReplaySummary.gate95,
          }
        : null,
      path: outPath,
    }
    const resultsPath = resolve('docs/rofl-research/autoresearch/results.jsonl')
    appendFileSync(resultsPath, JSON.stringify(line) + '\n', 'utf8')
    console.log(`logged → ${resultsPath}`)
  }
}

main()
