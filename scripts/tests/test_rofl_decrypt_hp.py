#!/usr/bin/env python3
"""Tests for Replication field catalog, decrypt probe, emitter, and HP fusion."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
ROOT = SCRIPTS.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import fuse_replay_api_hp as fuse  # noqa: E402
import maknee_packets_to_jsonl as maknee  # noqa: E402
import jsonl_to_timeline as j2t  # noqa: E402
import rofl2_packet_decrypt_probe as probe  # noqa: E402
import rofl2_to_maknee_events as emit  # noqa: E402
import rfc461_emit  # noqa: E402
from rofl_replication_fields import resolve_combat_stats  # noqa: E402

ACCEPT_FIXTURE = ROOT / "docs/rofl-research/fixtures/decrypt_hp_acceptance.json"


class ReplicationCombatMappingTests(unittest.TestCase):
    def test_resolve_ad_armor(self):
        resolved = resolve_combat_stats(
            {
                "mBaseAttackDamage": 70.0,
                "mFlatPhysicalDamageMod": 30.0,
                "mArmor": 40.0,
                "mBonusArmor": 15.0,
            }
        )
        assert resolved is not None
        self.assertAlmostEqual(resolved["attackDamage"], 100.0)
        self.assertAlmostEqual(resolved["armor"], 55.0)

    def test_no_combat_components_returns_none(self):
        self.assertIsNone(resolve_combat_stats({"mHP": 500.0}))


class DecryptProbeFixtureTests(unittest.TestCase):
    def test_fixture_backend_ten_hero_hp(self):
        report = probe.decrypt_replication_fields(
            backend="fixture",
            fixture_events=ACCEPT_FIXTURE,
        )
        self.assertTrue(report["ok"], report.get("decryptStatus"))
        snap = report["hpSnapshot"]
        self.assertEqual(snap["heroCount"], 10)
        self.assertTrue(snap["acceptance"]["passed"])
        for h in snap["heroes"]:
            self.assertGreater(h["mMaxHP"], 100)
            self.assertGreater(h["mHP"], 0)
            self.assertLessEqual(h["mHP"], h["mMaxHP"])

    def test_emulator_backend_fail_closed(self):
        report = probe.decrypt_replication_fields(backend="emulator")
        self.assertFalse(report["ok"])
        # May be accessor-only or packet-drive statuses; never invent HP.
        self.assertIn("decryptStatus", report)
        self.assertFalse(report["ok"])
        self.assertEqual(report.get("replication"), [])


class AccessorSpikeTests(unittest.TestCase):
    def test_registrar_finds_mhp_slots_when_binary_present(self):
        from pathlib import Path

        import rofl2_accessor_spike as spike

        binary = spike.DEFAULT_UNIVERSAL_BINARY
        if not binary.is_file():
            self.skipTest("League binary not installed")
        report = spike.run_accessor_spike(
            league_binary=binary,
            work_dir=Path("/tmp/lol-accessor-spike-test"),
        )
        self.assertIn(report["decryptStatus"], {
            "accessor_offsets_found_need_packet_drive",
            "accessor_slots_driven_need_packet_deserialize",
            "blocked_need_packet_accessor",
        })
        reg = report.get("registrar") or {}
        if report["decryptStatus"] in (
            "accessor_offsets_found_need_packet_drive",
            "accessor_slots_driven_need_packet_deserialize",
        ):
            self.assertEqual(reg["mHP"]["slotOffset"], 0x8D8)
            self.assertEqual(reg["mMaxHP"]["slotOffset"], 0x900)
            self.assertTrue((report.get("unicornSmoke") or {}).get("ok"))
            self.assertGreaterEqual(reg.get("fieldCount", 0), 2)
        if report["decryptStatus"] == "accessor_slots_driven_need_packet_deserialize":
            self.assertTrue((report.get("slotGetterDrive") or {}).get("ok"))


class EmitterAndMapperTests(unittest.TestCase):
    def test_emit_then_jsonl_has_hp_and_combat(self):
        report = probe.decrypt_replication_fields(
            backend="fixture",
            fixture_events=ACCEPT_FIXTURE,
        )
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            probe_path = td_path / "probe.json"
            events_path = td_path / "events.json"
            jsonl_path = td_path / "out.jsonl"
            timeline_path = td_path / "timeline.json"
            probe_path.write_text(json.dumps(report), encoding="utf-8")
            built = emit.build_events(
                probe=report,
                fixture_events=ACCEPT_FIXTURE,
            )
            events_path.write_text(json.dumps(built), encoding="utf-8")
            lines = maknee.convert(built, hz=1.0, game_id=42)
            rfc461_emit.write_jsonl(jsonl_path, lines)
            # HP present on stats_update
            stats = [r for r in lines if r["rfc461Schema"] == "stats_update"]
            self.assertGreaterEqual(len(stats), 1)
            late = stats[-1]["participants"]
            self.assertEqual(len(late), 10)
            for p in late:
                self.assertIn("health", p)
                self.assertIn("healthMax", p)
                self.assertEqual(p.get("healthSource"), "replication_decoded")
                self.assertEqual(p.get("abilityRanksSource"), "unavailable")
            # pid 1 should have combat from Replication components
            p1 = next(p for p in late if p["participantID"] == 1)
            self.assertEqual(p1.get("combatStatsSource"), "replication_decoded")
            self.assertAlmostEqual(float(p1["attackDamage"]), 100.0)
            self.assertAlmostEqual(float(p1["armor"]), 55.0)

            tl = j2t.build_timeline(
                jsonl_path,
                timeline_id="decrypt_accept",
                name="decrypt accept",
                patch="test",
            )
            u1 = tl["frames"][-1]["units"][0]
            self.assertTrue(u1["hpKnown"])
            self.assertTrue(u1["combatStatsKnown"])
            self.assertFalse(u1["abilityRanksKnown"])
            self.assertGreater(u1["hpMax"], 100)


class FuseReplayApiHpTests(unittest.TestCase):
    def test_static_fuse_injects_health(self):
        report = probe.decrypt_replication_fields(
            backend="fixture",
            fixture_events=ACCEPT_FIXTURE,
        )
        # Minimal replay-api shaped JSONL
        parts = []
        for i in range(1, 11):
            parts.append(
                rfc461_emit.participant_row(
                    participant_id=i,
                    team_id=100 if i <= 5 else 200,
                    champion_name=f"C{i}",
                    player_name=f"p{i}",
                    position={"x": 1000.0 * i, "z": 2000.0},
                    position_source="replay_api_focus_selection",
                    health_known=False,
                    health_source="unavailable_replay_api",
                    combat_stats_source="unavailable_replay_api",
                    ability_ranks_source="unavailable_replay_api",
                )
            )
        rows = [
            rfc461_emit.coverage_line(
                source="replay_api_playback",
                decoded=["positions_focus_selection"],
                missing=["health", "healthMax", "combatStats", "abilityRanks"],
                provenance=rfc461_emit.provenance_record(
                    source="replay_api_playback",
                    source_kind="replay_api_playback",
                    position_coverage="full_at_sampled_frames",
                    hp_coverage="none",
                    roster_mapping="liveclient_playerlist_participantID",
                ),
            ),
            rfc461_emit.game_info_line(
                game_id=1,
                participants=[
                    {
                        "participantID": i,
                        "teamID": 100 if i <= 5 else 200,
                        "championName": f"C{i}",
                        "playerName": f"p{i}",
                    }
                    for i in range(1, 11)
                ],
            ),
            rfc461_emit.stats_update_line(
                game_id=1,
                game_time=600000,
                participants=parts,
            ),
        ]
        fused = fuse.fuse(
            rows,
            hp_by_pid=fuse._hp_by_participant_from_probe(report),
            static_snapshot=True,
        )
        cov = fused[0]
        self.assertIn("health_rofl2_replication_decrypt", cov["decoded"])
        self.assertNotIn("health", cov["missing"])
        stats = next(r for r in fused if r["rfc461Schema"] == "stats_update")
        for p in stats["participants"]:
            self.assertIn("health", p)
            self.assertEqual(p["healthSource"], "rofl2_replication_decrypt")
            self.assertEqual(p["abilityRanksSource"], "unavailable")
            self.assertEqual(p["combatStatsSource"], "unavailable")


if __name__ == "__main__":
    unittest.main()
