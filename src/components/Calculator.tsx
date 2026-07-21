import { FighterPanel } from './FighterPanel'
import { CombatResult } from './CombatResult'
import { defaultLoadout, simulateMatchup } from '../engine/combat'
import { CHAMPION_LIST } from '../data/champions'
import type { FighterLoadout, MatchupInput } from '../engine/types'
import './Calculator.css'

interface Props {
  matchup: MatchupInput
  onChange: (next: MatchupInput) => void
  contextLabel?: string | null
}

function TeamColumn({
  side,
  fighters,
  onChangeFighter,
  onAdd,
  onRemove,
}: {
  side: 'blue' | 'red'
  fighters: FighterLoadout[]
  onChangeFighter: (index: number, next: FighterLoadout) => void
  onAdd: () => void
  onRemove: (index: number) => void
}) {
  return (
    <div className={`team-column side-${side}`}>
      <div className="team-column-head">
        <h3>{side === 'blue' ? 'Blue side' : 'Red side'}</h3>
        <span>
          {fighters.length} champ{fighters.length === 1 ? '' : 's'}
        </span>
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
  const result = simulateMatchup(matchup)

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

  return (
    <div className="calculator">
      {contextLabel && (
        <p className="calc-context">
          From map: <strong>{contextLabel}</strong>
        </p>
      )}

      <section className="match-controls" aria-label="Trade settings">
        <div className="mode-toggle">
          <span className="field-label">Trade type</span>
          <div className="segmented">
            <button
              type="button"
              className={matchup.mode === 'short' ? 'active' : ''}
              onClick={() => onChange({ ...matchup, mode: 'short' })}
            >
              Short (~3.5s)
            </button>
            <button
              type="button"
              className={matchup.mode === 'allin' ? 'active' : ''}
              onClick={() => onChange({ ...matchup, mode: 'allin' })}
            >
              All-in (~8s)
            </button>
            <button
              type="button"
              className={matchup.mode === 'extended' ? 'active' : ''}
              onClick={() => onChange({ ...matchup, mode: 'extended' })}
            >
              Extended (~16s)
            </button>
          </div>
        </div>

        <div className="engage-toggle">
          <span className="field-label">Who engages</span>
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
                onClick={() => onChange({ ...matchup, engager: value })}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        <div className="xh-toggle">
          <span className="field-label">Skillshot xH</span>
          <div className="segmented">
            {(
              [
                ['expected', 'Expected'],
                ['hit_all', 'Hit all'],
                ['miss_shots', 'Miss shots'],
                ['off', 'Off'],
              ] as const
            ).map(([value, label]) => (
              <button
                key={value}
                type="button"
                className={(matchup.xhMode ?? 'expected') === value ? 'active' : ''}
                onClick={() => onChange({ ...matchup, xhMode: value })}
                title={
                  value === 'expected'
                    ? 'Scale skillshots by hit-chance priors'
                    : value === 'hit_all'
                      ? 'Assume every skillshot connects'
                      : value === 'miss_shots'
                        ? 'Strip all skillshot damage'
                        : 'Raw damage, no xH tagging'
                }
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        <p className="matchup-size">
          {matchup.blue.length}v{matchup.red.length}
        </p>
      </section>

      <div className="fighters teams">
        <TeamColumn
          side="blue"
          fighters={matchup.blue}
          onChangeFighter={(index, next) => {
            const blue = matchup.blue.slice()
            blue[index] = next
            updateSide('blue', blue)
          }}
          onAdd={() => addFighter('blue')}
          onRemove={(index) => {
            if (matchup.blue.length <= 1) return
            updateSide(
              'blue',
              matchup.blue.filter((_, i) => i !== index),
            )
          }}
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

      <CombatResult result={result} />
    </div>
  )
}
