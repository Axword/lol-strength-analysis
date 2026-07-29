#!/usr/bin/env python3
"""16.14 type-107 combat wire table (PE registrar → primary/secondary).

Pinned proof (arm64 LeagueofLegends 16.14):
  * Registrar batch calls pass ``w3`` as a power-of-two mask; wire primary bit
    is ``w3.bit_length() - 1`` (``w3=32`` → primary 5 = mHP/mMaxHP control).
  * Secondaries are registration order within a shared context VA.
  * ActionState trio shares context ``0x10244d830`` with combat_core, so combat
    fields start at secondary 3 under primary 2.

Product map below is the first-write PE binding for FUR combat components.
Do not invent values; callers must still range-filter before emit.
"""
from __future__ import annotations

import struct
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

# Proven FUR combat components on live BR1 type-107 (post-Deserialize).
# Keys are (primary, secondary). Values are CharacterIntermediate field names.
PROVEN_COMBAT_WIRE_MAP_16_14: Dict[Tuple[int, int], str] = {
    (2, 3): "mBaseAttackDamage",
    (2, 7): "mArmor",
    (2, 8): "mSpellBlock",
    (2, 12): "mFlatPhysicalDamageMod",
    (2, 13): "mPercentPhysicalDamageMod",
    (2, 14): "mFlatMagicDamageMod",
    (2, 15): "mPercentMagicDamageMod",
    (2, 18): "mAttackSpeedMod",
    (3, 17): "mBonusArmor",
    (3, 18): "mBonusSpellBlock",
    (3, 21): "mPercentAttackSpeedMod",
    (3, 22): "mPercentMultiplicativeAttackSpeedMod",
}

# Refuted hypothesis formerly hardcoded in apply_fields_to_state.
REFUTED_PRIMARY1_HYPOTHESIS: Dict[Tuple[int, int], str] = {
    (1, 5): "mBaseAttackDamage",
    (1, 6): "mFlatMagicDamageMod",
    (1, 9): "mArmor",
    (1, 10): "mSpellBlock",
    (1, 14): "mFlatPhysicalDamageMod",
    (1, 19): "mAttackSpeedMod",
}

# Ordered batch registrars in CharacterIntermediate init (arm64 16.14).
# (context_va, w3_mask, fn_va, label)
BATCH_REGISTRARS_16_14: Tuple[Tuple[int, int, int, str], ...] = (
    (0x10244D830, 4, 0x10005FA2C, "action_state"),
    (0x10244D830, 4, 0x10005DCC4, "combat_core"),
    (0x10244DAD0, 8, 0x10005E1A8, "combat_ext"),
    (0x10244DD70, 16, 0x10005E520, "bank4a"),
    (0x10244DD70, 16, 0x10005FEB8, "bank4b"),
    (0x10244E010, 32, 0x1000CB5CC, "hp"),
    (0x10244E010, 32, 0x10005E5F8, "bank5b"),
    (0x10244E010, 32, 0x1000CB158, "targetable"),
)

FIELD_BINDER_FN = 0x10005E05C  # true entry (old pin 0x10005E074 was mid-prologue)

# Plausible Summoner's Rift ranges used for live QA / apply filters.
PLAUSIBLE_RANGES: Dict[str, Tuple[float, float]] = {
    "mBaseAttackDamage": (20.0, 200.0),
    "mFlatPhysicalDamageMod": (0.0, 800.0),
    "mPercentPhysicalDamageMod": (-0.5, 5.0),
    "mFlatMagicDamageMod": (0.0, 1200.0),
    "mPercentMagicDamageMod": (-0.5, 5.0),
    "mArmor": (10.0, 400.0),
    "mBonusArmor": (0.0, 400.0),
    "mSpellBlock": (10.0, 400.0),
    "mBonusSpellBlock": (0.0, 400.0),
    "mAttackSpeedMod": (0.2, 4.0),
    "mPercentAttackSpeedMod": (0.0, 3.0),
    "mPercentMultiplicativeAttackSpeedMod": (0.2, 5.0),
    "mHP": (100.0, 10000.0),
    "mMaxHP": (100.0, 10000.0),
}

