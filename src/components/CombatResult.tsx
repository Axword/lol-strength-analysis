import type { MatchupResult, SideResult } from '../engine/types'
import { championIconUrl } from '../data/champions'
import './CombatResult.css'

function fmt(n: number): string {
  return Math.round(n).toLocaleString()
}

function pct(n: number): number {
  return Math.round(n * 100)
}

function TeamFace({
  result,
  isWinner,
  isLoser,
}: {
  result: SideResult
  isWinner: boolean
  isLoser: boolean
}) {
  const lostPct = Math.max(0, Math.min(100, 100 - pct(result.hpRemainingPct)))

  return (
    <div
      className={`team-face side-${result.side} ${isWinner ? 'is-winner' : ''} ${isLoser ? 'is-loser' : ''}`}
    >
      {isWinner && <span className="win-tag">Favorite</span>}
      {result.lockedOut && <span className="lock-badge">Late react</span>}

      <div className="team-icons">
        {result.fighters.map((f) => (
          <img
            key={`${f.championId}-${f.index}`}
            src={championIconUrl(f.championId)}
            alt={f.championName}
            width={48}
            height={48}
            title={f.championName}
          />
        ))}
      </div>

      <h3>{result.label}</h3>
      <p className="team-size">
        {result.fighters.length} fighter{result.fighters.length === 1 ? '' : 's'}
      </p>

      <div className="hp-meter" aria-label={`${result.side} team HP remaining`}>
        <div className="hp-meter-track">
          <div
            className="hp-meter-fill"
            style={{ width: `${pct(result.hpRemainingPct)}%` }}
          />
          <div className="hp-meter-lost" style={{ width: `${lostPct}%` }} />
        </div>
        <div className="hp-meter-labels">
          <strong>{pct(result.hpRemainingPct)}%</strong>
          <span>
            {fmt(result.hpRemaining)} / {fmt(result.stats.hp)} HP
          </span>
        </div>
      </div>

      <div className="face-stats">
        <div>
          <span>Dealt</span>
          <strong>{fmt(result.mitigatedTotal)}</strong>
        </div>
        <div>
          <span>Of enemy</span>
          <strong>{pct(result.damagePctOfEnemy)}%</strong>
        </div>
        {result.avgXh != null && (
          <div>
            <span>Avg xH</span>
            <strong>{pct(result.avgXh)}%</strong>
          </div>
        )}
      </div>
    </div>
  )
}

function DamageTug({ blue, red }: { blue: SideResult; red: SideResult }) {
  const total = blue.mitigatedTotal + red.mitigatedTotal || 1
  const blueShare = (blue.mitigatedTotal / total) * 100
  const redShare = (red.mitigatedTotal / total) * 100

  return (
    <div className="damage-tug" aria-label="Damage share">
      <div className="tug-labels">
        <span className="tug-blue">{fmt(blue.mitigatedTotal)} dmg</span>
        <span className="tug-center">Damage share</span>
        <span className="tug-red">{fmt(red.mitigatedTotal)} dmg</span>
      </div>
      <div className="tug-bar">
        <div className="tug-blue-fill" style={{ width: `${blueShare}%` }} />
        <div className="tug-red-fill" style={{ width: `${redShare}%` }} />
      </div>
      <div className="tug-pct">
        <span>{Math.round(blueShare)}%</span>
        <span>{Math.round(redShare)}%</span>
      </div>
    </div>
  )
}

function FighterBars({ result }: { result: SideResult }) {
  const max = Math.max(...result.fighters.map((f) => f.mitigatedTotal), 1)
  return (
    <ul className="fighter-bars">
          {result.fighters.map((f) => (
            <li key={`${f.championId}-${f.index}`}>
              <img src={championIconUrl(f.championId)} alt="" width={22} height={22} />
              <span className="name">
                {f.championName}
                {f.dead ? ' (dead)' : ''}
                {f.omittedSlots?.length && !f.dead
                  ? ` −${f.omittedSlots.join('/')}`
                  : ''}
              </span>
              <div className="bar-track">
                <div
                  className="bar-fill"
                  style={{ width: `${(f.mitigatedTotal / max) * 100}%` }}
                />
              </div>
              <strong>{fmt(f.mitigatedTotal)}</strong>
            </li>
          ))}
    </ul>
  )
}

