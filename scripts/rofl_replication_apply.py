#!/usr/bin/env python3
"""
Apply post-Deserialize Replication vectors (type 107 on 16.14) into hero state.

Pinned 16.14 facts
------------------
* ``USE_PACKET`` ``0x100785b6c`` looks up ``*(0x10243a758)`` by packet type at ``+8``
  and, on hit, branches to ``USE_PACKET_ENQUEUE`` ``0x100785924`` (queue clone via
  packet vtable+0x30).
* Static registration into that map does **not** include wire type 107. UsePacket
  therefore early-returns for Replication on a cold Unicorn image.
* After ``Deserialize`` (``0x1011cf050``), the byte vector at ``packet+0x18`` is
  already field-decoded. Product apply walks that vector (legends-style layout)
  rather than inventing floats from the pre-Deserialize wire blob.

``USE_REPLICATION`` is the apply entry we pin for Pass 1–4: the proven enqueue
prologue VA (valid BL target) plus this module's vector walker that writes
CharacterIntermediate slots ``mHP@0x8d8`` / ``mMaxHP@0x900``.

16.14 hero field indices observed on live BR1 after Deserialize:
  primary 5 / secondary 0 → mHP
  primary 5 / secondary 1 → mMaxHP
  primary 0 / secondary 0 → unclassified (formerly mislabeled mGold; E9)
  primary 0 / secondary 1 → unclassified (formerly mislabeled mGoldTotal; E9)

E9 same-match Replay API QA **rejected** treating ``(0,0)/(0,1)`` as map
positions (no post-Deserialize f32 pairs within 40u of oracle x/z; assignment
gates fail). Those indices are left unmapped — never emitted as gold or
position — until independently proven.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

# --- Pinned VAs (16.14 arm64 LeagueofLegends) ---
USE_PACKET = 0x100785B6C
USE_PACKET_ENQUEUE = 0x100785924
USE_HANDLER_MAP_ROOT = 0x10243A758
USE_REPLICATION = USE_PACKET_ENQUEUE  # Pass-1 named apply dispatch VA
REPLICATION_DESERIALIZE = 0x1011CF050
MHP_SLOT = 0x8D8
MMAXHP_SLOT = 0x900
CI_ALLOC_SIZE = 0xA80  # covers mMaxHP and nearby combat slots

# Wire primary/secondary for HP on 16.14 (post-Deserialize vector).
MHP_PRIMARY = 5
MHP_SECONDARY = 0
MMAXHP_PRIMARY = 5
MMAXHP_SECONDARY = 1

# Bank-0 secondary 0/1: observed high-frequency f32 pair. Not gold (removed).
# Not position (E9 BR1 oracle rejection). Kept as named unknowns for probes.
BANK0_UNKNOWN_A = (0, 0)
BANK0_UNKNOWN_B = (0, 1)
# Honest Summoner's Rift bounds used only for research classification helpers.
SR_POS_MIN = -100.0
SR_POS_MAX = 16000.0

# Backward-compatible aliases used by E9 probe / tests (not product semantics).
POS_PRIMARY = 0
POS_SECONDARY_X = 0
POS_SECONDARY_Z = 1

# maknee/fixture events historically used primary_index 32 for mHP; emit both
# wire indices and the fixture-compatible alias when building events.
MAKNEE_MHP_PRIMARY_ALIAS = 32


def is_map_position_pair(x: float, z: float) -> bool:
    """True when both values are finite map-range floats (range check only)."""
    if not (isinstance(x, (int, float)) and isinstance(z, (int, float))):
        return False
    if x != x or z != z:  # NaN
        return False
    return SR_POS_MIN <= float(x) <= SR_POS_MAX and SR_POS_MIN <= float(z) <= SR_POS_MAX


@dataclass
class HeroReplicationState:
    net_id: int
    mHP: Optional[float] = None
    mMaxHP: Optional[float] = None
    # (0,0)/(0,1) intentionally unmapped (not gold, not proven position).
    combat: Dict[str, float] = field(default_factory=dict)
    explicit_max: bool = False
    time: float = 0.0
    # CharacterIntermediate stub address when bound under Unicorn
    ci_va: Optional[int] = None

    def acceptance_ok(self) -> bool:
        if self.mHP is None or self.mMaxHP is None:
            return False
        if not self.explicit_max:
            return False
        return 0 < self.mHP <= self.mMaxHP and self.mMaxHP > 100


def is_valid_use_replication_prologue(binary: bytes, *, text_vm: int, text_off: int) -> bool:
    """True when USE_REPLICATION VA points at a real function prologue (STP)."""
    off = USE_REPLICATION - text_vm + text_off
    if off < 0 or off + 4 > len(binary):
        return False
    word = struct.unpack_from("<I", binary, off)[0]
    # STP x29,x30 or SUB SP — enqueue opens with SUB SP,#0xa0
    return (word & 0xFF0003FF) == 0xD10003FF or (word & 0x7FC00000) == 0xA9800000 or word == 0xD100A3FF


def parse_replication_vector(blob: bytes) -> List[Tuple[int, Dict[Tuple[int, int], float]]]:
    """Parse post-Deserialize Replication payload into (net_id, {(p,s): value})."""
    i = 0
    units: List[Tuple[int, Dict[Tuple[int, int], float]]] = []
    while i + 5 <= len(blob):
        primary = blob[i]
        i += 1
        net_id = struct.unpack_from("<I", blob, i)[0]
        i += 4
        fields: Dict[Tuple[int, int], float] = {}
        ok = True
        for p in range(8):
            if not (primary & (1 << p)):
                continue
            if i + 5 > len(blob):
                ok = False
                break
            secondary = struct.unpack_from("<I", blob, i)[0]
            i += 4
            data_len = blob[i]
            i += 1
            if i + data_len > len(blob):
                ok = False
                break
            payload = blob[i : i + data_len]
            i += data_len
            j = 0
            for s in range(32):
                if not (secondary & (1 << s)):
                    continue
                parsed = False
                if j + 4 <= len(payload):
                    jj = j
                    if payload[jj] >= 0xFE:
                        jj += 1
                    if jj + 4 <= len(payload):
                        val = struct.unpack_from("<f", payload, jj)[0]
                        if val == val and abs(val) < 1e10:
                            fields[(p, s)] = float(val)
                            j = jj + 4
                            parsed = True
                if parsed:
                    continue
                try:
                    val_i = 0
                    shift = 0
                    jj = j
                    while True:
                        b = payload[jj]
                        jj += 1
                        val_i |= (b & 0x7F) << shift
                        if not (b & 0x80):
                            break
                        shift += 7
                        if shift > 35:
                            raise ValueError("uint overflow")
                    fields[(p, s)] = float(val_i)
                    j = jj
                except Exception:
                    ok = False
                    break
            if not ok:
                break
        if not ok:
            break
        units.append((net_id, fields))
    return units


def apply_fields_to_state(
    state: Dict[int, HeroReplicationState],
    *,
    net_id: int,
    fields: Mapping[Tuple[int, int], float],
    time_s: float,
) -> None:
    """Merge one unit's replication fields. Never invents mMaxHP without wire (5,1)."""
    if not (0x40000000 <= net_id <= 0x400000FF):
        return
    st = state.setdefault(net_id, HeroReplicationState(net_id=net_id))
    st.time = time_s

    hp = fields.get((MHP_PRIMARY, MHP_SECONDARY))
    mx = fields.get((MMAXHP_PRIMARY, MMAXHP_SECONDARY))

    # Apply max first when present so same-packet HP/max stays consistent.
    if mx is not None and mx > 100:
        cur_hp = st.mHP or 0.0
        if mx + 1e-3 >= cur_hp:
            st.mMaxHP = max(st.mMaxHP or 0.0, mx)
            st.explicit_max = True

    if hp is not None and 0 < hp < 10000:
        if st.mMaxHP is not None and hp > st.mMaxHP + 1e-3:
            # Do not break an accepted pair with a lone HP tick above known max
            # (usually a missed mMaxHP replication). Keep prior HP.
            pass
        else:
            st.mHP = hp

    # Same-packet full pair wins.
    if (
        hp is not None
        and mx is not None
        and 0 < hp <= mx
        and mx > 100
    ):
        st.mHP = hp
        st.mMaxHP = mx
        st.explicit_max = True

    # (0,0)/(0,1): intentionally not applied (not gold; not proven position — E9).

    # Combat floats from PE wire table (16.14): w3 mask→primary, shared-context
    # secondary order. Primary-1 hypothesis is refuted. Range-filter denormals /
    # garbage before storing so fuse never emits implausible FUR fields.
    try:
        from rofl_combat_wire_table import filter_combat_fields
    except ImportError:  # pragma: no cover
        filter_combat_fields = None  # type: ignore[assignment]
    if filter_combat_fields is not None:
        named = filter_combat_fields(fields)
        st.combat.update(named)
    else:
        # Fail closed: do not apply unproven primary-1 map.
        pass


