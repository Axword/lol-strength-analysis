/**
 * R36 — opener ally attribution from same-match skill_used (timeline/SQLite).
 *
 * Teamfight opener overkill (check03): 1v1 full-share on early killer marks
 * while allies also cast. Prefer skill_used count / local shares + disclosed
 * allyMarks (logOnly by default — no invent HP/combat/damage).
 *
 * NOT a global window coefficient (R26 trap). Prefer per-mark local shares;
 * finish marks with no local allies keep share=1. FA ≠ odds.
 */
import { DatabaseSync } from 'node:sqlite'
import { existsSync } from 'node:fs'

export type OpenerAllyAttribMode =
  | 'off'
  /** killer/(killer+ally) skill_used counts in opener — disclosed proxy */
  | 'opener_skill_share'
  /**
   * Victim HP-drop neighborhood (±attribMs) attributed to killer vs ally skills
   * in opener. Falls back to skill_share when no attributable early drops.
   */
  | 'opener_hp_neighborhood'
  /**
   * Per-mark local skill_used share (±localSec) for same-team allies.
   * Optional openerAllyMin gate: only activate when opener has ≥N ally skills.
   */
  | 'local_skill_share'

export type OpenerAllyAttribOpts = {
  mode: OpenerAllyAttribMode
  /** Opener horizon from window start (sec). Default 5. */
  openerWindowSec?: number
  /** HP-neighborhood half-window (ms). Default 750. */
  hpAttribMs?: number
  /** Local skill share half-window (sec). Default 2. */
  localWindowSec?: number
  /**
   * Minimum opener ally skill_used to activate attrib (default 1).
   * R26 used 5 as a global gate — here it only enables per-mark local shares.
   */
  openerAllyMin?: number
  /**
   * Require ≥N killer skill_used in opener to activate (default 0).
   * Set 1 to skip windows where killer is absent from the opener teamfight
   * (S1 Cass mid-fight spam) while still catching check03 opener overkill.
   */
  openerKillerMin?: number
  /**
   * Emit same-team ally skill_used in opener as ally marks.
   * Default logOnly (disclosed; shareHint=0 — no invent ally kit damage).
   */
  discloseAllyMarks?: boolean
  /** When discloseAllyMarks: force logOnly (default true). */
  allyMarksLogOnly?: boolean
  /** Floor for killer share when allies present (default 0.05). */
  minKillerShare?: number
}

export type SkillMarkLike = {
  tMs: number
  participantId: number
  skillSlot: number
  ally: boolean
  kind?: 'skill' | 'item' | 'aa'
  logOnly?: boolean
  share?: number
}

export type OpenerAllyAttribDisclosure = {
  mode: OpenerAllyAttribMode
  openerWindowSec: number
  localWindowSec: number
  openerAllyMin: number
  openerKillerMin: number
  killerSkillsOpener: number
  allySkillsOpener: number
  skillShareProxy: number
  hpKillerShare: number | null
  appliedKillerShare: number
  scaledKillerMarks: number
  meanLocalShare: number | null
  allyMarksDisclosed: number
  allyMarksLogOnly: boolean
  note: string
}

export type OpenerAllyAttribResult<T extends SkillMarkLike> = {
  marks: T[]
  disclosure: OpenerAllyAttribDisclosure
}

function rosterTeam(db: DatabaseSync, pid: number): number | null {
  const row = db
    .prepare(`SELECT team_id FROM roster WHERE participant_id = ?`)
    .get(pid) as { team_id: number } | undefined
  return row?.team_id != null ? Number(row.team_id) : null
}

function loadWindowSkillRows(
  db: DatabaseSync,
  startMs: number,
  endMs: number,
): { game_time_ms: number; participant_id: number }[] {
  return db
    .prepare(
      `SELECT game_time_ms, participant_id FROM events
       WHERE schema = 'skill_used'
         AND game_time_ms >= ? AND game_time_ms <= ?
       ORDER BY game_time_ms ASC`,
    )
    .all(startMs, endMs) as {
    game_time_ms: number
    participant_id: number
  }[]
}

