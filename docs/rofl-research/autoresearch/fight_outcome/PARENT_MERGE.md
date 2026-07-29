
## 2026-07-24T15:41:21Z — R02 source-preserve KEEP
- Source: `adv/fo-r02-digest-sources` @ `/Users/river/.codex/worktrees/rofl-fo-r02`
- Agent: abbc2aca-3482-4145-89de-dd89de042d7f
- Files: fuse_product_timeline.py, fuse_replay_api_combat.py, test_source_preserve_r02.py, fo_r02_source_preserve_audit.py (+ r11 test if differed)
- Reason: knownWithoutSource 0/0/0 on Path1 2970132; strip/clear no longer orphan sources
- Gate impact: digestCleanGate still false (needs DIGEST+reviewers); enables §D.2
- Test: `python3 -m unittest scripts.tests.test_source_preserve_r02 -v`

## 2026-07-24T15:42:17Z — R03 digest-validate KEEP (docs)
- Agent: 48094095-ba2f-4310-b21a-1eff4d526704
- DIGEST.md already improved (validate green 2970132; 2970110 PE gap disclosed)
- No code merge required (docs-only)
- digestCleanGate still false pending V2

## 2026-07-24T15:42:17Z — R04 metric-scorer (measure harness)
- Agent: 330454fb-4768-43fa-93a1-16ac566f6641
- Merged: scripts/fight_agreement_suite.ts from worktree (if present)
- S0 product FA 0.4217 / pass 0.1667 (2970110 proxy); research-drop 0.6018
- S1 product FA 0.3279 / pass 0.0 — gate false
- No best.json rewrite

## 2026-07-24T15:42:17Z — R07 unfreeze-marks NO KEEP
- Agent: 3d5804e9-0fe2-4789-a584-9561c061e13f
- Best FA 0.5351 Δ0 vs E0; product cusum worse −0.0503
- best.json unchanged; product selectors unchanged

## 2026-07-24T15:43:23Z — R01 digest-path KEEP
- Agent: 5ce6dcc7-be83-4373-a540-87f001e60b23
- Path1 digest proven; stamp_digest_path1_provenance.py merged
- digestCleanGate still false (V2 + second host)

## 2026-07-24T15:43:23Z — R06 metric-suites KEEP_wire_measure
- Agent: c3fc9baa-716c-4478-ae3c-40da78a1f461
- S1 FA 0.478 / pass 0.333; S2 FA 0.634 / pass 0.333 — gates fail
- No S1 tuning; Camille PE closed on measured hosts

## 2026-07-24T15:47:51Z — R05 metric-s0 Path1 measure
- Agent: 119a5d7d-a282-4c4b-9360-a83feae2a404
- Created crosschecks-2970132-g1.json
- S0 Path1 product cusum FA **0.228** / pass 0.000 — gate false (worse than 2970110 proxy)
- No code merge (worktree suite only)

## 2026-07-24T15:47:51Z — R08 unfreeze-density NO overlay KEEP
- Agent: d9c6232e-8822-488b-87ab-cc86986222e1
- 26 exps; S0 best still research BEST FA 0.493; product density hurts S0 / helps S1
- Do NOT merge overlays; best.json unchanged

## 2026-07-24T15:52:11Z — R14 action-noecho KEEP (docs/research)
- Agent: b194f6db-8de6-4d7b-8273-a2aa0c13f20a
- Honest PE damage F1=1.0; zero-dmg echo REJECTED for FA credit
- No parent product code merge required this wave (audit in r14/)

## 2026-07-24T15:55:01Z — R11 utility planner KEEP_contract
- Agent: e845305b-895e-482e-88e1-c952a541fe91
- Keep utility/engageCc at 0 damage in timed planner (honesty); FA flat 0.4217 — no best.json
- Merged parent combat/overlay if worktree differed

## 2026-07-24T15:56:48Z — R15/R16/R17
- R15: wire emit proof KEEP; FA regress discard
- R16: smoke:calc-parity Criterion G (11/11)
- R17: fo:send-smoke Criterion G (8/8)
- Merged smoke scripts/npm if present; FA still 0.228

