import { useMemo, useState } from 'react'
import { FighterPanel } from './FighterPanel'
import { CombatResult } from './CombatResult'
import {
  defaultLoadout,
  simulateMatchup,
  withBlueFighterItemBuild,
} from '../engine/combat'
import { resolveFightDuration } from '../engine/fightDuration'
import { CHAMPION_LIST } from '../data/champions'
import { resolveItem } from '../data/items'
import type { FighterLoadout, MatchupInput, MatchupResult } from '../engine/types'
import './Calculator.css'

interface Props {
  matchup: MatchupInput
  onChange: (next: MatchupInput) => void
  contextLabel?: string | null
}

type BuildSlot = 'A' | 'B'

function buildLabel(itemIds: string[]): string {
  const names = itemIds
    .map((id) => resolveItem(id)?.name)
    .filter(Boolean) as string[]
  if (!names.length) return 'no items'
  if (names.length <= 2) return names.join(' · ')
  return `${names[0]} · ${names[1]} · +${names.length - 2}`
}

function compareVerdict(a: MatchupResult, b: MatchupResult): string {
  const dmgA = a.blue.mitigatedTotal
  const dmgB = b.blue.mitigatedTotal
  if (dmgA <= 0 && dmgB <= 0) return 'Neither Blue fighter 1 item build deals meaningful damage.'
  const delta = Math.abs(dmgA - dmgB)
  const pct = Math.min(dmgA, dmgB) > 0
    ? Math.round((delta / Math.min(dmgA, dmgB)) * 100)
    : 100
  if (Math.abs(dmgA - dmgB) < 1) return 'Blue fighter 1 item builds deal the same damage in this window.'
  const winner = dmgA > dmgB ? 'A' : 'B'
  return `Blue fighter 1 · Build ${winner} deals ${Math.round(delta)} more (+${pct}%).`
}

function TeamColumn({
  side,
  fighters,
  onChangeFighter,
  onAdd,
  onRemove,
  buildSlot,
  onBuildSlot,
  compareOn,
}: {
  side: 'blue' | 'red'
  fighters: FighterLoadout[]
  onChangeFighter: (index: number, next: FighterLoadout) => void
  onAdd: () => void
  onRemove: (index: number) => void
  buildSlot?: BuildSlot
  onBuildSlot?: (slot: BuildSlot) => void
  compareOn?: boolean
}) {
  return (
    <div className={`team-column side-${side}`}>
      <div className="team-column-head">
        <h3>{side === 'blue' ? 'Blue' : 'Red'}</h3>
        <span>
          {fighters.length} champ{fighters.length === 1 ? '' : 's'}
        </span>
        {side === 'blue' && compareOn && onBuildSlot && buildSlot && (
          <div className="segmented build-slot" role="group" aria-label="Editing build">
            {(['A', 'B'] as const).map((slot) => (
              <button
                key={slot}
                type="button"
                className={buildSlot === slot ? 'active' : ''}
                onClick={() => onBuildSlot(slot)}
              >
                Build {slot}
              </button>
            ))}
          </div>
        )}
        <button type="button" className="add-fighter" onClick={onAdd}>
          + Add
        </button>
      </div>
      <div className="team-fighters">
        {fighters.map((loadout, index) => (
          <div key={`${side}-${index}-${loadout.championId}`} className="fighter-wrap">
            {fighters.length > 1 && (
              <button
                type="button"
                className="remove-fighter"
                onClick={() => onRemove(index)}
                aria-label="Remove champion"
              >
                ×
              </button>
            )}
            <FighterPanel
              side={side}
              loadout={loadout}
              onChange={(next) => onChangeFighter(index, next)}
            />
          </div>
        ))}
      </div>
    </div>
  )
}

