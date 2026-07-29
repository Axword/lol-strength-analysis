import { useState } from 'react'
import {
  CHAMPION_LIST,
  championIconUrl,
  getChampion,
  resolveChampionId,
} from '../data/champions'
import { ITEMS_BY_CATEGORY, itemIconUrl, ITEM_LIST, resolveItem } from '../data/items'
import { RUNE_LIST, resolveRuneId } from '../data/runes'
import { SUMMONER_LIST } from '../data/generated/allSummoners'
import { buildStats } from '../engine/stats'
import type { FighterLoadout } from '../engine/types'
import './FighterPanel.css'

const MAX_ITEMS = 6

const CATEGORY_LABELS: Record<string, string> = {
  starter: 'Starters',
  boots: 'Boots',
  damage: 'Damage',
  fighter: 'Fighter',
  mage: 'Mage',
  tank: 'Tank',
}

interface Props {
  side: 'blue' | 'red'
  loadout: FighterLoadout
  onChange: (next: FighterLoadout) => void
}

export function FighterPanel({ side, loadout, onChange }: Props) {
  const [itemFilter, setItemFilter] = useState('')
  const [runeFilter, setRuneFilter] = useState('')
  const resolvedId = resolveChampionId(loadout.championId)
  const champ =
    getChampion(loadout.championId) ??
    CHAMPION_LIST.find((c) => c.id === resolvedId) ??
    CHAMPION_LIST[0]
  const activeRune = resolveRuneId(loadout.runeId)

  const filteredItems = ITEM_LIST.filter((item) =>
    item.name.toLowerCase().includes(itemFilter.toLowerCase()),
  )

  const filteredRunes = RUNE_LIST.filter((rune) =>
    `${rune.name} ${rune.tree}`.toLowerCase().includes(runeFilter.toLowerCase()),
  )

  const resolvedStats = buildStats(loadout)
  const hpMax = Math.max(1, Math.round(resolvedStats.hpMax))
  const hpNow = Math.max(
    0,
    Math.round(
      loadout.liveStats?.hp != null && Number.isFinite(loadout.liveStats.hp)
        ? loadout.liveStats.hp
        : hpMax * (loadout.hpPct ?? 1),
    ),
  )

  function setChampion(championId: string) {
    onChange({ ...loadout, championId: resolveChampionId(championId) })
  }

  function toggleItem(itemId: string) {
    const has = loadout.itemIds.includes(itemId)
    if (has) {
      onChange({ ...loadout, itemIds: loadout.itemIds.filter((id) => id !== itemId) })
      return
    }
    if (loadout.itemIds.length >= MAX_ITEMS) return
    onChange({ ...loadout, itemIds: [...loadout.itemIds, itemId] })
  }

  function setSummoner(slot: 0 | 1, key: string) {
    const current = loadout.summonerSpells ?? ['SummonerFlash', 'SummonerDot']
    const next: [string, string] = [...current] as [string, string]
    next[slot] = key
    onChange({ ...loadout, summonerSpells: next })
  }

  if (!champ) {
    return (
      <section className={`fighter-panel side-${side}`}>
        <p className="champ-title">Unknown champion: {loadout.championId}</p>
      </section>
    )
  }

  return (
    <section className={`fighter-panel side-${side}`}>
      <header className="fighter-header">
        <img
          className="champ-portrait"
          src={championIconUrl(resolvedId)}
          alt={champ.name}
          width={64}
          height={64}
        />
        <div className="fighter-identity">
          <label className="field-label" htmlFor={`${side}-champ`}>
            {side === 'blue' ? 'Blue side' : 'Red side'}
          </label>
          <select
            id={`${side}-champ`}
            value={resolvedId}
            onChange={(e) => setChampion(e.target.value)}
          >
            {CHAMPION_LIST.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
          <p className="champ-title">{champ.title}</p>
        </div>
      </header>

      <div className="control-row">
        <label>
          Level
          <input
            type="range"
            min={1}
            max={18}
            value={loadout.level}
            onChange={(e) =>
              onChange({ ...loadout, level: Number(e.target.value) })
            }
          />
          <span className="level-value">{loadout.level}</span>
        </label>
        <label>
          HP%
          <input
            type="range"
            min={0}
            max={100}
            value={Math.round((loadout.hpPct ?? 1) * 100)}
            onChange={(e) => {
              const hpPct = Number(e.target.value) / 100
              onChange({
                ...loadout,
                hpPct,
                alive: hpPct > 0,
                liveStats: loadout.liveStats
                  ? {
                      ...loadout.liveStats,
                      hp: (loadout.liveStats.hpMax ?? loadout.liveStats.hp ?? 1) * hpPct,
                    }
                  : undefined,
              })
            }}
          />
          <span className="level-value">{Math.round((loadout.hpPct ?? 1) * 100)}</span>
          <span className="hp-abs" title="Current HP / max HP at fight start">
            {hpNow.toLocaleString()} / {hpMax.toLocaleString()} HP
          </span>
        </label>
      </div>

      <div className="target-stats">
        <div className="target-stats-head">
          <span className="field-label">Override HP / resists</span>
          <button
            type="button"
            className="target-preset"
            onClick={() =>
              onChange({
                ...loadout,
                hpPct: 1,
                alive: true,
                liveStats: {
                  ...loadout.liveStats,
                  hpMax: 3000,
                  hp: 3000,
                  armor: 150,
                  mr: 50,
                },
              })
            }
          >
            3000 / 150 / 50
          </button>
          {(loadout.liveStats?.hpMax != null ||
            loadout.liveStats?.armor != null ||
            loadout.liveStats?.mr != null) && (
            <button
              type="button"
              className="target-preset"
              onClick={() => {
                const { hpMax: _h, armor: _a, mr: _m, hp: _hp, ...rest } =
                  loadout.liveStats ?? {}
                onChange({
                  ...loadout,
                  liveStats: Object.keys(rest).length ? rest : undefined,
                })
              }}
            >
              Clear
            </button>
          )}
        </div>
        <div className="target-stats-grid">
          <label>
            Max HP
            <input
              type="number"
              min={100}
              max={12000}
              step={50}
              value={loadout.liveStats?.hpMax ?? ''}
              placeholder="auto"
              onChange={(e) => {
                const v = e.target.value
                if (v === '') {
                  const next = { ...loadout.liveStats }
                  delete next.hpMax
                  delete next.hp
                  onChange({
                    ...loadout,
                    liveStats: Object.keys(next).length ? next : undefined,
                  })
                  return
                }
                const hpMax = Number(v)
                if (!Number.isFinite(hpMax)) return
                const hpPct = loadout.hpPct ?? 1
                onChange({
                  ...loadout,
                  liveStats: {
                    ...loadout.liveStats,
                    hpMax,
                    hp: hpMax * hpPct,
                  },
                })
              }}
            />
          </label>
          <label>
            Armor
            <input
              type="number"
              min={0}
              max={500}
              step={5}
              value={loadout.liveStats?.armor ?? ''}
              placeholder="auto"
              onChange={(e) => {
                const v = e.target.value
                if (v === '') {
                  const next = { ...loadout.liveStats }
                  delete next.armor
                  onChange({
                    ...loadout,
                    liveStats: Object.keys(next).length ? next : undefined,
                  })
                  return
                }
                const armor = Number(v)
                if (!Number.isFinite(armor)) return
                onChange({
                  ...loadout,
                  liveStats: { ...loadout.liveStats, armor },
                })
              }}
            />
          </label>
          <label>
            MR
            <input
              type="number"
              min={0}
              max={500}
              step={5}
              value={loadout.liveStats?.mr ?? ''}
              placeholder="auto"
              onChange={(e) => {
                const v = e.target.value
                if (v === '') {
                  const next = { ...loadout.liveStats }
                  delete next.mr
                  onChange({
                    ...loadout,
                    liveStats: Object.keys(next).length ? next : undefined,
                  })
                  return
                }
                const mr = Number(v)
                if (!Number.isFinite(mr)) return
                onChange({
                  ...loadout,
                  liveStats: { ...loadout.liveStats, mr },
                })
              }}
            />
          </label>
        </div>
      </div>

      <div className="rank-row">
        <span className="field-label">Ability ranks</span>
        <div className="rank-sliders">
          {(['Q', 'W', 'E', 'R'] as const).map((slot) => (
            <label key={slot}>
              {slot}
              <input
                type="range"
                min={0}
                max={slot === 'R' ? 3 : 5}
                value={loadout.ranks?.[slot] ?? 0}
                onChange={(e) =>
                  onChange({
                    ...loadout,
                    ranks: {
                      Q: loadout.ranks?.Q ?? 0,
                      W: loadout.ranks?.W ?? 0,
                      E: loadout.ranks?.E ?? 0,
                      R: loadout.ranks?.R ?? 0,
                      [slot]: Number(e.target.value),
                    },
                  })
                }
              />
              <span>{loadout.ranks?.[slot] ?? 0}</span>
            </label>
          ))}
        </div>
      </div>

      {(loadout.alive === false || (loadout.hpPct ?? 1) <= 0) && (
        <p className="dead-banner">Dead — excluded from damage &amp; HP pool</p>
      )}

      <div className="rune-row">
        <span className="field-label">Keystone ({RUNE_LIST.length})</span>
        <input
          type="search"
          placeholder="Filter keystones…"
          value={runeFilter}
          onChange={(e) => setRuneFilter(e.target.value)}
        />
        <div className="rune-options">
          <button
            type="button"
            className={!activeRune ? 'active' : ''}
            onClick={() =>
              onChange({ ...loadout, runeId: null, spellbookState: undefined })
            }
          >
            None
          </button>
          {filteredRunes.map((rune) => (
            <button
              key={rune.id}
              type="button"
              className={activeRune?.id === rune.id ? 'active' : ''}
              title={rune.description}
              onClick={() =>
                onChange({
                  ...loadout,
                  runeId: rune.id,
                  spellbookState:
                    rune.spellbook
                      ? {
                          offered: [],
                          swapCooldownRemainingSec:
                            rune.spellbook.initialSwapCooldownSec,
                          swapsUsed: 0,
                        }
                      : undefined,
                })
              }
            >
              {rune.name}
            </button>
          ))}
        </div>
        {activeRune?.spellbook && (
          <div className="spellbook-panel">
            <strong>Unsealed Spellbook</strong>
            <p>
              Swap CD {activeRune.spellbook.initialSwapCooldownSec}s → min{' '}
              {activeRune.spellbook.minSwapCooldownSec}s; summoner cast −
              {activeRune.spellbook.swapCooldownReductionOnSummonerCastSec}s.
              Unique summoners only.
            </p>
            <ul>
              {activeRune.spellbook.notes.map((n) => (
                <li key={n}>{n}</li>
              ))}
            </ul>
            <div className="summoner-row">
              {([0, 1] as const).map((slot) => (
                <label key={slot}>
                  Summoner {slot + 1}
                  <select
                    value={
                      loadout.summonerSpells?.[slot] ??
                      (slot === 0 ? 'SummonerFlash' : 'SummonerDot')
                    }
                    onChange={(e) => setSummoner(slot, e.target.value)}
                  >
                    {SUMMONER_LIST.map((sp) => (
                      <option key={sp.id} value={sp.id}>
                        {sp.name}
                      </option>
                    ))}
                  </select>
                </label>
              ))}
            </div>
          </div>
        )}
      </div>

      <div className="items-equipped">
        <span className="field-label">
          Items ({loadout.itemIds.length}/{MAX_ITEMS}) · catalog {ITEM_LIST.length}
        </span>
        <div className="item-slots">
          {Array.from({ length: MAX_ITEMS }).map((_, i) => {
            const id = loadout.itemIds[i]
            const item = id ? resolveItem(id) : null
            return (
              <button
                key={i}
                type="button"
                className={`item-slot ${id ? 'filled' : ''}`}
                onClick={() => id && toggleItem(id)}
                title={item?.name ?? (id ? `Unknown item ${id}` : 'Empty')}
              >
                {id ? (
                  <img src={itemIconUrl(id)} alt="" width={36} height={36} />
                ) : (
                  <span>+</span>
                )}
              </button>
            )
          })}
        </div>
      </div>

      <div className="item-picker">
        <input
          type="search"
          placeholder="Search items…"
          value={itemFilter}
          onChange={(e) => setItemFilter(e.target.value)}
        />
        {itemFilter ? (
          <div className="item-grid">
            {filteredItems.map((item) => (
              <button
                key={item.id}
                type="button"
                className={loadout.itemIds.includes(item.id) ? 'selected' : ''}
                onClick={() => toggleItem(item.id)}
                title={`${item.name} — ${item.gold}g`}
              >
                <img src={itemIconUrl(item.id)} alt={item.name} width={32} height={32} />
                <span>{item.name}</span>
              </button>
            ))}
          </div>
        ) : (
          Object.entries(ITEMS_BY_CATEGORY).map(([cat, items]) => (
            <div key={cat} className="item-category">
              <h4>{CATEGORY_LABELS[cat] ?? cat}</h4>
              <div className="item-grid">
                {items.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    className={loadout.itemIds.includes(item.id) ? 'selected' : ''}
                    onClick={() => toggleItem(item.id)}
                    title={`${item.name} — ${item.gold}g`}
                  >
                    <img src={itemIconUrl(item.id)} alt={item.name} width={32} height={32} />
                    <span>{item.name}</span>
                  </button>
                ))}
              </div>
            </div>
          ))
        )}
      </div>
    </section>
  )
}
