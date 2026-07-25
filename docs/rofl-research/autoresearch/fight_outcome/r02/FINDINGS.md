# R02 — Source preserve audit (F1 #2)

**utc:** 2026-07-24T15:40:10Z  
**branch:** `adv/fo-r02-digest-sources`  
**worktree:** `/Users/river/.codex/worktrees/rofl-fo-r02`  
**never_edited_parent:** true (code patches only in worktree)  
**hypothesis:** F1#2 Source preserve — audit merge/fuse for silent wipe of `hpSource` / `combatSource` / `abilityRanksSource`

## Verdict

Path1 final **2970132** events→timeline rebuild: **knownWithoutSource = 0/0/0**.  
Two silent-honesty bugs patched in worktree; intentional dead-frame clears documented.

## Findings

| ID | Issue | Status |
|----|-------|--------|
| F1 | `jsonl_to_timeline` historically dropped source tags on rebuild → `peHpHeroes=0/10` | Copy path present; rebuild green |
| F2 | `strip_untrusted_product_fields` wiped floats but left orphan `hpSource`/`combatSource` | **Patched** |
| F3 | Combat clear without `combatSource` pop; worktree combat fuse lacked Path1 `hold_forward` | **Patched** (prd-r04 restore) |
| F4 | HP across-death dead frames `pop(hpSource)` | OK intentional (unknown dead) |

## Evidence (2970132 Path1 final)

| Artifact | bytes | sha256 |
|----------|------:|--------|
| `events.g1.path1-final.rfc461.jsonl` | 114456779 | `823aa35fc309efc7ed7536b5becb9d21f382ea3e03a250d87ad88bee5b0b9bf8` |
| `timeline.g1.path1-final.json` | 9064216 | `fb542736e56e6e0afbbc90c0a6a493b9f0236e898c7bca7c39cde50eaedc4fe4` |

Rebuild census: hp `pe=203` / `hold_forward=16098`; combat PE=1766 / hold=12959; ranks=16960; missing sources=0.

## Patches (worktree only)

1. `scripts/fuse_product_timeline.py` — clear `HP_SOURCE_STRIP_KEYS` + `COMBAT_SOURCE_STRIP_KEYS` on strip
2. `scripts/fuse_replay_api_combat.py` — restore Path1 `HOLD_FORWARD_SOURCE` + `_clear_combat` pops `combatSource`
3. `scripts/tests/test_source_preserve_r02.py` + r11 strip regression
4. `scripts/fo_r02_source_preserve_audit.py`

## Reproduce (~30s)

```bash
cd /Users/river/.codex/worktrees/rofl-fo-r02
python3 -m unittest scripts.tests.test_source_preserve_r02 -v
python3 scripts/fo_r02_source_preserve_audit.py
```

## digestCleanGate note

Contributes source end-to-end honesty for GOAL §D item 2. Does **not** alone flip `digestCleanGate` (still needs single-command DIGEST smoke + reviewer affirm).
