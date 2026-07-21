import { useEffect, useMemo, useRef, useState } from 'react'
import { CHAMPIONS, championIconUrl } from '../data/champions'
import { ITEMS } from '../data/items'
import {
  attributeDrakeBuffs,
  attributeGrubTouchFromCareer,
  attributeSustain,
  formatGrubTouchAudit,
  grubAttributionNote,
} from '../engine/careerStats'
import {
  histColumnsByWinCorrelation,
  histOrderNote,
  histPhase,
  type HistStatKey,
} from '../engine/histWinCorrelation'
import { combatModsFromObjectives, type TeamObjectives } from '../engine/objectives'
import { buildStats } from '../engine/stats'
import type { GameSnapshot, GameUnit } from '../game/types'
import './ChampHistoryBoard.css'

type BoardTab = 'champs' | 'all'

type SortKey = 'champ' | HistStatKey

const STAT_LABELS: Record<HistStatKey, (tab: BoardTab) => string> = {
  dmg: (tab) => (tab === 'champs' ? 'Dmg to champs' : 'Dmg dealt'),
  taken: (tab) => (tab === 'champs' ? 'Taken (champs)' : 'Taken'),
  mitigated: () => 'Mitigated',
  ccOrTurret: (tab) => (tab === 'champs' ? 'CC' : 'Turrets'),
  drake: () => 'Drake use',
  grub: () => 'Grub Touch',
  as: () => 'AS',
  ah: () => 'AH',
  gold: () => 'Gold',
  extra: (tab) => (tab === 'champs' ? 'Sustain' : 'Farm / vision'),
}

type SortDir = 'asc' | 'desc'

interface Props {
  snapshot: GameSnapshot
}

function fmt(n: number): string {
  if (!Number.isFinite(n)) return '—'
  if (Math.abs(n) >= 1000) return `${(n / 1000).toFixed(1)}k`
  return String(Math.round(n))
}

function pct(n: number): string {
  return `${Math.round(n * 100)}%`
}

function ahFromItems(itemIds: string[]): number {
  return itemIds.reduce((sum, id) => sum + (ITEMS[id]?.stats?.abilityHaste ?? 0), 0)
}

function omnivampFromItems(itemIds: string[]): number {
  return itemIds.reduce((sum, id) => sum + (ITEMS[id]?.stats?.omnivamp ?? 0), 0)
}

/** Shop gold currently sitting in inventory (completed/component prices). */
function goldInItems(itemIds: string[]): number {
  return itemIds.reduce((sum, id) => sum + (ITEMS[id]?.gold ?? 0), 0)
}

/**
 * Live ability haste: item catalog (+ hextech dragon stacks).
 * Riot spectator `cooldownReduction` is unused post-AH and stays 0 in our feeds.
 */
function abilityHaste(
  unit: GameUnit,
  teamObj?: TeamObjectives | null,
  gameTimeSec = 0,
): number {
  let ah = 0
  try {
    ah = buildStats(unit.loadout).abilityHaste
  } catch {
    ah = ahFromItems(unit.loadout.itemIds)
  }
  if (teamObj) {
    ah += combatModsFromObjectives(teamObj, gameTimeSec).abilityHaste
  }
  return ah
}

/** Feed `as` / career.asPct is % of base (100 = baseline). Convert to APS. */
function attackSpeedDisplay(unit: GameUnit): { aps: number; pctOfBase: number } {
  const c = unit.career
  const pctOfBase = c?.asPct ?? 100
  const champ = CHAMPIONS[unit.loadout.championId]
  const base = champ?.stats.attackspeed ?? 0.625
  return { aps: base * (pctOfBase / 100), pctOfBase }
}

function sortValue(
  unit: GameUnit,
  key: SortKey,
  tab: BoardTab,
  obj: GameSnapshot['score'],
  gameTimeSec: number,
): number | string {
  const c = unit.career
  if (key === 'champ') {
    return CHAMPIONS[unit.loadout.championId]?.name ?? unit.loadout.championId
  }
  if (!c) return 0
  const teamObj = unit.team === 'blue' ? obj?.blue : obj?.red
  const dmgFocus = tab === 'champs' ? c.dmgToChamps : c.dmgTotal
  const takenFocus = tab === 'champs' ? c.dmgTakenFromChamps : c.dmgTaken
  const drake = attributeDrakeBuffs(teamObj, c, gameTimeSec)
  const grub = attributeGrubTouchFromCareer(c, teamObj?.voidGrubs ?? 0)
  const sustain = attributeSustain(c, omnivampFromItems(unit.loadout.itemIds))

  switch (key) {
    case 'dmg':
      return dmgFocus
    case 'taken':
      return takenFocus
    case 'mitigated':
      return c.selfMitigated
    case 'ccOrTurret':
      return tab === 'champs' ? c.ccToChamps : c.dmgToTurrets
    case 'drake':
      return drake.sortValue
    case 'grub':
      return grub.sortValue
    case 'as':
      return attackSpeedDisplay(unit).aps
    case 'ah':
      return abilityHaste(unit, teamObj, gameTimeSec)
    case 'gold':
      return c.gold
    case 'extra':
      return tab === 'champs' ? sustain.sortValue : c.cs
    default:
      return 0
  }
}