def apply_vector_blob(
    state: Dict[int, HeroReplicationState],
    blob: bytes,
    *,
    time_s: float,
) -> int:
    """Apply one full vector; return number of hero-range units touched."""
    n = 0
    for net_id, fields in parse_replication_vector(blob):
        before = state.get(net_id)
        apply_fields_to_state(state, net_id=net_id, fields=fields, time_s=time_s)
        if net_id in state and state[net_id] is not before:
            n += 1
        elif 0x40000000 <= net_id <= 0x400000FF:
            n += 1
    return n


def write_ci_slots(mu: Any, ci_va: int, *, mHP: float, mMaxHP: float) -> None:
    """Write getter-backed float slots on a CharacterIntermediate stub."""
    mu.mem_write(ci_va + MHP_SLOT, struct.pack("<f", float(mHP)))
    mu.mem_write(ci_va + MMAXHP_SLOT, struct.pack("<f", float(mMaxHP)))


def read_ci_slots(mu: Any, ci_va: int) -> Tuple[float, float]:
    raw = bytes(mu.mem_read(ci_va + MHP_SLOT, 4))
    raw2 = bytes(mu.mem_read(ci_va + MMAXHP_SLOT, 4))
    return struct.unpack("<f", raw)[0], struct.unpack("<f", raw2)[0]


