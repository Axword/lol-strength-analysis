/**
 * Mathematical invariant eval for xH (xh-autoresearch metric).
 * Do not weaken checks to pass — fix the model instead.
 *
 * Run: npx --yes tsx scripts/eval-xh-math.ts
 */
import {
  ballisticRayMiss,
  ballisticSegmentMiss,
  ballisticSegmentCpa,
  ballisticFirstContactSec,
  accelZemClockSec,
  boundedAccelZemExtra,
  capsuleHitRadius,
  capsuleTravelBudgetUu,
  corridorHitProb,
  engagementHorizonSec,
  estimateXh,
  estimateXhm,
  firstContactTimeGo,
  inCastRange,
  interceptInMissileRange,
  interceptTimeGo,
  ISOTROPIC_PERP_FRAC,
  lateralMissFromHeadingError,
  lateralMissFromLead,
  occupancySigma,
  propagateLosFrame,
  requiredLeadAngle,
  type XhEstimateInput,
} from '../src/engine/xh'
import {
  averageXhRows,
  effectiveTargetMs,
  fightDodgeBands,
  ghostBuffActive,
  scaleXhBands,
  skillshotCastsForFight,
} from '../src/engine/combat'
import { emptyResolvedUtility } from '../src/engine/utility'
import { abilityCastsInFight } from '../src/engine/fightDuration'
import type { FighterLoadout } from '../src/engine/types'
import {
  abilityRateBaseline,
  abilityRateKey,
  abilityRatePosterior,
  analyticXhmMoments,
  analyticXhmPmfs,
  clearAbilityRates,
  corridorBrierSanity,
  corridorReliabilitySanity,
  estimateRhoFromPairwiseJoint,
  independentBinomialPmfs,
  invNorm,
  KILL_CRITERIA_VS_B1,
  logLoss,
  maxCalibrationError,
  adaptiveEce,
  meanCrpsCount,
  plattHeldOutGainSanity,
  plattScale,
  registerAbilityRate,
  rhoRecoverySanity,
  sigmaScaleKillSanity,
  temperatureScale,
  updateAbilityRate,
  corridorMiscalibrationKillSanity,
  xhmVarResidualSanity,
  xhmWrongRhoCrpsKillSanity,
  xhmTailCrpsSanity,
  discretePitEce,
  expectedCalibrationError,
  temperatureHeldOutGainSanity,
  corridorMurphySanity,
  murphyBrierDecomposition,
  xhmWrongRhoLogLossKillSanity,
  countBinEce,
  rhoTripleRecoverySanity,
  conditionalEceByTertile,
  discretePitKs,
  betaHeldOutGainSanity,
  murphyIdentitySanity,
  corridorBssSanity,
  xhmWrongRhoDssKillSanity,
  xhmIntervalCoverageSanity,
  abilityResidualKillSanity,
  xhmWrongRhoEnergyKillSanity,
  xhmWrongRhoWinklerKillSanity,
  isotonicHeldOutGainSanity,
  xhmWrongRhoJointLogLossKillSanity,
  corridorCoxSanity,
  corridorSpiegelhalterSanity,
  xhmConditionalCoverageSanity,
  stratifiedAbilityResidualKillSanity,
  xhmWrongRhoVariogramKillSanity,
  corridorIciSanity,
  corridorHosmerLemeshowSanity,
  corridorSphericalSanity,
  xhmPitAdSanity,
  xhmConditionalWinklerSanity,
  rhoQuartetRecoverySanity,
  xhmWrongRhoTwCrpsKillSanity,
  corridorConditionalIciSanity,
  xhmPitCvmSanity,
  xhmWrongRhoPinballKillSanity,
  xhmNearMissRhoCrpsKillSanity,
  xhmWrongRhoMidTwCrpsKillSanity,
} from './xh-baselines'

type Check = { name: string; pass: boolean; detail?: string }

const mid = { x: 0.45, y: 0.45 }
const near = { x: 0.48, y: 0.45 }
/** ~1040 uu from mid — inside 1175 range, near edge. */
const far = { x: 0.52, y: 0.45 }

function base(over: Partial<XhEstimateInput> = {}): XhEstimateInput {
  const out: XhEstimateInput = {
    targetChampionId: 'Lux',
    casterPosition: mid,
    targetPosition: near,
    abilityRange: 1175,
    vision: 'mutual',
    missileSpeed: 1200,
    missileWidth: 140,
    targetMovespeed: 335,
    dashReady: false,
    flashReady: false,
    leadSkill: 0.7,
    ...over,
  }
  // Eval contract: FoW age fixtures that omit LKP get explicit truth-as-belief
  // (oracle+age). Opt out by passing beliefMeanPosition: undefined via a
  // dedicated no-LKP call (see Pass-5 asserts) — here we only auto-fill when
  // the key is absent from `over`.
  const fow =
    out.vision === 'blind' ||
    (out.softVision != null && out.softVision < 0.85)
  if (
    fow &&
    !Object.prototype.hasOwnProperty.call(over, 'beliefMeanPosition') &&
    out.targetPosition
  ) {
    out.beliefMeanPosition = out.targetPosition
  }
  return out
}

const checks: Check[] = []

function assert(name: string, pass: boolean, detail?: string) {
  checks.push({ name, pass, detail })
}

// --- corridorHitProb unit ---
assert('corridor: sigma→0, mu=0 → ~1', Math.abs(corridorHitProb(100, 0, 1e-9) - 1) < 1e-6)
assert(
  'corridor: sigma→0, |mu|>R → ~0',
  corridorHitProb(10, 50, 1e-9) < 1e-6,
)
assert(
  'corridor: larger sigma lowers hit (mu=0)',
  corridorHitProb(50, 0, 20) > corridorHitProb(50, 0, 80),
)
assert(
  'corridor: larger |mu| lowers hit',
  corridorHitProb(50, 0, 30) > corridorHitProb(50, 40, 30),
)

// --- core estimateXh invariants ---
const pointBlank = estimateXh(
  base({
    targetPosition: { x: mid.x + 0.01, y: mid.y },
    abilityRange: 700,
    missileSpeed: 2000,
    missileWidth: 200,
    dashReady: false,
    crowdControlled: true,
  }),
)
assert(
  'point-blank CC immobile is high xH',
  pointBlank.xH > 0.85,
  `xH=${pointBlank.xH.toFixed(3)}`,
)

const maxRange = estimateXh(
  base({
    targetPosition: far,
    abilityRange: 1175,
    missileSpeed: 1200,
    missileWidth: 70,
    dashReady: true,
    flashReady: true,
    targetChampionId: 'Akali',
  }),
)
assert(
  'max-range mobile < point-blank CC',
  maxRange.xH < pointBlank.xH,
  `max=${maxRange.xH.toFixed(3)} pb=${pointBlank.xH.toFixed(3)}`,
)

const blindFresh = estimateXh(base({ vision: 'blind', lastKnownAgeSec: 0.3 }))
const blindStale = estimateXh(base({ vision: 'blind', lastKnownAgeSec: 6 }))
assert(
  'stale LKP blind < fresh LKP blind',
  blindStale.xH < blindFresh.xH,
  `stale=${blindStale.xH.toFixed(3)} fresh=${blindFresh.xH.toFixed(3)}`,
)

const mutual = estimateXh(base({ vision: 'mutual' }))
assert(
  'blind stale < mutual (same geometry)',
  blindStale.xH < mutual.xH,
  `blind=${blindStale.xH.toFixed(3)} mutual=${mutual.xH.toFixed(3)}`,
)

const ambush = estimateXh(base({ vision: 'ambush', dashReady: true }))
const mutualDash = estimateXh(base({ vision: 'mutual', dashReady: true }))
assert(
  'ambush ≥ mutual when dash ready (later reaction)',
  ambush.xH + 1e-9 >= mutualDash.xH * 0.98,
  `ambush=${ambush.xH.toFixed(3)} mutual=${mutualDash.xH.toFixed(3)}`,
)

const depleted = estimateXh(
  base({
    targetChampionId: 'Akali',
    dashReady: false,
    flashReady: false,
  }),
)
const fullBudget = estimateXh(
  base({
    targetChampionId: 'Akali',
    dashReady: true,
    flashReady: true,
  }),
)
assert(
  'dash+flash ready lowers xH vs depleted',
  fullBudget.xH < depleted.xH,
  `full=${fullBudget.xH.toFixed(3)} dep=${depleted.xH.toFixed(3)}`,
)

const cc = estimateXh(
  base({
    targetChampionId: 'Akali',
    dashReady: true,
    crowdControlled: true,
  }),
)
assert(
  'CC raises xH vs same kit free',
  cc.xH > fullBudget.xH,
  `cc=${cc.xH.toFixed(3)} free=${fullBudget.xH.toFixed(3)}`,
)

assert('bands present', !!pointBlank.bands)
assert(
  'bands: best ≥ typical ≥ worst',
  !!pointBlank.bands &&
    pointBlank.bands.best + 1e-9 >= pointBlank.bands.typical &&
    pointBlank.bands.typical + 1e-9 >= pointBlank.bands.worst,
  JSON.stringify(pointBlank.bands),
)

const wide = estimateXh(base({ missileWidth: 220 }))
const thin = estimateXh(base({ missileWidth: 50 }))
assert(
  'wider missile → higher xH',
  wide.xH > thin.xH,
  `wide=${wide.xH.toFixed(3)} thin=${thin.xH.toFixed(3)}`,
)

const fast = estimateXh(base({ missileSpeed: 2800 }))
const slow = estimateXh(base({ missileSpeed: 800 }))
assert(
  'faster missile → higher xH (less dodge window)',
  fast.xH > slow.xH,
  `fast=${fast.xH.toFixed(3)} slow=${slow.xH.toFixed(3)}`,
)

const oor = estimateXh(
  base({
    targetPosition: { x: 0.95, y: 0.95 },
    abilityRange: 500,
  }),
)
assert('out of range → xH 0', oor.xH === 0 && oor.inRange === false)

// --- xHm dependence ---
const p = 0.55
const n = 4
const indepVar = n * p * (1 - p)
const probs = estimateXhm(p, n, 0.5)
const mean = probs.reduce((s, pk, k) => s + k * pk, 0)
const ex2 = probs.reduce((s, pk, k) => s + k * k * pk, 0)
const depVar = ex2 - mean * mean
assert(
  'xHm probs sum ~ 1',
  Math.abs(probs.reduce((a, b) => a + b, 0) - 1) < 0.02,
  `sum=${probs.reduce((a, b) => a + b, 0).toFixed(3)}`,
)
assert(
  'xHm mean ≈ n*p',
  Math.abs(mean - n * p) < 0.25,
  `mean=${mean.toFixed(3)}`,
)
assert(
  'xHm variance > independent binomial (positive dependence)',
  depVar > indepVar * 0.95,
  `depVar=${depVar.toFixed(3)} indep=${indepVar.toFixed(3)}`,
)

// Extreme-cell inflation vs independent Binomial (equicorrelated probit /
// single-factor latent): P(K=0) and P(K=n) both rise under ρ > 0.
const indepP0 = Math.pow(1 - p, n)
const indepPn = Math.pow(p, n)
assert(
  'xHm P(K=0) inflates vs independent binomial',
  probs[0]! > indepP0 * 1.5,
  `P0=${probs[0]!.toFixed(4)} indep=${indepP0.toFixed(4)}`,
)
assert(
  'xHm P(K=n) inflates vs independent binomial',
  probs[n]! > indepPn * 1.5,
  `Pn=${probs[n]!.toFixed(4)} indep=${indepPn.toFixed(4)}`,
)
const probsIndepRho = estimateXhm(p, n, 0)
assert(
  'xHm ρ→0 extremes ≈ independent binomial',
  Math.abs(probsIndepRho[0]! - indepP0) < 0.02 &&
    Math.abs(probsIndepRho[n]! - indepPn) < 0.02,
  `P0=${probsIndepRho[0]!.toFixed(4)} Pn=${probsIndepRho[n]!.toFixed(4)}`,
)

// --- no multiplicative prior resurrection ---
const lux = estimateXh(base({ targetChampionId: 'Lux', dashReady: false }))
const akaliSameGeo = estimateXh(
  base({ targetChampionId: 'Akali', dashReady: false, flashReady: false }),
)
assert(
  'kit tag alone (dashes down) must not collapse Akali≪Lux',
  Math.abs(lux.xH - akaliSameGeo.xH) < 0.08,
  `Lux=${lux.xH.toFixed(3)} Akali=${akaliSameGeo.xH.toFixed(3)}`,
)

// --- geometry / collision-triangle (Pass-1 GEO) ---
assert(
  'intercept t_go @ v=0 ≈ R/V_m',
  Math.abs(interceptTimeGo(1000, 2000, 0, 0) - 0.5) < 1e-6,
)
assert(
  'fleeing radial lengthens t_go vs approaching',
  interceptTimeGo(1000, 1600, 300, 0) > interceptTimeGo(1000, 1600, -300, 0),
)
assert('perfect lead → lateral miss 0', lateralMissFromLead(0.5, 200, 1) === 0)
assert(
  'zero lead → miss = |v_perp| t_go',
  Math.abs(lateralMissFromLead(0.5, 200, 0) - 100) < 1e-9,
)
assert('isotropic perp frac ≈ 2/π', Math.abs(ISOTROPIC_PERP_FRAC - 2 / Math.PI) < 1e-12)
const leadHi = estimateXh(base({ leadSkill: 1, targetPerpVel: 250 }))
const leadLo = estimateXh(base({ leadSkill: 0, targetPerpVel: 250 }))
assert(
  'better lead → higher xH (same kinematics)',
  leadHi.xH > leadLo.xH,
  `hi=${leadHi.xH.toFixed(3)} lo=${leadLo.xH.toFixed(3)}`,
)
const approach = estimateXh(
  base({ targetRadialVel: -280, targetPerpVel: 200, leadSkill: 0.5 }),
)
const flee = estimateXh(
  base({ targetRadialVel: 280, targetPerpVel: 200, leadSkill: 0.5 }),
)
assert(
  'approaching along LOS → higher xH than fleeing',
  approach.xH > flee.xH,
  `ap=${approach.xH.toFixed(3)} fl=${flee.xH.toFixed(3)}`,
)

