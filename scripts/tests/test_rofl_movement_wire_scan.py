#!/usr/bin/env python3
"""Tests for Phase B E2 wire-id remap scanner."""
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

import rofl2_movement_decode as mov  # noqa: E402
import rofl2_movement_wire_scan as scan  # noqa: E402


class HungarianAssignmentTests(unittest.TestCase):
    def test_hungarian_prefers_global_optimum_over_greedy(self):
        # Greedy would take (0,0)=1 then be forced into (1,1)=100.
        # Optimal is (0,1)=2 + (1,0)=2 = 4.
        cost = [
            [1.0, 2.0],
            [2.0, 100.0],
        ]
        pairs, total = scan.hungarian_assignment(cost)
        assigned = sorted(pairs)
        self.assertEqual(assigned, [(0, 1), (1, 0)])
        self.assertAlmostEqual(total, 4.0)

    def test_optimal_oracle_assignment_not_product(self):
        oracle = [
            {
                "time": 60.0,
                "participants": [
                    {"participantID": 1, "x": 1000.0, "z": 2000.0},
                    {"participantID": 2, "x": 3000.0, "z": 4000.0},
                ],
            },
            {
                "time": 61.0,
                "participants": [
                    {"participantID": 1, "x": 1010.0, "z": 2010.0},
                    {"participantID": 2, "x": 3010.0, "z": 4010.0},
                ],
            },
        ]
        samples = [
            {"time": 60.0, "netId": 0x40000011, "x": 1002, "z": 1998},
            {"time": 60.05, "netId": 0x40000022, "x": 3005, "z": 4002},
            {"time": 61.0, "netId": 0x40000011, "x": 1012, "z": 2008},
            {"time": 61.0, "netId": 0x40000022, "x": 3012, "z": 4008},
        ]
        report = scan.optimal_oracle_assignment(samples, oracle, tolerance_s=0.5)
        self.assertFalse(report["productEligible"])
        self.assertEqual(report["label"], "research_only_not_product")
        self.assertEqual(report["method"], "hungarian")
        self.assertEqual(report["assignmentCount"], 2)
        self.assertGreaterEqual(report["comparedSamples"], 4)
        self.assertIsNotNone(report["medianError"])
        self.assertLess(float(report["medianError"]), 20.0)


class ScannerRankingTests(unittest.TestCase):
    def test_schema_only_never_accepted(self):
        decode_stats = {
            "successRatio": 0.9,
            "fullConsumeRatio": 0.9,
            "coordPlausibleRatio": 0.9,
            "uniqueNetIds": 10,
            "coordSpan": 5000,
        }
        ranked = scan.rank_channel_candidate(
            channel=556,
            count=30_000,
            decode_stats=decode_stats,
            payload_stats={"n": 30_000, "mean": 20},
            param_pattern={"distinctParams": 10},
            time_min=0.0,
            time_max=1000.0,
            oracle=None,
        )
        self.assertTrue(ranked["schemaOk"])
        self.assertFalse(ranked["accepted"])
        self.assertIn("schema_only_no_oracle", ranked["falsePositiveReasons"])

    def test_crafted_false_positive_fails_oracle_gate(self):
        """Schema-decodable synthetic samples that miss oracle positions."""
        lut, _ = mov.load_generated_lut_cache()
        # Build synthetic "decoded" samples far from oracle.
        samples = []
        for i, nid in enumerate(range(0x40000001, 0x4000000B)):
            for t in (60.0, 61.0, 62.0, 63.0, 64.0):
                samples.append(
                    {
                        "time": t,
                        "netId": nid,
                        "x": 100 + i * 10,
                        "z": 100 + i * 10,
                    }
                )
        # Also verify payloads schema-decode (crafted true schema success).
        payload = mov.encode_minimal_025b(
            net_id=0x40000001, x=150, z=150, lut=lut
        )
        res = mov.decode_025b_payload(payload, time_s=60.0, lut=lut)
        self.assertTrue(res.ok, res.error)

        oracle = []
        for t_ms in range(60_000, 65_000, 1000):
            oracle.append(
                {
                    "time": t_ms / 1000.0,
                    "participants": [
                        {
                            "participantID": pid,
                            "x": 5000.0 + pid * 100,
                            "z": 6000.0 + pid * 100,
                        }
                        for pid in range(1, 11)
                    ],
                }
            )
        oa = scan.optimal_oracle_assignment(samples, oracle, tolerance_s=0.5)
        ranked = scan.rank_channel_candidate(
            channel=999,
            count=20_000,
            decode_stats={
                "successRatio": 0.95,
                "fullConsumeRatio": 0.95,
                "coordPlausibleRatio": 1.0,
                "uniqueNetIds": 10,
                "coordSpan": 2000,
            },
            payload_stats={"n": 20_000},
            param_pattern={"distinctParams": 10},
            time_min=0.0,
            time_max=1200.0,
            oracle=oa,
        )
        self.assertTrue(ranked["schemaOk"])
        self.assertFalse(ranked["oraclePass"])
        self.assertFalse(ranked["accepted"])
        self.assertTrue(
            any(
                r.startswith(("median_error", "p95_error", "max_error", "schema_shaped"))
                for r in ranked["falsePositiveReasons"]
            )
        )

    def test_strong_oracle_can_accept(self):
        samples = []
        for pid in range(1, 11):
            nid = 0x40000000 + pid
            for sec in range(60, 80):
                samples.append(
                    {
                        "time": float(sec),
                        "netId": nid,
                        "x": 1000 + pid * 200,
                        "z": 2000 + pid * 150,
                    }
                )
        oracle = []
        for sec in range(60, 80):
            oracle.append(
                {
                    "time": float(sec),
                    "participants": [
                        {
                            "participantID": pid,
                            "x": float(1000 + pid * 200),
                            "z": float(2000 + pid * 150),
                        }
                        for pid in range(1, 11)
                    ],
                }
            )
        oa = scan.optimal_oracle_assignment(samples, oracle, tolerance_s=0.5)
        ranked = scan.rank_channel_candidate(
            channel=632,
            count=25_000,
            decode_stats={
                "successRatio": 0.8,
                "fullConsumeRatio": 0.75,
                "coordPlausibleRatio": 0.9,
                "uniqueNetIds": 10,
                "coordSpan": 3000,
            },
            payload_stats={"n": 25_000},
            param_pattern={"distinctParams": 10},
            time_min=0.0,
            time_max=1600.0,
            oracle=oa,
        )
        self.assertGreaterEqual(oa["assignmentCount"], 5)
        self.assertGreaterEqual(oa["comparedSamples"], 80)
        self.assertTrue(ranked["oraclePass"])
        self.assertTrue(ranked["accepted"])
        self.assertNotIn("productEligible", ranked)  # ranking dict stays research-scoped
        self.assertFalse(oa["productEligible"])


