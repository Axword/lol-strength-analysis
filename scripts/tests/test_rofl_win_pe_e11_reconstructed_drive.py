#!/usr/bin/env python3
"""E11 tests: framing encode, raw-vs-recon consume delta, axis-swap, gates, false match."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from rofl2_unicorn_packet_drive import TYPE_COUNT_VALUE, type_threshold  # noqa: E402
from rofl2_win_pe_e11_reconstructed_drive import (  # noqa: E402
    ACCEPT_MAX_MAX,
    ACCEPT_MAX_MEDIAN,
    ACCEPT_MAX_P95,
    ACCEPT_MIN_HEROES,
    ACCEPT_MIN_SAMPLES,
    OPCODE_DIRECT_INPUT,
    OPCODE_SET_MOVEMENT_DRIVER,
    _score_errs,
    bit_header_for_opcode,
    classify_blocker,
    deserialize_body,
    encode_type,
    qa_samples,
    reconstruct_buffer,
    train_holdout_qa,
)


class FramingEncodeTests(unittest.TestCase):
    def test_encode_type_single_byte_under_threshold(self):
        thr = type_threshold(TYPE_COUNT_VALUE)
        self.assertLess(OPCODE_DIRECT_INPUT, thr)
        self.assertEqual(encode_type(OPCODE_DIRECT_INPUT), bytes([OPCODE_DIRECT_INPUT]))

    def test_encode_type_multibyte_above_threshold(self):
        thr = type_threshold(TYPE_COUNT_VALUE)
        self.assertGreaterEqual(OPCODE_SET_MOVEMENT_DRIVER, thr)
        enc = encode_type(OPCODE_SET_MOVEMENT_DRIVER)
        self.assertEqual(len(enc), 2)
        # Inverse of read_packet_type
        first, second = enc[0], enc[1]
        typ = thr + (((first - thr) & 0xFF) << 8) + second
        self.assertEqual(typ & 0xFFFF, OPCODE_SET_MOVEMENT_DRIVER)

    def test_reconstruct_buffer_formula(self):
        wire = b"\x01\x02\x03"
        buf = reconstruct_buffer(OPCODE_DIRECT_INPUT, wire)
        self.assertEqual(buf, encode_type(58) + bit_header_for_opcode(58) + wire)
        self.assertEqual(deserialize_body(58, wire), bit_header_for_opcode(58) + wire)

    def test_set_movement_driver_uses_two_byte_header(self):
        self.assertEqual(len(bit_header_for_opcode(OPCODE_SET_MOVEMENT_DRIVER)), 2)
        self.assertEqual(len(bit_header_for_opcode(OPCODE_DIRECT_INPUT)), 1)


class ConsumeDeltaTests(unittest.TestCase):
    def test_recon_body_longer_than_raw(self):
        wire = b"\x00" * 13
        raw_len = len(wire)
        recon_len = len(deserialize_body(OPCODE_DIRECT_INPUT, wire))
        self.assertGreater(recon_len, raw_len)

    def test_blocker_reconstruction_invalid(self):
        framing = {
            58: {"validated": False},
            1104: {"validated": True},
        }
        b = classify_blocker(
            framing=framing,
            di={"nCaptured": 0, "mapRangeCount": 0, "uniqueNetIds": []},
            smd={"mapRangeFloatTotal": 0},
            qa={"winnerFound": False},
        )
        self.assertEqual(b["kind"], "reconstruction_invalid")

    def test_blocker_opcodes_not_position_carriers(self):
        framing = {58: {"validated": True}, 1104: {"validated": True}}
        b = classify_blocker(
            framing=framing,
            di={
                "nCaptured": 220,
                "mapRangeCount": 220,
                "uniqueNetIds": [0x400000AF],
            },
            smd={"mapRangeFloatTotal": 0},
            qa={"winnerFound": False},
        )
        self.assertEqual(b["kind"], "opcodes_not_position_carriers")
        self.assertTrue(b["reconstructionValidated"])
        self.assertTrue(b["directInputPlaintextReleased"])


class GateTests(unittest.TestCase):
    def test_gate_constants(self):
        self.assertEqual(ACCEPT_MIN_SAMPLES, 80)
        self.assertEqual(ACCEPT_MIN_HEROES, 5)
        self.assertEqual(ACCEPT_MAX_MEDIAN, 120.0)
        self.assertEqual(ACCEPT_MAX_P95, 350.0)
        self.assertEqual(ACCEPT_MAX_MAX, 800.0)

    def test_score_errs_false_match(self):
        errs = [2000.0] * 100
        sc = _score_errs(errs)
        self.assertGreaterEqual(sc["n"], 80)
        self.assertFalse(sc["ok"])
        self.assertGreater(sc["median"], ACCEPT_MAX_MEDIAN)

    def test_score_errs_passing_volume(self):
        errs = [50.0] * 100
        sc = _score_errs(errs)
        self.assertTrue(sc["ok"])


class AxisSwapTests(unittest.TestCase):
    def _oracle(self):
        return [
            {
                "time": float(t),
                "participants": [
                    {"participantID": 1, "x": 1000.0 + t, "z": 2000.0 + t},
                    {"participantID": 2, "x": 5000.0, "z": 6000.0},
                ],
            }
            for t in range(100, 200)
        ]

    def test_swap_worsens_aligned_samples(self):
        oracle = self._oracle()
        samples = [
            {"t": float(t), "param": 0x400000AF, "x": 1000.0 + t, "z": 2000.0 + t}
            for t in range(100, 200)
        ]
        direct = qa_samples(samples, oracle, swap=False)
        swapped = qa_samples(samples, oracle, swap=True)
        self.assertLess(direct["median"], swapped["median"])

    def test_train_holdout_rejects_high_error(self):
        oracle = self._oracle()
        samples = [
            {"t": float(t), "param": 0x400000AF, "x": 9000.0, "z": 9000.0}
            for t in range(100, 200)
        ]
        qa = train_holdout_qa(samples, oracle)
        self.assertFalse(qa["winnerFound"])
        self.assertFalse(qa.get("axisSwapAccepted"))


if __name__ == "__main__":
    unittest.main()
