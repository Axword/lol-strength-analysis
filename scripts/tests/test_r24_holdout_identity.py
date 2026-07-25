#!/usr/bin/env python3
"""R24 P8 H3 — holdout 2970137-g1 identity fail-closed under product_strict."""
from __future__ import annotations

import json
import sys
import unittest
from copy import deepcopy
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
ROOT = SCRIPTS.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from rofl2_packet_decrypt_probe import DecryptError  # noqa: E402
from rofl_fuse_identity import (  # noqa: E402
    assert_identity_match_context,
    assert_product_identity_binding,
    game_info_rows_from_slim_roster,
    identity_join_net_to_champ,
    load_slim_roster_rows,
    order_join_net_to_champ,
    pid_bindings_from_game_info,
    stamp_participant_ids_via_puuid_join,
    winners_net_to_champ,
)

IDENTITY = ROOT / (
    "docs/rofl-research/autoresearch/product_ready/r25/"
    "castspell-identity-2970137-g1.json"
)
DEV_IDENTITY = ROOT / (
    "docs/rofl-research/packet_decode/r32/castspell-identity-2970110-g1.json"
)
SQLITE = ROOT / "artifacts/pro-grid/2970137/timeline.g1.slim.sqlite"


@unittest.skipUnless(IDENTITY.is_file() and SQLITE.is_file(), "2970137 artifacts missing")
class R24HoldoutIdentityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.identity = json.loads(IDENTITY.read_text(encoding="utf-8"))
        self.roster = load_slim_roster_rows(SQLITE)
        self.stamped = stamp_participant_ids_via_puuid_join(
            self.identity, self.roster, join_key="puuid"
        )
        self.winners = winners_net_to_champ(self.identity)

    def test_puuid_stamp_bijection(self) -> None:
        parts = self.stamped["identityBinding"]["participants"]
        self.assertEqual(len(parts), 10)
        self.assertEqual(
            sorted(int(p["participantID"]) for p in parts), list(range(1, 11))
        )
        self.assertFalse(self.stamped["identityBinding"]["createHeroOrderFallback"])
        self.assertEqual(
            self.stamped["identityBinding"]["pidStampMethod"], "slim_roster_puuid_join"
        )
        self.assertFalse(self.stamped.get("productEligible"))
        self.assertFalse(self.stamped.get("calculatorReady"))

    def test_product_strict_match_context(self) -> None:
        assert_product_identity_binding(self.stamped)
        assert_identity_match_context(
            self.stamped, expected_series="2970137", expected_game_index=1
        )
        gi = game_info_rows_from_slim_roster(self.roster, game_id=2970137)
        pid_to_net, _, _ = pid_bindings_from_game_info(
            gi,
            self.stamped,
            product_strict=True,
            expected_series="2970137",
            expected_game_index=1,
            roster_rows=self.roster,
        )
        expected = {
            int(p["participantID"]): int(p["netId"])
            for p in self.stamped["identityBinding"]["participants"]
        }
        self.assertEqual(pid_to_net, expected)

    def test_scramble_stable(self) -> None:
        rev = list(reversed(self.roster))
        self.assertNotEqual(order_join_net_to_champ(self.identity, rev), self.winners)
        self.assertEqual(identity_join_net_to_champ(self.identity, rev), self.winners)

    def test_refuse_2970110_series_as_holdout(self) -> None:
        self.assertTrue(DEV_IDENTITY.is_file())
        dev = json.loads(DEV_IDENTITY.read_text(encoding="utf-8"))
        with self.assertRaises(DecryptError) as ctx:
            assert_identity_match_context(
                dev, expected_series="2970137", expected_game_index=1
            )
        self.assertIn("series", str(ctx.exception))

    def test_refuse_surgical_champ_remap(self) -> None:
        bad = deepcopy(self.stamped)
        bad["identityBinding"]["participants"][0]["champion"] = "Ambessa"
        with self.assertRaises(DecryptError) as ctx:
            stamp_participant_ids_via_puuid_join(bad, self.roster, join_key="puuid")
        msg = str(ctx.exception)
        self.assertTrue("CastSpell champion" in msg or "≠" in msg)

    def test_refuse_create_hero_order_fallback(self) -> None:
        bad = deepcopy(self.stamped)
        bad["identityBinding"]["createHeroOrderFallback"] = True
        with self.assertRaises(DecryptError) as ctx:
            assert_product_identity_binding(bad)
        self.assertIn("createHeroOrderFallback", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