class BlockParamGroupingTests(unittest.TestCase):
    def test_block_param_grouping_catches_candidate_inner_grouping_misses(self):
        """Regression: noisy decoded inner IDs must not hide a true blockParam track."""
        # 10 stable blockParams with positions matching oracle participants.
        samples = []
        for i, param in enumerate(scan.PROVEN_HERO_NET_IDS):
            pid = i + 1
            for sec in range(60, 90):
                samples.append(
                    {
                        "time": float(sec),
                        "blockParam": param,
                        # Hostile inner IDs: unique per sample → inner grouping explodes.
                        "netId": 0x10000000 + sec * 100 + i,
                        "decodedInnerNetId": 0x10000000 + sec * 100 + i,
                        "x": 1000 + pid * 200,
                        "z": 2000 + pid * 150,
                    }
                )
        oracle = []
        for sec in range(60, 90):
            oracle.append(
                {
                    "time": float(sec),
                    "participants": [
                        {
                            "participantID": pid,
                            "x": float(1000 + pid * 200),
                            "z": float(2000 + pid * 150),
                        }
                        for pid in range(1, 11)
                    ],
                }
            )

        inner = scan.optimal_oracle_assignment(samples, oracle, tolerance_s=0.5)
        by_param = scan.optimal_oracle_assignment_by_block_param(
            samples, oracle, tolerance_s=0.5
        )
        # Inner grouping sees hundreds of IDs → too few comparisons per entity.
        self.assertGreater(inner["uniqueNetIds"], 50)
        self.assertLess(inner["comparedSamples"], 80)
        # blockParam grouping recovers the 10 champions with dense comparisons.
        self.assertEqual(by_param["grouping"], "blockParam")
        self.assertGreaterEqual(by_param["assignmentCount"], 10)
        self.assertGreaterEqual(by_param["comparedSamples"], 80)
        self.assertEqual(by_param["methodPassed"], "raw_decoded_point")
        self.assertFalse(by_param["productEligible"])
        self.assertLess(float(by_param["medianError"]), 5.0)

    def test_hero_params_alone_do_not_accept(self):
        ranked = scan.rank_channel_candidate(
            channel=351,
            count=10_000,
            decode_stats={
                "successRatio": 0.01,
                "fullConsumeRatio": 0.01,
                "coordPlausibleRatio": 0.0,
                "uniqueNetIds": 0,
                "coordSpan": 0,
            },
            payload_stats={"n": 10_000},
            param_pattern={"distinctParams": 10},
            time_min=0.0,
            time_max=1600.0,
            oracle=None,
        )
        self.assertFalse(ranked["accepted"])
        self.assertFalse(ranked["schemaOk"])


if __name__ == "__main__":
    unittest.main()
