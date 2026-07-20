League of Legends Combat Analysis System: Technical Documentation
Executive Summary
This document outlines a comprehensive, multi-phase analytical framework for evaluating combat outcomes in League of Legends through probabilistic modeling, damage calculation engines, and historical data integration. The system progresses from isolated champion-versus-champion analysis to full teamfight outcome prediction incorporating spatial, temporal, and stochastic variables.

Phase 1: Isolated Champion Combat Calculator (1v1 Analysis Engine)
1.1 Foundational Damage Calculation Framework
The initial implementation establishes a deterministic damage calculation system that computes raw damage output against defensive statistics for binary champion matchups.

1.1.1 Core Computational Variables
Offensive Parameters:

Base attack damage (AD_base)
Bonus attack damage (AD_bonus)
Ability power (AP)
Attack speed (AS)
Critical strike chance (Crit_chance)
Critical strike damage multiplier (Crit_damage)
Armor penetration (Pen_armor_flat, Pen_armor_percent)
Magic penetration (Pen_magic_flat, Pen_magic_percent)
Lethality (Lethality)
Magic penetration percentage (MPen_percent)
Defensive Parameters:

Base armor (Armor_base)
Bonus armor (Armor_bonus)
Base magic resistance (MR_base)
Bonus magic resistance (MR_bonus)
Base health (HP_base)
Bonus health (HP_bonus)
Health regeneration per second (HP_regen)
Ability-Specific Parameters:

Spell damage coefficients (Spell_dmg_base[n], Spell_dmg_AP_ratio[n], Spell_dmg_AD_ratio[n])
Spell cooldowns (CD[n])
Mana/energy costs (Resource_cost[n])
Damage type classification (Physical, Magical, True)
Champion Mechanical Parameters:

Attack range (Range_auto)
Ability ranges (Range_ability[n])
Base movement speed (MS_base)
Crowd control duration vectors (CC_duration[type])
1.1.2 Damage Mitigation Calculations
Physical damage mitigation:

text

Damage_mitigated_physical = Damage_raw_physical × (100 / (100 + Armor_effective))

Where:
Armor_effective = (Armor_base + Armor_bonus) × (1 - Pen_armor_percent) - Pen_armor_flat - (Lethality × (0.6 + 0.4 × Attacker_level / 18))
Magical damage mitigation:

text

Damage_mitigated_magical = Damage_raw_magical × (100 / (100 + MR_effective))

Where:
MR_effective = (MR_base + MR_bonus) × (1 - Pen_magic_percent) - Pen_magic_flat
True damage:

text

Damage_true = Damage_raw_true (no mitigation)
1.1.3 Passive, Item, and Rune Effect Integration
All passive damage amplification, on-hit effects, damage-over-time effects, conditional damage modifiers, and proc-based damage sources must be incorporated into the calculation engine with appropriate triggering conditions and cooldown tracking.

Required Integration Categories:

Champion passive abilities
Keystone rune effects (e.g., Electrocute, Conqueror, Press the Attack)
Secondary rune effects (e.g., Cheap Shot, Sudden Impact, Eyeball Collection)
Item passive effects (e.g., Lich Bane, Divine Sunderer, Black Cleaver)
Item active effects (e.g., Galeforce, Prowler's Claw, Everfrost)
Summoner spell damage and effects (Ignite, Smite)
1.1.4 Engagement Sequence Modeling
Combat sequences must account for initiator advantage and ability ordering constraints:

Engagement Parameters:

Initiating champion (Champion_initiator)
Engagement ability utilized (Ability_engage)
Distance at engagement initialization (Distance_initial)
Ability hit confirmation (Hit_confirmed[ability])
Trade Pattern Classification:

Short Trade Definition:
A combat sequence consisting of ability rotation completion (typically 3 abilities + auto-attack weaving) followed by disengagement before cooldown refresh or full resource expenditure.

All-In Definition:
A sustained combat sequence continuing until one combatant reaches zero health points, incorporating all available abilities, auto-attacks, item actives, and summoner spells without disengagement.

1.1.5 Shielding and Healing Calculations
Effective health pool modifications through shielding and healing mechanics:

text

HP_effective = HP_current + Shield_magnitude + (Heal_magnitude × (1 + Heal_power_percent)) - Grievous_wounds_reduction

Where:
Grievous_wounds_reduction = Heal_magnitude × Grievous_wounds_percent (if applicable)
Shield decay mechanics, duration tracking, and conditional shield applications must be temporally modeled within the combat simulation.

1.1.6 User Interface Requirements for Phase 1
Input Interface Specifications:

Dual champion selection module
Item builder interface (6 item slots + boots per champion)
Rune configurator (Keystone + 3 secondary runes per champion)
Level selector (1-18 for both champions)
Summoner spell selector (2 per champion)
Skill point distribution interface (ability level allocation)
Output Interface Specifications:

Total damage output per champion (Physical/Magical/True breakdown)
Time-to-kill calculations for both combatants
Damage differential visualization
Effective health pool comparisons
DPS (damage per second) metrics
Burst damage potential (first 3 seconds of combat)
Sustained damage potential (damage over 10+ second engagement)
Phase 2: Expected Hit Probability Integration (xH Statistical Framework)
2.1 Historical Data Collection Methodology
The xH (expected hit) statistic represents the empirical probability of skillshot ability successful connection derived from historical match data under controlled categorical variables.

2.1.1 Categorical Variable Classification
Target Champion Mobility Classification:

Category 0: Immobile (no dash, no blink, boots incomplete, Flash unavailable)
Category 1: Single mobility ability available (one dash/blink, OR Flash available)
Category 2: Dual mobility abilities available (dash + Flash, OR multiple dashes)
Category 3: Triple+ mobility abilities available (multiple dashes + Flash + bonus mobility)
Spatial Environmental Variables:

Terrain proximity (distance to nearest wall in champion-radii)
Brush state (casting champion in brush: Boolean; target champion in brush: Boolean)
Elevation differential (higher ground: +1; equal ground: 0; lower ground: -1)
River positioning (in river: Boolean)
Lane positioning (top/mid/bot/jungle classification)
Tactical Context Variables:

Target champion current action state (walking/standing/casting/auto-attacking)
Target champion facing vector relative to skillshot origin
Minion wave density in skillshot trajectory path
Allied champion proximity (number of allies within 1000 units)
Enemy champion proximity (number of enemies within 1000 units)
2.1.2 Skillshot Ability Classification
Skillshots must be taxonomically classified by geometric and temporal properties:

Geometric Classifications:

Linear skillshot (constant width, defined length)
Cone skillshot (expanding width, defined length)
Circular skillshot (radius from center point)
Arcing skillshot (parabolic trajectory)
Temporal Classifications:

Instant cast (no travel time, immediate effect)
Projectile (defined travel velocity)
Delayed cast (windup time before effect)
Channeled (sustained targeting requirement)
Width/Radius Quantification:

Narrow (< 80 units)
Standard (80-120 units)
Wide (> 120 units)
Speed Quantification:

Slow (< 1000 units/second)
Medium (1000-2000 units/second)
Fast (> 2000 units/second)
2.1.3 xH Calculation Formula
For ability i cast under environmental condition set E at target with mobility classification M:

text

xH(i, E, M) = (Hits_successful(i, E, M)) / (Casts_total(i, E, M))

Where historical data aggregates all instances matching:
- Ability identifier (i)
- Environmental condition set (E)
- Mobility classification (M)
- Minimum sample size threshold (n ≥ 100 recommended)
2.1.4 Multi-Target Hit Probability (xHm)
The xHm statistic represents the probability distribution of hitting multiple targets with area-of-effect abilities:

text

xHm(i, E, n_enemies) = P(hits = k | ability = i, environment = E, targets_in_range = n_enemies)

Where k ∈ {0, 1, 2, ..., n_enemies}
Example Distribution:
For ability i cast with 3 enemies in range under environment E:

P(hits = 0) = 0.50
P(hits = 1) = 0.30
P(hits = 2) = 0.15
P(hits = 3) = 0.04
P(hits = 4+) = 0.01
Expected value calculation:

text

E[hits] = Σ(k × P(hits = k)) = 0(0.50) + 1(0.30) + 2(0.15) + 3(0.04) + 4(0.01) = 0.76
Phase 3: Combat Outcome Probability Metric (Strength Percentage)
3.1 Win Probability Calculation Framework
The Strength Percentage metric quantifies the probability of combat victory under varying execution quality scenarios.

3.1.1 Scenario Classification
Scenario 1: Perfect Execution (Both Sides)

text

Win_probability_perfect = f(Damage_total_A, Damage_total_B, HP_effective_A, HP_effective_B)

Where all abilities hit (xH = 1.0 for all skillshots) and damage rotation optimization is maximal
Scenario 2: Asymmetric Execution Quality

text

Win_probability_asymmetric_A = f(Damage_total_A × Execution_quality_A, Damage_total_B × Execution_quality_B, HP_effective_A, HP_effective_B)

Where:
Execution_quality ∈ [0, 1] representing the proportion of theoretical maximum damage achieved
Scenario 3: Probabilistic Execution (xH-Weighted)

text

Win_probability_expected = ∫∫ P(win | hits_A, hits_B) × P(hits_A | xH_A) × P(hits_B | xH_B) dhits_A dhits_B

Where hit patterns are sampled from xH probability distributions for all skillshots
3.1.2 Time-to-Kill Comparative Analysis
For All-In scenario classification:

text

TTK_A = HP_effective_B / (DPS_A × (1 - Miss_rate_A))
TTK_B = HP_effective_A / (DPS_B × (1 - Miss_rate_B))

Win_probability_all_in = sigmoid(TTK_B - TTK_A)

Where sigmoid function maps time differential to probability space [0, 1]
For Short Trade scenario classification:

text

Damage_trade_net_A = Damage_burst_A × Hit_rate_A - Damage_burst_B × Hit_rate_B
Trade_efficiency_A = Damage_trade_net_A / HP_effective_A

Win_probability_short_trade = sigmoid(Trade_efficiency_A)
3.1.3 Execution Quality Modeling
Skill-based execution quality can be modeled as:

text

Execution_quality_player = α × Accuracy_skillshot + β × Combo_optimization + γ × Cooldown_efficiency + δ × Positioning_quality

Where:
- Accuracy_skillshot: proportion of skillshots successfully landed
- Combo_optimization: proportion of theoretical maximum damage achieved through ability weaving
- Cooldown_efficiency: proportion of abilities used optimally relative to cooldown windows
- Positioning_quality: proportion of time spent in optimal combat range
- α + β + γ + δ = 1 (weighting coefficients)
Phase 4: Game State Integration and Replay Analysis
4.1 Map-Based Visualization System
4.1.1 Data Import Requirements
The system must ingest real-time or replay game state data including:

Champion State Vectors (per champion, per timestamp):

Position coordinates (x, y)
Health (current/maximum)
Mana/Energy/Resource (current/maximum)
Experience and level
Gold total
Item inventory state (6 items + trinket)
Ability cooldown states (Q, W, E, R + Summoner Spells)
Buff/debuff states with remaining duration
Current action state (moving/attacking/casting/recalling/dead)
Environmental State Vectors (per timestamp):

Minion wave positions and health states
Neutral monster spawn states
Vision ward positions
Turret health states
Inhibitor states
Dragon/Baron states and timers
4.1.2 Calculator Integration Pipeline
For each timestamp t in replay data:

Extract champion state vectors for all participants
For each possible binary combat pairing (champion i vs champion j):
Load item configurations into damage calculator
Load rune configurations into damage calculator
Load current ability levels and cooldown states
Execute combat simulation for both All-In and Short Trade scenarios
Generate win probability metrics incorporating xH statistics
Store results in temporal database indexed by timestamp and champion pair
4.1.3 Visualization Interface Specifications
Map Overlay Components:

Champion position markers with health/resource bars
Combat outcome probability heatmaps (gradient overlay indicating favorable/unfavorable combat zones)
Ability range indicators
Vision range indicators
Skillshot trajectory predictions with xH probability annotations
Champion Detail Panels:

Current item build with gold efficiency metrics
Ability cooldown timers
Combat power score relative to each enemy champion
Win probability matrix (5x5 grid for all possible 1v1 pairings)
Phase 5: Expected Hit Probability Implementation in Live Analysis
5.1 Real-Time xH Calculation
During replay analysis, for each skillshot cast:

Extract environmental context variables at cast timestamp
Classify target champion mobility state
Query historical database for xH(ability, environment, mobility)
Display xH probability as overlay on skillshot trajectory visualization
Post-cast, record actual hit/miss outcome
Update local database to refine future xH predictions
5.2 xHm Visualization for Area Abilities
For area-of-effect abilities:

Identify all enemy champions within ability range at cast time
Query historical database for xHm probability distribution
Display expected value E[hits] alongside individual hit probabilities
Visualize probability density function as graduated color intensity on affected game area
Post-resolution, record actual number of targets hit
Update xHm distribution database
Phase 6: Teamfight Outcome Prediction System
6.1 Teamfight Classification and Segmentation
A teamfight instance is defined as:

text

Teamfight = {t_start, t_end, Participants_A, Participants_B, Position_centroid, Outcome}

Where:
- t_start: timestamp of first damage exchange involving 3+ champions per team
- t_end: timestamp of combat cessation (5+ seconds without damage exchange)
- Participants_A: set of champions from team A involved
- Participants_B: set of champions from team B involved
- Position_centroid: spatial center of combat
- Outcome: {Victory_A, Victory_B, Disengage}
6.2 Historical Teamfight Similarity Metrics
For current teamfight state S_current, identify similar historical teamfights using distance metric:

text

Distance(S_current, S_historical) = w1 × d_composition + w2 × d_gold + w3 × d_position + w4 × d_objective + w5 × d_cooldowns

Where:
- d_composition: champion composition similarity (role matching, champion archetype matching)
- d_gold: total gold differential similarity
- d_position: spatial configuration similarity (relative champion positions)
- d_objective: objective context similarity (dragon/baron presence, tower proximity)
- d_cooldowns: ultimate ability availability similarity
- w1...w5: weighting coefficients (Σw_i = 1)
6.3 Scenario-Based Win Probability Calculation
6.3.1 Monte Carlo Combat Simulation
For each teamfight state:

Run N Monte Carlo simulations (N ≥ 10,000) where:

Each skillshot hits/misses according to xH probability
Each AoE ability hits k targets according to xHm distribution
Damage calculations proceed according to Phase 1 framework
Target selection follows threat-priority heuristics
Ability usage follows cooldown-optimal rotation patterns
Record outcome distribution:

text

P(Victory_A) = (Simulations_won_by_A) / N
P(Victory_B) = (Simulations_won_by_B) / N
6.3.2 Scenario Range Quantification
Worst-Case Scenario (Team A Perspective):

text

Win_probability_worst = f(
  Execution_quality_A = minimum,
  Execution_quality_B = maximum,
  xH_A = minimum_realistic,
  xH_B = maximum_realistic,
  xHm_A = minimum_AoE_targets,
  xHm_B = maximum_AoE_targets
)
Expected-Case Scenario:

text

Win_probability_expected = f(
  Execution_quality_A = player_historical_average,
  Execution_quality_B = player_historical_average,
  xH_A = historical_average_per_ability,
  xH_B = historical_average_per_ability,
  xHm_A = E[hits] per ability,
  xHm_B = E[hits] per ability
)
Best-Case Scenario (Team A Perspective):

text

Win_probability_best = f(
  Execution_quality_A = maximum,
  Execution_quality_B = minimum,
  xH_A = maximum_realistic,
  xH_B = minimum_realistic,
  xHm_A = maximum_AoE_targets,
  xHm_B = minimum_AoE_targets
)
6.4 Confidence Interval Calculation
Given the Monte Carlo simulation distribution:

text

Confidence_interval_95 = [P_win - 1.96 × SE, P_win + 1.96 × SE]

Where:
SE = √(P_win × (1 - P_win) / N)
6.5 Historical Data Weighting Integration
Combine simulation-based probability with historical similar-teamfight outcomes:

text

P_final(Victory_A) = λ × P_simulation(Victory_A) + (1 - λ) × P_historical(Victory_A | Similar_teamfights)

Where:
λ ∈ [0, 1] represents confidence weight toward simulation vs. historical data
λ = f(Sample_size_historical, Similarity_score_average)
6.6 Output Metrics for Teamfight Analysis
Probability Range Representation:

text

Teamfight_outcome_distribution = {
  P(Victory_A)_worst: [probability, confidence_interval],
  P(Victory_A)_expected: [probability, confidence_interval],
  P(Victory_A)_best: [probability, confidence_interval],
  Scenario_likelihoods: {
    P(worst_case_occurs): probability,
    P(expected_case_occurs): probability,
    P(best_case_occurs): probability
  }
}
Sensitivity Analysis:

Critical abilities (abilities whose hit/miss status most significantly alters outcome probability)
Critical champions (champions whose death most significantly alters outcome probability)
Optimal target priority rankings
Optimal ability usage sequencing
Positioning vulnerability assessment (spatial zones with highest death probability)
Phase 7: System Architecture and Data Requirements
7.1 Database Schema Requirements
Champions Table:

Champion_ID (primary key)
Champion_name
Base_stats (JSON object containing all base stats per level)
Abilities (JSON array containing ability data: damage, cooldowns, ranges, coefficients)
Passive_effects (JSON object)
Items Table:

Item_ID (primary key)
Item_name
Stats (JSON object)
Passive_effects (JSON object)
Active_effects (JSON object)
Cost
Runes Table:

Rune_ID (primary key)
Rune_name
Rune_type (Keystone/Primary/Secondary)
Effects (JSON object)
Match_Data Table:

Match_ID (primary key)
Timestamp
Patch_version
Participant_data (JSON array)
Timeline_data (JSON array of game state snapshots)
Skillshot_Statistics Table:

Ability_ID (foreign key)
Environment_context (JSON object)
Mobility_classification
Casts_total
Hits_successful
xH_calculated
Last_updated
AoE_Statistics Table:

Ability_ID (foreign key)
Environment_context (JSON object)
Enemies_in_range
Hit_distribution (JSON object: {0: probability, 1: probability, ...})
Sample_size
Last_updated
Teamfight_History Table:

Teamfight_ID (primary key)
Match_ID (foreign key)
Timestamp_start
Timestamp_end
Team_A_composition (JSON array)
Team_B_composition (JSON array)
Team_A_gold_total
Team_B_gold_total
Team_A_items (JSON object)
Team_B_items (JSON object)
Ultimate_availability (JSON object)
Position_data (JSON object)
Outcome
Duration
7.2 Computational Requirements
Phase 1 (Basic Calculator):

Processing: Single-threaded computation sufficient
Memory: < 100 MB
Storage: Champion/item/rune static data (< 50 MB)
Phase 2-3 (xH Integration):

Processing: Database query optimization required
Memory: 500 MB - 1 GB (for xH lookup tables)
Storage: 1-10 GB (depending on historical match sample size)
Phase 4-6 (Full System):

Processing: Multi-threaded/GPU acceleration recommended for Monte Carlo simulations
Memory: 2-4 GB RAM
Storage: 50-500 GB (comprehensive historical match database)
Database: PostgreSQL or MongoDB recommended for JSON document storage
7.3 API Integration Requirements
Riot Games API Endpoints Required:

Match-v5 (match data retrieval)
Summoner-v4 (player identification)
League-v4 (ranked statistics)
Champion-Mastery-v4 (champion-specific player data)
Data Dragon (static champion/item/rune data)
7.4 Update Cycle Requirements
Champion/item/rune data: Update with each patch release (bi-weekly)
xH/xHm statistics: Continuous update as new match data ingested
Historical teamfight database: Continuous growth
Model recalibration: Monthly review of weighting coefficients based on prediction accuracy analysis
Phase 8: Validation and Accuracy Metrics
8.1 Prediction Accuracy Assessment
For 1v1 combat predictions:

text

Accuracy_1v1 = (Correct_predictions) / (Total_predictions)

Where correct prediction defined as:
- Predicted winner matches actual winner (binary classification)
- OR predicted win probability within ±10% of empirical win rate (regression)
For teamfight predictions:

text

Accuracy_teamfight = Σ(1 - |P_predicted(Victory_A) - Outcome_actual|) / N_teamfights

Where Outcome_actual ∈ {0, 1} (binary actual outcome)
8.2 Calibration Assessment
Assess whether predicted probabilities match observed frequencies:

text

For each probability bin b ∈ {[0-10%], [10-20%], ..., [90-100%]}:
  Calibration_error(b) = |P_predicted_average(b) - Win_rate_observed(b)|

Overall_calibration_error = Σ(N_b × Calibration_error(b)) / N_total
Well-calibrated model should show calibration_error < 0.05 across all bins.

8.3 Brier Score Calculation
text

Brier_score = (1/N) × Σ(P_predicted(Victory_A) - Outcome_actual)²

Where lower Brier score indicates better probabilistic prediction accuracy
Perfect predictions: Brier_score = 0
Random predictions: Brier_score ≈ 0.25
Conclusion
This multi-phase system provides a comprehensive framework for probabilistic combat analysis in League of Legends, progressing from deterministic damage calculations to sophisticated teamfight outcome prediction incorporating spatial awareness, execution quality variance, and historical pattern recognition. The system's modular architecture allows for iterative development and continuous refinement as additional data sources become available and prediction accuracy improves through expanded historical datasets.



SORRY i wrote down my part and asked AI to redo it