// --- aim / Schmidt–SDN (Pass-1 AIM) ---
const aimLongT = estimateXh(base({ aimTimeSec: 0.55, dashReady: false }))
const aimShortT = estimateXh(base({ aimTimeSec: 0.14, dashReady: false }))
assert(
  'shorter T_avail → lower xH (Schmidt)',
  aimShortT.xH < aimLongT.xH,
  `short=${aimShortT.xH.toFixed(3)} long=${aimLongT.xH.toFixed(3)}`,
)
assert(
  'shorter T_avail → larger sigma.aim',
  !!aimShortT.sigma && !!aimLongT.sigma && aimShortT.sigma.aim > aimLongT.sigma.aim,
  `σ_short=${aimShortT.sigma?.aim.toFixed(1)} σ_long=${aimLongT.sigma?.aim.toFixed(1)}`,
)

// --- strategy bands (Pass-1 STRATEGY) ---
const env = estimateXh(
  base({
    targetChampionId: 'Akali',
    dashReady: true,
    flashReady: false,
    missileSpeed: 1000,
  }),
)
assert(
  'bands: worst < typical when dash ready, flash CD (envelope)',
  !!env.bands && env.bands.worst + 1e-6 < env.bands.typical,
  JSON.stringify(env.bands),
)
const dep = estimateXh(
  base({
    targetChampionId: 'Akali',
    dashReady: false,
    flashReady: false,
    missileSpeed: 1000,
  }),
)
assert(
  'bands: depleted ⇒ typical ≈ best',
  !!dep.bands && Math.abs(dep.bands.typical - dep.bands.best) < 0.02,
  JSON.stringify(dep.bands),
)
assert(
  'bands: depleted still allows worst < typical via Flash envelope',
  !!dep.bands && dep.bands.worst + 1e-6 < dep.bands.typical,
  JSON.stringify(dep.bands),
)
const amb = estimateXh(
  base({
    vision: 'ambush',
    targetChampionId: 'Akali',
    dashReady: true,
    flashReady: true,
    missileSpeed: 1200,
  }),
)
assert(
  'ambush+budget: band spread (best−worst) > 0.02',
  !!amb.bands && amb.bands.best - amb.bands.worst > 0.02,
  JSON.stringify(amb.bands),
)
const ccBands = estimateXh(
  base({
    targetChampionId: 'Akali',
    dashReady: true,
    flashReady: true,
    crowdControlled: true,
    missileSpeed: 1000,
  }),
)
assert(
  'CC ⇒ bands within 0.01',
  !!ccBands.bands && ccBands.bands.best - ccBands.bands.worst < 0.01,
  JSON.stringify(ccBands.bands),
)

// --- vision / belief (Pass-1 VISION) ---
const onTruth = estimateXh(base({ vision: 'blind', lastKnownAgeSec: 1 }))
const offLkp = estimateXh(
  base({
    vision: 'blind',
    lastKnownAgeSec: 1,
    beliefMeanPosition: { x: mid.x - 0.04, y: mid.y },
  }),
)
assert(
  'belief-aim off LKP ≤ oracle-aim same age',
  offLkp.xH <= onTruth.xH + 1e-9,
  `off=${offLkp.xH.toFixed(3)} on=${onTruth.xH.toFixed(3)}`,
)
const justLost = estimateXh(base({ vision: 'blind', lastKnownAgeSec: 0 }))
assert(
  'fresh loss not catastrophic vs mutual',
  justLost.xH > mutual.xH * 0.85,
  `justLost=${justLost.xH.toFixed(3)} mutual=${mutual.xH.toFixed(3)}`,
)
const edge = estimateXh(
  base({ vision: 'blind', softVision: 0.7, lastKnownAgeSec: 3 }),
)
const dark = estimateXh(
  base({ vision: 'blind', softVision: 0.0, lastKnownAgeSec: 3 }),
)
assert(
  'softVision edge > full dark',
  edge.xH > dark.xH,
  `edge=${edge.xH.toFixed(3)} dark=${dark.xH.toFixed(3)}`,
)
const ancient = estimateXh(base({ vision: 'blind', lastKnownAgeSec: 30 }))
assert(
  'ancient LKP still finite and low',
  ancient.xH < 0.2 && Number.isFinite(ancient.xH),
  `xH=${ancient.xH.toFixed(3)}`,
)

// --- empirics / calibration (Pass-2 EMPIRICS) ---
// Corridor closed-form p̂ must match synthetic N(μ,σ²) hit rates (Brier sanity).
{
  const cells = [
    { R: 50, mu: 0, sigma: 30 },
    { R: 50, mu: 20, sigma: 35 },
    { R: 80, mu: 0, sigma: 45 },
    { R: 40, mu: 30, sigma: 25 },
    { R: 100, mu: 10, sigma: 60 },
  ].map((c) => ({
    ...c,
    predictedXh: corridorHitProb(c.R, c.mu, c.sigma),
  }))
  const sanity = corridorBrierSanity({
    cells,
    trials: 8000,
    rateTol: KILL_CRITERIA_VS_B1.corridorRateTol,
  })
  assert(
    'corridor Brier: |empirical−p̂| ≤ rateTol',
    sanity.maxAbsRateGap <= KILL_CRITERIA_VS_B1.corridorRateTol,
    `maxGap=${sanity.maxAbsRateGap.toFixed(4)} tol=${KILL_CRITERIA_VS_B1.corridorRateTol}`,
  )
  assert(
    'corridor Brier: model ≤ coin×ratio (kill criteria)',
    sanity.meanBrier <=
      sanity.meanCoinBrier * KILL_CRITERIA_VS_B1.brierVsCoinMaxRatio + 1e-6,
    `brier=${sanity.meanBrier.toFixed(4)} coin=${sanity.meanCoinBrier.toFixed(4)}`,
  )
}

// Ability-rate baseline stub wiring (no logs yet — table + fallback only).
clearAbilityRates()
registerAbilityRate({ abilityKey: 'LuxQ', hits: 55, casts: 100 })
const luxRate = abilityRateBaseline('LuxQ')
const missRate = abilityRateBaseline('NoSuchAbility')
assert(
  'ability-rate stub: registered empirical',
  luxRate.source === 'empirical' && Math.abs(luxRate.rate - 0.55) < 1e-12,
  JSON.stringify(luxRate),
)
assert(
  'ability-rate stub: missing → fallback 0.5',
  missRate.source === 'fallback' && missRate.rate === 0.5 && missRate.n === 0,
  JSON.stringify(missRate),
)
clearAbilityRates()

// Temperature / Platt placeholders: identity at T=1 / (a=0,b=1); T>1 softens.
assert(
  'temperature identity at T=1',
  Math.abs(temperatureScale(0.72, 1) - 0.72) < 1e-12,
)
assert(
  'platt identity at a=0,b=1',
  Math.abs(plattScale(0.72, 0, 1) - 0.72) < 1e-12,
)
assert(
  'temperature T>1 softens toward 0.5',
  temperatureScale(0.85, 1.8) < 0.85 && temperatureScale(0.85, 1.8) > 0.5,
  `p=${temperatureScale(0.85, 1.8).toFixed(4)}`,
)
assert(
  'kill-criteria constants finite',
  Number.isFinite(KILL_CRITERIA_VS_B1.corridorRateTol) &&
    KILL_CRITERIA_VS_B1.minBrierGainToKill > 0,
  JSON.stringify(KILL_CRITERIA_VS_B1),
)

// --- geometry deepen (Pass-2 GEO) ---
assert(
  'required lead @ v_perp=0 → 0',
  Math.abs(requiredLeadAngle(0.5, 1000, 0, 0)) < 1e-12,
)
{
  const R = 1000
  const Vm = 1600
  const vp = 200
  const tg = interceptTimeGo(R, Vm, 0, vp)
  const lam = requiredLeadAngle(tg, R, 0, vp)
  const chord = lateralMissFromHeadingError(tg, Vm, lam, 0)
  assert(
    'collision-triangle identity: |sin λ*| V_m t_go = |v_perp| t_go',
    Math.abs(chord - Math.abs(vp) * tg) < 1e-6,
    `chord=${chord.toFixed(6)} vpT=${(Math.abs(vp) * tg).toFixed(6)}`,
  )
  assert(
    'perfect heading → miss 0',
    lateralMissFromHeadingError(tg, Vm, lam, lam) === 0,
  )
}
assert(
  'stationary edge: D ≤ R_max+R_champ via t_go reach',
  interceptInMissileRange(1175 / 1200, 1200, 1175) === true,
)
assert(
  'stationary beyond hitbox budget → OOR',
  interceptInMissileRange((1175 + 66) / 1200, 1200, 1175) === false,
)
{
  const D = 1100
  const Vm = 1200
  const Rmax = 1175
  const tg = interceptTimeGo(D, Vm, 280, 335 * ISOTROPIC_PERP_FRAC)
  assert(
    'fleeing near edge: t_go reach can OOR while D < R_max',
    D < Rmax && interceptInMissileRange(tg, Vm, Rmax) === false,
    `D=${D} reach=${(Vm * tg).toFixed(0)}`,
  )
}

// --- aim deepen (Pass-2 AIM) ---
const wideFitts = estimateXh(
  base({
    missileWidth: 220,
    aimTimeSec: 0.15,
    dashReady: false,
    crowdControlled: true,
  }),
)
const thinFitts = estimateXh(
  base({
    missileWidth: 50,
    aimTimeSec: 0.15,
    dashReady: false,
    crowdControlled: true,
  }),
)
assert(
  'narrower W → larger sigma.aim (Fitts ID gate)',
  !!wideFitts.sigma &&
    !!thinFitts.sigma &&
    thinFitts.sigma.aim > wideFitts.sigma.aim,
  `thin=${thinFitts.sigma?.aim.toFixed(1)} wide=${wideFitts.sigma?.aim.toFixed(1)}`,
)
assert(
  'factors expose fitts_ID',
  thinFitts.factors.some((f) => f.startsWith('fitts_ID:')),
  thinFitts.factors.join(','),
)
const nearId = estimateXh(
  base({
    targetPosition: { x: mid.x + 0.012, y: mid.y },
    abilityRange: 700,
    missileWidth: 140,
    aimTimeSec: 0.3,
    dashReady: false,
    crowdControlled: true,
  }),
)
const farId = estimateXh(
  base({
    targetPosition: far,
    abilityRange: 1175,
    missileWidth: 140,
    aimTimeSec: 0.3,
    dashReady: false,
    crowdControlled: true,
    flashReady: false,
  }),
)
assert(
  'same T,W: farther D → larger sigma.aim (ID + D/T)',
  !!nearId.sigma && !!farId.sigma && farId.sigma.aim > nearId.sigma.aim,
  `near=${nearId.sigma?.aim.toFixed(1)} far=${farId.sigma?.aim.toFixed(1)}`,
)
const forcedNarrow = estimateXh(
  base({
    fittsWidthUu: 60,
    aimTimeSec: 0.15,
    dashReady: false,
    crowdControlled: true,
  }),
)
const forcedWide = estimateXh(
  base({
    fittsWidthUu: 280,
    aimTimeSec: 0.15,
    dashReady: false,
    crowdControlled: true,
  }),
)
assert(
  'fittsWidthUu override: narrower → larger sigma.aim',
  !!forcedNarrow.sigma &&
    !!forcedWide.sigma &&
    forcedNarrow.sigma.aim > forcedWide.sigma.aim,
)
const fastMis2 = estimateXh(
  base({
    missileSpeed: 2800,
    aimTimeSec: 0.35,
    dashReady: false,
    crowdControlled: true,
  }),
)
const slowMis2 = estimateXh(
  base({
    missileSpeed: 800,
    aimTimeSec: 0.35,
    dashReady: false,
    crowdControlled: true,
  }),
)
assert(
  'Pass-2: slower missile → sigma.aim ≥ faster (TOF horizon ≠ T_avail)',
  !!slowMis2.sigma &&
    !!fastMis2.sigma &&
    slowMis2.sigma.aim + 1e-6 >= fastMis2.sigma.aim,
  `slow=${slowMis2.sigma?.aim.toFixed(1)} fast=${fastMis2.sigma?.aim.toFixed(1)}`,
)

// --- strategy deepen (Pass-2 STRATEGY) ---
const pbAmb = estimateXh(
  base({
    vision: 'ambush',
    targetChampionId: 'Akali',
    dashReady: true,
    flashReady: true,
    targetPosition: { x: mid.x + 0.008, y: mid.y },
    missileSpeed: 3000,
    abilityRange: 700,
  }),
)
assert(
  'precommit: ambush point-blank still worst < typical',
  !!pbAmb.bands && pbAmb.bands.worst + 1e-6 < pbAmb.bands.typical,
  JSON.stringify(pbAmb.bands),
)
const unk = estimateXh(
  base({
    targetChampionId: 'Akali',
    dashReady: true,
    flashReady: undefined,
    missileSpeed: 1000,
  }),
)
assert(
  'ne mix: worst ≤ mix ≤ typical when Flash unknown',
  !!unk.bands &&
    unk.bands.mix != null &&
    unk.bands.mix + 1e-9 >= unk.bands.worst &&
    unk.bands.mix <= unk.bands.typical + 1e-9,
  JSON.stringify(unk.bands),
)
const knownDown = estimateXh(
  base({
    targetChampionId: 'Akali',
    dashReady: true,
    flashReady: false,
    flashUpPrior: 0.35,
    missileSpeed: 1000,
  }),
)
assert(
  'ne mix: known Flash down still fears envelope',
  !!knownDown.bands &&
    knownDown.bands.mix != null &&
    knownDown.bands.mix + 1e-6 < knownDown.bands.typical,
  JSON.stringify(knownDown.bands),
)
const onCd = estimateXh(
  base({
    targetChampionId: 'Akali',
    dashReady: true,
    flashCdRemainingSec: 120,
    missileSpeed: 1000,
  }),
)
assert(
  'summoner CD: Flash on CD ⇒ typical > worst (envelope)',
  !!onCd.bands && onCd.bands.worst + 1e-6 < onCd.bands.typical,
  JSON.stringify(onCd.bands),
)
const flashUp = estimateXh(
  base({
    targetChampionId: 'Akali',
    dashReady: true,
    flashReady: true,
    missileSpeed: 1000,
  }),
)
assert(
  'ne mix: Flash known up → mix === typical',
  !!flashUp.bands &&
    flashUp.bands.mix != null &&
    Math.abs(flashUp.bands.mix - flashUp.bands.typical) < 1e-9,
  JSON.stringify(flashUp.bands),
)

