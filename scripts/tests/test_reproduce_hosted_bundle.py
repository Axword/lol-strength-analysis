"""Tests for the portable hosted-bundle entry point."""
from __future__ import annotations

import unittest

from scripts.reproduce_hosted_bundle import _require_public_patch


class HostedBundleEntryPointTests(unittest.TestCase):
    def test_accepts_current_public_patch_split(self) -> None:
        _require_public_patch(
            {
                "patch": "26.14",
                "publicPatch": "26.14",
                "embeddedPatch": "16.13",
            },
            "26.14",
        )

    def test_rejects_embedded_patch_in_player_facing_slot(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "expected public patch '26.14'.*patch='16.13', publicPatch=None",
        ):
            _require_public_patch({"patch": "16.13"}, "26.14")

    def test_rejects_mismatched_public_patch(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "expected public patch '26.14'.*patch='26.13', publicPatch='26.13'",
        ):
            _require_public_patch(
                {"patch": "26.13", "publicPatch": "26.13"},
                "26.14",
            )


if __name__ == "__main__":
    unittest.main()
