from __future__ import annotations

import functools
import json
import struct
import tempfile
import threading
import unittest
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from scripts.repro_bundle import (
    BundleError,
    create_manifest,
    fetch_bundle,
    validate_manifest,
    verify_local_bundle,
)


GAME_ID = 1234567
PLATFORM_ID = "BR1"
PATCH_BUILD = "16.14.794.5912"
CHAMPIONS = [
    "Renekton",
    "LeeSin",
    "Ahri",
    "Jhin",
    "Nami",
    "Camille",
    "Lillia",
    "Zed",
    "Ashe",
    "Sona",
]


def _participants(*, puuid_prefix: str = "player") -> list[dict[str, object]]:
    return [
        {
            "PUUID": f"{puuid_prefix}-{index}",
            "SKIN": champion,
            "TEAM": "100" if index <= 5 else "200",
            "RIOT_ID_GAME_NAME": f"Player {index}",
            "RIOT_ID_TAG_LINE": "TEST",
        }
        for index, champion in enumerate(CHAMPIONS, 1)
    ]


def _write_rofl(
    path: Path,
    *,
    participants: list[dict[str, object]],
    game_id: int = GAME_ID,
) -> None:
    metadata = {
        "platformId": PLATFORM_ID,
        "gameId": str(game_id),
        "gameLength": 1800000,
        "statsJson": participants,
    }
    encoded_metadata = json.dumps(metadata, separators=(",", ":")).encode("utf-8")
    version = PATCH_BUILD.encode("ascii")
    data = bytearray(b"RIOT\x02\x00")
    data.extend(b"\x00" * 8)
    data.append(len(version))
    data.extend(version)
    data.extend(struct.pack("<IIII", 0, 0, 0, 0))
    data.extend(b"fixture-packet-section")
    data.extend(encoded_metadata)
    data.extend(struct.pack("<I", len(encoded_metadata)))
    path.write_bytes(bytes(data))


def _write_jsonl(
    path: Path,
    *,
    participants: list[dict[str, object]],
    game_id: int = GAME_ID,
    platform_on_coverage_only: bool = False,
) -> None:
    rows = [
        {
            "rfc461Schema": "rofl_coverage",
            "gameID": game_id,
            "gridSeriesId": "2970110",
            "calculatorReady": False,
            "productEligible": False,
            "provenance": {
                "sourceKind": "grid_riot_livestats",
                "platformID": PLATFORM_ID,
            },
        },
        {
            "rfc461Schema": "game_info",
            "gameID": game_id,
            **({} if platform_on_coverage_only else {"platformID": PLATFORM_ID}),
            "gameVersion": PATCH_BUILD,
            "participants": [
                {
                    "participantID": index,
                    "puuid": row["PUUID"],
                    "championName": row["SKIN"],
                    "teamID": row["TEAM"],
                }
                for index, row in enumerate(participants, 1)
            ],
        },
    ]
    path.write_text(
        "".join(json.dumps(row, separators=(",", ":")) + "\n" for row in rows),
        encoding="utf-8",
    )


def _write_timeline(
    path: Path,
    *,
    game_id: int = GAME_ID,
    timeline_id: str | None = None,
) -> None:
    timeline = {
        "id": timeline_id or str(game_id),
        "patch": "16.14",
        "provenance": {
            "gameId": game_id,
            "matchCode": str(game_id),
        },
        "participants": [
            {
                "participantID": index,
                "championName": champion,
                "teamID": 100 if index <= 5 else 200,
            }
            for index, champion in enumerate(CHAMPIONS, 1)
        ],
        "frames": [],
    }
    path.write_text(json.dumps(timeline), encoding="utf-8")


def _make_bundle(root: Path) -> tuple[Path, Path, Path]:
    rofl = root / f"{PLATFORM_ID}-{GAME_ID}.rofl"
    jsonl = root / "events.rfc461.jsonl"
    timeline = root / "timeline.json"
    participants = _participants()
    _write_rofl(rofl, participants=participants)
    _write_jsonl(jsonl, participants=participants)
    _write_timeline(timeline)
    return rofl, jsonl, timeline


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, _format: str, *_args: object) -> None:
        return


