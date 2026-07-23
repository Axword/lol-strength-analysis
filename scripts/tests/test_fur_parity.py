#!/usr/bin/env python3
"""FUR live-stats parity gates: checklist, VoidGrub→rebuild→grub touch, e2e."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
ROOT = SCRIPTS.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import maknee_packets_to_jsonl as maknee  # noqa: E402
import rfc461_emit  # noqa: E402
import validate_fur_parity as fur  # noqa: E402

FIXTURE = ROOT / "docs/rofl-research/fixtures/fur_parity_maknee_events.json"
CHECKLIST = ROOT / "docs/rofl-research/fur-parity-checklist.json"

# Keep in sync with src/engine/objectives.ts GRUB.totvTick*
_TOTV_MELEE = (0, 4, 12, 16)
_TOTV_INTERVAL = 0.5


def grub_touch_dps(stacks: int, ranged: bool = False) -> float:
    table = (0, 2, 6, 8) if ranged else _TOTV_MELEE
    s = max(0, min(3, int(stacks)))
    tick = table[s]
    return 0.0 if tick <= 0 else tick / _TOTV_INTERVAL


class FurParityChecklistTests(unittest.TestCase):
    def test_checklist_exists(self):
        self.assertTrue(CHECKLIST.is_file())
        data = json.loads(CHECKLIST.read_text(encoding="utf-8"))
        self.assertIn("stats_update", data["requiredSchemas"])
        self.assertIn("VoidGrub", data["requiredEpicMonsterTypes"])
        self.assertIn("health", data["requiredStatsUpdateParticipantFields"])
        self.assertIn("ability1Level", data["requiredStatsUpdateParticipantFields"])

    def test_mapper_jsonl_is_parity_fixture_not_strict_product(self):
        match = json.loads(FIXTURE.read_text(encoding="utf-8"))
        rows = maknee.convert(match, hz=1.0, game_id=2970115)
        with tempfile.TemporaryDirectory() as td:
            jsonl = Path(td) / "events.jsonl"
            rfc461_emit.write_jsonl(jsonl, rows)
            report = fur.evaluate(
                fur.load_jsonl(jsonl),
                fur.load_checklist(CHECKLIST),
                strict_product=True,
            )
            self.assertFalse(report["ok"], report)
            self.assertFalse(report["trustedHpGate"]["ok"])
            self.assertTrue(
                any(
                    "fixture" in error
                    or "untrusted" in error
                    or "identity" in error
                    for error in report["trustedHpGate"]["errors"]
                )
            )
            self.assertGreaterEqual(report["product"]["voidGrubKills"], 3)
            self.assertEqual(report["epicMonsterTypes"].get("VoidGrub"), 3)


class VoidGrubMapperGateTests(unittest.TestCase):
    def test_voidgrub_rebuild_stacks_and_touch_math(self):
        match = json.loads(FIXTURE.read_text(encoding="utf-8"))
        rows = maknee.convert(match, hz=1.0, game_id=2970115)
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            jsonl = td_path / "events.jsonl"
            timeline = td_path / "timeline.json"
            rfc461_emit.write_jsonl(jsonl, rows)
            subprocess.check_call(
                [
                    sys.executable,
                    str(SCRIPTS / "jsonl_to_timeline.py"),
                    str(jsonl),
                    "-o",
                    str(timeline),
                    "--id",
                    "fur_parity",
                    "--name",
                    "FUR parity",
                    "--patch",
                    "test",
                ],
                cwd=str(ROOT),
            )
            subprocess.check_call(
                [
                    sys.executable,
                    str(SCRIPTS / "rebuild-timeline-scoreboard.py"),
                    "--jsonl",
                    str(jsonl),
                    "--timeline",
                    str(timeline),
                    "-o",
                    str(timeline),
                ],
                cwd=str(ROOT),
            )
            tl = json.loads(timeline.read_text(encoding="utf-8"))
            stacks = 0
            for fr in tl["frames"]:
                sc = fr.get("score") or {}
                stacks = max(stacks, int((sc.get("blue") or {}).get("voidGrubs") or 0))
            self.assertEqual(stacks, 3)
            dps = grub_touch_dps(stacks)
            self.assertGreater(dps, 0)
            self.assertAlmostEqual(dps, 16 / 0.5)  # 3-stack melee


class FurParityE2ETests(unittest.TestCase):
    def test_fixture_pipeline_calculator_and_scoreboard(self):
        script = SCRIPTS / "run_fur_parity_e2e.py"
        with tempfile.TemporaryDirectory() as td:
            out_dir = Path(td) / "out"
            proc = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "--fixture",
                    str(FIXTURE),
                    "--out-dir",
                    str(out_dir),
                ],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            report = json.loads((out_dir / "fur_parity_report.json").read_text())
            self.assertTrue(report["ok"], report)
            gates = report["timelineGates"]
            self.assertTrue(gates["hpKnown"])
            self.assertTrue(gates["combatStatsKnown"])
            self.assertTrue(gates["abilityRanksKnown"])
            self.assertGreaterEqual(gates["voidGrubsBlue"] or 0, 1)


class AccessorSlotDriveTests(unittest.TestCase):
    def test_slot_drive_when_binary_present(self):
        import rofl2_accessor_spike as spike

        binary = spike.DEFAULT_UNIVERSAL_BINARY
        if not binary.is_file():
            self.skipTest("League binary not installed")
        report = spike.run_accessor_spike(
            league_binary=binary,
            work_dir=Path("/tmp/lol-accessor-spike-fur-test"),
        )
        self.assertIn(
            report["decryptStatus"],
            {
                "accessor_slots_driven_need_packet_deserialize",
                "accessor_offsets_found_need_packet_drive",
                "blocked_need_packet_accessor",
            },
        )
        self.assertFalse(report["ok"])  # no live ROFL HP yet
        drive = report.get("slotGetterDrive") or {}
        if report["decryptStatus"] == "accessor_slots_driven_need_packet_deserialize":
            self.assertTrue(drive.get("ok"))
            self.assertAlmostEqual(float(drive["mHP"]), 1234.5, places=2)


class WaypointMotionTests(unittest.TestCase):
    def test_out_of_order_events_still_apply_early_waypoints(self):
        """CreateNeutral at t=90 before WaypointGroup at t=5 must not skip the walk."""
        match = {
            "events": [
                {"CreateHero": {"time": 0.0, "net_id": 101, "name": "a", "champion": "Gnar"}},
                {"CreateHero": {"time": 0.0, "net_id": 102, "name": "b", "champion": "LeeSin"}},
                {"CreateHero": {"time": 0.0, "net_id": 103, "name": "c", "champion": "Ahri"}},
                {"CreateHero": {"time": 0.0, "net_id": 104, "name": "d", "champion": "Jinx"}},
                {"CreateHero": {"time": 0.0, "net_id": 105, "name": "e", "champion": "Thresh"}},
                {"CreateHero": {"time": 0.0, "net_id": 201, "name": "f", "champion": "Darius"}},
                {"CreateHero": {"time": 0.0, "net_id": 202, "name": "g", "champion": "Vi"}},
                {"CreateHero": {"time": 0.0, "net_id": 203, "name": "h", "champion": "Syndra"}},
                {"CreateHero": {"time": 0.0, "net_id": 204, "name": "i", "champion": "Samira"}},
                {"CreateHero": {"time": 0.0, "net_id": 205, "name": "j", "champion": "Nautilus"}},
                # Intentionally before the early waypoint in list order
                {
                    "CreateNeutral": {
                        "time": 90.0,
                        "net_id": 9001,
                        "skin_name": "SRU_VoidGrub",
                        "position1": {"x": 0.0, "z": 0.0},
                    }
                },
                {
                    "WaypointGroup": {
                        "time": 5.0,
                        "waypoints": {
                            "1": [
                                {"x": -7000.0, "z": -7000.0},
                                {"x": -6000.0, "z": -6000.0},
                            ]
                        },
                    }
                },
            ]
        }
        rows = maknee.convert(match, hz=1.0, game_id=3264383283)
        updates = [r for r in rows if r.get("rfc461Schema") == "stats_update"]
        self.assertGreater(len(updates), 20)
        # By ~20s champ 1 should have left fountain toward the lane path.
        by_t = {int(r["gameTime"]): r for r in updates}
        p0 = next(p for p in by_t[0]["participants"] if p["participantID"] == 1)
        p20 = next(p for p in by_t[20000]["participants"] if p["participantID"] == 1)
        self.assertEqual(p0.get("positionSource"), "fountain_placeholder")
        self.assertEqual(p20.get("positionSource"), "maknee_waypoint")
        d = (
            (p20["position"]["x"] - p0["position"]["x"]) ** 2
            + (p20["position"]["z"] - p0["position"]["z"]) ** 2
        ) ** 0.5
        self.assertGreater(d, 500.0)
        # Motion should be gradual: 6s vs 20s not identical teleport-to-end.
        p6 = next(p for p in by_t[6000]["participants"] if p["participantID"] == 1)
        d6 = (
            (p6["position"]["x"] - p0["position"]["x"]) ** 2
            + (p6["position"]["z"] - p0["position"]["z"]) ** 2
        ) ** 0.5
        self.assertGreater(d, d6 + 100.0)

    def test_synthetic_waypoint_drain_stops_at_safety_cap(self):
        champs = [
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
        events = [
            {
                "CreateHero": {
                    "time": 0.0,
                    "net_id": 101 + i,
                    "name": f"p{i + 1}",
                    "champion": champ,
                }
            }
            for i, champ in enumerate(champs)
        ]
        # More than 12 minutes of valid-map walking at 375 u/s. The synthetic
        # drain must stop at 180s instead of consuming the entire path.
        long_path = [
            {"x": 400.0 if i % 2 == 0 else 14_400.0, "z": 400.0}
            for i in range(22)
        ]
        events.append(
            {
                "WaypointGroup": {
                    "time": 0.0,
                    "waypoints": {"1": long_path},
                }
            }
        )

        rows = maknee.convert({"events": events}, hz=1.0, game_id=3264383283)
        updates = [row for row in rows if row.get("rfc461Schema") == "stats_update"]
        game_end = next(row for row in rows if row.get("rfc461Schema") == "game_end")

        cap_ms = int(maknee.MAX_PATH_DRAIN_SECONDS * 1000)
        self.assertEqual(int(game_end["gameTime"]), cap_ms)
        self.assertEqual(max(int(row["gameTime"]) for row in updates), cap_ms)
        self.assertLessEqual(len(updates), int(maknee.MAX_PATH_DRAIN_SECONDS) + 1)


if __name__ == "__main__":
    unittest.main()
