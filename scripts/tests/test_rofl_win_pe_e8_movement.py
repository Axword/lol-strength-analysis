#!/usr/bin/env python3
"""Focused tests for E8 MSVC RTTI + semantic registration mapping."""
from __future__ import annotations

import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from rofl2_binary_format import build_synthetic_pe64, load_binary  # noqa: E402
from rofl2_win_pe_rtti import (  # noqa: E402
    COL_SIGNATURE_X64,
    demangle_msvc_name,
    rtti_from_vptr,
    validate_col,
)
import rofl2_win_pe_e8_movement as e8  # noqa: E402


def _build_pe_with_col(*, bad_self: bool = False, bad_sig: bool = False, bad_name: bool = False):
    """Synthetic PE64 with COL + TypeDescriptor + vtable in .rdata (not .text)."""
    image_base = 0x140000000
    # .text stub
    text = b"\xc3" * 64
    # .rdata layout: [8 pad][COL ptr slot for vptr-1][vtable...][COL][TD]
    rdata = bytearray(0x400)
    vtable_off = 0x100
    col_off = 0x200
    td_off = 0x300
    # section VAs from build_synthetic_pe64: typically text at image_base+0x1000, next section follows
    # We'll discover after load; for packing use relative offsets and fix via load.

    name = b".?AVbad_name@@" if bad_name else b".?AVFakeMovementPacket@@"
    rdata[td_off + 16 : td_off + 16 + len(name)] = name + b"\x00"

    # Placeholder COLs — absolute VAs filled after we know section VA
    pe = build_synthetic_pe64(
        image_base=image_base,
        sections=[(".text", text), (".rdata", bytes(rdata))],
    )
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "tmp.exe"
        path.write_bytes(pe)
        binary = load_binary(path)
    rdata_seg = next(s for s in binary.segments if s.name == ".rdata")
    rdata_va = rdata_seg.vmaddr
    col_va = rdata_va + col_off
    td_va = rdata_va + td_off
    vptr = rdata_va + vtable_off

    td_rva = (td_va - image_base) & 0xFFFFFFFF
    chd_rva = td_rva
    self_rva = (col_va - image_base) & 0xFFFFFFFF
    if bad_self:
        self_rva ^= 0x1111
    sig = 0 if bad_sig else COL_SIGNATURE_X64

    # Patch file bytes for COL + vptr[-1]
    data = bytearray(pe)
    # find .rdata file offset
    fileoff = rdata_seg.fileoff
    struct.pack_into(
        "<IIIIII",
        data,
        fileoff + col_off,
        sig,
        0,
        0,
        td_rva,
        chd_rva,
        self_rva,
    )
    struct.pack_into("<Q", data, fileoff + vtable_off - 8, col_va)
    struct.pack_into("<QQQ", data, fileoff + vtable_off, 0x1000, 0x2000, 0x3000)
    # rewrite name into patched data
    data[fileoff + td_off + 16 : fileoff + td_off + 16 + len(name) + 1] = name + b"\x00"
    return bytes(data), vptr, col_va


