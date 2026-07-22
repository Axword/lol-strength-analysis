import { useEffect, useMemo, useRef, useState } from 'react'
import { SAMPLE_SNAPSHOTS } from '../data/sampleGames'
import { CHAMPIONS } from '../data/champions'
import { parseSnapshotJson } from '../game/parseSnapshot'
import {
  defaultRegistryMatch,
  loadBuiltinTimeline,
  loadMatchRegistry,
  loadRegisteredTimeline,
  parseTimelineFile,
  snapshotAtTime,
  type BuiltinTimelineId,
  type GameTimeline,
  type MatchRegistry,
  type MatchRegistryEntry,
} from '../game/timeline'
import { formatGameTime } from '../game/parseSnapshot'
import type { GameSnapshot, GameUnit, TeamSide } from '../game/types'
import type { MatchupInput } from '../engine/types'
import { pickTradeModeForGameTime } from '../engine/fightDuration'
import { ChampHistoryBoard } from './ChampHistoryBoard'
import { MapView, UnitRoster } from './MapView'
import { Scoreboard } from './Scoreboard'
import './GameReview.css'

interface Props {
  onSendToCalculator: (matchup: MatchupInput, label: string) => void
}

type SourceMode = 'timeline' | 'sample' | 'import'
export type TimelineChoice =
  | `match:${string}`
  | `research:${BuiltinTimelineId}`
  | 'local'
  | ''

const PLAY_SPEEDS = [1, 2, 4, 8] as const

function compactCoverage(value: string): string {
  if (value === 'full_at_sampled_frames') return 'native'
  if (value === 'kda_total_cs_vision_at_sampled_frames') return 'KDA/CS/vision'
  return value.replaceAll('_', ' ')
}

export function MatchPicker({
  registry,
  value,
  localTimelineName,
  onChange,
}: {
  registry: MatchRegistry | null
  value: TimelineChoice
  localTimelineName: string | null
  onChange: (choice: TimelineChoice) => void
}) {
  return (
    <label>
      Match
      <select
        value={value}
        onChange={(event) => onChange(event.target.value as TimelineChoice)}
      >
        {value === 'local' && (
          <option value="local" disabled>
            {localTimelineName ?? 'Local timeline'}
          </option>
        )}
        {!value && (
          <option value="" disabled>
            No product match selected
          </option>
        )}
        {registry && registry.matches.length > 0 && (
          <optgroup label="Published matches">
            {registry.matches.map((entry) => (
              <option key={entry.matchCode} value={`match:${entry.matchCode}`}>
                {entry.matchCode}
                {entry.matchCode === registry.defaultMatchCode ? ' (default)' : ''}
              </option>
            ))}
          </optgroup>
        )}
        <optgroup label="Research fixtures">
          <option value="research:fur_parity">FUR parity fixture (demo)</option>
          <option value="research:maknee_stub">Maknee packet fixture (demo)</option>
        </optgroup>
      </select>
    </label>
  )
}

export function MatchCoverageBadges({
  entry,
  research,
}: {
  entry: MatchRegistryEntry | null
  research: boolean
}) {
  const badges = entry
    ? [
        ['Pos', entry.coverage.positions],
        ['Hist', entry.coverage.history],
        ['HP', entry.coverage.hp],
        ['Combat', entry.coverage.combat],
        ['Ranks', entry.coverage.ranks],
      ]
    : research
      ? [
          ['Pos', 'demo'],
          ['Hist', 'demo'],
          ['HP', 'untrusted'],
          ['Combat', 'untrusted'],
          ['Ranks', 'untrusted'],
        ]
      : []
  if (badges.length === 0) return null
  return (
    <>
      <div
        className="match-coverage-badges"
        aria-label={research ? 'Research fixture coverage' : 'Published match coverage'}
      >
        {badges.map(([label, value]) => (
          <span
            key={label}
            className={`coverage-badge ${
              value === 'none' || value === 'untrusted' ? 'unavailable' : ''
            }`}
            title={`${label} coverage: ${value.replaceAll('_', ' ')}`}
          >
            <strong>{label}</strong> {compactCoverage(value)}
          </span>
        ))}
        {entry && (
          <span
            className={`coverage-badge ${
              entry.productGates.calculatorReady ? 'ready' : 'unavailable'
            }`}
            title="Validated publication result; live frame gates still control calculator handoff"
          >
            <strong>Calc</strong>{' '}
            {entry.productGates.calculatorReady ? 'ready' : 'blocked'}
          </span>
        )}
      </div>
      {research && (
        <span className="research-fixture-label">
          Research fixture · demo only · calculator blocked
        </span>
      )}
    </>
  )
}