class ReproBundleTests(unittest.TestCase):
    def test_create_and_verify_certifies_same_match_without_product_authority(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rofl, jsonl, timeline = _make_bundle(root)
            manifest = create_manifest(
                rofl_path=rofl,
                jsonl_path=jsonl,
                timeline_path=timeline,
                url_base="https://example.test/matches/1234567/",
            )

            self.assertEqual(manifest["schema"], "lol-strength-repro-bundle-v1")
            self.assertEqual(manifest["match"]["gameId"], GAME_ID)
            self.assertEqual(manifest["sameMatch"]["status"], "verified")
            self.assertEqual(
                manifest["sameMatch"]["method"],
                "riot_match_identity_plus_puuid_and_champion_rosters",
            )
            self.assertFalse(manifest["policy"]["secretsIncluded"])
            self.assertEqual(
                manifest["policy"]["upstreamDeclarations"]["calculatorReady"],
                False,
            )
            self.assertIn(
                "do not establish calculatorReady",
                manifest["sameMatch"]["limits"],
            )
            self.assertTrue(all(row["url"] for row in manifest["artifacts"]))

            result = verify_local_bundle(manifest, root)
            self.assertTrue(result["ok"])
            self.assertEqual(result["sameMatch"], "verified")
            self.assertEqual(len(result["artifacts"]), 3)

    def test_create_fails_closed_when_puuid_rosters_differ(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rofl, jsonl, timeline = _make_bundle(root)
            _write_jsonl(jsonl, participants=_participants(puuid_prefix="other"))

            with self.assertRaisesRegex(BundleError, "PUUID rosters differ"):
                create_manifest(
                    rofl_path=rofl,
                    jsonl_path=jsonl,
                    timeline_path=timeline,
                )

    def test_create_accepts_disclosed_tournament_identity_locations(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rofl, jsonl, timeline = _make_bundle(root)
            _write_jsonl(
                jsonl,
                participants=_participants(),
                platform_on_coverage_only=True,
            )
            _write_timeline(timeline, timeline_id="2970110-g1")

            manifest = create_manifest(
                rofl_path=rofl,
                jsonl_path=jsonl,
                timeline_path=timeline,
            )

            self.assertEqual(manifest["match"]["platformId"], PLATFORM_ID)
            self.assertEqual(manifest["match"]["gameId"], GAME_ID)

    def test_verify_rejects_content_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rofl, jsonl, timeline = _make_bundle(root)
            manifest = create_manifest(
                rofl_path=rofl,
                jsonl_path=jsonl,
                timeline_path=timeline,
            )
            timeline.write_text("{}\n", encoding="utf-8")

            with self.assertRaisesRegex(BundleError, "size mismatch|SHA-256 mismatch"):
                verify_local_bundle(manifest, root)

    def test_manifest_rejects_path_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rofl, jsonl, timeline = _make_bundle(root)
            manifest = create_manifest(
                rofl_path=rofl,
                jsonl_path=jsonl,
                timeline_path=timeline,
            )
            manifest["artifacts"][0]["filename"] = "../escape.rofl"

            with self.assertRaisesRegex(BundleError, "must be a basename"):
                validate_manifest(manifest, require_urls=False)

    def test_manifest_rejects_spoofed_bundle_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rofl, jsonl, timeline = _make_bundle(root)
            manifest = create_manifest(
                rofl_path=rofl,
                jsonl_path=jsonl,
                timeline_path=timeline,
            )
            manifest["bundleId"] = "br1-1234567-0000000000000000"

            with self.assertRaisesRegex(BundleError, "bundleId does not match"):
                validate_manifest(manifest, require_urls=False)

    def test_fetch_remote_manifest_downloads_atomically_and_verifies(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            server_root = Path(tmp) / "server"
            out_root = Path(tmp) / "download"
            server_root.mkdir()
            rofl, jsonl, timeline = _make_bundle(server_root)
            handler = functools.partial(QuietHandler, directory=str(server_root))
            server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                base = f"http://127.0.0.1:{server.server_port}/"
                manifest = create_manifest(
                    rofl_path=rofl,
                    jsonl_path=jsonl,
                    timeline_path=timeline,
                    url_base=base,
                )
                manifest_path = server_root / "repro-bundle.json"
                manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

                result = fetch_bundle(base + "repro-bundle.json", out_root)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)

            self.assertTrue(result["ok"])
            self.assertEqual(result["bundleId"], manifest["bundleId"])
            self.assertTrue((out_root / rofl.name).is_file())
            self.assertTrue((out_root / jsonl.name).is_file())
            self.assertTrue((out_root / timeline.name).is_file())
            self.assertTrue((out_root / "repro-bundle.json").is_file())


if __name__ == "__main__":
    unittest.main()