export function Calculator({ matchup, onChange, contextLabel }: Props) {
  const [compareOn, setCompareOn] = useState(false)
  const [buildBItems, setBuildBItems] = useState<string[] | null>(null)
  const [editingBuild, setEditingBuild] = useState<BuildSlot>('A')

  const durationSec = resolveFightDuration(matchup)
  const aaUptime = matchup.aaUptime ?? 1
  const engageModeled = matchup.mode === 'short' && durationSec <= 4

  const result = useMemo(() => simulateMatchup(matchup), [matchup])

  const resultB = useMemo(() => {
    if (!compareOn || !buildBItems || !matchup.blue[0]) return null
    return simulateMatchup(withBlueFighterItemBuild(matchup, buildBItems))
  }, [compareOn, buildBItems, matchup])

  function updateSide(side: 'blue' | 'red', fighters: FighterLoadout[]) {
    onChange({ ...matchup, [side]: fighters })
  }

  function addFighter(side: 'blue' | 'red') {
    const fallback =
      CHAMPION_LIST.find((c) => c.id === 'Ambessa')?.id ??
      CHAMPION_LIST[0]?.id ??
      'Gragas'
    updateSide(side, [...matchup[side], defaultLoadout(fallback)])
  }

  function setFightLength(sec: number) {
    const mode =
      sec <= 4 ? 'short' : sec <= 10 ? 'allin' : ('extended' as const)
    onChange({ ...matchup, durationSec: sec, mode })
  }

  const lengthPreset =
    Math.abs(durationSec - 3.5) < 0.01
      ? 3.5
      : Math.abs(durationSec - 8) < 0.01
        ? 8
        : Math.abs(durationSec - 16) < 0.01
          ? 16
          : null

  function toggleCompare() {
    if (compareOn) {
      setCompareOn(false)
      setEditingBuild('A')
      return
    }
    setBuildBItems([...(matchup.blue[0]?.itemIds ?? [])])
    setEditingBuild('B')
    setCompareOn(true)
  }

  function onBlueChange(index: number, next: FighterLoadout) {
    if (compareOn && index === 0 && editingBuild === 'B' && buildBItems) {
      setBuildBItems(next.itemIds)
      // Build B is intentionally an item-only comparison for Blue fighter 1.
      // Champion, level, HP, runes, and all other fighters stay on Build A.
      return
    }
    const blue = matchup.blue.slice()
    blue[index] = next
    updateSide('blue', blue)
  }

  const bluePanels: FighterLoadout[] = matchup.blue.map((f, i) => {
    if (!compareOn || i !== 0 || editingBuild !== 'B' || !buildBItems) return f
    return { ...f, itemIds: buildBItems }
  })

  return (
    <div className="calculator">
      {contextLabel && (
        <p className="calc-context">
          From map: <strong>{contextLabel}</strong>
        </p>
      )}

      <section className="match-controls" aria-label="Trade settings">
        <div className="control-group">
          <span className="field-label">Fight length</span>
          <div className="length-row">
            <div className="segmented">
              {(
                [
                  [3.5, '3.5s'],
                  [8, '8s'],
                  [16, '16s'],
                ] as const
              ).map(([sec, label]) => (
                <button
                  key={sec}
                  type="button"
                  className={lengthPreset === sec ? 'active' : ''}
                  onClick={() => setFightLength(sec)}
                >
                  {label}
                </button>
              ))}
            </div>
            <label className="slider-field">
              <input
                type="range"
                min={1}
                max={40}
                step={0.5}
                value={durationSec}
                onChange={(e) => setFightLength(Number(e.target.value))}
                aria-label="Custom fight length in seconds"
              />
              <span className="level-value">{durationSec.toFixed(1)}s</span>
            </label>
          </div>
        </div>

        <label className="control-group slider-field aa-field">
          <span className="field-label">Auto uptime</span>
          <div className="length-row">
            <input
              type="range"
              min={0}
              max={100}
              step={5}
              value={Math.round(aaUptime * 100)}
              onChange={(e) =>
                onChange({
                  ...matchup,
                  aaUptime: Number(e.target.value) / 100,
                })
              }
            />
            <span className="level-value">{Math.round(aaUptime * 100)}%</span>
          </div>
        </label>

        <div className="control-group">
          <span className="field-label">Builds</span>
          <button
            type="button"
            className={`ghost-btn ${compareOn ? 'active' : ''}`}
            onClick={toggleCompare}
          >
            {compareOn ? 'Exit compare' : 'Compare builds'}
          </button>
        </div>

        <details className="advanced-controls">
          <summary>Engage &amp; skillshots</summary>
          <div className="advanced-body">
            <div className="control-group">
              <span className="field-label">Who engages</span>
              <p className="control-help">
                {engageModeled
                  ? 'Late reaction is modeled for this short window.'
                  : 'Disabled here: longer-fight engage timing is not modeled.'}
              </p>
              <div className="segmented">
                {(
                  [
                    ['blue', 'Blue'],
                    ['red', 'Red'],
                    ['neither', 'Neutral'],
                  ] as const
                ).map(([value, label]) => (
                  <button
                    key={value}
                    type="button"
                    className={matchup.engager === value ? 'active' : ''}
                    disabled={!engageModeled}
                    onClick={() => onChange({ ...matchup, engager: value })}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>

            <div className="control-group">
              <span className="field-label">Skillshot xH</span>
              <div className="segmented">
                {(
                  [
                    ['expected', 'Expected'],
                    ['hit_all', 'Hit all'],
                    ['miss_shots', 'Miss'],
                    ['off', 'Off'],
                  ] as const
                ).map(([value, label]) => (
                  <button
                    key={value}
                    type="button"
                    className={
                      (matchup.xhMode ?? 'expected') === value ? 'active' : ''
                    }
                    onClick={() => onChange({ ...matchup, xhMode: value })}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>
          </div>
        </details>

        <p className="matchup-size" aria-label="Matchup size">
          {matchup.blue.length}
          <span>v</span>
          {matchup.red.length}
        </p>
      </section>

      {compareOn && buildBItems && (
        <p className="compare-hint">
          Editing <strong>Blue fighter 1 · Build {editingBuild}</strong>
          {editingBuild === 'A'
            ? ` · ${buildLabel(matchup.blue[0]?.itemIds ?? [])}`
            : ` · ${buildLabel(buildBItems)}`}
          . Build B compares items only; level, champion, HP, runes, and the rest of the team stay unchanged.
        </p>
      )}

      <div className="fighters teams">
        <TeamColumn
          side="blue"
          fighters={bluePanels}
          onChangeFighter={onBlueChange}
          onAdd={() => addFighter('blue')}
          onRemove={(index) => {
            if (matchup.blue.length <= 1) return
            updateSide(
              'blue',
              matchup.blue.filter((_, i) => i !== index),
            )
          }}
          compareOn={compareOn}
          buildSlot={editingBuild}
          onBuildSlot={setEditingBuild}
        />
        <TeamColumn
          side="red"
          fighters={matchup.red}
          onChangeFighter={(index, next) => {
            const red = matchup.red.slice()
            red[index] = next
            updateSide('red', red)
          }}
          onAdd={() => addFighter('red')}
          onRemove={(index) => {
            if (matchup.red.length <= 1) return
            updateSide(
              'red',
              matchup.red.filter((_, i) => i !== index),
            )
          }}
        />
      </div>

      {resultB && (
        <section className="build-delta" aria-label="Build comparison">
          <p className="build-delta-verdict">{compareVerdict(result, resultB)}</p>
          <div className="build-delta-row">
            <div>
              <span className="build-delta-label">A</span>
              <span className="build-delta-dmg">
                {Math.round(result.blue.mitigatedTotal)}
              </span>
              <span className="build-delta-meta">
                {Math.round(result.red.hpRemainingPct * 100)}% enemy HP left · Blue fighter 1
              </span>
            </div>
            <div>
              <span className="build-delta-label">B</span>
              <span className="build-delta-dmg">
                {Math.round(resultB.blue.mitigatedTotal)}
              </span>
              <span className="build-delta-meta">
                {Math.round(resultB.red.hpRemainingPct * 100)}% enemy HP left · Blue fighter 1
              </span>
            </div>
          </div>
        </section>
      )}

      <CombatResult result={result} />
    </div>
  )
}
