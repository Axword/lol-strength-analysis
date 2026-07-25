#!/usr/bin/env python3
"""R23 P8 H2 — fail-closed product identity + scramble suite."""
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
    apply_roster_labels,
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
    "docs/rofl-research/packet_decode/r32/castspell-identity-2970110-g1.json"
)
SQLITE = ROOT / "artifacts/pro-grid/2970110/timeline.g1.slim.sqlite"


@unittest.skipUnless(IDENTITY.is_file() and SQLITE.is_file(), "2970110 artifacts missing")
class R23FailClosedIdentityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.identity = json.loads(IDENTITY.read_text(encoding="utf-8"))
        self.roster = load_slim_roster_rows(SQLITE)
        self.stamped = stamp_participant_ids_via_puuid_join(
            self.identity, self.roster, join_key="puuid"
        )
        self.winners = winners_net_to_champ(self.identity)

    def test_product_default_refuses_champ_fallback(self) -> None:
        gi = game_info_rows_from_slim_roster(self.roster, game_id=2970110)
        bad = deepcopy(gi)
        bad[0]["participants"][0]["puuid"] = ""
        bad[0]["participants"][0]["summonerName"] = ""
        bad[0]["participants"][0]["championName"] = "Ambessa"
        with self.assertRaises(DecryptError):
            pid_bindings_from_game_info(bad, self.stamped)

    def test_order_join_scrambles_under_reverse(self) -> None:
        rev = list(reversed(self.roster))
        order_map = order_join_net_to_champ(self.identity, rev)
        id_map = identity_join_net_to_champ(self.identity, rev)
        self.assertNotEqual(order_map, self.winners)
        self.assertEqual(id_map, self.winners)

    def test_liveclient_presentation_scramble(self) -> None:
        order = [0, 5, 1, 6, 2, 7, 3, 8, 4, 9]
        perm = [self.roster[i] for i in order]
        order_map = order_join_net_to_champ(self.identity, perm)
        id_map = identity_join_net_to_champ(self.identity, perm)
        self.assertNotEqual(order_map, self.winners)
        self.assertEqual(id_map, self.winners)

    def test_refuse_create_hero_order_fallback_for_product(self) -> None:
        bad = deepcopy(self.stamped)
        bad["identityBinding"]["createHeroOrderFallback"] = True
        with self.assertRaises(DecryptError) as ctx:
            assert_product_identity_binding(bad)
        self.assertIn("createHeroOrderFallback", str(ctx.exception))

    def test_product_eligible_requires_create_hero_false(self) -> None:
        bad = deepcopy(self.stamped)
        bad["productEligible"] = True
        bad["identityBinding"].pop("createHeroOrderFallback", None)
        with self.assertRaises(DecryptError) as ctx:
            assert_product_identity_binding(bad)
        self.assertIn("productEligible", str(ctx.exception))

    def test_label_rewrite_scrambled_champ_names(self) -> None:
        gi = game_info_rows_from_slim_roster(self.roster, game_id=2970110)
        for p in gi[0]["participants"]:
            p["championName"] = "Sona"
        pid_to_net, labels, _ = pid_bindings_from_game_info(gi, self.stamped)
        expected = {
            int(p["participantID"]): (int(p["netId"]), p["champion"])
            for p in self.stamped["identityBinding"]["participants"]
        }
        for pid, (net, champ) in expected.items():
            self.assertEqual(pid_to_net[pid], net)
            rewritten = apply_roster_labels(
                {"participantID": pid, "championName": "Sona"}, labels[pid]
            )
            self.assertEqual(rewritten["championName"], champ)
            self.assertNotEqual(rewritten["championName"], "Sona")

    def test_create_hero_order_fallback_stays_false_on_stamp(self) -> None:
        self.assertFalse(
            self.stamped["identityBinding"]["createHeroOrderFallback"]
        )
        self.assertFalse(self.stamped["createHeroOrderFallback"])
        self.assertFalse(self.stamped["productEligible"])
        self.assertFalse(self.stamped["calculatorReady"])


if __name__ == "__main__":
    unittest.main()