FUR_COMPONENT_REQUIREMENTS: Dict[str, Tuple[str, ...]] = {
    "attackDamage": ("mBaseAttackDamage", "mFlatPhysicalDamageMod"),
    "abilityPower": ("mFlatMagicDamageMod",),
    "armor": ("mArmor", "mBonusArmor"),
    "magicResist": ("mSpellBlock", "mBonusSpellBlock"),
    "attackSpeed": ("mAttackSpeedMod", "mPercentAttackSpeedMod"),
}

COMBAT_STATS_SOURCE = "same_match_replication_type107_pe_wire_table"


def primary_from_w3_mask(w3: int) -> int:
    """Convert registrar w3 power-of-two mask to wire primary bit index."""
    if w3 <= 0 or (w3 & (w3 - 1)) != 0:
        raise ValueError(f"w3 must be power-of-two mask, got {w3}")
    return w3.bit_length() - 1


def value_in_plausible_range(name: str, value: float) -> bool:
    bounds = PLAUSIBLE_RANGES.get(name)
    if bounds is None:
        return value == value and abs(value) < 1e10
    lo, hi = bounds
    return lo <= float(value) <= hi


def _parse_segments(data: bytes) -> List[Tuple[str, int, int, int, int]]:
    if data[:4] != b"\xcf\xfa\xed\xfe":
        raise ValueError("expected MH_MAGIC_64 arm64 Mach-O")
    ncmds = struct.unpack_from("<I", data, 16)[0]
    off = 32
    segments: List[Tuple[str, int, int, int, int]] = []
    for _ in range(ncmds):
        cmd, cmdsize = struct.unpack_from("<II", data, off)
        if cmd == 0x19:
            segname = data[off + 8 : off + 24].split(b"\x00", 1)[0].decode()
            vmaddr, vmsize, fileoff, filesize = struct.unpack_from(
                "<QQQQ", data, off + 24
            )
            segments.append((segname, vmaddr, vmsize, fileoff, filesize))
        off += cmdsize
    return segments


def _read_c_string(data: bytes, segments: Sequence[Tuple[str, int, int, int, int]], va: int) -> Optional[str]:
    for _name, vmaddr, vmsize, fileoff, _fsz in segments:
        if vmaddr <= va < vmaddr + vmsize:
            noff = fileoff + (va - vmaddr)
            raw = data[noff : noff + 80].split(b"\x00", 1)[0]
            try:
                return raw.decode("ascii")
            except UnicodeDecodeError:
                return None
    return None


def extract_batch_registrar_fields(
    data: bytes,
    *,
    fn_va: int,
    limit: int = 0x1000,
) -> List[Dict[str, Any]]:
    """Walk one batch registrar for (slot, name) in binder call order."""
    try:
        from capstone import CS_ARCH_ARM64, CS_MODE_ARM, Cs
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("capstone required: pip install capstone") from exc

    segments = _parse_segments(data)
    text = next(s for s in segments if s[0] == "__TEXT")
    text_vm, text_foff = text[1], text[3]

    def foff(va: int) -> int:
        return va - text_vm + text_foff

    md = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
    code = data[foff(fn_va) : foff(fn_va) + limit]
    fields: List[Dict[str, Any]] = []
    pending_slot: Optional[int] = None
    adrp_page: Optional[int] = None
    for insn in md.disasm(code, fn_va):
        if insn.mnemonic == "ret" and fields and insn.address > fn_va + 0x30:
            break
        if insn.mnemonic == "add" and insn.op_str.startswith("x0, x") and "#" in insn.op_str:
            try:
                pending_slot = int(insn.op_str.split("#")[1].split(",")[0], 0)
            except ValueError:
                pass
        elif insn.mnemonic == "adrp" and insn.op_str.startswith("x2,"):
            try:
                adrp_page = int(insn.op_str.split("#")[1], 0)
            except ValueError:
                adrp_page = None
        elif (
            insn.mnemonic == "add"
            and insn.op_str.startswith("x2, x2, #")
            and adrp_page is not None
        ):
            imm = int(insn.op_str.split("#")[1], 0)
            name = _read_c_string(data, segments, adrp_page + imm)
            fields.append(
                {
                    "slotOffset": pending_slot,
                    "slotOffsetHex": hex(pending_slot) if pending_slot is not None else None,
                    "name": name,
                }
            )
            adrp_page = None
            pending_slot = None
        elif insn.mnemonic == "bl":
            try:
                target = int(insn.op_str.lstrip("#"), 0)
            except ValueError:
                target = -1
            if target == FIELD_BINDER_FN:
                # name already captured on preceding add x2
                pass
    return fields