function SideDetails({ result }: { result: SideResult }) {
  return (
    <details className={`side-details side-${result.side}`}>
      <summary>
        {result.side === 'blue' ? 'Blue' : 'Red'} ability log &amp; stats
      </summary>

      <dl className="stat-strip">
        <div>
          <dt>Team HP</dt>
          <dd>{fmt(result.stats.hp)}</dd>
        </div>
        <div>
          <dt>Avg AD / AP</dt>
          <dd>
            {fmt(result.stats.ad)} / {fmt(result.stats.ap)}
          </dd>
        </div>
        <div>
          <dt>Avg Armor / MR</dt>
          <dd>
            {fmt(result.stats.armor)} / {fmt(result.stats.mr)}
          </dd>
        </div>
        <div>
          <dt>Raw damage</dt>
          <dd>{fmt(result.rawTotal)}</dd>
        </div>
      </dl>

      <ul className="packet-list">
        {result.packets.map((p, i) => (
          <li key={`${p.source}-${i}`}>
            <span className={`slot slot-${p.slot}`}>{p.slot}</span>
            <span className="src">
              {p.source}
              {p.skillshot ? ' · skillshot' : ''}
              {p.xH != null && p.skillshot ? ` · xH ${Math.round(p.xH * 100)}%` : ''}
            </span>
            <span className={`type type-${p.type}`}>{p.type}</span>
            <span className="raw">
              {p.rawBeforeXh != null && p.skillshot && p.raw !== p.rawBeforeXh
                ? `${fmt(p.rawBeforeXh)}→${fmt(p.raw)}`
                : fmt(p.raw)}
            </span>
          </li>
        ))}
        {result.packets.length === 0 && (
          <li className="empty">No damage packets.</li>
        )}
      </ul>
    </details>
  )
}