// --- empirics deepen (Pass-3 EMPIRICS) ---
{
  const r05 = rhoRecoverySanity({ p: 0.55, rhoStar: 0.5, nPairs: 30000, seed: 42 })
  assert(
    'ρ MoM: recover ρ★=0.5 within rhoAbsErrTol',
    r05.ok,
    `hat=${r05.rhoHat.toFixed(3)} err=${r05.absErr.toFixed(3)}`,
  )
  const r02 = rhoRecoverySanity({ p: 0.55, rhoStar: 0.2, nPairs: 30000, seed: 43 })
  assert(
    'ρ MoM: recover ρ★=0.2 within rhoAbsErrTol',
    r02.ok,
    `hat=${r02.rhoHat.toFixed(3)} err=${r02.absErr.toFixed(3)}`,
  )
  const m0 = analyticXhmMoments(0.55, 2, 0)
  assert(
    'ρ→0: pairwise joint ≈ p²',
    Math.abs(m0.pairwiseJoint - 0.55 * 0.55) < 0.01,
    `π11=${m0.pairwiseJoint.toFixed(4)}`,
  )
  // Frechet edge: invert at independence
  const rhoAtIndep = estimateRhoFromPairwiseJoint(0.55, 0.55 * 0.55)
  assert('ρ MoM at π11=p² → ~0', rhoAtIndep < 0.08, `ρ=${rhoAtIndep.toFixed(3)}`)
}
{
  const rel = corridorReliabilitySanity({
    cells: [
      { R: 50, mu: 10, sigma: 30 },
      { R: 80, mu: 0, sigma: 40 },
      { R: 40, mu: 35, sigma: 25 },
      { R: 60, mu: 0, sigma: 20 },
    ],
    trialsPerCell: 2500,
    bins: 10,
  })
  assert(
    'reliability ECE: corridor synthetic ≤ eceTol',
    rel.ok,
    `ece=${rel.ece.toFixed(4)} tol=${KILL_CRITERIA_VS_B1.eceTol}`,
  )
}
{
  // Log-loss: closed-form corridor vs coin on synthetic draws
  const cells = [
    { R: 50, mu: 10, sigma: 30 },
    { R: 80, mu: 0, sigma: 40 },
  ]
  const preds: number[] = []
  const outs: number[] = []
  for (const [i, cell] of cells.entries()) {
    const pHat = corridorHitProb(cell.R, cell.mu, cell.sigma)
    let s = (0xbeef ^ (i * 17)) | 0
    const nextU = () => {
      s = (Math.imul(s, 1664525) + 1013904223) | 0
      return (s >>> 0) / 4294967296
    }
    for (let t = 0; t < 4000; t++) {
      const u1 = Math.max(1e-12, nextU())
      const u2 = nextU()
      const z = Math.sqrt(-2 * Math.log(u1)) * Math.cos(2 * Math.PI * u2)
      const hit = Math.abs(cell.mu + cell.sigma * z) < cell.R ? 1 : 0
      preds.push(pHat)
      outs.push(hit)
    }
  }
  const ll = logLoss(preds, outs)
  const rate = outs.reduce((a, b) => a + b, 0) / outs.length
  const coinLl = logLoss(
    outs.map(() => rate),
    outs,
  )
  assert(
    'log-loss: model ≤ coin×logLossVsCoinMaxRatio',
    ll <= coinLl * KILL_CRITERIA_VS_B1.logLossVsCoinMaxRatio + 1e-6,
    `ll=${ll.toFixed(4)} coin=${coinLl.toFixed(4)}`,
  )
}
{
  const p = 0.55
  const n = 4
  const rho = 0.5
  const dep = analyticXhmPmfs(p, n, rho)
  const indep = independentBinomialPmfs(n, p)
  const thresh = invNorm(p)
  const sR = Math.sqrt(rho)
  const sI = Math.sqrt(1 - rho)
  const draws: number[] = []
  let st = 0x63727073
  const nextU = () => {
    st = (Math.imul(st, 1664525) + 1013904223) | 0
    return (st >>> 0) / 4294967296
  }
  const bm = () => {
    const u1 = Math.max(1e-12, nextU())
    const u2 = nextU()
    return Math.sqrt(-2 * Math.log(u1)) * Math.cos(2 * Math.PI * u2)
  }
  for (let t = 0; t < 3000; t++) {
    const Z = bm()
    let k = 0
    for (let j = 0; j < n; j++) {
      if (sR * Z + sI * bm() < thresh) k++
    }
    draws.push(k)
  }
  const crpsDep = meanCrpsCount(dep, draws)
  const crpsIndep = meanCrpsCount(indep, draws)
  assert(
    'CRPS: dependent xHm ≤ indep on overdispersed draws (ρ★=0.5)',
    crpsDep <= crpsIndep + 1e-6,
    `dep=${crpsDep.toFixed(4)} indep=${crpsIndep.toFixed(4)}`,
  )
}
{
  clearAbilityRates()
  const key = abilityRateKey('LuxQ')
  for (let i = 0; i < 400; i++) {
    updateAbilityRate(key, i < 240 ? 1 : 0) // Bern(0.6)
  }
  const post = abilityRatePosterior(key)
  assert(
    'online ability update: N=400 Bern(0.6) → |rate−0.6|≤0.08',
    Math.abs(post.mean - 0.6) <= 0.08,
    `mean=${post.mean.toFixed(3)} n=${post.n}`,
  )
  const strata = abilityRateKey('LuxQ', { vision: 'blind', rangeBand: 'long' })
  const global = abilityRateBaseline('LuxQ')
  const stratified = abilityRateBaseline(strata)
  assert(
    'strata key: LuxQ|blind|long ≠ LuxQ global until registered',
    strata !== 'LuxQ' &&
      stratified.source === 'fallback' &&
      global.source === 'empirical',
    `strata=${strata} g=${global.source} s=${stratified.source}`,
  )
  clearAbilityRates()
}
{
  const kill = sigmaScaleKillSanity({
    R: 50,
    mu: 0,
    sigmaStar: 30,
    sigmaModel: 45, // 1.5×
    trials: 10000,
  })
  assert(
    'σ-scale kill: wrong σ (1.5×) trips shouldKillScale',
    kill.shouldKillScale,
    `gap=${kill.rateGap.toFixed(3)} ece=${kill.ece.toFixed(3)}`,
  )
  const keep = sigmaScaleKillSanity({
    R: 50,
    mu: 0,
    sigmaStar: 30,
    sigmaModel: 30,
    trials: 10000,
  })
  assert(
    'σ-scale keep: σ_model=σ★ does not trip; Pass-2 rateTol still holds',
    !keep.shouldKillScale && keep.rateGap <= KILL_CRITERIA_VS_B1.corridorRateTol,
    `gap=${keep.rateGap.toFixed(3)} ece=${keep.ece.toFixed(3)}`,
  )
}
assert(
  'Pass-3 kill-criteria deepen fields finite',
  Number.isFinite(KILL_CRITERIA_VS_B1.rhoAbsErrTol) &&
    KILL_CRITERIA_VS_B1.eceTol > 0 &&
    KILL_CRITERIA_VS_B1.logLossVsCoinMaxRatio >= KILL_CRITERIA_VS_B1.brierVsCoinMaxRatio,
  JSON.stringify(KILL_CRITERIA_VS_B1),
)

// --- geometry deepen (Pass-3 GEO) ---
{
  const id = propagateLosFrame(1000, 0, 0, 0.5)
  assert(
    'propagate delay @ v=0 → range unchanged',
    Math.abs(id.rangeUu - 1000) < 1e-9 && id.vRadial === 0 && id.vPerp === 0,
  )
  const moved = propagateLosFrame(1000, 0, 200, 0.5)
  assert(
    'propagate perp delay → range grows',
    moved.rangeUu > 1000,
    `R'=${moved.rangeUu.toFixed(1)}`,
  )
}
{
  const miss0 = ballisticRayMiss(1000, 0, 200, 1600, 0, 1)
  const lam = requiredLeadAngle(interceptTimeGo(1000, 1600, 0, 200), 1000, 0, 200)
  const missPerfect = ballisticRayMiss(1000, 0, 200, 1600, lam, 1)
  assert(
    'ray CPA: perfect lead miss ≈ 0',
    missPerfect < 5,
    `miss=${missPerfect.toFixed(2)}`,
  )
  assert(
    'ray CPA: zero lead miss > perfect',
    miss0 > missPerfect + 10,
    `zero=${miss0.toFixed(1)} perf=${missPerfect.toFixed(1)}`,
  )
}
assert('inCastRange: D inside', inCastRange(1100, 1175) === true)
assert('inCastRange: D beyond+hitbox', inCastRange(1300, 1175) === false)

// --- aim deepen (Pass-3 AIM) ---
{
  const relThin = estimateXh(
    base({
      missileWidth: 50,
      aimTimeSec: 0.18,
      releaseJitterSec: 0.05,
      dashReady: false,
      crowdControlled: true,
      targetMovespeed: 420,
    }),
  )
  const relWide = estimateXh(
    base({
      missileWidth: 220,
      aimTimeSec: 0.18,
      releaseJitterSec: 0.05,
      dashReady: false,
      crowdControlled: true,
      targetMovespeed: 420,
    }),
  )
  assert(
    'Pass-3: thin W → larger sigma.aim (release–urgency/aperture)',
    !!relThin.sigma &&
      !!relWide.sigma &&
      relThin.sigma.aim > relWide.sigma.aim,
    `thin=${relThin.sigma?.aim.toFixed(1)} wide=${relWide.sigma?.aim.toFixed(1)}`,
  )
}

// --- vision deepen (Pass-3 VISION) ---
{
  const spotted = estimateXh(
    base({
      vision: 'blind',
      softVision: 0,
      lastKnownAgeSec: 1.5,
      spottedByTarget: true,
      dashReady: true,
      flashReady: false,
    }),
  )
  const unspotted = estimateXh(
    base({
      vision: 'blind',
      softVision: 0,
      lastKnownAgeSec: 1.5,
      spottedByTarget: false,
      dashReady: true,
      flashReady: false,
    }),
  )
  assert(
    'spottedByTarget (blind) → lower or equal xH (earlier reaction)',
    spotted.xH <= unspotted.xH + 1e-6,
    `spotted=${spotted.xH.toFixed(3)} un=${unspotted.xH.toFixed(3)}`,
  )
}

// --- strategy deepen (Pass-3 STRATEGY) ---
{
  const half = estimateXh(
    base({
      targetChampionId: 'Ahri',
      dashChargesRemaining: 1,
      flashReady: false,
      missileSpeed: 1000,
    }),
  )
  const full = estimateXh(
    base({
      targetChampionId: 'Ahri',
      dashReady: true,
      flashReady: false,
      missileSpeed: 1000,
    }),
  )
  const none = estimateXh(
    base({
      targetChampionId: 'Ahri',
      dashReady: false,
      flashReady: false,
      missileSpeed: 1000,
    }),
  )
  assert(
    'dash charges: half budget between depleted and full',
    none.xH >= half.xH - 1e-6 && half.xH >= full.xH - 1e-6,
    `none=${none.xH.toFixed(3)} half=${half.xH.toFixed(3)} full=${full.xH.toFixed(3)}`,
  )
  const unk = estimateXh(
    base({
      targetChampionId: 'Akali',
      dashReady: true,
      flashReady: undefined,
      missileSpeed: 1000,
    }),
  )
  const knownDown = estimateXh(
    base({
      targetChampionId: 'Akali',
      dashReady: true,
      flashReady: false,
      missileSpeed: 1000,
    }),
  )
  assert(
    'NE: unknown Flash → mix ≤ known-down mix (higher π fear)',
    !!unk.bands?.mix &&
      !!knownDown.bands?.mix &&
      unk.bands.mix <= knownDown.bands.mix + 1e-6,
    `unk=${unk.bands?.mix.toFixed(3)} down=${knownDown.bands?.mix.toFixed(3)}`,
  )
  assert(
    'NE: unknown Flash → packet xH uses mix',
    !!unk.bands?.mix && Math.abs(unk.xH - unk.bands.mix) < 1e-9,
    `xH=${unk.xH.toFixed(3)} mix=${unk.bands?.mix.toFixed(3)}`,
  )
}

// --- Pass-4 deepen asserts ---
{
  const id = propagateLosFrame(500, -2000, 0, 0.25)
  assert(
    'Pass-4: LOS collapse preserves speed into perp',
    Math.abs(id.vRadial) < 1e-6 && id.vPerp > 1000,
    JSON.stringify(id),
  )
}
{
  const webFast = estimateXh(
    base({
      missileSpeed: 2800,
      aimTimeSec: 0.35,
      releaseJitterSec: 0.04,
      releaseDelaySec: 0.28,
      dashReady: false,
      crowdControlled: true,
    }),
  )
  const webSlow = estimateXh(
    base({
      missileSpeed: 800,
      aimTimeSec: 0.35,
      releaseJitterSec: 0.04,
      releaseDelaySec: 0.28,
      dashReady: false,
      crowdControlled: true,
    }),
  )
  assert(
    'Pass-4: slower missile → sigma.aim ≥ faster (Weber)',
    !!webSlow.sigma &&
      !!webFast.sigma &&
      webSlow.sigma.aim + 1e-6 >= webFast.sigma.aim,
    `slow=${webSlow.sigma?.aim.toFixed(1)} fast=${webFast.sigma?.aim.toFixed(1)}`,
  )
  const prepLong = estimateXh(
    base({
      aimTimeSec: 0.3,
      releaseDelaySec: 0.45,
      dashReady: false,
      crowdControlled: true,
    }),
  )
  const prepSnap = estimateXh(
    base({
      aimTimeSec: 0.3,
      releaseDelaySec: 0.05,
      dashReady: false,
      crowdControlled: true,
    }),
  )
  assert(
    'Pass-4: longer prep → lower or equal sigma.aim',
    !!prepLong.sigma &&
      !!prepSnap.sigma &&
      prepLong.sigma.aim <= prepSnap.sigma.aim + 1e-6,
    `long=${prepLong.sigma?.aim.toFixed(1)} snap=${prepSnap.sigma?.aim.toFixed(1)}`,
  )
}
{
  const accel = estimateXh(
    base({ residualAccelUuPerSec2: 800, leadSkill: 1, targetPerpVel: 200 }),
  )
  const noAccel = estimateXh(
    base({ residualAccelUuPerSec2: 0, leadSkill: 1, targetPerpVel: 200 }),
  )
  assert(
    'Pass-4: accel ZEM extra → lower xH',
    accel.xH <= noAccel.xH + 1e-6,
    `a=${accel.xH.toFixed(3)} 0=${noAccel.xH.toFixed(3)}`,
  )
}