/** Same-team ally skill_used in [startMs, endMs] — never enemies/victim. */
export function countOpenerSkillUsed(opts: {
  sqlitePath: string
  killerId: number
  victimId: number
  startMs: number
  openerEndMs: number
}): { killer: number; ally: number; allyEvents: SkillMarkLike[] } {
  const { sqlitePath, killerId, victimId, startMs, openerEndMs } = opts
  if (!existsSync(sqlitePath) || openerEndMs <= startMs) {
    return { killer: 0, ally: 0, allyEvents: [] }
  }
  const db = new DatabaseSync(sqlitePath, { readOnly: true })
  try {
    try {
      db.exec('PRAGMA busy_timeout=5000')
    } catch {
      /* ignore */
    }
    const killerTeam = rosterTeam(db, killerId)
    const teamCache = new Map<number, number | null>()
    const teamOf = (pid: number) => {
      if (teamCache.has(pid)) return teamCache.get(pid)!
      const t = rosterTeam(db, pid)
      teamCache.set(pid, t)
      return t
    }
    const rows = db
      .prepare(
        `SELECT game_time_ms, participant_id, payload_json FROM events
         WHERE schema = 'skill_used'
           AND game_time_ms >= ? AND game_time_ms <= ?
         ORDER BY game_time_ms ASC`,
      )
      .all(startMs, openerEndMs) as {
      game_time_ms: number
      participant_id: number
      payload_json: string
    }[]
    let killer = 0
    let ally = 0
    const allyEvents: SkillMarkLike[] = []
    for (const r of rows) {
      const pid = Number(r.participant_id)
      if (pid === victimId) continue
      let skillSlot = 0
      try {
        const p = JSON.parse(r.payload_json) as { skillSlot?: number }
        skillSlot = Number(p.skillSlot ?? 0)
      } catch {
        skillSlot = 0
      }
      if (pid === killerId) {
        killer++
        continue
      }
      if (killerTeam == null) continue
      if (teamOf(pid) === killerTeam) {
        ally++
        allyEvents.push({
          tMs: Number(r.game_time_ms),
          participantId: pid,
          skillSlot,
          ally: true,
          kind: 'skill',
          logOnly: true,
        })
      }
    }
    return { killer, ally, allyEvents }
  } finally {
    db.close()
  }
}

/**
 * Attribute opener HP drops (>5) to nearest skill_used actor within ±attribMs.
 * Returns killerShare in [0,1] or null when no attributable drops.
 */
export function openerHpNeighborhoodKillerShare(opts: {
  sqlitePath: string
  killerId: number
  victimId: number
  startMs: number
  openerEndMs: number
  attribMs?: number
}): number | null {
  const {
    sqlitePath,
    killerId,
    victimId,
    startMs,
    openerEndMs,
    attribMs = 750,
  } = opts
  if (!existsSync(sqlitePath)) return null
  const db = new DatabaseSync(sqlitePath, { readOnly: true })
  try {
    try {
      db.exec('PRAGMA busy_timeout=5000')
    } catch {
      /* ignore */
    }
    const killerTeam = rosterTeam(db, killerId)
    const skills = loadWindowSkillRows(db, startMs, openerEndMs)
    const hp = db
      .prepare(
        `SELECT game_time_ms, health FROM frames
         WHERE participant_id = ?
           AND game_time_ms >= ? AND game_time_ms <= ?
           AND health IS NOT NULL
         ORDER BY game_time_ms ASC`,
      )
      .all(victimId, startMs, openerEndMs) as {
      game_time_ms: number
      health: number
    }[]
    let killerDmg = 0
    let allyDmg = 0
    for (let i = 1; i < hp.length; i++) {
      const prev = hp[i - 1]!
      const cur = hp[i]!
      const drop = Number(prev.health) - Number(cur.health)
      if (!(drop > 5)) continue
      const mid = (Number(prev.game_time_ms) + Number(cur.game_time_ms)) / 2
      let best: { participant_id: number } | null = null
      let bestD = Infinity
      for (const s of skills) {
        const d = Math.abs(Number(s.game_time_ms) - mid)
        if (d <= attribMs && d < bestD) {
          bestD = d
          best = s
        }
      }
      if (!best) continue
      const pid = Number(best.participant_id)
      if (pid === killerId) killerDmg += drop
      else if (
        killerTeam != null &&
        pid !== victimId &&
        rosterTeam(db, pid) === killerTeam
      ) {
        allyDmg += drop
      }
    }
    const denom = killerDmg + allyDmg
    if (denom <= 0) return null
    return killerDmg / denom
  } finally {
    db.close()
  }
}