function DrakeCell({
  unit,
  teamObj,
  gameTimeSec,
}: {
  unit: GameUnit
  teamObj: TeamObjectives | null | undefined
  gameTimeSec: number
}) {
  const c = unit.career!
  const drake = attributeDrakeBuffs(teamObj, c, gameTimeSec)
  const title = [
    drake.tags.length ? `Buffs: ${drake.tags.join(', ')}` : 'No dragon buffs',
    drake.infernalBonusDmg > 0
      ? `Infernal use ≈ +${Math.round(drake.infernalBonusDmg)} (phys/magic × AD/AP%/(1+%))`
      : '',
    drake.mountainMitigated > 0
      ? `Mountain use ≈ +${Math.round(drake.mountainMitigated)} mitigated (self-mit × resist%/(1+%))`
      : '',
    drake.soulBonusDmg > 0
      ? `Chemtech soul amp ≈ +${Math.round(drake.soulBonusDmg)}`
      : '',
    drake.soulMitigated > 0
      ? `Chemtech soul DR ≈ +${Math.round(drake.soulMitigated)} mitigated`
      : '',
    drake.chemHspBonus > 0
      ? `Chem HSP use ≈ +${Math.round(drake.chemHspBonus)} heal/shield`
      : '',
    drake.cloudMsPct > 0
      ? `Cloud/soul MS ${pct(drake.cloudMsPct)} (OoC; no pathing distance in feed)`
      : '',
  ]
    .filter(Boolean)
    .join('\n')

  if (drake.quantities.length === 0) {
    return (
      <td title={title}>
        —
        <em>no dragons</em>
      </td>
    )
  }

  const head = drake.quantities[0]
  const rest = drake.quantities.slice(1).join(' · ')
  return (
    <td title={title}>
      {head}
      {rest ? <em>{rest}</em> : <em>{drake.tags.slice(0, 2).join(' · ') || 'use'}</em>}
    </td>
  )
}