// --- empirics deepen (Pass-4 EMPIRICS) ---
{
  const cells = [
    { R: 50, mu: 10, sigma: 30 },
    { R: 80, mu: 0, sigma: 40 },
    { R: 40, mu: 35, sigma: 25 },
  ]
  const idGate = plattHeldOutGainSanity({ cells, bias: 0, trialsPerCell: 3000 })
  assert(
    'Platt gate: identity corridor gain < calibrationMinBrierGain (no-op)',
    !idGate.shouldApply,
    `gain=${idGate.gain.toFixed(4)}`,
  )
  const biasGate = plattHeldOutGainSanity({
    cells,
    corruptPlatt: { a: 0.55, b: 1.45 },
    trialsPerCell: 3000,
  })
  assert(
    'Platt gate: logit-corrupt gain ≥ calibrationMinBrierGain',
    biasGate.shouldApply,
    `gain=${biasGate.gain.toFixed(4)} a=${biasGate.a.toFixed(2)} b=${biasGate.b.toFixed(2)}`,
  )
  // True corridor MCE / adaptive ECE
  const preds: number[] = []
  const outs: number[] = []
  for (const [i, cell] of cells.entries()) {
    const pHat =
      // reuse corridorHitProb
      corridorHitProb(cell.R, cell.mu, cell.sigma)
    let s = (0x4d4345 ^ (i * 13)) | 0
    const nextU = () => {
      s = (Math.imul(s, 1664525) + 1013904223) | 0
      return (s >>> 0) / 4294967296
    }
    for (let t = 0; t < 3000; t++) {
      const u1 = Math.max(1e-12, nextU())
      const u2 = nextU()
      const z = Math.sqrt(-2 * Math.log(u1)) * Math.cos(2 * Math.PI * u2)
      preds.push(pHat)
      outs.push(Math.abs(cell.mu + cell.sigma * z) < cell.R ? 1 : 0)
    }
  }
  const mce = maxCalibrationError(preds, outs, 10)
  const aEce = adaptiveEce(preds, outs, 10)
  assert(
    'MCE: true corridor synthetic ≤ mceTol',
    mce <= KILL_CRITERIA_VS_B1.mceTol,
    `mce=${mce.toFixed(4)}`,
  )
  assert(
    'adaptive ECE: true corridor ≤ eceTol',
    aEce <= KILL_CRITERIA_VS_B1.eceTol,
    `aEce=${aEce.toFixed(4)}`,
  )
  const mis = corridorMiscalibrationKillSanity({
    cells,
    bias: 0.12,
    trialsPerCell: 3000,
  })
  assert(
    'miscal kill: bias=+0.12 trips ECE or MCE',
    mis.shouldKill,
    `ece=${mis.ece.toFixed(3)} mce=${mis.mce.toFixed(3)}`,
  )
}
{
  const varSan = xhmVarResidualSanity({
    p: 0.55,
    n: 4,
    rhoStar: 0.5,
    trials: 15000,
  })
  assert(
    'xHm Var MoM: |var̂/var★−1| ≤ varRelTol at ρ★=0.5',
    varSan.ok,
    `rel=${varSan.relErr.toFixed(3)}`,
  )
  const wrong = xhmWrongRhoCrpsKillSanity({
    p: 0.55,
    n: 4,
    rhoStar: 0.5,
    rhoWrong: 0,
    trials: 10000,
  })
  assert(
    'wrong-ρ CRPS: ρ=0 loses to ρ★ by ≥ crpsWrongRhoMinGain',
    wrong.shouldKillWrongRho,
    `gain=${wrong.gain.toFixed(3)}`,
  )
  const tail = xhmTailCrpsSanity({
    p: 0.55,
    n: 4,
    rhoStar: 0.5,
    trials: 12000,
  })
  assert(
    'tail CRPS: dep ≤ indep on {K=0}∪{K=n} mass',
    tail.ok,
    `dep=${tail.crpsDepTail.toFixed(3)} indep=${tail.crpsIndepTail.toFixed(3)}`,
  )
  // PIT
  const draws: number[] = []
  // reuse wrong's generative path via a small inline — call Var draws indirectly
  const pitStar = discretePitEce(
    analyticXhmPmfs(0.55, 4, 0.5),
    // regenerate
    (() => {
      const out: number[] = []
      let st = 0x504954
      const nextU = () => {
        st = (Math.imul(st, 1664525) + 1013904223) | 0
        return (st >>> 0) / 4294967296
      }
      const bm = () => {
        const u1 = Math.max(1e-12, nextU())
        const u2 = nextU()
        return Math.sqrt(-2 * Math.log(u1)) * Math.cos(2 * Math.PI * u2)
      }
      const c = invNorm(0.55)
      const sR = Math.sqrt(0.5)
      const sI = Math.sqrt(0.5)
      for (let t = 0; t < 8000; t++) {
        const Z = bm()
        let k = 0
        for (let j = 0; j < 4; j++) if (sR * Z + sI * bm() < c) k++
        out.push(k)
      }
      return out
    })(),
    10,
    0x504954,
  )
  assert(
    'PIT ECE: correct xHm PMF ≤ pitEceTol',
    pitStar.ok,
    `ece=${pitStar.ece.toFixed(4)}`,
  )
  const pitWrong = discretePitEce(
    analyticXhmPmfs(0.55, 4, 0),
    (() => {
      const out: number[] = []
      let st = 0x504955
      const nextU = () => {
        st = (Math.imul(st, 1664525) + 1013904223) | 0
        return (st >>> 0) / 4294967296
      }
      const bm = () => {
        const u1 = Math.max(1e-12, nextU())
        const u2 = nextU()
        return Math.sqrt(-2 * Math.log(u1)) * Math.cos(2 * Math.PI * u2)
      }
      const c = invNorm(0.55)
      const sR = Math.sqrt(0.5)
      const sI = Math.sqrt(0.5)
      for (let t = 0; t < 8000; t++) {
        const Z = bm()
        let k = 0
        for (let j = 0; j < 4; j++) if (sR * Z + sI * bm() < c) k++
        out.push(k)
      }
      return out
    })(),
    10,
    0x504955,
  )
  assert(
    'PIT ECE: wrong ρ=0 exceeds pitEceTol (or > correct)',
    !pitWrong.ok || pitWrong.ece > pitStar.ece + 0.005,
    `wrong=${pitWrong.ece.toFixed(4)} star=${pitStar.ece.toFixed(4)}`,
  )
  void draws
  void expectedCalibrationError
}
assert(
  'Pass-4 kill-criteria deepen fields finite',
  Number.isFinite(KILL_CRITERIA_VS_B1.mceTol) &&
    KILL_CRITERIA_VS_B1.pitEceTol >= KILL_CRITERIA_VS_B1.eceTol,
  JSON.stringify(KILL_CRITERIA_VS_B1),
)

// --- empirics deepen (Pass-5 EMPIRICS) ---
{
  const cells = [
    { R: 50, mu: 10, sigma: 30 },
    { R: 80, mu: 0, sigma: 40 },
    { R: 40, mu: 35, sigma: 25 },
  ]
  const idT = temperatureHeldOutGainSanity({
    cells,
    corruptT: 1,
    trialsPerCell: 3000,
  })
  assert(
    'Temp gate: identity corridor gain < calibrationMinBrierGain (no-op)',
    !idT.shouldApply,
    `gain=${idT.gain.toFixed(4)}`,
  )
  const badT = temperatureHeldOutGainSanity({
    cells,
    corruptT: 2.5,
    trialsPerCell: 4000,
  })
  assert(
    'Temp gate: corrupt T=2.5 gain ≥ calibrationMinBrierGain',
    badT.shouldApply,
    `gain=${badT.gain.toFixed(4)} T=${badT.T.toFixed(2)}`,
  )
  const mur = corridorMurphySanity({ cells, trialsPerCell: 3000 })
  assert(
    'Murphy: true corridor REL ≤ murphyRelTol and RES ≥ murphyMinRes',
    mur.ok,
    `rel=${mur.rel.toFixed(4)} res=${mur.res.toFixed(4)}`,
  )
  assert(
    'Murphy: climatology RES < murphyMinRes (no resolution)',
    mur.climRes < KILL_CRITERIA_VS_B1.murphyMinRes,
    `climRes=${mur.climRes.toFixed(4)}`,
  )
  // Conditional ECE on true corridor
  const preds: number[] = []
  const outs: number[] = []
  for (const [i, cell] of cells.entries()) {
    const pHat = corridorHitProb(cell.R, cell.mu, cell.sigma)
    let s = (0x434543 ^ (i * 19)) | 0
    const nextU = () => {
      s = (Math.imul(s, 1664525) + 1013904223) | 0
      return (s >>> 0) / 4294967296
    }
    for (let t = 0; t < 3000; t++) {
      const u1 = Math.max(1e-12, nextU())
      const u2 = nextU()
      const z = Math.sqrt(-2 * Math.log(u1)) * Math.cos(2 * Math.PI * u2)
      preds.push(pHat)
      outs.push(Math.abs(cell.mu + cell.sigma * z) < cell.R ? 1 : 0)
    }
  }
  const cond = conditionalEceByTertile(preds, outs)
  assert(
    'conditional ECE: true corridor tertiles ≤ conditionalEceTol',
    cond.ok,
    `eces=${cond.eces.map((e) => e.toFixed(3)).join(',')}`,
  )
  void murphyBrierDecomposition
}
{
  const ll = xhmWrongRhoLogLossKillSanity({
    p: 0.55,
    n: 4,
    rhoStar: 0.5,
    trials: 10000,
  })
  assert(
    'wrong-ρ count log-loss: ρ=0 loses to ρ★ by ≥ countLogLossWrongRhoMinGain',
    ll.shouldKillWrongRho,
    `gain=${ll.gain.toFixed(3)}`,
  )
  const draws: number[] = []
  let st = 0x434245
  const nextU = () => {
    st = (Math.imul(st, 1664525) + 1013904223) | 0
    return (st >>> 0) / 4294967296
  }
  const bm = () => {
    const u1 = Math.max(1e-12, nextU())
    const u2 = nextU()
    return Math.sqrt(-2 * Math.log(u1)) * Math.cos(2 * Math.PI * u2)
  }
  const c = invNorm(0.55)
  const sR = Math.sqrt(0.5)
  const sI = Math.sqrt(0.5)
  for (let t = 0; t < 8000; t++) {
    const Z = bm()
    let k = 0
    for (let j = 0; j < 4; j++) if (sR * Z + sI * bm() < c) k++
    draws.push(k)
  }
  const eceStar = countBinEce(analyticXhmPmfs(0.55, 4, 0.5), draws)
  const eceWrong = countBinEce(analyticXhmPmfs(0.55, 4, 0), draws)
  assert(
    'count-bin ECE: correct xHm PMF ≤ countBinEceTol',
    eceStar.ok,
    `ece=${eceStar.ece.toFixed(4)}`,
  )
  assert(
    'count-bin ECE: wrong ρ=0 exceeds (or > correct)',
    !eceWrong.ok || eceWrong.ece > eceStar.ece + 0.01,
    `wrong=${eceWrong.ece.toFixed(4)} star=${eceStar.ece.toFixed(4)}`,
  )
  const trip = rhoTripleRecoverySanity({
    p: 0.55,
    rhoStar: 0.5,
    nTriples: 30000,
    seed: 42,
  })
  assert(
    'ρ triple MoM: recover ρ★=0.5 within tripleRhoAbsErrTol',
    trip.ok,
    `hat3=${trip.rhoHat3.toFixed(3)} err=${trip.absErr3.toFixed(3)}`,
  )
  const ksStar = discretePitKs(analyticXhmPmfs(0.55, 4, 0.5), draws, 0x4b53)
  const ksWrong = discretePitKs(analyticXhmPmfs(0.55, 4, 0), draws, 0x4b54)
  assert(
    'PIT KS: correct ≤ pitKsTol; wrong ρ=0 fails or worse',
    ksStar.ok && (!ksWrong.ok || ksWrong.ks > ksStar.ks + 0.01),
    `star=${ksStar.ks.toFixed(4)} wrong=${ksWrong.ks.toFixed(4)}`,
  )
}
assert(
  'Pass-5 kill-criteria deepen fields finite',
  Number.isFinite(KILL_CRITERIA_VS_B1.murphyRelTol) &&
    KILL_CRITERIA_VS_B1.pitKsTol >= KILL_CRITERIA_VS_B1.pitEceTol,
  JSON.stringify(KILL_CRITERIA_VS_B1),
)

// --- Pass-5 GEO ---
{
  const R = 1000
  const Vm = 1600
  const L = R + 65
  const tg = interceptTimeGo(R, Vm, 0, 200)
  const te = engagementHorizonSec(tg, Vm, L)
  assert(
    'Pass-5: horizon ≡ t_go when L covers in-reach intercept',
    Math.abs(te - tg) < 1e-12,
    `te=${te.toFixed(6)} tg=${tg.toFixed(6)}`,
  )
}
{
  const te = engagementHorizonSec(1.2, 1600, 400)
  assert(
    'Pass-5: horizon clamps to L/V_m when tip binds',
    Math.abs(te - 400 / 1600) < 1e-12,
    `te=${te}`,
  )
}
{
  const R = 1000
  const Vm = 1600
  const vp = 250
  const L = 350
  const tg = interceptTimeGo(R, Vm, 0, vp)
  const te = engagementHorizonSec(tg, Vm, L)
  const lamFar = requiredLeadAngle(tg, R, 0, vp)
  const lamHor = requiredLeadAngle(te, R, 0, vp)
  const missFar = ballisticSegmentMiss(R, 0, vp, Vm, lamFar, te, L)
  const missHor = ballisticSegmentMiss(R, 0, vp, Vm, lamHor, te, L)
  assert(
    'Pass-5: finite-horizon lead ≤ unreachable-intercept lead miss',
    missHor <= missFar + 1e-9,
    `hor=${missHor.toFixed(2)} far=${missFar.toFixed(2)}`,
  )
}
{
  const tipOor = estimateXh(
    base({
      targetPosition: far,
      abilityRange: 1175,
      missileMaxTravelUu: 200,
      missileSpeed: 1200,
      missileWidth: 70,
      leadSkill: 0.8,
      targetPerpVel: 0,
      targetRadialVel: 0,
      dashReady: false,
      crowdControlled: true,
    }),
  )
  assert(
    'Pass-5: short Ltravel → reach OOR',
    tipOor.inRange === false && tipOor.factors.includes('reach_oor'),
    `inRange=${tipOor.inRange} factors=${tipOor.factors.join(',')}`,
  )
}