export function calculatorTrustBlockReason({
  research,
  positionBlocked,
  combatStateBlocked,
}: {
  research: boolean
  positionBlocked: boolean
  combatStateBlocked: boolean
}): string | null {
  if (research) {
    return 'Research fixtures are demo-only and cannot be sent to the product calculator'
  }
  if (positionBlocked) return 'Live replay positions are required'
  if (combatStateBlocked) {
    return 'Positions are real but HP, ability ranks, and combat stats are unavailable from this replay feed'
  }
  return null
}

export function GameReview({ onSendToCalculator }: Props) {
  const [timeline, setTimeline] = useState<GameTimeline | null>(null)
  const [timelineError, setTimelineError] = useState<string | null>(null)
  const [registry, setRegistry] = useState<MatchRegistry | null>(null)
  const [registryStatus, setRegistryStatus] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [timelineChoice, setTimelineChoice] = useState<TimelineChoice>('')
  const [localTimelineName, setLocalTimelineName] = useState<string | null>(null)
  const [timelineFileError, setTimelineFileError] = useState<string | null>(null)
  const timelineFileInputRef = useRef<HTMLInputElement>(null)
  /** Continuous playhead in game ms — drives fluid playback via lerp. */
  const [playheadMs, setPlayheadMs] = useState(8 * 60 * 1000)
  const [playing, setPlaying] = useState(false)
  const [playSpeed, setPlaySpeed] = useState<(typeof PLAY_SPEEDS)[number]>(4)

  const [source, setSource] = useState<SourceMode>('timeline')
  const [sampleId, setSampleId] = useState(SAMPLE_SNAPSHOTS[0].id)
  const [imported, setImported] = useState<GameSnapshot | null>(null)

  const [selectedIds, setSelectedIds] = useState<string[]>([])
  const [showXh, setShowXh] = useState(true)
  const [fogViewer, setFogViewer] = useState<TeamSide | 'shared' | 'none'>('blue')
  const [importText, setImportText] = useState('')
  const [importError, setImportError] = useState<string | null>(null)
  const [showImport, setShowImport] = useState(false)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    loadMatchRegistry()
      .then((loaded) => {
        if (cancelled) return
        setRegistry(loaded)
        const initial = defaultRegistryMatch(loaded)
        if (initial) {
          setTimelineChoice(`match:${initial.matchCode}`)
          setRegistryStatus(null)
        } else {
          setRegistryStatus('No product-validated matches are published yet.')
          setSource('sample')
          setLoading(false)
        }
      })
      .catch((error: Error) => {
        if (cancelled) return
        setRegistry(null)
        setRegistryStatus(error.message)
        setSource('sample')
        setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    if (!timelineChoice) return
    if (timelineChoice === 'local') {
      setLoading(false)
      return
    }
    const registered =
      timelineChoice.startsWith('match:')
        ? registry?.matches.find(
            (entry) => entry.matchCode === timelineChoice.slice('match:'.length),
          )
        : null
    if (timelineChoice.startsWith('match:') && !registered) {
      setTimeline(null)
      setTimelineError('Selected match is not present in the product registry.')
      setSource('sample')
      setLoading(false)
      return
    }
    const researchId = timelineChoice.startsWith('research:')
      ? (timelineChoice.slice('research:'.length) as BuiltinTimelineId)
      : null
    let cancelled = false
    setLoading(true)
    setTimelineError(null)
    setTimeline(null)
    const request = registered
      ? loadRegisteredTimeline(registered)
      : loadBuiltinTimeline(researchId as BuiltinTimelineId)
    request
      .then((data) => {
        if (cancelled) return
        setTimeline(data)
        const start =
          researchId === 'maknee_stub'
            ? Math.min(60_000, Math.floor((data.durationMs || 0) / 3))
            : registered || researchId === 'fur_parity'
              ? Math.min(10 * 60 * 1000, Math.floor((data.durationMs || 0) * 0.4))
              : 8 * 60 * 1000
        setPlayheadMs(start)
        setSource('timeline')
        setLoading(false)
      })
      .catch((err: Error) => {
        if (cancelled) return
        setTimelineError(err.message)
        setSource('sample')
        setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [timelineChoice, registry])

  // Fluid playback: advance playhead by wall-clock × speed, interpolate between frames
  const playSpeedRef = useRef(playSpeed)
  playSpeedRef.current = playSpeed
  useEffect(() => {
    if (!playing || !timeline || source !== 'timeline') return
    let raf = 0
    let last = performance.now()
    const endMs = timeline.durationMs || timeline.frames[timeline.frames.length - 1]?.t || 0
    const tick = (now: number) => {
      const dt = Math.min(0.05, (now - last) / 1000) // clamp hitch spikes
      last = now
      setPlayheadMs((ms) => {
        const next = ms + dt * playSpeedRef.current * 1000
        if (next >= endMs) {
          setPlaying(false)
          return endMs
        }
        return next
      })
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [playing, timeline, source])

  const snapshot: GameSnapshot | null = useMemo(() => {
    if (source === 'timeline' && timeline) {
      return snapshotAtTime(timeline, playheadMs)
    }
    if (source === 'import' && imported) return imported
    if (source === 'sample') {
      return SAMPLE_SNAPSHOTS.find((s) => s.id === sampleId) ?? SAMPLE_SNAPSHOTS[0]
    }
    return null
  }, [source, timeline, playheadMs, imported, sampleId])

  // Allow dragging units only for samples/imports (not live timeline)
  const [mutableSnapshot, setMutableSnapshot] = useState<GameSnapshot | null>(null)
  useEffect(() => {
    if (!snapshot) return
    if (source === 'timeline') {
      setMutableSnapshot(snapshot)
      return
    }
    setMutableSnapshot(structuredClone(snapshot))
  }, [snapshot, source, playheadMs])

  const active = mutableSnapshot
  const selectedRegistryEntry: MatchRegistryEntry | null = useMemo(() => {
    if (!timelineChoice.startsWith('match:')) return null
    const code = timelineChoice.slice('match:'.length)
    return registry?.matches.find((entry) => entry.matchCode === code) ?? null
  }, [registry, timelineChoice])
  const isResearchTimeline = timelineChoice.startsWith('research:')

  const selectedUnits = useMemo(
    () =>
      selectedIds
        .map((id) => active?.units.find((u) => u.id === id))
        .filter(Boolean) as GameUnit[],
    [selectedIds, active],
  )

  const placeholderUnits = active?.units.filter(
    (u) => u.positionSource === 'fountain_placeholder',
  ) ?? []
  const frameHasPlaceholderPositions =
    source === 'timeline' &&
    (placeholderUnits.length > 0 || timeline?.provenance?.positionCoverage === 'none')
  const selectedHasPlaceholderPositions = selectedUnits.some(
    (u) => u.positionSource === 'fountain_placeholder',
  )
  const selectedLacksCombatState = selectedUnits.some(
    (u) =>
      u.hpKnown === false ||
      u.combatStatsKnown === false ||
      u.abilityRanksKnown === false,
  )
  const timelineHpUnavailable =
    source === 'timeline' && timeline?.provenance?.hpCoverage === 'none'
  const combatStateBlocked =
    source === 'timeline' && (timelineHpUnavailable || selectedLacksCombatState)
  const positionBlocked =
    source === 'timeline' &&
    (timeline?.provenance?.positionCoverage === 'none' || selectedHasPlaceholderPositions)
  const calculatorBlockReason = calculatorTrustBlockReason({
    research: isResearchTimeline,
    positionBlocked,
    combatStateBlocked,
  })
  const calculatorBlocked = calculatorBlockReason !== null

  function toggleUnit(id: string) {
    setSelectedIds((prev) => {
      if (prev.includes(id)) return prev.filter((x) => x !== id)
      return [...prev, id]
    })
  }

  function moveUnit(id: string, x: number, y: number) {
    if (source === 'timeline') return
    setMutableSnapshot((prev) => {
      if (!prev) return prev
      return {
        ...prev,
        units: prev.units.map((u) =>
          u.id === id ? { ...u, position: { x, y } } : u,
        ),
      }
    })
  }

  function applyImport() {
    const result = parseSnapshotJson(importText)
    if (!result.ok) {
      setImportError(result.error)
      return
    }
    setImported(result.snapshot)
    setSource('import')
    setSelectedIds([])
    setImportError(null)
    setShowImport(false)
  }

  async function openTimelineFile(file: File) {
    setTimelineFileError(null)
    try {
      const data = parseTimelineFile(await file.text(), file.name)
      const duration = data.durationMs || data.frames[data.frames.length - 1]?.t || 0
      const firstFrame = data.frames[0]?.t ?? 0
      setTimeline(data)
      setTimelineChoice('local')
      setLocalTimelineName(file.name)
      setSource('timeline')
      setPlayheadMs(Math.min(duration, Math.max(firstFrame, 8 * 60 * 1000)))
      setSelectedIds([])
      setPlaying(false)
      setTimelineError(null)
    } catch (error) {
      setTimelineFileError(
        error instanceof Error ? error.message : 'Could not load that timeline file.',
      )
    }
  }

  const blueSelected = selectedUnits.filter((u) => u.team === 'blue')
  const redSelected = selectedUnits.filter((u) => u.team === 'red')
  const blueLiving = blueSelected.filter((u) => u.alive !== false)
  const redLiving = redSelected.filter((u) => u.alive !== false)
  const canSend = blueLiving.length >= 1 && redLiving.length >= 1
  const fightSizeLabel = `${blueLiving.length}v${redLiving.length}`
  const deadSelected =
    blueSelected.length - blueLiving.length + (redSelected.length - redLiving.length)
  const fightSizeTitle =
    deadSelected > 0
      ? `${fightSizeLabel} living (of ${blueSelected.length}v${redSelected.length} selected — dead excluded from the trade)`
      : `Send selected fighters as a ${fightSizeLabel} trade (click champs on the map/roster to pick sides)`

  function sendFight(engager: 'blue' | 'red' | 'neither' = 'neither') {
    if (!canSend || calculatorBlocked || !active) return

    const matchup: MatchupInput = {
      blue: blueLiving.map((u) => ({
        ...u.loadout,
        position: u.position,
        alive: true,
        hpPct: u.hpPct ?? u.loadout.hpPct,
      })),
      red: redLiving.map((u) => ({
        ...u.loadout,
        position: u.position,
        alive: true,
        hpPct: u.hpPct ?? u.loadout.hpPct,
      })),
      engager,
      mode: pickTradeModeForGameTime(active.gameTimeSec),
      xhMode: 'expected',
      objectives: active.score
        ? {
            blue: active.score.blue,
            red: active.score.red,
            gameTimeSec: active.gameTimeSec,
          }
        : undefined,
    }

    const blueNames = blueLiving
      .map((u) => CHAMPIONS[u.loadout.championId]?.name ?? u.loadout.championId)
      .join(' + ')
    const redNames = redLiving
      .map((u) => CHAMPIONS[u.loadout.championId]?.name ?? u.loadout.championId)
      .join(' + ')
    const label = `${blueSelected.length}v${redSelected.length} ${blueNames} vs ${redNames} · ${active.name}`
    onSendToCalculator(matchup, label)
  }

  if (loading) {
    return <p className="timeline-status">Loading timeline…</p>
  }

  if (!active) {
    return <p className="timeline-status">No snapshot available.</p>
  }

  const timeMs = source === 'timeline' ? playheadMs : (active.gameTimeSec * 1000)
  const durationMs = timeline?.durationMs || timeline?.frames[timeline.frames.length - 1]?.t || 0

  return (
    <section className="game-review">
      <div className="match-console-head">
        <Scoreboard score={active.score} gameTimeSec={active.gameTimeSec} />

        {source === 'timeline' && timeline && (
          <div className="timeline-scrubber">
            <button
              type="button"
              className="ghost"
              onClick={() => setPlaying((p) => !p)}
            >
              {playing ? 'Pause' : 'Play'}
            </button>
            <label className="scrub-label">
              <span>{formatGameTime(timeMs / 1000)}</span>
              <input
                type="range"
                min={0}
                max={durationMs}
                step={50}
                value={Math.min(playheadMs, durationMs)}
                onChange={(e) => {
                  setPlaying(false)
                  setPlayheadMs(Number(e.target.value))
                  setSelectedIds([])
                }}
              />
              <span>{formatGameTime(durationMs / 1000)}</span>
            </label>
            <label className="speed-label" title="Playback speed (game time)">
              <span>{playSpeed}×</span>
              <select
                value={playSpeed}
                onChange={(e) =>
                  setPlaySpeed(Number(e.target.value) as (typeof PLAY_SPEEDS)[number])
                }
              >
                {PLAY_SPEEDS.map((s) => (
                  <option key={s} value={s}>
                    {s}×
                  </option>
                ))}
              </select>
            </label>
            <div className="jump-buttons">
              {[5, 10, 15, 20].map((m) => (
                <button
                  key={m}
                  type="button"
                  className="ghost"
                  onClick={() => {
                    setPlaying(false)
                    setPlayheadMs(m * 60 * 1000)
                    setSelectedIds([])
                  }}
                >
                  {m}m
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      <div className="review-toolbar">
        <label>
          Source
          <select
            value={source}
            onChange={(e) => {
              setSource(e.target.value as SourceMode)
              setSelectedIds([])
              setPlaying(false)
            }}
          >
            <option value="timeline" disabled={!timeline}>
              Timeline{timelineError ? ' (failed)' : ''}
            </option>
            <option value="sample">Samples</option>
            <option value="import">Imported</option>
          </select>
        </label>

        <MatchPicker
          registry={registry}
          value={timelineChoice}
          localTimelineName={localTimelineName}
          onChange={(choice) => {
            setTimelineChoice(choice)
            setLocalTimelineName(null)
            setSelectedIds([])
            setPlaying(false)
            if (choice !== 'local') setSource('timeline')
          }}
        />

        <MatchCoverageBadges
          entry={selectedRegistryEntry}
          research={isResearchTimeline}
        />

        <input
          ref={timelineFileInputRef}
          type="file"
          accept=".json,.jsonl,application/json,application/x-ndjson,text/plain"
          hidden
          onChange={(e) => {
            const file = e.target.files?.[0]
            if (file) void openTimelineFile(file)
            e.target.value = ''
          }}
        />
        <button
          type="button"
          className="ghost"
          onClick={() => timelineFileInputRef.current?.click()}
        >
          Open timeline JSON / JSONL
        </button>

        {source === 'sample' && (
          <label>
            Snapshot
            <select
              value={sampleId}
              onChange={(e) => {
                setSampleId(e.target.value)
                setSelectedIds([])
              }}
            >
              {SAMPLE_SNAPSHOTS.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </label>
        )}

        <button type="button" className="ghost" onClick={() => setShowImport((v) => !v)}>
          {showImport ? 'Hide import' : 'Import'}
        </button>

        <span className="toolbar-sep" aria-hidden />

        <button
          type="button"
          className={showXh ? 'tonal' : 'ghost'}
          onClick={() => setShowXh((v) => !v)}
          title="Show skillshot hit-chance (xH) on the map"
        >
          xH
        </button>

        <label>
          FoW
          <select
            value={fogViewer}
            onChange={(e) =>
              setFogViewer(e.target.value as TeamSide | 'shared' | 'none')
            }
            title="Fog of war viewer"
          >
            <option value="blue">Blue</option>
            <option value="red">Red</option>
            <option value="shared">Shared</option>
            <option value="none">Off</option>
          </select>
        </label>

        <div className="selection-status">
          {selectedUnits.length === 0 && (
            <span>Select both sides to send a fight</span>
          )}
          {selectedUnits.length > 0 && (
            <span>
              <strong>
                {blueSelected.length}v{redSelected.length}
              </strong>{' '}
              {selectedUnits
                .map(
                  (u) =>
                    CHAMPIONS[u.loadout.championId]?.name ??
                    u.loadout.championId,
                )
                .join(', ')}
              {!canSend && <em> · need ≥1 per team</em>}
              {positionBlocked && <em> · live positions required</em>}
              {combatStateBlocked && !positionBlocked && (
                <em> · HP/combat state unavailable</em>
              )}
              {isResearchTimeline && <em> · research demo only</em>}
            </span>
          )}
        </div>

        {frameHasPlaceholderPositions && (
          <span className="position-coverage-warning">
            Fountain/scaffold positions shown — xH and calculator handoff are blocked until live positions are available.
          </span>
        )}
        {combatStateBlocked && !positionBlocked && (
          <span className="position-coverage-warning">
            Positions are real, but HP, ability ranks, and combat stats are unavailable from this replay feed — calculator handoff is blocked.
          </span>
        )}

        <div className="send-actions">
          <button
            type="button"
            className="ghost"
            onClick={() => {
              if (!active) return
              setSelectedIds(active.units.map((u) => u.id))
            }}
          >
            Both
          </button>
          <button
            type="button"
            className="ghost"
            onClick={() => {
              if (!active) return
              setSelectedIds(
                active.units.filter((u) => u.team === 'blue').map((u) => u.id),
              )
            }}
          >
            Blue
          </button>
          <button
            type="button"
            className="ghost"
            onClick={() => {
              if (!active) return
              setSelectedIds(
                active.units.filter((u) => u.team === 'red').map((u) => u.id),
              )
            }}
          >
            Red
          </button>
          <button
            type="button"
            disabled={!canSend || calculatorBlocked}
            title={calculatorBlockReason ?? fightSizeTitle}
            onClick={() => sendFight('neither')}
          >
            Send
            {canSend ? ` ${fightSizeLabel}` : ''}
          </button>
          <button
            type="button"
            className="ghost"
            disabled={!canSend || calculatorBlocked}
            onClick={() => sendFight('blue')}
          >
            Blue engages
          </button>
          <button
            type="button"
            className="ghost"
            disabled={!canSend || calculatorBlocked}
            onClick={() => sendFight('red')}
          >
            Red engages
          </button>
          {selectedIds.length > 0 && (
            <button
              type="button"
              className="ghost"
              onClick={() => setSelectedIds([])}
            >
              Clear
            </button>
          )}
        </div>
      </div>

      {showImport && (
        <div className="import-panel">
          <p>
            Paste snapshot JSON with <code>units[].loadout</code> and{' '}
            <code>position {'{x,y}'}</code> in 0–1 map space.
          </p>
          <textarea
            value={importText}
            onChange={(e) => setImportText(e.target.value)}
            rows={8}
            placeholder='{"name":"My fight","gameTimeSec":600,"units":[...]}'
          />
          {importError && <p className="import-error">{importError}</p>}
          <button type="button" onClick={applyImport}>
            Load snapshot
          </button>
        </div>
      )}

      {timelineError && source !== 'timeline' && (
        <p className="timeline-status warn">Timeline warning: {timelineError}</p>
      )}
      {registryStatus && (
        <p className="timeline-status warn">Published matches: {registryStatus}</p>
      )}
      {timelineFileError && (
        <p className="timeline-status warn">Timeline file: {timelineFileError}</p>
      )}

      <div className="review-layout">
        <MapView
          snapshot={active}
          selectedIds={selectedIds}
          onToggleUnit={toggleUnit}
          onMoveUnit={moveUnit}
          showXh={showXh && !frameHasPlaceholderPositions}
          fogViewer={fogViewer}
        />
        <div className="roster-pane">
          <div className="roster-pane-head">Roster</div>
          <UnitRoster
            snapshot={active}
            selectedIds={selectedIds}
            onToggleUnit={toggleUnit}
          />
        </div>
      </div>

      <ChampHistoryBoard snapshot={active} />
    </section>
  )
}