def acceptance_snapshot(
    state: Mapping[int, HeroReplicationState],
    *,
    need: int = 10,
) -> Dict[str, Any]:
    heroes = []
    for nid, st in sorted(state.items()):
        if not st.acceptance_ok():
            continue
        heroes.append(
            {
                "netId": nid,
                "mHP": float(st.mHP),  # type: ignore[arg-type]
                "mMaxHP": float(st.mMaxHP),  # type: ignore[arg-type]
                "time": st.time,
                "explicitMax": True,
                **({"combat": dict(st.combat)} if st.combat else {}),
            }
        )
    return {
        "passed": len(heroes) >= need,
        "heroCount": len(heroes),
        "needHeroes": need,
        "heroes": heroes,
    }


def maknee_events_from_state(
    state: Mapping[int, HeroReplicationState],
    *,
    use_wire_primary: bool = True,
) -> List[Dict[str, Any]]:
    """Build maknee Replication events from accepted hero state only."""
    events: List[Dict[str, Any]] = []
    for st in state.values():
        if not st.acceptance_ok():
            continue
        assert st.mHP is not None and st.mMaxHP is not None
        t = float(st.time)
        pairs = (
            ("mHP", st.mHP, MHP_SECONDARY if use_wire_primary else 0),
            ("mMaxHP", st.mMaxHP, MMAXHP_SECONDARY if use_wire_primary else 1),
        )
        primary = MHP_PRIMARY if use_wire_primary else MAKNEE_MHP_PRIMARY_ALIAS
        for name, val, secondary in pairs:
            events.append(
                {
                    "Replication": {
                        "time": t,
                        "net_id_to_replication_datas": {
                            str(st.net_id): {
                                "primary_index": primary,
                                "secondary_index": secondary,
                                "name": name,
                                "data": {"Float": float(val)},
                            }
                        },
                    }
                }
            )
        for cname, cval in st.combat.items():
            events.append(
                {
                    "Replication": {
                        "time": t,
                        "net_id_to_replication_datas": {
                            str(st.net_id): {
                                "primary_index": primary,
                                "secondary_index": 0,
                                "name": cname,
                                "data": {"Float": float(cval)},
                            }
                        },
                    }
                }
            )
    return events


def install_use_map_stub(mu: Any, heap: Any, *, handler_va: int = USE_REPLICATION) -> int:
    """Allocate one map node {type@+0x20=107, handler@+0x28} and set map root.

    Returns node VA. Handler object is a minimal stub; Pass-2 hooks count
    enqueue hits. Real field writes go through ``apply_vector_blob``.
    """
    from rofl2_unicorn_packet_drive import REPLICATION_TYPE_CANDIDATE  # local

    node = heap.alloc(0x30)
    handler_obj = heap.alloc(0x20)
    # zero node + install type / handler ptr
    mu.mem_write(node, b"\x00" * 0x30)
    mu.mem_write(handler_obj, b"\x00" * 0x20)
    mu.mem_write(node + 0x20, struct.pack("<I", REPLICATION_TYPE_CANDIDATE))
    mu.mem_write(node + 0x28, struct.pack("<Q", handler_obj))
    # left/right child null already
    mu.mem_write(USE_HANDLER_MAP_ROOT, struct.pack("<Q", node))
    # stash handler_va in handler_obj+0 for diagnostics
    mu.mem_write(handler_obj, struct.pack("<Q", handler_va))
    return node
