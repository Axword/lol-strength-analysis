import type {
  MatchupResult,
  MatchupTimingResult,
  SideResult,
  TimedCombatEvent,
} from '../engine/types'
import { championIconUrl } from '../data/champions'
import './CombatResult.css'

function fmt(n: number): string {
  return Math.round(n).toLocaleString()
}

function pct(n: number): number {
  return Math.round(n * 100)
}

/** Fight clock as S:mmm (seconds:milliseconds), e.g. 1:150 = 1.150s. */
function formatFightClock(sec: number): string {
  const ms = Math.max(0, Math.round(sec * 1000))
  const s = Math.floor(ms / 1000)
  const rem = ms % 1000
  return `${s}:${String(rem).padStart(3, '0')}`
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
      {isWinner && <span className="win-tag">Stronger</span>}
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
            {fmt(result.hpRemaining)} / {fmt(result.stats.hpMax)} HP
          </span>
        </div>
      </div>

      <div className="face-stats">
        <div>
          <span>Dealt</span>
          <strong>{fmt(result.mitigatedTotal)}</strong>
        </div>
        <div>
          <span>Of enemy start</span>
          <strong>
            {pct(result.damagePctOfEnemy)}%
            {result.damagePctOfEnemy > 1e-9
              ? ` · ${fmt(result.mitigatedTotal / result.damagePctOfEnemy)} HP`
              : ''}
          </strong>
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
                {f.omittedSlots?.length && !f.dead ? (
                  <span
                    className="omit-chip"
                    title={
                      (f.omissionNotes ?? [])
                        .filter((n) => /omitted /i.test(n))
                        .join(' · ') ||
                      `omitted ${f.omittedSlots.join('/')}`
                    }
                  >
                    {` −${f.omittedSlots.join('/')}`}
                  </span>
                ) : null}
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

function SideDetails({
  result,
  timing,
}: {
  result: SideResult
  timing?: MatchupTimingResult
}) {
  const focus = result.targets?.[0]
  const startHp = focus?.hpStart ?? result.stats.hp
  const startMax = focus?.hpMax ?? result.stats.hpMax
  const leftHp = focus?.hpRemaining ?? result.hpRemaining
  const enemyStartApprox =
    result.damagePctOfEnemy > 1e-9
      ? result.mitigatedTotal / result.damagePctOfEnemy
      : null

  const timed =
    timing?.method === 'timed_manual_1v1'
      ? timing.events.filter((e) => e.side === result.side)
      : null

  return (
    <details className={`side-details side-${result.side}`}>
      <summary>
        {result.side === 'blue' ? 'Blue' : 'Red'} ability log &amp; stats
        {timing?.method === 'timed_manual_1v1' && timing.firstLethalSec != null
          ? ` · stop ${formatFightClock(timing.firstLethalSec)}`
          : ''}
      </summary>

      <dl className="stat-strip">
        <div>
          <dt>Start HP</dt>
          <dd>
            {fmt(startHp)} / {fmt(startMax)}
          </dd>
        </div>
        <div>
          <dt>Leftover HP</dt>
          <dd>
            {fmt(leftHp)} / {fmt(startMax)}
          </dd>
        </div>
        <div>
          <dt>Dealt (mitigated)</dt>
          <dd>
            {fmt(result.mitigatedTotal)}
            {enemyStartApprox != null ? (
              <span className="stat-hint">
                {' '}
                of ~{fmt(enemyStartApprox)} enemy start
              </span>
            ) : null}
          </dd>
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

      {timed != null ? (
        <ul className="packet-list timed-log">
          {timed.map((e, i) => (
              <TimedLogRow
                key={`${e.side}-${e.slot}-${e.castIndex}-${e.impactSec}-${i}`}
                event={e}
                packet={matchPacketForEvent(result, e)}
              />
            ))}
          {timed.length === 0 && <li className="empty">No timed actions.</li>}
        </ul>
      ) : (
        <ul className="packet-list">
          {result.packets.map((p, i) => (
            <li key={`${p.source}-${i}`}>
              <span className="t-clock" title="No per-cast clock on aggregate_window">
                —:—
              </span>
              <span className={`slot slot-${p.slot}`}>{p.slot}</span>
              <span className="src">
                {p.source}
                {p.skillshot ? ' · skillshot' : ''}
                {p.xH != null && p.skillshot
                  ? ` · xH ${Math.round(p.xH * 100)}%`
                  : ''}
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
      )}
    </details>
  )
}

function matchPacketForEvent(
  result: SideResult,
  event: TimedCombatEvent,
): SideResult['packets'][number] | undefined {
  const bySource = result.packets.filter(
    (p) => p.slot === event.slot && p.source === event.source,
  )
  if (bySource.length === 1) return bySource[0]
  if (bySource.length > 1) {
    return bySource[Math.min(event.castIndex - 1, bySource.length - 1)]
  }
  const bySlot = result.packets.filter((p) => p.slot === event.slot)
  if (!bySlot.length) return undefined
  return bySlot[Math.min(event.castIndex - 1, bySlot.length - 1)]
}

function TimedLogRow({
  event,
  packet,
}: {
  event: TimedCombatEvent
  packet?: SideResult['packets'][number]
}) {
  const raw =
    event.suppressed
      ? 0
      : event.raw != null
        ? event.raw
        : packet?.raw
  return (
    <li className={event.suppressed ? 'suppressed' : undefined}>
      <span
        className="t-clock"
        title={`cast ${formatFightClock(event.startSec)} → impact ${formatFightClock(event.impactSec)}`}
      >
        {formatFightClock(event.impactSec)}
      </span>
      <span className={`slot slot-${event.slot}`}>{event.slot}</span>
      <span className="src">
        {event.source}
        {event.suppressed ? ' · suppressed' : ''}
        {packet?.skillshot ? ' · skillshot' : ''}
        {packet?.xH != null && packet.skillshot
          ? ` · xH ${Math.round(packet.xH * 100)}%`
          : ''}
        {event.attackReset ? ' · reset' : ''}
      </span>
      <span className={`type type-${packet?.type ?? 'physical'}`}>
        {packet?.type ?? (event.suppressed ? '—' : 'hit')}
      </span>
      <span className="raw">
        {event.suppressed
          ? '—'
          : packet?.rawBeforeXh != null &&
              packet.skillshot &&
              packet.raw !== packet.rawBeforeXh
            ? `${fmt(packet.rawBeforeXh)}→${fmt(packet.raw)}`
            : raw != null
              ? fmt(raw)
              : '—'}
      </span>
    </li>
  )
}

export function CombatResult({ result }: { result: MatchupResult }) {
  const blueWins = result.winner === 'blue'
  const redWins = result.winner === 'red'
  const draw = result.winner === 'draw'
  const bothLethal = !!(result.blue.kills && result.red.kills)

  const pBlue = result.pBlue ?? 0.5
  const pRed = result.pRed ?? 1 - pBlue
  const blueScore = Math.round(pBlue * 100)
  const redScore = Math.round(pRed * 100)
  const trust = result.modelTrust
  const trustBadge = trust?.badge ?? 'Experimental · uncalibrated'

  const headline = draw
    ? 'Even model score'
    : blueWins
      ? 'Blue model edge'
      : 'Red model edge'

  const leftoverLine = bothLethal
    ? `Both lethal · overkill ${Math.round(result.blue.damagePctOfEnemy * 100)}% / ${Math.round(result.red.damagePctOfEnemy * 100)}% of enemy HP`
    : `leftover HP ${pct(result.blue.hpRemainingPct)}% (${fmt(result.blue.hpRemaining)}/${fmt(result.blue.stats.hpMax)}) / ${pct(result.red.hpRemainingPct)}% (${fmt(result.red.hpRemaining)}/${fmt(result.red.stats.hpMax)})`

  const subline = `heuristic model score B ${blueScore} / R ${redScore} · not a win probability · ${leftoverLine}`

  const band = result.strengthBand

  return (
    <section className="combat-result">
      <div className={`verdict-board winner-${result.winner}`}>
        <p className="eyebrow">
          Trade outcome · xH {result.xhMode.replace('_', ' ')}
        </p>
        <div className="verdict-head">
          <h2>{headline}</h2>
          <span
            className={`trust-badge ${trust?.class === 'manual_kit_1v1' ? 'manual' : 'experimental'}`}
            title={trust?.reasons.join(' · ')}
          >
            {trustBadge}
          </span>
        </div>
        <p className="verdict-sub">{subline}</p>

        {band && (
          <div className="strength-band" aria-label="Model strength band">
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

        {result.assumptions && result.assumptions.length > 0 && (
          <footer className="assumptions">
            <p className="assumptions-title">Assumptions</p>
            <ul>
              {result.assumptions.map((a) => (
                <li key={a}>{a}</li>
              ))}
            </ul>
          </footer>
        )}
      </div>

      <div className="details-row">
        <SideDetails result={result.blue} timing={result.timing} />
        <SideDetails result={result.red} timing={result.timing} />
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
  const score =
    pBlue != null
      ? `score ${Math.round(pBlue * 100)}/${Math.round((1 - pBlue) * 100)}`
      : null
  return (
    <div className={`band-cell winner-${winner} ${active ? 'active' : ''}`}>
      <span className="band-label">{label}</span>
      <span className="band-hint">{hint}</span>
      {score && <span className="band-score">{score}</span>}
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