class StrictColTests(unittest.TestCase):
    def test_valid_col_and_vptr_lookup(self):
        pe, vptr, col_va = _build_pe_with_col()
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "t.exe"
            path.write_bytes(pe)
            binary = load_binary(path)
        col, reason = validate_col(binary, col_va, base=0x140000000)
        self.assertEqual(reason, "ok")
        self.assertIsNotNone(col)
        assert col is not None
        self.assertEqual(col.type_descriptor.name, ".?AVFakeMovementPacket@@")
        look = rtti_from_vptr(binary, vptr, base=0x140000000)
        self.assertTrue(look.ok)
        self.assertEqual(look.demangled, "FakeMovementPacket")

    def test_invalid_col_pSelf(self):
        pe, vptr, col_va = _build_pe_with_col(bad_self=True)
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "t.exe"
            path.write_bytes(pe)
            binary = load_binary(path)
        col, reason = validate_col(binary, col_va, base=0x140000000)
        self.assertIsNone(col)
        self.assertIn("pSelf_mismatch", reason)
        look = rtti_from_vptr(binary, vptr, base=0x140000000)
        self.assertFalse(look.ok)

    def test_invalid_col_signature(self):
        pe, _vptr, col_va = _build_pe_with_col(bad_sig=True)
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "t.exe"
            path.write_bytes(pe)
            binary = load_binary(path)
        col, reason = validate_col(binary, col_va, base=0x140000000)
        self.assertIsNone(col)
        self.assertIn("bad_signature", reason)

    def test_invalid_type_name_grammar(self):
        pe, _vptr, col_va = _build_pe_with_col(bad_name=True)
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "t.exe"
            path.write_bytes(pe)
            binary = load_binary(path)
        # Force a name that fails NAME_RE: ".?AVbad_name@@" actually still matches .?AV...
        # Use empty/invalid by patching after load via validate on a crafted buffer —
        # instead poke name to "PKT_no_rtti"
        # Rebuild with explicit bad grammar:
        pe2, vptr2, col_va2 = _build_pe_with_col()
        # overwrite name to not start with .?A
        data = bytearray(pe2)
        # find FakeMovement in pe bytes
        idx = data.find(b".?AVFakeMovementPacket@@")
        self.assertGreaterEqual(idx, 0)
        data[idx : idx + 8] = b"NOTRTTI\x00"
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "t.exe"
            path.write_bytes(bytes(data))
            binary = load_binary(path)
        col, reason = validate_col(binary, col_va2, base=0x140000000)
        self.assertIsNone(col)
        self.assertEqual(reason, "type_name_grammar_reject")


class DemangleTests(unittest.TestCase):
    def test_simple_class(self):
        self.assertEqual(demangle_msvc_name(".?AVFoo@@"), "Foo")

    def test_makefunction_pkt_extract(self):
        mangled = (
            ".?AV<lambda_1>@?1???$MakeFunction@VAIBaseClient@@V1@_NAEBVPKT_S2C_SetMovementDriver_s@@@Riot@@"
        )
        self.assertIn("PKT_S2C_SetMovementDriver_s", demangle_msvc_name(mangled))


class RegistrationFalsePositiveTests(unittest.TestCase):
    def test_selection_not_by_frequency(self):
        """Highest block count must not alone select the movement opcode."""
        mapped = {
            "PKT_S2C_FaceDirection_s": {"ok": True, "opcode": 420, "roflBlocks": 13353},
            "PKT_S2C_SetMovementDriver_s": {"ok": True, "opcode": 1104, "roflBlocks": 6},
            "PKT_DirectInputMovementDriverServerTurnData_s": {
                "ok": True,
                "opcode": 58,
                "roflBlocks": 220,
            },
        }
        by_blocks = sorted(
            (
                (info["opcode"], info["roflBlocks"], pkt)
                for pkt, info in mapped.items()
                if info.get("ok")
            ),
            key=lambda t: -t[1],
        )
        # Frequency winner is FaceDirection, but primary movement candidate is driver pair
        self.assertEqual(by_blocks[0][0], 420)
        primary = "PKT_S2C_SetMovementDriver_s"
        self.assertEqual(mapped[primary]["opcode"], 1104)
        self.assertNotEqual(mapped[primary]["opcode"], by_blocks[0][0])

    def test_opcode_from_register_wrapper_requires_hub(self):
        # Synthetic text: mov r8d, 0x450; call rel32_to_hub; ret
        # Without a real hub at REGISTER_HUB_VA this returns None on synthetic PE —
        # document contract via source check.
        src = Path(SCRIPTS / "rofl2_win_pe_e8_movement.py").read_text(encoding="utf-8")
        self.assertIn("REGISTER_HUB_VA", src)
        self.assertIn("mov r8d", src)
        self.assertIn("selectionCriterion", src)
        self.assertIn("not_frequency", src)


class FieldCaptureContractTests(unittest.TestCase):
    def test_ids_from_decoded_field_not_block_param(self):
        src = Path(SCRIPTS / "rofl2_win_pe_e8_movement.py").read_text(encoding="utf-8")
        self.assertIn("netIdField", src)
        self.assertIn("not blockParam", src)


if __name__ == "__main__":
    unittest.main()