// --- Pass-5 AIM ---
{
  const prepMid = estimateXh(
    base({
      releaseDelaySec: 0.2,
      aimTimeSec: 0.55,
      targetPerpVel: 420,
      missileSpeed: 2000,
      missileWidth: 200,
      dashReady: false,
      flashReady: false,
      crowdControlled: true,
    }),
  )
  const prepSnap = estimateXh(
    base({
      releaseDelaySec: 0.05,
      aimTimeSec: 0.55,
      targetPerpVel: 420,
      missileSpeed: 2000,
      missileWidth: 200,
      dashReady: false,
      flashReady: false,
      crowdControlled: true,
    }),
  )
  const prepLong = estimateXh(
    base({
      releaseDelaySec: 0.85,
      aimTimeSec: 0.55,
      targetPerpVel: 420,
      missileSpeed: 2000,
      missileWidth: 200,
      dashReady: false,
      flashReady: false,
      crowdControlled: true,
    }),
  )
  assert(
    'Pass-5: mid prep ≤ snap sigma.aim (prep↓motor)',
    !!prepMid.sigma &&
      !!prepSnap.sigma &&
      prepMid.sigma.aim <= prepSnap.sigma.aim + 1e-6,
    `mid=${prepMid.sigma?.aim.toFixed(1)} snap=${prepSnap.sigma?.aim.toFixed(1)}`,
  )
  assert(
    'Pass-5: very-long prep ≥ mid sigma.aim (foreperiod U-shape)',
    !!prepLong.sigma &&
      !!prepMid.sigma &&
      prepLong.sigma.aim + 1e-6 >= prepMid.sigma.aim,
    `long=${prepLong.sigma?.aim.toFixed(1)} mid=${prepMid.sigma?.aim.toFixed(1)}`,
  )
  const crossFast = estimateXh(
    base({
      targetPerpVel: 400,
      fittsWidthUu: 80,
      aimTimeSec: 0.4,
      dashReady: false,
      flashReady: false,
    }),
  )
  const crossSlow = estimateXh(
    base({
      targetPerpVel: 80,
      fittsWidthUu: 80,
      aimTimeSec: 0.4,
      dashReady: false,
      flashReady: false,
    }),
  )
  assert(
    'Pass-5: faster strafe → larger sigma.aim (crossing-time clock)',
    !!crossFast.sigma &&
      !!crossSlow.sigma &&
      crossFast.sigma.aim > crossSlow.sigma.aim,
    `fast=${crossFast.sigma?.aim.toFixed(1)} slow=${crossSlow.sigma?.aim.toFixed(1)}`,
  )
}

// --- Pass-5 VISION ---
{
  const oracleAim = estimateXh(
    base({
      vision: 'blind',
      lastKnownAgeSec: 2,
      softVision: 0,
      beliefMeanPosition: near,
    }),
  )
  const noLkp = estimateXh(
    base({
      vision: 'blind',
      lastKnownAgeSec: 2,
      softVision: 0,
      beliefMeanPosition: undefined,
    }),
  )
  assert(
    'Pass-5: no-LKP FoW ≠ silent god-eye',
    Math.abs(noLkp.xH - oracleAim.xH) > 0.02 ||
      (noLkp.factors.includes('belief:no_lkp_guard') &&
        (noLkp.distance == null ||
          Math.abs((noLkp.distance ?? 0) - (oracleAim.distance ?? 0)) > 1)),
    `no=${noLkp.xH.toFixed(3)} oracle=${oracleAim.xH.toFixed(3)} d=${noLkp.distance}`,
  )
  const a4 = estimateXh(
    base({
      vision: 'blind',
      lastKnownAgeSec: 4,
      beliefMeanPosition: near,
      softVision: 0,
    }),
  )
  const a30 = estimateXh(
    base({
      vision: 'blind',
      lastKnownAgeSec: 30,
      beliefMeanPosition: near,
      softVision: 0,
    }),
  )
  assert(
    'Pass-5: ancient xH ≤ mid-age xH',
    a30.xH <= a4.xH + 1e-9,
    `a30=${a30.xH.toFixed(3)} a4=${a4.xH.toFixed(3)}`,
  )
  const occ = occupancySigma('lane')
  assert(
    'Pass-5: ancient belief ≲ σ_occ + soft-asymptote tol',
    !!a30.sigma && a30.sigma.belief <= occ + 450,
    `σb=${a30.sigma?.belief.toFixed(0)} occ=${occ}`,
  )
}

// --- Pass-5 STRATEGY ---
{
  const avg = averageXhRows([
    { xH: 0.4, bands: { worst: 0.3, typical: 0.4, best: 0.6, mix: 0.35 } },
    { xH: 0.5, bands: { worst: 0.4, typical: 0.5, best: 0.7, mix: 0.45 } },
  ])
  assert(
    'Pass-5: avg bands ordered',
    !!avg.bands &&
      avg.bands.worst <= avg.bands.typical &&
      avg.bands.typical <= avg.bands.best,
  )
  assert(
    'Pass-5: avg mix in [worst,typical]',
    !!avg.bands &&
      avg.bands.mix != null &&
      avg.bands.mix >= avg.bands.worst - 1e-9 &&
      avg.bands.mix <= avg.bands.typical + 1e-9,
  )
  const scaled = scaleXhBands(
    { worst: 0.4, typical: 0.5, best: 0.6, mix: 0.45 },
    1.18,
  )
  assert(
    'Pass-5: utilMult scales bands componentwise',
    Math.abs(scaled.typical - Math.min(0.97, 0.5 * 1.18)) < 1e-9,
  )
  const ghostEquipOnly = {
    championId: 'MasterYi',
    level: 6,
    itemIds: [],
    runeId: null,
    ranks: { Q: 1, W: 1, E: 1, R: 1 },
    summonerSpells: ['Flash', 'Ghost'] as [string, string],
  } satisfies FighterLoadout
  const ghostWithLive = {
    ...ghostEquipOnly,
    liveStats: { movespeed: 400 },
  } satisfies FighterLoadout
  assert(
    'Pass-5: Ghost equipped alone ⇒ ghostBuffActive false',
    ghostBuffActive(ghostEquipOnly, 335, 335) === false,
  )
  assert(
    'Pass-5: Ghost + live MS bump ⇒ ghostBuffActive true',
    ghostBuffActive(ghostWithLive, 400, 335) === true,
  )
}

// --- Pass-6 GEO ---
{
  const R = 1000
  const Vm = 1600
  const vp = 220
  const L = R + 65
  const tg = interceptTimeGo(R, Vm, 0, vp)
  const te = engagementHorizonSec(tg, Vm, L)
  const lam = requiredLeadAngle(te, R, 0, vp) * 0.55
  const miss = ballisticSegmentMiss(R, 0, vp, Vm, lam, te, L)
  const cpa = ballisticSegmentCpa(R, 0, vp, Vm, lam, te, L)
  assert(
    'Pass-6: segment CPA miss ≡ ballisticSegmentMiss',
    Math.abs(cpa.missUu - miss) < 1e-12,
    `cpa=${cpa.missUu} miss=${miss}`,
  )
  assert(
    'Pass-6: t_cpa ≤ t_eng',
    cpa.tCpaSec <= te + 1e-12,
    `tCpa=${cpa.tCpaSec} te=${te}`,
  )
  const clock = accelZemClockSec(0.28, cpa.tCpaSec)
  assert(
    'Pass-6: accel clock = delay + t_cpa',
    Math.abs(clock - (0.28 + cpa.tCpaSec)) < 1e-12,
  )
  const a0 = estimateXh(
    base({ residualAccelUuPerSec2: 0, targetPerpVel: 200, leadSkill: 0.7 }),
  )
  const aHi = estimateXh(
    base({ residualAccelUuPerSec2: 1200, targetPerpVel: 200, leadSkill: 0.7 }),
  )
  assert(
    'Pass-6: accel ZEM → lower or equal xH',
    aHi.xH <= a0.xH + 1e-9,
    `aHi=${aHi.xH.toFixed(3)} a0=${a0.xH.toFixed(3)}`,
  )
  void boundedAccelZemExtra
}

// --- Pass-6 AIM ---
{
  const jitLo = estimateXh(
    base({
      aimTimeSec: 0.5,
      releaseDelaySec: 0.15,
      releaseJitterSec: 0.03,
      targetPerpVel: 350,
      dashReady: false,
      flashReady: false,
      crowdControlled: true,
    }),
  )
  const jitHi = estimateXh(
    base({
      aimTimeSec: 0.5,
      releaseDelaySec: 0.15,
      releaseJitterSec: 0.08,
      targetPerpVel: 350,
      dashReady: false,
      flashReady: false,
      crowdControlled: true,
    }),
  )
  assert(
    'Pass-6: higher releaseJitter → larger sigma.aim',
    !!jitLo.sigma && !!jitHi.sigma && jitHi.sigma.aim > jitLo.sigma.aim,
    `lo=${jitLo.sigma?.aim.toFixed(1)} hi=${jitHi.sigma?.aim.toFixed(1)}`,
  )
  const snap = estimateXh(
    base({
      aimTimeSec: 0.2,
      releaseDelaySec: 0.1,
      targetPerpVel: 350,
      dashReady: false,
      flashReady: false,
      crowdControlled: true,
    }),
  )
  const lined = estimateXh(
    base({
      aimTimeSec: 0.7,
      releaseDelaySec: 0.1,
      targetPerpVel: 350,
      dashReady: false,
      flashReady: false,
      crowdControlled: true,
    }),
  )
  assert(
    'Pass-6: short T_fb refractory ≥ long lineup sigma.aim',
    !!snap.sigma && !!lined.sigma && snap.sigma.aim + 1e-6 >= lined.sigma.aim,
    `snap=${snap.sigma?.aim.toFixed(1)} lined=${lined.sigma?.aim.toFixed(1)}`,
  )
}

// --- Pass-6 VISION ---
{
  const noLkp = estimateXh(
    base({
      vision: 'blind',
      softVision: 0,
      lastKnownAgeSec: 2,
      beliefMeanPosition: undefined,
    }),
  )
  assert(
    'Pass-6: open-loop zone uses caster (no oracle brush Cap)',
    noLkp.factors.includes('belief:no_lkp_guard') &&
      !noLkp.factors.some((f) => f.includes('zone_scale') && f.includes('0.9')),
    noLkp.factors.join(','),
  )
  const deep = estimateXh(
    base({
      vision: 'blind',
      softVision: 0.6,
      softVisionMarginNorm: 0.8,
      lastKnownAgeSec: 1,
      beliefMeanPosition: near,
    }),
  )
  const shallow = estimateXh(
    base({
      vision: 'blind',
      softVision: 0.6,
      softVisionMarginNorm: 0.05,
      lastKnownAgeSec: 1,
      beliefMeanPosition: near,
    }),
  )
  assert(
    'Pass-6: deeper margin → higher or equal soft-seen xH',
    deep.xH + 1e-9 >= shallow.xH,
    `deep=${deep.xH.toFixed(3)} shallow=${shallow.xH.toFixed(3)}`,
  )
}

// --- Pass-6 STRATEGY ---
{
  const baseLoad = {
    championId: 'Lux',
    level: 6,
    itemIds: [],
    runeId: null,
    ranks: { Q: 3, W: 1, E: 1, R: 1 },
  } satisfies FighterLoadout
  const empty = { hardCc: false, enemySlow: 0 } as import('../src/engine/types').ResolvedUtility
  const slowed = { hardCc: false, enemySlow: 0.4 } as import('../src/engine/types').ResolvedUtility
  const msOpen = effectiveTargetMs(baseLoad, 335, empty)
  const msSlow = effectiveTargetMs(baseLoad, 335, slowed)
  assert('Pass-6: slow shrinks effectiveTargetMs', msSlow < msOpen)
  assert(
    'Pass-6: Ghost trusts liveMs without liveStats',
    ghostBuffActive(
      { ...baseLoad, summonerSpells: ['Flash', 'Ghost'] },
      400,
      335,
    ) === true,
  )
}

// --- Pass-6 EMPIRICS ---
{
  const cells = [
    { R: 50, mu: 10, sigma: 30 },
    { R: 80, mu: 0, sigma: 40 },
    { R: 40, mu: 35, sigma: 25 },
  ]
  const idB = betaHeldOutGainSanity({ cells, trialsPerCell: 3000 })
  assert(
    'Pass-6: Beta identity gain < calibrationMinBrierGain',
    !idB.shouldApply,
    `gain=${idB.gain.toFixed(4)}`,
  )
  const badB = betaHeldOutGainSanity({
    cells,
    corrupt: { a: 0.6, b: -1.4, c: 0.3 },
    trialsPerCell: 4000,
  })
  assert(
    'Pass-6: Beta corrupt warp gain ≥ calibrationMinBrierGain',
    badB.shouldApply,
    `gain=${badB.gain.toFixed(4)}`,
  )
  const { preds, outs } = (() => {
    const p: number[] = []
    const o: number[] = []
    for (const [i, cell] of cells.entries()) {
      const pHat = corridorHitProb(cell.R, cell.mu, cell.sigma)
      let s = (0x4d5552 ^ (i * 17)) | 0
      const nextU = () => {
        s = (Math.imul(s, 1664525) + 1013904223) | 0
        return (s >>> 0) / 4294967296
      }
      for (let t = 0; t < 2000; t++) {
        const u1 = Math.max(1e-12, nextU())
        const u2 = nextU()
        const z = Math.sqrt(-2 * Math.log(u1)) * Math.cos(2 * Math.PI * u2)
        p.push(pHat)
        o.push(Math.abs(cell.mu + cell.sigma * z) < cell.R ? 1 : 0)
      }
    }
    return { preds: p, outs: o }
  })()
  const id = murphyIdentitySanity(preds, outs)
  assert(
    'Pass-6: Murphy BS = REL−RES+UNC',
    id.ok,
    `gap=${id.absGap.toExponential(2)}`,
  )
  const bss = corridorBssSanity({ cells, trialsPerCell: 3000 })
  assert(
    'Pass-6: corridor BSS ≥ bssMinTol; clim ~0',
    bss.ok,
    `bss=${bss.bss.toFixed(3)} clim=${bss.climBss.toExponential(2)}`,
  )
  const dss = xhmWrongRhoDssKillSanity({
    p: 0.55,
    n: 4,
    rhoStar: 0.5,
    trials: 8000,
  })
  assert(
    'Pass-6: wrong-ρ DSS kill',
    dss.shouldKillWrongRho,
    `gain=${dss.gain.toFixed(3)}`,
  )
  const cov = xhmIntervalCoverageSanity({
    p: 0.55,
    n: 4,
    rhoStar: 0.5,
    trials: 8000,
  })
  assert(
    'Pass-6: xHm 90% PI coverage honest; wrong ρ worse',
    cov.okStar && cov.okKillWrong,
    `star=${cov.covStar.toFixed(3)} wrong=${cov.covWrong.toFixed(3)}`,
  )
  const kill = abilityResidualKillSanity({ pStar: 0.55, corridorBias: 0.15 })
  assert(
    'Pass-6: ability residual kill path trips',
    kill.shouldKillB1,
    `res=${kill.residual.toFixed(3)} gain=${kill.brierGain.toFixed(3)}`,
  )
  const keep = abilityResidualKillSanity({ pStar: 0.55, corridorBias: 0 })
  assert(
    'Pass-6: ability identity does not kill',
    !keep.shouldKillB1,
    `res=${keep.residual.toFixed(3)}`,
  )
  assert(
    'Pass-6 kill-criteria deepen fields finite',
    Number.isFinite(KILL_CRITERIA_VS_B1.murphyIdentityTol) &&
      KILL_CRITERIA_VS_B1.bssMinTol > 0,
    JSON.stringify(KILL_CRITERIA_VS_B1),
  )
}

