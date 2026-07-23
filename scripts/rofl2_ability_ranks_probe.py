#!/usr/bin/env python3
"""Phase B: ability-rank wire probe — UpgradeSpellAns (636) or fail closed.

Live 16.14 proof path: ``PKT_NPC_UpgradeSpellAns_s`` opcode 636 first-write
level@+0x10 / slot@+0x11 (see ``rofl2_upgrade_spell_ranks``). CastSpellAns
remains identity-only. SkillLevelUp packet name is absent on this PE.

Never fixture-remaps maknee ranks onto the match.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from rofl2_probe import extract_segments, parse_rofl2  # noqa: E402
from rofl2_win_pe_packet_discover import enumerate_rofl  # noqa: E402

DEFAULT_ROFL = (
    Path.home() / "Documents/League of Legends/Replays/BR1-3264361042.rofl"
)
DEFAULT_OUT = Path("docs/rofl-research/ability-ranks-probe-BR1-3264361042.json")
UPGRADE_RANKS_REPORT = Path(
    "docs/rofl-research/upgrade-spell-ranks-BR1-3264361042.json"
)
LEVEL_SLOT_REPORT = Path(
    "docs/rofl-research/castspell-level-slot-BR1-3264361042.json"
)
SKILL_LEVEL_UP_NAME = "SkillLevelUp"
CASTSPELL_ANS_OPCODE = 197
CASTSPELL_ANS_PKT = "PKT_NPC_CastSpellAns_s"
UPGRADE_SPELL_OPCODE = 636
UPGRADE_SPELL_PKT = "PKT_NPC_UpgradeSpellAns_s"


def _load_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def run_ranks_probe(
    rofl: Path,
    *,
    upgrade_report: Optional[Path] = None,
    level_slot_report: Optional[Path] = None,
) -> Dict[str, Any]:
    counts, _ = enumerate_rofl(rofl)
    castspell_blocks = int(counts.get(CASTSPELL_ANS_OPCODE) or 0)
    upgrade_blocks = int(counts.get(UPGRADE_SPELL_OPCODE) or 0)
    info = parse_rofl2(rofl)
    extracted = extract_segments(info["payload"])
    needles = [b"SkillLevelUp", b"mSkillUpLevel", b"SkillUp"]
    hits: Dict[str, int] = {}
    for needle in needles:
        n = 0
        for seg in extracted["segments"]:
            n += (seg["bytes"] or b"").count(needle)
        hits[needle.decode()] = n

    upgrade_path = upgrade_report or UPGRADE_RANKS_REPORT
    upgrade = _load_json(upgrade_path)
    trusted = bool(
        upgrade
        and upgrade.get("ok") is True
        and upgrade.get("abilityRanksTrusted") is True
    )

    level_slot = _load_json(level_slot_report or LEVEL_SLOT_REPORT)

    if trusted and upgrade is not None:
        level_slot_path = level_slot_report or LEVEL_SLOT_REPORT
        return {
            "ok": True,
            "schema": "rofl-ability-ranks-probe-v1",
            "skillLevelUpName": SKILL_LEVEL_UP_NAME,
            "opcodeMapped": True,
            "mappedPkt": UPGRADE_SPELL_PKT,
            "mappedOpcode": UPGRADE_SPELL_OPCODE,
            "castSpellAnsMapped": True,
            "castSpellAnsOpcode": CASTSPELL_ANS_OPCODE,
            "castSpellAnsPkt": CASTSPELL_ANS_PKT,
            "castSpellAnsBlockCount": castspell_blocks,
            "castSpellAnsLevelSlotDecoded": False,
            "upgradeSpellAnsMapped": True,
            "upgradeSpellAnsOpcode": UPGRADE_SPELL_OPCODE,
            "upgradeSpellAnsBlockCount": upgrade_blocks,
            "upgradeSpellAnsDecoded": True,
            "levelSlotEvidence": str(level_slot_path) if level_slot else None,
            "upgradeEvidence": str(upgrade_path),
            "eventCount": upgrade.get("eventCount"),
            "finalRanksByChampion": upgrade.get("finalRanksByChampion"),
            "fieldLayout": upgrade.get("fieldLayout"),
            "plaintextHits": hits,
            "roflOpcodeCount": len(counts),
            "blocker": None,
            "abilityRanksTrusted": True,
            "productEligible": True,
            "dependsOnGateA": False,
            "abilityRanksSource": upgrade.get("abilityRanksSource"),
            "note": (
                "Ability ranks proven via PKT_NPC_UpgradeSpellAns_s opcode 636 "
                "first-write decode; CastSpellAns stays identity-only; "
                "SkillLevelUp name absent on 16.14 PE."
            ),
        }

    detail = (
        "CastSpellAns opcode 197 is mapped for champion identity, but "
        "UpgradeSpellAns ranks evidence is missing or untrusted — "
        "do not fuse abilityRanksKnown"
    )
    if level_slot is not None and not level_slot.get("castSpellAnsLevelSlotDecoded"):
        detail = (
            "CastSpellAns level/slot offsets remain unproven; prefer "
            "PKT_NPC_UpgradeSpellAns_s opcode 636 first-write decode "
            f"(ROFL has {upgrade_blocks} blocks). SkillLevelUp unmapped "
            "(0 plaintext SkillLevelUp hits)."
        )

    return {
        "ok": False,
        "schema": "rofl-ability-ranks-probe-v1",
        "skillLevelUpName": SKILL_LEVEL_UP_NAME,
        "opcodeMapped": False,
        "castSpellAnsMapped": True,
        "castSpellAnsOpcode": CASTSPELL_ANS_OPCODE,
        "castSpellAnsPkt": CASTSPELL_ANS_PKT,
        "castSpellAnsBlockCount": castspell_blocks,
        "castSpellAnsLevelSlotDecoded": False,
        "upgradeSpellAnsMapped": True,
        "upgradeSpellAnsOpcode": UPGRADE_SPELL_OPCODE,
        "upgradeSpellAnsBlockCount": upgrade_blocks,
        "upgradeSpellAnsDecoded": False,
        "upgradeEvidence": str(upgrade_path) if upgrade else None,
        "plaintextHits": hits,
        "roflOpcodeCount": len(counts),
        "blocker": {
            "kind": "ability_ranks_wire_unproven",
            "detail": detail,
        },
        "abilityRanksTrusted": False,
        "productEligible": False,
        "dependsOnGateA": True,
        "note": (
            "Run rofl2_upgrade_spell_ranks.py to prove opcode 636 first-write "
            "level/slot before fusing abilityRanksKnown."
        ),
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rofl", type=Path, default=DEFAULT_ROFL)
    ap.add_argument("--json-out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--upgrade-report", type=Path, default=UPGRADE_RANKS_REPORT)
    ap.add_argument("--level-slot-report", type=Path, default=LEVEL_SLOT_REPORT)
    args = ap.parse_args(argv)
    if not args.rofl.is_file():
        print(f"missing ROFL {args.rofl}", file=sys.stderr)
        return 2
    report = run_ranks_probe(
        args.rofl,
        upgrade_report=args.upgrade_report,
        level_slot_report=args.level_slot_report,
    )
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {args.json_out}")
    print(
        f"ok={report.get('ok')} trusted={report.get('abilityRanksTrusted')} "
        f"blocker={(report.get('blocker') or {}).get('kind')}"
    )
    return 0 if report.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
