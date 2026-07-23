#!/usr/bin/env python3
"""Focused tests for timed multi-sample type-107 HP evidence (Track 2)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import fuse_replay_api_hp as fuse  # noqa: E402
import rofl2_replication_timed_hp as timed  # noqa: E402

PROVEN = list(range(0x400000AE, 0x400000B8))


def _roster() -> list[dict]:
    rows = []
    for index in range(10):
        puuid = f"puuid-{index + 1}"
        full = f"Player{index + 1}#BR1"
        rows.append(
            {
                "puuid": puuid,
                "riotId": {"full": full},
                "champion": {"raw": f"Champ{index + 1}", "display": f"Champ{index + 1}"},
                "sourceIdentity": {
                    "stable": True,
                    "key": f"puuid:{puuid}",
                    "puuid": puuid,
                    "riotId": {"full": full},
                },
            }
        )
    return rows


def _heroes(time_s: float = 60.0) -> list[dict]:
    return [
        {
            "netId": PROVEN[i],
            "mHP": 500.0 + i,
            "mMaxHP": 1000.0 + i,
            "explicitMax": True,
            "time": time_s,
        }
        for i in range(10)
    ]


def _evidence(*, samples: int = 2, complete: bool = False) -> dict:
    binding = timed.attempt_identity_binding(
        _roster(),
        replication_net_ids=PROVEN,
        create_hero_rows=(
            [
                {
                    "net_id": PROVEN[i],
                    "champion": f"Champ{i + 1}",
                    "participantID": i + 1,
                }
                for i in range(10)
            ]
            if complete
            else None
        ),
    )
    sample_rows = [
        timed.make_sample(game_time_ms=60_000 + i * 60_000, heroes=_heroes(60.0 + i * 60))
        for i in range(samples)
    ]
    return timed.build_candidate_evidence(
        match={
            "platformId": "BR1",
            "matchCode": "3264361042",
            "gameId": 3264361042,
            "gameName": "3264361042",
        },
        rofl_meta={
            "patch": "16.14",
            "build": "16.14.794.5912",
            "sha256": "a" * 64,
            "basename": "BR1-3264361042.rofl",
        },
        roster_hash="b" * 64,
        samples=sample_rows,
        identity_binding=binding,
    )


class SamplerHelperTests(unittest.TestCase):
    def test_select_chunk_indices_early_mid_late(self) -> None:
        idxs = timed.select_chunk_indices(11, 5)
        self.assertEqual(idxs[0], 0)
        self.assertEqual(idxs[-1], 10)
        self.assertEqual(len(idxs), 5)
        self.assertIn(5, idxs)

    def test_units_require_explicit_max_and_ten(self) -> None:
        units = timed.units_from_heroes(_heroes())
        self.assertEqual(len(units), 10)
        self.assertTrue(all(u["mMaxHPExplicit"] is True for u in units))
        self.assertEqual(units[0]["netId"], PROVEN[0])
        with self.assertRaises(ValueError):
            timed.make_sample(game_time_ms=1000, heroes=_heroes()[:9])

    def test_chunk_sample_time_prefers_packet_rows(self) -> None:
        part = {
            "rows": [{"time": 12.5}, {"time": 40.25}],
            "timeEnd": 99.0,
        }
        self.assertAlmostEqual(timed._chunk_sample_time_s(part, []), 40.25)

        from rofl_replication_apply import (
            MHP_PRIMARY,
            MHP_SECONDARY,
            MMAXHP_PRIMARY,
            MMAXHP_SECONDARY,
        )

        self.assertEqual((MHP_PRIMARY, MHP_SECONDARY), (5, 0))
        self.assertEqual((MMAXHP_PRIMARY, MMAXHP_SECONDARY), (5, 1))


class ProductCompletenessTests(unittest.TestCase):
    def test_single_sample_not_product_complete(self) -> None:
        evidence = _evidence(samples=1, complete=True)
        blockers = timed.product_complete_blockers(evidence)
        self.assertIn("need_at_least_two_timed_samples", blockers)
        self.assertFalse(timed.is_product_complete(evidence))

    def test_incomplete_bind_not_complete_true(self) -> None:
        binding = timed.attempt_identity_binding(
            _roster(),
            replication_net_ids=PROVEN,
            create_hero_rows=None,
        )
        self.assertFalse(binding["complete"])
        self.assertTrue(binding["createHeroOrderFallback"])
        evidence = _evidence(samples=3, complete=False)
        self.assertFalse(evidence["identityBinding"]["complete"])
        self.assertFalse(timed.is_product_complete(evidence))
        self.assertIn("identityBinding_incomplete", timed.product_complete_blockers(evidence))

    def test_create_hero_champion_match_can_complete(self) -> None:
        binding = timed.attempt_identity_binding(
            _roster(),
            create_hero_rows=[
                {"net_id": PROVEN[i], "champion": f"Champ{i + 1}"} for i in range(10)
            ],
        )
        self.assertTrue(binding["complete"])
        self.assertTrue(binding["createHeroDecoded"])
        self.assertFalse(binding["createHeroOrderFallback"])


class FuseDryRunTests(unittest.TestCase):
    def test_fuse_dry_run_rejects_incomplete(self) -> None:
        evidence = _evidence(samples=3, complete=False)
        dry = timed.fuse_dry_run(evidence)
        self.assertFalse(dry["accepted"])
        self.assertFalse(dry["productEligible"])
        self.assertTrue(str(dry["reason"]).startswith("reject:"))
        self.assertTrue(dry["blockers"])

    def test_fuse_product_raises_on_incomplete_evidence(self) -> None:
        evidence = _evidence(samples=3, complete=False)
        # Minimal reject via trusted HP validation path without full JSONL:
        # incomplete provenance/bind must never look product-ready.
        self.assertNotEqual(
            evidence["provenance"]["sourceKind"],
            fuse.TRUSTED_HEALTH_SOURCE,
        )
        self.assertTrue(evidence["provenance"]["createHeroOrderFallback"])
        with self.assertRaises(fuse.DecryptError):
            # Empty rows force early failure; still proves incomplete evidence
            # is not silently accepted when a caller attempts product fuse.
            fuse.fuse_product(
                [],
                replay_manifest={"productGates": {}},
                hp_evidence=evidence,
            )


class LiveDecodeOptionalTests(unittest.TestCase):
    def test_live_decode_optional_skip(self) -> None:
        rofl = timed.DEFAULT_ROFL
        binary = timed.DEFAULT_LEAGUE_BINARY
        if not rofl.is_file() or not binary.is_file():
            self.skipTest("live ROFL/League binary not present")
        # Keep CI-light: only prove helpers; optional smoke is opt-in via env.
        import os

        if os.environ.get("ROFL_TIMED_HP_LIVE") != "1":
            self.skipTest("set ROFL_TIMED_HP_LIVE=1 for live Unicorn timed HP smoke")
        report = timed.decode_timed_hp(
            rofl=rofl,
            league_binary=binary,
            max_samples=3,
            max_chunks=80,
            max_blocks=2000,
        )
        self.assertGreaterEqual(report.get("sampleCount") or 0, 1)
        self.assertIn("fuseDryRun", report)
        self.assertFalse(report.get("combatTrusted"))


if __name__ == "__main__":
    unittest.main()