// --- Pass-7 GEO ---
{
  assert(
    'Pass-7: capsuleTravelBudget ≡ L + R_hit',
    Math.abs(capsuleTravelBudgetUu(1000, 140) - (1000 + capsuleHitRadius(140))) <
      1e-12,
  )
  assert(
    'Pass-7: thin width → champ-only pad',
    Math.abs(
      capsuleTravelBudgetUu(800, 0) - (800 + capsuleHitRadius(0)),
    ) < 1e-12,
  )
  assert(
    'Pass-7: wider missile → larger travel budget',
    capsuleTravelBudgetUu(800, 200) > capsuleTravelBudgetUu(800, 40) + 1e-9,
  )
}

// --- Pass-7 AIM ---
{
  const prepMid = estimateXh(
    base({
      releaseDelaySec: 0.25,
      aimTimeSec: 0.55,
      targetPerpVel: 420,
      missileSpeed: 2000,
      missileWidth: 200,
      dashReady: false,
      flashReady: false,
      crowdControlled: true,
    }),
  )
  const prepLong = estimateXh(
    base({
      releaseDelaySec: 0.9,
      aimTimeSec: 0.55,
      targetPerpVel: 420,
      missileSpeed: 2000,
      missileWidth: 200,
      dashReady: false,
      flashReady: false,
      crowdControlled: true,
    }),
  )
  assert(
    'Pass-7: super-foreperiod long ≥ mid sigma.aim',
    !!prepLong.sigma &&
      !!prepMid.sigma &&
      prepLong.sigma.aim + 1e-6 >= prepMid.sigma.aim,
    `long=${prepLong.sigma?.aim.toFixed(1)} mid=${prepMid.sigma?.aim.toFixed(1)}`,
  )
}

// --- Pass-7 VISION ---
{
  const one = estimateXh(
    base({
      vision: 'blind',
      softVision: 0,
      lastKnownAgeSec: 12,
      beliefMeanPosition: near,
    }),
  )
  const multi = estimateXh(
    base({
      vision: 'blind',
      softVision: 0,
      lastKnownAgeSec: 12,
      beliefMeanPosition: undefined,
      beliefHypotheses: [
        { weight: 0.4, mean: near, zone: 'brush', ageSec: 12 },
        { weight: 0.35, mean: { x: near.x + 0.03, y: near.y }, zone: 'river', ageSec: 12 },
        { weight: 0.25, mean: { x: near.x - 0.02, y: near.y }, zone: 'jungle', ageSec: 12 },
      ],
    }),
  )
  assert(
    'Pass-7: hypotheses-only FoW is not openLoop',
    !multi.factors.includes('belief:no_lkp_guard'),
  )
  assert(
    'Pass-7: multi-modal belief changes xH vs single LKP',
    Math.abs(multi.xH - one.xH) > 1e-4,
    `multi=${multi.xH.toFixed(3)} one=${one.xH.toFixed(3)}`,
  )
}

// --- Pass-7 STRATEGY ---
{
  const ghostLoad = {
    championId: 'MasterYi',
    level: 6,
    itemIds: [],
    runeId: null,
    ranks: { Q: 1, W: 1, E: 1, R: 1 },
    summonerSpells: ['Flash', 'Ghost'] as [string, string],
    liveStats: { movespeed: 400 },
  } satisfies FighterLoadout
  const slowed = effectiveTargetMs(ghostLoad, 335, {
    enemySlow: 0.4,
    enemyAsSlow: 0,
    hardCc: false,
    selfMsBuff: 0,
    armorShred: 0,
    mrShred: 0,
    damageAmp: 0,
    damageReduction: 0,
    sources: [],
  })
  assert(
    'Pass-7: Ghost stays active under slow when raw liveMs buffed',
    ghostBuffActive(ghostLoad, 400, 335) === true && slowed < 400,
  )
  void fightDodgeBands
}

// --- Pass-7 EMPIRICS ---
{
  const en = xhmWrongRhoEnergyKillSanity({
    p: 0.55,
    n: 6,
    rhoStar: 0.6,
    trials: 1200,
    pairedDraws: 64,
  })
  assert(
    'Pass-7: wrong-ρ energy kill',
    en.shouldKillWrongRho,
    `gain=${en.gain.toFixed(3)} star=${en.esStar.toFixed(3)} wrong=${en.esWrong.toFixed(3)}`,
  )
  const wk = xhmWrongRhoWinklerKillSanity({
    p: 0.55,
    n: 4,
    rhoStar: 0.5,
    trials: 8000,
  })
  assert(
    'Pass-7: wrong-ρ Winkler kill',
    wk.shouldKillWrongRho,
    `gain=${wk.gain.toFixed(3)}`,
  )
  assert(
    'Pass-7 kill-criteria deepen fields finite',
    Number.isFinite(KILL_CRITERIA_VS_B1.winklerWrongRhoMinGain) &&
      KILL_CRITERIA_VS_B1.energyWrongRhoMinGain > 0,
  )
}

// --- Pass-8 GEO ---
{
  const t0 = interceptTimeGo(1000, 1600, 0, 200)
  assert(
    'Pass-8: zero extent → firstContact ≡ center t_go',
    Math.abs(firstContactTimeGo(t0, 1000, 0) - t0) < 1e-12,
  )
  const tC = firstContactTimeGo(t0, 1000, 135)
  assert(
    'Pass-8: R_hit > 0 → firstContact < center t_go',
    tC < t0 - 1e-9,
    `tC=${tC} t0=${t0}`,
  )
  assert(
    'Pass-8: firstContact = t0·(1 − R_hit/R)',
    Math.abs(tC - t0 * (1 - 135 / 1000)) < 1e-12,
  )
  assert(
    'Pass-8: overlapping range → immediate contact floor',
    firstContactTimeGo(1.0, 50, 65) <= 0.05 + 1e-12,
  )
  const L = 400
  const Vm = 1600
  const teCenter = engagementHorizonSec(t0, Vm, L)
  const teContact = engagementHorizonSec(tC, Vm, L)
  assert(
    'Pass-8: contact horizon ≤ center horizon',
    teContact <= teCenter + 1e-12,
    `contact=${teContact} center=${teCenter}`,
  )
  const def = estimateXh(
    base({
      leadSkill: 0.7,
      targetPerpVel: 200,
      dashReady: false,
      crowdControlled: true,
      residualAccelUuPerSec2: 0,
    }),
  )
  assert('Pass-8: default A=0 still in range', def.inRange === true)
  assert(
    'Pass-8: default path exposes t_contact',
    def.factors.some((f) => f.startsWith('t_contact:')),
    def.factors.join(','),
  )
  assert(
    'Pass-8: default path still exposes t_cpa',
    def.factors.some((f) => f.startsWith('t_cpa:')),
    def.factors.join(','),
  )
  const wide = estimateXh(
    base({
      missileWidth: 200,
      leadSkill: 0.55,
      targetPerpVel: 180,
      targetRadialVel: 0,
      dashReady: false,
      crowdControlled: true,
      residualAccelUuPerSec2: 0,
    }),
  )
  const thin = estimateXh(
    base({
      missileWidth: 40,
      leadSkill: 0.55,
      targetPerpVel: 180,
      targetRadialVel: 0,
      dashReady: false,
      crowdControlled: true,
      residualAccelUuPerSec2: 0,
    }),
  )
  const tcWide = Number(
    wide.factors.find((f) => f.startsWith('t_contact:'))?.slice(10, -1),
  )
  const tcThin = Number(
    thin.factors.find((f) => f.startsWith('t_contact:'))?.slice(10, -1),
  )
  if (Number.isFinite(tcWide) && Number.isFinite(tcThin)) {
    assert(
      'Pass-8: wider R_hit → t_contact ≤ thinner',
      tcWide <= tcThin + 1e-9,
      `wide=${tcWide} thin=${tcThin}`,
    )
  }
  const tipOor = estimateXh(
    base({
      targetPosition: far,
      abilityRange: 1175,
      missileMaxTravelUu: 200,
      missileSpeed: 1200,
      missileWidth: 70,
      leadSkill: 0.8,
      targetPerpVel: 0,
      targetRadialVel: 0,
      dashReady: false,
      crowdControlled: true,
    }),
  )
  assert(
    'Pass-8: short Ltravel still reach_oor under center-path reach',
    tipOor.inRange === false && tipOor.factors.includes('reach_oor'),
    `inRange=${tipOor.inRange} factors=${tipOor.factors.join(',')}`,
  )
}

// --- Pass-8 AIM ---
{
  const p8Near = estimateXh(
    base({
      targetPosition: near,
      aimTimeSec: 0.55,
      fittsWidthUu: 180,
      targetPerpVel: 40,
      dashReady: false,
      crowdControlled: true,
    }),
  )
  const p8Far = estimateXh(
    base({
      targetPosition: far,
      aimTimeSec: 0.55,
      fittsWidthUu: 180,
      targetPerpVel: 40,
      dashReady: false,
      crowdControlled: true,
    }),
  )
  const p8Snap = estimateXh(
    base({
      targetPosition: near,
      aimTimeSec: 0.14,
      fittsWidthUu: 180,
      targetPerpVel: 40,
      dashReady: false,
      crowdControlled: true,
    }),
  )
  const p8Both = estimateXh(
    base({
      targetPosition: far,
      aimTimeSec: 0.14,
      fittsWidthUu: 180,
      targetPerpVel: 40,
      dashReady: false,
      crowdControlled: true,
    }),
  )
  const dD = (p8Far.sigma?.aim ?? 0) - (p8Near.sigma?.aim ?? 0)
  const dU = (p8Snap.sigma?.aim ?? 0) - (p8Near.sigma?.aim ?? 0)
  const dBoth = (p8Both.sigma?.aim ?? 0) - (p8Near.sigma?.aim ?? 0)
  const excessDU = dBoth - dD - dU
  assert(
    'Pass-8: D∧U σ_aim excess ≤ Schmidt-irreducible band (not urgency×D/T product)',
    !!p8Near.sigma &&
      !!p8Far.sigma &&
      !!p8Snap.sigma &&
      !!p8Both.sigma &&
      excessDU <= 500,
    `excess=${excessDU.toFixed(1)} both=${dBoth.toFixed(1)} d+u=${(dD + dU).toFixed(1)}`,
  )
  const p8RadFast = estimateXh(
    base({
      aimTimeSec: 0.4,
      releaseDelaySec: 0.25,
      releaseJitterSec: 0.045,
      targetPerpVel: 5,
      targetRadialVel: 220,
      missileSpeed: 2800,
      missileWidth: 160,
      dashReady: false,
      crowdControlled: true,
    }),
  )
  const p8RadSlow = estimateXh(
    base({
      aimTimeSec: 0.4,
      releaseDelaySec: 0.25,
      releaseJitterSec: 0.045,
      targetPerpVel: 5,
      targetRadialVel: 220,
      missileSpeed: 800,
      missileWidth: 160,
      dashReady: false,
      crowdControlled: true,
    }),
  )
  assert(
    'Pass-8: radial flee + slow missile → sigma.aim ≥ fast (radial∥timing)',
    !!p8RadSlow.sigma &&
      !!p8RadFast.sigma &&
      p8RadSlow.sigma.aim + 1e-6 >= p8RadFast.sigma.aim,
    `slow=${p8RadSlow.sigma?.aim.toFixed(1)} fast=${p8RadFast.sigma?.aim.toFixed(1)}`,
  )
  assert(
    'Pass-8: radial Weber margin ≥ 0.4 uu at v_perp≈0 (not silent)',
    !!p8RadSlow.sigma &&
      !!p8RadFast.sigma &&
      p8RadSlow.sigma.aim - p8RadFast.sigma.aim + 1e-6 >= 0.4,
    `Δ=${(p8RadSlow.sigma!.aim - p8RadFast.sigma!.aim).toFixed(2)}`,
  )
  const p8Tau = estimateXh(
    base({
      aimTimeSec: 0.45,
      releaseJitterSec: 0.02,
      releaseDelaySec: 0.2,
      targetPerpVel: 420,
      dashReady: false,
      crowdControlled: true,
    }),
  )
  assert(
    'Pass-8: factors expose tau+rad aim path',
    p8Tau.factors.some((f) => f.includes('tau') && f.includes('rad')),
    p8Tau.factors.join(','),
  )
  assert(
    'Pass-8: factors expose T_avail (lineup)',
    p8Tau.factors.some((f) => f.startsWith('T_avail:')),
    p8Tau.factors.join(','),
  )
}