export function applyOpenerAllyAttrib<T extends SkillMarkLike>(opts: {
  marks: T[]
  sqlitePath: string
  killerId: number
  victimId: number
  windowStartMs: number
  /** Full window end — used for local_skill_share neighborhood. */
  windowEndMs?: number
  attrib: OpenerAllyAttribOpts
}): OpenerAllyAttribResult<T> {
  const mode = opts.attrib.mode
  const openerWindowSec = opts.attrib.openerWindowSec ?? 5
  const localWindowSec = opts.attrib.localWindowSec ?? 2
  const openerAllyMin = opts.attrib.openerAllyMin ?? 1
  const openerKillerMin = opts.attrib.openerKillerMin ?? 0
  const discloseAlly = opts.attrib.discloseAllyMarks ?? true
  const allyLogOnly = opts.attrib.allyMarksLogOnly ?? true
  const minShare = opts.attrib.minKillerShare ?? 0.05
  const openerEndMs =
    opts.windowStartMs + Math.round(openerWindowSec * 1000)
  const localMs = Math.round(localWindowSec * 1000)

  const empty: OpenerAllyAttribDisclosure = {
    mode,
    openerWindowSec,
    localWindowSec,
    openerAllyMin,
    openerKillerMin,
    killerSkillsOpener: 0,
    allySkillsOpener: 0,
    skillShareProxy: 1,
    hpKillerShare: null,
    appliedKillerShare: 1,
    scaledKillerMarks: 0,
    meanLocalShare: null,
    allyMarksDisclosed: 0,
    allyMarksLogOnly: allyLogOnly,
    note: 'off',
  }

  if (mode === 'off') {
    return { marks: opts.marks, disclosure: empty }
  }

  const counts = countOpenerSkillUsed({
    sqlitePath: opts.sqlitePath,
    killerId: opts.killerId,
    victimId: opts.victimId,
    startMs: opts.windowStartMs,
    openerEndMs,
  })
  const skillShareProxy =
    counts.ally <= 0
      ? 1
      : counts.killer / Math.max(1, counts.killer + counts.ally)

  let hpKillerShare: number | null = null
  if (mode === 'opener_hp_neighborhood') {
    hpKillerShare = openerHpNeighborhoodKillerShare({
      sqlitePath: opts.sqlitePath,
      killerId: opts.killerId,
      victimId: opts.victimId,
      startMs: opts.windowStartMs,
      openerEndMs,
      attribMs: opts.attrib.hpAttribMs ?? 750,
    })
  }

  const activate =
    counts.ally >= openerAllyMin && counts.killer >= openerKillerMin
  let applied =
    mode === 'opener_hp_neighborhood' && hpKillerShare != null
      ? hpKillerShare
      : skillShareProxy
  if (activate && mode !== 'local_skill_share') {
    applied = Math.max(minShare, Math.min(1, applied))
  } else if (!activate) {
    applied = 1
  }

  let scaled = 0
  const localShares: number[] = []
  let out: T[] = [...opts.marks]

  if (mode === 'local_skill_share' && activate && existsSync(opts.sqlitePath)) {
    const db = new DatabaseSync(opts.sqlitePath, { readOnly: true })
    try {
      try {
        db.exec('PRAGMA busy_timeout=5000')
      } catch {
        /* ignore */
      }
      const killerTeam = rosterTeam(db, opts.killerId)
      const endMs = opts.windowEndMs ?? openerEndMs + 60_000
      const skills = loadWindowSkillRows(db, opts.windowStartMs, endMs)
      const teamCache = new Map<number, number | null>()
      const teamOf = (pid: number) => {
        if (teamCache.has(pid)) return teamCache.get(pid)!
        const t = rosterTeam(db, pid)
        teamCache.set(pid, t)
        return t
      }
      out = opts.marks.map((m) => {
        if (m.ally || m.logOnly || m.kind === 'item') return m
        let k = 0
        let a = 0
        for (const s of skills) {
          if (Math.abs(Number(s.game_time_ms) - m.tMs) > localMs) continue
          const pid = Number(s.participant_id)
          if (pid === opts.victimId) continue
          if (pid === opts.killerId) {
            k++
            continue
          }
          if (killerTeam != null && teamOf(pid) === killerTeam) a++
        }
        if (a <= 0) return m
        const share = Math.max(minShare, k / Math.max(1, k + a))
        localShares.push(share)
        scaled++
        return { ...m, share }
      })
      applied =
        localShares.length > 0
          ? localShares.reduce((x, y) => x + y, 0) / localShares.length
          : 1
    } finally {
      db.close()
    }
  } else if (mode !== 'local_skill_share') {
    out = opts.marks.map((m) => {
      if (m.ally || m.logOnly) return m
      if (m.kind === 'item') return m
      if (m.tMs > openerEndMs) return m
      if (!activate) return m
      scaled++
      return { ...m, share: applied }
    })
  }

  let allyMarksDisclosed = 0
  if (activate && discloseAlly && counts.allyEvents.length) {
    for (const a of counts.allyEvents) {
      out.push({
        ...(a as T),
        logOnly: allyLogOnly,
        share: allyLogOnly ? 0 : applied,
      })
      allyMarksDisclosed++
    }
    out.sort((a, b) => a.tMs - b.tMs)
  }

  const note = !activate
    ? `opener ally=${counts.ally}/min${openerAllyMin} killer=${counts.killer}/min${openerKillerMin}; no attrib`
    : mode === 'local_skill_share'
      ? `per-mark local±${localWindowSec}s skill_used shares; scaled=${scaled}; mean=${applied.toFixed(3)}; allyMarks logOnly disclose`
      : mode === 'opener_hp_neighborhood' && hpKillerShare != null
        ? `opener HP-neighborhood killerShare=${applied.toFixed(3)} (skillProxy=${skillShareProxy.toFixed(3)}); finish marks untouched`
        : `opener skill_used killerShare=${applied.toFixed(3)} (${counts.killer}/${counts.killer + counts.ally}); finish marks untouched`

  return {
    marks: out,
    disclosure: {
      mode,
      openerWindowSec,
      localWindowSec,
      openerAllyMin,
      openerKillerMin,
      killerSkillsOpener: counts.killer,
      allySkillsOpener: counts.ally,
      skillShareProxy,
      hpKillerShare,
      appliedKillerShare: applied,
      scaledKillerMarks: scaled,
      meanLocalShare: localShares.length ? applied : null,
      allyMarksDisclosed,
      allyMarksLogOnly: allyLogOnly,
      note,
    },
  }
}

