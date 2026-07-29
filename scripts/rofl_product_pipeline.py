#!/usr/bin/env python3
"""Phase D: one-command product pipeline with fail-closed gates A→B→C.

Gate A prefers CastSpellAns champion↔netId bind (CreateHero-*equivalent*), then
falls back to CreateHero discover. Timed HP fuse uses match-dir trusted evidence
when present. Combat trusts only a PE-proven type-107 wire table
(``combatTrusted`` / ``wireTableProven``). Ranks trust UpgradeSpellAns. Never
vendors League binaries.

Example:
  npm run rofl:product-pipeline -- \\
    --rofl \"$HOME/Documents/League of Legends/Replays/BR1-3264361042.rofl\" \\
    --match-dir artifacts/rofl/3264361042 \\
    --json-out docs/rofl-research/product-pipeline-BR1-3264361042.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import fuse_replay_api_hp as fuse  # noqa: E402
import rofl2_ability_ranks_probe as ranks  # noqa: E402
import rofl2_create_hero_discover as create_hero  # noqa: E402
import rofl2_replication_combat_inventory as combat  # noqa: E402
from rofl2_packet_decrypt_probe import DecryptError  # noqa: E402
from rofl_speed_bench import utc_now_iso  # noqa: E402

DEFAULT_ROFL = create_hero.DEFAULT_ROFL
DEFAULT_PE = create_hero.DEFAULT_PE
DEFAULT_MATCH_DIR = Path("artifacts/rofl/3264361042")
DEFAULT_OUT = Path("docs/rofl-research/product-pipeline-BR1-3264361042.json")
E17_REPORT = Path("docs/rofl-research/movement-win-pe-e17-BR1-3264361042.json")
TIMED_HP_REPORT = Path("docs/rofl-research/timed-hp-report-BR1-3264361042.json")
CASTSPELL_REPORT = Path("docs/rofl-research/castspell-identity-BR1-3264361042.json")
CREATE_HERO_REPORT = Path(
    "docs/rofl-research/create-hero-discover-BR1-3264361042.json"
)
COMBAT_WIRE_PROOF = Path("docs/rofl-research/combat-wire-proof-BR1-3264361042.json")
LEVEL_SLOT_REPORT = Path(
    "docs/rofl-research/castspell-level-slot-BR1-3264361042.json"
)
UPGRADE_RANKS_REPORT = Path(
    "docs/rofl-research/upgrade-spell-ranks-BR1-3264361042.json"
)
ABILITY_RANKS_REPORT = Path(
    "docs/rofl-research/ability-ranks-probe-BR1-3264361042.json"
)
COMBAT_INVENTORY_REPORT = Path(
    "docs/rofl-research/combat-inventory-BR1-3264361042.json"
)


def phase_c_from_e17(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {
            "ok": False,
            "blocker": {
                "kind": "e17_report_missing",
                "detail": f"missing {path}",
            },
            "productEligible": False,
            "positionPath": "replay_api_only_unconfirmed",
        }
    report = json.loads(path.read_text(encoding="utf-8"))
    blocker = report.get("blocker") or {
        "kind": "waypoints_not_structurally_decoded",
        "detail": "E17 report lacked blocker object",
    }
    return {
        "ok": False,
        "blocker": blocker,
        "productEligible": bool(report.get("productEligible")),
        "browserSafe": bool(report.get("browserSafe")),
        "pureDecoderDerived": bool(report.get("pureDecoderDerived")),
        "wallMs": report.get("wallMs"),
        "positionPath": "replay_api_only",
        "note": (
            "Offline continuous positions remain blocked; product capture stays "
            "Replay API (compact + final_settle=0), ~22–25 min/match."
        ),
        "evidence": str(path),
    }


def _load_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _load_jsonl(path: Path) -> List[dict]:
    rows: List[dict] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def resolve_gate_a(
    *,
    rofl: Path,
    pe: Path,
    skip_live_discover: bool,
) -> Dict[str, Any]:
    """Prefer CastSpellAns bind; fall back to CreateHero discover reports/live."""
    castspell = _load_json(CASTSPELL_REPORT)
    if (
        castspell
        and castspell.get("ok") is True
        and (castspell.get("identityBinding") or {}).get("complete") is True
    ):
        return {
            "ok": True,
            "method": "castspell_ans_champion_string",
            "productEligible": True,
            "identityBinding": castspell.get("identityBinding"),
            "blocker": None,
            "evidence": str(CASTSPELL_REPORT),
            "note": (
                "CreateHero-*equivalent* champion↔netId bind via "
                "PKT_NPC_CastSpellAns_s (opcode 197); not AE..B7 order."
            ),
        }

    create_hero_report = _load_json(CREATE_HERO_REPORT)
    if not skip_live_discover and pe.is_file() and rofl.is_file():
        create_hero_report = create_hero.run_discover(rofl=rofl, pe=pe)
        CREATE_HERO_REPORT.parent.mkdir(parents=True, exist_ok=True)
        CREATE_HERO_REPORT.write_text(
            json.dumps(create_hero_report, indent=2, default=str) + "\n",
            encoding="utf-8",
        )

    if create_hero_report and create_hero_report.get("ok") is True:
        return {
            "ok": True,
            "method": "create_hero_discover",
            "productEligible": bool(create_hero_report.get("productEligible")),
            "identityBinding": create_hero_report.get("identityBinding"),
            "blocker": None,
            "evidence": str(CREATE_HERO_REPORT),
        }

    return {
        "ok": False,
        "method": "none",
        "productEligible": False,
        "identityBinding": (create_hero_report or {}).get("identityBinding")
        or (castspell or {}).get("identityBinding"),
        "blocker": (castspell or {}).get("blocker")
        or (create_hero_report or {}).get("blocker")
        or {
            "kind": "create_hero_bind_unavailable",
            "detail": "no CastSpellAns or CreateHero complete bind report",
        },
        "evidence": str(CASTSPELL_REPORT if castspell else CREATE_HERO_REPORT),
    }


def resolve_timed_hp_fuse(
    *,
    match_dir: Path,
    gate_a: Mapping[str, Any],
    timed: Optional[Mapping[str, Any]],
) -> Dict[str, Any]:
    """Accept fuse from durable match-dir artifacts, else dry-run, else timed report."""
    manifest = _load_json(match_dir / "manifest.json")
    evidence = _load_json(match_dir / "hp-evidence.json")
    events_path = match_dir / "events.rfc461.jsonl"
    trusted = (manifest or {}).get("trustedHp") if manifest else None

    if (
        isinstance(trusted, Mapping)
        and trusted.get("ok") is True
        and evidence
        and (evidence.get("identityBinding") or {}).get("complete") is True
    ):
        return {
            "ok": True,
            "fuseDryRun": {
                "ok": True,
                "accepted": True,
                "productEligible": True,
                "reason": "accept:match_dir_trusted_hp",
                "summary": {
                    "coverage": trusted.get("coverage"),
                    "fusedFrames": trusted.get("fusedFrames"),
                    "sampleCount": trusted.get("sampleCount"),
                    "combatStatsKnown": False,
                    "abilityRanksKnown": False,
                },
            },
            "sampleCount": trusted.get("sampleCount")
            or len(evidence.get("samples") or []),
            "source": "match_dir_trusted_hp",
            "note": (
                "Durable match-dir trusted HP evidence accepted after CastSpellAns "
                "identity bind + frame-aligned fuse."
            ),
        }

    if evidence and manifest and events_path.is_file() and gate_a.get("ok"):
        try:
            rows = _load_jsonl(events_path)
            _fused, summary = fuse.fuse_product(
                rows,
                replay_manifest=manifest,
                hp_evidence=evidence,
            )
            dry = {
                "ok": True,
                "accepted": True,
                "productEligible": True,
                "reason": "accept",
                "summary": {
                    "coverage": summary.get("coverage"),
                    "fusedFrames": summary.get("fusedFrames"),
                    "sampleCount": summary.get("sampleCount"),
                    "combatStatsKnown": summary.get("combatStatsKnown"),
                    "abilityRanksKnown": summary.get("abilityRanksKnown"),
                },
            }
            return {
                "ok": True,
                "fuseDryRun": dry,
                "sampleCount": summary.get("sampleCount"),
                "source": "live_fuse_product",
                "note": "Recomputed fuse_product against match-dir events + hp-evidence.",
            }
        except (OSError, json.JSONDecodeError, DecryptError, ValueError) as exc:
            return {
                "ok": False,
                "fuseDryRun": {
                    "ok": False,
                    "accepted": False,
                    "productEligible": False,
                    "reason": f"reject:{exc}",
                    "blockers": [str(exc)],
                },
                "sampleCount": len(evidence.get("samples") or []),
                "source": "live_fuse_product",
                "note": "match-dir fuse recomputation failed",
            }

    fuse_dry = (timed or {}).get("fuseDryRun") or {
        "accepted": False,
        "reason": "timed_hp_report_missing",
    }
    return {
        "ok": bool(fuse_dry.get("accepted")) and bool(gate_a.get("ok")),
        "fuseDryRun": fuse_dry,
        "sampleCount": (timed or {}).get("sampleCount"),
        "source": "timed_hp_report",
        "note": (
            "Fuse accept requires Gate A complete bind plus product-shaped "
            "timed HP evidence."
        ),
    }


def run_pipeline(
    *,
    rofl: Path,
    pe: Path,
    match_dir: Path,
    skip_live_discover: bool = False,
) -> Dict[str, Any]:
    phases: Dict[str, Any] = {}

    phase_a = resolve_gate_a(
        rofl=rofl,
        pe=pe,
        skip_live_discover=skip_live_discover,
    )
    phases["A_createHero"] = {
        "ok": bool(phase_a.get("ok")),
        "method": phase_a.get("method"),
        "productEligible": bool(phase_a.get("productEligible")),
        "blocker": phase_a.get("blocker"),
        "identityBindingComplete": bool(
            (phase_a.get("identityBinding") or {}).get("complete")
        ),
        "evidence": phase_a.get("evidence"),
        "note": phase_a.get("note"),
    }
    gate_a = bool(phases["A_createHero"]["ok"])

    timed = _load_json(TIMED_HP_REPORT)
    hp_phase = resolve_timed_hp_fuse(
        match_dir=match_dir,
        gate_a=phase_a,
        timed=timed,
    )
    phases["A_timedHpFuse"] = {
        "ok": bool(hp_phase.get("ok")),
        "fuseDryRun": hp_phase.get("fuseDryRun"),
        "sampleCount": hp_phase.get("sampleCount"),
        "source": hp_phase.get("source"),
        "note": hp_phase.get("note"),
    }

    # Prefer identity from Gate A / durable evidence when refreshing combat inventory.
    timed_for_combat: Dict[str, Any] = dict(timed or {})
    if not (timed_for_combat.get("identityBinding") or {}).get("complete"):
        timed_for_combat["identityBinding"] = phase_a.get("identityBinding") or {}
    evidence = _load_json(match_dir / "hp-evidence.json")
    if evidence and "combatInventory" not in timed_for_combat:
        timed_for_combat["combatInventory"] = evidence.get("combatInventory") or {
            "trusted": False,
            "observedKeys": [],
        }
        timed_for_combat["evidence"] = evidence

    wire_proof = _load_json(COMBAT_WIRE_PROOF)
    combat_report = combat.build_combat_report(
        timed_report=timed_for_combat,
        wire_proof=wire_proof,
    )
    gate_b_combat = bool(
        combat_report.get("ok")
        and combat_report.get("combatTrusted")
        and (wire_proof or {}).get("wireTableProven")
    )
    phases["B_combat"] = {
        "ok": gate_b_combat,
        "blocker": None if gate_b_combat else combat_report.get("blocker"),
        "combatTrusted": gate_b_combat,
        "dependsOnGateA": not gate_a,
        "identityBindingComplete": bool(combat_report.get("identityBindingComplete")),
        "evidence": str(COMBAT_WIRE_PROOF if wire_proof else COMBAT_INVENTORY_REPORT),
        "wireProofSchema": (wire_proof or {}).get("schema"),
        "wireTableProven": bool((wire_proof or {}).get("wireTableProven")),
    }
    if rofl.is_file():
        ranks_report = ranks.run_ranks_probe(rofl)
    else:
        upgrade = _load_json(UPGRADE_RANKS_REPORT)
        if (
            upgrade
            and upgrade.get("ok") is True
            and upgrade.get("abilityRanksTrusted") is True
        ):
            ranks_report = {
                "ok": True,
                "abilityRanksTrusted": True,
                "productEligible": True,
                "castSpellAnsMapped": True,
                "castSpellAnsLevelSlotDecoded": False,
                "upgradeSpellAnsDecoded": True,
                "blocker": None,
                "levelSlotEvidence": str(LEVEL_SLOT_REPORT),
                "upgradeEvidence": str(UPGRADE_RANKS_REPORT),
                "eventCount": upgrade.get("eventCount"),
                "abilityRanksSource": upgrade.get("abilityRanksSource"),
            }
        else:
            ranks_report = {
                "ok": False,
                "blocker": {
                    "kind": "ability_ranks_wire_unproven",
                    "detail": "ROFL missing; ranks probe skipped",
                },
                "abilityRanksTrusted": False,
            }

    gate_b_ranks = bool(
        ranks_report.get("ok") and ranks_report.get("abilityRanksTrusted")
    )
    phases["B_ranks"] = {
        "ok": gate_b_ranks,
        "blocker": None if gate_b_ranks else ranks_report.get("blocker"),
        "abilityRanksTrusted": gate_b_ranks,
        "dependsOnGateA": not gate_a,
        "castSpellAnsMapped": bool(ranks_report.get("castSpellAnsMapped")),
        "castSpellAnsLevelSlotDecoded": bool(
            ranks_report.get("castSpellAnsLevelSlotDecoded")
        ),
        "upgradeSpellAnsDecoded": bool(ranks_report.get("upgradeSpellAnsDecoded")),
        "evidence": ranks_report.get("upgradeEvidence")
        or ranks_report.get("levelSlotEvidence")
        or str(ABILITY_RANKS_REPORT),
    }

    phases["C_offlinePositions"] = phase_c_from_e17(E17_REPORT)

    publish_hp = bool(phases["A_timedHpFuse"]["ok"])
    # Gate B1/B2 may be trusted; calculatorReady still requires every timeline
    # frame to carry hpKnown+combatStatsKnown+abilityRanksKnown. Current HP
    # evidence is partial (sampled frames only) — do not claim calculatorReady
    # until a denser same-match HP fuse covers all frames honestly.
    hp_full = False
    fuse_summary = _load_json(match_dir / "hp-fuse-summary.json") or {}
    if str(fuse_summary.get("coverage") or "").lower() == "full":
        hp_full = True
    calculator_ready = (
        gate_a and gate_b_combat and gate_b_ranks and publish_hp and hp_full
    )
    published_manifest = _load_json(
        Path("public/data/matches") / "3264361042" / "manifest.json"
    )
    registry_hp = bool(
        ((published_manifest or {}).get("productGates") or {}).get("hpTrusted")
    ) and bool(((published_manifest or {}).get("trustedHp") or {}).get("ok"))
    if calculator_ready:
        detail = "All product gates A+B1+B2 + full-frame HP passed — calculatorReady"
        publish_blocker = None
    elif gate_a and gate_b_combat and gate_b_ranks and publish_hp and not hp_full:
        mk_ms = None
        other_ms = None
        dense_count = None
        first_all10 = None
        combat_proof = _load_json(COMBAT_WIRE_PROOF) or {}
        hp_ev = combat_proof.get("timedHpEvidence") or {}
        blocker_ev = combat_proof.get("calculatorReadyBlocker") or {}
        mk_ms = hp_ev.get("monkeyKingFirstHpMs") or blocker_ev.get("monkeyKingFirstHpMs")
        other_ms = hp_ev.get("otherHeroesFirstHpMs") or blocker_ev.get(
            "otherHeroesFirstHpMs"
        )
        first_all10 = hp_ev.get("firstAll10HpMs") or blocker_ev.get("firstAll10HpMs")
        dense_count = hp_ev.get("sampleCount") or blocker_ev.get("denseHpSampleCount")
        detail = (
            "Gates A+B1+B2 trusted (CastSpellAns identity, PE combat wire table, "
            "UpgradeSpellAns ranks) but calculatorReady needs hpKnown on every "
            "Replay API frame. MonkeyKing (0x400000af) first explicit mMaxHP at "
            f"~{mk_ms}ms (others ~{other_ms}ms); densify covers frames after "
            f"firstAll10={first_all10}ms ({dense_count} samples) — early frames "
            "cannot honestly set hpKnown without inventing HP. Terminal wire gap."
        )
        publish_blocker = {
            "kind": "calculator_hp_density",
            "terminal": True,
            "detail": detail,
            "gateA": gate_a,
            "gateA_method": phase_a.get("method"),
            "gateB_combat": gate_b_combat,
            "gateB_ranks": gate_b_ranks,
            "gateC": False,
            "publishedHpTrusted": registry_hp,
            "hpCoverage": fuse_summary.get("coverage") or "partial",
            "monkeyKingFirstHpMs": mk_ms,
            "otherHeroesFirstHpMs": other_ms,
            "firstAll10HpMs": first_all10,
            "denseHpSampleCount": dense_count,
        }
    elif publish_hp and gate_b_ranks and not gate_b_combat:
        detail = (
            "Gate A + timed HP + UpgradeSpellAns ranks trusted; combat wire "
            "index→FUR map still unproven — HP/ranks may publish, calculator "
            "Send stays closed"
        )
        publish_blocker = {
            "kind": "product_gates_incomplete",
            "detail": detail,
            "gateA": gate_a,
            "gateA_method": phase_a.get("method"),
            "gateB_combat": gate_b_combat,
            "gateB_ranks": gate_b_ranks,
            "gateC": False,
            "publishedHpTrusted": registry_hp,
        }
    elif publish_hp and not (gate_b_combat and gate_b_ranks):
        detail = (
            "Gate A CastSpellAns bind + timed HP fuse accepted; combat/ranks still "
            "unproven and offline positions blocked — HP may publish as "
            "hpTrusted/partial, calculator Send stays closed"
        )
        publish_blocker = {
            "kind": "product_gates_incomplete",
            "detail": detail,
            "gateA": gate_a,
            "gateA_method": phase_a.get("method"),
            "gateB_combat": gate_b_combat,
            "gateB_ranks": gate_b_ranks,
            "gateC": False,
            "publishedHpTrusted": registry_hp,
        }
    elif not gate_a:
        detail = (
            "Gate A identity bind incomplete; combat/ranks unproven; offline "
            "positions blocked — do not mark calculatorReady or publish trusted HP"
        )
        publish_blocker = {
            "kind": "product_gates_incomplete",
            "detail": detail,
            "gateA": gate_a,
            "gateA_method": phase_a.get("method"),
            "gateB_combat": gate_b_combat,
            "gateB_ranks": gate_b_ranks,
            "gateC": False,
            "publishedHpTrusted": registry_hp,
        }
    else:
        detail = (
            "Gate A complete but timed HP fuse not accepted; combat/ranks unproven"
        )
        publish_blocker = {
            "kind": "product_gates_incomplete",
            "detail": detail,
            "gateA": gate_a,
            "gateA_method": phase_a.get("method"),
            "gateB_combat": gate_b_combat,
            "gateB_ranks": gate_b_ranks,
            "gateC": False,
            "publishedHpTrusted": registry_hp,
        }
    phases["D_publish"] = {
        "ok": bool(registry_hp or calculator_ready),
        "matchDir": str(match_dir),
        "registryPublish": registry_hp,
        "calculatorReady": calculator_ready,
        "trustedHpPublish": publish_hp,
        "blocker": publish_blocker,
        "ingestHint": (
            "rofl_ingest build --hp-evidence + fuse_replay_api_ranks + "
            "fuse_replay_api_combat + validate --require-calculator-ready + publish"
            if calculator_ready
            else (
                "rofl_ingest build --hp-evidence + fuse_replay_api_ranks + validate + "
                "publish; --require-calculator-ready needs Gate B combat too"
            )
        ),
    }
    if not gate_a:
        next_action = (
            "Decode CastSpellAns/CreateHero champion↔netId bind "
            f"(blocker={(phase_a.get('blocker') or {}).get('kind')})"
        )
    elif not publish_hp:
        next_action = (
            "Emit/fuse timed identity-bound HP evidence into match-dir "
            "(A_timedHpFuse still closed)"
        )
    elif not gate_b_ranks:
        next_action = (
            "Prove UpgradeSpellAns opcode 636 ranks "
            f"(blocker={(ranks_report.get('blocker') or {}).get('kind')})"
        )
    elif not gate_b_combat:
        next_action = (
            "Prove combat wire index→FUR field map "
            f"(blocker={(phases['B_combat'].get('blocker') or {}).get('kind')}); "
            "calculator Send stays closed"
        )
    elif not hp_full:
        next_action = (
            "Terminal calculator_hp_density: MonkeyKing explicit mMaxHP missing "
            "before firstAll10 — early Replay API frames stay hpKnown=false; "
            "densified late frames may still unlock Send at playhead"
        )
    else:
        next_action = "Publish calculator-ready match and unlock UI Send"

    return {
        "ok": bool(calculator_ready),
        "ts": utc_now_iso(),
        "matchCode": "3264361042",
        "phases": phases,
        "nextAction": next_action,
        "productEligible": bool(calculator_ready),
        "calculatorReady": calculator_ready,
        "hpTrustedEligible": publish_hp,
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rofl", type=Path, default=DEFAULT_ROFL)
    ap.add_argument("--pe", type=Path, default=DEFAULT_PE)
    ap.add_argument("--match-dir", type=Path, default=DEFAULT_MATCH_DIR)
    ap.add_argument("--json-out", type=Path, default=DEFAULT_OUT)
    ap.add_argument(
        "--skip-live-discover",
        action="store_true",
        help="Reuse prior CastSpellAns / CreateHero reports (CI / no PE)",
    )
    args = ap.parse_args(argv)

    report = run_pipeline(
        rofl=args.rofl,
        pe=args.pe,
        match_dir=args.match_dir,
        skip_live_discover=bool(args.skip_live_discover)
        or not args.pe.is_file()
        or not args.rofl.is_file(),
    )
    combat_out = COMBAT_INVENTORY_REPORT
    ranks_out = ABILITY_RANKS_REPORT
    if args.rofl.is_file():
        ranks_report = ranks.run_ranks_probe(args.rofl)
        ranks_out.write_text(json.dumps(ranks_report, indent=2) + "\n", encoding="utf-8")
    timed = _load_json(TIMED_HP_REPORT) or {}
    evidence = _load_json(args.match_dir / "hp-evidence.json")
    if evidence:
        timed = dict(timed)
        timed.setdefault("identityBinding", evidence.get("identityBinding"))
        timed.setdefault("combatInventory", evidence.get("combatInventory"))
        timed.setdefault("evidence", evidence)
    castspell = _load_json(CASTSPELL_REPORT)
    if castspell and not (timed.get("identityBinding") or {}).get("complete"):
        timed = dict(timed)
        timed["identityBinding"] = castspell.get("identityBinding")
    wire_proof = _load_json(COMBAT_WIRE_PROOF)
    combat_report = combat.build_combat_report(
        timed_report=timed,
        wire_proof=wire_proof,
    )
    combat_out.write_text(
        json.dumps(combat_report, indent=2, default=str) + "\n",
        encoding="utf-8",
    )

    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(
        json.dumps(report, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {args.json_out}")
    print(json.dumps(report["phases"], indent=2, default=str)[:2000])
    # Exit 0 when Gate A + HP fuse accepted (still not calculator-ready).
    if report.get("hpTrustedEligible") and report["phases"]["A_createHero"]["ok"]:
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
