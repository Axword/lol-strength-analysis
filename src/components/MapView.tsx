import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { PointerEvent as ReactPointerEvent, WheelEvent as ReactWheelEvent } from 'react'
import { championIconUrl } from '../data/champions'
import { itemIconUrl } from '../data/items'
import { CHAMPIONS } from '../data/champions'
import { campIconUrl, campMarkerSize, structureIconUrl, structureMarkerSize } from '../data/mapIcons'
import { SR_CAMPS, SR_STRUCTURES } from '../data/srLayout'
import { formatGameTime } from '../game/parseSnapshot'
import type {
  GameSnapshot,
  GameUnit,
  MapCampState,
  MapObjectsState,
  MapStructureState,
  TeamSide,
} from '../game/types'
import { buildSnapshotXh } from '../engine/xhOverlay'
import {
  buildFogGrid,
  buildSharedFogGrid,
  classifyVision,
  isSpottedByEnemy,
  loadTerrain,
  type TerrainMeta,
} from '../engine/vision'
import './MapView.css'

function teamFromId(team: 100 | 200): TeamSide {
  return team === 100 ? 'blue' : 'red'
}

/** Prefer timeline mapObjects; fall back to static layout with first-spawn clocks. */
function resolveMapObjects(snapshot: GameSnapshot): MapObjectsState {
  if (snapshot.mapObjects) return snapshot.mapObjects
  const tMs = snapshot.gameTimeSec * 1000
  return {
    structures: SR_STRUCTURES.map(
      (s): MapStructureState => ({
        id: s.id,
        kind: s.kind,
        team: teamFromId(s.team),
        lane: s.lane,
        tier: s.tier,
        x: s.x,
        y: s.y,
        alive: true,
      }),
    ),
    camps: SR_CAMPS.map((c): MapCampState => {
      const alive = tMs >= c.firstSpawnMs
      return {
        id: c.id,
        kind: c.kind,
        team: c.team == null ? null : teamFromId(c.team),
        label: c.label,
        x: c.x,
        y: c.y,
        alive,
        respawnsAtMs: alive ? undefined : c.firstSpawnMs,
      }
    }),
  }
}

interface Props {
  snapshot: GameSnapshot
  selectedIds: string[]
  onToggleUnit: (unitId: string) => void
  onMoveUnit: (unitId: string, x: number, y: number) => void
  showXh?: boolean
  /** Whose fog-of-war to render; 'shared' = god view (nobody vs one-sided); 'none' disables */
  fogViewer?: TeamSide | 'shared' | 'none'
}

const MAP_SIZE = 640
const MIN_ZOOM = 1
const MAX_ZOOM = 12

function toSvg(pos: { x: number; y: number }) {
  return {
    cx: pos.x * MAP_SIZE,
    cy: (1 - pos.y) * MAP_SIZE,
  }
}

function clamp(n: number, lo: number, hi: number) {
  return Math.min(hi, Math.max(lo, n))
}

/** Pan so the view stays over the map at the given zoom. */
function clampPan(panX: number, panY: number, zoom: number) {
  const view = MAP_SIZE / zoom
  const max = MAP_SIZE - view
  return {
    panX: clamp(panX, 0, Math.max(0, max)),
    panY: clamp(panY, 0, Math.max(0, max)),
  }
}

