import type { ScoreboardState, TeamObjectives } from '../engine/objectives'
import { describeGrubs, GRUB } from '../engine/objectives'
import './Scoreboard.css'

interface Props {
  score: ScoreboardState | null | undefined
  gameTimeSec: number
}

function TeamBlock({
  side,
  team,
  goldDelta,
  isGoldLeader,
}: {
  side: 'blue' | 'red'
  team: TeamObjectives
  goldDelta: number
  isGoldLeader: boolean
}) {
  const deltaAbs = Math.abs(goldDelta)
  const dragons = team.dragons?.length
    ? team.dragons.map((d) => d[0]?.toUpperCase() ?? '?').join('')
    : '—'

  return (
    <div className={`sb-team side-${side}`}>
      <div className="sb-kills" title="Team kills">
        {team.kills}
      </div>
      <div className="sb-gold" title="Team gold">
        <span>{Math.round(team.gold / 100) / 10}k</span>
        {isGoldLeader && deltaAbs > 0 && (
          <em className="sb-gold-delta">+{Math.round(deltaAbs)}</em>
        )}
      </div>
      <div className="sb-towers" title="Towers taken">
        <span className="sb-ico">⌁</span>
        {team.towers}
      </div>
      <div className="sb-grubs" title={describeGrubs(team.voidGrubs)}>
        <span className="sb-ico">⦿</span>
        {team.voidGrubs}/{GRUB.maxStacks}
      </div>
      <div
        className="sb-dragons"
        title={
          team.hasSoul && team.soulType
            ? `Dragons: ${(team.dragons || []).join(', ') || 'none'} · Soul: ${team.soulType}`
            : `Dragons: ${(team.dragons || []).join(', ') || 'none'}`
        }
      >
        <span className="sb-ico">◆</span>
        {team.dragonCount}
        <span className="sb-drake-types">{dragons}</span>
        {team.hasSoul && (
          <span className="sb-soul">
            {team.soulType ? `SOUL·${team.soulType.slice(0, 4)}` : 'SOUL'}
          </span>
        )}
      </div>
      <div
        className={`sb-baron ${team.baronActive ? 'active' : ''}`}
        title={
          team.baronActive
            ? `Baron ACTIVE (${team.barons} taken)`
            : `Barons taken: ${team.barons}`
        }
      >
        <span className="sb-ico">♛</span>
        {team.barons}
        {team.baronActive && <span className="sb-live">LIVE</span>}
      </div>
      <div
        className={`sb-elder ${team.elderActive ? 'active' : ''}`}
        title={
          team.elderActive
            ? `Elder ACTIVE (${team.elders} taken)`
            : `Elders taken: ${team.elders}`
        }
      >
        <span className="sb-ico">✶</span>
        {team.elders}
        {team.elderActive && <span className="sb-live">LIVE</span>}
      </div>
      <div className="sb-quests" title="Role quests completed">
        <span className="sb-ico">✓</span>
        {team.roleQuests}
      </div>
    </div>
  )
}

export function Scoreboard({ score, gameTimeSec }: Props) {
  if (!score) {
    return (
      <div className="scoreboard empty">
        <span>No scoreboard data for this snapshot</span>
      </div>
    )
  }

  const mm = Math.floor(gameTimeSec / 60)
  const ss = Math.floor(gameTimeSec % 60)
    .toString()
    .padStart(2, '0')

  return (
    <div className="scoreboard" role="region" aria-label="Match scoreboard">
      <TeamBlock
        side="blue"
        team={score.blue}
        goldDelta={score.goldDelta}
        isGoldLeader={score.goldLeader === 'blue'}
      />
      <div className="sb-center">
        <strong>
          {mm}:{ss}
        </strong>
        <span className="sb-legend">
          K · Gold · Towers · Grubs · Dragons · Baron · Elder · Quests
        </span>
      </div>
      <TeamBlock
        side="red"
        team={score.red}
        goldDelta={score.goldDelta}
        isGoldLeader={score.goldLeader === 'red'}
      />
    </div>
  )
}
