import './Faq.css'

const SECTIONS: { id: string; title: string; body: string }[] = [
  {
    id: 'winner',
    title: 'How can the gold/scoreboard loser win a trade?',
    body: `They usually should not. The primary verdict is calibrated fight odds from gold, levels, towers, dragons, baron/elder, and kill lead, then updated by combat pressure (how much of the enemy HP pool the exchange removes).

Leftover HP% after a light poke is secondary. A Blue side that “wins” 81% vs 75% leftover HP while Red is +6k with baron is not called the favorite — Red is.

This match (FUR vs G2 JSONL) is a foolproof check: after ~16 minutes every kill cluster went Red, and Red won the map. In the gold/baron regime the model must favor the leader.`,
  },
  {
    id: 'strength-band',
    title: 'What do Miss / Expected / Hit all show?',
    body: `Each band re-runs skillshot assumptions and reports both fight odds and leftover HP%. Odds can stay Red-favored across all three when the scoreboard gap is large; Hit all may only change how bloody the leftover HP looks.`,
  },
  {
    id: 'duration',
    title: 'Short vs all-in vs extended fights?',
    body: `Short (~3.5s) is a poke/trade: one basic rotation, few autos. All-in (~8s) adds ultimates and more autos. Extended (~16s) models a real skirmish: multiple basic ability casts via haste, autos from attack speed × time, and in-fight sustain.

Map sends after 15:00 default to extended; 8–15 minutes default to all-in.

Sustain in-fight: omnivamp (and baron omnivamp) heals from damage dealt; a fraction of listed HP regen ticks during the window (full out-of-combat regen does not). Ocean dragon regen stays out-of-combat and does not apply mid-fight.`,
  },
  {
    id: 'hp-budget',
    title: 'What does “omitted Q/W/E/R” mean?',
    body: `Ability use is gated by current HP%. A champion at very low HP does not get a full all-in kit in the model. They may keep a single ability or autos only.

That is why a Galio at ~11% HP can show −W/E/R: his engage and follow-up are largely removed from that trade, even if baron and dragons are buffing his team.`,
  },
  {
    id: 'xh',
    title: 'What is xH / xHm?',
    body: `xH is the estimated probability a skillshot hits in this situation. Expected mode multiplies skillshot damage by that probability. It is a physics-style prior (not yet fit to cast→hit logs).

Controls: Calculator → Skillshot xH = Expected / Hit all / Miss shots / Off. Map toolbar “xH” only toggles the overlay.

Model (src/engine/xh.ts): lateral miss M ~ N(μ, σ²) with σ² = σ_aim² + σ_juke² + σ_belief²; xH = P(|M−μ| < R_hit) where R_hit = missileWidth/2 + champ radius. Aim noise follows a Schmidt/Fitts-style D/T term; juke uses strafe + dash/Flash budget only while ready and inside the reaction window vs missile TOF; blind FoW expands σ via last-known-position age (not “oracle position × 0.55”). Ambush lengthens defender reaction (surprise). Worst/typical/best bands vary dodge budget.

xHm is a multi-target hit-count distribution with shared aim-error dependence (not independent Bernoulli). Overlay aid, not a second damage engine.

Eval: npm run eval:xh (mathematical invariants). See xh-autoresearch/program.md.`,
  },
  {
    id: 'objectives',
    title: 'Do dragons, baron, and grubs affect the calculator?',
    body: `Yes when the snapshot carries scoreboard state into the fight — but each objective is modeled honestly, not as a generic “+X% damage” lump.

Infernal drakes add % AD and % AP per stack. Mountain adds % armor and MR. Cloud adds out-of-combat movespeed. Hextech adds ability haste and attack speed. Chemtech Blight adds tenacity and heal/shield power — not direct damage. Ocean regen is out-of-combat only and does not tick mid-fight.

Dragon souls are type-specific (Infernal, Mountain, Cloud, Hextech, Chemtech, Ocean). Chemtech Soul is conditional bonus damage plus damage reduction on proc; the calculator uses a simplified always-on version. Baron adds AD/AP and omnivamp; Elder adds burn and execute pressure.

Void grubs are structure-only: Touch-of-the-Void burn (melee/ranged ticks every 0.5s), and at 3 stacks Hunger summons a Voidmite every 15s. They do not amp champion PvP DPS and they do not shift fight odds — only map/siege value.`,
  },
  {
    id: 'history',
    title: 'What is the champion history board under the map?',
    body: `At the scrubbed time it shows cumulative Riot career stats per champ: damage dealt/taken, mitigated, CC, farm, vision, live AS%, and item ability haste.

Tabs: Against champions (PvP damage split + sustain) vs All (total damage, turrets/buildings/objectives, farm/vision).

Column order follows win relevance at the scrubbed minute (parlay-risk-sim): gold is always first among champ cells (gold_k ≈ 0.80@10 → 0.46@25; ~19→11pp map WR per +1k near even). Early also elevates grub Touch and farm; mid/late elevate damage and turrets/CC as fight and closeout proxies. Default sort tracks the top column until you click a header.

Drake use (per champ): quantified conversion of the team’s dragon stacks — infernal amp ≈ phys×AD%/(1+%) + magic×AP%/(1+%); mountain mitigated ≈ self-mit×resist%/(1+%); chemtech HSP share of ally heal/shield; chemtech soul amp/DR when present; cloud MS % (team buff; no pathing in feed); hextech AH and AS shown separately. Sort by summed amp + mitigated + HSP use to see who made best use.

AS and AH are separate columns (attack speed % of base vs ability haste).

Grub Touch: estimated Touch-of-the-Void burn (touch-v5). Structure map seeded at t=0 from SR layout; plate/destroy refine it. Clean AA = near structure + AD/AS-sized delta + no skill in window. Burn ticks that continue in the turret feed after walking away are not counted as far rejects. High = ≥3 clean AAs and far-share ≤30%. Optional: scripts/touch_vod_probe.py on a match.mp4 cuts ambiguous siege clips for labeling. Grubs never feed fight odds.

Sustain: ally heal + shield from the feed, live HP regen, life steal / spell vamp, and item omnivamp.`,
  },
  {
    id: 'fow',
    title: 'What do the fog colors mean?',
    body: `From a team FoW view: clear = you see it; tinted = you do not, but the opponent does; near-black = neither team has vision. A dashed ring on an ally means the enemy currently spots them.`,
  },
  {
    id: 'map-objects',
    title: 'What are the structure and camp markers on the map?',
    body: `Each jungle camp shows an on-map badge: UP (green) when available, or a second-precise countdown (M:SS) until it respawns. Cleared camps are greyscale with a dashed frame. Timers use Riot epic_monster_kill times plus current SR clocks (patch 26.1): wolves/blue/red/raptors first spawn 0:55; gromp/krugs 1:07; scuttle 2:55; dragon/grubs 5:00. Respawn: small 2:15, buffs 5:00, scuttle 2:30, dragon 5:00. Hover shows absolute clear and available game clocks.`,
  },
  {
    id: 'dead',
    title: 'Do dead champions count?',
    body: `No. Dead fighters deal and take no damage and are excluded from team HP and resist pools. The Send NvM label counts living selected champs only (dead picks are ignored). Selecting them still shows them in the roster.`,
  },
  {
    id: 'utility',
    title: 'Why do zero-damage abilities still matter?',
    body: `Slows, attack-speed withers, shred, damage reduction, and hard CC still apply even when an ability deals no base damage. They change auto counts, xH, and incoming damage in the same trade.`,
  },
]

export function Faq() {
  return (
    <article className="faq">
      <header className="faq-head">
        <h1>FAQ</h1>
        <p>How the map, scoreboard, and trade model fit together.</p>
      </header>
      <div className="faq-list">
        {SECTIONS.map((s) => (
          <section key={s.id} id={s.id} className="faq-item">
            <h2>{s.title}</h2>
            {s.body.split('\n\n').map((p) => (
              <p key={p.slice(0, 48)}>{p}</p>
            ))}
          </section>
        ))}
      </div>
    </article>
  )
}