## 2026-07-24T16:01:23Z — R19 path1-early KEEP (idleFollowActual)
- Source: `adv/fo-r19-path1-early` @ `/Users/river/.codex/worktrees/rofl-fo-r19`
- Agent: b7f2e735-8e73-4c2a-8348-01535e1f4d1f
- Files: killWindowOverlay.ts, killWindowProduct.ts, types.ts, crosscheck_action_aligned.ts, killWindow.acceptance.test.ts
- Change: product `idleFollowActual: true` (truth-follow idle until engageSec)
- Measured (worktree): S0 FA 0.295→**0.411** (Δ+0.116); S1 FA +0.089 without S1 tune; Galio earlyMae 116→0
- Gate: fightOutcomeGate still false (FA≪0.95; passRate 0.167; Galio miss-kill; check03 earlyPoisoned)
- Test: `npm run test:kill-window` → 23 passed
- FA ≠ odds

## 2026-07-24T16:01:23Z — R20 holdout-s1 MEASURE_DISCLOSE_NO_KEEP
- Agent: c273af5d-e0b6-490a-8e9c-86868320984a
- S1 current-law freeze FA **≈0.411** / pass **≈0.167** (n=6) under LETHAL_TOL=0.75
- BRIEF/R06 cited **0.478** was inflated lethal on 2970137-c2 — superseded
- Camille PE invent refused; never_edited_parent_code true

## 2026-07-24T16:03:55Z — R22 camille-q-wire KEEP (wiki Q; no FA claim)
- Source: `adv/fo-r22-camille-q-wire` @ `/Users/river/.codex/worktrees/rofl-fo-r22`
- Agent: ffc8f9ac-a9bf-4294-8816-94a72df42a95
- File: src/data/generatedGameChamps.ts Camille.Q (wiki %AD + attackReset/empoweredAuto + MS utility)
- PE coeffs/recast: refused (impossibility disclosed)
- Path1 S0 FA unchanged vs Q lever (killers Galio/Olaf) — NO_FA_KEEP
- FA ≠ odds

## 2026-07-24T16:03:55Z — Phase C Cycle3 CLOSED
- fightOutcomeGate: **false** (0/15)
- digestCleanGate: **true** (12/15; dissent V12/V14/V15)
- criterionG: true
- Final: reviews/cycle3/CYCLE3_FINAL.json → CONTINUE_PHASE_B

## 2026-07-24T16:05:11Z — R25 path1-remeasure (no KEEP)
- Agent: c08b031f-ef02-49b4-b1de-70e43a5abc5b
- S0 Path1 FA **0.4107** / pass **0.167** (bit-match R19); vs R05 +0.183
- S1 current-law FA **0.4170** / pass 0 (no tune)
- Idle honesty closed; residual = lethal/timing (Galio miss-kill, lethErr≈2.81s, c3 earlyPoisoned 476)
- FA ≠ odds

## 2026-07-24T16:06:00Z — R27 suite-windows (docs KEEP, no code)
- Agent: a1c0a703-1fcc-4f4c-9cad-d5b86c6683e9
- Path1 suite complete: 6/6 on 2970132-g1 (SQLite-verified)
- S0=12 · S1=12 · S2=6 stable window ids under fight_outcome/r27/
- never_edited_parent_code: true

## 2026-07-24T16:07:52Z — R23 path1-lethal2 NO KEEP
- Agent: aec47760-dd9d-4b03-8d8d-136d471c8187
- Research best FA 0.250 (e7); product stays 0.228 on freeze-idle baseline / R25 product still 0.4107 idle-follow
- Galio W dropped 0.334s pre-CUSUM; sparse preEngageOpener research-only; |lethErr|≥1.13
- S1 never improves → no product KEEP

## 2026-07-24T16:08:35Z — R29 anti-odds KEEP_copy
- Agent: 8a099483-a0fa-46ff-91c1-3644fa1e12fb
- Files: Faq.tsx (model-edge-not-odds), gameStateOdds.ts, combat.ts comment, product_anti_odds_audit.ts
- best.json 0.9683 untouched
- Test: npm run test:anti-odds

## 2026-07-24T16:09:20Z — R21 path1-falsekill NO KEEP
- Agent: 63adb4c6-2e06-43c4-91a7-69bd55c5733a
- False-kill 0.50→0.00 research (e14 slot_ability); Path1 research FA 0.556 but S1 regress → product continuous unchanged
- Cause: continuous 0.4s DPS pulse + aaAtEachMark double-count
- Handoff: e14 recipe to lethal tracks without re-FK / without S1 regress
- FA ≠ odds

