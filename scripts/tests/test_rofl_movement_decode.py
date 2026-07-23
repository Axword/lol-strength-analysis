#!/usr/bin/env python3
"""Focused tests for offline 0x025B movement decode (Phase B E0/E1)."""
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

ROFL = Path.home() / "Documents/League of Legends/Replays/BR1-3264361042.rofl"
ORACLE = ROOT / "artifacts/rofl/3264361042/events.rfc461.jsonl"


def _test_lut() -> bytes:
    lut, _prov = mov.load_generated_lut_cache()
    return lut


class CipherPrimitiveTests(unittest.TestCase):
    def test_generated_lut_manifest_sha_matches_constant(self):
        lut, prov = mov.load_generated_lut_cache()
        self.assertEqual(len(lut), 256)
        self.assertIn("generated_cache", prov)
        self.assertEqual(
            __import__("hashlib").sha256(lut).hexdigest(),
            mov.LUT_SHA256,
        )

    def test_bitswap_involution(self):
        for b in range(256):
            self.assertEqual(mov.bitswap(mov.bitswap(b)), b)

    def test_f10_cipher_known_vector(self):
        # Independent vector: plaintext byte 0x00 → sub 0x62 → 0x9E → bitswap → add 7
        ciphers = mov.make_ciphers(_test_lut())
        _t, f10 = ciphers[10]
        # Derive expected by applying the documented recipe once.
        b = 0x11
        expected = (mov.bitswap((b - 0x62) & 0xFF) + 7) & 0xFF
        self.assertEqual(f10(b), expected)

    def test_cipher_permutation_invertible(self):
        ciphers = mov.make_ciphers(_test_lut())
        for fnum, (_rtype, cipher) in ciphers.items():
            inv = mov.invert_cipher(cipher)
            for b in (0, 1, 0x62, 0x7F, 0x80, 0xFF):
                self.assertEqual(inv(cipher(b)), b, msg=f"f{fnum}")

    def test_load_lut_prefers_binary_or_generated_cache(self):
        lut, prov = mov.load_lut(None)
        self.assertEqual(len(lut), 256)
        self.assertEqual(__import__("hashlib").sha256(lut).hexdigest(), mov.LUT_SHA256)
        self.assertTrue(
            prov.startswith("league_binary:") or prov.startswith("generated_cache:")
        )


class SchemaVarintTests(unittest.TestCase):
    def test_pack_unpack_xz(self):
        packed = mov.pack_xz(1234, 5678)
        self.assertEqual(mov.unpack_xz(packed), (1234, 5678))

    def test_varint_underflow(self):
        ciphers = mov.make_ciphers(_test_lut())
        with self.assertRaises(mov.MovementDecodeError):
            mov.read_varint(b"", 0, ciphers[4][1])

    def test_decode_underflow_short_payload(self):
        res = mov.decode_025b_payload(b"\x00\x01", time_s=1.0, lut=_test_lut())
        self.assertFalse(res.ok)
        self.assertIn("shorter", res.error or "")

    def test_synthetic_roundtrip(self):
        lut = _test_lut()
        payload = mov.encode_minimal_025b(
            net_id=0x40000001,
            x=3500,
            z=9200,
            lut=lut,
            state=3,
            sequence=9,
            speed=325.5,
        )
        res = mov.decode_025b_payload(payload, time_s=12.5, lut=lut)
        self.assertTrue(res.ok, res.error)
        assert res.sample is not None
        self.assertEqual(res.sample.net_id, 0x40000001)
        self.assertEqual(res.sample.x, 3500)
        self.assertEqual(res.sample.z, 9200)
        self.assertEqual(res.sample.state, 3)
        self.assertEqual(res.sample.sequence, 9)
        self.assertAlmostEqual(res.sample.speed or 0.0, 325.5, places=2)
        self.assertTrue(res.sample.as_dict()["nativePointSample"])

    def test_trailing_bytes_fail_closed(self):
        lut = _test_lut()
        payload = mov.encode_minimal_025b(net_id=0x40000002, x=100, z=200, lut=lut)
        res = mov.decode_025b_payload(payload + b"\x00\x00", time_s=1.0, lut=lut)
        self.assertFalse(res.ok)
        self.assertIn("trailing", res.error or "")

    def test_invalid_netid_zero(self):
        lut = _test_lut()
        payload = mov.encode_minimal_025b(net_id=0, x=100, z=200, lut=lut)
        res = mov.decode_025b_payload(payload, time_s=1.0, lut=lut)
        self.assertFalse(res.ok)
        self.assertIn("netId", res.error or "")


class MakneeProvenanceTests(unittest.TestCase):
    def test_maknee_events_are_point_samples(self):
        events = mov.samples_to_maknee_events(
            [{"time": 1.0, "netId": 0x40000001, "x": 1, "z": 2}],
            game_version="16.14.794.5912",
        )
        self.assertEqual(events["provenance"], mov.PROVENANCE)
        self.assertFalse(events["nativeMultiWaypoint"])
        self.assertEqual(events["kind"], "position_samples")
        self.assertFalse(events["productEligible"])
        wg = events["events"][0]["WaypointGroup"]
        self.assertTrue(wg["nativePointSample"])
        self.assertEqual(len(wg["waypoints"]["1073741825"]), 1)


class OracleAssignmentTests(unittest.TestCase):
    def test_oracle_assignment_cannot_be_product(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "oracle.jsonl"
            # Minimal synthetic oracle frame at t=60s
            row = {
                "rfc461Schema": "stats_update",
                "gameTime": 60000,
                "participants": [
                    {"participantID": 1, "position": {"x": 1000.0, "z": 2000.0}},
                    {"participantID": 2, "position": {"x": 3000.0, "z": 4000.0}},
                ],
            }
            path.write_text(json.dumps(row) + "\n", encoding="utf-8")
            samples = [
                {"time": 60.0, "netId": 0x40000011, "x": 1005, "z": 1990},
                {"time": 60.0, "netId": 0x40000022, "x": 3010, "z": 3995},
            ]
            report = mov.research_oracle_assignment(samples, path, tolerance_s=0.75)
            self.assertFalse(report["productEligible"])
            self.assertEqual(report["label"], "research_only_not_product")
            self.assertIn("do not use as product", report["note"])
            self.assertGreaterEqual(report["assignmentCount"], 1)


class InventoryTimingTests(unittest.TestCase):
    def test_inventory_reports_timing_and_025b(self):
        if not ROFL.is_file():
            self.skipTest("BR1-3264361042.rofl not present")
        # Bound to early window for speed in CI-like local runs
        report = mov.inventory_rofl(ROFL, max_time_s=60.0)
        self.assertTrue(report["ok"])
        self.assertIn("timingMs", report)
        self.assertGreater(report["packetCount"], 0)
        self.assertFalse(report["productEligible"])
        self.assertIn("movement025bCount", report)
        # Empirical on this match under current framing: absent.
        self.assertEqual(report["movement025bCount"], 0)

    def test_lut_from_binary_when_present(self):
        if not mov.DEFAULT_LEAGUE_BINARY.is_file():
            self.skipTest("League binary not installed")
        lut, prov = mov.load_lut(mov.DEFAULT_LEAGUE_BINARY)
        cached, _ = mov.load_generated_lut_cache()
        self.assertEqual(len(lut), 256)
        self.assertIn("league_binary", prov)
        self.assertEqual(lut, cached)


if __name__ == "__main__":
    unittest.main()