export function MapView({
  snapshot,
  selectedIds,
  onToggleUnit,
  onMoveUnit,
  showXh = false,
  fogViewer = 'blue',
}: Props) {
  const [zoom, setZoom] = useState(1)
  const [panX, setPanX] = useState(0)
  const [panY, setPanY] = useState(0)
  const [terrain, setTerrain] = useState<TerrainMeta | null>(null)
  const svgRef = useRef<SVGSVGElement | null>(null)
  const panning = useRef(false)

  useEffect(() => {
    loadTerrain()
      .then(setTerrain)
      .catch(() => setTerrain(null))
  }, [])

  const fogUrl = useMemo(() => {
    if (fogViewer === 'none' || !terrain) return null
    const grid =
      fogViewer === 'shared'
        ? buildSharedFogGrid(
            snapshot.units,
            snapshot.wards ?? [],
            64,
            terrain,
          )
        : buildFogGrid(
            fogViewer,
            snapshot.units,
            snapshot.wards ?? [],
            64,
            terrain,
          )
    const res = grid.resolution
    const canvas = document.createElement('canvas')
    canvas.width = res
    canvas.height = res
    const ctx = canvas.getContext('2d')!
    const img = ctx.createImageData(res, res)
    const oppIsRed = fogViewer === 'blue' || fogViewer === 'shared'
    for (let j = 0; j < res; j++) {
      for (let i = 0; i < res; i++) {
        // grid y=0 is bottom (game); canvas y=0 is top
        const idx = (res - 1 - j) * res + i
        const fog = grid.opacity[idx] ?? 0.7
        const kind = grid.kind[idx] ?? 2
        const p = (j * res + i) * 4
        if (kind === 0) {
          img.data[p] = 0
          img.data[p + 1] = 0
          img.data[p + 2] = 0
          img.data[p + 3] = Math.round(fog * 180)
        } else if (kind === 1) {
          // Opponent-only / one-sided vision — cooler or warmer tint
          if (fogViewer === 'shared') {
            // Contested: purple-ish mid tone avoided — use amber for "one side sees"
            img.data[p] = 40
            img.data[p + 1] = 32
            img.data[p + 2] = 18
          } else if (oppIsRed) {
            img.data[p] = 48
            img.data[p + 1] = 18
            img.data[p + 2] = 18
          } else {
            img.data[p] = 16
            img.data[p + 1] = 28
            img.data[p + 2] = 52
          }
          img.data[p + 3] = Math.round(fog * 200)
        } else {
          // Nobody — true fog
          img.data[p] = 4
          img.data[p + 1] = 6
          img.data[p + 2] = 10
          img.data[p + 3] = Math.round(fog * 235)
        }
      }
    }
    ctx.putImageData(img, 0, 0)
    return canvas.toDataURL()
  }, [fogViewer, snapshot.units, snapshot.wards, terrain])

  const mapObjects = useMemo(() => resolveMapObjects(snapshot), [snapshot])
  const gameTimeMs = snapshot.gameTimeSec * 1000

  const viewSize = MAP_SIZE / zoom
  const viewBox = `${panX} ${panY} ${viewSize} ${viewSize}`

  const zoomAt = useCallback(
    (nextZoom: number, focusX?: number, focusY?: number) => {
      const z = clamp(nextZoom, MIN_ZOOM, MAX_ZOOM)
      const fx = focusX ?? panX + viewSize / 2
      const fy = focusY ?? panY + viewSize / 2
      const nextView = MAP_SIZE / z
      const ratio = nextView / viewSize
      const next = clampPan(
        fx - (fx - panX) * ratio,
        fy - (fy - panY) * ratio,
        z,
      )
      setZoom(z)
      setPanX(next.panX)
      setPanY(next.panY)
    },
    [panX, panY, viewSize],
  )

  function clientToSvg(clientX: number, clientY: number) {
    const svg = svgRef.current
    if (!svg) return null
    const pt = svg.createSVGPoint()
    pt.x = clientX
    pt.y = clientY
    const ctm = svg.getScreenCTM()
    if (!ctm) return null
    const local = pt.matrixTransform(ctm.inverse())
    return { x: local.x, y: local.y }
  }

  function handleWheel(e: ReactWheelEvent<SVGSVGElement>) {
    e.preventDefault()
    const local = clientToSvg(e.clientX, e.clientY)
    const factor = e.deltaY < 0 ? 1.18 : 1 / 1.18
    zoomAt(zoom * factor, local?.x, local?.y)
  }

  function handleBackgroundPointerDown(e: ReactPointerEvent<SVGRectElement>) {
    if (e.button !== 0) return
    // Only pan when zoomed; at 1x a click does nothing special
    if (zoom <= 1.01) return
    e.preventDefault()
    panning.current = true
    const startClientX = e.clientX
    const startClientY = e.clientY
    const startPanX = panX
    const startPanY = panY
    const svg = svgRef.current
    if (!svg) return

    const onMove = (ev: PointerEvent) => {
      if (!panning.current) return
      const ctm = svg.getScreenCTM()
      if (!ctm) return
      // Screen delta → SVG viewBox delta (accounts for zoom/display size)
      const scale = viewSize / svg.clientWidth
      const next = clampPan(
        startPanX - (ev.clientX - startClientX) * scale,
        startPanY - (ev.clientY - startClientY) * scale,
        zoom,
      )
      setPanX(next.panX)
      setPanY(next.panY)
    }

    const onUp = () => {
      panning.current = false
      window.removeEventListener('pointermove', onMove)
      window.removeEventListener('pointerup', onUp)
    }

    window.addEventListener('pointermove', onMove)
    window.addEventListener('pointerup', onUp)
  }

  function handleUnitPointerDown(
    e: ReactPointerEvent<SVGGElement>,
    unit: GameUnit,
  ) {
    e.preventDefault()
    e.stopPropagation()
    const svg = e.currentTarget.ownerSVGElement
    if (!svg) return

    const moved = { current: false }
    const startX = e.clientX
    const startY = e.clientY

    const onMove = (ev: PointerEvent) => {
      if (Math.hypot(ev.clientX - startX, ev.clientY - startY) > 4) {
        moved.current = true
      }
      const pt = svg.createSVGPoint()
      pt.x = ev.clientX
      pt.y = ev.clientY
      const ctm = svg.getScreenCTM()
      if (!ctm) return
      const local = pt.matrixTransform(ctm.inverse())
      const x = Math.min(1, Math.max(0, local.x / MAP_SIZE))
      const y = Math.min(1, Math.max(0, 1 - local.y / MAP_SIZE))
      onMoveUnit(unit.id, x, y)
    }

    const onUp = (ev: PointerEvent) => {
      window.removeEventListener('pointermove', onMove)
      window.removeEventListener('pointerup', onUp)
      if (!moved.current) onToggleUnit(unit.id)
      ev.preventDefault()
    }

    window.addEventListener('pointermove', onMove)
    window.addEventListener('pointerup', onUp)
  }

  function zoomToSelection() {
    if (!selectedIds.length) {
      zoomAt(zoom < 3 ? 4 : zoom)
      return
    }
    const pts = snapshot.units
      .filter((u) => selectedIds.includes(u.id))
      .map((u) => toSvg(u.position))
    if (!pts.length) return
    const pad = 48
    const minX = Math.min(...pts.map((p) => p.cx)) - pad
    const maxX = Math.max(...pts.map((p) => p.cx)) + pad
    const minY = Math.min(...pts.map((p) => p.cy)) - pad
    const maxY = Math.max(...pts.map((p) => p.cy)) + pad
    // Don't zoom into a fountain pile — keep at least ~45% of the map in view
    const span = Math.max(maxX - minX, maxY - minY, MAP_SIZE * 0.45)
    const z = clamp(MAP_SIZE / span, MIN_ZOOM, MAX_ZOOM)
    const nextView = MAP_SIZE / z
    const cx = (minX + maxX) / 2
    const cy = (minY + maxY) / 2
    const next = clampPan(cx - nextView / 2, cy - nextView / 2, z)
    setZoom(z)
    setPanX(next.panX)
    setPanY(next.panY)
  }

  function resetView() {
    setZoom(1)
    setPanX(0)
    setPanY(0)
  }

  // Marker size scales slightly inverse to zoom so icons stay readable when zoomed out,
  // and don't explode the screen when deeply zoomed in.
  const markerScale = clamp(1.15 / Math.sqrt(zoom), 0.35, 1.1)
  // Map objects: gentler zoom shrink, never tiny at 1×.
  const objScale = clamp(1 / Math.pow(zoom, 0.2), 0.55, 1)

  const xhCasters = selectedIds.length ? selectedIds : snapshot.units.map((u) => u.id)
  const xhSummaries = showXh
    ? buildSnapshotXh(snapshot.units, xhCasters, {
        wards: snapshot.wards,
        terrain,
      })
    : []
  const unitPos = new Map(
    snapshot.units.map((u) => [u.id, toSvg(u.position)] as const),
  )

  // Range ring: longest skillshot per caster that has an in-range link
  const rangeRings = xhSummaries.flatMap((s) => {
    const inRange = s.links.filter((l) => l.inRange)
    if (!inRange.length) return []
    const maxRange = Math.max(...inRange.map((l) => l.abilityRange))
    const pos = unitPos.get(s.casterId)
    if (!pos) return []
    const r = (maxRange / 14870) * MAP_SIZE
    return [{ casterId: s.casterId, cx: pos.cx, cy: pos.cy, r }]
  })

  const xhLines = xhSummaries.flatMap((s) =>
    s.links
      .filter((l) => l.inRange)
      .map((l) => {
        const from = unitPos.get(l.casterId)
        const to = unitPos.get(l.targetId)
        if (!from || !to) return null
        return { ...l, from, to }
      })
      .filter(Boolean),
  ) as Array<{
    casterId: string
    targetId: string
    abilitySlot: string
    abilityName: string
    xH: number
    vision?: string
    from: { cx: number; cy: number }
    to: { cx: number; cy: number }
  }>

  return (
    <div className="map-view">
      <div className="map-meta">
        <div>
          <h2>{snapshot.name}</h2>
          <p>
            {formatGameTime(snapshot.gameTimeSec)} · patch {snapshot.patch}
            {snapshot.notes ? ` · ${snapshot.notes}` : ''}
          </p>
        </div>
        <div className="map-zoom-controls" role="group" aria-label="Map zoom">
          <button type="button" onClick={() => zoomAt(zoom / 1.35)} disabled={zoom <= MIN_ZOOM}>
            −
          </button>
          <span className="zoom-readout">{Math.round(zoom * 100)}%</span>
          <button type="button" onClick={() => zoomAt(zoom * 1.35)} disabled={zoom >= MAX_ZOOM}>
            +
          </button>
          <button type="button" className="ghost" onClick={zoomToSelection}>
            Focus
          </button>
          <button type="button" className="ghost" onClick={resetView} disabled={zoom === 1}>
            Reset
          </button>
        </div>
      </div>

      <div className={`map-stage ${zoom > 1.01 ? 'zoomed' : ''}`}>
        <svg
          ref={svgRef}
          className="rift-map"
          viewBox={viewBox}
          preserveAspectRatio="xMidYMid meet"
          role="img"
          aria-label="Summoner's Rift snapshot"
          onWheel={handleWheel}
        >
          <rect
            width={MAP_SIZE}
            height={MAP_SIZE}
            fill="#1a2218"
            rx="8"
            onPointerDown={handleBackgroundPointerDown}
            style={{ cursor: zoom > 1.01 ? 'grab' : 'default' }}
          />

          <image
            href="/map/summoners_rift.png"
            x={0}
            y={0}
            width={MAP_SIZE}
            height={MAP_SIZE}
            preserveAspectRatio="none"
            pointerEvents="none"
          />

          {fogUrl && (
            <image
              href={fogUrl}
              x={0}
              y={0}
              width={MAP_SIZE}
              height={MAP_SIZE}
              preserveAspectRatio="none"
              opacity={0.92}
              pointerEvents="none"
              className="fog-overlay"
            />
          )}

          {(snapshot.wards ?? []).map((w) => {
            const { cx, cy } = toSvg({ x: w.x, y: w.y })
            const r = (w.visionRadius || 0.055) * MAP_SIZE
            return (
              <g key={w.id} className={`ward-mark team-${w.team}`} pointerEvents="none">
                <circle
                  cx={cx}
                  cy={cy}
                  r={r}
                  fill={w.team === 'blue' ? 'rgba(80,140,220,0.08)' : 'rgba(200,80,80,0.08)'}
                  stroke={w.team === 'blue' ? '#6eb6ff' : '#ff7b7b'}
                  strokeWidth={0.8}
                  strokeDasharray="3 3"
                  opacity={0.55}
                />
                <circle cx={cx} cy={cy} r={3} fill={w.team === 'blue' ? '#6eb6ff' : '#ff7b7b'} />
              </g>
            )
          })}

          {mapObjects.structures.map((s) => {
            const { cx, cy } = toSvg({ x: s.x, y: s.y })
            const size = structureMarkerSize(s.kind) * objScale
            const title = [
              s.kind === 'turret' ? 'Turret' : s.kind === 'inhibitor' ? 'Inhibitor' : 'Nexus',
              s.team,
              s.lane,
              s.tier,
              s.alive ? 'up' : 'destroyed',
            ]
              .filter(Boolean)
              .join(' · ')
            const clipId = `struct-clip-${s.id}`
            const pad = 0.75
            return (
              <g
                key={s.id}
                className={`map-structure kind-${s.kind} team-${s.team} ${s.alive ? 'alive' : 'down'}`}
                transform={`translate(${cx}, ${cy})`}
                pointerEvents="none"
              >
                <rect
                  x={-(size / 2 + pad)}
                  y={-(size / 2 + pad)}
                  width={size + pad * 2}
                  height={size + pad * 2}
                  rx={2}
                  className="map-obj-frame"
                  fill={s.team === 'blue' ? 'rgba(20,36,56,0.75)' : 'rgba(56,20,20,0.75)'}
                  stroke={s.team === 'blue' ? '#6eb6ff' : '#ff7b7b'}
                  strokeWidth={s.alive ? 1.25 : 1}
                  strokeDasharray={s.alive ? undefined : '2 1.5'}
                />
                <clipPath id={clipId}>
                  <rect x={-size / 2} y={-size / 2} width={size} height={size} rx={1.5} />
                </clipPath>
                <image
                  href={structureIconUrl(s.kind, s.team)}
                  x={-size / 2}
                  y={-size / 2}
                  width={size}
                  height={size}
                  clipPath={`url(#${clipId})`}
                  className="map-icon"
                  preserveAspectRatio="xMidYMid slice"
                />
                <title>{title}</title>
              </g>
            )
          })}

          {mapObjects.camps.map((c) => {
            const { cx, cy } = toSvg({ x: c.x, y: c.y })
            const size = campMarkerSize(c.kind) * objScale
            const remainSec =
              !c.alive && c.respawnsAtMs != null
                ? Math.max(0, Math.ceil((c.respawnsAtMs - gameTimeMs) / 1000))
                : null
            const timerLabel = remainSec != null ? formatGameTime(remainSec) : null
            let tip = c.alive
              ? `${c.label} · UP`
              : `${c.label} · DOWN${timerLabel ? ` · up in ${timerLabel}` : ''}`
            if (c.clearedAtMs != null) {
              tip += ` · cleared ${formatGameTime(c.clearedAtMs / 1000)}`
            }
            if (c.respawnsAtMs != null) {
              tip += ` · available ${formatGameTime(c.respawnsAtMs / 1000)}`
            }
            const clipId = `camp-clip-${c.id}`
            const pad = 0.6
            const badgeW = Math.max(22, size * 0.95)
            const badgeH = 11 * Math.min(1.15, objScale + 0.15)
            return (
              <g
                key={c.id}
                className={`map-camp kind-${c.kind} ${c.alive ? 'alive' : 'down'}`}
                transform={`translate(${cx}, ${cy})`}
                pointerEvents="none"
              >
                <rect
                  x={-(size / 2 + pad)}
                  y={-(size / 2 + pad)}
                  width={size + pad * 2}
                  height={size + pad * 2}
                  rx={2}
                  className="map-obj-frame"
                  fill={c.alive ? 'rgba(8,10,8,0.7)' : 'rgba(8,8,8,0.82)'}
                  stroke={c.alive ? 'oklch(0.72 0.12 145 / 0.85)' : 'oklch(0.7 0.02 85 / 0.55)'}
                  strokeWidth={c.alive ? 1.35 : 1}
                  strokeDasharray={c.alive ? undefined : '2 1.5'}
                />
                <clipPath id={clipId}>
                  <rect x={-size / 2} y={-size / 2} width={size} height={size} rx={1.5} />
                </clipPath>
                <image
                  href={campIconUrl(c.kind)}
                  x={-size / 2}
                  y={-size / 2}
                  width={size}
                  height={size}
                  clipPath={`url(#${clipId})`}
                  className="map-icon"
                  preserveAspectRatio="xMidYMid slice"
                />
                {c.alive ? (
                  <g className="camp-status-badge up" transform={`translate(0, ${size / 2 + badgeH / 2 + 2})`}>
                    <rect
                      x={-badgeW / 2}
                      y={-badgeH / 2}
                      width={badgeW}
                      height={badgeH}
                      rx={2}
                      className="camp-badge-bg"
                    />
                    <text textAnchor="middle" y={3.2} className="camp-badge-text up">
                      UP
                    </text>
                  </g>
                ) : (
                  timerLabel && (
                    <g className="camp-status-badge down" transform={`translate(0, ${size / 2 + badgeH / 2 + 2})`}>
                      <rect
                        x={-badgeW / 2}
                        y={-badgeH / 2}
                        width={badgeW}
                        height={badgeH}
                        rx={2}
                        className="camp-badge-bg"
                      />
                      <text textAnchor="middle" y={3.2} className="camp-badge-text down">
                        {timerLabel}
                      </text>
                    </g>
                  )
                )}
                <title>{tip}</title>
              </g>
            )
          })}

          {/* Pit names sit just outside icon so the square art stays clean */}
          <text
            x={MAP_SIZE * (10021 / 14870)}
            y={MAP_SIZE * (1 - 4529 / 14870) + 22}
            textAnchor="middle"
            className="pit-label"
          >
            Drake
          </text>
          <text
            x={MAP_SIZE * (4803 / 14870)}
            y={MAP_SIZE * (1 - 10235 / 14870) + 22}
            textAnchor="middle"
            className="pit-label"
          >
            Baron
          </text>

          {showXh &&
            rangeRings.map((ring) => (
              <circle
                key={`range-${ring.casterId}`}
                cx={ring.cx}
                cy={ring.cy}
                r={ring.r}
                className="xh-range"
                pointerEvents="none"
              />
            ))}

          {showXh &&
            xhLines.map((line) => {
              const midX = (line.from.cx + line.to.cx) / 2
              const midY = (line.from.cy + line.to.cy) / 2
              const pct = Math.round(line.xH * 100)
              return (
                <g
                  key={`${line.casterId}-${line.targetId}-${line.abilitySlot}`}
                  pointerEvents="none"
                >
                  <line
                    x1={line.from.cx}
                    y1={line.from.cy}
                    x2={line.to.cx}
                    y2={line.to.cy}
                    className="xh-line"
                    strokeOpacity={0.35 + line.xH * 0.55}
                  />
                  <rect
                    x={midX - 18}
                    y={midY - 9}
                    width={36}
                    height={16}
                    rx={2}
                    className="xh-label-bg"
                  />
                  <text x={midX} y={midY + 3} textAnchor="middle" className="xh-label">
                    {line.abilitySlot} {pct}%
                  </text>
                  <title>
                    {line.abilityName}: xH {pct}%
                    {line.vision && line.vision !== 'unknown'
                      ? ` · ${line.vision}`
                      : ''}
                  </title>
                </g>
              )
            })}

          {snapshot.units.map((unit) => {
            const { cx, cy } = toSvg(unit.position)
            const selected = selectedIds.includes(unit.id)
            const champ = CHAMPIONS[unit.loadout.championId]
            const order = selectedIds.indexOf(unit.id)
            const r = (selected ? 18 : 15) * markerScale
            const img = 26 * markerScale

            let presence: 'visible' | 'opponent_only' | 'nobody' | 'off' = 'off'
            let spotted = false
            if (fogViewer === 'none') {
              presence = 'off'
            } else if (fogViewer === 'shared') {
              // God view: markers stay full opacity; fog overlay carries the signal
              presence = 'visible'
            } else if (unit.team === fogViewer) {
              presence = 'visible'
              spotted = isSpottedByEnemy(
                unit.position,
                fogViewer,
                snapshot.units,
                snapshot.wards ?? [],
                terrain,
              )
            } else {
              presence = classifyVision(
                unit.position,
                fogViewer,
                snapshot.units,
                snapshot.wards ?? [],
                terrain,
              )
            }

            const opacity =
              presence === 'nobody'
                ? 0.22
                : presence === 'opponent_only'
                  ? 0.45
                  : 1

            const fogLabel =
              presence === 'nobody'
                ? ' · true fog (nobody sees)'
                : presence === 'opponent_only'
                  ? ' · out of your vision (enemy sees)'
                  : spotted
                    ? ' · spotted by enemy'
                    : ''

            return (
              <g
                key={unit.id}
                className={`unit-marker team-${unit.team} ${selected ? 'selected' : ''} ${
                  presence === 'nobody'
                    ? 'true-fog'
                    : presence === 'opponent_only'
                      ? 'opponent-fog'
                      : ''
                } ${spotted ? 'spotted' : ''}`}
                transform={`translate(${cx}, ${cy})`}
                onPointerDown={(e) => handleUnitPointerDown(e, unit)}
                style={{ cursor: 'pointer', opacity }}
              >
                <circle
                  r={r}
                  className="unit-ring"
                  fill={unit.team === 'blue' ? 'oklch(0.42 0.1 245)' : 'oklch(0.42 0.12 28)'}
                />
                {spotted && (
                  <circle
                    r={r + 4}
                    className="spotted-ring"
                    fill="none"
                    stroke="#e8a84a"
                    strokeWidth={2}
                    strokeDasharray="3 2"
                  />
                )}
                <clipPath id={`clip-${unit.id}`}>
                  <circle r={img / 2} />
                </clipPath>
                <image
                  href={championIconUrl(unit.loadout.championId)}
                  x={-img / 2}
                  y={-img / 2}
                  width={img}
                  height={img}
                  clipPath={`url(#clip-${unit.id})`}
                />
                {selected && (
                  <text
                    y={-(r + 8)}
                    textAnchor="middle"
                    className="pick-order"
                    style={{ fontSize: `${Math.max(10, 14 * markerScale)}px` }}
                  >
                    {order + 1}
                  </text>
                )}
                <title>
                  {champ?.name ?? unit.loadout.championId} · {unit.role} · lv
                  {unit.loadout.level}
                  {fogLabel}
                  {'\n'}
                  pos {unit.position.x.toFixed(3)}, {unit.position.y.toFixed(3)}
                </title>
              </g>
            )
          })}
        </svg>
        {fogViewer !== 'none' && (
          <ul className="fow-legend">
            <li>
              <i className="swatch clear" /> You see
            </li>
            <li>
              <i className="swatch opponent" /> Enemy sees only
            </li>
            <li>
              <i className="swatch nobody" /> Nobody
            </li>
            <li>
              <i className="swatch spotted" /> Spotted
            </li>
          </ul>
        )}
      </div>
    </div>
  )
}