function GrubCell({
  unit,
  teamObj,
  expanded,
  onToggle,
}: {
  unit: GameUnit
  teamObj: TeamObjectives | null | undefined
  expanded: boolean
  onToggle: () => void
}) {
  const c = unit.career!
  const grub = attributeGrubTouchFromCareer(c, teamObj?.voidGrubs ?? 0)
  const a = grub.audit

  if (grub.stacks <= 0) {
    return (
      <td title="No void grubs">
        —
        <em>no grubs</em>
      </td>
    )
  }

  return (
    <td className={`hist-grub conf-${a.confidence}`}>
      <button
        type="button"
        className="hist-audit-btn"
        onClick={onToggle}
        aria-expanded={expanded}
        title="Toggle Touch audit trail (estimated burn model)"
      >
        {grub.touchDmg > 0 ? (
          <>
            ~{fmt(grub.touchDmg)}
            <span className={`hist-conf hist-conf-${a.confidence}`}>{a.confidence}</span>
          </>
        ) : (
          'ready'
        )}
        <em>
          {grub.note}
          {grub.touchDmg > 0
            ? ` · ${a.burnUptimeSec.toFixed(1)}s burn · ${a.plateProgressGold.toFixed(0)}g plate`
            : ''}
        </em>
      </button>
      {expanded && (
        <div className="hist-audit" role="region" aria-label="Touch of the Void audit">
          <table className="hist-audit-table">
            <thead>
              <tr>
                <th>Stacks</th>
                <th>Dmg/tick</th>
                <th>True DPS</th>
                <th>Burn (s)</th>
                <th>Touch est.</th>
                <th>AA refreshes</th>
                <th>Rejected</th>
                <th>Plate-eq</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>
                  {a.stacks} {a.role}
                </td>
                <td>
                  {a.tick}/{a.tickInterval}s
                </td>
                <td>{a.trueDps}</td>
                <td>{a.burnUptimeSec.toFixed(1)}</td>
                <td>~{Math.round(a.touchTrue)}</td>
                <td>{a.refreshAa}</td>
                <td>
                  far {a.rejectedFar} · size {a.rejectedAbility} · skill {a.rejectedSkill}
                </td>
                <td>{a.plateProgressGold.toFixed(1)}g</td>
              </tr>
            </tbody>
          </table>
          <p className="hist-audit-cycle">
            Turret feed {fmt(a.turretDmg)}
            {a.residualTrusted
              ? ` · residual ${fmt(a.residualTurret ?? 0)} · Touch share ${pct(a.touchShare ?? 0)}`
              : ' · residual untrusted (mixed Riot turret stat — not turret−Touch)'}
            . Full 4s cycle = {a.cycleTrueDmg} true. Hunger{' '}
            {a.hungerActive ? `on · ${a.hungerProcs} mite proc(s)` : 'off'}. Brief ceiling{' '}
            {a.briefCeilingTrue} true / {a.briefCeilingPlateGold.toFixed(1)}g (8s, no mite) —
            article scenario, not measured.
          </p>
          <ul className="hist-audit-assumptions">
            {a.assumptions.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
          <pre className="hist-audit-raw">{formatGrubTouchAudit(a)}</pre>
        </div>
      )}
    </td>
  )
}

function StatCell({
  keyName,
  unit,
  tab,
  teamObj,
  gameTimeSec,
  grubOpen,
  onToggleGrub,
}: {
  keyName: HistStatKey
  unit: GameUnit
  tab: BoardTab
  teamObj: TeamObjectives | null | undefined
  gameTimeSec: number
  grubOpen: boolean
  onToggleGrub: () => void
}) {
  const c = unit.career!
  const dmgFocus = tab === 'champs' ? c.dmgToChamps : c.dmgTotal
  const takenFocus = tab === 'champs' ? c.dmgTakenFromChamps : c.dmgTaken
  const sustain = attributeSustain(c, omnivampFromItems(unit.loadout.itemIds))
  const ah = abilityHaste(unit, teamObj, gameTimeSec)
  const as = attackSpeedDisplay(unit)

  switch (keyName) {
    case 'dmg':
      return (
        <td title="Damage dealt">
          {fmt(dmgFocus)}
          {tab === 'champs' && (
            <em>
              {fmt(c.physToChamps)}/{fmt(c.magicToChamps)}/{fmt(c.trueToChamps)}
            </em>
          )}
        </td>
      )
    case 'taken':
      return <td title="Damage taken">{fmt(takenFocus)}</td>
    case 'mitigated':
      return <td title="Self-mitigated">{fmt(c.selfMitigated)}</td>
    case 'ccOrTurret':
      return tab === 'champs' ? (
        <td title="CC to champions (s)">{c.ccToChamps.toFixed(1)}s</td>
      ) : (
        <td title="Turret / building / objectives">
          {fmt(c.dmgToTurrets)}
          <em>
            bld {fmt(c.dmgToBuildings)} · obj {fmt(c.dmgToObjectives)}
          </em>
        </td>
      )
    case 'drake':
      return <DrakeCell unit={unit} teamObj={teamObj} gameTimeSec={gameTimeSec} />
    case 'grub':
      return (
        <GrubCell unit={unit} teamObj={teamObj} expanded={grubOpen} onToggle={onToggleGrub} />
      )
    case 'as':
      return (
        <td title={`Attack speed: ${as.aps.toFixed(3)} APS · ${Math.round(as.pctOfBase)}% of champion base`}>
          {as.aps.toFixed(2)}
          <em>{Math.round(as.pctOfBase)}% base</em>
        </td>
      )
    case 'ah':
      return (
        <td title="Ability haste from items (+ hextech dragon stacks when present)">
          {Math.round(ah)}
          <em>AH</em>
        </td>
      )
    case 'gold':
      return (
        <td title="Total gold earned · shop value of current items · unspent gold in bag">
          {fmt(c.gold)}
          <em>
            items {fmt(goldInItems(unit.loadout.itemIds))} · bag{' '}
            {fmt(c.goldBag ?? Math.max(0, c.gold - goldInItems(unit.loadout.itemIds)))}
          </em>
        </td>
      )
    case 'extra':
      return (
        <td title="Ally heal + shield; live regen; LS / SV / item omnivamp">
          {tab === 'champs' ? (
            <>
              {sustain.supportTotal > 0 ? fmt(sustain.supportTotal) : fmt(sustain.hpRegen) + '/s'}
              <em>
                {sustain.supportTotal > 0
                  ? `heal ${fmt(sustain.healAlly)} · shld ${fmt(sustain.shieldAlly)} · `
                  : ''}
                regen {fmt(sustain.hpRegen)}/s
                {sustain.lifeSteal > 0 ? ` · LS ${sustain.lifeSteal}%` : ''}
                {sustain.spellVamp > 0 ? ` · SV ${sustain.spellVamp}%` : ''}
                {sustain.omnivampItems > 0 ? ` · OV ${pct(sustain.omnivampItems)}` : ''}
              </em>
            </>
          ) : (
            <>
              CS {c.cs}
              <em>
                vis {c.visionScore}
                {sustain.supportTotal > 0
                  ? ` · sustain ${fmt(sustain.supportTotal)}`
                  : ` · regen ${fmt(sustain.hpRegen)}/s`}
              </em>
            </>
          )}
        </td>
      )
  }
}

function Row({
  unit,
  tab,
  teamObj,
  gameTimeSec,
  columnKeys,
  grubOpen,
  onToggleGrub,
}: {
  unit: GameUnit
  tab: BoardTab
  teamObj: TeamObjectives | null | undefined
  gameTimeSec: number
  columnKeys: HistStatKey[]
  grubOpen: boolean
  onToggleGrub: () => void
}) {
  const c = unit.career
  const champ = CHAMPIONS[unit.loadout.championId]
  if (!c) {
    return (
      <tr className={`hist-row team-${unit.team}`}>
        <td className="hist-champ">
          <img src={championIconUrl(unit.loadout.championId)} alt="" width={22} height={22} />
          <span>{champ?.name ?? unit.loadout.championId}</span>
        </td>
        <td colSpan={columnKeys.length} className="hist-empty">
          No career stats at this frame
        </td>
      </tr>
    )
  }

  return (
    <tr className={`hist-row team-${unit.team} ${unit.alive === false ? 'dead' : ''}`}>
      <td className="hist-champ">
        <img src={championIconUrl(unit.loadout.championId)} alt="" width={22} height={22} />
        <div>
          <strong>{champ?.name ?? unit.loadout.championId}</strong>
          <span>
            {unit.team} · lv{unit.loadout.level} · {c.kills}/{c.deaths}/{c.assists}
          </span>
        </div>
      </td>
      {columnKeys.map((key) => (
        <StatCell
          key={key}
          keyName={key}
          unit={unit}
          tab={tab}
          teamObj={teamObj}
          gameTimeSec={gameTimeSec}
          grubOpen={grubOpen}
          onToggleGrub={onToggleGrub}
        />
      ))}
    </tr>
  )
}

function SortTh({
  label,
  sortKey,
  activeKey,
  dir,
  onSort,
  title,
}: {
  label: string
  sortKey: SortKey
  activeKey: SortKey
  dir: SortDir
  onSort: (key: SortKey) => void
  title?: string
}) {
  const active = activeKey === sortKey
  return (
    <th
      aria-sort={active ? (dir === 'asc' ? 'ascending' : 'descending') : 'none'}
      title={title}
    >
      <button type="button" className={`hist-sort ${active ? 'active' : ''}`} onClick={() => onSort(sortKey)}>
        {label}
        <span className="hist-sort-ind" aria-hidden>
          {active ? (dir === 'asc' ? ' ↑' : ' ↓') : ''}
        </span>
      </button>
    </th>
  )
}

export function ChampHistoryBoard({ snapshot }: Props) {
  const [tab, setTab] = useState<BoardTab>('champs')
  const [sortKey, setSortKey] = useState<SortKey>('gold')
  const [sortDir, setSortDir] = useState<SortDir>('desc')
  const [grubAuditPid, setGrubAuditPid] = useState<string | null>(null)
  const userSorted = useRef(false)
  const lastAutoPhase = useRef<string | null>(null)

  const columnOrder = useMemo(
    () => histColumnsByWinCorrelation(snapshot.gameTimeSec, tab),
    [snapshot.gameTimeSec, tab],
  )
  const columnKeys = useMemo(() => columnOrder.map((c) => c.key), [columnOrder])
  const phase = histPhase(snapshot.gameTimeSec)
  const orderNote = useMemo(() => histOrderNote(snapshot.gameTimeSec), [snapshot.gameTimeSec])

  // Default sort tracks the top win-correlation column when phase/tab changes,
  // until the user picks a sort manually.
  useEffect(() => {
    const autoKey = `${phase}:${tab}`
    if (lastAutoPhase.current === autoKey) return
    lastAutoPhase.current = autoKey
    if (userSorted.current) return
    const top = columnOrder[0]?.key
    if (top) {
      setSortKey(top)
      setSortDir('desc')
    }
  }, [phase, tab, columnOrder])

  const blueObj = snapshot.score?.blue
  const redObj = snapshot.score?.red

  const rows = useMemo(() => {
    return [...snapshot.units].sort((a, b) => {
      const va = sortValue(a, sortKey, tab, snapshot.score, snapshot.gameTimeSec)
      const vb = sortValue(b, sortKey, tab, snapshot.score, snapshot.gameTimeSec)
      let cmp = 0
      if (typeof va === 'string' && typeof vb === 'string') {
        cmp = va.localeCompare(vb)
      } else {
        cmp = Number(va) - Number(vb)
      }
      if (cmp === 0) {
        if (a.team !== b.team) return a.team === 'blue' ? -1 : 1
        const na = CHAMPIONS[a.loadout.championId]?.name ?? a.loadout.championId
        const nb = CHAMPIONS[b.loadout.championId]?.name ?? b.loadout.championId
        return na.localeCompare(nb)
      }
      return sortDir === 'asc' ? cmp : -cmp
    })
  }, [snapshot.units, snapshot.score, snapshot.gameTimeSec, sortKey, sortDir, tab])

  const hasCareer = rows.some((u) => u.career)

  function onSort(key: SortKey) {
    userSorted.current = true
    if (key === sortKey) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortKey(key)
      setSortDir(key === 'champ' ? 'asc' : 'desc')
    }
  }

  const blueDrake = attributeDrakeBuffs(blueObj, null)
  const redDrake = attributeDrakeBuffs(redObj, null)

  return (
    <section className="hist-board" aria-label="Champion history at this time">
      <header className="hist-head">
        <div>
          <h3>Champion history</h3>
          <p>
            Cumulative stats to {Math.floor(snapshot.gameTimeSec / 60)}:
            {String(Math.floor(snapshot.gameTimeSec % 60)).padStart(2, '0')}
          </p>
        </div>
        <div className="hist-tabs" role="tablist">
          <button
            type="button"
            role="tab"
            aria-selected={tab === 'champs'}
            className={tab === 'champs' ? 'active' : ''}
            onClick={() => {
              userSorted.current = false
              setTab('champs')
            }}
          >
            Against champions
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={tab === 'all'}
            className={tab === 'all' ? 'active' : ''}
            onClick={() => {
              userSorted.current = false
              setTab('all')
            }}
          >
            All
          </button>
        </div>
      </header>

      {!hasCareer ? (
        <p className="hist-missing">
          Career stats not loaded for this source. Timeline frames need enrichment.
        </p>
      ) : (
        <>
          <div className="hist-meta">
            <span>
              Blue objs:{' '}
              {blueDrake.quantities.length
                ? blueDrake.quantities.join(' · ')
                : blueDrake.tags.length
                  ? blueDrake.tags.join(' · ')
                  : 'no dragons'}
              {(blueObj?.voidGrubs ?? 0) > 0
                ? ` · ${grubAttributionNote(blueObj!.voidGrubs)}`
                : ''}
            </span>
            <span>
              Red objs:{' '}
              {redDrake.quantities.length
                ? redDrake.quantities.join(' · ')
                : redDrake.tags.length
                  ? redDrake.tags.join(' · ')
                  : 'no dragons'}
              {(redObj?.voidGrubs ?? 0) > 0
                ? ` · ${grubAttributionNote(redObj!.voidGrubs)}`
                : ''}
            </span>
            <span className="hist-order-note" title={orderNote}>
              {orderNote}
            </span>
          </div>

          <div className="hist-table-wrap">
            <table className="hist-table">
              <thead>
                <tr>
                  <SortTh label="Champion" sortKey="champ" activeKey={sortKey} dir={sortDir} onSort={onSort} />
                  {columnOrder.map(({ key, weight }) => (
                    <SortTh
                      key={key}
                      label={STAT_LABELS[key](tab)}
                      sortKey={key}
                      activeKey={sortKey}
                      dir={sortDir}
                      onSort={onSort}
                      title={`Win-relevance weight ${weight.toFixed(0)} @ ${phase}`}
                    />
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((u) => (
                  <Row
                    key={u.id}
                    unit={u}
                    tab={tab}
                    teamObj={u.team === 'blue' ? blueObj : redObj}
                    gameTimeSec={snapshot.gameTimeSec}
                    columnKeys={columnKeys}
                    grubOpen={grubAuditPid === u.id}
                    onToggleGrub={() =>
                      setGrubAuditPid((cur) => (cur === u.id ? null : u.id))
                    }
                  />
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  )
}