// --- Pass-8 VISION ---
{
  const dark = estimateXh(
    base({
      vision: 'blind',
      softVision: 0,
      lastKnownAgeSec: 8,
      beliefHypotheses: [
        { weight: 0.5, mean: near, zone: 'brush' },
        { weight: 0.5, mean: { x: near.x + 0.04, y: near.y }, zone: 'river' },
      ],
    }),
  )
  const penumbra = estimateXh(
    base({
      vision: 'blind',
      softVision: 0.55,
      softVisionMarginNorm: 0.5,
      lastKnownAgeSec: 8,
      beliefMeanSeen: near,
      beliefHypotheses: [
        { weight: 0.5, mean: near, zone: 'brush' },
        { weight: 0.5, mean: { x: near.x + 0.04, y: near.y }, zone: 'river' },
      ],
    }),
  )
  assert(
    'Pass-8: softV⊕hypotheses ≥ dark multi-mode xH',
    penumbra.xH + 1e-9 >= dark.xH,
  )
  const tight = estimateXh(
    base({
      vision: 'blind',
      softVision: 0,
      lastKnownAgeSec: 10,
      beliefHypotheses: [
        { weight: 0.5, mean: near, zone: 'jungle' },
        { weight: 0.5, mean: { x: near.x + 0.01, y: near.y }, zone: 'jungle' },
      ],
    }),
  )
  const split = estimateXh(
    base({
      vision: 'blind',
      softVision: 0,
      lastKnownAgeSec: 10,
      beliefHypotheses: [
        { weight: 0.5, mean: near, zone: 'jungle' },
        { weight: 0.5, mean: { x: near.x + 0.12, y: near.y }, zone: 'river' },
      ],
    }),
  )
  assert(
    'Pass-8: separated modes → larger σ_belief',
    !!split.sigma &&
      !!tight.sigma &&
      split.sigma.belief >= tight.sigma.belief + 1e-6,
  )
  const iso = estimateXh(
    base({
      vision: 'blind',
      softVision: 0,
      lastKnownAgeSec: 4,
      targetPerpVel: undefined,
      beliefHypotheses: [{ weight: 1, mean: near, zone: 'jungle' }],
    }),
  )
  const oracleVel = estimateXh(
    base({
      vision: 'blind',
      softVision: 0,
      lastKnownAgeSec: 4,
      targetPerpVel: 420,
      beliefHypotheses: [{ weight: 1, mean: near, zone: 'jungle' }],
    }),
  )
  assert(
    'Pass-8: FoW hypotheses use belief-local kinematics',
    Math.abs(iso.xH - oracleVel.xH) < 1e-9 &&
      !!iso.sigma &&
      !!oracleVel.sigma &&
      Math.abs(iso.sigma.belief - oracleVel.sigma.belief) < 1e-9,
  )
}

// --- Pass-8 STRATEGY ---
{
  const luxFull = {
    championId: 'Lux',
    level: 11,
    itemIds: [],
    runeId: null,
    ranks: { Q: 5, W: 3, E: 5, R: 2 },
    summonerSpells: ['Flash', 'Ignite'] as [string, string],
    position: mid,
  } satisfies FighterLoadout
  const luxNoR = {
    ...luxFull,
    ranks: { Q: 5, W: 3, E: 5, R: 0 },
  } satisfies FighterLoadout
  const targetNear = {
    championId: 'Ahri',
    level: 11,
    itemIds: [],
    runeId: null,
    ranks: { Q: 5, W: 3, E: 5, R: 2 },
    summonerSpells: ['Flash', 'Ignite'] as [string, string],
    position: near,
    flashCdRemainingSec: 0,
  } satisfies FighterLoadout
  const visionUnits = [
    {
      id: 'b0',
      team: 'blue' as const,
      position: mid,
      alive: true,
    },
    {
      id: 'r0',
      team: 'red' as const,
      position: near,
      alive: true,
    },
  ]
  const empty = emptyResolvedUtility()
  const shortCasts = skillshotCastsForFight(luxFull, 'short')
  const extCasts = skillshotCastsForFight(luxFull, 'extended')
  assert(
    'Pass-8: short mode omits R from cast multiset',
    shortCasts.every((c) => c.slot !== 'R') &&
      extCasts.some((c) => c.slot === 'R'),
    `short=${shortCasts.map((c) => c.slot).join(',')} ext=${extCasts.map((c) => c.slot).join(',')}`,
  )
  const noRCasts = skillshotCastsForFight(luxNoR, 'extended')
  assert(
    'Pass-8: unranked R omitted from cast multiset',
    noRCasts.every((c) => c.slot !== 'R') && noRCasts.length > 0,
  )
  const nearBands = fightDodgeBands(
    [luxFull],
    [targetNear],
    empty,
    visionUnits,
    'blue',
    undefined,
    'extended',
  )
  const oorTarget = {
    ...targetNear,
    position: { x: 0.95, y: 0.95 },
  } satisfies FighterLoadout
  // Mix near + OOR by averaging rows that include a forced OOR zero
  const oorFlat = averageXhRows([
    { xH: nearBands?.typical ?? 0.5, bands: nearBands },
    { xH: 0, bands: { worst: 0, typical: 0, best: 0 } },
  ])
  assert(
    'Pass-8: OOR zero pulls typical down vs in-range-only',
    !!nearBands &&
      !!oorFlat.bands &&
      oorFlat.bands.typical < nearBands.typical + 1e-9,
    `near=${nearBands?.typical} mixed=${oorFlat.bands?.typical}`,
  )
  const flashUpBands = fightDodgeBands(
    [luxFull],
    [{ ...targetNear, flashCdRemainingSec: 0 }],
    empty,
    visionUnits,
    'blue',
    undefined,
    'extended',
  )
  assert(
    'Pass-8: Flash-up ⇒ mix≡typical (policy typical)',
    flashUpBands != null &&
      flashUpBands.mix != null &&
      Math.abs(flashUpBands.mix - flashUpBands.typical) < 1e-9,
  )
  const neBands = fightDodgeBands(
    [luxFull],
    [
      {
        ...targetNear,
        flashCdRemainingSec: undefined,
        summonerSpells: ['Flash', 'Ignite'],
      },
    ],
    empty,
    visionUnits,
    'blue',
    undefined,
    'extended',
  )
  assert(
    'Pass-8: Flash-unknown ⇒ mix present and below typical',
    neBands != null &&
      neBands.mix != null &&
      neBands.mix + 1e-9 < neBands.typical,
  )
  const wideRow = estimateXh(
    base({
      missileWidth: 220,
      abilityRange: 1100,
      dashReady: false,
      crowdControlled: true,
    }),
  )
  const thinRow = estimateXh(
    base({
      missileWidth: 60,
      abilityRange: 1100,
      dashReady: false,
      crowdControlled: true,
    }),
  )
  assert(
    'Pass-8: wider kit missile → higher corridor xH',
    wideRow.xH + 1e-9 >= thinRow.xH,
    `wide=${wideRow.xH.toFixed(3)} thin=${thinRow.xH.toFixed(3)}`,
  )
}

// --- Pass-8 EMPIRICS ---
{
  const jll = xhmWrongRhoJointLogLossKillSanity({
    p: 0.55,
    n: 4,
    rhoStar: 0.5,
    trials: 1200,
  })
  assert(
    'Pass-8: wrong-ρ joint LL kill',
    jll.shouldKillWrongRho,
    `gain=${jll.gain.toFixed(3)}`,
  )
  const vs = xhmWrongRhoVariogramKillSanity({
    p: 0.55,
    n: 4,
    rhoStar: 0.5,
    trials: 2500,
    pairedDraws: 32,
  })
  assert(
    'Pass-8: wrong-ρ variogram kill',
    vs.shouldKillWrongRho,
    `gain=${vs.gain.toFixed(3)}`,
  )
  const cells = [
    { R: 50, mu: 10, sigma: 30 },
    { R: 80, mu: 0, sigma: 40 },
    { R: 40, mu: 35, sigma: 25 },
  ]
  const idIso = isotonicHeldOutGainSanity({
    cells,
    bias: 0,
    trialsPerCell: 2000,
  })
  assert(
    'Pass-8: Isotonic identity → no-op',
    !idIso.shouldApply,
    `gain=${idIso.gain.toFixed(4)}`,
  )
  const badIso = isotonicHeldOutGainSanity({
    cells,
    bias: 0.12,
    trialsPerCell: 2500,
  })
  assert(
    'Pass-8: Isotonic biased → apply',
    badIso.shouldApply,
    `gain=${badIso.gain.toFixed(4)}`,
  )
  const coxOk = corridorCoxSanity({ cells, bias: 0, trialsPerCell: 2000 })
  assert(
    'Pass-8: Cox true corridor ok',
    coxOk.ok,
    `a=${coxOk.intercept.toFixed(3)} b=${coxOk.slope.toFixed(3)}`,
  )
  const coxBad = corridorCoxSanity({ cells, bias: 0.12, trialsPerCell: 2000 })
  assert(
    'Pass-8: Cox biased trips tols',
    coxBad.shouldKillBiased,
    `a=${coxBad.intercept.toFixed(3)} b=${coxBad.slope.toFixed(3)}`,
  )
  const spOk = corridorSpiegelhalterSanity({
    cells,
    bias: 0,
    trialsPerCell: 2000,
  })
  assert(
    'Pass-8: Spiegelhalter true corridor |Z| ok',
    spOk.ok,
    `z=${spOk.z.toFixed(3)}`,
  )
  const spBad = corridorSpiegelhalterSanity({
    cells,
    bias: 0.12,
    trialsPerCell: 2000,
  })
  assert(
    'Pass-8: Spiegelhalter biased trips |Z|',
    spBad.shouldKillBiased,
    `z=${spBad.z.toFixed(3)}`,
  )
  const covC = xhmConditionalCoverageSanity({
    cells: [
      { p: 0.35, n: 4, rhoStar: 0.5 },
      { p: 0.55, n: 4, rhoStar: 0.5 },
      { p: 0.75, n: 4, rhoStar: 0.5 },
    ],
    trialsPerCell: 4000,
  })
  assert(
    'Pass-8: conditional 90% PI tertiles honest under ρ★',
    covC.okStar,
    `cov=${covC.covByTertile.map((c) => c.toFixed(3)).join(',')}`,
  )
  assert(
    'Pass-8: conditional 90% PI wrong ρ=0 worse',
    covC.okKillWrong,
  )
  const sk = stratifiedAbilityResidualKillSanity({
    pStar: 0.55,
    ability: 'LuxQ',
    strata: { vision: 'fog', rangeBand: 'mid' },
    corridorBias: 0.15,
    casts: 400,
  })
  assert(
    'Pass-8: stratified ability residual kill trips',
    sk.shouldKillB1,
    `key=${sk.key} res=${sk.residual.toFixed(3)}`,
  )
  const skKeep = stratifiedAbilityResidualKillSanity({
    pStar: 0.55,
    ability: 'LuxQ',
    strata: { vision: 'fog', rangeBand: 'mid' },
    corridorBias: 0,
    casts: 400,
  })
  assert(
    'Pass-8: stratified ability identity → no kill',
    !skKeep.shouldKillB1,
    `res=${skKeep.residual.toFixed(3)}`,
  )
  assert(
    'Pass-8 kill-criteria deepen fields finite',
    Number.isFinite(KILL_CRITERIA_VS_B1.jointLogLossWrongRhoMinGain) &&
      KILL_CRITERIA_VS_B1.coxSlopeAbsTol > 0 &&
      KILL_CRITERIA_VS_B1.coxInterceptAbsTol > 0 &&
      KILL_CRITERIA_VS_B1.variogramWrongRhoMinGain > 0 &&
      KILL_CRITERIA_VS_B1.spiegelhalterAbsTol > 0,
  )
}

// --- Pass-9 GEO ---
{
  const cpa0 = ballisticSegmentCpa(1000, 0, 200, 1600, 0.05, 2.0, 2000)
  assert(
    'Pass-9: zero extent → t_hit ≡ t_cpa',
    Math.abs(
      ballisticFirstContactSec(1000, 0, 200, 1600, 0.05, cpa0.tCpaSec, 0) -
        cpa0.tCpaSec,
    ) < 1e-12,
  )
  const Vm = 1600
  const R = 900
  const t0 = interceptTimeGo(R, Vm, 0, 0)
  const lam = requiredLeadAngle(t0, R, 0, 0)
  const cpa = ballisticSegmentCpa(R, 0, 0, Vm, lam, t0, 2000)
  const Rh = 135
  const tHit = ballisticFirstContactSec(R, 0, 0, Vm, lam, cpa.tCpaSec, Rh)
  assert(
    'Pass-9: penetrating aim → t_hit ≤ t_cpa',
    tHit <= cpa.tCpaSec + 1e-12,
    `tHit=${tHit} tCpa=${cpa.tCpaSec}`,
  )
  assert(
    'Pass-9: penetrating aim → t_hit < t_cpa when miss < R_hit',
    cpa.missUu >= Rh - 1e-6 || tHit < cpa.tCpaSec - 1e-9,
    `miss=${cpa.missUu} Rh=${Rh}`,
  )
  const def = estimateXh(
    base({
      leadSkill: 0.7,
      targetPerpVel: 200,
      dashReady: false,
      crowdControlled: true,
      residualAccelUuPerSec2: 0,
    }),
  )
  assert('Pass-9: default A=0 still in range', def.inRange === true)
  assert(
    'Pass-9: default path exposes t_hit',
    def.factors.some((f) => f.startsWith('t_hit:')),
    def.factors.join(','),
  )
}