## 2026-07-24T16:11:03Z — Phase C Cycle4 CLOSED
- fightOutcomeGate: **false** (0/15)
- digestCleanGate: **true** (reaffirm; see CYCLE4_FINAL.json)
- Final: reviews/cycle4/CYCLE4_FINAL.json → CONTINUE_PHASE_B

## 2026-07-24T16:11:30Z — R26 check03-poison NO KEEP
- Agent: 02521e5e-d828-4327-9e3d-433ff9f4381a
- earlyMae 476→89.6 research; S0 FA +0.135; S1 FA −0.056 → no product KEEP
- Cause: teamfight opener 1v1 full-share overkill (not idle / not false_all_in)
- Global assist-share is one-coeff trap on holdout
- FA ≠ odds

## 2026-07-24T16:11:30Z — C4 V6–V15 batches confirmed in CYCLE4_FINAL
- Agents: beac8feb-cb0d-4955-84d9-efafaf6738ea, 35414178-4798-4cb0-b7f2-318738a55b1f
- Note: V8 alone voted G=false (fo:send-smoke E2 endHp drift) — re-check parent smoke

## 2026-07-24T16:12:16Z — G restore: fo:send-smoke E2 idleFollowActual parity
- Cause: Matchup used PRODUCT defaults (idleFollowActual true); series path omitted flag → endHp 1137 vs 1066
- Fix: scripts/fo_r17_send_parity_smoke.ts pass idleFollowActual from PRODUCT_KILL_WINDOW_DEFAULTS
- Verify: npm run fo:send-smoke + smoke:calc-parity

## 2026-07-24T16:13:07Z — G restore complete (fo:send-smoke 8/8)
- E2 also needed selected.engageSec (CUSUM) not raw 1.5 + idleFollowActual
- npm run fo:send-smoke → 8/8; smoke:calc-parity → 11/11

## 2026-07-24T16:13:51Z — R28 galio-kit KEEP (CORE Galio)
- Agent: d8947b4d-40cb-4e93-83a9-f39d60f64291
- File: src/data/champions.ts Galio CORE (Q tornado %maxHP, W taunt/charge, E, R, Colossal Smash)
- check01 full modelKilled=true |lethErr|=0.36; burst still 0 marks → R24
- Claimed S0 FA 0.344→0.413; S1 flat 0.561; modelTrust still uncalibrated (CORE attention)
- FA ≠ odds; best.json untouched

## 2026-07-24T16:15:41Z — R30 olaf-lethal KEEP
- Agent: 15cbe0b5-0f66-462d-9f5d-6fd5f2422a3c
- Files: killWindowProduct.ts, killWindowOverlay.ts, crosscheck_action_aligned.ts
- Defaults: aaAtEachMark=false; perSlotPulse + pulseBySlot R=0
- S0 FA 0.411→**0.590**; S1 0.417→**0.562**; Olaf |lethErr| 2.81→0.33
- best.json FA fields updated; composite 0.9683 history preserved
- Also fixed fo_r16 seriesFromMatchup to mirror product defaults (e1 parity)
- FA ≠ odds; G smokes green

## 2026-07-24T16:16:17Z — R24 galio-kill NO KEEP (last researcher)
- Agent: 102e5cf7-ead0-49df-86c7-de7532511d15
- Research e49: Galio model kill |lethErr|=0.356; Path1 FA 0.228→0.503 on pre-KEEP baseline
- S1 0.519→0.338 → no product KEEP; harness knobs research-only
- Product FA remains R30 **0.590** (not R24 0.503)

## 2026-07-24T16:16:17Z — Phase C Cycle5 triggered (30/30)

## 2026-07-24T16:19:58Z — Phase C Cycle5 CLOSED (30/30 wave1)
- fightOutcomeGate: **false** (0/15)
- digestCleanGate: **true** (15/15)
- G: true
- Decision: CONTINUE_OVERNIGHT (FO unmet) — wave2 researchers on residual blockers
- Agents: V1–V5 32b4b4fd…; V6–V10 2b5c211a…; V11–V15 720c2d8b…

