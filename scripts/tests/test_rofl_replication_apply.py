#!/usr/bin/env python3
"""Unit tests for replication apply + USE_REPLICATION VA."""
from __future__ import annotations

import struct
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from rofl_replication_apply import (  # noqa: E402
    USE_REPLICATION,
    acceptance_snapshot,
    apply_vector_blob,
    is_valid_use_replication_prologue,
    parse_replication_vector,
)
import rofl2_accessor_spike as spike  # noqa: E402

BINARY = spike.DEFAULT_UNIVERSAL_BINARY
THIN = Path("/tmp/lol-repl-fullvec/LeagueofLegends.arm64")


class VectorParseTests(unittest.TestCase):
    def test_small_hp_blob(self):
        blob = bytes.fromhex("20b30000400100000004534ab044")
        units = parse_replication_vector(blob)
        self.assertEqual(len(units), 1)
        nid, fields = units[0]
        self.assertEqual(nid, 0x400000B3)
        self.assertIn((5, 0), fields)
        self.assertGreater(fields[(5, 0)], 1000)
        self.assertLess(fields[(5, 0)], 2000)

    def test_apply_requires_explicit_max(self):
        state = {}
        # HP only — must not accept
        apply_vector_blob(
            state,
            bytes.fromhex("20b30000400100000004534ab044"),
            time_s=10.0,
        )
        snap = acceptance_snapshot(state, need=1)
        self.assertFalse(snap["passed"])
        # Add explicit max via synthetic second apply with (5,1)
        # Build: primary 0x20, net 0x400000b3, secondary bit1, len4, float 1500
        mx = struct.pack("<f", 1500.0)
        blob = bytes([0x20]) + struct.pack("<I", 0x400000B3) + struct.pack("<I", 0x2) + bytes([4]) + mx
        apply_vector_blob(state, blob, time_s=10.1)
        snap2 = acceptance_snapshot(state, need=1)
        self.assertTrue(snap2["passed"])


class UseReplicationVaTests(unittest.TestCase):
    def test_prologue_is_real_bl_target(self):
        if not BINARY.is_file():
            self.skipTest("League binary missing")
        path = THIN if THIN.is_file() else Path("/tmp/lol-use-va-test") / "LeagueofLegends.arm64"
        if not path.is_file():
            path.parent.mkdir(parents=True, exist_ok=True)
            spike.thin_arm64(BINARY, path)
        data = path.read_bytes()
        segs = spike._parse_segments(data)
        text = next(s for s in segs if s[0] == "__TEXT")
        self.assertTrue(
            is_valid_use_replication_prologue(data, text_vm=text[1], text_off=text[3])
        )
        self.assertEqual(USE_REPLICATION, 0x100785924)


if __name__ == "__main__":
    unittest.main()