/**
 * Product/timeline path: scale killer actionMarks in opener; optionally
 * annotate allyMarks as logOnly disclosures.
 */
export function applyOpenerAllyAttribToActionMarks(opts: {
  actionMarks: Array<{
    tSec: number
    skillSlot?: number
    ally?: boolean
    share?: number
    logOnly?: boolean
    kind?: 'skill' | 'item' | 'aa'
  }>
  allyMarks?: Array<{
    tSec: number
    skillSlot?: number
    ally?: boolean
    share?: number
    logOnly?: boolean
    kind?: 'skill' | 'item' | 'aa'
  }>
  killerSkillsOpener: number
  allySkillsOpener: number
  openerWindowSec?: number
  mode?: Exclude<OpenerAllyAttribMode, 'off'>
  hpKillerShare?: number | null
  discloseAllyLogOnly?: boolean
}): {
  actionMarks: typeof opts.actionMarks
  allyMarks: NonNullable<typeof opts.allyMarks>
  disclosure: OpenerAllyAttribDisclosure
} {
  const openerWindowSec = opts.openerWindowSec ?? 5
  const mode = opts.mode ?? 'opener_skill_share'
  const skillShareProxy =
    opts.allySkillsOpener <= 0
      ? 1
      : opts.killerSkillsOpener /
        Math.max(1, opts.killerSkillsOpener + opts.allySkillsOpener)
  let applied =
    mode === 'opener_hp_neighborhood' && opts.hpKillerShare != null
      ? opts.hpKillerShare
      : skillShareProxy
  if (opts.allySkillsOpener > 0) {
    applied = Math.max(0.05, Math.min(1, applied))
  } else {
    applied = 1
  }
  let scaled = 0
  const actionMarks = opts.actionMarks.map((m) => {
    if (m.ally || m.logOnly) return m
    if ((m.tSec ?? 0) > openerWindowSec) return m
    if (opts.allySkillsOpener <= 0) return m
    scaled++
    return { ...m, share: applied }
  })
  const allyMarks = (opts.allyMarks ?? []).map((m) =>
    opts.discloseAllyLogOnly === false
      ? m
      : { ...m, ally: true as const, logOnly: true, share: 0 },
  )
  return {
    actionMarks,
    allyMarks,
    disclosure: {
      mode,
      openerWindowSec,
      localWindowSec: 2,
      openerAllyMin: 1,
      openerKillerMin: 0,
      killerSkillsOpener: opts.killerSkillsOpener,
      allySkillsOpener: opts.allySkillsOpener,
      skillShareProxy,
      hpKillerShare: opts.hpKillerShare ?? null,
      appliedKillerShare: applied,
      scaledKillerMarks: scaled,
      meanLocalShare: null,
      allyMarksDisclosed: allyMarks.length,
      allyMarksLogOnly: opts.discloseAllyLogOnly !== false,
      note:
        opts.allySkillsOpener <= 0
          ? 'no_opener_ally_skills'
          : `opener attrib share=${applied.toFixed(3)}`,
    },
  }
}