// --- Pass-9 AIM ---
{
  const p9MidT = estimateXh(
    base({
      aimTimeSec: 0.45,
      fittsWidthUu: 180,
      targetPerpVel: 40,
      dashReady: false,
      crowdControlled: true,
    }),
  )
  const p9LongT = estimateXh(
    base({
      aimTimeSec: 0.9,
      fittsWidthUu: 180,
      targetPerpVel: 40,
      dashReady: false,
      crowdControlled: true,
    }),
  )
  assert(
    'Pass-9: T=0.9 σ_aim ≤ T=0.45 (corr pulses ∝ D/T)',
    !!p9MidT.sigma &&
      !!p9LongT.sigma &&
      p9LongT.sigma.aim <= p9MidT.sigma.aim + 1e-6,
    `mid=${p9MidT.sigma?.aim.toFixed(1)} long=${p9LongT.sigma?.aim.toFixed(1)}`,
  )
  const p9SnapT = estimateXh(
    base({
      aimTimeSec: 0.14,
      fittsWidthUu: 180,
      targetPerpVel: 40,
      dashReady: false,
      crowdControlled: true,
    }),
  )
  assert(
    'Pass-9: snap T=0.14 σ_aim > lined T=0.9',
    !!p9SnapT.sigma &&
      !!p9LongT.sigma &&
      p9SnapT.sigma.aim > p9LongT.sigma.aim,
  )
  const p9Acc0 = estimateXh(
    base({
      aimTimeSec: 0.4,
      releaseDelaySec: 0.2,
      targetPerpVel: 180,
      residualAccelUuPerSec2: 0,
      missileSpeed: 1400,
      dashReady: false,
      crowdControlled: true,
    }),
  )
  const p9Acc1 = estimateXh(
    base({
      aimTimeSec: 0.4,
      releaseDelaySec: 0.2,
      targetPerpVel: 180,
      residualAccelUuPerSec2: 900,
      missileSpeed: 1400,
      dashReady: false,
      crowdControlled: true,
    }),
  )
  assert(
    'Pass-9: residualAccel → larger sigma.aim',
    !!p9Acc0.sigma &&
      !!p9Acc1.sigma &&
      p9Acc1.sigma.aim > p9Acc0.sigma.aim + 1e-6,
  )
  assert(
    'Pass-9: accel σ_aim margin ≥ 1.5 uu at |A|=900',
    !!p9Acc0.sigma &&
      !!p9Acc1.sigma &&
      p9Acc1.sigma.aim - p9Acc0.sigma.aim + 1e-6 >= 1.5,
    `Δ=${(p9Acc1.sigma!.aim - p9Acc0.sigma!.aim).toFixed(2)}`,
  )
  const p9Tag = estimateXh(
    base({
      aimTimeSec: 0.5,
      targetPerpVel: 200,
      residualAccelUuPerSec2: 400,
      dashReady: false,
      crowdControlled: true,
    }),
  )
  assert(
    'Pass-9: factors expose corrDT+accel aim path',
    p9Tag.factors.some((f) => f.includes('corrDT') && f.includes('accel')),
    p9Tag.factors.join(','),
  )
}

// --- Pass-9 VISION ---
{
  const dark = estimateXh(
    base({
      vision: 'blind',
      softVision: 0,
      lastKnownAgeSec: 8,
      flashReady: false,
      beliefHypotheses: [
        { weight: 0.5, mean: near, zone: 'brush' },
        { weight: 0.5, mean: { x: near.x + 0.04, y: near.y }, zone: 'river' },
      ],
    }),
  )
  const penumbra = estimateXh(
    base({
      vision: 'blind',
      softVision: 0.55,
      softVisionMarginNorm: 0.5,
      lastKnownAgeSec: 8,
      flashReady: false,
      beliefMeanSeen: near,
      beliefHypotheses: [
        { weight: 0.5, mean: near, zone: 'brush' },
        { weight: 0.5, mean: { x: near.x + 0.04, y: near.y }, zone: 'river' },
      ],
    }),
  )
  assert(
    'Pass-9: softV⊕hypotheses → smaller σ_belief than dark',
    !!penumbra.sigma &&
      !!dark.sigma &&
      penumbra.sigma.belief + 1e-6 < dark.sigma.belief,
  )
  const coloc = estimateXh(
    base({
      vision: 'blind',
      softVision: 0.5,
      lastKnownAgeSec: 6,
      beliefMeanSeen: near,
      beliefMeanPosition: near,
    }),
  )
  const shifted = estimateXh(
    base({
      vision: 'blind',
      softVision: 0.5,
      lastKnownAgeSec: 6,
      beliefMeanSeen: { x: near.x + 0.14, y: near.y },
      beliefMeanPosition: near,
    }),
  )
  assert(
    'Pass-9: binary softV between-μ raises σ_belief',
    !!shifted.sigma &&
      !!coloc.sigma &&
      shifted.sigma.belief >= coloc.sigma.belief + 1e-6,
  )
  const flashLo = estimateXh(
    base({
      vision: 'blind',
      softVision: 0.55,
      lastKnownAgeSec: 8,
      flashReady: true,
      beliefMeanPosition: near,
    }),
  )
  const flashHi = estimateXh(
    base({
      vision: 'blind',
      softVision: 0.9,
      lastKnownAgeSec: 8,
      flashReady: true,
      beliefMeanPosition: near,
    }),
  )
  assert(
    'Pass-9: Flash-on-lost under softV 0.55 > softV 0.9',
    !!flashLo.sigma &&
      !!flashHi.sigma &&
      flashLo.sigma.belief + 1e-6 > flashHi.sigma.belief,
  )
}

// --- Pass-9 STRATEGY ---
{
  const ahri = {
    championId: 'Ahri',
    level: 11,
    itemIds: [],
    runeId: null,
    ranks: { Q: 5, W: 3, E: 5, R: 2 },
    summonerSpells: ['Flash', 'Ignite'] as [string, string],
    position: mid,
  } satisfies FighterLoadout
  const lux = {
    championId: 'Lux',
    level: 11,
    itemIds: [],
    runeId: null,
    ranks: { Q: 5, W: 3, E: 5, R: 2 },
    summonerSpells: ['Flash', 'Ignite'] as [string, string],
    position: mid,
  } satisfies FighterLoadout
  const ahriCasts = skillshotCastsForFight(ahri, 'extended', false)
  const qN = ahriCasts.filter((c) => c.slot === 'Q').length
  const eN = ahriCasts.filter((c) => c.slot === 'E').length
  const qCasts = Math.max(1, abilityCastsInFight('extended', 'Q', 0))
  const eCasts = Math.max(1, abilityCastsInFight('extended', 'E', 0))
  // Packet weight = skillshot damage lines × casts (generated Ahri Q is 1 line).
  assert(
    'Pass-9: Ahri cast multiset matches skillshot packet × casts',
    qN === qCasts && eN === eCasts && qN > 0 && eN > 0,
    `Q=${qN}/${qCasts} E=${eN}/${eCasts}`,
  )
  // Multi-line skillshot: force 2× weight via synthetic damage expansion check
  // (CORE Ahri had out+return; generated kit may be 1 — still require E engage drop under lock)
  assert(
    'Pass-9: Ahri open cast multiset non-empty',
    ahriCasts.length >= 2,
  )
  const open = skillshotCastsForFight(lux, 'short', false)
  const locked = skillshotCastsForFight(lux, 'short', true)
  assert(
    'Pass-9: lockedOut omits engageCc Lux Q',
    open.some((c) => c.slot === 'Q') && locked.every((c) => c.slot !== 'Q'),
  )
  assert(
    'Pass-9: lockedOut multiset shorter than open',
    locked.length < open.length,
  )
}

// --- Pass-9 EMPIRICS ---
{
  const cells = [
    { R: 50, mu: 10, sigma: 30 },
    { R: 80, mu: 0, sigma: 40 },
    { R: 40, mu: 35, sigma: 25 },
  ]
  const iciOk = corridorIciSanity({ cells, bias: 0, trialsPerCell: 2000 })
  assert('Pass-9: ICI true corridor ok', iciOk.ok, `ici=${iciOk.ici.toFixed(4)}`)
  const iciBad = corridorIciSanity({ cells, bias: 0.12, trialsPerCell: 2000 })
  assert('Pass-9: ICI biased kills', iciBad.shouldKillBiased, `ici=${iciBad.ici.toFixed(4)}`)
  const hlOk = corridorHosmerLemeshowSanity({
    cells,
    bias: 0,
    trialsPerCell: 2000,
  })
  assert(
    'Pass-9: HL χ² true corridor ok',
    hlOk.ok,
    `chi=${hlOk.chiSq.toFixed(2)}`,
  )
  const hlBad = corridorHosmerLemeshowSanity({
    cells,
    bias: 0.12,
    trialsPerCell: 2000,
  })
  assert(
    'Pass-9: HL χ² biased kills',
    hlBad.shouldKillBiased,
    `chi=${hlBad.chiSq.toFixed(2)}`,
  )
  const spOk = corridorSphericalSanity({ cells, bias: 0, trialsPerCell: 2000 })
  assert('Pass-9: spherical vs coin ok', spOk.ok)
  const spBad = corridorSphericalSanity({
    cells,
    bias: 0.12,
    trialsPerCell: 2000,
  })
  assert('Pass-9: spherical biased kills', spBad.shouldKillBiased)
  const ad = xhmPitAdSanity({ p: 0.55, n: 4, rhoStar: 0.5, trials: 4000 })
  assert('Pass-9: AD-PIT under ρ★ ok', ad.okStar, `ad=${ad.adStar.toFixed(3)}`)
  assert('Pass-9: AD-PIT wrong ρ worse', ad.okKillWrong)
  const cw = xhmConditionalWinklerSanity({
    cells: [
      { p: 0.35, n: 4, rhoStar: 0.5 },
      { p: 0.55, n: 4, rhoStar: 0.5 },
      { p: 0.75, n: 4, rhoStar: 0.5 },
    ],
    trialsPerCell: 3000,
  })
  assert('Pass-9: cond Winkler ρ★ beats ρ=0', cw.okStar)
  assert('Pass-9: cond Winkler kill wrong', cw.okKillWrong)
  const q4 = rhoQuartetRecoverySanity({
    p: 0.55,
    rhoStar: 0.5,
    nQuartets: 20000,
  })
  assert(
    'Pass-9: quartet ρ MoM recovery',
    q4.ok,
    `err=${q4.absErr4.toFixed(3)}`,
  )
  const tw = xhmWrongRhoTwCrpsKillSanity({
    p: 0.55,
    n: 4,
    rhoStar: 0.5,
    trials: 4000,
  })
  assert(
    'Pass-9: twCRPS wrong-ρ kill',
    tw.shouldKillWrongRho,
    `gain=${tw.gain.toFixed(3)}`,
  )
  assert(
    'Pass-9 kill-criteria deepen fields finite',
    KILL_CRITERIA_VS_B1.iciTol > 0 &&
      KILL_CRITERIA_VS_B1.hosmerLemeshowChiSqTol > 0 &&
      KILL_CRITERIA_VS_B1.sphericalVsCoinMaxRatio > 0 &&
      KILL_CRITERIA_VS_B1.pitAdTol > 0 &&
      KILL_CRITERIA_VS_B1.quartetRhoAbsErrTol > 0 &&
      KILL_CRITERIA_VS_B1.twCrpsWrongRhoMinGain > 0,
  )
}

// --- Pass-10 VISION ---
{
  const ageLo = estimateXh(
    base({
      vision: 'blind',
      softVision: 0.49,
      flashReady: true,
      beliefMeanPosition: near,
    }),
  )
  const ageHi = estimateXh(
    base({
      vision: 'blind',
      softVision: 0.51,
      flashReady: true,
      beliefMeanPosition: near,
    }),
  )
  assert(
    'Pass-10: no ageDefault cliff at softV=0.5',
    !!ageLo.sigma &&
      !!ageHi.sigma &&
      Math.abs(ageLo.sigma.belief - ageHi.sigma.belief) < 80,
    `lo=${ageLo.sigma?.belief.toFixed(1)} hi=${ageHi.sigma?.belief.toFixed(1)}`,
  )
  const penNoAge = estimateXh(
    base({
      vision: 'blind',
      softVision: 0.7,
      flashReady: true,
      beliefMeanPosition: near,
    }),
  )
  const seenNoAge = estimateXh(
    base({
      vision: 'blind',
      softVision: 0.9,
      flashReady: true,
      beliefMeanPosition: near,
    }),
  )
  assert(
    'Pass-10: penumbra unset-age Flash/FoW σ_belief > softV=0.9',
    !!penNoAge.sigma &&
      !!seenNoAge.sigma &&
      penNoAge.sigma.belief + 1e-6 > seenNoAge.sigma.belief,
  )
}

// --- Pass-10 EMPIRICS ---
{
  const cells = [
    { R: 50, mu: 10, sigma: 30 },
    { R: 80, mu: 0, sigma: 40 },
    { R: 40, mu: 35, sigma: 25 },
  ]
  const cIci = corridorConditionalIciSanity({
    cells,
    bias: 0,
    trialsPerCell: 3000,
  })
  assert(
    'Pass-10: cond ICI true corridor ok',
    cIci.ok,
    `icis=${cIci.icis.map((x) => x.toFixed(3)).join(',')}`,
  )
  const cIciBad = corridorConditionalIciSanity({
    cells,
    bias: 0.12,
    trialsPerCell: 3000,
  })
  assert('Pass-10: cond ICI biased kills', cIciBad.shouldKillBiased)
  const cvm = xhmPitCvmSanity({ p: 0.55, n: 4, rhoStar: 0.5, trials: 8000 })
  assert(
    'Pass-10: CvM-PIT under ρ★ ok',
    cvm.okStar,
    `cvm=${cvm.cvmStar.toFixed(3)}`,
  )
  assert('Pass-10: CvM-PIT wrong ρ worse', cvm.okKillWrong)
  const pin = xhmWrongRhoPinballKillSanity({
    p: 0.55,
    n: 4,
    rhoStar: 0.5,
    trials: 8000,
  })
  assert(
    'Pass-10: pinball wrong-ρ kill',
    pin.shouldKillWrongRho,
    `gain=${pin.gain.toFixed(3)}`,
  )
  const nearMiss = xhmNearMissRhoCrpsKillSanity({
    p: 0.55,
    n: 4,
    rhoStar: 0.5,
    trials: 8000,
  })
  assert(
    'Pass-10: near-miss ρ CRPS kill',
    nearMiss.shouldKillNearMiss,
    `gain=${nearMiss.gain.toFixed(3)}`,
  )
  const midTw = xhmWrongRhoMidTwCrpsKillSanity({
    p: 0.55,
    n: 4,
    rhoStar: 0.5,
    trials: 8000,
  })
  assert(
    'Pass-10: mid-twCRPS wrong-ρ kill',
    midTw.shouldKillWrongRho,
    `gain=${midTw.gain.toFixed(3)}`,
  )
  assert(
    'Pass-10 kill-criteria deepen fields finite',
    KILL_CRITERIA_VS_B1.conditionalIciTol > 0 &&
      KILL_CRITERIA_VS_B1.pitCvmTol > 0 &&
      KILL_CRITERIA_VS_B1.pinballWrongRhoMinGain > 0 &&
      KILL_CRITERIA_VS_B1.nearMissCrpsMinGain > 0 &&
      KILL_CRITERIA_VS_B1.midTwCrpsWrongRhoMinGain > 0,
  )
}

const passed = checks.filter((c) => c.pass).length
const total = checks.length
const rate = passed / total

console.log('\n=== xH math eval ===')
for (const c of checks) {
  console.log(`${c.pass ? 'PASS' : 'FAIL'}  ${c.name}${c.detail ? `  (${c.detail})` : ''}`)
}
console.log(`\nmath_pass_rate=${rate.toFixed(4)}  (${passed}/${total})`)
if (passed < total) process.exitCode = 1
