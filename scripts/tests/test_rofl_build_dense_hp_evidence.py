#!/usr/bin/env python3
"""Unit tests for dense trusted-HP evidence builder."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import rofl_build_dense_hp_evidence as dense  # noqa: E402
from rofl2_packet_decrypt_probe import DecryptError  # noqa: E402


def _template() -> dict:
    return {
        "schema": "rofl-trusted-hp-v1",
        "match": {"matchCode": "3264361042"},
        "identityBinding": {
            "method": "stable_identity_to_net_id",
            "complete": True,
            "participants": [],
        },
        "timing": {"toleranceMs": 500},
        "provenance": {},
        "samples": [],
    }


def _units() -> list:
    return [
        {
            "netId": 0x400000AE + i,
            "mHP": 500.0 + i,
            "mMaxHP": 600.0 + i,
            "mMaxHPExplicit": True,
        }
        for i in range(10)
    ]


class BuildDenseHpEvidenceTests(unittest.TestCase):
    def test_replaces_samples_from_combat_proof(self):
        proof = {
            "combatTrusted": True,
            "wireTableProven": True,
            "timedHpEvidence": {
                "firstAll10HpMs": 77_278,
                "monkeyKingFirstHpMs": 77_278,
                "otherHeroesFirstHpMs": 267,
                "samples": [
                    {"gameTimeMs": 78_000, "units": _units()},
                    {"gameTimeMs": 79_000, "units": _units()},
                ],
            },
        }
        out = dense.build_dense_trusted_hp_evidence(
            template=_template(), combat_proof=proof
        )
        self.assertEqual(len(out["samples"]), 2)
        self.assertTrue(out["provenance"]["hpDensified"])
        self.assertEqual(out["provenance"]["firstAll10HpMs"], 77_278)

    def test_rejects_non_explicit_units(self):
        bad_units = _units()
        bad_units[0]["mMaxHPExplicit"] = False
        proof = {
            "timedHpEvidence": {
                "samples": [
                    {"gameTimeMs": 78_000, "units": bad_units},
                    {"gameTimeMs": 79_000, "units": _units()},
                ]
            }
        }
        with self.assertRaises(DecryptError):
            dense.build_dense_trusted_hp_evidence(
                template=_template(), combat_proof=proof
            )


if __name__ == "__main__":
    unittest.main()
