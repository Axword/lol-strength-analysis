#!/usr/bin/env python3
"""Tests for Unicorn Packet::Packet drive (factory smoke + type reader)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
ROOT = SCRIPTS.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import rofl2_unicorn_packet_drive as drive  # noqa: E402

ROFL = Path.home() / "Documents/League of Legends/Replays/BR1-3264383283.rofl"
BINARY = drive.DEFAULT_LEAGUE_BINARY


class TypeReaderTests(unittest.TestCase):
    def test_threshold_for_runtime_global(self):
        self.assertEqual(drive.type_threshold(0x55D), 251)

    def test_single_and_two_byte_types(self):
        thr = 251
        # single-byte
        typ, i = drive.read_packet_type_py(bytes([100, 1, 2]), 0, 3, threshold=thr)
        self.assertEqual(typ, 100)
        self.assertEqual(i, 1)
        # two-byte: first >= threshold
        typ, i = drive.read_packet_type_py(bytes([251, 5]), 0, 2, threshold=thr)
        self.assertEqual(typ, 251 + 0 + 5)
        self.assertEqual(i, 2)


class BlockFramingTests(unittest.TestCase):
    def test_extract_blocks_py_on_mid_chunk(self):
        if not ROFL.is_file():
            self.skipTest("BR1 ROFL not present")
        from rofl2_probe import extract_segments, parse_rofl2

        chunks = [
            s
            for s in extract_segments(parse_rofl2(ROFL)["payload"])["segments"]
            if s.get("type") == 1
        ]
        self.assertGreater(len(chunks), 10)
        body = chunks[len(chunks) // 2]["bytes"]
        blocks = drive.extract_blocks_py(body, max_blocks=64)
        self.assertGreaterEqual(len(blocks), 16)
        # First block absolute time matches plaintext float at body[1:5]
        import struct

        t0 = struct.unpack_from("<f", body, 1)[0]
        self.assertAlmostEqual(blocks[0]["time"], t0, places=3)
        # Times are non-decreasing across relative deltas
        times = [b["time"] for b in blocks]
        self.assertEqual(times, sorted(times))


class PacketFactoryDriveTests(unittest.TestCase):
    def test_factory_creates_packets_when_binary_and_rofl_present(self):
        if not BINARY.is_file():
            self.skipTest("League binary not installed")
        if not ROFL.is_file():
            self.skipTest("BR1 ROFL not present")
        report = drive.drive_rofl(
            rofl=ROFL,
            league_binary=BINARY,
            work_dir=Path("/tmp/lol-unicorn-pkt-test"),
            max_packets=24,
            max_blocks=64,
        )
        self.assertFalse(report["ok"])  # no HP yet
        self.assertGreaterEqual(report.get("createsOk") or 0, 3)
        self.assertIn(
            report["decryptStatus"],
            {
                "packet_factory_driven_need_stream_sync",
                "block_framing_synced_need_replication_fields",
                "block_framing_synced_packets_deserialized",
                "replication_candidate_deserialized_need_field_getters",
                # legacy statuses kept for older reports
                "packet_deserialize_partial",
                "packet_stream_driven_need_replication_fields",
                "packet_factory_ready_need_stream_sync",
            },
        )
        bf = report.get("blockFraming") or {}
        self.assertGreaterEqual(bf.get("unicornBlocks") or 0, 8)
        self.assertTrue(bf.get("channelMatch"))
        des = report.get("deserialize") or {}
        self.assertGreaterEqual(des.get("okCount") or 0, 1)
        smoke = report.get("createSmoke") or []
        self.assertTrue(any(c.get("packet") and c.get("deserialize") for c in smoke))
        # Stored type matches request for a simple case
        t2 = next(c for c in smoke if c.get("type") == 2)
        self.assertEqual(t2.get("storedType"), 2)


if __name__ == "__main__":
    unittest.main()