export function UnitRoster({
  snapshot,
  selectedIds,
  onToggleUnit,
}: {
  snapshot: GameSnapshot
  selectedIds: string[]
  onToggleUnit: (id: string) => void
}) {
  return (
    <ul className="unit-roster">
      {snapshot.units.map((unit) => {
        const champ = CHAMPIONS[unit.loadout.championId]
        const selected = selectedIds.includes(unit.id)
        return (
          <li key={unit.id}>
            <button
              type="button"
              className={`roster-card team-${unit.team} ${selected ? 'selected' : ''} ${unit.alive === false ? 'dead' : ''}`}
              onClick={() => onToggleUnit(unit.id)}
            >
              <img
                src={championIconUrl(unit.loadout.championId)}
                alt=""
                width={40}
                height={40}
              />
              <div className="roster-info">
                <strong>{champ?.name ?? unit.loadout.championId}</strong>
                <span>
                  {unit.team} {unit.role} · lv{unit.loadout.level}
                  {unit.hpPct != null ? ` · ${Math.round(unit.hpPct * 100)}% HP` : ''}
                  {unit.alive === false ? ' · DEAD' : ''}
                  {unit.loadout.ranks
                    ? ` · ${unit.loadout.ranks.Q}/${unit.loadout.ranks.W}/${unit.loadout.ranks.E}/${unit.loadout.ranks.R}`
                    : ''}
                </span>
                <div className="roster-items">
                  {unit.loadout.itemIds.map((id, i) => (
                    <img
                      key={`${unit.id}-${i}-${id}`}
                      src={itemIconUrl(id)}
                      alt=""
                      width={18}
                      height={18}
                    />
                  ))}
                  {unit.loadout.itemIds.length === 0 && <em>no items</em>}
                </div>
              </div>
              {selected && (
                <span className="pick-badge">{selectedIds.indexOf(unit.id) + 1}</span>
              )}
            </button>
          </li>
        )
      })}
    </ul>
  )
}