def extract_wire_table_from_pe(data: bytes) -> Dict[str, Any]:
    """Build (primary,secondary)→name table from pinned batch registrars."""
    ctx_counts: Dict[int, int] = {}
    rows: List[Dict[str, Any]] = []
    by_key: Dict[str, Dict[str, Any]] = {}
    for ctx, w3, fn_va, label in BATCH_REGISTRARS_16_14:
        primary = primary_from_w3_mask(w3)
        start_sec = ctx_counts.get(ctx, 0)
        fields = extract_batch_registrar_fields(data, fn_va=fn_va)
        for field in fields:
            secondary = ctx_counts.get(ctx, 0)
            ctx_counts[ctx] = secondary + 1
            key = f"{primary},{secondary}"
            row = {
                "primary": primary,
                "secondary": secondary,
                "name": field.get("name"),
                "slotOffset": field.get("slotOffset"),
                "slotOffsetHex": field.get("slotOffsetHex"),
                "registrar": label,
                "contextVa": hex(ctx),
                "w3Mask": w3,
                "registrarFn": hex(fn_va),
            }
            rows.append(row)
            by_key.setdefault(key, row)
        _ = start_sec  # documented for evidence
    hp0 = by_key.get("5,0")
    hp1 = by_key.get("5,1")
    return {
        "ok": True,
        "fieldBinderFn": hex(FIELD_BINDER_FN),
        "batchRegistrarCount": len(BATCH_REGISTRARS_16_14),
        "fieldCount": len(rows),
        "fields": rows,
        "byKey": by_key,
        "hpPositiveControl": {
            "mHP": hp0,
            "mMaxHP": hp1,
            "ok": bool(
                hp0
                and hp0.get("name") == "mHP"
                and hp1
                and hp1.get("name") == "mMaxHP"
            ),
        },
        "provenCombatMap": {
            f"{p},{s}": name for (p, s), name in sorted(PROVEN_COMBAT_WIRE_MAP_16_14.items())
        },
        "note": (
            "w3 power-of-two mask → primary bit; secondary = order within shared "
            "context VA. Object slot offsets are not wire indices."
        ),
    }


def load_arm64_slice(league_binary: Path) -> bytes:
    import tempfile

    import rofl2_accessor_spike as spike

    raw = league_binary.read_bytes()
    if raw[:4] == b"\xca\xfe\xba\xbe":
        with tempfile.TemporaryDirectory() as td:
            thin = Path(td) / "lol.arm64"
            spike.thin_arm64(league_binary, thin)
            return thin.read_bytes()
    if raw[:4] != b"\xcf\xfa\xed\xfe":
        raise ValueError(f"unsupported binary magic {raw[:4]!r}")
    return raw


def filter_combat_fields(
    fields: Mapping[Tuple[int, int], float],
    *,
    wire_map: Optional[Mapping[Tuple[int, int], str]] = None,
) -> Dict[str, float]:
    """Map wire floats to names, dropping out-of-range values."""
    mapping = wire_map or PROVEN_COMBAT_WIRE_MAP_16_14
    out: Dict[str, float] = {}
    for key, name in mapping.items():
        if key not in fields:
            continue
        val = float(fields[key])
        if not value_in_plausible_range(name, val):
            continue
        out[name] = val
    return out
