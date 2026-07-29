#!/usr/bin/env python3
"""Tests for Phase B E3 movement emulator / PathPacket probe."""
from __future__ import annotations

import struct
import sys
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import rofl2_movement_emulator_probe as e3  # noqa: E402


def _encode_simple_path(
    *,
    entity_id: int,
    speed: float,
    waypoints_enc: list[tuple[int, int]],
    optional: bool = False,
) -> bytes:
    """Build a minimal absolute-only PathPacket (all bitmask abs bits)."""
    n = len(waypoints_enc)
    parsing_type = (n << 1) | (1 if optional else 0)
    out = bytearray()
    out += struct.pack("<H", parsing_type)
    out += struct.pack("<I", entity_id)
    out += struct.pack("<f", speed)
    if optional:
        out += b"\x00"
    if n > 1:
        bitmask_len = ((n - 2) >> 2) + 1
        out += bytes(bitmask_len)  # all zeros → absolute for both axes
    for x_enc, z_enc in waypoints_enc:
        out += struct.pack("<HH", x_enc & 0xFFFF, z_enc & 0xFFFF)
    return bytes(out)


class CompressedPathParserTests(unittest.TestCase):
    def test_strict_parser_accepts_full_consume_hero_path(self):
        # Encode ~ (1000, 2000) and (1100, 2100) via inverse transform.
        # x = i16*2 + 7358 → i16 = (x - 7358) / 2
        def enc(x: float, z: float) -> tuple[int, int]:
            return int(round((x - 7358.0) / 2.0)), int(round((z - 7412.0) / 2.0))

        w0 = enc(1000.0, 2000.0)
        w1 = enc(1100.0, 2100.0)
        payload = _encode_simple_path(
            entity_id=0x400000AE,
            speed=325.5,
            waypoints_enc=[w0, w1],
        )
        pp = e3.parse_compressed_path_packet(payload)
        self.assertTrue(pp.full_consume)
        self.assertEqual(pp.entity_id, 0x400000AE)
        self.assertAlmostEqual(pp.speed, 325.5, places=2)
        self.assertEqual(len(pp.waypoints), 2)
        self.assertAlmostEqual(pp.waypoints[0][0], 1000.0, places=0)
        self.assertAlmostEqual(pp.waypoints[0][1], 2000.0, places=0)

    def test_strict_parser_rejects_trailing_bytes(self):
        payload = _encode_simple_path(
            entity_id=0x400000AE,
            speed=300.0,
            waypoints_enc=[(0, 0)],
        ) + b"\xff"
        with self.assertRaises(e3.PathParseError) as cm:
            e3.parse_compressed_path_packet(payload)
        self.assertIn("trailing", str(cm.exception).lower())

    def test_strict_parser_rejects_bad_speed(self):
        payload = _encode_simple_path(
            entity_id=0x400000AE,
            speed=float("nan"),
            waypoints_enc=[(0, 0)],
        )
        with self.assertRaises(e3.PathParseError):
            e3.parse_compressed_path_packet(payload)

    def test_strict_parser_rejects_zero_count(self):
        # parsing_type = 0 → count 0
        payload = struct.pack("<HIf", 0, 0x400000AE, 300.0)
        with self.assertRaises(e3.PathParseError):
            e3.parse_compressed_path_packet(payload)


class PtrBufferScanTests(unittest.TestCase):
    def test_scan_finds_pointer_length_buffer(self):
        heap_base = 0x20000000
        buf = b"\x01\x02\x03\x04" + b"\x00" * 12
        obj = bytearray(64)
        struct.pack_into("<Q", obj, 0x10, heap_base)
        struct.pack_into("<Q", obj, 0x18, len(buf))

        def read_mem(ptr: int, n: int) -> bytes:
            self.assertEqual(ptr, heap_base)
            return buf[:n]

        cands = e3.scan_ptr_len_buffers(
            bytes(obj),
            heap_allocs=[(heap_base, 0x1000)],
            read_mem=read_mem,
            min_size=8,
        )
        self.assertTrue(cands)
        hit = next(c for c in cands if c.get("size") == len(buf))
        self.assertEqual(hit["objOff"], 0x10)
        self.assertEqual(hit["buffer"], buf)

    def test_false_candidate_does_not_path_parse(self):
        """Pointer+len buffer that is not a PathPacket must fail closed."""
        heap_base = 0x20000000
        junk = b"\xaa" * 32
        obj = bytearray(64)
        struct.pack_into("<Q", obj, 0x08, heap_base)
        struct.pack_into("<I", obj, 0x10, len(junk))

        cands = e3.scan_ptr_len_buffers(
            bytes(obj),
            heap_allocs=[(heap_base, 0x100)],
            read_mem=lambda ptr, n: junk[:n],
        )
        self.assertTrue(cands)
        for c in cands:
            with self.assertRaises(e3.PathParseError):
                e3.parse_compressed_path_packet(c["buffer"])


class BrowserRuntimeSeparationTests(unittest.TestCase):
    def test_pure_decoder_config_has_no_emulator_runtime(self):
        cfg = e3.pure_decoder_config()
        self.assertEqual(cfg["decoderVersion"], e3.DECODER_CONFIG_VERSION)
        self.assertFalse(cfg["productEligible"])
        rt = cfg["runtime"]
        self.assertTrue(rt["browserSafe"])
        self.assertFalse(rt["requiresLeagueBinary"])
        self.assertFalse(rt["requiresUnicorn"])
        self.assertIn("Worker", rt["vercelNote"])
        self.assertIn("4.5MB", rt["vercelNote"])
        # Manifest must not embed binary paths or emulator entrypoints.
        blob = str(cfg)
        self.assertNotIn("LeagueofLegends", blob)
        self.assertNotIn("/Applications/", blob)
        self.assertNotIn("DEFAULT_LEAGUE_BINARY", blob)
        self.assertNotIn("create_packet", blob)
        self.assertIn("x0", cfg["coordinates"]["constants"])
        self.assertEqual(cfg["coordinates"]["constants"]["x0"], 7358.0)

    def test_probe_report_keeps_product_false_without_winner(self):
        """When no channel wins, productEligible stays false and pure=false."""
        with mock.patch.object(e3, "_setup_unicorn", side_effect=RuntimeError("skip")):
            with mock.patch.object(
                e3,
                "collect_channel_blocks",
                return_value=(
                    [],
                    {
                        "channel": 351,
                        "channelHex": "0x15f",
                        "heroBlockCount": 0,
                        "payloadSizeHistogram": [],
                        "firstByteHistogram": [],
                        "prefix6HistogramTop": [],
                        "sampleCount": 0,
                        "redactedSamplePrefixes": [],
                    },
                ),
            ):
                report = e3.run_e3_probe(
                    Path("/nonexistent.rofl"),
                    oracle_jsonl=Path("/nonexistent.jsonl"),
                    max_samples=1,
                )
        self.assertFalse(report["productEligible"])
        self.assertFalse(report["pureBrowserDecoderDerived"])
        self.assertFalse(report["winnerFound"])
        self.assertEqual(report["keep"], "discard")
        self.assertIn("pureDecoderConfig", report)
        self.assertTrue(report["pureDecoderConfig"]["runtime"]["browserSafe"])


if __name__ == "__main__":
    unittest.main()
