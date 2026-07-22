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
