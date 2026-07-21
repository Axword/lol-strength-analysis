import { useEffect, useMemo, useRef, useState } from 'react'
import { SAMPLE_SNAPSHOTS } from '../data/sampleGames'
import { CHAMPIONS } from '../data/champions'
import { parseSnapshotJson } from '../game/parseSnapshot'
import {
  loadFurVsG2Timeline,
  snapshotAtTime,
  type GameTimeline,
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

const PLAY_SPEEDS = [1, 2, 4, 8] as const

export function GameReview({ onSendToCalculator }: Props) {
  const [timeline, setTimeline] = useState<GameTimeline | null>(null)
  const [timelineError, setTimelineError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
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
    loadFurVsG2Timeline()
      .then((data) => {
        if (cancelled) return
        setTimeline(data)
        setPlayheadMs(8 * 60 * 1000)
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
  }, [])

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
    return SAMPLE_SNAPSHOTS[0]
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

  const selectedUnits = useMemo(
    () =>
      selectedIds
        .map((id) => active?.units.find((u) => u.id === id))
        .filter(Boolean) as GameUnit[],
    [selectedIds, active],
  )

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
    if (!canSend || !active) return

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
    return <p className="timeline-status">Loading FUR vs G2 timeline…</p>
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
              FUR vs G2{timelineError ? ' (failed)' : ''}
            </option>
            <option value="sample">Samples</option>
            <option value="import">Imported</option>
          </select>
        </label>

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
            </span>
          )}
        </div>

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
            disabled={!canSend}
            title={fightSizeTitle}
            onClick={() => sendFight('neither')}
          >
            Send
            {canSend ? ` ${fightSizeLabel}` : ''}
          </button>
          <button
            type="button"
            className="ghost"
            disabled={!canSend}
            onClick={() => sendFight('blue')}
          >
            Blue engages
          </button>
          <button
            type="button"
            className="ghost"
            disabled={!canSend}
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

      <div className="review-layout">
        <MapView
          snapshot={active}
          selectedIds={selectedIds}
          onToggleUnit={toggleUnit}
          onMoveUnit={moveUnit}
          showXh={showXh}
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
