import { useState } from 'react'
import { Calculator } from './components/Calculator'
import { Faq } from './components/Faq'
import { GameReview } from './components/GameReview'
import { emptyMatchup } from './engine/combat'
import type { MatchupInput } from './engine/types'
import './App.css'

type Tab = 'map' | 'calculator' | 'faq'

function App() {
  const [tab, setTab] = useState<Tab>('map')
  const [matchup, setMatchup] = useState<MatchupInput>(() => emptyMatchup())
  const [contextLabel, setContextLabel] = useState<string | null>(null)

  function handleSendFromMap(next: MatchupInput, label: string) {
    setMatchup(next)
    setContextLabel(label)
    setTab('calculator')
  }

  const subtitle =
    tab === 'map'
      ? 'Match state · map · fight select'
      : tab === 'calculator'
        ? 'Combat strength · xH bands'
        : 'Model rules · scoreboard vs trade'

  return (
    <div className="app">
      <header className="app-shell">
        <div>
          <p className="brand">LoL Strength Analysis</p>
          <p className="brand-sub">{subtitle}</p>
        </div>
        <nav className="app-tabs" aria-label="Primary">
          <button
            type="button"
            className={tab === 'map' ? 'active' : ''}
            onClick={() => setTab('map')}
          >
            Review
          </button>
          <button
            type="button"
            className={tab === 'calculator' ? 'active' : ''}
            onClick={() => setTab('calculator')}
          >
            Calculator
          </button>
          <button
            type="button"
            className={tab === 'faq' ? 'active' : ''}
            onClick={() => setTab('faq')}
          >
            FAQ
          </button>
        </nav>
      </header>

      {tab === 'map' ? (
        <GameReview onSendToCalculator={handleSendFromMap} />
      ) : tab === 'calculator' ? (
        <Calculator
          matchup={matchup}
          onChange={setMatchup}
          contextLabel={contextLabel}
        />
      ) : (
        <Faq />
      )}
    </div>
  )
}

export default App
