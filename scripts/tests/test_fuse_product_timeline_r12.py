#!/usr/bin/env python3
"""R12 P4 — attach R07 UpgradeSpellAns 1012 ranks into identity-stable fuse."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
ROOT = SCRIPTS.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import fuse_product_timeline as composer  # noqa: E402


IDENTITY = ROOT / (
    "docs/rofl-research/product_ready/r22/"
    "castspell-identity-2970110-g1-pid-stamped.json"
)
POSITION = ROOT / "artifacts/pro-grid/2970110/events.riot.rfc461.research.jsonl"
ACTION = ROOT / (
    "docs/rofl-research/autoresearch/packet_decode/researchers/r41/"
    "emit_2970110_basic_attack_damage.jsonl"
)
RANKS = ROOT / "docs/rofl-research/upgrade-spell-ranks-2970110-g1.json"
WIRE = ROOT / "docs/rofl-research/product_ready/r04/combat-wire-table-16.13.json"
if not WIRE.is_file():
    WIRE = ROOT / "docs/rofl-research/combat-wire-table-16.13.json"
if not WIRE.is_file():
    WIRE = (
        ROOT
        / "docs/rofl-research/autoresearch/product_ready/r04/combat-wire-table-16.13.json"
    )


@unittest.skipUnless(
    IDENTITY.is_file()
    and POSITION.is_file()
    and ACTION.is_file()
    and RANKS.is_file(),
    "2970110 KEEP artifacts / R07 ranks evidence required",
)
class TestFuseProductTimelineR12(unittest.TestCase):
    def test_match_code_series_parse(self) -> None:
        series, game = composer._evidence_series_game({"matchCode": "2970110-g1"})
        self.assertEqual(series, "2970110")
        self.assertEqual(game, 1)

    def test_wrong_match_br1_refused(self) -> None:
        rows: list = []
        _fused, layer = composer.try_ranks_fuse(
            rows,
            ranks_evidence_path=ROOT
            / "docs/rofl-research/upgrade-spell-ranks-BR1-3264361042.json",
            identity=json.loads(IDENTITY.read_text(encoding="utf-8")),
            series="2970110",
            game_index=1,
        )
        self.assertFalse(layer["accepted"])
        self.assertIn("wrong_match", layer["reason"])

    def test_compose_ranks_keepable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            match_dir = Path(tmp) / "2970110"
            summary = composer.compose_product_timeline(
                match_dir=match_dir,
                series="2970110",
                game_index=1,
                identity_path=IDENTITY,
                position_jsonl=POSITION,
                action_jsonl_paths=[ACTION],
                ranks_evidence=RANKS,
                combat_wire_table=WIRE if WIRE.is_file() else None,
            )
            self.assertTrue(summary.get("ok"))
            self.assertTrue(summary.get("keepable"))
            self.assertTrue(summary.get("D_ranks"))
            self.assertTrue(summary["layers"]["ranks"]["accepted"])
            self.assertEqual(summary["layers"]["ranks"]["opcode"], 1012)
            self.assertGreater(summary["knownFlagDensity"]["abilityRanksKnown_true"], 0)
            self.assertEqual(summary["knownFlagDensity"]["hpKnown_true"], 0)
            self.assertEqual(summary["knownFlagDensity"]["combatStatsKnown_true"], 0)
            self.assertFalse(summary["calculatorReady"])
            self.assertTrue((match_dir / "ranks-evidence.json").is_file())
            self.assertTrue((match_dir / "fuse-summary.json").is_file())
            timeline = json.loads(
                (match_dir / "timeline.g1.product-fuse.json").read_text(encoding="utf-8")
            )
            mid = timeline["frames"][len(timeline["frames"]) // 2]
            for unit in mid["units"]:
                self.assertTrue(unit["abilityRanksKnown"])
                self.assertEqual(
                    unit["abilityRanksSource"],
                    "rofl2_upgrade_spell_ans_1012_first_write",
                )


if __name__ == "__main__":
    unittest.main()
