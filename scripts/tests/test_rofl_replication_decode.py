#!/usr/bin/env python3
"""Tests for replication decode + maknee emit (fail-closed HP)."""
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

import rofl2_replication_decode as decode  # noqa: E402
from rofl2_unicorn_packet_drive import REPLICATION_TYPE_CANDIDATE, extract_blocks_py  # noqa: E402
from rofl2_probe import extract_segments, parse_rofl2  # noqa: E402

ROFL = Path.home() / "Documents/League of Legends/Replays/BR1-3264361042.rofl"
BINARY = decode.DEFAULT_LEAGUE_BINARY


class AcceptanceTests(unittest.TestCase):
    def test_rejects_short_or_invalid(self):
        acc = decode.acceptance_heroes(
            [{"netId": 1, "mHP": 100, "mMaxHP": 50}], need=10
        )
        self.assertFalse(acc["passed"])
        acc2 = decode.acceptance_heroes(
            [{"netId": i, "mHP": 500, "mMaxHP": 1000} for i in range(10)],
            need=10,
        )
        self.assertTrue(acc2["passed"])

    def test_maknee_events_shape(self):
        heroes = [
            {"netId": 1073741857, "mHP": 700.0, "mMaxHP": 800.0, "time": 12.5}
            for _ in range(10)
        ]
        heroes = [
            {**heroes[0], "netId": 1073741857 + i} for i in range(10)
        ]
        ev = decode.maknee_replication_events(time_s=12.5, heroes=heroes)
        self.assertEqual(len(ev), 20)  # mHP + mMaxHP each
        rep = ev[0]["Replication"]
        self.assertIn("net_id_to_replication_datas", rep)
        entry = next(iter(rep["net_id_to_replication_datas"].values()))
        self.assertEqual(entry["primary_index"], 5)
        self.assertEqual(entry["name"], "mHP")


class FramingReplicationTests(unittest.TestCase):
    def test_type_107_present_in_mid_chunk(self):
        if not ROFL.is_file():
            self.skipTest("BR1 ROFL not present")
        chunks = [
            s
            for s in extract_segments(parse_rofl2(ROFL)["payload"])["segments"]
            if s.get("type") == 1
        ]
        body = chunks[len(chunks) // 2]["bytes"]
        blocks = extract_blocks_py(body, max_blocks=2000)
        n107 = sum(1 for b in blocks if b["channel"] == REPLICATION_TYPE_CANDIDATE)
        self.assertGreaterEqual(n107, 1)
        self.assertEqual(REPLICATION_TYPE_CANDIDATE, 107)


class DecodeDriveTests(unittest.TestCase):
    def test_decode_fail_closed_without_full_acceptance(self):
        if not BINARY.is_file():
            self.skipTest("League binary not installed")
        if not ROFL.is_file():
            self.skipTest("BR1 ROFL not present")
        # Single mid chunk with a low block cap: may find HP but must not invent
        # a full 10-hero acceptance without explicit mMaxHP coverage.
        report = decode.decode_rofl_replication(
            rofl=ROFL,
            league_binary=BINARY,
            work_dir=Path("/tmp/lol-repl-decode-test"),
            max_blocks=80,
            max_chunks=1,
            chunk_index=27,
        )
        self.assertEqual(report.get("events") or [], [])
        self.assertFalse(report.get("ok"))
        self.assertIn(
            report["decryptStatus"],
            {
                "replication_use_map_stubbed",
                "replication_hp_rejected_fail_closed",
                "block_framing_ok_no_replication_in_chunk",
                "replication_deserialized_need_use_handler",
            },
        )
        self.assertTrue((report.get("useReplication") or {}).get("prologueOk"))
        self.assertEqual((report.get("useReplication") or {}).get("va"), "0x100785924")

    def test_decode_emits_when_heroes_accepted(self):
        if not BINARY.is_file():
            self.skipTest("League binary not installed")
        if not ROFL.is_file():
            self.skipTest("BR1 ROFL not present")
        heroes = [
            {
                "netId": 1073741857 + i,
                "mHP": 600.0 + i,
                "mMaxHP": 900.0,
                "time": 600.0,
            }
            for i in range(10)
        ]
        report = decode.decode_rofl_replication(
            rofl=ROFL,
            league_binary=BINARY,
            work_dir=Path("/tmp/lol-repl-decode-test"),
            max_blocks=120,
            heroes=heroes,
        )
        self.assertTrue(report["ok"])
        self.assertEqual(report["decryptStatus"], "replication_hp_accepted")
        self.assertEqual(len(report["events"]), 20)
        # Round-trip through emitter file shape
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "heroes.json"
            p.write_text(json.dumps({"heroes": heroes}), encoding="utf-8")
            report2 = decode.decode_rofl_replication(
                rofl=ROFL,
                league_binary=BINARY,
                work_dir=Path("/tmp/lol-repl-decode-test"),
                max_blocks=80,
                heroes=json.loads(p.read_text())["heroes"],
            )
            self.assertTrue(report2["ok"])


if __name__ == "__main__":
    unittest.main()
