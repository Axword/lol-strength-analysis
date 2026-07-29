#!/usr/bin/env python3
"""Unit tests for CastSpellAns level/slot structural probe helpers."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import rofl2_castspell_level_slot_probe as probe  # noqa: E402


class CastSpellLevelSlotHelpers(unittest.TestCase):
    def test_ability_slot_from_suffix(self):
        names = ["Yasuo", "MonkeyKing", "Leblanc"]
        self.assertEqual(probe._ability_slot("YasuoQ", names), 0)
        self.assertEqual(probe._ability_slot("YasuoW", names), 1)
        self.assertEqual(probe._ability_slot("YasuoE", names), 2)
        self.assertEqual(probe._ability_slot("YasuoR", names), 3)
        self.assertIsNone(probe._ability_slot("Yasuo", names))
        self.assertEqual(probe._ability_slot("WukongQ", names), 0)

    def test_scan_int_candidates_ranges(self):
        obj = bytearray(32)
        obj[4] = 2  # slot-like
        obj[8] = 3  # level-like and slot-like
        cands = probe._scan_int_candidates(bytes(obj))
        self.assertTrue(any(r["offset"] == 4 and r["value"] == 2 for r in cands["u8SlotLike"]))
        self.assertTrue(any(r["offset"] == 8 and r["value"] == 3 for r in cands["u8LevelLike"]))


if __name__ == "__main__":
    unittest.main()
