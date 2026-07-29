# r43 — s1-anivia-sylas-lethal

**Worktree:** `/Users/river/.codex/worktrees/rofl-fo-r43`  
**Branch:** `adv/fo-r43-s1-anivia-sylas-lethal`  
**never_edited_parent_code:** true  
**FA ≠ odds / pBlue%**

## Mandate
S1 Anivia→Sylas miss-kill without invent; disclose if blocked

## Parent stack (do not regress)
R19 idleFollow · R30 aaAtEachMark false + R-pulse0 · R31 preBurstLead 2.5 · R32 residual_hp (product) · R33 zeroDeadActualHp · R34 Galio Q tornado · R35 preEngageOpener 0.5/3 · R36 openerAlly local_skill_share

## Authoritative baselines (compound post-R31)
- S0 FA **0.7766** pass **0.333** (2970132-g1)
- S1 FA **0.5810** pass **0.333** (2970137-g1)
- c1 burst: marks=2 killed |leth|=0.635; c1 full |leth|=1.84; c2 burst mae=111.6 pathOk false

## Product KEEP rules
KEEP only if S0 FA↑ and S1 flat+; no invent; no FK reopen; no pathFollow/pathClamp product; FA≠odds.
Write `researcher_r43_summary.json` + NOTES.md under fight_outcome/r43/ (mirror docs to parent path OK).
