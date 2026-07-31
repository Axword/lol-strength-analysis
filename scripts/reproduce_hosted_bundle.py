#!/usr/bin/env python3
"""Fetch, validate, and build from a hosted reproduction bundle.

This is the portable second-machine entry point. It never receives or stores
provider credentials; the manifest supplies only HTTPS artifact URLs and
content hashes.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence


def _run(command: Sequence[str]) -> None:
    subprocess.run(list(command), check=True)


def _read_manifest(root: Path) -> Mapping[str, Any]:
    manifest_path = root / "repro-bundle.json"
    value = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise ValueError("fetched reproduction manifest must be an object")
    return value


def _artifact_path(manifest: Mapping[str, Any], role: str, root: Path) -> Path:
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list):
        raise ValueError("fetched reproduction manifest has no artifacts[]")
    for artifact in artifacts:
        if isinstance(artifact, Mapping) and artifact.get("role") == role:
            filename = artifact.get("filename")
            if not isinstance(filename, str) or Path(filename).name != filename:
                raise ValueError(f"invalid {role} artifact filename")
            return root / filename
    raise ValueError(f"missing {role} artifact")


def _require_public_patch(match: Mapping[str, Any], expected: str) -> None:
    if match.get("patch") != expected or match.get("publicPatch") != expected:
        raise ValueError(
            "fetched reproduction manifest does not carry the expected "
            f"public patch {expected!r}: "
            f"patch={match.get('patch')!r}, "
            f"publicPatch={match.get('publicPatch')!r}"
        )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, help="HTTPS bundle manifest URL")
    parser.add_argument("--out", required=True, type=Path, help="fresh local bundle directory")
    parser.add_argument(
        "--calculator-ready-policy",
        choices=("living_post_seed_v1", "strict_all_frame_v1"),
        default="living_post_seed_v1",
    )
    parser.add_argument(
        "--public-patch",
        default="26.14",
        help="Expected player-facing patch label (default: 26.14)",
    )
    parser.add_argument("--skip-build", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    root = args.out.expanduser().resolve()
    _run(
        [
            sys.executable,
            "scripts/repro_bundle.py",
            "fetch",
            "--manifest",
            args.manifest,
            "--out",
            str(root),
        ]
    )

    manifest = _read_manifest(root)
    match = manifest.get("match")
    if not isinstance(match, Mapping):
        raise ValueError("fetched reproduction manifest has no match object")
    _require_public_patch(match, args.public_patch)
    jsonl = _artifact_path(manifest, "canonical_rfc461_jsonl", root)
    timeline = _artifact_path(manifest, "timeline_json", root)
    _run(
        [
            sys.executable,
            "scripts/validate-rofl-pipeline.py",
            "--product",
            "--require-calculator-ready",
            "--calculator-ready-policy",
            args.calculator_ready_policy,
            "--require-aa-timeline",
            "--jsonl",
            str(jsonl),
            "--timeline",
            str(timeline),
        ]
    )
    if not args.skip_build:
        _run(["npm", "run", "build"])

    print(
        json.dumps(
            {
                "ok": True,
                "bundleId": manifest.get("bundleId"),
                "out": str(root),
                "publicPatch": args.public_patch,
                "calculatorReadyPolicy": args.calculator_ready_policy,
                "build": not args.skip_build,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
