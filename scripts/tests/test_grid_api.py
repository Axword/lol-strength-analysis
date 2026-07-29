#!/usr/bin/env python3
"""Unit tests for GRID API helpers (no live network)."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import grid_api as grid  # noqa: E402


class TestHelpers(unittest.TestCase):
    def test_team_match_fuzzy(self) -> None:
        self.assertTrue(grid.is_team_match("Gen.G", "Gen.G Esports"))
        self.assertTrue(grid.is_team_match("karmine", "Karmine Corp"))
        self.assertFalse(grid.is_team_match("T1", "Gen.G Esports"))

    def test_sanitize_filename(self) -> None:
        self.assertEqual(grid.sanitize_filename("Gen.G vs T1"), "Gen.G_vs_T1")

    def test_api_key_required(self) -> None:
        with mock.patch.dict("os.environ", {}, clear=True):
            with mock.patch.object(grid, "load_dotenv", lambda path=None: None):
                with self.assertRaises(grid.GridApiError):
                    grid.api_key()


class TestProOnlyGuard(unittest.TestCase):
    def test_looks_like_scrim(self) -> None:
        self.assertTrue(grid.looks_like_scrim("T1 Scrims"))
        self.assertTrue(grid.looks_like_scrim("practice lobby"))
        self.assertTrue(grid.looks_like_scrim(["Gen.G", "Scrim Team Blue"]))
        self.assertFalse(grid.looks_like_scrim("Gen.G Esports", "Karmine Corp"))
        self.assertFalse(grid.looks_like_scrim("2970110"))

    def test_search_blocks_scrim_team_query(self) -> None:
        with self.assertRaises(grid.GridProOnlyError):
            grid.fetch_series_for_team("T1 scrims")

    def test_download_blocks_scrim_filename(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(grid.GridProOnlyError):
                grid.download_series_games(
                    "2970110",
                    out_dir=Path(tmp),
                    filename_base="T1_Scrim_vs_GenG",
                    require_live_pro_check=False,
                )

    def test_cli_scrim_search_exit_code(self) -> None:
        code = grid.main(["search", "--team", "scrim practice"])
        self.assertEqual(code, 3)


class TestDownload(unittest.TestCase):
    def test_download_stops_on_404(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)

            def fake_download(url: str, dest: Path, *, timeout: float = 120.0) -> int:
                if url.endswith("/games/1"):
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_text('{"seriesId":"1"}\n', encoding="utf-8")
                    return 200
                return 404

            with mock.patch.object(grid, "_http_download", side_effect=fake_download):
                results = grid.download_series_games(
                    "2970110",
                    out_dir=out,
                    filename_base="Test_vs_Test",
                    max_games=5,
                    require_live_pro_check=False,
                )
            self.assertEqual(results[0]["status"], "downloaded")
            self.assertEqual(results[1]["status"], "not_found")
            self.assertTrue((out / "events_2970110_1_riot.jsonl").is_file())

    def test_assert_series_is_pro_requires_esports(self) -> None:
        with mock.patch.object(
            grid,
            "fetch_series_central",
            return_value={
                "id": "1",
                "type": "ESPORTS",
                "tournament": {"id": "t", "name": "Esports World Cup"},
                "teams": [
                    {"baseInfo": {"name": "Gen.G Esports"}},
                    {"baseInfo": {"name": "T1"}},
                ],
            },
        ):
            pro = grid.assert_series_is_pro("1")
            self.assertEqual(pro["type"], "ESPORTS")

        with mock.patch.object(
            grid,
            "fetch_series_central",
            return_value={
                "id": "2",
                "type": "OTHER",
                "tournament": {"id": "t", "name": "Something"},
                "teams": [{"baseInfo": {"name": "A"}}, {"baseInfo": {"name": "B"}}],
            },
        ):
            with self.assertRaises(grid.GridProOnlyError):
                grid.assert_series_is_pro("2")

    def test_download_series_files_uses_list_urls(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)

            def fake_json(url: str, **kwargs: object) -> dict:
                self.assertIn("/file-download/list/2970110", url)
                return {
                    "files": [
                        {
                            "id": "events-grid",
                            "status": "ready",
                            "fileName": "events_2970110_grid.jsonl.zip",
                            "fullURL": "https://api.grid.gg/file-download/events/grid/series/2970110",
                        }
                    ]
                }

            def fake_download(url: str, dest: Path, *, timeout: float = 180.0) -> int:
                dest.write_bytes(b"PK\x03\x04fake")
                return 200

            with mock.patch.object(
                grid,
                "assert_series_is_pro",
                return_value={
                    "id": "2970110",
                    "type": "ESPORTS",
                    "tournament": "EWC",
                    "teams": ["A", "B"],
                },
            ), mock.patch.object(grid, "_http_json", side_effect=fake_json), mock.patch.object(
                grid, "_http_download", side_effect=fake_download
            ):
                results = grid.download_series_files(
                    "2970110",
                    out_dir=out,
                    include=("events-grid",),
                )
            self.assertEqual(results[0]["status"], "downloaded")
            self.assertTrue((out / "events_2970110_grid.jsonl.zip").is_file())


class TestSearchPaging(unittest.TestCase):
    def test_fetch_series_filters_team_and_drops_scrims(self) -> None:
        pages = [
            {
                "allSeries": {
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                    "edges": [
                        {
                            "node": {
                                "id": "111",
                                "type": "ESPORTS",
                                "startTimeScheduled": "2026-07-01T00:00:00Z",
                                "tournament": {"id": "t1", "name": "EWC Group B"},
                                "teams": [
                                    {"baseInfo": {"name": "Gen.G Esports"}},
                                    {"baseInfo": {"name": "T1"}},
                                ],
                            }
                        },
                        {
                            "node": {
                                "id": "333",
                                "type": "ESPORTS",
                                "startTimeScheduled": "2026-07-03T00:00:00Z",
                                "tournament": {"id": "t3", "name": "Private Scrim Block"},
                                "teams": [
                                    {"baseInfo": {"name": "Gen.G Esports"}},
                                    {"baseInfo": {"name": "Gen.G Academy"}},
                                ],
                            }
                        },
                        {
                            "node": {
                                "id": "222",
                                "type": "ESPORTS",
                                "startTimeScheduled": "2026-07-02T00:00:00Z",
                                "tournament": {"id": "t2", "name": "LEC"},
                                "teams": [
                                    {"baseInfo": {"name": "Karmine Corp"}},
                                    {"baseInfo": {"name": "G2 Esports"}},
                                ],
                            }
                        },
                    ],
                }
            }
        ]

        with mock.patch.object(grid, "graphql", side_effect=pages):
            found = grid.fetch_series_for_team("Gen.G", limit=5)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["id"], "111")


if __name__ == "__main__":
    unittest.main()
