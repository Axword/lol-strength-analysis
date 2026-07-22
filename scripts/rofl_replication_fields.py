#!/usr/bin/env python3
"""
Replication field catalog for decoded spectator packets.

Confirmed names:
  - Fixture/HF stub (maknee_match_stub.json): mHP, mMaxHP, mLevelRef
  - Patch 16.14 LeagueofLegends binary string table (exact-build inventory)

Only map fields into rfc461 when a decoded Replication packet actually carries
them. Never invent combat stats from name presence alone.
"""
from __future__ import annotations

from typing import Dict, Mapping, Optional, Tuple

# Names observed in the committed maknee stub / HF-style exports.
FIXTURE_REPLICATION_NAMES = frozenset({"mHP", "mMaxHP", "mLevelRef"})

# Additional names confirmed in the 16.14 client binary field cluster
# (around mBaseAttackDamage … mLevelRef). Used for inventory/probe docs and
# for mapper readiness when an emulator decrypt emits them.
BINARY_COMBAT_REPLICATION_NAMES = frozenset(
    {
        "mBaseAttackDamage",
        "mFlatPhysicalDamageMod",
        "mPercentPhysicalDamageMod",
        "mFlatMagicDamageMod",
        "mPercentMagicDamageMod",
        "mArmor",
        "mBonusArmor",
        "mSpellBlock",
        "mBonusSpellBlock",
        "mAttackSpeedMod",
        "mPercentAttackSpeedMod",
        "mPercentMultiplicativeAttackSpeedMod",
        "mMoveSpeed",
        "mGoldTotal",
        "mGold",
        "mHP",
        "mMaxHP",
        "mLevelRef",
        "mSkillUpLevelDeltaReplicate",
    }
)

# Replication name → rfc461 participant key for direct 1:1 copies.
DIRECT_RFC461_MAP: Dict[str, str] = {
    "mHP": "health",
    "mMaxHP": "healthMax",
    "mLevelRef": "level",
    "mGoldTotal": "totalGold",
    "mGold": "currentGold",
}

# Best-effort combat mapping from CharacterIntermediate-style mods.
# Resolved AD/AP/armor/MR/AS when decrypt emits these names.
COMBAT_COMPONENT_NAMES = frozenset(
    {
        "mBaseAttackDamage",
        "mFlatPhysicalDamageMod",
        "mPercentPhysicalDamageMod",
        "mFlatMagicDamageMod",
        "mPercentMagicDamageMod",
        "mArmor",
        "mBonusArmor",
        "mSpellBlock",
        "mBonusSpellBlock",
        "mAttackSpeedMod",
        "mPercentAttackSpeedMod",
        "mPercentMultiplicativeAttackSpeedMod",
    }
)


def resolve_combat_stats(components: Mapping[str, float]) -> Optional[Dict[str, float]]:
    """Build resolved combat overrides from Replication intermediate values.

    Returns None when no combat components are present. Percent mods follow the
    usual LoL pattern (additive on the base+flat pool). Attack speed is emitted
    as a percent-of-base multiplier * 100 to match timeline ``as`` (100 = 1.0×).
    """
    if not any(k in components for k in COMBAT_COMPONENT_NAMES):
        return None

    base_ad = float(components.get("mBaseAttackDamage") or 0.0)
    flat_ad = float(components.get("mFlatPhysicalDamageMod") or 0.0)
    pct_ad = float(components.get("mPercentPhysicalDamageMod") or 0.0)
    ad = (base_ad + flat_ad) * (1.0 + pct_ad)

    flat_ap = float(components.get("mFlatMagicDamageMod") or 0.0)
    pct_ap = float(components.get("mPercentMagicDamageMod") or 0.0)
    ap = flat_ap * (1.0 + pct_ap)

    armor = float(components.get("mArmor") or 0.0) + float(
        components.get("mBonusArmor") or 0.0
    )
    mr = float(components.get("mSpellBlock") or 0.0) + float(
        components.get("mBonusSpellBlock") or 0.0
    )

    # Prefer multiplicative AS if present; else base mod * (1+percent).
    if "mPercentMultiplicativeAttackSpeedMod" in components:
        as_mult = float(components["mPercentMultiplicativeAttackSpeedMod"])
    else:
        base_as = float(components.get("mAttackSpeedMod") or 1.0)
        pct_as = float(components.get("mPercentAttackSpeedMod") or 0.0)
        as_mult = base_as * (1.0 + pct_as)
    as_pct = max(20.0, as_mult * 100.0)

    return {
        "attackDamage": ad,
        "abilityPower": ap,
        "armor": armor,
        "magicResist": mr,
        "attackSpeed": as_pct,
    }


def apply_replication_value(
    *,
    name: str,
    value: float,
    hp: Dict[int, float],
    hp_max: Dict[int, float],
    level: Dict[int, int],
    gold: Dict[int, float],
    combat: Dict[int, Dict[str, float]],
    nid: int,
) -> None:
    """Update live hero state dicts from one Replication name/value."""
    if name == "mHP":
        hp[nid] = value
    elif name == "mMaxHP":
        hp_max[nid] = value
    elif name == "mLevelRef":
        level[nid] = max(1, int(value))
    elif name in ("mGoldTotal", "mGold"):
        gold[nid] = value
    elif name in COMBAT_COMPONENT_NAMES:
        combat.setdefault(nid, {})[name] = value


def inventory_from_binary(binary: bytes) -> Tuple[str, ...]:
    """Extract m* field names from the client string cluster near mBaseAttackDamage."""
    start = binary.find(b"mBaseAttackDamage")
    if start < 0:
        return tuple()
    end = min(len(binary), start + 20_000)
    names = []
    i = start
    while i < end:
        if binary[i] == 0:
            i += 1
            continue
        j = i
        while j < end and 32 <= binary[j] < 127:
            j += 1
        if j > i and j < len(binary) and binary[j] == 0:
            s = binary[i:j].decode("ascii")
            if s.startswith("m") and len(s) > 2 and s[1].isupper():
                names.append(s)
            i = j + 1
        else:
            i += 1
    # stable unique order
    seen = set()
    out = []
    for n in names:
        if n not in seen:
            seen.add(n)
            out.append(n)
    return tuple(out)