## 2026-07-24T16:23:53Z — R37 holdout-s1-remeasure (no KEEP)
- Agent: 1ce7fc29-5744-482d-8633-fd70749f92aa
- Authoritative S0 FA **0.5938** / pass 0.333; S1 FA **0.5620** / pass 0.333
- S1 bit-match R30; S0 +0.004 vs R30 (Galio CORE)
- never_edited_parent_code; FA ≠ odds; gate false

## 2026-07-24T16:26:46Z — R38 suite-audit-gaps KEEP (docs-only)
- Agent: e2bfe2f9-fb96-4686-96f5-d447703d416a
- 19 failing S0/S1 windows audited under fight_outcome/audits/ (r27 stable ids)
- Corrected mislabeled 2970110 matchups; no invent; not FO gate evidence

## 2026-07-24T16:31:42Z — R35 preengage-s1safe KEEP
- Agent: 5435eac5-7d66-4ae7-bea9-b58a74f3fd06
- Files: killWindowProduct.ts, killWindowOverlay.ts, types.ts, crosscheck_action_aligned.ts
- Defaults: preEngageOpenerSec=0.5, preEngageOpenerMaxPostMarks=3
- S0 FA 0.5938→**0.6021**; S1 0.562→**0.581**; Galio W restored; |lethErr| still 1.84
- R24 far-share rejected; G smokes 8/8 + 11/11; FA ≠ odds

## 2026-07-24T16:33:06Z — R34 s0-passrate KEEP (Galio tornado 0.15)
- Agent: (summary at fight_outcome/r34; absorbed with R35 follow-up)
- File: champions.ts Galio Q tornadoPct 0.10→0.15 (attention blend; not calibrated)
- Claimed S0 FA→0.663 / pass→0.500; S1 flat — remesaure pending compound with R35/R32

## 2026-07-24T16:33:06Z — R32 check03-share KEEP (residual_hp)
- Agent: 1bcd1101-a38d-40cd-afb8-19f7c9d480c2
- Product defaults: killerShareMode=residual_hp (+ residual* knobs)
- Overlay already had residual_hp impl; enabled via product defaults
- Claimed S0 FA→0.7307; S1 flat; c3 earlyPoisoned cleared — remesaure pending compound

## 2026-07-24T16:35:34Z — R32/R34 already merged (notification ack)
- R32 residual_hp + R34 Galio tornado 0.15 were PARENT_MERGED in prior tick

## 2026-07-24T16:35:34Z — R36 ally-attrib KEEP
- Agent: 6844c0a8-5fd9-45be-b96b-ad25cd0da1f5
- Files: scripts/lib/opener_ally_attrib.ts, crosscheck_action_aligned.ts, killWindowProduct.skillMarksFromTimeline
- Defaults: openerAllyAttrib=local_skill_share (allyMin5, killerMin1, full-window gate)
- Claimed S0 FA→0.722; S1 flat; preserves R32/R35 KEEPs; G smokes green
- Compound remesaure still pending for authoritative FA

## 2026-07-24T16:38:56Z — Phase C Cycle6 CLOSED
- fightOutcomeGate: **false** (0/15)
- digestCleanGate: **true** (15/15)
- G: true
- Decision: CONTINUE_WAVE2 — await R31/R33 + compound remesaure
- Agents: V1–V5 d59501aa…; V6–V10 769c017f…; V11–V15 e417c7e5…

## 2026-07-24T16:40:59Z — R33 KEEP absorbed (zeroDeadActualHp)
- Agent: [R33](0ad4930c-6631-4355-9a87-23f20f01cd42)
- Product KEEP: harness `zeroDeadActualHp: true` (alive===0 → HP 0); pathFollow/pathClamp NOT product
- Surgical onto parent (preserve R32/R35/R36) — did NOT copy stale r33 worktree product.ts
- Reported: c2 pathBand 0.693→0.760; S0 FA 0.594→0.596; S1 flat 0.562; pathOk still false
- Rejected: pathFollow (S1 regress), pathClamp, killerShare≤0.99

## 2026-07-24T16:42:03Z — compound remesaure (post R33)
- S0 FA **0.7323** pass 0.333 (authoritative; claimed ~0.72 confirmed) FA≠odds
- S1 FA **0.5810** pass 0.333 (↑ vs R33-alone 0.562; no regress)
- c2_burst maeHp 111.6 pathBand pathOk still false
- Artifacts: r33/experiments/parent_stack_r33_remeasure.json + fight_agreement_S{0,1}_parent_stack_r33.json

