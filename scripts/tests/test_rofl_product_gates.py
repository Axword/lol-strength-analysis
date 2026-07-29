#!/usr/bin/env python3
"""Product publication gates + research/schema-proof provenance quarantine."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, List

SCRIPTS = Path(__file__).resolve().parents[1]
ROOT = SCRIPTS.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import fuse_replay_api_hp as fuse  # noqa: E402
import maknee_packets_to_jsonl as maknee  # noqa: E402
import rfc461_emit  # noqa: E402
import run_live_fur_e2e as live_fur  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "validate_rofl_pipeline",
    SCRIPTS / "validate-rofl-pipeline.py",
)
assert _spec and _spec.loader
validate_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(validate_mod)


def _roster(champs: List[str] | None = None) -> List[dict]:
    names = champs or [f"Champ{i}" for i in range(1, 11)]
    rows = []
    for i, champ in enumerate(names, start=1):
        rows.append(
            {
                "participantID": i,
                "teamID": 100 if i <= 5 else 200,
                "championName": champ,
                "playerName": f"player{i}",
                "summonerName": f"player{i}",
            }
        )
    return rows


def _write_pair(
    td: Path,
    *,
    source: str,
    source_kind: str,
    game_id: int = 3264383283,
    game_name: str | None = None,
    champs: List[str] | None = None,
    position_coverage: str = "full_at_sampled_frames",
    hp_coverage: str = "none",
    extra_prov: Dict[str, Any] | None = None,
    timeline_units_extra: Dict[str, Any] | None = None,
    has_career: bool = False,
    career: Dict[str, Any] | None = None,
    calculator_ready_note: bool = False,
) -> tuple[Path, Path]:
    roster = _roster(champs)
    prov = rfc461_emit.provenance_record(
        source=source,
        source_kind=source_kind,
        position_coverage=position_coverage,
        hp_coverage=hp_coverage,
        roster_mapping="test",
        artifact="test",
        notes=(
            "calculator-ready product claim" if calculator_ready_note else "unit test stream"
        ),
    )
    if extra_prov:
        prov.update(extra_prov)
    if game_id:
        prov["matchCode"] = str(game_id)
        prov["gameId"] = game_id

    participants = []
    for p in roster:
        row = rfc461_emit.participant_row(
            participant_id=p["participantID"],
            team_id=p["teamID"],
            champion_name=p["championName"],
            player_name=p["playerName"],
            position={"x": 1000.0 + p["participantID"], "z": 2000.0 + p["participantID"]},
            position_source="replay_api_focus",
            health_known=hp_coverage != "none",
            health_source=(
                "unavailable_replay_api" if hp_coverage == "none" else None
            ),
            combat_stats_source=(
                "unavailable_replay_api" if hp_coverage == "none" else None
            ),
            ability_ranks_source=(
                "unavailable_replay_api" if hp_coverage == "none" else None
            ),
        )
        participants.append(row)

    rows = [
        rfc461_emit.coverage_line(
            source=source,
            game_id=game_id,
            provenance=prov,
            notes=prov.get("notes") or "",
        ),
        rfc461_emit.game_info_line(
            game_id=game_id,
            game_name=game_name if game_name is not None else str(game_id),
            participants=roster,
        ),
        rfc461_emit.stats_update_line(
            game_id=game_id,
            game_time=60_000,
            participants=participants,
        ),
        rfc461_emit.stats_update_line(
            game_id=game_id,
            game_time=61_000,
            participants=participants,
        ),
        rfc461_emit.stats_update_line(
            game_id=game_id,
            game_time=62_000,
            participants=participants,
        ),
        rfc461_emit.game_end_line(game_id=game_id, game_time=62_000),
    ]
    jsonl = td / "events.jsonl"
    rfc461_emit.write_jsonl(jsonl, rows)

    units = []
    for p in roster:
        unit: Dict[str, Any] = {
            "pid": p["participantID"],
            "champ": p["championName"],
            "name": p["playerName"],
            "team": p["teamID"],
            "role": "Top",
            "level": 6,
            "hp": 0,
            "hpMax": 0,
            "alive": True,
            "hpKnown": False,
            "combatStatsKnown": False,
            "abilityRanksKnown": False,
            "ad": 0,
            "ap": 0,
            "armor": 0,
            "mr": 0,
            "as": 100,
            "x": 0.1,
            "y": 0.2,
            "positionSource": "replay_api_focus",
            "items": [1001],
            "q": 0,
            "w": 0,
            "e": 0,
            "r": 0,
        }
        if timeline_units_extra:
            unit.update(timeline_units_extra)
        if has_career:
            unit["career"] = dict(
                career
                or {
                    "kills": 1,
                    "deaths": 1,
                    "assists": 1,
                    "cs": 0,
                    "jungleCs": 0,
                    "visionScore": 0,
                    "dmgTotal": 0,
                    "dmgToChamps": 0,
                    "dmgTaken": 0,
                    "gold": 0,
                    "goldBag": 0,
                    "touchModel": "rofl_end_box_score_kda_only",
                }
            )
        units.append(unit)

    frame = {"t": 60_000, "units": units}
    frame2 = {"t": 61_000, "units": json.loads(json.dumps(units))}
    frame3 = {"t": 62_000, "units": json.loads(json.dumps(units))}
    timeline = {
        "id": "test_match",
        "name": str(game_id),
        "patch": "16.14",
        "source": source,
        "provenance": dict(prov),
        "cadenceMs": 1000,
        "participants": [
            {
                "participantID": p["participantID"],
                "summonerName": p["summonerName"],
                "championName": p["championName"],
                "teamID": p["teamID"],
                "role": "Top",
            }
            for p in roster
        ],
        "frameCount": 3,
        "durationMs": 62_000,
        "frames": [frame, frame2, frame3],
        "hasCareerStats": has_career,
        "hasScoreboard": False,
        "hasVision": False,
        "hasMapObjects": False,
    }
    tl_path = td / "timeline.json"
    tl_path.write_text(json.dumps(timeline) + "\n", encoding="utf-8")
    return jsonl, tl_path


class ProductGateRejectionTests(unittest.TestCase):
    def test_schema_proof_provenance_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            td = Path(tmp)
            jsonl, tl = _write_pair(
                td,
                source="schema_proof_fixture_hp_merge",
                source_kind="schema_proof_fixture_hp_merge",
                extra_prov={
                    "schemaProof": True,
                    "publicationBlocked": True,
                    "researchOnly": True,
                },
            )
            with self.assertRaises(SystemExit) as ctx:
                validate_mod.validate_product(jsonl, tl)
            self.assertTrue(
                any(
                    token in str(ctx.exception)
                    for token in ("schemaProof", "publicationBlocked", "schema_proof")
                ),
                str(ctx.exception),
            )

    def test_static_snapshot_hp_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            td = Path(tmp)
            jsonl, tl = _write_pair(
                td,
                source="replay_api_playback",
                source_kind="research_static_hp_snapshot",
                hp_coverage="snapshot_fused",
                extra_prov={"researchOnly": True, "publicationBlocked": True},
            )
            with self.assertRaises(SystemExit) as ctx:
                validate_mod.validate_product(jsonl, tl)
            msg = str(ctx.exception)
            self.assertTrue(
                "publicationBlocked" in msg
                or "researchOnly" in msg
                or "snapshot" in msg
                or "sourceKind" in msg,
                msg,
            )

    def test_synthetic_path_provenance_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            td = Path(tmp)
            jsonl, tl = _write_pair(
                td,
                source="maknee_decoded_packets",
                source_kind=maknee.SYNTHETIC_SOURCE_KIND,
                position_coverage="partial",
                hp_coverage="partial",
                extra_prov={
                    "positionSynthesis": maknee.POSITION_SYNTHESIS,
                    "researchOnly": True,
                    "publicationBlocked": True,
                },
            )
            with self.assertRaises(SystemExit) as ctx:
                validate_mod.validate_product(jsonl, tl)
            self.assertIn("FAIL", str(ctx.exception))

    def test_fixture_roster_under_real_match_rejected(self):
        fixture_champs = [
            "Gnar",
            "LeeSin",
            "Ahri",
            "Jinx",
            "Thresh",
            "Darius",
            "Vi",
            "Syndra",
            "Samira",
            "Nautilus",
        ]
        with tempfile.TemporaryDirectory() as tmp:
            td = Path(tmp)
            jsonl, tl = _write_pair(
                td,
                source="replay_api_playback",
                source_kind="replay_api_playback",
                champs=fixture_champs,
            )
            with self.assertRaises(SystemExit) as ctx:
                validate_mod.validate_product(jsonl, tl)
            self.assertIn("fixture roster", str(ctx.exception))

    def test_missing_match_identity_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            td = Path(tmp)
            jsonl, tl = _write_pair(
                td,
                source="replay_api_playback",
                source_kind="replay_api_playback",
                game_id=0,
                game_name="",
            )
            # Clear identity markers that _write_pair may still stamp.
            rows = [json.loads(l) for l in jsonl.read_text().splitlines() if l.strip()]
            for row in rows:
                if row.get("rfc461Schema") == "game_info":
                    row["gameID"] = 0
                    row["gameName"] = ""
                if row.get("rfc461Schema") == "rofl_coverage":
                    row.get("provenance", {}).pop("matchCode", None)
                    row.get("provenance", {}).pop("gameId", None)
            jsonl.write_text(
                "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8"
            )
            tl_data = json.loads(tl.read_text())
            tl_data["name"] = "no_code"
            tl_data["provenance"].pop("matchCode", None)
            tl_data["provenance"].pop("gameId", None)
            tl.write_text(json.dumps(tl_data) + "\n", encoding="utf-8")
            with self.assertRaises(SystemExit) as ctx:
                validate_mod.validate_product(jsonl, tl)
            self.assertIn("gameID", str(ctx.exception))

    def test_unknown_career_as_zero_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            td = Path(tmp)
            jsonl, tl = _write_pair(
                td,
                source="replay_api_playback",
                source_kind="replay_api_playback",
                has_career=True,
            )
            with self.assertRaises(SystemExit) as ctx:
                validate_mod.validate_product(jsonl, tl)
            self.assertIn("career", str(ctx.exception).lower())

    def test_calculator_claim_without_gates_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            td = Path(tmp)
            jsonl, tl = _write_pair(
                td,
                source="replay_api_playback",
                source_kind="replay_api_playback",
                calculator_ready_note=True,
            )
            with self.assertRaises(SystemExit) as ctx:
                validate_mod.validate_product(jsonl, tl)
            self.assertIn("calculator-ready", str(ctx.exception))

    def test_trustworthy_middle_frame_cannot_make_whole_timeline_calculator_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            td = Path(tmp)
            jsonl, tl = _write_pair(
                td,
                source="replay_api_playback",
                source_kind="replay_api_playback",
                hp_coverage="partial",
                calculator_ready_note=True,
            )

            rows = [json.loads(line) for line in jsonl.read_text().splitlines() if line]
            for row in rows:
                if (
                    row.get("rfc461Schema") != "stats_update"
                    or int(row.get("gameTime") or 0) != 61_000
                ):
                    continue
                for participant in row["participants"]:
                    participant.update(
                        {
                            "health": 750,
                            "healthMax": 1000,
                            "healthSource": "same_match_replication",
                            "attackDamage": 100,
                            "abilityPower": 0,
                            "armor": 50,
                            "magicResist": 35,
                            "attackSpeed": 0.75,
                            "combatStatsSource": "same_match_replication",
                            "ability1Level": 1,
                            "ability2Level": 1,
                            "ability3Level": 1,
                            "ability4Level": 1,
                            "abilityRanksSource": "same_match_replication",
                        }
                    )
            jsonl.write_text(
                "\n".join(json.dumps(row) for row in rows) + "\n",
                encoding="utf-8",
            )

            timeline = json.loads(tl.read_text())
            for unit in timeline["frames"][1]["units"]:
                unit.update(
                    {
                        "hp": 750,
                        "hpMax": 1000,
                        "hpKnown": True,
                        "ad": 100,
                        "ap": 0,
                        "armor": 50,
                        "mr": 35,
                        "as": 100,
                        "combatStatsKnown": True,
                        "q": 1,
                        "w": 1,
                        "e": 1,
                        "r": 1,
                        "abilityRanksKnown": True,
                    }
                )
            tl.write_text(json.dumps(timeline) + "\n", encoding="utf-8")

            with self.assertRaises(SystemExit) as ctx:
                validate_mod.validate_product(jsonl, tl)
            self.assertIn("every frame/unit", str(ctx.exception))

    def test_dishonest_interior_combat_row_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            td = Path(tmp)
            jsonl, tl = _write_pair(
                td,
                source="replay_api_playback",
                source_kind="replay_api_playback",
            )
            timeline = json.loads(tl.read_text())
            timeline["frames"][1]["units"][0]["combatStatsKnown"] = True
            tl.write_text(json.dumps(timeline) + "\n", encoding="utf-8")

            with self.assertRaises(SystemExit) as ctx:
                validate_mod.validate_product(jsonl, tl)
            self.assertIn("t=61000", str(ctx.exception))
            self.assertIn("non-placeholder combat", str(ctx.exception))

    def test_dishonest_interior_score_only_career_row_is_rejected(self):
        score_row = {
            "kills": 0,
            "deaths": 0,
            "assists": 0,
            "cs": 0,
            "visionScore": 0,
            "careerSource": "liveclient_scores",
        }
        with tempfile.TemporaryDirectory() as tmp:
            td = Path(tmp)
            jsonl, tl = _write_pair(
                td,
                source="replay_api_playback",
                source_kind="replay_api_playback",
                extra_prov={"scoreCoverage": "liveclient_scores"},
                has_career=True,
                career=score_row,
            )
            timeline = json.loads(tl.read_text())
            timeline["frames"][1]["units"][0]["career"]["dmgToChamps"] = 0
            tl.write_text(json.dumps(timeline) + "\n", encoding="utf-8")

            with self.assertRaises(SystemExit) as ctx:
                validate_mod.validate_product(jsonl, tl)
            self.assertIn("t=61000", str(ctx.exception))
            self.assertIn("unsupported fields", str(ctx.exception))

    def test_authoritative_early_zero_liveclient_scores_are_allowed(self):
        score_row = {
            "kills": 0,
            "deaths": 0,
            "assists": 0,
            "cs": 0,
            "visionScore": 0,
            "careerSource": "liveclient_scores",
        }
        with tempfile.TemporaryDirectory() as tmp:
            td = Path(tmp)
            jsonl, tl = _write_pair(
                td,
                source="replay_api_playback",
                source_kind="replay_api_playback",
                extra_prov={"scoreCoverage": "liveclient_scores"},
                has_career=True,
                career=score_row,
            )
            report = validate_mod.validate_product(jsonl, tl)
            self.assertTrue(report["ok"])
            self.assertFalse(report["calculatorReady"])

    def test_honest_replay_api_map_passes_product_without_calculator(self):
        with tempfile.TemporaryDirectory() as tmp:
            td = Path(tmp)
            champs = [
                "Renekton",
                "Mordekaiser",
                "Yasuo",
                "Jhin",
                "Nami",
                "Zaahen",
                "Lillia",
                "Zed",
                "Ashe",
                "Sona",
            ]
            jsonl, tl = _write_pair(
                td,
                source="replay_api_playback",
                source_kind="replay_api_playback",
                champs=champs,
                has_career=False,
            )
            # Generic validate + product (map publish, not calculator).
            generic = validate_mod.validate(jsonl, tl, require_live=False)
            self.assertTrue(generic["ok"])
            product = validate_mod.validate_product(jsonl, tl)
            self.assertTrue(product["ok"])
            self.assertFalse(product["calculatorReady"])
            self.assertIn("Zaahen", product["rosterChampions"])

    def test_grid_riot_livestats_source_kind_rejected(self):
        """R19: gameID rewrite must not publish GRID research density."""
        with tempfile.TemporaryDirectory() as tmp:
            td = Path(tmp)
            jsonl, tl = _write_pair(
                td,
                source="grid_riot_livestats",
                source_kind="grid_riot_livestats",
                game_id=3264361042,
                hp_coverage="dense_1hz_when_present",
            )
            with self.assertRaises(SystemExit) as ctx:
                validate_mod.validate_product(jsonl, tl)
            self.assertIn("grid_riot_livestats", str(ctx.exception))

    def test_short_game_id_without_tournament_disclosure_rejected(self):
        """R20: bare gameID 426746 must not publish without LOLTMNT disclosure."""
        with tempfile.TemporaryDirectory() as tmp:
            td = Path(tmp)
            jsonl, tl = _write_pair(
                td,
                source="replay_api_playback",
                source_kind="replay_api_playback",
                game_id=426746,
            )
            with self.assertRaises(SystemExit) as ctx:
                validate_mod.validate_product(jsonl, tl)
            self.assertIn("426746", str(ctx.exception))

    def test_disclosed_tournament_identity_allows_short_game_id(self):
        """R20: LOLTMNT01-426746 with explicit disclosure clears identity gate."""
        with tempfile.TemporaryDirectory() as tmp:
            td = Path(tmp)
            champs = [
                "Ambessa",
                "LeeSin",
                "Syndra",
                "Jhin",
                "Leona",
                "Gnar",
                "Naafiri",
                "Cassiopeia",
                "Ezreal",
                "Camille",
            ]
            jsonl, tl = _write_pair(
                td,
                source="rofl_upgrade_spell_ranks_fuse",
                source_kind="rofl_upgrade_spell_ranks_fuse",
                game_id=426746,
                champs=champs,
                extra_prov={
                    "tournamentIdentityDisclosed": True,
                    "suggestedProductRofl": "LOLTMNT01-426746.rofl",
                    "platformID": "LOLTMNT01",
                    "gridSeriesId": "2970110",
                    "matchCode": "426746",
                },
            )
            rows = [json.loads(l) for l in jsonl.read_text().splitlines() if l.strip()]
            for row in rows:
                if row.get("rfc461Schema") == "game_info":
                    row["platformID"] = "LOLTMNT01"
                    row["gameName"] = "426746"
            jsonl.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
            tl_obj = json.loads(tl.read_text())
            tl_obj["name"] = "426746"
            prov = dict(tl_obj.get("provenance") or {})
            prov.update(
                {
                    "tournamentIdentityDisclosed": True,
                    "suggestedProductRofl": "LOLTMNT01-426746.rofl",
                    "platformID": "LOLTMNT01",
                    "gridSeriesId": "2970110",
                    "matchCode": "426746",
                }
            )
            tl_obj["provenance"] = prov
            tl.write_text(json.dumps(tl_obj))
            product = validate_mod.validate_product(jsonl, tl)
            self.assertTrue(product["ok"])
            self.assertEqual(product["gameID"], 426746)
            self.assertFalse(product["calculatorReady"])
            self.assertFalse(product["hpTrusted"])

    def test_product_eligible_false_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            td = Path(tmp)
            jsonl, tl = _write_pair(
                td,
                source="replay_api_playback",
                source_kind="replay_api_playback",
                extra_prov={"productEligible": False},
            )
            # Mirror coverage.productEligible=false used by GRID adapters.
            rows = [json.loads(l) for l in jsonl.read_text().splitlines() if l.strip()]
            for row in rows:
                if row.get("rfc461Schema") == "rofl_coverage":
                    row["productEligible"] = False
            jsonl.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
            with self.assertRaises(SystemExit) as ctx:
                validate_mod.validate_product(jsonl, tl)
            self.assertIn("productEligible", str(ctx.exception))

    def test_grid_unit_health_source_rejected_when_hp_known(self):
        """Stripping sourceKind is not enough if unit healthSource stays grid_*."""
        with tempfile.TemporaryDirectory() as tmp:
            td = Path(tmp)
            jsonl, tl = _write_pair(
                td,
                source="replay_api_playback",
                source_kind="replay_api_playback",
                hp_coverage="partial",
                timeline_units_extra={
                    "hp": 1000.0,
                    "hpMax": 2000.0,
                    "hpKnown": True,
                },
            )
            rows = [json.loads(l) for l in jsonl.read_text().splitlines() if l.strip()]
            for row in rows:
                if row.get("rfc461Schema") == "stats_update":
                    for p in row.get("participants") or []:
                        p["health"] = 1000.0
                        p["healthMax"] = 2000.0
                        p["healthSource"] = "grid_riot_livestats"
            jsonl.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
            with self.assertRaises(SystemExit) as ctx:
                validate_mod.validate_product(jsonl, tl)
            self.assertIn("grid_riot_livestats", str(ctx.exception))

    def test_require_calculator_ready_fails_when_hp_coverage_none(self):
        """R21 H3: --require-calculator-ready must refuse incomplete HP/combat."""
        with tempfile.TemporaryDirectory() as tmp:
            td = Path(tmp)
            jsonl, tl = _write_pair(
                td,
                source="replay_api_playback",
                source_kind="replay_api_playback",
                hp_coverage="none",
                position_coverage="full_at_sampled_frames",
            )
            with self.assertRaises(SystemExit) as ctx:
                validate_mod.validate_product(
                    jsonl, tl, require_calculator_ready=True
                )
            msg = str(ctx.exception)
            self.assertIn("calculator-ready", msg)
            self.assertIn("hpTrusted=False", msg)
            self.assertIn("hpCoverage='none'", msg)
            self.assertIn("hp=False", msg)
            self.assertIn("combat=False", msg)

    def test_require_calculator_ready_fails_on_fountain_placeholders(self):
        """R21 H3: fountain_placeholder_only can never satisfy calculator claim."""
        with tempfile.TemporaryDirectory() as tmp:
            td = Path(tmp)
            jsonl, tl = _write_pair(
                td,
                source="rofl_upgrade_spell_ranks_fuse",
                source_kind="rofl_upgrade_spell_ranks_fuse",
                hp_coverage="none",
                position_coverage="fountain_placeholder_only",
                calculator_ready_note=True,
            )
            product = None
            with self.assertRaises(SystemExit) as ctx:
                product = validate_mod.validate_product(jsonl, tl)
            self.assertIsNone(product)
            msg = str(ctx.exception)
            self.assertIn("calculator-ready", msg)
            self.assertIn("positionCoverage='fountain_placeholder_only'", msg)
            self.assertIn("hpTrusted=False", msg)

    def test_provenance_calculator_ready_flag_cannot_bypass_gates(self):
        """R21 H3: stamping calculatorReady:true in provenance still fails closed."""
        with tempfile.TemporaryDirectory() as tmp:
            td = Path(tmp)
            jsonl, tl = _write_pair(
                td,
                source="replay_api_playback",
                source_kind="replay_api_playback",
                hp_coverage="none",
                extra_prov={"calculatorReady": True},
            )
            tl_obj = json.loads(tl.read_text())
            tl_obj["provenance"] = dict(tl_obj.get("provenance") or {})
            tl_obj["provenance"]["calculatorReady"] = True
            tl.write_text(json.dumps(tl_obj) + "\n", encoding="utf-8")
            with self.assertRaises(SystemExit) as ctx:
                validate_mod.validate_product(jsonl, tl)
            msg = str(ctx.exception)
            self.assertIn("calculator-ready", msg)
            self.assertIn("hpTrusted=False", msg)
            self.assertIn("hpCoverage='none'", msg)

    def test_loltmnt_scaffold_require_calculator_ready_refuses(self):
        """R21 H3: preferred pro scaffold stays red under --require-calculator-ready."""
        match_dir = ROOT / "artifacts/rofl/LOLTMNT01-426746"
        jsonl = match_dir / "events.ranks-trusted.scaffold.rfc461.jsonl"
        timeline = match_dir / "timeline.ranks-scaffold.json"
        if not jsonl.is_file() or not timeline.is_file():
            self.skipTest("LOLTMNT01-426746 scaffold artifacts not present")
        # Plain --product may be green (artifacts-first ranks scaffold).
        product = validate_mod.validate_product(jsonl, timeline)
        self.assertTrue(product["ok"])
        self.assertFalse(product["hpTrusted"])
        self.assertFalse(product["calculatorReady"])
        self.assertEqual(product.get("hpCoverage"), "none")
        self.assertEqual(
            product.get("positionCoverage"), "fountain_placeholder_only"
        )
        with self.assertRaises(SystemExit) as ctx:
            validate_mod.validate_product(
                jsonl, timeline, require_calculator_ready=True
            )
        msg = str(ctx.exception)
        self.assertIn("hpTrusted=False", msg)
        self.assertIn("hpCoverage='none'", msg)
        self.assertIn("positionCoverage='fountain_placeholder_only'", msg)
        self.assertIn("hp=False", msg)
        self.assertIn("combat=False", msg)


class LivingPostSeedCalculatorReadyTests(unittest.TestCase):
    """R15 Path1: living_post_seed_v1 honesty (dead/pre-seed may stay unknown)."""

    @staticmethod
    def _unit(
        pid: int,
        *,
        alive: bool = True,
        hp: bool = False,
        combat: bool = False,
        ranks: bool = True,
        hp_source: str | None = None,
        combat_source: str | None = None,
    ) -> dict:
        row: Dict[str, Any] = {
            "pid": pid,
            "alive": alive,
            "hpKnown": hp,
            "combatStatsKnown": combat,
            "abilityRanksKnown": ranks,
        }
        if hp_source is not None:
            row["hpSource"] = hp_source
        if combat_source is not None:
            row["combatStatsSource"] = combat_source
        return row

    def test_evaluate_allows_dead_and_preseed_unknown(self):
        pe = "same_match_replication_type107_pe_wire_table"
        frames = [
            {
                "t": 100,
                "units": [
                    self._unit(1, alive=True),  # pre-seed unknown OK
                    self._unit(2, alive=False),  # dead unknown OK
                ],
            },
            {
                "t": 200,
                "units": [
                    self._unit(
                        1,
                        hp=True,
                        combat=True,
                        hp_source="pe",
                        combat_source=pe,
                    ),
                    self._unit(
                        2,
                        hp=True,
                        combat=True,
                        hp_source="pe",
                        combat_source=pe,
                    ),
                ],
            },
            {
                "t": 300,
                "units": [
                    self._unit(
                        1,
                        hp=True,
                        combat=True,
                        hp_source="hold_forward",
                        combat_source="hold_forward",
                    ),
                    self._unit(2, alive=False),  # dead after seed OK
                ],
            },
        ]
        metrics = validate_mod.evaluate_calculator_ready_policies(
            frames, expected_units=2
        )
        self.assertTrue(metrics["livingPostSeedCalculatorReady"])
        self.assertFalse(metrics["strictAllFrameCalculatorReady"])
        self.assertEqual(metrics["livingMissSlots"], 0)
        self.assertGreater(metrics["preSeedSlots"], 0)
        self.assertGreater(metrics["deadSlots"], 0)

    def test_evaluate_requires_living_postseed_triple(self):
        pe = "same_match_replication_type107_pe_wire_table"
        frames = [
            {
                "t": 100,
                "units": [
                    self._unit(
                        1,
                        hp=True,
                        combat=True,
                        hp_source="pe",
                        combat_source=pe,
                    ),
                ],
            },
            {
                "t": 200,
                "units": [
                    # Past both seeds, alive, but HP dropped → must fail living gate.
                    self._unit(
                        1,
                        hp=False,
                        combat=True,
                        combat_source="hold_forward",
                    ),
                ],
            },
        ]
        metrics = validate_mod.evaluate_calculator_ready_policies(
            frames, expected_units=1
        )
        self.assertFalse(metrics["livingPostSeedCalculatorReady"])
        self.assertEqual(metrics["livingMissSlots"], 1)

    def test_evaluate_treats_post_death_before_hp_reseed_as_preseed(self):
        pe = "same_match_replication_type107_pe_wire_table"
        frames = [
            {
                "t": 100,
                "units": [
                    self._unit(
                        1,
                        hp=True,
                        combat=True,
                        hp_source="pe",
                        combat_source=pe,
                    ),
                ],
            },
            {"t": 200, "units": [self._unit(1, alive=False)]},
            {
                "t": 300,
                "units": [
                    # Respawn before HP PE re-seed: HP unknown, combat may hold.
                    self._unit(
                        1,
                        hp=False,
                        combat=True,
                        combat_source="hold_forward",
                    ),
                ],
            },
            {
                "t": 400,
                "units": [
                    self._unit(
                        1,
                        hp=True,
                        combat=True,
                        hp_source="pe",
                        combat_source="hold_forward",
                    ),
                ],
            },
        ]
        metrics = validate_mod.evaluate_calculator_ready_policies(
            frames, expected_units=1
        )
        self.assertTrue(metrics["livingPostSeedCalculatorReady"])
        self.assertEqual(metrics["livingMissSlots"], 0)
        self.assertFalse(metrics["strictAllFrameCalculatorReady"])

    def test_evaluate_hp_hold_across_respawn_counts_post_respawn_hold(self):
        """With hpHoldAcrossRespawn, post-death hold_forward is living-required."""
        pe = "same_match_replication_type107_pe_wire_table"
        frames = [
            {
                "t": 100,
                "units": [
                    self._unit(
                        1,
                        hp=True,
                        combat=True,
                        hp_source="pe",
                        combat_source=pe,
                    ),
                ],
            },
            {"t": 200, "units": [self._unit(1, alive=False)]},
            {
                "t": 300,
                "units": [
                    self._unit(
                        1,
                        hp=True,
                        combat=True,
                        hp_source="hold_forward",
                        combat_source="hold_forward",
                    ),
                ],
            },
        ]
        # Default clear-on-death: hold after death still re-seeds via hold_forward tag.
        metrics_default = validate_mod.evaluate_calculator_ready_policies(
            frames, expected_units=1
        )
        self.assertTrue(metrics_default["livingPostSeedCalculatorReady"])

        # Explicit across-respawn provenance: seed survives death even if a
        # respawn frame briefly lacks hold tags but later holds.
        frames_gap = [
            {
                "t": 100,
                "units": [
                    self._unit(
                        1,
                        hp=True,
                        combat=True,
                        hp_source="pe",
                        combat_source=pe,
                    ),
                ],
            },
            {"t": 200, "units": [self._unit(1, alive=False)]},
            {
                "t": 300,
                "units": [
                    # Alive post-respawn without tags → living miss under across-respawn.
                    self._unit(1, hp=False, combat=True, combat_source="hold_forward"),
                ],
            },
        ]
        metrics_gap = validate_mod.evaluate_calculator_ready_policies(
            frames_gap,
            expected_units=1,
            hp_hold_across_respawn=True,
        )
        self.assertFalse(metrics_gap["livingPostSeedCalculatorReady"])
        self.assertEqual(metrics_gap["livingMissSlots"], 1)
        self.assertTrue(metrics_gap["hpHoldAcrossRespawn"])

        # Same gap without across-respawn stays pre-seed (legacy clear).
        metrics_legacy = validate_mod.evaluate_calculator_ready_policies(
            frames_gap,
            expected_units=1,
            hp_hold_across_respawn=False,
        )
        self.assertTrue(metrics_legacy["livingPostSeedCalculatorReady"])
        self.assertEqual(metrics_legacy["livingMissSlots"], 0)
        self.assertGreater(metrics_legacy["preSeedSlots"], 0)

    def test_default_policy_stays_strict_without_disclosure(self):
        policy = validate_mod._resolve_calculator_ready_policy(
            cli_policy=None,
            provenance={},
            timeline_provenance={},
        )
        self.assertEqual(policy, validate_mod.CALCULATOR_READY_POLICY_STRICT)

    def test_provenance_policy_selects_living_post_seed(self):
        policy = validate_mod._resolve_calculator_ready_policy(
            cli_policy=None,
            provenance={},
            timeline_provenance={
                "calculatorReadyPolicy": "living_post_seed_v1",
            },
        )
        self.assertEqual(
            policy, validate_mod.CALCULATOR_READY_POLICY_LIVING_POST_SEED
        )

    def test_cli_policy_overrides_provenance(self):
        policy = validate_mod._resolve_calculator_ready_policy(
            cli_policy="strict_all_frame_v1",
            provenance={"calculatorReadyPolicy": "living_post_seed_v1"},
            timeline_provenance={"calculatorReadyPolicy": "living_post_seed_v1"},
        )
        self.assertEqual(policy, validate_mod.CALCULATOR_READY_POLICY_STRICT)

    def test_unknown_policy_fails_closed(self):
        with self.assertRaises(SystemExit) as ctx:
            validate_mod._resolve_calculator_ready_policy(
                cli_policy=None,
                provenance={"calculatorReadyPolicy": "weaken_silently_v0"},
                timeline_provenance={},
            )
        self.assertIn("unknown calculatorReadyPolicy", str(ctx.exception))

    def test_living_policy_require_calculator_ready_message_discloses_policy(self):
        """Living policy must not silently use strict wording when claim fails."""
        with tempfile.TemporaryDirectory() as tmp:
            td = Path(tmp)
            jsonl, tl = _write_pair(
                td,
                source="replay_api_playback",
                source_kind="replay_api_playback",
                hp_coverage="none",
                position_coverage="full_at_sampled_frames",
                extra_prov={"calculatorReadyPolicy": "living_post_seed_v1"},
            )
            with self.assertRaises(SystemExit) as ctx:
                validate_mod.validate_product(
                    jsonl,
                    tl,
                    require_calculator_ready=True,
                    calculator_ready_policy="living_post_seed_v1",
                )
            msg = str(ctx.exception)
            self.assertIn("living_post_seed_v1", msg)
            self.assertIn("livingReady=", msg)
            self.assertNotIn("every frame/unit", msg)


class ProvenanceBehaviorTests(unittest.TestCase):
    def test_maknee_marks_synthetic_path_walking(self):
        fixture = ROOT / "docs/rofl-research/fixtures/fur_parity_maknee_events.json"
        match = json.loads(fixture.read_text(encoding="utf-8"))
        rows = maknee.convert(match, hz=1.0, game_id=2970115)
        cov = next(r for r in rows if r.get("rfc461Schema") == "rofl_coverage")
        prov = cov["provenance"]
        self.assertEqual(prov["sourceKind"], maknee.SYNTHETIC_SOURCE_KIND)
        self.assertEqual(prov["positionSynthesis"], maknee.POSITION_SYNTHESIS)
        self.assertTrue(prov.get("publicationBlocked"))
        self.assertTrue(prov.get("researchOnly"))
        self.assertNotEqual(prov.get("positionCoverage"), "full_at_sampled_frames")
        self.assertIn("synthetic", (prov.get("notes") or "").lower())

    def test_fuse_static_snapshot_marks_research_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            td = Path(tmp)
            jsonl, _tl = _write_pair(
                td,
                source="replay_api_playback",
                source_kind="replay_api_playback",
                hp_coverage="none",
            )
            rows = [json.loads(l) for l in jsonl.read_text().splitlines() if l.strip()]
            # Ensure health fields absent for fuse to fill.
            for row in rows:
                if row.get("rfc461Schema") != "stats_update":
                    continue
                for p in row["participants"]:
                    p.pop("health", None)
                    p.pop("healthMax", None)
            hp = {i: (500.0 + i, 1000.0 + i) for i in range(1, 11)}
            fused = fuse.fuse(rows, hp_by_pid=hp, static_snapshot=True)
            cov = next(r for r in fused if r.get("rfc461Schema") == "rofl_coverage")
            prov = cov["provenance"]
            self.assertEqual(prov["hpCoverage"], "snapshot_fused")
            self.assertEqual(prov["sourceKind"], fuse.STATIC_SNAPSHOT_SOURCE_KIND)
            self.assertTrue(prov.get("publicationBlocked"))
            self.assertTrue(prov.get("researchOnly"))
            self.assertIn("RESEARCH", prov.get("notes") or "")

            # Product gate must reject this coverage even if we build a matching timeline.
            tl_path = td / "fused_tl.json"
            tl = {
                "id": "fused",
                "name": "3264383283",
                "source": "replay_api_playback",
                "provenance": dict(prov),
                "participants": [],
                "frames": [
                    {
                        "t": 60_000,
                        "units": [
                            {
                                "pid": i,
                                "champ": f"C{i}",
                                "hpKnown": True,
                                "combatStatsKnown": False,
                                "abilityRanksKnown": False,
                                "hp": 500,
                                "hpMax": 1000,
                                "ad": 0,
                                "ap": 0,
                                "armor": 0,
                                "mr": 0,
                            }
                            for i in range(1, 11)
                        ],
                    }
                ],
                "hasCareerStats": False,
            }
            # Rebuild jsonl from fused rows for product gate.
            out_jsonl = td / "fused.jsonl"
            rfc461_emit.write_jsonl(out_jsonl, fused)
            # Need game_info in fused stream — already present from _write_pair.
            tl["provenance"]["matchCode"] = "3264383283"
            tl_path.write_text(json.dumps(tl) + "\n", encoding="utf-8")
            # Fill game_info participants on timeline for roster checks.
            info = next(r for r in fused if r.get("rfc461Schema") == "game_info")
            tl["participants"] = info["participants"]
            tl_path.write_text(json.dumps(tl) + "\n", encoding="utf-8")
            with self.assertRaises(SystemExit):
                validate_mod.validate_product(out_jsonl, tl_path)

    def test_schema_proof_cli_refuses_public_data_output(self):
        forbidden = ROOT / "public/data/_schema_proof_forbidden_test"
        self.assertFalse(forbidden.exists(), f"unexpected test path already exists: {forbidden}")
        proc = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "run_live_fur_e2e.py"),
                "BR1-3264383283.rofl",
                "--out-dir",
                str(forbidden),
            ],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertIn("refusing schema-proof output inside public/data", proc.stderr)
        self.assertFalse(forbidden.exists())

    def test_schema_proof_has_no_live_product_timeline_alias(self):
        source = (SCRIPTS / "run_live_fur_e2e.py").read_text(encoding="utf-8")
        self.assertNotIn('out / "live_fur_timeline.json"', source)
        self.assertIn('out / "live_fur_schema_proof_timeline.json"', source)
        package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
        self.assertEqual(
            package["scripts"]["rofl:live-fur"],
            "npm run rofl:schema-proof --",
        )


if __name__ == "__main__":
    unittest.main()
