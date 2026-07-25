#!/usr/bin/env python3
"""R22 P8 H1 — PUUID pid stamp + fuse consumer (no CreateHero order)."""
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
    game_info_rows_from_slim_roster,
    load_slim_roster_rows,
    pid_bindings_from_game_info,
    stamp_participant_ids_via_puuid_join,
)

IDENTITY = ROOT / (
    "docs/rofl-research/packet_decode/r32/castspell-identity-2970110-g1.json"
)
SQLITE = ROOT / "artifacts/pro-grid/2970110/timeline.g1.slim.sqlite"


@unittest.skipUnless(IDENTITY.is_file() and SQLITE.is_file(), "2970110 artifacts missing")
class R22PidStampPuuidTests(unittest.TestCase):
    def setUp(self) -> None:
        self.identity = json.loads(IDENTITY.read_text(encoding="utf-8"))
        self.roster = load_slim_roster_rows(SQLITE)

    def test_stamp_10_of_10_puuid_bijection(self) -> None:
        stamped = stamp_participant_ids_via_puuid_join(
            self.identity, self.roster, join_key="puuid"
        )
        parts = stamped["identityBinding"]["participants"]
        self.assertEqual(len(parts), 10)
        pids = sorted(int(p["participantID"]) for p in parts)
        self.assertEqual(pids, list(range(1, 11)))
        self.assertFalse(stamped["identityBinding"]["createHeroOrderFallback"])
        self.assertEqual(
            stamped["identityBinding"]["pidStampMethod"], "slim_roster_puuid_join"
        )
        self.assertTrue(stamped["identityPidComplete"])
        self.assertFalse(stamped["calculatorReady"])
        self.assertFalse(stamped["productEligible"])

    def test_scramble_roster_order_stable(self) -> None:
        a = stamp_participant_ids_via_puuid_join(
            self.identity, self.roster, join_key="puuid"
        )
        scrambled = list(reversed(self.roster))
        b = stamp_participant_ids_via_puuid_join(
            self.identity, scrambled, join_key="puuid"
        )
        map_a = {
            int(p["netId"]): int(p["participantID"])
            for p in a["identityBinding"]["participants"]
        }
        map_b = {
            int(p["netId"]): int(p["participantID"])
            for p in b["identityBinding"]["participants"]
        }
        self.assertEqual(map_a, map_b)

    def test_ignores_create_hero_events(self) -> None:
        wiped = deepcopy(self.identity)
        wiped["createHeroEvents"] = []
        stamped = stamp_participant_ids_via_puuid_join(
            wiped, self.roster, join_key="puuid"
        )
        self.assertEqual(
            len(stamped["identityBinding"]["participants"]),
            10,
        )
        self.assertTrue(
            all(
                p.get("participantID") is not None
                for p in stamped["identityBinding"]["participants"]
            )
        )

    def test_refuse_duplicate_puuid(self) -> None:
        bad = deepcopy(self.roster)
        bad[1]["puuid"] = bad[0]["puuid"]
        with self.assertRaises(DecryptError):
            stamp_participant_ids_via_puuid_join(
                self.identity, bad, join_key="puuid"
            )

    def test_fuse_game_info_with_scrambled_champ_names(self) -> None:
        stamped = stamp_participant_ids_via_puuid_join(
            self.identity, self.roster, join_key="puuid"
        )
        gi = game_info_rows_from_slim_roster(self.roster, game_id=2970110)
        for p in gi[0]["participants"]:
            p["championName"] = "Sona"
        pid_to_net, labels, _ = pid_bindings_from_game_info(
            gi, stamped, allow_champion_fallback=False
        )
        self.assertEqual(len(pid_to_net), 10)
        # Labels come from CastSpell bind, not scrambled Sona.
        self.assertNotEqual(labels[1]["championName"], "Sona")
        expected = {
            int(p["participantID"]): int(p["netId"])
            for p in stamped["identityBinding"]["participants"]
        }
        self.assertEqual(pid_to_net, expected)


if __name__ == "__main__":
    unittest.main()
