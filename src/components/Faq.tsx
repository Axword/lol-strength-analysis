import './Faq.css'

const SECTIONS: { id: string; title: string; body: string }[] = [
  {
    id: 'winner',
    title: 'How can the gold/scoreboard loser win a trade?',
    body: `They usually should not. The primary verdict is a heuristic fight-odds prior from gold, levels, towers, dragons, baron/elder, and kill lead, then updated by combat pressure (how much of the enemy HP pool the exchange removes). It is not a calibrated probability claim, especially for NvM.

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

Sustain in-fight: omnivamp from items/runes heals from damage dealt; a fraction of listed HP regen ticks during the window (full out-of-combat regen does not). Baron Hand does not grant omnivamp. Ocean dragon regen (2% missing HP / 5s) can tick in combat but is not timed in this model and adds no invented heal.`,
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
    body: `Yes when the snapshot carries scoreboard state into the fight — but only effects the engine can apply exactly are written into combat stats. Timed or conditional procs are disclosed and excluded, never replaced by fake flat or on-AA damage.

Applied permanent drakes: Infernal +3% AD/AP per stack; Mountain +5% armor/MR; Hextech +5 ability haste and +5% attack speed added through the champion attack-speed ratio (AS only where there is no authoritative live AS). Chemtech +6% tenacity and +6% heal/shield power are tracked for career attribution only — the combat engine has no HSP or tenacity consumer yet, so they are not combat-applied. Cloud permanent grants slow resist and out-of-combat movespeed — that OoC speed is not added to in-combat movespeed. Ocean restores 2% missing HP per 5s and can function in combat; it is disclosed only until regen is timed faithfully.

Manual theorycraft stacking (not live pins): champion per-level growth uses the Riot interpolation curve (not naive linear mid-levels); item and Hextech bonus AS% convert through AS ratio; Rabadon Magical Opus (+30% total AP from local item 3089) applies after Baron flat AP and Infernal % AP; Cloud Soul % MS is soft-capped once (415 / 490 bands).

When a fighter carries authoritative liveStats (or absolute dummy pins) for AD/AP/armor/MR/attack speed/movespeed, those fields are not re-buffed by objectives — Riot live values already include active buffs.

Souls this batch: only Cloud Soul's unconditional +15% movespeed passive is applied (skipped when live MS is pinned). Chemtech Soul's +13% damage / damage reduction while HP ≤ 50% has a thresholded helper but is not applied as always-on. Infernal, Hextech, Mountain, and Ocean Soul procs are disclosed only (zero fabricated packets). Elder burn (75–225 true over 2.25s) and the sub-20% execute are disclosed only — no fake per-AA true damage.

Baron Hand grants AD/AP fixed at the minute Baron was slain (Patch 9.2 anchors 12/20 at 20:00, 26/43 at 30:00, 48/80 at 40:00; continuous quadratic between anchors is inferred). No omnivamp. When baronEndsAtMs is known, slain time is endsAt/1000 − 180; otherwise current game time is used and labeled.

Void grubs are structure-only (Touch-of-the-Void V26.11: melee ticks 4/12/16 and ranged 2/6/8 per 0.5s at 1/2/3 stacks; Hunger at 3). They do not amp champion PvP DPS. The 8s / 900 HP / 120g gold-equivalent is a documented article scenario, not live turret forecasting.`,
  },
  {
    id: 'history',
    title: 'What is the champion history board under the map?',
    body: `At the scrubbed time it shows cumulative Riot career stats per champ: damage dealt/taken, mitigated, CC, farm, vision, live AS%, and item ability haste.

Tabs: Against champions (PvP damage split + sustain) vs All (total damage, turrets/buildings/objectives, farm/vision).

Column order follows win relevance at the scrubbed minute (parlay-risk-sim): gold is always first among champ cells (gold_k ≈ 0.80@10 → 0.46@25; ~19→11pp map WR per +1k near even). Early also elevates grub Touch and farm; mid/late elevate damage and turrets/CC as fight and closeout proxies. Default sort tracks the top column until you click a header.

Drake use (per champ): quantified conversion of applied permanent stacks — infernal amp ≈ phys×AD%/(1+%) + magic×AP%/(1+%); mountain mitigated ≈ self-mit×resist%/(1+%); chemtech HSP/tenacity tracked share of ally heal/shield (career attribution only, not a combat heal engine); Cloud Soul passive MS % when present (permanent Cloud OoC MS is not in-combat); hextech AH and AS shown separately. Chemtech Soul amp/DR is tagged as conditional and stays at zero quantified without threshold-time evidence. Sort by summed amp + mitigated + HSP use to see who made best use.

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
  {
    id: 'nvm',
    title: 'How does NvM focus fire work?',
    body: `NvM uses a deterministic first-living-target policy: every living attacker sends single-target packets to the first living enemy in input order. The exchange is simultaneous, HP is pooled only for the team meter, and there is no automatic retarget after that focus target dies. Armor/MR, max-HP scaling, Liandry's, sustain, and defensive utility resolve against concrete targets.

The calculator exposes this in the assumptions footer. Relative damage is acceptance-tested across all 25 cells from 1v1 through 5v5, but NvM fight odds and retarget timing remain uncalibrated.`,
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