export function CombatResult({ result }: { result: MatchupResult }) {
  const blueWins = result.winner === 'blue'
  const redWins = result.winner === 'red'
  const draw = result.winner === 'draw'

  const pBlue = result.pBlue ?? 0.5
  const pRed = result.pRed ?? 1 - pBlue
  const favPct = Math.round(Math.max(pBlue, pRed) * 100)

  const headline = draw
    ? 'Even fight odds'
    : blueWins
      ? `Blue favored · ${favPct}%`
      : `Red favored · ${favPct}%`

  const subline = draw
    ? `Fight odds near coin-flip (B ${Math.round(pBlue * 100)}% / R ${Math.round(pRed * 100)}%)`
    : `${Math.round(pBlue * 100)}% blue · ${Math.round(pRed * 100)}% red · leftover HP ${pct(result.blue.hpRemainingPct)}% / ${pct(result.red.hpRemainingPct)}%`

  const band = result.strengthBand

  return (
    <section className="combat-result">
      <div className={`verdict-board winner-${result.winner}`}>
        <p className="eyebrow">
          Trade outcome · xH {result.xhMode.replace('_', ' ')}
        </p>
        <h2>{headline}</h2>
        <p className="verdict-sub">{subline}</p>

        {band && (
          <div className="strength-band" aria-label="Strength percentage band">
            <p className="band-title">Strength band</p>
            <div className="band-row">
              <BandCell
                label="Miss shots"
                hint="skillshots whiff"
                bluePct={band.missShots.blueHpPct}
                redPct={band.missShots.redHpPct}
                winner={band.missShots.winner}
                pBlue={band.missShots.pBlue}
              />
              <BandCell
                label="Expected xH"
                hint="trade under packet xH"
                bluePct={band.expected.blueHpPct}
                redPct={band.expected.redHpPct}
                winner={band.expected.winner}
                pBlue={band.expected.pBlue}
                active={result.xhMode === 'expected'}
              />
              <BandCell
                label="Hit all"
                hint="every skillshot lands"
                bluePct={band.hitAll.blueHpPct}
                redPct={band.hitAll.redHpPct}
                winner={band.hitAll.winner}
                pBlue={band.hitAll.pBlue}
                active={result.xhMode === 'hit_all'}
              />
            </div>
          </div>
        )}

        {result.xhDodgeBand && (
          <div className="strength-band dodge-band" aria-label="Skillshot dodge envelope">
            <p className="band-title">xH dodge</p>
            <p className="band-caption">
              packet:{' '}
              {result.xhPacketPolicy === 'mix' && result.xhDodgeBand.mix != null
                ? 'mix'
                : 'typical'}
              {result.xhPacketPolicy === 'mix' && result.xhDodgeBand.mix != null
                ? ' (Flash CD unknown)'
                : ''}
            </p>
            <div className="band-row dodge-row">
              <DodgeCell
                label="worst"
                hint="Flash envelope"
                value={result.xhDodgeBand.worst}
              />
              <DodgeCell
                label="typical"
                hint="observed budget"
                value={result.xhDodgeBand.typical}
                active={
                  result.xhPacketPolicy !== 'mix' ||
                  result.xhDodgeBand.mix == null
                }
              />
              {result.xhDodgeBand.mix != null && (
                <DodgeCell
                  label="mix"
                  hint="NE Flash prior"
                  value={result.xhDodgeBand.mix}
                  active={result.xhPacketPolicy === 'mix'}
                />
              )}
              <DodgeCell
                label="best"
                hint="depleted"
                value={result.xhDodgeBand.best}
              />
            </div>
          </div>
        )}

        <div className="arena">
          <TeamFace result={result.blue} isWinner={blueWins} isLoser={redWins} />

          <div className="arena-mid">
            <div className={`vs-pill ${draw ? 'draw' : ''}`}>
              {result.blue.fighters.length}v{result.red.fighters.length}
            </div>
            <DamageTug blue={result.blue} red={result.red} />
          </div>

          <TeamFace result={result.red} isWinner={redWins} isLoser={blueWins} />
        </div>

        <div className="contrib-row">
          <div className="contrib-side">
            <h4>Blue damage</h4>
            <FighterBars result={result.blue} />
          </div>
          <div className="contrib-side">
            <h4>Red damage</h4>
            <FighterBars result={result.red} />
          </div>
        </div>

        {result.notes.length > 0 && (
          <ul className="notes fight-alerts">
            {result.notes.map((n) => (
              <li key={n}>{n}</li>
            ))}
          </ul>
        )}
      </div>

      <div className="details-row">
        <SideDetails result={result.blue} />
        <SideDetails result={result.red} />
      </div>
    </section>
  )
}

function BandCell({
  label,
  hint,
  bluePct,
  redPct,
  winner,
  pBlue,
  active,
}: {
  label: string
  hint: string
  bluePct: number
  redPct: number
  winner: 'blue' | 'red' | 'draw'
  pBlue?: number
  active?: boolean
}) {
  const odds =
    pBlue != null
      ? `${Math.round(pBlue * 100)}/${Math.round((1 - pBlue) * 100)}`
      : null
  return (
    <div className={`band-cell winner-${winner} ${active ? 'active' : ''}`}>
      <span className="band-label">{label}</span>
      <span className="band-hint">{hint}</span>
      {odds && <span className="band-odds">odds {odds}</span>}
      <div className="band-hp">
        <span className="b">HP {pct(bluePct)}%</span>
        <span className="outcome">
          {winner === 'draw' ? 'even' : winner === 'blue' ? 'blue' : 'red'}
        </span>
        <span className="r">HP {pct(redPct)}%</span>
      </div>
    </div>
  )
}

function DodgeCell({
  label,
  hint,
  value,
  active,
}: {
  label: string
  hint: string
  value: number
  active?: boolean
}) {
  return (
    <div className={`band-cell dodge-cell ${active ? 'active' : ''}`}>
      <span className="band-label">{label}</span>
      <span className="band-hint">{hint}</span>
      <strong className="dodge-pct">{pct(value)}%</strong>
    </div>
  )
}