## 2026-07-24T16:46:21Z — R31 KEEP absorbed (markPreBurstSkillLeadSec=2.5)
- Agent: [R31](0c7807ea-058f-4ec3-b7e8-5387b7773531)
- Product KEEP: burst mark-domain lead 2.5s @ share 1 (Galio E+Q); HP onset legacy
- Surgical onto parent (preserve R32/R33/R35/R36)
- Compound remesaure: S0 FA **0.7766** pass 0.333; S1 FA **0.5810** flat; c1 burst marks=2 killed |leth|=0.635; A4 strict lethal PASS on S0
- Rejected: lead 3.5/W, R24 lead/far, heal-tolerant onset

## 2026-07-24T16:48:29Z — wave2 CLOSED; wave3+C7 launched
- R31 KEEP absorbed; S0 FA 0.7766 authoritative
- Wave3: R39–R46 live
- C7: V1–V15 batches live

## 2026-07-24T16:51:12Z — Phase C Cycle7 CLOSED
- fightOutcomeGate: **false** (0/15)
- digestCleanGate: **true** (15/15)
- G: true
- Decision: CONTINUE_WAVE3 — await R39–R46
- Agents: V1–V5 3ce20ee0…; V6–V10 aa5a65a8…; V11–V15 88b35d47…

## 2026-07-24T16:54:23Z — R45 NO KEEP absorbed (S2 transfer)
- Agent: [R45](07829aba-328b-4980-b2ae-ecb5e7c86e45)
- Series: 2954868-g1 unused pro slim
- S2 FA **0.4075** pass **0**; research best 0.4482 still pass 0
- No product merge; sharper: Camille→Vayne late leth; Cassio miss-kill; LeeSin earlyPoisoned

## 2026-07-24T16:59:55Z — R44 KEEP absorbed (truth domain + engage remap)
- Agent: [R44](9f504667-dc6c-4f5d-859f-ea312c412d59)
- Harness-only: truthBurstWindowOnly=false, truthPreBurstRemap=true; aaEcho disclose-only (no fold)
- Compound remesaure: S0 FA **0.7907** pass 0.333; S1 FA **0.5810** flat; c1-burst F1 **0.667** (secondary; not FO gate)
- Echo F1=1 REJECTED

## 2026-07-24T17:02:27Z — R39+R41+R42 KEEP batch (+ R46 NO KEEP)
- [R39](d58e0866-7911-4100-a451-4228ed5c6cce) KEEP: preEngageOpenerShare=0.18 slots=[2] (W attenuate)
- [R41](fe81dc28-a018-43c7-94ef-ca9c05203f11) KEEP subsumed: same Galio leth fix; prefer R39 slot filter over Path1 host-gate 0.2
- [R42](31b63d17-1cbe-422a-8736-3eba25351378) KEEP: markPreBurstDelaySec=0.3 + earlyMaePreEngageOnly
- [R46](4a8d58b4-8449-402c-a9f4-d9660d11b615) NO KEEP: finish/density cannot lift passRate alone
- Compound remesaure: S0 FA **0.9304** pass **0.667**; S1 FA **0.5926** pass 0.333; c1 full |leth|=0.36; c1 burst early/path mae 0
- Residual: c2_burst pathMae 111.6; S1 miss-kills; pass≪0.95

## 2026-07-24T17:04:13Z — R43 KEEP absorbed (Anivia CORE)
- Agent: [R43](a49355a0-1deb-40b8-82ac-f5becf8ff349)
- Product: Anivia CORE Q double + E chill×2 + Q-fold storm 7 ticks; R-pulse stays 0
- Compound remesaure: S0 FA **0.9304** flat; S1 FA **0.7628** pass **0.500**; c3 |leth|=0.125
- Rejected: global R-pulse (S0 Olaf regress)

## 2026-07-24T17:04:45Z — R40 NO KEEP absorbed (c2 pathMae)
- Agent: [R40](b9400284-fe1f-4e47-a799-6d7f2f60190a)
- No product merge; pathMae floors ~101 under lethOk; pathFollow S1-unsafe
- Wave3 CLOSED 8/8
